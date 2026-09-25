from __future__ import annotations

from decimal import Decimal

import numpy as np
import pytest

from app_module.recommendation.replay_numeric_projection import (
    ReplayThresholdUnit,
    UnsupportedReplayNumericScalarError,
    project_legacy_post_score_comparison_pair,
)
from decision_module.recommendation.replay_prefilter import (
    ReplayComparisonDomainKind,
    ReplayNumericOriginKind,
)


_UNIT = ReplayThresholdUnit.PRICE_CHANGE_PERCENT


def test_python_native_pair_preserves_exact_numeric_provenance() -> None:
    pair = project_legacy_post_score_comparison_pair(
        3,
        Decimal("1.25"),
        unit=_UNIT,
    )

    assert pair.metric.domain.kind is ReplayComparisonDomainKind.EXACT_RATIONAL
    assert pair.threshold.domain.kind is ReplayComparisonDomainKind.EXACT_RATIONAL
    assert pair.metric.origin.kind is ReplayNumericOriginKind.PYTHON_INT
    assert pair.threshold.origin.kind is ReplayNumericOriginKind.LEGACY_DECIMAL
    assert pair.metric.real.numerator == 3
    assert pair.metric.real.denominator == 1
    assert pair.threshold.real.numerator == 5
    assert pair.threshold.real.denominator == 4


def test_numpy_weak_promotion_keeps_effective_real_domain() -> None:
    pair = project_legacy_post_score_comparison_pair(
        np.int32(3),
        1.5,
        unit=_UNIT,
    )

    assert pair.metric.domain.kind is ReplayComparisonDomainKind.BINARY_REAL
    assert pair.threshold.domain == pair.metric.domain
    assert pair.metric.origin.kind is ReplayNumericOriginKind.NUMPY_INTEGER
    assert pair.metric.origin.dtype_name == "int32"
    assert pair.threshold.origin.kind is ReplayNumericOriginKind.PYTHON_FLOAT
    assert pair.metric.real.numerator is not None
    assert pair.threshold.real.numerator is not None


def test_numpy_complex_pair_preserves_non_orderable_domain() -> None:
    pair = project_legacy_post_score_comparison_pair(
        np.complex64(1 + 2j),
        2.0,
        unit=_UNIT,
    )

    assert pair.metric.domain.kind is ReplayComparisonDomainKind.NUMPY_COMPLEX
    assert pair.threshold.domain == pair.metric.domain
    assert pair.metric.origin.kind is ReplayNumericOriginKind.NUMPY_COMPLEX
    assert pair.threshold.origin.kind is ReplayNumericOriginKind.PYTHON_FLOAT
    imaginary = pair.threshold.imaginary
    assert imaginary is not None
    assert imaginary.numerator == 0
    assert imaginary.denominator == 1


def test_uncharacterized_native_threshold_fails_closed() -> None:
    with pytest.raises(UnsupportedReplayNumericScalarError):
        project_legacy_post_score_comparison_pair(
            3,
            object(),
            unit=_UNIT,
        )


def test_non_finite_decimal_fails_closed() -> None:
    with pytest.raises(UnsupportedReplayNumericScalarError):
        project_legacy_post_score_comparison_pair(
            3,
            Decimal("NaN"),
            unit=_UNIT,
        )
