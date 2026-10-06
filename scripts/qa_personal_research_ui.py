"""準備並啟動使用固定 QA SQLite 複本的個人研究 UI。"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import sys
from typing import Any, Mapping
from uuid import uuid4

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from data_module.config import TWStockConfig


QA_ROOT = REPOSITORY_ROOT / "output" / "qa" / "personal_daily_product_20261006"
REPO_IGNORED_QA_ROOT = REPOSITORY_ROOT / "output" / "qa"
RUNS_ROOT = QA_ROOT / "personal_research_ui"
PINNED_SNAPSHOT_RELATIVE = Path(
    "output/qa/personal_daily_product_20261006/real_source_validation_runs/"
    "formal_source_snapshot_v2/twstock.db"
)
PINNED_SNAPSHOT_RECEIPT_RELATIVE = PINNED_SNAPSHOT_RELATIVE.parent / "snapshot_receipt.json"
PINNED_SNAPSHOT_SHA256 = "c99c497657ca4ef63c73e56151d135996e3f2144ec45f8bf4b053eecf8dc5d08"
PINNED_SNAPSHOT_RECEIPT_SHA256 = "15e1f66f496865f55f97e6e76d1bb291cb1cb842d42d29ee42b7e8905f5b0e83"
PINNED_SCHEMA_SHA256 = "dc5a37f20103d1e14d9bc97914bb8680c40901a0cdad014ea985b1d82e98690f"
PINNED_SNAPSHOT_SIZE_BYTES = 3_827_728_384
MAX_SNAPSHOT_RECEIPT_BYTES = 2 * 1024 * 1024
MAX_MANIFEST_BYTES = 256 * 1024
COPY_CHUNK_BYTES = 8 * 1024 * 1024
MIN_FREE_SPACE_AFTER_COPY_BYTES = 1024 * 1024 * 1024
LEARNING_PIN_MAX_FILES = 10_000
LEARNING_PIN_MAX_FILE_BYTES = 512 * 1024 * 1024
LEARNING_PIN_MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_ISOLATED_ARTIFACT_ENV = (
    "RESEARCH_CONSOLE_PROJECTION",
    "P0_SOURCE_CONTROL_CENTER_AUDIT",
    "P0_SOURCE_CONTROL_CENTER_DECISIONS",
    "P0_SOURCE_CONTROL_CENTER_LICENSE_EVIDENCE",
    "PROGRAM_READINESS_ARTIFACT",
    "MONTHLY_REVENUE_AVAILABILITY_CANDIDATE",
    "MONTHLY_REVENUE_SNAPSHOT_CANDIDATE",
    "DATA_UPDATE_STATUS_ARTIFACT",
    "DATA_FRESHNESS_STATUS_ARTIFACT",
    "DATA_UPDATE_HISTORY_ARTIFACT",
    "TPEX_REFRESH_STATUS_ARTIFACT",
    "EVIDENCE_REHEARSAL_REPORT",
    "WEEKLY_EVIDENCE_HISTORY_PROJECTION_PATH",
    "BANKTAIWAN_RECOMMENDATION_LEARNING_OUTPUT_ROOT",
    "PAPER_EQUAL_WEIGHT_BENCHMARK_PATH",
    "PAPER_TRADE_LEDGER_PATH",
)


class IsolationError(RuntimeError):
    """隔離路徑、來源 pin 或複本驗證失敗時拋出的錯誤。"""


@dataclass(frozen=True)
class SnapshotAuthority:
    """已核准 QA 快照及其完整結構摘要。"""

    snapshot_path: Path
    receipt_path: Path
    snapshot_sha256: str
    receipt_sha256: str
    snapshot_size_bytes: int
    schema_sha256: str
    schema_object_count: int
    table_row_counts: Mapping[str, int]


@dataclass(frozen=True)
class RuntimeLayout:
    """PROFILE=test 後的精確產品路徑。"""

    run_root: Path
    data_root_base: Path
    output_root_base: Path
    data_root_actual: Path
    output_root_actual: Path
    working_db_path: Path
    policy_config_path: Path
    receipts_dir: Path


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _is_reparse_point(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT
    )


def _assert_no_reparse_components(path: Path, *, allow_missing: bool) -> Path:
    """拒絕路徑中的 symlink／junction，並回傳絕對正規化路徑。"""

    absolute = Path(os.path.abspath(os.fspath(path)))
    cursor = Path(absolute.anchor)
    for index, part in enumerate(absolute.parts[1:], start=1):
        cursor = cursor / part
        is_leaf = index == len(absolute.parts) - 1
        try:
            info = cursor.lstat()
        except FileNotFoundError:
            if allow_missing:
                continue
            raise IsolationError(f"必要路徑不存在：{cursor}") from None
        if _is_reparse_point(info):
            raise IsolationError(f"路徑不可包含 symlink／junction：{cursor}")
        if not is_leaf and not stat.S_ISDIR(info.st_mode):
            raise IsolationError(f"路徑中間元件不是目錄：{cursor}")
    return absolute.resolve(strict=not allow_missing)


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.path.normpath(str(left))) == os.path.normcase(
        os.path.normpath(str(right))
    )


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _assert_disjoint(label: str, path: Path, other_label: str, other: Path) -> None:
    if path == other or _is_within(path, other) or _is_within(other, path):
        raise IsolationError(f"{label} 與 {other_label} 必須是互相分離的路徑")


def _identity(info: os.stat_result) -> dict[str, int]:
    return {"device": int(info.st_dev), "inode": int(info.st_ino)}


def _same_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return left.st_dev == right.st_dev and left.st_ino == right.st_ino


def _open_regular_file(path: Path):
    """在開啟前後核對同一個一般檔案，拒絕已知 reparse point。"""

    absolute = _assert_no_reparse_components(path, allow_missing=False)
    before = absolute.lstat()
    if _is_reparse_point(before) or not stat.S_ISREG(before.st_mode):
        raise IsolationError(f"只接受一般檔案：{absolute}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    descriptor = os.open(absolute, flags)
    try:
        opened = os.fstat(descriptor)
        after = absolute.lstat()
        if (
            not stat.S_ISREG(opened.st_mode)
            or _is_reparse_point(opened)
            or _is_reparse_point(after)
            or not _same_identity(before, opened)
            or not _same_identity(opened, after)
            or opened.st_size != after.st_size
        ):
            raise IsolationError(f"檔案身分在開啟時改變：{absolute}")
        return os.fdopen(descriptor, "rb"), opened
    except Exception:
        os.close(descriptor)
        raise


def _sha256_regular_file(path: Path, *, max_bytes: int | None = None) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    stream, opened = _open_regular_file(path)
    with stream:
        while True:
            chunk = stream.read(COPY_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if max_bytes is not None and total > max_bytes:
                raise IsolationError(f"檔案超過讀取上限 {max_bytes} bytes：{path}")
            digest.update(chunk)
        final = os.fstat(stream.fileno())
        current = Path(path).lstat()
        if not _same_identity(opened, final) or not _same_identity(final, current):
            raise IsolationError(f"檔案在雜湊期間改變：{path}")
        if total != final.st_size:
            raise IsolationError(f"檔案讀取長度與 stat 不符：{path}")
    return digest.hexdigest(), total


def _read_bounded_bytes(path: Path, limit: int) -> bytes:
    stream, opened = _open_regular_file(path)
    with stream:
        if opened.st_size > limit:
            raise IsolationError(f"檔案超過讀取上限 {limit} bytes：{path}")
        data = stream.read(limit + 1)
        if len(data) > limit:
            raise IsolationError(f"檔案超過讀取上限 {limit} bytes：{path}")
        if len(data) != opened.st_size:
            raise IsolationError(f"檔案讀取長度與 stat 不符：{path}")
        final = os.fstat(stream.fileno())
        current = Path(path).lstat()
        if not _same_identity(opened, final) or not _same_identity(final, current):
            raise IsolationError(f"檔案在讀取期間改變：{path}")
        return data


def _stat_existing_directory(path: Path) -> os.stat_result:
    absolute = _assert_no_reparse_components(path, allow_missing=False)
    info = absolute.stat()
    if not stat.S_ISDIR(info.st_mode) or _is_reparse_point(info):
        raise IsolationError(f"只接受一般目錄：{absolute}")
    if info.st_ino == 0:
        raise IsolationError(f"檔案系統未提供可用目錄身分：{absolute}")
    return info


def _directory_tree_pin(root: Path) -> dict[str, Any]:
    """以有界逐檔雜湊固定唯讀 learning root，不載入模型。"""

    root = _assert_no_reparse_components(root, allow_missing=False)
    root_info = _stat_existing_directory(root)
    records: list[dict[str, Any]] = []
    total_bytes = 0
    pending = [root]
    while pending:
        directory = pending.pop()
        _assert_no_reparse_components(directory, allow_missing=False)
        try:
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda item: item.name)
        except OSError as exc:
            raise IsolationError(f"無法讀取 learning root：{directory}: {exc}") from exc
        for entry in entries:
            path = Path(entry.path)
            info = entry.stat(follow_symlinks=False)
            if _is_reparse_point(info):
                raise IsolationError(f"learning root 不可含 symlink／junction：{path}")
            relative = path.relative_to(root).as_posix()
            if stat.S_ISDIR(info.st_mode):
                pending.append(path)
                records.append(
                    {"kind": "directory", "path": relative, **_identity(info)}
                )
                if len(records) > LEARNING_PIN_MAX_FILES:
                    raise IsolationError("learning root 項目超過 10,000 個上限")
                continue
            if not stat.S_ISREG(info.st_mode):
                raise IsolationError(f"learning root 含非一般檔案：{path}")
            if len(records) >= LEARNING_PIN_MAX_FILES:
                raise IsolationError("learning root 項目超過 10,000 個上限")
            if info.st_size > LEARNING_PIN_MAX_FILE_BYTES:
                raise IsolationError(f"learning root 單檔超過 512 MiB 上限：{path}")
            total_bytes += int(info.st_size)
            if total_bytes > LEARNING_PIN_MAX_TOTAL_BYTES:
                raise IsolationError("learning root 總檔案量超過 2 GiB 上限")
            file_hash, file_size = _sha256_regular_file(path, max_bytes=LEARNING_PIN_MAX_FILE_BYTES)
            if file_size != info.st_size:
                raise IsolationError(f"learning root 檔案在雜湊期間改變：{path}")
            records.append(
                {
                    "kind": "file",
                    "path": relative,
                    **_identity(info),
                    "size_bytes": file_size,
                    "sha256": file_hash,
                }
            )
    records.sort(key=lambda item: (str(item["path"]), str(item["kind"])))
    fingerprint = hashlib.sha256(_canonical_json_bytes(records)).hexdigest()
    return {
        "path": str(root),
        "directory_identity": _identity(root_info),
        "entry_count": len(records),
        "file_count": sum(record["kind"] == "file" for record in records),
        "total_file_bytes": total_bytes,
        "tree_sha256": fingerprint,
        "bounds": {
            "max_entries": LEARNING_PIN_MAX_FILES,
            "max_file_bytes": LEARNING_PIN_MAX_FILE_BYTES,
            "max_total_bytes": LEARNING_PIN_MAX_TOTAL_BYTES,
        },
    }


def _sqlite_summary(path: Path) -> dict[str, Any]:
    """以唯讀、query-only 連線回讀資料庫結構與逐表筆數。"""

    _assert_no_reparse_components(path, allow_missing=False)
    uri = path.resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=30)
    try:
        connection.execute("PRAGMA query_only=ON")
        if int(connection.execute("PRAGMA query_only").fetchone()[0]) != 1:
            raise IsolationError("SQLite 未啟用 query_only")
        rows = connection.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()
        canonical = json.dumps(rows, ensure_ascii=False, separators=(",", ":"), default=str)
        tables = [str(row[1]) for row in rows if row[0] == "table"]
        counts: dict[str, int] = {}
        for table in tables:
            quoted = '"' + table.replace('"', '""') + '"'
            counts[table] = int(connection.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0])
        return {
            "schema_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            "schema_object_count": len(rows),
            "table_count": len(tables),
            "table_row_counts": counts,
            "query_only": True,
        }
    except sqlite3.Error as exc:
        raise IsolationError(f"無法唯讀驗證 SQLite 複本：{exc}") from exc
    finally:
        connection.close()


def _validate_sqlite_summary(actual: Mapping[str, Any], authority: SnapshotAuthority) -> None:
    expected = {
        "schema_sha256": authority.schema_sha256,
        "schema_object_count": authority.schema_object_count,
        "table_count": len(authority.table_row_counts),
        "table_row_counts": dict(authority.table_row_counts),
        "query_only": True,
    }
    if dict(actual) != expected:
        raise IsolationError("工作複本的 SQLite schema/table rows 與固定 snapshot receipt 不符")


def _load_pinned_snapshot_authority(
    snapshot_path: Path,
    receipt_path: Path,
    *,
    repository_root: Path | None = None,
) -> SnapshotAuthority:
    """只接受 repo 內已固定 SHA 的 QA snapshot 與 receipt。"""

    repository_root = repository_root or REPOSITORY_ROOT
    repo_root = _assert_no_reparse_components(repository_root, allow_missing=False)
    expected_snapshot = (repo_root / PINNED_SNAPSHOT_RELATIVE).resolve(strict=True)
    expected_receipt = (repo_root / PINNED_SNAPSHOT_RECEIPT_RELATIVE).resolve(strict=True)
    snapshot = _assert_no_reparse_components(snapshot_path, allow_missing=False)
    receipt = _assert_no_reparse_components(receipt_path, allow_missing=False)
    if not _same_path(snapshot, expected_snapshot):
        raise IsolationError(f"來源 DB 必須是固定 QA snapshot：{expected_snapshot}")
    if not _same_path(receipt, expected_receipt):
        raise IsolationError(f"snapshot receipt 必須是固定 QA receipt：{expected_receipt}")
    receipt_bytes = _read_bounded_bytes(receipt, MAX_SNAPSHOT_RECEIPT_BYTES)
    receipt_hash = hashlib.sha256(receipt_bytes).hexdigest()
    if receipt_hash != PINNED_SNAPSHOT_RECEIPT_SHA256:
        raise IsolationError("固定 QA snapshot receipt SHA 不符")
    try:
        payload = json.loads(receipt_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IsolationError(f"固定 QA snapshot receipt 格式無效：{exc}") from exc
    if not isinstance(payload, dict):
        raise IsolationError("固定 QA snapshot receipt 必須是 JSON object")
    schema = payload.get("snapshot_schema")
    if not isinstance(schema, dict):
        raise IsolationError("固定 QA snapshot receipt 缺 snapshot_schema")
    raw_path = payload.get("snapshot_path")
    try:
        receipt_snapshot_path = Path(str(raw_path)).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise IsolationError("snapshot receipt 的路徑無法解析") from exc
    if (
        payload.get("schema_version") != "formal-sqlite-source-snapshot.v1"
        or payload.get("method") != "sqlite3.Connection.backup from mode=ro source with query_only=ON"
        or payload.get("snapshot_scope") != "repo-ignored QA only; no formal-data writes"
        or payload.get("snapshot_sha256") != PINNED_SNAPSHOT_SHA256
        or payload.get("snapshot_integrity_check") != ["ok"]
        or payload.get("snapshot_data_version_stable") is not True
        or schema.get("schema_sha256") != PINNED_SCHEMA_SHA256
        or int(schema.get("logical_size_bytes", -1)) != PINNED_SNAPSHOT_SIZE_BYTES
        or int(schema.get("table_count", -1)) != len(schema.get("table_row_counts", {}))
        or not _same_path(receipt_snapshot_path, snapshot)
    ):
        raise IsolationError("固定 QA snapshot receipt 的內容與核准 pin 不符")
    raw_counts = schema.get("table_row_counts")
    if not isinstance(raw_counts, dict) or not raw_counts:
        raise IsolationError("固定 QA snapshot receipt 缺 table row counts")
    counts: dict[str, int] = {}
    for name, count in raw_counts.items():
        if not isinstance(name, str) or type(count) is not int or count < 0:
            raise IsolationError("固定 QA snapshot receipt 的 table row count 格式無效")
        counts[name] = count
    snapshot_info = snapshot.stat()
    if not stat.S_ISREG(snapshot_info.st_mode) or _is_reparse_point(snapshot_info):
        raise IsolationError("固定 QA snapshot 必須是一般檔案")
    if snapshot_info.st_size != PINNED_SNAPSHOT_SIZE_BYTES:
        raise IsolationError("固定 QA snapshot 長度與核准 pin 不符")
    return SnapshotAuthority(
        snapshot_path=snapshot,
        receipt_path=receipt,
        snapshot_sha256=PINNED_SNAPSHOT_SHA256,
        receipt_sha256=receipt_hash,
        snapshot_size_bytes=PINNED_SNAPSHOT_SIZE_BYTES,
        schema_sha256=PINNED_SCHEMA_SHA256,
        schema_object_count=int(schema.get("schema_object_count", -1)),
        table_row_counts=counts,
    )


def _runtime_layout(run_root: Path) -> RuntimeLayout:
    run_root = Path(os.path.abspath(os.fspath(run_root)))
    data_base = run_root / "data"
    output_base = run_root / "output"
    data_actual = data_base / "_test"
    output_actual = output_base / "_test"
    return RuntimeLayout(
        run_root=run_root,
        data_root_base=data_base,
        output_root_base=output_base,
        data_root_actual=data_actual,
        output_root_actual=output_actual,
        working_db_path=data_actual / "sqlite" / "twstock.db",
        policy_config_path=run_root / "app_config" / "personal_use_policy.json",
        receipts_dir=run_root / "receipts",
    )


def _verify_test_profile_config(config: TWStockConfig, layout: RuntimeLayout) -> None:
    pairs = (
        (Path(config.data_root), layout.data_root_actual, "DATA_ROOT"),
        (Path(config.output_root), layout.output_root_actual, "OUTPUT_ROOT"),
        (Path(config.db_file), layout.working_db_path, "SQLite DB"),
    )
    if config.profile != "test":
        raise IsolationError("launcher 僅接受 PROFILE=test")
    for actual, expected, label in pairs:
        if not _same_path(actual.resolve(strict=False), expected.resolve(strict=False)):
            raise IsolationError(f"PROFILE=test 的 {label} 實際路徑錯誤：{actual} != {expected}")
        if not _is_within(actual.resolve(strict=False), layout.run_root.resolve(strict=False)):
            raise IsolationError(f"{label} 離開隔離 run root：{actual}")


def _copy_snapshot_create_only(
    source_path: Path,
    destination_path: Path,
    *,
    expected_sha256: str,
    expected_size_bytes: int,
    minimum_free_space_bytes: int = MIN_FREE_SPACE_AFTER_COPY_BYTES,
) -> dict[str, Any]:
    """將固定來源以新一般檔案複製，拒絕連結並讀回驗 hash。"""

    source_path = _assert_no_reparse_components(source_path, allow_missing=False)
    destination_path = _assert_no_reparse_components(destination_path, allow_missing=True)
    before = source_path.lstat()
    if not stat.S_ISREG(before.st_mode) or _is_reparse_point(before):
        raise IsolationError("snapshot 來源必須是一般檔案")
    if before.st_size != expected_size_bytes:
        raise IsolationError("snapshot 來源長度與固定 pin 不符")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    _assert_no_reparse_components(destination_path.parent, allow_missing=False)
    free_bytes = shutil.disk_usage(destination_path.parent).free
    if free_bytes < expected_size_bytes + minimum_free_space_bytes:
        raise IsolationError(
            f"QA 磁碟空間不足：需要至少 {expected_size_bytes + minimum_free_space_bytes} bytes"
        )

    source_stream, opened_source = _open_regular_file(source_path)
    destination_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        destination_fd = os.open(destination_path, destination_flags, 0o600)
    except Exception:
        source_stream.close()
        raise
    digest = hashlib.sha256()
    copied_bytes = 0
    try:
        with source_stream:
            with os.fdopen(destination_fd, "wb") as destination_stream:
                while True:
                    chunk = source_stream.read(COPY_CHUNK_BYTES)
                    if not chunk:
                        break
                    copied_bytes += len(chunk)
                    if copied_bytes > expected_size_bytes:
                        raise IsolationError("snapshot 來源讀取期間超過固定長度")
                    digest.update(chunk)
                    destination_stream.write(chunk)
                destination_stream.flush()
                os.fsync(destination_stream.fileno())
                final_source = os.fstat(source_stream.fileno())
                current_source = source_path.lstat()
                if (
                    not _same_identity(opened_source, final_source)
                    or not _same_identity(final_source, current_source)
                    or final_source.st_size != expected_size_bytes
                ):
                    raise IsolationError("snapshot 來源在複製期間改變")
        copied_hash = digest.hexdigest()
        if copied_bytes != expected_size_bytes or copied_hash != expected_sha256:
            raise IsolationError("snapshot 複製來源的長度或 SHA-256 與核准 pin 不符")
    except Exception:
        try:
            os.close(destination_fd)
        except OSError:
            pass
        raise

    destination_info = destination_path.lstat()
    if not stat.S_ISREG(destination_info.st_mode) or _is_reparse_point(destination_info):
        raise IsolationError("工作 DB 複本不是一般檔案")
    if _same_identity(opened_source, destination_info) or os.path.samefile(
        source_path, destination_path
    ):
        raise IsolationError("工作 DB 不可 hardlink 或 alias 固定 snapshot")
    readback_hash, readback_size = _sha256_regular_file(
        destination_path, max_bytes=expected_size_bytes
    )
    if readback_hash != expected_sha256 or readback_size != expected_size_bytes:
        raise IsolationError("工作 DB 複本 readback SHA／長度與核准 snapshot 不符")
    return {
        "source_path": str(source_path),
        "source_sha256": expected_sha256,
        "source_size_bytes": expected_size_bytes,
        "source_file_identity": _identity(opened_source),
        "working_path": str(destination_path.resolve(strict=True)),
        "working_sha256": readback_hash,
        "working_size_bytes": readback_size,
        "working_file_identity": _identity(destination_info),
        "same_file_identity": False,
        "hardlink_or_symlink": False,
    }


def _learning_paths(
    learning_output_root: Path,
    *,
    data_root: Path,
    qa_root: Path,
    forbidden_paths: tuple[tuple[str, Path], ...] = (),
) -> tuple[Path, dict[str, Any]]:
    from app_module.recommendation_learning_paths import resolve_recommendation_learning_paths

    qa_root = _assert_no_reparse_components(qa_root, allow_missing=False)
    output_root_lexical = Path(os.path.abspath(os.fspath(learning_output_root)))
    if not _is_within(output_root_lexical, qa_root):
        # 先以詞法路徑拒絕 QA root 外路徑，不對 D: 等正式磁碟做 stat。
        raise IsolationError("learning output root 必須位於 repo-ignored output/qa root")
    output_root = _assert_no_reparse_components(output_root_lexical, allow_missing=False)
    if not _is_within(output_root, qa_root):
        raise IsolationError("learning output root 解析後離開 repo-ignored output/qa root")
    for other_label, other_path in forbidden_paths:
        _assert_disjoint("learning output root", output_root, other_label, other_path)
    paths = resolve_recommendation_learning_paths(
        data_root=data_root,
        explicit_output_root=output_root,
    )
    learning_root = _assert_no_reparse_components(paths.learning_root, allow_missing=False)
    if not _is_within(learning_root, qa_root):
        raise IsolationError("resolved learning root 必須位於 repo-ignored output/qa root")
    for other_label, other_path in forbidden_paths:
        _assert_disjoint("learning root", learning_root, other_label, other_path)
    if _is_within(learning_root, data_root) or _is_within(data_root, learning_root):
        raise IsolationError("learning root 與隔離 DATA_ROOT 必須分離")
    info = _stat_existing_directory(learning_root)
    return learning_root, {
        "learning_output_root": str(output_root),
        "learning_root": str(learning_root),
        "directory_identity": _identity(info),
        "directory_mtime_ns": int(info.st_mtime_ns),
        "tree_pin": _directory_tree_pin(learning_root),
        "writes_by_launcher": False,
    }


def _make_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    manifest = dict(payload)
    manifest["manifest_sha256"] = hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()
    return manifest


def _write_json_create_only(path: Path, payload: Mapping[str, Any]) -> None:
    _assert_no_reparse_components(path.parent, allow_missing=False)
    content = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def _read_manifest(path: Path) -> dict[str, Any]:
    raw = _read_bounded_bytes(path, MAX_MANIFEST_BYTES)
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IsolationError(f"隔離 manifest 無效：{exc}") from exc
    if not isinstance(manifest, dict):
        raise IsolationError("隔離 manifest 必須是 JSON object")
    claimed = manifest.get("manifest_sha256")
    body = dict(manifest)
    body.pop("manifest_sha256", None)
    actual = hashlib.sha256(_canonical_json_bytes(body)).hexdigest()
    if claimed != actual or manifest.get("schema_version") != "personal-research-ui-isolation.v1":
        raise IsolationError("隔離 manifest 自身 SHA 或 schema 不符")
    return manifest


def _verify_source_snapshot_cli_inputs(
    snapshot_path: Path,
    receipt_path: Path,
    *,
    repository_root: Path | None = None,
) -> SnapshotAuthority:
    repository_root = repository_root or REPOSITORY_ROOT
    return _load_pinned_snapshot_authority(
        snapshot_path,
        receipt_path,
        repository_root=repository_root,
    )


def prepare_isolated_workspace(
    *,
    run_root: Path,
    policy_config_path: Path,
    learning_output_root: Path,
    authority: SnapshotAuthority,
    qa_root: Path = QA_ROOT,
    learning_qa_root: Path | None = None,
    minimum_free_space_bytes: int = MIN_FREE_SPACE_AFTER_COPY_BYTES,
) -> tuple[Path, dict[str, Any]]:
    """建立全新 run root，複製固定 snapshot 並保存 self-hashed manifest。"""

    qa_root = _assert_no_reparse_components(qa_root, allow_missing=False)
    run_root = _assert_no_reparse_components(run_root, allow_missing=True)
    if run_root == qa_root or not _is_within(run_root, qa_root):
        raise IsolationError("run root 必須是 repo-ignored QA root 內的新子目錄")
    runs_root = _assert_no_reparse_components(RUNS_ROOT, allow_missing=True)
    if qa_root == QA_ROOT.resolve(strict=False) and not _is_within(run_root, runs_root):
        raise IsolationError("正式啟動的 run root 必須在 personal_research_ui/ 下")
    if run_root.exists():
        raise IsolationError(f"run root 已存在，拒絕覆寫：{run_root}")
    if not policy_config_path.is_absolute():
        raise IsolationError("policy config path 必須是絕對路徑")
    expected_layout = _runtime_layout(run_root)
    policy_config_path = _assert_no_reparse_components(policy_config_path, allow_missing=True)
    if not _same_path(policy_config_path, expected_layout.policy_config_path):
        raise IsolationError("policy config path 必須固定在 run root/app_config/personal_use_policy.json")
    learning_qa_root = _assert_no_reparse_components(
        learning_qa_root or REPO_IGNORED_QA_ROOT,
        allow_missing=False,
    )
    learning_output_root = Path(os.path.abspath(os.fspath(learning_output_root)))
    if not _is_within(learning_output_root, learning_qa_root):
        # 先拒絕 QA root 外的詞法路徑，不對正式磁碟或其路徑元件做 stat。
        raise IsolationError("learning output root 必須位於 repo-ignored output/qa root")
    _assert_disjoint("run root", run_root, "source snapshot", authority.snapshot_path)
    _assert_disjoint("run root", run_root, "learning output root", learning_output_root)
    _assert_disjoint(
        "learning output root",
        learning_output_root,
        "fixed QA snapshot",
        authority.snapshot_path,
    )
    learning_output_root = _assert_no_reparse_components(
        learning_output_root, allow_missing=False
    )
    run_root.parent.mkdir(parents=True, exist_ok=True)
    _assert_no_reparse_components(run_root.parent, allow_missing=False)
    run_root.mkdir(exist_ok=False)
    layout = _runtime_layout(run_root)
    policy_config_path.parent.mkdir(parents=True, exist_ok=False)
    layout.receipts_dir.mkdir(parents=True, exist_ok=False)

    config = TWStockConfig(
        data_root=layout.data_root_base,
        output_root=layout.output_root_base,
        profile="test",
    )
    _verify_test_profile_config(config, layout)
    if policy_config_path.exists():
        raise IsolationError("全新 run root 不應已有個人 policy 檔案")
    for candidate_path in (
        layout.run_root,
        layout.data_root_actual,
        layout.output_root_actual,
        layout.working_db_path.parent,
        policy_config_path.parent,
        layout.receipts_dir,
    ):
        if not _is_within(candidate_path.resolve(strict=False), layout.run_root.resolve(strict=True)):
            raise IsolationError(f"隔離目錄離開 run root：{candidate_path}")

    learning_root, learning_pin = _learning_paths(
        learning_output_root,
        data_root=layout.data_root_actual,
        qa_root=learning_qa_root,
        forbidden_paths=(
            ("run root", layout.run_root),
            ("fixed QA snapshot", authority.snapshot_path),
        ),
    )
    _assert_disjoint("learning root", learning_root, "run root", layout.run_root)
    _assert_disjoint("learning root", learning_root, "snapshot", authority.snapshot_path)

    copied = _copy_snapshot_create_only(
        authority.snapshot_path,
        layout.working_db_path,
        expected_sha256=authority.snapshot_sha256,
        expected_size_bytes=authority.snapshot_size_bytes,
        minimum_free_space_bytes=minimum_free_space_bytes,
    )
    sqlite_scope = _sqlite_summary(layout.working_db_path)
    _validate_sqlite_summary(sqlite_scope, authority)
    manifest_path = layout.receipts_dir / "isolation_manifest.json"
    payload: dict[str, Any] = {
        "schema_version": "personal-research-ui-isolation.v1",
        "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
        "repository_root": str(REPOSITORY_ROOT.resolve()),
        "run_root": str(layout.run_root.resolve()),
        "profile": "test",
        "data_root_base": str(layout.data_root_base.resolve()),
        "data_root_actual": str(layout.data_root_actual.resolve()),
        "output_root_base": str(layout.output_root_base.resolve()),
        "output_root_actual": str(layout.output_root_actual.resolve()),
        "working_db_path": str(layout.working_db_path.resolve()),
        "policy_config_path": str(policy_config_path.resolve(strict=False)),
        "source_snapshot": {
            "path": str(authority.snapshot_path.resolve()),
            "sha256": authority.snapshot_sha256,
            "size_bytes": authority.snapshot_size_bytes,
            "receipt_path": str(authority.receipt_path.resolve()),
            "receipt_sha256": authority.receipt_sha256,
            "schema_sha256": authority.schema_sha256,
            "schema_object_count": authority.schema_object_count,
            "table_row_counts": dict(authority.table_row_counts),
            "snapshot_integrity_check": ["ok"],
        },
        "working_copy": copied,
        "working_sqlite_scope": sqlite_scope,
        "learning_root_read_only_pin": learning_pin,
        "write_scope": [
            str(layout.data_root_actual.resolve()),
            str(layout.output_root_actual.resolve()),
            str(policy_config_path.resolve(strict=False)),
            str(layout.receipts_dir.resolve()),
        ],
        "launcher_actions": {
            "formal_data_written": False,
            "http_requested": False,
            "training_started": False,
            "promotion_started": False,
            "scheduler_registered": False,
            "learning_root_written": False,
            "native_window_started": False,
        },
    }
    manifest = _make_manifest(payload)
    _write_json_create_only(manifest_path, manifest)
    return manifest_path, manifest


def _verify_prepared_workspace(
    *,
    run_root: Path,
    policy_config_path: Path,
    learning_output_root: Path,
) -> tuple[RuntimeLayout, dict[str, Any], dict[str, Any]]:
    run_root = _assert_no_reparse_components(run_root, allow_missing=False)
    if not _is_within(run_root, _assert_no_reparse_components(RUNS_ROOT, allow_missing=False)):
        raise IsolationError("預備工作區必須位於固定 QA personal_research_ui 根目錄")
    layout = _runtime_layout(run_root)
    manifest_path = layout.receipts_dir / "isolation_manifest.json"
    manifest = _read_manifest(manifest_path)
    if not _same_path(Path(str(manifest.get("run_root", ""))), run_root):
        raise IsolationError("manifest run root 與命令列路徑不符")
    if manifest.get("profile") != "test":
        raise IsolationError("manifest profile 不是 test")
    if not policy_config_path.is_absolute() or not _same_path(
        Path(os.path.abspath(os.fspath(policy_config_path))), layout.policy_config_path
    ):
        raise IsolationError("policy config path 與隔離 run root 不符")
    if not learning_output_root.is_absolute():
        raise IsolationError("learning output root 必須是絕對路徑")
    if not _same_path(
        Path(os.path.abspath(os.fspath(learning_output_root))),
        Path(str(manifest["learning_root_read_only_pin"]["learning_output_root"])),
    ):
        raise IsolationError("learning output root 與準備時的唯讀 pin 不符")
    _assert_disjoint("learning output root", learning_output_root, "run root", run_root)
    _assert_disjoint(
        "learning output root",
        learning_output_root,
        "fixed QA snapshot",
        REPOSITORY_ROOT / PINNED_SNAPSHOT_RELATIVE,
    )
    _assert_no_reparse_components(policy_config_path.parent, allow_missing=False)
    _assert_no_reparse_components(policy_config_path, allow_missing=True)
    if policy_config_path.exists():
        _assert_no_reparse_components(policy_config_path, allow_missing=False)
        info = policy_config_path.stat()
        if not stat.S_ISREG(info.st_mode):
            raise IsolationError("policy config 只能是一般檔案")
    actual_learning_root, current_learning_pin = _learning_paths(
        learning_output_root,
        data_root=layout.data_root_actual,
        qa_root=REPO_IGNORED_QA_ROOT,
        forbidden_paths=(
            ("run root", layout.run_root),
            ("fixed QA snapshot", REPOSITORY_ROOT / PINNED_SNAPSHOT_RELATIVE),
        ),
    )
    recorded_learning_pin = manifest.get("learning_root_read_only_pin")
    if not isinstance(recorded_learning_pin, dict):
        raise IsolationError("manifest 缺 learning root 唯讀 pin")
    if current_learning_pin != recorded_learning_pin:
        raise IsolationError("learning root 檔案樹與準備時的唯讀 pin 不同")

    source_payload = manifest.get("source_snapshot")
    if not isinstance(source_payload, dict):
        raise IsolationError("manifest 缺 snapshot custody")
    authority = _load_pinned_snapshot_authority(
        Path(str(source_payload.get("path", ""))),
        Path(str(source_payload.get("receipt_path", ""))),
    )
    if (
        source_payload.get("sha256") != authority.snapshot_sha256
        or source_payload.get("receipt_sha256") != authority.receipt_sha256
    ):
        raise IsolationError("manifest snapshot pin 與固定 authority 不符")
    config = TWStockConfig(
        data_root=layout.data_root_base,
        output_root=layout.output_root_base,
        profile="test",
    )
    _verify_test_profile_config(config, layout)
    if not layout.working_db_path.is_file():
        raise IsolationError("QA working DB 不存在")
    db_info = _assert_no_reparse_components(layout.working_db_path, allow_missing=False).stat()
    if not stat.S_ISREG(db_info.st_mode):
        raise IsolationError("QA working DB 必須是一般檔案")
    copy_hash, copy_size = _sha256_regular_file(
        layout.working_db_path,
        max_bytes=authority.snapshot_size_bytes,
    )
    if copy_hash != authority.snapshot_sha256 or copy_size != authority.snapshot_size_bytes:
        raise IsolationError("QA working DB 已偏離核准 snapshot bytes")
    if copy_hash != manifest.get("working_copy", {}).get("working_sha256"):
        raise IsolationError("QA working DB 與 prepare manifest 的 SHA 不符")
    actual_sqlite_scope = _sqlite_summary(layout.working_db_path)
    _validate_sqlite_summary(actual_sqlite_scope, authority)
    if actual_sqlite_scope != manifest.get("working_sqlite_scope"):
        raise IsolationError("QA working DB 結構與 prepare manifest 不符")
    return layout, manifest, {
        "authority": authority,
        "learning_root": actual_learning_root,
        "learning_pin": current_learning_pin,
        "working_sqlite_scope": actual_sqlite_scope,
    }


def _configure_isolated_environment(layout: RuntimeLayout, learning_output_root: Path) -> None:
    os.environ["DATA_ROOT"] = str(layout.data_root_base.resolve())
    os.environ["OUTPUT_ROOT"] = str(layout.output_root_base.resolve())
    os.environ["PROFILE"] = "test"
    os.environ["RECOMMENDATION_LEARNING_OUTPUT_ROOT"] = str(
        learning_output_root.resolve(strict=True)
    )
    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["QT_QPA_PLATFORM"] = "windows"
    for key in _ISOLATED_ARTIFACT_ENV:
        os.environ.pop(key, None)
    for key in tuple(os.environ):
        if key.startswith(("FORMAL_DAILY_", "PIT_SECTOR_", "PIT_MEMBERSHIP_")):
            os.environ.pop(key, None)
    os.environ["FORMAL_DAILY_RUNTIME_ENVIRONMENT_FILE"] = str(
        layout.run_root / ".missing-formal-runtime-binding.json"
    )


def _launch_learning_pin_summary(
    learning_root_pin: Mapping[str, Any],
    post_ui_tree_pin: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """從外層 learning-root pin 取出內層 tree pin，建立啟動摘要欄位。"""

    before_tree_pin = learning_root_pin.get("tree_pin")
    if not isinstance(before_tree_pin, dict):
        raise IsolationError("learning root pin 缺少 tree_pin")
    before_hash = before_tree_pin.get("tree_sha256")
    if not isinstance(before_hash, str) or len(before_hash) != 64:
        raise IsolationError("learning root tree pin 缺少有效 SHA-256")
    summary: dict[str, Any] = {
        "learning_root_tree_sha256_before_ui": before_hash,
    }
    if post_ui_tree_pin is not None:
        after_hash = post_ui_tree_pin.get("tree_sha256")
        if not isinstance(after_hash, str) or len(after_hash) != 64:
            raise IsolationError("UI 關閉後 learning root tree pin 缺少有效 SHA-256")
        summary.update(
            {
                "learning_root_tree_sha256_after_ui": after_hash,
                "learning_root_unchanged": post_ui_tree_pin == before_tree_pin,
            }
        )
    return summary


def launch_prepared_workspace(
    *,
    run_root: Path,
    policy_config_path: Path,
    learning_output_root: Path,
) -> int:
    """驗證固定複本後，才建立並顯示真正的 MainWindow。"""

    if os.name != "nt":
        raise IsolationError("可見 UI 啟動僅支援 Windows 桌面環境")
    layout, manifest, verified = _verify_prepared_workspace(
        run_root=run_root,
        policy_config_path=policy_config_path,
        learning_output_root=learning_output_root,
    )
    _configure_isolated_environment(layout, learning_output_root)
    config = TWStockConfig()
    _verify_test_profile_config(config, layout)

    from PySide6.QtWidgets import QApplication

    from ui_qt.main import MainWindow, _drain_qt_deferred_deletes, apply_app_theme

    app = QApplication([sys.argv[0]])
    app.setOrganizationName("TechnicalAnalysis")
    app.setApplicationName("TechnicalAnalysis")
    apply_app_theme(app)
    window = MainWindow(policy_config_path=policy_config_path)
    window.setWindowTitle("個人研究 QA｜隔離資料工作區")
    window.show()
    print("已顯示隔離個人研究視窗；資料只來自固定 QA snapshot 的獨立複本。")
    print(f"working DB: {layout.working_db_path}")
    print(f"policy: {policy_config_path}")
    launch_pin_summary = _launch_learning_pin_summary(verified["learning_pin"])
    print(
        "learning root read-only pin: "
        f"{launch_pin_summary['learning_root_tree_sha256_before_ui']}"
    )
    exit_code = int(app.exec())
    _drain_qt_deferred_deletes(app, (window,))

    post_learning_pin = _directory_tree_pin(verified["learning_root"])
    launch_pin_summary = _launch_learning_pin_summary(
        verified["learning_pin"], post_learning_pin
    )
    receipt = {
        "schema_version": "personal-research-ui-launch-receipt.v1",
        "run_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8],
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "process_id": os.getpid(),
        "run_root": str(layout.run_root.resolve()),
        "profile": "test",
        "working_db_path": str(layout.working_db_path.resolve()),
        "working_db_sha256_before_ui": manifest["working_copy"]["working_sha256"],
        "policy_config_path": str(policy_config_path.resolve(strict=False)),
        **launch_pin_summary,
        "mainwindow_title": "個人研究 QA｜隔離資料工作區",
        "native_window_launched_by_explicit_launch_command": True,
        "formal_data_written_by_launcher": False,
        "http_requested_by_launcher": False,
        "training_or_promotion_started_by_launcher": False,
        "scheduler_registered_by_launcher": False,
        "app_exec_return_code": exit_code,
    }
    receipt_dir = layout.receipts_dir
    receipt_path = receipt_dir / f"visible_mainwindow_{receipt['run_id']}.json"
    _write_json_create_only(receipt_path, receipt)
    print(f"launch receipt: {receipt_path}")
    if not receipt["learning_root_unchanged"]:
        print("錯誤：UI 執行期間 learning root 內容改變，請檢查 receipt。", file=sys.stderr)
        return 2
    return exit_code


def _configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="backslashreplace")
            except (OSError, ValueError):
                continue


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="以固定 QA SQLite snapshot 複本準備或啟動隔離的個人研究 UI。"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser(
        "prepare",
        help="只複製並驗證資料，不建立 QApplication 或顯示視窗",
        description="建立全新 QA run root；此命令不會啟動 UI。",
    )
    prepare.add_argument("--run-root", required=True, type=Path)
    prepare.add_argument("--source-snapshot", required=True, type=Path)
    prepare.add_argument("--snapshot-receipt", required=True, type=Path)
    prepare.add_argument("--learning-output-root", required=True, type=Path)
    prepare.add_argument("--policy-config-path", required=True, type=Path)

    launch = commands.add_parser(
        "launch",
        help="重新驗證已準備的隔離工作區後，明確顯示真正 MainWindow",
        description="只讀驗證 prepare receipt，再由操作者明確啟動可見 UI。",
    )
    launch.add_argument("--run-root", required=True, type=Path)
    launch.add_argument("--learning-output-root", required=True, type=Path)
    launch.add_argument("--policy-config-path", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_console()
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "prepare":
            authority = _verify_source_snapshot_cli_inputs(
                args.source_snapshot,
                args.snapshot_receipt,
            )
            manifest_path, manifest = prepare_isolated_workspace(
                run_root=args.run_root,
                policy_config_path=args.policy_config_path,
                learning_output_root=args.learning_output_root,
                authority=authority,
            )
            print(
                json.dumps(
                    {
                        "mode": "prepare_only_no_window",
                        "manifest_path": str(manifest_path),
                        "manifest_sha256": manifest["manifest_sha256"],
                        "working_db_path": manifest["working_db_path"],
                        "working_db_sha256": manifest["working_copy"]["working_sha256"],
                        "working_db_size_bytes": manifest["working_copy"]["working_size_bytes"],
                        "table_count": manifest["working_sqlite_scope"]["table_count"],
                        "learning_root_tree_sha256": manifest[
                            "learning_root_read_only_pin"
                        ]["tree_pin"]["tree_sha256"],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        return launch_prepared_workspace(
            run_root=args.run_root,
            policy_config_path=args.policy_config_path,
            learning_output_root=args.learning_output_root,
        )
    except (IsolationError, OSError, ValueError, sqlite3.Error) as exc:
        print(f"隔離個人研究 UI launcher 停止：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
