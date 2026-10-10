"""F17、P01、MA、KDJ、波動率同母體複合查詢契約。

此模組只提供 opt-in 的 canonical query/page、四群三值判斷、有界全域排序及
reader 內部發行器；不開啟來源，也不分開執行子查詢。每組證據都必須綁定
同一 F17 reader-issued projection group，KDJ/波動率 feature date 不得晚於
F17 decision cutoff。來源可取得時間仍為 unknown，歷史 PIT 資格仍為 false。
若需回滾，只移除此模組與專屬測試，不更動 reader、金融計算、UI、bookmark
或資料檔。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import TYPE_CHECKING, Literal, NoReturn, Protocol, cast

from app_module.daily_market_technical_official_disposition_ma_query_v1 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_PAGE_SIZE,
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_ROWS,
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_SORT_CLAUSES,
    CombineMode,
    DailyMarketTechnicalOfficialDispositionMaQueryV1,
    MaState,
    UnknownPolicy,
    combine_truth_v1,
)
from app_module.daily_market_technical_official_disposition_query_v1 import (
    DailyMarketTechnicalOfficialDispositionFactRowV1,
    DailyMarketTechnicalOfficialDispositionFilterEvaluationV1,
    DailyMarketTechnicalOfficialDispositionJoinedRowV1,
    DailyMarketTechnicalOfficialDispositionQueryV1,
    DailyMarketTechnicalOfficialDispositionSortClauseV1,
    DailyMarketTechnicalOfficialDispositionSortValueV1,
    SortValue,
    project_daily_market_technical_official_disposition_sort_key_v1,
)
from app_module.daily_market_technical_official_disposition_volatility_query_v1 import (
    ATR14_SMA_METHOD_IDENTITY_SHA256_V1,
    ATR14_SMA_METHOD_ID_V1,
    BOLLINGER_BANDWIDTH_METHOD_IDENTITY_SHA256_V1,
    BOLLINGER_BANDWIDTH_METHOD_ID_V1,
    VOLATILITY_QUERY_MAX_DECIMAL_ADJUSTED_EXPONENT_V1,
    VOLATILITY_QUERY_MAX_DECIMAL_DIGITS_V1,
    VOLATILITY_QUERY_MAX_DECIMAL_TOKEN_BYTES_V1,
    VOLATILITY_QUERY_MIN_DECIMAL_ADJUSTED_EXPONENT_V1,
    _measure_range_truth,
)
from app_module.daily_market_technical_universe_kdj_alignment_query_v1 import (
    KDJ_METHOD_IDENTITY_SHA256_V1,
    KDJ_METHOD_ID_V1,
    KDJ_METHOD_VERSION_V1,
    DailyMarketTechnicalUniverseKDJCompactEntryV1,
)
from app_module.daily_market_technical_universe_ma_alignment_query_v1 import (
    DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_ID_V1,
    DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_VERSION_V1,
    DailyMarketTechnicalMaAlignmentCompactEntryV1,
)
from app_module.daily_market_technical_universe_v4_query import (
    DailyMarketTechnicalUniverseV4Counts,
)
from app_module.daily_market_technical_parent_v4_query import (
    DailyMarketTechnicalParentV4Row,
)
from app_module.daily_market_technical_universe_volatility_alignment_query_v1 import (
    ATR14_SMA_METHOD_VERSION_V1,
    DailyMarketTechnicalUniverseVolatilityCompactEntryV1,
    BOLLINGER_BANDWIDTH_METHOD_VERSION_V1,
)

if TYPE_CHECKING:
    from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
        DailyMarketTechnicalOfficialDispositionQueryCountsV1,
        DailyMarketTechnicalOfficialDispositionReadSessionV1,
    )
    from app_module.daily_market_technical_universe_projection_group_session_v2 import (
        DailyMarketTechnicalUniverseProjectionGroupSessionV2,
    )


DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_QUERY_V1_SCHEMA = (
    "daily-market-technical-official-disposition-composite-query.v1"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_PAGE_REQUEST_V1_SCHEMA = (
    "daily-market-technical-official-disposition-composite-page-request.v1"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_QUERY_BYTES = 32 * 1024 * 1024
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_ROWS = (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_ROWS
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_PAGE_SIZE = (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_PAGE_SIZE
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_PAGE_INDEX = 1_000_000
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_SORT_CLAUSES = (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_SORT_CLAUSES
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_SORT_BYTES = 64 * 1024 * 1024
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_JSON_DEPTH = 32

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STOCK_CODE_RE = re.compile(r"^[A-Z0-9]{1,16}$")
_TRUTH_ORDER = ("match", "no_match", "unknown", "not_evaluated", "not_applicable")
_STATE_ORDER = ("match", "no_match", "unknown")
_COMBINE_MODES = {"AND", "OR"}
_UNKNOWN_POLICIES = {"include", "exclude", "only"}
_DIRECTIONS = {"asc", "desc"}
_GROUP_NAMES = ("technical", "ma", "kdj", "volatility")
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
    "ma_index_identity_sha256",
    "ma_source_request_identity_sha256",
    "ma_index_source_clock_identity_sha256",
    "market_assignment_pin_identity_sha256",
    "official_disposal_pin_identity_sha256",
    "decision_date",
    "decision_cutoff",
    "ma_method_id",
    "ma_method_version",
    "projection_group_session_identity_sha256",
    "kdj_body_identity_sha256",
    "kdj_source_request_identity_sha256",
    "kdj_method_id",
    "kdj_method_version",
    "kdj_method_identity_sha256",
    "volatility_body_identity_sha256",
    "volatility_source_request_identity_sha256",
    "bandwidth_method_id",
    "bandwidth_method_version",
    "bandwidth_method_identity_sha256",
    "atr14_method_id",
    "atr14_method_version",
    "atr14_method_identity_sha256",
)
_RESULT_SEAL_V1 = object()
_PAGE_SEAL_V1 = object()
_ISSUER_CAPABILITY_V1 = object()

CompositeTruth = Literal[
    "match", "no_match", "unknown", "not_evaluated", "not_applicable",
]
CompositeSortDirection = Literal["asc", "desc"]
CompositeSortScalar = str | int | Decimal | date | datetime
KDJState = Literal["match", "no_match", "unknown"]


class DailyMarketTechnicalOfficialDispositionCompositeQueryV1Error(ValueError):
    """Composite request/result 契約的穩定拒絕碼。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"technical_official_composite_query_v1_{code}")


def _fail(code: str) -> NoReturn:
    raise DailyMarketTechnicalOfficialDispositionCompositeQueryV1Error(code)


def _require_sha(value: object, code: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        _fail(code)
    return cast(str, value)


def _reject_float_tree(value: object, *, depth: int = 0) -> None:
    if depth > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_JSON_DEPTH:
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
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise DailyMarketTechnicalOfficialDispositionCompositeQueryV1Error(
            "json_encoding_invalid"
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


def _preflight_json_depth(text: str) -> None:
    depth = 0
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_JSON_DEPTH:
                _fail("json_depth_limit")
        elif char in "]}":
            depth -= 1


def _parse_json(raw: bytes | str) -> object:
    if isinstance(raw, bytes):
        if len(raw) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_QUERY_BYTES:
            _fail("json_byte_limit")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DailyMarketTechnicalOfficialDispositionCompositeQueryV1Error(
                "json_utf8_invalid"
            ) from exc
    elif type(raw) is str:
        text = raw
        if len(text.encode("utf-8")) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_QUERY_BYTES:
            _fail("json_byte_limit")
    else:
        _fail("json_input_invalid")
    _preflight_json_depth(text)
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_unique_pairs,
            parse_constant=lambda _value: _fail("json_nonfinite_invalid"),
        )
        _reject_float_tree(payload)
        return payload
    except DailyMarketTechnicalOfficialDispositionCompositeQueryV1Error:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalOfficialDispositionCompositeQueryV1Error(
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
        or exponent < -100
        or exponent > 100
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
        raise DailyMarketTechnicalOfficialDispositionCompositeQueryV1Error(
            "decimal_invalid"
        ) from exc
    if not normalized.is_finite() or not (
        VOLATILITY_QUERY_MIN_DECIMAL_ADJUSTED_EXPONENT_V1
        <= normalized.adjusted()
        <= VOLATILITY_QUERY_MAX_DECIMAL_ADJUSTED_EXPONENT_V1
    ):
        _fail("decimal_bounds_invalid")
    return normalized


def _decimal_text(value: Decimal | None) -> str | None:
    normalized = _canonical_decimal(value)
    return None if normalized is None else str(normalized)


def _parse_decimal_text(value: object) -> Decimal | None:
    if value is None:
        return None
    if type(value) is not str or len(value.encode("utf-8")) > VOLATILITY_QUERY_MAX_DECIMAL_TOKEN_BYTES_V1:
        _fail("decimal_text_invalid")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise DailyMarketTechnicalOfficialDispositionCompositeQueryV1Error(
            "decimal_text_invalid"
        ) from exc
    normalized = _canonical_decimal(parsed)
    if normalized is None or str(normalized) != value:
        _fail("decimal_noncanonical")
    return normalized


def _normalize_states(
    values: Sequence[str] | None,
    *,
    field_name: str,
) -> tuple[str, ...] | None:
    if values is None:
        return None
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        _fail(f"{field_name}_invalid")
    items = tuple(values)
    if (
        not items
        or any(type(item) is not str or item not in _STATE_ORDER for item in items)
        or len(set(items)) != len(items)
    ):
        _fail(f"{field_name}_invalid")
    return tuple(item for item in _STATE_ORDER if item in items)


def _sort_field_allowlist(
    f17_query: DailyMarketTechnicalOfficialDispositionQueryV1,
) -> set[str]:
    allowed = {
        "stock_code", "decision_date", "latest_feature_date", "raw_row_count",
        "market_assignment.state", "market_assignment.snapshot_observed_at",
        "official_disposal.state", "official_disposal.observed_at",
        "official_disposal.observed_date", "ma_alignment_state", "kdj_state",
        "kdj_previous.feature_date", "kdj_previous.rsv", "kdj_previous.k",
        "kdj_previous.d", "kdj_previous.j", "kdj_current.feature_date",
        "kdj_current.rsv", "kdj_current.k", "kdj_current.d", "kdj_current.j",
        "bollinger_bandwidth_pct", "atr14_pct",
    }
    for rule_key in f17_query.technical_query.method_rule_keys:
        allowed.update(
            f"{rule_key}.{field_name}"
            for field_name in ("ratio", "numerator", "denominator")
        )
    return allowed


def _validate_neutral_f17_query(
    f17_query: DailyMarketTechnicalOfficialDispositionQueryV1,
) -> None:
    """複合查詢只允許 F17/P01 內層維持 canonical neutral 順序。"""
    if (
        len(f17_query.sort_clauses) != 1
        or f17_query.sort_clauses[0].field != "stock_code"
        or f17_query.sort_clauses[0].direction != "asc"
        or f17_query.technical_query.sort_key != "stock_code"
        or f17_query.technical_query.descending is not False
        or f17_query.technical_query.page_index != 0
        or f17_query.technical_query.page_size != 1
    ):
        _fail("nested_f17_sort_or_page_not_neutral")


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionCompositeSortClauseV1:
    field: str
    direction: CompositeSortDirection

    def __post_init__(self) -> None:
        if (
            type(self.field) is not str
            or not self.field
            or len(self.field.encode("utf-8")) > 128
            or type(self.direction) is not str
            or self.direction not in _DIRECTIONS
        ):
            _fail("sort_clause_invalid")

    def to_dict(self) -> dict[str, str]:
        return {"field": self.field, "direction": self.direction}

    @classmethod
    def from_dict(
        cls,
        value: object,
    ) -> DailyMarketTechnicalOfficialDispositionCompositeSortClauseV1:
        if not isinstance(value, Mapping) or set(value) != {"field", "direction"}:
            _fail("sort_clause_invalid")
        field_name = value.get("field")
        direction = value.get("direction")
        if type(field_name) is not str or type(direction) is not str:
            _fail("sort_clause_invalid")
        return cls(field_name, cast(CompositeSortDirection, direction))


def _validate_sort_clauses(
    f17_query: DailyMarketTechnicalOfficialDispositionQueryV1,
    clauses: tuple[DailyMarketTechnicalOfficialDispositionCompositeSortClauseV1, ...],
) -> None:
    if (
        type(clauses) is not tuple
        or not clauses
        or len(clauses) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_SORT_CLAUSES
        or any(type(item) is not DailyMarketTechnicalOfficialDispositionCompositeSortClauseV1 for item in clauses)
        or len({item.field for item in clauses}) != len(clauses)
        or any(item.field not in _sort_field_allowlist(f17_query) for item in clauses)
    ):
        _fail("sort_clauses_invalid")
    stock_positions = [index for index, item in enumerate(clauses) if item.field == "stock_code"]
    if stock_positions and (
        stock_positions != [len(clauses) - 1]
        or clauses[-1].direction != "asc"
    ):
        _fail("stock_code_tiebreak_invalid")


def _query_body(
    query: DailyMarketTechnicalOfficialDispositionCompositeQueryV1,
) -> dict[str, object]:
    return {
        "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_QUERY_V1_SCHEMA,
        "verification_status": "request_only",
        "f17_query_json": query.f17_query_json,
        "f17_query_identity_sha256": query.f17_query_identity_sha256,
        "projection_group_session_identity_sha256": query.projection_group_session_identity_sha256,
        "ma_states": None if query.ma_states is None else list(query.ma_states),
        "kdj_states": None if query.kdj_states is None else list(query.kdj_states),
        "bandwidth_min_pct": _decimal_text(query.bandwidth_min_pct),
        "bandwidth_max_pct": _decimal_text(query.bandwidth_max_pct),
        "atr14_min_pct": _decimal_text(query.atr14_min_pct),
        "atr14_max_pct": _decimal_text(query.atr14_max_pct),
        "condition_combine_mode": query.condition_combine_mode,
        "unknown_policy": query.unknown_policy,
        "sort_clauses": [item.to_dict() for item in query.sort_clauses],
        "source_available_at": None,
        "availability_status": "unknown",
        "historical_pit_eligible": False,
        "reader_qualified": False,
    }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionCompositeQueryV1:
    """一份 canonical 全域 request；不含任何 child result/page資格。"""

    f17_query_json: str
    f17_query_identity_sha256: str
    projection_group_session_identity_sha256: str
    ma_states: tuple[MaState, ...] | None
    kdj_states: tuple[KDJState, ...] | None
    bandwidth_min_pct: Decimal | None
    bandwidth_max_pct: Decimal | None
    atr14_min_pct: Decimal | None
    atr14_max_pct: Decimal | None
    condition_combine_mode: CombineMode
    unknown_policy: UnknownPolicy
    sort_clauses: tuple[DailyMarketTechnicalOfficialDispositionCompositeSortClauseV1, ...]
    query_identity_sha256: str

    def __post_init__(self) -> None:
        _require_sha(self.f17_query_identity_sha256, "f17_query_identity_invalid")
        _require_sha(
            self.projection_group_session_identity_sha256,
            "projection_group_session_identity_invalid",
        )
        _require_sha(self.query_identity_sha256, "query_identity_invalid")
        if type(self.f17_query_json) is not str or not self.f17_query_json:
            _fail("f17_query_json_invalid")
        if len(self.f17_query_json.encode("utf-8")) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_QUERY_BYTES:
            _fail("f17_query_byte_limit")
        try:
            f17_query = DailyMarketTechnicalOfficialDispositionQueryV1.from_json(
                self.f17_query_json
            )
        except (TypeError, ValueError, UnicodeError) as exc:
            raise DailyMarketTechnicalOfficialDispositionCompositeQueryV1Error(
                "f17_query_invalid"
            ) from exc
        if (
            f17_query.to_json() != self.f17_query_json
            or f17_query.query_identity_sha256 != self.f17_query_identity_sha256
        ):
            _fail("f17_query_identity_mismatch")
        _validate_neutral_f17_query(f17_query)
        normalized_ma = _normalize_states(self.ma_states, field_name="ma_states")
        normalized_kdj = _normalize_states(self.kdj_states, field_name="kdj_states")
        if normalized_ma != self.ma_states or normalized_kdj != self.kdj_states:
            _fail("state_filter_noncanonical")
        for value in (
            self.bandwidth_min_pct,
            self.bandwidth_max_pct,
            self.atr14_min_pct,
            self.atr14_max_pct,
        ):
            if _canonical_decimal(value) != value:
                _fail("decimal_noncanonical")
        if (
            self.bandwidth_min_pct is not None
            and self.bandwidth_max_pct is not None
            and self.bandwidth_min_pct > self.bandwidth_max_pct
        ) or (
            self.atr14_min_pct is not None
            and self.atr14_max_pct is not None
            and self.atr14_min_pct > self.atr14_max_pct
        ):
            _fail("decimal_range_invalid")
        if (
            type(self.condition_combine_mode) is not str
            or self.condition_combine_mode not in _COMBINE_MODES
            or type(self.unknown_policy) is not str
            or self.unknown_policy not in _UNKNOWN_POLICIES
        ):
            _fail("condition_policy_invalid")
        _validate_sort_clauses(f17_query, self.sort_clauses)
        active_count = sum(self.active_groups)
        if active_count < 2 and self.condition_combine_mode != "AND":
            _fail("combine_mode_not_canonical")
        if active_count == 0 and self.unknown_policy != "include":
            _fail("unknown_policy_not_canonical")
        body = _query_body(self)
        if _sha256_json(body) != self.query_identity_sha256:
            _fail("query_identity_mismatch")

    @property
    def f17_query(self) -> DailyMarketTechnicalOfficialDispositionQueryV1:
        return DailyMarketTechnicalOfficialDispositionQueryV1.from_json(self.f17_query_json)

    @property
    def active_groups(self) -> tuple[bool, bool, bool, bool]:
        f17_query = self.f17_query
        return (
            bool(f17_query.technical_query.rule_state_filters),
            self.ma_states is not None,
            self.kdj_states is not None,
            any(value is not None for value in (
                self.bandwidth_min_pct,
                self.bandwidth_max_pct,
                self.atr14_min_pct,
                self.atr14_max_pct,
            )),
        )

    @property
    def active_group_count(self) -> int:
        return sum(self.active_groups)

    @classmethod
    def create(
        cls,
        f17_query: DailyMarketTechnicalOfficialDispositionQueryV1,
        *,
        projection_group_session_identity_sha256: str,
        ma_states: Sequence[MaState] | None = None,
        kdj_states: Sequence[KDJState] | None = None,
        bandwidth_min_pct: Decimal | None = None,
        bandwidth_max_pct: Decimal | None = None,
        atr14_min_pct: Decimal | None = None,
        atr14_max_pct: Decimal | None = None,
        condition_combine_mode: CombineMode = "AND",
        unknown_policy: UnknownPolicy = "include",
        sort_clauses: Sequence[DailyMarketTechnicalOfficialDispositionCompositeSortClauseV1] = (),
    ) -> DailyMarketTechnicalOfficialDispositionCompositeQueryV1:
        if type(f17_query) is not DailyMarketTechnicalOfficialDispositionQueryV1:
            _fail("f17_query_type_invalid")
        f17_query.to_json()
        _validate_neutral_f17_query(f17_query)
        group_identity = _require_sha(
            projection_group_session_identity_sha256,
            "projection_group_session_identity_invalid",
        )
        normalized_ma = cast(
            tuple[MaState, ...] | None,
            _normalize_states(ma_states, field_name="ma_states"),
        )
        normalized_kdj = cast(
            tuple[KDJState, ...] | None,
            _normalize_states(kdj_states, field_name="kdj_states"),
        )
        normalized_bandwidth_min = _canonical_decimal(bandwidth_min_pct)
        normalized_bandwidth_max = _canonical_decimal(bandwidth_max_pct)
        normalized_atr_min = _canonical_decimal(atr14_min_pct)
        normalized_atr_max = _canonical_decimal(atr14_max_pct)
        if (
            normalized_bandwidth_min is not None
            and normalized_bandwidth_max is not None
            and normalized_bandwidth_min > normalized_bandwidth_max
        ) or (
            normalized_atr_min is not None
            and normalized_atr_max is not None
            and normalized_atr_min > normalized_atr_max
        ):
            _fail("decimal_range_invalid")
        if (
            type(condition_combine_mode) is not str
            or condition_combine_mode not in _COMBINE_MODES
            or type(unknown_policy) is not str
            or unknown_policy not in _UNKNOWN_POLICIES
        ):
            _fail("condition_policy_invalid")
        if isinstance(sort_clauses, (str, bytes)) or not isinstance(sort_clauses, Sequence):
            _fail("sort_clauses_invalid")
        normalized_sorts = tuple(sort_clauses)
        if not normalized_sorts:
            normalized_sorts = (
                DailyMarketTechnicalOfficialDispositionCompositeSortClauseV1(
                    "stock_code", "asc",
                ),
            )
        active = (
            bool(f17_query.technical_query.rule_state_filters),
            normalized_ma is not None,
            normalized_kdj is not None,
            any(value is not None for value in (
                normalized_bandwidth_min,
                normalized_bandwidth_max,
                normalized_atr_min,
                normalized_atr_max,
            )),
        )
        normalized_combine = cast(CombineMode, condition_combine_mode if sum(active) >= 2 else "AND")
        normalized_unknown = cast(UnknownPolicy, unknown_policy if sum(active) else "include")
        _validate_sort_clauses(f17_query, normalized_sorts)
        body = {
            "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_QUERY_V1_SCHEMA,
            "verification_status": "request_only",
            "f17_query_json": f17_query.to_json(),
            "f17_query_identity_sha256": f17_query.query_identity_sha256,
            "projection_group_session_identity_sha256": group_identity,
            "ma_states": None if normalized_ma is None else list(normalized_ma),
            "kdj_states": None if normalized_kdj is None else list(normalized_kdj),
            "bandwidth_min_pct": _decimal_text(normalized_bandwidth_min),
            "bandwidth_max_pct": _decimal_text(normalized_bandwidth_max),
            "atr14_min_pct": _decimal_text(normalized_atr_min),
            "atr14_max_pct": _decimal_text(normalized_atr_max),
            "condition_combine_mode": normalized_combine,
            "unknown_policy": normalized_unknown,
            "sort_clauses": [item.to_dict() for item in normalized_sorts],
            "source_available_at": None,
            "availability_status": "unknown",
            "historical_pit_eligible": False,
            "reader_qualified": False,
        }
        return cls(
            f17_query_json=f17_query.to_json(),
            f17_query_identity_sha256=f17_query.query_identity_sha256,
            projection_group_session_identity_sha256=group_identity,
            ma_states=normalized_ma,
            kdj_states=normalized_kdj,
            bandwidth_min_pct=normalized_bandwidth_min,
            bandwidth_max_pct=normalized_bandwidth_max,
            atr14_min_pct=normalized_atr_min,
            atr14_max_pct=normalized_atr_max,
            condition_combine_mode=normalized_combine,
            unknown_policy=normalized_unknown,
            sort_clauses=normalized_sorts,
            query_identity_sha256=_sha256_json(body),
        )

    @classmethod
    def from_dict(
        cls,
        value: object,
    ) -> DailyMarketTechnicalOfficialDispositionCompositeQueryV1:
        expected_fields = {
            "schema_version", "verification_status", "f17_query_json",
            "f17_query_identity_sha256", "projection_group_session_identity_sha256",
            "ma_states", "kdj_states", "bandwidth_min_pct", "bandwidth_max_pct",
            "atr14_min_pct", "atr14_max_pct", "condition_combine_mode",
            "unknown_policy", "sort_clauses", "source_available_at",
            "availability_status", "historical_pit_eligible", "reader_qualified",
            "query_identity_sha256",
        }
        if not isinstance(value, Mapping) or set(value) != expected_fields:
            _fail("query_fields_invalid")
        if (
            value.get("schema_version") != DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_QUERY_V1_SCHEMA
            or value.get("verification_status") != "request_only"
            or value.get("source_available_at") is not None
            or value.get("availability_status") != "unknown"
            or value.get("historical_pit_eligible") is not False
            or value.get("reader_qualified") is not False
        ):
            _fail("query_status_invalid")
        raw_f17 = value.get("f17_query_json")
        if type(raw_f17) is not str:
            _fail("f17_query_json_invalid")
        try:
            f17_query = DailyMarketTechnicalOfficialDispositionQueryV1.from_json(raw_f17)
        except (TypeError, ValueError, UnicodeError) as exc:
            raise DailyMarketTechnicalOfficialDispositionCompositeQueryV1Error(
                "f17_query_invalid"
            ) from exc
        if f17_query.to_json() != raw_f17:
            _fail("f17_query_noncanonical")
        ma_raw = value.get("ma_states")
        kdj_raw = value.get("kdj_states")
        ma_states = None if ma_raw is None else _normalize_states(ma_raw, field_name="ma_states")
        kdj_states = None if kdj_raw is None else _normalize_states(kdj_raw, field_name="kdj_states")
        raw_sorts = value.get("sort_clauses")
        if not isinstance(raw_sorts, list):
            _fail("sort_clauses_invalid")
        sorts = tuple(
            DailyMarketTechnicalOfficialDispositionCompositeSortClauseV1.from_dict(item)
            for item in raw_sorts
        )
        combine = value.get("condition_combine_mode")
        unknown = value.get("unknown_policy")
        if type(combine) is not str or type(unknown) is not str:
            _fail("condition_policy_invalid")
        query = cls(
            f17_query_json=raw_f17,
            f17_query_identity_sha256=cast(str, value.get("f17_query_identity_sha256")),
            projection_group_session_identity_sha256=cast(
                str, value.get("projection_group_session_identity_sha256"),
            ),
            ma_states=cast(tuple[MaState, ...] | None, ma_states),
            kdj_states=cast(tuple[KDJState, ...] | None, kdj_states),
            bandwidth_min_pct=_parse_decimal_text(value.get("bandwidth_min_pct")),
            bandwidth_max_pct=_parse_decimal_text(value.get("bandwidth_max_pct")),
            atr14_min_pct=_parse_decimal_text(value.get("atr14_min_pct")),
            atr14_max_pct=_parse_decimal_text(value.get("atr14_max_pct")),
            condition_combine_mode=cast(CombineMode, combine),
            unknown_policy=cast(UnknownPolicy, unknown),
            sort_clauses=sorts,
            query_identity_sha256=cast(str, value.get("query_identity_sha256")),
        )
        if query.to_json() != _canonical_json_bytes(value).decode("utf-8"):
            _fail("query_noncanonical")
        return query

    @classmethod
    def from_json(cls, raw: bytes | str) -> DailyMarketTechnicalOfficialDispositionCompositeQueryV1:
        payload = _parse_json(raw)
        query = cls.from_dict(payload)
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        if query.to_json() != text:
            _fail("query_noncanonical")
        return query

    def to_dict(self) -> dict[str, object]:
        body = _query_body(self)
        if _sha256_json(body) != self.query_identity_sha256:
            _fail("query_identity_mismatch")
        return {**body, "query_identity_sha256": self.query_identity_sha256}

    def to_json(self) -> str:
        encoded = _canonical_json_bytes(self.to_dict())
        if len(encoded) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_QUERY_BYTES:
            _fail("query_byte_limit")
        return encoded.decode("utf-8")

    def validate_reader_binding(
        self,
        f17_query: DailyMarketTechnicalOfficialDispositionQueryV1,
        projection_group_session: DailyMarketTechnicalUniverseProjectionGroupSessionV2,
    ) -> None:
        from app_module.daily_market_technical_universe_projection_group_session_v2 import (
            DailyMarketTechnicalUniverseProjectionGroupSessionV2,
        )

        if (
            type(f17_query) is not DailyMarketTechnicalOfficialDispositionQueryV1
            or type(projection_group_session) is not DailyMarketTechnicalUniverseProjectionGroupSessionV2
        ):
            _fail("reader_binding_type_invalid")
        self.to_json()
        if (
            f17_query.query_identity_sha256 != self.f17_query_identity_sha256
            or f17_query.to_json() != self.f17_query_json
            or projection_group_session.identity_sha256
            != self.projection_group_session_identity_sha256
        ):
            _fail("reader_binding_mismatch")


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionCompositeEvaluationContextV1:
    """在完整母體迴圈外驗證一次，避免每列重解析 canonical F17 JSON。"""

    query: DailyMarketTechnicalOfficialDispositionCompositeQueryV1
    f17_query: DailyMarketTechnicalOfficialDispositionQueryV1
    f17_sort_query: DailyMarketTechnicalOfficialDispositionQueryV1
    active_groups: tuple[bool, bool, bool, bool]


class _CompositePageMaterializer(Protocol):
    def _materialize_composite_query_page_v1(
        self,
        result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
        request: DailyMarketTechnicalOfficialDispositionCompositePageRequestV1,
        cancel_callback: Callable[[], object] | None,
    ) -> DailyMarketTechnicalOfficialDispositionCompositeQueryPageV1: ...


def _validate_reader_issuer_binding(
    query: DailyMarketTechnicalOfficialDispositionCompositeQueryV1,
    read_session: DailyMarketTechnicalOfficialDispositionReadSessionV1,
    projection_group_session: DailyMarketTechnicalUniverseProjectionGroupSessionV2,
) -> None:
    from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
        DailyMarketTechnicalOfficialDispositionReadSessionV1 as ReadSessionType,
    )
    from app_module.daily_market_technical_universe_projection_group_session_v2 import (
        DailyMarketTechnicalUniverseProjectionGroupSessionV2 as GroupSessionType,
    )

    if (
        type(read_session) is not ReadSessionType
        or type(projection_group_session) is not GroupSessionType
    ):
        _fail("reader_issuer_type_invalid")
    try:
        read_session.__post_init__()
        projection_group_session.reader_issued
    except Exception as exc:
        raise DailyMarketTechnicalOfficialDispositionCompositeQueryV1Error(
            "reader_issuer_not_active"
        ) from exc
    if (
        read_session.projection_group_session is not projection_group_session
        or read_session.query.query_identity_sha256 != query.f17_query_identity_sha256
        or read_session.query.to_json() != query.f17_query_json
        or projection_group_session.identity_sha256
        != query.projection_group_session_identity_sha256
    ):
        _fail("reader_issuer_binding_mismatch")
    query.validate_reader_binding(read_session.query, projection_group_session)


def _member_request_identity(source_request_json: str, code: str) -> str:
    payload = _parse_json(source_request_json)
    if not isinstance(payload, Mapping):
        _fail(code)
    return _require_sha(payload.get("request_identity_sha256"), code)


def _validate_result_source_pins_with_issuer(
    query: DailyMarketTechnicalOfficialDispositionCompositeQueryV1,
    source_pins: tuple[tuple[str, str], ...],
    read_session: DailyMarketTechnicalOfficialDispositionReadSessionV1,
    projection_group_session: DailyMarketTechnicalUniverseProjectionGroupSessionV2,
) -> None:
    """將可見 source pins 綁回實際 F17 session 與 group anchor。"""
    _validate_result_source_pins(
        query,
        source_pins,
        f17_query=read_session.query,
    )
    expected_pins = _source_pins_for_reader_v1(
        query,
        read_session,
        projection_group_session,
    )
    if source_pins != expected_pins:
        _fail("result_source_pin_owner_mismatch")


def _source_pins_for_reader_v1(
    query: DailyMarketTechnicalOfficialDispositionCompositeQueryV1,
    read_session: DailyMarketTechnicalOfficialDispositionReadSessionV1,
    projection_group_session: DailyMarketTechnicalUniverseProjectionGroupSessionV2,
) -> tuple[tuple[str, str], ...]:
    """依實際 reader 發行者產生唯一排序的來源 pins，供 executor 共用。"""
    _validate_reader_issuer_binding(query, read_session, projection_group_session)
    anchor = projection_group_session._require_active()
    prepared = anchor.prepared
    f17_query = read_session.query
    base_query = read_session._base_query
    ma_request = prepared.ma.request
    ma_index = projection_group_session.ma_index
    kdj_request_identity = _member_request_identity(
        prepared.kdj.source_request_json,
        "result_kdj_source_request_invalid",
    )
    volatility_request_identity = _member_request_identity(
        prepared.volatility.source_request_json,
        "result_volatility_source_request_invalid",
    )
    expected = {
        "bundle_output_root": read_session.bundle_reference.output_root,
        "bundle_identity_sha256": read_session.bundle_reference.bundle_identity_sha256,
        "bundle_manifest_sha256": read_session.bundle_reference.manifest_sha256,
        "p01_read_session_identity_sha256": read_session.p01_read_session_identity_sha256,
        "p01_selection_identity_sha256": read_session.p01_selection_identity_sha256,
        "p01_query_spec_identity_sha256": read_session.p01_query_spec_identity_sha256,
        "p01_generation_identity_sha256": base_query.generation_identity_sha256,
        "p01_plan_identity_sha256": base_query.plan_identity_sha256,
        "p01_plan_sha256": base_query.plan_sha256,
        "p01_receipt_identity_sha256": base_query.receipt_identity_sha256,
        "p01_receipt_sha256": base_query.receipt_sha256,
        "p01_cohort_identity_sha256": base_query.cohort_identity_sha256,
        "p01_source_clock_identity_sha256": base_query.source_clock_identity_sha256,
        "p01_method_contracts_sha256": base_query.method_contracts_sha256,
        "ma_index_identity_sha256": ma_index.index_identity_sha256,
        "ma_source_request_identity_sha256": ma_request.request_identity_sha256,
        "ma_index_source_clock_identity_sha256": ma_index.source_clock_identity_sha256,
        "market_assignment_pin_identity_sha256": f17_query.market_assignment_pin_identity_sha256,
        "official_disposal_pin_identity_sha256": f17_query.official_disposal_pin_identity_sha256,
        "decision_date": f17_query.decision_date.isoformat(),
        "decision_cutoff": f17_query.decision_cutoff.isoformat(),
        "ma_method_id": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_ID_V1,
        "ma_method_version": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_VERSION_V1,
        "projection_group_session_identity_sha256": projection_group_session.identity_sha256,
        "kdj_body_identity_sha256": prepared.kdj.body_identity_sha256,
        "kdj_source_request_identity_sha256": kdj_request_identity,
        "kdj_method_id": KDJ_METHOD_ID_V1,
        "kdj_method_version": KDJ_METHOD_VERSION_V1,
        "kdj_method_identity_sha256": KDJ_METHOD_IDENTITY_SHA256_V1,
        "volatility_body_identity_sha256": prepared.volatility.body_identity_sha256,
        "volatility_source_request_identity_sha256": volatility_request_identity,
        "bandwidth_method_id": BOLLINGER_BANDWIDTH_METHOD_ID_V1,
        "bandwidth_method_version": BOLLINGER_BANDWIDTH_METHOD_VERSION_V1,
        "bandwidth_method_identity_sha256": BOLLINGER_BANDWIDTH_METHOD_IDENTITY_SHA256_V1,
        "atr14_method_id": ATR14_SMA_METHOD_ID_V1,
        "atr14_method_version": ATR14_SMA_METHOD_VERSION_V1,
        "atr14_method_identity_sha256": ATR14_SMA_METHOD_IDENTITY_SHA256_V1,
    }
    if tuple(expected) != _SOURCE_PIN_KEYS or any(
        type(value) is not str or not value for value in expected.values()
    ):
        _fail("result_source_pin_owner_invalid")
    return tuple((key, expected[key]) for key in _SOURCE_PIN_KEYS)


def prepare_composite_evaluation_context_v1(
    query: DailyMarketTechnicalOfficialDispositionCompositeQueryV1,
) -> DailyMarketTechnicalOfficialDispositionCompositeEvaluationContextV1:
    """reader 在單次母體掃描前呼叫；row helper 只使用這份 immutable context。"""
    if type(query) is not DailyMarketTechnicalOfficialDispositionCompositeQueryV1:
        _fail("composite_query_invalid")
    query.to_json()
    f17_query = query.f17_query
    active = (
        bool(f17_query.technical_query.rule_state_filters),
        query.ma_states is not None,
        query.kdj_states is not None,
        any(value is not None for value in (
            query.bandwidth_min_pct,
            query.bandwidth_max_pct,
            query.atr14_min_pct,
            query.atr14_max_pct,
        )),
    )
    composite_only_sort_fields = {
        "ma_alignment_state", "kdj_state",
        "kdj_previous.feature_date", "kdj_previous.rsv", "kdj_previous.k",
        "kdj_previous.d", "kdj_previous.j", "kdj_current.feature_date",
        "kdj_current.rsv", "kdj_current.k", "kdj_current.d", "kdj_current.j",
        "bollinger_bandwidth_pct", "atr14_pct",
    }
    f17_sort_clauses = tuple(
        DailyMarketTechnicalOfficialDispositionSortClauseV1(item.field, item.direction)
        for item in query.sort_clauses
        if item.field not in composite_only_sort_fields
    )
    if not f17_sort_clauses:
        f17_sort_clauses = (
            DailyMarketTechnicalOfficialDispositionSortClauseV1("stock_code", "asc"),
        )
    f17_sort_query = DailyMarketTechnicalOfficialDispositionQueryV1.create(
        technical_query=f17_query.technical_query,
        decision_cutoff=f17_query.decision_cutoff,
        bundle_output_root=f17_query.bundle_output_root,
        bundle_identity_sha256=f17_query.bundle_identity_sha256,
        expected_manifest_sha256=f17_query.expected_manifest_sha256,
        market_assignment_pin_identity_sha256=f17_query.market_assignment_pin_identity_sha256,
        official_disposal_pin_identity_sha256=f17_query.official_disposal_pin_identity_sha256,
        row_scope_filter=f17_query.row_scope_filter,
        market_assignment_states=f17_query.market_assignment_states,
        official_disposal_states=f17_query.official_disposal_states,
        outer_stock_filter_mode=f17_query.outer_stock_filter_mode,
        outer_stock_codes=f17_query.outer_stock_codes,
        sort_clauses=f17_sort_clauses,
    )
    return DailyMarketTechnicalOfficialDispositionCompositeEvaluationContextV1(
        query, f17_query, f17_sort_query, active,
    )


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionCompositePageRequestV1:
    """只攜帶同一 composite query 下的 page index/size。"""

    query_json: str
    page_index: int
    page_size: int
    request_identity_sha256: str

    @classmethod
    def create(
        cls,
        query: DailyMarketTechnicalOfficialDispositionCompositeQueryV1,
        *,
        page_index: int,
        page_size: int,
    ) -> DailyMarketTechnicalOfficialDispositionCompositePageRequestV1:
        if type(query) is not DailyMarketTechnicalOfficialDispositionCompositeQueryV1:
            _fail("page_query_invalid")
        query_json = query.to_json()
        _validate_page(page_index, page_size)
        body = {
            "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_PAGE_REQUEST_V1_SCHEMA,
            "query_identity_sha256": query.query_identity_sha256,
            "page_index": page_index,
            "page_size": page_size,
        }
        return cls(
            query_json=query_json,
            page_index=page_index,
            page_size=page_size,
            request_identity_sha256=_sha256_json(body),
        )

    @classmethod
    def from_dict(
        cls,
        value: object,
    ) -> DailyMarketTechnicalOfficialDispositionCompositePageRequestV1:
        fields = {
            "schema_version", "query_json", "query_identity_sha256", "page_index",
            "page_size", "request_identity_sha256",
        }
        if not isinstance(value, Mapping) or set(value) != fields:
            _fail("page_request_fields_invalid")
        if value.get("schema_version") != DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_PAGE_REQUEST_V1_SCHEMA:
            _fail("page_request_schema_invalid")
        query_json = value.get("query_json")
        if type(query_json) is not str:
            _fail("page_query_json_invalid")
        query = DailyMarketTechnicalOfficialDispositionCompositeQueryV1.from_json(query_json)
        result = cls.create(
            query,
            page_index=cast(int, value.get("page_index")),
            page_size=cast(int, value.get("page_size")),
        )
        if (
            value.get("query_identity_sha256") != query.query_identity_sha256
            or value.get("request_identity_sha256") != result.request_identity_sha256
            or result.to_json() != _canonical_json_bytes(value).decode("utf-8")
        ):
            _fail("page_request_identity_mismatch")
        return result

    @classmethod
    def from_json(cls, raw: bytes | str) -> DailyMarketTechnicalOfficialDispositionCompositePageRequestV1:
        result = cls.from_dict(_parse_json(raw))
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        if result.to_json() != text:
            _fail("page_request_noncanonical")
        return result

    @property
    def query(self) -> DailyMarketTechnicalOfficialDispositionCompositeQueryV1:
        return DailyMarketTechnicalOfficialDispositionCompositeQueryV1.from_json(self.query_json)

    def to_dict(self) -> dict[str, object]:
        query = self.query
        _validate_page(self.page_index, self.page_size)
        if self.query_json != query.to_json():
            _fail("page_query_noncanonical")
        body = {
            "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_PAGE_REQUEST_V1_SCHEMA,
            "query_identity_sha256": query.query_identity_sha256,
            "page_index": self.page_index,
            "page_size": self.page_size,
        }
        if _sha256_json(body) != self.request_identity_sha256:
            _fail("page_request_identity_mismatch")
        return {**body, "query_json": self.query_json, "request_identity_sha256": self.request_identity_sha256}

    def to_json(self) -> str:
        encoded = _canonical_json_bytes(self.to_dict())
        if len(encoded) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_QUERY_BYTES:
            _fail("page_request_byte_limit")
        return encoded.decode("utf-8")


def _validate_page(page_index: object, page_size: object) -> None:
    if (
        type(page_index) is not int
        or not 0 <= page_index <= DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_PAGE_INDEX
        or type(page_size) is not int
        or not 1 <= page_size <= DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_PAGE_SIZE
    ):
        _fail("page_bounds_invalid")


def _fact_technical_status(
    fact_row: DailyMarketTechnicalOfficialDispositionFactRowV1,
) -> str:
    if type(fact_row) is not DailyMarketTechnicalOfficialDispositionFactRowV1:
        _fail("fact_row_type_invalid")
    payload = fact_row.to_dict()
    status = payload.get("technical_status")
    if type(status) is not str or status not in {"processed", "pending", "excluded"}:
        _fail("fact_row_status_invalid")
    return status


def _validate_row_status(value: object) -> str:
    if type(value) is not str or value not in {"processed", "pending", "excluded"}:
        _fail("fact_row_status_invalid")
    return cast(str, value)


def _validate_parent_row(
    f17_query: DailyMarketTechnicalOfficialDispositionQueryV1,
    fact_row: DailyMarketTechnicalOfficialDispositionFactRowV1,
    technical_row: DailyMarketTechnicalParentV4Row | None,
) -> None:
    if (
        type(technical_row) is not DailyMarketTechnicalParentV4Row
        or technical_row.stock_code != fact_row.stock_code
        or technical_row.decision_date != f17_query.decision_date
        or technical_row.latest_feature_date is not None
        and technical_row.latest_feature_date > f17_query.decision_cutoff.date()
    ):
        _fail("parent_row_scope_or_lookahead_invalid")


def _validate_entry_clock(
    *,
    stock_code: str,
    decision_date: date,
    cutoff: datetime,
    source_clock_identity_sha256: str,
    entry_stock_code: str,
    entry_decision_date: date,
    entry_cutoff: datetime,
    entry_source_clock_sha256: str,
    snapshot_identity_sha256: str,
    entry_snapshot_identity_sha256: str,
) -> None:
    _require_sha(snapshot_identity_sha256, "parent_snapshot_identity_invalid")
    _require_sha(entry_snapshot_identity_sha256, "entry_snapshot_identity_invalid")
    _require_sha(source_clock_identity_sha256, "source_clock_identity_invalid")
    _require_sha(entry_source_clock_sha256, "entry_source_clock_invalid")
    if (
        entry_stock_code != stock_code
        or entry_decision_date != decision_date
        or entry_cutoff.astimezone(timezone.utc) != cutoff.astimezone(timezone.utc)
        or entry_source_clock_sha256 != source_clock_identity_sha256
        or entry_snapshot_identity_sha256 != snapshot_identity_sha256
    ):
        _fail("entry_source_or_cutoff_mismatch")


def _decimal_text_equal(value: str | None, expected: Decimal | None) -> bool:
    if value is None or expected is None:
        return value is None and expected is None
    try:
        parsed = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return False
    return parsed.is_finite() and parsed == expected


def evaluate_technical_group_v1(
    context: DailyMarketTechnicalOfficialDispositionCompositeEvaluationContextV1,
    fact_row: DailyMarketTechnicalOfficialDispositionFactRowV1,
    technical_row: DailyMarketTechnicalParentV4Row | None,
    *,
    technical_status: str,
    hard_eligible: bool,
) -> CompositeTruth:
    """套用 P01 rule-state 條件；outer membership 與 P01 stock filter 是 hard gate。"""
    if type(context) is not DailyMarketTechnicalOfficialDispositionCompositeEvaluationContextV1 or type(hard_eligible) is not bool:
        _fail("technical_context_invalid")
    query = context.query
    filters = context.f17_query.technical_query.rule_state_filters
    if not filters:
        return "not_applicable"
    if not hard_eligible:
        return "not_evaluated"
    status = _validate_row_status(technical_status)
    if status in {"pending", "excluded"}:
        return "not_evaluated"
    _validate_parent_row(context.f17_query, fact_row, technical_row)
    if technical_row is None:
        _fail("technical_group_row_missing")
    truths: list[CompositeTruth] = []
    for item in filters:
        evidence = technical_row.rule(item.rule_key)
        if evidence.state not in _STATE_ORDER:
            _fail("technical_group_state_invalid")
        if evidence.state == "unknown":
            truths.append("unknown")
        elif evidence.state in item.states:
            truths.append("match")
        else:
            truths.append("no_match")
    return cast(
        CompositeTruth,
        combine_truth_v1(truths, context.f17_query.technical_query.combine_mode),
    )


def evaluate_ma_group_v1(
    context: DailyMarketTechnicalOfficialDispositionCompositeEvaluationContextV1,
    fact_row: DailyMarketTechnicalOfficialDispositionFactRowV1,
    technical_row: DailyMarketTechnicalParentV4Row | None,
    entry: DailyMarketTechnicalMaAlignmentCompactEntryV1 | None,
    *,
    technical_status: str,
    hard_eligible: bool,
) -> CompositeTruth:
    if type(context) is not DailyMarketTechnicalOfficialDispositionCompositeEvaluationContextV1 or type(hard_eligible) is not bool:
        _fail("ma_context_invalid")
    query = context.query
    if query.ma_states is None:
        return "not_applicable"
    if not hard_eligible:
        return "not_evaluated"
    status = _validate_row_status(technical_status)
    if status in {"pending", "excluded"}:
        return "not_evaluated"
    _validate_parent_row(context.f17_query, fact_row, technical_row)
    if type(entry) is not DailyMarketTechnicalMaAlignmentCompactEntryV1 or technical_row is None:
        _fail("ma_group_entry_missing")
    entry.to_dict()
    if (
        entry.stock_code != fact_row.stock_code
        or entry.decision_date != context.f17_query.decision_date
        or entry.latest_feature_date != technical_row.latest_feature_date
        or entry.feature_date != technical_row.latest_feature_date
        or entry.snapshot_identity_sha256 != technical_row.snapshot_identity_sha256
        or entry.source_identity != technical_row.source_identity
        or entry.raw_row_count != technical_row.raw_row_count
        or entry.observed_prefix_contiguous is not technical_row.observed_prefix_contiguous
        or entry.source_clock_identity_sha256
        != context.f17_query.technical_query.source_clock_identity_sha256
        or entry.feature_date is not None
        and entry.feature_date > context.f17_query.decision_cutoff.date()
        or entry.latest_feature_date is not None
        and entry.latest_feature_date > context.f17_query.decision_cutoff.date()
    ):
        _fail("ma_group_source_or_lookahead_mismatch")
    if len(entry.base_rule_facts) != len(technical_row.rules):
        _fail("ma_group_parent_rule_mismatch")
    for saved, current in zip(entry.base_rule_facts, technical_row.rules, strict=True):
        if (
            saved.key != current.key
            or saved.state != current.state
            or not _decimal_text_equal(saved.numerator, current.numerator)
            or not _decimal_text_equal(saved.denominator, current.denominator)
            or not _decimal_text_equal(saved.ratio, current.ratio)
        ):
            _fail("ma_group_parent_rule_mismatch")
    if entry.ma_state == "unknown":
        return "unknown"
    if entry.ma_state not in _STATE_ORDER:
        _fail("ma_group_state_invalid")
    return "match" if entry.ma_state in query.ma_states else "no_match"


def evaluate_kdj_group_v1(
    context: DailyMarketTechnicalOfficialDispositionCompositeEvaluationContextV1,
    fact_row: DailyMarketTechnicalOfficialDispositionFactRowV1,
    technical_row: DailyMarketTechnicalParentV4Row | None,
    entry: DailyMarketTechnicalUniverseKDJCompactEntryV1 | None,
    *,
    technical_status: str,
    hard_eligible: bool,
) -> CompositeTruth:
    if type(context) is not DailyMarketTechnicalOfficialDispositionCompositeEvaluationContextV1 or type(hard_eligible) is not bool:
        _fail("kdj_context_invalid")
    query = context.query
    if query.kdj_states is None:
        return "not_applicable"
    if not hard_eligible:
        return "not_evaluated"
    status = _validate_row_status(technical_status)
    if status in {"pending", "excluded"}:
        return "not_evaluated"
    _validate_parent_row(context.f17_query, fact_row, technical_row)
    if type(entry) is not DailyMarketTechnicalUniverseKDJCompactEntryV1 or technical_row is None:
        _fail("kdj_group_entry_missing")
    entry.to_dict()
    _validate_entry_clock(
        stock_code=fact_row.stock_code,
        decision_date=context.f17_query.decision_date,
        cutoff=context.f17_query.decision_cutoff,
        source_clock_identity_sha256=context.f17_query.technical_query.source_clock_identity_sha256,
        entry_stock_code=entry.stock_code,
        entry_decision_date=entry.decision_date,
        entry_cutoff=entry.decision_cutoff,
        entry_source_clock_sha256=entry.source_clock_sha256,
        snapshot_identity_sha256=technical_row.snapshot_identity_sha256,
        entry_snapshot_identity_sha256=entry.snapshot_identity_sha256,
    )
    if entry.source_identity != technical_row.source_identity:
        _fail("kdj_parent_source_identity_mismatch")
    cutoff_date = context.f17_query.decision_cutoff.date()
    if any(
        item is not None and item.feature_date > cutoff_date
        for item in (entry.previous, entry.current)
    ):
        _fail("kdj_feature_after_cutoff")
    if entry.state == "unknown":
        return "unknown"
    if entry.state not in _STATE_ORDER:
        _fail("kdj_group_state_invalid")
    return "match" if entry.state in query.kdj_states else "no_match"


def evaluate_volatility_group_v1(
    context: DailyMarketTechnicalOfficialDispositionCompositeEvaluationContextV1,
    fact_row: DailyMarketTechnicalOfficialDispositionFactRowV1,
    technical_row: DailyMarketTechnicalParentV4Row | None,
    entry: DailyMarketTechnicalUniverseVolatilityCompactEntryV1 | None,
    *,
    technical_status: str,
    hard_eligible: bool,
) -> CompositeTruth:
    if type(context) is not DailyMarketTechnicalOfficialDispositionCompositeEvaluationContextV1 or type(hard_eligible) is not bool:
        _fail("volatility_context_invalid")
    query = context.query
    active = context.active_groups[3]
    if not active:
        return "not_applicable"
    if not hard_eligible:
        return "not_evaluated"
    status = _validate_row_status(technical_status)
    if status in {"pending", "excluded"}:
        return "not_evaluated"
    _validate_parent_row(context.f17_query, fact_row, technical_row)
    if type(entry) is not DailyMarketTechnicalUniverseVolatilityCompactEntryV1 or technical_row is None:
        _fail("volatility_group_entry_missing")
    entry_payload = entry.to_dict()
    evidence = entry.evidence
    evidence_payload = evidence.to_dict()
    source_clock = context.f17_query.technical_query.source_clock_identity_sha256
    cutoff = context.f17_query.decision_cutoff
    if (
        entry_payload.get("verification_status") != "projection_unqualified"
        or entry.stock_code != fact_row.stock_code
        or entry.source_identity != technical_row.source_identity
        or entry.snapshot_identity_sha256 != technical_row.snapshot_identity_sha256
        or entry.source_clock_sha256 != source_clock
        or entry.decision_date != context.f17_query.decision_date
        or entry.decision_cutoff.astimezone(timezone.utc) != cutoff.astimezone(timezone.utc)
        or evidence.stock_code != fact_row.stock_code
        or evidence.snapshot_identity_sha256 != technical_row.snapshot_identity_sha256
        or evidence.source_clock_sha256 != source_clock
        or evidence.decision_date != context.f17_query.decision_date
        or evidence.decision_cutoff.astimezone(timezone.utc) != cutoff.astimezone(timezone.utc)
        or entry.parent_row_identity_sha256 != _sha256_json(technical_row.to_dict())
    ):
        _fail("volatility_group_source_mismatch")
    cutoff_date = cutoff.date()
    input_dates = (
        evidence.current_feature_date,
        *evidence.bandwidth.input_feature_dates,
        *evidence.atr14_sma.input_feature_dates,
    )
    if any(item is not None and item > cutoff_date for item in input_dates):
        _fail("volatility_feature_after_cutoff")
    if evidence_payload.get("availability") != {
        "source_available_at": None,
        "availability_status": "unknown",
        "historical_pit_eligible": False,
    }:
        _fail("volatility_availability_contract_invalid")
    truths: list[CompositeTruth] = []
    if query.bandwidth_min_pct is not None or query.bandwidth_max_pct is not None:
        truths.append(cast(
            CompositeTruth,
            _measure_range_truth(
                active=True,
                measure=evidence.bandwidth,
                method_id=BOLLINGER_BANDWIDTH_METHOD_ID_V1,
                method_identity=BOLLINGER_BANDWIDTH_METHOD_IDENTITY_SHA256_V1,
                lower=query.bandwidth_min_pct,
                upper=query.bandwidth_max_pct,
                use_normalized=False,
            ),
        ))
    if query.atr14_min_pct is not None or query.atr14_max_pct is not None:
        truths.append(cast(
            CompositeTruth,
            _measure_range_truth(
                active=True,
                measure=evidence.atr14_sma,
                method_id=ATR14_SMA_METHOD_ID_V1,
                method_identity=ATR14_SMA_METHOD_IDENTITY_SHA256_V1,
                lower=query.atr14_min_pct,
                upper=query.atr14_max_pct,
                use_normalized=True,
            ),
        ))
    if not truths:
        _fail("volatility_active_without_range")
    return cast(CompositeTruth, combine_truth_v1(truths, "AND"))


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionCompositeEvaluationV1:
    technical_truth: CompositeTruth
    ma_truth: CompositeTruth
    kdj_truth: CompositeTruth
    volatility_truth: CompositeTruth
    composite_truth: CompositeTruth
    active_groups: tuple[bool, bool, bool, bool]
    hard_eligible: bool
    audit_visible: bool
    included_by_unknown_policy: bool
    predicate_match: bool
    visible: bool

    def __post_init__(self) -> None:
        if (
            any(type(item) is not bool for item in self.active_groups)
            or type(self.active_groups) is not tuple
            or any(item not in _TRUTH_ORDER for item in (
                self.technical_truth, self.ma_truth, self.kdj_truth,
                self.volatility_truth, self.composite_truth,
            ))
            or any(type(item) is not bool for item in (
                self.hard_eligible, self.audit_visible, self.included_by_unknown_policy,
                self.predicate_match, self.visible,
            ))
        ):
            _fail("evaluation_invalid")

    def to_dict(self) -> dict[str, object]:
        return {
            "technical_truth": self.technical_truth,
            "ma_truth": self.ma_truth,
            "kdj_truth": self.kdj_truth,
            "volatility_truth": self.volatility_truth,
            "composite_truth": self.composite_truth,
            "active_groups": list(self.active_groups),
            "hard_eligible": self.hard_eligible,
            "audit_visible": self.audit_visible,
            "included_by_unknown_policy": self.included_by_unknown_policy,
            "predicate_match": self.predicate_match,
            "visible": self.visible,
        }


def evaluate_composite_predicate_v1(
    context: DailyMarketTechnicalOfficialDispositionCompositeEvaluationContextV1,
    *,
    technical_truth: CompositeTruth | None,
    ma_truth: CompositeTruth | None,
    kdj_truth: CompositeTruth | None,
    volatility_truth: CompositeTruth | None,
    technical_status: str,
    hard_eligible: bool,
) -> DailyMarketTechnicalOfficialDispositionCompositeEvaluationV1:
    """在 hard gates 通過後，一次套用全域四群三值政策。"""
    if type(context) is not DailyMarketTechnicalOfficialDispositionCompositeEvaluationContextV1:
        _fail("composite_context_invalid")
    query = context.query
    status = _validate_row_status(technical_status)
    if type(hard_eligible) is not bool:
        _fail("composite_gate_invalid")
    active = context.active_groups
    provided = (technical_truth, ma_truth, kdj_truth, volatility_truth)
    normalized: list[CompositeTruth] = []
    for is_active, value in zip(active, provided, strict=True):
        if value is not None and value not in _TRUTH_ORDER:
            _fail("composite_truth_invalid")
        if not is_active:
            if value not in {None, "not_applicable"}:
                _fail("inactive_group_truth_invalid")
            normalized.append("not_applicable")
        elif not hard_eligible:
            if value not in {None, "not_evaluated"}:
                _fail("hard_failed_group_was_evaluated")
            normalized.append("not_evaluated")
        elif status in {"pending", "excluded"}:
            if value not in {None, "not_evaluated"}:
                _fail("unprocessed_group_was_evaluated")
            normalized.append("not_evaluated")
        else:
            if value not in {"match", "no_match", "unknown"}:
                _fail("active_group_truth_invalid")
            normalized.append(cast(CompositeTruth, value))
    active_truths = [value for is_active, value in zip(active, normalized, strict=True) if is_active]
    if not hard_eligible:
        combined: CompositeTruth = "not_evaluated"
        included = False
        matched = False
    elif status in {"pending", "excluded"}:
        combined = "not_evaluated"
        included = not active_truths
        matched = False
    elif not active_truths:
        combined = "not_applicable"
        included = True
        matched = False
    else:
        combined = cast(
            CompositeTruth,
            combine_truth_v1(active_truths, query.condition_combine_mode),
        )
        matched = combined == "match"
        if query.unknown_policy == "include":
            included = combined in {"match", "unknown"}
        elif query.unknown_policy == "exclude":
            included = combined == "match"
        else:
            included = combined == "unknown"
    audit_visible = hard_eligible and not active_truths
    visible = hard_eligible and (included or audit_visible)
    return DailyMarketTechnicalOfficialDispositionCompositeEvaluationV1(
        technical_truth=normalized[0],
        ma_truth=normalized[1],
        kdj_truth=normalized[2],
        volatility_truth=normalized[3],
        composite_truth=combined,
        active_groups=active,
        hard_eligible=hard_eligible,
        audit_visible=audit_visible,
        included_by_unknown_policy=included,
        predicate_match=matched,
        visible=visible,
        )


def _strict_cancel(callback: Callable[[], object] | None) -> None:
    if callback is None:
        return
    if not callable(callback):
        _fail("cancel_callback_invalid")
    try:
        value = callback()
    except Exception as exc:
        raise DailyMarketTechnicalOfficialDispositionCompositeQueryV1Error(
            "cancel_check_failed"
        ) from exc
    if type(value) is not bool:
        _fail("cancel_callback_invalid")
    if value:
        _fail("cancelled")


def _valid_count_pairs(
    values: object,
    expected_keys: tuple[str, ...],
    total: int,
) -> bool:
    if type(values) is not tuple or len(values) != len(expected_keys):
        return False
    pairs: list[tuple[str, int]] = []
    for value in values:
        if (
            type(value) is not tuple
            or len(value) != 2
            or type(value[0]) is not str
            or type(value[1]) is not int
            or value[1] < 0
        ):
            return False
        pairs.append(cast(tuple[str, int], value))
    return (
        tuple(key for key, _count in pairs) == expected_keys
        and sum(count for _key, count in pairs) == total
    )


def _truth_count_dict(values: tuple[tuple[str, int], ...]) -> dict[str, int]:
    return {key: count for key, count in values}


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionCompositeCountsV1:
    """保持 F17 全母體分母，分列 hard gate、active evaluation 與 audit visible。"""

    base_f17_counts: DailyMarketTechnicalOfficialDispositionQueryCountsV1
    ma_state_counts: tuple[tuple[str, int], ...]
    kdj_state_counts: tuple[tuple[str, int], ...]
    bandwidth_state_counts: tuple[tuple[str, int], ...]
    atr14_state_counts: tuple[tuple[str, int], ...]
    technical_truth_counts: tuple[tuple[str, int], ...]
    ma_truth_counts: tuple[tuple[str, int], ...]
    kdj_truth_counts: tuple[tuple[str, int], ...]
    volatility_truth_counts: tuple[tuple[str, int], ...]
    composite_truth_counts: tuple[tuple[str, int], ...]
    hard_eligible_truth_counts: tuple[tuple[str, int], ...]
    active_evaluable_truth_counts: tuple[tuple[str, int], ...]
    hard_eligible_count: int
    active_evaluable_count: int
    audit_visible_count: int
    visible_count: int
    unknown_policy_included_count: int
    unknown_policy_excluded_count: int

    def __post_init__(self) -> None:
        from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
            DailyMarketTechnicalOfficialDispositionQueryCountsV1,
        )

        if type(self.base_f17_counts) is not DailyMarketTechnicalOfficialDispositionQueryCountsV1:
            _fail("counts_base_invalid")
        population = self.base_f17_counts.population
        declared = population.declared_count
        processed = population.processed_count
        if (
            not _valid_count_pairs(self.ma_state_counts, _STATE_ORDER, processed)
            or not _valid_count_pairs(self.kdj_state_counts, _STATE_ORDER, processed)
            or not _valid_count_pairs(self.bandwidth_state_counts, ("observed", "unknown"), processed)
            or not _valid_count_pairs(self.atr14_state_counts, ("observed", "unknown"), processed)
        ):
            _fail("counts_projection_states_invalid")
        for name, values in (
            ("technical", self.technical_truth_counts),
            ("ma", self.ma_truth_counts),
            ("kdj", self.kdj_truth_counts),
            ("volatility", self.volatility_truth_counts),
            ("composite", self.composite_truth_counts),
        ):
            if not _valid_count_pairs(values, _TRUTH_ORDER, declared):
                _fail(f"counts_{name}_truth_invalid")
        if not _valid_count_pairs(
            self.hard_eligible_truth_counts, _TRUTH_ORDER, self.hard_eligible_count,
        ) or not _valid_count_pairs(
            self.active_evaluable_truth_counts, _TRUTH_ORDER, self.active_evaluable_count,
        ):
            _fail("counts_eligible_truth_invalid")
        for value in (
            self.hard_eligible_count,
            self.active_evaluable_count,
            self.audit_visible_count,
            self.visible_count,
            self.unknown_policy_included_count,
            self.unknown_policy_excluded_count,
        ):
            if type(value) is not int or not 0 <= value <= declared:
                _fail("counts_invalid")
        if (
            self.active_evaluable_count > min(self.hard_eligible_count, processed)
            or self.audit_visible_count > self.hard_eligible_count
            or self.visible_count > self.hard_eligible_count
            or self.unknown_policy_included_count > self.visible_count
            or self.unknown_policy_excluded_count > self.hard_eligible_count
        ):
            _fail("counts_gate_relationship_invalid")

    @property
    def declared_count(self) -> int:
        return self.base_f17_counts.population.declared_count

    @property
    def pending_count(self) -> int:
        return self.base_f17_counts.population.pending_count

    @property
    def excluded_count(self) -> int:
        return self.base_f17_counts.population.excluded_count

    @property
    def not_evaluated_count(self) -> int:
        return _truth_count_dict(self.composite_truth_counts)["not_evaluated"]

    @property
    def predicate_match_count(self) -> int:
        return _truth_count_dict(self.hard_eligible_truth_counts)["match"]

    def to_dict(self) -> dict[str, object]:
        return {
            "base_f17_counts": self.base_f17_counts.to_dict(),
            "declared_count": self.declared_count,
            "processed_count": self.base_f17_counts.population.processed_count,
            "pending_count": self.pending_count,
            "excluded_count": self.excluded_count,
            "ma_state_counts": _truth_count_dict(self.ma_state_counts),
            "kdj_state_counts": _truth_count_dict(self.kdj_state_counts),
            "bandwidth_state_counts": _truth_count_dict(self.bandwidth_state_counts),
            "atr14_state_counts": _truth_count_dict(self.atr14_state_counts),
            "technical_truth_counts": _truth_count_dict(self.technical_truth_counts),
            "ma_truth_counts": _truth_count_dict(self.ma_truth_counts),
            "kdj_truth_counts": _truth_count_dict(self.kdj_truth_counts),
            "volatility_truth_counts": _truth_count_dict(self.volatility_truth_counts),
            "composite_truth_counts": _truth_count_dict(self.composite_truth_counts),
            "hard_eligible_truth_counts": _truth_count_dict(self.hard_eligible_truth_counts),
            "active_evaluable_truth_counts": _truth_count_dict(self.active_evaluable_truth_counts),
            "hard_eligible_count": self.hard_eligible_count,
            "active_evaluable_count": self.active_evaluable_count,
            "audit_visible_count": self.audit_visible_count,
            "visible_count": self.visible_count,
            "not_evaluated_count": self.not_evaluated_count,
            "predicate_match_count": self.predicate_match_count,
            "unknown_policy_included_count": self.unknown_policy_included_count,
            "unknown_policy_excluded_count": self.unknown_policy_excluded_count,
        }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionCompositeSortKeyV1:
    query_identity_sha256: str
    stock_code: str
    sort_values: tuple[DailyMarketTechnicalOfficialDispositionSortValueV1, ...]
    fact_row_sha256: str
    technical_snapshot_identity_sha256: str | None
    technical_source_identity: str | None
    ma_evidence_identity_sha256: str | None
    kdj_evidence_identity_sha256: str | None
    volatility_compact_identity_sha256: str | None
    projection_group_session_identity_sha256: str

    def __post_init__(self) -> None:
        _require_sha(self.query_identity_sha256, "sort_key_query_invalid")
        _require_sha(self.fact_row_sha256, "sort_key_fact_invalid")
        _require_sha(
            self.projection_group_session_identity_sha256,
            "sort_key_projection_group_invalid",
        )
        if type(self.stock_code) is not str or _STOCK_CODE_RE.fullmatch(self.stock_code) is None:
            _fail("sort_key_stock_invalid")
        if (
            type(self.sort_values) is not tuple
            or not self.sort_values
            or len(self.sort_values) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_SORT_CLAUSES
            or any(type(value) is not DailyMarketTechnicalOfficialDispositionSortValueV1 for value in self.sort_values)
        ):
            _fail("sort_key_values_invalid")
        if (self.technical_snapshot_identity_sha256 is None) != (self.technical_source_identity is None):
            _fail("sort_key_technical_identity_invalid")
        if self.technical_snapshot_identity_sha256 is not None:
            _require_sha(self.technical_snapshot_identity_sha256, "sort_key_technical_identity_invalid")
            if type(self.technical_source_identity) is not str or not self.technical_source_identity:
                _fail("sort_key_technical_identity_invalid")
        for value, code in (
            (self.ma_evidence_identity_sha256, "sort_key_ma_identity_invalid"),
            (self.kdj_evidence_identity_sha256, "sort_key_kdj_identity_invalid"),
            (self.volatility_compact_identity_sha256, "sort_key_volatility_identity_invalid"),
        ):
            if value is not None:
                _require_sha(value, code)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "daily-market-technical-official-disposition-composite-sort-key.v1",
            "query_identity_sha256": self.query_identity_sha256,
            "stock_code": self.stock_code,
            "sort_values": [item.to_dict() for item in self.sort_values],
            "fact_row_sha256": self.fact_row_sha256,
            "technical_snapshot_identity_sha256": self.technical_snapshot_identity_sha256,
            "technical_source_identity": self.technical_source_identity,
            "ma_evidence_identity_sha256": self.ma_evidence_identity_sha256,
            "kdj_evidence_identity_sha256": self.kdj_evidence_identity_sha256,
            "volatility_compact_identity_sha256": self.volatility_compact_identity_sha256,
            "projection_group_session_identity_sha256": self.projection_group_session_identity_sha256,
        }


def _validate_composite_sort_scalar_v1(
    f17_query: DailyMarketTechnicalOfficialDispositionQueryV1,
    field_name: str,
    value: SortValue | None,
) -> None:
    if value is None:
        return
    if field_name in {"ma_alignment_state", "kdj_state"}:
        if type(value) is not str or value not in {"match", "no_match"}:
            _fail("sort_key_scalar_invalid")
        return
    if field_name in {"decision_date", "latest_feature_date", "official_disposal.observed_date", "kdj_previous.feature_date", "kdj_current.feature_date"}:
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
    if field_name == "stock_code" or field_name in {"market_assignment.state", "official_disposal.state"}:
        if type(value) is not str or not value:
            _fail("sort_key_scalar_invalid")
        if field_name == "stock_code" and _STOCK_CODE_RE.fullmatch(value) is None:
            _fail("sort_key_scalar_invalid")
        if field_name == "market_assignment.state" and value not in {"assigned_twse", "assigned_tpex"}:
            _fail("sort_key_scalar_invalid")
        if field_name == "official_disposal.state" and value not in {
            "reported_upcoming", "reported_active", "reported_elapsed_only",
        }:
            _fail("sort_key_scalar_invalid")
        return
    if any(
        field_name == f"{rule_key}.{metric}"
        for rule_key in f17_query.technical_query.method_rule_keys
        for metric in ("ratio", "numerator", "denominator")
    ) or field_name in {
        "kdj_previous.rsv", "kdj_previous.k", "kdj_previous.d", "kdj_previous.j",
        "kdj_current.rsv", "kdj_current.k", "kdj_current.d", "kdj_current.j",
        "bollinger_bandwidth_pct", "atr14_pct",
    }:
        if type(value) is not Decimal or not value.is_finite() or len(str(value)) > 1024:
            _fail("sort_key_scalar_invalid")
        return
    _fail("sort_key_scalar_invalid")


def sort_composite_keys_v1(
    context: DailyMarketTechnicalOfficialDispositionCompositeEvaluationContextV1,
    keys: Sequence[DailyMarketTechnicalOfficialDispositionCompositeSortKeyV1],
    *,
    cancel_callback: Callable[[], object] | None = None,
) -> tuple[DailyMarketTechnicalOfficialDispositionCompositeSortKeyV1, ...]:
    """對唯一全母體 sort key 集作穩定排序；unknown/null 固定置尾。"""
    _strict_cancel(cancel_callback)
    if type(context) is not DailyMarketTechnicalOfficialDispositionCompositeEvaluationContextV1:
        _fail("sort_context_invalid")
    if isinstance(keys, (str, bytes)) or not isinstance(keys, Sequence):
        _fail("sort_keys_invalid")
    if len(keys) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_ROWS:
        _fail("sort_row_limit")
    query = context.query
    expected = tuple((item.field, item.direction) for item in query.sort_clauses)
    seen: set[str] = set()
    total_bytes = 0
    result: list[DailyMarketTechnicalOfficialDispositionCompositeSortKeyV1] = []
    for index, item in enumerate(keys):
        if index % 256 == 0:
            _strict_cancel(cancel_callback)
        if (
            type(item) is not DailyMarketTechnicalOfficialDispositionCompositeSortKeyV1
            or item.query_identity_sha256 != query.query_identity_sha256
            or item.projection_group_session_identity_sha256
            != query.projection_group_session_identity_sha256
            or item.stock_code in seen
            or tuple((value.field, value.direction) for value in item.sort_values) != expected
        ):
            _fail("sort_key_mismatch")
        for clause, sort_value in zip(query.sort_clauses, item.sort_values, strict=True):
            _validate_composite_sort_scalar_v1(context.f17_query, clause.field, sort_value.value)
            if clause.field == "stock_code" and sort_value.value != item.stock_code:
                _fail("sort_key_stock_code_value_mismatch")
        seen.add(item.stock_code)
        total_bytes += len(_canonical_json_bytes(item.to_dict())) + 1
        if total_bytes > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_SORT_BYTES:
            _fail("sort_key_byte_limit")
        result.append(item)
    _strict_cancel(cancel_callback)
    result.sort(key=lambda item: item.stock_code)
    _strict_cancel(cancel_callback)
    for clause_index in range(len(query.sort_clauses) - 1, -1, -1):
        clause = query.sort_clauses[clause_index]
        known: list[DailyMarketTechnicalOfficialDispositionCompositeSortKeyV1] = []
        nulls: list[DailyMarketTechnicalOfficialDispositionCompositeSortKeyV1] = []
        for index, item in enumerate(result):
            if index % 256 == 0:
                _strict_cancel(cancel_callback)
            value = item.sort_values[clause_index].value
            (nulls if value is None else known).append(item)
        _strict_cancel(cancel_callback)
        if clause.field in {
            "stock_code", "market_assignment.state", "official_disposal.state",
            "ma_alignment_state", "kdj_state",
        }:
            known.sort(
                key=lambda item: cast(str, item.sort_values[clause_index].value),
                reverse=clause.direction == "desc",
            )
        elif clause.field in {
            "decision_date", "latest_feature_date", "official_disposal.observed_date",
            "kdj_previous.feature_date", "kdj_current.feature_date",
        }:
            known.sort(
                key=lambda item: cast(date, item.sort_values[clause_index].value),
                reverse=clause.direction == "desc",
            )
        elif clause.field in {
            "market_assignment.snapshot_observed_at", "official_disposal.observed_at",
        }:
            known.sort(
                key=lambda item: cast(datetime, item.sort_values[clause_index].value),
                reverse=clause.direction == "desc",
            )
        elif clause.field == "raw_row_count":
            known.sort(
                key=lambda item: cast(int, item.sort_values[clause_index].value),
                reverse=clause.direction == "desc",
            )
        else:
            known.sort(
                key=lambda item: cast(Decimal, item.sort_values[clause_index].value),
                reverse=clause.direction == "desc",
            )
        _strict_cancel(cancel_callback)
        result = known + nulls
    _strict_cancel(cancel_callback)
    return tuple(result)


def project_composite_sort_key_v1(
    context: DailyMarketTechnicalOfficialDispositionCompositeEvaluationContextV1,
    fact_row: DailyMarketTechnicalOfficialDispositionFactRowV1,
    technical_row: DailyMarketTechnicalParentV4Row | None,
    ma_entry: DailyMarketTechnicalMaAlignmentCompactEntryV1 | None,
    kdj_entry: DailyMarketTechnicalUniverseKDJCompactEntryV1 | None,
    volatility_entry: DailyMarketTechnicalUniverseVolatilityCompactEntryV1 | None,
    projection_group_session: DailyMarketTechnicalUniverseProjectionGroupSessionV2,
) -> DailyMarketTechnicalOfficialDispositionCompositeSortKeyV1:
    """將 F17/P01 與三個已驗 projection 欄位投影到同一全域排序鍵。

    此函式不自行授予 F17/P01 列的來源資格；唯一 reader 必須先綁定同一
    F17 讀取 session 與有效群組 session，再以新鮮 F17/P01 列、該群組不可變
    預備 tuple 中同代碼的原始三個成員投影。群組發行時已核對 MA/KDJ/波動率
    entries 的完整排序母體及共同來源、snapshot、source clock、decision date
    與 cutoff；本函式再用原 tuple 的精確物件身分拒絕呼叫端重建的同代碼 entry。
    分頁時必須以相同群組的原始成員重算並比對固定排序鍵，不能用呼叫端提供的
    entries 或自算 SHA 取代來源核驗。
    """
    if type(context) is not DailyMarketTechnicalOfficialDispositionCompositeEvaluationContextV1:
        _fail("sort_context_invalid")
    if type(fact_row) is not DailyMarketTechnicalOfficialDispositionFactRowV1:
        _fail("sort_fact_invalid")
    _validate_composite_group_session_v1(context, projection_group_session)
    status = _fact_technical_status(fact_row)
    if status == "processed":
        if (
            type(technical_row) is not DailyMarketTechnicalParentV4Row
            or type(ma_entry) is not DailyMarketTechnicalMaAlignmentCompactEntryV1
            or type(kdj_entry) is not DailyMarketTechnicalUniverseKDJCompactEntryV1
            or type(volatility_entry) is not DailyMarketTechnicalUniverseVolatilityCompactEntryV1
        ):
            _fail("sort_processed_projection_missing")
        _validate_parent_row(context.f17_query, fact_row, technical_row)
        _validate_original_group_entries_for_code_v1(
            projection_group_session,
            fact_row.stock_code,
            ma_entry,
            kdj_entry,
            volatility_entry,
        )
        for entry_code in (ma_entry.stock_code, kdj_entry.stock_code, volatility_entry.stock_code):
            if entry_code != fact_row.stock_code:
                _fail("sort_projection_stock_mismatch")
    elif any(item is not None for item in (technical_row, ma_entry, kdj_entry, volatility_entry)):
        _fail("sort_nonprocessed_projection_present")

    f17_key = project_daily_market_technical_official_disposition_sort_key_v1(
        context.f17_sort_query,
        DailyMarketTechnicalOfficialDispositionJoinedRowV1(fact_row, technical_row),
    )
    f17_values = {item.field: item.value for item in f17_key.sort_values}
    values: list[DailyMarketTechnicalOfficialDispositionSortValueV1] = []
    for clause in context.query.sort_clauses:
        value: SortValue | None
        if clause.field in f17_values:
            value = f17_values[clause.field]
        elif clause.field == "ma_alignment_state":
            value = (
                ma_entry.ma_state if ma_entry is not None and ma_entry.ma_state != "unknown" else None
            )
        elif clause.field == "kdj_state":
            value = (
                kdj_entry.state if kdj_entry is not None and kdj_entry.state != "unknown" else None
            )
        elif clause.field.startswith("kdj_previous.") or clause.field.startswith("kdj_current."):
            day = None
            if kdj_entry is not None:
                day = kdj_entry.previous if clause.field.startswith("kdj_previous.") else kdj_entry.current
            suffix = clause.field.split(".", 1)[1]
            value = None if day is None else getattr(day, suffix)
        elif clause.field == "bollinger_bandwidth_pct":
            value = None if volatility_entry is None else volatility_entry.evidence.bandwidth.value
        elif clause.field == "atr14_pct":
            value = None if volatility_entry is None else volatility_entry.evidence.atr14_sma.normalized_value
        else:
            _fail("sort_projection_field_missing")
        _validate_composite_sort_scalar_v1(context.f17_query, clause.field, value)
        values.append(DailyMarketTechnicalOfficialDispositionSortValueV1(
            field=clause.field,
            direction=clause.direction,
            value=value,
        ))
    return DailyMarketTechnicalOfficialDispositionCompositeSortKeyV1(
        query_identity_sha256=context.query.query_identity_sha256,
        stock_code=fact_row.stock_code,
        sort_values=tuple(values),
        fact_row_sha256=hashlib.sha256(fact_row.body_json.encode("utf-8")).hexdigest(),
        technical_snapshot_identity_sha256=(
            None if technical_row is None else technical_row.snapshot_identity_sha256
        ),
        technical_source_identity=(None if technical_row is None else technical_row.source_identity),
        ma_evidence_identity_sha256=(None if ma_entry is None else ma_entry.evidence_identity_sha256),
        kdj_evidence_identity_sha256=(None if kdj_entry is None else kdj_entry.evidence_identity_sha256),
        volatility_compact_identity_sha256=(
            None if volatility_entry is None else volatility_entry.compact_identity_sha256
        ),
        projection_group_session_identity_sha256=(
            context.query.projection_group_session_identity_sha256
        ),
    )


def validate_composite_sort_key_against_fresh_sources_v1(
    context: DailyMarketTechnicalOfficialDispositionCompositeEvaluationContextV1,
    expected_key: DailyMarketTechnicalOfficialDispositionCompositeSortKeyV1,
    fact_row: DailyMarketTechnicalOfficialDispositionFactRowV1,
    technical_row: DailyMarketTechnicalParentV4Row | None,
    ma_entry: DailyMarketTechnicalMaAlignmentCompactEntryV1 | None,
    kdj_entry: DailyMarketTechnicalUniverseKDJCompactEntryV1 | None,
    volatility_entry: DailyMarketTechnicalUniverseVolatilityCompactEntryV1 | None,
    projection_group_session: DailyMarketTechnicalUniverseProjectionGroupSessionV2,
) -> None:
    """要求讀取頁面時以原 group entries 重建的鍵與 pinned key 完全相同。

    reader 必須以同一有效群組 session 的不可變預備 tuple 依同一股票代碼取得
    原始成員，再傳入本函式。本函式核對群組錨點中的精確成員物件身分，再比較
    query/group、列、成員 identities 與 sort values；呼叫端自行重建 entries 或
    自算 SHA 不能通過此來源核驗。
    """
    if type(context) is not DailyMarketTechnicalOfficialDispositionCompositeEvaluationContextV1:
        _fail("page_sort_context_invalid")
    if (
        type(expected_key) is not DailyMarketTechnicalOfficialDispositionCompositeSortKeyV1
        or expected_key.query_identity_sha256 != context.query.query_identity_sha256
        or expected_key.projection_group_session_identity_sha256
        != context.query.projection_group_session_identity_sha256
    ):
        _fail("page_pinned_sort_key_scope_mismatch")
    actual_key = project_composite_sort_key_v1(
        context,
        fact_row,
        technical_row,
        ma_entry,
        kdj_entry,
        volatility_entry,
        projection_group_session,
    )
    if actual_key.to_dict() != expected_key.to_dict():
        _fail("page_pinned_sort_key_source_mismatch")


def _validate_composite_group_session_v1(
    context: DailyMarketTechnicalOfficialDispositionCompositeEvaluationContextV1,
    projection_group_session: DailyMarketTechnicalUniverseProjectionGroupSessionV2,
) -> None:
    from app_module.daily_market_technical_universe_projection_group_session_v2 import (
        DailyMarketTechnicalUniverseProjectionGroupSessionV2 as GroupSessionType,
    )

    if type(context) is not DailyMarketTechnicalOfficialDispositionCompositeEvaluationContextV1:
        _fail("sort_context_invalid")
    if type(projection_group_session) is not GroupSessionType:
        _fail("sort_group_session_type_invalid")
    try:
        projection_group_session.reader_issued
        group_identity = projection_group_session.identity_sha256
    except Exception as exc:
        raise DailyMarketTechnicalOfficialDispositionCompositeQueryV1Error(
            "sort_group_session_not_active"
        ) from exc
    if group_identity != context.query.projection_group_session_identity_sha256:
        _fail("sort_group_session_binding_mismatch")


def _entry_for_sorted_code_v1(entries: tuple[object, ...], code: str) -> object | None:
    """在群組發行時已核排序的不可變 tuple 內二分查找代碼。"""
    low = 0
    high = len(entries)
    while low < high:
        middle = (low + high) // 2
        entry = entries[middle]
        entry_code = getattr(entry, "stock_code", None)
        if not isinstance(entry_code, str):
            _fail("sort_group_entry_invalid")
        if entry_code < code:
            low = middle + 1
        else:
            high = middle
    if low >= len(entries):
        return None
    candidate = entries[low]
    return candidate if getattr(candidate, "stock_code", None) == code else None


def _validate_original_group_entries_for_code_v1(
    projection_group_session: DailyMarketTechnicalUniverseProjectionGroupSessionV2,
    code: str,
    ma_entry: DailyMarketTechnicalMaAlignmentCompactEntryV1,
    kdj_entry: DailyMarketTechnicalUniverseKDJCompactEntryV1,
    volatility_entry: DailyMarketTechnicalUniverseVolatilityCompactEntryV1,
) -> None:
    try:
        ma_index = projection_group_session.ma_index
        kdj_entries = projection_group_session.kdj_entries
        volatility_entries = projection_group_session.volatility_entries
        if (
            type(ma_index.entries) is not tuple
            or type(kdj_entries) is not tuple
            or type(volatility_entries) is not tuple
        ):
            _fail("sort_group_entries_invalid")
        original_ma = _entry_for_sorted_code_v1(ma_index.entries, code)
        original_kdj = _entry_for_sorted_code_v1(kdj_entries, code)
        original_volatility = _entry_for_sorted_code_v1(volatility_entries, code)
    except DailyMarketTechnicalOfficialDispositionCompositeQueryV1Error:
        raise
    except Exception as exc:
        raise DailyMarketTechnicalOfficialDispositionCompositeQueryV1Error(
            "sort_group_entries_unavailable"
        ) from exc
    if (
        original_ma is not ma_entry
        or original_kdj is not kdj_entry
        or original_volatility is not volatility_entry
    ):
        _fail("sort_group_entry_identity_mismatch")




def _filter_evaluation_payload(
    value: DailyMarketTechnicalOfficialDispositionFilterEvaluationV1,
) -> dict[str, object]:
    return {
        "stock_code": value.stock_code,
        "row_scope": value.row_scope,
        "row_scope_match": value.row_scope_match,
        "stock_filter_match": value.stock_filter_match,
        "market_assignment_match": value.market_assignment_match,
        "market_assignment_truth": value.market_assignment_truth,
        "official_disposal_match": value.official_disposal_match,
        "official_disposal_truth": value.official_disposal_truth,
    }


def _row_identity_payload(
    *,
    query_identity_sha256: str,
    fact_row: DailyMarketTechnicalOfficialDispositionFactRowV1,
    technical_row: DailyMarketTechnicalParentV4Row | None,
    ma_entry: DailyMarketTechnicalMaAlignmentCompactEntryV1 | None,
    kdj_entry: DailyMarketTechnicalUniverseKDJCompactEntryV1 | None,
    volatility_entry: DailyMarketTechnicalUniverseVolatilityCompactEntryV1 | None,
    filter_evaluation: DailyMarketTechnicalOfficialDispositionFilterEvaluationV1,
    evaluation: DailyMarketTechnicalOfficialDispositionCompositeEvaluationV1,
) -> dict[str, object]:
    return {
        "schema_version": "daily-market-technical-official-disposition-composite-result-row.v1",
        "query_identity_sha256": query_identity_sha256,
        "fact_row_sha256": hashlib.sha256(fact_row.body_json.encode("utf-8")).hexdigest(),
        "technical_snapshot_identity_sha256": (
            None if technical_row is None else technical_row.snapshot_identity_sha256
        ),
        "technical_source_identity": None if technical_row is None else technical_row.source_identity,
        "ma_evidence_identity_sha256": None if ma_entry is None else ma_entry.evidence_identity_sha256,
        "kdj_evidence_identity_sha256": None if kdj_entry is None else kdj_entry.evidence_identity_sha256,
        "volatility_compact_identity_sha256": (
            None if volatility_entry is None else volatility_entry.compact_identity_sha256
        ),
        "filter_evaluation": _filter_evaluation_payload(filter_evaluation),
        "composite_evaluation": evaluation.to_dict(),
        "scope": "current_only",
        "official_available_at": None,
        "historical_pit_eligible": False,
    }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionCompositeResultRowV1:
    query_identity_sha256: str
    fact_row: DailyMarketTechnicalOfficialDispositionFactRowV1
    technical_row: DailyMarketTechnicalParentV4Row | None
    ma_entry: DailyMarketTechnicalMaAlignmentCompactEntryV1 | None
    kdj_entry: DailyMarketTechnicalUniverseKDJCompactEntryV1 | None
    volatility_entry: DailyMarketTechnicalUniverseVolatilityCompactEntryV1 | None
    filter_evaluation: DailyMarketTechnicalOfficialDispositionFilterEvaluationV1
    evaluation: DailyMarketTechnicalOfficialDispositionCompositeEvaluationV1
    row_identity_sha256: str

    def __post_init__(self) -> None:
        _require_sha(self.query_identity_sha256, "result_row_query_invalid")
        if (
            type(self.fact_row) is not DailyMarketTechnicalOfficialDispositionFactRowV1
            or type(self.filter_evaluation)
            is not DailyMarketTechnicalOfficialDispositionFilterEvaluationV1
            or type(self.evaluation)
            is not DailyMarketTechnicalOfficialDispositionCompositeEvaluationV1
        ):
            _fail("result_row_invalid")
        code = self.fact_row.stock_code
        if (
            self.filter_evaluation.stock_code != code
            or (
                self.technical_row is not None
                and type(self.technical_row) is not DailyMarketTechnicalParentV4Row
            )
            or (
                self.ma_entry is not None
                and type(self.ma_entry) is not DailyMarketTechnicalMaAlignmentCompactEntryV1
            )
            or (
                self.kdj_entry is not None
                and type(self.kdj_entry) is not DailyMarketTechnicalUniverseKDJCompactEntryV1
            )
            or (
                self.volatility_entry is not None
                and type(self.volatility_entry)
                is not DailyMarketTechnicalUniverseVolatilityCompactEntryV1
            )
            or (self.technical_row is not None and self.technical_row.stock_code != code)
            or (self.ma_entry is not None and self.ma_entry.stock_code != code)
            or (self.kdj_entry is not None and self.kdj_entry.stock_code != code)
            or (self.volatility_entry is not None and self.volatility_entry.stock_code != code)
            or not self.evaluation.visible
        ):
            _fail("result_row_invalid")
        status = _fact_technical_status(self.fact_row)
        projections = (self.technical_row, self.ma_entry, self.kdj_entry, self.volatility_entry)
        if (status == "processed") != all(item is not None for item in projections):
            _fail("result_row_projection_scope_invalid")
        if status != "processed" and any(item is not None for item in projections):
            _fail("result_row_projection_scope_invalid")
        _require_sha(self.row_identity_sha256, "result_row_identity_invalid")
        expected = _sha256_json(_row_identity_payload(
            query_identity_sha256=self.query_identity_sha256,
            fact_row=self.fact_row,
            technical_row=self.technical_row,
            ma_entry=self.ma_entry,
            kdj_entry=self.kdj_entry,
            volatility_entry=self.volatility_entry,
            filter_evaluation=self.filter_evaluation,
            evaluation=self.evaluation,
        ))
        if expected != self.row_identity_sha256:
            _fail("result_row_identity_mismatch")

    @property
    def stock_code(self) -> str:
        return self.fact_row.stock_code

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "daily-market-technical-official-disposition-composite-result-row.v1",
            "query_identity_sha256": self.query_identity_sha256,
            "stock_code": self.stock_code,
            "fact_row": self.fact_row.to_dict(),
            "technical_row": None if self.technical_row is None else self.technical_row.to_dict(),
            "ma_entry": None if self.ma_entry is None else self.ma_entry.to_dict(),
            "kdj_entry": None if self.kdj_entry is None else self.kdj_entry.to_dict(),
            "volatility_entry": None if self.volatility_entry is None else self.volatility_entry.to_dict(),
            "filter_evaluation": _filter_evaluation_payload(self.filter_evaluation),
            "composite_evaluation": self.evaluation.to_dict(),
            "row_identity_sha256": self.row_identity_sha256,
            "scope": "current_only",
            "official_available_at": None,
            "availability_status": "unknown",
            "historical_pit_eligible": False,
        }


def _rows_sha(
    rows: Sequence[DailyMarketTechnicalOfficialDispositionCompositeResultRowV1],
) -> str:
    return _sha256_json([row.to_dict() for row in rows])


def _validate_result_source_pins(
    query: DailyMarketTechnicalOfficialDispositionCompositeQueryV1,
    source_pins: tuple[tuple[str, str], ...],
    *,
    f17_query: DailyMarketTechnicalOfficialDispositionQueryV1 | None = None,
) -> None:
    if type(source_pins) is not tuple or len(source_pins) != len(_SOURCE_PIN_KEYS):
        _fail("result_source_pins_invalid")
    if any(
        type(item) is not tuple
        or len(item) != 2
        or type(item[0]) is not str
        or type(item[1]) is not str
        or not item[1]
        for item in source_pins
    ):
        _fail("result_source_pins_invalid")
    if tuple(item[0] for item in source_pins) != _SOURCE_PIN_KEYS:
        _fail("result_source_pins_invalid")
    pins = dict(source_pins)
    for key in _SOURCE_PIN_KEYS:
        if key.endswith("_sha256"):
            _require_sha(pins[key], "result_source_pin_sha_invalid")
    if f17_query is None:
        f17_query = query.f17_query
    expected = {
        "bundle_output_root": f17_query.bundle_output_root,
        "bundle_identity_sha256": f17_query.bundle_identity_sha256,
        "bundle_manifest_sha256": f17_query.expected_manifest_sha256,
        "market_assignment_pin_identity_sha256": f17_query.market_assignment_pin_identity_sha256,
        "official_disposal_pin_identity_sha256": f17_query.official_disposal_pin_identity_sha256,
        "decision_date": f17_query.decision_date.isoformat(),
        "decision_cutoff": f17_query.decision_cutoff.isoformat(),
        "ma_method_id": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_ID_V1,
        "ma_method_version": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_VERSION_V1,
        "projection_group_session_identity_sha256": query.projection_group_session_identity_sha256,
        "kdj_method_id": KDJ_METHOD_ID_V1,
        "kdj_method_version": KDJ_METHOD_VERSION_V1,
        "kdj_method_identity_sha256": KDJ_METHOD_IDENTITY_SHA256_V1,
        "bandwidth_method_id": BOLLINGER_BANDWIDTH_METHOD_ID_V1,
        "bandwidth_method_version": BOLLINGER_BANDWIDTH_METHOD_VERSION_V1,
        "bandwidth_method_identity_sha256": BOLLINGER_BANDWIDTH_METHOD_IDENTITY_SHA256_V1,
        "atr14_method_id": ATR14_SMA_METHOD_ID_V1,
        "atr14_method_version": ATR14_SMA_METHOD_VERSION_V1,
        "atr14_method_identity_sha256": ATR14_SMA_METHOD_IDENTITY_SHA256_V1,
    }
    if any(pins.get(key) != value for key, value in expected.items()):
        _fail("result_source_scope_mismatch")


def _result_identity(
    *,
    query: DailyMarketTechnicalOfficialDispositionCompositeQueryV1,
    source_pins: tuple[tuple[str, str], ...],
    counts: DailyMarketTechnicalOfficialDispositionCompositeCountsV1,
    ordered_keys: tuple[DailyMarketTechnicalOfficialDispositionCompositeSortKeyV1, ...],
    result_status: str,
    official_coverage_status: str,
) -> str:
    _validate_result_source_pins(query, source_pins)
    return _sha256_json({
        "schema_version": "daily-market-technical-official-disposition-composite-result.v1",
        "query_identity_sha256": query.query_identity_sha256,
        "source_pins": [[key, value] for key, value in source_pins],
        "counts": counts.to_dict(),
        "ordered_keys_sha256": _sha256_json([item.to_dict() for item in ordered_keys]),
        "ordered_codes_sha256": _sha256_json([item.stock_code for item in ordered_keys]),
        "result_status": result_status,
        "official_source_coverage_status": official_coverage_status,
        "scope": "current_only",
        "official_available_at": None,
        "availability_status": "unknown",
        "historical_pit_eligible": False,
    })


_RESULT_ANCHOR_ISSUER_V1 = object()


class _ResultAnchorV1:
    __slots__ = (
        "identity_sha256", "keys_sha256", "counts_sha256", "pins_sha256",
        "read_session", "projection_group_session", "query", "ordered_sort_keys",
        "counts", "source_pins", "ordered_codes_sha256", "result_status",
        "official_source_coverage_status", "_subject", "_locked",
    )
    identity_sha256: str
    keys_sha256: str
    counts_sha256: str
    pins_sha256: str
    read_session: DailyMarketTechnicalOfficialDispositionReadSessionV1
    projection_group_session: DailyMarketTechnicalUniverseProjectionGroupSessionV2
    query: DailyMarketTechnicalOfficialDispositionCompositeQueryV1
    ordered_sort_keys: tuple[DailyMarketTechnicalOfficialDispositionCompositeSortKeyV1, ...] | None
    counts: DailyMarketTechnicalOfficialDispositionCompositeCountsV1 | None
    source_pins: tuple[tuple[str, str], ...] | None
    ordered_codes_sha256: str | None
    result_status: Literal["complete", "partial"] | None
    official_source_coverage_status: Literal["complete", "partial"] | None
    _subject: object | None
    _locked: bool

    def __init__(
        self,
        identity_sha256: str,
        keys_sha256: str,
        counts_sha256: str,
        pins_sha256: str,
        read_session: DailyMarketTechnicalOfficialDispositionReadSessionV1,
        projection_group_session: DailyMarketTechnicalUniverseProjectionGroupSessionV2,
        query: DailyMarketTechnicalOfficialDispositionCompositeQueryV1,
        *,
        issuer: object,
    ) -> None:
        if issuer is not _RESULT_ANCHOR_ISSUER_V1:
            _fail("result_anchor_issuer_invalid")
        for value in (identity_sha256, keys_sha256, counts_sha256, pins_sha256):
            _require_sha(value, "result_anchor_identity_invalid")
        object.__setattr__(self, "identity_sha256", identity_sha256)
        object.__setattr__(self, "keys_sha256", keys_sha256)
        object.__setattr__(self, "counts_sha256", counts_sha256)
        object.__setattr__(self, "pins_sha256", pins_sha256)
        object.__setattr__(self, "read_session", read_session)
        object.__setattr__(self, "projection_group_session", projection_group_session)
        object.__setattr__(self, "query", query)
        object.__setattr__(self, "ordered_sort_keys", None)
        object.__setattr__(self, "counts", None)
        object.__setattr__(self, "source_pins", None)
        object.__setattr__(self, "ordered_codes_sha256", None)
        object.__setattr__(self, "result_status", None)
        object.__setattr__(self, "official_source_coverage_status", None)
        object.__setattr__(self, "_subject", None)
        object.__setattr__(self, "_locked", True)

    def can_claim(self, subject: object) -> bool:
        return self._subject is None or self._subject is subject

    def claim(self, subject: object) -> None:
        if not self.can_claim(subject):
            _fail("result_anchor_subject_mismatch")
        if self._subject is None:
            if type(subject) is not DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1:
                _fail("result_anchor_subject_invalid")
            object.__setattr__(self, "ordered_sort_keys", subject.ordered_sort_keys)
            object.__setattr__(self, "counts", subject.counts)
            object.__setattr__(self, "source_pins", subject.source_pins)
            object.__setattr__(self, "ordered_codes_sha256", subject.ordered_codes_sha256)
            object.__setattr__(self, "result_status", subject.result_status)
            object.__setattr__(
                self,
                "official_source_coverage_status",
                subject.official_source_coverage_status,
            )
            object.__setattr__(self, "_subject", subject)

    def matches_claimed_result(
        self,
        subject: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
    ) -> bool:
        return (
            self._subject is subject
            and subject.query is self.query
            and subject._read_session is self.read_session
            and subject._projection_group_session is self.projection_group_session
            and subject.operation_identity_sha256 == self.identity_sha256
            and subject.ordered_sort_keys is self.ordered_sort_keys
            and subject.counts is self.counts
            and subject.source_pins is self.source_pins
            and subject.ordered_codes_sha256 == self.ordered_codes_sha256
            and subject.result_status == self.result_status
            and subject.official_source_coverage_status
            == self.official_source_coverage_status
            and subject.scope == "current_only"
            and subject.official_available_at is None
            and subject.availability_status == "unknown"
            and subject.historical_pit_eligible is False
        )

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_locked", False):
            raise AttributeError("composite result anchor is immutable")
        object.__setattr__(self, name, value)


_PAGE_ANCHOR_ISSUER_V1 = object()


class _PageAnchorV1:
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
        if issuer is not _PAGE_ANCHOR_ISSUER_V1:
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
            raise AttributeError("composite page anchor is immutable")
        object.__setattr__(self, name, value)


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1:
    """由實際 F17 session 與群組 session 發行的不可變結果封套。

    首次發行完整核對所有排序鍵與摘要；重複讀頁只核對同一 subject 綁定的
    不可變 tuple、counts、source pins 與所有者參照，避免每頁重建全母體摘要。
    這不是防止同程序惡意 ``object.__setattr__`` 的安全邊界；reader 仍須在
    每頁重新讀取所選來源列，並以同一群組的原始 entries 重建固定排序鍵。
    """

    query: DailyMarketTechnicalOfficialDispositionCompositeQueryV1
    operation_identity_sha256: str
    ordered_codes_sha256: str
    counts: DailyMarketTechnicalOfficialDispositionCompositeCountsV1
    source_pins: tuple[tuple[str, str], ...]
    ordered_sort_keys: tuple[DailyMarketTechnicalOfficialDispositionCompositeSortKeyV1, ...]
    result_status: Literal["complete", "partial"]
    official_source_coverage_status: Literal["complete", "partial"]
    scope: Literal["current_only"]
    official_available_at: None
    availability_status: Literal["unknown"]
    historical_pit_eligible: Literal[False]
    _read_session: DailyMarketTechnicalOfficialDispositionReadSessionV1 = field(repr=False, compare=False)
    _projection_group_session: DailyMarketTechnicalUniverseProjectionGroupSessionV2 = field(repr=False, compare=False)
    _anchor: _ResultAnchorV1 = field(repr=False, compare=False)
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            self._seal is not _RESULT_SEAL_V1
            or type(self._anchor) is not _ResultAnchorV1
        ):
            _fail("result_not_reader_issued")
        if self._anchor._subject is self:
            # 此快路徑只略過全母體重雜湊；所有者與來源核驗保留，頁面列仍由 reader 新鮮重讀。
            if not self._anchor.matches_claimed_result(self):
                _fail("result_not_reader_issued")
            _validate_result_source_pins_with_issuer(
                self.query,
                self.source_pins,
                self._read_session,
                self._projection_group_session,
            )
            return
        if (
            not self._anchor.can_claim(self)
            or self._anchor.read_session is not self._read_session
            or self._anchor.projection_group_session is not self._projection_group_session
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
            or self.counts.visible_count > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_ROWS
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
        _validate_result_source_pins_with_issuer(
            self.query,
            self.source_pins,
            self._read_session,
            self._projection_group_session,
        )
        self._anchor.claim(self)

    @property
    def visible_count(self) -> int:
        return self.counts.visible_count

    @property
    def matching_count(self) -> int:
        """相容別名：政策後可見列數，不等於 predicate truth=match。"""
        return self.visible_count

    def read_page(
        self,
        page_index: int,
        page_size: int,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalOfficialDispositionCompositeQueryPageV1:
        _strict_cancel(cancel_callback)
        request = DailyMarketTechnicalOfficialDispositionCompositePageRequestV1.create(
            self.query, page_index=page_index, page_size=page_size,
        )
        return self.read_page_request(request, cancel_callback=cancel_callback)

    def read_page_request(
        self,
        request: DailyMarketTechnicalOfficialDispositionCompositePageRequestV1 | bytes | str,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalOfficialDispositionCompositeQueryPageV1:
        _strict_cancel(cancel_callback)
        if self._seal is not _RESULT_SEAL_V1:
            _fail("result_not_reader_issued")
        self.__post_init__()
        if isinstance(request, (bytes, str)):
            request = DailyMarketTechnicalOfficialDispositionCompositePageRequestV1.from_json(request)
        if type(request) is not DailyMarketTechnicalOfficialDispositionCompositePageRequestV1:
            _fail("page_request_invalid")
        if request.query.query_identity_sha256 != self.query.query_identity_sha256:
            _fail("page_request_query_mismatch")
        if not callable(getattr(self._read_session, "_materialize_composite_query_page_v1", None)):
            _fail("read_session_page_reader_unavailable")
        reader = cast(_CompositePageMaterializer, self._read_session)
        return reader._materialize_composite_query_page_v1(
            self, request, cancel_callback,
        )


def _validate_page_request_for_result_v1(
    result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
    request: DailyMarketTechnicalOfficialDispositionCompositePageRequestV1,
) -> None:
    if (
        type(result) is not DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1
        or type(request) is not DailyMarketTechnicalOfficialDispositionCompositePageRequestV1
    ):
        _fail("page_request_input_invalid")
    result.__post_init__()
    request_query = request.query
    expected = DailyMarketTechnicalOfficialDispositionCompositePageRequestV1.create(
        result.query,
        page_index=request.page_index,
        page_size=request.page_size,
    )
    if (
        request_query.query_identity_sha256 != result.query.query_identity_sha256
        or request.to_json() != expected.to_json()
    ):
        _fail("page_request_query_mismatch")
    page_count = (result.visible_count + request.page_size - 1) // request.page_size
    if (page_count == 0 and request.page_index != 0) or (
        page_count > 0 and request.page_index >= page_count
    ):
        _fail("page_request_out_of_range")


def _page_identity(
    *,
    result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
    request: DailyMarketTechnicalOfficialDispositionCompositePageRequestV1,
    rows: tuple[DailyMarketTechnicalOfficialDispositionCompositeResultRowV1, ...],
) -> str:
    return _sha256_json({
        "schema_version": "daily-market-technical-official-disposition-composite-page.v1",
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


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionCompositeQueryPageV1:
    query: DailyMarketTechnicalOfficialDispositionCompositeQueryV1
    request_identity_sha256: str
    operation_identity_sha256: str
    page_identity_sha256: str
    page_index: int
    page_size: int
    page_count: int
    counts: DailyMarketTechnicalOfficialDispositionCompositeCountsV1
    rows: tuple[DailyMarketTechnicalOfficialDispositionCompositeResultRowV1, ...]
    source_pins: tuple[tuple[str, str], ...]
    result_status: Literal["complete", "partial"]
    official_source_coverage_status: Literal["complete", "partial"]
    scope: Literal["current_only"]
    official_available_at: None
    availability_status: Literal["unknown"]
    historical_pit_eligible: Literal[False]
    _result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1 = field(repr=False, compare=False)
    _anchor: _PageAnchorV1 = field(repr=False, compare=False)
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        _validate_page(self.page_index, self.page_size)
        self._result.__post_init__()
        if (
            self._seal is not _PAGE_SEAL_V1
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
        request = DailyMarketTechnicalOfficialDispositionCompositePageRequestV1.create(
            self.query, page_index=self.page_index, page_size=self.page_size,
        )
        start = self.page_index * self.page_size
        expected_codes = tuple(
            item.stock_code for item in self._result.ordered_sort_keys[start:start + self.page_size]
        )
        if (
            tuple(row.stock_code for row in self.rows) != expected_codes
            or any(not row.evaluation.visible for row in self.rows)
            or _page_identity(result=self._result, request=request, rows=self.rows)
            != self.page_identity_sha256
            or request.request_identity_sha256 != self.request_identity_sha256
        ):
            _fail("page_identity_mismatch")
        self._anchor.claim(self)

    @property
    def visible_count(self) -> int:
        return self.counts.visible_count

    @property
    def matching_count(self) -> int:
        """相容別名：政策後可見列數，不等於 predicate truth=match。"""
        return self.visible_count

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "daily-market-technical-official-disposition-composite-page.v1",
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
            "scope": "current_only",
            "official_available_at": None,
            "availability_status": "unknown",
            "historical_pit_eligible": False,
        }


def _issue_result_v1(
    *,
    query: DailyMarketTechnicalOfficialDispositionCompositeQueryV1,
    counts: DailyMarketTechnicalOfficialDispositionCompositeCountsV1,
    source_pins: tuple[tuple[str, str], ...],
    ordered_keys: tuple[DailyMarketTechnicalOfficialDispositionCompositeSortKeyV1, ...],
    result_status: Literal["complete", "partial"],
    official_source_coverage_status: Literal["complete", "partial"],
    read_session: DailyMarketTechnicalOfficialDispositionReadSessionV1,
    projection_group_session: DailyMarketTechnicalUniverseProjectionGroupSessionV2,
) -> DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1:
    from app_module.daily_market_technical_universe_projection_group_session_v2 import (
        DailyMarketTechnicalUniverseProjectionGroupSessionV2 as GroupSessionType,
    )

    if (
        type(query) is not DailyMarketTechnicalOfficialDispositionCompositeQueryV1
        or type(counts) is not DailyMarketTechnicalOfficialDispositionCompositeCountsV1
        or type(ordered_keys) is not tuple
        or type(projection_group_session) is not GroupSessionType
        or result_status not in {"complete", "partial"}
        or official_source_coverage_status not in {"complete", "partial"}
    ):
        _fail("result_issue_inputs_invalid")
    counts.to_dict()
    _validate_result_source_pins_with_issuer(
        query,
        source_pins,
        read_session,
        projection_group_session,
    )
    if (
        len(ordered_keys) != counts.visible_count
        or len({item.stock_code for item in ordered_keys}) != len(ordered_keys)
        or len(ordered_keys) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_ROWS
        or any(
            type(item) is not DailyMarketTechnicalOfficialDispositionCompositeSortKeyV1
            or item.query_identity_sha256 != query.query_identity_sha256
            or item.projection_group_session_identity_sha256 != query.projection_group_session_identity_sha256
            for item in ordered_keys
        )
    ):
        _fail("result_issue_keys_invalid")
    operation = _result_identity(
        query=query,
        source_pins=source_pins,
        counts=counts,
        ordered_keys=ordered_keys,
        result_status=result_status,
        official_coverage_status=official_source_coverage_status,
    )
    return DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1(
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
        _projection_group_session=projection_group_session,
        _anchor=_ResultAnchorV1(
            identity_sha256=operation,
            keys_sha256=_sha256_json([item.to_dict() for item in ordered_keys]),
            counts_sha256=_sha256_json(counts.to_dict()),
            pins_sha256=_sha256_json([[key, value] for key, value in source_pins]),
            read_session=read_session,
            projection_group_session=projection_group_session,
            query=query,
            issuer=_RESULT_ANCHOR_ISSUER_V1,
        ),
        _seal=_RESULT_SEAL_V1,
    )


def _issue_page_v1(
    *,
    result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
    request: DailyMarketTechnicalOfficialDispositionCompositePageRequestV1,
    rows: tuple[DailyMarketTechnicalOfficialDispositionCompositeResultRowV1, ...],
) -> DailyMarketTechnicalOfficialDispositionCompositeQueryPageV1:
    _validate_page_request_for_result_v1(result, request)
    identity = _page_identity(result=result, request=request, rows=rows)
    return DailyMarketTechnicalOfficialDispositionCompositeQueryPageV1(
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
            issuer=_PAGE_ANCHOR_ISSUER_V1,
        ),
        _seal=_PAGE_SEAL_V1,
    )
