from __future__ import annotations

import pytest

from ml_module.historical_evaluation import evaluate_historical_predictions, evaluate_return_predictions


def test_evaluation_returns_deterministic_integer_metrics() -> None:
    metrics = evaluate_historical_predictions(
        return_targets_bp=(1000, 500, -500, -1000),
        downside_targets=(0, 0, 1, 1),
        return_predictions_bp=(900, 400, -400, -900),
        ranking_scores=(4, 3, 2, 1),
        downside_probabilities_bp=(1000, 2000, 8000, 9000),
        top_k=2,
    )

    assert metrics == {
        "coverage_bp": 10000,
        "mae_bp": 100,
        "brier_bp": 250,
        "precision_at_k_bp": 10000,
        "ndcg_bp": 10000,
        "bucket_monotonicity_bp": 10000,
    }
    assert all(type(value) is int for value in metrics.values())
    assert tuple(metrics) == ("coverage_bp", "mae_bp", "brier_bp", "precision_at_k_bp",
                              "ndcg_bp", "bucket_monotonicity_bp")


def test_return_only_metrics_match_existing_without_fabricated_downside() -> None:
    common = dict(return_targets_bp=(1000, 500, -500, -1000),
                  return_predictions_bp=(900, 400, -400, -900),
                  ranking_scores=(4, 3, 2, 1), top_k=2)
    legacy = evaluate_historical_predictions(**common, downside_targets=(0, 0, 1, 1),
        downside_probabilities_bp=(1000, 2000, 8000, 9000))
    only = evaluate_return_predictions(**common)
    assert "brier_bp" not in only
    assert only == {key: value for key, value in legacy.items() if key != "brier_bp"}


@pytest.mark.parametrize("targets,predictions,scores,k", [
    ((), (), (), 1), ((1,), (), (1,), 1), ((1,), (1,), (1,), 2),
])
def test_return_only_does_not_score_empty_misaligned_or_insufficient_common_samples(targets, predictions, scores, k):
    with pytest.raises(ValueError):
        evaluate_return_predictions(return_targets_bp=targets, return_predictions_bp=predictions,
                                    ranking_scores=scores, top_k=k)
