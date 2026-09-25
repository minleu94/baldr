from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from types import SimpleNamespace

from app_module.dtos import RecommendationDTO, RecommendationResultDTO
from app_module.evidence_event_dtos import EvidenceEventType
from app_module.evidence_event_importer_dtos import EvidenceCaptureRequest
from app_module.evidence_event_importers import RecommendationEvidenceImporter
from app_module.recommendation.queries import RecommendationExecutionReadModel


class FakeRecommendationQueries:
    def __init__(self, result: RecommendationResultDTO):
        self.result = result

    def get(self, result_id: str) -> RecommendationExecutionReadModel | None:
        return _read_model(self.result) if result_id == self.result.result_id else None

    def list(self) -> tuple[RecommendationExecutionReadModel, ...]:
        return (_read_model(self.result),)


def _read_model(result: RecommendationResultDTO) -> RecommendationExecutionReadModel:
    return RecommendationExecutionReadModel(
        execution=None,
        label=result.result_name,
        notes=result.notes,
        persisted_at=None,
        payload_hash=None,
        artifact_location="synthetic-legacy.json",
        legacy_result=result,
        ml_read_status="legacy_saved_fields",
    )


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
    importer = RecommendationEvidenceImporter(FakeRecommendationQueries(_result()))

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
        FakeRecommendationQueries(_result(threshold_mode="fixed"))
    )

    result = importer.collect(EvidenceCaptureRequest(source="recommendation", result_id="rec-001"))

    event = result.event_payloads[0]
    assert event["score_percentile_bp"] is None
    assert "score_percentile_missing" not in event["warnings"]
    assert event["metadata"]["threshold_mode"] == "fixed"


def test_recommendation_importer_uses_requested_decision_date_and_stable_source_id():
    importer = RecommendationEvidenceImporter(FakeRecommendationQueries(_result(score_percentile_bp=9000)))

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
    importer = RecommendationEvidenceImporter(FakeRecommendationQueries(result_dto))

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
    importer = RecommendationEvidenceImporter(FakeRecommendationQueries(_result()))

    result = importer.collect(EvidenceCaptureRequest(source="recommendation", result_id="rec-001"))

    event = result.event_payloads[0]
    assert "strategy_version_id" not in event
    assert "cost_model_id" not in event
    assert "benchmark_id" not in event
    assert "universe_id" not in event["metadata"]
    assert "horizon_days" not in event["metadata"]


def test_recommendation_importer_rejects_mixed_latest_when_any_clock_is_unknown() -> None:
    legacy = replace(_read_model(_result()), persisted_at=None)
    canonical = RecommendationExecutionReadModel(
        execution=SimpleNamespace(
            result_id="canonical-with-aware-clock",
            context=SimpleNamespace(
                created_at=datetime(2026, 7, 3, 9, tzinfo=timezone.utc)
            ),
        ),
        label="canonical",
        notes="",
        persisted_at=datetime(2026, 7, 3, 9, tzinfo=timezone.utc),
        payload_hash=None,
        artifact_location="canonical",
    )

    class MixedQueries:
        def get(self, _result_id: str) -> RecommendationExecutionReadModel | None:
            return None

        def list(self) -> tuple[RecommendationExecutionReadModel, ...]:
            return (canonical, legacy)

    result = RecommendationEvidenceImporter(MixedQueries()).collect(
        EvidenceCaptureRequest(source="recommendation")
    )

    assert result.events_seen == 0
    assert result.diagnostics_by_code == {
        "recommendation_latest_selection_ambiguous_clock": 1
    }
