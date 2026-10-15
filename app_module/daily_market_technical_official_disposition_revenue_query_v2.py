"""F17、四均線與月營收 YoY 的全母體 current-only 複合查詢契約。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import TYPE_CHECKING, Any, Literal, NoReturn, cast

from app_module.daily_market_monthly_revenue_yoy_index_v2 import (
    DailyMarketMonthlyRevenueYoyIndexSessionV2,
    DailyMarketMonthlyRevenueYoyIndexEntryV2,
)
from app_module.daily_market_technical_official_disposition_ma_query_v1 import (
    DailyMarketTechnicalOfficialDispositionMaQueryV1,
    DailyMarketTechnicalOfficialDispositionMaSortClauseV1,
    DailyMarketTechnicalOfficialDispositionMaQueryV1Error,
    CombineMode,
    UnknownPolicy,
    SortDirection,
    _validate_sort_fields,
)
from app_module.daily_market_technical_official_disposition_query_v1 import (
    ConditionTruth,
    DailyMarketTechnicalOfficialDispositionFactRowV1,
    DailyMarketTechnicalOfficialDispositionFilterEvaluationV1,
    DailyMarketTechnicalOfficialDispositionQueryV1,
    DailyMarketTechnicalOfficialDispositionSortValueV1,
)
from app_module.daily_market_technical_parent_v4_query import DailyMarketTechnicalParentV4Row
from app_module.daily_market_technical_universe_ma_alignment_query_v1 import (
    DailyMarketTechnicalMaAlignmentCompactEntryV1,
)
from decision_module.factors.selection_monthly_revenue_yoy_v2 import (
    SELECTION_REVENUE_YOY_METHOD_ID,
    SELECTION_REVENUE_YOY_METHOD_VERSION,
    SelectionMonthlyRevenueYoYFactV2,
    evaluate_monthly_revenue_yoy_min_v2,
)

if TYPE_CHECKING:
    from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
        DailyMarketTechnicalOfficialDispositionReadSessionV1,
    )


DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_QUERY_SCHEMA_V2 = (
    "daily-market-technical-official-disposition-revenue-query.v2"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_PAGE_REQUEST_SCHEMA_V2 = (
    "daily-market-technical-official-disposition-revenue-page-request.v2"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_MAX_QUERY_BYTES_V2 = 32 * 1024 * 1024
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_MAX_ROWS_V2 = 100_000
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_MAX_PAGE_SIZE_V2 = 256
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_MAX_SORT_CLAUSES_V2 = 34
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_MAX_COMPACT_BYTES_V2 = 64 * 1024 * 1024
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_MAX_JSON_DEPTH_V2 = 32

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STOCK_CODE_RE = re.compile(r"^[A-Z0-9]{1,16}$")
_TRUTH_ORDER: tuple[ConditionTruth, ...] = (
    "match", "no_match", "unknown", "not_evaluated", "not_applicable",
)
_SOURCE_PIN_KEYS = (
    "bundle_output_root", "bundle_identity_sha256", "bundle_manifest_sha256",
    "p01_read_session_identity_sha256", "p01_selection_identity_sha256",
    "p01_query_spec_identity_sha256", "p01_generation_identity_sha256",
    "p01_plan_identity_sha256", "p01_plan_sha256", "p01_receipt_identity_sha256",
    "p01_receipt_sha256", "p01_cohort_identity_sha256",
    "p01_source_clock_identity_sha256", "p01_method_contracts_sha256",
    "ma_read_session_identity_sha256", "ma_index_identity_sha256",
    "ma_source_request_identity_sha256", "ma_index_source_clock_identity_sha256",
    "market_assignment_pin_identity_sha256", "official_disposal_pin_identity_sha256",
    "monthly_yoy_read_session_identity_sha256", "monthly_yoy_index_identity_sha256",
    "monthly_yoy_finished_cohort_identity_sha256", "monthly_yoy_source_clock_identity_sha256",
    "decision_date", "decision_cutoff", "monthly_yoy_cutoff",
    "ma_method_id", "ma_method_version", "monthly_yoy_method_id",
    "monthly_yoy_method_version",
    "monthly_source_reference_external_sha256",
    "monthly_source_content_identity_sha256",
    "monthly_cohort_sha256",
    "monthly_availability_status",
)
_SOURCE_PIN_KEYS_V2 = _SOURCE_PIN_KEYS
_RESULT_SEAL_V2 = object()
_PAGE_SEAL_V2 = object()
_ANCHOR_ISSUER_V2 = object()

Truth = ConditionTruth


class DailyMarketTechnicalOfficialDispositionRevenueQueryV2Error(ValueError):
    """F12/F17/MA 複合查詢的穩定拒絕碼。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"technical_official_revenue_query_v2_{code}")


def _fail(code: str) -> NoReturn:
    raise DailyMarketTechnicalOfficialDispositionRevenueQueryV2Error(code)


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
        raise DailyMarketTechnicalOfficialDispositionRevenueQueryV2Error("json_invalid") from exc


def _reject_float_tree(value: object, *, depth: int = 0) -> None:
    if depth > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_MAX_JSON_DEPTH_V2:
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
            if depth > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_MAX_JSON_DEPTH_V2:
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
    except DailyMarketTechnicalOfficialDispositionRevenueQueryV2Error:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalOfficialDispositionRevenueQueryV2Error("json_invalid") from exc


def _strict_cancel(callback: Callable[[], object] | None) -> None:
    if callback is None:
        return
    if not callable(callback):
        _fail("cancel_callback_invalid")
    try:
        value = callback()
    except Exception as exc:
        raise DailyMarketTechnicalOfficialDispositionRevenueQueryV2Error("cancel_check_failed") from exc
    if type(value) is not bool:
        _fail("cancel_callback_invalid")
    if value:
        _fail("cancelled")


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if type(value) is not Decimal or not value.is_finite():
        _fail("decimal_invalid")
    exponent = value.as_tuple().exponent
    if (
        type(exponent) is not int
        or len(value.as_tuple().digits) > 64
        or abs(exponent) > 128
    ):
        _fail("decimal_bounds_invalid")
    if value == 0:
        return "0"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _parse_decimal_text(value: object) -> Decimal | None:
    if value is None:
        return None
    if type(value) is not str or len(value) > 256:
        _fail("minimum_yoy_percent_invalid")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise DailyMarketTechnicalOfficialDispositionRevenueQueryV2Error(
            "minimum_yoy_percent_invalid"
        ) from exc
    if not parsed.is_finite() or _decimal_text(parsed) != value:
        _fail("minimum_yoy_percent_noncanonical")
    return parsed


def _parse_ma_query(raw: object) -> DailyMarketTechnicalOfficialDispositionMaQueryV1:
    if type(raw) is not str or len(raw.encode("utf-8")) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_MAX_QUERY_BYTES_V2:
        _fail("ma_query_invalid")
    try:
        query = DailyMarketTechnicalOfficialDispositionMaQueryV1.from_json(raw)
    except (ValueError, UnicodeError) as exc:
        raise DailyMarketTechnicalOfficialDispositionRevenueQueryV2Error("ma_query_invalid") from exc
    if query.to_json() != raw:
        _fail("ma_query_noncanonical")
    if (
        query.condition_combine_mode != "AND"
        or query.unknown_policy != "include"
        or len(query.sort_clauses) != 1
        or query.sort_clauses[0].field != "stock_code"
        or query.sort_clauses[0].direction != "asc"
    ):
        _fail("nested_ma_query_not_neutral")
    return query


def _normalize_policy(
    *,
    active_groups: tuple[bool, bool, bool],
    combine_mode: object,
    unknown_policy: object,
) -> tuple[CombineMode, UnknownPolicy]:
    if combine_mode not in {"AND", "OR"} or unknown_policy not in {"include", "exclude", "only"}:
        _fail("condition_policy_invalid")
    count = sum(active_groups)
    normalized_combine = cast(CombineMode, combine_mode if count >= 2 else "AND")
    normalized_unknown = cast(UnknownPolicy, unknown_policy if count else "include")
    if unknown_policy == "only" and count == 0:
        _fail("unknown_only_without_condition")
    if combine_mode != normalized_combine or unknown_policy != normalized_unknown:
        _fail("condition_policy_noncanonical")
    return normalized_combine, normalized_unknown


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2:
    """外層 V2 全域排序欄；unknown/null 固定排在尾端。"""

    field: str
    direction: SortDirection

    def __post_init__(self) -> None:
        if type(self.field) is not str or not self.field or len(self.field) > 128:
            _fail("sort_clause_invalid")
        if type(self.direction) is not str or self.direction not in {"asc", "desc"}:
            _fail("sort_clause_invalid")

    def to_dict(self) -> dict[str, str]:
        return {"field": self.field, "direction": self.direction}

    @classmethod
    def from_dict(
        cls, value: object,
    ) -> DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2:
        if not isinstance(value, Mapping) or set(value) != {"field", "direction"}:
            _fail("sort_clause_invalid")
        field_name = value.get("field")
        direction = value.get("direction")
        if type(field_name) is not str or type(direction) is not str:
            _fail("sort_clause_invalid")
        return cls(field_name, cast(SortDirection, direction))


def _validate_sort_clauses(
    ma_query: DailyMarketTechnicalOfficialDispositionMaQueryV1,
    clauses: tuple[DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2, ...],
) -> None:
    if (
        not clauses
        or len(clauses) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_MAX_SORT_CLAUSES_V2
        or any(type(item) is not DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2 for item in clauses)
        or len({item.field for item in clauses}) != len(clauses)
    ):
        _fail("sort_clauses_invalid")
    revenue_clauses = tuple(
        item for item in clauses
        if item.field not in {"monthly_revenue_yoy_percent", "ma_alignment_state"}
    )
    if revenue_clauses:
        try:
            _validate_sort_fields(
                ma_query.f17_query,
                tuple(
                    DailyMarketTechnicalOfficialDispositionMaSortClauseV1(
                        item.field, item.direction,
                    )
                    for item in revenue_clauses
                ),
            )
        except DailyMarketTechnicalOfficialDispositionMaQueryV1Error as exc:
            raise DailyMarketTechnicalOfficialDispositionRevenueQueryV2Error("sort_field_invalid") from exc
    stock_positions = [index for index, item in enumerate(clauses) if item.field == "stock_code"]
    if stock_positions and (stock_positions != [len(clauses) - 1] or clauses[-1].direction != "asc"):
        _fail("stock_code_tiebreak_invalid")


def _query_body_v2(query: DailyMarketTechnicalOfficialDispositionRevenueQueryV2) -> dict[str, object]:
    return {
        "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_QUERY_SCHEMA_V2,
        "ma_query_json": query.ma_query_json,
        "monthly_yoy_read_session_identity_sha256": query.monthly_yoy_read_session_identity_sha256,
        "monthly_yoy_index_identity_sha256": query.monthly_yoy_index_identity_sha256,
        "monthly_yoy_finished_cohort_identity_sha256": query.monthly_yoy_finished_cohort_identity_sha256,
        "monthly_yoy_source_clock_identity_sha256": query.monthly_yoy_source_clock_identity_sha256,
        "monthly_yoy_cutoff": query.monthly_yoy_cutoff,
        "monthly_yoy_method_id": query.monthly_yoy_method_id,
        "monthly_yoy_method_version": query.monthly_yoy_method_version,
        "monthly_source_reference_external_sha256": query.monthly_source_reference_external_sha256,
        "monthly_source_content_identity_sha256": query.monthly_source_content_identity_sha256,
        "monthly_cohort_sha256": query.monthly_cohort_sha256,
        "monthly_availability_status": query.monthly_availability_status,
        "minimum_yoy_percent": _decimal_text(query.minimum_yoy_percent),
        "condition_combine_mode": query.condition_combine_mode,
        "unknown_policy": query.unknown_policy,
        "sort_clauses": [item.to_dict() for item in query.sort_clauses],
    }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionRevenueQueryV2:
    """全母體條件與排序；頁碼另由 PageRequest 指定。"""

    ma_query_json: str
    monthly_yoy_read_session_identity_sha256: str
    monthly_yoy_index_identity_sha256: str
    monthly_yoy_finished_cohort_identity_sha256: str
    monthly_yoy_source_clock_identity_sha256: str
    monthly_yoy_cutoff: str
    monthly_yoy_method_id: str
    monthly_yoy_method_version: str
    monthly_source_reference_external_sha256: str
    monthly_source_content_identity_sha256: str
    monthly_cohort_sha256: str
    monthly_availability_status: Literal["cohort_hour_bound"]
    minimum_yoy_percent: Decimal | None
    condition_combine_mode: CombineMode
    unknown_policy: UnknownPolicy
    sort_clauses: tuple[DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2, ...]
    query_identity_sha256: str

    def __post_init__(self) -> None:
        ma_query = _parse_ma_query(self.ma_query_json)
        for value in (
            self.monthly_yoy_read_session_identity_sha256,
            self.monthly_yoy_index_identity_sha256,
            self.monthly_yoy_finished_cohort_identity_sha256,
            self.monthly_yoy_source_clock_identity_sha256,
            self.monthly_source_reference_external_sha256,
            self.monthly_source_content_identity_sha256,
            self.monthly_cohort_sha256,
        ):
            _require_sha(value, "query_source_identity_invalid")
        if (
            type(self.monthly_availability_status) is not str
            or self.monthly_availability_status != "cohort_hour_bound"
        ):
            _fail("query_monthly_availability_invalid")
        if (
            self.monthly_yoy_method_id != SELECTION_REVENUE_YOY_METHOD_ID
            or self.monthly_yoy_method_version != SELECTION_REVENUE_YOY_METHOD_VERSION
        ):
            _fail("query_method_unsupported")
        if type(self.monthly_yoy_cutoff) is not str:
            _fail("query_cutoff_invalid")
        try:
            parsed_cutoff = datetime.fromisoformat(self.monthly_yoy_cutoff)
        except ValueError as exc:
            raise DailyMarketTechnicalOfficialDispositionRevenueQueryV2Error(
                "query_cutoff_invalid"
            ) from exc
        if (
            parsed_cutoff.tzinfo is None
            or parsed_cutoff.utcoffset() is None
            or parsed_cutoff.astimezone(timezone.utc).isoformat() != self.monthly_yoy_cutoff
            or parsed_cutoff.astimezone(timezone.utc)
            != ma_query.f17_query.decision_cutoff.astimezone(timezone.utc)
        ):
            _fail("query_cutoff_noncanonical")
        if self.minimum_yoy_percent is not None:
            if type(self.minimum_yoy_percent) is not Decimal or not self.minimum_yoy_percent.is_finite():
                _fail("minimum_yoy_percent_invalid")
            _decimal_text(self.minimum_yoy_percent)
        if type(self.sort_clauses) is not tuple:
            _fail("sort_clauses_invalid")
        active = (
            bool(ma_query.f17_query.technical_query.rule_state_filters),
            ma_query.ma_states is not None,
            self.minimum_yoy_percent is not None,
        )
        normalized_mode, normalized_policy = _normalize_policy(
            active_groups=active,
            combine_mode=self.condition_combine_mode,
            unknown_policy=self.unknown_policy,
        )
        if (
            self.condition_combine_mode != normalized_mode
            or self.unknown_policy != normalized_policy
        ):
            _fail("condition_policy_noncanonical")
        _validate_sort_clauses(ma_query, self.sort_clauses)
        _require_sha(self.query_identity_sha256, "query_identity_invalid")
        if _sha256_json(_query_body_v2(self)) != self.query_identity_sha256:
            _fail("query_identity_mismatch")

    @classmethod
    def create(
        cls,
        ma_query: DailyMarketTechnicalOfficialDispositionMaQueryV1,
        monthly_index_session: DailyMarketMonthlyRevenueYoyIndexSessionV2,
        *,
        minimum_yoy_percent: Decimal | None = None,
        condition_combine_mode: CombineMode = "AND",
        unknown_policy: UnknownPolicy = "include",
        sort_clauses: Sequence[DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2] = (),
    ) -> DailyMarketTechnicalOfficialDispositionRevenueQueryV2:
        if type(ma_query) is not DailyMarketTechnicalOfficialDispositionMaQueryV1:
            _fail("ma_query_type_invalid")
        if type(monthly_index_session) is not DailyMarketMonthlyRevenueYoyIndexSessionV2:
            _fail("monthly_index_session_not_reader_issued")
        ma_json = ma_query.to_json()
        _parse_ma_query(ma_json)
        try:
            index = monthly_index_session.index
            index.require_reader_issued(monthly_index_session)
            entries = monthly_index_session.validated_entries()
            source_clock = index.source_clock
        except (ValueError, TypeError, AttributeError) as exc:
            raise DailyMarketTechnicalOfficialDispositionRevenueQueryV2Error(
                "monthly_index_not_reader_issued"
            ) from exc
        cutoff = ma_query.f17_query.decision_cutoff.astimezone(timezone.utc)
        if (
            index.decision_cutoff.astimezone(timezone.utc) != cutoff
            or source_clock is None
            or tuple(entry.stock_code for entry in entries) != tuple(monthly_index_session.declared_stock_codes)
            or tuple(entry.stock_code for entry in entries) != index.declared_stock_codes
            or index.source_scope != "current_observed_only"
            or index.availability_status != "cohort_hour_bound"
            or index.historical_pit_eligible is not False
            or index.formal_pit_eligible is not False
        ):
            _fail("monthly_cutoff_source_mismatch")
        if minimum_yoy_percent is not None:
            if type(minimum_yoy_percent) is not Decimal or not minimum_yoy_percent.is_finite():
                _fail("minimum_yoy_percent_invalid")
            _decimal_text(minimum_yoy_percent)
        active = (
            bool(ma_query.f17_query.technical_query.rule_state_filters),
            ma_query.ma_states is not None,
            minimum_yoy_percent is not None,
        )
        normalized_mode, normalized_policy = _normalize_policy(
            active_groups=active,
            combine_mode=condition_combine_mode,
            unknown_policy=unknown_policy,
        )
        clauses = tuple(sort_clauses)
        if not clauses:
            clauses = (DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2("stock_code", "asc"),)
        _validate_sort_clauses(ma_query, clauses)
        body = {
            "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_QUERY_SCHEMA_V2,
            "ma_query_json": ma_json,
            "monthly_yoy_read_session_identity_sha256": monthly_index_session.read_session_identity_sha256,
            "monthly_yoy_index_identity_sha256": index.index_identity_sha256,
            "monthly_yoy_finished_cohort_identity_sha256": index.finished_cohort_identity_sha256,
            "monthly_yoy_source_clock_identity_sha256": index.source_clock.identity_sha256,
            "monthly_yoy_cutoff": index.decision_cutoff.astimezone(timezone.utc).isoformat(),
            "monthly_yoy_method_id": SELECTION_REVENUE_YOY_METHOD_ID,
            "monthly_yoy_method_version": SELECTION_REVENUE_YOY_METHOD_VERSION,
            "monthly_source_reference_external_sha256": index.source_reference_external_sha256,
            "monthly_source_content_identity_sha256": index.source_content_identity_sha256,
            "monthly_cohort_sha256": index.cohort_pin.cohort_sha256,
            "monthly_availability_status": "cohort_hour_bound",
            "minimum_yoy_percent": _decimal_text(minimum_yoy_percent),
            "condition_combine_mode": normalized_mode,
            "unknown_policy": normalized_policy,
            "sort_clauses": [item.to_dict() for item in clauses],
        }
        return cls.from_dict({**body, "query_identity_sha256": _sha256_json(body)})

    @property
    def ma_query(self) -> DailyMarketTechnicalOfficialDispositionMaQueryV1:
        return _parse_ma_query(self.ma_query_json)

    @property
    def f17_query(self) -> DailyMarketTechnicalOfficialDispositionQueryV1:
        return self.ma_query.f17_query

    def to_dict(self) -> dict[str, object]:
        body = _query_body_v2(self)
        if _sha256_json(body) != self.query_identity_sha256:
            _fail("query_identity_mismatch")
        return {**body, "query_identity_sha256": self.query_identity_sha256}

    def to_json(self) -> str:
        raw = _canonical_json_bytes(self.to_dict())
        if len(raw) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_MAX_QUERY_BYTES_V2:
            _fail("query_byte_limit")
        return raw.decode("utf-8")

    @classmethod
    def from_dict(cls, value: object) -> DailyMarketTechnicalOfficialDispositionRevenueQueryV2:
        expected = {
            "schema_version", "ma_query_json", "monthly_yoy_read_session_identity_sha256",
            "monthly_yoy_index_identity_sha256", "monthly_yoy_finished_cohort_identity_sha256",
            "monthly_yoy_source_clock_identity_sha256", "monthly_yoy_cutoff",
            "monthly_yoy_method_id", "monthly_yoy_method_version",
            "monthly_source_reference_external_sha256", "monthly_source_content_identity_sha256",
            "monthly_cohort_sha256", "monthly_availability_status", "minimum_yoy_percent",
            "condition_combine_mode", "unknown_policy", "sort_clauses", "query_identity_sha256",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            _fail("query_fields_invalid")
        payload = dict(value)
        if payload.get("schema_version") != DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_QUERY_SCHEMA_V2:
            _fail("query_schema_unsupported")
        ma_json = payload.get("ma_query_json")
        ma_query = _parse_ma_query(ma_json)
        identities = (
            "monthly_yoy_read_session_identity_sha256", "monthly_yoy_index_identity_sha256",
            "monthly_yoy_finished_cohort_identity_sha256", "monthly_yoy_source_clock_identity_sha256",
        )
        for key in identities:
            _require_sha(payload.get(key), "query_source_identity_invalid")
        if (
            payload.get("monthly_yoy_method_id") != SELECTION_REVENUE_YOY_METHOD_ID
            or payload.get("monthly_yoy_method_version") != SELECTION_REVENUE_YOY_METHOD_VERSION
        ):
            _fail("query_method_unsupported")
        cutoff = payload.get("monthly_yoy_cutoff")
        if not isinstance(cutoff, str):
            _fail("query_cutoff_invalid")
        try:
            parsed_cutoff = datetime.fromisoformat(cutoff)
        except ValueError as exc:
            raise DailyMarketTechnicalOfficialDispositionRevenueQueryV2Error("query_cutoff_invalid") from exc
        if parsed_cutoff.tzinfo is None or parsed_cutoff.utcoffset() is None or parsed_cutoff.astimezone(timezone.utc).isoformat() != cutoff:
            _fail("query_cutoff_noncanonical")
        minimum = _parse_decimal_text(payload.get("minimum_yoy_percent"))
        active = (
            bool(ma_query.f17_query.technical_query.rule_state_filters),
            ma_query.ma_states is not None,
            minimum is not None,
        )
        mode = payload.get("condition_combine_mode")
        policy = payload.get("unknown_policy")
        normalized_mode, normalized_policy = _normalize_policy(
            active_groups=active,
            combine_mode=mode,
            unknown_policy=policy,
        )
        for key in (
            "monthly_source_reference_external_sha256",
            "monthly_source_content_identity_sha256",
            "monthly_cohort_sha256",
        ):
            _require_sha(payload.get(key), "query_source_identity_invalid")
        if payload.get("monthly_availability_status") != "cohort_hour_bound":
            _fail("query_monthly_availability_invalid")
        raw_clauses = payload.get("sort_clauses")
        if not isinstance(raw_clauses, list):
            _fail("sort_clauses_invalid")
        clauses = tuple(
            DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2.from_dict(item)
            for item in raw_clauses
        )
        _validate_sort_clauses(ma_query, clauses)
        query = cls(
            ma_query_json=cast(str, ma_json),
            monthly_yoy_read_session_identity_sha256=cast(str, payload[identities[0]]),
            monthly_yoy_index_identity_sha256=cast(str, payload[identities[1]]),
            monthly_yoy_finished_cohort_identity_sha256=cast(str, payload[identities[2]]),
            monthly_yoy_source_clock_identity_sha256=cast(str, payload[identities[3]]),
            monthly_yoy_cutoff=cutoff,
            monthly_yoy_method_id=cast(str, payload["monthly_yoy_method_id"]),
            monthly_yoy_method_version=cast(str, payload["monthly_yoy_method_version"]),
            monthly_source_reference_external_sha256=cast(str, payload["monthly_source_reference_external_sha256"]),
            monthly_source_content_identity_sha256=cast(str, payload["monthly_source_content_identity_sha256"]),
            monthly_cohort_sha256=cast(str, payload["monthly_cohort_sha256"]),
            monthly_availability_status="cohort_hour_bound",
            minimum_yoy_percent=minimum,
            condition_combine_mode=normalized_mode,
            unknown_policy=normalized_policy,
            sort_clauses=clauses,
            query_identity_sha256=_require_sha(payload.get("query_identity_sha256"), "query_identity_invalid"),
        )
        if _sha256_json(_query_body_v2(query)) != query.query_identity_sha256:
            _fail("query_identity_mismatch")
        if query.to_json() != _canonical_json_bytes(payload).decode("utf-8"):
            _fail("query_noncanonical")
        return query

    @classmethod
    def from_json(cls, raw: bytes | str) -> DailyMarketTechnicalOfficialDispositionRevenueQueryV2:
        return cls.from_dict(_parse_json(raw, maximum=DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_MAX_QUERY_BYTES_V2))


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2:
    query_json: str
    page_index: int
    page_size: int
    request_identity_sha256: str

    @classmethod
    def create(
        cls,
        query: DailyMarketTechnicalOfficialDispositionRevenueQueryV2,
        *,
        page_index: int,
        page_size: int,
    ) -> DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2:
        if type(query) is not DailyMarketTechnicalOfficialDispositionRevenueQueryV2:
            _fail("page_query_invalid")
        query.to_json()
        _validate_page(page_index, page_size)
        body = {
            "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_PAGE_REQUEST_SCHEMA_V2,
            "query_identity_sha256": query.query_identity_sha256,
            "page_index": page_index,
            "page_size": page_size,
        }
        return cls(query.to_json(), page_index, page_size, _sha256_json(body))

    @property
    def query(self) -> DailyMarketTechnicalOfficialDispositionRevenueQueryV2:
        return DailyMarketTechnicalOfficialDispositionRevenueQueryV2.from_json(self.query_json)

    def to_dict(self) -> dict[str, object]:
        query = self.query
        _validate_page(self.page_index, self.page_size)
        if self.query_json != query.to_json():
            _fail("page_query_noncanonical")
        body = {
            "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_PAGE_REQUEST_SCHEMA_V2,
            "query_identity_sha256": query.query_identity_sha256,
            "page_index": self.page_index,
            "page_size": self.page_size,
        }
        if _sha256_json(body) != self.request_identity_sha256:
            _fail("page_request_identity_mismatch")
        return {**body, "query_json": self.query_json, "request_identity_sha256": self.request_identity_sha256}

    def to_json(self) -> str:
        return _canonical_json_bytes(self.to_dict()).decode("utf-8")

    @classmethod
    def from_json(cls, raw: bytes | str) -> DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2:
        payload = _parse_json(raw, maximum=DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_MAX_QUERY_BYTES_V2)
        required = {"schema_version", "query_identity_sha256", "page_index", "page_size", "query_json", "request_identity_sha256"}
        if not isinstance(payload, Mapping) or set(payload) != required or payload.get("schema_version") != DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_PAGE_REQUEST_SCHEMA_V2:
            _fail("page_request_fields_invalid")
        query = DailyMarketTechnicalOfficialDispositionRevenueQueryV2.from_json(cast(str, payload["query_json"]))
        if payload.get("query_identity_sha256") != query.query_identity_sha256:
            _fail("page_request_query_identity_mismatch")
        request = cls.create(query, page_index=cast(int, payload["page_index"]), page_size=cast(int, payload["page_size"]))
        if request.request_identity_sha256 != payload.get("request_identity_sha256") or request.to_json() != (raw.decode("utf-8") if isinstance(raw, bytes) else raw):
            _fail("page_request_noncanonical")
        return request


def _validate_page(page_index: object, page_size: object) -> None:
    if type(page_index) is not int or not 0 <= page_index <= 1_000_000:
        _fail("page_index_invalid")
    if type(page_size) is not int or not 1 <= page_size <= DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_MAX_PAGE_SIZE_V2:
        _fail("page_size_invalid")


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionRevenueCountsV2:
    base_f17_counts: object
    monthly_source_state_counts: tuple[tuple[str, int], ...]
    monthly_projected_state_counts: tuple[tuple[str, int], ...]
    technical_truth_counts: tuple[tuple[str, int], ...]
    ma_truth_counts: tuple[tuple[str, int], ...]
    revenue_truth_counts: tuple[tuple[str, int], ...]
    composite_truth_counts: tuple[tuple[str, int], ...]
    eligible_truth_counts: tuple[tuple[str, int], ...]
    hard_eligible_count: int
    visible_count: int
    unknown_policy_included_count: int
    unknown_policy_excluded_count: int

    def __post_init__(self) -> None:
        declared = _declared_count(self.base_f17_counts)
        if not _valid_counts(self.monthly_source_state_counts, ("blocked", "observed", "unknown"), declared):
            _fail("counts_monthly_states_invalid")
        if not _valid_counts(self.monthly_projected_state_counts, ("observed", "unknown"), declared):
            _fail("counts_monthly_projected_states_invalid")
        for name, values in (
            ("technical", self.technical_truth_counts),
            ("ma", self.ma_truth_counts),
            ("revenue", self.revenue_truth_counts),
            ("composite", self.composite_truth_counts),
        ):
            if not _valid_counts(values, _TRUTH_ORDER, declared):
                _fail(f"counts_{name}_truth_invalid")
        if not _valid_counts(self.eligible_truth_counts, _TRUTH_ORDER, self.hard_eligible_count):
            _fail("counts_eligible_truth_invalid")
        for number in (
            self.hard_eligible_count, self.visible_count,
            self.unknown_policy_included_count, self.unknown_policy_excluded_count,
        ):
            if type(number) is not int or not 0 <= number <= declared:
                _fail("counts_value_invalid")
        if (
            self.visible_count > self.hard_eligible_count
            or self.unknown_policy_included_count > self.visible_count
            or self.unknown_policy_included_count + self.unknown_policy_excluded_count > declared
        ):
            _fail("counts_relationship_invalid")

    @property
    def declared_count(self) -> int:
        return _declared_count(self.base_f17_counts)

    @property
    def matching_count(self) -> int:
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
        base = getattr(self.base_f17_counts, "to_dict", None)
        if not callable(base):
            _fail("counts_base_invalid")
        return {
            "base_f17_counts": base(),
            "monthly_source_state_counts": dict(self.monthly_source_state_counts),
            "monthly_projected_state_counts": dict(self.monthly_projected_state_counts),
            "technical_truth_counts": dict(self.technical_truth_counts),
            "ma_truth_counts": dict(self.ma_truth_counts),
            "revenue_truth_counts": dict(self.revenue_truth_counts),
            "composite_truth_counts": dict(self.composite_truth_counts),
            "eligible_truth_counts": dict(self.eligible_truth_counts),
            "hard_eligible_count": self.hard_eligible_count,
            "visible_count": self.visible_count,
            "predicate_match_count": self.predicate_match_count,
            "predicate_unknown_count": self.predicate_unknown_count,
            "predicate_not_evaluated_count": self.predicate_not_evaluated_count,
            "unknown_policy_included_count": self.unknown_policy_included_count,
            "unknown_policy_excluded_count": self.unknown_policy_excluded_count,
        }


def _declared_count(counts: object) -> int:
    population = getattr(counts, "population", None)
    declared = getattr(population, "declared_count", None)
    if type(declared) is not int or not 0 <= declared <= DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_MAX_ROWS_V2:
        _fail("counts_base_invalid")
    return declared


def _valid_counts(values: object, expected: tuple[str, ...], total: int) -> bool:
    if type(values) is not tuple or len(values) != len(expected):
        return False
    pairs: list[tuple[str, int]] = []
    for item in values:
        if type(item) is not tuple or len(item) != 2 or type(item[0]) is not str or type(item[1]) is not int or item[1] < 0:
            return False
        pairs.append(cast(tuple[str, int], item))
    return tuple(key for key, _ in pairs) == expected and sum(value for _, value in pairs) == total


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionRevenueSortKeyV2:
    query_identity_sha256: str
    stock_code: str
    sort_values: tuple[DailyMarketTechnicalOfficialDispositionSortValueV1, ...]
    fact_row_sha256: str
    technical_snapshot_identity_sha256: str | None
    technical_source_identity: str | None
    ma_evidence_identity_sha256: str | None
    monthly_result_identity_sha256: str
    monthly_fact_identity_sha256: str

    def __post_init__(self) -> None:
        _require_sha(self.query_identity_sha256, "sort_key_query_invalid")
        if type(self.stock_code) is not str or _STOCK_CODE_RE.fullmatch(self.stock_code) is None:
            _fail("sort_key_stock_invalid")
        if (
            type(self.sort_values) is not tuple
            or not self.sort_values
            or len(self.sort_values) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_MAX_SORT_CLAUSES_V2
            or any(type(item) is not DailyMarketTechnicalOfficialDispositionSortValueV1 for item in self.sort_values)
        ):
            _fail("sort_key_values_invalid")
        for value, code in (
            (self.fact_row_sha256, "sort_key_fact_invalid"),
            (self.monthly_result_identity_sha256, "sort_key_monthly_result_invalid"),
            (self.monthly_fact_identity_sha256, "sort_key_monthly_fact_invalid"),
        ):
            _require_sha(value, code)
        if (self.technical_snapshot_identity_sha256 is None) != (self.technical_source_identity is None):
            _fail("sort_key_technical_identity_invalid")
        if self.technical_snapshot_identity_sha256 is not None:
            _require_sha(self.technical_snapshot_identity_sha256, "sort_key_technical_identity_invalid")
        if self.ma_evidence_identity_sha256 is not None:
            _require_sha(self.ma_evidence_identity_sha256, "sort_key_ma_identity_invalid")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "daily-market-technical-official-disposition-revenue-sort-key.v2",
            "query_identity_sha256": self.query_identity_sha256,
            "stock_code": self.stock_code,
            "sort_values": [item.to_dict() for item in self.sort_values],
            "fact_row_sha256": self.fact_row_sha256,
            "technical_snapshot_identity_sha256": self.technical_snapshot_identity_sha256,
            "technical_source_identity": self.technical_source_identity,
            "ma_evidence_identity_sha256": self.ma_evidence_identity_sha256,
            "monthly_result_identity_sha256": self.monthly_result_identity_sha256,
            "monthly_fact_identity_sha256": self.monthly_fact_identity_sha256,
        }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionRevenueResultRowV2:
    fact_row: DailyMarketTechnicalOfficialDispositionFactRowV1
    technical_row: DailyMarketTechnicalParentV4Row | None
    ma_entry: DailyMarketTechnicalMaAlignmentCompactEntryV1 | None
    monthly_entry: DailyMarketMonthlyRevenueYoyIndexEntryV2
    filter_evaluation: DailyMarketTechnicalOfficialDispositionFilterEvaluationV1
    technical_condition_truth: Truth
    ma_condition_truth: Truth
    revenue_condition_truth: Truth
    composite_condition_truth: Truth
    hard_filter_match: bool
    included_by_unknown_policy: bool
    row_identity_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.fact_row) is not DailyMarketTechnicalOfficialDispositionFactRowV1
            or type(self.filter_evaluation) is not DailyMarketTechnicalOfficialDispositionFilterEvaluationV1
            or (self.technical_row is not None and type(self.technical_row) is not DailyMarketTechnicalParentV4Row)
            or (self.ma_entry is not None and type(self.ma_entry) is not DailyMarketTechnicalMaAlignmentCompactEntryV1)
            or type(self.monthly_entry) is not DailyMarketMonthlyRevenueYoyIndexEntryV2
        ):
            _fail("result_row_type_invalid")
        code = self.fact_row.stock_code
        if (
            self.filter_evaluation.stock_code != code
            or (self.technical_row is not None and self.technical_row.stock_code != code)
            or (self.ma_entry is not None and self.ma_entry.stock_code != code)
            or self.monthly_entry.stock_code != code
            or any(value not in _TRUTH_ORDER for value in (
                self.technical_condition_truth,
                self.ma_condition_truth,
                self.revenue_condition_truth,
                self.composite_condition_truth,
            ))
            or type(self.hard_filter_match) is not bool
            or type(self.included_by_unknown_policy) is not bool
        ):
            _fail("result_row_invalid")
        _require_sha(self.row_identity_sha256, "result_row_identity_invalid")

    @property
    def stock_code(self) -> str:
        return self.fact_row.stock_code

    @property
    def revenue_fact(self) -> SelectionMonthlyRevenueYoYFactV2:
        return self.monthly_entry.projected_fact

    def to_dict(self) -> dict[str, object]:
        return {
            "stock_code": self.stock_code,
            "fact_row": self.fact_row.to_dict(),
            "technical_row": None if self.technical_row is None else self.technical_row.to_dict(),
            "ma_entry": None if self.ma_entry is None else self.ma_entry.to_dict(),
            "monthly_entry": self.monthly_entry.to_dict(),
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
            "revenue_condition_truth": self.revenue_condition_truth,
            "composite_condition_truth": self.composite_condition_truth,
            "hard_filter_match": self.hard_filter_match,
            "included_by_unknown_policy": self.included_by_unknown_policy,
            "scope": "current_only",
            "official_available_at": None,
            "monthly_official_available_at": None,
            "historical_pit_eligible": False,
            "row_identity_sha256": self.row_identity_sha256,
        }


def _rows_sha_v2(rows: Sequence[DailyMarketTechnicalOfficialDispositionRevenueResultRowV2]) -> str:
    return _sha256_json([item.to_dict() for item in rows])


def _result_identity_v2(
    *,
    query: DailyMarketTechnicalOfficialDispositionRevenueQueryV2,
    source_pins: tuple[tuple[str, str], ...],
    counts: DailyMarketTechnicalOfficialDispositionRevenueCountsV2,
    ordered_keys: tuple[DailyMarketTechnicalOfficialDispositionRevenueSortKeyV2, ...],
    result_status: str,
    official_coverage_status: str,
) -> str:
    return _sha256_json({
        "schema_version": "daily-market-technical-official-disposition-revenue-result.v2",
        "query_identity_sha256": query.query_identity_sha256,
        "source_pins": [[key, value] for key, value in source_pins],
        "counts": counts.to_dict(),
        "ordered_keys_sha256": _sha256_json([item.to_dict() for item in ordered_keys]),
        "ordered_codes_sha256": _sha256_json([item.stock_code for item in ordered_keys]),
        "result_status": result_status,
        "official_source_coverage_status": official_coverage_status,
        "monthly_source_scope": "current_observed_only",
        "monthly_availability_status": "unknown",
        "monthly_official_available_at": None,
        "historical_pit_eligible": False,
    })


def _source_pins_match_query_v2(
    query: DailyMarketTechnicalOfficialDispositionRevenueQueryV2,
    source_pins: tuple[tuple[str, str], ...],
) -> bool:
    if type(source_pins) is not tuple or len(source_pins) != len(_SOURCE_PIN_KEYS_V2):
        return False
    if any(
        type(pair) is not tuple
        or len(pair) != 2
        or type(pair[0]) is not str
        or type(pair[1]) is not str
        or not pair[1]
        for pair in source_pins
    ):
        return False
    if tuple(pair[0] for pair in source_pins) != _SOURCE_PIN_KEYS_V2:
        return False
    pins = dict(source_pins)
    expected = {
        "monthly_yoy_read_session_identity_sha256": query.monthly_yoy_read_session_identity_sha256,
        "monthly_yoy_index_identity_sha256": query.monthly_yoy_index_identity_sha256,
        "monthly_yoy_finished_cohort_identity_sha256": query.monthly_yoy_finished_cohort_identity_sha256,
        "monthly_yoy_source_clock_identity_sha256": query.monthly_yoy_source_clock_identity_sha256,
        "monthly_yoy_cutoff": query.monthly_yoy_cutoff,
        "monthly_yoy_method_id": query.monthly_yoy_method_id,
        "monthly_yoy_method_version": query.monthly_yoy_method_version,
        "monthly_source_reference_external_sha256": query.monthly_source_reference_external_sha256,
        "monthly_source_content_identity_sha256": query.monthly_source_content_identity_sha256,
        "monthly_cohort_sha256": query.monthly_cohort_sha256,
        "monthly_availability_status": query.monthly_availability_status,
    }
    return all(pins.get(key) == value for key, value in expected.items())


class _ResultAnchorV2:
    identity: str
    keys_sha: str
    counts_sha: str
    pins_sha: str
    read_session: object
    query: object
    subject: object | None
    locked: bool
    __slots__ = ("identity", "keys_sha", "counts_sha", "pins_sha", "read_session", "query", "subject", "locked")

    def __init__(self, identity: str, keys_sha: str, counts_sha: str, pins_sha: str, read_session: object, query: object) -> None:
        for item in (identity, keys_sha, counts_sha, pins_sha):
            _require_sha(item, "result_anchor_invalid")
        object.__setattr__(self, "identity", identity)
        object.__setattr__(self, "keys_sha", keys_sha)
        object.__setattr__(self, "counts_sha", counts_sha)
        object.__setattr__(self, "pins_sha", pins_sha)
        object.__setattr__(self, "read_session", read_session)
        object.__setattr__(self, "query", query)
        object.__setattr__(self, "subject", None)
        object.__setattr__(self, "locked", True)

    def claim(self, subject: object) -> None:
        if self.subject is not None and self.subject is not subject:
            _fail("result_anchor_subject_mismatch")
        if self.subject is None:
            object.__setattr__(self, "subject", subject)

    def can_claim(self, subject: object) -> bool:
        return self.subject is None or self.subject is subject

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "locked", False):
            raise AttributeError("query issuance anchor is immutable")
        object.__setattr__(self, name, value)


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV2:
    query: DailyMarketTechnicalOfficialDispositionRevenueQueryV2
    operation_identity_sha256: str
    ordered_codes_sha256: str
    counts: DailyMarketTechnicalOfficialDispositionRevenueCountsV2
    source_pins: tuple[tuple[str, str], ...]
    ordered_sort_keys: tuple[DailyMarketTechnicalOfficialDispositionRevenueSortKeyV2, ...]
    result_status: Literal["complete", "partial"]
    official_source_coverage_status: Literal["complete", "partial"]
    scope: Literal["current_only"]
    official_available_at: None
    monthly_official_available_at: None
    availability_status: Literal["unknown"]
    historical_pit_eligible: Literal[False]
    _read_session: object = field(repr=False, compare=False)
    _anchor: _ResultAnchorV2 = field(repr=False, compare=False)
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        _validate_result_v2(self)
        self._anchor.claim(self)

    @property
    def visible_count(self) -> int:
        return self.counts.visible_count

    @property
    def matching_count(self) -> int:
        return self.counts.visible_count

    def read_page(
        self,
        page_index: int,
        page_size: int,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalOfficialDispositionRevenueQueryPageV2:
        _strict_cancel(cancel_callback)
        request = DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2.create(
            self.query, page_index=page_index, page_size=page_size,
        )
        return self.read_page_request(request, cancel_callback=cancel_callback)

    def read_page_request(
        self,
        request: DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2 | bytes | str,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalOfficialDispositionRevenueQueryPageV2:
        _strict_cancel(cancel_callback)
        _validate_result_v2(self)
        if isinstance(request, (bytes, str)):
            request = DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2.from_json(request)
        if type(request) is not DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2:
            _fail("page_request_invalid")
        if request.query.query_identity_sha256 != self.query.query_identity_sha256:
            _fail("page_request_query_mismatch")
        reader = getattr(self._read_session, "_materialize_revenue_query_page_v2", None)
        if not callable(reader):
            _fail("read_session_page_reader_unavailable")
        page = cast(Any, reader)(self, request, cancel_callback)
        _strict_cancel(cancel_callback)
        return page


def _validate_result_v2(result: DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV2) -> None:
    try:
        result.query.to_json()
    except (
        DailyMarketTechnicalOfficialDispositionRevenueQueryV2Error,
        ValueError,
        TypeError,
        AttributeError,
    ) as exc:
        raise DailyMarketTechnicalOfficialDispositionRevenueQueryV2Error(
            "result_query_invalid"
        ) from exc
    if (
        type(result.counts) is not DailyMarketTechnicalOfficialDispositionRevenueCountsV2
        or type(result.ordered_sort_keys) is not tuple
        or any(
            type(item) is not DailyMarketTechnicalOfficialDispositionRevenueSortKeyV2
            for item in result.ordered_sort_keys
        )
        or len({item.stock_code for item in result.ordered_sort_keys}) != len(result.ordered_sort_keys)
        or result._seal is not _RESULT_SEAL_V2
        or type(result._anchor) is not _ResultAnchorV2
        or not result._anchor.can_claim(result)
        or result._anchor.read_session is not result._read_session
        or result._anchor.query is not result.query
        or result._anchor.identity != result.operation_identity_sha256
        or not _source_pins_match_query_v2(result.query, result.source_pins)
        or result._anchor.keys_sha != _sha256_json([item.to_dict() for item in result.ordered_sort_keys])
        or result._anchor.counts_sha != _sha256_json(result.counts.to_dict())
        or result._anchor.pins_sha != _sha256_json([[key, value] for key, value in result.source_pins])
        or result.scope != "current_only"
        or result.official_available_at is not None
        or result.monthly_official_available_at is not None
        or result.availability_status != "unknown"
        or result.historical_pit_eligible is not False
        or result.result_status not in {"complete", "partial"}
        or result.official_source_coverage_status not in {"complete", "partial"}
        or result.counts.visible_count != len(result.ordered_sort_keys)
        or result.ordered_codes_sha256 != _sha256_json([item.stock_code for item in result.ordered_sort_keys])
        or _result_identity_v2(
            query=result.query,
            source_pins=result.source_pins,
            counts=result.counts,
            ordered_keys=result.ordered_sort_keys,
            result_status=result.result_status,
            official_coverage_status=result.official_source_coverage_status,
        ) != result.operation_identity_sha256
    ):
        _fail("result_not_reader_issued")


def _issue_result_v2(
    *,
    query: DailyMarketTechnicalOfficialDispositionRevenueQueryV2,
    counts: DailyMarketTechnicalOfficialDispositionRevenueCountsV2,
    source_pins: tuple[tuple[str, str], ...],
    ordered_keys: tuple[DailyMarketTechnicalOfficialDispositionRevenueSortKeyV2, ...],
    result_status: Literal["complete", "partial"],
    official_source_coverage_status: Literal["complete", "partial"],
    read_session: object,
) -> DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV2:
    query.to_json()
    operation = _result_identity_v2(
        query=query,
        source_pins=source_pins,
        counts=counts,
        ordered_keys=ordered_keys,
        result_status=result_status,
        official_coverage_status=official_source_coverage_status,
    )
    return DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV2(
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
        monthly_official_available_at=None,
        availability_status="unknown",
        historical_pit_eligible=False,
        _read_session=read_session,
        _anchor=_ResultAnchorV2(
            operation,
            _sha256_json([item.to_dict() for item in ordered_keys]),
            _sha256_json(counts.to_dict()),
            _sha256_json([[key, value] for key, value in source_pins]),
            read_session,
            query,
        ),
        _seal=_RESULT_SEAL_V2,
    )


class _PageAnchorV2:
    identity: str
    rows_sha: str
    request_sha: str
    result: object
    subject: object | None
    locked: bool
    __slots__ = ("identity", "rows_sha", "request_sha", "result", "subject", "locked")

    def __init__(self, identity: str, rows_sha: str, request_sha: str, result: object) -> None:
        for item in (identity, rows_sha, request_sha):
            _require_sha(item, "page_anchor_invalid")
        object.__setattr__(self, "identity", identity)
        object.__setattr__(self, "rows_sha", rows_sha)
        object.__setattr__(self, "request_sha", request_sha)
        object.__setattr__(self, "result", result)
        object.__setattr__(self, "subject", None)
        object.__setattr__(self, "locked", True)

    def claim(self, subject: object) -> None:
        if self.subject is not None and self.subject is not subject:
            _fail("page_anchor_subject_mismatch")
        if self.subject is None:
            object.__setattr__(self, "subject", subject)

    def can_claim(self, subject: object) -> bool:
        return self.subject is None or self.subject is subject

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "locked", False):
            raise AttributeError("page issuance anchor is immutable")
        object.__setattr__(self, name, value)


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionRevenueQueryPageV2:
    query: DailyMarketTechnicalOfficialDispositionRevenueQueryV2
    request_identity_sha256: str
    operation_identity_sha256: str
    page_identity_sha256: str
    page_index: int
    page_size: int
    page_count: int
    counts: DailyMarketTechnicalOfficialDispositionRevenueCountsV2
    rows: tuple[DailyMarketTechnicalOfficialDispositionRevenueResultRowV2, ...]
    source_pins: tuple[tuple[str, str], ...]
    result_status: Literal["complete", "partial"]
    official_source_coverage_status: Literal["complete", "partial"]
    scope: Literal["current_only"]
    official_available_at: None
    monthly_official_available_at: None
    availability_status: Literal["unknown"]
    historical_pit_eligible: Literal[False]
    _result: DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV2 = field(repr=False, compare=False)
    _anchor: _PageAnchorV2 = field(repr=False, compare=False)
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        _validate_page(self.page_index, self.page_size)
        try:
            expected_request = DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2.create(
                self.query,
                page_index=self.page_index,
                page_size=self.page_size,
            )
        except DailyMarketTechnicalOfficialDispositionRevenueQueryV2Error as exc:
            raise DailyMarketTechnicalOfficialDispositionRevenueQueryV2Error(
                "page_not_reader_issued"
            ) from exc
        if (
            type(self.rows) is not tuple
            or len(self.rows) > self.page_size
            or any(
                type(row) is not DailyMarketTechnicalOfficialDispositionRevenueResultRowV2
                for row in self.rows
            )
            or self._seal is not _PAGE_SEAL_V2
            or type(self._anchor) is not _PageAnchorV2
            or not self._anchor.can_claim(self)
            or self._anchor.result is not self._result
            or self._result.query is not self.query
            or self._anchor.identity != self.page_identity_sha256
            or self._anchor.rows_sha != _rows_sha_v2(self.rows)
            or self._anchor.request_sha != self.request_identity_sha256
            or expected_request.request_identity_sha256 != self.request_identity_sha256
            or self.operation_identity_sha256 != self._result.operation_identity_sha256
            or self.source_pins != self._result.source_pins
            or self.counts != self._result.counts
            or self.result_status != self._result.result_status
            or self.official_source_coverage_status != self._result.official_source_coverage_status
            or self.scope != "current_only"
            or self.official_available_at is not None
            or self.monthly_official_available_at is not None
            or self.availability_status != "unknown"
            or self.historical_pit_eligible is not False
            or self.page_count != (self.counts.visible_count + self.page_size - 1) // self.page_size
        ):
            _fail("page_not_reader_issued")
        _validate_result_v2(self._result)
        self._anchor.claim(self)

    def to_dict(self) -> dict[str, object]:
        self.__post_init__()
        return {
            "schema_version": "daily-market-technical-official-disposition-revenue-page.v2",
            "query_identity_sha256": self.query.query_identity_sha256,
            "request_identity_sha256": self.request_identity_sha256,
            "operation_identity_sha256": self.operation_identity_sha256,
            "page_identity_sha256": self.page_identity_sha256,
            "page_index": self.page_index,
            "page_size": self.page_size,
            "page_count": self.page_count,
            "counts": self.counts.to_dict(),
            "rows": [item.to_dict() for item in self.rows],
            "source_pins": [[key, value] for key, value in self.source_pins],
            "result_status": self.result_status,
            "official_source_coverage_status": self.official_source_coverage_status,
            "scope": self.scope,
            "official_available_at": None,
            "monthly_official_available_at": None,
            "availability_status": "unknown",
            "historical_pit_eligible": False,
        }


def _page_identity_v2(
    *,
    result: DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV2,
    request: DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2,
    rows: tuple[DailyMarketTechnicalOfficialDispositionRevenueResultRowV2, ...],
) -> str:
    return _sha256_json({
        "schema_version": "daily-market-technical-official-disposition-revenue-page.v2",
        "operation_identity_sha256": result.operation_identity_sha256,
        "request_identity_sha256": request.request_identity_sha256,
        "query_identity_sha256": result.query.query_identity_sha256,
        "rows_sha256": _rows_sha_v2(rows),
        "counts_sha256": _sha256_json(result.counts.to_dict()),
        "source_pins_sha256": _sha256_json([[key, value] for key, value in result.source_pins]),
        "result_status": result.result_status,
        "official_source_coverage_status": result.official_source_coverage_status,
        "scope": "current_only",
        "official_available_at": None,
        "monthly_official_available_at": None,
        "historical_pit_eligible": False,
    })


def _issue_page_v2(
    *,
    result: DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV2,
    request: DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2,
    rows: tuple[DailyMarketTechnicalOfficialDispositionRevenueResultRowV2, ...],
) -> DailyMarketTechnicalOfficialDispositionRevenueQueryPageV2:
    _validate_result_v2(result)
    _validate_page_request_for_result_v2(result, request)
    start = request.page_index * request.page_size
    expected_keys = result.ordered_sort_keys[start:start + request.page_size]
    if (
        type(rows) is not tuple
        or any(type(row) is not DailyMarketTechnicalOfficialDispositionRevenueResultRowV2 for row in rows)
        or tuple(row.stock_code for row in rows)
        != tuple(key.stock_code for key in expected_keys)
    ):
        _fail("page_rows_do_not_match_result")
    identity = _page_identity_v2(result=result, request=request, rows=rows)
    anchor = _PageAnchorV2(identity, _rows_sha_v2(rows), request.request_identity_sha256, result)
    page = DailyMarketTechnicalOfficialDispositionRevenueQueryPageV2(
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
        monthly_official_available_at=None,
        availability_status="unknown",
        historical_pit_eligible=False,
        _result=result,
        _anchor=anchor,
        _seal=_PAGE_SEAL_V2,
    )
    anchor.claim(page)
    page.__post_init__()
    return page


def _validate_page_request_for_result_v2(
    result: DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV2,
    request: DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2,
) -> None:
    _validate_result_v2(result)
    if type(request) is not DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2:
        _fail("page_request_invalid")
    expected = DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2.create(
        result.query, page_index=request.page_index, page_size=request.page_size,
    )
    if expected.to_json() != request.to_json():
        _fail("page_request_mismatch")
    page_count = (result.counts.visible_count + request.page_size - 1) // request.page_size
    if (page_count == 0 and request.page_index != 0) or (page_count > 0 and request.page_index >= page_count):
        _fail("page_request_out_of_range")


def sort_revenue_keys_v2(
    query: DailyMarketTechnicalOfficialDispositionRevenueQueryV2,
    keys: Sequence[DailyMarketTechnicalOfficialDispositionRevenueSortKeyV2],
    *,
    cancel_callback: Callable[[], object] | None = None,
) -> tuple[DailyMarketTechnicalOfficialDispositionRevenueSortKeyV2, ...]:
    _strict_cancel(cancel_callback)
    query.to_json()
    if len(keys) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_MAX_ROWS_V2:
        _fail("sort_row_limit")
    expected = tuple((item.field, item.direction) for item in query.sort_clauses)
    seen: set[str] = set()
    materialized: list[DailyMarketTechnicalOfficialDispositionRevenueSortKeyV2] = []
    total_bytes = 0
    for index, key in enumerate(keys):
        if index % 256 == 0:
            _strict_cancel(cancel_callback)
        if (
            type(key) is not DailyMarketTechnicalOfficialDispositionRevenueSortKeyV2
            or key.query_identity_sha256 != query.query_identity_sha256
            or key.stock_code in seen
            or tuple((item.field, item.direction) for item in key.sort_values) != expected
        ):
            _fail("sort_key_mismatch")
        for clause, value in zip(query.sort_clauses, key.sort_values, strict=True):
            if clause.field == "stock_code" and value.value != key.stock_code:
                _fail("sort_key_stock_code_mismatch")
            _validate_sort_scalar(clause.field, value.value)
        seen.add(key.stock_code)
        total_bytes += len(_canonical_json_bytes(key.to_dict())) + 1
        if total_bytes > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_MAX_COMPACT_BYTES_V2:
            _fail("sort_compact_byte_limit")
        materialized.append(key)
    _strict_cancel(cancel_callback)
    materialized.sort(key=lambda item: item.stock_code)
    _strict_cancel(cancel_callback)
    for column in range(len(query.sort_clauses) - 1, -1, -1):
        clause = query.sort_clauses[column]
        known: list[DailyMarketTechnicalOfficialDispositionRevenueSortKeyV2] = []
        nulls: list[DailyMarketTechnicalOfficialDispositionRevenueSortKeyV2] = []
        for index, item in enumerate(materialized):
            if index % 256 == 0:
                _strict_cancel(cancel_callback)
            (nulls if item.sort_values[column].value is None else known).append(item)
        _strict_cancel(cancel_callback)
        known.sort(key=lambda item: cast(Any, item.sort_values[column].value), reverse=clause.direction == "desc")
        _strict_cancel(cancel_callback)
        materialized = known + nulls
    _strict_cancel(cancel_callback)
    return tuple(materialized)


def _validate_sort_scalar(field_name: str, value: object) -> None:
    if value is None:
        return
    if field_name == "monthly_revenue_yoy_percent":
        if type(value) is not Decimal or not value.is_finite():
            _fail("sort_decimal_invalid")
        return
    if field_name == "ma_alignment_state":
        if type(value) is not str or value not in {"match", "no_match"}:
            _fail("sort_ma_state_invalid")
        return
    if field_name in {"stock_code", "market_assignment.state", "official_disposal.state"}:
        if type(value) is not str:
            _fail("sort_text_invalid")
        return
    if field_name in {"decision_date", "latest_feature_date", "official_disposal.observed_date"}:
        if type(value) is not date:
            _fail("sort_date_invalid")
        return
    if field_name in {"market_assignment.snapshot_observed_at", "official_disposal.observed_at"}:
        if type(value) is not datetime or value.tzinfo is not timezone.utc:
            _fail("sort_datetime_invalid")
        return
    if field_name == "raw_row_count":
        if type(value) is not int or value < 0:
            _fail("sort_integer_invalid")
        return
    if "." in field_name:
        if type(value) is not Decimal or not value.is_finite():
            _fail("sort_rule_decimal_invalid")
        return
    _fail("sort_scalar_invalid")


# 簡短別名供同一讀取器的版本化分派使用；具名完整型別仍是正式 API。
RevenueQueryV2 = DailyMarketTechnicalOfficialDispositionRevenueQueryV2
RevenuePageRequestV2 = DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2
RevenueCountsV2 = DailyMarketTechnicalOfficialDispositionRevenueCountsV2
RevenueSortClauseV2 = DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2
SortClauseV2 = DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2
RevenueSortKeyV2 = DailyMarketTechnicalOfficialDispositionRevenueSortKeyV2
RevenueResultRowV2 = DailyMarketTechnicalOfficialDispositionRevenueResultRowV2
RevenueResultV2 = DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV2
RevenuePageV2 = DailyMarketTechnicalOfficialDispositionRevenueQueryPageV2

