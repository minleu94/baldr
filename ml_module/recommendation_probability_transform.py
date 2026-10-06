"""Shared integer-basis probability transformation for recommendation calibration.

The transformation is deliberately small and frozen: a model probability is
bounded relative to the prediction of the champion that was active at the
capture/decision cutoff.  When no active model is available, the only
permitted fallback is an explicitly named null benchmark; it must not be
described as an existing rule probability.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


PROBABILITY_TRANSFORM_ID = "recommendation-probability-transform.v2"
NULL_BENCHMARK_BASELINE_ID = "null_benchmark_50pct_v1"
NULL_BENCHMARK_PROBABILITY_BP = 5_000
# After-cost is a different target from upside.  It therefore has its own
# explicit null benchmark contract; callers must not reuse the upside baseline
# identifier while silently claiming that a liquidity-cost observation exists.
AFTER_COST_NULL_BENCHMARK_BASELINE_ID = "after_cost_null_benchmark_50pct_v1"
AFTER_COST_NULL_BENCHMARK_PROBABILITY_BP = 5_000
AFTER_COST_DECLARED_BASELINE_ID = "declared_after_cost_rule_v1"
PROBABILITY_LINEAGE_SCHEMA_VERSION = "recommendation-effective-probability-lineage.v1"


@dataclass(frozen=True)
class RecommendationProbabilityTransform:
    """Apply the same capped integer-bp mapping in capture/evaluation/consumer."""

    baseline_id: str
    maximum_probability_change_bp: int
    transform_id: str = PROBABILITY_TRANSFORM_ID

    def __post_init__(self) -> None:
        if not self.baseline_id.strip():
            raise ValueError("probability transform baseline_id is required")
        if not 0 <= self.maximum_probability_change_bp <= 10_000:
            raise ValueError("probability transform cap must be within 0..10000")
        if self.transform_id != PROBABILITY_TRANSFORM_ID:
            raise ValueError("unsupported probability transform")

    def apply(self, raw_probability_bp: int | None, baseline_probability_bp: int | None) -> int | None:
        if raw_probability_bp is None or baseline_probability_bp is None:
            return None
        _probability(raw_probability_bp, "raw_probability_bp")
        _probability(baseline_probability_bp, "baseline_probability_bp")
        cap = self.maximum_probability_change_bp
        return max(
            0,
            min(
                10_000,
                max(
                    baseline_probability_bp - cap,
                    min(baseline_probability_bp + cap, raw_probability_bp),
                ),
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "transform_id": self.transform_id,
            "baseline_id": self.baseline_id,
            "maximum_probability_change_bp": self.maximum_probability_change_bp,
        }


def _probability(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10_000:
        raise ValueError(f"{field_name} must be an integer probability bp")


__all__ = [
    "AFTER_COST_DECLARED_BASELINE_ID",
    "AFTER_COST_NULL_BENCHMARK_BASELINE_ID",
    "AFTER_COST_NULL_BENCHMARK_PROBABILITY_BP",
    "NULL_BENCHMARK_BASELINE_ID",
    "NULL_BENCHMARK_PROBABILITY_BP",
    "PROBABILITY_LINEAGE_SCHEMA_VERSION",
    "PROBABILITY_TRANSFORM_ID",
    "RecommendationProbabilityTransform",
]
