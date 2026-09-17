"""Controlled writer for a new personalization research action.

The recorder is intentionally a thin facade over the existing
``DecisionContinuity``/``JournalService`` append-only stream.  It accepts a
read-side linked prediction projection, verifies every immutable prediction
field needed by the action contract, and stores the typed envelope inside the
existing revision payload.  It does not create a second ledger, retrofit old
actions, or imply broker execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from app_module.decision_continuity_controller import (
    DecisionContinuityController,
    RESEARCH_ACTIONS,
)
from app_module.dtos.decision_continuity_dtos import (
    DecisionContinuityRevision,
    DecisionIdentity,
)
from app_module.personalization_contract import (
    PersonalizationActionEnvelope,
    PersonalizationDeliveryCapture,
    PersonalizationDeliveryScope,
    canonical_aware_datetime,
)


class PersonalizationDecisionRecorderError(ValueError):
    """Raised when a new personal action cannot be exactly verified."""


@dataclass(frozen=True)
class PersonalizationDecisionRecord:
    """The existing continuity revision plus the persisted typed envelope."""

    revision: DecisionContinuityRevision
    envelope: PersonalizationActionEnvelope


def _text(value: object) -> str:
    return str(value or "").strip()


def _mapping(value: Any, field_name: str) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        converted = to_dict()
        if isinstance(converted, Mapping):
            return {str(key): item for key, item in converted.items()}
    raise PersonalizationDecisionRecorderError(f"{field_name} must be an object")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _scope_from_projection(projection: Any) -> PersonalizationDeliveryScope:
    scope_value = getattr(projection, "scope", None)
    if scope_value is None:
        evidence = getattr(projection, "evidence", None)
        scope_value = getattr(evidence, "scope", None)
    try:
        scope = (
            scope_value
            if isinstance(scope_value, PersonalizationDeliveryScope)
            else PersonalizationDeliveryScope.from_mapping(
                _mapping(scope_value, "projection.scope")
            )
        )
    except (TypeError, ValueError) as exc:
        raise PersonalizationDecisionRecorderError(
            "linked projection scope is invalid"
        ) from exc
    if (
        scope.scope_status != "bound"
        or not scope.is_personal_scope
        or scope.captured_at is None
        or scope.temporal_status != "verified"
    ):
        raise PersonalizationDecisionRecorderError(
            "new personal action requires a bound, temporally verified scope"
        )
    return scope


def _capture_from_projection(
    projection: Any,
) -> PersonalizationDeliveryCapture:
    evidence = getattr(projection, "evidence", None)
    capture_value = getattr(evidence, "delivery_capture", None)
    if capture_value is None:
        projection_map = _mapping(projection, "projection")
        evidence_map = projection_map.get("evidence")
        if isinstance(evidence_map, Mapping):
            capture_value = evidence_map.get("delivery_capture")
    try:
        capture = (
            capture_value
            if isinstance(capture_value, PersonalizationDeliveryCapture)
            else PersonalizationDeliveryCapture.from_mapping(
                _mapping(capture_value, "projection.delivery_capture")
            )
        )
    except (TypeError, ValueError) as exc:
        raise PersonalizationDecisionRecorderError(
            "linked projection delivery capture is invalid"
        ) from exc
    if capture.status != "delivered":
        raise PersonalizationDecisionRecorderError(
            "new personal action requires a delivered prediction"
        )
    return capture


def _prediction_from_projection(projection: Any) -> dict[str, Any]:
    prediction = getattr(projection, "prediction", None)
    if prediction is None:
        projection_map = _mapping(projection, "projection")
        prediction = projection_map.get("prediction")
    return _mapping(prediction, "projection.prediction")


def _required_prediction_text(prediction: Mapping[str, Any], name: str) -> str:
    value = _text(prediction.get(name))
    if not value:
        raise PersonalizationDecisionRecorderError(
            f"new personal action requires prediction.{name}"
        )
    return value


class PersonalizationDecisionRecorder:
    """Record only an explicitly requested action with exact prediction lineage."""

    def __init__(
        self,
        journal_service: Any,
        *,
        controller: DecisionContinuityController | None = None,
        now: Callable[[], str] = _utc_now_iso,
    ) -> None:
        if journal_service is None:
            raise PersonalizationDecisionRecorderError("journal_service is required")
        self.journal_service = journal_service
        self.controller = controller or DecisionContinuityController(journal_service)
        self.now = now

    def record(
        self,
        *,
        projection: Any,
        action: str,
        decision_kind: str,
        request_id: str,
        action_at: str,
        recorded_at: str | None = None,
        note: str = "",
        next_review_at: str = "",
        actor: str = "",
        user_intent: str = "research",
        execution_state: str = "not_executed",
    ) -> PersonalizationDecisionRecord:
        """Append one exact action through the existing Journal writer.

        ``projection`` must be a previously built linked read-side projection;
        a population-only/not-delivered/unavailable projection cannot be used
        to backfill a personal action.  The caller explicitly invokes this
        method, so no user action is inferred from delivery or outcome data.
        """

        if action not in RESEARCH_ACTIONS:
            raise PersonalizationDecisionRecorderError(
                f"unsupported new personal research action: {action}"
            )
        if not _text(decision_kind):
            raise PersonalizationDecisionRecorderError("decision_kind is required")
        resolved_request_id = _text(request_id)
        if not resolved_request_id:
            raise PersonalizationDecisionRecorderError("request_id is required")
        if _text(getattr(projection, "status", "")) != "linked_prediction":
            raise PersonalizationDecisionRecorderError(
                "new personal action requires linked_prediction projection"
            )

        scope = _scope_from_projection(projection)
        capture = _capture_from_projection(projection)
        prediction = _prediction_from_projection(projection)
        result_id = _text(getattr(projection, "result_id", ""))
        stock_code = _text(getattr(projection, "stock_code", ""))
        if not result_id or not stock_code:
            projection_map = _mapping(projection, "projection")
            result_id = _text(projection_map.get("result_id"))
            stock_code = _text(projection_map.get("stock_code"))
        if not result_id or not stock_code:
            raise PersonalizationDecisionRecorderError(
                "linked projection candidate identity is incomplete"
            )
        if capture.result_id != result_id or capture.stock_code != stock_code:
            raise PersonalizationDecisionRecorderError(
                "delivery capture candidate identity conflicts with projection"
            )
        if capture.scope.scope_id != scope.scope_id:
            raise PersonalizationDecisionRecorderError(
                "delivery capture scope conflicts with projection"
            )

        prediction_id = _required_prediction_text(prediction, "prediction_id")
        receipt_hash = _required_prediction_text(prediction, "projection_receipt_hash")
        horizon_value = prediction.get("horizon_days")
        if isinstance(horizon_value, bool) or not isinstance(horizon_value, int) or horizon_value <= 0:
            raise PersonalizationDecisionRecorderError(
                "prediction.horizon_days must be a positive integer"
            )
        cost_hash = _required_prediction_text(prediction, "cost_scenario_hash")
        label_contract_id = _required_prediction_text(prediction, "label_contract_id")
        return_basis = _required_prediction_text(prediction, "return_basis")
        if capture.prediction_id != prediction_id:
            raise PersonalizationDecisionRecorderError(
                "delivery capture prediction identity conflicts with projection"
            )
        if capture.projection_receipt_hash != receipt_hash:
            raise PersonalizationDecisionRecorderError(
                "delivery capture receipt identity conflicts with projection"
            )
        if capture.horizon_days != horizon_value:
            raise PersonalizationDecisionRecorderError(
                "delivery capture horizon conflicts with projection"
            )
        if capture.cost_scenario_hash != cost_hash:
            raise PersonalizationDecisionRecorderError(
                "delivery capture cost scenario conflicts with projection"
            )

        try:
            canonical_action_at = canonical_aware_datetime(action_at, "action_at")
        except (TypeError, ValueError) as exc:
            raise PersonalizationDecisionRecorderError(
                "personalization action clocks are invalid"
            ) from exc

        # Look up the request before reading the current candidate head.  A
        # retry is an immutable replay of the original command: a later
        # action may legitimately have moved the head, and an omitted
        # ``recorded_at`` must not call ``now`` and change the envelope.
        existing = self._existing_revision(resolved_request_id)
        existing_envelope: PersonalizationActionEnvelope | None = None
        if existing is not None:
            existing_payload = existing.payload.get("personalization_action")
            if not isinstance(existing_payload, Mapping):
                raise PersonalizationDecisionRecorderError(
                    "request id belongs to a legacy action without personal envelope"
                )
            try:
                existing_envelope = PersonalizationActionEnvelope.from_mapping(
                    existing_payload
                )
            except (TypeError, ValueError) as exc:
                raise PersonalizationDecisionRecorderError(
                    "existing personalization action envelope is invalid"
                ) from exc

        try:
            if existing_envelope is not None and recorded_at is None:
                canonical_recorded_at = existing_envelope.recorded_at
            else:
                canonical_recorded_at = canonical_aware_datetime(
                    recorded_at or self.now(),
                    "recorded_at",
                )
        except (TypeError, ValueError) as exc:
            raise PersonalizationDecisionRecorderError(
                "personalization action clocks are invalid"
            ) from exc
        try:
            delivered_at = canonical_aware_datetime(
                capture.delivered_at or "",
                "delivered_at",
            )
        except (TypeError, ValueError) as exc:
            raise PersonalizationDecisionRecorderError(
                "delivered prediction clock is invalid"
            ) from exc
        if canonical_action_at < delivered_at:
            raise PersonalizationDecisionRecorderError(
                "action_at must not precede delivered_at"
            )
        if canonical_recorded_at < canonical_action_at:
            raise PersonalizationDecisionRecorderError(
                "recorded_at must not precede action_at"
            )

        identity = DecisionIdentity(
            result_id=result_id,
            stock_code=stock_code,
            decision_date=_text(getattr(projection, "decision_date", "")),
        )
        if existing_envelope is not None:
            assert existing is not None
            if existing.decision_identity != identity:
                raise PersonalizationDecisionRecorderError(
                    "personalization action request id has a different decision identity"
                )
            expected_entity_id = self.controller.candidate_entity_id(identity)
            if existing.action != action or existing.entity_id != expected_entity_id:
                raise PersonalizationDecisionRecorderError(
                    "personalization action request id has a different action identity"
                )
            if existing.note != note.strip():
                raise PersonalizationDecisionRecorderError(
                    "personalization action request id has a different note"
                )
            if existing.next_review_at != next_review_at.strip():
                raise PersonalizationDecisionRecorderError(
                    "personalization action request id has a different review time"
                )
            if existing.actor != _text(actor):
                raise PersonalizationDecisionRecorderError(
                    "personalization action request id has a different actor"
                )

        state = None if existing_envelope is not None else self.controller.read_state(identity)
        if state is not None and not state.can_write:
            raise PersonalizationDecisionRecorderError(
                f"decision continuity is not writable: {state.blocked_reason}"
            )

        envelope = PersonalizationActionEnvelope(
            personalization_scope_id=scope.scope_id,
            result_id=result_id,
            stock_code=stock_code,
            prediction_id=prediction_id,
            prediction_receipt_hash=receipt_hash,
            decision_kind=_text(decision_kind),
            action=action,
            action_state="recorded",
            action_at=canonical_action_at,
            recorded_at=canonical_recorded_at,
            request_id=resolved_request_id,
            action_source="decision_continuity",
            actor=_text(actor),
            decision_revision_id=resolved_request_id,
            continuity_event_id=resolved_request_id,
            revision_of=(
                existing_envelope.revision_of
                if existing_envelope is not None
                else state.head_revision_id  # type: ignore[union-attr]
            ),
            user_intent=_text(user_intent) or "research",
            execution_state=_text(execution_state) or "not_executed",
            horizon_days=horizon_value,
            cost_scenario_hash=cost_hash,
            label_contract_id=label_contract_id,
            return_basis=return_basis,
        )

        # A retry with the same request id must return the original immutable
        # envelope.  Compare the fully reconstructed command, but preserve
        # the original ``revision_of`` and implicit recorded clock above.
        if existing_envelope is not None:
            assert existing is not None
            if existing_envelope != envelope:
                raise PersonalizationDecisionRecorderError(
                    "personalization action request id has a different envelope"
                )
            return PersonalizationDecisionRecord(
                revision=existing,
                envelope=existing_envelope,
            )

        writer = getattr(self.journal_service, "record_research_action", None)
        if not callable(writer):
            raise PersonalizationDecisionRecorderError(
                "existing Journal research-action writer is unavailable"
            )
        try:
            revision = writer(
                action,
                identity,
                note=note.strip(),
                body=note.strip() if action == "note" else "",
                title="研究動作",
                entity_id=state.candidate_entity_id,  # type: ignore[union-attr]
                next_review_at=next_review_at,
                actor=_text(actor),
                revision_id=resolved_request_id,
                continuity_event_id=resolved_request_id,
                revision_of=state.head_revision_id,  # type: ignore[union-attr]
                recorded_at=canonical_recorded_at,
                personalization_action=envelope.to_dict(),
            )
        except Exception as exc:  # noqa: BLE001 - preserve Journal's writer contract
            raise PersonalizationDecisionRecorderError(
                f"personalization action append failed:{type(exc).__name__}"
            ) from exc
        if not isinstance(revision, DecisionContinuityRevision):
            try:
                revision = DecisionContinuityRevision.from_mapping(
                    _mapping(revision, "journal revision")
                )
            except (TypeError, ValueError) as exc:
                raise PersonalizationDecisionRecorderError(
                    "personalization action writer returned invalid revision"
                ) from exc
        saved_payload = revision.payload.get("personalization_action")
        if not isinstance(saved_payload, Mapping):
            raise PersonalizationDecisionRecorderError(
                "personalization action readback envelope is missing"
            )
        try:
            saved_envelope = PersonalizationActionEnvelope.from_mapping(saved_payload)
        except (TypeError, ValueError) as exc:
            raise PersonalizationDecisionRecorderError(
                "personalization action readback envelope is invalid"
            ) from exc
        if saved_envelope != envelope:
            raise PersonalizationDecisionRecorderError(
                "personalization action readback envelope conflicts"
            )
        return PersonalizationDecisionRecord(revision=revision, envelope=saved_envelope)

    def _existing_revision(self, request_id: str) -> DecisionContinuityRevision | None:
        reader = getattr(self.journal_service, "list_decision_revisions", None)
        if not callable(reader):
            return None
        for raw in reader():
            if isinstance(raw, DecisionContinuityRevision):
                revision = raw
            elif isinstance(raw, Mapping):
                try:
                    revision = DecisionContinuityRevision.from_mapping(raw)
                except (TypeError, ValueError):
                    continue
            else:
                continue
            if revision.revision_id == request_id:
                return revision
        return None


__all__ = [
    "PersonalizationDecisionRecord",
    "PersonalizationDecisionRecorder",
    "PersonalizationDecisionRecorderError",
]
