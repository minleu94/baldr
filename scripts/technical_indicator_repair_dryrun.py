#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""受控的 2026-05-20 technical-indicator repair dry-run。

這個腳本只讀 SQLite 與既有個股 CSV，將已核准的 canonical 5/20 row
在記憶體中 overlay，使用 TA-Lib 直接計算白名單指標，輸出可審閱的
old/new row manifest。它沒有 formal writer，也不會呼叫 legacy
``TechnicalIndicatorCalculator``（該 calculator 會對缺值 ffill/bfill）。

輸出只包含 target date 之後「已存在於 technical_indicators」的 row；
target 之前的 row 不會出現在更新計畫中。遇到 OHLC 缺值會切斷序列，
下一個有效 segment 重新 warm-up；warm-up、缺價、缺 daily row 的結果
一律保留 NULL。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sqlite3
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
import talib


ROOT = Path(__file__).resolve().parents[1]
TARGET_DATE = "20260520"
DEFAULT_DATA_ROOT = Path(os.environ.get("DATA_ROOT", "F:/Min/Python/Project/FA_Data"))
DEFAULT_OVERLAY = (
    ROOT
    / "output"
    / "qa"
    / "historical_price_spike_20260921"
    / "no_merged_v2"
    / "historical_price_spike_audit.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "output"
    / "qa"
    / "price_repair_20260921"
    / "technical_indicator_dryrun_20260520.json"
)

# 這是本事件的保守白名單。ATR 目前在 formal table 多為 NULL，且正常
# calculator path 沒有產生它；dry-run 不因 repair 事件新增 ATR 來源。
DEPENDENT_INDICATORS: tuple[str, ...] = (
    "SMA30",
    "DEMA30",
    "EMA30",
    "RSI",
    "MACD",
    "MACD_signal",
    "MACD_hist",
    "slowk",
    "slowd",
    "middleband",
    "upperband",
    "lowerband",
    "SAR",
    "TSF",
    "MA5",
    "MA10",
    "MA20",
    "MA60",
    "ADX",
)
OHLC_COLUMNS = ("open", "high", "low", "close")
CANONICAL_FIELDS = {
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume_shares",
    "turnover": "turnover",
    "change": "change_value",
    "sign": "sign",
    "成交股數": "volume_shares",
    "成交筆數": "trade_count",
    "成交金額": "turnover",
    "開盤價": "open",
    "最高價": "high",
    "最低價": "low",
    "收盤價": "close",
    "漲跌(+/-)": "sign",
    "漲跌價差": "change_value",
    "最後揭示買價": "best_bid",
    "最後揭示買量": "best_bid_volume",
    "最後揭示賣價": "best_ask",
    "最後揭示賣量": "best_ask_volume",
    "本益比": "pe_ratio",
}
SOURCE_COLUMNS = tuple(
    key
    for key in (
        "成交股數",
        "成交筆數",
        "成交金額",
        "開盤價",
        "最高價",
        "最低價",
        "收盤價",
        "漲跌(+/-)",
        "漲跌價差",
        "最後揭示買價",
        "最後揭示買量",
        "最後揭示賣價",
        "最後揭示賣量",
        "本益比",
    )
)
TECHNICAL_ALIAS_COLUMNS = ("Date", "Open", "High", "Low", "Close", "Volume")

# Price repair owns these source fields.  The indicator dry-run records a
# narrow, target-date-only copy plan for them but never writes the fields.
# Keeping this mapping here makes the later apply step explicit and prevents
# it from guessing a source column from the indicator output.
SOURCE_FIELD_KEYS: dict[str, str] = {
    "Date": "date",
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Volume": "volume_shares",
    "證券名稱": "name",
    "成交股數": "volume_shares",
    "成交筆數": "trade_count",
    "成交金額": "turnover",
    "開盤價": "open",
    "最高價": "high",
    "最低價": "low",
    "收盤價": "close",
    "漲跌(+/-)": "sign",
    "漲跌": "sign",
    "涨跌": "sign",
    "漲跌價差": "change_value",
    "最後揭示買價": "best_bid",
    "最後揭示買量": "best_bid_volume",
    "最後揭示賣價": "best_ask",
    "最後揭示賣量": "best_ask_volume",
    "本益比": "pe_ratio",
}


class DryRunError(RuntimeError):
    """Raised when a dry-run input violates a safety boundary."""


def _quote(identifier: str) -> str:
    return '"' + str(identifier).replace('"', '""') + '"'


def _normalise_symbol(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text


def _date_key(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text or text.lower() in {"nan", "nat", "none"}:
        return ""
    digits = re.sub(r"[^0-9]", "", text)
    if len(digits) >= 8:
        candidate = digits[:8]
        if re.fullmatch(r"\d{8}", candidate):
            return candidate
    return ""


def _finite_number(value: Any) -> float:
    if value is None:
        return float("nan")
    try:
        if isinstance(value, str) and not value.strip():
            return float("nan")
        result = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return float("nan")
    return result if math.isfinite(result) else float("nan")


def _json_value(value: Any) -> Any:
    """Return JSON-safe value, never JSON NaN/Infinity."""
    if value is None:
        return None
    if isinstance(value, (np.generic,)):
        value = value.item()
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (np.integer, int)) and not isinstance(value, bool):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value) if math.isfinite(float(value)) else None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _hash_value(value: Any) -> str | None:
    value = _json_value(value)
    if value is None:
        return None
    if isinstance(value, float):
        return format(value, ".17g")
    return str(value)


def _values_equal(left: Any, right: Any) -> bool:
    left_json = _json_value(left)
    right_json = _json_value(right)
    if left_json is None or right_json is None:
        return left_json is None and right_json is None
    try:
        return Decimal(str(left_json)) == Decimal(str(right_json))
    except (InvalidOperation, ValueError):
        return str(left_json) == str(right_json)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _sha256_payload(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _normalise_overlay_row(item: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    """Normalize either the thin audit row or the approved price-plan source.

    The price repair owner may provide ``rows[].source`` with the complete
    quote/trade-count payload.  That source is preferred over the historical
    thin audit row, and no price-scale conversion is inferred here.
    """
    source_schema = "audit_canonical_daily_csv"
    source: Mapping[str, Any]
    if isinstance(item.get("source"), Mapping):
        source = item["source"]  # type: ignore[assignment]
        source_schema = "price_repair_plan_rows_source"
    elif isinstance(item.get("canonical_daily_csv"), Mapping):
        source = item["canonical_daily_csv"]  # type: ignore[assignment]
    elif isinstance(item.get("canonical"), Mapping):
        source = item["canonical"]  # type: ignore[assignment]
    elif isinstance(item.get("current_canonical_row"), Mapping):
        source = item["current_canonical_row"]  # type: ignore[assignment]
        source_schema = "root_cause_current_canonical_row"
    else:
        source = item

    # Some plan writers wrap the complete row in source.row.
    if isinstance(source.get("row"), Mapping):
        source = source["row"]  # type: ignore[assignment]

    aliases: dict[str, tuple[str, ...]] = {
        "symbol": ("symbol", "證券代號", "stock_code", "Code"),
        "date": ("date", "日期", "Date"),
        "open": ("open", "開盤價"),
        "high": ("high", "最高價"),
        "low": ("low", "最低價"),
        "close": ("close", "收盤價"),
        "volume_shares": ("volume_shares", "成交股數", "Volume"),
        "trade_count": ("trade_count", "成交筆數"),
        "turnover": ("turnover", "成交金額"),
        "change_value": ("change_value", "漲跌價差"),
        "sign": ("sign", "漲跌(+/-)", "漲跌", "涨跌"),
        "best_bid": ("best_bid", "最後揭示買價"),
        "best_bid_volume": ("best_bid_volume", "最後揭示買量"),
        "best_ask": ("best_ask", "最後揭示賣價"),
        "best_ask_volume": ("best_ask_volume", "最後揭示賣量"),
        "pe_ratio": ("pe_ratio", "本益比"),
    }
    normalized = dict(source)
    # Preserve the verified price-plan spelling for custody.  Normalized
    # aliases below are analysis inputs only; source_row_sha256 is computed
    # from this raw mapping and never from inferred aliases.
    normalized["_raw_source_row"] = dict(source)
    for target, candidates in aliases.items():
        for candidate in candidates:
            if candidate in source:
                normalized[target] = source[candidate]
                break
    if not normalized.get("symbol"):
        normalized["symbol"] = item.get("symbol") or item.get("證券代號")
    if not normalized.get("date"):
        normalized["date"] = item.get("date") or item.get("日期")
    normalized["symbol"] = _normalise_symbol(normalized.get("symbol"))
    normalized["date"] = _date_key(normalized.get("date"))
    return normalized, source_schema


def _table_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    rows = connection.execute(f"PRAGMA table_info({_quote(table)})").fetchall()
    return [str(row[1]) for row in rows]


def _pick(columns: Sequence[str], *names: str) -> str | None:
    for name in names:
        if name in columns:
            return name
    return None


def _read_only_connection(db_path: Path) -> sqlite3.Connection:
    if not db_path.is_file():
        raise DryRunError(f"SQLite DB 不存在：{db_path}")
    uri = "file:" + db_path.resolve().as_posix() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=30)
    connection.execute("PRAGMA query_only=ON")
    if int(connection.execute("PRAGMA query_only").fetchone()[0]) != 1:
        connection.close()
        raise DryRunError("SQLite query_only 未啟用")
    return connection


def _assert_output_safe(output_path: Path, source_roots: Iterable[Path]) -> None:
    """Reject output paths that could overwrite formal inputs or symlinks."""
    output_path = output_path.expanduser()
    if output_path.exists() and output_path.is_symlink():
        raise DryRunError(f"輸出檔不可是 symlink：{output_path}")
    resolved_output = output_path.resolve(strict=False)
    for source in source_roots:
        source = source.expanduser()
        resolved_source = source.resolve(strict=False)
        if resolved_output == resolved_source or resolved_source in resolved_output.parents:
            raise DryRunError(f"輸出路徑落在正式來源範圍：{output_path} / {source}")
    parent = output_path.parent
    if parent.exists() and parent.is_symlink():
        raise DryRunError(f"輸出父目錄不可是 symlink：{parent}")


def _load_overlay(path: Path, target_date: str) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    if not path.is_file():
        raise DryRunError(f"canonical overlay/audit 不存在：{path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows: list[Mapping[str, Any]] = []
    comparisons = payload.get("comparisons")
    if isinstance(comparisons, Mapping):
        for comparison in comparisons.values():
            if isinstance(comparison, Mapping):
                candidate = comparison.get("mismatch_rows")
                if isinstance(candidate, list):
                    rows.extend(item for item in candidate if isinstance(item, Mapping))
    if not rows and isinstance(payload.get("rows"), list):
        rows = [item for item in payload["rows"] if isinstance(item, Mapping)]
    overlay: dict[str, dict[str, Any]] = {}
    schema_counts: dict[str, int] = {}
    for item in rows:
        canonical, source_schema = _normalise_overlay_row(item)
        schema_counts[source_schema] = schema_counts.get(source_schema, 0) + 1
        date = _date_key(canonical.get("date") or item.get("date"))
        if date != target_date:
            continue
        symbol = _normalise_symbol(canonical.get("symbol") or item.get("symbol"))
        if not symbol:
            continue
        if symbol in overlay and overlay[symbol] != dict(canonical):
            raise DryRunError(f"canonical overlay 同一股票有多個不一致 row：{symbol}")
        overlay[symbol] = dict(canonical)
    if not overlay:
        raise DryRunError(f"overlay 沒有找到 target date {target_date} 的 row")
    metadata = {
        "path": str(path.resolve()),
        "sha256": _sha256_file(path),
        "target_date": target_date,
        "symbol_count": len(overlay),
        "row_schema_counts": schema_counts,
        "source_scope": payload.get("scope") or payload.get("schema_version") or "unknown",
    }
    for key in (
        "plan_hash",
        "allowlist_hash",
        "canonical_sha256",
        "source_date",
        "source_update_columns",
        "untouched_columns",
        "table_fingerprint_policy",
        "apply_allowed",
        "promotion_eligible",
        "formal_training_allowed",
    ):
        if key in payload:
            metadata[key] = payload[key]
    return overlay, metadata


def _canonical_value(row: Mapping[str, Any], field: str) -> float:
    key = CANONICAL_FIELDS[field]
    return _finite_number(row.get(key))


def _fetch_daily(connection: sqlite3.Connection, symbol: str) -> pd.DataFrame:
    columns = _table_columns(connection, "daily_prices")
    date_col = _pick(columns, "日期", "Date")
    code_col = _pick(columns, "證券代號", "stock_code", "Code")
    if date_col is None or code_col is None:
        raise DryRunError("daily_prices 缺少日期或證券代號欄位")
    selected: list[tuple[str, str | None]] = [
        ("date", date_col),
        ("symbol", code_col),
        ("open", _pick(columns, "開盤價", "Open")),
        ("high", _pick(columns, "最高價", "High")),
        ("low", _pick(columns, "最低價", "Low")),
        ("close", _pick(columns, "收盤價", "Close")),
        ("volume", _pick(columns, "成交股數", "Volume")),
    ]
    missing = [alias for alias, column in selected if column is None and alias in OHLC_COLUMNS]
    if missing:
        raise DryRunError(f"daily_prices 缺少 OHLC 欄位：{missing}")
    select_sql = ", ".join(
        f"{_quote(column)} AS {_quote(alias)}" if column is not None else f"NULL AS {_quote(alias)}"
        for alias, column in selected
    )
    sql = (
        f"SELECT {select_sql} FROM {_quote('daily_prices')} "
        f"WHERE {_quote(code_col)} = ? ORDER BY {_quote(date_col)} ASC"
    )
    frame = pd.read_sql_query(sql, connection, params=(symbol,))
    if frame.empty:
        # Some DB rows are zero-padded while the audit JSON may not be.
        frame = pd.read_sql_query(sql, connection, params=(symbol.zfill(4),))
    if frame.empty:
        return pd.DataFrame(columns=["date", "symbol", *OHLC_COLUMNS, "volume"])
    frame["date"] = frame["date"].map(_date_key)
    frame["symbol"] = frame["symbol"].map(_normalise_symbol)
    for column in (*OHLC_COLUMNS, "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame[frame["date"].astype(bool)].copy()
    if frame["date"].duplicated().any():
        raise DryRunError(f"daily_prices duplicate date：{symbol}")
    return frame.reset_index(drop=True)


def _fetch_technical_rows(
    connection: sqlite3.Connection, symbol: str, target_date: str
) -> tuple[list[str], list[tuple[Any, ...]]]:
    columns = _table_columns(connection, "technical_indicators")
    date_col = _pick(columns, "日期", "Date")
    code_col = _pick(columns, "證券代號", "stock_code", "Code")
    if date_col is None or code_col is None:
        raise DryRunError("technical_indicators 缺少日期或證券代號欄位")
    sql = (
        f"SELECT * FROM {_quote('technical_indicators')} "
        f"WHERE {_quote(code_col)} = ? ORDER BY {_quote(date_col)} ASC"
    )
    cursor = connection.execute(sql, (symbol,))
    rows = cursor.fetchall()
    if not rows and symbol.zfill(4) != symbol:
        rows = connection.execute(sql, (symbol.zfill(4),)).fetchall()
    date_index = columns.index(date_col)
    filtered = [row for row in rows if _date_key(row[date_index]) >= target_date]
    return columns, filtered


def _row_hash(columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    payload = {
        "columns": list(columns),
        "rows": [[_hash_value(value) for value in row] for row in rows],
    }
    return _sha256_payload(payload)


def _compute_segment(frame: pd.DataFrame) -> dict[str, np.ndarray]:
    """Compute one completely valid OHLC segment without any fill operation."""
    n = len(frame)
    result = {column: np.full(n, np.nan, dtype=float) for column in DEPENDENT_INDICATORS}
    # Numeric-analysis boundary: TA-Lib consumes float64 arrays in memory.
    # Values cross back to the manifest only through _json_value(), which
    # rejects non-finite values; no float is used for persisted money/position
    # calculations and this function never writes a source or formal row.
    close = np.ascontiguousarray(frame["close"].to_numpy(dtype=float), dtype=np.float64)
    high = np.ascontiguousarray(frame["high"].to_numpy(dtype=float), dtype=np.float64)
    low = np.ascontiguousarray(frame["low"].to_numpy(dtype=float), dtype=np.float64)

    result["SMA30"] = talib.SMA(close, timeperiod=30)
    result["DEMA30"] = talib.DEMA(close, timeperiod=30)
    result["EMA30"] = talib.EMA(close, timeperiod=30)
    result["RSI"] = talib.RSI(close, timeperiod=14)
    macd, signal, hist = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
    result["MACD"] = macd
    result["MACD_signal"] = signal
    result["MACD_hist"] = hist
    slowk, slowd = talib.STOCH(
        high,
        low,
        close,
        fastk_period=5,
        slowk_period=3,
        slowk_matype=0,
        slowd_period=3,
        slowd_matype=0,
    )
    result["slowk"] = slowk
    result["slowd"] = slowd
    upper, middle, lower = talib.BBANDS(
        close, timeperiod=30, nbdevup=2.0, nbdevdn=2.0, matype=0
    )
    result["middleband"] = middle
    result["upperband"] = upper
    result["lowerband"] = lower
    result["SAR"] = talib.SAR(high, low, acceleration=0.02, maximum=0.2)
    result["TSF"] = talib.TSF(close, timeperiod=14)
    result["MA5"] = talib.SMA(close, timeperiod=5)
    result["MA10"] = talib.SMA(close, timeperiod=10)
    result["MA20"] = talib.SMA(close, timeperiod=20)
    result["MA60"] = talib.SMA(close, timeperiod=60)
    result["ADX"] = talib.ADX(high, low, close, timeperiod=14)
    return result


def _compute_segmented(frame: pd.DataFrame) -> pd.DataFrame:
    """Reset all TA-Lib kernels after every missing OHLC row."""
    result = pd.DataFrame(
        {column: np.full(len(frame), np.nan, dtype=float) for column in DEPENDENT_INDICATORS},
        index=frame.index,
    )
    valid = frame[list(OHLC_COLUMNS)].notna().all(axis=1).to_numpy(dtype=bool)
    index = 0
    while index < len(frame):
        if not valid[index]:
            index += 1
            continue
        end = index + 1
        while end < len(frame) and valid[end]:
            end += 1
        segment = _compute_segment(frame.iloc[index:end].reset_index(drop=True))
        for column in DEPENDENT_INDICATORS:
            result.iloc[index:end, result.columns.get_loc(column)] = segment[column]
        index = end
    return result


def _overlay_daily(
    daily: pd.DataFrame, canonical: Mapping[str, Any], target_date: str
) -> tuple[pd.DataFrame, dict[str, Any]]:
    overlay = daily.copy()
    target_rows = overlay.index[overlay["date"] == target_date].tolist()
    source_summary = {
        "target_row_present": bool(target_rows),
        "canonical_ohlc_complete": all(
            math.isfinite(_canonical_value(canonical, field)) for field in OHLC_COLUMNS
        ),
        "canonical_fields": {
            key: _json_value(canonical.get(value))
            for key, value in CANONICAL_FIELDS.items()
            if key in OHLC_COLUMNS or key in {"成交股數", "成交金額", "漲跌價差", "漲跌(+/-)"}
        },
    }
    if not target_rows:
        return overlay, source_summary
    if len(target_rows) != 1:
        raise DryRunError(f"daily target row 非唯一：{canonical.get('symbol')}")
    row_index = target_rows[0]
    for field in OHLC_COLUMNS:
        overlay.at[row_index, field] = _canonical_value(canonical, field)
    overlay.at[row_index, "volume"] = _canonical_value(canonical, "成交股數")
    return overlay, source_summary


def _calculation_sequence_hash(frame: pd.DataFrame) -> str:
    """Hash only the date/OHLC sequence consumed by TA-Lib kernels."""
    rows = [
        {
            "date": str(row.get("date", "")),
            "open": _json_value(row.get("open")),
            "high": _json_value(row.get("high")),
            "low": _json_value(row.get("low")),
            "close": _json_value(row.get("close")),
        }
        for row in frame[["date", *OHLC_COLUMNS]].to_dict(orient="records")
    ]
    return _sha256_payload(rows)


def _record_values(row: Sequence[Any], columns: Sequence[str], names: Iterable[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in names:
        try:
            index = columns.index(name)
        except ValueError:
            continue
        result[name] = _json_value(row[index])
    return result


def _source_value(
    canonical: Mapping[str, Any], source_column: str
) -> tuple[bool, Any, str]:
    """Resolve one price-plan source field without inventing a value."""
    key = SOURCE_FIELD_KEYS.get(source_column)
    if key is None:
        return False, None, ""
    aliases: tuple[str, ...] = {
        "date": ("date", "日期", "Date"),
        "name": ("name", "證券名稱", "名稱"),
        "volume_shares": ("volume_shares", "成交股數", "Volume"),
        "trade_count": ("trade_count", "成交筆數"),
        "turnover": ("turnover", "成交金額"),
        "open": ("open", "開盤價", "Open"),
        "high": ("high", "最高價", "High"),
        "low": ("low", "最低價", "Low"),
        "close": ("close", "收盤價", "Close"),
        "sign": ("sign", "漲跌(+/-)", "漲跌", "涨跌"),
        "change_value": ("change_value", "漲跌價差"),
        "best_bid": ("best_bid", "最後揭示買價"),
        "best_bid_volume": ("best_bid_volume", "最後揭示買量"),
        "best_ask": ("best_ask", "最後揭示賣價"),
        "best_ask_volume": ("best_ask_volume", "最後揭示賣量"),
        "pe_ratio": ("pe_ratio", "本益比"),
    }[key]
    for alias in aliases:
        if alias in canonical:
            return True, _json_value(canonical[alias]), alias
    return False, None, key


def _source_copy_plan(
    *,
    columns: Sequence[str],
    technical_rows: Sequence[Sequence[Any]],
    canonical: Mapping[str, Any],
    target_date: str,
    source_update_columns: Sequence[str],
    source_plan_hash: str | None,
) -> dict[str, Any]:
    """Build a target-row-only source-field plan; never mutate a row.

    ``technical_indicators`` has duplicate sign columns in some formal
    schemas.  Every physical occurrence is emitted with its ordinal so an
    eventual writer cannot silently update only the first duplicate column.
    """
    date_column = _pick(columns, "日期", "Date")
    target_index: int | None = None
    if date_column is not None:
        date_index = columns.index(date_column)
        for index, row in enumerate(technical_rows):
            if _date_key(row[date_index]) == target_date:
                target_index = index
                break

    requested = list(dict.fromkeys(str(column) for column in source_update_columns))
    present = [column for column in requested if column in columns]
    missing = [column for column in requested if column not in columns]
    source_row = {
        str(key): _json_value(value)
        for key, value in canonical.items()
        if not str(key).startswith("_")
    }
    raw_source = canonical.get("_raw_source_row")
    if not isinstance(raw_source, Mapping):
        raw_source = source_row
    raw_source_payload = {
        str(key): _json_value(value) for key, value in raw_source.items()
    }
    source_row_hash = _sha256_payload(raw_source_payload)
    plan: dict[str, Any] = {
        "status": "ready" if target_index is not None else "no_existing_target_row",
        "target_date": target_date,
        "source_plan_hash": source_plan_hash,
        "source_row_sha256": source_row_hash,
        "source_row_hash_semantics": "raw_verified_price_plan_rows_source_mapping",
        "normalized_source_row_sha256": _sha256_payload(source_row),
        "source_columns_requested": requested,
        "source_columns_present": present,
        "source_columns_missing_from_technical": missing,
        "target_row_present": target_index is not None,
        "updates": [],
        "desired": [],
        "unavailable_source_fields": [],
        "formal_write_performed": False,
        "apply_policy": (
            "Apply only listed target-date cells after price-plan hash/source-row verification; "
            "do not update pre-target rows, unknown columns, or an absent source field."
        ),
    }
    if target_index is None:
        return plan

    row = technical_rows[target_index]
    for column in present:
        available, new_value, source_key = _source_value(canonical, column)
        if not available:
            plan["unavailable_source_fields"].append(column)
            continue
        occurrences = [index for index, value in enumerate(columns) if value == column]
        for ordinal, index in enumerate(occurrences):
            old_value = _json_value(row[index])
            plan["desired"].append(
                {
                    "row_identity": {"date": target_date},
                    "column": column,
                    "column_ordinal": ordinal,
                    "source_key": source_key,
                    "new": new_value,
                }
            )
            if _values_equal(old_value, new_value):
                continue
            plan["updates"].append(
                {
                    "row_identity": {"date": target_date},
                    "column": column,
                    "column_ordinal": ordinal,
                    "source_key": source_key,
                    "old": old_value,
                    "new": new_value,
                }
            )
    return plan


def _csv_target_snapshot(
    path: Path,
    symbol: str,
    target_date: str,
    dependent_columns: Sequence[str],
) -> dict[str, Any]:
    if not path.is_file():
        return {"status": "missing", "path": str(path)}
    if path.is_symlink():
        return {"status": "rejected_symlink", "path": str(path)}
    frame = pd.read_csv(path, encoding="utf-8-sig")
    date_col = _pick(list(frame.columns), "日期", "Date")
    if date_col is None:
        return {"status": "missing_date_column", "path": str(path)}
    frame = frame.copy()
    frame["__date_key"] = frame[date_col].map(_date_key)
    rows = frame[frame["__date_key"] >= target_date].copy()
    target = rows[rows["__date_key"] == target_date]
    return {
        "status": "ok",
        "path": str(path),
        "sha256": _sha256_file(path),
        "existing_rows": int(len(rows)),
        "target_row_count": int(len(target)),
        "target_source_fields": (
            target.iloc[0][[col for col in SOURCE_COLUMNS if col in target.columns]]
            .map(_json_value)
            .to_dict()
            if len(target) == 1
            else {}
        ),
        "dependent_columns_present": [
            column for column in dependent_columns if column in frame.columns
        ],
    }


def _build_symbol_plan(
    connection: sqlite3.Connection,
    symbol: str,
    canonical: Mapping[str, Any],
    target_date: str,
    technical_dir: Path | None = None,
    include_csv_cache: bool = False,
    source_update_columns: Sequence[str] = (),
    source_plan_hash: str | None = None,
) -> dict[str, Any]:
    daily = _fetch_daily(connection, symbol)
    overlaid, source_summary = _overlay_daily(daily, canonical, target_date)
    computed = _compute_segmented(overlaid) if not overlaid.empty else pd.DataFrame(columns=DEPENDENT_INDICATORS)
    columns, technical_rows = _fetch_technical_rows(connection, symbol, target_date)
    date_column = _pick(columns, "日期", "Date")
    code_column = _pick(columns, "證券代號", "stock_code", "Code")
    available_indicators = [column for column in DEPENDENT_INDICATORS if column in columns]
    # Keep date keys explicit; no price data is forward/backward filled.
    daily_by_date = {
        str(value): int(index) for index, value in overlaid["date"].items()
    }

    changes: list[dict[str, Any]] = []
    old_rows = [_row_hash(columns, [row]) for row in technical_rows]
    old_hash = _row_hash(columns, technical_rows)
    invalid_source_dates = set(
        str(value)
        for value in overlaid.loc[
            ~overlaid[list(OHLC_COLUMNS)].notna().all(axis=1), "date"
        ].tolist()
    )
    missing_daily_rows = 0
    updated_cells = 0
    invalidated_rows = 0
    cache_desired_rows: list[dict[str, Any]] = []
    for row in technical_rows:
        if date_column is None:
            continue
        date_index = columns.index(date_column)
        date = _date_key(row[date_index])
        old_values = _record_values(row, columns, available_indicators)
        if date in daily_by_date:
            computed_row = computed.iloc[daily_by_date[date]]
            new_values = {
                column: _json_value(computed_row[column]) for column in available_indicators
            }
        else:
            missing_daily_rows += 1
            new_values = {column: None for column in available_indicators}
        cache_desired_rows.append(
            {
                "date": date,
                "desired": {
                    column: _json_value(value) for column, value in new_values.items()
                },
            }
        )
        changed_old: dict[str, Any] = {}
        changed_new: dict[str, Any] = {}
        for column in available_indicators:
            if not _values_equal(old_values.get(column), new_values.get(column)):
                changed_old[column] = old_values.get(column)
                changed_new[column] = new_values.get(column)
        if not changed_old:
            continue
        updated_cells += len(changed_old)
        source_invalid = date in invalid_source_dates or date not in daily_by_date
        if source_invalid and all(value is None for value in changed_new.values()):
            invalidated_rows += 1
        changes.append(
            {
                "date": date,
                "old": changed_old,
                "new": changed_new,
                "changed_columns": sorted(changed_old),
                "action": "invalidate_dependent_indicators" if source_invalid else "replace_recomputed_indicators",
            }
        )

    target_source_fields = _record_values(
        next(
            (
                row
                for row in technical_rows
                if date_column is not None and _date_key(row[columns.index(date_column)]) == target_date
            ),
            (),
        ),
        columns,
        SOURCE_COLUMNS,
    )
    source_copy = _source_copy_plan(
        columns=columns,
        technical_rows=technical_rows,
        canonical=canonical,
        target_date=target_date,
        source_update_columns=source_update_columns,
        source_plan_hash=source_plan_hash,
    )
    result: dict[str, Any] = {
        "symbol": symbol,
        "canonical_target": {
            key: _json_value(value)
            for key, value in canonical.items()
            if key in {"symbol", "date", "open", "high", "low", "close", "volume_shares", "turnover", "change_value", "sign"}
        },
        "canonical_source_row": {
            key: _json_value(value)
            for key, value in canonical.items()
            if not str(key).startswith("_")
        },
        "canonical_source_row_raw": {
            str(key): _json_value(value)
            for key, value in (
                canonical.get("_raw_source_row", canonical)
                if isinstance(canonical.get("_raw_source_row", canonical), Mapping)
                else {}
            ).items()
        },
        "source_summary": source_summary,
        "source_copy_plan": source_copy,
        "technical_table": {
            "date_column": date_column,
            "code_column": code_column,
            "available_dependent_indicators": available_indicators,
            "missing_dependent_indicators": [
                column for column in DEPENDENT_INDICATORS if column not in columns
            ],
            "existing_rows_from_target": len(technical_rows),
            "old_rows_sha256": old_hash,
            "updated_rows": len(changes),
            "updated_cells": updated_cells,
            "invalidated_rows": invalidated_rows,
            "missing_daily_rows": missing_daily_rows,
            "target_source_fields_observed": target_source_fields,
            "pre_target_rows_untouched": True,
            "unknown_columns_untouched": True,
        },
        "daily_input": {
            "rows": len(daily),
            "first_date": str(daily["date"].min()) if not daily.empty else None,
            "last_date": str(daily["date"].max()) if not daily.empty else None,
            "missing_ohlc_rows": int(
                (~overlaid[list(OHLC_COLUMNS)].notna().all(axis=1)).sum()
            )
            if not overlaid.empty
            else 0,
            "missing_ohlc_dates": sorted(invalid_source_dates),
            "full_prefix_recomputed_in_memory": bool(not overlaid.empty),
            "calculation_sequence_sha256": _calculation_sequence_hash(overlaid)
            if not overlaid.empty
            else None,
            "calculation_sequence_row_count": int(len(overlaid)),
        },
        "updates": changes,
        "cache_desired_rows": cache_desired_rows,
        "rollback": {
            "formal_write_performed": False,
            "row_identity": [str(code_column or "證券代號"), str(date_column or "日期")],
            "old_values_embedded_in_updates": True,
            "restore_scope": "Only changed dependent columns on listed rows; pre-target and unknown columns remain untouched.",
        },
    }
    if include_csv_cache and technical_dir is not None:
        safe_symbol = re.sub(r"[^A-Za-z0-9_-]", "", symbol)
        csv_path = technical_dir / f"{safe_symbol}_indicators.csv"
        result["csv_cache"] = _csv_target_snapshot(
            csv_path, symbol, target_date, available_indicators
        )
    else:
        result["csv_cache"] = {
            "status": "not_requested",
            "policy": "SQLite is primary for report/recommendation consumers; CSV cache requires a separate approved narrow update with backup.",
        }
    return result


def _consumer_resolution() -> dict[str, Any]:
    return {
        "sqlite_primary": [
            "app_module/stock_research_report_service.py::_read_technical",
            "app_module/recommendation_market_data_provider.py::__call__",
            "app_module/backtest_service.py (use_sqlite path)",
            "decision_module/stock_screener.py (SQLite JOIN paths)",
            "ml_module/feature_eligibility.py (source_id sqlite.technical_indicators)",
        ],
        "csv_fallback_or_cache": [
            "app_module/recommendation_market_data_provider.py (SQLite failure fallback)",
            "app_module/backtest_service.py (non-SQLite fallback)",
            "decision_module/stock_screener.py (non-SQLite fallback)",
            "data_root/technical_analysis/{symbol}_indicators.csv",
        ],
        "repair_order": "Do not promote stale CSV over SQLite; if cache is updated later, retain a backup and apply only listed target-plus-existing rows.",
    }


def run_dryrun(
    *,
    db_path: Path,
    overlay_path: Path,
    output_path: Path,
    data_root: Path,
    target_date: str = TARGET_DATE,
    symbols: Sequence[str] | None = None,
    include_csv_cache: bool = False,
) -> dict[str, Any]:
    target_date = _date_key(target_date)
    if target_date != TARGET_DATE:
        raise DryRunError(f"本事件 dry-run 僅允許 target date {TARGET_DATE}")
    overlay, overlay_meta = _load_overlay(overlay_path, target_date)
    selected = sorted({_normalise_symbol(value) for value in symbols}) if symbols else sorted(overlay)
    missing_overlay = [symbol for symbol in selected if symbol not in overlay]
    if missing_overlay:
        raise DryRunError(f"指定股票不在 canonical overlay：{missing_overlay[:10]}")
    resolved_data_root = data_root.expanduser().resolve(strict=False)
    technical_dir = resolved_data_root / "technical_analysis"
    _assert_output_safe(
        output_path,
        (
            resolved_data_root,
            db_path,
            resolved_data_root / "daily_price",
            resolved_data_root / "daily_price_tpex",
            technical_dir,
            resolved_data_root / "meta_data",
        ),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    db_stat = db_path.stat()
    connection = _read_only_connection(db_path)
    plans: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    try:
        for symbol in selected:
            try:
                plans.append(
                    _build_symbol_plan(
                        connection,
                        symbol,
                        overlay[symbol],
                        target_date,
                        technical_dir=technical_dir,
                        include_csv_cache=include_csv_cache,
                        source_update_columns=tuple(
                            dict.fromkeys(
                                [
                                    str(column)
                                    for column in overlay_meta.get(
                                        "source_update_columns", SOURCE_COLUMNS
                                    )
                                ]
                                + list(TECHNICAL_ALIAS_COLUMNS)
                            )
                        ),
                        source_plan_hash=(
                            str(overlay_meta["plan_hash"])
                            if overlay_meta.get("plan_hash") is not None
                            else None
                        ),
                    )
                )
            except Exception as exc:  # retain per-symbol auditability
                failures.append({"symbol": symbol, "error": f"{type(exc).__name__}: {exc}"})
    finally:
        connection.close()
    summary = {
        "selected_symbols": len(selected),
        "planned_symbols": len(plans),
        "failed_symbols": len(failures),
        "technical_rows_from_target": sum(
            int(plan["technical_table"]["existing_rows_from_target"]) for plan in plans
        ),
        "updated_rows": sum(int(plan["technical_table"]["updated_rows"]) for plan in plans),
        "updated_cells": sum(int(plan["technical_table"]["updated_cells"]) for plan in plans),
        "invalidated_rows": sum(int(plan["technical_table"]["invalidated_rows"]) for plan in plans),
        "source_copy_rows": sum(
            1
            for plan in plans
            if bool(plan["source_copy_plan"].get("updates"))
        ),
        "source_copy_cells": sum(
            len(plan["source_copy_plan"].get("updates", [])) for plan in plans
        ),
        "source_copy_unavailable_fields": sum(
            len(plan["source_copy_plan"].get("unavailable_source_fields", []))
            for plan in plans
        ),
        "missing_daily_rows": sum(int(plan["technical_table"]["missing_daily_rows"]) for plan in plans),
        "symbols_with_missing_ohlc": sum(
            1 for plan in plans if int(plan["daily_input"]["missing_ohlc_rows"]) > 0
        ),
        "formal_data_written": False,
        "legacy_calculator_called": False,
        "all_output_values_are_null_or_talib": True,
    }
    manifest: dict[str, Any] = {
        "schema_version": "technical-indicator-repair-dryrun-20260520.v1",
        "scope": {
            "target_date": target_date,
            "selected_symbols_source": overlay_meta["path"],
            "scope_rule": "Only overlay candidates; only existing technical rows >= target date; no current-old diff expansion.",
            "dependent_indicators": list(DEPENDENT_INDICATORS),
        },
        "read_only": {
            "sqlite_uri_mode": "mode=ro",
            "query_only": True,
            "formal_data_written": False,
            "db_path": str(db_path.resolve()),
            "db_file_size": int(db_stat.st_size),
            "db_file_mtime_ns": int(db_stat.st_mtime_ns),
            "db_hash_semantics": "file stat only; this is not a transaction snapshot hash",
        },
        "overlay_source": overlay_meta,
        "consumer_resolution": _consumer_resolution(),
        "policy": {
            "missing_ohlc": "hard segment boundary; no ffill/bfill/zero; dependent outputs NULL during warmup or missing source",
            "official_missing_target": "target row remains present in scope and invalidates dependent indicators; it is not silently excluded",
            "pre_target": "preserve; not emitted as update rows",
            "unknown_columns": "preserve; no update plan",
            "atr": "not in this whitelist because current persisted contract is NULL and normal calculator path does not produce it",
            "source_copy": "target-date-only plan from repair_plan.json rows[].source; no source-field or cache write is performed",
            "csv_cache": "not written; optional audit records target source fields and existing rows only",
        },
        "summary": summary,
        "failures": failures,
        "plans": plans,
        "rollback": {
            "formal_write_performed": False,
            "manifest_contains_old_values_for_changed_cells": True,
            "required_before_any_future_write": [
                "Create and retain formal SQLite backup",
                "Verify this manifest and source hashes",
                "Apply only (symbol,date,dependent_column) cells listed in plans[].updates",
                "Keep pre-target rows and unknown columns unchanged",
                "Re-read affected rows and compare to manifest new values",
            ],
        },
    }
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sidecar = output_path.with_suffix(output_path.suffix + ".sha256")
    sidecar.write_text(_sha256_file(output_path) + "\n", encoding="ascii")
    return manifest


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--overlay", type=Path, default=DEFAULT_OVERLAY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--target-date", default=TARGET_DATE)
    parser.add_argument("--symbols", nargs="*", default=None)
    parser.add_argument(
        "--include-csv-cache",
        action="store_true",
        help="逐一讀取個股 technical CSV 的 target-plus-existing rows；仍不寫入",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    data_root = Path(args.data_root)
    db_path = Path(args.db) if args.db is not None else data_root / "sqlite" / "twstock.db"
    try:
        manifest = run_dryrun(
            db_path=db_path,
            overlay_path=Path(args.overlay),
            output_path=Path(args.output),
            data_root=data_root,
            target_date=args.target_date,
            symbols=args.symbols,
            include_csv_cache=bool(args.include_csv_cache),
        )
    except (DryRunError, OSError, sqlite3.Error, ValueError) as exc:
        print(f"dry-run failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"output": str(Path(args.output).resolve()), "summary": manifest["summary"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
