"""P02/P04 V2 價格閘門沿同一 V3 projection group 的回歸測試。"""

from __future__ import annotations

from dataclasses import replace as dataclass_replace
from decimal import Decimal
import json
from typing import Any, Literal, cast

import pytest

pytest_plugins = (
    "test_daily_market_technical_official_disposition_query_reader_v1",
)

import app_module.daily_market_technical_official_disposition_composite_query_v1 as composite_v1
import app_module.daily_market_technical_official_disposition_composite_query_v2 as composite_v2
import app_module.daily_market_technical_official_disposition_query_reader_v1 as query_reader
from app_module.daily_market_technical_universe_projection_group_session_v3 import (
    DailyMarketTechnicalUniverseProjectionGroupSessionV3,
)
from app_module.daily_market_technical_official_disposition_bundle_v1 import (
    DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1,
)
from app_module.daily_market_technical_universe_v4_store import (
    DailyMarketTechnicalUniverseV4StoreReader,
)


@pytest.fixture(scope="module")
def projection_group_session_v3(
    exact_query: Any,
) -> DailyMarketTechnicalUniverseProjectionGroupSessionV3:
    return query_reader.open_daily_market_technical_official_disposition_projection_group_session_v3(
        exact_query,
    )


def _base_query(
    exact_query: Any,
    session: DailyMarketTechnicalUniverseProjectionGroupSessionV3,
    *,
    group_identity: str | None = None,
) -> composite_v1.DailyMarketTechnicalOfficialDispositionCompositeQueryV1:
    return composite_v1.DailyMarketTechnicalOfficialDispositionCompositeQueryV1.create(
        exact_query,
        projection_group_session_identity_sha256=(
            session.identity_sha256 if group_identity is None else group_identity
        ),
    )


def _price_sort(
    direction: Literal["asc", "desc"] = "asc",
) -> tuple[composite_v2.DailyMarketTechnicalOfficialDispositionCompositeSortClauseV2, ...]:
    return (
        composite_v2.DailyMarketTechnicalOfficialDispositionCompositeSortClauseV2(
            "price.close_price", direction,
        ),
        composite_v2.DailyMarketTechnicalOfficialDispositionCompositeSortClauseV2(
            "stock_code", "asc",
        ),
    )


def test_v2_decimal_price_gate_preserves_base_counts_and_roundtrips_on_same_v3_session(
    bundle_fixture: Any,
    exact_query: Any,
    projection_group_session_v3: DailyMarketTechnicalUniverseProjectionGroupSessionV3,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = projection_group_session_v3
    assert session.reader_issued is True
    assert session.parent_segment_indexes == (0, 1)
    assert len(session.price_facts) == len(bundle_fixture.included_codes) == 257
    known = tuple(
        fact for fact in session.price_facts
        if fact.status == "known" and fact.close_price is not None
    )
    assert known
    target = known[len(known) // 2].close_price
    assert target is not None
    base = _base_query(exact_query, session)
    sort_clauses = _price_sort()
    baseline_query = composite_v2.DailyMarketTechnicalOfficialDispositionCompositeQueryV2.create(
        base,
        sort_clauses=sort_clauses,
    )
    filtered_query = composite_v2.DailyMarketTechnicalOfficialDispositionCompositeQueryV2.create(
        base,
        min_close_price=target,
        max_close_price=target,
        sort_clauses=sort_clauses,
    )
    above_range_query = composite_v2.DailyMarketTechnicalOfficialDispositionCompositeQueryV2.create(
        base,
        min_close_price=target + Decimal("0.01"),
        sort_clauses=sort_clauses,
    )
    assert composite_v2.DailyMarketTechnicalOfficialDispositionCompositeQueryV2.from_json(
        filtered_query.to_json().encode("utf-8")
    ) == filtered_query

    def forbidden_reopen(*_args: object, **_kwargs: object) -> Any:
        pytest.fail("V2 consumer 必須使用已發行的 V3 session")

    monkeypatch.setattr(
        query_reader,
        "open_daily_market_technical_official_disposition_projection_group_session_v3",
        forbidden_reopen,
    )
    monkeypatch.setattr(
        DailyMarketTechnicalUniverseV4StoreReader,
        "read_exact_with_verified_parent_callback",
        forbidden_reopen,
    )
    baseline = composite_v2.execute_composite_query_v2(baseline_query, session)
    result = composite_v2.execute_composite_query_v2(filtered_query, session)
    above_range = composite_v2.execute_composite_query_v2(above_range_query, session)

    expected_codes = tuple(sorted(
        fact.stock_code for fact in known if fact.close_price == target
    ))
    assert expected_codes
    assert result.ordered_stock_codes == expected_codes
    assert result.counts.declared_count == 258
    assert result.counts.processed_count == 257
    assert result.counts.excluded_count == 1
    assert result.counts.base_composite_counts.to_dict() == baseline.counts.base_composite_counts.to_dict()
    assert result.counts.base_visible_count == baseline.counts.base_visible_count
    assert result.counts.visible_count == len(expected_codes)
    assert above_range.ordered_stock_codes == ()
    assert above_range.counts.visible_count == 0
    assert above_range.counts.base_composite_counts.to_dict() == baseline.counts.base_composite_counts.to_dict()
    assert dict(result.counts.price_truth_counts)["match"] > 0
    assert sum(count for _, count in result.counts.price_truth_counts) == 258
    assert sum(count for _, count in result.counts.final_truth_counts) == 258

    raw_result = result.to_json()
    raw_result_bytes = raw_result.encode("utf-8")
    reopened_result = composite_v2.DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2.from_json(
        raw_result_bytes,
        # bytes 輸入是 public reader 的正式序列化路徑。
        projection_group_session=session,
    )
    assert reopened_result.to_json() == raw_result
    page = result.read_page(0, min(7, result.visible_count))
    assert tuple(row.stock_code for row in page.rows) == expected_codes[:len(page.rows)]
    for row in page.rows:
        assert row.price_state == "match"
        assert row.evaluation.price_truth == row.price_state
        assert row.evaluation.active_groups == (False, False, False, False, True)
        assert row.evaluation.predicate_match is True
        assert row.price_fact is session.price_fact_for_code(row.stock_code)

    reordered_keys = tuple(reversed(result._ordered_sort_keys))
    reordered_body = composite_v2._result_body_v2(
        query=result.query,
        counts=result.counts,
        source_pins=result.source_pins,
        ordered_keys=reordered_keys,
        result_status=result.result_status,
        coverage_status=result.official_source_coverage_status,
    )
    with pytest.raises(composite_v2.DailyMarketTechnicalOfficialDispositionCompositeQueryV2Error) as reordered_error:
        dataclass_replace(
            result,
            _ordered_sort_keys=reordered_keys,
            operation_identity_sha256=composite_v2._sha256_json(reordered_body),
        )
    assert reordered_error.value.code == "result_reader_anchor_mismatch"

    truth_counts = list(result.counts.price_truth_counts)
    source_index = next(index for index, (_key, count) in enumerate(truth_counts) if count > 0)
    target_index = (source_index + 1) % len(truth_counts)
    truth_counts[source_index] = (truth_counts[source_index][0], truth_counts[source_index][1] - 1)
    truth_counts[target_index] = (truth_counts[target_index][0], truth_counts[target_index][1] + 1)
    changed_counts = dataclass_replace(
        result.counts,
        price_truth_counts=tuple(truth_counts),
        final_truth_counts=tuple(truth_counts),
    )
    counts_body = composite_v2._result_body_v2(
        query=result.query,
        counts=changed_counts,
        source_pins=result.source_pins,
        ordered_keys=result._ordered_sort_keys,
        result_status=result.result_status,
        coverage_status=result.official_source_coverage_status,
    )
    with pytest.raises(composite_v2.DailyMarketTechnicalOfficialDispositionCompositeQueryV2Error) as counts_error:
        dataclass_replace(
            result,
            counts=changed_counts,
            operation_identity_sha256=composite_v2._sha256_json(counts_body),
        )
    assert counts_error.value.code == "result_reader_anchor_mismatch"

    changed_status = "partial" if result.result_status == "complete" else "complete"
    status_body = composite_v2._result_body_v2(
        query=result.query,
        counts=result.counts,
        source_pins=result.source_pins,
        ordered_keys=result._ordered_sort_keys,
        result_status=changed_status,
        coverage_status=result.official_source_coverage_status,
    )
    with pytest.raises(composite_v2.DailyMarketTechnicalOfficialDispositionCompositeQueryV2Error) as status_error:
        dataclass_replace(
            result,
            result_status=changed_status,
            operation_identity_sha256=composite_v2._sha256_json(status_body),
        )
    assert status_error.value.code == "result_reader_anchor_mismatch"

    first_page_row = page.rows[0]
    changed_evaluation = dataclass_replace(
        first_page_row.evaluation,
        audit_visible=not first_page_row.evaluation.audit_visible,
    )
    changed_row_identity = composite_v2._sha256_json(
        composite_v2._row_identity_payload_v2(
            query_identity_sha256=page.query.query_identity_sha256,
            base_row=first_page_row.base_row,
            price_fact=first_page_row.price_fact,
            price_state=first_page_row.price_state,
            evaluation=changed_evaluation,
        )
    )
    changed_page_row = dataclass_replace(
        first_page_row,
        evaluation=changed_evaluation,
        row_identity_sha256=changed_row_identity,
    )
    changed_page_rows = (changed_page_row, *page.rows[1:])
    changed_page_identity = composite_v2._page_identity_v2(
        result=result,
        request_identity_sha256=page.request_identity_sha256,
        page_index=page.page_index,
        page_size=page.page_size,
        rows=changed_page_rows,
    )
    with pytest.raises(composite_v2.DailyMarketTechnicalOfficialDispositionCompositeQueryV2Error) as page_row_error:
        dataclass_replace(
            page,
            rows=changed_page_rows,
            page_identity_sha256=changed_page_identity,
        )
    assert page_row_error.value.code == "page_reader_anchor_mismatch"

    raw_page = page.to_json()
    raw_page_bytes = raw_page.encode("utf-8")
    reopened_page = composite_v2.DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2.from_json(
        raw_page_bytes,
        result=reopened_result,
    )
    assert reopened_page.to_json() == raw_page
    changed_page = json.loads(raw_page)
    changed_page["rows"][0]["stock_code"] = "ZZZZ"
    changed_page_json = json.dumps(
        changed_page,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    with pytest.raises(composite_v2.DailyMarketTechnicalOfficialDispositionCompositeQueryV2Error):
        composite_v2.DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2.from_json(
            changed_page_json,
            result=reopened_result,
        )

    changed = json.loads(raw_result)
    changed["visible_count"] += 1
    changed_json = json.dumps(
        changed,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    with pytest.raises(composite_v2.DailyMarketTechnicalOfficialDispositionCompositeQueryV2Error):
        composite_v2.DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2.from_json(
            changed_json,
            projection_group_session=session,
        )


def test_v2_exact_decimal_bounds_apply_before_global_pagination(
    exact_query: Any,
    projection_group_session_v3: DailyMarketTechnicalUniverseProjectionGroupSessionV3,
) -> None:
    session = projection_group_session_v3
    known = tuple(
        fact for fact in session.price_facts
        if fact.status == "known" and fact.close_price is not None
    )
    target = known[len(known) // 2].close_price
    assert target is not None
    base = _base_query(exact_query, session)
    inclusive_query = composite_v2.DailyMarketTechnicalOfficialDispositionCompositeQueryV2.create(
        base,
        min_close_price=target,
        max_close_price=target,
        min_inclusive=True,
        max_inclusive=True,
        sort_clauses=_price_sort(),
    )
    exclusive_query = composite_v2.DailyMarketTechnicalOfficialDispositionCompositeQueryV2.create(
        base,
        min_close_price=target,
        max_close_price=target,
        min_inclusive=False,
        max_inclusive=False,
        sort_clauses=_price_sort(),
    )
    inclusive = composite_v2.execute_composite_query_v2(inclusive_query, session)
    exclusive = composite_v2.execute_composite_query_v2(exclusive_query, session)
    expected = tuple(sorted(
        fact.stock_code for fact in known if fact.close_price == target
    ))
    assert inclusive.ordered_stock_codes == expected
    assert exclusive.ordered_stock_codes == ()
    assert inclusive.counts.base_composite_counts.to_dict() == exclusive.counts.base_composite_counts.to_dict()
    first_row = inclusive.read_page(0, 1).rows[0]
    assert first_row.price_fact is not None
    assert first_row.price_fact.close_price == target


def test_v2_ma_kdj_or_truth_is_then_gated_by_price_on_the_same_v3_facts(
    exact_query: Any,
    projection_group_session_v3: DailyMarketTechnicalUniverseProjectionGroupSessionV3,
) -> None:
    session = projection_group_session_v3
    ma_entries = session.ma_index.entries
    kdj_entries = session.kdj_entries
    assert len(ma_entries) == len(kdj_entries) == len(session.price_facts) == 257
    assert tuple(item.stock_code for item in ma_entries) == tuple(
        item.stock_code for item in kdj_entries
    )

    # 從同一 session 的原始 MA/KDJ 狀態選出 OR 與 AND 結果確實不同的組合。
    state_options = (("match",), ("no_match",), ("match", "no_match"))
    selected_pair: tuple[tuple[str, ...], tuple[str, ...], set[str], set[str]] | None = None
    for ma_states in state_options:
        for kdj_states in state_options:
            ma_matches = {
                ma.stock_code
                for ma in ma_entries
                if ma.ma_state != "unknown" and ma.ma_state in ma_states
            }
            kdj_matches = {
                kdj.stock_code
                for kdj in kdj_entries
                if kdj.state != "unknown" and kdj.state in kdj_states
            }
            if (ma_matches | kdj_matches) and ma_matches != kdj_matches:
                selected_pair = ma_states, kdj_states, ma_matches, kdj_matches
                break
        if selected_pair is not None:
            break
    assert selected_pair is not None
    ma_states, kdj_states, ma_matches, kdj_matches = selected_pair
    expected_or_codes = ma_matches | kdj_matches
    expected_and_codes = ma_matches & kdj_matches
    assert expected_or_codes - expected_and_codes

    base = composite_v1.DailyMarketTechnicalOfficialDispositionCompositeQueryV1.create(
        exact_query,
        projection_group_session_identity_sha256=session.identity_sha256,
        ma_states=cast(tuple[composite_v1.MaState, ...], ma_states),
        kdj_states=cast(tuple[composite_v1.KDJState, ...], kdj_states),
        condition_combine_mode="OR",
        unknown_policy="exclude",
    )
    assert base.active_groups == (False, True, True, False)

    price_by_code = {fact.stock_code: fact for fact in session.price_facts}
    eligible_targets: list[Decimal] = []
    for code in expected_or_codes:
        fact = price_by_code[code]
        if fact.status == "known" and fact.close_price is not None:
            eligible_targets.append(fact.close_price)
    assert eligible_targets
    target = min(eligible_targets)
    expected_intersection = tuple(sorted(
        code for code in expected_or_codes
        if price_by_code[code].status == "known"
        and price_by_code[code].close_price == target
    ))
    assert expected_intersection

    exact_price_query = composite_v2.DailyMarketTechnicalOfficialDispositionCompositeQueryV2.create(
        base,
        min_close_price=target,
        max_close_price=target,
        unknown_price_policy="exclude",
        sort_clauses=_price_sort(),
    )
    rejected_price_query = composite_v2.DailyMarketTechnicalOfficialDispositionCompositeQueryV2.create(
        base,
        min_close_price=max(eligible_targets) + Decimal("0.01"),
        unknown_price_policy="exclude",
        sort_clauses=_price_sort(),
    )
    exact_price_result = composite_v2.execute_composite_query_v2(exact_price_query, session)
    rejected_price_result = composite_v2.execute_composite_query_v2(rejected_price_query, session)

    assert exact_price_result.counts.base_visible_count == len(expected_or_codes)
    assert exact_price_result.counts.visible_count == len(expected_intersection)
    assert exact_price_result.ordered_stock_codes == expected_intersection
    assert all(
        row.evaluation.active_groups == (False, True, True, False, True)
        and (row.evaluation.ma_truth == "match" or row.evaluation.kdj_truth == "match")
        for row in exact_price_result.read_page(
            0,
            min(
                len(expected_intersection),
                composite_v2.DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_PAGE_SIZE,
            ),
        ).rows
    )
    assert rejected_price_result.counts.base_visible_count == len(expected_or_codes)
    assert rejected_price_result.counts.visible_count == 0
    assert rejected_price_result.ordered_stock_codes == ()


@pytest.mark.parametrize(
    "invalid_price",
    (1.0, Decimal("NaN"), Decimal("Infinity")),
)
def test_v2_price_bounds_reject_binary_or_nonfinite_numbers(
    invalid_price: object,
    exact_query: Any,
    projection_group_session_v3: DailyMarketTechnicalUniverseProjectionGroupSessionV3,
) -> None:
    base = _base_query(exact_query, projection_group_session_v3)
    with pytest.raises(
        composite_v2.DailyMarketTechnicalOfficialDispositionCompositeQueryV2Error,
        match="price_decimal_invalid",
    ):
        composite_v2.DailyMarketTechnicalOfficialDispositionCompositeQueryV2.create(
            base,
            min_close_price=cast(Any, invalid_price),
        )


def test_v2_unknown_price_policy_is_a_gate_over_the_four_group_truth(
    exact_query: Any,
    projection_group_session_v3: DailyMarketTechnicalUniverseProjectionGroupSessionV3,
) -> None:
    session = projection_group_session_v3
    base = _base_query(exact_query, session)
    context = composite_v1.prepare_composite_evaluation_context_v1(base)
    base_evaluation = composite_v1.evaluate_composite_predicate_v1(
        context,
        technical_truth=None,
        ma_truth=None,
        kdj_truth=None,
        volatility_truth=None,
        technical_status="processed",
        hard_eligible=True,
    )
    known = next(
        fact for fact in session.price_facts
        if fact.status == "known" and fact.close_price is not None
    )
    assert known.close_price is not None
    evaluated: dict[str, composite_v2.DailyMarketTechnicalOfficialDispositionCompositeEvaluationV2] = {}
    policies: tuple[Literal["include", "exclude", "only"], ...] = (
        "include", "exclude", "only",
    )
    for policy in policies:
        query = composite_v2.DailyMarketTechnicalOfficialDispositionCompositeQueryV2.create(
            base,
            min_close_price=known.close_price,
            unknown_price_policy=policy,
        )
        evaluated[policy] = composite_v2._final_evaluation(
            base_evaluation,
            price_truth="unknown",
            technical_status="processed",
            hard_eligible=True,
            query=query,
        )
    assert evaluated["include"].visible is True
    assert evaluated["exclude"].visible is False
    assert evaluated["only"].visible is True
    assert all(item.price_truth == "unknown" for item in evaluated.values())
    assert all(item.composite_truth == "unknown" for item in evaluated.values())
    assert evaluated["include"].predicate_match is False
    assert evaluated["only"].included_by_unknown_policy is True

    active_base = composite_v1.DailyMarketTechnicalOfficialDispositionCompositeQueryV1.create(
        exact_query,
        projection_group_session_identity_sha256=session.identity_sha256,
        ma_states=("match",),
    )
    active_context = composite_v1.prepare_composite_evaluation_context_v1(active_base)
    matching_four_group_result = composite_v1.evaluate_composite_predicate_v1(
        active_context,
        technical_truth=None,
        ma_truth="match",
        kdj_truth=None,
        volatility_truth=None,
        technical_status="processed",
        hard_eligible=True,
    )
    no_match_query = composite_v2.DailyMarketTechnicalOfficialDispositionCompositeQueryV2.create(
        active_base,
        min_close_price=known.close_price + Decimal("1"),
    )
    gated = composite_v2._final_evaluation(
        matching_four_group_result,
        price_truth="no_match",
        technical_status="processed",
        hard_eligible=True,
        query=no_match_query,
    )
    assert gated.composite_truth == "no_match"
    assert gated.visible is False


@pytest.mark.parametrize(
    ("direction", "expected_codes"),
    (
        ("asc", ("0001", "0010", "0020", "9999")),
        ("desc", ("0010", "0020", "0001", "9999")),
    ),
)
def test_v2_price_sort_keeps_unknown_last_and_stock_ties_stable(
    direction: Literal["asc", "desc"],
    expected_codes: tuple[str, ...],
    exact_query: Any,
    projection_group_session_v3: DailyMarketTechnicalUniverseProjectionGroupSessionV3,
) -> None:
    session = projection_group_session_v3
    base = _base_query(exact_query, session)
    query = composite_v2.DailyMarketTechnicalOfficialDispositionCompositeQueryV2.create(
        base,
        sort_clauses=_price_sort(direction),
    )
    source_rows = (
        ("0020", Decimal("5")),
        ("9999", None),
        ("0001", Decimal("2")),
        ("0010", Decimal("5")),
    )
    keys = tuple(
        composite_v2.DailyMarketTechnicalOfficialDispositionCompositeSortKeyV2(
            stock_code=code,
            sort_values=(
                composite_v1.DailyMarketTechnicalOfficialDispositionSortValueV1(
                    "price.close_price", direction, price,
                ),
                composite_v1.DailyMarketTechnicalOfficialDispositionSortValueV1(
                    "stock_code", "asc", code,
                ),
            ),
            fact_row_sha256="1" * 64,
            price_fact_identity_sha256=None,
            projection_group_session_identity_sha256=session.identity_sha256,
        )
        for code, price in source_rows
    )
    ordered = composite_v2._sort_keys_v2(query, keys, None)
    assert tuple(item.stock_code for item in ordered) == expected_codes


def test_v2_rejects_a_query_bound_to_another_group_and_never_returns_cancelled_work(
    exact_query: Any,
    projection_group_session_v3: DailyMarketTechnicalUniverseProjectionGroupSessionV3,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = projection_group_session_v3
    other_identity = "f" * 64
    assert other_identity != session.identity_sha256
    wrong_base = _base_query(exact_query, session, group_identity=other_identity)
    wrong_query = composite_v2.DailyMarketTechnicalOfficialDispositionCompositeQueryV2.create(
        wrong_base,
        min_close_price=Decimal("1"),
    )
    with pytest.raises(
        composite_v2.DailyMarketTechnicalOfficialDispositionCompositeQueryV2Error,
        match="projection_group_session_binding_mismatch",
    ):
        composite_v2.execute_composite_query_v2(wrong_query, session)

    base = _base_query(exact_query, session)
    query = composite_v2.DailyMarketTechnicalOfficialDispositionCompositeQueryV2.create(
        base,
    )
    first_fact_consumed = False
    bundle_state = session._anchor.bundle_state
    original_iter = DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1.iter_verified_rows

    def observe_first_fact(
        instance: DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1,
        *,
        cancel_callback: Any = None,
    ) -> Any:
        nonlocal first_fact_consumed
        for fact in original_iter(instance, cancel_callback=cancel_callback):
            yield fact
            first_fact_consumed = True

    monkeypatch.setattr(
        DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1,
        "iter_verified_rows",
        observe_first_fact,
    )

    post_first_fact_checks = 0

    def cancel_after_first_fact() -> bool:
        nonlocal post_first_fact_checks
        if not first_fact_consumed:
            return False
        post_first_fact_checks += 1
        # 第一次是下層 iterator 的下一列前檢查，第二次是 consumer 的列首檢查。
        return post_first_fact_checks >= 2

    with pytest.raises(query_reader.DailyMarketTechnicalOfficialDispositionQueryReaderV1Cancelled):
        composite_v2.execute_composite_query_v2(
            query,
            session,
            cancel_callback=cancel_after_first_fact,
        )
    assert first_fact_consumed is True
    assert type(bundle_state) is DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1


def test_v2_rejects_a_poisoned_v3_group_without_issuing_a_result(
    exact_query: Any,
    projection_group_session_v3: DailyMarketTechnicalUniverseProjectionGroupSessionV3,
) -> None:
    session = projection_group_session_v3
    query = composite_v2.DailyMarketTechnicalOfficialDispositionCompositeQueryV2.create(
        _base_query(exact_query, session),
    )
    session._anchor.group._poison()
    with pytest.raises(
        composite_v2.DailyMarketTechnicalOfficialDispositionCompositeQueryV2Error,
        match="projection_group_session_not_active",
    ):
        composite_v2.execute_composite_query_v2(query, session)

