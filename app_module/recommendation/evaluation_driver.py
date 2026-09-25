"""Application orchestration for a decision-owned staged candidate evaluation."""

from __future__ import annotations

from typing import Callable

from decision_module.recommendation.evaluate import (
    CandidateEvaluationOutcome,
    CandidateSeed,
    NeedSourceFact,
    RecommendationEvaluationPolicy,
    RecommendationEvaluator,
    SourceFactError,
    SourceFactResponse,
)


SourceFactReader = Callable[[NeedSourceFact], SourceFactResponse]


def evaluate_candidate_staged(
    evaluator: RecommendationEvaluator,
    seed: CandidateSeed,
    policy: RecommendationEvaluationPolicy,
    read_source_fact: SourceFactReader,
) -> CandidateEvaluationOutcome:
    """Read exactly the one fact requested by decision, then resume that state.

    The callback owns source dispatch and projection. Exceptions become typed
    responses for the evaluator to map according to the pending fact kind.
    """

    step = evaluator.start(seed, policy)
    while step.request is not None:
        request = step.request
        try:
            response = read_source_fact(request)
        except Exception as exc:
            response = SourceFactResponse(
                request=request,
                error=SourceFactError(
                    error_type=type(exc).__name__,
                    message=str(exc),
                ),
            )
        step = evaluator.advance(step.state, response)
    assert step.outcome is not None
    return step.outcome


__all__ = ("evaluate_candidate_staged",)
