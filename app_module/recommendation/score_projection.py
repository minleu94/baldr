"""app boundary for preserving legacy score values beside canonical scores."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import math
from typing import cast, Any

import numpy as np

from decision_module.recommendation.evaluate import RecommendationScore
from decision_module.score_threshold_policy import quantize_score_to_basis_points


@dataclass(frozen=True, slots=True)
class LegacyScoreProjection:
    """Invocation-local original scalar retained for the old DTO facade only."""

    value: object
    runtime_type: str
    contract_value: Decimal | int
    score: RecommendationScore


def project_legacy_recommendation_score(
    value: object,
    *,
    include_quantile_score_bp: bool = True,
) -> LegacyScoreProjection:
    """Build an exact order key and old quantile bp without leaking floats to decision.

    Decimal.from_float preserves the exact IEEE value for fixed-rank comparisons. The
    legacy quantizer receives the untouched scalar so its Decimal(str(value)) and
    ROUND_HALF_UP behavior remains unchanged for quantile selection.
    """

    if type(value) is Decimal:
        if not value.is_finite():
            raise ValueError("recommendation score must be finite")
        order_value: Decimal | int | str = value
        contract_value: Decimal | int = value
    elif type(value) is int:
        order_value = value
        contract_value = value
    elif isinstance(value, np.integer):
        integer_value = int(value)
        order_value = integer_value
        contract_value = integer_value
    elif type(value) is str:
        try:
            string_value = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("recommendation score string must be numeric") from exc
        if not string_value.is_finite():
            raise ValueError("recommendation score must be finite")
        order_value = value
        contract_value = string_value
    elif type(value) in (float, np.float16, np.float32, np.float64):
        float_value = float(cast(Any, value))
        if not math.isfinite(float_value):
            raise ValueError("recommendation score must be finite")
        order_value = Decimal.from_float(float_value)
        contract_value = Decimal(str(value))
    else:
        raise TypeError(
            "legacy recommendation score must be Decimal, int, float scalar, or numeric string"
        )

    score_bp = (
        quantize_score_to_basis_points(value)
        if include_quantile_score_bp
        else None
    )
    return LegacyScoreProjection(
        value=value,
        runtime_type=type(value).__name__,
        contract_value=contract_value,
        score=RecommendationScore(
            ordering_value=order_value,
            quantile_score_bp=score_bp,
        ),
    )


__all__ = ("LegacyScoreProjection", "project_legacy_recommendation_score")
