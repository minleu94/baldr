"""F06／P07帶寬研究的真分析因果、量能門檻與未知反例。"""
from copy import deepcopy
from decimal import localcontext, ROUND_DOWN

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from decision_module.strategies.baldr_bollinger_squeeze_contract import (
    STRATEGY_ID, STRATEGY_VERSION, rule_definition,
)
from decision_module.strategies.baldr_bollinger_squeeze_executor import BaldrBollingerSqueezeExecutor
from decision_module.strategies.contracts import StrategySpec


def frame(prices=None, volumes=None):
    prices = [100] * 65 + [120, 121, 122, 119, 115, 100, 90] if prices is None else prices
    volumes = [100000] * 65 + [200000] * 7 if volumes is None else volumes
    return pd.DataFrame({"Open": prices, "High": [p + 1 for p in prices],
                         "Low": [p - 1 for p in prices], "Close": prices, "Volume": volumes},
                        index=pd.bdate_range("2025-01-02", periods=len(prices)))


def spec():
    return StrategySpec(STRATEGY_ID, STRATEGY_VERSION, config={"params": {}})


def run(data, **kwargs):
    selected = spec()
    return BaldrBollingerSqueezeExecutor(selected).generate_signals(data, selected, **kwargs)


OBSERVATIONS = ["signal", "rule_observation_ready", "entry_rule_match", "exit_rule_match", "reason_tags",
                "squeeze", "previous_squeeze", "previous_close", "previous_upper", "band_width",
                "floor_width20", "floor_middle20", "observed_volume", "volume_sum20"]


def test_real_analysis_prefixes_poisoned_precomputed_bands_and_original_unchanged():
    data = frame()
    original = data.copy(deep=True)
    expected = run(data)
    for length in range(1, len(data) + 1):
        assert_frame_equal(run(data.iloc[:length])[OBSERVATIONS], expected.iloc[:length][OBSERVATIONS])
    poisoned = data.assign(upperband=1, lowerband=999, middleband=0)
    assert_frame_equal(run(poisoned)[OBSERVATIONS], expected[OBSERVATIONS])
    assert_frame_equal(data, original)
    assert expected["signal"].iloc[65] == 1
    assert expected["signal"].iloc[66:68].eq(0).all()
    assert not expected["rule_observation_ready"].iloc[:49].any()
    assert expected["rule_observation_ready"].iloc[49]
    assert expected["exit_rule_match"].iloc[-1]


@pytest.mark.parametrize("last_volume,entry", [(56, False), (57, False), (58, True), (0, False)])
def test_strict_15_volume_boundary_uses_including_today_window(last_volume, entry):
    # 57*20/(19*37+57)=1.5，等於門檻不可進場。
    result = run(frame([100] * 65 + [120], [37] * 65 + [last_volume]))
    assert bool(result["entry_rule_match"].iloc[-1]) is entry
    assert result["previous_squeeze"].iloc[-1] is True


@pytest.mark.parametrize("above", [False, True])
def test_large_integer_volume_preserves_one_share_around_exact_threshold(above):
    base = 37 * 10**16 + 1
    threshold_floor = 57 * base // 37
    volume = threshold_floor + int(above)
    result = run(frame([100] * 65 + [120], [base] * 65 + [volume]))
    assert bool(result["entry_rule_match"].iloc[-1]) is above
    assert result["observed_volume"].iloc[-1] == volume


def test_missing_quote_rewarms_all_bands_and_contraction_without_filling():
    data = frame([100] * 140, [100000] * 140)
    data.loc[data.index[65], ["Open", "High", "Low", "Close"]] = None
    data.loc[data.index[65], "Volume"] = 0
    result = run(data)
    assert not result["rule_observation_ready"].iloc[65:115].any()
    assert result["rule_observation_ready"].iloc[115]
    assert result["squeeze"].iloc[65] is None
    assert result["signal"].eq(0).all()


def test_missing_volume_does_not_become_zero_or_false_qualified_window():
    data = frame([100] * 90, [100000] * 90)
    data.loc[data.index[65], "Volume"] = None
    result = run(data)
    assert result["observed_volume"].iloc[65] is None
    assert result["volume_sum20"].iloc[65] is None
    assert not result["rule_observation_ready"].iloc[65:85].any()
    assert result["rule_observation_ready"].iloc[85]


@pytest.mark.parametrize("bad", [-1, "invalid", "Infinity", True, "1e100", "0.12345678901234567890123456789"])
def test_invalid_volume_is_rejected_not_silently_unknown(bad):
    data = frame().astype({"Volume": object})
    data.loc[data.index[65], "Volume"] = bad
    with pytest.raises(ValueError, match="成交股數"):
        run(data)


def test_no_volume_denominator_and_inside_upper_are_not_entry():
    result = run(frame([100] * 75, [0] * 75))
    assert not result["rule_observation_ready"].any()
    assert result["signal"].eq(0).all()
    equal = run(frame([100] * 75, [100000] * 74 + [500000]))
    assert equal["rule_observation_ready"].iloc[-1]
    assert equal["signal"].eq(0).all()


def test_test_window_uses_previous_facts_without_prior_orders_or_parameter_mutation():
    data = frame()
    start = data.index[65].date().isoformat()
    full = run(data)
    selected = run(data, execution_start_date=start)
    assert selected["signal"].iloc[:65].eq(0).all()
    assert_frame_equal(selected.loc[start:, OBSERVATIONS], full.loc[start:, OBSERVATIONS])
    value = spec()
    executor = BaldrBollingerSqueezeExecutor(value)
    value.name = "changed"
    with pytest.raises(ValueError, match="變動"):
        executor.generate_signals(data, value)


def test_low_decimal_context_does_not_change_signal_or_observation():
    expected = run(frame())
    with localcontext() as context:
        context.prec = 4
        context.rounding = ROUND_DOWN
        actual = run(frame())
    assert_frame_equal(actual[OBSERVATIONS], expected[OBSERVATIONS])


@pytest.mark.parametrize("params", [None, [], {"entry_confirm_sessions": 1}, {"lookback": 19}])
def test_fixed_rule_does_not_accept_ambiguous_parameters(params):
    with pytest.raises(ValueError):
        rule_definition(params)


def test_numeric_stock_dates_and_duplicate_or_timezone_rejection():
    data = frame()
    numeric = data.reset_index(drop=True)
    numeric["日期"] = [int(when.strftime("%Y%m%d")) for when in data.index]
    assert run(numeric)["signal"].tolist() == run(data)["signal"].tolist()
    duplicate = data.copy()
    duplicate.index = pd.DatetimeIndex([data.index[0], *data.index[:-1]])
    with pytest.raises(ValueError, match="日期索引"):
        run(duplicate)
    with pytest.raises(ValueError, match="日期索引"):
        run(data.tz_localize("Asia/Taipei"))


def test_metadata_and_rule_returns_do_not_share_mutable_parameters():
    first = BaldrBollingerSqueezeExecutor.get_meta()
    copy = deepcopy(first)
    first["params"]["other"] = 1
    assert BaldrBollingerSqueezeExecutor.get_meta() == copy
    assert rule_definition({})["historical_pit_eligible"] is False
