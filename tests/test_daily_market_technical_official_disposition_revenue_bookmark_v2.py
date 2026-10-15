from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

pytest_plugins = ("test_daily_market_technical_official_disposition_bundle_v1",)

from app_module.daily_market_technical_official_disposition_revenue_bookmark_v1 import (
    DailyMarketTechnicalOfficialDispositionRevenueBookmarkV1,
    DailyMarketTechnicalOfficialDispositionRevenueBookmarkV1Error,
)
from app_module.daily_market_technical_official_disposition_revenue_bookmark_v2 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_BOOKMARK_SCHEMA_V2,
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_BOOKMARK_SOURCE_V2,
    DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2,
    DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2Error,
)
from app_module.daily_market_technical_official_disposition_revenue_query_v2 import (
    DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2,
)
from app_module.daily_market_technical_official_disposition_revenue_source_v2 import (
    DailyMarketTechnicalOfficialDispositionRevenueExactReadV2,
    DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2,
    reopen_daily_market_technical_official_disposition_revenue_from_recipe_v2,
)
from data_module.daily_monthly_revenue_cohort import DailyMonthlyRevenueCohortReader
from data_module.recommendation_current_fundamental_provider import RecommendationCurrentFundamentalProvider
from tests.test_daily_market_technical_official_disposition_revenue_source_v2 import (
    _PROTECTED_ROOTS,
    _open_bundle,
)
from tests.test_daily_market_technical_official_disposition_revenue_query_v2 import _daily_f17_environment


@dataclass(frozen=True, slots=True)
class _BookmarkEnvironment:
    provider: RecommendationCurrentFundamentalProvider
    reader: DailyMonthlyRevenueCohortReader
    artifact_root: Path
    exact: DailyMarketTechnicalOfficialDispositionRevenueExactReadV2


@pytest.fixture
def bookmark_environment(
    bundle_fixture: Any,
    tmp_path: Path,
) -> Any:
    provider, reader, _pin, _market_readers, _market_roots = _daily_f17_environment(
        tmp_path / "daily-source",
    )
    artifact_root = tmp_path / "monthly-reference-artifacts"
    exact = _open_bundle(
        bundle_fixture,
        provider=provider,
        reader=reader,
        operation_root=tmp_path / "operation-first",
        artifact_root=artifact_root,
        artifact_id="first-source",
    )
    try:
        yield _BookmarkEnvironment(provider, reader, artifact_root, exact)
    finally:
        exact.close()


def _bookmark(environment: _BookmarkEnvironment) -> DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2:
    return DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2.from_exact_read(
        environment.exact,
        "1000",
    )


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _rehashed_payload(payload: dict[str, object]) -> dict[str, object]:
    body = {key: value for key, value in payload.items() if key not in {"bookmark_identity_sha256", "source"}}
    payload["bookmark_identity_sha256"] = hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()
    return payload


def test_bookmark_v2_is_issued_from_exact_read_and_canonical_roundtrips(
    bookmark_environment: _BookmarkEnvironment,
) -> None:
    bookmark = _bookmark(bookmark_environment)
    restored = DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2.from_json(
        bookmark.to_json().encode("utf-8")
    )

    assert restored == bookmark
    assert restored.schema_version == DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_BOOKMARK_SCHEMA_V2
    assert restored.source == DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_BOOKMARK_SOURCE_V2
    assert restored.stock_code == "1000"
    assert restored.saved_recipe.monthly_source_reference_external_sha256 == restored.monthly_source_reference_external_sha256
    assert restored.saved_recipe.artifact_descriptor_external_sha256 == restored.artifact_descriptor_external_sha256
    assert restored.monthly_availability_status == "cohort_hour_bound"
    assert restored.source_scope == "current_only"
    assert restored.availability_status == "unknown"
    assert restored.historical_pit_eligible is False
    assert restored.to_dict()["bookmark_is_reader_qualification"] is False


def test_bookmark_v2_issued_page_factory_checks_request_recipe_row_and_hard_filter(
    bookmark_environment: _BookmarkEnvironment,
) -> None:
    exact = bookmark_environment.exact
    recipe = exact.saved_recipe
    request = exact.page_request
    page = exact.page
    issued = DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2.from_issued_result_page(
        recipe=recipe,
        page_request=request,
        page=page,
        stock_code="1000",
    )
    assert issued == _bookmark(bookmark_environment)

    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2Error, match="selected_stock_not_on_issued_page"):
        DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2.from_issued_result_page(
            recipe=recipe,
            page_request=request,
            page=page,
            stock_code="9999",
        )

    page_one_request = DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2.create(
        exact.query,
        page_index=1,
        page_size=request.page_size,
    )
    page_one = exact.result.read_page_request(page_one_request)
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2Error, match="issued_page_context_mismatch"):
        DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2.from_issued_result_page(
            recipe=recipe,
            page_request=page_one_request,
            page=page_one,
            stock_code="1000",
        )


def test_bookmark_v2_rejects_wrong_external_anchors_even_after_outer_rehash(
    bookmark_environment: _BookmarkEnvironment,
) -> None:
    bookmark = _bookmark(bookmark_environment)
    for key in (
        "monthly_source_reference_external_sha256",
        "artifact_descriptor_external_sha256",
    ):
        payload = bookmark.to_dict()
        payload[key] = "0" * 64 if payload[key] != "0" * 64 else "1" * 64
        with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2Error, match="recipe_page_or_anchor_context_mismatch"):
            DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2.from_dict(_rehashed_payload(payload))


def test_bookmark_v2_fact_context_is_checked_against_fresh_exact_row(
    bookmark_environment: _BookmarkEnvironment,
) -> None:
    bookmark = _bookmark(bookmark_environment)
    payload = bookmark.to_dict()
    context = json.loads(str(payload["selected_fact_context_json"]))
    context["monthly_projected_fact"]["growth_percent"] = "999.0"
    payload["selected_fact_context_json"] = _canonical_json(context)
    payload["selected_fact_context_identity_sha256"] = hashlib.sha256(
        _canonical_json(context).encode("utf-8")
    ).hexdigest()
    forged = DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2.from_dict(
        _rehashed_payload(payload)
    )

    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2Error, match="selected_fact_context_mismatch"):
        forged.verify_exact_row(bookmark_environment.exact)


def test_bookmark_v2_fresh_reopen_uses_stable_source_facts_not_ephemeral_operation_ids(
    bundle_fixture: Any,
    bookmark_environment: _BookmarkEnvironment,
) -> None:
    first = bookmark_environment.exact
    bookmark = _bookmark(bookmark_environment)
    reopened = reopen_daily_market_technical_official_disposition_revenue_from_recipe_v2(
        bookmark.saved_recipe,
        operation_root=bookmark_environment.artifact_root.parent / "operation-reopened",
        monthly_provider=bookmark_environment.provider,
        daily_monthly_cohort_reader=bookmark_environment.reader,
        monthly_reference_artifact_root=bookmark_environment.artifact_root,
        artifact_id="reopened-source",
        expected_descriptor_sha256=bookmark.artifact_descriptor_external_sha256,
        expected_monthly_source_reference_sha256=bookmark.monthly_source_reference_external_sha256,
        protected_roots=_PROTECTED_ROOTS,
    )
    try:
        assert reopened.artifact_descriptor.artifact_id != first.artifact_descriptor.artifact_id
        assert reopened.artifact_descriptor.external_descriptor_sha256 != bookmark.artifact_descriptor_external_sha256
        # The caller used the original recipe's external anchors to reopen. A new
        # operation may issue a different raw reference/descriptor SHA; verify the
        # fresh descriptor against its own reference and compare stable source facts.
        assert reopened.artifact_descriptor.to_dict()["reference_sha256"] == reopened.monthly_reference.external_reference_sha256
        assert reopened.query.monthly_source_reference_external_sha256 == reopened.monthly_reference.external_reference_sha256
        assert reopened.monthly_reference.source_content_identity_sha256 == bookmark.saved_recipe.monthly_source_content_identity_sha256
        assert reopened.monthly_reference.cohort_pin.to_dict() == json.loads(bookmark.saved_recipe.monthly_cohort_pin_json)
        row = bookmark.verify_exact_row(reopened)
        assert row.stock_code == bookmark.stock_code
        assert row.monthly_entry.projected_fact.growth_percent == Decimal("22.006875")
    finally:
        reopened.close()


def test_bookmark_v2_rejects_v1_schema_extra_fields_float_and_duplicate_json_keys(
    bookmark_environment: _BookmarkEnvironment,
) -> None:
    bookmark = _bookmark(bookmark_environment)
    payload = bookmark.to_dict()
    payload["schema_version"] = "daily-market-technical-official-disposition-revenue-bookmark.v1"
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2Error, match="schema_unsupported"):
        DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2.from_dict(payload)

    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueBookmarkV1Error):
        DailyMarketTechnicalOfficialDispositionRevenueBookmarkV1.from_dict(bookmark.to_dict())

    payload = bookmark.to_dict()
    payload["extra"] = "value"
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2Error, match="fields_invalid"):
        DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2.from_dict(payload)

    context = json.loads(bookmark.selected_fact_context_json)
    context["nonfinite_probe"] = 0.5
    payload = bookmark.to_dict()
    payload["selected_fact_context_json"] = _canonical_json(context)
    payload["selected_fact_context_identity_sha256"] = hashlib.sha256(
        _canonical_json(context).encode("utf-8")
    ).hexdigest()
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2Error, match="json_float_forbidden"):
        DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2.from_dict(_rehashed_payload(payload))

    raw = bookmark.to_json()
    duplicate = raw[:-1] + ',"source":"duplicate"}'
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2Error, match="json_duplicate_key"):
        DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2.from_json(duplicate)


@pytest.mark.parametrize(
    ("callback", "error_code"),
    [
        (lambda: 1, "cancel_callback_invalid"),
        (lambda: True, "cancelled"),
    ],
)
def test_bookmark_v2_verify_exact_row_has_strict_cancellation(
    bookmark_environment: _BookmarkEnvironment,
    callback: Any,
    error_code: str,
) -> None:
    bookmark = _bookmark(bookmark_environment)
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2Error, match=error_code):
        bookmark.verify_exact_row(bookmark_environment.exact, cancel_callback=callback)


def test_bookmark_v2_decoder_does_not_turn_json_into_reader_qualification(
    bookmark_environment: _BookmarkEnvironment,
) -> None:
    bookmark = DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2.from_json(
        _bookmark(bookmark_environment).to_json()
    )
    assert bookmark.to_dict()["bookmark_is_reader_qualification"] is False
    assert bookmark.availability_status == "unknown"
    assert bookmark.monthly_availability_status == "cohort_hour_bound"

