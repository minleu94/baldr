"""P07沿真executor／Broker／Registry保存、拒錯與唯讀重開。"""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal

import pandas as pd
import pytest

from app_module.backtest_service import BacktestService
from app_module.bollinger_squeeze_rule_card import SOURCE_KEYS
from app_module.registered_strategy_spec import registered_strategy_spec
from app_module.research_run_service import ResearchRunService
from app_module.saved_strategy_rule_card import load_saved_strategy_rule_card
from app_module.strategy_rule_card_readmodel import read_single_backtest_execution_rule_card, read_strategy_rule_card
from data_module.config import TWStockConfig
from decision_module.strategies.baldr_bollinger_squeeze_contract import STRATEGY_ID, EXECUTION_SCHEMA
from decision_module.strategies.baldr_bollinger_squeeze_executor import BaldrBollingerSqueezeExecutor
from decision_module.strategies.registry import StrategyRegistry
from tests.test_baldr_bollinger_squeeze_executor import frame
from ui_qt.views.backtest.execution_coordinator import BacktestExecutionRequest
from ui_qt.views.backtest.research_run_metadata import build_single_backtest_metadata, execute_single_backtest_with_rule_source


def market():
    # 原最後90元開盤在跌停邊界不可假定能賣；保留它，再提供下一有效開盤。
    return frame([100] * 65 + [120, 121, 122, 119, 115, 100, 90, 91, 92],
                 [100000] * 65 + [200000] * 9)


def request_for(data, *, start=None):
    selected = registered_strategy_spec(STRATEGY_ID, config={"params": {}})
    return BacktestExecutionRequest(stock_code="2330", start_date=start or data.index[0].date().isoformat(),
        end_date=data.index[-1].date().isoformat(), strategy_id=STRATEGY_ID, strategy_spec=selected,
        strategy_params={}, capital=1000000, fee_bps=Decimal("14.25"), slippage_bps=Decimal("5"),
        execution_price="next_open", stop_loss_pct=None, take_profit_pct=None, stop_loss_atr_mult=None, take_profit_atr_mult=None,
        sizing_mode="all_in", fixed_amount=None, risk_pct=None, max_positions=1, position_sizing="equal_weight",
        allow_pyramid=False, allow_reentry=True, reentry_cooldown_days=0, enable_limit=True, enable_volume=True,
        max_participation=Decimal("0.05"))


def saved_case(tmp_path, monkeypatch, *, with_prefix=False):
    data = market()
    request = request_for(data, start=data.index[65].date().isoformat() if with_prefix else None)
    service = BacktestService(config=None)
    loads = []
    def load(code, start, end):
        loads.append((code, start, end))
        selected = data.loc[(data.index >= start) & (data.index <= end)].copy(deep=True)
        return selected, selected.index[0].date().isoformat(), selected.index[-1].date().isoformat()
    monkeypatch.setattr(service, "_load_stock_data", load)
    report = execute_single_backtest_with_rule_source(request, service)
    assert len(loads) == 1
    metadata = build_single_backtest_metadata(run_id="squeeze-actual", run_name="帶寬隔離研究", notes="",
        params=request.run_params(), details=report.details, report=report, created_at="2026-10-17T09:00:00")
    registry = ResearchRunService(TWStockConfig(data_root=tmp_path / "data", output_root=tmp_path / "output"))
    metadata = registry.save_run(metadata, report.details["equity_curve"], report.details["trade_list"])
    return request, report, registry, metadata


def test_registered_rule_actual_save_and_read_without_current_executor(tmp_path, monkeypatch):
    selected = registered_strategy_spec(STRATEGY_ID, config={"params": {}})
    card = read_strategy_rule_card(selected)
    assert not card.reasons and not card.missing
    assert card.field("entry").value["setup"] == "previous_squeeze_is_true"
    request, report, registry, metadata = saved_case(tmp_path, monkeypatch)
    execution = metadata.data_manifest["single_backtest_rule_execution"]
    assert execution["schema"] == EXECUTION_SCHEMA and set(execution["source_hashes"]) == SOURCE_KEYS
    assert execution["input_context"]["max_prior_rows"] == 50
    assert metadata.parameter_contract_version == "baldr-bollinger-squeeze.v1"
    assert report.details["score_diagnostics"] == {} and report.details["factor_records"] == []
    assert report.details["rule_diagnostics"]["entry_signal_sessions"] == 1
    assert report.total_trades == 1 and report.details["can_promote"] is False
    from ui_qt.views.backtest.presenter import format_backtest_summary
    summary = format_backtest_summary(report)
    assert "--- 布林帶寬低點突破診斷 ---" in summary and "帶寬突破進場意圖: 1 列" in summary
    assert "策略分數診斷" not in summary and "確認所需交易日" not in summary
    rows = execution["signals"]
    entry = next(row for row in rows if row["entry"])
    exit_row = next(row for row in rows if row["exit"] and row["date"] > entry["date"])
    assert entry["previous_squeeze"] is True
    dates = market().index
    trades = report.details["trade_list"]
    assert pd.Timestamp(trades.iloc[0]["進場日期"]) == dates[dates.get_loc(pd.Timestamp(entry["date"])) + 1]
    assert pd.Timestamp(trades.iloc[0]["出場日期"]) == dates[dates.get_loc(pd.Timestamp(exit_row["date"])) + 2]
    def forbidden(*_a, **_kw):
        raise AssertionError("保存reader不可重算、查目前規則或另存")
    monkeypatch.setattr(StrategyRegistry, "get_executor", forbidden)
    monkeypatch.setattr(StrategyRegistry, "get_strategy_meta", forbidden)
    monkeypatch.setattr(BaldrBollingerSqueezeExecutor, "generate_signals", forbidden)
    monkeypatch.setattr(ResearchRunService, "save_run", forbidden)
    reopened = load_saved_strategy_rule_card(registry, metadata)
    assert not reopened.reasons and not reopened.rule_card.missing
    assert reopened.source_status == "source_ref_only" and reopened.performance_status == "not_evaluable"
    assert reopened.rule_card.field("source_trace").value["signal_sessions"] == len(market())


def test_prefix_context_is_bounded_and_first_execution_signal_uses_prior_squeeze(tmp_path, monkeypatch):
    request, report, _, metadata = saved_case(tmp_path, monkeypatch, with_prefix=True)
    execution = metadata.data_manifest["single_backtest_rule_execution"]
    assert execution["input_context"]["prior_rows"] == 50
    assert execution["input_context"]["start_date"] < request.start_date
    assert execution["start_date"] == request.start_date == metadata.start_date
    assert execution["signals"][0]["signal"] == 1
    assert all(row["date"] >= request.start_date for row in execution["signals"])


@pytest.mark.parametrize("change", ["rules", "sources", "fingerprint", "executor", "version", "contract", "width",
    "previous_squeeze", "previous_link", "entry", "unknown", "bool_signal", "date", "context", "runtime", "pit", "performance", "schema", "volume"])
def test_saved_evidence_rejects_changed_rule_source_and_signal(tmp_path, monkeypatch, change):
    _, _, _, metadata = saved_case(tmp_path, monkeypatch)
    execution = deepcopy(metadata.data_manifest["single_backtest_rule_execution"])
    entry = next(row for row in execution["signals"] if row["entry"])
    if change == "rules": execution["rules"]["contraction"]["window"] = 10
    if change == "sources": execution["source_hashes"].pop(next(iter(SOURCE_KEYS)))
    if change == "fingerprint": execution["input_fingerprint"] = "sha256:" + "f" * 64
    if change == "executor": execution["executor"]["window"] = 10
    if change == "version": execution["registry_metadata"]["strategy_version"] = "1.0.1"
    if change == "contract": execution["broker_config"]["execution_price"] = "close"
    if change == "width": entry["band_width"] = "10000"
    if change == "previous_squeeze": entry["previous_squeeze"] = False
    if change == "previous_link": entry["previous_close"] = "1"; entry["previous_upper"] = "2"
    if change == "entry": entry["entry"] = False; entry["signal"] = 0
    if change == "unknown": execution["signals"][0]["signal"] = 1
    if change == "bool_signal": entry["signal"] = True
    if change == "date": entry["date"] = execution["signals"][0]["date"]
    if change == "context": execution["input_context"]["max_prior_rows"] = 51
    if change == "runtime": execution["analysis_runtime"].pop("talib")
    if change == "pit": execution["qualification"]["historical_pit_eligible"] = True
    if change == "performance": execution["qualification"]["performance_evaluable"] = True
    if change == "schema": execution["schema"] = "single-backtest-bollinger-execution.v1"
    if change == "volume": entry["observed_volume"] = "0"
    selected = metadata.data_manifest["strategy_spec"]
    from decision_module.strategies.contracts import StrategySpec
    card = read_single_backtest_execution_rule_card(StrategySpec.from_dict(selected), execution)
    assert card.reasons and card.rule_status == "not_evaluable"


@pytest.mark.parametrize("change", ["stock_code", "fee_bps", "capital", "start_date", "strategy_params"])
def test_save_rejects_display_params_changed_after_execution(tmp_path, monkeypatch, change):
    request, report, _, _ = saved_case(tmp_path, monkeypatch)
    params = request.run_params()
    params[change] = {"stock_code": "2317", "fee_bps": Decimal(0), "capital": 1,
                      "start_date": "2026-01-01", "strategy_params": {"window": 10}}[change]
    with pytest.raises(ValueError, match="來源輸入不一致"):
        build_single_backtest_metadata(run_id="changed", run_name="", notes="", params=params,
            details=report.details, report=report, created_at="2026-10-17T09:00:00")


@pytest.mark.parametrize("change,value", [("execution_price", "close"), ("allow_pyramid", True),
                                        ("stop_loss_atr_mult", Decimal(2)), ("take_profit_atr_mult", Decimal(3))])
def test_unsupported_execution_rejected_before_loading(change, value, monkeypatch):
    request = replace(request_for(frame()), **{change: value})
    service = BacktestService(config=None)
    def forbidden(*_a, **_kw):
        raise AssertionError("拒絕未核路由前不能讀行情")
    monkeypatch.setattr(service, "_load_stock_data", forbidden)
    with pytest.raises(ValueError, match="next_open"):
        execute_single_backtest_with_rule_source(request, service)


@pytest.mark.parametrize("point", ["before_load", "after_engine"])
def test_cancel_does_not_publish_completed_rule_source(monkeypatch, point):
    data = frame()
    request = request_for(data)
    service = BacktestService(config=None)
    state = {"cancelled": point == "before_load", "loads": 0, "reports": []}
    def load(*_args):
        state["loads"] += 1
        assert not state["cancelled"]
        return data.copy(deep=True), request.start_date, request.end_date
    monkeypatch.setattr(service, "_load_stock_data", load)
    original = service.run_backtest
    def finish_then_cancel(**kwargs):
        report = original(**kwargs)
        state["reports"].append(report)
        state["cancelled"] = True
        return report
    monkeypatch.setattr(service, "run_backtest", finish_then_cancel)
    with pytest.raises(InterruptedError, match="取消"):
        execute_single_backtest_with_rule_source(request, service, check_cancel=lambda: state["cancelled"])
    assert state["loads"] == (0 if point == "before_load" else 1)
    assert all("single_backtest_rule_execution" not in report.details for report in state["reports"])


def test_batch_refuses_before_worker_or_data_loading():
    from app_module.batch_backtest_service import BatchBacktestService
    service = BatchBacktestService(BacktestService(config=None))
    with pytest.raises(ValueError, match="正常單股"):
        service.run_batch_backtest(["2330", "2317"], "2025-01-02", "2025-12-31", spec_for_batch())


def spec_for_batch():
    return registered_strategy_spec(STRATEGY_ID, config={"params": {}})


@pytest.mark.parametrize("mode", ["optimization", "train_test", "walkforward"])
def test_public_unaccepted_modes_reject_before_market_load_or_grid(monkeypatch, mode):
    from app_module.optimizer_service import OptimizerService
    from app_module.walkforward_service import WalkForwardService
    service = BacktestService(config=None)
    def forbidden(*_a, **_kw):
        pytest.fail("未接受模式不得讀行情、產生參數網格或執行")
    monkeypatch.setattr(service, "_load_stock_data", forbidden)
    monkeypatch.setattr(service, "run_backtest", forbidden)
    with pytest.raises(ValueError, match="正常單股"):
        if mode == "optimization":
            optimizer = OptimizerService(service, max_workers=1)
            monkeypatch.setattr(optimizer, "generate_param_grid", forbidden)
            optimizer.grid_search("2330", "2025-01-02", "2025-12-31", STRATEGY_ID, {}, {})
        else:
            operation = getattr(WalkForwardService(service), "train_test_split" if mode == "train_test" else "walk_forward")
            operation("2330", "2025-01-02", "2025-12-31", spec_for_batch())
