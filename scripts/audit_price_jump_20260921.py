"""唯讀稽核 2026-09-21 全市場每日價格跨日跳變與來源一致性。

本腳本不建立資料庫 schema、不啟動 writer，也不修改正式資料。Decimal 僅用於
價格、報酬與成交額隱含價格的稽核計算；輸出只寫入 repo 的 ignored QA 目錄。
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable


DEFAULT_DATA_ROOT = Path("F:/Min/Python/Project/FA_Data")
DEFAULT_DB = DEFAULT_DATA_ROOT / "sqlite" / "twstock.db"
DEFAULT_OUTPUT = Path("output/qa/price_jump_20260921")
TARGET_DATE = "20260921"
COMPARISON_START = "20260825"
COMPARISON_END = TARGET_DATE
PRICE_FIELDS = (
    "開盤價",
    "最高價",
    "最低價",
    "收盤價",
    "成交股數",
    "成交金額",
    "漲跌",
    "漲跌價差",
)


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if text in {"", "--", "—", "-", "None", "nan", "NaN"}:
        return None
    try:
        parsed = Decimal(text)
        return parsed if parsed.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _code(value: object) -> str:
    text = _text(value)
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text.zfill(4) if text.isdigit() else text


def _date_key(value: object) -> str:
    text = _text(value).replace("-", "").replace("/", "")
    if len(text) == 8 and text.isdigit():
        return text
    return text


def _iso_date_key(key: str) -> date:
    return date(int(key[:4]), int(key[4:6]), int(key[6:8]))


def _value_hash(row: dict[str, Any]) -> str:
    payload = "|".join(_text(row.get(field)) for field in PRICE_FIELDS)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _open_read_only(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.execute("PRAGMA query_only=ON")
    return connection


def _table_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')]


def _load_sqlite_rows(
    connection: sqlite3.Connection,
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    columns = _table_columns(connection, "daily_prices")
    required = {"日期", "證券代號", "開盤價", "最高價", "最低價", "收盤價", "成交股數", "成交金額", "漲跌價差"}
    missing = sorted(required.difference(columns))
    if missing:
        raise RuntimeError(f"daily_prices schema 缺少欄位: {missing}")
    sign_columns = [
        column
        for column in ("漲跌(+/-)", "漲跌", "涨跌")
        if column in columns
    ]
    projection = [
        "日期",
        "證券代號",
        "開盤價",
        "最高價",
        "最低價",
        "收盤價",
        "成交股數",
        "成交金額",
        "漲跌價差",
        *sign_columns,
    ]
    normalized_date = 'replace(replace(CAST("日期" AS TEXT), \'-\', \'\'), \'/\', \'\')'
    query = (
        'SELECT '
        + ", ".join(f'"{column}"' for column in projection)
        + f' FROM daily_prices WHERE {normalized_date} BETWEEN ? AND ? '
        + f'ORDER BY {normalized_date}, CAST("證券代號" AS TEXT)'
    )
    rows: list[dict[str, Any]] = []
    for values in connection.execute(query, (start_date, end_date)):
        item = dict(zip(projection, values, strict=True))
        item["日期"] = _date_key(item["日期"])
        item["證券代號"] = _code(item["證券代號"])
        item["_sign_candidates"] = {
            column: _text(item.get(column))
            for column in sign_columns
        }
        item["漲跌"] = next(
            (
                item["_sign_candidates"][column]
                for column in sign_columns
                if item["_sign_candidates"][column]
            ),
            "",
        )
        rows.append(item)
    return rows


def _load_csv_rows(
    path: Path,
    *,
    source: str,
    fallback_date: str | None = None,
) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            item = {str(key).strip(): value for key, value in raw.items() if key is not None}
            sign_columns = [
                column for column in ("漲跌(+/-)", "漲跌", "涨跌") if column in item
            ]
            item["_sign_candidates"] = {
                column: _text(item.get(column)) for column in sign_columns
            }
            if not item.get("漲跌"):
                item["漲跌"] = next(
                    (
                        item["_sign_candidates"][column]
                        for column in sign_columns
                        if item["_sign_candidates"][column]
                    ),
                    "",
                )
            if not item.get("漲跌價差"):
                item["漲跌價差"] = item.get("漲跌價差") or ""
            date_value = item.get("日期") or item.get("date") or item.get("Date") or fallback_date
            code_value = item.get("證券代號") or item.get("stock_code") or item.get("code")
            date_key = _date_key(date_value)
            if date_key not in {"20260918", TARGET_DATE}:
                continue
            item["日期"] = date_key
            item["證券代號"] = _code(code_value)
            item["_source"] = source
            rows.append(item)
    return rows


def _load_raw_rows(data_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for directory, source in (
        (data_root / "daily_price", "twse_raw"),
        (data_root / "daily_price_tpex", "tpex_raw"),
    ):
        for date_key in ("20260918", TARGET_DATE):
            rows.extend(
                _load_csv_rows(
                    directory / f"{date_key}.csv",
                    source=source,
                    fallback_date=date_key,
                )
            )
    return rows


def _load_merged_rows(data_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    path = data_root / "meta_data" / "stock_data_whole.csv"
    if not path.is_file():
        return [], {
            "path": str(path),
            "exists": False,
            "status": "missing",
            "total_row_count": 0,
            "distinct_date_count": 0,
            "date_min": None,
            "date_max": None,
            "target_date_row_count": 0,
            "previous_date_row_count": 0,
        }
    result: list[dict[str, Any]] = []
    date_counts: Counter[str] = Counter()
    total_row_count = 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            total_row_count += 1
            item = {str(key).strip(): value for key, value in raw.items() if key is not None}
            sign_columns = [
                column for column in ("漲跌(+/-)", "漲跌", "涨跌") if column in item
            ]
            item["_sign_candidates"] = {
                column: _text(item.get(column)) for column in sign_columns
            }
            if not item.get("漲跌"):
                item["漲跌"] = next(
                    (
                        item["_sign_candidates"][column]
                        for column in sign_columns
                        if item["_sign_candidates"][column]
                    ),
                    "",
                )
            date_key = _date_key(item.get("日期") or item.get("date"))
            if date_key:
                date_counts[date_key] += 1
            if date_key not in {"20260918", TARGET_DATE}:
                continue
            item["日期"] = date_key
            item["證券代號"] = _code(item.get("證券代號") or item.get("stock_code"))
            item["_source"] = "merged"
            result.append(item)
    coverage = {
        "path": str(path),
        "exists": True,
        "status": "completed" if result else "completed_no_target_rows",
        "total_row_count": total_row_count,
        "distinct_date_count": len(date_counts),
        "date_min": min(date_counts) if date_counts else None,
        "date_max": max(date_counts) if date_counts else None,
        "target_date_row_count": date_counts.get(TARGET_DATE, 0),
        "previous_date_row_count": date_counts.get("20260918", 0),
    }
    return result, coverage


def _market_by_source(row: dict[str, Any]) -> str:
    declared = _text(row.get("_market"))
    if declared:
        return declared.upper()
    source = _text(row.get("_source"))
    if "tpex" in source.lower():
        return "TPEX"
    if "twse" in source.lower():
        return "TWSE"
    return _text(row.get("市場")).upper() or "UNKNOWN（未核證）"


def _stock_type(code: str, registry: dict[str, str] | None = None) -> str:
    declared = (registry or {}).get(code, "")
    if declared in {"ETF", "ETN"}:
        return declared
    if code.isdigit() and len(code) == 4:
        return "普通四碼（未核證）"
    return "其他（未核證）"


def _load_security_registry(data_root: Path) -> tuple[dict[str, str], dict[str, str]]:
    """讀取既有公司清單，只作 market/type 分組，不把缺項推定成普通股票。"""

    path = data_root / "meta_data" / "companies_cleaned.csv"
    security_type: dict[str, str] = {}
    market: dict[str, str] = {}
    if not path.is_file():
        return security_type, market
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            code = _code(raw.get("stock_id"))
            if not code:
                continue
            category = _text(raw.get("industry_category")).upper()
            if category in {"ETF", "ETN"}:
                security_type[code] = category
            declared_market = _text(raw.get("type")).lower()
            if declared_market in {"twse", "tpex"}:
                market[code] = declared_market.upper()
    return security_type, market


def _safe_ratio(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    if numerator is None or denominator in {None, Decimal("0")}:
        return None
    return numerator / denominator


def _transition_record(
    code: str,
    previous_day: str,
    current_day: str,
    previous: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, Any] | None:
    previous_close = _decimal(previous.get("收盤價"))
    close = _decimal(current.get("收盤價"))
    ratio = _safe_ratio(close - previous_close if close is not None and previous_close is not None else None, previous_close)
    if ratio is None:
        return None
    return {
        "stock_code": code,
        "market": _market_by_source(current),
        "stock_type": _text(current.get("_stock_type")) or _stock_type(code),
        "previous_date": previous_day,
        "previous_close": str(previous_close),
        "target_date": current_day,
        "target_open": str(_decimal(current.get("開盤價"))),
        "target_high": str(_decimal(current.get("最高價"))),
        "target_low": str(_decimal(current.get("最低價"))),
        "target_close": str(close),
        "delta": str(close - previous_close),
        "return": str(ratio),
        "abs_return_percent": str(abs(ratio) * Decimal("100")),
        "review_10pct": abs(ratio) >= Decimal("0.10"),
        "review_20pct": abs(ratio) >= Decimal("0.20"),
        "review_50pct": abs(ratio) >= Decimal("0.50"),
    }


def _compare_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_code_date: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_code_date[(_code(row.get("證券代號")), _date_key(row.get("日期")))].append(row)
    duplicate_keys = [
        {"stock_code": code, "date": day, "count": len(values)}
        for (code, day), values in by_code_date.items()
        if len(values) > 1
    ]
    dates = sorted({day for _, day in by_code_date})
    per_day: dict[str, dict[str, Any]] = {}
    for day in dates:
        day_rows = [values[0] for (code, row_day), values in by_code_date.items() if row_day == day]
        invalid_ohl: list[dict[str, Any]] = []
        turnover_outside_ohl: list[dict[str, Any]] = []
        invalid_volume: list[dict[str, Any]] = []
        hashes: defaultdict[str, list[str]] = defaultdict(list)
        for row in day_rows:
            code = _code(row.get("證券代號"))
            open_price = _decimal(row.get("開盤價"))
            high_price = _decimal(row.get("最高價"))
            low_price = _decimal(row.get("最低價"))
            close_price = _decimal(row.get("收盤價"))
            volume = _decimal(row.get("成交股數"))
            amount = _decimal(row.get("成交金額"))
            if (
                None in {open_price, high_price, low_price, close_price}
                or high_price is not None
                and low_price is not None
                and (low_price > high_price or open_price < low_price or open_price > high_price or close_price < low_price or close_price > high_price)
                or any(value is not None and value <= 0 for value in (open_price, high_price, low_price, close_price))
            ):
                invalid_ohl.append({"stock_code": code, "row": row})
            if volume is not None and volume < 0:
                invalid_volume.append({"stock_code": code, "reason": "negative_volume", "row": row})
            if volume not in {None, Decimal("0")} and amount is not None and low_price is not None and high_price is not None:
                implied = amount / volume
                if implied < low_price or implied > high_price:
                    turnover_outside_ohl.append(
                        {"stock_code": code, "implied_price": str(implied), "low": str(low_price), "high": str(high_price)}
                    )
            hashes[_value_hash(row)].append(code)
        collisions = [
            {"value_hash": value_hash, "stock_codes": sorted(codes), "count": len(codes)}
            for value_hash, codes in hashes.items()
            if len(codes) >= 5
        ]
        per_day[day] = {
            "row_count": len(day_rows),
            "distinct_codes": len({code for code, row_day in by_code_date if row_day == day}),
            "groups": dict(
                Counter(
                    f"{_market_by_source(row)}|{_text(row.get('_stock_type')) or _stock_type(_code(row.get('證券代號')))}"
                    for row in day_rows
                )
            ),
            "invalid_ohl_count": len(invalid_ohl),
            "invalid_ohl_samples": invalid_ohl[:20],
            "negative_volume_count": len(invalid_volume),
            "implied_price_outside_ohl_count": len(turnover_outside_ohl),
            "implied_price_outside_ohl_samples": turnover_outside_ohl[:20],
            "same_value_hash_collisions_ge5": sorted(collisions, key=lambda item: -item["count"])[:50],
        }

    target_date = TARGET_DATE
    previous_dates = [day for day in dates if day < target_date]
    previous_date = previous_dates[-1] if previous_dates else None
    previous_by_code = {
        code: values[0]
        for (code, day), values in by_code_date.items()
        if day == previous_date
    }
    target_by_code = {
        code: values[0]
        for (code, day), values in by_code_date.items()
        if day == target_date
    }
    jumps: list[dict[str, Any]] = []
    change_mismatch: list[dict[str, Any]] = []
    change_direction_audit = {
        "down_moves_with_positive_abs_change": 0,
        "down_moves_with_missing_symbol": 0,
        "down_moves_with_minus_symbol": 0,
        "down_move_samples": [],
    }
    for code, row in target_by_code.items():
        previous = previous_by_code.get(code)
        close = _decimal(row.get("收盤價"))
        previous_close = _decimal(previous.get("收盤價")) if previous else None
        delta = close - previous_close if close is not None and previous_close is not None else None
        ratio = _safe_ratio(delta, previous_close)
        if ratio is not None:
            jumps.append(
                {
                    "stock_code": code,
                    "market": _market_by_source(row),
                    "stock_type": _text(row.get("_stock_type")) or _stock_type(code),
                    "previous_date": previous_date,
                    "previous_close": str(previous_close),
                    "target_date": target_date,
                    "target_open": str(_decimal(row.get("開盤價"))),
                    "target_high": str(_decimal(row.get("最高價"))),
                    "target_low": str(_decimal(row.get("最低價"))),
                    "target_close": str(close),
                    "delta": str(delta),
                    "return": str(ratio),
                    "abs_return_percent": str(abs(ratio) * Decimal("100")),
                    "review_10pct": abs(ratio) >= Decimal("0.10"),
                    "review_20pct": abs(ratio) >= Decimal("0.20"),
                    "review_50pct": abs(ratio) >= Decimal("0.50"),
                }
            )
        expected_change = delta
        observed_change = _decimal(row.get("漲跌價差"))
        symbol = _text(row.get("漲跌"))
        if delta is not None and delta < 0 and observed_change is not None and observed_change > 0:
            change_direction_audit["down_moves_with_positive_abs_change"] += 1
            if not symbol:
                change_direction_audit["down_moves_with_missing_symbol"] += 1
            elif symbol in {"-", "－"}:
                change_direction_audit["down_moves_with_minus_symbol"] += 1
            if len(change_direction_audit["down_move_samples"]) < 50:
                change_direction_audit["down_move_samples"].append(
                    {
                        "stock_code": code,
                        "previous_close": str(previous_close),
                        "target_close": str(close),
                        "expected_delta": str(delta),
                        "observed_change": str(observed_change),
                        "symbol": symbol,
                        "sign_candidates": row.get("_sign_candidates", {}),
                    }
                )
        signed_match = expected_change is None or observed_change is None or observed_change == expected_change
        absolute_match = expected_change is None or observed_change is None or abs(observed_change) == abs(expected_change)
        expected_sign = "+" if expected_change is not None and expected_change > 0 else "-" if expected_change is not None and expected_change < 0 else "0"
        sign_match = (
            expected_change is None
            or expected_sign == "0"
            or not symbol
            or symbol in {expected_sign, "＋" if expected_sign == "+" else "－"}
        )
        if not signed_match and not absolute_match or not sign_match:
            change_mismatch.append(
                {
                    "stock_code": code,
                    "previous_date": previous_date,
                    "previous_close": str(previous_close),
                    "target_close": str(close),
                    "expected_delta": str(expected_change),
                    "observed_change": str(observed_change),
                    "symbol": symbol,
                    "signed_match": signed_match,
                    "absolute_match": absolute_match,
                    "sign_match": sign_match,
                }
            )
    adjacent: dict[str, dict[str, Any]] = {}
    for previous_day, current_day in zip(dates, dates[1:]):
        previous_rows = {
            code: values[0]
            for (code, day), values in by_code_date.items()
            if day == previous_day
        }
        current_rows = {
            code: values[0]
            for (code, day), values in by_code_date.items()
            if day == current_day
        }
        transition_rows: list[dict[str, Any]] = []
        for code, current in current_rows.items():
            previous = previous_rows.get(code)
            if previous is None:
                continue
            record = _transition_record(code, previous_day, current_day, previous, current)
            if record is not None:
                transition_rows.append(record)
        transition_rows.sort(key=lambda item: Decimal(item["abs_return_percent"]), reverse=True)
        adjacent[f"{previous_day}->{current_day}"] = {
            "previous_row_count": len(previous_rows),
            "current_row_count": len(current_rows),
            "matched_code_count": len(transition_rows),
            "threshold_counts": {
                "abs_return_ge_10pct": sum(item["review_10pct"] for item in transition_rows),
                "abs_return_ge_20pct": sum(item["review_20pct"] for item in transition_rows),
                "abs_return_ge_50pct": sum(item["review_50pct"] for item in transition_rows),
            },
            "threshold_counts_by_group": {
                group: count
                for group, count in sorted(
                    Counter(
                        f"{item['market']}|{item['stock_type']}"
                        for item in transition_rows
                        if item["review_10pct"]
                    ).items()
                )
            },
            "top20_jumps": transition_rows[:20],
        }

    stock_sequences: dict[str, list[dict[str, Any]]] = {}
    for code in ("1256", "1477", "2382", "3207", "9935", "1418", "2330", "3017"):
        sequence = []
        for (row_code, day), values in sorted(by_code_date.items(), key=lambda item: item[0][1]):
            if row_code != code:
                continue
            row = values[0]
            sequence.append(
                {
                    "date": day,
                    "market": _market_by_source(row),
                    "stock_type": _text(row.get("_stock_type")) or _stock_type(code),
                    "open": str(_decimal(row.get("開盤價"))),
                    "high": str(_decimal(row.get("最高價"))),
                    "low": str(_decimal(row.get("最低價"))),
                    "close": str(_decimal(row.get("收盤價"))),
                    "volume": str(_decimal(row.get("成交股數"))),
                    "amount": str(_decimal(row.get("成交金額"))),
                    "change_symbol": _text(row.get("漲跌")),
                    "change": str(_decimal(row.get("漲跌價差"))),
                }
            )
        stock_sequences[code] = sequence

    jumps.sort(key=lambda item: Decimal(item["abs_return_percent"]), reverse=True)
    threshold_counts = {
        "abs_return_ge_10pct": sum(item["review_10pct"] for item in jumps),
        "abs_return_ge_20pct": sum(item["review_20pct"] for item in jumps),
        "abs_return_ge_50pct": sum(item["review_50pct"] for item in jumps),
    }
    return {
        "dates": dates,
        "previous_date_used": previous_date,
        "target_date": target_date,
        "per_day": per_day,
        "duplicate_keys": duplicate_keys,
        "target_vs_previous_count": len(jumps),
        "threshold_counts": threshold_counts,
        "top20_jumps": jumps[:20],
        "all_jumps": jumps,
        "adjacent_transitions": adjacent,
        "stock_sequences": stock_sequences,
        "change_mismatch_count": len(change_mismatch),
        "change_mismatch_samples": change_mismatch[:100],
        "change_direction_audit": change_direction_audit,
    }


def _cross_source(
    db_rows: list[dict[str, Any]],
    source_rows: list[dict[str, Any]],
    source_name: str,
    *,
    executed: bool = True,
) -> dict[str, Any]:
    if not executed or not source_rows:
        return {
            "source": source_name,
            "included": bool(source_rows),
            "executed": executed,
            "status": "not_run" if not executed else "source_missing_or_empty",
            "date_scope": [],
            "db_key_count_scoped": None,
            "source_key_count": 0,
            "matched_key_count": None,
            "missing_in_source_count": None,
            "missing_in_source_samples": [],
            "missing_in_db_count": None,
            "missing_in_db_samples": [],
            "mismatch_count": None,
            "mismatch_samples": [],
        }
    source_dates = {_date_key(row.get("日期")) for row in source_rows}
    db_index = {
        (_code(row.get("證券代號")), _date_key(row.get("日期"))): row
        for row in db_rows
        if not source_dates or _date_key(row.get("日期")) in source_dates
    }
    source_index = {(_code(row.get("證券代號")), _date_key(row.get("日期"))): row for row in source_rows}
    mismatches: list[dict[str, Any]] = []
    matched = 0
    for key, db_row in db_index.items():
        source_row = source_index.get(key)
        if source_row is None:
            continue
        matched += 1
        fields = {}
        for field in ("開盤價", "最高價", "最低價", "收盤價", "成交股數", "成交金額", "漲跌價差"):
            db_value = _decimal(db_row.get(field))
            source_value = _decimal(source_row.get(field))
            if db_value != source_value:
                fields[field] = {"db": str(db_value), source_name: str(source_value)}
        if fields:
            mismatches.append({"stock_code": key[0], "date": key[1], "fields": fields})
    return {
        "source": source_name,
        "included": True,
        "executed": True,
        "status": "completed",
        "date_scope": sorted(source_dates),
        "db_key_count_scoped": len(db_index),
        "source_key_count": len(source_index),
        "matched_key_count": matched,
        "missing_in_source_count": len(set(db_index).difference(source_index)),
        "missing_in_source_samples": [
            {"stock_code": key[0], "date": key[1]}
            for key in sorted(set(db_index).difference(source_index))[:100]
        ],
        "missing_in_db_count": len(set(source_index).difference(db_index)),
        "missing_in_db_samples": [
            {"stock_code": key[0], "date": key[1]}
            for key in sorted(set(source_index).difference(db_index))[:100]
        ],
        "mismatch_count": len(mismatches),
        "mismatch_samples": mismatches[:100],
    }


def _json_default(value: object) -> str:
    return str(value)


def run(db_path: Path, data_root: Path, output_dir: Path, *, include_merged: bool) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    with _open_read_only(db_path) as connection:
        rows = _load_sqlite_rows(connection, COMPARISON_START, COMPARISON_END)
        schema = _table_columns(connection, "daily_prices")
        indexes = [list(row) for row in connection.execute('PRAGMA index_list("daily_prices")')]
        db_count = connection.execute("SELECT COUNT(*) FROM daily_prices").fetchone()[0]
    security_types, markets = _load_security_registry(data_root)
    for row in rows:
        code = _code(row.get("證券代號"))
        row["_stock_type"] = _stock_type(code, security_types)
        row["_market"] = markets.get(code, "")
    sqlite_result = _compare_rows(rows)
    raw_rows = _load_raw_rows(data_root)
    for row in raw_rows:
        code = _code(row.get("證券代號"))
        row["_stock_type"] = _stock_type(code, security_types)
        row["_market"] = markets.get(code, "")
    raw_result = _compare_rows(raw_rows) if raw_rows else {"row_count": 0}
    if include_merged:
        merged_rows, merged_coverage = _load_merged_rows(data_root)
    else:
        merged_rows = []
        merged_coverage = {
            "path": str(data_root / "meta_data" / "stock_data_whole.csv"),
            "exists": None,
            "status": "not_run",
            "total_row_count": None,
            "distinct_date_count": None,
            "date_min": None,
            "date_max": None,
            "target_date_row_count": None,
            "previous_date_row_count": None,
        }
    for row in merged_rows:
        code = _code(row.get("證券代號"))
        row["_stock_type"] = _stock_type(code, security_types)
        row["_market"] = markets.get(code, "")
    merged_cross_source = _cross_source(
        rows,
        merged_rows,
        "merged",
        executed=include_merged,
    )
    if include_merged and not merged_rows and merged_coverage["status"] == "completed_no_target_rows":
        merged_cross_source["status"] = "source_stale_no_target_rows"
        merged_cross_source["coverage_date_max"] = merged_coverage["date_max"]
    result: dict[str, Any] = {
        "audit": {
            "db_path": str(db_path),
            "data_root": str(data_root),
            "output_dir": str(output_dir),
            "read_mode": "sqlite mode=ro + PRAGMA query_only=ON",
            "date_window": [COMPARISON_START, COMPARISON_END],
            "target_date": TARGET_DATE,
            "db_total_rows": db_count,
            "schema": schema,
            "indexes": indexes,
        },
        "sqlite": sqlite_result,
        "raw": {
            "row_count": len(raw_rows),
            "by_market": Counter(_market_by_source(row) for row in raw_rows),
            "audit": raw_result,
            "cross_source": _cross_source(rows, raw_rows, "raw", executed=True),
        },
        "merged": {
            "row_count": len(merged_rows),
            "audit": _compare_rows(merged_rows) if merged_rows else {"row_count": 0},
            "cross_source": merged_cross_source,
            "coverage": merged_coverage,
            "included": include_merged,
        },
    }
    (output_dir / "price_jump_audit.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8"
    )
    with (output_dir / "top20_20260918_to_20260921.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        top20 = sqlite_result["top20_jumps"]
        writer = csv.DictWriter(handle, fieldnames=list(top20[0]) if top20 else ["stock_code"])
        writer.writeheader()
        writer.writerows(top20)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--include-merged", action="store_true")
    args = parser.parse_args()
    result = run(args.db, args.data_root, args.output, include_merged=args.include_merged)
    sqlite_result = result["sqlite"]
    print(json.dumps({
        "dates": sqlite_result["dates"],
        "previous_date_used": sqlite_result["previous_date_used"],
        "target_date": sqlite_result["target_date"],
        "threshold_counts": sqlite_result["threshold_counts"],
        "change_mismatch_count": sqlite_result["change_mismatch_count"],
        "raw_cross_source": result["raw"]["cross_source"],
        "merged_cross_source": result["merged"]["cross_source"],
        "merged_coverage": result["merged"]["coverage"],
        "top20_jumps": sqlite_result["top20_jumps"],
    }, ensure_ascii=False, indent=2, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
