"""F17、MA、KDJ 三群條件的未核資格查詢契約。

本模組只驗證 canonical request、純三值 predicate 與有界排序投影；不讀來源、
不發 reader-qualified result/page。KDJ evidence 必須是 typed compact entry，且
呼叫端仍須由未來的 F17 exact observer 核對同一 snapshot/source pins。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import re
from typing import Any, Literal, NoReturn, cast

from app_module.daily_market_technical_kdj_evidence_v1 import (
    KDJ_METHOD_IDENTITY_SHA256_V1,
    KDJ_METHOD_ID_V1,
    KDJ_METHOD_VERSION_V1,
)
from app_module.daily_market_technical_official_disposition_ma_query_v1 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_PAGE_SIZE,
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_ROWS,
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_SORT_CLAUSES,
    DailyMarketTechnicalOfficialDispositionMaQueryV1,
    combine_truth_v1,
)
from app_module.daily_market_technical_universe_kdj_alignment_query_v1 import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_SOURCE_REQUEST_V1_SCHEMA,
    DailyMarketTechnicalUniverseKDJCompactEntryV1,
    DailyMarketTechnicalUniverseKDJSourceRequestV1,
)
from app_module.daily_market_technical_universe_ma_alignment_query_v1 import (
    DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_SOURCE_REQUEST_V1_SCHEMA,
    DailyMarketTechnicalMaAlignmentSourceRequestV1,
)

DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_KDJ_QUERY_V1_SCHEMA = (
    "daily-market-technical-official-disposition-kdj-query.v1"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_KDJ_PAGE_REQUEST_V1_SCHEMA = (
    "daily-market-technical-official-disposition-kdj-page-request.v1"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_KDJ_QUERY_V1_MAX_BYTES = 32 * 1024 * 1024
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_KDJ_SOURCE_REQUEST_MAX_BYTES = 16 * 1024
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_KDJ_MAX_JSON_DEPTH = 32
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_KDJ_MAX_SORT_PROJECTION_BYTES = 64 * 1024 * 1024
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_KDJ_MAX_DECIMAL_TOKEN_BYTES = 96
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_KDJ_MAX_TEXT_TOKEN_BYTES = 256
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_KDJ_MAX_INTEGER_BITS = 127
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_KDJ_MAX_PAGE_INDEX = 1_000_000

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STOCK_CODE_RE = re.compile(r"^[A-Z0-9]{1,16}$")
_KDJ_STATES = ("match", "no_match", "unknown")
_TRUTHS = {"match", "no_match", "unknown", "not_evaluated", "not_applicable"}
_COMBINE_MODES = {"AND", "OR"}
_UNKNOWN_POLICIES = {"include", "exclude", "only"}
_DIRECTIONS = {"asc", "desc"}
_F17_SORT_FIELDS = {
    "stock_code", "decision_date", "latest_feature_date", "raw_row_count",
    "market_assignment.state", "market_assignment.snapshot_observed_at",
    "official_disposal.state", "official_disposal.observed_at",
    "official_disposal.observed_date",
}
_KDJ_QUERY_FIELDS = {
    "schema_version", "verification_status", "ma_query_json",
    "ma_query_identity_sha256", "kdj_source_request_json",
    "kdj_source_request_identity_sha256", "kdj_read_session_identity_sha256",
    "kdj_index_identity_sha256", "kdj_source_clock_identity_sha256",
    "kdj_method_id", "kdj_method_version", "kdj_method_identity_sha256",
    "ma_states", "kdj_states", "condition_combine_mode", "unknown_policy", "sort_clauses",
    "source_available_at", "availability_status", "historical_pit_eligible",
    "reader_qualified", "query_identity_sha256",
}
_PAGE_FIELDS = {
    "schema_version", "query_json", "query_identity_sha256", "page_index",
    "page_size", "request_identity_sha256",
}

KDJTruth = Literal["match", "no_match", "unknown", "not_evaluated", "not_applicable"]
CombineMode = Literal["AND", "OR"]
UnknownPolicy = Literal["include", "exclude", "only"]
SortDirection = Literal["asc", "desc"]
SortScalar = str | int | Decimal | date | datetime


class DailyMarketTechnicalOfficialDispositionKDJQueryV1Error(ValueError):
    """F17/MA/KDJ 查詢契約的穩定拒絕碼。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"technical_official_kdj_query_v1_{code}")


def _fail(code: str) -> NoReturn:
    raise DailyMarketTechnicalOfficialDispositionKDJQueryV1Error(code)


def _require_sha(value: object, code: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        _fail(code)
    return cast(str, value)


def _check_integer(value: object, code: str) -> int:
    if type(value) is not int or value.bit_length() > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_KDJ_MAX_INTEGER_BITS:
        _fail(code)
    return cast(int, value)


def _reject_unsafe_tree(value: object, *, depth: int = 0) -> None:
    if depth > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_KDJ_MAX_JSON_DEPTH:
        _fail("json_depth_limit")
    if isinstance(value, float):
        _fail("float_forbidden")
    if type(value) is int:
        _check_integer(value, "integer_bounds_invalid")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if type(key) is not str:
                _fail("json_key_invalid")
            if len(key.encode("utf-8")) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_KDJ_MAX_TEXT_TOKEN_BYTES:
                _fail("json_key_too_long")
            _reject_unsafe_tree(item, depth=depth + 1)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_unsafe_tree(item, depth=depth + 1)


def _canonical_json_bytes(value: object) -> bytes:
    _reject_unsafe_tree(value)
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise DailyMarketTechnicalOfficialDispositionKDJQueryV1Error("json_invalid") from exc


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail("duplicate_json_key")
        result[key] = value
    return result


def _preflight_json_depth(text: str) -> None:
    depth = 0
    quoted = False
    escaped = False
    for character in text:
        if quoted:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = False
            continue
        if character == '"':
            quoted = True
        elif character in "[{":
            depth += 1
            if depth > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_KDJ_MAX_JSON_DEPTH:
                _fail("json_depth_limit")
        elif character in "]}":
            depth -= 1
            if depth < 0:
                _fail("json_invalid")
    if quoted or escaped or depth != 0:
        _fail("json_invalid")


def _parse_json(raw: bytes | str, *, maximum: int, code: str = "json_invalid") -> object:
    if type(raw) not in {bytes, str}:
        _fail(code)
    try:
        encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
        if type(encoded) is not bytes or len(encoded) > maximum:
            _fail("json_byte_limit")
        text = encoded.decode("utf-8")
        _preflight_json_depth(text)

        def parse_integer(token: str) -> int:
            digits = token[1:] if token.startswith("-") else token
            if len(digits) > 39:
                _fail("integer_bounds_invalid")
            return _check_integer(int(token), "integer_bounds_invalid")

        payload = json.loads(
            text, object_pairs_hook=_unique_pairs,
            parse_float=lambda _text: _fail("float_forbidden"),
            parse_int=parse_integer,
            parse_constant=lambda _text: _fail("json_invalid"),
        )
        _reject_unsafe_tree(payload)
        if _canonical_json_bytes(payload) != encoded:
            _fail("json_noncanonical")
        return payload
    except DailyMarketTechnicalOfficialDispositionKDJQueryV1Error:
        raise
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError, RecursionError) as exc:
        raise DailyMarketTechnicalOfficialDispositionKDJQueryV1Error(code) from exc


def _strict_cancel(callback: Callable[[], object] | None) -> None:
    if callback is None:
        return
    if not callable(callback):
        _fail("cancel_callback_invalid")
    try:
        cancelled = callback()
    except Exception as exc:
        raise DailyMarketTechnicalOfficialDispositionKDJQueryV1Error("cancel_check_failed") from exc
    if type(cancelled) is not bool:
        _fail("cancel_callback_invalid")
    if cancelled:
        _fail("cancelled")


def _parse_date(value: object, code: str) -> date:
    if type(value) is not str:
        _fail(code)
    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise DailyMarketTechnicalOfficialDispositionKDJQueryV1Error(code) from exc
    if result.isoformat() != value:
        _fail(code)
    return result


def _ma_source_request_from_payload(value: object) -> DailyMarketTechnicalMaAlignmentSourceRequestV1:
    keys = {
        "schema_version", "verification_status", "bundle_output_root",
        "bundle_identity_sha256", "manifest_relative_path", "expected_manifest_sha256",
        "technical_store_output_root", "generation_identity_sha256", "plan_identity_sha256",
        "plan_sha256", "receipt_identity_sha256", "receipt_sha256", "cohort_identity_sha256",
        "source_clock_identity_sha256", "method_contracts_sha256",
        "market_assignment_pin_identity_sha256", "official_disposal_pin_identity_sha256",
        "decision_date", "decision_cutoff", "declared_count", "included_count",
        "excluded_count", "source_coverage_status", "source_coverage_incomplete_reason_count",
        "technical_receipt_status", "source_available_at", "availability_status",
        "historical_pit_eligible",
    }
    if not isinstance(value, Mapping) or set(value) != keys:
        _fail("ma_source_request_fields_invalid")
    if (
        value.get("schema_version") != DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_SOURCE_REQUEST_V1_SCHEMA
        or value.get("verification_status") != "metadata_unverified"
        or value.get("source_available_at") is not None
        or value.get("availability_status") != "unknown"
        or value.get("historical_pit_eligible") is not False
    ):
        _fail("ma_source_request_policy_invalid")
    result = DailyMarketTechnicalMaAlignmentSourceRequestV1(
        bundle_output_root=cast(str, value.get("bundle_output_root")),
        bundle_identity_sha256=cast(str, value.get("bundle_identity_sha256")),
        manifest_relative_path=cast(str, value.get("manifest_relative_path")),
        expected_manifest_sha256=cast(str, value.get("expected_manifest_sha256")),
        technical_store_output_root=cast(str, value.get("technical_store_output_root")),
        generation_identity_sha256=cast(str, value.get("generation_identity_sha256")),
        plan_identity_sha256=cast(str, value.get("plan_identity_sha256")),
        plan_sha256=cast(str, value.get("plan_sha256")),
        receipt_identity_sha256=cast(str, value.get("receipt_identity_sha256")),
        receipt_sha256=cast(str, value.get("receipt_sha256")),
        cohort_identity_sha256=cast(str, value.get("cohort_identity_sha256")),
        source_clock_identity_sha256=cast(str, value.get("source_clock_identity_sha256")),
        method_contracts_sha256=cast(str, value.get("method_contracts_sha256")),
        market_assignment_pin_identity_sha256=cast(str, value.get("market_assignment_pin_identity_sha256")),
        official_disposal_pin_identity_sha256=cast(str, value.get("official_disposal_pin_identity_sha256")),
        decision_date=_parse_date(value.get("decision_date"), "ma_source_request_date_invalid"),
        decision_cutoff=cast(str, value.get("decision_cutoff")),
        declared_count=cast(int, value.get("declared_count")),
        included_count=cast(int, value.get("included_count")),
        excluded_count=cast(int, value.get("excluded_count")),
        source_coverage_status=cast(Any, value.get("source_coverage_status")),
        source_coverage_incomplete_reason_count=cast(int, value.get("source_coverage_incomplete_reason_count")),
        technical_receipt_status=cast(Any, value.get("technical_receipt_status")),
    )
    if result.to_dict() != dict(value):
        _fail("ma_source_request_noncanonical")
    return result


def _source_request_from_json(raw: str) -> DailyMarketTechnicalUniverseKDJSourceRequestV1:
    payload = _parse_json(
        raw,
        maximum=DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_KDJ_SOURCE_REQUEST_MAX_BYTES,
        code="source_request_json_invalid",
    )
    expected = {
        "schema_version", "verification_status", "ma_source_request",
        "kdj_method_id", "kdj_method_version", "kdj_method_identity_sha256",
        "source_available_at", "availability_status", "historical_pit_eligible",
        "request_identity_sha256",
    }
    if not isinstance(payload, Mapping) or set(payload) != expected:
        _fail("source_request_fields_invalid")
    if (
        payload.get("schema_version") != DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_SOURCE_REQUEST_V1_SCHEMA
        or payload.get("verification_status") != "metadata_unverified"
        or payload.get("kdj_method_id") != KDJ_METHOD_ID_V1
        or payload.get("kdj_method_version") != KDJ_METHOD_VERSION_V1
        or payload.get("kdj_method_identity_sha256") != KDJ_METHOD_IDENTITY_SHA256_V1
        or payload.get("source_available_at") is not None
        or payload.get("availability_status") != "unknown"
        or payload.get("historical_pit_eligible") is not False
    ):
        _fail("source_request_policy_invalid")
    try:
        ma_source = _ma_source_request_from_payload(payload.get("ma_source_request"))
    except DailyMarketTechnicalOfficialDispositionKDJQueryV1Error:
        raise
    except (TypeError, ValueError, UnicodeError, OverflowError) as exc:
        raise DailyMarketTechnicalOfficialDispositionKDJQueryV1Error("ma_source_request_invalid") from exc
    identity = _require_sha(payload.get("request_identity_sha256"), "source_request_identity_invalid")
    body = {key: item for key, item in payload.items() if key != "request_identity_sha256"}
    if _sha256_json(body) != identity:
        _fail("source_request_identity_mismatch")
    result = DailyMarketTechnicalUniverseKDJSourceRequestV1(
        ma_source_request=ma_source,
        request_identity_sha256=identity,
    )
    try:
        if result.to_dict() != dict(payload):
            _fail("source_request_noncanonical")
    except DailyMarketTechnicalOfficialDispositionKDJQueryV1Error:
        raise
    except (TypeError, ValueError, UnicodeError, OverflowError) as exc:
        raise DailyMarketTechnicalOfficialDispositionKDJQueryV1Error("source_request_invalid") from exc
    return result


def _parse_ma_query(raw: object) -> DailyMarketTechnicalOfficialDispositionMaQueryV1:
    if type(raw) is not str or len(raw.encode("utf-8")) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_KDJ_QUERY_V1_MAX_BYTES:
        _fail("ma_query_invalid")
    try:
        query = DailyMarketTechnicalOfficialDispositionMaQueryV1.from_json(raw)
    except (ValueError, TypeError, UnicodeError) as exc:
        raise DailyMarketTechnicalOfficialDispositionKDJQueryV1Error("ma_query_invalid") from exc
    if query.to_json() != raw:
        _fail("ma_query_noncanonical")
    if (
        query.ma_states is not None
        or query.condition_combine_mode != "AND"
        or query.unknown_policy != "include"
        or len(query.sort_clauses) != 1
        or query.sort_clauses[0].field != "stock_code"
        or query.sort_clauses[0].direction != "asc"
    ):
        _fail("nested_ma_query_not_neutral")
    return query


def _validate_source_pair(
    ma_query: DailyMarketTechnicalOfficialDispositionMaQueryV1,
    kdj_request: DailyMarketTechnicalUniverseKDJSourceRequestV1,
) -> None:
    request = kdj_request.ma_source_request
    f17 = ma_query.f17_query
    if (
        _sha256_json(request.to_dict()) != ma_query.ma_source_request_identity_sha256
        or request.bundle_output_root != str(f17.bundle_output_root)
        or request.bundle_identity_sha256 != f17.bundle_identity_sha256
        or request.expected_manifest_sha256 != f17.expected_manifest_sha256
        or request.market_assignment_pin_identity_sha256 != f17.market_assignment_pin_identity_sha256
        or request.official_disposal_pin_identity_sha256 != f17.official_disposal_pin_identity_sha256
        or request.decision_date != f17.decision_date
        or request.decision_cutoff != f17.decision_cutoff.isoformat()
        or request.technical_store_output_root != f17.technical_query.store_output_root
        or request.generation_identity_sha256 != f17.technical_query.generation_identity_sha256
        or request.plan_identity_sha256 != f17.technical_query.plan_identity_sha256
        or request.plan_sha256 != f17.technical_query.plan_sha256
        or request.receipt_identity_sha256 != f17.technical_query.receipt_identity_sha256
        or request.receipt_sha256 != f17.technical_query.receipt_sha256
        or request.cohort_identity_sha256 != f17.technical_query.cohort_identity_sha256
        or request.source_clock_identity_sha256 != f17.technical_query.source_clock_identity_sha256
        or request.method_contracts_sha256 != f17.technical_query.method_contracts_sha256
        or request.declared_count != f17.technical_query.declared_count
        or request.included_count != f17.technical_query.included_count
        or request.excluded_count != f17.technical_query.excluded_count
    ):
        _fail("source_scope_mismatch")


def _normalize_states(values: Sequence[str] | None) -> tuple[str, ...] | None:
    if values is None:
        return None
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        _fail("kdj_states_invalid")
    items = tuple(values)
    if (
        not items
        or any(type(item) is not str or item not in _KDJ_STATES for item in items)
        or len(set(items)) != len(items)
    ):
        _fail("kdj_states_invalid")
    return tuple(item for item in _KDJ_STATES if item in items)


def _normalize_ma_states(values: Sequence[str] | None) -> tuple[str, ...] | None:
    if values is None:
        return None
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        _fail("ma_states_invalid")
    items = tuple(values)
    if (
        not items
        or any(type(item) is not str or item not in {"match", "no_match", "unknown"} for item in items)
        or len(set(items)) != len(items)
    ):
        _fail("ma_states_invalid")
    order = ("match", "no_match", "unknown")
    return tuple(item for item in order if item in items)


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionKDJSortClauseV1:
    """一個全母體排序欄位與方向；未知值在兩種方向都固定排尾。"""

    field: str
    direction: SortDirection

    def __post_init__(self) -> None:
        if type(self.field) is not str or not self.field or len(self.field.encode("utf-8")) > 128:
            _fail("sort_clause_invalid")
        if type(self.direction) is not str or self.direction not in _DIRECTIONS:
            _fail("sort_clause_invalid")

    def to_dict(self) -> dict[str, str]:
        return {"field": self.field, "direction": self.direction}

    @classmethod
    def from_dict(cls, value: object) -> DailyMarketTechnicalOfficialDispositionKDJSortClauseV1:
        if not isinstance(value, Mapping) or set(value) != {"field", "direction"}:
            _fail("sort_clause_invalid")
        field_name = value.get("field")
        direction = value.get("direction")
        if type(field_name) is not str or type(direction) is not str or direction not in _DIRECTIONS:
            _fail("sort_clause_invalid")
        return cls(field_name, cast(SortDirection, direction))


def _active_group_count(
    ma_query: DailyMarketTechnicalOfficialDispositionMaQueryV1,
    ma_states: tuple[str, ...] | None,
    kdj_states: tuple[str, ...] | None,
) -> int:
    return (
        int(bool(ma_query.f17_query.technical_query.rule_state_filters))
        + int(ma_states is not None)
        + int(kdj_states is not None)
    )


def _query_body(query: DailyMarketTechnicalOfficialDispositionKDJQueryV1) -> dict[str, object]:
    return {
        "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_KDJ_QUERY_V1_SCHEMA,
        "verification_status": "request_only",
        "ma_query_json": query.ma_query_json,
        "ma_query_identity_sha256": query.ma_query_identity_sha256,
        "kdj_source_request_json": query.kdj_source_request_json,
        "kdj_source_request_identity_sha256": query.kdj_source_request_identity_sha256,
        "kdj_read_session_identity_sha256": query.kdj_read_session_identity_sha256,
        "kdj_index_identity_sha256": query.kdj_index_identity_sha256,
        "kdj_source_clock_identity_sha256": query.kdj_source_clock_identity_sha256,
        "kdj_method_id": KDJ_METHOD_ID_V1,
        "kdj_method_version": KDJ_METHOD_VERSION_V1,
        "kdj_method_identity_sha256": KDJ_METHOD_IDENTITY_SHA256_V1,
        "ma_states": None if query.ma_states is None else list(query.ma_states),
        "kdj_states": None if query.kdj_states is None else list(query.kdj_states),
        "condition_combine_mode": query.condition_combine_mode,
        "unknown_policy": query.unknown_policy,
        "sort_clauses": [item.to_dict() for item in query.sort_clauses],
        "source_available_at": None,
        "availability_status": "unknown",
        "historical_pit_eligible": False,
        "reader_qualified": False,
    }


def _enforce_query_budget(body: Mapping[str, object]) -> None:
    # 外層 canonical 長度含巢狀 JSON 字串的 escaping 與所有 identity 欄位。
    payload = {**body, "query_identity_sha256": "0" * 64}
    if len(_canonical_json_bytes(payload)) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_KDJ_QUERY_V1_MAX_BYTES:
        _fail("query_byte_limit")


def _validate_sort_fields(
    ma_query: DailyMarketTechnicalOfficialDispositionMaQueryV1,
    clauses: Sequence[DailyMarketTechnicalOfficialDispositionKDJSortClauseV1],
) -> None:
    allowed = set(_F17_SORT_FIELDS)
    for rule_key in ma_query.f17_query.technical_query.method_rule_keys:
        allowed.update(f"{rule_key}.{field}" for field in ("ratio", "numerator", "denominator"))
    allowed.update({
        "ma_alignment_state", "kdj_state",
        "kdj_previous.feature_date", "kdj_previous.rsv", "kdj_previous.k",
        "kdj_previous.d", "kdj_previous.j", "kdj_current.feature_date",
        "kdj_current.rsv", "kdj_current.k", "kdj_current.d", "kdj_current.j",
    })
    if any(clause.field not in allowed for clause in clauses):
        _fail("sort_field_unsupported")
    stock_positions = [index for index, clause in enumerate(clauses) if clause.field == "stock_code"]
    if stock_positions and (stock_positions != [len(clauses) - 1] or clauses[-1].direction != "asc"):
        _fail("stock_code_tiebreak_invalid")


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionKDJQueryV1:
    """F17、MA、KDJ 查詢要求；頁碼獨立保存，這不是資格封套。"""

    ma_query_json: str
    ma_query_identity_sha256: str
    kdj_source_request_json: str
    kdj_source_request_identity_sha256: str
    kdj_read_session_identity_sha256: str
    kdj_index_identity_sha256: str
    kdj_source_clock_identity_sha256: str
    ma_states: tuple[str, ...] | None
    kdj_states: tuple[str, ...] | None
    condition_combine_mode: CombineMode
    unknown_policy: UnknownPolicy
    sort_clauses: tuple[DailyMarketTechnicalOfficialDispositionKDJSortClauseV1, ...]
    query_identity_sha256: str

    def __post_init__(self) -> None:
        _validate_query_object(self)

    @classmethod
    def create(
        cls,
        ma_query: DailyMarketTechnicalOfficialDispositionMaQueryV1,
        kdj_source_request: DailyMarketTechnicalUniverseKDJSourceRequestV1,
        *,
        kdj_read_session_identity_sha256: str,
        kdj_index_identity_sha256: str,
        kdj_source_clock_identity_sha256: str,
        ma_states: Sequence[str] | None = None,
        kdj_states: Sequence[str] | None = None,
        condition_combine_mode: CombineMode = "AND",
        unknown_policy: UnknownPolicy = "include",
        sort_clauses: Sequence[DailyMarketTechnicalOfficialDispositionKDJSortClauseV1] = (),
    ) -> DailyMarketTechnicalOfficialDispositionKDJQueryV1:
        if type(ma_query) is not DailyMarketTechnicalOfficialDispositionMaQueryV1:
            _fail("ma_query_invalid")
        if type(kdj_source_request) is not DailyMarketTechnicalUniverseKDJSourceRequestV1:
            _fail("source_request_invalid")
        ma_query_json = ma_query.to_json()
        # 建立外層查詢前，先核巢狀 MA 要求符合此複合查詢的中立來源契約。
        _parse_ma_query(ma_query_json)
        source_payload = kdj_source_request.to_dict()
        source_json = _canonical_json_bytes(source_payload).decode("utf-8")
        _validate_source_pair(ma_query, kdj_source_request)
        outer_ma_states = _normalize_ma_states(ma_states)
        states = _normalize_states(kdj_states)
        if (
            type(condition_combine_mode) is not str
            or condition_combine_mode not in _COMBINE_MODES
            or type(unknown_policy) is not str
            or unknown_policy not in _UNKNOWN_POLICIES
        ):
            _fail("condition_policy_invalid")
        if kdj_source_clock_identity_sha256 != kdj_source_request.ma_source_request.source_clock_identity_sha256:
            _fail("source_clock_mismatch")
        clauses = tuple(sort_clauses)
        if not clauses:
            clauses = (DailyMarketTechnicalOfficialDispositionKDJSortClauseV1("stock_code", "asc"),)
        if (
            len(clauses) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_SORT_CLAUSES
            or any(type(item) is not DailyMarketTechnicalOfficialDispositionKDJSortClauseV1 for item in clauses)
            or len({item.field for item in clauses}) != len(clauses)
        ):
            _fail("sort_clauses_invalid")
        _validate_sort_fields(ma_query, clauses)
        active_count = _active_group_count(ma_query, outer_ma_states, states)
        if unknown_policy == "only" and active_count == 0:
            _fail("unknown_only_without_condition")
        if active_count < 2:
            condition_combine_mode = "AND"
        if active_count == 0:
            unknown_policy = "include"
        if unknown_policy == "only" and active_count == 0:
            _fail("unknown_only_without_condition")
        body = {
            "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_KDJ_QUERY_V1_SCHEMA,
            "verification_status": "request_only",
            "ma_query_json": ma_query_json,
            "ma_query_identity_sha256": ma_query.query_identity_sha256,
            "kdj_source_request_json": source_json,
            "kdj_source_request_identity_sha256": kdj_source_request.request_identity_sha256,
            "kdj_read_session_identity_sha256": _require_sha(kdj_read_session_identity_sha256, "read_session_identity_invalid"),
            "kdj_index_identity_sha256": _require_sha(kdj_index_identity_sha256, "index_identity_invalid"),
            "kdj_source_clock_identity_sha256": _require_sha(kdj_source_clock_identity_sha256, "source_clock_identity_invalid"),
            "kdj_method_id": KDJ_METHOD_ID_V1,
            "kdj_method_version": KDJ_METHOD_VERSION_V1,
            "kdj_method_identity_sha256": KDJ_METHOD_IDENTITY_SHA256_V1,
            "ma_states": None if outer_ma_states is None else list(outer_ma_states),
            "kdj_states": None if states is None else list(states),
            "condition_combine_mode": condition_combine_mode,
            "unknown_policy": unknown_policy,
            "sort_clauses": [item.to_dict() for item in clauses],
            "source_available_at": None,
            "availability_status": "unknown",
            "historical_pit_eligible": False,
            "reader_qualified": False,
        }
        _enforce_query_budget(body)
        return cls.from_dict({**body, "query_identity_sha256": _sha256_json(body)})

    @classmethod
    def from_dict(cls, value: object) -> DailyMarketTechnicalOfficialDispositionKDJQueryV1:
        if not isinstance(value, Mapping) or set(value) != _KDJ_QUERY_FIELDS:
            _fail("query_fields_invalid")
        payload = dict(value)
        if payload.get("schema_version") != DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_KDJ_QUERY_V1_SCHEMA:
            _fail("query_schema_unsupported")
        if (
            payload.get("verification_status") != "request_only"
            or payload.get("kdj_method_id") != KDJ_METHOD_ID_V1
            or payload.get("kdj_method_version") != KDJ_METHOD_VERSION_V1
            or payload.get("kdj_method_identity_sha256") != KDJ_METHOD_IDENTITY_SHA256_V1
            or payload.get("source_available_at") is not None
            or payload.get("availability_status") != "unknown"
            or payload.get("historical_pit_eligible") is not False
            or payload.get("reader_qualified") is not False
        ):
            _fail("query_policy_invalid")
        ma_query = _parse_ma_query(payload.get("ma_query_json"))
        if payload.get("ma_query_identity_sha256") != ma_query.query_identity_sha256:
            _fail("ma_query_identity_mismatch")
        source_json = payload.get("kdj_source_request_json")
        if type(source_json) is not str:
            _fail("source_request_json_invalid")
        source_request = _source_request_from_json(source_json)
        if payload.get("kdj_source_request_identity_sha256") != source_request.request_identity_sha256:
            _fail("source_request_identity_mismatch")
        _validate_source_pair(ma_query, source_request)
        if payload.get("kdj_source_clock_identity_sha256") != source_request.ma_source_request.source_clock_identity_sha256:
            _fail("source_clock_mismatch")
        ma_states_raw = payload.get("ma_states")
        if ma_states_raw is None:
            ma_states = None
        elif isinstance(ma_states_raw, list):
            ma_states = _normalize_ma_states(cast(list[str], ma_states_raw))
            if list(ma_states or ()) != ma_states_raw:
                _fail("ma_states_noncanonical")
        else:
            _fail("ma_states_invalid")
        states_raw = payload.get("kdj_states")
        if states_raw is None:
            states = None
        elif isinstance(states_raw, list):
            states = _normalize_states(cast(list[str], states_raw))
            if list(states or ()) != states_raw:
                _fail("kdj_states_noncanonical")
        else:
            _fail("kdj_states_invalid")
        combine = payload.get("condition_combine_mode")
        unknown = payload.get("unknown_policy")
        if (
            type(combine) is not str
            or combine not in _COMBINE_MODES
            or type(unknown) is not str
            or unknown not in _UNKNOWN_POLICIES
        ):
            _fail("condition_policy_invalid")
        clauses_raw = payload.get("sort_clauses")
        if not isinstance(clauses_raw, list) or not 1 <= len(clauses_raw) <= DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_SORT_CLAUSES:
            _fail("sort_clauses_invalid")
        clauses = tuple(DailyMarketTechnicalOfficialDispositionKDJSortClauseV1.from_dict(item) for item in clauses_raw)
        if len({item.field for item in clauses}) != len(clauses):
            _fail("sort_clauses_invalid")
        _validate_sort_fields(ma_query, clauses)
        active_count = _active_group_count(ma_query, ma_states, states)
        if active_count < 2 and combine != "AND":
            _fail("condition_combine_mode_not_canonical")
        if active_count == 0 and unknown != "include":
            _fail("unknown_policy_not_canonical")
        if unknown == "only" and active_count == 0:
            _fail("unknown_only_without_condition")
        for key in (
            "kdj_read_session_identity_sha256", "kdj_index_identity_sha256",
            "kdj_source_clock_identity_sha256",
        ):
            _require_sha(payload.get(key), "query_source_identity_invalid")
        body = {key: item for key, item in payload.items() if key != "query_identity_sha256"}
        _enforce_query_budget(body)
        query = cls(
            ma_query_json=cast(str, payload.get("ma_query_json")),
            ma_query_identity_sha256=cast(str, payload.get("ma_query_identity_sha256")),
            kdj_source_request_json=cast(str, source_json),
            kdj_source_request_identity_sha256=cast(str, payload.get("kdj_source_request_identity_sha256")),
            kdj_read_session_identity_sha256=cast(str, payload.get("kdj_read_session_identity_sha256")),
            kdj_index_identity_sha256=cast(str, payload.get("kdj_index_identity_sha256")),
            kdj_source_clock_identity_sha256=cast(str, payload.get("kdj_source_clock_identity_sha256")),
            ma_states=ma_states,
            kdj_states=states,
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
    def from_json(cls, raw: bytes | str) -> DailyMarketTechnicalOfficialDispositionKDJQueryV1:
        return cls.from_dict(_parse_json(raw, maximum=DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_KDJ_QUERY_V1_MAX_BYTES))

    @property
    def ma_query(self) -> DailyMarketTechnicalOfficialDispositionMaQueryV1:
        return _parse_ma_query(self.ma_query_json)

    @property
    def active_group_count(self) -> int:
        return _active_group_count(self.ma_query, self.ma_states, self.kdj_states)

    @property
    def identity_sha256(self) -> str:
        return self.query_identity_sha256

    def to_dict(self) -> dict[str, object]:
        _validate_query_object(self)
        body = _query_body(self)
        return {**body, "query_identity_sha256": self.query_identity_sha256}

    def to_json(self) -> str:
        encoded = _canonical_json_bytes(self.to_dict())
        if len(encoded) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_KDJ_QUERY_V1_MAX_BYTES:
            _fail("query_byte_limit")
        return encoded.decode("utf-8")


def _validate_query_object(query: DailyMarketTechnicalOfficialDispositionKDJQueryV1) -> None:
    """在建構、序列化與 predicate 入口重驗 request 語意及完整自我摘要。"""
    if type(query) is not DailyMarketTechnicalOfficialDispositionKDJQueryV1:
        _fail("query_type_invalid")
    if type(query.ma_query_json) is not str:
        _fail("ma_query_invalid")
    try:
        ma_json_bytes = query.ma_query_json.encode("utf-8")
    except UnicodeError as exc:
        raise DailyMarketTechnicalOfficialDispositionKDJQueryV1Error("ma_query_invalid") from exc
    if len(ma_json_bytes) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_KDJ_QUERY_V1_MAX_BYTES:
        _fail("ma_query_invalid")
    ma_query = _parse_ma_query(query.ma_query_json)
    if query.ma_query_identity_sha256 != ma_query.query_identity_sha256:
        _fail("ma_query_identity_mismatch")

    if type(query.kdj_source_request_json) is not str:
        _fail("source_request_json_invalid")
    try:
        source_json_bytes = query.kdj_source_request_json.encode("utf-8")
    except UnicodeError as exc:
        raise DailyMarketTechnicalOfficialDispositionKDJQueryV1Error("source_request_json_invalid") from exc
    if len(source_json_bytes) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_KDJ_SOURCE_REQUEST_MAX_BYTES:
        _fail("source_request_json_invalid")
    try:
        source_request = _source_request_from_json(query.kdj_source_request_json)
    except DailyMarketTechnicalOfficialDispositionKDJQueryV1Error:
        raise
    except (TypeError, ValueError, UnicodeError, OverflowError) as exc:
        raise DailyMarketTechnicalOfficialDispositionKDJQueryV1Error("source_request_invalid") from exc
    if query.kdj_source_request_identity_sha256 != source_request.request_identity_sha256:
        _fail("source_request_identity_mismatch")
    _validate_source_pair(ma_query, source_request)

    for value, code in (
        (query.kdj_read_session_identity_sha256, "read_session_identity_invalid"),
        (query.kdj_index_identity_sha256, "index_identity_invalid"),
        (query.kdj_source_clock_identity_sha256, "source_clock_identity_invalid"),
        (query.query_identity_sha256, "query_identity_invalid"),
    ):
        _require_sha(value, code)
    if query.kdj_source_clock_identity_sha256 != source_request.ma_source_request.source_clock_identity_sha256:
        _fail("source_clock_mismatch")

    if query.ma_states is not None:
        if type(query.ma_states) is not tuple:
            _fail("ma_states_invalid")
        if _normalize_ma_states(query.ma_states) != query.ma_states:
            _fail("ma_states_noncanonical")
    if query.kdj_states is not None:
        if type(query.kdj_states) is not tuple:
            _fail("kdj_states_invalid")
        if _normalize_states(query.kdj_states) != query.kdj_states:
            _fail("kdj_states_noncanonical")
    if (
        type(query.condition_combine_mode) is not str
        or query.condition_combine_mode not in _COMBINE_MODES
        or type(query.unknown_policy) is not str
        or query.unknown_policy not in _UNKNOWN_POLICIES
    ):
        _fail("condition_policy_invalid")
    if (
        type(query.sort_clauses) is not tuple
        or not 1 <= len(query.sort_clauses) <= DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_SORT_CLAUSES
        or any(type(item) is not DailyMarketTechnicalOfficialDispositionKDJSortClauseV1 for item in query.sort_clauses)
        or len({item.field for item in query.sort_clauses}) != len(query.sort_clauses)
    ):
        _fail("sort_clauses_invalid")
    _validate_sort_fields(ma_query, query.sort_clauses)

    active_count = _active_group_count(ma_query, query.ma_states, query.kdj_states)
    if active_count < 2 and query.condition_combine_mode != "AND":
        _fail("condition_combine_mode_not_canonical")
    if active_count == 0 and query.unknown_policy != "include":
        _fail("unknown_policy_not_canonical")
    if query.unknown_policy == "only" and active_count == 0:
        _fail("unknown_only_without_condition")

    body = _query_body(query)
    _enforce_query_budget(body)
    if _sha256_json(body) != query.query_identity_sha256:
        _fail("query_identity_mismatch")


def _validate_page(page_index: object, page_size: object) -> None:
    if type(page_index) is not int or not 0 <= page_index <= DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_KDJ_MAX_PAGE_INDEX:
        _fail("page_bounds_invalid")
    if type(page_size) is not int or not 1 <= page_size <= DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_PAGE_SIZE:
        _fail("page_bounds_invalid")


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionKDJPageRequestV1:
    """獨立頁碼 request；頁碼不進 global query identity。"""

    query_json: str
    page_index: int
    page_size: int
    request_identity_sha256: str

    def __post_init__(self) -> None:
        self.to_dict()

    @classmethod
    def create(
        cls,
        query: DailyMarketTechnicalOfficialDispositionKDJQueryV1,
        *,
        page_index: int,
        page_size: int,
    ) -> DailyMarketTechnicalOfficialDispositionKDJPageRequestV1:
        if type(query) is not DailyMarketTechnicalOfficialDispositionKDJQueryV1:
            _fail("page_query_invalid")
        query_json = query.to_json()
        _validate_page(page_index, page_size)
        body = {
            "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_KDJ_PAGE_REQUEST_V1_SCHEMA,
            "query_identity_sha256": query.query_identity_sha256,
            "page_index": page_index,
            "page_size": page_size,
        }
        result = cls(query_json, page_index, page_size, _sha256_json(body))
        result.to_dict()
        return result

    @classmethod
    def from_json(cls, raw: bytes | str) -> DailyMarketTechnicalOfficialDispositionKDJPageRequestV1:
        payload = _parse_json(raw, maximum=DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_KDJ_QUERY_V1_MAX_BYTES)
        if not isinstance(payload, Mapping) or set(payload) != _PAGE_FIELDS:
            _fail("page_fields_invalid")
        if payload.get("schema_version") != DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_KDJ_PAGE_REQUEST_V1_SCHEMA:
            _fail("page_schema_unsupported")
        query_json = payload.get("query_json")
        if type(query_json) is not str:
            _fail("page_query_invalid")
        query = DailyMarketTechnicalOfficialDispositionKDJQueryV1.from_json(query_json)
        if payload.get("query_identity_sha256") != query.query_identity_sha256:
            _fail("page_query_identity_mismatch")
        result = cls.create(
            query,
            page_index=cast(int, payload.get("page_index")),
            page_size=cast(int, payload.get("page_size")),
        )
        if result.request_identity_sha256 != payload.get("request_identity_sha256"):
            _fail("page_identity_mismatch")
        if result.to_json() != (raw.decode("utf-8") if isinstance(raw, bytes) else raw):
            _fail("page_noncanonical")
        return result

    @property
    def query(self) -> DailyMarketTechnicalOfficialDispositionKDJQueryV1:
        return DailyMarketTechnicalOfficialDispositionKDJQueryV1.from_json(self.query_json)

    def to_dict(self) -> dict[str, object]:
        query = self.query
        _validate_page(self.page_index, self.page_size)
        if self.query_json != query.to_json():
            _fail("page_query_noncanonical")
        body = {
            "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_KDJ_PAGE_REQUEST_V1_SCHEMA,
            "query_identity_sha256": query.query_identity_sha256,
            "page_index": self.page_index,
            "page_size": self.page_size,
        }
        if _sha256_json(body) != self.request_identity_sha256:
            _fail("page_identity_mismatch")
        return {**body, "query_json": self.query_json, "request_identity_sha256": self.request_identity_sha256}

    def to_json(self) -> str:
        encoded = _canonical_json_bytes(self.to_dict())
        if len(encoded) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_KDJ_QUERY_V1_MAX_BYTES:
            _fail("page_byte_limit")
        return encoded.decode("utf-8")


def evaluate_kdj_group_v1(
    query: DailyMarketTechnicalOfficialDispositionKDJQueryV1,
    entry: DailyMarketTechnicalUniverseKDJCompactEntryV1 | None,
    *,
    stock_code: str,
    expected_snapshot_identity_sha256: str,
) -> KDJTruth:
    """以 typed KDJ compact evidence 評估群組；結果仍是未核資格 truth。"""
    if type(query) is not DailyMarketTechnicalOfficialDispositionKDJQueryV1:
        _fail("predicate_query_invalid")
    query.to_json()
    if query.kdj_states is None:
        if entry is not None:
            if type(entry) is not DailyMarketTechnicalUniverseKDJCompactEntryV1:
                _fail("predicate_entry_type_invalid")
            entry.to_dict()
        return "not_applicable"
    if type(entry) is not DailyMarketTechnicalUniverseKDJCompactEntryV1:
        _fail("predicate_entry_type_invalid")
    if type(stock_code) is not str or _STOCK_CODE_RE.fullmatch(stock_code) is None:
        _fail("predicate_stock_code_invalid")
    expected_snapshot = _require_sha(expected_snapshot_identity_sha256, "predicate_snapshot_identity_invalid")
    entry_payload = entry.to_dict()
    source_request = _source_request_from_json(query.kdj_source_request_json)
    request = source_request.ma_source_request
    cutoff = query.ma_query.f17_query.decision_cutoff
    if (
        entry.stock_code != stock_code
        or entry.snapshot_identity_sha256 != expected_snapshot
        or entry.source_clock_sha256 != query.kdj_source_clock_identity_sha256
        or entry.decision_date != request.decision_date
        or entry.decision_cutoff.astimezone(timezone.utc) != cutoff.astimezone(timezone.utc)
        or entry_payload.get("verification_status") != "projection_unqualified"
        or (entry.current is not None and entry.current.feature_date > cutoff.date())
        or (entry.previous is not None and entry.previous.feature_date > cutoff.date())
    ):
        _fail("predicate_source_or_cutoff_mismatch")
    if entry.state == "unknown":
        return "unknown"
    if entry.state in {"match", "no_match"}:
        return "match" if entry.state in query.kdj_states else "no_match"
    _fail("predicate_state_invalid")


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionKDJCompositeEvaluationV1:
    """純 predicate 結果；候選布林不等於 reader qualification。"""

    technical_truth: KDJTruth
    ma_truth: KDJTruth
    kdj_truth: KDJTruth
    composite_truth: KDJTruth
    hard_eligible: bool
    policy_included: bool
    predicate_candidate: bool
    audit_visible: bool
    visible: bool


def evaluate_composite_v1(
    query: DailyMarketTechnicalOfficialDispositionKDJQueryV1,
    *,
    technical_truth: KDJTruth,
    ma_truth: KDJTruth,
    kdj_truth: KDJTruth,
    hard_eligible: bool,
    audit_visible: bool,
) -> DailyMarketTechnicalOfficialDispositionKDJCompositeEvaluationV1:
    """合併啟用群組並先套 outer hard gate；audit visibility 分開保留。"""
    if type(query) is not DailyMarketTechnicalOfficialDispositionKDJQueryV1:
        _fail("composite_query_invalid")
    query.to_json()
    if type(hard_eligible) is not bool or type(audit_visible) is not bool:
        _fail("composite_gate_invalid")
    active = (
        bool(query.ma_query.f17_query.technical_query.rule_state_filters),
        query.ma_states is not None,
        query.kdj_states is not None,
    )
    truths = (technical_truth, ma_truth, kdj_truth)
    for is_active, truth in zip(active, truths, strict=True):
        if type(truth) is not str or truth not in _TRUTHS:
            _fail("composite_truth_invalid")
        if is_active and truth == "not_applicable":
            _fail("active_group_truth_invalid")
        if not is_active and truth != "not_applicable":
            _fail("inactive_group_truth_invalid")
    active_truths = [truth for is_active, truth in zip(active, truths, strict=True) if is_active]
    if not active_truths:
        combined: KDJTruth = "not_applicable"
        policy_included = False
        candidate = False
        visible = audit_visible
    elif not hard_eligible:
        combined = "not_evaluated"
        policy_included = False
        candidate = False
        visible = False
    else:
        combined = cast(KDJTruth, combine_truth_v1(active_truths, query.condition_combine_mode))
        policy_included = (
            combined in {"match", "unknown"}
            if query.unknown_policy == "include"
            else combined == "match"
            if query.unknown_policy == "exclude"
            else combined == "unknown"
        )
        candidate = policy_included
        visible = audit_visible and policy_included
    return DailyMarketTechnicalOfficialDispositionKDJCompositeEvaluationV1(
        technical_truth=technical_truth,
        ma_truth=ma_truth,
        kdj_truth=kdj_truth,
        composite_truth=combined,
        hard_eligible=hard_eligible,
        policy_included=policy_included,
        predicate_candidate=candidate,
        audit_visible=audit_visible,
        visible=visible,
    )


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionKDJSortValueV1:
    field: str
    direction: SortDirection
    value: SortScalar | None

    def __post_init__(self) -> None:
        if type(self.field) is not str or not self.field or len(self.field.encode("utf-8")) > 128:
            _fail("sort_value_field_invalid")
        if type(self.direction) is not str or self.direction not in _DIRECTIONS:
            _fail("sort_value_direction_invalid")
        _validate_scalar_bounds(self.value)

    def to_dict(self) -> dict[str, object]:
        value = self.value
        if type(value) is Decimal:
            encoded: object = _decimal_text(value)
        elif type(value) is date:
            encoded = value.isoformat()
        elif type(value) is datetime:
            if value.tzinfo is None or value.utcoffset() is None:
                _fail("sort_value_datetime_invalid")
            encoded = value.astimezone(timezone.utc).isoformat()
        else:
            encoded = value
        return {"field": self.field, "direction": self.direction, "value": encoded}


def _validate_scalar_bounds(value: object) -> None:
    if value is None:
        return
    if type(value) is str:
        if len(value.encode("utf-8")) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_KDJ_MAX_TEXT_TOKEN_BYTES:
            _fail("sort_value_text_limit")
        return
    if type(value) is int:
        _check_integer(value, "sort_value_integer_bounds_invalid")
        return
    if type(value) is Decimal:
        if not value.is_finite():
            _fail("sort_value_decimal_invalid")
        exponent = value.as_tuple().exponent
        if (
            type(exponent) is not int
            or len(value.as_tuple().digits) > 34
            or exponent < -6143
            or exponent > 6144
            or len(str(value).encode("utf-8")) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_KDJ_MAX_DECIMAL_TOKEN_BYTES
        ):
            _fail("sort_value_decimal_bounds_invalid")
        return
    if type(value) is date or type(value) is datetime:
        return
    _fail("sort_value_scalar_invalid")


def _decimal_text(value: Decimal) -> str:
    _validate_scalar_bounds(value)
    return str(value)


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionKDJSortKeyV1:
    query_identity_sha256: str
    stock_code: str
    sort_values: tuple[DailyMarketTechnicalOfficialDispositionKDJSortValueV1, ...]
    fact_row_sha256: str
    technical_snapshot_identity_sha256: str | None
    ma_evidence_identity_sha256: str | None
    kdj_compact_identity_sha256: str | None

    def __post_init__(self) -> None:
        _require_sha(self.query_identity_sha256, "sort_key_query_identity_invalid")
        if type(self.stock_code) is not str or _STOCK_CODE_RE.fullmatch(self.stock_code) is None:
            _fail("sort_key_stock_invalid")
        _require_sha(self.fact_row_sha256, "sort_key_fact_identity_invalid")
        if type(self.sort_values) is not tuple or not 1 <= len(self.sort_values) <= DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_SORT_CLAUSES:
            _fail("sort_key_values_invalid")
        if any(type(value) is not DailyMarketTechnicalOfficialDispositionKDJSortValueV1 for value in self.sort_values):
            _fail("sort_key_value_type_invalid")
        for name, value in (
            ("technical_snapshot", self.technical_snapshot_identity_sha256),
            ("ma_evidence", self.ma_evidence_identity_sha256),
            ("kdj_compact", self.kdj_compact_identity_sha256),
        ):
            if value is not None:
                _require_sha(value, f"sort_key_{name}_identity_invalid")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "daily-market-technical-official-disposition-kdj-sort-key.v1",
            "query_identity_sha256": self.query_identity_sha256,
            "stock_code": self.stock_code,
            "sort_values": [value.to_dict() for value in self.sort_values],
            "fact_row_sha256": self.fact_row_sha256,
            "technical_snapshot_identity_sha256": self.technical_snapshot_identity_sha256,
            "ma_evidence_identity_sha256": self.ma_evidence_identity_sha256,
            "kdj_compact_identity_sha256": self.kdj_compact_identity_sha256,
            "verification_status": "sort_projection_unqualified",
        }


def _validate_sort_value_for_field(
    query: DailyMarketTechnicalOfficialDispositionKDJQueryV1,
    field_name: str,
    value: SortScalar | None,
) -> None:
    if value is None:
        return
    f17 = query.ma_query.f17_query
    if field_name == "stock_code":
        if type(value) is not str or _STOCK_CODE_RE.fullmatch(value) is None:
            _fail("sort_value_field_type_invalid")
        return
    if field_name in {
        "decision_date", "latest_feature_date", "official_disposal.observed_date",
        "kdj_previous.feature_date", "kdj_current.feature_date",
    }:
        if type(value) is not date:
            _fail("sort_value_field_type_invalid")
        return
    if field_name in {"market_assignment.snapshot_observed_at", "official_disposal.observed_at"}:
        if type(value) is not datetime or value.utcoffset() is None:
            _fail("sort_value_field_type_invalid")
        return
    if field_name == "raw_row_count":
        if type(value) is not int or value < 0:
            _fail("sort_value_field_type_invalid")
        return
    if field_name == "market_assignment.state":
        if type(value) is not str or value not in {"assigned_twse", "assigned_tpex"}:
            _fail("sort_value_field_type_invalid")
        return
    if field_name == "official_disposal.state":
        if type(value) is not str or value not in {"reported_upcoming", "reported_active", "reported_elapsed_only"}:
            _fail("sort_value_field_type_invalid")
        return
    if field_name in {"ma_alignment_state", "kdj_state"}:
        if type(value) is not str or value not in {"match", "no_match"}:
            _fail("sort_value_field_type_invalid")
        return
    if field_name.startswith(("kdj_previous.", "kdj_current.")):
        if type(value) is not Decimal:
            _fail("sort_value_field_type_invalid")
        return
    rule_fields = {
        f"{key}.{suffix}"
        for key in f17.technical_query.method_rule_keys
        for suffix in ("ratio", "numerator", "denominator")
    }
    if field_name in rule_fields:
        if type(value) is not Decimal:
            _fail("sort_value_field_type_invalid")
        return
    _fail("sort_value_field_unsupported")


def sort_composite_keys_v1(
    query: DailyMarketTechnicalOfficialDispositionKDJQueryV1,
    keys: Sequence[DailyMarketTechnicalOfficialDispositionKDJSortKeyV1],
    *,
    cancel_callback: Callable[[], object] | None = None,
) -> tuple[DailyMarketTechnicalOfficialDispositionKDJSortKeyV1, ...]:
    """排序未核 keys；先量最終 payload bytes，再配置索引或排序分區。"""
    _strict_cancel(cancel_callback)
    if type(query) is not DailyMarketTechnicalOfficialDispositionKDJQueryV1:
        _fail("sort_query_invalid")
    query.to_json()
    if not isinstance(keys, (tuple, list)) or len(keys) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_ROWS:
        _fail("sort_row_limit")
    frozen_keys = tuple(keys)
    expected_fields = tuple((clause.field, clause.direction) for clause in query.sort_clauses)
    total_bytes = 0
    for index, item in enumerate(frozen_keys):
        if index % 256 == 0:
            _strict_cancel(cancel_callback)
        if type(item) is not DailyMarketTechnicalOfficialDispositionKDJSortKeyV1:
            _fail("sort_key_type_invalid")
        if (
            item.query_identity_sha256 != query.query_identity_sha256
            or tuple((value.field, value.direction) for value in item.sort_values) != expected_fields
        ):
            _fail("sort_key_query_or_fields_mismatch")
        for value in item.sort_values:
            _validate_sort_value_for_field(query, value.field, value.value)
        encoded_length = len(_canonical_json_bytes(item.to_dict()))
        if encoded_length > 16 * 1024:
            _fail("sort_key_entry_byte_limit")
        total_bytes += encoded_length + 1
        if total_bytes > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_KDJ_MAX_SORT_PROJECTION_BYTES:
            _fail("sort_projection_byte_limit")
    _strict_cancel(cancel_callback)
    seen: set[str] = set()
    for index, item in enumerate(frozen_keys):
        if index % 256 == 0:
            _strict_cancel(cancel_callback)
        if item.stock_code in seen:
            _fail("sort_duplicate_stock")
        seen.add(item.stock_code)
    ordered = sorted(frozen_keys, key=lambda item: item.stock_code)
    _strict_cancel(cancel_callback)
    for clause_index in range(len(query.sort_clauses) - 1, -1, -1):
        clause = query.sort_clauses[clause_index]
        known: list[DailyMarketTechnicalOfficialDispositionKDJSortKeyV1] = []
        nulls: list[DailyMarketTechnicalOfficialDispositionKDJSortKeyV1] = []
        for index, item in enumerate(ordered):
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
        ordered = known + nulls
    _strict_cancel(cancel_callback)
    return tuple(ordered)
