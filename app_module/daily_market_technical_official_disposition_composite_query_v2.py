"""以同一 V3 四路 session 執行 F17/P01/F07 全母體複合查詢。"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
from typing import Any, Literal, NoReturn, cast

import app_module.daily_market_technical_official_disposition_composite_query_v1 as c
import app_module.daily_market_technical_official_disposition_query_reader_v1 as r
from app_module.daily_market_technical_official_disposition_bundle_v1 import (
    DailyMarketTechnicalOfficialDispositionBundleSelectedRowsV1,
    DailyMarketTechnicalOfficialDispositionFactRowV1,
)
from app_module.daily_market_technical_official_disposition_query_v1 import (
    DailyMarketTechnicalOfficialDispositionFilterEvaluationV1,
)
from app_module.daily_market_technical_parent_v4_query import DailyMarketTechnicalParentV4Row
from app_module.daily_market_technical_universe_kdj_alignment_query_v1 import (
    DailyMarketTechnicalUniverseKDJCompactEntryV1,
)
from app_module.daily_market_technical_universe_ma_alignment_query_v1 import (
    DailyMarketTechnicalMaAlignmentCompactEntryV1,
)
from app_module.daily_market_technical_universe_price_query_v1 import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_METHOD_VERSION,
    DailyMarketTechnicalUniversePriceFactV1,
    digest_daily_market_technical_universe_price_facts_v1,
)
from app_module.daily_market_technical_universe_v4_query import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_PAGE_SIZE,
    DailyMarketTechnicalUniverseV4ReadSelectionPage,
    DailyMarketTechnicalUniverseV4SelectedRows,
)
from app_module.daily_market_technical_universe_volatility_alignment_query_v1 import (
    DailyMarketTechnicalUniverseVolatilityCompactEntryV1,
)
from app_module.daily_market_technical_universe_projection_group_session_v3 import (
    DailyMarketTechnicalUniverseProjectionGroupSessionV3,
)


DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_QUERY_V2_SCHEMA = (
    "daily-market-technical-official-disposition-composite-query.v2"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_RESULT_V2_SCHEMA = (
    "daily-market-technical-official-disposition-composite-query-result.v2"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_PAGE_V2_SCHEMA = (
    "daily-market-technical-official-disposition-composite-page.v2"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_ROW_V2_SCHEMA = (
    "daily-market-technical-official-disposition-composite-result-row.v2"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_QUERY_BYTES = 32 * 1024 * 1024
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_RESULT_BYTES = 64 * 1024 * 1024
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_PAGE_BYTES = 32 * 1024 * 1024
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_PAGE_SIZE = (
    c.DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_PAGE_SIZE
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_PAGE_INDEX = (
    c.DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_PAGE_INDEX
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_SORT_CLAUSES = (
    c.DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_SORT_CLAUSES
)

_SHA256_RE = c._SHA256_RE
_TRUTH_ORDER = c._TRUTH_ORDER
_STATE_ORDER = c._STATE_ORDER
_UNKNOWN_PRICE_POLICIES = {"include", "exclude", "only"}
_RESULT_ANCHOR_ISSUER_V2 = object()
_PAGE_ANCHOR_ISSUER_V2 = object()
_SORT_VALUE_TYPES = (str, int, Decimal, date, datetime)
_MAX_JSON_DEPTH = c.DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_JSON_DEPTH


class DailyMarketTechnicalOfficialDispositionCompositeQueryV2Error(ValueError):
    """V2 request/result 契約的穩定拒絕碼。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"technical_official_composite_query_v2_{code}")


def _fail(code: str) -> NoReturn:
    raise DailyMarketTechnicalOfficialDispositionCompositeQueryV2Error(code)


class _ReaderIssuedIdentityAnchorV2:
    """綁定一次 reader 發行資料與原始 subject 的不可變錨點。"""

    __slots__ = ("identity_sha256", "subject", "_locked")

    identity_sha256: str
    subject: object
    _locked: bool

    def __init__(self, identity_sha256: str, subject: object, *, issuer: object) -> None:
        if issuer not in {_RESULT_ANCHOR_ISSUER_V2, _PAGE_ANCHOR_ISSUER_V2}:
            _fail("reader_identity_anchor_issuer_invalid")
        _sha(identity_sha256, "reader_identity_anchor_invalid")
        if subject is None:
            _fail("reader_identity_anchor_subject_invalid")
        object.__setattr__(self, "identity_sha256", identity_sha256)
        object.__setattr__(self, "subject", subject)
        object.__setattr__(self, "_locked", True)

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_locked", False):
            raise AttributeError("reader-issued identity anchor is immutable")
        object.__setattr__(self, name, value)


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _canonical_json_bytes(value: object) -> bytes:
    _reject_float_tree(value)
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _parse_json(raw: bytes | str, *, maximum_bytes: int) -> tuple[object, str]:
    if isinstance(raw, bytes):
        if len(raw) > maximum_bytes:
            _fail("json_byte_limit")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DailyMarketTechnicalOfficialDispositionCompositeQueryV2Error(
                "json_utf8_invalid"
            ) from exc
    elif type(raw) is str:
        if len(raw.encode("utf-8")) > maximum_bytes:
            _fail("json_byte_limit")
        text = raw
    else:
        _fail("json_input_invalid")
    _preflight_json_depth(text)
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=lambda _value: _fail("json_constant_invalid"),
            parse_float=lambda _value: _fail("json_float_invalid"),
        )
    except DailyMarketTechnicalOfficialDispositionCompositeQueryV2Error:
        raise
    except (UnicodeError, ValueError, TypeError) as exc:
        raise DailyMarketTechnicalOfficialDispositionCompositeQueryV2Error(
            "json_invalid"
        ) from exc
    return value, text


def _reject_float_tree(value: object, *, depth: int = 0) -> None:
    if depth > _MAX_JSON_DEPTH:
        _fail("json_depth_limit")
    if isinstance(value, float):
        _fail("json_float_invalid")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if type(key) is not str:
                _fail("json_key_invalid")
            _reject_float_tree(item, depth=depth + 1)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_float_tree(item, depth=depth + 1)


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
            if depth > _MAX_JSON_DEPTH:
                _fail("json_depth_limit")
        elif char in "]}":
            depth -= 1


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail("json_duplicate_key")
        result[key] = value
    return result


def _sha(value: object, code: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        _fail(code)
    return cast(str, value)


def _canonical_decimal(value: object) -> Decimal | None:
    try:
        normalized = c._canonical_decimal(value)
    except (TypeError, ValueError) as exc:
        raise DailyMarketTechnicalOfficialDispositionCompositeQueryV2Error(
            "price_decimal_invalid"
        ) from exc
    if normalized is not None and (
        type(normalized) is not Decimal or not normalized.is_finite()
    ):
        _fail("price_decimal_invalid")
    return normalized


def _decimal_text(value: Decimal | None) -> str | None:
    return c._decimal_text(value)


def _parse_decimal_text(value: object) -> Decimal | None:
    try:
        result = c._parse_decimal_text(value)
    except (TypeError, ValueError) as exc:
        raise DailyMarketTechnicalOfficialDispositionCompositeQueryV2Error(
            "price_decimal_text_invalid"
        ) from exc
    if value is not None and _decimal_text(result) != value:
        _fail("price_decimal_noncanonical")
    return result


def _base_query_with_sort(
    source: c.DailyMarketTechnicalOfficialDispositionCompositeQueryV1,
    clauses: tuple[DailyMarketTechnicalOfficialDispositionCompositeSortClauseV2, ...],
) -> c.DailyMarketTechnicalOfficialDispositionCompositeQueryV1:
    base_clauses = tuple(
        c.DailyMarketTechnicalOfficialDispositionCompositeSortClauseV1(
            item.field,
            cast(c.CompositeSortDirection, item.direction),
        )
        for item in clauses
        if item.field != "price.close_price"
    )
    if not base_clauses:
        base_clauses = (
            c.DailyMarketTechnicalOfficialDispositionCompositeSortClauseV1(
                "stock_code", "asc",
            ),
        )
    return c.DailyMarketTechnicalOfficialDispositionCompositeQueryV1.create(
        source.f17_query,
        projection_group_session_identity_sha256=(
            source.projection_group_session_identity_sha256
        ),
        ma_states=source.ma_states,
        kdj_states=source.kdj_states,
        bandwidth_min_pct=source.bandwidth_min_pct,
        bandwidth_max_pct=source.bandwidth_max_pct,
        atr14_min_pct=source.atr14_min_pct,
        atr14_max_pct=source.atr14_max_pct,
        condition_combine_mode=source.condition_combine_mode,
        unknown_policy=source.unknown_policy,
        sort_clauses=base_clauses,
    )


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionCompositeSortClauseV2:
    field: str
    direction: Literal["asc", "desc"]

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
    def from_dict(
        cls,
        value: object,
    ) -> DailyMarketTechnicalOfficialDispositionCompositeSortClauseV2:
        if not isinstance(value, Mapping) or set(value) != {"field", "direction"}:
            _fail("sort_clause_fields_invalid")
        field_name = value.get("field")
        direction = value.get("direction")
        if type(field_name) is not str or type(direction) is not str:
            _fail("sort_clause_fields_invalid")
        return cls(field_name, cast(Literal["asc", "desc"], direction))


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionCompositeQueryV2:
    base_query_json: str
    base_query_identity_sha256: str
    projection_group_session_identity_sha256: str
    min_close_price: Decimal | None
    max_close_price: Decimal | None
    min_inclusive: bool
    max_inclusive: bool
    unknown_price_policy: Literal["include", "exclude", "only"]
    sort_clauses: tuple[DailyMarketTechnicalOfficialDispositionCompositeSortClauseV2, ...]
    query_identity_sha256: str

    def __post_init__(self) -> None:
        _sha(self.base_query_identity_sha256, "base_query_identity_invalid")
        _sha(self.projection_group_session_identity_sha256, "group_identity_invalid")
        _sha(self.query_identity_sha256, "query_identity_invalid")
        if type(self.base_query_json) is not str or not self.base_query_json:
            _fail("base_query_json_invalid")
        if len(self.base_query_json.encode("utf-8")) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_QUERY_BYTES:
            _fail("base_query_byte_limit")
        try:
            base_query = c.DailyMarketTechnicalOfficialDispositionCompositeQueryV1.from_json(
                self.base_query_json
            )
        except (TypeError, ValueError, UnicodeError) as exc:
            raise DailyMarketTechnicalOfficialDispositionCompositeQueryV2Error(
                "base_query_invalid"
            ) from exc
        if (
            base_query.to_json() != self.base_query_json
            or base_query.query_identity_sha256 != self.base_query_identity_sha256
            or base_query.projection_group_session_identity_sha256
            != self.projection_group_session_identity_sha256
        ):
            _fail("base_query_identity_mismatch")
        for name, value in (
            ("min_close_price", self.min_close_price),
            ("max_close_price", self.max_close_price),
        ):
            try:
                normalized = _canonical_decimal(value)
            except DailyMarketTechnicalOfficialDispositionCompositeQueryV2Error as exc:
                raise DailyMarketTechnicalOfficialDispositionCompositeQueryV2Error(
                    f"{name}_invalid"
                ) from exc
            if normalized != value:
                _fail(f"{name}_noncanonical")
        if (
            type(self.min_inclusive) is not bool
            or type(self.max_inclusive) is not bool
            or type(self.unknown_price_policy) is not str
            or self.unknown_price_policy not in _UNKNOWN_PRICE_POLICIES
        ):
            _fail("price_policy_invalid")
        if (
            self.min_close_price is not None
            and self.max_close_price is not None
            and self.min_close_price > self.max_close_price
        ):
            _fail("price_range_invalid")
        _validate_sort_clauses(base_query.f17_query, self.sort_clauses)
        expected_base = _base_query_with_sort(base_query, self.sort_clauses)
        if expected_base.to_json() != self.base_query_json:
            _fail("base_query_sort_mismatch")
        if _sha256_json(_query_body_v2(self)) != self.query_identity_sha256:
            _fail("query_identity_mismatch")

    @property
    def base_query(self) -> c.DailyMarketTechnicalOfficialDispositionCompositeQueryV1:
        return c.DailyMarketTechnicalOfficialDispositionCompositeQueryV1.from_json(
            self.base_query_json
        )

    @property
    def f17_query(self) -> Any:
        return self.base_query.f17_query

    @property
    def active_price_filter(self) -> bool:
        return (
            self.min_close_price is not None
            or self.max_close_price is not None
            or self.unknown_price_policy != "include"
        )

    @classmethod
    def create(
        cls,
        base_query: c.DailyMarketTechnicalOfficialDispositionCompositeQueryV1,
        *,
        min_close_price: Decimal | None = None,
        max_close_price: Decimal | None = None,
        min_inclusive: bool = True,
        max_inclusive: bool = True,
        unknown_price_policy: Literal["include", "exclude", "only"] = "include",
        sort_clauses: Sequence[DailyMarketTechnicalOfficialDispositionCompositeSortClauseV2] = (),
    ) -> DailyMarketTechnicalOfficialDispositionCompositeQueryV2:
        if type(base_query) is not c.DailyMarketTechnicalOfficialDispositionCompositeQueryV1:
            _fail("base_query_type_invalid")
        base_query.to_json()
        normalized_min = _canonical_decimal(min_close_price)
        normalized_max = _canonical_decimal(max_close_price)
        if (
            normalized_min is not None
            and normalized_max is not None
            and normalized_min > normalized_max
        ):
            _fail("price_range_invalid")
        if (
            type(min_inclusive) is not bool
            or type(max_inclusive) is not bool
            or type(unknown_price_policy) is not str
            or unknown_price_policy not in _UNKNOWN_PRICE_POLICIES
        ):
            _fail("price_policy_invalid")
        if isinstance(sort_clauses, (str, bytes)) or not isinstance(sort_clauses, Sequence):
            _fail("sort_clauses_invalid")
        normalized_sorts = tuple(sort_clauses)
        if not normalized_sorts:
            normalized_sorts = (
                DailyMarketTechnicalOfficialDispositionCompositeSortClauseV2(
                    "stock_code", "asc",
                ),
            )
        _validate_sort_clauses(base_query.f17_query, normalized_sorts)
        stock_positions = [
            index for index, clause in enumerate(normalized_sorts)
            if type(clause) is DailyMarketTechnicalOfficialDispositionCompositeSortClauseV2
            and clause.field == "stock_code"
        ]
        if not stock_positions:
            normalized_sorts = (
                *normalized_sorts,
                DailyMarketTechnicalOfficialDispositionCompositeSortClauseV2(
                    "stock_code", "asc",
                ),
            )
        query_base = _base_query_with_sort(base_query, normalized_sorts)
        body = {
            "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_QUERY_V2_SCHEMA,
            "verification_status": "request_only",
            "base_query_json": query_base.to_json(),
            "base_query_identity_sha256": query_base.query_identity_sha256,
            "projection_group_session_identity_sha256": (
                query_base.projection_group_session_identity_sha256
            ),
            "min_close_price": _decimal_text(normalized_min),
            "max_close_price": _decimal_text(normalized_max),
            "min_inclusive": min_inclusive,
            "max_inclusive": max_inclusive,
            "unknown_price_policy": unknown_price_policy,
            "sort_clauses": [item.to_dict() for item in normalized_sorts],
            "scope": "current_only",
            "official_available_at": None,
            "availability_status": "unknown",
            "historical_pit_eligible": False,
        }
        result = cls(
            base_query_json=query_base.to_json(),
            base_query_identity_sha256=query_base.query_identity_sha256,
            projection_group_session_identity_sha256=(
                query_base.projection_group_session_identity_sha256
            ),
            min_close_price=normalized_min,
            max_close_price=normalized_max,
            min_inclusive=min_inclusive,
            max_inclusive=max_inclusive,
            unknown_price_policy=unknown_price_policy,
            sort_clauses=normalized_sorts,
            query_identity_sha256=_sha256_json(body),
        )
        result.to_json()
        return result

    @classmethod
    def from_dict(
        cls,
        value: object,
    ) -> DailyMarketTechnicalOfficialDispositionCompositeQueryV2:
        expected = {
            "schema_version", "verification_status", "base_query_json",
            "base_query_identity_sha256", "projection_group_session_identity_sha256",
            "min_close_price", "max_close_price", "min_inclusive", "max_inclusive",
            "unknown_price_policy", "sort_clauses", "scope",
            "official_available_at", "availability_status",
            "historical_pit_eligible", "query_identity_sha256",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            _fail("query_fields_invalid")
        if (
            value.get("schema_version") != DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_QUERY_V2_SCHEMA
            or value.get("verification_status") != "request_only"
            or value.get("scope") != "current_only"
            or value.get("official_available_at") is not None
            or value.get("availability_status") != "unknown"
            or value.get("historical_pit_eligible") is not False
        ):
            _fail("query_status_invalid")
        base_query_json = value.get("base_query_json")
        if type(base_query_json) is not str:
            _fail("base_query_json_invalid")
        base_query = c.DailyMarketTechnicalOfficialDispositionCompositeQueryV1.from_json(
            base_query_json
        )
        raw_sorts = value.get("sort_clauses")
        if not isinstance(raw_sorts, list):
            _fail("sort_clauses_invalid")
        sorts = tuple(DailyMarketTechnicalOfficialDispositionCompositeSortClauseV2.from_dict(
            item,
        ) for item in raw_sorts)
        min_value = _parse_decimal_text(value.get("min_close_price"))
        max_value = _parse_decimal_text(value.get("max_close_price"))
        if (
            type(value.get("min_inclusive")) is not bool
            or type(value.get("max_inclusive")) is not bool
        ):
            _fail("price_policy_invalid")
        result = cls.create(
            base_query,
            min_close_price=min_value,
            max_close_price=max_value,
            min_inclusive=cast(bool, value.get("min_inclusive")),
            max_inclusive=cast(bool, value.get("max_inclusive")),
            unknown_price_policy=cast(
                Literal["include", "exclude", "only"],
                value.get("unknown_price_policy"),
            ),
            sort_clauses=sorts,
        )
        if (
            value.get("base_query_identity_sha256") != result.base_query_identity_sha256
            or value.get("projection_group_session_identity_sha256")
            != result.projection_group_session_identity_sha256
            or value.get("query_identity_sha256") != result.query_identity_sha256
            or result.to_dict() != dict(value)
        ):
            _fail("query_identity_mismatch")
        return result

    @classmethod
    def from_json(
        cls,
        raw: bytes | str,
    ) -> DailyMarketTechnicalOfficialDispositionCompositeQueryV2:
        payload, text = _parse_json(
            raw,
            maximum_bytes=DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_QUERY_BYTES,
        )
        result = cls.from_dict(payload)
        if result.to_json() != text:
            _fail("query_noncanonical")
        return result

    def to_dict(self) -> dict[str, object]:
        return _query_body_v2(self) | {"query_identity_sha256": self.query_identity_sha256}

    def to_json(self) -> str:
        encoded = _canonical_json_bytes(self.to_dict())
        if len(encoded) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_QUERY_BYTES:
            _fail("query_byte_limit")
        return encoded.decode("utf-8")


def _query_body_v2(
    query: DailyMarketTechnicalOfficialDispositionCompositeQueryV2,
) -> dict[str, object]:
    return {
        "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_QUERY_V2_SCHEMA,
        "verification_status": "request_only",
        "base_query_json": query.base_query_json,
        "base_query_identity_sha256": query.base_query_identity_sha256,
        "projection_group_session_identity_sha256": (
            query.projection_group_session_identity_sha256
        ),
        "min_close_price": _decimal_text(query.min_close_price),
        "max_close_price": _decimal_text(query.max_close_price),
        "min_inclusive": query.min_inclusive,
        "max_inclusive": query.max_inclusive,
        "unknown_price_policy": query.unknown_price_policy,
        "sort_clauses": [item.to_dict() for item in query.sort_clauses],
        "scope": "current_only",
        "official_available_at": None,
        "availability_status": "unknown",
        "historical_pit_eligible": False,
    }


def _validate_sort_clauses(
    f17_query: Any,
    clauses: tuple[DailyMarketTechnicalOfficialDispositionCompositeSortClauseV2, ...],
) -> None:
    allowed = c._sort_field_allowlist(f17_query) | {"price.close_price"}
    if (
        type(clauses) is not tuple
        or not clauses
        or len(clauses) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_SORT_CLAUSES
        or any(type(item) is not DailyMarketTechnicalOfficialDispositionCompositeSortClauseV2 for item in clauses)
        or len({item.field for item in clauses}) != len(clauses)
        or any(item.field not in allowed for item in clauses)
    ):
        _fail("sort_clauses_invalid")
    stock_positions = [
        index for index, clause in enumerate(clauses)
        if clause.field == "stock_code"
    ]
    if stock_positions and (
        stock_positions != [len(clauses) - 1]
        or clauses[-1].direction != "asc"
    ):
        _fail("stock_code_tiebreak_invalid")


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionCompositeEvaluationV2:
    technical_truth: c.CompositeTruth
    ma_truth: c.CompositeTruth
    kdj_truth: c.CompositeTruth
    volatility_truth: c.CompositeTruth
    price_truth: c.CompositeTruth
    composite_truth: c.CompositeTruth
    active_groups: tuple[bool, bool, bool, bool, bool]
    hard_eligible: bool
    audit_visible: bool
    included_by_unknown_policy: bool
    predicate_match: bool
    visible: bool

    def __post_init__(self) -> None:
        truths = (
            self.technical_truth, self.ma_truth, self.kdj_truth,
            self.volatility_truth, self.price_truth, self.composite_truth,
        )
        if (
            type(self.active_groups) is not tuple
            or len(self.active_groups) != 5
            or any(type(item) is not bool for item in self.active_groups)
            or any(item not in _TRUTH_ORDER for item in truths)
            or any(type(item) is not bool for item in (
                self.hard_eligible, self.audit_visible,
                self.included_by_unknown_policy, self.predicate_match, self.visible,
            ))
        ):
            _fail("evaluation_invalid")

    def to_dict(self) -> dict[str, object]:
        return {
            "technical_truth": self.technical_truth,
            "ma_truth": self.ma_truth,
            "kdj_truth": self.kdj_truth,
            "volatility_truth": self.volatility_truth,
            "price_truth": self.price_truth,
            "composite_truth": self.composite_truth,
            "active_groups": list(self.active_groups),
            "hard_eligible": self.hard_eligible,
            "audit_visible": self.audit_visible,
            "included_by_unknown_policy": self.included_by_unknown_policy,
            "predicate_match": self.predicate_match,
            "visible": self.visible,
        }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionCompositeQueryV2Counts:
    base_f17_counts: Any
    base_composite_counts: c.DailyMarketTechnicalOfficialDispositionCompositeCountsV1
    price_truth_counts: tuple[tuple[str, int], ...]
    final_truth_counts: tuple[tuple[str, int], ...]
    price_known_count: int
    price_unknown_count: int
    base_visible_count: int
    visible_count: int

    def __post_init__(self) -> None:
        expected_truths = ("match", "no_match", "unknown", "not_evaluated", "not_applicable")
        if (
            type(self.base_f17_counts)
            is not r.DailyMarketTechnicalOfficialDispositionQueryCountsV1
            or type(self.base_composite_counts) is not c.DailyMarketTechnicalOfficialDispositionCompositeCountsV1
            or self.base_composite_counts.base_f17_counts != self.base_f17_counts
            or type(self.price_truth_counts) is not tuple
            or any(
                type(item) is not tuple
                or len(item) != 2
                or type(item[0]) is not str
                or type(item[1]) is not int
                or item[1] < 0
                for item in self.price_truth_counts
            )
            or tuple(item[0] for item in self.price_truth_counts) != expected_truths
            or sum(item[1] for item in self.price_truth_counts) != self.base_f17_counts.population.declared_count
            or type(self.final_truth_counts) is not tuple
            or any(
                type(item) is not tuple
                or len(item) != 2
                or type(item[0]) is not str
                or type(item[1]) is not int
                or item[1] < 0
                for item in self.final_truth_counts
            )
            or tuple(item[0] for item in self.final_truth_counts) != expected_truths
            or sum(item[1] for item in self.final_truth_counts) != self.base_f17_counts.population.declared_count
            or type(self.price_known_count) is not int
            or type(self.price_unknown_count) is not int
            or self.price_known_count < 0
            or self.price_unknown_count < 0
            or self.price_known_count + self.price_unknown_count
            != self.base_f17_counts.population.processed_count
            or type(self.base_visible_count) is not int
            or self.base_visible_count != self.base_composite_counts.visible_count
            or type(self.visible_count) is not int
            or not 0 <= self.visible_count <= self.base_visible_count
        ):
            _fail("counts_invalid")

    @property
    def declared_count(self) -> int:
        return self.base_f17_counts.population.declared_count

    @property
    def processed_count(self) -> int:
        return self.base_f17_counts.population.processed_count

    @property
    def pending_count(self) -> int:
        return self.base_f17_counts.population.pending_count

    @property
    def excluded_count(self) -> int:
        return self.base_f17_counts.population.excluded_count

    def to_dict(self) -> dict[str, object]:
        return {
            "base_f17_counts": self.base_f17_counts.to_dict(),
            "base_composite_counts": self.base_composite_counts.to_dict(),
            "price_truth_counts": {key: value for key, value in self.price_truth_counts},
            "final_truth_counts": {key: value for key, value in self.final_truth_counts},
            "price_known_count": self.price_known_count,
            "price_unknown_count": self.price_unknown_count,
            "base_visible_count": self.base_visible_count,
            "visible_count": self.visible_count,
            "declared_count": self.declared_count,
            "processed_count": self.processed_count,
            "pending_count": self.pending_count,
            "excluded_count": self.excluded_count,
        }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionCompositeSortKeyV2:
    stock_code: str
    sort_values: tuple[c.DailyMarketTechnicalOfficialDispositionSortValueV1, ...]
    fact_row_sha256: str
    price_fact_identity_sha256: str | None
    projection_group_session_identity_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "daily-market-technical-official-disposition-composite-sort-key.v2",
            "stock_code": self.stock_code,
            "sort_values": [item.to_dict() for item in self.sort_values],
            "fact_row_sha256": self.fact_row_sha256,
            "price_fact_identity_sha256": self.price_fact_identity_sha256,
            "projection_group_session_identity_sha256": self.projection_group_session_identity_sha256,
        }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionCompositeResultRowV2:
    query_identity_sha256: str
    base_row: c.DailyMarketTechnicalOfficialDispositionCompositeResultRowV1
    price_fact: DailyMarketTechnicalUniversePriceFactV1 | None
    price_state: c.CompositeTruth
    evaluation: DailyMarketTechnicalOfficialDispositionCompositeEvaluationV2
    row_identity_sha256: str

    def __post_init__(self) -> None:
        _sha(self.query_identity_sha256, "row_query_identity_invalid")
        _sha(self.row_identity_sha256, "row_identity_invalid")
        if (
            type(self.base_row) is not c.DailyMarketTechnicalOfficialDispositionCompositeResultRowV1
            or self.base_row.query_identity_sha256 == ""
            or (
                self.price_fact is not None
                and type(self.price_fact) is not DailyMarketTechnicalUniversePriceFactV1
            )
            or self.price_state not in _TRUTH_ORDER
            or type(self.evaluation) is not DailyMarketTechnicalOfficialDispositionCompositeEvaluationV2
            or self.evaluation.price_truth != self.price_state
            or not self.evaluation.visible
            or (
                self.price_fact is not None
                and self.price_fact.stock_code != self.base_row.stock_code
            )
            or (
                self.price_state == "match"
                and (self.price_fact is None or self.price_fact.status != "known")
            )
            or (
                self.price_state == "unknown"
                and (self.price_fact is None or self.price_fact.status != "unknown")
            )
            or (
                self.price_state == "no_match"
                and (self.price_fact is None or self.price_fact.status != "known")
            )
            or (
                self.price_state == "not_evaluated"
                and self.price_fact is not None
            )
        ):
            _fail("row_invalid")
        if _sha256_json(_row_identity_payload_v2(
            query_identity_sha256=self.query_identity_sha256,
            base_row=self.base_row,
            price_fact=self.price_fact,
            price_state=self.price_state,
            evaluation=self.evaluation,
        )) != self.row_identity_sha256:
            _fail("row_identity_mismatch")

    @property
    def fact_row(self) -> DailyMarketTechnicalOfficialDispositionFactRowV1:
        return self.base_row.fact_row

    @property
    def technical_row(self) -> DailyMarketTechnicalParentV4Row | None:
        return self.base_row.technical_row

    @property
    def ma_entry(self) -> DailyMarketTechnicalMaAlignmentCompactEntryV1 | None:
        return self.base_row.ma_entry

    @property
    def kdj_entry(self) -> DailyMarketTechnicalUniverseKDJCompactEntryV1 | None:
        return self.base_row.kdj_entry

    @property
    def volatility_entry(self) -> DailyMarketTechnicalUniverseVolatilityCompactEntryV1 | None:
        return self.base_row.volatility_entry

    @property
    def filter_evaluation(self) -> DailyMarketTechnicalOfficialDispositionFilterEvaluationV1:
        return self.base_row.filter_evaluation

    @property
    def stock_code(self) -> str:
        return self.base_row.stock_code

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_ROW_V2_SCHEMA,
            "query_identity_sha256": self.query_identity_sha256,
            "stock_code": self.stock_code,
            "base_row": self.base_row.to_dict(),
            "price_fact": None if self.price_fact is None else self.price_fact.to_dict(),
            "price_state": self.price_state,
            "evaluation": self.evaluation.to_dict(),
            "row_identity_sha256": self.row_identity_sha256,
            "scope": "current_only",
            "official_available_at": None,
            "availability_status": "unknown",
            "historical_pit_eligible": False,
        }


def _row_identity_payload_v2(
    *,
    query_identity_sha256: str,
    base_row: c.DailyMarketTechnicalOfficialDispositionCompositeResultRowV1,
    price_fact: DailyMarketTechnicalUniversePriceFactV1 | None,
    price_state: c.CompositeTruth,
    evaluation: DailyMarketTechnicalOfficialDispositionCompositeEvaluationV2,
) -> dict[str, object]:
    return {
        "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_ROW_V2_SCHEMA,
        "query_identity_sha256": query_identity_sha256,
        "base_row_identity_sha256": base_row.row_identity_sha256,
        "price_fact_identity_sha256": None if price_fact is None else price_fact.identity_sha256,
        "price_state": price_state,
        "evaluation": evaluation.to_dict(),
        "scope": "current_only",
        "official_available_at": None,
        "availability_status": "unknown",
        "historical_pit_eligible": False,
    }


def _source_pins_v2(
    query: DailyMarketTechnicalOfficialDispositionCompositeQueryV2,
    session: DailyMarketTechnicalUniverseProjectionGroupSessionV3,
) -> tuple[tuple[str, str], ...]:
    anchor = session._require_active()
    base = anchor.base_query
    prepared = anchor.prepared
    facts = session.price_facts
    digest, _size = digest_daily_market_technical_universe_price_facts_v1(facts)
    if digest != session.price_index_identity_sha256:
        _fail("price_index_digest_mismatch")
    pins = {
        "bundle_output_root": anchor.bundle_reference.output_root,
        "bundle_identity_sha256": anchor.bundle_reference.bundle_identity_sha256,
        "bundle_manifest_sha256": anchor.bundle_reference.manifest_sha256,
        "p01_read_session_identity_sha256": anchor.p01_session.read_session_identity_sha256,
        "p01_selection_identity_sha256": anchor.selection.selection_identity_sha256,
        "p01_query_spec_identity_sha256": anchor.selection.query_spec_identity_sha256,
        "p01_generation_identity_sha256": base.generation_identity_sha256,
        "p01_plan_identity_sha256": base.plan_identity_sha256,
        "p01_plan_sha256": base.plan_sha256,
        "p01_receipt_identity_sha256": base.receipt_identity_sha256,
        "p01_receipt_sha256": base.receipt_sha256,
        "p01_cohort_identity_sha256": base.cohort_identity_sha256,
        "p01_source_clock_identity_sha256": base.source_clock_identity_sha256,
        "p01_method_contracts_sha256": base.method_contracts_sha256,
        "ma_index_identity_sha256": session.ma_index.index_identity_sha256,
        "ma_source_request_identity_sha256": prepared.ma.request.request_identity_sha256,
        "kdj_body_identity_sha256": prepared.kdj.body_identity_sha256,
        "volatility_body_identity_sha256": prepared.volatility.body_identity_sha256,
        "price_index_identity_sha256": session.price_index_identity_sha256,
        "market_assignment_pin_identity_sha256": query.f17_query.market_assignment_pin_identity_sha256,
        "official_disposal_pin_identity_sha256": query.f17_query.official_disposal_pin_identity_sha256,
        "decision_date": query.f17_query.decision_date.isoformat(),
        "decision_cutoff": query.f17_query.decision_cutoff.isoformat(),
        "projection_group_session_identity_sha256": session.identity_sha256,
        "price_method_version": DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_METHOD_VERSION,
    }
    if any(type(value) is not str or not value for value in pins.values()):
        _fail("source_pins_invalid")
    return tuple((key, value) for key, value in pins.items())


def _result_body_v2(
    *,
    query: DailyMarketTechnicalOfficialDispositionCompositeQueryV2,
    counts: DailyMarketTechnicalOfficialDispositionCompositeQueryV2Counts,
    source_pins: tuple[tuple[str, str], ...],
    ordered_keys: tuple[DailyMarketTechnicalOfficialDispositionCompositeSortKeyV2, ...],
    result_status: Literal["complete", "partial"],
    coverage_status: Literal["complete", "partial"],
) -> dict[str, object]:
    return {
        "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_RESULT_V2_SCHEMA,
        "verification_status": "reader_verified",
        "query_json": query.to_json(),
        "query_identity_sha256": query.query_identity_sha256,
        "projection_group_session_identity_sha256": query.projection_group_session_identity_sha256,
        "counts": counts.to_dict(),
        "source_pins": [[key, value] for key, value in source_pins],
        "ordered_stock_codes": [item.stock_code for item in ordered_keys],
        "ordered_keys_sha256": _sha256_json([item.to_dict() for item in ordered_keys]),
        "result_status": result_status,
        "official_source_coverage_status": coverage_status,
        "scope": "current_only",
        "official_available_at": None,
        "availability_status": "unknown",
        "historical_pit_eligible": False,
    }


def _result_anchor_identity_v2(
    *,
    query: DailyMarketTechnicalOfficialDispositionCompositeQueryV2,
    operation_identity_sha256: str,
    counts: DailyMarketTechnicalOfficialDispositionCompositeQueryV2Counts,
    source_pins: tuple[tuple[str, str], ...],
    ordered_keys: tuple[DailyMarketTechnicalOfficialDispositionCompositeSortKeyV2, ...],
    result_status: Literal["complete", "partial"],
    coverage_status: Literal["complete", "partial"],
    projection_group_session: DailyMarketTechnicalUniverseProjectionGroupSessionV3,
    scope: Literal["current_only"],
    official_available_at: None,
    availability_status: Literal["unknown"],
    historical_pit_eligible: Literal[False],
) -> str:
    """固定 result 發行時的計數、排序、狀態與來源錨點。"""
    return _sha256_json({
        "schema_version": "daily-market-technical-official-disposition-composite-result-issuer-anchor.v2",
        "query_json": query.to_json(),
        "operation_identity_sha256": operation_identity_sha256,
        "counts": counts.to_dict(),
        "source_pins": [[key, value] for key, value in source_pins],
        "ordered_keys": [item.to_dict() for item in ordered_keys],
        "result_status": result_status,
        "official_source_coverage_status": coverage_status,
        "projection_group_session_identity_sha256": projection_group_session.identity_sha256,
        "scope": scope,
        "official_available_at": official_available_at,
        "availability_status": availability_status,
        "historical_pit_eligible": historical_pit_eligible,
    })


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2:
    query: DailyMarketTechnicalOfficialDispositionCompositeQueryV2
    operation_identity_sha256: str
    counts: DailyMarketTechnicalOfficialDispositionCompositeQueryV2Counts
    source_pins: tuple[tuple[str, str], ...]
    _ordered_sort_keys: tuple[DailyMarketTechnicalOfficialDispositionCompositeSortKeyV2, ...] = field(repr=False, compare=False)
    result_status: Literal["complete", "partial"]
    official_source_coverage_status: Literal["complete", "partial"]
    _projection_group_session: DailyMarketTechnicalUniverseProjectionGroupSessionV3 = field(repr=False, compare=False)
    _seal: _ReaderIssuedIdentityAnchorV2 = field(repr=False, compare=False)
    scope: Literal["current_only"] = "current_only"
    official_available_at: None = None
    availability_status: Literal["unknown"] = "unknown"
    historical_pit_eligible: Literal[False] = False

    def __post_init__(self) -> None:
        if (
            type(self._seal) is not _ReaderIssuedIdentityAnchorV2
            or self._seal.subject is not self._projection_group_session
            or type(self.query) is not DailyMarketTechnicalOfficialDispositionCompositeQueryV2
            or type(self.counts) is not DailyMarketTechnicalOfficialDispositionCompositeQueryV2Counts
            or type(self._projection_group_session) is not DailyMarketTechnicalUniverseProjectionGroupSessionV3
            or self._projection_group_session.identity_sha256
            != self.query.projection_group_session_identity_sha256
            or self.source_pins != _source_pins_v2(self.query, self._projection_group_session)
            or len(self._ordered_sort_keys) != self.counts.visible_count
            or len({item.stock_code for item in self._ordered_sort_keys}) != len(self._ordered_sort_keys)
            or self.result_status not in {"complete", "partial"}
            or self.official_source_coverage_status not in {"complete", "partial"}
            or self.scope != "current_only"
            or self.official_available_at is not None
            or self.availability_status != "unknown"
            or self.historical_pit_eligible is not False
        ):
            _fail("result_not_reader_issued")
        expected = _sha256_json(_result_body_v2(
            query=self.query,
            counts=self.counts,
            source_pins=self.source_pins,
            ordered_keys=self._ordered_sort_keys,
            result_status=self.result_status,
            coverage_status=self.official_source_coverage_status,
        ))
        if expected != self.operation_identity_sha256:
            _fail("result_identity_mismatch")
        expected_anchor = _result_anchor_identity_v2(
            query=self.query,
            operation_identity_sha256=self.operation_identity_sha256,
            counts=self.counts,
            source_pins=self.source_pins,
            ordered_keys=self._ordered_sort_keys,
            result_status=self.result_status,
            coverage_status=self.official_source_coverage_status,
            projection_group_session=self._projection_group_session,
            scope=self.scope,
            official_available_at=self.official_available_at,
            availability_status=self.availability_status,
            historical_pit_eligible=self.historical_pit_eligible,
        )
        if self._seal.identity_sha256 != expected_anchor:
            _fail("result_reader_anchor_mismatch")

    @property
    def visible_count(self) -> int:
        return self.counts.visible_count

    @property
    def ordered_stock_codes(self) -> tuple[str, ...]:
        return tuple(item.stock_code for item in self._ordered_sort_keys)

    def to_dict(self) -> dict[str, object]:
        body = _result_body_v2(
            query=self.query,
            counts=self.counts,
            source_pins=self.source_pins,
            ordered_keys=self._ordered_sort_keys,
            result_status=self.result_status,
            coverage_status=self.official_source_coverage_status,
        )
        body["operation_identity_sha256"] = self.operation_identity_sha256
        body["visible_count"] = self.visible_count
        return body

    def to_json(self) -> str:
        encoded = _canonical_json_bytes(self.to_dict())
        if len(encoded) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_RESULT_BYTES:
            _fail("result_byte_limit")
        return encoded.decode("utf-8")

    @classmethod
    def from_json(
        cls,
        raw: bytes | str,
        *,
        projection_group_session: DailyMarketTechnicalUniverseProjectionGroupSessionV3,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2:
        payload, text = _parse_json(
            raw,
            maximum_bytes=DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_RESULT_BYTES,
        )
        if (
            not isinstance(payload, Mapping)
            or payload.get("schema_version") != DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_RESULT_V2_SCHEMA
            or payload.get("verification_status") != "reader_verified"
            or payload.get("scope") != "current_only"
            or payload.get("official_available_at") is not None
            or payload.get("availability_status") != "unknown"
            or payload.get("historical_pit_eligible") is not False
        ):
            _fail("result_payload_invalid")
        query_text = payload.get("query_json")
        if type(query_text) is not str:
            _fail("result_query_invalid")
        query = DailyMarketTechnicalOfficialDispositionCompositeQueryV2.from_json(query_text)
        if type(projection_group_session) is not DailyMarketTechnicalUniverseProjectionGroupSessionV3:
            _fail("result_group_session_invalid")
        result = execute_composite_query_v2(
            query,
            projection_group_session,
            cancel_callback=cancel_callback,
        )
        if result.to_json() != text:
            _fail("result_roundtrip_mismatch")
        return result

    def read_page(
        self,
        page_index: int,
        page_size: int,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2:
        return _materialize_page_v2(
            self,
            page_index=page_index,
            page_size=page_size,
            cancel_callback=cancel_callback,
        )


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2:
    query: DailyMarketTechnicalOfficialDispositionCompositeQueryV2
    request_identity_sha256: str
    operation_identity_sha256: str
    page_identity_sha256: str
    page_index: int
    page_size: int
    page_count: int
    counts: DailyMarketTechnicalOfficialDispositionCompositeQueryV2Counts
    rows: tuple[DailyMarketTechnicalOfficialDispositionCompositeResultRowV2, ...]
    source_pins: tuple[tuple[str, str], ...]
    result_status: Literal["complete", "partial"]
    official_source_coverage_status: Literal["complete", "partial"]
    _result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2 = field(repr=False, compare=False)
    _seal: _ReaderIssuedIdentityAnchorV2 = field(repr=False, compare=False)
    scope: Literal["current_only"] = "current_only"
    official_available_at: None = None
    availability_status: Literal["unknown"] = "unknown"
    historical_pit_eligible: Literal[False] = False

    def __post_init__(self) -> None:
        _validate_page(self.page_index, self.page_size)
        if (
            type(self._seal) is not _ReaderIssuedIdentityAnchorV2
            or self._seal.subject is not self._result
            or type(self._result) is not DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2
            or self.query is not self._result.query
            or self.operation_identity_sha256 != self._result.operation_identity_sha256
            or self.counts != self._result.counts
            or self.source_pins != self._result.source_pins
            or self.result_status != self._result.result_status
            or self.official_source_coverage_status
            != self._result.official_source_coverage_status
            or self.page_count
            != (self.counts.visible_count + self.page_size - 1) // self.page_size
            or len(self.rows) > self.page_size
            or any(not item.evaluation.visible for item in self.rows)
            or self.scope != "current_only"
            or self.official_available_at is not None
            or self.availability_status != "unknown"
            or self.historical_pit_eligible is not False
        ):
            _fail("page_not_reader_issued")
        request_identity = _page_request_identity_v2(
            self.query, self.page_index, self.page_size,
        )
        start = self.page_index * self.page_size
        expected_codes = tuple(
            item.stock_code
            for item in self._result._ordered_sort_keys[start:start + self.page_size]
        )
        if (
            self.request_identity_sha256 != request_identity
            or tuple(item.stock_code for item in self.rows) != expected_codes
            or self.page_identity_sha256 != _page_identity_v2(
                result=self._result,
                request_identity_sha256=request_identity,
                page_index=self.page_index,
                page_size=self.page_size,
                rows=self.rows,
            )
        ):
            _fail("page_identity_mismatch")
        expected_anchor = _page_anchor_identity_v2(
            result=self._result,
            request_identity_sha256=self.request_identity_sha256,
            operation_identity_sha256=self.operation_identity_sha256,
            page_identity_sha256=self.page_identity_sha256,
            page_index=self.page_index,
            page_size=self.page_size,
            page_count=self.page_count,
            counts=self.counts,
            rows=self.rows,
            source_pins=self.source_pins,
            result_status=self.result_status,
            coverage_status=self.official_source_coverage_status,
            scope=self.scope,
            official_available_at=self.official_available_at,
            availability_status=self.availability_status,
            historical_pit_eligible=self.historical_pit_eligible,
        )
        if self._seal.identity_sha256 != expected_anchor:
            _fail("page_reader_anchor_mismatch")

    @property
    def visible_count(self) -> int:
        return self.counts.visible_count

    def to_dict(self) -> dict[str, object]:
        body = {
            "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_PAGE_V2_SCHEMA,
            "query_json": self.query.to_json(),
            "query_identity_sha256": self.query.query_identity_sha256,
            "request_identity_sha256": self.request_identity_sha256,
            "operation_identity_sha256": self.operation_identity_sha256,
            "page_identity_sha256": self.page_identity_sha256,
            "page_index": self.page_index,
            "page_size": self.page_size,
            "page_count": self.page_count,
            "visible_count": self.visible_count,
            "counts": self.counts.to_dict(),
            "rows": [item.to_dict() for item in self.rows],
            "source_pins": [[key, value] for key, value in self.source_pins],
            "result_status": self.result_status,
            "official_source_coverage_status": self.official_source_coverage_status,
            "scope": "current_only",
            "official_available_at": None,
            "availability_status": "unknown",
            "historical_pit_eligible": False,
        }
        return body

    def to_json(self) -> str:
        encoded = _canonical_json_bytes(self.to_dict())
        if len(encoded) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_PAGE_BYTES:
            _fail("page_byte_limit")
        return encoded.decode("utf-8")

    @classmethod
    def from_json(
        cls,
        raw: bytes | str,
        *,
        result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2:
        payload, text = _parse_json(
            raw,
            maximum_bytes=DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_PAGE_BYTES,
        )
        if (
            not isinstance(payload, Mapping)
            or payload.get("schema_version") != DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_PAGE_V2_SCHEMA
            or type(payload.get("page_index")) is not int
            or type(payload.get("page_size")) is not int
        ):
            _fail("page_payload_invalid")
        page = result.read_page(
            cast(int, payload["page_index"]),
            cast(int, payload["page_size"]),
            cancel_callback=cancel_callback,
        )
        if page.to_json() != text:
            _fail("page_roundtrip_mismatch")
        return page


def _page_request_identity_v2(
    query: DailyMarketTechnicalOfficialDispositionCompositeQueryV2,
    page_index: int,
    page_size: int,
) -> str:
    return _sha256_json({
        "schema_version": "daily-market-technical-official-disposition-composite-page-request.v2",
        "query_identity_sha256": query.query_identity_sha256,
        "page_index": page_index,
        "page_size": page_size,
    })


def _page_identity_v2(
    *,
    result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2,
    request_identity_sha256: str,
    page_index: int,
    page_size: int,
    rows: tuple[DailyMarketTechnicalOfficialDispositionCompositeResultRowV2, ...],
) -> str:
    return _sha256_json({
        "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_PAGE_V2_SCHEMA,
        "query_identity_sha256": result.query.query_identity_sha256,
        "operation_identity_sha256": result.operation_identity_sha256,
        "request_identity_sha256": request_identity_sha256,
        "page_index": page_index,
        "page_size": page_size,
        "rows": [item.to_dict() for item in rows],
        "source_pins": [[key, value] for key, value in result.source_pins],
        "counts": result.counts.to_dict(),
        "result_status": result.result_status,
        "official_source_coverage_status": result.official_source_coverage_status,
        "scope": "current_only",
        "official_available_at": None,
        "availability_status": "unknown",
        "historical_pit_eligible": False,
    })


def _page_anchor_identity_v2(
    *,
    result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2,
    request_identity_sha256: str,
    operation_identity_sha256: str,
    page_identity_sha256: str,
    page_index: int,
    page_size: int,
    page_count: int,
    counts: DailyMarketTechnicalOfficialDispositionCompositeQueryV2Counts,
    rows: tuple[DailyMarketTechnicalOfficialDispositionCompositeResultRowV2, ...],
    source_pins: tuple[tuple[str, str], ...],
    result_status: Literal["complete", "partial"],
    coverage_status: Literal["complete", "partial"],
    scope: Literal["current_only"],
    official_available_at: None,
    availability_status: Literal["unknown"],
    historical_pit_eligible: Literal[False],
) -> str:
    """固定 page 發行時的原 result、完整列內容、分頁與狀態。"""
    return _sha256_json({
        "schema_version": "daily-market-technical-official-disposition-composite-page-issuer-anchor.v2",
        "query_json": result.query.to_json(),
        "query_identity_sha256": result.query.query_identity_sha256,
        "result_issuer_anchor_sha256": result._seal.identity_sha256,
        "request_identity_sha256": request_identity_sha256,
        "operation_identity_sha256": operation_identity_sha256,
        "page_identity_sha256": page_identity_sha256,
        "page_index": page_index,
        "page_size": page_size,
        "page_count": page_count,
        "counts": counts.to_dict(),
        "rows": [item.to_dict() for item in rows],
        "source_pins": [[key, value] for key, value in source_pins],
        "result_status": result_status,
        "official_source_coverage_status": coverage_status,
        "scope": scope,
        "official_available_at": official_available_at,
        "availability_status": availability_status,
        "historical_pit_eligible": historical_pit_eligible,
    })


def _validate_page(page_index: object, page_size: object) -> None:
    if (
        type(page_index) is not int
        or page_index < 0
        or page_index > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_PAGE_INDEX
        or type(page_size) is not int
        or not 1 <= page_size <= DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_PAGE_SIZE
    ):
        _fail("page_request_invalid")


def _selection_rows(
    anchor: Any,
    cancel_callback: Callable[[], object] | None,
) -> Sequence[DailyMarketTechnicalParentV4Row]:
    selection = anchor.selection
    session = anchor.p01_session
    codes = selection.stock_codes
    if selection.matching_count != len(codes):
        _fail("selection_count_invalid")
    page_count = (len(codes) + DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_PAGE_SIZE - 1) // DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_PAGE_SIZE
    rows: list[DailyMarketTechnicalParentV4Row] = []
    for page_index in range(page_count):
        r._check_cancel(cancel_callback)
        page = session.read_selection_page(
            selection,
            page_index=page_index,
            page_size=DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_PAGE_SIZE,
            cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
        )
        if (
            type(page) is not DailyMarketTechnicalUniverseV4ReadSelectionPage
            or page.selection_identity_sha256 != selection.selection_identity_sha256
            or page.page_index != page_index
            or page.page_size != DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_PAGE_SIZE
            or page.matching_count != len(codes)
            or page.page_count != page_count
            or tuple(row.stock_code for row in page.rows)
            != codes[
                page_index * DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_PAGE_SIZE:
                (page_index + 1) * DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_PAGE_SIZE
            ]
        ):
            _fail("selection_page_identity_mismatch")
        rows.extend(page.rows)
    if tuple(row.stock_code for row in rows) != codes:
        _fail("selection_rows_order_invalid")
    return tuple(rows)


def _price_truth(
    fact: DailyMarketTechnicalUniversePriceFactV1 | None,
    query: DailyMarketTechnicalOfficialDispositionCompositeQueryV2,
    technical_status: str,
) -> c.CompositeTruth:
    if not query.active_price_filter:
        return "not_applicable"
    status = c._validate_row_status(technical_status)
    if status in {"pending", "excluded"}:
        return "not_evaluated"
    if fact is None or fact.status == "unknown":
        return "unknown"
    if fact.close_price is None or not fact.close_price.is_finite():
        _fail("known_price_fact_invalid")
    value = fact.close_price
    minimum = query.min_close_price
    if minimum is not None and (
        value < minimum
        or (value == minimum and not query.min_inclusive)
    ):
        return "no_match"
    maximum = query.max_close_price
    if maximum is not None and (
        value > maximum
        or (value == maximum and not query.max_inclusive)
    ):
        return "no_match"
    return "match"


def _final_evaluation(
    base: c.DailyMarketTechnicalOfficialDispositionCompositeEvaluationV1,
    *,
    price_truth: c.CompositeTruth,
    technical_status: str,
    hard_eligible: bool,
    query: DailyMarketTechnicalOfficialDispositionCompositeQueryV2,
) -> DailyMarketTechnicalOfficialDispositionCompositeEvaluationV2:
    base_active = base.active_groups
    price_active = query.active_price_filter
    active = (*base_active, price_active)
    status = c._validate_row_status(technical_status)
    if not price_active:
        price_gate_passes = True
        combined = base.composite_truth
    elif price_truth == "match":
        price_gate_passes = query.unknown_price_policy != "only"
        combined = (
            "not_evaluated"
            if status in {"pending", "excluded"} and hard_eligible
            else (
                price_truth
                if base.composite_truth == "not_applicable"
                else base.composite_truth
            )
        )
    elif price_truth == "no_match":
        price_gate_passes = False
        combined = "no_match"
    elif price_truth == "unknown":
        price_gate_passes = query.unknown_price_policy in {"include", "only"}
        if status in {"pending", "excluded"} and hard_eligible:
            combined = "not_evaluated"
        elif base.composite_truth == "not_applicable":
            combined = "unknown"
        elif base.composite_truth == "no_match":
            combined = "no_match"
        elif base.composite_truth in {"unknown", "not_evaluated"}:
            combined = base.composite_truth
        else:
            combined = "unknown"
    else:
        price_gate_passes = False
        combined = "not_evaluated"
    audit_visible = base.audit_visible and not price_active
    visible = hard_eligible and base.visible and price_gate_passes
    included = base.included_by_unknown_policy and price_gate_passes
    matched = (
        base.predicate_match
        if not price_active
        else price_truth == "match"
        and (base.predicate_match or not any(base_active))
    )
    return DailyMarketTechnicalOfficialDispositionCompositeEvaluationV2(
        technical_truth=base.technical_truth,
        ma_truth=base.ma_truth,
        kdj_truth=base.kdj_truth,
        volatility_truth=base.volatility_truth,
        price_truth=price_truth,
        composite_truth=combined,
        active_groups=active,
        hard_eligible=hard_eligible,
        audit_visible=audit_visible,
        included_by_unknown_policy=included,
        predicate_match=matched,
        visible=visible,
    )


def _evaluate_row(
    *,
    f17_query: Any,
    context: c.DailyMarketTechnicalOfficialDispositionCompositeEvaluationContextV1,
    fact: DailyMarketTechnicalOfficialDispositionFactRowV1,
    parent: DailyMarketTechnicalParentV4Row | None,
    ma: DailyMarketTechnicalMaAlignmentCompactEntryV1 | None,
    kd: DailyMarketTechnicalUniverseKDJCompactEntryV1 | None,
    vol: DailyMarketTechnicalUniverseVolatilityCompactEntryV1 | None,
    price: DailyMarketTechnicalUniversePriceFactV1 | None,
    query: DailyMarketTechnicalOfficialDispositionCompositeQueryV2,
) -> tuple[
    DailyMarketTechnicalOfficialDispositionFilterEvaluationV1,
    c.DailyMarketTechnicalOfficialDispositionCompositeEvaluationV1,
    DailyMarketTechnicalOfficialDispositionCompositeEvaluationV2,
    bool,
    c.CompositeTruth,
    bool,
]:
    outer = r.evaluate_f17_membership_v1(f17_query, fact)
    base_match, base_truth, stock_match = r._technical_filter_evaluation(
        f17_query, fact, parent,
    )
    hard = outer.filter_membership and stock_match
    status = c._fact_technical_status(fact)
    technical_truth = c.evaluate_technical_group_v1(
        context, fact, parent, technical_status=status, hard_eligible=hard,
    )
    ma_truth = c.evaluate_ma_group_v1(
        context, fact, parent, ma, technical_status=status, hard_eligible=hard,
    )
    kd_truth = c.evaluate_kdj_group_v1(
        context, fact, parent, kd, technical_status=status, hard_eligible=hard,
    )
    vol_truth = c.evaluate_volatility_group_v1(
        context, fact, parent, vol, technical_status=status, hard_eligible=hard,
    )
    base_evaluation = c.evaluate_composite_predicate_v1(
        context,
        technical_truth=technical_truth,
        ma_truth=ma_truth,
        kdj_truth=kd_truth,
        volatility_truth=vol_truth,
        technical_status=status,
        hard_eligible=hard,
    )
    p_truth = _price_truth(price, query, status)
    evaluation = _final_evaluation(
        base_evaluation,
        price_truth=p_truth,
        technical_status=status,
        hard_eligible=hard,
        query=query,
    )
    return outer, base_evaluation, evaluation, base_match, cast(c.CompositeTruth, base_truth), stock_match


def _sort_values_v2(
    query: DailyMarketTechnicalOfficialDispositionCompositeQueryV2,
    context: c.DailyMarketTechnicalOfficialDispositionCompositeEvaluationContextV1,
    fact: DailyMarketTechnicalOfficialDispositionFactRowV1,
    parent: DailyMarketTechnicalParentV4Row | None,
    ma: DailyMarketTechnicalMaAlignmentCompactEntryV1 | None,
    kd: DailyMarketTechnicalUniverseKDJCompactEntryV1 | None,
    vol: DailyMarketTechnicalUniverseVolatilityCompactEntryV1 | None,
    price: DailyMarketTechnicalUniversePriceFactV1 | None,
    group: DailyMarketTechnicalUniverseProjectionGroupSessionV3,
) -> tuple[c.DailyMarketTechnicalOfficialDispositionSortValueV1, ...]:
    group._require_active()
    status = c._fact_technical_status(fact)
    if status == "processed":
        if (
            _entry_for_code(group.ma_index.entries, fact.stock_code) is not ma
            or _entry_for_code(group.kdj_entries, fact.stock_code) is not kd
            or _entry_for_code(group.volatility_entries, fact.stock_code) is not vol
            or group.price_fact_for_code(fact.stock_code) is not price
        ):
            _fail("sort_group_entry_not_original")
    elif any(item is not None for item in (parent, ma, kd, vol, price)):
        _fail("sort_nonprocessed_projection_present")
    f17_key = c.project_daily_market_technical_official_disposition_sort_key_v1(
        context.f17_sort_query,
        c.DailyMarketTechnicalOfficialDispositionJoinedRowV1(fact, parent),
    )
    base_values = {item.field: item.value for item in f17_key.sort_values}
    result: list[c.DailyMarketTechnicalOfficialDispositionSortValueV1] = []
    for clause in query.sort_clauses:
        if clause.field in base_values:
            value = base_values[clause.field]
        elif clause.field == "price.close_price":
            value = (
                price.close_price
                if price is not None and price.status == "known"
                else None
            )
        elif clause.field == "ma_alignment_state":
            value = (
                ma.ma_state if ma is not None and ma.ma_state != "unknown" else None
            )
        elif clause.field == "kdj_state":
            value = kd.state if kd is not None and kd.state != "unknown" else None
        elif clause.field.startswith("kdj_previous.") or clause.field.startswith("kdj_current."):
            day = None
            if kd is not None:
                day = kd.previous if clause.field.startswith("kdj_previous.") else kd.current
            suffix = clause.field.split(".", 1)[1]
            value = None if day is None else getattr(day, suffix)
        elif clause.field == "bollinger_bandwidth_pct":
            value = None if vol is None else vol.evidence.bandwidth.value
        elif clause.field == "atr14_pct":
            value = None if vol is None else vol.evidence.atr14_sma.normalized_value
        else:
            _fail("sort_value_missing")
        c._validate_composite_sort_scalar_v1(
            query.f17_query, clause.field, cast(Any, value),
        ) if clause.field != "price.close_price" else None
        if value is not None and (
            type(value) not in _SORT_VALUE_TYPES
            or (type(value) is Decimal and not value.is_finite())
        ):
            _fail("sort_value_invalid")
        result.append(c.DailyMarketTechnicalOfficialDispositionSortValueV1(
            field=clause.field,
            direction=cast(c.CompositeSortDirection, clause.direction),
            value=cast(Any, value),
        ))
    return tuple(result)


def _sort_key_v2(
    query: DailyMarketTechnicalOfficialDispositionCompositeQueryV2,
    values: tuple[c.DailyMarketTechnicalOfficialDispositionSortValueV1, ...],
    fact: DailyMarketTechnicalOfficialDispositionFactRowV1,
    price: DailyMarketTechnicalUniversePriceFactV1 | None,
) -> DailyMarketTechnicalOfficialDispositionCompositeSortKeyV2:
    return DailyMarketTechnicalOfficialDispositionCompositeSortKeyV2(
        stock_code=fact.stock_code,
        sort_values=values,
        fact_row_sha256=hashlib.sha256(fact.body_json.encode("utf-8")).hexdigest(),
        price_fact_identity_sha256=None if price is None else price.identity_sha256,
        projection_group_session_identity_sha256=(
            query.projection_group_session_identity_sha256
        ),
    )


def _sort_keys_v2(
    query: DailyMarketTechnicalOfficialDispositionCompositeQueryV2,
    keys: Sequence[DailyMarketTechnicalOfficialDispositionCompositeSortKeyV2],
    cancel_callback: Callable[[], object] | None,
) -> tuple[DailyMarketTechnicalOfficialDispositionCompositeSortKeyV2, ...]:
    if len(keys) > c.DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_ROWS:
        _fail("sort_row_limit")
    expected = tuple((item.field, item.direction) for item in query.sort_clauses)
    result = list(keys)
    seen: set[str] = set()
    for item in result:
        r._check_cancel(cancel_callback)
        if (
            type(item) is not DailyMarketTechnicalOfficialDispositionCompositeSortKeyV2
            or item.stock_code in seen
            or tuple((value.field, value.direction) for value in item.sort_values) != expected
            or item.projection_group_session_identity_sha256
            != query.projection_group_session_identity_sha256
        ):
            _fail("sort_key_mismatch")
        seen.add(item.stock_code)
    result.sort(key=lambda item: item.stock_code)
    for index in range(len(query.sort_clauses) - 1, -1, -1):
        r._check_cancel(cancel_callback)
        clause = query.sort_clauses[index]
        known: list[DailyMarketTechnicalOfficialDispositionCompositeSortKeyV2] = []
        unknown: list[DailyMarketTechnicalOfficialDispositionCompositeSortKeyV2] = []
        for item in result:
            value = item.sort_values[index].value
            (unknown if value is None else known).append(item)
        known.sort(
            key=lambda item: cast(Any, item.sort_values[index].value),
            reverse=clause.direction == "desc",
        )
        result = known + unknown
    r._check_cancel(cancel_callback)
    return tuple(result)


def execute_composite_query_v2(
    query: DailyMarketTechnicalOfficialDispositionCompositeQueryV2,
    projection_group_session: DailyMarketTechnicalUniverseProjectionGroupSessionV3,
    *,
    cancel_callback: Callable[[], object] | None = None,
) -> DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2:
    """只消費 caller 已開啟的 V3 session；全母體過濾與排序後才發行結果。"""
    r._validate_cancel_callback(cancel_callback)
    r._check_cancel(cancel_callback)
    if (
        type(query) is not DailyMarketTechnicalOfficialDispositionCompositeQueryV2
        or type(projection_group_session) is not DailyMarketTechnicalUniverseProjectionGroupSessionV3
    ):
        _fail("executor_inputs_invalid")
    query.to_json()
    try:
        anchor = projection_group_session._require_active()
    except Exception as exc:
        raise DailyMarketTechnicalOfficialDispositionCompositeQueryV2Error(
            "projection_group_session_not_active"
        ) from exc
    if (
        projection_group_session.identity_sha256
        != query.projection_group_session_identity_sha256
        or anchor.outer_query.query_identity_sha256
        != query.f17_query.query_identity_sha256
        or anchor.outer_query.to_json() != query.f17_query.to_json()
        or anchor.bundle_state.reference != anchor.bundle_reference
    ):
        _fail("projection_group_session_binding_mismatch")
    source_pins = _source_pins_v2(query, projection_group_session)
    context = c.prepare_composite_evaluation_context_v1(query.base_query)
    group = projection_group_session
    ma_entries = group.ma_index.entries
    kd_entries = group.kdj_entries
    vol_entries = group.volatility_entries
    price_facts = group.price_facts
    expected = anchor.p01_session.source_counts
    if not (
        len(ma_entries) == len(kd_entries) == len(vol_entries)
        == len(price_facts) == expected.processed_count
    ):
        _fail("projection_population_mismatch")
    parent_rows = iter(_selection_rows(anchor, cancel_callback))
    parent = next(parent_rows, None)
    position = 0
    last_code: str | None = None
    base_counts = r._CountsBuilder(query.f17_query, expected)
    truths = {
        name: dict.fromkeys(_TRUTH_ORDER, 0)
        for name in ("technical", "ma", "kdj", "volatility", "composite", "eligible", "evaluable")
    }
    ma_states = dict.fromkeys(_STATE_ORDER, 0)
    kd_states = dict.fromkeys(_STATE_ORDER, 0)
    bandwidth = dict.fromkeys(("observed", "unknown"), 0)
    atr = dict.fromkeys(("observed", "unknown"), 0)
    price_truths = dict.fromkeys(_TRUTH_ORDER, 0)
    final_truths = dict.fromkeys(_TRUTH_ORDER, 0)
    price_known = price_unknown = 0
    hard_count = active_evaluable = audit_count = unknown_included = unknown_excluded = 0
    base_visible_count = 0
    sort_keys: list[DailyMarketTechnicalOfficialDispositionCompositeSortKeyV2] = []
    price_by_code = {fact.stock_code: fact for fact in price_facts}
    for fact in anchor.bundle_state.iter_verified_rows(
        cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
    ):
        r._check_cancel(cancel_callback)
        if last_code is not None and fact.stock_code <= last_code:
            _fail("bundle_order_invalid")
        last_code = fact.stock_code
        status = c._fact_technical_status(fact)
        current_parent = ma = kd = vol = price = None
        if status == "processed":
            if (
                parent is None
                or parent.stock_code != fact.stock_code
                or position >= len(ma_entries)
                or position >= len(anchor.selection.stock_codes)
                or anchor.selection.stock_codes[position] != fact.stock_code
            ):
                _fail("processed_join_mismatch")
            current_parent = parent
            parent = next(parent_rows, None)
            ma, kd, vol = ma_entries[position], kd_entries[position], vol_entries[position]
            price = price_by_code.get(fact.stock_code)
            if (
                price is None
                or any(entry.stock_code != fact.stock_code for entry in (ma, kd, vol))
                or price.snapshot_identity_sha256 != current_parent.snapshot_identity_sha256
                or price.source_identity != current_parent.source_identity
                or price.observation_date != current_parent.latest_feature_date
            ):
                _fail("projection_join_mismatch")
            position += 1
            ma_states[ma.ma_state] += 1
            kd_states[kd.state] += 1
            bandwidth["observed" if vol.evidence.bandwidth.value is not None else "unknown"] += 1
            atr["observed" if vol.evidence.atr14_sma.normalized_value is not None else "unknown"] += 1
            if price.status == "known":
                price_known += 1
            else:
                price_unknown += 1
        elif parent is not None and parent.stock_code <= fact.stock_code:
            _fail("unexpected_parent_row")
        outer, base_evaluation, evaluation, base_match, base_truth, stock_match = _evaluate_row(
            f17_query=query.f17_query,
            context=context,
            fact=fact,
            parent=current_parent,
            ma=ma,
            kd=kd,
            vol=vol,
            price=price,
            query=query,
        )
        price_truths[evaluation.price_truth] += 1
        final_truths[evaluation.composite_truth] += 1
        for name, value in (
            ("technical", base_evaluation.technical_truth),
            ("ma", base_evaluation.ma_truth),
            ("kdj", base_evaluation.kdj_truth),
            ("volatility", base_evaluation.volatility_truth),
            ("composite", base_evaluation.composite_truth),
        ):
            truths[name][value] += 1
        if base_evaluation.hard_eligible:
            hard_count += 1
            truths["eligible"][base_evaluation.composite_truth] += 1
            if status == "processed" and any(base_evaluation.active_groups):
                active_evaluable += 1
                truths["evaluable"][base_evaluation.composite_truth] += 1
            if base_evaluation.composite_truth == "unknown":
                if base_evaluation.visible:
                    unknown_included += 1
                else:
                    unknown_excluded += 1
        audit_count += int(base_evaluation.audit_visible)
        base_visible_count += int(base_evaluation.visible)
        base_counts.add(
            fact=fact,
            technical_row=current_parent,
            outer=outer,
            technical_stock_match=stock_match,
            technical_match=base_match,
            technical_truth=base_truth,
            overall_match=outer.filter_membership and base_match,
        )
        if evaluation.visible:
            base_key = _sort_values_v2(
                query, context, fact, current_parent, ma, kd, vol, price, group,
            )
            sort_keys.append(_sort_key_v2(query, base_key, fact, price))
        r._check_cancel(cancel_callback)
    if (
        parent is not None
        or next(parent_rows, None) is not None
        or position != expected.processed_count
        or position != len(anchor.selection.stock_codes)
    ):
        _fail("processed_population_mismatch")
    f17_counts = base_counts.finish()
    if f17_counts.population != expected:
        _fail("declared_population_mismatch")
    if (
        tuple(item.stock_code for item in price_facts)
        != tuple(item.stock_code for item in group.price_facts)
        or digest_daily_market_technical_universe_price_facts_v1(price_facts)[0]
        != group.price_index_identity_sha256
    ):
        _fail("price_index_mismatch")

    def pairs(name: str) -> tuple[tuple[str, int], ...]:
        return tuple((state, truths[name][state]) for state in _TRUTH_ORDER)

    composite_counts = c.DailyMarketTechnicalOfficialDispositionCompositeCountsV1(
        base_f17_counts=f17_counts,
        ma_state_counts=tuple(ma_states.items()),
        kdj_state_counts=tuple(kd_states.items()),
        bandwidth_state_counts=tuple(bandwidth.items()),
        atr14_state_counts=tuple(atr.items()),
        technical_truth_counts=pairs("technical"),
        ma_truth_counts=pairs("ma"),
        kdj_truth_counts=pairs("kdj"),
        volatility_truth_counts=pairs("volatility"),
        composite_truth_counts=pairs("composite"),
        hard_eligible_truth_counts=pairs("eligible"),
        active_evaluable_truth_counts=pairs("evaluable"),
        hard_eligible_count=hard_count,
        active_evaluable_count=active_evaluable,
        audit_visible_count=audit_count,
        visible_count=base_visible_count,
        unknown_policy_included_count=unknown_included,
        unknown_policy_excluded_count=unknown_excluded,
    )
    counts = DailyMarketTechnicalOfficialDispositionCompositeQueryV2Counts(
        base_f17_counts=f17_counts,
        base_composite_counts=composite_counts,
        price_truth_counts=tuple((key, price_truths[key]) for key in _TRUTH_ORDER),
        final_truth_counts=tuple((key, final_truths[key]) for key in _TRUTH_ORDER),
        price_known_count=price_known,
        price_unknown_count=price_unknown,
        base_visible_count=base_visible_count,
        visible_count=len(sort_keys),
    )
    ordered = _sort_keys_v2(query, sort_keys, cancel_callback)
    coverage = anchor.bundle_reference.source_coverage_status
    result_status: Literal["complete", "partial"] = (
        "complete"
        if anchor.bundle_reference.technical_receipt_status == "complete"
        and expected.pending_count == 0
        and expected.processed_count == expected.included_count
        and coverage == "complete"
        else "partial"
    )
    body = _result_body_v2(
        query=query,
        counts=counts,
        source_pins=source_pins,
        ordered_keys=ordered,
        result_status=result_status,
        coverage_status=coverage,
    )
    operation_identity = _sha256_json(body)
    anchor_identity = _result_anchor_identity_v2(
        query=query,
        operation_identity_sha256=operation_identity,
        counts=counts,
        source_pins=source_pins,
        ordered_keys=ordered,
        result_status=result_status,
        coverage_status=coverage,
        projection_group_session=projection_group_session,
        scope="current_only",
        official_available_at=None,
        availability_status="unknown",
        historical_pit_eligible=False,
    )
    result = DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2(
        query=query,
        operation_identity_sha256=operation_identity,
        counts=counts,
        source_pins=source_pins,
        _ordered_sort_keys=ordered,
        result_status=result_status,
        official_source_coverage_status=coverage,
        _projection_group_session=projection_group_session,
        _seal=_ReaderIssuedIdentityAnchorV2(
            anchor_identity,
            projection_group_session,
            issuer=_RESULT_ANCHOR_ISSUER_V2,
        ),
    )
    result.to_json()
    r._check_cancel(cancel_callback)
    return result


def _entry_for_code(entries: tuple[Any, ...], stock_code: str) -> Any | None:
    codes = tuple(item.stock_code for item in entries)
    position = bisect_left(codes, stock_code)
    return entries[position] if position < len(entries) and codes[position] == stock_code else None


def _materialize_page_v2(
    result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2,
    *,
    page_index: int,
    page_size: int,
    cancel_callback: Callable[[], object] | None,
) -> DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2:
    _validate_page(page_index, page_size)
    r._validate_cancel_callback(cancel_callback)
    r._check_cancel(cancel_callback)
    result.__post_init__()
    session = result._projection_group_session
    anchor = session._require_active()
    if (
        session.identity_sha256 != result.query.projection_group_session_identity_sha256
        or _source_pins_v2(result.query, session) != result.source_pins
    ):
        _fail("page_source_pins_mismatch")
    start = page_index * page_size
    keys = result._ordered_sort_keys[start:start + page_size]
    codes = tuple(item.stock_code for item in keys)
    selected = anchor.bundle_state.read_selected_rows(
        codes,
        cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
    )
    if (
        type(selected) is not DailyMarketTechnicalOfficialDispositionBundleSelectedRowsV1
        or selected.output_root != anchor.bundle_reference.output_root
        or selected.bundle_identity_sha256 != anchor.bundle_reference.bundle_identity_sha256
        or selected.manifest_relative_path != anchor.bundle_reference.manifest_relative_path
        or selected.manifest_sha256 != anchor.bundle_reference.manifest_sha256
        or selected.requested_stock_codes != codes
        or tuple(item.stock_code for item in selected.rows) != codes
    ):
        _fail("page_bundle_rows_mismatch")
    processed_codes = tuple(
        fact.stock_code for fact in selected.rows
        if c._fact_technical_status(fact) == "processed"
    )
    materialized = anchor.p01_session.materialize_selected_stock_codes(
        anchor.selection,
        explicit_stock_codes=processed_codes,
        cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
    )
    if (
        type(materialized) is not DailyMarketTechnicalUniverseV4SelectedRows
        or materialized.read_session_identity_sha256 != anchor.p01_session.read_session_identity_sha256
        or materialized.selection_identity_sha256 != anchor.selection.selection_identity_sha256
        or materialized.query_spec_identity_sha256 != anchor.selection.query_spec_identity_sha256
        or materialized.requested_stock_codes != processed_codes
    ):
        _fail("page_p01_materialization_mismatch")
    parents = {item.stock_code: item for item in materialized.rows}
    if tuple(parents) != processed_codes:
        _fail("page_parent_order_mismatch")
    context = c.prepare_composite_evaluation_context_v1(result.query.base_query)
    ma_entries = session.ma_index.entries
    kd_entries = session.kdj_entries
    vol_entries = session.volatility_entries
    rows: list[DailyMarketTechnicalOfficialDispositionCompositeResultRowV2] = []
    for key, fact in zip(keys, selected.rows, strict=True):
        r._check_cancel(cancel_callback)
        parent = parents.get(fact.stock_code)
        ma = kd = vol = None
        price = session.price_fact_for_code(fact.stock_code)
        if c._fact_technical_status(fact) == "processed":
            ma = _entry_for_code(ma_entries, fact.stock_code)
            kd = _entry_for_code(kd_entries, fact.stock_code)
            vol = _entry_for_code(vol_entries, fact.stock_code)
            if any(item is None for item in (parent, ma, kd, vol, price)):
                _fail("page_projection_missing")
        else:
            parent = None
            price = None
            if any(item is not None for item in (
                _entry_for_code(ma_entries, fact.stock_code),
                _entry_for_code(kd_entries, fact.stock_code),
                _entry_for_code(vol_entries, fact.stock_code),
            )):
                _fail("page_nonprocessed_projection_present")
        outer, base_eval, evaluation, _base_match, _base_truth, _stock_match = _evaluate_row(
            f17_query=result.query.f17_query,
            context=context,
            fact=fact,
            parent=parent,
            ma=ma,
            kd=kd,
            vol=vol,
            price=price,
            query=result.query,
        )
        if not evaluation.visible:
            _fail("page_row_no_longer_visible")
        sort_values = _sort_values_v2(
            result.query, context, fact, parent, ma, kd, vol, price, session,
        )
        actual_key = _sort_key_v2(result.query, sort_values, fact, price)
        if actual_key.to_dict() != key.to_dict():
            _fail("page_sort_key_changed")
        base_payload = c._row_identity_payload(
            query_identity_sha256=result.query.base_query.query_identity_sha256,
            fact_row=fact,
            technical_row=parent,
            ma_entry=ma,
            kdj_entry=kd,
            volatility_entry=vol,
            filter_evaluation=outer,
            evaluation=base_eval,
        )
        base_row = c.DailyMarketTechnicalOfficialDispositionCompositeResultRowV1(
            query_identity_sha256=result.query.base_query.query_identity_sha256,
            fact_row=fact,
            technical_row=parent,
            ma_entry=ma,
            kdj_entry=kd,
            volatility_entry=vol,
            filter_evaluation=outer,
            evaluation=base_eval,
            row_identity_sha256=c._sha256_json(base_payload),
        )
        row_identity = _sha256_json(_row_identity_payload_v2(
            query_identity_sha256=result.query.query_identity_sha256,
            base_row=base_row,
            price_fact=price,
            price_state=evaluation.price_truth,
            evaluation=evaluation,
        ))
        rows.append(DailyMarketTechnicalOfficialDispositionCompositeResultRowV2(
            query_identity_sha256=result.query.query_identity_sha256,
            base_row=base_row,
            price_fact=price,
            price_state=evaluation.price_truth,
            evaluation=evaluation,
            row_identity_sha256=row_identity,
        ))
    request_id = _page_request_identity_v2(result.query, page_index, page_size)
    identity = _page_identity_v2(
        result=result,
        request_identity_sha256=request_id,
        page_index=page_index,
        page_size=page_size,
        rows=tuple(rows),
    )
    page_rows = tuple(rows)
    page_count = (result.visible_count + page_size - 1) // page_size
    page_anchor_identity = _page_anchor_identity_v2(
        result=result,
        request_identity_sha256=request_id,
        operation_identity_sha256=result.operation_identity_sha256,
        page_identity_sha256=identity,
        page_index=page_index,
        page_size=page_size,
        page_count=page_count,
        counts=result.counts,
        rows=page_rows,
        source_pins=result.source_pins,
        result_status=result.result_status,
        coverage_status=result.official_source_coverage_status,
        scope="current_only",
        official_available_at=None,
        availability_status="unknown",
        historical_pit_eligible=False,
    )
    page = DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2(
        query=result.query,
        request_identity_sha256=request_id,
        operation_identity_sha256=result.operation_identity_sha256,
        page_identity_sha256=identity,
        page_index=page_index,
        page_size=page_size,
        page_count=page_count,
        counts=result.counts,
        rows=page_rows,
        source_pins=result.source_pins,
        result_status=result.result_status,
        official_source_coverage_status=result.official_source_coverage_status,
        _result=result,
        _seal=_ReaderIssuedIdentityAnchorV2(
            page_anchor_identity,
            result,
            issuer=_PAGE_ANCHOR_ISSUER_V2,
        ),
    )
    page.to_json()
    r._check_cancel(cancel_callback)
    return page


__all__ = (
    "DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_PAGE_BYTES",
    "DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_PAGE_INDEX",
    "DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_PAGE_SIZE",
    "DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_QUERY_BYTES",
    "DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_RESULT_BYTES",
    "DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_PAGE_V2_SCHEMA",
    "DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_QUERY_V2_SCHEMA",
    "DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_RESULT_V2_SCHEMA",
    "DailyMarketTechnicalOfficialDispositionCompositeEvaluationV2",
    "DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2",
    "DailyMarketTechnicalOfficialDispositionCompositeQueryV2",
    "DailyMarketTechnicalOfficialDispositionCompositeQueryV2Counts",
    "DailyMarketTechnicalOfficialDispositionCompositeQueryV2Error",
    "DailyMarketTechnicalOfficialDispositionCompositeResultRowV2",
    "DailyMarketTechnicalOfficialDispositionCompositeSortClauseV2",
    "DailyMarketTechnicalOfficialDispositionCompositeSortKeyV2",
    "DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2",
    "execute_composite_query_v2",
)
