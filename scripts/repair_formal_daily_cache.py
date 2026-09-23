"""由已核驗 SQLite 備份重建 stock_data_whole.csv，提供可恢復發布。"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import tempfile
from typing import Any, Iterable, Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from data_module.daily_price_revision_write_guard import DailyPriceRevisionWriteGuard
from data_module.daily_price_source_guard import (
    AGGREGATE_SOURCE_VERSION,
    aggregate_receipt_path,
)
from data_module.historical_session_revision import (
    RECEIPT_DIR as SESSION_RECEIPT_DIR,
    _plan as load_session_plan,
    validate_session_replacement,
)
from data_module.ml_daily_price_revision_gate import REPAIR_RECEIPT_RELATIVE_DIR
from data_module.ml_storage_capacity import (
    acquire_heavy_chain_reservation,
    release_heavy_chain_reservation,
)
from scripts.repair_formal_market_data import atomic, encoded, file_hash, now, quote, readonly
from scripts.repair_historical_sessions import verified_rows


SCHEMA = "formal-daily-cache-repair.v1"
CONFIRM = "repair-formal-daily-cache"
TECH_RECEIPT_DIR = Path("output/scheduled/formal_technical_repair_receipts")
RECEIPT_DIR = Path("output/scheduled/formal_daily_cache_receipts")
CSV_COLUMNS = (
    "日期",
    "證券代號",
    "證券名稱",
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
DB_COLUMN_FOR_CSV = {"漲跌(+/-)": "漲跌"}
INTEGER_COLUMNS = frozenset(
    {"成交股數", "成交筆數", "成交金額", "最後揭示買量", "最後揭示賣量"}
)
TEXT_COLUMNS = frozenset({"日期", "證券代號", "證券名稱", "漲跌(+/-)"})


def _regular_file_hash(path: Path, label: str) -> str | None:
    if path.is_symlink():
        raise ValueError(f"{label} 不得為連結：{path}")
    if not path.exists():
        return None
    if not path.is_file():
        raise ValueError(f"{label} 必須是一般檔案：{path}")
    return file_hash(path)


def _json_object(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} 不存在或為連結：{path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} 無法讀取：{path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} 必須是 JSON 物件：{path}")
    return payload


def _verify_self_hash(payload: Mapping[str, Any], field: str, label: str) -> None:
    supplied = payload.get(field)
    body = dict(payload)
    body.pop(field, None)
    actual = "sha256:" + hashlib.sha256(encoded(body)).hexdigest()
    if supplied != actual:
        raise ValueError(f"{label} 內容 hash 不符")


def _date_key(value: object) -> str:
    text = str(value).strip()
    if not re.fullmatch(r"\d{8}", text):
        raise ValueError(f"來源日期不是 YYYYMMDD：{value!r}")
    return datetime.strptime(text, "%Y%m%d").strftime("%Y%m%d")


def _symbol_key(value: object) -> str:
    if value is None or isinstance(value, bool):
        raise ValueError("來源證券代號為空或無效")
    text = str(value).strip()
    if not text:
        raise ValueError("來源證券代號為空")
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if text.isdigit() and len(text) < 4:
        text = text.zfill(4)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,24}", text):
        raise ValueError(f"來源證券代號不安全：{text!r}")
    return text


def _typed_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if not math.isfinite(value):
            return ""
        return repr(value)
    if isinstance(value, (int, str)):
        return str(value)
    if hasattr(value, "item"):
        try:
            return _typed_text(value.item())
        except (TypeError, ValueError):
            pass
    return str(value)


def _table_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    if connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is None:
        raise ValueError(f"來源資料庫缺少資料表：{table}")
    return [str(row[1]) for row in connection.execute(f"PRAGMA table_info({quote(table)})")]


def table_hash(connection: sqlite3.Connection, table: str = "daily_prices") -> str:
    columns = _table_columns(connection, table)
    digest = hashlib.sha256(encoded(columns))
    cursor = connection.execute(
        f"SELECT * FROM {quote(table)} ORDER BY {quote('證券代號')}, {quote('日期')}"
    )
    while rows := cursor.fetchmany(5_000):
        digest.update(encoded(rows))
    return digest.hexdigest()


def _root_paths(root: Path) -> tuple[Path, Path, Path, Path]:
    database = root / "sqlite" / "twstock.db"
    stock_file = root / "meta_data" / "stock_data_whole.csv"
    source_receipt = aggregate_receipt_path(stock_file)
    return database, stock_file, source_receipt, root / "output" / "release_v4" / ".ml_heavy_chain.lock"


def _validate_receipt_location(root: Path, receipt_dir: Path, *, must_be_new: bool) -> Path:
    canonical_parent = (root / RECEIPT_DIR).resolve(strict=False)
    resolved = receipt_dir.resolve(strict=False)
    if receipt_dir.is_symlink() or resolved.parent != canonical_parent:
        raise ValueError(f"daily cache receipt 必須是固定目錄的直接子目錄：{canonical_parent}")
    if resolved.name in {"", ".", ".."} or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", resolved.name):
        raise ValueError("daily cache receipt run 名稱不合法")
    if must_be_new and (resolved.exists() or resolved.is_symlink()):
        raise ValueError("拒絕覆寫既有 daily cache receipt")
    return resolved


def _validate_technical_receipt(
    root: Path, technical_receipt_dir: Path
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    resolved_root = root.resolve(strict=True)
    expected_parent = (resolved_root / TECH_RECEIPT_DIR).resolve(strict=False)
    receipt_dir = technical_receipt_dir.resolve(strict=True)
    if technical_receipt_dir.is_symlink() or receipt_dir.parent != expected_parent:
        raise ValueError("technical receipt 不在固定 formal technical receipt 目錄")
    source_path = receipt_dir / "source.sqlite"
    source_evidence_path = receipt_dir / "source.json"
    source_evidence = _json_object(source_evidence_path, "technical source receipt")
    if (
        source_evidence.get("schema_version") != "formal-technical-repair.v1"
        or Path(str(source_evidence.get("root", ""))).resolve() != resolved_root
        or Path(str(source_evidence.get("source_db", ""))).resolve() != source_path.resolve()
        or source_path.is_symlink()
        or not source_path.is_file()
    ):
        raise ValueError("technical source receipt 身分不符")
    source_hash = file_hash(source_path)
    if source_evidence.get("source_sha256") != source_hash:
        raise ValueError("immutable technical source.sqlite hash 不符")

    final_receipt = _json_object(receipt_dir / "receipt.json", "technical final receipt")
    journal = _json_object(receipt_dir / "journal.json", "technical journal")
    manifest_path = receipt_dir / "stage" / "manifest.json"
    manifest = _json_object(manifest_path, "technical stage manifest")
    if (
        final_receipt != journal
        or final_receipt.get("schema_version") != "formal-technical-repair.v1"
        or final_receipt.get("state") != "applied"
        or final_receipt.get("source_db") != str(source_path.resolve())
        or final_receipt.get("source_sha256") != source_hash
        or final_receipt.get("daily_before_hash") != source_evidence.get("daily_before_hash")
        or final_receipt.get("manifest_sha256") != file_hash(manifest_path)
        or manifest.get("source_sha256") != source_hash
        or Path(str(manifest.get("source_db", ""))).resolve() != source_path.resolve()
    ):
        raise ValueError("technical apply receipt 未完成或與 immutable source 不一致")
    return source_path, source_evidence, final_receipt


def _utc_time(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} 缺少實際時間證據")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} 時間格式不合法") from exc
    if parsed.tzinfo is None or parsed > datetime.now(timezone.utc):
        raise ValueError(f"{label} 時間不是已觀測的時區時間")
    return parsed.isoformat()


def _numeric_equal(left: object, right: object) -> bool:
    def decimal_or_none(value: object) -> Decimal | None:
        if value is None or str(value).strip() in {"", "nan", "NaN", "<NA>", "--"}:
            return None
        try:
            result = Decimal(str(value).replace(",", ""))
        except InvalidOperation as exc:
            raise ValueError(f"來源數值格式不合法：{value!r}") from exc
        if not result.is_finite():
            raise ValueError("來源數值不是有限值")
        return result

    return decimal_or_none(left) == decimal_or_none(right)


def _same_rows(
    actual: Sequence[Mapping[str, Any]], expected: Sequence[Mapping[str, Any]], columns: Sequence[str]
) -> bool:
    if len(actual) != len(expected):
        return False
    text_columns = {"日期", "證券代號", "證券名稱", "漲跌"}
    for left, right in zip(actual, expected, strict=True):
        for column in columns:
            if column in text_columns:
                if left.get(column) != right.get(column):
                    return False
            elif not _numeric_equal(left.get(column), right.get(column)):
                return False
    return True


def _session_source_evidence(
    root: Path, database: Path
) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]]]:
    marker_paths = sorted((root / SESSION_RECEIPT_DIR).glob("*/revision.json"))
    if not marker_paths:
        raise ValueError("缺少已套用的歷史交易日來源 receipt")
    active_plans: list[dict[str, Any]] = []
    revision_times: list[dict[str, Any]] = []
    all_sources: list[dict[str, Any]] = []
    dates: set[str] = set()
    expected_rows: list[dict[str, Any]] = []
    source_files: list[dict[str, str]] = []
    for marker_path in marker_paths:
        if marker_path.is_symlink():
            raise ValueError("歷史交易日 revision marker 不得為連結")
        marker, plan = load_session_plan(marker_path, database)
        if marker.get("state") == "rolled_back":
            continue
        if marker.get("state") != "applied":
            raise ValueError("歷史交易日 receipt 未完成，拒絕重建 aggregate")
        receipt_path = marker_path.parent / "receipt.json"
        receipt = _json_object(receipt_path, "historical session receipt")
        if (
            receipt.get("state") != "applied"
            or receipt.get("plan_sha256") != marker.get("plan_sha256")
            or receipt.get("dates") != plan.get("dates")
            or receipt.get("rows") != len(plan.get("rows", []))
        ):
            raise ValueError("歷史交易日完成 receipt 與 plan 不符")
        source_rows = verified_rows(plan.get("sources", []), set(plan.get("existing_universe", [])))
        if not _same_rows(source_rows, plan.get("rows", []), plan.get("columns", [])):
            raise ValueError("封存 TWSE/TPEx 報表與歷史交易日 plan 不一致")
        active_plans.append(plan)
        expected_rows.extend(plan["rows"])
        dates.update(str(day) for day in plan["dates"])
        completed_at = _utc_time(receipt.get("completed_at"), "歷史交易日修訂")
        captures = []
        for item in plan["sources"]:
            raw_path = Path(item["path"])
            if raw_path.is_symlink() or not raw_path.is_file() or file_hash(raw_path) != item["sha256"]:
                raise ValueError("歷史交易日官方 raw capture hash 不符")
            archive_receipt = _json_object(Path(item["receipt"]), "歷史交易日來源 capture receipt")
            if file_hash(Path(item["receipt"])) != str(item["receipt_sha256"]).removeprefix("sha256:"):
                raise ValueError("歷史交易日 source receipt hash 不符")
            source_files.extend(
                [
                    {"path": str(raw_path.resolve()), "sha256": file_hash(raw_path)},
                    {
                        "path": str(Path(item["receipt"]).resolve()),
                        "sha256": file_hash(Path(item["receipt"])),
                    },
                ]
            )
            captures.append(
                {
                    "date": item["day"],
                    "venue": item["venue"],
                    "receipt_path": str(Path(item["receipt"]).resolve()),
                    "receipt_sha256": item["receipt_sha256"],
                    "captured_at": _utc_time(archive_receipt.get("captured_at"), "官方行情來源"),
                    "historical_pit": archive_receipt.get("historical_pit"),
                }
            )
        revision_times.append(
            {
                "kind": "historical_sessions",
                "receipt_path": str(receipt_path.resolve()),
                "completed_at": completed_at,
                "dates": sorted(str(day) for day in plan["dates"]),
                "captures": captures,
                "historical_pit": False,
            }
        )
        all_sources.append(
            {
                "marker_path": str(marker_path.resolve()),
                "marker_sha256": file_hash(marker_path),
                "receipt_path": str(receipt_path.resolve()),
                "receipt_sha256": file_hash(receipt_path),
                "plan_path": str((marker_path.parent / "plan.json").resolve()),
                "plan_sha256": str(marker["plan_sha256"]),
            }
        )
        source_evidence = all_sources[-1]
        for field, hash_field in (
            ("marker_path", "marker_sha256"),
            ("receipt_path", "receipt_sha256"),
            ("plan_path", "plan_sha256"),
        ):
            source_files.append(
                {
                    "path": source_evidence[field],
                    "sha256": source_evidence[hash_field].removeprefix("sha256:"),
                }
            )
    if not active_plans or not dates or not expected_rows:
        raise ValueError("缺少已套用的歷史交易日修訂來源")
    expected_keys = [(str(row["日期"]), str(row["證券代號"])) for row in expected_rows]
    if len(expected_keys) != len(set(expected_keys)):
        raise ValueError("歷史交易日 canonical source 含重複 key")
    return sorted(dates), expected_rows, revision_times, source_files


def _price_revision_evidence(
    root: Path, database: Path, source: sqlite3.Connection, columns: Sequence[str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    guard = DailyPriceRevisionWriteGuard(database)
    if not guard.has_revision:
        raise ValueError("缺少有效的 2026-05-20 daily price revision receipt")
    receipt_path = root / REPAIR_RECEIPT_RELATIVE_DIR / "receipt.json"
    payload = _json_object(receipt_path, "daily price revision receipt")
    raw_allowed_rows = payload.get("allowlist_count")
    if isinstance(raw_allowed_rows, bool) or not isinstance(raw_allowed_rows, (int, str)):
        raise ValueError("2026-05-20 daily price revision allowlist_count 不合法")
    try:
        allowed_rows = int(raw_allowed_rows)
    except (TypeError, ValueError) as exc:
        raise ValueError("2026-05-20 daily price revision allowlist_count 不合法") from exc
    if (
        payload.get("schema_version") != "historical-price-spike-repair-20260921.v1"
        or payload.get("status") != "applied"
        or str(payload.get("source_date", "")).replace("-", "") != "20260520"
        or allowed_rows <= 0
        or payload.get("historical_decision_time_available") is not False
        or payload.get("available_at_backfilled") is not False
        or payload.get("available_at") is not None
    ):
        raise ValueError("2026-05-20 daily price revision receipt scope/status 不符")
    corrected_at = _utc_time(payload.get("corrected_at"), "daily price source correction")
    official_capture_at = _utc_time(payload.get("official_capture_at"), "official daily price capture")
    raw_rows = [
        dict(zip(columns, row, strict=True))
        for row in source.execute(
            f"SELECT * FROM {quote('daily_prices')} WHERE {quote('日期')}=? ORDER BY {quote('證券代號')}",
            ("20260520",),
        )
    ]
    if len(raw_rows) != allowed_rows:
        raise ValueError("2026-05-20 canonical source row count 不符")
    guard.prepare_frame(pd.DataFrame(raw_rows))
    guard.assert_full_replacement_complete()
    return payload, {
        "kind": "daily_price_revision",
        "source_date": "20260520",
        "receipt_path": str(receipt_path.resolve()),
        "receipt_sha256": file_hash(receipt_path),
        "corrected_at": corrected_at,
        "official_capture_at": official_capture_at,
        "row_count": len(raw_rows),
        "historical_pit": False,
    }


def _validate_canonical_inputs(
    root: Path,
    database: Path,
    source: sqlite3.Connection,
    source_columns: Sequence[str],
) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    price_payload, price_evidence = _price_revision_evidence(root, database, source, source_columns)
    session_dates, session_expected, session_evidence, session_files = _session_source_evidence(root, database)
    all_revision_evidence = [price_evidence, *session_evidence]
    session_fields = list(session_expected[0]) if session_expected else []
    if not session_expected or not session_fields:
        raise ValueError("歷史交易日 canonical source rows 不完整")
    placeholders = ",".join("?" for _ in session_dates)
    raw_session = [
        dict(zip(session_fields, row, strict=True))
        for row in source.execute(
            f"SELECT {','.join(quote(column) for column in session_fields)} "
            f"FROM {quote('daily_prices')} WHERE {quote('日期')} IN ({placeholders}) "
            f"ORDER BY {quote('日期')}, {quote('證券代號')}",
            session_dates,
        )
    ]
    if not _same_rows(raw_session, session_expected, session_fields):
        raise ValueError("immutable source.sqlite 歷史九日價量與官方 canonical 修訂不符")
    validate_session_replacement(database, raw_session, replace_all=True)
    session_rows_by_key = {(str(row["日期"]), str(row["證券代號"])) for row in raw_session}
    expected_rows_by_key = {(str(row["日期"]), str(row["證券代號"])) for row in session_expected}
    if session_rows_by_key != expected_rows_by_key:
        raise ValueError("歷史九日 key 集合與 canonical source 不一致")
    return session_dates, raw_session, all_revision_evidence, {
        "price_revision": price_payload,
        "session_row_count": len(raw_session),
        "session_dates": session_dates,
        "revision_files": [
            {
                "path": str((root / REPAIR_RECEIPT_RELATIVE_DIR / "receipt.json").resolve()),
                "sha256": file_hash(root / REPAIR_RECEIPT_RELATIVE_DIR / "receipt.json"),
            },
            *session_files,
        ],
    }


def _exclusion_state(
    database_path: Path, source: sqlite3.Connection
) -> dict[str, Any]:
    from data_module.excluded_daily_price_revision import load_exclusion_evidence

    raw_evidence = load_exclusion_evidence(database_path)
    if not isinstance(raw_evidence, list):
        raise ValueError("錯日排除來源證據格式無效")
    identities: list[dict[str, Any]] = []
    excluded_keys: set[tuple[str, str]] = set()
    closed_dates: set[str] = set()
    evidence_files: list[dict[str, str]] = []
    for item in raw_evidence:
        if not isinstance(item, Mapping):
            raise ValueError("錯日排除來源證據列格式無效")
        raw_keys, raw_dates = item.get("keys"), item.get("closed_dates")
        if not isinstance(raw_keys, (list, tuple, set)) or not isinstance(
            raw_dates, (list, tuple, set)
        ):
            raise ValueError("錯日排除來源證據範圍無效")
        if not raw_keys and not raw_dates:
            raise ValueError("錯日排除來源證據範圍不可為空")
        item_keys: set[tuple[str, str]] = set()
        item_dates = {_date_key(value) for value in raw_dates}
        for raw_key in raw_keys:
            if isinstance(raw_key, Mapping):
                day, symbol = raw_key.get("date", raw_key.get("日期")), raw_key.get(
                    "symbol", raw_key.get("證券代號")
                )
            elif isinstance(raw_key, (list, tuple)) and len(raw_key) == 2:
                day, symbol = raw_key
            else:
                raise ValueError("錯日排除來源股票鍵格式無效")
            key = (_date_key(day), _symbol_key(symbol))
            if not key[1] or key in item_keys:
                raise ValueError("錯日排除來源股票鍵缺漏或重複")
            item_keys.add(key)
        if excluded_keys.intersection(item_keys) or closed_dates.intersection(item_dates):
            raise ValueError("不同錯日排除 receipt 範圍重複")
        excluded_keys.update(item_keys)
        closed_dates.update(item_dates)
        receipt_path_raw = item.get("receipt_path")
        plan_sha = item.get("plan_sha256")
        receipt_sha = item.get("receipt_sha256")
        acquired_at = item.get("acquired_at")
        source_start_date = item.get("source_start_date")
        archive_relative = item.get("evidence_archive_relative")
        market_plan_sha = item.get("market_plan_sha256")
        if not all(
            isinstance(value, str) and value.strip()
            for value in (
                receipt_path_raw,
                plan_sha,
                receipt_sha,
                acquired_at,
                source_start_date,
                archive_relative,
                market_plan_sha,
            )
        ):
            raise ValueError("錯日排除來源 receipt identity 缺漏")
        receipt_path = Path(str(receipt_path_raw))
        if receipt_path.is_symlink() or not receipt_path.is_file():
            raise ValueError("錯日排除來源 receipt 不存在或為連結")
        actual_receipt_hash = file_hash(receipt_path)
        if actual_receipt_hash != str(receipt_sha).removeprefix("sha256:"):
            raise ValueError("錯日排除來源 receipt hash 不符")
        identities.append(
            {
                "kind": "excluded_daily_price_revision",
                "plan_sha256": str(plan_sha),
                "receipt_sha256": str(receipt_sha),
                "receipt_path": str(receipt_path.resolve()),
                "keys": [list(key) for key in sorted(item_keys)],
                "closed_dates": sorted(item_dates),
                "acquired_at": str(acquired_at),
                "source_start_date": _date_key(source_start_date),
                "evidence_archive_relative": str(archive_relative),
                "market_plan_sha256": str(market_plan_sha),
            }
        )
        evidence_files.append(
            {"path": str(receipt_path.resolve()), "sha256": actual_receipt_hash}
        )

    if closed_dates:
        placeholders = ",".join("?" for _ in closed_dates)
        found = source.execute(
            f"SELECT 日期 FROM daily_prices WHERE 日期 IN ({placeholders}) LIMIT 1",
            sorted(closed_dates),
        ).fetchone()
        if found is not None:
            raise ValueError(f"immutable daily_prices 仍含已核驗排除的休市日期：{found[0]}")
    keys_by_date: dict[str, set[str]] = {}
    for day, symbol in excluded_keys:
        keys_by_date.setdefault(day, set()).add(symbol)
    for day, symbols in keys_by_date.items():
        rows = source.execute(
            "SELECT 證券代號 FROM daily_prices WHERE 日期=?",
            (day,),
        )
        for row in rows:
            symbol = _symbol_key(row[0])
            if symbol in symbols:
                raise ValueError(f"immutable daily_prices 仍含已核驗排除的股票列：{day}/{symbol}")
    return {
        "evidence": identities,
        "files": evidence_files,
        "excluded_keys": [list(key) for key in sorted(excluded_keys)],
        "excluded_closed_dates": sorted(closed_dates),
    }


def _immutable(path: Path) -> sqlite3.Connection:
    uri = path.resolve(strict=True).as_uri() + "?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True, timeout=30)
    connection.execute("PRAGMA query_only=ON")
    return connection


def _source_state(
    root: Path,
    technical_receipt_dir: Path,
    *,
    expected_rows: int | None,
) -> dict[str, Any]:
    source_path, source_evidence, technical_receipt = _validate_technical_receipt(
        root, technical_receipt_dir
    )
    database, target, source_receipt, _lock = _root_paths(root.resolve())
    if not database.is_file() or database.is_symlink():
        raise ValueError(f"正式 SQLite 不存在或為連結：{database}")
    with _immutable(source_path) as source:
        check = source.execute("PRAGMA quick_check").fetchone()
        if check is None or check[0] != "ok":
            raise ValueError("immutable source.sqlite quick_check 失敗")
        columns = _table_columns(source, "daily_prices")
        source_columns = {name: name for name in CSV_COLUMNS}
        source_columns.update(DB_COLUMN_FOR_CSV)
        missing = sorted({source_columns[name] for name in CSV_COLUMNS} - set(columns))
        if missing:
            raise ValueError(f"daily_prices schema 缺少必要欄位：{missing}")
        if len(set(CSV_COLUMNS)) != 17:
            raise ValueError("stock_data_whole CSV 欄位契約不是既有 17 欄")
        row_count = int(source.execute("SELECT count(*) FROM daily_prices").fetchone()[0])
        if row_count <= 0 or (expected_rows is not None and row_count != expected_rows):
            raise ValueError(f"daily_prices row count 不符：{row_count} != {expected_rows}")
        source_daily_hash = table_hash(source)
        if source_daily_hash != source_evidence.get("daily_before_hash"):
            raise ValueError("source.sqlite daily_prices hash 不符 technical source.json")
        session_dates, _session_rows, revision_evidence, preflight = _validate_canonical_inputs(
            root.resolve(), database, source, columns
        )
        exclusion_state = _exclusion_state(database, source)
        date_keys = [str(row[0]) for row in source.execute("SELECT DISTINCT 日期 FROM daily_prices ORDER BY 日期")]
        if not date_keys:
            raise ValueError("daily_prices 沒有日期")
        for key in date_keys:
            _date_key(key)
        first_date, last_date = _date_key(date_keys[0]), _date_key(date_keys[-1])

    with readonly(database) as live:
        live_daily_hash = table_hash(live)
    if live_daily_hash != source_evidence.get("daily_before_hash"):
        raise ValueError("正式 daily_prices 已偏離 immutable technical source")
    if target.is_symlink() or source_receipt.is_symlink():
        raise ValueError("stock_data_whole 或其 source receipt 不得為連結")
    if not target.is_file():
        raise ValueError("正式 stock_data_whole.csv 不存在")
    _regular_file_hash(target, "stock_data_whole.csv")
    _regular_file_hash(source_receipt, "stock_data_whole aggregate source receipt")
    revision_file_map = {
        str(Path(item["path"]).resolve()): str(item["sha256"])
        for item in preflight["revision_files"]
    }
    revision_file_map.update(
        {
            str(Path(item["path"]).resolve()): str(item["sha256"])
            for item in exclusion_state["files"]
        }
    )
    revision_files = [
        {"path": path, "sha256": digest}
        for path, digest in sorted(revision_file_map.items())
    ]
    return {
        "schema_version": SCHEMA,
        "root": str(root.resolve()),
        "database_path": str(database.resolve()),
        "daily_before_hash": source_evidence["daily_before_hash"],
        "live_daily_hash_at_prepare": live_daily_hash,
        "source_db": str(source_path.resolve()),
        "source_db_sha256": file_hash(source_path),
        "technical_source_json": str((technical_receipt_dir / "source.json").resolve()),
        "technical_source_json_sha256": file_hash(technical_receipt_dir / "source.json"),
        "technical_receipt_sha256": file_hash(technical_receipt_dir / "receipt.json"),
        "technical_manifest_sha256": technical_receipt["manifest_sha256"],
        "target_path": str(target.resolve()),
        "source_receipt_path": str(source_receipt.resolve()),
        "before_sha256": {
            "target": file_hash(target),
            "source_receipt": _regular_file_hash(source_receipt, "stock_data_whole aggregate source receipt"),
        },
        "row_count": row_count,
        "date_keys": date_keys,
        "first_date": first_date,
        "last_date": last_date,
        "csv_columns": list(CSV_COLUMNS),
        "source_columns": columns,
        "source_receipt_dir": str(technical_receipt_dir.resolve()),
        "revision_evidence": revision_evidence,
        "exclusion_evidence": exclusion_state["evidence"],
        "excluded_keys": exclusion_state["excluded_keys"],
        "excluded_closed_dates": exclusion_state["excluded_closed_dates"],
        "revision_files": revision_files,
        "preflight": preflight,
        "prepared_at": now(),
        "historical_pit": False,
    }


def _verify_prepared(path: Path) -> dict[str, Any]:
    prepared = _json_object(path / "prepared.json", "daily cache prepared evidence")
    _verify_self_hash(prepared, "prepared_sha256", "daily cache prepared evidence")
    if prepared.get("schema_version") != SCHEMA:
        raise ValueError("daily cache prepared schema 不符")
    root = Path(str(prepared.get("root", ""))).resolve(strict=True)
    _validate_receipt_location(root, path, must_be_new=False)
    expected_database, expected_target, expected_source_receipt, _lock_path = _root_paths(root)
    if (
        Path(str(prepared.get("database_path", ""))).resolve() != expected_database.resolve()
        or Path(str(prepared.get("target_path", ""))).resolve() != expected_target.resolve()
        or Path(str(prepared.get("source_receipt_path", ""))).resolve() != expected_source_receipt.resolve()
    ):
        raise ValueError("daily cache prepared target path 不符合固定正式路徑")
    technical_dir = Path(str(prepared.get("source_receipt_dir", ""))).resolve(strict=True)
    source_path, source_evidence, technical_receipt = _validate_technical_receipt(root, technical_dir)
    if (
        str(source_path.resolve()) != prepared.get("source_db")
        or file_hash(source_path) != prepared.get("source_db_sha256")
        or file_hash(technical_dir / "source.json") != prepared.get("technical_source_json_sha256")
        or file_hash(technical_dir / "receipt.json") != prepared.get("technical_receipt_sha256")
        or technical_receipt.get("manifest_sha256") != prepared.get("technical_manifest_sha256")
        or source_evidence.get("daily_before_hash") != prepared.get("daily_before_hash")
    ):
        raise ValueError("immutable technical source receipt 發生漂移")
    for item in prepared.get("revision_files", []):
        revision_path = Path(str(item["path"]))
        if revision_path.is_symlink() or not revision_path.is_file() or file_hash(revision_path) != item.get("sha256"):
            raise ValueError(f"daily source revision receipt 發生漂移：{revision_path}")
    with _immutable(source_path) as source:
        if source.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("immutable source.sqlite quick_check 失敗")
        if int(source.execute("SELECT count(*) FROM daily_prices").fetchone()[0]) != prepared.get("row_count"):
            raise ValueError("immutable source.sqlite row count 發生漂移")
        if table_hash(source) != prepared.get("daily_before_hash"):
            raise ValueError("immutable source.sqlite daily_prices hash 發生漂移")
        exclusion_state = _exclusion_state(expected_database, source)
    if (
        exclusion_state["evidence"] != prepared.get("exclusion_evidence")
        or exclusion_state["excluded_keys"] != prepared.get("excluded_keys")
        or exclusion_state["excluded_closed_dates"] != prepared.get("excluded_closed_dates")
    ):
        raise ValueError("錯日排除來源 evidence 在 prepare 後發生漂移")
    return prepared


def prepare(
    root: Path,
    technical_receipt_dir: Path,
    receipt_dir: Path,
    *,
    expected_rows: int | None = None,
) -> dict[str, Any]:
    resolved_root = root.resolve(strict=True)
    output = _validate_receipt_location(resolved_root, receipt_dir, must_be_new=True)
    source_state = _source_state(
        resolved_root, technical_receipt_dir.resolve(strict=True), expected_rows=expected_rows
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.prepare.", dir=output.parent))
    try:
        body = {**source_state, "receipt_dir": str(output), "state": "prepared"}
        body["prepared_sha256"] = "sha256:" + hashlib.sha256(encoded(body)).hexdigest()
        atomic(temporary / "prepared.json", encoded(body))
        if output.exists():
            raise FileExistsError(f"拒絕覆寫既有 daily cache receipt：{output}")
        os.rename(temporary, output)
    except BaseException:
        if temporary.exists():
            resolved = temporary.resolve(strict=True)
            parent = output.parent.resolve(strict=True)
            if resolved.parent != parent or not resolved.name.startswith(f".{output.name}.prepare."):
                raise RuntimeError(f"refusing to remove unexpected temporary: {resolved}")
            shutil.rmtree(resolved, ignore_errors=True)
        raise
    return {"state": "prepared", "directory": str(output), "rows": source_state["row_count"]}


def _sidecar_payload(prepared: Mapping[str, Any], csv_hash: str) -> dict[str, Any]:
    return {
        "schema_version": AGGREGATE_SOURCE_VERSION,
        "source_version": AGGREGATE_SOURCE_VERSION,
        "quality_status": "accepted",
        "source_path": prepared["target_path"],
        "source_sha256": "sha256:" + csv_hash,
        "date_keys": list(prepared["date_keys"]),
        "row_count": int(prepared["row_count"]),
        "producer": "scripts.repair_formal_daily_cache",
        "producer_contract": "formal-daily-cache-repair.v1",
        "captured_at": now(),
        "source_database_path": prepared["source_db"],
        "source_database_sha256": "sha256:" + str(prepared["source_db_sha256"]),
        "source_daily_prices_hash": prepared["daily_before_hash"],
        "source_technical_receipt_dir": prepared["source_receipt_dir"],
        "source_technical_receipt_sha256": prepared["technical_receipt_sha256"],
        "source_technical_manifest_sha256": prepared["technical_manifest_sha256"],
        "source_revision_receipts": list(prepared["revision_evidence"]),
        "source_revision_times": list(prepared["revision_evidence"]),
        "source_exclusion_receipts": list(prepared["exclusion_evidence"]),
        "excluded_source_keys": list(prepared["excluded_keys"]),
        "excluded_closed_dates": list(prepared["excluded_closed_dates"]),
        "historical_pit": False,
    }


def _csv_stage_value(value: object) -> str:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("daily_prices 含非有限數值")
    return _typed_text(value)


def stage(receipt_dir: Path) -> dict[str, Any]:
    receipt = Path(receipt_dir).resolve(strict=True)
    prepared = _verify_prepared(receipt)
    root = Path(str(prepared["root"]))
    _validate_receipt_location(root, receipt, must_be_new=False)
    stage_dir = receipt / "stage"
    manifest_path = receipt / "manifest.json"
    if stage_dir.exists() or stage_dir.is_symlink() or manifest_path.exists():
        raise ValueError("daily cache staging 已存在，拒絕覆寫")
    source_path = Path(str(prepared["source_db"]))
    temp_dir = Path(tempfile.mkdtemp(prefix=f".stage.{receipt.name}.", dir=receipt))
    try:
        staged_csv = temp_dir / "stock_data_whole.csv"
        with _immutable(source_path) as source, staged_csv.open(
            "w", encoding="utf-8-sig", newline=""
        ) as stream:
            columns = _table_columns(source, "daily_prices")
            if columns != prepared["source_columns"]:
                raise ValueError("source.sqlite daily_prices schema 在 prepare 後改變")
            db_columns = [DB_COLUMN_FOR_CSV.get(name, name) for name in CSV_COLUMNS]
            sql = (
                "SELECT "
                + ",".join(
                    f"{quote(db_name)} AS {quote(csv_name)}"
                    for csv_name, db_name in zip(CSV_COLUMNS, db_columns, strict=True)
                )
                + f" FROM {quote('daily_prices')} ORDER BY {quote('日期')}, {quote('證券代號')}"
            )
            cursor = source.execute(sql)
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(CSV_COLUMNS)
            row_count = 0
            seen_dates: set[str] = set()
            previous_key: tuple[str, str] | None = None
            while rows := cursor.fetchmany(10_000):
                for values in rows:
                    row = dict(zip(CSV_COLUMNS, values, strict=True))
                    day = _date_key(row["日期"])
                    symbol = _symbol_key(row["證券代號"])
                    key = (day, symbol)
                    if previous_key is not None and key <= previous_key:
                        if key == previous_key:
                            raise ValueError(f"daily_prices duplicate key: {day}/{symbol}")
                        raise ValueError("daily_prices source ordering is not canonical")
                    previous_key = key
                    row["日期"] = day
                    row["證券代號"] = symbol
                    writer.writerow([_csv_stage_value(row[column]) for column in CSV_COLUMNS])
                    seen_dates.add(day)
                    row_count += 1
                    if row_count % 500_000 == 0:
                        print(
                            f"[formal-daily-cache] staged rows: {row_count:,}",
                            flush=True,
                        )
            stream.flush()
            os.fsync(stream.fileno())
        if row_count != prepared["row_count"]:
            raise ValueError("staged cache row count 與 immutable source 不符")
        if sorted(seen_dates) != prepared["date_keys"]:
            raise ValueError("staged cache date key set 與 immutable source 不符")
        staged_csv_hash = file_hash(staged_csv)
        sidecar = _sidecar_payload(prepared, staged_csv_hash)
        staged_sidecar = temp_dir / "stock_data_whole.csv.source.json"
        atomic(staged_sidecar, encoded(sidecar))
        os.rename(temp_dir, stage_dir)
        file_records = [
            {
                "target_path": prepared["target_path"],
                "staged_path": str((stage_dir / "stock_data_whole.csv").resolve()),
                "before_sha256": prepared["before_sha256"]["target"],
                "after_sha256": staged_csv_hash,
            },
            {
                "target_path": prepared["source_receipt_path"],
                "staged_path": str((stage_dir / "stock_data_whole.csv.source.json").resolve()),
                "before_sha256": prepared["before_sha256"]["source_receipt"],
                "after_sha256": file_hash(stage_dir / "stock_data_whole.csv.source.json"),
            },
        ]
        manifest = {
            "schema_version": SCHEMA,
            "state": "staged",
            "created_at": now(),
            "root": prepared["root"],
            "receipt_dir": str(receipt),
            "source_db": prepared["source_db"],
            "source_db_sha256": prepared["source_db_sha256"],
            "daily_before_hash": prepared["daily_before_hash"],
            "technical_source_json_sha256": prepared["technical_source_json_sha256"],
            "technical_receipt_sha256": prepared["technical_receipt_sha256"],
            "technical_manifest_sha256": prepared["technical_manifest_sha256"],
            "row_count": row_count,
            "first_date": prepared["first_date"],
            "last_date": prepared["last_date"],
            "date_keys": prepared["date_keys"],
            "csv_columns": list(CSV_COLUMNS),
            "canonical_checks": prepared["preflight"],
            "revision_evidence": prepared["revision_evidence"],
            "exclusion_evidence": prepared["exclusion_evidence"],
            "excluded_keys": prepared["excluded_keys"],
            "excluded_closed_dates": prepared["excluded_closed_dates"],
            "revision_files": prepared["revision_files"],
            "files": file_records,
            "historical_pit": False,
        }
        atomic(manifest_path, encoded(manifest))
        return {"state": "staged", "manifest": str(manifest_path), "rows": row_count}
    except BaseException:
        if temp_dir.exists():
            resolved = temp_dir.resolve(strict=True)
            parent = receipt.resolve(strict=True)
            if resolved.parent != parent or not resolved.name.startswith(f".stage.{receipt.name}."):
                raise RuntimeError(f"refusing to remove unexpected stage temporary: {resolved}")
            shutil.rmtree(resolved, ignore_errors=True)
        raise


def _self_hashed(body: Mapping[str, Any], field: str) -> dict[str, Any]:
    result = dict(body)
    result.pop(field, None)
    result[field] = "sha256:" + hashlib.sha256(encoded(result)).hexdigest()
    return result


def _load_manifest(receipt: Path, expected_hash: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    prepared = _verify_prepared(receipt)
    manifest_path = receipt / "manifest.json"
    if expected_hash is not None and file_hash(manifest_path) != expected_hash.removeprefix("sha256:"):
        raise ValueError("daily cache manifest hash 不符")
    manifest = _json_object(manifest_path, "daily cache manifest")
    if (
        manifest.get("schema_version") != SCHEMA
        or manifest.get("state") != "staged"
        or Path(str(manifest.get("receipt_dir", ""))).resolve() != receipt.resolve()
        or manifest.get("source_db") != prepared.get("source_db")
        or manifest.get("source_db_sha256") != prepared.get("source_db_sha256")
        or manifest.get("daily_before_hash") != prepared.get("daily_before_hash")
        or manifest.get("row_count") != prepared.get("row_count")
        or manifest.get("csv_columns") != list(CSV_COLUMNS)
        or manifest.get("exclusion_evidence") != prepared.get("exclusion_evidence")
        or manifest.get("excluded_keys") != prepared.get("excluded_keys")
        or manifest.get("excluded_closed_dates") != prepared.get("excluded_closed_dates")
    ):
        raise ValueError("daily cache manifest 與 prepared evidence 不一致")
    expected_targets = [prepared["target_path"], prepared["source_receipt_path"]]
    if not isinstance(manifest.get("files"), list) or len(manifest["files"]) != 2:
        raise ValueError("daily cache manifest 檔案集合不符")
    stage_root = (receipt / "stage").resolve(strict=True)
    for item, target in zip(manifest["files"], expected_targets, strict=True):
        target_path = Path(str(item.get("target_path", ""))).resolve()
        staged_path = Path(str(item.get("staged_path", ""))).resolve(strict=True)
        if (
            target_path != Path(target).resolve()
            or Path(str(item.get("staged_path", ""))).is_symlink()
            or not staged_path.is_relative_to(stage_root)
            or file_hash(staged_path) != item.get("after_sha256")
            or item.get("before_sha256") != prepared["before_sha256"][
                "target" if target == prepared["target_path"] else "source_receipt"
            ]
        ):
            raise ValueError("staged daily cache 檔案身分或 hash 不符")
    csv_payload = _json_object(Path(manifest["files"][1]["staged_path"]), "staged aggregate source receipt")
    if (
        csv_payload.get("schema_version") != AGGREGATE_SOURCE_VERSION
        or csv_payload.get("source_version") != AGGREGATE_SOURCE_VERSION
        or csv_payload.get("quality_status") != "accepted"
        or csv_payload.get("source_path") != prepared["target_path"]
        or csv_payload.get("source_sha256") != "sha256:" + manifest["files"][0]["after_sha256"]
        or csv_payload.get("row_count") != prepared["row_count"]
        or csv_payload.get("date_keys") != prepared["date_keys"]
        or csv_payload.get("historical_pit") is not False
    ):
        raise ValueError("staged aggregate source receipt 不符合 daily-price contract")
    return prepared, manifest


def _copy_atomic(source: Path, target: Path) -> None:
    if target.parent.is_symlink():
        raise ValueError(f"寫入目錄不得為連結：{target.parent}")
    target.parent.mkdir(parents=True, exist_ok=True)
    _regular_file_hash(target, "atomic copy target")
    fd, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as destination, source.open("rb") as origin:
            shutil.copyfileobj(origin, destination, length=1024 * 1024)
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _acquire_locks(root: Path, target: Path) -> tuple[Any, Any]:
    heavy_path = root / "output" / "release_v4" / ".ml_heavy_chain.lock"
    heavy = acquire_heavy_chain_reservation(heavy_path)
    if heavy is None:
        raise ValueError("ML heavy-chain maintenance lock 忙碌")
    try:
        csv_lock = acquire_heavy_chain_reservation(target.with_suffix(".csv.lock"))
        if csv_lock is None:
            raise ValueError("stock_data_whole CSV/source receipt lock 忙碌")
        return heavy, csv_lock
    except BaseException:
        release_heavy_chain_reservation(heavy)
        raise


def _release_locks(locks: tuple[Any, Any]) -> None:
    release_heavy_chain_reservation(locks[1])
    release_heavy_chain_reservation(locks[0])


def _live_database_lock(database: Path, expected_hash: str) -> sqlite3.Connection:
    connection = sqlite3.connect(database, timeout=30)
    try:
        connection.execute("BEGIN IMMEDIATE")
        if table_hash(connection) != expected_hash:
            raise ValueError("正式 daily_prices 與 immutable source.json hash 已漂移")
        return connection
    except BaseException:
        connection.close()
        raise


def _verify_csv_content(path: Path, manifest: Mapping[str, Any]) -> None:
    expected_dates = set(str(value) for value in manifest["date_keys"])
    found_dates: set[str] = set()
    count = 0
    previous: tuple[str, str] | None = None
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != list(CSV_COLUMNS):
            raise ValueError("發布後 stock_data_whole 欄位不符")
        for row in reader:
            if None in row:
                raise ValueError("發布後 stock_data_whole 含多餘欄位")
            day = _date_key(row.get("日期", ""))
            symbol = _symbol_key(row.get("證券代號", ""))
            key = (day, symbol)
            if previous is not None and key <= previous:
                raise ValueError("發布後 stock_data_whole key 重複或排序錯誤")
            previous = key
            found_dates.add(day)
            count += 1
    if count != manifest["row_count"] or found_dates != expected_dates:
        raise ValueError("發布後 stock_data_whole row/date coverage 不符")


def _write_journal(receipt: Path, journal: Mapping[str, Any]) -> dict[str, Any]:
    signed = _self_hashed(journal, "journal_sha256")
    atomic(receipt / "journal.json", encoded(signed))
    return signed


def _load_journal(receipt: Path) -> dict[str, Any]:
    journal = _json_object(receipt / "journal.json", "daily cache journal")
    _verify_self_hash(journal, "journal_sha256", "daily cache journal")
    if journal.get("schema_version") != SCHEMA or journal.get("state") not in {"pending", "applied", "rolled_back"}:
        raise ValueError("daily cache journal state/schema 不符")
    return journal


def _ensure_backups(receipt: Path, manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    backup_dir = receipt / "backup"
    if backup_dir.is_symlink() or (backup_dir.exists() and not backup_dir.is_dir()):
        raise ValueError(f"daily cache before backup 目錄不安全：{backup_dir}")
    backup_dir.mkdir(exist_ok=True)
    result = []
    for index, item in enumerate(manifest["files"]):
        before_hash = item["before_sha256"]
        backup_rel = f"backup/{index:02d}.before"
        backup = receipt / backup_rel
        target = Path(item["target_path"])
        current = _regular_file_hash(target, "正式快取目標")
        if current != before_hash:
            raise ValueError(f"正式快取在 prepare 後已漂移：{target}")
        if before_hash is not None:
            if backup.is_symlink():
                raise ValueError(f"before 備份不得為連結：{backup}")
            if backup.exists():
                if file_hash(backup) != before_hash:
                    raise ValueError(f"before 備份 hash 不符：{backup}")
            else:
                _copy_atomic(target, backup)
                if file_hash(backup) != before_hash:
                    raise ValueError(f"before 備份讀回 hash 不符：{backup}")
        result.append({**item, "backup": backup_rel})
    return result


def _publish_after(receipt: Path, files: Sequence[Mapping[str, Any]]) -> None:
    for item in files:
        target = Path(str(item["target_path"]))
        current = _regular_file_hash(target, "正式快取目標")
        if current not in (item["before_sha256"], item["after_sha256"]):
            raise ValueError(f"發布目標在中斷後發生外部變更：{target}")
        if current == item["after_sha256"]:
            continue
        staged = Path(str(item["staged_path"]))
        if staged.is_symlink():
            raise ValueError(f"staged cache 不得為連結：{staged}")
        if file_hash(staged) != item["after_sha256"]:
            raise ValueError(f"staged source hash 不符：{staged}")
        _copy_atomic(staged, target)


def _publish_before(receipt: Path, files: Sequence[Mapping[str, Any]]) -> None:
    for item in files:
        target = Path(str(item["target_path"]))
        before_hash = item["before_sha256"]
        current = _regular_file_hash(target, "正式快取回復目標")
        if current not in (before_hash, item["after_sha256"]):
            raise ValueError(f"回復目標在發布後發生外部變更：{target}")
        if current == before_hash:
            continue
        if before_hash is None:
            target.unlink(missing_ok=True)
            continue
        backup = receipt / str(item["backup"])
        if backup.is_symlink():
            raise ValueError(f"回復 before 備份不得為連結：{backup}")
        if file_hash(backup) != before_hash:
            raise ValueError(f"回復 before 備份 hash 不符：{backup}")
        _copy_atomic(backup, target)


def _finish(receipt: Path, journal: Mapping[str, Any], state: str) -> dict[str, Any]:
    result = {
        **dict(journal),
        "state": state,
        "completed_at": now(),
    }
    result.pop("journal_sha256", None)
    result.pop("receipt_sha256", None)
    result.pop("rollback_sha256", None)
    evidence_path = receipt / ("receipt.json" if state == "applied" else "rollback.json")
    evidence_field = "receipt_sha256" if state == "applied" else "rollback_sha256"
    if evidence_path.exists():
        existing = _json_object(evidence_path, f"daily cache {state} evidence")
        _verify_self_hash(existing, evidence_field, f"daily cache {state} evidence")
        existing_body = dict(existing)
        existing_body.pop(evidence_field, None)
        stable_fields = (
            "schema_version",
            "state",
            "root",
            "receipt_dir",
            "database_path",
            "daily_before_hash",
            "source_db",
            "source_db_sha256",
            "manifest_sha256",
            "row_count",
            "files",
            "started_at",
            "historical_pit",
        )
        if any(existing_body.get(key) != result.get(key) for key in stable_fields):
            raise ValueError(f"既有 daily cache {state} evidence 與 journal 不符")
        result = existing_body
    else:
        signed = _self_hashed(result, evidence_field)
        atomic(evidence_path, encoded(signed))
    _write_journal(receipt, result)
    return {"state": state, "rows": result["row_count"], "directory": str(receipt)}


def _validate_applied_receipt(receipt: Path, journal: Mapping[str, Any]) -> None:
    final = _json_object(receipt / "receipt.json", "daily cache final receipt")
    _verify_self_hash(final, "receipt_sha256", "daily cache final receipt")
    if final.get("state") != "applied":
        raise ValueError("daily cache final receipt state 不符")
    for key in (
        "schema_version",
        "root",
        "receipt_dir",
        "database_path",
        "daily_before_hash",
        "source_db",
        "source_db_sha256",
        "manifest_sha256",
        "row_count",
        "files",
        "started_at",
        "historical_pit",
    ):
        if final.get(key) != journal.get(key):
            raise ValueError("daily cache final receipt 與 journal 不符")


def apply(receipt_dir: Path, expected_manifest_hash: str) -> dict[str, Any]:
    receipt = Path(receipt_dir).resolve(strict=True)
    prepared, manifest = _load_manifest(receipt, expected_manifest_hash)
    if (receipt / "journal.json").exists():
        raise ValueError("已有 daily cache journal，請使用 resume 或 rollback")
    root = Path(prepared["root"])
    database = Path(prepared["database_path"])
    target = Path(prepared["target_path"])
    locks = _acquire_locks(root, target)
    live: sqlite3.Connection | None = None
    try:
        prepared, manifest = _load_manifest(receipt, expected_manifest_hash)
        live = _live_database_lock(database, str(prepared["daily_before_hash"]))
        backup_files = _ensure_backups(receipt, manifest)
        journal = {
            "schema_version": SCHEMA,
            "state": "pending",
            "root": str(root),
            "receipt_dir": str(receipt),
            "database_path": str(database),
            "daily_before_hash": prepared["daily_before_hash"],
            "source_db": prepared["source_db"],
            "source_db_sha256": prepared["source_db_sha256"],
            "manifest_sha256": file_hash(receipt / "manifest.json"),
            "row_count": manifest["row_count"],
            "files": backup_files,
            "started_at": now(),
            "historical_pit": False,
        }
        _write_journal(receipt, journal)
        _publish_after(receipt, backup_files)
        _verify_csv_content(target, manifest)
        expected_csv_hash = manifest["files"][0]["after_sha256"]
        if file_hash(target) != expected_csv_hash:
            raise ValueError("stock_data_whole 發布後 hash 不符")
        if file_hash(Path(prepared["source_receipt_path"])) != manifest["files"][1]["after_sha256"]:
            raise ValueError("stock_data_whole source receipt 發布後 hash 不符")
        if table_hash(live) != prepared["daily_before_hash"]:
            raise ValueError("發布期間正式 daily_prices 發生漂移")
        result = _finish(receipt, journal, "applied")
        live.commit()
        return result
    finally:
        if live is not None:
            live.close()
        _release_locks(locks)


def recover(receipt_dir: Path, *, rollback: bool) -> dict[str, Any]:
    receipt = Path(receipt_dir).resolve(strict=True)
    journal = _load_journal(receipt)
    prepared, manifest = _load_manifest(receipt, str(journal.get("manifest_sha256", "")))
    if (
        journal.get("receipt_dir") != str(receipt)
        or journal.get("database_path") != prepared.get("database_path")
        or journal.get("daily_before_hash") != prepared.get("daily_before_hash")
        or journal.get("source_db_sha256") != prepared.get("source_db_sha256")
        or journal.get("row_count") != manifest.get("row_count")
    ):
        raise ValueError("daily cache journal 與來源／stage 不符")
    if journal.get("state") == "rolled_back":
        raise ValueError("daily cache receipt 已回復，不可重複操作")
    if journal.get("state") == "applied":
        _validate_applied_receipt(receipt, journal)
    if rollback and journal.get("state") not in {"pending", "applied"}:
        raise ValueError("只可回復 pending 或 applied daily cache")
    if not rollback and journal.get("state") != "pending":
        raise ValueError("只可 resume pending daily cache")
    root = Path(prepared["root"])
    database = Path(prepared["database_path"])
    target = Path(prepared["target_path"])
    locks = _acquire_locks(root, target)
    live: sqlite3.Connection | None = None
    try:
        journal = _load_journal(receipt)
        prepared, manifest = _load_manifest(receipt, str(journal["manifest_sha256"]))
        live = _live_database_lock(database, str(prepared["daily_before_hash"]))
        files = journal["files"]
        if len(files) != 2:
            raise ValueError("daily cache journal file set 不符")
        for index, item in enumerate(files):
            planned = manifest["files"][index]
            if any(item.get(key) != planned.get(key) for key in ("target_path", "staged_path", "before_sha256", "after_sha256")):
                raise ValueError("daily cache journal files 不符 manifest")
            backup = receipt / str(item.get("backup", ""))
            if backup.is_symlink():
                raise ValueError("daily cache before backup 不得為連結")
            if item["before_sha256"] is not None and file_hash(backup) != item["before_sha256"]:
                raise ValueError("daily cache before backup hash 不符")
        if rollback:
            _publish_before(receipt, files)
            for item in files:
                target_path = Path(item["target_path"])
                current = _regular_file_hash(target_path, "正式快取回復目標")
                if current != item["before_sha256"]:
                    raise ValueError("daily cache rollback 讀回 hash 不符")
            return _finish(receipt, journal, "rolled_back")
        _publish_after(receipt, files)
        _verify_csv_content(target, manifest)
        if file_hash(target) != files[0]["after_sha256"] or file_hash(Path(files[1]["target_path"])) != files[1]["after_sha256"]:
            raise ValueError("daily cache resume 後讀回 hash 不符")
        if table_hash(live) != prepared["daily_before_hash"]:
            raise ValueError("resume 期間正式 daily_prices 發生漂移")
        result = _finish(receipt, journal, "applied")
        live.commit()
        return result
    finally:
        if live is not None:
            live.close()
        _release_locks(locks)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rebuild and publish stock_data_whole.csv from a verified immutable daily_prices source.")
    parser.add_argument("--mode", choices=("prepare", "stage", "apply", "resume", "rollback"), required=True)
    parser.add_argument("--root", type=Path, help="FA_Data root (required for prepare)")
    parser.add_argument("--technical-receipt-dir", type=Path, help="Applied technical receipt (required for prepare)")
    parser.add_argument("--receipt-dir", type=Path, required=True, help="New run under the fixed daily-cache receipt root")
    parser.add_argument("--expected-manifest-sha256", help="Stage manifest SHA-256 required for apply")
    parser.add_argument("--confirm", help=f"Confirmation token required for publish/recovery: {CONFIRM}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.mode == "prepare":
        if args.root is None or args.technical_receipt_dir is None:
            parser.error("prepare requires --root and --technical-receipt-dir")
        result = prepare(args.root, args.technical_receipt_dir, args.receipt_dir)
    elif args.mode == "stage":
        result = stage(args.receipt_dir)
    elif args.mode == "apply":
        if args.expected_manifest_sha256 is None or args.confirm != CONFIRM:
            parser.error("apply requires --expected-manifest-sha256 and the exact --confirm token")
        result = apply(args.receipt_dir, args.expected_manifest_sha256)
    elif args.mode == "resume":
        if args.confirm != CONFIRM:
            parser.error("resume requires the exact --confirm token")
        result = recover(args.receipt_dir, rollback=False)
    else:
        if args.confirm != CONFIRM:
            parser.error("rollback requires the exact --confirm token")
        result = recover(args.receipt_dir, rollback=True)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
