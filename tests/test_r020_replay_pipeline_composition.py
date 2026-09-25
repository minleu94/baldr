"""R020 provider sort/slice 與 replay service 二次切片的聯合固定向量。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Any, cast

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


_AS_OF = date(2026, 9, 6)  # Sunday; 最後可得交易日為 2026-09-04。
_CODES = (
    "P19",
    "HI",
    "EMPTY",
    "BROKEN",
    "SELECTED_PROJECTION",
    "MID",
    "SECOND_PROJECTION",
    "TAIL",
)
_SCORED_CODES = (
    "HI",
    "EMPTY",
    "BROKEN",
    "SELECTED_PROJECTION",
    "MID",
    "SECOND_PROJECTION",
    "TAIL",
)
_FINITE_SCORES: dict[str, object] = {
    "HI": 100.0,
    "SELECTED_PROJECTION": 95.0,
    "MID": 90.0,
    "SECOND_PROJECTION": 80.0,
    "TAIL": 70.0,
}
_NONFINITE_SCORES: dict[str, object] = {
    "HI": np.nan,
    "SELECTED_PROJECTION": np.inf,
    "MID": 20.0,
    "SECOND_PROJECTION": -np.inf,
    "TAIL": 10.0,
}


def _history() -> pd.DataFrame:
    """建立 19/20/21 筆可得列、三筆不可得列與 cutoff 後 poison rows。"""

    trading_days = pd.bdate_range(end="2026-09-04", periods=21)
    rows: list[dict[str, object]] = []
    for code in _CODES:
        for index, day in enumerate(trading_days):
            available_date: object = int(day.strftime("%Y%m%d"))
            if code == "P19" and index < 2:
                available_date = None
            elif code == "HI" and index == 0:
                available_date = None
            rows.append(
                {
                    "日期": int(day.strftime("%Y%m%d")),
                    "available_date": available_date,
                    "證券代號": code,
                    "證券名稱": f"名稱-{code}",
                    "收盤價": 100 + index,
                    "成交股數": 1_000 + index,
                }
            )
        # 週一資料只供 portfolio 出場；不得進入星期日 replay 的 scorer。
        rows.append(
            {
                "日期": 20260907,
                "available_date": 20991231,
                "證券代號": code,
                "證券名稱": f"未來名稱-{code}",
                "收盤價": 999_999,
                "成交股數": 999_999,
            }
        )
    return pd.DataFrame(rows)


class _MatrixScorer:
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
        self.calls: list[tuple[str, int, date]] = []

    def generate_recommendations(
        self, stock_data: pd.DataFrame, _config: dict[str, Any]
    ) -> pd.DataFrame:
        code = str(stock_data["證券代號"].iloc[0])
        latest_date = pd.Timestamp(stock_data["日期"].iloc[-1]).date()
        self.calls.append((code, len(stock_data), latest_date))
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


class _MatrixReasonEngine:
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


@dataclass(frozen=True)
class _ReplayCase:
    name: str
    top_n: int
    scores: dict[str, object]
    opaque_codes: frozenset[str]
    expected_provider_codes: tuple[str, ...]
    expected_snapshot_codes: tuple[str, ...]
    expected_child_codes: tuple[str, ...] | None


_CASES = (
    _ReplayCase(
        name="negative_slice_excludes_projection_failure",
        top_n=-1,
        scores=_FINITE_SCORES,
        opaque_codes=frozenset({"SECOND_PROJECTION"}),
        expected_provider_codes=(
            "HI",
            "SELECTED_PROJECTION",
            "MID",
            "SECOND_PROJECTION",
        ),
        expected_snapshot_codes=("HI", "SELECTED_PROJECTION", "MID"),
        expected_child_codes=("HI", "SELECTED_PROJECTION", "MID"),
    ),
    _ReplayCase(
        name="negative_slice_keeps_selected_projection_failure",
        top_n=-1,
        scores=_FINITE_SCORES,
        opaque_codes=frozenset({"SELECTED_PROJECTION", "SECOND_PROJECTION"}),
        expected_provider_codes=(
            "HI",
            "SELECTED_PROJECTION",
            "MID",
            "SECOND_PROJECTION",
        ),
        expected_snapshot_codes=("HI", "SELECTED_PROJECTION", "MID"),
        expected_child_codes=None,
    ),
    _ReplayCase(
        name="zero_slice_is_empty_completed_child",
        top_n=0,
        scores=_FINITE_SCORES,
        opaque_codes=frozenset({"SELECTED_PROJECTION", "SECOND_PROJECTION"}),
        expected_provider_codes=(),
        expected_snapshot_codes=(),
        expected_child_codes=(),
    ),
    _ReplayCase(
        name="positive_slice_keeps_selected_projection_failure",
        top_n=2,
        scores=_FINITE_SCORES,
        opaque_codes=frozenset({"SELECTED_PROJECTION"}),
        expected_provider_codes=("HI", "SELECTED_PROJECTION"),
        expected_snapshot_codes=("HI", "SELECTED_PROJECTION"),
        expected_child_codes=None,
    ),
    _ReplayCase(
        name="native_nonfinite_order_fails_child_closed",
        top_n=5,
        scores=_NONFINITE_SCORES,
        opaque_codes=frozenset(),
        # R005/provider output-boundary native stable reverse-sort vector.
        expected_provider_codes=(
            "HI",
            "SELECTED_PROJECTION",
            "MID",
            "TAIL",
            "SECOND_PROJECTION",
        ),
        expected_snapshot_codes=(
            "HI",
            "SELECTED_PROJECTION",
            "MID",
            "TAIL",
            "SECOND_PROJECTION",
        ),
        expected_child_codes=None,
    ),
)


def _expected_v1_row(code: str, score: float) -> dict[str, object]:
    """Frozen v1 row values from the R005 compatibility contract."""

    return {
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


def test_joint_provider_and_snapshot_slice_case_matrix_preserves_r005_rows_and_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同次 replay invocation 串接 cutoff、history gate、scorer 與兩層切片。"""

    completed: list[tuple[str, ReplayScorerDispositionV1]] = []
    original_complete = RecommendationEvaluator.complete_replay_scoring

    def capture_completion(
        evaluator: RecommendationEvaluator,
        step: ReplayCandidatePrefilterStep,
        response: ReplayScorerResponseV1,
    ) -> ReplayCandidateScoringOutcomeV1:
        outcome = original_complete(evaluator, step, response)
        request = step.request
        assert type(request) is NeedCandidateScoring
        completed.append((request.stock_code, outcome.disposition))
        return outcome

    monkeypatch.setattr(
        RecommendationEvaluator,
        "complete_replay_scoring",
        capture_completion,
    )
    history = _history()
    for case in _CASES:
        call_start = len(completed)
        provider = RecommendationDataFrameProvider()
        scorer = _MatrixScorer(
            case.scores,
            empty_codes={"EMPTY"},
            failing_codes={"BROKEN"},
        )
        setattr(provider, "strategy_configurator", scorer)
        setattr(provider, "reason_engine", _MatrixReasonEngine(set(case.opaque_codes)))

        handoffs: list[ReplayProviderCallResultV1] = []
        original_handoff = provider.run_with_as_of_handoff

        def capture_handoff(
            frame: pd.DataFrame,
            config: dict[str, Any],
            top_n: int,
            as_of_date: date,
            *,
            _original=original_handoff,
        ) -> ReplayProviderCallResultV1:
            result = _original(frame, config, top_n, as_of_date)
            handoffs.append(result)
            return result

        monkeypatch.setattr(
            provider,
            "run_with_as_of_handoff",
            capture_handoff,
        )
        snapshot = RecommendationReplayService(provider).run_snapshot(
            as_of_date=_AS_OF.isoformat(),
            profile_id=f"profile-r020-{case.name}",
            config={},
            history=history,
            universe=None,
            top_n=case.top_n,
            parent_result_id=f"parent-r020-{case.name}",
        )

        assert len(handoffs) == 1
        handoff = handoffs[0]
        assert handoff.as_of_date == _AS_OF
        assert handoff.requested_top_n == case.top_n
        assert snapshot.as_of_date == _AS_OF.isoformat()
        assert snapshot.diagnostics == ["unavailable_rows_excluded:3"]

        # 19-row P19 is first-seen but fails count preflight; every other
        # candidate sees only availability-valid rows through Friday 9/4.
        assert [code for code, _rows, _date in scorer.calls] == list(_SCORED_CODES)
        assert scorer.calls == [
            ("HI", 20, date(2026, 9, 4)),
            ("EMPTY", 21, date(2026, 9, 4)),
            ("BROKEN", 21, date(2026, 9, 4)),
            ("SELECTED_PROJECTION", 21, date(2026, 9, 4)),
            ("MID", 21, date(2026, 9, 4)),
            ("SECOND_PROJECTION", 21, date(2026, 9, 4)),
            ("TAIL", 21, date(2026, 9, 4)),
        ]
        assert completed[call_start:] == [
            ("EMPTY", ReplayScorerDispositionV1.SKIPPED_EMPTY),
            ("BROKEN", ReplayScorerDispositionV1.SKIPPED_SCORER_EXCEPTION),
        ]

        assert tuple(row["stock_code"] for row in handoff.rows) == case.expected_provider_codes
        assert tuple(
            row["stock_code"] for row in snapshot.recommendations
        ) == case.expected_snapshot_codes
        assert len(handoff.rows) == len(handoff.scoring_outcomes)
        # Custom scorer 的 terminal outcome 僅為本次呼叫稽核；非空 v1 rows
        # 不攜帶 canonical scoring outcome，也不建立 child。
        assert handoff.scoring_outcomes == tuple(None for _ in handoff.rows)

        for row in snapshot.recommendations:
            code = str(row["stock_code"])
            score = cast(float | int | np.floating[Any], case.scores[code])
            assert type(score) in (float, int) or isinstance(score, np.floating)
            score_value = float(score)
            is_nan = math.isnan(score_value)
            if is_nan:
                assert math.isnan(row["total_score"])
            else:
                assert row["total_score"] == score_value
            expected = _expected_v1_row(code, 0.0 if is_nan else score_value)
            assert row["stock_code"] == expected["stock_code"]
            assert row["stock_name"] == expected["stock_name"]
            assert row["factor_scores"] == expected["factor_scores"]
            if code in case.opaque_codes:
                assert type(row["selection_reason"]) is object
            else:
                assert row["selection_reason"] == expected["selection_reason"]

        if handoff.rows:
            # `expected_child_codes` 記錄責任轉移前 custom scorer 可重建 child
            # 的歷史基準；目前 custom scorer 只保留 v1 rows，不建 canonical child。
            assert snapshot.canonical_execution is None
        elif case.expected_child_codes == ():
            # 零列是 provider 的 empty slice，沒有 custom scored row 可供重建；保留
            # 原有、帶相同 parent reference 的合法空 execution。
            child = snapshot.canonical_execution
            assert child is not None
            assert child.related_references[0].reference_id == (
                f"parent-r020-{case.name}"
            )
            decision = child.decision
            assert decision is not None
            assert decision.items == ()
            assert decision.assessments == ()
        else:
            assert snapshot.canonical_execution is None
