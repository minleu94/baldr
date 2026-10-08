"""以固定 full-N v4 store 做全域、唯讀的技術規則查詢。"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace as dataclass_replace
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
from app_module.daily_market_technical_feature_snapshot_v4 import (
    DailyMarketTechnicalFeatureSnapshotV4,
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
    DailyMarketTechnicalUniverseV4ParentReceiptReference,
    DailyMarketTechnicalUniverseV4VerifiedState,
)


DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_SCHEMA = (
    "daily-market-technical-universe-query.v4"
)
DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_BYTES = 8 * 1024 * 1024
DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_PAGE_SIZE = 256
DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_PAGE_INDEX = 1_000_000
DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_SCOPE = "declared_full_universe_v4"
DAILY_MARKET_TECHNICAL_UNIVERSE_V4_READ_SESSION_MAX_INDEX_BYTES = 64 * 1024 * 1024
DAILY_MARKET_TECHNICAL_UNIVERSE_V4_SELECTED_ROWS_SCHEMA = (
    "daily-market-technical-universe-v4-selected-rows.v1"
)
DAILY_MARKET_TECHNICAL_UNIVERSE_V4_SELECTED_ROWS_MAX_CODES = 256

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STOCK_CODE_RE = re.compile(r"^[A-Z0-9]{1,16}$")
_RULE_STATE_ORDER = ("match", "no_match", "unknown")
_COMBINE_MODES = frozenset({"AND", "OR"})
_STATUSES = frozenset({"partial", "cancelled", "failed", "complete"})
_READ_SESSION_SEAL = object()
_READ_SELECTION_SEAL = object()
_SELECTED_ROWS_SEAL = object()
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
            cancel_callback=cancel_callback,
        )
        if _is_cancelled(cancel_callback):
            _fail("technical_universe_v4_query_cancelled")
        return _query_from_verified_state(
            root=root,
            state=state,
            plan_sha256=plan_sha256,
            receipt_sha256=receipt_sha256,
            rule_state_filters=rule_state_filters,
            combine_mode=combine_mode,
            stock_filter=stock_filter,
            sort_key=sort_key,
            descending=descending,
            page_index=page_index,
            page_size=page_size,
            cancel_callback=cancel_callback,
        )

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


def _query_from_verified_state(
    *,
    root: Path,
    state: DailyMarketTechnicalUniverseV4VerifiedState,
    plan_sha256: str,
    receipt_sha256: str,
    rule_state_filters: Sequence[DailyMarketTechnicalRuleStateFilterV4],
    combine_mode: CombineMode,
    stock_filter: Sequence[str],
    sort_key: str,
    descending: bool,
    page_index: int,
    page_size: int,
    cancel_callback: Callable[[], bool] | None = None,
) -> DailyMarketTechnicalUniverseV4Query:
    """由同次 strict reader state 組查詢，不另開第二次 store 讀取。"""

    if _is_cancelled(cancel_callback):
        _fail("technical_universe_v4_query_cancelled")
    if combine_mode not in _COMBINE_MODES or type(descending) is not bool:
        _fail("technical_universe_v4_query_conditions_invalid")
    metadata = _state_metadata(state)
    method_rule_keys = tuple(cast(list[str], metadata["method_rule_keys"]))
    filters = _normalize_filters(rule_state_filters, method_rule_keys)
    normalized_stocks = _normalize_stock_filter(stock_filter)
    _validate_sort_key(sort_key, method_rule_keys)
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
        "method_rule_keys": list(method_rule_keys),
        "state_filters": [item.to_dict() for item in filters],
        "combine_mode": combine_mode,
        "stock_filter": list(normalized_stocks),
        "sort_key": sort_key,
        "descending": descending,
        "page_index": page_index,
        "page_size": page_size,
    }
    body["query_identity_sha256"] = _sha256_json(body)
    if _is_cancelled(cancel_callback):
        _fail("technical_universe_v4_query_cancelled")
    return DailyMarketTechnicalUniverseV4Query.from_dict(body)


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


def _normalize_selection_stock_filter(
    value: Sequence[str] | None,
    *,
    cancel_callback: Callable[[], bool] | None = None,
) -> tuple[str, ...] | None:
    """外層 eligibility 可排序正規化，但保留 None 與空 tuple 的差別。"""

    if value is None:
        return None
    if isinstance(value, (str, bytes)):
        _fail("technical_universe_v4_read_selection_eligibility_invalid")
    try:
        if len(value) > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS:
            _fail("technical_universe_v4_read_selection_eligibility_invalid")
        codes_list: list[str] = []
        for code in value:
            if _is_cancelled(cancel_callback):
                _fail("technical_universe_v4_query_cancelled")
            if not isinstance(code, str) or _STOCK_CODE_RE.fullmatch(code) is None:
                _fail("technical_universe_v4_read_selection_eligibility_invalid")
            codes_list.append(code)
    except TypeError as exc:
        raise DailyMarketTechnicalUniverseV4QueryError(
            "technical_universe_v4_read_selection_eligibility_invalid"
        ) from exc
    codes = tuple(codes_list)
    if len(set(codes)) != len(codes):
        _fail("technical_universe_v4_read_selection_eligibility_invalid")
    return tuple(sorted(codes))


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

    segment_index: int
    repository_output_root: Path
    manifest_path: Path
    manifest_sha256: str
    cohort_identity_sha256: str
    source_clock_identity_sha256: str
    method_contract_sha256: str
    decision_date: date


@dataclass(frozen=True, slots=True)
class _ReadIndexRule:
    state: RuleState
    numerator: Decimal | None
    denominator: Decimal | None
    ratio: Decimal | None


@dataclass(frozen=True, slots=True)
class _ReadIndexCandidate:
    """全域篩選／排序需要的緊湊列，不保留原始 rows 或完整 snapshot。"""

    stock_code: str
    segment_index: int
    artifact_index: int
    snapshot_identity_sha256: str
    source_identity: str
    raw_row_count: int
    latest_feature_date: date | None
    rules: tuple[_ReadIndexRule, ...]


@dataclass(frozen=True, slots=True)
class _ReadSessionCollectionContext:
    source_clock_identity_sha256: str
    method_contracts_sha256: str
    method_rule_keys: tuple[str, ...]
    universe_id: str
    population_version: str
    decision_date: date
    rule_state_filters: tuple[DailyMarketTechnicalRuleStateFilterV4, ...] = ()
    combine_mode: CombineMode = "AND"
    stock_filter: tuple[str, ...] = ()
    sort_key: str = "stock_code"


@dataclass(frozen=True, slots=True)
class _ReadSessionParentObservation:
    segment_index: int
    parent_plan_identity_sha256: str
    parent_plan_sha256: str
    parent_receipt_identity_sha256: str
    parent_receipt_sha256: str
    cohort_identity_sha256: str
    source_clock_identity_sha256: str
    method_contracts_sha256: str
    included_stock_codes: tuple[str, ...]


def _read_index_rule_payload(rule: _ReadIndexRule) -> list[object]:
    return [
        rule.state,
        str(rule.numerator) if rule.numerator is not None else None,
        str(rule.denominator) if rule.denominator is not None else None,
        str(rule.ratio) if rule.ratio is not None else None,
    ]


def _read_index_candidate_size(candidate: _ReadIndexCandidate) -> int:
    payload = {
        "stock_code": candidate.stock_code,
        "segment_index": candidate.segment_index,
        "artifact_index": candidate.artifact_index,
        "snapshot_identity_sha256": candidate.snapshot_identity_sha256,
        "source_identity": candidate.source_identity,
        "raw_row_count": candidate.raw_row_count,
        "latest_feature_date": (
            candidate.latest_feature_date.isoformat()
            if candidate.latest_feature_date is not None
            else None
        ),
        "rules": [_read_index_rule_payload(rule) for rule in candidate.rules],
    }
    return len(_canonical_json_bytes(payload))


def _read_index_artifact_size(reference: _ChildArtifactReference) -> int:
    return len(_canonical_json_bytes({
        "segment_index": reference.segment_index,
        "repository_output_root": str(reference.repository_output_root),
        "manifest_path": str(reference.manifest_path),
        "manifest_sha256": reference.manifest_sha256,
        "cohort_identity_sha256": reference.cohort_identity_sha256,
        "source_clock_identity_sha256": reference.source_clock_identity_sha256,
        "method_contract_sha256": reference.method_contract_sha256,
        "decision_date": reference.decision_date.isoformat(),
    }))


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


def _normalize_selected_rows_codes(
    value: Sequence[str],
    *,
    cancel_callback: Callable[[], bool] | None,
) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        _fail("technical_universe_v4_selected_rows_codes_invalid")
    codes: list[str] = []
    seen: set[str] = set()
    try:
        for code in value:
            if _is_cancelled(cancel_callback):
                _fail("technical_universe_v4_query_cancelled")
            if len(codes) >= DAILY_MARKET_TECHNICAL_UNIVERSE_V4_SELECTED_ROWS_MAX_CODES:
                _fail("technical_universe_v4_selected_rows_code_limit")
            if not isinstance(code, str) or _STOCK_CODE_RE.fullmatch(code) is None:
                _fail("technical_universe_v4_selected_rows_codes_invalid")
            if code in seen:
                _fail("technical_universe_v4_selected_rows_duplicate_code")
            seen.add(code)
            codes.append(code)
    except DailyMarketTechnicalUniverseV4QueryError:
        raise
    except Exception as exc:
        raise DailyMarketTechnicalUniverseV4QueryError(
            "technical_universe_v4_selected_rows_codes_invalid", str(exc)
        ) from exc
    return tuple(codes)


def _consume_verified_segment(
    query: DailyMarketTechnicalUniverseV4Query | _ReadSessionCollectionContext,
    *,
    segment_index: int,
    parent_read: DailyMarketTechnicalParentCaptureV4VerifiedRead,
    candidates: list[_SortCandidate] | None,
    artifact_references: list[_ChildArtifactReference],
    processed_codes: list[str],
    missing_data_codes: list[str],
    unknown_rule_codes: list[str],
    seen_codes: set[str],
    stock_filter: set[str],
    cancel_callback: Callable[[], bool] | None,
    read_index_candidates: list[_ReadIndexCandidate] | None = None,
    index_byte_count: list[int] | None = None,
    max_index_bytes: int = DAILY_MARKET_TECHNICAL_UNIVERSE_V4_READ_SESSION_MAX_INDEX_BYTES,
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
                segment_index=segment_index,
                repository_output_root=verified.repository_output_root,
                manifest_path=verified.manifest_path,
                manifest_sha256=verified.manifest_sha256,
                cohort_identity_sha256=verified.cohort_identity_sha256,
                source_clock_identity_sha256=verified.source_clock_identity_sha256,
                method_contract_sha256=verified.method_contract_sha256,
                decision_date=verified.decision_date,
            )
        )
        if read_index_candidates is not None:
            if index_byte_count is None:
                _fail("technical_universe_v4_read_session_index_invalid")
            index_byte_count[0] += _read_index_artifact_size(artifact_references[-1])
            if index_byte_count[0] > max_index_bytes:
                _fail("technical_universe_v4_read_session_index_limit")
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
            if read_index_candidates is not None:
                compact_rules: list[_ReadIndexRule] = []
                for evidence in row.rules:
                    if evidence.state not in _RULE_STATE_ORDER:
                        _fail("technical_universe_v4_read_session_rule_invalid")
                    for number in (evidence.numerator, evidence.denominator, evidence.ratio):
                        if number is not None and (
                            not isinstance(number, Decimal) or not number.is_finite()
                        ):
                            _fail("technical_universe_v4_read_session_decimal_invalid")
                    compact_rules.append(
                        _ReadIndexRule(
                            state=cast(RuleState, evidence.state),
                            numerator=evidence.numerator,
                            denominator=evidence.denominator,
                            ratio=evidence.ratio,
                        )
                    )
                compact_candidate = _ReadIndexCandidate(
                    stock_code=row.stock_code,
                    segment_index=segment_index,
                    artifact_index=artifact_index,
                    snapshot_identity_sha256=snapshot.snapshot_identity_sha256,
                    source_identity=snapshot.source_identity,
                    raw_row_count=row.raw_row_count,
                    latest_feature_date=row.latest_feature_date,
                    rules=tuple(compact_rules),
                )
                read_index_candidates.append(compact_candidate)
                if index_byte_count is None:
                    _fail("technical_universe_v4_read_session_index_invalid")
                index_byte_count[0] += _read_index_candidate_size(compact_candidate)
                if (
                    len(read_index_candidates)
                    > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS
                    or index_byte_count[0] > max_index_bytes
                ):
                    _fail("technical_universe_v4_read_session_index_limit")
            if stock_filter and row.stock_code not in stock_filter:
                continue
            if not _row_matches_state_filters(row, query.rule_state_filters, query.combine_mode):
                continue
            sort_value = _row_sort_value(row, query.sort_key)
            if sort_value is not None and not isinstance(sort_value, (str, int, date, Decimal)):
                _fail("technical_universe_v4_query_sort_value_invalid")
            if candidates is not None:
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


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniverseV4ReadSelection:
    """同一 read session 的固定查詢條件及完整排序代碼清單。"""

    _query: DailyMarketTechnicalUniverseV4Query = field(repr=False)
    _read_session_identity_sha256: str = field(repr=False)
    _query_spec_identity_sha256: str = field(repr=False)
    _eligibility_mode: Literal["unrestricted", "explicit"]
    _eligible_stock_codes_sha256: str
    _effective_stock_filter_sha256: str
    _effective_stock_filter: tuple[str, ...] | None = field(repr=False)
    _candidate_indexes: tuple[int, ...] = field(repr=False)
    _candidate_indexes_sha256: str = field(repr=False)
    stock_codes: tuple[str, ...]
    _ordered_stock_codes_sha256: str = field(repr=False)
    selection_identity_sha256: str
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._seal is not _READ_SELECTION_SEAL:
            _fail("technical_universe_v4_read_selection_not_reader_issued")
        if (
            not isinstance(self._query, DailyMarketTechnicalUniverseV4Query)
            or self._eligibility_mode not in {"unrestricted", "explicit"}
            or _SHA256_RE.fullmatch(self._read_session_identity_sha256) is None
            or _SHA256_RE.fullmatch(self._query_spec_identity_sha256) is None
            or _SHA256_RE.fullmatch(self._eligible_stock_codes_sha256) is None
            or _SHA256_RE.fullmatch(self._effective_stock_filter_sha256) is None
            or _SHA256_RE.fullmatch(self._candidate_indexes_sha256) is None
            or _SHA256_RE.fullmatch(self._ordered_stock_codes_sha256) is None
            or _SHA256_RE.fullmatch(self.selection_identity_sha256) is None
            or self._query_spec_identity_sha256 != _query_selection_spec_identity(self._query)
            or len(self._candidate_indexes) != len(self.stock_codes)
            or len(set(self._candidate_indexes)) != len(self._candidate_indexes)
            or len(self.stock_codes) > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS
            or (
                self._effective_stock_filter == ()
                and (self._candidate_indexes or self.stock_codes)
            )
            or any(type(index) is not int or index < 0 for index in self._candidate_indexes)
            or any(
                not isinstance(code, str) or _STOCK_CODE_RE.fullmatch(code) is None
                for code in self.stock_codes
            )
            or len(set(self.stock_codes)) != len(self.stock_codes)
            or _sha256_json(list(self._candidate_indexes)) != self._candidate_indexes_sha256
            or _sha256_json(list(self.stock_codes)) != self._ordered_stock_codes_sha256
        ):
            _fail("technical_universe_v4_read_selection_invalid")
        effective_filter_payload: dict[str, object] = (
            {"scope": "unrestricted"}
            if self._effective_stock_filter is None
            else {"scope": "explicit", "codes": list(self._effective_stock_filter)}
        )
        if _sha256_json(effective_filter_payload) != self._effective_stock_filter_sha256:
            _fail("technical_universe_v4_read_selection_invalid")
        if self._effective_stock_filter is not None:
            try:
                normalized = _normalize_stock_filter(self._effective_stock_filter)
            except DailyMarketTechnicalUniverseV4QueryError as exc:
                raise DailyMarketTechnicalUniverseV4QueryError(
                    "technical_universe_v4_read_selection_invalid", str(exc)
                ) from exc
            if normalized != self._effective_stock_filter:
                _fail("technical_universe_v4_read_selection_invalid")

    @property
    def matching_count(self) -> int:
        return len(self.stock_codes)

    @property
    def query_spec_identity_sha256(self) -> str:
        """查詢條件 digest；不含頁碼與頁面大小。"""

        return self._query_spec_identity_sha256

    @property
    def has_explicit_empty_eligibility(self) -> bool:
        return self._effective_stock_filter == ()


def _query_selection_spec_identity(query: DailyMarketTechnicalUniverseV4Query) -> str:
    payload = query.to_dict()
    payload.pop("page_index", None)
    payload.pop("page_size", None)
    payload.pop("query_identity_sha256", None)
    return _sha256_json(payload)


def _read_selection_identity(selection: DailyMarketTechnicalUniverseV4ReadSelection) -> str:
    body = {
        "schema": "daily-market-technical-universe-read-selection.v1",
        "read_session_identity_sha256": selection._read_session_identity_sha256,
        "query_spec_identity_sha256": selection._query_spec_identity_sha256,
        "eligibility_mode": selection._eligibility_mode,
        "eligible_stock_codes_sha256": selection._eligible_stock_codes_sha256,
        "effective_stock_filter_sha256": selection._effective_stock_filter_sha256,
        "candidate_indexes_sha256": selection._candidate_indexes_sha256,
        "stock_count": len(selection.stock_codes),
        "ordered_stock_codes_sha256": selection._ordered_stock_codes_sha256,
    }
    return _sha256_json(body)


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniverseV4ReadSelectionPage:
    """固定 selection 的一頁；explicit-empty 不偽裝成 v4 空 stock_filter。"""

    selection_identity_sha256: str
    page_index: int
    page_size: int
    matching_count: int
    page_count: int
    page: DailyMarketTechnicalUniverseV4Page | None

    def __post_init__(self) -> None:
        if (
            _SHA256_RE.fullmatch(self.selection_identity_sha256) is None
            or type(self.page_index) is not int
            or not 0 <= self.page_index <= DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_PAGE_INDEX
            or type(self.page_size) is not int
            or not 1 <= self.page_size <= DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_PAGE_SIZE
            or type(self.matching_count) is not int
            or self.matching_count < 0
            or type(self.page_count) is not int
            or self.page_count != (self.matching_count + self.page_size - 1) // self.page_size
        ):
            _fail("technical_universe_v4_read_selection_page_invalid")
        if self.page is None:
            if self.matching_count != 0 or self.page_count != 0:
                _fail("technical_universe_v4_read_selection_page_invalid")
        elif (
            self.page.query.page_index != self.page_index
            or self.page.query.page_size != self.page_size
            or self.page.matching_count != self.matching_count
            or self.page.page_count != self.page_count
        ):
            _fail("technical_universe_v4_read_selection_page_invalid")

    @property
    def rows(self) -> tuple[DailyMarketTechnicalParentV4Row, ...]:
        return () if self.page is None else self.page.rows

    @property
    def is_explicit_empty(self) -> bool:
        return self.page is None


def _selected_rows_materialization_identity(
    *,
    read_session_identity_sha256: str,
    selection_identity_sha256: str,
    query_spec_identity_sha256: str,
    ordered_stock_codes_sha256: str,
    requested_count: int,
    rows_identity_sha256: str,
    row_count: int,
) -> str:
    return _sha256_json({
        "schema": "daily-market-technical-universe-v4-selected-rows.identity.v1",
        "read_session_identity_sha256": read_session_identity_sha256,
        "selection_identity_sha256": selection_identity_sha256,
        "query_spec_identity_sha256": query_spec_identity_sha256,
        "ordered_stock_codes_sha256": ordered_stock_codes_sha256,
        "requested_count": requested_count,
        "rows_identity_sha256": rows_identity_sha256,
        "row_count": row_count,
    })


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniverseV4SelectedRows:
    """同一 read-session 對明示代碼順序精確重開後的有界列批次。"""

    read_session_identity_sha256: str
    selection_identity_sha256: str
    query_spec_identity_sha256: str
    requested_stock_codes: tuple[str, ...]
    ordered_stock_codes_sha256: str
    rows: tuple[DailyMarketTechnicalParentV4Row, ...]
    rows_identity_sha256: str
    materialization_identity_sha256: str
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._seal is not _SELECTED_ROWS_SEAL:
            _fail("technical_universe_v4_selected_rows_not_reader_issued")
        if (
            any(
                not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None
                for value in (
                    self.read_session_identity_sha256,
                    self.selection_identity_sha256,
                    self.query_spec_identity_sha256,
                    self.ordered_stock_codes_sha256,
                    self.rows_identity_sha256,
                    self.materialization_identity_sha256,
                )
            )
            or not isinstance(self.requested_stock_codes, tuple)
            or not isinstance(self.rows, tuple)
            or len(self.requested_stock_codes)
            > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_SELECTED_ROWS_MAX_CODES
            or len(self.requested_stock_codes) != len(self.rows)
            or any(
                not isinstance(code, str) or _STOCK_CODE_RE.fullmatch(code) is None
                for code in self.requested_stock_codes
            )
            or len(set(self.requested_stock_codes)) != len(self.requested_stock_codes)
            or any(not isinstance(row, DailyMarketTechnicalParentV4Row) for row in self.rows)
            or tuple(row.stock_code for row in self.rows) != self.requested_stock_codes
            or _sha256_json(list(self.requested_stock_codes)) != self.ordered_stock_codes_sha256
            or _sha256_json([row.to_dict() for row in self.rows]) != self.rows_identity_sha256
            or _selected_rows_materialization_identity(
                read_session_identity_sha256=self.read_session_identity_sha256,
                selection_identity_sha256=self.selection_identity_sha256,
                query_spec_identity_sha256=self.query_spec_identity_sha256,
                ordered_stock_codes_sha256=self.ordered_stock_codes_sha256,
                requested_count=len(self.requested_stock_codes),
                rows_identity_sha256=self.rows_identity_sha256,
                row_count=len(self.rows),
            ) != self.materialization_identity_sha256
        ):
            _fail("technical_universe_v4_selected_rows_invalid")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": DAILY_MARKET_TECHNICAL_UNIVERSE_V4_SELECTED_ROWS_SCHEMA,
            "read_session_identity_sha256": self.read_session_identity_sha256,
            "selection_identity_sha256": self.selection_identity_sha256,
            "query_spec_identity_sha256": self.query_spec_identity_sha256,
            "requested_stock_codes": list(self.requested_stock_codes),
            "ordered_stock_codes_sha256": self.ordered_stock_codes_sha256,
            "rows": [row.to_dict() for row in self.rows],
            "rows_identity_sha256": self.rows_identity_sha256,
            "materialization_identity_sha256": self.materialization_identity_sha256,
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


def _read_session_collection_context(
    parent_read: DailyMarketTechnicalParentCaptureV4VerifiedRead,
) -> _ReadSessionCollectionContext:
    package = parent_read.package
    plan = package.get("plan")
    if not isinstance(plan, Mapping):
        _fail("technical_universe_v4_query_parent_invalid")
    cohort = plan.get("cohort")
    method = plan.get("method_contracts")
    if not isinstance(cohort, Mapping) or not isinstance(method, Mapping):
        _fail("technical_universe_v4_query_parent_invalid")
    raw_rules = method.get("rules")
    if not isinstance(raw_rules, list):
        _fail("technical_universe_v4_query_method_rules_invalid")
    keys: list[str] = []
    for item in raw_rules:
        if not isinstance(item, Mapping) or not isinstance(item.get("key"), str):
            _fail("technical_universe_v4_query_method_rules_invalid")
        keys.append(cast(str, item["key"]))
    if len(keys) != 5 or len(set(keys)) != len(keys):
        _fail("technical_universe_v4_query_method_rules_invalid")
    clock_id = _require_sha(
        plan.get("source_clock_identity_sha256"),
        "technical_universe_v4_query_parent_invalid",
    )
    method_id = _require_sha(
        plan.get("method_contracts_sha256"),
        "technical_universe_v4_query_parent_invalid",
    )
    universe_id = _bounded_text(
        cohort.get("universe_id"), 96, "technical_universe_v4_query_parent_invalid"
    )
    population_version = _bounded_text(
        cohort.get("population_version"), 128, "technical_universe_v4_query_parent_invalid"
    )
    decision_day = _parse_date(
        cohort.get("decision_date"), "technical_universe_v4_query_parent_invalid"
    )
    return _ReadSessionCollectionContext(
        source_clock_identity_sha256=clock_id,
        method_contracts_sha256=method_id,
        method_rule_keys=tuple(keys),
        universe_id=universe_id,
        population_version=population_version,
        decision_date=decision_day,
    )


def _read_session_parent_observation(
    segment_index: int,
    parent_read: DailyMarketTechnicalParentCaptureV4VerifiedRead,
) -> _ReadSessionParentObservation:
    package = parent_read.package
    plan = package.get("plan")
    receipt = package.get("receipt")
    if not isinstance(plan, Mapping) or not isinstance(receipt, Mapping):
        _fail("technical_universe_v4_query_parent_invalid")
    cohort = plan.get("cohort")
    if not isinstance(cohort, Mapping):
        _fail("technical_universe_v4_query_parent_invalid")
    included = cohort.get("included_stock_codes")
    if not isinstance(included, list) or any(not isinstance(code, str) for code in included):
        _fail("technical_universe_v4_query_parent_invalid")
    return _ReadSessionParentObservation(
        segment_index=segment_index,
        parent_plan_identity_sha256=_require_sha(
            plan.get("parent_plan_identity_sha256"),
            "technical_universe_v4_query_parent_invalid",
        ),
        parent_plan_sha256=_require_sha(
            package.get("plan_sha256"),
            "technical_universe_v4_query_parent_invalid",
        ),
        parent_receipt_identity_sha256=_require_sha(
            receipt.get("receipt_identity_sha256"),
            "technical_universe_v4_query_parent_invalid",
        ),
        parent_receipt_sha256=_require_sha(
            package.get("receipt_sha256"),
            "technical_universe_v4_query_parent_invalid",
        ),
        cohort_identity_sha256=_require_sha(
            cohort.get("cohort_identity_sha256"),
            "technical_universe_v4_query_parent_invalid",
        ),
        source_clock_identity_sha256=_require_sha(
            plan.get("source_clock_identity_sha256"),
            "technical_universe_v4_query_parent_invalid",
        ),
        method_contracts_sha256=_require_sha(
            plan.get("method_contracts_sha256"),
            "technical_universe_v4_query_parent_invalid",
        ),
        included_stock_codes=tuple(cast(list[str], included)),
    )


def _validate_read_session_material(
    *,
    root: Path,
    state: DailyMarketTechnicalUniverseV4VerifiedState,
    callback_segments: Sequence[int],
    parent_observations: Sequence[_ReadSessionParentObservation],
    candidates: Sequence[_ReadIndexCandidate],
    artifact_references: Sequence[_ChildArtifactReference],
    processed_codes: Sequence[str],
    missing_data_codes: Sequence[str],
    unknown_rule_codes: Sequence[str],
) -> None:
    metadata = _state_metadata(state)
    references = state.segment_parent_references
    expected_indices = tuple(index for index, _reference in references)
    if (
        expected_indices != tuple(range(len(references)))
        or tuple(callback_segments) != expected_indices
        or tuple(item.segment_index for item in parent_observations) != expected_indices
        or len(artifact_references) > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS
    ):
        _fail("technical_universe_v4_read_session_segment_mismatch")
    plan_cohort = state.plan.cohort
    included_codes = plan_cohort.included_stock_codes
    if (
        len(processed_codes) != state.counts.processed_count
        or tuple(processed_codes) != included_codes[:len(processed_codes)]
        or tuple(candidate.stock_code for candidate in candidates) != tuple(processed_codes)
        or len(set(processed_codes)) != len(processed_codes)
        or state.counts.pending_count != len(included_codes) - len(processed_codes)
        or state.counts.missing_data_count != len(state.missing_data_stock_codes)
        or tuple(missing_data_codes) != state.missing_data_stock_codes
        or state.counts.processed_count + state.counts.pending_count != state.counts.included_count
    ):
        _fail("technical_universe_v4_query_counts_mismatch")
    if any(
        not 0 <= item.artifact_index < len(artifact_references)
        or artifact_references[item.artifact_index].segment_index != item.segment_index
        for item in candidates
    ):
        _fail("technical_universe_v4_read_session_artifact_mismatch")
    if tuple(sorted(unknown_rule_codes)) != tuple(sorted(
        candidate.stock_code
        for candidate in candidates
        if any(rule.state == "unknown" for rule in candidate.rules)
    )):
        _fail("technical_universe_v4_read_session_unknown_count_mismatch")
    references_by_index = dict(references)
    for observation in parent_observations:
        reference = references_by_index.get(observation.segment_index)
        if reference is None:
            _fail("technical_universe_v4_read_session_parent_mismatch")
        segment = state.plan.segment_cohort(observation.segment_index)
        if (
            observation.parent_plan_identity_sha256 != reference.parent_plan_identity_sha256
            or observation.parent_plan_sha256 != reference.parent_plan_sha256
            or observation.parent_receipt_identity_sha256 != reference.parent_receipt_identity_sha256
            or observation.parent_receipt_sha256 != reference.parent_receipt_sha256
            or observation.cohort_identity_sha256 != segment.cohort_identity_sha256
            or observation.source_clock_identity_sha256 != metadata["source_clock_identity_sha256"]
            or observation.method_contracts_sha256 != metadata["method_contracts_sha256"]
            or observation.included_stock_codes != segment.included_stock_codes
        ):
            _fail("technical_universe_v4_read_session_parent_mismatch")
    if state.receipt.status == "complete" and (
        state.counts.pending_count != 0
        or state.counts.processed_count != state.counts.included_count
        or len(references) != len(state.plan.segments)
    ):
        _fail("technical_universe_v4_query_false_complete")


def _read_session_source_payload(
    *,
    root: Path,
    state: DailyMarketTechnicalUniverseV4VerifiedState,
    plan_sha256: str,
    receipt_sha256: str,
    artifact_references: Sequence[_ChildArtifactReference],
    index_count: int,
    index_bytes: int,
) -> dict[str, Any]:
    metadata = _state_metadata(state)
    return {
        "schema": "daily-market-technical-universe-read-session.v1",
        "store_output_root": str(root),
        "generation_identity_sha256": state.plan.generation_identity_sha256,
        "plan_identity_sha256": state.plan.identity_sha256,
        "plan_sha256": plan_sha256,
        "receipt_identity_sha256": state.receipt.identity_sha256,
        "receipt_sha256": receipt_sha256,
        "receipt_status": state.receipt.status,
        "cohort_identity_sha256": state.plan.cohort.cohort_identity_sha256,
        "source_clock_identity_sha256": metadata["source_clock_identity_sha256"],
        "method_contracts_sha256": metadata["method_contracts_sha256"],
        "calculation_identity_sha256": state.calculation_identity_sha256,
        "counts": state.counts.to_dict(),
        "segment_parent_references": [
            {"segment_index": index, **reference.to_dict()}
            for index, reference in state.segment_parent_references
        ],
        "child_artifacts": [
            {
                "segment_index": item.segment_index,
                "repository_output_root": str(item.repository_output_root),
                "manifest_path": str(item.manifest_path),
                "manifest_sha256": item.manifest_sha256,
                "cohort_identity_sha256": item.cohort_identity_sha256,
                "source_clock_identity_sha256": item.source_clock_identity_sha256,
                "method_contract_sha256": item.method_contract_sha256,
                "decision_date": item.decision_date.isoformat(),
            }
            for item in artifact_references
        ],
        "index_stock_count": index_count,
        "index_bytes": index_bytes,
    }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniverseV4ReadSession:
    """一次完整 strict read 建立的固定版本緊湊索引。

    session 代表建立時讀到並核驗的版本；它不表示來源檔之後仍未變動。
    index_bytes 是 canonical serialized payload 的預算，不代表 Python RSS 上限。
    新操作可另開 session；頁面與個股讀取仍精確重開選中的 child artifact。
    """

    _root: Path = field(repr=False)
    _state: DailyMarketTechnicalUniverseV4VerifiedState = field(repr=False)
    _plan_sha256: str = field(repr=False)
    _receipt_sha256: str = field(repr=False)
    _candidates: tuple[_ReadIndexCandidate, ...] = field(repr=False)
    _artifact_references: tuple[_ChildArtifactReference, ...] = field(repr=False)
    _missing_data_stock_codes: tuple[str, ...] = field(repr=False)
    _unknown_rule_stock_codes: tuple[str, ...] = field(repr=False)
    index_bytes: int
    read_session_identity_sha256: str
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._seal is not _READ_SESSION_SEAL:
            _fail("technical_universe_v4_read_session_not_reader_issued")
        if (
            len(self._candidates) > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS
            or self.index_bytes < 0
            or self.index_bytes > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_READ_SESSION_MAX_INDEX_BYTES
        ):
            _fail("technical_universe_v4_read_session_index_invalid")

    @property
    def store_output_root(self) -> str:
        return str(self._root)

    @property
    def source_counts(self) -> DailyMarketTechnicalUniverseV4Counts:
        """回傳 strict read 已核驗的母體計數，不重新讀取來源。"""

        return self._state.counts

    @property
    def index_stock_count(self) -> int:
        return len(self._candidates)

    @property
    def receipt_identity_sha256(self) -> str:
        return self._state.receipt.identity_sha256

    def create_query(
        self,
        *,
        rule_state_filters: Sequence[DailyMarketTechnicalRuleStateFilterV4] = (),
        combine_mode: CombineMode = "AND",
        stock_filter: Sequence[str] = (),
        sort_key: str = "stock_code",
        descending: bool = False,
        page_index: int = 0,
        page_size: int = 50,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> DailyMarketTechnicalUniverseV4Query:
        return _query_from_verified_state(
            root=self._root,
            state=self._state,
            plan_sha256=self._plan_sha256,
            receipt_sha256=self._receipt_sha256,
            rule_state_filters=rule_state_filters,
            combine_mode=combine_mode,
            stock_filter=stock_filter,
            sort_key=sort_key,
            descending=descending,
            page_index=page_index,
            page_size=page_size,
            cancel_callback=cancel_callback,
        )

    def matches_source(self, query: DailyMarketTechnicalUniverseV4Query) -> bool:
        if not isinstance(query, DailyMarketTechnicalUniverseV4Query):
            return False
        try:
            _validate_query_matches_state(query, root=self._root, state=self._state)
        except DailyMarketTechnicalUniverseV4QueryError:
            return False
        return query.plan_sha256 == self._plan_sha256 and query.receipt_sha256 == self._receipt_sha256

    def read_page(
        self,
        query: DailyMarketTechnicalUniverseV4Query,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> DailyMarketTechnicalUniverseV4Page:
        ordered = self._ordered_candidates(query, eligible_stock_codes=None, cancel_callback=cancel_callback)
        matching_count = len(ordered)
        page_count = (matching_count + query.page_size - 1) // query.page_size
        start = query.page_index * query.page_size
        page_candidates = tuple(
            (candidate, value)
            for _index, candidate, value in ordered[start:start + query.page_size]
        )
        page, _captured = self._materialize_page(
            query,
            page_candidates,
            matching_count=matching_count,
            page_count=page_count,
            capture_stock_code=None,
            cancel_callback=cancel_callback,
        )
        return page

    def read_page_and_stock_snapshot(
        self,
        query: DailyMarketTechnicalUniverseV4Query,
        stock_code: str,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> tuple[
        DailyMarketTechnicalUniverseV4Page,
        int,
        DailyMarketTechnicalUniverseV4ParentReceiptReference,
        DailyMarketTechnicalFeatureSnapshotV4,
    ]:
        """一次讀取 origin page，並從同一批驗證結果捕獲指定股票。"""

        if not isinstance(stock_code, str) or _STOCK_CODE_RE.fullmatch(stock_code) is None:
            _fail("technical_universe_v4_stock_code_invalid")
        ordered = self._ordered_candidates(query, eligible_stock_codes=None, cancel_callback=cancel_callback)
        matching_count = len(ordered)
        page_count = (matching_count + query.page_size - 1) // query.page_size
        start = query.page_index * query.page_size
        page_candidates = tuple(
            (candidate, value)
            for _index, candidate, value in ordered[start:start + query.page_size]
        )
        selected_candidate = next(
            (candidate for candidate, _value in page_candidates if candidate.stock_code == stock_code),
            None,
        )
        if selected_candidate is None:
            _fail("technical_universe_v4_stock_not_in_origin_page")
        page, captured = self._materialize_page(
            query,
            page_candidates,
            matching_count=matching_count,
            page_count=page_count,
            capture_stock_code=stock_code,
            cancel_callback=cancel_callback,
        )
        selected_row = next((row for row in page.rows if row.stock_code == stock_code), None)
        if selected_row is None or captured is None:
            _fail("technical_universe_v4_stock_snapshot_missing")
        candidate, snapshot = captured
        if (
            candidate != selected_candidate
            or snapshot.snapshot_identity_sha256 != selected_row.snapshot_identity_sha256
            or snapshot.source_identity != selected_row.source_identity
        ):
            _fail("technical_universe_v4_stock_snapshot_changed")
        parent_reference = dict(self._state.segment_parent_references).get(candidate.segment_index)
        if parent_reference is None:
            _fail("technical_universe_v4_stock_parent_reference_missing")
        if _is_cancelled(cancel_callback):
            _fail("technical_universe_v4_query_cancelled")
        return page, candidate.segment_index, parent_reference, snapshot

    def _ordered_candidates(
        self,
        query: DailyMarketTechnicalUniverseV4Query,
        *,
        eligible_stock_codes: tuple[str, ...] | None,
        cancel_callback: Callable[[], bool] | None,
    ) -> list[tuple[int, _ReadIndexCandidate, SortValue | None]]:
        if not isinstance(query, DailyMarketTechnicalUniverseV4Query):
            _fail("technical_universe_v4_query_invalid")
        if not self.matches_source(query):
            _fail("technical_universe_v4_read_session_source_mismatch")
        if _is_cancelled(cancel_callback):
            _fail("technical_universe_v4_query_cancelled")
        if eligible_stock_codes == ():
            return []
        stock_filter = set(query.stock_filter)
        eligible_filter = (
            None if eligible_stock_codes is None else set(eligible_stock_codes)
        )
        rule_indexes = {key: index for index, key in enumerate(query.method_rule_keys)}
        matching: list[tuple[int, _ReadIndexCandidate, SortValue | None]] = []
        for candidate_index, candidate in enumerate(self._candidates):
            if _is_cancelled(cancel_callback):
                _fail("technical_universe_v4_query_cancelled")
            if stock_filter and candidate.stock_code not in stock_filter:
                continue
            if eligible_filter is not None and candidate.stock_code not in eligible_filter:
                continue
            selected = tuple(
                candidate.rules[rule_indexes[item.rule_key]].state in item.states
                for item in query.rule_state_filters
            )
            if selected and not (all(selected) if query.combine_mode == "AND" else any(selected)):
                continue
            value = _read_index_sort_value(candidate, query)
            matching.append((candidate_index, candidate, value))
        matching.sort(key=lambda item: item[1].stock_code)
        null_candidates = [item for item in matching if item[2] is None]
        valued_candidates = [item for item in matching if item[2] is not None]
        valued_candidates.sort(key=lambda item: cast(SortValue, item[2]), reverse=query.descending)
        null_candidates.sort(key=lambda item: item[1].stock_code)
        ordered = valued_candidates + null_candidates
        if _is_cancelled(cancel_callback):
            _fail("technical_universe_v4_query_cancelled")
        return ordered

    def _materialize_page(
        self,
        query: DailyMarketTechnicalUniverseV4Query,
        page_candidates: Sequence[tuple[_ReadIndexCandidate, SortValue | None]],
        *,
        matching_count: int,
        page_count: int,
        capture_stock_code: str | None,
        cancel_callback: Callable[[], bool] | None,
    ) -> tuple[
        DailyMarketTechnicalUniverseV4Page,
        tuple[_ReadIndexCandidate, DailyMarketTechnicalFeatureSnapshotV4] | None,
    ]:
        selected_by_artifact: dict[int, list[_ReadIndexCandidate]] = {}
        for candidate, _value in page_candidates:
            selected_by_artifact.setdefault(candidate.artifact_index, []).append(candidate)
        page_rows: dict[str, DailyMarketTechnicalParentV4Row] = {}
        captured: tuple[_ReadIndexCandidate, DailyMarketTechnicalFeatureSnapshotV4] | None = None
        for artifact_index, selected_candidates in sorted(selected_by_artifact.items()):
            if _is_cancelled(cancel_callback):
                _fail("technical_universe_v4_query_cancelled")
            reference = _read_session_artifact_reference(
                self._artifact_references, artifact_index, selected_candidates
            )
            artifact = _read_session_child_artifact(reference, cancel_callback)
            snapshots = {item.stock_code: item for item in artifact.snapshots}
            if len(snapshots) != len(artifact.snapshots):
                _fail("technical_universe_v4_query_duplicate_page_stock")
            for candidate in selected_candidates:
                snapshot = snapshots.get(candidate.stock_code)
                if snapshot is None:
                    _fail("technical_universe_v4_query_page_rows_missing")
                row = _parent_query_module._make_row(snapshot)
                if (
                    snapshot.snapshot_identity_sha256 != candidate.snapshot_identity_sha256
                    or snapshot.source_identity != candidate.source_identity
                    or _row_sort_value(row, query.sort_key)
                    != _read_index_sort_value(candidate, query)
                ):
                    _fail("technical_universe_v4_read_session_candidate_changed")
                if row.stock_code in page_rows:
                    _fail("technical_universe_v4_query_duplicate_page_stock")
                page_rows[row.stock_code] = row
                if capture_stock_code == candidate.stock_code:
                    captured = (candidate, snapshot)
        expected_codes = tuple(candidate.stock_code for candidate, _value in page_candidates)
        if tuple(code for code in expected_codes if code not in page_rows) or set(page_rows) != set(expected_codes):
            _fail("technical_universe_v4_query_page_rows_missing")
        if capture_stock_code is not None and captured is None:
            _fail("technical_universe_v4_stock_snapshot_missing")
        if _is_cancelled(cancel_callback):
            _fail("technical_universe_v4_query_cancelled")
        rows = tuple(page_rows[code] for code in expected_codes)
        cohort = self._state.plan.cohort
        included_codes = cohort.included_stock_codes
        processed_count = self._state.counts.processed_count
        page = DailyMarketTechnicalUniverseV4Page(
            query=query,
            rows=rows,
            counts=self._state.counts,
            matching_count=matching_count,
            page_count=page_count,
            processed_segment_count=len(self._state.segment_parent_references),
            pending_stock_codes=included_codes[processed_count:],
            missing_data_stock_codes=self._missing_data_stock_codes,
            unknown_rule_stock_codes=self._unknown_rule_stock_codes,
            exclusion_reasons=cohort.exclusion_reasons,
        )
        return page, captured

    def select_stock_codes(
        self,
        query: DailyMarketTechnicalUniverseV4Query,
        *,
        eligible_stock_codes: Sequence[str] | None = None,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> DailyMarketTechnicalUniverseV4ReadSelection:
        """全域套用 query 與外層 eligibility 一次排序，回傳不含 raw history 的固定清單。"""

        if not isinstance(query, DailyMarketTechnicalUniverseV4Query):
            _fail("technical_universe_v4_query_invalid")
        if not self.matches_source(query):
            _fail("technical_universe_v4_read_session_source_mismatch")
        if _is_cancelled(cancel_callback):
            _fail("technical_universe_v4_query_cancelled")
        normalized_eligible = _normalize_selection_stock_filter(
            eligible_stock_codes, cancel_callback=cancel_callback
        )
        eligibility_mode: Literal["unrestricted", "explicit"] = (
            "unrestricted" if normalized_eligible is None else "explicit"
        )
        eligible_digest = _sha256_json({
            "mode": eligibility_mode,
            "codes": None if normalized_eligible is None else list(normalized_eligible),
        })
        if normalized_eligible is None:
            effective_stock_filter = query.stock_filter or None
        elif query.stock_filter:
            query_filter = set(query.stock_filter)
            effective_stock_filter = tuple(
                code for code in normalized_eligible if code in query_filter
            )
        else:
            effective_stock_filter = normalized_eligible
        ordered = self._ordered_candidates(
            query,
            eligible_stock_codes=effective_stock_filter,
            cancel_callback=cancel_callback,
        )
        candidate_indexes = tuple(index for index, _candidate, _value in ordered)
        stock_codes = tuple(candidate.stock_code for _index, candidate, _value in ordered)
        effective_filter_payload: dict[str, object] = (
            {"scope": "unrestricted"}
            if effective_stock_filter is None
            else {"scope": "explicit", "codes": list(effective_stock_filter)}
        )
        selection = DailyMarketTechnicalUniverseV4ReadSelection(
            _query=query,
            _read_session_identity_sha256=self.read_session_identity_sha256,
            _query_spec_identity_sha256=_query_selection_spec_identity(query),
            _eligibility_mode=eligibility_mode,
            _eligible_stock_codes_sha256=eligible_digest,
            _effective_stock_filter_sha256=_sha256_json(effective_filter_payload),
            _effective_stock_filter=effective_stock_filter,
            _candidate_indexes=candidate_indexes,
            _candidate_indexes_sha256=_sha256_json(list(candidate_indexes)),
            stock_codes=stock_codes,
            _ordered_stock_codes_sha256=_sha256_json(list(stock_codes)),
            selection_identity_sha256="0" * 64,
            _seal=_READ_SELECTION_SEAL,
        )
        identity = _read_selection_identity(selection)
        issued = dataclass_replace(selection, selection_identity_sha256=identity)
        if _is_cancelled(cancel_callback):
            _fail("technical_universe_v4_query_cancelled")
        return issued

    def _validate_selection(
        self,
        selection: DailyMarketTechnicalUniverseV4ReadSelection,
    ) -> None:
        if not isinstance(selection, DailyMarketTechnicalUniverseV4ReadSelection):
            _fail("technical_universe_v4_read_selection_invalid")
        if (
            selection._seal is not _READ_SELECTION_SEAL
            or selection._read_session_identity_sha256 != self.read_session_identity_sha256
            or not self.matches_source(selection._query)
            or _read_selection_identity(selection) != selection.selection_identity_sha256
        ):
            _fail("technical_universe_v4_read_selection_source_mismatch")

    def _selection_page_query(
        self,
        selection: DailyMarketTechnicalUniverseV4ReadSelection,
        *,
        page_index: int,
        page_size: int,
        cancel_callback: Callable[[], bool] | None,
    ) -> DailyMarketTechnicalUniverseV4Query:
        original = selection._query
        return _query_from_verified_state(
            root=self._root,
            state=self._state,
            plan_sha256=self._plan_sha256,
            receipt_sha256=self._receipt_sha256,
            rule_state_filters=original.rule_state_filters,
            combine_mode=original.combine_mode,
            stock_filter=selection._effective_stock_filter or (),
            sort_key=original.sort_key,
            descending=original.descending,
            page_index=page_index,
            page_size=page_size,
            cancel_callback=cancel_callback,
        )

    def read_selection_page(
        self,
        selection: DailyMarketTechnicalUniverseV4ReadSelection,
        *,
        page_index: int,
        page_size: int,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> DailyMarketTechnicalUniverseV4ReadSelectionPage:
        """切既有全域排序清單，僅精確重開該頁需要的 child artifact。"""

        self._validate_selection(selection)
        if (
            type(page_index) is not int
            or not 0 <= page_index <= DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_PAGE_INDEX
            or type(page_size) is not int
            or not 1 <= page_size <= DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_PAGE_SIZE
        ):
            _fail("technical_universe_v4_query_page_invalid")
        if _is_cancelled(cancel_callback):
            _fail("technical_universe_v4_query_cancelled")
        matching_count = selection.matching_count
        page_count = (matching_count + page_size - 1) // page_size
        if selection._effective_stock_filter == ():
            empty_page = DailyMarketTechnicalUniverseV4ReadSelectionPage(
                selection_identity_sha256=selection.selection_identity_sha256,
                page_index=page_index,
                page_size=page_size,
                matching_count=0,
                page_count=0,
                page=None,
            )
            if _is_cancelled(cancel_callback):
                _fail("technical_universe_v4_query_cancelled")
            return empty_page
        query = self._selection_page_query(
            selection,
            page_index=page_index,
            page_size=page_size,
            cancel_callback=cancel_callback,
        )
        start = page_index * page_size
        selected_indexes = selection._candidate_indexes[start:start + page_size]
        for offset, index in enumerate(selected_indexes):
            absolute_index = start + offset
            if (
                index >= len(self._candidates)
                or absolute_index >= len(selection.stock_codes)
                or self._candidates[index].stock_code != selection.stock_codes[absolute_index]
            ):
                _fail("technical_universe_v4_read_selection_candidate_mismatch")
        page_candidates = tuple(
            (self._candidates[index], None)
            for index in selected_indexes
        )
        page, _captured = self._materialize_page(
            query,
            page_candidates,
            matching_count=matching_count,
            page_count=page_count,
            capture_stock_code=None,
            cancel_callback=cancel_callback,
        )
        return DailyMarketTechnicalUniverseV4ReadSelectionPage(
            selection_identity_sha256=selection.selection_identity_sha256,
            page_index=page_index,
            page_size=page_size,
            matching_count=matching_count,
            page_count=page_count,
            page=page,
        )

    def materialize_selected_stock_codes(
        self,
        selection: DailyMarketTechnicalUniverseV4ReadSelection,
        *,
        explicit_stock_codes: Sequence[str],
        cancel_callback: Callable[[], bool] | None = None,
    ) -> DailyMarketTechnicalUniverseV4SelectedRows:
        """依 caller 順序精確讀取最多 256 列，不產生或偽裝 v4 查詢頁。"""

        if _is_cancelled(cancel_callback):
            _fail("technical_universe_v4_query_cancelled")
        self._validate_selection(selection)
        if _is_cancelled(cancel_callback):
            _fail("technical_universe_v4_query_cancelled")
        if selection._query.sort_key != "stock_code" or selection._query.descending:
            _fail("technical_universe_v4_selected_rows_base_order_invalid")
        requested_stock_codes = _normalize_selected_rows_codes(
            explicit_stock_codes,
            cancel_callback=cancel_callback,
        )
        if _is_cancelled(cancel_callback):
            _fail("technical_universe_v4_query_cancelled")

        selected_by_artifact: dict[int, list[_ReadIndexCandidate]] = {}
        for stock_code in requested_stock_codes:
            if _is_cancelled(cancel_callback):
                _fail("technical_universe_v4_query_cancelled")
            selection_index = bisect_left(selection.stock_codes, stock_code)
            if (
                selection_index >= len(selection.stock_codes)
                or selection.stock_codes[selection_index] != stock_code
            ):
                _fail("technical_universe_v4_selected_rows_code_not_in_selection")
            candidate_index = selection._candidate_indexes[selection_index]
            if not 0 <= candidate_index < len(self._candidates):
                _fail("technical_universe_v4_read_selection_candidate_mismatch")
            candidate = self._candidates[candidate_index]
            if candidate.stock_code != stock_code:
                _fail("technical_universe_v4_read_selection_candidate_mismatch")
            selected_by_artifact.setdefault(candidate.artifact_index, []).append(candidate)

        query = selection._query
        rows_by_code: dict[str, DailyMarketTechnicalParentV4Row] = {}
        for artifact_index, selected_candidates in sorted(selected_by_artifact.items()):
            if _is_cancelled(cancel_callback):
                _fail("technical_universe_v4_query_cancelled")
            reference = _read_session_artifact_reference(
                self._artifact_references, artifact_index, selected_candidates
            )
            artifact = _read_session_child_artifact(reference, cancel_callback)
            if _is_cancelled(cancel_callback):
                _fail("technical_universe_v4_query_cancelled")
            snapshots = {item.stock_code: item for item in artifact.snapshots}
            if len(snapshots) != len(artifact.snapshots):
                _fail("technical_universe_v4_query_duplicate_page_stock")
            for candidate in selected_candidates:
                if _is_cancelled(cancel_callback):
                    _fail("technical_universe_v4_query_cancelled")
                snapshot = snapshots.get(candidate.stock_code)
                if snapshot is None:
                    _fail("technical_universe_v4_query_page_rows_missing")
                if (
                    snapshot.snapshot_identity_sha256 != candidate.snapshot_identity_sha256
                    or snapshot.source_identity != candidate.source_identity
                ):
                    _fail("technical_universe_v4_read_session_candidate_changed")
                row = _parent_query_module._make_row(snapshot)
                if (
                    not _row_matches_state_filters(
                        row, query.rule_state_filters, query.combine_mode
                    )
                    or _row_sort_value(row, query.sort_key)
                    != _read_index_sort_value(candidate, query)
                ):
                    _fail("technical_universe_v4_read_session_candidate_changed")
                if candidate.stock_code in rows_by_code:
                    _fail("technical_universe_v4_query_duplicate_page_stock")
                rows_by_code[candidate.stock_code] = row
            del snapshots
            del artifact

        if len(rows_by_code) != len(requested_stock_codes):
            _fail("technical_universe_v4_query_page_rows_missing")
        rows = tuple(rows_by_code[code] for code in requested_stock_codes)
        ordered_stock_codes_sha256 = _sha256_json(list(requested_stock_codes))
        rows_identity_sha256 = _sha256_json([row.to_dict() for row in rows])
        if _is_cancelled(cancel_callback):
            _fail("technical_universe_v4_query_cancelled")
        materialization_identity_sha256 = _selected_rows_materialization_identity(
            read_session_identity_sha256=self.read_session_identity_sha256,
            selection_identity_sha256=selection.selection_identity_sha256,
            query_spec_identity_sha256=selection.query_spec_identity_sha256,
            ordered_stock_codes_sha256=ordered_stock_codes_sha256,
            requested_count=len(requested_stock_codes),
            rows_identity_sha256=rows_identity_sha256,
            row_count=len(rows),
        )
        if _is_cancelled(cancel_callback):
            _fail("technical_universe_v4_query_cancelled")
        result = DailyMarketTechnicalUniverseV4SelectedRows(
            read_session_identity_sha256=self.read_session_identity_sha256,
            selection_identity_sha256=selection.selection_identity_sha256,
            query_spec_identity_sha256=selection.query_spec_identity_sha256,
            requested_stock_codes=requested_stock_codes,
            ordered_stock_codes_sha256=ordered_stock_codes_sha256,
            rows=rows,
            rows_identity_sha256=rows_identity_sha256,
            materialization_identity_sha256=materialization_identity_sha256,
            _seal=_SELECTED_ROWS_SEAL,
        )
        if _is_cancelled(cancel_callback):
            _fail("technical_universe_v4_query_cancelled")
        return result

    def read_selection_stock_snapshot(
        self,
        selection: DailyMarketTechnicalUniverseV4ReadSelection,
        stock_code: str,
        *,
        page_index: int,
        page_size: int,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> tuple[
        DailyMarketTechnicalUniverseV4Query,
        int,
        DailyMarketTechnicalUniverseV4ParentReceiptReference,
        DailyMarketTechnicalFeatureSnapshotV4,
    ]:
        """只讀 selection 指定頁內個股的 exact artifact，不重新排序母體。"""

        self._validate_selection(selection)
        if not isinstance(stock_code, str) or _STOCK_CODE_RE.fullmatch(stock_code) is None:
            _fail("technical_universe_v4_stock_code_invalid")
        if (
            type(page_index) is not int
            or not 0 <= page_index <= DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_PAGE_INDEX
            or type(page_size) is not int
            or not 1 <= page_size <= DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_PAGE_SIZE
        ):
            _fail("technical_universe_v4_query_page_invalid")
        start = page_index * page_size
        selected_indexes = selection._candidate_indexes[start:start + page_size]
        candidate_index: int | None = None
        for offset, index in enumerate(selected_indexes):
            absolute_index = start + offset
            if (
                index >= len(self._candidates)
                or absolute_index >= len(selection.stock_codes)
                or self._candidates[index].stock_code != selection.stock_codes[absolute_index]
            ):
                _fail("technical_universe_v4_read_selection_candidate_mismatch")
            if selection.stock_codes[absolute_index] == stock_code:
                candidate_index = index
                break
        if candidate_index is None:
            _fail("technical_universe_v4_stock_not_in_origin_page")
        if selection._effective_stock_filter == ():
            _fail("technical_universe_v4_stock_not_in_origin_page")
        query = self._selection_page_query(
            selection,
            page_index=page_index,
            page_size=page_size,
            cancel_callback=cancel_callback,
        )
        if _is_cancelled(cancel_callback):
            _fail("technical_universe_v4_query_cancelled")
        candidate = self._candidates[candidate_index]
        reference = _read_session_artifact_reference(
            self._artifact_references, candidate.artifact_index, (candidate,)
        )
        artifact = _read_session_child_artifact(reference, cancel_callback)
        snapshots = {item.stock_code: item for item in artifact.snapshots}
        if len(snapshots) != len(artifact.snapshots):
            _fail("technical_universe_v4_query_duplicate_page_stock")
        snapshot = snapshots.get(stock_code)
        if snapshot is None or (
            snapshot.snapshot_identity_sha256 != candidate.snapshot_identity_sha256
            or snapshot.source_identity != candidate.source_identity
        ):
            _fail("technical_universe_v4_stock_snapshot_changed")
        row = _parent_query_module._make_row(snapshot)
        if (
            (query.stock_filter and stock_code not in query.stock_filter)
            or not _row_matches_state_filters(row, query.rule_state_filters, query.combine_mode)
            or _row_sort_value(row, query.sort_key) != _read_index_sort_value(candidate, query)
        ):
            _fail("technical_universe_v4_read_session_candidate_changed")
        parent_reference = dict(self._state.segment_parent_references).get(candidate.segment_index)
        if parent_reference is None:
            _fail("technical_universe_v4_stock_parent_reference_missing")
        if _is_cancelled(cancel_callback):
            _fail("technical_universe_v4_query_cancelled")
        return query, candidate.segment_index, parent_reference, snapshot

    def read_stock_snapshot(
        self,
        query: DailyMarketTechnicalUniverseV4Query,
        stock_code: str,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> tuple[int, DailyMarketTechnicalUniverseV4ParentReceiptReference, DailyMarketTechnicalFeatureSnapshotV4]:
        """原查詢當頁只讀一次各 child artifact，並捕獲所選股票。"""

        _page, segment_index, parent_reference, snapshot = self.read_page_and_stock_snapshot(
            query, stock_code, cancel_callback=cancel_callback
        )
        return segment_index, parent_reference, snapshot

def _read_index_sort_value(
    candidate: _ReadIndexCandidate,
    query: DailyMarketTechnicalUniverseV4Query,
) -> SortValue | None:
    sort_key = query.sort_key
    if sort_key == "stock_code":
        return candidate.stock_code
    if sort_key == "decision_date":
        return query.decision_date
    if sort_key == "latest_feature_date":
        return candidate.latest_feature_date
    if sort_key == "raw_row_count":
        return candidate.raw_row_count
    rule_key, field_name = sort_key.rsplit(".", 1)
    try:
        rule = candidate.rules[query.method_rule_keys.index(rule_key)]
    except (ValueError, IndexError) as exc:
        raise DailyMarketTechnicalUniverseV4QueryError(
            "technical_universe_v4_query_sort_key_invalid"
        ) from exc
    value = getattr(rule, field_name)
    if value is not None and not isinstance(value, Decimal):
        _fail("technical_universe_v4_query_sort_value_invalid")
    return cast(Decimal | None, value)


def _read_session_artifact_reference(
    references: Sequence[_ChildArtifactReference],
    artifact_index: int,
    candidates: Sequence[_ReadIndexCandidate],
) -> _ChildArtifactReference:
    if not 0 <= artifact_index < len(references):
        _fail("technical_universe_v4_query_page_reference_missing")
    reference = references[artifact_index]
    if any(
        candidate.artifact_index != artifact_index
        or candidate.segment_index != reference.segment_index
        for candidate in candidates
    ):
        _fail("technical_universe_v4_read_session_artifact_mismatch")
    return reference


def _read_session_child_artifact(
    reference: _ChildArtifactReference,
    cancel_callback: Callable[[], bool] | None,
) -> DailyMarketTechnicalBatchArtifactV4:
    if _is_cancelled(cancel_callback):
        _fail("technical_universe_v4_query_cancelled")
    try:
        artifact = DailyMarketTechnicalSnapshotV4Repository(
            reference.repository_output_root
        ).read_exact(
            reference.manifest_path,
            expected_manifest_sha256=reference.manifest_sha256,
            expected_cohort_identity_sha256=reference.cohort_identity_sha256,
            expected_source_clock_sha256=reference.source_clock_identity_sha256,
            expected_method_contract_sha256=reference.method_contract_sha256,
            expected_decision_date=reference.decision_date,
        )
    except (DailyMarketTechnicalSnapshotV4RepositoryError, OSError, ValueError) as exc:
        code = getattr(exc, "code", "technical_universe_v4_query_child_read_failed")
        raise DailyMarketTechnicalUniverseV4QueryError(str(code), str(exc)) from exc
    if _is_cancelled(cancel_callback):
        _fail("technical_universe_v4_query_cancelled")
    return artifact


class DailyMarketTechnicalUniverseV4ReadSessionBuilder:
    """收集同一次 StoreReader exact callback，完成後才建立 P01 固定 session。"""

    def __init__(
        self,
        *,
        store_output_root: str | Path,
        generation_identity_sha256: str,
        plan_identity_sha256: str,
        plan_sha256: str,
        receipt_identity_sha256: str,
        receipt_sha256: str,
        cancel_callback: Callable[[], bool] | None = None,
        max_index_bytes: int = DAILY_MARKET_TECHNICAL_UNIVERSE_V4_READ_SESSION_MAX_INDEX_BYTES,
    ) -> None:
        if (
            type(max_index_bytes) is not int
            or max_index_bytes <= 0
            or max_index_bytes > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_READ_SESSION_MAX_INDEX_BYTES
        ):
            _fail("technical_universe_v4_read_session_index_limit_invalid")
        if _is_cancelled(cancel_callback):
            _fail("technical_universe_v4_query_cancelled")
        raw_store_root = _absolute_path_text(
            str(store_output_root), "technical_universe_v4_read_session_root_invalid"
        )
        try:
            # 採用 StoreReader 的公開 root 正規形式，避免長路徑顯示差異被誤判。
            canonical_reader = DailyMarketTechnicalUniverseV4StoreReader(raw_store_root)
        except (DailyMarketTechnicalUniverseV4StoreError, OSError, ValueError) as exc:
            code = getattr(exc, "code", "technical_universe_v4_read_session_root_invalid")
            raise DailyMarketTechnicalUniverseV4QueryError(str(code), str(exc)) from exc
        self.store_output_root = _absolute_path_text(
            str(canonical_reader.output_root),
            "technical_universe_v4_read_session_root_invalid",
        )
        self.generation_identity_sha256 = _require_sha(
            generation_identity_sha256, "technical_universe_v4_read_pin_invalid"
        )
        self.plan_identity_sha256 = _require_sha(
            plan_identity_sha256, "technical_universe_v4_read_pin_invalid"
        )
        self.plan_sha256 = _require_sha(plan_sha256, "technical_universe_v4_read_pin_invalid")
        self.receipt_identity_sha256 = _require_sha(
            receipt_identity_sha256, "technical_universe_v4_read_pin_invalid"
        )
        self.receipt_sha256 = _require_sha(
            receipt_sha256, "technical_universe_v4_read_pin_invalid"
        )
        self.cancel_callback = cancel_callback
        self.max_index_bytes = max_index_bytes
        self._candidates: list[_ReadIndexCandidate] = []
        self._artifact_references: list[_ChildArtifactReference] = []
        self._processed_codes: list[str] = []
        self._missing_data_codes: list[str] = []
        self._unknown_rule_codes: list[str] = []
        self._seen_codes: set[str] = set()
        self._callback_segments: list[int] = []
        self._parent_observations: list[_ReadSessionParentObservation] = []
        self._context_holder: list[_ReadSessionCollectionContext] = []
        self._index_byte_count = [0]
        self._bundle_pin: tuple[str, str, str] | None = None
        self._build_attempted = False
        self._built_session: DailyMarketTechnicalUniverseV4ReadSession | None = None
        self._published_session: DailyMarketTechnicalUniverseV4ReadSession | None = None

    @property
    def verified_session(self) -> DailyMarketTechnicalUniverseV4ReadSession | None:
        """只有 BundleReader 完整 exact 成功後才可讀取此值。"""

        return self._published_session

    def consume_verified_parent(
        self,
        segment_index: int,
        parent_read: DailyMarketTechnicalParentCaptureV4VerifiedRead,
    ) -> None:
        if self._build_attempted or self._is_cancelled():
            _fail("technical_universe_v4_query_cancelled")
        if segment_index != len(self._callback_segments):
            _fail("technical_universe_v4_query_segment_order_invalid")
        try:
            context = _read_session_collection_context(parent_read)
            if self._context_holder and self._context_holder[0] != context:
                _fail("technical_universe_v4_read_session_cross_segment_source_mismatch")
            if not self._context_holder:
                self._context_holder.append(context)
            _consume_verified_segment(
                context,
                segment_index=segment_index,
                parent_read=parent_read,
                candidates=None,
                artifact_references=self._artifact_references,
                processed_codes=self._processed_codes,
                missing_data_codes=self._missing_data_codes,
                unknown_rule_codes=self._unknown_rule_codes,
                seen_codes=self._seen_codes,
                stock_filter=set(),
                cancel_callback=self.cancel_callback,
                read_index_candidates=self._candidates,
                index_byte_count=self._index_byte_count,
                max_index_bytes=self.max_index_bytes,
            )
            self._parent_observations.append(
                _read_session_parent_observation(segment_index, parent_read)
            )
        except DailyMarketTechnicalUniverseV4QueryError as exc:
            raise DailyMarketTechnicalUniverseV4StoreError(exc.code, str(exc)) from exc
        self._callback_segments.append(segment_index)

    def _bind_to_verified_bundle(
        self,
        *,
        bundle_output_root: str | Path,
        bundle_identity_sha256: str,
        expected_manifest_sha256: str,
    ) -> None:
        if self._bundle_pin is not None or self._build_attempted:
            _fail("technical_universe_v4_read_session_builder_already_bound")
        root = _absolute_path_text(
            str(bundle_output_root), "technical_universe_v4_read_session_bundle_root_invalid"
        )
        identity = _require_sha(
            bundle_identity_sha256, "technical_universe_v4_read_session_bundle_pin_invalid"
        )
        manifest_sha = _require_sha(
            expected_manifest_sha256, "technical_universe_v4_read_session_bundle_pin_invalid"
        )
        self._bundle_pin = (root, identity, manifest_sha)

    def build_verified_session(
        self,
        *,
        root: Path,
        state: DailyMarketTechnicalUniverseV4VerifiedState,
    ) -> DailyMarketTechnicalUniverseV4ReadSession:
        if self._build_attempted:
            _fail("technical_universe_v4_read_session_builder_already_finished")
        self._build_attempted = True
        if self._is_cancelled():
            _fail("technical_universe_v4_query_cancelled")
        if not isinstance(root, Path) or str(root) != self.store_output_root:
            _fail("technical_universe_v4_read_session_root_mismatch")
        if type(state) is not DailyMarketTechnicalUniverseV4VerifiedState:
            _fail("technical_universe_v4_read_session_store_state_invalid")
        if (
            state.plan.generation_identity_sha256 != self.generation_identity_sha256
            or state.plan.identity_sha256 != self.plan_identity_sha256
            or _sha256_bytes(state.plan.to_json().encode("utf-8")) != self.plan_sha256
            or state.receipt.identity_sha256 != self.receipt_identity_sha256
            or _sha256_bytes(state.receipt.to_json().encode("utf-8")) != self.receipt_sha256
        ):
            _fail("technical_universe_v4_read_session_store_pin_mismatch")
        _validate_read_session_material(
            root=root,
            state=state,
            callback_segments=self._callback_segments,
            parent_observations=self._parent_observations,
            candidates=self._candidates,
            artifact_references=self._artifact_references,
            processed_codes=self._processed_codes,
            missing_data_codes=self._missing_data_codes,
            unknown_rule_codes=self._unknown_rule_codes,
        )
        metadata_bytes = len(_canonical_json_bytes({
            "counts": state.counts.to_dict(),
            "missing_data_stock_codes": list(state.missing_data_stock_codes),
            "unknown_rule_stock_codes": sorted(self._unknown_rule_codes),
            "parent_references": [
                {"segment_index": index, **reference.to_dict()}
                for index, reference in state.segment_parent_references
            ],
        }))
        self._index_byte_count[0] += metadata_bytes
        if self._index_byte_count[0] > self.max_index_bytes:
            _fail("technical_universe_v4_read_session_index_limit")
        if self._is_cancelled():
            _fail("technical_universe_v4_query_cancelled")
        source_payload = _read_session_source_payload(
            root=root,
            state=state,
            plan_sha256=self.plan_sha256,
            receipt_sha256=self.receipt_sha256,
            artifact_references=self._artifact_references,
            index_count=len(self._candidates),
            index_bytes=self._index_byte_count[0],
        )
        source_payload["missing_data_stock_codes"] = list(state.missing_data_stock_codes)
        source_payload["unknown_rule_stock_codes"] = sorted(self._unknown_rule_codes)
        session_identity = _sha256_json(source_payload)
        if self._is_cancelled():
            _fail("technical_universe_v4_query_cancelled")
        session = DailyMarketTechnicalUniverseV4ReadSession(
            _root=root,
            _state=state,
            _plan_sha256=self.plan_sha256,
            _receipt_sha256=self.receipt_sha256,
            _candidates=tuple(self._candidates),
            _artifact_references=tuple(self._artifact_references),
            _missing_data_stock_codes=state.missing_data_stock_codes,
            _unknown_rule_stock_codes=tuple(sorted(self._unknown_rule_codes)),
            index_bytes=self._index_byte_count[0],
            read_session_identity_sha256=session_identity,
            _seal=_READ_SESSION_SEAL,
        )
        if self._is_cancelled():
            _fail("technical_universe_v4_query_cancelled")
        self._built_session = session
        return session

    def _publish_verified_bundle_session(
        self,
        session: DailyMarketTechnicalUniverseV4ReadSession,
    ) -> None:
        if (
            self._bundle_pin is None
            or self._built_session is not session
            or type(session) is not DailyMarketTechnicalUniverseV4ReadSession
            or self._published_session is not None
        ):
            _fail("technical_universe_v4_read_session_bundle_publication_invalid")
        if self._is_cancelled():
            _fail("technical_universe_v4_query_cancelled")
        self._published_session = session

    def _is_cancelled(self) -> bool:
        return _is_cancelled(self.cancel_callback)


def open_daily_market_technical_universe_v4_read_session(
    *,
    store_output_root: str | Path,
    generation_identity_sha256: str,
    plan_identity_sha256: str,
    plan_sha256: str,
    receipt_identity_sha256: str,
    receipt_sha256: str,
    cancel_callback: Callable[[], bool] | None = None,
    max_index_bytes: int = DAILY_MARKET_TECHNICAL_UNIVERSE_V4_READ_SESSION_MAX_INDEX_BYTES,
) -> DailyMarketTechnicalUniverseV4ReadSession:
    """一次完成原 strict reader 核驗並建立有界、不可變的完整母體索引。"""

    builder = DailyMarketTechnicalUniverseV4ReadSessionBuilder(
        store_output_root=store_output_root,
        generation_identity_sha256=generation_identity_sha256,
        plan_identity_sha256=plan_identity_sha256,
        plan_sha256=plan_sha256,
        receipt_identity_sha256=receipt_identity_sha256,
        receipt_sha256=receipt_sha256,
        cancel_callback=cancel_callback,
        max_index_bytes=max_index_bytes,
    )
    root, state = _read_exact_store_state(
        store_output_root=store_output_root,
        generation_identity_sha256=generation_identity_sha256,
        plan_identity_sha256=plan_identity_sha256,
        plan_sha256=plan_sha256,
        receipt_identity_sha256=receipt_identity_sha256,
        receipt_sha256=receipt_sha256,
        parent_verified_callback=builder.consume_verified_parent,
        cancel_callback=cancel_callback,
    )
    return builder.build_verified_session(root=root, state=state)
