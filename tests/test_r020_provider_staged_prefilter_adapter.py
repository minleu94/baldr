"""R020 DataFrame provider 對 staged replay prefilter 的接線契約測試。"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import pytest
import numpy as np

import decision_module.recommendation.evaluate as replay_evaluate_module
from app_module.recommendation_dataframe_provider import (
    RecommendationDataFrameProvider,
    _LegacyFastFilterTraceCapture,
)
from decision_module.recommendation.evaluate import (
    NeedCandidateScoring,
    NeedReplayPrefilterFact,
    RecommendationEvaluator,
    ReplayCandidateHistoryFacts,
    ReplayCandidatePrefilterStep,
    ReplayCandidatePrefilterState,
    ReplayPrefilterFactResponse,
)
from decision_module.recommendation.replay_prefilter import (
    ReplayFastFilterPolicyV1,
    ReplayMetricStatus,
    ReplayPrefilterFactKind,
    ReplayPrefilterObservations,
    ReplayPreflightDisposition,
)


class _RecordingScorer:
    def __init__(self) -> None:
        self.inputs: list[pd.DataFrame] = []

    def generate_recommendations(self, stock_data: pd.DataFrame, config: dict) -> pd.DataFrame:
        self.inputs.append(stock_data.copy(deep=True))
        result = stock_data.copy(deep=True)
        result["FinalScore"] = 80
        return result


class _FixedReasonEngine:
    def generate_reasons(self, latest_row: pd.Series, config: dict) -> list[str]:
        return ["staged-prefilter-fixture"]

    def format_reason_text(self, reasons: list[str], max_reasons: int = 3) -> str:
        return "|".join(reasons[:max_reasons])


class _FloatProbe:
    def __init__(
        self,
        name: str,
        calls: list[str],
        value: float,
        *,
        fail: bool = False,
        events: list[str] | None = None,
    ) -> None:
        self.name = name
        self.calls = calls
        self.value = value
        self.fail = fail
        self.events = events

    def __float__(self) -> float:
        self.calls.append(self.name)
        if self.events is not None:
            self.events.append(f"convert:{self.name}")
        if self.fail:
            raise ValueError(f"synthetic invalid threshold: {self.name}")
        return self.value


class _RejectingAppendList(list[Any]):
    def append(self, item: Any) -> None:
        raise RuntimeError("synthetic optional trace sink failure")


class _StagedEvaluatorSpy:
    def __init__(self) -> None:
        self.start_facts: list[ReplayCandidateHistoryFacts] = []
        self.start_policies: list[ReplayFastFilterPolicyV1] = []
        self.requests: list[NeedReplayPrefilterFact] = []
        self.scoring_requests: list[NeedCandidateScoring] = []
        self.responses: list[ReplayPrefilterFactResponse] = []
        self.prefilter_inputs: list[
            tuple[ReplayFastFilterPolicyV1, ReplayPrefilterObservations]
        ] = []
        self.prefilter_outcomes: list[Any] = []
        self.events: list[str] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        original_start = RecommendationEvaluator.start_replay_prefilter
        original_advance = RecommendationEvaluator.advance_replay_prefilter
        original_prefilter = replay_evaluate_module.evaluate_replay_prefilter

        def record_step(step: ReplayCandidatePrefilterStep) -> None:
            if type(step.request) is NeedReplayPrefilterFact:
                self.requests.append(step.request)
                self.events.append(f"request:{step.request.kind.value}")
            elif type(step.request) is NeedCandidateScoring:
                self.scoring_requests.append(step.request)
                self.events.append("request:candidate_scoring")

        def start(
            evaluator: RecommendationEvaluator,
            facts: ReplayCandidateHistoryFacts,
            policy: ReplayFastFilterPolicyV1,
        ) -> ReplayCandidatePrefilterStep:
            self.events.append("evaluator:start")
            self.start_facts.append(facts)
            self.start_policies.append(policy)
            step = original_start(evaluator, facts, policy)
            record_step(step)
            return step

        def advance(
            evaluator: RecommendationEvaluator,
            state: ReplayCandidatePrefilterState,
            response: ReplayPrefilterFactResponse | None,
        ) -> ReplayCandidatePrefilterStep:
            if response is not None:
                self.responses.append(response)
                self.events.append(f"response:{response.request.kind.value}")
            step = original_advance(evaluator, state, response)
            record_step(step)
            return step

        def evaluate(
            policy: ReplayFastFilterPolicyV1,
            observations: ReplayPrefilterObservations,
            **stage_kwargs: Any,
        ) -> Any:
            self.events.append("decision:evaluate_replay_prefilter")
            self.prefilter_inputs.append((policy, observations))
            outcome = original_prefilter(policy, observations, **stage_kwargs)
            self.prefilter_outcomes.append(outcome)
            return outcome

        monkeypatch.setattr(RecommendationEvaluator, "start_replay_prefilter", start)
        monkeypatch.setattr(RecommendationEvaluator, "advance_replay_prefilter", advance)
        monkeypatch.setattr(
            replay_evaluate_module,
            "evaluate_replay_prefilter",
            evaluate,
        )


def _provider() -> tuple[RecommendationDataFrameProvider, _RecordingScorer]:
    provider = RecommendationDataFrameProvider()
    scorer = _RecordingScorer()
    provider.strategy_configurator = scorer
    provider.reason_engine = _FixedReasonEngine()
    return provider, scorer


def _history(*, rows: int = 21, dtype: str = "float64") -> pd.DataFrame:
    dates = pd.date_range("2026-08-12", periods=rows, freq="D")
    close = [100.0] * rows
    volume = [100.0] * rows
    if rows >= 2:
        close[-1] = 101.0
    if rows >= 21:
        volume[-1] = 110.0
    return pd.DataFrame(
        {
            "日期": [int(value.strftime("%Y%m%d")) for value in dates],
            "證券代號": ["STAGED"] * rows,
            "證券名稱": ["staged fixture"] * rows,
            "收盤價": pd.Series(close, dtype=dtype),
            "成交股數": pd.Series(volume, dtype=dtype),
        }
    )


def _request_kinds(spy: _StagedEvaluatorSpy) -> list[ReplayPrefilterFactKind]:
    return [request.kind for request in spy.requests]


def test_provider_drives_staged_prefilter_in_lazy_price_then_volume_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spy = _StagedEvaluatorSpy()
    spy.install(monkeypatch)
    conversions: list[str] = []
    provider, scorer = _provider()
    requested_as_of = date(2026, 9, 2)

    result = provider.run_with_as_of(
        _history(),
        {
            "filters": {
                "price_change_min": _FloatProbe(
                    "price_min", conversions, 0.0, events=spy.events
                ),
                "price_change_max": _FloatProbe(
                    "price_max", conversions, 2.0, events=spy.events
                ),
                "volume_ratio_min": _FloatProbe(
                    "volume_min", conversions, 1.1, events=spy.events
                ),
            }
        },
        top_n=5,
        as_of_date=requested_as_of,
    )

    assert [item["stock_code"] for item in result] == ["STAGED"]
    assert len(scorer.inputs) == 1
    assert conversions == ["price_min", "price_max", "volume_min"]
    assert spy.start_facts
    assert spy.prefilter_inputs
    assert _request_kinds(spy) == [
        ReplayPrefilterFactKind.PRICE_CHANGE_METRIC,
        ReplayPrefilterFactKind.PRICE_CHANGE_MIN_THRESHOLD,
        ReplayPrefilterFactKind.PRICE_CHANGE_MAX_THRESHOLD,
        ReplayPrefilterFactKind.VOLUME_CHANGE_METRIC,
        ReplayPrefilterFactKind.VOLUME_CHANGE_MIN_THRESHOLD,
    ]

    facts = spy.start_facts[0]
    assert facts.observations.as_of_date == requested_as_of
    assert facts.observations.maximum_row_date == date(2026, 9, 1)
    assert all(request.as_of_date == requested_as_of for request in spy.requests)
    assert all(request.invocation_id == facts.invocation_id for request in spy.requests)
    assert spy.prefilter_outcomes[-1].disposition is ReplayPreflightDisposition.READY
    assert spy.events.index("request:price_change_min_threshold") < spy.events.index(
        "convert:price_min"
    )
    assert spy.events.index("convert:price_min") < spy.events.index(
        "request:price_change_max_threshold"
    )
    assert spy.events.index("request:price_change_max_threshold") < spy.events.index(
        "convert:price_max"
    )
    assert spy.events.index("convert:price_max") < spy.events.index(
        "request:volume_change_metric"
    )
    assert spy.events.index("request:volume_change_min_threshold") < spy.events.index(
        "convert:volume_min"
    )


def test_price_minimum_reject_does_not_resolve_bad_maximum_or_volume_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spy = _StagedEvaluatorSpy()
    spy.install(monkeypatch)
    conversions: list[str] = []
    provider, scorer = _provider()

    result = provider(
        _history(),
        {
            "filters": {
                "price_change_min": _FloatProbe("price_min", conversions, 100.0),
                "price_change_max": "bad",
                "volume_ratio_min": _FloatProbe(
                    "volume_min", conversions, 1.0, fail=True
                ),
            }
        },
        top_n=5,
    )

    assert result == []
    assert scorer.inputs == []
    assert conversions == ["price_min"]
    assert _request_kinds(spy) == [
        ReplayPrefilterFactKind.PRICE_CHANGE_METRIC,
        ReplayPrefilterFactKind.PRICE_CHANGE_MIN_THRESHOLD,
    ]
    assert spy.prefilter_outcomes[-1].disposition is ReplayPreflightDisposition.REJECT
    assert spy.prefilter_outcomes[-1].reason_code == "price_change_below_min"


def test_price_minimum_reject_does_not_project_float16_overflowing_maximum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spy = _StagedEvaluatorSpy()
    spy.install(monkeypatch)
    conversions: list[str] = []
    provider, scorer = _provider()

    with np.errstate(over="raise"):
        result = provider(
            _history(dtype="float16"),
            {
                "filters": {
                    "price_change_min": _FloatProbe(
                        "price_min", conversions, 100.0, events=spy.events
                    ),
                    "price_change_max": _FloatProbe(
                        "price_max", conversions, 1e100, events=spy.events
                    ),
                    "volume_ratio_min": _FloatProbe(
                        "volume_min", conversions, 1.1, fail=True, events=spy.events
                    ),
                }
            },
            top_n=5,
        )

    assert result == []
    assert scorer.inputs == []
    assert conversions == ["price_min"]
    assert _request_kinds(spy) == [
        ReplayPrefilterFactKind.PRICE_CHANGE_METRIC,
        ReplayPrefilterFactKind.PRICE_CHANGE_MIN_THRESHOLD,
    ]


def test_twenty_rows_never_request_or_convert_volume_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spy = _StagedEvaluatorSpy()
    spy.install(monkeypatch)
    conversions: list[str] = []
    provider, scorer = _provider()

    result = provider.run_with_as_of(
        _history(rows=20),
        {
            "filters": {
                "volume_ratio_min": _FloatProbe(
                    "volume_min", conversions, 1.1, fail=True
                )
            }
        },
        top_n=5,
        as_of_date=date(2026, 9, 2),
    )

    assert [item["stock_code"] for item in result] == ["STAGED"]
    assert len(scorer.inputs) == 1
    assert conversions == []
    assert _request_kinds(spy) == []
    assert len(spy.scoring_requests) == 1
    assert spy.scoring_requests[0].history_rows == 20
    assert spy.start_facts[0].observations.volume_change_status is (
        ReplayMetricStatus.INSUFFICIENT_WINDOW
    )
    assert spy.start_facts[0].observations.as_of_date == date(2026, 9, 2)


def test_optional_trace_sink_failure_does_not_change_provider_decision() -> None:
    history = _history()
    config = {"filters": {"price_change_min": "0"}}
    baseline_provider, baseline_scorer = _provider()
    traced_provider, traced_scorer = _provider()
    sink = _LegacyFastFilterTraceCapture()
    sink.events = _RejectingAppendList()

    baseline = baseline_provider(history, config, top_n=5)
    traced = traced_provider(history, config, top_n=5, capture_sink=sink)

    assert traced == baseline
    assert len(baseline_scorer.inputs) == len(traced_scorer.inputs) == 1
    assert sink.available is False


def test_nonempty_filters_still_compute_legacy_price_metric_without_price_threshold() -> None:
    provider, scorer = _provider()
    history = _history(dtype="float16")
    history["收盤價"] = np.asarray([0.01] * 20 + [65], dtype="float16")
    capture = _LegacyFastFilterTraceCapture()

    def legacy_metric_terminal() -> tuple[object, ...]:
        try:
            previous = pd.to_numeric(history.iloc[-2].get("收盤價", 0), errors="coerce")
            current = pd.to_numeric(history.iloc[-1].get("收盤價", 0), errors="coerce")
            metric = ((current - previous) / previous * 100) if previous and not pd.isna(previous) else 0
            return ("value", metric)
        except Exception as exc:
            return ("exception", type(exc), str(exc))

    def provider_terminal() -> tuple[object, ...]:
        try:
            rows = provider(
                history,
                {"filters": {"unrelated_filter": True}},
                top_n=5,
                capture_sink=capture,
            )
            return ("value", rows)
        except Exception as exc:
            return ("exception", type(exc), str(exc))

    with np.errstate(over="raise"):
        legacy_terminal = legacy_metric_terminal()
        actual_terminal = provider_terminal()

    assert legacy_terminal[0] == actual_terminal[0]
    if legacy_terminal[0] == "exception":
        assert actual_terminal == legacy_terminal
        assert scorer.inputs == []
        assert capture.available is False
    else:
        assert actual_terminal[0] == "value"
        assert [item["stock_code"] for item in actual_terminal[1]] == ["STAGED"]
        assert len(scorer.inputs) == 1
        assert capture.available is True
        assert any(event.stage.value == "price_change_metric" for event in capture.events)
