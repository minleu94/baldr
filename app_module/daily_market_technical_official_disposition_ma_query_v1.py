"""F17 與四均線條件的全母體複合查詢契約。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import re
from typing import Any, Literal, NoReturn, cast

from app_module.daily_market_technical_official_disposition_query_v1 import (
    ConditionTruth,
    DailyMarketTechnicalOfficialDispositionFilterEvaluationV1,
    DailyMarketTechnicalOfficialDispositionQueryV1,
    DailyMarketTechnicalOfficialDispositionSortValueV1,
    DailyMarketTechnicalOfficialDispositionFactRowV1,
)
from app_module.daily_market_technical_parent_v4_query import DailyMarketTechnicalParentV4Row
from app_module.daily_market_technical_universe_v4_query import DailyMarketTechnicalUniverseV4Counts
from app_module.daily_market_technical_universe_ma_alignment_query_v1 import (
    DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_ID_V1,
    DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_VERSION_V1,
    DailyMarketTechnicalMaAlignmentCompactEntryV1,
    DailyMarketTechnicalMaAlignmentCompactIndexV1,
)


DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_QUERY_V1_SCHEMA = (
    "daily-market-technical-official-disposition-ma-query.v1"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_PAGE_REQUEST_V1_SCHEMA = (
    "daily-market-technical-official-disposition-ma-page-request.v1"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_QUERY_V1_MAX_BYTES = 32 * 1024 * 1024
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_SORT_CLAUSES = 33
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_ROWS = 100_000
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_PAGE_SIZE = 256
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_COMPACT_BYTES = 64 * 1024 * 1024
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_JSON_DEPTH = 32

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STOCK_CODE_RE = re.compile(r"^[A-Z0-9]{1,16}$")
_STATE_ORDER = ("match", "no_match", "unknown")
_TRUTH_ORDER = ("match", "no_match", "unknown", "not_evaluated", "not_applicable")
_SOURCE_PIN_KEYS = (
    "bundle_output_root",
    "bundle_identity_sha256",
    "bundle_manifest_sha256",
    "p01_read_session_identity_sha256",
    "p01_selection_identity_sha256",
    "p01_query_spec_identity_sha256",
    "p01_generation_identity_sha256",
    "p01_plan_identity_sha256",
    "p01_plan_sha256",
    "p01_receipt_identity_sha256",
    "p01_receipt_sha256",
    "p01_cohort_identity_sha256",
    "p01_source_clock_identity_sha256",
    "p01_method_contracts_sha256",
    "ma_read_session_identity_sha256",
    "ma_index_identity_sha256",
    "ma_source_request_identity_sha256",
    "ma_index_source_clock_identity_sha256",
    "market_assignment_pin_identity_sha256",
    "official_disposal_pin_identity_sha256",
    "decision_date",
    "decision_cutoff",
    "ma_method_id",
    "ma_method_version",
)
_UNKNOWN_POLICIES = ("include", "exclude", "only")
_COMBINE_MODES = ("AND", "OR")
_RESULT_SEAL = object()
_PAGE_SEAL = object()

MaState = Literal["match", "no_match", "unknown"]
CombineMode = Literal["AND", "OR"]
UnknownPolicy = Literal["include", "exclude", "only"]
SortDirection = Literal["asc", "desc"]
Truth = ConditionTruth
SortScalar = str | int | Decimal | date | datetime


class DailyMarketTechnicalOfficialDispositionMaQueryV1Error(ValueError):
    """F17/MA 複合查詢的穩定拒絕碼。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise DailyMarketTechnicalOfficialDispositionMaQueryV1Error(
        f"technical_official_ma_query_v1_{code}"
    )


def _reject_float_tree(value: object, *, depth: int = 0) -> None:
    if depth > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_JSON_DEPTH:
        _fail("json_depth_limit")
    if isinstance(value, float):
        _fail("float_forbidden")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                _fail("json_key_invalid")
            _reject_float_tree(item, depth=depth + 1)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_float_tree(item, depth=depth + 1)


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
        raise DailyMarketTechnicalOfficialDispositionMaQueryV1Error(
            "technical_official_ma_query_v1_json_invalid"
        ) from exc


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _require_sha(value: object, code: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail(code)
    return cast(str, value)


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail("duplicate_json_key")
        result[key] = value
    return result


def _preflight_depth(text: str) -> None:
    depth = 0
    quoted = False
    escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_JSON_DEPTH:
                _fail("json_depth_limit")
        elif char in "]}":
            depth -= 1
            if depth < 0:
                _fail("json_invalid")
    if quoted or escaped or depth != 0:
        _fail("json_invalid")


def _parse_json(raw: bytes | str, *, maximum: int) -> object:
    try:
        encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
        if not isinstance(encoded, bytes) or len(encoded) > maximum:
            _fail("json_byte_limit")
        text = encoded.decode("utf-8")
        _preflight_depth(text)
        value = json.loads(
            text,
            object_pairs_hook=_unique_pairs,
            parse_float=lambda _text: _fail("float_forbidden"),
            parse_constant=lambda _text: _fail("json_invalid"),
        )
        _reject_float_tree(value)
        if _canonical_json_bytes(value) != encoded:
            _fail("json_noncanonical")
        return value
    except DailyMarketTechnicalOfficialDispositionMaQueryV1Error:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalOfficialDispositionMaQueryV1Error(
            "technical_official_ma_query_v1_json_invalid"
        ) from exc


def _strict_cancel(callback: Callable[[], object] | None) -> None:
    if callback is None:
        return
    if not callable(callback):
        _fail("cancel_callback_invalid")
    try:
        value = callback()
    except Exception as exc:
        raise DailyMarketTechnicalOfficialDispositionMaQueryV1Error(
            "technical_official_ma_query_v1_cancel_check_failed"
        ) from exc
    if type(value) is not bool:
        _fail("cancel_callback_invalid")
    if value:
        _fail("cancelled")


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionMaSortClauseV1:
    """一個全母體排序欄與方向；unknown/null 永遠排在尾端。"""

    field: str
    direction: SortDirection

    def __post_init__(self) -> None:
        if not isinstance(self.field, str) or not self.field or len(self.field) > 128:
            _fail("sort_clause_invalid")
        if not isinstance(self.direction, str) or self.direction not in {"asc", "desc"}:
            _fail("sort_clause_invalid")

    def to_dict(self) -> dict[str, str]:
        return {"field": self.field, "direction": self.direction}

    @classmethod
    def from_dict(cls, value: object) -> DailyMarketTechnicalOfficialDispositionMaSortClauseV1:
        if not isinstance(value, Mapping) or set(value) != {"field", "direction"}:
            _fail("sort_clause_invalid")
        field_name = value.get("field")
        direction = value.get("direction")
        if not isinstance(field_name, str) or not isinstance(direction, str) or direction not in {"asc", "desc"}:
            _fail("sort_clause_invalid")
        return cls(field_name, cast(SortDirection, direction))


def _parse_f17_query(raw: object) -> DailyMarketTechnicalOfficialDispositionQueryV1:
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_QUERY_V1_MAX_BYTES:
        _fail("f17_query_invalid")
    try:
        query = DailyMarketTechnicalOfficialDispositionQueryV1.from_json(raw)
    except (ValueError, UnicodeError) as exc:
        raise DailyMarketTechnicalOfficialDispositionMaQueryV1Error(
            "technical_official_ma_query_v1_f17_query_invalid"
        ) from exc
    if query.to_json() != raw:
        _fail("f17_query_noncanonical")
    # F17 來源 query 在 composite path 固定 neutral order；有效排序只存在於外層。
    if (
        len(query.sort_clauses) != 1
        or query.sort_clauses[0].field != "stock_code"
        or query.sort_clauses[0].direction != "asc"
        or query.technical_query.sort_key != "stock_code"
        or query.technical_query.descending is not False
        or query.technical_query.page_index != 0
        or query.technical_query.page_size != 1
    ):
        _fail("nested_f17_sort_or_page_not_neutral")
    return query


def _normalize_states(values: Sequence[str] | None) -> tuple[MaState, ...] | None:
    if values is None:
        return None
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        _fail("ma_states_invalid")
    items = tuple(values)
    if (
        not items
        or any(not isinstance(item, str) or item not in _STATE_ORDER for item in items)
        or len(set(cast(tuple[str, ...], items))) != len(items)
    ):
        _fail("ma_states_invalid")
    return cast(tuple[MaState, ...], tuple(item for item in _STATE_ORDER if item in items))


def _query_body(query: DailyMarketTechnicalOfficialDispositionMaQueryV1) -> dict[str, object]:
    return {
        "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_QUERY_V1_SCHEMA,
        "f17_query_json": query.f17_query_json,
        "ma_alignment_read_session_identity_sha256": query.ma_alignment_read_session_identity_sha256,
        "ma_alignment_index_identity_sha256": query.ma_alignment_index_identity_sha256,
        "ma_source_request_identity_sha256": query.ma_source_request_identity_sha256,
        "ma_method_id": query.ma_method_id,
        "ma_method_version": query.ma_method_version,
        "ma_states": None if query.ma_states is None else list(query.ma_states),
        "condition_combine_mode": query.condition_combine_mode,
        "unknown_policy": query.unknown_policy,
        "sort_clauses": [item.to_dict() for item in query.sort_clauses],
    }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionMaQueryV1:
    """全母體條件與排序；頁碼獨立保存在 PageRequest。"""

    f17_query_json: str
    ma_alignment_read_session_identity_sha256: str
    ma_alignment_index_identity_sha256: str
    ma_source_request_identity_sha256: str
    ma_method_id: str
    ma_method_version: str
    ma_states: tuple[MaState, ...] | None
    condition_combine_mode: CombineMode
    unknown_policy: UnknownPolicy
    sort_clauses: tuple[DailyMarketTechnicalOfficialDispositionMaSortClauseV1, ...]
    query_identity_sha256: str

    @classmethod
    def create(
        cls,
        f17_query: DailyMarketTechnicalOfficialDispositionQueryV1,
        ma_alignment_session: object,
        *,
        ma_states: Sequence[MaState] | None = None,
        condition_combine_mode: CombineMode = "AND",
        unknown_policy: UnknownPolicy = "include",
        sort_clauses: Sequence[DailyMarketTechnicalOfficialDispositionMaSortClauseV1] = (),
    ) -> DailyMarketTechnicalOfficialDispositionMaQueryV1:
        from app_module.daily_market_technical_universe_ma_alignment_query_v1 import (
            DailyMarketTechnicalMaAlignmentReadSessionV1,
        )

        if type(f17_query) is not DailyMarketTechnicalOfficialDispositionQueryV1:
            _fail("f17_query_invalid")
        if type(ma_alignment_session) is not DailyMarketTechnicalMaAlignmentReadSessionV1:
            _fail("ma_session_not_reader_issued")
        try:
            ma_alignment_session._validate_session_anchor()
        except Exception as exc:
            raise DailyMarketTechnicalOfficialDispositionMaQueryV1Error(
                "technical_official_ma_query_v1_ma_session_invalid"
            ) from exc
        states = _normalize_states(ma_states)
        if condition_combine_mode not in _COMBINE_MODES or unknown_policy not in _UNKNOWN_POLICIES:
            _fail("condition_policy_invalid")
        clauses = tuple(sort_clauses)
        if not clauses:
            clauses = (DailyMarketTechnicalOfficialDispositionMaSortClauseV1("stock_code", "asc"),)
        if (
            len(clauses) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_SORT_CLAUSES
            or any(type(item) is not DailyMarketTechnicalOfficialDispositionMaSortClauseV1 for item in clauses)
            or len({item.field for item in clauses}) != len(clauses)
        ):
            _fail("sort_clauses_invalid")
        f17_json = f17_query.to_json()
        _parse_f17_query(f17_json)
        rules_active = bool(f17_query.technical_query.rule_state_filters)
        ma_active = states is not None
        if unknown_policy == "only" and not (rules_active or ma_active):
            _fail("unknown_only_without_condition")
        active_group_count = int(rules_active) + int(ma_active)
        if active_group_count < 2:
            condition_combine_mode = "AND"
        if active_group_count == 0:
            unknown_policy = "include"
        _validate_sort_fields(f17_query, clauses)
        source_request = ma_alignment_session.source_request
        index = cast(
            DailyMarketTechnicalMaAlignmentCompactIndexV1,
            ma_alignment_session._index,
        )
        if (
            index.index_identity_sha256 != ma_alignment_session.index_identity_sha256
            or source_request.bundle_output_root != f17_query.bundle_output_root
            or source_request.bundle_identity_sha256 != f17_query.bundle_identity_sha256
            or source_request.expected_manifest_sha256 != f17_query.expected_manifest_sha256
            or source_request.market_assignment_pin_identity_sha256
            != f17_query.market_assignment_pin_identity_sha256
            or source_request.official_disposal_pin_identity_sha256
            != f17_query.official_disposal_pin_identity_sha256
            or source_request.decision_date != f17_query.decision_date
            or source_request.decision_cutoff != f17_query.decision_cutoff.isoformat()
        ):
            _fail("source_scope_mismatch")
        body = {
            "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_QUERY_V1_SCHEMA,
            "f17_query_json": f17_json,
            "ma_alignment_read_session_identity_sha256": ma_alignment_session.read_session_identity_sha256,
            "ma_alignment_index_identity_sha256": ma_alignment_session.index_identity_sha256,
            "ma_source_request_identity_sha256": source_request.request_identity_sha256,
            "ma_method_id": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_ID_V1,
            "ma_method_version": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_VERSION_V1,
            "ma_states": None if states is None else list(states),
            "condition_combine_mode": condition_combine_mode,
            "unknown_policy": unknown_policy,
            "sort_clauses": [item.to_dict() for item in clauses],
        }
        return cls.from_dict({**body, "query_identity_sha256": _sha256_json(body)})

    @classmethod
    def from_dict(cls, value: object) -> DailyMarketTechnicalOfficialDispositionMaQueryV1:
        keys = {
            "schema_version", "f17_query_json", "ma_alignment_read_session_identity_sha256",
            "ma_alignment_index_identity_sha256", "ma_source_request_identity_sha256",
            "ma_method_id", "ma_method_version", "ma_states", "condition_combine_mode",
            "unknown_policy", "sort_clauses", "query_identity_sha256",
        }
        if not isinstance(value, Mapping) or set(value) != keys:
            _fail("query_fields_invalid")
        payload = dict(value)
        if payload.get("schema_version") != DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_QUERY_V1_SCHEMA:
            _fail("query_schema_unsupported")
        f17_query_json = payload.get("f17_query_json")
        f17_query = _parse_f17_query(f17_query_json)
        states_raw = payload.get("ma_states")
        if states_raw is None:
            states = None
        elif isinstance(states_raw, list):
            states = _normalize_states(cast(list[str], states_raw))
            if list(states or ()) != states_raw:
                _fail("ma_states_not_canonical")
        else:
            _fail("ma_states_invalid")
        combine = payload.get("condition_combine_mode")
        unknown = payload.get("unknown_policy")
        if combine not in _COMBINE_MODES or unknown not in _UNKNOWN_POLICIES:
            _fail("condition_policy_invalid")
        clauses_raw = payload.get("sort_clauses")
        if not isinstance(clauses_raw, list) or not 1 <= len(clauses_raw) <= DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_SORT_CLAUSES:
            _fail("sort_clauses_invalid")
        clauses = tuple(DailyMarketTechnicalOfficialDispositionMaSortClauseV1.from_dict(item) for item in clauses_raw)
        if len({item.field for item in clauses}) != len(clauses):
            _fail("sort_clauses_invalid")
        _validate_sort_fields(f17_query, clauses)
        if unknown == "only" and not (f17_query.technical_query.rule_state_filters or states is not None):
            _fail("unknown_only_without_condition")
        active_group_count = int(bool(f17_query.technical_query.rule_state_filters)) + int(states is not None)
        if active_group_count < 2 and combine != "AND":
            _fail("condition_combine_mode_not_canonical")
        if active_group_count == 0 and unknown != "include":
            _fail("unknown_policy_not_canonical")
        for key in (
            "ma_alignment_read_session_identity_sha256", "ma_alignment_index_identity_sha256",
            "ma_source_request_identity_sha256",
        ):
            _require_sha(payload.get(key), "query_source_identity_invalid")
        if (
            payload.get("ma_method_id") != DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_ID_V1
            or payload.get("ma_method_version") != DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_VERSION_V1
        ):
            _fail("query_method_unsupported")
        query = cls(
            f17_query_json=cast(str, f17_query_json),
            ma_alignment_read_session_identity_sha256=cast(str, payload["ma_alignment_read_session_identity_sha256"]),
            ma_alignment_index_identity_sha256=cast(str, payload["ma_alignment_index_identity_sha256"]),
            ma_source_request_identity_sha256=cast(str, payload["ma_source_request_identity_sha256"]),
            ma_method_id=cast(str, payload["ma_method_id"]),
            ma_method_version=cast(str, payload["ma_method_version"]),
            ma_states=states,
            condition_combine_mode=cast(CombineMode, combine),
            unknown_policy=cast(UnknownPolicy, unknown),
            sort_clauses=clauses,
            query_identity_sha256=_require_sha(payload.get("query_identity_sha256"), "query_identity_invalid"),
        )
        if _sha256_json(_query_body(query)) != query.query_identity_sha256:
            _fail("query_identity_mismatch")
        if query.to_json() != _canonical_json_bytes(payload).decode("utf-8"):
            _fail("query_noncanonical")
        return query

    @classmethod
    def from_json(cls, raw: bytes | str) -> DailyMarketTechnicalOfficialDispositionMaQueryV1:
        return cls.from_dict(_parse_json(raw, maximum=DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_QUERY_V1_MAX_BYTES))

    @property
    def f17_query(self) -> DailyMarketTechnicalOfficialDispositionQueryV1:
        return _parse_f17_query(self.f17_query_json)

    @property
    def identity_sha256(self) -> str:
        return self.query_identity_sha256

    def to_dict(self) -> dict[str, object]:
        if _sha256_json(_query_body(self)) != self.query_identity_sha256:
            _fail("query_identity_mismatch")
        return {**_query_body(self), "query_identity_sha256": self.query_identity_sha256}

    def to_json(self) -> str:
        raw = _canonical_json_bytes(self.to_dict())
        if len(raw) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_QUERY_V1_MAX_BYTES:
            _fail("query_byte_limit")
        return raw.decode("utf-8")


def _validate_sort_fields(
    f17_query: DailyMarketTechnicalOfficialDispositionQueryV1,
    clauses: Sequence[DailyMarketTechnicalOfficialDispositionMaSortClauseV1],
) -> None:
    technical_fields = {"stock_code", "decision_date", "latest_feature_date", "raw_row_count"}
    for key in f17_query.technical_query.method_rule_keys:
        technical_fields.update({f"{key}.{field}" for field in ("ratio", "numerator", "denominator")})
    allowed = technical_fields | {
        "market_assignment.state", "market_assignment.snapshot_observed_at",
        "official_disposal.state", "official_disposal.observed_at", "official_disposal.observed_date",
        "ma_alignment_state",
    }
    if any(clause.field not in allowed for clause in clauses):
        _fail("sort_field_unsupported")
    stock_positions = [index for index, clause in enumerate(clauses) if clause.field == "stock_code"]
    if stock_positions and (
        stock_positions != [len(clauses) - 1]
        or clauses[-1].direction != "asc"
    ):
        _fail("stock_code_tiebreak_invalid")
@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionMaPageRequestV1:
    """與全域條件身份分離的頁碼與每頁筆數。"""

    query_json: str
    page_index: int
    page_size: int
    request_identity_sha256: str

    @classmethod
    def create(
        cls,
        query: DailyMarketTechnicalOfficialDispositionMaQueryV1,
        *,
        page_index: int,
        page_size: int,
    ) -> DailyMarketTechnicalOfficialDispositionMaPageRequestV1:
        if type(query) is not DailyMarketTechnicalOfficialDispositionMaQueryV1:
            _fail("page_request_query_invalid")
        query.to_json()
        _validate_page(page_index, page_size)
        body = {
            "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_PAGE_REQUEST_V1_SCHEMA,
            "query_identity_sha256": query.query_identity_sha256,
            "page_index": page_index,
            "page_size": page_size,
        }
        return cls(query.to_json(), page_index, page_size, _sha256_json(body))

    @classmethod
    def from_json(cls, raw: bytes | str) -> DailyMarketTechnicalOfficialDispositionMaPageRequestV1:
        payload = _parse_json(raw, maximum=DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_QUERY_V1_MAX_BYTES)
        expected = {
            "schema_version", "query_json", "query_identity_sha256", "page_index", "page_size",
            "request_identity_sha256",
        }
        if not isinstance(payload, Mapping) or set(payload) != expected or payload.get("schema_version") != DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_PAGE_REQUEST_V1_SCHEMA:
            _fail("page_request_fields_invalid")
        raw_query = payload.get("query_json")
        raw_query_identity = payload.get("query_identity_sha256")
        if not isinstance(raw_query, str):
            _fail("page_request_query_invalid")
        query = DailyMarketTechnicalOfficialDispositionMaQueryV1.from_json(raw_query)
        if raw_query_identity != query.query_identity_sha256:
            _fail("page_request_query_identity_mismatch")
        result = cls.create(
            query,
            page_index=cast(int, payload.get("page_index")),
            page_size=cast(int, payload.get("page_size")),
        )
        if result.request_identity_sha256 != payload.get("request_identity_sha256") or result.to_json() != (raw.decode("utf-8") if isinstance(raw, bytes) else raw):
            _fail("page_request_noncanonical")
        return result

    @property
    def query(self) -> DailyMarketTechnicalOfficialDispositionMaQueryV1:
        return DailyMarketTechnicalOfficialDispositionMaQueryV1.from_json(self.query_json)

    def to_dict(self) -> dict[str, object]:
        query = self.query
        _validate_page(self.page_index, self.page_size)
        if self.query_json != query.to_json():
            _fail("page_request_query_noncanonical")
        body = {
            "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_PAGE_REQUEST_V1_SCHEMA,
            "query_identity_sha256": query.query_identity_sha256,
            "page_index": self.page_index,
            "page_size": self.page_size,
        }
        if _sha256_json(body) != self.request_identity_sha256:
            _fail("page_request_identity_mismatch")
        return {**body, "query_json": self.query_json, "request_identity_sha256": self.request_identity_sha256}

    def to_json(self) -> str:
        return _canonical_json_bytes(self.to_dict()).decode("utf-8")


def _validate_page(page_index: object, page_size: object) -> None:
    if type(page_index) is not int or not 0 <= page_index <= 1_000_000:
        _fail("page_anchor_invalid")
    if type(page_size) is not int or not 1 <= page_size <= DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_PAGE_SIZE:
        _fail("page_anchor_invalid")


def combine_truth_v1(values: Sequence[Truth], mode: CombineMode) -> Truth:
    """按明確三值表合併已啟用的條件群組。"""
    if not values:
        return "not_applicable"
    if mode == "AND":
        if "no_match" in values:
            return "no_match"
        if "not_evaluated" in values:
            return "not_evaluated"
        if "unknown" in values:
            return "unknown"
        return "match"
    if mode == "OR":
        if "match" in values:
            return "match"
        if "not_evaluated" in values:
            return "not_evaluated"
        if "unknown" in values:
            return "unknown"
        return "no_match"
    _fail("combine_mode_invalid")


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionMaCountsV1:
    """保留 F17 全分母；可見列數與 eligible predicate truth 分開計數。"""

    base_f17_counts: object
    ma_state_counts: tuple[tuple[str, int], ...]
    technical_truth_counts: tuple[tuple[str, int], ...]
    ma_truth_counts: tuple[tuple[str, int], ...]
    composite_truth_counts: tuple[tuple[str, int], ...]
    eligible_truth_counts: tuple[tuple[str, int], ...]
    hard_eligible_count: int
    visible_count: int
    unknown_policy_included_count: int
    unknown_policy_excluded_count: int

    def __post_init__(self) -> None:
        base_population = getattr(self.base_f17_counts, "population", None)
        if type(base_population) is not DailyMarketTechnicalUniverseV4Counts:
            _fail("counts_base_invalid")
        declared = _population_declared(self.base_f17_counts)
        processed = base_population.processed_count
        if not _valid_count_pairs(self.ma_state_counts, _STATE_ORDER, processed):
            _fail("counts_ma_states_invalid")
        for name, values in (
            ("technical", self.technical_truth_counts),
            ("ma", self.ma_truth_counts),
            ("composite", self.composite_truth_counts),
        ):
            if not _valid_count_pairs(values, _TRUTH_ORDER, declared):
                _fail(f"counts_{name}_truth_invalid")
        if not _valid_count_pairs(self.eligible_truth_counts, _TRUTH_ORDER, self.hard_eligible_count):
            _fail("counts_eligible_truth_invalid")
        for value in (
            self.hard_eligible_count, self.visible_count,
            self.unknown_policy_included_count, self.unknown_policy_excluded_count,
        ):
            if type(value) is not int or not 0 <= value <= declared:
                _fail("counts_invalid")
        if self.visible_count > self.hard_eligible_count:
            _fail("counts_visible_exceeds_eligible")
        if self.unknown_policy_included_count > self.visible_count:
            _fail("counts_unknown_included_invalid")
        if (
            self.unknown_policy_excluded_count > declared
            or self.unknown_policy_included_count + self.unknown_policy_excluded_count > declared
        ):
            _fail("counts_unknown_excluded_invalid")

    @property
    def declared_count(self) -> int:
        return _population_declared(self.base_f17_counts)

    @property
    def population(self) -> object:
        return getattr(self.base_f17_counts, "population")

    @property
    def matching_count(self) -> int:
        """相容舊呼叫端的別名；值是政策後可見列數，不代表 predicate truth=match。"""
        return self.visible_count

    @property
    def predicate_match_count(self) -> int:
        return dict(self.eligible_truth_counts)["match"]

    @property
    def predicate_unknown_count(self) -> int:
        return dict(self.eligible_truth_counts)["unknown"]

    @property
    def predicate_not_evaluated_count(self) -> int:
        return dict(self.eligible_truth_counts)["not_evaluated"]

    def to_dict(self) -> dict[str, object]:
        base_to_dict = getattr(self.base_f17_counts, "to_dict", None)
        if not callable(base_to_dict):
            _fail("counts_base_invalid")
        return {
            "base_f17_counts": base_to_dict(),
            "ma_state_counts": {key: value for key, value in self.ma_state_counts},
            "technical_truth_counts": {key: value for key, value in self.technical_truth_counts},
            "ma_truth_counts": {key: value for key, value in self.ma_truth_counts},
            "composite_truth_counts": {key: value for key, value in self.composite_truth_counts},
            "eligible_truth_counts": {key: value for key, value in self.eligible_truth_counts},
            "hard_eligible_count": self.hard_eligible_count,
            "visible_count": self.visible_count,
            "predicate_match_count": self.predicate_match_count,
            "predicate_unknown_count": self.predicate_unknown_count,
            "predicate_not_evaluated_count": self.predicate_not_evaluated_count,
            "unknown_policy_included_count": self.unknown_policy_included_count,
            "unknown_policy_excluded_count": self.unknown_policy_excluded_count,
        }


def _population_declared(counts: object) -> int:
    population = getattr(counts, "population", None)
    if type(population) is not DailyMarketTechnicalUniverseV4Counts:
        _fail("counts_base_invalid")
    value = population.declared_count
    if type(value) is not int or value < 0:
        _fail("counts_base_invalid")
    return value


def _valid_count_pairs(values: object, expected_keys: tuple[str, ...], total: int) -> bool:
    if not isinstance(values, tuple) or len(values) != len(expected_keys):
        return False
    pairs: list[tuple[str, int]] = []
    for item in values:
        if (
            not isinstance(item, tuple)
            or len(item) != 2
            or not isinstance(item[0], str)
            or type(item[1]) is not int
            or item[1] < 0
        ):
            return False
        pairs.append(cast(tuple[str, int], item))
    return tuple(key for key, _value in pairs) == expected_keys and sum(
        count for _key, count in pairs
    ) == total


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionMaSortKeyV1:
    query_identity_sha256: str
    stock_code: str
    sort_values: tuple[DailyMarketTechnicalOfficialDispositionSortValueV1, ...]
    fact_row_sha256: str
    ma_evidence_identity_sha256: str | None
    technical_snapshot_identity_sha256: str | None
    technical_source_identity: str | None

    def __post_init__(self) -> None:
        _require_sha(self.query_identity_sha256, "sort_key_query_invalid")
        if not isinstance(self.stock_code, str) or _STOCK_CODE_RE.fullmatch(self.stock_code) is None:
            _fail("sort_key_stock_invalid")
        _require_sha(self.fact_row_sha256, "sort_key_fact_invalid")
        if (
            not isinstance(self.sort_values, tuple)
            or not self.sort_values
            or len(self.sort_values) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_SORT_CLAUSES
            or any(type(item) is not DailyMarketTechnicalOfficialDispositionSortValueV1 for item in self.sort_values)
        ):
            _fail("sort_key_values_invalid")
        if (self.technical_snapshot_identity_sha256 is None) != (self.technical_source_identity is None):
            _fail("sort_key_technical_identity_invalid")
        if self.technical_snapshot_identity_sha256 is not None:
            _require_sha(self.technical_snapshot_identity_sha256, "sort_key_technical_identity_invalid")
            if not isinstance(self.technical_source_identity, str) or not self.technical_source_identity:
                _fail("sort_key_technical_identity_invalid")
        if self.ma_evidence_identity_sha256 is not None:
            _require_sha(self.ma_evidence_identity_sha256, "sort_key_ma_identity_invalid")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "daily-market-technical-official-disposition-ma-sort-key.v1",
            "query_identity_sha256": self.query_identity_sha256,
            "stock_code": self.stock_code,
            "sort_values": [item.to_dict() for item in self.sort_values],
            "fact_row_sha256": self.fact_row_sha256,
            "ma_evidence_identity_sha256": self.ma_evidence_identity_sha256,
            "technical_snapshot_identity_sha256": self.technical_snapshot_identity_sha256,
            "technical_source_identity": self.technical_source_identity,
        }


def sort_composite_keys_v1(
    query: DailyMarketTechnicalOfficialDispositionMaQueryV1,
    keys: Sequence[DailyMarketTechnicalOfficialDispositionMaSortKeyV1],
    *,
    cancel_callback: Callable[[], object] | None = None,
) -> tuple[DailyMarketTechnicalOfficialDispositionMaSortKeyV1, ...]:
    _strict_cancel(cancel_callback)
    if len(keys) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_ROWS:
        _fail("sort_row_limit")
    if type(query) is not DailyMarketTechnicalOfficialDispositionMaQueryV1:
        _fail("sort_query_invalid")
    query.to_json()
    expected_fields = tuple((item.field, item.direction) for item in query.sort_clauses)
    seen: set[str] = set()
    total_bytes = 0
    materialized: list[DailyMarketTechnicalOfficialDispositionMaSortKeyV1] = []
    for index, item in enumerate(keys):
        if index >= DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_ROWS:
            _fail("sort_row_limit")
        if index % 256 == 0:
            _strict_cancel(cancel_callback)
        if (
            type(item) is not DailyMarketTechnicalOfficialDispositionMaSortKeyV1
            or item.query_identity_sha256 != query.query_identity_sha256
            or item.stock_code in seen
            or tuple((value.field, value.direction) for value in item.sort_values) != expected_fields
        ):
            _fail("sort_key_mismatch")
        for clause, sort_value in zip(query.sort_clauses, item.sort_values, strict=True):
            _validate_sort_scalar_v1(query.f17_query, clause.field, sort_value.value)
            if clause.field == "stock_code" and sort_value.value != item.stock_code:
                _fail("sort_key_stock_code_value_mismatch")
        seen.add(item.stock_code)
        total_bytes += len(_canonical_json_bytes(item.to_dict())) + 1
        if total_bytes > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_COMPACT_BYTES:
            _fail("sort_key_byte_limit")
        materialized.append(item)
    # 每一欄逐欄排序，將 null 獨立置尾，不受升降方向影響。
    _strict_cancel(cancel_callback)
    materialized.sort(key=lambda item: item.stock_code)
    _strict_cancel(cancel_callback)
    for clause_index in range(len(query.sort_clauses) - 1, -1, -1):
        clause = query.sort_clauses[clause_index]
        known: list[DailyMarketTechnicalOfficialDispositionMaSortKeyV1] = []
        nulls: list[DailyMarketTechnicalOfficialDispositionMaSortKeyV1] = []
        for index, item in enumerate(materialized):
            if index % 256 == 0:
                _strict_cancel(cancel_callback)
            value = item.sort_values[clause_index].value
            (nulls if value is None else known).append(item)
        _strict_cancel(cancel_callback)
        known.sort(
            key=lambda item: cast(Any, item.sort_values[clause_index].value),
            reverse=clause.direction == "desc",
        )
        _strict_cancel(cancel_callback)
        materialized = known + nulls
    _strict_cancel(cancel_callback)
    return tuple(materialized)


def _validate_sort_scalar_v1(
    f17_query: DailyMarketTechnicalOfficialDispositionQueryV1,
    field_name: str,
    value: SortScalar | None,
) -> None:
    if value is None:
        return
    if field_name == "ma_alignment_state":
        if type(value) is not str or value not in {"match", "no_match"}:
            _fail("sort_key_scalar_invalid")
        return
    if field_name == "stock_code" or field_name in {
        "market_assignment.state", "official_disposal.state",
    }:
        if type(value) is not str:
            _fail("sort_key_scalar_invalid")
        if field_name == "market_assignment.state" and value not in {"assigned_twse", "assigned_tpex"}:
            _fail("sort_key_scalar_invalid")
        if field_name == "official_disposal.state" and value not in {
            "reported_upcoming", "reported_active", "reported_elapsed_only",
        }:
            _fail("sort_key_scalar_invalid")
        return
    if field_name in {"decision_date", "latest_feature_date", "official_disposal.observed_date"}:
        if type(value) is not date:
            _fail("sort_key_scalar_invalid")
        return
    if field_name in {"market_assignment.snapshot_observed_at", "official_disposal.observed_at"}:
        if type(value) is not datetime or value.tzinfo is not timezone.utc:
            _fail("sort_key_scalar_invalid")
        return
    if field_name == "raw_row_count":
        if type(value) is not int or value < 0:
            _fail("sort_key_scalar_invalid")
        return
    if any(
        field_name == f"{rule_key}.{metric}"
        for rule_key in f17_query.technical_query.method_rule_keys
        for metric in ("ratio", "numerator", "denominator")
    ):
        if type(value) is not Decimal or not value.is_finite():
            _fail("sort_key_scalar_invalid")
        return
    _fail("sort_key_scalar_invalid")


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionMaResultRowV1:
    fact_row: DailyMarketTechnicalOfficialDispositionFactRowV1
    technical_row: DailyMarketTechnicalParentV4Row | None
    ma_entry: DailyMarketTechnicalMaAlignmentCompactEntryV1 | None
    filter_evaluation: DailyMarketTechnicalOfficialDispositionFilterEvaluationV1
    technical_condition_truth: Truth
    ma_condition_truth: Truth
    composite_condition_truth: Truth
    hard_filter_match: bool
    included_by_unknown_policy: bool
    row_identity_sha256: str

    def __post_init__(self) -> None:
        code = self.fact_row.stock_code
        if (
            self.filter_evaluation.stock_code != code
            or (self.technical_row is not None and self.technical_row.stock_code != code)
            or (self.ma_entry is not None and self.ma_entry.stock_code != code)
            or self.composite_condition_truth not in _TRUTH_ORDER
        ):
            _fail("result_row_invalid")
        _require_sha(self.row_identity_sha256, "result_row_identity_invalid")

    @property
    def stock_code(self) -> str:
        return self.fact_row.stock_code

    def to_dict(self) -> dict[str, object]:
        return {
            "stock_code": self.stock_code,
            "fact_row": self.fact_row.to_dict(),
            "technical_row": None if self.technical_row is None else self.technical_row.to_dict(),
            "ma_entry": None if self.ma_entry is None else self.ma_entry.to_dict(),
            "filter_evaluation": {
                "row_scope": self.filter_evaluation.row_scope,
                "row_scope_match": self.filter_evaluation.row_scope_match,
                "stock_filter_match": self.filter_evaluation.stock_filter_match,
                "market_assignment_match": self.filter_evaluation.market_assignment_match,
                "market_assignment_truth": self.filter_evaluation.market_assignment_truth,
                "official_disposal_match": self.filter_evaluation.official_disposal_match,
                "official_disposal_truth": self.filter_evaluation.official_disposal_truth,
            },
            "technical_condition_truth": self.technical_condition_truth,
            "ma_condition_truth": self.ma_condition_truth,
            "composite_condition_truth": self.composite_condition_truth,
            "hard_filter_match": self.hard_filter_match,
            "included_by_unknown_policy": self.included_by_unknown_policy,
            "row_identity_sha256": self.row_identity_sha256,
        }


def _rows_sha(rows: Sequence[DailyMarketTechnicalOfficialDispositionMaResultRowV1]) -> str:
    return _sha256_json([row.to_dict() for row in rows])


def _result_identity(
    *,
    query: DailyMarketTechnicalOfficialDispositionMaQueryV1,
    source_pins: tuple[tuple[str, str], ...],
    counts: DailyMarketTechnicalOfficialDispositionMaCountsV1,
    ordered_keys: tuple[DailyMarketTechnicalOfficialDispositionMaSortKeyV1, ...],
    result_status: str,
    official_coverage_status: str,
) -> str:
    _validate_result_source_pins(query, source_pins)
    return _sha256_json({
        "schema_version": "daily-market-technical-official-disposition-ma-result.v1",
        "query_identity_sha256": query.query_identity_sha256,
        "source_pins": [[key, value] for key, value in source_pins],
        "counts": counts.to_dict(),
        "ordered_keys_sha256": _sha256_json([item.to_dict() for item in ordered_keys]),
        "ordered_codes_sha256": _sha256_json([item.stock_code for item in ordered_keys]),
        "result_status": result_status,
        "official_source_coverage_status": official_coverage_status,
        "scope": "current_only",
        "official_available_at": None,
        "historical_pit_eligible": False,
    })


def _validate_result_source_pins(
    query: DailyMarketTechnicalOfficialDispositionMaQueryV1,
    source_pins: tuple[tuple[str, str], ...],
) -> None:
    if not isinstance(source_pins, tuple):
        _fail("result_source_pins_invalid")
    if any(
        not isinstance(item, tuple)
        or len(item) != 2
        or not isinstance(item[0], str)
        or not isinstance(item[1], str)
        or not item[1]
        for item in source_pins
    ):
        _fail("result_source_pins_invalid")
    if tuple(key for key, _value in source_pins) != _SOURCE_PIN_KEYS:
        _fail("result_source_pins_invalid")
    pins = dict(source_pins)
    for key in _SOURCE_PIN_KEYS:
        if key.endswith("_sha256"):
            _require_sha(pins[key], "result_source_pin_sha_invalid")
    f17 = query.f17_query
    if (
        pins["bundle_output_root"] != f17.bundle_output_root
        or pins["bundle_identity_sha256"] != f17.bundle_identity_sha256
        or pins["bundle_manifest_sha256"] != f17.expected_manifest_sha256
        or pins["market_assignment_pin_identity_sha256"] != f17.market_assignment_pin_identity_sha256
        or pins["official_disposal_pin_identity_sha256"] != f17.official_disposal_pin_identity_sha256
        or pins["decision_date"] != f17.decision_date.isoformat()
        or pins["decision_cutoff"] != f17.decision_cutoff.isoformat()
        or pins["ma_method_id"] != DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_ID_V1
        or pins["ma_method_version"] != DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_VERSION_V1
    ):
        _fail("result_source_scope_mismatch")


_ANCHOR_ISSUER = object()


class _ResultAnchorV1:
    """不可由 dataclasses.replace 重建的每次發行錨點。"""

    __slots__ = (
        "identity_sha256", "keys_sha256", "counts_sha256", "pins_sha256",
        "read_session", "query", "_subject", "_locked",
    )

    identity_sha256: str
    keys_sha256: str
    counts_sha256: str
    pins_sha256: str
    read_session: object
    query: object
    _subject: object | None
    _locked: bool

    def __init__(
        self,
        identity_sha256: str,
        keys_sha256: str,
        counts_sha256: str,
        pins_sha256: str,
        read_session: object,
        query: object,
        *,
        issuer: object,
    ) -> None:
        if issuer is not _ANCHOR_ISSUER:
            _fail("result_anchor_issuer_invalid")
        for value in (identity_sha256, keys_sha256, counts_sha256, pins_sha256):
            _require_sha(value, "result_anchor_identity_invalid")
        object.__setattr__(self, "identity_sha256", identity_sha256)
        object.__setattr__(self, "keys_sha256", keys_sha256)
        object.__setattr__(self, "counts_sha256", counts_sha256)
        object.__setattr__(self, "pins_sha256", pins_sha256)
        object.__setattr__(self, "read_session", read_session)
        object.__setattr__(self, "query", query)
        object.__setattr__(self, "_subject", None)
        object.__setattr__(self, "_locked", True)

    def can_claim(self, subject: object) -> bool:
        return self._subject is None or self._subject is subject

    def claim(self, subject: object) -> None:
        if not self.can_claim(subject):
            _fail("result_anchor_subject_mismatch")
        if self._subject is None:
            object.__setattr__(self, "_subject", subject)

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_locked", False):
            raise AttributeError("result issuance anchor is immutable")
        object.__setattr__(self, name, value)


class _PageAnchorV1:
    """不可由 dataclasses.replace 重建的每頁原始結果錨點。"""

    __slots__ = (
        "identity_sha256", "rows_sha256", "request_identity_sha256",
        "result", "_subject", "_locked",
    )

    identity_sha256: str
    rows_sha256: str
    request_identity_sha256: str
    result: object
    _subject: object | None
    _locked: bool

    def __init__(
        self,
        identity_sha256: str,
        rows_sha256: str,
        request_identity_sha256: str,
        result: object,
        *,
        issuer: object,
    ) -> None:
        if issuer is not _ANCHOR_ISSUER:
            _fail("page_anchor_issuer_invalid")
        for value in (identity_sha256, rows_sha256, request_identity_sha256):
            _require_sha(value, "page_anchor_identity_invalid")
        object.__setattr__(self, "identity_sha256", identity_sha256)
        object.__setattr__(self, "rows_sha256", rows_sha256)
        object.__setattr__(self, "request_identity_sha256", request_identity_sha256)
        object.__setattr__(self, "result", result)
        object.__setattr__(self, "_subject", None)
        object.__setattr__(self, "_locked", True)

    def can_claim(self, subject: object) -> bool:
        return self._subject is None or self._subject is subject

    def claim(self, subject: object) -> None:
        if not self.can_claim(subject):
            _fail("page_anchor_subject_mismatch")
        if self._subject is None:
            object.__setattr__(self, "_subject", subject)

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_locked", False):
            raise AttributeError("page issuance anchor is immutable")
        object.__setattr__(self, name, value)


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionMaVerifiedQueryResultV1:
    query: DailyMarketTechnicalOfficialDispositionMaQueryV1
    operation_identity_sha256: str
    ordered_codes_sha256: str
    counts: DailyMarketTechnicalOfficialDispositionMaCountsV1
    source_pins: tuple[tuple[str, str], ...]
    ordered_sort_keys: tuple[DailyMarketTechnicalOfficialDispositionMaSortKeyV1, ...]
    result_status: Literal["complete", "partial"]
    official_source_coverage_status: Literal["complete", "partial"]
    scope: Literal["current_only"]
    official_available_at: None
    availability_status: Literal["unknown"]
    historical_pit_eligible: Literal[False]
    _read_session: object = field(repr=False, compare=False)
    _anchor: _ResultAnchorV1 = field(repr=False, compare=False)
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            self._seal is not _RESULT_SEAL
            or type(self._anchor) is not _ResultAnchorV1
            or not self._anchor.can_claim(self)
            or self._anchor.read_session is not self._read_session
            or self._anchor.query is not self.query
            or self._anchor.identity_sha256 != self.operation_identity_sha256
            or self._anchor.keys_sha256 != _sha256_json([item.to_dict() for item in self.ordered_sort_keys])
            or self._anchor.counts_sha256 != _sha256_json(self.counts.to_dict())
            or self._anchor.pins_sha256 != _sha256_json([[key, value] for key, value in self.source_pins])
            or self.scope != "current_only"
            or self.official_available_at is not None
            or self.availability_status != "unknown"
            or self.historical_pit_eligible is not False
            or self.result_status not in {"complete", "partial"}
            or self.official_source_coverage_status not in {"complete", "partial"}
            or len(self.ordered_sort_keys) != self.counts.visible_count
            or self.counts.visible_count > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_ROWS
            or self.ordered_codes_sha256 != _sha256_json([item.stock_code for item in self.ordered_sort_keys])
            or _result_identity(
                query=self.query,
                source_pins=self.source_pins,
                counts=self.counts,
                ordered_keys=self.ordered_sort_keys,
                result_status=self.result_status,
                official_coverage_status=self.official_source_coverage_status,
            ) != self.operation_identity_sha256
        ):
            _fail("result_not_reader_issued")
        self._anchor.claim(self)

    @property
    def matching_count(self) -> int:
        """相容別名：表示政策後可見筆數，不表示 predicate truth=match。"""
        return self.visible_count

    @property
    def visible_count(self) -> int:
        return self.counts.visible_count

    def read_page(
        self,
        page_index: int,
        page_size: int,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalOfficialDispositionMaQueryPageV1:
        _strict_cancel(cancel_callback)
        request = DailyMarketTechnicalOfficialDispositionMaPageRequestV1.create(
            self.query, page_index=page_index, page_size=page_size,
        )
        return self.read_page_request(request, cancel_callback=cancel_callback)

    def read_page_request(
        self,
        request: DailyMarketTechnicalOfficialDispositionMaPageRequestV1 | bytes | str,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalOfficialDispositionMaQueryPageV1:
        _strict_cancel(cancel_callback)
        if self._seal is not _RESULT_SEAL:
            _fail("result_not_reader_issued")
        self.__post_init__()
        if isinstance(request, (bytes, str)):
            request = DailyMarketTechnicalOfficialDispositionMaPageRequestV1.from_json(request)
        if type(request) is not DailyMarketTechnicalOfficialDispositionMaPageRequestV1:
            _fail("page_request_invalid")
        if request.query.query_identity_sha256 != self.query.query_identity_sha256:
            _fail("page_request_query_mismatch")
        reader = getattr(self._read_session, "_materialize_ma_query_page_v1", None)
        if not callable(reader):
            _fail("read_session_page_reader_unavailable")
        return cast(Any, reader)(self, request, cancel_callback)


def _validate_page_request_for_result_v1(
    result: DailyMarketTechnicalOfficialDispositionMaVerifiedQueryResultV1,
    request: DailyMarketTechnicalOfficialDispositionMaPageRequestV1,
) -> None:
    """核對單頁請求屬於指定的 reader-issued 全域結果。"""
    if (
        type(result) is not DailyMarketTechnicalOfficialDispositionMaVerifiedQueryResultV1
        or type(request) is not DailyMarketTechnicalOfficialDispositionMaPageRequestV1
    ):
        _fail("page_request_input_invalid")
    result.__post_init__()
    try:
        request_json = request.to_json()
        request_query = request.query
        expected_request = DailyMarketTechnicalOfficialDispositionMaPageRequestV1.create(
            result.query,
            page_index=request.page_index,
            page_size=request.page_size,
        )
    except (ValueError, TypeError) as exc:
        raise DailyMarketTechnicalOfficialDispositionMaQueryV1Error(
            "technical_official_ma_query_v1_page_request_invalid"
        ) from exc
    if (
        request_query.query_identity_sha256 != result.query.query_identity_sha256
        or request_json != expected_request.to_json()
    ):
        _fail("page_request_query_mismatch")
    page_count = (result.visible_count + request.page_size - 1) // request.page_size
    if (page_count == 0 and request.page_index != 0) or (
        page_count > 0 and request.page_index >= page_count
    ):
        _fail("page_request_out_of_range")


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionMaQueryPageV1:
    query: DailyMarketTechnicalOfficialDispositionMaQueryV1
    request_identity_sha256: str
    operation_identity_sha256: str
    page_identity_sha256: str
    page_index: int
    page_size: int
    page_count: int
    counts: DailyMarketTechnicalOfficialDispositionMaCountsV1
    rows: tuple[DailyMarketTechnicalOfficialDispositionMaResultRowV1, ...]
    source_pins: tuple[tuple[str, str], ...]
    result_status: Literal["complete", "partial"]
    official_source_coverage_status: Literal["complete", "partial"]
    scope: Literal["current_only"]
    official_available_at: None
    availability_status: Literal["unknown"]
    historical_pit_eligible: Literal[False]
    _result: DailyMarketTechnicalOfficialDispositionMaVerifiedQueryResultV1 = field(repr=False, compare=False)
    _anchor: _PageAnchorV1 = field(repr=False, compare=False)
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        _validate_page(self.page_index, self.page_size)
        if (
            self._seal is not _PAGE_SEAL
            or type(self._anchor) is not _PageAnchorV1
            or not self._anchor.can_claim(self)
            or self._anchor.result is not self._result
            or self._anchor.identity_sha256 != self.page_identity_sha256
            or self._anchor.rows_sha256 != _rows_sha(self.rows)
            or self._anchor.request_identity_sha256 != self.request_identity_sha256
            or self.query is not self._result.query
            or self.operation_identity_sha256 != self._result.operation_identity_sha256
            or self.counts != self._result.counts
            or self.source_pins != self._result.source_pins
            or self.result_status != self._result.result_status
            or self.official_source_coverage_status != self._result.official_source_coverage_status
            or self.scope != "current_only"
            or self.official_available_at is not None
            or self.availability_status != "unknown"
            or self.historical_pit_eligible is not False
            or self.page_count != (self.counts.visible_count + self.page_size - 1) // self.page_size
            or len(self.rows) > self.page_size
        ):
            _fail("page_not_reader_issued")
        request = DailyMarketTechnicalOfficialDispositionMaPageRequestV1.create(
            self.query, page_index=self.page_index, page_size=self.page_size,
        )
        expected = _page_identity(
            result=self._result,
            request=request,
            rows=self.rows,
        )
        if expected != self.page_identity_sha256 or request.request_identity_sha256 != self.request_identity_sha256:
            _fail("page_identity_mismatch")
        self._anchor.claim(self)

    @property
    def matching_count(self) -> int:
        """相容別名：表示政策後可見筆數，不表示 predicate truth=match。"""
        return self.visible_count

    @property
    def visible_count(self) -> int:
        return self.counts.visible_count

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "daily-market-technical-official-disposition-ma-page.v1",
            "query": self.query.to_dict(),
            "request_identity_sha256": self.request_identity_sha256,
            "operation_identity_sha256": self.operation_identity_sha256,
            "page_identity_sha256": self.page_identity_sha256,
            "page_index": self.page_index,
            "page_size": self.page_size,
            "page_count": self.page_count,
            "visible_count": self.visible_count,
            "counts": self.counts.to_dict(),
            "rows": [row.to_dict() for row in self.rows],
            "source_pins": [[key, value] for key, value in self.source_pins],
            "result_status": self.result_status,
            "official_source_coverage_status": self.official_source_coverage_status,
            "scope": self.scope,
            "official_available_at": None,
            "availability_status": "unknown",
            "historical_pit_eligible": False,
        }


def _page_identity(
    *,
    result: DailyMarketTechnicalOfficialDispositionMaVerifiedQueryResultV1,
    request: DailyMarketTechnicalOfficialDispositionMaPageRequestV1,
    rows: tuple[DailyMarketTechnicalOfficialDispositionMaResultRowV1, ...],
) -> str:
    return _sha256_json({
        "schema_version": "daily-market-technical-official-disposition-ma-page.v1",
        "query_identity_sha256": result.query.query_identity_sha256,
        "request_identity_sha256": request.request_identity_sha256,
        "operation_identity_sha256": result.operation_identity_sha256,
        "page_index": request.page_index,
        "page_size": request.page_size,
        "visible_count": result.counts.visible_count,
        "rows": [row.to_dict() for row in rows],
        "source_pins": [[key, value] for key, value in result.source_pins],
        "availability_status": "unknown",
        "historical_pit_eligible": False,
    })


def _issue_result_v1(
    *,
    query: DailyMarketTechnicalOfficialDispositionMaQueryV1,
    counts: DailyMarketTechnicalOfficialDispositionMaCountsV1,
    source_pins: tuple[tuple[str, str], ...],
    ordered_keys: tuple[DailyMarketTechnicalOfficialDispositionMaSortKeyV1, ...],
    result_status: Literal["complete", "partial"],
    official_source_coverage_status: Literal["complete", "partial"],
    read_session: object,
) -> DailyMarketTechnicalOfficialDispositionMaVerifiedQueryResultV1:
    operation = _result_identity(
        query=query,
        source_pins=source_pins,
        counts=counts,
        ordered_keys=ordered_keys,
        result_status=result_status,
        official_coverage_status=official_source_coverage_status,
    )
    return DailyMarketTechnicalOfficialDispositionMaVerifiedQueryResultV1(
        query=query,
        operation_identity_sha256=operation,
        ordered_codes_sha256=_sha256_json([item.stock_code for item in ordered_keys]),
        counts=counts,
        source_pins=source_pins,
        ordered_sort_keys=ordered_keys,
        result_status=result_status,
        official_source_coverage_status=official_source_coverage_status,
        scope="current_only",
        official_available_at=None,
        availability_status="unknown",
        historical_pit_eligible=False,
        _read_session=read_session,
        _anchor=_ResultAnchorV1(
            identity_sha256=operation,
            keys_sha256=_sha256_json([item.to_dict() for item in ordered_keys]),
            counts_sha256=_sha256_json(counts.to_dict()),
            pins_sha256=_sha256_json([[key, value] for key, value in source_pins]),
            read_session=read_session,
            query=query,
            issuer=_ANCHOR_ISSUER,
        ),
        _seal=_RESULT_SEAL,
    )


def _issue_page_v1(
    *,
    result: DailyMarketTechnicalOfficialDispositionMaVerifiedQueryResultV1,
    request: DailyMarketTechnicalOfficialDispositionMaPageRequestV1,
    rows: tuple[DailyMarketTechnicalOfficialDispositionMaResultRowV1, ...],
) -> DailyMarketTechnicalOfficialDispositionMaQueryPageV1:
    identity = _page_identity(result=result, request=request, rows=rows)
    return DailyMarketTechnicalOfficialDispositionMaQueryPageV1(
        query=result.query,
        request_identity_sha256=request.request_identity_sha256,
        operation_identity_sha256=result.operation_identity_sha256,
        page_identity_sha256=identity,
        page_index=request.page_index,
        page_size=request.page_size,
        page_count=(result.counts.visible_count + request.page_size - 1) // request.page_size,
        counts=result.counts,
        rows=rows,
        source_pins=result.source_pins,
        result_status=result.result_status,
        official_source_coverage_status=result.official_source_coverage_status,
        scope="current_only",
        official_available_at=None,
        availability_status="unknown",
        historical_pit_eligible=False,
        _result=result,
        _anchor=_PageAnchorV1(
            identity,
            _rows_sha(rows),
            request.request_identity_sha256,
            result,
            issuer=_ANCHOR_ISSUER,
        ),
        _seal=_PAGE_SEAL,
    )

