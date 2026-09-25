from __future__ import annotations

from dataclasses import FrozenInstanceError
from itertools import product
import math

import pytest

from decision_module.recommendation.replay_policy import (
    ReplayExecutionPolicyV1,
    ReplayRankingSemanticsV1,
    ReplayScoreOrderingKindV1,
    ReplayScoreOrderingV1,
    ReplayScorerFailureSemanticsV1,
    ReplayTopNSlicingSemanticsV1,
)


def test_replay_execution_policy_v1_names_fixed_legacy_modes() -> None:
    policy = ReplayExecutionPolicyV1(top_n=10)

    assert policy.schema_version == 1
    assert policy.lookback_calendar_days == 80
    assert policy.first_seen_max_stocks == 200
    assert policy.minimum_history_rows == 20
    assert (
        policy.ranking_semantics
        is ReplayRankingSemanticsV1.PYTHON_FLOAT_KEY_LIST_SORT_REVERSE_TRUE_STABLE
    )
    assert (
        policy.scorer_failure_semantics
        is ReplayScorerFailureSemanticsV1.SILENT_SKIP_PER_STOCK
    )
    assert (
        policy.top_n_slicing_semantics
        is ReplayTopNSlicingSemanticsV1.PROVIDER_THEN_SNAPSHOT_PYTHON_SLICE
    )


@pytest.mark.parametrize("top_n", [0, -1, -4])
def test_policy_preserves_raw_signed_top_n_and_signed_configured_limits(
    top_n: int,
) -> None:
    policy = ReplayExecutionPolicyV1(
        top_n=top_n,
        lookback_calendar_days=-3,
        first_seen_max_stocks=-2,
    )

    assert policy.top_n == top_n
    assert policy.lookback_calendar_days == -3
    assert policy.first_seen_max_stocks == -2
    # 這只是既有二次 Python slicing 的具名模式，不在 contract 內重做 slicing。
    assert (
        policy.top_n_slicing_semantics
        is ReplayTopNSlicingSemanticsV1.PROVIDER_THEN_SNAPSHOT_PYTHON_SLICE
    )


def test_policy_retains_zero_lookback_and_max_stocks_values() -> None:
    policy = ReplayExecutionPolicyV1(
        top_n=1,
        lookback_calendar_days=0,
        first_seen_max_stocks=0,
    )

    assert policy.lookback_calendar_days == 0
    assert policy.first_seen_max_stocks == 0


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("top_n", True),
        ("top_n", 1.5),
        ("lookback_calendar_days", False),
        ("lookback_calendar_days", "80"),
        ("first_seen_max_stocks", True),
        ("first_seen_max_stocks", 200.0),
    ],
)
def test_policy_requires_app_normalized_exact_integers(
    field_name: str, value: object
) -> None:
    arguments: dict[str, object] = {"top_n": 10}
    arguments[field_name] = value

    with pytest.raises(TypeError, match=field_name):
        ReplayExecutionPolicyV1(**arguments)  # type: ignore[arg-type]


def test_policy_is_frozen() -> None:
    policy = ReplayExecutionPolicyV1(top_n=10)

    with pytest.raises(FrozenInstanceError):
        policy.top_n = -1  # type: ignore[misc]


def _typed_replay_score(value: float) -> ReplayScoreOrderingV1:
    if math.isnan(value):
        return ReplayScoreOrderingV1.nan()
    if math.isinf(value):
        if value < 0:
            return ReplayScoreOrderingV1.negative_infinity()
        return ReplayScoreOrderingV1.positive_infinity()
    numerator, denominator = value.as_integer_ratio()
    return ReplayScoreOrderingV1.finite(numerator, denominator)


def test_replay_score_ordering_matches_native_float_reverse_stable_sort() -> None:
    # 有限值只在測試 oracle 轉為精確比；production contract 不接收 float。
    values = (float("nan"), float("inf"), float("-inf"), -0.0, 0.0, 2.5, -3.0)
    for length in range(6):
        for raw_values in product(values, repeat=length):
            typed_values = tuple(_typed_replay_score(value) for value in raw_values)

            native_order = sorted(
                range(length),
                key=raw_values.__getitem__,
                reverse=True,
            )
            typed_order = sorted(
                range(length),
                key=typed_values.__getitem__,
                reverse=True,
            )

            assert typed_order == native_order, raw_values


def test_replay_score_ordering_preserves_unordered_nan_and_stable_ties() -> None:
    nan = ReplayScoreOrderingV1.nan()
    negative_infinity = ReplayScoreOrderingV1.negative_infinity()
    positive_infinity = ReplayScoreOrderingV1.positive_infinity()
    zero = ReplayScoreOrderingV1.finite(0, 3)
    equal_zero = ReplayScoreOrderingV1.finite(0, 1)
    finite = ReplayScoreOrderingV1.finite(5, 2)

    assert not nan < finite
    assert not finite < nan
    assert not nan < nan
    assert negative_infinity < zero
    assert zero < positive_infinity
    assert not zero < equal_zero

    keys = (nan, finite, positive_infinity, nan, negative_infinity, zero, equal_zero)
    assert sorted(range(len(keys)), key=keys.__getitem__, reverse=True) == [
        0,
        2,
        1,
        3,
        5,
        6,
        4,
    ]


def test_replay_score_ordering_compares_large_finite_ratios_exactly() -> None:
    left = ReplayScoreOrderingV1.finite(2**200 + 1, 2**100)
    right = ReplayScoreOrderingV1.finite(2**100 + 1, 2**0)

    assert left < right
    assert ReplayScoreOrderingV1.finite(6, 9) == ReplayScoreOrderingV1.finite(2, 3)
    assert ReplayScoreOrderingV1.finite(0, 7).numerator == 0
    assert ReplayScoreOrderingV1.finite(0, 7).denominator == 1


@pytest.mark.parametrize(
    ("numerator", "denominator", "exception"),
    [
        (True, 1, TypeError),
        (1.0, 1, TypeError),
        (1, False, TypeError),
        (1, 0, ValueError),
        (1, -1, ValueError),
    ],
)
def test_replay_score_ordering_requires_exact_finite_integer_ratio(
    numerator: object,
    denominator: object,
    exception: type[Exception],
) -> None:
    with pytest.raises(exception):
        ReplayScoreOrderingV1.finite(  # type: ignore[arg-type]
            numerator,
            denominator,
        )


def test_replay_score_ordering_special_tags_reject_finite_payload() -> None:
    with pytest.raises(ValueError, match="不可帶分子或分母"):
        ReplayScoreOrderingV1(
            kind=ReplayScoreOrderingKindV1.UNORDERED_NAN,
            numerator=0,
            denominator=1,
        )
