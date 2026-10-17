"""四均線沿原撮合／producer／Registry保存，不用目前規則補歷史。"""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal

import pandas as pd
import pytest

from app_module.backtest_service import BacktestService
from app_module.registered_strategy_spec import registered_strategy_spec
from app_module.research_run_service import ResearchRunService
from app_module.saved_strategy_rule_card import load_saved_strategy_rule_card
from app_module.strategy_rule_card_readmodel import read_strategy_rule_card, read_single_backtest_execution_rule_card
from app_module.ma_alignment_rule_card import SOURCE_KEYS
from data_module.config import TWStockConfig
from decision_module.strategies.baldr_ma_alignment_contract import STRATEGY_ID, EXECUTION_SCHEMA
from decision_module.strategies.baldr_ma_alignment_executor import BaldrMAAlignmentExecutor
from decision_module.strategies.contracts import StrategySpec
from decision_module.strategies.registry import StrategyRegistry
from tests.test_baldr_ma_alignment_executor import frame
from ui_qt.views.backtest.execution_coordinator import BacktestExecutionRequest
from ui_qt.views.backtest.research_run_metadata import build_single_backtest_metadata, execute_single_backtest_with_rule_source


def market():
    return frame(list(range(100, 180)) + list(range(180, 100, -1))
                 + list(range(100, 220)) + list(range(220, 100, -1)))


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
    request = request_for(data, start=data.index[180].date().isoformat() if with_prefix else None)
    service = BacktestService(config=None)
    loads = []
    def load(code, start, end):
        loads.append((code, start, end))
        selected = data.loc[(data.index >= start) & (data.index <= end)].copy(deep=True)
        return selected, selected.index[0].date().isoformat(), selected.index[-1].date().isoformat()
    monkeypatch.setattr(service, "_load_stock_data", load)
    report = execute_single_backtest_with_rule_source(request, service)
    assert len(loads) == 1
    metadata = build_single_backtest_metadata(run_id="ma-alignment-actual", run_name="四均線隔離研究", notes="",
        params=request.run_params(), details=report.details, report=report, created_at="2026-10-17T06:00:00")
    registry = ResearchRunService(TWStockConfig(data_root=tmp_path / "data", output_root=tmp_path / "output"))
    metadata = registry.save_run(metadata, report.details["equity_curve"], report.details["trade_list"])
    return request, report, registry, metadata


def test_registered_rule_card_and_actual_save_reopen_without_current_executor(tmp_path, monkeypatch):
    selected = registered_strategy_spec(STRATEGY_ID, config={"params": {}})
    card = read_strategy_rule_card(selected)
    assert not card.reasons and not card.missing
    assert card.field("entry").value["alignment"] == "MA5 > MA10 > MA20 > MA60"
    request, report, registry, metadata = saved_case(tmp_path, monkeypatch)
    execution = metadata.data_manifest["single_backtest_rule_execution"]
    assert execution["schema"] == EXECUTION_SCHEMA and set(execution["source_hashes"]) == SOURCE_KEYS
    assert execution["input_context"]["prior_rows"] == 0 and execution["input_context"]["max_prior_rows"] == 61
    assert metadata.parameter_contract_version == "baldr-ma-alignment-basic.v1"
    assert report.details["score_diagnostics"] == {} and report.details["factor_records"] == []
    assert report.details["rule_diagnostics"]["entry_signal_sessions"] == 1
    assert report.total_trades == 1 and report.details["can_promote"] is False
    from ui_qt.views.backtest.presenter import format_backtest_summary
    summary = format_backtest_summary(report)
    assert "--- 四均線規則診斷 ---" in summary and "新排列進場意圖: 1 列" in summary
    assert "策略分數診斷" not in summary and "確認所需交易日" not in summary
    rows = execution["signals"]
    assert len(rows) == len(market())
    entry = next(row for row in rows if row["entry"])
    assert entry["previous_alignment"] is False
    exit_row = next(row for row in rows if row["exit"] and row["date"] > entry["date"])
    dates = market().index
    trades = report.details["trade_list"]
    assert pd.Timestamp(trades.iloc[0]["進場日期"]) == dates[dates.get_loc(pd.Timestamp(entry["date"])) + 1]
    assert pd.Timestamp(trades.iloc[0]["出場日期"]) == dates[dates.get_loc(pd.Timestamp(exit_row["date"])) + 1]
    assert all(row["signal"] == 0 for row in rows[:59])
    def forbidden(*_a, **_kw):
        raise AssertionError("保存reader不可重算、讀目前規則或另存")
    monkeypatch.setattr(StrategyRegistry, "get_executor", forbidden)
    monkeypatch.setattr(StrategyRegistry, "get_strategy_meta", forbidden)
    monkeypatch.setattr(BaldrMAAlignmentExecutor, "generate_signals", forbidden)
    monkeypatch.setattr(ResearchRunService, "save_run", forbidden)
    reopened = load_saved_strategy_rule_card(registry, metadata)
    assert not reopened.reasons and not reopened.rule_card.missing
    assert reopened.source_status == "source_ref_only" and reopened.performance_status == "not_evaluable"
    assert reopened.rule_card.field("source_trace").value["signal_sessions"] == len(market())


def test_prefix_context_is_bounded_and_not_counted_as_execution(tmp_path, monkeypatch):
    request, report, _, metadata = saved_case(tmp_path, monkeypatch, with_prefix=True)
    execution = metadata.data_manifest["single_backtest_rule_execution"]
    assert execution["input_context"]["prior_rows"] == 61
    assert execution["input_context"]["start_date"] < request.start_date
    assert execution["start_date"] == request.start_date == report.details["start_date"]
    expected = BaldrMAAlignmentExecutor(request.strategy_spec).generate_signals(market(), request.strategy_spec)
    assert [row["signal"] for row in execution["signals"]] == expected.loc[expected.index >= request.start_date, "signal"].tolist()
    assert all(row["date"] >= request.start_date for row in execution["signals"])


@pytest.mark.parametrize("change", ["rules", "sources", "fingerprint", "executor", "version", "contract", "alignment",
    "previous_alignment", "entry", "unknown", "bool_signal", "date", "context", "runtime", "pit", "performance", "schema"])
def test_saved_evidence_rejects_changed_rule_source_and_signal(tmp_path, monkeypatch, change):
    _, _, _, metadata = saved_case(tmp_path, monkeypatch)
    execution = deepcopy(metadata.data_manifest["single_backtest_rule_execution"])
    entry = next(row for row in execution["signals"] if row["entry"])
    if change == "rules": execution["rules"]["indicator"]["periods"] = [5, 20]
    if change == "sources": execution["source_hashes"].pop(next(iter(SOURCE_KEYS)))
    if change == "fingerprint": execution["input_fingerprint"] = "sha256:" + "f" * 64
    if change == "executor": execution["executor"]["periods"] = [5, 10, 20, 30]
    if change == "version": execution["registry_metadata"]["strategy_version"] = "1.0.1"
    if change == "contract": execution["broker_config"]["execution_price"] = "close"
    if change == "alignment": entry["ma5"] = entry["ma10"]
    if change == "previous_alignment": entry["previous_alignment"] = True
    if change == "entry": entry["entry"] = False; entry["signal"] = 0
    if change == "unknown": execution["signals"][0]["signal"] = 1
    if change == "bool_signal": entry["signal"] = True
    if change == "date": entry["date"] = execution["signals"][0]["date"]
    if change == "context": execution["input_context"]["max_prior_rows"] = 31
    if change == "runtime": execution["analysis_runtime"] = {}
    if change == "pit": execution["qualification"]["historical_pit_eligible"] = True
    if change == "performance": execution["qualification"]["performance_evaluable"] = True
    if change == "schema": execution["schema"] = "single-backtest-bollinger-execution.v1"
    card = read_single_backtest_execution_rule_card(StrategySpec.from_dict(metadata.data_manifest["strategy_spec"]), execution)
    assert card.reasons and card.rule_status == "not_evaluable"


@pytest.mark.parametrize("override", [{"execution_price": "close"}, {"allow_pyramid": True},
    {"stop_loss_atr_mult": Decimal("2")}, {"take_profit_atr_mult": Decimal("3")}])
def test_unaccepted_execution_refuses_before_loading(monkeypatch, override):
    service = BacktestService(config=None)
    def forbidden(*_a):
        raise AssertionError("拒絕路由不可讀行情")
    monkeypatch.setattr(service, "_load_stock_data", forbidden)
    request = replace(request_for(market()), **override)
    with pytest.raises(ValueError, match="四均線基礎研究"):
        execute_single_backtest_with_rule_source(request, service)
    with pytest.raises(ValueError, match="四均線基礎研究"):
        request.execute(service)


def test_research_promotion_is_refused_even_with_passed_sop(tmp_path, monkeypatch):
    from app_module.promotion_reconciliation_service import PromotionPreflightError, PromotionReconciliationService
    from app_module.strategy_version_service import StrategyVersionService
    _, _, registry, metadata = saved_case(tmp_path, monkeypatch)
    reconciliation = PromotionReconciliationService(research_repository=registry.repository,
        strategy_version_service=StrategyVersionService(registry.config))
    with pytest.raises(PromotionPreflightError, match="研究假說"):
        reconciliation.promote_registry_run(metadata.run_id)
    assert reconciliation.strategy_version_service.list_versions() == []


@pytest.mark.parametrize("key,value", [("stock_code", "2454"), ("capital", 2000000), ("fee_bps", Decimal("99")),
    ("strategy_params", {"buy_score": 1}), ("start_date", "2024-01-01"), ("allow_pyramid", True)])
def test_metadata_refuses_detached_financial_inputs(tmp_path, monkeypatch, key, value):
    request, report, _, _ = saved_case(tmp_path, monkeypatch)
    params = request.run_params()
    params[key] = value
    with pytest.raises(ValueError, match="四均線研究來源輸入不一致"):
        build_single_backtest_metadata(run_id="detached", run_name="錯配", notes="", params=params,
            details=report.details, report=report, created_at="2026-10-17T06:00:00")


def test_invalid_diagnostics_do_not_fall_back_to_invented_score(tmp_path, monkeypatch):
    from ui_qt.views.backtest.presenter import format_backtest_summary
    _, report, _, _ = saved_case(tmp_path, monkeypatch)
    report.details["rule_diagnostics"]["ready_sessions"] = True
    summary = format_backtest_summary(report)
    assert "規則診斷不可用" in summary and "策略分數診斷" not in summary


@pytest.mark.parametrize("point", ["before_load", "after_engine"])
def test_cancel_does_not_publish_completed_rule_source(monkeypatch, point):
    data = market()
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
