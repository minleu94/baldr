from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import pytest

import decision_module.strategy_configurator as strategy_module
from decision_module.strategy_configurator import (
    StrategyConfigurator,
    observe_screening_diagnostics,
)


def _price_frame(value: Any = 0.0) -> pd.DataFrame:
    return pd.DataFrame({"證券代號": ["SYN"], "漲幅%": [value]})


def _volume_frame(value: Any = 0.0) -> pd.DataFrame:
    return pd.DataFrame({"證券代號": ["SYN"], "成交量變化率%": [value]})


def test_observer_keeps_warning_counter_and_later_volume_error_order(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls: list[tuple[int, dict[str, Any]]] = []
    original = strategy_module.filter_completed_frame

    def observe(frame: pd.DataFrame, filters: dict[str, Any]) -> pd.DataFrame:
        calls.append((len(frame), dict(filters)))
        return original(frame, filters)

    monkeypatch.setattr(strategy_module, "filter_completed_frame", observe)
    monkeypatch.setattr(StrategyConfigurator, "_price_filter_log_count", 0, raising=False)
    monkeypatch.setattr(StrategyConfigurator, "_volume_filter_log_count", 0, raising=False)
    caplog.set_level("WARNING", logger="decision_module.strategy_configurator")

    with pytest.raises(TypeError, match="Invalid comparison between dtype=float64 and str"):
        observe_screening_diagnostics(
            pd.DataFrame(
                {
                    "證券代號": ["SYN"],
                    "漲幅%": [0.0],
                    "成交量變化率%": [20.0],
                }
            ),
            {"price_change_min": 100, "volume_ratio_min": "bad"},
            logger=logging.getLogger("decision_module.strategy_configurator"),
            counter_owner=StrategyConfigurator,
        )

    assert calls == [
        (1, {"price_change_min": 100}),
        (0, {"volume_ratio_min": "bad"}),
    ]
    assert [record.message for record in caplog.records if record.levelname == "WARNING"] == [
        "[漲幅篩選] 要求 >= 100%, 但樣本值=0.00%"
    ]
    assert getattr(StrategyConfigurator, "_price_filter_log_count") == 1
    assert getattr(StrategyConfigurator, "_volume_filter_log_count") == 0


def test_observer_caps_each_warning_counter_across_candidates(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(StrategyConfigurator, "_price_filter_log_count", 0, raising=False)
    monkeypatch.setattr(StrategyConfigurator, "_volume_filter_log_count", 0, raising=False)
    caplog.set_level("WARNING", logger="decision_module.strategy_configurator")
    logger = logging.getLogger("decision_module.strategy_configurator")

    for _ in range(4):
        observe_screening_diagnostics(
            _price_frame(),
            {"price_change_min": 100},
            logger=logger,
            counter_owner=StrategyConfigurator,
        )
        observe_screening_diagnostics(
            _volume_frame(),
            {"volume_ratio_min": 100},
            logger=logger,
            counter_owner=StrategyConfigurator,
        )

    messages = [record.message for record in caplog.records if record.levelname == "WARNING"]
    assert messages == [
        "[漲幅篩選] 要求 >= 100%, 但樣本值=0.00%",
        "[成交量篩選] 要求 >= 100.00%, 但樣本值=0.00%",
    ] * 3
    assert getattr(StrategyConfigurator, "_price_filter_log_count") == 4
    assert getattr(StrategyConfigurator, "_volume_filter_log_count") == 4


def test_observer_keeps_missing_columns_and_price_max_missing_min_key_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    original = strategy_module.filter_completed_frame

    def observe(frame: pd.DataFrame, filters: dict[str, Any]) -> pd.DataFrame:
        calls.append(dict(filters))
        return original(frame, filters)

    monkeypatch.setattr(strategy_module, "filter_completed_frame", observe)
    monkeypatch.setattr(StrategyConfigurator, "_price_filter_log_count", 0, raising=False)
    monkeypatch.setattr(StrategyConfigurator, "_volume_filter_log_count", 0, raising=False)
    logger = logging.getLogger("decision_module.strategy_configurator")

    observe_screening_diagnostics(
        pd.DataFrame({"證券代號": ["MISSING"]}),
        {"price_change_min": "bad", "volume_ratio_min": "bad"},
        logger=logger,
        counter_owner=StrategyConfigurator,
    )
    assert calls == []
    assert getattr(StrategyConfigurator, "_price_filter_log_count") == 0
    assert getattr(StrategyConfigurator, "_volume_filter_log_count") == 0

    with pytest.raises(KeyError, match="price_change_min"):
        observe_screening_diagnostics(
            _price_frame(2.0),
            {"price_change_max": 0.0},
            logger=logger,
            counter_owner=StrategyConfigurator,
        )
    assert calls == [{"price_change_max": 0.0}]
    # 舊 warning 分支先遞增類別 counter，再於讀取缺少的 min key 時拋錯。
    assert getattr(StrategyConfigurator, "_price_filter_log_count") == 1
    assert getattr(StrategyConfigurator, "_volume_filter_log_count") == 0


def test_screen_stocks_uses_observer_and_keeps_final_filter_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, dict[str, Any]]] = []
    original = strategy_module.observe_screening_diagnostics

    def observe(
        frame: pd.DataFrame,
        filters: dict[str, Any],
        *,
        logger: logging.Logger,
        counter_owner: Any,
    ) -> None:
        calls.append((len(frame), dict(filters)))
        original(frame, filters, logger=logger, counter_owner=counter_owner)

    monkeypatch.setattr(strategy_module, "observe_screening_diagnostics", observe)
    result = StrategyConfigurator().screen_stocks(
        pd.DataFrame(
            {
                "證券代號": ["DROP", "KEEP"],
                "漲幅%": [0.0, 5.0],
                "成交量變化率%": [0.0, 30.0],
                "RSI": [30, 70],
            }
        ),
        {"price_change_min": 1.0, "volume_ratio_min": 20.0},
    )

    assert calls == [(2, {"price_change_min": 1.0, "volume_ratio_min": 20.0})]
    assert result["證券代號"].tolist() == ["KEEP"]
