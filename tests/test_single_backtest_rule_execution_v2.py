"""固定策略回測來源封存與重開驗證；使用原策略執行器與撮合器。"""

from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
import math
import re

import pandas as pd
import pytest

from app_module.backtest_service import BacktestService
from app_module.basic_strategy_saved_pair import BasicStrategySavedPairReader, _preflight
from app_module.research_history_lookup import ResearchHistoryLookup, ResearchHistoryReadBudget
from app_module.research_run_service import ResearchRunService
from app_module.saved_strategy_rule_card import load_saved_strategy_rule_card, metadata_sha256
from app_module.strategy_rule_card_readmodel import read_single_backtest_execution_rule_card
from data_module.config import TWStockConfig
from decision_module.strategies.contracts import StrategyMeta, StrategySpec
from decision_module.strategies.registry import StrategyRegistry
from ui_qt.views.backtest.execution_coordinator import BacktestExecutionRequest
from ui_qt.views.backtest.research_run_metadata import (
    build_single_backtest_metadata,
    execute_single_backtest_with_rule_source,
)


_STRATEGIES = {
    "stable_conservative_v1": "stable-conservative-fixed.v1",
    "momentum_aggressive_v1": "momentum-aggressive-fixed.v1",
}
_EXECUTOR_TYPES = {
    "stable_conservative_v1": (
        "decision_module.strategies.stable_conservative_executor."
        "StableConservativeExecutor"
    ),
    "momentum_aggressive_v1": (
        "decision_module.strategies.momentum_aggressive_executor."
        "MomentumAggressiveExecutor"
    ),
}


def test_two_basic_strategies_compare_saved_originals_and_reject_incomplete_conditions(
    tmp_path, monkeypatch,
):
    _, registry, stable, _, _, _ = executed_v2_case(
        tmp_path, monkeypatch, "stable_conservative_v1",
    )
    _, _, momentum, _, _, _ = executed_v2_case(
        tmp_path, monkeypatch, "momentum_aggressive_v1",
    )
    lookup = ResearchHistoryLookup(
        registry=registry,
        read_budget=ResearchHistoryReadBudget(64 * 1024 * 1024, 256 * 1024 * 1024),
    )
    reader = BasicStrategySavedPairReader(registry, lookup)
    original_stable_hash = metadata_sha256(stable)
    original_momentum_hash = metadata_sha256(momentum)

    pair = reader.read_selected((stable, momentum))
    assert pair.state == "saved_conditions_match", pair.reasons
    assert [entry.run_id for entry in pair.entries] == [stable.run_id, momentum.run_id]
    assert all(card.read_state.value == "read_verified" for card in pair.cards)
    assert all(card.metrics_state.value == "saved_metrics_schema_observed" for card in pair.cards)
    assert all(rule.performance_status == "not_evaluable" for rule in pair.rules)
    assert all(rule.rule_card.field("qualification").value["historical_pit_eligible"] is False
               for rule in pair.rules)
    assert lookup.resolve(pair.entries[0]).result.metadata.run_id == stable.run_id
    assert lookup.resolve(pair.entries[1]).result.metadata.run_id == momentum.run_id
    assert metadata_sha256(registry.repository.get_metadata(stable.run_id)) == original_stable_hash
    assert metadata_sha256(registry.repository.get_metadata(momentum.run_id)) == original_momentum_hash

    missing_fee = deepcopy(momentum.original_input)
    del missing_fee["raw_params"]["fee_bps"]
    other_actual_period = deepcopy(momentum.data_manifest)
    other_actual_period["single_backtest_metrics_contract"]["period_end"] = "2026-05-02"
    cases = (
        (replace(momentum, end_date="2026-05-01"), "研究期間不同"),
        (replace(momentum, fee_bp_x100=momentum.fee_bp_x100 + 1), "執行與成本條件不同"),
        (replace(momentum, original_input=missing_fee), "原執行輸入不完整"),
        (replace(momentum, data_manifest=other_actual_period), "保存權益實際期間不同"),
        (replace(momentum, strategy_id="stable_conservative_v1"), "請各選一筆穩健策略與積極策略"),
    )
    for changed, reason in cases:
        blocked = reader.read_selected((stable, changed))
        assert blocked.state == "blocked" and reason in blocked.reasons
        assert not blocked.cards and not blocked.entries

    stale = reader.read_selected((replace(stable, run_name="已更動的選取"), momentum))
    assert stale.state == "blocked" and "所選保存來源已變動" in stale.reasons
    assert not stale.cards


def test_two_basic_strategies_reject_matching_but_internally_inconsistent_saved_inputs(
    tmp_path, monkeypatch,
):
    _, _, stable, _, _, _ = executed_v2_case(
        tmp_path, monkeypatch, "stable_conservative_v1",
    )
    _, _, momentum, _, _, _ = executed_v2_case(
        tmp_path, monkeypatch, "momentum_aggressive_v1",
    )
    assert _preflight((stable, momentum)) == ()

    for source, key, value in (
        ("raw", "capital", 2_000_000),
        ("raw", "capital", "NaN"),
        ("raw", "fee_bps", Decimal("15")),
        ("raw", "max_participation", Decimal("0.10")),
        ("raw", "enable_limit", False),
        ("broker", "slippage_bps", 6),
        ("broker", "max_positions", 2),
        ("broker", "allow_reentry", False),
    ):
        changed = []
        for original in (stable, momentum):
            if source == "raw":
                original_input = deepcopy(original.original_input)
                original_input["raw_params"][key] = value
                changed.append(replace(original, original_input=original_input))
            else:
                manifest = deepcopy(original.data_manifest)
                manifest["single_backtest_rule_execution"]["broker_config"][key] = value
                changed.append(replace(original, data_manifest=manifest))
        assert "原執行輸入、保存金額或撮合設定不符" in _preflight(tuple(changed))


def test_two_basic_strategies_reject_different_saved_daily_calendars(
    tmp_path, monkeypatch,
):
    _, registry, stable, _, _, _ = executed_v2_case(
        tmp_path, monkeypatch, "stable_conservative_v1",
    )
    _, _, momentum, _, _, _ = executed_v2_case(
        tmp_path, monkeypatch, "momentum_aggressive_v1",
        shift_equity_calendar=True,
    )
    assert _preflight((stable, momentum)) == ()
    lookup = ResearchHistoryLookup(
        registry=registry,
        read_budget=ResearchHistoryReadBudget(64 * 1024 * 1024, 256 * 1024 * 1024),
    )
    result = BasicStrategySavedPairReader(registry, lookup).read_selected((stable, momentum))
    assert result.state == "blocked"
    assert result.reasons == ("兩筆原保存權益逐日日期不同，不能並列績效",)
    assert not result.cards and not result.entries


def _raw_ohlcv() -> pd.DataFrame:
    index = pd.bdate_range("2026-01-02", periods=90)
    close = [100.0 + i * 0.35 + (i % 7) * 0.8 for i in range(len(index))]
    frame = pd.DataFrame(
        {
            "Open": [value - 0.2 for value in close],
            "High": [value + 1.0 for value in close],
            "Low": [value - 1.0 for value in close],
            "Close": close,
            "Volume": [1_000_000 + (i % 11) * 10_000 for i in range(len(index))],
        },
        index=index,
    )
    assert not frame.isna().any().any()
    assert all(math.isfinite(float(value)) for value in frame.to_numpy().flat)
    return frame


def executed_v2_case(tmp_path, monkeypatch, strategy_id, *, strategy_params=None,
                     risk_limits=None, shift_equity_calendar=False):
    """只替換行情載入；策略 registry、typed executor、broker 與保存均用原實作。"""
    if strategy_id not in _STRATEGIES:
        raise ValueError("只接受本輪兩個 fixed 策略")

    config = TWStockConfig(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        profile="test",
    )
    raw_meta = StrategyRegistry.get_strategy_meta(strategy_id)
    meta = raw_meta.to_dict() if isinstance(raw_meta, StrategyMeta) else raw_meta
    assert meta["strategy_version"] == "1.0.0"
    if strategy_params is None:
        params = dict(meta["default_params"])
        params.update(
            threshold_mode="fixed",
            buy_score=0,
            sell_score=100,
            buy_confirm_days=1,
            sell_confirm_days=1,
            cooldown_days=0,
        )
    else:
        params = dict(strategy_params)
    spec = StrategySpec(
        strategy_id=strategy_id,
        strategy_version="1.0.0",
        name=meta["name"],
        description=meta["description"],
        regime=list(meta["regime"]),
        risk_level=meta["risk_level"],
        target_type=meta["target_type"],
        default_params=dict(meta["default_params"]),
        config={"params": params},
    )
    frame = _raw_ohlcv()
    service = BacktestService(config=None)
    loads = []

    def load_synthetic_market(*args):
        loads.append(args)
        return frame.copy(), frame.index[0].strftime("%Y-%m-%d"), frame.index[-1].strftime("%Y-%m-%d")

    monkeypatch.setattr(service, "_load_stock_data", load_synthetic_market)
    service._fixture_loads = loads
    service._fixture_raw_ohlcv = frame.copy()
    request = BacktestExecutionRequest(
        stock_code="2330",
        start_date=frame.index[0].strftime("%Y-%m-%d"),
        end_date=frame.index[-1].strftime("%Y-%m-%d"),
        strategy_id=strategy_id,
        strategy_spec=spec,
        strategy_params=dict(params),
        capital=1_000_000,
        fee_bps=Decimal("14.25"),
        slippage_bps=Decimal("5"),
        execution_price="next_open",
        stop_loss_pct=(risk_limits or {}).get("stop_loss_pct"),
        take_profit_pct=(risk_limits or {}).get("take_profit_pct"),
        stop_loss_atr_mult=None,
        take_profit_atr_mult=None,
        sizing_mode="all_in",
        fixed_amount=None,
        risk_pct=None,
        max_positions=1,
        position_sizing="equal_weight",
        allow_pyramid=False,
        allow_reentry=True,
        reentry_cooldown_days=0,
        enable_limit=True,
        enable_volume=True,
        max_participation=Decimal("0.05"),
    )
    report = execute_single_backtest_with_rule_source(request, service)
    assert len(loads) == 1
    if shift_equity_calendar:
        # 保留起訖與列數，只改中間某個週五為週六，模擬兩曲線日期集合不同。
        curve = report.details["equity_curve"].copy(deep=True)
        friday = next(i for i in range(1, len(curve) - 1) if curve.index[i].weekday() == 4)
        shifted = curve.index.tolist()
        shifted[friday] = shifted[friday] + pd.Timedelta(days=1)
        curve.index = pd.DatetimeIndex(shifted)
        for column in ("date", "日期"):
            if column in curve:
                curve.loc[curve.index[friday], column] = curve.index[friday]
        report.details["equity_curve"] = curve
    metadata = build_single_backtest_metadata(
        run_id=f"executed-{strategy_id}",
        run_name="固定策略 typed 合成執行",
        notes="",
        params=request.run_params(),
        details=report.details,
        report=report,
        created_at="2026-10-15T10:00:00",
    )
    registry = ResearchRunService(config)
    metadata = registry.save_run(
        metadata,
        report.details["equity_curve"],
        report.details["trade_list"],
    )
    return config, registry, metadata, request, report, service


@pytest.mark.parametrize("strategy_id", tuple(_STRATEGIES))
def test_fixed_v2_execution_matches_request_and_reopens_without_current_registry(
    tmp_path,
    monkeypatch,
    strategy_id,
):
    config, registry, metadata, request, report, service = executed_v2_case(
        tmp_path,
        monkeypatch,
        strategy_id,
    )
    original_spec = request.strategy_spec.to_dict()
    execution = report.details["data_manifest"]["single_backtest_rule_execution"]

    assert execution["schema"] == "single-backtest-rule-execution.v2"
    assert execution["strategy_spec"]["strategy_id"] == strategy_id
    assert execution["strategy_spec"]["strategy_version"] == "1.0.0"
    assert execution["strategy_spec"]["data_version"].startswith("sha256:")
    assert metadata.strategy_id == strategy_id
    assert metadata.strategy_version == "1.0.0"
    assert metadata.parameter_contract_version == _STRATEGIES[strategy_id]
    assert metadata.data_manifest["single_backtest_rule_execution"] == execution
    assert execution["executor"]["threshold_mode"] == "fixed"
    assert execution["executor"]["buy_score"] == request.strategy_params["buy_score"]
    assert execution["executor"]["sell_score"] == request.strategy_params["sell_score"]
    assert execution["executor"]["buy_confirm_days"] == request.strategy_params["buy_confirm_days"]
    assert execution["executor"]["sell_confirm_days"] == request.strategy_params["sell_confirm_days"]
    assert execution["executor"]["cooldown_days"] == request.strategy_params["cooldown_days"]
    assert execution["executor"]["threshold_value_source"] == "ScoreThresholdPolicy.fixed"
    assert execution["broker_config"]["execution_price"] == "next_open"
    expected_sources = {
        _EXECUTOR_TYPES[strategy_id],
        "backtest_module.broker_simulator.BrokerSimulator",
        "decision_module.score_threshold_policy.ScoreThresholdPolicy",
        "app_module.backtest_service.BacktestService",
        "ui_qt.views.backtest.research_run_metadata.execute_single_backtest_with_rule_source",
    }
    assert set(execution["source_hashes"]) == expected_sources
    assert all(re.fullmatch(r"[0-9a-f]{64}", value) for value in execution["source_hashes"].values())
    assert len(service._fixture_loads) == 1
    assert request.strategy_spec.to_dict() == original_spec

    original_report = request.execute(service)
    assert len(service._fixture_loads) == 2
    pd.testing.assert_frame_equal(original_report.details["equity_curve"], report.details["equity_curve"])
    pd.testing.assert_frame_equal(original_report.details["trade_list"], report.details["trade_list"])
    assert request.strategy_spec.to_dict() == original_spec

    fresh_registry = ResearchRunService(config)

    def deny_current_registry(*_args, **_kwargs):
        raise AssertionError("保存規則 reader 不得重取目前 executor／metadata")

    monkeypatch.setattr(StrategyRegistry, "get_executor", deny_current_registry)
    monkeypatch.setattr(StrategyRegistry, "get_strategy_meta", deny_current_registry)
    saved = load_saved_strategy_rule_card(fresh_registry, metadata)

    assert saved.source_status == "source_ref_only", saved.reasons
    assert saved.rule_card.rule_status == "execution_contract_bound"
    assert saved.rule_card.missing == ()
    assert saved.performance_status == "not_evaluable"
    assert saved.rule_card.field("qualification").value["historical_pit_eligible"] is False
    # 原 Registry 將 Decimal JSON 葉節點保存為精確字串，按同一序列化契約核完整 DTO。
    reloaded = registry.repository.get_metadata(metadata.run_id)
    assert reloaded is not None
    assert metadata_sha256(reloaded) == metadata_sha256(metadata)


@pytest.mark.parametrize("ratio", [None, Decimal("0"), Decimal("0.05"), Decimal("0.055")])
def test_v2_saved_rule_cross_binds_exact_risk_ratio_and_legacy_integer(tmp_path, monkeypatch, ratio):
    _, registry, metadata, _, _, _ = executed_v2_case(
        tmp_path, monkeypatch, "stable_conservative_v1",
        risk_limits={"stop_loss_pct": ratio, "take_profit_pct": ratio},
    )
    card = load_saved_strategy_rule_card(registry, metadata)
    assert card.source_status == "source_ref_only", card.reasons
    assert card.rule_card.rule_status == "execution_contract_bound", card.reasons
    assert card.rule_card.field("stop_loss").value["ratio"] == (str(ratio) if ratio is not None else None)
    for key in ("stop_loss_bp", "take_profit_bp"):
        changed = replace(metadata, **{key: (getattr(metadata, key) or 0) + 1})
        monkeypatch.setattr(registry, "load_run_data", lambda _run_id: type("Loaded", (), {"metadata": changed})())
        rejected = load_saved_strategy_rule_card(registry, changed)
        assert "execution_rule_saved_cost_mismatch" in rejected.reasons
    for key in ("stop_loss_pct", "take_profit_pct"):
        original_input = deepcopy(metadata.original_input)
        original_input["raw_params"][key] = "0.15"
        changed = replace(metadata, original_input=original_input)
        monkeypatch.setattr(registry, "load_run_data", lambda _run_id: type("Loaded", (), {"metadata": changed})())
        rejected = load_saved_strategy_rule_card(registry, changed)
        assert "execution_rule_saved_cost_mismatch" in rejected.reasons


def test_v2_reader_rejects_v1_cross_identity_changed_source_and_metadata_version(
    tmp_path,
    monkeypatch,
):
    config, _registry, metadata, request, report, _service = executed_v2_case(
        tmp_path,
        monkeypatch,
        "stable_conservative_v1",
    )
    execution = deepcopy(report.details["data_manifest"]["single_backtest_rule_execution"])
    spec = StrategySpec.from_dict(execution["strategy_spec"])

    v1_schema = deepcopy(execution)
    v1_schema["schema"] = "single-backtest-rule-execution.v1"
    assert read_single_backtest_execution_rule_card(spec, v1_schema).reasons

    baseline_spec = StrategySpec(
        "baseline_score_threshold",
        "1.0",
        config={"params": {"threshold_mode": "fixed"}},
    )
    assert read_single_backtest_execution_rule_card(baseline_spec, execution).reasons

    changed_source = deepcopy(execution)
    changed_source["source_hashes"].pop(_EXECUTOR_TYPES[spec.strategy_id])
    assert read_single_backtest_execution_rule_card(spec, changed_source).reasons

    wrong_spec_version = replace(spec, strategy_version="9.9.9")
    assert read_single_backtest_execution_rule_card(wrong_spec_version, execution).reasons

    changed_metadata = replace(metadata, strategy_version="9.9.9")
    reopened = load_saved_strategy_rule_card(ResearchRunService(config), changed_metadata)
    assert "selected_source_changed" in reopened.reasons


def test_v2_cancellation_is_checked_before_market_load(tmp_path, monkeypatch):
    _config, _registry, _metadata, request, _report, service = executed_v2_case(
        tmp_path,
        monkeypatch,
        "momentum_aggressive_v1",
    )
    count_before_cancel = len(service._fixture_loads)

    with pytest.raises(InterruptedError, match="取消"):
        execute_single_backtest_with_rule_source(
            request,
            service,
            check_cancel=lambda: True,
        )

    assert len(service._fixture_loads) == count_before_cancel


@pytest.mark.parametrize("strategy_id", tuple(_STRATEGIES))
def test_v2_uses_effective_policy_defaults_for_omitted_scores(tmp_path, monkeypatch, strategy_id):
    partial_params = {
        "threshold_mode": "fixed",
        "buy_confirm_days": 1,
        "sell_confirm_days": 1,
        "cooldown_days": 0,
    }
    _config, _registry, _metadata, request, report, service = executed_v2_case(
        tmp_path,
        monkeypatch,
        strategy_id,
        strategy_params=partial_params,
    )
    assert "buy_score" not in request.strategy_params
    assert "sell_score" not in request.strategy_params
    execution = report.details["data_manifest"]["single_backtest_rule_execution"]

    assert execution["executor"]["buy_score"] == 60
    assert execution["executor"]["sell_score"] == 40
    assert execution["executor"]["threshold_value_source"] == "ScoreThresholdPolicy.fixed"
    saved_card = read_single_backtest_execution_rule_card(StrategySpec.from_dict(execution["strategy_spec"]), execution)
    assert saved_card.rule_status == "execution_contract_bound"
    assert saved_card.field("entry").value["threshold"] == 60
    assert saved_card.field("exit").value["threshold"] == 40

    original_spec = request.strategy_spec.to_dict()
    original_report = request.execute(service)
    assert len(service._fixture_loads) == 2
    pd.testing.assert_frame_equal(original_report.details["equity_curve"], report.details["equity_curve"])
    pd.testing.assert_frame_equal(original_report.details["trade_list"], report.details["trade_list"])
    assert request.strategy_spec.to_dict() == original_spec


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("historical_pit_eligible", True),
        ("historical_pit_eligible", 1),
        ("historical_pit_eligible", None),
        ("performance_evaluable", True),
        ("performance_evaluable", 1),
        ("performance_evaluable", None),
    ],
)
def test_v2_reader_rejects_qualification_grants(tmp_path, monkeypatch, field, invalid_value):
    _config, _registry, _metadata, request, report, _service = executed_v2_case(
        tmp_path,
        monkeypatch,
        "stable_conservative_v1",
    )
    execution = deepcopy(report.details["data_manifest"]["single_backtest_rule_execution"])
    execution["qualification"][field] = invalid_value

    card = read_single_backtest_execution_rule_card(StrategySpec.from_dict(execution["strategy_spec"]), execution)

    assert "execution_rule_qualification_invalid" in card.reasons


@pytest.mark.parametrize(
    ("field", "changed_value"),
    [
        ("buy_score", 1),
        ("sell_score", 99),
        ("buy_confirm_days", 2),
        ("sell_confirm_days", 2),
        ("cooldown_days", 1),
    ],
)
def test_v2_reader_rejects_explicit_params_that_disagree_with_effective_capture(
    tmp_path,
    monkeypatch,
    field,
    changed_value,
):
    _config, _registry, _metadata, request, report, _service = executed_v2_case(
        tmp_path,
        monkeypatch,
        "stable_conservative_v1",
    )
    execution = deepcopy(report.details["data_manifest"]["single_backtest_rule_execution"])
    captured_spec = StrategySpec.from_dict(execution["strategy_spec"])
    changed_spec_config = deepcopy(captured_spec.config)
    changed_spec_config["params"][field] = changed_value
    changed_spec = replace(captured_spec, config=changed_spec_config)
    execution["strategy_spec"] = changed_spec.to_dict()

    card = read_single_backtest_execution_rule_card(changed_spec, execution)

    assert "execution_rule_parameter_mismatch" in card.reasons


@pytest.mark.parametrize("strategy_id", tuple(_STRATEGIES))
def test_original_executor_signal_prefix_is_stable_after_future_ohlcv_append(
    tmp_path,
    monkeypatch,
    strategy_id,
):
    _config, _registry, _metadata, request, _report, service = executed_v2_case(
        tmp_path,
        monkeypatch,
        strategy_id,
    )
    raw = service._fixture_raw_ohlcv
    prefix = raw.iloc[:60].copy()
    appended = pd.concat([prefix, raw.iloc[60:].copy()])
    original_spec = request.strategy_spec
    executor = StrategyRegistry.get_executor(original_spec)

    prefix_signals = executor.generate_signals(prefix.copy(), original_spec)
    appended_signals = executor.generate_signals(appended.copy(), original_spec)

    pd.testing.assert_frame_equal(
        prefix_signals,
        appended_signals.loc[prefix_signals.index],
    )
