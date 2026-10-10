"""QA 專用複合 reader 邊界候選；重用真實 public-owner fixture，尚未執行。"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

import app_module.daily_market_technical_official_disposition_composite_query_v1 as composite
from app_module.daily_market_technical_official_disposition_query_v1 import (
    DailyMarketTechnicalOfficialDispositionQueryV1,
)


_REPOSITORY_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "app_module").is_dir() and (parent / "tests").is_dir()
)
_TESTS_ROOT = str(_REPOSITORY_ROOT / "tests")
if _TESTS_ROOT not in sys.path:
    sys.path.insert(0, _TESTS_ROOT)

# 直接重用 repo 內安裝且已通過的真實 257 母體 public-owner fixture。
pytest_plugins = (
    "test_daily_market_technical_official_disposition_composite_reader_v1",
)


@pytest.fixture(scope="module")
def full257_audit_sorted_result(full257_audit_owner):
    owner = full257_audit_owner
    query = composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1.create(
        owner.session.query,
        projection_group_session_identity_sha256=owner.group.identity_sha256,
        condition_combine_mode="AND",
        unknown_policy="include",
        sort_clauses=(
            composite.DailyMarketTechnicalOfficialDispositionCompositeSortClauseV1(
                "kdj_state", "desc",
            ),
            composite.DailyMarketTechnicalOfficialDispositionCompositeSortClauseV1(
                "stock_code", "asc",
            ),
        ),
    )
    assert query.active_groups == (False, False, False, False)
    return owner.session.execute_composite_query_v1(query)


@pytest.fixture(scope="module")
def full257_audit_kdj_only_sorted_result(full257_audit_owner):
    owner = full257_audit_owner
    query = composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1.create(
        owner.session.query,
        projection_group_session_identity_sha256=owner.group.identity_sha256,
        condition_combine_mode="AND",
        unknown_policy="include",
        sort_clauses=(
            composite.DailyMarketTechnicalOfficialDispositionCompositeSortClauseV1(
                "kdj_state", "asc",
            ),
        ),
    )
    assert query.active_groups == (False, False, False, False)
    return owner.session.execute_composite_query_v1(query)


def test_full257_descending_non_stock_sort_keeps_ascending_stock_tie_and_reopens_page(
    bundle_fixture,
    full257_audit_owner,
    full257_audit_sorted_result,
) -> None:
    owner = full257_audit_owner
    result = full257_audit_sorted_result
    kdj_states = {entry.state for entry in owner.group.kdj_entries}
    assert len(kdj_states) == 1
    assert kdj_states <= {"match", "no_match"}

    keys = result.ordered_sort_keys
    assert len(keys) == 258
    assert {key.sort_values[0].value for key in keys[:-1]} == kdj_states
    assert keys[-1].sort_values[0].value is None
    assert tuple(key.stock_code for key in keys[:-1]) == bundle_fixture.included_codes
    assert keys[-1].stock_code == bundle_fixture.excluded_code

    request = composite.DailyMarketTechnicalOfficialDispositionCompositePageRequestV1.create(
        result.query,
        page_index=0,
        page_size=256,
    )
    reopened_request = composite.DailyMarketTechnicalOfficialDispositionCompositePageRequestV1.from_json(
        request.to_json(),
    )
    assert reopened_request == request
    original_page = result.read_page_request(request.to_json())
    reopened_page = result.read_page_request(reopened_request)
    assert original_page.page_identity_sha256 == reopened_page.page_identity_sha256
    assert tuple(row.fact_row.stock_code for row in original_page.rows) == tuple(
        bundle_fixture.included_codes[:256]
    )
    last_page = result.read_page(1, 256)
    assert tuple(row.fact_row.stock_code for row in last_page.rows) == (
        bundle_fixture.included_codes[-1],
        bundle_fixture.excluded_code,
    )


def test_explicit_descending_stock_code_tie_break_is_rejected(
    full257_audit_owner,
) -> None:
    owner = full257_audit_owner
    with pytest.raises(
        composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1Error,
        match="stock_code_tiebreak_invalid",
    ):
        composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1.create(
            owner.session.query,
            projection_group_session_identity_sha256=owner.group.identity_sha256,
            condition_combine_mode="AND",
            unknown_policy="include",
            sort_clauses=(
                composite.DailyMarketTechnicalOfficialDispositionCompositeSortClauseV1(
                    "kdj_state", "desc",
                ),
                composite.DailyMarketTechnicalOfficialDispositionCompositeSortClauseV1(
                    "stock_code", "desc",
                ),
            ),
        )


def test_kdj_only_sort_uses_default_ascending_stock_code_tie_break(
    bundle_fixture,
    full257_audit_owner,
    full257_audit_kdj_only_sorted_result,
) -> None:
    owner = full257_audit_owner
    result = full257_audit_kdj_only_sorted_result
    kdj_states = {entry.state for entry in owner.group.kdj_entries}
    assert len(kdj_states) == 1
    assert kdj_states <= {"match", "no_match"}

    keys = result.ordered_sort_keys
    assert len(keys) == 258
    assert {key.sort_values[0].value for key in keys[:-1]} == kdj_states
    assert keys[-1].sort_values[0].value is None
    assert tuple(key.stock_code for key in keys[:-1]) == bundle_fixture.included_codes
    assert keys[-1].stock_code == bundle_fixture.excluded_code


def test_page_request_from_other_canonical_query_is_rejected(
    full257_audit_owner,
    full257_audit_sorted_result,
) -> None:
    owner = full257_audit_owner
    result = full257_audit_sorted_result
    other_query = composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1.create(
        owner.session.query,
        projection_group_session_identity_sha256=owner.group.identity_sha256,
        condition_combine_mode="AND",
        unknown_policy="include",
        sort_clauses=(
            composite.DailyMarketTechnicalOfficialDispositionCompositeSortClauseV1(
                "kdj_state", "asc",
            ),
            composite.DailyMarketTechnicalOfficialDispositionCompositeSortClauseV1(
                "stock_code", "asc",
            ),
        ),
    )
    other_request = composite.DailyMarketTechnicalOfficialDispositionCompositePageRequestV1.create(
        other_query,
        page_index=0,
        page_size=256,
    )
    with pytest.raises(
        composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1Error,
        match="page_request_query_mismatch",
    ):
        result.read_page_request(other_request.to_json())


def test_issued_owner_rejects_wrong_f17_query_group_and_session(
    full257_audit_owner,
    full257_no_match_owner,
) -> None:
    owner = full257_audit_owner
    other_owner = full257_no_match_owner
    query = composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1.create(
        owner.session.query,
        projection_group_session_identity_sha256=owner.group.identity_sha256,
        condition_combine_mode="AND",
        unknown_policy="include",
    )

    base = owner.session.query
    alternate_f17_query = DailyMarketTechnicalOfficialDispositionQueryV1.create(
        technical_query=base.technical_query,
        decision_cutoff=base.decision_cutoff,
        bundle_output_root=base.bundle_output_root,
        bundle_identity_sha256=base.bundle_identity_sha256,
        expected_manifest_sha256=base.expected_manifest_sha256,
        market_assignment_pin_identity_sha256=base.market_assignment_pin_identity_sha256,
        official_disposal_pin_identity_sha256=base.official_disposal_pin_identity_sha256,
        row_scope_filter=base.row_scope_filter,
        market_assignment_states=("assigned_twse",),
        official_disposal_states=base.official_disposal_states,
        outer_stock_filter_mode=base.outer_stock_filter_mode,
        outer_stock_codes=base.outer_stock_codes,
        sort_clauses=base.sort_clauses,
    )
    wrong_f17_query = composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1.create(
        alternate_f17_query,
        projection_group_session_identity_sha256=owner.group.identity_sha256,
        condition_combine_mode="AND",
        unknown_policy="include",
    )
    with pytest.raises(
        composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1Error,
        match="reader_issuer_binding_mismatch",
    ):
        composite._validate_reader_issuer_binding(
            wrong_f17_query,
            owner.session,
            owner.group,
        )

    wrong_group_query = composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1.create(
        owner.session.query,
        projection_group_session_identity_sha256=other_owner.group.identity_sha256,
        condition_combine_mode="AND",
        unknown_policy="include",
    )
    with pytest.raises(
        composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1Error,
        match="reader_issuer_binding_mismatch",
    ):
        composite._validate_reader_issuer_binding(
            wrong_group_query,
            owner.session,
            other_owner.group,
        )

    with pytest.raises(
        composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1Error,
        match="reader_issuer_binding_mismatch",
    ):
        composite._validate_reader_issuer_binding(
            query,
            other_owner.session,
            other_owner.group,
        )


def test_real_issued_result_rejects_source_pin_from_other_group_state(
    full257_audit_owner,
    full257_audit_sorted_result,
) -> None:
    owner = full257_audit_owner
    result = full257_audit_sorted_result
    source_pins = list(result.source_pins)
    pin_index = next(
        index
        for index, (key, _value) in enumerate(source_pins)
        if key == "ma_index_identity_sha256"
    )
    key, _value = source_pins[pin_index]
    source_pins[pin_index] = (key, "1" * 64)

    with pytest.raises(
        composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1Error,
        match="result_source_pin_owner_mismatch",
    ):
        composite._validate_result_source_pins_with_issuer(
            result.query,
            tuple(source_pins),
            owner.session,
            owner.group,
        )
