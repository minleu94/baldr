"""F17、MA 與波動原料的三群 canonical 查詢請求。

本模組只保存篩選請求、分頁請求與純函式契約，不開啟來源、不發行 reader
qualification，也不把 Bollinger/ATR 數值稱為收斂或突破。實際 reader 必須依
同一次 exact source operation 重新核對全部 source pins，並另外發行 sealed
result/page；本模組的 JSON identity 只保證請求內容自洽。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Literal, NoReturn, cast

from app_module.daily_market_technical_official_disposition_ma_query_v1 import (
    CombineMode,
    DailyMarketTechnicalOfficialDispositionMaQueryV1,
    MaState,
    UnknownPolicy,
    combine_truth_v1,
)
from app_module.daily_market_technical_volatility_evidence_v1 import (
    ATR14_SMA_METHOD_IDENTITY_SHA256_V1,
    ATR14_SMA_METHOD_ID_V1,
    ATR14_SMA_METHOD_VERSION_V1,
    BOLLINGER_BANDWIDTH_METHOD_IDENTITY_SHA256_V1,
    BOLLINGER_BANDWIDTH_METHOD_ID_V1,
    BOLLINGER_BANDWIDTH_METHOD_VERSION_V1,
    DailyMarketTechnicalVolatilityMeasureV1,
)


VOLATILITY_QUERY_SCHEMA_V1 = "daily-market-technical-official-disposition-volatility-query.v1"
VOLATILITY_PAGE_REQUEST_SCHEMA_V1 = "daily-market-technical-official-disposition-volatility-page-request.v1"
VOLATILITY_QUERY_MAX_BYTES_V1 = 32 * 1024 * 1024
VOLATILITY_QUERY_MAX_JSON_DEPTH_V1 = 32
VOLATILITY_QUERY_MAX_SORT_CLAUSES_V1 = 33
VOLATILITY_QUERY_MAX_ROWS_V1 = 100_000
VOLATILITY_QUERY_MAX_SORT_PROJECTION_BYTES_V1 = 64 * 1024 * 1024
VOLATILITY_QUERY_MAX_PAGE_SIZE_V1 = 256
VOLATILITY_QUERY_MAX_PAGE_INDEX_V1 = 1_000_000
VOLATILITY_QUERY_MAX_DECIMAL_TOKEN_BYTES_V1 = 256
VOLATILITY_QUERY_MAX_DECIMAL_DIGITS_V1 = 34
VOLATILITY_QUERY_MIN_DECIMAL_EXPONENT_V1 = -100
VOLATILITY_QUERY_MAX_DECIMAL_EXPONENT_V1 = 100
VOLATILITY_QUERY_MIN_DECIMAL_ADJUSTED_EXPONENT_V1 = -100
VOLATILITY_QUERY_MAX_DECIMAL_ADJUSTED_EXPONENT_V1 = 100
VOLATILITY_QUERY_MAX_SOURCE_QUERY_BYTES_V1 = 32 * 1024 * 1024

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STOCK_CODE_RE = re.compile(r"^[A-Z0-9]{1,16}$")
_MA_STATE_ORDER: tuple[MaState, ...] = ("match", "no_match", "unknown")
_TRUTH_VALUES = frozenset({"match", "no_match", "unknown", "not_evaluated", "not_applicable"})
_METHOD_FIELDS = (
    "bandwidth_method_id",
    "bandwidth_method_version",
    "bandwidth_method_identity_sha256",
    "atr14_method_id",
    "atr14_method_version",
    "atr14_method_identity_sha256",
)
_RANGE_FIELDS = (
    "bandwidth_min_pct",
    "bandwidth_max_pct",
    "atr14_min_pct",
    "atr14_max_pct",
)

Truth = Literal["match", "no_match", "unknown", "not_evaluated", "not_applicable"]
SortDirection = Literal["asc", "desc"]
SortScalar = str | int | Decimal | date | datetime
MeasureState = Literal["observed", "unknown"]


class DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error(ValueError):
    """波動複合查詢的穩定拒絕碼。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"technical_official_volatility_query_v1_{code}")


def _fail(code: str) -> NoReturn:
    raise DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error(code)


def _require_sha(value: object, code: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        _fail(code)
    return cast(str, value)


def _reject_float_tree(value: object, *, depth: int = 0) -> None:
    if depth > VOLATILITY_QUERY_MAX_JSON_DEPTH_V1:
        _fail("json_depth_limit")
    if isinstance(value, float):
        _fail("float_forbidden")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if type(key) is not str:
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
        raise DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error(
            "json_invalid"
        ) from exc


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail("json_duplicate_key")
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
            if depth > VOLATILITY_QUERY_MAX_JSON_DEPTH_V1:
                _fail("json_depth_limit")
        elif char in "]}":
            depth -= 1
            if depth < 0:
                _fail("json_invalid")
    if quoted or escaped or depth != 0:
        _fail("json_invalid")


def _parse_json(raw: bytes | str) -> object:
    if type(raw) not in {bytes, str}:
        _fail("json_invalid")
    try:
        encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
        if type(encoded) is not bytes or len(encoded) > VOLATILITY_QUERY_MAX_BYTES_V1:
            _fail("json_byte_limit")
        text = encoded.decode("utf-8")
        _preflight_depth(text)
        payload = json.loads(
            text,
            object_pairs_hook=_unique_pairs,
            parse_float=lambda _value: _fail("float_forbidden"),
            parse_constant=lambda _value: _fail("json_invalid"),
        )
        _reject_float_tree(payload)
        if _canonical_json_bytes(payload) != encoded:
            _fail("json_noncanonical")
        return payload
    except DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error(
            "json_invalid"
        ) from exc


def _canonical_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if type(value) is not Decimal or not value.is_finite():
        _fail("decimal_invalid")
    sign, digits_tuple, exponent = value.as_tuple()
    if (
        type(exponent) is not int
        or len(digits_tuple) > VOLATILITY_QUERY_MAX_DECIMAL_DIGITS_V1
        or exponent < VOLATILITY_QUERY_MIN_DECIMAL_EXPONENT_V1
        or exponent > VOLATILITY_QUERY_MAX_DECIMAL_EXPONENT_V1
        or value.adjusted() < VOLATILITY_QUERY_MIN_DECIMAL_ADJUSTED_EXPONENT_V1
        or value.adjusted() > VOLATILITY_QUERY_MAX_DECIMAL_ADJUSTED_EXPONENT_V1
    ):
        _fail("decimal_bounds_invalid")
    if value.is_zero():
        return Decimal(0)

    digits = list(digits_tuple)
    while len(digits) > 1 and digits[-1] == 0:
        digits.pop()
        exponent += 1
    digits_text = "".join(str(item) for item in digits)
    if exponent >= 0:
        text = digits_text + ("0" * exponent)
    else:
        split = len(digits_text) + exponent
        if split > 0:
            text = digits_text[:split] + "." + digits_text[split:]
        else:
            text = "0." + ("0" * (-split)) + digits_text
    if sign:
        text = "-" + text
    if len(text.encode("utf-8")) > VOLATILITY_QUERY_MAX_DECIMAL_TOKEN_BYTES_V1:
        _fail("decimal_token_limit")
    try:
        normalized = Decimal(text)
    except InvalidOperation as exc:
        raise DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error(
            "decimal_invalid"
        ) from exc
    if normalized.adjusted() < VOLATILITY_QUERY_MIN_DECIMAL_ADJUSTED_EXPONENT_V1 or normalized.adjusted() > VOLATILITY_QUERY_MAX_DECIMAL_ADJUSTED_EXPONENT_V1:
        _fail("decimal_bounds_invalid")
    return normalized


def _decimal_text(value: Decimal | None) -> str | None:
    normalized = _canonical_decimal(value)
    if normalized is None:
        return None
    return str(normalized)


def _parse_decimal_text(value: object, code: str) -> Decimal | None:
    if value is None:
        return None
    if type(value) is not str or len(value.encode("utf-8")) > VOLATILITY_QUERY_MAX_DECIMAL_TOKEN_BYTES_V1:
        _fail(code)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error(code) from exc
    normalized = _canonical_decimal(parsed)
    if normalized is None or str(normalized) != value:
        _fail("decimal_noncanonical")
    return normalized


def _normalize_ma_states(values: Sequence[MaState] | None) -> tuple[MaState, ...] | None:
    if values is None:
        return None
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        _fail("ma_states_invalid")
    items = tuple(values)
    if (
        not items
        or any(type(item) is not str or item not in _MA_STATE_ORDER for item in items)
        or len(set(items)) != len(items)
    ):
        _fail("ma_states_invalid")
    return tuple(item for item in _MA_STATE_ORDER if item in items)


def _parse_ma_source_query(raw: object) -> DailyMarketTechnicalOfficialDispositionMaQueryV1:
    if type(raw) is not str or len(raw.encode("utf-8")) > VOLATILITY_QUERY_MAX_SOURCE_QUERY_BYTES_V1:
        _fail("ma_source_query_invalid")
    try:
        query = DailyMarketTechnicalOfficialDispositionMaQueryV1.from_json(raw)
    except (ValueError, TypeError, UnicodeError) as exc:
        raise DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error(
            "ma_source_query_invalid"
        ) from exc
    if query.to_json() != raw:
        _fail("ma_source_query_noncanonical")
    if (
        query.ma_states is not None
        or query.condition_combine_mode != "AND"
        or query.unknown_policy != "include"
        or len(query.sort_clauses) != 1
        or query.sort_clauses[0].field != "stock_code"
        or query.sort_clauses[0].direction != "asc"
    ):
        _fail("nested_ma_source_query_not_neutral")
    return query


def _active_groups(
    source_query: DailyMarketTechnicalOfficialDispositionMaQueryV1,
    ma_states: tuple[MaState, ...] | None,
    bandwidth_min_pct: Decimal | None,
    bandwidth_max_pct: Decimal | None,
    atr14_min_pct: Decimal | None,
    atr14_max_pct: Decimal | None,
) -> tuple[bool, bool, bool]:
    return (
        bool(source_query.f17_query.technical_query.rule_state_filters),
        ma_states is not None,
        any(value is not None for value in (
            bandwidth_min_pct, bandwidth_max_pct, atr14_min_pct, atr14_max_pct,
        )),
    )


def _normalize_policy(
    active: tuple[bool, bool, bool],
    combine_mode: object,
    unknown_policy: object,
) -> tuple[CombineMode, UnknownPolicy]:
    if (
        type(combine_mode) is not str
        or combine_mode not in {"AND", "OR"}
        or type(unknown_policy) is not str
        or unknown_policy not in {"include", "exclude", "only"}
    ):
        _fail("condition_policy_invalid")
    count = sum(active)
    if count == 0 and unknown_policy == "only":
        _fail("unknown_only_without_condition")
    normalized_combine = cast(CombineMode, combine_mode if count >= 2 else "AND")
    normalized_unknown = cast(UnknownPolicy, unknown_policy if count else "include")
    return normalized_combine, normalized_unknown


def _sort_clause_payload(clauses: Sequence[DailyMarketTechnicalOfficialDispositionVolatilitySortClauseV1]) -> list[dict[str, str]]:
    return [item.to_dict() for item in clauses]


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionVolatilitySortClauseV1:
    """全母體 sort 欄與方向；讀取資格不由排序 DTO 發行。"""

    field: str
    direction: SortDirection

    def __post_init__(self) -> None:
        if (
            type(self.field) is not str
            or not self.field
            or len(self.field.encode("utf-8")) > 128
            or type(self.direction) is not str
            or self.direction not in {"asc", "desc"}
        ):
            _fail("sort_clause_invalid")

    def to_dict(self) -> dict[str, str]:
        return {"field": self.field, "direction": self.direction}

    @classmethod
    def from_dict(cls, value: object) -> DailyMarketTechnicalOfficialDispositionVolatilitySortClauseV1:
        if not isinstance(value, Mapping) or set(value) != {"field", "direction"}:
            _fail("sort_clause_invalid")
        field_name = value.get("field")
        direction = value.get("direction")
        if type(field_name) is not str or type(direction) is not str:
            _fail("sort_clause_invalid")
        return cls(field_name, cast(SortDirection, direction))


def _allowed_sort_fields(
    source_query: DailyMarketTechnicalOfficialDispositionMaQueryV1,
) -> set[str]:
    technical = source_query.f17_query.technical_query
    allowed = {
        "stock_code",
        "decision_date",
        "latest_feature_date",
        "raw_row_count",
        "market_assignment.state",
        "market_assignment.snapshot_observed_at",
        "official_disposal.state",
        "official_disposal.observed_at",
        "official_disposal.observed_date",
        "ma_alignment_state",
        "bollinger_bandwidth_pct",
        "atr14_pct",
    }
    for rule_key in technical.method_rule_keys:
        allowed.update({f"{rule_key}.{field}" for field in ("ratio", "numerator", "denominator")})
    return allowed


def _validate_sort_clauses(
    source_query: DailyMarketTechnicalOfficialDispositionMaQueryV1,
    clauses: tuple[DailyMarketTechnicalOfficialDispositionVolatilitySortClauseV1, ...],
) -> None:
    if (
        not clauses
        or len(clauses) > VOLATILITY_QUERY_MAX_SORT_CLAUSES_V1
        or any(type(item) is not DailyMarketTechnicalOfficialDispositionVolatilitySortClauseV1 for item in clauses)
        or len({item.field for item in clauses}) != len(clauses)
        or any(item.field not in _allowed_sort_fields(source_query) for item in clauses)
    ):
        _fail("sort_clauses_invalid")
    stock_positions = [index for index, item in enumerate(clauses) if item.field == "stock_code"]
    if stock_positions and (
        stock_positions != [len(clauses) - 1]
        or clauses[-1].direction != "asc"
    ):
        _fail("stock_code_tiebreak_invalid")


def _query_body(query: DailyMarketTechnicalOfficialDispositionVolatilityQueryV1) -> dict[str, object]:
    return {
        "schema_version": VOLATILITY_QUERY_SCHEMA_V1,
        "ma_source_query_json": query.ma_source_query_json,
        "ma_source_query_identity_sha256": query.ma_source_query_identity_sha256,
        "volatility_read_session_identity_sha256": query.volatility_read_session_identity_sha256,
        "volatility_index_identity_sha256": query.volatility_index_identity_sha256,
        "volatility_source_request_identity_sha256": query.volatility_source_request_identity_sha256,
        "volatility_source_clock_identity_sha256": query.volatility_source_clock_identity_sha256,
        "decision_date": query.decision_date.isoformat(),
        "decision_cutoff": query.decision_cutoff,
        "bandwidth_method_id": query.bandwidth_method_id,
        "bandwidth_method_version": query.bandwidth_method_version,
        "bandwidth_method_identity_sha256": query.bandwidth_method_identity_sha256,
        "atr14_method_id": query.atr14_method_id,
        "atr14_method_version": query.atr14_method_version,
        "atr14_method_identity_sha256": query.atr14_method_identity_sha256,
        "ma_states": None if query.ma_states is None else list(query.ma_states),
        "bandwidth_min_pct": _decimal_text(query.bandwidth_min_pct),
        "bandwidth_max_pct": _decimal_text(query.bandwidth_max_pct),
        "atr14_min_pct": _decimal_text(query.atr14_min_pct),
        "atr14_max_pct": _decimal_text(query.atr14_max_pct),
        "condition_combine_mode": query.condition_combine_mode,
        "unknown_policy": query.unknown_policy,
        "sort_clauses": _sort_clause_payload(query.sort_clauses),
        "scope": "current_only",
        "availability_status": "unknown",
        "source_available_at": None,
        "historical_pit_eligible": False,
        "qualification_status": "request_only",
    }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionVolatilityQueryV1:
    """全域條件與排序；F17/MA 僅作 neutral source recipe，頁碼獨立保存。"""

    ma_source_query_json: str
    ma_source_query_identity_sha256: str
    volatility_read_session_identity_sha256: str
    volatility_index_identity_sha256: str
    volatility_source_request_identity_sha256: str
    volatility_source_clock_identity_sha256: str
    decision_date: date
    decision_cutoff: str
    bandwidth_method_id: str
    bandwidth_method_version: str
    bandwidth_method_identity_sha256: str
    atr14_method_id: str
    atr14_method_version: str
    atr14_method_identity_sha256: str
    ma_states: tuple[MaState, ...] | None
    bandwidth_min_pct: Decimal | None
    bandwidth_max_pct: Decimal | None
    atr14_min_pct: Decimal | None
    atr14_max_pct: Decimal | None
    condition_combine_mode: CombineMode
    unknown_policy: UnknownPolicy
    sort_clauses: tuple[DailyMarketTechnicalOfficialDispositionVolatilitySortClauseV1, ...]
    query_identity_sha256: str

    def __post_init__(self) -> None:
        source_query = _parse_ma_source_query(self.ma_source_query_json)
        if self.ma_source_query_identity_sha256 != source_query.query_identity_sha256:
            _fail("ma_source_query_identity_mismatch")
        for name in (
            "volatility_read_session_identity_sha256",
            "volatility_index_identity_sha256",
            "volatility_source_request_identity_sha256",
            "volatility_source_clock_identity_sha256",
            "bandwidth_method_identity_sha256",
            "atr14_method_identity_sha256",
        ):
            _require_sha(getattr(self, name), f"{name}_invalid")
        f17_query = source_query.f17_query
        expected_cutoff = f17_query.decision_cutoff.astimezone(timezone.utc).isoformat()
        expected_date = f17_query.decision_date
        if (
            type(self.decision_date) is not date
            or self.decision_date != expected_date
            or type(self.decision_cutoff) is not str
            or self.decision_cutoff != expected_cutoff
            or self.volatility_source_clock_identity_sha256
            != f17_query.technical_query.source_clock_identity_sha256
        ):
            _fail("volatility_source_cutoff_or_clock_mismatch")
        expected_methods = (
            (self.bandwidth_method_id, BOLLINGER_BANDWIDTH_METHOD_ID_V1),
            (self.bandwidth_method_version, BOLLINGER_BANDWIDTH_METHOD_VERSION_V1),
            (self.bandwidth_method_identity_sha256, BOLLINGER_BANDWIDTH_METHOD_IDENTITY_SHA256_V1),
            (self.atr14_method_id, ATR14_SMA_METHOD_ID_V1),
            (self.atr14_method_version, ATR14_SMA_METHOD_VERSION_V1),
            (self.atr14_method_identity_sha256, ATR14_SMA_METHOD_IDENTITY_SHA256_V1),
        )
        if any(actual != expected for actual, expected in expected_methods):
            _fail("volatility_method_identity_mismatch")
        for name in _RANGE_FIELDS:
            value = _canonical_decimal(getattr(self, name))
            if value is not None and value < 0:
                _fail("volatility_range_negative")
            object.__setattr__(self, name, value)
        if (
            self.bandwidth_min_pct is not None
            and self.bandwidth_max_pct is not None
            and self.bandwidth_min_pct > self.bandwidth_max_pct
        ) or (
            self.atr14_min_pct is not None
            and self.atr14_max_pct is not None
            and self.atr14_min_pct > self.atr14_max_pct
        ):
            _fail("volatility_range_order_invalid")
        states = _normalize_ma_states(self.ma_states)
        if states != self.ma_states:
            _fail("ma_states_noncanonical")
        if type(self.sort_clauses) is not tuple:
            _fail("sort_clauses_invalid")
        _validate_sort_clauses(source_query, self.sort_clauses)
        active = _active_groups(
            source_query,
            states,
            self.bandwidth_min_pct,
            self.bandwidth_max_pct,
            self.atr14_min_pct,
            self.atr14_max_pct,
        )
        combine, policy = _normalize_policy(active, self.condition_combine_mode, self.unknown_policy)
        if combine != self.condition_combine_mode or policy != self.unknown_policy:
            _fail("condition_policy_noncanonical")
        _require_sha(self.query_identity_sha256, "query_identity_invalid")
        if _sha256_json(_query_body(self)) != self.query_identity_sha256:
            _fail("query_identity_mismatch")

    @classmethod
    def create(
        cls,
        ma_source_query: DailyMarketTechnicalOfficialDispositionMaQueryV1,
        *,
        volatility_read_session_identity_sha256: str,
        volatility_index_identity_sha256: str,
        volatility_source_request_identity_sha256: str,
        volatility_source_clock_identity_sha256: str,
        ma_states: Sequence[MaState] | None = None,
        bandwidth_min_pct: Decimal | None = None,
        bandwidth_max_pct: Decimal | None = None,
        atr14_min_pct: Decimal | None = None,
        atr14_max_pct: Decimal | None = None,
        condition_combine_mode: CombineMode = "AND",
        unknown_policy: UnknownPolicy = "include",
        sort_clauses: Sequence[DailyMarketTechnicalOfficialDispositionVolatilitySortClauseV1] = (),
    ) -> DailyMarketTechnicalOfficialDispositionVolatilityQueryV1:
        if type(ma_source_query) is not DailyMarketTechnicalOfficialDispositionMaQueryV1:
            _fail("ma_source_query_type_invalid")
        source_json = ma_source_query.to_json()
        source_query = _parse_ma_source_query(source_json)
        states = _normalize_ma_states(ma_states)
        ranges = tuple(_canonical_decimal(value) for value in (
            bandwidth_min_pct, bandwidth_max_pct, atr14_min_pct, atr14_max_pct,
        ))
        for value in ranges:
            if value is not None and value < 0:
                _fail("volatility_range_negative")
        bw_min, bw_max, atr_min, atr_max = cast(
            tuple[Decimal | None, Decimal | None, Decimal | None, Decimal | None],
            ranges,
        )
        if (bw_min is not None and bw_max is not None and bw_min > bw_max) or (
            atr_min is not None and atr_max is not None and atr_min > atr_max
        ):
            _fail("volatility_range_order_invalid")
        clauses = tuple(sort_clauses)
        if not clauses:
            clauses = (DailyMarketTechnicalOfficialDispositionVolatilitySortClauseV1("stock_code", "asc"),)
        _validate_sort_clauses(source_query, clauses)
        active = _active_groups(source_query, states, bw_min, bw_max, atr_min, atr_max)
        combine, policy = _normalize_policy(active, condition_combine_mode, unknown_policy)
        f17_query = source_query.f17_query
        source_clock = f17_query.technical_query.source_clock_identity_sha256
        if volatility_source_clock_identity_sha256 != source_clock:
            _fail("volatility_source_clock_mismatch")
        body: dict[str, object] = {
            "schema_version": VOLATILITY_QUERY_SCHEMA_V1,
            "ma_source_query_json": source_json,
            "ma_source_query_identity_sha256": ma_source_query.query_identity_sha256,
            "volatility_read_session_identity_sha256": _require_sha(volatility_read_session_identity_sha256, "volatility_read_session_identity_invalid"),
            "volatility_index_identity_sha256": _require_sha(volatility_index_identity_sha256, "volatility_index_identity_invalid"),
            "volatility_source_request_identity_sha256": _require_sha(volatility_source_request_identity_sha256, "volatility_source_request_identity_invalid"),
            "volatility_source_clock_identity_sha256": _require_sha(volatility_source_clock_identity_sha256, "volatility_source_clock_identity_invalid"),
            "decision_date": f17_query.decision_date.isoformat(),
            "decision_cutoff": f17_query.decision_cutoff.astimezone(timezone.utc).isoformat(),
            "bandwidth_method_id": BOLLINGER_BANDWIDTH_METHOD_ID_V1,
            "bandwidth_method_version": BOLLINGER_BANDWIDTH_METHOD_VERSION_V1,
            "bandwidth_method_identity_sha256": BOLLINGER_BANDWIDTH_METHOD_IDENTITY_SHA256_V1,
            "atr14_method_id": ATR14_SMA_METHOD_ID_V1,
            "atr14_method_version": ATR14_SMA_METHOD_VERSION_V1,
            "atr14_method_identity_sha256": ATR14_SMA_METHOD_IDENTITY_SHA256_V1,
            "ma_states": None if states is None else list(states),
            "bandwidth_min_pct": _decimal_text(bw_min),
            "bandwidth_max_pct": _decimal_text(bw_max),
            "atr14_min_pct": _decimal_text(atr_min),
            "atr14_max_pct": _decimal_text(atr_max),
            "condition_combine_mode": combine,
            "unknown_policy": policy,
            "sort_clauses": [item.to_dict() for item in clauses],
            "scope": "current_only",
            "availability_status": "unknown",
            "source_available_at": None,
            "historical_pit_eligible": False,
            "qualification_status": "request_only",
        }
        return cls.from_dict({**body, "query_identity_sha256": _sha256_json(body)})

    @classmethod
    def from_dict(cls, value: object) -> DailyMarketTechnicalOfficialDispositionVolatilityQueryV1:
        expected = {
            "schema_version", "ma_source_query_json", "ma_source_query_identity_sha256",
            "volatility_read_session_identity_sha256", "volatility_index_identity_sha256",
            "volatility_source_request_identity_sha256", "volatility_source_clock_identity_sha256",
            "decision_date", "decision_cutoff", *_METHOD_FIELDS, "ma_states", *_RANGE_FIELDS,
            "condition_combine_mode", "unknown_policy", "sort_clauses", "scope",
            "availability_status", "source_available_at", "historical_pit_eligible",
            "qualification_status", "query_identity_sha256",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            _fail("query_fields_invalid")
        payload = dict(value)
        if payload.get("schema_version") != VOLATILITY_QUERY_SCHEMA_V1:
            _fail("query_schema_unsupported")
        if (
            payload.get("scope") != "current_only"
            or payload.get("availability_status") != "unknown"
            or payload.get("source_available_at") is not None
            or payload.get("historical_pit_eligible") is not False
            or payload.get("qualification_status") != "request_only"
        ):
            _fail("query_availability_or_qualification_invalid")
        raw_source = payload.get("ma_source_query_json")
        source_query = _parse_ma_source_query(raw_source)
        if payload.get("ma_source_query_identity_sha256") != source_query.query_identity_sha256:
            _fail("ma_source_query_identity_mismatch")
        raw_date = payload.get("decision_date")
        raw_cutoff = payload.get("decision_cutoff")
        if type(raw_date) is not str or type(raw_cutoff) is not str:
            _fail("query_decision_date_or_cutoff_invalid")
        try:
            parsed_date = date.fromisoformat(raw_date)
            parsed_cutoff = datetime.fromisoformat(raw_cutoff)
        except ValueError as exc:
            raise DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error(
                "query_decision_date_or_cutoff_invalid"
            ) from exc
        if parsed_date.isoformat() != raw_date or parsed_cutoff.tzinfo is None or parsed_cutoff.utcoffset() is None or parsed_cutoff.astimezone(timezone.utc).isoformat() != raw_cutoff:
            _fail("query_decision_date_or_cutoff_noncanonical")
        states_raw = payload.get("ma_states")
        if states_raw is None:
            states = None
        elif isinstance(states_raw, list):
            states = _normalize_ma_states(cast(list[MaState], states_raw))
            if list(states or ()) != states_raw:
                _fail("ma_states_noncanonical")
        else:
            _fail("ma_states_invalid")
        decimal_values = tuple(_parse_decimal_text(payload.get(name), f"{name}_invalid") for name in _RANGE_FIELDS)
        combine_raw = payload.get("condition_combine_mode")
        unknown_raw = payload.get("unknown_policy")
        if (
            type(combine_raw) is not str
            or combine_raw not in {"AND", "OR"}
            or type(unknown_raw) is not str
            or unknown_raw not in {"include", "exclude", "only"}
        ):
            _fail("condition_policy_invalid")
        clauses_raw = payload.get("sort_clauses")
        if not isinstance(clauses_raw, list):
            _fail("sort_clauses_invalid")
        clauses = tuple(DailyMarketTechnicalOfficialDispositionVolatilitySortClauseV1.from_dict(item) for item in clauses_raw)
        query = cls(
            ma_source_query_json=cast(str, raw_source),
            ma_source_query_identity_sha256=cast(str, payload["ma_source_query_identity_sha256"]),
            volatility_read_session_identity_sha256=cast(str, payload["volatility_read_session_identity_sha256"]),
            volatility_index_identity_sha256=cast(str, payload["volatility_index_identity_sha256"]),
            volatility_source_request_identity_sha256=cast(str, payload["volatility_source_request_identity_sha256"]),
            volatility_source_clock_identity_sha256=cast(str, payload["volatility_source_clock_identity_sha256"]),
            decision_date=parsed_date,
            decision_cutoff=raw_cutoff,
            bandwidth_method_id=cast(str, payload["bandwidth_method_id"]),
            bandwidth_method_version=cast(str, payload["bandwidth_method_version"]),
            bandwidth_method_identity_sha256=cast(str, payload["bandwidth_method_identity_sha256"]),
            atr14_method_id=cast(str, payload["atr14_method_id"]),
            atr14_method_version=cast(str, payload["atr14_method_version"]),
            atr14_method_identity_sha256=cast(str, payload["atr14_method_identity_sha256"]),
            ma_states=states,
            bandwidth_min_pct=decimal_values[0],
            bandwidth_max_pct=decimal_values[1],
            atr14_min_pct=decimal_values[2],
            atr14_max_pct=decimal_values[3],
            condition_combine_mode=cast(CombineMode, combine_raw),
            unknown_policy=cast(UnknownPolicy, unknown_raw),
            sort_clauses=clauses,
            query_identity_sha256=_require_sha(payload.get("query_identity_sha256"), "query_identity_invalid"),
        )
        if query.to_json() != _canonical_json_bytes(payload).decode("utf-8"):
            _fail("query_noncanonical")
        return query

    @classmethod
    def from_json(cls, raw: bytes | str) -> DailyMarketTechnicalOfficialDispositionVolatilityQueryV1:
        return cls.from_dict(_parse_json(raw))

    @property
    def ma_source_query(self) -> DailyMarketTechnicalOfficialDispositionMaQueryV1:
        return _parse_ma_source_query(self.ma_source_query_json)

    @property
    def active_groups(self) -> tuple[bool, bool, bool]:
        return _active_groups(
            self.ma_source_query,
            self.ma_states,
            self.bandwidth_min_pct,
            self.bandwidth_max_pct,
            self.atr14_min_pct,
            self.atr14_max_pct,
        )

    @property
    def identity_sha256(self) -> str:
        return self.query_identity_sha256

    @property
    def reader_qualified(self) -> Literal[False]:
        return False

    def to_dict(self) -> dict[str, object]:
        body = _query_body(self)
        if _sha256_json(body) != self.query_identity_sha256:
            _fail("query_identity_mismatch")
        return {**body, "query_identity_sha256": self.query_identity_sha256}

    def to_json(self) -> str:
        raw = _canonical_json_bytes(self.to_dict())
        if len(raw) > VOLATILITY_QUERY_MAX_BYTES_V1:
            _fail("query_byte_limit")
        return raw.decode("utf-8")


def _validate_page(page_index: object, page_size: object) -> None:
    if type(page_index) is not int or not 0 <= page_index <= VOLATILITY_QUERY_MAX_PAGE_INDEX_V1:
        _fail("page_index_invalid")
    if type(page_size) is not int or not 1 <= page_size <= VOLATILITY_QUERY_MAX_PAGE_SIZE_V1:
        _fail("page_size_invalid")


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionVolatilityPageRequestV1:
    """頁碼獨立綁定 global query，不改動條件身份。"""

    query_json: str
    page_index: int
    page_size: int
    request_identity_sha256: str

    def __post_init__(self) -> None:
        query = DailyMarketTechnicalOfficialDispositionVolatilityQueryV1.from_json(self.query_json)
        _validate_page(self.page_index, self.page_size)
        body = {
            "schema_version": VOLATILITY_PAGE_REQUEST_SCHEMA_V1,
            "query_identity_sha256": query.query_identity_sha256,
            "page_index": self.page_index,
            "page_size": self.page_size,
        }
        if _sha256_json(body) != self.request_identity_sha256:
            _fail("page_request_identity_mismatch")

    @classmethod
    def create(
        cls,
        query: DailyMarketTechnicalOfficialDispositionVolatilityQueryV1,
        *,
        page_index: int,
        page_size: int,
    ) -> DailyMarketTechnicalOfficialDispositionVolatilityPageRequestV1:
        if type(query) is not DailyMarketTechnicalOfficialDispositionVolatilityQueryV1:
            _fail("page_request_query_invalid")
        query_json = query.to_json()
        _validate_page(page_index, page_size)
        body = {
            "schema_version": VOLATILITY_PAGE_REQUEST_SCHEMA_V1,
            "query_identity_sha256": query.query_identity_sha256,
            "page_index": page_index,
            "page_size": page_size,
        }
        return cls(query_json, page_index, page_size, _sha256_json(body))

    @classmethod
    def from_dict(cls, value: object) -> DailyMarketTechnicalOfficialDispositionVolatilityPageRequestV1:
        expected = {
            "schema_version", "query_json", "query_identity_sha256", "page_index",
            "page_size", "request_identity_sha256",
        }
        if not isinstance(value, Mapping) or set(value) != expected or value.get("schema_version") != VOLATILITY_PAGE_REQUEST_SCHEMA_V1:
            _fail("page_request_fields_invalid")
        query_json = value.get("query_json")
        if type(query_json) is not str:
            _fail("page_request_query_invalid")
        query = DailyMarketTechnicalOfficialDispositionVolatilityQueryV1.from_json(query_json)
        if value.get("query_identity_sha256") != query.query_identity_sha256:
            _fail("page_request_query_identity_mismatch")
        request = cls.create(
            query,
            page_index=cast(int, value.get("page_index")),
            page_size=cast(int, value.get("page_size")),
        )
        if request.request_identity_sha256 != value.get("request_identity_sha256"):
            _fail("page_request_identity_mismatch")
        if request.to_json() != _canonical_json_bytes(dict(value)).decode("utf-8"):
            _fail("page_request_noncanonical")
        return request

    @classmethod
    def from_json(cls, raw: bytes | str) -> DailyMarketTechnicalOfficialDispositionVolatilityPageRequestV1:
        return cls.from_dict(_parse_json(raw))

    @property
    def query(self) -> DailyMarketTechnicalOfficialDispositionVolatilityQueryV1:
        return DailyMarketTechnicalOfficialDispositionVolatilityQueryV1.from_json(self.query_json)

    def to_dict(self) -> dict[str, object]:
        query = self.query
        _validate_page(self.page_index, self.page_size)
        body = {
            "schema_version": VOLATILITY_PAGE_REQUEST_SCHEMA_V1,
            "query_identity_sha256": query.query_identity_sha256,
            "page_index": self.page_index,
            "page_size": self.page_size,
        }
        if _sha256_json(body) != self.request_identity_sha256:
            _fail("page_request_identity_mismatch")
        return {**body, "query_json": self.query_json, "request_identity_sha256": self.request_identity_sha256}

    def to_json(self) -> str:
        raw = _canonical_json_bytes(self.to_dict())
        if len(raw) > VOLATILITY_QUERY_MAX_BYTES_V1:
            _fail("page_request_byte_limit")
        return raw.decode("utf-8")


def _truth(value: object, code: str) -> Truth:
    if type(value) is not str or value not in _TRUTH_VALUES:
        _fail(code)
    return cast(Truth, value)


def _measure_range_truth(
    *,
    active: bool,
    measure: DailyMarketTechnicalVolatilityMeasureV1 | None,
    method_id: str,
    method_identity: str,
    lower: Decimal | None,
    upper: Decimal | None,
    use_normalized: bool,
) -> Truth:
    if not active:
        return "not_applicable"
    if measure is None:
        return "unknown"
    if type(measure) is not DailyMarketTechnicalVolatilityMeasureV1:
        _fail("volatility_measure_type_invalid")
    try:
        payload = measure.to_dict()
    except (ValueError, TypeError, ArithmeticError) as exc:
        raise DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error(
            "volatility_measure_invalid"
        ) from exc
    if payload.get("method_id") != method_id or payload.get("method_identity_sha256") != method_identity:
        _fail("volatility_measure_method_mismatch")
    if measure.state == "unknown":
        return "unknown"
    if measure.state != "observed":
        _fail("volatility_measure_state_invalid")
    value = measure.normalized_value if use_normalized else measure.value
    if type(value) is not Decimal:
        _fail("volatility_measure_value_missing")
    _canonical_decimal(value)
    if lower is not None and value < lower:
        return "no_match"
    if upper is not None and value > upper:
        return "no_match"
    return "match"


def evaluate_volatility_group_v1(
    query: DailyMarketTechnicalOfficialDispositionVolatilityQueryV1,
    *,
    bandwidth: DailyMarketTechnicalVolatilityMeasureV1 | None,
    atr14_sma: DailyMarketTechnicalVolatilityMeasureV1 | None,
) -> Truth:
    """以固定 AND 評估已啟用的 bandwidth／ATR 百分比範圍。"""

    if type(query) is not DailyMarketTechnicalOfficialDispositionVolatilityQueryV1:
        _fail("query_type_invalid")
    query.to_json()
    truths: list[Truth] = []
    if query.bandwidth_min_pct is not None or query.bandwidth_max_pct is not None:
        truths.append(_measure_range_truth(
            active=True,
            measure=bandwidth,
            method_id=BOLLINGER_BANDWIDTH_METHOD_ID_V1,
            method_identity=BOLLINGER_BANDWIDTH_METHOD_IDENTITY_SHA256_V1,
            lower=query.bandwidth_min_pct,
            upper=query.bandwidth_max_pct,
            use_normalized=False,
        ))
    if query.atr14_min_pct is not None or query.atr14_max_pct is not None:
        truths.append(_measure_range_truth(
            active=True,
            measure=atr14_sma,
            method_id=ATR14_SMA_METHOD_ID_V1,
            method_identity=ATR14_SMA_METHOD_IDENTITY_SHA256_V1,
            lower=query.atr14_min_pct,
            upper=query.atr14_max_pct,
            use_normalized=True,
        ))
    if not truths:
        return "not_applicable"
    return cast(Truth, combine_truth_v1(tuple(truths), "AND"))


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionVolatilityEvaluationV1:
    """不發行 qualification 的單列 predicate 結果；audit visibility 獨立保存。"""

    query_identity_sha256: str
    hard_eligible: bool
    audit_visible: bool
    technical_truth: Truth
    ma_truth: Truth
    volatility_truth: Truth
    composite_truth: Truth
    included_by_unknown_policy: bool
    predicate_match: bool


def evaluate_composite_predicate_v1(
    query: DailyMarketTechnicalOfficialDispositionVolatilityQueryV1,
    *,
    technical_truth: Truth,
    ma_truth: Truth,
    bandwidth: DailyMarketTechnicalVolatilityMeasureV1 | None,
    atr14_sma: DailyMarketTechnicalVolatilityMeasureV1 | None,
    hard_eligible: bool,
    audit_visible: bool,
) -> DailyMarketTechnicalOfficialDispositionVolatilityEvaluationV1:
    """合併三群 truth；硬資格與 audit 可見度不參與 AND/OR。"""

    if type(query) is not DailyMarketTechnicalOfficialDispositionVolatilityQueryV1:
        _fail("query_type_invalid")
    if type(hard_eligible) is not bool or type(audit_visible) is not bool:
        _fail("row_scope_or_hard_gate_invalid")
    query.to_json()
    technical = _truth(technical_truth, "technical_truth_invalid")
    ma = _truth(ma_truth, "ma_truth_invalid")
    technical_active, ma_active, volatility_active = query.active_groups
    if not hard_eligible:
        technical_out: Truth = "not_evaluated" if technical_active else "not_applicable"
        ma_out: Truth = "not_evaluated" if ma_active else "not_applicable"
        volatility_out: Truth = "not_evaluated" if volatility_active else "not_applicable"
        combined: Truth = "not_evaluated"
        included = False
        matched = False
    else:
        if technical_active and technical in {"not_evaluated", "not_applicable"}:
            _fail("technical_truth_incompatible_with_active_group")
        if ma_active and ma in {"not_evaluated", "not_applicable"}:
            _fail("ma_truth_incompatible_with_active_group")
        technical_out = technical if technical_active else "not_applicable"
        ma_out = ma if ma_active else "not_applicable"
        volatility_out = (
            evaluate_volatility_group_v1(query, bandwidth=bandwidth, atr14_sma=atr14_sma)
            if volatility_active
            else "not_applicable"
        )
        active_truths = tuple(
            value for active, value in (
                (technical_active, technical_out),
                (ma_active, ma_out),
                (volatility_active, volatility_out),
            ) if active
        )
        combined = cast(Truth, combine_truth_v1(active_truths, query.condition_combine_mode))
        matched = bool(active_truths) and combined == "match"
        if not active_truths:
            included = True
        elif combined == "match":
            included = query.unknown_policy != "only"
        elif combined == "unknown":
            included = query.unknown_policy in {"include", "only"}
        else:
            included = False
    return DailyMarketTechnicalOfficialDispositionVolatilityEvaluationV1(
        query_identity_sha256=query.query_identity_sha256,
        hard_eligible=hard_eligible,
        audit_visible=audit_visible,
        technical_truth=technical_out,
        ma_truth=ma_out,
        volatility_truth=volatility_out,
        composite_truth=combined,
        included_by_unknown_policy=included,
        predicate_match=matched,
    )


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionVolatilitySortValueV1:
    """未核來源的排序投影值；只能供排序 helper 使用。"""

    field: str
    value: SortScalar | None

    def __post_init__(self) -> None:
        if type(self.field) is not str or not self.field or len(self.field.encode("utf-8")) > 128:
            _fail("sort_value_field_invalid")
        value = self.value
        if value is None:
            return
        if type(value) is Decimal:
            _canonical_decimal(value)
        elif type(value) is str:
            if len(value.encode("utf-8")) > 256:
                _fail("sort_value_text_limit")
        elif type(value) is int:
            if value < 0 or value.bit_length() > 426:
                _fail("sort_value_integer_limit")
            try:
                if len(str(value)) > 128:
                    _fail("sort_value_integer_limit")
            except ValueError as exc:
                raise DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error(
                    "sort_value_integer_limit"
                ) from exc
        elif type(value) is date:
            return
        elif type(value) is datetime:
            if value.tzinfo is None or value.utcoffset() is None:
                _fail("sort_value_datetime_naive")
        else:
            _fail("sort_value_type_invalid")


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionVolatilityUnqualifiedSortKeyV1:
    """測試／純排序用的未核 row projection，不能當 reader-issued row。"""

    query_identity_sha256: str
    stock_code: str
    values: tuple[DailyMarketTechnicalOfficialDispositionVolatilitySortValueV1, ...]

    def __post_init__(self) -> None:
        _require_sha(self.query_identity_sha256, "sort_key_query_identity_invalid")
        if type(self.stock_code) is not str or _STOCK_CODE_RE.fullmatch(self.stock_code) is None:
            _fail("sort_key_stock_code_invalid")
        if type(self.values) is not tuple or any(
            type(item) is not DailyMarketTechnicalOfficialDispositionVolatilitySortValueV1
            for item in self.values
        ) or len(self.values) > VOLATILITY_QUERY_MAX_SORT_CLAUSES_V1 or len({item.field for item in self.values}) != len(self.values):
            _fail("sort_key_values_invalid")


def _strict_cancel(callback: Callable[[], object] | None) -> None:
    if callback is None:
        return
    if not callable(callback):
        _fail("cancel_callback_invalid")
    try:
        value = callback()
    except Exception as exc:
        raise DailyMarketTechnicalOfficialDispositionVolatilityQueryV1Error(
            "cancel_callback_failed"
        ) from exc
    if type(value) is not bool:
        _fail("cancel_callback_invalid")
    if value:
        _fail("cancelled")


def _sort_value_payload(value: SortScalar | None) -> str | int | None:
    if value is None:
        return None
    if type(value) is Decimal:
        return _decimal_text(value)
    if type(value) is datetime:
        if value.tzinfo is not timezone.utc:
            _fail("sort_value_datetime_utc_required")
        return value.isoformat()
    if type(value) is date:
        return value.isoformat()
    if type(value) is str or type(value) is int:
        return value
    _fail("sort_value_type_invalid")


def _sort_field_value_valid(
    source_query: DailyMarketTechnicalOfficialDispositionMaQueryV1,
    field_name: str,
    value: SortScalar | None,
) -> bool:
    if value is None:
        return True
    string_fields = {
        "stock_code", "market_assignment.state", "official_disposal.state",
        "ma_alignment_state",
    }
    date_fields = {"decision_date", "latest_feature_date", "official_disposal.observed_date"}
    datetime_fields = {"market_assignment.snapshot_observed_at", "official_disposal.observed_at"}
    decimal_fields = {"bollinger_bandwidth_pct", "atr14_pct"}
    if any(
        field_name == f"{rule_key}.{metric}"
        for rule_key in source_query.f17_query.technical_query.method_rule_keys
        for metric in ("ratio", "numerator", "denominator")
    ):
        decimal_fields.add(field_name)
    if field_name in string_fields:
        if type(value) is not str:
            return False
        if field_name == "market_assignment.state":
            return value in {"assigned_twse", "assigned_tpex"}
        if field_name == "official_disposal.state":
            return value in {"reported_upcoming", "reported_active", "reported_elapsed_only"}
        if field_name == "ma_alignment_state":
            return value in {"match", "no_match"}
        return True
    if field_name in date_fields:
        return type(value) is date
    if field_name in datetime_fields:
        return type(value) is datetime and value.tzinfo is timezone.utc
    if field_name == "raw_row_count":
        return type(value) is int and value >= 0
    if field_name in decimal_fields:
        return type(value) is Decimal and value.is_finite()
    return False


def sort_unqualified_volatility_keys_v1(
    query: DailyMarketTechnicalOfficialDispositionVolatilityQueryV1,
    keys: Sequence[DailyMarketTechnicalOfficialDispositionVolatilityUnqualifiedSortKeyV1],
    *,
    cancel_callback: Callable[[], object] | None = None,
) -> tuple[DailyMarketTechnicalOfficialDispositionVolatilityUnqualifiedSortKeyV1, ...]:
    """排序未核的最多 100,000 筆投影；此函式不發行 result/page。"""

    _strict_cancel(cancel_callback)
    if type(query) is not DailyMarketTechnicalOfficialDispositionVolatilityQueryV1:
        _fail("query_type_invalid")
    query.to_json()
    if isinstance(keys, (str, bytes)) or not isinstance(keys, Sequence) or len(keys) > VOLATILITY_QUERY_MAX_ROWS_V1:
        _fail("sort_key_rows_invalid")
    fields = tuple(item.field for item in query.sort_clauses)
    codes: set[str] = set()
    field_types: dict[str, type[object]] = {}
    by_code: list[DailyMarketTechnicalOfficialDispositionVolatilityUnqualifiedSortKeyV1] = []
    projection_bytes = 0
    for index, key in enumerate(keys):
        if index % 256 == 0:
            _strict_cancel(cancel_callback)
        if type(key) is not DailyMarketTechnicalOfficialDispositionVolatilityUnqualifiedSortKeyV1:
            _fail("sort_key_type_invalid")
        if key.query_identity_sha256 != query.query_identity_sha256 or key.stock_code in codes:
            _fail("sort_key_query_or_duplicate_code_invalid")
        codes.add(key.stock_code)
        if tuple(item.field for item in key.values) != fields:
            _fail("sort_key_fields_mismatch")
        key_payload = {
            "query_identity_sha256": key.query_identity_sha256,
            "stock_code": key.stock_code,
            "values": [
                {"field": item.field, "value": _sort_value_payload(item.value)}
                for item in key.values
            ],
        }
        projection_bytes += len(_canonical_json_bytes(key_payload)) + 1
        if projection_bytes > VOLATILITY_QUERY_MAX_SORT_PROJECTION_BYTES_V1:
            _fail("sort_projection_byte_limit")
        for value_item in key.values:
            if not _sort_field_value_valid(query.ma_source_query, value_item.field, value_item.value):
                _fail("sort_key_field_type_mismatch")
            if value_item.field == "stock_code" and value_item.value is not None and value_item.value != key.stock_code:
                _fail("sort_key_stock_code_value_mismatch")
            if value_item.value is not None:
                value_type = type(value_item.value)
                previous = field_types.setdefault(value_item.field, value_type)
                if previous is not value_type:
                    _fail("sort_key_field_type_mismatch")
        by_code.append(key)

    ordered = sorted(by_code, key=lambda item: item.stock_code)
    for clause_index in reversed(range(len(query.sort_clauses))):
        clause = query.sort_clauses[clause_index]
        _strict_cancel(cancel_callback)
        non_null: list[DailyMarketTechnicalOfficialDispositionVolatilityUnqualifiedSortKeyV1] = []
        nulls: list[DailyMarketTechnicalOfficialDispositionVolatilityUnqualifiedSortKeyV1] = []
        for index, sort_key in enumerate(ordered):
            if index % 256 == 0:
                _strict_cancel(cancel_callback)
            if sort_key.values[clause_index].value is None:
                nulls.append(sort_key)
            else:
                non_null.append(sort_key)
        reverse = clause.direction == "desc"
        non_null = sorted(
            non_null,
            key=lambda sort_key: cast(SortScalar, sort_key.values[clause_index].value),
            reverse=reverse,
        )
        ordered = non_null + nulls
        _strict_cancel(cancel_callback)
    return tuple(ordered)
