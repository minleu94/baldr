"""R020 concrete replay 混合 scorer terminal 與雙層切片固定向量。"""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd
import pytest

from app_module.recommendation_dataframe_provider import (
    RecommendationDataFrameProvider,
    ReplayProviderCallResultV1,
)
from app_module.recommendation_replay_service import RecommendationReplayService
from decision_module.recommendation.evaluate import (
    NeedCandidateScoring,
    RecommendationEvaluator,
    ReplayCandidatePrefilterStep,
    ReplayCandidateScoringOutcomeV1,
    ReplayScorerDispositionV1,
    ReplayScorerResponseV1,
)


_AS_OF = date(2026, 9, 24)


def _history(codes: tuple[str, ...]) -> pd.DataFrame:
    """建立 cutoff 前 24 列，並為每檔追加一筆未來 poison row。"""

    days = pd.date_range("2026-09-01", periods=24, freq="D")
    rows: list[dict[str, object]] = []
    for code in codes:
        for index, day in enumerate(days):
            key = int(day.strftime("%Y%m%d"))
            rows.append(
                {
                    "日期": key,
                    "available_date": key,
                    "證券代號": code,
                    "證券名稱": f"名稱-{code}",
                    "收盤價": 100 + index,
                    "成交股數": 1_000 + index,
                }
            )
        rows.append(
            {
                "日期": 20260925,
                "available_date": 20260925,
                "證券代號": code,
                "證券名稱": f"未來名稱-{code}",
                "收盤價": 999_999,
                "成交股數": 999_999,
            }
        )
    return pd.DataFrame(rows)


class _MixedScorer:
    def __init__(
        self,
        scores: dict[str, object],
        *,
        empty_codes: set[str],
        failing_codes: set[str],
    ) -> None:
        self.scores = scores
        self.empty_codes = empty_codes
        self.failing_codes = failing_codes
        self.calls: list[str] = []
        self.latest_dates: list[date] = []

    def generate_recommendations(
        self, stock_data: pd.DataFrame, _config: dict[str, Any]
    ) -> pd.DataFrame:
        code = str(stock_data["證券代號"].iloc[0])
        self.calls.append(code)
        self.latest_dates.append(pd.Timestamp(stock_data["日期"].iloc[-1]).date())
        if code in self.failing_codes:
            raise RuntimeError(f"合成 scorer error: {code}")
        if code in self.empty_codes:
            return stock_data.iloc[0:0].copy()

        result = stock_data.copy(deep=True)
        result["FinalScore"] = self.scores[code]
        result["IndicatorScore"] = 3
        result["PatternScore"] = 2
        result["VolumeScore"] = 1
        return result


class _MixedReasonEngine:
    def __init__(self, opaque_codes: set[str]) -> None:
        self.opaque_codes = opaque_codes

    def generate_reasons(
        self, latest_row: pd.Series, _config: dict[str, Any]
    ) -> list[str]:
        return [f"reason-{latest_row['證券代號']}"]

    def format_reason_text(
        self, reasons: list[str], max_reasons: int = 3
    ) -> object:
        code = reasons[0].removeprefix("reason-") if reasons else ""
        if code in self.opaque_codes:
            return object()
        return "|".join(reasons[:max_reasons])


def _provider(
    scores: dict[str, object],
    *,
    empty_codes: set[str] | None = None,
    failing_codes: set[str] | None = None,
    opaque_codes: set[str] | None = None,
) -> tuple[RecommendationDataFrameProvider, _MixedScorer]:
    provider = RecommendationDataFrameProvider()
    scorer = _MixedScorer(
        scores,
        empty_codes=set() if empty_codes is None else empty_codes,
        failing_codes=set() if failing_codes is None else failing_codes,
    )
    setattr(provider, "strategy_configurator", scorer)
    setattr(
        provider,
        "reason_engine",
        _MixedReasonEngine(set() if opaque_codes is None else opaque_codes),
    )
    return provider, scorer


def _capture_handoff(
    monkeypatch: pytest.MonkeyPatch,
    provider: RecommendationDataFrameProvider,
) -> list[ReplayProviderCallResultV1]:
    handoffs: list[ReplayProviderCallResultV1] = []
    original = provider.run_with_as_of_handoff

    def capture(
        frame: pd.DataFrame,
        config: dict[str, Any],
        top_n: int,
        as_of_date: date,
    ) -> ReplayProviderCallResultV1:
        result = original(frame, config, top_n, as_of_date)
        handoffs.append(result)
        return result

    monkeypatch.setattr(provider, "run_with_as_of_handoff", capture)
    return handoffs


def _capture_completions(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[str, ReplayScorerDispositionV1]]:
    completed: list[tuple[str, ReplayScorerDispositionV1]] = []
    original = RecommendationEvaluator.complete_replay_scoring

    def capture(
        evaluator: RecommendationEvaluator,
        step: ReplayCandidatePrefilterStep,
        response: ReplayScorerResponseV1,
    ) -> ReplayCandidateScoringOutcomeV1:
        outcome = original(evaluator, step, response)
        request = step.request
        assert type(request) is NeedCandidateScoring
        completed.append((request.stock_code, outcome.disposition))
        return outcome

    monkeypatch.setattr(RecommendationEvaluator, "complete_replay_scoring", capture)
    return completed


def _run_snapshot(
    provider: RecommendationDataFrameProvider,
    codes: tuple[str, ...],
    *,
    top_n: int,
    parent_id: str,
):
    return RecommendationReplayService(provider).run_snapshot(
        as_of_date=_AS_OF.isoformat(),
        profile_id="profile-r020-mixed-terminal",
        config={},
        history=_history(codes),
        universe=None,
        top_n=top_n,
        parent_result_id=parent_id,
    )


def _assert_v1_row(row: dict[str, object], code: str, score: float) -> None:
    assert row == {
        "stock_code": code,
        "stock_name": f"名稱-{code}",
        "total_score": score,
        "factor_scores": {
            "technical": 3.0,
            "pattern": 2.0,
            "volume": 1.0,
            "broker_flow": 0.0,
            "revenue": 0.0,
        },
        "selection_reason": f"reason-{code}",
    }


def test_mixed_terminals_keep_selected_v1_rows_and_fail_child_atomically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codes = (
        "HI",
        "EMPTY",
        "BROKEN",
        "SELECTED_PROJECTION",
        "MID",
        "SECOND_SLICE_PROJECTION",
        "FIRST_SLICE_TAIL",
    )
    provider, scorer = _provider(
        {
            "HI": 100,
            "SELECTED_PROJECTION": 90,
            "MID": 80,
            "SECOND_SLICE_PROJECTION": 70,
            "FIRST_SLICE_TAIL": 60,
        },
        empty_codes={"EMPTY"},
        failing_codes={"BROKEN"},
        opaque_codes={"SELECTED_PROJECTION", "SECOND_SLICE_PROJECTION"},
    )
    handoffs = _capture_handoff(monkeypatch, provider)
    completions = _capture_completions(monkeypatch)

    snapshot = _run_snapshot(
        provider,
        codes,
        top_n=-1,
        parent_id="parent-r020-mixed-selected-projection",
    )

    # 每檔 scorer 只呼叫一次；服務在 cutoff 前移除 9/25 poison row。
    assert scorer.calls == list(codes)
    assert scorer.latest_dates == [_AS_OF] * len(codes)
    assert completions == [
        ("HI", ReplayScorerDispositionV1.SCORED),
        ("EMPTY", ReplayScorerDispositionV1.SKIPPED_EMPTY),
        ("BROKEN", ReplayScorerDispositionV1.SKIPPED_SCORER_EXCEPTION),
        (
            "SELECTED_PROJECTION",
            ReplayScorerDispositionV1.SKIPPED_PROJECTION_EXCEPTION,
        ),
        ("MID", ReplayScorerDispositionV1.SCORED),
        (
            "SECOND_SLICE_PROJECTION",
            ReplayScorerDispositionV1.SKIPPED_PROJECTION_EXCEPTION,
        ),
        ("FIRST_SLICE_TAIL", ReplayScorerDispositionV1.SCORED),
    ]
    assert len(handoffs) == 1
    handoff = handoffs[0]
    assert handoff.as_of_date == _AS_OF
    assert handoff.requested_top_n == -1

    # EMPTY 與 BROKEN 有 scorer terminal，但不形成 legacy v1 candidate。
    assert [row["stock_code"] for row in handoff.rows] == [
        "HI",
        "SELECTED_PROJECTION",
        "MID",
        "SECOND_SLICE_PROJECTION",
    ]
    assert all(outcome is not None for outcome in handoff.scoring_outcomes)
    assert [
        outcome.disposition
        for outcome in handoff.scoring_outcomes
        if outcome is not None
    ] == [
        ReplayScorerDispositionV1.SCORED,
        ReplayScorerDispositionV1.SKIPPED_PROJECTION_EXCEPTION,
        ReplayScorerDispositionV1.SCORED,
        ReplayScorerDispositionV1.SKIPPED_PROJECTION_EXCEPTION,
    ]
    assert all(
        outcome is not None and outcome.request.as_of_date == _AS_OF
        for outcome in handoff.scoring_outcomes
    )

    # Provider 的第一次 [-1] 已去除 TAIL；snapshot 的第二次 [-1] 再去除 SECOND。
    assert [row["stock_code"] for row in snapshot.recommendations] == [
        "HI",
        "SELECTED_PROJECTION",
        "MID",
    ]
    _assert_v1_row(snapshot.recommendations[0], "HI", 100.0)
    selected_projection = snapshot.recommendations[1]
    assert selected_projection["stock_name"] == "名稱-SELECTED_PROJECTION"
    assert selected_projection["total_score"] == 90.0
    assert type(selected_projection["selection_reason"]) is object
    _assert_v1_row(snapshot.recommendations[2], "MID", 80.0)
    assert snapshot.canonical_execution is None


def test_second_slice_excludes_projection_failure_before_child_materialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codes = (
        "HI",
        "EMPTY",
        "BROKEN",
        "MID",
        "LO",
        "SECOND_SLICE_PROJECTION",
        "FIRST_SLICE_TAIL",
    )
    provider, scorer = _provider(
        {
            "HI": 100,
            "MID": 90,
            "LO": 80,
            "SECOND_SLICE_PROJECTION": 70,
            "FIRST_SLICE_TAIL": 60,
        },
        empty_codes={"EMPTY"},
        failing_codes={"BROKEN"},
        opaque_codes={"SECOND_SLICE_PROJECTION"},
    )
    handoffs = _capture_handoff(monkeypatch, provider)
    completions = _capture_completions(monkeypatch)

    snapshot = _run_snapshot(
        provider,
        codes,
        top_n=-1,
        parent_id="parent-r020-second-slice-projection",
    )

    assert scorer.calls == list(codes)
    assert scorer.latest_dates == [_AS_OF] * len(codes)
    assert completions == [
        ("HI", ReplayScorerDispositionV1.SCORED),
        ("EMPTY", ReplayScorerDispositionV1.SKIPPED_EMPTY),
        ("BROKEN", ReplayScorerDispositionV1.SKIPPED_SCORER_EXCEPTION),
        ("MID", ReplayScorerDispositionV1.SCORED),
        ("LO", ReplayScorerDispositionV1.SCORED),
        (
            "SECOND_SLICE_PROJECTION",
            ReplayScorerDispositionV1.SKIPPED_PROJECTION_EXCEPTION,
        ),
        ("FIRST_SLICE_TAIL", ReplayScorerDispositionV1.SCORED),
    ]
    assert len(handoffs) == 1
    handoff = handoffs[0]
    assert [row["stock_code"] for row in handoff.rows] == [
        "HI",
        "MID",
        "LO",
        "SECOND_SLICE_PROJECTION",
    ]
    assert all(outcome is not None for outcome in handoff.scoring_outcomes)
    assert [
        outcome.disposition
        for outcome in handoff.scoring_outcomes
        if outcome is not None
    ] == [
        ReplayScorerDispositionV1.SCORED,
        ReplayScorerDispositionV1.SCORED,
        ReplayScorerDispositionV1.SCORED,
        ReplayScorerDispositionV1.SKIPPED_PROJECTION_EXCEPTION,
    ]

    # The one invalid projection is present after provider slicing, then excluded
    # by the wrapper's second slice; only the three typed successes reach the child.
    assert [row["stock_code"] for row in snapshot.recommendations] == ["HI", "MID", "LO"]
    _assert_v1_row(snapshot.recommendations[0], "HI", 100.0)
    _assert_v1_row(snapshot.recommendations[1], "MID", 90.0)
    _assert_v1_row(snapshot.recommendations[2], "LO", 80.0)
    child = snapshot.canonical_execution
    assert child is not None
    assert [item.stock_code for item in child.decision.items] == ["HI", "MID", "LO"]
    assert [item.stock_code for item in child.decision.assessments] == ["HI", "MID", "LO"]
    assert child.related_references[0].reference_id == "parent-r020-second-slice-projection"


def test_native_nan_and_infinities_remain_v1_rows_and_fail_child_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codes = ("NAN", "POS_INF", "TEN", "NEG_INF", "TWENTY")
    provider, scorer = _provider(
        {
            "NAN": np.nan,
            "POS_INF": np.inf,
            "TEN": 10.0,
            "NEG_INF": -np.inf,
            "TWENTY": 20.0,
        }
    )
    completions = _capture_completions(monkeypatch)

    snapshot = _run_snapshot(
        provider,
        codes,
        top_n=len(codes),
        parent_id="parent-r020-nan-infinity",
    )

    # 既有 provider native-sort characterization 固定的 stable order。
    expected_codes = ["NAN", "POS_INF", "TWENTY", "TEN", "NEG_INF"]
    assert scorer.calls == list(codes)
    assert scorer.latest_dates == [_AS_OF] * len(codes)
    assert completions == [
        (code, ReplayScorerDispositionV1.SCORED) for code in codes
    ]
    assert [row["stock_code"] for row in snapshot.recommendations] == expected_codes
    scores_by_code = {
        row["stock_code"]: row["total_score"] for row in snapshot.recommendations
    }
    assert np.isnan(scores_by_code["NAN"])
    assert scores_by_code["POS_INF"] == np.inf
    assert scores_by_code["TWENTY"] == 20.0
    assert scores_by_code["TEN"] == 10.0
    assert scores_by_code["NEG_INF"] == -np.inf
    assert snapshot.canonical_execution is None
