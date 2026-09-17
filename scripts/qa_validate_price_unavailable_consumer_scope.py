"""Read-only full-scope validation for mapped price-unavailable contracts.

The input artifacts are deliberately consumed as JSON arrays one object at a
time.  This keeps the 16,919-row mapping and the existing 16,912-contract
receipt out of an unbounded Python list while still comparing the complete key
sequence, rebuilding every eligible contract, and preserving a complete
per-key JSONL validation receipt.

This script never opens the production database, never reads the canonical D:
roots, and never writes a PIT, Direct, OOC, or training artifact.  It only
uses the already-produced C: artifacts plus in-memory isolated consumer
fixtures.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import itertools
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterator, Mapping, Sequence
import uuid


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_module.ml_historical_snapshot_provider import (
    HistoricalIndexObservation,
    HistoricalPriceObservation,
    HistoricalRawSnapshot,
)
from data_module.ml_pit_year_shard_exporter import (
    _source_quality_is_price_unavailable_only,
)
from data_module.ml_price_availability_contract import (
    build_price_unavailable_research_contract,
    validate_price_unavailable_research_contract,
)
from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY
from ml_module.historical_contracts import HistoricalFeatureRow
from ml_module.historical_feature_builder import HistoricalFeatureBuilder
from ml_module.historical_label_builder import (
    CorporateActionLabelEligibility,
    HistoricalLabelBuilder,
)


SCHEMA_VERSION = "raw-pit-price-unavailable-consumer-full-scope.v1"
RECORDS_SCHEMA_VERSION = "raw-pit-price-unavailable-consumer-record.v1"
_CHUNK_BYTES = 1 << 16
_HASH_CHUNK_BYTES = 1 << 20
_SHA256_PREFIX = "sha256:"
_MAX_EXCEPTION_SUMMARY_ROWS = 64


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _payload_hash(value: object) -> str:
    return _SHA256_PREFIX + hashlib.sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest()


def _file_fingerprint(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_file() or resolved.is_symlink():
        raise FileNotFoundError(resolved)
    digest = hashlib.sha256()
    with resolved.open("rb") as stream:
        while chunk := stream.read(_HASH_CHUNK_BYTES):
            digest.update(chunk)
    stat = resolved.stat()
    return {
        "path": str(resolved),
        "bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "file_sha256": _SHA256_PREFIX + digest.hexdigest(),
    }


def _key_digest_update(
    digest: "hashlib._Hash",
    *,
    date_value: str,
    symbol: str,
) -> None:
    encoded = _canonical_json(
        {"date": date_value, "symbol": symbol}
    ).encode("utf-8")
    digest.update(len(encoded).to_bytes(8, "big"))
    digest.update(encoded)


def _key(row: Mapping[str, Any]) -> tuple[str, str]:
    raw_date = row.get("date")
    raw_symbol = row.get("symbol")
    if raw_date is None or raw_symbol is None:
        raise ValueError("mapping row requires date and symbol")
    return str(raw_date), str(raw_symbol)


def _normalise_date(value: object) -> str:
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return date(
            int(text[:4]), int(text[4:6]), int(text[6:8])
        ).isoformat()
    return date.fromisoformat(text[:10]).isoformat()


def _raw_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "symbol": row["symbol"],
        "name": row.get("name"),
        "open": row.get("open"),
        "high": row.get("high"),
        "low": row.get("low"),
        "close": row.get("close"),
        "volume_shares": row.get("volume_shares"),
        "unit": row.get("unit"),
        "scale": row.get("scale"),
    }


def _source_file(mapping: Mapping[str, Any]) -> Mapping[str, Any] | None:
    route = mapping.get("route")
    if not isinstance(route, Mapping) or route.get("status") != "invalid_only":
        return None
    invalid = route.get("invalid")
    if not isinstance(invalid, list) or len(invalid) != 1:
        return None
    entry = invalid[0]
    if not isinstance(entry, Mapping) or not isinstance(entry.get("file"), Mapping):
        return None
    return entry["file"]


def _is_equivalent_unavailable(mapping: Mapping[str, Any]) -> bool:
    comparison = mapping.get("comparison")
    route = mapping.get("route")
    if not isinstance(comparison, Mapping) or not isinstance(route, Mapping):
        return False
    invalid = route.get("invalid")
    return (
        comparison.get("all_fields_equal") is True
        and comparison.get("all_ohlc_missing_equivalent") is True
        and route.get("status") == "invalid_only"
        and isinstance(invalid, list)
        and len(invalid) == 1
    )


def _seek_array_field(stream: Any, field_name: str) -> None:
    """Seek to a top-level JSON array using bounded binary scanning."""

    needle = (json.dumps(field_name, ensure_ascii=False) + ":").encode("utf-8")
    carry = b""
    bytes_read = 0
    while True:
        chunk = stream.read(_CHUNK_BYTES)
        if not chunk:
            raise ValueError(f"JSON array field not found: {field_name}")
        combined = carry + chunk
        offset = combined.find(needle)
        if offset >= 0:
            absolute = bytes_read - len(carry) + offset + len(needle)
            stream.seek(absolute)
            break
        bytes_read += len(chunk)
        carry = combined[-(len(needle) - 1) :]
    while True:
        current = stream.read(1)
        if not current:
            raise ValueError(f"JSON array value is missing: {field_name}")
        if current in b" \t\r\n":
            continue
        if current != b"[":
            raise ValueError(f"JSON field is not an array: {field_name}")
        return


def _iter_array_values(stream: Any) -> Iterator[Mapping[str, Any]]:
    """Yield one JSON object from an array without buffering the array."""

    value_bytes = bytearray()
    depth = 0
    started = False
    in_string = False
    escaped = False
    while True:
        chunk = stream.read(_CHUNK_BYTES)
        if not chunk:
            raise ValueError("unterminated JSON array")
        for current in chunk:
            if not started:
                if current in b" \t\r\n,":
                    continue
                if current == ord("]"):
                    return
                started = True
                value_bytes.clear()
                depth = 0
                in_string = False
                escaped = False
            value_bytes.append(current)
            if in_string:
                if escaped:
                    escaped = False
                elif current == ord("\\"):
                    escaped = True
                elif current == ord('"'):
                    in_string = False
                continue
            if current == ord('"'):
                in_string = True
            elif current in (ord("{"), ord("[")):
                depth += 1
            elif current in (ord("}"), ord("]")):
                depth -= 1
                if depth < 0:
                    raise ValueError("invalid JSON array nesting")
            if depth == 0:
                parsed = json.loads(bytes(value_bytes).decode("utf-8"))
                if not isinstance(parsed, Mapping):
                    raise ValueError("JSON array item must be an object")
                yield parsed
                value_bytes.clear()
                started = False
                in_string = False
                escaped = False


def _iter_json_array_field(path: Path, field_name: str) -> Iterator[Mapping[str, Any]]:
    with path.open("rb") as stream:
        _seek_array_field(stream, field_name)
        yield from _iter_array_values(stream)


def _iter_jsonl(path: Path) -> Iterator[Mapping[str, Any]]:
    with path.open("rb") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            if not raw_line.strip():
                continue
            try:
                value = json.loads(raw_line.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid JSONL at {path}:{line_number}") from exc
            if not isinstance(value, Mapping):
                raise ValueError(f"JSONL item must be an object: {path}:{line_number}")
            yield value


def _write_json_create_only(path: Path, payload: Mapping[str, Any]) -> None:
    resolved = path.resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )
    with resolved.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


class _ValidationRecordsWriter:
    """Publish a complete per-key receipt without overwriting a prior run."""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            raise FileExistsError(self.path)
        self._temporary_path = self.path.with_name(f".{uuid.uuid4().hex}.tmp")
        self._stream = self._temporary_path.open("xb")
        self._key_digest = hashlib.sha256()
        self._record_digest = hashlib.sha256()
        self._row_count = 0
        self._previous_key: tuple[str, str] | None = None
        self._duplicate_key_count = 0
        self._out_of_order_key_count = 0
        self._closed = False

    def write(self, record: Mapping[str, Any]) -> None:
        if self._closed:
            raise RuntimeError("validation records writer is closed")
        date_value, symbol = _key(record)
        encoded = (_canonical_json(dict(record)) + "\n").encode("utf-8")
        self._stream.write(encoded)
        self._record_digest.update(len(encoded).to_bytes(8, "big"))
        self._record_digest.update(encoded)
        _key_digest_update(
            self._key_digest,
            date_value=date_value,
            symbol=symbol,
        )
        current_key = (date_value, symbol)
        if self._previous_key is not None:
            if current_key == self._previous_key:
                self._duplicate_key_count += 1
            elif current_key < self._previous_key:
                self._out_of_order_key_count += 1
        self._previous_key = current_key
        self._row_count += 1

    def finalize(self) -> dict[str, Any]:
        if self._closed:
            raise RuntimeError("validation records writer is already closed")
        try:
            self._stream.flush()
            os.fsync(self._stream.fileno())
            self._stream.close()
            self._closed = True
            if self.path.exists():
                raise FileExistsError(self.path)
            os.link(self._temporary_path, self.path)
            self._temporary_path.unlink(missing_ok=True)
        except BaseException:
            try:
                if not self._stream.closed:
                    self._stream.close()
            except OSError:
                pass
            self._closed = True
            try:
                self._temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        return {
            "schema_version": RECORDS_SCHEMA_VERSION,
            "format": "jsonl",
            "path": str(self.path),
            "row_count": self._row_count,
            "key_fields": ["date", "symbol"],
            "key_order": "date_symbol_ascending",
            "duplicate_key_count": self._duplicate_key_count,
            "out_of_order_key_count": self._out_of_order_key_count,
            "complete": self._duplicate_key_count == 0
            and self._out_of_order_key_count == 0,
            "key_digest": _SHA256_PREFIX + self._key_digest.hexdigest(),
            "record_digest": _SHA256_PREFIX + self._record_digest.hexdigest(),
            "file_sha256": _file_fingerprint(self.path)["file_sha256"],
        }

    def abort(self) -> None:
        if not self._closed:
            try:
                self._stream.close()
            except (OSError, ValueError):
                pass
            self._closed = True
        try:
            self._temporary_path.unlink(missing_ok=True)
        except OSError:
            pass


def _safe_disposition(contract: Mapping[str, Any]) -> bool:
    disposition = contract.get("disposition")
    return (
        isinstance(disposition, Mapping)
        and disposition.get("research_only") is True
        and disposition.get("include_price_feature_row") is False
        and disposition.get("include_price_label_row") is False
        and disposition.get("preserve_source_row") is True
        and disposition.get("zero_fill") is False
        and disposition.get("drop_source_row") is False
        and disposition.get("source_quality_research_eligible") is True
    )


def _contract_record(
    *,
    raw: Mapping[str, Any],
    mapping: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    affected_window = contract.get("affected_window")
    disposition = contract.get("disposition")
    if not isinstance(affected_window, Mapping) or not isinstance(
        disposition, Mapping
    ):
        raise ValueError("validated contract has missing consumer fields")
    return {
        "schema_version": RECORDS_SCHEMA_VERSION,
        "date": str(raw["date"]),
        "symbol": str(raw["symbol"]),
        "sqlite_rowid": raw.get("sqlite_rowid"),
        "sqlite_bucket": raw.get("bucket"),
        "canonical_route_status": (
            mapping.get("route", {}).get("status")
            if isinstance(mapping.get("route"), Mapping)
            else None
        ),
        "contract_validation": "passed",
        "contract_payload_hash": _payload_hash(contract),
        "field_status": contract["field_status"],
        "missing_mask": contract["missing_mask"],
        "volume_shares": contract["volume_shares"],
        "source_file": contract.get("source_file"),
        "window_scope": affected_window["window_scope"],
        "feature_window_complete": affected_window["feature_window_complete"],
        "label_window_complete": affected_window["label_window_complete"],
        "horizon_expansion_required": affected_window[
            "horizon_expansion_required"
        ],
        "feature_consumer_status": (
            "context_ready_for_execution"
            if affected_window["feature_window_complete"]
            else "requires_explicit_feature_horizon_context"
        ),
        "label_consumer_status": (
            "context_ready_for_execution"
            if affected_window["label_window_complete"]
            else "requires_explicit_label_horizon_context"
        ),
        "source_quality_disposition": disposition[
            "source_quality_disposition"
        ],
    }


def _excluded_record(
    *, raw: Mapping[str, Any], mapping: Mapping[str, Any]
) -> dict[str, Any]:
    comparison = mapping.get("comparison")
    route = mapping.get("route")
    return {
        "schema_version": RECORDS_SCHEMA_VERSION,
        "date": str(raw["date"]),
        "symbol": str(raw["symbol"]),
        "sqlite_bucket": raw.get("bucket"),
        "route_status": (
            route.get("status") if isinstance(route, Mapping) else None
        ),
        "differing_fields": (
            comparison.get("differing_fields", [])
            if isinstance(comparison, Mapping)
            else []
        ),
        "contract_validation": "not_run_non_equivalent",
        "reason": "canonical_evidence_not_identically_unavailable",
    }


def _feature_probe() -> dict[str, Any]:
    prices = tuple(
        HistoricalPriceObservation(
            symbol="2330",
            trading_date=f"2024-01-{day:02d}",
            open_price=Decimal(day),
            high_price=Decimal(day + 1),
            low_price=Decimal(day - 1),
            close_price=Decimal(day),
            volume=day * 100,
            turnover_amount_minor=day * 1000,
        )
        for day in range(1, 22)
    )
    snapshot = HistoricalRawSnapshot(
        decision_date="2024-01-22",
        feature_as_of_date="2024-01-21",
        prices=prices,
        technicals=(),
        market=tuple(
            HistoricalIndexObservation(
                "market", f"2024-01-{day:02d}", Decimal(day * 2)
            )
            for day in range(1, 22)
        ),
        industries=(),
        source_fingerprint=_SHA256_PREFIX + "1" * 64,
        query_count=1,
    )
    contract = build_price_unavailable_research_contract(
        symbol="2330",
        date_iso="2024-01-10",
        raw_row={
            "symbol": "2330",
            "open": "--",
            "high": "--",
            "low": "--",
            "close": "--",
            "volume": 2_000,
        },
        feature_window_dates=tuple(
            f"2024-01-{day:02d}" for day in range(1, 22)
        ),
    )
    row = HistoricalFeatureBuilder().compute(
        snapshot,
        industry_index_name_by_symbol={},
        price_unavailable_contracts=(contract,),
    )[0]
    values = dict(row.values)
    recent_gap_contract = build_price_unavailable_research_contract(
        symbol="2330",
        date_iso="2024-01-20",
        raw_row=contract["raw_row"],
        feature_window_dates=tuple(
            f"2024-01-{day:02d}" for day in range(1, 22)
        ),
    )
    recent_row = HistoricalFeatureBuilder().compute(
        snapshot,
        industry_index_name_by_symbol={},
        price_unavailable_contracts=(recent_gap_contract,),
    )[0]
    recent_values = dict(recent_row.values)
    anchor_only = build_price_unavailable_research_contract(
        symbol="2330",
        date_iso="2024-01-20",
        raw_row=contract["raw_row"],
    )
    try:
        HistoricalFeatureBuilder().compute(
            snapshot,
            industry_index_name_by_symbol={},
            price_unavailable_contracts=(anchor_only,),
        )
    except ValueError as exc:
        anchor_only_rejected = "feature window is incomplete" in str(exc)
    else:
        anchor_only_rejected = False
    checks = {
        "explicit_contract_consumed": True,
        "early_gap_return_1d_is_available": values["stock_return_1d_bp"] == 500,
        "early_gap_return_5d_is_available": values["stock_return_5d_bp"] == 3125,
        "early_gap_return_20d_is_missing": values["stock_return_20d_bp"] is None,
        "early_gap_ma_5d_is_available": values["close_to_ma_5d_bp"] is not None,
        "early_gap_ma_20d_is_missing": values["close_to_ma_20d_bp"] is None,
        "recent_gap_return_1d_is_missing": recent_values["stock_return_1d_bp"] is None,
        "recent_gap_return_5d_is_missing": recent_values["stock_return_5d_bp"] is None,
        "trailing_volatility_20d_is_missing": (
            values["trailing_volatility_20d_bp"] is None
        ),
        "volume_ratio_5d_is_missing": values["volume_ratio_5d_bp"] is None,
        "anchor_only_contract_rejected": anchor_only_rejected,
    }
    return {
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "policy": (
            "explicit feature window required; missing_is_not_zero; "
            "surrounding rows are not bridged"
        ),
    }


def _label_probe() -> dict[str, Any]:
    prices = tuple(
        HistoricalPriceObservation(
            symbol="2330",
            trading_date=f"2024-01-{day:02d}",
            open_price=Decimal(day),
            high_price=Decimal(day),
            low_price=Decimal(day),
            close_price=Decimal(day),
            volume=100,
            turnover_amount_minor=1000,
        )
        for day in range(1, 22)
    )
    market = tuple(
        HistoricalIndexObservation("market", f"2024-01-{day:02d}", Decimal(day))
        for day in range(1, 22)
    )
    contract = build_price_unavailable_research_contract(
        symbol="2330",
        date_iso="2024-01-10",
        raw_row={
            "symbol": "2330",
            "open": "--",
            "high": "--",
            "low": "--",
            "close": "--",
            "volume": 100,
        },
        feature_window_dates=("2024-01-10",),
        label_window_dates=tuple(
            f"2024-01-{day:02d}" for day in range(1, 22)
        ),
    )
    feature = HistoricalFeatureRow(
        symbol="2330",
        decision_date="2024-01-02",
        feature_as_of_date="2024-01-01",
        available_date="2024-01-02",
        values=tuple(
            (spec.feature_id, None)
            for spec in CORE_LONG_HISTORY_FEATURE_REGISTRY.specs
        ),
    )
    clean = CorporateActionLabelEligibility(
        label_start_date="2024-01-01",
        label_end_date="2024-01-21",
        eligible=True,
        quality="clean",
    )
    result = HistoricalLabelBuilder().build(
        feature_rows=(feature,),
        prices=prices,
        market=market,
        label_as_of="2024-01-21",
        corporate_action_by_row={("2330", "2024-01-02"): clean},
        mode="strict",
        price_unavailable_contracts=(contract,),
    )
    outside_label_contract = build_price_unavailable_research_contract(
        symbol="2330",
        date_iso="2023-12-31",
        raw_row=contract["raw_row"],
        feature_window_dates=("2023-12-31",),
        label_window_dates=tuple(
            f"2024-01-{day:02d}" for day in range(1, 22)
        ),
    )
    outside_result = HistoricalLabelBuilder().build(
        feature_rows=(feature,),
        prices=prices,
        market=market,
        label_as_of="2024-01-21",
        corporate_action_by_row={("2330", "2024-01-02"): clean},
        mode="strict",
        price_unavailable_contracts=(outside_label_contract,),
    )
    anchor_only = build_price_unavailable_research_contract(
        symbol="2330",
        date_iso="2024-01-10",
        raw_row=contract["raw_row"],
    )
    try:
        HistoricalLabelBuilder().build(
            feature_rows=(feature,),
            prices=prices,
            market=market,
            label_as_of="2024-01-21",
            corporate_action_by_row={("2330", "2024-01-02"): clean},
            mode="strict",
            price_unavailable_contracts=(anchor_only,),
        )
    except ValueError as exc:
        anchor_only_rejected = "label window is incomplete" in str(exc)
    else:
        anchor_only_rejected = False
    checks = {
        "explicit_contract_consumed": True,
        "labels_empty": result.labels == (),
        "price_unavailable_in_label_window": result.excluded_diagnostics
        == {"price_unavailable_in_label_window": 1},
        "outside_label_anchor_does_not_block": len(outside_result.labels) == 4,
        "formal_oos_not_granted": result.formal_oos_allowed is False,
        "anchor_only_contract_rejected": anchor_only_rejected,
    }
    return {
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "policy": (
            "explicit label window required; label path is excluded on gap; "
            "no adjacency compression"
        ),
    }


def _compare_existing_contract_records(
    *,
    diagnostic_path: Path,
    records_path: Path,
) -> dict[str, Any]:
    expected = (
        record
        for record in _iter_jsonl(records_path)
        if record.get("contract_validation") == "passed"
    )
    actual = _iter_json_array_field(diagnostic_path, "contract_records")
    compared = 0
    mismatch_count = 0
    first_mismatch: dict[str, Any] | None = None
    for existing, generated in itertools.zip_longest(actual, expected):
        if existing is None or generated is None:
            mismatch_count += 1
            if first_mismatch is None:
                first_mismatch = {
                    "existing_present": existing is not None,
                    "generated_present": generated is not None,
                }
            continue
        compared += 1
        fields = (
            "date",
            "symbol",
            "contract_payload_hash",
            "field_status",
            "missing_mask",
            "volume_shares",
            "window_scope",
            "feature_window_complete",
            "label_window_complete",
            "horizon_expansion_required",
            "source_quality_disposition",
        )
        if any(existing.get(field) != generated.get(field) for field in fields):
            mismatch_count += 1
            if first_mismatch is None:
                first_mismatch = {
                    "key": [existing.get("date"), existing.get("symbol")],
                    "fields": [
                        field
                        for field in fields
                        if existing.get(field) != generated.get(field)
                    ],
                }
    return {
        "existing_contract_record_count": compared,
        "mismatch_count": mismatch_count,
        "first_mismatch": first_mismatch,
        "status": "passed" if mismatch_count == 0 else "failed",
    }


def _compare_existing_excluded_rows(
    *,
    diagnostic_path: Path,
    records_path: Path,
) -> dict[str, Any]:
    actual = _iter_json_array_field(
        diagnostic_path, "excluded_non_equivalent_rows"
    )
    expected = (
        record
        for record in _iter_jsonl(records_path)
        if record.get("contract_validation") == "not_run_non_equivalent"
    )
    compared = 0
    mismatch_count = 0
    first_mismatch: dict[str, Any] | None = None
    for existing, generated in itertools.zip_longest(actual, expected):
        if existing is None or generated is None:
            mismatch_count += 1
            if first_mismatch is None:
                first_mismatch = {
                    "existing_present": existing is not None,
                    "generated_present": generated is not None,
                }
            continue
        compared += 1
        fields = (
            "date",
            "symbol",
            "sqlite_bucket",
            "route_status",
            "differing_fields",
            "reason",
        )
        if any(existing.get(field) != generated.get(field) for field in fields):
            mismatch_count += 1
            if first_mismatch is None:
                first_mismatch = {
                    "key": [existing.get("date"), existing.get("symbol")],
                    "fields": [
                        field
                        for field in fields
                        if existing.get(field) != generated.get(field)
                    ],
                }
    return {
        "existing_excluded_record_count": compared,
        "mismatch_count": mismatch_count,
        "first_mismatch": first_mismatch,
        "status": "passed" if mismatch_count == 0 else "failed",
    }


def _required_horizon_data() -> dict[str, list[str]]:
    return {
        "historical_feature_builder": [
            "decision_date and feature_as_of_date",
            "ordered per-symbol price observations covering every explicit feature window date",
            "raw OHLC, volume, turnover and source/availability identity for those observations",
            "market and industry observations required by the frozen feature registry",
        ],
        "historical_label_builder": [
            "label_as_of and a symbol/date keyed feature row",
            "a complete market trading calendar for the 20-session label window",
            "per-symbol stock OHLC/volume rows for every label-window session, including explicit gap evidence",
            "benchmark observations and an exact corporate-action eligibility window",
            "source row hashes and available_at values no later than label_as_of",
        ],
        "portfolio_ml_dataset_assembler": [
            "PIT raw shard rows carrying the validated contract",
            "ordered stock and benchmark paths for each configured 5/10/20/60-session horizon",
            "the assembler price-gap lookup and label-path source hashes",
        ],
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate mapped price-unavailable contracts without a source rescan."
    )
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--contract-diagnostic", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--records-output", type=Path, required=True)
    return parser


def _main(arguments: Sequence[str] | None = None) -> int:
    options = _build_parser().parse_args(arguments)
    mapping_path = options.mapping.resolve()
    diagnostic_path = options.contract_diagnostic.resolve()
    output_path = options.output.resolve()
    records_path = options.records_output.resolve()
    if output_path in {mapping_path, diagnostic_path} or records_path in {
        mapping_path,
        diagnostic_path,
    }:
        raise ValueError("output paths must not overwrite input artifacts")

    mapping_fingerprint = _file_fingerprint(mapping_path)
    diagnostic_fingerprint = _file_fingerprint(diagnostic_path)
    writer = _ValidationRecordsWriter(records_path)
    counters: Counter[str] = Counter()
    key_digests = {
        "mapping_all": hashlib.sha256(),
        "invalid_all": hashlib.sha256(),
        "eligible": hashlib.sha256(),
        "excluded": hashlib.sha256(),
    }
    previous_mapping_key: tuple[str, str] | None = None
    previous_invalid_key: tuple[str, str] | None = None
    excluded_summary_rows: list[dict[str, Any]] = []
    sequence_mismatch_count = 0
    first_sequence_mismatch: dict[str, Any] | None = None

    mappings = _iter_json_array_field(
        mapping_path, "invalid_row_canonical_mappings_union"
    )
    invalid_rows = _iter_json_array_field(mapping_path, "invalid_rows")
    try:
        for index, (mapping, raw) in enumerate(
            itertools.zip_longest(mappings, invalid_rows), start=1
        ):
            if mapping is None or raw is None:
                sequence_mismatch_count += 1
                if first_sequence_mismatch is None:
                    first_sequence_mismatch = {
                        "index": index,
                        "mapping_present": mapping is not None,
                        "invalid_present": raw is not None,
                    }
                continue
            mapping_key = _key(mapping)
            invalid_key = _key(raw)
            _key_digest_update(
                key_digests["mapping_all"],
                date_value=mapping_key[0],
                symbol=mapping_key[1],
            )
            _key_digest_update(
                key_digests["invalid_all"],
                date_value=invalid_key[0],
                symbol=invalid_key[1],
            )
            counters["mapping_rows"] += 1
            counters["invalid_rows"] += 1
            if previous_mapping_key is not None and mapping_key <= previous_mapping_key:
                counters["mapping_duplicate_or_out_of_order"] += 1
            if previous_invalid_key is not None and invalid_key <= previous_invalid_key:
                counters["invalid_duplicate_or_out_of_order"] += 1
            previous_mapping_key = mapping_key
            previous_invalid_key = invalid_key
            if mapping_key != invalid_key:
                sequence_mismatch_count += 1
                if first_sequence_mismatch is None:
                    first_sequence_mismatch = {
                        "index": index,
                        "mapping_key": list(mapping_key),
                        "invalid_key": list(invalid_key),
                    }
                continue
            if _is_equivalent_unavailable(mapping):
                source_file = _source_file(mapping)
                if source_file is None:
                    raise ValueError(
                        f"eligible row has no unique canonical source file: {mapping_key}"
                    )
                contract = build_price_unavailable_research_contract(
                    symbol=str(raw["symbol"]),
                    date_iso=_normalise_date(raw["date"]),
                    raw_row=_raw_row(raw),
                    source_file=source_file,
                )
                validate_price_unavailable_research_contract(contract)
                if not _safe_disposition(contract):
                    raise ValueError(f"unsafe price-unavailable disposition: {mapping_key}")
                record = _contract_record(
                    raw=raw, mapping=mapping, contract=contract
                )
                writer.write(record)
                _key_digest_update(
                    key_digests["eligible"],
                    date_value=mapping_key[0],
                    symbol=mapping_key[1],
                )
                counters["contract_validation_success"] += 1
                if raw.get("bucket") == "literal_marker_all_ohlc":
                    counters["literal_marker_contracts"] += 1
                elif raw.get("bucket") == "sql_null_or_empty_all_ohlc":
                    counters["sql_null_contracts"] += 1
                else:
                    raise ValueError(f"unexpected eligible bucket: {raw.get('bucket')}")
                window = contract["affected_window"]
                if window["feature_window_complete"]:
                    counters["feature_context_ready"] += 1
                else:
                    counters["feature_context_required"] += 1
                if window["label_window_complete"]:
                    counters["label_context_ready"] += 1
                else:
                    counters["label_context_required"] += 1
            else:
                record = _excluded_record(raw=raw, mapping=mapping)
                writer.write(record)
                if len(excluded_summary_rows) < _MAX_EXCEPTION_SUMMARY_ROWS:
                    excluded_summary_rows.append(record)
                _key_digest_update(
                    key_digests["excluded"],
                    date_value=mapping_key[0],
                    symbol=mapping_key[1],
                )
                counters["excluded_non_equivalent"] += 1
    except BaseException:
        writer.abort()
        raise
    records_manifest = writer.finalize()
    counters["sequence_mismatch"] = sequence_mismatch_count
    mixed_gate = _source_quality_is_price_unavailable_only(
        {
            "candidate_count": counters["mapping_rows"],
            "research_price_unavailable_count": counters[
                "contract_validation_success"
            ],
            "research_price_invalid_count": counters["excluded_non_equivalent"],
            "classification_counts": {
                "sqlite_row_invalid_requires_quarantine": counters[
                    "contract_validation_success"
                ],
                "canonical_evidence_not_identically_unavailable": counters[
                    "excluded_non_equivalent"
                ],
            },
        }
    )
    scoped_gate = _source_quality_is_price_unavailable_only(
        {
            "candidate_count": counters["contract_validation_success"],
            "research_price_unavailable_count": counters[
                "contract_validation_success"
            ],
            "research_price_invalid_count": 0,
            "classification_counts": {
                "sqlite_row_invalid_requires_quarantine": counters[
                    "contract_validation_success"
                ],
            },
        }
    )
    existing_contracts = _compare_existing_contract_records(
        diagnostic_path=diagnostic_path,
        records_path=records_path,
    )
    existing_excluded = _compare_existing_excluded_rows(
        diagnostic_path=diagnostic_path,
        records_path=records_path,
    )
    feature_probe = _feature_probe()
    label_probe = _label_probe()
    repo_root = Path(__file__).resolve().parents[1]
    code_files = (
        repo_root / "data_module" / "ml_price_availability_contract.py",
        repo_root / "ml_module" / "historical_feature_builder.py",
        repo_root / "ml_module" / "historical_label_builder.py",
        Path(__file__).resolve(),
    )
    body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": (
            "passed_with_horizon_context_pending"
            if sequence_mismatch_count == 0
            and counters["mapping_rows"] > 0
            and counters["mapping_rows"] == counters["invalid_rows"]
            and counters["excluded_non_equivalent"] > 0
            and counters["contract_validation_success"] > 0
            and counters["feature_context_required"]
            == counters["contract_validation_success"]
            and counters["label_context_required"]
            == counters["contract_validation_success"]
            and counters["mapping_duplicate_or_out_of_order"] == 0
            and counters["invalid_duplicate_or_out_of_order"] == 0
            and mixed_gate is False
            and scoped_gate is True
            and existing_contracts["status"] == "passed"
            and existing_excluded["status"] == "passed"
            and feature_probe["status"] == "passed"
            and label_probe["status"] == "passed"
            else "failed"
        ),
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "network_attempted": False,
        "source_database_opened": False,
        "source_database_write": False,
        "direct_rebuild": False,
        "raw_pit_rebuild": False,
        "formal_training_or_promotion": False,
        "input_artifacts": {
            "mapping_union": mapping_fingerprint,
            "existing_contract_diagnostic": diagnostic_fingerprint,
        },
        "code_fingerprints": [_file_fingerprint(path) for path in code_files],
        "full_scope_counts": dict(counters),
        "sequence_integrity": {
            "mapping_and_invalid_key_sequence_equal": sequence_mismatch_count == 0,
            "first_mismatch": first_sequence_mismatch,
            "mapping_duplicate_or_out_of_order": counters[
                "mapping_duplicate_or_out_of_order"
            ],
            "invalid_duplicate_or_out_of_order": counters[
                "invalid_duplicate_or_out_of_order"
            ],
        },
        "key_digests": {
            name: _SHA256_PREFIX + digest.hexdigest()
            for name, digest in key_digests.items()
        },
        "contract_scope": {
            "contract_schema_version": "ml-daily-price-availability.v1",
            "eligible_contracts_rebuilt_and_validated": counters[
                "contract_validation_success"
            ],
            "feature_context_ready": counters["feature_context_ready"],
            "feature_context_required": counters["feature_context_required"],
            "label_context_ready": counters["label_context_ready"],
            "label_context_required": counters["label_context_required"],
            "window_scope_observed": "anchor_only",
            "full_feature_label_horizon_expansion_performed": False,
            "full_production_pipeline_execution": False,
            "research_only": True,
            "formal_training_allowed": False,
            "note": (
                "Every eligible contract was rebuilt from the union row and "
                "validated. Existing receipts contain anchor-only windows, so "
                "no key is claimed as a fully expanded feature/label sample."
            ),
        },
        "consumer_validation": {
            "historical_feature_builder": feature_probe,
            "historical_label_builder": label_probe,
            "existing_contract_receipt_readback": existing_contracts,
            "existing_excluded_rows_readback": existing_excluded,
            "required_horizon_context": _required_horizon_data(),
        },
        "source_quality_gates": {
            "mixed_mapping_gate_allowed": mixed_gate,
            "scoped_equivalent_subset_gate_allowed": scoped_gate,
            "seven_non_equivalent_rows_isolated": counters[
                "excluded_non_equivalent"
            ] > 0,
            "formal_training_allowed": False,
        },
        "unprocessed_exceptions": {
            "non_equivalent_rows": excluded_summary_rows,
            "non_equivalent_rows_summary_truncated": counters[
                "excluded_non_equivalent"
            ]
            > len(excluded_summary_rows),
            "horizon_context_missing": {
                "count": counters["contract_validation_success"],
                "key_digest": _SHA256_PREFIX
                + key_digests["eligible"].hexdigest(),
                "feature_window": "all existing contracts are anchor_only",
                "label_window": "all existing contracts are anchor_only",
            },
        },
        "output_records": records_manifest,
        "reproducibility": {
            "jsonl_record_hash": records_manifest["record_digest"],
            "summary_report_hash_definition": (
                "sha256(canonical JSON body excluding report_hash)"
            ),
            "key_digest_definition": (
                "length-prefixed canonical JSON {date,symbol}, in source order"
            ),
            "input_rescan_performed": False,
        },
    }
    body["report_hash"] = _payload_hash(body)
    _write_json_create_only(output_path, body)
    summary_fingerprint = _file_fingerprint(output_path)
    print(
        json.dumps(
            {
                "status": body["status"],
                "summary_path": str(output_path),
                "summary_file_sha256": summary_fingerprint["file_sha256"],
                "report_hash": body["report_hash"],
                "records_path": records_manifest["path"],
                "records_file_sha256": records_manifest["file_sha256"],
                "mapping_rows": counters["mapping_rows"],
                "eligible_contracts": counters["contract_validation_success"],
                "excluded_non_equivalent": counters["excluded_non_equivalent"],
                "feature_context_required": counters["feature_context_required"],
                "label_context_required": counters["label_context_required"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if body["status"] != "failed" else 2


if __name__ == "__main__":
    raise SystemExit(_main())
