"""計分1.1.0使用原producer／Broker／Registry，與1.0原件分版核對。"""
from copy import deepcopy
from dataclasses import replace

import pandas as pd
import pytest

from app_module.backtest_service import BacktestService
from app_module.basic_strategy_saved_pair import BasicStrategySavedPairReader, _preflight
from app_module.research_run_service import ResearchRunService
from app_module.saved_strategy_rule_card import load_saved_strategy_rule_card
from app_module.strategy_rule_card_readmodel import read_single_backtest_execution_rule_card
from data_module.config import TWStockConfig
from decision_module.strategies.contracts import StrategySpec
from decision_module.strategies.registry import StrategyRegistry
from tests.test_ma_alignment_execution_source import request_for
from tests.test_score_executor_causal_input_v11 import CASES, spec_for
from ui_qt.views.backtest.research_run_metadata import execute_single_backtest_with_rule_source, build_single_backtest_metadata


def market():
    return pd.DataFrame({"開盤價": [100] * 100, "最高價": [101] * 100, "最低價": [99] * 100,
        "收盤價": [100] * 100, "成交股數": [1000000] * 100,
        "RSI": [None] * 20 + [20] * 10 + [90] * 30 + [20] * 10 + [90] * 30},
        index=pd.bdate_range("2026-01-02", periods=100))


def saved_case(tmp_path, monkeypatch, strategy, *, version="1.1.0", run_id=None, unquoted_index=None):
    data = market()
    if unquoted_index is not None:
        data.loc[data.index[unquoted_index], ["開盤價", "最高價", "最低價", "收盤價"]] = None
        data.loc[data.index[unquoted_index], "成交股數"] = 0
    request = replace(request_for(data), strategy_id=strategy, strategy_spec=spec_for(strategy, version),
                      strategy_params=deepcopy(spec_for(strategy, version).config["params"]))
    service = BacktestService(config=None)
    monkeypatch.setattr(service, "_load_stock_data", lambda *_a: (data.copy(deep=True), request.start_date, request.end_date))
    report = execute_single_backtest_with_rule_source(request, service)
    identifier = run_id or strategy + "-" + version
    metadata = build_single_backtest_metadata(run_id=identifier, run_name="因果缺值研究", notes="",
        params=request.run_params(), details=report.details, report=report, created_at="2026-10-17T08:00:00")
    registry = ResearchRunService(TWStockConfig(profile="prod", data_root=tmp_path / "data", output_root=tmp_path / "output"))
    metadata = registry.save_run(metadata, report.details["equity_curve"], report.details["trade_list"])
    return request, report, registry, metadata


@pytest.mark.parametrize("strategy,cls", CASES)
def test_v3_actual_orders_save_and_reopen_without_current_executor(tmp_path, monkeypatch, strategy, cls):
    request, report, registry, metadata = saved_case(tmp_path, monkeypatch, strategy)
    execution = metadata.data_manifest["single_backtest_rule_execution"]
    assert execution["schema"] == "single-backtest-rule-execution.v3"
    assert len(execution["source_hashes"]) == 11
    assert execution["registry_metadata"].get("strategy_version", execution["registry_metadata"].get("version")) == "1.1.0"
    assert metadata.parameter_contract_version.endswith("-fixed.v2")
    assert len(execution["score_observations"]) == 100
    assert all(row == {"date": row["date"], "score": None, "score_bp": None, "ready": False, "signal": 0}
               for row in execution["score_observations"][:20])
    assert execution["score_observations"][20]["signal"] == 1
    assert pd.Timestamp(report.details["trade_list"].iloc[0]["進場日期"]) == market().index[21]
    assert report.details["can_promote"] is False
    from ui_qt.views.backtest.presenter import format_backtest_summary
    summary = format_backtest_summary(report)
    assert "可判讀得分: 80 / 100 天；缺值或暖機未知: 20 天。" in summary
    def forbidden(*_a, **_kw):
        raise AssertionError("保存reader不可重算、查目前executor或另存")
    monkeypatch.setattr(StrategyRegistry, "get_strategy_meta", forbidden)
    monkeypatch.setattr(StrategyRegistry, "get_executor", forbidden)
    monkeypatch.setattr(cls, "generate_signals", forbidden)
    monkeypatch.setattr(ResearchRunService, "save_run", forbidden)
    card = load_saved_strategy_rule_card(registry, metadata)
    assert not card.reasons and not card.rule_card.reasons and not card.rule_card.missing
    assert card.source_status == "source_ref_only" and card.performance_status == "not_evaluable"


@pytest.mark.parametrize("strategy,cls", CASES)
def test_old_v2_explicit_version_remains_loadable(tmp_path, monkeypatch, strategy, cls):
    _, report, registry, metadata = saved_case(tmp_path, monkeypatch, strategy, version="1.0.0")
    execution = metadata.data_manifest["single_backtest_rule_execution"]
    expected_version = "1.0" if strategy == "baseline_score_threshold" else "1.0.0"
    assert execution["schema"] == ("single-backtest-rule-execution.v1" if strategy == "baseline_score_threshold" else "single-backtest-rule-execution.v2")
    assert execution["registry_metadata"].get("strategy_version", execution["registry_metadata"].get("version")) == expected_version
    assert metadata.parameter_contract_version.endswith("-fixed.v1")
    assert "input_preparation" not in execution and "score_observations" not in execution
    assert not load_saved_strategy_rule_card(registry, metadata).reasons


@pytest.mark.parametrize("change", ["policy", "policy_version", "runtime", "source", "version", "unknown_zero",
                                    "unknown_order", "known_score", "bp_bool", "date", "schema", "qualification"])
def test_v3_saved_rule_refuses_mutated_evidence(tmp_path, monkeypatch, change):
    _, _, _, metadata = saved_case(tmp_path, monkeypatch, "stable_conservative_v1")
    execution = deepcopy(metadata.data_manifest["single_backtest_rule_execution"])
    if change == "policy": execution["input_preparation"]["indicators"] = "bfill"
    if change == "policy_version": execution["input_preparation"]["schema"] = "causal-score-input.v2"
    if change == "runtime": execution["analysis_runtime"] = {}
    if change == "source": execution["source_hashes"].pop(next(iter(execution["source_hashes"])))
    if change == "version": execution["registry_metadata"]["strategy_version"] = "1.0.0"
    if change == "unknown_zero": execution["score_observations"][0]["score"] = "0"
    if change == "unknown_order": execution["score_observations"][0]["signal"] = 1
    if change == "known_score": execution["score_observations"][20]["score"] = "99.99"
    if change == "bp_bool": execution["score_observations"][20]["score_bp"] = True
    if change == "date": execution["score_observations"][20]["date"] = execution["score_observations"][0]["date"]
    if change == "schema": execution["schema"] = "single-backtest-rule-execution.v2"
    if change == "qualification": execution["qualification"]["historical_pit_eligible"] = True
    card = read_single_backtest_execution_rule_card(StrategySpec.from_dict(metadata.data_manifest["strategy_spec"]), execution)
    assert card.reasons and card.rule_status == "not_evaluable"


def test_pair_keeps_same_method_version_and_blocks_cross_version(tmp_path, monkeypatch):
    _, _, _, stable = saved_case(tmp_path, monkeypatch, "stable_conservative_v1")
    _, _, _, momentum = saved_case(tmp_path, monkeypatch, "momentum_aggressive_v1")
    assert not _preflight((stable, momentum))
    _, _, _, old = saved_case(tmp_path, monkeypatch, "momentum_aggressive_v1", version="1.0.0")
    assert any("缺值方法版本不同" in reason for reason in _preflight((stable, old)))


@pytest.mark.parametrize("change", ["stock_code", "capital", "fee_bps", "strategy_params"])
def test_v3_metadata_does_not_save_other_financial_inputs(tmp_path, monkeypatch, change):
    request, report, _, _ = saved_case(tmp_path, monkeypatch, "stable_conservative_v1")
    params = request.run_params()
    params[change] = {"stock_code": "2454", "capital": 2000000, "fee_bps": 99, "strategy_params": {"buy_score": 1}}[change]
    with pytest.raises(ValueError, match="因果計分1.1.0研究來源輸入不一致"):
        build_single_backtest_metadata(run_id="bad", run_name="錯配", notes="", params=params,
            details=report.details, report=report, created_at="2026-10-17T08:00:00")


@pytest.mark.parametrize("strategy,cls", CASES)
@pytest.mark.parametrize("mode", ["close", "quantile"])
def test_unbound_modes_reject_before_loading(monkeypatch, strategy, cls, mode):
    data = market()
    spec = spec_for(strategy)
    if mode == "quantile":
        spec.config["params"]["threshold_mode"] = "quantile"
    request = replace(request_for(data), strategy_id=strategy, strategy_spec=spec,
                      strategy_params=deepcopy(spec.config["params"]), execution_price="close" if mode == "close" else "next_open")
    service = BacktestService(config=None)
    def forbidden(*_a):
        raise AssertionError("拒絕路由不可讀行情")
    monkeypatch.setattr(service, "_load_stock_data", forbidden)
    with pytest.raises(ValueError, match="因果缺值1.1.0"):
        execute_single_backtest_with_rule_source(request, service)
    with pytest.raises(ValueError, match="因果缺值1.1.0"):
        request.execute(service)


def test_research_revision_refuses_promotion(tmp_path, monkeypatch):
    from app_module.promotion_reconciliation_service import PromotionPreflightError, PromotionReconciliationService
    from app_module.strategy_version_service import StrategyVersionService
    _, _, registry, metadata = saved_case(tmp_path, monkeypatch, "baseline_score_threshold")
    versions = StrategyVersionService(registry.config)
    service = PromotionReconciliationService(research_repository=registry.repository, strategy_version_service=versions)
    with pytest.raises(PromotionPreflightError, match="因果缺值1.1.0"):
        service.promote_registry_run(metadata.run_id)
    assert versions.list_versions() == []


@pytest.mark.parametrize("strategy,cls", CASES)
def test_unquoted_zero_volume_row_is_unknown_and_pending_order_waits_for_original_broker(tmp_path, monkeypatch, strategy, cls):
    _, report, _, metadata = saved_case(tmp_path, monkeypatch, strategy, unquoted_index=21)
    rows = metadata.data_manifest["single_backtest_rule_execution"]["score_observations"]
    assert rows[20]["signal"] == 1
    assert rows[21] == {"date": rows[21]["date"], "score": None, "score_bp": None, "ready": False, "signal": 0}
    assert pd.Timestamp(report.details["trade_list"].iloc[0]["進場日期"]) == market().index[22]
    assert report.details["score_diagnostics"]["unknown_score_days"] == 21
