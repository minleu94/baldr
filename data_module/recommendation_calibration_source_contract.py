"""Operational source-contract and lane audit for recommendation calibration.

The contract is an append-only shadow artifact.  It binds real daily-update
receipts, technical-publication receipts, official market-event publications,
and cost provenance without modifying the formal SQLite database.  Historical
PIT eligibility is never inferred from a later capture; prospective readiness
and historical replay readiness are reported separately.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Mapping, Sequence
from uuid import uuid4


SCHEMA_VERSION = "recommendation-calibration-source-contract.v1"
TECHNICAL_PUBLICATION_SCHEMA_VERSION = "technical-indicator-publication-receipt.v1"
TECHNICAL_COMPUTATION_SCHEMA_VERSION = "technical-computation-evidence.v1"
_SHA256 = "sha256:"


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash_bytes(value: bytes) -> str:
    return _SHA256 + hashlib.sha256(value).hexdigest()


def _hash_payload(value: Mapping[str, object]) -> str:
    return _hash_bytes(_canonical_json(value).encode("utf-8"))


def _hash_file(path: Path) -> str | None:
    if not path.is_file() or path.is_symlink():
        return None
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    except OSError:
        return None
    return _SHA256 + digest.hexdigest()


def _read_json(path: Path) -> Mapping[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, Mapping) else None


def _write_create_only(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError(f"immutable source-contract conflict: {path}")
        return
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _date_text(value: object) -> str | None:
    text = str(value or "").strip().replace("/", "-")
    if len(text) == 8 and text.isdigit():
        text = f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def _aware_datetime(value: object) -> datetime | None:
    """Parse an availability timestamp and normalize it to UTC."""

    text = str(value or "").strip().replace("Z", "+00:00")
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _availability_before_or_at(value: object, cutoff: datetime | None) -> bool:
    parsed = _aware_datetime(value)
    return parsed is not None and (cutoff is None or parsed <= cutoff)


def _date_key(value: object) -> str | None:
    normalized = _date_text(value)
    return normalized.replace("-", "") if normalized else None


def _verified_content_hash(payload: Mapping[str, Any], field_name: str) -> bool:
    declared = payload.get(field_name)
    if not isinstance(declared, str) or not declared.startswith(_SHA256):
        return False
    body = {key: value for key, value in payload.items() if key != field_name}
    return declared == _hash_payload(body)


def _technical_output_snapshot(
    source_db: str | Path | None,
    *,
    source_date_start: str | None,
    source_date_end: str | None,
) -> dict[str, object]:
    """Hash the exact technical rows visible after the update step.

    This is deliberately a prospective operational fingerprint.  It is not a
    substitute for a row-level ``available_at`` column or the formal
    recommendation source-contract table used by historical replay.
    """

    if source_db is None:
        return {"status": "not_bound", "verified": False, "reason": "source_db_not_supplied"}
    path = Path(source_db).expanduser().resolve()
    if not path.is_file() or path.is_symlink():
        return {"status": "missing", "verified": False, "reason": "source_db_missing"}
    start_key = _date_key(source_date_start)
    end_key = _date_key(source_date_end)
    start_iso = _date_text(source_date_start)
    end_iso = _date_text(source_date_end)
    if not start_key or not end_key or not start_iso or not end_iso:
        return {"status": "blocked", "verified": False, "reason": "technical_source_date_invalid"}
    columns = ("日期", "證券代號", "RSI", "MACD", "ADX")
    try:
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
            connection.execute("PRAGMA query_only=ON")
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if "technical_indicators" not in tables:
                return {
                    "status": "missing_table",
                    "verified": False,
                    "reason": "technical_indicators_table_missing",
                }
            actual_columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(technical_indicators)")
            }
            missing = sorted(set(columns) - actual_columns)
            if missing:
                return {
                    "status": "schema_incomplete",
                    "verified": False,
                    "reason": "technical_columns_missing:" + ",".join(missing),
                }
            rows = []
            for row in connection.execute(
                'SELECT "日期", "證券代號", "RSI", "MACD", "ADX" '
                'FROM "technical_indicators" '
                'WHERE ("日期" >= ? AND "日期" <= ?) '
                '   OR ("日期" >= ? AND "日期" <= ?) '
                'ORDER BY "日期", "證券代號"',
                (start_key, end_key, start_iso, end_iso),
            ):
                normalized_row_date = _date_text(row[0])
                if normalized_row_date is None or not start_iso <= normalized_row_date <= end_iso:
                    continue
                rows.append([_canonical_json_value(value) for value in row])
    except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
        return {
            "status": "unreadable",
            "verified": False,
            "reason": f"technical_output_read_failed:{type(exc).__name__}",
        }
    covered_symbols = sorted({str(row[1]).strip() for row in rows if str(row[1]).strip()})
    actual_dates = sorted({str(row[0]).strip() for row in rows if str(row[0]).strip()})
    digest_body = {
        "component": "technical",
        "source_table": "technical_indicators",
        "columns": list(columns),
        "source_date_start": start_key,
        "source_date_end": end_key,
        "rows": rows,
    }
    snapshot: dict[str, object] = {
        "status": "captured" if rows else "empty",
        "verified": bool(rows),
        "source_db": str(path),
        "source_table": "technical_indicators",
        "source_columns": list(columns),
        "requested_date_start": _date_text(source_date_start),
        "requested_date_end": _date_text(source_date_end),
        "actual_date_start": _date_text(actual_dates[0]) if actual_dates else None,
        "actual_date_end": _date_text(actual_dates[-1]) if actual_dates else None,
        "row_count": len(rows),
        "covered_symbols": covered_symbols,
        # Keep the row-level digest separate from the envelope digest.  The
        # envelope is what the receipt verifier recomputes; the row digest is
        # the immutable fingerprint of the exact technical rows.
        "rows_sha256": _hash_payload(digest_body),
        "reason": None if rows else "technical_output_rows_empty",
    }
    snapshot["content_sha256"] = _hash_payload(
        {key: value for key, value in snapshot.items() if key != "content_sha256"}
    )
    return snapshot


def _prospective_feature_snapshot(
    *,
    source_db: str | Path,
    decision_date: str,
    history_start_date: str,
    symbols: Sequence[str],
    captured_at: str | None = None,
) -> dict[str, object]:
    """Materialize the exact feature rows that a future capture may use.

    The source contract must bind more than a publication receipt hash.  This
    snapshot is produced from the same read-only provider/feature builder used
    by the scheduled capture path, so a later capture can compare its actual
    feature values to an immutable, source-bound row set.  It is prospective
    evidence only; it never creates historical PIT eligibility.
    """

    requested_symbols = tuple(
        sorted({str(symbol).strip() for symbol in symbols if str(symbol).strip()})
    )
    if not requested_symbols:
        return {
            "status": "blocked",
            "verified": False,
            "reason": "prospective_feature_symbols_empty",
        }
    try:
        from data_module.ml_historical_snapshot_provider import MLHistoricalSnapshotProvider
        from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY
        from ml_module.historical_feature_builder import HistoricalFeatureBuilder

        provider = MLHistoricalSnapshotProvider(database_path=Path(source_db).expanduser().resolve())
        feature_builder = HistoricalFeatureBuilder(CORE_LONG_HISTORY_FEATURE_REGISTRY)
        raw_snapshot = provider.load(
            decision_date=_date_text(decision_date) or str(decision_date)[:10],
            history_start_date=_date_text(history_start_date) or str(history_start_date)[:10],
            symbols=requested_symbols,
            industry_index_names=(),
        )
        feature_rows = feature_builder.compute(
            raw_snapshot,
            industry_index_name_by_symbol={},
        )
        rows = [
            {
                "symbol": str(row.symbol),
                "decision_date": _date_text(row.decision_date),
                "feature_as_of_date": _date_text(row.feature_as_of_date),
                "feature_available_date": _date_text(row.available_date),
                "feature_ids": list(CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_ids),
                "feature_values": [value for _, value in row.values],
                "snapshot_hash": str(getattr(row, "snapshot_hash", "") or ""),
            }
            for row in sorted(feature_rows, key=lambda item: str(item.symbol))
        ]
        row_symbols = [str(row["symbol"]) for row in rows]
        if row_symbols != list(requested_symbols) or len(set(row_symbols)) != len(row_symbols):
            return {
                "status": "blocked",
                "verified": False,
                "reason": "prospective_feature_symbol_coverage_incomplete",
                "requested_symbols": list(requested_symbols),
                "covered_symbols": sorted(set(row_symbols)),
                "row_count": len(rows),
            }
        body = {
            "component": "prospective_recommendation_features",
            "source_db": str(Path(source_db).expanduser().resolve()),
            "decision_date": _date_text(decision_date),
            "history_start_date": _date_text(history_start_date),
            "feature_registry_hash": CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
            "feature_schema_hash": feature_builder.load_contract.schema_hash,
            "symbols": list(requested_symbols),
            "rows": rows,
        }
        snapshot: dict[str, object] = {
            "status": "captured",
            "verified": True,
            "captured_at": captured_at or datetime.now(timezone.utc).isoformat(),
            **body,
            "row_count": len(rows),
            "rows_sha256": _hash_payload(body),
            "reason": None,
        }
        snapshot["content_sha256"] = _hash_payload(
            {key: value for key, value in snapshot.items() if key != "content_sha256"}
        )
        return snapshot
    except (ImportError, OSError, RuntimeError, TypeError, ValueError, sqlite3.Error) as exc:
        return {
            "status": "blocked",
            "verified": False,
            "reason": f"prospective_feature_snapshot_failed:{type(exc).__name__}",
        }


def _technical_input_snapshot(
    source_db: str | Path | None,
    *,
    source_date_start: str | None = None,
    source_date_end: str | None = None,
) -> dict[str, object]:
    """Capture the rows visible to the real technical calculator.

    The calculator currently loads ``daily_prices`` as a whole before applying
    its per-symbol incremental window.  This snapshot therefore fingerprints
    that complete read boundary instead of claiming that a later technical
    table is an input witness.  Rows are hashed incrementally so a production
    SQLite file does not have to be materialised as one JSON object.
    """

    if source_db is None:
        return {"status": "not_bound", "verified": False, "reason": "source_db_not_supplied"}
    path = Path(source_db).expanduser().resolve()
    if not path.is_file() or path.is_symlink():
        return {"status": "missing", "verified": False, "reason": "source_db_missing"}
    start_key = _date_key(source_date_start) if source_date_start else None
    end_key = _date_key(source_date_end) if source_date_end else None
    if (source_date_start and not start_key) or (source_date_end and not end_key):
        return {"status": "blocked", "verified": False, "reason": "technical_input_date_invalid"}

    try:
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if "daily_prices" not in tables:
                return {
                    "status": "missing_table",
                    "verified": False,
                    "reason": "daily_prices_table_missing",
                }
            columns = [
                str(row[1])
                for row in connection.execute('PRAGMA table_info("daily_prices")')
            ]
            date_column = next(
                (
                    candidate
                    for candidate in ("日期", "date", "trade_date", "trading_date", "Date")
                    if candidate in columns
                ),
                None,
            )
            symbol_column = next(
                (
                    candidate
                    for candidate in ("證券代號", "股票代號", "stock_code", "stock_id")
                    if candidate in columns
                ),
                None,
            )
            if not date_column or not symbol_column:
                return {
                    "status": "schema_incomplete",
                    "verified": False,
                    "reason": "daily_prices_date_or_symbol_column_missing",
                }

            date_expression = (
                f"REPLACE(REPLACE(CAST({_quote_identifier(date_column)} AS TEXT), '-', ''), '/', '')"
            )
            predicates: list[str] = []
            parameters: list[str] = []
            if start_key:
                predicates.append(f"{date_expression} >= ?")
                parameters.append(start_key)
            if end_key:
                predicates.append(f"{date_expression} <= ?")
                parameters.append(end_key)
            where_clause = f" WHERE {' AND '.join(predicates)}" if predicates else ""
            query = (
                f'SELECT * FROM "daily_prices"{where_clause} '
                f'ORDER BY {_quote_identifier(date_column)}, {_quote_identifier(symbol_column)}'
            )
            row_digest = hashlib.sha256()
            row_count = 0
            actual_dates: set[str] = set()
            covered_symbols: set[str] = set()
            cursor = connection.execute(query, parameters)
            while batch := cursor.fetchmany(5000):
                for row in batch:
                    values = [_canonical_json_value(value) for value in row]
                    encoded = _canonical_json(values).encode("utf-8")
                    row_digest.update(encoded)
                    row_digest.update(b"\n")
                    row_count += 1
                    normalized_date = _date_text(row[date_column])
                    if normalized_date:
                        actual_dates.add(normalized_date)
                    symbol = str(row[symbol_column] or "").strip()
                    if symbol:
                        covered_symbols.add(symbol)
    except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
        return {
            "status": "unreadable",
            "verified": False,
            "reason": f"technical_input_read_failed:{type(exc).__name__}",
        }

    body: dict[str, object] = {
        "component": "technical_input",
        "source_table": "daily_prices",
        "source_columns": columns,
        "requested_date_start": _date_text(source_date_start),
        "requested_date_end": _date_text(source_date_end),
        "actual_date_start": min(actual_dates) if actual_dates else None,
        "actual_date_end": max(actual_dates) if actual_dates else None,
        "row_count": row_count,
        "covered_symbols": sorted(covered_symbols),
        "rows_sha256": _SHA256 + row_digest.hexdigest(),
    }
    snapshot: dict[str, object] = {
        "status": "captured" if row_count else "empty",
        "verified": bool(row_count),
        "source_db": str(path),
        **body,
        "reason": None if row_count else "technical_input_rows_empty",
    }
    snapshot["content_sha256"] = _hash_payload(
        {key: value for key, value in snapshot.items() if key != "content_sha256"}
    )
    return snapshot


def _quote_identifier(value: str) -> str:
    if not value or "\x00" in value:
        raise ValueError("invalid_sql_identifier")
    return '"' + value.replace('"', '""') + '"'


def _technical_receipt_source_dates(paths: Iterable[Path]) -> list[str]:
    dates: set[str] = set()
    for path in paths:
        payload = _read_json(path)
        if not isinstance(payload, Mapping):
            continue
        if payload.get("schema_version") != "official-daily-price-response-capture.v1":
            continue
        if payload.get("source_id") not in {
            "twse.mi_index.daily_price",
            "tpex.daily_close_quotes",
        }:
            continue
        value = _date_text(payload.get("source_date"))
        if value:
            dates.add(value)
    return sorted(dates)


def discover_daily_price_receipt_paths(
    output_root: str | Path,
    *,
    values: object | None = None,
    source_date_start: str | None = None,
    source_date_end: str | None = None,
) -> list[Path]:
    """Find official daily-price receipts for one bounded scheduler window."""

    root = Path(output_root).expanduser().resolve()
    candidates: set[Path] = set()
    if values is not None:
        collected: set[str] = set()
        _collect_receipt_paths(values, collected)
        candidates.update(Path(value) for value in collected)
    custody_root = root / "scheduled" / "daily_price_source_custody"
    if custody_root.is_dir():
        candidates.update(custody_root.glob("*/*/*/receipt.json"))
    start = _date_text(source_date_start) if source_date_start else None
    end = _date_text(source_date_end) if source_date_end else None
    selected: list[Path] = []
    for path in sorted(candidates):
        payload = _read_json(path)
        if not isinstance(payload, Mapping):
            continue
        if payload.get("schema_version") != "official-daily-price-response-capture.v1":
            continue
        if payload.get("source_id") not in {
            "twse.mi_index.daily_price",
            "tpex.daily_close_quotes",
        }:
            continue
        source_date = _date_text(payload.get("source_date"))
        if not source_date or (start and source_date < start) or (end and source_date > end):
            continue
        selected.append(path.resolve())
    return list(dict.fromkeys(selected))


def daily_price_receipt_source_dates(paths: Iterable[Path | str]) -> list[str]:
    """Return canonical source dates from validated-candidate receipt paths."""

    return _technical_receipt_source_dates(Path(path) for path in paths)


def build_technical_computation_evidence(
    *,
    source_db: str | Path,
    calculation_result: Mapping[str, Any],
    source_date_start: str,
    source_date_end: str,
    started_at: datetime | str,
    completed_at: datetime | str,
    input_snapshot: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build a hash-bound witness for an actual technical calculation."""

    resolved_input = (
        dict(input_snapshot)
        if isinstance(input_snapshot, Mapping)
        else _technical_input_snapshot(
            source_db,
            source_date_start=source_date_start,
            source_date_end=source_date_end,
        )
    )
    calculator_source = (
        Path(__file__).resolve().parents[1]
        / "analysis_module"
        / "technical_analysis"
        / "technical_indicators.py"
    )
    output = _technical_output_snapshot(
        source_db,
        source_date_start=source_date_start,
        source_date_end=source_date_end,
    )
    output_evidence = {
        "source_snapshot": output,
        "source_db": output.get("source_db"),
        "source_table": output.get("source_table"),
        "rows_sha256": output.get("rows_sha256"),
        "row_count": output.get("row_count"),
        "symbols": output.get("covered_symbols", []),
        "date_start": output.get("actual_date_start"),
        "date_end": output.get("actual_date_end"),
        "missing_symbols": [],
    }
    output_evidence["content_sha256"] = _hash_payload(output_evidence)
    started_text = started_at.isoformat() if isinstance(started_at, datetime) else str(started_at)
    completed_text = completed_at.isoformat() if isinstance(completed_at, datetime) else str(completed_at)
    body: dict[str, object] = {
        "schema_version": TECHNICAL_COMPUTATION_SCHEMA_VERSION,
        "producer": "data_module.recommendation_calibration_source_contract",
        "source_db": str(Path(source_db).expanduser().resolve()),
        "source_date_start": _date_text(source_date_start),
        "source_date_end": _date_text(source_date_end),
        "input_snapshot": resolved_input,
        "algorithm": {
            "implementation": (
                "analysis_module.technical_analysis.technical_indicators."
                "TechnicalIndicatorCalculator.calculate_all_indicators"
            ),
            "source_path": str(calculator_source),
            "source_sha256": _hash_file(calculator_source),
        },
        "calculation_result": dict(calculation_result),
        "output_snapshot": output_evidence,
        "started_at": started_text,
        "completed_at": completed_text,
        "formal_source_contract_eligible": False,
        "historical_pit_eligible": False,
    }
    body["evidence_sha256"] = _hash_payload(body)
    return body


def capture_technical_input_snapshot(
    source_db: str | Path,
    *,
    source_date_start: str | None = None,
    source_date_end: str | None = None,
) -> dict[str, object]:
    """Public wrapper for the pre-calculation daily-price snapshot."""

    return _technical_input_snapshot(
        source_db,
        source_date_start=source_date_start,
        source_date_end=source_date_end,
    )


def _canonical_json_value(value: object) -> object:
    if isinstance(value, float):
        return None if value != value or value in {float("inf"), float("-inf")} else value
    return value


def _collect_receipt_paths(value: object, result: set[str]) -> None:
    if isinstance(value, Mapping):
        receipt = value.get("receipt_path")
        if isinstance(receipt, str) and receipt.strip():
            result.add(str(Path(receipt).expanduser().resolve()))
        for child in value.values():
            _collect_receipt_paths(child, result)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _collect_receipt_paths(child, result)


def _verify_technical_computation_evidence(
    evidence: object,
    *,
    technical_output: Mapping[str, object],
    source_dates: Sequence[str],
    completed_at: str,
) -> tuple[bool, str, Mapping[str, object] | None]:
    """Verify a real recomputation witness before publishing a passed step."""

    if not isinstance(evidence, Mapping):
        return False, "technical_computation_evidence_missing", None
    declared_evidence_hash = evidence.get("evidence_sha256")
    evidence_body = {
        key: value for key, value in evidence.items() if key != "evidence_sha256"
    }
    if (
        not isinstance(declared_evidence_hash, str)
        or declared_evidence_hash != _hash_payload(evidence_body)
    ):
        return False, "technical_computation_evidence_hash_invalid", None
    calculation = evidence.get("calculation_result")
    if not isinstance(calculation, Mapping) or calculation.get("success") is not True:
        return False, "technical_computation_result_not_successful", None
    input_snapshot = evidence.get("input_snapshot")
    if not isinstance(input_snapshot, Mapping):
        return False, "technical_input_snapshot_missing", None
    if (
        not _verified_content_hash(input_snapshot, "content_sha256")
        or not isinstance(input_snapshot.get("rows_sha256"), str)
        or int(input_snapshot.get("row_count") or 0) <= 0
    ):
        return False, "technical_input_snapshot_unverified", None
    algorithm = evidence.get("algorithm")
    if not isinstance(algorithm, Mapping):
        return False, "technical_algorithm_version_missing", None
    algorithm_path = Path(str(algorithm.get("source_path") or "")).expanduser()
    algorithm_hash = _hash_file(algorithm_path) if algorithm_path else None
    if (
        not algorithm_hash
        or algorithm_hash != algorithm.get("source_sha256")
    ):
        return False, "technical_algorithm_source_hash_invalid", None
    output_snapshot = evidence.get("output_snapshot")
    if not isinstance(output_snapshot, Mapping):
        return False, "technical_output_snapshot_missing", None
    if (
        not _verified_content_hash(output_snapshot, "content_sha256")
        or not isinstance(output_snapshot.get("rows_sha256"), str)
        or int(output_snapshot.get("row_count") or 0) <= 0
        or output_snapshot.get("missing_symbols")
    ):
        return False, "technical_output_snapshot_unverified", None
    source_snapshot = output_snapshot.get("source_snapshot")
    if not isinstance(source_snapshot, Mapping):
        return False, "technical_output_source_snapshot_missing", None
    if not _verified_content_hash(source_snapshot, "content_sha256"):
        return False, "technical_output_source_snapshot_hash_invalid", None
    if source_snapshot.get("rows_sha256") != output_snapshot.get("rows_sha256"):
        return False, "technical_output_row_hash_binding_invalid", None
    if source_snapshot.get("content_sha256") != technical_output.get("content_sha256"):
        return False, "technical_output_content_binding_invalid", None
    if source_snapshot.get("rows_sha256") != technical_output.get("rows_sha256"):
        return False, "technical_output_value_binding_invalid", None
    if output_snapshot.get("source_db") != source_snapshot.get("source_db"):
        return False, "technical_output_source_db_binding_invalid", None
    if output_snapshot.get("row_count") != technical_output.get("row_count"):
        return False, "technical_output_row_count_binding_invalid", None
    evidence_symbols_value = output_snapshot.get("symbols")
    technical_symbols_value = technical_output.get("covered_symbols")
    if not isinstance(evidence_symbols_value, (list, tuple, set)):
        return False, "technical_output_symbol_binding_invalid", None
    if not isinstance(technical_symbols_value, (list, tuple, set)):
        return False, "technical_output_symbol_binding_invalid", None
    if {str(value) for value in evidence_symbols_value} != {
        str(value) for value in technical_symbols_value
    }:
        return False, "technical_output_symbol_binding_invalid", None
    if (
        source_dates
        and _date_text(output_snapshot.get("date_end"))
        != _date_text(source_dates[-1])
    ):
        return False, "technical_output_date_binding_invalid", None
    try:
        evidence_completed = datetime.fromisoformat(
            str(evidence.get("completed_at") or "").replace("Z", "+00:00")
        )
        publication_completed = datetime.fromisoformat(
            str(completed_at).replace("Z", "+00:00")
        )
        if (
            evidence_completed.tzinfo is None
            or publication_completed.tzinfo is None
            or evidence_completed > publication_completed
        ):
            return False, "technical_computation_completion_time_invalid", None
    except (TypeError, ValueError):
        return False, "technical_computation_completion_time_invalid", None
    return True, "verified", evidence


def publish_technical_indicator_receipt(
    *,
    output_root: str | Path,
    update_status: Mapping[str, Any],
    source_db: str | Path | None = None,
    authorized_output_roots: Sequence[str | Path] | None = None,
) -> dict[str, object]:
    """Bind a successful daily-update/indicator publication to source receipts.

    A ``skipped`` technical step is accepted only when the scheduler recorded
    a successful currentity check.  The resulting receipt remains prospective
    and never asserts historical PIT availability.
    """

    steps = update_status.get("steps")
    technical_step: Mapping[str, Any] | None = None
    if isinstance(steps, list):
        for step in steps:
            if isinstance(step, Mapping) and step.get("name") == "calculate_technical_indicators":
                technical_step = step
                break
    if str(update_status.get("status") or "") not in {"passed", "passed_with_warnings"}:
        return {"status": "blocked", "reason": "daily_update_not_successful"}
    technical_step_status = str(technical_step.get("status") or "") if technical_step else ""
    technical_result = technical_step.get("result") if technical_step else None
    if not isinstance(technical_result, Mapping):
        technical_result = {}
    if technical_step_status not in {"passed", "skipped"} or technical_result.get("success") is False:
        return {"status": "blocked", "reason": "technical_indicators_not_published_in_run"}
    receipt_roots = tuple(
        dict.fromkeys(
            Path(root).expanduser().resolve()
            for root in (authorized_output_roots or (output_root,))
        )
    )
    receipt_paths: set[str] = set()
    for receipt_root in receipt_roots:
        for path in discover_daily_price_receipt_paths(
            receipt_root,
            values=steps,
            source_date_start=update_status.get("start_date"),
            source_date_end=update_status.get("end_date"),
        ):
            if _path_is_within_any_root(path, receipt_roots):
                receipt_paths.add(str(path))
    bound: list[dict[str, object]] = []
    for raw_path_text in sorted(receipt_paths):
        path = Path(raw_path_text)
        payload = _read_json(path)
        digest = _hash_file(path)
        if payload is None or digest is None:
            continue
        if payload.get("schema_version") != "official-daily-price-response-capture.v1":
            continue
        if payload.get("source_id") not in {
            "twse.mi_index.daily_price",
            "tpex.daily_close_quotes",
        }:
            # Intraday quote observations have a different semantic contract;
            # they must never satisfy the daily-price/technical input lane.
            continue
        if not _verified_content_hash(payload, "content_sha256"):
            continue
        raw_path_value = payload.get("raw_response_path")
        raw_response_path = (
            (path.parent / str(raw_path_value)).resolve()
            if isinstance(raw_path_value, str) and not Path(raw_path_value).is_absolute()
            else Path(str(raw_path_value)).resolve()
            if raw_path_value
            else path.parent / "raw_response.bin"
        )
        if (
            raw_response_path.is_symlink()
            or not raw_response_path.is_file()
            or not raw_response_path.is_relative_to(path.parent.resolve())
            or _hash_file(raw_response_path) != payload.get("raw_response_sha256")
        ):
            continue
        bound.append(
            {
                "receipt_path": str(path),
                "receipt_sha256": digest,
                "source_id": payload.get("source_id"),
                "source_date": payload.get("source_date"),
                "available_at": payload.get("available_at"),
                "raw_response_sha256": payload.get("raw_response_sha256"),
                "raw_response_path": str(raw_response_path),
                "source_columns": payload.get("source_columns", []),
                "content_sha256": payload.get("content_sha256"),
            }
        )
    if not bound:
        return {"status": "blocked", "reason": "daily_source_custody_receipts_missing"}
    source_dates = sorted(
        value for value in (_date_text(item.get("source_date")) for item in bound) if value
    )
    technical_output = _technical_output_snapshot(
        source_db,
        source_date_start=source_dates[0] if source_dates else None,
        source_date_end=source_dates[-1] if source_dates else None,
    )
    if not technical_output.get("verified"):
        return {
            "status": "blocked",
            "reason": str(technical_output.get("reason") or "technical_output_fingerprint_missing"),
            "technical_output": technical_output,
            "source_receipt_count": len(bound),
        }
    completed_at = str(update_status.get("completed_at") or "").strip()
    computation_evidence_status = "not_run_currentity_skip"
    computation_evidence: Mapping[str, object] | None = None
    computation_reuse: Mapping[str, object] | None = None
    available_at = completed_at or None
    if technical_step_status == "passed":
        evidence_ok, evidence_reason, computation_evidence = (
            _verify_technical_computation_evidence(
                technical_result.get("technical_computation"),
                technical_output=technical_output,
                source_dates=source_dates,
                completed_at=completed_at,
            )
        )
        if not evidence_ok:
            return {
                "status": "blocked",
                "reason": evidence_reason,
                "technical_output": technical_output,
                "source_receipt_count": len(bound),
            }
        computation_evidence_status = "verified"
    elif technical_step_status == "skipped" and technical_result.get("technical_computation") is not None:
        reuse_value = technical_result.get("technical_computation_reuse")
        if not isinstance(reuse_value, Mapping):
            return {
                "status": "blocked",
                "reason": "technical_computation_reuse_lineage_missing",
                "technical_output": technical_output,
                "source_receipt_count": len(bound),
            }
        reuse_path = Path(str(reuse_value.get("path") or "")).expanduser()
        reuse_hash = _hash_file(reuse_path) if reuse_path else None
        reuse_available_at = str(reuse_value.get("available_at") or "").strip()
        reuse_cutoff = _aware_datetime(reuse_available_at)
        publication_cutoff = _aware_datetime(completed_at)
        if (
            reuse_path.is_symlink()
            or not reuse_path.is_file()
            or reuse_hash != reuse_value.get("sha256")
            or reuse_cutoff is None
            or (
                publication_cutoff is not None
                and reuse_cutoff > publication_cutoff
            )
        ):
            return {
                "status": "blocked",
                "reason": "technical_computation_reuse_lineage_invalid",
                "technical_output": technical_output,
                "source_receipt_count": len(bound),
            }
        evidence_ok, evidence_reason, computation_evidence = (
            _verify_technical_computation_evidence(
                technical_result.get("technical_computation"),
                technical_output=technical_output,
                source_dates=source_dates,
                completed_at=reuse_available_at,
            )
        )
        if not evidence_ok:
            return {
                "status": "blocked",
                "reason": evidence_reason,
                "technical_output": technical_output,
                "source_receipt_count": len(bound),
            }
        computation_evidence_status = "verified"
        computation_reuse = dict(reuse_value)
        available_at = reuse_available_at
    availability_basis = (
        "technical_calculation_step_completed"
        if technical_step_status == "passed"
        else "technical_verified_computation_reused"
        if computation_evidence_status == "verified"
        else "technical_currentity_check_completed"
    )
    body: dict[str, object] = {
        "schema_version": TECHNICAL_PUBLICATION_SCHEMA_VERSION,
        "producer": "data_module.recommendation_calibration_source_contract",
        "publication_kind": "technical_indicator_publication",
        "run_id": update_status.get("run_id"),
        "source_date_start": source_dates[0] if source_dates else None,
        "source_date_end": source_dates[-1] if source_dates else None,
        "available_at": available_at,
        "publication_run_completed_at": completed_at or None,
        "availability_basis": availability_basis,
        "technical_step_status": technical_step_status,
        "technical_step_result_sha256": _hash_payload(dict(technical_result)),
        "technical_source_table": "technical_indicators",
        "technical_source_columns": ["日期", "證券代號", "RSI", "MACD", "ADX"],
        "source_receipts": bound,
        "technical_output": technical_output,
        "technical_computation_evidence": computation_evidence,
        "technical_computation_evidence_status": computation_evidence_status,
        "technical_computation_reuse": computation_reuse,
        "publication_time_verified": True,
        "historical_pit_eligible": False,
        "prospective_source_only": True,
        "formal_source_contract_eligible": False,
    }
    payload = {**body, "content_sha256": _hash_payload(body)}
    digest = str(payload["content_sha256"])
    path = (
        Path(output_root).expanduser().resolve()
        / "scheduled"
        / "technical_indicator_publication"
        / str(body["source_date_end"] or "unknown")
        / digest[7:23]
        / "receipt.json"
    )
    encoded = (_canonical_json(payload) + "\n").encode("utf-8")
    _write_create_only(path, encoded)
    return {
        "status": "published",
        "schema_version": TECHNICAL_PUBLICATION_SCHEMA_VERSION,
        "receipt_path": str(path.resolve()),
        "receipt_sha256": _hash_bytes(encoded),
        "source_date_start": body["source_date_start"],
        "source_date_end": body["source_date_end"],
        "available_at": body["available_at"],
        "source_receipt_count": len(bound),
        "technical_output": technical_output,
        "historical_pit_eligible": False,
        "formal_source_contract_eligible": False,
    }


def _daily_price_receipts(output_root: Path) -> list[dict[str, object]]:
    root = output_root / "scheduled" / "daily_price_source_custody"
    items: list[dict[str, object]] = []
    if not root.is_dir():
        return items
    for path in sorted(root.glob("*/*/*/receipt.json")):
        payload = _read_json(path)
        digest = _hash_file(path)
        if payload is None or digest is None:
            continue
        if payload.get("schema_version") != "official-daily-price-response-capture.v1":
            continue
        if payload.get("source_id") not in {
            "twse.mi_index.daily_price",
            "tpex.daily_close_quotes",
        }:
            continue
        if not _verified_content_hash(payload, "content_sha256"):
            continue
        raw_path_value = payload.get("raw_response_path")
        raw_path = (
            Path(str(raw_path_value)).expanduser()
            if raw_path_value and Path(str(raw_path_value)).is_absolute()
            else path.parent / str(raw_path_value or "raw_response.bin")
        ).resolve()
        if not raw_path.is_relative_to(path.parent.resolve()):
            continue
        if not raw_path.is_file() or raw_path.is_symlink():
            continue
        if _hash_file(raw_path) != payload.get("raw_response_sha256"):
            continue
        coverage = _response_symbol_coverage(raw_path)
        items.append(
            {
                "receipt_path": str(path.resolve()),
                "receipt_sha256": digest,
                "source_id": payload.get("source_id"),
                "source_authority": payload.get("source_authority"),
                "source_date": _date_text(payload.get("source_date")),
                "available_at": payload.get("available_at"),
                "raw_response_sha256": payload.get("raw_response_sha256"),
                "source_columns": payload.get("source_columns", []),
                "row_count": payload.get("row_count"),
                "historical_pit_status": payload.get("historical_pit_status"),
                "covered_symbols": coverage["symbols"],
                "symbol_coverage_status": coverage["status"],
            }
        )
    return items


def _response_symbol_coverage(path: Path) -> dict[str, object]:
    """Extract symbol coverage from an official raw response without guessing."""

    try:
        payload = json.loads(path.read_bytes().decode("utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"status": "unparseable", "symbols": []}
    symbols: set[str] = set()
    tables = payload.get("tables") if isinstance(payload, Mapping) else None
    if isinstance(tables, list):
        for table in tables:
            if not isinstance(table, Mapping):
                continue
            fields = table.get("fields")
            rows = table.get("data")
            if not isinstance(fields, list) or not isinstance(rows, list):
                continue
            normalized_fields = [str(field).strip() for field in fields]
            symbol_indexes = [
                index
                for index, field in enumerate(normalized_fields)
                if field in {"證券代號", "代號", "股票代號", "code", "Code"}
            ]
            if not symbol_indexes:
                continue
            index = symbol_indexes[0]
            for row in rows:
                if isinstance(row, (list, tuple)) and index < len(row):
                    value = str(row[index]).strip()
                    if value and value not in {"--", "-"}:
                        symbols.add(value)
    msg_array = payload.get("msgArray") if isinstance(payload, Mapping) else None
    if isinstance(msg_array, list):
        for row in msg_array:
            if isinstance(row, Mapping):
                value = str(row.get("c") or row.get("code") or "").strip()
                if value:
                    symbols.add(value.split(".", 1)[0])
    if tables is None and msg_array is None:
        return {"status": "unsupported_shape", "symbols": sorted(symbols)}
    return {
        "status": "parsed" if symbols else "parsed_empty",
        "symbols": sorted(symbols),
    }


def _technical_receipt_lineage_verified(
    payload: Mapping[str, Any] | None,
    valid_daily_receipts: Sequence[Mapping[str, object]],
) -> bool:
    """Verify that the technical publication still points at current custody."""

    if not isinstance(payload, Mapping):
        return False
    source_receipts = payload.get("source_receipts")
    if not isinstance(source_receipts, list) or not source_receipts:
        return False
    by_path = {
        str(item.get("receipt_path")): item
        for item in valid_daily_receipts
        if item.get("receipt_path")
    }
    for reference in source_receipts:
        if not isinstance(reference, Mapping):
            return False
        reference_path = str(reference.get("receipt_path") or "")
        current = by_path.get(reference_path)
        if current is None:
            return False
        if reference.get("receipt_sha256") != current.get("receipt_sha256"):
            return False
        if reference.get("raw_response_sha256") != current.get("raw_response_sha256"):
            return False
    return True


def _path_is_within_any_root(path: Path, roots: Sequence[Path]) -> bool:
    resolved = path.resolve()
    return any(
        resolved == root or resolved.is_relative_to(root)
        for root in roots
    )


def reuse_verified_technical_computation_receipt(
    *,
    authorized_output_roots: Sequence[str | Path],
    source_db: str | Path,
    source_date_start: str,
    source_date_end: str,
    availability_cutoff_at: datetime | str,
    max_receipts: int = 64,
) -> dict[str, object]:
    """Find and revalidate a same-window technical computation witness.

    A currentity skip may reuse a prior computation only when the receipt is
    under an explicitly authorized output root and every input/output hash can
    still be re-read from the current formal database and immutable daily-price
    custody.  The scan is bounded to the requested end-date directory; it does
    not search arbitrary history or guess a root from a receipt path.
    """

    start = _date_text(source_date_start)
    end = _date_text(source_date_end)
    cutoff = _aware_datetime(availability_cutoff_at)
    database = Path(source_db).expanduser().resolve()
    roots = tuple(
        dict.fromkeys(
            Path(root).expanduser().resolve()
            for root in authorized_output_roots
        )
    )
    if not start or not end or cutoff is None:
        return {
            "status": "not_found",
            "reason": "technical_reuse_window_or_cutoff_invalid",
        }
    if not roots:
        return {
            "status": "not_found",
            "reason": "technical_reuse_authorized_roots_empty",
        }
    if max_receipts <= 0:
        return {
            "status": "not_found",
            "reason": "technical_reuse_receipt_bound_invalid",
        }

    technical_output_current = _technical_output_snapshot(
        database,
        source_date_start=start,
        source_date_end=end,
    )
    if technical_output_current.get("verified") is not True:
        return {
            "status": "not_found",
            "reason": "technical_reuse_current_output_unverified",
            "technical_output": technical_output_current,
        }

    candidate_paths: list[tuple[Path, Path]] = []
    for root in roots:
        date_root = root / "scheduled" / "technical_indicator_publication" / end
        if not date_root.is_dir():
            continue
        for path in date_root.glob("*/receipt.json"):
            if path.is_file() and not path.is_symlink():
                candidate_paths.append((path, root))
    candidate_paths.sort(
        key=lambda item: item[0].stat().st_mtime_ns,
        reverse=True,
    )
    candidate_paths = candidate_paths[:max_receipts]
    diagnostics: list[str] = []

    for publication_path, publication_root in candidate_paths:
        payload = _read_json(publication_path)
        publication_hash = _hash_file(publication_path)
        if payload is None or publication_hash is None:
            diagnostics.append("publication_unreadable")
            continue
        if payload.get("schema_version") != TECHNICAL_PUBLICATION_SCHEMA_VERSION:
            diagnostics.append("publication_schema_invalid")
            continue
        if not _verified_content_hash(payload, "content_sha256"):
            diagnostics.append("publication_content_hash_invalid")
            continue
        if payload.get("technical_step_status") != "passed":
            diagnostics.append("publication_step_not_passed")
            continue
        if (
            _date_text(payload.get("source_date_start")) != start
            or _date_text(payload.get("source_date_end")) != end
        ):
            diagnostics.append("publication_date_window_mismatch")
            continue
        available_at = _aware_datetime(payload.get("available_at"))
        if available_at is None or available_at > cutoff:
            diagnostics.append("publication_after_availability_cutoff")
            continue

        technical_output = payload.get("technical_output")
        if not isinstance(technical_output, Mapping):
            diagnostics.append("technical_output_missing")
            continue
        if not _verified_content_hash(technical_output, "content_sha256"):
            diagnostics.append("technical_output_content_hash_invalid")
            continue
        if technical_output.get("source_db") != str(database):
            diagnostics.append("technical_output_source_db_mismatch")
            continue
        if (
            technical_output.get("content_sha256")
            != technical_output_current.get("content_sha256")
            or technical_output.get("rows_sha256")
            != technical_output_current.get("rows_sha256")
            or technical_output.get("row_count")
            != technical_output_current.get("row_count")
        ):
            diagnostics.append("technical_output_current_value_mismatch")
            continue

        references = payload.get("source_receipts")
        if not isinstance(references, list) or not references:
            diagnostics.append("daily_source_receipts_missing")
            continue
        source_dates: list[str] = []
        invalid_reference = False
        for reference in references:
            if not isinstance(reference, Mapping):
                invalid_reference = True
                diagnostics.append("daily_source_reference_invalid")
                break
            raw_receipt_path = Path(str(reference.get("receipt_path") or "")).expanduser()
            if not raw_receipt_path.is_absolute():
                raw_receipt_path = publication_path.parent / raw_receipt_path
            if (
                not raw_receipt_path
                or raw_receipt_path.is_symlink()
                or not raw_receipt_path.is_file()
            ):
                invalid_reference = True
                diagnostics.append("daily_source_receipt_missing")
                break
            receipt_path = raw_receipt_path.resolve()
            if not _path_is_within_any_root(receipt_path, roots):
                invalid_reference = True
                diagnostics.append("daily_source_receipt_root_unauthorized")
                break
            receipt_hash = _hash_file(receipt_path)
            receipt_payload = _read_json(receipt_path)
            if (
                receipt_hash is None
                or receipt_hash != reference.get("receipt_sha256")
                or receipt_payload is None
                or receipt_payload.get("schema_version")
                != "official-daily-price-response-capture.v1"
                or receipt_payload.get("source_id") not in {
                    "twse.mi_index.daily_price",
                    "tpex.daily_close_quotes",
                }
                or not _verified_content_hash(receipt_payload, "content_sha256")
            ):
                invalid_reference = True
                diagnostics.append("daily_source_receipt_hash_invalid")
                break
            source_date = _date_text(receipt_payload.get("source_date"))
            if not source_date or not start <= source_date <= end:
                invalid_reference = True
                diagnostics.append("daily_source_receipt_date_invalid")
                break
            source_available_at = _aware_datetime(receipt_payload.get("available_at"))
            if source_available_at is None or source_available_at > cutoff or source_available_at > available_at:
                invalid_reference = True
                diagnostics.append("daily_source_receipt_after_cutoff")
                break
            raw_response_value = reference.get("raw_response_path")
            raw_response_path = Path(str(raw_response_value or "")).expanduser()
            if not raw_response_path.is_absolute():
                raw_response_path = receipt_path.parent / raw_response_path
            if (
                raw_response_path.is_symlink()
                or not raw_response_path.is_file()
                or not raw_response_path.resolve().is_relative_to(receipt_path.parent)
                or _hash_file(raw_response_path) != reference.get("raw_response_sha256")
            ):
                invalid_reference = True
                diagnostics.append("daily_source_raw_response_hash_invalid")
                break
            source_dates.append(source_date)
        if invalid_reference:
            continue
        source_dates = sorted(set(source_dates))
        if not source_dates or source_dates[0] != start or source_dates[-1] != end:
            diagnostics.append("daily_source_receipt_window_incomplete")
            continue

        evidence = payload.get("technical_computation_evidence")
        if (
            payload.get("technical_computation_evidence_status") != "verified"
            or not isinstance(evidence, Mapping)
        ):
            diagnostics.append("technical_computation_witness_missing")
            continue
        evidence_ok, evidence_reason, verified_evidence = (
            _verify_technical_computation_evidence(
                evidence,
                technical_output=technical_output_current,
                source_dates=source_dates,
                completed_at=str(payload.get("available_at") or ""),
            )
        )
        if not evidence_ok or verified_evidence is None:
            diagnostics.append(evidence_reason)
            continue
        input_snapshot = verified_evidence.get("input_snapshot")
        if not isinstance(input_snapshot, Mapping):
            diagnostics.append("technical_input_snapshot_missing")
            continue
        current_input = _technical_input_snapshot(
            database,
            source_date_start=_date_text(input_snapshot.get("requested_date_start")),
            source_date_end=_date_text(input_snapshot.get("requested_date_end")),
        )
        if any(
            current_input.get(field) != input_snapshot.get(field)
            for field in ("source_db", "content_sha256", "rows_sha256", "row_count")
        ):
            diagnostics.append("technical_input_current_value_mismatch")
            continue
        return {
            "status": "reused",
            "technical_computation": dict(verified_evidence),
            "source_publication_receipt": {
                "path": str(publication_path.resolve()),
                "sha256": publication_hash,
                "available_at": payload.get("available_at"),
                "source_root": str(publication_root),
            },
            "source_date_start": start,
            "source_date_end": end,
        }

    return {
        "status": "not_found",
        "reason": "verified_technical_computation_receipt_not_reusable",
        "checked_receipt_count": len(candidate_paths),
        "diagnostics": list(dict.fromkeys(diagnostics))[:8],
    }


def _event_publication_status(
    output_root: Path,
    *,
    availability_cutoff_at: datetime | None = None,
) -> dict[str, object]:
    status_path = output_root / "scheduled" / "official_market_events" / "latest_status.json"
    status = _read_json(status_path)
    if status is None:
        return {"status": "missing", "status_path": str(status_path)}
    publication_root = (output_root / "release_v4" / "official_market_events").resolve()
    refresh_failed = status.get("status") != "published"
    binding: Mapping[str, Any] = status
    pointer_path: Path | None = None
    pointer: Mapping[str, Any] | None = None
    if refresh_failed:
        # A failed bounded refresh must not erase a verified prospective
        # publication.  Prefer the prospective pointer, then the formal
        # pointer, and validate the child files before exposing last-good
        # custody to a downstream lane.
        for candidate in (
            publication_root / "prospective_latest_manifest.json",
            publication_root / "latest_manifest.json",
        ):
            candidate_payload = _read_json(candidate)
            if isinstance(candidate_payload, Mapping) and candidate_payload.get("manifest_path"):
                pointer_path = candidate
                pointer = candidate_payload
                binding = candidate_payload
                break
        if pointer is None:
            return {
                "status": str(status.get("status") or "unknown"),
                "status_path": str(status_path),
                "reason": status.get("message") or status.get("failure_class"),
                "formal_publication_preserved": status.get("formal_publication_preserved"),
                "formal_publication_verified": False,
                "prospective_publication_verified": False,
                "refresh_failure_preserved": True,
            }
    manifest_path = Path(str(binding.get("manifest_path") or ""))
    if not manifest_path.is_absolute():
        manifest_path = (publication_root / manifest_path).resolve()
    else:
        manifest_path = manifest_path.resolve()
    try:
        manifest_is_safe = manifest_path.is_relative_to(publication_root)
    except (OSError, ValueError):
        manifest_is_safe = False
    if not manifest_is_safe:
        return {
            "status": "invalid",
            "status_path": str(status_path),
            "reason": "manifest_path_escapes_publication_root",
            "formal_publication_verified": False,
            "prospective_publication_verified": False,
            "refresh_failure_preserved": refresh_failed,
        }
    manifest_hash = _hash_file(manifest_path)
    manifest = _read_json(manifest_path)
    logical_hash_ok = False
    logical_pointer_binding_ok = False
    canonical_ok = False
    canonical_pointer_binding_ok = False
    raw_index_ok = False
    raw_response_hashes: set[str] = set()
    if manifest is not None:
        declared_logical_hash = manifest.get("manifest_hash")
        logical_body = {key: value for key, value in manifest.items() if key != "manifest_hash"}
        logical_hash_ok = declared_logical_hash == _hash_payload(logical_body)
        logical_pointer_binding_ok = declared_logical_hash == binding.get("manifest_hash")
        raw_index = manifest.get("raw_index")
        canonical = manifest.get("canonical_events")
        if isinstance(raw_index, Mapping):
            raw_index_path = (manifest_path.parent / str(raw_index.get("path") or "")).resolve()
            raw_index_hash = _hash_file(raw_index_path)
            raw_index_ok = bool(
                raw_index_path.is_relative_to(manifest_path.parent.resolve())
                and raw_index_hash
                and raw_index_hash == raw_index.get("file_hash")
            )
            if raw_index_ok:
                try:
                    for line in raw_index_path.read_text(encoding="utf-8").splitlines():
                        entry = json.loads(line)
                        if isinstance(entry, Mapping) and entry.get("response_sha256"):
                            response_path = (manifest_path.parent / str(entry.get("response_path") or "")).resolve()
                            if (
                                response_path.is_relative_to(manifest_path.parent.resolve())
                                and _hash_file(response_path) == entry.get("response_sha256")
                            ):
                                raw_response_hashes.add(str(entry["response_sha256"]))
                            else:
                                raw_index_ok = False
                                break
                except (OSError, UnicodeError, json.JSONDecodeError):
                    raw_index_ok = False
        if isinstance(canonical, Mapping):
            canonical_path = (manifest_path.parent / str(canonical.get("path") or "")).resolve()
            canonical_ok = bool(
                canonical_path.is_relative_to(manifest_path.parent.resolve())
                and _hash_file(canonical_path) == canonical.get("file_hash")
            )
            canonical_pointer_binding_ok = canonical.get("file_hash") == binding.get("canonical_events_hash")
            if canonical_ok:
                try:
                    for line in canonical_path.read_text(encoding="utf-8").splitlines():
                        event = json.loads(line)
                        if not isinstance(event, Mapping):
                            canonical_ok = False
                            break
                        raw_hash = str(event.get("raw_response_sha256") or "")
                        if raw_hash and raw_hash not in raw_response_hashes:
                            canonical_ok = False
                            break
                except (OSError, UnicodeError, json.JSONDecodeError):
                    canonical_ok = False
    verified = bool(
        manifest_hash
        and manifest_hash == binding.get("manifest_file_hash")
        and logical_hash_ok
        and logical_pointer_binding_ok
        and canonical_ok
        and canonical_pointer_binding_ok
        and raw_index_ok
    )
    publication_status = str(manifest.get("status") or "") if manifest else ""
    formal_publication_verified = verified and (
        publication_status == "formal_source_publication"
    )
    generated_at = manifest.get("generated_at") if isinstance(manifest, Mapping) else None
    last_good_age_seconds: float | None = None
    freshness_status = "unknown"
    if generated_at:
        try:
            generated_dt = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
            if generated_dt.tzinfo is None:
                generated_dt = generated_dt.replace(tzinfo=timezone.utc)
            last_good_age_seconds = max(
                0.0,
                (datetime.now(timezone.utc) - generated_dt.astimezone(timezone.utc)).total_seconds(),
            )
            freshness_status = "within_bounded_retry_window" if last_good_age_seconds <= 3 * 86400 else "stale"
        except (TypeError, ValueError, OverflowError):
            freshness_status = "invalid_timestamp"
    publication_available_at = generated_at
    prospective_availability_ok = _availability_before_or_at(
        publication_available_at,
        availability_cutoff_at,
    )
    prospective_freshness_ok = not refresh_failed or freshness_status == "within_bounded_retry_window"
    prospective_publication_verified = verified and prospective_freshness_ok and prospective_availability_ok and (
        publication_status == "prospective_source_publication"
    )
    return {
        "status": "published" if verified and not refresh_failed else "published_last_known_good" if verified else "invalid",
        "status_path": str(status_path),
        "pointer_path": str(pointer_path) if pointer_path is not None else None,
        "manifest_path": str(manifest_path),
        "manifest_file_sha256": manifest_hash,
        "manifest_file_hash_declared": binding.get("manifest_file_hash"),
        "manifest_hash": binding.get("manifest_hash"),
        "canonical_events_hash": binding.get("canonical_events_hash"),
        "manifest_logical_hash_verified": logical_hash_ok,
        "manifest_pointer_binding_verified": logical_pointer_binding_ok,
        "canonical_events_verified": canonical_ok,
        "canonical_events_pointer_binding_verified": canonical_pointer_binding_ok,
        "raw_index_and_responses_verified": raw_index_ok,
        "publication_scope": manifest.get("publication_scope") if manifest else None,
        "formal_publication_verified": formal_publication_verified,
        "prospective_publication_verified": prospective_publication_verified,
        "source_publication_generated_at": generated_at,
        "source_publication_available_at": publication_available_at,
        "availability_cutoff_at": (
            availability_cutoff_at.isoformat() if availability_cutoff_at is not None else None
        ),
        "availability_before_cutoff_verified": prospective_availability_ok,
        "last_good_age_seconds": last_good_age_seconds,
        "last_good_freshness_status": freshness_status,
        "refresh_failure_preserved": refresh_failed,
        "refresh_status": status if refresh_failed else None,
        "refresh_failure_reason": (
            status.get("message") or status.get("failure_class")
            if refresh_failed
            else None
        ),
    }


def _corporate_adjustment_table_status(source_db: Path) -> dict[str, object]:
    if not source_db.is_file():
        return {"status": "missing_database", "verified": False}
    try:
        with sqlite3.connect(source_db.as_uri() + "?mode=ro", uri=True) as connection:
            connection.execute("PRAGMA query_only=ON")
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if "corporate_action_adjustments" not in tables:
                return {
                    "status": "missing_table",
                    "table": "corporate_action_adjustments",
                    "verified": False,
                }
            count = int(connection.execute("SELECT COUNT(*) FROM corporate_action_adjustments").fetchone()[0])
            actual_columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(corporate_action_adjustments)")
            }
            required_columns = {
                "symbol",
                "event_date",
                "available_at",
                "effective_from",
                "adjustment_factor",
            }
            missing_columns = sorted(required_columns - actual_columns)
            return {
                "status": "present" if count else "empty",
                "table": "corporate_action_adjustments",
                "row_count": count,
                "columns": sorted(actual_columns),
                "missing_columns": missing_columns,
                "inventory_present": count > 0 and not missing_columns,
                "verified": False,
                "reason": (
                    "inventory_only_formal_source_contract_not_validated"
                    if count > 0 and not missing_columns
                    else "corporate_adjustment_inventory_incomplete"
                ),
            }
    except (OSError, sqlite3.Error, TypeError, ValueError):
        return {"status": "unreadable", "verified": False}


def _corporate_adjustment_custody_status(
    output_root: Path,
    *,
    event_status: Mapping[str, object],
    decision_date: date,
    symbols: Sequence[str],
    availability_cutoff_at: datetime | None = None,
) -> dict[str, object]:
    """Verify the append-only official result-factor sidecar, if present."""

    root = output_root / "release_v4" / "corporate_action_adjustments"
    pointer_path = root / "latest_manifest.json"
    if not pointer_path.is_file():
        return {
            "status": "missing",
            "verified": False,
            "prospective_verified": False,
            "pointer_path": str(pointer_path),
    }
    try:
        pointer = _read_json(pointer_path)
        if pointer is None:
            raise ValueError("adjustment_pointer_invalid_json")
        manifest_path = (root / str(pointer.get("manifest_path") or "")).resolve()
        if not manifest_path.is_relative_to(root.resolve()):
            raise ValueError("adjustment_manifest_path_escapes_root")
        manifest_file_hash = _hash_file(manifest_path)
        if not manifest_file_hash or manifest_file_hash != pointer.get("manifest_file_hash"):
            raise ValueError("adjustment_manifest_file_hash_mismatch")
        manifest = _read_json(manifest_path)
        if manifest is None:
            raise ValueError("adjustment_manifest_invalid_json")
        manifest_hash = str(manifest.get("manifest_hash") or "")
        manifest_body = {key: value for key, value in manifest.items() if key != "manifest_hash"}
        if not manifest_hash or _hash_payload(manifest_body) != manifest_hash or pointer.get("manifest_hash") != manifest_hash:
            raise ValueError("adjustment_manifest_logical_hash_mismatch")
        adjustments = manifest.get("adjustments")
        coverage = manifest.get("coverage")
        if not isinstance(adjustments, Mapping) or not isinstance(coverage, Mapping):
            raise ValueError("adjustment_manifest_sections_missing")
        adjustments_path = (manifest_path.parent / str(adjustments.get("path") or "")).resolve()
        coverage_path = (manifest_path.parent / str(coverage.get("path") or "")).resolve()
        if not adjustments_path.is_relative_to(manifest_path.parent) or not coverage_path.is_relative_to(manifest_path.parent):
            raise ValueError("adjustment_manifest_child_path_escapes")
        if _hash_file(adjustments_path) != adjustments.get("file_hash"):
            raise ValueError("adjustment_rows_hash_mismatch")
        if _hash_file(coverage_path) != coverage.get("file_hash"):
            raise ValueError("adjustment_coverage_hash_mismatch")
        coverage_payload = _read_json(coverage_path)
        if coverage_payload is None:
            raise ValueError("adjustment_coverage_invalid_json")
        source_publication_declared = manifest.get("source_publication")
        if not isinstance(source_publication_declared, Mapping):
            raise ValueError("adjustment_source_publication_missing")
        source_manifest_hash_declared = source_publication_declared.get("manifest_hash")
        rows: list[Mapping[str, object]] = []
        for line in adjustments_path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if not isinstance(row, Mapping):
                raise ValueError("adjustment_row_not_object")
            if not _verified_content_hash(row, "content_sha256"):
                raise ValueError("adjustment_row_content_hash_mismatch")
            if row.get("source_manifest_hash") != source_manifest_hash_declared:
                raise ValueError("adjustment_row_source_manifest_mismatch")
            if row.get("historical_pit_eligible") is not False or row.get("formal_source_contract_eligible") is not False:
                raise ValueError("adjustment_row_pit_or_formal_flag_invalid")
            rows.append(row)
        if adjustments.get("row_count") != len(rows):
            raise ValueError("adjustment_row_count_mismatch")
        if coverage_payload.get("result_event_count") != len(rows):
            raise ValueError("adjustment_coverage_row_count_mismatch")
        if coverage_payload.get("factor_available_count") != sum(
            row.get("adjustment_factor") not in (None, "") for row in rows
        ):
            raise ValueError("adjustment_factor_available_count_mismatch")
        if coverage_payload.get("factor_missing_count") != sum(
            row.get("adjustment_factor") in (None, "") for row in rows
        ):
            raise ValueError("adjustment_factor_missing_count_mismatch")
        requested = {str(symbol).strip() for symbol in symbols if str(symbol).strip()}
        relevant = [row for row in rows if str(row.get("symbol") or "").strip() in requested]
        missing_factor_symbols = sorted(
            {
                str(row.get("symbol") or "").strip()
                for row in relevant
                if row.get("adjustment_factor") in (None, "")
            }
        )
        future_rows = sum(
            1
            for row in relevant
            if (
                not _availability_before_or_at(
                    row.get("available_at"),
                    availability_cutoff_at,
                )
                if availability_cutoff_at is not None
                else (_date_text(row.get("available_at")) or "9999-12-31") > decision_date.isoformat()
            )
        )
        manifest_available_at = manifest.get("created_at") or pointer.get("updated_at")
        source_publication = manifest_body.get("source_publication")
        source_publication = source_publication if isinstance(source_publication, Mapping) else {}
        event_manifest_hash = str(event_status.get("manifest_hash") or "")
        event_manifest_file_hash = str(event_status.get("manifest_file_sha256") or "")
        source_manifest_matches = bool(
            event_manifest_hash
            and source_publication.get("manifest_hash") == event_manifest_hash
        )
        source_manifest_file_matches = bool(
            event_manifest_file_hash
            and source_publication.get("manifest_file_hash") == event_manifest_file_hash
        )
        blockers: list[str] = []
        event_publication_verified = (
            event_status.get("formal_publication_verified") is True
            or event_status.get("prospective_publication_verified") is True
        )
        if not event_publication_verified:
            blockers.append("official_event_publication_unverified")
        if not source_manifest_matches:
            blockers.append("adjustment_source_manifest_not_bound_to_verified_event_publication")
        if not source_manifest_file_matches:
            blockers.append("adjustment_source_manifest_file_not_bound_to_verified_event_publication")
        if missing_factor_symbols:
            blockers.append("adjustment_factor_missing:" + ",".join(missing_factor_symbols))
        if future_rows:
            blockers.append("adjustment_available_after_decision:" + str(future_rows))
        if availability_cutoff_at is not None and not _availability_before_or_at(
            manifest_available_at,
            availability_cutoff_at,
        ):
            blockers.append("adjustment_manifest_available_after_capture_cutoff")
        prospective_verified = not blockers
        return {
            "status": "verified" if prospective_verified else "partial",
            "verified": False,
            "prospective_verified": prospective_verified,
            "manifest_path": str(manifest_path),
            "manifest_file_hash": manifest_file_hash,
            "manifest_hash": manifest_hash,
            "available_at": manifest_available_at,
            "availability_cutoff_at": (
                availability_cutoff_at.isoformat() if availability_cutoff_at is not None else None
            ),
            "availability_before_cutoff_verified": _availability_before_or_at(
                manifest_available_at,
                availability_cutoff_at,
            ),
            "source_manifest_hash": source_publication.get("manifest_hash"),
            "source_manifest_file_hash": source_publication.get("manifest_file_hash"),
            "source_manifest_binding_verified": source_manifest_matches and source_manifest_file_matches,
            "row_count": len(rows),
            "requested_symbol_row_count": len(relevant),
            "missing_factor_symbols": missing_factor_symbols,
            "future_rows": future_rows,
            "blockers": blockers,
            "formal_source_contract_eligible": False,
        }
    except (OSError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        return {
            "status": "invalid",
            "verified": False,
            "prospective_verified": False,
            "reason": f"adjustment_custody_validation_failed:{type(exc).__name__}",
            "error": str(exc),
            "formal_source_contract_eligible": False,
        }


def _cost_lanes(*, source_db: Path, output_root: Path, estimated_cost_bp: int) -> dict[str, object]:
    observed_rows = 0
    ready_rows = 0
    unverified_lineage_rows = 0
    simulated_rows = 0
    if source_db.is_file():
        try:
            with sqlite3.connect(source_db.as_uri() + "?mode=ro", uri=True) as connection:
                connection.execute("PRAGMA query_only=ON")
                tables = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                if {"evidence_events", "evidence_outcomes"}.issubset(tables):
                    columns = {
                        str(row[1])
                        for row in connection.execute("PRAGMA table_info(evidence_outcomes)")
                    }
                    metadata_column = "metadata_json" if "metadata_json" in columns else None
                    select_metadata = ", o.metadata_json" if metadata_column else ""
                    rows = connection.execute(
                        """
                        SELECT o.liquidity_cost_bp, o.outcome_status"""
                        + select_metadata
                        + """
                        FROM evidence_outcomes AS o
                        WHERE o.liquidity_cost_bp IS NOT NULL
                        """
                    ).fetchall()
                    for row in rows:
                        if str(row[1]).lower() != "ready":
                            continue
                        ready_rows += 1
                        # Do not infer execution lineage from a substring.  A
                        # value such as {"actual_fill": false}, or prose such
                        # as "no broker_execution", is explicitly non-proof.
                        # The broker-fill verifier is not implemented in this
                        # lane yet, so even a structured claim remains
                        # unverified until it can be checked against a ledger.
                        metadata_payload: Mapping[str, Any] = {}
                        if metadata_column:
                            try:
                                decoded = json.loads(str(row[2] or "{}"))
                            except (TypeError, ValueError, json.JSONDecodeError):
                                decoded = {}
                            if isinstance(decoded, Mapping):
                                metadata_payload = decoded
                        structured_lineage = metadata_payload.get("actual_fill_lineage")
                        if structured_lineage is not None:
                            unverified_lineage_rows += 1
                        # ``observed_rows`` intentionally remains zero until
                        # a real broker ledger verifier is available.
        except (OSError, sqlite3.Error, TypeError, ValueError):
            pass
    ledger = output_root / "paper_execution_eod_replay" / "paper_trade_ledger.sqlite"
    if ledger.is_file():
        try:
            with sqlite3.connect(ledger.as_uri() + "?mode=ro", uri=True) as connection:
                connection.execute("PRAGMA query_only=ON")
                simulated_rows = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM paper_trade_ledger WHERE COALESCE(research_only, 1) = 1"
                    ).fetchone()[0]
                )
        except (OSError, sqlite3.Error, TypeError, ValueError):
            simulated_rows = 0
    return {
        "observed": {
            "ready_rows": ready_rows,
            "actual_fill_lineage_rows": observed_rows,
            "unverified_structured_lineage_rows": unverified_lineage_rows,
            "eligible": False,
            "verified": False,
            "reason": "broker_actual_fill_lineage_verifier_not_implemented",
            "source": "evidence_outcomes.liquidity_cost_bp;broker_ledger_verification_pending",
        },
        "estimated": {
            "cost_bp": int(estimated_cost_bp),
            "eligible_for_estimate_only": True,
            "source": "fixed_policy_parameter",
        },
        "simulated": {
            "paper_ledger_research_only_rows": simulated_rows,
            "eligible_as_observed": False,
            "source": "paper_trade_ledger.research_only",
        },
    }


def _formal_source_contract_status(
    *,
    source_db: Path,
    decision_date: date,
    symbols: Sequence[str],
    history_start_date: str,
    replay_start_date: str,
    replay_end_date: str,
) -> dict[str, object]:
    """Reuse the strict replay validator as the authority for formal status."""

    try:
        from ml_module.recommendation_historical_replay import (
            RecommendationHistoricalReplayConfig,
            _read_source_contract,
        )

        config = RecommendationHistoricalReplayConfig(
            history_start_date=history_start_date,
            replay_start_date=replay_start_date,
            replay_end_date=replay_end_date,
            symbols=tuple(symbols),
            fixed_round_trip_cost_bp=0,
            max_decision_dates=1,
        )
        contract = _read_source_contract(source_db, config=config)
        technical = dict(contract.get("technical") or {})
        corporate = dict(contract.get("corporate_actions") or {})
        return {
            "status": "validated" if technical.get("verified") or corporate.get("verified") else "blocked",
            "technical": technical,
            "corporate_actions": corporate,
            "summary": contract.get("summary"),
            "fingerprint": contract.get("fingerprint"),
            "decision_date": decision_date.isoformat(),
            "authority": "ml_module.recommendation_historical_replay._read_source_contract",
        }
    except (ImportError, OSError, RuntimeError, TypeError, ValueError, sqlite3.Error) as exc:
        return {
            "status": "blocked",
            "technical": {"verified": False, "reason": "formal_validator_unavailable"},
            "corporate_actions": {"verified": False, "reason": "formal_validator_unavailable"},
            "reason": f"formal_source_contract_validation_failed:{type(exc).__name__}",
            "authority": "ml_module.recommendation_historical_replay._read_source_contract",
        }


def inspect_source_contract(
    *,
    data_root: str | Path,
    output_root: str | Path,
    source_db: str | Path,
    decision_date: date,
    symbols: Sequence[str],
    estimated_cost_bp: int = 50,
    history_start_date: str = "2014-01-01",
    replay_start_date: str | None = None,
    replay_end_date: str | None = None,
    availability_cutoff_at: str | datetime | None = None,
    authorized_output_roots: Sequence[str | Path] | None = None,
) -> dict[str, object]:
    """Inspect real artifacts and return lane-specific readiness."""

    source_output = Path(output_root).expanduser().resolve()
    technical_output_roots = tuple(
        dict.fromkeys(
            Path(root).expanduser().resolve()
            for root in (
                authorized_output_roots
                if authorized_output_roots is not None
                else (source_output, Path(data_root).expanduser() / "output")
            )
        )
    )
    database = Path(source_db).expanduser().resolve()
    replay_start = str(replay_start_date or history_start_date)[:10]
    replay_end = str(replay_end_date or decision_date.isoformat())[:10]
    availability_cutoff = _aware_datetime(
        availability_cutoff_at or datetime.now(timezone.utc)
    )
    availability_cutoff_text = (
        availability_cutoff.isoformat() if availability_cutoff is not None else None
    )
    daily_receipts = [
        item
        for root in technical_output_roots
        for item in _daily_price_receipts(root)
    ]
    date_text = decision_date.isoformat()
    late_daily_receipts = [
        item
        for item in daily_receipts
        if item.get("available_at")
        and (
            not _availability_before_or_at(item.get("available_at"), availability_cutoff)
            or (_date_text(item.get("source_date")) or "9999-12-31") > date_text
        )
    ]
    relevant_receipts = [
        item for item in daily_receipts
        if item.get("source_date")
        and str(item["source_date"]) <= date_text
        and item.get("available_at")
        and _availability_before_or_at(item.get("available_at"), availability_cutoff)
    ]
    technical_receipts: list[dict[str, Any]] = []
    for technical_root in (
        root / "scheduled" / "technical_indicator_publication"
        for root in technical_output_roots
    ):
        if not technical_root.is_dir():
            continue
        technical_receipts.extend(
            {
                "path": str(path.resolve()),
                "sha256": _hash_file(path),
                "payload": _read_json(path),
            }
            for path in technical_root.glob("**/receipt.json")
            if path.is_file()
        )
    technical_receipts = [
        item
        for item in technical_receipts
        if item["payload"] is not None
        and _verified_content_hash(item["payload"], "content_sha256")
        and (_date_text(item["payload"].get("source_date_end")) or "9999-12-31") <= date_text
        and _availability_before_or_at(item["payload"].get("available_at"), availability_cutoff)
    ]
    technical_latest = max(
        technical_receipts,
        key=lambda item: str(item["payload"].get("available_at") or ""),
        default=None,
    )
    event_status = _event_publication_status(
        source_output,
        availability_cutoff_at=availability_cutoff,
    )
    adjustment_custody = _corporate_adjustment_custody_status(
        source_output,
        event_status=event_status,
        decision_date=decision_date,
        symbols=symbols,
        availability_cutoff_at=availability_cutoff,
    )
    corporate_table = _corporate_adjustment_table_status(database)
    formal_contract = _formal_source_contract_status(
        source_db=database,
        decision_date=decision_date,
        symbols=symbols,
        history_start_date=history_start_date,
        replay_start_date=replay_start,
        replay_end_date=replay_end,
    )
    cost = _cost_lanes(
        source_db=database,
        output_root=source_output,
        estimated_cost_bp=estimated_cost_bp,
    )
    source_dates = sorted(
        str(item["source_date"])
        for item in relevant_receipts
        if item.get("source_date")
    )
    latest_technical_payload = technical_latest["payload"] if technical_latest is not None else None
    technical_output = (
        latest_technical_payload.get("technical_output")
        if isinstance(latest_technical_payload, Mapping)
        else None
    )
    technical_output_is_mapping = isinstance(technical_output, Mapping)
    technical_output_mapping: Mapping[str, Any] = (
        technical_output if isinstance(technical_output, Mapping) else {}
    )
    technical_covered_symbols = (
        technical_output_mapping.get("covered_symbols")
        if technical_output_is_mapping
        else None
    )
    technical_output_symbols = (
        {str(item) for item in technical_covered_symbols if str(item).strip()}
        if isinstance(technical_covered_symbols, (list, tuple, set))
        else set()
    )
    technical_output_hash_verified = (
        technical_output_is_mapping
        and _verified_content_hash(technical_output_mapping, "content_sha256")
        and isinstance(technical_output_mapping.get("rows_sha256"), str)
    )
    technical_output_current = (
        _technical_output_snapshot(
            database,
            source_date_start=(
                latest_technical_payload.get("source_date_start")
                if isinstance(latest_technical_payload, Mapping)
                else None
            ),
            source_date_end=(
                latest_technical_payload.get("source_date_end")
                if isinstance(latest_technical_payload, Mapping)
                else None
            ),
        )
        if isinstance(latest_technical_payload, Mapping)
        and technical_output_is_mapping
        else {"verified": False, "reason": "technical_publication_missing"}
    )
    technical_output_value_binding_verified = bool(
        technical_output_hash_verified
        and technical_output_current.get("verified") is True
        and technical_output_current.get("source_db") == str(database)
        and technical_output_current.get("content_sha256") == technical_output_mapping.get("content_sha256")
        and technical_output_current.get("rows_sha256") == technical_output_mapping.get("rows_sha256")
    )
    prospective_feature_snapshot = _prospective_feature_snapshot(
        source_db=database,
        decision_date=date_text,
        history_start_date=history_start_date,
        symbols=symbols,
        captured_at=availability_cutoff_text,
    )
    prospective_feature_snapshot_verified = (
        prospective_feature_snapshot.get("verified") is True
        and _verified_content_hash(prospective_feature_snapshot, "content_sha256")
        and isinstance(prospective_feature_snapshot.get("rows_sha256"), str)
    )
    technical_receipt_lineage_verified = _technical_receipt_lineage_verified(
        latest_technical_payload,
        relevant_receipts,
    )
    requested_symbols = {str(symbol).strip() for symbol in symbols if str(symbol).strip()}
    missing_technical_symbols = sorted(requested_symbols - technical_output_symbols)
    latest_source_date = (
        _date_text(latest_technical_payload.get("source_date_end"))
        if isinstance(latest_technical_payload, Mapping)
        else None
    )
    latest_receipts = [
        item
        for item in relevant_receipts
        if item.get("source_date") == latest_source_date
    ] if latest_source_date else []
    source_covered_symbols: set[str] = set()
    for item in latest_receipts:
        covered_symbols = item.get("covered_symbols")
        if isinstance(covered_symbols, (list, tuple, set)):
            source_covered_symbols.update(str(symbol) for symbol in covered_symbols)
    missing_source_symbols = sorted(requested_symbols - source_covered_symbols)
    technical_prospective = bool(
        relevant_receipts
        and technical_latest is not None
        and technical_latest["payload"].get("publication_time_verified") is True
        and isinstance(technical_output, Mapping)
        and technical_output.get("verified") is True
        and technical_output_hash_verified
        and technical_output_value_binding_verified
        and technical_receipt_lineage_verified
        and not missing_technical_symbols
        and not missing_source_symbols
        and prospective_feature_snapshot_verified
    )
    technical_formal_value = formal_contract.get("technical")
    technical_formal = (
        dict(technical_formal_value)
        if isinstance(technical_formal_value, Mapping)
        else {}
    )
    formal_corporate_value = formal_contract.get("corporate_actions")
    formal_corporate = (
        formal_corporate_value
        if isinstance(formal_corporate_value, Mapping)
        else {}
    )
    technical_blockers: list[str] = []
    if not technical_prospective:
        technical_blockers.append("prospective_receipt_or_symbol_coverage_incomplete")
    if missing_technical_symbols:
        technical_blockers.append("technical_output_symbol_coverage_missing:" + ",".join(missing_technical_symbols))
    if missing_source_symbols:
        technical_blockers.append("daily_source_symbol_coverage_missing:" + ",".join(missing_source_symbols))
    if not technical_output_hash_verified:
        technical_blockers.append("technical_output_content_hash_unverified")
    if not technical_output_value_binding_verified:
        technical_blockers.append("technical_output_value_binding_unverified")
    if not technical_receipt_lineage_verified:
        technical_blockers.append("technical_source_receipt_lineage_unverified")
    if not prospective_feature_snapshot_verified:
        technical_blockers.append(
            str(
                prospective_feature_snapshot.get("reason")
                or "prospective_feature_snapshot_unverified"
            )
        )
    if not technical_formal.get("verified"):
        technical_blockers.append("formal_technical_source_contract_unverified")
    technical = {
        "source_id": "twse.mi_index.daily_price+tpex.daily_close_quotes",
        "source_table": "technical_indicators",
        "source_dates": source_dates,
        "source_receipts": relevant_receipts,
        "publication_receipt": (
            {key: value for key, value in technical_latest.items() if key != "payload"}
            if technical_latest is not None
            else None
        ),
        "publication_available_at": (
            latest_technical_payload.get("available_at")
            if isinstance(latest_technical_payload, Mapping)
            else None
        ),
        "source_receipt_available_ats": [
            item.get("available_at")
            for item in relevant_receipts
            if item.get("available_at")
        ],
        "prospective_feature_snapshot": prospective_feature_snapshot,
        "publication_time_verified": technical_prospective,
        "prospective_available": technical_prospective,
        "historical_pit_eligible": False,
        "formal_source_contract": technical_formal,
        "verified": bool(technical_formal.get("verified")),
        "inventory": {
            "latest_receipt_source_date": latest_source_date,
            "requested_symbols": sorted(requested_symbols),
            "technical_output_symbols": sorted(technical_output_symbols),
            "daily_source_symbols": sorted(source_covered_symbols),
            "missing_technical_symbols": missing_technical_symbols,
            "missing_source_symbols": missing_source_symbols,
            "late_daily_source_receipt_count": len(late_daily_receipts),
            "technical_output_content_hash_verified": technical_output_hash_verified,
            "technical_output_value_binding_verified": technical_output_value_binding_verified,
            "technical_source_receipt_lineage_verified": technical_receipt_lineage_verified,
            "prospective_feature_snapshot_verified": prospective_feature_snapshot_verified,
        },
        "prospective_blockers": technical_blockers,
        "reason": (
            "formal_technical_source_contract_verified"
            if technical_formal.get("verified")
            else "prospective_inventory_only_or_formal_contract_missing"
        ),
        "source_columns": ["日期", "證券代號", "RSI", "MACD", "ADX"],
    }
    corporate = {
        "source_id": "official_market_event_publication",
        "source_table": "official_market_event_publication.canonical/events.jsonl",
        "event_publication": event_status,
        "adjustment_custody": adjustment_custody,
        "adjustment_table": corporate_table,
        "source_available": event_status.get("formal_publication_verified") is True,
        "adjustment_verified": bool(formal_corporate.get("verified")),
        "historical_pit_eligible": False,
        "formal_source_contract": formal_corporate,
        "verified": bool(
            formal_corporate.get("verified")
            and event_status.get("formal_publication_verified") is True
        ),
        "qualification_blockers": (
            []
            if formal_corporate.get("verified")
            and event_status.get("formal_publication_verified") is True
            else list(
                dict.fromkeys(
                    [
                        *([
                            "official_event_publication_unverified"
                            ] if event_status.get("formal_publication_verified") is not True else []),
                        *([ 
                            "formal_corporate_adjustment_contract_unverified"
                        ] if not formal_corporate.get("verified") else []),
                    ]
                )
            )
        ),
        "reason": "official_event_and_formal_corporate_adjustment_contract_verified"
        if formal_corporate.get("verified")
        and event_status.get("formal_publication_verified") is True
        else "corporate_adjustment_inventory_or_formal_contract_unverified",
    }
    price_up_blockers = []
    if not technical["prospective_available"]:
        price_up_blockers.append("technical_prospective_source_not_ready")
    if not technical["verified"]:
        price_up_blockers.append("formal_technical_source_contract_unverified")
    if not corporate["verified"]:
        price_up_blockers.append("corporate_action_adjustment_not_verified")
    prospective_price_up_blockers = []
    if not technical["prospective_available"]:
        prospective_price_up_blockers.append("technical_prospective_source_not_ready")
    adjustment_blockers_value = adjustment_custody.get("blockers")
    adjustment_blockers = (
        adjustment_blockers_value
        if isinstance(adjustment_blockers_value, (list, tuple, set))
        else []
    )
    if adjustment_custody.get("prospective_verified") is not True:
        prospective_price_up_blockers.extend(
            str(item)
            for item in adjustment_blockers
            if str(item).strip()
        )
        if not adjustment_blockers:
            prospective_price_up_blockers.append("corporate_action_adjustment_custody_not_ready")
    price_up = {
        "status": "ready" if not price_up_blockers else "blocked",
        "prospective_status": "ready" if not prospective_price_up_blockers else "blocked",
        "prospective_blockers": list(dict.fromkeys(prospective_price_up_blockers)),
        "requires_observed_cost": False,
        "prospective_only": True,
        "historical_replay_eligible": False,
        "blockers": price_up_blockers,
    }
    after_cost_blockers = list(price_up_blockers)
    observed_cost = cost.get("observed")
    observed_cost = observed_cost if isinstance(observed_cost, Mapping) else {}
    if not observed_cost.get("eligible"):
        after_cost_blockers.append("observed_liquidity_cost_not_matured_with_fill_lineage")
    after_cost = {
        "status": "ready" if not after_cost_blockers else "blocked",
        "requires_observed_cost": True,
        "estimated_cost_is_not_observed": True,
        "prospective_only": True,
        "historical_replay_eligible": False,
        "blockers": after_cost_blockers,
    }
    actual_execution = {
        "status": "blocked",
        "requires_broker_fill_custody": True,
        "blockers": ["broker_actual_fill_custody_not_in_scope"],
    }
    contract_body: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "status": "ready" if all(
            str(lane.get("status")) == "ready"
            for lane in (price_up, after_cost, actual_execution)
        ) else "blocked",
        "decision_date": date_text,
        "availability_cutoff_at": availability_cutoff_text,
        "symbols": sorted({str(symbol).strip() for symbol in symbols if str(symbol).strip()}),
        "source_root": str(source_output),
        "data_root": str(Path(data_root).expanduser().resolve()),
        "source_database": str(database),
        "technical": technical,
        "corporate_actions": corporate,
        "cost": cost,
        "lanes": {
            "price_up_calibration": price_up,
            "after_cost_calibration": after_cost,
            "actual_execution": actual_execution,
        },
        "historical_pit_policy": {
            "eligible": False,
            "reason": "newly_captured_receipts cannot backdate historical decisions",
        },
        "replay_vs_prospective": {
            "historical_replay_status": "blocked_until_true_pit_source_contract_exists",
            "prospective_input_status": "ready_for_future_capture_only"
            if price_up["prospective_status"] == "ready"
            else "blocked_until_daily_update_receipts_exist",
        },
    }
    contract = {
        **contract_body,
        "contract_sha256": _hash_payload(contract_body),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    return contract


def write_source_contract(
    contract: Mapping[str, object],
    *,
    learning_output_root: str | Path,
) -> dict[str, object]:
    """Persist the contract as an immutable dataset plus a replaceable pointer."""

    root = Path(learning_output_root).expanduser().resolve() / "recommendation_learning" / "source_contract"
    decision_date = str(contract.get("decision_date") or "unknown")
    digest = str(contract.get("contract_sha256") or _hash_payload(dict(contract)))
    path = root / decision_date / digest[7:23] / "contract.json"
    encoded = (_canonical_json(dict(contract)) + "\n").encode("utf-8")
    _write_create_only(path, encoded)
    pointer = {
        "schema_version": "recommendation-calibration-source-contract-pointer.v1",
        "decision_date": decision_date,
        "contract_path": str(path.resolve()),
        "contract_content_sha256": digest,
        "contract_file_sha256": _hash_bytes(encoded),
        "contract_sha256": _hash_bytes(encoded),
        "lane_status": contract.get("lanes"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    pointer_path = root / "latest.json"
    _write_replace_json(pointer_path, pointer)
    return {
        "status": "persisted",
        "contract_path": str(path.resolve()),
        "contract_content_sha256": digest,
        "contract_file_sha256": _hash_bytes(encoded),
        "contract_sha256": _hash_bytes(encoded),
        "pointer_path": str(pointer_path.resolve()),
        "lanes": contract.get("lanes"),
    }


def _write_replace_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(_canonical_json(payload) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


__all__ = [
    "SCHEMA_VERSION",
    "TECHNICAL_COMPUTATION_SCHEMA_VERSION",
    "TECHNICAL_PUBLICATION_SCHEMA_VERSION",
    "build_technical_computation_evidence",
    "capture_technical_input_snapshot",
    "daily_price_receipt_source_dates",
    "discover_daily_price_receipt_paths",
    "inspect_source_contract",
    "publish_technical_indicator_receipt",
    "reuse_verified_technical_computation_receipt",
    "write_source_contract",
]
