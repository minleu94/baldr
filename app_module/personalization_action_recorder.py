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
import os
from pathlib import Path
from typing import Any, Callable, Mapping

from app_module.decision_continuity_controller import (
    DecisionContinuityController,
    RESEARCH_ACTIONS,
)
from app_module.dtos.decision_continuity_dtos import (
    ACTION_NOTE,
    DecisionContinuityRevision,
    DecisionIdentity,
)
from app_module.personalization_contract import (
    PersonalizationActionEnvelope,
    PersonalizationDeliveryCapture,
    PersonalizationDeliveryScope,
    PersonalRecommendationChoice,
    PersonalRecommendationModelEvidence,
    PersonalRecommendationOverrideReason,
    canonical_aware_datetime,
    parse_aware_datetime,
    read_personal_use_policy_snapshot_event,
)


class PersonalizationDecisionRecorderError(ValueError):
    """Raised when a new personal action cannot be exactly verified."""


@dataclass(frozen=True)
class PersonalizationDecisionRecord:
    """The existing continuity revision plus the persisted typed envelope."""

    revision: DecisionContinuityRevision
    envelope: PersonalizationActionEnvelope


@dataclass(frozen=True)
class PersonalRecommendationChoiceRecord:
    """既有 Journal revision 與 typed 個人決策選擇的精確讀回。"""

    revision: DecisionContinuityRevision
    choice: PersonalRecommendationChoice
    readback_verified: bool = True


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


def _thaw_json_value(value: Any, field_name: str) -> Any:
    """將 read model 的唯讀 JSON 容器還原成 JSON list/dict 比對形狀。

    ``RecommendationExecutionQueries`` 會把 JSON list 凍結成 tuple、object
    凍結成 ``MappingProxyType``。此處只還原容器，不轉字串或數值，也不排序，
    因而仍會檢查原始欄位型別、值與順序。
    """

    if isinstance(value, Mapping):
        thawed: dict[str, Any] = {}
        for key, item in value.items():
            if type(key) is not str:
                raise PersonalizationDecisionRecorderError(
                    f"{field_name} JSON object key must be str"
                )
            thawed[key] = _thaw_json_value(item, f"{field_name}.{key}")
        return thawed
    if type(value) in (tuple, list):
        return [
            _thaw_json_value(item, f"{field_name}[]") for item in value
        ]
    if value is None or type(value) in (str, int, float, bool):
        return value
    raise PersonalizationDecisionRecorderError(
        f"{field_name} contains a non-JSON value"
    )


def _thaw_json_mapping(value: Any, field_name: str) -> dict[str, Any]:
    thawed = _thaw_json_value(value, field_name)
    if type(thawed) is not dict:
        raise PersonalizationDecisionRecorderError(f"{field_name} must be an object")
    return thawed


def validate_personal_recommendation_choice_binding(
    raw_record: Mapping[str, Any],
    revision: DecisionContinuityRevision,
    choice: PersonalRecommendationChoice,
    *,
    expected_identity: DecisionIdentity,
) -> None:
    """Validate the typed choice against its complete outer Journal envelope.

    This applies only to ``personal_recommendation_choice`` records. Legacy
    Journal action parsing and retry behavior deliberately remain unchanged.
    """

    if not isinstance(raw_record, Mapping):
        raise ValueError("personal choice Journal record is not an object")
    if type(raw_record.get("record_type")) is not str or raw_record.get(
        "record_type"
    ) != "decision_continuity_revision":
        raise ValueError("personal choice Journal record type is invalid")
    if type(raw_record.get("action")) is not str or raw_record.get("action") != ACTION_NOTE:
        raise ValueError("personal choice must use ACTION_NOTE")
    if type(raw_record.get("entity_type")) is not str or raw_record.get(
        "entity_type"
    ) != "journal":
        raise ValueError("personal choice must be a Journal entity")
    request_id = choice.request_id
    if not request_id:
        raise ValueError("personal choice request id is missing")
    for field_name in ("revision_id", "continuity_event_id"):
        value = raw_record.get(field_name)
        if type(value) is not str or value != request_id:
            raise ValueError(f"personal choice outer {field_name} conflicts")
    if (
        revision.action != ACTION_NOTE
        or revision.entity_type != "journal"
        or revision.revision_id != request_id
        or revision.continuity_event_id != request_id
    ):
        raise ValueError("personal choice revision/event identity conflicts")

    identity_fields = {
        "result_id": expected_identity.result_id,
        "stock_code": expected_identity.stock_code,
        "source_snapshot_id": expected_identity.source_snapshot_id,
        "source_snapshot_hash": expected_identity.source_snapshot_hash,
        "decision_date": expected_identity.decision_date,
        "identity_status": expected_identity.identity_status,
    }
    if revision.decision_identity != expected_identity:
        raise ValueError("personal choice outer DecisionIdentity conflicts")
    raw_identity = raw_record.get("decision_identity")
    if not isinstance(raw_identity, Mapping):
        raise ValueError("personal choice outer DecisionIdentity is missing")
    for field_name, expected_value in identity_fields.items():
        for source_name, source in (
            ("nested", raw_identity),
            ("flattened", raw_record),
        ):
            value = source.get(field_name)
            if type(value) is not str or value != expected_value:
                raise ValueError(
                    f"personal choice {source_name} DecisionIdentity {field_name} conflicts"
                )
    for field_name, expected_value in (
        ("result_id", choice.result_id),
        ("stock_code", choice.stock_code),
        ("decision_date", choice.decision_date),
        ("source_snapshot_id", choice.source_snapshot_id),
        ("source_snapshot_hash", choice.source_snapshot_hash),
    ):
        if expected_value != identity_fields[field_name]:
            raise ValueError(f"personal choice payload {field_name} conflicts")

    journal_payload = raw_record.get("payload")
    if not isinstance(journal_payload, Mapping):
        raise ValueError("personal choice Journal payload is missing")
    raw_choice = journal_payload.get("personal_recommendation_choice")
    if not isinstance(raw_choice, Mapping):
        raise ValueError("personal choice typed payload is missing")
    if _thaw_json_mapping(raw_choice, "personal choice payload") != choice.to_dict():
        raise ValueError("personal choice typed payload conflicts with parsed choice")

    expected_payload_fields = {
        "linked_type": "recommendation_result",
        "linked_id": choice.result_id,
        "source_type": "personal_recommendation_choice",
        "source_id": choice.result_id,
        "source_snapshot_id": choice.source_snapshot_id,
        "source_snapshot_hash": choice.source_snapshot_hash,
        "stock_code": choice.stock_code,
    }
    for field_name, expected_value in expected_payload_fields.items():
        for source_name, source in (
            ("outer", raw_record),
            ("payload", journal_payload),
        ):
            value = source.get(field_name)
            if type(value) is not str or value != expected_value:
                raise ValueError(
                    f"personal choice {source_name} {field_name} conflicts"
                )
    entity_id = raw_record.get("entity_id")
    if (
        type(entity_id) is not str
        or not entity_id
        or revision.entity_id != entity_id
        or journal_payload.get("journal_id") != entity_id
    ):
        raise ValueError("personal choice Journal entity identity conflicts")

    outer_created_at = raw_record.get("created_at")
    payload_created_at = journal_payload.get("created_at")
    if type(outer_created_at) is not str or not outer_created_at:
        raise ValueError("personal choice outer created_at is missing")
    if type(payload_created_at) is not str or not payload_created_at:
        raise ValueError("personal choice payload created_at is missing")
    outer_clock = canonical_aware_datetime(
        outer_created_at, "personal choice Journal created_at"
    )
    payload_clock = canonical_aware_datetime(
        payload_created_at, "personal choice Journal payload created_at"
    )
    recorded_clock = canonical_aware_datetime(
        choice.recorded_at, "personal choice recorded_at"
    )
    revision_clock = canonical_aware_datetime(
        revision.created_at, "personal choice revision created_at"
    )
    if not (outer_clock == payload_clock == recorded_clock == revision_clock):
        raise ValueError("personal choice Journal clock conflicts with recorded_at")


def _normalized_absolute_path(value: object, field_name: str) -> str:
    text = _text(value)
    if not text or not Path(text).is_absolute():
        raise PersonalizationDecisionRecorderError(
            f"{field_name} must be an absolute path"
        )
    # 只做純字串路徑標準化，不檢查或讀取目前的候選目錄。
    return os.path.normcase(os.path.normpath(text))


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
        canonical_execution_reader: Callable[[str], Any] | None = None,
        now: Callable[[], str] = _utc_now_iso,
    ) -> None:
        if journal_service is None:
            raise PersonalizationDecisionRecorderError("journal_service is required")
        self.journal_service = journal_service
        self.controller = controller or DecisionContinuityController(journal_service)
        self.canonical_execution_reader = canonical_execution_reader
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

    def record_personal_recommendation_choice(
        self,
        *,
        result_id: str,
        stock_code: str,
        choice: str,
        request_id: str,
        override_reason: PersonalRecommendationOverrideReason | Mapping[str, Any] | None = None,
        note: str = "",
        actor: str = "",
    ) -> PersonalRecommendationChoiceRecord:
        """將明確個人採用／拒絕／推翻保存到既有 ACTION_NOTE stream。

        Canonical result 與同次 policy event 是唯一來源。舊結果缺少 event
        時拒絕以今日設定補標；模型證據只取所選股票的已驗證有效 projection。
        """

        resolved_result_id = _text(result_id)
        resolved_stock_code = _text(stock_code)
        resolved_request_id = _text(request_id)
        if not resolved_result_id or not resolved_stock_code or not resolved_request_id:
            raise PersonalizationDecisionRecorderError(
                "result_id、stock_code、request_id 均為必填"
            )
        if choice not in {"adopt", "reject", "override"}:
            raise PersonalizationDecisionRecorderError(
                "choice 必須是 adopt、reject 或 override"
            )
        if self.canonical_execution_reader is None:
            raise PersonalizationDecisionRecorderError(
                "canonical recommendation exact reader is unavailable"
            )
        try:
            read_model = self.canonical_execution_reader(resolved_result_id)
        except Exception as exc:  # noqa: BLE001 - keep the writer fail-closed
            raise PersonalizationDecisionRecorderError(
                f"canonical recommendation read failed:{type(exc).__name__}"
            ) from exc
        if read_model is None or getattr(
            read_model, "integrity_basis", ""
        ) != "canonical_payload_and_index_verified":
            raise PersonalizationDecisionRecorderError(
                "個人選擇只接受 canonical payload 與 index 已驗證的保存推薦"
            )
        execution = getattr(read_model, "execution", None)
        if execution is None or _text(getattr(read_model, "result_id", "")) != resolved_result_id:
            raise PersonalizationDecisionRecorderError(
                "canonical recommendation exact identity is unavailable"
            )
        status = getattr(getattr(execution, "status", None), "value", None)
        if status != "completed" or getattr(execution, "decision", None) is None:
            raise PersonalizationDecisionRecorderError(
                "個人選擇需要一筆已完成且有決策列的保存推薦"
            )
        matching_items = [
            item
            for item in getattr(execution, "items", ())
            if _text(getattr(item, "stock_code", "")) == resolved_stock_code
        ]
        if len(matching_items) != 1:
            raise PersonalizationDecisionRecorderError(
                "所選股票必須唯一存在於這筆保存推薦"
            )
        context = getattr(execution, "context", None)
        saved_day = getattr(context, "as_of_date", None)
        saved_day_isoformat = getattr(saved_day, "isoformat", None)
        decision_date = saved_day_isoformat() if callable(saved_day_isoformat) else ""
        if not decision_date:
            raise PersonalizationDecisionRecorderError(
                "保存推薦缺少明確決策日期，不能建立個人選擇"
            )
        source_snapshot_id, source_snapshot_hash = self._choice_source_snapshot(context)
        if not source_snapshot_id:
            raise PersonalizationDecisionRecorderError(
                "保存推薦缺少明確 source snapshot identity；不會以目前來源補值"
            )
        if not source_snapshot_hash:
            raise PersonalizationDecisionRecorderError(
                "保存推薦缺少 source snapshot hash；不會以目前來源補值"
            )
        try:
            policy_event = read_personal_use_policy_snapshot_event(
                execution,
                expected_result_id=resolved_result_id,
            )
        except (TypeError, ValueError) as exc:
            raise PersonalizationDecisionRecorderError(str(exc)) from exc
        policy_snapshot = policy_event["policy_snapshot"]
        requested_mode = str(policy_event["requested_mode"])
        effective_mode = str(policy_event["effective_mode"])
        model_evidence = self.validate_selected_stock_model_evidence(
            read_model=read_model,
            execution=execution,
            stock_code=resolved_stock_code,
            decision_date=decision_date,
            policy_snapshot=policy_snapshot,
            requested_mode=requested_mode,
            event_effective_mode=effective_mode,
        )
        choice_effective_mode = (
            "personal_calibrated_probability"
            if model_evidence is not None
            else "rule_only"
        )
        if override_reason is not None and not isinstance(
            override_reason, PersonalRecommendationOverrideReason
        ):
            try:
                override_reason = PersonalRecommendationOverrideReason.from_mapping(
                    _mapping(override_reason, "override_reason")
                )
            except (TypeError, ValueError) as exc:
                raise PersonalizationDecisionRecorderError(
                    "override_reason is invalid"
                ) from exc

        identity = DecisionIdentity(
            result_id=resolved_result_id,
            stock_code=resolved_stock_code,
            decision_date=decision_date,
            source_snapshot_id=source_snapshot_id,
            source_snapshot_hash=source_snapshot_hash,
        )
        note_text = note.strip() or f"個人推薦選擇：{choice}"
        history_snapshot, history_token = self._journal_snapshot()
        prior_match = self._personal_choice_revision_from_records(
            history_snapshot, resolved_request_id
        )
        if prior_match is not None:
            prior_raw, prior, prior_choice = prior_match
            try:
                validate_personal_recommendation_choice_binding(
                    prior_raw,
                    prior,
                    prior_choice,
                    expected_identity=identity,
                )
            except (TypeError, ValueError) as exc:
                raise PersonalizationDecisionRecorderError(
                    f"existing personal choice outer binding is invalid:{exc}"
                ) from exc
            if parse_aware_datetime(
                prior_choice.action_at, "personal choice action_at"
            ) < parse_aware_datetime(policy_event["decision_at"], "decision_at"):
                raise PersonalizationDecisionRecorderError(
                    "personal choice action time precedes the saved recommendation"
                )
            if parse_aware_datetime(
                prior_choice.recorded_at, "personal choice recorded_at"
            ) < parse_aware_datetime(policy_event["decision_at"], "decision_at"):
                raise PersonalizationDecisionRecorderError(
                    "personal choice recorded time precedes the saved recommendation"
                )
            expected_choice = self._build_choice(
                read_model=read_model,
                result_id=resolved_result_id,
                stock_code=resolved_stock_code,
                decision_date=decision_date,
                source_snapshot_id=source_snapshot_id,
                source_snapshot_hash=source_snapshot_hash,
                choice=choice,
                requested_mode=requested_mode,
                effective_mode=choice_effective_mode,
                action_at=prior_choice.action_at,
                recorded_at=prior_choice.recorded_at,
                request_id=resolved_request_id,
                policy_snapshot=policy_snapshot,
                override_reason=override_reason,
                model_evidence=model_evidence,
            )
            if (
                prior_choice != expected_choice
                or prior.note != note_text
                or prior.actor != _text(actor)
            ):
                raise PersonalizationDecisionRecorderError(
                    "personal choice request id has different content"
                )
            confirmed_records, confirmed_token = self._journal_snapshot()
            if confirmed_token != history_token:
                raise PersonalizationDecisionRecorderError(
                    "journal changed while confirming an idempotent choice retry"
                )
            confirmed_match = self._personal_choice_revision_from_records(
                confirmed_records, resolved_request_id
            )
            if confirmed_match is None:
                raise PersonalizationDecisionRecorderError(
                    "personal choice disappeared while confirming an idempotent retry"
                )
            confirmed_raw, confirmed_revision, confirmed_choice = confirmed_match
            try:
                validate_personal_recommendation_choice_binding(
                    confirmed_raw,
                    confirmed_revision,
                    confirmed_choice,
                    expected_identity=identity,
                )
            except (TypeError, ValueError) as exc:
                raise PersonalizationDecisionRecorderError(
                    f"personal choice retry confirmation is invalid:{exc}"
                ) from exc
            if (
                confirmed_revision != prior
                or confirmed_choice != prior_choice
                or confirmed_revision.note != note_text
                or confirmed_revision.actor != _text(actor)
            ):
                raise PersonalizationDecisionRecorderError(
                    "journal changed while confirming an idempotent choice retry"
                )
            return PersonalRecommendationChoiceRecord(
                confirmed_revision, confirmed_choice
            )

        state = self.controller.read_state(identity)
        if not state.can_write:
            raise PersonalizationDecisionRecorderError(
                f"decision continuity is not writable: {state.blocked_reason}"
            )
        # A second snapshot brackets the state read; if the journal moved while
        # the candidate identity was checked, do not append against stale state.
        latest_records, latest_token = self._journal_snapshot()
        if latest_token != history_token:
            raise PersonalizationDecisionRecorderError(
                "journal changed during choice validation; retry with a new read"
            )
        if (
            self._personal_choice_revision_from_records(
                latest_records, resolved_request_id
            )
            is not None
        ):
            raise PersonalizationDecisionRecorderError(
                "journal changed during choice validation; retry with a new read"
            )

        action_at = canonical_aware_datetime(self.now(), "action_at")
        recorded_at = canonical_aware_datetime(self.now(), "recorded_at")
        decision_clock = parse_aware_datetime(
            policy_event["decision_at"], "personal policy event decision_at"
        )
        if (
            parse_aware_datetime(action_at, "action_at") < decision_clock
            or parse_aware_datetime(recorded_at, "recorded_at") < decision_clock
        ):
            raise PersonalizationDecisionRecorderError(
                "個人選擇時間不可早於原推薦決策時間"
            )
        choice_record = self._build_choice(
            read_model=read_model,
            result_id=resolved_result_id,
            stock_code=resolved_stock_code,
            decision_date=decision_date,
            source_snapshot_id=source_snapshot_id,
            source_snapshot_hash=source_snapshot_hash,
            choice=choice,
            requested_mode=requested_mode,
            effective_mode=choice_effective_mode,
            action_at=action_at,
            recorded_at=recorded_at,
            request_id=resolved_request_id,
            policy_snapshot=policy_snapshot,
            override_reason=override_reason,
            model_evidence=model_evidence,
        )
        entity_id = f"{state.candidate_entity_id}:personal-choice:{resolved_request_id}"
        try:
            revision = self.journal_service.record_decision_action(
                ACTION_NOTE,
                identity,
                note=note_text,
                body=note_text,
                title="個人推薦決策",
                entity_id=entity_id,
                linked_type="recommendation_result",
                linked_id=resolved_result_id,
                tags=["personal-recommendation-choice"],
                source_type="personal_recommendation_choice",
                source_id=resolved_result_id,
                source_snapshot_id=source_snapshot_id,
                source_snapshot_hash=source_snapshot_hash,
                actor=_text(actor),
                revision_id=resolved_request_id,
                continuity_event_id=resolved_request_id,
                recorded_at=recorded_at,
                personal_recommendation_choice=choice_record.to_dict(),
                expected_history_token=history_token,
            )
        except Exception as exc:  # noqa: BLE001 - preserve Journal error details
            raise PersonalizationDecisionRecorderError(
                f"personal recommendation choice append failed:{type(exc).__name__}"
            ) from exc
        if not isinstance(revision, DecisionContinuityRevision):
            try:
                revision = DecisionContinuityRevision.from_mapping(
                    _mapping(revision, "personal recommendation choice revision")
                )
            except (TypeError, ValueError) as exc:
                raise PersonalizationDecisionRecorderError(
                    "personal choice writer returned an invalid revision"
                ) from exc
        readback_records, _readback_token = self._journal_snapshot()
        saved_match = self._personal_choice_revision_from_records(
            readback_records, resolved_request_id
        )
        if saved_match is None:
            raise PersonalizationDecisionRecorderError(
                "personal choice journal readback is missing"
            )
        saved_raw, saved, saved_choice = saved_match
        try:
            validate_personal_recommendation_choice_binding(
                saved_raw,
                saved,
                saved_choice,
                expected_identity=identity,
            )
        except (TypeError, ValueError) as exc:
            raise PersonalizationDecisionRecorderError(
                f"personal choice journal readback binding is invalid:{exc}"
            ) from exc
        if saved_choice != choice_record or saved != revision:
            raise PersonalizationDecisionRecorderError(
                "personal choice journal readback conflicts with the command"
            )
        return PersonalRecommendationChoiceRecord(saved, saved_choice)

    @staticmethod
    def _choice_source_snapshot(context: Any) -> tuple[str, str]:
        universe = getattr(context, "universe_identity", None)
        snapshot = getattr(universe, "snapshot", None)
        snapshot_id = _text(getattr(snapshot, "universe_snapshot_id", ""))
        snapshot_hash = _text(getattr(snapshot, "universe_snapshot_hash", ""))
        if snapshot_id or snapshot_hash:
            return snapshot_id, snapshot_hash
        universe_ref = getattr(context, "universe_snapshot_ref", None)
        if universe_ref is not None:
            return _text(getattr(universe_ref, "reference_id", "")), ""
        data_refs = tuple(getattr(context, "data_snapshot_refs", ()))
        if len(data_refs) == 1:
            return _text(getattr(data_refs[0], "reference_id", "")), ""
        return "", ""

    @staticmethod
    def validate_selected_stock_model_evidence(
        *,
        read_model: Any,
        execution: Any,
        stock_code: str,
        decision_date: str,
        policy_snapshot: Mapping[str, Any],
        requested_mode: str,
        event_effective_mode: str,
    ) -> PersonalRecommendationModelEvidence | None:
        """依 canonical saved projection 驗證所選股票的模型證據。

        writer 與唯讀 Journal projection 共用此驗證，避免 run-level effective
        mode 取代 selected-stock mode，或讓重算 choice hash 的竄改資料被信任。
        """

        if requested_mode not in {"rule_only", "personal_calibrated_probability"}:
            raise PersonalizationDecisionRecorderError(
                "保存推薦的個人模式無法辨識"
            )
        if event_effective_mode not in {"rule_only", "personal_calibrated_probability"}:
            raise PersonalizationDecisionRecorderError(
                "保存推薦的實際個人模式無法辨識"
            )
        bindings = tuple(getattr(execution, "ml_receipt_refs", ()))
        projection_refs = tuple(getattr(execution, "ml_projection_refs", ()))
        read_rows = tuple(getattr(read_model, "ml_projection_rows", ()))
        read_status = _text(getattr(read_model, "ml_read_status", ""))

        if requested_mode == "rule_only":
            if event_effective_mode != "rule_only":
                raise PersonalizationDecisionRecorderError(
                    "rule-only 設定與保存結果的模型輸出矛盾"
                )
            if bindings or projection_refs or read_rows:
                raise PersonalizationDecisionRecorderError(
                    "rule-only 保存結果含模型輸出或殘留 receipt，拒絕記錄個人選擇"
                )
            return None

        if not bindings and not projection_refs and not read_rows:
            if event_effective_mode != "rule_only" or read_status not in {
                "not_requested",
                "unavailable",
            }:
                raise PersonalizationDecisionRecorderError(
                    "模型身分或投影狀態無法核驗；請重新產生並保存推薦後再記錄選擇"
                )
            return None
        if read_status != "verified":
            raise PersonalizationDecisionRecorderError(
                "模型 receipt 或投影讀回未通過驗證；請重新保存推薦後再記錄選擇"
            )

        candidate = policy_snapshot.get("candidate")
        if not isinstance(candidate, Mapping):
            raise PersonalizationDecisionRecorderError(
                "個人模型政策缺少已 pin 的候選身分"
            )
        candidate_id = _text(candidate.get("candidate_id"))
        if len(bindings) != 1 or len(projection_refs) != 1 or not candidate_id:
            raise PersonalizationDecisionRecorderError(
                "模型 receipt 與投影必須唯一且綁定同一候選"
            )
        binding = bindings[0]
        binding_date = getattr(binding, "decision_date", None)
        binding_date_isoformat = getattr(binding_date, "isoformat", None)
        if (
            _text(getattr(binding, "model_candidate_id", "")) != candidate_id
            or _text(getattr(binding, "result_id", ""))
            != _text(getattr(read_model, "result_id", ""))
            or not callable(binding_date_isoformat)
            or binding_date_isoformat() != decision_date
        ):
            raise PersonalizationDecisionRecorderError(
                "模型 receipt 的結果或日期身分與保存推薦不符"
            )
        projection_reference = _text(getattr(projection_refs[0], "reference_id", ""))
        receipt_reference = getattr(binding, "receipt_ref", None)
        receipt_path = _text(getattr(receipt_reference, "reference_id", ""))
        receipt_hash = _text(getattr(binding, "receipt_hash", ""))
        if not projection_reference or not receipt_path or not receipt_hash:
            raise PersonalizationDecisionRecorderError(
                "模型 receipt/projection reference 不完整"
            )
        try:
            from ml_module.recommendation_inference_provenance import (
                read_inference_projection_receipt,
            )

            receipt = read_inference_projection_receipt(
                receipt_path,
                expected_receipt_hash=receipt_hash,
                expected_decision_date=decision_date,
                expected_candidate_id=candidate_id,
                expected_result_id=_text(getattr(read_model, "result_id", "")),
                expected_cost_scenario_hash=getattr(
                    binding, "cost_scenario_hash", None
                ),
            )
        except Exception as exc:  # noqa: BLE001 - a broken receipt is never rule-only
            raise PersonalizationDecisionRecorderError(
                f"模型 receipt 身分無法核驗:{type(exc).__name__}"
            ) from exc
        if Path(receipt_path).expanduser().resolve() != Path(
            receipt.receipt_path or ""
        ).resolve():
            raise PersonalizationDecisionRecorderError(
                "模型 receipt path reference 與已讀 receipt 不一致"
            )
        body = receipt.payload
        if body.get("projection_rows_sha256") != projection_reference:
            raise PersonalizationDecisionRecorderError(
                "保存的 projection reference 未綁定模型 receipt rows"
            )
        receipt_candidate = body.get("candidate_identity")
        if not isinstance(receipt_candidate, Mapping):
            raise PersonalizationDecisionRecorderError(
                "模型 receipt 缺少候選身分"
            )
        expected_candidate_fields = {
            "candidate_id": "candidate_id",
            "candidate_manifest_hash": "candidate_manifest_hash",
            "candidate_artifact_hash": "candidate_artifact_hash",
            "candidate_freeze_hash": "candidate_freeze_hash",
            "dataset_hash": "dataset_hash",
        }
        for policy_key, receipt_key in expected_candidate_fields.items():
            expected_value = _text(candidate.get(policy_key))
            actual_value = _text(receipt_candidate.get(receipt_key))
            if not expected_value or actual_value != expected_value:
                raise PersonalizationDecisionRecorderError(
                    f"模型 receipt 候選身分與保存政策不符:{policy_key}"
                )
        expected_root = _normalized_absolute_path(
            candidate.get("candidate_root"), "policy candidate_root"
        )
        actual_root = _normalized_absolute_path(
            receipt_candidate.get("candidate_root"), "receipt candidate_root"
        )
        if actual_root != expected_root:
            raise PersonalizationDecisionRecorderError(
                "模型 receipt 候選身分與保存政策不符:candidate_root"
            )
        for receipt_key in (
            "candidate_json_sha256",
            "personal_candidate_json_sha256",
        ):
            declared_json_hash = receipt_candidate.get(receipt_key)
            if declared_json_hash is not None and _text(declared_json_hash) != _text(
                candidate.get("candidate_json_sha256")
            ):
                raise PersonalizationDecisionRecorderError(
                    "模型 receipt candidate.json pin 與保存政策不符"
                )
        raw_rows = body.get("projections")
        if type(raw_rows) is not list or not raw_rows:
            raise PersonalizationDecisionRecorderError(
                "模型 receipt 缺少已保存 projection rows"
            )
        raw_codes = tuple(
            _text(item.get("stock_code"))
            for item in raw_rows
            if isinstance(item, Mapping)
        )
        binding_codes = tuple(getattr(binding, "projected_stock_codes", ()))
        if (
            len(raw_codes) != len(raw_rows)
            or raw_codes != binding_codes
            or len(raw_codes) != len(set(raw_codes))
        ):
            raise PersonalizationDecisionRecorderError(
                "模型 receipt projection row 身分與 execution binding 不符"
            )
        detached_read_rows = tuple(
            _thaw_json_mapping(item, "read_model.ml_projection_rows")
            for item in read_rows
        )
        detached_receipt_rows = tuple(
            _thaw_json_mapping(item, "receipt.projections") for item in raw_rows
        )
        if detached_read_rows != detached_receipt_rows:
            raise PersonalizationDecisionRecorderError(
                "模型 receipt rows 與 canonical read model 不一致"
            )
        for saved_row in detached_receipt_rows:
            if saved_row.get("status") == "active_candidate":
                saved_probability = saved_row.get("calibrated_probability_bp")
                if (
                    saved_row.get("calibrated_probability_status")
                    != "active_effective"
                    or isinstance(saved_probability, bool)
                    or type(saved_probability) is not int
                    or not 0 <= saved_probability <= 10_000
                    or _text(saved_row.get("model_version")) != candidate_id
                ):
                    raise PersonalizationDecisionRecorderError(
                        "模型 receipt 含無效或矛盾的 active projection row"
                    )
            elif not PersonalizationDecisionRecorder._is_explicit_rule_only_fallback(
                saved_row
            ):
                raise PersonalizationDecisionRecorderError(
                    "模型 receipt 含未識別的 projection/fallback row"
                )
        matching_rows = [
            item for item in detached_receipt_rows
            if _text(item.get("stock_code")) == stock_code
        ]
        if len(matching_rows) != 1:
            raise PersonalizationDecisionRecorderError(
                "模型 receipt 未唯一保存所選股票的 projection/fallback 狀態"
            )
        row = matching_rows[0]

        row_has_model_output = row.get("status") == "active_candidate"
        any_model_output = any(
            item.get("status") == "active_candidate"
            for item in detached_receipt_rows
        )
        if (event_effective_mode == "personal_calibrated_probability") != any_model_output:
            raise PersonalizationDecisionRecorderError(
                "policy event 實際模式與保存 receipt 的模型輸出狀態矛盾"
            )
        if not row_has_model_output:
            if not PersonalizationDecisionRecorder._is_explicit_rule_only_fallback(
                row
            ):
                raise PersonalizationDecisionRecorderError(
                    "所選股票的模型投影狀態不完整或矛盾；請重新產生並保存推薦"
                )
            return None

        probability = row.get("calibrated_probability_bp")
        model_version = _text(row.get("model_version"))
        if (
            row.get("calibrated_probability_status") != "active_effective"
            or isinstance(probability, bool)
            or type(probability) is not int
            or not 0 <= probability <= 10_000
            or model_version != candidate_id
            or event_effective_mode != "personal_calibrated_probability"
        ):
            raise PersonalizationDecisionRecorderError(
                "所選股票的模型投影身分或數值無法核驗"
            )
        ranking_score = row.get("ranking_score_bp")
        if ranking_score is not None and (isinstance(ranking_score, bool) or type(ranking_score) is not int):
            raise PersonalizationDecisionRecorderError(
                "所選股票的模型排序分數型別無法核驗"
            )
        try:
            return PersonalRecommendationModelEvidence(
                candidate_id=candidate_id,
                candidate_root=_text(candidate.get("candidate_root")),
                candidate_json_sha256=_text(candidate.get("candidate_json_sha256")),
                candidate_manifest_hash=_text(candidate.get("candidate_manifest_hash")),
                candidate_artifact_hash=_text(candidate.get("candidate_artifact_hash")),
                candidate_freeze_hash=_text(candidate.get("candidate_freeze_hash")),
                dataset_hash=_text(candidate.get("dataset_hash")),
                receipt_reference=str(receipt.receipt_path),
                receipt_hash=receipt_hash,
                projection_reference=projection_reference,
                projection_rows_sha256=projection_reference,
                stock_code=stock_code,
                decision_date=decision_date,
                model_version=model_version,
                ranking_score_bp=ranking_score,
                calibrated_probability_bp=probability,
                calibrated_probability_status="active_effective",
                cost_scenario_hash=getattr(binding, "cost_scenario_hash", None),
            )
        except (TypeError, ValueError) as exc:
            raise PersonalizationDecisionRecorderError(
                "所選股票的模型證據欄位不完整"
            ) from exc

    @staticmethod
    def _is_explicit_rule_only_fallback(row: Mapping[str, Any]) -> bool:
        if (
            row.get("status") != "rule_only"
            or row.get("ranking_method") != "rule_only"
            or row.get("calibrated_probability_status") != "unavailable"
            or row.get("after_cost_profit_probability_status") != "unavailable"
            or row.get("probability_baseline_kind") != "unavailable"
            or row.get("provenance_status") != "unavailable"
            or _text(row.get("model_version"))
            or _text(row.get("dataset_version"))
        ):
            return False
        probability_fields = (
            "calibrated_probability_bp",
            "after_cost_profit_probability_bp",
            "probability_baseline_probability_bp",
            "population_probability_bp",
            "raw_calibrated_probability_bp",
            "raw_after_cost_profit_probability_bp",
        )
        if any(row.get(name) is not None for name in probability_fields):
            return False
        warnings = row.get("warnings")
        compatibility = row.get("provenance_compatibility")
        if warnings is None or type(warnings) not in (list, tuple) or not warnings:
            return False
        if not all(type(item) is str and item.strip() for item in warnings):
            return False
        if not isinstance(compatibility, Mapping):
            return False
        reason = compatibility.get("reason")
        return (
            compatibility.get("status") == "blocked"
            and type(reason) is str
            and bool(reason.strip())
        )

    @staticmethod
    def _build_choice(
        *,
        read_model: Any,
        result_id: str,
        stock_code: str,
        decision_date: str,
        source_snapshot_id: str,
        source_snapshot_hash: str,
        choice: str,
        requested_mode: str,
        effective_mode: str,
        action_at: str,
        recorded_at: str,
        request_id: str,
        policy_snapshot: Mapping[str, Any],
        override_reason: PersonalRecommendationOverrideReason | None,
        model_evidence: PersonalRecommendationModelEvidence | None,
    ) -> PersonalRecommendationChoice:
        payload_hash = _text(getattr(read_model, "payload_hash", ""))
        artifact_hash = _text(getattr(read_model, "raw_artifact_sha256", ""))
        if not payload_hash or not artifact_hash:
            raise PersonalizationDecisionRecorderError(
                "canonical recommendation readback lacks exact content hashes"
            )
        return PersonalRecommendationChoice(
            result_id=result_id,
            stock_code=stock_code,
            decision_date=decision_date,
            source_snapshot_id=source_snapshot_id,
            source_snapshot_hash=source_snapshot_hash,
            canonical_payload_hash=payload_hash,
            raw_artifact_sha256=artifact_hash,
            choice=choice,
            requested_mode=requested_mode,
            effective_mode=effective_mode,
            action_at=action_at,
            recorded_at=recorded_at,
            request_id=request_id,
            policy_snapshot=policy_snapshot,
            override_reason=override_reason,
            model_evidence=model_evidence,
        )

    def _journal_snapshot(self) -> tuple[list[Mapping[str, Any]], str]:
        store = getattr(self.journal_service, "store", None)
        loader = getattr(store, "load_journal_snapshot", None)
        if not callable(loader):
            raise PersonalizationDecisionRecorderError(
                "Journal store does not support compare-and-append snapshots"
            )
        records, token = loader()
        if not isinstance(records, list) or not _text(token):
            raise PersonalizationDecisionRecorderError(
                "Journal store returned an invalid history snapshot"
            )
        return records, str(token)

    @staticmethod
    def _personal_choice_revision_from_records(
        records: list[Mapping[str, Any]], request_id: str
    ) -> tuple[Mapping[str, Any], DecisionContinuityRevision, PersonalRecommendationChoice] | None:
        """Find a new typed choice by either outer id or its inner request id.

        The ordinary revision lookup remains untouched for legacy actions. For
        this typed choice, checking all three identities prevents a modified
        outer revision/event pair from making an existing request look new.
        """

        matches: list[Mapping[str, Any]] = []
        for raw in records:
            if not isinstance(raw, Mapping):
                continue
            payload = raw.get("payload")
            choice_value = (
                payload.get("personal_recommendation_choice")
                if isinstance(payload, Mapping)
                else None
            )
            inner_request_id = (
                choice_value.get("request_id")
                if isinstance(choice_value, Mapping)
                else None
            )
            if (
                (type(raw.get("revision_id")) is str and raw.get("revision_id") == request_id)
                or (
                    type(raw.get("continuity_event_id")) is str
                    and raw.get("continuity_event_id") == request_id
                )
                or (type(inner_request_id) is str and inner_request_id == request_id)
            ):
                matches.append(raw)

        if len(matches) > 1:
            raise PersonalizationDecisionRecorderError(
                "personal choice request id is duplicated in Journal history"
            )
        if not matches:
            return None
        raw = matches[0]
        try:
            revision = DecisionContinuityRevision.from_mapping(raw)
        except (TypeError, ValueError) as exc:
            raise PersonalizationDecisionRecorderError(
                "request_id already exists with an invalid Journal revision"
            ) from exc
        payload = raw.get("payload")
        choice_value = (
            payload.get("personal_recommendation_choice")
            if isinstance(payload, Mapping)
            else None
        )
        if revision.action != ACTION_NOTE or not isinstance(choice_value, Mapping):
            raise PersonalizationDecisionRecorderError(
                "request_id 已用於其他 Journal action"
            )
        try:
            choice = PersonalRecommendationChoice.from_mapping(choice_value)
        except (TypeError, ValueError) as exc:
            raise PersonalizationDecisionRecorderError(
                "existing personal choice is invalid"
            ) from exc
        return raw, revision, choice

    @staticmethod
    def _revision_from_records(
        records: list[Mapping[str, Any]], request_id: str
    ) -> DecisionContinuityRevision | None:
        for raw in records:
            if not isinstance(raw, Mapping) or _text(raw.get("revision_id")) != request_id:
                continue
            try:
                return DecisionContinuityRevision.from_mapping(raw)
            except (TypeError, ValueError) as exc:
                raise PersonalizationDecisionRecorderError(
                    "request_id already exists with an invalid Journal revision"
                ) from exc
        return None

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
    "PersonalRecommendationChoiceRecord",
    "validate_personal_recommendation_choice_binding",
]
