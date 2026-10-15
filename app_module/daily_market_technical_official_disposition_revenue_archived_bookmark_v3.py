"""F17／MA／月營收封存來源的 V3 選列收藏；外部錨點保留原始版本。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Literal, NoReturn, cast

from app_module.daily_market_technical_official_disposition_revenue_archived_recipe_v3 import (
    DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3,
)
from app_module.daily_market_technical_official_disposition_revenue_archived_source_v3 import (
    DailyMarketTechnicalOfficialDispositionRevenueArchivedExactReadV3,
)
from app_module.daily_market_technical_official_disposition_revenue_bookmark_v2 import (
    _row_fact_context_v2,
)
from app_module.daily_market_technical_official_disposition_revenue_query_v2 import (
    DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2,
    DailyMarketTechnicalOfficialDispositionRevenueQueryV2,
    DailyMarketTechnicalOfficialDispositionRevenueResultRowV2,
)
from data_module.daily_market_monthly_revenue_cohort_v2 import (
    DailyMarketMonthlyRevenueSourceReferenceV3,
    decode_daily_market_monthly_revenue_source_reference_v3,
)


DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_ARCHIVED_BOOKMARK_SCHEMA_V3 = (
    "daily-market-technical-official-disposition-revenue-archived-bookmark.v3"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_ARCHIVED_BOOKMARK_SOURCE_V3 = (
    "technical_official_disposition_revenue_archived_research_bookmark_v3"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_ARCHIVED_BOOKMARK_MAX_BYTES_V3 = 128 * 1024 * 1024
_MAX_CONTEXT_BYTES = 64 * 1024 * 1024
_MAX_JSON_DEPTH = 48
_MAX_ARCHIVED_UNIVERSE_SIZE = 258
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STOCK_CODE_RE = re.compile(r"^[A-Z0-9]{1,16}$")

# Fresh V2 sessions reissue these identities. All conditions, cutoffs, pins,
# source content, methods, policies and ordering remain exact comparisons.
_REISSUED_QUERY_IDENTITY_FIELDS = frozenset({
    "query_identity_sha256",
    "monthly_yoy_read_session_identity_sha256",
    "monthly_yoy_index_identity_sha256",
    "monthly_yoy_finished_cohort_identity_sha256",
    "monthly_yoy_source_clock_identity_sha256",
    "monthly_source_reference_external_sha256",
})


class DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3Error(ValueError):
    """Archived Bookmark V3 的穩定拒絕碼。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"technical_official_revenue_archived_bookmark_v3_{code}")


def _fail(code: str) -> NoReturn:
    raise DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3Error(code)


def _reject_float_tree(value: object, *, depth: int = 0) -> None:
    if depth > _MAX_JSON_DEPTH:
        _fail("json_depth_limit")
    if isinstance(value, float):
        _fail("json_float_forbidden")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if type(key) is not str:
                _fail("json_key_invalid")
            _reject_float_tree(item, depth=depth + 1)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_float_tree(item, depth=depth + 1)


def _canonical_bytes(value: object) -> bytes:
    _reject_float_tree(value)
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3Error(
            "json_invalid"
        ) from exc


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_json(value: object) -> str:
    return _sha256_bytes(_canonical_bytes(value))


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    output: dict[str, object] = {}
    for key, value in pairs:
        if key in output:
            _fail("json_duplicate_key")
        output[key] = value
    return output


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
    if in_string or escaped or depth != 0:
        _fail("json_invalid")


def _parse_json(raw: bytes | str, *, maximum: int) -> object:
    try:
        if type(raw) is bytes:
            encoded = raw
        elif type(raw) is str:
            encoded = raw.encode("utf-8", errors="strict")
        else:
            _fail("json_input_invalid")
        if len(encoded) > maximum:
            _fail("json_byte_limit")
        text = encoded.decode("utf-8", errors="strict")
        _preflight_depth(text)
        payload = json.loads(
            text,
            object_pairs_hook=_unique_pairs,
            parse_float=lambda _value: _fail("json_float_forbidden"),
            parse_constant=lambda _value: _fail("json_constant_invalid"),
        )
        _reject_float_tree(payload)
        if _canonical_bytes(payload) != encoded:
            _fail("json_noncanonical")
        return payload
    except DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3Error:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3Error(
            "json_invalid"
        ) from exc


def _validate_sha(value: object, code: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        _fail(code)
    return cast(str, value)


def _validate_stock_code(value: object) -> str:
    if type(value) is not str or _STOCK_CODE_RE.fullmatch(value) is None:
        _fail("stock_code_invalid")
    return cast(str, value)


def _origin_reference(
    recipe: DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3,
) -> DailyMarketMonthlyRevenueSourceReferenceV3:
    base = recipe.base_recipe
    try:
        decoded = decode_daily_market_monthly_revenue_source_reference_v3(
            base.monthly_source_reference_json,
            expected_reference_sha256=base.monthly_source_reference_external_sha256,
        )
    except (TypeError, ValueError, UnicodeError) as exc:
        raise DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3Error(
            "origin_monthly_reference_invalid"
        ) from exc
    reference = decoded.reference
    if (
        reference.to_json() != base.monthly_source_reference_json
        or reference.source_kind != "daily_monthly_revenue_cohort"
        or reference.source_scope != "current_observed_only"
        or reference.availability_status != "cohort_hour_bound"
        or reference.historical_pit_eligible is not False
        or reference.formal_pit_eligible is not False
        or len(reference.declared_stock_codes) != _MAX_ARCHIVED_UNIVERSE_SIZE
        or len(reference.result_identity_by_stock) != _MAX_ARCHIVED_UNIVERSE_SIZE
        or len(reference.fact_identity_by_stock) != _MAX_ARCHIVED_UNIVERSE_SIZE
        or sum(count for _, count in reference.reader_result_status_counts)
        != _MAX_ARCHIVED_UNIVERSE_SIZE
        or sum(count for _, count in reference.fact_state_counts)
        != _MAX_ARCHIVED_UNIVERSE_SIZE
    ):
        _fail("origin_monthly_reference_contract_invalid")
    return reference


def _query_semantics_dict(query: DailyMarketTechnicalOfficialDispositionRevenueQueryV2) -> dict[str, object]:
    value = query.to_dict()
    return {
        key: item for key, item in value.items()
        if key not in _REISSUED_QUERY_IDENTITY_FIELDS
    }


def archived_revenue_query_matches_recipe_v3(
    query: DailyMarketTechnicalOfficialDispositionRevenueQueryV2,
    recipe: DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3,
) -> bool:
    """比較 fresh QueryV2 的條件語意與 V3 原 recipe；不授予來源資格。

    只略過重開時會重發的 session/index/cohort/clock/reference identities。
    月營收內容、cohort pin digest、decision cutoff/hour、方法版本、F17/MA
    條件、硬篩選、未知政策、門檻及全域排序都必須與原 recipe 相同。完整
    258 股票、雙 ledger 與分母由 V3 recipe 的錨定來源 reference 驗證；真
    來源接受仍必須由 BookmarkV3.verify_exact_row 對 issued exact token 執行。
    """

    if (
        type(query) is not DailyMarketTechnicalOfficialDispositionRevenueQueryV2
        or type(recipe) is not DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3
    ):
        return False
    try:
        recipe_json = recipe.to_json()
        saved = DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3.from_json(recipe_json)
        base = saved.base_recipe
        saved_query = DailyMarketTechnicalOfficialDispositionRevenueQueryV2.from_json(
            base.revenue_query_json
        )
        reference = _origin_reference(saved)
        current_body = _query_semantics_dict(query)
        saved_body = _query_semantics_dict(saved_query)
        return bool(
            current_body == saved_body
            and query.f17_query.to_json() == base.f17_query_json
            and query.ma_query.f17_query.to_json() == base.f17_query_json
            and query.monthly_yoy_cutoff == reference.decision_cutoff
            and query.monthly_source_content_identity_sha256
            == reference.source_content_identity_sha256
            and query.monthly_cohort_sha256 == reference.cohort_pin.cohort_sha256
            and query.monthly_availability_status == "cohort_hour_bound"
            and query.monthly_yoy_method_id == saved_query.monthly_yoy_method_id
            and query.monthly_yoy_method_version == saved_query.monthly_yoy_method_version
        )
    except (TypeError, ValueError, UnicodeError, AttributeError, KeyError):
        return False


def _validate_context(
    raw: str,
    *,
    stock_code: str,
    reference: DailyMarketMonthlyRevenueSourceReferenceV3,
) -> dict[str, object]:
    value = _parse_json(raw, maximum=_MAX_CONTEXT_BYTES)
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
        != reference.source_content_identity_sha256
        or value.get("monthly_decision_cutoff") != reference.decision_cutoff
        or value.get("monthly_declared_stock_codes") != list(reference.declared_stock_codes)
        or value.get("monthly_cohort_pin") != reference.cohort_pin.to_dict()
        or value.get("monthly_result_identity_by_stock")
        != [list(item) for item in reference.result_identity_by_stock]
        or value.get("monthly_fact_identity_by_stock")
        != [list(item) for item in reference.fact_identity_by_stock]
        or value.get("monthly_reader_result_status_counts")
        != [list(item) for item in reference.reader_result_status_counts]
        or value.get("monthly_fact_state_counts")
        != [list(item) for item in reference.fact_state_counts]
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
        _fail("selected_fact_context_invalid")
    return dict(value)


def _stable_reference_matches(
    current: DailyMarketMonthlyRevenueSourceReferenceV3,
    origin: DailyMarketMonthlyRevenueSourceReferenceV3,
) -> bool:
    return bool(
        current.source_kind == origin.source_kind == "daily_monthly_revenue_cohort"
        and current.source_scope == origin.source_scope == "current_observed_only"
        and current.availability_status == origin.availability_status == "cohort_hour_bound"
        and current.historical_pit_eligible is False
        and current.formal_pit_eligible is False
        and current.source_content_identity_sha256 == origin.source_content_identity_sha256
        and current.decision_cutoff == origin.decision_cutoff
        and current.declared_stock_codes == origin.declared_stock_codes
        and len(current.declared_stock_codes) == _MAX_ARCHIVED_UNIVERSE_SIZE
        and current.result_identity_by_stock == origin.result_identity_by_stock
        and current.fact_identity_by_stock == origin.fact_identity_by_stock
        and current.reader_result_status_counts == origin.reader_result_status_counts
        and current.fact_state_counts == origin.fact_state_counts
        and current.cohort_pin == origin.cohort_pin
    )


def _validate_exact_source(
    exact: DailyMarketTechnicalOfficialDispositionRevenueArchivedExactReadV3,
    *,
    recipe: DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3,
    source_identity_sha256: str | None,
) -> tuple[DailyMarketMonthlyRevenueSourceReferenceV3, DailyMarketTechnicalOfficialDispositionRevenueQueryV2]:
    if type(exact) is not DailyMarketTechnicalOfficialDispositionRevenueArchivedExactReadV3:
        _fail("exact_read_invalid")
    try:
        actual_source_identity = _validate_sha(
            exact.source_pair_identity_sha256,
            "exact_source_identity_invalid",
        )
        current_recipe = exact.saved_recipe
        descriptor = exact.artifact_descriptor
        reference = exact.monthly_reference
        query = exact.query
        exact.result
        exact.request
        exact.page
    except (TypeError, ValueError, AttributeError) as exc:
        raise DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3Error(
            "exact_source_not_open_or_issued"
        ) from exc
    if source_identity_sha256 is not None and actual_source_identity != source_identity_sha256:
        _fail("exact_stable_source_identity_mismatch")
    if (
        current_recipe.to_json() != recipe.to_json()
        or exact.f17_query.to_json() != recipe.base_recipe.f17_query_json
        or descriptor.to_json() != recipe.archive_artifact_descriptor_json
        or descriptor.external_descriptor_sha256
        != recipe.archive_artifact_descriptor_external_sha256
        or not archived_revenue_query_matches_recipe_v3(query, recipe)
        or not exact.monthly_sqlite_connection_closed
        or exact.source_scope != "current_only"
        or exact.availability_status != "unknown"
        or exact.monthly_availability_status != "cohort_hour_bound"
        or exact.historical_pit_eligible is not False
        or exact.formal_pit_eligible is not False
    ):
        _fail("exact_source_recipe_or_scope_mismatch")
    origin = _origin_reference(recipe)
    if not _stable_reference_matches(reference, origin):
        _fail("exact_monthly_source_identity_mismatch")
    pin = exact.monthly_cohort_pin
    if (
        pin != origin.cohort_pin
        or query.monthly_source_reference_external_sha256 != reference.external_reference_sha256
        or query.monthly_source_content_identity_sha256 != reference.source_content_identity_sha256
        or query.monthly_cohort_sha256 != pin.cohort_sha256
        or query.monthly_availability_status != "cohort_hour_bound"
    ):
        _fail("exact_query_source_pin_mismatch")
    return reference, query


def _bookmark_body_v3(
    *,
    saved_recipe_json: str,
    selected_page_request_json: str,
    selected_stock_code: str,
    selected_stock_name: str,
    selected_result_identity_sha256: str,
    selected_query_identity_sha256: str,
    selected_page_identity_sha256: str,
    selected_row_identity_sha256: str,
    selected_fact_context_json: str,
    selected_fact_context_identity_sha256: str,
    original_monthly_source_reference_external_sha256: str,
    original_monthly_artifact_descriptor_external_sha256: str,
    archive_reference_external_sha256: str,
    archive_artifact_descriptor_external_sha256: str,
    source_pair_identity_sha256: str,
) -> dict[str, object]:
    return {
        "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_ARCHIVED_BOOKMARK_SCHEMA_V3,
        "saved_recipe_json": saved_recipe_json,
        "selected_page_request_json": selected_page_request_json,
        "selected_stock_code": selected_stock_code,
        "selected_stock_name": selected_stock_name,
        "selected_result_identity_sha256": selected_result_identity_sha256,
        "selected_query_identity_sha256": selected_query_identity_sha256,
        "selected_page_identity_sha256": selected_page_identity_sha256,
        "selected_row_identity_sha256": selected_row_identity_sha256,
        "selected_fact_context_json": selected_fact_context_json,
        "selected_fact_context_identity_sha256": selected_fact_context_identity_sha256,
        "original_monthly_source_reference_external_sha256": original_monthly_source_reference_external_sha256,
        "original_monthly_artifact_descriptor_external_sha256": original_monthly_artifact_descriptor_external_sha256,
        "archive_reference_external_sha256": archive_reference_external_sha256,
        "archive_artifact_descriptor_external_sha256": archive_artifact_descriptor_external_sha256,
        "source_pair_identity_sha256": source_pair_identity_sha256,
        "source_scope": "current_only",
        "availability_status": "unknown",
        "monthly_availability_status": "cohort_hour_bound",
        "historical_pit_eligible": False,
        "bookmark_is_reader_qualification": False,
    }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3:
    """封存來源 V3 收藏；typed decode 是資料，不是 exact-reader 資格。"""

    saved_recipe_json: str
    selected_page_request_json: str
    selected_stock_code: str
    selected_stock_name: str
    selected_result_identity_sha256: str
    selected_query_identity_sha256: str
    selected_page_identity_sha256: str
    selected_row_identity_sha256: str
    selected_fact_context_json: str
    selected_fact_context_identity_sha256: str
    original_monthly_source_reference_external_sha256: str
    original_monthly_artifact_descriptor_external_sha256: str
    archive_reference_external_sha256: str
    archive_artifact_descriptor_external_sha256: str
    source_pair_identity_sha256: str
    bookmark_identity_sha256: str
    schema_version: str = DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_ARCHIVED_BOOKMARK_SCHEMA_V3

    def __post_init__(self) -> None:
        if self.schema_version != DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_ARCHIVED_BOOKMARK_SCHEMA_V3:
            _fail("schema_unsupported")
        code = _validate_stock_code(self.selected_stock_code)
        if type(self.selected_stock_name) is not str or self.selected_stock_name != code:
            _fail("stock_name_invalid")
        for value, error_code in (
            (self.selected_result_identity_sha256, "result_identity_invalid"),
            (self.selected_query_identity_sha256, "query_identity_invalid"),
            (self.selected_page_identity_sha256, "page_identity_invalid"),
            (self.selected_row_identity_sha256, "row_identity_invalid"),
            (self.selected_fact_context_identity_sha256, "fact_context_identity_invalid"),
            (self.original_monthly_source_reference_external_sha256, "monthly_reference_sha_invalid"),
            (self.original_monthly_artifact_descriptor_external_sha256, "monthly_descriptor_sha_invalid"),
            (self.archive_reference_external_sha256, "archive_reference_sha_invalid"),
            (self.archive_artifact_descriptor_external_sha256, "archive_descriptor_sha_invalid"),
            (self.source_pair_identity_sha256, "source_pair_identity_invalid"),
            (self.bookmark_identity_sha256, "bookmark_identity_invalid"),
        ):
            _validate_sha(value, error_code)
        if type(self.saved_recipe_json) is not str or type(self.selected_page_request_json) is not str:
            _fail("saved_recipe_or_request_invalid")
        recipe = DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3.from_json(
            self.saved_recipe_json
        )
        request = DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2.from_json(
            self.selected_page_request_json
        )
        base = recipe.base_recipe
        if (
            recipe.to_json() != self.saved_recipe_json
            or request.to_json() != self.selected_page_request_json
            or request.to_json() != base.page_request_json
            or request.page_index != base.page_index
            or request.page_size != base.page_size
            or request.query.query_identity_sha256 != self.selected_query_identity_sha256
            or request.query.to_json() != base.revenue_query_json
            or base.monthly_source_reference_external_sha256
            != self.original_monthly_source_reference_external_sha256
            or base.artifact_descriptor_external_sha256
            != self.original_monthly_artifact_descriptor_external_sha256
            or recipe.archive_reference_external_sha256 != self.archive_reference_external_sha256
            or recipe.archive_artifact_descriptor_external_sha256
            != self.archive_artifact_descriptor_external_sha256
        ):
            _fail("recipe_page_or_external_anchor_mismatch")
        origin = _origin_reference(recipe)
        context = _validate_context(
            self.selected_fact_context_json,
            stock_code=code,
            reference=origin,
        )
        if _canonical_bytes(context).decode("utf-8", errors="strict") != self.selected_fact_context_json:
            _fail("fact_context_noncanonical")
        if _sha256_json(context) != self.selected_fact_context_identity_sha256:
            _fail("fact_context_identity_mismatch")
        body = _bookmark_body_v3(
            saved_recipe_json=self.saved_recipe_json,
            selected_page_request_json=self.selected_page_request_json,
            selected_stock_code=code,
            selected_stock_name=self.selected_stock_name,
            selected_result_identity_sha256=self.selected_result_identity_sha256,
            selected_query_identity_sha256=self.selected_query_identity_sha256,
            selected_page_identity_sha256=self.selected_page_identity_sha256,
            selected_row_identity_sha256=self.selected_row_identity_sha256,
            selected_fact_context_json=self.selected_fact_context_json,
            selected_fact_context_identity_sha256=self.selected_fact_context_identity_sha256,
            original_monthly_source_reference_external_sha256=self.original_monthly_source_reference_external_sha256,
            original_monthly_artifact_descriptor_external_sha256=self.original_monthly_artifact_descriptor_external_sha256,
            archive_reference_external_sha256=self.archive_reference_external_sha256,
            archive_artifact_descriptor_external_sha256=self.archive_artifact_descriptor_external_sha256,
            source_pair_identity_sha256=self.source_pair_identity_sha256,
        )
        if _sha256_json(body) != self.bookmark_identity_sha256:
            _fail("bookmark_identity_mismatch")
        if len(_canonical_bytes(self.to_dict())) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_ARCHIVED_BOOKMARK_MAX_BYTES_V3:
            _fail("byte_limit")

    @classmethod
    def from_exact_read(
        cls,
        exact3: DailyMarketTechnicalOfficialDispositionRevenueArchivedExactReadV3,
        *,
        stock_code: str,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3:
        _poll_cancel(cancel_callback)
        if type(exact3) is not DailyMarketTechnicalOfficialDispositionRevenueArchivedExactReadV3:
            _fail("exact_read_invalid")
        try:
            source_identity = _validate_sha(
                exact3.source_pair_identity_sha256,
                "exact_source_identity_invalid",
            )
            recipe = exact3.saved_recipe
            request = exact3.request
            page = exact3.page
            query = exact3.query
            result = exact3.result
        except (TypeError, ValueError, AttributeError) as exc:
            raise DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3Error(
                "exact_source_not_open_or_issued"
            ) from exc
        reference, query = _validate_exact_source(
            exact3,
            recipe=recipe,
            source_identity_sha256=source_identity,
        )
        code = _validate_stock_code(stock_code)
        if not archived_revenue_query_matches_recipe_v3(query, recipe):
            _fail("query_recipe_mismatch")
        page_dict = page.to_dict()
        if (
            request.to_json() != recipe.base_recipe.page_request_json
            or request.query.query_identity_sha256 != query.query_identity_sha256
            or request.page_index != recipe.base_recipe.page_index
            or request.page_size != recipe.base_recipe.page_size
            or page.page_index != request.page_index
            or page.page_size != request.page_size
            or page.query.query_identity_sha256 != query.query_identity_sha256
            or page.operation_identity_sha256 != result.operation_identity_sha256
            or page.source_pins != result.source_pins
            or page_dict.get("operation_identity_sha256") != result.operation_identity_sha256
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
        context = _row_fact_context_v2(row, monthly_reference=reference)
        context_json = _canonical_bytes(context).decode("utf-8", errors="strict")
        original_base = recipe.base_recipe
        body = _bookmark_body_v3(
            saved_recipe_json=recipe.to_json(),
            selected_page_request_json=request.to_json(),
            selected_stock_code=code,
            selected_stock_name=code,
            selected_result_identity_sha256=result.operation_identity_sha256,
            selected_query_identity_sha256=query.query_identity_sha256,
            selected_page_identity_sha256=page.page_identity_sha256,
            selected_row_identity_sha256=row.row_identity_sha256,
            selected_fact_context_json=context_json,
            selected_fact_context_identity_sha256=_sha256_json(context),
            original_monthly_source_reference_external_sha256=original_base.monthly_source_reference_external_sha256,
            original_monthly_artifact_descriptor_external_sha256=original_base.artifact_descriptor_external_sha256,
            archive_reference_external_sha256=recipe.archive_reference_external_sha256,
            archive_artifact_descriptor_external_sha256=recipe.archive_artifact_descriptor_external_sha256,
            source_pair_identity_sha256=source_identity,
        )
        _poll_cancel(cancel_callback)
        return cls(
            saved_recipe_json=recipe.to_json(),
            selected_page_request_json=request.to_json(),
            selected_stock_code=code,
            selected_stock_name=code,
            selected_result_identity_sha256=result.operation_identity_sha256,
            selected_query_identity_sha256=query.query_identity_sha256,
            selected_page_identity_sha256=page.page_identity_sha256,
            selected_row_identity_sha256=row.row_identity_sha256,
            selected_fact_context_json=context_json,
            selected_fact_context_identity_sha256=_sha256_json(context),
            original_monthly_source_reference_external_sha256=original_base.monthly_source_reference_external_sha256,
            original_monthly_artifact_descriptor_external_sha256=original_base.artifact_descriptor_external_sha256,
            archive_reference_external_sha256=recipe.archive_reference_external_sha256,
            archive_artifact_descriptor_external_sha256=recipe.archive_artifact_descriptor_external_sha256,
            source_pair_identity_sha256=source_identity,
            bookmark_identity_sha256=_sha256_json(body),
        )

    @classmethod
    def from_dict(
        cls,
        payload: object,
    ) -> DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3:
        expected = {
            "schema_version", "saved_recipe_json", "selected_page_request_json",
            "selected_stock_code", "selected_stock_name", "selected_result_identity_sha256",
            "selected_query_identity_sha256", "selected_page_identity_sha256",
            "selected_row_identity_sha256", "selected_fact_context_json",
            "selected_fact_context_identity_sha256",
            "original_monthly_source_reference_external_sha256",
            "original_monthly_artifact_descriptor_external_sha256",
            "archive_reference_external_sha256", "archive_artifact_descriptor_external_sha256",
            "source_pair_identity_sha256", "source_scope", "availability_status",
            "monthly_availability_status", "historical_pit_eligible",
            "bookmark_is_reader_qualification", "bookmark_identity_sha256", "source",
        }
        if not isinstance(payload, Mapping) or set(payload) != expected:
            _fail("fields_invalid")
        if (
            payload.get("source") != DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_ARCHIVED_BOOKMARK_SOURCE_V3
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
            selected_page_identity_sha256=cast(str, payload.get("selected_page_identity_sha256")),
            selected_row_identity_sha256=cast(str, payload.get("selected_row_identity_sha256")),
            selected_fact_context_json=cast(str, payload.get("selected_fact_context_json")),
            selected_fact_context_identity_sha256=cast(str, payload.get("selected_fact_context_identity_sha256")),
            original_monthly_source_reference_external_sha256=cast(str, payload.get("original_monthly_source_reference_external_sha256")),
            original_monthly_artifact_descriptor_external_sha256=cast(str, payload.get("original_monthly_artifact_descriptor_external_sha256")),
            archive_reference_external_sha256=cast(str, payload.get("archive_reference_external_sha256")),
            archive_artifact_descriptor_external_sha256=cast(str, payload.get("archive_artifact_descriptor_external_sha256")),
            source_pair_identity_sha256=cast(str, payload.get("source_pair_identity_sha256")),
            bookmark_identity_sha256=cast(str, payload.get("bookmark_identity_sha256")),
            schema_version=cast(str, payload.get("schema_version")),
        )
        if result.to_dict() != dict(payload):
            _fail("noncanonical")
        return result

    @classmethod
    def from_json(
        cls,
        raw: bytes | str,
    ) -> DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3:
        payload = _parse_json(
            raw,
            maximum=DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_ARCHIVED_BOOKMARK_MAX_BYTES_V3,
        )
        return cls.from_dict(payload)

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
        return DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_ARCHIVED_BOOKMARK_SOURCE_V3

    @property
    def source_scope(self) -> Literal["current_only"]:
        return "current_only"

    @property
    def availability_status(self) -> Literal["unknown"]:
        return "unknown"

    @property
    def monthly_availability_status(self) -> Literal["cohort_hour_bound"]:
        return "cohort_hour_bound"

    @property
    def historical_pit_eligible(self) -> Literal[False]:
        return False

    @property
    def saved_recipe(self) -> DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3:
        return DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3.from_json(
            self.saved_recipe_json
        )

    def to_dict(self) -> dict[str, object]:
        body = _bookmark_body_v3(
            saved_recipe_json=self.saved_recipe_json,
            selected_page_request_json=self.selected_page_request_json,
            selected_stock_code=self.selected_stock_code,
            selected_stock_name=self.selected_stock_name,
            selected_result_identity_sha256=self.selected_result_identity_sha256,
            selected_query_identity_sha256=self.selected_query_identity_sha256,
            selected_page_identity_sha256=self.selected_page_identity_sha256,
            selected_row_identity_sha256=self.selected_row_identity_sha256,
            selected_fact_context_json=self.selected_fact_context_json,
            selected_fact_context_identity_sha256=self.selected_fact_context_identity_sha256,
            original_monthly_source_reference_external_sha256=self.original_monthly_source_reference_external_sha256,
            original_monthly_artifact_descriptor_external_sha256=self.original_monthly_artifact_descriptor_external_sha256,
            archive_reference_external_sha256=self.archive_reference_external_sha256,
            archive_artifact_descriptor_external_sha256=self.archive_artifact_descriptor_external_sha256,
            source_pair_identity_sha256=self.source_pair_identity_sha256,
        )
        if _sha256_json(body) != self.bookmark_identity_sha256:
            _fail("bookmark_identity_mismatch")
        return {
            **body,
            "source": self.source,
            "bookmark_identity_sha256": self.bookmark_identity_sha256,
        }

    def to_json(self) -> str:
        raw = _canonical_bytes(self.to_dict())
        if len(raw) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_ARCHIVED_BOOKMARK_MAX_BYTES_V3:
            _fail("byte_limit")
        return raw.decode("utf-8", errors="strict")

    def verify_exact_row(
        self,
        exact3: DailyMarketTechnicalOfficialDispositionRevenueArchivedExactReadV3,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalOfficialDispositionRevenueResultRowV2:
        """以 owner-thread V3 exact token 重查原清冊與選列的穩定來源事實。"""

        self.__post_init__()
        _poll_cancel(cancel_callback)
        if type(exact3) is not DailyMarketTechnicalOfficialDispositionRevenueArchivedExactReadV3:
            _fail("exact_read_invalid")
        recipe = self.saved_recipe
        saved_request = DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2.from_json(
            self.selected_page_request_json
        )
        reference, query = _validate_exact_source(
            exact3,
            recipe=recipe,
            source_identity_sha256=self.source_pair_identity_sha256,
        )
        request = exact3.request
        page = exact3.page
        result = exact3.result
        if (
            request.page_index != saved_request.page_index
            or request.page_size != saved_request.page_size
            or page.page_index != saved_request.page_index
            or page.page_size != saved_request.page_size
            or request.query.query_identity_sha256 != query.query_identity_sha256
            or page.query.query_identity_sha256 != query.query_identity_sha256
            or page.operation_identity_sha256 != result.operation_identity_sha256
            or page.source_pins != result.source_pins
        ):
            _fail("exact_page_context_mismatch")
        row = next((item for item in page.rows if item.stock_code == self.selected_stock_code), None)
        if type(row) is not DailyMarketTechnicalOfficialDispositionRevenueResultRowV2:
            _fail("selected_stock_not_on_reopened_page")
        if row.hard_filter_match is not True:
            _fail("selected_stock_hard_filtered")
        actual_context = _row_fact_context_v2(row, monthly_reference=reference)
        actual_context_json = _canonical_bytes(actual_context).decode("utf-8", errors="strict")
        if (
            _sha256_json(actual_context) != self.selected_fact_context_identity_sha256
            or actual_context_json != self.selected_fact_context_json
        ):
            _fail("selected_fact_context_mismatch")
        _poll_cancel(cancel_callback)
        return row


def _poll_cancel(callback: Callable[[], object] | None) -> None:
    if callback is None:
        return
    if not callable(callback):
        _fail("cancel_callback_invalid")
    try:
        value = callback()
    except Exception as exc:
        raise DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3Error(
            "cancel_check_failed"
        ) from exc
    if type(value) is not bool:
        _fail("cancel_callback_invalid")
    if value:
        _fail("cancelled")


__all__ = [
    "DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_ARCHIVED_BOOKMARK_MAX_BYTES_V3",
    "DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_ARCHIVED_BOOKMARK_SCHEMA_V3",
    "DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_ARCHIVED_BOOKMARK_SOURCE_V3",
    "DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3",
    "DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3Error",
    "archived_revenue_query_matches_recipe_v3",
]
