"""以固定 full-N v4 store 做全域、唯讀的技術規則查詢。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Literal, NoReturn, cast

from app_module import daily_market_technical_parent_v4_query as _parent_query_module
from app_module.daily_market_technical_parent_v4_query import (
    DailyMarketTechnicalParentV4Row,
    DailyMarketTechnicalRuleStateFilterV4,
    _row_matches_state_filters,
    _row_sort_value,
)
from app_module.daily_market_technical_snapshot_v4_repository import (
    DailyMarketTechnicalBatchArtifactV4,
    DailyMarketTechnicalSnapshotV4Repository,
    DailyMarketTechnicalSnapshotV4RepositoryError,
)
from app_module.rule_research_technical_parent_capture_v4 import (
    DailyMarketTechnicalParentCaptureV4VerifiedRead,
)
from app_module.daily_market_technical_universe_v4_store import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS,
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_SEGMENTS,
    DailyMarketTechnicalUniverseV4Counts,
    DailyMarketTechnicalUniverseV4StoreError,
    DailyMarketTechnicalUniverseV4StoreReader,
    DailyMarketTechnicalUniverseV4VerifiedState,
)


DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_SCHEMA = (
    "daily-market-technical-universe-query.v4"
)
DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_BYTES = 8 * 1024 * 1024
DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_PAGE_SIZE = 256
DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_PAGE_INDEX = 1_000_000
DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_SCOPE = "declared_full_universe_v4"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STOCK_CODE_RE = re.compile(r"^[A-Z0-9]{1,16}$")
_RULE_STATE_ORDER = ("match", "no_match", "unknown")
_COMBINE_MODES = frozenset({"AND", "OR"})
_STATUSES = frozenset({"partial", "cancelled", "failed", "complete"})
_QUERY_KEYS = frozenset({
    "schema_version",
    "store_output_root",
    "generation_identity_sha256",
    "plan_identity_sha256",
    "plan_sha256",
    "receipt_identity_sha256",
    "receipt_sha256",
    "receipt_status",
    "cohort_identity_sha256",
    "source_clock_identity_sha256",
    "method_contracts_sha256",
    "universe_id",
    "population_version",
    "decision_date",
    "declared_count",
    "included_count",
    "excluded_count",
    "segment_count",
    "counts",
    "method_rule_keys",
    "state_filters",
    "combine_mode",
    "stock_filter",
    "sort_key",
    "descending",
    "page_index",
    "page_size",
    "query_identity_sha256",
})
_STATE_FILTER_KEYS = frozenset({"rule_key", "states"})

RuleState = Literal["match", "no_match", "unknown"]
CombineMode = Literal["AND", "OR"]
StoreStatus = Literal["partial", "cancelled", "failed", "complete"]
SortValue = str | int | date | Decimal


class DailyMarketTechnicalUniverseV4QueryError(ValueError):
    """full-N v4 查詢條件、保存 pin 或已驗證資料不符合契約。"""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


def _fail(code: str, message: str | None = None) -> NoReturn:
    raise DailyMarketTechnicalUniverseV4QueryError(code, message)


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
        raise DailyMarketTechnicalUniverseV4QueryError(
            "technical_universe_v4_query_json_invalid", str(exc)
        ) from exc


def _reject_float_tree(value: object) -> None:
    if isinstance(value, float):
        _fail("technical_universe_v4_query_float_forbidden")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                _fail("technical_universe_v4_query_json_invalid")
            _reject_float_tree(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_float_tree(item)


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_json(value: object) -> str:
    return _sha256_bytes(_canonical_json_bytes(value))


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("technical_universe_v4_query_duplicate_json_key")
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    _fail("technical_universe_v4_query_json_invalid", value)


def _parse_canonical_json(raw: bytes | str) -> dict[str, Any]:
    try:
        encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
        if not isinstance(encoded, bytes) or len(encoded) > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_BYTES:
            _fail("technical_universe_v4_query_byte_limit")
        parsed = json.loads(
            encoded.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except DailyMarketTechnicalUniverseV4QueryError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalUniverseV4QueryError(
            "technical_universe_v4_query_json_invalid", str(exc)
        ) from exc
    if not isinstance(parsed, dict):
        _fail("technical_universe_v4_query_json_invalid")
    _reject_float_tree(parsed)
    if _canonical_json_bytes(parsed) != encoded:
        _fail("technical_universe_v4_query_json_noncanonical")
    return parsed


def _require_sha(value: object, code: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail(code)
    return value


def _absolute_path_text(value: object, code: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 32767:
        _fail(code)
    path = Path(value)
    if (
        not path.is_absolute()
        or ".." in path.parts
        or str(path) != value
        or value.startswith(("\\\\?\\", "\\\\.\\"))
    ):
        _fail(code)
    return value


def _parse_date(value: object, code: str) -> date:
    if not isinstance(value, str):
        _fail(code)
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise DailyMarketTechnicalUniverseV4QueryError(code) from exc
    if parsed.isoformat() != value:
        _fail(code)
    return parsed


def _validate_codes(
    value: object,
    *,
    maximum: int,
    code: str,
    allow_empty: bool,
) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or len(value) > maximum
        or (not allow_empty and not value)
        or any(not isinstance(item, str) or _STOCK_CODE_RE.fullmatch(item) is None for item in value)
    ):
        _fail(code)
    result = tuple(cast(list[str], value))
    if result != tuple(sorted(set(result))):
        _fail(code)
    return result


def _validate_filter(value: object) -> dict[str, Any]:
    if isinstance(value, DailyMarketTechnicalRuleStateFilterV4):
        value = value.to_dict()
    if not isinstance(value, Mapping) or frozenset(value) != _STATE_FILTER_KEYS:
        _fail("technical_universe_v4_query_state_filter_invalid")
    rule_key = value.get("rule_key")
    states = value.get("states")
    if not isinstance(rule_key, str) or not rule_key:
        _fail("technical_universe_v4_query_state_filter_invalid")
    if (
        not isinstance(states, list)
        or not states
        or any(item not in _RULE_STATE_ORDER for item in states)
        or tuple(states) != tuple(state for state in _RULE_STATE_ORDER if state in states)
        or len(set(states)) != len(states)
    ):
        _fail("technical_universe_v4_query_state_filter_invalid")
    return {"rule_key": rule_key, "states": list(states)}


def _query_body(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != "query_identity_sha256"}


def _bounded_text(value: object, maximum: int, code: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or value.strip() != value
    ):
        _fail(code)
    return value


def _method_rule_keys(state: DailyMarketTechnicalUniverseV4VerifiedState) -> tuple[str, ...]:
    method = state.plan.to_dict().get("method_contracts")
    if not isinstance(method, Mapping):
        _fail("technical_universe_v4_query_method_rules_invalid")
    rules = method.get("rules")
    if not isinstance(rules, list):
        _fail("technical_universe_v4_query_method_rules_invalid")
    keys: list[str] = []
    for item in rules:
        if not isinstance(item, Mapping) or not isinstance(item.get("key"), str):
            _fail("technical_universe_v4_query_method_rules_invalid")
        keys.append(cast(str, item["key"]))
    if len(keys) != 5 or len(set(keys)) != 5:
        _fail("technical_universe_v4_query_method_rules_invalid")
    return tuple(keys)


def _state_metadata(
    state: DailyMarketTechnicalUniverseV4VerifiedState,
) -> dict[str, Any]:
    plan = state.plan.to_dict()
    cohort = state.plan.cohort
    clock = plan.get("source_clock_identity_sha256")
    method = plan.get("method_contracts_sha256")
    return {
        "generation_identity_sha256": state.plan.generation_identity_sha256,
        "plan_identity_sha256": state.plan.identity_sha256,
        "receipt_identity_sha256": state.receipt.identity_sha256,
        "receipt_status": state.receipt.status,
        "cohort_identity_sha256": cohort.cohort_identity_sha256,
        "source_clock_identity_sha256": clock,
        "method_contracts_sha256": method,
        "universe_id": cohort.universe_id,
        "population_version": cohort.population_version,
        "decision_date": cohort.decision_date.isoformat(),
        "declared_count": len(cohort.declared_stock_codes),
        "included_count": len(cohort.included_stock_codes),
        "excluded_count": len(cohort.excluded_stock_codes),
        "segment_count": len(state.plan.segments),
        "method_rule_keys": list(_method_rule_keys(state)),
    }


def _read_exact_store_state(
    *,
    store_output_root: str | Path,
    generation_identity_sha256: str,
    plan_identity_sha256: str,
    plan_sha256: str,
    receipt_identity_sha256: str,
    receipt_sha256: str,
    parent_verified_callback: Callable[
        [int, DailyMarketTechnicalParentCaptureV4VerifiedRead], None
    ] | None = None,
    cancel_callback: Callable[[], bool] | None = None,
) -> tuple[Path, DailyMarketTechnicalUniverseV4VerifiedState]:
    try:
        reader = DailyMarketTechnicalUniverseV4StoreReader(store_output_root)
        if parent_verified_callback is None and cancel_callback is None:
            state = reader.read_exact(
                generation_identity_sha256,
                plan_identity_sha256,
                receipt_identity_sha256,
                expected_receipt_sha256=receipt_sha256,
                expected_plan_sha256=plan_sha256,
            )
        else:
            state = reader.read_exact_with_verified_parent_callback(
                generation_identity_sha256,
                plan_identity_sha256,
                receipt_identity_sha256,
                expected_receipt_sha256=receipt_sha256,
                expected_plan_sha256=plan_sha256,
                parent_verified_callback=parent_verified_callback,
                cancel_callback=cancel_callback,
            )
    except (DailyMarketTechnicalUniverseV4StoreError, OSError, ValueError) as exc:
        if cancel_callback is not None and _is_cancelled(cancel_callback):
            _fail("technical_universe_v4_query_cancelled")
        code = getattr(exc, "code", "technical_universe_v4_query_store_read_failed")
        raise DailyMarketTechnicalUniverseV4QueryError(str(code), str(exc)) from exc
    return reader.output_root, state


def _validate_query_matches_state(
    query: DailyMarketTechnicalUniverseV4Query,
    *,
    root: Path,
    state: DailyMarketTechnicalUniverseV4VerifiedState,
) -> None:
    expected = _state_metadata(state)
    if (
        str(root) != query.store_output_root
        or expected["generation_identity_sha256"] != query.generation_identity_sha256
        or expected["plan_identity_sha256"] != query.plan_identity_sha256
        or expected["receipt_identity_sha256"] != query.receipt_identity_sha256
        or expected["receipt_status"] != query.receipt_status
        or expected["cohort_identity_sha256"] != query.cohort_identity_sha256
        or expected["source_clock_identity_sha256"] != query.source_clock_identity_sha256
        or expected["method_contracts_sha256"] != query.method_contracts_sha256
        or expected["universe_id"] != query.universe_id
        or expected["population_version"] != query.population_version
        or expected["decision_date"] != query.decision_date.isoformat()
        or expected["declared_count"] != query.declared_count
        or expected["included_count"] != query.included_count
        or expected["excluded_count"] != query.excluded_count
        or expected["segment_count"] != query.segment_count
        or tuple(expected["method_rule_keys"]) != query.method_rule_keys
        or state.counts != query.counts
    ):
        _fail("technical_universe_v4_query_source_identity_mismatch")


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniverseV4Query:
    """固定 generation、plan、receipt 與 full-N filter/sort/page 條件。"""

    store_output_root: str
    generation_identity_sha256: str
    plan_identity_sha256: str
    plan_sha256: str
    receipt_identity_sha256: str
    receipt_sha256: str
    receipt_status: StoreStatus
    cohort_identity_sha256: str
    source_clock_identity_sha256: str
    method_contracts_sha256: str
    universe_id: str
    population_version: str
    decision_date: date
    declared_count: int
    included_count: int
    excluded_count: int
    segment_count: int
    counts: DailyMarketTechnicalUniverseV4Counts
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
        return DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_SCOPE

    @property
    def aggregation_scope(self) -> str:
        return "global_full_universe"

    @property
    def full_n_aggregation(self) -> bool:
        return True

    @property
    def full_market_claim(self) -> bool:
        return False

    def __post_init__(self) -> None:
        _validate_query_dict(self.to_dict())

    @classmethod
    def create(
        cls,
        *,
        store_output_root: str | Path,
        generation_identity_sha256: str,
        plan_identity_sha256: str,
        plan_sha256: str,
        receipt_identity_sha256: str,
        receipt_sha256: str,
        rule_state_filters: Sequence[DailyMarketTechnicalRuleStateFilterV4] = (),
        combine_mode: CombineMode = "AND",
        stock_filter: Sequence[str] = (),
        sort_key: str = "stock_code",
        descending: bool = False,
        page_index: int = 0,
        page_size: int = 50,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> DailyMarketTechnicalUniverseV4Query:
        if _is_cancelled(cancel_callback):
            _fail("technical_universe_v4_query_cancelled")
        if combine_mode not in _COMBINE_MODES or type(descending) is not bool:
            _fail("technical_universe_v4_query_conditions_invalid")
        root, state = _read_exact_store_state(
            store_output_root=store_output_root,
            generation_identity_sha256=generation_identity_sha256,
            plan_identity_sha256=plan_identity_sha256,
            plan_sha256=plan_sha256,
            receipt_identity_sha256=receipt_identity_sha256,
            receipt_sha256=receipt_sha256,
        )
        if _is_cancelled(cancel_callback):
            _fail("technical_universe_v4_query_cancelled")
        metadata = _state_metadata(state)
        filters = _normalize_filters(rule_state_filters, tuple(metadata["method_rule_keys"]))
        normalized_stocks = _normalize_stock_filter(stock_filter)
        _validate_sort_key(sort_key, tuple(metadata["method_rule_keys"]))
        body: dict[str, Any] = {
            "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_SCHEMA,
            "store_output_root": str(root),
            "generation_identity_sha256": metadata["generation_identity_sha256"],
            "plan_identity_sha256": metadata["plan_identity_sha256"],
            "plan_sha256": plan_sha256,
            "receipt_identity_sha256": metadata["receipt_identity_sha256"],
            "receipt_sha256": receipt_sha256,
            "receipt_status": metadata["receipt_status"],
            "cohort_identity_sha256": metadata["cohort_identity_sha256"],
            "source_clock_identity_sha256": metadata["source_clock_identity_sha256"],
            "method_contracts_sha256": metadata["method_contracts_sha256"],
            "universe_id": metadata["universe_id"],
            "population_version": metadata["population_version"],
            "decision_date": metadata["decision_date"],
            "declared_count": metadata["declared_count"],
            "included_count": metadata["included_count"],
            "excluded_count": metadata["excluded_count"],
            "segment_count": metadata["segment_count"],
            "counts": state.counts.to_dict(),
            "method_rule_keys": metadata["method_rule_keys"],
            "state_filters": [item.to_dict() for item in filters],
            "combine_mode": combine_mode,
            "stock_filter": list(normalized_stocks),
            "sort_key": sort_key,
            "descending": descending,
            "page_index": page_index,
            "page_size": page_size,
        }
        body["query_identity_sha256"] = _sha256_json(body)
        return cls.from_dict(body)

    @classmethod
    def from_dict(cls, value: object) -> DailyMarketTechnicalUniverseV4Query:
        payload = _validate_query_dict(value)
        return cls(
            store_output_root=cast(str, payload["store_output_root"]),
            generation_identity_sha256=cast(str, payload["generation_identity_sha256"]),
            plan_identity_sha256=cast(str, payload["plan_identity_sha256"]),
            plan_sha256=cast(str, payload["plan_sha256"]),
            receipt_identity_sha256=cast(str, payload["receipt_identity_sha256"]),
            receipt_sha256=cast(str, payload["receipt_sha256"]),
            receipt_status=cast(StoreStatus, payload["receipt_status"]),
            cohort_identity_sha256=cast(str, payload["cohort_identity_sha256"]),
            source_clock_identity_sha256=cast(str, payload["source_clock_identity_sha256"]),
            method_contracts_sha256=cast(str, payload["method_contracts_sha256"]),
            universe_id=cast(str, payload["universe_id"]),
            population_version=cast(str, payload["population_version"]),
            decision_date=_parse_date(payload["decision_date"], "technical_universe_v4_query_date_invalid"),
            declared_count=cast(int, payload["declared_count"]),
            included_count=cast(int, payload["included_count"]),
            excluded_count=cast(int, payload["excluded_count"]),
            segment_count=cast(int, payload["segment_count"]),
            counts=DailyMarketTechnicalUniverseV4Counts.from_dict(payload["counts"]),
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
    def from_json(cls, raw: bytes | str) -> DailyMarketTechnicalUniverseV4Query:
        return cls.from_dict(_parse_canonical_json(raw))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_SCHEMA,
            "store_output_root": self.store_output_root,
            "generation_identity_sha256": self.generation_identity_sha256,
            "plan_identity_sha256": self.plan_identity_sha256,
            "plan_sha256": self.plan_sha256,
            "receipt_identity_sha256": self.receipt_identity_sha256,
            "receipt_sha256": self.receipt_sha256,
            "receipt_status": self.receipt_status,
            "cohort_identity_sha256": self.cohort_identity_sha256,
            "source_clock_identity_sha256": self.source_clock_identity_sha256,
            "method_contracts_sha256": self.method_contracts_sha256,
            "universe_id": self.universe_id,
            "population_version": self.population_version,
            "decision_date": self.decision_date.isoformat(),
            "declared_count": self.declared_count,
            "included_count": self.included_count,
            "excluded_count": self.excluded_count,
            "segment_count": self.segment_count,
            "counts": self.counts.to_dict(),
            "method_rule_keys": list(self.method_rule_keys),
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


def _normalize_stock_filter(value: Sequence[str]) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)):
        _fail("technical_universe_v4_query_stock_filter_invalid")
    codes = tuple(value)
    if any(not isinstance(code, str) or _STOCK_CODE_RE.fullmatch(code) is None for code in codes):
        _fail("technical_universe_v4_query_stock_filter_invalid")
    result = tuple(sorted(codes))
    if len(result) != len(codes) or tuple(codes) != result:
        _fail("technical_universe_v4_query_stock_filter_invalid")
    if len(result) > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS:
        _fail("technical_universe_v4_query_stock_filter_invalid")
    return result


def _normalize_filters(
    value: Sequence[DailyMarketTechnicalRuleStateFilterV4],
    method_rule_keys: tuple[str, ...],
) -> tuple[DailyMarketTechnicalRuleStateFilterV4, ...]:
    if isinstance(value, (str, bytes)):
        _fail("technical_universe_v4_query_state_filter_invalid")
    result: list[DailyMarketTechnicalRuleStateFilterV4] = []
    for item in value:
        if not isinstance(item, DailyMarketTechnicalRuleStateFilterV4):
            _fail("technical_universe_v4_query_state_filter_invalid")
        if item.rule_key not in method_rule_keys:
            _fail("technical_universe_v4_query_state_filter_invalid")
        result.append(item)
    keys = tuple(item.rule_key for item in result)
    if len(set(keys)) != len(keys):
        _fail("technical_universe_v4_query_state_filter_invalid")
    return tuple(result)


def _validate_sort_key(value: object, method_rule_keys: tuple[str, ...]) -> str:
    if not isinstance(value, str):
        _fail("technical_universe_v4_query_sort_key_invalid")
    if value in {"stock_code", "decision_date", "latest_feature_date", "raw_row_count"}:
        return value
    parts = value.split(".")
    if len(parts) == 2 and parts[0] in method_rule_keys and parts[1] in {
        "ratio", "numerator", "denominator",
    }:
        return value
    _fail("technical_universe_v4_query_sort_key_invalid")


def _validate_query_dict(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping) or frozenset(value) != _QUERY_KEYS:
        _fail("technical_universe_v4_query_fields_invalid")
    payload = dict(value)
    if payload.get("schema_version") != DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_SCHEMA:
        _fail("technical_universe_v4_query_schema_unsupported")
    _absolute_path_text(payload.get("store_output_root"), "technical_universe_v4_query_store_root_invalid")
    for key in (
        "generation_identity_sha256", "plan_identity_sha256", "plan_sha256",
        "receipt_identity_sha256", "receipt_sha256", "cohort_identity_sha256",
        "source_clock_identity_sha256", "method_contracts_sha256",
    ):
        _require_sha(payload.get(key), "technical_universe_v4_query_pin_invalid")
    if payload.get("receipt_status") not in _STATUSES:
        _fail("technical_universe_v4_query_status_invalid")
    _bounded_text(payload.get("universe_id"), 96, "technical_universe_v4_query_cohort_invalid")
    _bounded_text(payload.get("population_version"), 128, "technical_universe_v4_query_cohort_invalid")
    _parse_date(payload.get("decision_date"), "technical_universe_v4_query_date_invalid")
    for key in ("declared_count", "included_count", "excluded_count", "segment_count"):
        if type(payload.get(key)) is not int or payload[key] < 0:
            _fail("technical_universe_v4_query_counts_invalid")
    if (
        payload["declared_count"] != payload["included_count"] + payload["excluded_count"]
        or payload["declared_count"] > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS
        or payload["segment_count"] > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_SEGMENTS
    ):
        _fail("technical_universe_v4_query_counts_invalid")
    counts = DailyMarketTechnicalUniverseV4Counts.from_dict(payload.get("counts"))
    if (
        counts.declared_count != payload["declared_count"]
        or counts.included_count != payload["included_count"]
        or counts.excluded_count != payload["excluded_count"]
        or (payload["receipt_status"] == "complete" and counts.pending_count != 0)
    ):
        _fail("technical_universe_v4_query_counts_invalid")
    raw_keys = payload.get("method_rule_keys")
    if (
        not isinstance(raw_keys, list)
        or len(raw_keys) != 5
        or any(not isinstance(item, str) or not item for item in raw_keys)
        or len(set(raw_keys)) != len(raw_keys)
    ):
        _fail("technical_universe_v4_query_method_rules_invalid")
    method_rule_keys = tuple(cast(list[str], raw_keys))
    raw_filters = payload.get("state_filters")
    if not isinstance(raw_filters, list) or len(raw_filters) > len(method_rule_keys):
        _fail("technical_universe_v4_query_state_filter_invalid")
    filters = tuple(_validate_filter(item) for item in raw_filters)
    filter_keys = tuple(cast(str, item["rule_key"]) for item in filters)
    if len(set(filter_keys)) != len(filter_keys) or any(key not in method_rule_keys for key in filter_keys):
        _fail("technical_universe_v4_query_state_filter_invalid")
    if payload.get("combine_mode") not in _COMBINE_MODES:
        _fail("technical_universe_v4_query_combine_mode_invalid")
    stock_filter = _validate_codes(
        payload.get("stock_filter"),
        maximum=DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS,
        code="technical_universe_v4_query_stock_filter_invalid",
        allow_empty=True,
    )
    _validate_sort_key(payload.get("sort_key"), method_rule_keys)
    if type(payload.get("descending")) is not bool:
        _fail("technical_universe_v4_query_sort_direction_invalid")
    page_index = payload.get("page_index")
    page_size = payload.get("page_size")
    if (
        type(page_index) is not int
        or not 0 <= page_index <= DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_PAGE_INDEX
        or type(page_size) is not int
        or not 1 <= page_size <= DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_PAGE_SIZE
    ):
        _fail("technical_universe_v4_query_page_invalid")
    query_id = _require_sha(
        payload.get("query_identity_sha256"), "technical_universe_v4_query_identity_invalid"
    )
    if _sha256_json(_query_body(payload)) != query_id:
        _fail("technical_universe_v4_query_identity_mismatch")
    payload["method_rule_keys"] = list(method_rule_keys)
    payload["state_filters"] = list(filters)
    payload["stock_filter"] = list(stock_filter)
    return payload


@dataclass(frozen=True, slots=True)
class _SortCandidate:
    stock_code: str
    segment_index: int
    sort_value: SortValue | None
    artifact_index: int


@dataclass(frozen=True, slots=True)
class _ChildArtifactReference:
    """頁面重開單一 child batch 所需的精確、輕量引用。"""

    repository_output_root: Path
    manifest_path: Path
    manifest_sha256: str
    cohort_identity_sha256: str
    source_clock_identity_sha256: str
    method_contract_sha256: str
    decision_date: date


def _is_cancelled(callback: Callable[[], bool] | None) -> bool:
    if callback is None:
        return False
    try:
        cancelled = callback()
    except Exception as exc:
        raise DailyMarketTechnicalUniverseV4QueryError(
            "technical_universe_v4_query_cancel_check_failed", str(exc)
        ) from exc
    if type(cancelled) is not bool:
        _fail("technical_universe_v4_query_cancel_callback_invalid")
    return cancelled


def _consume_verified_segment(
    query: DailyMarketTechnicalUniverseV4Query,
    *,
    segment_index: int,
    parent_read: DailyMarketTechnicalParentCaptureV4VerifiedRead,
    candidates: list[_SortCandidate],
    artifact_references: list[_ChildArtifactReference],
    processed_codes: list[str],
    missing_data_codes: list[str],
    unknown_rule_codes: list[str],
    seen_codes: set[str],
    stock_filter: set[str],
    cancel_callback: Callable[[], bool] | None,
) -> None:
    """同次消費已核驗 parent context，只留下排序候選與 child pins。"""

    if _is_cancelled(cancel_callback):
        _fail("technical_universe_v4_query_cancelled")
    if not isinstance(parent_read, DailyMarketTechnicalParentCaptureV4VerifiedRead):
        _fail("technical_universe_v4_query_parent_invalid")
    package = parent_read.package
    verified_batches = parent_read.verified_batches
    if not isinstance(package, Mapping) or not isinstance(verified_batches, tuple):
        _fail("technical_universe_v4_query_parent_invalid")
    plan = package.get("plan")
    receipt = package.get("receipt")
    if not isinstance(plan, Mapping) or not isinstance(receipt, Mapping):
        _fail("technical_universe_v4_query_parent_invalid")
    cohort = plan.get("cohort")
    clock = plan.get("source_clock")
    method = plan.get("method_contracts")
    if not isinstance(cohort, Mapping) or not isinstance(clock, Mapping) or not isinstance(method, Mapping):
        _fail("technical_universe_v4_query_parent_invalid")
    rules = method.get("rules")
    if not isinstance(rules, list):
        _fail("technical_universe_v4_query_method_rules_invalid")
    current_rule_keys = tuple(
        cast(str, rule["key"])
        for rule in rules
        if isinstance(rule, Mapping) and isinstance(rule.get("key"), str)
    )
    if (
        plan.get("source_clock_identity_sha256") != query.source_clock_identity_sha256
        or receipt.get("source_clock_identity_sha256") != query.source_clock_identity_sha256
        or plan.get("method_contracts_sha256") != query.method_contracts_sha256
        or current_rule_keys != query.method_rule_keys
        or cohort.get("universe_id") != query.universe_id
        or cohort.get("population_version") != query.population_version
        or cohort.get("decision_date") != query.decision_date.isoformat()
    ):
        _fail("technical_universe_v4_query_source_identity_mismatch")
    if (
        plan.get("generation_identity_sha256") != receipt.get("generation_identity_sha256")
        or plan.get("parent_plan_identity_sha256") != receipt.get("parent_plan_identity_sha256")
        or receipt.get("status") != "complete"
    ):
        _fail("technical_universe_v4_query_segment_content_mismatch")

    batches = plan.get("batches")
    artifacts = receipt.get("batch_artifacts")
    included_codes = cohort.get("included_stock_codes")
    if (
        not isinstance(batches, list)
        or not isinstance(artifacts, list)
        or not isinstance(included_codes, list)
        or len(batches) != len(artifacts)
        or len(artifacts) != len(verified_batches)
    ):
        _fail("technical_universe_v4_query_parent_invalid")
    if not isinstance(cohort.get("cohort_identity_sha256"), str):
        _fail("technical_universe_v4_query_parent_invalid")
    cohort_identity = cast(str, cohort["cohort_identity_sha256"])
    expected_segment_codes: list[str] = []
    for batch in batches:
        if not isinstance(batch, Mapping):
            _fail("technical_universe_v4_query_parent_invalid")
        codes = batch.get("expected_stock_codes")
        if not isinstance(codes, list) or any(not isinstance(code, str) for code in codes):
            _fail("technical_universe_v4_query_parent_invalid")
        code_tuple = tuple(cast(list[str], codes))
        expected_segment_codes.extend(code_tuple)
    if tuple(expected_segment_codes) != tuple(cast(list[str], included_codes)):
        _fail("technical_universe_v4_query_segment_content_mismatch")

    for batch_plan, receipt_artifact, verified in zip(
        batches,
        artifacts,
        verified_batches,
    ):
        if _is_cancelled(cancel_callback):
            _fail("technical_universe_v4_query_cancelled")
        if (
            not isinstance(batch_plan, Mapping)
            or not isinstance(receipt_artifact, Mapping)
            or not isinstance(verified, DailyMarketTechnicalBatchArtifactV4)
        ):
            _fail("technical_universe_v4_query_parent_invalid")
        batch_codes = tuple(cast(list[str], batch_plan["expected_stock_codes"]))
        receipt_codes = receipt_artifact.get("expected_stock_codes")
        if (
            not isinstance(receipt_codes, list)
            or tuple(cast(list[str], receipt_codes)) != batch_codes
            or verified.expected_stock_codes != batch_codes
            or tuple(snapshot.stock_code for snapshot in verified.snapshots) != batch_codes
            or receipt_artifact.get("manifest_path") != str(verified.manifest_path)
            or receipt_artifact.get("manifest_sha256") != verified.manifest_sha256
            or verified.cohort_identity_sha256 != cohort_identity
        ):
            _fail("technical_universe_v4_query_segment_content_mismatch")
        if (
            verified.source_clock_identity_sha256 != query.source_clock_identity_sha256
            or verified.method_contract_sha256 != query.method_contracts_sha256
            or verified.decision_date.isoformat() != query.decision_date.isoformat()
        ):
            _fail("technical_universe_v4_query_source_identity_mismatch")
        artifact_index = len(artifact_references)
        artifact_references.append(
            _ChildArtifactReference(
                repository_output_root=verified.repository_output_root,
                manifest_path=verified.manifest_path,
                manifest_sha256=verified.manifest_sha256,
                cohort_identity_sha256=verified.cohort_identity_sha256,
                source_clock_identity_sha256=verified.source_clock_identity_sha256,
                method_contract_sha256=verified.method_contract_sha256,
                decision_date=verified.decision_date,
            )
        )
        for snapshot in verified.snapshots:
            if snapshot.stock_code in seen_codes:
                _fail("technical_universe_v4_query_duplicate_stock")
            seen_codes.add(snapshot.stock_code)
            processed_codes.append(snapshot.stock_code)
            row = _parent_query_module._make_row(snapshot)
            if row.raw_row_count == 0:
                missing_data_codes.append(row.stock_code)
            if any(rule.state == "unknown" for rule in row.rules):
                unknown_rule_codes.append(row.stock_code)
            if stock_filter and row.stock_code not in stock_filter:
                continue
            if not _row_matches_state_filters(row, query.rule_state_filters, query.combine_mode):
                continue
            sort_value = _row_sort_value(row, query.sort_key)
            if sort_value is not None and not isinstance(sort_value, (str, int, date, Decimal)):
                _fail("technical_universe_v4_query_sort_value_invalid")
            candidates.append(
                _SortCandidate(
                    stock_code=row.stock_code,
                    segment_index=segment_index,
                    sort_value=cast(SortValue | None, sort_value),
                    artifact_index=artifact_index,
                )
            )
    if _is_cancelled(cancel_callback):
        _fail("technical_universe_v4_query_cancelled")


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniverseV4Page:
    """全 declared cohort 的 global-sort 一頁及未篩選的 store 分母。"""

    query: DailyMarketTechnicalUniverseV4Query
    rows: tuple[DailyMarketTechnicalParentV4Row, ...]
    counts: DailyMarketTechnicalUniverseV4Counts
    matching_count: int
    page_count: int
    processed_segment_count: int
    pending_stock_codes: tuple[str, ...]
    missing_data_stock_codes: tuple[str, ...]
    unknown_rule_stock_codes: tuple[str, ...]
    exclusion_reasons: tuple[tuple[str, str], ...]

    @property
    def is_complete(self) -> bool:
        return (
            self.query.receipt_status == "complete"
            and self.counts.pending_count == 0
            and self.counts.processed_count == self.counts.included_count
            and self.processed_segment_count == self.query.segment_count
        )

    @property
    def coverage_scope(self) -> str:
        return DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_SCOPE

    @property
    def aggregation_scope(self) -> str:
        return "global_full_universe"

    @property
    def full_n_aggregation(self) -> bool:
        return True

    @property
    def full_market_claim(self) -> bool:
        return False

    @property
    def unknown_rule_count(self) -> int:
        return len(self.unknown_rule_stock_codes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query.to_dict(),
            "coverage_scope": self.coverage_scope,
            "aggregation_scope": self.aggregation_scope,
            "full_n_aggregation": True,
            "full_market_claim": False,
            "parent_status": self.query.receipt_status,
            "is_complete": self.is_complete,
            "counts": {
                **self.counts.to_dict(),
                "matching_count": self.matching_count,
                "page_count": self.page_count,
                "unknown_rule_count": self.unknown_rule_count,
                "processed_segment_count": self.processed_segment_count,
                "segment_count": self.query.segment_count,
            },
            "page_index": self.query.page_index,
            "page_size": self.query.page_size,
            "pending_stock_codes": list(self.pending_stock_codes),
            "missing_data_stock_codes": list(self.missing_data_stock_codes),
            "unknown_rule_stock_codes": list(self.unknown_rule_stock_codes),
            "exclusion_reasons": dict(self.exclusion_reasons),
            "rows": [row.to_dict() for row in self.rows],
        }


def read_daily_market_technical_universe_v4_page(
    query: DailyMarketTechnicalUniverseV4Query | bytes | str,
    *,
    cancel_callback: Callable[[], bool] | None = None,
) -> DailyMarketTechnicalUniverseV4Page:
    """精確重開 full-N receipt，先跨全部 segments global-sort，再取一頁。"""

    if isinstance(query, (bytes, str)):
        query = DailyMarketTechnicalUniverseV4Query.from_json(query)
    if not isinstance(query, DailyMarketTechnicalUniverseV4Query):
        _fail("technical_universe_v4_query_invalid")
    if _is_cancelled(cancel_callback):
        _fail("technical_universe_v4_query_cancelled")

    candidates: list[_SortCandidate] = []
    artifact_references: list[_ChildArtifactReference] = []
    processed_codes: list[str] = []
    missing_data_codes: list[str] = []
    unknown_rule_codes: list[str] = []
    seen_codes: set[str] = set()
    callback_segments: list[int] = []
    stock_filter = set(query.stock_filter)

    def consume_verified_segment(
        segment_index: int,
        parent_read: DailyMarketTechnicalParentCaptureV4VerifiedRead,
    ) -> None:
        if segment_index != len(callback_segments):
            _fail("technical_universe_v4_query_segment_order_invalid")
        try:
            _consume_verified_segment(
                query,
                segment_index=segment_index,
                parent_read=parent_read,
                candidates=candidates,
                artifact_references=artifact_references,
                processed_codes=processed_codes,
                missing_data_codes=missing_data_codes,
                unknown_rule_codes=unknown_rule_codes,
                seen_codes=seen_codes,
                stock_filter=stock_filter,
                cancel_callback=cancel_callback,
            )
        except DailyMarketTechnicalUniverseV4QueryError as exc:
            raise DailyMarketTechnicalUniverseV4StoreError(
                exc.code, str(exc)
            ) from exc
        callback_segments.append(segment_index)

    root, state = _read_exact_store_state(
        store_output_root=query.store_output_root,
        generation_identity_sha256=query.generation_identity_sha256,
        plan_identity_sha256=query.plan_identity_sha256,
        plan_sha256=query.plan_sha256,
        receipt_identity_sha256=query.receipt_identity_sha256,
        receipt_sha256=query.receipt_sha256,
        parent_verified_callback=consume_verified_segment,
        cancel_callback=cancel_callback,
    )
    _validate_query_matches_state(query, root=root, state=state)
    if _is_cancelled(cancel_callback):
        _fail("technical_universe_v4_query_cancelled")

    references = state.segment_parent_references
    if tuple(index for index, _reference in references) != tuple(range(len(references))):
        _fail("technical_universe_v4_query_segment_order_invalid")
    if len(references) > query.segment_count:
        _fail("technical_universe_v4_query_segment_count_invalid")
    if tuple(callback_segments) != tuple(index for index, _reference in references):
        _fail("technical_universe_v4_query_segment_callback_mismatch")

    cohort = state.plan.cohort
    included_codes = cohort.included_stock_codes
    if (
        len(processed_codes) != state.counts.processed_count
        or tuple(processed_codes) != included_codes[:len(processed_codes)]
        or state.counts.pending_count != len(included_codes) - len(processed_codes)
        or state.counts.missing_data_count != len(state.missing_data_stock_codes)
        or tuple(missing_data_codes) != state.missing_data_stock_codes
        or state.counts.processed_count + state.counts.pending_count != state.counts.included_count
    ):
        _fail("technical_universe_v4_query_counts_mismatch")
    if query.receipt_status == "complete" and (
        state.counts.pending_count != 0
        or state.counts.processed_count != state.counts.included_count
        or len(references) != query.segment_count
    ):
        _fail("technical_universe_v4_query_false_complete")
    if _is_cancelled(cancel_callback):
        _fail("technical_universe_v4_query_cancelled")

    candidates.sort(key=lambda item: item.stock_code)
    null_candidates = [item for item in candidates if item.sort_value is None]
    valued_candidates = [item for item in candidates if item.sort_value is not None]
    valued_candidates.sort(
        key=lambda item: cast(SortValue, item.sort_value),
        reverse=query.descending,
    )
    null_candidates.sort(key=lambda item: item.stock_code)
    ordered = valued_candidates + null_candidates
    matching_count = len(ordered)
    page_count = (matching_count + query.page_size - 1) // query.page_size
    page_start = query.page_index * query.page_size
    page_candidates = ordered[page_start:page_start + query.page_size]
    selected_by_artifact: dict[int, list[_SortCandidate]] = {}
    for item in page_candidates:
        selected_by_artifact.setdefault(item.artifact_index, []).append(item)

    page_rows_by_code: dict[str, DailyMarketTechnicalParentV4Row] = {}
    for artifact_index, artifact_candidates in sorted(selected_by_artifact.items()):
        if _is_cancelled(cancel_callback):
            _fail("technical_universe_v4_query_cancelled")
        if not 0 <= artifact_index < len(artifact_references):
            _fail("technical_universe_v4_query_page_reference_missing")
        artifact_reference = artifact_references[artifact_index]
        try:
            verified_artifact = DailyMarketTechnicalSnapshotV4Repository(
                artifact_reference.repository_output_root
            ).read_exact(
                artifact_reference.manifest_path,
                expected_manifest_sha256=artifact_reference.manifest_sha256,
                expected_cohort_identity_sha256=artifact_reference.cohort_identity_sha256,
                expected_source_clock_sha256=artifact_reference.source_clock_identity_sha256,
                expected_method_contract_sha256=artifact_reference.method_contract_sha256,
                expected_decision_date=artifact_reference.decision_date,
            )
        except (DailyMarketTechnicalSnapshotV4RepositoryError, OSError, ValueError) as exc:
            code = getattr(exc, "code", "technical_universe_v4_query_child_read_failed")
            raise DailyMarketTechnicalUniverseV4QueryError(str(code), str(exc)) from exc
        if _is_cancelled(cancel_callback):
            _fail("technical_universe_v4_query_cancelled")
        snapshots_by_code = {
            snapshot.stock_code: snapshot
            for snapshot in verified_artifact.snapshots
        }
        if len(snapshots_by_code) != len(verified_artifact.snapshots):
            _fail("technical_universe_v4_query_duplicate_page_stock")
        for candidate in artifact_candidates:
            snapshot = snapshots_by_code.get(candidate.stock_code)
            if snapshot is None:
                _fail("technical_universe_v4_query_page_rows_missing")
            row = _parent_query_module._make_row(snapshot)
            actual_sort_value = _row_sort_value(row, query.sort_key)
            if actual_sort_value != candidate.sort_value:
                _fail("technical_universe_v4_query_page_sort_value_changed")
            if row.stock_code in page_rows_by_code:
                _fail("technical_universe_v4_query_duplicate_page_stock")
            page_rows_by_code[row.stock_code] = row
    if set(page_rows_by_code) != {item.stock_code for item in page_candidates}:
        _fail("technical_universe_v4_query_page_rows_missing")
    if _is_cancelled(cancel_callback):
        _fail("technical_universe_v4_query_cancelled")

    page_rows = tuple(page_rows_by_code[item.stock_code] for item in page_candidates)
    pending_codes = included_codes[len(processed_codes):]
    return DailyMarketTechnicalUniverseV4Page(
        query=query,
        rows=page_rows,
        counts=state.counts,
        matching_count=matching_count,
        page_count=page_count,
        processed_segment_count=len(references),
        pending_stock_codes=pending_codes,
        missing_data_stock_codes=state.missing_data_stock_codes,
        unknown_rule_stock_codes=tuple(sorted(unknown_rule_codes)),
        exclusion_reasons=cohort.exclusion_reasons,
    )
