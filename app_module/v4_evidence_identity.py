"""Versioned identity constants for the scheduled V4 research cohort.

The scheduled recommendation path needs an explicit cohort identity so that
future outcomes can be grouped without guessing from a profile or a current
stock pool.  The cost identity below intentionally describes a gross,
unpriced observation; it is not a cost-adjusted performance claim.
"""

from __future__ import annotations


SCHEDULED_RECOMMENDATION_STRATEGY_VERSION_ID = "scheduled-recommendation-default-v1"
SCHEDULED_RECOMMENDATION_COST_MODEL_ID = "gross-close-to-close-no-cost-v1"
SCHEDULED_RECOMMENDATION_BENCHMARK_ID = "TAIEX"
SCHEDULED_RECOMMENDATION_PRIMARY_HORIZON_DAYS = 20

# Forward outcome storage evaluates every declared window.  The primary
# horizon is kept separately in the event identity for cohort reporting.
SCHEDULED_RECOMMENDATION_OUTCOME_WINDOWS = (5, 10, 20, 60)

UNMODELED_COST_MODEL_IDS = frozenset({SCHEDULED_RECOMMENDATION_COST_MODEL_ID})


__all__ = [
    "SCHEDULED_RECOMMENDATION_BENCHMARK_ID",
    "SCHEDULED_RECOMMENDATION_COST_MODEL_ID",
    "SCHEDULED_RECOMMENDATION_OUTCOME_WINDOWS",
    "SCHEDULED_RECOMMENDATION_PRIMARY_HORIZON_DAYS",
    "SCHEDULED_RECOMMENDATION_STRATEGY_VERSION_ID",
    "UNMODELED_COST_MODEL_IDS",
]
