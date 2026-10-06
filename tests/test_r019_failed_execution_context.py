from __future__ import annotations

from datetime import date
from typing import Any, NoReturn

from app_module.recommendation.contracts import (
    ExecutionStatus,
    MLAvailabilityStatus,
    QualityStatus,
)
from app_module.recommendation.execute import execute_recommendation


class _FailingService:
    calibration_consumer = None

    def __init__(self) -> None:
        self.last_calibration_projections: list[object] = []
        self.last_screening_matrix: list[dict[str, object]] = []
        self.last_excluded_candidates_json: list[dict[str, object]] = []
        self.last_why_not_payload_json: list[dict[str, object]] = []
        self.last_liquidity_gate_payload_json: list[dict[str, object]] = []
        self.last_exclusion_quality = "observed"
        self.last_exclusion_warnings_json: list[str] = []
        self.last_run_context: dict[str, object] = {}
        self._personalization_execution_clocks: dict[str, str] = {}

    def _reset_negative_evidence_buffers(self) -> None:
        self.last_screening_matrix = []
        self.last_excluded_candidates_json = []
        self.last_why_not_payload_json = []
        self.last_liquidity_gate_payload_json = []
        self.last_exclusion_quality = "observed"
        self.last_exclusion_warnings_json = []
        self.last_run_context = {}

    def _get_fundamental_sqlite_provider(self) -> None:
        return None

    def _run_recommendation_body_result(self, **_kwargs: Any) -> NoReturn:
        self._reset_negative_evidence_buffers()
        self.last_run_context = {
            "result_id": "partial-wrong-result-id",
            "as_of_date": "1999-01-01",
            "decision_at": "1999-01-01T00:00:00+00:00",
            "strategy_config_id": "partial-strategy-id",
            "strategy_config_schema": "partial-strategy-version",
            "universe_policy_id": "partial-universe-policy-id",
            "universe_snapshot_id": "partial-universe-snapshot-id",
            "warnings": ["partial-body-warning"],
            "calibration_projection_status": "unavailable",
            "calibration_projection_receipt_status": "unavailable",
            "calibration_projection_receipt_error_detail": "partial-ml-error",
        }
        self.last_screening_matrix = [
            {
                "stock_code": "BAD",
                "status": "fail",
                "stage": "partial-stage",
                "reason_codes": ["partial-reason"],
                "quality": "degraded",
            }
        ]
        self.last_exclusion_quality = "degraded"
        raise RuntimeError("injected body failure")


def test_failed_execution_context_uses_request_and_not_partial_body_state() -> None:
    service = _FailingService()
    execution = execute_recommendation(
        service,
        {
            "as_of_date": "2026-05-20",
            "config_id": "caller-config-id",
            "config_version": "caller-config-version",
        },
        as_of_date="2026-05-20",
        result_id="r019-failed-explicit-request",
    )

    assert execution.status is ExecutionStatus.FAILED
    assert execution.decision is None
    assert execution.result_id == "r019-failed-explicit-request"
    assert execution.request.as_of_date == date(2026, 5, 20)
    assert execution.request.config_ref is not None
    assert execution.request.config_ref.reference_id == "caller-config-id"
    assert execution.context.as_of_date == date(2026, 5, 20)
    assert execution.context.decision_at is None
    assert execution.context.strategy_identity is None
    assert execution.context.universe_identity is None
    assert execution.context.universe_policy_ref is None
    assert execution.context.universe_snapshot_ref is None
    assert execution.quality.status is QualityStatus.UNKNOWN
    assert execution.quality.warnings == ("legacy_source_identity_unbound",)
    assert execution.quality.metrics == {
        "screening_row_count": 0,
        "recommendation_count": 0,
    }
    assert execution.ml_availability.status is MLAvailabilityStatus.NOT_REQUESTED

    # The partial facts remain available for compatibility diagnostics only.
    sidecar = next(
        event for event in execution.events
        if event.event_type == "legacy_negative_evidence_capture"
    )
    assert sidecar.details["screening_matrix"][0]["stock_code"] == "BAD"
    context_event = next(
        event for event in execution.events
        if event.event_type == "legacy_invocation_context"
    )
    assert context_event.details["result_id"] == "partial-wrong-result-id"
