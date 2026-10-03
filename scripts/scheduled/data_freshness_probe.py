"""唯讀資料新鮮度與完整性 probe。

這個 probe 是排程的觀測邊界，不會修資料、建立表或同步 SQLite。日資料的
expected period 必須先通過 ``OfficialTradingCalendar``；因此週末、國定休市日、
臨時休市或官方日曆服務不可用時，不會以工作日或 ``MAX(日期)`` 猜測市場狀態。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sqlite3
import stat
from datetime import date, datetime, time, timedelta
from pathlib import Path
import sys
from typing import Any, Iterable
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data_module.official_trading_calendar import (
    OfficialTradingCalendar,
    OfficialTradingCalendarError,
)
from data_module.phase3c_backfill_runner import configured_candidate_db_path
from data_module.p0_candidate_repository import validate_candidate_working_copy_path
from data_module.scheduled_research_acquisition_binding import verify_weekly_acquisition
from app_module.update_status_history import (
    MAX_STATUS_HISTORY_BYTES,
    UPDATE_STATUS_HISTORY_SCHEMA,
    build_update_status_history_record,
)
from scripts.scheduled.scheduled_clock import scheduled_now


PACIFIC = ZoneInfo("America/Los_Angeles")
TAIPEI = ZoneInfo("Asia/Taipei")
DAILY_DATA_CUTOFF_LOCAL = time(4, 30)
_DATE_RE = re.compile(r"(?<!\d)(\d{8})(?!\d)")
_ISO_DATE_RE = re.compile(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)")
MAX_QUICK_STATUS_BYTES = 2 * 1024 * 1024
MAX_QUICK_HISTORY_RECORD_BYTES = 512 * 1024
MAX_QUICK_HISTORY_RECORD_COUNT = 10_000
_QUICK_TERMINAL_STATUSES = {"passed", "passed_with_warnings", "failed"}


class _QuickReceiptReadError(ValueError):
    """A bounded Quick receipt read failed its local file contract."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate_json_key:{key}")
        value[key] = item
    return value


def _reject_non_finite_json_constant(value: str) -> None:
    raise ValueError(f"non_finite_json_constant:{value}")


def _strict_json_loads(raw: str | bytes) -> Any:
    """Parse bounded JSON while rejecting duplicate keys and nonstandard numbers."""

    return json.loads(
        raw,
        object_pairs_hook=_strict_json_object,
        parse_constant=_reject_non_finite_json_constant,
    )


def _path_key(path: Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _is_reparse_point(info: os.stat_result) -> bool:
    flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(getattr(info, "st_file_attributes", 0) & flag)


def _stat_identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        int(info.st_dev),
        int(info.st_ino),
        int(info.st_size),
        int(info.st_mtime_ns),
        int(info.st_ctime_ns),
    )


def _assert_quick_receipt_path_no_link(path: Path) -> Path:
    absolute = Path(os.path.abspath(os.fspath(path)))
    for candidate in reversed([*absolute.parents, absolute]):
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            raise
        except OSError as exc:
            raise _QuickReceiptReadError(
                f"receipt_path_unreadable:{type(exc).__name__}"
            ) from exc
        if stat.S_ISLNK(info.st_mode) or _is_reparse_point(info):
            raise _QuickReceiptReadError("receipt_path_contains_link")
        if candidate != absolute and not stat.S_ISDIR(info.st_mode):
            raise _QuickReceiptReadError("receipt_parent_not_directory")
    return absolute


def _read_bounded_regular_file(path: Path, *, max_bytes: int) -> bytes:
    """Read one stable regular-file snapshot without following path links."""

    absolute = _assert_quick_receipt_path_no_link(path)
    try:
        before = absolute.lstat()
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise _QuickReceiptReadError(
            f"receipt_file_unreadable:{type(exc).__name__}"
        ) from exc
    if stat.S_ISLNK(before.st_mode) or _is_reparse_point(before):
        raise _QuickReceiptReadError("receipt_file_is_link")
    if not stat.S_ISREG(before.st_mode) or int(before.st_nlink) != 1:
        raise _QuickReceiptReadError("receipt_file_not_regular_single_link")
    if int(before.st_size) > max_bytes:
        raise _QuickReceiptReadError("receipt_file_too_large")

    try:
        with absolute.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or _is_reparse_point(opened)
                or _stat_identity(before) != _stat_identity(opened)
            ):
                raise _QuickReceiptReadError("receipt_file_identity_changed")
            if int(opened.st_nlink) != 1:
                raise _QuickReceiptReadError("receipt_file_not_regular_single_link")
            raw = handle.read(max_bytes + 1)
            after = os.fstat(handle.fileno())
    except _QuickReceiptReadError:
        raise
    except OSError as exc:
        raise _QuickReceiptReadError(
            f"receipt_file_unreadable:{type(exc).__name__}"
        ) from exc

    if len(raw) > max_bytes or int(after.st_size) > max_bytes:
        raise _QuickReceiptReadError("receipt_file_too_large")
    if (
        _stat_identity(opened) != _stat_identity(after)
        or len(raw) != int(after.st_size)
    ):
        raise _QuickReceiptReadError("receipt_file_changed_during_read")
    return raw


def _unverified_quick_binding(
    *,
    status_path: Path,
    observed_at: datetime,
    reason: str,
    status_sha256: str | None = None,
    status_bytes: int | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = payload or {}
    return {
        "binding_status": "unverified",
        "binding_reason": reason,
        "binding_scope": "terminal_receipt_identity_only",
        "status_path": str(status_path),
        "status_sha256": status_sha256,
        "status_bytes": status_bytes,
        "observed_at": observed_at.isoformat(),
        "task": payload.get("task"),
        "status": payload.get("status"),
        "run_id": payload.get("run_id"),
        "started_at": payload.get("started_at"),
        "completed_at": payload.get("completed_at"),
        "checked_at": payload.get("checked_at"),
        "history_record_id": None,
        "history_record_sha256": None,
        "history_payload_sha256": None,
        "db_write_attribution": False,
        "historical_pit": False,
        "formal_credit": False,
    }


def _verify_quick_history_record(
    *,
    status_path: Path,
    payload: dict[str, Any],
    observed_at: datetime,
) -> dict[str, Any]:
    """Bind one Quick terminal payload to its canonical sibling history row."""

    history_path = status_path.parent / "history.jsonl"
    terminal_binding = _unverified_quick_binding(
        status_path=status_path,
        observed_at=observed_at,
        reason="quick_terminal_identity_missing",
        payload=payload,
    )
    task = payload.get("task")
    status = str(payload.get("status", "")).strip().lower()
    run_id = payload.get("run_id")
    started_at = payload.get("started_at")
    completed_at = payload.get("completed_at")
    history_pointer = payload.get("history")

    if task != "baldr-data-update-quick-daily":
        terminal_binding["binding_reason"] = "quick_task_identity_mismatch"
        return terminal_binding
    if status not in _QUICK_TERMINAL_STATUSES:
        terminal_binding["binding_reason"] = "quick_status_not_terminal"
        return terminal_binding
    if not isinstance(run_id, str) or not run_id.strip():
        terminal_binding["binding_reason"] = "quick_run_id_missing"
        return terminal_binding
    if (
        not isinstance(started_at, str)
        or _parse_timestamp(started_at) is None
        or not isinstance(completed_at, str)
        or _parse_timestamp(completed_at) is None
    ):
        terminal_binding["binding_reason"] = "quick_terminal_time_missing_or_invalid"
        return terminal_binding
    if not isinstance(history_pointer, dict):
        terminal_binding["binding_reason"] = "quick_history_pointer_missing"
        return terminal_binding
    record_id = history_pointer.get("record_id")
    pointer_path = history_pointer.get("path")
    if not isinstance(record_id, str) or not record_id.strip():
        terminal_binding["binding_reason"] = "quick_history_record_id_missing"
        return terminal_binding
    if not isinstance(pointer_path, str) or _path_key(Path(pointer_path)) != _path_key(history_path):
        terminal_binding["binding_reason"] = "quick_history_path_not_canonical"
        return terminal_binding

    try:
        history_raw = _read_bounded_regular_file(
            history_path,
            max_bytes=MAX_STATUS_HISTORY_BYTES,
        )
    except FileNotFoundError:
        terminal_binding["binding_reason"] = "quick_history_missing"
        return terminal_binding
    except _QuickReceiptReadError as exc:
        terminal_binding["binding_reason"] = exc.reason
        return terminal_binding

    stream = io.BytesIO(history_raw)
    record_count = 0
    matching_record_ids: list[tuple[dict[str, Any], bytes]] = []
    terminal_run_records = 0
    seen_record_ids: set[str] = set()
    try:
        while True:
            line = stream.readline(MAX_QUICK_HISTORY_RECORD_BYTES + 2)
            if not line:
                break
            if len(line) > MAX_QUICK_HISTORY_RECORD_BYTES + 1:
                terminal_binding["binding_reason"] = "quick_history_record_too_large"
                return terminal_binding
            if line.endswith(b"\n"):
                record_bytes = line[:-1]
                if record_bytes.endswith(b"\r"):
                    record_bytes = record_bytes[:-1]
            else:
                record_bytes = line
            if not record_bytes:
                continue
            record_count += 1
            if record_count > MAX_QUICK_HISTORY_RECORD_COUNT:
                terminal_binding["binding_reason"] = "quick_history_record_count_exceeded"
                return terminal_binding
            record = _strict_json_loads(record_bytes.decode("utf-8"))
            if not isinstance(record, dict):
                terminal_binding["binding_reason"] = "quick_history_record_not_object"
                return terminal_binding
            if record.get("schema_version") != UPDATE_STATUS_HISTORY_SCHEMA:
                terminal_binding["binding_reason"] = "quick_history_schema_mismatch"
                return terminal_binding
            row_id = record.get("record_id")
            row_run_id = record.get("run_id")
            if not isinstance(row_id, str) or not row_id:
                terminal_binding["binding_reason"] = "quick_history_identity_missing"
                return terminal_binding
            if row_id in seen_record_ids:
                terminal_binding["binding_reason"] = "quick_history_duplicate_record_id"
                return terminal_binding
            seen_record_ids.add(row_id)
            if row_run_id == run_id and str(record.get("status", "")).lower() in _QUICK_TERMINAL_STATUSES:
                terminal_run_records += 1
            if row_id == record_id:
                matching_record_ids.append((record, record_bytes))
    except (UnicodeDecodeError, ValueError, RecursionError):
        terminal_binding["binding_reason"] = "quick_history_record_invalid"
        return terminal_binding

    if terminal_run_records != 1:
        terminal_binding["binding_reason"] = "quick_history_terminal_run_not_unique"
        return terminal_binding
    if len(matching_record_ids) != 1:
        terminal_binding["binding_reason"] = "quick_history_record_id_not_unique"
        return terminal_binding
    history_record, history_record_bytes = matching_record_ids[0]
    payload_without_history = dict(payload)
    payload_without_history.pop("history", None)
    captured_at = history_record.get("captured_at")
    if not isinstance(captured_at, str) or _parse_timestamp(captured_at) is None:
        terminal_binding["binding_reason"] = "quick_history_capture_time_invalid"
        return terminal_binding
    try:
        expected_record = build_update_status_history_record(
            payload_without_history,
            captured_at=captured_at,
        )
    except (TypeError, ValueError):
        terminal_binding["binding_reason"] = "quick_history_payload_unserializable"
        return terminal_binding
    if expected_record != history_record:
        terminal_binding["binding_reason"] = "quick_history_payload_or_record_hash_mismatch"
        return terminal_binding
    if (
        history_record.get("run_id") != run_id
        or history_record.get("status") != status
        or history_record.get("started_at") != started_at
        or history_record.get("completed_at") != completed_at
    ):
        terminal_binding["binding_reason"] = "quick_history_terminal_identity_mismatch"
        return terminal_binding

    return {
        **terminal_binding,
        "binding_status": "verified",
        "binding_reason": "quick_terminal_receipt_and_append_record_match",
        "task": task,
        "status": status,
        "run_id": run_id,
        "started_at": started_at,
        "completed_at": completed_at,
        "checked_at": payload.get("checked_at"),
        "history_record_id": record_id,
        "history_record_sha256": hashlib.sha256(history_record_bytes).hexdigest(),
        "history_payload_sha256": history_record.get("payload_sha256"),
        "db_write_attribution": False,
        "historical_pit": False,
        "formal_credit": False,
    }


def _quick_status_snapshot(
    *,
    status_path: Path,
    canonical_status_path: Path,
    observed_at: datetime,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    try:
        raw = _read_bounded_regular_file(
            status_path,
            max_bytes=MAX_QUICK_STATUS_BYTES,
        )
    except FileNotFoundError:
        return None, _unverified_quick_binding(
            status_path=status_path,
            observed_at=observed_at,
            reason="quick_status_missing",
        )
    except _QuickReceiptReadError as exc:
        return None, _unverified_quick_binding(
            status_path=status_path,
            observed_at=observed_at,
            reason=exc.reason,
        )
    except OSError as exc:
        return None, _unverified_quick_binding(
            status_path=status_path,
            observed_at=observed_at,
            reason=f"quick_status_unreadable:{type(exc).__name__}",
        )

    status_sha256 = f"sha256:{hashlib.sha256(raw).hexdigest()}"
    try:
        parsed = _strict_json_loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None, _unverified_quick_binding(
            status_path=status_path,
            observed_at=observed_at,
            reason="quick_status_json_invalid",
            status_sha256=status_sha256,
            status_bytes=len(raw),
        )
    if not isinstance(parsed, dict):
        return None, _unverified_quick_binding(
            status_path=status_path,
            observed_at=observed_at,
            reason="quick_status_not_object",
            status_sha256=status_sha256,
            status_bytes=len(raw),
        )

    if _path_key(status_path) != _path_key(canonical_status_path):
        return parsed, _unverified_quick_binding(
            status_path=status_path,
            observed_at=observed_at,
            reason="quick_status_path_not_canonical",
            status_sha256=status_sha256,
            status_bytes=len(raw),
            payload=parsed,
        )
    binding = _verify_quick_history_record(
        status_path=status_path,
        payload=parsed,
        observed_at=observed_at,
    )
    binding["status_sha256"] = status_sha256
    binding["status_bytes"] = len(raw)
    return parsed, binding


def _parse_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=PACIFIC)
    return parsed


def _parse_date(value: object) -> date | None:
    timestamp = _parse_timestamp(value)
    if timestamp is not None:
        return timestamp.date()
    if value is None:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text[:10] if fmt == "%Y-%m-%d" else text[:8], fmt).date()
        except ValueError:
            continue
    return None


def _date_key(value: object) -> str | None:
    parsed = _parse_date(value)
    if parsed is not None:
        return parsed.strftime("%Y%m%d")
    if value is None:
        return None
    text = str(value).strip().replace("-", "")
    return text if len(text) == 8 and text.isdigit() else None


def _date_from_key(value: str) -> date:
    return datetime.strptime(value, "%Y%m%d").date()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {
        str(row[1])
        for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    }


def _latest_date(conn: sqlite3.Connection, table: str) -> str | None:
    columns = _table_columns(conn, table)
    date_column = next(
        (column for column in ("日期", "trade_date", "date", "decision_date") if column in columns),
        None,
    )
    if date_column is None:
        return None
    row = conn.execute(f'SELECT MAX("{date_column}") FROM "{table}"').fetchone()
    return _date_key(row[0]) if row and row[0] is not None else None


def _db_date_summary(
    conn: sqlite3.Connection,
    table: str,
    date_key: str,
) -> dict[str, Any]:
    columns = _table_columns(conn, table)
    if not columns:
        return {
            "table_exists": False,
            "date": date_key,
            "row_count": 0,
            "distinct_code_count": None,
            "duplicate_key_count": None,
        }
    date_column = next(
        (column for column in ("日期", "trade_date", "date", "decision_date") if column in columns),
        None,
    )
    code_column = next(
        (column for column in ("證券代號", "stock_code", "stock_id", "code") if column in columns),
        None,
    )
    if date_column is None:
        return {
            "table_exists": True,
            "date": date_key,
            "row_count": 0,
            "distinct_code_count": None,
            "duplicate_key_count": None,
        }
    if code_column is None:
        row = conn.execute(
            f'SELECT COUNT(*) FROM "{table}" WHERE "{date_column}"=?',
            (date_key,),
        ).fetchone()
        return {
            "table_exists": True,
            "date": date_key,
            "row_count": int(row[0] or 0),
            "distinct_code_count": None,
            "duplicate_key_count": None,
        }
    row = conn.execute(
        f'''SELECT COUNT(*), COUNT(DISTINCT "{code_column}")
            FROM "{table}" WHERE "{date_column}"=?''',
        (date_key,),
    ).fetchone()
    row_count = int(row[0] or 0)
    distinct_count = int(row[1] or 0)
    return {
        "table_exists": True,
        "date": date_key,
        "row_count": row_count,
        "distinct_code_count": distinct_count,
        "duplicate_key_count": max(row_count - distinct_count, 0),
    }


def _db_codes_for_date(
    conn: sqlite3.Connection,
    table: str,
    date_key: str,
) -> set[str]:
    columns = _table_columns(conn, table)
    date_column = next(
        (column for column in ("日期", "trade_date", "date", "decision_date") if column in columns),
        None,
    )
    code_column = next(
        (column for column in ("證券代號", "stock_code", "stock_id", "code") if column in columns),
        None,
    )
    if date_column is None or code_column is None:
        return set()
    return {
        str(row[0]).strip()
        for row in conn.execute(
            f'SELECT DISTINCT "{code_column}" FROM "{table}" WHERE "{date_column}"=?',
            (date_key,),
        ).fetchall()
        if row[0] is not None and str(row[0]).strip()
    }


def _db_date_keys(
    conn: sqlite3.Connection,
    table: str,
    expected_keys: Iterable[str],
) -> set[str]:
    columns = _table_columns(conn, table)
    date_column = next(
        (column for column in ("日期", "trade_date", "date", "decision_date") if column in columns),
        None,
    )
    keys = tuple(expected_keys)
    if date_column is None or not keys:
        return set()
    placeholders = ",".join("?" for _ in keys)
    result: set[str] = set()
    for row in conn.execute(
        f'SELECT DISTINCT "{date_column}" FROM "{table}" WHERE "{date_column}" IN ({placeholders})',
        keys,
    ).fetchall():
        key = _date_key(row[0])
        if key is not None:
            result.add(key)
    return result


def _read_csv_summary(
    path: Path,
    *,
    expected_date_key: str | None = None,
    code_columns: tuple[str, ...] = ("證券代號", "stock_code", "code", "證券代碼"),
    date_columns: tuple[str, ...] = ("日期", "date", "trade_date", "Date"),
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "path": str(path),
        "exists": path.is_file(),
        "row_count": 0,
        "distinct_code_count": 0,
        "duplicate_code_count": 0,
        "invalid_code_count": 0,
        "schema_missing": [],
        "date_values": [],
        "read_error": None,
    }
    if not path.is_file():
        return summary
    codes: set[str] = set()
    date_values: set[str] = set()
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = tuple(reader.fieldnames or ())
            code_column = next((column for column in code_columns if column in fields), None)
            date_column = next((column for column in date_columns if column in fields), None)
            summary["schema_missing"] = [
                column for column in ("證券代號", "收盤價") if column not in fields
            ]
            for row in reader:
                summary["row_count"] += 1
                if code_column is not None:
                    code = str(row.get(code_column, "") or "").strip()
                    if code:
                        if code in codes:
                            summary["duplicate_code_count"] += 1
                        codes.add(code)
                    else:
                        summary["invalid_code_count"] += 1
                if date_column is not None:
                    value = _date_key(row.get(date_column))
                    if value is not None:
                        date_values.add(value)
    except (OSError, UnicodeError, csv.Error) as exc:
        summary["read_error"] = f"{type(exc).__name__}:{exc}"
        return summary
    summary["distinct_code_count"] = len(codes)
    summary["date_values"] = sorted(date_values)
    # Kept private for the in-process raw↔SQLite reconciliation; never emit a
    # full symbol set in the status artifact.
    summary["_codes"] = codes
    summary["date_mismatch"] = bool(
        expected_date_key is not None
        and date_values
        and date_values != {expected_date_key}
    )
    summary["code_sample"] = sorted(codes)[:12]
    return summary


def _file_date_key(path: Path) -> str | None:
    match = _DATE_RE.search(path.stem)
    if match:
        return match.group(1)
    iso_match = _ISO_DATE_RE.search(path.stem)
    if iso_match:
        return iso_match.group(1).replace("-", "")
    return None


def _available_file_date_keys(root: Path, *, recursive: bool = False) -> set[str]:
    if not root.is_dir():
        return set()
    iterator = root.rglob("*.csv") if recursive else root.glob("*.csv")
    return {
        key
        for path in iterator
        for key in [_file_date_key(path)]
        if key is not None
    }


def _local_now(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=PACIFIC)
    return value.astimezone(PACIFIC)


def _expected_quick_update_date(
    today: date,
    *,
    calendar: OfficialTradingCalendar | None = None,
) -> date:
    """Compatibility helper backed by the shared official calendar."""

    resolver = calendar or OfficialTradingCalendar()
    records = resolver.get_recent_official_trading_days(
        today,
        1,
        include_reference=True,
        allow_online_probe=True,
    )
    return date.fromisoformat(str(records[-1]["date_str"]))


def _coverage_bp(covered: int, eligible: int) -> int | None:
    if eligible <= 0:
        return None
    return (covered * 10000) // eligible


def _roll_forward_weekend_filing_deadline(due_date: date) -> date:
    """Apply the general weekend extension; do not infer other holidays."""
    if due_date.weekday() == 5:
        return due_date + timedelta(days=2)
    if due_date.weekday() == 6:
        return due_date + timedelta(days=1)
    return due_date


def _expected_latest_monthly_period(reference_date: date) -> str:
    monthly_due_date = _roll_forward_weekend_filing_deadline(
        date(reference_date.year, reference_date.month, 10)
    )
    months_back = 1 if reference_date > monthly_due_date else 2
    month_index = reference_date.year * 12 + reference_date.month - 1 - months_back
    year, month_zero = divmod(month_index, 12)
    return f"{year:04d}-{month_zero + 1:02d}"


def _expected_latest_statement_period(reference_date: date) -> str:
    """Return the latest calendar-year reporting period past its filing window.

    Q1--Q3 are due within 45 days after quarter-end; the annual/Q4 statement is
    due within three months after year-end. A Saturday/Sunday deadline rolls to
    Monday under the general weekend rule. The adjusted due date remains
    inclusive, so a period becomes expected only on the following day. This is
    an aggregate freshness baseline, not evidence of a company's actual
    publication time; non-weekend holidays, issuer exceptions, and company
    coverage are not evaluated here.
    """
    eligible_periods: list[tuple[int, int]] = []
    for year in range(reference_date.year - 2, reference_date.year + 1):
        for quarter in range(1, 4):
            quarter_end_month = quarter * 3
            next_month = quarter_end_month + 1
            quarter_end = date(year, next_month, 1) - timedelta(days=1)
            due_date = _roll_forward_weekend_filing_deadline(
                quarter_end + timedelta(days=45)
            )
            if reference_date > due_date:
                eligible_periods.append((year, quarter))

        annual_due_date = _roll_forward_weekend_filing_deadline(
            date(year + 1, 3, 31)
        )
        if reference_date > annual_due_date:
            eligible_periods.append((year, 4))

    if not eligible_periods:
        return ""
    year, quarter = max(eligible_periods)
    return f"{year:04d}-Q{quarter}"


def _official_sessions_in_week(
    calendar: OfficialTradingCalendar,
    week_start: date,
    *,
    allow_online_probe: bool,
) -> tuple[list[date], list[str]]:
    records = calendar.get_trading_days_in_range(
        week_start,
        week_start + timedelta(days=4),
        allow_online_probe=allow_online_probe,
    )
    sessions: list[date] = []
    unresolved: list[str] = []
    for record in records:
        date_str = str(record.get("date_str") or "")
        if record.get("is_trading_day") is None:
            unresolved.append(date_str)
        elif record.get("is_trading_day") is True:
            try:
                sessions.append(date.fromisoformat(date_str))
            except ValueError:
                unresolved.append(date_str or "invalid_date")
    return sessions, unresolved


def _expected_tdcc_weekly_periods(
    reference_date: date,
    calendar: OfficialTradingCalendar | None,
    *,
    allow_online_probe: bool = True,
) -> tuple[str | None, str | None, date | None, str | None]:
    """Resolve last completed TDCC week, prior week, and a two-session grace.

    A week is complete once its last official session has passed. A missing
    snapshot can wait through the end of the second subsequent official
    session; older-than-one-week observations remain stale during that grace.
    """
    if calendar is None:
        return None, None, None, "official calendar was not supplied"
    if not callable(getattr(calendar, "get_trading_days_in_range", None)):
        return None, None, None, "official calendar cannot resolve weekly date ranges"

    current_week_start = reference_date - timedelta(days=reference_date.weekday())
    selected_week_offset: int | None = None
    expected_date: date | None = None
    for week_offset in range(9):
        week_start = current_week_start - timedelta(days=7 * week_offset)
        sessions, unresolved = _official_sessions_in_week(
            calendar,
            week_start,
            allow_online_probe=allow_online_probe,
        )
        if unresolved:
            return None, None, None, (
                "official weekly calendar unresolved: " + ", ".join(unresolved)
            )
        if not sessions:
            continue
        week_last_session = max(sessions)
        if week_offset == 0 and week_last_session > reference_date:
            continue
        expected_date = week_last_session
        selected_week_offset = week_offset
        break

    if expected_date is None or selected_week_offset is None:
        return None, None, None, "no completed official trading week was resolved"

    previous_period: str | None = None
    for week_offset in range(selected_week_offset + 1, selected_week_offset + 9):
        week_start = current_week_start - timedelta(days=7 * week_offset)
        sessions, unresolved = _official_sessions_in_week(
            calendar,
            week_start,
            allow_online_probe=allow_online_probe,
        )
        if unresolved:
            return None, None, None, (
                "previous official weekly calendar unresolved: "
                + ", ".join(unresolved)
            )
        if sessions:
            previous_period = max(sessions).strftime("%Y%m%d")
            break
    if previous_period is None:
        return None, None, None, "previous official trading week was not resolved"

    grace_records = calendar.get_trading_days_in_range(
        expected_date + timedelta(days=1),
        expected_date + timedelta(days=14),
        allow_online_probe=allow_online_probe,
    )
    grace_sessions: list[date] = []
    for record in grace_records:
        date_str = str(record.get("date_str") or "")
        if record.get("is_trading_day") is None:
            return None, None, None, f"official publication-window calendar unresolved: {date_str}"
        if record.get("is_trading_day") is True:
            try:
                grace_sessions.append(date.fromisoformat(date_str))
            except ValueError:
                return None, None, None, f"invalid official calendar date: {date_str}"
            if len(grace_sessions) == 2:
                break
    if len(grace_sessions) < 2:
        return None, None, None, "two-session TDCC publication window was not resolved"

    return (
        expected_date.strftime("%Y%m%d"),
        previous_period,
        grace_sessions[-1],
        None,
    )


def _tdcc_publication_window_open(
    run_now: datetime | None,
    reference_date: date,
    grace_through: date,
) -> bool:
    if run_now is None:
        as_of_date = reference_date
    elif run_now.tzinfo is None:
        as_of_date = run_now.date()
    else:
        as_of_date = run_now.astimezone(TAIPEI).date()
    return as_of_date <= grace_through


def _static_file_status(
    path: Path,
    *,
    source_id: str,
    authority: str,
    update_entry: str = "static inventory observation only",
    scheduled_task: str = "not scheduled for production ingestion",
    owner: str = "Data Engineering + source owner",
    downstream: list[str] | None = None,
    candidate_only: bool = False,
) -> dict[str, Any]:
    exists = path.is_file()
    observed_at = None
    size = None
    if exists:
        try:
            stat = path.stat()
            observed_at = datetime.fromtimestamp(stat.st_mtime, tz=PACIFIC).isoformat(timespec="seconds")
            size = int(stat.st_size)
        except OSError:
            observed_at = None
    return {
        "source_id": source_id,
        "authority": authority,
        "frequency": "static/event snapshot",
        "actual_period": None,
        "published_at": None,
        "available_at": None,
        "last_successful_check_at": observed_at,
        "time_provenance": "local_observation_only; upstream_publish_time_not_recorded",
        "coverage": {"file_exists": exists, "bytes": size},
        "missing_periods": [],
        "duplicate_key_count": None,
        "freshness_status": "not_applicable" if exists else "unknown",
        "reason": "static_file_present_without_upstream_validity_window" if exists else "file_missing",
        "update_entry": update_entry,
        "scheduled_task": scheduled_task,
        "owner": owner,
        "downstream": list(downstream or []),
        "candidate_only": candidate_only,
    }


def _default_calendar_cache_path() -> Path | None:
    """Use the existing immutable official-calendar cache when available."""

    path = REPO_ROOT / "output" / "paper_execution_eod_replay" / "calendar_cache"
    return path if path.is_dir() else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only baldr data freshness probe.")
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--status-path")
    parser.add_argument("--log-path")
    parser.add_argument("--quick-status-path")
    parser.add_argument("--weekly-parent-receipt-path", type=Path)
    parser.add_argument("--weekly-parent-receipt-sha256")
    parser.add_argument("--stale-days", type=int, default=7)
    parser.add_argument("--calendar-cache-path")
    parser.add_argument("--temporary-closure-path")
    parser.add_argument("--calendar-window-sessions", type=int, default=10)
    return parser


def _write_artifact(path: Path, text: str, *, label: str) -> str | None:
    """Best-effort write that keeps ACL failures visible as structured output."""

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        return f"{label}_artifact_write_failed:{type(exc).__name__}"
    return None


def _append_warning(warnings: list[str], value: str) -> None:
    if value not in warnings:
        warnings.append(value)


def _source_status(
    *,
    source_id: str,
    authority: str,
    frequency: str,
    actual_period: str | None,
    published_at: str | None,
    available_at: str | None,
    expected_period: str | None,
    coverage: dict[str, Any],
    missing_periods: list[str],
    duplicate_key_count: int | None,
    freshness_status: str,
    reason: str,
    update_entry: str,
    scheduled_task: str,
    owner: str,
    downstream: list[str],
    candidate_only: bool = False,
    time_provenance: str = "source_publish_or_fetch_receipt_not_recorded",
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "authority": authority,
        "frequency": frequency,
        "actual_period": actual_period,
        "published_at": published_at,
        "available_at": available_at,
        "time_provenance": time_provenance,
        "expected_period": expected_period,
        "coverage": coverage,
        "missing_periods": missing_periods,
        "duplicate_key_count": duplicate_key_count,
        "freshness_status": freshness_status,
        "reason": reason,
        "update_entry": update_entry,
        "scheduled_task": scheduled_task,
        "owner": owner,
        "downstream": downstream,
        "candidate_only": candidate_only,
    }


def _build_operational_source_statuses(
    *,
    conn: sqlite3.Connection,
    data_root: Path,
    expected_records: list[dict[str, Any]],
    quick_payload: dict[str, Any] | None,
    run_now: datetime,
    warnings: list[str],
    checks: dict[str, Any],
) -> list[dict[str, Any]]:
    expected_keys = [str(item["date_str"]).replace("-", "") for item in expected_records]
    expected_key = expected_keys[-1]
    expected_date = _date_from_key(expected_key)
    local_now = _local_now(run_now)
    after_cutoff = local_now.time() >= DAILY_DATA_CUTOFF_LOCAL
    twse_path = data_root / "daily_price" / f"{expected_key}.csv"
    tpex_path = data_root / "daily_price_tpex" / f"{expected_key}.csv"
    twse = _read_csv_summary(twse_path)
    tpex = _read_csv_summary(tpex_path, expected_date_key=expected_key)
    twse_dates = _available_file_date_keys(data_root / "daily_price")
    tpex_dates = _available_file_date_keys(data_root / "daily_price_tpex")
    twse_missing = sorted(set(expected_keys) - twse_dates)
    tpex_missing = sorted(set(expected_keys) - tpex_dates)

    quick_checked_at = None
    if quick_payload:
        quick_checked_at = _parse_timestamp(
            quick_payload.get("completed_at") or quick_payload.get("checked_at")
        )
    receipt_at = quick_checked_at.isoformat(timespec="seconds") if quick_checked_at else None
    source_statuses: list[dict[str, Any]] = []

    for source_id, authority, path, summary, missing in (
        ("twse.daily_prices.raw", "TWSE MI_INDEX / ALLBUT0999", twse_path, twse, twse_missing),
        ("tpex.daily_prices.raw", "TPEx OpenAPI daily close quotes", tpex_path, tpex, tpex_missing),
    ):
        status = "current"
        reason = "official source file matches expected official session"
        if not summary["exists"] or summary.get("read_error"):
            status = "expected_wait" if not after_cutoff else "stale"
            reason = "source file is not yet locally available" if not summary["read_error"] else "source file unreadable"
        elif summary.get("schema_missing"):
            status = "failed"
            reason = "source schema missing required fields"
        elif summary.get("date_mismatch") or summary.get("duplicate_code_count", 0) > 0:
            status = "partial"
            reason = "source file contains a date mismatch or duplicate code"
        elif missing:
            if expected_key in missing:
                status = "expected_wait" if not after_cutoff else "stale"
                reason = "target official session file is not yet locally available"
            else:
                status = "partial"
                reason = "older official session files are missing inside the bounded audit window"
        elif summary.get("row_count", 0) == 0:
            status = "failed"
            reason = "source file is present but contains no data rows"
        available_dates = (
            twse_dates
            if source_id == "twse.daily_prices.raw"
            else tpex_dates
        )
        actual_period = max(available_dates) if available_dates else None
        source_file_mtime = None
        if summary["exists"]:
            try:
                source_file_mtime = datetime.fromtimestamp(
                    path.stat().st_mtime,
                    tz=PACIFIC,
                ).isoformat(timespec="seconds")
            except OSError:
                source_file_mtime = None
        available_at = source_file_mtime or receipt_at
        source_statuses.append(
            _source_status(
                source_id=source_id,
                authority=authority,
                frequency="daily after official close/publication",
                actual_period=actual_period,
                published_at=None,
                available_at=available_at,
                expected_period=expected_key,
                coverage={
                    "row_count": int(summary.get("row_count", 0)),
                    "distinct_code_count": int(summary.get("distinct_code_count", 0)),
                    "duplicate_code_count": int(summary.get("duplicate_code_count", 0)),
                    "file_exists": bool(summary["exists"]),
                    "path": str(path),
                    "source_file_mtime": source_file_mtime,
                    "quick_update_receipt_at": receipt_at,
                },
                missing_periods=missing,
                duplicate_key_count=int(summary.get("duplicate_code_count", 0)),
                freshness_status=status,
                reason=reason,
                update_entry="UpdateService.update_daily / update_tpex_daily_price_range",
                scheduled_task="baldr-data-update-quick-daily",
                owner="Data Engineering",
                downstream=["sqlite.daily_prices", "technical_indicators", "paper/raw consumers"],
            )
        )

    daily_db = _db_date_summary(conn, "daily_prices", expected_key)
    daily_dates = _db_date_keys(conn, "daily_prices", expected_keys)
    daily_missing = sorted(set(expected_keys) - daily_dates)
    raw_rows = int(twse.get("row_count", 0)) + int(tpex.get("row_count", 0))
    raw_codes: set[str] = set()
    raw_codes.update(twse.get("_codes", set()))
    raw_codes.update(tpex.get("_codes", set()))
    db_codes = _db_codes_for_date(conn, "daily_prices", expected_key)
    both_raw_files_present = bool(twse.get("exists") and tpex.get("exists"))
    code_set_comparable = both_raw_files_present
    db_matches_raw = (
        raw_rows > 0
        and daily_db.get("row_count") == raw_rows
        and both_raw_files_present
        and (
            not code_set_comparable
            or (
                daily_db.get("distinct_code_count") == raw_rows
                and db_codes == raw_codes
            )
        )
    )
    if expected_key in daily_missing:
        daily_status = "expected_wait" if not after_cutoff else "stale"
        daily_reason = "target official session is not yet present in SQLite"
    elif daily_missing:
        daily_status = "partial"
        daily_reason = "SQLite daily_prices is missing older official sessions in the bounded audit window"
    elif db_matches_raw:
        daily_status = "current"
        daily_reason = "SQLite row count and code set match both official market files"
    else:
        daily_status = "partial" if raw_rows or daily_db.get("row_count") else "stale"
        daily_reason = "SQLite daily_prices does not reconcile to the bounded official raw files"
    if daily_status == "partial":
        _append_warning(warnings, "sqlite_daily_prices_raw_reconciliation_partial")
    source_statuses.append(
        _source_status(
            source_id="sqlite.daily_prices",
            authority="SQLite synchronized from TWSE + TPEx official raw files",
            frequency="daily synchronized read model",
            actual_period=_latest_date(conn, "daily_prices"),
            published_at=None,
            available_at=receipt_at,
            expected_period=expected_key,
            coverage={
                "db_row_count": int(daily_db.get("row_count", 0)),
                "db_distinct_code_count": daily_db.get("distinct_code_count"),
                "raw_row_count": raw_rows,
                "reconciles_to_raw": db_matches_raw,
                "observed_official_sessions": len(daily_dates),
                "expected_official_sessions": len(expected_keys),
            },
            missing_periods=daily_missing,
            duplicate_key_count=daily_db.get("duplicate_key_count"),
            freshness_status=daily_status,
            reason=daily_reason,
            update_entry="UpdateService.sync_source_to_sqlite('daily_price_files')",
            scheduled_task="baldr-data-update-quick-daily",
            owner="Data Engineering",
            downstream=["technical_indicators", "all SQLite-first market consumers"],
        )
    )

    for source_id, table, authority, downstream, update_entry in (
        (
            "sqlite.market_indices",
            "market_indices",
            "TWSE FMTQIK / market index CSV",
            ["market regime", "benchmark consumers"],
            "UpdateService.update_market + sync_source_to_sqlite('market_index')",
        ),
        (
            "sqlite.industry_indices",
            "industry_indices",
            "TWSE MI_INDEX industry index CSV",
            ["industry mapper", "sector rotation", "benchmark consumers"],
            "UpdateService.update_industry + sync_source_to_sqlite('industry_index')",
        ),
        (
            "sqlite.broker_flows",
            "broker_flows",
            "MoneyDJ branch daily pages / broker registry",
            ["broker flow repository", "research-only microstructure"],
            "UpdateService.update_broker_branch + sync_source_to_sqlite('broker_branch_files')",
        ),
    ):
        summary = _db_date_summary(conn, table, expected_key)
        dates = _db_date_keys(conn, table, expected_keys)
        status = "current" if summary.get("row_count", 0) > 0 else "stale"
        reason = "target official session has SQLite rows" if status == "current" else "target official session has no SQLite rows"
        missing = sorted(set(expected_keys) - dates)
        if expected_key in missing:
            status = "stale"
            reason = "target official session has no SQLite rows"
        elif missing:
            status = "partial"
            reason = "bounded official session window is incomplete"
        elif summary.get("duplicate_key_count", 0) and table != "broker_flows":
            status = "partial"
            reason = "target official session contains duplicate date/code keys"
        source_statuses.append(
            _source_status(
                source_id=source_id,
                authority=authority,
                frequency="daily official session",
                actual_period=_latest_date(conn, table),
                published_at=None,
                available_at=receipt_at,
                expected_period=expected_key,
                coverage={
                    "target_row_count": int(summary.get("row_count", 0)),
                    "target_distinct_code_count": summary.get("distinct_code_count"),
                    "observed_official_sessions": len(dates),
                    "expected_official_sessions": len(expected_keys),
                },
                missing_periods=missing,
                duplicate_key_count=summary.get("duplicate_key_count"),
                freshness_status=status,
                reason=reason,
                update_entry=update_entry,
                scheduled_task="baldr-data-update-quick-daily",
                owner="Data Engineering",
                downstream=downstream,
            )
        )

    technical = _db_date_summary(conn, "technical_indicators", expected_key)
    technical_dates = _db_date_keys(conn, "technical_indicators", expected_keys)
    technical_missing = sorted(set(expected_keys) - technical_dates)
    daily_latest = _latest_date(conn, "daily_prices")
    technical_latest = _latest_date(conn, "technical_indicators")
    eligible = 0
    covered = 0
    if _table_exists(conn, "daily_prices") and _table_exists(conn, "technical_indicators"):
        row = conn.execute(
            '''WITH latest AS (
                   SELECT MAX("日期") AS latest_date FROM daily_prices
               ), eligible AS (
                   SELECT "證券代號" AS stock_code
                   FROM daily_prices
                   GROUP BY "證券代號"
                   HAVING COUNT(*) >= 30
                      AND MAX("日期") = (SELECT latest_date FROM latest)
               ), covered AS (
                   SELECT DISTINCT "證券代號" AS stock_code
                   FROM technical_indicators
                   WHERE "日期" = (SELECT latest_date FROM latest)
               )
               SELECT (SELECT COUNT(*) FROM eligible),
                      (SELECT COUNT(*) FROM eligible e JOIN covered c ON c.stock_code=e.stock_code)'''
        ).fetchone()
        eligible = int(row[0] or 0)
        covered = int(row[1] or 0)
    technical_current = bool(
        daily_latest == expected_key
        and technical_latest == expected_key
        and daily_latest == technical_latest
        and not technical_missing
        and eligible > 0
        and covered >= eligible
    )
    technical_status = "current" if technical_current else "partial" if technical.get("row_count", 0) else "stale"
    if not technical_current:
        _append_warning(warnings, "technical_indicators_latest_coverage_partial")
    source_statuses.append(
        _source_status(
            source_id="sqlite.technical_indicators",
            authority="derived from SQLite daily_prices by UpdateService calculator",
            frequency="after each daily price update",
            actual_period=technical_latest,
            published_at=None,
            available_at=receipt_at,
            expected_period=expected_key,
            coverage={
                "target_row_count": int(technical.get("row_count", 0)),
                "eligible_stock_count": eligible,
                "covered_stock_count": covered,
                "coverage_bp": _coverage_bp(covered, eligible),
                "observed_official_sessions": len(technical_dates),
                "expected_official_sessions": len(expected_keys),
                "eligibility_excluded_count": max(
                    int(daily_db.get("distinct_code_count") or 0) - eligible,
                    0,
                ),
            },
            missing_periods=technical_missing,
            duplicate_key_count=technical.get("duplicate_key_count"),
            freshness_status=technical_status,
            reason=(
                "latest daily official session has full eligible technical coverage"
                if technical_current
                else "technical latest date or eligible-stock coverage is incomplete"
            ),
            update_entry="UpdateService.calculate_technical_indicators",
            scheduled_task="baldr-data-update-quick-daily",
            owner="Data Engineering",
            downstream=["recommendation", "decision desk", "research consumers"],
        )
    )

    revenue_latest = None
    revenue_available = None
    revenue_count = 0
    if _table_exists(conn, "fundamental_monthly_revenues"):
        row = conn.execute(
            'SELECT MAX("period"), MAX("available_date"), COUNT(*) FROM fundamental_monthly_revenues'
        ).fetchone()
        revenue_latest = str(row[0]) if row and row[0] is not None else None
        revenue_available = str(row[1]) if row and row[1] is not None else None
        revenue_count = int(row[2] or 0)
    revenue_expected = _expected_latest_monthly_period(expected_date)
    revenue_present = _table_exists(conn, "fundamental_monthly_revenues")
    revenue_status = (
        "current" if revenue_latest == revenue_expected else "stale"
        if revenue_present else "not_applicable"
    )
    if revenue_status == "stale":
        _append_warning(warnings, "monthly_revenue_expected_period_not_available")
    source_statuses.append(
        _source_status(
            source_id="fundamental.monthly_revenues",
            authority="TWSE / TPEx / MOPS announcement lanes recorded in availability map",
            frequency=(
                "monthly; general deadline is the 10th of the following month, "
                "rolled to Monday when it falls on a weekend"
            ),
            actual_period=revenue_latest,
            published_at=None,
            available_at=revenue_available,
            expected_period=revenue_expected,
            coverage={
                "db_row_count": revenue_count,
                "general_weekend_deadline_policy": "roll_saturday_sunday_to_monday",
                "non_weekend_holiday_adjustments_evaluated": False,
                "issuer_specific_deadline_exceptions_evaluated": False,
            },
            missing_periods=[revenue_expected] if revenue_status == "stale" else [],
            duplicate_key_count=None,
            freshness_status=revenue_status,
            reason=(
                "expected monthly period is present"
                if revenue_status == "current"
                else "candidate source table is not present in this database"
                if revenue_status == "not_applicable"
                else "expected monthly period is absent; source publication or candidate acceptance is required"
            ),
            update_entry="UpdateService.dry_run/apply MOPS monthly revenue backfill",
            scheduled_task="not in daily quick update; candidate route only",
            owner="Data Engineering + Fundamental Data owner",
            downstream=["fundamental snapshot", "valuation consumers"],
            candidate_only=True,
        )
    )

    statement_latest = None
    statement_available = None
    statement_count = 0
    if _table_exists(conn, "fundamental_statement_items"):
        row = conn.execute(
            'SELECT MAX("period"), MAX("available_date"), COUNT(*) FROM fundamental_statement_items'
        ).fetchone()
        statement_latest = str(row[0]) if row and row[0] is not None else None
        statement_available = str(row[1]) if row and row[1] is not None else None
        statement_count = int(row[2] or 0)
    statement_expected = _expected_latest_statement_period(expected_date)
    statement_present = _table_exists(conn, "fundamental_statement_items")
    statement_status = (
        "not_applicable"
        if not statement_present
        else "stale"
        if not statement_latest or statement_latest < statement_expected
        else "partial"
    )
    if statement_status == "stale":
        _append_warning(warnings, "quarterly_statement_expected_period_not_available")
    source_statuses.append(
        _source_status(
            source_id="fundamental.quarterly_statements",
            authority="MOPS financial statement publication/document lanes",
            frequency=(
                "calendar-year general baseline: Q1-Q3 due within 45 days and "
                "annual/Q4 within three months; weekend deadlines roll to Monday"
            ),
            actual_period=statement_latest,
            published_at=None,
            available_at=statement_available,
            expected_period=statement_expected,
            coverage={
                "db_row_count": statement_count,
                "period_scope_completeness_verified": False,
                "issuer_specific_deadline_exceptions_evaluated": False,
                "non_weekend_holiday_adjustments_evaluated": False,
                "general_weekend_deadline_policy": "roll_saturday_sunday_to_monday",
                "per_row_available_date_pit_qualification": False,
                "available_date_max_is_independent_of_latest_period": True,
            },
            missing_periods=[statement_expected] if statement_status == "stale" else [],
            duplicate_key_count=None,
            freshness_status=statement_status,
            reason=(
                "expected calendar-year due-window period is represented; issuer scope, "
                "per-row availability, and PIT qualification are unverified"
                if statement_status == "partial"
                else "candidate statement table is not present in this database"
                if statement_status == "not_applicable"
                else (
                    "aggregate statement period is below the calendar-year general "
                    "due-window "
                    "baseline; issuer exceptions and company coverage are unverified"
                )
            ),
            update_entry="candidate MOPS statement publication acquisition",
            scheduled_task="not in daily quick update; candidate route only",
            owner="Data Engineering + Fundamental Data owner",
            downstream=["fundamental snapshot", "PIT research only"],
            candidate_only=True,
        )
    )

    if _table_exists(conn, "fundamental_current_observations"):
        for kind, identifier, expected in (
            ("monthly_revenue", "fundamental.current_monthly_observations", revenue_expected),
            ("statement_item", "fundamental.current_statement_observations", statement_expected),
        ):
            grouped = conn.execute(
                "SELECT period, market, COUNT(DISTINCT stock_code), MAX(observed_at) "
                "FROM fundamental_current_observations WHERE kind=? AND julianday(observed_at)<=julianday(?) "
                "GROUP BY period, market ORDER BY period, market", (kind, run_now.isoformat()),
            ).fetchall()
            if not grouped:
                continue
            latest = max(str(row[0]) for row in grouped)
            source_statuses.append(_source_status(
                source_id=identifier, authority="official observed snapshot; no original announcement claim",
                frequency="monthly" if kind == "monthly_revenue" else "quarterly",
                actual_period=latest, published_at=None, available_at=max(str(row[3]) for row in grouped),
                expected_period=expected,
                coverage={"companies_by_period_market": {f"{r[0]}/{r[1]}": int(r[2]) for r in grouped}},
                missing_periods=[expected] if latest < expected else [], duplicate_key_count=0,
                freshness_status="partial" if latest >= expected else "stale",
                reason="current observations ingested; publication coverage is partial/unverified; historical PIT is separate",
                update_entry="official current snapshot fetch and backed-up incremental apply",
                scheduled_task="manual source refresh", owner="Data Engineering",
                downstream=["current stock research report"], candidate_only=False,
            ))

    checks["expected_official_session"] = expected_key
    checks["expected_official_session_window"] = expected_keys
    legacy_key = _date_key(checks.get("daily_prices_latest_date")) or expected_key
    legacy_twse_path = data_root / "daily_price" / f"{legacy_key}.csv"
    legacy_tpex_path = data_root / "daily_price_tpex" / f"{legacy_key}.csv"
    checks["twse_daily_price_file_exists_for_latest_date"] = legacy_twse_path.exists()
    checks["tpex_daily_price_file_exists_for_latest_date"] = legacy_tpex_path.exists()
    checks["twse_daily_price_file"] = str(legacy_twse_path)
    checks["tpex_daily_price_file"] = str(legacy_tpex_path)
    checks["daily_price_latest_date_key"] = legacy_key
    if not legacy_twse_path.exists():
        _append_warning(warnings, f"twse_daily_price_file_missing:{legacy_key}")
    if not legacy_tpex_path.exists():
        _append_warning(warnings, f"tpex_daily_price_file_missing:{legacy_key}")
    checks["technical_coverage"] = {
        "eligible_stock_count": eligible,
        "covered_stock_count": covered,
        "coverage_bp": _coverage_bp(covered, eligible),
    }
    return source_statuses


def _phase3c_candidate_statuses(
    *,
    candidate_db_path: Path | None,
    expected_session: str | None,
    calendar: OfficialTradingCalendar | None = None,
    reference_date: date | None = None,
    run_now: datetime | None = None,
    allow_online_probe: bool = True,
) -> list[dict[str, Any]]:
    table_specs = (
        (
            "institutional_flows",
            "TWSE + TPEx institutional official endpoints",
            (
                frozenset({"twse-official-T86"}),
                frozenset({"tpex-official-3itrade"}),
            ),
            "baldr-data-update-quick-daily",
        ),
        (
            "credit_transactions",
            "TWSE + TPEx margin official endpoints",
            (
                frozenset({"twse-official-MI_MARGN"}),
                frozenset(
                    {
                        "tpex-official-margin_bal",
                        "tpex-mainboard-margin-openapi.v1",
                    }
                ),
            ),
            "baldr-data-update-quick-daily",
        ),
        (
            "tdcc_shareholding",
            "TDCC public holdings lane",
            (
                frozenset(
                    {
                        "tdcc-official-od-1-5",
                        "tdcc-openapi-1-5.v1",
                    }
                ),
            ),
            "baldr-data-update-quick-daily (Monday latest snapshot only)",
        ),
    )
    statuses: list[dict[str, Any]] = []
    conn: sqlite3.Connection | None = None
    db_error: str | None = None
    if candidate_db_path is not None and candidate_db_path.is_file():
        try:
            uri = f"file:{candidate_db_path.resolve().as_posix()}?mode=ro"
            conn = sqlite3.connect(uri, uri=True)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
        except sqlite3.Error as exc:
            db_error = f"{type(exc).__name__}:{exc}"

    try:
        for source_id, authority, expected_version_groups, scheduled_task in table_specs:
            expected_versions = frozenset().union(*expected_version_groups)
            exists = conn is not None and _table_exists(conn, source_id)
            count = (
                int(conn.execute(f'SELECT COUNT(*) FROM "{source_id}"').fetchone()[0])
                if exists and conn is not None
                else 0
            )
            latest = _latest_date(conn, source_id) if exists and conn is not None else None
            current_row_count = 0
            observed_versions: list[str] = []
            duplicate_key_count: int | None = None
            latest_available_at: str | None = None
            if exists and conn is not None and latest is not None:
                current_row_count = int(
                    conn.execute(
                        f'SELECT COUNT(*) FROM "{source_id}" WHERE REPLACE("decision_date", "-", "")=?',
                        (latest,),
                    ).fetchone()[0]
                )
                observed_versions = sorted(
                    str(row[0])
                    for row in conn.execute(
                        f'SELECT DISTINCT "source_version" FROM "{source_id}" '
                        'WHERE REPLACE("decision_date", "-", "")=? ORDER BY "source_version"',
                        (latest,),
                    ).fetchall()
                    if row[0] is not None
                )
                duplicate_key_count = int(
                    conn.execute(
                        f'SELECT COUNT(*) FROM ('
                        f'SELECT "stock_code", "decision_date", COUNT(*) AS n FROM "{source_id}" '
                        'GROUP BY "stock_code", "decision_date" HAVING n > 1)'
                    ).fetchone()[0]
                )
                if "available_at" in _table_columns(conn, source_id):
                    row = conn.execute(
                        f'SELECT MAX("available_at") FROM "{source_id}" '
                        'WHERE REPLACE("decision_date", "-", "")=?',
                        (latest,),
                    ).fetchone()
                    latest_available_at = str(row[0]) if row and row[0] is not None else None

            version_coverage_complete = all(
                not group.isdisjoint(observed_versions)
                for group in expected_version_groups
            )
            weekly_calendar_error: str | None = None
            weekly_previous_period: str | None = None
            weekly_grace_through: date | None = None
            if source_id == "tdcc_shareholding":
                if candidate_db_path is None:
                    expected_period = None
                elif reference_date is None:
                    expected_period = None
                    weekly_calendar_error = "reference date was not supplied"
                else:
                    try:
                        (
                            expected_period,
                            weekly_previous_period,
                            weekly_grace_through,
                            weekly_calendar_error,
                        ) = _expected_tdcc_weekly_periods(
                            reference_date,
                            calendar,
                            allow_online_probe=allow_online_probe,
                        )
                    except (
                        AttributeError,
                        OfficialTradingCalendarError,
                        TypeError,
                        ValueError,
                    ) as exc:
                        expected_period = None
                        weekly_calendar_error = (
                            f"{type(exc).__name__}: {exc}"
                        )
                grace_open = bool(
                    weekly_grace_through is not None
                    and reference_date is not None
                    and _tdcc_publication_window_open(
                        run_now,
                        reference_date,
                        weekly_grace_through,
                    )
                )
                missing_periods = []
                if weekly_calendar_error or expected_period is None:
                    freshness_status = "unknown"
                elif latest == expected_period:
                    freshness_status = (
                        "current"
                        if version_coverage_complete and not duplicate_key_count
                        else "partial"
                    )
                elif latest and latest > expected_period:
                    freshness_status = (
                        "unknown"
                        if reference_date is not None
                        and latest > reference_date.strftime("%Y%m%d")
                        else "partial"
                    )
                elif grace_open and (
                    latest is None or latest == weekly_previous_period
                ):
                    freshness_status = "expected_wait"
                else:
                    freshness_status = "stale"
                    missing_periods = [expected_period]
            else:
                expected_period = expected_session
                missing_periods = (
                    [expected_session]
                    if expected_session and latest != expected_session
                    else []
                )
                if not exists or not count:
                    freshness_status = "unknown"
                elif expected_session and latest != expected_session:
                    freshness_status = "stale"
                elif not version_coverage_complete or duplicate_key_count:
                    freshness_status = "partial"
                else:
                    freshness_status = "current"

            if source_id == "tdcc_shareholding" and weekly_calendar_error:
                reason = f"official weekly calendar is unknown: {weekly_calendar_error}"
            elif candidate_db_path is None:
                reason = "PHASE3C_CANDIDATE_DB_PATH is not configured"
            elif db_error is not None:
                reason = f"candidate DB read failed: {db_error}"
            elif not candidate_db_path.is_file():
                reason = "configured candidate DB does not exist"
            elif not exists:
                reason = "candidate table does not exist"
            elif source_id == "tdcc_shareholding" and freshness_status == "current":
                reason = "latest completed-week TDCC snapshot is present"
            elif freshness_status == "current":
                reason = "latest official session and both market source versions are present"
            elif source_id == "tdcc_shareholding" and freshness_status == "expected_wait":
                reason = (
                    "waiting through the second subsequent official session for the "
                    "latest completed-week TDCC snapshot"
                )
            elif source_id == "tdcc_shareholding" and freshness_status == "stale":
                if (
                    latest is not None
                    and weekly_previous_period is not None
                    and latest < weekly_previous_period
                ):
                    reason = (
                        "latest TDCC observation is older than the previous completed "
                        "week; stale regardless of the internal publication grace"
                    )
                elif latest is None:
                    reason = "no TDCC weekly snapshot is available"
                else:
                    reason = (
                        "latest completed-week TDCC snapshot is missing after the "
                        "internal two-session grace ended"
                    )
            elif source_id == "tdcc_shareholding" and freshness_status == "partial":
                if latest and expected_period and latest > expected_period:
                    reason = (
                        "weekly observation is newer than the expected completed-week "
                        "period; cadence requires review"
                    )
                else:
                    reason = "weekly snapshot is present but source-version or key coverage is incomplete"
            elif source_id == "tdcc_shareholding" and freshness_status == "unknown":
                reason = (
                    "weekly observation date or calendar boundary cannot be safely classified"
                )
            elif missing_periods:
                reason = "latest candidate observation is behind the expected official session"
            else:
                reason = "candidate rows are present but source-version coverage is incomplete"

            statuses.append(
                _source_status(
                    source_id=source_id,
                    authority=authority,
                    frequency=(
                        "daily candidate source"
                        if source_id != "tdcc_shareholding"
                        else "weekly candidate source"
                    ),
                    actual_period=latest,
                    published_at=None,
                    available_at=latest_available_at,
                    expected_period=expected_period,
                    coverage={
                        "candidate_db_path": str(candidate_db_path) if candidate_db_path else None,
                        "candidate_db_exists": bool(candidate_db_path and candidate_db_path.is_file()),
                        "table_exists": bool(exists),
                        "db_row_count": count,
                        "latest_session_row_count": current_row_count,
                        "expected_source_versions": sorted(expected_versions),
                        "expected_source_version_groups": [
                            sorted(group) for group in expected_version_groups
                        ],
                        "observed_source_versions": observed_versions,
                        "source_version_coverage_complete": version_coverage_complete,
                        **(
                            {
                                "weekly_calendar_policy": (
                                    "last official session of the latest completed trading week"
                                ),
                                "official_data_period_basis": (
                                    "TDCC weekly snapshot data period is the last business "
                                    "day of the week; no official publication deadline is stated"
                                ),
                                "official_publication_deadline": None,
                                "publication_grace_policy": (
                                    "internal_conservative_two_subsequent_official_sessions"
                                ),
                                "publication_grace_is_official_deadline": False,
                                "previous_week_expected_period": weekly_previous_period,
                                "publication_grace_sessions": 2,
                                "publication_grace_through": (
                                    weekly_grace_through.isoformat()
                                    if weekly_grace_through is not None
                                    else None
                                ),
                                "issuer_or_scope_completeness_verified": False,
                            }
                            if source_id == "tdcc_shareholding"
                            else {}
                        ),
                    },
                    missing_periods=missing_periods,
                    duplicate_key_count=duplicate_key_count,
                    freshness_status=freshness_status,
                    reason=reason,
                    update_entry="UpdateService.update_phase3c_candidate_range",
                    scheduled_task=scheduled_task,
                    owner="Data Engineering + P0 source owners",
                    downstream=["candidate research only"],
                    candidate_only=True,
                )
            )
    finally:
        if conn is not None:
            conn.close()
    return statuses


def _candidate_and_static_statuses(
    *,
    data_root: Path,
) -> list[dict[str, Any]]:
    statuses: list[dict[str, Any]] = []
    static_specs = (
        ("company.master_data", data_root / "meta_data" / "companies.csv", "company registry / official listing metadata"),
        ("broker.branch_registry", data_root / "meta_data" / "broker_branch_registry.csv", "broker registry and MoneyDJ route mapping"),
        ("fundamental.monthly_availability_map", data_root / "meta_data" / "monthly_revenue_availability.csv", "TWSE / TPEx / MOPS availability map"),
        ("fundamental.statement_availability_map", data_root / "meta_data" / "fundamental_statement_availability.csv", "MOPS statement availability map"),
        ("calendar.local_date_table", data_root / "meta_data" / "Date_table.csv", "local calendar artifact; not authoritative without official evidence"),
        ("legacy.aggregate_stock_snapshot", data_root / "meta_data" / "stock_data_whole.csv", "legacy aggregate; source receipt required for prod acceptance"),
        ("legacy.all_stocks_snapshot", data_root / "meta_data" / "all_stocks_data.csv", "legacy aggregate; not a daily completeness proof"),
        ("derived.industry_analysis", data_root / "industry_analysis", "derived industry analysis files"),
        ("derived.features", data_root / "features", "derived feature files"),
    )
    for source_id, path, authority in static_specs:
        if path.is_dir():
            files = list(path.rglob("*"))
            file_items = [item for item in files if item.is_file()]
            observed = max((item.stat().st_mtime for item in file_items), default=None)
            statuses.append(_source_status(
                source_id=source_id,
                authority=authority,
                frequency="derived/static",
                actual_period=None,
                published_at=None,
                available_at=(
                    datetime.fromtimestamp(observed, tz=PACIFIC).isoformat(timespec="seconds")
                    if observed is not None else None
                ),
                expected_period=None,
                coverage={
                    "directory_exists": path.is_dir(),
                    "file_count": len(file_items),
                },
                missing_periods=[],
                duplicate_key_count=None,
                freshness_status="not_applicable" if file_items else "unknown",
                reason=(
                    "derived/static source; no official release cadence registered"
                    if file_items else "directory missing or empty"
                ),
                update_entry="derived consumer-specific refresh; no daily source updater",
                scheduled_task="not scheduled by daily data update",
                owner="Downstream data owner",
                downstream=[],
            ))
        else:
            statuses.append(_static_file_status(
                path,
                source_id=source_id,
                authority=authority,
                update_entry="static registry refresh / source-specific updater",
                scheduled_task="not scheduled by daily data update",
                owner="Data Engineering + source owner",
                downstream=[],
            ))

    for source_id, authority, reason in (
        ("derivatives.futures_options", "No registered local official futures/options source", "source type is not present in configured roots, schema, or updater registry"),
        ("corporate_actions.production_table", "TWSE / TPEx corporate-action candidate routes", "only candidate/event artifacts exist; no production SQLite table is registered"),
        ("microstructure.restrictions.production_table", "TWSE restriction candidate routes", "only candidate/event artifacts exist; no production SQLite table is registered"),
    ):
        statuses.append(
            _source_status(
                source_id=source_id,
                authority=authority,
                frequency="event-driven",
                actual_period=None,
                published_at=None,
                available_at=None,
                expected_period=None,
                coverage={"present": False},
                missing_periods=[],
                duplicate_key_count=None,
                freshness_status="not_applicable",
                reason=reason,
                update_entry="candidate source registry only",
                scheduled_task="not scheduled for production ingestion",
                owner="Data Engineering + source owner",
                downstream=[],
                candidate_only=True,
            )
        )
    return statuses


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    data_root = Path(args.data_root)
    output_root = Path(args.output_root)
    db_path = Path(args.db_path)
    run_root = output_root / "scheduled" / "data_freshness"
    run_now = scheduled_now()
    run_date = _local_now(run_now).date()
    today_key = run_date.isoformat().replace("-", "")
    status_path = Path(args.status_path) if args.status_path else run_root / "latest_status.json"
    log_path = Path(args.log_path) if args.log_path else run_root / f"{today_key}_data_freshness.log"

    checks: dict[str, Any] = {
        "data_root_exists": data_root.exists(),
        "db_path": str(db_path),
        "db_exists": db_path.exists(),
        "calendar_cutoff_local": DAILY_DATA_CUTOFF_LOCAL.strftime("%H:%M"),
        "read_only": True,
    }
    warnings: list[str] = []
    errors: list[str] = []

    if not data_root.exists():
        errors.append("data_root_missing")
    if not db_path.exists():
        errors.append("sqlite_db_missing")

    canonical_quick_status_path = (
        output_root / "scheduled" / "data_update_quick" / "latest_status.json"
    )
    quick_update_status_path = (
        Path(args.quick_status_path)
        if args.quick_status_path
        else canonical_quick_status_path
    )
    quick_payload, quick_binding = _quick_status_snapshot(
        status_path=quick_update_status_path,
        canonical_status_path=canonical_quick_status_path,
        observed_at=run_now,
    )
    checks["data_update_quick_receipt_binding"] = quick_binding
    if quick_binding["binding_reason"] == "quick_status_missing":
        checks["data_update_quick_status"] = "missing"
        _append_warning(warnings, "data_update_quick_status_missing")
    elif quick_binding["binding_reason"] == "quick_status_not_object":
        # Preserve the legacy status classification for valid non-object JSON.
        checks["data_update_quick_status"] = "unknown"
    elif quick_payload is None:
        _append_warning(warnings, "data_update_quick_status_unreadable")
    elif isinstance(quick_payload, dict):
        quick_status = str(quick_payload.get("status", "unknown"))
        checks["data_update_quick_status"] = quick_status
        if quick_status == "failed":
            _append_warning(warnings, "data_update_quick_failed")
        quick_checked_at = _parse_timestamp(
            quick_payload.get("completed_at") or quick_payload.get("checked_at")
        )
        checks["data_update_quick_checked_at"] = (
            quick_checked_at.isoformat(timespec="seconds") if quick_checked_at else None
        )

    # 研究採集是獨立唯讀投影，不併入正式／候選 freshness 或整體通過狀態。
    try:
        from scripts.audit_scheduled_research_acquisition import audit_quick_monthly_capture

        quick_monthly_research = audit_quick_monthly_capture(
            quick_update_status_path,
            quick_payload=quick_payload,
            quick_binding=quick_binding,
            now=run_now,
        )
    except (OSError, ValueError, TypeError, KeyError, ImportError, SyntaxError) as exc:
        quick_monthly_research = {
            "status": "blocked",
            "reason": str(exc) or type(exc).__name__,
            "error_type": type(exc).__name__,
            "formal_credit": False,
        }
    weekly_research = verify_weekly_acquisition(
        output_root,
        now=run_now,
        receipt_path=args.weekly_parent_receipt_path,
        expected_sha256=args.weekly_parent_receipt_sha256,
    )
    checks["research_acquisition"] = {
        "status": "blocked"
        if "blocked" in {quick_monthly_research.get("status"), weekly_research.get("status")}
        else "observed",
        "quick_monthly_candidate": quick_monthly_research,
        "weekly_collection": weekly_research,
        "independent_of_formal_and_candidate_freshness": True,
        "formal_credit": False,
        "historical_pit_credit": False,
        "database_write_performed_by_probe": False,
    }

    source_statuses: list[dict[str, Any]] = []
    candidate_db_path: Path | None = None
    configured_candidate_path = configured_candidate_db_path()
    if configured_candidate_path is not None:
        try:
            candidate_db_path = validate_candidate_working_copy_path(
                configured_candidate_path,
                production_data_root=data_root,
                production_db_path=db_path,
            )
        except ValueError as exc:
            checks["phase3c_candidate_db"] = {
                "status": "invalid",
                "path": str(configured_candidate_path),
                "reason": f"{type(exc).__name__}:{exc}",
            }
        else:
            checks["phase3c_candidate_db"] = {
                "status": "available" if candidate_db_path.is_file() else "missing",
                "path": str(candidate_db_path),
                "read_only": True,
            }
    else:
        checks["phase3c_candidate_db"] = {
            "status": "not_configured",
            "path": None,
            "read_only": True,
        }
    if db_path.exists():
        try:
            uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
            with sqlite3.connect(uri, uri=True) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA query_only=ON")
                checks["sqlite_journal_mode"] = str(conn.execute("PRAGMA journal_mode").fetchone()[0])
                checks["sqlite_query_only"] = int(conn.execute("PRAGMA query_only").fetchone()[0])
                for table in ("daily_prices", "technical_indicators"):
                    checks[f"{table}_latest_date"] = _latest_date(conn, table)

                calendar = OfficialTradingCalendar(
                    db_path=db_path,
                    calendar_cache_path=(
                        args.calendar_cache_path
                        or _default_calendar_cache_path()
                    ),
                    temporary_closure_path=args.temporary_closure_path,
                )
                try:
                    expected_records = calendar.get_recent_official_trading_days(
                        run_date,
                        max(1, int(args.calendar_window_sessions)),
                        include_reference=True,
                        allow_online_probe=True,
                    )
                except (OfficialTradingCalendarError, ValueError) as exc:
                    checks["official_calendar"] = {
                        "freshness_status": "failed",
                        "reason": f"{type(exc).__name__}:{exc}",
                    }
                    errors.append("official_calendar_unavailable")
                    expected_records = []
                else:
                    checks["official_calendar"] = {
                        "freshness_status": "current",
                        "source": "TWSE holidaySchedule + temporary closure evidence",
                        "records": [
                            {key: value for key, value in record.items() if key != "date"}
                            for record in expected_records
                        ],
                    }

                if expected_records:
                    expected_latest = str(expected_records[-1]["date_str"]).replace("-", "")
                    expected_date = _date_from_key(expected_latest)
                    checks["data_update_quick_expected_date"] = expected_date.isoformat()
                    quick_checked_at = _parse_timestamp(
                        (quick_payload or {}).get("completed_at") or (quick_payload or {}).get("checked_at")
                    )
                    quick_checked_date = _local_now(quick_checked_at).date() if quick_checked_at else None
                    checks["data_update_quick_checked_date"] = quick_checked_date.isoformat() if quick_checked_date else None
                    if quick_payload is not None and (
                        quick_checked_date is None or quick_checked_date < expected_date
                    ):
                        _append_warning(warnings, "data_update_quick_status_stale")
                    elif (
                        quick_checked_date == expected_date
                        and _local_now(run_now).time() < DAILY_DATA_CUTOFF_LOCAL
                    ):
                        checks["data_update_quick_waiting_for_cutoff"] = True
                    elif quick_payload and str(quick_payload.get("status")) not in {"passed", "passed_with_warnings"}:
                        _append_warning(warnings, "data_update_quick_status_not_successful")

                    source_statuses.extend(
                        _build_operational_source_statuses(
                            conn=conn,
                            data_root=data_root,
                            expected_records=expected_records,
                            quick_payload=quick_payload,
                            run_now=run_now,
                            warnings=warnings,
                            checks=checks,
                        )
                    )
                source_statuses.extend(
                    _phase3c_candidate_statuses(
                        candidate_db_path=candidate_db_path,
                        expected_session=checks.get("expected_official_session"),
                        calendar=calendar,
                        reference_date=run_date,
                        run_now=run_now,
                        allow_online_probe=True,
                    )
                )
                source_statuses.extend(
                    _candidate_and_static_statuses(data_root=data_root)
                )
        except Exception as exc:  # noqa: BLE001 - read failure must be visible
            errors.append("sqlite_read_failed")
            checks["sqlite_error"] = f"{type(exc).__name__}:{exc}"

    checks["source_statuses"] = source_statuses
    expected_key = checks.get("expected_official_session")
    for item in source_statuses:
        source_status = str(item.get("freshness_status", ""))
        if source_status not in {"stale", "partial", "failed"}:
            continue
        if item.get("candidate_only"):
            continue
        # Preserve the legacy per-file diagnostics for an old local snapshot,
        # while ensuring a current-session source problem can never result in
        # a green overall probe merely because MAX(date) exists.
        _append_warning(
            warnings,
            f"source_freshness_degraded:{item.get('source_id')}",
        )
    checks["source_status_counts"] = {
        status: sum(1 for item in source_statuses if item.get("freshness_status") == status)
        for status in sorted({str(item.get("freshness_status")) for item in source_statuses})
    }
    status = "failed" if errors else "degraded" if warnings else "passed"
    payload = {
        "task": "baldr-data-freshness-check-daily",
        "status": status,
        "read_only": True,
        "checked_at": run_now.isoformat(timespec="seconds"),
        "data_root": str(data_root),
        "output_root": str(output_root),
        "checks": checks,
        "source_statuses": source_statuses,
        "warnings": warnings,
        "errors": errors,
        "stale_days": args.stale_days,
        "status_vocabulary": ["current", "expected_wait", "stale", "failed", "partial", "not_applicable", "unknown"],
    }
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, default=str)
    write_errors: list[str] = []
    for label, path in (("status", status_path), ("log", log_path)):
        write_error = _write_artifact(path, text + "\n", label=label)
        if write_error is not None:
            write_errors.append(write_error)

    if write_errors:
        errors.extend(write_errors)
        payload["status"] = "failed"
        payload["errors"] = errors
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, default=str)
        for label, path in (("status_retry", status_path), ("log_retry", log_path)):
            _write_artifact(path, text + "\n", label=label)
    print(text)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
