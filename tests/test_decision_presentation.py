from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app_module.advice_dtos import AdviceAction, PortfolioAdviceDTO, RecommendationAdviceDTO
from app_module.decision_presentation import (
    DecisionPresentationDTO,
    DecisionPresentationService,
    decision_action_label,
    format_decision_presentation,
)


def test_presentation_round_trip_keeps_decimal_and_fail_closed_probability() -> None:
    presentation = DecisionPresentationDTO(
        stock_code="2330",
        ranking_score=Decimal("82.5"),
        ranking_percentile_bp=8250,
        ranking_method="nearest_rank",
        calibrated_probability_status="available",
        action_suitability=AdviceAction.HOLD.value,
        evidence_status="observed",
        sample_size=120,
        cost_basis=Decimal("950.00"),
        target_weight_bp=1500,
        current_weight_bp=1000,
        weight_gap_bp=500,
    )

    assert presentation.calibrated_probability_bp is None
    assert presentation.calibrated_probability_status == "unavailable"
    assert decision_action_label(presentation.action_suitability) == "持有"
    restored = DecisionPresentationDTO.from_dict(presentation.to_dict())
    assert restored == presentation
    assert "校準機率：不可用" in format_decision_presentation(presentation)


def test_recommendation_adapter_does_not_invent_probability() -> None:
    service = DecisionPresentationService()
    advice = RecommendationAdviceDTO(
        stock_code="2330",
        advice_action=AdviceAction.ADD_CANDIDATE,
        why_reasons=("score_eligible",),
        risk_reasons=("liquidity_review",),
        data_quality="degraded",
        holding_horizon="swing",
        decision_date="2026-09-08",
        data_as_of_date="2026-09-07",
        source_trace=("recommendation:run-1",),
    )

    presentation = service.from_recommendation_advice(
        advice,
        ranking_score="82.5",
        sample_size=120,
    )

    assert presentation.action_suitability == "ADD_CANDIDATE"
    assert presentation.ranking_score == Decimal("82.5")
    assert presentation.ranking_percentile_bp is None
    assert presentation.sample_size == 120
    assert presentation.evidence_status == "degraded"
    assert presentation.calibrated_probability_bp is None
    assert presentation.calibrated_probability_status == "research"
    assert presentation.after_cost_profit_probability_bp is None
    assert presentation.after_cost_profit_probability_status == "research"


def test_watchlist_adapter_uses_saved_score_and_research_action() -> None:
    service = DecisionPresentationService()
    analysis = SimpleNamespace(
        stock_code="2603",
        status="saved",
        score="71.25",
        sample_size=48,
        score_percentile_bp=7350,
        ranking_method="nearest_rank",
        reasons="量價結構；保存快照",
        message="已保存",
        result_id="run-2",
        decision_date="2026-09-08",
        data_date="2026-09-07",
        source_id="source-2",
    )

    presentation = service.from_watchlist_analysis(analysis)

    assert presentation.ranking_score == Decimal("71.25")
    assert presentation.sample_size == 48
    assert presentation.ranking_percentile_bp == 7350
    assert presentation.ranking_method == "nearest_rank"
    assert presentation.action_suitability == "RESEARCH"
    assert presentation.evidence_status == "degraded"
    assert presentation.calibrated_probability_status == "research"
    assert presentation.reasons == ("量價結構", "保存快照")


def test_position_adapter_maps_existing_condition_state_and_keeps_unknown_gap() -> None:
    service = DecisionPresentationService()
    position = SimpleNamespace(
        stock_code="1101",
        stock_name="水泥",
        average_cost=Decimal("32.50"),
        last_trade_date="2026-09-05",
        source_type="recommendation_result",
        source_id="run-3",
        source_snapshot_hash="hash-3",
        source_summary={
            "current_weight_bp": 1200,
            "target_weight_bp": 800,
            "weight_gap_bp": -400,
            "invalidation_conditions": ("跌破 thesis 支撐",),
        },
        health_reasons=("相對強弱轉弱",),
        exit_reasons=(),
    )
    condition = SimpleNamespace(
        status="invalid",
        reasons=("已觸發失效條件",),
    )

    presentation = service.from_position(position, condition_result=condition)

    assert presentation.action_suitability == "EXIT_CANDIDATE"
    assert presentation.evidence_status == "degraded"
    assert presentation.cost_basis == Decimal("32.50")
    assert presentation.target_weight_bp == 800
    assert presentation.current_weight_bp == 1200
    assert presentation.weight_gap_bp == -400
    assert presentation.invalidation_conditions == ("跌破 thesis 支撐",)
    assert any("唯讀候選分類" in warning for warning in presentation.warnings)


def test_position_adapter_exposes_condition_reason_as_invalidation_hint() -> None:
    service = DecisionPresentationService()
    position = SimpleNamespace(stock_code="2330", source_summary={})
    condition = SimpleNamespace(status="warning", reasons=("Regime 已改變",))

    presentation = service.from_position(position, condition_result=condition)

    assert presentation.invalidation_conditions == ("Regime 已改變",)


def test_invalid_probability_value_is_rejected() -> None:
    with pytest.raises(ValueError, match="calibrated_probability_bp"):
        DecisionPresentationDTO(
            stock_code="2330",
            calibrated_probability_bp=10001,
        )


def test_presentation_separates_calibrated_and_after_cost_probability() -> None:
    presentation = DecisionPresentationDTO(
        stock_code="2330",
        ranking_score=Decimal("82.5"),
        calibrated_probability_bp=6400,
        after_cost_profit_probability_bp=5100,
        evidence_confidence="B",
    )

    text = format_decision_presentation(presentation)

    assert "排名分數：82.5（僅作排序，不等於機率）" in text
    assert "校準機率：64.00%" in text
    assert "成本後獲利機率：51.00%" in text
    assert "證據信心：B" in text


def test_probability_status_available_without_value_fails_closed_for_both_fields() -> None:
    presentation = DecisionPresentationDTO(
        stock_code="2330",
        calibrated_probability_status="available",
        after_cost_profit_probability_status="available",
    )

    assert presentation.calibrated_probability_bp is None
    assert presentation.calibrated_probability_status == "unavailable"
    assert presentation.after_cost_profit_probability_bp is None
    assert presentation.after_cost_profit_probability_status == "unavailable"


def test_from_dict_normalizes_bp_strings_without_deriving_probability_from_score() -> None:
    presentation = DecisionPresentationDTO.from_dict(
        {
            "stock_code": "2330",
            "ranking_score": "82.5",
            "target_weight_bp": "1500",
            "current_weight_bp": "1000",
            "weight_gap_bp": "500",
            "calibrated_probability_status": "research",
            "after_cost_profit_probability_status": "research",
        }
    )

    assert presentation.ranking_score == Decimal("82.5")
    assert presentation.target_weight_bp == 1500
    assert presentation.current_weight_bp == 1000
    assert presentation.weight_gap_bp == 500
    assert presentation.calibrated_probability_bp is None
    assert presentation.after_cost_profit_probability_bp is None
