"""F17／P01／MA／KDJ／波動率全母體複合查詢純契約測試。"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Literal, cast

import pytest

import app_module.daily_market_technical_official_disposition_composite_query_v1 as composite
import app_module.daily_market_technical_official_disposition_query_v1 as f17_module
from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
    DailyMarketTechnicalOfficialDispositionQueryCountsV1,
    DailyMarketTechnicalOfficialDispositionReadSessionV1,
    DailyMarketTechnicalOfficialDispositionRuleStateCountsV1,
    open_daily_market_technical_official_disposition_projection_group_session_v2,
)
from app_module.daily_market_technical_official_disposition_bundle_v1 import (
    DailyMarketTechnicalOfficialDispositionFactRowV1,
)
from app_module.daily_market_technical_official_disposition_query_v1 import (
    DailyMarketTechnicalOfficialDispositionQueryV1,
    DailyMarketTechnicalOfficialDispositionSortClauseV1,
    DailyMarketTechnicalOfficialDispositionSortValueV1,
)
from app_module.daily_market_technical_universe_v4_query import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_SCHEMA,
    DailyMarketTechnicalUniverseV4Query,
)
from app_module.daily_market_technical_universe_v4_store import (
    DailyMarketTechnicalUniverseV4Counts,
)
from app_module.daily_market_technical_universe_projection_group_session_v2 import (
    DailyMarketTechnicalUniverseProjectionGroupSessionV2,
)
from test_daily_market_technical_official_disposition_bundle_v1 import (  # type: ignore[import-not-found]
    _BundleFixture,
    bundle_fixture,
)
from test_daily_market_technical_official_disposition_query_reader_v1 import (  # type: ignore[import-not-found]
    exact_query,
    exact_p01_session,
)


_DECISION_DATE = date(2026, 10, 7)
_CUTOFF = datetime.fromisoformat("2026-10-07T16:00:00+08:00")
_RULE_KEYS = ("r1", "r2", "r3", "r4", "r5")


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _p01_query(
    *,
    rule_filters: tuple[dict[str, object], ...] = (),
    stock_filter: tuple[str, ...] = (),
) -> DailyMarketTechnicalUniverseV4Query:
    body: dict[str, object] = {
        "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_SCHEMA,
        "store_output_root": r"C:\synthetic\technical-store",
        "generation_identity_sha256": "a" * 64,
        "plan_identity_sha256": "b" * 64,
        "plan_sha256": "c" * 64,
        "receipt_identity_sha256": "d" * 64,
        "receipt_sha256": "e" * 64,
        "receipt_status": "partial",
        "cohort_identity_sha256": "f" * 64,
        "source_clock_identity_sha256": "1" * 64,
        "method_contracts_sha256": "2" * 64,
        "universe_id": "synthetic-universe",
        "population_version": "fixture-v1",
        "decision_date": _DECISION_DATE.isoformat(),
        "declared_count": 4,
        "included_count": 3,
        "excluded_count": 1,
        "segment_count": 1,
        "counts": {
            "declared_count": 4,
            "included_count": 3,
            "excluded_count": 1,
            "processed_count": 2,
            "pending_count": 1,
            "missing_data_count": 0,
            "missing_data_pending_count": 1,
        },
        "method_rule_keys": list(_RULE_KEYS),
        "state_filters": list(rule_filters),
        "combine_mode": "AND",
        "stock_filter": list(stock_filter),
        "sort_key": "stock_code",
        "descending": False,
        "page_index": 0,
        "page_size": 1,
    }
    body["query_identity_sha256"] = _sha(body)
    return DailyMarketTechnicalUniverseV4Query.from_dict(body)


def _f17_query(
    *,
    rule_filters: tuple[dict[str, object], ...] = (),
    sort_clauses: tuple[DailyMarketTechnicalOfficialDispositionSortClauseV1, ...] = (),
) -> DailyMarketTechnicalOfficialDispositionQueryV1:
    return DailyMarketTechnicalOfficialDispositionQueryV1.create(
        technical_query=_p01_query(rule_filters=rule_filters),
        decision_cutoff=_CUTOFF,
        bundle_output_root=Path(r"C:\synthetic\f17-bundle"),
        bundle_identity_sha256="3" * 64,
        expected_manifest_sha256="4" * 64,
        market_assignment_pin_identity_sha256="5" * 64,
        official_disposal_pin_identity_sha256="6" * 64,
        row_scope_filter=("included_processed", "included_pending", "excluded"),
        sort_clauses=sort_clauses,
    )


def _query(
    *,
    rule_filters: tuple[dict[str, object], ...] = (),
    ma_states: tuple[composite.MaState, ...] | None = None,
    kdj_states: tuple[composite.KDJState, ...] | None = None,
    bandwidth_min_pct: Decimal | None = None,
    atr14_min_pct: Decimal | None = None,
    combine: composite.CombineMode = "AND",
    unknown_policy: composite.UnknownPolicy = "include",
    sorts: tuple[composite.DailyMarketTechnicalOfficialDispositionCompositeSortClauseV1, ...] = (),
    f17_sort: tuple[DailyMarketTechnicalOfficialDispositionSortClauseV1, ...] = (),
) -> composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1:
    return composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1.create(
        _f17_query(rule_filters=rule_filters, sort_clauses=f17_sort),
        projection_group_session_identity_sha256="7" * 64,
        ma_states=ma_states,
        kdj_states=kdj_states,
        bandwidth_min_pct=bandwidth_min_pct,
        atr14_min_pct=atr14_min_pct,
        condition_combine_mode=combine,
        unknown_policy=unknown_policy,
        sort_clauses=sorts,
    )


def _one_code_outer_query(
    exact_query: DailyMarketTechnicalOfficialDispositionQueryV1,
    code: str,
) -> DailyMarketTechnicalOfficialDispositionQueryV1:
    return DailyMarketTechnicalOfficialDispositionQueryV1.create(
        technical_query=exact_query.technical_query,
        decision_cutoff=exact_query.decision_cutoff,
        bundle_output_root=exact_query.bundle_output_root,
        bundle_identity_sha256=exact_query.bundle_identity_sha256,
        expected_manifest_sha256=exact_query.expected_manifest_sha256,
        market_assignment_pin_identity_sha256=(
            exact_query.market_assignment_pin_identity_sha256
        ),
        official_disposal_pin_identity_sha256=(
            exact_query.official_disposal_pin_identity_sha256
        ),
        row_scope_filter=exact_query.row_scope_filter,
        market_assignment_states=exact_query.market_assignment_states,
        official_disposal_states=exact_query.official_disposal_states,
        outer_stock_filter_mode="explicit_codes",
        outer_stock_codes=(code,),
        sort_clauses=exact_query.sort_clauses,
    )


@pytest.fixture(scope="module")
def real_group_owner(
    bundle_fixture: _BundleFixture,
    exact_query: DailyMarketTechnicalOfficialDispositionQueryV1,
) -> tuple[
    DailyMarketTechnicalOfficialDispositionQueryV1,
    DailyMarketTechnicalOfficialDispositionReadSessionV1,
    DailyMarketTechnicalUniverseProjectionGroupSessionV2,
]:
    one_code_query = _one_code_outer_query(exact_query, bundle_fixture.included_codes[0])
    read_session = open_daily_market_technical_official_disposition_projection_group_session_v2(
        one_code_query,
    )
    projection_group_session = read_session.projection_group_session
    assert projection_group_session is not None
    return one_code_query, read_session, projection_group_session


def _truth_counts(
    *,
    match: int = 0,
    no_match: int = 0,
    unknown: int = 0,
    not_evaluated: int = 0,
    not_applicable: int = 0,
) -> tuple[tuple[str, int], ...]:
    return (
        ("match", match),
        ("no_match", no_match),
        ("unknown", unknown),
        ("not_evaluated", not_evaluated),
        ("not_applicable", not_applicable),
    )


def _base_counts() -> DailyMarketTechnicalOfficialDispositionQueryCountsV1:
    population = DailyMarketTechnicalUniverseV4Counts(4, 3, 1, 2, 1, 0, 1)
    return DailyMarketTechnicalOfficialDispositionQueryCountsV1(
        population=population,
        unknown_rule_stock_count=0,
        rule_state_counts=tuple(
            DailyMarketTechnicalOfficialDispositionRuleStateCountsV1(key, 2, 0, 0)
            for key in _RULE_KEYS
        ),
        market_state_counts=(("assigned_twse", 4),),
        disposal_state_counts=(("reported_active", 4),),
        truth_counts=(),
        membership_counts=(),
        matching_count=0,
    )


def test_query_round_trip_and_page_request_keep_one_identity() -> None:
    query = _query(
        rule_filters=({"rule_key": "r1", "states": ["match"]},),
        ma_states=("match", "unknown"),
        bandwidth_min_pct=Decimal("1.2500"),
        combine="OR",
        unknown_policy="exclude",
    )

    assert query.bandwidth_min_pct == Decimal("1.25")
    assert query.active_groups == (True, True, False, True)
    assert composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1.from_json(
        query.to_json()
    ) == query
    page = composite.DailyMarketTechnicalOfficialDispositionCompositePageRequestV1.create(
        query, page_index=2, page_size=25,
    )
    assert page.query.query_identity_sha256 == query.query_identity_sha256
    assert composite.DailyMarketTechnicalOfficialDispositionCompositePageRequestV1.from_json(
        page.to_json()
    ) == page


def test_context_parses_f17_once_and_pending_excluded_never_enter_or_unknown_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query = _query(
        rule_filters=({"rule_key": "r1", "states": ["match"]},),
        ma_states=("match",),
        combine="OR",
        unknown_policy="include",
    )
    f17_type = f17_module.DailyMarketTechnicalOfficialDispositionQueryV1
    original_from_json = f17_type.from_json
    calls = 0

    def counted_from_json(
        cls: type[DailyMarketTechnicalOfficialDispositionQueryV1],
        raw: bytes | str,
    ) -> DailyMarketTechnicalOfficialDispositionQueryV1:
        nonlocal calls
        calls += 1
        return original_from_json(raw)

    monkeypatch.setattr(f17_type, "from_json", classmethod(counted_from_json))
    context = composite.prepare_composite_evaluation_context_v1(query)
    after_context = calls
    assert context.active_groups == (True, True, False, False)
    assert after_context == 1

    for status in ("pending", "excluded"):
        technical = composite.evaluate_technical_group_v1(
            context, cast(DailyMarketTechnicalOfficialDispositionFactRowV1, None), None,
            technical_status=status, hard_eligible=True,
        )
        ma = composite.evaluate_ma_group_v1(
            context, cast(DailyMarketTechnicalOfficialDispositionFactRowV1, None), None, None,
            technical_status=status, hard_eligible=True,
        )
        assert technical == "not_evaluated"
        assert ma == "not_evaluated"
        evaluation = composite.evaluate_composite_predicate_v1(
            context,
            technical_truth=technical,
            ma_truth=ma,
            kdj_truth=None,
            volatility_truth=None,
            technical_status=status,
            hard_eligible=True,
        )
        assert evaluation.composite_truth == "not_evaluated"
        assert evaluation.included_by_unknown_policy is False
        assert evaluation.predicate_match is False
        assert evaluation.visible is False
    assert calls == after_context


@pytest.mark.parametrize("status", ("pending", "excluded"))
def test_inactive_query_preserves_hard_eligible_audit_browse_for_unprocessed_rows(
    status: str,
) -> None:
    context = composite.prepare_composite_evaluation_context_v1(_query())
    evaluation = composite.evaluate_composite_predicate_v1(
        context,
        technical_truth=None,
        ma_truth=None,
        kdj_truth=None,
        volatility_truth=None,
        technical_status=status,
        hard_eligible=True,
    )

    assert evaluation.composite_truth == "not_evaluated"
    assert evaluation.hard_eligible is True
    assert evaluation.active_groups == (False, False, False, False)
    assert evaluation.audit_visible is True
    assert evaluation.included_by_unknown_policy is True
    assert evaluation.predicate_match is False
    assert evaluation.visible is True


def test_hard_gate_and_active_unknown_policy_are_independent() -> None:
    context = composite.prepare_composite_evaluation_context_v1(_query(
        rule_filters=({"rule_key": "r1", "states": ["match"]},),
        ma_states=("match",),
        combine="OR",
        unknown_policy="include",
    ))
    hard_failed = composite.evaluate_composite_predicate_v1(
        context,
        technical_truth=None,
        ma_truth=None,
        kdj_truth=None,
        volatility_truth=None,
        technical_status="processed",
        hard_eligible=False,
    )
    assert hard_failed.composite_truth == "not_evaluated"
    assert hard_failed.included_by_unknown_policy is False
    assert hard_failed.visible is False

    unknown = composite.evaluate_composite_predicate_v1(
        context,
        technical_truth="unknown",
        ma_truth="no_match",
        kdj_truth=None,
        volatility_truth=None,
        technical_status="processed",
        hard_eligible=True,
    )
    assert unknown.composite_truth == "unknown"
    assert unknown.included_by_unknown_policy is True
    assert unknown.predicate_match is False
    assert unknown.visible is True

    matched = composite.evaluate_composite_predicate_v1(
        context,
        technical_truth="no_match",
        ma_truth="match",
        kdj_truth=None,
        volatility_truth=None,
        technical_status="processed",
        hard_eligible=True,
    )
    assert matched.composite_truth == "match"
    assert matched.predicate_match is True
    assert matched.visible is True


@pytest.mark.parametrize(
    ("policy", "unknown_included", "match_included"),
    (
        ("include", True, True),
        ("exclude", False, True),
        ("only", True, False),
    ),
)
def test_unknown_policy_applies_only_to_evaluated_truth(
    policy: composite.UnknownPolicy,
    unknown_included: bool,
    match_included: bool,
) -> None:
    context = composite.prepare_composite_evaluation_context_v1(_query(
        ma_states=("match",), unknown_policy=policy,
    ))
    unknown = composite.evaluate_composite_predicate_v1(
        context,
        technical_truth=None,
        ma_truth="unknown",
        kdj_truth=None,
        volatility_truth=None,
        technical_status="processed",
        hard_eligible=True,
    )
    matched = composite.evaluate_composite_predicate_v1(
        context,
        technical_truth=None,
        ma_truth="match",
        kdj_truth=None,
        volatility_truth=None,
        technical_status="processed",
        hard_eligible=True,
    )

    assert unknown.composite_truth == "unknown"
    assert unknown.included_by_unknown_policy is unknown_included
    assert matched.composite_truth == "match"
    assert matched.included_by_unknown_policy is match_included


def test_counts_keep_declared_hard_eligible_evaluable_and_not_evaluated_denominators() -> None:
    active_truth = _truth_counts(match=1, unknown=1, not_evaluated=2)
    counts = composite.DailyMarketTechnicalOfficialDispositionCompositeCountsV1(
        base_f17_counts=_base_counts(),
        ma_state_counts=(("match", 1), ("no_match", 0), ("unknown", 1)),
        kdj_state_counts=(("match", 1), ("no_match", 1), ("unknown", 0)),
        bandwidth_state_counts=(("observed", 1), ("unknown", 1)),
        atr14_state_counts=(("observed", 2), ("unknown", 0)),
        technical_truth_counts=active_truth,
        ma_truth_counts=active_truth,
        kdj_truth_counts=_truth_counts(not_applicable=4),
        volatility_truth_counts=active_truth,
        composite_truth_counts=active_truth,
        hard_eligible_truth_counts=active_truth,
        active_evaluable_truth_counts=_truth_counts(match=1, unknown=1),
        hard_eligible_count=4,
        active_evaluable_count=2,
        audit_visible_count=0,
        visible_count=2,
        unknown_policy_included_count=1,
        unknown_policy_excluded_count=0,
    )

    payload = counts.to_dict()
    assert payload["declared_count"] == 4
    assert payload["processed_count"] == 2
    assert payload["pending_count"] == 1
    assert payload["excluded_count"] == 1
    assert payload["hard_eligible_count"] == 4
    assert payload["active_evaluable_count"] == 2
    assert payload["not_evaluated_count"] == 2
    assert payload["audit_visible_count"] == 0
    assert payload["visible_count"] == 2


def _sort_key(
    query: composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1,
    stock_code: str,
    state: str | None,
) -> composite.DailyMarketTechnicalOfficialDispositionCompositeSortKeyV1:
    values = (
        DailyMarketTechnicalOfficialDispositionSortValueV1(
            "ma_alignment_state", "asc", state,
        ),
        DailyMarketTechnicalOfficialDispositionSortValueV1(
            "stock_code", "asc", stock_code,
        ),
    )
    return composite.DailyMarketTechnicalOfficialDispositionCompositeSortKeyV1(
        query_identity_sha256=query.query_identity_sha256,
        stock_code=stock_code,
        sort_values=values,
        fact_row_sha256="8" * 64,
        technical_snapshot_identity_sha256=None,
        technical_source_identity=None,
        ma_evidence_identity_sha256=None,
        kdj_evidence_identity_sha256=None,
        volatility_compact_identity_sha256=None,
        projection_group_session_identity_sha256=query.projection_group_session_identity_sha256,
    )


def test_global_sort_keeps_null_last_stock_tiebreak_and_cancellation() -> None:
    query = _query(
        sorts=(
            composite.DailyMarketTechnicalOfficialDispositionCompositeSortClauseV1(
                "ma_alignment_state", "asc",
            ),
            composite.DailyMarketTechnicalOfficialDispositionCompositeSortClauseV1(
                "stock_code", "asc",
            ),
        ),
    )
    context = composite.prepare_composite_evaluation_context_v1(query)
    ordered = composite.sort_composite_keys_v1(context, (
        _sort_key(query, "QQQ", None),
        _sort_key(query, "ZZZ", "match"),
        _sort_key(query, "BBB", "no_match"),
        _sort_key(query, "AAA", "match"),
    ))
    assert tuple((item.stock_code, item.sort_values[0].value) for item in ordered) == (
        ("AAA", "match"),
        ("ZZZ", "match"),
        ("BBB", "no_match"),
        ("QQQ", None),
    )

    with pytest.raises(composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1Error, match="cancelled"):
        composite.sort_composite_keys_v1(context, (), cancel_callback=lambda: True)


def test_nested_sort_and_float_decimal_are_rejected() -> None:
    with pytest.raises(composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1Error, match="nested_f17_sort_or_page_not_neutral"):
        _query(f17_sort=(
            DailyMarketTechnicalOfficialDispositionSortClauseV1("decision_date", "desc"),
        ))
    with pytest.raises(composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1Error, match="decimal_invalid"):
        composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1.create(
            _f17_query(),
            projection_group_session_identity_sha256="7" * 64,
            bandwidth_min_pct=cast(Decimal, 1.25),
        )


def test_reader_issuer_rejects_object_stubs() -> None:
    query = _query()
    with pytest.raises(
        composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1Error,
        match="reader_issuer_type_invalid",
    ):
        composite._validate_reader_issuer_binding(
            query,
            cast(DailyMarketTechnicalOfficialDispositionReadSessionV1, object()),
            cast(DailyMarketTechnicalUniverseProjectionGroupSessionV2, object()),
        )

    context = composite.prepare_composite_evaluation_context_v1(query)
    with pytest.raises(
        composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1Error,
        match="sort_group_session_type_invalid",
    ):
        composite._validate_composite_group_session_v1(
            context,
            cast(DailyMarketTechnicalUniverseProjectionGroupSessionV2, object()),
        )


def test_result_row_rejects_wrong_fact_type_before_field_access() -> None:
    with pytest.raises(
        composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1Error,
        match="result_row_invalid",
    ):
        composite.DailyMarketTechnicalOfficialDispositionCompositeResultRowV1(
            query_identity_sha256="a" * 64,
            fact_row=cast(DailyMarketTechnicalOfficialDispositionFactRowV1, object()),
            technical_row=None,
            ma_entry=None,
            kdj_entry=None,
            volatility_entry=None,
            filter_evaluation=cast(
                composite.DailyMarketTechnicalOfficialDispositionFilterEvaluationV1,
                object(),
            ),
            evaluation=cast(
                composite.DailyMarketTechnicalOfficialDispositionCompositeEvaluationV1,
                object(),
            ),
            row_identity_sha256="b" * 64,
        )


def test_source_pin_contract_uses_group_ma_index_without_standalone_ma_session() -> None:
    assert "ma_read_session_identity_sha256" not in composite._SOURCE_PIN_KEYS
    assert "ma_source_request_identity_sha256" in composite._SOURCE_PIN_KEYS
    assert "ma_index_source_clock_identity_sha256" in composite._SOURCE_PIN_KEYS
    assert "projection_group_session_identity_sha256" in composite._SOURCE_PIN_KEYS


def test_real_public_group_owner_qualifies_exact_original_entries(
    real_group_owner: tuple[
        DailyMarketTechnicalOfficialDispositionQueryV1,
        DailyMarketTechnicalOfficialDispositionReadSessionV1,
        DailyMarketTechnicalUniverseProjectionGroupSessionV2,
    ],
) -> None:
    one_code_query, read_session, projection_group_session = real_group_owner
    composite_query = composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1.create(
        one_code_query,
        projection_group_session_identity_sha256=projection_group_session.identity_sha256,
    )

    composite._validate_reader_issuer_binding(
        composite_query,
        read_session,
        projection_group_session,
    )
    ma_index = projection_group_session.ma_index
    kdj_entries = projection_group_session.kdj_entries
    volatility_entries = projection_group_session.volatility_entries
    assert len(ma_index.entries) == len(kdj_entries) == len(volatility_entries) == 257
    assert tuple(entry.stock_code for entry in ma_index.entries) == tuple(
        sorted(entry.stock_code for entry in ma_index.entries)
    )
    assert tuple(entry.stock_code for entry in ma_index.entries) == tuple(
        entry.stock_code for entry in kdj_entries
    ) == tuple(entry.stock_code for entry in volatility_entries)
    code = ma_index.entries[0].stock_code
    ma_entry = ma_index.entries[0]
    kdj_entry = kdj_entries[0]
    volatility_entry = volatility_entries[0]
    composite._validate_original_group_entries_for_code_v1(
        projection_group_session,
        code,
        ma_entry,
        kdj_entry,
        volatility_entry,
    )

    with pytest.raises(
        composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1Error,
        match="sort_group_entry_identity_mismatch",
    ):
        composite._validate_original_group_entries_for_code_v1(
            projection_group_session,
            code,
            replace(ma_entry),
            kdj_entry,
            volatility_entry,
        )


def test_real_owner_issues_result_anchor_and_rejects_copy_or_rehash(
    bundle_fixture: _BundleFixture,
    real_group_owner: tuple[
        DailyMarketTechnicalOfficialDispositionQueryV1,
        DailyMarketTechnicalOfficialDispositionReadSessionV1,
        DailyMarketTechnicalUniverseProjectionGroupSessionV2,
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    one_code_query, read_session, projection_group_session = real_group_owner
    base_result = read_session.execute()
    base_page = base_result.read_page(0, 1)
    assert len(base_page.rows) == 1
    assert base_result.counts.matching_count == 1
    base_row = base_page.rows[0]
    composite_query = composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1.create(
        one_code_query,
        projection_group_session_identity_sha256=projection_group_session.identity_sha256,
    )
    context = composite.prepare_composite_evaluation_context_v1(composite_query)
    ma_entries = projection_group_session.ma_index.entries
    kdj_entries = projection_group_session.kdj_entries
    volatility_entries = projection_group_session.volatility_entries
    code = base_row.fact_row.stock_code
    position = bundle_fixture.included_codes.index(code)
    assert position < len(ma_entries)
    ma_entry = ma_entries[position]
    kdj_entry = kdj_entries[position]
    volatility_entry = volatility_entries[position]
    evaluation = composite.evaluate_composite_predicate_v1(
        context,
        technical_truth=None,
        ma_truth=None,
        kdj_truth=None,
        volatility_truth=None,
        technical_status="processed",
        hard_eligible=True,
    )
    assert evaluation.audit_visible is True and evaluation.visible is True
    key = composite.project_composite_sort_key_v1(
        context,
        base_row.fact_row,
        base_row.technical_row,
        ma_entry,
        kdj_entry,
        volatility_entry,
        projection_group_session,
    )
    declared = base_result.counts.population.declared_count
    processed = base_result.counts.population.processed_count
    state_order = ("match", "no_match", "unknown")

    def state_counts(values: tuple[str, ...]) -> tuple[tuple[str, int], ...]:
        observed = Counter(values)
        return tuple((state, observed.get(state, 0)) for state in state_order)

    ma_state_counts = state_counts(tuple(entry.ma_state for entry in ma_entries))
    kdj_state_counts = state_counts(tuple(entry.state for entry in kdj_entries))
    bandwidth_state_counts = (
        ("observed", sum(entry.evidence.bandwidth.value is not None for entry in volatility_entries)),
        ("unknown", sum(entry.evidence.bandwidth.value is None for entry in volatility_entries)),
    )
    atr14_state_counts = (
        ("observed", sum(entry.evidence.atr14_sma.normalized_value is not None for entry in volatility_entries)),
        ("unknown", sum(entry.evidence.atr14_sma.normalized_value is None for entry in volatility_entries)),
    )
    n_a_truths = _truth_counts(not_applicable=declared)
    composite_truths = _truth_counts(
        not_evaluated=declared - 1,
        not_applicable=1,
    )
    eligible_truths = _truth_counts(not_applicable=1)
    counts = composite.DailyMarketTechnicalOfficialDispositionCompositeCountsV1(
        base_f17_counts=base_result.counts,
        ma_state_counts=ma_state_counts,
        kdj_state_counts=kdj_state_counts,
        bandwidth_state_counts=bandwidth_state_counts,
        atr14_state_counts=atr14_state_counts,
        technical_truth_counts=n_a_truths,
        ma_truth_counts=n_a_truths,
        kdj_truth_counts=n_a_truths,
        volatility_truth_counts=n_a_truths,
        composite_truth_counts=composite_truths,
        hard_eligible_truth_counts=eligible_truths,
        active_evaluable_truth_counts=_truth_counts(),
        hard_eligible_count=1,
        active_evaluable_count=0,
        audit_visible_count=1,
        visible_count=1,
        unknown_policy_included_count=0,
        unknown_policy_excluded_count=0,
    )
    source_pins = composite._source_pins_for_reader_v1(
        composite_query,
        read_session,
        projection_group_session,
    )
    result = composite._issue_result_v1(
        query=composite_query,
        counts=counts,
        source_pins=source_pins,
        ordered_keys=(key,),
        result_status=base_page.result_status,
        official_source_coverage_status=base_page.official_source_coverage_status,
        read_session=read_session,
        projection_group_session=projection_group_session,
    )

    def fail_if_all_keys_are_rehashed(_self: object) -> dict[str, object]:
        raise AssertionError("同一結果重讀時不可重新序列化全體排序鍵")

    monkeypatch.setattr(
        composite.DailyMarketTechnicalOfficialDispositionCompositeSortKeyV1,
        "to_dict",
        fail_if_all_keys_are_rehashed,
    )
    result.__post_init__()
    with pytest.raises(
        composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1Error,
        match="result_not_reader_issued",
    ):
        replace(result)
