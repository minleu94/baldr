from __future__ import annotations

from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from app_module.recommendation_dataframe_provider import (
    RecommendationDataFrameProvider,
    _LegacyFastFilterTraceCapture,
)
from decision_module.recommendation.evaluate import (
    NeedCandidateScoring,
    RecommendationEvaluator,
    ReplayCandidatePrefilterStep,
    ReplayCandidateScoringOutcomeV1,
    ReplayScorerDispositionV1,
    ReplayScorerResponseV1,
)
from decision_module.recommendation.replay_policy import ReplayScoreOrderingKindV1


class _Scorer:
    def __init__(
        self,
        *,
        empty_codes: set[str] | None = None,
        failing_codes: set[str] | None = None,
        scores: dict[str, float] | None = None,
        indicator_scores: dict[str, object] | None = None,
    ) -> None:
        self.inputs: list[pd.DataFrame] = []
        self.empty_codes = empty_codes or set()
        self.failing_codes = failing_codes or set()
        self.scores = scores or {}
        self.indicator_scores = indicator_scores or {}

    def generate_recommendations(
        self, stock_data: pd.DataFrame, config: dict
    ) -> pd.DataFrame:
        self.inputs.append(stock_data.copy(deep=True))
        stock_code = str(stock_data["證券代號"].iloc[0])
        if stock_code in self.failing_codes:
            raise RuntimeError(f"synthetic scorer error: {stock_code}")
        if stock_code in self.empty_codes:
            return stock_data.iloc[0:0].copy()
        result = stock_data.copy(deep=True)
        result["FinalScore"] = self.scores.get(stock_code, 80.0)
        if stock_code in self.indicator_scores:
            result["IndicatorScore"] = self.indicator_scores[stock_code]
        else:
            result["IndicatorScore"] = 3.0
        result["PatternScore"] = 2.0
        result["VolumeScore"] = 1.0
        return result


class _ReasonEngine:
    def __init__(self, *, failing_codes: set[str] | None = None) -> None:
        self.failing_codes = failing_codes or set()
        self.current_code = ""

    def generate_reasons(self, latest_row: pd.Series, config: dict) -> list[str]:
        self.current_code = str(latest_row.get("證券代號", ""))
        return [f"reason-{self.current_code}"]

    def format_reason_text(self, reasons: list[str], max_reasons: int = 3) -> object:
        if self.current_code in self.failing_codes:
            raise RuntimeError(f"synthetic row projection error: {self.current_code}")
        return "|".join(reasons[:max_reasons])


class _OpaqueReasonEngine(_ReasonEngine):
    def __init__(self, value: object) -> None:
        super().__init__()
        self.value = value

    def format_reason_text(self, reasons: list[str], max_reasons: int = 3) -> object:
        return self.value


def _history(stock_codes: tuple[str, ...], *, rows: int = 20) -> pd.DataFrame:
    dates = pd.date_range("2026-08-01", periods=rows, freq="D")
    return pd.DataFrame(
        [
            {
                "日期": int(current_date.strftime("%Y%m%d")),
                "證券代號": stock_code,
                "證券名稱": f"name-{stock_code}",
                "收盤價": 100.0,
                "成交股數": 100.0,
                "available_date": int(current_date.strftime("%Y%m%d")),
            }
            for stock_code in stock_codes
            for current_date in dates
        ]
    )


def _provider(
    scorer: _Scorer,
    *,
    reason_engine: _ReasonEngine | None = None,
) -> RecommendationDataFrameProvider:
    provider = RecommendationDataFrameProvider()
    provider.strategy_configurator = scorer
    provider.reason_engine = reason_engine or _ReasonEngine()
    return provider


def _observe_completions(
    monkeypatch: pytest.MonkeyPatch,
) -> list[
    tuple[
        ReplayCandidatePrefilterStep,
        ReplayScorerResponseV1,
        ReplayCandidateScoringOutcomeV1,
    ]
]:
    completed: list[
        tuple[
            ReplayCandidatePrefilterStep,
            ReplayScorerResponseV1,
            ReplayCandidateScoringOutcomeV1,
        ]
    ] = []
    original = RecommendationEvaluator.complete_replay_scoring

    def record(
        evaluator: RecommendationEvaluator,
        prefilter_step: ReplayCandidatePrefilterStep,
        response: ReplayScorerResponseV1,
    ) -> ReplayCandidateScoringOutcomeV1:
        outcome = original(evaluator, prefilter_step, response)
        completed.append((prefilter_step, response, outcome))
        return outcome

    monkeypatch.setattr(RecommendationEvaluator, "complete_replay_scoring", record)
    return completed


def test_no_filter_candidate_hands_real_ready_step_without_computing_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed = _observe_completions(monkeypatch)
    scorer = _Scorer()
    provider = _provider(scorer)
    history = _history(("PASS",))
    trace = _LegacyFastFilterTraceCapture()

    rows = provider(history, {}, top_n=5, capture_sink=trace)

    assert [row["stock_code"] for row in rows] == ["PASS"]
    assert len(scorer.inputs) == 1
    assert trace.events == []
    assert len(completed) == 1
    step, response, outcome = completed[0]
    assert type(step) is ReplayCandidatePrefilterStep
    assert type(step.request) is NeedCandidateScoring
    assert step.request.stock_code == "PASS"
    assert step.request.as_of_date == date(2026, 8, 20)
    assert step.state.policy.price_change_min.status.value == "disabled"
    assert step.state.policy.price_change_max.status.value == "disabled"
    assert step.state.policy.volume_ratio_min.status.value == "disabled"
    assert step.state.policy.volume_minimum is None
    assert step.state.observations.price_change_status.value == "not_requested"
    assert step.state.observations.volume_change_status.value == "insufficient_window"
    assert response.disposition is ReplayScorerDispositionV1.SCORED
    assert response.item.stock_code == "PASS"
    assert response.item.rule_score == Decimal("80.0")
    assert response.item.indicator_score == Decimal("3.0")
    assert response.score_ordering.kind is ReplayScoreOrderingKindV1.FINITE
    assert response.score_ordering.numerator == 80
    assert response.score_ordering.denominator == 1
    assert outcome.disposition is ReplayScorerDispositionV1.SCORED


def test_prefilter_pass_with_filters_is_the_step_completed_by_scorer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed = _observe_completions(monkeypatch)
    scorer = _Scorer()
    provider = _provider(scorer)

    rows = provider(
        _history(("FILTERED",)),
        {"filters": {"price_change_min": "0"}},
        top_n=5,
    )

    assert [row["stock_code"] for row in rows] == ["FILTERED"]
    assert len(completed) == 1
    step, response, outcome = completed[0]
    assert type(step.request) is NeedCandidateScoring
    assert step.request.prefilter_outcome.reason_code == "ready"
    assert response.request == step.request
    assert response.disposition is ReplayScorerDispositionV1.SCORED
    assert outcome.request == step.request


def test_empty_and_scorer_exception_are_completed_as_typed_per_stock_skips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed = _observe_completions(monkeypatch)
    scorer = _Scorer(empty_codes={"EMPTY"}, failing_codes={"BROKEN"})
    provider = _provider(scorer)

    rows = provider(_history(("EMPTY", "BROKEN", "GOOD")), {}, top_n=5)

    assert [row["stock_code"] for row in rows] == ["GOOD"]
    assert [entry[1].disposition for entry in completed] == [
        ReplayScorerDispositionV1.SKIPPED_EMPTY,
        ReplayScorerDispositionV1.SKIPPED_SCORER_EXCEPTION,
        ReplayScorerDispositionV1.SCORED,
    ]
    assert completed[1][1].error_type == "RuntimeError"
    assert completed[1][2].assessment.reasons == ("scorer_exception",)


def test_legacy_row_projection_exception_is_a_typed_skip_and_does_not_stop_next_stock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed = _observe_completions(monkeypatch)
    scorer = _Scorer()
    provider = _provider(scorer, reason_engine=_ReasonEngine(failing_codes={"BADROW"}))

    rows = provider(_history(("BADROW", "GOODROW")), {}, top_n=5)

    assert [row["stock_code"] for row in rows] == ["GOODROW"]
    assert [entry[1].disposition for entry in completed] == [
        ReplayScorerDispositionV1.SKIPPED_PROJECTION_EXCEPTION,
        ReplayScorerDispositionV1.SCORED,
    ]
    assert completed[0][1].error_type == "RuntimeError"


def test_empty_stock_code_keeps_legacy_row_without_inventing_typed_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed = _observe_completions(monkeypatch)
    scorer = _Scorer(scores={"": 80.0, "VALID": 70.0})
    provider = _provider(scorer)

    rows = provider(_history(("", "VALID")), {}, top_n=5)

    assert [row["stock_code"] for row in rows] == ["", "VALID"]
    assert [str(frame["證券代號"].iloc[0]) for frame in scorer.inputs] == ["", "VALID"]
    assert [entry[0].request.stock_code for entry in completed] == ["VALID"]
    assert [entry[1].disposition for entry in completed] == [
        ReplayScorerDispositionV1.SCORED
    ]


def test_nonfinite_factor_stays_in_legacy_row_but_is_missing_in_typed_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed = _observe_completions(monkeypatch)
    scorer = _Scorer(indicator_scores={"NAN-FACTOR": np.nan})
    provider = _provider(scorer)

    rows = provider(_history(("NAN-FACTOR",)), {}, top_n=5)

    assert len(rows) == 1
    assert np.isnan(rows[0]["factor_scores"]["technical"])
    assert len(completed) == 1
    response = completed[0][1]
    assert response.disposition is ReplayScorerDispositionV1.SCORED
    assert response.item.indicator_score is None


def test_unrepresentable_reason_keeps_legacy_row_and_marks_typed_projection_skip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed = _observe_completions(monkeypatch)
    opaque_reason = object()
    scorer = _Scorer()
    provider = _provider(scorer, reason_engine=_OpaqueReasonEngine(opaque_reason))

    rows = provider(_history(("OPAQUE",)), {}, top_n=5)

    assert [row["stock_code"] for row in rows] == ["OPAQUE"]
    assert rows[0]["selection_reason"] is opaque_reason
    assert completed[0][1].disposition is (
        ReplayScorerDispositionV1.SKIPPED_PROJECTION_EXCEPTION
    )
    assert completed[0][1].error_type == "TypeError"


def test_requested_cutoff_rejects_unsliced_future_rows_on_no_filter_path() -> None:
    scorer = _Scorer()
    provider = _provider(scorer)
    history = _history(("FUTURE",))

    with pytest.raises(ValueError, match="maximum_row_date 超過 replay cutoff"):
        provider.run_with_as_of(
            history,
            {},
            top_n=5,
            as_of_date=date(2026, 8, 19),
        )
    assert scorer.inputs == []
