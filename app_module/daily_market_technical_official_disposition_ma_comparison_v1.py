"""F17／MA 複合研究跨頁比較的純資料契約與 exact 重開。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import NoReturn, TYPE_CHECKING, cast

from app_module.daily_market_technical_official_disposition_ma_query_v1 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_PAGE_SIZE,
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_QUERY_V1_MAX_BYTES,
    DailyMarketTechnicalOfficialDispositionMaPageRequestV1,
    DailyMarketTechnicalOfficialDispositionMaQueryPageV1,
    DailyMarketTechnicalOfficialDispositionMaQueryV1,
    DailyMarketTechnicalOfficialDispositionMaResultRowV1,
    DailyMarketTechnicalOfficialDispositionMaVerifiedQueryResultV1,
)

if TYPE_CHECKING:
    from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
        DailyMarketTechnicalOfficialDispositionReadSessionV1,
    )


DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_SELECTION_V1_SCHEMA = (
    "daily-market-technical-official-disposition-ma-selection.v1"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_COMPARISON_V1_SCHEMA = (
    "daily-market-technical-official-disposition-ma-comparison.v1"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_COMPARISON_V1_MAX_ITEMS = 5
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_COMPARISON_V1_MAX_BYTES = 64 * 1024 * 1024
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_SELECTION_V1_MAX_ROW_BYTES = 256 * 1024
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_SELECTION_V1_MAX_JSON_DEPTH = 32
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_SOURCE_AVAILABLE_AT = None
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_AVAILABILITY_STATUS = "unknown"
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_HISTORICAL_PIT_ELIGIBLE = False
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_SCOPE = "current_only"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STOCK_CODE_RE = re.compile(r"^[A-Z0-9]{1,16}$")
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
_RESULT_SEAL = object()
_VERIFIED_SELECTION_SEAL = object()
_VERIFIED_COMPARISON_SEAL = object()


class DailyMarketTechnicalOfficialDispositionMaComparisonV1Error(ValueError):
    """MA 比較資料格式或 exact 重開失敗。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise DailyMarketTechnicalOfficialDispositionMaComparisonV1Error(
        f"technical_official_ma_comparison_v1_{code}"
    )


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
            if depth > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_SELECTION_V1_MAX_JSON_DEPTH:
                _fail("json_depth_limit")
        elif char in "]}":
            depth -= 1
            if depth < 0:
                _fail("json_invalid")
    if quoted or escaped or depth != 0:
        _fail("json_invalid")


def _reject_float_tree(value: object, *, depth: int = 0) -> None:
    if depth > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_SELECTION_V1_MAX_JSON_DEPTH:
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
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise DailyMarketTechnicalOfficialDispositionMaComparisonV1Error(
            "technical_official_ma_comparison_v1_json_invalid"
        ) from exc


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail("duplicate_json_key")
        result[key] = value
    return result


def _parse_json(raw: bytes | str, *, maximum_bytes: int, code: str) -> object:
    try:
        encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
        if not isinstance(encoded, bytes) or len(encoded) > maximum_bytes:
            _fail("json_byte_limit")
        text = encoded.decode("utf-8")
        _preflight_depth(text)
        value = json.loads(
            text,
            object_pairs_hook=_unique_pairs,
            parse_float=lambda _value: _fail("float_forbidden"),
            parse_constant=lambda _value: _fail("json_constant_invalid"),
        )
        _reject_float_tree(value)
        if _canonical_json_bytes(value) != encoded:
            _fail("json_noncanonical")
        return value
    except DailyMarketTechnicalOfficialDispositionMaComparisonV1Error:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalOfficialDispositionMaComparisonV1Error(code) from exc


def _require_sha(value: object, code: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail(code)
    return cast(str, value)


def _strict_cancel(callback: Callable[[], object] | None) -> None:
    if callback is None:
        return
    if not callable(callback):
        _fail("cancel_callback_invalid")
    try:
        value = callback()
    except Exception as exc:
        raise DailyMarketTechnicalOfficialDispositionMaComparisonV1Error(
            "technical_official_ma_comparison_v1_cancel_check_failed"
        ) from exc
    if type(value) is not bool:
        _fail("cancel_callback_invalid")
    if value:
        _fail("cancelled")


def _bounded_selections(value: object, *, minimum: int, maximum: int) -> tuple[DailyMarketTechnicalOfficialDispositionMaSelectionV1, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _fail("comparison_selections_invalid")
    result: list[DailyMarketTechnicalOfficialDispositionMaSelectionV1] = []
    try:
        iterator = iter(value)
        for _ in range(maximum + 1):
            try:
                item = next(iterator)
            except StopIteration:
                break
            if type(item) is not DailyMarketTechnicalOfficialDispositionMaSelectionV1:
                _fail("comparison_selections_invalid")
            result.append(item)
    except DailyMarketTechnicalOfficialDispositionMaComparisonV1Error:
        raise
    except Exception as exc:
        raise DailyMarketTechnicalOfficialDispositionMaComparisonV1Error(
            "technical_official_ma_comparison_v1_comparison_selections_invalid"
        ) from exc
    if len(result) < minimum or len(result) > maximum:
        _fail("comparison_count_invalid")
    return tuple(result)


def _parse_query(raw: object) -> DailyMarketTechnicalOfficialDispositionMaQueryV1:
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_QUERY_V1_MAX_BYTES:
        _fail("query_invalid")
    query = DailyMarketTechnicalOfficialDispositionMaQueryV1.from_json(raw)
    if query.to_json() != raw:
        _fail("query_noncanonical")
    return query


def _source_pins_tuple(value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, tuple) or len(value) != len(_SOURCE_PIN_KEYS):
        _fail("source_pins_invalid")
    result: list[tuple[str, str]] = []
    for item in value:
        if (
            not isinstance(item, tuple)
            or len(item) != 2
            or not isinstance(item[0], str)
            or not isinstance(item[1], str)
            or not item[1]
        ):
            _fail("source_pins_invalid")
        result.append((item[0], item[1]))
    if tuple(key for key, _value in result) != _SOURCE_PIN_KEYS:
        _fail("source_pins_invalid")
    pins = dict(result)
    for key, pin in result:
        if key.endswith("_sha256"):
            _require_sha(pin, "source_pin_invalid")
    return tuple(result)


def _validate_source_pins(
    query: DailyMarketTechnicalOfficialDispositionMaQueryV1,
    source_pins: tuple[tuple[str, str], ...],
) -> None:
    pins = dict(_source_pins_tuple(source_pins))
    f17 = query.f17_query
    expected = {
        "bundle_output_root": f17.bundle_output_root,
        "bundle_identity_sha256": f17.bundle_identity_sha256,
        "bundle_manifest_sha256": f17.expected_manifest_sha256,
        "market_assignment_pin_identity_sha256": f17.market_assignment_pin_identity_sha256,
        "official_disposal_pin_identity_sha256": f17.official_disposal_pin_identity_sha256,
        "decision_date": f17.decision_date.isoformat(),
        "decision_cutoff": f17.decision_cutoff.isoformat(),
        "ma_read_session_identity_sha256": query.ma_alignment_read_session_identity_sha256,
        "ma_index_identity_sha256": query.ma_alignment_index_identity_sha256,
        "ma_source_request_identity_sha256": query.ma_source_request_identity_sha256,
        "ma_method_id": query.ma_method_id,
        "ma_method_version": query.ma_method_version,
    }
    if any(pins.get(key) != value for key, value in expected.items()):
        _fail("source_scope_mismatch")


def _row_dict(raw: object, stock_code: str, row_identity: str) -> dict[str, object]:
    if not isinstance(raw, str):
        _fail("row_json_invalid")
    encoded = raw.encode("utf-8")
    if len(encoded) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_SELECTION_V1_MAX_ROW_BYTES:
        _fail("row_byte_limit")
    value = _parse_json(
        encoded,
        maximum_bytes=DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_SELECTION_V1_MAX_ROW_BYTES,
        code="row_json_invalid",
    )
    if not isinstance(value, Mapping) or set(value) != {
        "stock_code", "fact_row", "technical_row", "ma_entry", "filter_evaluation",
        "technical_condition_truth", "ma_condition_truth", "composite_condition_truth",
        "hard_filter_match", "included_by_unknown_policy", "row_identity_sha256",
    }:
        _fail("row_fields_invalid")
    if value.get("stock_code") != stock_code or value.get("row_identity_sha256") != row_identity:
        _fail("row_identity_mismatch")
    if type(value.get("hard_filter_match")) is not bool or type(value.get("included_by_unknown_policy")) is not bool:
        _fail("row_truth_flags_invalid")
    return dict(cast(Mapping[str, object], value))


def _selection_body(selection: DailyMarketTechnicalOfficialDispositionMaSelectionV1) -> dict[str, object]:
    return {
        "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_SELECTION_V1_SCHEMA,
        "query_identity_sha256": selection.query_identity_sha256,
        "page_index": selection.page_index,
        "page_size": selection.page_size,
        "page_request_identity_sha256": selection.page_request_identity_sha256,
        "result_identity_sha256": selection.result_identity_sha256,
        "page_identity_sha256": selection.page_identity_sha256,
        "stock_code": selection.stock_code,
        "row_json": selection.row_json,
        "row_identity_sha256": selection.row_identity_sha256,
        "source_pins": [[key, value] for key, value in selection.source_pins],
        "ma_alignment_read_session_identity_sha256": selection.ma_alignment_read_session_identity_sha256,
        "ma_alignment_index_identity_sha256": selection.ma_alignment_index_identity_sha256,
        "ma_source_request_identity_sha256": selection.ma_source_request_identity_sha256,
        "scope": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_SCOPE,
        "official_available_at": None,
        "availability_status": "unknown",
        "historical_pit_eligible": False,
    }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionMaSelectionV1:
    """跨頁選取錨點；需由其父 DTO 提供唯一 query 才能重建 PageRequest。"""

    query_identity_sha256: str
    page_index: int
    page_size: int
    page_request_identity_sha256: str
    result_identity_sha256: str
    page_identity_sha256: str
    stock_code: str
    row_json: str
    row_identity_sha256: str
    source_pins: tuple[tuple[str, str], ...]
    ma_alignment_read_session_identity_sha256: str
    ma_alignment_index_identity_sha256: str
    ma_source_request_identity_sha256: str
    selection_identity_sha256: str
    schema_version: str = DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_SELECTION_V1_SCHEMA

    def __post_init__(self) -> None:
        if (
            self.schema_version != DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_SELECTION_V1_SCHEMA
            or type(self.page_index) is not int
            or not 0 <= self.page_index <= 1_000_000
            or type(self.page_size) is not int
            or not 1 <= self.page_size <= DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_PAGE_SIZE
            or not isinstance(self.stock_code, str)
            or _STOCK_CODE_RE.fullmatch(self.stock_code) is None
        ):
            _fail("selection_fields_invalid")
        for value in (
            self.query_identity_sha256, self.page_request_identity_sha256,
            self.result_identity_sha256, self.page_identity_sha256,
            self.row_identity_sha256, self.ma_alignment_read_session_identity_sha256,
            self.ma_alignment_index_identity_sha256, self.ma_source_request_identity_sha256,
            self.selection_identity_sha256,
        ):
            _require_sha(value, "selection_sha_invalid")
        _row_dict(self.row_json, self.stock_code, self.row_identity_sha256)
        pins = _source_pins_tuple(self.source_pins)
        pin_map = dict(pins)
        if (
            pin_map["ma_read_session_identity_sha256"] != self.ma_alignment_read_session_identity_sha256
            or pin_map["ma_index_identity_sha256"] != self.ma_alignment_index_identity_sha256
            or pin_map["ma_source_request_identity_sha256"] != self.ma_source_request_identity_sha256
        ):
            _fail("selection_source_pin_mismatch")
        if self.selection_identity_sha256 != _sha256_json(_selection_body(self)):
            _fail("selection_identity_mismatch")

    @classmethod
    def from_page(
        cls,
        page: DailyMarketTechnicalOfficialDispositionMaQueryPageV1,
        stock_code: str,
    ) -> DailyMarketTechnicalOfficialDispositionMaSelectionV1:
        if type(page) is not DailyMarketTechnicalOfficialDispositionMaQueryPageV1:
            _fail("selection_page_type_invalid")
        # page.to_dict() 重驗 reader-issued page anchor 與完整列身份。
        page.to_dict()
        query = page.query
        request = DailyMarketTechnicalOfficialDispositionMaPageRequestV1.create(
            query, page_index=page.page_index, page_size=page.page_size,
        )
        row = next((item for item in page.rows if item.stock_code == stock_code), None)
        if row is None:
            _fail("selection_stock_not_in_page")
        source_pins = _source_pins_tuple(page.source_pins)
        _validate_source_pins(query, source_pins)
        body = {
            "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_SELECTION_V1_SCHEMA,
            "query_identity_sha256": query.query_identity_sha256,
            "page_index": page.page_index,
            "page_size": page.page_size,
            "page_request_identity_sha256": request.request_identity_sha256,
            "result_identity_sha256": page.operation_identity_sha256,
            "page_identity_sha256": page.page_identity_sha256,
            "stock_code": stock_code,
            "row_json": _canonical_json_bytes(row.to_dict()).decode("utf-8"),
            "row_identity_sha256": row.row_identity_sha256,
            "source_pins": [[key, value] for key, value in source_pins],
            "ma_alignment_read_session_identity_sha256": query.ma_alignment_read_session_identity_sha256,
            "ma_alignment_index_identity_sha256": query.ma_alignment_index_identity_sha256,
            "ma_source_request_identity_sha256": query.ma_source_request_identity_sha256,
            "scope": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_SCOPE,
            "official_available_at": None,
            "availability_status": "unknown",
            "historical_pit_eligible": False,
        }
        return cls(
            query_identity_sha256=query.query_identity_sha256,
            page_index=page.page_index,
            page_size=page.page_size,
            page_request_identity_sha256=request.request_identity_sha256,
            result_identity_sha256=page.operation_identity_sha256,
            page_identity_sha256=page.page_identity_sha256,
            stock_code=stock_code,
            row_json=cast(str, body["row_json"]),
            row_identity_sha256=row.row_identity_sha256,
            source_pins=source_pins,
            ma_alignment_read_session_identity_sha256=query.ma_alignment_read_session_identity_sha256,
            ma_alignment_index_identity_sha256=query.ma_alignment_index_identity_sha256,
            ma_source_request_identity_sha256=query.ma_source_request_identity_sha256,
            selection_identity_sha256=_sha256_json(body),
        )

    @classmethod
    def from_dict(cls, payload: object) -> DailyMarketTechnicalOfficialDispositionMaSelectionV1:
        expected = {
            "schema_version", "query_identity_sha256", "page_index", "page_size",
            "page_request_identity_sha256", "result_identity_sha256", "page_identity_sha256",
            "stock_code", "row_json", "row_identity_sha256", "source_pins",
            "ma_alignment_read_session_identity_sha256", "ma_alignment_index_identity_sha256",
            "ma_source_request_identity_sha256", "scope", "official_available_at",
            "availability_status", "historical_pit_eligible", "selection_identity_sha256",
        }
        if not isinstance(payload, Mapping) or set(payload) != expected:
            _fail("selection_fields_invalid")
        if (
            payload.get("scope") != "current_only"
            or payload.get("official_available_at") is not None
            or payload.get("availability_status") != "unknown"
            or payload.get("historical_pit_eligible") is not False
        ):
            _fail("selection_qualification_invalid")
        raw_pins = payload.get("source_pins")
        if not isinstance(raw_pins, list):
            _fail("selection_source_pins_invalid")
        pins: list[tuple[str, str]] = []
        for item in raw_pins:
            if not isinstance(item, list) or len(item) != 2 or not all(isinstance(v, str) for v in item):
                _fail("selection_source_pins_invalid")
            pins.append((cast(str, item[0]), cast(str, item[1])))
        result = cls(
            query_identity_sha256=cast(str, payload["query_identity_sha256"]),
            page_index=cast(int, payload["page_index"]),
            page_size=cast(int, payload["page_size"]),
            page_request_identity_sha256=cast(str, payload["page_request_identity_sha256"]),
            result_identity_sha256=cast(str, payload["result_identity_sha256"]),
            page_identity_sha256=cast(str, payload["page_identity_sha256"]),
            stock_code=cast(str, payload["stock_code"]),
            row_json=cast(str, payload["row_json"]),
            row_identity_sha256=cast(str, payload["row_identity_sha256"]),
            source_pins=tuple(pins),
            ma_alignment_read_session_identity_sha256=cast(str, payload["ma_alignment_read_session_identity_sha256"]),
            ma_alignment_index_identity_sha256=cast(str, payload["ma_alignment_index_identity_sha256"]),
            ma_source_request_identity_sha256=cast(str, payload["ma_source_request_identity_sha256"]),
            selection_identity_sha256=cast(str, payload["selection_identity_sha256"]),
            schema_version=cast(str, payload["schema_version"]),
        )
        return result

    def to_dict(self) -> dict[str, object]:
        return {**_selection_body(self), "selection_identity_sha256": self.selection_identity_sha256}


def _comparison_body(
    query_json: str,
    selections: tuple[DailyMarketTechnicalOfficialDispositionMaSelectionV1, ...],
) -> dict[str, object]:
    return {
        "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_COMPARISON_V1_SCHEMA,
        "query_json": query_json,
        "selections": [item.to_dict() for item in selections],
        "source_pins": [[key, value] for key, value in selections[0].source_pins],
        "ma_alignment_read_session_identity_sha256": selections[0].ma_alignment_read_session_identity_sha256,
        "ma_alignment_index_identity_sha256": selections[0].ma_alignment_index_identity_sha256,
        "ma_source_request_identity_sha256": selections[0].ma_source_request_identity_sha256,
        "scope": "current_only",
        "official_available_at": None,
        "availability_status": "unknown",
        "historical_pit_eligible": False,
    }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionMaComparisonV1:
    """一份未重新核驗的跨頁比較請求；不代表 fresh source qualification。"""

    query_json: str
    selections: tuple[DailyMarketTechnicalOfficialDispositionMaSelectionV1, ...]
    comparison_identity_sha256: str
    schema_version: str = DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_COMPARISON_V1_SCHEMA

    def __post_init__(self) -> None:
        query = _parse_query(self.query_json)
        if (
            self.schema_version != DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_COMPARISON_V1_SCHEMA
            or not isinstance(self.selections, tuple)
            or not 2 <= len(self.selections) <= DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_COMPARISON_V1_MAX_ITEMS
            or any(type(item) is not DailyMarketTechnicalOfficialDispositionMaSelectionV1 for item in self.selections)
            or len({item.stock_code for item in self.selections}) != len(self.selections)
            or any(item.query_identity_sha256 != query.query_identity_sha256 for item in self.selections)
            or len({item.result_identity_sha256 for item in self.selections}) != 1
            or len({item.source_pins for item in self.selections}) != 1
            or len({item.ma_alignment_read_session_identity_sha256 for item in self.selections}) != 1
            or len({item.ma_alignment_index_identity_sha256 for item in self.selections}) != 1
            or len({item.ma_source_request_identity_sha256 for item in self.selections}) != 1
            or self.comparison_identity_sha256 != _sha256_json(
                _comparison_body(self.query_json, self.selections)
            )
        ):
            _fail("comparison_identity_invalid")
        for item in self.selections:
            request = DailyMarketTechnicalOfficialDispositionMaPageRequestV1.create(
                query, page_index=item.page_index, page_size=item.page_size,
            )
            if request.request_identity_sha256 != item.page_request_identity_sha256:
                _fail("comparison_request_identity_mismatch")
        if len(_canonical_json_bytes(self.to_dict())) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_COMPARISON_V1_MAX_BYTES:
            _fail("comparison_byte_limit")

    @classmethod
    def create(
        cls,
        query: DailyMarketTechnicalOfficialDispositionMaQueryV1,
        selections: Sequence[DailyMarketTechnicalOfficialDispositionMaSelectionV1],
    ) -> DailyMarketTechnicalOfficialDispositionMaComparisonV1:
        if type(query) is not DailyMarketTechnicalOfficialDispositionMaQueryV1:
            _fail("comparison_query_type_invalid")
        query_json = query.to_json()
        values = _bounded_selections(
            selections,
            minimum=2,
            maximum=DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_COMPARISON_V1_MAX_ITEMS,
        )
        provisional = _comparison_body(query_json, values)
        return cls(
            query_json=query_json,
            selections=values,
            comparison_identity_sha256=_sha256_json(provisional),
        )

    @classmethod
    def from_dict(cls, payload: object) -> DailyMarketTechnicalOfficialDispositionMaComparisonV1:
        expected = {
            "schema_version", "query_json", "selections", "source_pins",
            "ma_alignment_read_session_identity_sha256", "ma_alignment_index_identity_sha256",
            "ma_source_request_identity_sha256", "scope", "official_available_at",
            "availability_status", "historical_pit_eligible", "comparison_identity_sha256",
        }
        if not isinstance(payload, Mapping) or set(payload) != expected:
            _fail("comparison_fields_invalid")
        if (
            payload.get("scope") != "current_only"
            or payload.get("official_available_at") is not None
            or payload.get("availability_status") != "unknown"
            or payload.get("historical_pit_eligible") is not False
        ):
            _fail("comparison_qualification_invalid")
        raw = payload.get("selections")
        if not isinstance(raw, list):
            _fail("comparison_selections_invalid")
        selections = tuple(DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_dict(item) for item in raw)
        result = cls(
            query_json=cast(str, payload.get("query_json")),
            selections=selections,
            comparison_identity_sha256=cast(str, payload.get("comparison_identity_sha256")),
            schema_version=cast(str, payload.get("schema_version")),
        )
        if result.to_dict() != dict(payload):
            _fail("comparison_noncanonical")
        return result

    @classmethod
    def from_json(cls, raw: bytes | str) -> DailyMarketTechnicalOfficialDispositionMaComparisonV1:
        payload = _parse_json(
            raw,
            maximum_bytes=DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_COMPARISON_V1_MAX_BYTES,
            code="comparison_json_invalid",
        )
        result = cls.from_dict(payload)
        if _canonical_json_bytes(result.to_dict()) != (raw.encode("utf-8") if isinstance(raw, str) else raw):
            _fail("comparison_noncanonical")
        return result

    def to_dict(self) -> dict[str, object]:
        return {
            **_comparison_body(self.query_json, self.selections),
            "comparison_identity_sha256": self.comparison_identity_sha256,
        }

    def to_json(self) -> str:
        raw = _canonical_json_bytes(self.to_dict())
        if len(raw) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_COMPARISON_V1_MAX_BYTES:
            _fail("comparison_byte_limit")
        return raw.decode("utf-8")


class _VerifiedSelectionAnchor:
    __slots__ = ("selection", "page", "row", "session", "result", "subject")
    selection: DailyMarketTechnicalOfficialDispositionMaSelectionV1
    page: DailyMarketTechnicalOfficialDispositionMaQueryPageV1
    row: DailyMarketTechnicalOfficialDispositionMaResultRowV1
    session: object
    result: DailyMarketTechnicalOfficialDispositionMaVerifiedQueryResultV1
    subject: object | None

    def __init__(self, selection: DailyMarketTechnicalOfficialDispositionMaSelectionV1,
                 page: DailyMarketTechnicalOfficialDispositionMaQueryPageV1,
                 row: DailyMarketTechnicalOfficialDispositionMaResultRowV1,
                 session: object, result: DailyMarketTechnicalOfficialDispositionMaVerifiedQueryResultV1) -> None:
        object.__setattr__(self, "selection", selection)
        object.__setattr__(self, "page", page)
        object.__setattr__(self, "row", row)
        object.__setattr__(self, "session", session)
        object.__setattr__(self, "result", result)
        object.__setattr__(self, "subject", None)

    def claim(self, subject: object) -> None:
        if self.subject is not None and self.subject is not subject:
            _fail("verified_selection_already_claimed")
        object.__setattr__(self, "subject", subject)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("verified MA selection anchor is immutable")


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionMaVerifiedSelectionV1:
    """只有以保存來源 exact 重開並重核列頁後才由 reader 簽發的資料。"""

    selection: DailyMarketTechnicalOfficialDispositionMaSelectionV1
    page: DailyMarketTechnicalOfficialDispositionMaQueryPageV1
    row: DailyMarketTechnicalOfficialDispositionMaResultRowV1
    _session: object = field(repr=False, compare=False)
    _result: DailyMarketTechnicalOfficialDispositionMaVerifiedQueryResultV1 = field(repr=False, compare=False)
    _anchor: _VerifiedSelectionAnchor = field(repr=False, compare=False)
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            self._seal is not _VERIFIED_SELECTION_SEAL
            or type(self._anchor) is not _VerifiedSelectionAnchor
            or (self._anchor.subject is not None and self._anchor.subject is not self)
            or self._anchor.selection is not self.selection
            or self._anchor.page is not self.page
            or self._anchor.row is not self.row
            or self._anchor.session is not self._session
            or self._anchor.result is not self._result
            or self.page.operation_identity_sha256 != self.selection.result_identity_sha256
            or self.page.page_identity_sha256 != self.selection.page_identity_sha256
            or self.row.stock_code != self.selection.stock_code
            or self.row.row_identity_sha256 != self.selection.row_identity_sha256
            or _canonical_json_bytes(self.row.to_dict()).decode("utf-8") != self.selection.row_json
        ):
            _fail("verified_selection_invalid")
        self._anchor.claim(self)


class _VerifiedComparisonAnchor:
    __slots__ = ("comparison", "items", "subject")
    comparison: DailyMarketTechnicalOfficialDispositionMaComparisonV1
    items: tuple[DailyMarketTechnicalOfficialDispositionMaVerifiedSelectionV1, ...]
    subject: object | None

    def __init__(self, comparison: DailyMarketTechnicalOfficialDispositionMaComparisonV1,
                 items: tuple[DailyMarketTechnicalOfficialDispositionMaVerifiedSelectionV1, ...]) -> None:
        object.__setattr__(self, "comparison", comparison)
        object.__setattr__(self, "items", items)
        object.__setattr__(self, "subject", None)

    def claim(self, subject: object) -> None:
        if self.subject is not None and self.subject is not subject:
            _fail("verified_comparison_already_claimed")
        object.__setattr__(self, "subject", subject)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("verified MA comparison anchor is immutable")


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionMaVerifiedComparisonV1:
    comparison: DailyMarketTechnicalOfficialDispositionMaComparisonV1
    columns: tuple[DailyMarketTechnicalOfficialDispositionMaVerifiedSelectionV1, ...]
    comparison_identity_sha256: str
    scope: str
    official_available_at: None
    availability_status: str
    historical_pit_eligible: bool
    _anchor: _VerifiedComparisonAnchor = field(repr=False, compare=False)
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            self._seal is not _VERIFIED_COMPARISON_SEAL
            or type(self._anchor) is not _VerifiedComparisonAnchor
            or (self._anchor.subject is not None and self._anchor.subject is not self)
            or self._anchor.comparison is not self.comparison
            or self._anchor.items is not self.columns
            or self.comparison_identity_sha256 != self.comparison.comparison_identity_sha256
            or self.scope != "current_only"
            or self.official_available_at is not None
            or self.availability_status != "unknown"
            or self.historical_pit_eligible is not False
        ):
            _fail("verified_comparison_invalid")
        self._anchor.claim(self)


def _read_daily_market_technical_official_disposition_ma_selections_with_result_v1(
    query: DailyMarketTechnicalOfficialDispositionMaQueryV1,
    selections: Sequence[DailyMarketTechnicalOfficialDispositionMaSelectionV1],
    *,
    cancel_callback: Callable[[], object] | None = None,
) -> tuple[
    tuple[DailyMarketTechnicalOfficialDispositionMaVerifiedSelectionV1, ...],
    DailyMarketTechnicalOfficialDispositionMaVerifiedQueryResultV1,
]:
    """以同一 exact session／完整 global result 重核選取列並保留原結果。"""

    _strict_cancel(cancel_callback)
    if type(query) is not DailyMarketTechnicalOfficialDispositionMaQueryV1:
        _fail("query_type_invalid")
    query_json = query.to_json()
    saved_items = _bounded_selections(
        selections,
        minimum=1,
        maximum=DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_COMPARISON_V1_MAX_ITEMS + 1,
    )
    if len({item.stock_code for item in saved_items}) != len(saved_items):
        _fail("selection_duplicate_stock")
    if any(item.query_identity_sha256 != query.query_identity_sha256 for item in saved_items):
        _fail("selection_query_mismatch")
    for item in saved_items:
        request = DailyMarketTechnicalOfficialDispositionMaPageRequestV1.create(
            query, page_index=item.page_index, page_size=item.page_size,
        )
        if request.request_identity_sha256 != item.page_request_identity_sha256:
            _fail("selection_request_mismatch")
        if item.source_pins != saved_items[0].source_pins:
            _fail("selection_source_mismatch")
    _strict_cancel(cancel_callback)

    from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
        open_daily_market_technical_official_disposition_read_session_v1,
    )

    session = open_daily_market_technical_official_disposition_read_session_v1(
        query.f17_query,
        cancel_callback=cancel_callback,
    )
    _strict_cancel(cancel_callback)
    reopened_query = session.create_ma_query_v1(
        ma_states=query.ma_states,
        condition_combine_mode=query.condition_combine_mode,
        unknown_policy=query.unknown_policy,
        sort_clauses=query.sort_clauses,
    )
    if reopened_query.to_json() != query_json:
        _fail("reopened_query_mismatch")
    result = session.execute_ma_query_v1(reopened_query, cancel_callback=cancel_callback)
    if (
        result.operation_identity_sha256 != saved_items[0].result_identity_sha256
        or result.source_pins != saved_items[0].source_pins
    ):
        _fail("reopened_result_mismatch")

    verified: list[DailyMarketTechnicalOfficialDispositionMaVerifiedSelectionV1 | None] = [None] * len(saved_items)
    page_cache: dict[str, DailyMarketTechnicalOfficialDispositionMaQueryPageV1] = {}
    for index, saved in enumerate(saved_items):
        _strict_cancel(cancel_callback)
        request = DailyMarketTechnicalOfficialDispositionMaPageRequestV1.create(
            reopened_query, page_index=saved.page_index, page_size=saved.page_size,
        )
        if request.request_identity_sha256 != saved.page_request_identity_sha256:
            _fail("reopened_request_mismatch")
        page = page_cache.get(request.request_identity_sha256)
        if page is None:
            page = result.read_page_request(request, cancel_callback=cancel_callback)
            page.to_dict()
            page_cache[request.request_identity_sha256] = page
        if (
            page.operation_identity_sha256 != saved.result_identity_sha256
            or page.page_identity_sha256 != saved.page_identity_sha256
            or page.source_pins != saved.source_pins
        ):
            _fail("reopened_page_mismatch")
        actual = DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_page(page, saved.stock_code)
        if actual.to_dict() != saved.to_dict():
            _fail("reopened_row_mismatch")
        row = next((item for item in page.rows if item.stock_code == saved.stock_code), None)
        if row is None:
            _fail("reopened_row_missing")
        anchor = _VerifiedSelectionAnchor(saved, page, row, session, result)
        verified[index] = DailyMarketTechnicalOfficialDispositionMaVerifiedSelectionV1(
            selection=saved,
            page=page,
            row=row,
            _session=session,
            _result=result,
            _anchor=anchor,
            _seal=_VERIFIED_SELECTION_SEAL,
        )
    _strict_cancel(cancel_callback)
    if any(item is None for item in verified):
        _fail("publish_incomplete")
    return (
        tuple(cast(DailyMarketTechnicalOfficialDispositionMaVerifiedSelectionV1, item) for item in verified),
        result,
    )


def read_daily_market_technical_official_disposition_ma_selections_v1(
    query: DailyMarketTechnicalOfficialDispositionMaQueryV1,
    selections: Sequence[DailyMarketTechnicalOfficialDispositionMaSelectionV1],
    *,
    cancel_callback: Callable[[], object] | None = None,
) -> tuple[DailyMarketTechnicalOfficialDispositionMaVerifiedSelectionV1, ...]:
    """以同一 exact session／完整 global result 重核所選股票與原列。"""

    verified, _result = _read_daily_market_technical_official_disposition_ma_selections_with_result_v1(
        query, selections, cancel_callback=cancel_callback,
    )
    return verified


def read_daily_market_technical_official_disposition_ma_comparison_v1(
    comparison: DailyMarketTechnicalOfficialDispositionMaComparisonV1 | bytes | str,
    *,
    cancel_callback: Callable[[], object] | None = None,
) -> DailyMarketTechnicalOfficialDispositionMaVerifiedComparisonV1:
    """全域 exact 重開後才原子簽發跨頁比較；不查 latest。"""

    _strict_cancel(cancel_callback)
    if isinstance(comparison, (bytes, str)):
        saved = DailyMarketTechnicalOfficialDispositionMaComparisonV1.from_json(comparison)
    elif type(comparison) is DailyMarketTechnicalOfficialDispositionMaComparisonV1:
        saved = DailyMarketTechnicalOfficialDispositionMaComparisonV1.from_dict(comparison.to_dict())
    else:
        _fail("comparison_type_invalid")
    query = _parse_query(saved.query_json)
    columns = read_daily_market_technical_official_disposition_ma_selections_v1(
        query, saved.selections, cancel_callback=cancel_callback,
    )
    _strict_cancel(cancel_callback)
    anchor = _VerifiedComparisonAnchor(saved, columns)
    result = DailyMarketTechnicalOfficialDispositionMaVerifiedComparisonV1(
        comparison=saved,
        columns=columns,
        comparison_identity_sha256=saved.comparison_identity_sha256,
        scope="current_only",
        official_available_at=None,
        availability_status="unknown",
        historical_pit_eligible=False,
        _anchor=anchor,
        _seal=_VERIFIED_COMPARISON_SEAL,
    )
    _strict_cancel(cancel_callback)
    return result

