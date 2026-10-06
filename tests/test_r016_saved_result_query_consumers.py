"""Wave 6 R016 saved-result consumers use one verified read view."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from app_module.advice_composer import AdviceComposer
from app_module.advice_dtos import AdviceMode
from app_module.advice_policy import AdvicePolicy
from app_module.decision_desk_service import SavedRecommendationDeskProvider
from app_module.dtos import RecommendationResultDTO
from app_module.evidence_event_importer_dtos import EvidenceCaptureRequest
from app_module.evidence_event_importers import RecommendationEvidenceImporter
from app_module.evidence_source_coverage_service import EvidenceSourceCoverageService
from app_module.historical_evidence_replay import HistoricalEvidenceReplayService
from app_module.recommendation.contracts import (
    Context,
    ExecutionStatus,
    ExecutionEvent,
    QualityReport,
    QualityStatus,
    RecommendationExecution,
    RecommendationResultConfigSnapshot,
    ReferenceKind,
    Request,
    VersionReference,
)
from app_module.recommendation.persistence import (
    ExecutionArtifactIntegrityError,
    RecommendationExecutionPersistence,
)
from app_module.recommendation.queries import RecommendationExecutionQueries, RecommendationExecutionReadModel
from app_module.saved_recommendation_queries import select_latest_saved_recommendation
from app_module.saved_recommendation_queries import (
    canonical_manual_decision_date,
    canonical_scheduled_decision_date,
)
from app_module.pre_v2_readiness_service import PreV2ReadinessService
from app_module.watchlist_analysis_service import WatchlistAnalysisService
from data_module.contracts.market import SourceRef
from data_module.result_artifact_store import ResultArtifactStore
from decision_module.recommendation.contracts import (
    CandidateAssessment,
    DecisionBatch,
    FilterOutcome,
    LiquidityAssessment,
    NegativeEvidence,
    RecommendationItem,
)


RESULT_ID = "r016-canonical-synthetic-001"
AS_OF_DATE = date(2026, 9, 8)
SOURCE_REF = SourceRef("synthetic-provider", "rev-4", "snapshot-r016")


def _stack(tmp_path: Path) -> tuple[Any, RecommendationExecutionQueries, Path]:
    output_root = tmp_path / "output"
    runs_dir = output_root / "recommendation" / "runs"
    store = ResultArtifactStore(
        artifact_root=runs_dir / "execution_artifacts",
        database_path=runs_dir / "recommendation_runs.db",
    )
    persistence = RecommendationExecutionPersistence(store)
    queries = RecommendationExecutionQueries(persistence)
    config = SimpleNamespace(output_root=output_root)
    execution = _execution()
    receipt = persistence.save(
        execution,
        label="R016 synthetic result",
        now=lambda: datetime(2026, 9, 8, 7, tzinfo=timezone.utc),
    )
    assert receipt.artifact_location is not None
    artifact_path = store.artifact_root / receipt.artifact_location
    return config, queries, artifact_path


def _save_capture_execution(
    tmp_path: Path,
    *,
    result_id: str,
) -> tuple[Any, RecommendationExecutionQueries, Path]:
    config, queries, _initial_artifact = _stack(tmp_path)
    runs_dir = Path(config.output_root) / "recommendation" / "runs"
    store = ResultArtifactStore(
        artifact_root=runs_dir / "execution_artifacts",
        database_path=runs_dir / "recommendation_runs.db",
    )
    persistence = RecommendationExecutionPersistence(store)
    execution = replace(
        _execution(result_id=result_id),
        events=(
            ExecutionEvent(
                event_type="legacy_negative_evidence_capture",
                message="synthetic saved capture",
                details={
                    "screening_matrix": [{"stock_code": "2330", "status": "pass"}],
                    "why_not_payload": [{"stock_code": "1101", "reason": "excluded"}],
                    "liquidity_gate_payload": [{"stock_code": "2201", "reason": "low liquidity"}],
                    "excluded_candidates": [{"stock_code": "1101"}],
                },
            ),
        ),
    )
    receipt = persistence.save(
        execution,
        label="R016 synthetic capture result",
        now=lambda: datetime(2026, 9, 8, 9, tzinfo=timezone.utc),
    )
    assert receipt.artifact_location is not None
    return config, queries, store.artifact_root / receipt.artifact_location


def _execution(*, result_id: str = RESULT_ID, as_of_date: date | None = AS_OF_DATE) -> RecommendationExecution:
    saved_config = {
        "profile_id": "balanced-synthetic",
        "profile_version": "2.1",
        "strategy_status": "promoted",
        "parameters_locked": True,
        "disclosure_complete": True,
        "execution_feasible": True,
        "risk_budget_available": True,
    }
    raw_config = json.dumps(saved_config, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    config_snapshot = RecommendationResultConfigSnapshot(
        raw_result_config_json=raw_config,
        config_sha256="sha256:" + hashlib.sha256(raw_config.encode("utf-8")).hexdigest(),
    )
    profile_ref = VersionReference(ReferenceKind.PROFILE, "balanced-synthetic", "2.1")
    item = RecommendationItem(
        stock_code="2330",
        stock_name="合成台積電",
        rank=1,
        rule_score=Decimal("75"),
        close_price=Decimal("100"),
        price_change=Decimal("1.25"),
        indicator_score=Decimal("25"),
        pattern_score=Decimal("20"),
        volume_score=Decimal("30"),
        industry="合成半導體",
        reason_text="均線向上",
        reasons=("rank_top", "volume_ok"),
        score_percentile_bp=9000,
        eligible_universe_size=12,
        ranking_method="score_desc",
        threshold_mode="fixed",
        regime_match=True,
    )
    excluded = CandidateAssessment(
        stock_code="1101",
        eligible=False,
        filter_outcomes={
            "min-turnover": FilterOutcome(
                "min-turnover",
                False,
                reason="turnover_below_minimum",
                evidence={
                    "threshold_name": "min-turnover",
                    "observed_value": "0",
                    "required_value": "100000",
                },
            )
        },
        negative_evidence=(
            NegativeEvidence(
                "negative-r016-1",
                "資料尚未完整",
                source_refs=(SOURCE_REF,),
                observed_at=datetime(2026, 9, 8, 6, tzinfo=timezone.utc),
                details={"missing": "turnover"},
            ),
        ),
        liquidity=LiquidityAssessment(
            acceptable=False,
            reasons=("liquidity_below_minimum",),
            missing_data=("turnover",),
            observations={"turnover_twd": Decimal("0")},
        ),
    )
    request = Request(as_of_date=as_of_date, profile_ref=profile_ref)
    context = Context(
        as_of_date=as_of_date,
        created_at=datetime(2026, 9, 8, 7, tzinfo=timezone.utc),
        decision_at=datetime(2026, 9, 8, 7, tzinfo=timezone.utc),
        source_refs=(SOURCE_REF,),
        profile_ref=profile_ref,
        result_config_snapshot=config_snapshot,
        warnings=("source_snapshot_saved",),
    )
    return RecommendationExecution(
        result_id=result_id,
        request=request,
        context=context,
        status=ExecutionStatus.COMPLETED,
        decision=DecisionBatch(items=(item,), assessments=(excluded,), regime="Trend"),
        quality=QualityReport(QualityStatus.DEGRADED, warnings=("saved_quality_warning",)),
    )


def test_canonical_saved_result_projects_through_r016_consumers_without_mutation(tmp_path: Path) -> None:
    config, queries, artifact_path = _stack(tmp_path)
    before = artifact_path.read_bytes()
    before_hash = "sha256:" + hashlib.sha256(before).hexdigest()
    read_model = queries.get(RESULT_ID)
    assert read_model is not None
    assert read_model.execution is not None
    assert read_model.integrity_basis == "canonical_payload_and_index_verified"
    assert read_model.raw_artifact_sha256 == before_hash

    watchlist = WatchlistAnalysisService(config, queries=queries).fetch("2330", RESULT_ID, AS_OF_DATE)
    assert watchlist.status == "saved"
    assert watchlist.result_id == RESULT_ID
    assert watchlist.analysis_date == AS_OF_DATE.isoformat()
    assert watchlist.score == "75"
    assert watchlist.reasons == "均線向上"
    assert watchlist.source_id == "synthetic-provider"
    assert watchlist.source_snapshot_id == "snapshot-r016"
    assert watchlist.source_snapshot_hash == ""

    desk = SavedRecommendationDeskProvider(config, queries=queries).fetch(AS_OF_DATE)
    assert desk is not None
    assert desk.result_id == RESULT_ID
    assert desk.profile_id == "balanced-synthetic"
    assert desk.stock_codes == ("2330",)
    assert desk.quality.value == "degraded"
    assert "saved_quality_warning" in desk.warnings
    assert SavedRecommendationDeskProvider(config, queries=queries).fetch(date(2026, 9, 7)) is None

    advice = AdviceComposer(AdvicePolicy()).compose(
        recommendations=read_model,
        portfolio_result=None,
        evidence_quality="OBSERVED",
        decision_date=AS_OF_DATE,
        data_as_of_date=AS_OF_DATE,
        mode=AdviceMode.GUIDED,
    )
    assert len(advice.recommendations) == 1
    assert advice.recommendations[0].stock_code == "2330"
    assert advice.recommendations[0].why_reasons == ("均線向上",)
    assert advice.recommendations[0].source_trace[:2] == ("RecommendationExecution", RESULT_ID)

    imported = RecommendationEvidenceImporter(queries).collect(
        EvidenceCaptureRequest(source="recommendation", result_id=RESULT_ID)
    )
    assert imported.decision_date == AS_OF_DATE.isoformat()
    included = next(row for row in imported.event_payloads if row["event_family"] == "recommendation")
    screening = next(row for row in imported.event_payloads if row["event_family"] == "screening_matrix")
    negative = next(row for row in imported.event_payloads if row["event_family"] == "recommendation_exclusion")
    liquidity = [
        row for row in imported.event_payloads
        if row["source_type"] == "recommendation_result_liquidity_gate"
    ]
    assert included["source_id"] == RESULT_ID
    assert included["symbol"] == "2330"
    assert included["profile_id"] == "balanced-synthetic"
    assert screening["symbol"] == "1101"
    assert screening["source_id"] == RESULT_ID
    assert screening["reason_codes"] == ("turnover_below_minimum",)
    assert negative["metadata"]["evidence_id"] == "negative-r016-1"
    assert negative["metadata"]["source_refs"][0]["snapshot_id"] == "snapshot-r016"
    assert len(liquidity) == 1
    assert liquidity[0]["metadata"]["missing_data"] == ("turnover",)

    replay = HistoricalEvidenceReplayService(config)
    assert replay._select_recommendation_result_id(AS_OF_DATE.isoformat(), config) == RESULT_ID
    assert replay._select_recommendation_result_id("2026-09-07", config) is None
    assert artifact_path.read_bytes() == before


def test_saved_result_missing_cutoff_and_unsupported_execution_fail_closed() -> None:
    missing_cutoff = _execution(result_id="r016-no-asof", as_of_date=None)
    missing_cutoff_model = RecommendationExecutionReadModel(
        execution=missing_cutoff,
        label="missing cutoff",
        notes="",
        persisted_at=None,
        payload_hash=None,
        artifact_location="synthetic",
    )

    class OneResultQueries:
        def __init__(self, model: RecommendationExecutionReadModel) -> None:
            self.model = model

        def get(self, result_id: str) -> RecommendationExecutionReadModel | None:
            return self.model if result_id == self.model.result_id else None

        def list(self) -> tuple[RecommendationExecutionReadModel, ...]:
            return (self.model,)

    queries = OneResultQueries(missing_cutoff_model)
    config = SimpleNamespace(output_root=Path("unused-r016-test-root"))
    watchlist = WatchlistAnalysisService(config, queries=queries).fetch(
        "2330", "r016-no-asof", AS_OF_DATE
    )
    assert watchlist.status == "unavailable"
    assert "分析日期缺失" in watchlist.message
    imported = RecommendationEvidenceImporter(queries).collect(
        EvidenceCaptureRequest(source="recommendation", result_id="r016-no-asof")
    )
    assert imported.events_seen == 0
    assert imported.diagnostics_by_code == {"source_missing_as_of_date": 1}

    failed = RecommendationExecution(
        result_id="r016-failed",
        request=Request(as_of_date=AS_OF_DATE),
        context=Context(as_of_date=AS_OF_DATE),
        status=ExecutionStatus.FAILED,
        failure_reason="synthetic failure",
    )
    failed_model = RecommendationExecutionReadModel(
        execution=failed,
        label="failed",
        notes="",
        persisted_at=None,
        payload_hash=None,
        artifact_location="synthetic",
    )
    failed_queries = OneResultQueries(failed_model)
    failed_watchlist = WatchlistAnalysisService(config, queries=failed_queries).fetch(
        "2330", "r016-failed", AS_OF_DATE
    )
    assert failed_watchlist.status == "unavailable"
    assert "沒有 completed 決策資料" in failed_watchlist.message
    failed_import = RecommendationEvidenceImporter(failed_queries).collect(
        EvidenceCaptureRequest(source="recommendation", result_id="r016-failed")
    )
    assert failed_import.events_seen == 0
    assert failed_import.diagnostics_by_code == {"source_unsupported_execution": 1}


def test_latest_saved_selection_preserves_single_namespace_order_and_compares_mixed_aware_clocks() -> None:
    canonical_first = RecommendationExecutionReadModel(
        execution=_execution(result_id="canonical-first"),
        label="first",
        notes="",
        persisted_at=datetime(2026, 9, 8, 7, tzinfo=timezone.utc),
        payload_hash=None,
        artifact_location="first",
    )
    canonical_second = RecommendationExecutionReadModel(
        execution=_execution(result_id="canonical-second"),
        label="second",
        notes="",
        persisted_at=datetime(2026, 9, 8, 8, tzinfo=timezone.utc),
        payload_hash=None,
        artifact_location="second",
    )
    legacy_first = RecommendationExecutionReadModel(
        execution=None,
        legacy_result=SimpleNamespace(result_id="legacy-first"),  # type: ignore[arg-type]
        label="legacy first",
        notes="",
        persisted_at=datetime(2026, 9, 8, 7, tzinfo=timezone.utc),
        payload_hash=None,
        artifact_location="legacy-first",
    )
    legacy_second = RecommendationExecutionReadModel(
        execution=None,
        legacy_result=SimpleNamespace(result_id="legacy-second"),  # type: ignore[arg-type]
        label="legacy second",
        notes="",
        persisted_at=datetime(2026, 9, 8, 8, tzinfo=timezone.utc),
        payload_hash=None,
        artifact_location="legacy-second",
    )

    selected_canonical, canonical_diagnostic = select_latest_saved_recommendation(
        (canonical_first, canonical_second)
    )
    selected_legacy, legacy_diagnostic = select_latest_saved_recommendation(
        (legacy_first, legacy_second)
    )
    selected_mixed, mixed_diagnostic = select_latest_saved_recommendation(
        (canonical_first, legacy_second)
    )

    assert selected_canonical is canonical_first
    assert canonical_diagnostic is None
    assert selected_legacy is legacy_first
    assert legacy_diagnostic is None
    assert selected_mixed is legacy_second
    assert mixed_diagnostic is None


def test_latest_saved_mixed_selection_ties_by_result_id_and_rejects_unknown_clocks() -> None:
    timestamp = datetime(2026, 9, 8, 7, tzinfo=timezone.utc)
    canonical_z = RecommendationExecutionReadModel(
        execution=_execution(result_id="z-canonical"),
        label="canonical",
        notes="",
        persisted_at=timestamp,
        payload_hash=None,
        artifact_location="canonical",
    )
    legacy_a = RecommendationExecutionReadModel(
        execution=None,
        legacy_result=SimpleNamespace(result_id="a-legacy"),  # type: ignore[arg-type]
        label="legacy",
        notes="",
        persisted_at=timestamp,
        payload_hash=None,
        artifact_location="legacy",
    )
    legacy_unknown = RecommendationExecutionReadModel(
        execution=None,
        legacy_result=SimpleNamespace(result_id="unknown-legacy"),  # type: ignore[arg-type]
        label="legacy unknown",
        notes="",
        persisted_at=None,
        payload_hash=None,
        artifact_location="legacy-unknown",
    )
    canonical_naive = RecommendationExecutionReadModel(
        execution=_execution(result_id="naive-canonical"),
        label="canonical naive",
        notes="",
        persisted_at=datetime(2026, 9, 8, 8),
        payload_hash=None,
        artifact_location="canonical-naive",
    )

    selected, diagnostic = select_latest_saved_recommendation((canonical_z, legacy_a))
    unknown, unknown_diagnostic = select_latest_saved_recommendation(
        (canonical_z, legacy_unknown)
    )
    naive, naive_diagnostic = select_latest_saved_recommendation(
        (canonical_z, canonical_naive, legacy_a)
    )

    assert selected is legacy_a
    assert diagnostic is None
    assert unknown is None
    assert unknown_diagnostic == "recommendation_latest_selection_ambiguous_clock"
    assert naive is None
    assert naive_diagnostic == "recommendation_latest_selection_ambiguous_clock"


def test_canonical_status_date_helpers_reject_noncompleted_or_decisionless_execution() -> None:
    result_config = SimpleNamespace(
        raw_result_config_json='{"scheduled_snapshot": true, "decision_date": "2026-09-08"}'
    )
    request_config = SimpleNamespace(raw_config_json='{"manual_qt_snapshot": true}')

    def model(status: ExecutionStatus, decision: object):
        execution = SimpleNamespace(
            result_id=f"status-{status.value}",
            status=status,
            decision=decision,
            request=SimpleNamespace(
                config_snapshot=request_config,
                as_of_date=AS_OF_DATE,
            ),
            context=SimpleNamespace(
                result_config_snapshot=result_config,
                as_of_date=AS_OF_DATE,
            ),
        )
        return RecommendationExecutionReadModel(
            execution=execution,  # type: ignore[arg-type]
            label="status fixture",
            notes="",
            persisted_at=datetime(2026, 9, 8, tzinfo=timezone.utc),
            payload_hash=None,
            artifact_location="status-fixture",
        )

    failed = model(ExecutionStatus.FAILED, None)
    cancelled = model(ExecutionStatus.CANCELLED, DecisionBatch(items=()))
    completed_without_decision = model(ExecutionStatus.COMPLETED, None)
    scheduled_date_mismatch = model(
        ExecutionStatus.COMPLETED,
        DecisionBatch(items=()),
    )
    assert scheduled_date_mismatch.execution is not None
    scheduled_date_mismatch.execution.context.as_of_date = date(2026, 9, 7)

    assert canonical_scheduled_decision_date(failed) is None
    assert canonical_manual_decision_date(failed) is None
    assert canonical_scheduled_decision_date(cancelled) is None
    assert canonical_manual_decision_date(cancelled) is None
    assert canonical_scheduled_decision_date(completed_without_decision) is None
    assert canonical_manual_decision_date(completed_without_decision) is None
    assert canonical_scheduled_decision_date(scheduled_date_mismatch) is None


def test_canonical_capture_projection_drives_evidence_source_coverage(tmp_path: Path) -> None:
    config, queries, artifact_path = _save_capture_execution(
        tmp_path,
        result_id="r016-coverage-canonical",
    )
    before = artifact_path.read_bytes()
    before_hash = hashlib.sha256(before).hexdigest()

    summary = EvidenceSourceCoverageService(
        config,
        db_path=tmp_path / "missing-evidence.sqlite",
        recommendation_queries=queries,
    ).inspect(result_id="r016-coverage-canonical").to_dict()

    assert summary["recommendation_persisted_available"] is True
    assert summary["recommendation_exclusion_payload_available"] is True
    assert summary["recommendation_screening_matrix_available"] is True
    assert summary["why_not_capture_ready"] is True
    assert summary["liquidity_gate_capture_ready"] is True
    assert summary["screening_matrix_capture_ready"] is True
    assert artifact_path.read_bytes() == before
    assert hashlib.sha256(artifact_path.read_bytes()).hexdigest() == before_hash


def test_canonical_capture_projection_drives_pre_v2_source_gap_readiness(tmp_path: Path) -> None:
    config, queries, artifact_path = _save_capture_execution(
        tmp_path,
        result_id="r016-pre-v2-canonical",
    )
    before = artifact_path.read_bytes()

    report = PreV2ReadinessService(
        config,
        evidence_db_path=tmp_path / "missing-evidence.sqlite",
        research_db_path=tmp_path / "missing-research.sqlite",
        recommendation_queries=queries,
    ).inspect(multi_day_record_path=tmp_path / "missing-multiday-record.md")
    source_gaps = next(item for item in report.items if item.item_id == "source_gaps")

    assert source_gaps.evidence["recommendation_persisted_available"] is True
    assert source_gaps.evidence["recommendation_exclusion_payload_available"] is True
    assert source_gaps.evidence["recommendation_screening_matrix_available"] is True
    assert source_gaps.evidence["why_not_capture_ready"] is True
    assert source_gaps.evidence["liquidity_gate_capture_ready"] is True
    assert source_gaps.evidence["screening_matrix_capture_ready"] is True
    assert artifact_path.read_bytes() == before


def test_evidence_importer_reports_query_integrity_failure_without_fallback() -> None:
    class FailingQueries:
        def get(self, _result_id: str) -> None:
            raise ExecutionArtifactIntegrityError("synthetic corrupt query result")

        def list(self) -> tuple[Any, ...]:
            raise ExecutionArtifactIntegrityError("synthetic corrupt query index")

    importer = RecommendationEvidenceImporter(FailingQueries())
    by_id = importer.collect(
        EvidenceCaptureRequest(source="recommendation", result_id="r016-corrupt")
    )
    latest = importer.collect(EvidenceCaptureRequest(source="recommendation"))

    assert by_id.events_seen == 0
    assert by_id.diagnostics_by_code == {
        "recommendation_query_failure:ExecutionArtifactIntegrityError": 1
    }
    assert latest.events_seen == 0
    assert latest.diagnostics_by_code == {
        "recommendation_query_failure:ExecutionArtifactIntegrityError": 1
    }
