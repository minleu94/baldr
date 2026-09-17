"""V6 personalization 的 scope-specific read projection 與 delivery adapter。

本模組只接受 caller 提供的 read-only reader／mapping，不建立任何 repository、
資料表、ledger、active pointer 或寫入副作用。所有跨領域 join 都必須使用
exact ``(result_id, stock_code)``；``source_id``、profile、holding、股票名稱
與 row index 不會被提升成推薦結果身份。

既有 ``recommendation-calibration-projection-receipt.v1`` 保持不變。這裡的
delivery capture 只以 receipt hash/reference 串接舊 receipt，並以獨立 hash
驗證 personal scope、prediction 與交付狀態。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime
import json
from pathlib import Path
import re
from typing import Any, Callable, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from app_module.personalization_contract import (
    PERSONALIZATION_ACTIONS,
    PERSONALIZATION_ACTION_STATES,
    PERSONALIZATION_OUTCOME_STATUSES,
    PERSONALIZATION_DELIVERY_ACK_SCHEMA_VERSION,
    PERSONALIZATION_PREDICTION_RECEIPT_SCHEMA_VERSION,
    PersonalizationDecisionEvidence,
    PersonalizationDeliveryCapture,
    PersonalizationDeliveryScope,
    canonical_aware_datetime,
    canonical_payload_hash,
    inspect_personalization_temporal_context,
    parse_aware_datetime,
    validate_forward_outcome_chronology,
)


PERSONALIZATION_PROJECTION_SCHEMA_VERSION = "personalization-projection.v1"
_MARKET_TIMEZONE = ZoneInfo("Asia/Taipei")
PERSONALIZATION_PROJECTION_STATUSES = frozenset(
    {
        "linked_prediction",
        "population_only",
        "not_delivered",
        "unavailable",
        "duplicate_exact",
        "duplicate_conflict",
    }
)


class PersonalizationProjectionError(ValueError):
    """Raised when a read-side personalisation identity cannot be verified."""


Reader = Callable[..., Any] | Mapping[Any, Any] | None


def _text(value: object) -> str:
    return str(value or "").strip()


def _mapping(value: Any, field_name: str = "mapping") -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        result = to_dict()
        if isinstance(result, Mapping):
            return {str(key): item for key, item in result.items()}
    if is_dataclass(value) and not isinstance(value, type):
        result = asdict(value)
        if isinstance(result, Mapping):
            return {str(key): item for key, item in result.items()}
    raise PersonalizationProjectionError(f"{field_name} must be an object")


def _optional_mapping(value: Any, field_name: str = "mapping") -> dict[str, Any] | None:
    if value is None:
        return None
    return _mapping(value, field_name)


def _reader_value(reader: Reader, *keys: object) -> Any:
    """Read one exact key from a mapping or invoke a documented reader.

    Callable readers receive positional exact keys. Mapping readers may use the
    one-key form or a tuple key. No scan or fuzzy fallback is performed.
    """

    if reader is None:
        return None
    if callable(reader):
        return reader(*keys)
    if len(keys) == 1:
        return reader.get(keys[0])
    return reader.get(tuple(keys))


def _reader_rows(reader: Reader, result_id: str, stock_code: str) -> tuple[Any, ...]:
    value = _reader_value(reader, result_id, stock_code)
    if value is None:
        return ()
    if isinstance(value, Mapping) or hasattr(value, "to_dict"):
        return (value,)
    if isinstance(value, (str, bytes)):
        raise PersonalizationProjectionError("read-only reader returned non-row text")
    try:
        return tuple(value)
    except TypeError as exc:
        raise PersonalizationProjectionError("read-only reader returned invalid rows") from exc


def _iter_alias_sources(row: Mapping[str, Any]) -> tuple[tuple[str, Mapping[str, Any]], ...]:
    """Return bounded nested containers that may repeat one semantic field.

    Continuity revisions and evidence adapters legitimately expose the same
    identity in more than one layer (root, ``decision_identity``, ``payload``
    or a typed personalization envelope).  Those layers are useful only when
    they agree exactly.  This helper deliberately walks a small allow-list;
    arbitrary ``source_id``/metadata values never become candidate identity.
    """

    queue: list[tuple[str, Mapping[str, Any]]] = [("row", row)]
    sources: list[tuple[str, Mapping[str, Any]]] = []
    seen: set[int] = set()
    nested_keys = (
        "decision_identity",
        "payload",
        "metadata",
        "personalization_action",
        "personalization_envelope",
    )
    while queue:
        source_name, current = queue.pop(0)
        marker = id(current)
        if marker in seen:
            continue
        seen.add(marker)
        sources.append((source_name, current))
        for key in nested_keys:
            nested = current.get(key)
            if isinstance(nested, Mapping):
                queue.append((f"{source_name}.{key}", nested))
    return tuple(sources)


def _alias_values(
    row: Mapping[str, Any],
    aliases: Sequence[str],
) -> tuple[tuple[str, str], ...]:
    """Collect all non-empty values for one semantic alias family."""

    values: list[tuple[str, str]] = []
    for source_name, source in _iter_alias_sources(row):
        for alias in aliases:
            if alias not in source or source.get(alias) in (None, ""):
                continue
            value = _text(source.get(alias))
            if value:
                values.append((f"{source_name}.{alias}", value))
    return tuple(values)


def _verified_alias_text(
    row: Mapping[str, Any],
    field_name: str,
    aliases: Sequence[str],
    *,
    required: bool = False,
) -> str:
    """Resolve one semantic field and fail closed on alias disagreement."""

    values = _alias_values(row, aliases)
    distinct = tuple(dict.fromkeys(value for _, value in values))
    if len(distinct) > 1:
        detail = ", ".join(f"{source}={value}" for source, value in values)
        raise PersonalizationProjectionError(
            f"{field_name} has conflicting aliases: {detail}"
        )
    if not distinct:
        if required:
            raise PersonalizationProjectionError(f"{field_name} is missing")
        return ""
    return distinct[0]


def _verified_alias_horizon(
    row: Mapping[str, Any],
    field_name: str,
) -> int | None:
    """Resolve ``horizon_days``/``horizon`` aliases by parsed day count."""

    values = _alias_values(row, ("horizon_days", "horizon"))
    parsed: list[tuple[str, int]] = []
    for source, value in values:
        try:
            horizon = _horizon_days(value, field_name)
        except PersonalizationProjectionError as exc:
            raise PersonalizationProjectionError(
                f"{field_name} alias is invalid: {source}"
            ) from exc
        if horizon is None:
            raise PersonalizationProjectionError(
                f"{field_name} alias is invalid: {source}"
            )
        parsed.append((source, horizon))
    distinct = tuple(dict.fromkeys(value for _, value in parsed))
    if len(distinct) > 1:
        detail = ", ".join(f"{source}={value}" for source, value in parsed)
        raise PersonalizationProjectionError(
            f"{field_name} has conflicting aliases: {detail}"
        )
    return distinct[0] if distinct else None


def _verify_nested_contract_aliases(
    parent: Mapping[str, Any],
    child: Mapping[str, Any],
) -> None:
    """Verify event-level fields before an evidence outcome is flattened.

    Evidence adapters commonly expose event identity on the parent and
    outcome identity on the child.  ``dict.update`` is safe only after every
    shared semantic field has been compared; otherwise a conflicting parent
    can be silently overwritten by a valid child.
    """

    fields: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("result_id", ("result_id", "source_result_id")),
        ("stock_code", ("stock_code", "symbol", "證券代號")),
        (
            "personalization_scope_id",
            ("personalization_scope_id", "scope_id"),
        ),
        ("prediction_id", ("prediction_id",)),
        (
            "prediction_receipt_hash",
            ("prediction_receipt_hash", "projection_receipt_hash"),
        ),
        ("cost_scenario_hash", ("cost_scenario_hash",)),
        ("label_contract_id", ("label_contract_id",)),
        ("return_basis", ("return_basis",)),
        ("event_id", ("event_id",)),
    )
    for field_name, aliases in fields:
        parent_value = _verified_alias_text(parent, field_name, aliases)
        child_value = _verified_alias_text(child, field_name, aliases)
        if parent_value and child_value and parent_value != child_value:
            raise PersonalizationProjectionError(
                f"evidence parent/child {field_name} conflict"
            )

    parent_horizon = _verified_alias_horizon(parent, "evidence.horizon")
    child_horizon = _verified_alias_horizon(child, "evidence.horizon")
    parent_window = _verified_alias_text(parent, "evidence.window_days", ("window_days",))
    child_window = _verified_alias_text(child, "evidence.window_days", ("window_days",))
    # ``horizon_days`` on an event can describe the prediction while
    # ``window_days`` on a nested child identifies one of several parallel
    # forward outcomes.  Compare like-for-like aliases only; do not turn two
    # legitimate outcome windows into a parent/child conflict.
    horizon_values: list[tuple[str, int]] = []
    for label, value in (
        ("parent.horizon", parent_horizon),
        ("child.horizon", child_horizon),
    ):
        if value is not None:
            horizon_values.append((label, value))
    distinct_horizons = tuple(dict.fromkeys(value for _, value in horizon_values))
    if len(distinct_horizons) > 1:
        detail = ", ".join(f"{label}={value}" for label, value in horizon_values)
        raise PersonalizationProjectionError(
            f"evidence parent/child horizon conflict: {detail}"
        )

    window_values: list[tuple[str, int]] = []
    for label, window_value in (
        ("parent.window_days", parent_window),
        ("child.window_days", child_window),
    ):
        if window_value:
            try:
                parsed = int(window_value)
            except ValueError as exc:
                raise PersonalizationProjectionError(
                    f"{label} is invalid"
                ) from exc
            if parsed <= 0:
                raise PersonalizationProjectionError(f"{label} is invalid")
            window_values.append((label, parsed))
    distinct_windows = tuple(dict.fromkeys(value for _, value in window_values))
    if len(distinct_windows) > 1:
        detail = ", ".join(f"{label}={value}" for label, value in window_values)
        raise PersonalizationProjectionError(
            f"evidence parent/child window_days conflict: {detail}"
        )


def _merge_evidence_parent_child(
    parent: Mapping[str, Any],
    child: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate then flatten one evidence child without dropping metadata."""

    _verify_nested_contract_aliases(parent, child)
    merged = dict(parent)
    merged.update(dict(child))
    parent_metadata = parent.get("metadata")
    child_metadata = child.get("metadata")
    if isinstance(parent_metadata, Mapping) and isinstance(child_metadata, Mapping):
        # The pre-flatten verifier has already rejected contradictory shared
        # aliases.  Preserve parent-only and child-only fields for the
        # downstream exact outcome/evaluation contract.
        merged["metadata"] = {**dict(parent_metadata), **dict(child_metadata)}
    return merged


def _stock_code(value: Mapping[str, Any]) -> str:
    return _verified_alias_text(
        value,
        "stock_code",
        ("stock_code", "symbol", "證券代號"),
    )


def _result_id(value: Mapping[str, Any]) -> str:
    return _text(value.get("result_id"))


def _date_text(value: object, field_name: str) -> str:
    text = _text(value)[:10]
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise PersonalizationProjectionError(f"{field_name} must be ISO date") from exc


def _datetime_optional(value: object, field_name: str) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return parse_aware_datetime(value, field_name)
    except ValueError as exc:
        raise PersonalizationProjectionError(str(exc)) from exc


def _horizon_days(value: object, field_name: str = "horizon") -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise PersonalizationProjectionError(f"{field_name} must be a positive integer")
    if isinstance(value, int):
        return value if value > 0 else None
    text = _text(value)
    match = re.fullmatch(r"(\d+)(?:\s+trading\s+days?)?", text, flags=re.IGNORECASE)
    if match is None:
        raise PersonalizationProjectionError(f"{field_name} is not an exact horizon")
    parsed = int(match.group(1))
    return parsed if parsed > 0 else None


def _probability_bp(value: object, field_name: str = "probability") -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise PersonalizationProjectionError(f"{field_name} must be integer bp")
    try:
        parsed = int(str(value))
    except (TypeError, ValueError) as exc:
        raise PersonalizationProjectionError(f"{field_name} must be integer bp") from exc
    if not 0 <= parsed <= 10_000:
        raise PersonalizationProjectionError(f"{field_name} must be integer bp within 0..10000")
    return parsed


def _json_equal(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    try:
        return json.dumps(
            left,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ) == json.dumps(
            right,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    except (TypeError, ValueError):
        return dict(left) == dict(right)


def _identity_from_row(row: Mapping[str, Any]) -> tuple[str, str]:
    resolved_result = _verified_alias_text(
        row,
        "result_id",
        ("result_id", "source_result_id"),
    )
    # ``source_id`` is intentionally absent: it is a provider/source
    # identity, not an alias for the persisted recommendation result.
    resolved_stock = _verified_alias_text(
        row,
        "stock_code",
        ("stock_code", "symbol", "證券代號"),
    )
    return resolved_result, resolved_stock


def _exact_rows(
    rows: Iterable[Any],
    *,
    result_id: str,
    stock_code: str,
) -> tuple[tuple[dict[str, Any], ...], int, int]:
    """Return exact rows and duplicate diagnostics without fuzzy joining."""

    normalized: list[dict[str, Any]] = []
    for raw in rows:
        row = _mapping(raw, "reader row")
        row_result, row_stock = _identity_from_row(row)
        if row_result != result_id or row_stock != stock_code:
            continue
        normalized.append(row)
    if len(normalized) < 2:
        return tuple(normalized), 0, 0
    first = normalized[0]
    if all(_json_equal(first, row) for row in normalized[1:]):
        return (first,), len(normalized) - 1, 0
    return (), 0, len(normalized)


def _capture_from_any(value: Any) -> PersonalizationDeliveryCapture | None:
    if value is None:
        return None
    if isinstance(value, PersonalizationDeliveryCapture):
        return value
    return PersonalizationDeliveryCapture.from_mapping(_mapping(value, "delivery_capture"))


def _scope_from_any(value: Any) -> PersonalizationDeliveryScope | None:
    if value is None:
        return None
    if isinstance(value, PersonalizationDeliveryScope):
        return value
    return PersonalizationDeliveryScope.from_mapping(_mapping(value, "personalization_scope"))


def _capture_candidates(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, Mapping):
        return (value,)
    if isinstance(value, (str, bytes)):
        return ()
    try:
        return tuple(value)
    except TypeError:
        return (value,)


def _first_text(*values: object) -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return ""


def _receipt_mapping(value: Any) -> dict[str, Any]:
    receipt = _mapping(value, "projection_receipt")
    if "payload" in receipt and isinstance(receipt.get("payload"), Mapping):
        body = dict(receipt["payload"])
        if receipt.get("receipt_hash"):
            body["receipt_hash"] = receipt["receipt_hash"]
        receipt = body
    return receipt


def _verify_receipt_mapping(
    receipt: Mapping[str, Any],
    *,
    expected_hash: str,
    result_id: str,
    stock_code: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = dict(receipt)
    supplied_hash = _text(payload.pop("receipt_hash"))
    if not supplied_hash or supplied_hash != expected_hash:
        raise PersonalizationProjectionError("projection receipt hash mismatch")
    if canonical_payload_hash(payload) != supplied_hash:
        raise PersonalizationProjectionError("projection receipt body hash mismatch")
    if payload.get("schema_version") != PERSONALIZATION_PREDICTION_RECEIPT_SCHEMA_VERSION:
        raise PersonalizationProjectionError("projection receipt schema is unsupported")
    declared_result = _text(payload.get("result_id"))
    if not declared_result or declared_result != result_id:
        raise PersonalizationProjectionError("projection receipt result identity mismatch")
    if _date_text(payload.get("decision_date"), "projection receipt decision_date") is None:
        raise PersonalizationProjectionError("projection receipt decision date is missing")
    if payload.get("formal_order_allowed") is True or payload.get("production_action_allowed") is True:
        raise PersonalizationProjectionError("projection receipt action flag is unsafe")
    if payload.get("shadow_only") is not True:
        raise PersonalizationProjectionError("projection receipt is not shadow-only")
    selection = payload.get("selection_contract")
    expected_selection = {
        "authority": "rule_top_n",
        "score_kind": "rule_total_score",
        "percentile_kind": "rule_percentile",
        "model_ranking_kind": "model_return_bp",
        "top_n_changed_by_model": False,
    }
    if not isinstance(selection, Mapping) or any(
        selection.get(key) != value for key, value in expected_selection.items()
    ):
        raise PersonalizationProjectionError("projection receipt selection contract is invalid")
    raw_rows = payload.get("projections")
    if not isinstance(raw_rows, list):
        raise PersonalizationProjectionError("projection receipt projections are missing")
    rows = [
        _mapping(item, "projection receipt row")
        for item in raw_rows
        if isinstance(item, Mapping)
    ]
    declared_rows_hash = _text(payload.get("projection_rows_sha256"))
    if declared_rows_hash and declared_rows_hash != canonical_payload_hash(raw_rows):
        raise PersonalizationProjectionError("projection receipt rows hash mismatch")
    matching = [row for row in rows if _stock_code(row) == stock_code]
    if not matching:
        raise PersonalizationProjectionError("projection receipt stock identity mismatch")
    if len(matching) > 1:
        if all(_json_equal(matching[0], row) for row in matching[1:]):
            raise PersonalizationProjectionError("projection receipt duplicate exact row")
        raise PersonalizationProjectionError("projection receipt duplicate conflict row")
    return payload, matching[0]


def _consistent_text(
    values: Sequence[object],
    field_name: str,
    *,
    required: bool = True,
) -> str:
    normalized = tuple(_text(value) for value in values if _text(value))
    distinct = tuple(dict.fromkeys(normalized))
    if len(distinct) > 1:
        raise PersonalizationProjectionError(f"{field_name} has conflicting verified values")
    if not distinct:
        if required:
            raise PersonalizationProjectionError(f"{field_name} is missing from verified receipt")
        return ""
    return distinct[0]


def _outcome_timestamp(row: Mapping[str, Any]) -> datetime | None:
    for key in (
        "label_available_at",
        "outcome_available_at",
        "available_at",
        "outcome_recorded_at",
        "recorded_at",
        "calculated_at",
    ):
        if row.get(key) not in (None, ""):
            return _datetime_optional(row.get(key), f"outcome.{key}")
    return None


def _verified_horizon_from_prediction(prediction: Mapping[str, Any]) -> int:
    value = prediction.get("horizon_days") or prediction.get("horizon")
    parsed = _horizon_days(value, "verified horizon")
    if parsed is None:
        raise PersonalizationProjectionError("verified horizon is missing")
    return parsed


def _verified_cost_from_prediction(prediction: Mapping[str, Any]) -> str:
    value = _text(prediction.get("cost_scenario_hash"))
    if not value:
        raise PersonalizationProjectionError("verified cost scenario is missing")
    return value


def _canonical_action(raw: Mapping[str, Any]) -> tuple[str, str, str, str]:
    try:
        action = _verified_alias_text(raw, "action", ("action",)) or "not_recorded"
        action_state = _verified_alias_text(
            raw,
            "action_state",
            ("action_state",),
        ) or "recorded"
    except PersonalizationProjectionError as exc:
        return "not_recorded", "conflict", _text(raw.get("revision_id")), str(exc)
    if action not in PERSONALIZATION_ACTIONS:
        return "not_recorded", "conflict", "", "unsupported_action"
    if action_state not in PERSONALIZATION_ACTION_STATES:
        return action, "conflict", _text(raw.get("revision_id")), "unsupported_action_state"
    return action, action_state, _text(raw.get("revision_id")), ""


def _outcome_status(raw: Mapping[str, Any]) -> str:
    status = _text(raw.get("outcome_status") or raw.get("status"))
    mapping = {
        "pending": "pending_maturity",
        "insufficient_future_data": "pending_maturity",
        "missing_price": "matured_missing",
        "ready": "ready",
        "pending_maturity": "pending_maturity",
        "matured_missing": "matured_missing",
        "invalid": "invalid",
        "not_applicable": "not_applicable",
        "conflict": "conflict",
        "duplicate_exact": "duplicate_exact",
        "duplicate_conflict": "duplicate_conflict",
    }
    return mapping.get(status, "invalid")


def _aggregate_outcome_status(outcomes: Sequence[Mapping[str, Any]]) -> str:
    if not outcomes:
        return "not_applicable"
    statuses = {_outcome_status(item) for item in outcomes}
    if "conflict" in statuses or "duplicate_conflict" in statuses:
        return "conflict"
    for status in ("invalid", "matured_missing", "pending_maturity", "duplicate_exact", "not_applicable"):
        if status in statuses:
            return status
    if "ready" in statuses:
        return "ready"
    return "invalid"


@dataclass(frozen=True)
class PersonalizationProjectionResult:
    """一個 exact candidate 的唯讀 projection 結果。"""

    status: str
    result_id: str
    stock_code: str
    decision_date: str | None = None
    scope: PersonalizationDeliveryScope | None = None
    evidence: PersonalizationDecisionEvidence | None = None
    prediction: Mapping[str, Any] = field(default_factory=dict)
    action: str = "not_recorded"
    action_state: str = "not_recorded"
    action_revision_id: str = ""
    historical_action_state: str = "not_recorded"
    current_action_state: str = "not_recorded"
    outcome_status: str = "not_applicable"
    outcomes: tuple[Mapping[str, Any], ...] = ()
    delivery_status: str = "not_recorded"
    late_delivery: bool = False
    # ``prediction_decision_at`` is the immutable producer inference clock;
    # ``delivery_at`` is the explicit ACK clock; ``human_decision_at`` is the
    # Journal action/evaluation anchor when a human action exists.  They are
    # intentionally not collapsed into the source cutoff date.
    prediction_decision_at: str | None = None
    delivery_at: str | None = None
    human_decision_at: str | None = None
    duplicate_exact_count: int = 0
    duplicate_conflict_count: int = 0
    warnings: tuple[str, ...] = ()
    source_trace: tuple[str, ...] = ()
    formal_order_allowed: bool = False
    auto_action_allowed: bool = False
    read_only: bool = True
    schema_version: str = PERSONALIZATION_PROJECTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.status not in PERSONALIZATION_PROJECTION_STATUSES:
            raise ValueError(f"unsupported personalization projection status: {self.status}")
        if not _text(self.result_id) or not _text(self.stock_code):
            raise ValueError("result_id and stock_code are required")
        if self.formal_order_allowed or self.auto_action_allowed or not self.read_only:
            raise ValueError("personalization projection must remain read-only")
        if self.action not in PERSONALIZATION_ACTIONS:
            raise ValueError(f"unsupported personalization action: {self.action}")
        if self.action_state not in PERSONALIZATION_ACTION_STATES:
            raise ValueError(f"unsupported personalization action_state: {self.action_state}")
        if self.outcome_status not in PERSONALIZATION_OUTCOME_STATUSES and self.outcome_status != "not_recorded":
            raise ValueError(f"unsupported personalization outcome status: {self.outcome_status}")
        if self.decision_date is not None:
            _date_text(self.decision_date, "decision_date")
        if self.duplicate_exact_count < 0 or self.duplicate_conflict_count < 0:
            raise ValueError("duplicate counts must be non-negative")
        object.__setattr__(self, "prediction", dict(self.prediction))
        object.__setattr__(self, "outcomes", tuple(dict(item) for item in self.outcomes))
        object.__setattr__(self, "warnings", tuple(str(item) for item in self.warnings))
        object.__setattr__(self, "source_trace", tuple(str(item) for item in self.source_trace))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "result_id": self.result_id,
            "stock_code": self.stock_code,
            "decision_date": self.decision_date,
            "scope": self.scope.to_dict() if self.scope is not None else None,
            "evidence": self.evidence.to_dict() if self.evidence is not None else None,
            "prediction": dict(self.prediction),
            "action": self.action,
            "action_state": self.action_state,
            "action_revision_id": self.action_revision_id,
            "historical_action_state": self.historical_action_state,
            "current_action_state": self.current_action_state,
            "outcome_status": self.outcome_status,
            "outcomes": [dict(item) for item in self.outcomes],
            "delivery_status": self.delivery_status,
            "late_delivery": self.late_delivery,
            "prediction_decision_at": self.prediction_decision_at,
            "delivery_at": self.delivery_at,
            "human_decision_at": self.human_decision_at,
            "duplicate_exact_count": self.duplicate_exact_count,
            "duplicate_conflict_count": self.duplicate_conflict_count,
            "warnings": list(self.warnings),
            "source_trace": list(self.source_trace),
            "formal_order_allowed": False,
            "auto_action_allowed": False,
            "read_only": True,
        }


class PersonalizationDeliveryCaptureService:
    """建立／驗證 immutable capture；不自行寫入任何 persistence。"""

    def capture(
        self,
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
    ) -> PersonalizationDeliveryCapture:
        """建立 generated capture；caller 必須明確管理後續保存／交付確認。"""

        if scope.scope_status != "bound":
            raise PersonalizationProjectionError("delivery capture requires a bound scope")
        if scope.captured_at is None or scope.temporal_status != "verified":
            raise PersonalizationProjectionError(
                "delivery capture requires a verified captured_at clock"
            )
        return PersonalizationDeliveryCapture.create(
            scope=scope,
            request_id=request_id,
            result_id=result_id,
            stock_code=stock_code,
            projection_receipt_hash=projection_receipt_hash,
            generated_at=generated_at,
            prediction_id=prediction_id,
            projection_receipt_path=projection_receipt_path,
            model_id=model_id,
            dataset_id=dataset_id,
            dataset_hash=dataset_hash,
            cost_scenario_hash=cost_scenario_hash,
            horizon_days=horizon_days,
        )

    @staticmethod
    def mark_persisted(
        capture: PersonalizationDeliveryCapture,
        *,
        persisted_at: str,
    ) -> PersonalizationDeliveryCapture:
        return capture.mark_persisted(persisted_at)

    @staticmethod
    def mark_delivered(
        capture: PersonalizationDeliveryCapture,
        *,
        delivered_at: str,
    ) -> PersonalizationDeliveryCapture:
        return capture.mark_delivered(delivered_at)

    @staticmethod
    def retry_is_same_identity(
        original: PersonalizationDeliveryCapture,
        retry: PersonalizationDeliveryCapture,
    ) -> bool:
        """同一 retry 只可重送同一 prediction，不可製造新 calibration row。"""

        return (
            original.delivery_id == retry.delivery_id
            and original.request_id == retry.request_id
            and original.result_id == retry.result_id
            and original.stock_code == retry.stock_code
            and original.prediction_id == retry.prediction_id
            and original.projection_receipt_hash == retry.projection_receipt_hash
            and original.scope.envelope_hash == retry.scope.envelope_hash
        )

    @staticmethod
    def verify_saved_capture(
        saved_result: Any,
        capture: PersonalizationDeliveryCapture,
    ) -> None:
        """驗證既有 result readback 內的 exact capture，不建立新寫入路徑。"""

        result = _mapping(saved_result, "saved recommendation result")
        if _result_id(result) != capture.result_id:
            raise PersonalizationProjectionError("saved result identity mismatch")
        context = result.get("run_context")
        context_map = context if isinstance(context, Mapping) else {}
        raw_values = context_map.get("personalization_delivery_captures")
        found: list[PersonalizationDeliveryCapture] = []
        for raw in _capture_candidates(raw_values):
            try:
                parsed = _capture_from_any(raw)
            except (TypeError, ValueError) as exc:
                raise PersonalizationProjectionError("saved delivery capture is invalid") from exc
            if parsed is not None and parsed.result_id == capture.result_id and parsed.stock_code == capture.stock_code:
                found.append(parsed)
        if len(found) != 1:
            raise PersonalizationProjectionError("saved delivery capture exact row is missing")
        if found[0].capture_hash != capture.capture_hash:
            raise PersonalizationProjectionError("saved delivery capture hash mismatch")


class PersonalizationProjectionService:
    """Read-only scope-specific projection over existing result/evidence stores."""

    def __init__(
        self,
        *,
        recommendation_reader: Reader = None,
        projection_receipt_reader: Reader = None,
        action_reader: Reader = None,
        outcome_reader: Reader = None,
        evidence_reader: Reader = None,
        delivery_reader: Reader = None,
        capture_service: PersonalizationDeliveryCaptureService | None = None,
    ) -> None:
        self.recommendation_reader = recommendation_reader
        self.projection_receipt_reader = projection_receipt_reader
        self.action_reader = action_reader
        self.outcome_reader = outcome_reader
        self.evidence_reader = evidence_reader
        self.delivery_reader = delivery_reader
        self.capture_service = capture_service or PersonalizationDeliveryCaptureService()

    def build_for_candidate(
        self,
        *,
        result_id: str,
        stock_code: str,
        personalization_scope_id: str | None = None,
        evaluated_as_of: str | None = None,
        evaluation_cutoff_at: str | None = None,
        result: Any = None,
        delivery_capture: Any = None,
        projection_receipt: Any = None,
    ) -> PersonalizationProjectionResult:
        """Build one exact candidate projection with fail-closed identity checks."""

        resolved_result_id = _text(result_id)
        resolved_stock_code = _text(stock_code)
        if not resolved_result_id or not resolved_stock_code:
            raise PersonalizationProjectionError("result_id and stock_code are required")
        evaluated_date = (
            _date_text(evaluated_as_of, "evaluated_as_of")
            if evaluated_as_of is not None
            else None
        )
        cutoff = _datetime_optional(evaluation_cutoff_at, "evaluation_cutoff_at")
        if cutoff is not None and evaluated_date is not None:
            if cutoff.astimezone(_MARKET_TIMEZONE).date() > date.fromisoformat(evaluated_date):
                return self._empty(
                    resolved_result_id,
                    resolved_stock_code,
                    status="unavailable",
                    warnings=("evaluation_cutoff_after_evaluated_as_of",),
                    source_trace=("evaluation_clock",),
                )
        raw_result = result if result is not None else _reader_value(self.recommendation_reader, resolved_result_id)
        if raw_result is None:
            return self._empty(
                resolved_result_id,
                resolved_stock_code,
                status="unavailable",
                warnings=("recommendation_result_not_found",),
                source_trace=("recommendation_result_reader",),
            )
        try:
            result_map = _mapping(raw_result, "recommendation result")
        except PersonalizationProjectionError as exc:
            return self._empty(
                resolved_result_id,
                resolved_stock_code,
                status="unavailable",
                warnings=("recommendation_result_invalid", str(exc)),
                source_trace=("recommendation_result_reader",),
            )
        stored_result_id = _result_id(result_map)
        if stored_result_id != resolved_result_id:
            return self._empty(
                resolved_result_id,
                resolved_stock_code,
                status="unavailable",
                warnings=("recommendation_result_identity_mismatch",),
                source_trace=("recommendation_result_reader",),
            )

        candidate_rows = self._candidate_rows(result_map, resolved_stock_code)
        if not candidate_rows:
            return self._empty(
                resolved_result_id,
                resolved_stock_code,
                status="unavailable",
                warnings=("exact_candidate_not_found",),
                source_trace=("recommendation_result_reader",),
            )
        if len(candidate_rows) > 1:
            if all(_json_equal(candidate_rows[0], item) for item in candidate_rows[1:]):
                return self._empty(
                    resolved_result_id,
                    resolved_stock_code,
                    status="duplicate_exact",
                    warnings=("exact_candidate_duplicate_exact",),
                    duplicate_exact_count=len(candidate_rows) - 1,
                    source_trace=("recommendation_result_reader",),
                )
            return self._empty(
                resolved_result_id,
                resolved_stock_code,
                status="duplicate_conflict",
                warnings=("exact_candidate_duplicate_conflict",),
                duplicate_conflict_count=len(candidate_rows),
                source_trace=("recommendation_result_reader",),
            )
        candidate = candidate_rows[0]
        run_context = result_map.get("run_context")
        context_map = run_context if isinstance(run_context, Mapping) else {}
        # ``as_of_date`` is the source/data cutoff.  Once an exact personal
        # scope is present, the projection decision date is the actual
        # producer decision market date from ``scope.decision_at``.  The two
        # dates may legitimately differ by a market-session boundary.
        source_cutoff_date = self._decision_date(result_map, candidate, context_map)

        capture, scope, capture_warning = self._resolve_capture_and_scope(
            result_map,
            candidate,
            context_map,
            result_id=resolved_result_id,
            stock_code=resolved_stock_code,
            requested_scope_id=personalization_scope_id,
            explicit_capture=delivery_capture,
        )
        decision_date = scope.decision_date if scope is not None else source_cutoff_date
        if decision_date is None:
            return self._empty(
                resolved_result_id,
                resolved_stock_code,
                status="unavailable",
                warnings=("decision_date_missing",),
                source_trace=("recommendation_result_reader",),
            )
        if capture_warning:
            return self._empty(
                resolved_result_id,
                resolved_stock_code,
                status="unavailable",
                decision_date=decision_date,
                scope=scope,
                delivery_status=(capture.status if capture is not None else "not_recorded"),
                warnings=(capture_warning,),
                source_trace=("recommendation_result_reader", "personalization_delivery_capture"),
            )
        capture, delivery_warning = self._resolve_delivery_ack(
            capture,
            result_id=resolved_result_id,
            stock_code=resolved_stock_code,
        )
        if delivery_warning:
            return self._empty(
                resolved_result_id,
                resolved_stock_code,
                status="unavailable",
                decision_date=decision_date,
                scope=scope,
                delivery_status=(capture.status if capture is not None else "not_recorded"),
                warnings=(delivery_warning,),
                source_trace=("recommendation_result_reader", "personalization_delivery_ack"),
            )
        if scope is not None and capture is not None:
            temporal_state, temporal_warnings = inspect_personalization_temporal_context(
                context_map,
                actual_decision_date=scope.decision_date,
                scope=scope,
                expected_result_id=resolved_result_id,
                expected_receipt_hash=(
                    capture.projection_receipt_hash if capture is not None else None
                ),
            )
            if temporal_state == "invalid":
                return self._empty(
                    resolved_result_id,
                    resolved_stock_code,
                    status="unavailable",
                    decision_date=decision_date,
                    scope=scope,
                    delivery_status=(capture.status if capture is not None else "not_recorded"),
                    warnings=temporal_warnings or ("temporal_contract_invalid",),
                    source_trace=("recommendation_result_reader", "producer_temporal_contract"),
                )
            if temporal_state == "historical":
                return self._population_only(
                    result_id=resolved_result_id,
                    stock_code=resolved_stock_code,
                    decision_date=decision_date,
                    scope=scope,
                    capture=capture,
                    warnings=(
                        "historical_research_not_natural",
                        *temporal_warnings,
                    ),
                )
            if temporal_state == "legacy_unverified":
                return self._population_only(
                    result_id=resolved_result_id,
                    stock_code=resolved_stock_code,
                    decision_date=decision_date,
                    scope=scope,
                    capture=capture,
                    warnings=("temporal_contract_unverified",),
                )
        if (
            scope is None
            or scope.scope_status != "bound"
            or not scope.is_personal_scope
            or scope.captured_at is None
            or scope.temporal_status != "verified"
        ):
            return self._population_only(
                result_id=resolved_result_id,
                stock_code=resolved_stock_code,
                decision_date=decision_date,
                scope=scope,
                capture=capture,
                warnings=("personalization_scope_unbound_or_temporal_unverified",),
            )

        if capture is None:
            return self._population_only(
                result_id=resolved_result_id,
                stock_code=resolved_stock_code,
                decision_date=decision_date,
                scope=scope,
                warnings=("delivery_capture_missing",),
            )
        if capture.status != "delivered":
            return self._not_delivered(
                result_id=resolved_result_id,
                stock_code=resolved_stock_code,
                decision_date=decision_date,
                scope=scope,
                capture=capture,
            )

        prediction, receipt_warning = self._resolve_prediction(
            result_map,
            candidate,
            context_map,
            capture=capture,
            result_id=resolved_result_id,
            stock_code=resolved_stock_code,
            decision_date=decision_date,
            source_cutoff_date=source_cutoff_date,
            explicit_receipt=projection_receipt,
        )
        if receipt_warning:
            return self._empty(
                resolved_result_id,
                resolved_stock_code,
                status="unavailable",
                decision_date=decision_date,
                scope=scope,
                delivery_status=capture.status,
                warnings=(receipt_warning,),
                source_trace=("recommendation_result_reader", "personalization_delivery_capture", "projection_receipt"),
            )
        (
            action,
            action_state,
            revision_id,
            action_warnings,
            historical_state,
            current_state,
            human_decision_at,
        ) = self._resolve_action(
            resolved_result_id,
            resolved_stock_code,
            scope=scope,
            capture=capture,
            prediction=prediction,
            cutoff=cutoff,
        )
        outcomes, outcome_status, outcome_warnings, duplicate_exact, duplicate_conflict = self._resolve_outcomes(
            resolved_result_id,
            resolved_stock_code,
            scope=scope,
            capture=capture,
            prediction=prediction,
            cutoff=cutoff,
            evaluated_as_of=evaluated_date,
        )
        warnings = list(action_warnings) + list(outcome_warnings)
        delivered_at = _datetime_optional(capture.delivered_at, "delivered_at")
        prediction_decision_at = _datetime_optional(scope.decision_at, "decision_at")
        # ACK naturally follows producer inference.  ``late_delivery`` is a
        # personal-evaluation gate only when an explicit human/evaluation
        # anchor exists and the ACK arrived after that anchor.  The producer
        # clock is still exposed separately as ``prediction_decision_at``.
        late_delivery = bool(
            delivered_at is not None
            and human_decision_at is not None
            and delivered_at > human_decision_at
        )
        if late_delivery:
            warnings.append("late_delivery_no_natural_credit")
        evidence_status = "linked_prediction"
        evidence = PersonalizationDecisionEvidence(
            scope=scope,
            result_id=resolved_result_id,
            stock_code=resolved_stock_code,
            decision_date=decision_date,
            prediction_id=capture.prediction_id,
            prediction_status="delivered" if not late_delivery else "delivered_late",
            prediction=prediction,
            action=action,
            action_state=action_state,
            action_revision_id=revision_id,
            historical_action_state=historical_state,
            current_action_state=current_state,
            outcome_status=outcome_status,
            outcomes=tuple(outcomes),
            source_trace=(
                "recommendation_result_reader",
                "personalization_delivery_capture",
                "projection_receipt",
                "decision_continuity_reader",
                "evidence_outcome_reader",
            ),
            warnings=tuple(warnings),
            status=evidence_status,
            delivery_capture=capture,
            prediction_decision_at=(
                prediction_decision_at.isoformat(timespec="microseconds")
                if prediction_decision_at is not None
                else None
            ),
            delivery_at=(
                delivered_at.isoformat(timespec="microseconds")
                if delivered_at is not None
                else None
            ),
            human_decision_at=(
                human_decision_at.isoformat(timespec="microseconds")
                if human_decision_at is not None
                else None
            ),
            formal_order_allowed=False,
            auto_action_allowed=False,
        )
        return PersonalizationProjectionResult(
            status="linked_prediction",
            result_id=resolved_result_id,
            stock_code=resolved_stock_code,
            decision_date=decision_date,
            scope=scope,
            evidence=evidence,
            prediction=prediction,
            action=action,
            action_state=action_state,
            action_revision_id=revision_id,
            historical_action_state=historical_state,
            current_action_state=current_state,
            outcome_status=outcome_status,
            outcomes=tuple(outcomes),
            delivery_status=capture.status,
            late_delivery=late_delivery,
            prediction_decision_at=(
                prediction_decision_at.isoformat(timespec="microseconds")
                if prediction_decision_at is not None
                else None
            ),
            delivery_at=(
                delivered_at.isoformat(timespec="microseconds")
                if delivered_at is not None
                else None
            ),
            human_decision_at=(
                human_decision_at.isoformat(timespec="microseconds")
                if human_decision_at is not None
                else None
            ),
            duplicate_exact_count=duplicate_exact,
            duplicate_conflict_count=duplicate_conflict,
            warnings=tuple(warnings),
            source_trace=evidence.source_trace,
        )

    def _resolve_delivery_ack(
        self,
        capture: PersonalizationDeliveryCapture | None,
        *,
        result_id: str,
        stock_code: str,
    ) -> tuple[PersonalizationDeliveryCapture | None, str | None]:
        """Apply an append-only delivery ACK without rewriting the result row."""

        if capture is None or self.delivery_reader is None:
            return capture, None
        try:
            rows = _reader_rows(self.delivery_reader, result_id, stock_code)
            exact_rows, _, conflict_count = _exact_rows(
                rows,
                result_id=result_id,
                stock_code=stock_code,
            )
        except PersonalizationProjectionError as exc:
            return capture, f"delivery ACK reader invalid:{exc}"
        if conflict_count:
            return None, "delivery ACK duplicate identity conflict"
        if not exact_rows:
            return capture, None
        if any(
            _text(row.get("journal_read_status")) == "incomplete"
            for row in exact_rows
        ):
            return capture, "delivery ACK history incomplete"
        raw = exact_rows[0]
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
        if _text(merged.get("event_kind")) != PERSONALIZATION_DELIVERY_ACK_SCHEMA_VERSION:
            return capture, "delivery ACK event schema is unsupported"
        if _text(merged.get("status")) != "delivered":
            return capture, "delivery ACK lifecycle status is unsupported"
        if _text(merged.get("result_id")) != result_id or _text(merged.get("stock_code")) != stock_code:
            return capture, "delivery ACK candidate identity mismatch"
        if _text(merged.get("personalization_scope_id")) != capture.scope.scope_id:
            return capture, "delivery ACK scope identity mismatch"
        if _text(merged.get("scope_envelope_hash")) != capture.scope.envelope_hash:
            return capture, "delivery ACK scope envelope mismatch"
        if _text(merged.get("delivery_id")) != capture.delivery_id:
            return capture, "delivery ACK delivery identity mismatch"
        if _text(merged.get("request_id")) != capture.request_id:
            return capture, "delivery ACK request identity mismatch"
        if _text(merged.get("capture_hash")) != capture.capture_hash:
            return capture, "delivery ACK compare-and-set capture hash conflict"
        persisted_at = _text(merged.get("persisted_at"))
        delivered_at = _text(merged.get("delivered_at"))
        if not persisted_at or not delivered_at:
            return capture, "delivery ACK lifecycle clocks are incomplete"
        try:
            if capture.status == "delivered":
                canonical_delivered_at = canonical_aware_datetime(
                    delivered_at, "delivered_at"
                )
                if capture.delivered_at != canonical_delivered_at:
                    return capture, "delivery ACK delivered timestamp conflict"
                return capture, None
            persisted = (
                capture
                if capture.status == "persisted"
                else self.capture_service.mark_persisted(
                    capture,
                    persisted_at=persisted_at,
                )
            )
            return self.capture_service.mark_delivered(
                persisted,
                delivered_at=delivered_at,
            ), None
        except (TypeError, ValueError) as exc:
            return capture, f"delivery ACK lifecycle invalid:{type(exc).__name__}"

    @staticmethod
    def _candidate_rows(result: Mapping[str, Any], stock_code: str) -> list[dict[str, Any]]:
        raw_rows = result.get("recommendations")
        if not isinstance(raw_rows, list):
            return []
        rows: list[dict[str, Any]] = []
        for raw in raw_rows:
            try:
                row = _mapping(raw, "recommendation row")
            except PersonalizationProjectionError:
                continue
            try:
                candidate_stock = _stock_code(row)
            except PersonalizationProjectionError:
                # A contradictory stock alias must not be allowed to hide
                # behind the first truthy field and become an exact match.
                continue
            if candidate_stock == stock_code:
                rows.append(row)
        return rows

    @staticmethod
    def _decision_date(
        result: Mapping[str, Any],
        candidate: Mapping[str, Any],
        context: Mapping[str, Any],
    ) -> str | None:
        for value in (
            context.get("as_of_date"),
            context.get("decision_date"),
            candidate.get("decision_date"),
            result.get("decision_date"),
        ):
            if _text(value):
                try:
                    return _date_text(value, "decision_date")
                except PersonalizationProjectionError:
                    return None
        return None

    def _resolve_capture_and_scope(
        self,
        result: Mapping[str, Any],
        candidate: Mapping[str, Any],
        context: Mapping[str, Any],
        *,
        result_id: str,
        stock_code: str,
        requested_scope_id: str | None,
        explicit_capture: Any,
    ) -> tuple[PersonalizationDeliveryCapture | None, PersonalizationDeliveryScope | None, str | None]:
        raw_captures: list[Any] = []
        if explicit_capture is not None:
            raw_captures.append(explicit_capture)
        for key in ("personalization_delivery_capture", "delivery_capture"):
            if candidate.get(key) is not None:
                raw_captures.append(candidate.get(key))
        provenance = candidate.get("calibration_provenance")
        if isinstance(provenance, Mapping) and provenance.get("delivery_capture") is not None:
            raw_captures.append(provenance.get("delivery_capture"))
        for key in ("personalization_delivery_capture", "delivery_capture"):
            if context.get(key) is not None:
                raw_captures.append(context.get(key))
        raw_list = context.get("personalization_delivery_captures")
        raw_captures.extend(_capture_candidates(raw_list))
        captures: list[PersonalizationDeliveryCapture] = []
        for raw in raw_captures:
            try:
                parsed = _capture_from_any(raw)
            except (TypeError, ValueError) as exc:
                return None, None, f"delivery_capture_invalid:{type(exc).__name__}"
            if parsed is None:
                continue
            if parsed.result_id != result_id or parsed.stock_code != stock_code:
                return None, parsed.scope, "delivery_capture_identity_mismatch"
            if parsed.result_id == result_id and parsed.stock_code == stock_code:
                captures.append(parsed)
        if not captures:
            scope = self._scope_from_sources(result, candidate, context)
            if requested_scope_id and scope is not None and scope.scope_id != _text(requested_scope_id):
                return None, scope, "personalization_scope_identity_mismatch"
            return None, scope, None
        first = captures[0]
        if any(parsed.capture_hash != first.capture_hash for parsed in captures[1:]):
            return None, first.scope, "delivery_capture_duplicate_conflict"
        if requested_scope_id and first.scope.scope_id != _text(requested_scope_id):
            return None, first.scope, "personalization_scope_identity_mismatch"
        for source in (
            candidate.get("personalization_scope"),
            candidate.get("delivery_scope"),
            context.get("personalization_scope"),
            context.get("personalization_delivery_scope"),
            result.get("personalization_scope"),
        ):
            if source is None:
                continue
            try:
                source_scope = _scope_from_any(source)
            except (TypeError, ValueError):
                return None, first.scope, "personalization_scope_invalid"
            if source_scope is not None and source_scope.envelope_hash != first.scope.envelope_hash:
                return None, first.scope, "personalization_scope_conflict"
        for source in (candidate.get("personalization_scope_hash"), candidate.get("scope_hash")):
            if _text(source) and _text(source) != first.scope.envelope_hash:
                return None, first.scope, "personalization_scope_hash_mismatch"
        provenance = candidate.get("calibration_provenance")
        if isinstance(provenance, Mapping):
            for source in (provenance.get("personalization_scope_hash"), provenance.get("scope_hash")):
                if _text(source) and _text(source) != first.scope.envelope_hash:
                    return None, first.scope, "personalization_scope_hash_mismatch"
        return first, first.scope, None

    @staticmethod
    def _scope_from_sources(
        result: Mapping[str, Any],
        candidate: Mapping[str, Any],
        context: Mapping[str, Any],
    ) -> PersonalizationDeliveryScope | None:
        for source in (
            candidate.get("personalization_scope"),
            candidate.get("delivery_scope"),
            context.get("personalization_scope"),
            context.get("personalization_delivery_scope"),
            result.get("personalization_scope"),
        ):
            if source is None:
                continue
            try:
                return _scope_from_any(source)
            except (TypeError, ValueError):
                return None
        return None

    def _resolve_prediction(
        self,
        result: Mapping[str, Any],
        candidate: Mapping[str, Any],
        context: Mapping[str, Any],
        *,
        capture: PersonalizationDeliveryCapture,
        result_id: str,
        stock_code: str,
        decision_date: str,
        source_cutoff_date: str | None,
        explicit_receipt: Any,
    ) -> tuple[dict[str, Any], str | None]:
        provenance = candidate.get("calibration_provenance")
        provenance_map = provenance if isinstance(provenance, Mapping) else {}
        rows = context.get("calibration_projection_rows")
        row = rows.get(stock_code) if isinstance(rows, Mapping) else None
        context_row = row if isinstance(row, Mapping) else {}
        declared_prediction_id = _first_text(
            context_row.get("prediction_id"),
            candidate.get("prediction_id"),
            provenance_map.get("prediction_id"),
        )
        if declared_prediction_id and declared_prediction_id != capture.prediction_id:
            return {}, "prediction identity mismatch"
        expected_hash = capture.projection_receipt_hash
        receipt_value = explicit_receipt
        if receipt_value is None:
            for value in (
                candidate.get("projection_receipt"),
                provenance_map.get("projection_receipt"),
                context.get("projection_receipt"),
                context.get("calibration_projection_receipt"),
            ):
                if value is None:
                    continue
                value_map = value if isinstance(value, Mapping) else {}
                # The service stores a metadata reference with ``path`` and
                # hash in this field.  Treat only an embedded receipt payload
                # (or a receipt DTO with a payload) as the actual receipt;
                # path metadata is resolved below.
                if isinstance(value, Mapping) and not (
                    "projections" in value or isinstance(value.get("payload"), Mapping)
                ):
                    continue
                if value is not None and (not isinstance(value, Mapping) or value_map):
                    receipt_value = value
                    break
        context_receipt = context.get("calibration_projection_receipt")
        context_receipt_path: object = context.get("calibration_projection_receipt_path")
        if isinstance(context_receipt, Mapping):
            context_receipt_path = context_receipt.get("path") or context_receipt_path
        elif context_receipt not in (None, ""):
            context_receipt_path = context_receipt
        receipt_path = _first_text(
            capture.projection_receipt_path,
            candidate.get("projection_receipt_path"),
            provenance_map.get("projection_receipt_path"),
            context_receipt_path,
        )
        try:
            if receipt_value is None and receipt_path:
                from ml_module.recommendation_inference_provenance import (
                    read_inference_projection_receipt,
                )

                receipt_value = read_inference_projection_receipt(
                    Path(receipt_path),
                    expected_receipt_hash=expected_hash,
                    expected_result_id=result_id,
                    expected_stock_code=stock_code,
                )
            if receipt_value is None:
                receipt_value = _reader_value(self.projection_receipt_reader, expected_hash)
            if receipt_value is None:
                return {}, "projection receipt is missing"
            payload, receipt_row = _verify_receipt_mapping(
                _receipt_mapping(receipt_value),
                expected_hash=expected_hash,
                result_id=result_id,
                stock_code=stock_code,
            )
        except (OSError, TypeError, ValueError) as exc:
            return {}, f"projection receipt invalid:{type(exc).__name__}"
        receipt_identity = _text(receipt_row.get("prediction_id"))
        if receipt_identity and receipt_identity != capture.prediction_id:
            return {}, "projection receipt prediction identity mismatch"
        receipt_decision_date = _date_text(
            payload.get("decision_date"),
            "projection receipt decision_date",
        )
        if source_cutoff_date is not None and receipt_decision_date != source_cutoff_date:
            return {}, "projection receipt source cutoff date mismatch"
        try:
            verified_horizon = _horizon_days(
                receipt_row.get("horizon_days") or receipt_row.get("horizon"),
                "projection receipt horizon",
            )
        except PersonalizationProjectionError as exc:
            return {}, str(exc)
        if verified_horizon is None or capture.horizon_days is None:
            return {}, "prediction horizon is not verified"
        if verified_horizon != capture.horizon_days:
            return {}, "projection receipt horizon mismatch"

        candidate_identity = payload.get("candidate_identity")
        candidate_identity_map = (
            candidate_identity if isinstance(candidate_identity, Mapping) else {}
        )
        training_provenance = payload.get("training_provenance")
        training_map = (
            training_provenance if isinstance(training_provenance, Mapping) else {}
        )
        inference_provenance = payload.get("inference_provenance")
        inference_map = (
            inference_provenance if isinstance(inference_provenance, Mapping) else {}
        )
        try:
            verified_model_id = _consistent_text(
                (
                    receipt_row.get("model_id"),
                    receipt_row.get("model_version"),
                    payload.get("model_id"),
                    candidate_identity_map.get("model_id"),
                    inference_map.get("model_id"),
                ),
                "model_id",
            )
            verified_dataset_id = _consistent_text(
                (
                    receipt_row.get("dataset_id"),
                    receipt_row.get("dataset_version"),
                    payload.get("dataset_id"),
                    training_map.get("dataset_id"),
                    inference_map.get("dataset_id"),
                ),
                "dataset_id",
            )
            verified_cost = _consistent_text(
                (
                    receipt_row.get("cost_scenario_hash"),
                    payload.get("cost_scenario_hash"),
                    inference_map.get("cost_scenario_hash"),
                ),
                "cost_scenario_hash",
            )
        except PersonalizationProjectionError as exc:
            return {}, str(exc)
        if not capture.model_id or capture.model_id != verified_model_id:
            return {}, "capture model identity is not verified"
        if not capture.dataset_id or capture.dataset_id != verified_dataset_id:
            return {}, "capture dataset identity is not verified"
        if capture.cost_scenario_hash is None or capture.cost_scenario_hash != verified_cost:
            return {}, "capture cost scenario identity is not verified"

        verified_dataset_hash = _consistent_text(
            (
                receipt_row.get("dataset_hash"),
                payload.get("dataset_hash"),
                training_map.get("dataset_hash"),
            ),
            "dataset_hash",
            required=False,
        )
        capture_dataset_hash = capture.dataset_hash
        if capture.dataset_hash:
            if not verified_dataset_hash or capture.dataset_hash != verified_dataset_hash:
                return {}, "capture dataset hash is not verified"
        elif verified_dataset_hash:
            capture_dataset_hash = verified_dataset_hash

        probability_key = ""
        verified_probability: int | None = None
        verified_probabilities: dict[str, int] = {}
        for key in (
            "calibrated_probability_bp",
            "after_cost_profit_probability_bp",
            "population_probability_bp",
        ):
            if receipt_row.get(key) not in (None, ""):
                parsed_probability = _probability_bp(
                    receipt_row.get(key),
                    f"receipt.{key}",
                )
                if parsed_probability is not None:
                    verified_probabilities[key] = parsed_probability
                    if not probability_key:
                        probability_key = key
                        verified_probability = parsed_probability
        if not probability_key or verified_probability is None:
            return {}, "projection receipt probability is not verified"

        verified_label_contract = _consistent_text(
            (
                receipt_row.get("label_contract_id"),
                payload.get("label_contract_id"),
                inference_map.get("label_contract_id"),
            ),
            "label_contract_id",
            required=False,
        )
        verified_return_basis = _consistent_text(
            (
                receipt_row.get("return_basis"),
                payload.get("return_basis"),
                inference_map.get("return_basis"),
            ),
            "return_basis",
            required=False,
        )
        verified_universe_policy_hash = _consistent_text(
            (
                receipt_row.get("universe_policy_hash"),
                payload.get("universe_policy_hash"),
                inference_map.get("universe_policy_hash"),
            ),
            "universe_policy_hash",
            required=False,
        )
        verified_source_id = _consistent_text(
            (
                receipt_row.get("source_id"),
                payload.get("source_id"),
                inference_map.get("source_id"),
                capture.source,
            ),
            "source_id",
        )

        context_sources = (
            ("calibration_projection_row", context_row),
            ("candidate", candidate),
            ("calibration_provenance", provenance_map),
        )
        for source_name, source in context_sources:
            if not isinstance(source, Mapping):
                continue
            for key in ("calibrated_probability_bp", "after_cost_profit_probability_bp"):
                if source.get(key) not in (None, "") and receipt_row.get(key) not in (None, ""):
                    if _probability_bp(source.get(key), f"{source_name}.{key}") != _probability_bp(
                        receipt_row.get(key),
                        f"receipt.{key}",
                    ):
                        return {}, f"{source_name} {key} conflicts with verified receipt"
            if source.get("population_probability_bp") not in (None, "") and receipt_row.get("population_probability_bp") not in (None, ""):
                if _probability_bp(source.get("population_probability_bp"), f"{source_name}.population_probability_bp") != _probability_bp(
                    receipt_row.get("population_probability_bp"),
                    "receipt.population_probability_bp",
                ):
                    return {}, f"{source_name} population probability conflicts with verified receipt"
            source_horizon = source.get("horizon_days") or source.get("horizon")
            if source_horizon not in (None, "") and _horizon_days(source_horizon, f"{source_name}.horizon") != verified_horizon:
                return {}, f"{source_name} horizon conflicts with verified receipt"
            for source_key, expected in (
                ("model_id", verified_model_id),
                ("model_version", verified_model_id),
                ("dataset_id", verified_dataset_id),
                ("dataset_version", verified_dataset_id),
                ("cost_scenario_hash", verified_cost),
                ("projection_receipt_hash", expected_hash),
            ):
                if source.get(source_key) not in (None, "") and _text(source.get(source_key)) != expected:
                    return {}, f"{source_name} {source_key} conflicts with verified receipt"
            if source.get("decision_date") not in (None, "") and _date_text(
                source.get("decision_date"),
                f"{source_name}.decision_date",
            ) != receipt_decision_date:
                return {}, f"{source_name} decision_date conflicts with verified receipt"

        prediction: dict[str, Any] = {
            "stock_code": stock_code,
            "prediction_id": capture.prediction_id,
            "projection_receipt_hash": expected_hash,
            "projection_receipt_result_id": result_id,
            "prediction_receipt_schema_version": PERSONALIZATION_PREDICTION_RECEIPT_SCHEMA_VERSION,
            # Keep actual prediction timing separate from the immutable
            # receipt's source/data cutoff.  The latter is not a substitute
            # for the personal decision session used by outcome joins.
            "decision_date": decision_date,
            "prediction_decision_date": decision_date,
            "data_as_of_date": receipt_decision_date,
            "projection_receipt_decision_date": receipt_decision_date,
            "model_id": verified_model_id,
            "model_version": verified_model_id,
            "dataset_id": verified_dataset_id,
            "dataset_version": verified_dataset_id,
            "dataset_hash": capture_dataset_hash,
            "cost_scenario_hash": verified_cost,
            "horizon_days": verified_horizon,
            "horizon": f"{verified_horizon} trading days",
            "source_id": verified_source_id,
            "receipt_selection_contract": dict(payload.get("selection_contract") or {}),
        }
        if verified_probability is not None:
            for key, value in verified_probabilities.items():
                prediction[key] = value
            # Preserve the existing projection's primary probability alias,
            # while keeping an explicitly supplied population probability
            # separate for the personal evaluator.  Never derive population
            # probability from calibrated/after-cost output.
            prediction["calibrated_probability_bp"] = verified_probabilities.get(
                "calibrated_probability_bp",
                verified_probabilities.get(
                    "after_cost_profit_probability_bp",
                    verified_probabilities.get("population_probability_bp", verified_probability),
                ),
            )
        if verified_label_contract:
            prediction["label_contract_id"] = verified_label_contract
        if verified_return_basis:
            prediction["return_basis"] = verified_return_basis
        if verified_universe_policy_hash:
            prediction["universe_policy_hash"] = verified_universe_policy_hash
        for key in ("ranking_score_bp", "ranking_percentile_bp", "status"):
            if context_row.get(key) is not None:
                prediction[key] = context_row[key]
            elif candidate.get(key) is not None:
                prediction[key] = candidate[key]
        return prediction, None

    def _resolve_action(
        self,
        result_id: str,
        stock_code: str,
        *,
        scope: PersonalizationDeliveryScope,
        capture: PersonalizationDeliveryCapture,
        prediction: Mapping[str, Any],
        cutoff: datetime | None,
    ) -> tuple[str, str, str, tuple[str, ...], str, str, datetime | None]:
        raw_rows = _reader_rows(self.action_reader, result_id, stock_code)
        exact_rows: list[tuple[datetime, str, dict[str, Any]]] = []
        warnings: list[str] = []
        identity_conflict = False
        observed_human_decision_at: datetime | None = None
        latest_observed_revision: tuple[datetime, str] | None = None
        expected_horizon = _verified_horizon_from_prediction(prediction)
        expected_cost = _verified_cost_from_prediction(prediction)
        expected_label_contract = _text(prediction.get("label_contract_id"))
        expected_return_basis = _text(prediction.get("return_basis"))
        for raw in raw_rows:
            try:
                row = _mapping(raw, "action row")
            except PersonalizationProjectionError:
                warnings.append("action_row_invalid")
                continue
            if _text(row.get("journal_read_status")) == "incomplete":
                identity_conflict = True
                warnings.append("action_history_incomplete")
                continue
            try:
                row_result, row_stock = _identity_from_row(row)
            except PersonalizationProjectionError:
                identity_conflict = True
                warnings.append("action_identity_alias_conflict")
                continue
            if row_result != result_id or row_stock != stock_code:
                warnings.append("action_identity_mismatch")
                continue
            try:
                row_scope = _verified_alias_text(
                    row,
                    "action.personalization_scope_id",
                    ("personalization_scope_id", "scope_id"),
                )
                row_prediction = _verified_alias_text(
                    row,
                    "action.prediction_id",
                    ("prediction_id",),
                )
                row_receipt = _verified_alias_text(
                    row,
                    "action.prediction_receipt_hash",
                    ("prediction_receipt_hash", "projection_receipt_hash"),
                )
                row_horizon = _verified_alias_horizon(row, "action.horizon")
                row_cost = _verified_alias_text(
                    row,
                    "action.cost_scenario_hash",
                    ("cost_scenario_hash",),
                )
                row_label_contract = _verified_alias_text(
                    row,
                    "action.label_contract_id",
                    ("label_contract_id",),
                )
                row_return_basis = _verified_alias_text(
                    row,
                    "action.return_basis",
                    ("return_basis",),
                )
            except PersonalizationProjectionError:
                identity_conflict = True
                warnings.append("action_contract_alias_conflict")
                continue
            if (
                not row_scope
                or row_scope != scope.scope_id
                or not row_prediction
                or row_prediction != capture.prediction_id
                or not row_receipt
                or row_receipt != capture.projection_receipt_hash
                or row_horizon != expected_horizon
                or row_cost != expected_cost
                or (
                    expected_label_contract
                    and row_label_contract != expected_label_contract
                )
                or (
                    expected_return_basis
                    and row_return_basis != expected_return_basis
                )
            ):
                identity_conflict = True
                warnings.append("action_contract_mismatch")
                continue
            try:
                action_at = _datetime_optional(
                    _verified_alias_text(row, "action.action_at", ("action_at",)),
                    "action.action_at",
                )
                recorded_text = _verified_alias_text(
                    row,
                    "action.recorded_at",
                    ("recorded_at",),
                )
                if not recorded_text:
                    recorded_text = _verified_alias_text(
                        row,
                        "action.created_at",
                        ("created_at",),
                    )
                recorded_at = _datetime_optional(recorded_text, "action.recorded_at")
                created_text = _verified_alias_text(
                    row,
                    "action.created_at",
                    ("created_at",),
                )
                created_at = _datetime_optional(created_text, "action.created_at")
            except PersonalizationProjectionError:
                identity_conflict = True
                warnings.append("action_clock_invalid")
                continue
            if action_at is None or recorded_at is None:
                identity_conflict = True
                warnings.append("action_clock_missing")
                continue
            cutoff_clock = created_at or recorded_at
            if cutoff is not None and (
                action_at > cutoff
                or recorded_at > cutoff
                or cutoff_clock > cutoff
            ):
                # A future revision is outside this evaluation snapshot and
                # must not become its human/evaluation anchor.
                continue
            delivered_at = _datetime_optional(capture.delivered_at, "delivered_at")
            if recorded_at < action_at or (created_at is not None and created_at < recorded_at):
                identity_conflict = True
                warnings.append("action_clock_order_invalid")
                continue
            revision_id = _text(row.get("revision_id"))
            revision_key = (recorded_at, revision_id)
            if (
                latest_observed_revision is None
                or revision_key > latest_observed_revision
            ):
                latest_observed_revision = revision_key
                # The last recorded matching revision defines the
                # human/evaluation anchor.  It is intentionally not the
                # maximum action_at across history because a later revision
                # may legitimately correct the earlier action timestamp.
                observed_human_decision_at = action_at
            if delivered_at is not None and action_at < delivered_at:
                # Historical continuity may predate delivery, but it cannot
                # be elevated to a response to this personal prediction.
                identity_conflict = True
                warnings.append("action_before_delivery")
                continue
            exact_rows.append((recorded_at, _text(row.get("revision_id")), row))
        if not exact_rows:
            if identity_conflict:
                return (
                    "not_recorded",
                    "conflict",
                    "",
                    tuple(warnings),
                    "conflict",
                    "conflict",
                    observed_human_decision_at,
                )
            return (
                "not_recorded",
                "not_recorded",
                "",
                tuple(warnings),
                "not_recorded",
                "not_recorded",
                observed_human_decision_at,
            )
        exact_rows.sort(key=lambda item: (item[0], item[1]))
        if identity_conflict:
            warnings.append("action_alias_conflict")
            return (
                "not_recorded",
                "conflict",
                "",
                tuple(warnings),
                "conflict",
                "conflict",
                observed_human_decision_at,
            )
        action, state, revision_id, action_warning = _canonical_action(exact_rows[-1][2])
        if action_warning:
            warnings.append(action_warning)
        historical_action = _canonical_action(exact_rows[0][2])[1]
        return (
            action,
            state,
            revision_id,
            tuple(warnings),
            historical_action,
            state,
            observed_human_decision_at,
        )

    def _resolve_outcomes(
        self,
        result_id: str,
        stock_code: str,
        *,
        scope: PersonalizationDeliveryScope,
        capture: PersonalizationDeliveryCapture,
        prediction: Mapping[str, Any],
        cutoff: datetime | None,
        evaluated_as_of: str | None,
    ) -> tuple[tuple[dict[str, Any], ...], str, tuple[str, ...], int, int]:
        raw_rows = list(_reader_rows(self.outcome_reader, result_id, stock_code))
        preflatten_warnings: list[str] = []
        preflatten_identity_conflict = False
        for event in _reader_rows(self.evidence_reader, result_id, stock_code):
            try:
                event_map = _mapping(event, "evidence event")
            except PersonalizationProjectionError:
                continue
            nested_outcomes = event_map.get("outcomes")
            if isinstance(nested_outcomes, (list, tuple)):
                for nested in nested_outcomes:
                    if isinstance(nested, Mapping):
                        try:
                            merged = _merge_evidence_parent_child(event_map, nested)
                        except PersonalizationProjectionError:
                            preflatten_identity_conflict = True
                            preflatten_warnings.append(
                                "outcome_preflatten_contract_conflict"
                            )
                            continue
                        raw_rows.append(merged)
            elif isinstance(event_map.get("outcome"), Mapping):
                nested = event_map["outcome"]
                try:
                    merged = _merge_evidence_parent_child(event_map, nested)
                except PersonalizationProjectionError:
                    preflatten_identity_conflict = True
                    preflatten_warnings.append(
                        "outcome_preflatten_contract_conflict"
                    )
                else:
                    raw_rows.append(merged)
            elif event_map.get("outcome_status") is not None or event_map.get("status") is not None:
                raw_rows.append(event_map)
        exact_rows: list[dict[str, Any]] = []
        warnings: list[str] = list(preflatten_warnings)
        identity_conflict = preflatten_identity_conflict
        expected_horizon = _verified_horizon_from_prediction(prediction)
        expected_cost = _verified_cost_from_prediction(prediction)
        expected_label_contract = _text(prediction.get("label_contract_id"))
        expected_return_basis = _text(prediction.get("return_basis"))
        for raw in raw_rows:
            try:
                row = _mapping(raw, "outcome row")
            except PersonalizationProjectionError:
                warnings.append("outcome_row_invalid")
                continue
            try:
                row_result, row_stock = _identity_from_row(row)
            except PersonalizationProjectionError:
                identity_conflict = True
                warnings.append("outcome_identity_alias_conflict")
                continue
            if row_result != result_id or row_stock != stock_code:
                warnings.append("outcome_identity_mismatch")
                continue
            try:
                row_scope = _verified_alias_text(
                    row,
                    "outcome.personalization_scope_id",
                    ("personalization_scope_id", "scope_id"),
                )
                row_prediction = _verified_alias_text(
                    row,
                    "outcome.prediction_id",
                    ("prediction_id",),
                )
                row_receipt = _verified_alias_text(
                    row,
                    "outcome.prediction_receipt_hash",
                    ("prediction_receipt_hash", "projection_receipt_hash"),
                )
                row_horizon = _verified_alias_horizon(row, "outcome.horizon")
                # Evidence rows use ``window_days`` as the outcome-window
                # identity.  An event parent may also carry the prediction's
                # ``horizon_days`` while exposing several child windows; the
                # child window therefore takes precedence and siblings are
                # evaluated independently.
                window_days = _verified_alias_text(row, "outcome.window_days", ("window_days",))
                if window_days:
                    try:
                        parsed_window_days = int(window_days)
                    except ValueError as exc:
                        raise PersonalizationProjectionError(
                            "outcome.window_days is invalid"
                        ) from exc
                    if parsed_window_days <= 0:
                        raise PersonalizationProjectionError(
                            "outcome.window_days is invalid"
                        )
                    row_horizon = parsed_window_days
                row_cost = _verified_alias_text(
                    row,
                    "outcome.cost_scenario_hash",
                    ("cost_scenario_hash",),
                )
                row_label_contract = _verified_alias_text(
                    row,
                    "outcome.label_contract_id",
                    ("label_contract_id",),
                )
                row_return_basis = _verified_alias_text(
                    row,
                    "outcome.return_basis",
                    ("return_basis",),
                )
            except PersonalizationProjectionError:
                identity_conflict = True
                warnings.append("outcome_contract_alias_conflict")
                continue
            if (
                row_horizon is not None
                and row_horizon != expected_horizon
                and row_scope == scope.scope_id
                and row_prediction == capture.prediction_id
                and row_receipt == capture.projection_receipt_hash
            ):
                # One EvidenceEvent may legitimately carry several forward
                # windows.  They are parallel outcome rows, not duplicates or
                # aliases of one another.  Keep only the prediction's exact
                # horizon; a wrong prediction/scope/receipt still reaches the
                # contract-mismatch branch below.
                warnings.append("outcome_parallel_horizon_ignored")
                continue
            if (
                not row_scope
                or row_scope != scope.scope_id
                or not row_prediction
                or row_prediction != capture.prediction_id
                or not row_receipt
                or row_receipt != capture.projection_receipt_hash
                or row_horizon != expected_horizon
                or row_cost != expected_cost
                or not expected_label_contract
                or row_label_contract != expected_label_contract
                or not expected_return_basis
                or row_return_basis != expected_return_basis
            ):
                identity_conflict = True
                warnings.append("outcome_contract_mismatch")
                continue
            status = _outcome_status(row)
            if status not in PERSONALIZATION_OUTCOME_STATUSES:
                status = "invalid"
            row["outcome_status"] = status
            row["personalization_scope_id"] = row_scope
            row["prediction_id"] = row_prediction
            row["prediction_receipt_hash"] = row_receipt
            row["horizon_days"] = row_horizon
            row["cost_scenario_hash"] = row_cost
            row["label_contract_id"] = row_label_contract
            row["return_basis"] = row_return_basis
            outcome_timestamp: datetime | None = None
            if status == "ready":
                chronology_warnings = validate_forward_outcome_chronology(
                    row,
                    decision_at=scope.decision_at,
                    decision_date=scope.decision_date,
                )
                if chronology_warnings:
                    row["outcome_status"] = "invalid"
                    warnings.extend(chronology_warnings)
                if cutoff is None or evaluated_as_of is None:
                    row["outcome_status"] = "invalid"
                    warnings.append("outcome_cutoff_missing")
                elif row["outcome_status"] == "ready":
                    try:
                        available_at = _outcome_timestamp(row)
                        outcome_timestamp = available_at
                        recorded_at = _datetime_optional(
                            row.get("outcome_recorded_at")
                            or row.get("recorded_at")
                            or row.get("calculated_at"),
                            "outcome.outcome_recorded_at",
                        )
                    except PersonalizationProjectionError:
                        available_at = None
                        recorded_at = None
                        row["outcome_status"] = "invalid"
                        warnings.append("outcome_clock_invalid")
                    if row["outcome_status"] == "ready":
                        if available_at is None or recorded_at is None:
                            row["outcome_status"] = "invalid"
                            warnings.append("outcome_clock_missing")
                        elif recorded_at < available_at:
                            row["outcome_status"] = "invalid"
                            warnings.append("outcome_clock_order_invalid")
                        elif available_at > cutoff or recorded_at > cutoff:
                            row["outcome_status"] = "pending_maturity"
            row["outcome_verified_at"] = (
                outcome_timestamp.isoformat(timespec="microseconds")
                if outcome_timestamp is not None
                else None
            )
            exact_rows.append(row)
        if identity_conflict:
            warnings.append("outcome_alias_conflict")
        grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for row in exact_rows:
            key = (
                _first_text(row.get("prediction_id")),
                _first_text(row.get("window_days"), row.get("horizon_days"), ""),
                _first_text(row.get("return_basis")),
            )
            grouped.setdefault(key, []).append(row)
        selected: list[dict[str, Any]] = []
        duplicate_exact = 0
        duplicate_conflict = 0
        for values in grouped.values():
            if len(values) == 1:
                selected.append(values[0])
            elif all(_json_equal(values[0], item) for item in values[1:]):
                selected.append(values[0])
                duplicate_exact += len(values) - 1
            else:
                duplicate_conflict += len(values)
                warnings.append("outcome_duplicate_conflict")
        if duplicate_conflict or identity_conflict:
            selected.append({"outcome_status": "duplicate_conflict", "outcome_tier": "natural_forward"})
        tiers = {
            _text(row.get("outcome_tier"))
            for row in selected
            if _text(row.get("outcome_tier"))
        }
        if len(tiers) > 1:
            selected.append({"outcome_status": "conflict", "outcome_tier": "natural_forward"})
            warnings.append("outcome_tier_mixed")
        status = _aggregate_outcome_status(selected)
        return tuple(selected), status, tuple(warnings), duplicate_exact, duplicate_conflict

    @staticmethod
    def _empty(
        result_id: str,
        stock_code: str,
        *,
        status: str,
        decision_date: str | None = None,
        scope: PersonalizationDeliveryScope | None = None,
        delivery_status: str = "not_recorded",
        warnings: Sequence[str] = (),
        source_trace: Sequence[str] = (),
        duplicate_exact_count: int = 0,
        duplicate_conflict_count: int = 0,
    ) -> PersonalizationProjectionResult:
        return PersonalizationProjectionResult(
            status=status,
            result_id=result_id,
            stock_code=stock_code,
            decision_date=decision_date,
            scope=scope,
            delivery_status=delivery_status,
            warnings=tuple(warnings),
            source_trace=tuple(source_trace),
            duplicate_exact_count=duplicate_exact_count,
            duplicate_conflict_count=duplicate_conflict_count,
        )

    @staticmethod
    def _population_only(
        *,
        result_id: str,
        stock_code: str,
        decision_date: str,
        scope: PersonalizationDeliveryScope | None,
        capture: PersonalizationDeliveryCapture | None = None,
        warnings: Sequence[str] = (),
    ) -> PersonalizationProjectionResult:
        return PersonalizationProjectionResult(
            status="population_only",
            result_id=result_id,
            stock_code=stock_code,
            decision_date=decision_date,
            scope=scope,
            delivery_status=capture.status if capture is not None else "not_recorded",
            warnings=tuple(warnings),
            source_trace=("recommendation_result_reader", "personalization_scope"),
        )

    @staticmethod
    def _not_delivered(
        *,
        result_id: str,
        stock_code: str,
        decision_date: str,
        scope: PersonalizationDeliveryScope,
        capture: PersonalizationDeliveryCapture,
    ) -> PersonalizationProjectionResult:
        return PersonalizationProjectionResult(
            status="not_delivered",
            result_id=result_id,
            stock_code=stock_code,
            decision_date=decision_date,
            scope=scope,
            delivery_status=capture.status,
            warnings=("delivery_not_confirmed;prediction_not_in_calibration_denominator",),
            source_trace=("recommendation_result_reader", "personalization_delivery_capture"),
        )


__all__ = [
    "PERSONALIZATION_PROJECTION_SCHEMA_VERSION",
    "PERSONALIZATION_PROJECTION_STATUSES",
    "PersonalizationDeliveryCaptureService",
    "PersonalizationProjectionError",
    "PersonalizationProjectionResult",
    "PersonalizationProjectionService",
]
