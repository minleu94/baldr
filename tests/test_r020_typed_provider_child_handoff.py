"""R020 concrete provider 至 typed replay child 的合成整合回歸。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date
from decimal import Decimal
from threading import Barrier, Lock
from typing import Any

import numpy as np
import pandas as pd
import pytest

import app_module.recommendation_replay_service as replay_service_module
from app_module.recommendation_dataframe_provider import (
    RecommendationDataFrameProvider,
    ReplayProviderCallResultV1,
)
from app_module.recommendation_replay_service import RecommendationReplayService
from decision_module.recommendation.evaluate import ReplayScorerDispositionV1


def _history(codes: tuple[str, ...], *, periods: int = 26) -> pd.DataFrame:
    dates = pd.date_range("2026-09-01", periods=periods, freq="D")
    rows: list[dict[str, object]] = []
    for code in codes:
        for index, day in enumerate(dates):
            date_key = int(day.strftime("%Y%m%d"))
            rows.append(
                {
                    "日期": date_key,
                    "available_date": date_key,
                    "證券代號": code,
                    "證券名稱": f"名稱-{code}",
                    "收盤價": 100 + index,
                    "成交股數": 1_000 + index,
                }
            )
    return pd.DataFrame(
        rows,
        columns=[
            "日期",
            "available_date",
            "證券代號",
            "證券名稱",
            "收盤價",
            "成交股數",
        ],
    )


class _SyntheticScorer:
    def __init__(
        self,
        scores: dict[str, object] | None = None,
        *,
        empty_codes: set[str] | None = None,
        failing_codes: set[str] | None = None,
        score_from_latest_day: bool = False,
        barrier: Barrier | None = None,
    ) -> None:
        self.scores = scores or {}
        self.empty_codes = empty_codes or set()
        self.failing_codes = failing_codes or set()
        self.score_from_latest_day = score_from_latest_day
        self.barrier = barrier
        self.calls: list[str] = []
        self.latest_days: list[date] = []
        self._lock = Lock()

    def generate_recommendations(
        self, stock_data: pd.DataFrame, _config: dict[str, Any]
    ) -> pd.DataFrame:
        code = str(stock_data["證券代號"].iloc[0])
        latest_day = pd.Timestamp(stock_data["日期"].iloc[-1]).date()
        with self._lock:
            self.calls.append(code)
            self.latest_days.append(latest_day)
        if self.barrier is not None:
            self.barrier.wait(timeout=5)
        if code in self.failing_codes:
            raise RuntimeError(f"合成 scorer 錯誤：{code}")
        if code in self.empty_codes:
            return stock_data.iloc[0:0].copy()

        result = stock_data.copy(deep=True)
        if self.score_from_latest_day:
            score: object = latest_day.day
        else:
            score = self.scores.get(code, 80)
        result["FinalScore"] = score
        result["IndicatorScore"] = 61
        result["PatternScore"] = 12
        result["VolumeScore"] = 7
        result["BrokerFlowScore"] = 3
        result["RevenueScore"] = 2
        return result


class _SyntheticReasonEngine:
    def __init__(self, *, opaque_codes: set[str] | None = None) -> None:
        self.opaque_codes = opaque_codes or set()

    def generate_reasons(self, latest_row: pd.Series, _config: dict[str, Any]) -> list[str]:
        return [f"合成理由-{latest_row['證券代號']}"]

    def format_reason_text(self, reasons: list[str], max_reasons: int = 3) -> object:
        code = reasons[0].removeprefix("合成理由-") if reasons else ""
        if code in self.opaque_codes:
            return object()
        return "|".join(reasons[:max_reasons])


def _provider(
    scores: dict[str, object] | None = None,
    *,
    empty_codes: set[str] | None = None,
    failing_codes: set[str] | None = None,
    opaque_codes: set[str] | None = None,
    score_from_latest_day: bool = False,
    barrier: Barrier | None = None,
) -> tuple[RecommendationDataFrameProvider, _SyntheticScorer]:
    provider = RecommendationDataFrameProvider()
    scorer = _SyntheticScorer(
        scores,
        empty_codes=empty_codes,
        failing_codes=failing_codes,
        score_from_latest_day=score_from_latest_day,
        barrier=barrier,
    )
    provider.strategy_configurator = scorer
    provider.reason_engine = _SyntheticReasonEngine(opaque_codes=opaque_codes)
    return provider, scorer


def _capture_handoffs(
    monkeypatch: pytest.MonkeyPatch,
    provider: RecommendationDataFrameProvider,
) -> list[ReplayProviderCallResultV1]:
    captured: list[ReplayProviderCallResultV1] = []
    original = provider.run_with_as_of_handoff

    def capture(
        as_of_data: pd.DataFrame,
        config: dict[str, Any],
        top_n: int,
        as_of_date: date,
    ) -> ReplayProviderCallResultV1:
        result = original(as_of_data, config, top_n, as_of_date)
        captured.append(result)
        return result

    monkeypatch.setattr(provider, "run_with_as_of_handoff", capture)
    return captured


def _run_snapshot(
    provider: object,
    history: pd.DataFrame,
    *,
    top_n: int = 5,
    as_of_date: str = "2026-09-24",
    parent_result_id: str = "parent-r020-synthetic",
):
    return RecommendationReplayService(provider).run_snapshot(
        as_of_date=as_of_date,
        profile_id="profile-r020-synthetic",
        config={},
        history=history,
        universe=None,
        top_n=top_n,
        parent_result_id=parent_result_id,
    )


def _forbid_legacy_row_parser() -> None:
    assert not hasattr(replay_service_module, "_build_canonical_replay_execution")


def test_concrete_provider_uses_one_scorer_pass_for_typed_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codes = ("A", "B", "C")
    provider, scorer = _provider({"A": 90, "B": 80, "C": 70})
    handoffs = _capture_handoffs(monkeypatch, provider)
    _forbid_legacy_row_parser()

    def forbid_list_path(*_args: object, **_kwargs: object) -> list[dict[str, object]]:
        pytest.fail("concrete provider 應使用明示 typed handoff")

    monkeypatch.setattr(provider, "run_with_as_of", forbid_list_path)
    snapshot = _run_snapshot(provider, _history(codes))

    assert len(scorer.calls) == len(codes)
    assert sorted(scorer.calls) == sorted(codes)
    assert scorer.latest_days == [date(2026, 9, 24)] * len(codes)
    assert len(handoffs) == 1
    handoff = handoffs[0]
    assert type(handoff) is ReplayProviderCallResultV1
    assert handoff.as_of_date == date(2026, 9, 24)
    assert handoff.requested_top_n == 5
    assert [row["stock_code"] for row in handoff.rows] == ["A", "B", "C"]
    assert all(outcome is not None for outcome in handoff.scoring_outcomes)

    child = snapshot.canonical_execution
    assert child is not None
    assert child.context.as_of_date == date(2026, 9, 24)
    assert child.request.as_of_date == date(2026, 9, 24)
    assert child.related_references[0].reference_id == "parent-r020-synthetic"
    assert child.decision.items == tuple(
        outcome.item for outcome in handoff.scoring_outcomes if outcome is not None
    )
    assert child.decision.assessments == tuple(
        outcome.assessment
        for outcome in handoff.scoring_outcomes
        if outcome is not None
    )
    assert [row["stock_code"] for row in snapshot.recommendations] == [
        item.stock_code for item in child.decision.items
    ]


def test_typed_provider_children_keep_distinct_result_ids() -> None:
    provider, _scorer = _provider({"A": 85})
    history = _history(("A",))

    first = _run_snapshot(
        provider,
        history,
        parent_result_id="parent-r020-typed-distinct",
    )
    second = _run_snapshot(
        provider,
        history,
        parent_result_id="parent-r020-typed-distinct",
    )

    first_child = first.canonical_execution
    second_child = second.canonical_execution
    assert first_child is not None
    assert second_child is not None
    assert first_child.result_id != second_child.result_id
    assert first_child.related_references[0].reference_id == "parent-r020-typed-distinct"
    assert second_child.related_references[0].reference_id == "parent-r020-typed-distinct"


def test_handoff_rows_match_legacy_provider_rows_for_the_same_synthetic_input() -> None:
    provider, scorer = _provider({"A": 75, "B": 92, "C": 80})
    history = _history(("A", "B", "C"), periods=24)
    config = {"filters": {"price_change_min": "0"}}

    legacy_rows = provider.run_with_as_of(
        history,
        config,
        3,
        date(2026, 9, 24),
    )
    legacy_call_count = len(scorer.calls)
    handoff = provider.run_with_as_of_handoff(
        history,
        config,
        3,
        date(2026, 9, 24),
    )

    assert type(handoff) is ReplayProviderCallResultV1
    assert handoff.rows == legacy_rows
    assert len(scorer.calls) == legacy_call_count * 2
    assert len(handoff.rows) == len(handoff.scoring_outcomes)
    assert all(outcome is not None for outcome in handoff.scoring_outcomes)


@pytest.mark.parametrize(
    ("top_n", "provider_codes", "snapshot_codes"),
    [
        (-1, ["A", "B", "C", "D"], ["A", "B", "C"]),
        (0, [], []),
    ],
)
def test_typed_child_preserves_provider_then_snapshot_double_slice(
    monkeypatch: pytest.MonkeyPatch,
    top_n: int,
    provider_codes: list[str],
    snapshot_codes: list[str],
) -> None:
    codes = ("A", "B", "C", "D", "E")
    provider, scorer = _provider(
        {code: 100 - index * 10 for index, code in enumerate(codes)}
    )
    handoffs = _capture_handoffs(monkeypatch, provider)
    _forbid_legacy_row_parser()

    snapshot = _run_snapshot(provider, _history(codes), top_n=top_n)

    assert len(scorer.calls) == len(codes)
    assert len(handoffs) == 1
    handoff = handoffs[0]
    assert [row["stock_code"] for row in handoff.rows] == provider_codes
    assert [row["stock_code"] for row in snapshot.recommendations] == snapshot_codes
    assert [item.stock_code for item in snapshot.canonical_execution.decision.items] == snapshot_codes
    assert [item.stock_code for item in snapshot.canonical_execution.decision.assessments] == snapshot_codes
    assert snapshot.canonical_execution.request.top_n is None


def test_empty_snapshot_keeps_completed_empty_child_but_nonfinite_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    empty_provider, empty_scorer = _provider()
    _forbid_legacy_row_parser()
    empty_snapshot = _run_snapshot(
        empty_provider,
        _history((), periods=0),
        parent_result_id="parent-r020-empty",
    )

    assert empty_scorer.calls == []
    assert empty_snapshot.recommendations == []
    assert empty_snapshot.canonical_execution is not None
    assert empty_snapshot.canonical_execution.decision.items == ()
    assert empty_snapshot.canonical_execution.decision.assessments == ()

    skipped_provider, skipped_scorer = _provider(empty_codes={"EMPTY"})
    skipped_snapshot = _run_snapshot(
        skipped_provider,
        _history(("EMPTY",)),
        parent_result_id="parent-r020-empty-scorer",
    )
    assert skipped_scorer.calls == ["EMPTY"]
    assert skipped_snapshot.recommendations == []
    assert skipped_snapshot.canonical_execution is not None
    assert skipped_snapshot.canonical_execution.decision.items == ()
    assert skipped_snapshot.canonical_execution.decision.assessments == ()

    nan_provider, nan_scorer = _provider({"NAN": np.nan})
    nan_snapshot = _run_snapshot(
        nan_provider,
        _history(("NAN",)),
        parent_result_id="parent-r020-nan",
    )

    assert nan_scorer.calls == ["NAN"]
    assert len(nan_snapshot.recommendations) == 1
    assert np.isnan(nan_snapshot.recommendations[0]["total_score"])
    assert nan_snapshot.canonical_execution is None


def test_typed_projection_failure_keeps_v1_row_without_canonical_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, _scorer = _provider({"OPAQUE": 80}, opaque_codes={"OPAQUE"})
    handoffs = _capture_handoffs(monkeypatch, provider)
    _forbid_legacy_row_parser()

    snapshot = _run_snapshot(
        provider,
        _history(("OPAQUE",)),
        parent_result_id="parent-r020-projection-error",
    )

    assert len(snapshot.recommendations) == 1
    assert snapshot.recommendations[0]["stock_code"] == "OPAQUE"
    assert len(handoffs) == 1
    outcome = handoffs[0].scoring_outcomes[0]
    assert outcome is not None
    assert outcome.disposition is ReplayScorerDispositionV1.SKIPPED_PROJECTION_EXCEPTION
    assert snapshot.canonical_execution is None


def test_blank_stock_code_without_effective_threshold_keeps_legacy_row_only() -> None:
    provider, scorer = _provider({"": 80})
    history = _history(("",), periods=24)

    snapshot = RecommendationReplayService(provider).run_snapshot(
        as_of_date="2026-09-24",
        profile_id="profile-r020-blank-no-threshold",
        config={"filters": {"price_change_min": None}},
        history=history,
        universe=None,
        top_n=5,
        parent_result_id="parent-r020-blank-no-threshold",
    )

    assert scorer.calls == [""]
    assert len(snapshot.recommendations) == 1
    assert snapshot.recommendations[0]["stock_code"] == ""
    assert snapshot.canonical_execution is None


@pytest.mark.parametrize("corruption", ["row_score", "row_reason", "outcome_order"])
def test_handoff_row_and_outcome_mismatch_keeps_rows_without_child(
    monkeypatch: pytest.MonkeyPatch,
    corruption: str,
) -> None:
    provider, _scorer = _provider({"A": 90, "B": 80})
    original = provider.run_with_as_of_handoff
    returned: list[ReplayProviderCallResultV1] = []

    def corrupt_handoff(
        as_of_data: pd.DataFrame,
        config: dict[str, Any],
        top_n: int,
        as_of_date: date,
    ) -> ReplayProviderCallResultV1:
        result = original(as_of_data, config, top_n, as_of_date)
        rows = [dict(row) for row in result.rows]
        outcomes = result.scoring_outcomes
        if corruption == "row_score":
            rows[0]["total_score"] = 999.0
        elif corruption == "row_reason":
            rows[0]["selection_reason"] = "遭竄改的理由"
        else:
            outcomes = tuple(reversed(outcomes))
        changed = replace(result, rows=rows, scoring_outcomes=outcomes)
        returned.append(changed)
        return changed

    monkeypatch.setattr(provider, "run_with_as_of_handoff", corrupt_handoff)
    _forbid_legacy_row_parser()

    snapshot = _run_snapshot(
        provider,
        _history(("A", "B")),
        parent_result_id=f"parent-r020-mismatch-{corruption}",
    )

    assert len(returned) == 1
    expected_rows = returned[0].rows
    assert snapshot.recommendations == expected_rows
    if corruption == "row_score":
        assert snapshot.recommendations[0]["total_score"] == 999.0
    elif corruption == "row_reason":
        assert snapshot.recommendations[0]["selection_reason"] == "遭竄改的理由"
    else:
        assert [row["stock_code"] for row in snapshot.recommendations] == ["A", "B"]
    assert snapshot.canonical_execution is None


def _legacy_row(code: str, score: int) -> dict[str, object]:
    return {
        "stock_code": code,
        "stock_name": f"舊路徑-{code}",
        "total_score": score,
        "factor_scores": {"technical": 61, "pattern": 12, "volume": 7},
        "selection_reason": f"舊路徑理由-{code}",
    }


def test_three_argument_legacy_callable_keeps_plain_list_route() -> None:
    calls: list[tuple[dict[str, Any], int, date | None]] = []

    def legacy_provider(
        data: pd.DataFrame,
        config: dict[str, Any],
        top_n: int,
    ) -> list[dict[str, object]]:
        latest = pd.Timestamp(data["日期"].max()).date()
        calls.append((config, top_n, latest))
        return [_legacy_row("LEGACY", 77)]

    snapshot = _run_snapshot(
        legacy_provider,
        _history(("A",)),
        parent_result_id="parent-r020-three-arg",
    )

    assert len(calls) == 1
    assert calls[0][1] == 5
    assert calls[0][2] == date(2026, 9, 24)
    assert [row["stock_code"] for row in snapshot.recommendations] == ["LEGACY"]
    assert snapshot.replay_parent_id == "parent-r020-three-arg"
    assert snapshot.canonical_execution is None


def test_subclass_overriding_run_with_as_of_keeps_legacy_list_route() -> None:
    class CustomProvider(RecommendationDataFrameProvider):
        def __init__(self) -> None:
            super().__init__()
            self.legacy_calls: list[date] = []
            self.handoff_calls = 0

        def run_with_as_of(
            self,
            _data: pd.DataFrame,
            _config: dict[str, Any],
            _top_n: int,
            as_of_date: date,
        ) -> list[dict[str, object]]:
            self.legacy_calls.append(as_of_date)
            return [_legacy_row("SUBCLASS", 66)]

        def run_with_as_of_handoff(
            self,
            _data: pd.DataFrame,
            _config: dict[str, Any],
            _top_n: int,
            _as_of_date: date,
        ) -> ReplayProviderCallResultV1:
            self.handoff_calls += 1
            raise AssertionError("subclass must retain the overridden list route")

    provider = CustomProvider()
    snapshot = _run_snapshot(
        provider,
        _history(("A",)),
        parent_result_id="parent-r020-subclass",
    )

    assert provider.legacy_calls == [date(2026, 9, 24)]
    assert provider.handoff_calls == 0
    assert snapshot.recommendations == [_legacy_row("SUBCLASS", 66)]
    assert snapshot.replay_parent_id == "parent-r020-subclass"
    assert snapshot.canonical_execution is None


def test_subclass_with_legacy_three_argument_call_does_not_receive_hidden_kwargs() -> None:
    class ThreeArgCallSubclass(RecommendationDataFrameProvider):
        def __init__(self) -> None:
            super().__init__()
            self.calls: list[tuple[int, date]] = []

        def __call__(
            self,
            data: pd.DataFrame,
            _config: dict[str, Any],
            top_n: int,
        ) -> list[dict[str, object]]:
            self.calls.append(
                (top_n, pd.Timestamp(data["日期"].max()).date())
            )
            return [_legacy_row("THREE-ARG-SUBCLASS", 63)]

    provider = ThreeArgCallSubclass()
    snapshot = _run_snapshot(
        provider,
        _history(("A",)),
        parent_result_id="parent-r020-three-arg-subclass",
    )

    assert provider.calls == [(5, date(2026, 9, 24))]
    assert [row["stock_code"] for row in snapshot.recommendations] == [
        "THREE-ARG-SUBCLASS"
    ]
    assert snapshot.replay_parent_id == "parent-r020-three-arg-subclass"
    assert snapshot.canonical_execution is None


def test_subclass_accepting_call_context_keeps_inherited_as_of_route() -> None:
    class ContextAwareCallSubclass(RecommendationDataFrameProvider):
        def __init__(self) -> None:
            super().__init__()
            self.context_dates: list[date | None] = []
            self.latest_data_dates: list[date] = []

        def __call__(
            self,
            data: pd.DataFrame,
            _config: dict[str, Any],
            _top_n: int,
            *,
            _call_context: object | None = None,
        ) -> list[dict[str, object]]:
            self.latest_data_dates.append(pd.Timestamp(data["日期"].max()).date())
            context_date = getattr(_call_context, "as_of_date", None)
            self.context_dates.append(context_date)
            return [_legacy_row("CONTEXT-SUBCLASS", 64)]

    provider = ContextAwareCallSubclass()
    snapshot = _run_snapshot(
        provider,
        _history(("A",)),
        parent_result_id="parent-r020-context-subclass",
    )

    assert provider.context_dates == [date(2026, 9, 24)]
    assert provider.latest_data_dates == [date(2026, 9, 24)]
    assert snapshot.recommendations == [_legacy_row("CONTEXT-SUBCLASS", 64)]
    assert snapshot.replay_parent_id == "parent-r020-context-subclass"
    assert snapshot.canonical_execution is None


def test_parallel_concrete_provider_calls_keep_cutoff_and_scoring_local() -> None:
    codes = ("TICK",)
    barrier = Barrier(2)
    provider, scorer = _provider(score_from_latest_day=True, barrier=barrier)
    service = RecommendationReplayService(provider)
    history = _history(codes)

    def run(as_of: str, parent: str):
        return service.run_snapshot(
            as_of_date=as_of,
            profile_id=f"profile-{parent}",
            config={},
            history=history,
            universe=None,
            top_n=5,
            parent_result_id=parent,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        early_future = pool.submit(run, "2026-09-20", "parent-r020-early")
        late_future = pool.submit(run, "2026-09-24", "parent-r020-late")
        early = early_future.result(timeout=10)
        late = late_future.result(timeout=10)

    assert len(scorer.calls) == 2
    assert set(scorer.latest_days) == {date(2026, 9, 20), date(2026, 9, 24)}
    for snapshot, expected_date, expected_parent in (
        (early, date(2026, 9, 20), "parent-r020-early"),
        (late, date(2026, 9, 24), "parent-r020-late"),
    ):
        child = snapshot.canonical_execution
        assert child is not None
        assert child.context.as_of_date == expected_date
        assert child.request.as_of_date == expected_date
        assert child.related_references[0].reference_id == expected_parent
        assessment = child.decision.assessments[0]
        prefilter = assessment.filter_outcomes["replay_prefilter"]
        assert prefilter.evidence["as_of_date"] == expected_date.isoformat()
        assert child.decision.items[0].rule_score == Decimal(str(expected_date.day))
