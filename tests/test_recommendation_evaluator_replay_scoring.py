from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from decision_module.recommendation.contracts import FilterOutcome, RecommendationItem
from decision_module.recommendation.evaluate import (
    NeedCandidateScoring,
    RecommendationEvaluator,
    ReplayCandidateHistoryFacts,
    ReplayCandidatePrefilterStep,
    ReplayCandidateScoringOutcomeV1,
    ReplayScorerDispositionV1,
    ReplayScorerResponseV1,
    SourceFactMismatchError,
)
from decision_module.recommendation.replay_policy import (
    ReplayScoreOrderingKindV1,
    ReplayScoreOrderingV1,
)
from decision_module.recommendation.replay_prefilter import (
    ReplayFastFilterPolicyV1,
    ReplayMetricStatus,
    ReplayPrefilterObservations,
)


AS_OF = date(2026, 9, 22)


def _ready_prefilter_step(
    *, stock_code: str = "2330", invocation_id: str = "run-A"
) -> ReplayCandidatePrefilterStep:
    observations = ReplayPrefilterObservations(
        stock_code=stock_code,
        as_of_date=AS_OF,
        history_rows=20,
        maximum_row_date=AS_OF,
        availability_column_present=False,
        maximum_available_date=None,
        price_change_status=ReplayMetricStatus.NOT_REQUESTED,
        volume_change_status=ReplayMetricStatus.INSUFFICIENT_WINDOW,
    )
    return RecommendationEvaluator().start_replay_prefilter(
        ReplayCandidateHistoryFacts(
            invocation_id=invocation_id,
            observations=observations,
        ),
        ReplayFastFilterPolicyV1(),
    )


def _request(step: ReplayCandidatePrefilterStep) -> NeedCandidateScoring:
    assert type(step.request) is NeedCandidateScoring
    return step.request


@pytest.mark.parametrize(
    "ordering",
    [
        ReplayScoreOrderingV1.nan(),
        ReplayScoreOrderingV1.positive_infinity(),
        ReplayScoreOrderingV1.negative_infinity(),
    ],
)
def test_replay_scoring_accepts_nonfinite_ordering_with_none_canonical_score(
    ordering: ReplayScoreOrderingV1,
) -> None:
    step = _ready_prefilter_step()
    item = RecommendationItem(stock_code="2330", rule_score=None)
    response = ReplayScorerResponseV1(
        request=_request(step),
        disposition=ReplayScorerDispositionV1.SCORED,
        item=item,
        score_ordering=ordering,
    )

    result = RecommendationEvaluator().complete_replay_scoring(step, response)

    assert result.response is response
    assert result.request == _request(step)
    assert result.item is item
    assert result.score_ordering is ordering
    assert result.assessment.stock_code == "2330"
    assert result.assessment.eligible is True
    assert result.assessment.filter_outcomes["replay_prefilter"].passed is True
    assert result.assessment.filter_outcomes["replay_scoring"].passed is True
    assert result.reason_code is None


def test_replay_scoring_accepts_finite_projected_item_and_ordering() -> None:
    step = _ready_prefilter_step()
    response = ReplayScorerResponseV1(
        request=_request(step),
        disposition=ReplayScorerDispositionV1.SCORED,
        item=RecommendationItem(stock_code="2330", rule_score=Decimal("0.1")),
        score_ordering=ReplayScoreOrderingV1.finite(1, 10),
    )

    result = RecommendationEvaluator().complete_replay_scoring(step, response)

    assert result.disposition is ReplayScorerDispositionV1.SCORED
    assert result.item is not None and result.item.rule_score == Decimal("0.1")
    assert result.score_ordering == ReplayScoreOrderingV1.finite(1, 10)


@pytest.mark.parametrize(
    ("disposition", "error_type", "reason_code"),
    [
        (ReplayScorerDispositionV1.SKIPPED_EMPTY, None, "scorer_empty_result"),
        (
            ReplayScorerDispositionV1.SKIPPED_SCORER_EXCEPTION,
            "RuntimeError",
            "scorer_exception",
        ),
        (
            ReplayScorerDispositionV1.SKIPPED_PROJECTION_EXCEPTION,
            "InvalidOperation",
            "item_projection_exception",
        ),
    ],
)
def test_replay_scoring_skips_keep_candidate_assessment_reason(
    disposition: ReplayScorerDispositionV1,
    error_type: str | None,
    reason_code: str,
) -> None:
    step = _ready_prefilter_step()
    response = ReplayScorerResponseV1(
        request=_request(step),
        disposition=disposition,
        error_type=error_type,
    )

    result = RecommendationEvaluator().complete_replay_scoring(step, response)

    assert result.disposition is disposition
    assert result.item is None
    assert result.score_ordering is None
    assert result.error_type == error_type
    assert result.reason_code == reason_code
    assert result.assessment.stock_code == "2330"
    assert result.assessment.eligible is None
    assert result.assessment.reasons == (reason_code,)
    assert result.assessment.filter_outcomes["replay_prefilter"].passed is True
    scoring_filter = result.assessment.filter_outcomes["replay_scoring"]
    assert scoring_filter.passed is None
    assert scoring_filter.reason == reason_code
    assert scoring_filter.evidence["error_type"] == error_type


def test_replay_scoring_rejects_response_from_another_handoff() -> None:
    step_a = _ready_prefilter_step(stock_code="2330", invocation_id="run-A")
    step_b = _ready_prefilter_step(stock_code="2317", invocation_id="run-B")
    response_b = ReplayScorerResponseV1(
        request=_request(step_b),
        disposition=ReplayScorerDispositionV1.SKIPPED_EMPTY,
    )

    with pytest.raises(SourceFactMismatchError, match="request"):
        RecommendationEvaluator().complete_replay_scoring(step_a, response_b)


@pytest.mark.parametrize(
    "request_change",
    [
        {"request_id": "other-request"},
        {"invocation_id": "run-B"},
    ],
)
def test_replay_scoring_rejects_changed_request_identity_fields(
    request_change: dict[str, str],
) -> None:
    step = _ready_prefilter_step()
    changed_request = replace(_request(step), **request_change)
    response = ReplayScorerResponseV1(
        request=changed_request,
        disposition=ReplayScorerDispositionV1.SKIPPED_EMPTY,
    )

    with pytest.raises(SourceFactMismatchError):
        RecommendationEvaluator().complete_replay_scoring(step, response)


def test_replay_scoring_requires_ready_handoff_and_matching_item_code() -> None:
    evaluator = RecommendationEvaluator()
    not_ready = evaluator.start_replay_prefilter(
        ReplayCandidateHistoryFacts(
            invocation_id="run-A",
            observations=ReplayPrefilterObservations(
                stock_code="2330",
                as_of_date=AS_OF,
                history_rows=19,
                maximum_row_date=AS_OF,
                availability_column_present=False,
                maximum_available_date=None,
            ),
        ),
        ReplayFastFilterPolicyV1(),
    )
    ready = _ready_prefilter_step()
    response = ReplayScorerResponseV1(
        request=_request(ready),
        disposition=ReplayScorerDispositionV1.SKIPPED_EMPTY,
    )

    with pytest.raises(ValueError, match="NeedCandidateScoring"):
        evaluator.complete_replay_scoring(not_ready, response)

    with pytest.raises(ValueError, match="stock_code"):
        ReplayScorerResponseV1(
            request=_request(ready),
            disposition=ReplayScorerDispositionV1.SCORED,
            item=RecommendationItem(stock_code="2317", rule_score=None),
            score_ordering=ReplayScoreOrderingV1.nan(),
        )


def test_replay_scoring_response_rejects_raw_exception_and_mixed_payloads() -> None:
    request = _request(_ready_prefilter_step())

    with pytest.raises(TypeError, match="exception instance"):
        ReplayScorerResponseV1(
            request=request,
            disposition=ReplayScorerDispositionV1.SKIPPED_SCORER_EXCEPTION,
            error_type=RuntimeError("raw exception is not part of the pure response"),  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="不可帶 item 或 score_ordering"):
        ReplayScorerResponseV1(
            request=request,
            disposition=ReplayScorerDispositionV1.SKIPPED_EMPTY,
            item=RecommendationItem(stock_code="2330"),
        )
    with pytest.raises(ValueError, match="必須配有限"):
        ReplayScorerResponseV1(
            request=request,
            disposition=ReplayScorerDispositionV1.SCORED,
            item=RecommendationItem(stock_code="2330", rule_score=Decimal("1")),
            score_ordering=ReplayScoreOrderingV1.nan(),
        )


def test_replay_scoring_outcome_requires_consistent_assessment() -> None:
    step = _ready_prefilter_step()
    response = ReplayScorerResponseV1(
        request=_request(step),
        disposition=ReplayScorerDispositionV1.SKIPPED_EMPTY,
    )
    result = RecommendationEvaluator().complete_replay_scoring(step, response)

    with pytest.raises(ValueError, match="skip reason"):
        ReplayCandidateScoringOutcomeV1(
            response=response,
            assessment=replace(result.assessment, reasons=()),
        )

    original_filters = result.assessment.filter_outcomes
    assert original_filters is not None
    altered_prefilter = FilterOutcome(
        filter_id="replay_prefilter",
        passed=True,
        reason="ready",
        evidence={
            "as_of_date": "2099-01-01",
            "history_rows": _request(step).history_rows,
            "reason_code": "ready",
            "stage": "ready",
        },
    )
    with pytest.raises(ValueError, match="prefilter evidence"):
        ReplayCandidateScoringOutcomeV1(
            response=response,
            assessment=replace(
                result.assessment,
                filter_outcomes={
                    **original_filters,
                    "replay_prefilter": altered_prefilter,
                },
            ),
        )
