"""原兩策略1.1.0缺值／因果契約；1.0.0原行為另行保留。"""
from copy import deepcopy

import pandas as pd
import pytest

from analysis_module.technical_analysis.causal_score_input import prepare_causal_score_input
from decision_module.strategies.contracts import StrategySpec
from decision_module.strategies.stable_conservative_executor import StableConservativeExecutor
from decision_module.strategies.momentum_aggressive_executor import MomentumAggressiveExecutor
from decision_module.strategies.baseline_score_executor import BaselineScoreExecutor

CASES = (("stable_conservative_v1", StableConservativeExecutor), ("momentum_aggressive_v1", MomentumAggressiveExecutor),
         ("baseline_score_threshold", BaselineScoreExecutor))


def frame():
    return pd.DataFrame({"開盤價": [100] * 12, "最高價": [101] * 12, "最低價": [99] * 12,
        "收盤價": [100] * 12, "成交股數": [1000000] * 12, "RSI": [None] * 5 + [90] * 7},
        index=pd.bdate_range("2026-01-02", periods=12))


def spec_for(strategy, version="1.1.0"):
    if strategy == "baseline_score_threshold" and version == "1.0.0":
        version = "1.0"
    return StrategySpec(strategy_id=strategy, strategy_version=version, config={"config_schema_version": 1,
        "technical": {"momentum": {"enabled": True, "rsi": {"enabled": True}, "macd": {"enabled": False}, "kd": {"enabled": False}}},
        "weights": {"pattern": 0, "technical": 10000, "volume": 0},
        "params": {"threshold_mode": "fixed", "buy_score": 60, "sell_score": 40,
                   "buy_confirm_days": 1, "sell_confirm_days": 1, "cooldown_days": 0}})


@pytest.mark.parametrize("strategy,cls", CASES)
def test_new_version_preserves_unknown_and_all_prefixes(strategy, cls):
    data = frame()
    original = data.copy(deep=True)
    spec = spec_for(strategy)
    frozen = deepcopy(spec.to_dict())
    full = cls(spec).generate_signals(data, spec)
    assert full["RSI"].iloc[:5].isna().all() and full["score"].iloc[:5].isna().all()
    assert not full["signal"].iloc[:5].any()
    for length in range(1, len(data) + 1):
        prefix = cls(spec).generate_signals(data.iloc[:length], spec)
        for key in ("RSI", "score", "signal", "buy_threshold_hit", "sell_threshold_hit"):
            pd.testing.assert_series_equal(prefix[key], full[key].iloc[:length], check_dtype=False)
    pd.testing.assert_frame_equal(data, original)
    assert spec.to_dict() == frozen


@pytest.mark.parametrize("strategy,cls", CASES)
def test_old_version_keeps_original_reproduced_behavior(strategy, cls):
    spec = spec_for(strategy, "1.0.0")
    prefix = cls(spec).generate_signals(frame().iloc[:3], spec)
    full = cls(spec).generate_signals(frame(), spec)
    assert prefix["RSI"].tolist() == [0, 0, 0]
    assert full["RSI"].iloc[:3].tolist() == [90, 90, 90]
    assert prefix["signal"].iloc[0] == 1 and full["signal"].iloc[0] == 0
    old_meta = cls.get_meta(spec.strategy_version)
    new_meta = cls.get_meta()
    assert (old_meta["version"] if isinstance(old_meta, dict) else old_meta.strategy_version) == spec.strategy_version
    assert (new_meta["version"] if isinstance(new_meta, dict) else new_meta.strategy_version) == "1.1.0"


@pytest.mark.parametrize("strategy,cls", CASES)
@pytest.mark.parametrize("field,value", [("開盤價", None), ("最高價", 90), ("收盤價", 0), ("成交股數", None), ("成交股數", -1)])
def test_new_version_refuses_missing_or_inconsistent_ohlcv(strategy, cls, field, value):
    data = frame()
    data.loc[data.index[4], field] = value
    spec = spec_for(strategy)
    with pytest.raises(ValueError, match="因果計分OHLCV"):
        cls(spec).generate_signals(data, spec)


@pytest.mark.parametrize("strategy,cls", CASES)
@pytest.mark.parametrize("change", ["params", "version"])
def test_new_version_rejects_mutated_execution_spec(strategy, cls, change):
    spec = spec_for(strategy)
    executor = cls(spec)
    if change == "params":
        spec.config["params"]["buy_score"] = 1
    else:
        spec.strategy_version = "1.0.0"
    with pytest.raises(ValueError, match="規格已變動"):
        executor.generate_signals(frame(), spec)


def test_numeric_yyyymmdd_and_nonfinite_indicator_do_not_invent_values():
    data = frame()
    data["日期"] = [int(value.strftime("%Y%m%d")) for value in data.index]
    data = data.reset_index(drop=True)
    data["RSI"] = data["RSI"].astype(object)
    data.loc[6, "RSI"] = "inf"
    ready = prepare_causal_score_input(data)
    assert ready.index.equals(frame().index)
    assert pd.isna(ready.iloc[6]["RSI"])
    assert ready["RSI"].iloc[:5].isna().all()


@pytest.mark.parametrize("strategy,cls", CASES)
def test_long_missing_prefix_does_not_choose_recalculation_using_future_presence(strategy, cls):
    data = pd.concat([frame().iloc[:1]] * 70, ignore_index=True)
    data.index = pd.bdate_range("2026-01-02", periods=70)
    data["RSI"] = [None] * 40 + [90] * 30
    spec = spec_for(strategy)
    full = cls(spec).generate_signals(data, spec)
    assert full["RSI"].iloc[:40].isna().all()
    for length in (1, 14, 20, 39, 40, 41, 70):
        prefix = cls(spec).generate_signals(data.iloc[:length], spec)
        for key in ("RSI", "score", "signal"):
            pd.testing.assert_series_equal(prefix[key], full[key].iloc[:length], check_dtype=False)


def test_ohlcv_aliases_and_duplicate_dates_do_not_silently_select_conflicting_sources():
    data = frame()
    data["Close"] = ["100"] * len(data)
    assert prepare_causal_score_input(data)["Close"].equals(prepare_causal_score_input(data)["收盤價"])
    data.loc[data.index[0], "Close"] = "110"
    with pytest.raises(ValueError, match="別名衝突"):
        prepare_causal_score_input(data)
    data = frame()
    data["日期"] = [int(value.strftime("%Y%m%d")) + 1 for value in data.index]
    with pytest.raises(ValueError, match="日期欄與原日索引衝突"):
        prepare_causal_score_input(data)


@pytest.mark.parametrize("strategy,cls", CASES)
def test_registry_explicit_old_and_new_metadata_are_read_only_without_executor(monkeypatch, strategy, cls):
    from decision_module.strategies.registry import StrategyRegistry
    old = "1.0" if strategy == "baseline_score_threshold" else "1.0.0"
    def forbidden(*_a, **_kw):
        raise AssertionError("metadata查詢不可建立executor")
    monkeypatch.setattr(StrategyRegistry, "get_executor", forbidden)
    for version in (old, "1.1.0"):
        value = StrategyRegistry.get_strategy_meta(strategy, version=version)
        assert (value["version"] if isinstance(value, dict) else value.strategy_version) == version
    assert StrategyRegistry.get_strategy_meta(strategy, version="999.0.0") is None


@pytest.mark.parametrize("strategy,cls", CASES)
def test_quote_gap_preserves_raw_unknown_and_causal_segment_prefixes(strategy, cls):
    data = pd.concat([frame().iloc[:1]] * 48, ignore_index=True)
    data.index = pd.bdate_range("2026-01-02", periods=48)
    data["RSI"] = [20] * 48
    data.loc[data.index[20], ["開盤價", "最高價", "最低價", "收盤價"]] = None
    data.loc[data.index[20], "成交股數"] = 0
    original = data.copy(deep=True)
    spec = spec_for(strategy)
    spec.config["patterns"] = {"selected": ["W底"]}
    full = cls(spec).generate_signals(data, spec)
    assert full.loc[data.index[20], ["開盤價", "最高價", "最低價", "收盤價", "score"]].isna().all()
    assert full.loc[data.index[20], "signal"] == 0
    assert pd.notna(full.loc[data.index[21], "score"])
    for length in (1, 19, 20, 21, 22, 35, 48):
        prefix = cls(spec).generate_signals(data.iloc[:length], spec)
        for key in ("score", "signal", "IndicatorScore", "PatternScore", "VolumeScore"):
            pd.testing.assert_series_equal(prefix[key], full[key].iloc[:length], check_dtype=False)
    pd.testing.assert_frame_equal(data, original)


@pytest.mark.parametrize("strategy,cls", CASES)
@pytest.mark.parametrize("bad_quote", ["broken", "inf", "-inf"])
def test_four_bad_quotes_with_zero_volume_are_not_a_missing_quote_row(strategy, cls, bad_quote):
    data = frame()
    columns = ["開盤價", "最高價", "最低價", "收盤價"]
    data[columns] = data[columns].astype(object)
    data.loc[data.index[4], columns] = bad_quote
    data.loc[data.index[4], "成交股數"] = 0
    spec = spec_for(strategy)
    with pytest.raises(ValueError, match="因果計分OHLCV含不可解析或非有限原報價"):
        cls(spec).generate_signals(data, spec)
