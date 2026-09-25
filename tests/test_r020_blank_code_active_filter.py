"""R020 空白代碼 active-filter 相容路徑契約。"""

from __future__ import annotations

from dataclasses import fields
from datetime import date

import pandas as pd
import pytest

from app_module.recommendation_dataframe_provider import RecommendationDataFrameProvider
from app_module.recommendation_replay_service import RecommendationReplayService
from decision_module.recommendation.evaluate import (
    NeedCompatibilityScoring,
    RecommendationEvaluator,
    ReplayCandidateHistoryFacts,
    ReplayCandidatePrefilterStep,
)
from decision_module.recommendation.replay_prefilter import (
    ReplayCompatibilityCandidateKeyV1,
    ReplayCompatibilityPrefilterObservationsV1,
    ReplayPrefilterObservations,
    ReplayFastFilterPolicyV1,
)


class _ProbeThreshold:
    def __init__(
        self,
        name: str,
        calls: list[str],
        value: float,
        *,
        fail: bool = False,
    ) -> None:
        self.name = name
        self.calls = calls
        self.value = value
        self.fail = fail

    def __float__(self) -> float:
        self.calls.append(self.name)
        if self.fail:
            raise ValueError(f"synthetic threshold failure: {self.name}")
        return self.value


class _Scorer:
    def __init__(self, scores: dict[str, int] | None = None) -> None:
        self.scores = scores or {}
        self.stock_codes: list[str] = []
        self.inputs: list[pd.DataFrame] = []

    def generate_recommendations(
        self, stock_data: pd.DataFrame, config: dict[str, object]
    ) -> pd.DataFrame:
        self.inputs.append(stock_data.copy(deep=True))
        stock_code = str(stock_data["證券代號"].iloc[0])
        self.stock_codes.append(stock_code)
        result = stock_data.copy(deep=True)
        result["FinalScore"] = self.scores.get(stock_code, 80)
        return result


class _ReasonEngine:
    def generate_reasons(
        self, latest_row: pd.Series, config: dict[str, object]
    ) -> list[str]:
        return ["synthetic-reason"]

    def format_reason_text(
        self, reasons: list[str], max_reasons: int = 3
    ) -> str:
        return "|".join(reasons[:max_reasons])


class _EvaluatorTrace:
    def __init__(self) -> None:
        self.facts: list[ReplayCandidateHistoryFacts] = []
        self.steps: list[ReplayCandidatePrefilterStep] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        original_start = RecommendationEvaluator.start_replay_prefilter
        original_advance = RecommendationEvaluator.advance_replay_prefilter

        def start(
            evaluator: RecommendationEvaluator,
            facts: ReplayCandidateHistoryFacts,
            policy: object,
        ) -> ReplayCandidatePrefilterStep:
            self.facts.append(facts)
            step = original_start(evaluator, facts, policy)  # type: ignore[arg-type]
            self.steps.append(step)
            return step

        def advance(
            evaluator: RecommendationEvaluator,
            state: object,
            response: object,
        ) -> ReplayCandidatePrefilterStep:
            step = original_advance(  # type: ignore[arg-type]
                evaluator, state, response
            )
            self.steps.append(step)
            return step

        monkeypatch.setattr(RecommendationEvaluator, "start_replay_prefilter", start)
        monkeypatch.setattr(
            RecommendationEvaluator, "advance_replay_prefilter", advance
        )


def _history(stock_codes: tuple[str, ...], *, rows: int = 21) -> pd.DataFrame:
    dates = pd.date_range("2026-08-01", periods=rows, freq="D")
    close_prices = [100] * rows
    close_prices[-1] = 101
    volumes = [100] * rows
    if rows >= 21:
        volumes[-1] = 110
    return pd.DataFrame(
        [
            {
                "日期": int(current_date.strftime("%Y%m%d")),
                "證券代號": stock_code,
                "證券名稱": f"synthetic-{stock_code}",
                "收盤價": close_prices[index],
                "成交股數": volumes[index],
                "available_date": int(current_date.strftime("%Y%m%d")),
            }
            for stock_code in stock_codes
            for index, current_date in enumerate(dates)
        ]
    )


def _provider(*, scores: dict[str, int] | None = None) -> tuple[
    RecommendationDataFrameProvider, _Scorer
]:
    provider = RecommendationDataFrameProvider()
    scorer = _Scorer(scores)
    provider.strategy_configurator = scorer
    provider.reason_engine = _ReasonEngine()
    return provider, scorer


@pytest.mark.parametrize("blank_code", ["", "   "])
@pytest.mark.parametrize(
    ("filter_name", "threshold", "accepted", "expected_conversion"),
    [
        ("price_change_min", 2.0, False, "price_change_min"),
        ("price_change_min", 0.5, True, "price_change_min"),
        ("price_change_max", 0.5, False, "price_change_max"),
        ("price_change_max", 2.0, True, "price_change_max"),
        ("volume_ratio_min", 1.2, False, "volume_ratio_min"),
        ("volume_ratio_min", 1.05, True, "volume_ratio_min"),
    ],
)
def test_blank_active_filter_uses_call_local_evaluator_without_canonical_identity(
    monkeypatch: pytest.MonkeyPatch,
    blank_code: str,
    filter_name: str,
    threshold: float,
    accepted: bool,
    expected_conversion: str,
) -> None:
    trace = _EvaluatorTrace()
    trace.install(monkeypatch)
    provider, scorer = _provider()
    conversions: list[str] = []
    provider_result = provider.run_with_as_of_handoff(
        _history((blank_code,)),
        {"filters": {filter_name: _ProbeThreshold(filter_name, conversions, threshold)}},
        top_n=5,
        as_of_date=date(2026, 8, 21),
    )

    assert len(trace.facts) == 1
    facts = trace.facts[0]
    assert facts.observations.stock_code == blank_code
    candidate_key = getattr(facts.observations, "compatibility_candidate_key", None)
    assert candidate_key is not None
    assert type(candidate_key).__name__ == "ReplayCompatibilityCandidateKeyV1"
    assert candidate_key.invocation_id == facts.invocation_id
    assert not isinstance(candidate_key, str)
    assert conversions == [expected_conversion]

    if accepted:
        assert provider_result.rows == [
            {
                "stock_code": blank_code,
                "stock_name": f"synthetic-{blank_code}",
                "total_score": 80.0,
                "factor_scores": {
                    "technical": 0.0,
                    "pattern": 0.0,
                    "volume": 0.0,
                    "broker_flow": 0.0,
                    "revenue": 0.0,
                },
                "selection_reason": "synthetic-reason",
            }
        ]
        assert scorer.stock_codes == [blank_code]
        assert provider_result.scoring_outcomes == (None,)
        assert any(
            type(step.request) is NeedCompatibilityScoring
            for step in trace.steps
        )
    else:
        assert provider_result.rows == []
        assert scorer.stock_codes == []
        assert provider_result.scoring_outcomes == ()
        terminal = trace.steps[-1].outcome
        assert terminal is not None
        assert type(terminal).__name__ == "ReplayCompatibilityPrefilterOutcomeV1"
        assert not hasattr(terminal, "assessment")


def test_blank_compatibility_contract_does_not_relax_canonical_identity() -> None:
    key = ReplayCompatibilityCandidateKeyV1("invocation-a", "candidate-a")
    with pytest.raises(ValueError, match="stock_code 不可為空"):
        ReplayPrefilterObservations(
            stock_code="",
            as_of_date=date(2026, 8, 21),
            history_rows=20,
            maximum_row_date=date(2026, 8, 21),
            availability_column_present=False,
            maximum_available_date=None,
        )

    observations = ReplayCompatibilityPrefilterObservationsV1(
        stock_code="",
        as_of_date=date(2026, 8, 21),
        history_rows=20,
        maximum_row_date=date(2026, 8, 21),
        availability_column_present=False,
        maximum_available_date=None,
        compatibility_candidate_key=key,
    )
    with pytest.raises(ValueError, match="綁定 facts invocation"):
        ReplayCandidateHistoryFacts("invocation-b", observations)

    step = RecommendationEvaluator().start_replay_prefilter(
        ReplayCandidateHistoryFacts("invocation-a", observations),
        ReplayFastFilterPolicyV1(),
    )
    assert type(step.request) is NeedCompatibilityScoring
    assert step.request.compatibility_candidate_key == key
    assert step.state.outcome is None


def test_blank_active_filters_keep_legacy_lazy_conversion_and_exception_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace = _EvaluatorTrace()
    trace.install(monkeypatch)
    provider, scorer = _provider()
    conversions: list[str] = []
    config = {
        "filters": {
            "price_change_min": _ProbeThreshold("min", conversions, 2.0),
            "price_change_max": _ProbeThreshold(
                "max", conversions, 0.0, fail=True
            ),
            "volume_ratio_min": _ProbeThreshold(
                "volume", conversions, 1.2, fail=True
            ),
        }
    }

    rows = provider(_history(("   ",)), config, top_n=5)

    assert rows == []
    assert conversions == ["min"]
    assert scorer.stock_codes == []
    assert len(trace.facts) == 1
    assert trace.steps[-1].outcome is not None

    failing_conversions: list[str] = []
    failure_trace = _EvaluatorTrace()
    failure_trace.install(monkeypatch)
    failing_provider, failing_scorer = _provider()
    with pytest.raises(ValueError, match="synthetic threshold failure: min"):
        failing_provider(
            _history(("",)),
            {
                "filters": {
                    "price_change_min": _ProbeThreshold(
                        "min", failing_conversions, 0.5, fail=True
                    ),
                    "price_change_max": 2.0,
                    "volume_ratio_min": 1.2,
                }
            },
            top_n=5,
        )

    assert failing_conversions == ["min"]
    assert failing_scorer.stock_codes == []
    assert len(failure_trace.facts) == 1


def test_blank_and_valid_candidates_keep_v1_order_top_n_and_child_boundary() -> None:
    provider, _ = _provider(scores={"": 90, "VALID": 80})
    service = RecommendationReplayService(provider)
    history = _history(("", "VALID"))
    config = {"filters": {"price_change_min": 0.5}}

    both = service.run_snapshot(
        as_of_date="2026-08-21",
        profile_id="blank-mixed",
        config=config,
        history=history,
        universe=None,
        top_n=2,
    )
    assert [row["stock_code"] for row in both.recommendations] == ["", "VALID"]
    assert both.canonical_execution is None
    assert not hasattr(both, "compatibility_scoring_outcomes")
    assert not hasattr(both, "compatibility_candidate_key")

    valid_only_provider, _ = _provider(scores={"": 70, "VALID": 80})
    valid_only = RecommendationReplayService(valid_only_provider).run_snapshot(
        as_of_date="2026-08-21",
        profile_id="blank-top-one",
        config=config,
        history=history,
        universe=None,
        top_n=1,
    )
    assert [row["stock_code"] for row in valid_only.recommendations] == ["VALID"]
    assert valid_only.canonical_execution is not None


def test_blank_filter_cutoff_is_applied_before_evaluator_and_scorer() -> None:
    provider, scorer = _provider()
    history = _history(("",))
    history.loc[history.index[-2], "收盤價"] = 101
    history.loc[history.index[-1], "收盤價"] = 500
    snapshot = RecommendationReplayService(provider).run_snapshot(
        as_of_date="2026-08-20",
        profile_id="blank-cutoff",
        config={"filters": {"price_change_min": 0.5}},
        history=history,
        universe=None,
        top_n=5,
    )

    assert [row["stock_code"] for row in snapshot.recommendations] == [""]
    assert len(scorer.inputs) == 1
    assert len(scorer.inputs[0]) == 20
    assert scorer.inputs[0]["日期"].max() == pd.Timestamp("2026-08-20")
    assert snapshot.canonical_execution is None


def test_distinct_blank_groups_receive_distinct_call_local_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace = _EvaluatorTrace()
    trace.install(monkeypatch)
    provider, scorer = _provider(scores={"": 90, " ": 80})
    result = provider.run_with_as_of_handoff(
        _history(("", " ")),
        {"filters": {"price_change_min": 0.5}},
        top_n=5,
        as_of_date=date(2026, 8, 21),
    )

    assert [row["stock_code"] for row in result.rows] == ["", " "]
    assert scorer.stock_codes == ["", " "]
    assert len(trace.facts) == 2
    keys = [fact.observations.compatibility_candidate_key for fact in trace.facts]
    assert keys[0] != keys[1]
    assert keys[0].invocation_id == keys[1].invocation_id
    assert result.scoring_outcomes == (None, None)


class _TerminalModeScorer(_Scorer):
    def __init__(self, blank_mode: str) -> None:
        super().__init__({"": 90, "VALID": 80})
        self.blank_mode = blank_mode

    def generate_recommendations(
        self, stock_data: pd.DataFrame, config: dict[str, object]
    ) -> pd.DataFrame:
        stock_code = str(stock_data["證券代號"].iloc[0])
        self.stock_codes.append(stock_code)
        if stock_code == "" and self.blank_mode == "exception":
            raise ValueError("synthetic blank scorer failure")
        if stock_code == "" and self.blank_mode == "empty":
            return pd.DataFrame()
        result = stock_data.copy(deep=True)
        if stock_code == "" and self.blank_mode == "projection_exception":
            result["FinalScore"] = _BadFinalScore()
        else:
            result["FinalScore"] = self.scores.get(stock_code, 80)
        return result


class _BadFinalScore:
    def __float__(self) -> float:
        raise ValueError("synthetic compatibility projection failure")


@pytest.mark.parametrize(
    ("mode", "expected_name"),
    [
        ("success", "SCORED"),
        ("empty", "SKIPPED_EMPTY"),
        ("exception", "SKIPPED_SCORER_EXCEPTION"),
        ("projection_exception", "SKIPPED_PROJECTION_EXCEPTION"),
    ],
)
def test_blank_compatibility_scorer_completes_all_terminal_paths_without_canonical_slot(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    expected_name: str,
) -> None:
    import decision_module.recommendation.evaluate as replay_evaluate

    response_type = getattr(
        replay_evaluate, "ReplayCompatibilityScorerResponseV1", None
    )
    outcome_type = getattr(
        replay_evaluate, "ReplayCompatibilityScoringOutcomeV1", None
    )
    disposition_type = getattr(
        replay_evaluate, "ReplayCompatibilityScorerDispositionV1", None
    )
    complete = getattr(RecommendationEvaluator, "complete_compatibility_scoring", None)
    assert response_type is not None
    assert outcome_type is not None
    assert disposition_type is not None
    assert complete is not None

    compatibility_completions: list[object] = []
    original_complete = RecommendationEvaluator.complete_compatibility_scoring

    def trace_complete(
        evaluator: RecommendationEvaluator,
        prefilter_step: ReplayCandidatePrefilterStep,
        response: object,
    ) -> object:
        terminal_step = original_complete(evaluator, prefilter_step, response)
        compatibility_completions.append(terminal_step)
        return terminal_step

    monkeypatch.setattr(
        RecommendationEvaluator,
        "complete_compatibility_scoring",
        trace_complete,
    )
    provider, _ = _provider()
    scorer = _TerminalModeScorer(mode)
    provider.strategy_configurator = scorer
    result = provider.run_with_as_of_handoff(
        _history(("", "VALID")),
        {"filters": {"price_change_min": 0.5}},
        top_n=5,
        as_of_date=date(2026, 8, 21),
    )

    assert len(compatibility_completions) == 1
    terminal_step = compatibility_completions[0]
    assert type(terminal_step).__name__ == "ReplayCandidatePrefilterStep"
    assert terminal_step.request is None
    assert terminal_step.state.phase.value == "complete"
    assert terminal_step.state.scoring_request is None
    terminal = terminal_step.outcome
    assert type(terminal) is outcome_type
    assert type(terminal.response) is response_type
    assert terminal.response.disposition is getattr(disposition_type, expected_name)
    assert terminal.response.request.stock_code == ""
    assert terminal.response.request.as_of_date == date(2026, 8, 21)
    assert (
        terminal.response.request.compatibility_candidate_key.invocation_id
        == terminal.response.request.invocation_id
    )
    assert not hasattr(terminal, "assessment")
    assert not hasattr(terminal, "item")
    assert not hasattr(terminal, "score_ordering")
    assert [field.name for field in fields(terminal.response)] == [
        "request",
        "disposition",
        "error_type",
    ]
    assert [field.name for field in fields(terminal)] == ["response"]
    assert terminal.response.error_type == (
        "ValueError"
        if mode in {"exception", "projection_exception"}
        else None
    )

    if mode == "success":
        assert [row["stock_code"] for row in result.rows] == ["", "VALID"]
        assert result.scoring_outcomes[0] is None
        assert result.scoring_outcomes[1] is not None
    else:
        assert [row["stock_code"] for row in result.rows] == ["VALID"]
        assert len(result.scoring_outcomes) == 1
        assert result.scoring_outcomes[0] is not None
    assert scorer.stock_codes == ["", "VALID"]
    assert result.compatibility_scoring_outcomes == (terminal,)


def test_blank_compatibility_scoring_completion_rejects_cross_candidate_response() -> None:
    import decision_module.recommendation.evaluate as replay_evaluate

    response_type = getattr(
        replay_evaluate, "ReplayCompatibilityScorerResponseV1", None
    )
    disposition_type = getattr(
        replay_evaluate, "ReplayCompatibilityScorerDispositionV1", None
    )
    complete = getattr(RecommendationEvaluator, "complete_compatibility_scoring", None)
    assert response_type is not None
    assert disposition_type is not None
    assert complete is not None

    def ready_step(candidate_id: str) -> ReplayCandidatePrefilterStep:
        key = ReplayCompatibilityCandidateKeyV1("invocation-a", candidate_id)
        observations = ReplayCompatibilityPrefilterObservationsV1(
            stock_code="",
            as_of_date=date(2026, 8, 21),
            history_rows=21,
            maximum_row_date=date(2026, 8, 21),
            availability_column_present=False,
            maximum_available_date=None,
            compatibility_candidate_key=key,
        )
        return RecommendationEvaluator().start_replay_prefilter(
            ReplayCandidateHistoryFacts("invocation-a", observations),
            ReplayFastFilterPolicyV1(),
        )

    step_a = ready_step("candidate-a")
    step_b = ready_step("candidate-b")
    assert isinstance(step_a.request, NeedCompatibilityScoring)
    assert isinstance(step_b.request, NeedCompatibilityScoring)
    response_from_b = response_type(
        request=step_b.request,
        disposition=disposition_type.SCORED,
    )
    with pytest.raises(ValueError, match="不屬於目前 invocation/candidate/cutoff request"):
        complete(RecommendationEvaluator(), step_a, response_from_b)
