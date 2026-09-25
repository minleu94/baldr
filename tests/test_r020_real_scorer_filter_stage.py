from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import pytest

from app_module.recommendation_dataframe_provider import (
    RecommendationDataFrameProvider,
    ReplayProviderCallResultV1,
)
from app_module.recommendation_replay_service import RecommendationReplayService
from decision_module.recommendation.evaluate import (
    RecommendationEvaluator,
    ReplayPostScoreDispositionV1,
    ReplayPostScoreEvaluationStepV1,
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


def _capture_post_score_terminals(
    monkeypatch: pytest.MonkeyPatch,
) -> list[ReplayPostScoreDispositionV1]:
    terminals: list[ReplayPostScoreDispositionV1] = []
    original = RecommendationEvaluator.advance_replay_post_score_staged

    def observe_terminal(
        evaluator: RecommendationEvaluator,
        step: ReplayPostScoreEvaluationStepV1,
        response: Any,
    ) -> ReplayPostScoreEvaluationStepV1:
        terminal = original(evaluator, step, response)
        if terminal.outcome is not None:
            terminals.append(terminal.outcome.disposition)
        return terminal

    monkeypatch.setattr(
        RecommendationEvaluator,
        "advance_replay_post_score_staged",
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


def _capture_builtin_scorer_config(
    provider: RecommendationDataFrameProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> list[dict[str, Any] | None]:
    """透過 built-in 技術準備邊界觀察完整 scorer config，不覆寫 scorer。"""

    received: list[dict[str, Any] | None] = []
    original = provider.strategy_configurator.configure_technical_indicators

    def observe_config(
        frame: pd.DataFrame,
        technical_config: dict[str, Any],
        full_config: dict[str, Any] | None = None,
    ) -> pd.DataFrame:
        received.append(None if full_config is None else dict(full_config))
        return original(frame, technical_config, full_config)

    monkeypatch.setattr(
        provider.strategy_configurator,
        "configure_technical_indicators",
        observe_config,
    )
    return received


def test_real_volume_scorer_is_unfiltered_then_replay_evaluator_rejects_twenty_row_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """20 列 scorer 產生 fallback 量比後，由 replay evaluator 拒絕。"""

    history = _synthetic_history(20, "VOL20", final_volume=1000)
    config = {"filters": {"volume_ratio_min": 1.5}}
    direct_legacy = StrategyConfigurator().generate_recommendations(
        history.copy(deep=True), config
    )
    assert direct_legacy.empty

    terminals = _capture_scorer_terminals(monkeypatch)
    post_score_terminals = _capture_post_score_terminals(monkeypatch)
    provider = RecommendationDataFrameProvider()
    assert type(provider.strategy_configurator) is StrategyConfigurator
    scorer_configs = _capture_builtin_scorer_config(provider, monkeypatch)
    result = provider.run_with_as_of_handoff(
        history,
        config,
        top_n=10,
        as_of_date=date(2026, 9, 20),
    )

    assert scorer_configs == [{}]
    assert config == {"filters": {"volume_ratio_min": 1.5}}
    assert len(terminals) == 1
    assert terminals[0].response.disposition is ReplayScorerDispositionV1.SKIPPED_EMPTY
    assert post_score_terminals == [ReplayPostScoreDispositionV1.REJECTED]
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


def test_builtin_replay_scorer_builds_canonical_child_after_post_score_accept() -> None:
    history = _synthetic_history(21, "BUILTIN-CHILD", final_volume=1500)
    parent_id = "parent-r020-builtin-post-score"
    snapshot = RecommendationReplayService(
        RecommendationDataFrameProvider()
    ).run_snapshot(
        as_of_date="2026-09-21",
        profile_id="profile-r020-builtin-post-score",
        config={"filters": {"volume_ratio_min": 1.5}},
        history=history,
        universe=None,
        top_n=10,
        parent_result_id=parent_id,
    )

    assert [row["stock_code"] for row in snapshot.recommendations] == [
        "BUILTIN-CHILD"
    ]
    child = snapshot.canonical_execution
    assert child is not None
    assert child.related_references[0].reference_id == parent_id
    decision = child.decision
    assert decision is not None
    assert [item.stock_code for item in decision.items] == [
        "BUILTIN-CHILD"
    ]
    assert [assessment.stock_code for assessment in decision.assessments] == [
        "BUILTIN-CHILD"
    ]


def test_real_rsi_scorer_is_unfiltered_then_replay_evaluator_rejects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RSI 不屬 fast policy；無 filters scorer 返回列後由 replay evaluator 拒絕。"""

    history = _synthetic_history(21, "RSI50", final_volume=1000, rsi=50)
    config = {"filters": {"rsi_min": 101}}
    direct_legacy = StrategyConfigurator().generate_recommendations(
        history.copy(deep=True), config
    )
    assert direct_legacy.empty

    provider = RecommendationDataFrameProvider()
    assert type(provider.strategy_configurator) is StrategyConfigurator
    scorer_configs = _capture_builtin_scorer_config(provider, monkeypatch)
    scorer_terminals = _capture_scorer_terminals(monkeypatch)
    post_score_terminals = _capture_post_score_terminals(monkeypatch)
    result = provider.run_with_as_of_handoff(
        history,
        config,
        top_n=10,
        as_of_date=date(2026, 9, 21),
    )

    assert scorer_configs == [{}]
    assert config == {"filters": {"rsi_min": 101}}
    assert len(scorer_terminals) == 1
    assert scorer_terminals[0].response.disposition is ReplayScorerDispositionV1.SKIPPED_EMPTY
    assert post_score_terminals == [ReplayPostScoreDispositionV1.REJECTED]
    assert result.rows == []
    assert result.scoring_outcomes == ()


@pytest.mark.parametrize(
    "config",
    [
        {},
        {"filters": {"price_change_min": -1}},
        {"filters": {"volume_ratio_min": 0}},
        {"filters": {"rsi_min": 40}},
        {"filters": None},
    ],
)
def test_custom_strategy_keeps_v1_rows_without_canonical_scoring_child(
    config: dict[str, Any],
) -> None:
    """自訂 scorer 對空、price、volume、RSI、None filters 僅保留 v1。"""

    class CustomStrategyConfigurator(StrategyConfigurator):
        def generate_recommendations(
            self, frame: pd.DataFrame, received_config: dict[str, Any]
        ) -> pd.DataFrame:
            assert received_config == config
            result = frame.iloc[[-1]].copy()
            result["漲幅%"] = 0.0
            result["成交量變化率%"] = 0.0
            result["FinalScore"] = 7.0
            result["IndicatorScore"] = 3.0
            result["PatternScore"] = 2.0
            result["VolumeScore"] = 1.0
            return result

    history = _synthetic_history(21, "CUSTOM", final_volume=1000, rsi=50)
    provider = RecommendationDataFrameProvider()
    provider.strategy_configurator = CustomStrategyConfigurator()

    result = provider.run_with_as_of_handoff(
        history,
        config,
        top_n=10,
        as_of_date=date(2026, 9, 21),
    )

    assert len(result.rows) == 1
    assert result.rows[0]["stock_code"] == "CUSTOM"
    assert result.scoring_outcomes == (None,)


def test_overridden_builtin_scorer_is_v1_only_without_filter_shape_inspection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = _synthetic_history(21, "OVERRIDE", final_volume=1500, rsi=50)
    config = {"filters": None}
    provider = RecommendationDataFrameProvider()
    observed_configs: list[dict[str, Any]] = []

    def override(frame: pd.DataFrame, received_config: dict[str, Any]) -> pd.DataFrame:
        observed_configs.append(received_config.copy())
        result = frame.iloc[[-1]].copy()
        result["漲幅%"] = 0.0
        result["成交量變化率%"] = 50.0
        result["FinalScore"] = 7.0
        return result

    monkeypatch.setattr(
        provider.strategy_configurator,
        "generate_recommendations",
        override,
    )
    result = provider.run_with_as_of_handoff(
        history,
        config,
        top_n=10,
        as_of_date=date(2026, 9, 21),
    )

    assert observed_configs == [config]
    assert len(result.rows) == 1
    assert result.rows[0]["stock_code"] == "OVERRIDE"
    assert result.scoring_outcomes == (None,)


@pytest.mark.parametrize(
    ("filter_key", "expected_screen_warning"),
    [
        ("price_change_min", True),
        ("rsi_min", False),
    ],
)
def test_present_none_threshold_keeps_legacy_rejection_and_diagnostics(
    filter_key: str,
    expected_screen_warning: bool,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    history = _synthetic_history(21, "NONE", final_volume=1000, rsi=50)
    config = {"filters": {filter_key: None}}
    monkeypatch.setattr(StrategyConfigurator, "_filter_log_count", 0, raising=False)
    monkeypatch.setattr(StrategyConfigurator, "_price_filter_log_count", 0, raising=False)
    assert StrategyConfigurator().generate_recommendations(
        history.copy(deep=True), config
    ).empty

    caplog.set_level("WARNING", logger="decision_module.strategy_configurator")
    provider = RecommendationDataFrameProvider()
    terminals = _capture_scorer_terminals(monkeypatch)
    post_score_terminals = _capture_post_score_terminals(monkeypatch)

    result = provider.run_with_as_of_handoff(
        history,
        config,
        top_n=10,
        as_of_date=date(2026, 9, 21),
    )

    assert result.rows == []
    assert result.scoring_outcomes == ()
    assert [terminal.response.disposition for terminal in terminals] == [
        ReplayScorerDispositionV1.SKIPPED_EMPTY
    ]
    assert post_score_terminals == [ReplayPostScoreDispositionV1.REJECTED]
    warning_messages = [record.getMessage() for record in caplog.records]
    assert any(message.startswith("[篩選診斷 #") for message in warning_messages)
    assert any(message.startswith("[漲幅篩選]") for message in warning_messages) is expected_screen_warning


@pytest.mark.parametrize(
    ("filter_key", "expected_error_type", "expected_error_message"),
    [
        ("price_change_max", KeyError, "'price_change_min'"),
        ("volume_ratio_min", TypeError, "'<=' not supported"),
    ],
)
def test_present_none_legacy_error_still_occurs_after_unfiltered_scorer(
    filter_key: str,
    expected_error_type: type[Exception],
    expected_error_message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = _synthetic_history(21, "NONE-ERROR", final_volume=1000, rsi=50)
    config = {"filters": {filter_key: None}}
    # 既有 diagnostic counter 是 process-global；固定測試起點，避免前序測試
    # 消耗 warning quota 後改變 missing-min KeyError 的舊路徑觀察。
    monkeypatch.setattr(StrategyConfigurator, "_filter_log_count", 0, raising=False)
    monkeypatch.setattr(StrategyConfigurator, "_price_filter_log_count", 0, raising=False)
    with pytest.raises(expected_error_type, match=expected_error_message):
        StrategyConfigurator().generate_recommendations(
            history.copy(deep=True), config
    )

    provider = RecommendationDataFrameProvider()
    scorer_configs = _capture_builtin_scorer_config(provider, monkeypatch)
    terminals = _capture_scorer_terminals(monkeypatch)
    result = provider.run_with_as_of_handoff(
        history,
        config,
        top_n=10,
        as_of_date=date(2026, 9, 21),
    )

    assert scorer_configs == [{}]
    assert result.rows == []
    assert result.scoring_outcomes == ()
    assert len(terminals) == 1
    assert terminals[0].response.disposition is ReplayScorerDispositionV1.SKIPPED_SCORER_EXCEPTION
    assert terminals[0].response.error_type == expected_error_type.__name__
