"""具名布林研究策略的因果、成交與原Registry保存；僅隔離合成行情。"""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal, localcontext
import json

import pandas as pd
import pytest

from app_module.backtest_service import BacktestService
from app_module.registered_strategy_spec import registered_strategy_spec
from app_module.research_run_service import ResearchRunService
from app_module.saved_strategy_rule_card import load_saved_strategy_rule_card
from app_module.strategy_rule_card_readmodel import read_strategy_rule_card, read_single_backtest_execution_rule_card
from data_module.config import TWStockConfig
from decision_module.strategies.baldr_bollinger_contract import STRATEGY_ID, EXECUTION_SCHEMA
from decision_module.strategies.baldr_bollinger_executor import BaldrBollingerExecutor
from decision_module.strategies.registry import StrategyRegistry
from ui_qt.views.backtest.research_run_metadata import build_single_backtest_metadata, execute_single_backtest_with_rule_source
from tests.test_single_backtest_rule_execution_v2 import executed_v2_case


def market(closes=None):
    closes = closes if closes is not None else [100] * 40 + [160, 180, 200, 190, 100, 95] + [100] * 38
    index = pd.bdate_range("2026-01-02", periods=len(closes))
    return pd.DataFrame({"Open": closes, "High": [value + 1 for value in closes],
                         "Low": [value - 1 for value in closes], "Close": closes,
                         "Volume": [1_000_000] * len(closes)}, index=index)


def spec(confirm=1):
    return registered_strategy_spec(STRATEGY_ID, config={"params": {"entry_confirm_sessions": confirm}})


def test_new_registry_spec_and_complete_pre_execution_rule_card():
    selected = spec("1")
    assert selected.strategy_version == "1.0.0"
    card = read_strategy_rule_card(selected)
    assert not card.reasons and not card.missing
    assert card.rule_status == "specified_research_hypothesis"
    assert card.field("entry").value["cross"].startswith("previous_close <=")
    assert card.field("exit").value == {"condition": "close < middle", "equal_middle": "hold"}
    assert card.field("qualification").value["historical_pit_eligible"] is False


@pytest.mark.parametrize("confirm", [1, 2, 3])
def test_actual_bands_emit_confirmed_cross_once_and_middle_exit(confirm):
    selected = spec(confirm)
    result = BaldrBollingerExecutor(selected).generate_signals(market(), selected)
    assert result.index[result.signal == 1].tolist() == [result.index[39 + confirm]]
    assert result.iloc[44].signal == -1
    assert not result.iloc[:29].rule_observation_ready.any()
    assert not result.iloc[:40].entry_rule_match.any()
    assert "score" not in result


def test_equal_upper_is_not_cross_and_equal_middle_is_not_exit():
    selected = spec()
    result = BaldrBollingerExecutor(selected).generate_signals(market([100] * 60), selected)
    assert not result.signal.any()
    assert result.iloc[29:].rule_observation_ready.all()


def test_every_prefix_and_future_append_preserve_original_signal_and_bands():
    frame = market(); selected = spec(2)
    complete = BaldrBollingerExecutor(selected).generate_signals(frame, selected)
    columns = ["upperband", "middleband", "signal", "entry_rule_match", "exit_rule_match", "rule_observation_ready"]
    for count in range(1, len(frame) + 1):
        prefix = BaldrBollingerExecutor(selected).generate_signals(frame.iloc[:count], selected)
        pd.testing.assert_frame_equal(prefix[columns], complete.iloc[:count][columns])
    later = market([100] * len(frame) + [1000, 10, 2000])
    later.iloc[:len(frame)] = frame
    appended = BaldrBollingerExecutor(selected).generate_signals(later, selected)
    pd.testing.assert_frame_equal(appended.iloc[:len(frame)][columns], complete[columns])


def test_missing_ohlc_resets_warmup_and_cannot_be_filled_from_future():
    frame = market(); frame.loc[frame.index[39], "High"] = None
    frame["upperband"] = 1; frame["middleband"] = 1
    selected = spec()
    result = BaldrBollingerExecutor(selected).generate_signals(frame, selected)
    assert not result.iloc[39:69].rule_observation_ready.any()
    assert not result.iloc[39:69].signal.any()
    assert result.iloc[40].upperband != 1
    assert pd.isna(result.iloc[40].upperband)


def test_test_window_does_not_inherit_training_cross_confirmation():
    frame = market(); selected = spec(2)
    result = BaldrBollingerExecutor(selected).generate_signals(frame, selected,
        execution_start_date=frame.index[41].strftime("%Y-%m-%d"))
    assert not (result.signal == 1).any()
    assert not result.iloc[:41].signal.any()


@pytest.mark.parametrize("params", [{"entry_confirm_sessions": True}, {"entry_confirm_sessions": 0},
    {"entry_confirm_sessions": 4}, {"buy_score": 60}, {"entry_confirm_sessions": "1.0"}])
def test_invalid_or_score_parameters_rejected(params):
    selected = replace(spec(), config={"params": params})
    with pytest.raises(ValueError):
        BaldrBollingerExecutor(selected)


def test_decimal_caller_context_cannot_change_comparison_signals():
    selected = spec(); frame = market()
    baseline = BaldrBollingerExecutor(selected).generate_signals(frame, selected)
    with localcontext() as context:
        context.prec = 2
        actual = BaldrBollingerExecutor(selected).generate_signals(frame, selected)
    pd.testing.assert_series_equal(actual.signal, baseline.signal)


def saved_bollinger_case(tmp_path, monkeypatch, confirm=1):
    _, _, _, original_request, _, _ = executed_v2_case(tmp_path / "old", monkeypatch, "stable_conservative_v1")
    frame = market(); selected = spec(confirm)
    request = replace(original_request, strategy_id=STRATEGY_ID, strategy_spec=selected,
        strategy_params=selected.config["params"], start_date=frame.index[0].strftime("%Y-%m-%d"),
        end_date=frame.index[-1].strftime("%Y-%m-%d"))
    service = BacktestService(config=None)
    loads = []
    def load(*args):
        loads.append(args)
        return frame.copy(), request.start_date, request.end_date
    monkeypatch.setattr(service, "_load_stock_data", load)
    report = execute_single_backtest_with_rule_source(request, service)
    assert len(loads) == 1
    assert report.details["execution_contract"] == "next-session-open.v2"
    metadata = build_single_backtest_metadata(run_id="bollinger-executed", run_name="隔離布林原執行",
        notes="", params=request.run_params(), details=report.details, report=report, created_at="2026-10-16T01:00:00")
    registry = ResearchRunService(TWStockConfig(data_root=tmp_path / "data", output_root=tmp_path / "output"))
    metadata = registry.save_run(metadata, report.details["equity_curve"], report.details["trade_list"])
    return request, report, registry, metadata


def test_original_broker_fills_next_open_and_saved_signals_reopen_without_executor(tmp_path, monkeypatch):
    request, report, registry, metadata = saved_bollinger_case(tmp_path, monkeypatch)
    execution = metadata.data_manifest["single_backtest_rule_execution"]
    assert execution["schema"] == EXECUTION_SCHEMA
    assert metadata.parameter_contract_version == "baldr-bollinger-basic.v1"
    assert len(execution["signals"]) == len(market())
    assert execution["signals"][40]["signal"] == 1
    assert report.details["score_diagnostics"] == {}
    assert report.details["factor_records"] == []
    assert report.details["execution_summary"]["trade_count"] >= 2
    assert report.total_trades == 1
    # 原漲跌停守衛拒絕兩個超限開盤，保留原委託至第三個有效開盤。
    assert pd.Timestamp(report.details["trade_list"].iloc[0]["進場日期"]) == market().index[43]
    assert pd.Timestamp(report.details["trade_list"].iloc[0]["出場日期"]) == market().index[45]
    def forbidden(*_a, **_kw):
        raise AssertionError("保存reader不可查目前Registry或重跑executor")
    monkeypatch.setattr(StrategyRegistry, "get_executor", forbidden)
    monkeypatch.setattr(StrategyRegistry, "get_strategy_meta", forbidden)
    monkeypatch.setattr(BaldrBollingerExecutor, "generate_signals", forbidden)
    card = load_saved_strategy_rule_card(registry, metadata)
    assert not card.reasons and not card.rule_card.missing
    assert card.source_status == "source_ref_only" and card.performance_status == "not_evaluable"
    assert card.rule_card.field("source_trace").value["signal_sessions"] == len(market())


@pytest.mark.parametrize("change", ["future_qualification", "performance_qualification", "input_context", "rules", "sources", "signal", "unknown_signal"])
def test_saved_rule_cross_binding_rejects_changed_evidence(tmp_path, monkeypatch, change):
    _, _, _, metadata = saved_bollinger_case(tmp_path, monkeypatch)
    execution = deepcopy(metadata.data_manifest["single_backtest_rule_execution"])
    if change == "future_qualification": execution["qualification"]["historical_pit_eligible"] = True
    if change == "performance_qualification": execution["qualification"]["performance_evaluable"] = True
    if change == "input_context": execution["input_context"]["prior_rows"] = 999
    if change == "rules": execution["rules"]["entry"]["confirmation_sessions"] = 3
    if change == "sources": execution["source_hashes"] = {}
    if change == "signal": execution["signals"][40]["signal"] = 0
    if change == "unknown_signal": execution["signals"][0]["signal"] = 1
    from decision_module.strategies.contracts import StrategySpec
    stored_spec = StrategySpec.from_dict(metadata.data_manifest["strategy_spec"])
    card = read_single_backtest_execution_rule_card(stored_spec, execution)
    assert card.reasons and card.rule_status == "not_evaluable"
    if change in ("future_qualification", "performance_qualification"):
        assert "execution_rule_qualification_invalid" in card.reasons
    if change == "input_context":
        assert "execution_rule_input_context_invalid" in card.reasons


def test_confirmation_sensitivity_is_saved_as_signal_counts_not_selected_performance(tmp_path):
    counts = []
    for confirm in (1, 2, 3):
        selected = spec(confirm)
        short = market([100] * 40 + [160, 100, 100] + [100] * 35)
        result = BaldrBollingerExecutor(selected).generate_signals(short, selected)
        counts.append({"confirmation_sessions": confirm, "entry_intents": int((result.signal == 1).sum())})
    assert counts == [{"confirmation_sessions": 1, "entry_intents": 1},
                      {"confirmation_sessions": 2, "entry_intents": 0},
                      {"confirmation_sessions": 3, "entry_intents": 0}]
    (tmp_path / "sensitivity.json").write_text(json.dumps({"fixture": "single_false_break",
        "results": counts, "chosen_by_performance": False}), encoding="utf-8")


def test_nonpositive_future_ohlc_is_rejected_by_original_indicator_guard():
    frame = market([100] * 40 + [1])
    selected = spec()
    with pytest.raises(ValueError, match="OHLC 含非正價格"):
        BaldrBollingerExecutor(selected).generate_signals(frame, selected)


@pytest.mark.parametrize("override", [{"execution_price": "close"}, {"allow_pyramid": True},
    {"stop_loss_atr_mult": Decimal("2")}, {"take_profit_atr_mult": Decimal("3")}])
def test_unsupported_execution_route_refused_before_load(tmp_path, monkeypatch, override):
    request, _, _, _ = saved_bollinger_case(tmp_path, monkeypatch)
    service = BacktestService(config=None)
    def unexpected(*args):
        raise AssertionError("不支持路由不可先讀資料或執行")
    monkeypatch.setattr(service, "_load_stock_data", unexpected)
    with pytest.raises(ValueError, match="布林基礎研究"):
        execute_single_backtest_with_rule_source(replace(request, **override), service)


def test_explicit_no_limit_fixture_fills_first_next_open_never_signal_close(tmp_path, monkeypatch):
    request, _, _, _ = saved_bollinger_case(tmp_path, monkeypatch)
    frame = market(); service = BacktestService(config=None)
    monkeypatch.setattr(service, "_load_stock_data", lambda *_args: (frame.copy(), request.start_date, request.end_date))
    report = execute_single_backtest_with_rule_source(replace(request, enable_limit=False), service)
    assert pd.Timestamp(report.details["trade_list"].iloc[0]["進場日期"]) == frame.index[41]
    assert pd.Timestamp(report.details["trade_list"].iloc[0]["出場日期"]) == frame.index[45]
    assert report.details["data_manifest"]["single_backtest_rule_execution"]["broker_config"]["enable_limit_up_down"] is False


@pytest.mark.parametrize("start_index,confirm,first_signal", [(40, 1, 1), (41, 2, 0)])
def test_normal_producer_uses_bounded_pretest_context_without_training_orders(
        tmp_path, monkeypatch, start_index, confirm, first_signal):
    request, _, _, _ = saved_bollinger_case(tmp_path, monkeypatch)
    selected = spec(confirm)
    frame = market(); start = frame.index[start_index].strftime("%Y-%m-%d")
    request = replace(request, start_date=start, strategy_spec=selected, strategy_params=selected.config["params"])
    service = BacktestService(config=None); loads = []
    def load(*args):
        loads.append(args)
        return frame.copy(), frame.index[0].strftime("%Y-%m-%d"), request.end_date
    monkeypatch.setattr(service, "_load_stock_data", load)
    report = execute_single_backtest_with_rule_source(request, service)
    expected_start = (pd.Timestamp(start) - pd.Timedelta(days=180)).strftime("%Y-%m-%d")
    assert loads == [(request.stock_code, expected_start, request.end_date)]
    execution = report.details["data_manifest"]["single_backtest_rule_execution"]
    assert execution["input_context"]["prior_rows"] == 31
    assert execution["input_context"]["start_date"] == frame.index[start_index - 31].strftime("%Y-%m-%d")
    assert execution["start_date"] == report.details["start_date"] == start
    assert execution["signals"][0]["date"] == start and execution["signals"][0]["ready"] is True
    assert execution["signals"][0]["signal"] == first_signal
    assert len(execution["signals"]) == len(frame) - start_index
    assert report.details["equity_curve"].index.min() >= pd.Timestamp(start)
    assert report.details["rule_diagnostics"]["total_sessions"] == len(frame) - start_index
    assert report.details["rule_diagnostics"]["entry_signal_sessions"] == first_signal


@pytest.mark.parametrize("change", ["duplicate", "reverse", "intraday", "timezone", "missing_volume"])
def test_ambiguous_daily_source_is_rejected(change):
    frame = market()
    if change == "duplicate": frame.index = pd.DatetimeIndex([frame.index[0]] * len(frame))
    if change == "reverse": frame = frame.iloc[::-1]
    if change == "intraday": frame.index = frame.index + pd.Timedelta(hours=1)
    if change == "timezone": frame.index = frame.index.tz_localize("Asia/Taipei")
    if change == "missing_volume": frame = frame.drop(columns=["Volume"])
    selected = spec()
    with pytest.raises(ValueError):
        BaldrBollingerExecutor(selected).generate_signals(frame, selected)


def test_cancellation_before_input_load_never_publishes_execution(tmp_path, monkeypatch):
    request, _, _, _ = saved_bollinger_case(tmp_path, monkeypatch)
    service = BacktestService(config=None)
    def forbidden(*args):
        raise AssertionError("取消前不應載入行情")
    monkeypatch.setattr(service, "_load_stock_data", forbidden)
    with pytest.raises(InterruptedError, match="回測已取消"):
        execute_single_backtest_with_rule_source(request, service, check_cancel=lambda: True)


def test_research_strategy_cannot_take_promotion_credit_from_sop_alone(tmp_path, monkeypatch):
    from app_module.promotion_reconciliation_service import PromotionPreflightError, PromotionReconciliationService
    from app_module.strategy_version_service import StrategyVersionService
    request, _, registry, metadata = saved_bollinger_case(tmp_path, monkeypatch)
    reconciliation = PromotionReconciliationService(research_repository=registry.repository,
        strategy_version_service=StrategyVersionService(registry.config))
    with pytest.raises(PromotionPreflightError, match="研究假說"):
        reconciliation.promote_registry_run(metadata.run_id)
    assert reconciliation.strategy_version_service.list_versions() == []
    service = BacktestService(config=None); frame = market()
    monkeypatch.setattr(service, "_load_stock_data", lambda *_a: (frame.copy(), request.start_date, request.end_date))
    original = service.sop_validator.validate_backtest_result
    def sop_alone(**kwargs):
        result = original(**kwargs)
        result["can_promote"] = True
        return result
    monkeypatch.setattr(service.sop_validator, "validate_backtest_result", sop_alone)
    report = request.execute(service)
    assert report.details["can_promote"] is False
    assert "研究假說" in report.details["promotion_blocker"]
