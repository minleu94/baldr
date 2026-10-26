from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

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
    assert result.recommendations[0].liquidity_state == "UNKNOWN"
    assert result.recommendations[0].source_trace == ("AdviceComposer.refusal",)
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
    assert recommendation.stock_name == "台積電"
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


def test_composer_projects_only_exact_stock_saved_screening_and_risk_evidence() -> None:
    from app_module.advice_composer import AdviceComposer

    source = _recommendation_result()
    source.screening_matrix_json = [
        {
            "stock_code": "2330",
            "stage": "legacy:technical_gate",
            "status": "pass",
            "quality": "observed",
            "reason_codes": [],
        },
        {
            "stock_code": "1101",
            "stage": "legacy:relative_strength",
            "status": "fail",
            "quality": "observed",
            "reason_codes": ["weak_rs"],
        },
    ]
    source.why_not_payload_json = [
        {"stock_code": "1101", "reason_codes": ["weak_rs"]}
    ]
    source.liquidity_gate_payload_json = [
        {"stock_code": "2201", "reason_codes": ["low_liquidity"]}
    ]

    result = AdviceComposer(AdvicePolicy()).compose(
        recommendations=source,
        portfolio_result=None,
        evidence_quality="OBSERVED",
        decision_date=date(2026, 7, 12),
        data_as_of_date=date(2026, 7, 11),
        mode=AdviceMode.GUIDED,
    )

    advice = result.recommendations[0]
    assert advice.stock_code == "2330"
    assert advice.advice_action is AdviceAction.ADD_CANDIDATE
    assert advice.liquidity_state == "UNKNOWN"
    assert advice.source_evidence == (
        "篩選：階段=legacy:technical_gate；結果=通過；資料品質=已觀測",
    )
    assert "1101" not in " ".join(advice.source_evidence)
    assert "2201" not in " ".join(advice.source_evidence)


def test_composer_projects_only_observed_same_stock_liquidity_gate_failure() -> None:
    from app_module.advice_composer import AdviceComposer

    source = _recommendation_result()
    source.liquidity_gate_payload_json = [
        {
            "stock_code": "2330",
            "status": "fail",
            "quality": "observed",
            "reason_codes": ["low_liquidity"],
            "threshold_name": "min_liquidity",
        }
    ]
    advice = AdviceComposer(AdvicePolicy()).compose(
        recommendations=source,
        portfolio_result=None,
        evidence_quality="OBSERVED",
        decision_date=date(2026, 7, 12),
        data_as_of_date=date(2026, 7, 11),
        mode=AdviceMode.GUIDED,
    ).recommendations[0]
    assert advice.liquidity_state == "GATE_FAIL"


@pytest.mark.parametrize(
    "payload",
    [
        [{"stock_code": "2330", "status": "degraded", "quality": "observed", "reason_codes": ["low_liquidity"]}],
        [{"stock_code": "2330", "status": "fail", "quality": "estimated", "reason_codes": ["low_liquidity"]}],
        [
            {"stock_code": "2330", "status": "fail", "quality": "observed", "reason_codes": ["low_liquidity"]},
            {"stock_code": "2330", "status": "fail", "quality": "observed", "reason_codes": ["low_liquidity"]},
        ],
    ],
)
def test_composer_keeps_untrusted_liquidity_payload_unknown(payload) -> None:
    from app_module.advice_composer import AdviceComposer

    source = _recommendation_result()
    source.liquidity_gate_payload_json = payload
    advice = AdviceComposer(AdvicePolicy()).compose(
        recommendations=source,
        portfolio_result=None,
        evidence_quality="OBSERVED",
        decision_date=date(2026, 7, 12),
        data_as_of_date=date(2026, 7, 11),
        mode=AdviceMode.GUIDED,
    ).recommendations[0]
    assert advice.liquidity_state == "UNKNOWN"


def test_advice_source_evidence_round_trips_and_missing_stays_explicit() -> None:
    from app_module.advice_composer import AdviceComposer
    from app_module.advice_dtos import RecommendationAdviceDTO

    source = _recommendation_result()
    advice = AdviceComposer(AdvicePolicy()).compose(
        recommendations=source,
        portfolio_result=None,
        evidence_quality="OBSERVED",
        decision_date=date(2026, 7, 12),
        data_as_of_date=date(2026, 7, 11),
        mode=AdviceMode.GUIDED,
    ).recommendations[0]

    assert "不能據此推定沒有反證或風險" in advice.source_evidence[0]
    assert advice.stock_name == "台積電"
    restored = RecommendationAdviceDTO.from_dict(advice.to_dict())
    assert restored.source_evidence == advice.source_evidence
    assert restored.stock_name == "台積電"


def test_composer_reads_canonical_typed_evidence_for_exact_recommended_stock() -> None:
    from app_module.advice_composer import AdviceComposer
    from app_module.recommendation.queries import RecommendationExecutionReadModel
    from decision_module.recommendation.contracts import (
        CandidateAssessment,
        DecisionBatch,
        FilterOutcome,
        RecommendationItem,
    )

    def assessment(stock_code: str, *, passed: bool, reason_code: str = "") -> CandidateAssessment:
        stage = "final_selection"
        row = {
            "stock_code": stock_code,
            "stock_name": f"name-{stock_code}",
            "status": "pass" if passed else "fail",
            "reason_codes": (reason_code,) if reason_code else (),
            "quality": "observed",
            "stage": stage,
            "threshold_name": "",
            "observed_value": "",
            "required_value": "",
            "total_score": "",
            "score_bp": None,
            "score_percentile_bp": None,
            "eligible_universe_size": None,
            "threshold_mode": "fixed",
            "warnings": (),
            "industry": "",
            "as_of_date": "2026-07-11",
            "data_fingerprint": "sha256:source",
        }
        outcome = FilterOutcome(
            filter_id=f"legacy:{stage}",
            passed=passed,
            reason=reason_code or ("pass" if passed else "fail"),
            evidence=row,
        )
        return CandidateAssessment(
            stock_code=stock_code,
            eligible=passed,
            filter_outcomes={outcome.filter_id: outcome},
        )

    decision = DecisionBatch(
        items=(RecommendationItem(stock_code="2330", reason_text="規則候選"),),
        assessments=(
            assessment("2330", passed=True),
            assessment("1101", passed=False, reason_code="weak_rs"),
        ),
    )
    execution = SimpleNamespace(
        result_id="canonical-evidence-result",
        context=SimpleNamespace(
            created_at=None,
            as_of_date=date(2026, 7, 11),
            result_config_snapshot=None,
            strategy_identity=None,
        ),
        request=SimpleNamespace(as_of_date=date(2026, 7, 11)),
        decision=decision,
        events=(),
    )
    read_model = RecommendationExecutionReadModel(
        execution=execution,
        label="canonical evidence result",
        notes=None,
        persisted_at=None,
        payload_hash="sha256:" + "b" * 64,
        artifact_location="private-path",
        integrity_basis="canonical_payload_and_index_verified",
    )

    advice = AdviceComposer(AdvicePolicy()).compose(
        recommendations=read_model,
        portfolio_result=None,
        evidence_quality="OBSERVED",
        decision_date=date(2026, 7, 12),
        data_as_of_date=date(2026, 7, 11),
        mode=AdviceMode.GUIDED,
    ).recommendations[0]

    assert advice.stock_code == "2330"
    assert advice.advice_action is AdviceAction.NO_NEW_POSITION
    assert advice.source_evidence == (
        "篩選：階段=final_selection；結果=通過；資料品質=已觀測",
    )
    assert "weak_rs" not in " ".join(advice.source_evidence)
    assert "private-path" not in " ".join(advice.source_evidence)


def test_strategy_advice_does_not_require_account_budget_or_position_inputs() -> None:
    from app_module.advice_composer import AdviceComposer

    recommendations = _recommendation_result()
    recommendations.config.pop("risk_budget_available")
    recommendations.config.pop("execution_feasible")
    result = AdviceComposer(AdvicePolicy()).compose(
        recommendations=recommendations,
        portfolio_result=None,
        evidence_quality="OBSERVED",
        decision_date=date(2026, 7, 12),
        data_as_of_date=date(2026, 7, 11),
        mode=AdviceMode.GUIDED,
    )

    advice = result.recommendations[0]
    assert advice.advice_action is AdviceAction.ADD_CANDIDATE
    assert advice.execution_feasibility == "UNKNOWN"
    assert "risk_budget_not_confirmed" not in advice.risk_reasons
    assert "execution_feasibility_not_confirmed" in advice.risk_reasons


def test_composer_carries_only_verified_canonical_payload_hash_into_source_trace() -> None:
    from app_module.advice_composer import AdviceComposer
    from app_module.recommendation.queries import RecommendationExecutionReadModel

    execution = SimpleNamespace(
        result_id="canonical-advice-result",
        context=SimpleNamespace(result_config_snapshot=None, strategy_identity=None),
        decision=SimpleNamespace(
            regime="Trend",
            items=(
                SimpleNamespace(
                    stock_code="2330",
                    stock_name="台積電",
                    close_price=Decimal("1000"),
                    price_change=Decimal("1"),
                    rule_score=Decimal("90"),
                    indicator_score=Decimal("30"),
                    pattern_score=Decimal("30"),
                    volume_score=Decimal("30"),
                    reason_text="test evidence",
                    reasons=(),
                    industry="半導體",
                    regime_match=True,
                    score_percentile_bp=None,
                    eligible_universe_size=None,
                    ranking_method=None,
                    threshold_mode=None,
                ),
            ),
        ),
        ml_receipt_refs=(),
    )
    read_model = RecommendationExecutionReadModel(
        execution=execution,
        label="canonical result",
        notes=None,
        persisted_at=None,
        payload_hash="sha256:" + "a" * 64,
        artifact_location="must-not-be-exposed",
        integrity_basis="canonical_payload_and_index_verified",
    )

    result = AdviceComposer(AdvicePolicy()).compose(
        recommendations=read_model,
        portfolio_result=None,
        evidence_quality="OBSERVED",
        decision_date=date(2026, 7, 12),
        data_as_of_date=date(2026, 7, 11),
        mode=AdviceMode.GUIDED,
    )

    advice = result.recommendations[0]
    assert advice.source_trace == (
        "RecommendationExecution",
        "canonical-advice-result",
        "canonical_payload_sha256:" + "a" * 64,
    )
    assert "must-not-be-exposed" not in advice.source_trace
    assert type(advice).from_dict(advice.to_dict()).source_trace == advice.source_trace


def test_composer_uses_only_canonical_saved_strategy_advice_contract_snapshot() -> None:
    from app_module.advice_composer import AdviceComposer
    from app_module.recommendation.contracts import StrategyAdviceContractSnapshot
    from app_module.recommendation.queries import RecommendationExecutionReadModel
    from app_module.strategy_advice_contract import StrategyAdviceContract

    contract = StrategyAdviceContract(
        thesis="策略作者明示的趨勢延續論點",
        invalidation_conditions=("收盤跌破策略界線",),
        holding_horizon="10 個交易日",
        review_cadence="每個交易日收盤後",
    )
    snapshot = StrategyAdviceContractSnapshot(
        strategy_version_id="version-1",
        contract_sha256=contract.contract_sha256,
        contract=contract,
    )
    execution = SimpleNamespace(
        result_id="canonical-advice-contract-result",
        context=SimpleNamespace(
            result_config_snapshot=None,
            strategy_identity=SimpleNamespace(strategy_version_id="version-1"),
            advice_contract_snapshot=snapshot,
        ),
        decision=SimpleNamespace(
            regime="Trend",
            items=(
                SimpleNamespace(
                    stock_code="2330",
                    stock_name="台積電",
                    close_price=Decimal("1000"),
                    price_change=Decimal("1"),
                    rule_score=Decimal("90"),
                    indicator_score=Decimal("30"),
                    pattern_score=Decimal("30"),
                    volume_score=Decimal("30"),
                    reason_text="保存的規則理由",
                    reasons=(),
                    industry="半導體",
                    regime_match=True,
                    score_percentile_bp=None,
                    eligible_universe_size=None,
                    ranking_method=None,
                    threshold_mode=None,
                ),
            ),
        ),
        ml_receipt_refs=(),
    )
    read_model = RecommendationExecutionReadModel(
        execution=execution,
        label="verified canonical result",
        notes=None,
        persisted_at=None,
        payload_hash="sha256:" + "a" * 64,
        artifact_location="private-path",
        integrity_basis="canonical_payload_and_index_verified",
    )

    advice = AdviceComposer(AdvicePolicy()).compose(
        recommendations=read_model,
        portfolio_result=None,
        evidence_quality="OBSERVED",
        decision_date=date(2026, 7, 12),
        data_as_of_date=date(2026, 7, 11),
        mode=AdviceMode.GUIDED,
    ).recommendations[0]

    assert advice.entry_thesis == contract.thesis
    assert advice.invalidation_conditions == contract.invalidation_conditions
    assert advice.holding_horizon == contract.holding_horizon
    assert advice.review_cadence == contract.review_cadence
    assert advice.source_trace[-3:] == (
        "strategy_advice_contract:",
        "version-1",
        contract.contract_sha256,
    )
    assert type(advice).from_dict(advice.to_dict()) == advice

    unverified_read_model = RecommendationExecutionReadModel(
        execution=execution,
        label="legacy-only hash verification",
        notes=None,
        persisted_at=None,
        payload_hash="sha256:" + "a" * 64,
        artifact_location="private-path",
        integrity_basis="legacy_read_time_hash_only",
    )
    unverified = AdviceComposer(AdvicePolicy()).compose(
        recommendations=unverified_read_model,
        portfolio_result=None,
        evidence_quality="OBSERVED",
        decision_date=date(2026, 7, 12),
        data_as_of_date=date(2026, 7, 11),
        mode=AdviceMode.GUIDED,
    ).recommendations[0]
    assert unverified.entry_thesis == ""
    assert unverified.invalidation_conditions == ()
    assert unverified.holding_horizon == ""
    assert unverified.review_cadence == ""

    legacy = AdviceComposer(AdvicePolicy()).compose(
        recommendations=_recommendation_result(),
        portfolio_result=None,
        evidence_quality="OBSERVED",
        decision_date=date(2026, 7, 12),
        data_as_of_date=date(2026, 7, 11),
        mode=AdviceMode.GUIDED,
    ).recommendations[0]
    assert legacy.entry_thesis == ""
    assert legacy.invalidation_conditions == ()
    assert legacy.holding_horizon == ""
    assert legacy.review_cadence == ""


@pytest.mark.parametrize(
    ("payload_hash", "integrity_basis"),
    [
        ("sha256:" + "z" * 64, "canonical_payload_and_index_verified"),
        ("sha256:" + "a" * 64, "legacy_read_time_hash_only"),
        ("sha256:" + "a" * 64, "legacy_trusted_hash_verified"),
    ],
)
def test_composer_omits_untrusted_or_invalid_source_hash(
    payload_hash: str, integrity_basis: str
) -> None:
    from app_module.advice_composer import AdviceComposer
    from app_module.recommendation.queries import RecommendationExecutionReadModel

    read_model = RecommendationExecutionReadModel(
        execution=object(),
        label="result",
        notes=None,
        persisted_at=None,
        payload_hash=payload_hash,
        artifact_location="private-path",
        integrity_basis=integrity_basis,  # type: ignore[arg-type]
    )

    assert AdviceComposer._verified_source_provenance(read_model) == ()


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
    assert presentation.cost_basis is None
    assert presentation.cost_basis_bp == 50
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
    assert advice.holding_horizon == ""
    assert advice.calibration_horizon == "20 trading days"
    presentation = DecisionPresentationService().from_recommendation_advice(advice)
    assert presentation.horizon == "20 trading days"
    assert presentation.holding_horizon == ""
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


@pytest.mark.parametrize("strategy_status", [None, "", "unknown", "retired"])
def test_professional_without_promoted_strategy_status_stays_research_candidate(
    strategy_status: str | None,
) -> None:
    from app_module.advice_composer import AdviceComposer

    source = _recommendation_result()
    source.config["strategy_status"] = strategy_status
    result = AdviceComposer(
        AdvicePolicy(AdvicePolicyConfig(mode=AdviceMode.PROFESSIONAL))
    ).compose(
        recommendations=source,
        portfolio_result=None,
        evidence_quality="OBSERVED",
        decision_date=date(2026, 7, 12),
        data_as_of_date=date(2026, 7, 12),
        mode=AdviceMode.PROFESSIONAL,
    )

    recommendation = result.recommendations[0]
    assert recommendation.advice_action is AdviceAction.RESEARCH
    assert recommendation.classification is AdviceClassification.PROFESSIONAL_CANDIDATE


def test_professional_promoted_strategy_is_independent_of_portfolio_inputs() -> None:
    from app_module.advice_composer import AdviceComposer

    result = AdviceComposer(
        AdvicePolicy(AdvicePolicyConfig(mode=AdviceMode.PROFESSIONAL))
    ).compose(
        recommendations=_recommendation_result(),
        portfolio_result=None,
        evidence_quality="OBSERVED",
        decision_date=date(2026, 7, 12),
        data_as_of_date=date(2026, 7, 12),
        mode=AdviceMode.PROFESSIONAL,
    )

    recommendation = result.recommendations[0]
    assert recommendation.advice_action is AdviceAction.ADD_CANDIDATE
    assert recommendation.classification is AdviceClassification.FORMAL_ADVICE
