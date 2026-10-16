"""W底自有研究核心：逐日可知、反證、原撮合與輸入不變；全部為合成行情。"""
from datetime import date
from decimal import Decimal, Overflow, ROUND_DOWN, localcontext
import ast
import json
from pathlib import Path

import pandas as pd
import pytest

from analysis_module.pattern_analysis.causal_w_bottom import observe_w_bottom, price_decimal
from backtest_module.broker_simulator import BrokerConfig, BrokerSimulator
from decision_module.strategies.baldr_w_bottom_contract import (
    STRATEGY_ID, STRATEGY_VERSION, PARAMETER_CONTRACT, rule_definition, wait_sessions,
)
from decision_module.strategies.baldr_w_bottom_executor import BaldrWBottomExecutor
from decision_module.strategies.contracts import StrategySpec
from decision_module.strategies.registry import StrategyRegistry


# 第一谷idx6、頸線idx8、第二谷idx10於idx11確認、idx12突破、idx15跌回。
BASE = [120, 118, 116, 112, 108, 104, 100, 105, 110, 106, 101, 106, 111, 114, 110, 109, 108]


def selected(wait=20):
    return StrategySpec(STRATEGY_ID, STRATEGY_VERSION, config={"params": {"max_wait_sessions": wait}})


def market(closes=None):
    values = [Decimal(str(value)) if value is not None else None for value in (BASE if closes is None else closes)]
    index = pd.bdate_range("2026-01-02", periods=len(values))
    return pd.DataFrame({"Open": values, "High": [value + 1 if value is not None else None for value in values],
                         "Low": [value - 1 if value is not None else None for value in values],
                         "Close": values, "Volume": [1000000] * len(values)}, index=index)


def run(frame=None, *, wait=20, start=None):
    spec = selected(wait)
    return BaldrWBottomExecutor(spec).generate_signals(market() if frame is None else frame, spec, start)


def test_frozen_rule_contract_is_independent_research_and_not_publicly_registered():
    assert not StrategyRegistry.is_registered(STRATEGY_ID)
    rules = rule_definition({})
    assert rules["schema"] == PARAMETER_CONTRACT
    assert rules["historical_pit_eligible"] is rules["performance_evaluable"] is False
    assert rules["entry"]["max_wait_sessions"] == 20
    assert rules["state"] == "order_intent_episode_not_assumed_fills"
    assert rules["execution"] == "next-session-open.v2"


def test_actual_confirmation_is_right_row_not_second_trough_or_chart_end():
    frame = market(); result = run(frame)
    assert result.index[result.signal == 1].tolist() == [frame.index[12]]
    assert result.index[result.signal == -1].tolist() == [frame.index[15]]
    assert result.iloc[10].pattern_confirmed_at is None
    assert result.iloc[11].pattern_second_trough_at == frame.index[10].date()
    assert result.iloc[11].pattern_confirmed_at == frame.index[11].date()
    assert result.iloc[12].pattern_confirmed_at == frame.index[11].date()
    assert result.iloc[12].pattern_neckline_at == frame.index[8].date()
    assert result.iloc[12].pattern_neckline == Decimal("110")
    assert result.iloc[12].pattern_floor == Decimal("100")
    assert not result.iloc[:6].rule_observation_ready.any()
    assert "score" not in result


def test_every_prefix_and_future_append_preserve_all_observations():
    frame = market(); complete = run(frame)
    for count in range(1, len(frame) + 1):
        pd.testing.assert_frame_equal(run(frame.iloc[:count]), complete.iloc[:count])
    future = pd.concat([frame, market([10000, 2, 99999]).set_axis(pd.bdate_range(frame.index[-1] + pd.Timedelta(days=1), periods=3))])
    pd.testing.assert_frame_equal(run(future).iloc[:len(frame)], complete)


def test_second_trough_is_unknown_until_next_close_and_geometry_is_not_entry():
    prefix = run(market(BASE[:11]))
    assert prefix.iloc[-1].pattern_confirmed_at is None and not prefix.entry_rule_match.any()
    geometry = run(market(BASE[:12]))
    assert geometry.iloc[-1].pattern_state == "candidate" and not geometry.entry_rule_match.any()


def test_confirmation_day_can_itself_cross_without_backdating():
    values = BASE[:11] + [111, 112]
    result = run(market(values))
    assert result.index[result.signal == 1].tolist() == [result.index[11]]
    assert result.iloc[11].pattern_second_trough_at == result.index[10].date()
    assert result.iloc[11].pattern_confirmed_at == result.index[11].date()


def test_neckline_equality_is_no_entry_then_equal_after_entry_is_hold():
    result = run(market(BASE[:12] + [110, 111, 110, 109]))
    assert result.iloc[12].signal == 0 and result.iloc[13].signal == 1
    assert result.iloc[14].signal == 0 and result.iloc[15].signal == -1


@pytest.mark.parametrize("second,expected", [("105", True), ("105.0001", False), ("95", True), ("94.9999", False)])
def test_five_percent_tolerance_uses_first_trough_exact_boundary(second, expected):
    # 避免候選在確認後因floor失效；只核第二谷確認當天有無幾何。
    values = [120, 118, 116, 112, 108, 104, 100, 108, 112, 110, second, 108]
    result = run(market(values))
    assert (result.iloc[-1].pattern_state == "candidate") is expected


@pytest.mark.parametrize("neck,expected", [("101", False), ("101.0001", True)])
def test_neckline_must_exceed_both_troughs_by_strict_one_percent(neck, expected):
    values = [120, 118, 116, 112, 108, 104, 100, "100.5", neck, "100.5", 100, "100.5"]
    result = run(market(values))
    assert (result.iloc[-1].pattern_state == "candidate") is expected


def test_equal_neckline_tie_uses_earliest_date():
    result = run(market(BASE[:8] + [110, 110, 101, 106, 111]))
    assert result.iloc[-1].pattern_neckline_at == result.index[8].date()


def test_plateau_bottom_is_not_a_strict_trough():
    result = run(market(BASE[:10] + [101, 101, 106, 111]))
    assert not result.entry_rule_match.any() and result.iloc[-1].pattern_confirmed_at is None


def test_missing_predecline_is_not_skipped_and_non_decline_is_rejected():
    assert not run(market(BASE[5:])).entry_rule_match.any()
    values = [90, 92, 94, 96, 98, 104] + BASE[6:]
    assert not run(market(values)).entry_rule_match.any()


@pytest.mark.parametrize("gap,expected", [(2, False), (3, True), (20, True), (21, False)])
def test_only_consecutive_troughs_with_three_to_twenty_row_separation(gap, expected):
    between = [Decimal(110)] * (gap - 1)
    values = BASE[:7] + between + [101, 106, 111]
    result = run(market(values))
    assert bool(result.entry_rule_match.any()) is expected


def test_intervening_confirmed_trough_cannot_be_skipped_for_prettier_geometry():
    values = BASE[:7] + [110, 90, 110, 101, 106, 111]
    result = run(market(values))
    assert not result.entry_rule_match.any()


@pytest.mark.parametrize("wait", [5, 10, 20])
def test_expiry_equal_boundary_allows_cross_one_later_rejects(wait):
    exact = run(market(BASE[:12] + [106] * (wait - 1) + [111]), wait=wait)
    assert exact.iloc[-1].signal == 1
    late = run(market(BASE[:12] + [106] * wait + [111]), wait=wait)
    assert late.iloc[-1].signal == 0 and late.iloc[-1].reason_tags == "candidate_expired"


def test_floor_equality_does_not_invalidate_but_lower_close_restarts_without_entry():
    equal = run(market(BASE[:12] + [100]))
    assert equal.iloc[-1].pattern_state == "candidate"
    lower = run(market(BASE[:12] + [99, 111]))
    assert lower.iloc[-2].reason_tags == "candidate_below_floor"
    assert not lower.entry_rule_match.any()


def test_first_candidate_stays_frozen_when_new_troughs_arrive():
    result = run(market(BASE[:12] + [102, 108, 103, 107, 111]))
    assert result.iloc[-1].signal == 1
    assert result.iloc[-1].pattern_second_trough_at == result.index[10].date()
    assert result.iloc[-1].pattern_neckline == Decimal("110")


@pytest.mark.parametrize("column", ["Open", "High", "Low", "Close"])
def test_missing_ohlc_clears_unentered_candidate_without_bfill(column):
    frame = market(BASE[:12] + [106, 111])
    frame.loc[frame.index[12], column] = None
    before = frame.copy(deep=True)
    result = run(frame)
    assert not result.entry_rule_match.any()
    assert not result.iloc[12].rule_observation_ready
    assert result.iloc[12].reason_tags == "missing_ohlc_reset_geometry"
    pd.testing.assert_frame_equal(frame, before)


def test_missing_after_intent_preserves_frozen_neckline_for_later_exit_only():
    result = run(market(BASE[:13] + [None, 110, 109]))
    assert result.iloc[12].signal == 1
    assert result.iloc[13].signal == 0 and not result.iloc[13].rule_observation_ready
    assert result.iloc[13].pattern_neckline == Decimal("110")
    assert result.iloc[14].signal == 0 and result.iloc[15].signal == -1


def test_episode_is_not_assumed_fill_and_suppresses_repeated_entries():
    frame = market(BASE[:13] + [114, 113, 115, 112, 116, 109, 108])
    frame["Volume"] = 0
    result = run(frame)
    assert int(result.entry_rule_match.sum()) == int(result.exit_rule_match.sum()) == 1
    trades, equity = BrokerSimulator(BrokerConfig(execution_price="next_open")).run(result, Decimal("1000000"))
    assert trades == [] and equity["position"].eq(0).all()
    assert not result.attrs["rule_diagnostics"].get("filled_positions")


def test_original_broker_uses_next_open_not_signal_close_and_no_terminal_fill():
    frame = market(); result = run(frame)
    broker = BrokerSimulator(BrokerConfig(execution_price="next_open", fee_bps=0, slippage_bps=0))
    trades, equity = broker.run(result, Decimal("1000000"))
    assert [(item.type, item.date) for item in trades] == [("buy", frame.index[13]), ("sell", frame.index[16])]
    assert Decimal(str(trades[0].price)) == Decimal("114")
    assert Decimal(str(trades[1].price)) == Decimal("108")
    pending = run(market(BASE[:13]))
    assert BrokerSimulator(BrokerConfig(execution_price="next_open")).run(pending, Decimal("1000000"))[0] == []
    assert equity.index.equals(frame.index)


def test_original_limit_guard_delays_entry_and_preserves_original_signal_time():
    frame = market()
    frame.loc[frame.index[13], ["Open", "High"]] = [Decimal("130"), Decimal("131")]
    result = run(frame)
    broker = BrokerSimulator(BrokerConfig(execution_price="next_open", fee_bps=0, slippage_bps=0))
    trades, _ = broker.run(result, Decimal("1000000"))
    assert trades[0].date == frame.index[14]
    filled = next(item for item in broker.execution_diagnostics if item["status"] == "filled")
    assert filled["signal_time"] == frame.index[12].isoformat()
    assert filled["execution_time"] == frame.index[14].isoformat()


def test_filled_position_stays_open_at_end_without_inventing_terminal_sell():
    frame = market(BASE[:15]); result = run(frame)
    trades, equity = BrokerSimulator(BrokerConfig(execution_price="next_open")).run(result, Decimal("1000000"))
    assert [(item.type, item.date) for item in trades] == [("buy", frame.index[13])]
    assert equity.iloc[-1]["position"] > 0
    assert result.iloc[-1].pattern_state == "intent_episode" and result.iloc[-1].signal == 0


@pytest.mark.parametrize("start_index", [6, 11, 12, 13])
def test_test_start_clears_prior_geometry_candidate_and_episode(start_index):
    frame = market()
    result = run(frame, start=frame.index[start_index].strftime("%Y-%m-%d"))
    assert not result.signal.any()
    assert not result.iloc[:start_index].rule_observation_ready.any()
    assert all(item == "context_only_no_order" for item in result.iloc[:start_index].reason_tags)


def test_decimal_context_cannot_change_border_or_saved_evidence_values():
    frame = market(); expected = run(frame)
    with localcontext() as context:
        context.prec = 2
        actual = run(frame)
    pd.testing.assert_frame_equal(actual, expected)


def test_caller_rounding_exponent_limits_and_flags_are_isolated():
    frame = market(); expected = run(frame)
    with localcontext() as context:
        context.prec = 2; context.rounding = ROUND_DOWN
        context.Emax = 2; context.Emin = -2; context.clamp = 1
        context.traps[Overflow] = True
        original_flags = dict(context.flags)
        actual = run(frame)
        assert (context.prec, context.rounding, context.Emax, context.Emin, context.clamp) == (2, ROUND_DOWN, 2, -2, 1)
        assert context.flags == original_flags
    pd.testing.assert_frame_equal(actual, expected)


@pytest.mark.parametrize("params", [{"max_wait_sessions": True}, {"max_wait_sessions": 1},
    {"max_wait_sessions": "5.0"}, {"buy_score": 60}, None])
def test_unknown_or_ambiguous_parameters_refused(params):
    with pytest.raises(ValueError):
        rule_definition(params)


@pytest.mark.parametrize("wait", [5, 10, 20, "5", "10", "20"])
def test_explicit_ui_integer_text_is_canonical(wait):
    assert wait_sessions({"max_wait_sessions": wait}) == int(wait)


@pytest.mark.parametrize("change", ["duplicate", "reverse", "intraday", "timezone", "volume", "negative", "inconsistent"])
def test_ambiguous_daily_source_and_invalid_prices_refused(change):
    frame = market()
    if change == "duplicate": frame.index = pd.DatetimeIndex([frame.index[0]] * len(frame))
    if change == "reverse": frame = frame.iloc[::-1]
    if change == "intraday": frame.index = frame.index + pd.Timedelta(hours=1)
    if change == "timezone": frame.index = frame.index.tz_localize("Asia/Taipei")
    if change == "volume": frame = frame.drop(columns=["Volume"])
    if change == "negative": frame.loc[frame.index[6], "Low"] = Decimal(0)
    if change == "inconsistent": frame.loc[frame.index[6], "High"] = Decimal(1)
    with pytest.raises(ValueError):
        run(frame)


def test_numeric_yyyymmdd_uses_existing_explicit_date_boundary_and_does_not_mutate_input():
    frame = market().reset_index(names="日期")
    frame["日期"] = frame["日期"].dt.strftime("%Y%m%d").astype(int)
    before = frame.copy(deep=True)
    result = run(frame)
    assert result.index[0] == pd.Timestamp("2026-01-02")
    assert result.index[result.signal == 1].tolist() == [market().index[12]]
    pd.testing.assert_frame_equal(frame, before)


def test_spec_mutation_after_creation_does_not_silently_change_executor_rules():
    spec = selected(); executor = BaldrWBottomExecutor(spec)
    spec.config["params"]["max_wait_sessions"] = 5
    with pytest.raises(ValueError, match="規格已變動"):
        executor.generate_signals(market(), spec)


@pytest.mark.parametrize("value", ["Infinity", "0", "-1", True, "0.0000000000001", "12345678901234567890123456789"])
def test_precision_contract_refuses_nonpositive_nonfinite_or_unsupported_price(value):
    with pytest.raises(ValueError):
        price_decimal(value)


def test_positive_exponent_within_twenty_eight_price_digits_is_allowed():
    assert price_decimal("1E-12") == Decimal("0.000000000001")
    assert price_decimal("1E+27") == Decimal("1000000000000000000000000000")
    with pytest.raises(ValueError):
        price_decimal("1E+28")


def test_new_core_has_no_bare_float_literals_or_float_conversion_calls():
    root = Path(__file__).resolve().parents[1]
    for name in ("analysis_module/pattern_analysis/causal_w_bottom.py",
                 "decision_module/strategies/baldr_w_bottom_contract.py",
                 "decision_module/strategies/baldr_w_bottom_executor.py"):
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        assert not any(isinstance(node, ast.Constant) and type(node.value) is float for node in ast.walk(tree)), name
        assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                       and node.func.id == "float" for node in ast.walk(tree)), name


def test_kernel_refuses_nond_decimal_or_nonincreasing_dates():
    with pytest.raises(ValueError):
        observe_w_bottom([(date(2026, 1, 1), 100)])
    with pytest.raises(ValueError):
        observe_w_bottom([(date(2026, 1, 1), Decimal(100))] * 2)


def test_wait_sensitivity_records_signal_counts_without_performance_selection(tmp_path):
    frame = market(BASE[:12] + [106] * 7 + [111])
    records = [{"max_wait_sessions": wait, "entry_intents": int(run(frame, wait=wait).entry_rule_match.sum())}
               for wait in (5, 10, 20)]
    assert records == [{"max_wait_sessions": 5, "entry_intents": 0},
                       {"max_wait_sessions": 10, "entry_intents": 1},
                       {"max_wait_sessions": 20, "entry_intents": 1}]
    (tmp_path / "w_bottom_sensitivity.json").write_text(json.dumps({
        "fixture": "delayed_neckline_cross", "results": records, "chosen_by_performance": False}), encoding="utf-8")
