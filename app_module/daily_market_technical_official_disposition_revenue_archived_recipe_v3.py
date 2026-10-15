"""保存 F17 V2 查詢與其月營收 raw archive V4 的固定關聯。"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import NoReturn, cast

from app_module.daily_market_monthly_revenue_archive_reference_artifact_v4 import (
    DailyMarketMonthlyRevenueArchiveReferenceArtifactDescriptorV4,
    decode_daily_market_monthly_revenue_archive_reference_artifact_descriptor_v4,
)
from app_module.daily_market_monthly_revenue_reference_artifact_v3 import (
    DAILY_MARKET_MONTHLY_REVENUE_REFERENCE_ARTIFACT_DESCRIPTOR_V3_SCHEMA,
)
from app_module.daily_market_technical_official_disposition_revenue_source_v2 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_RECIPE_SCHEMA_V2,
    DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2,
)
from app_module.daily_market_technical_official_disposition_revenue_query_v2 import (
    DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2,
)
from data_module.daily_market_monthly_revenue_cohort_v2 import (
    DailyMarketMonthlyRevenueSourceReferenceV3,
    decode_daily_market_monthly_revenue_source_reference_v3,
)


DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_ARCHIVED_RECIPE_SCHEMA_V3 = (
    "daily-market-technical-official-disposition-revenue-archived-saved-recipe.v3"
)
_MAX_RECIPE_BYTES = 96 * 1024 * 1024
_MAX_JSON_DEPTH = 48
_MAX_EMBEDDED_RECIPE_BYTES = 64 * 1024 * 1024
_MAX_V3_DESCRIPTOR_BYTES = 4 * 1024 * 1024
_HEX = frozenset("0123456789abcdef")


class DailyMarketTechnicalOfficialDispositionRevenueArchivedRecipeV3Error(ValueError):
    """Archived recipe V3 的穩定拒絕錯誤。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"technical_official_revenue_archived_recipe_v3_{code}")


def _fail(code: str) -> NoReturn:
    raise DailyMarketTechnicalOfficialDispositionRevenueArchivedRecipeV3Error(code)


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise DailyMarketTechnicalOfficialDispositionRevenueArchivedRecipeV3Error(
            "canonical_json_invalid"
        ) from exc


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json_sha256(value: object) -> str:
    return _sha256(_canonical_bytes(value))


def _require_sha(value: object, code: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in _HEX for character in value)
    ):
        _fail(code)
    return cast(str, value)


def _depth_preflight(text: str) -> None:
    depth = 0
    quoted = False
    escaped = False
    for character in text:
        if quoted:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = False
        elif character == '"':
            quoted = True
        elif character in "[{":
            depth += 1
            if depth > _MAX_JSON_DEPTH:
                _fail("json_depth_limit")
        elif character in "]}":
            depth -= 1
            if depth < 0:
                _fail("json_invalid")
    if quoted or escaped or depth != 0:
        _fail("json_invalid")


def _parse_object(raw: bytes | str, *, label: str) -> dict[str, object]:
    try:
        if type(raw) is bytes:
            encoded = raw
        elif type(raw) is str:
            if len(raw) > _MAX_RECIPE_BYTES:
                _fail(f"{label}_size_invalid")
            encoded = raw.encode("utf-8", errors="strict")
        else:
            _fail(f"{label}_input_type_invalid")
        if not encoded or len(encoded) > _MAX_RECIPE_BYTES:
            _fail(f"{label}_size_invalid")
        text = encoded.decode("utf-8", errors="strict")
        _depth_preflight(text)

        def unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in pairs:
                if key in result:
                    _fail(f"{label}_duplicate_key")
                result[key] = value
            return result

        payload = json.loads(
            text,
            object_pairs_hook=unique_pairs,
            parse_float=lambda _value: _fail(f"{label}_float_forbidden"),
            parse_constant=lambda _value: _fail(f"{label}_constant_invalid"),
        )
        if type(payload) is not dict:
            _fail(f"{label}_object_required")
        if _canonical_bytes(payload) != encoded:
            _fail(f"{label}_noncanonical")
        return cast(dict[str, object], payload)
    except DailyMarketTechnicalOfficialDispositionRevenueArchivedRecipeV3Error:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalOfficialDispositionRevenueArchivedRecipeV3Error(
            f"{label}_json_invalid"
        ) from exc


def _ledger_sha256(ledger: tuple[tuple[str, str], ...]) -> str:
    return _json_sha256([list(item) for item in ledger])


def _source_reference(base: DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2) -> DailyMarketMonthlyRevenueSourceReferenceV3:
    try:
        decoded = decode_daily_market_monthly_revenue_source_reference_v3(
            base.monthly_source_reference_json,
            expected_reference_sha256=base.monthly_source_reference_external_sha256,
        )
    except (TypeError, ValueError) as exc:
        raise DailyMarketTechnicalOfficialDispositionRevenueArchivedRecipeV3Error(
            "base_source_reference_invalid"
        ) from exc
    return decoded.reference


def _descriptor_values_from_base(
    base: DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2,
) -> dict[str, object]:
    raw = base.artifact_descriptor_json.encode("utf-8", errors="strict")
    if len(raw) > _MAX_V3_DESCRIPTOR_BYTES or _sha256(raw) != base.artifact_descriptor_external_sha256:
        _fail("base_v3_descriptor_external_sha_mismatch")
    value = _parse_object(raw, label="base_v3_descriptor")
    expected_fields = {
        "schema_version", "artifact_schema_version", "artifact_id", "reference_relative_path",
        "descriptor_relative_path", "reference_size_bytes", "reference_sha256",
        "source_reference_identity_sha256", "index_identity_sha256", "read_session_identity_sha256",
        "source_clock_identity_sha256", "source_content_identity_sha256",
        "finished_cohort_identity_sha256", "cohort_sha256", "decision_cutoff",
        "declared_stock_codes", "declared_stock_codes_sha256", "result_ledger_sha256",
        "fact_ledger_sha256", "reader_result_status_counts", "fact_state_counts",
        "projected_state_counts", "source_scope", "availability_status", "complete",
        "historical_pit_eligible", "formal_pit_eligible",
    }
    if set(value) != expected_fields:
        _fail("base_v3_descriptor_fields_invalid")
    if (
        value.get("schema_version") != DAILY_MARKET_MONTHLY_REVENUE_REFERENCE_ARTIFACT_DESCRIPTOR_V3_SCHEMA
        or value.get("artifact_schema_version") != "daily-market-monthly-revenue-reference-artifact.v3"
    ):
        _fail("base_v3_descriptor_schema_invalid")
    return value


def _validate_cross_binding(
    *,
    base: DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2,
    descriptor: DailyMarketMonthlyRevenueArchiveReferenceArtifactDescriptorV4,
    archive_reference_sha256: str,
) -> None:
    try:
        base.to_dict()
        reference = _source_reference(base)
        original = _descriptor_values_from_base(base)
    except DailyMarketTechnicalOfficialDispositionRevenueArchivedRecipeV3Error:
        raise
    except (TypeError, ValueError, UnicodeError) as exc:
        raise DailyMarketTechnicalOfficialDispositionRevenueArchivedRecipeV3Error(
            "base_recipe_invalid"
        ) from exc

    cohort_pin_dict = reference.cohort_pin.to_dict()
    declared_codes = reference.declared_stock_codes
    result_ledger_sha = _ledger_sha256(reference.result_identity_by_stock)
    fact_ledger_sha = _ledger_sha256(reference.fact_identity_by_stock)
    expected_bindings = (
        descriptor.original_descriptor_sha256 == base.artifact_descriptor_external_sha256,
        descriptor.reference_sha256 == base.monthly_source_reference_external_sha256,
        descriptor.archive_reference_sha256 == archive_reference_sha256,
        descriptor.source_reference_identity_sha256 == reference.identity_sha256,
        descriptor.source_content_identity_sha256 == reference.source_content_identity_sha256,
        descriptor.finished_cohort_identity_sha256 == reference.finished_cohort_identity_sha256,
        descriptor.cohort_sha256 == reference.cohort_pin.cohort_sha256,
        descriptor.cohort_pin.to_dict() == cohort_pin_dict,
        descriptor.decision_cutoff == reference.decision_cutoff,
        descriptor.declared_stock_codes == declared_codes,
        descriptor.declared_stock_codes_sha256 == reference.declared_stock_codes_sha256,
        descriptor.result_ledger_sha256 == result_ledger_sha,
        descriptor.fact_ledger_sha256 == fact_ledger_sha,
        descriptor.reader_result_status_counts == reference.reader_result_status_counts,
        descriptor.fact_state_counts == reference.fact_state_counts,
        descriptor.source_scope == "current_observed_only",
        descriptor.availability_status == "cohort_hour_bound",
        descriptor.complete is True,
        descriptor.historical_pit_eligible is False,
        descriptor.formal_pit_eligible is False,
        original.get("reference_sha256") == base.monthly_source_reference_external_sha256,
        original.get("source_reference_identity_sha256") == reference.identity_sha256,
        original.get("reference_size_bytes")
        == len(base.monthly_source_reference_json.encode("utf-8", errors="strict")),
        original.get("source_content_identity_sha256") == reference.source_content_identity_sha256,
        original.get("finished_cohort_identity_sha256") == reference.finished_cohort_identity_sha256,
        original.get("cohort_sha256") == reference.cohort_pin.cohort_sha256,
        original.get("decision_cutoff") == reference.decision_cutoff,
        original.get("declared_stock_codes") == list(declared_codes),
        original.get("declared_stock_codes_sha256") == reference.declared_stock_codes_sha256,
        original.get("result_ledger_sha256") == result_ledger_sha,
        original.get("fact_ledger_sha256") == fact_ledger_sha,
        original.get("reader_result_status_counts") == [list(item) for item in reference.reader_result_status_counts],
        original.get("fact_state_counts") == [list(item) for item in reference.fact_state_counts],
        original.get("projected_state_counts")
        == [list(item) for item in descriptor.projected_state_counts],
        original.get("index_identity_sha256") == descriptor.index_identity_sha256,
        original.get("read_session_identity_sha256") == descriptor.read_session_identity_sha256,
        original.get("source_clock_identity_sha256") == descriptor.source_clock_identity_sha256,
        original.get("source_scope") == "current_observed_only",
        original.get("availability_status") == "cohort_hour_bound",
        original.get("complete") is True,
        original.get("historical_pit_eligible") is False,
        original.get("formal_pit_eligible") is False,
    )
    if not all(expected_bindings):
        _fail("archive_descriptor_base_recipe_binding_mismatch")


def _recipe_body_v3(recipe: DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3) -> dict[str, object]:
    return {
        "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_ARCHIVED_RECIPE_SCHEMA_V3,
        "base_recipe_v2_json": recipe.base_recipe_v2_json,
        "archive_artifact_descriptor_json": recipe.archive_artifact_descriptor_json,
        "archive_artifact_descriptor_external_sha256": recipe.archive_artifact_descriptor_external_sha256,
        "archive_reference_external_sha256": recipe.archive_reference_external_sha256,
    }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3:
    """Archived V3 codec；解析與 self-hash 不授予來源資格。"""

    base_recipe_v2_json: str
    archive_artifact_descriptor_json: str
    archive_artifact_descriptor_external_sha256: str
    archive_reference_external_sha256: str
    recipe_identity_sha256: str

    @classmethod
    def create(
        cls,
        base_recipe: DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2,
        archive_descriptor: DailyMarketMonthlyRevenueArchiveReferenceArtifactDescriptorV4,
        *,
        expected_archive_descriptor_sha256: str,
        expected_archive_reference_sha256: str,
    ) -> DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3:
        if type(base_recipe) is not DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2:
            _fail("base_recipe_v2_required")
        if type(archive_descriptor) is not DailyMarketMonthlyRevenueArchiveReferenceArtifactDescriptorV4:
            _fail("archive_descriptor_v4_required")
        if archive_descriptor.is_writer_issued is not True:
            _fail("archive_descriptor_not_writer_issued")
        expected_descriptor_sha = _require_sha(
            expected_archive_descriptor_sha256,
            "expected_archive_descriptor_sha_invalid",
        )
        expected_archive_sha = _require_sha(
            expected_archive_reference_sha256,
            "expected_archive_reference_sha_invalid",
        )
        try:
            base_json = base_recipe.to_json()
            descriptor_raw = archive_descriptor.to_bytes()
            descriptor_json = descriptor_raw.decode("utf-8", errors="strict")
        except (TypeError, ValueError, UnicodeError) as exc:
            raise DailyMarketTechnicalOfficialDispositionRevenueArchivedRecipeV3Error(
                "writer_input_invalid"
            ) from exc
        if (
            _sha256(descriptor_raw) != expected_descriptor_sha
            or archive_descriptor.external_descriptor_sha256 != expected_descriptor_sha
        ):
            _fail("archive_descriptor_external_sha_mismatch")
        try:
            checked_descriptor = decode_daily_market_monthly_revenue_archive_reference_artifact_descriptor_v4(
                descriptor_raw,
                expected_descriptor_sha,
            )
        except (TypeError, ValueError) as exc:
            raise DailyMarketTechnicalOfficialDispositionRevenueArchivedRecipeV3Error(
                "writer_v4_descriptor_decode_failed"
            ) from exc
        if checked_descriptor.to_dict() != archive_descriptor.to_dict():
            _fail("writer_v4_descriptor_serialization_mismatch")
        if checked_descriptor.archive_reference_sha256 != expected_archive_sha:
            _fail("archive_reference_external_sha_mismatch")
        _validate_cross_binding(
            base=base_recipe,
            descriptor=checked_descriptor,
            archive_reference_sha256=expected_archive_sha,
        )
        body = {
            "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_ARCHIVED_RECIPE_SCHEMA_V3,
            "base_recipe_v2_json": base_json,
            "archive_artifact_descriptor_json": descriptor_json,
            "archive_artifact_descriptor_external_sha256": expected_descriptor_sha,
            "archive_reference_external_sha256": expected_archive_sha,
        }
        return cls.from_dict({**body, "recipe_identity_sha256": _json_sha256(body)})

    @property
    def base_recipe(self) -> DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2:
        return DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2.from_json(
            self.base_recipe_v2_json
        )

    @property
    def archive_artifact_descriptor(self) -> DailyMarketMonthlyRevenueArchiveReferenceArtifactDescriptorV4:
        return decode_daily_market_monthly_revenue_archive_reference_artifact_descriptor_v4(
            self.archive_artifact_descriptor_json.encode("utf-8", errors="strict"),
            self.archive_artifact_descriptor_external_sha256,
        )

    def to_dict(self) -> dict[str, object]:
        body = _recipe_body_v3(self)
        if _json_sha256(body) != self.recipe_identity_sha256:
            _fail("recipe_identity_mismatch")
        _validate_recipe_v3(self)
        return {**body, "recipe_identity_sha256": self.recipe_identity_sha256}

    def to_json(self) -> str:
        raw = _canonical_bytes(self.to_dict())
        if len(raw) > _MAX_RECIPE_BYTES:
            _fail("recipe_size_invalid")
        return raw.decode("utf-8", errors="strict")

    @classmethod
    def from_dict(
        cls,
        value: object,
    ) -> DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3:
        expected = {
            "schema_version",
            "base_recipe_v2_json",
            "archive_artifact_descriptor_json",
            "archive_artifact_descriptor_external_sha256",
            "archive_reference_external_sha256",
            "recipe_identity_sha256",
        }
        if type(value) is not dict or set(value) != expected:
            _fail("recipe_fields_invalid")
        payload = cast(dict[str, object], value)
        if payload.get("schema_version") != DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_ARCHIVED_RECIPE_SCHEMA_V3:
            _fail("recipe_schema_unsupported")
        base_raw = payload.get("base_recipe_v2_json")
        descriptor_raw = payload.get("archive_artifact_descriptor_json")
        if (
            type(base_raw) is not str
            or not base_raw
            or len(base_raw) > _MAX_EMBEDDED_RECIPE_BYTES
            or type(descriptor_raw) is not str
            or not descriptor_raw
            or len(descriptor_raw) > _MAX_V3_DESCRIPTOR_BYTES
        ):
            _fail("recipe_nested_size_invalid")
        try:
            base_bytes = cast(str, base_raw).encode("utf-8", errors="strict")
            descriptor_bytes = cast(str, descriptor_raw).encode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise DailyMarketTechnicalOfficialDispositionRevenueArchivedRecipeV3Error(
                "recipe_nested_utf8_invalid"
            ) from exc
        if (
            len(base_bytes) > _MAX_EMBEDDED_RECIPE_BYTES
            or len(descriptor_bytes) > _MAX_V3_DESCRIPTOR_BYTES
        ):
            _fail("recipe_nested_size_invalid")
        recipe = cls(
            base_recipe_v2_json=cast(str, base_raw),
            archive_artifact_descriptor_json=cast(str, descriptor_raw),
            archive_artifact_descriptor_external_sha256=_require_sha(
                payload.get("archive_artifact_descriptor_external_sha256"),
                "recipe_descriptor_sha_invalid",
            ),
            archive_reference_external_sha256=_require_sha(
                payload.get("archive_reference_external_sha256"),
                "recipe_archive_reference_sha_invalid",
            ),
            recipe_identity_sha256=_require_sha(
                payload.get("recipe_identity_sha256"),
                "recipe_identity_invalid",
            ),
        )
        if _json_sha256(_recipe_body_v3(recipe)) != recipe.recipe_identity_sha256:
            _fail("recipe_identity_mismatch")
        _validate_recipe_v3(recipe)
        return recipe

    @classmethod
    def from_json(
        cls,
        raw: bytes | str,
    ) -> DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3:
        return cls.from_dict(_parse_object(raw, label="recipe"))

    def with_page(
        self,
        page_index: int,
        page_size: int,
    ) -> DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3:
        base = self.base_recipe
        try:
            old_request = DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2.from_json(
                base.page_request_json
            )
            request = DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2.create(
                old_request.query,
                page_index=page_index,
                page_size=page_size,
            )
        except (TypeError, ValueError) as exc:
            raise DailyMarketTechnicalOfficialDispositionRevenueArchivedRecipeV3Error(
                "page_request_invalid"
            ) from exc
        body = base.to_dict()
        body.pop("recipe_identity_sha256", None)
        body["page_request_json"] = request.to_json()
        body["page_index"] = request.page_index
        body["page_size"] = request.page_size
        inner_identity = _json_sha256(body)
        new_base = DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2.from_dict(
            {**body, "recipe_identity_sha256": inner_identity}
        )
        outer_body = {
            "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_ARCHIVED_RECIPE_SCHEMA_V3,
            "base_recipe_v2_json": new_base.to_json(),
            "archive_artifact_descriptor_json": self.archive_artifact_descriptor_json,
            "archive_artifact_descriptor_external_sha256": self.archive_artifact_descriptor_external_sha256,
            "archive_reference_external_sha256": self.archive_reference_external_sha256,
        }
        return DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3.from_dict(
            {**outer_body, "recipe_identity_sha256": _json_sha256(outer_body)}
        )


def _validate_recipe_v3(
    recipe: DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3,
) -> None:
    try:
        base = DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2.from_json(
            recipe.base_recipe_v2_json
        )
        descriptor_raw = recipe.archive_artifact_descriptor_json.encode(
            "utf-8", errors="strict"
        )
        if _sha256(descriptor_raw) != recipe.archive_artifact_descriptor_external_sha256:
            _fail("archive_descriptor_external_sha_mismatch")
        descriptor = decode_daily_market_monthly_revenue_archive_reference_artifact_descriptor_v4(
            descriptor_raw,
            recipe.archive_artifact_descriptor_external_sha256,
        )
        _validate_cross_binding(
            base=base,
            descriptor=descriptor,
            archive_reference_sha256=recipe.archive_reference_external_sha256,
        )
    except DailyMarketTechnicalOfficialDispositionRevenueArchivedRecipeV3Error:
        raise
    except (TypeError, ValueError, UnicodeError) as exc:
        raise DailyMarketTechnicalOfficialDispositionRevenueArchivedRecipeV3Error(
            "recipe_nested_payload_invalid"
        ) from exc


__all__ = [
    "DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_ARCHIVED_RECIPE_SCHEMA_V3",
    "DailyMarketTechnicalOfficialDispositionRevenueArchivedRecipeV3Error",
    "DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3",
]
