"""未成交日仍須保留收盤估值，並沿原時間軸處理既有委託。"""

from decimal import Decimal

import pandas as pd
import pytest

from backtest_module.broker_simulator import BrokerConfig, BrokerSimulator


def _frame(opens, closes, signals, *, volume=1000000):
    dates = pd.bdate_range("2026-07-01", periods=len(opens), name="date")
    return pd.DataFrame(
        {
            "開盤價": [Decimal(value) for value in opens],
            "收盤價": [Decimal(value) for value in closes],
            "成交股數": [volume] * len(opens),
            "signal": signals,
        },
        index=dates,
    )


def _broker(*, volume_constraint=False):
    return BrokerSimulator(BrokerConfig(
        execution_price="next_open", fee_bps=0, slippage_bps=0,
        enable_volume_constraint=volume_constraint, enable_limit_up_down=True,
    ))


@pytest.mark.parametrize(
    "capital,volume,reason",
    [
        (Decimal("100"), 1000000, "zero_requested_shares"),
        (Decimal("1000000"), 100, "participation_capacity_zero"),
    ],
)
def test_no_fill_keeps_every_session_and_ending_cash(capital, volume, reason):
    frame = _frame(["100", "100"], ["100", "101"], [1, 0], volume=volume)
    broker = _broker(volume_constraint=True)

    trades, equity = broker.run(frame, capital)

    assert trades == []
    assert equity.index.equals(frame.index)
    assert [Decimal(str(value)) for value in equity["equity"]] == [capital, capital]
    assert [Decimal(str(value)) for value in equity["cash"]] == [capital, capital]
    assert equity["position"].tolist() == [0, 0]
    assert broker.execution_diagnostics[0]["reason"] == reason


def test_limit_blocked_buy_observes_opposite_close_before_next_open():
    frame = _frame(["100", "110", "104"], ["100", "105", "103"], [1, -1, 0])
    broker = _broker()

    trades, equity = broker.run(frame, Decimal("1000000"))

    # 第二日不能買入；當日收盤已反向，第三日不得成交舊買單。
    assert trades == []
    assert equity.index.equals(frame.index)
    assert equity["position"].tolist() == [0, 0, 0]
    assert all(Decimal(str(value)) == Decimal("1000000") for value in equity["equity"])
    assert any(item.get("reason") == "opposite_close_signal" for item in broker.execution_diagnostics)


def test_limit_retry_uses_latest_completed_close_and_keeps_original_signal():
    frame = _frame(["100", "110", "120"], ["100", "110", "121"], [1, 0, 0])
    broker = _broker()

    trades, equity = broker.run(frame, Decimal("1000000"))

    # 第三日120低於前一收盤110的上限121；不可一直沿用第一日100。
    assert [(trade.type, trade.date, trade.shares) for trade in trades] == [
        ("buy", frame.index[2], 8000)
    ]
    assert equity.index.equals(frame.index)
    assert Decimal(str(equity.iloc[1]["cash"])) == Decimal("1000000")
    assert Decimal(str(equity.iloc[2]["cash"])) == Decimal("39980")
    assert Decimal(str(equity.iloc[2]["equity"])) == Decimal("1007980")
    filled = next(item for item in broker.execution_diagnostics if item["status"] == "filled")
    assert filled["signal_time"] == frame.index[0].isoformat()
    assert filled["execution_time"] == frame.index[2].isoformat()


def test_limit_blocked_sell_keeps_drawdown_and_original_exact_costs():
    frame = _frame(
        ["100", "100", "90", "84"], ["100", "100", "85", "84"], [1, -1, 0, 0]
    )
    broker = _broker()

    trades, equity = broker.run(frame, Decimal("1000000"))

    assert [(trade.type, trade.date, trade.shares) for trade in trades] == [
        ("buy", frame.index[1], 9000), ("sell", frame.index[3], 9000)
    ]
    assert equity.index.equals(frame.index)
    # 無成交的跌停日仍有持股及收盤損失；下一開盤賣出沿原最低費用與30bp稅。
    assert Decimal(str(equity.iloc[2]["equity"])) == Decimal("864980")
    assert equity.iloc[2]["position"] == 9000
    assert Decimal(str(trades[1].fee)) == Decimal("2288")
    assert Decimal(str(equity.iloc[3]["cash"])) == Decimal("853692")
    assert equity.iloc[3]["position"] == 0


def test_future_append_does_not_change_unfilled_session_history():
    frame = _frame(["100", "110", "120"], ["100", "110", "121"], [1, 0, 0])
    future = _frame(["100", "110", "120", "99999"], ["100", "110", "121", "1"], [1, 0, 0, -1])
    original_trades, original_equity = _broker().run(frame, Decimal("1000000"))
    appended_trades, appended_equity = _broker().run(future, Decimal("1000000"))

    assert original_trades == appended_trades
    pd.testing.assert_frame_equal(original_equity, appended_equity.loc[frame.index])
