from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app_module.decision_continuity_controller import DecisionContinuityController
from app_module.journal_service import JournalService
from app_module.personalization_action_recorder import (
    PersonalizationDecisionRecorder,
    PersonalizationDecisionRecorderError,
)
from app_module.personalization_contract import (
    PersonalizationDeliveryScope,
    canonical_payload_hash,
)
from app_module.personalization_projection import (
    PersonalizationDeliveryCaptureService,
    PersonalizationProjectionService,
)


RESULT_ID = "rec_action_recorder_001"
STOCK_CODE = "2330"
SCOPE_ID = "scope_action_recorder_001"
PREDICTION_ID = "00000000-0000-0000-0000-000000000010"
RECEIPT_COST_HASH = "sha256:" + ("b" * 64)
DATASET_HASH = "sha256:" + ("d" * 64)
UNIVERSE_HASH = "sha256:" + ("e" * 64)
RECEIPT_HASH = "sha256:" + ("f" * 64)
LABEL_CONTRACT = "label_projection_v1"
RETURN_BASIS = "close_to_close_event_date"


def _scope() -> PersonalizationDeliveryScope:
    return PersonalizationDeliveryScope.create(
        scope_id=SCOPE_ID,
        scope_type="user",
        delivery_id="delivery_action_recorder_001",
        declared_at="2025-02-10T08:50:00+00:00",
        decision_at="2025-02-10T09:00:00+00:00",
        available_at="2025-02-10T08:55:00+00:00",
        captured_at="2025-02-10T08:55:00+00:00",
        receipt_created_at="2025-02-10T09:01:00+00:00",
    )


def _receipt() -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_version": "recommendation-calibration-projection-receipt.v1",
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
                "cost_scenario_hash": RECEIPT_COST_HASH,
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


def _capture() -> Any:
    capture_service = PersonalizationDeliveryCaptureService()
    generated = capture_service.capture(
        scope=_scope(),
        request_id="request_action_recorder_001",
        result_id=RESULT_ID,
        stock_code=STOCK_CODE,
        projection_receipt_hash=_receipt()["receipt_hash"],
        generated_at="2025-02-10T08:50:00+00:00",
        prediction_id=PREDICTION_ID,
        model_id="model_001",
        dataset_id="dataset_001",
        dataset_hash=DATASET_HASH,
        cost_scenario_hash=RECEIPT_COST_HASH,
        horizon_days=20,
    )
    persisted = capture_service.mark_persisted(
        generated,
        persisted_at="2025-02-10T08:56:00+00:00",
    )
    return capture_service.mark_delivered(
        persisted,
        delivered_at="2025-02-10T08:59:00+00:00",
    )


def _result() -> dict[str, Any]:
    receipt = _receipt()
    capture = _capture()
    return {
        "result_id": RESULT_ID,
        "run_context": {
            "as_of_date": "2025-02-10",
            "data_date": "2025-02-10",
            "run_started_at": "2025-02-10T08:49:00+00:00",
            "personalization_scope_declared_at": _scope().declared_at,
            "available_at": _scope().available_at,
            "captured_at": _scope().captured_at,
            "decision_at": _scope().decision_at,
            "calibration_projection_receipt_created_at": _scope().receipt_created_at,
            "temporal_contract": "recommendation-producer-clock.v1",
            "temporal_mode": "natural_producer_clock",
            "cutoff_selection": "producer_selected_latest_available_cutoff",
            "cutoff_policy": "source_latest_available_exact",
            "decision_clock_timezone": "UTC",
            "market_calendar_timezone": "Asia/Taipei",
            "prediction_decision_anchor": "actual_producer_decision_at",
            "horizon_anchor": "immutable_projection_receipt",
            "personalization_delivery_captures": [capture.to_dict()],
            "calibration_projection_receipt": receipt,
            "calibration_projection_receipt_metadata": {
                "result_id": RESULT_ID,
                "receipt_hash": receipt["receipt_hash"],
                "receipt_created_at": _scope().receipt_created_at,
            },
            "calibration_projection_rows": {
                STOCK_CODE: dict(receipt["projections"][0]),
            },
        },
        "recommendations": [
            {
                "stock_code": STOCK_CODE,
                "calibration_provenance": {
                    "projection_receipt_hash": receipt["receipt_hash"],
                    "model_version": "model_001",
                    "dataset_version": "dataset_001",
                    "cost_scenario_hash": RECEIPT_COST_HASH,
                },
            }
        ],
    }


def _projection(actions: list[dict[str, Any]] | None = None) -> Any:
    return PersonalizationProjectionService(
        action_reader={(RESULT_ID, STOCK_CODE): actions or []},
    ).build_for_candidate(
        result_id=RESULT_ID,
        stock_code=STOCK_CODE,
        personalization_scope_id=SCOPE_ID,
        result=_result(),
        projection_receipt=_receipt(),
        evaluated_as_of="2025-02-11",
        evaluation_cutoff_at="2025-02-11T00:00:00+00:00",
    )


def _recorder(tmp_path: Path, *, now: str = "2025-02-10T12:00:00+00:00") -> tuple[Any, PersonalizationDecisionRecorder]:
    journal = JournalService(SimpleNamespace(output_root=tmp_path))
    return journal, PersonalizationDecisionRecorder(journal, now=lambda: now)


def _record_kwargs(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "projection": _projection(),
        "action": "accepted",
        "decision_kind": "recommendation_response",
        "request_id": "request_action_001",
        "action_at": "2025-02-10T09:00:00+00:00",
        "recorded_at": "2025-02-10T09:02:01+00:00",
        "note": "first response",
        "actor": "user:test",
    }
    values.update(overrides)
    return values


def test_recorder_retry_preserves_original_lineage_clock_after_later_action(
    tmp_path: Path,
) -> None:
    journal, recorder = _recorder(tmp_path)
    first = recorder.record(**_record_kwargs())
    second = recorder.record(
        **_record_kwargs(recorded_at=None),
    )
    assert second.revision == first.revision
    assert second.envelope == first.envelope
    assert second.envelope.revision_of == ""
    assert second.envelope.recorded_at == first.envelope.recorded_at

    later = recorder.record(
        **_record_kwargs(
            action="skipped",
            request_id="request_action_002",
            action_at="2025-02-10T09:05:00+00:00",
            recorded_at="2025-02-10T09:06:00+00:00",
            note="later response",
        )
    )
    old_retry = recorder.record(**_record_kwargs(recorded_at=None))
    assert later.envelope.revision_of == first.revision.revision_id
    assert old_retry.revision == first.revision
    assert old_retry.envelope.revision_of == ""
    assert len(journal.list_decision_revisions()) == 2

    with pytest.raises(PersonalizationDecisionRecorderError, match="different note"):
        recorder.record(**_record_kwargs(recorded_at=None, note="tampered note"))
    assert len(journal.list_decision_revisions()) == 2


@pytest.mark.parametrize(
    ("action_at", "should_pass"),
    [
        ("2025-02-10T08:58:59+00:00", False),
        ("2025-02-10T08:59:00+00:00", True),
        ("2025-02-10T03:59:00-05:00", True),
        ("2025-02-10T09:00:00+00:00", True),
    ],
)
def test_new_action_requires_action_at_on_or_after_delivery(
    tmp_path: Path,
    action_at: str,
    should_pass: bool,
) -> None:
    _journal, recorder = _recorder(tmp_path)
    kwargs = _record_kwargs(
        request_id=f"request_action_clock_{action_at[-8:].replace(':', '')}",
        action_at=action_at,
        recorded_at="2025-02-10T09:02:01+00:00",
    )
    if should_pass:
        result = recorder.record(**kwargs)
        assert result.envelope.action_at == datetime.fromisoformat(
            action_at
        ).astimezone(timezone.utc).isoformat(timespec="microseconds")
    else:
        with pytest.raises(PersonalizationDecisionRecorderError, match="delivered_at"):
            recorder.record(**kwargs)


def test_projection_does_not_promote_predelivery_human_action(
    tmp_path: Path,
) -> None:
    _journal, _recorder_instance = _recorder(tmp_path)
    projection = _projection(
        [
            {
                "result_id": RESULT_ID,
                "stock_code": STOCK_CODE,
                "personalization_scope_id": SCOPE_ID,
                "prediction_id": PREDICTION_ID,
                "prediction_receipt_hash": _receipt()["receipt_hash"],
                "horizon_days": 20,
                "cost_scenario_hash": RECEIPT_COST_HASH,
                "label_contract_id": LABEL_CONTRACT,
                "return_basis": RETURN_BASIS,
                "action": "accepted",
                "action_state": "recorded",
                "action_at": "2025-02-10T08:58:00+00:00",
                "recorded_at": "2025-02-10T09:02:00+00:00",
                "created_at": "2025-02-10T09:02:00+00:00",
                "revision_id": "predelivery_action_001",
            }
        ]
    )
    assert projection.action == "not_recorded"
    assert projection.action_state == "conflict"
    assert "action_before_delivery" in projection.warnings
    assert projection.late_delivery is True
    assert projection.human_decision_at == "2025-02-10T08:58:00.000000+00:00"
    assert "late_delivery_no_natural_credit" in projection.warnings


def test_projection_uses_last_recorded_revision_as_human_anchor() -> None:
    projection = _projection(
        [
            {
                "result_id": RESULT_ID,
                "stock_code": STOCK_CODE,
                "personalization_scope_id": SCOPE_ID,
                "prediction_id": PREDICTION_ID,
                "prediction_receipt_hash": _receipt()["receipt_hash"],
                "horizon_days": 20,
                "cost_scenario_hash": RECEIPT_COST_HASH,
                "label_contract_id": LABEL_CONTRACT,
                "return_basis": RETURN_BASIS,
                "action": "accepted",
                "action_state": "recorded",
                "action_at": "2025-02-10T09:10:00+00:00",
                "recorded_at": "2025-02-10T09:11:00+00:00",
                "created_at": "2025-02-10T09:11:00+00:00",
                "revision_id": "revision_first",
            },
            {
                "result_id": RESULT_ID,
                "stock_code": STOCK_CODE,
                "personalization_scope_id": SCOPE_ID,
                "prediction_id": PREDICTION_ID,
                "prediction_receipt_hash": _receipt()["receipt_hash"],
                "horizon_days": 20,
                "cost_scenario_hash": RECEIPT_COST_HASH,
                "label_contract_id": LABEL_CONTRACT,
                "return_basis": RETURN_BASIS,
                "action": "skipped",
                "action_state": "recorded",
                "action_at": "2025-02-10T09:05:00+00:00",
                "recorded_at": "2025-02-10T09:12:00+00:00",
                "created_at": "2025-02-10T09:12:00+00:00",
                "revision_id": "revision_correction",
            },
        ]
    )
    assert projection.action == "skipped"
    assert projection.action_state == "recorded"
    assert projection.human_decision_at == "2025-02-10T09:05:00.000000+00:00"
    assert projection.late_delivery is False
