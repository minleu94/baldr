"""同一 F17／P01／三路 projection 的全母體複合查詢執行器。

只復用已核來源的研究事實；不重算金融證據，不授歷史 PIT 或交易資格。
OR 必須遍歷全母體，不能先截取任一子查詢的入選清單。
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Callable
from typing import Literal, cast

import app_module.daily_market_technical_official_disposition_composite_query_v1 as c
import app_module.daily_market_technical_official_disposition_query_reader_v1 as r


def _binding(
    session: r.DailyMarketTechnicalOfficialDispositionReadSessionV1,
    query: c.DailyMarketTechnicalOfficialDispositionCompositeQueryV1,
    cancel: Callable[[], object] | None,
) -> c.DailyMarketTechnicalUniverseProjectionGroupSessionV2:
    r._validate_cancel_callback(cancel)
    r._check_cancel(cancel)
    if type(session) is not r.DailyMarketTechnicalOfficialDispositionReadSessionV1:
        r._fail("composite_reader_issuer_invalid")
    if type(query) is not c.DailyMarketTechnicalOfficialDispositionCompositeQueryV1:
        r._fail("composite_query_invalid")
    query.to_json()
    session.__post_init__()
    r._validate_bundle_query_relationship(session.query, session._bundle_state)
    group = session.projection_group_session
    if group is None:
        r._fail("composite_projection_group_unavailable")
    c._validate_reader_issuer_binding(query, session, group)
    return group


def _evaluate(
    session: r.DailyMarketTechnicalOfficialDispositionReadSessionV1,
    context: c.DailyMarketTechnicalOfficialDispositionCompositeEvaluationContextV1,
    fact: c.DailyMarketTechnicalOfficialDispositionFactRowV1,
    parent: c.DailyMarketTechnicalParentV4Row | None,
    ma: c.DailyMarketTechnicalMaAlignmentCompactEntryV1 | None,
    kd: c.DailyMarketTechnicalUniverseKDJCompactEntryV1 | None,
    vol: c.DailyMarketTechnicalUniverseVolatilityCompactEntryV1 | None,
) -> tuple[
    c.DailyMarketTechnicalOfficialDispositionFilterEvaluationV1,
    c.DailyMarketTechnicalOfficialDispositionCompositeEvaluationV1,
    bool, c.CompositeTruth, bool,
]:
    outer = r.evaluate_f17_membership_v1(session.query, fact)
    base_match, base_truth, stock_match = r._technical_filter_evaluation(
        session.query, fact, parent,
    )
    hard = outer.filter_membership and stock_match
    status = c._fact_technical_status(fact)
    # Explicit arguments retain static types; no numeric conversion at this boundary.
    technical_truth = c.evaluate_technical_group_v1(
        context, fact, parent, technical_status=status, hard_eligible=hard,
    )
    ma_truth = c.evaluate_ma_group_v1(
        context, fact, parent, ma, technical_status=status, hard_eligible=hard,
    )
    kd_truth = c.evaluate_kdj_group_v1(
        context, fact, parent, kd, technical_status=status, hard_eligible=hard,
    )
    vol_truth = c.evaluate_volatility_group_v1(
        context, fact, parent, vol, technical_status=status, hard_eligible=hard,
    )
    evaluation = c.evaluate_composite_predicate_v1(
        context, technical_truth=technical_truth, ma_truth=ma_truth,
        kdj_truth=kd_truth, volatility_truth=vol_truth,
        technical_status=status, hard_eligible=hard,
    )
    return outer, evaluation, base_match, cast(c.CompositeTruth, base_truth), stock_match


def execute_composite_query_v1(
    session: r.DailyMarketTechnicalOfficialDispositionReadSessionV1,
    query: c.DailyMarketTechnicalOfficialDispositionCompositeQueryV1,
    *, cancel_callback: Callable[[], object] | None = None,
) -> c.DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1:
    group = _binding(session, query, cancel_callback)
    context = c.prepare_composite_evaluation_context_v1(query)
    ma_entries = group.ma_index.entries
    kd_entries = group.kdj_entries
    vol_entries = group.volatility_entries
    expected = session._technical_session.source_counts
    if not (len(ma_entries) == len(kd_entries) == len(vol_entries) == expected.processed_count):
        r._fail("composite_projection_population_mismatch")
    base = r._CountsBuilder(session.query, expected)
    truths = {name: dict.fromkeys(c._TRUTH_ORDER, 0) for name in (
        "technical", "ma", "kdj", "volatility", "composite", "eligible", "evaluable",
    )}
    ma_states = dict.fromkeys(c._STATE_ORDER, 0)
    kd_states = dict.fromkeys(c._STATE_ORDER, 0)
    bandwidth = dict.fromkeys(("observed", "unknown"), 0)
    atr = dict.fromkeys(("observed", "unknown"), 0)
    hard_count = evaluable_count = audit_count = unknown_included = unknown_excluded = 0
    keys: list[c.DailyMarketTechnicalOfficialDispositionCompositeSortKeyV1] = []
    parents = iter(session._iter_selection_rows(cancel_callback))
    current = next(parents, None)
    position = 0
    last_code: str | None = None
    for fact in session._iter_verified_bundle_rows(cancel_callback):
        r._check_cancel(cancel_callback)
        if last_code is not None and fact.stock_code <= last_code:
            r._fail("composite_bundle_order_invalid")
        last_code = fact.stock_code
        status = c._fact_technical_status(fact)
        parent = None
        ma = None
        kd = None
        vol = None
        if status == "processed":
            if (
                current is None or current.stock_code != fact.stock_code
                or position >= len(ma_entries)
                or position >= len(session._selection.stock_codes)
                or session._selection.stock_codes[position] != fact.stock_code
            ):
                r._fail("composite_processed_join_mismatch")
            parent = current
            current = next(parents, None)
            ma, kd, vol = ma_entries[position], kd_entries[position], vol_entries[position]
            if any(entry.stock_code != fact.stock_code for entry in (ma, kd, vol)):
                r._fail("composite_projection_join_mismatch")
            position += 1
            ma_states[ma.ma_state] += 1
            kd_states[kd.state] += 1
            bandwidth["observed" if vol.evidence.bandwidth.value is not None else "unknown"] += 1
            atr["observed" if vol.evidence.atr14_sma.normalized_value is not None else "unknown"] += 1
        elif current is not None and current.stock_code <= fact.stock_code:
            r._fail("composite_unexpected_parent_row")
        outer, evaluation, base_match, base_truth, stock_match = _evaluate(
            session, context, fact, parent, ma, kd, vol,
        )
        for name, value in (
            ("technical", evaluation.technical_truth), ("ma", evaluation.ma_truth),
            ("kdj", evaluation.kdj_truth), ("volatility", evaluation.volatility_truth),
            ("composite", evaluation.composite_truth),
        ):
            truths[name][value] += 1
        if evaluation.hard_eligible:
            hard_count += 1
            truths["eligible"][evaluation.composite_truth] += 1
            if status == "processed" and any(context.active_groups):
                evaluable_count += 1
                truths["evaluable"][evaluation.composite_truth] += 1
            if evaluation.composite_truth == "unknown":
                if evaluation.visible:
                    unknown_included += 1
                else:
                    unknown_excluded += 1
        audit_count += int(evaluation.audit_visible)
        base.add(
            fact=fact, technical_row=parent, outer=outer,
            technical_stock_match=stock_match, technical_match=base_match,
            technical_truth=base_truth, overall_match=outer.filter_membership and base_match,
        )
        if evaluation.visible:
            keys.append(c.project_composite_sort_key_v1(context, fact, parent, ma, kd, vol, group))
        r._check_cancel(cancel_callback)
    if (
        current is not None or next(parents, None) is not None
        or position != expected.processed_count
        or position != len(session._selection.stock_codes)
    ):
        r._fail("composite_processed_population_mismatch")
    base_counts = base.finish()
    if base_counts.population != expected:
        r._fail("composite_declared_population_mismatch")
    def pairs(name: str) -> tuple[tuple[str, int], ...]:
        return tuple((state, truths[name][state]) for state in c._TRUTH_ORDER)
    counts = c.DailyMarketTechnicalOfficialDispositionCompositeCountsV1(
        base_f17_counts=base_counts,
        ma_state_counts=tuple(ma_states.items()), kdj_state_counts=tuple(kd_states.items()),
        bandwidth_state_counts=tuple(bandwidth.items()), atr14_state_counts=tuple(atr.items()),
        technical_truth_counts=pairs("technical"), ma_truth_counts=pairs("ma"),
        kdj_truth_counts=pairs("kdj"), volatility_truth_counts=pairs("volatility"),
        composite_truth_counts=pairs("composite"), hard_eligible_truth_counts=pairs("eligible"),
        active_evaluable_truth_counts=pairs("evaluable"), hard_eligible_count=hard_count,
        active_evaluable_count=evaluable_count, audit_visible_count=audit_count,
        visible_count=len(keys), unknown_policy_included_count=unknown_included,
        unknown_policy_excluded_count=unknown_excluded,
    )
    r._check_cancel(cancel_callback)
    ordered = c.sort_composite_keys_v1(context, keys, cancel_callback=cancel_callback)
    coverage = session.bundle_reference.source_coverage_status
    status_result: Literal["complete", "partial"] = (
        "complete" if session.bundle_reference.technical_receipt_status == "complete"
        and expected.pending_count == 0 and expected.processed_count == expected.included_count
        and coverage == "complete" else "partial"
    )
    result = c._issue_result_v1(
        query=query, counts=counts, source_pins=c._source_pins_for_reader_v1(query, session, group),
        ordered_keys=ordered, result_status=status_result,
        official_source_coverage_status=coverage, read_session=session,
        projection_group_session=group,
    )
    r._check_cancel(cancel_callback)
    return result


def materialize_composite_query_page_v1(
    session: r.DailyMarketTechnicalOfficialDispositionReadSessionV1,
    result: c.DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
    request: c.DailyMarketTechnicalOfficialDispositionCompositePageRequestV1,
    cancel_callback: Callable[[], object] | None,
) -> c.DailyMarketTechnicalOfficialDispositionCompositeQueryPageV1:
    if type(result) is not c.DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1:
        r._fail("composite_page_result_invalid")
    group = _binding(session, result.query, cancel_callback)
    c._validate_page_request_for_result_v1(result, request)
    if result._read_session is not session or result._projection_group_session is not group:
        r._fail("composite_page_owner_mismatch")
    if result.source_pins != c._source_pins_for_reader_v1(result.query, session, group):
        r._fail("composite_page_source_pins_mismatch")
    start = request.page_index * request.page_size
    keys = result.ordered_sort_keys[start:start + request.page_size]
    codes = tuple(key.stock_code for key in keys)
    try:
        selected = session._bundle_state.read_selected_rows(
            codes, cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
        )
    except r.DailyMarketTechnicalOfficialDispositionBundleError as exc:
        r._check_source_error_cancelled(exc)
        raise r.DailyMarketTechnicalOfficialDispositionQueryReaderV1Error(
            "technical_official_query_reader_v1_composite_bundle_selected_rows_failed"
        ) from exc
    if (
        type(selected) is not r.DailyMarketTechnicalOfficialDispositionBundleSelectedRowsV1
        or selected.output_root != session.bundle_reference.output_root
        or selected.bundle_identity_sha256 != session.bundle_reference.bundle_identity_sha256
        or selected.manifest_relative_path != session.bundle_reference.manifest_relative_path
        or selected.manifest_sha256 != session.bundle_reference.manifest_sha256
        or selected.requested_stock_codes != codes
        or tuple(fact.stock_code for fact in selected.rows) != codes
        or len(set(codes)) != len(codes)
    ):
        r._fail("composite_page_bundle_mismatch")
    processed = tuple(fact.stock_code for fact in selected.rows if c._fact_technical_status(fact) == "processed")
    materialization = session._materialize_selected_rows(processed, cancel_callback)
    parents = {row.stock_code: row for row in materialization.rows}
    if tuple(parents) != processed or len(parents) != len(materialization.rows):
        r._fail("composite_page_parent_mismatch")
    context = c.prepare_composite_evaluation_context_v1(result.query)
    ma_entries, kd_entries, vol_entries = group.ma_index.entries, group.kdj_entries, group.volatility_entries
    rows: list[c.DailyMarketTechnicalOfficialDispositionCompositeResultRowV1] = []
    for key, fact in zip(keys, selected.rows, strict=True):
        r._check_cancel(cancel_callback)
        parent = parents.get(fact.stock_code)
        ma = None
        kd = None
        vol = None
        if c._fact_technical_status(fact) == "processed":
            position = bisect_left(ma_entries, fact.stock_code, key=lambda entry: entry.stock_code)
            if position >= len(ma_entries) or ma_entries[position].stock_code != fact.stock_code:
                r._fail("composite_page_projection_missing")
            ma, kd, vol = ma_entries[position], kd_entries[position], vol_entries[position]
        outer, evaluation, _, _, _ = _evaluate(session, context, fact, parent, ma, kd, vol)
        if not evaluation.visible:
            r._fail("composite_page_row_no_longer_visible")
        c.validate_composite_sort_key_against_fresh_sources_v1(
            context, key, fact, parent, ma, kd, vol, group,
        )
        payload = c._row_identity_payload(
            query_identity_sha256=result.query.query_identity_sha256, fact_row=fact,
            technical_row=parent, ma_entry=ma, kdj_entry=kd, volatility_entry=vol,
            filter_evaluation=outer, evaluation=evaluation,
        )
        rows.append(c.DailyMarketTechnicalOfficialDispositionCompositeResultRowV1(
            query_identity_sha256=result.query.query_identity_sha256, fact_row=fact,
            technical_row=parent, ma_entry=ma, kdj_entry=kd, volatility_entry=vol,
            filter_evaluation=outer, evaluation=evaluation, row_identity_sha256=c._sha256_json(payload),
        ))
    r._check_cancel(cancel_callback)
    page = c._issue_page_v1(result=result, request=request, rows=tuple(rows))
    r._check_cancel(cancel_callback)
    return page
