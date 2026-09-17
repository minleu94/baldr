"""Typed contracts for research decision continuity.

The contract intentionally separates a recommendation ``result_id`` from a
source snapshot id/hash.  Legacy callers may still carry an untyped
``source_id``; that value is never promoted to a result identity here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Mapping


DECISION_IDENTITY_SCHEMA_VERSION = "decision-identity.v1"
DECISION_CONTINUITY_SCHEMA_VERSION = "decision-continuity.v1"
DECISION_CONTINUITY_RECORD_TYPE = "decision_continuity_revision"

IDENTITY_STATUS_LINKED = "linked"
IDENTITY_STATUS_UNKNOWN = "unknown"
IDENTITY_STATUS_CONFLICT = "conflict"
IDENTITY_STATUS_UNLINKED = "unlinked"
DECISION_IDENTITY_STATUSES = frozenset(
    {
        IDENTITY_STATUS_LINKED,
        IDENTITY_STATUS_UNKNOWN,
        IDENTITY_STATUS_CONFLICT,
        IDENTITY_STATUS_UNLINKED,
    }
)

ACTION_ADDED = "added"
ACTION_UPDATED = "updated"
ACTION_ACCEPTED = "accepted"
ACTION_SKIPPED = "skipped"
ACTION_NOTE = "note"
ACTION_REVIEW_SCHEDULED = "review_scheduled"
ACTION_REMOVED = "removed"
ACTION_CLEARED = "cleared"
# Technical append-only event; this is deliberately not part of the research
# action command set and must never be presented as a human decision.
ACTION_DELIVERY_ACK = "delivery_ack"
DECISION_CONTINUITY_ACTIONS = frozenset(
    {
        ACTION_ADDED,
        ACTION_UPDATED,
        ACTION_ACCEPTED,
        ACTION_SKIPPED,
        ACTION_NOTE,
        ACTION_REVIEW_SCHEDULED,
        ACTION_REMOVED,
        ACTION_CLEARED,
    }
)
DECISION_CONTINUITY_EVENT_ACTIONS = frozenset({ACTION_DELIVERY_ACK})
DECISION_CONTINUITY_TOMBSTONE_ACTIONS = frozenset(
    {ACTION_REMOVED, ACTION_CLEARED}
)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _json_value(value: Any) -> Any:
    """Copy nested payloads without retaining mutable caller references."""

    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool, Decimal)):
        return value
    raise TypeError(f"unsupported decision continuity payload value: {type(value).__name__}")


def _freeze_json(value: Any) -> Any:
    """Recursively freeze JSON-shaped values held by a frozen DTO."""

    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze_json(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    if value is None or isinstance(value, (str, int, float, bool, Decimal)):
        return value
    raise TypeError(f"unsupported decision continuity payload value: {type(value).__name__}")


@dataclass(frozen=True)
class DecisionIdentity:
    """Explicit recommendation/candidate identity carried by a user action.

    ``result_id`` and ``stock_code`` are the candidate identity. Snapshot
    fields are independent optional provenance; they are never filled from
    ``result_id``.  Empty result identity is valid for legacy input and is
    classified as ``unknown`` rather than guessed.
    """

    result_id: str = ""
    stock_code: str = ""
    source_snapshot_id: str = ""
    source_snapshot_hash: str = ""
    decision_date: str = ""
    identity_status: str = ""

    def __post_init__(self) -> None:
        values = {
            "result_id": _text(self.result_id),
            "stock_code": _text(self.stock_code),
            "source_snapshot_id": _text(self.source_snapshot_id),
            "source_snapshot_hash": _text(self.source_snapshot_hash),
            "decision_date": _text(self.decision_date),
            "identity_status": _text(self.identity_status),
        }
        if not values["identity_status"]:
            values["identity_status"] = (
                IDENTITY_STATUS_LINKED
                if values["result_id"] and values["stock_code"]
                else IDENTITY_STATUS_UNKNOWN
            )
        if values["identity_status"] not in DECISION_IDENTITY_STATUSES:
            raise ValueError(
                f"unsupported decision identity status: {values['identity_status']}"
            )
        if values["identity_status"] == IDENTITY_STATUS_LINKED and not (
            values["result_id"] and values["stock_code"]
        ):
            raise ValueError("linked decision identity requires result_id and stock_code")
        result_id = values["result_id"]
        if result_id and values["source_snapshot_id"] == result_id:
            raise ValueError("source_snapshot_id must not reuse result_id")
        if result_id and values["source_snapshot_hash"] == result_id:
            raise ValueError("source_snapshot_hash must not reuse result_id")
        for name, value in values.items():
            object.__setattr__(self, name, value)

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any] | "DecisionIdentity" | None,
        *,
        default_stock_code: str = "",
    ) -> "DecisionIdentity":
        if isinstance(payload, cls):
            context_stock_code = _text(default_stock_code)
            if context_stock_code and payload.stock_code and payload.stock_code != context_stock_code:
                raise ValueError("decision identity stock_code conflicts with context")
            if context_stock_code and not payload.stock_code:
                return cls(
                    result_id=payload.result_id,
                    stock_code=default_stock_code,
                    source_snapshot_id=payload.source_snapshot_id,
                    source_snapshot_hash=payload.source_snapshot_hash,
                    decision_date=payload.decision_date,
                    identity_status=payload.identity_status,
                )
            return payload
        source: Mapping[str, Any]
        outer: Mapping[str, Any]
        nested: Mapping[str, Any] | None
        if isinstance(payload, Mapping):
            outer = payload
            raw_nested = payload.get("decision_identity")
            if raw_nested is not None and not isinstance(raw_nested, Mapping):
                raise ValueError("decision_identity must be an object")
            nested = raw_nested if isinstance(raw_nested, Mapping) else None
            source = nested or outer
        else:
            outer = {}
            nested = None
            source = {}

        def merged_text(name: str, *aliases: str, default: str = "") -> str:
            nested_value = _text(source.get(name))
            if not nested_value:
                for alias in aliases:
                    nested_value = _text(source.get(alias))
                    if nested_value:
                        break
            outer_value = _text(outer.get(name))
            if not outer_value:
                for alias in aliases:
                    outer_value = _text(outer.get(alias))
                    if outer_value:
                        break
            if nested_value and outer_value and nested_value != outer_value:
                raise ValueError(f"conflicting decision identity field: {name}")
            return nested_value or outer_value or _text(default)

        explicit_stock_code = merged_text("stock_code", "證券代號")
        context_stock_code = _text(default_stock_code)
        if (
            explicit_stock_code
            and context_stock_code
            and explicit_stock_code != context_stock_code
        ):
            raise ValueError("decision identity stock_code conflicts with context")
        stock_code = explicit_stock_code or context_stock_code
        return cls(
            # Deliberately do not fall back to source_id: it is not typed as a
            # recommendation result and may refer to a provider/strategy.
            result_id=merged_text("result_id"),
            stock_code=stock_code,
            source_snapshot_id=merged_text("source_snapshot_id"),
            source_snapshot_hash=merged_text("source_snapshot_hash"),
            decision_date=merged_text("decision_date"),
            identity_status=merged_text("identity_status"),
        )

    @property
    def candidate_key(self) -> tuple[str, str] | None:
        if not self.result_id or not self.stock_code:
            return None
        return self.result_id, self.stock_code

    @property
    def is_linked(self) -> bool:
        return self.identity_status == IDENTITY_STATUS_LINKED and self.candidate_key is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": DECISION_IDENTITY_SCHEMA_VERSION,
            "result_id": self.result_id,
            "stock_code": self.stock_code,
            "source_snapshot_id": self.source_snapshot_id,
            "source_snapshot_hash": self.source_snapshot_hash,
            "decision_date": self.decision_date,
            "identity_status": self.identity_status,
        }


@dataclass(frozen=True)
class DecisionContinuityRevision:
    """One immutable research action/revision record."""

    revision_id: str
    continuity_event_id: str
    action: str
    entity_type: str
    entity_id: str
    decision_identity: DecisionIdentity = field(default_factory=DecisionIdentity)
    revision_of: str = ""
    note: str = ""
    next_review_at: str = ""
    actor: str = ""
    created_at: str = ""
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        revision_id = _text(self.revision_id)
        event_id = _text(self.continuity_event_id)
        action = _text(self.action)
        entity_type = _text(self.entity_type)
        entity_id = _text(self.entity_id)
        if not revision_id:
            raise ValueError("revision_id is required")
        if not event_id:
            raise ValueError("continuity_event_id is required")
        if not action or action not in (
            DECISION_CONTINUITY_ACTIONS | DECISION_CONTINUITY_EVENT_ACTIONS
        ):
            raise ValueError(f"unsupported decision continuity action: {action}")
        if not entity_type or not entity_id:
            raise ValueError("entity_type and entity_id are required")
        if revision_id == _text(self.revision_of):
            raise ValueError("revision_of must not equal revision_id")
        identity = DecisionIdentity.from_mapping(
            self.decision_identity,
            default_stock_code="",
        )
        object.__setattr__(self, "revision_id", revision_id)
        object.__setattr__(self, "continuity_event_id", event_id)
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "entity_type", entity_type)
        object.__setattr__(self, "entity_id", entity_id)
        object.__setattr__(self, "decision_identity", identity)
        object.__setattr__(self, "revision_of", _text(self.revision_of))
        object.__setattr__(self, "note", _text(self.note))
        object.__setattr__(self, "next_review_at", _text(self.next_review_at))
        object.__setattr__(self, "actor", _text(self.actor))
        object.__setattr__(self, "created_at", _text(self.created_at))
        object.__setattr__(self, "payload", _freeze_json(self.payload))

    @property
    def is_tombstone(self) -> bool:
        return self.action in DECISION_CONTINUITY_TOMBSTONE_ACTIONS

    @property
    def candidate_key(self) -> tuple[str, str] | None:
        return self.decision_identity.candidate_key

    def to_dict(self) -> dict[str, Any]:
        identity = self.decision_identity.to_dict()
        return {
            "record_type": DECISION_CONTINUITY_RECORD_TYPE,
            "schema_version": DECISION_CONTINUITY_SCHEMA_VERSION,
            "revision_id": self.revision_id,
            "continuity_event_id": self.continuity_event_id,
            "revision_of": self.revision_of,
            "action": self.action,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "decision_identity": identity,
            # Keep explicit top-level fields for existing read adapters.
            "result_id": identity["result_id"],
            "stock_code": identity["stock_code"],
            "source_snapshot_id": identity["source_snapshot_id"],
            "source_snapshot_hash": identity["source_snapshot_hash"],
            "decision_date": identity["decision_date"],
            "identity_status": identity["identity_status"],
            "note": self.note,
            "next_review_at": self.next_review_at,
            "actor": self.actor,
            "created_at": self.created_at,
            "tombstone": self.is_tombstone,
            "payload": _json_value(self.payload),
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "DecisionContinuityRevision":
        identity = DecisionIdentity.from_mapping(payload)
        raw_payload = payload.get("payload")
        return cls(
            revision_id=_text(payload.get("revision_id")),
            continuity_event_id=_text(payload.get("continuity_event_id"))
            or _text(payload.get("event_id")),
            action=_text(payload.get("action")),
            entity_type=_text(payload.get("entity_type")),
            entity_id=_text(payload.get("entity_id"))
            or _text(payload.get("journal_id")),
            decision_identity=identity,
            revision_of=_text(payload.get("revision_of")),
            note=_text(payload.get("note")),
            next_review_at=_text(payload.get("next_review_at")),
            actor=_text(payload.get("actor")),
            created_at=_text(payload.get("created_at")),
            payload=raw_payload if isinstance(raw_payload, Mapping) else {},
        )


__all__ = [
    "ACTION_ACCEPTED",
    "ACTION_ADDED",
    "ACTION_CLEARED",
    "ACTION_DELIVERY_ACK",
    "ACTION_NOTE",
    "ACTION_REMOVED",
    "ACTION_REVIEW_SCHEDULED",
    "ACTION_SKIPPED",
    "ACTION_UPDATED",
    "DECISION_CONTINUITY_ACTIONS",
    "DECISION_CONTINUITY_EVENT_ACTIONS",
    "DECISION_CONTINUITY_RECORD_TYPE",
    "DECISION_CONTINUITY_SCHEMA_VERSION",
    "DECISION_CONTINUITY_TOMBSTONE_ACTIONS",
    "DECISION_IDENTITY_SCHEMA_VERSION",
    "DECISION_IDENTITY_STATUSES",
    "DecisionContinuityRevision",
    "DecisionIdentity",
    "IDENTITY_STATUS_CONFLICT",
    "IDENTITY_STATUS_LINKED",
    "IDENTITY_STATUS_UNKNOWN",
    "IDENTITY_STATUS_UNLINKED",
]
