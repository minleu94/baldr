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
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Mapping
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo


PERSONALIZATION_DELIVERY_SCOPE_SCHEMA_VERSION = "personalization-delivery-scope.v1"
PERSONALIZATION_DELIVERY_CAPTURE_SCHEMA_VERSION = "personalization-delivery-capture.v1"
PERSONALIZATION_DELIVERY_ACK_SCHEMA_VERSION = "personalization-delivery-ack.v1"
PERSONALIZATION_ACTION_SCHEMA_VERSION = "personalization-action.v1"
PERSONAL_RECOMMENDATION_CHOICE_SCHEMA_VERSION = "personal-recommendation-choice.v1"
PERSONAL_RECOMMENDATION_MODEL_EVIDENCE_SCHEMA_VERSION = (
    "personal-recommendation-model-evidence.v1"
)
PERSONAL_USE_POLICY_SNAPSHOT_EVENT_TYPE = "personal_use_policy_snapshot"
PERSONAL_USE_POLICY_SNAPSHOT_EVENT_SCHEMA_VERSION = (
    "recommendation-personal-use-policy-snapshot.v1"
)
PERSONAL_USE_POLICY_SNAPSHOT_EVENT_SCHEMA_VERSION_V2 = (
    "recommendation-personal-use-policy-snapshot.v2"
)
PERSONALIZATION_EVALUATION_ROW_SCHEMA_VERSION = "personalization-evaluation-row.v1"
PERSONALIZATION_DECISION_EVIDENCE_SCHEMA_VERSION = "personalization-decision-evidence.v1"
PERSONALIZATION_COHORT_CONTRACT_SCHEMA_VERSION = "personalization-cohort-contract.v1"
PERSONALIZATION_PREDICTION_RECEIPT_SCHEMA_VERSION = (
    "recommendation-calibration-projection-receipt.v1"
)
PERSONALIZATION_TEMPORAL_CONTRACT = "recommendation-producer-clock.v1"
PERSONALIZATION_TEMPORAL_MODES = frozenset(
    {
        "natural_producer_clock",
        "historical_research_not_as_if_available",
    }
)
_MARKET_TIMEZONE = ZoneInfo("Asia/Taipei")

PERSONALIZATION_SCOPE_TYPES = frozenset({"user", "profile", "local", "unbound"})
PERSONALIZATION_SCOPE_STATUSES = frozenset({"bound", "unbound"})
PERSONALIZATION_DELIVERY_STATUSES = frozenset(
    {"generated", "persisted", "delivered", "not_delivered"}
)
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
PERSONALIZATION_OUTCOME_STATUSES = frozenset(
    {
        "pending_maturity",
        "ready",
        "matured_missing",
        "invalid",
        "not_applicable",
        "conflict",
        "duplicate_exact",
        "duplicate_conflict",
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


def canonical_payload_hash(value: Any) -> str:
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


def read_personal_use_policy_snapshot_event(
    execution: Any,
    *,
    expected_result_id: str | None = None,
) -> dict[str, Any]:
    """Validate the invocation-owned policy event from one canonical execution.

    Historical results without this event are intentionally not backfilled from
    the current local preference.  The returned value is a detached JSON-shaped
    copy of the exact saved event details.
    """

    result_id = _text(getattr(execution, "result_id", ""))
    if not result_id or (expected_result_id and result_id != expected_result_id):
        raise ValueError("canonical execution result identity mismatch")
    events = getattr(execution, "events", ())
    matches = [
        event
        for event in events
        if _text(getattr(event, "event_type", ""))
        == PERSONAL_USE_POLICY_SNAPSHOT_EVENT_TYPE
    ]
    if len(matches) != 1:
        raise ValueError(
            "saved result has no unique personal policy snapshot; "
            "請先以個人模式重新產生並保存推薦，再記錄個人選擇。"
        )
    event = matches[0]
    details = getattr(event, "details", None)
    base_details = {
        "schema_version",
        "result_id",
        "decision_at",
        "policy_snapshot",
        "requested_mode",
        "effective_mode",
    }
    if not isinstance(details, Mapping):
        raise ValueError("saved personal policy event fields are incomplete or unknown")
    details_schema = details.get("schema_version")
    if details_schema == PERSONAL_USE_POLICY_SNAPSHOT_EVENT_SCHEMA_VERSION:
        if set(details) != base_details:
            raise ValueError("saved V1 personal policy event fields are incomplete or unknown")
    elif details_schema == PERSONAL_USE_POLICY_SNAPSHOT_EVENT_SCHEMA_VERSION_V2:
        source_marker_fields = {
            "source_time_basis",
            "research_only",
            "official_historical_pit_verified",
        }
        if set(details) not in (base_details, base_details | source_marker_fields):
            raise ValueError("saved V2 personal policy event fields are incomplete or unknown")
    else:
        raise ValueError("saved personal policy event schema is unsupported")
    if details.get("result_id") != result_id:
        raise ValueError("saved personal policy event result identity mismatch")

    context = getattr(execution, "context", None)
    context_decision_at = getattr(context, "decision_at", None)
    if type(context_decision_at) is not datetime:
        raise ValueError("canonical execution decision_at is missing")
    try:
        event_decision_at = canonical_aware_datetime(
            details.get("decision_at"), "personal policy event decision_at"
        )
        context_decision_at_text = canonical_aware_datetime(
            context_decision_at, "canonical execution decision_at"
        )
        occurred_at = canonical_aware_datetime(
            getattr(event, "occurred_at", None), "personal policy event occurred_at"
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("saved personal policy event clock is invalid") from exc
    if event_decision_at != context_decision_at_text or occurred_at != event_decision_at:
        raise ValueError("saved personal policy event clock conflicts with execution")

    policy_value = details.get("policy_snapshot")
    if not isinstance(policy_value, Mapping):
        raise ValueError("saved personal policy snapshot must be an object")
    policy = {str(key): _thaw_choice_value(value) for key, value in policy_value.items()}
    from app_module.recommendation.personal_use_policy import (
        validate_personal_use_policy_snapshot,
    )

    policy = validate_personal_use_policy_snapshot(policy)
    policy_is_v2 = policy.get("schema_version") == "recommendation-personal-use-policy.v2"
    source_time_trust = policy.get("source_time_trust") if policy_is_v2 else None
    expected_v2_markers = {
        "source_time_basis": "user_declared_source_time",
        "research_only": True,
        "official_historical_pit_verified": False,
    }
    if policy_is_v2:
        has_markers = set(details) == base_details | set(expected_v2_markers)
        if source_time_trust is None:
            if has_markers:
                raise ValueError("V2 rule-only event must not claim source-time trust")
        else:
            if not has_markers or any(
                type(details.get(key)) is not type(value)
                or details.get(key) != value
                for key, value in expected_v2_markers.items()
            ):
                raise ValueError("V2 personal source-time event markers are inconsistent")
            if (
                source_time_trust.get("basis") != details.get("source_time_basis")
                or source_time_trust.get("research_only") is not details.get("research_only")
                or source_time_trust.get("official_historical_pit_verified")
                is not details.get("official_historical_pit_verified")
            ):
                raise ValueError("V2 event markers differ from its saved source-time trust")
    elif set(details) != base_details:
        raise ValueError("V1 personal policy event has unexpected fields")
    decision_at = parse_aware_datetime(
        event_decision_at, "personal policy event decision_at"
    )
    if type(policy.get("revision")) is not int:
        raise ValueError("saved personal policy revision is invalid")
    if policy["revision"] > 0:
        confirmed_at = policy.get("confirmed_at")
        if type(confirmed_at) is not str:
            raise ValueError("saved personal policy confirmation time is missing")
        if parse_aware_datetime(confirmed_at, "personal policy confirmed_at") > decision_at:
            raise ValueError("saved personal policy was confirmed after the recommendation")
    requested_mode = details.get("requested_mode")
    effective_mode = details.get("effective_mode")
    allowed_modes = {"rule_only", "personal_calibrated_probability"}
    if (
        type(requested_mode) is not str
        or requested_mode not in allowed_modes
        or requested_mode != policy.get("mode")
        or type(effective_mode) is not str
        or effective_mode not in allowed_modes
        or (requested_mode == "rule_only" and effective_mode != "rule_only")
        or (
            effective_mode == "personal_calibrated_probability"
            and requested_mode != "personal_calibrated_probability"
        )
    ):
        raise ValueError("saved personal policy event modes are inconsistent")
    return {
        "schema_version": details_schema,
        "result_id": result_id,
        "decision_at": event_decision_at,
        "policy_snapshot": policy,
        "requested_mode": requested_mode,
        "effective_mode": effective_mode,
        **(
            {key: details[key] for key in expected_v2_markers}
            if policy_is_v2 and source_time_trust is not None
            else {}
        ),
    }


def _freeze_choice_value(value: Any, field_name: str) -> Any:
    """Freeze the bounded JSON data supported by the personal-choice DTO."""

    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if type(key) is not str or not key.strip():
                raise ValueError(f"{field_name} keys must be non-empty strings")
            frozen[key] = _freeze_choice_value(item, f"{field_name}.{key}")
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(
            _freeze_choice_value(item, f"{field_name}[{index}]")
            for index, item in enumerate(value)
        )
    if value is None or type(value) in (str, int, bool):
        return value
    raise TypeError(f"{field_name} contains unsupported JSON value {type(value).__name__}")


def _thaw_choice_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_choice_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_choice_value(item) for item in value]
    return value


def _require_choice_hash(value: object, field_name: str) -> str:
    text = _text(value)
    if re.fullmatch(r"sha256:[0-9a-f]{64}", text) is None:
        raise ValueError(f"{field_name} must be sha256:<64 lowercase hex>")
    return text


def _iso_date(value: object, field_name: str) -> str:
    text = _text(value)[:10]
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field_name} must be ISO date") from exc


def _optional_iso_date(value: object, field_name: str) -> str | None:
    text = _text(value)
    return None if not text else _iso_date(text, field_name)


def inspect_personalization_temporal_context(
    context: Mapping[str, Any],
    *,
    actual_decision_date: str | None = None,
    scope: Any | None = None,
    expected_result_id: str | None = None,
    expected_receipt_hash: str | None = None,
) -> tuple[str, tuple[str, ...]]:
    """Classify the producer clock contract used by a personal capture.

    ``legacy_unverified`` is kept for old result files that predate the
    producer-clock contract.  New contexts must carry the complete contract,
    six producer-owned clocks, a durable receipt reference, and an exact
    scope envelope.  A marker-only context is therefore never treated as
    natural or historical.  The source cutoff is compared with the actual
    scope decision date only as an ordering check.  No weekday or
    calendar-day distance is inferred here.
    """

    if not isinstance(context, Mapping):
        return "invalid", ("temporal_contract_context_invalid",)
    marker_keys = (
        "temporal_contract",
        "temporal_mode",
        "cutoff_selection",
        "cutoff_policy",
        "decision_clock_timezone",
        "market_calendar_timezone",
        "prediction_decision_anchor",
        "horizon_anchor",
    )
    if not any(context.get(key) not in (None, "") for key in marker_keys):
        return "legacy_unverified", ()

    mode = _text(context.get("temporal_mode"))
    expected_by_mode = {
        "natural_producer_clock": {
            "cutoff_selection": "producer_selected_latest_available_cutoff",
            "cutoff_policy": "source_latest_available_exact",
        },
        "historical_research_not_as_if_available": {
            "cutoff_selection": "explicit_historical_cutoff",
            "cutoff_policy": "explicit_historical_research",
        },
    }
    diagnostics: list[str] = []
    if context.get("temporal_contract") != PERSONALIZATION_TEMPORAL_CONTRACT:
        diagnostics.append("temporal_contract_invalid")
    if mode not in PERSONALIZATION_TEMPORAL_MODES:
        diagnostics.append("temporal_mode_invalid")
    else:
        for key, expected in expected_by_mode[mode].items():
            if context.get(key) != expected:
                diagnostics.append(f"{key}_invalid")
    for key, expected in (
        ("decision_clock_timezone", "UTC"),
        ("market_calendar_timezone", "Asia/Taipei"),
        ("prediction_decision_anchor", "actual_producer_decision_at"),
        ("horizon_anchor", "immutable_projection_receipt"),
    ):
        if context.get(key) != expected:
            diagnostics.append(f"{key}_invalid")

    clock_keys = (
        "run_started_at",
        "personalization_scope_declared_at",
        "available_at",
        "captured_at",
        "decision_at",
        "calibration_projection_receipt_created_at",
    )
    clocks: dict[str, datetime] = {}
    for key in clock_keys:
        value = context.get(key)
        if value in (None, ""):
            diagnostics.append(f"{key}_missing")
            continue
        try:
            clocks[key] = parse_aware_datetime(value, key)
        except ValueError:
            diagnostics.append(f"{key}_invalid")
    if all(key in clocks for key in clock_keys):
        ordered_clocks = (
            ("run_started_at", "personalization_scope_declared_at"),
            ("personalization_scope_declared_at", "available_at"),
            ("available_at", "captured_at"),
            ("captured_at", "decision_at"),
            ("decision_at", "calibration_projection_receipt_created_at"),
        )
        for earlier, later in ordered_clocks:
            if clocks[earlier] > clocks[later]:
                diagnostics.append(f"temporal_clock_order_invalid:{earlier}>{later}")

    if scope is None:
        diagnostics.append("temporal_scope_missing")
    else:
        if _text(getattr(scope, "scope_status", "")) != "bound":
            diagnostics.append("temporal_scope_unbound")
        if _text(getattr(scope, "temporal_status", "")) != "verified":
            diagnostics.append("temporal_scope_unverified")
        if not _text(getattr(scope, "scope_id", "")):
            diagnostics.append("temporal_scope_id_missing")
        scope_clock_map = {
            "personalization_scope_declared_at": "declared_at",
            "available_at": "available_at",
            "captured_at": "captured_at",
            "decision_at": "decision_at",
            "calibration_projection_receipt_created_at": "receipt_created_at",
        }
        for context_key, scope_key in scope_clock_map.items():
            context_clock = clocks.get(context_key)
            scope_value = getattr(scope, scope_key, None)
            if context_clock is None or scope_value in (None, ""):
                diagnostics.append(f"temporal_scope_{scope_key}_missing")
                continue
            try:
                if context_clock != parse_aware_datetime(scope_value, scope_key):
                    diagnostics.append(f"temporal_scope_{scope_key}_mismatch")
            except ValueError:
                diagnostics.append(f"temporal_scope_{scope_key}_invalid")
        resolved_scope_date = _text(getattr(scope, "decision_date", ""))
        if not resolved_scope_date:
            diagnostics.append("temporal_scope_decision_date_missing")
        elif actual_decision_date is not None:
            try:
                if _iso_date(resolved_scope_date, "scope.decision_date") != _iso_date(
                    actual_decision_date,
                    "actual_decision_date",
                ):
                    diagnostics.append("temporal_scope_decision_date_mismatch")
            except ValueError:
                diagnostics.append("actual_decision_date_invalid")

    # The receipt metadata is separate from a full embedded receipt in some
    # legacy fixtures.  Prefer the explicit metadata object, but still compare
    # its identity/hash with any embedded payload available in the context.
    embedded_receipt = context.get("calibration_projection_receipt")
    embedded_receipt_map = (
        embedded_receipt if isinstance(embedded_receipt, Mapping) else {}
    )
    receipt_metadata_value = context.get("calibration_projection_receipt_metadata")
    receipt_metadata = (
        receipt_metadata_value
        if isinstance(receipt_metadata_value, Mapping)
        else embedded_receipt_map
    )
    receipt_result_id = _text(receipt_metadata.get("result_id"))
    context_result_id = _text(context.get("result_id"))
    expected_id = _text(expected_result_id)
    if not receipt_result_id:
        diagnostics.append("temporal_receipt_result_id_missing")
    if context_result_id and receipt_result_id and context_result_id != receipt_result_id:
        diagnostics.append("temporal_receipt_result_id_mismatch")
    if expected_id and receipt_result_id and expected_id != receipt_result_id:
        diagnostics.append("temporal_receipt_result_id_mismatch")
    receipt_hash = _text(receipt_metadata.get("receipt_hash"))
    embedded_hash = _text(embedded_receipt_map.get("receipt_hash"))
    if not receipt_hash:
        diagnostics.append("temporal_receipt_hash_missing")
    elif not receipt_hash.startswith("sha256:"):
        diagnostics.append("temporal_receipt_hash_invalid")
    if embedded_hash and receipt_hash and embedded_hash != receipt_hash:
        diagnostics.append("temporal_receipt_hash_conflict")
    expected_hash = _text(expected_receipt_hash)
    if expected_hash and receipt_hash and expected_hash != receipt_hash:
        diagnostics.append("temporal_receipt_hash_mismatch")
    receipt_created_at = receipt_metadata.get("receipt_created_at")
    if receipt_created_at in (None, ""):
        receipt_created_at = context.get("calibration_projection_receipt_created_at")
    if receipt_created_at in (None, ""):
        diagnostics.append("temporal_receipt_created_at_missing")
    else:
        try:
            parsed_receipt_created_at = parse_aware_datetime(
                receipt_created_at,
                "receipt_created_at",
            )
            context_receipt_clock = clocks.get(
                "calibration_projection_receipt_created_at"
            )
            if (
                context_receipt_clock is not None
                and parsed_receipt_created_at != context_receipt_clock
            ):
                diagnostics.append("temporal_receipt_created_at_mismatch")
        except ValueError:
            diagnostics.append("temporal_receipt_created_at_invalid")
    receipt_path = _text(
        receipt_metadata.get("path")
        or receipt_metadata.get("receipt_path")
        or context.get("calibration_projection_receipt_path")
    )
    if not receipt_path and not embedded_receipt_map.get("projections"):
        diagnostics.append("temporal_receipt_reference_missing")

    cutoff_date: str | None = None
    if context.get("as_of_date") not in (None, ""):
        try:
            cutoff_date = _iso_date(context.get("as_of_date"), "as_of_date")
        except ValueError:
            diagnostics.append("temporal_cutoff_date_invalid")
    else:
        diagnostics.append("temporal_cutoff_date_missing")
    if mode == "natural_producer_clock" and cutoff_date is not None:
        # A source-latest contract must agree with the consumed source's own
        # declared latest row when that field is available.  This closes the
        # old-cutoff-as-natural path without guessing a T-1 or weekday rule.
        source_latest = context.get("data_date")
        if source_latest in (None, ""):
            diagnostics.append("natural_source_latest_date_missing")
        else:
            try:
                if _iso_date(source_latest, "data_date") != cutoff_date:
                    diagnostics.append("natural_cutoff_not_source_latest")
            except ValueError:
                diagnostics.append("natural_source_latest_date_invalid")
    if actual_decision_date is not None and cutoff_date is not None:
        try:
            actual_date = _iso_date(actual_decision_date, "actual_decision_date")
            if cutoff_date > actual_date:
                diagnostics.append("temporal_cutoff_after_actual_decision")
        except ValueError:
            diagnostics.append("actual_decision_date_invalid")
    if diagnostics:
        return "invalid", tuple(dict.fromkeys(diagnostics))
    return ("historical" if mode.startswith("historical_") else "natural"), ()


def validate_forward_outcome_chronology(
    row: Mapping[str, Any],
    *,
    decision_at: str,
    decision_date: str,
) -> tuple[str, ...]:
    """Validate a realized forward label against the actual decision anchor.

    The outcome producer owns the official trading-session sequence.  The
    reader therefore verifies the persisted event/outcome dates and the
    declared ``window_days`` identity, but never reconstructs a horizon by
    subtracting calendar dates or by assuming weekdays are trading days.
    """

    if not isinstance(row, Mapping):
        return ("outcome_row_invalid",)
    diagnostics: list[str] = []
    try:
        decision = parse_aware_datetime(decision_at, "decision_at")
    except ValueError:
        return ("outcome_decision_clock_invalid",)
    try:
        actual_decision_date = _iso_date(decision_date, "decision_date")
    except ValueError:
        return ("outcome_decision_date_invalid",)

    def date_alias(field_name: str, aliases: tuple[str, ...]) -> str | None:
        values: list[str] = []
        for alias in aliases:
            value = _text(row.get(alias))
            if not value:
                continue
            try:
                normalized = _iso_date(value, field_name)
            except ValueError:
                diagnostics.append(f"{field_name}_invalid")
                continue
            if normalized not in values:
                values.append(normalized)
        if len(values) > 1:
            diagnostics.append(f"{field_name}_conflict")
        return values[0] if values else None

    def datetime_alias(field_name: str, aliases: tuple[str, ...]) -> datetime | None:
        values: list[datetime] = []
        for alias in aliases:
            value = row.get(alias)
            if value in (None, ""):
                continue
            try:
                parsed = parse_aware_datetime(value, field_name)
            except ValueError:
                diagnostics.append(f"{field_name}_invalid")
                continue
            if parsed not in values:
                values.append(parsed)
        if len(values) > 1:
            diagnostics.append(f"{field_name}_conflict")
        return values[0] if values else None

    event_price_date = date_alias(
        "outcome_event_price_date",
        ("event_price_date", "event_date"),
    )
    outcome_price_date = date_alias(
        "outcome_price_date",
        ("outcome_price_date",),
    )
    label_available_date = date_alias(
        "label_available_date",
        ("label_available_date",),
    )
    if event_price_date is not None and event_price_date != actual_decision_date:
        diagnostics.append("outcome_event_date_mismatch_actual_decision")
    if event_price_date is None:
        diagnostics.append("outcome_event_price_date_missing")
    if outcome_price_date is None:
        diagnostics.append("outcome_price_date_missing")
    if (
        event_price_date is not None
        and outcome_price_date is not None
        and outcome_price_date <= event_price_date
    ):
        diagnostics.append("outcome_price_date_not_after_event")
    if (
        outcome_price_date is not None
        and label_available_date is not None
        and label_available_date < outcome_price_date
    ):
        diagnostics.append("label_available_date_before_outcome_price")
    if label_available_date is not None and label_available_date < actual_decision_date:
        diagnostics.append("label_available_date_before_decision")

    label_available_at = datetime_alias(
        "label_available_at",
        ("label_available_at",),
    )
    if label_available_date is None:
        diagnostics.append("label_available_date_missing")
    if label_available_at is None:
        diagnostics.append("label_available_at_missing")
    # Match the read projection's precedence.  SQLite's technical
    # ``calculated_at`` may be a legacy naive timestamp even when the explicit
    # outcome_recorded_at is valid; an unused fallback alias must not poison
    # the selected clock.
    recorded_alias = next(
        (
            alias
            for alias in ("outcome_recorded_at", "recorded_at", "calculated_at")
            if row.get(alias) not in (None, "")
        ),
        None,
    )
    outcome_recorded_at = datetime_alias(
        "outcome_recorded_at",
        (recorded_alias,) if recorded_alias is not None else (),
    )
    if outcome_recorded_at is None:
        diagnostics.append("outcome_recorded_at_missing")
    if label_available_at is not None and label_available_at <= decision:
        diagnostics.append("label_available_at_before_or_at_decision")
    if outcome_recorded_at is not None and outcome_recorded_at < decision:
        diagnostics.append("outcome_recorded_at_before_decision")
    if (
        label_available_at is not None
        and outcome_recorded_at is not None
        and outcome_recorded_at < label_available_at
    ):
        diagnostics.append("outcome_recorded_at_before_label_available")

    data_as_of_date = date_alias("data_as_of_date", ("data_as_of_date",))
    if (
        outcome_price_date is not None
        and data_as_of_date is not None
        and data_as_of_date < outcome_price_date
    ):
        diagnostics.append("outcome_data_as_of_before_outcome_price")
    return tuple(dict.fromkeys(diagnostics))


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
    captured_at: str | None = None
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
        captured = (
            parse_aware_datetime(self.captured_at, "captured_at")
            if self.captured_at is not None
            else None
        )
        available = (
            parse_aware_datetime(self.available_at, "available_at")
            if self.available_at is not None
            else None
        )
        if declared > decision:
            raise ValueError("scope declared_at must not follow decision_at")
        if receipt < decision:
            raise ValueError("receipt_created_at must not precede decision_at")
        if captured is not None and captured > decision:
            raise ValueError("captured_at must not follow decision_at")
        temporal_status = _text(self.temporal_status) or (
            "verified" if available is not None else "temporal_precision_unproven"
        )
        if temporal_status not in {"verified", "temporal_precision_unproven"}:
            raise ValueError("unsupported personalization temporal_status")
        if available is None or captured is None:
            temporal_status = "temporal_precision_unproven"
        elif available > decision:
            raise ValueError("available_at must not follow decision_at")
        # Date-only fields are market dates, not UTC calendar dates.  In
        # particular, Taipei 00:xx belongs to the prior UTC date.
        decision_date = decision.astimezone(_MARKET_TIMEZONE).date().isoformat()
        available_date = (
            available.astimezone(_MARKET_TIMEZONE).date().isoformat()
            if available is not None
            else None
        )
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
        object.__setattr__(
            self,
            "captured_at",
            captured.isoformat(timespec="microseconds") if captured is not None else None,
        )
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
        captured_at: str | None = None,
        delivery_id: str | None = None,
        source: str = "recommendation_service",
    ) -> "PersonalizationDeliveryScope":
        now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        resolved_decision = canonical_aware_datetime(decision_at or now, "decision_at")
        resolved_receipt = canonical_aware_datetime(
            receipt_created_at or now,
            "receipt_created_at",
        )
        resolved_captured = (
            canonical_aware_datetime(captured_at, "captured_at")
            if captured_at is not None
            else None
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
            captured_at=resolved_captured,
            scope_status="bound" if _text(scope_id) else "unbound",
            temporal_status=(
                "verified"
                if available_at is not None and resolved_captured is not None
                else "temporal_precision_unproven"
            ),
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
            captured_at=self.captured_at,
            scope_status=self.scope_status,
            temporal_status=self.temporal_status,
            source=self.source,
            schema_version=self.schema_version,
        )

    @property
    def is_personal_scope(self) -> bool:
        # ``local`` is an explicit single-install research scope. It is
        # linkable for prediction evidence, but it is not a human/user
        # identity and must never be inferred from profile or holding data.
        return self.scope_status == "bound" and self.scope_type in {
            "user",
            "profile",
            "local",
        }

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
            "captured_at": self.captured_at,
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
            captured_at=(
                _text(value.get("captured_at")) or None
                if value.get("captured_at") is not None
                else None
            ),
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
class PersonalizationDeliveryCapture:
    """一個 exact prediction 的生成、保存與實際交付狀態。

    ``prediction_id`` 是 prediction identity，``delivery_id`` 是一次交付
    exposure identity；同一個 prediction 重新顯示時不應自動建立新的
    calibration row。這個 DTO 不自行寫檔，僅由既有 result/run-context
    保存或由 caller 暫存，並要求 caller 在真正顯示成功後才標記 delivered。
    """

    delivery_id: str
    request_id: str
    scope: PersonalizationDeliveryScope
    result_id: str
    stock_code: str
    prediction_id: str
    projection_receipt_hash: str
    generated_at: str
    projection_receipt_path: str | None = None
    status: str = "generated"
    persisted_at: str | None = None
    delivered_at: str | None = None
    source: str = "recommendation_service"
    model_id: str = ""
    dataset_id: str = ""
    dataset_hash: str = ""
    cost_scenario_hash: str | None = None
    horizon_days: int | None = None
    capture_hash: str = field(init=False)

    def __post_init__(self) -> None:
        for name in (
            "delivery_id",
            "request_id",
            "result_id",
            "stock_code",
            "prediction_id",
            "projection_receipt_hash",
            "generated_at",
        ):
            if not _text(getattr(self, name)):
                raise ValueError(f"{name} is required")
        try:
            UUID(_text(self.prediction_id))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("prediction_id must be a UUID") from exc
        if not _text(self.projection_receipt_hash).startswith("sha256:"):
            raise ValueError("projection_receipt_hash must be a sha256 hash")
        if self.scope.delivery_id != _text(self.delivery_id):
            raise ValueError("delivery_id must match scope delivery_id")
        if self.status not in PERSONALIZATION_DELIVERY_STATUSES:
            raise ValueError(f"unsupported personalization delivery status: {self.status}")
        generated = parse_aware_datetime(self.generated_at, "generated_at")
        scope_decision = parse_aware_datetime(self.scope.decision_at, "scope.decision_at")
        persisted = (
            parse_aware_datetime(self.persisted_at, "persisted_at")
            if self.persisted_at is not None
            else None
        )
        delivered = (
            parse_aware_datetime(self.delivered_at, "delivered_at")
            if self.delivered_at is not None
            else None
        )
        if persisted is not None and persisted < generated:
            raise ValueError("persisted_at must not precede generated_at")
        if generated > scope_decision:
            raise ValueError("generated_at must not follow scope decision_at")
        if delivered is not None and persisted is None:
            raise ValueError("delivered_at requires persisted_at")
        if delivered is not None and persisted is not None and delivered < persisted:
            raise ValueError("delivered_at must not precede persisted_at")
        if self.status == "persisted" and persisted is None:
            raise ValueError("persisted delivery requires persisted_at")
        if self.status == "delivered" and delivered is None:
            raise ValueError("delivered delivery requires delivered_at")
        if self.status == "generated" and (persisted is not None or delivered is not None):
            raise ValueError("generated delivery cannot have persistence timestamps")
        if self.status == "not_delivered" and delivered is not None:
            raise ValueError("not_delivered capture cannot have delivered_at")
        if self.horizon_days is not None and (
            isinstance(self.horizon_days, bool)
            or not isinstance(self.horizon_days, int)
            or self.horizon_days <= 0
        ):
            raise ValueError("horizon_days must be a positive integer or None")
        object.__setattr__(self, "delivery_id", _text(self.delivery_id))
        object.__setattr__(self, "request_id", _text(self.request_id))
        object.__setattr__(self, "result_id", _text(self.result_id))
        object.__setattr__(self, "stock_code", _text(self.stock_code))
        object.__setattr__(self, "prediction_id", _text(self.prediction_id))
        object.__setattr__(
            self,
            "projection_receipt_hash",
            _text(self.projection_receipt_hash),
        )
        object.__setattr__(
            self,
            "projection_receipt_path",
            _text(self.projection_receipt_path) or None,
        )
        object.__setattr__(self, "generated_at", generated.isoformat(timespec="microseconds"))
        object.__setattr__(
            self,
            "persisted_at",
            persisted.isoformat(timespec="microseconds") if persisted is not None else None,
        )
        object.__setattr__(
            self,
            "delivered_at",
            delivered.isoformat(timespec="microseconds") if delivered is not None else None,
        )
        object.__setattr__(self, "source", _text(self.source) or "recommendation_service")
        object.__setattr__(self, "model_id", _text(self.model_id))
        object.__setattr__(self, "dataset_id", _text(self.dataset_id))
        object.__setattr__(self, "dataset_hash", _text(self.dataset_hash))
        object.__setattr__(
            self,
            "cost_scenario_hash",
            _text(self.cost_scenario_hash) or None,
        )
        object.__setattr__(
            self,
            "capture_hash",
            canonical_payload_hash(self._hash_payload()),
        )

    @classmethod
    def create(
        cls,
        *,
        scope: PersonalizationDeliveryScope,
        request_id: str,
        result_id: str,
        stock_code: str,
        projection_receipt_hash: str,
        generated_at: str,
        prediction_id: str | None = None,
        projection_receipt_path: str | None = None,
        model_id: str = "",
        dataset_id: str = "",
        dataset_hash: str = "",
        cost_scenario_hash: str | None = None,
        horizon_days: int | None = None,
    ) -> "PersonalizationDeliveryCapture":
        return cls(
            delivery_id=scope.delivery_id,
            request_id=request_id,
            scope=scope,
            result_id=result_id,
            stock_code=stock_code,
            prediction_id=prediction_id or str(uuid4()),
            projection_receipt_hash=projection_receipt_hash,
            generated_at=generated_at,
            projection_receipt_path=projection_receipt_path,
            model_id=model_id,
            dataset_id=dataset_id,
            dataset_hash=dataset_hash,
            cost_scenario_hash=cost_scenario_hash,
            horizon_days=horizon_days,
        )

    def _hash_payload(self) -> dict[str, Any]:
        return {
            "schema_version": PERSONALIZATION_DELIVERY_CAPTURE_SCHEMA_VERSION,
            "delivery_id": self.delivery_id,
            "request_id": self.request_id,
            "scope_hash": self.scope.envelope_hash,
            "result_id": self.result_id,
            "stock_code": self.stock_code,
            "prediction_id": self.prediction_id,
            "projection_receipt_hash": self.projection_receipt_hash,
            "projection_receipt_path": self.projection_receipt_path,
            "generated_at": self.generated_at,
            "persisted_at": self.persisted_at,
            "delivered_at": self.delivered_at,
            "status": self.status,
            "source": self.source,
            "model_id": self.model_id,
            "dataset_id": self.dataset_id,
            "dataset_hash": self.dataset_hash,
            "cost_scenario_hash": self.cost_scenario_hash,
            "horizon_days": self.horizon_days,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._hash_payload(),
            "scope": self.scope.to_dict(),
            "capture_hash": self.capture_hash,
        }

    def mark_persisted(self, persisted_at: str) -> "PersonalizationDeliveryCapture":
        if self.status not in {"generated", "persisted", "not_delivered"}:
            raise ValueError("delivered capture cannot be marked persisted")
        return PersonalizationDeliveryCapture(
            delivery_id=self.delivery_id,
            request_id=self.request_id,
            scope=self.scope,
            result_id=self.result_id,
            stock_code=self.stock_code,
            prediction_id=self.prediction_id,
            projection_receipt_hash=self.projection_receipt_hash,
            generated_at=self.generated_at,
            projection_receipt_path=self.projection_receipt_path,
            status="persisted",
            persisted_at=persisted_at,
            source=self.source,
            model_id=self.model_id,
            dataset_id=self.dataset_id,
            dataset_hash=self.dataset_hash,
            cost_scenario_hash=self.cost_scenario_hash,
            horizon_days=self.horizon_days,
        )

    def mark_delivered(self, delivered_at: str) -> "PersonalizationDeliveryCapture":
        if self.status != "persisted":
            raise ValueError("only a persisted capture can be marked delivered")
        return PersonalizationDeliveryCapture(
            delivery_id=self.delivery_id,
            request_id=self.request_id,
            scope=self.scope,
            result_id=self.result_id,
            stock_code=self.stock_code,
            prediction_id=self.prediction_id,
            projection_receipt_hash=self.projection_receipt_hash,
            generated_at=self.generated_at,
            projection_receipt_path=self.projection_receipt_path,
            status="delivered",
            persisted_at=self.persisted_at,
            delivered_at=delivered_at,
            source=self.source,
            model_id=self.model_id,
            dataset_id=self.dataset_id,
            dataset_hash=self.dataset_hash,
            cost_scenario_hash=self.cost_scenario_hash,
            horizon_days=self.horizon_days,
        )

    def mark_not_delivered(self) -> "PersonalizationDeliveryCapture":
        if self.status == "delivered":
            raise ValueError("delivered capture cannot be marked not_delivered")
        return PersonalizationDeliveryCapture(
            delivery_id=self.delivery_id,
            request_id=self.request_id,
            scope=self.scope,
            result_id=self.result_id,
            stock_code=self.stock_code,
            prediction_id=self.prediction_id,
            projection_receipt_hash=self.projection_receipt_hash,
            generated_at=self.generated_at,
            projection_receipt_path=self.projection_receipt_path,
            status="not_delivered",
            persisted_at=self.persisted_at,
            source=self.source,
            model_id=self.model_id,
            dataset_id=self.dataset_id,
            dataset_hash=self.dataset_hash,
            cost_scenario_hash=self.cost_scenario_hash,
            horizon_days=self.horizon_days,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PersonalizationDeliveryCapture":
        if not isinstance(value, Mapping):
            raise ValueError("personalization delivery capture must be an object")
        raw_scope = value.get("scope")
        if not isinstance(raw_scope, Mapping):
            raise ValueError("personalization delivery capture scope is missing")
        raw_horizon = value.get("horizon_days")
        capture = cls(
            delivery_id=_text(value.get("delivery_id")),
            request_id=_text(value.get("request_id")),
            scope=PersonalizationDeliveryScope.from_mapping(raw_scope),
            result_id=_text(value.get("result_id")),
            stock_code=_text(value.get("stock_code")),
            prediction_id=_text(value.get("prediction_id")),
            projection_receipt_hash=_text(value.get("projection_receipt_hash")),
            generated_at=_text(value.get("generated_at")),
            projection_receipt_path=(
                _text(value.get("projection_receipt_path")) or None
                if value.get("projection_receipt_path") is not None
                else None
            ),
            status=_text(value.get("status")) or "generated",
            persisted_at=(
                _text(value.get("persisted_at")) or None
                if value.get("persisted_at") is not None
                else None
            ),
            delivered_at=(
                _text(value.get("delivered_at")) or None
                if value.get("delivered_at") is not None
                else None
            ),
            source=_text(value.get("source")) or "recommendation_service",
            model_id=_text(value.get("model_id")),
            dataset_id=_text(value.get("dataset_id")),
            dataset_hash=_text(value.get("dataset_hash")),
            cost_scenario_hash=(
                _text(value.get("cost_scenario_hash")) or None
                if value.get("cost_scenario_hash") is not None
                else None
            ),
            horizon_days=(int(str(raw_horizon)) if raw_horizon is not None else None),
        )
        if _text(value.get("capture_hash")) != capture.capture_hash:
            raise ValueError("personalization delivery capture hash mismatch")
        return capture


@dataclass(frozen=True)
class PersonalizationActionEnvelope:
    """可放入既有 append-only revision payload 的 typed action envelope。"""

    personalization_scope_id: str
    result_id: str
    stock_code: str
    prediction_id: str
    prediction_receipt_hash: str
    decision_kind: str
    action: str
    action_state: str
    action_at: str
    recorded_at: str
    request_id: str
    action_source: str = "decision_continuity"
    actor: str = ""
    decision_revision_id: str = ""
    continuity_event_id: str = ""
    revision_of: str = ""
    user_intent: str = "research"
    execution_state: str = "not_executed"
    # These immutable prediction-contract fields are optional at the generic
    # DTO boundary for backward compatibility, but the controlled
    # PersonalizationDecisionRecorder requires them for a new personal action.
    horizon_days: int | None = None
    cost_scenario_hash: str | None = None
    label_contract_id: str = ""
    return_basis: str = ""
    schema_version: str = PERSONALIZATION_ACTION_SCHEMA_VERSION
    envelope_hash: str = field(init=False)

    def __post_init__(self) -> None:
        for name in (
            "personalization_scope_id",
            "result_id",
            "stock_code",
            "prediction_id",
            "prediction_receipt_hash",
            "decision_kind",
            "action",
            "action_state",
            "request_id",
            "action_source",
        ):
            if not _text(getattr(self, name)):
                raise ValueError(f"{name} is required")
        try:
            UUID(_text(self.prediction_id))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("prediction_id must be a UUID") from exc
        if self.prediction_receipt_hash and not self.prediction_receipt_hash.startswith("sha256:"):
            raise ValueError("prediction_receipt_hash must be a sha256 hash")
        if self.action not in PERSONALIZATION_ACTIONS:
            raise ValueError(f"unsupported personalization action: {self.action}")
        if self.action_state not in PERSONALIZATION_ACTION_STATES:
            raise ValueError(f"unsupported personalization action_state: {self.action_state}")
        if self.horizon_days is not None and (
            isinstance(self.horizon_days, bool)
            or not isinstance(self.horizon_days, int)
            or self.horizon_days <= 0
        ):
            raise ValueError("horizon_days must be a positive integer or None")
        if self.cost_scenario_hash is not None:
            cost_hash = _text(self.cost_scenario_hash)
            if not cost_hash:
                raise ValueError("cost_scenario_hash must be non-empty when supplied")
            if not cost_hash.startswith("sha256:"):
                raise ValueError("cost_scenario_hash must be a sha256 hash")
        action_at = parse_aware_datetime(self.action_at, "action_at")
        recorded_at = parse_aware_datetime(self.recorded_at, "recorded_at")
        if recorded_at < action_at:
            raise ValueError("recorded_at must not precede action_at")
        if self.schema_version != PERSONALIZATION_ACTION_SCHEMA_VERSION:
            raise ValueError("unsupported personalization action schema")
        object.__setattr__(self, "personalization_scope_id", _text(self.personalization_scope_id))
        object.__setattr__(self, "result_id", _text(self.result_id))
        object.__setattr__(self, "stock_code", _text(self.stock_code))
        object.__setattr__(self, "prediction_id", _text(self.prediction_id))
        object.__setattr__(self, "prediction_receipt_hash", _text(self.prediction_receipt_hash))
        object.__setattr__(self, "decision_kind", _text(self.decision_kind))
        object.__setattr__(self, "action_at", action_at.isoformat(timespec="microseconds"))
        object.__setattr__(self, "recorded_at", recorded_at.isoformat(timespec="microseconds"))
        object.__setattr__(self, "request_id", _text(self.request_id))
        object.__setattr__(self, "action_source", _text(self.action_source))
        object.__setattr__(self, "actor", _text(self.actor))
        object.__setattr__(self, "decision_revision_id", _text(self.decision_revision_id))
        object.__setattr__(self, "continuity_event_id", _text(self.continuity_event_id))
        object.__setattr__(self, "revision_of", _text(self.revision_of))
        object.__setattr__(self, "user_intent", _text(self.user_intent) or "research")
        object.__setattr__(self, "execution_state", _text(self.execution_state) or "not_executed")
        object.__setattr__(self, "cost_scenario_hash", _text(self.cost_scenario_hash) or None)
        object.__setattr__(self, "label_contract_id", _text(self.label_contract_id))
        object.__setattr__(self, "return_basis", _text(self.return_basis))
        object.__setattr__(self, "envelope_hash", canonical_payload_hash(self._hash_payload()))

    def _hash_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "personalization_scope_id": self.personalization_scope_id,
            "result_id": self.result_id,
            "stock_code": self.stock_code,
            "prediction_id": self.prediction_id,
            "prediction_receipt_hash": self.prediction_receipt_hash,
            "decision_kind": self.decision_kind,
            "action": self.action,
            "action_state": self.action_state,
            "action_at": self.action_at,
            "recorded_at": self.recorded_at,
            "request_id": self.request_id,
            "action_source": self.action_source,
            "actor": self.actor,
            "decision_revision_id": self.decision_revision_id,
            "continuity_event_id": self.continuity_event_id,
            "revision_of": self.revision_of,
            "user_intent": self.user_intent,
            "execution_state": self.execution_state,
            "horizon_days": self.horizon_days,
            "cost_scenario_hash": self.cost_scenario_hash,
            "label_contract_id": self.label_contract_id,
            "return_basis": self.return_basis,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._hash_payload(), "envelope_hash": self.envelope_hash}

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PersonalizationActionEnvelope":
        if not isinstance(value, Mapping):
            raise ValueError("personalization action envelope must be an object")
        raw_horizon = value.get("horizon_days")
        envelope = cls(
            personalization_scope_id=_text(value.get("personalization_scope_id")),
            result_id=_text(value.get("result_id")),
            stock_code=_text(value.get("stock_code")),
            prediction_id=_text(value.get("prediction_id")),
            prediction_receipt_hash=_text(value.get("prediction_receipt_hash")),
            decision_kind=_text(value.get("decision_kind")),
            action=_text(value.get("action")),
            action_state=_text(value.get("action_state")),
            action_at=_text(value.get("action_at")),
            recorded_at=_text(value.get("recorded_at")),
            request_id=_text(value.get("request_id")),
            action_source=_text(value.get("action_source")) or "decision_continuity",
            actor=_text(value.get("actor")),
            decision_revision_id=_text(value.get("decision_revision_id")),
            continuity_event_id=_text(value.get("continuity_event_id")),
            revision_of=_text(value.get("revision_of")),
            user_intent=_text(value.get("user_intent")) or "research",
            execution_state=_text(value.get("execution_state")) or "not_executed",
            horizon_days=(int(str(raw_horizon)) if raw_horizon is not None else None),
            cost_scenario_hash=(
                _text(value.get("cost_scenario_hash")) or None
                if value.get("cost_scenario_hash") is not None
                else None
            ),
            label_contract_id=_text(value.get("label_contract_id")),
            return_basis=_text(value.get("return_basis")),
            schema_version=_text(value.get("schema_version"))
            or PERSONALIZATION_ACTION_SCHEMA_VERSION,
        )
        if _text(value.get("envelope_hash")) != envelope.envelope_hash:
            raise ValueError("personalization action envelope hash mismatch")
        return envelope


@dataclass(frozen=True)
class PersonalRecommendationOverrideReason:
    """個人推翻原建議時必須保存的結構化理由。"""

    code: str
    detail: str

    def __post_init__(self) -> None:
        if not _text(self.code) or not _text(self.detail):
            raise ValueError("override reason requires non-empty code and detail")
        object.__setattr__(self, "code", _text(self.code))
        object.__setattr__(self, "detail", _text(self.detail))

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any]
    ) -> "PersonalRecommendationOverrideReason":
        if not isinstance(value, Mapping) or set(value) != {"code", "detail"}:
            raise ValueError("override reason fields are invalid")
        if type(value["code"]) is not str or type(value["detail"]) is not str:
            raise ValueError("override reason fields must be strings")
        return cls(code=value["code"], detail=value["detail"])


@dataclass(frozen=True)
class PersonalRecommendationModelEvidence:
    """只記錄已由 canonical read model 驗證的所選股票模型投影。"""

    candidate_id: str
    candidate_root: str
    candidate_json_sha256: str
    candidate_manifest_hash: str
    candidate_artifact_hash: str
    candidate_freeze_hash: str
    dataset_hash: str
    receipt_reference: str
    receipt_hash: str
    projection_reference: str
    projection_rows_sha256: str
    stock_code: str
    decision_date: str
    model_version: str
    ranking_score_bp: int | None
    calibrated_probability_bp: int
    calibrated_probability_status: str
    cost_scenario_hash: str | None = None
    schema_version: str = PERSONAL_RECOMMENDATION_MODEL_EVIDENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "candidate_id",
            "candidate_root",
            "receipt_reference",
            "projection_reference",
            "stock_code",
            "model_version",
        ):
            if not _text(getattr(self, name)):
                raise ValueError(f"model evidence {name} is required")
        if not Path(self.candidate_root).is_absolute():
            raise ValueError("model evidence candidate_root must be absolute")
        for name in (
            "candidate_json_sha256",
            "candidate_manifest_hash",
            "candidate_artifact_hash",
            "candidate_freeze_hash",
            "dataset_hash",
        ):
            _require_choice_hash(getattr(self, name), name)
        _require_choice_hash(self.receipt_hash, "receipt_hash")
        _require_choice_hash(self.projection_rows_sha256, "projection_rows_sha256")
        if self.projection_reference != self.projection_rows_sha256:
            raise ValueError("projection reference must bind the saved projection rows")
        if self.model_version != self.candidate_id:
            raise ValueError("model version must match the selected candidate")
        if self.schema_version != PERSONAL_RECOMMENDATION_MODEL_EVIDENCE_SCHEMA_VERSION:
            raise ValueError("unsupported personal model evidence schema")
        normalized_day = _iso_date(self.decision_date, "decision_date")
        if normalized_day != self.decision_date:
            raise ValueError("decision_date must be a canonical ISO date")
        if (
            isinstance(self.ranking_score_bp, bool)
            or (
                self.ranking_score_bp is not None
                and type(self.ranking_score_bp) is not int
            )
        ):
            raise ValueError("ranking_score_bp must be an integer or None")
        if (
            isinstance(self.calibrated_probability_bp, bool)
            or type(self.calibrated_probability_bp) is not int
            or not 0 <= self.calibrated_probability_bp <= 10_000
        ):
            raise ValueError("calibrated_probability_bp must be 0..10000 basis points")
        if self.calibrated_probability_status != "active_effective":
            raise ValueError("personal model evidence requires an effective saved projection")
        if self.cost_scenario_hash is not None:
            _require_choice_hash(self.cost_scenario_hash, "cost_scenario_hash")
        for name in (
            "candidate_id",
            "candidate_root",
            "candidate_json_sha256",
            "candidate_manifest_hash",
            "candidate_artifact_hash",
            "candidate_freeze_hash",
            "dataset_hash",
            "receipt_reference",
            "projection_reference",
            "stock_code",
            "model_version",
            "calibrated_probability_status",
        ):
            object.__setattr__(self, name, _text(getattr(self, name)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "candidate_id": self.candidate_id,
            "candidate_root": self.candidate_root,
            "candidate_json_sha256": self.candidate_json_sha256,
            "candidate_manifest_hash": self.candidate_manifest_hash,
            "candidate_artifact_hash": self.candidate_artifact_hash,
            "candidate_freeze_hash": self.candidate_freeze_hash,
            "dataset_hash": self.dataset_hash,
            "receipt_reference": self.receipt_reference,
            "receipt_hash": self.receipt_hash,
            "projection_reference": self.projection_reference,
            "projection_rows_sha256": self.projection_rows_sha256,
            "stock_code": self.stock_code,
            "decision_date": self.decision_date,
            "model_version": self.model_version,
            "ranking_score_bp": self.ranking_score_bp,
            "calibrated_probability_bp": self.calibrated_probability_bp,
            "calibrated_probability_status": self.calibrated_probability_status,
            "cost_scenario_hash": self.cost_scenario_hash,
        }

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any]
    ) -> "PersonalRecommendationModelEvidence":
        fields = {
            "schema_version",
            "candidate_id",
            "candidate_root",
            "candidate_json_sha256",
            "candidate_manifest_hash",
            "candidate_artifact_hash",
            "candidate_freeze_hash",
            "dataset_hash",
            "receipt_reference",
            "receipt_hash",
            "projection_reference",
            "projection_rows_sha256",
            "stock_code",
            "decision_date",
            "model_version",
            "ranking_score_bp",
            "calibrated_probability_bp",
            "calibrated_probability_status",
            "cost_scenario_hash",
        }
        if not isinstance(value, Mapping) or set(value) != fields:
            raise ValueError("personal model evidence fields are invalid")
        text_fields = fields - {
            "ranking_score_bp",
            "calibrated_probability_bp",
            "cost_scenario_hash",
        }
        if any(type(value[name]) is not str for name in text_fields):
            raise ValueError("personal model evidence text fields must be strings")
        if value["cost_scenario_hash"] is not None and type(
            value["cost_scenario_hash"]
        ) is not str:
            raise ValueError("cost_scenario_hash must be a string or None")
        return cls(**dict(value))


@dataclass(frozen=True)
class PersonalRecommendationChoice:
    """對一筆已保存推薦的明確個人採用、拒絕或推翻事件。"""

    result_id: str
    stock_code: str
    decision_date: str
    source_snapshot_id: str
    source_snapshot_hash: str
    canonical_payload_hash: str
    raw_artifact_sha256: str
    choice: str
    requested_mode: str
    effective_mode: str
    action_at: str
    recorded_at: str
    request_id: str
    policy_snapshot: Mapping[str, Any] | None = None
    override_reason: PersonalRecommendationOverrideReason | None = None
    model_evidence: PersonalRecommendationModelEvidence | None = None
    schema_version: str = PERSONAL_RECOMMENDATION_CHOICE_SCHEMA_VERSION
    choice_hash: str = field(init=False)

    def __post_init__(self) -> None:
        for name in ("result_id", "stock_code", "request_id"):
            if not _text(getattr(self, name)):
                raise ValueError(f"{name} is required")
        if self.choice not in {"adopt", "reject", "override"}:
            raise ValueError("choice must be adopt, reject, or override")
        if self.requested_mode not in {"rule_only", "personal_calibrated_probability"}:
            raise ValueError("requested_mode is invalid")
        if self.effective_mode not in {"rule_only", "personal_calibrated_probability"}:
            raise ValueError("effective_mode is invalid")
        _require_choice_hash(self.canonical_payload_hash, "canonical_payload_hash")
        _require_choice_hash(self.raw_artifact_sha256, "raw_artifact_sha256")
        if not _text(self.source_snapshot_id):
            raise ValueError("source_snapshot_id is required")
        _require_choice_hash(self.source_snapshot_hash, "source_snapshot_hash")
        normalized_day = _iso_date(self.decision_date, "decision_date")
        if normalized_day != self.decision_date:
            raise ValueError("decision_date must be a canonical ISO date")
        action_at = parse_aware_datetime(self.action_at, "action_at")
        recorded_at = parse_aware_datetime(self.recorded_at, "recorded_at")
        if recorded_at < action_at:
            raise ValueError("recorded_at must not precede action_at")
        if self.schema_version != PERSONAL_RECOMMENDATION_CHOICE_SCHEMA_VERSION:
            raise ValueError("unsupported personal recommendation choice schema")
        if (self.choice == "override") != (self.override_reason is not None):
            raise ValueError("override requires a structured reason; other choices forbid it")
        if self.override_reason is not None and type(
            self.override_reason
        ) is not PersonalRecommendationOverrideReason:
            raise TypeError("override_reason must be PersonalRecommendationOverrideReason")
        if (self.effective_mode == "personal_calibrated_probability") != (
            self.model_evidence is not None
        ):
            raise ValueError("effective personal model mode requires selected-stock evidence")
        if self.model_evidence is not None:
            if type(self.model_evidence) is not PersonalRecommendationModelEvidence:
                raise TypeError("model_evidence must be PersonalRecommendationModelEvidence")
            if (
                self.model_evidence.stock_code != self.stock_code
                or self.model_evidence.decision_date != self.decision_date
            ):
                raise ValueError("model evidence must match selected stock and saved decision date")
        frozen_policy: Mapping[str, Any] | None = None
        if self.policy_snapshot is None:
            raise ValueError("new personal recommendation choice requires a policy snapshot")
        if self.policy_snapshot is not None:
            frozen = _freeze_choice_value(self.policy_snapshot, "policy_snapshot")
            if not isinstance(frozen, Mapping):
                raise TypeError("policy_snapshot must be an object")
            required = {
                "schema_version",
                "policy_version",
                "revision",
                "scope_id",
                "mode",
                "policy_sha256",
            }
            if not required.issubset(frozen):
                raise ValueError("policy_snapshot identity is incomplete")
            if type(frozen["policy_version"]) is not int or type(frozen["revision"]) is not int:
                raise ValueError("policy_snapshot version/revision must be integers")
            if frozen["revision"] < 0:
                raise ValueError("policy_snapshot revision must be non-negative")
            schema_version = frozen["schema_version"]
            policy_version = frozen["policy_version"]
            if (schema_version, policy_version) not in {
                ("recommendation-personal-use-policy.v1", 1),
                ("recommendation-personal-use-policy.v2", 2),
            }:
                raise ValueError("policy_snapshot schema version is unsupported")
            if not _text(frozen["scope_id"]):
                raise ValueError("policy_snapshot version/scope is invalid")
            if frozen["mode"] not in {"rule_only", "personal_calibrated_probability"}:
                raise ValueError("policy_snapshot mode is invalid")
            if frozen["mode"] != self.requested_mode:
                raise ValueError("requested_mode must match saved policy snapshot")
            _require_choice_hash(frozen["policy_sha256"], "policy_snapshot.policy_sha256")
            from app_module.recommendation.personal_use_policy import (
                validate_personal_use_policy_snapshot,
            )

            try:
                validated_policy = validate_personal_use_policy_snapshot(
                    _thaw_choice_value(frozen)
                )
            except (TypeError, ValueError) as exc:
                raise ValueError("policy_snapshot does not match its versioned schema/hash") from exc
            if validated_policy != _thaw_choice_value(frozen):
                raise ValueError("policy_snapshot is not a canonical saved identity")
            if self.model_evidence is not None:
                candidate = frozen.get("candidate")
                if not isinstance(candidate, Mapping):
                    raise ValueError("model evidence requires a pinned policy candidate")
                for name in (
                    "candidate_id",
                    "candidate_root",
                    "candidate_json_sha256",
                    "candidate_manifest_hash",
                    "candidate_artifact_hash",
                    "candidate_freeze_hash",
                    "dataset_hash",
                ):
                    if candidate.get(name) != getattr(self.model_evidence, name):
                        raise ValueError(
                            f"model evidence {name} differs from the saved policy pin"
                        )
            frozen_policy = frozen
        if self.effective_mode == "personal_calibrated_probability":
            if self.requested_mode != "personal_calibrated_probability":
                raise ValueError("effective personal model mode conflicts with requested mode")
        object.__setattr__(self, "result_id", _text(self.result_id))
        object.__setattr__(self, "stock_code", _text(self.stock_code))
        object.__setattr__(self, "source_snapshot_id", _text(self.source_snapshot_id))
        object.__setattr__(self, "request_id", _text(self.request_id))
        object.__setattr__(self, "action_at", action_at.isoformat(timespec="microseconds"))
        object.__setattr__(self, "recorded_at", recorded_at.isoformat(timespec="microseconds"))
        object.__setattr__(self, "policy_snapshot", frozen_policy)
        object.__setattr__(self, "choice_hash", canonical_payload_hash(self._hash_payload()))

    def _hash_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "result_id": self.result_id,
            "stock_code": self.stock_code,
            "decision_date": self.decision_date,
            "source_snapshot_id": self.source_snapshot_id,
            "source_snapshot_hash": self.source_snapshot_hash,
            "canonical_payload_hash": self.canonical_payload_hash,
            "raw_artifact_sha256": self.raw_artifact_sha256,
            "choice": self.choice,
            "requested_mode": self.requested_mode,
            "effective_mode": self.effective_mode,
            "policy_snapshot": (
                _thaw_choice_value(self.policy_snapshot)
                if self.policy_snapshot is not None
                else None
            ),
            "override_reason": (
                self.override_reason.to_dict() if self.override_reason is not None else None
            ),
            "model_evidence": (
                self.model_evidence.to_dict() if self.model_evidence is not None else None
            ),
            "action_at": self.action_at,
            "recorded_at": self.recorded_at,
            "request_id": self.request_id,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._hash_payload(), "choice_hash": self.choice_hash}

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PersonalRecommendationChoice":
        fields = {
            "schema_version",
            "result_id",
            "stock_code",
            "decision_date",
            "source_snapshot_id",
            "source_snapshot_hash",
            "canonical_payload_hash",
            "raw_artifact_sha256",
            "choice",
            "requested_mode",
            "effective_mode",
            "policy_snapshot",
            "override_reason",
            "model_evidence",
            "action_at",
            "recorded_at",
            "request_id",
            "choice_hash",
        }
        if not isinstance(value, Mapping) or set(value) != fields:
            raise ValueError("personal recommendation choice fields are invalid")
        text_fields = fields - {"policy_snapshot", "override_reason", "model_evidence"}
        if any(type(value[name]) is not str for name in text_fields):
            raise ValueError("personal recommendation choice text fields must be strings")
        reason_value = value["override_reason"]
        if reason_value is not None:
            if not isinstance(reason_value, Mapping):
                raise ValueError("override_reason must be an object or None")
            reason = PersonalRecommendationOverrideReason.from_mapping(reason_value)
        else:
            reason = None
        model_value = value["model_evidence"]
        if model_value is not None:
            if not isinstance(model_value, Mapping):
                raise ValueError("model_evidence must be an object or None")
            model_evidence = PersonalRecommendationModelEvidence.from_mapping(model_value)
        else:
            model_evidence = None
        policy_value = value["policy_snapshot"]
        if policy_value is not None and not isinstance(policy_value, Mapping):
            raise ValueError("policy_snapshot must be an object or None")
        choice = cls(
            result_id=value["result_id"],
            stock_code=value["stock_code"],
            decision_date=value["decision_date"],
            source_snapshot_id=value["source_snapshot_id"],
            source_snapshot_hash=value["source_snapshot_hash"],
            canonical_payload_hash=value["canonical_payload_hash"],
            raw_artifact_sha256=value["raw_artifact_sha256"],
            choice=value["choice"],
            requested_mode=value["requested_mode"],
            effective_mode=value["effective_mode"],
            action_at=value["action_at"],
            recorded_at=value["recorded_at"],
            request_id=value["request_id"],
            policy_snapshot=policy_value,
            override_reason=reason,
            model_evidence=model_evidence,
            schema_version=value["schema_version"],
        )
        if value["choice_hash"] != choice.choice_hash:
            raise ValueError("personal recommendation choice hash mismatch")
        return choice


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
    label_available_at: str | None = None
    outcome_recorded_at: str | None = None
    outcome_tier: str = "natural_forward"
    action_state: str = "not_recorded"
    decision_at: str | None = None
    available_at: str | None = None
    receipt_created_at: str | None = None
    captured_at: str | None = None
    # Keep the producer inference anchor, delivery ACK, and human/evaluation
    # anchor observable as separate clocks.  ``decision_at`` remains the
    # backward-compatible producer anchor; the explicit aliases prevent a
    # later action timestamp from being mistaken for source cutoff or model
    # inference time.
    prediction_decision_at: str | None = None
    delivery_at: str | None = None
    human_decision_at: str | None = None
    decision_day_block: str | None = None
    row_id: str = ""
    personal_observation_count: int = 0
    personal_positive_count: int = 0
    outcome_status: str = "ready"
    delivery_status: str = "not_recorded"
    late_delivery: bool = False
    source_result_id: str = ""
    prediction_receipt_hash: str = ""
    model_id: str = ""
    dataset_id: str = ""
    dataset_hash: str = ""
    cost_scenario_id: str = ""
    cost_scenario_version: str = ""
    universe_policy_hash: str = ""
    label_contract_id: str = ""
    return_basis: str = ""
    source_id: str = ""
    prediction_receipt_schema_version: str = PERSONALIZATION_PREDICTION_RECEIPT_SCHEMA_VERSION
    statistical_id: str = ""
    outcome_id: str = ""
    event_id: str = ""
    window_days: int | None = None

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
        if self.outcome_status not in PERSONALIZATION_OUTCOME_STATUSES:
            raise ValueError(f"unsupported outcome_status: {self.outcome_status}")
        if self.delivery_status not in PERSONALIZATION_DELIVERY_STATUSES:
            raise ValueError(f"unsupported delivery_status: {self.delivery_status}")
        if not isinstance(self.late_delivery, bool):
            raise ValueError("late_delivery must be boolean")
        if self.action_state not in PERSONALIZATION_ACTION_STATES:
            raise ValueError(f"unsupported action_state: {self.action_state}")
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
        captured = (
            parse_aware_datetime(self.captured_at, "captured_at")
            if self.captured_at is not None
            else None
        )
        if available is not None and decision is not None and available > decision:
            raise ValueError("available_at must not follow decision_at")
        if captured is not None and decision is not None and captured > decision:
            raise ValueError("captured_at must not follow decision_at")
        if self.receipt_created_at is not None and decision is not None:
            if parse_aware_datetime(self.receipt_created_at, "receipt_created_at") < decision:
                raise ValueError("receipt_created_at must not precede decision_at")
        label_available = (
            parse_aware_datetime(self.label_available_at, "label_available_at")
            if self.label_available_at is not None
            else None
        )
        outcome_recorded = (
            parse_aware_datetime(self.outcome_recorded_at, "outcome_recorded_at")
            if self.outcome_recorded_at is not None
            else None
        )
        if label_available is not None and label_available.astimezone(_MARKET_TIMEZONE).date().isoformat() != _iso_date(
            self.label_available_date,
            "label_available_date",
        ):
            raise ValueError("label_available_at date must match label_available_date")
        if (
            label_available is not None
            and outcome_recorded is not None
            and outcome_recorded < label_available
        ):
            raise ValueError("outcome_recorded_at must not precede label_available_at")
        if label_available is not None and decision is not None and label_available <= decision:
            raise ValueError("label_available_at must follow decision_at")
        if outcome_recorded is not None and decision is not None and outcome_recorded < decision:
            raise ValueError("outcome_recorded_at must not precede decision_at")
        if date.fromisoformat(
            _iso_date(self.label_available_date, "label_available_date")
        ) < date.fromisoformat(_iso_date(self.decision_date, "decision_date")):
            raise ValueError("label_available_date must not precede decision_date")
        # ``decision_date`` is the market/data cutoff day while ``decision_at``
        # is the actual producer execution instant.  A legitimate T-1 market
        # cutoff can therefore be followed by a next-calendar-day runtime.
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
        if self.captured_at is not None:
            object.__setattr__(
                self,
                "captured_at",
                canonical_aware_datetime(self.captured_at, "captured_at"),
            )
        if self.prediction_decision_at is not None:
            object.__setattr__(
                self,
                "prediction_decision_at",
                canonical_aware_datetime(
                    self.prediction_decision_at,
                    "prediction_decision_at",
                ),
            )
        if self.delivery_at is not None:
            object.__setattr__(
                self,
                "delivery_at",
                canonical_aware_datetime(self.delivery_at, "delivery_at"),
            )
        if self.human_decision_at is not None:
            object.__setattr__(
                self,
                "human_decision_at",
                canonical_aware_datetime(
                    self.human_decision_at,
                    "human_decision_at",
                ),
            )
        if self.delivery_at is not None and self.human_decision_at is not None:
            if parse_aware_datetime(self.human_decision_at, "human_decision_at") < parse_aware_datetime(
                self.delivery_at,
                "delivery_at",
            ):
                raise ValueError("human_decision_at must not precede delivery_at")
        if self.prediction_receipt_hash and not _text(self.prediction_receipt_hash).startswith("sha256:"):
            raise ValueError("prediction_receipt_hash must be a sha256 hash")
        object.__setattr__(self, "source_result_id", _text(self.source_result_id))
        object.__setattr__(self, "prediction_receipt_hash", _text(self.prediction_receipt_hash))
        object.__setattr__(self, "model_id", _text(self.model_id))
        object.__setattr__(self, "dataset_id", _text(self.dataset_id))
        object.__setattr__(self, "dataset_hash", _text(self.dataset_hash))
        object.__setattr__(self, "cost_scenario_id", _text(self.cost_scenario_id))
        object.__setattr__(self, "cost_scenario_version", _text(self.cost_scenario_version))
        object.__setattr__(self, "universe_policy_hash", _text(self.universe_policy_hash))
        object.__setattr__(self, "label_contract_id", _text(self.label_contract_id))
        object.__setattr__(self, "return_basis", _text(self.return_basis))
        object.__setattr__(self, "source_id", _text(self.source_id))
        object.__setattr__(
            self,
            "prediction_receipt_schema_version",
            _text(self.prediction_receipt_schema_version)
            or PERSONALIZATION_PREDICTION_RECEIPT_SCHEMA_VERSION,
        )
        object.__setattr__(self, "statistical_id", _text(self.statistical_id))
        object.__setattr__(self, "outcome_id", _text(self.outcome_id))
        object.__setattr__(self, "event_id", _text(self.event_id))
        if self.window_days is not None and (
            isinstance(self.window_days, bool)
            or not isinstance(self.window_days, int)
            or self.window_days <= 0
        ):
            raise ValueError("window_days must be a positive integer or None")
        if self.label_available_at is not None:
            object.__setattr__(
                self,
                "label_available_at",
                canonical_aware_datetime(self.label_available_at, "label_available_at"),
            )
        if self.outcome_recorded_at is not None:
            object.__setattr__(
                self,
                "outcome_recorded_at",
                canonical_aware_datetime(self.outcome_recorded_at, "outcome_recorded_at"),
            )

    @property
    def effective_row_id(self) -> str:
        return _text(self.row_id) or self.prediction_id

    @property
    def effective_statistical_id(self) -> str:
        """不依賴 row alias 的 immutable statistical trial identity。"""

        if self.statistical_id:
            return self.statistical_id
        return canonical_payload_hash(
            {
                "scope_id": self.scope_id,
                "symbol": self.symbol,
                "decision_date": self.decision_date,
                "decision_at": self.decision_at,
                "horizon_days": self.horizon_days,
                "cost_scenario_hash": self.cost_scenario_hash,
                "outcome_tier": self.outcome_tier,
                "source_id": self.source_id,
                "model_id": self.model_id,
                "dataset_id": self.dataset_id,
                "dataset_hash": self.dataset_hash,
                "prediction_receipt_schema_version": self.prediction_receipt_schema_version,
                "prediction_receipt_hash": self.prediction_receipt_hash,
                "universe_policy_hash": self.universe_policy_hash,
                "label_contract_id": self.label_contract_id,
                "return_basis": self.return_basis,
            }
        )

    @property
    def statistical_identity(self) -> str:
        """向後相容的 statistical identity 名稱。"""

        return self.effective_statistical_id

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
            "label_available_at": self.label_available_at,
            "outcome_recorded_at": self.outcome_recorded_at,
            "outcome_tier": self.outcome_tier,
            "action_state": self.action_state,
            "decision_at": self.decision_at,
            "available_at": self.available_at,
            "receipt_created_at": self.receipt_created_at,
            "captured_at": self.captured_at,
            "prediction_decision_at": self.prediction_decision_at,
            "delivery_at": self.delivery_at,
            "human_decision_at": self.human_decision_at,
            "decision_day_block": self.decision_day_block or self.decision_date,
            "row_id": self.effective_row_id,
            "personal_observation_count": self.personal_observation_count,
            "personal_positive_count": self.personal_positive_count,
            "outcome_status": self.outcome_status,
            "delivery_status": self.delivery_status,
            "late_delivery": self.late_delivery,
            "source_result_id": self.source_result_id,
            "prediction_receipt_hash": self.prediction_receipt_hash,
            "model_id": self.model_id,
            "dataset_id": self.dataset_id,
            "dataset_hash": self.dataset_hash,
            "cost_scenario_id": self.cost_scenario_id,
            "cost_scenario_version": self.cost_scenario_version,
            "universe_policy_hash": self.universe_policy_hash,
            "label_contract_id": self.label_contract_id,
            "return_basis": self.return_basis,
            "source_id": self.source_id,
            "prediction_receipt_schema_version": self.prediction_receipt_schema_version,
            "statistical_id": self.effective_statistical_id,
            "outcome_id": self.outcome_id,
            "event_id": self.event_id,
            "window_days": self.window_days,
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
    delivery_capture: PersonalizationDeliveryCapture | None = None
    prediction_decision_at: str | None = None
    delivery_at: str | None = None
    human_decision_at: str | None = None
    formal_order_allowed: bool = False
    auto_action_allowed: bool = False

    def __post_init__(self) -> None:
        if not _text(self.result_id) or not _text(self.stock_code):
            raise ValueError("result_id and stock_code are required")
        _iso_date(self.decision_date, "decision_date")
        if self.status == "linked_prediction" and not _text(self.prediction_id):
            raise ValueError("linked prediction evidence requires prediction_id")
        if self.formal_order_allowed or self.auto_action_allowed:
            raise ValueError("personalization evidence cannot authorize actions")
        if self.action not in PERSONALIZATION_ACTIONS:
            raise ValueError(f"unsupported personalization action: {self.action}")
        if self.action_state not in PERSONALIZATION_ACTION_STATES:
            raise ValueError(f"unsupported personalization action_state: {self.action_state}")
        normalized_outcomes: list[dict[str, Any]] = []
        for item in self.outcomes:
            if not isinstance(item, Mapping):
                raise ValueError("personalization outcomes must be objects")
            normalized_outcomes.append(dict(item))
        if self.delivery_capture is not None:
            if self.delivery_capture.result_id != self.result_id:
                raise ValueError("delivery capture result identity mismatch")
            if self.delivery_capture.stock_code != self.stock_code:
                raise ValueError("delivery capture stock identity mismatch")
            if self.delivery_capture.prediction_id != self.prediction_id:
                raise ValueError("delivery capture prediction identity mismatch")
        object.__setattr__(self, "source_trace", tuple(str(item) for item in self.source_trace))
        object.__setattr__(self, "warnings", tuple(str(item) for item in self.warnings))
        object.__setattr__(self, "outcomes", tuple(normalized_outcomes))

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
            "delivery_capture": (
                self.delivery_capture.to_dict()
                if self.delivery_capture is not None
                else None
            ),
            "prediction_decision_at": self.prediction_decision_at,
            "delivery_at": self.delivery_at,
            "human_decision_at": self.human_decision_at,
            "formal_order_allowed": False,
            "auto_action_allowed": False,
        }


__all__ = [
    "PERSONALIZATION_ACTIONS",
    "PERSONALIZATION_ACTION_STATES",
    "PERSONALIZATION_COHORT_CONTRACT_SCHEMA_VERSION",
    "PERSONALIZATION_DELIVERY_CAPTURE_SCHEMA_VERSION",
    "PERSONALIZATION_DELIVERY_ACK_SCHEMA_VERSION",
    "PERSONALIZATION_DELIVERY_STATUSES",
    "PERSONALIZATION_OUTCOME_TIERS",
    "PERSONALIZATION_OUTCOME_STATUSES",
    "PERSONALIZATION_PREDICTION_RECEIPT_SCHEMA_VERSION",
    "PERSONALIZATION_TEMPORAL_CONTRACT",
    "PERSONALIZATION_TEMPORAL_MODES",
    "PERSONAL_RECOMMENDATION_CHOICE_SCHEMA_VERSION",
    "PERSONAL_RECOMMENDATION_MODEL_EVIDENCE_SCHEMA_VERSION",
    "PERSONAL_USE_POLICY_SNAPSHOT_EVENT_SCHEMA_VERSION",
    "PERSONAL_USE_POLICY_SNAPSHOT_EVENT_TYPE",
    "PersonalizationActionEnvelope",
    "PersonalizationDecisionEvidence",
    "PersonalizationDeliveryCapture",
    "PersonalizationDeliveryScope",
    "PersonalizationEvaluationRow",
    "PersonalRecommendationChoice",
    "PersonalRecommendationModelEvidence",
    "PersonalRecommendationOverrideReason",
    "canonical_aware_datetime",
    "canonical_payload_hash",
    "inspect_personalization_temporal_context",
    "parse_aware_datetime",
    "read_personal_use_policy_snapshot_event",
    "validate_forward_outcome_chronology",
]
