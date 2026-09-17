from __future__ import annotations

from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from typing import Any
from typing import cast

from app_module.dtos import RecommendationDTO
from app_module.decision_continuity_controller import DecisionIdentity
from app_module.evidence_event_dtos import (
    EvidenceDataQuality,
    EvidenceEvent,
    EvidenceEventType,
    EvidenceOutcome,
    EvidenceOutcomeStatus,
)
from app_module.evidence_event_repository import EvidenceEventRepository
from app_module.journal_service import JournalService
from app_module.personalization_calibration import (
    PersonalizationCalibrationEvaluator,
    PersonalizationCalibrationPolicy,
)
from app_module.personalization_contract import (
    PERSONALIZATION_PREDICTION_RECEIPT_SCHEMA_VERSION,
    PersonalizationDeliveryScope,
    PersonalizationEvaluationRow,
    canonical_payload_hash,
)
from app_module.personalization_action_recorder import PersonalizationDecisionRecorder
from app_module.personalization_save_adapter import (
    PersonalizationRecommendationSaveAdapter,
)
from app_module.recommendation_repository import RecommendationRepository
from app_module.recommendation_save_coordinator import RecommendationSaveRequest


RESULT_ID = "rec_read_service_001"
STOCK_CODE = "2330"
SCOPE_ID = "scope_read_service_001"
PREDICTION_ID = "00000000-0000-0000-0000-000000000010"
FIT_PREDICTION_ID = "00000000-0000-0000-0000-000000000011"
COST_HASH = "sha256:" + ("b" * 64)
DATASET_HASH = "sha256:" + ("d" * 64)
UNIVERSE_HASH = "sha256:" + ("e" * 64)
RECEIPT_HASH = "sha256:" + ("f" * 64)
FIT_RECEIPT_HASH = "sha256:" + ("1" * 64)
LABEL_CONTRACT = "label_projection_v1"
RETURN_BASIS = "close_to_close_event_date"


class _TempConfig:
    def __init__(self, output_root: Path) -> None:
        self.output_root = output_root

    def resolve_output_path(self, subfolder: str) -> Path:
        path = self.output_root / subfolder
        path.mkdir(parents=True, exist_ok=True)
        return path


def _scope() -> PersonalizationDeliveryScope:
    return PersonalizationDeliveryScope.create(
        scope_id=SCOPE_ID,
        scope_type="user",
        delivery_id="delivery_read_service_001",
        declared_at="2025-02-10T08:50:00+00:00",
        decision_at="2025-02-10T09:00:00+00:00",
        available_at="2025-02-10T08:55:00+00:00",
        captured_at="2025-02-10T08:55:00+00:00",
        receipt_created_at="2025-02-10T09:01:00+00:00",
    )


def _receipt() -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_version": PERSONALIZATION_PREDICTION_RECEIPT_SCHEMA_VERSION,
        "result_id": RESULT_ID,
        "decision_date": "2025-02-10",
        "candidate_identity": {"candidate_id": "model_001"},
        "model_id": "model_001",
        "dataset_id": "dataset_001",
        "dataset_hash": DATASET_HASH,
        "label_contract_id": LABEL_CONTRACT,
        "return_basis": RETURN_BASIS,
        "universe_policy_hash": UNIVERSE_HASH,
        "source_id": "recommendation_service",
        "selection_contract": {
            "authority": "rule_top_n",
            "score_kind": "rule_total_score",
            "percentile_kind": "rule_percentile",
            "model_ranking_kind": "model_return_bp",
            "top_n_changed_by_model": False,
        },
        "projections": [
            {
                "stock_code": STOCK_CODE,
                "model_version": "model_001",
                "dataset_version": "dataset_001",
                "dataset_hash": DATASET_HASH,
                "cost_scenario_hash": COST_HASH,
                "horizon": "20 trading days",
                "prediction_id": PREDICTION_ID,
                "label_contract_id": LABEL_CONTRACT,
                "return_basis": RETURN_BASIS,
                "universe_policy_hash": UNIVERSE_HASH,
                "calibrated_probability_bp": 5200,
                "population_probability_bp": 5000,
                "status": "active_candidate",
            }
        ],
        "formal_order_allowed": False,
        "production_action_allowed": False,
        "shadow_only": True,
    }
    return {**body, "receipt_hash": canonical_payload_hash(body)}


def _save_sources(tmp_path: Path) -> tuple[Path, RecommendationRepository, JournalService, Any]:
    output_root = tmp_path / "output"
    repository = RecommendationRepository(_TempConfig(output_root))
    journal = JournalService(cast(Any, SimpleNamespace(output_root=output_root)))
    receipt = _receipt()
    scope = _scope()
    context = {
        "as_of_date": "2025-02-10",
        "data_date": "2025-02-10",
        "run_started_at": "2025-02-10T08:49:00+00:00",
        "personalization_scope_declared_at": scope.declared_at,
        "available_at": scope.available_at,
        "captured_at": scope.captured_at,
        "decision_at": scope.decision_at,
        "calibration_projection_receipt_created_at": scope.receipt_created_at,
        "temporal_contract": "recommendation-producer-clock.v1",
        "temporal_mode": "natural_producer_clock",
        "cutoff_selection": "producer_selected_latest_available_cutoff",
        "cutoff_policy": "source_latest_available_exact",
        "decision_clock_timezone": "UTC",
        "market_calendar_timezone": "Asia/Taipei",
        "prediction_decision_anchor": "actual_producer_decision_at",
        "horizon_anchor": "immutable_projection_receipt",
        "calibration_projection_receipt": receipt,
        "calibration_projection_receipt_metadata": {
            "result_id": RESULT_ID,
            "receipt_hash": receipt["receipt_hash"],
            "receipt_created_at": scope.receipt_created_at,
        },
        "calibration_projection_rows": {STOCK_CODE: dict(receipt["projections"][0])},
    }
    recommendation = RecommendationDTO(
        stock_code=STOCK_CODE,
        stock_name="台積電",
        close_price=Decimal("100.00"),
        price_change=1.0,
        total_score=80.0,
        indicator_score=80.0,
        pattern_score=80.0,
        volume_score=80.0,
        recommendation_reasons="read service integration",
        industry="半導體",
        regime_match=True,
        calibration_provenance={"projection_receipt_hash": receipt["receipt_hash"]},
    )
    request = RecommendationSaveRequest(
        result_name="personalization read service integration",
        config={"_recommendation_run_context": context},
        recommendations=(recommendation,),
        current_profile=None,
        profile_meta={},
        current_regime=None,
        personalization_scope=scope,
        personalization_request_id="request_read_service_001",
    )
    outcome = request.persist(
        recommendation_repository=repository,
        universe_service=None,
        recommendation_service=SimpleNamespace(last_run_context={}),
        regime_service=SimpleNamespace(),
    )
    ack = PersonalizationRecommendationSaveAdapter().acknowledge_delivery(
        recommendation_repository=repository,
        journal_service=journal,
        result_id=outcome.result_id,
        scope_id=SCOPE_ID,
        delivery_id=outcome.personalization_delivery_id or "",
        persisted_at="2025-02-10T09:00:00+00:00",
        delivered_at="2025-02-10T09:00:00+00:00",
        recorded_at="2025-02-10T09:01:00+00:00",
    )
    assert ack.status == "delivered"
    return output_root, repository, journal, outcome


def _append_action_and_outcome(
    output_root: Path,
    repository: RecommendationRepository,
    journal: JournalService,
) -> None:
    from app_module.personalization_read_service import PersonalizationReadService

    service = PersonalizationReadService.from_paths(
        output_root=output_root,
        evidence_db_path=output_root.parent / "evidence.sqlite",
    )
    saved = service.recommendation_source.read_result(RESULT_ID)
    assert saved is not None
    projection = service.projection_service.build_for_candidate(
        result_id=RESULT_ID,
        stock_code=STOCK_CODE,
        personalization_scope_id=SCOPE_ID,
        result=saved,
        evaluated_as_of="2025-03-05",
        evaluation_cutoff_at="2025-03-05T00:00:00+00:00",
    )
    assert projection.status == "linked_prediction"
    assert projection.delivery_status == "delivered"
    action = PersonalizationDecisionRecorder(journal, now=lambda: "2025-03-05T00:00:00+00:00")
    recorded = action.record(
        projection=projection,
        action="accepted",
        decision_kind="recommendation_response",
        request_id="request_read_service_action_001",
        action_at="2025-02-10T09:00:00+00:00",
        recorded_at="2025-02-10T09:02:00+00:00",
        actor="user:integration",
        note="accepted after delivered prediction",
    )
    assert recorded.envelope.horizon_days == 20
    assert recorded.envelope.cost_scenario_hash == COST_HASH

    evidence_db = output_root.parent / "evidence.sqlite"
    evidence = EvidenceEventRepository(object(), db_path=evidence_db)
    identity = {
        "result_id": RESULT_ID,
        "stock_code": STOCK_CODE,
        "personalization_scope_id": SCOPE_ID,
        "prediction_id": PREDICTION_ID,
        "prediction_receipt_hash": _receipt()["receipt_hash"],
        "horizon_days": 20,
        "cost_scenario_hash": COST_HASH,
        "label_contract_id": LABEL_CONTRACT,
        "return_basis": RETURN_BASIS,
    }
    event = EvidenceEvent(
        event_id="event_read_service_001",
        event_hash="sha256:" + ("a" * 64),
        event_date="2025-02-10",
        decision_date="2025-02-10",
        symbol=STOCK_CODE,
        event_type=EvidenceEventType.RECOMMENDATION_INCLUDED,
        event_family="recommendation",
        source_type="recommendation_service",
        source_id="provider-event-source",
        available_date="2025-02-10",
        data_quality=EvidenceDataQuality.OBSERVED,
        metadata=dict(identity),
        created_at="2025-02-10T09:00:00+00:00",
    )
    evidence.insert_event(event)
    outcome_metadata = {
        **identity,
        "label_available_date": "2025-03-02",
        "label_available_at": "2025-03-02T00:00:00+00:00",
        "outcome_recorded_at": "2025-03-02T00:00:00+00:00",
        "label": 1,
        "outcome_tier": "natural_forward",
    }
    evidence.upsert_outcome(
        EvidenceOutcome(
            outcome_id="outcome_read_service_001",
            event_id=event.event_id,
            window_days=20,
            return_basis=RETURN_BASIS,
            event_price_date="2025-02-10",
            outcome_price_date="2025-03-02",
            forward_return_bp=800,
            outcome_status=EvidenceOutcomeStatus.READY,
            data_quality=EvidenceDataQuality.OBSERVED,
            calculated_at="2025-03-02T00:00:00+00:00",
            data_as_of_date="2025-03-02",
            metadata=outcome_metadata,
        )
    )


def _fit_artifact() -> Any:
    fit_row = PersonalizationEvaluationRow(
        prediction_id=FIT_PREDICTION_ID,
        scope_id=SCOPE_ID,
        symbol=STOCK_CODE,
        decision_date="2024-12-01",
        label_available_date="2024-12-20",
        horizon_days=20,
        cost_scenario_hash=COST_HASH,
        population_probability_bp=5000,
        label=1,
        label_available_at="2024-12-20T00:00:00+00:00",
        outcome_recorded_at="2024-12-20T00:00:00+00:00",
        outcome_tier="natural_forward",
        action_state="not_recorded",
        decision_at="2024-12-01T09:00:00+00:00",
        available_at="2024-12-01T08:55:00+00:00",
        receipt_created_at="2024-12-01T09:01:00+00:00",
        captured_at="2024-12-01T08:55:00+00:00",
        row_id="fit-outcome-001",
        outcome_status="ready",
        delivery_status="delivered",
        source_result_id="fit-result-001",
        prediction_receipt_hash=FIT_RECEIPT_HASH,
        model_id="model_001",
        dataset_id="dataset_001",
        dataset_hash=DATASET_HASH,
        universe_policy_hash=UNIVERSE_HASH,
        label_contract_id=LABEL_CONTRACT,
        return_basis=RETURN_BASIS,
        source_id="recommendation_service",
        prediction_receipt_schema_version=PERSONALIZATION_PREDICTION_RECEIPT_SCHEMA_VERSION,
        outcome_id="fit-outcome-001",
        event_id="fit-event-001",
        window_days=20,
    )
    policy = PersonalizationCalibrationPolicy(
        horizon_days=20,
        cost_scenario_hash=COST_HASH,
        scope_id=SCOPE_ID,
        source_id="recommendation_service",
        model_id="model_001",
        dataset_id="dataset_001",
        dataset_hash=DATASET_HASH,
        universe_policy_hash=UNIVERSE_HASH,
        label_contract_id=LABEL_CONTRACT,
        return_basis=RETURN_BASIS,
        population_prior_bp=5000,
    )
    return PersonalizationCalibrationEvaluator().fit(
        [fit_row],
        fit_as_of="2025-01-01",
        policy=policy,
        created_at="2025-01-22T00:00:00+00:00",
    )


def test_real_sources_save_ack_action_outcome_reader_and_evaluator_are_integrated(
    tmp_path: Path,
) -> None:
    output_root, repository, journal, outcome = _save_sources(tmp_path)
    _append_action_and_outcome(output_root, repository, journal)
    from app_module.personalization_read_service import PersonalizationReadService

    report = PersonalizationReadService.from_paths(
        output_root=output_root,
        evidence_db_path=output_root.parent / "evidence.sqlite",
    ).inspect_scope(
        scope_id=SCOPE_ID,
        evaluated_as_of="2025-03-05",
        evaluation_cutoff_at="2025-03-05T00:00:00+00:00",
        result_id=RESULT_ID,
        stock_code=STOCK_CODE,
        fit_artifact=_fit_artifact(),
    )
    assert outcome.result_id == RESULT_ID
    assert report.source_bytes_unchanged is True
    assert report.denominators["prediction_available_count"] == 1
    assert report.denominators["action_recorded_count"] == 1
    assert report.denominators["outcome_ready_count"] == 1
    assert report.denominators["natural_forward_count"] == 1
    assert report.denominators["action_utility_count"] == 0
    assert report.denominators["evaluation_row_count"] == 1
    assert report.evaluation is not None
    assert report.evaluation.status == "evaluated"
    assert report.evaluation.rows[0].population_probability_bp == 5000
    assert not any("population_probability_missing" in item for item in report.diagnostics)
    assert report.source_manifest_hash.startswith("sha256:")
    assert any(
        item["path"].endswith("recommendation_runs.db")
        and item["before"]["sha256"] == item["after"]["sha256"]
        for item in report.source_fingerprints
    )


def test_readback_excludes_action_delivered_late_than_latest_human_revision(
    tmp_path: Path,
) -> None:
    output_root, repository, journal, _outcome = _save_sources(tmp_path)
    _append_action_and_outcome(output_root, repository, journal)
    # The normal recorder rejects this chronology.  The readback test keeps
    # an adversarial persisted revision in scope to prove that diagnosis and
    # exclusion remain observable instead of being rewritten as no action.
    late_action = {
        "result_id": RESULT_ID,
        "stock_code": STOCK_CODE,
        "personalization_scope_id": SCOPE_ID,
        "prediction_id": PREDICTION_ID,
        "prediction_receipt_hash": _receipt()["receipt_hash"],
        "horizon_days": 20,
        "cost_scenario_hash": COST_HASH,
        "label_contract_id": LABEL_CONTRACT,
        "return_basis": RETURN_BASIS,
        "action": "accepted",
        "action_state": "recorded",
        "action_at": "2025-02-10T08:59:00+00:00",
        "recorded_at": "2025-02-10T09:03:00+00:00",
        "created_at": "2025-02-10T09:03:00.000000+00:00",
        "revision_id": "readback_late_action_001",
    }
    journal.record_research_action(
        "accepted",
        DecisionIdentity(
            result_id=RESULT_ID,
            stock_code=STOCK_CODE,
            decision_date="2025-02-10",
        ),
        note="adversarial late action readback fixture",
        entity_id="readback_late_action_001",
        revision_id="readback_late_action_001",
        continuity_event_id="readback_late_action_001",
        recorded_at="2025-02-10T09:03:00+00:00",
        personalization_action=late_action,
    )

    from app_module.personalization_read_service import PersonalizationReadService

    report = PersonalizationReadService.from_paths(
        output_root=output_root,
        evidence_db_path=output_root.parent / "evidence.sqlite",
    ).inspect_scope(
        scope_id=SCOPE_ID,
        evaluated_as_of="2025-03-05",
        evaluation_cutoff_at="2025-03-05T00:00:00+00:00",
        result_id=RESULT_ID,
        stock_code=STOCK_CODE,
        fit_artifact=_fit_artifact(),
    )
    assert report.source_consistency_status == "verified"
    assert report.source_completeness_status == "verified"
    assert report.denominators["prediction_available_count"] == 1
    assert report.denominators["action_conflict_count"] == 1
    assert report.denominators["natural_forward_count"] == 1
    assert report.denominators["outcome_ready_count"] == 0
    assert report.denominators["evaluation_row_count"] == 0
    assert report.evaluation is not None
    assert report.evaluation.status == "insufficient_evidence"
    assert report.evaluation.rows == ()
    assert report.cohort["included_evaluation_row_count"] == 0
    assert report.cohort["excluded_reason_counts"][
        "late_delivery_no_natural_credit"
    ] == 1
    assert any(
        item.startswith("late_delivery_no_natural_credit:")
        for item in report.diagnostics
    )


def test_exact_journal_scope_reads_apply_bound_after_identity_filter(
    tmp_path: Path,
) -> None:
    from app_module.personalization_read_service import PersonalizationReadService

    output_root, repository, journal, _outcome = _save_sources(tmp_path)
    _append_action_and_outcome(output_root, repository, journal)
    report = PersonalizationReadService.from_paths(
        output_root=output_root,
        evidence_db_path=output_root.parent / "evidence.sqlite",
        max_journal_rows=1,
    ).inspect_scope(
        scope_id=SCOPE_ID,
        evaluated_as_of="2025-03-05",
        evaluation_cutoff_at="2025-03-05T00:00:00+00:00",
        result_id=RESULT_ID,
        stock_code=STOCK_CODE,
        fit_artifact=_fit_artifact(),
    )

    assert report.source_bytes_unchanged is True
    assert report.source_consistency_status == "verified"
    assert report.source_completeness_status == "verified"
    assert report.inventory["journal"]["query_mode"] == (
        "exact_identity_and_scope_before_bound"
    )
    assert report.inventory["journal"]["completeness_status"] == "verified"
    assert report.denominators["action_recorded_count"] == 1
    assert report.denominators["action_not_recorded_count"] == 0
    assert report.evaluation is not None
    assert report.evaluation.status == "evaluated"


def test_truncated_exact_action_history_is_incomplete_and_not_not_recorded(
    tmp_path: Path,
) -> None:
    from app_module.personalization_read_service import PersonalizationReadService

    output_root, repository, journal, _outcome = _save_sources(tmp_path)
    _append_action_and_outcome(output_root, repository, journal)
    service = PersonalizationReadService.from_paths(
        output_root=output_root,
        evidence_db_path=output_root.parent / "evidence.sqlite",
    )
    saved = service.recommendation_source.read_result(RESULT_ID)
    assert saved is not None
    projection = service.projection_service.build_for_candidate(
        result_id=RESULT_ID,
        stock_code=STOCK_CODE,
        personalization_scope_id=SCOPE_ID,
        result=saved,
        evaluated_as_of="2025-03-05",
        evaluation_cutoff_at="2025-03-05T00:00:00+00:00",
    )
    second = PersonalizationDecisionRecorder(
        journal,
        now=lambda: "2025-03-05T00:00:00+00:00",
    ).record(
        projection=projection,
        action="skipped",
        decision_kind="recommendation_response",
        request_id="request_read_service_action_002",
        action_at="2025-02-10T09:05:00+00:00",
        recorded_at="2025-02-10T09:06:00+00:00",
        actor="user:integration",
        note="later review changed the decision",
    )
    assert second.envelope.action == "skipped"

    report = PersonalizationReadService.from_paths(
        output_root=output_root,
        evidence_db_path=output_root.parent / "evidence.sqlite",
        max_journal_rows=1,
    ).inspect_scope(
        scope_id=SCOPE_ID,
        evaluated_as_of="2025-03-05",
        evaluation_cutoff_at="2025-03-05T00:00:00+00:00",
        result_id=RESULT_ID,
        stock_code=STOCK_CODE,
        fit_artifact=_fit_artifact(),
    )

    assert report.source_bytes_unchanged is True
    assert report.source_consistency_status == "verified"
    assert report.source_completeness_status == "incomplete"
    assert report.cohort["cohort_status"] == "source_incomplete"
    assert report.evaluation is None
    assert report.evaluation_rows == ()
    assert report.denominators["action_conflict_count"] == 1
    assert report.denominators["action_not_recorded_count"] == 0
    assert report.denominators["source_completeness_incomplete_count"] == 1
    assert "journal_source_completeness_incomplete" in report.diagnostics
    assert any(
        item.startswith("journal_exact_read_limit_reached:action:")
        for item in report.diagnostics
    )


def test_malformed_journal_history_is_incomplete_and_not_not_recorded(
    tmp_path: Path,
) -> None:
    from app_module.personalization_read_service import PersonalizationReadService

    output_root, repository, journal, _outcome = _save_sources(tmp_path)
    _append_action_and_outcome(output_root, repository, journal)
    journal_path = output_root / "portfolio" / "journal_entries.jsonl"
    lines = journal_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    lines[1] = "{broken action"
    journal_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = PersonalizationReadService.from_paths(
        output_root=output_root,
        evidence_db_path=output_root.parent / "evidence.sqlite",
    ).inspect_scope(
        scope_id=SCOPE_ID,
        evaluated_as_of="2025-03-05",
        evaluation_cutoff_at="2025-03-05T00:00:00+00:00",
        result_id=RESULT_ID,
        stock_code=STOCK_CODE,
        fit_artifact=_fit_artifact(),
    )

    assert report.source_bytes_unchanged is True
    assert report.source_consistency_status == "verified"
    assert report.source_completeness_status == "incomplete"
    assert report.cohort["cohort_status"] == "source_incomplete"
    assert report.evaluation is None
    assert report.denominators["action_conflict_count"] == 1
    assert report.denominators["action_not_recorded_count"] == 0
    assert "journal_jsonl_malformed_line:2" in report.diagnostics
    assert "action_history_incomplete" in report.projections[0]["projection"]["warnings"]


def test_missing_roots_are_diagnostic_only_and_create_no_files(tmp_path: Path) -> None:
    from app_module.personalization_read_service import PersonalizationReadService

    missing_root = tmp_path / "missing" / "output"
    report = PersonalizationReadService.from_paths(output_root=missing_root).inspect_scope(
        scope_id="scope_missing_root",
        evaluated_as_of="2025-03-05",
        result_id="rec_missing_root",
        stock_code=STOCK_CODE,
    )
    assert report.source_bytes_unchanged is True
    assert report.projections == ()
    assert report.denominators["evaluation_row_count"] == 0
    assert "recommendation_metadata_database_missing" in report.diagnostics
    assert "journal_jsonl_missing" in report.diagnostics
    assert "evidence_database_missing" in report.diagnostics
    assert "fit_artifact_missing:evaluation_not_run" in report.diagnostics
    assert not missing_root.exists()
    assert not missing_root.parent.exists()


def test_source_mutation_after_result_read_invalidates_ready_evaluation(
    tmp_path: Path,
) -> None:
    from app_module.personalization_read_service import (
        PersonalizationReadService,
        ReadOnlyEvidenceSource,
        ReadOnlyJournalRevisionSource,
        ReadOnlyProjectionReceiptSource,
        ReadOnlyRecommendationSource,
    )

    output_root, repository, journal, _outcome = _save_sources(tmp_path)
    _append_action_and_outcome(output_root, repository, journal)

    recommendation_source = ReadOnlyRecommendationSource(output_root)
    original_read = recommendation_source.read_result
    mutated = False

    def read_then_mutate(result_id: str) -> dict[str, Any] | None:
        nonlocal mutated
        payload = original_read(result_id)
        if payload is not None and not mutated:
            path = recommendation_source._path_for(result_id)
            changed = json.loads(path.read_text(encoding="utf-8"))
            changed["result_id"] = "changed-after-read"
            path.write_text(json.dumps(changed), encoding="utf-8")
            mutated = True
        return dict(payload) if payload is not None else None

    setattr(recommendation_source, "read_result", cast(Any, read_then_mutate))
    service = PersonalizationReadService(
        recommendation_source,
        ReadOnlyJournalRevisionSource(output_root / "portfolio" / "journal_entries.jsonl"),
        ReadOnlyEvidenceSource(output_root.parent / "evidence.sqlite"),
        ReadOnlyProjectionReceiptSource(output_root),
    )
    report = service.inspect_scope(
        scope_id=SCOPE_ID,
        evaluated_as_of="2025-03-05",
        evaluation_cutoff_at="2025-03-05T00:00:00+00:00",
        result_id=RESULT_ID,
        stock_code=STOCK_CODE,
        fit_artifact=_fit_artifact(),
    )

    assert mutated is True
    assert report.source_bytes_unchanged is False
    assert report.source_consistency_status == "invalidated"
    assert report.evaluation is None
    assert report.evaluation_rows == ()
    assert report.cohort["cohort_status"] == "source_changed_during_read"
    assert report.denominators["source_consistency_invalidated_count"] == 1
    assert "evaluation_not_run:source_consistency_invalidated" in report.diagnostics
    assert any(
        item["path"].endswith(f"{RESULT_ID}.json")
        and item["unchanged"] is False
        for item in report.source_fingerprints
    )


def test_bounded_result_and_candidate_inventory_is_visible_and_stable(
    tmp_path: Path,
) -> None:
    from app_module.personalization_read_service import PersonalizationReadService

    output_root = tmp_path / "output"
    runs_dir = output_root / "recommendation" / "runs"
    runs_dir.mkdir(parents=True)
    result_ids = (
        "rec_20250914",
        "rec_20250915",
        "rec_20250916",
    )
    for current_result_id in result_ids:
        rows = [
            {"stock_code": "2330"},
            {"stock_code": "2317"},
            {"stock_code": "2454"},
        ]
        (runs_dir / f"{current_result_id}.json").write_text(
            json.dumps(
                {
                    "result_id": current_result_id,
                    "recommendations": rows,
                }
            ),
            encoding="utf-8",
        )

    report = PersonalizationReadService.from_paths(
        output_root=output_root,
        max_results=2,
        max_candidates_per_result=2,
    ).inspect_scope(
        scope_id="scope_inventory",
        evaluated_as_of="2025-09-16",
    )

    assert report.inventory["selection_mode"] == "bounded_inventory"
    assert report.inventory["available_result_count"] == 3
    assert report.inventory["selected_result_count"] == 2
    assert report.inventory["excluded_result_count"] == 1
    assert report.inventory["selected_result_ids"] == [
        "rec_20250916",
        "rec_20250915",
    ]
    assert report.inventory["truncated"] is True
    assert any(
        item.startswith("recommendation_result_inventory_truncated:limit=2")
        for item in report.diagnostics
    )
    for current_result_id in report.inventory["selected_result_ids"]:
        candidate = report.candidate_inventory[current_result_id]
        assert candidate["available_candidate_count"] == 3
        assert candidate["selected_candidate_count"] == 2
        assert candidate["excluded_candidate_count"] == 1
        assert candidate["selected_stock_codes"] == ["2330", "2317"]
        assert candidate["truncated"] is True
        assert any(
            item.startswith(
                f"recommendation_candidate_inventory_truncated:{current_result_id}:limit=2"
            )
            for item in report.diagnostics
        )


def test_reused_read_service_refreshes_new_recommendation_inventory(
    tmp_path: Path,
) -> None:
    from app_module.personalization_read_service import PersonalizationReadService

    output_root = tmp_path / "output"
    runs_dir = output_root / "recommendation" / "runs"
    runs_dir.mkdir(parents=True)
    first_id = "rec_20250915"
    second_id = "rec_20250916"
    (runs_dir / f"{first_id}.json").write_text(
        json.dumps({"result_id": first_id, "recommendations": []}),
        encoding="utf-8",
    )
    service = PersonalizationReadService.from_paths(
        output_root=output_root,
        max_results=10,
    )
    first_report = service.inspect_scope(
        scope_id="scope_reuse",
        evaluated_as_of="2025-09-16",
    )
    assert first_report.inventory["available_result_count"] == 1

    (runs_dir / f"{second_id}.json").write_text(
        json.dumps({"result_id": second_id, "recommendations": []}),
        encoding="utf-8",
    )
    second_report = service.inspect_scope(
        scope_id="scope_reuse",
        evaluated_as_of="2025-09-16",
    )

    assert second_report.inventory["available_result_count"] == 2
    assert second_report.inventory["selected_result_ids"] == [
        second_id,
        first_id,
    ]


def test_evidence_event_and_outcome_share_wal_snapshot_and_refresh_after_commit(
    tmp_path: Path,
) -> None:
    from app_module.personalization_read_service import ReadOnlyEvidenceSource

    evidence_db = tmp_path / "evidence.sqlite"
    evidence = EvidenceEventRepository(object(), db_path=evidence_db)
    event_id = "event_wal_snapshot_001"
    identity = {
        "result_id": RESULT_ID,
        "stock_code": STOCK_CODE,
        "personalization_scope_id": SCOPE_ID,
        "prediction_id": PREDICTION_ID,
        "prediction_receipt_hash": RECEIPT_HASH,
        "horizon_days": 20,
        "cost_scenario_hash": COST_HASH,
        "label_contract_id": LABEL_CONTRACT,
        "return_basis": RETURN_BASIS,
    }
    evidence.insert_event(
        EvidenceEvent(
            event_id=event_id,
            event_hash="sha256:" + ("9" * 64),
            event_date="2025-02-10",
            decision_date="2025-02-10",
            symbol=STOCK_CODE,
            event_type=EvidenceEventType.RECOMMENDATION_INCLUDED,
            event_family="recommendation",
            source_type="recommendation_service",
            metadata=dict(identity),
            created_at="2025-02-10T09:00:00+00:00",
        )
    )
    writer = sqlite3.connect(evidence_db)
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.commit()
        outcome = EvidenceOutcome(
            outcome_id="outcome_wal_snapshot_001",
            event_id=event_id,
            window_days=20,
            return_basis=RETURN_BASIS,
            event_price_date="2025-02-10",
            outcome_price_date="2025-03-02",
            forward_return_bp=900,
            outcome_status=EvidenceOutcomeStatus.READY,
            data_quality=EvidenceDataQuality.OBSERVED,
            calculated_at="2025-03-02T00:00:00+00:00",
            data_as_of_date="2025-03-02",
            metadata={
                **identity,
                "label_available_date": "2025-03-02",
                "label_available_at": "2025-03-02T00:00:00+00:00",
                "outcome_recorded_at": "2025-03-02T00:00:00+00:00",
                "label": 1,
                "outcome_tier": "natural_forward",
            },
        )
        row = evidence._outcome_to_row(outcome)
        columns = tuple(row)
        placeholders = ", ".join("?" for _ in columns)
        writer.execute(
            f"INSERT INTO evidence_outcomes ({', '.join(columns)}) "
            f"VALUES ({placeholders})",
            tuple(row[column] for column in columns),
        )
        # The outcome is committed from inside the event conversion, after
        # the reader has begun its explicit transaction but before its outcome
        # SELECT.  A single snapshot must not see this newly-committed row.
        source = ReadOnlyEvidenceSource(evidence_db)
        original_row_to_event = source.repository._row_to_event
        committed = False

        def commit_when_event_is_decoded(row_value: dict[str, Any]) -> Any:
            nonlocal committed
            if not committed:
                writer.commit()
                committed = True
            return original_row_to_event(row_value)

        setattr(
            source.repository,
            "_row_to_event",
            cast(Any, commit_when_event_is_decoded),
        )
        first_read = source.list_events(RESULT_ID, STOCK_CODE)
        assert committed is True
        assert len(first_read) == 1
        assert first_read[0]["outcomes"] == []
        assert any(
            item.name.endswith("evidence.sqlite-wal")
            for item in source.paths_for_fingerprint()
        )

        source.reset()
        second_read = source.list_events(RESULT_ID, STOCK_CODE)
        assert len(second_read) == 1
        assert len(second_read[0]["outcomes"]) == 1
    finally:
        writer.close()


def test_evidence_exact_result_filter_precedes_event_bound_and_keeps_alias_conflicts(
    tmp_path: Path,
) -> None:
    from app_module.personalization_read_service import ReadOnlyEvidenceSource

    evidence_db = tmp_path / "evidence.sqlite"
    evidence = EvidenceEventRepository(object(), db_path=evidence_db)
    for index, decision_date in enumerate(
        ("2025-02-01", "2025-02-02", "2025-02-03"),
        start=1,
    ):
        result_id = f"result-{index}"
        evidence.insert_event(
            EvidenceEvent(
                event_id=f"event_bound_{index}",
                event_hash="sha256:" + (str(index) * 64),
                event_date=decision_date,
                decision_date=decision_date,
                symbol=STOCK_CODE,
                event_type=EvidenceEventType.RECOMMENDATION_INCLUDED,
                event_family="recommendation",
                source_type="recommendation_service",
                metadata={
                    "result_id": result_id,
                    "stock_code": STOCK_CODE,
                    "personalization_scope_id": SCOPE_ID,
                },
                created_at=f"{decision_date}T09:00:00+00:00",
            )
        )
    conflict_result_id = "result-conflict"
    evidence.insert_event(
        EvidenceEvent(
            event_id="event_bound_conflict",
            event_hash="sha256:" + ("c" * 64),
            event_date="2025-02-04",
            decision_date="2025-02-04",
            symbol=STOCK_CODE,
            event_type=EvidenceEventType.RECOMMENDATION_INCLUDED,
            event_family="recommendation",
            source_type="recommendation_service",
            metadata={
                "result_id": conflict_result_id,
                "source_result_id": "result-other",
                "stock_code": STOCK_CODE,
                "personalization_scope_id": SCOPE_ID,
            },
            created_at="2025-02-04T09:00:00+00:00",
        )
    )

    source = ReadOnlyEvidenceSource(evidence_db, max_events=1)
    target = source.list_events("result-3", STOCK_CODE)
    assert len(target) == 1
    assert target[0]["event_id"] == "event_bound_3"
    conflict = source.list_events(conflict_result_id, STOCK_CODE)
    assert len(conflict) == 1
    assert conflict[0]["metadata"]["result_id"] == conflict_result_id
    assert conflict[0]["metadata"]["source_result_id"] == "result-other"


def test_action_cli_preflights_then_appends_existing_journal_and_reads_back(
    tmp_path: Path,
    capsys: Any,
) -> None:
    from scripts.record_personalization_action import main

    output_root, repository, journal, _outcome = _save_sources(tmp_path)
    del repository, journal
    default_journal_path = output_root / "portfolio" / "journal_entries.jsonl"
    default_journal_bytes = default_journal_path.read_bytes()
    custom_journal_path = tmp_path / "custom-journal" / "research.jsonl"
    custom_journal_path.parent.mkdir(parents=True)
    custom_journal_path.write_bytes(default_journal_bytes)
    common = [
        "--scope-id",
        SCOPE_ID,
        "--result-id",
        RESULT_ID,
        "--stock-code",
        STOCK_CODE,
        "--action",
        "accepted",
        "--decision-kind",
        "recommendation_response",
        "--request-id",
        "request_cli_action_001",
        "--actor",
        "user:cli-test",
        "--note",
        "accepted from explicit CLI command",
        "--as-of",
        "2025-03-05",
        "--action-at",
        "2025-02-10T09:02:00+00:00",
        "--recorded-at",
        "2025-02-10T09:03:00+00:00",
        "--output-root",
        str(output_root),
        "--evidence-db",
        str(output_root.parent / "evidence.sqlite"),
        "--journal-path",
        str(custom_journal_path),
    ]

    first_code = main(common)
    first_payload = json.loads(capsys.readouterr().out)
    assert first_code == 0
    assert first_payload["ok"] is True
    assert first_payload["read_only_preflight"] is True
    assert first_payload["readback"]["action_state"] == "recorded"
    first_revision_id = first_payload["revision_id"]

    later = list(common)
    later[later.index("accepted")] = "skipped"
    later[later.index("request_cli_action_001")] = "request_cli_action_002"
    later[later.index("accepted from explicit CLI command")] = "skipped after later review"
    later[later.index("2025-02-10T09:02:00+00:00")] = "2025-02-10T09:05:00+00:00"
    later[later.index("2025-02-10T09:03:00+00:00")] = "2025-02-10T09:06:00+00:00"
    later_code = main(later)
    later_payload = json.loads(capsys.readouterr().out)
    assert later_code == 0
    assert later_payload["ok"] is True
    assert later_payload["revision_id"] == "request_cli_action_002"

    retry_code = main(common)
    retry_payload = json.loads(capsys.readouterr().out)
    assert retry_code == 0
    assert retry_payload["ok"] is True
    assert retry_payload["revision_id"] == first_revision_id
    assert retry_payload["idempotent_retry"] is True
    assert retry_payload["personalization_action"] == first_payload["personalization_action"]
    assert retry_payload["readback"]["action_revision_id"] == "request_cli_action_002"
    assert retry_payload["readback"]["requested_action_revision_id"] == first_revision_id
    assert default_journal_path.read_bytes() == default_journal_bytes
    assert len(
        JournalService(
            cast(Any, SimpleNamespace(output_root=output_root)),
            journal_path=custom_journal_path,
        ).list_decision_revisions()
    ) == 3  # one technical ACK plus two new human actions


def test_action_cli_missing_linked_prediction_does_not_create_writer_files(
    tmp_path: Path,
    capsys: Any,
) -> None:
    from scripts.record_personalization_action import main

    output_root = tmp_path / "missing" / "output"
    journal_path = output_root / "portfolio" / "journal_entries.jsonl"
    code = main(
        [
            "--scope-id",
            "scope_missing_cli",
            "--result-id",
            "result_missing_cli",
            "--stock-code",
            STOCK_CODE,
            "--action",
            "accepted",
            "--decision-kind",
            "recommendation_response",
            "--request-id",
            "request_missing_cli",
            "--actor",
            "user:cli-test",
            "--as-of",
            "2025-03-05",
            "--output-root",
            str(output_root),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    assert payload["ok"] is False
    assert payload["write_attempted"] is False
    assert payload["read_only_preflight"] is True
    assert "exact_projection_missing" in payload["diagnostics"]
    assert not output_root.exists()
    assert not journal_path.exists()
