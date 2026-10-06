from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
import pytest

import decision_module.strategy_configurator as strategy_module
from decision_module.strategy_configurator import (
    StrategyConfigurator,
    normalize_recommendation_filter_aliases,
)


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({}, {}),
        (
            {
                "min_return_pct": 1,
                "price_change_min": 2,
                "price_change_max": 8,
                "rsi_min": 40,
                "market_cap_max": 100,
            },
            {
                "price_change_min": 2,
                "price_change_max": 8,
                "rsi_min": 40,
                "market_cap_max": 100,
            },
        ),
        (
            {"min_volume_ratio": 1.5, "volume_ratio_min": 1.3},
            {"volume_ratio_min": 50.0},
        ),
    ],
)
def test_alias_precedence_and_passthrough_match_legacy_mapping(
    filters: dict[str, Any], expected: dict[str, Any]
) -> None:
    original = filters.copy()

    assert normalize_recommendation_filter_aliases(filters) == expected
    assert filters == original


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (-50, -5100),
        (10, 900),
        (-50.0001, -50.0001),
        (10.0001, 10.0001),
    ],
)
def test_direct_volume_alias_keeps_legacy_inclusive_conversion_boundary(
    raw: float, expected: float
) -> None:
    assert normalize_recommendation_filter_aliases(
        {"volume_ratio_min": raw}
    ) == {"volume_ratio_min": expected}


@pytest.mark.parametrize("raw", [np.float16(1.5), np.float32(1.5), np.float64(1.5), np.int64(2)])
def test_volume_conversion_preserves_native_numpy_scalar_type(raw: Any) -> None:
    result = normalize_recommendation_filter_aliases({"min_volume_ratio": raw})

    expected = (raw - 1) * 100
    assert result["volume_ratio_min"] == expected
    assert type(result["volume_ratio_min"]) is type(expected)


def test_none_and_nullable_values_keep_legacy_conversion_failures_and_passthrough() -> None:
    assert normalize_recommendation_filter_aliases({"min_return_pct": pd.NA}) == {
        "price_change_min": pd.NA
    }

    with pytest.raises(TypeError):
        normalize_recommendation_filter_aliases({"min_volume_ratio": None})
    with pytest.raises(TypeError):
        normalize_recommendation_filter_aliases({"volume_ratio_min": None})


def test_generate_recommendations_uses_shared_alias_helper_after_scoring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = pd.DataFrame(
        {
            "證券代號": ["SYN"],
            "日期": [20260924],
            "漲幅%": [0.0],
            "成交量變化率%": [20.0],
            "TotalScore": [50.0],
            "IndicatorScore": [50.0],
            "PatternScore": [0.0],
            "VolumeScore": [0.0],
        }
    )
    configurator = StrategyConfigurator()
    stage_order: list[str] = []
    screen_filters: list[dict[str, Any]] = []
    original_helper = strategy_module.normalize_recommendation_filter_aliases

    def observe_helper(filters: Any) -> dict[str, Any]:
        stage_order.append("normalize")
        return original_helper(filters)

    monkeypatch.setattr(
        strategy_module, "normalize_recommendation_filter_aliases", observe_helper
    )
    monkeypatch.setattr(
        configurator,
        "configure_technical_indicators",
        lambda data, _technical, *, full_config: data,
    )

    def score(data: pd.DataFrame, _config: dict[str, Any], *, regime: Any = None) -> pd.DataFrame:
        stage_order.append("score")
        return data

    monkeypatch.setattr(configurator.scoring_engine, "calculate_total_score", score)

    def screen(data: pd.DataFrame, filters: dict[str, Any]) -> pd.DataFrame:
        stage_order.append("screen")
        screen_filters.append(dict(filters))
        return data

    monkeypatch.setattr(configurator, "screen_stocks", screen)
    monkeypatch.setattr(strategy_module, "build_recommendation_row", lambda data: data)

    result = configurator.generate_recommendations(
        frame,
        {
            "filters": {
                "min_return_pct": 1,
                "price_change_min": 2,
                "min_volume_ratio": 1.5,
                "volume_ratio_min": 1.3,
            }
        },
    )

    assert not result.empty
    assert stage_order == ["score", "normalize", "screen"]
    assert screen_filters == [
        {"price_change_min": 2, "volume_ratio_min": 50.0}
    ]


def test_bad_direct_volume_alias_still_raises_after_scoring_before_screening(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = pd.DataFrame(
        {
            "證券代號": ["SYN"],
            "日期": [20260924],
            "漲幅%": [0.0],
            "成交量變化率%": [20.0],
            "TotalScore": [50.0],
            "IndicatorScore": [50.0],
            "PatternScore": [0.0],
            "VolumeScore": [0.0],
        }
    )
    configurator = StrategyConfigurator()
    calls: list[str] = []
    monkeypatch.setattr(
        configurator,
        "configure_technical_indicators",
        lambda data, _technical, *, full_config: data,
    )

    def score(data: pd.DataFrame, _config: dict[str, Any], *, regime: Any = None) -> pd.DataFrame:
        calls.append("score")
        return data

    monkeypatch.setattr(configurator.scoring_engine, "calculate_total_score", score)
    monkeypatch.setattr(
        configurator,
        "screen_stocks",
        lambda data, _filters: calls.append("screen") or data,
    )

    with pytest.raises(TypeError):
        configurator.generate_recommendations(
            frame, {"filters": {"volume_ratio_min": "bad"}}
        )

    assert calls == ["score"]
