"""從唯讀來源建立 WP5 隔離 QA SQLite seed；不執行任何 pipeline child。"""

from __future__ import annotations

import argparse
from contextlib import closing
from dataclasses import fields
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
import time
from typing import Any, Callable
from uuid import uuid4
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
QA_PARENT = REPO_ROOT / "output" / "qa"
TAIPEI = ZoneInfo("Asia/Taipei")
SAMPLE_WINDOW_BYTES = 1024 * 1024
BACKUP_PAGES_PER_STEP = 8192
BACKUP_RETRY_SLEEP_SECONDS = 0.05
BACKUP_MAX_DURATION_SECONDS = 300.0
BACKUP_MAX_STALL_SECONDS = 45.0
SNAPSHOT_RELATIVE_PATH = Path(
    "output/qa/personal_daily_product_20261006/real_source_validation_runs/"
    "formal_source_snapshot_v2/twstock.db"
)
SNAPSHOT_SHA256 = "c99c497657ca4ef63c73e56151d135996e3f2144ec45f8bf4b053eecf8dc5d08"
SNAPSHOT_RECEIPT_SHA256 = "15e1f66f496865f55f97e6e76d1bb291cb1cb842d42d29ee42b7e8905f5b0e83"
SNAPSHOT_SCHEMA_SHA256 = "dc5a37f20103d1e14d9bc97914bb8680c40901a0cdad014ea985b1d82e98690f"
SNAPSHOT_SIZE_BYTES = 3_827_728_384
SNAPSHOT_SCHEMA_OBJECT_COUNT = 48
SNAPSHOT_TABLE_COUNT = 23
SNAPSHOT_PAGE_COUNT = 934_504
SNAPSHOT_PAGE_SIZE = 4096
SNAPSHOT_RECEIPT_MAX_BYTES = 2 * 1024 * 1024
SNAPSHOT_COPY_CHUNK_BYTES = 8 * 1024 * 1024
SNAPSHOT_RESEARCH_AS_OF = date(2026, 9, 28)
SNAPSHOT_SCHEMA_VERSION = "formal-sqlite-source-snapshot.v1"
REQUIRED_DATE_TABLES = (
    "daily_prices",
    "technical_indicators",
    "market_indices",
    "industry_indices",
)
DATE_COLUMN_NAMES = ("日期", "date", "trade_date", "交易日期", "date_str")
SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")
REPARSE_POINT_ATTRIBUTE = 0x400
PIT_ENV_NAMES = (
    "PIT_SECTOR_MEMBERSHIP_PATH",
    "PIT_SECTOR_MEMBERSHIP_RAW_ROOT",
    "PIT_SECTOR_MEMBERSHIP_CLOCK_MANIFEST_PATH",
    "PIT_SECTOR_MEMBERSHIP_UNIVERSE_SYMBOLS_PATH",
    "PIT_SECTOR_MEMBERSHIP_UNIVERSE_IDENTITY_PATH",
    "PIT_SECTOR_MEMBERSHIP_TAXONOMY_IDENTITY_PATH",
)


class BootstrapError(RuntimeError):
    """Bootstrap 前置、來源穩定性或副本驗證失敗。"""


class _BackupProgressError(BootstrapError):
    def __init__(self, message: str, progress: dict[str, Any]) -> None:
        super().__init__(message)
        self.progress = progress


class _BackupProgressGuard:
    """以淨完成頁數追蹤 backup；SQLite 重啟複製時不把回退算成進度。"""

    def __init__(
        self,
        *,
        pages_per_step: int | None = None,
        max_duration_seconds: float | None = None,
        max_stall_seconds: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._clock = clock
        self._pages_per_step = (
            BACKUP_PAGES_PER_STEP if pages_per_step is None else pages_per_step
        )
        self._started_at = clock()
        self._last_progress_at = self._started_at
        self._last_report_at = self._started_at
        self._max_duration_seconds = (
            BACKUP_MAX_DURATION_SECONDS
            if max_duration_seconds is None
            else max_duration_seconds
        )
        self._max_stall_seconds = (
            BACKUP_MAX_STALL_SECONDS
            if max_stall_seconds is None
            else max_stall_seconds
        )
        self._best_completed_pages = 0
        self._callback_count = 0
        self._last_status: int | None = None
        self._last_remaining_pages: int | None = None
        self._last_total_pages: int | None = None
        self._remaining_increase_count = 0
        self._total_change_count = 0
        self._restart_count = 0
        self._status_counts: dict[str, int] = {}

    def __call__(self, status: int, remaining: int, total: int) -> None:
        now = self._clock()
        self._callback_count += 1
        status = int(status)
        remaining = int(remaining)
        total = int(total)
        status_name = {
            sqlite3.SQLITE_OK: "ok",
            sqlite3.SQLITE_DONE: "done",
            sqlite3.SQLITE_BUSY: "busy",
            sqlite3.SQLITE_LOCKED: "locked",
        }.get(status, str(status))
        self._status_counts[status_name] = self._status_counts.get(status_name, 0) + 1
        if (
            self._last_remaining_pages is not None
            and remaining > self._last_remaining_pages
        ):
            self._remaining_increase_count += 1
            self._restart_count += 1
        if self._last_total_pages is not None and total != self._last_total_pages:
            self._total_change_count += 1
        self._last_status = int(status)
        self._last_remaining_pages = remaining
        self._last_total_pages = total
        completed_pages = max(0, total - remaining)
        if completed_pages > self._best_completed_pages:
            self._best_completed_pages = completed_pages
            self._last_progress_at = now

        elapsed = now - self._started_at
        if now - self._last_report_at >= 15.0:
            print(
                "[sqlite-backup] "
                f"completed={completed_pages}/{total} "
                f"best={self._best_completed_pages} remaining={remaining} "
                f"elapsed={elapsed:.0f}s callbacks={self._callback_count} "
                f"restarts={self._restart_count} status={status_name}",
                file=sys.stderr,
                flush=True,
            )
            self._last_report_at = now
        if elapsed >= self._max_duration_seconds:
            raise _BackupProgressError(
                "SQLite online backup 超過總時間上限 "
                f"({self._max_duration_seconds:.0f}s)；"
                f"completed_pages={self._best_completed_pages}, remaining={remaining}",
                self.summary(),
            )
        if (
            status != sqlite3.SQLITE_DONE
            and now - self._last_progress_at >= self._max_stall_seconds
        ):
            raise _BackupProgressError(
                "SQLite online backup 達停滯上限，淨完成頁數未增加；"
                f"stall={self._max_stall_seconds:.0f}s, "
                f"completed_pages={self._best_completed_pages}, "
                f"remaining={remaining}, total={total}。來源可能持續被寫入或鎖定",
                self.summary(),
            )

    def summary(self) -> dict[str, Any]:
        return {
            "pages_per_step": self._pages_per_step,
            "retry_sleep_seconds": BACKUP_RETRY_SLEEP_SECONDS,
            "stall_timeout_seconds": self._max_stall_seconds,
            "max_duration_seconds": self._max_duration_seconds,
            "timeout_enforcement": (
                "callback-only between sqlite backup steps; this is not a hard wall-clock "
                "kill, and one blocked step can exceed the limits; use an external "
                "supervisor for a hard process timeout"
            ),
            "elapsed_seconds": round(self._clock() - self._started_at, 3),
            "progress_callback_count": self._callback_count,
            "last_status": self._last_status,
            "status_counts": dict(self._status_counts),
            "last_remaining_pages": self._last_remaining_pages,
            "last_total_pages": self._last_total_pages,
            "highest_completed_pages": self._best_completed_pages,
            "remaining_increase_count": self._remaining_increase_count,
            "total_change_count": self._total_change_count,
            "restart_count": self._restart_count,
            "restart_count_method": (
                "count of callbacks where remaining pages increased from the prior callback; "
                "this is an observed rewind, not proof of its cause"
            ),
        }


def _run_online_backup(
    source_connection: sqlite3.Connection,
    destination_connection: sqlite3.Connection,
) -> dict[str, Any]:
    pages_per_step = BACKUP_PAGES_PER_STEP
    guard = _BackupProgressGuard(pages_per_step=pages_per_step)
    source_connection.backup(
        destination_connection,
        pages=pages_per_step,
        progress=guard,
        sleep=BACKUP_RETRY_SLEEP_SECONDS,
    )
    progress = guard.summary()
    if progress["progress_callback_count"] == 0 or progress["last_remaining_pages"] != 0:
        raise BootstrapError(
            "SQLite online backup 未回報完成進度；拒絕建立成功 receipt"
        )
    return progress


def _configured_data_root() -> Path:
    """讀取 TWStockConfig.data_root 的 default factory，不建立任何目錄。"""

    # 避免建立 TWStockConfig instance；其 __post_init__ 會建立資料目錄與 log。
    from data_module.config import TWStockConfig

    field = next(item for item in fields(TWStockConfig) if item.name == "data_root")
    if not callable(field.default_factory):
        raise BootstrapError("TWStockConfig.data_root 沒有可用 default factory")
    return Path(field.default_factory()).expanduser()


def _is_reparse_point(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    attributes = int(getattr(metadata, "st_file_attributes", 0))
    return stat.S_ISLNK(metadata.st_mode) or bool(
        attributes & REPARSE_POINT_ATTRIBUTE
    )


def _assert_no_reparse_chain(path: Path) -> None:
    cursor = Path(os.path.abspath(path))
    chain: list[Path] = []
    while True:
        chain.append(cursor)
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    for component in reversed(chain):
        if _is_reparse_point(component):
            raise BootstrapError(f"目的路徑含 symlink/junction：{component}")


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _assert_target_path_in_qa(target_root: Path, path: Path) -> None:
    """重查目的路徑仍在新 QA root 內，並且沒有 symlink/junction。"""

    target_root = Path(os.path.abspath(target_root))
    path = Path(os.path.abspath(path))
    _assert_no_reparse_chain(QA_PARENT)
    _assert_no_reparse_chain(target_root)
    _assert_no_reparse_chain(path.parent)
    qa_parent = QA_PARENT.resolve(strict=True)
    resolved_root = target_root.resolve(strict=True)
    if path == target_root:
        if resolved_root.parent != qa_parent:
            raise BootstrapError("目的 root 已離開 output/qa 的直接子目錄")
        return
    resolved_parent = path.parent.resolve(strict=True)
    if resolved_root.parent != qa_parent:
        raise BootstrapError("目的 root 已離開 output/qa 的直接子目錄")
    if resolved_parent != resolved_root and not _is_within(resolved_parent, resolved_root):
        raise BootstrapError("目的檔案父目錄已逸出新 QA root")
    if os.path.lexists(path):
        _assert_no_reparse_chain(path)
        resolved_path = path.resolve(strict=True)
        if not _is_within(resolved_path, resolved_root):
            raise BootstrapError("目的檔案實際路徑已逸出新 QA root")


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _date_text(value: object) -> str | None:
    if value is None:
        return None
    raw = str(value)
    try:
        if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
            return date.fromisoformat(raw).isoformat()
        if len(raw) == 8 and raw.isascii() and raw.isdigit():
            return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8])).isoformat()
    except ValueError:
        return None
    return None


def _file_observation(path: Path) -> dict[str, Any]:
    """小檔完整雜湊；大檔只雜湊首尾各 1 MiB，從不稱為全檔 hash。"""

    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return {"path": str(path), "exists": False}
    if _is_reparse_point(path) or not stat.S_ISREG(metadata.st_mode):
        raise BootstrapError(f"SQLite 檔或 sidecar 不是一般檔案：{path}")

    size = metadata.st_size
    full_hash = size <= SAMPLE_WINDOW_BYTES * 2
    digest = hashlib.sha256()
    if not full_hash:
        digest.update(b"bounded-file-sha256-v1\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\0")
    with path.open("rb") as stream:
        head = stream.read(min(size, SAMPLE_WINDOW_BYTES))
        tail_size = max(0, min(SAMPLE_WINDOW_BYTES, size - len(head)))
        if tail_size:
            stream.seek(max(0, size - tail_size))
            tail = stream.read(tail_size)
        else:
            tail = b""
    if full_hash:
        digest.update(head)
        digest.update(tail)
    else:
        digest.update(b"head\0")
        digest.update(head)
        digest.update(b"tail\0")
        digest.update(tail)
    after = path.lstat()
    if (metadata.st_size, metadata.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise BootstrapError(f"SQLite 檔或 sidecar 在指紋讀取期間改變：{path}")
    return {
        "path": str(path),
        "exists": True,
        "size_bytes": size,
        "mtime_utc": datetime.fromtimestamp(
            metadata.st_mtime_ns / 1_000_000_000, timezone.utc
        ).isoformat(),
        "mtime_ns": metadata.st_mtime_ns,
        "hash_method": "sha256_full_file" if full_hash else "sha256_bounded_head_tail_v1",
        "hash_is_full_file": full_hash,
        "hash_bytes_read": len(head) + len(tail),
        "sha256": digest.hexdigest(),
    }


def _source_observations(source_db: Path) -> dict[str, dict[str, Any]]:
    return {
        "database": _file_observation(source_db),
        **{
            suffix[1:]: _file_observation(Path(str(source_db) + suffix))
            for suffix in SIDECAR_SUFFIXES
        },
    }


def _source_data_signatures_match(
    before: dict[str, dict[str, Any]], after: dict[str, dict[str, Any]]
) -> bool:
    return all(
        before[name].get("exists") == after[name].get("exists")
        and (
            not before[name].get("exists")
            or (
                before[name].get("size_bytes") == after[name].get("size_bytes")
                and before[name].get("mtime_ns") == after[name].get("mtime_ns")
                and before[name].get("sha256") == after[name].get("sha256")
            )
        )
        for name in ("database", "wal", "journal")
    )


def _observation_changed(
    before: dict[str, Any], after: dict[str, Any]
) -> bool:
    return any(
        before.get(key) != after.get(key)
        for key in ("exists", "size_bytes", "mtime_ns", "sha256")
    )


def _connect_read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    if int(connection.execute("PRAGMA query_only").fetchone()[0]) != 1:
        connection.close()
        raise BootstrapError("SQLite source 未進入 query_only")
    return connection


def _inspect_database(path: Path, *, as_of_date: date) -> dict[str, Any]:
    with closing(_connect_read_only(path)) as connection:
        checks = [str(row[0]).lower() for row in connection.execute("PRAGMA quick_check")]
        if checks != ["ok"]:
            raise BootstrapError(f"目的 SQLite quick_check 失敗：{checks[:8]}")
        schema_rows = [
            [str(row[0]), str(row[1]), str(row[2]), row[3]]
            for row in connection.execute(
                "SELECT type, name, tbl_name, sql FROM sqlite_master "
                "WHERE type IN ('table','index','view','trigger') "
                "ORDER BY type, name"
            )
        ]
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        date_ranges: dict[str, dict[str, Any]] = {}
        for table in REQUIRED_DATE_TABLES:
            if table not in tables:
                raise BootstrapError(f"目的 SQLite 缺少必要資料表：{table}")
            columns = {
                str(row[1]).casefold(): str(row[1])
                for row in connection.execute(
                    f"PRAGMA table_info({_quote_identifier(table)})"
                )
            }
            date_column = next(
                (columns[name.casefold()] for name in DATE_COLUMN_NAMES if name.casefold() in columns),
                None,
            )
            if date_column is None:
                raise BootstrapError(f"資料表缺少可辨識日期欄位：{table}")
            raw_dates = list(
                connection.execute(
                    "SELECT DISTINCT " + _quote_identifier(date_column) +
                    " FROM " + _quote_identifier(table)
                )
            )
            if not raw_dates:
                raise BootstrapError(f"必要資料表沒有日期資料列：{table}")
            parsed_dates: list[date] = []
            for (raw_date,) in raw_dates:
                normalized = _date_text(raw_date)
                if normalized is None:
                    if raw_date is None:
                        raise BootstrapError(
                            f"日期欄位包含 NULL：{table}.{date_column}"
                        )
                    raise BootstrapError(
                        f"日期欄位無法解析：{table}.{date_column}={raw_date!r}"
                    )
                parsed_dates.append(date.fromisoformat(normalized))
            minimum_date = min(parsed_dates)
            maximum_date = max(parsed_dates)
            if maximum_date > as_of_date:
                raise BootstrapError(
                    f"未來資料超過 bootstrap 基準日："
                    f"{table}={maximum_date.isoformat()} > {as_of_date}"
                )
            date_ranges[table] = {
                "date_column": date_column,
                "min_date": minimum_date.isoformat(),
                "max_date": maximum_date.isoformat(),
            }
    schema_bytes = json.dumps(
        schema_rows, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return {
        "quick_check": "ok",
        "schema_sha256": hashlib.sha256(schema_bytes).hexdigest(),
        "schema_object_count": len(schema_rows),
        "tables": sorted(tables),
        "date_ranges": date_ranges,
    }


def _inspect_snapshot_database(path: Path, *, as_of_date: date) -> dict[str, Any]:
    """alternate mode 專用的 verifier 相容 schema/count 摘要。"""

    summary = _inspect_database(path, as_of_date=as_of_date)
    with closing(_connect_read_only(path)) as connection:
        for table in REQUIRED_DATE_TABLES:
            columns = {
                str(row[1]).casefold(): str(row[1])
                for row in connection.execute(
                    f"PRAGMA table_info({_quote_identifier(table)})"
                )
            }
            candidate_columns: list[str] = []
            for name in DATE_COLUMN_NAMES:
                actual = columns.get(name.casefold())
                if actual is not None and actual not in candidate_columns:
                    candidate_columns.append(actual)
            selected_column = summary["date_ranges"][table]["date_column"]
            summary["date_ranges"][table]["candidate_date_columns"] = candidate_columns
            summary["date_ranges"][table]["unscanned_date_columns"] = [
                name for name in candidate_columns if name != selected_column
            ]
        rows = connection.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()
        tables = [str(row[1]) for row in rows if row[0] == "table"]
        table_row_counts: dict[str, int] = {}
        for table in tables:
            table_row_counts[table] = int(
                connection.execute(
                    "SELECT COUNT(*) FROM " + _quote_identifier(table)
                ).fetchone()[0]
            )
        page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
        page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
        journal_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0])
    schema_bytes = json.dumps(
        rows, ensure_ascii=False, separators=(",", ":"), default=str
    ).encode("utf-8")
    return {
        **summary,
        "schema_sha256": hashlib.sha256(schema_bytes).hexdigest(),
        "schema_object_count": len(rows),
        "tables": sorted(tables),
        "table_count": len(tables),
        "table_row_counts": table_row_counts,
        "page_count": page_count,
        "page_size": page_size,
        "journal_mode": journal_mode,
    }


def _write_create_only(path: Path, payload: dict[str, Any]) -> None:
    encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    created = False
    try:
        with path.open("xb") as stream:
            created = True
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        if created:
            try:
                path.unlink()
            except OSError:
                pass
        raise


def _full_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(SNAPSHOT_COPY_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot_file_identity(path: Path) -> dict[str, Any]:
    metadata = path.lstat()
    if _is_reparse_point(path) or not stat.S_ISREG(metadata.st_mode):
        raise BootstrapError(f"固定 snapshot 必須是一般檔案：{path}")
    return {
        "size_bytes": metadata.st_size,
        "mtime_ns": metadata.st_mtime_ns,
        "device": getattr(metadata, "st_dev", None),
        "inode": getattr(metadata, "st_ino", None),
    }


def _read_bounded_receipt(path: Path) -> bytes:
    metadata = path.lstat()
    if _is_reparse_point(path) or not stat.S_ISREG(metadata.st_mode):
        raise BootstrapError("snapshot receipt 必須是一般檔案")
    if metadata.st_size > SNAPSHOT_RECEIPT_MAX_BYTES:
        raise BootstrapError("snapshot receipt 超過允許大小")
    with path.open("rb") as stream:
        payload = stream.read(SNAPSHOT_RECEIPT_MAX_BYTES + 1)
    if len(payload) > SNAPSHOT_RECEIPT_MAX_BYTES:
        raise BootstrapError("snapshot receipt 超過允許大小")
    return payload


def _aware_receipt_timestamp(value: object, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise BootstrapError(f"snapshot receipt 缺少有效時間：{field_name}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BootstrapError(f"snapshot receipt 時間格式錯誤：{field_name}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise BootstrapError(f"snapshot receipt 時間必須含時區：{field_name}")
    return parsed.astimezone(timezone.utc)


def _validate_pinned_qa_snapshot(
    snapshot_db: Path, snapshot_receipt: Path
) -> tuple[Path, Path, dict[str, Any], str]:
    """只接受固定 repo QA snapshot/receipt；不存取 receipt 記載的正式來源路徑。"""

    repo_root = Path(REPO_ROOT).resolve(strict=True)
    _assert_no_reparse_chain(repo_root)
    expected_snapshot = repo_root / SNAPSHOT_RELATIVE_PATH
    expected_receipt = expected_snapshot.parent / "snapshot_receipt.json"
    supplied_snapshot = Path(os.path.abspath(snapshot_db))
    supplied_receipt = Path(os.path.abspath(snapshot_receipt))
    _assert_no_reparse_chain(supplied_snapshot)
    _assert_no_reparse_chain(supplied_receipt)
    try:
        snapshot = supplied_snapshot.resolve(strict=True)
        receipt = supplied_receipt.resolve(strict=True)
        expected_snapshot = expected_snapshot.resolve(strict=True)
        expected_receipt = expected_receipt.resolve(strict=True)
        allowed_qa = (repo_root / "output" / "qa").resolve(strict=True)
    except OSError as exc:
        raise BootstrapError("固定 QA snapshot 路徑不存在或無法解析") from exc
    if snapshot != expected_snapshot or receipt != expected_receipt:
        raise BootstrapError("alternate mode 只接受 repo output/qa 內固定的 snapshot 與 sibling receipt")
    if not _is_within(snapshot, allowed_qa) or not _is_within(receipt, allowed_qa):
        raise BootstrapError("snapshot 與 receipt 必須位於 repo output/qa")
    snapshot_identity = _snapshot_file_identity(snapshot)
    if snapshot_identity["size_bytes"] != SNAPSHOT_SIZE_BYTES:
        raise BootstrapError("固定 QA snapshot 大小與核准 pin 不符")
    for suffix in SIDECAR_SUFFIXES:
        sidecar = Path(str(snapshot) + suffix)
        if os.path.lexists(sidecar):
            _assert_no_reparse_chain(sidecar)
            raise BootstrapError(f"固定 QA snapshot 出現未核准 SQLite sidecar：{suffix}")

    receipt_bytes = _read_bounded_receipt(receipt)
    receipt_sha256 = hashlib.sha256(receipt_bytes).hexdigest()
    if receipt_sha256 != SNAPSHOT_RECEIPT_SHA256:
        raise BootstrapError("固定 QA snapshot receipt SHA 與核准 pin 不符")
    try:
        payload = json.loads(receipt_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BootstrapError("固定 QA snapshot receipt 不是有效 UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise BootstrapError("固定 QA snapshot receipt 必須是 JSON object")
    schema = payload.get("snapshot_schema")
    if not isinstance(schema, dict):
        raise BootstrapError("固定 QA snapshot receipt 缺少 snapshot_schema")
    raw_snapshot_path = payload.get("snapshot_path")
    if not isinstance(raw_snapshot_path, str):
        raise BootstrapError("固定 QA snapshot receipt 缺少 snapshot_path")
    if Path(os.path.abspath(raw_snapshot_path)) != snapshot:
        raise BootstrapError("固定 QA snapshot receipt 指向不同資料庫")

    started_at = _aware_receipt_timestamp(payload.get("started_at"), "started_at")
    completed_at = _aware_receipt_timestamp(payload.get("completed_at"), "completed_at")
    if completed_at < started_at or completed_at.astimezone(TAIPEI).date() > SNAPSHOT_RESEARCH_AS_OF:
        raise BootstrapError("snapshot receipt 時間超出 2026-09-28 研究日期範圍")
    checks = payload.get("snapshot_data_version_checks")
    if (
        payload.get("status") != "complete"
        or payload.get("schema_version") != SNAPSHOT_SCHEMA_VERSION
        or payload.get("method") != "sqlite3.Connection.backup from mode=ro source with query_only=ON"
        or payload.get("snapshot_scope") != "repo-ignored QA only; no formal-data writes"
        or payload.get("snapshot_sha256") != SNAPSHOT_SHA256
        or payload.get("snapshot_integrity_check") != ["ok"]
        or payload.get("snapshot_data_version_stable") is not True
        or not isinstance(checks, list)
        or not checks
        or any(type(value) is not int for value in checks)
        or len(set(checks)) != 1
        or payload.get("snapshot_journal_mode") != "delete"
        or schema.get("schema_sha256") != SNAPSHOT_SCHEMA_SHA256
        or type(schema.get("logical_size_bytes")) is not int
        or schema.get("logical_size_bytes") != SNAPSHOT_SIZE_BYTES
        or type(schema.get("schema_object_count")) is not int
        or schema.get("schema_object_count") != SNAPSHOT_SCHEMA_OBJECT_COUNT
        or type(schema.get("table_count")) is not int
        or schema.get("table_count") != SNAPSHOT_TABLE_COUNT
        or type(schema.get("page_count")) is not int
        or schema.get("page_count") != SNAPSHOT_PAGE_COUNT
        or type(schema.get("page_size")) is not int
        or schema.get("page_size") != SNAPSHOT_PAGE_SIZE
    ):
        raise BootstrapError("固定 QA snapshot receipt 內容不符合核准 lineage pin")

    raw_counts = schema.get("table_row_counts")
    if (
        not isinstance(raw_counts, dict)
        or len(raw_counts) != SNAPSHOT_TABLE_COUNT
        or type(schema.get("table_count")) is not int
        or schema["table_count"] != len(raw_counts)
        or any(
            not isinstance(name, str) or type(count) is not int or count < 0
            for name, count in raw_counts.items()
        )
    ):
        raise BootstrapError("固定 QA snapshot receipt 的 table row counts 無效")
    if payload.get("source_unchanged") is not True:
        raise BootstrapError("上游 receipt 未確認正式來源前後穩定")
    source_before = payload.get("source_before")
    source_after = payload.get("source_after")
    source_path = payload.get("source_path")
    if (
        not isinstance(source_before, dict)
        or not isinstance(source_after, dict)
        or source_before != source_after
        or not isinstance(source_path, str)
        or payload.get("source_confirmation") != source_path
        or payload.get("source_schema") != schema
    ):
        raise BootstrapError("上游 receipt 的正式來源前後觀測或 schema 不一致")
    for name, suffix in (("main", ""), ("wal", "-wal"), ("shm", "-shm")):
        entry = source_before.get(name)
        if (
            not isinstance(entry, dict)
            or entry.get("path") != source_path + suffix
            or entry.get("exists") is not True
            or entry.get("is_regular_file") is not True
            or entry.get("is_reparse_point") is not False
            or entry.get("is_symlink") is not False
            or type(entry.get("size_bytes")) is not int
            or entry.get("size_bytes") < 0
            or not isinstance(entry.get("sha256"), str)
            or len(entry["sha256"]) != 64
        ):
            raise BootstrapError(f"上游 receipt 的正式來源觀測欄位無效：{name}")
    if source_before["main"]["size_bytes"] != SNAPSHOT_SIZE_BYTES:
        raise BootstrapError("上游 receipt 的正式來源 main size 與 snapshot 不符")
    return snapshot, receipt, payload, receipt_sha256


def _copy_pinned_snapshot_create_only(
    source: Path, destination: Path, *, target_root: Path
) -> dict[str, Any]:
    _assert_no_reparse_chain(source)
    expected_source = (Path(REPO_ROOT) / SNAPSHOT_RELATIVE_PATH).resolve(strict=True)
    allowed_qa = (Path(REPO_ROOT) / "output" / "qa").resolve(strict=True)
    if source.resolve(strict=True) != expected_source or not _is_within(source, allowed_qa):
        raise BootstrapError("固定 QA snapshot 路徑在 copy 前已改變")
    before = _snapshot_file_identity(source)
    if before["size_bytes"] != SNAPSHOT_SIZE_BYTES:
        raise BootstrapError("snapshot 複製前大小改變")
    source_digest = hashlib.sha256()
    copied_bytes = 0
    with source.open("rb") as input_stream:
        _assert_target_path_in_qa(target_root, destination)
        with destination.open("xb") as output_stream:
            while chunk := input_stream.read(SNAPSHOT_COPY_CHUNK_BYTES):
                source_digest.update(chunk)
                output_stream.write(chunk)
                copied_bytes += len(chunk)
            output_stream.flush()
            os.fsync(output_stream.fileno())
    _assert_no_reparse_chain(source)
    _assert_target_path_in_qa(target_root, destination)
    if source.resolve(strict=True) != expected_source or not _is_within(source, allowed_qa):
        raise BootstrapError("固定 QA snapshot 路徑在 copy 期間已改變")
    source_sha256 = source_digest.hexdigest()
    after = _snapshot_file_identity(source)
    if before != after:
        raise BootstrapError("固定 QA snapshot 複製期間的 size/mtime/file identity 改變")
    if copied_bytes != SNAPSHOT_SIZE_BYTES or source_sha256 != SNAPSHOT_SHA256:
        raise BootstrapError("固定 QA snapshot 全檔 SHA/size 與核准 pin 不符")
    destination_sha256 = _full_file_sha256(destination)
    if destination_sha256 != SNAPSHOT_SHA256:
        raise BootstrapError("QA working copy 全檔 SHA 與固定 snapshot 不符")
    return {
        "source_before": before,
        "source_after": after,
        "source_sha256_during_copy": source_sha256,
        "destination_sha256_readback": destination_sha256,
        "size_bytes": copied_bytes,
        "hash_method": "sha256_full_file",
        "hash_is_full_file": True,
        "destination_readback_hash_bytes": copied_bytes,
    }


def bootstrap_isolated_root(
    source_data_root: Path,
    qa_root: Path,
    *,
    as_of_date: date | None = None,
) -> dict[str, Any]:
    """只建立新 QA root 與 SQLite working copy；不執行 updater 或 learning child。"""

    source_root = Path(source_data_root).expanduser().resolve(strict=True)
    if not source_root.is_dir():
        raise BootstrapError(f"來源 data root 不是目錄：{source_root}")
    source_db = source_root / "sqlite" / "twstock.db"
    source_info = source_db.lstat()
    if _is_reparse_point(source_db) or not stat.S_ISREG(source_info.st_mode):
        raise BootstrapError(f"來源 SQLite 必須是一般檔案：{source_db}")

    target_root = Path(os.path.abspath(qa_root))
    target_parent = target_root.parent
    if not target_parent.is_dir():
        raise BootstrapError(f"QA parent 必須先存在：{target_parent}")
    _assert_no_reparse_chain(target_parent)
    try:
        allowed_parent = QA_PARENT.resolve(strict=True)
        resolved_target_parent = target_parent.resolve(strict=True)
    except OSError as exc:
        raise BootstrapError("無法解析 QA 輸出目錄") from exc
    if resolved_target_parent != allowed_parent:
        raise BootstrapError(f"目的只能是 output/qa 下的新 run root：{allowed_parent}")
    if target_root.name in {"", ".", ".."} or target_root.parent != target_parent:
        raise BootstrapError("QA root 必須是 QA parent 的單一新子目錄")
    resolved_parent = target_parent.resolve(strict=True)
    target_root = resolved_parent / target_root.name
    if os.path.lexists(target_root):
        raise BootstrapError(f"QA root 已存在，拒絕覆寫：{target_root}")
    if _is_within(target_root, source_root) or _is_within(source_root, target_root):
        raise BootstrapError("QA root 與來源 data root 重疊")

    before = _source_observations(source_db)
    if before["journal"].get("exists"):
        raise BootstrapError("來源有 rollback journal；唯讀 bootstrap fail closed")
    reference_date = as_of_date or datetime.now(TAIPEI).date()

    root_created = False
    try:
        target_root.mkdir()
        root_created = True
        _assert_no_reparse_chain(target_root)
        data_root = target_root / "data"
        output_root = target_root / "output"
        sqlite_dir = data_root / "sqlite"
        technical_output_root = data_root / "output"
        for directory in (data_root, output_root, sqlite_dir, technical_output_root):
            directory.mkdir()

        destination_db = sqlite_dir / "twstock.db"
        with closing(_connect_read_only(source_db)) as source_connection:
            destination_connection = sqlite3.connect(destination_db)
            try:
                backup_progress = _run_online_backup(
                    source_connection, destination_connection
                )
                destination_connection.commit()
            finally:
                destination_connection.close()

        after = _source_observations(source_db)
        if not _source_data_signatures_match(before, after):
            raise BootstrapError("來源 DB/WAL 在 online backup 期間改變；請於來源穩定後重跑")
        shm_changed = _observation_changed(before["shm"], after["shm"])
        destination_database = _inspect_database(destination_db, as_of_date=reference_date)
        destination_file = _file_observation(destination_db)

        receipt_path = target_root / "bootstrap_receipt.json"
        writes = [
            {"path": ".", "kind": "created_directory"},
            *[
                {"path": path.relative_to(target_root).as_posix(), "kind": "created_directory"}
                for path in (data_root, output_root, sqlite_dir, technical_output_root)
            ],
            {
                "path": destination_db.relative_to(target_root).as_posix(),
                "kind": "sqlite_online_backup",
                "size_bytes": destination_file["size_bytes"],
                "hash_method": destination_file["hash_method"],
                "sha256": destination_file["sha256"],
            },
            {"path": receipt_path.name, "kind": "create_only_success_receipt"},
        ]
        payload: dict[str, Any] = {
            "schema_version": "wp5-isolated-qa-sqlite-bootstrap.v1",
            "status": "database_seed_created",
            "bootstrap_scope": "sqlite_seed_only",
            "ready_for_daily_pipeline": False,
            "daily_chain_preflight_complete": False,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "as_of_date_guard": reference_date.isoformat(),
            "paths": {
                "qa_root": str(target_root),
                "data_root": str(data_root),
                "output_root": str(output_root),
                "technical_output_root": str(technical_output_root),
                "source_db": str(source_db),
                "working_db": str(destination_db),
                "receipt": str(receipt_path),
            },
            "source": {
                "before": before,
                "after": after,
                "database_wal_and_journal_observed_fingerprints_stable": True,
                "source_fingerprint_comparison": {
                    "compared_artifacts": ["database", "wal", "journal"],
                    "compared_fields": ["exists", "size_bytes", "mtime_ns", "sha256"],
                    "hash_scope": (
                        "Each file observation records its hash_method and hash_bytes_read: "
                        "full SHA-256 for files up to 2 MiB; otherwise a domain-separated "
                        "SHA-256 over the first and last 1 MiB plus file size. Bounded "
                        "hashes do not establish that unobserved middle bytes were unchanged."
                    ),
                },
                "shm_changed_during_backup": shm_changed,
                "shm_change_classification": (
                    "possible_transient_sqlite_read_lock_metadata"
                    if shm_changed
                    else "unchanged"
                ),
                "sqlite_open_mode": "mode=ro",
                "query_only": True,
                "backup_api": "sqlite3.Connection.backup",
            },
            "external_environment_presence": {
                "PHASE3C_CANDIDATE_DB_PATH": {
                    "process_value_present": bool(os.environ.get("PHASE3C_CANDIDATE_DB_PATH")),
                    "path_value_recorded": False,
                    "persisted_user_value_checked": False,
                },
                "PIT_SECTOR_MEMBERSHIP_*": {
                    name: bool(os.environ.get(name)) for name in PIT_ENV_NAMES
                },
                "PROFILE": {
                    "process_value": os.environ.get("PROFILE"),
                    "test_suffix_may_change_configured_paths": os.environ.get("PROFILE") == "test",
                },
            },
            "destination": {
                "backup_progress": backup_progress,
                **destination_file,
                **destination_database,
            },
            "lookahead_self_check": {
                "status": "passed",
                "scope": "data copy and date-boundary check only; no features, labels, or model calculations",
                "all_required_table_max_dates_at_or_before_as_of_date": True,
            },
            "not_bootstrapped": [
                {
                    "input": "meta_data/monthly_revenue_availability.csv",
                    "reason": "PIT recommendation sidecar; not copied or scanned",
                },
                {
                    "input": "meta_data/fundamental_statement_availability.csv",
                    "reason": "configured sidecar; not copied or scanned",
                },
                {
                    "input": "PIT_SECTOR_MEMBERSHIP_* environment paths",
                    "reason": "external optional PIT sidecars; not copied or redirected",
                },
                {
                    "input": "PHASE3C_CANDIDATE_DB_PATH",
                    "reason": "external writable candidate DB; operator must unset or redirect inside this QA root before quick update",
                },
                {
                    "input": "official calendar cache under repository output/",
                    "reason": "separate repo source; not copied or freshness-validated by this bootstrap",
                },
            ],
            "operator_preflight_required": [
                "Run the SQLite seed during a confirmed source-writer-idle window; concurrent writes can restart the online backup.",
                "Review or unset/redirect PIT_SECTOR_MEMBERSHIP_* paths before recommendation snapshot.",
                "Unset PHASE3C_CANDIDATE_DB_PATH or point it to a QA-owned candidate DB before quick update.",
                "Decide whether required PIT availability CSVs and a fresh official calendar cache must be copied or separately validated.",
                "Run the actual daily pipeline and BankTaiwan wrapper after completing same-day calendar/source checks and external path preflight.",
            ],
            "writes": writes,
        }
        _write_create_only(receipt_path, payload)
        return payload
    except Exception as exc:
        if root_created:
            failure_path = target_root / "bootstrap_failed.json"
            try:
                failure_payload: dict[str, Any] = {
                    "schema_version": "wp5-isolated-qa-sqlite-bootstrap-failure.v1",
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:1000],
                    "success_receipt_created": False,
                }
                if isinstance(exc, _BackupProgressError):
                    failure_payload["backup_progress"] = exc.progress
                _write_create_only(
                    failure_path,
                    failure_payload,
                )
            except OSError:
                pass
        raise


def bootstrap_from_verified_qa_snapshot(
    snapshot_db: Path,
    snapshot_receipt: Path,
    qa_root: Path,
) -> dict[str, Any]:
    """以固定 repo QA snapshot 建立研究限定副本；完全不開啟正式來源路徑。"""

    target_root = Path(os.path.abspath(qa_root))
    target_parent = target_root.parent
    if not target_parent.is_dir():
        raise BootstrapError(f"QA parent 必須先存在：{target_parent}")
    _assert_no_reparse_chain(target_parent)
    try:
        allowed_parent = QA_PARENT.resolve(strict=True)
        resolved_target_parent = target_parent.resolve(strict=True)
    except OSError as exc:
        raise BootstrapError("無法解析 QA 輸出目錄") from exc
    if resolved_target_parent != allowed_parent:
        raise BootstrapError(f"目的只能是 output/qa 下的新 run root：{allowed_parent}")
    if target_root.name in {"", ".", ".."} or target_root.parent != target_parent:
        raise BootstrapError("QA root 必須是 QA parent 的單一新子目錄")
    target_root = resolved_target_parent / target_root.name
    if os.path.lexists(target_root):
        raise BootstrapError(f"QA root 已存在，拒絕覆寫：{target_root}")

    root_created = False
    try:
        target_root.mkdir()
        root_created = True
        _assert_target_path_in_qa(target_root, target_root)
        data_root = target_root / "data"
        output_root = target_root / "output"
        sqlite_dir = data_root / "sqlite"
        technical_output_root = data_root / "output"
        for directory in (data_root, output_root, sqlite_dir, technical_output_root):
            _assert_target_path_in_qa(target_root, directory)
            directory.mkdir()
            _assert_target_path_in_qa(target_root, directory)

        snapshot, upstream_receipt_path, upstream, upstream_receipt_sha256 = (
            _validate_pinned_qa_snapshot(snapshot_db, snapshot_receipt)
        )
        if _is_within(target_root, snapshot) or _is_within(snapshot, target_root):
            raise BootstrapError("QA working root 與固定 snapshot 路徑重疊")
        destination_db = sqlite_dir / "twstock.db"
        copy_observation = _copy_pinned_snapshot_create_only(
            snapshot, destination_db, target_root=target_root
        )
        _assert_target_path_in_qa(target_root, destination_db)
        destination_database = _inspect_snapshot_database(
            destination_db, as_of_date=SNAPSHOT_RESEARCH_AS_OF
        )
        _assert_target_path_in_qa(target_root, destination_db)
        upstream_schema = upstream["snapshot_schema"]
        if (
            destination_database["schema_sha256"] != SNAPSHOT_SCHEMA_SHA256
            or destination_database["schema_sha256"] != upstream_schema["schema_sha256"]
            or destination_database["schema_object_count"] != SNAPSHOT_SCHEMA_OBJECT_COUNT
            or destination_database["table_count"] != SNAPSHOT_TABLE_COUNT
            or destination_database["table_row_counts"] != upstream_schema["table_row_counts"]
            or destination_database["page_count"] != SNAPSHOT_PAGE_COUNT
            or destination_database["page_size"] != SNAPSHOT_PAGE_SIZE
        ):
            raise BootstrapError("QA working DB 的 schema/row counts 與固定 upstream receipt 不符")

        receipt_path = target_root / "bootstrap_receipt.json"
        created_at = datetime.now(timezone.utc).isoformat()
        writes = [
            {"path": ".", "kind": "created_directory"},
            *[
                {"path": path.relative_to(target_root).as_posix(), "kind": "created_directory"}
                for path in (data_root, output_root, sqlite_dir, technical_output_root)
            ],
            {
                "path": destination_db.relative_to(target_root).as_posix(),
                "kind": "create_only_full_sha256_snapshot_copy",
                **copy_observation,
            },
            {"path": receipt_path.name, "kind": "create_only_success_receipt"},
        ]
        payload: dict[str, Any] = {
            "schema_version": "wp5-isolated-qa-sqlite-bootstrap.v1",
            "status": "database_seed_created",
            "bootstrap_scope": "sqlite_seed_only_from_verified_qa_snapshot",
            "source_mode": "verified_qa_snapshot",
            "research_use_only": True,
            "official_point_in_time_eligibility": "not_established",
            "as_of_date_guard_for_reported_date_columns": SNAPSHOT_RESEARCH_AS_OF.isoformat(),
            "date_guard_scope": {
                "tables": list(REQUIRED_DATE_TABLES),
                "claim": (
                    "only each listed date_ranges entry's selected date_column max_date "
                    "was checked against 2026-09-28"
                ),
                "unscanned_date_candidate_columns": {
                    table: destination_database["date_ranges"][table][
                        "unscanned_date_columns"
                    ]
                    for table in REQUIRED_DATE_TABLES
                },
                "unscanned_candidate_columns_parsed_or_normalized": False,
                "other_tables_date_scanned": False,
            },
            "ready_for_daily_pipeline": False,
            "daily_chain_preflight_complete": False,
            "created_at_utc": created_at,
            "paths": {
                "qa_root": str(target_root),
                "data_root": str(data_root),
                "output_root": str(output_root),
                "technical_output_root": str(technical_output_root),
                "source_snapshot_db": str(snapshot),
                "source_snapshot_receipt": str(upstream_receipt_path),
                "working_db": str(destination_db),
                "receipt": str(receipt_path),
            },
            "lineage": {
                "upstream_receipt_schema_version": upstream["schema_version"],
                "upstream_receipt_sha256": upstream_receipt_sha256,
                "snapshot_sha256": SNAPSHOT_SHA256,
                "snapshot_size_bytes": SNAPSHOT_SIZE_BYTES,
                "snapshot_started_at": upstream["started_at"],
                "snapshot_completed_at": upstream["completed_at"],
                "snapshot_schema_sha256": SNAPSHOT_SCHEMA_SHA256,
                "snapshot_integrity_check": ["ok"],
                "upstream_formal_source_before_after_equal": True,
                "formal_source_path_access": {
                    "receipt_d_paths_directly_opened_or_statted": False,
                    "limitation": (
                        "path-based validation is not OS-handle-bound and does not "
                        "defend against malicious concurrent namespace swaps"
                    ),
                    "operating_assumption": "non-adversarial local QA workspace",
                },
                "source_snapshot_file_before_copy": copy_observation["source_before"],
                "source_snapshot_file_after_copy": copy_observation["source_after"],
                "copy_source_sha256": copy_observation["source_sha256_during_copy"],
                "working_copy_sha256": copy_observation["destination_sha256_readback"],
            },
            "source": {
                "mode": "verified_qa_snapshot",
                "filesystem_race_limitation": (
                    "reparse/containment checks are repeated around writes and inspection; "
                    "they are not bound to OS file handles and cannot fully prevent a malicious "
                    "concurrent junction swap; use only in a non-adversarial local QA workspace"
                ),
                "sqlite_open_mode": "snapshot copied as raw bytes; source SQLite connection not opened",
                "upstream_receipt_source_before_after_comparison": (
                    "validated equality of pinned receipt main/wal/shm metadata; "
                    "recorded formal paths were not accessed"
                ),
                "source_qa_snapshot_stability_check": (
                    "file size, mtime_ns, device, and inode compared before/after copy; "
                    "full streamed SHA-256 matched the pinned snapshot hash"
                ),
            },
            "destination": {
                "copy": copy_observation,
                **destination_database,
            },
            "lookahead_self_check": {
                "status": "partial",
                "scope": (
                    "only max_date values for the selected date_ranges.date_column entries "
                    "were checked; other candidate columns and other tables were not scanned "
                    "or normalized; no features, labels, or model calculations"
                ),
                "guarded_tables": list(REQUIRED_DATE_TABLES),
                "all_reported_date_range_max_dates_at_or_before_2026_09_28": True,
                "full_database_future_date_absence_established": False,
                "unscanned_date_candidate_columns": {
                    table: destination_database["date_ranges"][table][
                        "unscanned_date_columns"
                    ]
                    for table in REQUIRED_DATE_TABLES
                },
                "unscanned_candidate_columns_parsed_or_normalized": False,
                "other_tables_date_scanned": False,
            },
            "not_bootstrapped": [
                {"input": "meta_data/monthly_revenue_availability.csv", "reason": "PIT sidecar not copied or validated"},
                {"input": "meta_data/fundamental_statement_availability.csv", "reason": "PIT sidecar not copied or validated"},
                {"input": "PIT_SECTOR_MEMBERSHIP_*", "reason": "external PIT paths not copied or redirected"},
                {"input": "PHASE3C_CANDIDATE_DB_PATH", "reason": "external writable DB not copied or redirected"},
                {"input": "official calendar cache", "reason": "not copied or freshness-validated by this bootstrap"},
            ],
            "operator_preflight_required": [
                "完成當日 calendar/source checks 與外部路徑 preflight 後，才可另行執行日 pipeline。",
                "僅 date_ranges 所列 date_column 的 max_date 經檢查不晚於 2026-09-28；其他候選日期欄未掃描/未轉碼、其他表未掃日期，且此資料不是官方 PIT 認定。",
            ],
            "writes": writes,
        }
        _assert_target_path_in_qa(target_root, receipt_path)
        _write_create_only(receipt_path, payload)
        _assert_target_path_in_qa(target_root, receipt_path)
        return payload
    except Exception as exc:
        if root_created:
            failure_path = target_root / "bootstrap_failed.json"
            try:
                _assert_target_path_in_qa(target_root, failure_path)
                _write_create_only(
                    failure_path,
                    {
                        "schema_version": "wp5-isolated-qa-sqlite-bootstrap-failure.v1",
                        "status": "failed",
                        "source_mode": "verified_qa_snapshot",
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:1000],
                        "success_receipt_created": False,
                    },
                )
                _assert_target_path_in_qa(target_root, failure_path)
            except Exception:
                pass
        raise


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-mode",
        choices=("formal-data-root", "verified-qa-snapshot"),
        default="formal-data-root",
        help="正式來源唯讀 backup，或 repo 內固定 snapshot alternate mode",
    )
    parser.add_argument("--source-data-root", type=Path)
    parser.add_argument("--source-snapshot-db", type=Path)
    parser.add_argument("--snapshot-receipt", type=Path)
    parser.add_argument(
        "--qa-root-name",
        help="output/qa 下的新目錄名稱；預設產生唯一時間戳名稱",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if not QA_PARENT.is_dir():
        print(json.dumps({"status": "failed", "error": f"QA parent 不存在：{QA_PARENT}"}, ensure_ascii=False))
        return 2
    _assert_no_reparse_chain(QA_PARENT)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = args.qa_root_name or f"wp5_sqlite_seed_{stamp}_{uuid4().hex[:8]}"
    if Path(name).name != name or name in {"", ".", ".."}:
        print(json.dumps({"status": "failed", "error": "qa-root-name 必須是單一目錄名稱"}, ensure_ascii=False))
        return 2
    try:
        if args.source_mode == "formal-data-root":
            if args.source_snapshot_db is not None or args.snapshot_receipt is not None:
                raise BootstrapError("formal-data-root 不接受 snapshot alternate mode 參數")
            source_data_root = args.source_data_root or _configured_data_root()
            result = bootstrap_isolated_root(source_data_root, QA_PARENT / name)
        else:
            if args.source_data_root is not None:
                raise BootstrapError("verified-qa-snapshot 不接受 --source-data-root")
            if args.source_snapshot_db is None or args.snapshot_receipt is None:
                raise BootstrapError(
                    "verified-qa-snapshot 必須同時提供 --source-snapshot-db 與 --snapshot-receipt"
                )
            result = bootstrap_from_verified_qa_snapshot(
                args.source_snapshot_db,
                args.snapshot_receipt,
                QA_PARENT / name,
            )
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def _configure_cli_encoding() -> None:
    """讓繁體中文 CLI 訊息在 Windows 非 UTF-8 pipe 中不因 code page 中止。"""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace")


if __name__ == "__main__":
    _configure_cli_encoding()
    raise SystemExit(main())
