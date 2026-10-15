"""保存可攜 V3 月營收參照與 V2 raw archive bytes 的隔離 V4 artifact。"""

from __future__ import annotations

import base64
from pathlib import Path
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Sequence, cast

from app_module.daily_market_monthly_revenue_reference_artifact_v3 import (
    DAILY_MARKET_MONTHLY_REVENUE_REFERENCE_ARTIFACT_DESCRIPTOR_V3_SCHEMA,
    DAILY_MARKET_MONTHLY_REVENUE_REFERENCE_ARTIFACT_V3_SCHEMA,
    DailyMarketMonthlyRevenueReferenceArtifactDescriptorV3,
    UnverifiedDailyMarketMonthlyRevenueReferenceArtifactV3,
    _MAX_DESCRIPTOR_BYTES as _MAX_V3_DESCRIPTOR_BYTES,
    _MAX_REFERENCE_BYTES as _MAX_V3_REFERENCE_BYTES,
    _artifact_id as _v3_artifact_id,
    _canonical_json_bytes,
    _check_path_components,
    _create_only_write,
    _decode_json_object,
    _descriptor_from_bytes as _parse_v3_descriptor,
    _read_verified_file,
    _sha256,
    _validate_artifact_root,
    read_daily_market_monthly_revenue_reference_artifact_v3,
)
from app_module.daily_market_monthly_revenue_yoy_index_v2 import (
    DailyMarketMonthlyRevenueYoyIndexSessionV2,
)
from data_module.daily_market_monthly_revenue_cohort_v2 import (
    DAILY_MARKET_MONTHLY_REVENUE_SOURCE_REFERENCE_V3_SCHEMA,
    DailyMarketMonthlyRevenueSourceReferenceV3,
    UnverifiedDailyMarketMonthlyRevenueSourceReferenceV3,
    decode_daily_market_monthly_revenue_source_reference_v3,
)
from data_module.daily_monthly_revenue_cohort import (
    DailyMonthlyRevenueCohortPin,
    DailyMonthlyRevenueCohortReader,
)
from data_module.fundamental_read_snapshot_raw_archive_v2 import (
    FUNDAMENTAL_READ_SNAPSHOT_RAW_ARCHIVE_V2_SCHEMA,
    MAX_RAW_ARCHIVE_REFERENCE_JSON_BYTES,
    FundamentalReadSnapshotRawArchiveReferenceV2,
    UnverifiedFundamentalReadSnapshotRawArchiveReferenceV2,
    decode_raw_archive_reference_v2,
)
from data_module.fundamental_read_snapshot_raw_archive_io_v2 import (
    reverify_raw_archive_reference_v2,
    verify_raw_archive_reference_v2,
)
from data_module.recommendation_current_fundamental_provider import (
    RecommendationCurrentFundamentalProvider,
)


DAILY_MARKET_MONTHLY_REVENUE_ARCHIVE_REFERENCE_ARTIFACT_DESCRIPTOR_V4_SCHEMA = (
    "daily-market-monthly-revenue-archive-reference-artifact-descriptor.v4"
)
DAILY_MARKET_MONTHLY_REVENUE_ARCHIVE_REFERENCE_ARTIFACT_V4_SCHEMA = (
    "daily-market-monthly-revenue-archive-reference-artifact.v4"
)
_MAX_DESCRIPTOR_BYTES = 4 * 1024 * 1024
_MAX_ENVELOPE_BYTES = 128 * 1024 * 1024
_MAX_CODES = 100_000
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_ENVELOPE_FIELDS = frozenset(
    {
        "schema_version",
        "artifact_id",
        "original_descriptor_bytes_b64",
        "source_reference_bytes_b64",
        "archive_reference_bytes_b64",
    }
)
_DESCRIPTOR_FIELDS = frozenset(
    {
        "schema_version",
        "artifact_schema_version",
        "artifact_id",
        "envelope_relative_path",
        "descriptor_relative_path",
        "envelope_size_bytes",
        "envelope_sha256",
        "original_descriptor_sha256",
        "reference_sha256",
        "archive_reference_sha256",
        "source_reference_identity_sha256",
        "index_identity_sha256",
        "read_session_identity_sha256",
        "source_clock_identity_sha256",
        "source_content_identity_sha256",
        "finished_cohort_identity_sha256",
        "cohort_sha256",
        "cohort_pin",
        "decision_cutoff",
        "declared_stock_codes",
        "declared_stock_codes_sha256",
        "result_ledger_sha256",
        "fact_ledger_sha256",
        "reader_result_status_counts",
        "fact_state_counts",
        "projected_state_counts",
        "archive_identity_sha256",
        "archive_manifest_sha256",
        "source_scope",
        "availability_status",
        "complete",
        "historical_pit_eligible",
        "formal_pit_eligible",
    }
)


class DailyMarketMonthlyRevenueArchiveReferenceArtifactV4Error(ValueError):
    """V4 artifact 的外部錨、來源綁定、路徑或內容無效。"""


def _fail(code: str) -> DailyMarketMonthlyRevenueArchiveReferenceArtifactV4Error:
    return DailyMarketMonthlyRevenueArchiveReferenceArtifactV4Error(code)


def _require_sha(value: object, name: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise _fail(f"{name}_sha256_invalid")
    return cast(str, value)


def _ledger_hash(ledger: tuple[tuple[str, str], ...]) -> str:
    return _sha256(_canonical_json_bytes([list(item) for item in ledger]))


def _count_rows(value: object, *, label: str) -> tuple[tuple[str, int], ...]:
    if type(value) not in (tuple, list):
        raise _fail(f"{label}_invalid")
    rows = cast(tuple[object, ...] | list[object], value)
    if len(rows) > 8:
        raise _fail(f"{label}_invalid")
    result: list[tuple[str, int]] = []
    for row in rows:
        if type(row) not in (tuple, list):
            raise _fail(f"{label}_row_invalid")
        pair = cast(tuple[object, ...] | list[object], row)
        if (
            len(pair) != 2
            or type(pair[0]) is not str
            or not cast(str, pair[0])
            or type(pair[1]) is not int
            or cast(int, pair[1]) < 0
        ):
            raise _fail(f"{label}_row_invalid")
        result.append((cast(str, pair[0]), cast(int, pair[1])))
    normalized = tuple(result)
    if normalized != tuple(sorted(normalized)) or len({name for name, _ in normalized}) != len(normalized):
        raise _fail(f"{label}_not_canonical")
    return normalized


@dataclass(frozen=True, slots=True, init=False)
class DailyMarketMonthlyRevenueArchiveReferenceArtifactDescriptorV4:
    """V4 外層 descriptor；只有 publisher 才能發行 writer-issued instance。"""

    schema_version: str
    artifact_schema_version: str
    artifact_id: str
    envelope_relative_path: str
    descriptor_relative_path: str
    envelope_size_bytes: int
    envelope_sha256: str
    original_descriptor_sha256: str
    reference_sha256: str
    archive_reference_sha256: str
    source_reference_identity_sha256: str
    index_identity_sha256: str
    read_session_identity_sha256: str
    source_clock_identity_sha256: str
    source_content_identity_sha256: str
    finished_cohort_identity_sha256: str
    cohort_sha256: str
    cohort_pin: DailyMonthlyRevenueCohortPin
    decision_cutoff: str
    declared_stock_codes: tuple[str, ...]
    declared_stock_codes_sha256: str
    result_ledger_sha256: str
    fact_ledger_sha256: str
    reader_result_status_counts: tuple[tuple[str, int], ...]
    fact_state_counts: tuple[tuple[str, int], ...]
    projected_state_counts: tuple[tuple[str, int], ...]
    archive_identity_sha256: str
    archive_manifest_sha256: str
    source_scope: str
    availability_status: str
    complete: bool
    historical_pit_eligible: bool
    formal_pit_eligible: bool
    _writer_issued: bool

    def __init__(self) -> None:
        raise TypeError("V4 descriptor 只能由 publisher 或 pure decoder 建立")

    @classmethod
    def _from_values(
        cls,
        values: dict[str, object],
        *,
        writer_issued: bool,
    ) -> DailyMarketMonthlyRevenueArchiveReferenceArtifactDescriptorV4:
        result = object.__new__(cls)
        for name in (
            "schema_version",
            "artifact_schema_version",
            "artifact_id",
            "envelope_relative_path",
            "descriptor_relative_path",
            "envelope_size_bytes",
            "envelope_sha256",
            "original_descriptor_sha256",
            "reference_sha256",
            "archive_reference_sha256",
            "source_reference_identity_sha256",
            "index_identity_sha256",
            "read_session_identity_sha256",
            "source_clock_identity_sha256",
            "source_content_identity_sha256",
            "finished_cohort_identity_sha256",
            "cohort_sha256",
            "cohort_pin",
            "decision_cutoff",
            "declared_stock_codes",
            "declared_stock_codes_sha256",
            "result_ledger_sha256",
            "fact_ledger_sha256",
            "reader_result_status_counts",
            "fact_state_counts",
            "projected_state_counts",
            "archive_identity_sha256",
            "archive_manifest_sha256",
            "source_scope",
            "availability_status",
            "complete",
            "historical_pit_eligible",
            "formal_pit_eligible",
        ):
            object.__setattr__(result, name, values[name])
        object.__setattr__(result, "_writer_issued", writer_issued)
        return cast(DailyMarketMonthlyRevenueArchiveReferenceArtifactDescriptorV4, result)

    @property
    def is_writer_issued(self) -> bool:
        return self._writer_issued is True

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "artifact_schema_version": self.artifact_schema_version,
            "artifact_id": self.artifact_id,
            "envelope_relative_path": self.envelope_relative_path,
            "descriptor_relative_path": self.descriptor_relative_path,
            "envelope_size_bytes": self.envelope_size_bytes,
            "envelope_sha256": self.envelope_sha256,
            "original_descriptor_sha256": self.original_descriptor_sha256,
            "reference_sha256": self.reference_sha256,
            "archive_reference_sha256": self.archive_reference_sha256,
            "source_reference_identity_sha256": self.source_reference_identity_sha256,
            "index_identity_sha256": self.index_identity_sha256,
            "read_session_identity_sha256": self.read_session_identity_sha256,
            "source_clock_identity_sha256": self.source_clock_identity_sha256,
            "source_content_identity_sha256": self.source_content_identity_sha256,
            "finished_cohort_identity_sha256": self.finished_cohort_identity_sha256,
            "cohort_sha256": self.cohort_sha256,
            "cohort_pin": self.cohort_pin.to_dict(),
            "decision_cutoff": self.decision_cutoff,
            "declared_stock_codes": list(self.declared_stock_codes),
            "declared_stock_codes_sha256": self.declared_stock_codes_sha256,
            "result_ledger_sha256": self.result_ledger_sha256,
            "fact_ledger_sha256": self.fact_ledger_sha256,
            "reader_result_status_counts": [list(item) for item in self.reader_result_status_counts],
            "fact_state_counts": [list(item) for item in self.fact_state_counts],
            "projected_state_counts": [list(item) for item in self.projected_state_counts],
            "archive_identity_sha256": self.archive_identity_sha256,
            "archive_manifest_sha256": self.archive_manifest_sha256,
            "source_scope": self.source_scope,
            "availability_status": self.availability_status,
            "complete": self.complete,
            "historical_pit_eligible": self.historical_pit_eligible,
            "formal_pit_eligible": self.formal_pit_eligible,
        }

    def to_bytes(self) -> bytes:
        raw = _canonical_json_bytes(self.to_dict())
        if len(raw) > _MAX_DESCRIPTOR_BYTES:
            raise _fail("descriptor_size_exceeded")
        return raw

    def to_json(self) -> str:
        return self.to_bytes().decode("utf-8", errors="strict")

    @property
    def external_descriptor_sha256(self) -> str:
        return _sha256(self.to_bytes())


@dataclass(frozen=True, slots=True)
class UnverifiedDailyMarketMonthlyRevenueArchiveReferenceArtifactV4:
    """V4 envelope 的解析結果；不代表來源、raw archive 或 PIT 資格。"""

    source_reference: UnverifiedDailyMarketMonthlyRevenueSourceReferenceV3
    raw_archive_reference: UnverifiedFundamentalReadSnapshotRawArchiveReferenceV2
    original_descriptor: DailyMarketMonthlyRevenueReferenceArtifactDescriptorV3
    descriptor: DailyMarketMonthlyRevenueArchiveReferenceArtifactDescriptorV4
    external_descriptor_sha256: str

    def __post_init__(self) -> None:
        if type(self.source_reference) is not UnverifiedDailyMarketMonthlyRevenueSourceReferenceV3:
            raise _fail("unverified_source_reference_type_invalid")
        if type(self.raw_archive_reference) is not UnverifiedFundamentalReadSnapshotRawArchiveReferenceV2:
            raise _fail("unverified_archive_reference_type_invalid")
        if type(self.original_descriptor) is not DailyMarketMonthlyRevenueReferenceArtifactDescriptorV3:
            raise _fail("original_descriptor_type_invalid")
        if type(self.descriptor) is not DailyMarketMonthlyRevenueArchiveReferenceArtifactDescriptorV4:
            raise _fail("descriptor_type_invalid")
        _require_sha(self.external_descriptor_sha256, "external_descriptor")


def _descriptor_from_values(
    payload: dict[str, object],
    *,
    writer_issued: bool,
) -> DailyMarketMonthlyRevenueArchiveReferenceArtifactDescriptorV4:
    if set(payload) != _DESCRIPTOR_FIELDS:
        raise _fail("descriptor_fields_invalid")
    if payload.get("schema_version") != DAILY_MARKET_MONTHLY_REVENUE_ARCHIVE_REFERENCE_ARTIFACT_DESCRIPTOR_V4_SCHEMA:
        raise _fail("descriptor_schema_unsupported")
    if payload.get("artifact_schema_version") != DAILY_MARKET_MONTHLY_REVENUE_ARCHIVE_REFERENCE_ARTIFACT_V4_SCHEMA:
        raise _fail("descriptor_artifact_schema_unsupported")
    try:
        artifact_id = _v3_artifact_id(payload.get("artifact_id"))
    except ValueError as exc:
        raise _fail("descriptor_artifact_id_invalid") from exc
    if (
        payload.get("envelope_relative_path") != f"{artifact_id}.archive-reference.v4.json"
        or payload.get("descriptor_relative_path") != f"{artifact_id}.descriptor.v4.json"
    ):
        raise _fail("descriptor_paths_invalid")
    size = payload.get("envelope_size_bytes")
    if type(size) is not int or size <= 0 or size > _MAX_ENVELOPE_BYTES:
        raise _fail("descriptor_envelope_size_invalid")
    for name in (
        "envelope_sha256",
        "original_descriptor_sha256",
        "reference_sha256",
        "archive_reference_sha256",
        "source_reference_identity_sha256",
        "index_identity_sha256",
        "read_session_identity_sha256",
        "source_clock_identity_sha256",
        "source_content_identity_sha256",
        "finished_cohort_identity_sha256",
        "cohort_sha256",
        "declared_stock_codes_sha256",
        "result_ledger_sha256",
        "fact_ledger_sha256",
        "archive_identity_sha256",
        "archive_manifest_sha256",
    ):
        _require_sha(payload.get(name), f"descriptor_{name}")
    raw_pin = payload.get("cohort_pin")
    try:
        pin = DailyMonthlyRevenueCohortPin.from_dict(raw_pin)
    except (TypeError, ValueError) as exc:
        raise _fail("descriptor_full_cohort_pin_invalid") from exc
    if pin.cohort_sha256 != payload.get("cohort_sha256"):
        raise _fail("descriptor_full_cohort_pin_sha_mismatch")
    raw_codes_value = payload.get("declared_stock_codes")
    if type(raw_codes_value) not in (list, tuple):
        raise _fail("descriptor_declared_codes_invalid")
    raw_codes = cast(list[object] | tuple[object, ...], raw_codes_value)
    if (
        not raw_codes
        or len(raw_codes) > _MAX_CODES
        or any(type(code) is not str or re.fullmatch(r"[A-Za-z0-9]{1,6}", code) is None for code in raw_codes)
    ):
        raise _fail("descriptor_declared_codes_invalid")
    codes = tuple(cast(str, item) for item in raw_codes)
    if codes != tuple(sorted(set(codes))) or _sha256(_canonical_json_bytes(list(codes))) != payload.get("declared_stock_codes_sha256"):
        raise _fail("descriptor_declared_codes_binding_mismatch")
    cutoff = payload.get("decision_cutoff")
    if type(cutoff) is not str or not cutoff or len(cutoff) > 64:
        raise _fail("descriptor_cutoff_invalid")
    try:
        parsed_cutoff = datetime.fromisoformat(cutoff)
    except ValueError as exc:
        raise _fail("descriptor_cutoff_invalid") from exc
    if (
        parsed_cutoff.tzinfo is None
        or parsed_cutoff.utcoffset() is None
        or parsed_cutoff.isoformat() != cutoff
        or pin.available_hour.astimezone(timezone.utc)
        > parsed_cutoff.astimezone(timezone.utc)
    ):
        raise _fail("descriptor_cutoff_or_cohort_hour_invalid")
    count_values: dict[str, tuple[tuple[str, int], ...]] = {}
    for name in ("reader_result_status_counts", "fact_state_counts", "projected_state_counts"):
        counts = _count_rows(payload.get(name), label=f"descriptor_{name}")
        if sum(number for _, number in counts) != len(codes):
            raise _fail(f"descriptor_{name}_denominator_mismatch")
        count_values[name] = counts
    if (
        payload.get("source_scope") != "current_observed_only"
        or payload.get("availability_status") != "cohort_hour_bound"
        or payload.get("complete") is not True
        or payload.get("historical_pit_eligible") is not False
        or payload.get("formal_pit_eligible") is not False
    ):
        raise _fail("descriptor_source_policy_invalid")
    values = dict(payload)
    values.update(
        {
            "artifact_id": artifact_id,
            "cohort_pin": pin,
            "declared_stock_codes": codes,
            **count_values,
        }
    )
    return DailyMarketMonthlyRevenueArchiveReferenceArtifactDescriptorV4._from_values(
        values,
        writer_issued=writer_issued,
    )


def _descriptor_from_bytes(
    raw: bytes,
    *,
    writer_issued: bool,
) -> DailyMarketMonthlyRevenueArchiveReferenceArtifactDescriptorV4:
    payload = _decode_json_object(raw, label="v4_descriptor", maximum=_MAX_DESCRIPTOR_BYTES)
    parsed = _descriptor_from_values(payload, writer_issued=writer_issued)
    if parsed.to_bytes() != raw:
        raise _fail("descriptor_not_canonical")
    return parsed


def decode_daily_market_monthly_revenue_archive_reference_artifact_descriptor_v4(
    raw: bytes,
    expected_descriptor_sha256: str,
) -> DailyMarketMonthlyRevenueArchiveReferenceArtifactDescriptorV4:
    """解析外部 SHA 錨定的 descriptor，不發行 reader 或 writer 資格。"""

    expected = _require_sha(expected_descriptor_sha256, "expected_descriptor")
    if type(raw) is not bytes or len(raw) > _MAX_DESCRIPTOR_BYTES or _sha256(raw) != expected:
        raise _fail("external_descriptor_sha_mismatch")
    return _descriptor_from_bytes(raw, writer_issued=False)


def _encode_envelope(
    *,
    artifact_id: str,
    original_descriptor_raw: bytes,
    source_reference_raw: bytes,
    archive_reference_raw: bytes,
) -> bytes:
    payload = {
        "schema_version": DAILY_MARKET_MONTHLY_REVENUE_ARCHIVE_REFERENCE_ARTIFACT_V4_SCHEMA,
        "artifact_id": artifact_id,
        "original_descriptor_bytes_b64": base64.b64encode(original_descriptor_raw).decode("ascii"),
        "source_reference_bytes_b64": base64.b64encode(source_reference_raw).decode("ascii"),
        "archive_reference_bytes_b64": base64.b64encode(archive_reference_raw).decode("ascii"),
    }
    raw = _canonical_json_bytes(payload)
    if len(raw) > _MAX_ENVELOPE_BYTES:
        raise _fail("envelope_size_exceeded")
    return raw


def _decode_envelope(raw: bytes, *, expected_artifact_id: str) -> tuple[bytes, bytes, bytes]:
    payload = _decode_json_object(raw, label="v4_envelope", maximum=_MAX_ENVELOPE_BYTES)
    if _canonical_json_bytes(payload) != raw:
        raise _fail("envelope_not_canonical")
    if (
        set(payload) != _ENVELOPE_FIELDS
        or payload.get("schema_version") != DAILY_MARKET_MONTHLY_REVENUE_ARCHIVE_REFERENCE_ARTIFACT_V4_SCHEMA
        or payload.get("artifact_id") != expected_artifact_id
    ):
        raise _fail("envelope_fields_or_identity_invalid")
    decoded: list[bytes] = []
    for field_name in (
        "original_descriptor_bytes_b64",
        "source_reference_bytes_b64",
        "archive_reference_bytes_b64",
    ):
        value = payload.get(field_name)
        if type(value) is not str or len(value) > 96 * 1024 * 1024:
            raise _fail(f"envelope_{field_name}_invalid")
        try:
            item = base64.b64decode(value.encode("ascii", errors="strict"), validate=True)
        except (ValueError, UnicodeError) as exc:
            raise _fail(f"envelope_{field_name}_invalid") from exc
        if base64.b64encode(item).decode("ascii") != value:
            raise _fail(f"envelope_{field_name}_not_canonical_base64")
        decoded.append(item)
    if len(decoded[0]) > _MAX_V3_DESCRIPTOR_BYTES:
        raise _fail("embedded_v3_descriptor_size_exceeded")
    if len(decoded[1]) > _MAX_V3_REFERENCE_BYTES:
        raise _fail("embedded_v3_reference_size_exceeded")
    if len(decoded[2]) > MAX_RAW_ARCHIVE_REFERENCE_JSON_BYTES:
        raise _fail("embedded_raw_archive_reference_size_exceeded")
    return decoded[0], decoded[1], decoded[2]


def _validate_binding(
    *,
    descriptor: DailyMarketMonthlyRevenueArchiveReferenceArtifactDescriptorV4,
    original_descriptor: DailyMarketMonthlyRevenueReferenceArtifactDescriptorV3,
    source_reference: UnverifiedDailyMarketMonthlyRevenueSourceReferenceV3,
    archive_reference: UnverifiedFundamentalReadSnapshotRawArchiveReferenceV2,
    original_descriptor_raw: bytes,
    source_reference_raw: bytes,
    archive_reference_raw: bytes,
) -> None:
    reference = source_reference.reference
    archive = archive_reference.reference
    upstream = reference.upstream_reference
    clock = archive.source_clock
    if (
        original_descriptor.schema_version != DAILY_MARKET_MONTHLY_REVENUE_REFERENCE_ARTIFACT_DESCRIPTOR_V3_SCHEMA
        or original_descriptor.artifact_schema_version != DAILY_MARKET_MONTHLY_REVENUE_REFERENCE_ARTIFACT_V3_SCHEMA
        or _sha256(original_descriptor_raw) != descriptor.original_descriptor_sha256
        or original_descriptor.external_descriptor_sha256 != descriptor.original_descriptor_sha256
        or source_reference.external_reference_sha256 != descriptor.reference_sha256
        or _sha256(source_reference_raw) != descriptor.reference_sha256
        or original_descriptor.reference_sha256 != descriptor.reference_sha256
        or original_descriptor.reference_size_bytes != len(source_reference_raw)
        or archive_reference.external_reference_sha256 != descriptor.archive_reference_sha256
        or _sha256(archive_reference_raw) != descriptor.archive_reference_sha256
        or reference.schema_version != DAILY_MARKET_MONTHLY_REVENUE_SOURCE_REFERENCE_V3_SCHEMA
        or reference.identity_sha256 != descriptor.source_reference_identity_sha256
        or reference.upstream_reference != archive.snapshot_reference
        or reference.upstream_reference_sha256 != archive.snapshot_reference_sha256
        or reference.source_content_identity_sha256 != descriptor.source_content_identity_sha256
        or reference.finished_cohort_identity_sha256 != descriptor.finished_cohort_identity_sha256
        or reference.cohort_pin != descriptor.cohort_pin
        or reference.cohort_pin.cohort_sha256 != descriptor.cohort_sha256
        or reference.decision_cutoff != descriptor.decision_cutoff
        or reference.declared_stock_codes != descriptor.declared_stock_codes
        or reference.declared_stock_codes_sha256 != descriptor.declared_stock_codes_sha256
        or _ledger_hash(reference.result_identity_by_stock) != descriptor.result_ledger_sha256
        or _ledger_hash(reference.fact_identity_by_stock) != descriptor.fact_ledger_sha256
        or reference.reader_result_status_counts != descriptor.reader_result_status_counts
        or reference.fact_state_counts != descriptor.fact_state_counts
        or reference.source_scope != descriptor.source_scope
        or reference.availability_status != descriptor.availability_status
        or reference.historical_pit_eligible is not descriptor.historical_pit_eligible
        or reference.formal_pit_eligible is not descriptor.formal_pit_eligible
        or original_descriptor.source_reference_identity_sha256 != reference.identity_sha256
        or original_descriptor.index_identity_sha256 != descriptor.index_identity_sha256
        or original_descriptor.read_session_identity_sha256 != descriptor.read_session_identity_sha256
        or original_descriptor.source_clock_identity_sha256 != descriptor.source_clock_identity_sha256
        or original_descriptor.source_content_identity_sha256 != reference.source_content_identity_sha256
        or original_descriptor.finished_cohort_identity_sha256 != reference.finished_cohort_identity_sha256
        or original_descriptor.cohort_sha256 != reference.cohort_pin.cohort_sha256
        or original_descriptor.decision_cutoff != reference.decision_cutoff
        or original_descriptor.declared_stock_codes != reference.declared_stock_codes
        or original_descriptor.declared_stock_codes_sha256 != reference.declared_stock_codes_sha256
        or original_descriptor.result_ledger_sha256 != descriptor.result_ledger_sha256
        or original_descriptor.fact_ledger_sha256 != descriptor.fact_ledger_sha256
        or original_descriptor.reader_result_status_counts != reference.reader_result_status_counts
        or original_descriptor.fact_state_counts != reference.fact_state_counts
        or original_descriptor.projected_state_counts != descriptor.projected_state_counts
        or original_descriptor.source_scope != "current_observed_only"
        or original_descriptor.availability_status != "cohort_hour_bound"
        or original_descriptor.complete is not True
        or original_descriptor.historical_pit_eligible is not False
        or original_descriptor.formal_pit_eligible is not False
        or clock.identity_sha256 != descriptor.source_clock_identity_sha256
        or clock.identity_sha256 != upstream.source_clock_identity_sha256
        or clock.source_content_identity_sha256 != upstream.source_content_identity_sha256
        or clock.cohort_sha256 != upstream.daily_cohort_sha256
        or clock.cohort_pin != descriptor.cohort_pin
        or clock.decision_cutoff.isoformat() != descriptor.decision_cutoff
        or clock.declared_stock_codes != descriptor.declared_stock_codes
        or clock.source_scope != "current_observed_only"
        or clock.availability_status != "cohort_hour_bound"
        or clock.historical_pit_eligible is not False
        or clock.formal_pit_eligible is not False
        or archive.schema_version != FUNDAMENTAL_READ_SNAPSHOT_RAW_ARCHIVE_V2_SCHEMA
        or archive.source_scope != "current_observed_only"
        or archive.availability_status != "cohort_hour_bound"
        or archive.historical_pit_eligible is not False
        or archive.formal_pit_eligible is not False
        or archive.archive_identity_sha256 != descriptor.archive_identity_sha256
        or archive.archive_manifest_sha256 != descriptor.archive_manifest_sha256
        or upstream.source_content_identity_sha256 != reference.upstream_reference.source_content_identity_sha256
        or upstream.decision_cutoff != descriptor.decision_cutoff
        or upstream.declared_stock_codes != descriptor.declared_stock_codes
        or upstream.declared_stock_codes_sha256 != descriptor.declared_stock_codes_sha256
        or upstream.daily_cohort_sha256 != descriptor.cohort_sha256
    ):
        raise _fail("v4_descriptor_embedded_sources_binding_mismatch")


def _index_values(
    *,
    artifact_id: str,
    envelope_raw: bytes,
    original_descriptor_raw: bytes,
    source_reference: DailyMarketMonthlyRevenueSourceReferenceV3,
    index: object,
    archive_reference: FundamentalReadSnapshotRawArchiveReferenceV2,
    archive_reference_sha256: str,
) -> dict[str, object]:
    source_clock = getattr(index, "source_clock", None)
    index_identity = getattr(index, "index_identity_sha256", None)
    read_session_identity = getattr(index, "read_session_identity_sha256", None)
    if (
        source_clock is None
        or type(index_identity) is not str
        or type(read_session_identity) is not str
        or source_clock.identity_sha256
        != source_reference.upstream_reference.source_clock_identity_sha256
    ):
        raise _fail("index_source_clock_or_identity_mismatch")
    return {
        "schema_version": DAILY_MARKET_MONTHLY_REVENUE_ARCHIVE_REFERENCE_ARTIFACT_DESCRIPTOR_V4_SCHEMA,
        "artifact_schema_version": DAILY_MARKET_MONTHLY_REVENUE_ARCHIVE_REFERENCE_ARTIFACT_V4_SCHEMA,
        "artifact_id": artifact_id,
        "envelope_relative_path": f"{artifact_id}.archive-reference.v4.json",
        "descriptor_relative_path": f"{artifact_id}.descriptor.v4.json",
        "envelope_size_bytes": len(envelope_raw),
        "envelope_sha256": _sha256(envelope_raw),
        "original_descriptor_sha256": _sha256(original_descriptor_raw),
        "reference_sha256": source_reference.external_reference_sha256,
        "archive_reference_sha256": archive_reference_sha256,
        "source_reference_identity_sha256": source_reference.identity_sha256,
        "index_identity_sha256": index_identity,
        "read_session_identity_sha256": read_session_identity,
        "source_clock_identity_sha256": source_clock.identity_sha256,
        "source_content_identity_sha256": source_reference.source_content_identity_sha256,
        "finished_cohort_identity_sha256": source_reference.finished_cohort_identity_sha256,
        "cohort_sha256": source_reference.cohort_pin.cohort_sha256,
        "cohort_pin": source_reference.cohort_pin.to_dict(),
        "decision_cutoff": source_reference.decision_cutoff,
        "declared_stock_codes": list(source_reference.declared_stock_codes),
        "declared_stock_codes_sha256": source_reference.declared_stock_codes_sha256,
        "result_ledger_sha256": _ledger_hash(source_reference.result_identity_by_stock),
        "fact_ledger_sha256": _ledger_hash(source_reference.fact_identity_by_stock),
        "reader_result_status_counts": [
            list(item) for item in source_reference.reader_result_status_counts
        ],
        "fact_state_counts": [list(item) for item in source_reference.fact_state_counts],
        "projected_state_counts": [
            list(item)
            for item in _count_rows(
                getattr(index, "projected_state_counts", None),
                label="projected_state_counts",
            )
        ],
        "archive_identity_sha256": archive_reference.archive_identity_sha256,
        "archive_manifest_sha256": archive_reference.archive_manifest_sha256,
        "source_scope": source_reference.source_scope,
        "availability_status": source_reference.availability_status,
        "complete": getattr(index, "complete", None),
        "historical_pit_eligible": source_reference.historical_pit_eligible,
        "formal_pit_eligible": source_reference.formal_pit_eligible,
    }


def _build_envelope_components(
    *,
    descriptor: DailyMarketMonthlyRevenueArchiveReferenceArtifactDescriptorV4,
    envelope_raw: bytes,
    original_descriptor_raw: bytes | None = None,
    source_reference_raw: bytes | None = None,
    archive_reference_raw: bytes | None = None,
) -> UnverifiedDailyMarketMonthlyRevenueArchiveReferenceArtifactV4:
    embedded_descriptor_raw, embedded_reference_raw, embedded_archive_raw = _decode_envelope(
        envelope_raw,
        expected_artifact_id=descriptor.artifact_id,
    )
    if (
        len(envelope_raw) != descriptor.envelope_size_bytes
        or _sha256(envelope_raw) != descriptor.envelope_sha256
        or (original_descriptor_raw is not None and embedded_descriptor_raw != original_descriptor_raw)
        or (source_reference_raw is not None and embedded_reference_raw != source_reference_raw)
        or (archive_reference_raw is not None and embedded_archive_raw != archive_reference_raw)
    ):
        raise _fail("envelope_size_or_sha_mismatch")
    try:
        original_descriptor = _parse_v3_descriptor(embedded_descriptor_raw)
        source_reference = decode_daily_market_monthly_revenue_source_reference_v3(
            embedded_reference_raw,
            expected_reference_sha256=descriptor.reference_sha256,
        )
        raw_archive_reference = decode_raw_archive_reference_v2(
            embedded_archive_raw,
            expected_reference_sha256=descriptor.archive_reference_sha256,
        )
    except (TypeError, ValueError) as exc:
        raise _fail("embedded_reference_decode_failed") from exc
    _validate_binding(
        descriptor=descriptor,
        original_descriptor=original_descriptor,
        source_reference=source_reference,
        archive_reference=raw_archive_reference,
        original_descriptor_raw=embedded_descriptor_raw,
        source_reference_raw=embedded_reference_raw,
        archive_reference_raw=embedded_archive_raw,
    )
    return UnverifiedDailyMarketMonthlyRevenueArchiveReferenceArtifactV4(
        source_reference=source_reference,
        raw_archive_reference=raw_archive_reference,
        original_descriptor=original_descriptor,
        descriptor=descriptor,
        external_descriptor_sha256=descriptor.external_descriptor_sha256,
    )


def _read_original_v3(
    original_artifact_root: Path,
    *,
    original_descriptor: DailyMarketMonthlyRevenueReferenceArtifactDescriptorV3 | bytes,
    expected_original_descriptor_sha256: str,
    protected_roots: Sequence[Path],
) -> tuple[
    UnverifiedDailyMarketMonthlyRevenueReferenceArtifactV3,
    bytes,
    bytes,
    tuple[int, ...],
    tuple[int, ...],
]:
    original_raw: bytes
    if type(original_descriptor) is DailyMarketMonthlyRevenueReferenceArtifactDescriptorV3:
        if original_descriptor.is_writer_issued is not True:
            raise _fail("original_v3_descriptor_not_writer_issued")
        original_raw = original_descriptor.to_bytes()
    elif type(original_descriptor) is bytes:
        original_raw = original_descriptor
    else:
        raise _fail("original_v3_descriptor_type_invalid")
    expected = _require_sha(expected_original_descriptor_sha256, "original_descriptor")
    if len(original_raw) > _MAX_V3_DESCRIPTOR_BYTES or _sha256(original_raw) != expected:
        raise _fail("original_v3_descriptor_external_sha_mismatch")
    try:
        checked = read_daily_market_monthly_revenue_reference_artifact_v3(
            original_artifact_root,
            descriptor=original_raw,
            expected_descriptor_sha256=expected,
            protected_roots=protected_roots,
        )
    except (TypeError, ValueError, OSError) as exc:
        raise _fail("original_v3_artifact_readback_failed") from exc
    parsed = checked.descriptor
    root = _validate_artifact_root(original_artifact_root, protected_roots=protected_roots)
    _check_path_components(root, require_directory=True)
    descriptor_path = root / parsed.descriptor_relative_path
    reference_path = root / parsed.reference_relative_path
    disk_descriptor, descriptor_signature = _read_verified_file(
        descriptor_path,
        label="original_v3_descriptor",
        maximum=_MAX_V3_DESCRIPTOR_BYTES,
    )
    source_reference_raw, reference_signature = _read_verified_file(
        reference_path,
        label="original_v3_source_reference",
        maximum=_MAX_V3_REFERENCE_BYTES,
    )
    if (
        disk_descriptor != original_raw
        or source_reference_raw != checked.source_reference.reference.to_json().encode("utf-8")
        or _sha256(source_reference_raw) != parsed.reference_sha256
    ):
        raise _fail("original_v3_embedded_bytes_not_exact_readback")
    return checked, original_raw, source_reference_raw, descriptor_signature, reference_signature


def publish_daily_market_monthly_revenue_archive_reference_artifact_v4(
    root: Path,
    *,
    artifact_id: str,
    index_session: DailyMarketMonthlyRevenueYoyIndexSessionV2,
    original_artifact_root: Path,
    original_descriptor: DailyMarketMonthlyRevenueReferenceArtifactDescriptorV3 | bytes,
    expected_original_descriptor_sha256: str,
    raw_archive_reference: FundamentalReadSnapshotRawArchiveReferenceV2,
    expected_archive_reference_sha256: str,
    monthly_provider: RecommendationCurrentFundamentalProvider,
    daily_monthly_cohort_reader: DailyMonthlyRevenueCohortReader,
    protected_roots: Sequence[Path],
    cancel_callback: Callable[[], bool] | None = None,
) -> DailyMarketMonthlyRevenueArchiveReferenceArtifactDescriptorV4:
    """以兩個 create-only 檔封存 V3 參照、原始 descriptor 與 V2 raw archive bytes。"""

    try:
        selected_root = _validate_artifact_root(root, protected_roots=protected_roots)
        selected_id = _v3_artifact_id(artifact_id)
        if type(monthly_provider) is not RecommendationCurrentFundamentalProvider:
            raise _fail("monthly_provider_type_invalid")
        if type(daily_monthly_cohort_reader) is not DailyMonthlyRevenueCohortReader:
            raise _fail("daily_monthly_cohort_reader_type_invalid")
        if type(index_session) is not DailyMarketMonthlyRevenueYoyIndexSessionV2:
            raise _fail("reader_issued_index_session_required")
        if type(raw_archive_reference) is not FundamentalReadSnapshotRawArchiveReferenceV2:
            raise _fail("typed_raw_archive_reference_required")
        if cancel_callback is not None and not callable(cancel_callback):
            raise _fail("cancel_callback_invalid")
        _check_cancel_v4(cancel_callback)
        index, reference, reference_raw = _verify_v3_writer_inputs(index_session)
        v3_read, original_raw, persisted_reference_raw, v3_descriptor_signature, v3_reference_signature = _read_original_v3(
            original_artifact_root,
            original_descriptor=original_descriptor,
            expected_original_descriptor_sha256=expected_original_descriptor_sha256,
            protected_roots=protected_roots,
        )
        if (
            v3_read.source_reference.reference != reference
            or v3_read.source_reference.external_reference_sha256 != _sha256(reference_raw)
            or persisted_reference_raw != reference_raw
        ):
            raise _fail("v3_artifact_and_reader_issued_index_mismatch")
        archive_raw = raw_archive_reference.to_json().encode("utf-8", errors="strict")
        expected_archive_sha = _require_sha(expected_archive_reference_sha256, "archive_reference")
        if _sha256(archive_raw) != expected_archive_sha:
            raise _fail("raw_archive_reference_external_sha_mismatch")
        try:
            archive_unverified = decode_raw_archive_reference_v2(
                archive_raw,
                expected_reference_sha256=expected_archive_sha,
            )
            verified_archive = verify_raw_archive_reference_v2(
                archive_unverified.reference,
                expected_reference_sha256=expected_archive_sha,
                provider=monthly_provider,
                daily_monthly_cohort_reader=daily_monthly_cohort_reader,
                cancel_callback=cancel_callback,
            )
        except Exception as exc:
            raise _fail("raw_archive_physical_verification_failed") from exc
        if verified_archive.archive_reference != raw_archive_reference:
            raise _fail("raw_archive_verified_subject_changed")
        archive_root = Path(raw_archive_reference.archive_root)
        protected_source_paths = (
            archive_root,
            Path(raw_archive_reference.archived_snapshot_root),
            Path(raw_archive_reference.archived_monthly_source_root),
            monthly_provider.output_root,
            monthly_provider.monthly_source_root,
            Path(monthly_provider.db_file).parent,
        )
        if any(_paths_overlap(selected_root, path) for path in protected_source_paths):
            raise _fail("v4_output_overlaps_raw_archive_root")
        envelope_raw = _encode_envelope(
            artifact_id=selected_id,
            original_descriptor_raw=original_raw,
            source_reference_raw=reference_raw,
            archive_reference_raw=archive_raw,
        )
        values = _index_values(
            artifact_id=selected_id,
            envelope_raw=envelope_raw,
            original_descriptor_raw=original_raw,
            source_reference=reference,
            index=index,
            archive_reference=raw_archive_reference,
            archive_reference_sha256=expected_archive_sha,
        )
        descriptor = _descriptor_from_values(values, writer_issued=True)
        _validate_binding(
            descriptor=descriptor,
            original_descriptor=v3_read.descriptor,
            source_reference=v3_read.source_reference,
            archive_reference=archive_unverified,
            original_descriptor_raw=original_raw,
            source_reference_raw=reference_raw,
            archive_reference_raw=archive_raw,
        )
        descriptor_raw = descriptor.to_bytes()
        envelope_path = selected_root / descriptor.envelope_relative_path
        descriptor_path = selected_root / descriptor.descriptor_relative_path
        _verify_pair_inventory(selected_root, selected_id)
        if envelope_path.exists() or descriptor_path.exists():
            raise _fail("artifact_create_only_collision")
        envelope_signature: tuple[int, ...] | None = None
        descriptor_signature: tuple[int, ...] | None = None
        try:
            _check_cancel_v4(cancel_callback)
            _check_path_components(selected_root, require_directory=True)
            envelope_signature = _create_only_write(
                envelope_path,
                envelope_raw,
                label="v4_envelope",
                cancel_callback=cancel_callback,
            )
            _check_cancel_v4(cancel_callback)
            disk_envelope, checked_envelope_signature = _read_verified_file(
                envelope_path,
                label="v4_envelope_readback",
                maximum=_MAX_ENVELOPE_BYTES,
            )
            if disk_envelope != envelope_raw or checked_envelope_signature != envelope_signature:
                raise _fail("v4_envelope_readback_mismatch")
            # 寫入最後的 descriptor 前，重驗所有仍須存在的原始來源。
            _check_cancel_v4(cancel_callback)
            rechecked_index, rechecked_reference, rechecked_reference_raw = _verify_v3_writer_inputs(index_session)
            rechecked_v3, rechecked_original_raw, rechecked_persisted_reference_raw, rechecked_descriptor_signature, rechecked_v3_reference_signature = _read_original_v3(
                original_artifact_root,
                original_descriptor=original_raw,
                expected_original_descriptor_sha256=expected_original_descriptor_sha256,
                protected_roots=protected_roots,
            )
            if (
                rechecked_index is not index
                or rechecked_reference != reference
                or rechecked_reference_raw != reference_raw
                or rechecked_v3.source_reference.reference != reference
                or rechecked_original_raw != original_raw
                or rechecked_persisted_reference_raw != persisted_reference_raw
                or rechecked_descriptor_signature != v3_descriptor_signature
                or rechecked_v3_reference_signature != v3_reference_signature
            ):
                raise _fail("v3_inputs_changed_before_descriptor_commit")
            current_archive = reverify_raw_archive_reference_v2(
                verified_archive,
                provider=monthly_provider,
                daily_monthly_cohort_reader=daily_monthly_cohort_reader,
                cancel_callback=cancel_callback,
            )
            if current_archive != verified_archive:
                raise _fail("raw_archive_changed_before_descriptor_commit")
            _check_cancel_v4(cancel_callback)
            descriptor_signature = _create_only_write(
                descriptor_path,
                descriptor_raw,
                label="v4_descriptor",
                cancel_callback=cancel_callback,
            )
            _check_cancel_v4(cancel_callback)
            disk_descriptor, checked_descriptor_signature = _read_verified_file(
                descriptor_path,
                label="v4_descriptor_readback",
                maximum=_MAX_DESCRIPTOR_BYTES,
            )
            disk_envelope, checked_envelope_signature = _read_verified_file(
                envelope_path,
                label="v4_envelope_readback_final",
                maximum=_MAX_ENVELOPE_BYTES,
            )
            if (
                disk_descriptor != descriptor_raw
                or disk_envelope != envelope_raw
                or checked_descriptor_signature != descriptor_signature
                or checked_envelope_signature != envelope_signature
            ):
                raise _fail("v4_publish_readback_mismatch")
            _verify_pair_inventory(selected_root, selected_id)
            _build_envelope_components(
                descriptor=_descriptor_from_bytes(descriptor_raw, writer_issued=False),
                envelope_raw=disk_envelope,
                original_descriptor_raw=original_raw,
                source_reference_raw=reference_raw,
                archive_reference_raw=archive_raw,
            )
            _check_cancel_v4(cancel_callback)
            final_index, final_reference, final_reference_raw = _verify_v3_writer_inputs(index_session)
            final_v3, final_original_raw, final_persisted_reference_raw, final_v3_descriptor_signature, final_v3_reference_signature = _read_original_v3(
                original_artifact_root,
                original_descriptor=original_raw,
                expected_original_descriptor_sha256=expected_original_descriptor_sha256,
                protected_roots=protected_roots,
            )
            if (
                final_index is not index
                or final_reference != reference
                or final_reference_raw != reference_raw
                or final_v3.source_reference.reference != reference
                or final_original_raw != original_raw
                or final_persisted_reference_raw != persisted_reference_raw
                or final_v3_descriptor_signature != v3_descriptor_signature
                or final_v3_reference_signature != v3_reference_signature
            ):
                raise _fail("v3_inputs_changed_after_v4_write")
            final_archive = reverify_raw_archive_reference_v2(
                verified_archive,
                provider=monthly_provider,
                daily_monthly_cohort_reader=daily_monthly_cohort_reader,
                cancel_callback=cancel_callback,
            )
            if final_archive != verified_archive:
                raise _fail("raw_archive_changed_after_v4_write")
            _check_path_components(selected_root, require_directory=True)
            return descriptor
        except BaseException:
            _cleanup_v4(envelope_path, envelope_signature)
            _cleanup_v4(descriptor_path, descriptor_signature)
            raise
    except DailyMarketMonthlyRevenueArchiveReferenceArtifactV4Error:
        raise
    except Exception as exc:
        raise _fail(f"publish_failed:{type(exc).__name__}") from exc


def _verify_v3_writer_inputs(
    index_session: DailyMarketMonthlyRevenueYoyIndexSessionV2,
) -> tuple[object, DailyMarketMonthlyRevenueSourceReferenceV3, bytes]:
    from app_module.daily_market_monthly_revenue_reference_artifact_v3 import _verify_writer_inputs

    try:
        index, reference, raw = _verify_writer_inputs(index_session)
    except (TypeError, ValueError) as exc:
        raise _fail("reader_issued_v3_index_verification_failed") from exc
    if type(reference) is not DailyMarketMonthlyRevenueSourceReferenceV3:
        raise _fail("reader_issued_v3_source_reference_required")
    return index, reference, raw


def _check_cancel_v4(callback: Callable[[], bool] | None) -> None:
    if callback is None:
        return
    try:
        value = callback()
    except Exception as exc:
        raise _fail("cancel_callback_failed") from exc
    if type(value) is not bool:
        raise _fail("cancel_callback_must_return_bool")
    if value:
        raise _fail("operation_cancelled")


def _verify_pair_inventory(root: Path, artifact_id: str) -> None:
    expected = {
        f"{artifact_id}.archive-reference.v4.json",
        f"{artifact_id}.descriptor.v4.json",
    }
    prefix = f"{artifact_id}."
    try:
        matching = {child.name for child in root.iterdir() if child.name.startswith(prefix)}
    except OSError as exc:
        raise _fail("artifact_inventory_unavailable") from exc
    if not matching.issubset(expected):
        raise _fail("artifact_inventory_contains_unexpected_entry")


def _paths_overlap(left: Path, right: Path) -> bool:
    try:
        left.relative_to(right)
        return True
    except ValueError:
        pass
    try:
        right.relative_to(left)
        return True
    except ValueError:
        return False


def _cleanup_v4(path: Path, signature: tuple[int, ...] | None) -> None:
    if signature is None:
        return
    from app_module.daily_market_monthly_revenue_reference_artifact_v3 import _cleanup_owned

    _cleanup_owned(path, signature)


def read_daily_market_monthly_revenue_archive_reference_artifact_v4(
    root: Path,
    *,
    descriptor: DailyMarketMonthlyRevenueArchiveReferenceArtifactDescriptorV4 | bytes,
    expected_descriptor_sha256: str,
    protected_roots: Sequence[Path],
) -> UnverifiedDailyMarketMonthlyRevenueArchiveReferenceArtifactV4:
    """只讀 V4 自含 envelope；不開舊 V3 root、DB 或 archived snapshot。"""

    try:
        selected_root = _validate_artifact_root(root, protected_roots=protected_roots)
        expected = _require_sha(expected_descriptor_sha256, "external_descriptor")
        if type(descriptor) is DailyMarketMonthlyRevenueArchiveReferenceArtifactDescriptorV4:
            descriptor_raw = descriptor.to_bytes()
        elif type(descriptor) is bytes:
            descriptor_raw = descriptor
        else:
            raise _fail("descriptor_input_type_invalid")
        if len(descriptor_raw) > _MAX_DESCRIPTOR_BYTES or _sha256(descriptor_raw) != expected:
            raise _fail("external_descriptor_sha_mismatch")
        parsed = _descriptor_from_bytes(descriptor_raw, writer_issued=False)
        envelope_path = selected_root / parsed.envelope_relative_path
        descriptor_path = selected_root / parsed.descriptor_relative_path
        _verify_pair_inventory(selected_root, parsed.artifact_id)
        _check_path_components(selected_root, require_directory=True)
        disk_descriptor, descriptor_signature = _read_verified_file(
            descriptor_path,
            label="v4_descriptor",
            maximum=_MAX_DESCRIPTOR_BYTES,
        )
        if disk_descriptor != descriptor_raw or _sha256(disk_descriptor) != expected:
            raise _fail("persisted_v4_descriptor_external_anchor_mismatch")
        _check_path_components(selected_root, require_directory=True)
        envelope_raw, envelope_signature = _read_verified_file(
            envelope_path,
            label="v4_envelope",
            maximum=_MAX_ENVELOPE_BYTES,
        )
        result = _build_envelope_components(
            descriptor=parsed,
            envelope_raw=envelope_raw,
        )
        if (
            _check_file_v4(descriptor_path) != descriptor_signature
            or _check_file_v4(envelope_path) != envelope_signature
        ):
            raise _fail("v4_artifact_changed_after_read")
        _verify_pair_inventory(selected_root, parsed.artifact_id)
        _check_path_components(selected_root, require_directory=True)
        return UnverifiedDailyMarketMonthlyRevenueArchiveReferenceArtifactV4(
            source_reference=result.source_reference,
            raw_archive_reference=result.raw_archive_reference,
            original_descriptor=result.original_descriptor,
            descriptor=parsed,
            external_descriptor_sha256=expected,
        )
    except DailyMarketMonthlyRevenueArchiveReferenceArtifactV4Error:
        raise
    except Exception as exc:
        raise _fail(f"read_failed:{type(exc).__name__}") from exc


def _check_file_v4(path: Path) -> tuple[int, ...]:
    from app_module.daily_market_monthly_revenue_reference_artifact_v3 import _check_file

    return _check_file(path, "v4_artifact_file")


__all__ = [
    "DAILY_MARKET_MONTHLY_REVENUE_ARCHIVE_REFERENCE_ARTIFACT_DESCRIPTOR_V4_SCHEMA",
    "DAILY_MARKET_MONTHLY_REVENUE_ARCHIVE_REFERENCE_ARTIFACT_V4_SCHEMA",
    "DailyMarketMonthlyRevenueArchiveReferenceArtifactV4Error",
    "DailyMarketMonthlyRevenueArchiveReferenceArtifactDescriptorV4",
    "UnverifiedDailyMarketMonthlyRevenueArchiveReferenceArtifactV4",
    "decode_daily_market_monthly_revenue_archive_reference_artifact_descriptor_v4",
    "publish_daily_market_monthly_revenue_archive_reference_artifact_v4",
    "read_daily_market_monthly_revenue_archive_reference_artifact_v4",
]
