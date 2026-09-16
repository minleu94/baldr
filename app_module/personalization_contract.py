"""V6 個人化 scope、PIT、action 與 read-side evaluation contract。

本模組只保存 immutable DTO 與 canonical validation。它不建立資料表、JSONL
或任何新的 ledger；delivery scope 由既有 Recommendation result/receipt
保存，action 由既有 DecisionContinuity/Journal 保存。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import hashlib
import json
from typing import Any, Mapping
from uuid import uuid4


PERSONALIZATION_DELIVERY_SCOPE_SCHEMA_VERSION = "personalization-delivery-scope.v1"
PERSONALIZATION_ACTION_SCHEMA_VERSION = "personalization-action.v1"
PERSONALIZATION_EVALUATION_ROW_SCHEMA_VERSION = "personalization-evaluation-row.v1"
PERSONALIZATION_DECISION_EVIDENCE_SCHEMA_VERSION = "personalization-decision-evidence.v1"

PERSONALIZATION_SCOPE_TYPES = frozenset({"user", "profile", "local", "unbound"})
PERSONALIZATION_SCOPE_STATUSES = frozenset({"bound", "unbound"})
PERSONALIZATION_ACTIONS = frozenset(
    {
        "accepted",
        "skipped",
        "watch",
        "held",
        "buy",
        "sell",
        "review_scheduled",
        "note",
        "not_recorded",
    }
)
PERSONALIZATION_ACTION_STATES = frozenset(
    {"recorded", "not_recorded", "superseded", "voided", "conflict"}
)
PERSONALIZATION_OUTCOME_TIERS = frozenset(
    {
        "natural_forward",
        "paper_research",
        "user_declared_context",
        "historical_replay",
        "synthetic_fixture",
    }
)


def _text(value: object) -> str:
    return str(value or "").strip()


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _canonical(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise TypeError(f"unsupported personalization contract value: {type(value).__name__}")


def canonical_payload_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        _canonical(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def parse_aware_datetime(value: object, field_name: str) -> datetime:
    text = _text(value).replace("Z", "+00:00")
    if not text:
        raise ValueError(f"{field_name} is required")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be ISO datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include timezone")
    return parsed.astimezone(timezone.utc)


def canonical_aware_datetime(value: object, field_name: str) -> str:
    return parse_aware_datetime(value, field_name).isoformat(timespec="microseconds")


def _iso_date(value: object, field_name: str) -> str:
    text = _text(value)[:10]
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field_name} must be ISO date") from exc


def _optional_iso_date(value: object, field_name: str) -> str | None:
    text = _text(value)
    return None if not text else _iso_date(text, field_name)


def _probability(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10_000:
        raise ValueError(f"{field_name} must be integer bp within 0..10000 or None")
    return value


@dataclass(frozen=True)
class PersonalizationDeliveryScope:
    """在 prediction delivery 當下凍結的 scope／時間 envelope。"""

    scope_id: str
    scope_type: str
    delivery_id: str
    declared_at: str
    decision_at: str
    available_at: str | None
    receipt_created_at: str
    scope_status: str = "bound"
    temporal_status: str = "verified"
    source: str = "recommendation_service"
    schema_version: str = PERSONALIZATION_DELIVERY_SCOPE_SCHEMA_VERSION
    decision_date: str = field(init=False)
    available_date: str | None = field(init=False)
    envelope_hash: str = field(init=False)

    def __post_init__(self) -> None:
        scope_id = _text(self.scope_id)
        scope_type = _text(self.scope_type) or ("unbound" if not scope_id else "local")
        delivery_id = _text(self.delivery_id)
        if not delivery_id:
            raise ValueError("delivery_id is required")
        if scope_type not in PERSONALIZATION_SCOPE_TYPES:
            raise ValueError(f"unsupported personalization scope_type: {scope_type}")
        status = _text(self.scope_status) or ("bound" if scope_id else "unbound")
        if status not in PERSONALIZATION_SCOPE_STATUSES:
            raise ValueError(f"unsupported personalization scope_status: {status}")
        if status == "bound" and not scope_id:
            raise ValueError("bound personalization scope requires scope_id")
        if status == "unbound" and scope_type != "unbound":
            raise ValueError("unbound personalization scope must use scope_type=unbound")
        if self.schema_version != PERSONALIZATION_DELIVERY_SCOPE_SCHEMA_VERSION:
            raise ValueError("unsupported personalization delivery scope schema")
        declared = parse_aware_datetime(self.declared_at, "declared_at")
        decision = parse_aware_datetime(self.decision_at, "decision_at")
        receipt = parse_aware_datetime(self.receipt_created_at, "receipt_created_at")
        available = (
            parse_aware_datetime(self.available_at, "available_at")
            if self.available_at is not None
            else None
        )
        if declared > decision:
            raise ValueError("scope declared_at must not follow decision_at")
        if receipt < decision:
            raise ValueError("receipt_created_at must not precede decision_at")
        temporal_status = _text(self.temporal_status) or (
            "verified" if available is not None else "temporal_precision_unproven"
        )
        if temporal_status not in {"verified", "temporal_precision_unproven"}:
            raise ValueError("unsupported personalization temporal_status")
        if available is None:
            temporal_status = "temporal_precision_unproven"
        elif available > decision:
            raise ValueError("available_at must not follow decision_at")
        decision_date = decision.date().isoformat()
        available_date = available.date().isoformat() if available is not None else None
        object.__setattr__(self, "scope_id", scope_id)
        object.__setattr__(self, "scope_type", scope_type)
        object.__setattr__(self, "delivery_id", delivery_id)
        object.__setattr__(self, "scope_status", status)
        object.__setattr__(self, "declared_at", declared.isoformat(timespec="microseconds"))
        object.__setattr__(self, "decision_at", decision.isoformat(timespec="microseconds"))
        object.__setattr__(
            self,
            "available_at",
            available.isoformat(timespec="microseconds") if available is not None else None,
        )
        object.__setattr__(self, "receipt_created_at", receipt.isoformat(timespec="microseconds"))
        object.__setattr__(self, "temporal_status", temporal_status)
        object.__setattr__(self, "decision_date", decision_date)
        object.__setattr__(self, "available_date", available_date)
        object.__setattr__(
            self,
            "envelope_hash",
            canonical_payload_hash(self._hash_payload()),
        )

    @classmethod
    def create(
        cls,
        *,
        scope_id: str | None,
        scope_type: str | None,
        decision_at: str,
        available_at: str | None,
        declared_at: str | None = None,
        receipt_created_at: str | None = None,
        delivery_id: str | None = None,
        source: str = "recommendation_service",
    ) -> "PersonalizationDeliveryScope":
        now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        resolved_decision = canonical_aware_datetime(decision_at or now, "decision_at")
        resolved_receipt = canonical_aware_datetime(
            receipt_created_at or now,
            "receipt_created_at",
        )
        return cls(
            scope_id=_text(scope_id),
            scope_type=_text(scope_type) or ("unbound" if not _text(scope_id) else "local"),
            delivery_id=_text(delivery_id) or f"delivery_{uuid4().hex}",
            declared_at=canonical_aware_datetime(
                declared_at or resolved_decision,
                "declared_at",
            ),
            decision_at=resolved_decision,
            available_at=(
                canonical_aware_datetime(available_at, "available_at")
                if available_at is not None
                else None
            ),
            receipt_created_at=resolved_receipt,
            scope_status="bound" if _text(scope_id) else "unbound",
            temporal_status="verified" if available_at is not None else "temporal_precision_unproven",
            source=source,
        )

    def with_receipt_created_at(self, receipt_created_at: str) -> "PersonalizationDeliveryScope":
        """Return the same frozen envelope with the immutable receipt timestamp."""

        return PersonalizationDeliveryScope(
            scope_id=self.scope_id,
            scope_type=self.scope_type,
            delivery_id=self.delivery_id,
            declared_at=self.declared_at,
            decision_at=self.decision_at,
            available_at=self.available_at,
            receipt_created_at=receipt_created_at,
            scope_status=self.scope_status,
            temporal_status=self.temporal_status,
            source=self.source,
            schema_version=self.schema_version,
        )

    @property
    def is_personal_scope(self) -> bool:
        return self.scope_status == "bound" and self.scope_type in {"user", "profile"}

    def _hash_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "scope_id": self.scope_id,
            "scope_type": self.scope_type,
            "delivery_id": self.delivery_id,
            "declared_at": self.declared_at,
            "decision_at": self.decision_at,
            "available_at": self.available_at,
            "receipt_created_at": self.receipt_created_at,
            "scope_status": self.scope_status,
            "temporal_status": self.temporal_status,
            "source": self.source,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._hash_payload(),
            "decision_date": self.decision_date,
            "available_date": self.available_date,
            "envelope_hash": self.envelope_hash,
            "personal_scope": self.is_personal_scope,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PersonalizationDeliveryScope":
        if not isinstance(value, Mapping):
            raise ValueError("personalization delivery scope must be an object")
        scope = cls(
            scope_id=_text(value.get("scope_id")),
            scope_type=_text(value.get("scope_type")) or "unbound",
            delivery_id=_text(value.get("delivery_id")),
            declared_at=_text(value.get("declared_at")),
            decision_at=_text(value.get("decision_at")),
            available_at=(
                _text(value.get("available_at")) or None
                if value.get("available_at") is not None
                else None
            ),
            receipt_created_at=_text(value.get("receipt_created_at")),
            scope_status=_text(value.get("scope_status")) or "unbound",
            temporal_status=_text(value.get("temporal_status")) or "verified",
            source=_text(value.get("source")) or "recommendation_service",
            schema_version=_text(value.get("schema_version"))
            or PERSONALIZATION_DELIVERY_SCOPE_SCHEMA_VERSION,
        )
        if _text(value.get("envelope_hash")) != scope.envelope_hash:
            raise ValueError("personalization delivery scope envelope hash mismatch")
        return scope


@dataclass(frozen=True)
class PersonalizationEvaluationRow:
    """固定 fit/evaluation contract 的一筆 matured prediction row。"""

    prediction_id: str
    scope_id: str
    symbol: str
    decision_date: str
    label_available_date: str
    horizon_days: int
    cost_scenario_hash: str | None
    population_probability_bp: int | None
    label: int | None
    outcome_tier: str = "natural_forward"
    action_state: str = "not_recorded"
    decision_at: str | None = None
    available_at: str | None = None
    receipt_created_at: str | None = None
    decision_day_block: str | None = None
    row_id: str = ""
    personal_observation_count: int = 0
    personal_positive_count: int = 0

    def __post_init__(self) -> None:
        for name in ("prediction_id", "scope_id", "symbol", "decision_date"):
            if not _text(getattr(self, name)):
                raise ValueError(f"{name} is required")
        _iso_date(self.decision_date, "decision_date")
        _iso_date(self.label_available_date, "label_available_date")
        if isinstance(self.horizon_days, bool) or not isinstance(self.horizon_days, int) or self.horizon_days <= 0:
            raise ValueError("horizon_days must be a positive integer")
        if self.outcome_tier not in PERSONALIZATION_OUTCOME_TIERS:
            raise ValueError(f"unsupported outcome_tier: {self.outcome_tier}")
        if self.label is not None and self.label not in {0, 1}:
            raise ValueError("label must be 0, 1 or None")
        _probability(self.population_probability_bp, "population_probability_bp")
        if self.cost_scenario_hash is not None and not _text(self.cost_scenario_hash):
            raise ValueError("cost_scenario_hash must be non-empty when supplied")
        for name in ("personal_observation_count", "personal_positive_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.personal_positive_count > self.personal_observation_count:
            raise ValueError(
                "personal_positive_count must not exceed personal_observation_count"
            )
        decision = (
            parse_aware_datetime(self.decision_at, "decision_at")
            if self.decision_at is not None
            else None
        )
        available = (
            parse_aware_datetime(self.available_at, "available_at")
            if self.available_at is not None
            else None
        )
        if available is not None and decision is not None and available > decision:
            raise ValueError("available_at must not follow decision_at")
        if self.receipt_created_at is not None and decision is not None:
            if parse_aware_datetime(self.receipt_created_at, "receipt_created_at") < decision:
                raise ValueError("receipt_created_at must not precede decision_at")
        if decision is not None and decision.date().isoformat() != _iso_date(
            self.decision_date,
            "decision_date",
        ):
            raise ValueError("decision_at date must match decision_date")
        object.__setattr__(self, "decision_date", _iso_date(self.decision_date, "decision_date"))
        object.__setattr__(
            self,
            "label_available_date",
            _iso_date(self.label_available_date, "label_available_date"),
        )
        if self.decision_at is not None:
            object.__setattr__(
                self,
                "decision_at",
                canonical_aware_datetime(self.decision_at, "decision_at"),
            )
        if self.available_at is not None:
            object.__setattr__(
                self,
                "available_at",
                canonical_aware_datetime(self.available_at, "available_at"),
            )
        if self.receipt_created_at is not None:
            object.__setattr__(
                self,
                "receipt_created_at",
                canonical_aware_datetime(self.receipt_created_at, "receipt_created_at"),
            )

    @property
    def effective_row_id(self) -> str:
        return _text(self.row_id) or self.prediction_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PERSONALIZATION_EVALUATION_ROW_SCHEMA_VERSION,
            "prediction_id": self.prediction_id,
            "scope_id": self.scope_id,
            "symbol": self.symbol,
            "decision_date": self.decision_date,
            "label_available_date": self.label_available_date,
            "horizon_days": self.horizon_days,
            "cost_scenario_hash": self.cost_scenario_hash,
            "population_probability_bp": self.population_probability_bp,
            "label": self.label,
            "outcome_tier": self.outcome_tier,
            "action_state": self.action_state,
            "decision_at": self.decision_at,
            "available_at": self.available_at,
            "receipt_created_at": self.receipt_created_at,
            "decision_day_block": self.decision_day_block or self.decision_date,
            "row_id": self.effective_row_id,
            "personal_observation_count": self.personal_observation_count,
            "personal_positive_count": self.personal_positive_count,
        }


@dataclass(frozen=True)
class PersonalizationDecisionEvidence:
    """Recommendation、action、outcome 的 read-side exact join projection。"""

    scope: PersonalizationDeliveryScope
    result_id: str
    stock_code: str
    decision_date: str
    prediction_id: str
    prediction_status: str
    prediction: Mapping[str, Any]
    action: str = "not_recorded"
    action_state: str = "not_recorded"
    action_revision_id: str = ""
    historical_action_state: str = "not_recorded"
    current_action_state: str = "not_recorded"
    outcome_status: str = "not_applicable"
    outcomes: tuple[Mapping[str, Any], ...] = ()
    source_trace: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    status: str = "population_only"
    formal_order_allowed: bool = False
    auto_action_allowed: bool = False

    def __post_init__(self) -> None:
        if not _text(self.result_id) or not _text(self.stock_code):
            raise ValueError("result_id and stock_code are required")
        _iso_date(self.decision_date, "decision_date")
        if self.formal_order_allowed or self.auto_action_allowed:
            raise ValueError("personalization evidence cannot authorize actions")
        if self.action not in PERSONALIZATION_ACTIONS:
            raise ValueError(f"unsupported personalization action: {self.action}")
        if self.action_state not in PERSONALIZATION_ACTION_STATES:
            raise ValueError(f"unsupported personalization action_state: {self.action_state}")
        object.__setattr__(self, "source_trace", tuple(str(item) for item in self.source_trace))
        object.__setattr__(self, "warnings", tuple(str(item) for item in self.warnings))
        object.__setattr__(self, "outcomes", tuple(dict(item) for item in self.outcomes))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PERSONALIZATION_DECISION_EVIDENCE_SCHEMA_VERSION,
            "scope": self.scope.to_dict(),
            "result_id": self.result_id,
            "stock_code": self.stock_code,
            "decision_date": self.decision_date,
            "prediction_id": self.prediction_id,
            "prediction_status": self.prediction_status,
            "prediction": dict(self.prediction),
            "action": self.action,
            "action_state": self.action_state,
            "action_revision_id": self.action_revision_id,
            "historical_action_state": self.historical_action_state,
            "current_action_state": self.current_action_state,
            "outcome_status": self.outcome_status,
            "outcomes": [dict(item) for item in self.outcomes],
            "source_trace": list(self.source_trace),
            "warnings": list(self.warnings),
            "status": self.status,
            "formal_order_allowed": False,
            "auto_action_allowed": False,
        }


__all__ = [
    "PERSONALIZATION_ACTIONS",
    "PERSONALIZATION_ACTION_STATES",
    "PERSONALIZATION_OUTCOME_TIERS",
    "PersonalizationDecisionEvidence",
    "PersonalizationDeliveryScope",
    "PersonalizationEvaluationRow",
    "canonical_aware_datetime",
    "canonical_payload_hash",
    "parse_aware_datetime",
]
