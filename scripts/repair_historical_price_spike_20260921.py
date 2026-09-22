"""受控修復 2026-05-20 daily_prices 的 868 筆官方可重建行情。

預設只建立 dry-run plan。``--apply`` 必須帶著已產生的 plan、明確確認字串、
maintenance lock 與 backup 路徑；執行前會重新驗證 audit allowlist、canonical
CSV、完整 TWSE 官方 response、SQLite bytes、schema 與每一筆 before row。
正式來源、raw CSV、merged CSV 與模型產物都不在本工具的寫入範圍。

Receipt 是 sidecar custody：transaction 前先以 create-only pending marker
鎖定 plan/source/db before hash；transaction commit 後才建立 final receipt。
若 final receipt 無法寫入，pending marker 會保留且不會被視為成功，讓 PIT
consumer fail closed。``available_at`` 永遠不回填成 2026-05-20；官方 response
的 2026-09-07 capture time 與實際 ``corrected_at`` 分開保存。
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import gzip
import hashlib
import html
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from typing import Any, Iterable, Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_module.ml_storage_capacity import (
    acquire_heavy_chain_reservation,
    release_heavy_chain_reservation,
)


TARGET_DATE = "20260520"
EXPECTED_ALLOWLIST_COUNT = 868
EXPECTED_MISSING_CANONICAL_COUNT = 54
EXPECTED_MISSING_OHLC_SYMBOLS = ("1538", "2321", "5906")
CONFIRM_TOKEN = "repair-historical-price-spike-20260921"
REPAIR_SCHEMA = "historical-price-spike-repair-20260921.v1"
# These are the source bytes reviewed for this one repair.  A receipt is
# evidence, not an authority: apply mode compares the actual bytes to these
# pins and refuses a substituted capture or CSV.
PINNED_CANONICAL_SHA256 = "sha256:1fdbe6f5f9d539d59144115586b90768593be0ffca71558454e72a0205780385"
PINNED_OFFICIAL_WIRE_SHA256 = "sha256:f185b2e953836028b9c2ed70c380f41155f68abc6357843a33bed1afe1345cea"
PINNED_OFFICIAL_DECODED_SHA256 = "sha256:c0d5739decee9efba163cbde2a238b35e8ee3b1b64300bc89717711c5ec3e866"

CANONICAL_COLUMNS = (
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
DB_UPDATE_COLUMNS = (
    "證券名稱",
    "成交股數",
    "成交筆數",
    "成交金額",
    "開盤價",
    "最高價",
    "最低價",
    "收盤價",
    "漲跌(+/-)",
    "漲跌",
    "涨跌",
    "漲跌價差",
    "最後揭示買價",
    "最後揭示買量",
    "最後揭示賣價",
    "最後揭示賣量",
    "本益比",
)
INTEGER_COLUMNS = {
    "成交股數",
    "成交筆數",
    "成交金額",
    "最後揭示買量",
    "最後揭示賣量",
}
NUMERIC_CANONICAL_COLUMNS = set(CANONICAL_COLUMNS) - {"證券名稱", "漲跌(+/-)"}
NUMERIC_DB_COLUMNS = set(NUMERIC_CANONICAL_COLUMNS)
IDENTITY_COLUMNS = ("日期", "證券代號")


class RepairError(RuntimeError):
    """Any fail-closed condition in plan, apply or rollback."""


class SourceEvidenceError(RepairError):
    pass


class RowDriftError(RepairError):
    pass


class ReceiptError(RepairError):
    pass


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _json_bytes(payload: object) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _payload_hash(payload: object) -> str:
    return f"sha256:{hashlib.sha256(_json_bytes(payload)).hexdigest()}"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError(path)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RepairError(f"JSON object required: {path}")
    return value


def _write_json_atomic(path: Path, payload: Mapping[str, Any], *, replace: bool) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or (path.exists() and not replace):
        raise ReceiptError(f"refusing to overwrite receipt path: {path}")
    temporary: Path | None = None
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(_json_bytes(payload))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _date_key(value: object) -> str:
    value_text = _text(value).replace("-", "").replace("/", "")
    return value_text if len(value_text) == 8 and value_text.isdigit() else ""


def _symbol(value: object) -> str:
    value_text = _text(value)
    if value_text.endswith(".0") and value_text[:-2].isdigit():
        value_text = value_text[:-2]
    return value_text.zfill(4) if value_text.isdigit() else value_text


def _decimal(value: object) -> Decimal | None:
    value_text = _text(value).replace(",", "")
    if value_text in {"", "--", "—", "None", "nan", "NaN"}:
        return None
    try:
        number = Decimal(value_text)
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def _decimal_text(value: object) -> str | None:
    number = _decimal(value)
    return None if number is None else format(number, "f")


def _numeric_identity(value: object) -> str | None:
    number = _decimal(value)
    if number is None:
        return None
    return format(number.normalize(), "f")


def _integer(value: object) -> int | None:
    number = _decimal(value)
    if number is None or number != number.to_integral_value():
        return None
    return int(number)


def _normalise_sign(value: object) -> str | None:
    text = html.unescape(_text(value))
    text = " ".join(text.split())
    text = text.replace("－", "-").replace("−", "-").replace("＋", "+")
    text = text.replace("<p style= color:green>", "").replace("<p style= color:red>", "")
    text = text.replace("<p>", "").replace("</p>", "").strip()
    if text in {"-", "跌", "▼"}:
        return "-"
    if text in {"+", "漲", "▲"}:
        return "+"
    if text in {"", "0", "0.0", "--", "—"}:
        return None
    return None


def _stable_value(value: object) -> object:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            return str(value)
        return format(Decimal(str(value)).normalize(), "f")
    if isinstance(value, bytes):
        return {"__bytes_sha256__": hashlib.sha256(value).hexdigest(), "bytes": len(value)}
    return str(value)


def _json_row(row: Mapping[str, object]) -> dict[str, object]:
    return {
        str(key): (_numeric_identity(value) if str(key) in NUMERIC_DB_COLUMNS else _stable_value(value))
        for key, value in row.items()
    }


def _open_read_only(path: Path) -> sqlite3.Connection:
    path = path.resolve()
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError(path)
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    if connection.execute("PRAGMA query_only").fetchone()[0] != 1:
        connection.close()
        raise RepairError("SQLite query_only could not be enabled")
    return connection


def _load_allowlist(
    audit_path: Path,
    *,
    expected_count: int = EXPECTED_ALLOWLIST_COUNT,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    report = _read_json(audit_path)
    comparisons = report.get("comparisons")
    if not isinstance(comparisons, Mapping):
        raise SourceEvidenceError("audit comparisons missing")
    comparison = comparisons.get("sqlite_vs_canonical_daily_csv")
    if not isinstance(comparison, Mapping):
        raise SourceEvidenceError("sqlite/canonical comparison missing")
    rows = comparison.get("mismatch_rows")
    if not isinstance(rows, list) or len(rows) != expected_count:
        raise SourceEvidenceError(
            f"allowlist mismatch count {len(rows) if isinstance(rows, list) else None} != {expected_count}"
        )
    target_rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise SourceEvidenceError("audit mismatch row is not an object")
        date = _date_key(raw.get("date"))
        symbol = _symbol(raw.get("symbol"))
        key = (date, symbol)
        if date != TARGET_DATE or not symbol or key in seen:
            raise SourceEvidenceError(f"invalid or duplicate allowlist key: {key}")
        sqlite_row = raw.get("sqlite")
        canonical_row = raw.get("canonical_daily_csv")
        if not isinstance(sqlite_row, Mapping) or not isinstance(canonical_row, Mapping):
            raise SourceEvidenceError(f"allowlist source row missing: {key}")
        if _date_key(canonical_row.get("date")) != TARGET_DATE:
            raise SourceEvidenceError(f"canonical row date drift: {key}")
        if _symbol(canonical_row.get("symbol")) != symbol:
            raise SourceEvidenceError(f"canonical row symbol drift: {key}")
        seen.add(key)
        target_rows.append(
            {
                "date": TARGET_DATE,
                "symbol": symbol,
                "audit_sqlite": dict(sqlite_row),
                "audit_canonical": dict(canonical_row),
                "differing_fields": list(raw.get("differing_fields") or []),
            }
        )
    target_rows.sort(key=lambda item: item["symbol"])
    allowlist_hash = _payload_hash(
        [
            {
                "date": row["date"],
                "symbol": row["symbol"],
                "sqlite": row["audit_sqlite"],
                "canonical": row["audit_canonical"],
            }
            for row in target_rows
        ]
    )
    by_date = comparison.get("by_date")
    target_stats = by_date.get(TARGET_DATE) if isinstance(by_date, Mapping) else None
    source_files = report.get("source_files")
    if not isinstance(source_files, Mapping):
        raise SourceEvidenceError("audit source_files missing")
    canonical_meta = source_files.get("canonical_daily_csv")
    if not isinstance(canonical_meta, Mapping):
        raise SourceEvidenceError("audit canonical metadata missing")
    files = canonical_meta.get("files")
    target_files = [
        item
        for item in (files if isinstance(files, list) else [])
        if isinstance(item, Mapping) and _date_key(item.get("date")) == TARGET_DATE
    ]
    if len(target_files) != 1:
        twse_files = [
            item
            for item in target_files
            if "daily_price_tpex" not in _text(item.get("path")).replace("\\", "/")
        ]
        if len(twse_files) == 1:
            target_files = twse_files
        else:
            raise SourceEvidenceError("audit does not identify exactly one target canonical CSV")
    missing_right = int(target_stats.get("missing_in_right", 0)) if isinstance(target_stats, Mapping) else None
    if missing_right is not None and missing_right < EXPECTED_MISSING_CANONICAL_COUNT:
        raise SourceEvidenceError("audit missing-in-right count is smaller than accepted scope")
    return target_rows, {
        "audit_path": str(audit_path.resolve()),
        "audit_sha256": _sha256_file(audit_path),
        "allowlist_count": len(target_rows),
        "allowlist_hash": allowlist_hash,
        "target_stats": dict(target_stats) if isinstance(target_stats, Mapping) else {},
        "canonical_file": dict(target_files[0]),
    }


def _load_canonical_rows(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError(path)
    rows: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not set(CANONICAL_COLUMNS).issubset(reader.fieldnames):
            raise SourceEvidenceError("canonical CSV is missing required quote columns")
        for raw in reader:
            symbol = _symbol(raw.get("證券代號"))
            if not symbol:
                continue
            if symbol in rows:
                raise SourceEvidenceError(f"duplicate canonical symbol: {symbol}")
            values: dict[str, Any] = {
                "date": TARGET_DATE,
                "symbol": symbol,
                "證券名稱": _text(raw.get("證券名稱")),
                "漲跌(+/-)": _normalise_sign(raw.get("漲跌(+/-)")),
            }
            for column in NUMERIC_CANONICAL_COLUMNS:
                if column in INTEGER_COLUMNS:
                    values[column] = _integer(raw.get(column))
                else:
                    values[column] = _decimal_text(raw.get(column))
            rows[symbol] = values
    if not rows:
        raise SourceEvidenceError("canonical CSV has no rows")
    return rows


def _find_official_table(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    tables = payload.get("tables")
    if not isinstance(tables, list):
        raise SourceEvidenceError("official response tables missing")
    for table in tables:
        if not isinstance(table, Mapping):
            continue
        title = _text(table.get("title"))
        if "每日收盤行情(全部)" in title:
            return table
    raise SourceEvidenceError("official full daily-price table missing")


def _official_row_values(fields: Sequence[object], row: Sequence[object]) -> dict[str, Any]:
    expected_fields = ["證券代號", *CANONICAL_COLUMNS]
    if len(fields) != len(row) or list(fields) != expected_fields:
        raise SourceEvidenceError("official field order is not the canonical 16-column contract")
    values: dict[str, Any] = {
        "date": TARGET_DATE,
        "symbol": _symbol(row[0]),
        "證券名稱": _text(row[1]),
        "漲跌(+/-)": _normalise_sign(row[9]),
    }
    for index, column in enumerate(CANONICAL_COLUMNS):
        if column in {"證券名稱", "漲跌(+/-)"}:
            continue
        raw = row[index + 1]
        values[column] = _integer(raw) if column in INTEGER_COLUMNS else _decimal_text(raw)
    return values


def _compare_source_rows(left: Mapping[str, Any], right: Mapping[str, Any]) -> list[str]:
    differences: list[str] = []
    for column in CANONICAL_COLUMNS:
        if column == "漲跌(+/-)":
            if _normalise_sign(left.get(column)) != _normalise_sign(right.get(column)):
                differences.append(column)
        elif column in INTEGER_COLUMNS:
            if _integer(left.get(column)) != _integer(right.get(column)):
                differences.append(column)
        elif column == "證券名稱":
            if _text(left.get(column)) != _text(right.get(column)):
                differences.append(column)
        elif _decimal(left.get(column)) != _decimal(right.get(column)):
            differences.append(column)
    return differences


def _load_official_rows(
    capture_dir: Path,
    *,
    required_symbols: Iterable[str],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    capture_dir = capture_dir.resolve()
    receipt_path = capture_dir / "receipt.json"
    response_path = capture_dir / "response.json.gz"
    receipt = _read_json(receipt_path)
    if not response_path.is_file() or response_path.is_symlink():
        raise FileNotFoundError(response_path)
    wire_hash = _sha256_file(response_path)
    response_meta = receipt.get("response")
    if not isinstance(response_meta, Mapping) or response_meta.get("wire_sha256") != wire_hash:
        raise SourceEvidenceError("official wire hash does not match capture receipt")
    with gzip.open(response_path, "rb") as stream:
        decoded = stream.read()
    decoded_hash = f"sha256:{hashlib.sha256(decoded).hexdigest()}"
    if response_meta.get("decoded_sha256") != decoded_hash:
        raise SourceEvidenceError("official decoded hash does not match capture receipt")
    payload = json.loads(decoded.decode("utf-8"))
    if not isinstance(payload, Mapping) or _date_key(payload.get("date")) != TARGET_DATE:
        raise SourceEvidenceError("official response date is not 20260520")
    table = _find_official_table(payload)
    fields = table.get("fields")
    data = table.get("data")
    if not isinstance(fields, list) or not isinstance(data, list):
        raise SourceEvidenceError("official table fields/data missing")
    rows: dict[str, dict[str, Any]] = {}
    for raw_row in data:
        if not isinstance(raw_row, list):
            raise SourceEvidenceError("official row is not an array")
        values = _official_row_values(fields, raw_row)
        symbol = values["symbol"]
        if not symbol:
            continue
        if symbol in rows:
            raise SourceEvidenceError(f"duplicate official symbol: {symbol}")
        rows[symbol] = values
    required = set(required_symbols)
    missing = sorted(required.difference(rows))
    if missing:
        raise SourceEvidenceError(f"official response missing allowlist symbols: {missing[:10]}")
    timing = receipt.get("capture_timing")
    if not isinstance(timing, Mapping):
        raise SourceEvidenceError("official capture timing missing")
    captured_at = timing.get("response_completed_at_utc") or timing.get("quality_known_at")
    if not isinstance(captured_at, str) or not captured_at.startswith("2026-09-07T"):
        raise SourceEvidenceError("official capture timestamp is not the approved 2026-09-07 capture")
    return rows, {
        "receipt_path": str(receipt_path),
        "receipt_sha256": _sha256_file(receipt_path),
        "wire_sha256": wire_hash,
        "decoded_sha256": decoded_hash,
        "official_row_count": len(rows),
        "official_capture_at": captured_at,
        "safety": dict(receipt.get("safety") or {}),
        "response_path": str(response_path),
    }


def _schema_info(connection: sqlite3.Connection) -> dict[str, Any]:
    info = [dict(row) for row in connection.execute('PRAGMA table_info("daily_prices")')]
    if not info:
        raise RepairError("daily_prices table missing")
    columns = [str(row["name"]) for row in info]
    missing = [column for column in (*IDENTITY_COLUMNS, *DB_UPDATE_COLUMNS) if column not in columns]
    if missing:
        raise RepairError(f"daily_prices schema missing required columns: {missing}")
    pk = {str(row["name"]): int(row["pk"] or 0) for row in info}
    if pk.get("日期") != 2 or pk.get("證券代號") != 1:
        raise RepairError(f"daily_prices composite primary key unexpected: {pk}")
    indexes = [dict(row) for row in connection.execute('PRAGMA index_list("daily_prices")')]
    duplicates = connection.execute(
        'SELECT COUNT(*) FROM (SELECT "日期", "證券代號", COUNT(*) AS n FROM "daily_prices" '
        'GROUP BY "日期", "證券代號" HAVING n > 1)'
    ).fetchone()[0]
    if int(duplicates) != 0:
        raise RepairError("daily_prices has duplicate identity rows")
    return {
        "table": "daily_prices",
        "columns": columns,
        "column_info": info,
        "primary_key": pk,
        "indexes": indexes,
        "schema_hash": _payload_hash({"columns": info, "indexes": indexes}),
        "update_columns": [column for column in DB_UPDATE_COLUMNS if column in columns],
        "untouched_technical_columns": [
            column
            for column in columns
            if column not in (*IDENTITY_COLUMNS, *DB_UPDATE_COLUMNS)
        ],
    }


def _fetch_rows(
    connection: sqlite3.Connection,
    keys: Sequence[tuple[str, str]],
    columns: Sequence[str],
) -> dict[tuple[str, str], dict[str, object]]:
    projection = ", ".join(_quote(column) for column in columns)
    result: dict[tuple[str, str], dict[str, object]] = {}
    query = (
        f'SELECT {projection} FROM "daily_prices" WHERE {_quote("日期")} = ? '
        f'AND {_quote("證券代號")} = ?'
    )
    for date, symbol in keys:
        row = connection.execute(query, (date, symbol)).fetchone()
        if row is None:
            raise RowDriftError(f"daily_prices row missing: {(date, symbol)}")
        if (date, symbol) in result:
            raise RowDriftError(f"duplicate daily_prices row: {(date, symbol)}")
        result[(date, symbol)] = dict(zip(columns, row, strict=True))
    return result


def _audit_view(row: Mapping[str, object]) -> dict[str, object]:
    sign = next(
        (_normalise_sign(row.get(column)) for column in ("漲跌(+/-)", "漲跌", "涨跌") if _normalise_sign(row.get(column))),
        None,
    )
    return {
        "date": _date_key(row.get("日期")),
        "symbol": _symbol(row.get("證券代號")),
        "name": _text(row.get("證券名稱")),
        "open": _decimal_text(row.get("開盤價")),
        "high": _decimal_text(row.get("最高價")),
        "low": _decimal_text(row.get("最低價")),
        "close": _decimal_text(row.get("收盤價")),
        "volume_shares": _integer(row.get("成交股數")),
        "turnover": _integer(row.get("成交金額")),
        "change_value": _decimal_text(row.get("漲跌價差")),
        "sign": sign,
    }


def _assert_audit_before(rows: Sequence[dict[str, Any]], current: Mapping[tuple[str, str], Mapping[str, object]]) -> None:
    for item in rows:
        key = (item["date"], item["symbol"])
        actual = _audit_view(current[key])
        expected = item["audit_sqlite"]
        fields = ("open", "high", "low", "close", "volume_shares", "turnover", "change_value", "sign")
        differences = [
            field
            for field in fields
            if (
                _normalise_sign(actual.get(field)) != _normalise_sign(expected.get(field))
                if field == "sign"
                    else (_integer(actual.get(field)) != _integer(expected.get(field)) if field in {"volume_shares", "turnover"} else _decimal(actual.get(field)) != _decimal(expected.get(field)))
            )
        ]
        if differences:
            raise RowDriftError(f"audit before row drift {key}: {differences}")


def _update_values(source: Mapping[str, Any], columns: Sequence[str]) -> dict[str, object]:
    """Map the canonical source row to the explicit daily_prices update set."""

    return {
        column: (
            source.get("漲跌(+/-)")
            if column in {"漲跌(+/-)", "漲跌", "涨跌"}
            else source.get(column)
        )
        for column in columns
    }


def _database_objects_hash(connection: sqlite3.Connection) -> str:
    rows = connection.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master "
        "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
    ).fetchall()
    return _payload_hash(
        [
            [_stable_value(value) for value in row]
            for row in rows
        ]
    )


def _target_date_non_target_fingerprint(
    connection: sqlite3.Connection,
    target_keys: Sequence[tuple[str, str]],
) -> str:
    """Hash only the other rows on 2026-05-20; never scan the 3.6 GB table."""

    columns_info = [dict(row) for row in connection.execute('PRAGMA table_info("daily_prices")')]
    columns = [str(row["name"]) for row in columns_info]
    projection = ", ".join(_quote(column) for column in columns)
    clauses = []
    args: list[str] = [TARGET_DATE]
    for date, symbol in target_keys:
        clauses.append(f"({_quote('日期')} = ? AND {_quote('證券代號')} = ?)")
        args.extend((date, symbol))
    query = (
        f'SELECT {projection} FROM "daily_prices" WHERE "日期" = ? '
        + ("AND NOT (" + " OR ".join(clauses) + ") " if clauses else "")
        + 'ORDER BY "證券代號"'
    )
    digest = hashlib.sha256()
    for row in connection.execute(query, args):
        digest.update(_json_bytes([_stable_value(value) for value in row]))
    return f"sha256:{digest.hexdigest()}"


def _target_rows_fingerprint(rows: Mapping[tuple[str, str], Mapping[str, object]]) -> str:
    payload = [
        {"date": date, "symbol": symbol, "row": _json_row(rows[(date, symbol)])}
        for date, symbol in sorted(rows)
    ]
    return _payload_hash(payload)


def _logical_snapshot(
    connection: sqlite3.Connection,
    *,
    target_keys: Sequence[tuple[str, str]],
    target_rows: Mapping[tuple[str, str], Mapping[str, object]] | None = None,
    schema_hash: str | None = None,
) -> dict[str, Any]:
    rows = target_rows or _fetch_rows(
        connection,
        target_keys,
        [str(row["name"]) for row in connection.execute('PRAGMA table_info("daily_prices")')],
    )
    return {
        "quick_check": str(connection.execute("PRAGMA quick_check").fetchone()[0]),
        "target_rows_hash": _target_rows_fingerprint(rows),
        "target_date_non_target_hash": _target_date_non_target_fingerprint(connection, target_keys),
        "database_objects_hash": _database_objects_hash(connection),
        "schema_hash": schema_hash,
    }


def _capacity(db_path: Path, receipt_dir: Path) -> dict[str, int | str | bool]:
    usage = shutil.disk_usage(db_path.parent)
    db_bytes = db_path.stat().st_size
    estimated_backup_bytes = db_bytes
    estimated_receipt_bytes = max(db_bytes // 100, 16 * 1024 * 1024)
    required = estimated_backup_bytes + estimated_receipt_bytes + 64 * 1024 * 1024
    return {
        "probe_path": str(db_path.parent),
        "receipt_path": str(receipt_dir),
        "total_bytes": int(usage.total),
        "free_bytes": int(usage.free),
        "db_bytes": int(db_bytes),
        "estimated_backup_bytes": int(estimated_backup_bytes),
        "estimated_receipt_bytes": int(estimated_receipt_bytes),
        "required_bytes": int(required),
        "sufficient": bool(usage.free >= required),
    }


def _canonical_path_from_meta(meta: Mapping[str, Any]) -> Path:
    value = meta.get("path")
    if not isinstance(value, str) or not value:
        raise SourceEvidenceError("canonical target file path missing")
    return Path(value)


def prepare_plan(
    *,
    db_path: Path,
    audit_path: Path,
    canonical_path: Path | None,
    capture_dir: Path,
    receipt_dir: Path,
    expected_allowlist_count: int = EXPECTED_ALLOWLIST_COUNT,
    expected_canonical_sha256: str | None = PINNED_CANONICAL_SHA256,
    expected_official_wire_sha256: str | None = PINNED_OFFICIAL_WIRE_SHA256,
    expected_official_decoded_sha256: str | None = PINNED_OFFICIAL_DECODED_SHA256,
) -> dict[str, Any]:
    allowlist, audit_meta = _load_allowlist(audit_path, expected_count=expected_allowlist_count)
    canonical_path = canonical_path or _canonical_path_from_meta(audit_meta["canonical_file"])
    canonical_sha256 = _sha256_file(canonical_path)
    audit_canonical_sha256 = audit_meta["canonical_file"].get("sha256")
    if audit_canonical_sha256 and audit_canonical_sha256 != canonical_sha256:
        raise SourceEvidenceError("canonical CSV does not match audit-pinned hash")
    if expected_canonical_sha256 is not None and canonical_sha256 != expected_canonical_sha256:
        raise SourceEvidenceError("canonical CSV does not match reviewed source hash")
    canonical_rows = _load_canonical_rows(canonical_path)
    missing_canonical = sorted(set(item["symbol"] for item in allowlist).difference(canonical_rows))
    if missing_canonical:
        raise SourceEvidenceError(f"canonical CSV missing allowlist symbols: {missing_canonical[:10]}")
    official_rows, official_meta = _load_official_rows(
        capture_dir,
        required_symbols=(item["symbol"] for item in allowlist),
    )
    if expected_official_wire_sha256 is not None and official_meta["wire_sha256"] != expected_official_wire_sha256:
        raise SourceEvidenceError("official response does not match reviewed wire hash")
    if expected_official_decoded_sha256 is not None and official_meta["decoded_sha256"] != expected_official_decoded_sha256:
        raise SourceEvidenceError("official response does not match reviewed decoded hash")
    source_mismatches: dict[str, list[str]] = {}
    source_name_conflicts: dict[str, dict[str, str]] = {}
    for item in allowlist:
        symbol = item["symbol"]
        differences = _compare_source_rows(canonical_rows[symbol], official_rows[symbol])
        strict_differences = [difference for difference in differences if difference != "證券名稱"]
        if strict_differences:
            source_mismatches[symbol] = strict_differences
        elif "證券名稱" in differences:
            source_name_conflicts[symbol] = {
                "canonical_name": str(canonical_rows[symbol].get("證券名稱") or ""),
                "official_name": str(official_rows[symbol].get("證券名稱") or ""),
            }
    if source_mismatches:
        raise SourceEvidenceError(f"canonical/official source mismatch: {dict(list(source_mismatches.items())[:5])}")
    db_path = db_path.resolve()
    with _open_read_only(db_path) as connection:
        quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        if quick_check.lower() != "ok":
            raise RepairError(f"SQLite quick_check failed: {quick_check}")
        schema = _schema_info(connection)
        keys = [(item["date"], item["symbol"]) for item in allowlist]
        columns = [str(row["name"]) for row in connection.execute('PRAGMA table_info("daily_prices")')]
        before_rows = _fetch_rows(connection, keys, columns)
        _assert_audit_before(allowlist, before_rows)
        update_columns = schema["update_columns"]
        after_rows: dict[tuple[str, str], dict[str, object]] = {}
        for item in allowlist:
            source = canonical_rows[item["symbol"]]
            before = before_rows[(item["date"], item["symbol"])]
            after = dict(before)
            after.update(_update_values(source, update_columns))
            after_rows[(item["date"], item["symbol"])] = after
        target_snapshot = _logical_snapshot(
            connection,
            target_keys=keys,
            target_rows=before_rows,
            schema_hash=schema["schema_hash"],
        )
        target_count = int(
            connection.execute(
                'SELECT COUNT(*) FROM "daily_prices" WHERE "日期" = ?', (TARGET_DATE,)
            ).fetchone()[0]
        )
        db_quick = quick_check
    missing_ohlc = sorted(
        symbol
        for symbol in EXPECTED_MISSING_OHLC_SYMBOLS
        if symbol in canonical_rows
        and all(canonical_rows[symbol].get(column) is None for column in ("開盤價", "最高價", "最低價", "收盤價"))
    )
    plan: dict[str, Any] = {
        "schema_version": REPAIR_SCHEMA,
        "mode": "dry_run",
        "apply_allowed": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "db_path": str(db_path),
        "audit_path": str(audit_path.resolve()),
        "canonical_path": str(canonical_path.resolve()),
        "capture_dir": str(capture_dir.resolve()),
        "receipt_dir": str(receipt_dir.resolve()),
        "source_date": TARGET_DATE,
        "allowlist_count": len(allowlist),
        "allowlist_hash": audit_meta["allowlist_hash"],
        "audit": audit_meta,
        "canonical_sha256": canonical_sha256,
        "official": official_meta,
        "official_source_mismatches": source_mismatches,
        "official_name_conflicts": source_name_conflicts,
        "name_update_policy": "preserve canonical historical CSV name; official name conflict is recorded and never silently promoted",
        "official_capture_at": official_meta["official_capture_at"],
        "available_at": None,
        "available_at_backfilled": False,
        "historical_decision_time_available": False,
        "formal_training_allowed": False,
        "promotion_eligible": False,
        "db_before_snapshot": target_snapshot,
        "db_quick_check": db_quick,
        "target_date_row_count": target_count,
        "schema": schema,
        "source_update_columns": list(schema["update_columns"]),
        "untouched_columns": list(schema["untouched_technical_columns"]),
        "missing_canonical_count": int(audit_meta["target_stats"].get("missing_in_right", 0)) - int(audit_meta["target_stats"].get("missing_in_left", 0)),
        "expected_missing_canonical_count": EXPECTED_MISSING_CANONICAL_COUNT,
        "missing_ohlc_symbols": missing_ohlc,
        "capacity": _capacity(db_path, receipt_dir),
        "full_table_fingerprints": None,
        "table_fingerprint_policy": "online backup custody plus target-row logical hash, target-date non-target hash, sqlite object/trigger hash, schema, and transaction drift checks; no full-table scan",
        "rows": [
            {
                "date": item["date"],
                "symbol": item["symbol"],
                "differing_fields": item["differing_fields"],
                "before": _json_row(before_rows[(item["date"], item["symbol"])]),
                "after": _json_row(after_rows[(item["date"], item["symbol"])]),
                "source": _json_row(canonical_rows[item["symbol"]]),
            }
            for item in allowlist
        ],
    }
    plan["plan_hash"] = _payload_hash(plan)
    return plan


def _verify_plan_hash(plan: Mapping[str, Any]) -> None:
    if plan.get("schema_version") != REPAIR_SCHEMA:
        raise RepairError("repair plan schema mismatch")
    supplied = plan.get("plan_hash")
    body = dict(plan)
    body.pop("plan_hash", None)
    if supplied != _payload_hash(body):
        raise RepairError("repair plan hash mismatch")


def _verify_receipt_hash(receipt: Mapping[str, Any]) -> None:
    supplied = receipt.get("receipt_sha256")
    body = dict(receipt)
    body.pop("receipt_sha256", None)
    if not isinstance(supplied, str) or supplied != _payload_hash(body):
        raise ReceiptError("repair receipt hash mismatch")


def _make_online_backup(db_path: Path, backup_path: Path) -> Path:
    if backup_path.exists() or backup_path.is_symlink():
        raise RepairError(f"backup path already exists: {backup_path}")
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    fd, name = tempfile.mkstemp(prefix=f".{backup_path.name}.", suffix=".tmp", dir=backup_path.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        source = sqlite3.connect(db_path)
        destination = sqlite3.connect(temporary)
        try:
            source.backup(destination)
            if str(destination.execute("PRAGMA quick_check").fetchone()[0]).lower() != "ok":
                raise RepairError("online backup quick_check failed")
            destination.commit()
        finally:
            destination.close()
            source.close()
        temporary.replace(backup_path)
        temporary = None
        return backup_path
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _pending_payload(plan: Mapping[str, Any], backup_path: Path, *, status: str = "pending") -> dict[str, Any]:
    return {
        "schema_version": REPAIR_SCHEMA,
        "receipt_kind": "historical_price_spike_repair_pending",
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_date": TARGET_DATE,
        "allowlist_count": plan["allowlist_count"],
        "allowlist_hash": plan["allowlist_hash"],
        "plan_hash": plan["plan_hash"],
        "db_path": plan["db_path"],
        "db_before_snapshot": plan["db_before_snapshot"],
        "db_before_snapshot_hash": _payload_hash(plan["db_before_snapshot"]),
        "backup_path": str(backup_path.resolve()),
        "canonical_sha256": plan["canonical_sha256"],
        "official_wire_sha256": plan["official"]["wire_sha256"],
        "official_decoded_sha256": plan["official"]["decoded_sha256"],
        "official_name_conflicts": plan.get("official_name_conflicts", {}),
        "name_update_policy": plan.get("name_update_policy"),
        "official_capture_at": plan["official_capture_at"],
        "available_at": None,
        "available_at_backfilled": False,
    }


def _receipt_body(
    plan: Mapping[str, Any],
    *,
    backup_path: Path,
    backup_sha256: str,
    before_snapshot: Mapping[str, Any],
    after_snapshot: Mapping[str, Any],
    transaction_total_changes: int,
    capacity_at_apply: Mapping[str, Any],
    corrected_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": REPAIR_SCHEMA,
        "receipt_kind": "historical_price_spike_repair",
        "status": "applied",
        "source_date": TARGET_DATE,
        "corrected_at": corrected_at,
        "official_capture_at": plan["official_capture_at"],
        "available_at": None,
        "available_at_backfilled": False,
        "historical_decision_time_available": False,
        "formal_training_allowed": False,
        "promotion_eligible": False,
        "db_path": plan["db_path"],
        "db_before_snapshot": dict(before_snapshot),
        "db_after_snapshot": dict(after_snapshot),
        "db_before_snapshot_hash": _payload_hash(before_snapshot),
        "db_after_snapshot_hash": _payload_hash(after_snapshot),
        "backup_path": str(backup_path.resolve()),
        "backup_sha256": backup_sha256,
        "transaction_total_changes": transaction_total_changes,
        "capacity_at_apply": dict(capacity_at_apply),
        "allowlist_count": plan["allowlist_count"],
        "allowlist_hash": plan["allowlist_hash"],
        "plan_hash": plan["plan_hash"],
        "audit_path": plan["audit_path"],
        "audit_sha256": plan["audit"]["audit_sha256"],
        "canonical_path": plan["canonical_path"],
        "canonical_sha256": plan["canonical_sha256"],
        "official_capture_receipt_path": plan["official"]["receipt_path"],
        "official_capture_receipt_sha256": plan["official"]["receipt_sha256"],
        "official_response_path": plan["official"]["response_path"],
        "official_wire_sha256": plan["official"]["wire_sha256"],
        "official_decoded_sha256": plan["official"]["decoded_sha256"],
        "source_update_columns": plan["source_update_columns"],
        "untouched_columns": plan["untouched_columns"],
        "missing_ohlc_symbols": plan["missing_ohlc_symbols"],
        "rows": plan["rows"],
    }


def apply_plan(
    plan: Mapping[str, Any],
    *,
    backup_path: Path,
    pending_path: Path,
    receipt_path: Path,
    lock_path: Path,
    expected_allowlist_count: int = EXPECTED_ALLOWLIST_COUNT,
    pinned_canonical_sha256: str | None = PINNED_CANONICAL_SHA256,
    pinned_official_wire_sha256: str | None = PINNED_OFFICIAL_WIRE_SHA256,
    pinned_official_decoded_sha256: str | None = PINNED_OFFICIAL_DECODED_SHA256,
) -> dict[str, Any]:
    _verify_plan_hash(plan)
    if plan.get("mode") != "dry_run" or int(plan.get("allowlist_count", 0)) != expected_allowlist_count:
        raise RepairError(f"apply requires the approved {expected_allowlist_count}-row dry-run plan")
    if not bool((plan.get("capacity") or {}).get("sufficient")):
        raise RepairError("capacity preflight failed")
    db_path = Path(str(plan["db_path"])).resolve()
    capacity_at_apply = _capacity(db_path, receipt_path.parent)
    if not bool(capacity_at_apply.get("sufficient")):
        raise RepairError("capacity preflight failed at apply time")
    canonical_path = Path(str(plan["canonical_path"])).resolve()
    official_response_path = Path(str(plan["official"]["response_path"])).resolve()
    if _sha256_file(canonical_path) != plan["canonical_sha256"]:
        raise SourceEvidenceError("canonical source changed since dry-run plan")
    if _sha256_file(official_response_path) != plan["official"]["wire_sha256"]:
        raise SourceEvidenceError("official response changed since dry-run plan")
    if pinned_canonical_sha256 is not None and plan["canonical_sha256"] != pinned_canonical_sha256:
        raise SourceEvidenceError("plan canonical source is not the reviewed pinned hash")
    if (
        pinned_official_wire_sha256 is not None
        and plan["official"]["wire_sha256"] != pinned_official_wire_sha256
    ) or (
        pinned_official_decoded_sha256 is not None
        and plan["official"]["decoded_sha256"] != pinned_official_decoded_sha256
    ):
        raise SourceEvidenceError("plan official source is not the reviewed pinned hash")
    reservation = acquire_heavy_chain_reservation(lock_path.resolve())
    if reservation is None:
        raise RepairError(f"maintenance lock unavailable: {lock_path}")
    try:
        backup = _make_online_backup(db_path, backup_path.resolve())
        backup_sha256 = _sha256_file(backup)
        _write_json_atomic(pending_path, _pending_payload(plan, backup), replace=False)
        keys = [(str(row["date"]), str(row["symbol"])) for row in plan["rows"]]
        columns = list((plan.get("schema") or {}).get("columns") or [])
        update_columns = list(plan["source_update_columns"])
        before_snapshot: dict[str, Any]
        after_snapshot: dict[str, Any]
        transaction_total_changes = 0
        try:
            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("BEGIN IMMEDIATE")
                before_rows = _fetch_rows(connection, keys, columns)
                expected_before = {
                    (str(row["date"]), str(row["symbol"])): row["before"]
                    for row in plan["rows"]
                }
                for key, actual in before_rows.items():
                    if _json_row(actual) != dict(expected_before[key]):
                        raise RowDriftError(f"full before row drift inside transaction: {key}")
                before_snapshot = _logical_snapshot(
                    connection,
                    target_keys=keys,
                    target_rows=before_rows,
                    schema_hash=plan["schema"]["schema_hash"],
                )
                if before_snapshot != plan["db_before_snapshot"]:
                    raise RowDriftError("logical DB snapshot changed since dry-run plan")
                total_changes_before = connection.total_changes
                assignments = ", ".join(f"{_quote(column)} = ?" for column in update_columns)
                update_sql = f'UPDATE "daily_prices" SET {assignments} WHERE "日期" = ? AND "證券代號" = ?'
                for row in plan["rows"]:
                    source = row["source"]
                    values = [source.get("漲跌(+/-)") if column in {"漲跌(+/-)", "漲跌", "涨跌"} else source.get(column) for column in update_columns]
                    values.extend((row["date"], row["symbol"]))
                    changed = connection.execute(update_sql, values).rowcount
                    if changed != 1:
                        raise RowDriftError(f"expected one updated row, got {changed}: {(row['date'], row['symbol'])}")
                transaction_total_changes = connection.total_changes - total_changes_before
                if transaction_total_changes != len(plan["rows"]):
                    raise RepairError(
                        "unexpected trigger or extra SQLite changes: "
                        f"{transaction_total_changes} != {len(plan['rows'])}"
                    )
                after_rows = _fetch_rows(connection, keys, columns)
                for row in plan["rows"]:
                    key = (str(row["date"]), str(row["symbol"]))
                    if _json_row(after_rows[key]) != dict(row["after"]):
                        raise RowDriftError(f"full after row mismatch: {key}")
                after_snapshot = _logical_snapshot(
                    connection,
                    target_keys=keys,
                    target_rows=after_rows,
                    schema_hash=plan["schema"]["schema_hash"],
                )
                for field in ("target_date_non_target_hash", "database_objects_hash", "schema_hash"):
                    if before_snapshot[field] != after_snapshot[field]:
                        raise RepairError(f"non-target logical state changed: {field}")
                if str(connection.execute("PRAGMA quick_check").fetchone()[0]).lower() != "ok":
                    raise RepairError("transaction quick_check failed")
                connection.commit()
        except Exception:
            try:
                _write_json_atomic(
                    pending_path,
                    _pending_payload(plan, backup, status="rolled_back_before_commit"),
                    replace=True,
                )
            except Exception:
                pass
            raise
        with _open_read_only(db_path) as verification:
            if str(verification.execute("PRAGMA quick_check").fetchone()[0]).lower() != "ok":
                raise RepairError("post-commit quick_check failed")
            post_rows = _fetch_rows(verification, keys, columns)
            for row in plan["rows"]:
                key = (str(row["date"]), str(row["symbol"]))
                if _json_row(post_rows[key]) != dict(row["after"]):
                    raise RepairError(f"post-commit row verification failed: {key}")
            post_snapshot = _logical_snapshot(
                verification,
                target_keys=keys,
                target_rows=post_rows,
                schema_hash=plan["schema"]["schema_hash"],
            )
            if post_snapshot != after_snapshot:
                raise RepairError("post-commit logical snapshot changed unexpectedly")
        body = _receipt_body(
            plan,
            backup_path=backup,
            backup_sha256=backup_sha256,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
            transaction_total_changes=transaction_total_changes,
            capacity_at_apply=capacity_at_apply,
            corrected_at=datetime.now(timezone.utc).isoformat(),
        )
        final = dict(body)
        final["receipt_sha256"] = _payload_hash(body)
        try:
            _write_json_atomic(receipt_path, final, replace=False)
        except Exception:
            try:
                _write_json_atomic(
                    pending_path,
                    _pending_payload(plan, backup, status="commit_receipt_write_failed"),
                    replace=True,
                )
            except Exception:
                pass
            raise ReceiptError("DB committed but final receipt was not written; pending marker blocks consumers")
        _write_json_atomic(
            pending_path,
            _pending_payload(plan, backup, status="applied_receipt_written"),
            replace=True,
        )
        return final
    finally:
        release_heavy_chain_reservation(reservation)


def rollback_receipt(receipt_path: Path, *, lock_path: Path) -> dict[str, Any]:
    receipt = _read_json(receipt_path)
    _verify_receipt_hash(receipt)
    if receipt.get("receipt_kind") != "historical_price_spike_repair" or receipt.get("status") != "applied":
        raise ReceiptError("rollback requires an applied repair receipt")
    db_path = Path(str(receipt["db_path"])).resolve()
    backup_path = Path(str(receipt["backup_path"])).resolve()
    if _sha256_file(backup_path) != receipt.get("backup_sha256"):
        raise ReceiptError("rollback refused: backup bytes changed")
    repair_rows = receipt.get("rows")
    update_columns = receipt.get("source_update_columns")
    if not isinstance(repair_rows, list) or not repair_rows or not isinstance(update_columns, list):
        raise ReceiptError("receipt lacks row-bound before/after evidence")
    rollback_path = receipt_path.with_name("rollback_receipt.json")
    if rollback_path.exists() or rollback_path.is_symlink():
        raise ReceiptError(f"rollback receipt already exists: {rollback_path}")
    keys = [(str(row["date"]), str(row["symbol"])) for row in repair_rows]
    columns = list(dict(repair_rows[0]["before"]).keys())
    schema_hash = (receipt.get("db_after_snapshot") or {}).get("schema_hash")
    reservation = acquire_heavy_chain_reservation(lock_path.resolve())
    if reservation is None:
        raise RepairError(f"maintenance lock unavailable: {lock_path}")
    try:
        with sqlite3.connect(db_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("BEGIN IMMEDIATE")
            current_rows = _fetch_rows(connection, keys, columns)
            pre_snapshot = _logical_snapshot(
                connection,
                target_keys=keys,
                target_rows=current_rows,
                schema_hash=schema_hash,
            )
            after_snapshot = receipt.get("db_after_snapshot")
            if not isinstance(after_snapshot, Mapping):
                raise ReceiptError("receipt after snapshot missing")
            # An unrelated later write to a target row's untouched column is
            # allowed.  The rows below guard only columns owned by repair;
            # non-target rows/tables are never restored from the backup.
            for row in repair_rows:
                key = (str(row["date"]), str(row["symbol"]))
                current = _json_row(current_rows[key])
                expected_after = dict(row["after"])
                drift = [column for column in update_columns if current.get(column) != expected_after.get(column)]
                if drift:
                    raise RowDriftError(f"rollback refused; repaired columns drifted {key}: {drift}")
            # Only target-date rows outside the repair are guarded.  A later
            # unrelated table/row addition is deliberately preserved.
            pre_non_target_hash = pre_snapshot["target_date_non_target_hash"]
            total_changes_before = connection.total_changes
            assignments = ", ".join(f"{_quote(column)} = ?" for column in update_columns)
            update_sql = f'UPDATE "daily_prices" SET {assignments} WHERE "日期" = ? AND "證券代號" = ?'
            for row in repair_rows:
                before = dict(row["before"])
                values = [before.get(column) for column in update_columns]
                values.extend((row["date"], row["symbol"]))
                if connection.execute(update_sql, values).rowcount != 1:
                    raise RowDriftError(f"rollback expected one row: {(row['date'], row['symbol'])}")
            transaction_total_changes = connection.total_changes - total_changes_before
            if transaction_total_changes != len(repair_rows):
                raise RepairError("rollback encountered unexpected trigger or extra changes")
            restored_rows = _fetch_rows(connection, keys, columns)
            for row in repair_rows:
                key = (str(row["date"]), str(row["symbol"]))
                current = _json_row(restored_rows[key])
                expected_before = dict(row["before"])
                drift = [column for column in update_columns if current.get(column) != expected_before.get(column)]
                if drift:
                    raise RepairError(f"rollback after-row verification failed {key}: {drift}")
            post_snapshot = _logical_snapshot(
                connection,
                target_keys=keys,
                target_rows=restored_rows,
                schema_hash=schema_hash,
            )
            if pre_non_target_hash != post_snapshot["target_date_non_target_hash"]:
                raise RepairError("rollback changed unrelated target-date rows")
            if str(connection.execute("PRAGMA quick_check").fetchone()[0]).lower() != "ok":
                raise RepairError("rollback quick_check failed")
            connection.commit()
        with _open_read_only(db_path) as verification:
            restored_rows = _fetch_rows(verification, keys, columns)
            for row in repair_rows:
                key = (str(row["date"]), str(row["symbol"]))
                current = _json_row(restored_rows[key])
                expected_before = dict(row["before"])
                drift = [column for column in update_columns if current.get(column) != expected_before.get(column)]
                if drift:
                    raise RepairError(f"post-rollback verification failed {key}: {drift}")
        result = {
            "schema_version": REPAIR_SCHEMA,
            "receipt_kind": "historical_price_spike_repair_rollback",
            "status": "rolled_back",
            "rolled_back_at": datetime.now(timezone.utc).isoformat(),
            "source_receipt": str(receipt_path.resolve()),
            "source_receipt_sha256": _sha256_file(receipt_path),
            "db_path": str(db_path),
            "backup_custody_only": True,
            "row_bound": True,
            "preserved_later_unrelated_writes": True,
            "updated_rows": len(repair_rows),
            "transaction_total_changes": transaction_total_changes,
            "restored_columns": list(update_columns),
        }
        result["receipt_sha256"] = _payload_hash(result)
        _write_json_atomic(rollback_path, result, replace=False)
        return result
    finally:
        release_heavy_chain_reservation(reservation)


def _default_paths(data_root: Path, repo_root: Path) -> dict[str, Path]:
    audit = repo_root / "output" / "qa" / "historical_price_spike_20260921" / "no_merged_v2" / "historical_price_spike_audit.json"
    canonical = data_root / "daily_price" / f"{TARGET_DATE}.csv"
    capture = repo_root / "output" / "v4_ml_daily_price_source_quality_20260907" / "twse_official_capture_20260520_v2" / "runs" / "twse-mi-index-20260520-all-f185b2e953836028"
    receipt = data_root / "output" / "scheduled" / "daily_price_repair_receipts" / TARGET_DATE / "historical_price_spike_20260921"
    return {"audit": audit, "canonical": canonical, "capture": capture, "receipt": receipt}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--canonical", type=Path)
    parser.add_argument("--capture-dir", type=Path)
    parser.add_argument("--receipt-dir", type=Path)
    parser.add_argument("--plan", type=Path, default=Path("output/qa/historical_price_spike_20260921/repair_plan.json"))
    parser.add_argument("--backup-path", type=Path)
    parser.add_argument("--lock-path", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm")
    parser.add_argument("--rollback", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    data_root = (args.data_root or Path("D:/Min/Python/Project/FA_Data")).resolve()
    defaults = _default_paths(data_root, repo_root)
    db_path = (args.db_path or data_root / "sqlite" / "twstock.db").resolve()
    receipt_dir = (args.receipt_dir or defaults["receipt"]).resolve()
    lock_path = (args.lock_path or data_root / "output" / "release_v4" / ".ml_heavy_chain.lock").resolve()
    if args.rollback:
        result = rollback_receipt(args.rollback.resolve(), lock_path=lock_path)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.apply:
        if args.confirm != CONFIRM_TOKEN:
            raise RepairError(f"--apply requires --confirm {CONFIRM_TOKEN}")
        plan = _read_json(args.plan.resolve())
        final_path = receipt_dir / "receipt.json"
        pending_path = receipt_dir / "pending.json"
        backup_path = (args.backup_path or receipt_dir / "sqlite_before_repair.db").resolve()
        result = apply_plan(
            plan,
            backup_path=backup_path,
            pending_path=pending_path,
            receipt_path=final_path,
            lock_path=lock_path,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    plan = prepare_plan(
        db_path=db_path,
        audit_path=(args.audit or defaults["audit"]).resolve(),
        canonical_path=(args.canonical or defaults["canonical"]).resolve(),
        capture_dir=(args.capture_dir or defaults["capture"]).resolve(),
        receipt_dir=receipt_dir,
    )
    plan_path = args.plan.resolve()
    _write_json_atomic(plan_path, plan, replace=True)
    print(json.dumps({"mode": "dry_run", "plan": str(plan_path), "plan_hash": plan["plan_hash"], "allowlist_count": plan["allowlist_count"], "db_before_snapshot_hash": _payload_hash(plan["db_before_snapshot"]), "missing_ohlc_symbols": plan["missing_ohlc_symbols"]}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RepairError as exc:
        print(f"repair refused: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
