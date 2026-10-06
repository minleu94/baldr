"""唯讀稽核 2026-05-20 歷史價格尖峰與來源分歧。

本工具只讀 Formal SQLite、daily price CSV、merged aggregate 與指定歷史
backup，輸出 dry-run evidence。它不初始化 schema、不使用 immutable、不寫入
正式資料、不執行 collector／repair／回填，也不把 canonical 或 backup 自動
升格為官方真值。
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterable


def _configured_data_root() -> Path:
    """讀 TWStockConfig 的 data_root default factory，不執行其初始化副作用。"""

    try:
        from data_module.config import TWStockConfig

        factory = TWStockConfig.__dataclass_fields__["data_root"].default_factory
        if factory is not None:
            return Path(factory())
    except (ImportError, KeyError, TypeError, ValueError):
        pass
    return Path(os.environ.get("DATA_ROOT", "D:/Min/Python/Project/FA_Data"))


DEFAULT_DATA_ROOT = _configured_data_root()
DEFAULT_DB = DEFAULT_DATA_ROOT / "sqlite" / "twstock.db"
DEFAULT_START = "20260501"
DEFAULT_END = "20260630"
CONTEXT_START = "20260430"
CONTEXT_END = "20260701"
TARGET_DATE = "20260520"
TARGET_SYMBOLS = ("1256", "1477")
BACKUP_NAME = "daily_price_20260520_corrupt_20260624_152726.csv"

NUMERIC_FIELDS = (
    "open",
    "high",
    "low",
    "close",
    "volume_shares",
    "turnover",
    "change_value",
)
CSV_FIELDS = {
    "open": "開盤價",
    "high": "最高價",
    "low": "最低價",
    "close": "收盤價",
    "volume_shares": "成交股數",
    "turnover": "成交金額",
    "change_value": "漲跌價差",
}


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _date_key(value: object) -> str:
    text = _text(value).replace("-", "").replace("/", "")
    return text if len(text) == 8 and text.isdigit() else ""


def _code(value: object) -> str:
    text = _text(value)
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text.zfill(4) if text.isdigit() else text


def _decimal(value: object) -> Decimal | None:
    text = _text(value).replace(",", "")
    if text in {"", "--", "—", "None", "nan", "NaN"}:
        return None
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def _serial_decimal(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _normalize_sign(value: object) -> str:
    text = html.unescape(_text(value))
    text = re.sub(r"<[^>]*>", "", text).strip()
    if text in {"-", "－", "−", "跌", "▼"}:
        return "-"
    if text in {"+", "＋", "漲", "▲"}:
        return "+"
    if text in {"0", "0.0", "—", "--"}:
        return "0"
    return ""


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _open_read_only(path: Path) -> sqlite3.Connection:
    resolved = path.resolve()
    if not resolved.is_file() or resolved.is_symlink():
        raise FileNotFoundError(resolved)
    connection = sqlite3.connect(f"file:{resolved.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    if connection.execute("PRAGMA query_only").fetchone()[0] != 1:
        raise RuntimeError("SQLite query_only was not enabled")
    return connection


def _load_security_registry(path: Path) -> dict[str, str]:
    """讀既有市場 registry；缺項保留 UNKNOWN，不猜市場。"""

    if not path.is_file() or path.is_symlink():
        return {}
    result: dict[str, str] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        for raw in reader:
            symbol = _code(raw.get("stock_id"))
            market = _text(raw.get("type")).upper()
            if symbol and market in {"TWSE", "TPEX"}:
                result[symbol] = market
    return result


def _row_from_mapping(
    raw: dict[str, Any],
    *,
    date_value: str,
    source: str,
    market: str,
) -> dict[str, Any]:
    sign_columns = ("漲跌(+/-)", "漲跌", "涨跌")
    sign_candidates = {
        column: _text(raw.get(column))
        for column in sign_columns
        if column in raw
    }
    sign = next(
        (
            _normalize_sign(value)
            for value in sign_candidates.values()
            if _normalize_sign(value)
        ),
        "",
    )
    result: dict[str, Any] = {
        "date": _date_key(date_value),
        "symbol": _code(raw.get("證券代號") or raw.get("stock_code") or raw.get("code")),
        "name": _text(raw.get("證券名稱") or raw.get("name")),
        "source": source,
        "market": market,
        "sign": sign,
        "sign_candidates": sign_candidates,
    }
    for field, column in CSV_FIELDS.items():
        result[field] = _serial_decimal(_decimal(raw.get(column)))
    return result


def _load_sqlite_rows(
    connection: sqlite3.Connection,
    *,
    start_date: str,
    end_date: str,
    market_map: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    columns = [str(row[1]) for row in connection.execute('PRAGMA table_info("daily_prices")')]
    required = {"日期", "證券代號", *CSV_FIELDS.values()}
    missing = sorted(required.difference(columns))
    if missing:
        raise RuntimeError(f"daily_prices schema missing columns: {missing}")
    sign_columns = [
        column for column in ("漲跌(+/-)", "漲跌", "涨跌") if column in columns
    ]
    projection = ["日期", "證券代號", "證券名稱", *CSV_FIELDS.values(), *sign_columns]
    normalized = 'replace(replace(CAST("日期" AS TEXT), \'-\', \'\'), \'/\', \'\')'
    query = (
        "SELECT "
        + ", ".join(f'"{column}"' for column in projection)
        + f' FROM daily_prices WHERE {normalized} BETWEEN ? AND ? '
        + f'ORDER BY {normalized}, CAST("證券代號" AS TEXT)'
    )
    rows: list[dict[str, Any]] = []
    for values in connection.execute(query, (start_date, end_date)):
        raw = dict(zip(projection, values, strict=True))
        item = _row_from_mapping(
            raw,
            date_value=raw.get("日期"),
            source="sqlite",
            market=(market_map or {}).get(_code(raw.get("證券代號")), "UNKNOWN"),
        )
        rows.append(item)
    return rows, {
        "row_count": len(rows),
        "date_min": min((row["date"] for row in rows), default=None),
        "date_max": max((row["date"] for row in rows), default=None),
        "sign_columns": sign_columns,
    }


def _filename_date(path: Path) -> str:
    match = re.search(r"(?<!\d)(20\d{6})(?!\d)", path.stem)
    return match.group(1) if match else ""


def _load_csv_file(path: Path, *, source: str, market: str, fallback_date: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        for raw in reader:
            item = _row_from_mapping(
                {str(key).strip(): value for key, value in raw.items() if key is not None},
                date_value=raw.get("日期") or raw.get("date") or fallback_date,
                source=source,
                market=market,
            )
            if item["date"] and item["symbol"]:
                rows.append(item)
    return rows


def _load_daily_sources(
    data_root: Path,
    *,
    start_date: str,
    end_date: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    for directory_name, source, market in (
        ("daily_price", "twse_raw", "TWSE"),
        ("daily_price_tpex", "tpex_raw", "TPEX"),
    ):
        directory = data_root / directory_name
        for path in sorted(directory.glob("20*.csv")):
            file_date = _filename_date(path)
            if not file_date or not start_date <= file_date <= end_date:
                continue
            file_rows = _load_csv_file(
                path,
                source=source,
                market=market,
                fallback_date=file_date,
            )
            rows.extend(file_rows)
            files.append(
                {
                    "path": str(path),
                    "date": file_date,
                    "rows": len(file_rows),
                    "sha256": _file_sha256(path),
                }
            )
    return rows, {
        "file_count": len(files),
        "files": files,
        "row_count": len(rows),
    }


def _load_merged_rows(
    path: Path,
    *,
    start_date: str,
    end_date: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not path.is_file() or path.is_symlink():
        return [], {"path": str(path), "status": "missing"}
    rows: list[dict[str, Any]] = []
    date_counts: Counter[str] = Counter()
    total_rows = 0
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        for raw in reader:
            total_rows += 1
            date_value = _date_key(raw.get("日期") or raw.get("date"))
            if date_value:
                date_counts[date_value] += 1
            if not date_value or not start_date <= date_value <= end_date:
                continue
            item = _row_from_mapping(
                {str(key).strip(): value for key, value in raw.items() if key is not None},
                date_value=date_value,
                source="merged",
                market="UNKNOWN",
            )
            if item["symbol"]:
                rows.append(item)
    return rows, {
        "path": str(path),
        "status": "completed",
        "sha256": _file_sha256(path),
        "total_rows": total_rows,
        "row_count": len(rows),
        "distinct_dates": len(date_counts),
        "date_min": min(date_counts, default=None),
        "date_max": max(date_counts, default=None),
        "target_date_rows": date_counts.get(TARGET_DATE, 0),
    }


def _index_rows(
    rows: Iterable[dict[str, Any]],
    *,
    include_market: bool = True,
) -> tuple[dict[tuple[str, ...], dict[str, Any]], list[dict[str, Any]]]:
    indexed: dict[tuple[str, ...], dict[str, Any]] = {}
    duplicate_keys: list[dict[str, Any]] = []
    counts: Counter[tuple[str, ...]] = Counter()
    for row in rows:
        key = (
            (row["date"], row.get("market", "UNKNOWN"), row["symbol"])
            if include_market
            else (row["date"], row["symbol"])
        )
        counts[key] += 1
        indexed.setdefault(key, row)
    for key, count in counts.items():
        if count > 1:
            duplicate_keys.append(
                {
                    "date": key[0],
                    "market": key[1] if include_market else None,
                    "symbol": key[-1],
                    "count": count,
                }
            )
    return indexed, duplicate_keys


def _compare_rows(left: dict[str, Any] | None, right: dict[str, Any] | None) -> list[str]:
    if left is None or right is None:
        return list(NUMERIC_FIELDS) + ["sign"]
    differences: list[str] = []
    for field in NUMERIC_FIELDS:
        left_number = _decimal(left.get(field))
        right_number = _decimal(right.get(field))
        if left_number != right_number:
            differences.append(field)
    if _normalize_sign(left.get("sign")) != _normalize_sign(right.get("sign")):
        differences.append("sign")
    return differences


def _compare_sources(
    left_rows: Iterable[dict[str, Any]],
    right_rows: Iterable[dict[str, Any]],
    *,
    left_name: str,
    right_name: str,
    include_market: bool = True,
    sample_limit: int = 100,
) -> dict[str, Any]:
    left, left_duplicates = _index_rows(left_rows, include_market=include_market)
    right, right_duplicates = _index_rows(right_rows, include_market=include_market)
    all_keys = sorted(set(left) | set(right))
    by_date: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    mismatches: list[dict[str, Any]] = []
    numeric_mismatch_count = 0
    sign_only_mismatch_count = 0
    numeric_and_sign_mismatch_count = 0
    difference_field_counts: Counter[str] = Counter()
    all_mismatch_rows: list[dict[str, Any]] = []
    for key in all_keys:
        day, symbol = key[0], key[-1]
        if key not in left:
            by_date[day]["missing_in_left"] += 1
            continue
        if key not in right:
            by_date[day]["missing_in_right"] += 1
            continue
        differences = _compare_rows(left[key], right[key])
        if differences:
            by_date[day]["mismatch"] += 1
            numeric_differences = [
                field for field in differences if field in NUMERIC_FIELDS
            ]
            if numeric_differences:
                numeric_mismatch_count += 1
            if differences == ["sign"]:
                sign_only_mismatch_count += 1
            elif numeric_differences and "sign" in differences:
                numeric_and_sign_mismatch_count += 1
            for field in differences:
                difference_field_counts[field] += 1
            mismatch_row = {
                "date": day,
                "symbol": symbol,
                "market": key[1] if include_market else None,
                "differing_fields": differences,
                left_name: left[key],
                right_name: right[key],
            }
            all_mismatch_rows.append(mismatch_row)
            if len(mismatches) < sample_limit:
                mismatches.append(mismatch_row)
        else:
            by_date[day]["matched"] += 1
    return {
        "left": left_name,
        "right": right_name,
        "left_row_count": len(left),
        "right_row_count": len(right),
        "left_duplicate_keys": left_duplicates,
        "right_duplicate_keys": right_duplicates,
        "matched_count": sum(item.get("matched", 0) for item in by_date.values()),
        "mismatch_count": sum(item.get("mismatch", 0) for item in by_date.values()),
        "numeric_value_mismatch_count": numeric_mismatch_count,
        "sign_only_mismatch_count": sign_only_mismatch_count,
        "numeric_and_sign_mismatch_count": numeric_and_sign_mismatch_count,
        "difference_field_counts": dict(sorted(difference_field_counts.items())),
        "missing_in_left_count": sum(item.get("missing_in_left", 0) for item in by_date.values()),
        "missing_in_right_count": sum(item.get("missing_in_right", 0) for item in by_date.values()),
        "by_date": {day: dict(stats) for day, stats in sorted(by_date.items())},
        "mismatch_samples": mismatches,
        "mismatch_rows": all_mismatch_rows,
    }


def _load_backup(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not path.is_file() or path.is_symlink():
        return [], {"path": str(path), "status": "missing"}
    rows = _load_csv_file(
        path,
        source="historical_corrupt_backup",
        market="TWSE",
        fallback_date=TARGET_DATE,
    )
    return rows, {
        "path": str(path),
        "status": "completed",
        "sha256": _file_sha256(path),
        "row_count": len(rows),
    }


def _target_sequences(
    sources: dict[str, list[dict[str, Any]]],
    symbols: tuple[str, ...],
) -> dict[str, list[dict[str, Any]]]:
    indexes = {
        name: _index_rows(rows, include_market=False)[0]
        for name, rows in sources.items()
    }
    dates = sorted(
        {
            day
            for index in indexes.values()
            for day, symbol in index
            if symbol in symbols and CONTEXT_START <= day <= CONTEXT_END
        }
    )
    result: dict[str, list[dict[str, Any]]] = {}
    for symbol in symbols:
        sequence: list[dict[str, Any]] = []
        for day in dates:
            entry: dict[str, Any] = {"date": day, "symbol": symbol}
            present = False
            for name, index in indexes.items():
                row = index.get((day, symbol))
                entry[name] = row
                present = present or row is not None
            if present:
                sequence.append(entry)
        result[symbol] = sequence
    return result


def _official_scope(data_root: Path, repo_root: Path) -> dict[str, Any]:
    checked = [
        data_root / "output" / "scheduled" / "daily_price_source_custody" / "twse" / TARGET_DATE,
        data_root / "output" / "scheduled" / "daily_price_source_custody" / "tpex" / TARGET_DATE,
        repo_root / "output" / "v4_ml_daily_price_source_quality_20260907",
        repo_root / "output" / "qa" / "historical_price_spike_20260921" / "official" / "official_capture_verification.json",
        repo_root / "output" / "qa" / "historical_price_spike_20260921" / "official" / "canonical_full_response_comparison.json",
    ]
    found: list[str] = []
    for path in checked:
        if path.is_dir():
            found.extend(str(item) for item in path.rglob("comparison.json"))
        elif path.is_file() and path.name == "official_capture_verification.json":
            found.append(str(path))
    verification: dict[str, Any] = {}
    full_comparison: dict[str, Any] = {}
    verification_path = checked[-1]
    if verification_path.is_file() and verification_path.name == "canonical_full_response_comparison.json":
        try:
            payload = json.loads(verification_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            payload = {}
        if isinstance(payload, dict):
            comparison = payload.get("comparison") or {}
            numeric = comparison.get("numeric_mismatch") or {}
            sign = comparison.get("sign_mismatch") or {}
            none_suspension = comparison.get("none_suspension") or {}
            full_comparison = {
                "path": str(verification_path),
                "date": payload.get("date"),
                "canonical_row_count": (payload.get("canonical_index") or {}).get("row_count"),
                "official_table_row_count": (payload.get("official_index") or {}).get("row_count"),
                "matched": comparison.get("matched"),
                "semantically_matched_after_neutral_sign_encoding": comparison.get(
                    "semantically_matched_after_neutral_sign_encoding"
                ),
                "numeric_mismatch_count": numeric.get("row_count"),
                "sign_mismatch_count": sign.get("row_count"),
                "none_suspension_count": none_suspension.get("overlap_count"),
                "read_only": payload.get("read_only"),
                "http_was_called": payload.get("http_was_called"),
                "formal_data_written": payload.get("formal_data_written"),
            }
    verification_path = checked[-2]
    if verification_path.is_file():
        try:
            payload = json.loads(verification_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            payload = {}
        if isinstance(payload, dict):
            verification = {
                "path": str(verification_path),
                "receipt_verified": payload.get("receipt_verified"),
                "comparison_verified": payload.get("comparison_verified"),
                "wire_sha256": (payload.get("wire") or {}).get("sha256"),
                "decoded_sha256": (payload.get("decoded") or {}).get("sha256"),
                "top_level_date": (payload.get("response_identity") or {}).get("top_level_date"),
                "table_row_count": (payload.get("response_identity") or {}).get("table_row_count"),
                "verified_symbols": sorted((payload.get("official_rows") or {}).keys()),
                "full_response_rows_present": (payload.get("custody_scope") or {}).get("full_response_rows_present"),
            }
    return {
        "checked_paths": [str(path) for path in checked],
        "found_comparison_files": sorted(found),
        "official_capture_verification": verification,
        "official_full_response_comparison": full_comparison,
        "target_symbols_in_known_33_file": False,
        "interpretation": (
            "既有 2026-09-07 33 檔 comparison 名單不含 1256／1477；"
            "另有完整 TWSE response 的 read-only verification artifact，"
            "本稽核只採其明示的 1256／1477 rows，不把 33 檔 comparison 名單擴張解讀。"
        ),
    }


def _validate_output_dir(output_dir: Path, source_roots: Iterable[Path]) -> Path:
    candidate = output_dir.expanduser()
    if candidate.is_symlink():
        raise ValueError("audit output must not be a symlink")
    resolved = candidate.resolve()
    for source_root in source_roots:
        root = source_root.expanduser().resolve()
        if resolved == root or root in resolved.parents:
            raise ValueError(f"audit output is inside a source root: {resolved}")
    return resolved


def audit(
    *,
    data_root: Path,
    sqlite_path: Path,
    output_dir: Path,
    start_date: str = DEFAULT_START,
    end_date: str = DEFAULT_END,
    include_merged: bool = True,
) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    context_start = min(CONTEXT_START, start_date)
    context_end = max(CONTEXT_END, end_date)
    market_map = _load_security_registry(data_root / "meta_data" / "companies_cleaned.csv")
    with _open_read_only(sqlite_path) as connection:
        sqlite_rows, sqlite_meta = _load_sqlite_rows(
            connection,
            start_date=context_start,
            end_date=context_end,
            market_map=market_map,
        )
    raw_rows, raw_meta = _load_daily_sources(
        data_root,
        start_date=context_start,
        end_date=context_end,
    )
    raw_markets: dict[str, set[str]] = defaultdict(set)
    for row in raw_rows:
        raw_markets[row["symbol"]].add(row["market"])
    resolved_from_raw = 0
    for row in sqlite_rows:
        if row["market"] == "UNKNOWN" and len(raw_markets.get(row["symbol"], set())) == 1:
            row["market"] = next(iter(raw_markets[row["symbol"]]))
            resolved_from_raw += 1
    merged_rows: list[dict[str, Any]] = []
    merged_meta: dict[str, Any] = {"status": "not_run"}
    merged_path = data_root / "meta_data" / "stock_data_whole.csv"
    if include_merged:
        merged_rows, merged_meta = _load_merged_rows(
            merged_path,
            start_date=context_start,
            end_date=context_end,
        )
    backup_rows, backup_meta = _load_backup(
        data_root / "meta_data" / "backup" / BACKUP_NAME
    )
    source_rows = {
        "sqlite": sqlite_rows,
        "canonical_daily_csv": raw_rows,
        "historical_corrupt_backup": backup_rows,
    }
    if include_merged:
        source_rows["merged"] = merged_rows
    comparisons = {
        "sqlite_vs_canonical_daily_csv": _compare_sources(
            sqlite_rows,
            raw_rows,
            left_name="sqlite",
            right_name="canonical_daily_csv",
            include_market=True,
        ),
        "historical_corrupt_backup_vs_canonical_daily_csv": _compare_sources(
            backup_rows,
            raw_rows,
            left_name="historical_corrupt_backup",
            right_name="canonical_daily_csv",
            include_market=True,
        ),
    }
    if include_merged:
        comparisons["sqlite_vs_merged"] = _compare_sources(
            sqlite_rows,
            merged_rows,
            left_name="sqlite",
            right_name="merged",
            include_market=False,
        )
    target_db_index, _ = _index_rows(sqlite_rows, include_market=False)
    target_raw_index, _ = _index_rows(raw_rows, include_market=False)
    target_backup_index, _ = _index_rows(backup_rows, include_market=False)
    target_merged_index, _ = _index_rows(merged_rows, include_market=False)
    target_values = {
        symbol: {
            "date": TARGET_DATE,
            "symbol": symbol,
            "sqlite": target_db_index.get((TARGET_DATE, symbol)),
            "canonical_daily_csv": target_raw_index.get((TARGET_DATE, symbol)),
            "historical_corrupt_backup": target_backup_index.get((TARGET_DATE, symbol)),
            "merged": target_merged_index.get((TARGET_DATE, symbol)) if include_merged else None,
        }
        for symbol in TARGET_SYMBOLS
    }
    result = {
        "schema_version": "historical-price-spike-audit-20260921.v1",
        "read_only": True,
        "sqlite_mode": "mode=ro + PRAGMA query_only=ON",
        "transaction_note": (
            "rows were read through one query_only connection; the SQLite file hash is a "
            "path-level byte read at audit time, not a transaction snapshot hash"
        ),
        "scope": {
            "requested_start": start_date,
            "requested_end": end_date,
            "context_start": context_start,
            "context_end": context_end,
            "target_date": TARGET_DATE,
            "target_symbols": list(TARGET_SYMBOLS),
        },
        "source_files": {
            "sqlite": {
                "path": str(sqlite_path.resolve()),
                "sha256": _file_sha256(sqlite_path),
                "hash_scope": "path bytes read at audit time; not a transaction snapshot",
            },
            "market_registry": {
                "path": str((data_root / "meta_data" / "companies_cleaned.csv").resolve()),
                "status": "read_only_registry_for_market_grain",
            },
            "canonical_daily_csv": raw_meta,
            "merged": merged_meta,
            "historical_corrupt_backup": backup_meta,
        },
        "row_metadata": {
            "sqlite": sqlite_meta,
            "canonical_daily_csv": {"row_count": len(raw_rows), "file_count": raw_meta["file_count"]},
            "merged": {"row_count": len(merged_rows), "status": merged_meta.get("status")},
            "historical_corrupt_backup": backup_meta,
        },
        "comparisons": comparisons,
        "target_date_values": target_values,
        "target_sequences": _target_sequences(source_rows, TARGET_SYMBOLS),
        "official_custody": _official_scope(data_root, repo_root),
        "repair_policy": {
            "repair_performed": False,
            "formal_data_written": False,
            "recommended_next_step": (
                "保留 formal SQLite 與 raw/backup 不變；由 owner 依逐列 evidence 建立"
                "隔離修復方案，先核准來源與受影響 row，再另行執行受控修復。"
            ),
        },
    }
    result["market_resolution"] = {
        "registry_symbol_count": len(market_map),
        "sqlite_unknown_resolved_from_unique_raw_market": resolved_from_raw,
        "ambiguous_raw_market_symbols": sorted(
            symbol for symbol, markets in raw_markets.items() if len(markets) > 1
        ),
    }
    source_roots = (
        sqlite_path.parent,
        data_root / "daily_price",
        data_root / "daily_price_tpex",
        data_root / "meta_data",
        data_root / "meta_data" / "backup",
    )
    resolved_output = _validate_output_dir(output_dir, source_roots)
    encoded = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    resolved_output.mkdir(parents=True, exist_ok=True)
    output_path = resolved_output / "historical_price_spike_audit.json"
    if output_path.is_symlink():
        raise ValueError("audit output file must not be a symlink")
    output_path.write_text(encoded + "\n", encoding="utf-8")
    summary = {
        "output": str(output_path.resolve()),
        "target_values": target_values,
        "sqlite_vs_raw_target_mismatch": comparisons["sqlite_vs_canonical_daily_csv"]["by_date"].get(TARGET_DATE, {}),
        "sqlite_vs_raw_total_mismatch": comparisons["sqlite_vs_canonical_daily_csv"]["mismatch_count"],
        "official_comparison_files": result["official_custody"]["found_comparison_files"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--sqlite", type=Path)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--output", type=Path, default=Path("output/qa/historical_price_spike_20260921"))
    parser.add_argument("--skip-merged", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    data_root = (args.data_root or DEFAULT_DATA_ROOT).expanduser()
    sqlite_path = (args.sqlite or data_root / "sqlite" / "twstock.db").expanduser()
    audit(
        data_root=data_root,
        sqlite_path=sqlite_path,
        output_dir=args.output,
        start_date=args.start,
        end_date=args.end,
        include_merged=not args.skip_merged,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
