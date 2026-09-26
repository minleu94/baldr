from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any, Literal
import warnings

import numpy as np
import pandas as pd
import pytest

import app_module.recommendation_dataframe_provider as replay_provider_module
import app_module.recommendation_replay_service as replay_service_module
from app_module.recommendation_dataframe_provider import (
    RecommendationDataFrameProvider,
    ReplayProviderCallResultV1,
)
from app_module.recommendation_replay_service import RecommendationReplayService
from decision_module.recommendation.evaluate import (
    RecommendationEvaluator,
    ReplayPostScoreDispositionV1,
    ReplayPostScoreEffectKindV1,
    ReplayPostScoreEffectV1,
    ReplayPostScoreEvaluationStepV1,
    ReplayCandidateScoringOutcomeV1,
    ReplayPostScoreRuleV1,
    ReplayScorerDispositionV1,
    ReplayScorerResponseV1,
)
from decision_module.recommendation.replay_prefilter import ReplayComparisonOperator
from decision_module.strategy_configurator import StrategyConfigurator


@pytest.fixture(autouse=True)
def isolate_strategy_diagnostic_counters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """隔離 legacy process-local 診斷配額，避免跨測試改變 oracle。"""

    monkeypatch.setattr(StrategyConfigurator, "_filter_log_count", 0, raising=False)
    monkeypatch.setattr(StrategyConfigurator, "_price_filter_log_count", 0, raising=False)
    monkeypatch.setattr(StrategyConfigurator, "_volume_filter_log_count", 0, raising=False)




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


def _install_fixed_post_score_metrics(
    provider: RecommendationDataFrameProvider,
    monkeypatch: pytest.MonkeyPatch,
    *,
    price_change: object,
    price_dtype: str | None = None,
    rsi: object = 50,
    rsi_dtype: str = "int64",
) -> None:
    """保留 built-in scorer 身分，只固定其 post-score scalar 輸出。"""

    monkeypatch.setattr(
        provider.strategy_configurator,
        "configure_technical_indicators",
        lambda frame, technical_config, full_config=None: frame,
    )

    def calculate_total_score(
        frame: pd.DataFrame,
        config: dict[str, Any],
        regime: Any = None,
    ) -> pd.DataFrame:
        scored = frame.copy()
        output_count = len(scored)
        price_values = np.asarray([price_change] * output_count, dtype=price_dtype)
        scored["漲幅%"] = pd.Series(price_values, index=scored.index)
        scored["成交量變化率%"] = pd.Series(
            np.asarray([20] * output_count, dtype="float64"), index=scored.index
        )
        scored["RSI"] = pd.Series(
            np.asarray([rsi] * output_count, dtype=rsi_dtype), index=scored.index
        )
        scored["TotalScore"] = 50
        scored["FinalScore"] = 50
        scored["IndicatorScore"] = 50
        scored["PatternScore"] = 0
        scored["VolumeScore"] = 0
        return scored

    monkeypatch.setattr(
        provider.strategy_configurator.scoring_engine,
        "calculate_total_score",
        calculate_total_score,
    )


def _install_post_score_side_effect_spies(
    monkeypatch: pytest.MonkeyPatch,
) -> list[str]:
    """記錄 legacy Pandas pass 與 typed paired projection 的呼叫次序。"""

    import app_module.recommendation_dataframe_provider as provider_module
    import decision_module.strategy_configurator as strategy_module

    events: list[str] = []
    original_filter = strategy_module.filter_completed_frame
    original_projection = provider_module.project_legacy_post_score_comparison_pair

    def observe_filter(frame: pd.DataFrame, filters: Any) -> pd.DataFrame:
        events.append("legacy-filter")
        return original_filter(frame, filters)

    def observe_projection(*args: Any, **kwargs: Any) -> Any:
        events.append("typed-pair-projection")
        return original_projection(*args, **kwargs)

    monkeypatch.setattr(strategy_module, "filter_completed_frame", observe_filter)
    monkeypatch.setattr(
        provider_module,
        "project_legacy_post_score_comparison_pair",
        observe_projection,
    )
    return events


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


def test_builtin_child_handoff_does_not_read_v1_rows_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Typed child 直接取 candidate/outcome，v1 row 僅作外層輸出。"""

    history = _synthetic_history(21, "TYPED-PRIMARY", final_volume=1500)
    provider = RecommendationDataFrameProvider()
    terminals = _capture_scorer_terminals(monkeypatch)

    def forbidden_rows_read(_handoff: ReplayProviderCallResultV1):
        pytest.fail("service 不得以 stored v1 rows 建立 canonical child")

    monkeypatch.setattr(
        ReplayProviderCallResultV1,
        "rows",
        property(forbidden_rows_read),
    )
    snapshot = RecommendationReplayService(provider).run_snapshot(
        as_of_date="2026-09-21",
        profile_id="profile-r020-typed-primary",
        config={"filters": {"volume_ratio_min": 1.5}},
        history=history,
        universe=None,
        top_n=10,
        parent_result_id="parent-r020-typed-primary",
    )

    assert [row["stock_code"] for row in snapshot.recommendations] == ["TYPED-PRIMARY"]
    assert [terminal.response.disposition for terminal in terminals] == [
        ReplayScorerDispositionV1.SCORED
    ]
    child = snapshot.canonical_execution
    assert child is not None
    assert [item.stock_code for item in child.decision.items] == ["TYPED-PRIMARY"]
    assert [assessment.stock_code for assessment in child.decision.assessments] == [
        "TYPED-PRIMARY"
    ]


@pytest.mark.parametrize("corruption", ["row_score", "row_reason", "row_order"])
def test_projected_v1_row_mismatch_keeps_rows_without_canonical_child(
    monkeypatch: pytest.MonkeyPatch,
    corruption: str,
) -> None:
    """v1 projection 與同次 typed 候選不一致時，不發布 canonical child。"""

    history = pd.concat(
        [
            _synthetic_history(21, "PARITY-A", final_volume=1500),
            _synthetic_history(21, "PARITY-B", final_volume=1500),
        ],
        ignore_index=True,
    )
    original = ReplayProviderCallResultV1.project_v1_rows

    def corrupted_projection(
        handoff: ReplayProviderCallResultV1,
    ) -> list[dict[str, Any]]:
        rows = original(handoff)
        if corruption == "row_score":
            rows[0]["total_score"] = 999.0
        elif corruption == "row_reason":
            rows[0]["selection_reason"] = "遭污染的相容理由"
        else:
            rows.reverse()
        return rows

    monkeypatch.setattr(
        ReplayProviderCallResultV1,
        "project_v1_rows",
        corrupted_projection,
    )

    snapshot = RecommendationReplayService(
        RecommendationDataFrameProvider()
    ).run_snapshot(
        as_of_date="2026-09-21",
        profile_id=f"profile-r020-projection-mismatch-{corruption}",
        config={"filters": {"volume_ratio_min": 1.5}},
        history=history,
        universe=None,
        top_n=10,
        parent_result_id=f"parent-r020-projection-mismatch-{corruption}",
    )

    assert len(snapshot.recommendations) == 2
    if corruption == "row_score":
        assert snapshot.recommendations[0]["total_score"] == 999.0
    elif corruption == "row_reason":
        assert snapshot.recommendations[0]["selection_reason"] == "遭污染的相容理由"
    else:
        assert [row["stock_code"] for row in snapshot.recommendations] == [
            "PARITY-B",
            "PARITY-A",
        ]
    assert snapshot.canonical_execution is None


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


@pytest.mark.parametrize("dtype", ["float16", "float32"])
def test_provider_pair_projection_keeps_native_overflow_warning_sequence(
    dtype: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """診斷 pass 與 paired projection 的 overflow warnings 數量和順序要相同。"""

    history = _synthetic_history(21, "OVERFLOW", final_volume=1000, rsi=50)
    config = {"filters": {"price_change_max": 1e100}}
    provider = RecommendationDataFrameProvider()
    _install_fixed_post_score_metrics(
        provider,
        monkeypatch,
        price_change=1,
        price_dtype=dtype,
    )
    events = _install_post_score_side_effect_spies(monkeypatch)
    caplog.set_level("WARNING", logger=StrategyConfigurator.__module__)

    monkeypatch.setattr(StrategyConfigurator, "_filter_log_count", 0, raising=False)
    monkeypatch.setattr(StrategyConfigurator, "_price_filter_log_count", 0, raising=False)
    events.clear()
    with np.errstate(over="warn"):
        with warnings.catch_warnings(record=True) as legacy_warnings:
            warnings.simplefilter("always")
            legacy_rows = provider(history.copy(deep=True), config, 10)
    legacy_events = list(events)
    legacy_warning_messages = [str(item.message) for item in legacy_warnings]
    legacy_warning_categories = [type(item.message) for item in legacy_warnings]
    legacy_log_messages = [record.getMessage() for record in caplog.records]

    monkeypatch.setattr(StrategyConfigurator, "_filter_log_count", 0, raising=False)
    monkeypatch.setattr(StrategyConfigurator, "_price_filter_log_count", 0, raising=False)
    caplog.clear()
    events.clear()
    with np.errstate(over="warn"):
        with warnings.catch_warnings(record=True) as provider_warnings:
            warnings.simplefilter("always")
            replay_result = provider.run_with_as_of_handoff(
                history.copy(deep=True),
                config,
                top_n=10,
                as_of_date=date(2026, 9, 21),
            )

    assert len(legacy_rows) == 1
    assert len(replay_result.rows) == 1
    # 每個 runtime 以自己的 native 執行作 oracle；NumPy 1.26 與 2.3
    # 對低精度 overflow 的 warning 數不同，但同一 runtime 兩條路必須相等。
    assert [str(item.message) for item in provider_warnings] == legacy_warning_messages
    assert [type(item.message) for item in provider_warnings] == legacy_warning_categories
    assert legacy_events == ["legacy-filter", "legacy-filter"]
    assert events == ["legacy-filter", "typed-pair-projection"]
    assert [record.getMessage() for record in caplog.records] == legacy_log_messages
    assert getattr(StrategyConfigurator, "_price_filter_log_count") == 0
    assert getattr(StrategyConfigurator, "_filter_log_count") == 0


@pytest.mark.parametrize("dtype", ["float16", "float32"])
def test_provider_overflow_raise_stays_at_first_native_diagnostic_pass(
    dtype: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """raise mode 在第一個 native diagnostic comparison 結束，尚未 paired 投影。"""

    history = _synthetic_history(21, "OVERFLOW-RAISE", final_volume=1000, rsi=50)
    config = {"filters": {"price_change_max": 1e100}}
    provider = RecommendationDataFrameProvider()
    _install_fixed_post_score_metrics(
        provider,
        monkeypatch,
        price_change=1,
        price_dtype=dtype,
    )
    events = _install_post_score_side_effect_spies(monkeypatch)
    terminals = _capture_scorer_terminals(monkeypatch)

    events.clear()
    legacy_exc: FloatingPointError | None = None
    with np.errstate(over="raise"):
        try:
            provider.strategy_configurator.generate_recommendations(
                history.copy(deep=True), config
            )
        except FloatingPointError as exc:
            legacy_exc = exc

    events.clear()
    with np.errstate(over="raise"):
        legacy_rows = provider(history.copy(deep=True), config, 10)
    legacy_events = list(events)

    events.clear()
    with np.errstate(over="raise"):
        replay_result = provider.run_with_as_of_handoff(
            history.copy(deep=True),
            config,
            top_n=10,
            as_of_date=date(2026, 9, 21),
        )

    if legacy_exc is not None:
        assert events == ["legacy-filter"]
        assert legacy_rows == []
        assert replay_result.rows == []
        assert len(terminals) == 2
        assert all(
            terminal.response.disposition
            is ReplayScorerDispositionV1.SKIPPED_SCORER_EXCEPTION
            for terminal in terminals
        )
        assert all(
            terminal.response.error_type == type(legacy_exc).__name__
            for terminal in terminals
        )
        assert legacy_events == ["legacy-filter"]
    else:
        assert len(legacy_rows) == 1
        assert len(replay_result.rows) == 1
        assert replay_result.scoring_outcomes
        assert replay_result.scoring_outcomes[0] is not None
        assert replay_result.scoring_outcomes[0].response.disposition is ReplayScorerDispositionV1.SCORED
        assert len(terminals) == 2
        assert all(
            terminal.response.disposition is ReplayScorerDispositionV1.SCORED
            for terminal in terminals
        )
        assert legacy_events == ["legacy-filter", "legacy-filter"]
        assert events == ["legacy-filter", "typed-pair-projection"]


@pytest.mark.parametrize(
    ("real_component", "expected_warning_messages"),
    [
        (2.0, ()),
        (
            1.0,
            (
                "invalid value encountered in greater_equal",
                "invalid value encountered in greater_equal",
            ),
        ),
    ],
)
def test_provider_complex_nan_matches_pandas_final_filter_and_effect_order(
    real_component: float,
    expected_warning_messages: tuple[str, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pandas complex Series 的 final filter 與 native effect 都需同值。"""

    history = _synthetic_history(21, "COMPLEX-NAN", final_volume=1000, rsi=50)
    history.loc[history.index[-1], "收盤價"] = 101
    history.loc[history.index[-1], "開盤價"] = 101
    history.loc[history.index[-1], "最高價"] = 102
    history.loc[history.index[-1], "最低價"] = 100
    config = {"filters": {"price_change_min": 1.0}}
    provider = RecommendationDataFrameProvider()
    metric = np.complex64(complex(real_component, float("nan")))
    _install_fixed_post_score_metrics(
        provider,
        monkeypatch,
        price_change=metric,
        price_dtype="complex64",
    )
    events = _install_post_score_side_effect_spies(monkeypatch)

    monkeypatch.setattr(StrategyConfigurator, "_filter_log_count", 0, raising=False)
    monkeypatch.setattr(StrategyConfigurator, "_price_filter_log_count", 0, raising=False)
    with np.errstate(invalid="warn"):
        with warnings.catch_warnings(record=True) as legacy_warnings:
            warnings.simplefilter("always")
            legacy_rows = provider(history.copy(deep=True), config, 10)
    legacy_events = list(events)
    legacy_warning_messages = tuple(str(item.message) for item in legacy_warnings)
    legacy_warning_categories = tuple(type(item.message) for item in legacy_warnings)
    legacy_warning_locations = tuple(
        (item.filename, item.lineno) for item in legacy_warnings
    )

    monkeypatch.setattr(StrategyConfigurator, "_filter_log_count", 0, raising=False)
    monkeypatch.setattr(StrategyConfigurator, "_price_filter_log_count", 0, raising=False)
    events.clear()
    with np.errstate(invalid="warn"):
        with warnings.catch_warnings(record=True) as provider_warnings:
            warnings.simplefilter("always")
            replay_result = provider.run_with_as_of_handoff(
                history.copy(deep=True),
                config,
                top_n=10,
                as_of_date=date(2026, 9, 21),
            )

    assert legacy_rows == []
    assert replay_result.rows == []
    assert legacy_warning_messages == expected_warning_messages
    assert tuple(str(item.message) for item in provider_warnings) == legacy_warning_messages
    assert tuple(type(item.message) for item in provider_warnings) == legacy_warning_categories
    assert tuple(
        (item.filename, item.lineno) for item in provider_warnings
    ) == legacy_warning_locations
    assert legacy_events == ["legacy-filter", "legacy-filter"]
    assert events == ["legacy-filter", "typed-pair-projection"]
    assert replay_result.scoring_outcomes == ()


def test_provider_complex_nan_warn_effect_obeys_native_pandas_warning_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """warn module filter 對 native 與投影 warning 必須同樣生效。"""

    history = _synthetic_history(21, "COMPLEX-FILTER", final_volume=1000, rsi=50)
    history.loc[history.index[-1], "收盤價"] = 101
    history.loc[history.index[-1], "開盤價"] = 101
    history.loc[history.index[-1], "最高價"] = 102
    history.loc[history.index[-1], "最低價"] = 100
    config = {"filters": {"price_change_min": 1.0}}
    provider = RecommendationDataFrameProvider()
    _install_fixed_post_score_metrics(
        provider,
        monkeypatch,
        price_change=np.complex64(complex(1.0, float("nan"))),
        price_dtype="complex64",
    )

    with np.errstate(invalid="warn"):
        with warnings.catch_warnings(record=True) as legacy_warnings:
            warnings.filterwarnings(
                "ignore",
                message=r"^invalid value encountered in greater_equal$",
                category=RuntimeWarning,
                module=r"^pandas\.core\.computation\.expressions$",
            )
            legacy_rows = provider(history.copy(deep=True), config, 10)
    with np.errstate(invalid="warn"):
        with warnings.catch_warnings(record=True) as replay_warnings:
            warnings.filterwarnings(
                "ignore",
                message=r"^invalid value encountered in greater_equal$",
                category=RuntimeWarning,
                module=r"^pandas\.core\.computation\.expressions$",
            )
            replay_result = provider.run_with_as_of_handoff(
                history.copy(deep=True),
                config,
                top_n=10,
                as_of_date=date(2026, 9, 21),
            )

    assert legacy_rows == []
    assert replay_result.rows == []
    assert legacy_warnings == []
    assert replay_warnings == []


def test_provider_complex_nan_default_warning_registry_matches_native_location(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同位置重複 warning 的 default registry 行為也要相同。"""

    history = _synthetic_history(21, "COMPLEX-DEFAULT-FILTER", final_volume=1000, rsi=50)
    history.loc[history.index[-1], "收盤價"] = 101
    history.loc[history.index[-1], "開盤價"] = 101
    history.loc[history.index[-1], "最高價"] = 102
    history.loc[history.index[-1], "最低價"] = 100
    config = {"filters": {"price_change_min": 1.0}}
    provider = RecommendationDataFrameProvider()
    _install_fixed_post_score_metrics(
        provider,
        monkeypatch,
        price_change=np.complex64(complex(1.0, float("nan"))),
        price_dtype="complex64",
    )
    expressions = replay_provider_module.sys.modules[
        "pandas.core.computation.expressions"
    ]
    expressions.__dict__.pop("__warningregistry__", None)

    def run_with_default_filter(action: Any) -> list[warnings.WarningMessage]:
        with warnings.catch_warnings(record=True) as observed:
            warnings.filterwarnings(
                "default",
                message=r"^invalid value encountered in greater_equal$",
                category=RuntimeWarning,
                module=r"^pandas\.core\.computation\.expressions$",
            )
            with np.errstate(invalid="warn"):
                action()
            return list(observed)

    legacy = run_with_default_filter(
        lambda: provider(history.copy(deep=True), config, 10)
    )
    expressions.__dict__.pop("__warningregistry__", None)
    replay = run_with_default_filter(
        lambda: provider.run_with_as_of_handoff(
            history.copy(deep=True),
            config,
            top_n=10,
            as_of_date=date(2026, 9, 21),
        )
    )

    assert len(legacy) == len(replay) == 1
    assert str(legacy[0].message) == str(replay[0].message)
    assert type(legacy[0].message) is type(replay[0].message) is RuntimeWarning
    assert (legacy[0].filename, legacy[0].lineno) == (
        replay[0].filename,
        replay[0].lineno,
    )


def test_unsupported_rule_cannot_reuse_previous_complex_warning_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """unsupported rule 的未來 effect 不可借用前一 rule 的 warning site。"""

    history = _synthetic_history(21, "COMPLEX-STALE-SITE", final_volume=1000, rsi=50)
    history.loc[history.index[-1], "收盤價"] = 101
    history.loc[history.index[-1], "開盤價"] = 101
    history.loc[history.index[-1], "最高價"] = 102
    history.loc[history.index[-1], "最低價"] = 100
    provider = RecommendationDataFrameProvider()
    _install_fixed_post_score_metrics(
        provider,
        monkeypatch,
        price_change=np.complex64(complex(1.0, float("nan"))),
        price_dtype="complex64",
    )
    monkeypatch.setattr(
        replay_provider_module,
        "observe_screening_diagnostics",
        lambda *_args, **_kwargs: None,
    )
    original_project = replay_provider_module.project_legacy_post_score_comparison_pair
    project_calls = 0

    def project_with_unsupported_second_rule(*args: Any, **kwargs: Any) -> Any:
        nonlocal project_calls
        project_calls += 1
        if project_calls == 2:
            raise replay_provider_module.UnsupportedReplayNumericScalarError(
                "synthetic unsupported max threshold"
            )
        return original_project(*args, **kwargs)

    monkeypatch.setattr(
        replay_provider_module,
        "project_legacy_post_score_comparison_pair",
        project_with_unsupported_second_rule,
    )
    original_advance = RecommendationEvaluator.advance_replay_post_score_staged

    def append_future_unsupported_effect(
        evaluator: RecommendationEvaluator,
        step: Any,
        response: Any,
    ) -> Any:
        advanced = original_advance(evaluator, step, response)
        if response.request.filter_id is ReplayPostScoreRuleV1.PRICE_CHANGE_MAX:
            synthetic_future_effect = SimpleNamespace(
                effects=(
                    ReplayPostScoreEffectV1(
                        kind=ReplayPostScoreEffectKindV1.NUMPY_INVALID_COMPARISON,
                        operator=ReplayComparisonOperator.LESS_THAN_OR_EQUAL,
                    ),
                )
            )
            return SimpleNamespace(
                state=SimpleNamespace(
                    rules=(*advanced.state.rules, synthetic_future_effect)
                ),
                request=advanced.request,
                outcome=advanced.outcome,
            )
        return advanced

    monkeypatch.setattr(
        RecommendationEvaluator,
        "advance_replay_post_score_staged",
        append_future_unsupported_effect,
    )

    with np.errstate(invalid="ignore"):
        with pytest.raises(
            replay_provider_module.ReplayNativeEffectProjectionUnavailableError
        ):
            provider.run_with_as_of_handoff(
                history,
                {"filters": {"price_change_min": 1.0, "price_change_max": 2.0}},
                top_n=10,
                as_of_date=date(2026, 9, 21),
            )

    assert project_calls == 2


@pytest.mark.parametrize(
    "unavailable",
    ["runtime_profile", "bytecode_location", "non_windows_platform", "unknown_platform"],
)
def test_unverified_complex_effect_profile_fails_before_canonical_child(
    unavailable: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未驗證 runtime/location 不能變成 row 或 canonical child。"""

    history = _synthetic_history(21, "2330", final_volume=1000, rsi=50)
    history.loc[history.index[-1], "收盤價"] = 101
    history.loc[history.index[-1], "開盤價"] = 101
    history.loc[history.index[-1], "最高價"] = 102
    history.loc[history.index[-1], "最低價"] = 100
    provider = RecommendationDataFrameProvider()
    _install_fixed_post_score_metrics(
        provider,
        monkeypatch,
        price_change=np.complex64(complex(1.0, float("nan"))),
        price_dtype="complex64",
    )
    if unavailable == "runtime_profile":
        monkeypatch.setattr(replay_provider_module.pd, "__version__", "unverified")
    elif unavailable == "bytecode_location":
        monkeypatch.setattr(
            replay_provider_module.dis,
            "get_instructions",
            lambda _function: (),
        )
    elif unavailable == "non_windows_platform":
        monkeypatch.setattr(replay_provider_module.sys, "platform", "linux")
    else:
        monkeypatch.setattr(replay_provider_module.sys, "platform", "unknown-os")

    child_builder_calls: list[object] = []
    monkeypatch.setattr(
        replay_service_module,
        "_build_canonical_replay_execution_from_handoff",
        lambda *args, **kwargs: child_builder_calls.append((args, kwargs)),
    )
    replay_service = RecommendationReplayService(provider)
    with np.errstate(invalid="warn"):
        with pytest.raises(
            replay_provider_module.ReplayNativeEffectProjectionUnavailableError
        ):
            replay_service.run_snapshot(
                as_of_date="2026-09-21",
                profile_id="synthetic",
                config={"filters": {"price_change_min": 1.0}},
                history=history,
                universe=None,
                top_n=10,
            )

    assert child_builder_calls == []


@pytest.mark.parametrize("platform", ["linux", "darwin", "unknown-os"])
def test_unverified_platform_fails_closed_for_no_warning_complex_row(
    platform: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未驗平台即使 complex 比較不發 warning 也不得產生 row 或 child。"""

    history = _synthetic_history(21, "COMPLEX-PLATFORM", final_volume=1000, rsi=50)
    history.loc[history.index[-1], "收盤價"] = 101
    history.loc[history.index[-1], "開盤價"] = 101
    history.loc[history.index[-1], "最高價"] = 102
    history.loc[history.index[-1], "最低價"] = 100
    provider = RecommendationDataFrameProvider()
    _install_fixed_post_score_metrics(
        provider,
        monkeypatch,
        price_change=np.complex64(complex(2.0, float("nan"))),
        price_dtype="complex64",
    )
    monkeypatch.setattr(replay_provider_module.sys, "platform", platform)

    child_builder_calls: list[object] = []
    monkeypatch.setattr(
        replay_service_module,
        "_build_canonical_replay_execution_from_handoff",
        lambda *args, **kwargs: child_builder_calls.append((args, kwargs)),
    )
    replay_service = RecommendationReplayService(provider)
    with np.errstate(invalid="ignore"):
        with warnings.catch_warnings(record=True) as captured_warnings:
            warnings.simplefilter("always")
            with pytest.raises(
                replay_provider_module.ReplayNativeEffectProjectionUnavailableError
            ):
                replay_service.run_snapshot(
                    as_of_date="2026-09-21",
                    profile_id="synthetic",
                    config={"filters": {"price_change_min": 1.0}},
                    history=history,
                    universe=None,
                    top_n=10,
                )

    assert not any("invalid value encountered" in str(item.message) for item in captured_warnings)
    assert child_builder_calls == []


def test_non_windows_platform_keeps_numpy_scalar_replay_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """平台限制只封鎖未驗 complex domain，不影響一般 NumPy scalar。"""

    history = _synthetic_history(21, "SCALAR-PLATFORM", final_volume=1000, rsi=50)
    history.loc[history.index[-1], "收盤價"] = 101
    history.loc[history.index[-1], "開盤價"] = 101
    history.loc[history.index[-1], "最高價"] = 102
    history.loc[history.index[-1], "最低價"] = 100
    provider = RecommendationDataFrameProvider()
    _install_fixed_post_score_metrics(
        provider,
        monkeypatch,
        price_change=np.float32(2.0),
        price_dtype="float32",
    )
    monkeypatch.setattr(replay_provider_module.sys, "platform", "linux")

    result = RecommendationReplayService(provider).run_snapshot(
        as_of_date="2026-09-21",
        profile_id="synthetic",
        config={"filters": {"price_change_min": 1.0}},
        history=history,
        universe=None,
        top_n=10,
    )

    assert len(result.recommendations) == 1
    assert result.canonical_execution is not None


def test_provider_complex_nan_invalid_raise_keeps_native_exception_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = _synthetic_history(21, "COMPLEX-RAISE", final_volume=1000, rsi=50)
    history.loc[history.index[-1], "收盤價"] = 101
    history.loc[history.index[-1], "開盤價"] = 101
    history.loc[history.index[-1], "最高價"] = 102
    history.loc[history.index[-1], "最低價"] = 100
    config = {"filters": {"price_change_min": 1.0}}
    provider = RecommendationDataFrameProvider()
    _install_fixed_post_score_metrics(
        provider,
        monkeypatch,
        price_change=np.complex64(complex(1.0, float("nan"))),
        price_dtype="complex64",
    )
    terminals = _capture_scorer_terminals(monkeypatch)

    with np.errstate(invalid="raise"):
        with pytest.raises(
            FloatingPointError,
            match="invalid value encountered in greater_equal",
        ) as legacy_exc:
            provider.strategy_configurator.generate_recommendations(
                history.copy(deep=True), config
            )
    with np.errstate(invalid="raise"):
        legacy_rows = provider(history.copy(deep=True), config, 10)
    with np.errstate(invalid="raise"):
        replay_result = provider.run_with_as_of_handoff(
            history.copy(deep=True),
            config,
            top_n=10,
            as_of_date=date(2026, 9, 21),
        )

    assert str(legacy_exc.value) == "invalid value encountered in greater_equal"
    assert legacy_rows == []
    assert replay_result.rows == []
    assert replay_result.scoring_outcomes == ()
    assert len(terminals) == 2
    assert all(
        terminal.response.disposition
        is ReplayScorerDispositionV1.SKIPPED_SCORER_EXCEPTION
        for terminal in terminals
    )
    assert all(terminal.response.error_type == "FloatingPointError" for terminal in terminals)


@pytest.mark.parametrize("action", ["ignore", "print", "log", "call"])
def test_provider_complex_nan_projects_numpy_invalid_errstate_channels(
    action: Literal["ignore", "print", "log", "call"],
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """非 warn/raise errstate channels 要逐一跟 native Pandas side effect 對齊。"""

    history = _synthetic_history(21, "COMPLEX-CHANNEL", final_volume=1000, rsi=50)
    history.loc[history.index[-1], "收盤價"] = 101
    history.loc[history.index[-1], "開盤價"] = 101
    history.loc[history.index[-1], "最高價"] = 102
    history.loc[history.index[-1], "最低價"] = 100
    config = {"filters": {"price_change_min": 1.0}}
    provider = RecommendationDataFrameProvider()
    _install_fixed_post_score_metrics(
        provider,
        monkeypatch,
        price_change=np.complex64(complex(1.0, float("nan"))),
        price_dtype="complex64",
    )

    class _LogSink:
        def __init__(self) -> None:
            self.messages: list[str] = []

        def write(self, message: str) -> None:
            self.messages.append(message)

    old_callback = np.geterrcall()
    call_effects: list[tuple[str, int]] = []
    log_sink = _LogSink()
    if action == "call":
        np.seterrcall(lambda message, flag: call_effects.append((message, flag)))
    elif action == "log":
        np.seterrcall(log_sink)
    try:
        with np.errstate(invalid=action):
            legacy_rows = provider(history.copy(deep=True), config, 10)
        legacy_call_effects = list(call_effects)
        legacy_log_effects = list(log_sink.messages)
        legacy_stderr = capfd.readouterr().err

        call_effects.clear()
        log_sink.messages.clear()
        with np.errstate(invalid=action):
            replay_result = provider.run_with_as_of_handoff(
                history.copy(deep=True),
                config,
                top_n=10,
                as_of_date=date(2026, 9, 21),
            )
        replay_stderr = capfd.readouterr().err
    finally:
        np.seterrcall(old_callback)

    assert legacy_rows == []
    assert replay_result.rows == []
    assert call_effects == legacy_call_effects
    assert log_sink.messages == legacy_log_effects
    assert replay_stderr == legacy_stderr


def test_provider_preserves_price_reject_then_empty_rsi_error_and_diagnostic_order(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """價格拒絕後仍執行 RSI native error，並保留先行診斷 warning。"""

    history = _synthetic_history(21, "REJECT-THEN-RSI", final_volume=1000, rsi=50)
    history.loc[history.index[-1], "收盤價"] = 200
    history.loc[history.index[-1], "開盤價"] = 200
    history.loc[history.index[-1], "最高價"] = 201
    history.loc[history.index[-1], "最低價"] = 199
    config = {"filters": {"price_change_min": 50, "rsi_min": "bad"}}
    provider = RecommendationDataFrameProvider()
    _install_fixed_post_score_metrics(
        provider,
        monkeypatch,
        price_change=0.0,
        rsi=50,
        rsi_dtype="int64",
    )
    events = _install_post_score_side_effect_spies(monkeypatch)
    terminals = _capture_scorer_terminals(monkeypatch)
    caplog.set_level("WARNING", logger=StrategyConfigurator.__module__)

    monkeypatch.setattr(StrategyConfigurator, "_filter_log_count", 0, raising=False)
    monkeypatch.setattr(StrategyConfigurator, "_price_filter_log_count", 0, raising=False)
    with pytest.raises(
        TypeError, match="Invalid comparison between dtype=int64 and str"
    ):
        provider.strategy_configurator.generate_recommendations(
            history.copy(deep=True), config
        )
    legacy_events = list(events)
    legacy_warnings = [record.getMessage() for record in caplog.records]
    assert getattr(StrategyConfigurator, "_price_filter_log_count") == 1
    assert getattr(StrategyConfigurator, "_filter_log_count") == 0

    monkeypatch.setattr(StrategyConfigurator, "_filter_log_count", 0, raising=False)
    monkeypatch.setattr(StrategyConfigurator, "_price_filter_log_count", 0, raising=False)
    caplog.clear()
    events.clear()
    replay_result = provider.run_with_as_of_handoff(
        history.copy(deep=True),
        config,
        top_n=10,
        as_of_date=date(2026, 9, 21),
    )

    assert replay_result.rows == []
    assert events == ["legacy-filter", "typed-pair-projection"]
    assert legacy_events == ["legacy-filter", "legacy-filter"]
    assert [record.getMessage() for record in caplog.records] == legacy_warnings
    assert len(legacy_warnings) == 1
    assert legacy_warnings[0].startswith("[漲幅篩選]")
    assert getattr(StrategyConfigurator, "_price_filter_log_count") == 1
    assert getattr(StrategyConfigurator, "_filter_log_count") == 0
    assert len(terminals) == 1
    assert terminals[0].response.disposition is ReplayScorerDispositionV1.SKIPPED_SCORER_EXCEPTION
    assert terminals[0].response.error_type == "TypeError"
