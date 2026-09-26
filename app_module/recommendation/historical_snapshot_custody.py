"""版本化的唯讀 historical raw snapshot 身分與內容 custody facts。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import hashlib
import json
from typing import TypeAlias

from data_module.ml_historical_snapshot_provider import (
    HISTORICAL_SNAPSHOT_PROVIDER_CONTRACT_ID_V1,
    HistoricalIndexObservation,
    HistoricalPriceObservation,
    HistoricalRawSnapshot,
    HistoricalTechnicalObservation,
    ValidatedHistoricalLoadScopeV1,
    ValidatedHistoricalSchemaEvidenceV1,
)
from ml_module.prepared_input_contract import (
    AvailabilityBinding,
    AvailabilityStatus,
    DateRange,
    SnapshotKind,
    SnapshotQualityStatus,
    SnapshotReference,
    SnapshotScopeStatus,
)


_FACTS_CONTRACT = "historical-raw-snapshot-custody.v1"
_SOURCE_TABLES = (
    "daily_prices",
    "technical_indicators",
    "market_indices",
    "industry_indices",
)
_CanonicalScalar: TypeAlias = str | int | None | dict[str, str]


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("historical raw custody payload is not canonical JSON") from exc


def _domain_hash(domain: str, payload: object) -> str:
    envelope = {
        "contract": _FACTS_CONTRACT,
        "domain": domain,
        "payload": payload,
    }
    return f"sha256:{hashlib.sha256(_canonical_json(envelope)).hexdigest()}"


def _exact_iso_date(value: object, field_name: str) -> date:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be an ISO date string")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a canonical ISO date") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{field_name} must be a canonical ISO date")
    return parsed


def _require_text(value: object, field_name: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text")
    return value


def _require_sorted_texts(value: object, field_name: str, *, nonempty: bool) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise TypeError(f"{field_name} must be an immutable tuple")
    items = value
    if nonempty and not items:
        raise ValueError(f"{field_name} must not be empty")
    if any(type(item) is not str or not item or item != item.strip() for item in items):
        raise ValueError(f"{field_name} must contain normalized text")
    if tuple(sorted(set(items))) != items:
        raise ValueError(f"{field_name} must be sorted and unique")
    return items


@dataclass(frozen=True, slots=True)
class HistoricalRawSnapshotQueryScopeV1:
    """呼叫端明示的邏輯來源與 query scope，不從檔案路徑推測來源。"""

    source_id: str
    decision_date: date
    history_start_date: date
    symbols: tuple[str, ...]
    industry_index_names: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text(self.source_id, "source_id")
        if type(self.decision_date) is not date:
            raise TypeError("decision_date must be an exact date")
        if type(self.history_start_date) is not date:
            raise TypeError("history_start_date must be an exact date")
        _require_sorted_texts(self.symbols, "symbols", nonempty=True)
        _require_sorted_texts(
            self.industry_index_names, "industry_index_names", nonempty=False
        )


@dataclass(frozen=True, slots=True)
class HistoricalRawSnapshotCustodyFactsV1:
    """由 provider 同次載入的 typed rows/schema/scope 建立的不可變 facts。"""

    query_scope: HistoricalRawSnapshotQueryScopeV1
    feature_as_of_date: date
    validated_schema_version: str
    content_hash: str
    row_identity_hash: str
    snapshot_id: str
    row_count: int
    table_row_counts: tuple[tuple[str, int], ...]
    row_range_start: date | None
    row_range_end: date | None

    def __post_init__(self) -> None:
        if type(self.query_scope) is not HistoricalRawSnapshotQueryScopeV1:
            raise TypeError("query_scope must be HistoricalRawSnapshotQueryScopeV1")
        if type(self.feature_as_of_date) is not date:
            raise TypeError("feature_as_of_date must be an exact date")
        _require_text(self.validated_schema_version, "validated_schema_version")
        for name, value in (
            ("content_hash", self.content_hash),
            ("row_identity_hash", self.row_identity_hash),
        ):
            if type(value) is not str or len(value) != 71 or not value.startswith("sha256:"):
                raise ValueError(f"{name} must be sha256:<64 lowercase hex>")
            if any(character not in "0123456789abcdef" for character in value[7:]):
                raise ValueError(f"{name} must be sha256:<64 lowercase hex>")
        if type(self.snapshot_id) is not str or not self.snapshot_id.startswith(
            f"{_FACTS_CONTRACT}:sha256:"
        ):
            raise ValueError("snapshot_id must be a versioned custody identity")
        digest = self.snapshot_id.rsplit(":", 1)[-1]
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("snapshot_id must contain a lowercase SHA-256 digest")
        if type(self.row_count) is not int or self.row_count < 0:
            raise ValueError("row_count must be a non-negative exact int")
        if type(self.table_row_counts) is not tuple or len(self.table_row_counts) != 4:
            raise TypeError("table_row_counts must be a fixed four-table tuple")
        for expected, record in zip(_SOURCE_TABLES, self.table_row_counts):
            if type(record) is not tuple or len(record) != 2:
                raise TypeError("table row count entry is malformed")
            table, count = record
            if table != expected or type(count) is not int or count < 0:
                raise ValueError("table row count entry is invalid")
        if sum(count for _, count in self.table_row_counts) != self.row_count:
            raise ValueError("row_count does not equal table row counts")
        if self.row_count == 0:
            if self.row_range_start is not None or self.row_range_end is not None:
                raise ValueError("empty raw snapshot cannot claim a row range")
        else:
            if type(self.row_range_start) is not date or type(self.row_range_end) is not date:
                raise ValueError("non-empty raw snapshot requires an exact row range")
            if self.row_range_start > self.row_range_end:
                raise ValueError("row range start must not follow row range end")

    def to_snapshot_reference(self) -> SnapshotReference:
        """投影可確認的 reference；未知的 source revision/PIT/品質維持 UNKNOWN。"""

        row_range = (
            None
            if self.row_count == 0
            else DateRange(
                start_date=self.row_range_start,  # type: ignore[arg-type]
                end_date=self.row_range_end,  # type: ignore[arg-type]
            )
        )
        return SnapshotReference(
            snapshot_id=self.snapshot_id,
            source_id=self.query_scope.source_id,
            kind=SnapshotKind.BOUNDED,
            dataset_id=None,
            schema_version=self.validated_schema_version,
            content_hash=self.content_hash,
            row_identity_hash=self.row_identity_hash,
            row_count=self.row_count,
            row_range=row_range,
            source_revision=None,
            availability=AvailabilityBinding(status=AvailabilityStatus.UNKNOWN),
            quality_status=SnapshotQualityStatus.UNKNOWN,
            missing_inputs=(),
            scope_status=SnapshotScopeStatus.UNKNOWN,
        )


def _typed_decimal(value: object, field_name: str) -> _CanonicalScalar:
    if value is None:
        return None
    if type(value) is not Decimal:
        raise TypeError(f"{field_name} must be Decimal or None")
    return {"type": "decimal", "value": str(value)}


def _typed_integer(value: object, field_name: str) -> _CanonicalScalar:
    if value is None:
        return None
    if type(value) is not int:
        raise TypeError(f"{field_name} must be int or None")
    return {"type": "integer", "value": str(value)}


def _row_date(value: object, field_name: str) -> tuple[str, date]:
    parsed = _exact_iso_date(value, field_name)
    return parsed.isoformat(), parsed


def _serialized_sort_key(value: object) -> bytes:
    return _canonical_json(value)


def build_historical_raw_snapshot_custody_facts_v1(
    *,
    snapshot: HistoricalRawSnapshot,
    query_scope: HistoricalRawSnapshotQueryScopeV1,
) -> HistoricalRawSnapshotCustodyFactsV1:
    """不重查資料；只接受 provider 同次產生的 typed rows/schema/query scope。"""

    if type(snapshot) is not HistoricalRawSnapshot:
        raise TypeError("snapshot must be HistoricalRawSnapshot")
    if type(query_scope) is not HistoricalRawSnapshotQueryScopeV1:
        raise TypeError("query_scope must be HistoricalRawSnapshotQueryScopeV1")
    if snapshot.provider_contract_id != HISTORICAL_SNAPSHOT_PROVIDER_CONTRACT_ID_V1:
        raise ValueError("provider-carried historical source contract ID is required")
    if query_scope.source_id != snapshot.provider_contract_id:
        raise ValueError("query scope source ID does not match provider contract ID")
    schema = snapshot.validated_schema
    request = snapshot.validated_query_scope
    if type(schema) is not ValidatedHistoricalSchemaEvidenceV1:
        raise ValueError("validated schema evidence is required for raw custody")
    if type(request) is not ValidatedHistoricalLoadScopeV1:
        raise ValueError("same-call validated query scope evidence is required for raw custody")

    decision_date, parsed_decision = _row_date(snapshot.decision_date, "snapshot.decision_date")
    cutoff_date, parsed_cutoff = _row_date(snapshot.feature_as_of_date, "snapshot.feature_as_of_date")
    if query_scope.decision_date.isoformat() != decision_date:
        raise ValueError("query scope decision date does not match provider snapshot")
    if parsed_cutoff >= parsed_decision:
        raise ValueError("feature cutoff must precede decision date")
    if (
        request.decision_date != decision_date
        or request.history_start_date != query_scope.history_start_date.isoformat()
        or request.symbols != query_scope.symbols
        or request.industry_index_names != query_scope.industry_index_names
    ):
        raise ValueError("query scope does not match same-call provider request evidence")
    if snapshot.source_tables != _SOURCE_TABLES:
        raise ValueError("snapshot source table whitelist mismatch")
    if type(snapshot.query_count) is not int or snapshot.query_count < 0:
        raise ValueError("snapshot query count must be a non-negative exact int")

    history_start = query_scope.history_start_date
    if not all(type(rows) is tuple for rows in (snapshot.prices, snapshot.technicals, snapshot.market, snapshot.industries)):
        raise TypeError("snapshot row collections must be immutable tuples")

    counts = {
        "daily_prices": len(snapshot.prices),
        "technical_indicators": len(snapshot.technicals),
        "market_indices": len(snapshot.market),
        "industry_indices": len(snapshot.industries),
    }
    identity_rows: dict[str, list[object]] = {table: [] for table in _SOURCE_TABLES}
    binding_rows: dict[str, list[object]] = {table: [] for table in _SOURCE_TABLES}
    observed_dates: list[date] = []

    def add_row(
        table: str, key: list[str], values: list[_CanonicalScalar], row_date: date
    ) -> None:
        if row_date < history_start or row_date > parsed_cutoff or row_date >= parsed_decision:
            raise ValueError("raw observation is outside the declared historical cutoff/range")
        identity_rows[table].append(key)
        binding_rows[table].append({"key": key, "values": values})
        observed_dates.append(row_date)

    allowed_symbols = set(query_scope.symbols)
    for price_row in snapshot.prices:
        if type(price_row) is not HistoricalPriceObservation:
            raise TypeError("prices contains an unsupported observation")
        symbol = _require_text(price_row.symbol, "price.symbol")
        if symbol != symbol.strip() or symbol not in allowed_symbols:
            raise ValueError("price symbol is outside normalized query scope")
        iso_day, parsed_day = _row_date(price_row.trading_date, "price.trading_date")
        add_row(
            "daily_prices",
            [symbol, iso_day],
            [
                _typed_decimal(price_row.open_price, "open_price"),
                _typed_decimal(price_row.high_price, "high_price"),
                _typed_decimal(price_row.low_price, "low_price"),
                _typed_decimal(price_row.close_price, "close_price"),
                _typed_integer(price_row.volume, "volume"),
                _typed_integer(price_row.turnover_amount_minor, "turnover_amount_minor"),
            ],
            parsed_day,
        )

    for technical_row in snapshot.technicals:
        if type(technical_row) is not HistoricalTechnicalObservation:
            raise TypeError("technicals contains an unsupported observation")
        symbol = _require_text(technical_row.symbol, "technical.symbol")
        if symbol != symbol.strip() or symbol not in allowed_symbols:
            raise ValueError("technical symbol is outside normalized query scope")
        iso_day, parsed_day = _row_date(technical_row.trading_date, "technical.trading_date")
        add_row(
            "technical_indicators",
            [symbol, iso_day],
            [
                _typed_decimal(technical_row.rsi, "rsi"),
                _typed_decimal(technical_row.macd, "macd"),
                _typed_decimal(technical_row.adx, "adx"),
            ],
            parsed_day,
        )

    for market_row in snapshot.market:
        if type(market_row) is not HistoricalIndexObservation:
            raise TypeError("market contains an unsupported observation")
        if market_row.index_name != "market":
            raise ValueError("market index name is not the provider's fixed market identity")
        iso_day, parsed_day = _row_date(market_row.trading_date, "market.trading_date")
        add_row(
            "market_indices",
            [market_row.index_name, iso_day],
            [_typed_decimal(market_row.close_value, "market.close_value")],
            parsed_day,
        )

    allowed_industries = set(query_scope.industry_index_names)
    for industry_row in snapshot.industries:
        if type(industry_row) is not HistoricalIndexObservation:
            raise TypeError("industries contains an unsupported observation")
        industry_name = _require_text(industry_row.index_name, "industry.index_name")
        if industry_name != industry_name.strip() or industry_name not in allowed_industries:
            raise ValueError("industry row is outside normalized query scope")
        iso_day, parsed_day = _row_date(industry_row.trading_date, "industry.trading_date")
        add_row(
            "industry_indices",
            [industry_name, iso_day],
            [_typed_decimal(industry_row.close_value, "industry.close_value")],
            parsed_day,
        )

    identity_payload = {
        "tables": [
            {
                "name": table,
                "keys": sorted(identity_rows[table], key=_serialized_sort_key),
            }
            for table in _SOURCE_TABLES
        ]
    }
    row_identity_hash = _domain_hash("raw-row-identity", identity_payload)
    content_payload = {
        "tables": [
            {
                "name": table,
                "rows": sorted(binding_rows[table], key=_serialized_sort_key),
            }
            for table in _SOURCE_TABLES
        ]
    }
    # Content covers complete key→value row records; row_identity_hash is the
    # separate key-only projection used to distinguish row identity changes.
    content_hash = _domain_hash("raw-row-content", content_payload)
    row_count = sum(counts.values())
    row_range_start = min(observed_dates) if observed_dates else None
    row_range_end = max(observed_dates) if observed_dates else None
    scope_payload = {
        "source_id": query_scope.source_id,
        "decision_date": decision_date,
        "history_start_date": history_start.isoformat(),
        "feature_as_of_date": cutoff_date,
        "symbols": list(query_scope.symbols),
        "industry_index_names": list(query_scope.industry_index_names),
    }
    snapshot_payload = {
        "scope": scope_payload,
        "schema_version": schema.schema_version,
        "content_hash": content_hash,
        "row_identity_hash": row_identity_hash,
        "table_row_counts": [[table, counts[table]] for table in _SOURCE_TABLES],
        "row_range_start": row_range_start.isoformat() if row_range_start else None,
        "row_range_end": row_range_end.isoformat() if row_range_end else None,
    }
    snapshot_digest = _domain_hash("raw-snapshot-identity", snapshot_payload)
    snapshot_id = f"{_FACTS_CONTRACT}:{snapshot_digest}"
    return HistoricalRawSnapshotCustodyFactsV1(
        query_scope=query_scope,
        feature_as_of_date=parsed_cutoff,
        validated_schema_version=schema.schema_version,
        content_hash=content_hash,
        row_identity_hash=row_identity_hash,
        snapshot_id=snapshot_id,
        row_count=row_count,
        table_row_counts=tuple((table, counts[table]) for table in _SOURCE_TABLES),
        row_range_start=row_range_start,
        row_range_end=row_range_end,
    )
