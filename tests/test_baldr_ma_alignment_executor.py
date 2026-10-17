"""F02研究策略的因果、暖機、未知及固定規格反例。"""
from copy import deepcopy
from decimal import localcontext, ROUND_DOWN

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from decision_module.strategies.baldr_ma_alignment_contract import (
    STRATEGY_ID, STRATEGY_VERSION, rule_definition,
)
from decision_module.strategies.baldr_ma_alignment_executor import BaldrMAAlignmentExecutor
from decision_module.strategies.contracts import StrategySpec


def frame(prices=None):
    prices = list(range(100, 180)) + list(range(180, 100, -1)) + list(range(100, 220)) if prices is None else prices
    return pd.DataFrame({"Open": prices, "High": [p + 1 for p in prices],
                         "Low": [p - 1 for p in prices], "Close": prices, "Volume": 100000},
                        index=pd.bdate_range("2025-01-02", periods=len(prices)))


def spec():
    return StrategySpec(STRATEGY_ID, STRATEGY_VERSION, config={"params": {}})


def run(data, **kwargs):
    value = spec()
    return BaldrMAAlignmentExecutor(value).generate_signals(data, value, **kwargs)


OBSERVATIONS = ["signal", "rule_observation_ready", "ma_alignment", "previous_ma_alignment", "entry_rule_match", "exit_rule_match", "reason_tags"]


def test_every_prefix_is_unchanged_by_future_rows_and_precomputed_ma():
    source = frame()
    original = source.copy(deep=True)
    expected = run(source)
    for length in range(1, len(source) + 1):
        assert_frame_equal(run(source.iloc[:length])[OBSERVATIONS], expected.iloc[:length][OBSERVATIONS])
    poisoned = source.assign(MA5=1, MA10=2, MA20=3, MA60=4)
    assert_frame_equal(run(poisoned)[OBSERVATIONS], expected[OBSERVATIONS])
    assert_frame_equal(source, original)
    assert expected["entry_rule_match"].sum() == 1
    assert not expected["entry_rule_match"].iloc[:60].any()
    assert not expected["rule_observation_ready"].iloc[:59].any()
    assert expected["rule_observation_ready"].iloc[59]


def test_equality_is_known_not_aligned_and_not_a_growth_or_cross_signal():
    result = run(frame([100] * 100))
    assert not result["entry_rule_match"].any()
    assert result["ma_alignment"].iloc[60] is False
    assert result["exit_rule_match"].iloc[60]
    assert result["signal"].iloc[60] == -1
    rising = run(frame(list(range(100, 220))))
    assert not rising["entry_rule_match"].any()
    assert rising["ma_alignment"].iloc[59] is True


def test_missing_ohlc_rewarms_and_does_not_turn_unknown_into_exit():
    source = frame()
    source.loc[source.index[100], "Close"] = None
    result = run(source)
    assert not result["rule_observation_ready"].iloc[100:160].any()
    assert result["ma_alignment"].iloc[100] is None
    assert not result["signal"].iloc[100:160].any()
    assert result["rule_observation_ready"].iloc[160]
    assert not result["entry_rule_match"].iloc[160]


def test_test_start_retains_indicator_prefix_but_never_emits_orders_before_start():
    source = frame()
    full = run(source)
    start = source.index[180].date().isoformat()
    result = run(source, execution_start_date=start)
    assert not result.loc[result.index < start, "signal"].any()
    assert_frame_equal(result.loc[result.index >= start, OBSERVATIONS], full.loc[full.index >= start, OBSERVATIONS])


def test_decimal_caller_context_and_numeric_stock_dates_do_not_change_rules():
    source = frame()
    expected = run(source)
    with localcontext() as context:
        context.prec = 2
        context.rounding = ROUND_DOWN
        assert_frame_equal(run(source)[OBSERVATIONS], expected[OBSERVATIONS])
    numeric = source.reset_index(drop=True)
    numeric["日期"] = source.index.strftime("%Y%m%d").astype(int)
    actual = run(numeric)
    assert actual.index.equals(expected.index)
    assert_frame_equal(actual[OBSERVATIONS].reset_index(drop=True), expected[OBSERVATIONS].reset_index(drop=True))


@pytest.mark.parametrize("params", [{"buy_score": 60}, {"entry_confirm_sessions": 2}, {"periods": [5, 20]}, None])
def test_no_score_or_period_fallback(params):
    with pytest.raises(ValueError):
        rule_definition(params)


def test_version_mutation_and_invalid_dates_are_rejected():
    value = spec()
    executor = BaldrMAAlignmentExecutor(value)
    changed = deepcopy(value)
    changed.strategy_version = "1.0.1"
    with pytest.raises(ValueError, match="規格已變動"):
        executor.generate_signals(frame(), changed)
    with pytest.raises(ValueError, match="版本不符"):
        BaldrMAAlignmentExecutor(changed)
    for data in (frame().iloc[::-1], frame().set_axis([pd.Timestamp("2025-01-02")] * len(frame())),
                 frame().tz_localize("Asia/Taipei")):
        with pytest.raises(ValueError, match="日期索引"):
            run(data)
    with pytest.raises(ValueError, match="成交股數"):
        run(frame().drop(columns="Volume"))
    mutable = spec()
    frozen = BaldrMAAlignmentExecutor(mutable)
    mutable.config["params"]["buy_score"] = 1
    with pytest.raises(ValueError, match="規格已變動"):
        frozen.generate_signals(frame(), mutable)
