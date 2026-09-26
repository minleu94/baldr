from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
import numpy as np
import pandas as pd

from app_module.recommendation.replay_numeric_projection import (
    ReplayThresholdUnit,
    project_legacy_post_score_comparison_pair,
)
from decision_module.recommendation.contracts import RecommendationItem
from decision_module.recommendation.evaluate import (
    NeedCandidateScoring,
    ReplayCandidateHistoryFacts,
    ReplayPostScoreDispositionV1,
    ReplayPostScoreFactsV1,
    ReplayPostScoreMetricFactV1,
    ReplayPostScorePolicyV1,
    ReplayPostScoreRuleDispositionV1,
    ReplayPostScoreRuleV1,
    ReplayScoredRowReadyV1,
    ReplayScorerDispositionV1,
    ReplayScorerResponseV1,
    RecommendationEvaluator,
)
from decision_module.recommendation.replay_policy import ReplayScoreOrderingV1
from decision_module.recommendation.replay_prefilter import (
    ReplayComparisonComponent,
    ReplayComparisonDomain,
    ReplayComparisonDomainMismatchError,
    ReplayComparisonOperator,
    ReplayComparisonOperand,
    ReplayFastFilterPolicyV1,
    ReplayMetricStatus,
    ReplayNumericOrigin,
    ReplayNumericOriginKind,
    ReplayPrefilterObservations,
    ReplayThreshold,
    compare_replay_operands,
)


def _operand(value: int) -> ReplayComparisonOperand:
    return ReplayComparisonOperand(
        origin=ReplayNumericOrigin(ReplayNumericOriginKind.PYTHON_INT),
        domain=ReplayComparisonDomain.exact_rational(),
        real=ReplayComparisonComponent.finite(value),
    )


def _metric(value: int) -> ReplayPostScoreMetricFactV1:
    return ReplayPostScoreMetricFactV1(
        status=ReplayMetricStatus.AVAILABLE,
        value=_operand(value),
    )


def _request(
    *,
    invocation_id: str = "invocation-A",
    stock_code: str = "SYN-1",
    as_of_date: date = date(2026, 9, 4),
):
    evaluator = RecommendationEvaluator()
    facts = ReplayCandidateHistoryFacts(
        invocation_id=invocation_id,
        observations=ReplayPrefilterObservations(
            stock_code=stock_code,
            as_of_date=as_of_date,
            history_rows=20,
            maximum_row_date=as_of_date,
            availability_column_present=False,
            maximum_available_date=None,
        ),
    )
    step = evaluator.start_replay_prefilter(facts, ReplayFastFilterPolicyV1())
    request = step.request
    assert type(request) is NeedCandidateScoring
    return evaluator, request, step


def _scored(
    *, invocation_id: str = "invocation-A", stock_code: str = "SYN-1"
):
    evaluator, request, step = _request(
        invocation_id=invocation_id, stock_code=stock_code
    )
    response = ReplayScorerResponseV1(
        request=request,
        disposition=ReplayScorerDispositionV1.SCORED,
        item=RecommendationItem(stock_code=stock_code, rule_score=Decimal("1")),
        score_ordering=ReplayScoreOrderingV1.finite(1),
    )
    return evaluator, evaluator.complete_replay_scoring(step, response), request


def _post_facts(request: NeedCandidateScoring) -> ReplayPostScoreFactsV1:
    return ReplayPostScoreFactsV1(
        request=request,
        price_change=_metric(10),
        volume_change_percent=_metric(5),
        rsi=_metric(50),
        rsi_source_column="RSI",
    )


def _policy(
    invocation_id: str,
    *,
    price_change_min: ReplayThreshold | None = None,
    price_change_max: ReplayThreshold | None = None,
    volume_change_min_percent: ReplayThreshold | None = None,
    rsi_min: ReplayThreshold | None = None,
    rsi_max: ReplayThreshold | None = None,
) -> ReplayPostScorePolicyV1:
    return ReplayPostScorePolicyV1(
        invocation_id=invocation_id,
        price_change_min=price_change_min or ReplayThreshold.disabled(),
        price_change_max=price_change_max or ReplayThreshold.disabled(),
        volume_change_min_percent=(
            volume_change_min_percent or ReplayThreshold.disabled()
        ),
        rsi_min=rsi_min or ReplayThreshold.disabled(),
        rsi_max=rsi_max or ReplayThreshold.disabled(),
    )


def test_scored_row_ready_can_reject_before_any_item_projection() -> None:
    evaluator, request, _step = _request()
    facts = _post_facts(request)
    ready = ReplayScoredRowReadyV1(request=request, facts=facts)

    result = evaluator.evaluate_replay_post_score_ready(
        ready,
        _policy(
            request.invocation_id,
            price_change_min=ReplayThreshold.enabled(_operand(11)),
        ),
    )

    assert result.disposition is ReplayPostScoreDispositionV1.REJECTED
    assert result.request == request
    assert result.rules[0].filter_id is ReplayPostScoreRuleV1.PRICE_CHANGE_MIN
    assert result.rules[0].disposition is ReplayPostScoreRuleDispositionV1.REJECTED
    assert not hasattr(ready, "item")


def test_scored_row_ready_fails_closed_on_request_and_policy_identity_mismatch() -> None:
    evaluator, request, _step = _request()
    _other_evaluator, other_request, _other_step = _request(
        invocation_id="invocation-B", stock_code=request.stock_code
    )

    with pytest.raises(ValueError, match="facts 不屬於 scorer request"):
        ReplayScoredRowReadyV1(
            request=request,
            facts=_post_facts(other_request),
        )

    _cutoff_evaluator, wrong_cutoff_request, _cutoff_step = _request(
        as_of_date=date(2026, 9, 5)
    )
    with pytest.raises(ValueError, match="facts 不屬於 scorer request"):
        ReplayScoredRowReadyV1(
            request=request,
            facts=_post_facts(wrong_cutoff_request),
        )

    ready = ReplayScoredRowReadyV1(request=request, facts=_post_facts(request))
    with pytest.raises(ValueError, match="policy invocation 不一致"):
        evaluator.evaluate_replay_post_score_ready(
            ready,
            _policy("invocation-B", price_change_min=ReplayThreshold.enabled(_operand(1))),
        )


def test_scored_row_ready_and_item_bearing_api_share_the_same_rule_core() -> None:
    evaluator, scored, request = _scored()
    facts = _post_facts(request)
    policy = _policy(
        request.invocation_id,
        price_change_min=ReplayThreshold.enabled(_operand(10)),
        volume_change_min_percent=ReplayThreshold.enabled(_operand(6)),
    )

    ready_result = evaluator.evaluate_replay_post_score_ready(
        ReplayScoredRowReadyV1(request=request, facts=facts),
        policy,
    )
    item_bearing_result = evaluator.evaluate_replay_post_score(scored, facts, policy)

    assert ready_result == item_bearing_result


def test_final_post_score_rules_are_inclusive_and_have_legacy_order() -> None:
    evaluator, scored, request = _scored()
    result = evaluator.evaluate_replay_post_score(
        scored,
        _post_facts(request),
        _policy(
            request.invocation_id,
            price_change_min=ReplayThreshold.enabled(_operand(10)),
            price_change_max=ReplayThreshold.enabled(_operand(10)),
            volume_change_min_percent=ReplayThreshold.enabled(_operand(5)),
            rsi_min=ReplayThreshold.enabled(_operand(50)),
            rsi_max=ReplayThreshold.enabled(_operand(50)),
        ),
    )

    assert result.disposition is ReplayPostScoreDispositionV1.ACCEPTED
    assert tuple(rule.filter_id for rule in result.rules) == (
        ReplayPostScoreRuleV1.PRICE_CHANGE_MIN,
        ReplayPostScoreRuleV1.PRICE_CHANGE_MAX,
        ReplayPostScoreRuleV1.VOLUME_CHANGE_MIN,
        ReplayPostScoreRuleV1.RSI_MIN,
        ReplayPostScoreRuleV1.RSI_MAX,
    )
    assert all(
        rule.disposition is ReplayPostScoreRuleDispositionV1.PASSED
        for rule in result.rules
    )
    assert result.request == request


def test_unordered_metric_rejects_inclusive_price_and_volume_rules() -> None:
    evaluator, scored, request = _scored()
    unordered = ReplayPostScoreMetricFactV1(
        status=ReplayMetricStatus.AVAILABLE,
        value=ReplayComparisonOperand(
            origin=ReplayNumericOrigin(ReplayNumericOriginKind.PYTHON_FLOAT),
            domain=ReplayComparisonDomain.exact_rational(),
            real=ReplayComparisonComponent.unordered(),
        ),
    )
    facts = replace(_post_facts(request), price_change=unordered, volume_change_percent=unordered)
    result = evaluator.evaluate_replay_post_score(
        scored,
        facts,
        _policy(
            request.invocation_id,
            price_change_min=ReplayThreshold.enabled(_operand(0)),
            price_change_max=ReplayThreshold.enabled(_operand(100)),
            volume_change_min_percent=ReplayThreshold.enabled(_operand(0)),
        ),
    )
    assert result.disposition is ReplayPostScoreDispositionV1.REJECTED
    assert [rule.disposition for rule in result.rules] == [
        ReplayPostScoreRuleDispositionV1.REJECTED,
        ReplayPostScoreRuleDispositionV1.REJECTED,
        ReplayPostScoreRuleDispositionV1.REJECTED,
    ]
    assert all(rule.reason_code == "unordered_value" for rule in result.rules)


@pytest.mark.parametrize(
    ("real_component", "expected_effect"),
    [
        (2, False),
        (1, True),
    ],
)
def test_post_score_complex_nan_uses_pandas_series_unordered_policy(
    real_component: int,
    expected_effect: bool,
) -> None:
    evaluator, scored, request = _scored()
    legacy_metric = np.complex64(complex(real_component, float("nan")))
    legacy_threshold = 1.0
    native_result = bool(
        pd.Series([legacy_metric], dtype=np.complex64).__ge__(legacy_threshold).iloc[0]
    )
    pair = project_legacy_post_score_comparison_pair(
        legacy_metric,
        legacy_threshold,
        unit=ReplayThresholdUnit.PRICE_CHANGE_PERCENT,
    )
    shared_result = compare_replay_operands(
        pair.metric,
        pair.threshold,
        operator=ReplayComparisonOperator.GREATER_THAN_OR_EQUAL,
    )
    assert native_result is False
    assert shared_result is native_result

    facts = replace(
        _post_facts(request),
        price_change=ReplayPostScoreMetricFactV1(
            status=ReplayMetricStatus.AVAILABLE,
            value=pair.metric,
        ),
    )
    result = evaluator.evaluate_replay_post_score(
        scored,
        facts,
        _policy(
            request.invocation_id,
            price_change_min=ReplayThreshold.enabled(pair.threshold),
        ),
    )

    assert result.rules[0].disposition is ReplayPostScoreRuleDispositionV1.REJECTED
    assert result.rules[0].reason_code == "unordered_value"
    assert bool(result.rules[0].effects) is expected_effect


def test_post_score_complex_nan_max_rule_returns_less_equal_effect_fact() -> None:
    evaluator, scored, request = _scored()
    metric = np.complex64(complex(1.0, float("nan")))
    pair = project_legacy_post_score_comparison_pair(
        metric,
        1.0,
        unit=ReplayThresholdUnit.PRICE_CHANGE_PERCENT,
    )
    facts = replace(
        _post_facts(request),
        price_change=ReplayPostScoreMetricFactV1(
            status=ReplayMetricStatus.AVAILABLE,
            value=pair.metric,
        ),
    )

    result = evaluator.evaluate_replay_post_score(
        scored,
        facts,
        _policy(
            request.invocation_id,
            price_change_max=ReplayThreshold.enabled(pair.threshold),
        ),
    )

    assert result.rules[0].filter_id is ReplayPostScoreRuleV1.PRICE_CHANGE_MAX
    assert result.rules[0].disposition is ReplayPostScoreRuleDispositionV1.REJECTED
    assert len(result.rules[0].effects) == 1
    assert result.rules[0].effects[0].operator is ReplayComparisonOperator.LESS_THAN_OR_EQUAL
    assert result.rules[0].effects[0].message == "invalid value encountered in less_equal"


def test_missing_metric_column_skips_even_unsupported_threshold() -> None:
    evaluator, scored, request = _scored()
    missing = ReplayPostScoreMetricFactV1(
        status=ReplayMetricStatus.MISSING_COLUMN,
        value=None,
    )
    facts = ReplayPostScoreFactsV1(
        request=request,
        price_change=missing,
        volume_change_percent=missing,
        rsi=missing,
        rsi_source_column=None,
    )
    invalid_threshold = ReplayThreshold.unsupported("legacy_invalid_value")
    result = evaluator.evaluate_replay_post_score(
        scored,
        facts,
        _policy(
            request.invocation_id,
            price_change_min=invalid_threshold,
            volume_change_min_percent=invalid_threshold,
            rsi_min=invalid_threshold,
        ),
    )
    assert result.disposition is ReplayPostScoreDispositionV1.ACCEPTED
    assert [rule.disposition for rule in result.rules] == [
        ReplayPostScoreRuleDispositionV1.SKIPPED_MISSING_COLUMN,
        ReplayPostScoreRuleDispositionV1.SKIPPED_MISSING_COLUMN,
        ReplayPostScoreRuleDispositionV1.SKIPPED_MISSING_COLUMN,
    ]


def test_final_rule_walk_does_not_short_circuit_after_a_rejection() -> None:
    evaluator, scored, request = _scored()
    result = evaluator.evaluate_replay_post_score(
        scored,
        _post_facts(request),
        _policy(
            request.invocation_id,
            price_change_min=ReplayThreshold.enabled(_operand(11)),
            price_change_max=ReplayThreshold.unsupported("legacy_invalid_max"),
        ),
    )
    assert result.disposition is ReplayPostScoreDispositionV1.UNSUPPORTED
    assert [rule.filter_id for rule in result.rules] == [
        ReplayPostScoreRuleV1.PRICE_CHANGE_MIN,
        ReplayPostScoreRuleV1.PRICE_CHANGE_MAX,
    ]
    assert [rule.disposition for rule in result.rules] == [
        ReplayPostScoreRuleDispositionV1.REJECTED,
        ReplayPostScoreRuleDispositionV1.UNSUPPORTED,
    ]

    complex_domain = ReplayComparisonDomain.python_complex()
    complex_threshold = ReplayComparisonOperand(
        origin=ReplayNumericOrigin(ReplayNumericOriginKind.PYTHON_COMPLEX),
        domain=complex_domain,
        real=ReplayComparisonComponent.finite(1),
        imaginary=ReplayComparisonComponent.finite(0),
    )
    with pytest.raises(TypeError, match="'<=' not supported between instances of 'int' and 'complex'"):
        evaluator.evaluate_replay_post_score(
            scored,
            _post_facts(request),
            _policy(
                request.invocation_id,
                price_change_min=ReplayThreshold.enabled(_operand(11)),
                price_change_max=ReplayThreshold.enabled(complex_threshold),
            ),
        )


def test_post_score_facts_and_policy_must_match_scored_invocation() -> None:
    evaluator, scored, request = _scored()
    _, other_scored, other_request = _scored(invocation_id="invocation-B")
    with pytest.raises(ValueError, match="request"):
        evaluator.evaluate_replay_post_score(
            scored,
            _post_facts(other_request),
            _policy(request.invocation_id),
        )
    with pytest.raises(ValueError, match="invocation"):
        evaluator.evaluate_replay_post_score(
            other_scored,
            _post_facts(other_request),
            _policy(request.invocation_id),
        )


def test_python_complex_keeps_native_directional_ordering_error() -> None:
    evaluator, scored, request = _scored()
    complex_domain = ReplayComparisonDomain.python_complex()
    metric = ReplayPostScoreMetricFactV1(
        status=ReplayMetricStatus.AVAILABLE,
        value=ReplayComparisonOperand(
            origin=ReplayNumericOrigin(ReplayNumericOriginKind.PYTHON_COMPLEX),
            domain=complex_domain,
            real=ReplayComparisonComponent.unordered(),
            imaginary=ReplayComparisonComponent.finite(1),
        ),
    )
    threshold = ReplayComparisonOperand(
        origin=ReplayNumericOrigin(ReplayNumericOriginKind.PYTHON_FLOAT),
        domain=complex_domain,
        real=ReplayComparisonComponent.finite(0),
        imaginary=ReplayComparisonComponent.finite(0),
    )
    facts = replace(_post_facts(request), price_change=metric)
    with pytest.raises(TypeError, match="'>=' not supported between instances of 'complex' and 'float'"):
        evaluator.evaluate_replay_post_score(
            scored,
            facts,
            _policy(request.invocation_id, price_change_min=ReplayThreshold.enabled(threshold)),
        )


def test_comparison_domain_mismatch_is_not_misreported_as_nan_rejection() -> None:
    evaluator, scored, request = _scored()
    binary = ReplayComparisonDomain.binary_real(
        "float64", precision_bits=53, min_exponent=-1022, max_exponent=1024
    )
    threshold = ReplayComparisonOperand(
        origin=ReplayNumericOrigin(ReplayNumericOriginKind.PYTHON_FLOAT),
        domain=binary,
        real=ReplayComparisonComponent.finite(0),
    )
    with pytest.raises(ReplayComparisonDomainMismatchError):
        evaluator.evaluate_replay_post_score(
            scored,
            _post_facts(request),
            _policy(request.invocation_id, price_change_min=ReplayThreshold.enabled(threshold)),
        )


def test_post_score_rejects_a_non_scored_terminal_and_pending_policy() -> None:
    evaluator, scored, request = _scored()
    response = ReplayScorerResponseV1(
        request=request,
        disposition=ReplayScorerDispositionV1.SKIPPED_EMPTY,
    )
    skipped_step = evaluator.start_replay_prefilter(
        ReplayCandidateHistoryFacts(
            invocation_id=request.invocation_id,
            observations=ReplayPrefilterObservations(
                stock_code=request.stock_code,
                as_of_date=request.as_of_date,
                history_rows=request.history_rows,
                maximum_row_date=request.as_of_date,
                availability_column_present=False,
                maximum_available_date=None,
            ),
        ),
        ReplayFastFilterPolicyV1(),
    )
    skipped = evaluator.complete_replay_scoring(skipped_step, response)
    with pytest.raises(ValueError, match="scored terminal"):
        evaluator.evaluate_replay_post_score(
            skipped,
            _post_facts(request),
            _policy(request.invocation_id),
        )
    with pytest.raises(ValueError, match="pending threshold"):
        _policy(
            request.invocation_id,
            price_change_min=ReplayThreshold.pending(),
        )


def test_deferred_post_score_resolves_thresholds_in_rule_order_after_rejection() -> None:
    """App 只在 evaluator 要求該階段時解析 raw threshold。"""

    from decision_module.recommendation.evaluate import (
        NeedReplayPostScoreThresholdV1,
        ReplayPostScoreDeferredPolicyV1,
        ReplayPostScoreThresholdResponseV1,
    )

    evaluator, request, _step = _request()
    ready = ReplayScoredRowReadyV1(request=request, facts=_post_facts(request))
    base_policy = _policy(request.invocation_id)
    staged_policy = ReplayPostScoreDeferredPolicyV1(
        policy=base_policy,
        deferred_rules=(
            ReplayPostScoreRuleV1.PRICE_CHANGE_MIN,
            ReplayPostScoreRuleV1.PRICE_CHANGE_MAX,
        ),
    )

    step = evaluator.start_replay_post_score_staged(ready, staged_policy)
    assert type(step.request) is NeedReplayPostScoreThresholdV1
    assert step.request.filter_id is ReplayPostScoreRuleV1.PRICE_CHANGE_MIN

    resolution_order: list[ReplayPostScoreRuleV1] = []

    def resolve_only_requested_threshold(
        threshold_request: NeedReplayPostScoreThresholdV1,
    ) -> ReplayPostScoreThresholdResponseV1:
        resolution_order.append(threshold_request.filter_id)
        if threshold_request.filter_id is ReplayPostScoreRuleV1.PRICE_CHANGE_MAX:
            raise TypeError("legacy max threshold conversion failed")
        assert threshold_request.filter_id is ReplayPostScoreRuleV1.PRICE_CHANGE_MIN
        return ReplayPostScoreThresholdResponseV1(
            request=threshold_request,
            threshold=ReplayThreshold.enabled(_operand(11)),
        )

    step = evaluator.advance_replay_post_score_staged(
        step, resolve_only_requested_threshold(step.request)
    )
    assert type(step.request) is NeedReplayPostScoreThresholdV1
    assert step.request.filter_id is ReplayPostScoreRuleV1.PRICE_CHANGE_MAX
    assert [rule.filter_id for rule in step.state.rules] == [
        ReplayPostScoreRuleV1.PRICE_CHANGE_MIN
    ]
    assert step.state.rules[0].disposition is ReplayPostScoreRuleDispositionV1.REJECTED

    with pytest.raises(TypeError, match="legacy max threshold conversion failed"):
        resolve_only_requested_threshold(step.request)
    assert resolution_order == [
        ReplayPostScoreRuleV1.PRICE_CHANGE_MIN,
        ReplayPostScoreRuleV1.PRICE_CHANGE_MAX,
    ]


def test_deferred_post_score_does_not_request_threshold_for_missing_rsi_column() -> None:
    from dataclasses import replace

    from decision_module.recommendation.evaluate import ReplayPostScoreDeferredPolicyV1

    evaluator, request, _step = _request()
    facts = replace(
        _post_facts(request),
        rsi=ReplayPostScoreMetricFactV1(
            status=ReplayMetricStatus.MISSING_COLUMN,
            value=None,
        ),
        rsi_source_column=None,
    )
    ready = ReplayScoredRowReadyV1(request=request, facts=facts)
    staged_policy = ReplayPostScoreDeferredPolicyV1(
        policy=_policy(request.invocation_id),
        deferred_rules=(ReplayPostScoreRuleV1.RSI_MIN,),
    )

    step = evaluator.start_replay_post_score_staged(ready, staged_policy)
    assert step.request is None
    assert step.outcome is not None
    assert step.outcome.disposition is ReplayPostScoreDispositionV1.ACCEPTED
    assert len(step.outcome.rules) == 1
    assert step.outcome.rules[0].filter_id is ReplayPostScoreRuleV1.RSI_MIN
    assert (
        step.outcome.rules[0].disposition
        is ReplayPostScoreRuleDispositionV1.SKIPPED_MISSING_COLUMN
    )


def test_deferred_post_score_requests_threshold_for_present_unsupported_metric() -> None:
    from decision_module.recommendation.evaluate import (
        NeedReplayPostScoreThresholdV1,
        ReplayPostScoreDeferredPolicyV1,
        ReplayPostScoreThresholdResponseV1,
    )

    evaluator, request, _step = _request()
    facts = replace(
        _post_facts(request),
        price_change=ReplayPostScoreMetricFactV1(
            status=ReplayMetricStatus.UNSUPPORTED,
            value=None,
            unsupported_reason="present_metric_not_projectable",
        ),
    )
    ready = ReplayScoredRowReadyV1(request=request, facts=facts)
    deferred_policy = ReplayPostScoreDeferredPolicyV1(
        policy=_policy(request.invocation_id),
        deferred_rules=(ReplayPostScoreRuleV1.PRICE_CHANGE_MIN,),
    )

    step = evaluator.start_replay_post_score_staged(ready, deferred_policy)
    assert type(step.request) is NeedReplayPostScoreThresholdV1
    assert step.request.filter_id is ReplayPostScoreRuleV1.PRICE_CHANGE_MIN

    resolver_calls: list[ReplayPostScoreRuleV1] = []

    def resolve_threshold(threshold_request: NeedReplayPostScoreThresholdV1) -> None:
        resolver_calls.append(threshold_request.filter_id)
        raise TypeError("legacy threshold conversion failed at requested stage")

    with pytest.raises(TypeError, match="legacy threshold conversion failed"):
        resolve_threshold(step.request)
    assert resolver_calls == [ReplayPostScoreRuleV1.PRICE_CHANGE_MIN]

    completed = evaluator.advance_replay_post_score_staged(
        step,
        ReplayPostScoreThresholdResponseV1(
            request=step.request,
            threshold=ReplayThreshold.enabled(_operand(0)),
        ),
    )
    assert completed.request is None
    assert completed.outcome is not None
    assert completed.outcome.disposition is ReplayPostScoreDispositionV1.UNSUPPORTED
    assert len(completed.outcome.rules) == 1
    assert completed.outcome.rules[0].filter_id is ReplayPostScoreRuleV1.PRICE_CHANGE_MIN
    assert (
        completed.outcome.rules[0].disposition
        is ReplayPostScoreRuleDispositionV1.UNSUPPORTED
    )
    assert completed.outcome.rules[0].reason_code == "present_metric_not_projectable"


@pytest.mark.parametrize(
    "threshold",
    [ReplayThreshold.disabled(), ReplayThreshold.pending()],
    ids=("disabled", "pending"),
)
def test_deferred_post_score_response_cannot_clear_present_filter(
    threshold: ReplayThreshold,
) -> None:
    from decision_module.recommendation.evaluate import (
        NeedReplayPostScoreThresholdV1,
        ReplayPostScoreDeferredPolicyV1,
        ReplayPostScoreThresholdResponseV1,
    )

    evaluator, request, _step = _request()
    ready = ReplayScoredRowReadyV1(request=request, facts=_post_facts(request))
    deferred_policy = ReplayPostScoreDeferredPolicyV1(
        policy=_policy(request.invocation_id),
        deferred_rules=(ReplayPostScoreRuleV1.PRICE_CHANGE_MIN,),
    )
    step = evaluator.start_replay_post_score_staged(ready, deferred_policy)
    assert type(step.request) is NeedReplayPostScoreThresholdV1

    with pytest.raises(ValueError, match="deferred threshold response"):
        ReplayPostScoreThresholdResponseV1(request=step.request, threshold=threshold)


def test_deferred_post_score_response_is_bound_to_requested_rule_and_candidate() -> None:
    from decision_module.recommendation.evaluate import (
        NeedReplayPostScoreThresholdV1,
        ReplayPostScoreDeferredPolicyV1,
        ReplayPostScoreThresholdResponseV1,
        SourceFactMismatchError,
    )

    evaluator, request, _step = _request()
    ready = ReplayScoredRowReadyV1(request=request, facts=_post_facts(request))
    staged_policy = ReplayPostScoreDeferredPolicyV1(
        policy=_policy(request.invocation_id),
        deferred_rules=(ReplayPostScoreRuleV1.PRICE_CHANGE_MIN,),
    )
    step = evaluator.start_replay_post_score_staged(ready, staged_policy)
    assert type(step.request) is NeedReplayPostScoreThresholdV1
    wrong_request = replace(step.request, filter_id=ReplayPostScoreRuleV1.RSI_MIN)

    with pytest.raises(SourceFactMismatchError, match="threshold response"):
        evaluator.advance_replay_post_score_staged(
            step,
            ReplayPostScoreThresholdResponseV1(
                request=wrong_request,
                threshold=ReplayThreshold.enabled(_operand(0)),
            ),
        )


def test_deferred_post_score_and_eager_policy_share_the_same_rule_result() -> None:
    from decision_module.recommendation.evaluate import (
        NeedReplayPostScoreThresholdV1,
        ReplayPostScoreDeferredPolicyV1,
        ReplayPostScoreThresholdResponseV1,
    )

    evaluator, request, _step = _request()
    ready = ReplayScoredRowReadyV1(request=request, facts=_post_facts(request))
    deferred_minimum = ReplayThreshold.enabled(_operand(10))
    deferred_maximum = ReplayThreshold.enabled(_operand(50))
    eager_policy = _policy(
        request.invocation_id,
        price_change_min=deferred_minimum,
        price_change_max=ReplayThreshold.enabled(_operand(10)),
        volume_change_min_percent=ReplayThreshold.enabled(_operand(5)),
        rsi_min=ReplayThreshold.enabled(_operand(40)),
        rsi_max=deferred_maximum,
    )
    staged_policy = ReplayPostScoreDeferredPolicyV1(
        policy=_policy(
            request.invocation_id,
            price_change_max=ReplayThreshold.enabled(_operand(10)),
            volume_change_min_percent=ReplayThreshold.enabled(_operand(5)),
            rsi_min=ReplayThreshold.enabled(_operand(40)),
        ),
        deferred_rules=(
            ReplayPostScoreRuleV1.PRICE_CHANGE_MIN,
            ReplayPostScoreRuleV1.RSI_MAX,
        ),
    )

    step = evaluator.start_replay_post_score_staged(ready, staged_policy)
    resolved = {
        ReplayPostScoreRuleV1.PRICE_CHANGE_MIN: deferred_minimum,
        ReplayPostScoreRuleV1.RSI_MAX: deferred_maximum,
    }
    while step.request is not None:
        assert type(step.request) is NeedReplayPostScoreThresholdV1
        response = ReplayPostScoreThresholdResponseV1(
            request=step.request,
            threshold=resolved[step.request.filter_id],
        )
        step = evaluator.advance_replay_post_score_staged(step, response)

    assert step.outcome is not None
    assert step.outcome == evaluator.evaluate_replay_post_score_ready(ready, eager_policy)
