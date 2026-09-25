"""唯讀驗證 Paper EOD replay 的資料更新相依性。

這個 gate 只觀察固定 D 槽來源，不呼叫 API、不寫入來源檔或 SQLite。Paper
EOD 只有在 quick update、freshness、daily_prices 交易日與來源檔 hash 同屬
當日且可重驗時才會進入既有 isolated adapter。週末或 hash-bound 官方年度
休市 cache 明確關閉 exact target date 時直接回傳 no-op；quick update 的真實
錯誤仍由其自身 receipt 保留，不被休市分類改寫。
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from io import StringIO
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from data_module.official_trading_calendar_cache import (
    OfficialCalendarCacheError,
    VerifiedOfficialCalendarCache,
    load_verified_twse_calendar_cache,
)


TAIPEI = ZoneInfo("Asia/Taipei")
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_ROOT = Path(r"D:\Min\Python\Project\FA_Data")
DEFAULT_OUTPUT_ROOT = DEFAULT_DATA_ROOT / "output"
DEFAULT_DB_PATH = DEFAULT_DATA_ROOT / "sqlite" / "twstock.db"
DEFAULT_CALENDAR_CACHE_ROOT = (
    REPOSITORY_ROOT / "output" / "paper_execution_eod_replay" / "calendar_cache"
)

# Paper EOD 只消費下列三個 freshness 市場來源；其他來源由各自 lane
# 另行判定，不能因跨 lane 的降級狀態直接阻擋 Paper。
PAPER_EOD_REQUIRED_FRESHNESS_SOURCE_IDS = frozenset(
    {
        "twse.daily_prices.raw",
        "tpex.daily_prices.raw",
        "sqlite.daily_prices",
    }
)
PAPER_EOD_NON_REQUIRED_FRESHNESS_SOURCE_IDS = frozenset(
    {
        "sqlite.market_indices",
        "sqlite.industry_indices",
        "sqlite.broker_flows",
        "sqlite.technical_indicators",
        "fundamental.monthly_revenues",
        "fundamental.quarterly_statements",
        "fundamental.current_monthly_observations",
        "fundamental.current_statement_observations",
        "fundamental.statement_availability_map",
        "institutional_flows",
        "credit_transactions",
        "tdcc_shareholding",
    }
)
PAPER_EOD_ALLOWED_DEGRADED_SOURCE_STATUSES = frozenset({"stale", "partial"})
PAPER_EOD_FRESHNESS_SOURCE_STATUS_VALUES = frozenset(
    {"current", "expected_wait", "stale", "failed", "partial", "not_applicable", "unknown"}
)
PAPER_EOD_EXACT_NON_REQUIRED_WARNINGS = {
    "monthly_revenue_expected_period_not_available": "fundamental.monthly_revenues",
    "quarterly_statement_expected_period_not_available": "fundamental.quarterly_statements",
    "technical_indicators_latest_coverage_partial": "sqlite.technical_indicators",
}
# 這兩個來源的 unknown 只代表其各自 consumer 尚未完成證據，不是 Paper
# EOD 的輸入。例外必須逐一列出；不把其他 unknown 轉成可接受狀態。
PAPER_EOD_NON_REQUIRED_UNKNOWN_POLICIES: dict[str, dict[str, str]] = {
    "tdcc_shareholding": {
        "reason_code": "weekly_candidate_completeness_not_proven",
        "consumer_boundary": "tdcc_p0_candidate_shadow",
        "consumer_basis": "P0 週資料候選；無 Paper EOD downstream 或 production ingestion",
    },
    "fundamental.statement_availability_map": {
        "reason_code": "fundamental_pit_mapping_missing",
        "consumer_boundary": "fundamental_pit_availability",
        "consumer_basis": "MOPS Fundamental/PIT availability mapping；不在 Paper EOD input",
    },
}
# candidate-only source 若要從 Paper EOD freshness lane 隔離，必須逐一列入
# policy，並精確符合 data_freshness_probe 的 source row contract；不能因
# candidate_only=True 就概括放行所有來源。
PAPER_EOD_NON_REQUIRED_CANDIDATE_POLICIES: dict[str, dict[str, object]] = {
    "credit_transactions": {
        "policy_version": "paper-eod-candidate-non-required.v1",
        "reason_code": "p0_candidate_source_not_paper_eod_input",
        "consumer_boundary": "p0_candidate_shadow",
        "consumer_basis": (
            "P0 candidate source; candidate research only; "
            "no Paper EOD downstream or production ingestion"
        ),
        "expected_frequency": "daily candidate source",
        "expected_downstream": ("candidate research only",),
        "expected_update_entry": "UpdateService.update_phase3c_candidate_range",
    },
}


def _parse_date(value: object) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text[:10] if fmt == "%Y-%m-%d" else text[:8], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def _parse_aware_timestamp(value: object) -> tuple[datetime | None, str | None]:
    """Parse a receipt timestamp without accepting local/naive clock guesses."""

    if value is None:
        return None, "missing"
    text = str(value).strip()
    if not text:
        return None, "missing"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None, "malformed"
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None, "naive"
    return parsed.astimezone(timezone.utc), None


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """讀取 JSON 並回傳 payload、內容 hash、可觀測錯誤。"""

    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None, None, f"missing:{path}"
    except OSError as error:
        return None, None, f"read_failed:{path}:{type(error).__name__}:{error}"
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        return None, _sha256_bytes(raw), f"malformed:{path}:{type(error).__name__}:{error}"
    if not isinstance(payload, dict):
        return None, _sha256_bytes(raw), f"{path}:payload_not_object"
    return payload, _sha256_bytes(raw), None


def _file_observation_with_raw(
    path: Path,
) -> tuple[dict[str, object] | None, str | None, bytes | None]:
    try:
        before = path.stat()
        raw = path.read_bytes()
        after = path.stat()
    except OSError as error:
        return None, f"{path}:read_failed:{type(error).__name__}:{error}", None
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        return None, f"{path}:changed_during_read", None
    return {
        "path": str(path.resolve()),
        "size_bytes": int(before.st_size),
        "mtime_ns": int(before.st_mtime_ns),
        "sha256": _sha256_bytes(raw),
    }, None, raw


def _file_observation(path: Path) -> tuple[dict[str, object] | None, str | None]:
    observation, error, _ = _file_observation_with_raw(path)
    return observation, error


_CODE_COLUMNS = ("證券代號", "證券代碼", "股票代號", "代號", "code", "Code")
_OPEN_COLUMNS = ("開盤價", "開盤", "open", "Open")
_DATE_COLUMNS = ("日期", "交易日期", "date", "Date")


def _first_column(fieldnames: Sequence[str] | None, candidates: Sequence[str]) -> str | None:
    if not fieldnames:
        return None
    by_normalised = {str(name).strip().lstrip("\ufeff").lower(): str(name) for name in fieldnames}
    for candidate in candidates:
        found = by_normalised.get(candidate.lower())
        if found is not None:
            return found
    return None


def _read_source_open_rows(
    path: Path,
    *,
    target: date,
    raw: bytes | None = None,
    limit: int | None = None,
) -> tuple[list[tuple[str, Decimal]], dict[str, object] | None, str | None]:
    """讀取 bounded source rows，供同日 SQLite open readback 使用。"""

    try:
        before = path.stat()
        if raw is None:
            raw = path.read_bytes()
    except OSError as error:
        return [], None, f"source_file_read_failed:{path}:{type(error).__name__}:{error}"

    rows: list[tuple[str, Decimal]] = []
    total_data_rows = 0
    parse_error: str | None = None
    for encoding in ("utf-8-sig", "cp950"):
        parse_error = None
        try:
            text = raw.decode(encoding)
            reader = csv.DictReader(StringIO(text))
            code_column = _first_column(reader.fieldnames, _CODE_COLUMNS)
            open_column = _first_column(reader.fieldnames, _OPEN_COLUMNS)
            date_column = _first_column(reader.fieldnames, _DATE_COLUMNS)
            if code_column is None or open_column is None:
                parse_error = f"source_columns_missing:{path}"
                continue
            rows = []
            total_data_rows = 0
            for row in reader:
                total_data_rows += 1
                if date_column is not None:
                    row_date = _parse_date(row.get(date_column))
                    if row_date != target:
                        parse_error = f"source_row_date_mismatch:{path}:{row.get(date_column)}"
                        break
                code = str(row.get(code_column) or "").strip()
                raw_open = str(row.get(open_column) or "").strip().replace(",", "")
                if not code or raw_open in {"", "-", "--", "N/A", "NA"}:
                    continue
                try:
                    open_value = Decimal(raw_open)
                except InvalidOperation:
                    parse_error = f"source_open_not_decimal:{path}:{code}"
                    break
                rows.append((code, open_value))
                if limit is not None and len(rows) >= limit:
                    break
            if parse_error is None or parse_error.startswith("source_row_date_mismatch:"):
                break
        except UnicodeDecodeError:
            continue
        except (csv.Error, ValueError) as error:
            parse_error = f"source_csv_parse_failed:{path}:{type(error).__name__}:{error}"
            continue

    try:
        after = path.stat()
    except OSError as error:
        return [], None, f"source_file_stat_failed:{path}:{type(error).__name__}:{error}"
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        return [], None, f"source_file_changed_during_read:{path}"
    observation = {
        "path": str(path.resolve()),
        "total_data_rows_observed": total_data_rows,
        "usable_open_rows_observed": len(rows),
        "readback_limit": limit,
        "scope": "all_usable_source_rows" if limit is None else f"first_{limit}_usable_source_rows",
    }
    if parse_error is not None:
        return rows, observation, parse_error
    if total_data_rows == 0 or not rows:
        return rows, observation, f"source_rows_empty_or_open_missing:{path}"
    return rows, observation, None


def _source_db_readback(
    db_path: Path,
    *,
    target: date,
    source_rows: Sequence[tuple[str, Decimal]],
    market_name: str,
) -> tuple[dict[str, object], list[str]]:
    """以 SQLite read-only 查核 bounded source code/open values。"""

    diagnostics: list[str] = []
    if not source_rows:
        return {"market": market_name, "checked_rows": 0, "matched_rows": 0}, diagnostics
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)
        connection.execute("PRAGMA query_only=ON")
        codes = list(dict.fromkeys(code for code, _ in source_rows))
        placeholders = ",".join("?" for _ in codes)
        target_key = target.strftime("%Y%m%d")
        db_values: dict[str, object] = {}
        # SQLite builds commonly cap bound variables at 999. Chunking keeps
        # the readback full-file capable without changing the connection mode.
        for offset in range(0, len(codes), 500):
            chunk = codes[offset : offset + 500]
            placeholders = ",".join("?" for _ in chunk)
            records = connection.execute(
                'SELECT "證券代號", "開盤價" FROM "daily_prices" '
                f'WHERE REPLACE(REPLACE("日期", \'-\', \'\'), \'/\', \'\')=? '
                f'AND "證券代號" IN ({placeholders})',
                [target_key, *chunk],
            ).fetchall()
            db_values.update({str(code).strip(): value for code, value in records})
    except (OSError, sqlite3.Error) as error:
        diagnostics.append(
            f"source_db_readback_failed:{market_name}:{type(error).__name__}:{error}"
        )
        return {"market": market_name, "checked_rows": len(source_rows), "matched_rows": 0}, diagnostics
    finally:
        if connection is not None:
            connection.close()
    matched = 0
    for code, source_open in source_rows:
        db_open = db_values.get(code)
        if db_open is None:
            diagnostics.append(f"source_db_readback_missing:{market_name}:{code}")
            continue
        try:
            db_decimal = Decimal(str(db_open))
        except InvalidOperation:
            diagnostics.append(f"source_db_readback_open_not_decimal:{market_name}:{code}")
            continue
        if db_decimal != source_open:
            diagnostics.append(
                f"source_db_readback_mismatch:{market_name}:{code}:source={source_open}:db={db_decimal}"
            )
            continue
        matched += 1
    return {
        "market": market_name,
        "checked_rows": len(source_rows),
        "matched_rows": matched,
        "scope": "all_usable_source_rows",
    }, diagnostics


def _latest_market_rows(db_path: Path, target: date) -> tuple[dict[str, object] | None, str | None]:
    """以 SQLite mode=ro/query_only 檢查 target 日行情，不取得或寫入資料。"""

    if not db_path.is_file():
        return None, f"market_db_missing:{db_path}"
    connection: sqlite3.Connection | None = None
    try:
        before = db_path.stat()
        connection = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)
        connection.execute("PRAGMA query_only=ON")
        columns = {
            str(row[1])
            for row in connection.execute('PRAGMA table_info("daily_prices")').fetchall()
        }
        required = {"日期", "證券代號", "開盤價"}
        missing = sorted(required - columns)
        if missing:
            return None, f"market_db_columns_missing:{','.join(missing)}"
        target_key = target.strftime("%Y%m%d")
        row = connection.execute(
            'SELECT COUNT(*), COUNT("開盤價"), MAX("日期") '
            'FROM "daily_prices" WHERE REPLACE(REPLACE("日期", \'-\', \'\'), \'/\', \'\')=?',
            (target_key,),
        ).fetchone()
        total_rows = int(row[0] or 0)
        open_rows = int(row[1] or 0)
        latest = None if row[2] is None else str(row[2])
    except (OSError, sqlite3.Error) as error:
        return None, f"market_db_read_failed:{type(error).__name__}:{error}"
    finally:
        if connection is not None:
            connection.close()
    try:
        after = db_path.stat()
    except OSError as error:
        return None, f"market_db_stat_failed:{type(error).__name__}:{error}"
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        return None, "market_db_changed_during_read"
    return {
        "path": str(db_path.resolve()),
        "mode": "ro/query_only",
        "target_date": target.isoformat(),
        "target_key": target_key,
        "row_count": total_rows,
        "open_row_count": open_rows,
        "latest_date": latest,
        "ready": total_rows > 0 and open_rows > 0,
    }, None


def _step(payload: Mapping[str, object], name: str) -> Mapping[str, object] | None:
    raw_steps = payload.get("steps")
    steps = raw_steps if isinstance(raw_steps, list) else []
    for item in steps:
        if isinstance(item, Mapping) and item.get("name") == name:
            return item
    return None


def _step_passed(payload: Mapping[str, object] | None, name: str) -> bool:
    step = _step(payload or {}, name)
    return isinstance(step, Mapping) and step.get("status") == "passed"


def _calendar_cache_candidates(
    cache_path: str | Path,
    *,
    calendar_year: int,
) -> tuple[Path, ...]:
    """列出指定年度 cache candidates，並拒絕 reparse 後逃離 root 的檔案。"""

    root = Path(cache_path).expanduser().resolve()
    if root.exists() and root.is_file():
        return (root,)
    if root.suffix.casefold() == ".json":
        return (root,)
    if not root.is_dir():
        return ()
    candidates = list(root.glob(f"twse_holiday_schedule_{calendar_year}_*.json"))
    exact = root / f"twse_holiday_schedule_{calendar_year}.json"
    if exact.exists():
        candidates.append(exact)
    resolved: list[Path] = []
    for candidate in sorted(set(candidates)):
        candidate_resolved = candidate.resolve()
        try:
            candidate_resolved.relative_to(root)
        except ValueError:
            continue
        resolved.append(candidate_resolved)
    return tuple(resolved)


def _verified_closed_calendar_evidence(
    *,
    target: date,
    observed: datetime,
    cache_path: str | Path,
) -> dict[str, object] | None:
    """只把 exact target 的 hash-bound 官方 annual closed row 當作 no-op。

    loader 會以同一個 gate observed clock 驗證 raw/content hash、完整年度、
    available/captured 時間鏈與 freshness；open、缺失、過期或任何驗證失敗
    都回傳 ``None``，讓既有 required-source gate 繼續 fail closed。
    """

    verified: list[VerifiedOfficialCalendarCache] = []
    for candidate in _calendar_cache_candidates(
        cache_path,
        calendar_year=target.year,
    ):
        try:
            verified.append(
                load_verified_twse_calendar_cache(
                    candidate,
                    calendar_year=target.year,
                    observed_at=observed,
                )
            )
        except OfficialCalendarCacheError:
            continue
    if not verified:
        return None

    selected = max(
        verified,
        key=lambda item: str(item.evidence.get("captured_at", "")),
    )
    if selected.schedule.get(target) is not False:
        return None
    evidence = dict(selected.evidence)
    evidence.update(
        {
            "target_date": target.isoformat(),
            "is_trading_day": False,
            "reason_code": "twse_holiday_schedule_cache_closed",
        }
    )
    return evidence


def _candidate_non_eod_policy(
    *,
    source_id: str,
    source_status: str,
    source: Mapping[str, object],
) -> dict[str, object] | None:
    """只接受具名、candidate-only 且完整符合來源契約的非 EOD source。"""

    if source_status not in PAPER_EOD_ALLOWED_DEGRADED_SOURCE_STATUSES:
        return None
    policy = PAPER_EOD_NON_REQUIRED_CANDIDATE_POLICIES.get(source_id)
    if policy is None or source.get("candidate_only") is not True:
        return None
    if source.get("frequency") != policy.get("expected_frequency"):
        return None
    downstream = source.get("downstream")
    expected_downstream = policy.get("expected_downstream")
    if (
        not isinstance(downstream, list)
        or not isinstance(expected_downstream, tuple)
        or downstream != list(expected_downstream)
    ):
        return None
    if source.get("update_entry") != policy.get("expected_update_entry"):
        return None
    reason = source.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return None
    return {
        "policy_version": policy["policy_version"],
        "reason_code": policy["reason_code"],
        "consumer_boundary": policy["consumer_boundary"],
        "consumer_basis": policy["consumer_basis"],
    }


def _paper_eod_freshness_projection(
    payload: Mapping[str, object],
    *,
    target: date,
) -> tuple[dict[str, object], list[str], list[str]]:
    """將 freshness aggregate 投影為 Paper EOD 可審的 lane 結果。

    只有 probe 明確回報 degraded、errors 為空、每個 warning 都能對應到
    已登記的非 EOD source，且三個 Paper 市場 source 同日 current 時，才
    允許後續 gate 以 warning 繼續。此函式不改寫 aggregate status，也不移除
    日期、時間、raw/DB readback 等 gate blocker。
    """

    aggregate_status = str(payload.get("status") or "").strip().lower()
    projection: dict[str, object] = {
        "schema_version": "paper-eod-freshness-lane.v1",
        "lane": "paper_eod",
        "target_date": target.isoformat(),
        "aggregate_status": aggregate_status,
        "required_source_ids": sorted(PAPER_EOD_REQUIRED_FRESHNESS_SOURCE_IDS),
        "allowed_non_eod_source_ids": sorted(PAPER_EOD_NON_REQUIRED_FRESHNESS_SOURCE_IDS),
    }
    if aggregate_status != "degraded":
        projection["status"] = "not_applicable"
        return projection, [], []

    blockers: list[str] = []
    ignored_warnings: list[str] = []
    raw_errors = payload.get("errors")
    raw_warnings = payload.get("warnings")
    raw_source_statuses = payload.get("source_statuses")
    projection["aggregate_errors"] = raw_errors
    projection["aggregate_warnings"] = raw_warnings

    if not isinstance(raw_errors, list) or any(not isinstance(item, str) for item in raw_errors):
        blockers.append("freshness_lane_errors_malformed")
    elif raw_errors:
        blockers.append("freshness_lane_errors_present")
    if not isinstance(raw_warnings, list) or any(
        not isinstance(item, str) or not item.strip() for item in raw_warnings
    ):
        blockers.append("freshness_lane_warnings_malformed")
    elif not raw_warnings:
        blockers.append("freshness_lane_warnings_empty")
    if not isinstance(raw_source_statuses, list):
        blockers.append("freshness_lane_source_statuses_malformed")

    source_by_id: dict[str, Mapping[str, object]] = {}
    if isinstance(raw_source_statuses, list):
        source_status_by_id: dict[str, str] = {}
        for index, item in enumerate(raw_source_statuses):
            if not isinstance(item, Mapping):
                blockers.append(f"freshness_lane_source_status_malformed:{index}")
                continue
            raw_source_id = item.get("source_id")
            if not isinstance(raw_source_id, str) or not raw_source_id.strip():
                blockers.append(f"freshness_lane_source_id_malformed:{index}")
                continue
            source_id = raw_source_id.strip()
            if source_id in source_by_id:
                blockers.append(f"freshness_lane_source_id_duplicate:{source_id}")
                continue
            source_by_id[source_id] = item
            raw_source_status = item.get("freshness_status")
            if not isinstance(raw_source_status, str) or not raw_source_status.strip():
                blockers.append(f"freshness_lane_source_status_malformed:{source_id}")
                source_status_by_id[source_id] = ""
                continue
            source_status = raw_source_status.strip().lower()
            source_status_by_id[source_id] = source_status
            if source_status not in PAPER_EOD_FRESHNESS_SOURCE_STATUS_VALUES:
                blockers.append(f"freshness_lane_source_status_unknown:{source_id}:{source_status}")
    else:
        source_status_by_id = {}

    required_projection: dict[str, object] = {}
    for source_id in sorted(PAPER_EOD_REQUIRED_FRESHNESS_SOURCE_IDS):
        source = source_by_id.get(source_id)
        if source is None:
            blockers.append(f"freshness_required_source_missing:{source_id}")
            continue
        source_status = source_status_by_id.get(source_id, "")
        actual_period = _parse_date(source.get("actual_period"))
        expected_period = _parse_date(source.get("expected_period"))
        required_projection[source_id] = {
            "freshness_status": source_status,
            "actual_period": actual_period.isoformat() if actual_period else None,
            "expected_period": expected_period.isoformat() if expected_period else None,
        }
        if source_status != "current":
            blockers.append(f"freshness_required_source_not_current:{source_id}:{source_status or 'missing'}")
        if actual_period != target:
            blockers.append(f"freshness_required_source_date_not_target:{source_id}:actual")
        if expected_period != target:
            blockers.append(f"freshness_required_source_date_not_target:{source_id}:expected")
    projection["required_sources"] = required_projection

    warning_sources: dict[str, list[str]] = {}
    if isinstance(raw_warnings, list):
        for raw_warning in raw_warnings:
            warning = raw_warning.strip() if isinstance(raw_warning, str) else ""
            warning_source_id: str | None = PAPER_EOD_EXACT_NON_REQUIRED_WARNINGS.get(warning)
            if warning_source_id is None and warning.startswith("source_freshness_degraded:"):
                warning_source_id = warning.split(":", 1)[1].strip()
            if (
                warning_source_id is None
                or warning_source_id not in PAPER_EOD_NON_REQUIRED_FRESHNESS_SOURCE_IDS
            ):
                blockers.append(f"freshness_lane_warning_unclassified:{warning or 'missing'}")
                continue
            source = source_by_id.get(warning_source_id)
            if source is None:
                blockers.append(f"freshness_non_eod_source_missing:{warning_source_id}")
                continue
            source_status = source_status_by_id.get(warning_source_id, "")
            if source_status not in PAPER_EOD_ALLOWED_DEGRADED_SOURCE_STATUSES:
                blockers.append(
                    "freshness_non_eod_source_status_not_degraded:"
                    f"{warning_source_id}:{source_status or 'missing'}"
                )
                continue
            warning_sources.setdefault(warning_source_id, []).append(warning)
            ignored_warnings.append(warning)

    projection["ignored_non_eod_sources"] = {
        source_id: {
            "freshness_status": source_status_by_id.get(source_id, ""),
            "warnings": warning_list,
            "candidate_only": bool(source_by_id[source_id].get("candidate_only", False)),
        }
        for source_id, warning_list in sorted(warning_sources.items())
    }
    projection["ignored_non_eod_source_ids"] = sorted(warning_sources)
    projection["ignored_non_eod_warnings"] = ignored_warnings
    non_current_sources: list[dict[str, str]] = []
    not_required_for_paper_eod: dict[str, dict[str, object]] = {}
    for source_id, source_status in sorted(source_status_by_id.items()):
        if source_status in {"", "current", "not_applicable"}:
            continue
        non_current_sources.append({"source_id": source_id, "freshness_status": source_status})
        if source_id in PAPER_EOD_REQUIRED_FRESHNESS_SOURCE_IDS:
            continue
        if source_status == "unknown":
            policy = PAPER_EOD_NON_REQUIRED_UNKNOWN_POLICIES.get(source_id)
            source = source_by_id[source_id]
            if policy is not None:
                # 保存完整原始 row，讓 TDCC／Fundamental 自己的 consumer 仍能
                # 看到 unknown、reason、availability 與 coverage 診斷。
                not_required_for_paper_eod[source_id] = {
                    **policy,
                    "source_id": source_id,
                    "freshness_status": source_status,
                    "not_required_for_paper_eod": True,
                    "source_diagnostic": dict(source),
                }
                continue
            blockers.append(f"freshness_lane_source_status_unknown:{source_id}")
        elif source_status not in PAPER_EOD_ALLOWED_DEGRADED_SOURCE_STATUSES:
            blockers.append(f"freshness_lane_noncurrent_source_blocked:{source_id}:{source_status}")
        else:
            source = source_by_id[source_id]
            candidate_policy = _candidate_non_eod_policy(
                source_id=source_id,
                source_status=source_status,
                source=source,
            )
            if candidate_policy is not None:
                not_required_for_paper_eod[source_id] = {
                    **candidate_policy,
                    "source_id": source_id,
                    "freshness_status": source_status,
                    "candidate_only": True,
                    "reason": source.get("reason"),
                    "not_required_for_paper_eod": True,
                    "source_diagnostic": dict(source),
                }
                continue
            # 已登記的 candidate source 必須先通過具名 policy；即使 aggregate
            # 帶有同名 warning，也不能退回一般 warning allowlist。
            if source_id in PAPER_EOD_NON_REQUIRED_CANDIDATE_POLICIES:
                blockers.append(
                    f"freshness_lane_noncurrent_source_unattributed:{source_id}:{source_status}"
                )
                continue
            if source_id in warning_sources:
                continue
            blockers.append(f"freshness_lane_noncurrent_source_unattributed:{source_id}:{source_status}")
    projection["non_current_sources"] = non_current_sources
    projection["not_required_for_paper_eod"] = not_required_for_paper_eod
    projection["lane_blockers"] = list(blockers)
    projection["status"] = "degraded_non_eod_only" if not blockers else "blocked"
    return projection, blockers, ignored_warnings


def inspect_dependency(
    *,
    data_root: str | Path = DEFAULT_DATA_ROOT,
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
    db_path: str | Path = DEFAULT_DB_PATH,
    calendar_cache_path: str | Path = DEFAULT_CALENDAR_CACHE_ROOT,
    observed_at: datetime | None = None,
) -> dict[str, object]:
    """回傳可重驗的 gate 結果；所有輸入皆固定為 read-only observation。

    只有 exact target date 的 hash-bound 官方 annual cache 明確標示休市時，
    才會在讀取 quick/freshness/market source 前回傳 Paper no-op。開市、cache
    缺失、過期或驗證失敗都保留既有 required-source gate。
    """

    observed = (observed_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    taipei_now = observed.astimezone(TAIPEI)
    data_root_path = Path(data_root).expanduser().resolve()
    output_root_path = Path(output_root).expanduser().resolve()
    db_path_obj = Path(db_path).expanduser().resolve()
    target = taipei_now.date()
    quick_path = output_root_path / "scheduled" / "data_update_quick" / "latest_status.json"
    freshness_path = output_root_path / "scheduled" / "data_freshness" / "latest_status.json"
    blockers: list[str] = []
    warnings: list[str] = []
    freshness_lane_projection: dict[str, object] | None = None
    freshness_lane_ignored_warnings: list[str] = []

    result: dict[str, object] = {
        "schema_version": "paper-execution-dependency-gate.v1",
        "observed_at": observed.isoformat(timespec="seconds"),
        "observed_taipei_at": taipei_now.isoformat(timespec="seconds"),
        "decision_timezone": "Asia/Taipei",
        "target_date": target.isoformat(),
        "data_root": str(data_root_path),
        "output_root": str(output_root_path),
        "market_db": str(db_path_obj),
        "query_only": True,
        "source_db_written": False,
        "source_files_written": False,
        "formal_credit": False,
        "broker_order_allowed": False,
    }

    if target.weekday() >= 5:
        result.update({"status": "not_trading_day", "ready": True, "reason": "taipei_weekend"})
        return result

    calendar_evidence = _verified_closed_calendar_evidence(
        target=target,
        observed=observed,
        cache_path=calendar_cache_path,
    )
    if calendar_evidence is not None:
        result.update(
            {
                "status": "not_trading_day",
                "ready": True,
                "reason": "twse_holiday_schedule_cache_closed",
                "adapter_noop": True,
                "calendar_evidence": calendar_evidence,
                "blockers": [],
                "warnings": [],
            }
        )
        return result

    quick, quick_hash, quick_error = _read_json(quick_path)
    freshness, freshness_hash, freshness_error = _read_json(freshness_path)
    result["quick_update_status_path"] = str(quick_path)
    result["freshness_status_path"] = str(freshness_path)
    result["quick_update_status_hash"] = quick_hash
    result["freshness_status_hash"] = freshness_hash
    if quick_error:
        blockers.append(f"quick_update_receipt_unavailable:{quick_error}")
    if freshness_error:
        blockers.append(f"freshness_receipt_unavailable:{freshness_error}")

    quick_no_data = False
    if quick is not None:
        quick_status = str(quick.get("status") or "").lower()
        quick_target = _parse_date(quick.get("end_date"))
        quick_checked_at, quick_checked_error = _parse_aware_timestamp(quick.get("checked_at"))
        quick_checked = (
            quick_checked_at.astimezone(TAIPEI).date()
            if quick_checked_at is not None
            else None
        )
        result["quick_update_status"] = quick_status
        result["quick_update_end_date"] = quick_target.isoformat() if quick_target else None
        result["quick_update_checked_date"] = quick_checked.isoformat() if quick_checked else None
        result["quick_update_checked_at"] = (
            quick_checked_at.isoformat(timespec="seconds") if quick_checked_at else None
        )
        twse_step = _step(quick, "update_twse_daily_prices")
        sync_step = _step(quick, "sync_daily_prices_to_sqlite")
        twse_result = twse_step.get("result", {}) if twse_step else {}
        if not isinstance(twse_result, Mapping):
            twse_result = {}
        quick_no_data = target.strftime("%Y-%m-%d") in {
            str(value)[:10]
            for value in twse_result.get("no_data_skipped_dates", [])
            if value is not None
        }
        if quick_status not in {"passed", "passed_with_warnings"}:
            blockers.append(f"quick_update_status_not_success:{quick_status or 'missing'}")
        if quick_target is None or quick_target != target:
            blockers.append("quick_update_receipt_data_date_not_target")
        if quick_checked is None or quick_checked != target:
            blockers.append("quick_update_receipt_checked_date_not_target")
        if quick_checked_error is not None:
            blockers.append(f"quick_update_receipt_checked_at_invalid:{quick_checked_error}")
        elif quick_checked_at is not None and quick_checked_at > observed:
            blockers.append("quick_update_receipt_checked_at_after_observed")
        if not isinstance(twse_step, Mapping) or twse_step.get("status") != "passed":
            blockers.append("quick_update_twse_step_not_passed")
        if not isinstance(sync_step, Mapping) or sync_step.get("status") != "passed":
            blockers.append("quick_update_sqlite_sync_step_not_passed")

    if freshness is not None:
        freshness_status = str(freshness.get("status") or "").lower()
        raw_checks = freshness.get("checks")
        checks: Mapping[str, object] = raw_checks if isinstance(raw_checks, Mapping) else {}
        freshness_checked_at, freshness_checked_error = _parse_aware_timestamp(
            freshness.get("checked_at")
        )
        freshness_checked_date = (
            freshness_checked_at.astimezone(TAIPEI).date()
            if freshness_checked_at is not None
            else None
        )
        freshness_target = _parse_date(checks.get("daily_prices_latest_date"))
        result["freshness_status"] = freshness_status
        result["freshness_checked_date"] = (
            freshness_checked_date.isoformat() if freshness_checked_date else None
        )
        result["freshness_checked_at"] = (
            freshness_checked_at.isoformat(timespec="seconds") if freshness_checked_at else None
        )
        result["freshness_daily_prices_date"] = (
            freshness_target.isoformat() if freshness_target else None
        )
        (
            freshness_lane_projection,
            freshness_lane_blockers,
            freshness_lane_ignored_warnings,
        ) = _paper_eod_freshness_projection(freshness, target=target)
        result["freshness_lane"] = freshness_lane_projection
        blockers.extend(freshness_lane_blockers)
        if freshness_status != "passed":
            blockers.append(f"freshness_status_not_passed:{freshness_status or 'missing'}")
        if freshness_target is None or freshness_target != target:
            blockers.append("freshness_receipt_daily_prices_not_target")
        if _parse_date(checks.get("data_update_quick_checked_date")) != target:
            blockers.append("freshness_receipt_update_date_not_target")
        if freshness_checked_error is not None:
            blockers.append(f"freshness_receipt_checked_at_invalid:{freshness_checked_error}")
        elif freshness_checked_at is not None and freshness_checked_at > observed:
            blockers.append("freshness_receipt_checked_at_after_observed")
        if freshness_checked_date is None or freshness_checked_date != target:
            blockers.append("freshness_receipt_checked_date_not_target")

    market, market_error = _latest_market_rows(db_path_obj, target)
    if market_error:
        blockers.append(market_error)
    if market is not None:
        result["market_observation"] = market
        if not bool(market.get("ready")):
            blockers.append("daily_prices_target_open_rows_unavailable")

    source_files: list[dict[str, object]] = []
    source_readback: dict[str, object] = {}
    for market_name, source_path in (
        ("twse", data_root_path / "daily_price" / f"{target:%Y%m%d}.csv"),
        ("tpex", data_root_path / "daily_price_tpex" / f"{target:%Y%m%d}.csv"),
    ):
        if not source_path.is_file():
            blockers.append(f"source_file_missing:{source_path}")
            continue
        observation, error, raw = _file_observation_with_raw(source_path)
        if error:
            blockers.append(error)
            continue
        if observation is not None:
            source_files.append(observation)
        rows, readback_observation, readback_error = _read_source_open_rows(
            source_path,
            target=target,
            raw=raw,
        )
        if readback_observation is not None:
            source_readback[market_name] = readback_observation
        if readback_error is not None:
            blockers.append(readback_error)
        readback, readback_blockers = _source_db_readback(
            db_path_obj,
            target=target,
            source_rows=rows,
            market_name=market_name,
        )
        previous_readback = source_readback.get(market_name)
        previous_mapping: Mapping[str, object] = (
            previous_readback if isinstance(previous_readback, Mapping) else {}
        )
        source_readback[market_name] = {**dict(previous_mapping), **readback}
        blockers.extend(readback_blockers)
    result["source_files"] = source_files
    result["source_db_readback"] = source_readback
    result["source_hash"] = _sha256_bytes(
        _canonical_json([{key: item[key] for key in ("path", "size_bytes", "mtime_ns", "sha256")} for item in source_files]).encode("utf-8")
    ) if len(source_files) == 2 else None
    if len(source_files) != 2:
        blockers.append("source_file_set_incomplete")

    try:
        result["free_bytes"] = int(shutil.disk_usage(data_root_path).free)
    except OSError as error:
        warnings.append(f"disk_usage_unavailable:{type(error).__name__}")

    if quick_no_data:
        # The updater explicitly recorded that the official source had no
        # rows for this date. This is a scheduler no-op, never a successful
        # market session. Only the expected missing-date observations may be
        # tolerated; DB/schema/receipt integrity failures remain blockers.
        quick_status = str((quick or {}).get("status") or "").lower()
        quick_steps_valid = all(
            _step_passed(quick, name)
            for name in ("update_twse_daily_prices", "sync_daily_prices_to_sqlite")
        )
        no_data_tolerated = (
            "quick_update_receipt_data_date_not_target",
            "quick_update_receipt_checked_date_not_target",
            "freshness_receipt_daily_prices_not_target",
            "freshness_receipt_update_date_not_target",
            "daily_prices_target_open_rows_unavailable",
            "source_file_missing:",
            "source_file_set_incomplete",
        )
        unexpected_blockers = [
            blocker
            for blocker in blockers
            if not any(str(blocker).startswith(marker) for marker in no_data_tolerated)
        ]
        if quick_status in {"passed", "passed_with_warnings"} and quick_steps_valid and not unexpected_blockers:
            warnings.append("quick_update_recorded_official_no_data_for_target")
            result.update(
                {
                    "status": "official_no_data",
                    "ready": True,
                    "reason": "updater_explicit_no_data",
                    "adapter_noop": True,
                }
            )
            result["warnings"] = warnings
            result["blockers"] = blockers
            return result

    freshness_lane_ready_with_warnings = (
        freshness_lane_projection is not None
        and freshness_lane_projection.get("status") == "degraded_non_eod_only"
        and not quick_no_data
    )
    if freshness_lane_ready_with_warnings:
        blockers = [
            blocker
            for blocker in blockers
            if blocker != "freshness_status_not_passed:degraded"
        ]
        warnings.extend(
            f"paper_eod_ignored_non_eod_freshness:{warning}"
            for warning in freshness_lane_ignored_warnings
        )

    if blockers:
        if freshness_lane_projection is not None and freshness_lane_ready_with_warnings:
            freshness_lane_projection["gate_eligible"] = False
            freshness_lane_projection["status"] = "eligible_but_other_blockers"
            freshness_lane_projection["gate_blockers"] = list(blockers)
        result.update({"status": "blocked", "ready": False})
    elif freshness_lane_ready_with_warnings:
        if freshness_lane_projection is not None:
            freshness_lane_projection["gate_eligible"] = True
            freshness_lane_projection["status"] = "ready_with_warnings"
            freshness_lane_projection["gate_blockers"] = []
        result.update(
            {
                "status": "ready_with_warnings",
                "ready": True,
                "reason": "same_date_update_freshness_db_and_source_hash_with_non_eod_warnings",
            }
        )
    else:
        result.update({"status": "ready", "ready": True, "reason": "same_date_update_freshness_db_and_source_hash"})
    result["warnings"] = warnings
    result["blockers"] = blockers
    return result


def _write_output(payload: Mapping[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--output", type=Path, help="明確指定單次 JSON 報告路徑。")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    _configure_utf8_stdio()
    args = build_parser().parse_args(argv)
    payload = inspect_dependency(
        data_root=args.data_root,
        output_root=args.output_root,
        db_path=args.db_path,
    )
    if args.output is not None:
        _write_output(payload, args.output)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if bool(payload.get("ready")) else 2


def _configure_utf8_stdio() -> None:
    """讓 Windows 非 UTF-8 主控台也能安全顯示繁中 help/JSON。"""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    raise SystemExit(main())
