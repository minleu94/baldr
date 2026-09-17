"""Recommendation save path 的 personalisation delivery composition adapter。

這個 adapter 只把 caller-owned local research scope 綁到既有
``RecommendationResultDTO.run_context``／candidate provenance，並透過既有
recommendation repository 做 save/readback。它不建立第二個 ledger，也不
修改既有 immutable projection receipt 或任何 action/order state。
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from app_module.dtos import RecommendationResultDTO
from app_module.personalization_contract import (
    PERSONALIZATION_DELIVERY_ACK_SCHEMA_VERSION,
    PERSONALIZATION_DELIVERY_CAPTURE_SCHEMA_VERSION,
    PersonalizationDeliveryCapture,
    PersonalizationDeliveryScope,
    canonical_aware_datetime,
    inspect_personalization_temporal_context,
)
from app_module.personalization_projection import (
    PersonalizationDeliveryCaptureService,
    PersonalizationProjectionError,
)


LOCAL_RESEARCH_SCOPE_ID = "local_research_scope_v1"
LOCAL_RESEARCH_SCOPE_TYPE = "local"
PERSONALIZATION_CAPTURE_CONTEXT_KEY = "personalization_delivery_captures"


class PersonalizationSaveAdapterError(PersonalizationProjectionError):
    """Raised when save/readback or delivery ACK identity cannot be verified."""


@dataclass(frozen=True)
class RecommendationDeliveryAckOutcome:
    """Exact result/scope delivery ACK outcome."""

    result_id: str
    scope_id: str
    delivery_id: str
    delivered_at: str
    capture_hashes: tuple[str, ...]
    status: str = "delivered"


def _text(value: object) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        converted = to_dict()
        if isinstance(converted, Mapping):
            return {str(key): item for key, item in converted.items()}
    return {}


def _first_text(*values: object) -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return ""


def _first_value(*values: object) -> object | None:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _parse_horizon(value: object) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    match = re.fullmatch(
        r"(\d+)(?:\s+trading\s+days?)?",
        _text(value),
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    parsed = int(match.group(1))
    return parsed if parsed > 0 else None


def _uuid_or_none(value: object) -> str | None:
    text = _text(value)
    if not text:
        return None
    try:
        return str(UUID(text))
    except (ValueError, AttributeError, TypeError):
        return None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _canonical_clock(value: object, field_name: str) -> str | None:
    if value in (None, ""):
        return None
    try:
        return canonical_aware_datetime(value, field_name)
    except (TypeError, ValueError):
        return None


class PersonalizationRecommendationSaveAdapter:
    """Bind local prediction captures to the existing recommendation save path."""

    def __init__(
        self,
        *,
        capture_service: PersonalizationDeliveryCaptureService | None = None,
        local_scope_id: str = LOCAL_RESEARCH_SCOPE_ID,
    ) -> None:
        self.capture_service = capture_service or PersonalizationDeliveryCaptureService()
        self.local_scope_id = _text(local_scope_id) or LOCAL_RESEARCH_SCOPE_ID

    def bind_result(
        self,
        result: RecommendationResultDTO,
        *,
        personalization_scope: PersonalizationDeliveryScope | None = None,
        request_id: str | None = None,
    ) -> tuple[RecommendationResultDTO, tuple[PersonalizationDeliveryCapture, ...]]:
        """Create generated captures and attach them to the existing result DTO.

        A missing or unverified receipt/clock deliberately returns the ordinary
        result without a personal capture. The ordinary recommendation save is
        therefore preserved while the personal denominator remains fail-closed.
        """

        context = deepcopy(_mapping(result.run_context))
        existing = self.captures_from_result(result)
        if existing:
            if (
                personalization_scope is not None
                and personalization_scope.envelope_hash != existing[0].scope.envelope_hash
            ):
                raise PersonalizationSaveAdapterError(
                    "personalization retry scope envelope conflict"
                )
            return result, existing

        candidates = list(result.recommendations)
        receipt_refs = [
            self._receipt_reference(
                context=context,
                candidate=_mapping(getattr(candidate, "calibration_provenance", {})),
                stock_code=_text(getattr(candidate, "stock_code", "")),
                result_id=_text(result.result_id),
            )
            for candidate in candidates
        ]
        if not any(item is not None for item in receipt_refs):
            return result, ()

        scope = personalization_scope or self._scope_from_context(context)
        if scope is None:
            context.setdefault("warnings", []).append(
                "personalization_capture_unavailable:caller_scope_missing_or_unverified"
            )
            result.run_context = context
            return result, ()
        temporal_state, temporal_warnings = inspect_personalization_temporal_context(
            context,
            actual_decision_date=scope.decision_date,
            scope=scope,
            expected_result_id=_text(result.result_id),
        )
        if temporal_state in {"invalid", "legacy_unverified"}:
            diagnostics = temporal_warnings or ("temporal_contract_unverified",)
            context.setdefault("warnings", []).extend(
                f"personalization_capture_unavailable:{warning}"
                for warning in diagnostics
            )
            result.run_context = context
            return result, ()

        resolved_request_id = self._request_id(
            context=context,
            result_id=_text(result.result_id),
            request_id=request_id,
        )
        captures: list[PersonalizationDeliveryCapture] = []
        seen_stocks: set[str] = set()
        capture_warnings: list[str] = []
        for candidate, reference in zip(candidates, receipt_refs):
            stock_code = _text(getattr(candidate, "stock_code", ""))
            if reference is None:
                continue
            if not stock_code:
                capture_warnings.append("candidate_stock_code_missing")
                continue
            if stock_code in seen_stocks:
                raise PersonalizationSaveAdapterError(
                    "personalization capture candidate stock identity is duplicated"
                )
            seen_stocks.add(stock_code)
            metadata = self._prediction_metadata(
                context=context,
                candidate=_mapping(getattr(candidate, "calibration_provenance", {})),
                reference=reference,
                stock_code=stock_code,
            )
            if metadata is None:
                capture_warnings.append(
                    f"personalization_capture_unavailable:{stock_code}:receipt_lineage_incomplete"
                )
                continue
            prediction_id = _uuid_or_none(metadata.get("prediction_id"))
            declared_prediction_id = _text(metadata.get("declared_prediction_id"))
            if declared_prediction_id and prediction_id is None:
                capture_warnings.append(
                    f"personalization_capture_unavailable:{stock_code}:prediction_id_invalid"
                )
                continue
            if prediction_id is None:
                prediction_id = str(
                    uuid5(
                        NAMESPACE_URL,
                        "|".join(
                            (
                                scope.scope_id,
                                _text(result.result_id),
                                stock_code,
                                reference["receipt_hash"],
                            )
                        ),
                    )
                )
            try:
                capture = self.capture_service.capture(
                    scope=scope,
                    request_id=resolved_request_id,
                    result_id=_text(result.result_id),
                    stock_code=stock_code,
                    projection_receipt_hash=reference["receipt_hash"],
                    generated_at=scope.decision_at,
                    prediction_id=prediction_id,
                    projection_receipt_path=reference.get("receipt_path"),
                    model_id=_text(metadata.get("model_id")),
                    dataset_id=_text(metadata.get("dataset_id")),
                    dataset_hash=_text(metadata.get("dataset_hash")),
                    cost_scenario_hash=_text(metadata.get("cost_scenario_hash")) or None,
                    horizon_days=metadata.get("horizon_days"),
                )
            except (TypeError, ValueError, PersonalizationProjectionError) as exc:
                capture_warnings.append(
                    f"personalization_capture_unavailable:{stock_code}:{type(exc).__name__}"
                )
                continue
            captures.append(capture)
            self._attach_candidate_capture(candidate, capture)

        if not captures:
            if capture_warnings:
                context.setdefault("warnings", []).extend(capture_warnings)
            result.run_context = context
            return result, ()

        context["personalization_scope"] = scope.to_dict()
        context["personalization_delivery_scope"] = scope.to_dict()
        context[PERSONALIZATION_CAPTURE_CONTEXT_KEY] = [
            capture.to_dict() for capture in captures
        ]
        context["personalization_capture_schema_version"] = (
            PERSONALIZATION_DELIVERY_CAPTURE_SCHEMA_VERSION
        )
        context["personalization_capture_status"] = "generated"
        context["personalization_request_id"] = resolved_request_id
        if capture_warnings:
            context.setdefault("warnings", []).extend(capture_warnings)
        result.run_context = context
        return result, tuple(captures)

    def build_local_scope(
        self,
        *,
        context: Mapping[str, Any],
        result_id: str,
        request_id: str | None,
        receipt_hash: str,
    ) -> PersonalizationDeliveryScope | None:
        """Build a stable local research scope from explicit execution clocks.

        The stable scope is intentionally not derived from profile, holding,
        portfolio, source id, or user-declared identity. Missing clocks never
        fall back to save time, so temporal precision is not fabricated.
        """

        declared_at = _canonical_clock(
            context.get("personalization_scope_declared_at"),
            "scope_declared_at",
        )
        decision_at = _canonical_clock(context.get("decision_at"), "decision_at")
        available_at = _canonical_clock(context.get("available_at"), "available_at")
        captured_at = _canonical_clock(context.get("captured_at"), "captured_at")
        receipt_created_at = _canonical_clock(
            context.get("calibration_projection_receipt_created_at"),
            "receipt_created_at",
        )
        if not declared_at or not decision_at or not available_at or not captured_at or not receipt_created_at:
            return None
        resolved_request_id = self._request_id(
            context=context,
            result_id=result_id,
            request_id=request_id,
        )
        delivery_id = "delivery_" + uuid5(
            NAMESPACE_URL,
            "|".join(
                (
                    self.local_scope_id,
                    result_id,
                    resolved_request_id,
                    receipt_hash,
                )
            ),
        ).hex
        try:
            return PersonalizationDeliveryScope.create(
                scope_id=self.local_scope_id,
                scope_type=LOCAL_RESEARCH_SCOPE_TYPE,
                delivery_id=delivery_id,
                declared_at=declared_at,
                decision_at=decision_at,
                available_at=available_at,
                captured_at=captured_at,
                receipt_created_at=receipt_created_at,
                source="recommendation_save_adapter",
            )
        except (TypeError, ValueError):
            return None

    def load_existing_for_retry(
        self,
        recommendation_repository: Any,
        *,
        result_id: str,
    ) -> RecommendationResultDTO | None:
        """Read an existing result when the caller is retrying a save.

        ``None`` is reserved for a repository that has no row yet. A missing
        ``load_result`` implementation is an integration error, because a
        personal capture cannot be reported without exact readback.
        """

        loader = getattr(recommendation_repository, "load_result", None)
        if not callable(loader):
            raise PersonalizationSaveAdapterError(
                "personalization capture requires existing repository load_result readback"
            )
        loaded = loader(_text(result_id))
        if loaded is None:
            return None
        if _text(_mapping(loaded).get("result_id")) != _text(result_id):
            raise PersonalizationSaveAdapterError(
                "personalization retry readback result identity mismatch"
            )
        return loaded

    def save_and_readback(
        self,
        *,
        recommendation_repository: Any,
        result: RecommendationResultDTO,
        captures: tuple[PersonalizationDeliveryCapture, ...],
    ) -> RecommendationResultDTO:
        """Save through the existing repository and verify exact persisted rows."""

        create_only_saver = getattr(
            recommendation_repository, "save_result_create_only", None
        )
        save_method = (
            create_only_saver
            if callable(create_only_saver)
            else getattr(recommendation_repository, "save_result", None)
        )
        if not callable(save_method):
            raise PersonalizationSaveAdapterError(
                "personalization capture requires the existing recommendation save boundary"
            )
        saved_id = _text(save_method(result))
        if saved_id != _text(result.result_id):
            raise PersonalizationSaveAdapterError(
                "recommendation save returned a different result identity"
            )
        saved = self._load_result(recommendation_repository, saved_id)
        for capture in captures:
            self.capture_service.verify_saved_capture(saved, capture)
        return saved

    def merge_existing_retry(
        self,
        *,
        candidate_result: RecommendationResultDTO,
        existing_result: RecommendationResultDTO,
        candidate_captures: tuple[PersonalizationDeliveryCapture, ...],
    ) -> tuple[RecommendationResultDTO, tuple[PersonalizationDeliveryCapture, ...]]:
        """Keep an existing lifecycle state when the caller retries the same save."""

        existing_captures = self.captures_from_result(existing_result)
        if not existing_captures:
            raise PersonalizationSaveAdapterError(
                "personalization result identity collides with a result without capture"
            )
        by_stock = {capture.stock_code: capture for capture in existing_captures}
        if set(by_stock) != {capture.stock_code for capture in candidate_captures}:
            raise PersonalizationSaveAdapterError(
                "personalization retry candidate set conflicts with saved capture set"
            )
        for candidate_capture in candidate_captures:
            existing_capture = by_stock[candidate_capture.stock_code]
            if not self._same_capture_identity(existing_capture, candidate_capture):
                raise PersonalizationSaveAdapterError(
                    "personalization retry compare-and-set identity conflict"
                )
        return existing_result, existing_captures

    def acknowledge_delivery(
        self,
        *,
        recommendation_repository: Any,
        journal_service: Any,
        result_id: str,
        scope_id: str,
        delivery_id: str,
        persisted_at: str,
        delivered_at: str,
        recorded_at: str | None = None,
        expected_capture_hashes: Mapping[str, str] | None = None,
    ) -> RecommendationDeliveryAckOutcome:
        """Append a CAS-style ACK to the existing Journal stream.

        The saved recommendation JSON remains immutable after the initial
        generated-capture write. The Journal event carries only the technical
        lifecycle transition and is joined back by the read-side projection.
        """

        result_id_text = _text(result_id)
        scope_id_text = _text(scope_id)
        delivery_id_text = _text(delivery_id)
        if not result_id_text or not scope_id_text or not delivery_id_text:
            raise PersonalizationSaveAdapterError(
                "delivery ACK requires result_id, scope_id, and delivery_id"
            )
        ack_writer = getattr(journal_service, "record_personalization_delivery_acks", None)
        ack_reader = getattr(journal_service, "list_personalization_delivery_acks", None)
        if not callable(ack_writer) or not callable(ack_reader):
            raise PersonalizationSaveAdapterError(
                "delivery ACK requires the existing append-only Journal writer/readback"
            )
        canonical_persisted_at = canonical_aware_datetime(persisted_at, "persisted_at")
        canonical_delivered_at = canonical_aware_datetime(delivered_at, "delivered_at")
        canonical_recorded_at = canonical_aware_datetime(
            recorded_at or _utc_now_iso(),
            "recorded_at",
        )
        if canonical_delivered_at < canonical_persisted_at:
            raise PersonalizationSaveAdapterError(
                "delivery ACK delivered_at must not precede persisted_at"
            )
        if canonical_recorded_at < canonical_delivered_at:
            raise PersonalizationSaveAdapterError(
                "delivery ACK recorded_at must not precede delivered_at"
            )
        current = self._load_result(recommendation_repository, result_id_text)
        captures = self.captures_from_result(current)
        if not captures:
            raise PersonalizationSaveAdapterError("delivery ACK capture set is missing")
        if any(capture.result_id != result_id_text for capture in captures):
            raise PersonalizationSaveAdapterError("delivery ACK result identity mismatch")
        if any(capture.scope.scope_id != scope_id_text for capture in captures):
            raise PersonalizationSaveAdapterError("delivery ACK scope identity mismatch")
        if any(capture.delivery_id != delivery_id_text for capture in captures):
            raise PersonalizationSaveAdapterError("delivery ACK delivery identity mismatch")
        self._verify_expected_hashes(captures, expected_capture_hashes)

        existing_ack_rows: dict[str, tuple[Any, ...]] = {
            capture.stock_code: tuple(
                ack_reader(result_id_text, capture.stock_code, delivery_id_text)
            )
            for capture in captures
        }
        if all(existing_ack_rows[capture.stock_code] for capture in captures):
            for capture in captures:
                self._verify_ack_readback(
                    existing_ack_rows[capture.stock_code],
                    capture=capture,
                    result_id=result_id_text,
                    scope_id=scope_id_text,
                    delivery_id=delivery_id_text,
                    persisted_at=canonical_persisted_at,
                    delivered_at=canonical_delivered_at,
                )
            return RecommendationDeliveryAckOutcome(
                result_id=result_id_text,
                scope_id=scope_id_text,
                delivery_id=delivery_id_text,
                delivered_at=canonical_delivered_at,
                capture_hashes=tuple(capture.capture_hash for capture in captures),
                status="already_delivered",
            )

        ack_rows: list[dict[str, Any]] = []
        for capture in captures:
            if capture.status == "delivered":
                raise PersonalizationSaveAdapterError(
                    "delivery ACK compare-and-set conflict: result capture is already delivered"
                )
            if capture.status not in {"generated", "persisted", "not_delivered"}:
                raise PersonalizationSaveAdapterError(
                    "delivery ACK capture lifecycle state is invalid"
                )
            if capture.status == "generated":
                persisted_capture = self.capture_service.mark_persisted(
                    capture,
                    persisted_at=canonical_persisted_at,
                )
            else:
                if capture.persisted_at is None:
                    raise PersonalizationSaveAdapterError(
                        "delivery ACK requires persisted_at on every capture"
                    )
                if capture.status == "persisted" and capture.persisted_at != canonical_persisted_at:
                    raise PersonalizationSaveAdapterError(
                        "delivery ACK compare-and-set persisted timestamp conflict"
                    )
                persisted_capture = capture
            delivered_capture = self.capture_service.mark_delivered(
                persisted_capture,
                delivered_at=canonical_delivered_at,
            )
            ack_request_id = (
                f"personalization-delivery-ack:{delivery_id_text}:{capture.stock_code}"
            )
            ack_rows.append(
                {
                    "result_id": result_id_text,
                    "stock_code": capture.stock_code,
                    "personalization_scope_id": scope_id_text,
                    "scope_envelope_hash": capture.scope.envelope_hash,
                    "delivery_id": delivery_id_text,
                    "capture_hash": capture.capture_hash,
                    "request_id": capture.request_id,
                    "persisted_at": delivered_capture.persisted_at,
                    "delivered_at": delivered_capture.delivered_at,
                    "recorded_at": canonical_recorded_at,
                    "revision_id": ack_request_id,
                }
            )
        try:
            ack_writer(ack_rows)
        except Exception as exc:  # noqa: BLE001 - append-only writer owns its error contract
            raise PersonalizationSaveAdapterError(
                f"delivery ACK append failed:{type(exc).__name__}"
            ) from exc

        for capture in captures:
            readback_rows = tuple(
                ack_reader(result_id_text, capture.stock_code, delivery_id_text)
            )
            self._verify_ack_readback(
                readback_rows,
                capture=capture,
                result_id=result_id_text,
                scope_id=scope_id_text,
                delivery_id=delivery_id_text,
                persisted_at=canonical_persisted_at,
                delivered_at=canonical_delivered_at,
            )
        return RecommendationDeliveryAckOutcome(
            result_id=result_id_text,
            scope_id=scope_id_text,
            delivery_id=delivery_id_text,
            delivered_at=canonical_delivered_at,
            capture_hashes=tuple(capture.capture_hash for capture in captures),
        )

    @staticmethod
    def _ack_payload(value: Any) -> dict[str, Any]:
        raw = _mapping(value)
        payload = _mapping(raw.get("payload"))
        merged = dict(payload)
        for key in (
            "event_kind",
            "result_id",
            "stock_code",
            "personalization_scope_id",
            "scope_envelope_hash",
            "delivery_id",
            "capture_hash",
            "request_id",
            "persisted_at",
            "delivered_at",
            "status",
        ):
            if raw.get(key) not in (None, ""):
                merged[key] = raw.get(key)
        return merged

    @classmethod
    def _verify_ack_readback(
        cls,
        rows: tuple[Any, ...],
        *,
        capture: PersonalizationDeliveryCapture,
        result_id: str,
        scope_id: str,
        delivery_id: str,
        persisted_at: str,
        delivered_at: str,
    ) -> None:
        if not rows:
            raise PersonalizationSaveAdapterError(
                "delivery ACK exact append-only readback is missing"
            )
        matching: list[dict[str, Any]] = []
        for row in rows:
            payload = cls._ack_payload(row)
            if (
                _text(payload.get("result_id")) == result_id
                and _text(payload.get("stock_code")) == capture.stock_code
                and _text(payload.get("delivery_id")) == delivery_id
            ):
                matching.append(payload)
        if len(matching) != 1:
            raise PersonalizationSaveAdapterError(
                "delivery ACK exact readback is duplicated or missing"
            )
        payload = matching[0]
        if _text(payload.get("event_kind")) != PERSONALIZATION_DELIVERY_ACK_SCHEMA_VERSION:
            raise PersonalizationSaveAdapterError("delivery ACK schema readback mismatch")
        if _text(payload.get("personalization_scope_id")) != scope_id:
            raise PersonalizationSaveAdapterError("delivery ACK scope readback mismatch")
        if _text(payload.get("scope_envelope_hash")) != capture.scope.envelope_hash:
            raise PersonalizationSaveAdapterError("delivery ACK scope envelope readback mismatch")
        if _text(payload.get("capture_hash")) != capture.capture_hash:
            raise PersonalizationSaveAdapterError("delivery ACK capture hash readback mismatch")
        if _text(payload.get("request_id")) != capture.request_id:
            raise PersonalizationSaveAdapterError("delivery ACK request readback mismatch")
        if _text(payload.get("persisted_at")) != persisted_at:
            raise PersonalizationSaveAdapterError(
                "delivery ACK compare-and-set persisted timestamp conflict"
            )
        if _text(payload.get("delivered_at")) != delivered_at:
            raise PersonalizationSaveAdapterError(
                "delivery ACK compare-and-set delivered timestamp conflict"
            )

    def captures_from_result(
        self,
        result: RecommendationResultDTO | Mapping[str, Any],
    ) -> tuple[PersonalizationDeliveryCapture, ...]:
        raw_result = _mapping(result)
        if isinstance(result, RecommendationResultDTO):
            context = _mapping(result.run_context)
        else:
            context = _mapping(raw_result.get("run_context"))
        raw_values = context.get(PERSONALIZATION_CAPTURE_CONTEXT_KEY)
        if raw_values is None:
            return ()
        if isinstance(raw_values, Mapping) or isinstance(raw_values, (str, bytes)):
            raw_items = (raw_values,)
        else:
            try:
                raw_items = tuple(raw_values)
            except TypeError as exc:
                raise PersonalizationSaveAdapterError(
                    "saved personalization captures must be a sequence"
                ) from exc
        captures: list[PersonalizationDeliveryCapture] = []
        for raw in raw_items:
            try:
                captures.append(PersonalizationDeliveryCapture.from_mapping(_mapping(raw)))
            except (TypeError, ValueError) as exc:
                raise PersonalizationSaveAdapterError(
                    "saved personalization capture is invalid"
                ) from exc
        if len({(capture.result_id, capture.stock_code) for capture in captures}) != len(captures):
            raise PersonalizationSaveAdapterError(
                "saved personalization capture set contains duplicate candidate identity"
            )
        return tuple(captures)

    def _receipt_reference(
        self,
        *,
        context: Mapping[str, Any],
        candidate: Mapping[str, Any],
        stock_code: str,
        result_id: str,
    ) -> dict[str, Any] | None:
        references = [
            context.get("calibration_projection_receipt"),
            context.get("projection_receipt"),
            candidate.get("projection_receipt"),
        ]
        hashes = [
            _text(context.get("calibration_projection_receipt_hash")),
            _text(candidate.get("projection_receipt_hash")),
        ]
        receipt_path = _first_text(
            candidate.get("projection_receipt_path"),
            context.get("calibration_projection_receipt_path"),
        )
        receipt_body: dict[str, Any] | None = None
        for reference in references:
            mapping = _mapping(reference)
            if not mapping:
                continue
            if mapping.get("projections") is not None:
                receipt_body = mapping
            reference_hash = _text(mapping.get("receipt_hash"))
            if reference_hash:
                hashes.append(reference_hash)
            receipt_path = _first_text(receipt_path, mapping.get("path"))
            declared_result = _text(mapping.get("result_id"))
            if declared_result and declared_result != result_id:
                raise PersonalizationSaveAdapterError(
                    "projection receipt result identity conflicts with saved result"
                )
        distinct_hashes = tuple(dict.fromkeys(value for value in hashes if value))
        if len(distinct_hashes) > 1:
            raise PersonalizationSaveAdapterError(
                "projection receipt hash conflict in save request"
            )
        receipt_hash = distinct_hashes[0] if distinct_hashes else ""
        if receipt_path:
            try:
                from ml_module.recommendation_inference_provenance import (
                    read_inference_projection_receipt,
                )

                receipt = read_inference_projection_receipt(
                    receipt_path,
                    expected_receipt_hash=receipt_hash or None,
                    expected_result_id=result_id,
                    expected_stock_code=stock_code,
                )
                receipt_body = dict(receipt.payload)
                receipt_hash = receipt.receipt_hash
            except (OSError, TypeError, ValueError):
                return None
        if not receipt_hash.startswith("sha256:"):
            return None
        if receipt_body is not None:
            declared_result = _text(receipt_body.get("result_id"))
            if declared_result and declared_result != result_id:
                raise PersonalizationSaveAdapterError(
                    "projection receipt result identity conflicts with saved result"
                )
        return {
            "receipt_hash": receipt_hash,
            "receipt_path": receipt_path,
            "receipt_body": receipt_body,
        }

    def _prediction_metadata(
        self,
        *,
        context: Mapping[str, Any],
        candidate: Mapping[str, Any],
        reference: Mapping[str, Any],
        stock_code: str,
    ) -> dict[str, Any] | None:
        rows = _mapping(context.get("calibration_projection_rows"))
        context_row = _mapping(rows.get(stock_code))
        receipt_body = _mapping(reference.get("receipt_body"))
        receipt_rows = receipt_body.get("projections")
        receipt_row: dict[str, Any] = {}
        if isinstance(receipt_rows, list):
            matches = [
                _mapping(row)
                for row in receipt_rows
                if _text(_mapping(row).get("stock_code") or _mapping(row).get("證券代號"))
                == stock_code
            ]
            if len(matches) == 1:
                receipt_row = matches[0]
            elif len(matches) > 1:
                return None
        training = _mapping(receipt_body.get("training_provenance"))
        inference = _mapping(receipt_body.get("inference_provenance"))
        candidate_identity = _mapping(receipt_body.get("candidate_identity"))
        training_candidate = _mapping(candidate.get("training_provenance"))
        inference_candidate = _mapping(candidate.get("inference_provenance"))
        prediction_candidates = (
            receipt_row.get("prediction_id"),
            context_row.get("prediction_id"),
            candidate.get("prediction_id"),
        )
        declared_prediction_id = _first_text(*prediction_candidates)
        model_id = _first_text(
            receipt_row.get("model_id"),
            receipt_row.get("model_version"),
            context_row.get("model_id"),
            context_row.get("model_version"),
            receipt_body.get("model_id"),
            candidate_identity.get("model_id"),
            candidate_identity.get("candidate_id"),
            training.get("model_id"),
            inference.get("model_id"),
            candidate.get("model_id"),
            candidate.get("model_version"),
            training_candidate.get("model_id"),
            inference_candidate.get("model_id"),
        )
        dataset_id = _first_text(
            receipt_row.get("dataset_id"),
            receipt_row.get("dataset_version"),
            context_row.get("dataset_id"),
            context_row.get("dataset_version"),
            receipt_body.get("dataset_id"),
            training.get("dataset_id"),
            inference.get("dataset_id"),
            candidate.get("dataset_id"),
            candidate.get("dataset_version"),
            training_candidate.get("dataset_id"),
            inference_candidate.get("dataset_id"),
        )
        dataset_hash = _first_text(
            receipt_row.get("dataset_hash"),
            context_row.get("dataset_hash"),
            receipt_body.get("dataset_hash"),
            training.get("dataset_hash"),
            inference.get("dataset_hash"),
            training_candidate.get("dataset_hash"),
            inference_candidate.get("dataset_hash"),
        )
        cost_scenario_hash = _first_text(
            receipt_row.get("cost_scenario_hash"),
            context_row.get("cost_scenario_hash"),
            receipt_body.get("cost_scenario_hash"),
            inference.get("cost_scenario_hash"),
            training.get("cost_scenario_hash"),
            inference_candidate.get("cost_scenario_hash"),
            training_candidate.get("cost_scenario_hash"),
        )
        horizon_days = _parse_horizon(
            _first_value(
                receipt_row.get("horizon_days"),
                receipt_row.get("horizon"),
                context_row.get("horizon_days"),
                context_row.get("horizon"),
                candidate.get("horizon_days"),
                candidate.get("horizon"),
            )
        )
        if not model_id or not dataset_id or not cost_scenario_hash or horizon_days is None:
            return None
        return {
            "declared_prediction_id": declared_prediction_id,
            "prediction_id": declared_prediction_id,
            "model_id": model_id,
            "dataset_id": dataset_id,
            "dataset_hash": dataset_hash,
            "cost_scenario_hash": cost_scenario_hash,
            "horizon_days": horizon_days,
        }

    def _request_id(
        self,
        *,
        context: Mapping[str, Any],
        result_id: str,
        request_id: str | None,
    ) -> str:
        explicit = _first_text(request_id, context.get("personalization_request_id"))
        return explicit or f"recommendation-save:{result_id}"

    @staticmethod
    def _scope_from_context(
        context: Mapping[str, Any],
    ) -> PersonalizationDeliveryScope | None:
        raw_scope = context.get("personalization_scope")
        if raw_scope is None:
            raw_scope = context.get("personalization_delivery_scope")
        if not isinstance(raw_scope, Mapping):
            return None
        try:
            return PersonalizationDeliveryScope.from_mapping(raw_scope)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _attach_candidate_capture(
        candidate: Any,
        capture: PersonalizationDeliveryCapture,
    ) -> None:
        provenance = _mapping(getattr(candidate, "calibration_provenance", {}))
        provenance.update(
            {
                "personalization_scope_id": capture.scope.scope_id,
                "personalization_scope_hash": capture.scope.envelope_hash,
                "delivery_id": capture.delivery_id,
                "request_id": capture.request_id,
                "prediction_id": capture.prediction_id,
                "projection_receipt_hash": capture.projection_receipt_hash,
                "projection_receipt_path": capture.projection_receipt_path,
                "personalization_delivery_capture": capture.to_dict(),
            }
        )
        candidate.calibration_provenance = provenance

    @staticmethod
    def _same_capture_identity(
        left: PersonalizationDeliveryCapture,
        right: PersonalizationDeliveryCapture,
    ) -> bool:
        if not PersonalizationDeliveryCaptureService.retry_is_same_identity(left, right):
            return False
        return all(
            getattr(left, field_name) == getattr(right, field_name)
            for field_name in (
                "projection_receipt_path",
                "source",
                "model_id",
                "dataset_id",
                "dataset_hash",
                "cost_scenario_hash",
                "horizon_days",
            )
        )

    @staticmethod
    def _verify_expected_hashes(
        captures: tuple[PersonalizationDeliveryCapture, ...],
        expected_capture_hashes: Mapping[str, str] | None,
    ) -> None:
        if expected_capture_hashes is None:
            return
        expected = {str(key): _text(value) for key, value in expected_capture_hashes.items()}
        actual_keys = {capture.stock_code for capture in captures}
        if set(expected) != actual_keys or any(
            expected[capture.stock_code] != capture.capture_hash for capture in captures
        ):
            raise PersonalizationSaveAdapterError(
                "delivery ACK compare-and-set capture hash conflict"
            )

    @staticmethod
    def _load_result(repository: Any, result_id: str) -> RecommendationResultDTO:
        loader = getattr(repository, "load_result", None)
        if not callable(loader):
            raise PersonalizationSaveAdapterError(
                "personalization capture requires existing repository load_result readback"
            )
        loaded = loader(result_id)
        if loaded is None:
            raise PersonalizationSaveAdapterError(
                "personalization capture exact result readback is missing"
            )
        if _text(_mapping(loaded).get("result_id")) != result_id:
            raise PersonalizationSaveAdapterError(
                "personalization capture readback result identity mismatch"
            )
        return loaded


__all__ = [
    "LOCAL_RESEARCH_SCOPE_ID",
    "LOCAL_RESEARCH_SCOPE_TYPE",
    "PersonalizationRecommendationSaveAdapter",
    "PersonalizationSaveAdapterError",
    "RecommendationDeliveryAckOutcome",
]
