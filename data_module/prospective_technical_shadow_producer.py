"""Run a bounded prospective technical-indicator recomputation in a shadow DB.

The formal market database is opened read-only.  Only the requested symbols and
the requested feature-input history are copied into a new shadow SQLite file;
the existing ``UpdateService.calculate_technical_indicators`` producer then
calculates and writes the technical rows there.  The resulting evidence binds
the input-row hash, calculator source hash, output-row hash, and completion
time before the normal technical-publication receipt is emitted.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping, Sequence

from app_module.update_service import UpdateService
from data_module.config import TWStockConfig
from data_module.recommendation_calibration_source_contract import (
    build_technical_computation_evidence,
    capture_technical_input_snapshot,
    publish_technical_indicator_receipt,
)


SCHEMA_VERSION = "prospective-technical-shadow-publication.v1"
_REPO_ROOT = Path(__file__).resolve().parents[1]
_CALCULATOR_SOURCE = (
    _REPO_ROOT / "analysis_module" / "technical_analysis" / "technical_indicators.py"
)


def _hash_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _hash_json(value: object) -> str:
    return _hash_bytes(_canonical_json(value).encode("utf-8"))


def _quote_identifier(value: str) -> str:
    if not value or "\x00" in value:
        raise ValueError("invalid_sql_identifier")
    return '"' + value.replace('"', '""') + '"'


def _read_only_connection(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(path)
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _table_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [
        str(row[1])
        for row in connection.execute(
            f"PRAGMA table_info({_quote_identifier(table)})"
        )
    ]


def _date_column(columns: Sequence[str]) -> str:
    for candidate in ("日期", "date", "trade_date", "trading_date", "Date"):
        if candidate in columns:
            return candidate
    raise ValueError("daily_prices_date_column_missing")


def _symbol_column(columns: Sequence[str]) -> str:
    for candidate in ("證券代號", "股票代號", "stock_code", "stock_id"):
        if candidate in columns:
            return candidate
    raise ValueError("daily_prices_symbol_column_missing")


def _normal_date(value: object) -> str:
    text = str(value or "").strip()
    return text.replace("-", "").replace("/", "")[:8]


def _row_payload(columns: Sequence[str], rows: Sequence[sqlite3.Row]) -> list[list[object]]:
    return [
        [row[column] for column in columns]
        for row in rows
    ]


def _snapshot(
    *,
    columns: Sequence[str],
    rows: Sequence[sqlite3.Row],
    date_column: str,
    symbol_column: str,
    source_kind: str,
) -> dict[str, object]:
    payload = {
        "columns": list(columns),
        "rows": _row_payload(columns, rows),
    }
    dates = sorted({_normal_date(row[date_column]) for row in rows if row[date_column]})
    symbols = sorted({str(row[symbol_column]).strip() for row in rows if row[symbol_column]})
    return {
        "source_kind": source_kind,
        "columns": list(columns),
        "row_count": len(rows),
        "symbols": symbols,
        "date_start": dates[0] if dates else None,
        "date_end": dates[-1] if dates else None,
        "content_sha256": _hash_json(payload),
    }


def _copy_daily_price_subset(
    *,
    source_db: Path,
    shadow_db: Path,
    source_date: str,
    symbols: Sequence[str],
) -> dict[str, object]:
    source_date_key = _normal_date(source_date)
    requested_symbols = tuple(sorted({str(symbol).strip() for symbol in symbols if str(symbol).strip()}))
    if not requested_symbols:
        raise ValueError("prospective_technical_symbols_empty")
    with _read_only_connection(source_db) as source:
        columns = _table_columns(source, "daily_prices")
        date_column = _date_column(columns)
        symbol_column = _symbol_column(columns)
        placeholders = ",".join("?" for _ in requested_symbols)
        query = (
            f"SELECT * FROM {_quote_identifier('daily_prices')} "
            f"WHERE {_quote_identifier(symbol_column)} IN ({placeholders}) "
            f"AND REPLACE(REPLACE(CAST({_quote_identifier(date_column)} AS TEXT), '-', ''), '/', '') <= ? "
            f"ORDER BY {_quote_identifier(date_column)} ASC, {_quote_identifier(symbol_column)} ASC"
        )
        rows = source.execute(query, (*requested_symbols, source_date_key)).fetchall()
        if not rows:
            raise ValueError("prospective_technical_daily_input_empty")
        schema_row = source.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            ("daily_prices",),
        ).fetchone()
        create_sql = str(schema_row[0]) if schema_row and schema_row[0] else ""
        if not create_sql:
            raise ValueError("daily_prices_schema_missing")
        auxiliary_tables: dict[str, tuple[str, list[str], list[sqlite3.Row]]] = {}
        for table in ("market_indices", "industry_indices"):
            auxiliary_schema_row = source.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            auxiliary_create_sql = (
                str(auxiliary_schema_row[0])
                if auxiliary_schema_row and auxiliary_schema_row[0]
                else ""
            )
            if not auxiliary_create_sql:
                raise ValueError(f"{table}_schema_missing")
            auxiliary_columns = _table_columns(source, table)
            auxiliary_rows = source.execute(
                f"SELECT * FROM {_quote_identifier(table)}"
            ).fetchall()
            auxiliary_tables[table] = (
                auxiliary_create_sql,
                auxiliary_columns,
                auxiliary_rows,
            )

    shadow_db.parent.mkdir(parents=True, exist_ok=True)
    if shadow_db.exists():
        raise FileExistsError(f"shadow_database_already_exists:{shadow_db}")
    with sqlite3.connect(shadow_db) as shadow:
        shadow.execute(create_sql)
        # Keep the publication contract's required feature columns present in
        # the isolated destination.  The existing calculator writes RSI/MACD
        # and may leave ADX null; null is preserved as an observed output and
        # is never converted into a fabricated value.
        shadow.execute(
            """
            CREATE TABLE technical_indicators (
                "日期" TEXT,
                "證券代號" TEXT,
                "RSI" REAL,
                "MACD" REAL,
                "ADX" REAL,
                PRIMARY KEY ("證券代號", "日期")
            )
            """
        )
        for table, (auxiliary_create_sql, auxiliary_columns, auxiliary_rows) in auxiliary_tables.items():
            shadow.execute(auxiliary_create_sql)
            quoted_auxiliary_columns = ",".join(
                _quote_identifier(column) for column in auxiliary_columns
            )
            auxiliary_placeholders = ",".join("?" for _ in auxiliary_columns)
            shadow.executemany(
                f"INSERT INTO {_quote_identifier(table)} ({quoted_auxiliary_columns}) VALUES ({auxiliary_placeholders})",
                [
                    tuple(row[column] for column in auxiliary_columns)
                    for row in auxiliary_rows
                ],
            )
        quoted_columns = ",".join(_quote_identifier(column) for column in columns)
        placeholders = ",".join("?" for _ in columns)
        shadow.executemany(
            f"INSERT INTO {_quote_identifier('daily_prices')} ({quoted_columns}) VALUES ({placeholders})",
            [tuple(row[column] for column in columns) for row in rows],
        )
        shadow.commit()
    return _snapshot(
        columns=columns,
        rows=rows,
        date_column=date_column,
        symbol_column=symbol_column,
        source_kind="formal_daily_prices_read_only_subset",
    )


def _technical_snapshot(
    *,
    shadow_db: Path,
    source_date: str,
    symbols: Sequence[str],
) -> dict[str, object]:
    with _read_only_connection(shadow_db) as connection:
        columns = _table_columns(connection, "technical_indicators")
        date_column = _date_column(columns)
        symbol_column = _symbol_column(columns)
        placeholders = ",".join("?" for _ in symbols)
        rows = connection.execute(
            f"SELECT * FROM {_quote_identifier('technical_indicators')} "
            f"WHERE {_quote_identifier(date_column)} = ? "
            f"AND {_quote_identifier(symbol_column)} IN ({placeholders}) "
            f"ORDER BY {_quote_identifier(symbol_column)} ASC",
            (_normal_date(source_date), *symbols),
        ).fetchall()
    snapshot = _snapshot(
        columns=columns,
        rows=rows,
        date_column=date_column,
        symbol_column=symbol_column,
        source_kind="isolated_technical_indicators_output",
    )
    snapshot["requested_symbols"] = sorted(str(symbol) for symbol in symbols)
    snapshot_symbols = snapshot.get("symbols")
    if not isinstance(snapshot_symbols, list):
        snapshot_symbols = []
    snapshot["missing_symbols"] = sorted(
        {str(symbol) for symbol in symbols} - {str(symbol) for symbol in snapshot_symbols}
    )
    return snapshot


def _receipt_paths(output_root: Path, source_date: str) -> list[Path]:
    date_key = _normal_date(source_date)
    paths = sorted(
        output_root.glob(
            f"scheduled/daily_price_source_custody/*/{date_key}/*/receipt.json"
        )
    )
    required = {"twse.mi_index.daily_price", "tpex.daily_close_quotes"}
    selected: list[Path] = []
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(payload, Mapping) and payload.get("source_id") in required:
            selected.append(path)
    found = {
        str(json.loads(path.read_text(encoding="utf-8")).get("source_id"))
        for path in selected
    }
    if found != required:
        raise ValueError("prospective_technical_daily_source_custody_incomplete")
    return selected


def run_prospective_technical_shadow(
    *,
    source_db: str | Path,
    data_root: str | Path,
    output_root: str | Path,
    source_date: str,
    symbols: Sequence[str],
) -> dict[str, object]:
    """Recompute a bounded symbol cohort and publish its verified receipt."""

    formal_db = Path(source_db).expanduser().resolve()
    isolated_data_root = Path(data_root).expanduser().resolve()
    shadow_output = Path(output_root).expanduser().resolve()
    shadow_db = isolated_data_root / "sqlite" / "twstock.db"
    input_snapshot = _copy_daily_price_subset(
        source_db=formal_db,
        shadow_db=shadow_db,
        source_date=source_date,
        symbols=symbols,
    )
    config = TWStockConfig(
        data_root=isolated_data_root,
        output_root=shadow_output,
        technical_process_pool_enabled=False,
    )
    config.min_data_days = 30
    service = UpdateService(config)
    started_at = datetime.now(timezone.utc)
    calculation = service.calculate_technical_indicators(
        target_stock=None,
        force_all=True,
        start_date=None,
        progress_callback=None,
        incremental_lookback_days=120,
        technical_process_pool=False,
    )
    completed_at = datetime.now(timezone.utc)
    if not calculation.get("success"):
        raise RuntimeError(
            "prospective_technical_recomputation_failed:"
            + str(calculation.get("message") or "unknown")
        )
    output_snapshot = _technical_snapshot(
        shadow_db=shadow_db,
        source_date=source_date,
        symbols=symbols,
    )
    missing_symbols = output_snapshot.get("missing_symbols")
    if isinstance(missing_symbols, list) and missing_symbols:
        raise ValueError(
            "prospective_technical_output_symbol_coverage_missing:"
            + ",".join(str(value) for value in missing_symbols)
        )
    source_receipt_paths = _receipt_paths(shadow_output, source_date)
    computation = build_technical_computation_evidence(
        source_db=shadow_db,
        calculation_result={
            **calculation,
            "formal_source_db": str(formal_db),
            "isolated_shadow_db": str(shadow_db),
            "source_date": _normal_date(source_date),
            "symbols": sorted(str(symbol) for symbol in symbols),
            "formal_daily_price_input_snapshot": input_snapshot,
            "shadow_output_snapshot": output_snapshot,
        },
        source_date_start=_normal_date(source_date),
        source_date_end=_normal_date(source_date),
        started_at=started_at,
        completed_at=completed_at,
        input_snapshot=capture_technical_input_snapshot(shadow_db),
    )
    update_status: dict[str, Any] = {
        "task": "baldr-data-update-quick-daily-shadow",
        "status": "passed",
        "run_id": "prospective-technical-shadow-" + completed_at.strftime("%Y%m%dT%H%M%S%fZ"),
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "writes_market_data_db": False,
        "formal_source_contract_eligible": False,
        "steps": [
            {
                "name": "calculate_technical_indicators",
                "status": "passed",
                "result": {
                    "success": True,
                    "source_db": str(shadow_db),
                    "technical_computation": computation,
                    "source_receipts": [
                        {"receipt_path": str(path)}
                        for path in source_receipt_paths
                    ],
                },
            }
        ],
    }
    publication = publish_technical_indicator_receipt(
        output_root=shadow_output,
        update_status=update_status,
        source_db=shadow_db,
    )
    if publication.get("status") != "published":
        raise RuntimeError(
            "prospective_technical_receipt_publish_failed:"
            + str(publication.get("reason") or "unknown")
        )
    return {
        "status": "published",
        "schema_version": SCHEMA_VERSION,
        "shadow_db": str(shadow_db),
        "technical_computation": computation,
        "technical_publication_receipt": publication,
        "update_status": update_status,
    }


__all__ = ["SCHEMA_VERSION", "run_prospective_technical_shadow"]
