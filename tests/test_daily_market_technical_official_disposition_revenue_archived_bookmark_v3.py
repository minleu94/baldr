from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

pytest_plugins = ("test_daily_market_technical_official_disposition_bundle_v1",)

from app_module.daily_market_technical_official_disposition_revenue_archived_bookmark_v3 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_ARCHIVED_BOOKMARK_SCHEMA_V3,
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_ARCHIVED_BOOKMARK_SOURCE_V3,
    DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3,
    DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3Error,
    archived_revenue_query_matches_recipe_v3,
)
from app_module.daily_market_technical_official_disposition_revenue_archived_source_v3 import (
    DailyMarketTechnicalOfficialDispositionRevenueArchivedExactReadV3,
    open_daily_market_technical_official_disposition_revenue_archived_bundle_source_v3,
    reopen_daily_market_technical_official_disposition_revenue_archived_from_recipe_v3,
)
from app_module.daily_market_technical_official_disposition_revenue_query_v2 import (
    DailyMarketTechnicalOfficialDispositionRevenueQueryV2,
    DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2,
)
from tests.test_daily_market_technical_official_disposition_revenue_source_v2 import (
    _PROTECTED_ROOTS,
    _ROW_SCOPES,
)
from tests.test_daily_market_technical_official_disposition_revenue_query_v2 import (
    _daily_f17_environment,
)


@dataclass(frozen=True, slots=True)
class _ArchivedBookmarkEnvironment:
    provider: Any
    reader: Any
    exact: DailyMarketTechnicalOfficialDispositionRevenueArchivedExactReadV3
    bundle: Any
    root4: Path
    temp: Path


@pytest.fixture(scope="module")
def archive_bookmark_environment(bundle_fixture: Any, tmp_path_factory: Any) -> Any:
    temp = tmp_path_factory.mktemp("archived-bookmark-v3")
    provider, reader, _pin, _market_readers, _market_roots = _daily_f17_environment(
        temp / "daily-source",
    )
    root3 = temp / "original-reference-artifacts"
    root4 = temp / "archive-reference-artifacts"
    root3.mkdir()
    root4.mkdir()
    exact = open_daily_market_technical_official_disposition_revenue_archived_bundle_source_v3(
        archive_parent=temp / "saved-monthly-archives",
        archived_reference_artifact_root=root4,
        archived_artifact_id="archive-origin",
        bundle_output_root=bundle_fixture.bundle_root,
        bundle_identity_sha256=bundle_fixture.reference.bundle_identity_sha256,
        expected_manifest_sha256=bundle_fixture.reference.manifest_sha256,
        row_scope_filter=_ROW_SCOPES,
        operation_root=temp / "original-operation",
        monthly_provider=provider,
        daily_monthly_cohort_reader=reader,
        monthly_reference_artifact_root=root3,
        artifact_id="original-monthly",
        protected_roots=_PROTECTED_ROOTS,
        ma_states=("unknown",),
        minimum_yoy_percent=Decimal("0"),
        condition_combine_mode="OR",
        unknown_policy="include",
        sort_clauses=(
            DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2(
                "monthly_revenue_yoy_percent", "desc"
            ),
            DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2("stock_code", "asc"),
        ),
        page_index=0,
        page_size=8,
    )
    try:
        assert len(exact.monthly_reference.declared_stock_codes) == 258
        yield _ArchivedBookmarkEnvironment(provider, reader, exact, bundle_fixture, root4, temp)
    finally:
        exact.close()


def _bookmark_v3(
    environment: _ArchivedBookmarkEnvironment,
    stock_code: str = "1000",
) -> DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3:
    return DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3.from_exact_read(
        environment.exact,
        stock_code=stock_code,
    )


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _rehashed_bookmark(payload: dict[str, object]) -> dict[str, object]:
    body = {
        key: value for key, value in payload.items()
        if key not in {"bookmark_identity_sha256", "source"}
    }
    payload["bookmark_identity_sha256"] = hashlib.sha256(
        _canonical(body).encode("utf-8")
    ).hexdigest()
    return payload


def _rehashed_query(payload: dict[str, object]) -> dict[str, object]:
    body = {key: value for key, value in payload.items() if key != "query_identity_sha256"}
    payload["query_identity_sha256"] = hashlib.sha256(
        _canonical(body).encode("utf-8")
    ).hexdigest()
    return payload


def _reopen_v3(
    environment: _ArchivedBookmarkEnvironment,
    bookmark: DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3,
    *,
    artifact_id: str = "fresh-source",
) -> DailyMarketTechnicalOfficialDispositionRevenueArchivedExactReadV3:
    recipe = bookmark.saved_recipe
    monthly_root = environment.temp / f"artifacts-{artifact_id}"
    monthly_root.mkdir()
    return reopen_daily_market_technical_official_disposition_revenue_archived_from_recipe_v3(
        recipe,
        operation_root=environment.temp / f"operation-{artifact_id}",
        monthly_provider=environment.provider,
        daily_monthly_cohort_reader=environment.reader,
        monthly_reference_artifact_root=monthly_root,
        artifact_id=artifact_id,
        archived_reference_artifact_root=environment.root4,
        expected_archive_descriptor_sha256=bookmark.archive_artifact_descriptor_external_sha256,
        expected_archive_reference_sha256=bookmark.archive_reference_external_sha256,
        expected_monthly_source_reference_sha256=(
            bookmark.original_monthly_source_reference_external_sha256
        ),
        protected_roots=_PROTECTED_ROOTS,
    )


def test_archived_bookmark_v3_issues_from_full258_exact_and_roundtrips(
    archive_bookmark_environment: _ArchivedBookmarkEnvironment,
) -> None:
    bookmark = _bookmark_v3(archive_bookmark_environment)
    restored = DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3.from_json(
        bookmark.to_json().encode("utf-8")
    )

    assert restored == bookmark
    assert restored.schema_version == DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_ARCHIVED_BOOKMARK_SCHEMA_V3
    assert restored.source == DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_ARCHIVED_BOOKMARK_SOURCE_V3
    assert restored.stock_code == restored.selected_stock_code == "1000"
    assert restored.stock_name == "1000"
    assert restored.monthly_availability_status == "cohort_hour_bound"
    assert restored.source_scope == "current_only"
    assert restored.availability_status == "unknown"
    assert restored.historical_pit_eligible is False
    assert restored.to_dict()["bookmark_is_reader_qualification"] is False
    assert restored.saved_recipe.to_json() == archive_bookmark_environment.exact.saved_recipe.to_json()
    assert restored.verify_exact_row(archive_bookmark_environment.exact).stock_code == "1000"


def test_archived_bookmark_v3_reopens_stable_full_source_without_reusing_fresh_hashes(
    archive_bookmark_environment: _ArchivedBookmarkEnvironment,
) -> None:
    environment = archive_bookmark_environment
    bookmark = _bookmark_v3(environment)
    reopened = _reopen_v3(environment, bookmark)
    try:
        assert len(reopened.monthly_reference.declared_stock_codes) == 258
        assert reopened.source_pair_identity_sha256 == bookmark.source_pair_identity_sha256
        assert reopened.monthly_reference.external_reference_sha256 != (
            bookmark.original_monthly_source_reference_external_sha256
        )
        assert reopened.query.query_identity_sha256 != bookmark.selected_query_identity_sha256
        assert archived_revenue_query_matches_recipe_v3(reopened.query, bookmark.saved_recipe)
        row = bookmark.verify_exact_row(reopened)
        assert row.stock_code == "1000"
        assert row.monthly_entry.projected_fact.growth_percent == Decimal("22.006875")
    finally:
        reopened.close()


def test_archived_bookmark_v3_rejects_each_wrong_origin_external_anchor_after_rehash(
    archive_bookmark_environment: _ArchivedBookmarkEnvironment,
) -> None:
    bookmark = _bookmark_v3(archive_bookmark_environment)
    keys = (
        "original_monthly_source_reference_external_sha256",
        "original_monthly_artifact_descriptor_external_sha256",
        "archive_reference_external_sha256",
        "archive_artifact_descriptor_external_sha256",
    )
    for key in keys:
        payload = bookmark.to_dict()
        old = str(payload[key])
        payload[key] = "0" * 64 if old != "0" * 64 else "1" * 64
        with pytest.raises(
            DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3Error,
            match="recipe_page_or_external_anchor_mismatch",
        ):
            DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3.from_dict(
                _rehashed_bookmark(payload)
            )


def test_archived_bookmark_v3_rejects_tampered_selected_facts_on_exact_verify(
    archive_bookmark_environment: _ArchivedBookmarkEnvironment,
) -> None:
    environment = archive_bookmark_environment
    bookmark = _bookmark_v3(environment)
    payload = bookmark.to_dict()
    context = json.loads(str(payload["selected_fact_context_json"]))
    context["monthly_projected_fact"]["growth_percent"] = "999.0"
    payload["selected_fact_context_json"] = _canonical(context)
    payload["selected_fact_context_identity_sha256"] = hashlib.sha256(
        str(payload["selected_fact_context_json"]).encode("utf-8")
    ).hexdigest()
    forged = DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3.from_dict(
        _rehashed_bookmark(payload)
    )

    with pytest.raises(
        DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3Error,
        match="selected_fact_context_mismatch",
    ):
        forged.verify_exact_row(environment.exact)


def test_archived_bookmark_v3_rejects_wrong_page_and_stock_against_exact_source(
    archive_bookmark_environment: _ArchivedBookmarkEnvironment,
) -> None:
    environment = archive_bookmark_environment
    bookmark = _bookmark_v3(environment)
    payload = bookmark.to_dict()
    changed_recipe = bookmark.saved_recipe.with_page(1, 8)
    payload["saved_recipe_json"] = changed_recipe.to_json()
    payload["selected_page_request_json"] = changed_recipe.base_recipe.page_request_json
    wrong_page = DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3.from_dict(
        _rehashed_bookmark(payload)
    )
    with pytest.raises(
        DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3Error,
        match="exact_source_recipe_or_scope_mismatch",
    ):
        wrong_page.verify_exact_row(environment.exact)

    payload = bookmark.to_dict()
    payload["selected_stock_code"] = "9999"
    payload["selected_stock_name"] = "9999"
    with pytest.raises(
        DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3Error,
        match="selected_fact_context_invalid",
    ):
        DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3.from_dict(
            _rehashed_bookmark(payload)
        )


def test_archived_bookmark_v3_rejects_other_source_token_even_with_same_data(
    archive_bookmark_environment: _ArchivedBookmarkEnvironment,
) -> None:
    environment = archive_bookmark_environment
    bookmark = _bookmark_v3(environment)
    root3 = environment.temp / "other-original-reference-artifacts"
    root4 = environment.temp / "other-archive-reference-artifacts"
    root3.mkdir()
    root4.mkdir()
    other = open_daily_market_technical_official_disposition_revenue_archived_bundle_source_v3(
        archive_parent=environment.temp / "other-saved-monthly-archives",
        archived_reference_artifact_root=root4,
        archived_artifact_id="other-archive",
        bundle_output_root=environment.bundle.bundle_root,
        bundle_identity_sha256=environment.bundle.reference.bundle_identity_sha256,
        expected_manifest_sha256=environment.bundle.reference.manifest_sha256,
        row_scope_filter=_ROW_SCOPES,
        operation_root=environment.temp / "other-operation",
        monthly_provider=environment.provider,
        daily_monthly_cohort_reader=environment.reader,
        monthly_reference_artifact_root=root3,
        artifact_id="other-monthly",
        protected_roots=_PROTECTED_ROOTS,
        ma_states=("unknown",),
        minimum_yoy_percent=Decimal("0"),
        condition_combine_mode="OR",
        unknown_policy="include",
        sort_clauses=(
            DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2(
                "monthly_revenue_yoy_percent", "desc"
            ),
            DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2("stock_code", "asc"),
        ),
        page_index=0,
        page_size=8,
    )
    try:
        with pytest.raises(
            DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3Error,
            match="exact_stable_source_identity_mismatch",
        ):
            bookmark.verify_exact_row(other)
    finally:
        other.close()


def test_archived_bookmark_v3_alignment_allows_only_reissued_ids(
    archive_bookmark_environment: _ArchivedBookmarkEnvironment,
) -> None:
    environment = archive_bookmark_environment
    recipe = environment.exact.saved_recipe
    query = environment.exact.query
    payload = query.to_dict()
    for key in (
        "monthly_yoy_read_session_identity_sha256",
        "monthly_yoy_index_identity_sha256",
        "monthly_yoy_finished_cohort_identity_sha256",
        "monthly_yoy_source_clock_identity_sha256",
        "monthly_source_reference_external_sha256",
    ):
        payload[key] = "f" * 64 if payload[key] != "f" * 64 else "e" * 64
    reissued = DailyMarketTechnicalOfficialDispositionRevenueQueryV2.from_dict(
        _rehashed_query(payload)
    )
    assert archived_revenue_query_matches_recipe_v3(reissued, recipe)

    changed = query.to_dict()
    changed["minimum_yoy_percent"] = "999"
    altered = DailyMarketTechnicalOfficialDispositionRevenueQueryV2.from_dict(
        _rehashed_query(changed)
    )
    assert not archived_revenue_query_matches_recipe_v3(altered, recipe)


def test_archived_bookmark_v3_codec_is_strict_and_decode_is_not_qualification(
    archive_bookmark_environment: _ArchivedBookmarkEnvironment,
) -> None:
    bookmark = _bookmark_v3(archive_bookmark_environment)
    raw = bookmark.to_json()
    decoded = DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3.from_json(raw)
    assert decoded.to_dict()["bookmark_is_reader_qualification"] is False
    assert decoded.historical_pit_eligible is False
    assert decoded.availability_status == "unknown"

    with pytest.raises(
        DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3Error,
        match="json_duplicate_key",
    ):
        DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3.from_json(
            raw[:-1] + ',"source":"duplicate"}'
        )

    payload = bookmark.to_dict()
    payload["unexpected"] = "field"
    with pytest.raises(
        DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3Error,
        match="fields_invalid",
    ):
        DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3.from_dict(
            _rehashed_bookmark(payload)
        )

    with pytest.raises(
        DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3Error,
        match="exact_read_invalid",
    ):
        decoded.verify_exact_row(cast(Any, object()))


def test_archived_bookmark_v3_verify_cancellation_is_strict(
    archive_bookmark_environment: _ArchivedBookmarkEnvironment,
) -> None:
    bookmark = _bookmark_v3(archive_bookmark_environment)
    with pytest.raises(
        DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3Error,
        match="cancelled",
    ):
        bookmark.verify_exact_row(
            archive_bookmark_environment.exact,
            cancel_callback=lambda: True,
        )
    with pytest.raises(
        DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3Error,
        match="cancel_callback_invalid",
    ):
        DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3.from_exact_read(
            archive_bookmark_environment.exact,
            stock_code="1000",
            cancel_callback=lambda: 1,
        )
