"""固定 post-score 欄位缺席與 numeric projector 不支援值的 legacy 差異。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pandas as pd
import pytest

import decision_module.strategy_configurator as strategy_module
from app_module.recommendation.replay_numeric_projection import (
    ReplayThresholdUnit,
    UnsupportedReplayNumericScalarError,
    project_legacy_comparison_pair,
)
from decision_module.strategy_configurator import StrategyConfigurator


def _unsupported_projection(value: object) -> None:
    project_legacy_comparison_pair(
        value,
        0.0,
        unit=ReplayThresholdUnit.PRICE_CHANGE_PERCENT,
    )


def test_missing_price_column_skips_invalid_threshold_and_keeps_candidate(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """缺欄時 legacy 診斷與最終 filter 都不比較無效 threshold。"""

    monkeypatch.setattr(StrategyConfigurator, "_price_filter_log_count", 0, raising=False)
    caplog.set_level("WARNING", logger="decision_module.strategy_configurator")

    result = StrategyConfigurator().screen_stocks(
        pd.DataFrame({"證券代號": ["MISSING"]}),
        {"price_change_min": "bad"},
    )

    assert result["證券代號"].tolist() == ["MISSING"]
    assert not [record for record in caplog.records if record.levelname == "WARNING"]
    assert getattr(StrategyConfigurator, "_price_filter_log_count") == 0


def test_present_decimal_metric_is_projector_unsupported_and_legacy_compare_raises(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """存在的 Decimal object metric 走舊比較並在 threshold 解析前拋原生 TypeError。"""

    metric = Decimal("1.25")
    with pytest.raises(UnsupportedReplayNumericScalarError):
        _unsupported_projection(metric)

    calls: list[tuple[int, dict[str, Any]]] = []
    original = strategy_module.filter_completed_frame

    def observe(frame: pd.DataFrame, filters: Any) -> pd.DataFrame:
        calls.append((len(frame), dict(filters)))
        return original(frame, filters)

    monkeypatch.setattr(strategy_module, "filter_completed_frame", observe)
    monkeypatch.setattr(StrategyConfigurator, "_price_filter_log_count", 0, raising=False)
    caplog.set_level("WARNING", logger="decision_module.strategy_configurator")

    frame = pd.DataFrame(
        {
            "證券代號": ["DECIMAL"],
            "漲幅%": pd.Series([metric], dtype=object),
        }
    )
    with pytest.raises(
        TypeError,
        match=r"'>=' not supported between instances of 'decimal\.Decimal' and 'str'",
    ):
        StrategyConfigurator().screen_stocks(frame, {"price_change_min": "bad"})

    assert calls == [(1, {"price_change_min": "bad"})]
    assert not [record for record in caplog.records if record.levelname == "WARNING"]
    assert getattr(StrategyConfigurator, "_price_filter_log_count") == 0


def test_present_pd_na_metric_is_projector_unsupported_but_legacy_excludes_and_warns(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """object-dtype pd.NA 原生比較不通過，並觸發 legacy 警告。"""

    with pytest.raises(UnsupportedReplayNumericScalarError):
        _unsupported_projection(pd.NA)

    monkeypatch.setattr(StrategyConfigurator, "_price_filter_log_count", 0, raising=False)
    caplog.set_level("WARNING", logger="decision_module.strategy_configurator")

    frame = pd.DataFrame(
        {
            "證券代號": ["PD_NA"],
            "漲幅%": pd.Series([pd.NA], dtype=object),
        }
    )
    result = StrategyConfigurator().screen_stocks(
        frame,
        {"price_change_min": "bad"},
    )

    assert result.empty
    assert [record.message for record in caplog.records if record.levelname == "WARNING"] == [
        "[漲幅篩選] 要求 >= bad%, 但樣本值=<NA>%"
    ]
    assert getattr(StrategyConfigurator, "_price_filter_log_count") == 1
