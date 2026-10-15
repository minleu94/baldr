"""月營收 V2 複合研究收藏；JSON 本身不構成來源驗證資格。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import hashlib
import json
import re
from typing import NoReturn, cast

from app_module.daily_market_technical_official_disposition_revenue_query_v2 import (
    DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2,
    DailyMarketTechnicalOfficialDispositionRevenueQueryPageV2,
    DailyMarketTechnicalOfficialDispositionRevenueQueryV2,
    DailyMarketTechnicalOfficialDispositionRevenueResultRowV2,
)
from app_module.daily_market_technical_official_disposition_revenue_source_v2 import (
    DailyMarketTechnicalOfficialDispositionRevenueExactReadV2,
    DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2,
)
from data_module.daily_market_monthly_revenue_cohort_v2 import (
    DailyMarketMonthlyRevenueSourceReferenceV3,
    decode_daily_market_monthly_revenue_source_reference_v3,
)


DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_BOOKMARK_SCHEMA_V2 = (
    "daily-market-technical-official-disposition-revenue-bookmark.v2"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_BOOKMARK_SOURCE_V2 = (
    "technical_official_disposition_revenue_research_bookmark_v2"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_BOOKMARK_MAX_BYTES_V2 = 64 * 1024 * 1024
_MAX_JSON_DEPTH = 32
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STOCK_CODE_RE = re.compile(r"^[A-Z0-9]{1,16}$")


class DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2Error(ValueError):
    """月營收 V2 收藏的穩定拒絕碼。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"technical_official_disposition_revenue_bookmark_v2_{code}")


def _fail(code: str) -> NoReturn:
    raise DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2Error(code)


def _canonical_bytes(value: object) -> bytes:
    def reject(item: object, depth: int) -> None:
        if depth > _MAX_JSON_DEPTH:
            _fail("json_depth_limit")
        if isinstance(item, float):
            _fail("json_float_forbidden")
        if isinstance(item, Mapping):
            for key, child in item.items():
                if not isinstance(key, str):
                    _fail("json_key_invalid")
                reject(child, depth + 1)
        elif isinstance(item, (list, tuple)):
            for child in item:
                reject(child, depth + 1)

    reject(value, 0)
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2Error(
            "json_invalid"
        ) from exc


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _preflight_depth(text: str) -> None:
    depth = 0
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > _MAX_JSON_DEPTH:
                _fail("json_depth_limit")
        elif char in "]}":
            depth -= 1
            if depth < 0:
                _fail("json_invalid")
    if in_string or depth != 0:
        _fail("json_invalid")


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail("json_duplicate_key")
        result[key] = value
    return result


def _parse_json(raw: str | bytes) -> object:
    if isinstance(raw, bytes):
        if len(raw) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_BOOKMARK_MAX_BYTES_V2:
            _fail("json_byte_limit")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2Error(
                "json_encoding_invalid"
            ) from exc
    elif isinstance(raw, str):
        if len(raw.encode("utf-8")) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_BOOKMARK_MAX_BYTES_V2:
            _fail("json_byte_limit")
        text = raw
    else:
        _fail("json_type_invalid")
    _preflight_depth(text)
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_pairs,
            parse_constant=lambda _value: _fail("json_nonfinite_invalid"),
        )
    except DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2Error:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2Error(
            "json_invalid"
        ) from exc
    if _canonical_bytes(value) != text.encode("utf-8"):
        _fail("json_noncanonical")
    return value


def _validate_stock_code(value: object) -> str:
    if type(value) is not str or _STOCK_CODE_RE.fullmatch(value) is None:
        _fail("stock_code_invalid")
    return cast(str, value)


def _validate_sha(value: object, code: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        _fail(code)
    return cast(str, value)


def _row_fact_context_v2(
    row: DailyMarketTechnicalOfficialDispositionRevenueResultRowV2,
    *,
    monthly_reference: DailyMarketMonthlyRevenueSourceReferenceV3,
) -> dict[str, object]:
    """保存穩定來源事實；reference/operation/query/page SHA 屬發行錨點。"""

    return {
        "stock_code": row.stock_code,
        "f17_fact": row.fact_row.to_dict(),
        "technical_row": None if row.technical_row is None else row.technical_row.to_dict(),
        "ma_entry": None if row.ma_entry is None else row.ma_entry.to_dict(),
        "monthly_source_fact": row.monthly_entry.source_fact.to_dict(),
        "monthly_projected_fact": row.monthly_entry.projected_fact.to_dict(),
        "monthly_source_content_identity_sha256": monthly_reference.source_content_identity_sha256,
        "monthly_decision_cutoff": monthly_reference.decision_cutoff,
        "monthly_declared_stock_codes": list(monthly_reference.declared_stock_codes),
        "monthly_cohort_pin": monthly_reference.cohort_pin.to_dict(),
        "monthly_result_identity_by_stock": [
            list(item) for item in monthly_reference.result_identity_by_stock
        ],
        "monthly_fact_identity_by_stock": [
            list(item) for item in monthly_reference.fact_identity_by_stock
        ],
        "monthly_reader_result_status_counts": [
            list(item) for item in monthly_reference.reader_result_status_counts
        ],
        "monthly_fact_state_counts": [
            list(item) for item in monthly_reference.fact_state_counts
        ],
        "filter_evaluation": {
            "row_scope": row.filter_evaluation.row_scope,
            "row_scope_match": row.filter_evaluation.row_scope_match,
            "stock_filter_match": row.filter_evaluation.stock_filter_match,
            "market_assignment_match": row.filter_evaluation.market_assignment_match,
            "market_assignment_truth": row.filter_evaluation.market_assignment_truth,
            "official_disposal_match": row.filter_evaluation.official_disposal_match,
            "official_disposal_truth": row.filter_evaluation.official_disposal_truth,
        },
        "technical_condition_truth": row.technical_condition_truth,
        "ma_condition_truth": row.ma_condition_truth,
        "revenue_condition_truth": row.revenue_condition_truth,
        "composite_condition_truth": row.composite_condition_truth,
        "hard_filter_match": row.hard_filter_match,
        "included_by_unknown_policy": row.included_by_unknown_policy,
        "scope": "current_only",
        "official_available_at": None,
        "monthly_official_available_at": None,
        "availability_status": "unknown",
        "monthly_availability_status": "cohort_hour_bound",
        "historical_pit_eligible": False,
    }


def _bookmark_body_v2(
    *,
    saved_recipe_json: str,
    selected_page_request_json: str,
    selected_stock_code: str,
    selected_stock_name: str,
    selected_result_identity_sha256: str,
    selected_query_identity_sha256: str,
    selected_row_identity_sha256: str,
    selected_fact_context_json: str,
    selected_fact_context_identity_sha256: str,
    monthly_source_reference_external_sha256: str,
    artifact_descriptor_external_sha256: str,
) -> dict[str, object]:
    return {
        "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_BOOKMARK_SCHEMA_V2,
        "saved_recipe_json": saved_recipe_json,
        "selected_page_request_json": selected_page_request_json,
        "selected_stock_code": selected_stock_code,
        "selected_stock_name": selected_stock_name,
        "selected_result_identity_sha256": selected_result_identity_sha256,
        "selected_query_identity_sha256": selected_query_identity_sha256,
        "selected_row_identity_sha256": selected_row_identity_sha256,
        "selected_fact_context_json": selected_fact_context_json,
        "selected_fact_context_identity_sha256": selected_fact_context_identity_sha256,
        "monthly_source_reference_external_sha256": monthly_source_reference_external_sha256,
        "artifact_descriptor_external_sha256": artifact_descriptor_external_sha256,
        "source_scope": "current_only",
        "availability_status": "unknown",
        "monthly_availability_status": "cohort_hour_bound",
        "historical_pit_eligible": False,
        "bookmark_is_reader_qualification": False,
    }


def _validate_context_v2(
    raw: str,
    *,
    stock_code: str,
    monthly_reference: DailyMarketMonthlyRevenueSourceReferenceV3,
) -> dict[str, object]:
    value = _parse_json(raw)
    required = {
        "stock_code", "f17_fact", "technical_row", "ma_entry", "monthly_source_fact",
        "monthly_projected_fact", "monthly_source_content_identity_sha256",
        "monthly_decision_cutoff", "monthly_declared_stock_codes", "monthly_cohort_pin",
        "monthly_result_identity_by_stock", "monthly_fact_identity_by_stock",
        "monthly_reader_result_status_counts", "monthly_fact_state_counts",
        "filter_evaluation", "technical_condition_truth", "ma_condition_truth",
        "revenue_condition_truth", "composite_condition_truth", "hard_filter_match",
        "included_by_unknown_policy", "scope", "official_available_at",
        "monthly_official_available_at", "availability_status",
        "monthly_availability_status", "historical_pit_eligible",
    }
    if (
        not isinstance(value, Mapping)
        or set(value) != required
        or value.get("stock_code") != stock_code
        or value.get("monthly_source_content_identity_sha256")
        != monthly_reference.source_content_identity_sha256
        or value.get("monthly_decision_cutoff") != monthly_reference.decision_cutoff
        or value.get("monthly_declared_stock_codes")
        != list(monthly_reference.declared_stock_codes)
        or value.get("monthly_cohort_pin") != monthly_reference.cohort_pin.to_dict()
        or value.get("monthly_result_identity_by_stock")
        != [list(item) for item in monthly_reference.result_identity_by_stock]
        or value.get("monthly_fact_identity_by_stock")
        != [list(item) for item in monthly_reference.fact_identity_by_stock]
        or value.get("monthly_reader_result_status_counts")
        != [list(item) for item in monthly_reference.reader_result_status_counts]
        or value.get("monthly_fact_state_counts")
        != [list(item) for item in monthly_reference.fact_state_counts]
        or value.get("scope") != "current_only"
        or value.get("availability_status") != "unknown"
        or value.get("monthly_availability_status") != "cohort_hour_bound"
        or value.get("official_available_at") is not None
        or value.get("monthly_official_available_at") is not None
        or value.get("historical_pit_eligible") is not False
        or type(value.get("hard_filter_match")) is not bool
        or value.get("hard_filter_match") is not True
        or type(value.get("included_by_unknown_policy")) is not bool
        or not isinstance(value.get("filter_evaluation"), Mapping)
    ):
        _fail("fact_context_invalid")
    return dict(value)


def _verify_recipe_query_semantics_v2(
    recipe: DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2,
    query: DailyMarketTechnicalOfficialDispositionRevenueQueryV2,
) -> None:
    saved_query = DailyMarketTechnicalOfficialDispositionRevenueQueryV2.from_json(
        recipe.revenue_query_json
    )
    if (
        saved_query.f17_query.to_json() != query.f17_query.to_json()
        or saved_query.ma_query.ma_states != query.ma_query.ma_states
        or saved_query.minimum_yoy_percent != query.minimum_yoy_percent
        or saved_query.condition_combine_mode != query.condition_combine_mode
        or saved_query.unknown_policy != query.unknown_policy
        or saved_query.sort_clauses != query.sort_clauses
        or saved_query.monthly_source_content_identity_sha256
        != query.monthly_source_content_identity_sha256
        or saved_query.monthly_cohort_sha256 != query.monthly_cohort_sha256
        or saved_query.monthly_availability_status != query.monthly_availability_status
    ):
        _fail("recipe_query_context_mismatch")


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2:
    """V2 Watchlist 研究收藏；fresh exact 驗證重比穩定事實，不比 operation ids。"""

    saved_recipe_json: str
    selected_page_request_json: str
    selected_stock_code: str
    selected_stock_name: str
    selected_result_identity_sha256: str
    selected_query_identity_sha256: str
    selected_row_identity_sha256: str
    selected_fact_context_json: str
    selected_fact_context_identity_sha256: str
    monthly_source_reference_external_sha256: str
    artifact_descriptor_external_sha256: str
    bookmark_identity_sha256: str
    schema_version: str = DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_BOOKMARK_SCHEMA_V2

    def __post_init__(self) -> None:
        if self.schema_version != DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_BOOKMARK_SCHEMA_V2:
            _fail("schema_unsupported")
        code = _validate_stock_code(self.selected_stock_code)
        if type(self.selected_stock_name) is not str or self.selected_stock_name != code:
            _fail("stock_name_invalid")
        for value, code_name in (
            (self.selected_result_identity_sha256, "result_identity_invalid"),
            (self.selected_query_identity_sha256, "query_identity_invalid"),
            (self.selected_row_identity_sha256, "row_identity_invalid"),
            (self.selected_fact_context_identity_sha256, "fact_context_identity_invalid"),
            (self.monthly_source_reference_external_sha256, "monthly_reference_sha_invalid"),
            (self.artifact_descriptor_external_sha256, "artifact_descriptor_sha_invalid"),
            (self.bookmark_identity_sha256, "bookmark_identity_invalid"),
        ):
            _validate_sha(value, code_name)
        recipe = DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2.from_json(
            self.saved_recipe_json
        )
        request = DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2.from_json(
            self.selected_page_request_json
        )
        if (
            recipe.to_json() != self.saved_recipe_json
            or request.to_json() != self.selected_page_request_json
            or request.page_index != recipe.page_index
            or request.page_size != recipe.page_size
            or request.query.query_identity_sha256 != self.selected_query_identity_sha256
            or request.query.to_json() != recipe.revenue_query_json
            or recipe.monthly_source_reference_external_sha256
            != self.monthly_source_reference_external_sha256
            or recipe.artifact_descriptor_external_sha256
            != self.artifact_descriptor_external_sha256
        ):
            _fail("recipe_page_or_anchor_context_mismatch")
        source_reference_wrapper = decode_daily_market_monthly_revenue_source_reference_v3(
            recipe.monthly_source_reference_json,
            expected_reference_sha256=recipe.monthly_source_reference_external_sha256,
        )
        source_reference = source_reference_wrapper.reference
        context = _validate_context_v2(
            self.selected_fact_context_json,
            stock_code=code,
            monthly_reference=source_reference,
        )
        if _canonical_bytes(context).decode("utf-8") != self.selected_fact_context_json:
            _fail("fact_context_noncanonical")
        if _sha256(context) != self.selected_fact_context_identity_sha256:
            _fail("fact_context_identity_mismatch")
        body = _bookmark_body_v2(
            saved_recipe_json=self.saved_recipe_json,
            selected_page_request_json=self.selected_page_request_json,
            selected_stock_code=code,
            selected_stock_name=self.selected_stock_name,
            selected_result_identity_sha256=self.selected_result_identity_sha256,
            selected_query_identity_sha256=self.selected_query_identity_sha256,
            selected_row_identity_sha256=self.selected_row_identity_sha256,
            selected_fact_context_json=self.selected_fact_context_json,
            selected_fact_context_identity_sha256=self.selected_fact_context_identity_sha256,
            monthly_source_reference_external_sha256=self.monthly_source_reference_external_sha256,
            artifact_descriptor_external_sha256=self.artifact_descriptor_external_sha256,
        )
        if _sha256(body) != self.bookmark_identity_sha256:
            _fail("bookmark_identity_mismatch")
        if len(_canonical_bytes(self.to_dict())) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_BOOKMARK_MAX_BYTES_V2:
            _fail("byte_limit")

    @classmethod
    def from_exact_read(
        cls,
        exact_read: DailyMarketTechnicalOfficialDispositionRevenueExactReadV2,
        stock_code: str,
    ) -> DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2:
        if type(exact_read) is not DailyMarketTechnicalOfficialDispositionRevenueExactReadV2:
            _fail("exact_read_invalid")
        return cls.from_issued_result_page(
            recipe=exact_read.saved_recipe,
            page_request=exact_read.page_request,
            page=exact_read.page,
            stock_code=_validate_stock_code(stock_code),
        )

    @classmethod
    def from_issued_result_page(
        cls,
        *,
        recipe: DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2,
        page_request: DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2,
        page: DailyMarketTechnicalOfficialDispositionRevenueQueryPageV2,
        stock_code: str,
    ) -> DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2:
        if type(recipe) is not DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2:
            _fail("saved_recipe_invalid")
        if type(page_request) is not DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2:
            _fail("page_request_invalid")
        if type(page) is not DailyMarketTechnicalOfficialDispositionRevenueQueryPageV2:
            _fail("page_invalid")
        code = _validate_stock_code(stock_code)
        recipe.to_json()
        request_json = page_request.to_json()
        page_dict = page.to_dict()
        query = page.query
        recipe_query = DailyMarketTechnicalOfficialDispositionRevenueQueryV2.from_json(
            recipe.revenue_query_json
        )
        if (
            page_request.query.query_identity_sha256 != query.query_identity_sha256
            or page_request.request_identity_sha256 != page.request_identity_sha256
            or page_request.page_index != page.page_index
            or page_request.page_size != page.page_size
            or request_json != recipe.page_request_json
            or page_request.page_index != recipe.page_index
            or page_request.page_size != recipe.page_size
            or recipe_query.to_json() != query.to_json()
            or page_dict.get("operation_identity_sha256") != page.operation_identity_sha256
            or page_dict.get("query_identity_sha256") != query.query_identity_sha256
        ):
            _fail("issued_page_context_mismatch")
        row = next((item for item in page.rows if item.stock_code == code), None)
        if type(row) is not DailyMarketTechnicalOfficialDispositionRevenueResultRowV2:
            _fail("selected_stock_not_on_issued_page")
        if row.hard_filter_match is not True:
            _fail("selected_stock_hard_filtered")
        page_rows = page_dict.get("rows")
        if type(page_rows) is not list or not any(
            isinstance(item, Mapping)
            and item.get("stock_code") == code
            and item.get("row_identity_sha256") == row.row_identity_sha256
            for item in page_rows
        ):
            _fail("issued_row_context_mismatch")
        _verify_recipe_query_semantics_v2(recipe, query)
        reference_sha = recipe.monthly_source_reference_external_sha256
        descriptor_sha = recipe.artifact_descriptor_external_sha256
        context = _row_fact_context_v2(
            row,
            monthly_reference=decode_daily_market_monthly_revenue_source_reference_v3(
                recipe.monthly_source_reference_json,
                expected_reference_sha256=recipe.monthly_source_reference_external_sha256,
            ).reference,
        )
        context_json = _canonical_bytes(context).decode("utf-8")
        body = _bookmark_body_v2(
            saved_recipe_json=recipe.to_json(),
            selected_page_request_json=request_json,
            selected_stock_code=code,
            selected_stock_name=code,
            selected_result_identity_sha256=page.operation_identity_sha256,
            selected_query_identity_sha256=query.query_identity_sha256,
            selected_row_identity_sha256=row.row_identity_sha256,
            selected_fact_context_json=context_json,
            selected_fact_context_identity_sha256=_sha256(context),
            monthly_source_reference_external_sha256=reference_sha,
            artifact_descriptor_external_sha256=descriptor_sha,
        )
        return cls(
            saved_recipe_json=recipe.to_json(),
            selected_page_request_json=request_json,
            selected_stock_code=code,
            selected_stock_name=code,
            selected_result_identity_sha256=page.operation_identity_sha256,
            selected_query_identity_sha256=query.query_identity_sha256,
            selected_row_identity_sha256=row.row_identity_sha256,
            selected_fact_context_json=context_json,
            selected_fact_context_identity_sha256=_sha256(context),
            monthly_source_reference_external_sha256=reference_sha,
            artifact_descriptor_external_sha256=descriptor_sha,
            bookmark_identity_sha256=_sha256(body),
        )

    @classmethod
    def from_dict(
        cls,
        payload: object,
    ) -> DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2:
        expected = {
            "schema_version", "saved_recipe_json", "selected_page_request_json",
            "selected_stock_code", "selected_stock_name", "selected_result_identity_sha256",
            "selected_query_identity_sha256", "selected_row_identity_sha256",
            "selected_fact_context_json", "selected_fact_context_identity_sha256",
            "monthly_source_reference_external_sha256", "artifact_descriptor_external_sha256",
            "source_scope", "availability_status", "monthly_availability_status",
            "historical_pit_eligible", "bookmark_is_reader_qualification",
            "bookmark_identity_sha256", "source",
        }
        if not isinstance(payload, Mapping) or set(payload) != expected:
            _fail("fields_invalid")
        if (
            payload.get("source") != DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_BOOKMARK_SOURCE_V2
            or payload.get("source_scope") != "current_only"
            or payload.get("availability_status") != "unknown"
            or payload.get("monthly_availability_status") != "cohort_hour_bound"
            or payload.get("historical_pit_eligible") is not False
            or payload.get("bookmark_is_reader_qualification") is not False
        ):
            _fail("qualification_invalid")
        result = cls(
            saved_recipe_json=cast(str, payload.get("saved_recipe_json")),
            selected_page_request_json=cast(str, payload.get("selected_page_request_json")),
            selected_stock_code=cast(str, payload.get("selected_stock_code")),
            selected_stock_name=cast(str, payload.get("selected_stock_name")),
            selected_result_identity_sha256=cast(str, payload.get("selected_result_identity_sha256")),
            selected_query_identity_sha256=cast(str, payload.get("selected_query_identity_sha256")),
            selected_row_identity_sha256=cast(str, payload.get("selected_row_identity_sha256")),
            selected_fact_context_json=cast(str, payload.get("selected_fact_context_json")),
            selected_fact_context_identity_sha256=cast(str, payload.get("selected_fact_context_identity_sha256")),
            monthly_source_reference_external_sha256=cast(str, payload.get("monthly_source_reference_external_sha256")),
            artifact_descriptor_external_sha256=cast(str, payload.get("artifact_descriptor_external_sha256")),
            bookmark_identity_sha256=cast(str, payload.get("bookmark_identity_sha256")),
            schema_version=cast(str, payload.get("schema_version")),
        )
        if result.to_dict() != dict(payload):
            _fail("noncanonical")
        return result

    @classmethod
    def from_json(
        cls,
        raw: str | bytes,
    ) -> DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2:
        payload = _parse_json(raw)
        result = cls.from_dict(payload)
        encoded = raw if isinstance(raw, bytes) else raw.encode("utf-8")
        if result.to_json().encode("utf-8") != encoded:
            _fail("json_noncanonical")
        return result

    @property
    def bookmark_id(self) -> str:
        return self.bookmark_identity_sha256

    @property
    def stock_code(self) -> str:
        return self.selected_stock_code

    @property
    def stock_name(self) -> str:
        return self.selected_stock_name

    @property
    def source(self) -> str:
        return DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_BOOKMARK_SOURCE_V2

    @property
    def source_scope(self) -> str:
        return "current_only"

    @property
    def availability_status(self) -> str:
        return "unknown"

    @property
    def monthly_availability_status(self) -> str:
        return "cohort_hour_bound"

    @property
    def historical_pit_eligible(self) -> bool:
        return False

    @property
    def saved_recipe(self) -> DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2:
        return DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2.from_json(
            self.saved_recipe_json
        )

    def to_dict(self) -> dict[str, object]:
        body = _bookmark_body_v2(
            saved_recipe_json=self.saved_recipe_json,
            selected_page_request_json=self.selected_page_request_json,
            selected_stock_code=self.selected_stock_code,
            selected_stock_name=self.selected_stock_name,
            selected_result_identity_sha256=self.selected_result_identity_sha256,
            selected_query_identity_sha256=self.selected_query_identity_sha256,
            selected_row_identity_sha256=self.selected_row_identity_sha256,
            selected_fact_context_json=self.selected_fact_context_json,
            selected_fact_context_identity_sha256=self.selected_fact_context_identity_sha256,
            monthly_source_reference_external_sha256=self.monthly_source_reference_external_sha256,
            artifact_descriptor_external_sha256=self.artifact_descriptor_external_sha256,
        )
        if _sha256(body) != self.bookmark_identity_sha256:
            _fail("bookmark_identity_mismatch")
        return {
            **body,
            "source": self.source,
            "bookmark_identity_sha256": self.bookmark_identity_sha256,
        }

    def to_json(self) -> str:
        raw = _canonical_bytes(self.to_dict())
        if len(raw) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_BOOKMARK_MAX_BYTES_V2:
            _fail("byte_limit")
        return raw.decode("utf-8")

    def verify_exact_row(
        self,
        exact_read: DailyMarketTechnicalOfficialDispositionRevenueExactReadV2,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalOfficialDispositionRevenueResultRowV2:
        """在 fresh V2 exact read 重比來源錨點與原選取列，不比較易變 operation identities。"""

        self.__post_init__()
        _poll_cancel(cancel_callback)
        if type(exact_read) is not DailyMarketTechnicalOfficialDispositionRevenueExactReadV2:
            _fail("exact_read_invalid")
        recipe = self.saved_recipe
        saved_request = DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2.from_json(
            self.selected_page_request_json
        )
        _verify_recipe_query_semantics_v2(recipe, exact_read.query)
        reference = exact_read.monthly_reference
        pin = exact_read.monthly_cohort_pin
        saved_reference_wrapper = decode_daily_market_monthly_revenue_source_reference_v3(
            recipe.monthly_source_reference_json,
            expected_reference_sha256=recipe.monthly_source_reference_external_sha256,
        )
        saved_reference = saved_reference_wrapper.reference
        if (
            exact_read.f17_query.to_json() != recipe.f17_query_json
            or reference.source_scope != "current_observed_only"
            or reference.source_kind != "daily_monthly_revenue_cohort"
            or reference.availability_status != "cohort_hour_bound"
            or reference.historical_pit_eligible is not False
            or reference.formal_pit_eligible is not False
            or reference.external_reference_sha256
            != exact_read.query.monthly_source_reference_external_sha256
            or reference.source_content_identity_sha256
            != saved_reference.source_content_identity_sha256
            or reference.source_content_identity_sha256 != recipe.monthly_source_content_identity_sha256
            or reference.decision_cutoff != saved_reference.decision_cutoff
            or reference.declared_stock_codes != saved_reference.declared_stock_codes
            or reference.result_identity_by_stock != saved_reference.result_identity_by_stock
            or reference.fact_identity_by_stock != saved_reference.fact_identity_by_stock
            or reference.reader_result_status_counts != saved_reference.reader_result_status_counts
            or reference.fact_state_counts != saved_reference.fact_state_counts
            or pin.cohort_sha256 != recipe.monthly_cohort_sha256
            or pin != saved_reference.cohort_pin
            or _canonical_bytes(pin.to_dict()).decode("utf-8") != recipe.monthly_cohort_pin_json
            or reference.cohort_pin != pin
            or exact_read.query.monthly_source_content_identity_sha256
            != reference.source_content_identity_sha256
            or exact_read.query.monthly_cohort_sha256 != pin.cohort_sha256
            or exact_read.query.monthly_availability_status != "cohort_hour_bound"
            or exact_read.source_scope != "current_only"
            or exact_read.availability_status != "unknown"
            or exact_read.historical_pit_eligible is not False
            or exact_read.formal_pit_eligible is not False
        ):
            _fail("exact_source_anchor_mismatch")
        descriptor = exact_read.artifact_descriptor
        descriptor_dict = descriptor.to_dict()
        _validate_sha(descriptor.external_descriptor_sha256, "exact_descriptor_sha_invalid")
        # Fresh reads publish a new descriptor containing new operation IDs. Bind its
        # stable source linkage here; the original descriptor SHA remains bound by
        # this bookmark's recipe and must be supplied to the exact-reopen caller.
        if (
            descriptor_dict.get("reference_sha256") != reference.external_reference_sha256
            or descriptor_dict.get("source_reference_identity_sha256") != reference.identity_sha256
            or descriptor_dict.get("source_content_identity_sha256") != reference.source_content_identity_sha256
            or descriptor_dict.get("finished_cohort_identity_sha256") != reference.finished_cohort_identity_sha256
            or descriptor_dict.get("cohort_sha256") != pin.cohort_sha256
            or descriptor_dict.get("decision_cutoff") != reference.decision_cutoff
            or descriptor_dict.get("declared_stock_codes") != list(reference.declared_stock_codes)
            or descriptor_dict.get("declared_stock_codes_sha256")
            != reference.declared_stock_codes_sha256
            or descriptor_dict.get("result_ledger_sha256")
            != _sha256([list(item) for item in reference.result_identity_by_stock])
            or descriptor_dict.get("fact_ledger_sha256")
            != _sha256([list(item) for item in reference.fact_identity_by_stock])
            or descriptor_dict.get("reader_result_status_counts")
            != [list(item) for item in reference.reader_result_status_counts]
            or descriptor_dict.get("fact_state_counts")
            != [list(item) for item in reference.fact_state_counts]
            or descriptor_dict.get("source_scope") != "current_observed_only"
            or descriptor_dict.get("availability_status") != "cohort_hour_bound"
            or descriptor_dict.get("complete") is not True
            or descriptor_dict.get("historical_pit_eligible") is not False
            or descriptor_dict.get("formal_pit_eligible") is not False
        ):
            _fail("exact_descriptor_source_mismatch")
        request = exact_read.page_request
        page = exact_read.page
        if (
            request.page_index != saved_request.page_index
            or request.page_size != saved_request.page_size
            or request.query.query_identity_sha256 != exact_read.query.query_identity_sha256
            or page.page_index != saved_request.page_index
            or page.page_size != saved_request.page_size
            or page.query.query_identity_sha256 != exact_read.query.query_identity_sha256
            or page.operation_identity_sha256 != exact_read.result.operation_identity_sha256
            or page.source_pins != exact_read.result.source_pins
        ):
            _fail("exact_page_context_mismatch")
        row = next((item for item in page.rows if item.stock_code == self.selected_stock_code), None)
        if type(row) is not DailyMarketTechnicalOfficialDispositionRevenueResultRowV2:
            _fail("selected_stock_not_on_reopened_page")
        if row.hard_filter_match is not True:
            _fail("selected_stock_hard_filtered")
        actual_context = _row_fact_context_v2(
            row,
            monthly_reference=reference,
        )
        if (
            _sha256(actual_context) != self.selected_fact_context_identity_sha256
            or _canonical_bytes(actual_context).decode("utf-8") != self.selected_fact_context_json
        ):
            _fail("selected_fact_context_mismatch")
        _poll_cancel(cancel_callback)
        return row


def _poll_cancel(callback: Callable[[], object] | None) -> None:
    if callback is None:
        return
    if not callable(callback):
        _fail("cancel_callback_invalid")
    result = callback()
    if type(result) is not bool:
        _fail("cancel_callback_invalid")
    if result:
        _fail("cancelled")


__all__ = [
    "DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_BOOKMARK_MAX_BYTES_V2",
    "DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_BOOKMARK_SCHEMA_V2",
    "DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_BOOKMARK_SOURCE_V2",
    "DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2",
    "DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2Error",
]
