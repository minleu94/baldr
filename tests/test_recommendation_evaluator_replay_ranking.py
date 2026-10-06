from __future__ import annotations

import pytest

from decision_module.recommendation.evaluate import RecommendationEvaluator
from decision_module.recommendation.replay_policy import (
    ReplayExecutionPolicyV1,
    ReplayScoreOrderingV1,
)


@pytest.mark.parametrize("top_n", [5, 3, 0, -1, -4])
def test_replay_evaluator_ranking_and_first_slice_match_native_float_oracle(
    top_n: int,
) -> None:
    raw = (float("nan"), float("inf"), 20.0, 10.0, float("-inf"))
    scores = (
        ReplayScoreOrderingV1.nan(),
        ReplayScoreOrderingV1.positive_infinity(),
        ReplayScoreOrderingV1.finite(20),
        ReplayScoreOrderingV1.finite(10),
        ReplayScoreOrderingV1.negative_infinity(),
    )
    expected = tuple(sorted(range(len(raw)), key=raw.__getitem__, reverse=True)[:top_n])

    actual = RecommendationEvaluator().rank_replay_candidate_ordinals(
        scores,
        ReplayExecutionPolicyV1(top_n=top_n),
    )

    assert actual == expected


def test_replay_evaluator_ranking_rejects_untyped_boundary_input() -> None:
    evaluator = RecommendationEvaluator()
    policy = ReplayExecutionPolicyV1(top_n=1)

    with pytest.raises(TypeError, match="scores"):
        evaluator.rank_replay_candidate_ordinals((1,), policy)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="policy"):
        evaluator.rank_replay_candidate_ordinals((), object())  # type: ignore[arg-type]
