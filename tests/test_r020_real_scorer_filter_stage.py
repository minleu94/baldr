from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import pytest

from app_module.recommendation_dataframe_provider import (
    RecommendationDataFrameProvider,
    ReplayProviderCallResultV1,
)
from decision_module.recommendation.evaluate import (
    NeedCandidateScoring,
    RecommendationEvaluator,
    ReplayCandidateScoringOutcomeV1,
    ReplayScorerDispositionV1,
    ReplayScorerResponseV1,
)
from decision_module.strategy_configurator import StrategyConfigurator




def _synthetic_history(
    row_count: int,
    stock_code: str,
    *,
    final_volume: int,
    rsi: int = 50,
) -> pd.DataFrame:
    dates = pd.date_range("2026-09-01", periods=row_count, freq="D")
    volumes = [1000] * (row_count - 1) + [final_volume]
    return pd.DataFrame(
        {
            "日期": [int(value.strftime("%Y%m%d")) for value in dates],
            "證券代號": [stock_code] * row_count,
            "證券名稱": [f"名稱-{stock_code}"] * row_count,
            "開盤價": [100.0] * row_count,
            "最高價": [101.0] * row_count,
            "最低價": [99.0] * row_count,
            "收盤價": [100.0] * row_count,
            "成交股數": volumes,
            "RSI": [rsi] * row_count,
        }
    )


def _capture_scorer_terminals(
    monkeypatch: pytest.MonkeyPatch,
) -> list[ReplayCandidateScoringOutcomeV1]:
    terminals: list[ReplayCandidateScoringOutcomeV1] = []
    original = RecommendationEvaluator.complete_replay_scoring

    def observe_terminal(
        evaluator: RecommendationEvaluator,
        step: Any,
        response: ReplayScorerResponseV1,
    ) -> ReplayCandidateScoringOutcomeV1:
        outcome = original(evaluator, step, response)
        terminals.append(outcome)
        return outcome

    monkeypatch.setattr(
        RecommendationEvaluator,
        "complete_replay_scoring",
        observe_terminal,
    )
    return terminals


def _run_real_provider(
    history: pd.DataFrame,
    config: dict[str, Any],
) -> ReplayProviderCallResultV1:
    provider = RecommendationDataFrameProvider()
    assert type(provider.strategy_configurator) is StrategyConfigurator
    as_of = pd.to_datetime(history["日期"].max(), format="%Y%m%d").date()
    return provider.run_with_as_of_handoff(
        history,
        config,
        top_n=10,
        as_of_date=as_of,
    )


def test_real_volume_scorer_applies_twenty_row_fallback_after_prefilter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """20 列不足以產生快篩量比，但既有 scorer 仍用 19 列衍生量比篩選。"""

    history = _synthetic_history(20, "VOL20", final_volume=1000)
    config = {"filters": {"volume_ratio_min": 1.5}}
    direct_legacy = StrategyConfigurator().generate_recommendations(
        history.copy(deep=True), config
    )
    assert direct_legacy.empty

    terminals = _capture_scorer_terminals(monkeypatch)
    provider = RecommendationDataFrameProvider()
    assert type(provider.strategy_configurator) is StrategyConfigurator
    scorer_calls: list[tuple[int, int]] = []
    original_generate = provider.strategy_configurator.generate_recommendations

    def observe_generate(frame: pd.DataFrame, received_config: dict[str, Any]) -> pd.DataFrame:
        scored = original_generate(frame, received_config)
        scorer_calls.append((len(frame), len(scored)))
        return scored

    monkeypatch.setattr(
        provider.strategy_configurator,
        "generate_recommendations",
        observe_generate,
    )
    result = provider.run_with_as_of_handoff(
        history,
        config,
        top_n=10,
        as_of_date=date(2026, 9, 20),
    )

    assert scorer_calls == [(20, 0)]
    assert len(terminals) == 1
    assert type(terminals[0].request) is NeedCandidateScoring
    assert terminals[0].request.stock_code == "VOL20"
    assert terminals[0].response.disposition is ReplayScorerDispositionV1.SKIPPED_EMPTY
    assert result.rows == []
    assert result.scoring_outcomes == ()
    assert result.as_of_date == date(2026, 9, 20)


def test_real_twenty_one_row_scorer_matches_frozen_v1_row_and_typed_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """21 列快篩與 StrategyConfigurator 都接受 50% 量增，v1 row 仍可見。"""

    history = _synthetic_history(21, "VOL21", final_volume=1500)
    config = {"filters": {"volume_ratio_min": 1.5}}

    # 這是實際 legacy scorer 的獨立同模式基準，固定可觀測欄位，非由 provider
    # 輸出反推期望。漲幅為 0、量增為 50%，故經其原本 hard filter 後只留末列。
    direct_legacy = StrategyConfigurator().generate_recommendations(
        history.copy(deep=True), config
    )
    assert len(direct_legacy) == 1
    legacy_row = direct_legacy.iloc[-1]
    assert str(legacy_row["TotalScore"]) == "50.00"
    assert str(legacy_row["IndicatorScore"]) == "50"
    assert legacy_row["PatternScore"] == 50.0
    assert legacy_row["VolumeScore"] == 50.0
    assert "BrokerFlowScore" not in direct_legacy.columns
    assert "RevenueScore" not in direct_legacy.columns
    assert str(legacy_row["成交量變化率%"]) == "50.0"

    terminals = _capture_scorer_terminals(monkeypatch)
    result = _run_real_provider(history, config)

    assert [
        (outcome.request.stock_code, outcome.response.disposition)
        for outcome in terminals
    ] == [("VOL21", ReplayScorerDispositionV1.SCORED)]
    assert result.rows == [
        {
            "stock_code": "VOL21",
            "stock_name": "名稱-VOL21",
            "total_score": 50.0,
            "factor_scores": {
                "technical": 50.0,
                "pattern": 50.0,
                "volume": 50.0,
                "broker_flow": 0.0,
                "revenue": 0.0,
            },
            "selection_reason": "符合策略條件",
        }
    ]
    assert type(result.rows[0]["total_score"]) is float
    assert all(
        type(value) is float for value in result.rows[0]["factor_scores"].values()
    )
    assert len(result.rows) == len(result.scoring_outcomes) == 1
    outcome = result.scoring_outcomes[0]
    assert outcome is not None
    assert outcome.request.stock_code == result.rows[0]["stock_code"]
    assert outcome.response.disposition is ReplayScorerDispositionV1.SCORED


def test_rsi_only_filter_is_applied_by_real_scorer_after_fast_prefilter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RSI 不屬 fast policy；既有 scorer 對 RSI=50/min=101 回空列。"""

    history = _synthetic_history(21, "RSI50", final_volume=1000, rsi=50)
    config = {"filters": {"rsi_min": 101}}
    direct_legacy = StrategyConfigurator().generate_recommendations(
        history.copy(deep=True), config
    )
    assert direct_legacy.empty

    terminals = _capture_scorer_terminals(monkeypatch)
    provider = RecommendationDataFrameProvider()
    assert type(provider.strategy_configurator) is StrategyConfigurator
    scorer_calls: list[tuple[int, int]] = []
    original_generate = provider.strategy_configurator.generate_recommendations

    def observe_generate(frame: pd.DataFrame, received_config: dict[str, Any]) -> pd.DataFrame:
        scored = original_generate(frame, received_config)
        scorer_calls.append((len(frame), len(scored)))
        return scored

    monkeypatch.setattr(
        provider.strategy_configurator,
        "generate_recommendations",
        observe_generate,
    )
    result = provider.run_with_as_of_handoff(
        history,
        config,
        top_n=10,
        as_of_date=date(2026, 9, 21),
    )

    assert scorer_calls == [(21, 0)]
    assert len(terminals) == 1
    assert type(terminals[0].request) is NeedCandidateScoring
    assert terminals[0].request.stock_code == "RSI50"
    assert terminals[0].response.disposition is ReplayScorerDispositionV1.SKIPPED_EMPTY
    assert result.rows == []
    assert result.scoring_outcomes == ()
