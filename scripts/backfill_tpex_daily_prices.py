from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import sqlite3
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd
import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data_module.config import TWStockConfig
from data_module.official_daily_price_custody import (
    MAX_RESPONSE_BYTES,
    _write_create_only,
    persist_official_daily_price_response,
)
from data_module.tpex_daily_price_backfill import (
    apply_tpex_daily_price_backfill,
    build_tpex_daily_price_plan,
    normalize_tpex_daily_price_rows,
)
from data_module.tpex_daily_price_source import _rows_from_after_trading_response

TPEX_DAILY_CLOSE_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
TPEX_AFTER_TRADING_OTC_URL = "https://www.tpex.org.tw/www/zh-tw/afterTrading/otc"
TPEX_OFFICIAL_HOST = "www.tpex.org.tw"
TPEX_REQUIRED_SYMBOL = "1569"
_KNOWN_DIAGNOSTIC_CODES = frozenset(
    {
        "tpex_daily_price.invalid_stock_code",
        "tpex_daily_price.invalid_price",
    }
)
_NUMERIC_COLUMNS = frozenset(
    {
        "成交股數",
        "成交筆數",
        "成交金額",
        "開盤價",
        "最高價",
        "最低價",
        "收盤價",
        "漲跌價差",
        "最後揭示買價",
        "最後揭示買量",
        "最後揭示賣價",
        "最後揭示賣量",
        "本益比",
    }
)
_COLUMN_ALIASES = {
    "漲跌": ("漲跌", "涨跌", "漲跌(+/-)"),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dry-run or apply TPEX daily price backfill.")
    parser.add_argument("--db-file", type=Path, default=None)
    parser.add_argument("--backup-dir", type=Path, default=None)
    parser.add_argument("--source-json", type=Path, default=None)
    parser.add_argument(
        "--source-raw",
        type=Path,
        default=None,
        help="官方 afterTrading/otc 原始 response bytes；與 --capture-metadata 一起使用",
    )
    parser.add_argument(
        "--capture-metadata",
        type=Path,
        default=None,
        help="保存 raw provenance、官方 URL、參數與實際 captured_at 的 JSON",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help="raw 模式的資料根目錄；dry-run 也必須明確指定",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="raw 模式的 custody 輸出根目錄；dry-run 也必須明確指定",
    )
    parser.add_argument(
        "--required-symbol",
        type=str,
        default=None,
        help="raw 模式必須明確指定 1569",
    )
    parser.add_argument("--date", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", choices=["apply-tpex-daily-price-backfill"], default=None)
    args = parser.parse_args(argv)

    if args.source_raw is not None or args.capture_metadata is not None:
        return _run_precaptured_after_trading_mode(args)

    config = TWStockConfig()
    db_file = args.db_file or config.db_file
    backup_dir = args.backup_dir or config.backup_dir
    source_rows = _load_source_rows(args.source_json)

    if args.apply:
        if args.confirm != "apply-tpex-daily-price-backfill":
            print("Applying TPEX daily price backfill requires --confirm apply-tpex-daily-price-backfill")
            return 2
        result = apply_tpex_daily_price_backfill(
            db_file=db_file,
            backup_dir=backup_dir,
            source_rows=source_rows,
            fallback_date=args.date,
            strict=False,
        )
        print(result.plan.to_markdown())
        print(f"- applied: {str(result.applied).lower()}")
        print(f"- inserted_count: {result.inserted_count}")
        print(f"- backup_file: {result.backup_file or 'none'}")
        return 0 if result.applied else 1

    plan = build_tpex_daily_price_plan(
        db_file=db_file,
        source_rows=source_rows,
        fallback_date=args.date,
        strict=False,
    )
    print(plan.to_markdown())
    for diagnostic in plan.diagnostics:
        print(f"- {diagnostic.code}: {diagnostic.stock_code} {diagnostic.message}".rstrip())
    return 0 if plan.ready_for_apply else 1


def _run_precaptured_after_trading_mode(args: argparse.Namespace) -> int:
    """受控處理一個已保存的官方 afterTrading response。"""

    try:
        if args.source_raw is None or args.capture_metadata is None:
            raise ValueError("raw 模式必須同時提供 --source-raw 與 --capture-metadata")
        if args.source_json is not None:
            raise ValueError("raw 模式不可同時使用 --source-json")
        if args.apply and args.dry_run:
            raise ValueError("--apply 與 --dry-run 不可同時使用")
        if args.required_symbol != TPEX_REQUIRED_SYMBOL:
            raise ValueError(
                f"raw 模式必須明確指定 --required-symbol {TPEX_REQUIRED_SYMBOL}"
            )
        if args.data_root is None or args.output_root is None or args.db_file is None:
            raise ValueError(
                "raw 模式必須明確指定 --data-root、--output-root 與 --db-file"
            )
        if args.backup_dir is None:
            raise ValueError("raw 模式必須明確指定 --backup-dir")

        requested_date = _date_key(args.date)
        data_root = Path(args.data_root).resolve()
        output_root = Path(args.output_root).resolve()
        db_file = Path(args.db_file).resolve()
        backup_dir = Path(args.backup_dir).resolve()
        _validate_raw_mode_paths(
            data_root=data_root,
            output_root=output_root,
            db_file=db_file,
            backup_dir=backup_dir,
        )
        capture = _load_precaptured_after_trading(
            raw_path=Path(args.source_raw),
            metadata_path=Path(args.capture_metadata),
            requested_date=requested_date,
            required_symbol=TPEX_REQUIRED_SYMBOL,
        )
        csv_path = data_root / "daily_price_tpex" / f"{requested_date}.csv"
        csv_bytes = _canonical_csv_bytes(capture["normalized_rows"])
        csv_state = _existing_csv_state(csv_path, csv_bytes)
        plan = build_tpex_daily_price_plan(
            db_file=db_file,
            source_rows=capture["source_rows"],
            fallback_date=requested_date,
            strict=False,
        )
        conflicts = _find_db_conflicts(
            db_file=db_file,
            rows=capture["normalized_rows"],
            date_key=requested_date,
        )
        ready = csv_state != "conflict" and not conflicts and not plan.diagnostics
        _print_precaptured_plan(
            capture=capture,
            requested_date=requested_date,
            csv_path=csv_path,
            csv_state=csv_state,
            db_file=db_file,
            backup_dir=backup_dir,
            plan=plan,
            conflicts=conflicts,
            ready=ready,
            applying=args.apply,
        )
        if not ready:
            return 1
        if not args.apply:
            return 0
        if args.confirm != "apply-tpex-daily-price-backfill":
            print(
                "Applying TPEX daily price backfill requires "
                "--confirm apply-tpex-daily-price-backfill"
            )
            return 2

        custody = persist_official_daily_price_response(
            output_root=output_root,
            venue="tpex",
            source_id="tpex.daily_close_quotes",
            source_date=requested_date,
            requested_url=str(capture["requested_url"]),
            final_url=str(capture["final_url"]),
            request_parameters=dict(capture["request_parameters"]),
            http_status=int(capture["http_status"]),
            response_headers=dict(capture["response_headers"]),
            raw_response=bytes(capture["raw_response"]),
            captured_at=capture["captured_at"],
            row_count=len(capture["normalized_rows"]),
            source_columns=tuple(capture["normalized_rows"][0].keys()),
            parser_id="tpex.daily_close_quotes.v1",
            historical_backfill_claimed=True,
        )
        _write_create_only(csv_path, csv_bytes)
        applied = apply_tpex_daily_price_backfill(
            db_file=db_file,
            backup_dir=backup_dir,
            source_rows=capture["source_rows"],
            fallback_date=requested_date,
            strict=False,
            insert_only=True,
        )
        if applied.applied and applied.inserted_count != applied.plan.insert_count:
            raise ValueError(
                "DB apply inserted_count 與 preflight insert_count 不一致；拒絕宣稱成功"
            )
        if not applied.applied and applied.plan.insert_count > 0:
            raise ValueError(
                "DB apply 未實際套用但仍有待插入 rows；拒絕宣稱成功"
            )
        print(f"- custody_path: {custody['receipt_path']}")
        print(f"- raw_response_path: {custody['raw_response_path']}")
        print(f"- csv_path: {csv_path}")
        print(f"- applied: {str(applied.applied).lower()}")
        print(f"- inserted_count: {applied.inserted_count}")
        print(f"- backup_file: {applied.backup_file or 'none'}")
        _verify_precaptured_db_readback(
            db_file=db_file,
            rows=capture["normalized_rows"],
            date_key=requested_date,
            required_symbol=TPEX_REQUIRED_SYMBOL,
        )
        print("- readback_verified: true")
        return 0
    except (OSError, ValueError, json.JSONDecodeError, sqlite3.Error) as exc:
        print(f"- status: rejected")
        print(f"- reason: {exc}")
        return 1


def _validate_raw_mode_paths(
    *,
    data_root: Path,
    output_root: Path,
    db_file: Path,
    backup_dir: Path,
) -> None:
    if data_root == output_root:
        raise ValueError("data_root 與 output_root 必須是不同根目錄")
    if not _path_is_within(db_file, data_root):
        raise ValueError("db_file 必須位於 data_root 之下")
    if not _path_is_within(backup_dir, data_root):
        raise ValueError("backup_dir 必須位於 data_root 之下")
    if not db_file.exists() or not db_file.is_file():
        raise ValueError(f"db_file 不存在，raw 模式不會建立資料庫：{db_file}")


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _load_precaptured_after_trading(
    *,
    raw_path: Path,
    metadata_path: Path,
    requested_date: str,
    required_symbol: str,
) -> dict[str, Any]:
    if raw_path.is_symlink() or not raw_path.is_file():
        raise ValueError(f"source raw 必須是一般檔案：{raw_path}")
    if metadata_path.is_symlink() or not metadata_path.is_file():
        raise ValueError(f"capture metadata 必須是一般檔案：{metadata_path}")
    raw_response = raw_path.read_bytes()
    if not raw_response:
        raise ValueError("source raw 不可為空")
    if len(raw_response) > MAX_RESPONSE_BYTES:
        raise ValueError("source raw 超過 bounded response 大小")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(metadata, Mapping):
        raise ValueError("capture metadata 必須是 JSON object")

    _validate_raw_provenance(
        metadata=metadata,
        raw_path=raw_path,
        metadata_path=metadata_path,
        raw_response=raw_response,
        requested_date=requested_date,
    )
    try:
        payload = json.loads(raw_response.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("afterTrading raw 不是有效 UTF-8 JSON") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("raw 模式只接受 official afterTrading JSON object")
    table = _select_after_trading_table(
        payload.get("tables"),
        requested_date=requested_date,
        required_symbol=required_symbol,
    )
    payload_for_parser = dict(payload)
    payload_for_parser["tables"] = [table]
    source_rows = _rows_from_after_trading_response(
        payload_for_parser,
        fallback_date=requested_date,
    )
    normalized = normalize_tpex_daily_price_rows(
        source_rows,
        fallback_date=requested_date,
        strict=True,
    )
    if not normalized.rows:
        raise ValueError("raw afterTrading 沒有可正規化的 TPEX rows")
    normalized_rows = list(normalized.rows)
    normalized_dates = {str(row.get("日期")) for row in normalized_rows}
    if normalized_dates != {requested_date}:
        raise ValueError("normalized rows 含有非 requested date")
    if not any(str(row.get("證券代號")) == required_symbol for row in normalized_rows):
        raise ValueError(f"raw payload 缺少 required symbol {required_symbol} 的有效收盤列")
    invalid_required = [
        diagnostic
        for diagnostic in normalized.diagnostics
        if str(diagnostic.stock_code or "") == required_symbol
    ]
    unexpected_diagnostics = [
        diagnostic
        for diagnostic in normalized.diagnostics
        if diagnostic.code not in _KNOWN_DIAGNOSTIC_CODES
    ]
    if invalid_required or unexpected_diagnostics:
        raise ValueError("strict diagnostics 包含 required symbol 或未知診斷")
    return {
        "raw_response": raw_response,
        "requested_url": str(metadata["requested_url"]),
        "final_url": str(metadata["final_url"]),
        "request_parameters": dict(metadata["request_parameters"]),
        "response_headers": dict(metadata["response_headers"]),
        "http_status": int(metadata["http_status"]),
        "captured_at": _parse_aware_datetime(metadata["captured_at"]),
        "source_rows": source_rows,
        "normalized_rows": normalized_rows,
        "diagnostic_count": len(normalized.diagnostics),
        "diagnostic_codes": _diagnostic_counts(normalized.diagnostics),
        "raw_response_sha256": _sha256(raw_response),
    }


def _select_after_trading_table(
    tables: object,
    *,
    requested_date: str,
    required_symbol: str,
) -> Mapping[str, object]:
    """選擇指定日期、且具行情欄位與目標證券的 afterTrading table。"""

    if not isinstance(tables, list) or not tables:
        raise ValueError("afterTrading raw 缺少 tables")
    date_candidates: list[Mapping[str, object]] = []
    symbol_candidates: list[Mapping[str, object]] = []
    for candidate in tables:
        if not isinstance(candidate, Mapping):
            continue
        try:
            candidate_date = _date_key(str(candidate.get("date", "")))
        except ValueError:
            continue
        if candidate_date != requested_date:
            continue
        fields = candidate.get("fields")
        data_rows = candidate.get("data")
        if not isinstance(fields, list) or not isinstance(data_rows, list):
            continue
        field_names = [str(field) for field in fields]
        normalized_fields = [field.replace(" ", "").replace("<br>", "") for field in field_names]
        if not any("代號" in field for field in normalized_fields):
            continue
        if not any("收盤" in field for field in normalized_fields):
            continue
        date_candidates.append(candidate)
        code_indexes = [
            index for index, field in enumerate(normalized_fields) if "代號" in field
        ]
        if any(
            isinstance(row, list)
            and any(
                index < len(row) and str(row[index]).strip() == required_symbol
                for index in code_indexes
            )
            for row in data_rows
        ):
            symbol_candidates.append(candidate)
    if len(symbol_candidates) > 1:
        raise ValueError(
            "afterTrading requested date 有多個含 required symbol 的行情 table，拒絕猜測"
        )
    if symbol_candidates:
        return symbol_candidates[0]
    if date_candidates:
        raise ValueError(
            f"afterTrading requested date 缺少 required symbol {required_symbol} 的行情 table"
        )
    raise ValueError("afterTrading raw 找不到指定日期且具行情欄位的 table")


def _validate_raw_provenance(
    *,
    metadata: Mapping[str, object],
    raw_path: Path,
    metadata_path: Path,
    raw_response: bytes,
    requested_date: str,
) -> None:
    if str(metadata.get("source_authority", "")).strip().lower() != "tpex":
        raise ValueError("raw provenance source_authority 必須是 tpex")
    if str(metadata.get("source_id", "")).strip() != "tpex.daily_close_quotes":
        raise ValueError("raw provenance source_id 不符合 TPEX daily close contract")
    if _date_key(str(metadata.get("requested_date", ""))) != requested_date:
        raise ValueError("capture metadata requested_date 不等於 CLI date")
    for field_name in ("requested_url", "final_url"):
        _validate_official_after_trading_url(metadata.get(field_name), field_name)
    request_parameters = metadata.get("request_parameters")
    if not isinstance(request_parameters, Mapping):
        raise ValueError("capture metadata 缺少 request_parameters object")
    expected_parameters = {
        "date": f"{requested_date[:4]}/{requested_date[4:6]}/{requested_date[6:8]}",
        "type": "EW",
        "response": "json",
    }
    for key, expected in expected_parameters.items():
        if str(request_parameters.get(key, "")) != expected:
            raise ValueError(f"request_parameters[{key}] 不符合 production afterTrading 參數")
    if not isinstance(metadata.get("response_headers"), Mapping):
        raise ValueError("capture metadata 缺少 response_headers object")
    status = metadata.get("http_status")
    if isinstance(status, bool) or not isinstance(status, int) or status != 200:
        raise ValueError("capture metadata http_status 必須是 200")
    captured_at = _parse_aware_datetime(metadata.get("captured_at"))
    if captured_at > datetime.now(timezone.utc):
        raise ValueError("captured_at 不可晚於目前 checked clock")
    declared_bytes = metadata.get("raw_response_bytes")
    if isinstance(declared_bytes, bool) or not isinstance(declared_bytes, int):
        raise ValueError("capture metadata raw_response_bytes 必須是整數")
    if declared_bytes != len(raw_response):
        raise ValueError("raw_response_bytes 與實際 raw 長度不一致")
    expected_hash = _sha256(raw_response)
    if str(metadata.get("raw_response_sha256", "")).strip().lower() != expected_hash:
        raise ValueError("raw_response_sha256 與實際 raw 不一致")
    declared_path = metadata.get("raw_response_path")
    if not isinstance(declared_path, str) or not declared_path.strip():
        raise ValueError("capture metadata 缺少 raw_response_path")
    path_value = Path(declared_path)
    if not path_value.is_absolute():
        path_value = metadata_path.parent / path_value
    if path_value.resolve() != raw_path.resolve():
        raise ValueError("raw_response_path 與 --source-raw 不一致")


def _validate_official_after_trading_url(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"capture metadata 缺少 {field_name}")
    parsed = urlparse(value)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"{field_name} URL port 無效") from exc
    if (
        parsed.scheme.lower() != "https"
        or parsed.hostname != TPEX_OFFICIAL_HOST
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.path.rstrip("/") != "/www/zh-tw/afterTrading/otc"
    ):
        raise ValueError(f"{field_name} 必須是 official HTTPS afterTrading/otc URL")


def _parse_aware_datetime(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("captured_at 必須是 timezone-aware ISO datetime")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("captured_at 不是有效 ISO datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("captured_at 必須包含 timezone")
    return parsed.astimezone(timezone.utc)


def _canonical_csv_bytes(rows: list[Mapping[str, object]]) -> bytes:
    buffer = io.BytesIO()
    pd.DataFrame(rows).to_csv(buffer, index=False, encoding="utf-8-sig")
    return buffer.getvalue()


def _existing_csv_state(path: Path, candidate: bytes) -> str:
    if not path.exists():
        return "absent"
    if path.is_symlink():
        raise ValueError(f"CSV 目標不可是 symlink：{path}")
    return "identical" if path.read_bytes() == candidate else "conflict"


def _find_db_conflicts(
    *,
    db_file: Path,
    rows: list[Mapping[str, object]],
    date_key: str,
) -> list[dict[str, object]]:
    uri = db_file.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = sqlite3.Row
        columns = tuple(
            row[1]
            for row in conn.execute("PRAGMA table_info(daily_prices)").fetchall()
        )
        if not columns:
            raise ValueError("daily_prices table 不存在，raw 模式不會初始化 DB")
        existing = conn.execute(
            'SELECT * FROM daily_prices WHERE "日期" = ?',
            (date_key,),
        ).fetchall()
    by_key = {
        (str(row["證券代號"]), str(row["日期"])): row
        for row in existing
        if row["證券代號"] is not None and row["日期"] is not None
    }
    conflicts: list[dict[str, object]] = []
    for source_row in rows:
        key = (str(source_row["證券代號"]), str(source_row["日期"]))
        current = by_key.get(key)
        if current is None:
            continue
        different: list[str] = []
        for source_column, expected in source_row.items():
            db_column = _find_db_column(source_column, columns)
            if db_column is None:
                continue
            if not _values_equal(source_column, expected, current[db_column]):
                different.append(source_column)
        if different:
            conflicts.append(
                {
                    "symbol": key[0],
                    "date": key[1],
                    "different_columns": different,
                }
            )
    return conflicts


def _verify_precaptured_db_readback(
    *,
    db_file: Path,
    rows: list[Mapping[str, object]],
    date_key: str,
    required_symbol: str,
) -> None:
    """寫入後重新以唯讀連線核對目標 rows，避免假報 apply 成功。"""

    uri = db_file.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = sqlite3.Row
        columns = tuple(
            row[1]
            for row in conn.execute("PRAGMA table_info(daily_prices)").fetchall()
        )
        required_columns = ("開盤價", "最高價", "最低價", "收盤價", "成交股數")
        missing_required = [
            column
            for column in required_columns
            if _find_db_column(column, columns) is None
        ]
        if missing_required:
            raise ValueError(
                "DB readback 缺少 required OHLC/volume 欄位："
                + ", ".join(missing_required)
            )
        current_rows = conn.execute(
            'SELECT * FROM daily_prices WHERE "日期" = ?',
            (date_key,),
        ).fetchall()
    by_key = {
        (str(row["證券代號"]), str(row["日期"])): row
        for row in current_rows
        if row["證券代號"] is not None and row["日期"] is not None
    }
    required_key = (required_symbol, date_key)
    if required_key not in by_key:
        raise ValueError(f"DB readback 缺少 required symbol {required_symbol}")
    for source_row in rows:
        key = (str(source_row["證券代號"]), str(source_row["日期"]))
        current = by_key.get(key)
        if current is None:
            raise ValueError(f"DB readback 缺少 {key[0]} {key[1]} row")
        for source_column, expected in source_row.items():
            db_column = _find_db_column(source_column, columns)
            if db_column is None:
                continue
            if not _values_equal(source_column, expected, current[db_column]):
                raise ValueError(
                    f"DB readback mismatch: {key[0]} {key[1]} {source_column}"
                )


def _find_db_column(source_column: str, columns: tuple[str, ...]) -> str | None:
    aliases = _COLUMN_ALIASES.get(source_column, (source_column,))
    return next((column for column in aliases if column in columns), None)


def _values_equal(column: str, expected: object, actual: object) -> bool:
    if _is_empty_value(expected) and _is_empty_value(actual):
        return True
    if column in _NUMERIC_COLUMNS:
        try:
            return Decimal(str(expected).replace(",", "")) == Decimal(
                str(actual).replace(",", "")
            )
        except (InvalidOperation, ValueError):
            return False
    return str(expected).strip() == str(actual).strip()


def _is_empty_value(value: object) -> bool:
    return value is None or str(value).strip().lower() in {"", "none", "nan", "nat"}


def _diagnostic_counts(diagnostics: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for diagnostic in diagnostics:
        counts[diagnostic.code] = counts.get(diagnostic.code, 0) + 1
    return dict(sorted(counts.items()))


def _print_precaptured_plan(
    *,
    capture: Mapping[str, Any],
    requested_date: str,
    csv_path: Path,
    csv_state: str,
    db_file: Path,
    backup_dir: Path,
    plan: Any,
    conflicts: list[dict[str, object]],
    ready: bool,
    applying: bool,
) -> None:
    print("# TPEX pre-captured single-day backfill plan")
    print("- mode: official_after_trading_raw")
    print(f"- requested_date: {requested_date}")
    print(f"- source_date: {requested_date}")
    print(f"- captured_at: {capture['captured_at'].isoformat()}")
    print("- historical_pit_status: not_proven_by_after_close_capture")
    print("- formal_source_contract_eligible: false")
    print(f"- raw_response_sha256: {capture['raw_response_sha256']}")
    print(f"- raw_response_bytes: {len(capture['raw_response'])}")
    print(f"- normalized_row_count: {len(capture['normalized_rows'])}")
    print(f"- strict_diagnostic_count: {capture['diagnostic_count']}")
    print(f"- strict_diagnostic_codes: {json.dumps(capture['diagnostic_codes'], ensure_ascii=False)}")
    print(f"- csv_path: {csv_path}")
    print(f"- csv_state: {csv_state}")
    print(f"- db_file: {db_file}")
    print(f"- backup_dir: {backup_dir}")
    print(f"- existing_count: {plan.existing_count}")
    print(f"- insert_count: {plan.insert_count}")
    print(f"- db_conflict_count: {len(conflicts)}")
    if conflicts:
        print(f"- first_db_conflict: {json.dumps(conflicts[0], ensure_ascii=False)}")
    print(f"- ready_for_apply: {str(ready).lower()}")
    print(f"- dry_run: {str(not applying).lower()}")


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _date_key(value: object) -> str:
    text = str(value or "").strip().replace("-", "").replace("/", "")
    if len(text) == 8 and text.isdigit():
        datetime.strptime(text, "%Y%m%d")
        return text
    if len(text) == 7 and text.isdigit():
        year = int(text[:3]) + 1911
        normalized = f"{year:04d}{text[3:5]}{text[5:7]}"
        datetime.strptime(normalized, "%Y%m%d")
        return normalized
    raise ValueError(f"Unsupported TPEX date format: {value}")


def _load_source_rows(source_json: Path | None) -> list[Mapping[str, object]]:
    if source_json is not None:
        data = json.loads(Path(source_json).read_text(encoding="utf-8"))
    else:
        response = requests.get(
            TPEX_DAILY_CLOSE_URL,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
    if not isinstance(data, list):
        raise ValueError("TPEX daily close response is not a list")
    return data


if __name__ == "__main__":
    raise SystemExit(main())
