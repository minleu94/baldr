"""策略版本回測摘要的缺值與有限數值呈現。"""

from decimal import Decimal

import pytest

from ui_qt.views.portfolio_view import format_strategy_version_backtest_summary


@pytest.mark.parametrize(
    ("missing_key", "expected_fragment"),
    [
        ("total_return", "總報酬: 未提供"),
        ("sharpe_ratio", "Sharpe: 未提供"),
        ("max_drawdown", "MaxDD: 未提供"),
    ],
)
def test_each_missing_strategy_metric_is_unavailable_independently(
    missing_key: str,
    expected_fragment: str,
) -> None:
    summary: dict[str, object] = {
        "total_return": Decimal("0.125"),
        "sharpe_ratio": Decimal("1.234"),
        "max_drawdown": Decimal("-0.045"),
    }
    summary.pop(missing_key)

    rendered = format_strategy_version_backtest_summary(summary)

    assert expected_fragment in rendered
    if missing_key != "total_return":
        assert "總報酬: +12.5%" in rendered
    if missing_key != "sharpe_ratio":
        assert "Sharpe: 1.23" in rendered
    if missing_key != "max_drawdown":
        assert "MaxDD: -4.5%" in rendered


def test_valid_zero_metrics_remain_observed_zero_with_existing_units() -> None:
    rendered = format_strategy_version_backtest_summary(
        {"total_return": 0, "sharpe_ratio": Decimal("0"), "max_drawdown": 0.0}
    )

    assert rendered == "總報酬: +0.0%, Sharpe: 0.00, MaxDD: 0.0%"


@pytest.mark.parametrize(
    "value",
    [None, "not-a-number", True, Decimal("NaN"), Decimal("Infinity"), float("-inf")],
)
@pytest.mark.parametrize(
    ("key", "expected_fragment"),
    [
        ("total_return", "總報酬: 未提供"),
        ("sharpe_ratio", "Sharpe: 未提供"),
        ("max_drawdown", "MaxDD: 未提供"),
    ],
)
def test_invalid_or_nonfinite_strategy_metric_is_not_displayed_as_a_number(
    key: str,
    expected_fragment: str,
    value: object,
) -> None:
    rendered = format_strategy_version_backtest_summary({key: value})

    assert expected_fragment in rendered
    assert "nan" not in rendered.lower()
    assert "inf" not in rendered.lower()
