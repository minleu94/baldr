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


def _history(
    row_count: int,
    stock_code: str,
    *,
    final_volume: int = 1000,
    rsi: int | None = 50,
    available_date: date | None = None,
) -> pd.DataFrame:
    dates = pd.date_range("2026-09-01", periods=row_count, freq="D")
    volumes = [1000] * (row_count - 1) + [final_volume]
    values: dict[str, Any] = {
        "日期": [int(value.strftime("%Y%m%d")) for value in dates],
        "證券代號": [stock_code] * row_count,
        "證券名稱": [f"名稱-{stock_code}"] * row_count,
        "開盤價": [100.0] * row_count,
        "最高價": [101.0] * row_count,
        "最低價": [99.0] * row_count,
        "收盤價": [100.0] * row_count,
        "成交股數": volumes,
    }
    if rsi is not None:
        values["RSI"] = [rsi] * row_count
    if available_date is not None:
        values["available_date"] = [
            int(available_date.strftime("%Y%m%d"))
        ] * row_count
    return pd.DataFrame(values)


def _capture_terminals(
    monkeypatch: pytest.MonkeyPatch,
) -> list[ReplayCandidateScoringOutcomeV1]:
    terminals: list[ReplayCandidateScoringOutcomeV1] = []
    original = RecommendationEvaluator.complete_replay_scoring

    def observe(
        evaluator: RecommendationEvaluator,
        step: Any,
        response: ReplayScorerResponseV1,
    ) -> ReplayCandidateScoringOutcomeV1:
        terminal = original(evaluator, step, response)
        terminals.append(terminal)
        return terminal

    monkeypatch.setattr(RecommendationEvaluator, "complete_replay_scoring", observe)
    return terminals


def _run_provider(
    history: pd.DataFrame,
    config: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    *,
    as_of_date: date | None = None,
) -> tuple[ReplayProviderCallResultV1, list[int], list[ReplayCandidateScoringOutcomeV1]]:
    provider = RecommendationDataFrameProvider()
    assert type(provider.strategy_configurator) is StrategyConfigurator
    calls: list[int] = []
    original_generate = provider.strategy_configurator.generate_recommendations

    def observe_generate(frame: pd.DataFrame, received_config: dict[str, Any]) -> pd.DataFrame:
        calls.append(len(frame))
        return original_generate(frame, received_config)

    monkeypatch.setattr(
        provider.strategy_configurator,
        "generate_recommendations",
        observe_generate,
    )
    cutoff = as_of_date or pd.to_datetime(
        history["日期"], format="%Y%m%d"
    ).max().date()
    terminals = _capture_terminals(monkeypatch)
    result = provider.run_with_as_of_handoff(
        history,
        config,
        top_n=10,
        as_of_date=cutoff,
    )
    return result, calls, terminals


def _direct_scorer(history: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    return StrategyConfigurator().generate_recommendations(
        history.copy(deep=True), config
    )


def test_volume_prefilter_and_scorer_keep_19_20_21_row_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """固定 legacy scorer 的 19-row fallback 與 provider 20/21-row 階段差異。"""

    config = {"filters": {"volume_ratio_min": 1.5}}
    expected_v1 = {
        "stock_name": "名稱-VOLUME-19",
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

    for row_count in (19, 20, 21):
        history = _history(
            row_count,
            f"VOLUME-{row_count}",
            final_volume=1500,
        )
        native = _direct_scorer(history, config)
        assert len(native) == 1
        assert str(native.iloc[-1]["TotalScore"]) == "50.00"
        assert str(native.iloc[-1]["成交量變化率%"]) == "50.0"

        result, calls, terminals = _run_provider(history, config, monkeypatch)
        if row_count == 19:
            assert calls == []
            assert terminals == []
            assert result.rows == []
            assert result.scoring_outcomes == ()
            continue

        assert calls == [row_count]
        assert len(terminals) == 1
        terminal = terminals[0]
        assert type(terminal.request) is NeedCandidateScoring
        assert terminal.request.stock_code == f"VOLUME-{row_count}"
        assert terminal.request.history_rows == row_count
        assert terminal.response.disposition is ReplayScorerDispositionV1.SCORED
        assert len(result.rows) == len(result.scoring_outcomes) == 1
        row = result.rows[0]
        assert row["stock_code"] == f"VOLUME-{row_count}"
        assert row["stock_name"] == f"名稱-VOLUME-{row_count}"
        assert row["total_score"] == expected_v1["total_score"]
        assert row["factor_scores"] == expected_v1["factor_scores"]
        assert row["selection_reason"] == expected_v1["selection_reason"]
        outcome = result.scoring_outcomes[0]
        assert outcome is not None
        assert outcome.request.stock_code == row["stock_code"]
        assert outcome.response.disposition is ReplayScorerDispositionV1.SCORED


@pytest.mark.parametrize(
    ("config", "native_count", "provider_count", "scorer_calls", "terminal"),
    [
        (
            {"filters": {"volume_ratio_min": 1.3, "min_volume_ratio": 1.5}},
            0,
            0,
            [21],
            ReplayScorerDispositionV1.SKIPPED_EMPTY,
        ),
        (
            {"filters": {"volume_ratio_min": 1.5, "min_volume_ratio": 1.3}},
            1,
            0,
            [],
            None,
        ),
    ],
)
def test_volume_alias_priority_is_applied_at_different_stages(
    monkeypatch: pytest.MonkeyPatch,
    config: dict[str, Any],
    native_count: int,
    provider_count: int,
    scorer_calls: list[int],
    terminal: ReplayScorerDispositionV1 | None,
) -> None:
    """兩個 volume key 同時存在時，provider 與 scorer 使用的優先序不同。"""

    history = _history(21, "ALIAS", final_volume=1400)
    native = _direct_scorer(history, config)
    assert len(native) == native_count
    if native_count:
        assert str(native.iloc[-1]["TotalScore"]) == "50.00"

    result, calls, terminals = _run_provider(history, config, monkeypatch)
    assert calls == scorer_calls
    assert len(result.rows) == provider_count
    if terminal is None:
        assert terminals == []
        assert result.scoring_outcomes == ()
    else:
        assert len(terminals) == 1
        assert terminals[0].request.stock_code == "ALIAS"
        assert terminals[0].response.disposition is terminal
        assert result.scoring_outcomes == ()


@pytest.mark.parametrize(
    ("rsi", "config", "expected_count", "terminal"),
    [
        (None, {"filters": {"rsi_min": 101}}, 1, ReplayScorerDispositionV1.SCORED),
        (50, {"filters": {"rsi_min": 51}}, 0, ReplayScorerDispositionV1.SKIPPED_EMPTY),
        (50, {"filters": {"rsi_max": 49}}, 0, ReplayScorerDispositionV1.SKIPPED_EMPTY),
        (
            50,
            {"filters": {"rsi_min": 50, "rsi_max": 50}},
            1,
            ReplayScorerDispositionV1.SCORED,
        ),
    ],
)
def test_rsi_missing_column_and_inclusive_bounds_are_scorer_owned(
    monkeypatch: pytest.MonkeyPatch,
    rsi: int | None,
    config: dict[str, Any],
    expected_count: int,
    terminal: ReplayScorerDispositionV1,
) -> None:
    history = _history(21, "RSI", rsi=rsi)
    native = _direct_scorer(history, config)
    assert len(native) == expected_count

    result, calls, terminals = _run_provider(history, config, monkeypatch)
    assert calls == [21]
    assert len(result.rows) == expected_count
    assert len(terminals) == 1
    assert terminals[0].request.stock_code == "RSI"
    assert terminals[0].response.disposition is terminal
    if expected_count:
        assert str(native.iloc[-1]["TotalScore"]) == "50.00"
        assert result.rows[0]["total_score"] == 50.0
        assert len(result.scoring_outcomes) == 1
        assert result.scoring_outcomes[0] is not None
        assert (
            result.scoring_outcomes[0].response.disposition
            is ReplayScorerDispositionV1.SCORED
        )
    else:
        assert result.scoring_outcomes == ()


def test_min_return_alias_is_applied_after_real_scorer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = {"filters": {"min_return_pct": 1}}
    history = _history(21, "RETURN")
    assert _direct_scorer(history, config).empty

    result, calls, terminals = _run_provider(history, config, monkeypatch)
    assert calls == [21]
    assert result.rows == []
    assert result.scoring_outcomes == ()
    assert len(terminals) == 1
    assert terminals[0].request.stock_code == "RETURN"
    assert terminals[0].response.disposition is ReplayScorerDispositionV1.SKIPPED_EMPTY


def test_min_return_alias_pd_na_keeps_real_scorer_warning_and_empty_terminal(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """固定 nullable alias 經既有 scorer 投影的 warning、呼叫與 empty terminal。"""

    config = {"filters": {"min_return_pct": pd.NA}}
    history = _history(21, "RETURN-NA")
    monkeypatch.setattr(StrategyConfigurator, "_price_filter_log_count", 0, raising=False)
    caplog.set_level("WARNING", logger="decision_module.strategy_configurator")

    native = _direct_scorer(history, config)
    assert native.empty

    result, calls, terminals = _run_provider(history, config, monkeypatch)
    assert calls == [21]
    assert result.rows == []
    assert result.scoring_outcomes == ()
    assert len(terminals) == 1
    terminal = terminals[0]
    assert terminal.request.stock_code == "RETURN-NA"
    assert terminal.response.disposition is ReplayScorerDispositionV1.SKIPPED_EMPTY
    assert terminal.response.reason_code == "scorer_empty_result"
    assert [record.message for record in caplog.records if record.levelname == "WARNING"] == [
        "[漲幅篩選] 要求 >= <NA>%, 但樣本值=0.00%",
        "[漲幅篩選] 要求 >= <NA>%, 但樣本值=0.00%",
    ]
    assert getattr(StrategyConfigurator, "_price_filter_log_count") == 2


@pytest.mark.parametrize(
    ("row_count", "call_count", "disposition", "raises"),
    [
        (19, [], None, None),
        (20, [20], ReplayScorerDispositionV1.SKIPPED_SCORER_EXCEPTION, None),
        (21, [], None, ValueError),
    ],
)
def test_invalid_volume_threshold_keeps_legacy_error_and_terminal_stage(
    monkeypatch: pytest.MonkeyPatch,
    row_count: int,
    call_count: list[int],
    disposition: ReplayScorerDispositionV1 | None,
    raises: type[Exception] | None,
) -> None:
    config = {"filters": {"volume_ratio_min": "bad"}}
    history = _history(row_count, f"BAD-{row_count}", final_volume=1500)
    with pytest.raises(TypeError):
        _direct_scorer(history, config)

    if raises is not None:
        provider = RecommendationDataFrameProvider()
        calls: list[int] = []
        original_generate = provider.strategy_configurator.generate_recommendations

        def observe_generate(frame: pd.DataFrame, received_config: dict[str, Any]) -> pd.DataFrame:
            calls.append(len(frame))
            return original_generate(frame, received_config)

        monkeypatch.setattr(
            provider.strategy_configurator,
            "generate_recommendations",
            observe_generate,
        )
        with pytest.raises(raises):
            provider.run_with_as_of_handoff(
                history,
                config,
                top_n=10,
                as_of_date=date(2026, 9, row_count),
            )
        assert calls == call_count
        return

    result, calls, terminals = _run_provider(history, config, monkeypatch)
    assert calls == call_count
    assert result.rows == []
    assert result.scoring_outcomes == ()
    if disposition is None:
        assert terminals == []
    else:
        assert len(terminals) == 1
        assert terminals[0].response.disposition is disposition
        assert terminals[0].response.error_type == "TypeError"


def test_rejecting_price_min_does_not_parse_later_invalid_thresholds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = {
        "filters": {
            "price_change_min": 100,
            "price_change_max": "bad",
            "volume_ratio_min": "bad",
        }
    }
    history = _history(21, "LAZY")
    with pytest.raises(TypeError):
        _direct_scorer(history, config)

    result, calls, terminals = _run_provider(history, config, monkeypatch)
    assert result.rows == []
    assert result.scoring_outcomes == ()
    assert calls == []
    assert terminals == []


@pytest.mark.parametrize(
    ("last_row_date", "available_date", "expected_message"),
    [
        (date(2026, 9, 22), None, "maximum_row_date 超過 replay cutoff"),
        (
            date(2026, 9, 21),
            date(2026, 9, 22),
            "maximum_available_date 超過 replay cutoff",
        ),
    ],
)
def test_future_row_or_availability_is_rejected_before_scorer(
    monkeypatch: pytest.MonkeyPatch,
    last_row_date: date,
    available_date: date | None,
    expected_message: str,
) -> None:
    history = _history(
        21,
        "FUTURE",
        available_date=available_date,
    )
    history.loc[history.index[-1], "日期"] = int(last_row_date.strftime("%Y%m%d"))
    provider = RecommendationDataFrameProvider()
    calls: list[int] = []
    original_generate = provider.strategy_configurator.generate_recommendations

    def observe_generate(frame: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
        calls.append(len(frame))
        return original_generate(frame, config)

    monkeypatch.setattr(
        provider.strategy_configurator,
        "generate_recommendations",
        observe_generate,
    )
    with pytest.raises(ValueError, match=expected_message):
        provider.run_with_as_of_handoff(
            history,
            {"filters": {"rsi_min": 0}},
            top_n=10,
            as_of_date=date(2026, 9, 21),
        )
    assert calls == []
