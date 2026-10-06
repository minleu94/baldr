from datetime import date
from decimal import Decimal

import pytest

from decision_module.recommendation.replay_prefilter import (
    REPLAY_FAST_FILTER_POLICY_VERSION,
    REPLAY_VOLUME_THRESHOLD_VERSION,
    ReplayComparisonComponent,
    ReplayComparisonDomain,
    ReplayComparisonDomainMismatchError,
    ReplayComparisonOperand,
    ReplayComparisonValue,
    ReplayFastFilterPolicyV1,
    ReplayMetricStatus,
    ReplayNumericOrigin,
    ReplayNumericOriginKind,
    ReplayPrefilterObservations,
    ReplayPreflightDisposition,
    ReplayPreflightStage,
    ReplayThreshold,
    ReplayVolumeThresholdKind,
    ReplayVolumeThresholdV1,
    evaluate_replay_prefilter,
)


AS_OF = date(2026, 9, 1)


def _observations(
    *,
    stock_code: str = "2330",
    history_rows: int = 20,
    price_status: ReplayMetricStatus | None = None,
    price_change: Decimal | int | ReplayComparisonValue | ReplayComparisonOperand | None = None,
    volume_status: ReplayMetricStatus | None = None,
    volume_change: Decimal | int | ReplayComparisonValue | ReplayComparisonOperand | None = None,
    maximum_row_date: date | None = AS_OF,
    availability_column_present: bool = True,
    maximum_available_date: date | None = AS_OF,
) -> ReplayPrefilterObservations:
    if price_status is None:
        price_status = (
            ReplayMetricStatus.AVAILABLE
            if history_rows >= 2
            else ReplayMetricStatus.INSUFFICIENT_WINDOW
        )
    if price_change is None and price_status is ReplayMetricStatus.AVAILABLE:
        price_change = Decimal("0")
    if volume_status is None:
        volume_status = (
            ReplayMetricStatus.AVAILABLE
            if history_rows >= 21
            else ReplayMetricStatus.INSUFFICIENT_WINDOW
        )
    if volume_change is None and volume_status is ReplayMetricStatus.AVAILABLE:
        volume_change = Decimal("0")
    if history_rows == 0:
        maximum_row_date = None
        maximum_available_date = None
    return ReplayPrefilterObservations(
        stock_code=stock_code,
        as_of_date=AS_OF,
        history_rows=history_rows,
        maximum_row_date=maximum_row_date,
        availability_column_present=availability_column_present,
        maximum_available_date=maximum_available_date,
        price_change_status=price_status,
        price_change_percent=price_change,
        volume_change_status=volume_status,
        volume_change_percent=volume_change,
    )


def test_history_19_rejects_before_filters_and_20_advances_to_price_minimum():
    policy = ReplayFastFilterPolicyV1(
        price_change_min=ReplayThreshold.enabled(Decimal("2")),
        volume_ratio_min=ReplayThreshold.enabled(Decimal("100")),
    )

    short = evaluate_replay_prefilter(
        policy,
        _observations(history_rows=19, price_change=Decimal("0")),
    )
    exact_minimum = evaluate_replay_prefilter(
        policy,
        _observations(history_rows=20, price_change=Decimal("0")),
    )

    assert short.policy_version == REPLAY_FAST_FILTER_POLICY_VERSION
    assert short.disposition is ReplayPreflightDisposition.REJECT
    assert short.stage is ReplayPreflightStage.MINIMUM_HISTORY
    assert short.reason_code == "insufficient_history"
    assert short.observed_value == Decimal("19")
    assert exact_minimum.disposition is ReplayPreflightDisposition.REJECT
    assert exact_minimum.stage is ReplayPreflightStage.PRICE_CHANGE_MIN
    assert exact_minimum.reason_code == "price_change_below_min"


def test_price_minimum_and_maximum_are_inclusive_and_keep_order_before_volume():
    policy = ReplayFastFilterPolicyV1(
        price_change_min=ReplayThreshold.enabled(Decimal("1")),
        price_change_max=ReplayThreshold.enabled(Decimal("10")),
        volume_ratio_min=ReplayThreshold.enabled(Decimal("5")),
    )

    at_minimum = evaluate_replay_prefilter(
        policy,
        _observations(
            history_rows=21,
            price_change=Decimal("1"),
            volume_change=Decimal("400"),
        ),
    )
    at_maximum = evaluate_replay_prefilter(
        policy,
        _observations(
            history_rows=21,
            price_change=Decimal("10"),
            volume_change=Decimal("400"),
        ),
    )
    below_minimum = evaluate_replay_prefilter(
        policy,
        _observations(
            history_rows=21,
            price_change=Decimal("0"),
            volume_change=Decimal("400"),
        ),
    )
    above_maximum = evaluate_replay_prefilter(
        policy,
        _observations(
            history_rows=21,
            price_change=Decimal("10.01"),
            volume_change=Decimal("400"),
        ),
    )

    assert at_minimum.disposition is ReplayPreflightDisposition.READY
    assert at_maximum.disposition is ReplayPreflightDisposition.READY
    assert below_minimum.stage is ReplayPreflightStage.PRICE_CHANGE_MIN
    assert below_minimum.reason_code == "price_change_below_min"
    assert above_maximum.stage is ReplayPreflightStage.PRICE_CHANGE_MAX
    assert above_maximum.reason_code == "price_change_above_max"


def test_volume_ratio_uses_legacy_normalization_and_needs_21_total_rows():
    policy = ReplayFastFilterPolicyV1(
        volume_ratio_min=ReplayThreshold.enabled(Decimal("1.5")),
    )

    twenty_rows = evaluate_replay_prefilter(
        policy,
        _observations(
            history_rows=20,
            volume_status=ReplayMetricStatus.INSUFFICIENT_WINDOW,
            volume_change=None,
        ),
    )
    at_normalized_threshold = evaluate_replay_prefilter(
        policy,
        _observations(history_rows=21, volume_change=Decimal("50")),
    )
    below_normalized_threshold = evaluate_replay_prefilter(
        policy,
        _observations(history_rows=21, volume_change=Decimal("49.99")),
    )

    assert policy.normalized_volume_change_min_percent == Decimal("50.0")
    assert twenty_rows.disposition is ReplayPreflightDisposition.READY
    assert at_normalized_threshold.disposition is ReplayPreflightDisposition.READY
    assert below_normalized_threshold.stage is ReplayPreflightStage.VOLUME_RATIO_MIN
    assert below_normalized_threshold.required_value == Decimal("50.0")


def test_volume_ratio_legacy_normalization_keeps_inclusive_conversion_band():
    assert ReplayFastFilterPolicyV1(
        volume_ratio_min=ReplayThreshold.enabled(Decimal("-50")),
    ).normalized_volume_change_min_percent == Decimal("-5100")
    assert ReplayFastFilterPolicyV1(
        volume_ratio_min=ReplayThreshold.enabled(Decimal("10")),
    ).normalized_volume_change_min_percent == Decimal("900")
    assert ReplayFastFilterPolicyV1(
        volume_ratio_min=ReplayThreshold.enabled(Decimal("10.01")),
    ).normalized_volume_change_min_percent == Decimal("10.01")


def test_zero_denominator_is_explicit_zero_and_still_compared_to_active_threshold():
    observations = _observations(
        history_rows=21,
        price_status=ReplayMetricStatus.ZERO_DENOMINATOR,
        price_change=Decimal("0"),
        volume_status=ReplayMetricStatus.ZERO_DENOMINATOR,
        volume_change=Decimal("0"),
    )
    policy = ReplayFastFilterPolicyV1(
        price_change_min=ReplayThreshold.enabled(Decimal("1")),
        volume_ratio_min=ReplayThreshold.enabled(Decimal("1.5")),
    )

    outcome = evaluate_replay_prefilter(policy, observations)
    volume_outcome = evaluate_replay_prefilter(
        ReplayFastFilterPolicyV1(
            volume_ratio_min=ReplayThreshold.enabled(Decimal("1.5")),
        ),
        observations,
    )

    assert outcome.disposition is ReplayPreflightDisposition.REJECT
    assert outcome.stage is ReplayPreflightStage.PRICE_CHANGE_MIN
    assert outcome.observed_value == Decimal("0")
    assert volume_outcome.disposition is ReplayPreflightDisposition.REJECT
    assert volume_outcome.stage is ReplayPreflightStage.VOLUME_RATIO_MIN
    assert volume_outcome.observed_value == Decimal("0")


def test_rejected_prefilter_outcome_is_not_marked_scoreable():
    outcome = evaluate_replay_prefilter(
        ReplayFastFilterPolicyV1(
            price_change_min=ReplayThreshold.enabled(Decimal("2")),
        ),
        _observations(price_change=Decimal("0")),
    )

    assert outcome.disposition is ReplayPreflightDisposition.REJECT
    assert outcome.may_score is False


def test_missing_columns_short_windows_and_disabled_thresholds_keep_no_filter_path():
    missing_and_short = _observations(
        history_rows=20,
        price_status=ReplayMetricStatus.MISSING_COLUMN,
        price_change=None,
        volume_status=ReplayMetricStatus.INSUFFICIENT_WINDOW,
        volume_change=None,
    )
    disabled = ReplayFastFilterPolicyV1()
    unsupported_but_disabled = _observations(
        history_rows=20,
        price_status=ReplayMetricStatus.UNSUPPORTED,
        price_change=None,
        volume_status=ReplayMetricStatus.UNSUPPORTED,
        volume_change=None,
    )

    assert evaluate_replay_prefilter(disabled, missing_and_short).may_score
    assert evaluate_replay_prefilter(disabled, unsupported_but_disabled).may_score


def test_active_filter_returns_unsupported_instead_of_guessing_on_unordered_input():
    outcome = evaluate_replay_prefilter(
        ReplayFastFilterPolicyV1(
            price_change_min=ReplayThreshold.enabled(Decimal("0")),
        ),
        _observations(
            price_status=ReplayMetricStatus.UNSUPPORTED,
            price_change=None,
        ),
    )

    assert outcome.disposition is ReplayPreflightDisposition.UNSUPPORTED
    assert outcome.stage is ReplayPreflightStage.PRICE_CHANGE_MIN
    assert outcome.reason_code == "unsupported_price_change_below_min_observation"


def test_unsupported_config_threshold_is_only_relevant_when_legacy_filter_would_run():
    policy = ReplayFastFilterPolicyV1(
        price_change_min=ReplayThreshold.unsupported("legacy_config_coercion_error"),
    )
    available = evaluate_replay_prefilter(
        policy,
        _observations(price_change=Decimal("1")),
    )
    missing_column = evaluate_replay_prefilter(
        policy,
        _observations(
            price_status=ReplayMetricStatus.MISSING_COLUMN,
            price_change=None,
        ),
    )

    assert available.disposition is ReplayPreflightDisposition.UNSUPPORTED
    assert available.reason_code == (
        "unsupported_price_change_below_min_threshold:legacy_config_coercion_error"
    )
    assert missing_column.disposition is ReplayPreflightDisposition.READY


def test_invalid_policy_or_observations_fail_closed():
    with pytest.raises(ValueError, match="policy version"):
        ReplayFastFilterPolicyV1(version="replay-fast-filter.v2")
    with pytest.raises(TypeError, match="threshold status"):
        ReplayThreshold(status="enabled", value=Decimal("1"))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="enabled threshold"):
        ReplayThreshold(status=ReplayThreshold.enabled(1).status)
    with pytest.raises(ValueError, match="有限 Decimal"):
        _observations(price_change=Decimal("NaN"))
    with pytest.raises(ValueError, match="zero_denominator metric 必須是 0"):
        _observations(
            price_status=ReplayMetricStatus.ZERO_DENOMINATOR,
            price_change=Decimal("1"),
        )
    with pytest.raises(ValueError, match="缺值／unsupported 狀態不可帶數值"):
        _observations(
            price_status=ReplayMetricStatus.MISSING_COLUMN,
            price_change=Decimal("0"),
        )
    with pytest.raises(ValueError, match="狀態與 history_rows 不相容"):
        _observations(
            history_rows=20,
            volume_status=ReplayMetricStatus.AVAILABLE,
            volume_change=Decimal("0"),
        )
    with pytest.raises(ValueError, match="maximum_row_date 超過 replay cutoff"):
        _observations(maximum_row_date=date(2026, 9, 2))
    with pytest.raises(ValueError, match="maximum_available_date 超過 replay cutoff"):
        _observations(maximum_available_date=date(2026, 9, 2))
    with pytest.raises(TypeError, match="僅接受 Decimal 或 int"):
        _observations(price_change=0.5)  # type: ignore[arg-type]


def test_effective_volume_threshold_is_versioned_mutually_exclusive_and_not_renormalized():
    raw_policy = ReplayFastFilterPolicyV1(
        volume_ratio_min=ReplayThreshold.enabled(Decimal("1.1")),
    )
    versioned_raw_policy = ReplayFastFilterPolicyV1(
        volume_minimum=ReplayVolumeThresholdV1.raw_ratio(
            ReplayThreshold.enabled(Decimal("1.1"))
        ),
    )
    legacy_float_effective_percent = Decimal.from_float(10.000000000000009)
    effective_percent = Decimal.from_float(10.000000000000009)
    effective_policy = ReplayFastFilterPolicyV1(
        volume_minimum=ReplayVolumeThresholdV1.effective_change_percent(
            ReplayThreshold.enabled(effective_percent)
        ),
    )
    effective_result = evaluate_replay_prefilter(
        effective_policy,
        _observations(
            history_rows=21,
            volume_change=effective_percent,
        ),
    )

    assert raw_policy.normalized_volume_change_min_percent == Decimal("10.0")
    assert versioned_raw_policy.normalized_volume_change_min_percent == Decimal("10.0")
    assert legacy_float_effective_percent != Decimal("10.0")
    assert effective_policy.volume_minimum is not None
    assert effective_policy.volume_minimum.version == REPLAY_VOLUME_THRESHOLD_VERSION
    assert effective_policy.volume_minimum.kind is ReplayVolumeThresholdKind.EFFECTIVE_CHANGE_PERCENT
    assert effective_policy.normalized_volume_change_min_percent == effective_percent
    assert effective_result.disposition is ReplayPreflightDisposition.READY
    assert effective_result.stage is ReplayPreflightStage.READY

    normalization_sensitive_percent = Decimal("5.0")
    normalization_sensitive_policy = ReplayFastFilterPolicyV1(
        volume_minimum=ReplayVolumeThresholdV1.effective_change_percent(
            ReplayThreshold.enabled(normalization_sensitive_percent)
        ),
    )
    exact_effective_boundary = evaluate_replay_prefilter(
        normalization_sensitive_policy,
        _observations(history_rows=21, volume_change=normalization_sensitive_percent),
    )
    below_effective_boundary = evaluate_replay_prefilter(
        normalization_sensitive_policy,
        _observations(history_rows=21, volume_change=Decimal("4.9")),
    )
    assert (
        normalization_sensitive_policy.normalized_volume_change_min_percent
        == normalization_sensitive_percent
    )
    assert exact_effective_boundary.disposition is ReplayPreflightDisposition.READY
    assert below_effective_boundary.disposition is ReplayPreflightDisposition.REJECT
    assert below_effective_boundary.required_value == normalization_sensitive_percent

    raw_unordered_policy = ReplayFastFilterPolicyV1(
        volume_minimum=ReplayVolumeThresholdV1.raw_ratio(
            ReplayThreshold.unordered()
        ),
    )
    raw_positive_infinity_policy = ReplayFastFilterPolicyV1(
        volume_minimum=ReplayVolumeThresholdV1.raw_ratio(
            ReplayThreshold.positive_infinity()
        ),
    )
    assert evaluate_replay_prefilter(
        raw_unordered_policy,
        _observations(history_rows=21, volume_change=Decimal("0")),
    ).disposition is ReplayPreflightDisposition.READY
    assert evaluate_replay_prefilter(
        raw_positive_infinity_policy,
        _observations(history_rows=21, volume_change=Decimal("0")),
    ).disposition is ReplayPreflightDisposition.REJECT

    with pytest.raises(ValueError, match="不可同時設定"):
        ReplayFastFilterPolicyV1(
            volume_ratio_min=ReplayThreshold.enabled(Decimal("1.1")),
            volume_minimum=ReplayVolumeThresholdV1.effective_change_percent(
                ReplayThreshold.enabled(effective_percent)
            ),
        )
    with pytest.raises(ValueError, match="volume threshold version"):
        ReplayVolumeThresholdV1(
            ReplayVolumeThresholdKind.EFFECTIVE_CHANGE_PERCENT,
            ReplayThreshold.enabled(Decimal("10")),
            version="replay-volume-threshold.v2",
        )


def test_unordered_metric_and_threshold_keep_legacy_nan_comparison_as_pass():
    unordered_metric = evaluate_replay_prefilter(
        ReplayFastFilterPolicyV1(
            price_change_min=ReplayThreshold.enabled(Decimal("0")),
            price_change_max=ReplayThreshold.enabled(Decimal("10")),
        ),
        _observations(
            price_change=ReplayComparisonValue.unordered(),
        ),
    )
    unordered_threshold = evaluate_replay_prefilter(
        ReplayFastFilterPolicyV1(
            price_change_min=ReplayThreshold.unordered(),
        ),
        _observations(price_change=Decimal("5")),
    )

    assert unordered_metric.disposition is ReplayPreflightDisposition.READY
    assert unordered_threshold.disposition is ReplayPreflightDisposition.READY


def test_infinite_metric_and_thresholds_keep_legacy_ordered_comparisons():
    positive_metric_above_max = evaluate_replay_prefilter(
        ReplayFastFilterPolicyV1(
            price_change_max=ReplayThreshold.enabled(Decimal("100")),
        ),
        _observations(
            price_change=ReplayComparisonValue.positive_infinity(),
        ),
    )
    negative_metric_below_min = evaluate_replay_prefilter(
        ReplayFastFilterPolicyV1(
            price_change_min=ReplayThreshold.enabled(Decimal("-100")),
        ),
        _observations(
            price_change=ReplayComparisonValue.negative_infinity(),
        ),
    )
    finite_below_positive_infinite_min = evaluate_replay_prefilter(
        ReplayFastFilterPolicyV1(
            price_change_min=ReplayThreshold.positive_infinity(),
        ),
        _observations(price_change=Decimal("0")),
    )
    finite_above_negative_infinite_max = evaluate_replay_prefilter(
        ReplayFastFilterPolicyV1(
            price_change_max=ReplayThreshold.negative_infinity(),
        ),
        _observations(price_change=Decimal("0")),
    )
    equal_positive_infinity_max = evaluate_replay_prefilter(
        ReplayFastFilterPolicyV1(
            price_change_max=ReplayThreshold.positive_infinity(),
        ),
        _observations(
            price_change=ReplayComparisonValue.positive_infinity(),
        ),
    )

    assert positive_metric_above_max.disposition is ReplayPreflightDisposition.REJECT
    assert positive_metric_above_max.observed_value == ReplayComparisonValue.positive_infinity()
    assert positive_metric_above_max.required_value == Decimal("100")
    assert negative_metric_below_min.disposition is ReplayPreflightDisposition.REJECT
    assert negative_metric_below_min.observed_value == ReplayComparisonValue.negative_infinity()
    assert finite_below_positive_infinite_min.disposition is ReplayPreflightDisposition.REJECT
    assert finite_below_positive_infinite_min.required_value == ReplayComparisonValue.positive_infinity()
    assert finite_above_negative_infinite_max.disposition is ReplayPreflightDisposition.REJECT
    assert finite_above_negative_infinite_max.required_value == ReplayComparisonValue.negative_infinity()
    assert equal_positive_infinity_max.disposition is ReplayPreflightDisposition.READY


def test_float_ulp_values_keep_exact_legacy_comparison_side_of_endpoint():
    metric = Decimal.from_float(10.100000000000001)
    threshold = Decimal.from_float(10.1)
    outcome = evaluate_replay_prefilter(
        ReplayFastFilterPolicyV1(
            price_change_max=ReplayThreshold.enabled(threshold),
        ),
        _observations(price_change=metric),
    )

    assert metric > threshold
    assert outcome.disposition is ReplayPreflightDisposition.REJECT
    assert outcome.stage is ReplayPreflightStage.PRICE_CHANGE_MAX
    assert outcome.observed_value == metric
    assert outcome.required_value == threshold


def test_filter_disposition_short_circuits_later_unsupported_threshold_stages():
    minimum_rejects_before_maximum_and_volume = evaluate_replay_prefilter(
        ReplayFastFilterPolicyV1(
            price_change_min=ReplayThreshold.enabled(Decimal("100")),
            price_change_max=ReplayThreshold.unsupported("must_not_be_reached"),
            volume_minimum=ReplayVolumeThresholdV1.effective_change_percent(
                ReplayThreshold.unsupported("must_not_be_reached")
            ),
        ),
        _observations(
            history_rows=21,
            price_change=Decimal("10"),
            volume_change=Decimal("0"),
        ),
    )
    maximum_rejects_before_volume = evaluate_replay_prefilter(
        ReplayFastFilterPolicyV1(
            price_change_max=ReplayThreshold.enabled(Decimal("5")),
            volume_minimum=ReplayVolumeThresholdV1.effective_change_percent(
                ReplayThreshold.unsupported("must_not_be_reached")
            ),
        ),
        _observations(
            history_rows=21,
            price_change=Decimal("6"),
            volume_change=Decimal("0"),
        ),
    )

    assert minimum_rejects_before_maximum_and_volume.stage is ReplayPreflightStage.PRICE_CHANGE_MIN
    assert minimum_rejects_before_maximum_and_volume.reason_code == "price_change_below_min"
    assert maximum_rejects_before_volume.stage is ReplayPreflightStage.PRICE_CHANGE_MAX
    assert maximum_rejects_before_volume.reason_code == "price_change_above_max"


def _binary_real_domain(
    format_name: str,
    *,
    precision_bits: int,
    min_exponent: int,
    max_exponent: int,
) -> ReplayComparisonDomain:
    return ReplayComparisonDomain.binary_real(
        format_name,
        precision_bits=precision_bits,
        min_exponent=min_exponent,
        max_exponent=max_exponent,
    )


def _typed_real(
    origin_kind: ReplayNumericOriginKind,
    domain: ReplayComparisonDomain,
    numerator: int,
    denominator: int = 1,
    *,
    dtype_name: str | None = None,
) -> ReplayComparisonOperand:
    return ReplayComparisonOperand(
        origin=ReplayNumericOrigin(origin_kind, dtype_name),
        domain=domain,
        real=ReplayComparisonComponent.finite(numerator, denominator),
    )


def test_float16_float32_effective_operands_compare_in_their_bound_domain():
    cases = (
        ("float16", 11, -14, 16),
        ("float32", 24, -126, 128),
    )
    for format_name, precision_bits, min_exponent, max_exponent in cases:
        domain = _binary_real_domain(
            format_name,
            precision_bits=precision_bits,
            min_exponent=min_exponent,
            max_exponent=max_exponent,
        )
        metric = _typed_real(
            ReplayNumericOriginKind.NUMPY_FLOAT,
            domain,
            1,
            dtype_name=format_name,
        )
        # Legacy weak scalar coercion rounds each selected threshold to 1.0
        # in its metric domain before this pure comparator receives it.
        effective_threshold = _typed_real(
            ReplayNumericOriginKind.PYTHON_FLOAT,
            domain,
            1,
        )
        outcome = evaluate_replay_prefilter(
            ReplayFastFilterPolicyV1(
                price_change_min=ReplayThreshold.enabled(effective_threshold),
            ),
            _observations(price_change=metric),
        )

        assert outcome.disposition is ReplayPreflightDisposition.READY


@pytest.mark.parametrize(
    ("format_name", "precision_bits", "min_exponent", "max_exponent"),
    [
        ("float16", 11, -14, 16),
        ("float32", 24, -126, 128),
    ],
)
def test_volume_effective_percent_is_not_normalized_again_in_metric_domain(
    format_name: str,
    precision_bits: int,
    min_exponent: int,
    max_exponent: int,
):
    domain = _binary_real_domain(
        format_name,
        precision_bits=precision_bits,
        min_exponent=min_exponent,
        max_exponent=max_exponent,
    )
    metric = _typed_real(
        ReplayNumericOriginKind.NUMPY_FLOAT,
        domain,
        10,
        dtype_name=format_name,
    )
    effective_threshold = _typed_real(
        ReplayNumericOriginKind.PYTHON_FLOAT,
        domain,
        10,
    )
    policy = ReplayFastFilterPolicyV1(
        volume_minimum=ReplayVolumeThresholdV1.effective_change_percent(
            ReplayThreshold.enabled(effective_threshold)
        ),
    )

    outcome = evaluate_replay_prefilter(
        policy,
        _observations(history_rows=21, volume_change=metric),
    )

    assert policy.normalized_volume_change_min_percent == effective_threshold
    assert outcome.disposition is ReplayPreflightDisposition.READY


@pytest.mark.parametrize(
    ("format_name", "precision_bits", "min_exponent", "max_exponent"),
    [
        ("float16", 11, -14, 16),
        ("float32", 24, -126, 128),
    ],
)
def test_metric_and_effective_positive_infinity_max_are_equal(
    format_name: str,
    precision_bits: int,
    min_exponent: int,
    max_exponent: int,
):
    domain = _binary_real_domain(
        format_name,
        precision_bits=precision_bits,
        min_exponent=min_exponent,
        max_exponent=max_exponent,
    )
    metric = ReplayComparisonOperand(
        origin=ReplayNumericOrigin(
            ReplayNumericOriginKind.NUMPY_FLOAT,
            format_name,
        ),
        domain=domain,
        real=ReplayComparisonComponent.positive_infinity(),
    )
    effective_threshold = ReplayComparisonOperand(
        origin=ReplayNumericOrigin(ReplayNumericOriginKind.PYTHON_FLOAT),
        domain=domain,
        real=ReplayComparisonComponent.positive_infinity(),
    )

    outcome = evaluate_replay_prefilter(
        ReplayFastFilterPolicyV1(
            price_change_max=ReplayThreshold.enabled(effective_threshold),
        ),
        _observations(price_change=metric),
    )
    volume_outcome = evaluate_replay_prefilter(
        ReplayFastFilterPolicyV1(
            volume_minimum=ReplayVolumeThresholdV1.effective_change_percent(
                ReplayThreshold.enabled(effective_threshold)
            ),
        ),
        _observations(history_rows=21, volume_change=metric),
    )

    assert outcome.disposition is ReplayPreflightDisposition.READY
    assert volume_outcome.disposition is ReplayPreflightDisposition.READY


def test_numpy_int64_python_float_promotion_uses_effective_float64_value():
    domain = _binary_real_domain(
        "float64",
        precision_bits=53,
        min_exponent=-1022,
        max_exponent=1024,
    )
    # 2**53 + 1 is rounded to 2**53 when NumPy promotes the comparison to
    # float64; the typed operand carries that effective value and its origin.
    promoted_integer_metric = _typed_real(
        ReplayNumericOriginKind.NUMPY_INTEGER,
        domain,
        2**53,
        dtype_name="int64",
    )
    python_float_threshold = _typed_real(
        ReplayNumericOriginKind.PYTHON_FLOAT,
        domain,
        2**53,
    )
    outcome = evaluate_replay_prefilter(
        ReplayFastFilterPolicyV1(
            price_change_max=ReplayThreshold.enabled(python_float_threshold),
        ),
        _observations(price_change=promoted_integer_metric),
    )
    exact_integer_without_legacy_promotion = evaluate_replay_prefilter(
        ReplayFastFilterPolicyV1(
            price_change_max=ReplayThreshold.enabled(
                _typed_real(
                    ReplayNumericOriginKind.PYTHON_INT,
                    ReplayComparisonDomain.exact_rational(),
                    2**53,
                )
            ),
        ),
        _observations(
            price_change=_typed_real(
                ReplayNumericOriginKind.NUMPY_INTEGER,
                ReplayComparisonDomain.exact_rational(),
                2**53 + 1,
                dtype_name="int64",
            ),
        ),
    )

    assert outcome.disposition is ReplayPreflightDisposition.READY
    assert exact_integer_without_legacy_promotion.disposition is ReplayPreflightDisposition.REJECT
    assert promoted_integer_metric.origin.dtype_name == "int64"
    assert promoted_integer_metric.real.numerator == 2**53


def test_numpy_complex_comparison_checks_real_before_nan_imaginary_component():
    domain = ReplayComparisonDomain.numpy_complex(
        "complex128",
        precision_bits=53,
        min_exponent=-1022,
        max_exponent=1024,
    )
    left = ReplayComparisonOperand(
        origin=ReplayNumericOrigin(
            ReplayNumericOriginKind.NUMPY_COMPLEX,
            "complex128",
        ),
        domain=domain,
        real=ReplayComparisonComponent.finite(1),
        imaginary=ReplayComparisonComponent.unordered(),
    )
    right = ReplayComparisonOperand(
        origin=ReplayNumericOrigin(
            ReplayNumericOriginKind.NUMPY_COMPLEX,
            "complex128",
        ),
        domain=domain,
        real=ReplayComparisonComponent.finite(2),
        imaginary=ReplayComparisonComponent.finite(0),
    )
    decisive_real = evaluate_replay_prefilter(
        ReplayFastFilterPolicyV1(price_change_min=ReplayThreshold.enabled(right)),
        _observations(price_change=left),
    )
    equal_real_unordered_imaginary = evaluate_replay_prefilter(
        ReplayFastFilterPolicyV1(price_change_min=ReplayThreshold.enabled(left)),
        _observations(
            price_change=ReplayComparisonOperand(
                origin=right.origin,
                domain=domain,
                real=ReplayComparisonComponent.finite(1),
                imaginary=ReplayComparisonComponent.finite(0),
            ),
        ),
    )

    assert decisive_real.disposition is ReplayPreflightDisposition.REJECT
    assert equal_real_unordered_imaginary.disposition is ReplayPreflightDisposition.READY


def test_numpy_complex_compares_positive_and_negative_infinity_components():
    domain = ReplayComparisonDomain.numpy_complex(
        "complex64",
        precision_bits=24,
        min_exponent=-126,
        max_exponent=128,
    )
    positive_infinite_real = ReplayComparisonOperand(
        origin=ReplayNumericOrigin(
            ReplayNumericOriginKind.NUMPY_COMPLEX,
            "complex64",
        ),
        domain=domain,
        real=ReplayComparisonComponent.positive_infinity(),
        imaginary=ReplayComparisonComponent.unordered(),
    )
    finite_real_threshold = ReplayComparisonOperand(
        origin=positive_infinite_real.origin,
        domain=domain,
        real=ReplayComparisonComponent.finite(10),
        imaginary=ReplayComparisonComponent.positive_infinity(),
    )
    negative_imaginary_metric = ReplayComparisonOperand(
        origin=positive_infinite_real.origin,
        domain=domain,
        real=ReplayComparisonComponent.finite(1),
        imaginary=ReplayComparisonComponent.negative_infinity(),
    )
    positive_imaginary_threshold = ReplayComparisonOperand(
        origin=positive_infinite_real.origin,
        domain=domain,
        real=ReplayComparisonComponent.finite(1),
        imaginary=ReplayComparisonComponent.positive_infinity(),
    )

    real_component_orders_first = evaluate_replay_prefilter(
        ReplayFastFilterPolicyV1(
            price_change_max=ReplayThreshold.enabled(finite_real_threshold),
        ),
        _observations(price_change=positive_infinite_real),
    )
    imaginary_component_orders_after_equal_real = evaluate_replay_prefilter(
        ReplayFastFilterPolicyV1(
            price_change_min=ReplayThreshold.enabled(positive_imaginary_threshold),
        ),
        _observations(price_change=negative_imaginary_metric),
    )

    assert real_component_orders_first.disposition is ReplayPreflightDisposition.REJECT
    assert imaginary_component_orders_after_equal_real.disposition is ReplayPreflightDisposition.REJECT


def test_python_complex_ordering_preserves_operator_and_operand_type_error():
    complex_domain = ReplayComparisonDomain.python_complex()
    complex_metric = ReplayComparisonOperand(
        origin=ReplayNumericOrigin(ReplayNumericOriginKind.PYTHON_COMPLEX),
        domain=complex_domain,
        real=ReplayComparisonComponent.finite(1),
        imaginary=ReplayComparisonComponent.finite(1),
    )
    float_threshold = _typed_real(
        ReplayNumericOriginKind.PYTHON_FLOAT,
        ReplayComparisonDomain.exact_rational(),
        2,
    )

    with pytest.raises(TypeError) as minimum_error:
        evaluate_replay_prefilter(
            ReplayFastFilterPolicyV1(
                price_change_min=ReplayThreshold.enabled(float_threshold),
            ),
            _observations(price_change=complex_metric),
        )
    with pytest.raises(TypeError) as maximum_error:
        evaluate_replay_prefilter(
            ReplayFastFilterPolicyV1(
                price_change_max=ReplayThreshold.enabled(float_threshold),
            ),
            _observations(price_change=complex_metric),
        )
    with pytest.raises(TypeError) as reversed_operands_error:
        evaluate_replay_prefilter(
            ReplayFastFilterPolicyV1(
                price_change_min=ReplayThreshold.enabled(complex_metric),
            ),
            _observations(price_change=float_threshold),
        )

    assert str(minimum_error.value) == (
        "'<' not supported between instances of 'complex' and 'float'"
    )
    assert str(maximum_error.value) == (
        "'>' not supported between instances of 'complex' and 'float'"
    )
    assert str(reversed_operands_error.value) == (
        "'<' not supported between instances of 'float' and 'complex'"
    )


def test_comparison_domain_mismatch_raises_instead_of_becoming_filter_outcome():
    half_domain = _binary_real_domain(
        "float16",
        precision_bits=11,
        min_exponent=-14,
        max_exponent=16,
    )
    single_domain = _binary_real_domain(
        "float32",
        precision_bits=24,
        min_exponent=-126,
        max_exponent=128,
    )
    metric = _typed_real(
        ReplayNumericOriginKind.NUMPY_FLOAT,
        half_domain,
        1,
        dtype_name="float16",
    )
    threshold = _typed_real(
        ReplayNumericOriginKind.PYTHON_FLOAT,
        single_domain,
        1,
    )

    with pytest.raises(ReplayComparisonDomainMismatchError):
        evaluate_replay_prefilter(
            ReplayFastFilterPolicyV1(
                price_change_min=ReplayThreshold.enabled(threshold),
            ),
            _observations(price_change=metric),
        )


def test_wide_rational_comparison_is_exact_without_float_conversion():
    domain = ReplayComparisonDomain.exact_rational()
    metric = _typed_real(
        ReplayNumericOriginKind.PYTHON_INT,
        domain,
        (1 << 4096) + 1,
        1 << 4096,
    )
    threshold = _typed_real(
        ReplayNumericOriginKind.PYTHON_INT,
        domain,
        1,
    )
    outcome = evaluate_replay_prefilter(
        ReplayFastFilterPolicyV1(
            price_change_max=ReplayThreshold.enabled(threshold),
        ),
        _observations(price_change=metric),
    )

    assert outcome.disposition is ReplayPreflightDisposition.REJECT
    assert outcome.observed_value == metric
