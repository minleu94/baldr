"""建立有界、唯讀且明確標為 current-observed 的來源契約。"""

from __future__ import annotations

import csv
import hashlib
import json
import numbers
import sqlite3
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

import pandas as pd

from app_module.decision_market_frame import DecisionMarketFrameLoader
from app_module.exceptions import BacktestCancelledError


SCHEMA_VERSION = "current-observed-source-contract.v1"
ROWSET_HASH_VERSION = "decision-market-frame-rowset.v1"
TAIPEI = ZoneInfo("Asia/Taipei")
MAX_WINDOW_TRADING_DAYS = 60
MAX_SYMBOLS = 5000
MAX_FEATURE_SPECS = 50
MAX_CLASSIFICATION_CSV_BYTES = 32 * 1024 * 1024
_BASE_REQUIRED_COLUMNS = ("日期", "證券代號", "收盤價", "漲跌價差", "成交股數")


def build_current_observed_source_contract(
    database_path: str | Path,
    *,
    decision_cutoff: datetime,
    as_of_date: date,
    window_trading_days: int,
    symbols: Iterable[str] | None = None,
    source_ref: str | None = None,
    expected_source_pin: Mapping[str, Any] | None = None,
    expected_scope_identity: str | None = None,
    expected_rowset_sha256: str | None = None,
    feature_specs: Sequence[Mapping[str, Any]] = (),
    company_classification_csv: str | Path | None = None,
    benchmark_evidence: Mapping[str, Any] | None = None,
    cancel_callback: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """只讀指定 SQLite 來源的有限交易日窗口並回傳研究 manifest。

    ``symbols=None`` 表示呼叫者沒有提供母體分母；回傳只描述實際讀到的
    rowset，不推論全市場完整性。價格日期沒有可得時間時仍可作 current-only
    研究讀取，但不會因此被視為歷史 PIT、訓練輸入或已發布快照。
    """

    if not isinstance(decision_cutoff, datetime):
        raise ValueError("decision_cutoff 必須是含時區的 datetime。")
    if decision_cutoff.tzinfo is None or decision_cutoff.utcoffset() is None:
        raise ValueError("decision_cutoff 必須明示時區。")
    if isinstance(as_of_date, datetime) or not isinstance(as_of_date, date):
        raise ValueError("as_of_date 必須是日期。")
    if (
        isinstance(window_trading_days, bool)
        or not isinstance(window_trading_days, int)
        or not 1 <= window_trading_days <= MAX_WINDOW_TRADING_DAYS
    ):
        raise ValueError(
            f"window_trading_days 必須介於 1 至 {MAX_WINDOW_TRADING_DAYS}；"
            "此為單次讀取上限，不代表任何指標暖機門檻。"
        )
    normalized_features = _normalize_feature_specs(
        feature_specs, int(window_trading_days)
    )
    normalized_symbols, duplicate_input_symbols = _normalize_symbols(symbols)
    scope_identity = _scope_identity(normalized_symbols)

    path = Path(database_path).expanduser().resolve()
    reference = str(source_ref or f"sqlite:{path}#daily_prices")
    started_at = datetime.now(timezone.utc)
    cutoff_taipei = decision_cutoff.astimezone(TAIPEI)
    cutoff_utc = decision_cutoff.astimezone(timezone.utc)
    now_utc = datetime.now(timezone.utc)
    base: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "rowset_hash_version": ROWSET_HASH_VERSION,
        "status": "rejected",
        "read_started_at": started_at.isoformat(),
        "request": {
            "source_ref": reference,
            "database_path": str(path),
            "decision_cutoff": decision_cutoff.isoformat(),
            "decision_cutoff_utc": cutoff_utc.isoformat(),
            "cutoff_taipei_date": cutoff_taipei.date().isoformat(),
            "as_of_date": as_of_date.isoformat(),
            "window_trading_days": int(window_trading_days),
            "window_limit_trading_days": MAX_WINDOW_TRADING_DAYS,
            "window_basis": "來源表最近 N 個不晚於 as_of_date 的不同交易日",
            "feature_spec_state": "caller_declared" if normalized_features else "unknown",
        },
        "source": {"reference": reference, "table": "daily_prices", "state": "not_read"},
        "scope": _scope_payload(normalized_symbols, duplicate_input_symbols, scope_identity),
        "features": _feature_payload(normalized_features, ()),
        "company_classification": _unknown_classification(),
        "benchmark": _benchmark_payload(benchmark_evidence, as_of_date),
        "research_only": True,
        "historical_pit_eligible": False,
        "formal_training_eligible": False,
        "formal_oos_allowed": False,
        "published_snapshot": False,
        "blockers": [],
    }

    if cutoff_taipei.date() != as_of_date:
        return _reject(
            base,
            "as_of_date_mismatch",
            "as_of_date 必須等於 decision_cutoff 轉為 Asia/Taipei 後的日期。",
        )
    if cutoff_utc > now_utc or as_of_date > now_utc.astimezone(TAIPEI).date():
        return _reject(base, "future_as_of", "不接受晚於目前時間的決策 cutoff／日期。")
    if normalized_symbols is not None and len(normalized_symbols) > MAX_SYMBOLS:
        raise ValueError(f"symbols 最多 {MAX_SYMBOLS} 個。")
    if not path.is_file():
        return _reject(base, "source_database_missing", "來源 SQLite 檔案不存在。")

    stat_before = _file_identity(path)
    try:
        schema_before = _read_daily_prices_schema(path)
    except (OSError, sqlite3.Error) as exc:
        return _reject(
            base,
            "source_schema_read_failed",
            f"無法唯讀檢查 daily_prices schema：{type(exc).__name__}。",
        )
    schema_hash = _stable_hash(schema_before)
    base_columns = {item["name"] for item in schema_before}
    missing_required = [name for name in _BASE_REQUIRED_COLUMNS if name not in base_columns]
    actual_pin = {**stat_before, "schema_sha256": schema_hash}
    base["source"].update(
        {
            "state": "schema_checked",
            "schema": {"table": "daily_prices", "columns": schema_before, "sha256": schema_hash},
            "file_identity_before": stat_before,
            "expected_pin_state": "not_provided",
            "read_only": True,
        }
    )
    if missing_required:
        return _reject(
            base,
            "required_columns_missing",
            "daily_prices 缺少 reader 必要欄位：" + ", ".join(missing_required),
        )
    pin_mismatch = _source_pin_mismatch(expected_source_pin, actual_pin)
    base["source"]["expected_pin_state"] = "matched" if expected_source_pin else "not_provided"
    if pin_mismatch:
        base["source"]["expected_pin_state"] = "mismatch"
        return _reject(base, "source_pin_mismatch", pin_mismatch)
    if expected_scope_identity and expected_scope_identity != scope_identity:
        return _reject(
            base,
            "scope_identity_mismatch",
            "明示 symbols 的 scope identity 與預期 pin 不相符。",
        )

    _checkpoint(cancel_callback)
    loader = DecisionMarketFrameLoader(path)
    try:
        frame = loader.load(
            as_of_date,
            window_trading_days,
            cancel_callback=cancel_callback,
            include_source_timing=True,
            raise_sql_errors=True,
        )
    except BacktestCancelledError:
        raise
    except (sqlite3.Error, pd.errors.DatabaseError) as exc:
        base["source"]["query_error_type"] = type(exc).__name__
        return _reject(
            base,
            "source_query_failed",
            f"daily_prices 有界查詢失敗：{type(exc).__name__}。",
        )
    _checkpoint(cancel_callback)

    read_columns = tuple(str(column) for column in frame.columns)
    requested_set = set(normalized_symbols or ())
    content_rows: list[str] = []
    cutoff_rows: list[str] = []
    window_by_symbol: dict[str, list[date]] = defaultdict(list)
    rows_by_symbol: Counter[str] = Counter()
    date_key_counts: Counter[tuple[str, str]] = Counter()
    availability_counts: Counter[str] = Counter()
    observed_at_counts: Counter[str] = Counter()
    cutoff_screened_counts: Counter[str] = Counter()
    invalid_market_date_rows = 0
    future_market_date_rows = 0
    missing_code_rows = 0
    outside_scope_rows = 0
    late_availability_rows = 0
    late_observation_rows = 0
    source_availability_column_present = "available_at" in base_columns
    source_observed_at_column_present = "observed_at" in base_columns

    columns = list(read_columns)
    for index, values in enumerate(frame.itertuples(index=False, name=None)):
        if index % 256 == 0:
            _checkpoint(cancel_callback)
        row = dict(zip(columns, values))
        raw_code = row.get("證券代號")
        code = "" if _is_missing(raw_code) else str(raw_code).strip()
        if not code:
            missing_code_rows += 1
            continue
        if normalized_symbols is not None and code not in requested_set:
            outside_scope_rows += 1
            continue
        raw_date = row.get("日期")
        parsed_date = DecisionMarketFrameLoader._parse_date(raw_date)
        if parsed_date is None:
            invalid_market_date_rows += 1
        elif parsed_date > as_of_date:
            future_market_date_rows += 1
        else:
            window_by_symbol[code].append(parsed_date)
        rows_by_symbol[code] += 1
        date_key = parsed_date.isoformat() if parsed_date is not None else str(raw_date)
        date_key_counts[(code, date_key)] += 1
        row_json = _canonical_row_json(row, read_columns)
        content_rows.append(row_json)

        availability_state, available_at = _parse_aware_timestamp(row.get("available_at"))
        observation_state, observed_at = _parse_aware_timestamp(row.get("observed_at"))
        availability_counts[availability_state] += 1
        observed_at_counts[observation_state] += 1
        future_available = (
            available_at is not None and available_at > cutoff_utc
        )
        future_observed = observed_at is not None and observed_at > cutoff_utc
        if future_available:
            late_availability_rows += 1
        if future_observed:
            late_observation_rows += 1
        market_date_valid = parsed_date is not None and parsed_date <= as_of_date
        cutoff_screened = (
            market_date_valid
            and availability_state == "known"
            and available_at is not None
            and available_at <= cutoff_utc
            and observation_state != "invalid"
            and not future_observed
        )
        if cutoff_screened:
            cutoff_rows.append(row_json)
            cutoff_screened_counts[code] += 1

    _checkpoint(cancel_callback)
    file_after = _file_identity(path)
    try:
        schema_after = _read_daily_prices_schema(path)
    except (OSError, sqlite3.Error):
        schema_after = []
    stable_source, shm_mtime_changed = _source_identities_stable(stat_before, file_after)
    stable_source = stable_source and schema_before == schema_after
    identity_differences = _source_identity_differences(stat_before, file_after)
    base["source"].update(
        {
            "file_identity_after": file_after,
            "schema_sha256_after": _stable_hash(schema_after) if schema_after else None,
            "identity_differences": identity_differences,
            "shm_mtime_changed_during_read": shm_mtime_changed,
            "shm_is_shared_index_metadata_not_content_identity": True,
        }
    )
    if not stable_source:
        return _reject(
            base,
            "source_changed_during_read",
            "唯讀期間來源檔案識別或 schema 改變"
            + ("：" + ", ".join(identity_differences) if identity_differences else "：schema hash 改變")
            + "；本次結果不視為穩定快照。",
        )

    duplicate_rows = sum(count - 1 for count in date_key_counts.values() if count > 1)
    requested_codes = normalized_symbols or tuple(sorted(rows_by_symbol))
    missing_symbols = (
        [code for code in normalized_symbols if rows_by_symbol.get(code, 0) == 0]
        if normalized_symbols is not None
        else []
    )
    all_requested_observed = not missing_symbols and normalized_symbols is not None
    observed_rowset_hash = _rowset_hash(read_columns, content_rows, scope_identity)
    cutoff_rowset_hash = _rowset_hash(read_columns, cutoff_rows, scope_identity)
    expected_hash_mismatch = bool(
        expected_rowset_sha256 and expected_rowset_sha256 != observed_rowset_hash
    )

    stock_windows = []
    for code in requested_codes:
        dates = window_by_symbol.get(code, [])
        stock_windows.append(
            {
                "symbol": code,
                "row_count": rows_by_symbol.get(code, 0),
                "distinct_market_dates": len(set(dates)),
                "first_market_date": min(dates).isoformat() if dates else None,
                "last_market_date": max(dates).isoformat() if dates else None,
                "cutoff_screened_rows": cutoff_screened_counts.get(code, 0),
                "window_coverage_state": "observed_rows_only; expected per-symbol calendar unknown",
            }
        )

    market_dates = sorted({item for dates in window_by_symbol.values() for item in dates})
    blockers: list[dict[str, str]] = []
    if missing_symbols:
        blockers.append(_issue("cohort_symbols_missing", "有明示股票未在讀取窗口出現。"))
    if duplicate_rows:
        blockers.append(_issue("duplicate_symbol_market_dates", "來源窗口含重複股票／交易日列。"))
    if invalid_market_date_rows or future_market_date_rows or missing_code_rows:
        blockers.append(_issue("invalid_market_rows", "來源窗口包含無效日期、未來日期或空股票代碼列。"))
    if late_availability_rows:
        blockers.append(_issue("available_after_cutoff", "晚於 cutoff 的來源列未納入 cutoff-screened rowset。"))
    if late_observation_rows:
        blockers.append(_issue("observed_after_cutoff", "晚於 cutoff 的觀測列未納入 cutoff-screened rowset。"))
    if availability_counts.get("invalid", 0):
        blockers.append(_issue("invalid_available_at", "available_at 含無效或缺少時區的時間值。"))
    if observed_at_counts.get("invalid", 0):
        blockers.append(_issue("invalid_observed_at", "observed_at 含無效或缺少時區的時間值。"))
    if frame.empty:
        blockers.append(_issue("empty_window", "指定日期窗口沒有可讀列。"))
    if expected_hash_mismatch:
        return _reject(
            base,
            "rowset_pin_mismatch",
            "實際 scoped rowset hash 與預期 pin 不相符。",
        )
    if expected_rowset_sha256:
        base["source"]["expected_rowset_pin_state"] = "matched"
    else:
        base["source"]["expected_rowset_pin_state"] = "not_provided"

    features = _feature_payload(normalized_features, read_columns)
    if normalized_symbols is None:
        scope_state = "unknown_denominator"
    else:
        scope_state = "declared_cohort"
    base.update(
        {
            "status": "partial" if blockers else "observed",
            "read_finished_at": datetime.now(timezone.utc).isoformat(),
            "request": {
                **base["request"],
                "market_window_first_date": market_dates[0].isoformat() if market_dates else None,
                "market_window_last_date": market_dates[-1].isoformat() if market_dates else None,
                "market_window_distinct_dates": len(market_dates),
            },
            "source": {
                **base["source"],
                "state": "stable_read",
                "file_identity_after": file_after,
                "stable_during_read": stable_source,
                "file_identity_is_not_content_identity": True,
                "shm_mtime_changed_during_read": shm_mtime_changed,
                "rowset": {
                    "reader_rows_before_symbol_filter": int(len(frame)),
                    "scoped_rows": len(content_rows),
                    "duplicate_symbol_market_date_rows": duplicate_rows,
                    "rows_with_invalid_market_date": invalid_market_date_rows,
                    "rows_with_future_market_date": future_market_date_rows,
                    "rows_with_missing_symbol": missing_code_rows,
                    "rows_outside_requested_scope": outside_scope_rows,
                    "content_sha256": observed_rowset_hash,
                    "cutoff_screened_rows": len(cutoff_rows),
                    "cutoff_screened_sha256": cutoff_rowset_hash,
                    "canonicalization_version": ROWSET_HASH_VERSION,
                },
                "source_time_fields": {
                    "available_at_column_present": source_availability_column_present,
                    "observed_at_column_present": source_observed_at_column_present,
                    "available_at_counts": _time_counts_payload(availability_counts),
                    "observed_at_counts": _time_counts_payload(observed_at_counts),
                    "observed_at_is_official_availability": False,
                    "available_at_source_semantics_verified": False,
                    "cutoff_screen_is_historical_pit_proof": False,
                },
                "expected_rowset_pin_state": base["source"].get("expected_rowset_pin_state", "not_provided"),
            },
            "scope": {
                **base["scope"],
                "state": scope_state,
                "denominator_known": normalized_symbols is not None,
                "denominator": len(normalized_symbols) if normalized_symbols is not None else None,
                "missing_symbols": missing_symbols,
                "all_requested_symbols_observed": all_requested_observed,
                "market_universe_completeness": "unknown",
                "outside_requested_scope_rows": outside_scope_rows,
            },
            "stock_windows": stock_windows,
            "features": features,
            "company_classification": _read_current_classification(
                company_classification_csv,
                set(normalized_symbols) if normalized_symbols is not None else None,
                as_of_date,
                cancel_callback,
            )
            if company_classification_csv is not None
            else _unknown_classification(),
            "benchmark": _benchmark_payload(benchmark_evidence, as_of_date),
            "availability": {
                "state": "known_for_some_rows"
                if availability_counts.get("known", 0)
                else "unknown",
                "explicit_source_available_at_required_for_cutoff_screen": True,
                "official_availability_verified": False,
                "historical_pit_eligible": False,
                "note": "market date 本身不證明 cutoff 前可用；缺少時鐘仍可作 current-observed 研究讀取。",
            },
            "blockers": blockers,
        }
    )
    return base


def _normalize_symbols(symbols: Iterable[str] | None) -> tuple[tuple[str, ...] | None, list[str]]:
    if symbols is None:
        return None, []
    raw = [str(item).strip() for item in symbols]
    if not raw or any(not item for item in raw):
        raise ValueError("明示 symbols 時不可為空或含空代碼。")
    counts = Counter(raw)
    duplicates = sorted(code for code, count in counts.items() if count > 1)
    normalized = tuple(sorted(counts))
    if len(normalized) > MAX_SYMBOLS:
        raise ValueError(f"symbols 最多 {MAX_SYMBOLS} 個。")
    return normalized, duplicates


def _scope_identity(symbols: tuple[str, ...] | None) -> str:
    if symbols is None:
        return "unknown"
    payload = json.dumps(symbols, ensure_ascii=False, separators=(",", ":"))
    return "symbols-sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _scope_payload(
    symbols: tuple[str, ...] | None,
    duplicates: Sequence[str],
    identity: str,
) -> dict[str, Any]:
    return {
        "identity": identity,
        "symbols": list(symbols) if symbols is not None else None,
        "denominator_known": symbols is not None,
        "denominator": len(symbols) if symbols is not None else None,
        "duplicate_symbols_in_request": list(duplicates),
        "market_universe_completeness": "unknown",
    }


def _normalize_feature_specs(
    specs: Sequence[Mapping[str, Any]], window_trading_days: int
) -> list[dict[str, Any]]:
    if len(specs) > MAX_FEATURE_SPECS:
        raise ValueError(f"feature_specs 最多 {MAX_FEATURE_SPECS} 項。")
    normalized: list[dict[str, Any]] = []
    for item in specs:
        name = str(item.get("name", "")).strip()
        table = str(item.get("source_table", "")).strip()
        columns = tuple(str(value).strip() for value in item.get("columns", ()))
        feature_window = item.get("window_sessions")
        if not name or not table or not columns or any(not value for value in columns):
            raise ValueError("feature spec 必須明示 name、source_table 與 columns。")
        if not isinstance(feature_window, int) or not 1 <= feature_window <= window_trading_days:
            raise ValueError("feature spec window_sessions 必須在讀取窗口內明示。")
        raw_warmup = item.get("warmup_sessions")
        if raw_warmup is not None and (
            not isinstance(raw_warmup, int) or raw_warmup <= 0
        ):
            raise ValueError("warmup_sessions 若提供必須是正整數。")
        normalized.append(
            {
                "name": name,
                "source_table": table,
                "columns": list(columns),
                "window_sessions": feature_window,
                "warmup_sessions": raw_warmup,
                "version": item.get("version"),
                "unit": item.get("unit"),
            }
        )
    return normalized


def _feature_payload(
    specs: Sequence[Mapping[str, Any]], read_columns: Sequence[str]
) -> dict[str, Any]:
    read_set = set(read_columns)
    items = []
    for spec in specs:
        missing = [column for column in spec["columns"] if column not in read_set]
        warmup = spec["warmup_sessions"]
        items.append(
            {
                **spec,
                "requested_columns_read": not missing and spec["source_table"] == "daily_prices",
                "requested_columns_not_read": missing,
                "computed": False,
                "warmup_spec": {
                    "state": "caller_declared_unverified" if warmup is not None else "unknown",
                    "sessions": warmup,
                    "basis": "caller declaration only" if warmup is not None else None,
                    "warmup_qualified": False,
                },
            }
        )
    return {"state": "caller_declared" if specs else "unknown", "items": items}


def _file_identity(path: Path) -> dict[str, Any]:
    def identity(item: Path) -> dict[str, Any] | None:
        try:
            stat = item.stat()
        except FileNotFoundError:
            return None
        return {
            "path": str(item.resolve()),
            "device": int(stat.st_dev),
            "inode": int(stat.st_ino),
            "size_bytes": int(stat.st_size),
            "mtime_ns": int(stat.st_mtime_ns),
        }

    main = identity(path)
    if main is None:
        raise FileNotFoundError(path)
    return {
        "path": str(path.resolve()),
        "device": main["device"],
        "inode": main["inode"],
        "size_bytes": main["size_bytes"],
        "mtime_ns": main["mtime_ns"],
        "wal": identity(Path(str(path) + "-wal")),
        "shm": identity(Path(str(path) + "-shm")),
    }


def _source_identities_stable(before: Mapping[str, Any], after: Mapping[str, Any]) -> tuple[bool, bool]:
    main_keys = ("path", "device", "inode", "size_bytes", "mtime_ns")
    main_stable = all(before.get(key) == after.get(key) for key in main_keys)
    wal_stable = before.get("wal") == after.get("wal")
    before_shm = before.get("shm")
    after_shm = after.get("shm")
    if before_shm is None or after_shm is None:
        shm_stable = before_shm is after_shm
        shm_mtime_changed = False
    else:
        shm_keys = ("path", "device", "inode", "size_bytes")
        shm_stable = all(before_shm.get(key) == after_shm.get(key) for key in shm_keys)
        shm_mtime_changed = before_shm.get("mtime_ns") != after_shm.get("mtime_ns")
    return main_stable and wal_stable and shm_stable, shm_mtime_changed


def _source_identity_differences(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> list[str]:
    differences = []
    for key in ("path", "device", "inode", "size_bytes", "mtime_ns"):
        if before.get(key) != after.get(key):
            differences.append(f"main.{key}")
    if before.get("wal") != after.get("wal"):
        differences.append("wal.identity")
    before_shm = before.get("shm")
    after_shm = after.get("shm")
    if before_shm is None or after_shm is None:
        if before_shm is not after_shm:
            differences.append("shm.presence")
    elif any(
        before_shm.get(key) != after_shm.get(key)
        for key in ("path", "device", "inode", "size_bytes")
    ):
        differences.append("shm.identity")
    return differences


def _read_daily_prices_schema(path: Path) -> list[dict[str, Any]]:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        rows = connection.execute('PRAGMA table_info("daily_prices")').fetchall()
    return [
        {
            "ordinal": int(row[0]),
            "name": str(row[1]),
            "type": str(row[2] or ""),
            "not_null": bool(row[3]),
            "default": None if row[4] is None else str(row[4]),
            "primary_key_order": int(row[5]),
        }
        for row in rows
    ]


def _source_pin_mismatch(
    expected: Mapping[str, Any] | None, actual: Mapping[str, Any]
) -> str | None:
    if expected is None:
        return None
    aliases = {"resolved_path": "path", "size": "size_bytes"}
    for raw_key, expected_value in expected.items():
        key = aliases.get(str(raw_key), str(raw_key))
        if key not in actual and key != "schema_sha256":
            return f"預期來源 pin 含不支援欄位：{raw_key}。"
        if key in {"shm", "wal"} and isinstance(expected_value, Mapping):
            expected_sidecar = {
                k: v
                for k, v in expected_value.items()
                if not (key == "shm" and k == "mtime_ns")
            }
            actual_sidecar = actual.get(key)
            if actual_sidecar is None or any(
                actual_sidecar.get(k) != v for k, v in expected_sidecar.items()
            ):
                return f"來源 pin 欄位 {key} 不相符。"
            continue
        if actual.get(key) != expected_value:
            return f"來源 pin 欄位 {raw_key} 不相符。"
    return None


def _canonical_value(value: Any) -> Any:
    if _is_missing(value):
        return None
    if isinstance(value, datetime):
        return {"datetime": value.isoformat()}
    if isinstance(value, date):
        return {"date": value.isoformat()}
    if isinstance(value, Decimal):
        return {"decimal": str(value)}
    if isinstance(value, bool):
        return value
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        # 僅用於穩定序列化 rowset；不是金融計算或金額轉換。
        return {"float_hex": float(value).hex()}  # numeric-boundary: dto
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    return str(value)


def _canonical_row_json(row: Mapping[str, Any], columns: Sequence[str]) -> str:
    values = [_canonical_value(row.get(column)) for column in columns]
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


def _rowset_hash(columns: Sequence[str], rows: Sequence[str], scope_identity: str) -> str:
    digest = hashlib.sha256()
    digest.update(ROWSET_HASH_VERSION.encode("ascii"))
    digest.update(b"\n")
    digest.update(scope_identity.encode("utf-8"))
    digest.update(b"\n")
    digest.update(json.dumps(list(columns), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    digest.update(b"\n")
    for row in sorted(rows):
        digest.update(row.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        result = pd.isna(value)
        return bool(result) if not hasattr(result, "__len__") else False
    except (TypeError, ValueError):
        return False


def _parse_aware_timestamp(value: Any) -> tuple[str, datetime | None]:
    if _is_missing(value) or not str(value).strip():
        return "unknown", None
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value).strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return "invalid", None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return "invalid", None
    return "known", parsed.astimezone(timezone.utc)


def _time_counts_payload(counts: Counter[str]) -> dict[str, int]:
    return {key: int(counts.get(key, 0)) for key in ("known", "unknown", "invalid")}


def _unknown_classification() -> dict[str, Any]:
    return {
        "state": "unknown",
        "membership_semantics": "current_only",
        "cutoff_qualified_rows": 0,
        "current_membership_used_for_historical_scope": False,
        "historical_pit_eligible": False,
        "source_available_at": "unknown",
        "rows": [],
    }


def _read_current_classification(
    source_path: str | Path,
    symbols: set[str] | None,
    as_of_date: date,
    cancel_callback: Callable[[], bool] | None,
) -> dict[str, Any]:
    path = Path(source_path).expanduser().resolve()
    if not path.is_file():
        return {**_unknown_classification(), "state": "rejected", "reason": "source_missing"}
    identity_before = _file_identity(path)
    if identity_before["size_bytes"] > MAX_CLASSIFICATION_CSV_BYTES:
        return {**_unknown_classification(), "state": "rejected", "reason": "source_exceeds_read_limit"}
    filtered_rows: list[dict[str, str | None]] = []
    counts: Counter[tuple[str, str]] = Counter()
    required = {"stock_id", "industry_category"}
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if not reader.fieldnames or not required.issubset(reader.fieldnames):
                return {
                    **_unknown_classification(),
                    "state": "rejected",
                    "reason": "required_columns_missing",
                }
            for index, source_row in enumerate(reader):
                if index % 256 == 0:
                    _checkpoint(cancel_callback)
                code = str(source_row.get("stock_id", "")).strip()
                if not code or (symbols is not None and code not in symbols):
                    continue
                row = {
                    key: (str(source_row.get(key, "")).strip() or None)
                    for key in ("stock_id", "industry_category", "stock_name", "type", "date", "download_time")
                }
                filtered_rows.append(row)
                counts[(code, str(row.get("date") or ""))] += 1
    except (OSError, UnicodeError, csv.Error) as exc:
        return {
            **_unknown_classification(),
            "state": "rejected",
            "reason": type(exc).__name__,
        }
    identity_after = _file_identity(path)
    if identity_before != identity_after:
        return {
            **_unknown_classification(),
            "state": "partial",
            "reason": "source_changed_during_read",
        }
    duplicate_count = sum(count - 1 for count in counts.values() if count > 1)
    date_after_cutoff = sum(
        1
        for row in filtered_rows
        if (parsed := _parse_source_date(row.get("date"))) is not None and parsed > as_of_date
    )
    filtered_rows.sort(key=lambda row: json.dumps(row, ensure_ascii=False, sort_keys=True))
    return {
        "state": "current_only_observed" if filtered_rows else "current_only_no_matching_rows",
        "source_ref": str(path),
        "file_identity": identity_before,
        "filtered_row_count": len(filtered_rows),
        "duplicate_stock_date_rows": duplicate_count,
        "rows_after_as_of_date": date_after_cutoff,
        "rowset_sha256": _stable_hash(filtered_rows),
        "rows": filtered_rows,
        "membership_semantics": "current_only",
        "cutoff_qualified_rows": 0,
        "current_membership_used_for_historical_scope": False,
        "historical_pit_eligible": False,
        "source_available_at": "unknown",
        "download_time_is_official_availability": False,
    }


def _parse_source_date(value: str | None) -> date | None:
    if not value:
        return None
    text = value.strip()
    for format_string in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, format_string).date()
        except ValueError:
            continue
    return None


def _benchmark_payload(
    evidence: Mapping[str, Any] | None, as_of_date: date
) -> dict[str, Any]:
    if evidence is None:
        return {"state": "unknown", "identity": None, "window": None, "verified": False}
    identity = str(evidence.get("identity", "")).strip()
    source_ref = str(evidence.get("source_ref", "")).strip()
    start = _parse_source_date(str(evidence.get("window_start", "")))
    end = _parse_source_date(str(evidence.get("window_end", "")))
    valid = bool(identity and source_ref and start and end and start <= end and end <= as_of_date)
    return {
        "state": "provided_unverified" if valid else "rejected_evidence",
        "identity": identity or None,
        "source_ref": source_ref or None,
        "window": {
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
        },
        "rowset_sha256": evidence.get("rowset_sha256"),
        "verified": False,
        "historical_pit_eligible": False,
    }


def _checkpoint(cancel_callback: Callable[[], bool] | None) -> None:
    if cancel_callback is not None and cancel_callback():
        raise BacktestCancelledError("current-observed 來源契約讀取已取消。")


def _issue(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _reject(contract: dict[str, Any], code: str, message: str) -> dict[str, Any]:
    contract["status"] = "rejected"
    contract["blockers"].append(_issue(code, message))
    contract["read_finished_at"] = datetime.now(timezone.utc).isoformat()
    return contract
