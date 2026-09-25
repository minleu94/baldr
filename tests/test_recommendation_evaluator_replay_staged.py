from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from decision_module.recommendation.evaluate import (
    CandidateEvaluationOutcome,
    MINIMUM_RECOMMENDATION_HISTORY_ROWS,
    NeedCandidateScoring,
    NeedReplayPrefilterFact,
    RecommendationEvaluator,
    ReplayCandidateHistoryFacts,
    ReplayCandidatePrefilterPhase,
    ReplayPrefilterFactResponse,
    SourceFactMismatchError,
)
from decision_module.recommendation.evaluation_constants import (
    MINIMUM_RECOMMENDATION_HISTORY_ROWS as SHARED_MINIMUM_HISTORY_ROWS,
)
from decision_module.recommendation.replay_prefilter import (
    ReplayComparisonComponent,
    ReplayComparisonDomain,
    ReplayComparisonOperand,
    ReplayFastFilterPolicyV1,
    ReplayMetricStatus,
    ReplayNumericOrigin,
    ReplayNumericOriginKind,
    ReplayPrefilterFactKind,
    ReplayPrefilterObservations,
    ReplayPreflightDisposition,
    ReplayThreshold,
    ReplayVolumeThresholdV1,
    evaluate_replay_prefilter,
)


AS_OF = date(2026, 9, 1)


def test_history_constant_keeps_evaluator_import_alias_and_single_value():
    assert MINIMUM_RECOMMENDATION_HISTORY_ROWS == 20
    assert MINIMUM_RECOMMENDATION_HISTORY_ROWS == SHARED_MINIMUM_HISTORY_ROWS


def _observations(
    *,
    stock_code: str = "2330",
    history_rows: int = 21,
    as_of_date: date = AS_OF,
    price_status: ReplayMetricStatus | None = None,
    volume_status: ReplayMetricStatus | None = None,
    maximum_row_date: date | None = AS_OF,
    maximum_available_date: date | None = AS_OF,
) -> ReplayPrefilterObservations:
    if price_status is None:
        price_status = (
            ReplayMetricStatus.NOT_REQUESTED
            if history_rows >= 2
            else ReplayMetricStatus.INSUFFICIENT_WINDOW
        )
    if volume_status is None:
        volume_status = (
            ReplayMetricStatus.NOT_REQUESTED
            if history_rows >= 21
            else ReplayMetricStatus.INSUFFICIENT_WINDOW
        )
    if history_rows == 0:
        maximum_row_date = None
        maximum_available_date = None
    return ReplayPrefilterObservations(
        stock_code=stock_code,
        as_of_date=as_of_date,
        history_rows=history_rows,
        maximum_row_date=maximum_row_date,
        availability_column_present=True,
        maximum_available_date=maximum_available_date,
        price_change_status=price_status,
        volume_change_status=volume_status,
    )


def _metric_response(
    request: NeedReplayPrefilterFact,
    value: Decimal | int | ReplayComparisonOperand,
) -> ReplayPrefilterFactResponse:
    return ReplayPrefilterFactResponse(
        request=request,
        metric_status=ReplayMetricStatus.AVAILABLE,
        metric_value=value,
    )


def _typed_real_operand(
    value: int,
    dtype_name: str = "float64",
    *,
    origin_dtype_name: str | None = None,
) -> ReplayComparisonOperand:
    binary_metadata = {
        "float16": (11, -14, 16),
        "float32": (24, -126, 128),
        "float64": (53, -1021, 1024),
    }
    precision_bits, min_exponent, max_exponent = binary_metadata[dtype_name]
    origin_dtype_name = origin_dtype_name or dtype_name
    domain = ReplayComparisonDomain.binary_real(
        dtype_name,
        precision_bits=precision_bits,
        min_exponent=min_exponent,
        max_exponent=max_exponent,
    )
    return ReplayComparisonOperand(
        origin=ReplayNumericOrigin(
            ReplayNumericOriginKind.NUMPY_FLOAT,
            origin_dtype_name,
        ),
        domain=domain,
        real=ReplayComparisonComponent.finite(value),
    )


def _awaiting_metric_response(
    request: NeedReplayPrefilterFact,
) -> ReplayPrefilterFactResponse:
    return ReplayPrefilterFactResponse(
        request=request,
        metric_status=ReplayMetricStatus.AWAITING_THRESHOLD_PROJECTION,
    )


def test_staged_replay_preserves_typed_metric_and_threshold_operand_identity():
    domain = ReplayComparisonDomain.binary_real(
        "float16",
        precision_bits=11,
        min_exponent=-14,
        max_exponent=16,
    )
    metric = ReplayComparisonOperand(
        origin=ReplayNumericOrigin(
            ReplayNumericOriginKind.NUMPY_FLOAT,
            "float16",
        ),
        domain=domain,
        real=ReplayComparisonComponent.finite(1),
    )
    threshold_operand = ReplayComparisonOperand(
        origin=ReplayNumericOrigin(ReplayNumericOriginKind.PYTHON_FLOAT),
        domain=domain,
        real=ReplayComparisonComponent.finite(1),
    )
    evaluator = RecommendationEvaluator()
    step = evaluator.start_replay_prefilter(
        ReplayCandidateHistoryFacts("typed-run", _observations()),
        ReplayFastFilterPolicyV1(price_change_min=ReplayThreshold.pending()),
    )

    assert isinstance(step.request, NeedReplayPrefilterFact)
    assert step.request.kind is ReplayPrefilterFactKind.PRICE_CHANGE_METRIC
    step = evaluator.advance_replay_prefilter(step.state, _metric_response(step.request, metric))
    assert isinstance(step.request, NeedReplayPrefilterFact)
    assert step.request.kind is ReplayPrefilterFactKind.PRICE_CHANGE_MIN_THRESHOLD
    step = evaluator.advance_replay_prefilter(
        step.state,
        ReplayPrefilterFactResponse(
            request=step.request,
            threshold=ReplayThreshold.enabled(threshold_operand),
        ),
    )

    assert isinstance(step.request, NeedCandidateScoring)
    assert step.state.observations.price_change_percent == metric
    assert step.state.policy.price_change_min.value == threshold_operand
    assert step.request.prefilter_outcome.disposition is ReplayPreflightDisposition.READY


def test_staged_typed_rejection_materializes_exact_rational_diagnostics():
    domain = ReplayComparisonDomain.binary_real(
        "float32",
        precision_bits=24,
        min_exponent=-126,
        max_exponent=128,
    )
    metric = ReplayComparisonOperand(
        origin=ReplayNumericOrigin(
            ReplayNumericOriginKind.NUMPY_FLOAT,
            "float32",
        ),
        domain=domain,
        real=ReplayComparisonComponent.finite(1),
    )
    threshold_operand = ReplayComparisonOperand(
        origin=ReplayNumericOrigin(ReplayNumericOriginKind.PYTHON_FLOAT),
        domain=domain,
        real=ReplayComparisonComponent.finite(2),
    )
    evaluator = RecommendationEvaluator()
    step = evaluator.start_replay_prefilter(
        ReplayCandidateHistoryFacts("typed-reject-run", _observations()),
        ReplayFastFilterPolicyV1(price_change_min=ReplayThreshold.pending()),
    )
    assert isinstance(step.request, NeedReplayPrefilterFact)
    step = evaluator.advance_replay_prefilter(step.state, _metric_response(step.request, metric))
    assert isinstance(step.request, NeedReplayPrefilterFact)
    step = evaluator.advance_replay_prefilter(
        step.state,
        ReplayPrefilterFactResponse(
            request=step.request,
            threshold=ReplayThreshold.enabled(threshold_operand),
        ),
    )

    assert step.outcome is not None
    assert step.outcome.assessment is not None
    assert step.outcome.assessment.eligible is False


def test_evaluator_owns_lazy_price_and_volume_request_order_then_stops_at_scorer():
    evaluator = RecommendationEvaluator()
    policy = ReplayFastFilterPolicyV1(
        price_change_min=ReplayThreshold.pending(),
        price_change_max=ReplayThreshold.pending(),
        volume_minimum=ReplayVolumeThresholdV1.effective_change_percent(
            ReplayThreshold.pending()
        ),
    )
    step = evaluator.start_replay_prefilter(
        ReplayCandidateHistoryFacts("run-a", _observations()), policy
    )
    requested: list[ReplayPrefilterFactKind] = []

    assert isinstance(step.request, NeedReplayPrefilterFact)
    requested.append(step.request.kind)
    step = evaluator.advance_replay_prefilter(
        step.state, _metric_response(step.request, Decimal("0"))
    )

    assert isinstance(step.request, NeedReplayPrefilterFact)
    requested.append(step.request.kind)
    step = evaluator.advance_replay_prefilter(
        step.state,
        ReplayPrefilterFactResponse(
            request=step.request,
            threshold=ReplayThreshold.enabled(Decimal("-1")),
        ),
    )

    assert isinstance(step.request, NeedReplayPrefilterFact)
    requested.append(step.request.kind)
    step = evaluator.advance_replay_prefilter(
        step.state,
        ReplayPrefilterFactResponse(
            request=step.request,
            threshold=ReplayThreshold.enabled(Decimal("1")),
        ),
    )

    assert isinstance(step.request, NeedReplayPrefilterFact)
    requested.append(step.request.kind)
    step = evaluator.advance_replay_prefilter(
        step.state, _metric_response(step.request, Decimal("0"))
    )

    assert isinstance(step.request, NeedReplayPrefilterFact)
    requested.append(step.request.kind)
    step = evaluator.advance_replay_prefilter(
        step.state,
        ReplayPrefilterFactResponse(
            request=step.request,
            volume_threshold=ReplayVolumeThresholdV1.effective_change_percent(
                ReplayThreshold.enabled(Decimal("0"))
            ),
        ),
    )

    assert isinstance(step.request, NeedCandidateScoring)
    assert step.state.phase is ReplayCandidatePrefilterPhase.NEEDS_SCORING
    assert step.request.prefilter_outcome.disposition is ReplayPreflightDisposition.READY
    assert not hasattr(step.request, "assessment")
    assert requested == [
        ReplayPrefilterFactKind.PRICE_CHANGE_METRIC,
        ReplayPrefilterFactKind.PRICE_CHANGE_MIN_THRESHOLD,
        ReplayPrefilterFactKind.PRICE_CHANGE_MAX_THRESHOLD,
        ReplayPrefilterFactKind.VOLUME_CHANGE_METRIC,
        ReplayPrefilterFactKind.VOLUME_CHANGE_MIN_THRESHOLD,
    ]
    with pytest.raises(ValueError, match="terminal replay prefilter state"):
        evaluator.advance_replay_prefilter(step.state, None)


def test_nineteen_rows_terminal_before_any_metric_or_threshold_request():
    step = RecommendationEvaluator().start_replay_prefilter(
        ReplayCandidateHistoryFacts("run-a", _observations(history_rows=19)),
        ReplayFastFilterPolicyV1(
            price_change_min=ReplayThreshold.pending(),
            price_change_max=ReplayThreshold.pending(),
            volume_minimum=ReplayVolumeThresholdV1.effective_change_percent(
                ReplayThreshold.pending()
            ),
        ),
    )

    assert step.request is None
    assert isinstance(step.outcome, CandidateEvaluationOutcome)
    assert step.outcome.status == "missing"
    assert step.outcome.reason_codes == ("insufficient_history",)
    assert step.outcome.assessment is not None
    assert step.state.phase is ReplayCandidatePrefilterPhase.COMPLETE
    assert step.state.responses == ()


def test_twenty_rows_skip_volume_fact_and_request_scoring_when_other_filters_disabled():
    step = RecommendationEvaluator().start_replay_prefilter(
        ReplayCandidateHistoryFacts("run-a", _observations(history_rows=20)),
        ReplayFastFilterPolicyV1(
            volume_minimum=ReplayVolumeThresholdV1.effective_change_percent(
                ReplayThreshold.pending()
            )
        ),
    )

    assert isinstance(step.request, NeedCandidateScoring)
    assert step.request.history_rows == 20
    assert step.state.responses == ()


def test_twenty_one_rows_requests_volume_only_after_any_enabled_price_filter():
    evaluator = RecommendationEvaluator()
    step = evaluator.start_replay_prefilter(
        ReplayCandidateHistoryFacts("run-a", _observations(history_rows=21)),
        ReplayFastFilterPolicyV1(
            price_change_min=ReplayThreshold.disabled(),
            price_change_max=ReplayThreshold.disabled(),
            volume_minimum=ReplayVolumeThresholdV1.effective_change_percent(
                ReplayThreshold.pending()
            ),
        ),
    )

    assert isinstance(step.request, NeedReplayPrefilterFact)
    assert step.request.kind is ReplayPrefilterFactKind.VOLUME_CHANGE_METRIC


def test_price_minimum_reject_is_assessed_and_stops_before_maximum_or_volume():
    evaluator = RecommendationEvaluator()
    step = evaluator.start_replay_prefilter(
        ReplayCandidateHistoryFacts("run-a", _observations()),
        ReplayFastFilterPolicyV1(
            price_change_min=ReplayThreshold.pending(),
            price_change_max=ReplayThreshold.pending(),
            volume_minimum=ReplayVolumeThresholdV1.effective_change_percent(
                ReplayThreshold.pending()
            ),
        ),
    )
    assert isinstance(step.request, NeedReplayPrefilterFact)
    step = evaluator.advance_replay_prefilter(
        step.state,
        ReplayPrefilterFactResponse(
            request=step.request,
            metric_status=ReplayMetricStatus.ZERO_DENOMINATOR,
            metric_value=Decimal("0"),
        ),
    )
    assert isinstance(step.request, NeedReplayPrefilterFact)
    assert step.request.kind is ReplayPrefilterFactKind.PRICE_CHANGE_MIN_THRESHOLD
    step = evaluator.advance_replay_prefilter(
        step.state,
        ReplayPrefilterFactResponse(
            request=step.request,
            threshold=ReplayThreshold.enabled(Decimal("1")),
        ),
    )

    assert step.request is None
    assert isinstance(step.outcome, CandidateEvaluationOutcome)
    assert step.outcome.status == "excluded"
    assert step.outcome.reason_codes == ("price_change_below_min",)
    assert step.outcome.assessment is not None
    assert step.state.responses[-1].request.kind is ReplayPrefilterFactKind.PRICE_CHANGE_MIN_THRESHOLD


def test_direct_pure_prefilter_with_partial_state_reports_need_fact_not_ready():
    outcome = evaluate_replay_prefilter(
        ReplayFastFilterPolicyV1(price_change_min=ReplayThreshold.pending()),
        _observations(),
    )

    assert outcome.disposition is ReplayPreflightDisposition.NEED_FACT
    assert outcome.required_fact is ReplayPrefilterFactKind.PRICE_CHANGE_METRIC


def test_staged_readback_rejects_cross_candidate_or_stale_request():
    evaluator = RecommendationEvaluator()
    step_a = evaluator.start_replay_prefilter(
        ReplayCandidateHistoryFacts("run-a", _observations(stock_code="A")),
        ReplayFastFilterPolicyV1(price_change_min=ReplayThreshold.pending()),
    )
    step_b = evaluator.start_replay_prefilter(
        ReplayCandidateHistoryFacts("run-a", _observations(stock_code="B")),
        ReplayFastFilterPolicyV1(price_change_min=ReplayThreshold.pending()),
    )
    assert isinstance(step_a.request, NeedReplayPrefilterFact)
    assert isinstance(step_b.request, NeedReplayPrefilterFact)
    with pytest.raises(SourceFactMismatchError, match="replay fact"):
        evaluator.advance_replay_prefilter(
            step_a.state, _metric_response(step_b.request, Decimal("0"))
        )

    stale_request = replace(step_a.request, request_id="stale-request")
    with pytest.raises(SourceFactMismatchError, match="replay fact"):
        evaluator.advance_replay_prefilter(
            step_a.state, _metric_response(stale_request, Decimal("0"))
        )


def test_pit_date_validation_remains_bound_to_replay_cutoff():
    with pytest.raises(ValueError, match="maximum_row_date 超過 replay cutoff"):
        _observations(maximum_row_date=date(2026, 9, 2))


def test_unsupported_threshold_becomes_assessed_degraded_outcome():
    evaluator = RecommendationEvaluator()
    step = evaluator.start_replay_prefilter(
        ReplayCandidateHistoryFacts("run-a", _observations()),
        ReplayFastFilterPolicyV1(price_change_min=ReplayThreshold.pending()),
    )
    assert isinstance(step.request, NeedReplayPrefilterFact)
    step = evaluator.advance_replay_prefilter(
        step.state, _metric_response(step.request, Decimal("0"))
    )
    assert isinstance(step.request, NeedReplayPrefilterFact)
    step = evaluator.advance_replay_prefilter(
        step.state,
        ReplayPrefilterFactResponse(
            request=step.request,
            threshold=ReplayThreshold.unsupported("legacy_parse_error"),
        ),
    )

    assert step.request is None
    assert isinstance(step.outcome, CandidateEvaluationOutcome)
    assert step.outcome.status == "degraded"
    assert step.outcome.assessment is not None
    assert step.outcome.reason_codes == (
        "unsupported_price_change_below_min_threshold:legacy_parse_error",
    )


def test_scoring_request_identity_is_not_reused_across_invocations():
    evaluator = RecommendationEvaluator()
    first = evaluator.start_replay_prefilter(
        ReplayCandidateHistoryFacts("run-a", _observations()),
        ReplayFastFilterPolicyV1(),
    )
    second = evaluator.start_replay_prefilter(
        ReplayCandidateHistoryFacts("run-b", _observations()),
        ReplayFastFilterPolicyV1(),
    )

    assert isinstance(first.request, NeedCandidateScoring)
    assert isinstance(second.request, NeedCandidateScoring)
    assert first.request.request_id != second.request.request_id


def test_projection_awaits_threshold_then_atomically_pairs_each_price_stage():
    evaluator = RecommendationEvaluator()
    min_metric = _typed_real_operand(1, "float16")
    max_metric = _typed_real_operand(1, "float32", origin_dtype_name="float16")
    policy = ReplayFastFilterPolicyV1(
        price_change_min=ReplayThreshold.pending(),
        price_change_max=ReplayThreshold.pending(),
    )
    step = evaluator.start_replay_prefilter(
        ReplayCandidateHistoryFacts("paired-run", _observations()), policy
    )
    assert isinstance(step.request, NeedReplayPrefilterFact)
    metric_request = step.request

    step = evaluator.advance_replay_prefilter(
        step.state, _awaiting_metric_response(metric_request)
    )
    assert isinstance(step.request, NeedReplayPrefilterFact)
    assert step.request.kind is ReplayPrefilterFactKind.PRICE_CHANGE_MIN_THRESHOLD
    assert step.state.observations.price_change_status is ReplayMetricStatus.AWAITING_THRESHOLD_PROJECTION
    assert step.state.observations.price_change_percent is None
    assert step.state.responses[0].request == metric_request

    step = evaluator.advance_replay_prefilter(
        step.state,
        ReplayPrefilterFactResponse(
            request=step.request,
            threshold=ReplayThreshold.enabled(_typed_real_operand(0, "float16")),
            paired_metric_request_id=metric_request.request_id,
            paired_metric_status=ReplayMetricStatus.AVAILABLE,
            paired_metric_value=min_metric,
        ),
    )
    assert isinstance(step.request, NeedReplayPrefilterFact)
    assert step.request.kind is ReplayPrefilterFactKind.PRICE_CHANGE_MAX_THRESHOLD
    assert step.state.observations.price_change_percent == min_metric

    step = evaluator.advance_replay_prefilter(
        step.state,
        ReplayPrefilterFactResponse(
            request=step.request,
            threshold=ReplayThreshold.enabled(_typed_real_operand(2, "float32")),
            paired_metric_request_id=metric_request.request_id,
            paired_metric_status=ReplayMetricStatus.AVAILABLE,
            paired_metric_value=max_metric,
        ),
    )
    assert isinstance(step.request, NeedCandidateScoring)
    assert [
        response.paired_metric_request_id
        for response in step.state.responses
        if response.paired_metric_request_id is not None
    ] == [metric_request.request_id, metric_request.request_id]
    assert step.state.observations.price_change_percent == max_metric


def test_threshold_pairs_for_one_metric_request_keep_origin_and_status_stable():
    evaluator = RecommendationEvaluator()
    mismatch_cases = (
        (_typed_real_operand(1, "float32", origin_dtype_name="float32"), ReplayMetricStatus.AVAILABLE),
        (_typed_real_operand(0, "float32", origin_dtype_name="float16"), ReplayMetricStatus.ZERO_DENOMINATOR),
    )
    for max_metric, max_status in mismatch_cases:
        step = evaluator.start_replay_prefilter(
            ReplayCandidateHistoryFacts("pair-origin-status", _observations()),
            ReplayFastFilterPolicyV1(
                price_change_min=ReplayThreshold.pending(),
                price_change_max=ReplayThreshold.pending(),
            ),
        )
        assert isinstance(step.request, NeedReplayPrefilterFact)
        metric_request = step.request
        step = evaluator.advance_replay_prefilter(
            step.state, _awaiting_metric_response(metric_request)
        )
        assert isinstance(step.request, NeedReplayPrefilterFact)
        step = evaluator.advance_replay_prefilter(
            step.state,
            ReplayPrefilterFactResponse(
                request=step.request,
                threshold=ReplayThreshold.enabled(_typed_real_operand(0, "float16")),
                paired_metric_request_id=metric_request.request_id,
                paired_metric_status=ReplayMetricStatus.AVAILABLE,
                paired_metric_value=_typed_real_operand(1, "float16"),
            ),
        )
        assert isinstance(step.request, NeedReplayPrefilterFact)
        assert step.request.kind is ReplayPrefilterFactKind.PRICE_CHANGE_MAX_THRESHOLD

        with pytest.raises(ValueError, match="origin/status"):
            evaluator.advance_replay_prefilter(
                step.state,
                ReplayPrefilterFactResponse(
                    request=step.request,
                    threshold=ReplayThreshold.enabled(_typed_real_operand(2, "float32")),
                    paired_metric_request_id=metric_request.request_id,
                    paired_metric_status=max_status,
                    paired_metric_value=max_metric,
                ),
            )


def test_paired_minimum_rejects_before_requesting_maximum_or_volume():
    evaluator = RecommendationEvaluator()
    metric = _typed_real_operand(1)
    step = evaluator.start_replay_prefilter(
        ReplayCandidateHistoryFacts("paired-reject", _observations()),
        ReplayFastFilterPolicyV1(
            price_change_min=ReplayThreshold.pending(),
            price_change_max=ReplayThreshold.pending(),
            volume_minimum=ReplayVolumeThresholdV1.effective_change_percent(
                ReplayThreshold.pending()
            ),
        ),
    )
    assert isinstance(step.request, NeedReplayPrefilterFact)
    metric_request = step.request
    step = evaluator.advance_replay_prefilter(
        step.state, _awaiting_metric_response(metric_request)
    )
    assert isinstance(step.request, NeedReplayPrefilterFact)
    step = evaluator.advance_replay_prefilter(
        step.state,
        ReplayPrefilterFactResponse(
            request=step.request,
            threshold=ReplayThreshold.enabled(_typed_real_operand(2)),
            paired_metric_request_id=metric_request.request_id,
            paired_metric_status=ReplayMetricStatus.AVAILABLE,
            paired_metric_value=metric,
        ),
    )

    assert step.request is None
    assert isinstance(step.outcome, CandidateEvaluationOutcome)
    assert step.outcome.status == "excluded"
    assert step.outcome.reason_codes == ("price_change_below_min",)
    assert tuple(response.request.kind for response in step.state.responses) == (
        ReplayPrefilterFactKind.PRICE_CHANGE_METRIC,
        ReplayPrefilterFactKind.PRICE_CHANGE_MIN_THRESHOLD,
    )


def test_zero_denominator_status_survives_paired_metric_projection():
    evaluator = RecommendationEvaluator()
    zero = _typed_real_operand(0)
    step = evaluator.start_replay_prefilter(
        ReplayCandidateHistoryFacts("paired-zero", _observations()),
        ReplayFastFilterPolicyV1(price_change_min=ReplayThreshold.pending()),
    )
    assert isinstance(step.request, NeedReplayPrefilterFact)
    metric_request = step.request
    step = evaluator.advance_replay_prefilter(
        step.state, _awaiting_metric_response(metric_request)
    )
    assert isinstance(step.request, NeedReplayPrefilterFact)
    step = evaluator.advance_replay_prefilter(
        step.state,
        ReplayPrefilterFactResponse(
            request=step.request,
            threshold=ReplayThreshold.enabled(_typed_real_operand(-1)),
            paired_metric_request_id=metric_request.request_id,
            paired_metric_status=ReplayMetricStatus.ZERO_DENOMINATOR,
            paired_metric_value=zero,
        ),
    )

    assert isinstance(step.request, NeedCandidateScoring)
    assert step.state.observations.price_change_status is ReplayMetricStatus.ZERO_DENOMINATOR
    assert step.state.observations.price_change_percent == zero


def test_enabled_threshold_cannot_resolve_awaiting_metric_without_pair():
    evaluator = RecommendationEvaluator()
    step = evaluator.start_replay_prefilter(
        ReplayCandidateHistoryFacts("paired-missing", _observations()),
        ReplayFastFilterPolicyV1(price_change_min=ReplayThreshold.pending()),
    )
    assert isinstance(step.request, NeedReplayPrefilterFact)
    step = evaluator.advance_replay_prefilter(
        step.state, _awaiting_metric_response(step.request)
    )
    assert isinstance(step.request, NeedReplayPrefilterFact)

    with pytest.raises(ValueError, match="paired metric"):
        evaluator.advance_replay_prefilter(
            step.state,
            ReplayPrefilterFactResponse(
                request=step.request,
                threshold=ReplayThreshold.enabled(Decimal("0")),
            ),
        )


def test_paired_projection_rejects_foreign_request_and_domain_mismatch():
    evaluator = RecommendationEvaluator()
    step_a = evaluator.start_replay_prefilter(
        ReplayCandidateHistoryFacts("inv-a", _observations(stock_code="A")),
        ReplayFastFilterPolicyV1(price_change_min=ReplayThreshold.pending()),
    )
    step_b = evaluator.start_replay_prefilter(
        ReplayCandidateHistoryFacts("inv-b", _observations(stock_code="A")),
        ReplayFastFilterPolicyV1(price_change_min=ReplayThreshold.pending()),
    )
    assert isinstance(step_a.request, NeedReplayPrefilterFact)
    assert isinstance(step_b.request, NeedReplayPrefilterFact)
    metric_request_a = step_a.request
    step_a = evaluator.advance_replay_prefilter(
        step_a.state, _awaiting_metric_response(metric_request_a)
    )
    assert isinstance(step_a.request, NeedReplayPrefilterFact)

    foreign_pair = ReplayPrefilterFactResponse(
        request=step_a.request,
        threshold=ReplayThreshold.enabled(_typed_real_operand(0)),
        paired_metric_request_id=step_b.request.request_id,
        paired_metric_status=ReplayMetricStatus.AVAILABLE,
        paired_metric_value=_typed_real_operand(1),
    )
    with pytest.raises(ValueError, match="paired_metric_request_id"):
        evaluator.advance_replay_prefilter(step_a.state, foreign_pair)

    other_domain = ReplayComparisonDomain.binary_real(
        "float32",
        precision_bits=24,
        min_exponent=-126,
        max_exponent=128,
    )
    wrong_domain_metric = ReplayComparisonOperand(
        origin=ReplayNumericOrigin(ReplayNumericOriginKind.NUMPY_FLOAT, "float32"),
        domain=other_domain,
        real=ReplayComparisonComponent.finite(1),
    )
    with pytest.raises(ValueError, match="domain"):
        ReplayPrefilterFactResponse(
            request=step_a.request,
            threshold=ReplayThreshold.enabled(_typed_real_operand(0)),
            paired_metric_request_id=metric_request_a.request_id,
            paired_metric_status=ReplayMetricStatus.AVAILABLE,
            paired_metric_value=wrong_domain_metric,
        )


def test_paired_projection_rejects_wrong_date_or_stock_source_request():
    evaluator = RecommendationEvaluator()
    as_of = date(2026, 9, 2)
    step_target = evaluator.start_replay_prefilter(
        ReplayCandidateHistoryFacts(
            "same-invocation",
            _observations(stock_code="A", as_of_date=as_of, maximum_row_date=as_of, maximum_available_date=as_of),
        ),
        ReplayFastFilterPolicyV1(price_change_min=ReplayThreshold.pending()),
    )
    step_other_code = evaluator.start_replay_prefilter(
        ReplayCandidateHistoryFacts(
            "same-invocation",
            _observations(stock_code="B", as_of_date=as_of, maximum_row_date=as_of, maximum_available_date=as_of),
        ),
        ReplayFastFilterPolicyV1(price_change_min=ReplayThreshold.pending()),
    )
    step_other_date = evaluator.start_replay_prefilter(
        ReplayCandidateHistoryFacts(
            "same-invocation",
            _observations(stock_code="A"),
        ),
        ReplayFastFilterPolicyV1(price_change_min=ReplayThreshold.pending()),
    )
    assert isinstance(step_target.request, NeedReplayPrefilterFact)
    assert isinstance(step_other_code.request, NeedReplayPrefilterFact)
    assert isinstance(step_other_date.request, NeedReplayPrefilterFact)
    target_metric_request = step_target.request
    step_target = evaluator.advance_replay_prefilter(
        step_target.state, _awaiting_metric_response(target_metric_request)
    )
    assert isinstance(step_target.request, NeedReplayPrefilterFact)

    for foreign_request in (step_other_code.request, step_other_date.request):
        with pytest.raises(ValueError, match="paired_metric_request_id"):
            evaluator.advance_replay_prefilter(
                step_target.state,
                ReplayPrefilterFactResponse(
                    request=step_target.request,
                    threshold=ReplayThreshold.enabled(_typed_real_operand(0)),
                    paired_metric_request_id=foreign_request.request_id,
                    paired_metric_status=ReplayMetricStatus.AVAILABLE,
                    paired_metric_value=_typed_real_operand(1),
                ),
            )


def test_volume_projection_cannot_reuse_price_metric_request_stage():
    evaluator = RecommendationEvaluator()
    step = evaluator.start_replay_prefilter(
        ReplayCandidateHistoryFacts("stage-run", _observations()),
        ReplayFastFilterPolicyV1(
            price_change_min=ReplayThreshold.pending(),
            volume_minimum=ReplayVolumeThresholdV1.effective_change_percent(
                ReplayThreshold.pending()
            ),
        ),
    )
    assert isinstance(step.request, NeedReplayPrefilterFact)
    price_metric_request = step.request
    step = evaluator.advance_replay_prefilter(
        step.state, _awaiting_metric_response(price_metric_request)
    )
    assert isinstance(step.request, NeedReplayPrefilterFact)
    step = evaluator.advance_replay_prefilter(
        step.state,
        ReplayPrefilterFactResponse(
            request=step.request,
            threshold=ReplayThreshold.enabled(_typed_real_operand(0)),
            paired_metric_request_id=price_metric_request.request_id,
            paired_metric_status=ReplayMetricStatus.AVAILABLE,
            paired_metric_value=_typed_real_operand(1),
        ),
    )
    assert isinstance(step.request, NeedReplayPrefilterFact)
    assert step.request.kind is ReplayPrefilterFactKind.VOLUME_CHANGE_METRIC
    volume_metric_request = step.request
    step = evaluator.advance_replay_prefilter(
        step.state, _awaiting_metric_response(volume_metric_request)
    )
    assert isinstance(step.request, NeedReplayPrefilterFact)
    assert step.request.kind is ReplayPrefilterFactKind.VOLUME_CHANGE_MIN_THRESHOLD

    with pytest.raises(ValueError, match="identity/stage"):
        evaluator.advance_replay_prefilter(
            step.state,
            ReplayPrefilterFactResponse(
                request=step.request,
                volume_threshold=ReplayVolumeThresholdV1.effective_change_percent(
                    ReplayThreshold.enabled(_typed_real_operand(0))
                ),
                paired_metric_request_id=price_metric_request.request_id,
                paired_metric_status=ReplayMetricStatus.AVAILABLE,
                paired_metric_value=_typed_real_operand(1),
            ),
        )


def test_pending_projection_rejects_non_threshold_fact_kind_with_value_error():
    with pytest.raises(ValueError, match="threshold fact kind"):
        evaluate_replay_prefilter(
            ReplayFastFilterPolicyV1(),
            _observations(),
            pending_projection_stages=(ReplayPrefilterFactKind.PRICE_CHANGE_METRIC,),
        )
