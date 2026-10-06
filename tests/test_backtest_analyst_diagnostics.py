from types import SimpleNamespace
from decimal import Decimal

import pandas as pd

from app_module.backtest_analyst_diagnostics import build_backtest_analyst_diagnostics


def _report(*, periods: int = 4, initial_capital: int | None = 100000) -> SimpleNamespace:
    index = pd.date_range("2024-01-30", periods=periods, freq="D")
    equity = [initial_capital + index_no * 100 for index_no in range(periods)] if initial_capital else [100000 + index_no * 100 for index_no in range(periods)]
    frame = pd.DataFrame(
        {
            "equity": equity,
            "cash": [initial_capital or 100000] + [0] * (periods - 1),
            "position_value": [0] + [initial_capital or 100000] * (periods - 1),
        },
        index=index,
    )
    return SimpleNamespace(
        total_return=0.02,
        sharpe_ratio=1.1,
        max_drawdown=-0.03,
        baseline_comparison={
            "baseline_returns": 0.01,
            "baseline_sharpe": 0.8,
            "baseline_max_drawdown": -0.04,
            "excess_returns": 0.01,
            "relative_sharpe": 0.3,
            "relative_drawdown": 0.01,
        },
        details={
            "initial_capital": initial_capital,
            "equity_curve": frame,
            "transaction_costs": {
                "fee_cents": 1000,
                "slippage_cents": 200,
                "total_cents": 1200,
            },
            "execution_summary": {"gross_notional_cents": 1000000},
        },
    )


def test_diagnostics_uses_decimal_bp_and_frozen_baseline_fields():
    diagnostics = build_backtest_analyst_diagnostics(_report())

    assert diagnostics.status == "available"
    assert diagnostics.kpis["transaction_costs"]["fee_bp"] == 1
    assert diagnostics.kpis["transaction_costs"]["total_bp"] == 1
    assert diagnostics.benchmark["strategy_return_bp"] == 200
    assert diagnostics.benchmark["benchmark_return_bp"] == 100
    assert diagnostics.benchmark["sharpe_delta"] == Decimal("0.3")


def test_monthly_returns_use_month_end_change_and_first_month_anchor():
    diagnostics = build_backtest_analyst_diagnostics(_report())

    # Jan 31 / initial_capital, then Feb 2 / Jan 31; never first-observation-to-last.
    assert diagnostics.monthly[0]["return_bp"] == 10
    assert diagnostics.monthly[1]["return_bp"] == 20

    no_anchor = build_backtest_analyst_diagnostics(_report(initial_capital=None))
    assert no_anchor.monthly[0]["status"] == "unknown"
    assert "anchor" in str(no_anchor.monthly[0]["reason"])


def test_monthly_gap_is_unknown_instead_of_combining_two_months():
    index = pd.to_datetime(["2024-01-31", "2024-03-29", "2024-04-30"])
    frame = pd.DataFrame(
        {
            "equity": [100000, 120000, 121000],
            "cash": [100000, 120000, 121000],
            "position_value": [0, 0, 0],
        },
        index=index,
    )
    report = _report()
    report.details["equity_curve"] = frame

    diagnostics = build_backtest_analyst_diagnostics(report)

    march = next(item for item in diagnostics.monthly if item["month"] == 3)
    assert march["status"] == "unknown"
    assert march["return_bp"] is None
    assert "缺觀測月份" in str(march["reason"])


def test_rolling_is_trailing_only_and_does_not_look_ahead():
    original = _report(periods=65)
    changed = _report(periods=65)
    changed.details["equity_curve"].iloc[:4, changed.details["equity_curve"].columns.get_loc("equity")] = [900000, 1200000, 700000, 1500000]

    first = build_backtest_analyst_diagnostics(original)
    second = build_backtest_analyst_diagnostics(changed)
    assert first.rolling == second.rolling
    assert all(item["observation_count"] in {20, 60} for item in first.rolling)


def test_legacy_without_saved_equity_or_costs_is_explicitly_unknown():
    diagnostics = build_backtest_analyst_diagnostics(
        run_data={"total_return": 0.2, "baseline_comparison": {"baseline_returns": 0.1}}
    )
    assert diagnostics.status == "unknown"
    assert "equity_curve" in str(diagnostics.reason)

    legacy = _report()
    legacy.details.pop("transaction_costs")
    legacy.details.pop("execution_summary")
    details = build_backtest_analyst_diagnostics(legacy)
    assert details.kpis["transaction_costs"]["status"] == "unknown"
    assert details.kpis["turnover_status"] == "unknown"
