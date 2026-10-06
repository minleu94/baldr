"""RecommendationPortfolioBacktestService 的臺銀證券成本 consumer 回歸。"""

from decimal import Decimal

import pandas as pd
import pytest

from app_module.recommendation_portfolio_backtest_service import (
    RecommendationPortfolioBacktestService,
)
from financial_module.banktaiwan_cost_policy import (
    BANKTAIWAN_ELECTRONIC_COST_POLICY_ID,
    BANKTAIWAN_ELECTRONIC_COST_POLICY_VERSION,
    BankTaiwanElectronicCostPolicy,
    BankTaiwanOrder,
)


def _provider(*_args):
    return [
        {
            "stock_code": "2330",
            "stock_name": "台積電",
            "total_score": 90,
            "factor_scores": {},
        }
    ]


def _history_for_buy():
    return pd.DataFrame(
        [
            {"日期": "2026-06-05", "證券代號": "2330", "收盤價": "10", "成交股數": 200},
            {"日期": "2026-06-08", "證券代號": "2330", "開盤價": "10", "收盤價": "10", "成交股數": 100000},
        ]
    )


def _run(history, **kwargs):
    params = {
        "start_date": "2026-06-05",
        "end_date": "2026-06-08",
        "profile_id": "fixture",
        "recommendation_config": {},
        "history": history,
        "initial_capital": "10020",
        "rebalance_frequency": "once",
        "top_n": 1,
        "allocation_method": "equal_weight",
        "holding_days": 30,
        "cost_policy_id": BANKTAIWAN_ELECTRONIC_COST_POLICY_ID,
        "cost_policy_lot_type": "full_lot",
        "cost_policy_instrument_type": "ordinary_stock",
    }
    params.update(kwargs)
    return RecommendationPortfolioBacktestService(_provider).run_portfolio_backtest(**params)


def test_full_lot_affordability_includes_twenty_twd_minimum_and_metadata():
    result = _run(_history_for_buy())

    assert result.period_holdings[0].shares == 1000
    assert result.trades.iloc[0]["fee"] == 20
    assert result.trades.iloc[0]["tax"] == 0
    assert result.summary["ending_cash"] == 0
    assert result.summary["cost_policy_id"] == BANKTAIWAN_ELECTRONIC_COST_POLICY_ID
    assert result.summary["cost_policy_version"] == BANKTAIWAN_ELECTRONIC_COST_POLICY_VERSION
    assert result.summary["cost_basis"] == "estimated_research_only"
    assert result.summary["broker_fill_observed"] is False
    assert result.details["execution_cost_policy"]["minimum_commission_twd"] == "20"
    assert result.details["portfolio_credibility"]["execution_costs"]["policy_version"] == (
        BANKTAIWAN_ELECTRONIC_COST_POLICY_VERSION
    )


def test_cash_one_twd_below_full_lot_cost_remains_unfilled():
    result = _run(_history_for_buy(), initial_capital="10019")

    assert result.trades.empty
    assert result.period_holdings == []
    assert result.summary["ending_cash"] == 10019
    assert result.details["unfilled_orders"][0]["reason"] == "zero_requested_shares"


def test_odd_lot_order_caps_at_999_and_records_unallocated_budget():
    result = _run(
        _history_for_buy(),
        initial_capital="20000",
        cost_policy_lot_type="odd_lot",
    )

    assert result.period_holdings[0].shares == 999
    assert result.trades.iloc[0]["fee"] == 4
    assert result.summary["unallocated_cash"] == 10006
    assert result.summary["unallocated_allocation_count"] == 1
    allocation = result.details["unallocated_allocations"][0]
    assert allocation["reason"] == "odd_lot_order_cap_999"
    assert allocation["requested_shares_before_cap"] == 2000
    assert allocation["filled_shares"] == 999
    assert allocation["unallocated_amount"] == "10006.00"


class _RecordingPolicy(BankTaiwanElectronicCostPolicy):
    def __init__(self):
        super().__init__()
        self.calls = []

    def estimate(self, order: BankTaiwanOrder):
        self.calls.append(order)
        return super().estimate(order)


def test_partial_fill_recomputes_same_policy_for_affordability_and_actual_fill():
    history = pd.DataFrame(
        [
            {"日期": "2026-06-05", "證券代號": "2330", "收盤價": "10", "成交股數": 200},
            {"日期": "2026-06-08", "證券代號": "2330", "開盤價": "10", "收盤價": "10", "成交股數": 200},
            {"日期": "2026-06-09", "證券代號": "2330", "開盤價": "10", "收盤價": "10", "成交股數": 200},
            {"日期": "2026-06-10", "證券代號": "2330", "開盤價": "12", "收盤價": "12", "成交股數": 200},
        ]
    )
    service = RecommendationPortfolioBacktestService(_provider)
    policy = _RecordingPolicy()
    service._banktaiwan_cost_policy = policy
    result = service.run_portfolio_backtest(
        start_date="2026-06-05",
        end_date="2026-06-10",
        profile_id="fixture",
        recommendation_config={},
        history=history,
        initial_capital="2000",
        rebalance_frequency="once",
        top_n=1,
        allocation_method="equal_weight",
        holding_days=1,
        max_participation_rate="0.25",
        cost_policy_id=BANKTAIWAN_ELECTRONIC_COST_POLICY_ID,
        cost_policy_lot_type="odd_lot",
        cost_policy_instrument_type="ordinary_stock",
    )

    buy_calls = [item for item in policy.calls if item.side == "buy"]
    assert [item.quantity_shares for item in buy_calls] == [200, 199, 50]
    assert len({item.order_id for item in buy_calls}) == 1
    assert len({item.trade_date for item in buy_calls}) == 1
    assert list(result.trades["shares"]) == [50, 50]
    assert list(result.trades["fee"]) == [1, 1]
    assert list(result.trades["tax"]) == [0, 1]
    assert result.summary["total_transaction_cost"] == 3
    assert result.summary["total_trades"] == 1


def test_policy_does_not_accept_unknown_or_generic_etf_in_consumer():
    with pytest.raises(ValueError, match="未知商品"):
        _run(_history_for_buy(), cost_policy_instrument_type="unknown")
    with pytest.raises(ValueError, match="過於寬泛"):
        _run(_history_for_buy(), cost_policy_instrument_type="ETF")


def test_next_open_policy_uses_execution_date_and_ignores_future_rows():
    base = _history_for_buy()
    future = pd.DataFrame(
        [{"日期": "2026-06-09", "證券代號": "2330", "開盤價": "999", "收盤價": "999"}]
    )
    first = _run(base)
    with_future = _run(pd.concat([base, future], ignore_index=True))

    pd.testing.assert_frame_equal(first.trades, with_future.trades)
    pd.testing.assert_frame_equal(first.equity_curve, with_future.equity_curve)
    assert first.trades.iloc[0]["date"] == "2026-06-08"
    assert first.trades.iloc[0]["cost_estimate"]["trade_date"] == "2026-06-08"


def test_policy_arguments_cannot_be_mixed_with_legacy_close_contract_or_bps():
    with pytest.raises(ValueError, match="僅支援 NEXT_OPEN"):
        _run(_history_for_buy(), execution_contract="legacy_same_day_close")
    with pytest.raises(ValueError, match="不可與 fee/slippage/tax bps 混用"):
        _run(_history_for_buy(), fee_bps=1)
