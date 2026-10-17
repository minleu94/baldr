"""原P07三段收縮的確認時點、精確邊界與缺件反例。"""
from copy import deepcopy
from collections import deque
from decimal import Decimal, ROUND_DOWN, localcontext

import pandas as pd
from pandas.testing import assert_frame_equal
import pytest

from decision_module.strategies.baldr_vcp_contract import STRATEGY_ID, STRATEGY_VERSION, rule_definition
from decision_module.strategies.baldr_vcp_executor import BaldrVCPExecutor, _Bar, _Pivot, _base, _observe_frame
from decision_module.strategies.contracts import StrategySpec


def fixture_frame():
    tail = [122, 126, 130, 126, 120, 112, 110, 112, 120, 125, 128, 124, 119,
            116, 114, 116, 122, 126, 122, 120, 118, 120, 123, 125, 129, 133]
    prices = list(range(40, 120)) + tail
    volumes = [3000] * 80 + [6000] * 8 + [4500] * 8 + [2500] * (len(tail) - 16)
    volumes[-1] = 20000
    return pd.DataFrame({"Open": prices, "High": [p + 1 for p in prices],
                         "Low": [p - 1 for p in prices], "Close": prices, "Volume": volumes},
                        index=pd.bdate_range("2025-01-02", periods=len(prices)))


def spec():
    return StrategySpec(STRATEGY_ID, STRATEGY_VERSION, config={"params": {}})


def run(data, **kwargs):
    selected = spec()
    return BaldrVCPExecutor(selected).generate_signals(data, selected, **kwargs)


FIELDS = ["signal", "rule_observation_ready", "entry_rule_match", "exit_rule_match", "reason_tags",
          "setup_match", "pattern_already_consumed", "valid_observed_rows", "previous_close",
          "observed_close", "observed_volume", "vcp_ma20", "vcp_ma50", "volume_sum20", "contraction_evidence"]


def test_three_true_contractions_emit_one_breakout_and_keep_original():
    source = fixture_frame()
    original = source.copy(deep=True)
    result = run(source)
    assert result["entry_rule_match"].sum() == 1
    assert result.iloc[-1]["signal"] == 1
    assert result.iloc[-1]["contraction_evidence"]["pivot_price"] == Decimal(131)
    assert [p["position"] for p in result.iloc[-1]["contraction_evidence"]["pivots"]] == [82, 86, 90, 94, 97, 100]
    assert not result["rule_observation_ready"].iloc[:79].any()
    assert result["rule_observation_ready"].iloc[79]
    assert_frame_equal(source, original)


def test_every_prefix_and_future_suffix_preserve_original_decisions():
    source = fixture_frame()
    full = run(source)
    for length in range(1, len(source) + 1):
        assert_frame_equal(run(source.iloc[:length])[FIELDS], full.iloc[:length][FIELDS])
    suffix = source.iloc[-1:].copy()
    suffix.index = pd.bdate_range(source.index[-1] + pd.Timedelta(days=1), periods=1)
    suffix.loc[:, ["Open", "High", "Low", "Close"]] = [500, 1000, 1, 900]
    assert_frame_equal(run(pd.concat([source, suffix])).iloc[:len(source)][FIELDS], full[FIELDS])


def test_turning_point_is_known_only_after_two_right_rows():
    result = run(fixture_frame())
    for position in (100, 101):
        assert all(p["position"] != 100 for p in result.iloc[position]["contraction_evidence"]["pivots"])
    last = result.iloc[102]["contraction_evidence"]["pivots"][-1]
    assert last == {"kind": "low", "position": 100, "price": Decimal(117), "confirmed_position": 102}


def test_context_breakout_is_consumed_without_creating_an_order():
    source = fixture_frame()
    suffix = source.iloc[-2:].copy()
    suffix.index = pd.bdate_range(source.index[-1] + pd.Timedelta(days=1), periods=2)
    complete = pd.concat([source, suffix])
    result = run(complete)
    assert result["entry_rule_match"].sum() == 1
    assert result.iloc[-1]["pattern_already_consumed"]
    contextual = run(complete, execution_start_date=complete.index[-2].strftime("%Y-%m-%d"))
    assert not contextual["entry_rule_match"].any()
    assert contextual.iloc[-1]["pattern_already_consumed"]


@pytest.mark.parametrize("increment,expected", [(0, False), (1, True)])
def test_large_integer_volume_one_share_boundary(increment, expected):
    source = fixture_frame()
    base = 2 ** 53 + 1
    source["Volume"] = pd.Series([3 * base] * len(source), index=source.index, dtype=object)
    source.loc[source.index[-20:], "Volume"] = base
    source.loc[source.index[-1], "Volume"] = 57 * base // 37 + increment
    result = run(source)
    assert result.iloc[-1]["setup_match"]
    assert bool(result.iloc[-1]["entry_rule_match"]) is expected
    assert result.iloc[-1]["observed_volume"] == 57 * base // 37 + increment


def test_missing_input_resets_all_affected_windows():
    source = fixture_frame().astype(object)
    source.loc[source.index[90], "Volume"] = None
    result = run(source)
    assert result.iloc[90]["valid_observed_rows"] == 0
    assert result.iloc[90]["contraction_evidence"] == {"pivots": []}
    assert not result["rule_observation_ready"].iloc[90:].any()
    assert not result["entry_rule_match"].any()


def test_official_missing_price_marker_is_unknown_and_rewarms_without_zero_fill():
    source = fixture_frame().astype(object)
    source.loc[source.index[90], ["Open", "High", "Low", "Close", "Volume"]] = ["--", "--", "--", "--", 0]
    result = run(source)
    assert result.iloc[90]["observed_close"] is None
    assert result.iloc[90]["valid_observed_rows"] == 0
    assert not result["rule_observation_ready"].iloc[90:].any()


def test_grouped_numeric_text_keeps_exact_decisions_and_rejects_invalid_grouping():
    source = fixture_frame()
    grouped = source.apply(lambda column: column.map(lambda value: f"{value:,}"))
    assert_frame_equal(run(grouped)[FIELDS], run(source)[FIELDS])
    grouped.loc[grouped.index[-1], "Volume"] = "1,00"
    with pytest.raises(ValueError, match="千分位"):
        run(grouped)


@pytest.mark.parametrize("case", ["first_depth", "last_depth", "low_not_raised", "high_increased", "volume_not_dry", "equal_pivot"])
def test_each_failed_contraction_or_breakout_condition_remains_a_nonmatch(case):
    source = fixture_frame()
    replacement = {"first_depth": (82, 200), "last_depth": (100, 117),
                   "low_not_raised": (94, 108), "high_increased": (90, 132),
                   "equal_pivot": (105, 131)}
    if case == "volume_not_dry":
        source.loc[source.index[97:101], "Volume"] = 6000
    else:
        position, close = replacement[case]
        source.loc[source.index[position], ["Open", "High", "Low", "Close"]] = [close, close + 1, close - 1, close]
    result = run(source)
    assert result.iloc[-1]["rule_observation_ready"]
    assert not result["entry_rule_match"].any()


def test_known_sma_exit_and_equal_hold_are_separate_from_a_missing_setup():
    source = fixture_frame().iloc[:80].copy()
    source.loc[:, ["Open", "High", "Low", "Close"]] = [100, 101, 99, 100]
    equal = run(source)
    assert equal.iloc[-1]["setup_match"] is False
    assert not equal.iloc[-1]["exit_rule_match"]
    source.loc[source.index[-1], ["Open", "High", "Low", "Close"]] = [99, 100, 98, 99]
    below = run(source)
    assert below.iloc[-1]["exit_rule_match"]
    assert below.iloc[-1]["signal"] == -1


@pytest.mark.parametrize("boundary,low,expected", [
    ("first", "105", True), ("first", "104.999999999999999999999999", False),
    ("last", "115", True), ("last", "114.999999999999999999999999", False),
])
def test_depth_caps_include_equality_and_reject_the_next_decimal(boundary, low, expected):
    # 此處單測三段原值的比例上限；實際轉折確認另由全prefix案例驗證。
    first_low = Decimal(low) if boundary == "first" else Decimal(105)
    last_low = Decimal(low) if boundary == "last" else Decimal(115)
    pivots = deque([_Pivot("high", 80, Decimal(150), 82), _Pivot("low", 84, first_low, 86),
                    _Pivot("high", 88, Decimal(140), 90), _Pivot("low", 92, Decimal(113), 94),
                    _Pivot("high", 96, Decimal(125), 98), _Pivot("low", 100, last_low, 102)])
    bars = deque(_Bar(p, Decimal(120), Decimal(119), Decimal(120), 6000 if p <= 84 else 2500)
                 for p in range(80, 105))
    with localcontext() as context:
        context.prec = 120
        assert _base(pivots, bars, 104, 60)[0] is expected


def test_expired_base_is_not_reused_after_the_declared_window():
    source = fixture_frame()
    suffix = pd.concat([source.iloc[-1:]] * 80, ignore_index=True)
    suffix.index = pd.bdate_range(source.index[-1] + pd.Timedelta(days=1), periods=80)
    result = run(pd.concat([source, suffix]))
    assert result.iloc[-1]["rule_observation_ready"]
    assert result.iloc[-1]["setup_match"] is False
    assert result.iloc[-1]["contraction_evidence"]["pivots"] == []


def test_precomputed_fields_are_not_a_rule_source_and_decimal_context_is_local():
    source = fixture_frame()
    baseline = run(source)
    with localcontext() as context:
        context.prec = 6
        context.rounding = ROUND_DOWN
        actual = run(source.assign(MA20=999999, MA50=0, setup_match=True, signal=1))
        assert context.prec == 6
    assert_frame_equal(actual[FIELDS], baseline[FIELDS])


@pytest.mark.parametrize("field,value", [("Volume", -1), ("Volume", Decimal("1.5")), ("Volume", 1000.0),
                                         ("Volume", True), ("High", 1), ("Low", 500),
                                         ("Close", 0), ("Open", Decimal("Infinity"))])
def test_invalid_raw_values_reject_instead_of_fabricating_a_signal(field, value):
    source = fixture_frame().astype(object)
    source.loc[source.index[-1], field] = value
    with pytest.raises(ValueError):
        run(source)


def test_fixed_contract_rejects_other_versions_params_and_mutation():
    with pytest.raises(ValueError):
        BaldrVCPExecutor(StrategySpec(STRATEGY_ID, "2.0.0", config={"params": {}}))
    with pytest.raises(ValueError):
        rule_definition({"pivot_span": 3})
    selected = spec()
    executor = BaldrVCPExecutor(selected)
    selected.config["params"]["pivot_span"] = 3
    with pytest.raises(ValueError):
        executor.generate_signals(fixture_frame(), selected)


def test_sensitivity_cannot_claim_the_registered_fixed_version():
    variant = _observe_frame(fixture_frame(), pivot_span=1, max_base_rows=80)
    assert variant.attrs["rule_diagnostics"]["fixed_version_compatible"] is False
    assert variant.attrs["rule_diagnostics"]["strategy_id"] == "experimental_not_registered_strategy"
    rule = rule_definition({})
    changed = deepcopy(rule)
    changed["pivot"]["right_confirmation_rows"] = 0
    assert rule_definition({}) == rule


@pytest.mark.parametrize("kind", ["duplicate", "reverse", "intraday", "tz"])
def test_date_identity_must_be_unique_ordered_naive_days(kind):
    source = fixture_frame()
    if kind == "duplicate":
        source.index = pd.DatetimeIndex([source.index[0]] * len(source))
    elif kind == "reverse":
        source = source.iloc[::-1]
    elif kind == "intraday":
        source.index += pd.Timedelta(hours=1)
    else:
        source.index = source.index.tz_localize("Asia/Taipei")
    with pytest.raises(ValueError):
        run(source)
