"""R020 minimum-history preflight regression tests."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

import decision_module.recommendation.replay_prefilter as replay_prefilter_module
from app_module.recommendation_dataframe_provider import RecommendationDataFrameProvider
from app_module.recommendation_replay_service import RecommendationReplayService
from decision_module.recommendation.evaluate import RecommendationEvaluator
from decision_module.recommendation.replay_prefilter import (
    ReplayFastFilterPolicyV1,
    ReplayHistoryPreflightDisposition,
    ReplayMetricStatus,
    ReplayPrefilterObservations,
    ReplayPreflightDisposition,
    ReplayPreflightStage,
    evaluate_replay_prefilter,
)


class _RecordingScorer:
    def __init__(self) -> None:
        self.stock_codes: list[str] = []

    def generate_recommendations(
        self, stock_data: pd.DataFrame, config: dict[str, object]
    ) -> pd.DataFrame:
        stock_code = str(stock_data["證券代號"].iloc[0])
        self.stock_codes.append(stock_code)
        result = stock_data.copy(deep=True)
        result["FinalScore"] = 80
        return result


class _FixedReasonEngine:
    def generate_reasons(
        self, latest_row: pd.Series, config: dict[str, object]
    ) -> list[str]:
        return ["history-preflight"]

    def format_reason_text(self, reasons: list[str], max_reasons: int = 3) -> str:
        return "|".join(reasons[:max_reasons])


class _FloatProbe:
    def __init__(self, calls: list[str], name: str, *, fail: bool = False) -> None:
        self.calls = calls
        self.name = name
        self.fail = fail

    def __float__(self) -> float:
        self.calls.append(self.name)
        if self.fail:
            raise ValueError(f"synthetic invalid threshold: {self.name}")
        return 0.0


def _history(stock_code: str, rows: int) -> pd.DataFrame:
    dates = pd.date_range("2026-09-01", periods=rows, freq="D")
    return pd.DataFrame(
        {
            "日期": [int(value.strftime("%Y%m%d")) for value in dates],
            "證券代號": [stock_code] * rows,
            "證券名稱": [f"name-{stock_code}"] * rows,
            "收盤價": [100] * rows,
            "成交股數": [100] * rows,
        }
    )


def _provider() -> tuple[RecommendationDataFrameProvider, _RecordingScorer]:
    scorer = _RecordingScorer()
    provider = RecommendationDataFrameProvider()
    provider.strategy_configurator = scorer
    provider.reason_engine = _FixedReasonEngine()
    return provider, scorer


@pytest.mark.parametrize(
    ("history_rows", "expected_disposition"),
    [
        (0, ReplayHistoryPreflightDisposition.INSUFFICIENT_HISTORY),
        (19, ReplayHistoryPreflightDisposition.INSUFFICIENT_HISTORY),
        (20, ReplayHistoryPreflightDisposition.CONTINUE_TO_FAST_FILTERS),
        (21, ReplayHistoryPreflightDisposition.CONTINUE_TO_FAST_FILTERS),
    ],
)
def test_evaluator_history_preflight_is_count_only(
    history_rows: int,
    expected_disposition: ReplayHistoryPreflightDisposition,
) -> None:
    result = RecommendationEvaluator().preflight_replay_history(history_rows)

    assert result.history_rows == history_rows
    assert result.disposition is expected_disposition
    assert result.minimum_history_rows == 20


@pytest.mark.parametrize("invalid_history_rows", [-1, True, 20.0])
def test_evaluator_history_preflight_rejects_invalid_row_counts(
    invalid_history_rows: object,
) -> None:
    with pytest.raises(ValueError, match="非負 int"):
        RecommendationEvaluator().preflight_replay_history(invalid_history_rows)  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_filter", ["price_change_min", "volume_ratio_min"])
def test_nineteen_rows_preflight_before_any_threshold_conversion_or_scorer(
    monkeypatch: pytest.MonkeyPatch, invalid_filter: str
) -> None:
    conversions: list[str] = []
    evaluator_results = []
    original = RecommendationEvaluator.preflight_replay_history

    def record_preflight(
        evaluator: RecommendationEvaluator, history_rows: int
    ):
        result = original(evaluator, history_rows)
        evaluator_results.append(result)
        return result

    monkeypatch.setattr(
        RecommendationEvaluator, "preflight_replay_history", record_preflight
    )
    provider, scorer = _provider()
    result = provider.run_with_as_of(
        _history("SHORT", 19),
        {"filters": {invalid_filter: _FloatProbe(conversions, invalid_filter, fail=True)}},
        top_n=5,
        as_of_date=date(2026, 9, 30),
    )

    assert result == []
    assert conversions == []
    assert scorer.stock_codes == []
    assert len(evaluator_results) == 1
    assert evaluator_results[0].history_rows == 19
    assert (
        evaluator_results[0].disposition
        is ReplayHistoryPreflightDisposition.INSUFFICIENT_HISTORY
    )


def test_nineteen_row_blank_stock_code_uses_count_only_preflight() -> None:
    provider, scorer = _provider()

    result = provider(_history("", 19), {}, top_n=5)

    assert result == []
    assert scorer.stock_codes == []


def test_twenty_rows_continue_without_resolving_volume_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversions: list[str] = []
    evaluator_results = []
    original = RecommendationEvaluator.preflight_replay_history

    def record_preflight(
        evaluator: RecommendationEvaluator, rows: int
    ):
        result = original(evaluator, rows)
        evaluator_results.append(result)
        return result

    monkeypatch.setattr(
        RecommendationEvaluator, "preflight_replay_history", record_preflight
    )
    provider, scorer = _provider()
    result = provider.run_with_as_of(
        _history("CONTINUE", 20),
        {"filters": {"volume_ratio_min": _FloatProbe(conversions, "volume", fail=True)}},
        top_n=5,
        as_of_date=date(2026, 9, 30),
    )

    assert [row["stock_code"] for row in result] == ["CONTINUE"]
    assert len(scorer.stock_codes) == 1
    assert len(evaluator_results) == 1
    assert (
        evaluator_results[0].disposition
        is ReplayHistoryPreflightDisposition.CONTINUE_TO_FAST_FILTERS
    )
    assert conversions == []


def test_twenty_one_rows_keep_existing_volume_threshold_exception_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversions: list[str] = []
    evaluator_results = []
    original = RecommendationEvaluator.preflight_replay_history

    def record_preflight(
        evaluator: RecommendationEvaluator, rows: int
    ):
        result = original(evaluator, rows)
        evaluator_results.append(result)
        return result

    monkeypatch.setattr(
        RecommendationEvaluator, "preflight_replay_history", record_preflight
    )
    provider, scorer = _provider()

    with pytest.raises(ValueError, match="synthetic invalid threshold: volume"):
        provider.run_with_as_of(
            _history("VOLUME-THRESHOLD", 21),
            {
                "filters": {
                    "volume_ratio_min": _FloatProbe(
                        conversions, "volume", fail=True
                    )
                }
            },
            top_n=5,
            as_of_date=date(2026, 9, 30),
        )

    assert conversions == ["volume"]
    assert scorer.stock_codes == []
    assert len(evaluator_results) == 1
    assert evaluator_results[0].history_rows == 21
    assert (
        evaluator_results[0].disposition
        is ReplayHistoryPreflightDisposition.CONTINUE_TO_FAST_FILTERS
    )


def test_replay_prefilter_uses_shared_history_preflight_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_rows: list[int] = []
    original = replay_prefilter_module.evaluate_replay_history_preflight

    def record_history_preflight(history_rows: int):
        observed_rows.append(history_rows)
        return original(history_rows)

    monkeypatch.setattr(
        replay_prefilter_module,
        "evaluate_replay_history_preflight",
        record_history_preflight,
    )
    observations = ReplayPrefilterObservations(
        stock_code="SHORT",
        as_of_date=date(2026, 9, 19),
        history_rows=19,
        maximum_row_date=date(2026, 9, 19),
        availability_column_present=False,
        maximum_available_date=None,
        price_change_status=ReplayMetricStatus.MISSING_COLUMN,
        volume_change_status=ReplayMetricStatus.INSUFFICIENT_WINDOW,
    )

    outcome = evaluate_replay_prefilter(ReplayFastFilterPolicyV1(), observations)

    assert observed_rows == [19]
    assert outcome.disposition is ReplayPreflightDisposition.REJECT
    assert outcome.stage is ReplayPreflightStage.MINIMUM_HISTORY
    assert outcome.reason_code == "insufficient_history"
    assert outcome.observed_value == 19
    assert outcome.required_value == 20


def test_cutoff_and_availability_rejection_happen_before_history_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_rows: list[int] = []
    original = RecommendationEvaluator.preflight_replay_history

    def record_preflight(
        evaluator: RecommendationEvaluator, history_rows: int
    ):
        observed_rows.append(history_rows)
        return original(evaluator, history_rows)

    monkeypatch.setattr(
        RecommendationEvaluator, "preflight_replay_history", record_preflight
    )
    provider, scorer = _provider()
    valid = _history("PIT", 19)
    valid["available_date"] = valid["日期"]
    unavailable = pd.DataFrame(
        {
            "日期": [20260919],
            "證券代號": ["PIT"],
            "證券名稱": ["name-PIT"],
            "收盤價": [100],
            "成交股數": [100],
            "available_date": [None],
        }
    )
    future = pd.DataFrame(
        {
            "日期": [20260920],
            "證券代號": ["PIT"],
            "證券名稱": ["name-PIT"],
            "收盤價": [100],
            "成交股數": [100],
            "available_date": [20260920],
        }
    )
    history = pd.concat([valid, unavailable, future], ignore_index=True)

    snapshot = RecommendationReplayService(provider).run_snapshot(
        as_of_date="2026-09-19",
        profile_id="history-preflight-pit",
        config={},
        history=history,
        universe=None,
        top_n=5,
    )

    assert snapshot.recommendations == []
    assert snapshot.diagnostics == ["unavailable_rows_excluded:1"]
    assert observed_rows == [19]
    assert scorer.stock_codes == []
