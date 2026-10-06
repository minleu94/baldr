from __future__ import annotations

from collections.abc import Callable
from datetime import date

import numpy as np
import pytest

from app_module.recommendation.replay_numeric_projection import (
    ReplayThresholdUnit,
    UnsupportedReplayNumericScalarError,
    project_legacy_comparison_pair,
)
from decision_module.recommendation.replay_prefilter import (
    ReplayComparisonComponent,
    ReplayComparisonDomainKind,
    ReplayMetricStatus,
    ReplayNumericOriginKind,
    ReplayPreflightDisposition,
    ReplayPreflightStage,
    ReplayPrefilterObservations,
    ReplayFastFilterPolicyV1,
    ReplayThreshold,
    ReplayVolumeThresholdV1,
    evaluate_replay_prefilter,
)


_AS_OF = date(2026, 9, 23)


def _outcome(
    metric: object,
    threshold: float,
    *,
    unit: ReplayThresholdUnit,
    maximum: bool = False,
) -> tuple[bool, ReplayPreflightDisposition, ReplayPreflightStage]:
    pair = project_legacy_comparison_pair(metric, threshold, unit=unit)
    if unit is ReplayThresholdUnit.PRICE_CHANGE_PERCENT:
        observations = ReplayPrefilterObservations(
            stock_code="PROJECTION",
            as_of_date=_AS_OF,
            history_rows=21,
            maximum_row_date=_AS_OF,
            availability_column_present=False,
            maximum_available_date=None,
            price_change_status=ReplayMetricStatus.AVAILABLE,
            price_change_percent=pair.metric,
            volume_change_status=ReplayMetricStatus.MISSING_COLUMN,
        )
        policy = ReplayFastFilterPolicyV1(
            price_change_max=(
                ReplayThreshold.enabled(pair.threshold)
                if maximum
                else ReplayThreshold.disabled()
            ),
            price_change_min=(
                ReplayThreshold.disabled()
                if maximum
                else ReplayThreshold.enabled(pair.threshold)
            ),
        )
    else:
        observations = ReplayPrefilterObservations(
            stock_code="PROJECTION",
            as_of_date=_AS_OF,
            history_rows=21,
            maximum_row_date=_AS_OF,
            availability_column_present=False,
            maximum_available_date=None,
            price_change_status=ReplayMetricStatus.MISSING_COLUMN,
            volume_change_status=ReplayMetricStatus.AVAILABLE,
            volume_change_percent=pair.metric,
        )
        policy = ReplayFastFilterPolicyV1(
            volume_minimum=ReplayVolumeThresholdV1.effective_change_percent(
                ReplayThreshold.enabled(pair.threshold)
            )
        )

    outcome = evaluate_replay_prefilter(policy, observations)
    return (
        outcome.disposition is ReplayPreflightDisposition.REJECT,
        outcome.disposition,
        outcome.stage,
    )


@pytest.mark.parametrize(
    ("metric", "threshold", "unit", "maximum"),
    [
        (np.float16(1.0), 1.0001, ReplayThresholdUnit.PRICE_CHANGE_PERCENT, False),
        (np.float32(1.0), 1.00000001, ReplayThresholdUnit.PRICE_CHANGE_PERCENT, False),
        (
            np.float64(10.100000000000001),
            10.1,
            ReplayThresholdUnit.PRICE_CHANGE_PERCENT,
            True,
        ),
    ],
)
def test_numpy_float_pair_matches_legacy_scalar_comparison(
    metric: np.generic,
    threshold: float,
    unit: ReplayThresholdUnit,
    maximum: bool,
) -> None:
    pair = project_legacy_comparison_pair(metric, threshold, unit=unit)
    legacy_reject = bool(metric > threshold) if maximum else bool(metric < threshold)
    projected_reject, _, _ = _outcome(
        metric,
        threshold,
        unit=unit,
        maximum=maximum,
    )

    assert projected_reject is legacy_reject
    assert pair.metric.domain == pair.threshold.domain
    assert pair.metric.origin.kind is ReplayNumericOriginKind.NUMPY_FLOAT
    assert pair.threshold.origin.kind is ReplayNumericOriginKind.PYTHON_FLOAT
    assert pair.metric.domain.kind is ReplayComparisonDomainKind.BINARY_REAL


@pytest.mark.parametrize(
    ("dtype", "raw_ratio_threshold"),
    [
        ("float16", 1.09964),
        ("float32", 1.1000000191734864),
        ("float64", 1.1000000191734864),
    ],
)
def test_volume_pair_accepts_only_already_normalized_effective_percent(
    dtype: str,
    raw_ratio_threshold: float,
) -> None:
    # 僅此測試重現 provider 原 normalization；projector 收到的是最後的有效百分比。
    effective_threshold = (raw_ratio_threshold - 1) * 100
    metric = np.dtype(dtype).type(10.0)
    pair = project_legacy_comparison_pair(
        metric,
        effective_threshold,
        unit=ReplayThresholdUnit.VOLUME_EFFECTIVE_CHANGE_PERCENT,
    )
    legacy_reject = bool(metric < effective_threshold)
    projected_reject, _, _ = _outcome(
        metric,
        effective_threshold,
        unit=ReplayThresholdUnit.VOLUME_EFFECTIVE_CHANGE_PERCENT,
    )

    assert pair.unit is ReplayThresholdUnit.VOLUME_EFFECTIVE_CHANGE_PERCENT
    assert projected_reject is legacy_reject
    assert pair.metric.domain == pair.threshold.domain


def test_volume_effective_threshold_is_not_normalized_a_second_time() -> None:
    metric = np.float64(2.0)
    effective_threshold = 1.25
    pair = project_legacy_comparison_pair(
        metric,
        effective_threshold,
        unit=ReplayThresholdUnit.VOLUME_EFFECTIVE_CHANGE_PERCENT,
    )
    legacy_reject = bool(metric < effective_threshold)
    projected_reject, _, _ = _outcome(
        metric,
        effective_threshold,
        unit=ReplayThresholdUnit.VOLUME_EFFECTIVE_CHANGE_PERCENT,
    )

    assert pair.threshold.real == ReplayComparisonComponent.finite(
        *np.float64(effective_threshold).as_integer_ratio()
    )
    assert legacy_reject is False
    assert projected_reject is legacy_reject


def test_numpy_integer_and_python_float_use_numpy_weak_promotion_domain() -> None:
    metric = np.int64(2**53 + 1)
    threshold = float(2**53)
    pair = project_legacy_comparison_pair(
        metric,
        threshold,
        unit=ReplayThresholdUnit.PRICE_CHANGE_PERCENT,
    )
    legacy_reject = bool(metric > threshold)
    projected_reject, disposition, _ = _outcome(
        metric,
        threshold,
        unit=ReplayThresholdUnit.PRICE_CHANGE_PERCENT,
        maximum=True,
    )

    assert pair.metric.origin.kind is ReplayNumericOriginKind.NUMPY_INTEGER
    assert pair.metric.domain == pair.threshold.domain
    assert pair.metric.real == pair.threshold.real
    assert legacy_reject is False
    assert projected_reject is legacy_reject
    assert disposition is ReplayPreflightDisposition.READY


@pytest.mark.parametrize("maximum", [False, True])
def test_numpy_complex_imaginary_nan_keeps_legacy_unordered_result(
    maximum: bool,
) -> None:
    metric = np.complex64(complex(1.0, float("nan")))
    threshold = 1.0
    legacy_reject = bool(metric > threshold) if maximum else bool(metric < threshold)
    pair = project_legacy_comparison_pair(
        metric,
        threshold,
        unit=ReplayThresholdUnit.PRICE_CHANGE_PERCENT,
    )
    projected_reject, disposition, stage = _outcome(
        metric,
        threshold,
        unit=ReplayThresholdUnit.PRICE_CHANGE_PERCENT,
        maximum=maximum,
    )

    assert pair.metric.domain.kind is ReplayComparisonDomainKind.NUMPY_COMPLEX
    assert pair.metric.imaginary == ReplayComparisonComponent.unordered()
    assert projected_reject is legacy_reject is False
    assert disposition is ReplayPreflightDisposition.READY
    assert stage is ReplayPreflightStage.READY


def test_numpy_complex_finite_components_keep_lexicographic_order() -> None:
    metric = np.complex64(complex(1.0, 1.0))
    threshold = 1.0
    pair = project_legacy_comparison_pair(
        metric,
        threshold,
        unit=ReplayThresholdUnit.PRICE_CHANGE_PERCENT,
    )

    assert bool(metric > threshold) is True
    assert _outcome(
        metric,
        threshold,
        unit=ReplayThresholdUnit.PRICE_CHANGE_PERCENT,
        maximum=True,
    )[0] is True
    assert pair.threshold.imaginary == ReplayComparisonComponent.finite(0)


def test_python_builtin_complex_is_deferred_to_evaluator_type_error() -> None:
    pair = project_legacy_comparison_pair(
        complex(1.0, 0.0),
        1.0,
        unit=ReplayThresholdUnit.PRICE_CHANGE_PERCENT,
    )

    assert pair.metric.domain.kind is ReplayComparisonDomainKind.PYTHON_COMPLEX
    assert pair.metric.domain == pair.threshold.domain
    with pytest.raises(
        TypeError,
        match=r"'<' not supported between instances of 'complex' and 'float'",
    ):
        _outcome(
            complex(1.0, 0.0),
            1.0,
            unit=ReplayThresholdUnit.PRICE_CHANGE_PERCENT,
        )


def test_float16_threshold_overflow_preserves_numpy_seterr_behavior() -> None:
    metric = np.float16(1.0)
    threshold = 1e100

    def terminal(operation: Callable[[], object]) -> tuple[object, ...]:
        """保留原生比較或新投影的布林／例外 terminal，不折成相同假值。"""
        try:
            result = operation()
        except Exception as exc:
            return (
                "exception",
                type(exc).__module__,
                type(exc).__qualname__,
                str(exc),
                tuple(repr(argument) for argument in exc.args),
            )
        if type(result) is bool:
            return ("bool", result)
        return (
            "non_bool_return",
            type(result).__module__,
            type(result).__qualname__,
            repr(result),
        )

    for overflow_mode in ("ignore", "raise"):
        with np.errstate(over=overflow_mode):
            native_terminal = terminal(lambda: bool(metric < threshold))
        with np.errstate(over=overflow_mode):
            staged_terminal = terminal(
                lambda: _outcome(
                    metric,
                    threshold,
                    unit=ReplayThresholdUnit.PRICE_CHANGE_PERCENT,
                )[0]
            )

        # 由同一 NumPy runtime 的舊原生比較決定是否拋錯；NumPy 2 的
        # overflow 例外仍必須在 staged 路徑出現，NumPy 1 若回傳 bool 也要保留。
        assert staged_terminal == native_terminal, (
            f"over={overflow_mode}: native={native_terminal!r}, "
            f"staged={staged_terminal!r}"
        )


def test_longdouble_uses_runtime_precision_without_python_float_roundtrip() -> None:
    dtype = np.dtype(np.longdouble)
    metric = np.nextafter(dtype.type(1), dtype.type(2))
    threshold = 1.0
    pair = project_legacy_comparison_pair(
        metric,
        threshold,
        unit=ReplayThresholdUnit.PRICE_CHANGE_PERCENT,
    )
    finfo = np.finfo(dtype)

    assert pair.metric.domain.format_name == np.result_type(metric, threshold).name
    assert pair.metric.domain.precision_bits == int(finfo.nmant) + 1
    assert pair.metric.domain.min_exponent == int(finfo.minexp)
    assert pair.metric.domain.max_exponent == int(finfo.maxexp)
    if finfo.nmant > np.finfo(np.float64).nmant:
        assert float(metric) == threshold
        assert bool(metric > threshold) is True
        assert _outcome(
            metric,
            threshold,
            unit=ReplayThresholdUnit.PRICE_CHANGE_PERCENT,
            maximum=True,
        )[0] is True


def test_python_builtin_integer_and_float_keep_exact_rational_values() -> None:
    metric = 10**100 + 1
    threshold = float(10**100)
    pair = project_legacy_comparison_pair(
        metric,
        threshold,
        unit=ReplayThresholdUnit.PRICE_CHANGE_PERCENT,
    )

    assert pair.metric.domain.kind is ReplayComparisonDomainKind.EXACT_RATIONAL
    assert pair.metric.real == ReplayComparisonComponent.finite(metric)
    assert pair.metric.origin.kind is ReplayNumericOriginKind.PYTHON_INT


@pytest.mark.parametrize("metric", [object(), np.asarray([1.0]), np.bool_(True), True])
def test_unsupported_scalar_is_an_explicit_exception(metric: object) -> None:
    with pytest.raises(UnsupportedReplayNumericScalarError):
        project_legacy_comparison_pair(
            metric,
            1.0,
            unit=ReplayThresholdUnit.PRICE_CHANGE_PERCENT,
        )


def test_effective_threshold_must_be_python_float_and_unit_is_required() -> None:
    with pytest.raises(TypeError, match="呼叫者已轉換的 Python float"):
        project_legacy_comparison_pair(
            np.float32(1.0),
            np.float64(1.0),
            unit=ReplayThresholdUnit.PRICE_CHANGE_PERCENT,
        )
