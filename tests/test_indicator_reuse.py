from __future__ import annotations

import math

import pandas as pd
import pytest

from analysis_module.technical_analysis.indicator_parameter_registry import InvalidParameterError
from decision_module.indicator_reuse import prepare_indicator_reuse


def test_default_rsi_and_bollinger_reuse_existing_columns() -> None:
    frame = pd.DataFrame(
        {
            "RSI": [50],
            "upperband": [11],
            "middleband": [10],
            "lowerband": [9],
        }
    )
    config = {
        "momentum": {"enabled": True, "rsi": {"enabled": True}},
        "volatility": {"enabled": True, "bollinger": {"enabled": True}},
    }

    plan = prepare_indicator_reuse(frame, config, {"config_schema_version": 0})

    assert plan.reused_indicators == frozenset({"rsi", "bollinger"})
    assert plan.technical_config["momentum"]["rsi"]["enabled"] is False
    assert plan.technical_config["volatility"]["bollinger"]["enabled"] is False
    assert plan.frame["BB_Upper"].tolist() == [11]
    assert plan.frame["BB_Middle"].tolist() == [10]
    assert plan.frame["BB_Lower"].tolist() == [9]


def test_default_kd_reuse_adds_legacy_analysis_aliases() -> None:
    frame = pd.DataFrame({"slowk": [25], "slowd": [30]})
    config = {"momentum": {"enabled": True, "kd": {"enabled": True}}}

    plan = prepare_indicator_reuse(frame, config, {"config_schema_version": 0})

    assert plan.reused_indicators == frozenset({"kd"})
    assert plan.frame["SlowK"].tolist() == [25]
    assert plan.frame["SlowD"].tolist() == [30]


def test_causal_policy_keeps_provided_unknown_indicators_without_future_presence_choice() -> None:
    frame = pd.DataFrame({"RSI": [None, None]})
    config = {"momentum": {"enabled": True, "rsi": {"enabled": True}}}
    original = prepare_indicator_reuse(frame, config, None)
    causal = prepare_indicator_reuse(frame, config, {"input_preparation_policy": "causal-score-input.v1"})
    assert "rsi" not in original.reused_indicators
    assert causal.reused_indicators == frozenset({"rsi"})
    assert causal.frame["RSI"].isna().all()
    assert causal.technical_config["momentum"]["rsi"]["enabled"] is False


def test_custom_rsi_period_is_not_reused() -> None:
    frame = pd.DataFrame({"RSI": [50]})
    config = {
        "momentum": {
            "enabled": True,
            "rsi": {"enabled": True, "timeperiod": 7},
        }
    }

    plan = prepare_indicator_reuse(frame, config, {"config_schema_version": 0})

    assert "rsi" not in plan.reused_indicators
    assert plan.technical_config["momentum"]["rsi"]["enabled"] is True


def test_all_invalid_indicator_values_are_not_reused() -> None:
    frame = pd.DataFrame({"RSI": [math.nan, math.nan]})
    config = {"momentum": {"enabled": True, "rsi": {"enabled": True}}}

    plan = prepare_indicator_reuse(frame, config, {"config_schema_version": 0})

    assert "rsi" not in plan.reused_indicators


def test_schema_v1_missing_parameter_still_fails_closed() -> None:
    frame = pd.DataFrame({"RSI": [50]})
    config = {"momentum": {"enabled": True, "rsi": {"enabled": True}}}

    with pytest.raises(InvalidParameterError):
        prepare_indicator_reuse(frame, config, {"config_schema_version": 1})


def test_reused_macd_preserves_observed_signal_and_missing_values_for_scorer() -> None:
    from decision_module.scoring_engine import ScoringEngine

    frame = pd.DataFrame({
        "MACD": [1, 2, 3], "MACD_signal": [0, math.nan, 2], "MACD_hist": [1, math.nan, 1]
    })
    before = frame.copy(deep=True)
    config = {"momentum": {"enabled": True, "macd": {"enabled": True}}}
    plan = prepare_indicator_reuse(frame, config, {"config_schema_version": 0})

    assert plan.reused_indicators == frozenset({"macd"})
    assert plan.technical_config["momentum"]["macd"]["enabled"] is False
    pd.testing.assert_series_equal(plan.frame["MACD_Signal"], frame["MACD_signal"], check_names=False)
    pd.testing.assert_frame_equal(frame, before)
    scorer = ScoringEngine()
    actual = scorer.calculate_indicator_score(plan.frame, {"technical": config})
    reference = scorer.calculate_indicator_score(
        frame.rename(columns={"MACD_signal": "MACD_Signal"}), {"technical": config}
    )
    pd.testing.assert_series_equal(actual, reference)
    assert actual.notna().tolist() == [True, False, True]


def test_reused_macd_keeps_existing_scorer_alias_priority() -> None:
    frame = pd.DataFrame({"MACD": [2], "MACD_signal": [1], "MACD_hist": [1], "MACD_Signal": [3]})
    config = {"momentum": {"enabled": True, "macd": {"enabled": True}}}

    plan = prepare_indicator_reuse(frame, config, {"config_schema_version": 0})

    assert plan.frame["MACD_Signal"].tolist() == [3]
    assert plan.frame["MACD_signal"].tolist() == [1]


def test_missing_macd_signal_cannot_be_reused_or_filled_as_neutral() -> None:
    from decision_module.scoring_engine import ScoringEngine

    frame = pd.DataFrame({"MACD": [1, 2], "MACD_signal": [math.nan, math.nan], "MACD_hist": [1, 2]})
    config = {"momentum": {"enabled": True, "macd": {"enabled": True}}}

    plan = prepare_indicator_reuse(frame, config, {"config_schema_version": 0})

    assert "macd" not in plan.reused_indicators
    assert "MACD_Signal" not in plan.frame
    assert plan.technical_config["momentum"]["macd"]["enabled"] is True
    assert ScoringEngine().calculate_indicator_score(plan.frame, {"technical": config}).isna().all()
