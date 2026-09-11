from __future__ import annotations

from datetime import date

from app_module.dtos import RecommendationDTO, RecommendationResultDTO
from app_module.evidence_event_dtos import EvidenceEventType
from app_module.evidence_event_importer_dtos import EvidenceCaptureRequest
from app_module.evidence_event_importers import RecommendationEvidenceImporter


class FakeRecommendationRepository:
    def __init__(self, result: RecommendationResultDTO):
        self.result = result

    def load_result(self, result_id: str) -> RecommendationResultDTO | None:
        return self.result if result_id == self.result.result_id else None

    def list_results(self) -> list[dict[str, object]]:
        return [
            {
                "result_id": self.result.result_id,
                "created_at": self.result.created_at,
            }
        ]


def _result(
    score_percentile_bp: int | None = None,
    *,
    threshold_mode: str = "cross_sectional",
) -> RecommendationResultDTO:
    return RecommendationResultDTO(
        result_id="rec-001",
        result_name="Evidence Import Test",
        config={"profile_id": "balanced", "profile_version": "1.0"},
        recommendations=[
            RecommendationDTO(
                stock_code="2330",
                stock_name="台積電",
                close_price=100.0,
                price_change=1.0,
                total_score=82.0,
                indicator_score=30.0,
                pattern_score=30.0,
                volume_score=22.0,
                recommendation_reasons="rank_top; volume_ok",
                industry="半導體",
                regime_match=True,
                score_percentile_bp=score_percentile_bp,
                threshold_mode=threshold_mode,
            )
        ],
        regime="Trend",
        created_at="2026-07-02T09:00:00",
    )


def test_recommendation_importer_preserves_missing_percentile_with_warning():
    importer = RecommendationEvidenceImporter(FakeRecommendationRepository(_result()))

    result = importer.collect(EvidenceCaptureRequest(source="recommendation", result_id="rec-001"))

    assert result.events_seen == 1
    event = result.event_payloads[0]
    assert event["event_type"] == EvidenceEventType.RECOMMENDATION_INCLUDED
    assert event["source_type"] == "recommendation_result"
    assert event["source_id"] == "rec-001"
    assert event["score_percentile_bp"] is None
    assert event["warnings"] == ("score_percentile_missing",)
    assert event["profile_id"] == "balanced"
    assert event["metadata"]["profile_version"] == "1.0"
    assert event["metadata"]["indicator_score_bp"] == 3000
    assert event["metadata"]["pattern_score_bp"] == 3000
    assert event["metadata"]["volume_score_bp"] == 2200
    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "source_missing_screening_matrix",
        "source_missing_exclusion_payload",
    ]
    assert result.diagnostics_by_code["source_missing_exclusion_payload"] == 1


def test_fixed_threshold_recommendation_does_not_emit_percentile_missing_warning():
    importer = RecommendationEvidenceImporter(
        FakeRecommendationRepository(_result(threshold_mode="fixed"))
    )

    result = importer.collect(EvidenceCaptureRequest(source="recommendation", result_id="rec-001"))

    event = result.event_payloads[0]
    assert event["score_percentile_bp"] is None
    assert "score_percentile_missing" not in event["warnings"]
    assert event["metadata"]["threshold_mode"] == "fixed"


def test_recommendation_importer_uses_requested_decision_date_and_stable_source_id():
    importer = RecommendationEvidenceImporter(FakeRecommendationRepository(_result(score_percentile_bp=9000)))

    result = importer.collect(
        EvidenceCaptureRequest(
            source="recommendation",
            result_id="rec-001",
            decision_date=date(2026, 7, 3),
        )
    )

    event = result.event_payloads[0]
    assert event["decision_date"] == "2026-07-03"
    assert event["source_id"] == "rec-001"
    assert event["score_percentile_bp"] == 9000


def test_recommendation_importer_preserves_explicit_v4_identity_without_defaults():
    result_dto = _result(score_percentile_bp=9000)
    result_dto.config.update(
        {
            "strategy_version_id": "strategy-v4-test",
            "cost_model_id": "cost-v1",
            "benchmark_id": "TAIEX",
            "industry_benchmark_id": "semiconductor-index",
            "universe_id": "recommendation-universe-v1:test",
            "universe_hash": "sha256:" + "a" * 64,
            "horizon_days": 5,
        }
    )
    result_dto.run_context = {
        "universe_id": "recommendation-universe-v1:test",
        "universe_hash": "sha256:" + "a" * 64,
        "universe_identity_schema": "recommendation-universe.v1",
        "horizon_days": 5,
    }
    importer = RecommendationEvidenceImporter(FakeRecommendationRepository(result_dto))

    result = importer.collect(EvidenceCaptureRequest(source="recommendation", result_id="rec-001"))

    event = result.event_payloads[0]
    assert event["strategy_version_id"] == "strategy-v4-test"
    assert event["cost_model_id"] == "cost-v1"
    assert event["benchmark_id"] == "TAIEX"
    assert event["industry_benchmark_id"] == "semiconductor-index"
    assert event["metadata"]["universe_id"] == "recommendation-universe-v1:test"
    assert event["metadata"]["universe_hash"] == "sha256:" + "a" * 64
    assert event["metadata"]["horizon_days"] == 5


def test_recommendation_importer_does_not_infer_missing_v4_identity():
    importer = RecommendationEvidenceImporter(FakeRecommendationRepository(_result()))

    result = importer.collect(EvidenceCaptureRequest(source="recommendation", result_id="rec-001"))

    event = result.event_payloads[0]
    assert "strategy_version_id" not in event
    assert "cost_model_id" not in event
    assert "benchmark_id" not in event
    assert "universe_id" not in event["metadata"]
    assert "horizon_days" not in event["metadata"]
