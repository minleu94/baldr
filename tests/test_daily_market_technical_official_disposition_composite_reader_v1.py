"""QA 專用 F17 複合 reader 整合測試候選；目前只作靜態審閱，尚未執行。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Callable, Iterator, Literal, cast

import pytest

import app_module.daily_market_technical_official_disposition_composite_query_v1 as composite
from app_module.daily_market_technical_official_disposition_bundle_v1 import (
    DailyMarketTechnicalOfficialDispositionBundleSelectedRowsV1,
    DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1,
    DailyMarketTechnicalOfficialDispositionFactRowV1,
)
from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
    DailyMarketTechnicalOfficialDispositionQueryReaderV1Cancelled,
    DailyMarketTechnicalOfficialDispositionReadSessionV1,
    open_daily_market_technical_official_disposition_projection_group_session_v2,
)
from app_module.daily_market_technical_official_disposition_query_v1 import (
    DailyMarketTechnicalOfficialDispositionQueryV1,
)
from app_module.daily_market_technical_parent_v4_query import (
    DailyMarketTechnicalRuleStateFilterV4,
)
from app_module.daily_market_technical_universe_projection_group_session_v2 import (
    DailyMarketTechnicalUniverseProjectionGroupSessionV2,
)
from app_module.daily_market_technical_universe_v4_query import (
    DailyMarketTechnicalUniverseV4ReadSession,
)
from test_daily_market_technical_official_disposition_bundle_v1 import (
    _BundleFixture,
    bundle_fixture,
)
from test_daily_market_technical_official_disposition_query_reader_v1 import (
    exact_p01_session,
    exact_query,
)


@dataclass(frozen=True, slots=True)
class _FullOwner:
    session: DailyMarketTechnicalOfficialDispositionReadSessionV1
    group: DailyMarketTechnicalUniverseProjectionGroupSessionV2
    p01_rule_key: str
    observed_p01_state: Literal["match", "no_match"]
    kdj_state: Literal["match", "no_match"]


@dataclass(frozen=True, slots=True)
class _AuditOwner:
    session: DailyMarketTechnicalOfficialDispositionReadSessionV1
    group: DailyMarketTechnicalUniverseProjectionGroupSessionV2


def _verified_p01_rows(
    session: DailyMarketTechnicalUniverseV4ReadSession,
) -> tuple[object, ...]:
    query = session.create_query(
        rule_state_filters=(),
        combine_mode="AND",
        stock_filter=(),
        sort_key="stock_code",
        descending=False,
        page_index=0,
        page_size=256,
    )
    selection = session.select_stock_codes(query)
    assert selection.matching_count == 257
    page_count = (selection.matching_count + 255) // 256
    rows = tuple(
        row
        for page_index in range(page_count)
        for row in session.read_selection_page(
            selection,
            page_index=page_index,
            page_size=256,
        ).rows
    )
    assert len(rows) == 257
    return rows


def _opposite(state: str) -> Literal["match", "no_match"]:
    assert state in {"match", "no_match"}
    return "no_match" if state == "match" else "match"


def _outer_query_with_p01_filter(
    base: DailyMarketTechnicalOfficialDispositionQueryV1,
    p01_session: DailyMarketTechnicalUniverseV4ReadSession,
    rule_key: str,
    accepted_state: Literal["match", "no_match"],
) -> DailyMarketTechnicalOfficialDispositionQueryV1:
    technical_query = p01_session.create_query(
        rule_state_filters=(DailyMarketTechnicalRuleStateFilterV4.create(
            rule_key,
            (accepted_state,),
        ),),
        combine_mode="AND",
        stock_filter=(),
        sort_key="stock_code",
        descending=False,
        page_index=0,
        page_size=1,
    )
    return DailyMarketTechnicalOfficialDispositionQueryV1.create(
        technical_query=technical_query,
        decision_cutoff=base.decision_cutoff,
        bundle_output_root=base.bundle_output_root,
        bundle_identity_sha256=base.bundle_identity_sha256,
        expected_manifest_sha256=base.expected_manifest_sha256,
        market_assignment_pin_identity_sha256=base.market_assignment_pin_identity_sha256,
        official_disposal_pin_identity_sha256=base.official_disposal_pin_identity_sha256,
        row_scope_filter=base.row_scope_filter,
        market_assignment_states=base.market_assignment_states,
        official_disposal_states=base.official_disposal_states,
        outer_stock_filter_mode="all",
        outer_stock_codes=(),
        sort_clauses=base.sort_clauses,
    )


def _outer_query_without_p01_filter(
    base: DailyMarketTechnicalOfficialDispositionQueryV1,
    p01_session: DailyMarketTechnicalUniverseV4ReadSession,
) -> DailyMarketTechnicalOfficialDispositionQueryV1:
    technical_query = p01_session.create_query(
        rule_state_filters=(),
        combine_mode="AND",
        stock_filter=(),
        sort_key="stock_code",
        descending=False,
        page_index=0,
        page_size=1,
    )
    return DailyMarketTechnicalOfficialDispositionQueryV1.create(
        technical_query=technical_query,
        decision_cutoff=base.decision_cutoff,
        bundle_output_root=base.bundle_output_root,
        bundle_identity_sha256=base.bundle_identity_sha256,
        expected_manifest_sha256=base.expected_manifest_sha256,
        market_assignment_pin_identity_sha256=base.market_assignment_pin_identity_sha256,
        official_disposal_pin_identity_sha256=base.official_disposal_pin_identity_sha256,
        row_scope_filter=base.row_scope_filter,
        market_assignment_states=base.market_assignment_states,
        official_disposal_states=base.official_disposal_states,
        outer_stock_filter_mode="all",
        outer_stock_codes=(),
        sort_clauses=base.sort_clauses,
    )


@pytest.fixture(scope="module")
def full257_no_match_owner(
    bundle_fixture: _BundleFixture,
    exact_p01_session: object,
    exact_query: DailyMarketTechnicalOfficialDispositionQueryV1,
) -> _FullOwner:
    """以真 P01、F17 bundle 與 public group opener 發行完整母體 owner。"""
    p01 = cast(DailyMarketTechnicalUniverseV4ReadSession, exact_p01_session)
    p01_rows = _verified_p01_rows(p01)
    rule_keys = tuple(rule.key for rule in p01_rows[0].rules)
    concrete_uniform_states = tuple(
        (key, next(iter(states)))
        for key in rule_keys
        if len(states := {row.rule(key).state for row in p01_rows}) == 1
        and next(iter(states)) in {"match", "no_match"}
    )
    assert concrete_uniform_states, "257 股 fixture 必須有一條一致且可評估的 P01 rule"
    rule_key, observed_state_text = concrete_uniform_states[0]
    observed_state = cast(Literal["match", "no_match"], observed_state_text)
    outer_query = _outer_query_with_p01_filter(
        exact_query,
        p01,
        rule_key,
        _opposite(observed_state),
    )
    read_session = open_daily_market_technical_official_disposition_projection_group_session_v2(
        outer_query,
    )
    group = read_session.projection_group_session
    assert group is not None
    assert read_session.query.technical_query.stock_filter == ()
    assert read_session._selection.stock_codes == bundle_fixture.included_codes
    assert len(read_session._selection.stock_codes) == 257
    assert len(group.ma_index.entries) == len(group.kdj_entries) == len(group.volatility_entries) == 257
    assert tuple(entry.stock_code for entry in group.ma_index.entries) == bundle_fixture.included_codes
    assert tuple(entry.stock_code for entry in group.kdj_entries) == bundle_fixture.included_codes
    assert tuple(entry.stock_code for entry in group.volatility_entries) == bundle_fixture.included_codes

    actual_parent_rows = tuple(read_session._iter_selection_rows(None))
    assert len(actual_parent_rows) == 257
    assert {row.rule(rule_key).state for row in actual_parent_rows} == {observed_state}
    kdj_states = {entry.state for entry in group.kdj_entries}
    assert len(kdj_states) == 1 and kdj_states <= {"match", "no_match"}
    kdj_state = cast(Literal["match", "no_match"], next(iter(kdj_states)))
    return _FullOwner(read_session, group, rule_key, observed_state, kdj_state)


@pytest.fixture(scope="module")
def full257_audit_owner(
    bundle_fixture: _BundleFixture,
    exact_p01_session: object,
    exact_query: DailyMarketTechnicalOfficialDispositionQueryV1,
) -> _AuditOwner:
    """以 neutral F17/P01 query 與真 public opener 發行完整 audit 母體。"""
    p01 = cast(DailyMarketTechnicalUniverseV4ReadSession, exact_p01_session)
    outer_query = _outer_query_without_p01_filter(exact_query, p01)
    read_session = open_daily_market_technical_official_disposition_projection_group_session_v2(
        outer_query,
    )
    group = read_session.projection_group_session
    assert group is not None
    assert read_session.query.technical_query.rule_state_filters == ()
    assert read_session._selection.stock_codes == bundle_fixture.included_codes
    assert len(read_session._selection.stock_codes) == 257
    assert len(group.ma_index.entries) == len(group.kdj_entries) == len(group.volatility_entries) == 257
    assert tuple(entry.stock_code for entry in group.ma_index.entries) == bundle_fixture.included_codes
    assert tuple(entry.stock_code for entry in group.kdj_entries) == bundle_fixture.included_codes
    assert tuple(entry.stock_code for entry in group.volatility_entries) == bundle_fixture.included_codes
    return _AuditOwner(read_session, group)


def _composite_query(
    owner: _FullOwner,
    *,
    combine: Literal["AND", "OR"],
    unknown_policy: Literal["include", "exclude"] = "exclude",
    use_kdj: bool = True,
    use_ma: bool = False,
) -> composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1:
    return composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1.create(
        owner.session.query,
        projection_group_session_identity_sha256=owner.group.identity_sha256,
        ma_states=("match",) if use_ma else None,
        kdj_states=(owner.kdj_state,) if use_kdj else None,
        condition_combine_mode=combine,
        unknown_policy=unknown_policy,
    )


def _assert_full257_population(
    owner: _FullOwner,
    result: composite.DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
) -> None:
    population = result.counts.base_f17_counts.population
    assert population.declared_count == 258
    assert population.included_count == 257
    assert population.processed_count == 257
    assert population.excluded_count == 1
    assert population.pending_count == 0
    assert owner.session._selection.stock_codes == tuple(sorted(owner.session._selection.stock_codes))
    assert len(owner.group.ma_index.entries) == 257


@pytest.fixture(scope="module")
def full257_or_result(
    full257_no_match_owner: _FullOwner,
) -> composite.DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1:
    owner = full257_no_match_owner
    query = _composite_query(owner, combine="OR")
    return owner.session.execute_composite_query_v1(query)


def test_full257_or_rescue_and_and_intersection(
    full257_no_match_owner: _FullOwner,
    full257_or_result: composite.DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
) -> None:
    owner = full257_no_match_owner
    or_result = full257_or_result
    _assert_full257_population(owner, or_result)
    assert or_result.counts.base_f17_counts.matching_count == 0
    assert or_result.visible_count == 257
    assert dict(or_result.counts.composite_truth_counts) == {
        "match": 257,
        "no_match": 0,
        "unknown": 0,
        "not_applicable": 0,
        "not_evaluated": 1,
    }

    first_page = or_result.read_page(0, 256)
    last_page = or_result.read_page(1, 256)
    visible_rows = (*first_page.rows, *last_page.rows)
    assert len(first_page.rows) == 256
    assert len(last_page.rows) == 1
    assert tuple(row.fact_row.stock_code for row in visible_rows) == owner.session._selection.stock_codes
    assert all(row.evaluation.technical_truth == "no_match" for row in visible_rows)
    assert all(row.evaluation.kdj_truth == "match" for row in visible_rows)
    assert all(row.evaluation.composite_truth == "match" and row.evaluation.visible for row in visible_rows)

    and_result = owner.session.execute_composite_query_v1(
        _composite_query(owner, combine="AND"),
    )
    _assert_full257_population(owner, and_result)
    assert and_result.counts.base_f17_counts.matching_count == 0
    assert and_result.visible_count == 0
    assert dict(and_result.counts.composite_truth_counts) == {
        "match": 0,
        "no_match": 257,
        "unknown": 0,
        "not_applicable": 0,
        "not_evaluated": 1,
    }


def test_full257_all_inactive_audit_pages_declared_population_at_256_boundary(
    bundle_fixture: _BundleFixture,
    full257_audit_owner: _AuditOwner,
) -> None:
    owner = full257_audit_owner
    query = composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1.create(
        owner.session.query,
        projection_group_session_identity_sha256=owner.group.identity_sha256,
        condition_combine_mode="AND",
        unknown_policy="include",
    )
    assert query.active_groups == (False, False, False, False)

    result = owner.session.execute_composite_query_v1(query)
    population = result.counts.base_f17_counts.population
    assert (
        population.declared_count,
        population.included_count,
        population.excluded_count,
        population.processed_count,
        population.pending_count,
    ) == (258, 257, 1, 257, 0)
    assert result.counts.hard_eligible_count == 258
    assert result.counts.active_evaluable_count == 0
    assert result.counts.audit_visible_count == 258
    assert result.visible_count == 258
    assert dict(result.counts.composite_truth_counts) == {
        "match": 0,
        "no_match": 0,
        "unknown": 0,
        "not_evaluated": 1,
        "not_applicable": 257,
    }

    first_page = result.read_page(0, 256)
    final_page = result.read_page(1, 256)
    rows = (*first_page.rows, *final_page.rows)
    assert len(first_page.rows) == 256
    assert len(final_page.rows) == 2
    assert tuple(row.fact_row.stock_code for row in rows) == tuple(
        sorted((*bundle_fixture.included_codes, bundle_fixture.excluded_code))
    )
    assert all(row.evaluation.audit_visible and row.evaluation.visible for row in rows)
    assert sum(row.evaluation.composite_truth == "not_evaluated" for row in rows) == 1
    assert sum(row.technical_row is None for row in rows) == 1


def test_global_unknown_policy_include_and_exclude_on_full257_owner(
    full257_no_match_owner: _FullOwner,
) -> None:
    owner = full257_no_match_owner
    assert all(entry.ma_state == "unknown" for entry in owner.group.ma_index.entries)
    include_result = owner.session.execute_composite_query_v1(
        _composite_query(
            owner,
            combine="OR",
            unknown_policy="include",
            use_kdj=False,
            use_ma=True,
        ),
    )
    exclude_result = owner.session.execute_composite_query_v1(
        _composite_query(
            owner,
            combine="OR",
            unknown_policy="exclude",
            use_kdj=False,
            use_ma=True,
        ),
    )
    _assert_full257_population(owner, include_result)
    _assert_full257_population(owner, exclude_result)
    assert include_result.visible_count == 257
    assert include_result.counts.unknown_policy_included_count == 257
    assert exclude_result.visible_count == 0
    assert exclude_result.counts.unknown_policy_excluded_count == 257


def test_late_execute_cancellation_never_returns_partial_result(
    full257_no_match_owner: _FullOwner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = full257_no_match_owner
    query = _composite_query(owner, combine="OR")
    cancelled = {"value": False}
    original = type(owner.session)._iter_verified_bundle_rows

    def cancel_after_ten_verified_rows(
        session: DailyMarketTechnicalOfficialDispositionReadSessionV1,
        callback: Callable[[], object] | None,
    ) -> Iterator[DailyMarketTechnicalOfficialDispositionFactRowV1]:
        for index, fact in enumerate(original(session, callback)):
            yield fact
            if session is owner.session and index == 9:
                # 每筆仍由真 verified reader 讀取；此處只安排延後取消。
                cancelled["value"] = True

    monkeypatch.setattr(
        type(owner.session),
        "_iter_verified_bundle_rows",
        cancel_after_ten_verified_rows,
    )
    result = None
    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryReaderV1Cancelled):
        result = owner.session.execute_composite_query_v1(
            query,
            cancel_callback=lambda: cancelled["value"],
        )
    assert cancelled["value"] is True
    assert result is None


def test_page_selected_read_cancellation_is_mapped_and_returns_no_page(
    full257_or_result: composite.DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected_read_codes: list[tuple[str, ...]] = []
    state_type = DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1
    original_read_selected_rows = state_type.read_selected_rows
    selected_read_entered = False

    def observed_read_selected_rows(
        state: DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1,
        explicit_stock_codes: Sequence[str],
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> DailyMarketTechnicalOfficialDispositionBundleSelectedRowsV1:
        nonlocal selected_read_entered
        selected_read_entered = True
        selected_read_codes.append(tuple(explicit_stock_codes))
        return original_read_selected_rows(
            state,
            explicit_stock_codes,
            cancel_callback=cancel_callback,
        )

    monkeypatch.setattr(state_type, "read_selected_rows", observed_read_selected_rows)

    def cancel_on_selected_row_read() -> bool:
        return selected_read_entered

    page = None
    with pytest.raises(DailyMarketTechnicalOfficialDispositionQueryReaderV1Cancelled):
        page = full257_or_result.read_page(
            0,
            1,
            cancel_callback=cancel_on_selected_row_read,
        )
    assert selected_read_entered is True
    assert selected_read_codes == [("1000",)]
    assert page is None
