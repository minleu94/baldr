"""以固定 parent v4 收據唯讀查詢已驗證的五條技術規則。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Literal, NoReturn, cast
from zoneinfo import ZoneInfo

from app_module.daily_market_technical_feature_snapshot_v4 import (
    DailyMarketTechnicalFeatureSnapshotV4,
    DailyMarketTechnicalRuleEvidenceV4,
)
from app_module.daily_market_technical_snapshot_v4_repository import (
    DailyMarketTechnicalSnapshotV4Repository,
    DailyMarketTechnicalSnapshotV4RepositoryError,
    generation_identity_sha256,
)
from app_module.rule_research_technical_parent_capture_v4 import (
    BoundedDailyMarketTechnicalParentCaptureWriterV4,
    TechnicalParentCaptureV4Error,
)


DAILY_MARKET_TECHNICAL_PARENT_V4_QUERY_SCHEMA = (
    "daily-market-technical-parent-query.v4"
)
DAILY_MARKET_TECHNICAL_PARENT_V4_QUERY_MAX_BYTES = 256 * 1024
DAILY_MARKET_TECHNICAL_PARENT_V4_QUERY_MAX_PAGE_SIZE = 256
DAILY_MARKET_TECHNICAL_PARENT_V4_MAX_PAGE_INDEX = 1_000_000
DAILY_MARKET_TECHNICAL_PARENT_V4_INCLUDED_LIMIT = 256
DAILY_MARKET_TECHNICAL_PARENT_V4_EXCLUDED_LIMIT = 256
DAILY_MARKET_TECHNICAL_PARENT_V4_COVERAGE_SCOPE = "bounded_parent_v4"

_TAIPEI = ZoneInfo("Asia/Taipei")
_MINIMUM_CUTOFF = time(16, 0)
_STATE_ORDER = ("match", "no_match", "unknown")
_PARENT_STATUSES = frozenset({"partial", "complete", "failed", "cancelled"})
_STOCK_CODE_RE = re.compile(r"^[A-Za-z0-9]{1,16}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_QUERY_KEYS = frozenset({
    "schema_version",
    "parent_output_root",
    "parent_plan_identity_sha256",
    "parent_plan_sha256",
    "parent_receipt_identity_sha256",
    "parent_receipt_sha256",
    "parent_status",
    "child_repository_output_root",
    "generation_identity_sha256",
    "cohort_identity_sha256",
    "universe_id",
    "population_version",
    "decision_date",
    "population_state",
    "declared_count",
    "included_stock_codes",
    "excluded_stock_codes",
    "exclusion_reasons",
    "source_clock",
    "source_clock_identity_sha256",
    "method_contracts_sha256",
    "method_rule_keys",
    "coverage_scope",
    "aggregation_scope",
    "included_stock_limit",
    "excluded_stock_limit",
    "full_market_claim",
    "full_n_aggregation",
    "state_filters",
    "combine_mode",
    "stock_filter",
    "sort_key",
    "descending",
    "page_index",
    "page_size",
    "query_identity_sha256",
})
_CLOCK_KEYS = frozenset({
    "database_path",
    "source_id",
    "schema_identity_sha256",
    "source_file_pin",
    "source_pin_sha256",
    "decision_date",
    "decision_cutoff",
    "cutoff_guard_version",
    "source_available_at",
    "availability_status",
    "historical_pit_eligible",
})
_STATE_FILTER_KEYS = frozenset({"rule_key", "states"})

RuleState = Literal["match", "no_match", "unknown"]
CombineMode = Literal["AND", "OR"]
ParentStatus = Literal["partial", "complete", "failed", "cancelled"]


class DailyMarketTechnicalParentV4QueryError(ValueError):
    """固定 parent、查詢條件或保存證據不符合唯讀查詢契約。"""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


def _fail(code: str, message: str | None = None) -> NoReturn:
    raise DailyMarketTechnicalParentV4QueryError(code, message)


def _canonical_json_bytes(value: object) -> bytes:
    _reject_float_tree(value)
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise DailyMarketTechnicalParentV4QueryError(
            "technical_parent_v4_query_json_invalid", str(exc)
        ) from exc


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_json(value: object) -> str:
    return _sha256_bytes(_canonical_json_bytes(value))


def _reject_float_tree(value: object) -> None:
    if isinstance(value, float):
        _fail("technical_parent_v4_query_float_forbidden")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                _fail("technical_parent_v4_query_json_invalid")
            _reject_float_tree(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_float_tree(item)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            _fail("technical_parent_v4_query_duplicate_json_key")
        value[key] = item
    return value


def _reject_constant(value: str) -> NoReturn:
    _fail("technical_parent_v4_query_json_invalid", value)


def _parse_json(raw: bytes | str) -> dict[str, Any]:
    try:
        encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
        if not isinstance(encoded, bytes) or len(encoded) > DAILY_MARKET_TECHNICAL_PARENT_V4_QUERY_MAX_BYTES:
            _fail("technical_parent_v4_query_byte_limit")
        parsed = json.loads(
            encoded.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except DailyMarketTechnicalParentV4QueryError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalParentV4QueryError(
            "technical_parent_v4_query_json_invalid", str(exc)
        ) from exc
    if not isinstance(parsed, dict):
        _fail("technical_parent_v4_query_json_invalid")
    _reject_float_tree(parsed)
    if _canonical_json_bytes(parsed) != encoded:
        _fail("technical_parent_v4_query_noncanonical_json")
    return parsed


def _require_sha(value: object, code: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        _fail(code)
    return value


def _bounded_text(value: object, maximum: int, code: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or value.strip() != value
    ):
        _fail(code)
    return value


def _canonical_absolute_path(value: object, code: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 4096:
        _fail(code)
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts or str(path) != value:
        _fail(code)
    if value.startswith(("\\\\?\\", "\\\\.\\")):
        _fail(code)
    return value


def _parse_iso_date(value: object, code: str) -> date:
    if not isinstance(value, str):
        _fail(code)
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise DailyMarketTechnicalParentV4QueryError(code) from exc
    if parsed.isoformat() != value:
        _fail(code)
    return parsed


def _validate_stock_codes(
    value: object,
    *,
    maximum: int,
    code: str,
    allow_empty: bool,
) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum or (not allow_empty and not value):
        _fail(code)
    if any(not isinstance(item, str) or not _STOCK_CODE_RE.fullmatch(item) for item in value):
        _fail(code)
    result = tuple(cast(list[str], value))
    if result != tuple(sorted(set(result))):
        _fail(code)
    return result


def _validate_source_clock(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping) or frozenset(value) != _CLOCK_KEYS:
        _fail("technical_parent_v4_query_source_clock_invalid")
    clock = dict(value)
    db_path = _canonical_absolute_path(
        clock.get("database_path"), "technical_parent_v4_query_source_clock_invalid"
    )
    if clock.get("source_id") != "sqlite.daily_prices":
        _fail("technical_parent_v4_query_source_clock_invalid")
    _require_sha(clock.get("schema_identity_sha256"), "technical_parent_v4_query_source_clock_invalid")
    _require_sha(clock.get("source_pin_sha256"), "technical_parent_v4_query_source_clock_invalid")
    raw_pins = clock.get("source_file_pin")
    if not isinstance(raw_pins, list) or len(raw_pins) != 2:
        _fail("technical_parent_v4_query_source_clock_invalid")
    pins: list[list[str | int]] = []
    for index, raw_pin in enumerate(raw_pins):
        if not isinstance(raw_pin, list) or not raw_pin or not isinstance(raw_pin[0], str):
            _fail("technical_parent_v4_query_source_clock_invalid")
        expected_path = db_path if index == 0 else f"{db_path}-wal"
        if raw_pin[0] != expected_path or len(raw_pin) not in ({5} if index == 0 else {1, 5}):
            _fail("technical_parent_v4_query_source_clock_invalid")
        if any(type(item) is not int or item < 0 for item in raw_pin[1:]):
            _fail("technical_parent_v4_query_source_clock_invalid")
        pins.append(cast(list[str | int], raw_pin))
    if _sha256_json(pins) != clock.get("source_pin_sha256"):
        _fail("technical_parent_v4_query_source_clock_pin_mismatch")
    decision_day = _parse_iso_date(
        clock.get("decision_date"), "technical_parent_v4_query_source_clock_invalid"
    )
    cutoff_text = clock.get("decision_cutoff")
    if not isinstance(cutoff_text, str):
        _fail("technical_parent_v4_query_source_clock_invalid")
    try:
        cutoff = datetime.fromisoformat(cutoff_text)
    except ValueError as exc:
        raise DailyMarketTechnicalParentV4QueryError(
            "technical_parent_v4_query_source_clock_invalid"
        ) from exc
    if (
        cutoff.utcoffset() is None
        or cutoff.isoformat() != cutoff_text
        or cutoff.astimezone(_TAIPEI).date() != decision_day
        or cutoff.astimezone(_TAIPEI).time() < _MINIMUM_CUTOFF
    ):
        _fail("technical_parent_v4_query_source_clock_invalid")
    if (
        not isinstance(clock.get("cutoff_guard_version"), str)
        or clock.get("source_available_at") is not None
        or clock.get("availability_status") != "unknown"
        or clock.get("historical_pit_eligible") is not False
    ):
        _fail("technical_parent_v4_query_source_clock_invalid")
    return clock


def _rule_state_filter_payload(value: object) -> dict[str, Any]:
    if isinstance(value, DailyMarketTechnicalRuleStateFilterV4):
        return value.to_dict()
    if not isinstance(value, Mapping) or frozenset(value) != _STATE_FILTER_KEYS:
        _fail("technical_parent_v4_query_state_filter_invalid")
    rule_key = value.get("rule_key")
    states = value.get("states")
    if not isinstance(rule_key, str) or not rule_key:
        _fail("technical_parent_v4_query_state_filter_invalid")
    if (
        not isinstance(states, list)
        or not states
        or any(item not in _STATE_ORDER for item in states)
        or tuple(states) != tuple(state for state in _STATE_ORDER if state in states)
        or len(set(states)) != len(states)
    ):
        _fail("technical_parent_v4_query_state_filter_invalid")
    return {"rule_key": rule_key, "states": list(states)}


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalRuleStateFilterV4:
    """一條 v4 方法規則可接受的已保存狀態集合。"""

    rule_key: str
    states: tuple[RuleState, ...]

    def __post_init__(self) -> None:
        _rule_state_filter_payload(self.to_dict())

    @classmethod
    def create(
        cls,
        rule_key: str,
        states: Sequence[RuleState],
    ) -> DailyMarketTechnicalRuleStateFilterV4:
        if isinstance(states, (str, bytes)):
            _fail("technical_parent_v4_query_state_filter_invalid")
        normalized = tuple(state for state in _STATE_ORDER if state in states)
        if len(normalized) != len(tuple(states)):
            _fail("technical_parent_v4_query_state_filter_invalid")
        return cls(rule_key=rule_key, states=cast(tuple[RuleState, ...], normalized))

    @classmethod
    def from_dict(cls, value: object) -> DailyMarketTechnicalRuleStateFilterV4:
        payload = _rule_state_filter_payload(value)
        return cls(
            rule_key=cast(str, payload["rule_key"]),
            states=cast(tuple[RuleState, ...], tuple(payload["states"])),
        )

    def to_dict(self) -> dict[str, object]:
        return {"rule_key": self.rule_key, "states": list(self.states)}


def _validate_sort_key(value: object, method_rule_keys: tuple[str, ...]) -> str:
    if not isinstance(value, str):
        _fail("technical_parent_v4_query_sort_key_invalid")
    if value in {"stock_code", "decision_date", "latest_feature_date", "raw_row_count"}:
        return value
    parts = value.split(".")
    if len(parts) == 2 and parts[0] in method_rule_keys and parts[1] in {
        "ratio", "numerator", "denominator",
    }:
        return value
    _fail("technical_parent_v4_query_sort_key_invalid")


def _query_body(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != "query_identity_sha256"}


def _validate_query_dict(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping) or frozenset(value) != _QUERY_KEYS:
        _fail("technical_parent_v4_query_fields_invalid")
    payload = dict(value)
    if payload.get("schema_version") != DAILY_MARKET_TECHNICAL_PARENT_V4_QUERY_SCHEMA:
        _fail("technical_parent_v4_query_schema_unsupported")
    _canonical_absolute_path(payload.get("parent_output_root"), "technical_parent_v4_query_root_invalid")
    if payload.get("child_repository_output_root") is not None:
        _canonical_absolute_path(
            payload.get("child_repository_output_root"),
            "technical_parent_v4_query_child_root_invalid",
        )
    for key in (
        "parent_plan_identity_sha256", "parent_plan_sha256",
        "parent_receipt_identity_sha256", "parent_receipt_sha256",
        "generation_identity_sha256", "cohort_identity_sha256",
        "source_clock_identity_sha256", "method_contracts_sha256",
    ):
        _require_sha(payload.get(key), "technical_parent_v4_query_pin_invalid")
    if payload.get("parent_status") not in _PARENT_STATUSES:
        _fail("technical_parent_v4_query_parent_status_invalid")
    decision_day = _parse_iso_date(
        payload.get("decision_date"), "technical_parent_v4_query_date_invalid"
    )
    _bounded_text(payload.get("universe_id"), 128, "technical_parent_v4_query_cohort_invalid")
    _bounded_text(payload.get("population_version"), 128, "technical_parent_v4_query_cohort_invalid")
    included = _validate_stock_codes(
        payload.get("included_stock_codes"),
        maximum=DAILY_MARKET_TECHNICAL_PARENT_V4_INCLUDED_LIMIT,
        code="technical_parent_v4_query_cohort_invalid",
        allow_empty=True,
    )
    excluded = _validate_stock_codes(
        payload.get("excluded_stock_codes"),
        maximum=DAILY_MARKET_TECHNICAL_PARENT_V4_EXCLUDED_LIMIT,
        code="technical_parent_v4_query_cohort_invalid",
        allow_empty=True,
    )
    if set(included).intersection(excluded):
        _fail("technical_parent_v4_query_cohort_overlap")
    declared = payload.get("declared_count")
    if type(declared) is not int or declared != len(included) + len(excluded):
        _fail("technical_parent_v4_query_declared_count_mismatch")
    reasons = payload.get("exclusion_reasons")
    if not isinstance(reasons, Mapping) or set(reasons) != set(excluded):
        _fail("technical_parent_v4_query_exclusion_reasons_mismatch")
    for reason in reasons.values():
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 512:
            _fail("technical_parent_v4_query_exclusion_reasons_mismatch")
    cohort_body = {
        "schema_version": "daily-market-technical-cohort.v4",
        "universe_id": payload["universe_id"],
        "population_version": payload["population_version"],
        "decision_date": decision_day.isoformat(),
        "included_stock_codes": list(included),
        "excluded_stock_codes": list(excluded),
        "exclusion_reasons": dict(sorted(cast(Mapping[str, str], reasons).items())),
        "declared_count": declared,
    }
    if _sha256_json(cohort_body) != payload.get("cohort_identity_sha256"):
        _fail("technical_parent_v4_query_cohort_identity_mismatch")
    expected_population_state = "included" if included else "all_excluded" if excluded else "empty"
    if payload.get("population_state") != expected_population_state:
        _fail("technical_parent_v4_query_population_state_mismatch")

    clock = _validate_source_clock(payload.get("source_clock"))
    if (
        clock["decision_date"] != decision_day.isoformat()
        or _sha256_json(clock) != payload.get("source_clock_identity_sha256")
    ):
        _fail("technical_parent_v4_query_source_clock_identity_mismatch")
    if payload.get("coverage_scope") != DAILY_MARKET_TECHNICAL_PARENT_V4_COVERAGE_SCOPE:
        _fail("technical_parent_v4_query_coverage_invalid")
    if (
        payload.get("aggregation_scope") != "single_parent_segment"
        or payload.get("full_n_aggregation") is not False
    ):
        _fail("technical_parent_v4_query_aggregation_scope_invalid")
    if (
        type(payload.get("included_stock_limit")) is not int
        or payload["included_stock_limit"] != DAILY_MARKET_TECHNICAL_PARENT_V4_INCLUDED_LIMIT
        or type(payload.get("excluded_stock_limit")) is not int
        or payload["excluded_stock_limit"] != DAILY_MARKET_TECHNICAL_PARENT_V4_EXCLUDED_LIMIT
        or payload.get("full_market_claim") is not False
    ):
        _fail("technical_parent_v4_query_coverage_invalid")

    method_keys_raw = payload.get("method_rule_keys")
    if (
        not isinstance(method_keys_raw, list)
        or not method_keys_raw
        or len(method_keys_raw) > 16
        or any(not isinstance(item, str) or not item for item in method_keys_raw)
        or len(set(method_keys_raw)) != len(method_keys_raw)
    ):
        _fail("technical_parent_v4_query_method_rules_invalid")
    method_rule_keys = tuple(cast(list[str], method_keys_raw))
    filters_raw = payload.get("state_filters")
    if not isinstance(filters_raw, list) or len(filters_raw) > len(method_rule_keys):
        _fail("technical_parent_v4_query_state_filter_invalid")
    filters = tuple(_rule_state_filter_payload(item) for item in filters_raw)
    filter_keys = tuple(cast(str, item["rule_key"]) for item in filters)
    if (
        len(set(filter_keys)) != len(filter_keys)
        or any(key not in method_rule_keys for key in filter_keys)
    ):
        _fail("technical_parent_v4_query_state_filter_invalid")
    if payload.get("combine_mode") not in {"AND", "OR"}:
        _fail("technical_parent_v4_query_combine_mode_invalid")
    stock_filter = _validate_stock_codes(
        payload.get("stock_filter"),
        maximum=DAILY_MARKET_TECHNICAL_PARENT_V4_INCLUDED_LIMIT,
        code="technical_parent_v4_query_stock_filter_invalid",
        allow_empty=True,
    )
    _validate_sort_key(payload.get("sort_key"), method_rule_keys)
    if type(payload.get("descending")) is not bool:
        _fail("technical_parent_v4_query_sort_direction_invalid")
    page_index = payload.get("page_index")
    page_size = payload.get("page_size")
    if (
        type(page_index) is not int
        or not 0 <= page_index <= DAILY_MARKET_TECHNICAL_PARENT_V4_MAX_PAGE_INDEX
        or type(page_size) is not int
        or not 1 <= page_size <= DAILY_MARKET_TECHNICAL_PARENT_V4_QUERY_MAX_PAGE_SIZE
    ):
        _fail("technical_parent_v4_query_page_invalid")
    expected_generation = generation_identity_sha256(
        cohort_identity_sha256=cast(str, payload["cohort_identity_sha256"]),
        source_clock_identity_sha256=cast(str, payload["source_clock_identity_sha256"]),
        method_contract_sha256=cast(str, payload["method_contracts_sha256"]),
    )
    if payload.get("generation_identity_sha256") != expected_generation:
        _fail("technical_parent_v4_query_generation_identity_mismatch")
    query_hash = _require_sha(
        payload.get("query_identity_sha256"), "technical_parent_v4_query_identity_invalid"
    )
    if _sha256_json(_query_body(payload)) != query_hash:
        _fail("technical_parent_v4_query_identity_mismatch")
    payload["decision_date"] = decision_day.isoformat()
    payload["included_stock_codes"] = list(included)
    payload["excluded_stock_codes"] = list(excluded)
    payload["exclusion_reasons"] = dict(sorted(cast(Mapping[str, str], reasons).items()))
    payload["method_rule_keys"] = list(method_rule_keys)
    payload["state_filters"] = list(filters)
    payload["stock_filter"] = list(stock_filter)
    return payload


def _package_query_payload(
    *,
    package: Mapping[str, Any],
    parent_output_root: str | Path,
    rule_state_filters: Sequence[DailyMarketTechnicalRuleStateFilterV4],
    combine_mode: CombineMode,
    stock_filter: Sequence[str],
    sort_key: str,
    descending: bool,
    page_index: int,
    page_size: int,
) -> dict[str, Any]:
    plan = package.get("plan")
    receipt = package.get("receipt")
    if not isinstance(plan, Mapping) or not isinstance(receipt, Mapping):
        _fail("technical_parent_v4_query_parent_invalid")
    cohort = plan.get("cohort")
    clock = plan.get("source_clock")
    method = plan.get("method_contracts")
    if not isinstance(cohort, Mapping) or not isinstance(clock, Mapping) or not isinstance(method, Mapping):
        _fail("technical_parent_v4_query_parent_invalid")
    raw_rules = method.get("rules")
    if not isinstance(raw_rules, list):
        _fail("technical_parent_v4_query_method_rules_invalid")
    method_rule_keys: list[str] = []
    for item in raw_rules:
        if not isinstance(item, Mapping) or not isinstance(item.get("key"), str):
            _fail("technical_parent_v4_query_method_rules_invalid")
        method_rule_keys.append(cast(str, item["key"]))
    if len(method_rule_keys) != 5 or len(set(method_rule_keys)) != 5:
        _fail("technical_parent_v4_query_method_rules_unsupported")
    filters: list[dict[str, Any]] = []
    if isinstance(rule_state_filters, (str, bytes)):
        _fail("technical_parent_v4_query_state_filter_invalid")
    for item in rule_state_filters:
        if not isinstance(item, DailyMarketTechnicalRuleStateFilterV4):
            _fail("technical_parent_v4_query_state_filter_invalid")
        filter_payload = item.to_dict()
        if item.rule_key not in method_rule_keys:
            _fail("technical_parent_v4_query_state_filter_invalid")
        filters.append(filter_payload)
    if len({item["rule_key"] for item in filters}) != len(filters):
        _fail("technical_parent_v4_query_state_filter_invalid")
    if isinstance(stock_filter, (str, bytes)):
        _fail("technical_parent_v4_query_stock_filter_invalid")
    raw_stock_filter = tuple(stock_filter)
    if any(
        not isinstance(code, str) or not _STOCK_CODE_RE.fullmatch(code)
        for code in raw_stock_filter
    ):
        _fail("technical_parent_v4_query_stock_filter_invalid")
    normalized_stock_filter = tuple(sorted(raw_stock_filter))
    if (
        len(normalized_stock_filter) != len(raw_stock_filter)
        or tuple(raw_stock_filter) != normalized_stock_filter
    ):
        _fail("technical_parent_v4_query_stock_filter_invalid")
    cohort_payload = {
        "schema_version": cohort["schema_version"],
        "universe_id": cohort["universe_id"],
        "population_version": cohort["population_version"],
        "decision_date": cohort["decision_date"],
        "included_stock_codes": cohort["included_stock_codes"],
        "excluded_stock_codes": cohort["excluded_stock_codes"],
        "exclusion_reasons": cohort["exclusion_reasons"],
        "declared_count": cohort["declared_count"],
        "cohort_identity_sha256": cohort["cohort_identity_sha256"],
    }
    root = package.get("parent_output_root")
    if root is None:
        root = parent_output_root
    if str(Path(parent_output_root)) != str(Path(root)):
        _fail("technical_parent_v4_query_root_mismatch")
    plan_sha = package.get("plan_sha256")
    receipt_sha = package.get("receipt_sha256")
    plan_identity = plan.get("parent_plan_identity_sha256")
    receipt_identity = receipt.get("receipt_identity_sha256")
    for value in (plan_sha, receipt_sha, plan_identity, receipt_identity):
        _require_sha(value, "technical_parent_v4_query_parent_pin_invalid")
    clock_sha = plan.get("source_clock_identity_sha256")
    method_sha = plan.get("method_contracts_sha256")
    cohort_sha = cohort.get("cohort_identity_sha256")
    generation_sha = plan.get("generation_identity_sha256")
    status = receipt.get("status")
    if status not in _PARENT_STATUSES:
        _fail("technical_parent_v4_query_parent_status_invalid")
    clock_payload = _validate_source_clock(clock)
    root_text = _canonical_absolute_path(
        str(root), "technical_parent_v4_query_root_invalid"
    )
    body: dict[str, Any] = {
        "schema_version": DAILY_MARKET_TECHNICAL_PARENT_V4_QUERY_SCHEMA,
        "parent_output_root": root_text,
        "parent_plan_identity_sha256": plan_identity,
        "parent_plan_sha256": plan_sha,
        "parent_receipt_identity_sha256": receipt_identity,
        "parent_receipt_sha256": receipt_sha,
        "parent_status": status,
        "child_repository_output_root": receipt.get("repository_output_root"),
        "generation_identity_sha256": generation_sha,
        "cohort_identity_sha256": cohort_sha,
        "universe_id": cohort_payload["universe_id"],
        "population_version": cohort_payload["population_version"],
        "decision_date": cohort_payload["decision_date"],
        "population_state": plan.get("population_state"),
        "declared_count": cohort_payload["declared_count"],
        "included_stock_codes": cohort_payload["included_stock_codes"],
        "excluded_stock_codes": cohort_payload["excluded_stock_codes"],
        "exclusion_reasons": cohort_payload["exclusion_reasons"],
        "source_clock": clock_payload,
        "source_clock_identity_sha256": clock_sha,
        "method_contracts_sha256": method_sha,
        "method_rule_keys": method_rule_keys,
        "coverage_scope": DAILY_MARKET_TECHNICAL_PARENT_V4_COVERAGE_SCOPE,
        "aggregation_scope": "single_parent_segment",
        "included_stock_limit": DAILY_MARKET_TECHNICAL_PARENT_V4_INCLUDED_LIMIT,
        "excluded_stock_limit": DAILY_MARKET_TECHNICAL_PARENT_V4_EXCLUDED_LIMIT,
        "full_market_claim": False,
        "full_n_aggregation": False,
        "state_filters": filters,
        "combine_mode": combine_mode,
        "stock_filter": list(normalized_stock_filter),
        "sort_key": sort_key,
        "descending": descending,
        "page_index": page_index,
        "page_size": page_size,
    }
    body["query_identity_sha256"] = _sha256_json(body)
    _validate_query_dict(body)
    return body


def _read_parent_package(
    *,
    parent_output_root: str | Path,
    plan_identity_sha256: str,
    plan_sha256: str,
    receipt_identity_sha256: str,
    receipt_sha256: str,
) -> tuple[Path, dict[str, Any]]:
    try:
        reader = BoundedDailyMarketTechnicalParentCaptureWriterV4(
            parent_output_root,
            read_only=True,
        )
        package = reader.read(
            plan_identity_sha256,
            receipt_identity_sha256,
            expected_receipt_sha256=receipt_sha256,
            expected_plan_sha256=plan_sha256,
        )
    except (
        TechnicalParentCaptureV4Error,
        DailyMarketTechnicalSnapshotV4RepositoryError,
        OSError,
    ) as exc:
        reason = getattr(exc, "code", "technical_parent_v4_query_parent_read_failed")
        raise DailyMarketTechnicalParentV4QueryError(str(reason), str(exc)) from exc
    if not isinstance(package, dict):
        _fail("technical_parent_v4_query_parent_invalid")
    return reader.output_root, package


def _query_matches_package(
    query: DailyMarketTechnicalParentV4Query,
    *,
    root: Path,
    package: Mapping[str, Any],
) -> None:
    plan = package.get("plan")
    receipt = package.get("receipt")
    if not isinstance(plan, Mapping) or not isinstance(receipt, Mapping):
        _fail("technical_parent_v4_query_parent_invalid")
    cohort = plan.get("cohort")
    clock = plan.get("source_clock")
    method = plan.get("method_contracts")
    if not isinstance(cohort, Mapping) or not isinstance(clock, Mapping) or not isinstance(method, Mapping):
        _fail("technical_parent_v4_query_parent_invalid")
    rules = method.get("rules")
    if not isinstance(rules, list):
        _fail("technical_parent_v4_query_method_rules_invalid")
    current_rule_keys = tuple(
        cast(str, rule["key"])
        for rule in rules
        if isinstance(rule, Mapping) and isinstance(rule.get("key"), str)
    )
    if (
        str(root) != query.parent_output_root
        or package.get("plan_sha256") != query.parent_plan_sha256
        or package.get("receipt_sha256") != query.parent_receipt_sha256
        or plan.get("parent_plan_identity_sha256") != query.parent_plan_identity_sha256
        or receipt.get("receipt_identity_sha256") != query.parent_receipt_identity_sha256
        or receipt.get("status") != query.parent_status
        or receipt.get("repository_output_root") != query.child_repository_output_root
        or plan.get("generation_identity_sha256") != query.generation_identity_sha256
        or cohort.get("cohort_identity_sha256") != query.cohort_identity_sha256
        or cohort.get("universe_id") != query.universe_id
        or cohort.get("population_version") != query.population_version
        or cohort.get("decision_date") != query.decision_date.isoformat()
        or plan.get("population_state") != query.population_state
        or cohort.get("declared_count") != query.declared_count
        or tuple(cohort.get("included_stock_codes", ())) != query.included_stock_codes
        or tuple(cohort.get("excluded_stock_codes", ())) != query.excluded_stock_codes
        or tuple(sorted(cast(Mapping[str, str], cohort.get("exclusion_reasons", {})).items()))
        != query.exclusion_reasons
        or _canonical_json_bytes(clock).decode("utf-8") != query.source_clock_json
        or plan.get("source_clock_identity_sha256") != query.source_clock_identity_sha256
        or plan.get("method_contracts_sha256") != query.method_contracts_sha256
        or current_rule_keys != query.method_rule_keys
    ):
        _fail("technical_parent_v4_query_source_identity_mismatch")


def _load_verified_snapshots(
    package: Mapping[str, Any],
    *,
    cancel_callback: Callable[[], bool] | None = None,
) -> tuple[DailyMarketTechnicalFeatureSnapshotV4, ...]:
    plan = package.get("plan")
    receipt = package.get("receipt")
    if not isinstance(plan, Mapping) or not isinstance(receipt, Mapping):
        _fail("technical_parent_v4_query_parent_invalid")
    child_items = receipt.get("batch_artifacts")
    if not isinstance(child_items, list):
        _fail("technical_parent_v4_query_parent_invalid")
    child_root_value = receipt.get("repository_output_root")
    if not child_items:
        if child_root_value is not None:
            _fail("technical_parent_v4_query_child_root_mismatch")
        return ()
    if not isinstance(child_root_value, str):
        _fail("technical_parent_v4_query_child_root_missing")
    try:
        repository = DailyMarketTechnicalSnapshotV4Repository(child_root_value)
    except DailyMarketTechnicalSnapshotV4RepositoryError as exc:
        raise DailyMarketTechnicalParentV4QueryError(exc.code, str(exc)) from exc
    cohort = plan.get("cohort")
    if not isinstance(cohort, Mapping):
        _fail("technical_parent_v4_query_parent_invalid")
    decision_day = _parse_iso_date(
        cohort.get("decision_date"), "technical_parent_v4_query_date_invalid"
    )
    snapshots: list[DailyMarketTechnicalFeatureSnapshotV4] = []
    seen: set[str] = set()
    for child in child_items:
        if _is_cancelled(cancel_callback):
            _fail("technical_parent_v4_query_cancelled")
        if not isinstance(child, Mapping):
            _fail("technical_parent_v4_query_parent_invalid")
        try:
            verified = repository.read_exact(
                cast(str, child.get("manifest_path")),
                expected_manifest_sha256=cast(str, child.get("manifest_sha256")),
                expected_cohort_identity_sha256=cast(str, cohort.get("cohort_identity_sha256")),
                expected_source_clock_sha256=cast(str, plan.get("source_clock_identity_sha256")),
                expected_method_contract_sha256=cast(str, plan.get("method_contracts_sha256")),
                expected_decision_date=decision_day,
            )
        except DailyMarketTechnicalSnapshotV4RepositoryError as exc:
            raise DailyMarketTechnicalParentV4QueryError(exc.code, str(exc)) from exc
        if _is_cancelled(cancel_callback):
            _fail("technical_parent_v4_query_cancelled")
        if verified.generation_identity_sha256 != plan.get("generation_identity_sha256"):
            _fail("technical_parent_v4_query_generation_identity_mismatch")
        for snapshot in verified.snapshots:
            if snapshot.stock_code in seen:
                _fail("technical_parent_v4_query_duplicate_stock")
            seen.add(snapshot.stock_code)
            if snapshot.stock_code != snapshot.stock_code.upper():
                _fail("technical_parent_v4_query_stock_code_invalid")
            if any(
                (rule.feature_date is not None and rule.feature_date > decision_day)
                or (rule.previous_feature_date is not None and rule.previous_feature_date > decision_day)
                for rule in snapshot.rules
            ):
                _fail("technical_parent_v4_query_future_rule_date")
            snapshots.append(snapshot)
    included_codes = tuple(cast(Sequence[str], cohort.get("included_stock_codes", ())))
    expected_prefix = included_codes[:len(snapshots)]
    if tuple(snapshot.stock_code for snapshot in snapshots) != expected_prefix:
        _fail("technical_parent_v4_query_processed_prefix_invalid")
    return tuple(snapshots)


def _rule_by_key(
    row: DailyMarketTechnicalParentV4Row,
    rule_key: str,
) -> DailyMarketTechnicalRuleEvidenceV4:
    for rule in row.rules:
        if rule.key == rule_key:
            return rule
    _fail("technical_parent_v4_query_rule_missing")


def _row_sort_value(
    row: DailyMarketTechnicalParentV4Row,
    sort_key: str,
) -> str | int | date | Decimal | None:
    if sort_key == "stock_code":
        return row.stock_code
    if sort_key == "decision_date":
        return row.decision_date
    if sort_key == "latest_feature_date":
        return row.latest_feature_date
    if sort_key == "raw_row_count":
        return row.raw_row_count
    rule_key, field_name = sort_key.rsplit(".", 1)
    evidence = _rule_by_key(row, rule_key)
    return cast(Decimal | None, getattr(evidence, field_name))


def _row_matches_state_filters(
    row: DailyMarketTechnicalParentV4Row,
    filters: tuple[DailyMarketTechnicalRuleStateFilterV4, ...],
    combine_mode: CombineMode,
) -> bool:
    if not filters:
        return True
    outcomes = tuple(
        _rule_by_key(row, item.rule_key).state in item.states
        for item in filters
    )
    return all(outcomes) if combine_mode == "AND" else any(outcomes)


def _make_row(
    snapshot: DailyMarketTechnicalFeatureSnapshotV4,
) -> DailyMarketTechnicalParentV4Row:
    return DailyMarketTechnicalParentV4Row(
        stock_code=snapshot.stock_code,
        decision_date=snapshot.decision_date,
        snapshot_identity_sha256=snapshot.snapshot_identity_sha256,
        source_identity=snapshot.source_identity,
        raw_row_count=len(snapshot.rows),
        observed_prefix_contiguous=snapshot.observed_prefix_contiguous,
        latest_feature_date=(
            snapshot.current_session.feature_date
            if snapshot.current_session is not None
            else None
        ),
        rules=snapshot.rules,
    )


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalParentV4Row:
    """單一已處理股票的五條原始 v4 規則與來源列數。"""

    stock_code: str
    decision_date: date
    snapshot_identity_sha256: str
    source_identity: str
    raw_row_count: int
    observed_prefix_contiguous: bool
    latest_feature_date: date | None
    rules: tuple[DailyMarketTechnicalRuleEvidenceV4, ...]

    @property
    def has_missing_data(self) -> bool:
        return self.raw_row_count == 0

    @property
    def has_unknown_rules(self) -> bool:
        return any(rule.state == "unknown" for rule in self.rules)

    def rule(self, rule_key: str) -> DailyMarketTechnicalRuleEvidenceV4:
        return _rule_by_key(self, rule_key)

    def to_dict(self) -> dict[str, object]:
        return {
            "stock_code": self.stock_code,
            "decision_date": self.decision_date.isoformat(),
            "snapshot_identity_sha256": self.snapshot_identity_sha256,
            "source_identity": self.source_identity,
            "raw_row_count": self.raw_row_count,
            "observed_prefix_contiguous": self.observed_prefix_contiguous,
            "latest_feature_date": (
                self.latest_feature_date.isoformat() if self.latest_feature_date else None
            ),
            "rules": [item.to_dict() for item in self.rules],
            "has_missing_data": self.has_missing_data,
        }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalParentV4Query:
    """完整固定 parent、來源與呈現條件的 canonical 查詢描述。"""

    parent_output_root: str
    parent_plan_identity_sha256: str
    parent_plan_sha256: str
    parent_receipt_identity_sha256: str
    parent_receipt_sha256: str
    parent_status: ParentStatus
    child_repository_output_root: str | None
    generation_identity_sha256: str
    cohort_identity_sha256: str
    universe_id: str
    population_version: str
    decision_date: date
    population_state: Literal["included", "all_excluded", "empty"]
    declared_count: int
    included_stock_codes: tuple[str, ...]
    excluded_stock_codes: tuple[str, ...]
    exclusion_reasons: tuple[tuple[str, str], ...]
    source_clock_json: str
    source_clock_identity_sha256: str
    method_contracts_sha256: str
    method_rule_keys: tuple[str, ...]
    rule_state_filters: tuple[DailyMarketTechnicalRuleStateFilterV4, ...]
    combine_mode: CombineMode
    stock_filter: tuple[str, ...]
    sort_key: str
    descending: bool
    page_index: int
    page_size: int
    query_identity_sha256: str

    @property
    def coverage_scope(self) -> str:
        return DAILY_MARKET_TECHNICAL_PARENT_V4_COVERAGE_SCOPE

    @property
    def aggregation_scope(self) -> str:
        return "single_parent_segment"

    @property
    def full_n_aggregation(self) -> bool:
        return False

    @property
    def full_market_claim(self) -> bool:
        return False

    def __post_init__(self) -> None:
        _validate_query_dict(self.to_dict())

    @classmethod
    def create(
        cls,
        *,
        parent_output_root: str | Path,
        parent_plan_identity_sha256: str,
        parent_plan_sha256: str,
        parent_receipt_identity_sha256: str,
        parent_receipt_sha256: str,
        rule_state_filters: Sequence[DailyMarketTechnicalRuleStateFilterV4] = (),
        combine_mode: CombineMode = "AND",
        stock_filter: Sequence[str] = (),
        sort_key: str = "stock_code",
        descending: bool = False,
        page_index: int = 0,
        page_size: int = 50,
    ) -> DailyMarketTechnicalParentV4Query:
        """以明示的 parent/receipt pins 驗證來源後建立不可變查詢。"""

        if combine_mode not in {"AND", "OR"} or type(descending) is not bool:
            _fail("technical_parent_v4_query_conditions_invalid")
        root, package = _read_parent_package(
            parent_output_root=parent_output_root,
            plan_identity_sha256=parent_plan_identity_sha256,
            plan_sha256=parent_plan_sha256,
            receipt_identity_sha256=parent_receipt_identity_sha256,
            receipt_sha256=parent_receipt_sha256,
        )
        payload = _package_query_payload(
            package=package,
            parent_output_root=root,
            rule_state_filters=rule_state_filters,
            combine_mode=combine_mode,
            stock_filter=stock_filter,
            sort_key=sort_key,
            descending=descending,
            page_index=page_index,
            page_size=page_size,
        )
        return cls.from_dict(payload)

    @classmethod
    def from_dict(cls, value: object) -> DailyMarketTechnicalParentV4Query:
        payload = _validate_query_dict(value)
        clock_json = _canonical_json_bytes(payload["source_clock"]).decode("utf-8")
        return cls(
            parent_output_root=cast(str, payload["parent_output_root"]),
            parent_plan_identity_sha256=cast(str, payload["parent_plan_identity_sha256"]),
            parent_plan_sha256=cast(str, payload["parent_plan_sha256"]),
            parent_receipt_identity_sha256=cast(str, payload["parent_receipt_identity_sha256"]),
            parent_receipt_sha256=cast(str, payload["parent_receipt_sha256"]),
            parent_status=cast(ParentStatus, payload["parent_status"]),
            child_repository_output_root=cast(str | None, payload["child_repository_output_root"]),
            generation_identity_sha256=cast(str, payload["generation_identity_sha256"]),
            cohort_identity_sha256=cast(str, payload["cohort_identity_sha256"]),
            universe_id=cast(str, payload["universe_id"]),
            population_version=cast(str, payload["population_version"]),
            decision_date=_parse_iso_date(payload["decision_date"], "technical_parent_v4_query_date_invalid"),
            population_state=cast(Literal["included", "all_excluded", "empty"], payload["population_state"]),
            declared_count=cast(int, payload["declared_count"]),
            included_stock_codes=cast(tuple[str, ...], tuple(payload["included_stock_codes"])),
            excluded_stock_codes=cast(tuple[str, ...], tuple(payload["excluded_stock_codes"])),
            exclusion_reasons=tuple(sorted(cast(Mapping[str, str], payload["exclusion_reasons"]).items())),
            source_clock_json=clock_json,
            source_clock_identity_sha256=cast(str, payload["source_clock_identity_sha256"]),
            method_contracts_sha256=cast(str, payload["method_contracts_sha256"]),
            method_rule_keys=cast(tuple[str, ...], tuple(payload["method_rule_keys"])),
            rule_state_filters=tuple(
                DailyMarketTechnicalRuleStateFilterV4.from_dict(item)
                for item in cast(Sequence[object], payload["state_filters"])
            ),
            combine_mode=cast(CombineMode, payload["combine_mode"]),
            stock_filter=cast(tuple[str, ...], tuple(payload["stock_filter"])),
            sort_key=cast(str, payload["sort_key"]),
            descending=cast(bool, payload["descending"]),
            page_index=cast(int, payload["page_index"]),
            page_size=cast(int, payload["page_size"]),
            query_identity_sha256=cast(str, payload["query_identity_sha256"]),
        )

    @classmethod
    def from_json(cls, raw: bytes | str) -> DailyMarketTechnicalParentV4Query:
        return cls.from_dict(_parse_json(raw))

    @property
    def source_clock(self) -> dict[str, Any]:
        value = json.loads(self.source_clock_json)
        if not isinstance(value, dict):
            _fail("technical_parent_v4_query_source_clock_invalid")
        return value

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": DAILY_MARKET_TECHNICAL_PARENT_V4_QUERY_SCHEMA,
            "parent_output_root": self.parent_output_root,
            "parent_plan_identity_sha256": self.parent_plan_identity_sha256,
            "parent_plan_sha256": self.parent_plan_sha256,
            "parent_receipt_identity_sha256": self.parent_receipt_identity_sha256,
            "parent_receipt_sha256": self.parent_receipt_sha256,
            "parent_status": self.parent_status,
            "child_repository_output_root": self.child_repository_output_root,
            "generation_identity_sha256": self.generation_identity_sha256,
            "cohort_identity_sha256": self.cohort_identity_sha256,
            "universe_id": self.universe_id,
            "population_version": self.population_version,
            "decision_date": self.decision_date.isoformat(),
            "population_state": self.population_state,
            "declared_count": self.declared_count,
            "included_stock_codes": list(self.included_stock_codes),
            "excluded_stock_codes": list(self.excluded_stock_codes),
            "exclusion_reasons": dict(self.exclusion_reasons),
            "source_clock": self.source_clock,
            "source_clock_identity_sha256": self.source_clock_identity_sha256,
            "method_contracts_sha256": self.method_contracts_sha256,
            "method_rule_keys": list(self.method_rule_keys),
            "coverage_scope": DAILY_MARKET_TECHNICAL_PARENT_V4_COVERAGE_SCOPE,
            "aggregation_scope": "single_parent_segment",
            "included_stock_limit": DAILY_MARKET_TECHNICAL_PARENT_V4_INCLUDED_LIMIT,
            "excluded_stock_limit": DAILY_MARKET_TECHNICAL_PARENT_V4_EXCLUDED_LIMIT,
            "full_market_claim": False,
            "full_n_aggregation": False,
            "state_filters": [item.to_dict() for item in self.rule_state_filters],
            "combine_mode": self.combine_mode,
            "stock_filter": list(self.stock_filter),
            "sort_key": self.sort_key,
            "descending": self.descending,
            "page_index": self.page_index,
            "page_size": self.page_size,
            "query_identity_sha256": self.query_identity_sha256,
        }

    def to_json(self) -> str:
        return _canonical_json_bytes(self.to_dict()).decode("utf-8")


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalParentV4Page:
    """固定 parent 的一頁結果與完整母體計數。"""

    query: DailyMarketTechnicalParentV4Query
    rows: tuple[DailyMarketTechnicalParentV4Row, ...]
    declared_count: int
    included_count: int
    excluded_count: int
    processed_count: int
    pending_count: int
    missing_data_count: int
    unknown_rule_count: int
    matching_count: int
    page_count: int
    pending_stock_codes: tuple[str, ...]
    missing_data_stock_codes: tuple[str, ...]
    unknown_rule_stock_codes: tuple[str, ...]
    exclusion_reasons: tuple[tuple[str, str], ...]
    parent_status: ParentStatus

    @property
    def is_complete(self) -> bool:
        return self.parent_status == "complete" and self.pending_count == 0

    @property
    def coverage_scope(self) -> str:
        return DAILY_MARKET_TECHNICAL_PARENT_V4_COVERAGE_SCOPE

    @property
    def aggregation_scope(self) -> str:
        return "single_parent_segment"

    @property
    def full_market_claim(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query.to_dict(),
            "coverage_scope": self.coverage_scope,
            "aggregation_scope": self.aggregation_scope,
            "full_market_claim": False,
            "full_n_aggregation": False,
            "parent_status": self.parent_status,
            "is_complete": self.is_complete,
            "counts": {
                "declared": self.declared_count,
                "included": self.included_count,
                "excluded": self.excluded_count,
                "processed": self.processed_count,
                "pending": self.pending_count,
                "missing_data": self.missing_data_count,
                "unknown_rules": self.unknown_rule_count,
                "matching": self.matching_count,
                "pages": self.page_count,
            },
            "page_index": self.query.page_index,
            "page_size": self.query.page_size,
            "pending_stock_codes": list(self.pending_stock_codes),
            "missing_data_stock_codes": list(self.missing_data_stock_codes),
            "unknown_rule_stock_codes": list(self.unknown_rule_stock_codes),
            "exclusion_reasons": dict(self.exclusion_reasons),
            "rows": [item.to_dict() for item in self.rows],
        }


def _is_cancelled(callback: Callable[[], bool] | None) -> bool:
    if callback is None:
        return False
    try:
        value = callback()
    except Exception as exc:
        raise DailyMarketTechnicalParentV4QueryError(
            "technical_parent_v4_query_cancel_check_failed", str(exc)
        ) from exc
    if type(value) is not bool:
        _fail("technical_parent_v4_query_cancel_callback_invalid")
    return value


def read_daily_market_technical_parent_v4_page(
    query: DailyMarketTechnicalParentV4Query | bytes | str,
    *,
    cancel_callback: Callable[[], bool] | None = None,
) -> DailyMarketTechnicalParentV4Page:
    """重新驗證 query 固定的 parent/receipt/child refs，再由保存資料分頁。"""

    if isinstance(query, (bytes, str)):
        query = DailyMarketTechnicalParentV4Query.from_json(query)
    if not isinstance(query, DailyMarketTechnicalParentV4Query):
        _fail("technical_parent_v4_query_invalid")
    if _is_cancelled(cancel_callback):
        _fail("technical_parent_v4_query_cancelled")
    root, package = _read_parent_package(
        parent_output_root=query.parent_output_root,
        plan_identity_sha256=query.parent_plan_identity_sha256,
        plan_sha256=query.parent_plan_sha256,
        receipt_identity_sha256=query.parent_receipt_identity_sha256,
        receipt_sha256=query.parent_receipt_sha256,
    )
    _query_matches_package(query, root=root, package=package)
    snapshots: list[DailyMarketTechnicalFeatureSnapshotV4] = []
    snapshots.extend(_load_verified_snapshots(package, cancel_callback=cancel_callback))
    if _is_cancelled(cancel_callback):
        _fail("technical_parent_v4_query_cancelled")

    rows = tuple(_make_row(snapshot) for snapshot in snapshots)
    included_codes = query.included_stock_codes
    processed_codes = tuple(row.stock_code for row in rows)
    if processed_codes != included_codes[:len(processed_codes)]:
        _fail("technical_parent_v4_query_processed_prefix_invalid")
    processed_set = set(processed_codes)
    pending_codes = tuple(code for code in included_codes if code not in processed_set)
    missing_codes = tuple(row.stock_code for row in rows if row.has_missing_data)
    unknown_rule_codes = tuple(row.stock_code for row in rows if row.has_unknown_rules)
    selected = [
        row for row in rows
        if (not query.stock_filter or row.stock_code in query.stock_filter)
        and _row_matches_state_filters(
            row,
            query.rule_state_filters,
            query.combine_mode,
        )
    ]
    selected.sort(key=lambda row: row.stock_code)
    missing_sort_values = [
        row for row in selected if _row_sort_value(row, query.sort_key) is None
    ]
    valued_rows = [
        row for row in selected if _row_sort_value(row, query.sort_key) is not None
    ]
    valued_rows.sort(
        key=lambda row: cast(str | int | date | Decimal, _row_sort_value(row, query.sort_key)),
        reverse=query.descending,
    )
    missing_sort_values.sort(key=lambda row: row.stock_code)
    ordered = valued_rows + missing_sort_values
    matching_count = len(ordered)
    page_count = (matching_count + query.page_size - 1) // query.page_size
    offset = query.page_index * query.page_size
    page_rows = tuple(ordered[offset:offset + query.page_size])
    pending_count = len(pending_codes)
    if query.parent_status == "complete" and pending_count != 0:
        _fail("technical_parent_v4_query_false_complete")
    return DailyMarketTechnicalParentV4Page(
        query=query,
        rows=page_rows,
        declared_count=query.declared_count,
        included_count=len(query.included_stock_codes),
        excluded_count=len(query.excluded_stock_codes),
        processed_count=len(rows),
        pending_count=pending_count,
        missing_data_count=len(missing_codes),
        unknown_rule_count=len(unknown_rule_codes),
        matching_count=matching_count,
        page_count=page_count,
        pending_stock_codes=pending_codes,
        missing_data_stock_codes=missing_codes,
        unknown_rule_stock_codes=unknown_rule_codes,
        exclusion_reasons=query.exclusion_reasons,
        parent_status=query.parent_status,
    )
