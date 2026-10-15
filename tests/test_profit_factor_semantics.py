from __future__ import annotations

from decimal import Decimal, Inexact, localcontext

import pandas as pd

from backtest_module.broker_simulator import Trade
from backtest_module.performance_metrics import PerformanceAnalyzer, PerformanceMetrics


def _trade(
    side: str,
    *,
    day: str,
    price: int,
    shares: int,
    value: int,
    fee: int,
    slippage: int,
) -> Trade:
    return Trade(
        date=pd.Timestamp(day),
        type=side,
        price=price,
        shares=shares,
        value=value,
        fee=fee,
        slippage=slippage,
        reason_tags="increment50-synthetic",
        signal=1 if side == "buy" else -1,
    )


def _mixed_trades(scale: int = 1) -> list[Trade]:
    return [
        _trade("buy", day="2026-01-02", price=100, shares=10 * scale,
               value=1000 * scale, fee=5 * scale, slippage=5 * scale),
        _trade("sell", day="2026-01-05", price=112, shares=4 * scale,
               value=448 * scale, fee=2 * scale, slippage=2 * scale),
        _trade("sell", day="2026-01-06", price=112, shares=6 * scale,
               value=672 * scale, fee=3 * scale, slippage=3 * scale),
        _trade("buy", day="2026-01-07", price=100, shares=10 * scale,
               value=1000 * scale, fee=5 * scale, slippage=5 * scale),
        _trade("sell", day="2026-01-08", price=72, shares=10 * scale,
               value=720 * scale, fee=5 * scale, slippage=5 * scale),
    ]


def _equity_curve() -> pd.DataFrame:
    return pd.DataFrame(
        {"equity": [10_000, 10_100]},
        index=pd.DatetimeIndex(["2026-01-02", "2026-01-05"]),
    )


def test_manual_legacy_metrics_default_profit_factor_status_is_unversioned() -> None:
    metrics = PerformanceMetrics(
        total_return=0,
        annual_return=0,
        sharpe_ratio=0,
        max_drawdown=0,
        win_rate=0,
        total_trades=0,
        expectancy=0,
        profit_factor=0,
        avg_win=0,
        avg_loss=0,
        largest_win=0,
        largest_loss=0,
    )

    assert metrics.profit_factor == 0
    assert metrics.profit_factor_status == "legacy_unversioned"


def test_empty_and_unclosed_buys_report_no_closed_pairs() -> None:
    analyzer = PerformanceAnalyzer()
    buy_only = _trade(
        "buy", day="2026-01-02", price=100, shares=10,
        value=1000, fee=5, slippage=5,
    )

    for trades in ([], [buy_only]):
        stats = analyzer._analyze_trades(trades, initial_capital=10_000)
        summary = analyzer.summarize(trades, _equity_curve(), initial_capital=10_000)

        assert stats["total_trades"] == 0
        assert stats["profit_factor"] is None
        assert stats["profit_factor_status"] == "no_closed_pairs"
        assert summary.total_trades == 0
        assert summary.profit_factor is None
        assert summary.profit_factor_status == "no_closed_pairs"


def test_all_winning_pairs_have_unbounded_status_without_infinity() -> None:
    analyzer = PerformanceAnalyzer()
    trades = [
        _trade("buy", day="2026-01-02", price=100, shares=10,
               value=1000, fee=5, slippage=5),
        _trade("sell", day="2026-01-05", price=112, shares=10,
               value=1120, fee=5, slippage=5),
    ]

    pairs = analyzer._closed_trade_pairs(trades)
    stats = analyzer._analyze_trades(trades, initial_capital=10_000)
    summary = analyzer.summarize(trades, _equity_curve(), initial_capital=10_000)

    assert len(pairs) == 1
    assert pairs[0]["shares"] == 10
    assert Decimal(str(pairs[0]["profit"])) == Decimal("100")
    assert stats["profit_factor"] is None
    assert stats["profit_factor_status"] == "unbounded_no_gross_loss"
    assert summary.profit_factor is None
    assert summary.profit_factor_status == "unbounded_no_gross_loss"


def test_flat_pairs_are_undefined_zero_over_zero() -> None:
    analyzer = PerformanceAnalyzer()
    trades = [
        _trade("buy", day="2026-01-02", price=100, shares=10,
               value=1000, fee=5, slippage=5),
        _trade("sell", day="2026-01-05", price=102, shares=10,
               value=1020, fee=5, slippage=5),
    ]

    pairs = analyzer._closed_trade_pairs(trades)
    stats = analyzer._analyze_trades(trades, initial_capital=10_000)
    summary = analyzer.summarize(trades, _equity_curve(), initial_capital=10_000)

    assert len(pairs) == 1
    assert Decimal(str(pairs[0]["profit"])) == Decimal("0")
    assert stats["profit_factor"] is None
    assert stats["profit_factor_status"] == "undefined_zero_over_zero"
    assert summary.profit_factor is None
    assert summary.profit_factor_status == "undefined_zero_over_zero"


def test_losses_only_have_observed_zero_profit_factor() -> None:
    analyzer = PerformanceAnalyzer()
    trades = [
        _trade("buy", day="2026-01-02", price=100, shares=10,
               value=1000, fee=5, slippage=5),
        _trade("sell", day="2026-01-05", price=92, shares=10,
               value=920, fee=5, slippage=5),
    ]

    pairs = analyzer._closed_trade_pairs(trades)
    stats = analyzer._analyze_trades(trades, initial_capital=10_000)
    summary = analyzer.summarize(trades, _equity_curve(), initial_capital=10_000)

    assert len(pairs) == 1
    assert Decimal(str(pairs[0]["profit"])) == Decimal("-100")
    assert stats["profit_factor"] == 0.0
    assert stats["profit_factor_status"] == "observed"
    assert summary.profit_factor == 0.0
    assert summary.profit_factor_status == "observed"


def test_mixed_factor_uses_net_fifo_pairs_and_is_scale_invariant() -> None:
    analyzer = PerformanceAnalyzer()
    trades = _mixed_trades()
    scaled_trades = _mixed_trades(scale=7)
    pairs = analyzer._closed_trade_pairs(trades)
    stats = analyzer._analyze_trades(trades, initial_capital=10_000)
    scaled_stats = analyzer._analyze_trades(scaled_trades, initial_capital=70_000)
    summary = analyzer.summarize(trades, _equity_curve(), initial_capital=10_000)

    assert [pair["shares"] for pair in pairs] == [4, 6, 10]
    assert [Decimal(str(pair["profit"])) for pair in pairs] == [
        Decimal("40"), Decimal("60"), Decimal("-300")
    ]
    assert stats["profit_factor_status"] == "observed"
    assert scaled_stats["profit_factor_status"] == "observed"
    assert isinstance(stats["profit_factor"], float)
    assert isinstance(scaled_stats["profit_factor"], float)
    factor = Decimal(str(stats["profit_factor"]))
    scaled_factor = Decimal(str(scaled_stats["profit_factor"]))
    assert factor.is_finite() and factor >= 0
    assert scaled_factor.is_finite() and scaled_factor >= 0
    assert factor == scaled_factor
    with localcontext() as context:
        context.prec = 60
        assert abs(factor - (Decimal("100") / Decimal("300"))) < Decimal("1e-15")
    assert summary.profit_factor == stats["profit_factor"]
    assert summary.profit_factor_status == "observed"


def test_caller_decimal_precision_and_inexact_trap_do_not_change_factor() -> None:
    outputs: list[tuple[Decimal, str]] = []
    for precision, trap_inexact in ((6, True), (28, False), (60, True)):
        with localcontext() as context:
            context.prec = precision
            context.traps[Inexact] = trap_inexact
            summary = PerformanceAnalyzer().summarize(
                _mixed_trades(), _equity_curve(), initial_capital=10_000
            )
        assert summary.profit_factor is not None
        outputs.append(
            (Decimal(str(summary.profit_factor)), summary.profit_factor_status)
        )

    assert outputs[0] == outputs[1] == outputs[2]
    assert outputs[0][1] == "observed"
