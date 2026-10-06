"""R019 staged evaluator contracts and numeric-boundary characterization."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from app_module.recommendation_service import RecommendationService
from app_module.recommendation.score_projection import (
    project_legacy_recommendation_score,
)
from app_module.recommendation_ranking_pipeline import build_ranking_plan
from app_module.recommendation.evaluation_driver import evaluate_candidate_staged
from app_module.recommendation.source_fact_projection import (
    project_current_monthly_revenue_records,
    project_current_pe_observation,
    project_monthly_revenue_records,
    project_pe_observation,
)
from decision_module.recommendation.contracts import (
    CandidateAssessment,
    DecisionBatch,
    RecommendationItem,
)
from decision_module.recommendation.evaluate import (
    CandidateCurrentMarketStatusFact,
    CandidatePrefilterFact,
    CandidateEvaluationOutcome,
    CandidateSeed,
    CandidateStage,
    DecisionUniverseTooSmallError,
    IndustryContextFact,
    MonthlyRevenueFact,
    MonthlyRevenueFacts,
    NeedSourceFact,
    PEFact,
    RecommendationEvaluationPolicy,
    RecommendationEvaluationResult,
    RecommendationEvaluator,
    RecommendationScore,
    SourceFactError,
    SourceFactKind,
    SourceFactMismatchError,
    SourceFactResponse,
    StrategyEvaluationError,
)
from data_module.fundamental_data import MonthlyRevenueRecord
from data_module.recommendation_current_fundamental_provider import (
    CurrentObservedMonthlyRevenueInput,
    CurrentObservedPEInput,
)
from data_module.recommendation_input_providers import ValuationPEObservation
from data_module.config import TWStockConfig
from recommendation_test_support import build_recommendation_test_preparer


CUTOFF = date(2026, 5, 20)


def _policy(
    invocation_id: str = "r019-test-1",
    *,
    pe_max: Decimal | None = None,
    revenue_min: Decimal | None = None,
    industry: bool = False,
    threshold_mode: str = "fixed",
    top_n: int = 50,
    minimum_bp: int | None = None,
    minimum_size: int | None = None,
) -> RecommendationEvaluationPolicy:
    return RecommendationEvaluationPolicy(
        invocation_id=invocation_id,
        decision_date=CUTOFF,
        decision_date_text=CUTOFF.isoformat(),
        pe_ratio_max=pe_max,
        monthly_revenue_yoy_min=revenue_min,
        industry_context_required=industry,
        threshold_mode=threshold_mode,
        top_n=top_n,
        minimum_percentile_bp=minimum_bp,
        minimum_universe_size=minimum_size,
        ranking_method="nearest_rank" if threshold_mode == "quantile" else "fixed",
        eligible_universe_date=CUTOFF,
    )


def _seed(
    code: str = "2330",
    *,
    invocation_id: str = "r019-test-1",
    score: RecommendationScore | None = None,
    history_rows: int = 20,
    strategy_result_present: bool = True,
    strategy_error: StrategyEvaluationError | None = None,
) -> CandidateSeed:
    item = (
        RecommendationItem(
            stock_code=code,
            stock_name=f"{code}_NAME",
            rule_score=Decimal("70.0100"),
        )
        if score is not None
        else None
    )
    return CandidateSeed(
        invocation_id=invocation_id,
        stock_code=code,
        stock_name=f"{code}_NAME",
        history_rows=history_rows,
        strategy_result_present=strategy_result_present,
        strategy_error=strategy_error,
        item=item,
        score=score,
    )


def _response(request: NeedSourceFact, value: object) -> SourceFactResponse:
    return SourceFactResponse(request=request, value=value)  # type: ignore[arg-type]


def _rankable_outcome(
    code: str,
    raw_score: object,
    *,
    invocation_id: str = "r019-rank",
) -> CandidateEvaluationOutcome:
    projection = project_legacy_recommendation_score(raw_score)
    return CandidateEvaluationOutcome(
        invocation_id=invocation_id,
        stock_code=code,
        status="fail",
        quality="observed",
        stage="candidate_scored",
        reason_codes=("pending_final_selection",),
        item=RecommendationItem(
            stock_code=code,
            stock_name=f"{code}_NAME",
            rule_score=Decimal("1"),
        ),
        assessment=CandidateAssessment(stock_code=code, eligible=True),
        score=projection.score,
    )


def _ranking_evidence(batch_code: str, batch: object) -> object:
    decision_batch = batch
    assessment = next(
        item for item in decision_batch.assessments if item.stock_code == batch_code
    )
    return assessment.filter_outcomes["recommendation_ranking"].evidence


def test_state_and_response_are_frozen_and_fact_requests_are_invocation_bound() -> None:
    evaluator = RecommendationEvaluator()
    first = evaluator.start(
        _seed("2330", invocation_id="run-a"),
        _policy("run-a", pe_max=Decimal("15")),
    )
    second = evaluator.start(
        _seed("2330", invocation_id="run-b"),
        _policy("run-b", pe_max=Decimal("15")),
    )
    same_run_other_stock = evaluator.start(
        _seed("2317", invocation_id="run-a"),
        _policy("run-a", pe_max=Decimal("15")),
    )
    assert first.request is not None and second.request is not None
    assert same_run_other_stock.request is not None
    assert first.request.kind is SourceFactKind.PE
    assert first.request.stock_code == "2330"
    assert first.request.decision_date == CUTOFF
    assert first.request.request_id != second.request.request_id
    assert first.request.request_id != same_run_other_stock.request.request_id
    with pytest.raises(FrozenInstanceError):
        first.request.stock_code = "9999"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        first.state.stage = CandidateStage.COMPLETE  # type: ignore[misc]
    with pytest.raises(SourceFactMismatchError):
        evaluator.advance(
            second.state,
            _response(first.request, PEFact(Decimal("12"), CUTOFF)),
        )
    with pytest.raises(SourceFactMismatchError):
        evaluator.advance(
            same_run_other_stock.state,
            _response(first.request, PEFact(Decimal("12"), CUTOFF)),
        )
    with pytest.raises(SourceFactMismatchError):
        evaluator.advance(first.state, None)


def test_candidate_and_batch_contracts_reject_cross_stock_identity() -> None:
    score = RecommendationScore(Decimal("70"), 7000)
    with pytest.raises(ValueError, match="CandidateSeed item.stock_code"):
        CandidateSeed(
            invocation_id="identity-run",
            stock_code="A",
            stock_name="A name",
            history_rows=20,
            strategy_result_present=True,
            item=RecommendationItem(stock_code="B", rule_score=Decimal("70")),
            score=score,
        )

    with pytest.raises(ValueError, match="Outcome item.stock_code"):
        CandidateEvaluationOutcome(
            invocation_id="identity-run",
            stock_code="A",
            status="fail",
            quality="observed",
            stage="candidate_scored",
            reason_codes=("pending_final_selection",),
            item=RecommendationItem(stock_code="B", rule_score=Decimal("70")),
            assessment=CandidateAssessment(stock_code="A", eligible=True),
            score=score,
        )

    evaluator = RecommendationEvaluator()
    policy = _policy("identity-run")
    first = evaluator.evaluate_batch_result(
        (_rankable_outcome("A", Decimal("70"), invocation_id="identity-run"),),
        policy,
    )
    other = evaluator.evaluate_batch_result(
        (_rankable_outcome("B", Decimal("70"), invocation_id="identity-run"),),
        policy,
    )
    with pytest.raises(ValueError, match="依序對應 dispositions"):
        RecommendationEvaluationResult(
            decision=first.decision,
            dispositions=other.dispositions,
        )


def test_evaluation_result_rejects_item_for_unscored_failed_disposition() -> None:
    evaluator = RecommendationEvaluator()
    policy = _policy("identity-failed-item")
    outcome = CandidateEvaluationOutcome(
        invocation_id="identity-failed-item",
        stock_code="A",
        status="fail",
        quality="observed",
        stage="candidate_filter",
        reason_codes=("rejected_before_scoring",),
        assessment=CandidateAssessment(stock_code="A", eligible=False),
    )
    evaluated = evaluator.evaluate_batch_result((outcome,), policy)
    assert evaluated.decision.items == ()
    assert evaluated.dispositions[0].status == "fail"
    assert evaluated.dispositions[0].scored is False

    forged_batch = DecisionBatch(
        items=(RecommendationItem(stock_code="A", rule_score=Decimal("70")),),
        assessments=evaluated.decision.assessments,
    )
    with pytest.raises(ValueError, match="pass/scored/eligible"):
        RecommendationEvaluationResult(
            decision=forged_batch,
            dispositions=evaluated.dispositions,
        )


def test_pe_gate_is_lazy_and_prevents_monthly_revenue_read_when_rejected() -> None:
    evaluator = RecommendationEvaluator()
    step = evaluator.start(
        _seed(),
        _policy(pe_max=Decimal("15"), revenue_min=Decimal("5")),
    )
    assert step.request is not None
    assert step.request.kind is SourceFactKind.PE

    rejected = evaluator.advance(
        step.state,
        _response(step.request, PEFact(Decimal("20"), CUTOFF)),
    )
    assert rejected.request is None
    assert rejected.outcome is not None
    assert rejected.outcome.reason_codes == ("valuation_pe_above_max",)
    assert rejected.state.stage is CandidateStage.COMPLETE


@pytest.mark.parametrize(
    ("history_rows", "strategy_result_present", "expected_reason"),
    [
        (19, True, "insufficient_history"),
        (20, False, "strategy_filter_no_signal"),
    ],
)
def test_pre_candidate_early_exit_does_not_request_fundamental_facts(
    history_rows: int,
    strategy_result_present: bool,
    expected_reason: str,
) -> None:
    step = RecommendationEvaluator().start(
        _seed(
            history_rows=history_rows,
            strategy_result_present=strategy_result_present,
        ),
        _policy(pe_max=Decimal("15"), revenue_min=Decimal("5")),
    )
    assert step.request is None
    assert step.outcome is not None
    assert step.outcome.reason_codes == (expected_reason,)


def test_strategy_exception_is_typed_degraded_outcome_and_batch_continues() -> None:
    evaluator = RecommendationEvaluator()
    policy = _policy("r019-partial")
    pass_step = evaluator.start(
        _seed(
            "PASS",
            invocation_id="r019-partial",
            score=RecommendationScore(Decimal("80"), 8000),
        ),
        policy,
    )
    no_signal_step = evaluator.start(
        _seed(
            "NO_SIGNAL",
            invocation_id="r019-partial",
            strategy_result_present=False,
        ),
        policy,
    )
    broken_step = evaluator.start(
        _seed(
            "BROKEN",
            invocation_id="r019-partial",
            strategy_result_present=False,
            strategy_error=StrategyEvaluationError(
                "RuntimeError", "fixture source failure"
            ),
        ),
        policy,
    )
    short_step = evaluator.start(
        _seed("SHORT", invocation_id="r019-partial", history_rows=19),
        policy,
    )

    assert pass_step.outcome is not None
    assert no_signal_step.outcome is not None
    assert broken_step.outcome is not None
    assert short_step.outcome is not None
    assert broken_step.outcome.status == "degraded"
    assert broken_step.outcome.quality == "degraded"
    assert broken_step.outcome.reason_codes == ("screening_exception",)
    assert broken_step.outcome.threshold_name == "RuntimeError"
    assert broken_step.outcome.observed_value == "fixture source failure"
    assert broken_step.outcome.required_value == "successful_evaluation"
    assert broken_step.outcome.warnings == ("screening_exception:RuntimeError",)

    batch = evaluator.evaluate_batch(
        (
            pass_step.outcome,
            no_signal_step.outcome,
            broken_step.outcome,
            short_step.outcome,
        ),
        policy,
    )
    assert [item.stock_code for item in batch.items] == ["PASS"]
    assert [assessment.stock_code for assessment in batch.assessments] == [
        "PASS",
        "NO_SIGNAL",
        "BROKEN",
        "SHORT",
    ]


def test_valid_pe_requests_monthly_revenue_and_excludes_future_revisions() -> None:
    evaluator = RecommendationEvaluator()
    step = evaluator.start(
        _seed(score=RecommendationScore(Decimal("70.0100"), 7001)),
        _policy(pe_max=Decimal("15"), revenue_min=Decimal("10")),
    )
    assert step.request is not None
    pe_step = evaluator.advance(
        step.state,
        _response(step.request, PEFact(Decimal("12.00"), date(2026, 5, 19))),
    )
    assert pe_step.request is not None
    assert pe_step.request.kind is SourceFactKind.MONTHLY_REVENUE
    revenue = MonthlyRevenueFacts(
        records=(
            MonthlyRevenueFact(
                "2025-04", date(2025, 5, 18), "v1", Decimal("100")
            ),
            MonthlyRevenueFact(
                "2026-04", date(2026, 5, 19), "v1", Decimal("110")
            ),
            MonthlyRevenueFact(
                "2026-04", date(2026, 5, 21), "v2", Decimal("1000")
            ),
            MonthlyRevenueFact(
                "2026-05", date(2026, 6, 1), "v1", Decimal("2000")
            ),
        )
    )
    completed = evaluator.advance(
        pe_step.state,
        _response(pe_step.request, revenue),
    )
    assert completed.request is None
    assert completed.outcome is not None
    assert completed.outcome.reason_codes == ("pending_final_selection",)
    assert completed.outcome.item is not None


def test_future_pe_and_missing_source_errors_map_to_missing_without_fallback_reads() -> None:
    evaluator = RecommendationEvaluator()
    step = evaluator.start(
        _seed(),
        _policy(pe_max=Decimal("15"), revenue_min=Decimal("0")),
    )
    assert step.request is not None
    future_pe = evaluator.advance(
        step.state,
        _response(step.request, PEFact(Decimal("12"), date(2026, 5, 21))),
    )
    assert future_pe.request is None
    assert future_pe.outcome is not None
    assert future_pe.outcome.reason_codes == ("valuation_pe_missing",)

    error_step = evaluator.start(
        _seed(invocation_id="run-error"),
        _policy("run-error", pe_max=Decimal("15")),
    )
    assert error_step.request is not None
    errored = evaluator.advance(
        error_step.state,
        SourceFactResponse(
            request=error_step.request,
            error=SourceFactError("ReaderUnavailable", "temporary"),
        ),
    )
    assert errored.outcome is not None
    assert errored.outcome.reason_codes == ("valuation_pe_missing",)
    assert errored.outcome.warnings == ()
    assert errored.outcome.source_responses[0].error is not None
    assert errored.outcome.source_responses[0].error.error_type == "ReaderUnavailable"


def test_natural_current_pe_requires_matching_capture_and_frozen_clock() -> None:
    frozen = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    policy = replace(
        _policy(pe_max=Decimal("15")),
        fundamental_input_scope="natural_current_observation",
        current_observation_cutoff_at=frozen,
    )
    source_observation = CurrentObservedPEInput(
        stock_code="2330",
        value=Decimal("12.00"),
        as_of_date=CUTOFF,
        available_at=frozen.replace(hour=11, minute=59),
        source="twse.openapi.bwibbu_all",
        source_version="capture-v1",
        market="twse",
        raw_response_sha256="a" * 64,
        market_calendar_session_date=CUTOFF,
        market_calendar_reason_code="twstock_db_market_indices_evidence",
    )
    projected = project_current_pe_observation(source_observation)
    assert projected.formal_pit_eligible is False
    assert projected.availability_basis == "official_body_capture"
    assert projected.raw_response_sha256 == "a" * 64
    assert projected.as_of_date == CUTOFF
    assert projected.available_date == source_observation.available_at.astimezone(
        ZoneInfo("Asia/Taipei")
    ).date()

    evaluator = RecommendationEvaluator()
    step = evaluator.start(
        _seed(score=RecommendationScore(Decimal("70.01"))),
        policy,
    )
    assert step.request is not None
    assert step.request.fundamental_input_scope == "natural_current_observation"
    assert step.request.current_observation_cutoff_at == frozen
    passed = evaluator.advance(step.state, _response(step.request, projected))
    assert passed.outcome is not None
    assert passed.outcome.reason_codes == ("pending_final_selection",)
    stale = PEFact(
        value=Decimal("12.00"),
        available_date=CUTOFF,
        as_of_date=CUTOFF,
        source="twse.openapi.bwibbu_all",
        source_version="capture-v1",
        stock_code="2330",
        available_at=frozen.replace(hour=12, minute=0, second=1),
        availability_basis="official_body_capture",
        raw_response_sha256="a" * 64,
        formal_pit_eligible=False,
    )
    late_step = evaluator.start(
        _seed(invocation_id="late-current", score=RecommendationScore(Decimal("70.01"))),
        replace(policy, invocation_id="late-current"),
    )
    assert late_step.request is not None
    late = evaluator.advance(late_step.state, _response(late_step.request, stale))
    assert late.outcome is not None
    assert late.outcome.reason_codes == ("valuation_pe_missing",)


def test_current_pe_projection_keeps_quote_date_separate_from_capture_date() -> None:
    quote_date = date(2026, 5, 19)
    captured_at = datetime(2026, 5, 20, 16, 30, tzinfo=timezone.utc)
    observation = CurrentObservedPEInput(
        stock_code="2330",
        value=Decimal("12"),
        as_of_date=quote_date,
        available_at=captured_at,
        source="twse.openapi.bwibbu_all",
        source_version="capture-v1",
        market="twse",
        raw_response_sha256="a" * 64,
        market_calendar_session_date=quote_date,
        market_calendar_reason_code="twstock_db_market_indices_evidence",
    )

    projected = project_current_pe_observation(observation)

    assert projected.as_of_date == quote_date
    assert projected.available_date == date(2026, 5, 21)
    assert projected.available_at == captured_at


def test_natural_current_revenue_yoy_requires_current_period_and_exact_baseline() -> None:
    frozen = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    policy = replace(
        _policy(revenue_min=Decimal("10")),
        fundamental_input_scope="natural_current_observation",
        current_observation_cutoff_at=frozen,
    )
    current = CurrentObservedMonthlyRevenueInput(
        stock_code="2330",
        period="2026-04",
        revenue=Decimal("110"),
        observed_at=frozen.replace(hour=11, minute=59),
        source_available_at=None,
        available_at=frozen.replace(hour=11, minute=59),
        source="mops.monthly_revenue_static_snapshot",
        source_version=(
            "mops-current-revenue-normalizer.v2:twse:2026-04:raw:"
            "mops-static-twse-2026-04-sha256-" + "b" * 64
            + ":derived:sha256:" + "c" * 64
        ),
        market="twse",
        raw_source_version="mops-static-twse-2026-04-sha256-" + "b" * 64,
        raw_source_sha256="b" * 64,
    )
    prior = MonthlyRevenueRecord(
        stock_code="2330",
        period="2025-04",
        as_of_date=date(2025, 4, 30),
        raw_date=date(2025, 4, 30),
        announced_date=date(2025, 5, 10),
        available_date=date(2025, 5, 12),
        revenue=Decimal("100"),
        source="financial_data.monthly_revenue_csv",
        source_version="pit-v1",
    )
    current_comparator = CurrentObservedMonthlyRevenueInput(
        stock_code="2330",
        period="2025-04",
        revenue=Decimal("100"),
        observed_at=current.observed_at,
        source_available_at=None,
        available_at=current.available_at,
        source="mops.monthly_revenue_static_snapshot",
        source_version=(
            "mops-current-revenue-yoy-comparator.v1:twse:2025-04:from:2026-04:raw:"
            "mops-static-twse-2026-04-sha256-" + "b" * 64
            + ":derived:sha256:" + "d" * 64
        ),
        market="twse",
        raw_source_version="mops-static-twse-2026-04-sha256-" + "b" * 64,
        raw_source_sha256="b" * 64,
        input_role="same_report_prior_year_comparison_baseline",
        parent_report_period="2026-04",
    )
    facts = project_current_monthly_revenue_records(
        (current, current_comparator), (prior,), stock_code="2330"
    )
    assert [record.period for record in facts.records] == ["2025-04", "2026-04"]
    assert facts.records[0].availability_basis == "local_verified_observation"
    assert facts.records[0].source_version.startswith(
        "mops-current-revenue-yoy-comparator.v1:"
    )
    assert facts.records[0].formal_pit_eligible is False
    assert facts.records[1].availability_basis == "local_verified_observation"
    assert facts.records[1].source_available_at is None

    evaluator = RecommendationEvaluator()
    step = evaluator.start(
        _seed(score=RecommendationScore(Decimal("70.01"))),
        policy,
    )
    assert step.request is not None
    passed = evaluator.advance(step.state, _response(step.request, facts))
    assert passed.outcome is not None
    assert passed.outcome.reason_codes == ("pending_final_selection",)

    no_baseline = project_current_monthly_revenue_records(
        (
            current,
            CurrentObservedMonthlyRevenueInput(
                stock_code="2330",
                period="2025-04",
                revenue=Decimal("100"),
                observed_at=current.observed_at,
                source_available_at=None,
                available_at=current.available_at,
                source="mops.monthly_revenue_static_snapshot",
                source_version=(
                    "mops-current-revenue-normalizer.v2:twse:2025-04:raw:"
                    "mops-static-twse-2025-04-sha256-" + "a" * 64
                    + ":derived:sha256:" + "e" * 64
                ),
                market="twse",
                raw_source_version="mops-static-twse-2025-04-sha256-" + "a" * 64,
                raw_source_sha256="a" * 64,
            ),
        ),
        (),
        stock_code="2330",
    )
    assert [record.period for record in no_baseline.records] == ["2026-04"]
    assert RecommendationEvaluator._revenue_yoy(
        no_baseline,
        cutoff=CUTOFF,
        stock_code="2330",
        fundamental_input_scope="natural_current_observation",
        current_observation_cutoff_at=frozen,
    ) is None
    stale_reported_prior = replace(
        facts.records[1],
        period="2025-04",
        source_version=(
            "mops-current-revenue-normalizer.v2:twse:2025-04:raw:"
            "mops-static-twse-2025-04-sha256-" + "a" * 64
            + ":derived:sha256:" + "e" * 64
        ),
        revenue=Decimal("100"),
        input_role="reported_period_value",
        parent_report_period=None,
    )
    stale_reported_prior_facts = MonthlyRevenueFacts(
        records=(facts.records[1], stale_reported_prior)
    )
    assert RecommendationEvaluator._revenue_yoy(
        stale_reported_prior_facts,
        cutoff=CUTOFF,
        stock_code="2330",
        fundamental_input_scope="natural_current_observation",
        current_observation_cutoff_at=frozen,
    ) is None
    unqualified_formal_baseline = project_current_monthly_revenue_records(
        (current,), (prior,), stock_code="2330"
    )
    assert [record.period for record in unqualified_formal_baseline.records] == [
        "2026-04"
    ]
    assert RecommendationEvaluator._revenue_yoy(
        unqualified_formal_baseline,
        cutoff=CUTOFF,
        stock_code="2330",
        fundamental_input_scope="natural_current_observation",
        current_observation_cutoff_at=frozen,
    ) is None
    missing_baseline_step = evaluator.advance(
        step.state,
        _response(step.request, no_baseline),
    )
    assert missing_baseline_step.outcome is not None
    assert missing_baseline_step.outcome.reason_codes == (
        "fundamental_revenue_yoy_missing",
    )
    formal_latest_only = MonthlyRevenueFacts(
        records=(
            MonthlyRevenueFact(
                period="2026-04",
                available_date=date(2026, 5, 12),
                source_version="old-current-period",
                revenue=Decimal("90"),
                stock_code="2330",
                availability_basis="formal_pit_available_date",
                formal_pit_eligible=True,
            ),
            facts.records[0],
        )
    )
    assert RecommendationEvaluator._revenue_yoy(
        formal_latest_only,
        cutoff=CUTOFF,
        stock_code="2330",
        fundamental_input_scope="natural_current_observation",
        current_observation_cutoff_at=frozen,
    ) is None


def test_current_observation_facts_are_not_usable_by_historical_policy() -> None:
    current_pe = PEFact(
        value=Decimal("12"),
        available_date=CUTOFF,
        as_of_date=CUTOFF,
        stock_code="2330",
        available_at=datetime(2026, 5, 20, 11, 0, tzinfo=timezone.utc),
        availability_basis="official_body_capture",
        raw_response_sha256="a" * 64,
        formal_pit_eligible=False,
    )
    evaluator = RecommendationEvaluator()
    step = evaluator.start(_seed(), _policy(pe_max=Decimal("15")))
    assert step.request is not None
    result = evaluator.advance(step.state, _response(step.request, current_pe))
    assert result.outcome is not None
    assert result.outcome.reason_codes == ("valuation_pe_missing",)


@pytest.mark.parametrize(
    ("raw_value", "expected_reason"),
    (
        ("-5", "valuation_pe_non_positive"),
        ("0", "valuation_pe_non_positive"),
        ("5", "pending_final_selection"),
        ("Infinity", "valuation_pe_non_finite"),
        ("NaN", "valuation_pe_non_finite"),
    ),
)
@pytest.mark.parametrize("fundamental_scope", ("formal_pit", "natural_current_observation"))
def test_pe_max_requires_positive_finite_value_in_both_scopes(
    raw_value: str,
    expected_reason: str,
    fundamental_scope: str,
) -> None:
    frozen = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    policy = _policy(pe_max=Decimal("15"))
    if fundamental_scope == "natural_current_observation":
        policy = replace(
            policy,
            fundamental_input_scope=fundamental_scope,
            current_observation_cutoff_at=frozen,
        )
    current = fundamental_scope == "natural_current_observation"
    fact = PEFact(
        value=Decimal(raw_value),
        available_date=CUTOFF,
        as_of_date=CUTOFF,
        source="fixture",
        source_version="source-version-v1",
        stock_code="2330" if current else None,
        available_at=frozen if current else None,
        availability_basis="official_body_capture" if current else "formal_pit_available_date",
        raw_response_sha256="a" * 64 if current else None,
        formal_pit_eligible=not current,
    )
    evaluator = RecommendationEvaluator()
    step = evaluator.start(
        _seed(score=RecommendationScore(Decimal("70.01"))),
        policy,
    )
    assert step.request is not None

    result = evaluator.advance(step.state, _response(step.request, fact))

    assert result.outcome is not None
    assert result.outcome.reason_codes == (expected_reason,)
    if expected_reason.startswith("valuation_pe_non_"):
        assert result.outcome.quality == "degraded"
        assert result.outcome.observed_value == raw_value
        assert result.outcome.required_value == "finite PE > 0 and <= 15"
        assert result.outcome.source_responses[0].value == fact
    else:
        assert result.outcome.quality == "observed"



def test_nonfinite_monthly_revenue_keeps_existing_comparison_semantics() -> None:
    evaluator = RecommendationEvaluator()
    revenue_step = evaluator.start(_seed(), _policy(revenue_min=Decimal("0")))
    assert revenue_step.request is not None
    with pytest.raises(InvalidOperation):
        evaluator.advance(
            revenue_step.state,
            _response(
                revenue_step.request,
                MonthlyRevenueFacts(
                    records=(
                        MonthlyRevenueFact(
                            "2025-04",
                            date(2025, 5, 19),
                            "v1",
                            Decimal("100"),
                        ),
                        MonthlyRevenueFact(
                            "2026-04",
                            date(2026, 5, 19),
                            "v1",
                            Decimal("NaN"),
                        ),
                    )
                ),
            ),
        )


def test_future_monthly_revenue_is_ignored_and_reader_error_is_missing() -> None:
    evaluator = RecommendationEvaluator()
    step = evaluator.start(
        _seed(),
        _policy(revenue_min=Decimal("0")),
    )
    assert step.request is not None
    future_only = MonthlyRevenueFacts(
        records=(
            MonthlyRevenueFact(
                "2026-04", date(2026, 5, 21), "v1", Decimal("110")
            ),
            MonthlyRevenueFact(
                "2025-04", date(2025, 5, 19), "v1", Decimal("100")
            ),
        )
    )
    completed = evaluator.advance(
        step.state,
        _response(step.request, future_only),
    )
    assert completed.outcome is not None
    assert completed.outcome.reason_codes == ("fundamental_revenue_yoy_missing",)

    error_step = evaluator.start(
        _seed(invocation_id="run-revenue-error"),
        _policy("run-revenue-error", revenue_min=Decimal("0")),
    )
    assert error_step.request is not None
    errored = evaluator.advance(
        error_step.state,
        SourceFactResponse(
            request=error_step.request,
            error=SourceFactError("ReaderUnavailable", "temporary"),
        ),
    )
    assert errored.outcome is not None
    assert errored.outcome.reason_codes == ("fundamental_revenue_yoy_missing",)
    assert errored.outcome.warnings == ()
    assert errored.outcome.source_responses[0].error is not None
    assert errored.outcome.source_responses[0].error.error_type == "ReaderUnavailable"


def test_app_source_projection_preserves_dates_lineage_and_raw_quality_literals() -> None:
    pe = project_pe_observation(
        ValuationPEObservation(
            value="12.00",
            as_of_date="2026-05-19",
            available_date="2026-05-20",
            source="fixture",
            source_version="v7",
            quality="observed",
        )
    )
    assert pe == PEFact(
        value=Decimal("12.00"),
        available_date=CUTOFF,
        as_of_date=date(2026, 5, 19),
        source="fixture",
        source_version="v7",
        quality_literal="observed",
    )
    monthly = project_monthly_revenue_records(
        (
            MonthlyRevenueRecord(
                stock_code="2330",
                period="2026-04",
                as_of_date=date(2026, 4, 30),
                raw_date=date(2026, 4, 30),
                announced_date=date(2026, 5, 10),
                available_date=date(2026, 5, 11),
                revenue=Decimal("110.00"),
                source="fixture-csv",
                source_version="sha256:abc",
                legacy_quality_wire_value="estimated",
            ),
        )
    )
    assert monthly.records == (
        MonthlyRevenueFact(
            period="2026-04",
            available_date=date(2026, 5, 11),
            source_version="sha256:abc",
            revenue=Decimal("110.00"),
            source="fixture-csv",
            quality_literal="estimated",
            stock_code="2330",
            availability_basis="formal_pit_available_date",
            formal_pit_eligible=True,
        ),
    )


def test_industry_source_error_is_typed_as_degraded_candidate() -> None:
    evaluator = RecommendationEvaluator()
    step = evaluator.start(_seed(), _policy(industry=True))
    assert step.request is not None
    assert step.request.kind is SourceFactKind.INDUSTRY_CONTEXT
    completed = evaluator.advance(
        step.state,
        SourceFactResponse(
            request=step.request,
            error=SourceFactError("MapperFailure", "industry lookup failed"),
        ),
    )
    assert completed.outcome is not None
    assert completed.outcome.status == "degraded"
    assert completed.outcome.reason_codes == ("screening_exception",)
    assert completed.outcome.warnings == ("screening_exception:MapperFailure",)


def test_app_driver_reads_only_requests_returned_by_decision() -> None:
    evaluator = RecommendationEvaluator()
    read_order: list[SourceFactKind] = []

    def pe_rejected_reader(request: NeedSourceFact) -> SourceFactResponse:
        read_order.append(request.kind)
        assert request.kind is SourceFactKind.PE
        return _response(request, PEFact(Decimal("20"), CUTOFF))

    rejected = evaluate_candidate_staged(
        evaluator,
        _seed(),
        _policy(pe_max=Decimal("15"), revenue_min=Decimal("5")),
        pe_rejected_reader,
    )
    assert rejected.reason_codes == ("valuation_pe_above_max",)
    assert read_order == [SourceFactKind.PE]

    read_order.clear()

    def passing_reader(request: NeedSourceFact) -> SourceFactResponse:
        read_order.append(request.kind)
        if request.kind is SourceFactKind.PE:
            return _response(request, PEFact(Decimal("12"), CUTOFF))
        assert request.kind is SourceFactKind.MONTHLY_REVENUE
        return _response(
            request,
            MonthlyRevenueFacts(
                records=(
                    MonthlyRevenueFact(
                        "2025-04", date(2025, 5, 19), "v1", Decimal("100")
                    ),
                    MonthlyRevenueFact(
                        "2026-04", date(2026, 5, 19), "v1", Decimal("110")
                    ),
                )
            ),
        )

    passed = evaluate_candidate_staged(
        evaluator,
        _seed(score=RecommendationScore(Decimal("70.0100"), 7001)),
        _policy(pe_max=Decimal("15"), revenue_min=Decimal("10")),
        passing_reader,
    )
    assert passed.reason_codes == ("pending_final_selection",)
    assert read_order == [
        SourceFactKind.PE,
        SourceFactKind.MONTHLY_REVENUE,
    ]


def test_app_driver_converts_reader_exceptions_to_per_candidate_typed_errors() -> None:
    evaluator = RecommendationEvaluator()
    reads: list[tuple[str, SourceFactKind]] = []

    def broken_reader(request: NeedSourceFact) -> SourceFactResponse:
        reads.append((request.stock_code, request.kind))
        raise RuntimeError(f"cannot read {request.stock_code}")

    first = evaluate_candidate_staged(
        evaluator,
        _seed("A", invocation_id="driver-run-a"),
        _policy("driver-run-a", pe_max=Decimal("15")),
        broken_reader,
    )
    second = evaluate_candidate_staged(
        evaluator,
        _seed("B", invocation_id="driver-run-b"),
        _policy("driver-run-b", pe_max=Decimal("15")),
        broken_reader,
    )
    assert first.reason_codes == second.reason_codes == ("valuation_pe_missing",)
    assert reads == [("A", SourceFactKind.PE), ("B", SourceFactKind.PE)]
    assert first.source_responses[0].request.stock_code == "A"
    assert second.source_responses[0].request.stock_code == "B"
    assert first.source_responses[0].error is not None
    assert second.source_responses[0].error is not None


@pytest.mark.parametrize(
    ("score", "expected_recommendations"),
    [(Decimal("80.00"), 1), (Decimal("NaN"), 0)],
)
def test_staged_industry_request_preserves_mapper_reason_performance_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    score: Decimal,
    expected_recommendations: int,
) -> None:
    config = TWStockConfig(
        data_root=tmp_path / "profile-test-data",
        output_root=tmp_path / "profile-test-output",
        profile="test",
    )
    dates = pd.date_range("2026-05-01", periods=20, freq="D")
    frame = pd.DataFrame(
        [
            {
                "日期": current_date,
                "available_date": current_date,
                "證券代號": "2330",
                "證券名稱": "TSMC",
                "收盤價": Decimal("100.00"),
                "成交股數": 1000,
            }
            for current_date in dates
        ]
    )
    market_data_provider = lambda: frame.copy(deep=True)
    preparer = build_recommendation_test_preparer(
        config,
        market_data_provider=market_data_provider,
    )
    events: list[str] = []
    industry_mapper = MagicMock()
    industry_mapper.get_stock_industries.side_effect = (
        lambda _stock_code: events.append("industry_mapper") or ["半導體"]
    )
    industry_mapper.get_industry_performance.side_effect = (
        lambda _industry, date: events.append("industry_performance")
        or {"漲跌百分比": "1.50%"}
    )
    service = RecommendationService(
        config,
        industry_mapper=industry_mapper,
        market_data_provider=market_data_provider,
        regime_detector=MagicMock(),
        input_preparer=preparer,
    )
    service.reason_engine = MagicMock()
    service.reason_engine.generate_reasons.side_effect = (
        lambda _row, _runtime_config: events.append("reason_engine") or []
    )
    service.reason_engine.format_reason_text.return_value = ""
    service.strategy_configurator.generate_recommendations = (
        lambda _stock_frame, _runtime_config: pd.DataFrame(
            {
                "FinalScore": [score],
                "TotalScore": [score],
                "收盤價": [Decimal("100.00")],
            }
        )
    )

    read_events: list[tuple[str, str, str]] = []
    input_session = preparer.begin(
        config,
        invocation_frozen_at=datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc),
    )

    def read_pe(*, stock_code: str, decision_date: str) -> ValuationPEObservation:
        read_events.append(("pe", stock_code, decision_date))
        return ValuationPEObservation(
            value=Decimal("10"),
            as_of_date=date(2026, 4, 30),
            available_date=date.fromisoformat(decision_date),
            source="synthetic-test",
            source_version="v1",
            quality="observed",
        )

    def read_monthly_revenues(
        *, stock_code: str, decision_date: date
    ) -> tuple[MonthlyRevenueRecord, ...]:
        read_events.append(("monthly_revenue", stock_code, decision_date.isoformat()))
        return (
            MonthlyRevenueRecord(
                stock_code=stock_code,
                period="2025-04",
                as_of_date=date(2025, 4, 30),
                raw_date=date(2025, 5, 10),
                announced_date=date(2025, 5, 10),
                available_date=date(2025, 5, 10),
                revenue=Decimal("100"),
                source="synthetic-test",
                source_version="v1",
            ),
            MonthlyRevenueRecord(
                stock_code=stock_code,
                period="2026-04",
                as_of_date=date(2026, 4, 30),
                raw_date=date(2026, 5, 10),
                announced_date=date(2026, 5, 10),
                available_date=date(2026, 5, 10),
                revenue=Decimal("110"),
                source="synthetic-test",
                source_version="v1",
            ),
        )

    monkeypatch.setattr(input_session, "load_pe", read_pe)
    monkeypatch.setattr(input_session, "load_monthly_revenues", read_monthly_revenues)

    recommendations = service._run_recommendation_body(
        {"filters": {"pe_ratio_max": "15", "monthly_revenue_yoy_min": "0"}},
        result_id="r019-industry-order",
        input_session=input_session,
    )

    assert len(recommendations) == expected_recommendations
    assert read_events == [
        ("pe", "2330", "2026-05-20"),
        ("monthly_revenue", "2330", "2026-05-20"),
    ]
    assert events == [
        "industry_mapper",
        "reason_engine",
        "industry_performance",
    ]
    if expected_recommendations == 0:
        assert service.last_screening_matrix[0]["reason_codes"] == [
            "total_score_missing_or_nonfinite"
        ]


def test_fixed_ranking_matches_mixed_decimal_float_legacy_order_and_stable_ties() -> None:
    raw_values: list[tuple[str, object]] = [
        ("DECIMAL_TIE_B", Decimal("70.0100")),
        ("FLOAT_HIGH", np.float64(91.5)),
        ("DECIMAL_TIE_A", Decimal("70.0100")),
        ("FLOAT_LOW", 30.0),
        ("FLOAT32_NEAR_TIE", np.float32(50.005)),
    ]
    adversarial = [
        ("FLOAT", 50.005),
        ("DECIMAL_EQUAL_TO_FLOAT", Decimal.from_float(50.005)),
        ("DECIMAL_ABOVE", Decimal.from_float(50.005) + Decimal("1E-20")),
        ("DECIMAL_BELOW", Decimal.from_float(50.005) - Decimal("1E-20")),
        ("FLOAT_TIE", 50.005),
    ]
    raw_values.extend(adversarial)
    expected_codes = [
        code
        for code, _ in sorted(raw_values, key=lambda pair: pair[1], reverse=True)
    ]
    outcomes = tuple(
        _rankable_outcome(code, raw_value) for code, raw_value in raw_values
    )
    legacy_plan = build_ranking_plan(
        raw_values,
        mode="fixed",
        top_n=len(raw_values),
        ranking_config={},
        eligible_universe_date=CUTOFF.isoformat(),
    )
    batch = RecommendationEvaluator().evaluate_batch(
        outcomes,
        _policy("r019-rank", top_n=len(outcomes)),
    )
    assert [item.stock_code for item in batch.items] == expected_codes
    assert [item.stock_code for item in batch.items] == list(legacy_plan.ordered_codes)
    float_projection = project_legacy_recommendation_score(np.float64(91.5))
    assert type(float_projection.value) is np.float64
    assert type(float_projection.contract_value) is Decimal
    assert str(float_projection.contract_value) == "91.5"
    decimal_projection = project_legacy_recommendation_score(Decimal("70.0100"))
    assert str(decimal_projection.value) == "70.0100"
    assert decimal_projection.contract_value.as_tuple().exponent == -4


def test_numeric_string_ranking_and_mixed_type_failure_match_legacy_behavior() -> None:
    raw_values: list[tuple[str, object]] = [
        ("SCORE_8", "8"),
        ("SCORE_70", "70"),
        ("SCORE_100", "100"),
    ]
    expected_codes = [
        code
        for code, _ in sorted(raw_values, key=lambda pair: pair[1], reverse=True)
    ]
    legacy_plan = build_ranking_plan(
        raw_values,
        mode="fixed",
        top_n=len(raw_values),
        ranking_config={},
        eligible_universe_date=CUTOFF.isoformat(),
    )
    batch = RecommendationEvaluator().evaluate_batch(
        tuple(
            _rankable_outcome(code, score, invocation_id="r019-string-fixed")
            for code, score in raw_values
        ),
        _policy("r019-string-fixed", top_n=len(raw_values)),
    )
    assert expected_codes == ["SCORE_8", "SCORE_70", "SCORE_100"]
    assert tuple(item.stock_code for item in batch.items) == tuple(expected_codes)
    assert tuple(item.stock_code for item in batch.items) == legacy_plan.ordered_codes
    projected_string = project_legacy_recommendation_score("70.0100")
    assert projected_string.value == "70.0100"
    assert projected_string.score.ordering_value == "70.0100"
    assert projected_string.contract_value == Decimal("70.0100")

    mixed_values: list[tuple[str, object]] = [
        ("STRING", "80"),
        ("DECIMAL", Decimal("70")),
    ]
    with pytest.raises(TypeError):
        build_ranking_plan(
            mixed_values,
            mode="fixed",
            top_n=len(mixed_values),
            ranking_config={},
            eligible_universe_date=CUTOFF.isoformat(),
        )
    with pytest.raises(TypeError):
        RecommendationEvaluator().evaluate_batch(
            tuple(
                _rankable_outcome(code, score, invocation_id="r019-string-mixed")
                for code, score in mixed_values
            ),
            _policy("r019-string-mixed", top_n=len(mixed_values)),
        )


def test_quantile_numeric_strings_preserve_raw_legacy_order_after_bp_population() -> None:
    raw_values: list[tuple[str, object]] = [
        ("SCORE_8", "8"),
        ("SCORE_70", "70"),
        ("SCORE_100", "100"),
    ]
    ranking_config = {
        "recommendation_min_percentile_bp": 0,
        "recommendation_min_universe_size": 3,
        "recommendation_ranking_method": "nearest_rank",
    }
    legacy_plan = build_ranking_plan(
        raw_values,
        mode="quantile",
        top_n=len(raw_values),
        ranking_config=ranking_config,
        eligible_universe_date=CUTOFF.isoformat(),
    )
    batch = RecommendationEvaluator().evaluate_batch(
        tuple(
            _rankable_outcome(code, score, invocation_id="r019-string-quantile")
            for code, score in raw_values
        ),
        _policy(
            "r019-string-quantile",
            threshold_mode="quantile",
            top_n=len(raw_values),
            minimum_bp=0,
            minimum_size=3,
        ),
    )
    assert tuple(item.stock_code for item in batch.items) == ("SCORE_8", "SCORE_70", "SCORE_100")
    assert tuple(item.stock_code for item in batch.items) == legacy_plan.selected_codes
    assert {
        assessment.stock_code: _ranking_evidence(assessment.stock_code, batch)[
            "score_percentile_bp"
        ]
        for assessment in batch.assessments
    } == dict(legacy_plan.percentiles_bp)


def test_legacy_quantile_half_point_rounding_is_done_before_float_projection() -> None:
    raw_values: tuple[object, ...] = (
        Decimal("50.0049"),
        Decimal("50.0050"),
        Decimal("50.0051"),
        50.0049,
        50.005,
        np.float64(50.005),
        np.float32(50.005),
    )
    projections = tuple(project_legacy_recommendation_score(value) for value in raw_values)
    assert [projection.score.quantile_score_bp for projection in projections] == [
        5000,
        5001,
        5001,
        5000,
        5001,
        5001,
        5001,
    ]
    assert str(projections[5].contract_value) == str(Decimal(str(np.float64(50.005))))
    numpy_integer_projection = project_legacy_recommendation_score(np.int64(70))
    assert numpy_integer_projection.runtime_type == "int64"
    assert numpy_integer_projection.value == np.int64(70)
    assert numpy_integer_projection.contract_value == 70
    assert numpy_integer_projection.score.quantile_score_bp == 7000


def test_quantile_population_is_independent_of_top_n_and_outputs_ranked_assessments() -> None:
    codes_and_scores = (
        ("Q50D", Decimal("50.0050")),
        ("Q90", Decimal("90.0000")),
        ("Q20", Decimal("20.0000")),
        ("Q50B", Decimal("50.0050")),
        ("Q50A", Decimal("50.0049")),
        ("Q50C", Decimal("50.0051")),
    )
    outcomes = tuple(
        _rankable_outcome(code, score, invocation_id="r019-quantile")
        for code, score in codes_and_scores
    )
    policy = _policy(
        "r019-quantile",
        threshold_mode="quantile",
        top_n=3,
        minimum_bp=8000,
        minimum_size=6,
    )
    legacy_plan = build_ranking_plan(
        codes_and_scores,
        mode="quantile",
        top_n=3,
        ranking_config={
            "recommendation_min_percentile_bp": 8000,
            "recommendation_min_universe_size": 6,
            "recommendation_ranking_method": "nearest_rank",
        },
        eligible_universe_date=CUTOFF.isoformat(),
    )
    batch = RecommendationEvaluator().evaluate_batch(outcomes, policy)
    assert [item.stock_code for item in batch.items] == ["Q90", "Q50C", "Q50B"]
    assert tuple(item.stock_code for item in batch.items) == legacy_plan.selected_codes
    assert dict(
        (
            assessment.stock_code,
            _ranking_evidence(assessment.stock_code, batch)["score_percentile_bp"],
        )
        for assessment in batch.assessments
    ) == dict(legacy_plan.percentiles_bp)
    assert [
        (item.stock_code, item.score_percentile_bp, item.eligible_universe_size)
        for item in batch.items
    ] == [("Q90", 10_000, 6), ("Q50C", 8_334, 6), ("Q50B", 8_334, 6)]
    assert [assessment.stock_code for assessment in batch.assessments] == [
        code for code, _ in codes_and_scores
    ]
    evidence = _ranking_evidence("Q50D", batch)
    assert evidence["ordered_rank"] == 4
    assert evidence["eligible_universe_size"] == 6
    assert _ranking_evidence("Q50A", batch)["score_percentile_bp"] == 3334
    with pytest.raises(DecisionUniverseTooSmallError):
        RecommendationEvaluator().evaluate_batch(
            outcomes,
            _policy(
                "r019-quantile",
                threshold_mode="quantile",
                top_n=3,
                minimum_bp=8000,
                minimum_size=7,
            ),
        )


def test_typed_prefilter_and_quantile_empty_batch_keep_final_dispositions() -> None:
    evaluator = RecommendationEvaluator()
    fact = CandidatePrefilterFact(
        invocation_id="r019-prefilter",
        stock_code="2330",
        requested_industry="半導體",
        point_in_time_required=True,
        membership_usable=False,
        matching_stock_count=0,
    )
    outcome = evaluator.prefilter_outcome(fact)
    policy = _policy(
        "r019-prefilter",
        threshold_mode="quantile",
        top_n=5,
        minimum_bp=8000,
        minimum_size=6,
    )

    result = evaluator.evaluate_batch_result((outcome,), policy)

    assert result.decision.items == ()
    assert len(result.decision.assessments) == 1
    disposition = result.dispositions[0]
    assert (
        disposition.stock_code,
        disposition.status,
        disposition.quality,
        disposition.stage,
        disposition.reason_codes,
    ) == (
        "2330",
        "missing",
        "missing",
        "universe_gate",
        ("industry_membership_pit_unavailable",),
    )
    assert disposition.assessment == result.decision.assessments[0]

    empty = evaluator.evaluate_batch_result((), policy)
    assert empty.decision.items == ()
    assert empty.decision.assessments == ()
    assert empty.dispositions == ()


def test_verified_current_delisting_is_typed_observed_exclusion() -> None:
    evidence = {
        "schema_version": "current-market-status-preflight.v1",
        "symbol": "4130",
        "scope": "current_only",
        "pit_eligible": False,
        "raw_sha256": "sha256:" + "a" * 64,
    }
    outcome = RecommendationEvaluator.current_market_status_outcome(
        CandidateCurrentMarketStatusFact(
            invocation_id="r019-current-market-status",
            stock_code="4130",
            evidence=evidence,
        )
    )

    result = RecommendationEvaluator().evaluate_batch_result(
        (outcome,), _policy("r019-current-market-status")
    )

    assert result.decision.items == ()
    assert len(result.decision.assessments) == 1
    assessment = result.decision.assessments[0]
    assert assessment.stock_code == "4130"
    assert assessment.eligible is False
    gate = assessment.filter_outcomes["current_market_status_gate"]
    assert gate.passed is False
    assert gate.reason == "official_delisted"
    assert dict(gate.evidence) == evidence
    disposition = result.dispositions[0]
    assert (
        disposition.status,
        disposition.quality,
        disposition.stage,
        disposition.reason_codes,
        disposition.scored,
    ) == (
        "fail",
        "observed",
        "current_market_status_gate",
        ("official_delisted",),
        False,
    )


def test_evaluation_result_exposes_final_ranking_disposition() -> None:
    outcomes = (
        _rankable_outcome("TOP", Decimal("90"), invocation_id="r019-disposition"),
        _rankable_outcome("OUT", Decimal("80"), invocation_id="r019-disposition"),
    )
    result = RecommendationEvaluator().evaluate_batch_result(
        outcomes,
        _policy("r019-disposition", top_n=1),
    )

    assert [item.stock_code for item in result.decision.items] == ["TOP"]
    assert [
        (item.stock_code, item.status, item.stage, item.reason_codes)
        for item in result.dispositions
    ] == [
        ("TOP", "pass", "final_selection", ("recommendation_selected",)),
        ("OUT", "fail", "top_n_gate", ("recommendation_outside_top_n",)),
    ]


def test_evaluator_has_no_concrete_source_or_application_dependencies() -> None:
    source_path = Path(__file__).parents[1] / "decision_module" / "recommendation" / "evaluate.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.append(node.module)
    forbidden = (
        "app_module",
        "data_module",
        "ui_qt",
        "scripts",
        "ml_module",
        "sqlite3",
        "requests",
        "httpx",
    )
    assert not [
        module for module in imported
        if any(module == prefix or module.startswith(prefix + ".") for prefix in forbidden)
    ]
