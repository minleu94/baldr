from __future__ import annotations

import pytest

from app_module.recommendation_portfolio_affordable_order import (
    AffordableOrderCancelledError,
    max_affordable_lot_shares,
)


def test_large_request_uses_bounded_integer_predicate_evaluations() -> None:
    requested_shares = 10**18 + 987
    lot_size = 1000
    max_lots = requested_shares // lot_size
    affordable_limit = 123_456_789_012_000
    seen: list[int] = []

    def is_affordable(shares: int) -> bool:
        seen.append(shares)
        return shares <= affordable_limit

    result = max_affordable_lot_shares(
        requested_shares=requested_shares,
        lot_size=lot_size,
        is_affordable=is_affordable,
    )

    assert result == affordable_limit
    assert result % lot_size == 0
    assert seen
    assert all(type(value) is int and value > 0 for value in seen)
    assert all(value % lot_size == 0 for value in seen)
    assert len(seen) <= max_lots.bit_length() + 2


def test_maximum_affordable_amount_returns_without_search() -> None:
    seen: list[int] = []

    def is_affordable(shares: int) -> bool:
        seen.append(shares)
        return True

    result = max_affordable_lot_shares(
        requested_shares=12_000,
        lot_size=1000,
        is_affordable=is_affordable,
    )

    assert result == 12_000
    assert seen == [12_000]


def test_adjacent_affordable_lot_keeps_original_cost_evaluation_order() -> None:
    seen: list[int] = []

    def is_affordable(shares: int) -> bool:
        seen.append(shares)
        return shares <= 199

    assert max_affordable_lot_shares(
        requested_shares=200, lot_size=1, is_affordable=is_affordable,
    ) == 199
    assert seen == [200, 199]


def test_request_remainder_is_discarded_and_exact_threshold_is_returned() -> None:
    result = max_affordable_lot_shares(
        requested_shares=10_999,
        lot_size=1000,
        is_affordable=lambda shares: shares <= 7000,
    )

    assert result == 7000
    assert result <= requested_shares_floor(10_999, 1000)
    assert result % 1000 == 0


def test_zero_lot_upper_bound_does_not_call_cost_callback() -> None:
    def unexpected_cost_call(_: int) -> bool:
        raise AssertionError("零手上限不得呼叫成本 callback")

    assert max_affordable_lot_shares(
        requested_shares=999,
        lot_size=1000,
        is_affordable=unexpected_cost_call,
    ) == 0


def test_zero_requested_shares_returns_zero_without_cost_callback() -> None:
    def unexpected_cost_call(_: int) -> bool:
        raise AssertionError("零股數不得呼叫成本 callback")

    assert max_affordable_lot_shares(
        requested_shares=0,
        lot_size=1000,
        is_affordable=unexpected_cost_call,
    ) == 0


def test_one_lot_exact_minimum_is_found() -> None:
    seen: list[int] = []

    def is_affordable(shares: int) -> bool:
        seen.append(shares)
        return shares == 1000

    assert max_affordable_lot_shares(
        requested_shares=2000,
        lot_size=1000,
        is_affordable=is_affordable,
    ) == 1000
    assert all(value > 0 for value in seen)


def test_unaffordable_minimum_returns_zero() -> None:
    assert max_affordable_lot_shares(
        requested_shares=5000,
        lot_size=1000,
        is_affordable=lambda _shares: False,
    ) == 0


def test_callback_must_return_an_actual_bool() -> None:
    with pytest.raises(TypeError, match="is_affordable 必須回傳 bool"):
        max_affordable_lot_shares(
            requested_shares=1000,
            lot_size=1000,
            is_affordable=lambda _: 1,  # type: ignore[arg-type]
        )


def test_cost_callback_exception_is_not_hidden() -> None:
    class CostModelFailure(RuntimeError):
        pass

    def fail_cost(_: int) -> bool:
        raise CostModelFailure("原成本模型錯誤")

    with pytest.raises(CostModelFailure, match="原成本模型錯誤"):
        max_affordable_lot_shares(
            requested_shares=1000,
            lot_size=1000,
            is_affordable=fail_cost,
        )


def test_cancel_before_first_cost_evaluation_raises_dedicated_error() -> None:
    cost_calls: list[int] = []

    def is_affordable(shares: int) -> bool:
        cost_calls.append(shares)
        return True

    with pytest.raises(AffordableOrderCancelledError):
        max_affordable_lot_shares(
            requested_shares=1000,
            lot_size=1000,
            is_affordable=is_affordable,
            check_cancel=lambda: True,
        )

    assert cost_calls == []


def test_cancel_is_polled_between_bisection_evaluations() -> None:
    cancel_checks = 0
    cost_calls: list[int] = []

    def check_cancel() -> bool:
        nonlocal cancel_checks
        cancel_checks += 1
        return cancel_checks == 2

    def is_affordable(shares: int) -> bool:
        cost_calls.append(shares)
        return False

    with pytest.raises(AffordableOrderCancelledError):
        max_affordable_lot_shares(
            requested_shares=8000,
            lot_size=1000,
            is_affordable=is_affordable,
            check_cancel=check_cancel,
        )

    assert cost_calls == [8000]
    assert cancel_checks == 2


def test_check_cancel_must_return_an_actual_bool() -> None:
    with pytest.raises(TypeError, match="check_cancel 必須回傳 bool"):
        max_affordable_lot_shares(
            requested_shares=1000,
            lot_size=1000,
            is_affordable=lambda _: True,
            check_cancel=lambda: 0,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("requested_shares", "lot_size"),
    [
        (True, 1000),
        (1000, True),
        (-1, 1000),
        (1000, 0),
        (1000, -1000),
    ],
)
def test_invalid_share_bounds_are_rejected(
    requested_shares: int,
    lot_size: int,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        max_affordable_lot_shares(
            requested_shares=requested_shares,
            lot_size=lot_size,
            is_affordable=lambda _: True,
        )


def test_non_callable_predicate_is_rejected() -> None:
    with pytest.raises(TypeError, match="is_affordable 必須可呼叫"):
        max_affordable_lot_shares(
            requested_shares=1000,
            lot_size=1000,
            is_affordable=None,  # type: ignore[arg-type]
        )


def requested_shares_floor(requested_shares: int, lot_size: int) -> int:
    """測試內表達可用整手上限，不引用生產 helper 的內部實作。"""

    return requested_shares // lot_size * lot_size
