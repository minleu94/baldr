"""Neutral protocol for frozen recommendation-calibration inference.

The application consumer implements this protocol, while ML-side capture and
evidence producers depend only on the protocol.  This keeps the evidence
producer independent from the application projection namespace without
silently replacing an active champion with a permanent ``None`` fallback.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence

from ml_module.recommendation_calibration_training import RecommendationPrediction


class FrozenRecommendationInference(Protocol):
    """Read-only active/champion inference surface required by ML capture."""

    def reload(self, *, decision_date: str | None = None) -> str:
        """Reload the frozen pointer and return its machine-readable status."""

    def active_identity(self, *, decision_date: str) -> Mapping[str, Any] | None:
        """Return the verified active model identity and probability lineage."""

    def predict_active(
        self,
        *,
        feature_values: Sequence[int | None],
        decision_date: str,
        baseline_probability_bp: int = 5_000,
        baseline_after_cost_probability_bp: int | None = None,
    ) -> RecommendationPrediction | None:
        """Return the effective prediction from the verified active model."""
