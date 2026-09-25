"""固定 post-score lazy threshold 與候選 metric 的同域配對契約。"""

from dataclasses import replace
from datetime import date

import pytest

from decision_module.recommendation.evaluate import (
    NeedCandidateScoring,
    NeedReplayPostScoreThresholdV1,
    ReplayCandidateHistoryFacts,
    ReplayPostScoreDeferredPolicyV1,
    ReplayPostScoreDispositionV1,
    ReplayPostScoreFactsV1,
    ReplayPostScoreMetricFactV1,
    ReplayPostScorePolicyV1,
    ReplayPostScoreRuleV1,
    ReplayPostScorePairedMetricV1,
    ReplayPostScoreThresholdResponseV1,
    ReplayScoredRowReadyV1,
    RecommendationEvaluator,
    SourceFactMismatchError,
)
from decision_module.recommendation.replay_prefilter import (
    ReplayComparisonComponent,
    ReplayComparisonDomain,
    ReplayComparisonOperand,
    ReplayFastFilterPolicyV1,
    ReplayMetricStatus,
    ReplayNumericOrigin,
    ReplayNumericOriginKind,
    ReplayPrefilterObservations,
    ReplayThreshold,
)


def _operand(value: int, *, format_name: str) -> ReplayComparisonOperand:
    if format_name == "float16":
        domain = ReplayComparisonDomain.binary_real(
            format_name, precision_bits=11, min_exponent=-14, max_exponent=16
        )
    elif format_name == "float64":
        domain = ReplayComparisonDomain.binary_real(
            format_name, precision_bits=53, min_exponent=-1022, max_exponent=1024
        )
    else:
        raise AssertionError("測試只使用已宣告的 binary domain")
    return ReplayComparisonOperand(
        origin=ReplayNumericOrigin(
            ReplayNumericOriginKind.NUMPY_FLOAT, dtype_name=format_name
        ),
        domain=domain,
        real=ReplayComparisonComponent.finite(value),
    )


def _ready(
    stock_code: str = "PAIR",
) -> tuple[RecommendationEvaluator, NeedCandidateScoring, ReplayScoredRowReadyV1]:
    evaluator = RecommendationEvaluator()
    facts = ReplayCandidateHistoryFacts(
        invocation_id="pairing-invocation",
        observations=ReplayPrefilterObservations(
            stock_code=stock_code,
            as_of_date=date(2026, 9, 21),
            history_rows=21,
            maximum_row_date=date(2026, 9, 21),
            availability_column_present=False,
            maximum_available_date=None,
        ),
    )
    prefilter = evaluator.start_replay_prefilter(facts, ReplayFastFilterPolicyV1())
    request = prefilter.request
    assert type(request) is NeedCandidateScoring
    awaiting = ReplayPostScoreMetricFactV1(
        status=ReplayMetricStatus.AWAITING_THRESHOLD_PROJECTION,
        value=None,
    )
    missing = ReplayPostScoreMetricFactV1(
        status=ReplayMetricStatus.MISSING_COLUMN,
        value=None,
    )
    post_facts = ReplayPostScoreFactsV1(
        request=request,
        price_change=awaiting,
        volume_change_percent=missing,
        rsi=missing,
        rsi_source_column=None,
    )
    return evaluator, request, ReplayScoredRowReadyV1(request, post_facts)


def _deferred(
    request: NeedCandidateScoring,
) -> ReplayPostScoreDeferredPolicyV1:
    return ReplayPostScoreDeferredPolicyV1(
        policy=ReplayPostScorePolicyV1(invocation_id=request.invocation_id),
        deferred_rules=(
            ReplayPostScoreRuleV1.PRICE_CHANGE_MIN,
            ReplayPostScoreRuleV1.PRICE_CHANGE_MAX,
        ),
    )


def _response(
    request: NeedReplayPostScoreThresholdV1,
    *,
    metric_value: int,
    threshold_value: int,
    format_name: str,
) -> ReplayPostScoreThresholdResponseV1:
    domain_metric = _operand(metric_value, format_name=format_name)
    domain_threshold = _operand(threshold_value, format_name=format_name)
    return ReplayPostScoreThresholdResponseV1(
        request=request,
        threshold=ReplayThreshold.enabled(domain_threshold),
        paired_metric=ReplayPostScorePairedMetricV1(
            request=request,
            metric=ReplayPostScoreMetricFactV1(
                status=ReplayMetricStatus.AVAILABLE,
                value=domain_metric,
            ),
        ),
    )


def test_post_score_metric_can_wait_for_threshold_domain_projection() -> None:
    fact = ReplayPostScoreMetricFactV1(
        status=ReplayMetricStatus.AWAITING_THRESHOLD_PROJECTION,
        value=None,
    )
    assert fact.status is ReplayMetricStatus.AWAITING_THRESHOLD_PROJECTION
    assert fact.value is None


def test_each_shared_price_rule_uses_its_own_paired_domain() -> None:
    evaluator, request, ready = _ready()
    step = evaluator.start_replay_post_score_staged(ready, _deferred(request))
    assert type(step.request) is NeedReplayPostScoreThresholdV1
    assert step.request.filter_id is ReplayPostScoreRuleV1.PRICE_CHANGE_MIN

    step = evaluator.advance_replay_post_score_staged(
        step,
        _response(
            step.request,
            metric_value=1,
            threshold_value=0,
            format_name="float16",
        ),
    )
    assert type(step.request) is NeedReplayPostScoreThresholdV1
    assert step.request.filter_id is ReplayPostScoreRuleV1.PRICE_CHANGE_MAX
    assert (
        step.state.ready.facts.price_change.status
        is ReplayMetricStatus.AWAITING_THRESHOLD_PROJECTION
    )

    step = evaluator.advance_replay_post_score_staged(
        step,
        _response(
            step.request,
            metric_value=1,
            threshold_value=2,
            format_name="float64",
        ),
    )
    assert step.request is None
    assert step.outcome is not None
    assert step.outcome.disposition is ReplayPostScoreDispositionV1.ACCEPTED


def test_pending_threshold_requires_identity_bound_paired_metric() -> None:
    evaluator, request, ready = _ready()
    step = evaluator.start_replay_post_score_staged(ready, _deferred(request))
    assert step.request is not None
    missing_pair = ReplayPostScoreThresholdResponseV1(
        request=step.request,
        threshold=ReplayThreshold.enabled(_operand(0, format_name="float16")),
    )
    with pytest.raises((TypeError, ValueError, SourceFactMismatchError)):
        evaluator.advance_replay_post_score_staged(step, missing_pair)

    wrong_candidate = replace(
        step.request,
        request_id=step.request.request_id + ":other",
    )
    wrong_pair = _response(
        wrong_candidate,
        metric_value=1,
        threshold_value=0,
        format_name="float16",
    )
    with pytest.raises(SourceFactMismatchError):
        evaluator.advance_replay_post_score_staged(step, wrong_pair)


def test_threshold_and_paired_metric_must_share_the_current_domain() -> None:
    evaluator, request, ready = _ready()
    step = evaluator.start_replay_post_score_staged(ready, _deferred(request))
    assert step.request is not None
    with pytest.raises(ValueError, match="domain"):
        ReplayPostScoreThresholdResponseV1(
            request=step.request,
            threshold=ReplayThreshold.enabled(_operand(0, format_name="float64")),
            paired_metric=ReplayPostScorePairedMetricV1(
                request=step.request,
                metric=ReplayPostScoreMetricFactV1(
                    status=ReplayMetricStatus.AVAILABLE,
                    value=_operand(1, format_name="float16"),
                ),
            ),
        )


def test_same_candidate_with_different_scored_facts_rejects_stale_pair() -> None:
    evaluator_a, request_a, ready_a = _ready()
    step_a = evaluator_a.start_replay_post_score_staged(ready_a, _deferred(request_a))
    assert step_a.request is not None

    evaluator_b, request_b, ready_b = _ready()
    assert request_a == request_b
    step_b = evaluator_b.start_replay_post_score_staged(ready_b, _deferred(request_b))
    assert step_b.request is not None
    assert step_a.request.request_id == step_b.request.request_id
    assert step_a.request.facts_identity_token is not step_b.request.facts_identity_token

    stale_response = _response(
        step_a.request,
        metric_value=1,
        threshold_value=0,
        format_name="float16",
    )
    with pytest.raises(SourceFactMismatchError, match="identity"):
        evaluator_b.advance_replay_post_score_staged(step_b, stale_response)


def test_paired_metric_cannot_be_rebound_to_another_rule() -> None:
    evaluator, request, ready = _ready()
    step = evaluator.start_replay_post_score_staged(ready, _deferred(request))
    assert step.request is not None
    wrong_rule_request = replace(
        step.request,
        filter_id=ReplayPostScoreRuleV1.PRICE_CHANGE_MAX,
    )
    paired = ReplayPostScorePairedMetricV1(
        request=wrong_rule_request,
        metric=ReplayPostScoreMetricFactV1(
            status=ReplayMetricStatus.AVAILABLE,
            value=_operand(1, format_name="float16"),
        ),
    )
    with pytest.raises(SourceFactMismatchError, match="paired metric"):
        ReplayPostScoreThresholdResponseV1(
            request=step.request,
            threshold=ReplayThreshold.enabled(_operand(0, format_name="float16")),
            paired_metric=paired,
        )
