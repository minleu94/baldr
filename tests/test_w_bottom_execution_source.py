"""W底沿原正常producer／Broker／Registry保存；合成行情不授資料或績效資格。"""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pandas as pd

import pytest

from app_module.backtest_service import BacktestService
from app_module.registered_strategy_spec import registered_strategy_spec
from app_module.research_run_service import ResearchRunService
from app_module.saved_strategy_rule_card import load_saved_strategy_rule_card
from app_module.strategy_rule_card_readmodel import read_strategy_rule_card, read_single_backtest_execution_rule_card
from app_module.w_bottom_rule_card import SOURCE_KEYS
from data_module.config import TWStockConfig
from decision_module.strategies.baldr_w_bottom_contract import STRATEGY_ID, EXECUTION_SCHEMA
from decision_module.strategies.baldr_w_bottom_executor import BaldrWBottomExecutor
from decision_module.strategies.contracts import StrategySpec
from decision_module.strategies.registry import StrategyRegistry
from tests.test_baldr_completion_p07_w_bottom import market
from ui_qt.views.backtest.execution_coordinator import BacktestExecutionRequest
from ui_qt.views.backtest.research_run_metadata import build_single_backtest_metadata, execute_single_backtest_with_rule_source


def request_for(frame, wait=20):
    selected = registered_strategy_spec(STRATEGY_ID, config={"params": {"max_wait_sessions": wait}})
    return BacktestExecutionRequest(stock_code="2330", start_date=frame.index[0].strftime("%Y-%m-%d"),
        end_date=frame.index[-1].strftime("%Y-%m-%d"), strategy_id=STRATEGY_ID, strategy_spec=selected,
        strategy_params=selected.config["params"], capital=1000000, fee_bps=Decimal("14.25"), slippage_bps=Decimal("5"),
        execution_price="next_open", stop_loss_pct=None, take_profit_pct=None, stop_loss_atr_mult=None, take_profit_atr_mult=None,
        sizing_mode="all_in", fixed_amount=None, risk_pct=None, max_positions=1, position_sizing="equal_weight",
        allow_pyramid=False, allow_reentry=True, reentry_cooldown_days=0, enable_limit=True, enable_volume=True,
        max_participation=Decimal("0.05"))


def saved_case(tmp_path, monkeypatch):
    frame = market(); request = request_for(frame); service = BacktestService(config=None); loads = []
    def load(*args):
        loads.append(args)
        return frame.copy(deep=True), request.start_date, request.end_date
    monkeypatch.setattr(service, "_load_stock_data", load)
    report = execute_single_backtest_with_rule_source(request, service)
    assert loads == [(request.stock_code, request.start_date, request.end_date)]
    metadata = build_single_backtest_metadata(run_id="w-bottom-actual", run_name="W底隔離研究", notes="",
        params=request.run_params(), details=report.details, report=report, created_at="2026-10-16T03:00:00")
    registry = ResearchRunService(TWStockConfig(data_root=tmp_path / "data", output_root=tmp_path / "output"))
    metadata = registry.save_run(metadata, report.details["equity_curve"], report.details["trade_list"])
    return request, report, registry, metadata


def test_registered_spec_has_complete_w_bottom_card_without_bollinger_features():
    request = request_for(market())
    card = read_strategy_rule_card(request.strategy_spec)
    assert not card.reasons and not card.missing
    assert card.rule_status == "specified_research_hypothesis"
    assert card.field("entry").value["max_wait_sessions"] == 20
    assert card.field("exit").value["condition"] == "close < entry_episode_frozen_neckline"
    assert "causal_BBANDS30_2_SMA" not in card.field("required_features").value
    assert card.field("qualification").value["performance_evaluable"] is False


def test_original_normal_producer_saves_actual_confirmed_signals_and_reopens_without_executor(tmp_path, monkeypatch):
    request, report, registry, metadata = saved_case(tmp_path, monkeypatch)
    execution = metadata.data_manifest["single_backtest_rule_execution"]
    assert execution["schema"] == EXECUTION_SCHEMA and set(execution["source_hashes"]) == SOURCE_KEYS
    assert execution["input_context"] == {"prior_rows": 0, "start_date": request.start_date, "end_date": request.end_date,
                                           "state_policy": "test_window_reset_all_geometry_candidate_episode"}
    assert metadata.parameter_contract_version == "baldr-w-bottom-basic.v1"
    assert report.details["score_diagnostics"] == {} and report.details["factor_records"] == []
    assert report.details["rule_diagnostics"]["entry_signal_sessions"] == 1
    rows = execution["signals"]
    assert len(rows) == len(market()) and rows[12]["signal"] == 1 and rows[15]["signal"] == -1
    assert rows[12]["evidence"]["confirmed_at"] == market().index[11].strftime("%Y-%m-%d")
    assert rows[12]["evidence"]["second_trough_at"] == market().index[10].strftime("%Y-%m-%d")
    assert report.total_trades == 1 and report.details["can_promote"] is False
    def forbidden(*_a, **_kw):
        raise AssertionError("保存reader不可讀目前Registry、重算或保存")
    monkeypatch.setattr(StrategyRegistry, "get_executor", forbidden)
    monkeypatch.setattr(StrategyRegistry, "get_strategy_meta", forbidden)
    monkeypatch.setattr(BaldrWBottomExecutor, "generate_signals", forbidden)
    monkeypatch.setattr(ResearchRunService, "save_run", forbidden)
    card = load_saved_strategy_rule_card(registry, metadata)
    assert not card.reasons and not card.rule_card.missing
    assert card.source_status == "source_ref_only" and card.performance_status == "not_evaluable"
    assert card.rule_card.field("source_trace").value["signal_sessions"] == len(market())


@pytest.mark.parametrize("change", ["rules", "sources", "fingerprint", "executor", "source_version", "contract",
    "past_confirmation", "future_confirmation", "neck_price", "episode_changed", "entry_signal", "unknown_signal",
    "bool_signal", "duplicate_date", "input_context", "runtime", "qualification", "performance", "bollinger_schema"])
def test_saved_w_evidence_cross_binding_rejects_changed_fields(tmp_path, monkeypatch, change):
    _, _, _, metadata = saved_case(tmp_path, monkeypatch)
    execution = deepcopy(metadata.data_manifest["single_backtest_rule_execution"])
    if change == "rules": execution["rules"]["entry"]["max_wait_sessions"] = 5
    if change == "sources": execution["source_hashes"].pop(next(iter(SOURCE_KEYS)))
    if change == "fingerprint": execution["input_fingerprint"] = "sha256:" + "f" * 64
    if change == "executor": execution["executor"]["max_wait_sessions"] = 10
    if change == "source_version": execution["registry_metadata"]["strategy_version"] = "1.0.1"
    if change == "contract": execution["broker_config"]["execution_price"] = "close"
    if change == "past_confirmation": execution["signals"][12]["evidence"]["confirmed_at"] = execution["signals"][10]["date"]
    if change == "future_confirmation": execution["signals"][12]["evidence"]["confirmed_at"] = execution["signals"][13]["date"]
    if change == "neck_price": execution["signals"][12]["evidence"]["neckline"] = "109"
    if change == "episode_changed": execution["signals"][13]["evidence"]["confirmed_at"] = execution["signals"][12]["date"]
    if change == "entry_signal": execution["signals"][12]["signal"] = 0
    if change == "unknown_signal": execution["signals"][0]["signal"] = 1
    if change == "bool_signal": execution["signals"][12]["signal"] = True
    if change == "duplicate_date": execution["signals"][12]["date"] = execution["signals"][11]["date"]
    if change == "input_context": execution["input_context"]["prior_rows"] = 31
    if change == "runtime": execution["analysis_runtime"] = {"talib": "not_used"}
    if change == "qualification": execution["qualification"]["historical_pit_eligible"] = True
    if change == "performance": execution["qualification"]["performance_evaluable"] = True
    if change == "bollinger_schema": execution["schema"] = "single-backtest-bollinger-execution.v1"
    stored_spec = StrategySpec.from_dict(metadata.data_manifest["strategy_spec"])
    card = read_single_backtest_execution_rule_card(stored_spec, execution)
    assert card.reasons and card.rule_status == "not_evaluable"


@pytest.mark.parametrize("override", [{"execution_price": "close"}, {"allow_pyramid": True},
    {"stop_loss_atr_mult": Decimal("2")}, {"take_profit_atr_mult": Decimal("3")}])
def test_unaccepted_route_refused_before_loading_by_wrapper_and_direct_service(monkeypatch, override):
    service = BacktestService(config=None)
    def forbidden(*_a):
        raise AssertionError("拒絕路由不可先讀資料")
    monkeypatch.setattr(service, "_load_stock_data", forbidden)
    request = replace(request_for(market()), **override)
    with pytest.raises(ValueError, match="W底基礎研究"):
        execute_single_backtest_with_rule_source(request, service)
    with pytest.raises(ValueError, match="W底基礎研究"):
        request.execute(service)


def test_cancel_before_or_after_run_does_not_publish_full_rule_source(monkeypatch):
    service = BacktestService(config=None); frame = market(); request = request_for(frame)
    def forbidden(*_a):
        raise AssertionError("預先取消不可先讀行情")
    monkeypatch.setattr(service, "_load_stock_data", forbidden)
    with pytest.raises(InterruptedError):
        execute_single_backtest_with_rule_source(request, service, check_cancel=lambda: True)
    monkeypatch.setattr(service, "_load_stock_data", lambda *_a: (frame.copy(), request.start_date, request.end_date))
    original = service.run_backtest; completed = []
    def run_then_cancel(**kwargs):
        completed.append(original(**kwargs))
        return completed[-1]
    monkeypatch.setattr(service, "run_backtest", run_then_cancel)
    with pytest.raises(InterruptedError, match="不發布完整規則來源"):
        execute_single_backtest_with_rule_source(request, service, check_cancel=lambda: bool(completed))
    assert "single_backtest_rule_execution" not in completed[-1].details.get("data_manifest", {})


def test_research_w_cannot_promote_even_if_sop_returns_true(tmp_path, monkeypatch):
    from app_module.promotion_reconciliation_service import PromotionPreflightError, PromotionReconciliationService
    from app_module.strategy_version_service import StrategyVersionService
    request, _, registry, metadata = saved_case(tmp_path, monkeypatch)
    reconciliation = PromotionReconciliationService(research_repository=registry.repository,
        strategy_version_service=StrategyVersionService(registry.config))
    with pytest.raises(PromotionPreflightError, match="研究假說"):
        reconciliation.promote_registry_run(metadata.run_id)
    assert reconciliation.strategy_version_service.list_versions() == []
    service = BacktestService(config=None); frame = market()
    monkeypatch.setattr(service, "_load_stock_data", lambda *_a: (frame.copy(), request.start_date, request.end_date))
    original = service.sop_validator.validate_backtest_result
    def sop_alone(**kwargs):
        result = original(**kwargs); result["can_promote"] = True
        return result
    monkeypatch.setattr(service.sop_validator, "validate_backtest_result", sop_alone)
    report = request.execute(service)
    assert report.details["can_promote"] is False and "研究假說" in report.details["promotion_blocker"]


@pytest.mark.parametrize("key,value", [("stock_code", "2454"), ("strategy_id", "stable_conservative_v1"),
    ("capital", 2000000), ("fee_bps", Decimal("99")), ("strategy_params", {"max_wait_sessions": 5}),
    ("start_date", "2026-01-01"), ("end_date", "2026-02-01"), ("allow_pyramid", True), ("enable_limit", False)])
def test_metadata_builder_rejects_detached_inputs_even_with_valid_execution(tmp_path, monkeypatch, key, value):
    request, report, _, _ = saved_case(tmp_path, monkeypatch)
    params = deepcopy(request.run_params()); params[key] = value
    with pytest.raises(ValueError, match="來源輸入不一致"):
        build_single_backtest_metadata(run_id="detached", run_name="不可保存", notes="", params=params,
            details=report.details, report=report, created_at="2026-10-16T03:00:00")


def test_source_finalize_cancel_does_not_return_complete_execution(tmp_path, monkeypatch):
    request, _, _, _ = saved_case(tmp_path, monkeypatch)
    frame = market(); service = BacktestService(config=None); cancelled = []
    monkeypatch.setattr(service, "_load_stock_data", lambda *_a: (frame.copy(), request.start_date, request.end_date))
    original = Path.read_bytes
    def read_then_cancel(path):
        value = original(path)
        if path.name == "units.py" and path.parent.name == "financial_module":
            cancelled.append(True)
        return value
    monkeypatch.setattr(Path, "read_bytes", read_then_cancel)
    with pytest.raises(InterruptedError, match="不發布完整規則來源"):
        execute_single_backtest_with_rule_source(request, service, check_cancel=lambda: bool(cancelled))


def test_actual_window_is_saved_while_requested_bounds_remain_in_original_input(tmp_path, monkeypatch):
    frame = market()
    request = request_for(frame)
    request = replace(request, start_date=(frame.index[0] - pd.Timedelta(days=2)).strftime("%Y-%m-%d"),
                      end_date=(frame.index[-1] + pd.Timedelta(days=2)).strftime("%Y-%m-%d"))
    service = BacktestService(config=None)
    actual_start, actual_end = (frame.index[0].strftime("%Y-%m-%d"), frame.index[-1].strftime("%Y-%m-%d"))
    monkeypatch.setattr(service, "_load_stock_data", lambda *_a: (frame.copy(), actual_start, actual_end))
    report = execute_single_backtest_with_rule_source(request, service)
    metadata = build_single_backtest_metadata(run_id="adjusted", run_name="實際研究窗", notes="", params=request.run_params(),
        details=report.details, report=report, created_at="2026-10-16T03:00:00")
    assert (metadata.start_date, metadata.end_date) == (actual_start, actual_end)
    assert metadata.original_input["raw_params"]["start_date"] == request.start_date
    assert metadata.original_input["raw_params"]["end_date"] == request.end_date
    registry = ResearchRunService(TWStockConfig(data_root=tmp_path / "data", output_root=tmp_path / "output"))
    metadata = registry.save_run(metadata, report.details["equity_curve"], report.details["trade_list"])
    assert not load_saved_strategy_rule_card(registry, metadata).reasons
