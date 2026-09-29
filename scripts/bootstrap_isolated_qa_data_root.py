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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-data-root", type=Path, default=_configured_data_root())
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
        result = bootstrap_isolated_root(args.source_data_root, QA_PARENT / name)
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
