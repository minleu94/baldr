from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
import hashlib
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from zoneinfo import ZoneInfo

import pytest

from app_module.dtos import RecommendationDTO, RecommendationResultDTO
from app_module.recommendation.contracts import (
    Context,
    ExecutionStatus,
    QualityReport,
    QualityStatus,
    RecommendationConfigSnapshot,
    RecommendationExecution,
    SnapshotCohort,
    SnapshotCohortCoverage,
    SnapshotCohortCoverageStatus,
    Request,
)
from app_module.recommendation.current_market_status_preflight import (
    CURRENT_MARKET_STATUS_POINTER_RELATIVE,
    CurrentMarketStatusPreflight,
    validate_current_market_status_evidence,
)
from app_module.recommendation.persistence import RecommendationExecutionPersistence
from app_module.recommendation.queries import (
    RecommendationExecutionQueries,
    RecommendationExecutionReadModel,
)
from data_module.result_artifact_store import ResultArtifactStore
from decision_module.recommendation.contracts import (
    CandidateAssessment,
    DecisionBatch,
    FilterOutcome,
)
from app_module.scheduled_evidence_status_service import ScheduledEvidenceStatusService
from data_module.current_market_status_observation import (
    MarketStatusEvidence,
    build_snapshot,
    sha256_bytes,
)


class _Config:
    def __init__(self, output_root: Path) -> None:
        self.output_root = output_root


class _QueryStub:
    def __init__(self, read_models: tuple[RecommendationExecutionReadModel, ...]) -> None:
        self._read_models = read_models

    def list(self) -> tuple[RecommendationExecutionReadModel, ...]:
        return self._read_models


def _write_minimal_scheduled_statuses(output_root: Path) -> None:
    for name in (
        "data_freshness",
        "recommendation_snapshot",
        "evidence_pipeline_dry_run",
    ):
        (output_root / "scheduled" / name).mkdir(parents=True, exist_ok=True)
    (output_root / "scheduled" / "data_freshness" / "latest_status.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "checked_at": "2026-09-07T05:00:00Z",
                "checks": {"daily_prices_latest_date": "20260907"},
            }
        ),
        encoding="utf-8",
    )
    (output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "checked_at": "2026-09-07T05:01:00Z",
                "decision_date": "2026-09-07",
                "result_id": "scheduled_rec_20260907_050100",
                "recommendations_count": 2,
                "writes_recommendation_result": True,
                "writes_evidence_db": False,
                "auto_trading": False,
                "lifecycle_action": False,
            }
        ),
        encoding="utf-8",
    )
    (output_root / "scheduled" / "evidence_pipeline_dry_run" / "latest_status.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "pipeline_overall_status": "passed",
                "checked_at": "2026-09-07T05:02:00Z",
                "decision_date": "2026-09-07",
                "dry_run": True,
                "exit_code": 0,
                "writes_evidence_db": False,
                "confirm": False,
                "pipeline_blocking_gaps": [],
            }
        ),
        encoding="utf-8",
    )


def test_scheduled_status_has_unknown_state_before_first_observation(tmp_path: Path) -> None:
    service = ScheduledEvidenceStatusService(
        _Config(tmp_path / "output"),
        clock=lambda: datetime(2026, 9, 7, 5, 0, tzinfo=timezone.utc),
    )

    status = service.load_latest()

    assert status.load_state == "unknown"
    assert status.is_stale is False
    assert status.last_good_loaded_at is None
    assert status.machine_status_classification == "unknown"
    assert any(item.startswith("status_missing:") for item in status.diagnostics)


def test_scheduled_status_keeps_partial_initial_read_unknown(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    _write_minimal_scheduled_statuses(output_root)
    (output_root / "scheduled" / "evidence_pipeline_dry_run" / "latest_status.json").unlink()
    service = ScheduledEvidenceStatusService(
        _Config(output_root),
        clock=lambda: datetime(2026, 9, 7, 5, 2, tzinfo=timezone.utc),
    )

    status = service.load_latest()

    assert status.load_state == "unknown"
    assert status.is_stale is False
    assert status.last_good_loaded_at is None
    assert status.machine_status_classification == "source_missing"
    assert "status_no_observation" not in status.diagnostics


def test_scheduled_status_keeps_optional_forward_gap_out_of_core_classification(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    _write_minimal_scheduled_statuses(output_root)

    status = ScheduledEvidenceStatusService(_Config(output_root)).load_latest()

    assert status.load_state == "current"
    assert status.forward_outcome_status == "missing"
    assert status.forward_outcome_status_path is None
    assert dict(status.machine_status_classifications)["forward_outcomes"] == "source_missing"
    assert status.machine_status_classification == "machine_verified"


def test_scheduled_status_preserves_last_known_good_when_latest_payload_breaks(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    _write_minimal_scheduled_statuses(output_root)
    clock_values = iter(
        (
            datetime(2026, 9, 7, 5, 3, tzinfo=timezone.utc),
            datetime(2026, 9, 7, 5, 4, tzinfo=timezone.utc),
            datetime(2026, 9, 7, 5, 5, tzinfo=timezone.utc),
        )
    )
    service = ScheduledEvidenceStatusService(_Config(output_root), clock=lambda: next(clock_values))

    first = service.load_latest()
    (output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json").write_text(
        "{broken-json",
        encoding="utf-8",
    )
    stale = service.load_latest()

    assert first.load_state == "current"
    assert first.last_good_loaded_at == "2026-09-07T05:03:00+00:00"
    assert stale.load_state == "stale"
    assert stale.is_stale is True
    assert stale.last_good_loaded_at == first.last_good_loaded_at
    assert stale.recommendation_result_id == first.recommendation_result_id
    assert stale.machine_status_classification == "stale"
    assert "last_known_good_preserved" in stale.diagnostics
    assert any(item.startswith("status_unreadable:") for item in stale.diagnostics)


def test_scheduled_status_recovers_to_current_after_payload_is_repaired(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    _write_minimal_scheduled_statuses(output_root)
    clock_values = iter(
        (
            datetime(2026, 9, 7, 5, 6, tzinfo=timezone.utc),
            datetime(2026, 9, 7, 5, 7, tzinfo=timezone.utc),
            datetime(2026, 9, 7, 5, 8, tzinfo=timezone.utc),
        )
    )
    service = ScheduledEvidenceStatusService(_Config(output_root), clock=lambda: next(clock_values))

    first = service.load_latest()
    (output_root / "scheduled" / "evidence_pipeline_dry_run" / "latest_status.json").unlink()
    stale = service.load_latest()
    _write_minimal_scheduled_statuses(output_root)
    recovered = service.load_latest()

    assert first.load_state == "current"
    assert stale.is_stale is True
    assert recovered.load_state == "current"
    assert recovered.is_stale is False
    assert recovered.last_good_loaded_at == "2026-09-07T05:08:00+00:00"


def test_scheduled_evidence_status_reads_latest_status_and_report(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    freshness_dir = output_root / "scheduled" / "data_freshness"
    dry_run_dir = output_root / "scheduled" / "evidence_pipeline_dry_run"
    recommendation_dir = output_root / "scheduled" / "recommendation_snapshot"
    report_dir = dry_run_dir / "reports"
    freshness_dir.mkdir(parents=True)
    recommendation_dir.mkdir(parents=True)
    report_dir.mkdir(parents=True)
    report_path = report_dir / "20260707_evidence_pipeline_dry_run.md"
    report_path.write_text(
        "# Evidence Pipeline Dry-run Report\n\n"
        "## Run Metadata\n"
        "- decision_date: 2026-07-07\n"
        "- dry_run: True\n"
        "- confirm: False\n",
        encoding="utf-8",
    )
    (freshness_dir / "latest_status.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "checked_at": "2026-07-07T05:00:01",
                "checks": {"daily_prices_latest_date": "20260707"},
                "warnings": [],
                "errors": [],
            }
        ),
        encoding="utf-8",
    )
    (dry_run_dir / "latest_status.json").write_text(
        json.dumps(
            {
                "status": "degraded",
                "pipeline_overall_status": "degraded",
                "checked_at": "2026-07-07T05:15:39",
                "decision_date": "2026-07-07",
                "dry_run": True,
                "exit_code": 0,
                "report_path": str(report_path),
                "pipeline_blocking_gaps": [],
                "pipeline_warnings_count": 7,
                "pipeline_warning_unique_count": 2,
                "pipeline_advisories_count": 3,
                "pipeline_advisory_unique_count": 2,
                "pipeline_advisory_top_counts": [
                    {"advisory": "portfolio_alerts_chip_estimated:2330", "count": 1},
                ],
                "pipeline_warning_top_counts": [
                    {"warning": "risk_prompt_source_quality:portfolio_alerts:estimated", "count": 4},
                    {"warning": "relative_strength_liquidity_skipped_symbols:1", "count": 3},
                ],
                "source_coverage_warnings": ["screening_matrix_missing"],
                "writes_evidence_db": False,
            }
        ),
        encoding="utf-8",
    )
    (report_dir / "20260706_evidence_pipeline_dry_run.md").write_text("older report", encoding="utf-8")
    (recommendation_dir / "latest_status.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "checked_at": "2026-07-07T05:10:01",
                "decision_date": "2026-07-07",
                "result_id": "scheduled_rec_20260707_051001",
                "recommendations_count": 12,
                "screening_matrix_rows": 200,
                "why_not_payload_rows": 188,
                "liquidity_gate_payload_rows": 9,
                "writes_recommendation_result": True,
                "writes_evidence_db": False,
                "auto_trading": False,
                "lifecycle_action": False,
                "confirm": False,
            }
        ),
        encoding="utf-8",
    )
    runs_dir = output_root / "recommendation" / "runs"
    runs_dir.mkdir(parents=True)
    read_models = (
        _legacy_read_model(
            "scheduled_rec_20260706_051001",
            decision_date="2026-07-06",
            persisted_at=datetime(2026, 7, 6, 5, 10, tzinfo=timezone.utc),
        ),
        _legacy_read_model(
            "scheduled_rec_20260707_051001",
            decision_date="2026-07-07",
            persisted_at=datetime(2026, 7, 7, 5, 10, tzinfo=timezone.utc),
        ),
    )

    status = ScheduledEvidenceStatusService(
        _Config(output_root), recommendation_queries=_QueryStub(read_models)
    ).load_latest()

    assert status.freshness_status == "passed"
    assert status.latest_data_date == "20260707"
    assert status.evidence_status == "degraded"
    assert status.pipeline_overall_status == "degraded"
    assert status.recommendation_status == "passed"
    assert status.recommendation_result_id == "scheduled_rec_20260707_051001"
    assert status.recommendations_count == 12
    assert status.screening_matrix_rows == 200
    assert status.writes_recommendation_result is True
    assert status.auto_trading is False
    assert status.lifecycle_action is False
    assert status.recommendation_snapshot_observed_days == 2
    assert status.evidence_dry_run_observed_days == 2
    assert status.scheduled_joint_observed_days == 2
    assert status.scheduled_joint_observed_dates == ("20260706", "20260707")
    assert status.decision_date == "2026-07-07"
    assert status.report_path == report_path
    assert status.report_exists is True
    assert status.writes_evidence_db is False
    assert status.source_coverage_warnings == ("screening_matrix_missing",)
    assert getattr(status, "pipeline_warnings_count", None) == 7
    assert getattr(status, "pipeline_warning_unique_count", None) == 2
    assert getattr(status, "pipeline_advisories_count", None) == 3
    assert getattr(status, "pipeline_advisory_unique_count", None) == 2
    assert getattr(status, "pipeline_advisory_top_counts", ()) == (
        ("portfolio_alerts_chip_estimated:2330", 1),
    )
    assert getattr(status, "pipeline_warning_top_counts", ()) == (
        ("risk_prompt_source_quality:portfolio_alerts:estimated", 4),
        ("relative_strength_liquidity_skipped_symbols:1", 3),
    )
    assert "Run Metadata" in status.report_preview


def test_scheduled_evidence_status_reads_forward_outcome_receipt(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    _write_minimal_scheduled_statuses(output_root)
    forward_dir = output_root / "scheduled" / "forward_outcomes"
    forward_dir.mkdir(parents=True)
    forward_path = forward_dir / "latest_status.json"
    forward_path.write_text(
        json.dumps(
            {
                "status": "passed_with_warnings",
                "checked_at": "2026-09-09T05:40:00+08:00",
                "run_id": "20260908T214000000000Z",
                "writes_evidence_db": True,
                "summary": {
                    "events_scanned": 2500,
                    "outcomes_written": 1820,
                    "pending_insufficient_future_data": 680,
                    "warnings_count": 4,
                },
                "blockers": [],
                "warnings": ["missing_benchmark"],
            }
        ),
        encoding="utf-8",
    )
    progress_dir = output_root / "scheduled" / "evidence_progress"
    progress_dir.mkdir(parents=True)
    progress_path = progress_dir / "latest_status.json"
    progress_path.write_text(
        json.dumps(
            {
                "schema_version": "scheduled-evidence-progress.v1",
                "status": "passed_with_warnings",
                "checked_at": "2026-09-09T05:40:00+08:00",
                "daily": {
                    "captures": {"decision_day_count": 2, "new_event_count": 0},
                    "maturity": {"ready": 0, "pending": 20, "missing": 0},
                },
                "weekly": {"capture_decision_day_count": 2},
                "no_new_data_alert": {
                    "alert": True,
                    "consecutive_no_new_data_days": 2,
                },
                "blockers": [],
                "warnings": [],
                "next_action": "wait",
            }
        ),
        encoding="utf-8",
    )

    status = ScheduledEvidenceStatusService(_Config(output_root)).load_latest()

    assert status.load_state == "current"
    assert status.forward_outcome_status == "passed_with_warnings"
    assert status.forward_outcome_run_id == "20260908T214000000000Z"
    assert status.forward_outcome_events_scanned == 2500
    assert status.forward_outcome_outcomes_written == 1820
    assert status.forward_outcome_pending == 680
    assert status.forward_outcome_warnings_count == 4
    assert status.forward_outcome_writes_evidence_db is True
    assert status.forward_outcome_status_path == forward_path
    assert status.evidence_progress_status == "passed_with_warnings"
    assert status.evidence_progress_daily == {
        "captures": {"decision_day_count": 2, "new_event_count": 0},
        "maturity": {"ready": 0, "pending": 20, "missing": 0},
    }
    assert status.evidence_progress_weekly == {"capture_decision_day_count": 2}
    assert status.evidence_progress_no_new_data_alert == {
        "alert": True,
        "consecutive_no_new_data_days": 2,
    }
    assert status.evidence_progress_status_path == progress_path
    assert "evidence_progress_no_new_data_consecutive" in status.evidence_progress_warnings
    assert status.has_production_write_risk is True
    assert dict(status.machine_status_classifications)["forward_outcomes"] == "machine_degraded"


def test_scheduled_status_projects_forward_health_blocker(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    _write_minimal_scheduled_statuses(output_root)
    forward_dir = output_root / "scheduled" / "forward_outcomes"
    forward_dir.mkdir(parents=True)
    (forward_dir / "latest_status.json").write_text(
        json.dumps(
            {
                "status": "passed_with_warnings",
                "checked_at": "2026-09-10T05:40:00+08:00",
                "summary": {"events_scanned": 0, "outcomes_written": 0},
                "health": {
                    "classification": "actionable_engineering_blocker",
                    "qualifying_event_count": 0,
                    "cohort_count": 0,
                    "blockers": ["events_missing_complete_cohort_identity"],
                    "warnings": [],
                    "blocking_reason": "events_missing_complete_cohort_identity",
                    "next_action": "repair producer",
                    "recovery_verification": {
                        "status": "required",
                        "checks": ["source_preflight.ready=true"],
                    },
                    "horizons": {"60": {"ready": 0, "pending": 0, "missing": 0}},
                },
            }
        ),
        encoding="utf-8",
    )

    status = ScheduledEvidenceStatusService(_Config(output_root)).load_latest()

    assert status.forward_health_classification == "actionable_engineering_blocker"
    assert status.forward_health_qualifying_event_count == 0
    assert status.forward_health_horizons == {
        "60": {"ready": 0, "pending": 0, "missing": 0}
    }
    assert status.forward_health_blocking_reason == "events_missing_complete_cohort_identity"
    assert status.forward_health_next_action == "repair producer"
    assert status.forward_health_recovery_verification == {
        "status": "required",
        "checks": ["source_preflight.ready=true"],
    }
    assert dict(status.machine_status_classifications)["forward_outcomes"] == "invalid_evidence"
    assert status.machine_status_classification == "invalid_evidence"


def test_scheduled_evidence_status_uses_same_day_manual_recommendation_when_scheduled_status_missing(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    freshness_dir = output_root / "scheduled" / "data_freshness"
    dry_run_dir = output_root / "scheduled" / "evidence_pipeline_dry_run"
    runs_dir = output_root / "recommendation" / "runs"
    freshness_dir.mkdir(parents=True)
    dry_run_dir.mkdir(parents=True)
    runs_dir.mkdir(parents=True)

    (freshness_dir / "latest_status.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "checked_at": "2026-07-07T05:00:01",
                "checks": {"daily_prices_latest_date": "20260707"},
                "warnings": [],
                "errors": [],
            }
        ),
        encoding="utf-8",
    )
    (dry_run_dir / "latest_status.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "checked_at": "2026-07-07T05:15:39",
                "decision_date": "2026-07-07",
                "dry_run": True,
                "exit_code": 0,
                "pipeline_blocking_gaps": [],
                "writes_evidence_db": False,
                "confirm": False,
            }
        ),
        encoding="utf-8",
    )
    manual_path = runs_dir / "rec_20260707_113744.json"
    manual_path.write_text(
        json.dumps(
            {
                "result_id": "rec_20260707_113744",
                "created_at": "2026-07-07T11:37:44.761292",
                "recommendations": [{"stock_code": "1409"}, {"stock_code": "1466"}],
                "screening_matrix_json": [{"stock_code": "1409"}],
                "why_not_payload_json": [{"stock_code": "2330"}],
                "liquidity_gate_payload_json": [],
                "exclusion_quality": "observed",
                "exclusion_warnings_json": ["screening_matrix_persisted_v1"],
            }
        ),
        encoding="utf-8",
    )
    before_manual_bytes = manual_path.read_bytes()
    read_model = _legacy_read_model(
        "rec_20260707_113744",
        decision_date="2026-07-07",
        persisted_at=None,
        recommendations_count=2,
        created_at="2026-07-07T11:37:44.761292",
    )

    status = ScheduledEvidenceStatusService(
        _Config(output_root), recommendation_queries=_QueryStub((read_model,))
    ).load_latest()

    assert status.recommendation_status == "manual_observed"
    assert status.recommendation_source == "manual_result"
    assert status.manual_recommendation_result_path == manual_path
    assert status.recommendation_result_id == "rec_20260707_113744"
    assert status.recommendation_checked_at == "2026-07-07T11:37:44.761292"
    assert status.recommendations_count == 2
    assert status.screening_matrix_rows == 1
    assert status.why_not_payload_rows == 1
    assert status.writes_recommendation_result is True
    assert status.writes_evidence_db is False
    assert status.confirm is False
    assert status.recommendation_snapshot_observed_days == 0
    assert status.manual_recommendation_observed_days == 1
    assert status.scheduled_joint_observed_days == 0
    assert manual_path.read_bytes() == before_manual_bytes


def test_scheduled_status_uses_only_verified_same_day_canonical_qt_manual_provenance(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    _write_minimal_scheduled_statuses(output_root)
    recommendation_status_path = (
        output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json"
    )
    recommendation_status_path.unlink()
    evidence_path = output_root / "scheduled" / "evidence_pipeline_dry_run" / "latest_status.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["decision_date"] = "2026-09-08"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    runs_dir = output_root / "recommendation" / "runs"
    store = ResultArtifactStore(
        artifact_root=runs_dir / "execution_artifacts",
        database_path=runs_dir / "recommendation_runs.db",
    )
    persistence = RecommendationExecutionPersistence(store)

    def save_result(result_id: str, *, manual: bool, hour: int) -> Path:
        raw_config = json.dumps(
            {"manual_qt_snapshot": True} if manual else {"profile": "unmarked"},
            sort_keys=True,
            separators=(",", ":"),
        )
        config_snapshot = RecommendationConfigSnapshot(
            raw_config_json=raw_config,
            raw_json_sha256="sha256:" + hashlib.sha256(raw_config.encode()).hexdigest(),
        )
        execution = RecommendationExecution(
            result_id=result_id,
            request=Request(
                as_of_date=date(2026, 9, 8),
                config_snapshot=config_snapshot,
            ),
            context=Context(
                as_of_date=date(2026, 9, 8),
                created_at=datetime(2026, 9, 8, hour, tzinfo=timezone.utc),
            ),
            status=ExecutionStatus.COMPLETED,
            decision=DecisionBatch(items=()),
            quality=QualityReport(QualityStatus.COMPLETE),
        )
        receipt = persistence.save(
            execution,
            label=result_id,
            now=lambda: datetime(2026, 9, 8, hour, tzinfo=timezone.utc),
        )
        assert receipt.artifact_location is not None
        return store.artifact_root / receipt.artifact_location

    manual_artifact = save_result("canonical-qt-manual", manual=True, hour=8)
    unmarked_artifact = save_result("canonical-unmarked", manual=False, hour=9)
    before_manual = manual_artifact.read_bytes()
    before_unmarked = unmarked_artifact.read_bytes()
    queries = RecommendationExecutionQueries(persistence)

    status = ScheduledEvidenceStatusService(
        _Config(output_root),
        recommendation_queries=queries,
    ).load_latest()

    # The manual result is observable, while the missing scheduled status keeps
    # the overall loader in its existing conservative unknown state.
    assert status.load_state == "unknown"
    assert status.recommendation_status == "manual_observed"
    assert status.recommendation_source == "canonical_manual_result"
    assert status.recommendation_result_id == "canonical-qt-manual"
    assert status.manual_recommendation_observed_days == 1
    assert status.recommendation_snapshot_observed_days == 0
    assert status.recommendations_count == 0
    assert status.writes_recommendation_result is True
    assert any(
        item == "canonical_manual_recommendation_result_observed:canonical-qt-manual"
        for item in status.diagnostics
    )
    assert manual_artifact.read_bytes() == before_manual
    assert unmarked_artifact.read_bytes() == before_unmarked


def _legacy_read_model(
    result_id: str,
    *,
    decision_date: str,
    persisted_at: datetime | None,
    recommendations_count: int = 0,
    created_at: str | None = None,
) -> RecommendationExecutionReadModel:
    recommendation = RecommendationDTO(
        stock_code="2330",
        stock_name="合成標的",
        close_price=100,
        price_change=0,
        total_score=75,
        indicator_score=25,
        pattern_score=20,
        volume_score=30,
        recommendation_reasons="synthetic",
        industry="synthetic",
        regime_match=True,
    )
    legacy = RecommendationResultDTO(
        result_id=result_id,
        result_name=result_id,
        config={},
        recommendations=[recommendation] * recommendations_count,
        created_at=(
            created_at
            if created_at is not None
            else persisted_at.isoformat() if persisted_at is not None else None
        ),
        screening_matrix_json=[{"stock_code": "2330"}],
        why_not_payload_json=[{"stock_code": "1101"}],
        liquidity_gate_payload_json=[],
        exclusion_quality="observed",
        exclusion_warnings_json=["synthetic_verified_legacy"],
        run_context={"as_of_date": decision_date},
    )
    return RecommendationExecutionReadModel(
        execution=None,
        label=result_id,
        notes="",
        persisted_at=persisted_at,
        payload_hash=None,
        artifact_location=f"{result_id}.json",
        legacy_result=legacy,
        raw_artifact_sha256="sha256:synthetic",
        integrity_basis="legacy_read_time_hash_only",
        ml_read_status="legacy_saved_fields",
    )


def _canonical_manual_read_model(
    result_id: str,
    *,
    decision_date: date,
    persisted_at: datetime | None,
) -> RecommendationExecutionReadModel:
    execution = SimpleNamespace(
        result_id=result_id,
        status=ExecutionStatus.COMPLETED,
        decision=DecisionBatch(items=()),
        request=SimpleNamespace(
            config_snapshot=SimpleNamespace(
                raw_config_json='{"manual_qt_snapshot": true}'
            ),
            as_of_date=decision_date,
        ),
        context=SimpleNamespace(
            as_of_date=decision_date,
            result_config_snapshot=None,
            created_at=persisted_at,
            warnings=(),
            source_refs=(),
            profile_ref=None,
        ),
        events=(),
        quality=SimpleNamespace(status=QualityStatus.COMPLETE, warnings=()),
    )
    return RecommendationExecutionReadModel(
        execution=execution,  # type: ignore[arg-type]
        label=result_id,
        notes="",
        persisted_at=persisted_at,
        payload_hash=None,
        artifact_location=result_id,
    )


def test_unverified_recommendation_filenames_do_not_add_observed_dates(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    _write_minimal_scheduled_statuses(output_root)
    runs_dir = output_root / "recommendation" / "runs"
    runs_dir.mkdir(parents=True)
    (runs_dir / "rec_20260908_010101.json").write_text(
        "{invalid",
        encoding="utf-8",
    )
    (runs_dir / "scheduled_rec_20260909_010101.json").write_text(
        json.dumps({"result_id": "different-result-id", "as_of_date": "2026-09-09"}),
        encoding="utf-8",
    )
    symlink_path = runs_dir / "rec_20260910_010101.json"
    try:
        symlink_path.symlink_to(runs_dir / "rec_20260908_010101.json")
    except (OSError, NotImplementedError):
        symlink_created = False
    else:
        symlink_created = True

    status = ScheduledEvidenceStatusService(_Config(output_root)).load_latest()

    assert status.recommendation_snapshot_observed_days == 1
    assert status.manual_recommendation_observed_days == 0
    assert status.scheduled_joint_observed_dates == ("20260907",)
    assert any(
        item.startswith("recommendation_legacy_candidate_query_failure:")
        for item in status.diagnostics
    )
    if symlink_created:
        assert symlink_path.is_symlink()


def test_unindexed_manual_result_uses_verified_exact_payload_and_preserves_bytes(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    _write_minimal_scheduled_statuses(output_root)
    (output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json").unlink()
    evidence_path = output_root / "scheduled" / "evidence_pipeline_dry_run" / "latest_status.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["decision_date"] = "2026-09-08"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    runs_dir = output_root / "recommendation" / "runs"
    runs_dir.mkdir(parents=True)
    result_id = "rec_20260908_113744"
    manual_path = runs_dir / f"{result_id}.json"
    manual_payload = {
        "result_id": result_id,
        "created_at": "2026-09-08T11:37:44+08:00",
        "run_context": {
            "as_of_date": "2026-09-08",
            "data_as_of_date": "2026-09-07",
        },
        "recommendations": [{"stock_code": "1409"}, {"stock_code": "1466"}],
        "screening_matrix_json": [{"stock_code": "1409"}],
        "why_not_payload_json": [{"stock_code": "2330"}],
        "liquidity_gate_payload_json": [],
        "exclusion_quality": "observed",
        "exclusion_warnings_json": ["synthetic_saved_capture"],
        "opaque_root": {"keep": [1, {"field": "value"}]},
    }
    manual_path.write_text(json.dumps(manual_payload), encoding="utf-8")
    before = manual_path.read_bytes()
    before_hash = hashlib.sha256(before).hexdigest()

    status = ScheduledEvidenceStatusService(_Config(output_root)).load_latest()

    assert status.recommendation_status == "manual_observed"
    assert status.recommendation_source == "manual_result"
    assert status.recommendation_result_id == result_id
    assert status.manual_recommendation_result_path == manual_path.resolve()
    assert status.recommendation_checked_at == manual_payload["created_at"]
    assert status.recommendations_count == 2
    assert status.screening_matrix_rows == 1
    assert status.why_not_payload_rows == 1
    assert status.writes_recommendation_result is True
    assert status.manual_recommendation_observed_days == 1
    assert any(
        f"legacy_read_time_hash_only:{result_id}:sha256:{before_hash}" in item
        for item in status.diagnostics
    )
    assert manual_path.read_bytes() == before


def test_verified_unindexed_scheduled_file_adds_content_checked_inventory_date(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    _write_minimal_scheduled_statuses(output_root)
    runs_dir = output_root / "recommendation" / "runs"
    runs_dir.mkdir(parents=True)
    result_id = "scheduled_rec_20260906_051001"
    path = runs_dir / f"{result_id}.json"
    payload = {
        "result_id": result_id,
        "created_at": "2026-09-06T05:10:01+00:00",
        "run_context": {"as_of_date": "2026-09-06"},
        "recommendations": [{"stock_code": "2330"}],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    before = path.read_bytes()

    status = ScheduledEvidenceStatusService(_Config(output_root)).load_latest()

    assert status.recommendation_snapshot_observed_days == 2
    assert status.manual_recommendation_observed_days == 0
    assert path.read_bytes() == before


def test_unindexed_file_reusing_canonical_result_id_is_ambiguous_and_excluded(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    _write_minimal_scheduled_statuses(output_root)
    (output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json").unlink()
    evidence_path = output_root / "scheduled" / "evidence_pipeline_dry_run" / "latest_status.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["decision_date"] = "2026-09-08"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    result_id = "rec_20260908_010000"
    runs_dir = output_root / "recommendation" / "runs"
    store = ResultArtifactStore(
        artifact_root=runs_dir / "execution_artifacts",
        database_path=runs_dir / "recommendation_runs.db",
    )
    persistence = RecommendationExecutionPersistence(store)
    raw_config = '{"manual_qt_snapshot": true}'
    request_snapshot = RecommendationConfigSnapshot(
        raw_config_json=raw_config,
        raw_json_sha256="sha256:" + hashlib.sha256(raw_config.encode()).hexdigest(),
    )
    execution = RecommendationExecution(
        result_id=result_id,
        request=Request(as_of_date=date(2026, 9, 8), config_snapshot=request_snapshot),
        context=Context(
            as_of_date=date(2026, 9, 8),
            created_at=datetime(2026, 9, 8, 10, tzinfo=timezone.utc),
        ),
        status=ExecutionStatus.COMPLETED,
        decision=DecisionBatch(items=()),
        quality=QualityReport(QualityStatus.COMPLETE),
    )
    persistence.save(execution, label="canonical manual")
    runs_dir.mkdir(parents=True, exist_ok=True)
    conflicting_path = runs_dir / f"{result_id}.json"
    conflicting_payload = {
        "result_id": result_id,
        "created_at": "2026-09-08T11:00:00+00:00",
        "run_context": {"as_of_date": "2026-09-08"},
        "recommendations": [{"stock_code": "2330"}],
    }
    conflicting_path.write_text(json.dumps(conflicting_payload), encoding="utf-8")
    before = conflicting_path.read_bytes()

    status = ScheduledEvidenceStatusService(_Config(output_root)).load_latest()

    assert status.recommendation_status == "missing"
    assert status.recommendation_result_id is None
    assert status.manual_recommendation_observed_days == 0
    assert any(
        item.startswith("recommendation_legacy_canonical_identity_collision:")
        for item in status.diagnostics
    )
    assert conflicting_path.read_bytes() == before


def test_same_day_mixed_manual_candidates_use_aware_latest_clock_or_fail_closed(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    _write_minimal_scheduled_statuses(output_root)
    (output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json").unlink()
    evidence_path = output_root / "scheduled" / "evidence_pipeline_dry_run" / "latest_status.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["decision_date"] = "2026-09-08"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    legacy = _legacy_read_model(
        "rec_20260908_120000",
        decision_date="2026-09-08",
        persisted_at=datetime(2026, 9, 8, 12, tzinfo=timezone.utc),
        recommendations_count=3,
    )
    canonical = _canonical_manual_read_model(
        "canonical-manual-1000",
        decision_date=date(2026, 9, 8),
        persisted_at=datetime(2026, 9, 8, 10, tzinfo=timezone.utc),
    )

    selected_legacy = ScheduledEvidenceStatusService(
        _Config(output_root),
        recommendation_queries=_QueryStub((legacy, canonical)),
    ).load_latest()
    assert selected_legacy.recommendation_status == "manual_observed"
    assert selected_legacy.recommendation_source == "manual_result"
    assert selected_legacy.recommendation_result_id == legacy.result_id
    assert selected_legacy.manual_recommendation_result_path == (
        output_root / "recommendation" / "runs" / f"{legacy.result_id}.json"
    )

    unknown_clock_legacy = _legacy_read_model(
        "rec_20260908_120001",
        decision_date="2026-09-08",
        persisted_at=None,
    )
    ambiguous = ScheduledEvidenceStatusService(
        _Config(output_root),
        recommendation_queries=_QueryStub((unknown_clock_legacy, canonical)),
    ).load_latest()
    assert ambiguous.recommendation_status == "missing"
    assert ambiguous.recommendation_result_id is None
    assert "recommendation_latest_selection_ambiguous_clock" in ambiguous.diagnostics


@pytest.mark.parametrize(
    ("legacy_created_at", "expected_status", "expected_result_id"),
    (
        (
            "2026-09-08T12:00:00+00:00",
            "manual_observed",
            "rec_20260908_120000",
        ),
        (
            "2026-09-08T12:00:00",
            "missing",
            None,
        ),
    ),
)
def test_unindexed_manual_mixed_clock_selection_is_utc_or_ambiguous(
    tmp_path: Path,
    legacy_created_at: str,
    expected_status: str,
    expected_result_id: str | None,
) -> None:
    output_root = tmp_path / "output"
    _write_minimal_scheduled_statuses(output_root)
    (output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json").unlink()
    evidence_path = output_root / "scheduled" / "evidence_pipeline_dry_run" / "latest_status.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["decision_date"] = "2026-09-08"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    runs_dir = output_root / "recommendation" / "runs"
    store = ResultArtifactStore(
        artifact_root=runs_dir / "execution_artifacts",
        database_path=runs_dir / "recommendation_runs.db",
    )
    persistence = RecommendationExecutionPersistence(store)
    raw_config = '{"manual_qt_snapshot": true}'
    request_snapshot = RecommendationConfigSnapshot(
        raw_config_json=raw_config,
        raw_json_sha256="sha256:" + hashlib.sha256(raw_config.encode()).hexdigest(),
    )
    canonical_execution = RecommendationExecution(
        result_id="canonical-manual-1000",
        request=Request(
            as_of_date=date(2026, 9, 8),
            config_snapshot=request_snapshot,
        ),
        context=Context(
            as_of_date=date(2026, 9, 8),
            created_at=datetime(2026, 9, 8, 10, tzinfo=timezone.utc),
        ),
        status=ExecutionStatus.COMPLETED,
        decision=DecisionBatch(items=()),
        quality=QualityReport(QualityStatus.COMPLETE),
    )
    persistence.save(
        canonical_execution,
        label="canonical manual",
        now=lambda: datetime(2026, 9, 8, 10, tzinfo=timezone.utc),
    )
    legacy_id = "rec_20260908_120000"
    manual_path = runs_dir / f"{legacy_id}.json"
    manual_path.parent.mkdir(parents=True, exist_ok=True)
    manual_path.write_text(
        json.dumps(
            {
                "result_id": legacy_id,
                "created_at": legacy_created_at,
                "run_context": {"as_of_date": "2026-09-08"},
                "recommendations": [{"stock_code": "2330"}],
            }
        ),
        encoding="utf-8",
    )

    status = ScheduledEvidenceStatusService(_Config(output_root)).load_latest()

    assert status.recommendation_status == expected_status
    assert status.recommendation_result_id == expected_result_id
    if expected_result_id is None:
        assert "recommendation_latest_selection_ambiguous_clock" in status.diagnostics


def test_scheduled_recommendation_inventory_requires_saved_scheduled_marker(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    _write_minimal_scheduled_statuses(output_root)

    def read_model(result_id: str, *, scheduled: bool, decision_date: str):
        raw_result_config = json.dumps(
            {
                "scheduled_snapshot": scheduled,
                "decision_date": decision_date,
            }
        )
        execution = SimpleNamespace(
            result_id=result_id,
            status=ExecutionStatus.COMPLETED,
            decision=DecisionBatch(items=()),
            context=SimpleNamespace(
                as_of_date=date.fromisoformat(decision_date),
                result_config_snapshot=SimpleNamespace(
                    raw_result_config_json=raw_result_config
                ),
            ),
            request=SimpleNamespace(
                as_of_date=date.fromisoformat(decision_date),
                config_snapshot=SimpleNamespace(raw_config_json='{"manual_qt_snapshot": false}'),
            ),
        )
        return RecommendationExecutionReadModel(
            execution=execution,  # type: ignore[arg-type]
            label=result_id,
            notes="",
            persisted_at=datetime(2026, 9, 8, tzinfo=timezone.utc),
            payload_hash=None,
            artifact_location=result_id,
        )

    scheduled_model = read_model(
        "canonical-scheduled",
        scheduled=True,
        decision_date="2026-09-06",
    )
    unmarked_model = read_model(
        "canonical-unmarked",
        scheduled=False,
        decision_date="2026-09-05",
    )

    class QueryStub:
        def list(self):
            return (scheduled_model, unmarked_model)

    status = ScheduledEvidenceStatusService(
        _Config(output_root),
        recommendation_queries=QueryStub(),
    ).load_latest()

    assert status.recommendation_snapshot_observed_days == 2
    assert status.manual_recommendation_observed_days == 0
    assert status.recommendation_result_id == "scheduled_rec_20260907_050100"


def _classification_test_cohort(*, include_current_delisted: bool = False) -> SnapshotCohort:
    requested: tuple[str, ...] = ("0050", "0066", "1101", "2330", "2603", "2881", "6488")
    eligible = ("0050", "0066")
    missing = ("1101",)
    degraded = ("0066", "2330", "2603", "6488")
    excluded: tuple[str, ...] = ("2881",)
    coverage_rows: dict[str, dict[str, object]] = {
        "0066": {
            "status": "skipped",
            "quality": "degraded",
            "stage": "strategy_evaluation",
            "reason_codes": ["liquidity_volume_ratio_below_min"],
            "warnings": [],
        },
        "0050": {
            "status": "pass",
            "quality": "observed",
            "stage": "final_selection",
            "reason_codes": ["recommendation_selected"],
            "warnings": [],
        },
        "1101": {
            "status": "missing",
            "quality": "missing",
            "stage": "source_fetch",
            "reason_codes": ["source_unavailable"],
            "warnings": [],
        },
        "2330": {
            "status": "skipped",
            "quality": "degraded",
            "stage": "strategy_evaluation",
            "reason_codes": ["liquidity_volume_ratio_below_min"],
            "warnings": [],
        },
        "2603": {
            "status": "skipped",
            "quality": "degraded",
            "stage": "strategy_evaluation",
            "reason_codes": ["strategy_filter_no_signal"],
            "warnings": ["source_quality_warning"],
        },
        "2881": {
            "status": "excluded",
            "quality": "observed",
            "stage": "final_selection",
            "reason_codes": ["not_selected"],
            "warnings": [],
        },
        "6488": {
            "status": "skipped",
            "quality": "degraded",
            "stage": "strategy_evaluation",
            "reason_codes": ["unrecognized_future_reason"],
            "warnings": [],
        },
    }
    if include_current_delisted:
        requested = tuple(sorted((*requested, "4130")))
        excluded = tuple(sorted((*excluded, "4130")))
        coverage_rows["4130"] = {
            "status": "fail",
            "quality": "observed",
            "stage": "current_market_status_gate",
            "reason_codes": ["official_delisted"],
            "warnings": [],
        }
    definitions = {
        "eligible_definition": "final scheduled recommendation DTO rows",
        "missing_definition": "screening rows with quality=missing; same-day retry candidates",
        "degraded_definition": "screening rows with quality=degraded; visible but not source-missing",
        "excluded_definition": "requested rows not selected and not missing/degraded",
    }
    body = {
        "schema_version": "scheduled-recommendation-snapshot-cohort.v1",
        "requested_symbols": list(requested),
        "eligible_symbols": list(eligible),
        "missing_symbols": list(missing),
        "degraded_symbols": list(degraded),
        "excluded_symbols": list(excluded),
        "requested_count": len(requested),
        "eligible_count": len(eligible),
        "missing_count": len(missing),
        "degraded_count": len(degraded),
        "excluded_count": len(excluded),
        "coverage_status": SnapshotCohortCoverageStatus.PARTIAL.value,
        "coverage_by_symbol": coverage_rows,
        **definitions,
    }
    cohort_hash = "sha256:" + hashlib.sha256(
        json.dumps(
            body,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return SnapshotCohort(
        cohort_hash=cohort_hash,
        requested_symbols=requested,
        eligible_symbols=eligible,
        missing_symbols=missing,
        degraded_symbols=degraded,
        excluded_symbols=excluded,
        requested_count=len(requested),
        eligible_count=len(eligible),
        missing_count=len(missing),
        degraded_count=len(degraded),
        excluded_count=len(excluded),
        coverage_status=SnapshotCohortCoverageStatus.PARTIAL,
        coverage_by_symbol={
            symbol: SnapshotCohortCoverage(
                status=cast(str | None, row.get("status")),
                quality=cast(str | None, row.get("quality")),
                stage=cast(str | None, row.get("stage")),
                reason_codes=tuple(cast(list[str], row.get("reason_codes", []))),
                warnings=tuple(cast(list[str], row.get("warnings", []))),
            )
            for symbol, row in coverage_rows.items()
        },
    )


def test_scheduled_status_derives_classifications_only_from_matching_verified_cohort(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    _write_minimal_scheduled_statuses(output_root)
    result_id = "canonical-cohort-result"
    recommendation_status_path = (
        output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json"
    )
    recommendation_status = json.loads(
        recommendation_status_path.read_text(encoding="utf-8")
    )
    recommendation_status["result_id"] = result_id
    recommendation_status["recommendations_count"] = 1
    recommendation_status_path.write_text(
        json.dumps(recommendation_status),
        encoding="utf-8",
    )

    decision_date = date(2026, 9, 7)
    execution = RecommendationExecution(
        result_id=result_id,
        request=Request(as_of_date=decision_date),
        context=Context(as_of_date=decision_date, snapshot_cohort=_classification_test_cohort()),
        status=ExecutionStatus.COMPLETED,
        decision=DecisionBatch(items=()),
        quality=QualityReport(QualityStatus.COMPLETE),
    )
    read_model = RecommendationExecutionReadModel(
        execution=execution,
        label=result_id,
        notes="",
        persisted_at=datetime(2026, 9, 7, 5, 0, tzinfo=timezone.utc),
        payload_hash="sha256:" + "a" * 64,
        artifact_location=f"{result_id}.json",
        schema_version="recommendation-execution.v1",
        schema_revision=2,
        raw_artifact_sha256="sha256:" + "b" * 64,
        integrity_basis="canonical_payload_and_index_verified",
    )

    status = ScheduledEvidenceStatusService(
        _Config(output_root),
        recommendation_queries=_QueryStub((read_model,)),
    ).load_latest()

    assert status.recommendation_status == "passed"
    assert status.recommendations_count == 1
    assert status.recommendation_cohort_integrity_basis == (
        "canonical_payload_and_index_verified"
    )
    assert status.recommendation_canonical_payload_hash == "sha256:" + "a" * 64
    cohort = execution.context.snapshot_cohort
    assert cohort is not None
    assert status.recommendation_cohort_hash == cohort.cohort_hash
    assert status.recommendation_cohort_requested_count == 7
    assert status.recommendation_cohort_quality_missing_count == 1
    assert status.recommendation_cohort_quality_degraded_count == 4
    assert dict(status.recommendation_cohort_classifications) == {
        "可用候選": 1,
        "策略排除": 1,
        "市場狀態排除": 0,
        "缺資料": 1,
        "來源品質問題": 1,
        "其他未判定": 3,
    }
    assert cohort.coverage_status is SnapshotCohortCoverageStatus.PARTIAL

    legacy_claim = replace(read_model, integrity_basis="legacy_read_time_hash_only")
    unverified = ScheduledEvidenceStatusService(
        _Config(output_root),
        recommendation_queries=_QueryStub((legacy_claim,)),
    ).load_latest()
    assert unverified.recommendation_cohort_integrity_basis is None
    assert unverified.recommendation_canonical_payload_hash is None
    assert unverified.recommendation_cohort_hash is None
    assert unverified.recommendation_cohort_requested_count is None
    assert unverified.recommendation_cohort_quality_missing_count is None
    assert unverified.recommendation_cohort_quality_degraded_count is None
    assert unverified.recommendation_cohort_classifications == ()

    malformed_hash_model = replace(read_model, payload_hash="sha256:invalid")
    malformed_hash = ScheduledEvidenceStatusService(
        _Config(output_root),
        recommendation_queries=_QueryStub((malformed_hash_model,)),
    ).load_latest()
    assert malformed_hash.recommendation_cohort_integrity_basis is None
    assert malformed_hash.recommendation_cohort_classifications == ()


def _valid_current_delisted_evidence(
    source_root: Path,
    *,
    symbol: str,
    decision_at: datetime,
) -> dict[str, object]:
    assert symbol == "4130"
    source_root = source_root.resolve()
    pointer_path = source_root / CURRENT_MARKET_STATUS_POINTER_RELATIVE
    output_dir = pointer_path.parent
    run_id = "scheduled-status-4130-fixture"
    run_dir = output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = run_dir / "raw"
    raw_dir.mkdir(exist_ok=True)
    raw_path = raw_dir / "s0001.bin"
    raw_body = b"Fixture bytes for a current official termination notice.\n"
    raw_path.write_bytes(raw_body)
    raw_sha256 = sha256_bytes(raw_body)
    source_id = "tpex.terminated_listing"
    source_url = "https://www.tpex.org.tw/www/zh-tw/company/deListed"
    captured_at = (
        decision_at.astimezone(timezone.utc) - timedelta(minutes=20)
    ).replace(microsecond=0)
    snapshot_observed_at = captured_at + timedelta(seconds=3)
    captured_text = captured_at.isoformat(timespec="microseconds")
    capture = {
        "source_id": source_id,
        "url": source_url,
        "final_url": source_url,
        "status": "captured",
        "parse_status": "parsed",
        "http_status": 200,
        "captured_at": captured_text,
        "raw_path": str(raw_path),
        "raw_sha256": raw_sha256,
        "raw_bytes": len(raw_body),
    }
    evidence = MarketStatusEvidence(
        symbol=symbol,
        source_id=source_id,
        evidence_type="terminated",
        observed_at=captured_text,
        raw_sha256=raw_sha256,
        source_url=source_url,
        effective_from="2026-07-28",
        published_date="2026-07-27",
        notice_reference="fixture-official-termination-notice",
        market="tpex",
        name="Fixture delisted issuer",
    )
    snapshot = build_snapshot(
        observed_at=snapshot_observed_at,
        source_captures=[capture],
        evidence=[evidence],
    )
    snapshot.update(
        {
            "run_id": run_id,
            "source_count": 1,
            "successful_source_count": 1,
            "partial_failure": False,
        }
    )
    snapshot_path = run_dir / "snapshot.json"
    snapshot_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    snapshot_sha256 = sha256_bytes(snapshot_path.read_bytes())
    manifest_path = run_dir / "manifest.json"
    manifest = {
        "schema_version": "current-market-status-capture-manifest.v1",
        "run_id": run_id,
        "snapshot_path": str(snapshot_path),
        "snapshot_sha256": snapshot_sha256,
        "raw_sources": [
            {
                "source_id": source_id,
                "raw_path": str(raw_path),
                "raw_sha256": raw_sha256,
                "captured_at": captured_text,
                "status": "captured",
                "parse_status": "parsed",
            }
        ],
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest_sha256 = sha256_bytes(manifest_path.read_bytes())
    pointer = {
        "schema_version": "current-market-status-pointer.v1",
        "scope": "current_only",
        "pit_eligible": False,
        "run_id": run_id,
        "published_at": snapshot_observed_at.isoformat(),
        "snapshot_path": f"{run_id}/snapshot.json",
        "snapshot_sha256": snapshot_sha256,
        "manifest_path": f"{run_id}/manifest.json",
        "manifest_sha256": manifest_sha256,
        "source_count": 1,
        "successful_source_count": 1,
        "partial_failure": False,
    }
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    pointer_path.write_text(
        json.dumps(pointer, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    result = CurrentMarketStatusPreflight(source_root.resolve()).get(
        symbol,
        cutoff_at=decision_at,
        decision_date=decision_at.astimezone(ZoneInfo("Asia/Taipei")).date(),
    )
    assert result.disposition == "verified_delisted", result.reason_code
    assert result.evidence is not None
    assert validate_current_market_status_evidence(
        result.evidence,
        expected_symbol=symbol,
        decision_at=decision_at,
    )
    return dict(result.evidence)


def _current_delisted_read_model(
    *,
    evidence: dict[str, object],
    assessment_symbol: str = "4130",
    decision_at: datetime | None = None,
) -> RecommendationExecutionReadModel:
    result_id = "canonical-current-delisted-result"
    decision_date = date(2026, 9, 7)
    invocation_at = decision_at or datetime(2026, 9, 7, 5, 0, tzinfo=timezone.utc)
    execution = RecommendationExecution(
        result_id=result_id,
        request=Request(as_of_date=decision_date),
        context=Context(
            as_of_date=decision_date,
            decision_at=invocation_at,
            snapshot_cohort=_classification_test_cohort(include_current_delisted=True),
        ),
        status=ExecutionStatus.COMPLETED,
        decision=DecisionBatch(
            items=(),
            assessments=(
                CandidateAssessment(
                    stock_code=assessment_symbol,
                    eligible=False,
                    filter_outcomes={
                        "current_market_status_gate": FilterOutcome(
                            filter_id="current_market_status_gate",
                            passed=False,
                            reason="official_delisted",
                            evidence=evidence,
                        )
                    },
                ),
            ),
        ),
        quality=QualityReport(QualityStatus.COMPLETE),
    )
    return RecommendationExecutionReadModel(
        execution=execution,
        label=result_id,
        notes="",
        persisted_at=datetime(2026, 9, 7, 5, 1, tzinfo=timezone.utc),
        payload_hash="sha256:" + "a" * 64,
        artifact_location=f"{result_id}.json",
        schema_version="recommendation-execution.v1",
        schema_revision=2,
        raw_artifact_sha256="sha256:" + "b" * 64,
        integrity_basis="canonical_payload_and_index_verified",
    )


def _load_current_delisted_classification(
    tmp_path: Path,
    *,
    evidence: dict[str, object],
    assessment_symbol: str = "4130",
    decision_at: datetime | None = None,
) -> ScheduledEvidenceStatusService:
    output_root = tmp_path / "output"
    _write_minimal_scheduled_statuses(output_root)
    result_id = "canonical-current-delisted-result"
    status_path = output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json"
    latest_status = json.loads(status_path.read_text(encoding="utf-8"))
    latest_status["result_id"] = result_id
    latest_status["recommendations_count"] = 1
    status_path.write_text(json.dumps(latest_status), encoding="utf-8")
    read_model = _current_delisted_read_model(
        evidence=evidence,
        assessment_symbol=assessment_symbol,
        decision_at=decision_at,
    )
    return ScheduledEvidenceStatusService(
        _Config(output_root),
        recommendation_queries=_QueryStub((read_model,)),
    )


def test_scheduled_status_classifies_only_verified_current_delisted_exclusion(
    tmp_path: Path,
) -> None:
    decision_at = datetime(2026, 10, 4, 13, 0, tzinfo=timezone.utc)
    evidence = _valid_current_delisted_evidence(
        tmp_path / "canonical_source", symbol="4130", decision_at=decision_at
    )

    status = _load_current_delisted_classification(
        tmp_path, evidence=evidence, decision_at=decision_at
    ).load_latest()

    assert dict(status.recommendation_cohort_classifications)["市場狀態排除"] == 1
    assert dict(status.recommendation_cohort_classifications)["其他未判定"] == 3
    assert status.recommendation_cohort_requested_count == 8


@pytest.mark.parametrize(
    ("case", "assessment_symbol"),
    (
        ("missing_lineage", "4130"),
        ("wrong_evidence_symbol", "4130"),
        ("wrong_assessment_symbol", "2330"),
        ("decision_clock_mismatch", "4130"),
    ),
)
def test_scheduled_status_keeps_unverified_delisted_rows_unclassified(
    tmp_path: Path,
    case: str,
    assessment_symbol: str,
) -> None:
    decision_at = datetime(2026, 10, 4, 13, 0, tzinfo=timezone.utc)
    evidence = _valid_current_delisted_evidence(
        tmp_path / "canonical_source", symbol="4130", decision_at=decision_at
    )
    if case == "missing_lineage":
        evidence.pop("manifest_path")
    elif case == "wrong_evidence_symbol":
        evidence["symbol"] = "9999"
    model_decision_at = decision_at
    if case == "decision_clock_mismatch":
        model_decision_at = decision_at + timedelta(seconds=1)

    status = _load_current_delisted_classification(
        tmp_path,
        evidence=evidence,
        assessment_symbol=assessment_symbol,
        decision_at=model_decision_at,
    ).load_latest()

    classifications = dict(status.recommendation_cohort_classifications)
    assert classifications["市場狀態排除"] == 0
    assert classifications["其他未判定"] == 4
