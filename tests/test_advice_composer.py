from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app_module.advice_dtos import AdviceAction, AdviceClassification, AdviceMode, AdvicePolicyConfig
from app_module.advice_policy import AdvicePolicy
from app_module.dtos import RecommendationDTO, RecommendationResultDTO
from app_module.portfolio_construction_dtos import (
    PortfolioAllocationRow,
    PortfolioConstructionResult,
)
from app_module.portfolio_allocation_dtos import (
    AllocationWeightContract,
    PortfolioAllocationResultV2,
    PortfolioAllocationRowV2,
)


def _recommendation_result() -> RecommendationResultDTO:
    return RecommendationResultDTO(
        result_id="rec-20260712-001",
        result_name="平衡型推薦",
        config={
            "strategy_status": "promoted",
            "parameters_locked": True,
            "disclosure_complete": True,
            "strategy_version": "v2.1",
            "execution_feasible": True,
            "risk_budget_available": True,
        },
        recommendations=[
            RecommendationDTO(
                stock_code="2330",
                stock_name="台積電",
                close_price=Decimal("1000"),
                price_change=Decimal("1.2"),
                total_score=Decimal("90"),
                indicator_score=Decimal("30"),
                pattern_score=Decimal("30"),
                volume_score=Decimal("30"),
                recommendation_reasons="技術型態完整；量能支持",
                industry="半導體",
                regime_match=True,
            )
        ],
        regime="Trend",
        created_at="2026-07-12T09:00:00",
    )


def _portfolio_result() -> PortfolioConstructionResult:
    return PortfolioConstructionResult(
        decision_date="2026-07-12",
        allocation_method="equal_weight",
        capital_amount=Decimal("1000000"),
        allocations=(
            PortfolioAllocationRow(
                stock_code="2330",
                stock_name="台積電",
                target_weight_bp=1500,
                constrained_weight_bp=1500,
                target_amount=Decimal("150000"),
                constrained_amount=Decimal("150000"),
                executable_amount=Decimal("150000"),
                reference_price=Decimal("1000"),
                executable_shares=150,
                diagnostics=("lot_size_applied",),
            ),
        ),
        residual_cash=Decimal("300000"),
    )


def test_composer_preserves_dates_and_returns_no_new_position_for_missing_evidence() -> None:
    from app_module.advice_composer import AdviceComposer

    result = AdviceComposer(AdvicePolicy()).compose(
        recommendations=(),
        portfolio_result=None,
        evidence_quality="MISSING",
        decision_date=date(2026, 7, 12),
        data_as_of_date=date(2026, 7, 12),
        mode=AdviceMode.GUIDED,
    )

    assert result.decision_date == "2026-07-12"
    assert result.data_as_of_date == "2026-07-12"
    assert result.recommendations[0].advice_action is AdviceAction.NO_NEW_POSITION
    assert result.recommendations[0].source_trace == ("RecommendationResultDTO",)
    assert result.recommendations[0].why_not_reasons == (
        "evidence_quality_missing",
    )
    assert "evidence_quality_missing" in result.recommendations[0].risk_reasons
    assert result.recommendations[0].refusal_reasons == ("evidence_quality_missing",)


def test_composer_uses_injected_payloads_and_integer_bp_portfolio_gap() -> None:
    from app_module.advice_composer import AdviceComposer

    result = AdviceComposer(AdvicePolicy()).compose(
        recommendations=_recommendation_result(),
        portfolio_result=_portfolio_result(),
        evidence_quality="OBSERVED",
        evidence_warnings=("evidence_freshness_review_required",),
        decision_date=date(2026, 7, 12),
        data_as_of_date=date(2026, 7, 11),
        mode=AdviceMode.GUIDED,
        current_weights_bp={"2330": 500},
    )

    recommendation = result.recommendations[0]
    portfolio = result.portfolio_rows[0]
    assert recommendation.advice_action is AdviceAction.ADD_CANDIDATE
    assert recommendation.source_trace == ("RecommendationResultDTO", "rec-20260712-001")
    assert recommendation.decision_date == "2026-07-12"
    assert recommendation.data_as_of_date == "2026-07-11"
    assert recommendation.why_reasons == ("技術型態完整", "量能支持")
    assert recommendation.why_not_reasons == ()
    assert recommendation.risk_reasons == (
        "evidence_freshness_review_required",
    )
    assert portfolio.target_weight_bp == 1500
    assert portfolio.current_weight_bp == 500
    assert portfolio.weight_gap_bp == 1000
    assert portfolio.source_trace == ("PortfolioConstructionResult", "rec-20260712-001")
    assert result.warnings == ("evidence_freshness_review_required",)


def test_composer_keeps_missing_current_weight_as_diagnostic_without_inventing_position() -> None:
    from app_module.advice_composer import AdviceComposer

    result = AdviceComposer(AdvicePolicy()).compose(
        recommendations=_recommendation_result(),
        portfolio_result=_portfolio_result(),
        evidence_quality="OBSERVED",
        decision_date=date(2026, 7, 12),
        data_as_of_date=date(2026, 7, 12),
        mode=AdviceMode.GUIDED,
    )

    portfolio = result.portfolio_rows[0]
    assert portfolio.current_weight_bp is None
    assert portfolio.weight_gap_bp is None
    assert portfolio.advice_action is AdviceAction.NO_NEW_POSITION
    assert portfolio.reasons == ("current_weight_missing",)
    assert portfolio.diagnostics == ("lot_size_applied", "current_weight_missing")


def test_composer_derives_exit_reduce_and_hold_from_final_weight_gap() -> None:
    from app_module.advice_composer import AdviceComposer

    composer = AdviceComposer(AdvicePolicy())
    exit_result = composer.compose(
        recommendations=_recommendation_result(),
        portfolio_result=_portfolio_result(),
        evidence_quality="OBSERVED",
        decision_date=date(2026, 7, 12),
        data_as_of_date=date(2026, 7, 12),
        mode=AdviceMode.GUIDED,
        current_weights_bp={"2330": 1800},
    )
    hold_result = composer.compose(
        recommendations=_recommendation_result(),
        portfolio_result=_portfolio_result(),
        evidence_quality="OBSERVED",
        decision_date=date(2026, 7, 12),
        data_as_of_date=date(2026, 7, 12),
        mode=AdviceMode.GUIDED,
        current_weights_bp={"2330": 1600},
    )

    assert exit_result.portfolio_rows[0].advice_action is AdviceAction.REDUCE_CANDIDATE
    assert hold_result.portfolio_rows[0].advice_action is AdviceAction.HOLD


def test_composer_rejects_portfolio_result_after_advice_decision_date() -> None:
    from app_module.advice_composer import AdviceComposer

    future_portfolio = PortfolioConstructionResult(
        decision_date="2026-07-13",
        allocation_method="equal_weight",
        capital_amount=Decimal("1000000"),
        allocations=(),
        residual_cash=Decimal("300000"),
    )

    with pytest.raises(ValueError, match="portfolio_result.decision_date"):
        AdviceComposer(AdvicePolicy()).compose(
            recommendations=_recommendation_result(),
            portfolio_result=future_portfolio,
            evidence_quality="OBSERVED",
            decision_date=date(2026, 7, 12),
            data_as_of_date=date(2026, 7, 12),
            mode=AdviceMode.GUIDED,
        )


def test_composer_accepts_v2_allocation_and_preserves_executable_weight() -> None:
    from app_module.advice_composer import AdviceComposer

    weights = AllocationWeightContract(
        symbol_weights_bp={"2330": 1500},
        cash_weight_bp=8500,
    )
    result_v2 = PortfolioAllocationResultV2(
        decision_date="2026-07-12",
        alpha_bp=0,
        rule_requested_weights=weights,
        ml_requested_weights=weights,
        blended_weights=weights,
        target_weights=weights,
        executable_weights=weights,
        rows=(
            PortfolioAllocationRowV2(
                stock_code="2330",
                stock_name="台積電",
                rule_requested_weight_bp=1500,
                ml_requested_weight_bp=1500,
                blended_weight_bp=1500,
                target_weight_bp=1500,
                current_weight_bp=1000,
                gap_weight_bp=500,
                executable_weight_bp=1500,
                executable_shares=1000,
                reference_price=Decimal("1000"),
                executable_amount=Decimal("1000000.00"),
                estimated_cost=Decimal("2500.00"),
            ),
        ),
        current_cash_bp=9000,
        post_cost_cash_amount=Decimal("8975000.00"),
        total_estimated_cost=Decimal("2500.00"),
        advice_action="ADD_CANDIDATE",
        coverage_bp=10000,
        model_hash="sha256:model",
        dataset_identity_hash="sha256:dataset-identity",
        dataset_manifest_file_hash="sha256:dataset-manifest-file",
        universe_hash="sha256:universe",
        policy_hash="sha256:policy",
        rule_policy_hash="sha256:rule",
    )

    dashboard = AdviceComposer(AdvicePolicy()).compose(
        recommendations=_recommendation_result(),
        portfolio_result=result_v2,
        evidence_quality="OBSERVED",
        decision_date=date(2026, 7, 12),
        data_as_of_date=date(2026, 7, 11),
        mode=AdviceMode.GUIDED,
    )

    row = dashboard.portfolio_rows[0]
    assert row.advice_action is AdviceAction.ADD_CANDIDATE
    assert row.current_weight_bp == 1000
    assert row.weight_gap_bp == 500
    assert row.executable_weight_bp == 1500
    assert row.source_trace[0] == "PortfolioAllocationResultV2"


def test_typed_calibration_projection_flows_to_advice_and_decision_presentation() -> None:
    from app_module.advice_composer import AdviceComposer
    from app_module.decision_presentation import DecisionPresentationService
    from app_module.recommendation_calibration_consumer import RecommendationCalibrationProjection

    projection = RecommendationCalibrationProjection(
        stock_code="2330",
        ranking_score_bp=2400,
        ranking_percentile_bp=8200,
        ranking_method="absolute_return_shadow_candidate",
        calibrated_probability_bp=6000,
        calibrated_probability_status="shadow_candidate",
        after_cost_profit_probability_bp=5500,
        after_cost_profit_probability_status="shadow_candidate",
        confidence_tier="research_candidate",
        evidence_confidence="shadow_candidate",
        sample_size=120,
        horizon="20 trading days",
        cost_basis="fixed_round_trip_bp=50; observed liquidity",
        cost_basis_bp=50,
        model_version="rec-cal-model-2",
        dataset_version="recommendation-dataset-2",
        source_trace=(
            "candidate:rec-cal-model-2",
            "dataset:recommendation-dataset-2",
            "cost_scenario:legacy-fixed-round-trip-bp-v1",
            "after_cost_baseline:after_cost_null_benchmark_50pct_v1",
            "after_cost_baseline_contract:independent_null_benchmark_v1",
        ),
        warnings=("shadow-only",),
        status="active_candidate",
    )
    dashboard = AdviceComposer(AdvicePolicy()).compose(
        recommendations=_recommendation_result(),
        portfolio_result=_portfolio_result(),
        evidence_quality="OBSERVED",
        decision_date=date(2026, 7, 12),
        data_as_of_date=date(2026, 7, 11),
        mode=AdviceMode.GUIDED,
        current_weights_bp={"2330": 500},
        calibration_by_stock_code={"2330": projection},
    )
    recommendation = dashboard.recommendations[0]
    portfolio = dashboard.portfolio_rows[0]
    assert recommendation.calibrated_probability_bp == 6000
    assert recommendation.after_cost_profit_probability_bp == 5500
    assert recommendation.ranking_score_bp == 2400
    assert recommendation.sample_size == 120
    assert "candidate:rec-cal-model-2" in recommendation.source_trace
    assert "cost_scenario:legacy-fixed-round-trip-bp-v1" in recommendation.source_trace
    assert portfolio.calibrated_probability_bp == 6000
    presentation = DecisionPresentationService().from_recommendation_advice(recommendation)
    assert presentation.ranking_score == Decimal("2400")
    assert presentation.ranking_percentile_bp == 8200
    assert presentation.calibrated_probability_bp == 6000
    assert presentation.after_cost_profit_probability_bp == 5500
    assert presentation.sample_size == 120
    assert presentation.cost_basis == Decimal("50")
    assert presentation.horizon == "20 trading days"
    assert "cost_scenario:legacy-fixed-round-trip-bp-v1" in presentation.source_trace


def test_untyped_calibration_mapping_cannot_inject_probability_or_scope() -> None:
    from app_module.advice_composer import AdviceComposer
    from app_module.decision_presentation import DecisionPresentationService, format_decision_presentation

    raw_payload = {
        "ranking_score_bp": 2400,
        "calibrated_probability_bp": 8000,
        "calibrated_probability_status": "available",
        "after_cost_profit_probability_bp": 7500,
        "after_cost_profit_probability_status": "available",
        "evidence_confidence": "verified",
        "sample_size": 9999,
        "cost_basis_bp": 50,
        "horizon": "20 trading days",
        "model_version": "spoofed-model",
        "dataset_version": "spoofed-dataset",
        "status": "verified",
    }

    dashboard = AdviceComposer(AdvicePolicy()).compose(
        recommendations=_recommendation_result(),
        portfolio_result=_portfolio_result(),
        evidence_quality="OBSERVED",
        decision_date=date(2026, 7, 12),
        data_as_of_date=date(2026, 7, 11),
        mode=AdviceMode.GUIDED,
        current_weights_bp={"2330": 500},
        calibration_by_stock_code={"2330": raw_payload},
    )

    advice = dashboard.recommendations[0]
    presentation = DecisionPresentationService().from_recommendation_advice(advice)
    assert advice.ranking_score_bp is None
    assert advice.calibrated_probability_bp is None
    assert advice.after_cost_profit_probability_bp is None
    assert advice.sample_size is None
    assert presentation.calibrated_probability_bp is None
    assert presentation.after_cost_profit_probability_bp is None
    text = format_decision_presentation(presentation)
    assert "80.00%" not in text
    assert "75.00%" not in text
    assert "可用估計" not in text


def test_typed_projection_with_missing_scope_or_wrong_stock_fails_closed() -> None:
    from app_module.advice_composer import AdviceComposer
    from app_module.decision_presentation import DecisionPresentationService
    from app_module.recommendation_calibration_consumer import RecommendationCalibrationProjection

    projection = RecommendationCalibrationProjection(
        stock_code="1101",
        ranking_score_bp=2400,
        ranking_percentile_bp=8200,
        ranking_method="absolute_return_shadow_candidate",
        calibrated_probability_bp=8000,
        calibrated_probability_status="shadow_candidate",
        after_cost_profit_probability_bp=7500,
        after_cost_profit_probability_status="shadow_candidate",
        confidence_tier="research_candidate",
        evidence_confidence="shadow_candidate",
        sample_size=9999,
        horizon="",
        cost_basis="",
        cost_basis_bp=None,
        model_version="",
        dataset_version="",
        source_trace=("candidate:spoofed",),
        status="active_candidate",
    )

    dashboard = AdviceComposer(AdvicePolicy()).compose(
        recommendations=_recommendation_result(),
        portfolio_result=None,
        evidence_quality="OBSERVED",
        decision_date=date(2026, 7, 12),
        data_as_of_date=date(2026, 7, 11),
        mode=AdviceMode.GUIDED,
        calibration_by_stock_code={"2330": projection},
    )

    advice = dashboard.recommendations[0]
    presentation = DecisionPresentationService().from_recommendation_advice(advice)
    assert advice.calibrated_probability_bp is None
    assert advice.after_cost_profit_probability_bp is None
    assert presentation.calibrated_probability_bp is None
    assert presentation.after_cost_profit_probability_bp is None


def test_recommendation_dto_without_projection_scope_fails_closed() -> None:
    from app_module.advice_composer import AdviceComposer
    from app_module.decision_presentation import DecisionPresentationService

    source = _recommendation_result()
    recommendation = source.recommendations[0]
    recommendation.calibrated_probability_bp = 8000
    recommendation.calibrated_probability_status = "shadow_candidate"
    recommendation.after_cost_profit_probability_bp = 7500
    recommendation.after_cost_profit_probability_status = "shadow_candidate"
    recommendation.calibration_status = "active_candidate"
    # Deliberately omit model/dataset/horizon/source/cost lineage.

    dashboard = AdviceComposer(AdvicePolicy()).compose(
        recommendations=source,
        portfolio_result=None,
        evidence_quality="OBSERVED",
        decision_date=date(2026, 7, 12),
        data_as_of_date=date(2026, 7, 11),
        mode=AdviceMode.GUIDED,
    )

    advice = dashboard.recommendations[0]
    presentation = DecisionPresentationService().from_recommendation_advice(advice)
    assert advice.calibrated_probability_bp is None
    assert advice.after_cost_profit_probability_bp is None
    assert presentation.calibrated_probability_bp is None
    assert presentation.after_cost_profit_probability_bp is None


def test_recommendation_dto_projection_is_reused_by_normal_advice_and_portfolio_paths() -> None:
    from app_module.advice_composer import AdviceComposer
    from app_module.decision_presentation import DecisionPresentationService

    source = _recommendation_result()
    recommendation = source.recommendations[0]
    recommendation.ranking_score_bp = 2_400
    recommendation.score_percentile_bp = 8_200
    recommendation.ranking_method = "absolute_return_shadow_candidate"
    recommendation.calibrated_probability_bp = 6_000
    recommendation.calibrated_probability_status = "shadow_candidate"
    recommendation.after_cost_profit_probability_bp = 5_500
    recommendation.after_cost_profit_probability_status = "shadow_candidate"
    recommendation.evidence_confidence = "shadow_candidate"
    recommendation.sample_size = 120
    recommendation.cost_basis_bp = 50
    recommendation.calibration_model_version = "rec-cal-model-2"
    recommendation.calibration_dataset_version = "recommendation-dataset-2"
    recommendation.calibration_horizon = "20 trading days"
    recommendation.calibration_status = "active_candidate"
    recommendation.calibration_source = "RecommendationCalibrationConsumer"
    recommendation.calibration_source_trace = [
        "candidate:rec-cal-model-2",
        "dataset:recommendation-dataset-2",
        "cost_scenario:legacy-fixed-round-trip-bp-v1",
        "after_cost_baseline:after_cost_null_benchmark_50pct_v1",
        "after_cost_baseline_contract:independent_null_benchmark_v1",
    ]

    dashboard = AdviceComposer(AdvicePolicy()).compose(
        recommendations=source,
        portfolio_result=_portfolio_result(),
        evidence_quality="OBSERVED",
        decision_date=date(2026, 7, 12),
        data_as_of_date=date(2026, 7, 11),
        mode=AdviceMode.GUIDED,
        current_weights_bp={"2330": 500},
    )

    advice = dashboard.recommendations[0]
    assert advice.calibrated_probability_bp == 6_000
    assert advice.after_cost_profit_probability_bp == 5_500
    assert advice.sample_size == 120
    assert "candidate:rec-cal-model-2" in advice.source_trace
    portfolio = dashboard.portfolio_rows[0]
    assert portfolio.calibrated_probability_bp == 6_000
    presentation = DecisionPresentationService().from_recommendation_advice(advice)
    assert presentation.calibrated_probability_bp == 6_000
    assert presentation.after_cost_profit_probability_bp == 5_500
    assert presentation.sample_size == 120


def test_professional_candidate_is_classified_for_research_section() -> None:
    from app_module.advice_composer import AdviceComposer

    source = _recommendation_result()
    source.config["strategy_status"] = "candidate"
    result = AdviceComposer(AdvicePolicy(AdvicePolicyConfig(mode=AdviceMode.PROFESSIONAL))).compose(
        recommendations=source,
        portfolio_result=_portfolio_result(),
        evidence_quality="OBSERVED",
        decision_date=date(2026, 7, 12),
        data_as_of_date=date(2026, 7, 12),
        mode=AdviceMode.PROFESSIONAL,
    )

    recommendation = result.recommendations[0]
    assert recommendation.advice_action is AdviceAction.RESEARCH
    assert recommendation.classification is AdviceClassification.PROFESSIONAL_CANDIDATE
