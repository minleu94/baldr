"""保存原run的跨家族訊號對照；合成價量不授來源、PIT或績效資格。"""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal, localcontext
from hashlib import sha256
import json

import pandas as pd
import pytest

from app_module.backtest_service import BacktestService
from app_module.registered_strategy_spec import registered_strategy_spec
from app_module.research_run_service import ResearchRunService
from app_module.saved_strategy_rule_card import load_saved_strategy_rule_card
from app_module.saved_strategy_signal_comparison import (
    SavedSignalStrategy, SavedStrategySignal, _comparison_day, read_saved_strategy_signal_comparison,
)
from app_module.strategy_signal_context import capture_strategy_signal_context, validate_strategy_signal_context
from data_module.config import TWStockConfig
from tests.test_ma_alignment_execution_source import market, request_for
from ui_qt.views.backtest.research_run_metadata import build_single_backtest_metadata, execute_single_backtest_with_rule_source


def saved_run(tmp_path, monkeypatch, strategy_id, *, data=None, remove_context=False, detach_context=False, code="2330"):
    data = market() if data is None else data
    request = request_for(data, start=data.index[180].date().isoformat())
    spec = registered_strategy_spec(strategy_id, config={"params": {}})
    request = replace(request, strategy_id=strategy_id, strategy_spec=spec, strategy_params={}, stock_code=code)
    engine = BacktestService(config=None)
    loads = []
    def load(stock, start, end):
        loads.append((stock, start, end))
        frame = data.loc[start:end].copy(deep=True)
        return frame, frame.index[0].date().isoformat(), frame.index[-1].date().isoformat()
    monkeypatch.setattr(engine, "_load_stock_data", load)
    report = execute_single_backtest_with_rule_source(request, engine)
    assert len(loads) == 1
    if remove_context:
        report.details["data_manifest"].pop("signal_comparison_context", None)
        qualification = report.details["data_manifest"]["single_backtest_rule_execution"]["qualification"]
        qualification.pop("signal_context_schema", None)
        qualification.pop("signal_context_sha256", None)
    if detach_context:
        raw = report.details["data_manifest"]["signal_comparison_context"]
        raw["rows"][1]["Open"] = "999"
        raw["sha256"] = sha256(json.dumps({key: value for key, value in raw.items() if key != "sha256"},
            ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    metadata = build_single_backtest_metadata(run_id=strategy_id + "-saved", run_name=strategy_id, notes="",
        params=request.run_params(), details=report.details, report=report, created_at="2026-10-17T08:00:00")
    service = ResearchRunService(TWStockConfig(data_root=tmp_path / "data", output_root=tmp_path / "output"))
    metadata = service.save_run(metadata, report.details["equity_curve"], report.details["trade_list"])
    return service, metadata, report


def _files(root):
    return {str(path.relative_to(root)): sha256(path.read_bytes()).hexdigest() for path in root.rglob("*") if path.is_file()}


def test_real_saved_ports_compare_different_warmup_once_without_current_executor_or_writes(tmp_path, monkeypatch):
    service, left, _ = saved_run(tmp_path, monkeypatch, "baldr_ma_alignment_basic_v1")
    _, right, _ = saved_run(tmp_path, monkeypatch, "baldr_w_bottom_basic_v1")
    assert left.data_fingerprint != right.data_fingerprint
    assert left.data_manifest["signal_comparison_context"] == right.data_manifest["signal_comparison_context"]
    assert not load_saved_strategy_rule_card(service, left).reasons
    assert not load_saved_strategy_rule_card(service, right).reasons
    before = _files(tmp_path / "output")
    calls = []
    original = service.load_run_data
    def loaded(run_id, **kwargs):
        calls.append(run_id)
        return original(run_id, **kwargs)
    monkeypatch.setattr(service, "load_run_data", loaded)
    from decision_module.strategies.registry import StrategyRegistry
    monkeypatch.setattr(StrategyRegistry, "get_executor", lambda *a, **kw: pytest.fail("reader不得重算或查目前executor"))
    result = read_saved_strategy_signal_comparison(service, (left, right))
    assert result.state == "available", result.reasons
    assert calls == [left.run_id, right.run_id]
    assert len(result.rows) == len(left.data_manifest["signal_comparison_context"]["rows"])
    assert {strategy.family_id for strategy in result.strategies} == {"trend", "pattern"}
    assert not result.historical_pit_eligible and not result.performance_evaluable
    assert before == _files(tmp_path / "output")


@pytest.mark.parametrize("strategy", ["baldr_bollinger_basic_v1", "baldr_bollinger_squeeze_v1", "baldr_vcp_three_contractions_v1", "baseline_score_threshold"])
def test_other_typed_producers_share_common_window_with_w_bottom(tmp_path, monkeypatch, strategy):
    service, first, _ = saved_run(tmp_path, monkeypatch, strategy)
    _, second, _ = saved_run(tmp_path, monkeypatch, "baldr_w_bottom_basic_v1")
    result = read_saved_strategy_signal_comparison(service, (first, second))
    assert result.state == "available", result.reasons


def test_old_bound_run_remains_readable_but_cannot_invent_signal_context(tmp_path, monkeypatch):
    service, old, _ = saved_run(tmp_path, monkeypatch, "baldr_ma_alignment_basic_v1", remove_context=True)
    _, current, _ = saved_run(tmp_path, monkeypatch, "baldr_w_bottom_basic_v1")
    assert load_saved_strategy_rule_card(service, old).source_status == "source_ref_only"
    result = read_saved_strategy_signal_comparison(service, (old, current))
    assert result.state == "unavailable" and "共同價量版本" in result.reasons[0]


def test_rehashed_context_cannot_detach_from_original_execution_identity(tmp_path, monkeypatch):
    service, altered, _ = saved_run(tmp_path, monkeypatch, "baldr_ma_alignment_basic_v1", detach_context=True)
    _, other, _ = saved_run(tmp_path, monkeypatch, "baldr_w_bottom_basic_v1")
    assert load_saved_strategy_rule_card(service, altered).source_status == "source_ref_only"
    result = read_saved_strategy_signal_comparison(service, (altered, other))
    assert result.state == "unavailable" and "未綁定" in result.reasons[0]


@pytest.mark.parametrize("strategy", ["baldr_ma_alignment_basic_v1", "baldr_bollinger_basic_v1", "baldr_bollinger_squeeze_v1",
    "baldr_vcp_three_contractions_v1", "baseline_score_threshold", "stable_conservative_v1", "momentum_aggressive_v1"])
def test_real_market_chinese_columns_share_context_and_cannot_shadow_conflicting_aliases(tmp_path, monkeypatch, strategy):
    frame = market()
    chinese = frame.rename(columns={"Open": "開盤價", "High": "最高價", "Low": "最低價", "Close": "收盤價", "Volume": "成交股數"})
    service, first, _ = saved_run(tmp_path, monkeypatch, strategy, data=chinese)
    _, second, _ = saved_run(tmp_path, monkeypatch, "baldr_w_bottom_basic_v1", data=chinese)
    result = read_saved_strategy_signal_comparison(service, (first, second))
    assert result.state == "available", result.reasons
    options = dict(stock_code="2330", start_date=first.original_input["raw_params"]["start_date"], end_date=first.original_input["raw_params"]["end_date"])
    assert capture_strategy_signal_context(frame, **options) == first.data_manifest["signal_comparison_context"]
    chinese["Close"] = chinese["收盤價"]
    assert capture_strategy_signal_context(chinese, **options) == first.data_manifest["signal_comparison_context"]
    chinese.loc[chinese.index[200], "Close"] += 1
    with pytest.raises(ValueError, match="別名"):
        capture_strategy_signal_context(chinese, **options)


@pytest.mark.parametrize("different", ["stock", "price", "date", "policy"])
def test_same_dates_or_metrics_never_replace_exact_common_input(tmp_path, monkeypatch, different):
    data = market()
    service, left, _ = saved_run(tmp_path, monkeypatch, "baldr_ma_alignment_basic_v1", data=data)
    if different == "price":
        data.loc[data.index[200], "Open"] += 1
    if different == "date":
        data = data.drop(data.index[200])
    if different == "policy":
        data.attrs["price_input_preparation"] = "other-policy.v1"
    _, right, _ = saved_run(tmp_path, monkeypatch, "baldr_w_bottom_basic_v1", data=data, code="2317" if different == "stock" else "2330")
    result = read_saved_strategy_signal_comparison(service, (left, right))
    assert result.state == "unavailable" and "不同" in result.reasons[0]
    assert not result.rows


def test_selected_metadata_drift_duplicate_strategy_and_cancel_reject(tmp_path, monkeypatch):
    service, left, _ = saved_run(tmp_path, monkeypatch, "baldr_ma_alignment_basic_v1")
    _, right, _ = saved_run(tmp_path, monkeypatch, "baldr_w_bottom_basic_v1")
    assert read_saved_strategy_signal_comparison(service, (left, replace(left, run_id="another"))).state == "unavailable"
    altered = replace(left, run_name="已變更")
    assert read_saved_strategy_signal_comparison(service, (altered, right)).state == "unavailable"
    with pytest.raises(InterruptedError):
        read_saved_strategy_signal_comparison(service, (left, right), check_cancel=lambda: True)


def test_capture_is_prefix_bounded_precision_independent_and_nonmutating():
    frame = market().astype(object)
    frame.loc[frame.index[180], "Volume"] = Decimal("9007199254740993")
    original = frame.copy(deep=True)
    options = dict(stock_code="2330", start_date=frame.index[180].date().isoformat(), end_date=frame.index[220].date().isoformat())
    expected = capture_strategy_signal_context(frame.iloc[:221], **options)
    with localcontext() as context:
        context.prec = 6
        actual = capture_strategy_signal_context(frame, **options)
    assert actual == expected
    assert actual["rows"][0]["Volume"] == "9007199254740993"
    assert validate_strategy_signal_context(actual) == actual
    pd.testing.assert_frame_equal(frame, original)


@pytest.mark.parametrize("mutation", ["hash", "float", "duplicate", "order", "future", "qualification", "normalization", "compact", "number_text"])
def test_changed_or_noncanonical_context_rejected(mutation):
    frame = market()
    raw = capture_strategy_signal_context(frame, stock_code="2330", start_date=frame.index[0].date().isoformat(), end_date=frame.index[-1].date().isoformat())
    if mutation == "hash": raw["sha256"] = "0" * 64
    if mutation == "float": raw["rows"][0]["Close"] = 100.0
    if mutation == "duplicate": raw["rows"][1]["date"] = raw["rows"][0]["date"]
    if mutation == "order": raw["rows"].reverse()
    if mutation == "future": raw["rows"][-1]["date"] = "2030-01-01"
    if mutation == "qualification": raw["historical_pit_eligible"] = True
    if mutation == "normalization": raw["normalization"] = "newer"
    if mutation == "compact": raw["rows"][0]["date"] = raw["rows"][0]["date"].replace("-", "")
    if mutation == "number_text": raw["rows"][0]["Close"] += ".00"
    if mutation != "hash":
        raw["sha256"] = sha256(json.dumps({key: value for key, value in raw.items() if key != "sha256"},
            ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    with pytest.raises(ValueError):
        validate_strategy_signal_context(raw)


@pytest.mark.parametrize("states,expected,count", [
    (("match", "match"), "match", 2), (("match", "unknown"), "unknown", 1),
    (("unknown", "no_match"), "no_match", 0), (("unknown", "unknown"), "unknown", 0),
])
def test_three_state_joint_entry_and_family_count(states, expected, count):
    # 此處只測三態聚合；真port及原規則綁定另由上面的實際保存測試證明。
    strategies = tuple(SavedSignalStrategy(str(i), str(i), str(i), "1", "same-family", "同族", None) for i in range(2))
    signals = tuple(SavedStrategySignal(state, 1 if state == "match" else 0, "原觀測") for state in states)
    row = _comparison_day("2026-01-02", strategies, signals)
    assert row.common_entry_state == expected and row.matching_strategy_count == count
    assert row.matching_family_count == (1 if count else 0)
