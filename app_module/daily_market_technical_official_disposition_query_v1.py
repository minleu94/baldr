"""F17 current-only fact rows 的 canonical criteria 與純查詢運算。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Literal, NoReturn, cast
from zoneinfo import ZoneInfo

from app_module.daily_market_technical_official_disposition_bundle_v1 import (
    DailyMarketTechnicalOfficialDispositionFactRowV1,
)
from app_module.daily_market_technical_parent_v4_query import (
    DailyMarketTechnicalParentV4Row,
)
from app_module.daily_market_technical_universe_v4_query import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS,
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_BYTES,
    DailyMarketTechnicalUniverseV4Query,
    DailyMarketTechnicalUniverseV4QueryError,
)


DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_QUERY_V1_SCHEMA = (
    "daily-market-technical-official-disposition-query.v1"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_QUERY_V1_MAX_BYTES = 16 * 1024 * 1024
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_QUERY_V1_CANONICAL_PAGE_SIZE = 1
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_QUERY_V1_MAX_SORT_CLAUSES = 32
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPACT_SORT_MAX_BYTES = 64 * 1024 * 1024
_COMPACT_SORT_CANCEL_CHECK_INTERVAL = 256

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STOCK_CODE_RE = re.compile(r"^[A-Z0-9]{1,16}$")
_TAIPEI = ZoneInfo("Asia/Taipei")
_ROW_SCOPE_ORDER = ("included_processed", "included_pending", "excluded")
_MARKET_STATE_ORDER = ("assigned_twse", "assigned_tpex", "unknown")
_DISPOSAL_STATE_ORDER = (
    "reported_upcoming",
    "reported_active",
    "reported_elapsed_only",
    "unknown",
)
_MARKET_ASSIGNMENT_FIELDS = frozenset({
    "market_assignment.state",
    "market_assignment.snapshot_observed_at",
})
_OFFICIAL_DISPOSAL_FIELDS = frozenset({
    "official_disposal.state",
    "official_disposal.observed_at",
    "official_disposal.observed_date",
})
_KNOWN_UNBOUND_FIELDS = frozenset({
    "price.close_decimal",
    "volume.ratio_20d_decimal",
    "volume.ratio_5d_decimal",
    "chip.branch_net_shares",
    "fundamental.revenue_yoy_percent",
    "industry.excess_bp_5d",
    "industry.excess_bp_20d",
})
_FACT_ROW_SCHEMA = "daily-market-technical-official-disposition-fact-row.v1"
_FACT_ROW_KEYS = frozenset({
    "schema_version",
    "stock_code",
    "cohort_role",
    "exclusion_reason",
    "technical_status",
    "technical_missing_data",
    "market_assignment",
    "official_disposal",
})
_TRUTH_VALUES = frozenset({
    "match", "no_match", "unknown", "not_evaluated", "not_applicable",
})

RowScope = Literal["included_processed", "included_pending", "excluded"]
SortDirection = Literal["asc", "desc"]
ConditionTruth = Literal[
    "match", "no_match", "unknown", "not_evaluated", "not_applicable",
]
SortValue = str | int | date | datetime | Decimal


class DailyMarketTechnicalOfficialDispositionQueryV1Error(ValueError):
    """F17 query criteria、來源列或純排序不符合固定契約。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise DailyMarketTechnicalOfficialDispositionQueryV1Error(code)


def _reject_float_tree(value: object) -> None:
    if isinstance(value, float):
        _fail("technical_official_query_v1_float_forbidden")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                _fail("technical_official_query_v1_json_invalid")
            _reject_float_tree(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_float_tree(item)


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
        raise DailyMarketTechnicalOfficialDispositionQueryV1Error(
            "technical_official_query_v1_json_invalid"
        ) from exc


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("technical_official_query_v1_duplicate_json_key")
        result[key] = value
    return result


def _reject_json_float(_value: str) -> NoReturn:
    _fail("technical_official_query_v1_float_forbidden")


def _reject_json_constant(_value: str) -> NoReturn:
    _fail("technical_official_query_v1_json_constant_invalid")


def _parse_canonical_object(raw: bytes | str) -> dict[str, Any]:
    try:
        encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
        if not isinstance(encoded, bytes):
            _fail("technical_official_query_v1_json_invalid")
        if len(encoded) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_QUERY_V1_MAX_BYTES:
            _fail("technical_official_query_v1_byte_limit")
        value = json.loads(
            encoded.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_float=_reject_json_float,
            parse_constant=_reject_json_constant,
        )
    except DailyMarketTechnicalOfficialDispositionQueryV1Error:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalOfficialDispositionQueryV1Error(
            "technical_official_query_v1_json_invalid"
        ) from exc
    if not isinstance(value, dict):
        _fail("technical_official_query_v1_json_invalid")
    _reject_float_tree(value)
    if _canonical_json_bytes(value) != encoded:
        _fail("technical_official_query_v1_json_noncanonical")
    return value


def _require_text(value: object, code: str, *, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or value.strip() != value
    ):
        _fail(code)
    return value


def _require_sha256(value: object, code: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail(code)
    return value


def normalize_daily_market_technical_official_source_pin_identity_sha256(
    value: object,
) -> str:
    """將官方 source pin 的裸摘要或精確 `sha256:` 形式正規化為裸摘要。"""

    if isinstance(value, str):
        if _SHA256_RE.fullmatch(value) is not None:
            return value
        if value.startswith("sha256:") and _SHA256_RE.fullmatch(value[len("sha256:"):]) is not None:
            return value[len("sha256:"):]
    _fail("technical_official_query_v1_source_pin_identity_invalid")


def _canonical_absolute_path(value: object) -> str:
    text = _require_text(value, "technical_official_query_v1_bundle_root_invalid", maximum=4096)
    path = Path(text)
    if (
        not path.is_absolute()
        or ".." in path.parts
        or str(path) != text
        or text.startswith(("\\\\?\\", "\\\\.\\"))
    ):
        _fail("technical_official_query_v1_bundle_root_invalid")
    return text


def _parse_aware_datetime(value: object, code: str) -> datetime:
    if not isinstance(value, str) or len(value) > 128:
        _fail(code)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise DailyMarketTechnicalOfficialDispositionQueryV1Error(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None or parsed.isoformat() != value:
        _fail(code)
    return parsed


def _parse_date(value: object, code: str) -> date:
    if not isinstance(value, str):
        _fail(code)
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise DailyMarketTechnicalOfficialDispositionQueryV1Error(code) from exc
    if parsed.isoformat() != value:
        _fail(code)
    return parsed


def _normalize_choice_sequence(
    values: Sequence[str],
    allowed: tuple[str, ...],
    *,
    code: str,
    allow_empty: bool,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        _fail(code)
    materialized = tuple(values)
    if (
        (not allow_empty and not materialized)
        or any(not isinstance(value, str) or value not in allowed for value in materialized)
        or len(set(materialized)) != len(materialized)
    ):
        _fail(code)
    return tuple(value for value in allowed if value in materialized)


def _validate_canonical_choices(
    value: object,
    allowed: tuple[str, ...],
    *,
    code: str,
    allow_empty: bool,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        _fail(code)
    raw = tuple(cast(list[object], value))
    if any(not isinstance(item, str) for item in raw):
        _fail(code)
    parsed = _normalize_choice_sequence(
        cast(tuple[str, ...], raw), allowed, code=code, allow_empty=allow_empty
    )
    if parsed != raw:
        _fail(code)
    return parsed


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionSortClauseV1:
    """一項 full-cohort sort 欄位；stock_code 另作最終穩定 tie-break。"""

    field: str
    direction: SortDirection

    def __post_init__(self) -> None:
        _require_text(self.field, "technical_official_query_v1_sort_field_invalid", maximum=128)
        if not isinstance(self.direction, str) or self.direction not in {"asc", "desc"}:
            _fail("technical_official_query_v1_sort_direction_invalid")

    @classmethod
    def from_dict(
        cls, value: object
    ) -> DailyMarketTechnicalOfficialDispositionSortClauseV1:
        if not isinstance(value, Mapping) or set(value) != {"field", "direction"}:
            _fail("technical_official_query_v1_sort_clause_invalid")
        field_value = value.get("field")
        direction = value.get("direction")
        if (
            not isinstance(field_value, str)
            or not isinstance(direction, str)
            or direction not in {"asc", "desc"}
        ):
            _fail("technical_official_query_v1_sort_clause_invalid")
        return cls(
            field=field_value,
            direction=cast(SortDirection, direction),
        )

    def to_dict(self) -> dict[str, str]:
        return {"field": self.field, "direction": self.direction}


_QUERY_KEYS = frozenset({
    "schema_version",
    "technical_query_json",
    "decision_cutoff",
    "bundle_output_root",
    "bundle_identity_sha256",
    "expected_manifest_sha256",
    "market_assignment_pin_identity_sha256",
    "official_disposal_pin_identity_sha256",
    "row_scope_filter",
    "market_assignment_states",
    "official_disposal_states",
    "outer_stock_filter_mode",
    "outer_stock_codes",
    "sort_clauses",
    "query_identity_sha256",
})


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionQueryV1:
    """固定 P01 exact query、F17 bundle pins 與 outer query 條件。"""

    technical_query: DailyMarketTechnicalUniverseV4Query
    decision_cutoff: datetime
    bundle_output_root: str
    bundle_identity_sha256: str
    expected_manifest_sha256: str
    market_assignment_pin_identity_sha256: str
    official_disposal_pin_identity_sha256: str
    row_scope_filter: tuple[RowScope, ...]
    market_assignment_states: tuple[str, ...]
    official_disposal_states: tuple[str, ...]
    outer_stock_filter_mode: Literal["all", "explicit_codes"]
    outer_stock_codes: tuple[str, ...]
    sort_clauses: tuple[DailyMarketTechnicalOfficialDispositionSortClauseV1, ...]
    query_identity_sha256: str

    def __post_init__(self) -> None:
        _validate_query_object(self)

    @classmethod
    def create(
        cls,
        *,
        technical_query: DailyMarketTechnicalUniverseV4Query,
        decision_cutoff: datetime,
        bundle_output_root: str | Path,
        bundle_identity_sha256: str,
        expected_manifest_sha256: str,
        market_assignment_pin_identity_sha256: str,
        official_disposal_pin_identity_sha256: str,
        row_scope_filter: Sequence[RowScope],
        market_assignment_states: Sequence[str] = (),
        official_disposal_states: Sequence[str] = (),
        outer_stock_filter_mode: Literal["all", "explicit_codes"] = "all",
        outer_stock_codes: Sequence[str] = (),
        sort_clauses: Sequence[DailyMarketTechnicalOfficialDispositionSortClauseV1] = (),
    ) -> DailyMarketTechnicalOfficialDispositionQueryV1:
        if not isinstance(technical_query, DailyMarketTechnicalUniverseV4Query):
            _fail("technical_official_query_v1_technical_query_invalid")
        if not isinstance(decision_cutoff, datetime):
            _fail("technical_official_query_v1_cutoff_invalid")
        cutoff = decision_cutoff
        if cutoff.tzinfo is None or cutoff.utcoffset() is None:
            _fail("technical_official_query_v1_cutoff_invalid")
        market_pin_identity = normalize_daily_market_technical_official_source_pin_identity_sha256(
            market_assignment_pin_identity_sha256
        )
        disposal_pin_identity = normalize_daily_market_technical_official_source_pin_identity_sha256(
            official_disposal_pin_identity_sha256
        )
        normalized_scopes = _normalize_choice_sequence(
            row_scope_filter,
            cast(tuple[str, ...], _ROW_SCOPE_ORDER),
            code="technical_official_query_v1_row_scope_invalid",
            allow_empty=False,
        )
        normalized_market = _normalize_choice_sequence(
            market_assignment_states,
            cast(tuple[str, ...], _MARKET_STATE_ORDER),
            code="technical_official_query_v1_market_states_invalid",
            allow_empty=True,
        )
        normalized_disposal = _normalize_choice_sequence(
            official_disposal_states,
            cast(tuple[str, ...], _DISPOSAL_STATE_ORDER),
            code="technical_official_query_v1_disposal_states_invalid",
            allow_empty=True,
        )
        if not isinstance(outer_stock_filter_mode, str) or outer_stock_filter_mode not in {"all", "explicit_codes"}:
            _fail("technical_official_query_v1_stock_filter_invalid")
        if isinstance(outer_stock_codes, (str, bytes)) or not isinstance(outer_stock_codes, Sequence):
            _fail("technical_official_query_v1_stock_filter_invalid")
        codes = tuple(outer_stock_codes)
        if (
            len(codes) > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS
            or any(not isinstance(code, str) or _STOCK_CODE_RE.fullmatch(code) is None for code in codes)
            or len(set(codes)) != len(codes)
        ):
            _fail("technical_official_query_v1_stock_filter_invalid")
        codes = tuple(sorted(codes))
        if outer_stock_filter_mode == "all" and codes:
            _fail("technical_official_query_v1_stock_filter_invalid")
        if isinstance(sort_clauses, (str, bytes)) or not isinstance(sort_clauses, Sequence):
            _fail("technical_official_query_v1_sort_clauses_invalid")
        clauses = tuple(sort_clauses)
        if any(not isinstance(clause, DailyMarketTechnicalOfficialDispositionSortClauseV1) for clause in clauses):
            _fail("technical_official_query_v1_sort_clauses_invalid")
        if not clauses:
            clauses = (
                DailyMarketTechnicalOfficialDispositionSortClauseV1("stock_code", "asc"),
            )
        body = _query_body_from_values(
            technical_query=technical_query,
            decision_cutoff=cutoff,
            bundle_output_root=str(bundle_output_root),
            bundle_identity_sha256=bundle_identity_sha256,
            expected_manifest_sha256=expected_manifest_sha256,
            market_assignment_pin_identity_sha256=market_pin_identity,
            official_disposal_pin_identity_sha256=disposal_pin_identity,
            row_scope_filter=normalized_scopes,
            market_assignment_states=normalized_market,
            official_disposal_states=normalized_disposal,
            outer_stock_filter_mode=outer_stock_filter_mode,
            outer_stock_codes=codes,
            sort_clauses=clauses,
        )
        return cls(
            technical_query=technical_query,
            decision_cutoff=cutoff,
            bundle_output_root=str(bundle_output_root),
            bundle_identity_sha256=bundle_identity_sha256,
            expected_manifest_sha256=expected_manifest_sha256,
            market_assignment_pin_identity_sha256=market_pin_identity,
            official_disposal_pin_identity_sha256=disposal_pin_identity,
            row_scope_filter=cast(tuple[RowScope, ...], normalized_scopes),
            market_assignment_states=normalized_market,
            official_disposal_states=normalized_disposal,
            outer_stock_filter_mode=outer_stock_filter_mode,
            outer_stock_codes=codes,
            sort_clauses=clauses,
            query_identity_sha256=_sha256_json(body),
        )

    @classmethod
    def from_dict(cls, value: object) -> DailyMarketTechnicalOfficialDispositionQueryV1:
        if not isinstance(value, Mapping) or set(value) != _QUERY_KEYS:
            _fail("technical_official_query_v1_fields_invalid")
        payload = dict(value)
        if payload.get("schema_version") != DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_QUERY_V1_SCHEMA:
            _fail("technical_official_query_v1_schema_unsupported")
        raw_technical_query = payload.get("technical_query_json")
        if not isinstance(raw_technical_query, str) or len(raw_technical_query.encode("utf-8")) > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_BYTES:
            _fail("technical_official_query_v1_technical_query_invalid")
        try:
            technical_query = DailyMarketTechnicalUniverseV4Query.from_json(raw_technical_query)
        except (DailyMarketTechnicalUniverseV4QueryError, UnicodeError) as exc:
            raise DailyMarketTechnicalOfficialDispositionQueryV1Error(
                "technical_official_query_v1_technical_query_invalid"
            ) from exc
        cutoff = _parse_aware_datetime(
            payload.get("decision_cutoff"), "technical_official_query_v1_cutoff_invalid"
        )
        scopes = _validate_canonical_choices(
            payload.get("row_scope_filter"),
            cast(tuple[str, ...], _ROW_SCOPE_ORDER),
            code="technical_official_query_v1_row_scope_invalid",
            allow_empty=False,
        )
        market_states = _validate_canonical_choices(
            payload.get("market_assignment_states"),
            cast(tuple[str, ...], _MARKET_STATE_ORDER),
            code="technical_official_query_v1_market_states_invalid",
            allow_empty=True,
        )
        disposal_states = _validate_canonical_choices(
            payload.get("official_disposal_states"),
            cast(tuple[str, ...], _DISPOSAL_STATE_ORDER),
            code="technical_official_query_v1_disposal_states_invalid",
            allow_empty=True,
        )
        mode = payload.get("outer_stock_filter_mode")
        if not isinstance(mode, str) or mode not in {"all", "explicit_codes"}:
            _fail("technical_official_query_v1_stock_filter_invalid")
        raw_codes = payload.get("outer_stock_codes")
        if not isinstance(raw_codes, list):
            _fail("technical_official_query_v1_stock_filter_invalid")
        codes = tuple(cast(list[object], raw_codes))
        if (
            len(codes) > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS
            or any(not isinstance(code, str) or _STOCK_CODE_RE.fullmatch(code) is None for code in codes)
        ):
            _fail("technical_official_query_v1_stock_filter_invalid")
        typed_codes = cast(tuple[str, ...], codes)
        if typed_codes != tuple(sorted(set(typed_codes))) or (mode == "all" and typed_codes):
            _fail("technical_official_query_v1_stock_filter_invalid")
        raw_clauses = payload.get("sort_clauses")
        if not isinstance(raw_clauses, list) or len(raw_clauses) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_QUERY_V1_MAX_SORT_CLAUSES:
            _fail("technical_official_query_v1_sort_clauses_invalid")
        clauses = tuple(
            DailyMarketTechnicalOfficialDispositionSortClauseV1.from_dict(item)
            for item in cast(list[object], raw_clauses)
        )
        if not clauses or len({clause.field for clause in clauses}) != len(clauses):
            _fail("technical_official_query_v1_sort_clauses_invalid")
        query = cls(
            technical_query=technical_query,
            decision_cutoff=cutoff,
            bundle_output_root=_canonical_absolute_path(payload.get("bundle_output_root")),
            bundle_identity_sha256=_require_sha256(
                payload.get("bundle_identity_sha256"), "technical_official_query_v1_bundle_identity_invalid"
            ),
            expected_manifest_sha256=_require_sha256(
                payload.get("expected_manifest_sha256"), "technical_official_query_v1_manifest_sha_invalid"
            ),
            market_assignment_pin_identity_sha256=_require_sha256(
                payload.get("market_assignment_pin_identity_sha256"), "technical_official_query_v1_market_pin_invalid"
            ),
            official_disposal_pin_identity_sha256=_require_sha256(
                payload.get("official_disposal_pin_identity_sha256"), "technical_official_query_v1_disposal_pin_invalid"
            ),
            row_scope_filter=cast(tuple[RowScope, ...], scopes),
            market_assignment_states=market_states,
            official_disposal_states=disposal_states,
            outer_stock_filter_mode=cast(Literal["all", "explicit_codes"], mode),
            outer_stock_codes=typed_codes,
            sort_clauses=clauses,
            query_identity_sha256=_require_sha256(
                payload.get("query_identity_sha256"), "technical_official_query_v1_identity_invalid"
            ),
        )
        if query.to_json() != _canonical_json_bytes(payload).decode("utf-8"):
            _fail("technical_official_query_v1_json_noncanonical")
        return query

    @classmethod
    def from_json(cls, raw: bytes | str) -> DailyMarketTechnicalOfficialDispositionQueryV1:
        return cls.from_dict(_parse_canonical_object(raw))

    @property
    def decision_date(self) -> date:
        return self.technical_query.decision_date

    @property
    def identity_sha256(self) -> str:
        return self.query_identity_sha256

    def to_dict(self) -> dict[str, object]:
        return {
            **_query_body_from_values(
                technical_query=self.technical_query,
                decision_cutoff=self.decision_cutoff,
                bundle_output_root=self.bundle_output_root,
                bundle_identity_sha256=self.bundle_identity_sha256,
                expected_manifest_sha256=self.expected_manifest_sha256,
                market_assignment_pin_identity_sha256=self.market_assignment_pin_identity_sha256,
                official_disposal_pin_identity_sha256=self.official_disposal_pin_identity_sha256,
                row_scope_filter=self.row_scope_filter,
                market_assignment_states=self.market_assignment_states,
                official_disposal_states=self.official_disposal_states,
                outer_stock_filter_mode=self.outer_stock_filter_mode,
                outer_stock_codes=self.outer_stock_codes,
                sort_clauses=self.sort_clauses,
            ),
            "query_identity_sha256": self.query_identity_sha256,
        }

    def to_json(self) -> str:
        raw = _canonical_json_bytes(self.to_dict())
        if len(raw) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_QUERY_V1_MAX_BYTES:
            _fail("technical_official_query_v1_byte_limit")
        return raw.decode("utf-8")


def _query_body_from_values(
    *,
    technical_query: DailyMarketTechnicalUniverseV4Query,
    decision_cutoff: datetime,
    bundle_output_root: str,
    bundle_identity_sha256: str,
    expected_manifest_sha256: str,
    market_assignment_pin_identity_sha256: str,
    official_disposal_pin_identity_sha256: str,
    row_scope_filter: Sequence[str],
    market_assignment_states: Sequence[str],
    official_disposal_states: Sequence[str],
    outer_stock_filter_mode: str,
    outer_stock_codes: Sequence[str],
    sort_clauses: Sequence[DailyMarketTechnicalOfficialDispositionSortClauseV1],
) -> dict[str, object]:
    return {
        "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_QUERY_V1_SCHEMA,
        "technical_query_json": technical_query.to_json(),
        "decision_cutoff": decision_cutoff.isoformat(),
        "bundle_output_root": bundle_output_root,
        "bundle_identity_sha256": bundle_identity_sha256,
        "expected_manifest_sha256": expected_manifest_sha256,
        "market_assignment_pin_identity_sha256": market_assignment_pin_identity_sha256,
        "official_disposal_pin_identity_sha256": official_disposal_pin_identity_sha256,
        "row_scope_filter": list(row_scope_filter),
        "market_assignment_states": list(market_assignment_states),
        "official_disposal_states": list(official_disposal_states),
        "outer_stock_filter_mode": outer_stock_filter_mode,
        "outer_stock_codes": list(outer_stock_codes),
        "sort_clauses": [item.to_dict() for item in sort_clauses],
    }


def _validate_query_object(query: DailyMarketTechnicalOfficialDispositionQueryV1) -> None:
    if not isinstance(query.technical_query, DailyMarketTechnicalUniverseV4Query):
        _fail("technical_official_query_v1_technical_query_invalid")
    technical = query.technical_query
    if (
        technical.page_index != 0
        or technical.page_size != DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_QUERY_V1_CANONICAL_PAGE_SIZE
    ):
        _fail("technical_official_query_v1_technical_query_page_placeholder_invalid")
    cutoff = query.decision_cutoff
    if not isinstance(cutoff, datetime) or cutoff.tzinfo is None or cutoff.utcoffset() is None:
        _fail("technical_official_query_v1_cutoff_invalid")
    taipei_cutoff = cutoff.astimezone(_TAIPEI)
    if taipei_cutoff.date() != technical.decision_date or taipei_cutoff.time().replace(tzinfo=None) < time(16, 0):
        _fail("technical_official_query_v1_cutoff_guard_invalid")
    _canonical_absolute_path(query.bundle_output_root)
    _require_sha256(query.bundle_identity_sha256, "technical_official_query_v1_bundle_identity_invalid")
    _require_sha256(query.expected_manifest_sha256, "technical_official_query_v1_manifest_sha_invalid")
    _require_sha256(
        query.market_assignment_pin_identity_sha256, "technical_official_query_v1_market_pin_invalid"
    )
    _require_sha256(
        query.official_disposal_pin_identity_sha256, "technical_official_query_v1_disposal_pin_invalid"
    )
    scopes = _normalize_choice_sequence(
        query.row_scope_filter,
        cast(tuple[str, ...], _ROW_SCOPE_ORDER),
        code="technical_official_query_v1_row_scope_invalid",
        allow_empty=False,
    )
    if scopes != query.row_scope_filter:
        _fail("technical_official_query_v1_row_scope_invalid")
    market = _normalize_choice_sequence(
        query.market_assignment_states,
        cast(tuple[str, ...], _MARKET_STATE_ORDER),
        code="technical_official_query_v1_market_states_invalid",
        allow_empty=True,
    )
    disposal = _normalize_choice_sequence(
        query.official_disposal_states,
        cast(tuple[str, ...], _DISPOSAL_STATE_ORDER),
        code="technical_official_query_v1_disposal_states_invalid",
        allow_empty=True,
    )
    if market != query.market_assignment_states or disposal != query.official_disposal_states:
        _fail("technical_official_query_v1_state_order_invalid")
    if (
        not isinstance(query.outer_stock_filter_mode, str)
        or query.outer_stock_filter_mode not in {"all", "explicit_codes"}
    ):
        _fail("technical_official_query_v1_stock_filter_invalid")
    codes = query.outer_stock_codes
    if (
        len(codes) > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS
        or codes != tuple(sorted(set(codes)))
        or any(not isinstance(code, str) or _STOCK_CODE_RE.fullmatch(code) is None for code in codes)
        or (query.outer_stock_filter_mode == "all" and codes)
    ):
        _fail("technical_official_query_v1_stock_filter_invalid")
    if not query.sort_clauses or len(query.sort_clauses) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_QUERY_V1_MAX_SORT_CLAUSES:
        _fail("technical_official_query_v1_sort_clauses_invalid")
    if any(
        not isinstance(item, DailyMarketTechnicalOfficialDispositionSortClauseV1)
        for item in query.sort_clauses
    ):
        _fail("technical_official_query_v1_sort_clauses_invalid")
    fields = tuple(item.field for item in query.sort_clauses)
    if len(fields) != len(set(fields)):
        _fail("technical_official_query_v1_sort_clauses_invalid")
    _validate_sort_fields(fields, technical.method_rule_keys)
    if _sha256_json(_query_body_from_values(
        technical_query=technical,
        decision_cutoff=cutoff,
        bundle_output_root=query.bundle_output_root,
        bundle_identity_sha256=query.bundle_identity_sha256,
        expected_manifest_sha256=query.expected_manifest_sha256,
        market_assignment_pin_identity_sha256=query.market_assignment_pin_identity_sha256,
        official_disposal_pin_identity_sha256=query.official_disposal_pin_identity_sha256,
        row_scope_filter=query.row_scope_filter,
        market_assignment_states=query.market_assignment_states,
        official_disposal_states=query.official_disposal_states,
        outer_stock_filter_mode=query.outer_stock_filter_mode,
        outer_stock_codes=query.outer_stock_codes,
        sort_clauses=query.sort_clauses,
    )) != query.query_identity_sha256:
        _fail("technical_official_query_v1_identity_mismatch")


def _validate_sort_fields(fields: Sequence[str], method_rule_keys: Sequence[str]) -> None:
    technical_fields = {
        "stock_code", "decision_date", "latest_feature_date", "raw_row_count",
    }
    for rule_key in method_rule_keys:
        technical_fields.update({
            f"{rule_key}.ratio",
            f"{rule_key}.numerator",
            f"{rule_key}.denominator",
        })
    allowed = technical_fields | _MARKET_ASSIGNMENT_FIELDS | _OFFICIAL_DISPOSAL_FIELDS
    for field_name in fields:
        if field_name in _KNOWN_UNBOUND_FIELDS:
            _fail("technical_official_query_v1_sort_source_not_bound")
        if field_name not in allowed:
            _fail("technical_official_query_v1_sort_key_unsupported")


def _fact_payload(
    fact_row: DailyMarketTechnicalOfficialDispositionFactRowV1,
    query: DailyMarketTechnicalOfficialDispositionQueryV1,
) -> dict[str, object]:
    if not isinstance(fact_row, DailyMarketTechnicalOfficialDispositionFactRowV1):
        _fail("technical_official_query_v1_fact_row_unverified")
    payload = fact_row.to_dict()
    if set(payload) != _FACT_ROW_KEYS or payload.get("schema_version") != _FACT_ROW_SCHEMA:
        _fail("technical_official_query_v1_fact_row_schema_invalid")
    stock_code = payload.get("stock_code")
    if (
        not isinstance(stock_code, str)
        or _STOCK_CODE_RE.fullmatch(stock_code) is None
        or fact_row.stock_code != stock_code
    ):
        _fail("technical_official_query_v1_fact_row_stock_invalid")
    role = payload.get("cohort_role")
    status = payload.get("technical_status")
    reason = payload.get("exclusion_reason")
    missing = payload.get("technical_missing_data")
    if role == "included":
        if status not in {"processed", "pending"} or reason is not None:
            _fail("technical_official_query_v1_fact_row_role_invalid")
        if status == "pending" and missing is not None:
            _fail("technical_official_query_v1_fact_row_missing_state_invalid")
        if status == "processed" and type(missing) is not bool:
            _fail("technical_official_query_v1_fact_row_missing_state_invalid")
    elif role == "excluded":
        if status != "excluded" or not isinstance(reason, str) or not reason.strip() or missing is not None:
            _fail("technical_official_query_v1_fact_row_role_invalid")
    else:
        _fail("technical_official_query_v1_fact_row_role_invalid")
    market = payload.get("market_assignment")
    disposal = payload.get("official_disposal")
    if not isinstance(market, Mapping) or not isinstance(disposal, Mapping):
        _fail("technical_official_query_v1_fact_row_observation_invalid")
    _validate_observation_scope(market, stock_code, query.market_assignment_pin_identity_sha256)
    _validate_observation_scope(disposal, stock_code, query.official_disposal_pin_identity_sha256)
    market_state = market.get("state")
    disposal_state = disposal.get("state")
    if market_state not in _MARKET_STATE_ORDER or disposal_state not in _DISPOSAL_STATE_ORDER:
        _fail("technical_official_query_v1_fact_row_state_invalid")
    cutoff = query.decision_cutoff
    market_cutoff = _parse_aware_datetime(
        market.get("cutoff_at"), "technical_official_query_v1_market_cutoff_invalid"
    )
    if market_cutoff != cutoff:
        _fail("technical_official_query_v1_market_cutoff_mismatch")
    snapshot_time = _parse_aware_datetime(
        market.get("snapshot_observed_at"), "technical_official_query_v1_market_observation_time_invalid"
    )
    pointer_time = _parse_aware_datetime(
        market.get("pointer_published_at"), "technical_official_query_v1_market_pointer_time_invalid"
    )
    if snapshot_time > cutoff or pointer_time > cutoff:
        _fail("technical_official_query_v1_future_market_evidence")
    _validate_optional_observed_at(disposal.get("observed_at"), cutoff)
    _validate_disposal_evidence(disposal, cutoff)
    observed_date = disposal.get("observed_date")
    if observed_date is not None and _parse_date(
        observed_date, "technical_official_query_v1_disposal_observed_date_invalid"
    ) > cutoff.astimezone(_TAIPEI).date():
        _fail("technical_official_query_v1_future_disposal_observation")
    return dict(payload)


def _validate_observation_scope(
    observation: Mapping[str, object], stock_code: str, expected_pin_sha256: str
) -> None:
    if (
        observation.get("symbol") != stock_code
        or observation.get("scope") != "current_only"
        or observation.get("historical_pit_eligible") is not False
        or observation.get("official_available_at") is not None
    ):
        _fail("technical_official_query_v1_observation_scope_invalid")
    aliases = tuple(
        normalize_daily_market_technical_official_source_pin_identity_sha256(
            observation[key]
        )
        for key in ("source_pin_identity_sha256", "source_pin_sha256")
        if key in observation
    )
    if not aliases:
        _fail("technical_official_query_v1_observation_pin_mismatch")
    if len(set(aliases)) > 1:
        _fail("technical_official_query_v1_observation_pin_alias_conflict")
    if aliases[0] != expected_pin_sha256:
        _fail("technical_official_query_v1_observation_pin_mismatch")


def _validate_optional_observed_at(value: object, cutoff: datetime) -> datetime | None:
    if value is None:
        return None
    parsed = _parse_aware_datetime(value, "technical_official_query_v1_observed_at_invalid")
    if parsed > cutoff:
        _fail("technical_official_query_v1_future_observation")
    return parsed


def _validate_disposal_evidence(disposal: Mapping[str, object], cutoff: datetime) -> None:
    source_dates = disposal.get("source_data_dates")
    if not isinstance(source_dates, list):
        _fail("technical_official_query_v1_disposal_source_dates_invalid")
    cutoff_date = cutoff.astimezone(_TAIPEI).date()
    for raw_date in source_dates:
        if _parse_date(raw_date, "technical_official_query_v1_disposal_source_date_invalid") > cutoff_date:
            _fail("technical_official_query_v1_future_disposal_source_date")
    captures = disposal.get("source_capture_dates_by_id")
    if not isinstance(captures, list):
        _fail("technical_official_query_v1_disposal_capture_dates_invalid")
    for item in captures:
        if not isinstance(item, Mapping):
            _fail("technical_official_query_v1_disposal_capture_dates_invalid")
        captured_at = _parse_aware_datetime(
            item.get("captured_at"), "technical_official_query_v1_capture_time_invalid"
        )
        if captured_at > cutoff:
            _fail("technical_official_query_v1_future_capture")
        raw_source_dates = item.get("source_data_dates")
        if not isinstance(raw_source_dates, list):
            _fail("technical_official_query_v1_disposal_capture_dates_invalid")
        for raw_date in raw_source_dates:
            if _parse_date(raw_date, "technical_official_query_v1_disposal_source_date_invalid") > cutoff_date:
                _fail("technical_official_query_v1_future_disposal_source_date")
    events = disposal.get("events")
    if not isinstance(events, list):
        _fail("technical_official_query_v1_disposal_events_invalid")
    for event in events:
        if not isinstance(event, Mapping):
            _fail("technical_official_query_v1_disposal_events_invalid")
        announcement = _parse_date(
            event.get("announcement_date"), "technical_official_query_v1_announcement_date_invalid"
        )
        effective_from = _parse_date(
            event.get("effective_from"), "technical_official_query_v1_effective_date_invalid"
        )
        effective_to = _parse_date(
            event.get("effective_to"), "technical_official_query_v1_effective_date_invalid"
        )
        observed_at = _parse_aware_datetime(
            event.get("observed_at"), "technical_official_query_v1_event_observed_at_invalid"
        )
        if effective_to < effective_from:
            _fail("technical_official_query_v1_effective_date_invalid")
        if observed_at > cutoff:
            _fail("technical_official_query_v1_future_event_observation")
        if announcement > observed_at.astimezone(_TAIPEI).date():
            _fail("technical_official_query_v1_future_announcement")
        # 生效日可晚於觀察日；已觀察的公告事件仍可呈現 upcoming。


def evaluate_f17_membership_v1(
    query: DailyMarketTechnicalOfficialDispositionQueryV1,
    fact_row: DailyMarketTechnicalOfficialDispositionFactRowV1,
) -> "DailyMarketTechnicalOfficialDispositionFilterEvaluationV1":
    """評估 row-scope／股票／官方狀態篩選，明確分開 membership 與來源 truth。

    此結果只描述 F17 outer filters；它不代表技術條件已通過，也不代表完整
    composite query 已 join 或完成全母體驗證。
    """

    if not isinstance(query, DailyMarketTechnicalOfficialDispositionQueryV1):
        _fail("technical_official_query_v1_query_invalid")
    payload = _fact_payload(fact_row, query)
    code = cast(str, payload["stock_code"])
    role = cast(str, payload["cohort_role"])
    status = cast(str, payload["technical_status"])
    scope: str = "excluded" if role == "excluded" else (
        "included_processed" if status == "processed" else "included_pending"
    )
    scope_match = scope in query.row_scope_filter
    stock_match = (
        query.outer_stock_filter_mode == "all"
        or code in query.outer_stock_codes
    )
    market = cast(Mapping[str, object], payload["market_assignment"])
    disposal = cast(Mapping[str, object], payload["official_disposal"])
    market_match, market_truth = _state_filter_outcome(
        cast(str, market["state"]),
        query.market_assignment_states,
        _MARKET_STATE_ORDER,
    )
    disposal_match, disposal_truth = _state_filter_outcome(
        cast(str, disposal["state"]),
        query.official_disposal_states,
        _DISPOSAL_STATE_ORDER,
    )
    return DailyMarketTechnicalOfficialDispositionFilterEvaluationV1(
        stock_code=code,
        row_scope=cast(RowScope, scope),
        row_scope_match=scope_match,
        stock_filter_match=stock_match,
        market_assignment_match=market_match,
        market_assignment_truth=market_truth,
        official_disposal_match=disposal_match,
        official_disposal_truth=disposal_truth,
    )


def _state_filter_outcome(
    actual_state: str,
    selected_states: Sequence[str],
    valid_states: tuple[str, ...],
) -> tuple[bool, ConditionTruth]:
    if actual_state not in valid_states:
        _fail("technical_official_query_v1_fact_row_state_invalid")
    if not selected_states:
        return True, "not_applicable"
    if actual_state == "unknown":
        return actual_state in selected_states, "unknown"
    if actual_state in selected_states:
        return True, "match"
    return False, "no_match"


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionFilterEvaluationV1:
    stock_code: str
    row_scope: RowScope
    row_scope_match: bool
    stock_filter_match: bool
    market_assignment_match: bool
    market_assignment_truth: ConditionTruth
    official_disposal_match: bool
    official_disposal_truth: ConditionTruth

    @property
    def filter_membership(self) -> bool:
        return (
            self.row_scope_match
            and self.stock_filter_match
            and self.market_assignment_match
            and self.official_disposal_match
        )


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionJoinedRowV1:
    """已核 F17 列與同一代 P01 row 的純排序輸入。

    此 DTO 的欄位一致性檢查不能取代 reader 對 issuer、generation、receipt
    與來源 pins 的 exact 驗證。
    """

    fact_row: DailyMarketTechnicalOfficialDispositionFactRowV1
    technical_row: DailyMarketTechnicalParentV4Row | None

    def __post_init__(self) -> None:
        if not isinstance(self.fact_row, DailyMarketTechnicalOfficialDispositionFactRowV1):
            _fail("technical_official_query_v1_fact_row_unverified")
        if self.technical_row is not None and (
            not isinstance(self.technical_row, DailyMarketTechnicalParentV4Row)
            or self.technical_row.stock_code != self.fact_row.stock_code
        ):
            _fail("technical_official_query_v1_technical_row_mismatch")


def _validate_joined_technical_row(
    query: DailyMarketTechnicalOfficialDispositionQueryV1,
    *,
    fact_payload: Mapping[str, object],
    technical_row: DailyMarketTechnicalParentV4Row | None,
) -> None:
    """核對公開 DTO 可驗的 P01 日期、規則與缺值一致性。"""

    status = fact_payload.get("technical_status")
    if (status == "processed") != (technical_row is not None):
        _fail("technical_official_query_v1_technical_row_scope_invalid")
    if technical_row is None:
        return

    if technical_row.stock_code != fact_payload.get("stock_code"):
        _fail("technical_official_query_v1_technical_row_stock_scope_mismatch")
    if type(technical_row.decision_date) is not date or technical_row.decision_date != query.decision_date:
        _fail("technical_official_query_v1_technical_row_decision_date_mismatch")
    latest_feature_date = technical_row.latest_feature_date
    if latest_feature_date is not None and type(latest_feature_date) is not date:
        _fail("technical_official_query_v1_technical_row_feature_date_invalid")
    if latest_feature_date is not None and latest_feature_date > query.decision_date:
        _fail("technical_official_query_v1_technical_row_future_feature_date")
    if type(technical_row.raw_row_count) is not int or technical_row.raw_row_count < 0:
        _fail("technical_official_query_v1_technical_row_raw_count_invalid")
    if type(technical_row.observed_prefix_contiguous) is not bool:
        _fail("technical_official_query_v1_technical_row_source_scope_invalid")
    missing = fact_payload.get("technical_missing_data")
    if type(missing) is not bool or missing != technical_row.has_missing_data:
        _fail("technical_official_query_v1_technical_missing_data_mismatch")
    _require_sha256(
        technical_row.snapshot_identity_sha256,
        "technical_official_query_v1_technical_snapshot_identity_invalid",
    )
    _require_text(
        technical_row.source_identity,
        "technical_official_query_v1_technical_source_identity_invalid",
        maximum=512,
    )

    expected_rule_keys = query.technical_query.method_rule_keys
    rules = technical_row.rules
    if not isinstance(rules, tuple) or tuple(rule.key for rule in rules) != expected_rule_keys:
        _fail("technical_official_query_v1_technical_rule_scope_mismatch")

    expected_lookahead = (
        "feature_dates_within_decision_date"
        if technical_row.observed_prefix_contiguous
        else "observed_prefix_not_contiguous"
    )
    source_window_fingerprints: set[str] = set()
    previous_feature_dates: set[date | None] = set()
    for rule in rules:
        if rule.stock_code != technical_row.stock_code:
            _fail("technical_official_query_v1_technical_rule_stock_scope_mismatch")
        if type(rule.decision_date) is not date or rule.decision_date != query.decision_date:
            _fail("technical_official_query_v1_technical_rule_decision_date_mismatch")
        rule_cutoff = rule.decision_cutoff
        if (
            not isinstance(rule_cutoff, datetime)
            or rule_cutoff.tzinfo is None
            or rule_cutoff.utcoffset() is None
            or rule_cutoff != query.decision_cutoff
        ):
            _fail("technical_official_query_v1_technical_rule_cutoff_mismatch")
        if rule.source_identity != technical_row.source_identity:
            _fail("technical_official_query_v1_technical_rule_source_scope_mismatch")
        source_window_fingerprints.add(_require_sha256(
            rule.source_window_fingerprint_sha256,
            "technical_official_query_v1_technical_rule_source_fingerprint_invalid",
        ))
        for label, feature_date in (
            ("feature", rule.feature_date),
            ("previous", rule.previous_feature_date),
        ):
            if feature_date is not None and type(feature_date) is not date:
                _fail(f"technical_official_query_v1_technical_rule_{label}_date_invalid")
            if feature_date is not None and feature_date > query.decision_date:
                _fail(f"technical_official_query_v1_technical_rule_future_{label}_date")
        if rule.feature_date != latest_feature_date:
            _fail("technical_official_query_v1_technical_rule_feature_scope_mismatch")
        previous_feature_dates.add(rule.previous_feature_date)
        if rule.lookahead_check != expected_lookahead:
            _fail("technical_official_query_v1_technical_rule_lookahead_mismatch")
        # available_at_unknown 是 current-only 來源的明示限制，不代表未來資料。
        if rule.availability_result != "available_at_unknown":
            _fail("technical_official_query_v1_technical_rule_availability_invalid")
        if rule.state not in {"match", "no_match", "unknown"}:
            _fail("technical_official_query_v1_technical_rule_state_invalid")
        for numeric_value in (rule.numerator, rule.denominator, rule.ratio):
            if numeric_value is not None and (
                not isinstance(numeric_value, Decimal) or not numeric_value.is_finite()
            ):
                _fail("technical_official_query_v1_technical_rule_decimal_invalid")
    if len(source_window_fingerprints) != 1 or len(previous_feature_dates) != 1:
        _fail("technical_official_query_v1_technical_rule_source_scope_mismatch")


def sort_joined_rows_v1(
    query: DailyMarketTechnicalOfficialDispositionQueryV1,
    rows: Sequence[DailyMarketTechnicalOfficialDispositionJoinedRowV1],
) -> tuple[DailyMarketTechnicalOfficialDispositionJoinedRowV1, ...]:
    """在完整輸入集合上依多欄排序；所有 null 雙向置尾、股票代碼穩定打破平手。"""

    if not isinstance(query, DailyMarketTechnicalOfficialDispositionQueryV1):
        _fail("technical_official_query_v1_query_invalid")
    if isinstance(rows, (str, bytes)) or not isinstance(rows, Sequence):
        _fail("technical_official_query_v1_sort_rows_invalid")
    materialized = tuple(rows)
    codes: list[str] = []
    values_by_code: dict[str, dict[str, SortValue | None]] = {}
    for row in materialized:
        if not isinstance(row, DailyMarketTechnicalOfficialDispositionJoinedRowV1):
            _fail("technical_official_query_v1_sort_rows_invalid")
        payload = _fact_payload(row.fact_row, query)
        code = cast(str, payload["stock_code"])
        if code in values_by_code:
            _fail("technical_official_query_v1_duplicate_stock")
        _validate_joined_technical_row(
            query, fact_payload=payload, technical_row=row.technical_row
        )
        codes.append(code)
        values: dict[str, SortValue | None] = {}
        for clause in query.sort_clauses:
            values[clause.field] = _sort_value_for_row(
                clause.field,
                code=code,
                payload=payload,
                technical_row=row.technical_row,
                decision_date=query.decision_date,
                method_rule_keys=query.technical_query.method_rule_keys,
            )
        values_by_code[code] = values
    if len(codes) > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS:
        _fail("technical_official_query_v1_stock_limit")
    ordered = list(materialized)
    ordered.sort(key=lambda item: item.fact_row.stock_code)
    for clause in reversed(query.sort_clauses):
        known: list[DailyMarketTechnicalOfficialDispositionJoinedRowV1] = []
        nulls: list[DailyMarketTechnicalOfficialDispositionJoinedRowV1] = []
        for item in ordered:
            value = values_by_code[item.fact_row.stock_code][clause.field]
            (nulls if value is None else known).append(item)
        known.sort(
            key=lambda item: cast(SortValue, values_by_code[item.fact_row.stock_code][clause.field]),
            reverse=clause.direction == "desc",
        )
        ordered = known + nulls
    return tuple(ordered)


def _sort_value_for_row(
    field_name: str,
    *,
    code: str,
    payload: Mapping[str, object],
    technical_row: DailyMarketTechnicalParentV4Row | None,
    decision_date: date,
    method_rule_keys: Sequence[str],
) -> SortValue | None:
    _validate_sort_fields((field_name,), method_rule_keys)
    if field_name == "stock_code":
        return code
    if field_name == "decision_date":
        return decision_date
    if field_name in {"latest_feature_date", "raw_row_count"} or any(
        field_name == f"{rule_key}.{metric}"
        for rule_key in method_rule_keys
        for metric in ("ratio", "numerator", "denominator")
    ):
        if technical_row is None:
            return None
        if field_name == "latest_feature_date":
            return technical_row.latest_feature_date
        if field_name == "raw_row_count":
            return technical_row.raw_row_count
        rule_key, metric = field_name.rsplit(".", 1)
        try:
            value = getattr(technical_row.rule(rule_key), metric)
        except (ValueError, AttributeError) as exc:
            raise DailyMarketTechnicalOfficialDispositionQueryV1Error(
                "technical_official_query_v1_technical_sort_value_invalid"
            ) from exc
        if value is None:
            return None
        if not isinstance(value, Decimal) or not value.is_finite():
            _fail("technical_official_query_v1_technical_sort_value_invalid")
        return value
    market = cast(Mapping[str, object], payload["market_assignment"])
    disposal = cast(Mapping[str, object], payload["official_disposal"])
    if field_name == "market_assignment.state":
        value = market.get("state")
        return None if value == "unknown" else cast(str, value)
    if field_name == "market_assignment.snapshot_observed_at":
        return _sort_datetime(market.get("snapshot_observed_at"))
    if field_name == "official_disposal.state":
        value = disposal.get("state")
        return None if value == "unknown" else cast(str, value)
    if field_name == "official_disposal.observed_at":
        return _sort_datetime(disposal.get("observed_at"))
    if field_name == "official_disposal.observed_date":
        value = disposal.get("observed_date")
        return None if value is None else _parse_date(
            value, "technical_official_query_v1_disposal_observed_date_invalid"
        )
    _fail("technical_official_query_v1_sort_key_unsupported")


def _sort_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    parsed = _parse_aware_datetime(value, "technical_official_query_v1_sort_time_invalid")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionSortValueV1:
    """單一排序欄位及其型別化值；不保存來源列或 snapshot。"""

    field: str
    direction: SortDirection
    value: SortValue | None

    def __post_init__(self) -> None:
        _require_text(
            self.field,
            "technical_official_query_v1_compact_sort_field_invalid",
            maximum=128,
        )
        if not isinstance(self.direction, str) or self.direction not in {"asc", "desc"}:
            _fail("technical_official_query_v1_compact_sort_direction_invalid")
        value = self.value
        if value is None:
            return
        if type(value) is str:
            if not value or len(value) > 512:
                _fail("technical_official_query_v1_compact_sort_value_invalid")
        elif type(value) is int:
            if value < 0:
                _fail("technical_official_query_v1_compact_sort_value_invalid")
        elif type(value) is Decimal:
            if not value.is_finite() or len(str(value)) > 1024:
                _fail("technical_official_query_v1_compact_sort_value_invalid")
        elif type(value) is datetime:
            if value.tzinfo is None or value.utcoffset() is None:
                _fail("technical_official_query_v1_compact_sort_value_invalid")
        elif type(value) is date:
            pass
        else:
            _fail("technical_official_query_v1_compact_sort_value_invalid")

    def to_dict(self) -> dict[str, object]:
        value = self.value
        if value is None:
            encoded: dict[str, object] = {"type": "null", "value": None}
        elif type(value) is str:
            encoded = {"type": "str", "value": value}
        elif type(value) is int:
            encoded = {"type": "int", "value": value}
        elif type(value) is Decimal:
            encoded = {"type": "decimal", "value": str(value)}
        elif type(value) is datetime:
            encoded = {"type": "datetime", "value": value.isoformat()}
        elif type(value) is date:
            encoded = {"type": "date", "value": value.isoformat()}
        else:
            _fail("technical_official_query_v1_compact_sort_value_invalid")
        return {"field": self.field, "direction": self.direction, "sort_value": encoded}


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionCompactSortKeyV1:
    """可排序的小型候選；精確來源仍須由上層 reader 核驗。"""

    query_identity_sha256: str
    stock_code: str
    sort_values: tuple[DailyMarketTechnicalOfficialDispositionSortValueV1, ...]
    fact_row_sha256: str
    market_assignment_pin_identity_sha256: str
    official_disposal_pin_identity_sha256: str
    technical_snapshot_identity_sha256: str | None
    technical_source_identity: str | None

    def __post_init__(self) -> None:
        _require_sha256(
            self.query_identity_sha256,
            "technical_official_query_v1_compact_sort_query_identity_invalid",
        )
        if not isinstance(self.stock_code, str) or _STOCK_CODE_RE.fullmatch(self.stock_code) is None:
            _fail("technical_official_query_v1_compact_sort_stock_code_invalid")
        if (
            not isinstance(self.sort_values, tuple)
            or not self.sort_values
            or len(self.sort_values) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_QUERY_V1_MAX_SORT_CLAUSES
        ):
            _fail("technical_official_query_v1_compact_sort_values_invalid")
        if any(not isinstance(item, DailyMarketTechnicalOfficialDispositionSortValueV1) for item in self.sort_values):
            _fail("technical_official_query_v1_compact_sort_values_invalid")
        fields = tuple(item.field for item in self.sort_values)
        if len(fields) != len(set(fields)):
            _fail("technical_official_query_v1_compact_sort_values_invalid")
        _require_sha256(
            self.fact_row_sha256,
            "technical_official_query_v1_compact_sort_fact_identity_invalid",
        )
        _require_sha256(
            self.market_assignment_pin_identity_sha256,
            "technical_official_query_v1_compact_sort_market_pin_invalid",
        )
        _require_sha256(
            self.official_disposal_pin_identity_sha256,
            "technical_official_query_v1_compact_sort_disposal_pin_invalid",
        )
        snapshot_identity = self.technical_snapshot_identity_sha256
        source_identity = self.technical_source_identity
        if (snapshot_identity is None) != (source_identity is None):
            _fail("technical_official_query_v1_compact_sort_technical_identity_invalid")
        if snapshot_identity is not None:
            _require_sha256(
                snapshot_identity,
                "technical_official_query_v1_compact_sort_technical_identity_invalid",
            )
            _require_text(
                source_identity,
                "technical_official_query_v1_compact_sort_technical_identity_invalid",
                maximum=512,
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "daily-market-technical-official-disposition-sort-key.v1",
            "query_identity_sha256": self.query_identity_sha256,
            "stock_code": self.stock_code,
            "sort_values": [item.to_dict() for item in self.sort_values],
            "fact_row_sha256": self.fact_row_sha256,
            "market_assignment_pin_identity_sha256": self.market_assignment_pin_identity_sha256,
            "official_disposal_pin_identity_sha256": self.official_disposal_pin_identity_sha256,
            "technical_snapshot_identity_sha256": self.technical_snapshot_identity_sha256,
            "technical_source_identity": self.technical_source_identity,
        }


def _check_compact_sort_cancel(
    cancel_callback: Callable[[], object] | None,
) -> None:
    if cancel_callback is None:
        return
    if not callable(cancel_callback):
        _fail("technical_official_query_v1_compact_sort_cancel_callback_invalid")
    try:
        cancelled = cancel_callback()
    except Exception as exc:
        raise DailyMarketTechnicalOfficialDispositionQueryV1Error(
            "technical_official_query_v1_compact_sort_cancel_callback_failed"
        ) from exc
    if type(cancelled) is not bool:
        _fail("technical_official_query_v1_compact_sort_cancel_callback_invalid")
    if cancelled:
        _fail("technical_official_query_v1_compact_sort_cancelled")


def project_daily_market_technical_official_disposition_sort_key_v1(
    query: DailyMarketTechnicalOfficialDispositionQueryV1,
    row: DailyMarketTechnicalOfficialDispositionJoinedRowV1,
    *,
    cancel_callback: Callable[[], object] | None = None,
) -> DailyMarketTechnicalOfficialDispositionCompactSortKeyV1:
    """驗單列可檢查欄位後投影 compact key；不替代 source reader 的 exact 驗證。"""

    _check_compact_sort_cancel(cancel_callback)
    if not isinstance(query, DailyMarketTechnicalOfficialDispositionQueryV1):
        _fail("technical_official_query_v1_query_invalid")
    if not isinstance(row, DailyMarketTechnicalOfficialDispositionJoinedRowV1):
        _fail("technical_official_query_v1_sort_rows_invalid")
    payload = _fact_payload(row.fact_row, query)
    code = cast(str, payload["stock_code"])
    _validate_joined_technical_row(
        query,
        fact_payload=payload,
        technical_row=row.technical_row,
    )
    values: list[DailyMarketTechnicalOfficialDispositionSortValueV1] = []
    for clause in query.sort_clauses:
        value = _sort_value_for_row(
            clause.field,
            code=code,
            payload=payload,
            technical_row=row.technical_row,
            decision_date=query.decision_date,
            method_rule_keys=query.technical_query.method_rule_keys,
        )
        values.append(DailyMarketTechnicalOfficialDispositionSortValueV1(
            field=clause.field,
            direction=clause.direction,
            value=value,
        ))
    projected = DailyMarketTechnicalOfficialDispositionCompactSortKeyV1(
        query_identity_sha256=query.query_identity_sha256,
        stock_code=code,
        sort_values=tuple(values),
        fact_row_sha256=hashlib.sha256(row.fact_row.body_json.encode("utf-8")).hexdigest(),
        market_assignment_pin_identity_sha256=query.market_assignment_pin_identity_sha256,
        official_disposal_pin_identity_sha256=query.official_disposal_pin_identity_sha256,
        technical_snapshot_identity_sha256=(
            row.technical_row.snapshot_identity_sha256 if row.technical_row is not None else None
        ),
        technical_source_identity=(
            row.technical_row.source_identity if row.technical_row is not None else None
        ),
    )
    _check_compact_sort_cancel(cancel_callback)
    return projected


def _validate_compact_sort_value_for_field(
    field_name: str,
    value: SortValue | None,
    *,
    method_rule_keys: Sequence[str],
) -> None:
    _validate_sort_fields((field_name,), method_rule_keys)
    if value is None:
        return
    if field_name == "stock_code" or field_name in _MARKET_ASSIGNMENT_FIELDS | _OFFICIAL_DISPOSAL_FIELDS:
        if field_name in {"market_assignment.snapshot_observed_at", "official_disposal.observed_at"}:
            if type(value) is not datetime or value.tzinfo is not timezone.utc:
                _fail("technical_official_query_v1_compact_sort_value_type_mismatch")
        elif field_name == "official_disposal.observed_date":
            if type(value) is not date:
                _fail("technical_official_query_v1_compact_sort_value_type_mismatch")
        elif type(value) is not str:
            _fail("technical_official_query_v1_compact_sort_value_type_mismatch")
        elif (
            field_name == "market_assignment.state" and value not in _MARKET_STATE_ORDER[:-1]
        ) or (
            field_name == "official_disposal.state" and value not in _DISPOSAL_STATE_ORDER[:-1]
        ):
            _fail("technical_official_query_v1_compact_sort_value_invalid")
        return
    if field_name == "decision_date" or field_name == "latest_feature_date":
        if type(value) is not date:
            _fail("technical_official_query_v1_compact_sort_value_type_mismatch")
        return
    if field_name == "raw_row_count":
        if type(value) is not int or value < 0:
            _fail("technical_official_query_v1_compact_sort_value_type_mismatch")
        return
    if field_name.rsplit(".", 1)[-1] in {"ratio", "numerator", "denominator"}:
        if type(value) is not Decimal or not value.is_finite():
            _fail("technical_official_query_v1_compact_sort_value_type_mismatch")
        return
    _fail("technical_official_query_v1_compact_sort_value_type_mismatch")


def sort_daily_market_technical_official_disposition_sort_keys_v1(
    query: DailyMarketTechnicalOfficialDispositionQueryV1,
    sort_keys: Sequence[DailyMarketTechnicalOfficialDispositionCompactSortKeyV1],
    *,
    cancel_callback: Callable[[], object] | None = None,
) -> tuple[DailyMarketTechnicalOfficialDispositionCompactSortKeyV1, ...]:
    """排序完整 compact key 集；不保存 joined rows，超預算或取消即失敗。"""

    _check_compact_sort_cancel(cancel_callback)
    if not isinstance(query, DailyMarketTechnicalOfficialDispositionQueryV1):
        _fail("technical_official_query_v1_query_invalid")
    if isinstance(sort_keys, (str, bytes)) or not isinstance(sort_keys, Sequence):
        _fail("technical_official_query_v1_compact_sort_keys_invalid")
    if len(sort_keys) > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS:
        _fail("technical_official_query_v1_stock_limit")
    bounded_keys: list[DailyMarketTechnicalOfficialDispositionCompactSortKeyV1] = []
    for index, item in enumerate(sort_keys):
        if index % _COMPACT_SORT_CANCEL_CHECK_INTERVAL == 0:
            _check_compact_sort_cancel(cancel_callback)
        bounded_keys.append(item)
        if len(bounded_keys) > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS:
            _fail("technical_official_query_v1_stock_limit")
    materialized = bounded_keys
    expected_signature = tuple((item.field, item.direction) for item in query.sort_clauses)
    seen_codes: set[str] = set()
    total_bytes = 0
    for index, item in enumerate(materialized):
        if index % _COMPACT_SORT_CANCEL_CHECK_INTERVAL == 0:
            _check_compact_sort_cancel(cancel_callback)
        if not isinstance(item, DailyMarketTechnicalOfficialDispositionCompactSortKeyV1):
            _fail("technical_official_query_v1_compact_sort_keys_invalid")
        validated_values: list[DailyMarketTechnicalOfficialDispositionSortValueV1] = []
        if not isinstance(item.sort_values, tuple):
            _fail("technical_official_query_v1_compact_sort_values_invalid")
        for value in item.sort_values:
            if not isinstance(value, DailyMarketTechnicalOfficialDispositionSortValueV1):
                _fail("technical_official_query_v1_compact_sort_values_invalid")
            validated_values.append(DailyMarketTechnicalOfficialDispositionSortValueV1(
                field=value.field,
                direction=value.direction,
                value=value.value,
            ))
        item = DailyMarketTechnicalOfficialDispositionCompactSortKeyV1(
            query_identity_sha256=item.query_identity_sha256,
            stock_code=item.stock_code,
            sort_values=tuple(validated_values),
            fact_row_sha256=item.fact_row_sha256,
            market_assignment_pin_identity_sha256=item.market_assignment_pin_identity_sha256,
            official_disposal_pin_identity_sha256=item.official_disposal_pin_identity_sha256,
            technical_snapshot_identity_sha256=item.technical_snapshot_identity_sha256,
            technical_source_identity=item.technical_source_identity,
        )
        if item.query_identity_sha256 != query.query_identity_sha256:
            _fail("technical_official_query_v1_compact_sort_query_mismatch")
        if item.market_assignment_pin_identity_sha256 != query.market_assignment_pin_identity_sha256:
            _fail("technical_official_query_v1_compact_sort_market_pin_mismatch")
        if item.official_disposal_pin_identity_sha256 != query.official_disposal_pin_identity_sha256:
            _fail("technical_official_query_v1_compact_sort_disposal_pin_mismatch")
        if item.stock_code in seen_codes:
            _fail("technical_official_query_v1_duplicate_stock")
        seen_codes.add(item.stock_code)
        signature = tuple((value.field, value.direction) for value in item.sort_values)
        if signature != expected_signature:
            _fail("technical_official_query_v1_compact_sort_clause_mismatch")
        for clause_value in item.sort_values:
            _validate_compact_sort_value_for_field(
                clause_value.field,
                clause_value.value,
                method_rule_keys=query.technical_query.method_rule_keys,
            )
            if clause_value.field == "stock_code" and clause_value.value != item.stock_code:
                _fail("technical_official_query_v1_compact_sort_value_identity_mismatch")
            if clause_value.field == "decision_date" and clause_value.value != query.decision_date:
                _fail("technical_official_query_v1_compact_sort_value_date_mismatch")
            if (
                clause_value.field == "latest_feature_date"
                and clause_value.value is not None
                and cast(date, clause_value.value) > query.decision_date
            ):
                _fail("technical_official_query_v1_compact_sort_future_feature_date")
            if (
                clause_value.field in {
                    "market_assignment.snapshot_observed_at",
                    "official_disposal.observed_at",
                }
                and clause_value.value is not None
                and cast(datetime, clause_value.value) > query.decision_cutoff.astimezone(timezone.utc)
            ):
                _fail("technical_official_query_v1_compact_sort_future_observation")
            if (
                clause_value.field == "official_disposal.observed_date"
                and clause_value.value is not None
                and cast(date, clause_value.value) > query.decision_cutoff.astimezone(_TAIPEI).date()
            ):
                _fail("technical_official_query_v1_compact_sort_future_observation")
        encoded_size = len(_canonical_json_bytes(item.to_dict())) + 1
        total_bytes += encoded_size
        if total_bytes > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPACT_SORT_MAX_BYTES:
            _fail("technical_official_query_v1_compact_sort_byte_limit")
        materialized[index] = item
    _check_compact_sort_cancel(cancel_callback)

    stock_code_key_calls = 0

    def checked_stock_code(item: DailyMarketTechnicalOfficialDispositionCompactSortKeyV1) -> str:
        nonlocal stock_code_key_calls
        if stock_code_key_calls % _COMPACT_SORT_CANCEL_CHECK_INTERVAL == 0:
            _check_compact_sort_cancel(cancel_callback)
        stock_code_key_calls += 1
        return item.stock_code

    ordered = materialized
    ordered.sort(key=checked_stock_code)
    for clause_index in range(len(expected_signature) - 1, -1, -1):
        _check_compact_sort_cancel(cancel_callback)
        clause = query.sort_clauses[clause_index]
        known: list[DailyMarketTechnicalOfficialDispositionCompactSortKeyV1] = []
        nulls: list[DailyMarketTechnicalOfficialDispositionCompactSortKeyV1] = []
        for index, item in enumerate(ordered):
            if index % _COMPACT_SORT_CANCEL_CHECK_INTERVAL == 0:
                _check_compact_sort_cancel(cancel_callback)
            sort_value = item.sort_values[clause_index].value
            (nulls if sort_value is None else known).append(item)

        value_key_calls = 0

        def checked_value(item: DailyMarketTechnicalOfficialDispositionCompactSortKeyV1) -> SortValue:
            nonlocal value_key_calls
            if value_key_calls % _COMPACT_SORT_CANCEL_CHECK_INTERVAL == 0:
                _check_compact_sort_cancel(cancel_callback)
            value_key_calls += 1
            sort_value = item.sort_values[clause_index].value
            if sort_value is None:
                _fail("technical_official_query_v1_compact_sort_value_invalid")
            return sort_value

        known.sort(key=checked_value, reverse=clause.direction == "desc")
        known.extend(nulls)
        ordered = known
        _check_compact_sort_cancel(cancel_callback)
    result = tuple(ordered)
    _check_compact_sort_cancel(cancel_callback)
    return result
