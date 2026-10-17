"""三段收縮沿真Broker保存／讀回與原輸入綁定，市場I/O用隔離fixture。"""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal

import pandas as pd
import pytest

from app_module.backtest_service import BacktestService
from app_module.registered_strategy_spec import registered_strategy_spec
from app_module.research_run_service import ResearchRunService
from app_module.saved_strategy_rule_card import load_saved_strategy_rule_card
from app_module.strategy_rule_card_readmodel import read_single_backtest_execution_rule_card, read_strategy_rule_card
from app_module.vcp_rule_card import SOURCE_KEYS
from data_module.config import TWStockConfig
from decision_module.strategies.baldr_vcp_contract import STRATEGY_ID, EXECUTION_SCHEMA
from decision_module.strategies.baldr_vcp_executor import BaldrVCPExecutor
from decision_module.strategies.registry import StrategyRegistry
from tests.test_baldr_vcp_executor import fixture_frame
from ui_qt.views.backtest.execution_coordinator import BacktestExecutionRequest
from ui_qt.views.backtest.research_run_metadata import build_single_backtest_metadata, execute_single_backtest_with_rule_source


def market():
    data = fixture_frame()
    suffix = pd.DataFrame({"Open": [134, 110, 111], "High": [135, 111, 112], "Low": [133, 109, 110],
                           "Close": [134, 110, 111], "Volume": [1000000] * 3},
                          index=pd.bdate_range(data.index[-1] + pd.Timedelta(days=1), periods=3))
    return pd.concat([data, suffix])


def request_for(data, *, start=None):
    selected = registered_strategy_spec(STRATEGY_ID, config={"params": {}})
    return BacktestExecutionRequest(stock_code="2330", start_date=start or data.index[0].date().isoformat(),
        end_date=data.index[-1].date().isoformat(), strategy_id=STRATEGY_ID, strategy_spec=selected,
        strategy_params={}, capital=1000000, fee_bps=Decimal("14.25"), slippage_bps=Decimal("5"),
        execution_price="next_open", stop_loss_pct=None, take_profit_pct=None, stop_loss_atr_mult=None, take_profit_atr_mult=None,
        sizing_mode="all_in", fixed_amount=None, risk_pct=None, max_positions=1, position_sizing="equal_weight",
        allow_pyramid=False, allow_reentry=True, reentry_cooldown_days=0, enable_limit=True, enable_volume=True,
        max_participation=Decimal("0.05"))


def executed(data, monkeypatch, *, start=None):
    request = request_for(data, start=start)
    service = BacktestService(config=None)
    loads = []
    def load(code, first, last):
        loads.append((code, first, last))
        selected = data.loc[(data.index >= first) & (data.index <= last)].copy(deep=True)
        return selected, selected.index[0].date().isoformat(), selected.index[-1].date().isoformat()
    monkeypatch.setattr(service, "_load_stock_data", load)
    report = execute_single_backtest_with_rule_source(request, service)
    return request, report, loads


def saved_case(tmp_path, monkeypatch):
    request, report, loads = executed(market(), monkeypatch)
    metadata = build_single_backtest_metadata(run_id="vcp-actual", run_name="三段收縮隔離研究", notes="",
        params=request.run_params(), details=report.details, report=report, created_at="2026-10-17T12:00:00")
    registry = ResearchRunService(TWStockConfig(data_root=tmp_path / "data", output_root=tmp_path / "output"))
    metadata = registry.save_run(metadata, report.details["equity_curve"], report.details["trade_list"])
    assert len(loads) == 1
    return request, report, registry, metadata


def test_registered_execution_save_and_reopen_without_current_executor(tmp_path, monkeypatch):
    spec = registered_strategy_spec(STRATEGY_ID, config={"params": {}})
    card = read_strategy_rule_card(spec)
    assert not card.reasons and not card.missing
    assert card.field("entry").value["base"]["last_depth_max_bp"] == 800
    request, report, registry, metadata = saved_case(tmp_path, monkeypatch)
    execution = metadata.data_manifest["single_backtest_rule_execution"]
    assert execution["schema"] == EXECUTION_SCHEMA and set(execution["source_hashes"]) == SOURCE_KEYS
    assert execution["input_context"]["max_prior_rows"] == 160
    assert execution["input_context"]["lookback_calendar_days"] == 365
    assert metadata.parameter_contract_version == "baldr-vcp-three-contractions.v1"
    assert report.total_trades >= 1 and report.details["can_promote"] is False
    assert report.details["score_diagnostics"] == {} and report.details["factor_records"] == []
    assert report.details["rule_diagnostics"]["entry_signal_sessions"] == 1
    from ui_qt.views.backtest.presenter import format_backtest_summary
    summary = format_backtest_summary(report)
    assert "--- 三段轉折收縮診斷 ---" in summary and "三段收縮突破進場意圖: 1 列" in summary
    assert "策略分數診斷" not in summary
    entry = next(row for row in execution["signals"] if row["entry"])
    first_fill = pd.Timestamp(report.details["trade_list"].iloc[0]["進場日期"])
    assert first_fill > pd.Timestamp(entry["date"])
    def forbidden(*args, **kwargs):
        raise AssertionError("保存reader不可重跑或改查目前Registry")
    monkeypatch.setattr(StrategyRegistry, "get_executor", forbidden)
    monkeypatch.setattr(StrategyRegistry, "get_strategy_meta", forbidden)
    monkeypatch.setattr(BaldrVCPExecutor, "generate_signals", forbidden)
    monkeypatch.setattr(ResearchRunService, "save_run", forbidden)
    reopened = load_saved_strategy_rule_card(registry, metadata)
    assert not reopened.reasons and not reopened.rule_card.missing
    assert reopened.source_status == "source_ref_only" and reopened.performance_status == "not_evaluable"
    assert reopened.rule_card.field("source_trace").value["signal_sessions"] == len(market())


@pytest.mark.parametrize("offset", [104, 106])
def test_bounded_context_keeps_original_and_consumed_breakout_state(monkeypatch, offset):
    data = pd.concat([fixture_frame().iloc[:80]] * 3 + [market()], ignore_index=True)
    data.index = pd.bdate_range("2024-01-02", periods=len(data))
    start = data.index[240 + offset].date().isoformat()
    request, report, loads = executed(data, monkeypatch, start=start)
    execution = report.details["data_manifest"]["single_backtest_rule_execution"]
    assert len(loads) == 1 and execution["input_context"]["prior_rows"] == 160
    whole = BaldrVCPExecutor(request.strategy_spec).generate_signals(data, request.strategy_spec, execution_start_date=start)
    selected = whole.loc[whole.index >= start]
    assert [row["signal"] for row in execution["signals"]] == selected["signal"].tolist()
    assert [row["pattern_already_consumed"] for row in execution["signals"]] == selected["pattern_already_consumed"].tolist()
    assert not read_single_backtest_execution_rule_card(
        type(request.strategy_spec).from_dict(execution["strategy_spec"]), execution).reasons


@pytest.mark.parametrize("change", ["future_confirmation", "ma", "previous_close", "quantity", "source", "consumed", "context", "pivot_price", "pullback_volume"])
def test_saved_evidence_tampering_does_not_bind_a_rule(tmp_path, monkeypatch, change):
    _, _, _, metadata = saved_case(tmp_path, monkeypatch)
    execution = deepcopy(metadata.data_manifest["single_backtest_rule_execution"])
    row = next(item for item in execution["signals"] if item["entry"])
    if change == "future_confirmation":
        row["evidence"]["pivots"][-1]["confirmed_position"] = row["position"] + 1
    elif change == "ma":
        row["ma20"] = "1"
    elif change == "previous_close":
        row["previous_close"] = "1"
    elif change == "quantity":
        row["volume_sum20"] = "1"
    elif change == "source":
        execution["source_hashes"].pop(next(iter(execution["source_hashes"])))
    elif change == "consumed":
        row["pattern_already_consumed"] = True
    elif change == "pivot_price":
        row["evidence"]["pivots"][-1]["price"] = "118"
    elif change == "pullback_volume":
        row["evidence"]["last_pullback_volume_sum"] = "1"
    else:
        execution["input_context"]["max_prior_rows"] = 50
    assert read_single_backtest_execution_rule_card(
        type(request_for(market()).strategy_spec).from_dict(execution["strategy_spec"]), execution).reasons


@pytest.mark.parametrize("change", ["fee_bps", "capital", "strategy_params"])
def test_saving_cannot_change_the_original_financial_inputs(tmp_path, monkeypatch, change):
    request, report, _, _ = saved_case(tmp_path, monkeypatch)
    params = request.run_params()
    params[change] = {"other": 1} if change == "strategy_params" else Decimal("1")
    with pytest.raises(ValueError):
        build_single_backtest_metadata(run_id="changed", run_name="錯配", notes="", params=params,
                                       details=report.details, report=report, created_at="2026-10-17T12:00:00")


def test_cancel_and_unsupported_execution_reject_before_loading(monkeypatch):
    service = BacktestService(config=None)
    monkeypatch.setattr(service, "_load_stock_data", lambda *args: pytest.fail("拒絕前不可載入行情"))
    request = request_for(market())
    with pytest.raises(InterruptedError):
        execute_single_backtest_with_rule_source(request, service, check_cancel=lambda: True)
    with pytest.raises(ValueError):
        execute_single_backtest_with_rule_source(replace(request, execution_price="close"), service)


@pytest.mark.parametrize("mode", ["batch", "optimization", "train_test", "walkforward"])
def test_unaccepted_public_modes_stop_before_market_or_grid(monkeypatch, mode):
    from app_module.batch_backtest_service import BatchBacktestService
    from app_module.optimizer_service import OptimizerService
    from app_module.walkforward_service import WalkForwardService
    service = BacktestService(config=None)
    def forbidden(*args, **kwargs):
        pytest.fail("未接受模式不可載入行情、產生網格或執行")
    monkeypatch.setattr(service, "_load_stock_data", forbidden)
    monkeypatch.setattr(service, "run_backtest", forbidden)
    with pytest.raises(ValueError, match="正常單股"):
        if mode == "batch":
            BatchBacktestService(service).run_batch_backtest(["2330"], "2025-01-02", "2025-12-31", request_for(market()).strategy_spec)
        elif mode == "optimization":
            optimizer = OptimizerService(service, max_workers=1)
            monkeypatch.setattr(optimizer, "generate_param_grid", forbidden)
            optimizer.grid_search("2330", "2025-01-02", "2025-12-31", STRATEGY_ID, {}, {})
        else:
            operation = getattr(WalkForwardService(service), "train_test_split" if mode == "train_test" else "walk_forward")
            operation("2330", "2025-01-02", "2025-12-31", request_for(market()).strategy_spec)
