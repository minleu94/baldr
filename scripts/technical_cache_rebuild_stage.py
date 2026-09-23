"""Build an isolated technical-indicator and CSV stage from an immutable DB backup.

This module is deliberately a staging-only tool: source SQLite and formal CSVs are
opened read-only, while every generated file is placed beneath ``output_dir``.
"""
from __future__ import annotations

import csv
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
from typing import Any, Iterable, Mapping, Sequence, TypedDict, cast

import pandas as pd

from analysis_module.technical_analysis.technical_indicators import (
    CAUSAL_INDICATOR_COLUMNS,
    calculate_causal_indicators,
)


SCHEMA_VERSION = "technical-cache-rebuild-stage.v1"
COMPUTED_TABLE = "technical_rebuild_values"
DAILY_TABLE = "daily_prices"
TECHNICAL_TABLE = "technical_indicators"
DAILY_REQUIRED = ("日期", "證券代號", "開盤價", "最高價", "最低價", "收盤價", "成交股數")
DAILY_COPY_COLUMNS = (
    "證券名稱",
    "成交股數",
    "成交筆數",
    "成交金額",
    "開盤價",
    "最高價",
    "最低價",
    "收盤價",
    "漲跌",
    "漲跌價差",
    "最後揭示買價",
    "最後揭示買量",
    "最後揭示賣價",
    "最後揭示賣量",
    "本益比",
)
OHLCV_COLUMNS = ("開盤價", "最高價", "最低價", "收盤價", "成交股數")
REBUILD_COLUMNS = (*CAUSAL_INDICATOR_COLUMNS, *OHLCV_COLUMNS)
KEY_COLUMNS = ("日期", "證券代號")
CSV_ENCODING = "utf-8-sig"


class _StageCounts(TypedDict):
    rows: int
    symbols: int
    symbols_without_source: list[str]
    per_stock_preserved_rows_without_source: int
    aggregate_preserved_rows_without_source: int


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(payload: object) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _atomic_bytes(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_csv(path: Path, fieldnames: Sequence[str], rows: Iterable[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding=CSV_ENCODING, newline="") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=list(fieldnames),
                extrasaction="raise",
                lineterminator="\n",
            )
            writer.writeheader()
            for row in rows:
                writer.writerow({name: row.get(name, "") for name in fieldnames})
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _formal_target(root: Path, path: Path) -> Path:
    candidate = path.resolve(strict=False)
    resolved_root = root.resolve(strict=True)
    if not candidate.is_relative_to(resolved_root):
        raise ValueError(f"formal target escapes formal_root: {path}")
    if path.is_symlink():
        raise ValueError(f"formal CSV must not be a symlink: {path}")
    return candidate


def _normalize_date(value: object) -> str:
    text = str(value).strip()
    compact = text.replace("-", "").replace("/", "")
    if not re.fullmatch(r"\d{8}", compact):
        raise ValueError(f"unsupported daily date: {value!r}")
    return datetime.strptime(compact, "%Y%m%d").strftime("%Y%m%d")


def _csv_date_style(value: object) -> str:
    text = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return "iso"
    if re.fullmatch(r"\d{4}/\d{2}/\d{2}", text):
        return "slash"
    return "compact"


def _format_csv_date(day: str, style: str | None) -> str:
    if style == "slash":
        return f"{day[:4]}/{day[4:6]}/{day[6:]}"
    if style == "compact":
        return day
    return f"{day[:4]}-{day[4:6]}-{day[6:]}"


def _normalize_symbol(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, int):
        text = str(value)
    elif isinstance(value, float) and math.isfinite(value) and value.is_integer():
        text = str(int(value))
    else:
        text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if text.isdigit() and len(text) < 4:
        text = text.zfill(4)
    return text


def _safe_symbol(symbol: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,24}", symbol):
        raise ValueError(f"unsafe stock code for CSV path: {symbol!r}")


def _source_connection(path: Path) -> sqlite3.Connection:
    uri = path.resolve(strict=True).as_uri() + "?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _table_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    if connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is None:
        raise ValueError(f"source database is missing table {table}")
    return [str(row[1]) for row in connection.execute(f"PRAGMA table_info({_quote(table)})")]


def _target_symbols(connection: sqlite3.Connection) -> tuple[list[str], list[str]]:
    daily_symbols = {
        symbol
        for (raw,) in connection.execute(f"SELECT DISTINCT {_quote('證券代號')} FROM {_quote(DAILY_TABLE)}")
        if (symbol := _normalize_symbol(raw))
    }
    technical_symbols = {
        symbol
        for (raw,) in connection.execute(
            f"SELECT DISTINCT {_quote('證券代號')} FROM {_quote(TECHNICAL_TABLE)}"
        )
        if (symbol := _normalize_symbol(raw))
    }
    targets = sorted(daily_symbols | technical_symbols)
    for symbol in targets:
        _safe_symbol(symbol)
    return targets, sorted(technical_symbols)


def _computed_schema(connection: sqlite3.Connection, source_columns: Sequence[str]) -> list[str]:
    columns = [*DAILY_COPY_COLUMNS]
    included = [name for name in columns if name in source_columns]
    declarations = [f'{_quote("日期")} TEXT NOT NULL', f'{_quote("證券代號")} TEXT NOT NULL']
    declarations.extend(f"{_quote(name)} REAL" for name in CAUSAL_INDICATOR_COLUMNS)
    for name in included:
        if name == "成交股數" or name in {"成交筆數", "成交金額", "最後揭示買量", "最後揭示賣量"}:
            kind = "INTEGER"
        elif name == "證券名稱" or name == "漲跌":
            kind = "TEXT"
        else:
            kind = "REAL"
        declarations.append(f"{_quote(name)} {kind}")
    connection.execute(
        f"CREATE TABLE {_quote(COMPUTED_TABLE)} ({', '.join(declarations)}, "
        f"PRIMARY KEY ({_quote('日期')}, {_quote('證券代號')})) WITHOUT ROWID"
    )
    connection.execute(
        f"CREATE INDEX idx_{COMPUTED_TABLE}_symbol_date ON {_quote(COMPUTED_TABLE)} "
        f"({_quote('證券代號')}, {_quote('日期')})"
    )
    connection.execute(
        "CREATE TABLE seen_aggregate_keys ("
        '"日期" TEXT NOT NULL, "證券代號" TEXT NOT NULL, "row_json" TEXT NOT NULL, '
        'PRIMARY KEY ("日期", "證券代號")) WITHOUT ROWID'
    )
    return included


def _number_for_storage(value: object) -> float | None:
    if value is None:
        return None
    try:
        number = float(cast(Any, value))
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _csv_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if not math.isfinite(value):
            return ""
        return repr(value)
    if hasattr(value, "item"):
        try:
            return _csv_value(value.item())
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def _make_read_frame(source_rows: list[dict[str, Any]], symbol: str) -> pd.DataFrame:
    frame = pd.DataFrame(source_rows)
    frame["日期"] = frame["_date_key"]
    frame["證券代號"] = symbol
    return frame


def _daily_groups(
    connection: sqlite3.Connection,
    daily_columns: Sequence[str],
    targets: set[str],
) -> Iterable[tuple[str, list[dict[str, Any]]]]:
    connection.create_function("normalize_stock", 1, _normalize_symbol, deterministic=True)
    date_order = f"replace(replace(CAST({_quote('日期')} AS TEXT), '-', ''), '/', '')"
    query = (
        f"SELECT {', '.join(_quote(name) for name in daily_columns)} "
        f"FROM {_quote(DAILY_TABLE)} "
        f"ORDER BY normalize_stock({_quote('證券代號')}), {date_order}, "
        f"CAST({_quote('證券代號')} AS TEXT)"
    )
    active_symbol: str | None = None
    group: list[dict[str, Any]] = []
    seen_dates: set[str] = set()
    cursor = connection.execute(query)
    for raw in cursor:
        symbol = _normalize_symbol(raw["證券代號"])
        if symbol != active_symbol:
            if active_symbol in targets and group:
                yield active_symbol, group
            active_symbol, group, seen_dates = symbol, [], set()
        if symbol not in targets:
            continue
        day = _normalize_date(raw["日期"])
        if day in seen_dates:
            raise ValueError(f"duplicate source daily key: {symbol}/{day}")
        seen_dates.add(day)
        row = {name: raw[name] for name in daily_columns}
        row["_date_key"] = day
        row["日期"] = day
        row["證券代號"] = symbol
        group.append(row)
    if active_symbol in targets and group:
        yield active_symbol, group


def _calculate_symbol(
    symbol: str,
    source_rows: list[dict[str, Any]],
    source_columns: Sequence[str],
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    source_rows.sort(key=lambda row: row["_date_key"])
    frame = _make_read_frame(source_rows, symbol)
    calculated = calculate_causal_indicators(frame)
    if len(calculated) != len(source_rows):
        raise ValueError(f"causal calculation changed row count for {symbol}")
    records: list[dict[str, Any]] = []
    indicator_rows = calculated[list(CAUSAL_INDICATOR_COLUMNS)].itertuples(
        index=False, name=None
    )
    for row, indicators in zip(source_rows, indicator_rows, strict=True):
        output: dict[str, Any] = {
            "日期": row["_date_key"],
            "證券代號": symbol,
        }
        for name, value in zip(CAUSAL_INDICATOR_COLUMNS, indicators, strict=True):
            output[name] = _number_for_storage(value)
        for name in source_columns:
            if name == "日期":
                continue
            if name == "證券代號":
                output[name] = symbol
            else:
                output[name] = row.get(name)
        records.append(output)
    return calculated, records


def _computed_insert_sql(source_columns: Sequence[str]) -> tuple[str, list[str]]:
    included = [name for name in DAILY_COPY_COLUMNS if name in source_columns]
    columns = ["日期", "證券代號", *CAUSAL_INDICATOR_COLUMNS, *included]
    sql = (
        f"INSERT INTO {_quote(COMPUTED_TABLE)} "
        f"({', '.join(_quote(name) for name in columns)}) "
        f"VALUES ({', '.join('?' for _ in columns)})"
    )
    return sql, columns


def _insert_computed(
    connection: sqlite3.Connection,
    sql: str,
    columns: Sequence[str],
    records: Sequence[Mapping[str, Any]],
) -> None:
    values = []
    for row in records:
        values.append(
            [
                row.get(name)
                if name not in CAUSAL_INDICATOR_COLUMNS
                else _number_for_storage(row.get(name))
                for name in columns
            ]
        )
    connection.executemany(sql, values)


def _csv_header(path: Path, *, default_fields: Sequence[str]) -> tuple[list[str], int]:
    if not path.exists():
        return list(default_fields), 0
    with path.open("r", encoding=CSV_ENCODING, newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {path}")
        fields = [str(name) for name in reader.fieldnames]
        if len(set(fields)) != len(fields) or any(not name for name in fields):
            raise ValueError(f"CSV has duplicate or empty columns: {path}")
        return fields, len(fields)


def _fields_with_targets(path: Path, default_fields: Sequence[str]) -> list[str]:
    fields, _ = _csv_header(path, default_fields=default_fields)
    if "日期" not in fields or "證券代號" not in fields:
        raise ValueError(f"CSV is missing 日期/證券代號 keys: {path}")
    return [*fields, *(name for name in REBUILD_COLUMNS if name not in fields)]


def _default_csv_fields(source_columns: Sequence[str]) -> list[str]:
    return list(dict.fromkeys([*KEY_COLUMNS, *source_columns, *CAUSAL_INDICATOR_COLUMNS]))


def _load_computed_for_symbol(
    connection: sqlite3.Connection,
    symbol: str,
) -> dict[str, dict[str, Any]]:
    rows = connection.execute(
        f"SELECT * FROM {_quote(COMPUTED_TABLE)} WHERE {_quote('證券代號')}=? ORDER BY {_quote('日期')}",
        (symbol,),
    )
    return {str(row["日期"]): dict(row) for row in rows}


def _merge_symbol_csv(
    target: Path,
    staged: Path,
    symbol: str,
    computed: Mapping[str, Mapping[str, Any]],
    source_columns: Sequence[str],
    before_hash: str | None,
) -> dict[str, Any]:
    source_name = target.name
    fields = _fields_with_targets(
        target,
        _default_csv_fields(source_columns),
    )
    staged_rows: list[dict[str, str]] = []
    seen: set[str] = set()
    updated = 0
    preserved_without_source = 0
    date_style: str | None = None
    if target.exists():
        with target.open("r", encoding=CSV_ENCODING, newline="") as stream:
            reader = csv.DictReader(stream)
            for raw in reader:
                if None in raw:
                    raise ValueError(f"CSV row has more values than header: {target}")
                raw_day = raw.get("日期", "")
                day = _normalize_date(raw_day)
                if date_style is None:
                    date_style = _csv_date_style(raw_day)
                existing_symbol = _normalize_symbol(raw.get("證券代號", symbol)) or symbol
                if existing_symbol != symbol:
                    raise ValueError(f"stock id does not match filename {source_name}: {existing_symbol}")
                if day in seen:
                    raise ValueError(f"duplicate technical CSV key: {symbol}/{day}")
                seen.add(day)
                row = {name: str(raw.get(name) or "") for name in fields}
                if not raw.get("證券代號"):
                    row["證券代號"] = symbol
                current = computed.get(day)
                if current is not None:
                    for column in REBUILD_COLUMNS:
                        row[column] = _csv_value(current.get(column))
                    updated += 1
                else:
                    preserved_without_source += 1
                staged_rows.append(row)
    added = 0
    for day, current in computed.items():
        if day in seen:
            continue
        row = {name: "" for name in fields}
        for name in source_columns:
            if name in row:
                row[name] = _csv_value(current.get(name))
        row["日期"] = _format_csv_date(day, date_style)
        row["證券代號"] = symbol
        for column in REBUILD_COLUMNS:
            row[column] = _csv_value(current.get(column))
        staged_rows.append(row)
        added += 1
    staged_rows.sort(key=lambda row: _normalize_date(row["日期"]))
    _atomic_csv(staged, fields, staged_rows)
    if target.exists() and _sha256_file(target) != before_hash:
        raise ValueError(f"formal CSV changed while staging: {target}")
    return {
        "target_path": str(target.resolve(strict=False)),
        "staged_path": str(staged.resolve(strict=False)),
        "before_sha256": before_hash,
        "after_sha256": _sha256_file(staged),
        "row_count_before": len(seen),
        "row_count_after": len(staged_rows),
        "updated_existing_rows": updated,
        "added_source_rows": added,
        "preserved_rows_without_source": preserved_without_source,
        "updated_columns": list(REBUILD_COLUMNS),
        "unchanged_columns": [name for name in fields if name not in REBUILD_COLUMNS],
    }


def _merge_aggregate_csv(
    target: Path,
    staged: Path,
    computed: sqlite3.Connection,
    source_columns: Sequence[str],
    before_hash: str | None,
) -> dict[str, Any]:
    fields = _fields_with_targets(target, _default_csv_fields(source_columns))
    computed.row_factory = sqlite3.Row
    updated = 0
    preserved_without_source = 0
    row_count_before = 0
    added = 0
    rows_emitted = 0
    date_style: str | None = None

    def output_rows() -> Iterable[Mapping[str, object]]:
        nonlocal updated, preserved_without_source, row_count_before, added, rows_emitted, date_style
        if target.exists():
            with target.open("r", encoding=CSV_ENCODING, newline="") as stream:
                reader = csv.DictReader(stream)
                for raw in reader:
                    if None in raw:
                        raise ValueError(f"CSV row has more values than header: {target}")
                    raw_day = raw.get("日期", "")
                    day = _normalize_date(raw_day)
                    if date_style is None:
                        date_style = _csv_date_style(raw_day)
                    symbol = _normalize_symbol(raw.get("證券代號", ""))
                    if not symbol:
                        raise ValueError(f"CSV has empty stock key: {target}/{day}")
                    current = computed.execute(
                        f"SELECT * FROM {_quote(COMPUTED_TABLE)} "
                        f"WHERE {_quote('日期')}=? AND {_quote('證券代號')}=?",
                        (day, symbol),
                    ).fetchone()
                    row = {name: str(raw.get(name) or "") for name in fields}
                    if current is None:
                        preserved_without_source += 1
                    else:
                        for column in REBUILD_COLUMNS:
                            row[column] = _csv_value(current[column])
                        updated += 1
                    try:
                        computed.execute(
                            "INSERT INTO seen_aggregate_keys VALUES (?, ?, ?)",
                            (
                                day,
                                symbol,
                                json.dumps(row, ensure_ascii=False, separators=(",", ":")),
                            ),
                        )
                    except sqlite3.IntegrityError as exc:
                        raise ValueError(f"duplicate all-stocks CSV key: {symbol}/{day}") from exc
                    row_count_before += 1
                    if row_count_before % 250_000 == 0:
                        print(
                            f"[technical-cache-stage] aggregate rows scanned: {row_count_before:,}",
                            flush=True,
                        )
        rows = computed.execute(
            f"SELECT c.* FROM {_quote(COMPUTED_TABLE)} c "
            "LEFT JOIN seen_aggregate_keys s ON "
            'c."日期"=s."日期" AND c."證券代號"=s."證券代號" '
            'WHERE s."日期" IS NULL ORDER BY c."日期", c."證券代號"'
        )
        for current in rows:
            day, symbol = str(current["日期"]), str(current["證券代號"])
            row = {name: "" for name in fields}
            for name in source_columns:
                if name in row:
                    row[name] = _csv_value(current[name])
            row["日期"] = _format_csv_date(day, date_style)
            row["證券代號"] = symbol
            for column in REBUILD_COLUMNS:
                row[column] = _csv_value(current[column])
            computed.execute(
                "INSERT INTO seen_aggregate_keys VALUES (?, ?, ?)",
                (
                    day,
                    symbol,
                    json.dumps(row, ensure_ascii=False, separators=(",", ":")),
                ),
            )
            added += 1
        rows = computed.execute(
            "SELECT row_json FROM seen_aggregate_keys ORDER BY \"日期\", \"證券代號\""
        )
        for (row_json,) in rows:
            rows_emitted += 1
            if rows_emitted % 250_000 == 0:
                print(
                    f"[technical-cache-stage] aggregate rows written: {rows_emitted:,}",
                    flush=True,
                )
            yield json.loads(row_json)

    _atomic_csv(staged, fields, output_rows())
    computed.commit()
    if target.exists() and _sha256_file(target) != before_hash:
        raise ValueError(f"formal CSV changed while staging: {target}")
    return {
        "target_path": str(target.resolve(strict=False)),
        "staged_path": str(staged.resolve(strict=False)),
        "before_sha256": before_hash,
        "after_sha256": _sha256_file(staged),
        "row_count_before": row_count_before,
        "row_count_after": row_count_before + added,
        "updated_existing_rows": updated,
        "added_source_rows": added,
        "preserved_rows_without_source": preserved_without_source,
        "updated_columns": list(REBUILD_COLUMNS),
        "unchanged_columns": [name for name in fields if name not in REBUILD_COLUMNS],
    }


def _formal_hash_before(path: Path) -> str | None:
    return _sha256_file(path) if path.is_file() else None


def stage_rebuild(source_db: Path, formal_root: Path, output_dir: Path) -> dict[str, Any]:
    """Stage all causal indicators without writing to ``source_db`` or ``formal_root``.

    ``output_dir`` must be new. The completed directory is atomically published so
    callers can rerun this function with a new output directory without replacing a
    previous reviewable artifact.
    """
    source = Path(source_db).resolve(strict=True)
    root = Path(formal_root).resolve(strict=True)
    output = Path(output_dir).resolve(strict=False)
    if not source.is_file():
        raise FileNotFoundError(source)
    if output == root or output.is_relative_to(root):
        receipt_root = root / "output" / "scheduled" / "formal_technical_repair_receipts"
        receipt_relative = output.relative_to(receipt_root) if output.is_relative_to(receipt_root) else None
        if (
            receipt_relative is None
            or len(receipt_relative.parts) != 2
            or receipt_relative.parts[-1].lower() != "stage"
        ):
            raise ValueError(
                "output_dir inside formal_root is allowed only at "
                "output/scheduled/formal_technical_repair_receipts/<run>/stage"
            )
    if output.exists():
        raise FileExistsError(f"refusing to overwrite stage output: {output}")
    if output == source or source.is_relative_to(output):
        raise ValueError("output_dir cannot contain source_db")
    output.parent.mkdir(parents=True, exist_ok=True)
    source_before = _sha256_file(source)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    computed_path = temporary / "computed.sqlite"
    technical_dir = _formal_target(root, root / "technical_analysis")
    aggregate_path = _formal_target(root, root / "meta_data" / "all_stocks_data.csv")
    source_files: list[dict[str, Any]] = []
    computed_connection: sqlite3.Connection | None = None
    counts: _StageCounts = {
        "rows": 0,
        "symbols": 0,
        "symbols_without_source": [],
        "per_stock_preserved_rows_without_source": 0,
        "aggregate_preserved_rows_without_source": 0,
    }
    try:
        with _source_connection(source) as src:
            daily_columns = _table_columns(src, DAILY_TABLE)
            missing = sorted(set(DAILY_REQUIRED) - set(daily_columns))
            if missing:
                raise ValueError(f"daily_prices is missing required columns: {missing}")
            technical_columns = _table_columns(src, TECHNICAL_TABLE)
            if "證券代號" not in technical_columns:
                raise ValueError("technical_indicators is missing 證券代號")
            targets, _technical_symbols = _target_symbols(src)
            source_columns = [
                "日期",
                "證券代號",
                *(name for name in DAILY_COPY_COLUMNS if name in daily_columns),
            ]

            db = sqlite3.connect(computed_path)
            computed_connection = db
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("PRAGMA synchronous=FULL")
            _computed_schema(db, source_columns)
            insert_sql, insert_columns = _computed_insert_sql(source_columns)
            target_set = set(targets)
            symbols_seen: set[str] = set()
            with db:
                for symbol, rows in _daily_groups(src, daily_columns, target_set):
                    calculated, records = _calculate_symbol(symbol, rows, source_columns)
                    del calculated
                    _insert_computed(db, insert_sql, insert_columns, records)
                    symbols_seen.add(symbol)
                    counts["rows"] += len(records)
                    target_path = _formal_target(
                        root, technical_dir / f"{symbol}_indicators.csv"
                    )
                    before_hash = _formal_hash_before(target_path)
                    staged_path = temporary / "staged" / "technical_analysis" / target_path.name
                    computed_for_symbol = _load_computed_for_symbol(db, symbol)
                    file_record = _merge_symbol_csv(
                        target_path,
                        staged_path,
                        symbol,
                        computed_for_symbol,
                        source_columns,
                        before_hash,
                    )
                    source_files.append(file_record)
                    counts["per_stock_preserved_rows_without_source"] += int(
                        file_record["preserved_rows_without_source"]
                    )
                    if len(symbols_seen) % 50 == 0:
                        print(
                            f"[technical-cache-stage] symbols: {len(symbols_seen):,}; "
                            f"computed rows: {counts['rows']:,}",
                            flush=True,
                        )
            db.commit()

            counts["symbols"] = len(symbols_seen)
            counts["symbols_without_source"] = sorted(target_set - symbols_seen)
            if counts["rows"] or aggregate_path.exists():
                before_hash = _formal_hash_before(aggregate_path)
                staged_aggregate = temporary / "staged" / "meta_data" / "all_stocks_data.csv"
                aggregate_record = _merge_aggregate_csv(
                    aggregate_path,
                    staged_aggregate,
                    db,
                    source_columns,
                    before_hash,
                )
                source_files.append(aggregate_record)
                counts["aggregate_preserved_rows_without_source"] = int(
                    aggregate_record["preserved_rows_without_source"]
                )
            db.close()
            computed_connection = None

        if _sha256_file(source) != source_before:
            raise ValueError("immutable source database changed during staging")
        computed_hash = _sha256_file(computed_path)
        # The stage directory is published with a single rename. Rewrite paths
        # captured while building under the private temporary directory so the
        # manifest points at the final artifact locations.
        for file_record in source_files:
            staged_path = Path(file_record["staged_path"])
            file_record["staged_path"] = str(
                (output / staged_path.relative_to(temporary)).resolve(strict=False)
            )
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "source_db": str(source),
            "source_sha256": source_before,
            "computed_db": str(output / "computed.sqlite"),
            "computed_sha256": computed_hash,
            "computed_table": COMPUTED_TABLE,
            "rows": counts["rows"],
            "symbols": targets,
            "target_symbol_scope": (
                "all existing daily_prices symbols union existing technical_indicators symbols"
            ),
            "computed_symbols": counts["symbols"],
            "symbols_without_source": counts["symbols_without_source"],
            "files": source_files,
            "indicator_columns": list(CAUSAL_INDICATOR_COLUMNS),
            "canonical_ohlcv_columns": list(OHLCV_COLUMNS),
            "preserved_existing_no_source_keys": {
                "per_stock_csv_rows": counts["per_stock_preserved_rows_without_source"],
                "aggregate_csv_rows": counts["aggregate_preserved_rows_without_source"],
            },
            "unchanged_columns_promise": "existing non-rebuild columns retain their row values; source keys without a daily_prices row are preserved and counted",
            "formal_files_read_only": True,
            "source_db_read_only": True,
            "historical_pit": False,
        }
        _atomic_bytes(temporary / "manifest.json", _json_bytes(manifest))
        if output.exists():
            raise FileExistsError(f"refusing to overwrite stage output: {output}")
        os.rename(temporary, output)
        return manifest
    except BaseException:
        if computed_connection is not None:
            computed_connection.close()
        if temporary.exists():
            resolved_temporary = temporary.resolve(strict=True)
            resolved_parent = output.parent.resolve(strict=True)
            if (
                resolved_temporary.parent != resolved_parent
                or not resolved_temporary.name.startswith(f".{output.name}.")
            ):
                raise RuntimeError(
                    f"refusing to remove unexpected staging temporary: {resolved_temporary}"
                )
            shutil.rmtree(resolved_temporary, ignore_errors=True)
        raise
