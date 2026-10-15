"""V2 複合研究收藏：保存查詢身分並要求呼叫端提供既有 V3 session 重驗。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import NoReturn, cast

import app_module.daily_market_technical_official_disposition_composite_query_v2 as composite
from app_module.daily_market_technical_universe_projection_group_session_v3 import (
    DailyMarketTechnicalUniverseProjectionGroupSessionV3,
)


DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_SCHEMA_V2 = (
    "daily-market-technical-official-disposition-composite-bookmark.v2"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_SELECTION_SCHEMA_V2 = (
    "daily-market-technical-official-disposition-composite-selection.v2"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_SOURCE_V2 = (
    "technical_official_disposition_composite_research_bookmark_v2"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_MAX_BYTES_V2 = 64 * 1024 * 1024
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_MAX_SCROLL_V2 = 10_000_000
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_MAX_SELECTIONS_V2 = 64
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_SELECTION_MAX_ROW_BYTES_V2 = 4 * 1024 * 1024

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STOCK_CODE_RE = re.compile(r"^[A-Z0-9]{1,16}$")
_MAX_JSON_DEPTH = 32
_MAX_SOURCE_PINS = 64
_BOOKMARK_SEAL_V2 = object()
_SELECTION_SEAL_V2 = object()
_RESTORE_CONTEXT_SEAL_V2 = object()
_BOOKMARK_SCOPE = {
    "scope": "current_only",
    "official_available_at": None,
    "availability_status": "unknown",
    "historical_pit_eligible": False,
    "bookmark_is_reader_certification": False,
}


class DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2Error(ValueError):
    """V2 收藏格式或精確重開契約的穩定拒絕碼。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"technical_official_composite_bookmark_v2_{code}")


def _fail(code: str) -> NoReturn:
    raise DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2Error(code)


def _reject_float_tree(value: object, *, depth: int = 0) -> None:
    if depth > _MAX_JSON_DEPTH:
        _fail("json_depth_limit")
    if type(value) is float:
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
        raise DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2Error(
            "json_invalid"
        ) from exc


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _require_sha(value: object, code: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        _fail(code)
    return cast(str, value)


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, item in pairs:
        if key in result:
            _fail("duplicate_json_key")
        result[key] = item
    return result


def _preflight_json_depth(text: str) -> None:
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
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > _MAX_JSON_DEPTH:
                _fail("json_depth_limit")
        elif char in "]}":
            depth -= 1
            if depth < 0:
                _fail("json_invalid")
    if quoted or escaped or depth != 0:
        _fail("json_invalid")


def _parse_float(_value: str) -> NoReturn:
    _fail("float_forbidden")


def _parse_constant(_value: str) -> NoReturn:
    _fail("json_constant_invalid")


def _parse_json(
    raw: bytes | str,
    *,
    maximum_bytes: int = DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_MAX_BYTES_V2,
) -> tuple[object, str]:
    try:
        if type(raw) is str:
            encoded = raw.encode("utf-8")
        elif type(raw) is bytes:
            encoded = raw
        else:
            _fail("json_input_invalid")
        if len(encoded) > maximum_bytes:
            _fail("byte_limit")
        text = encoded.decode("utf-8")
        _preflight_json_depth(text)
        value = json.loads(
            text,
            object_pairs_hook=_unique_pairs,
            parse_float=_parse_float,
            parse_constant=_parse_constant,
        )
        _reject_float_tree(value)
        if _canonical_json_bytes(value) != encoded:
            _fail("json_noncanonical")
        return value, text
    except DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2Error:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2Error(
            "json_invalid"
        ) from exc


def _check_cancel(callback: Callable[[], object] | None) -> None:
    if callback is None:
        return
    if not callable(callback):
        _fail("cancel_callback_invalid")
    try:
        value = callback()
    except Exception as exc:
        raise DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2Error(
            "cancel_check_failed"
        ) from exc
    if type(value) is not bool:
        _fail("cancel_callback_invalid")
    if value:
        _fail("cancelled")


def _source_pins(value: object, *, code: str = "source_pins_invalid") -> tuple[tuple[str, str], ...]:
    if not isinstance(value, (list, tuple)) or isinstance(value, (str, bytes)):
        _fail(code)
    if len(value) > _MAX_SOURCE_PINS:
        _fail(code)
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for pair in value:
        if (
            not isinstance(pair, (list, tuple))
            or isinstance(pair, (str, bytes))
            or len(pair) != 2
        ):
            _fail(code)
        key, item = pair
        if (
            type(key) is not str
            or not key
            or len(key) > 256
            or type(item) is not str
            or not item
            or len(item) > 4096
            or key in seen
        ):
            _fail(code)
        seen.add(key)
        result.append((key, item))
    if not result:
        _fail(code)
    return tuple(result)


def _source_pins_from_dict(value: object) -> tuple[tuple[str, str], ...]:
    return _source_pins(value)


def _mapping_payload(value: object, code: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        _fail(code)
    return cast(Mapping[str, object], value)


def _mapping_rows(value: object, code: str) -> list[Mapping[str, object]]:
    if type(value) is not list:
        _fail(code)
    return [_mapping_payload(item, code) for item in cast(list[object], value)]


def _stock_code_list(value: object, code: str) -> list[str]:
    if type(value) is not list:
        _fail(code)
    items = cast(list[object], value)
    for item in items:
        if type(item) is not str:
            _fail(code)
        stock_code = cast(str, item)
        if _STOCK_CODE_RE.fullmatch(stock_code) is None:
            _fail(code)
    return cast(list[str], items)


def _row_payload_is_visible(value: object) -> bool:
    """V2 列將可見判定放在 evaluation DTO，而非列層頂欄。"""
    if not isinstance(value, Mapping):
        return False
    row_payload = cast(Mapping[str, object], value)
    evaluation = row_payload.get("evaluation")
    if not isinstance(evaluation, Mapping):
        return False
    evaluation_payload = cast(Mapping[str, object], evaluation)
    return evaluation_payload.get("visible") is True


def _pins_payload(value: tuple[tuple[str, str], ...]) -> list[list[str]]:
    return [[key, item] for key, item in value]


def _counts_identity(
    result: composite.DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2,
) -> str:
    return _sha256_json(result.counts.to_dict())


def _page_request_identity(
    query_identity_sha256: str,
    page_index: int,
    page_size: int,
) -> str:
    return _sha256_json({
        "schema_version": "daily-market-technical-official-disposition-composite-page-request.v2",
        "query_identity_sha256": query_identity_sha256,
        "page_index": page_index,
        "page_size": page_size,
    })


def _page_identity_from_payload(value: Mapping[str, object]) -> str:
    return _sha256_json({
        "schema_version": composite.DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_PAGE_V2_SCHEMA,
        "query_identity_sha256": value.get("query_identity_sha256"),
        "operation_identity_sha256": value.get("operation_identity_sha256"),
        "request_identity_sha256": value.get("request_identity_sha256"),
        "page_index": value.get("page_index"),
        "page_size": value.get("page_size"),
        "rows": value.get("rows"),
        "source_pins": value.get("source_pins"),
        "counts": value.get("counts"),
        "result_status": value.get("result_status"),
        "official_source_coverage_status": value.get("official_source_coverage_status"),
        "scope": "current_only",
        "official_available_at": None,
        "availability_status": "unknown",
        "historical_pit_eligible": False,
    })


def _row_identity_from_payload(
    row: Mapping[str, object],
    query: composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV2,
) -> str:
    base_row = row.get("base_row")
    if not isinstance(base_row, Mapping):
        _fail("selection_base_row_invalid")
    base_identity = base_row.get("row_identity_sha256")
    _require_sha(base_identity, "selection_base_row_identity_invalid")
    price_fact = row.get("price_fact")
    price_fact_identity = None
    if price_fact is not None:
        if not isinstance(price_fact, Mapping):
            _fail("selection_price_fact_invalid")
        price_fact_identity = _sha256_json(price_fact)
    return _sha256_json({
        "schema_version": "daily-market-technical-official-disposition-composite-result-row.v2",
        "query_identity_sha256": query.query_identity_sha256,
        "base_row_identity_sha256": base_identity,
        "price_fact_identity_sha256": price_fact_identity,
        "price_state": row.get("price_state"),
        "evaluation": row.get("evaluation"),
        "scope": "current_only",
        "official_available_at": None,
        "availability_status": "unknown",
        "historical_pit_eligible": False,
    })


def _result_payload(
    result_json: object,
    *,
    query_json: str,
    query_identity_sha256: str,
    projection_group_session_identity_sha256: str,
    result_identity_sha256: str,
    result_counts_identity_sha256: str,
    result_status: str,
    official_source_coverage_status: str,
    source_pins: tuple[tuple[str, str], ...],
) -> Mapping[str, object]:
    if type(result_json) is not str or not result_json:
        _fail("result_json_invalid")
    raw, _text = _parse_json(
        result_json,
        maximum_bytes=composite.DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_RESULT_BYTES,
    )
    raw = _mapping_payload(raw, "result_payload_invalid")
    query = composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV2.from_json(query_json)
    counts = raw.get("counts")
    expected_fields = {
        "schema_version", "verification_status", "query_json",
        "query_identity_sha256", "projection_group_session_identity_sha256",
        "counts", "source_pins", "ordered_stock_codes", "ordered_keys_sha256",
        "result_status", "official_source_coverage_status", "scope",
        "official_available_at", "availability_status", "historical_pit_eligible",
        "operation_identity_sha256", "visible_count",
    }
    expected_result_schema = (
        "daily-market-technical-official-disposition-composite-query-result.v2"
    )
    result_body = {
        key: item
        for key, item in raw.items()
        if key not in {"operation_identity_sha256", "visible_count"}
    }
    visible_count = raw.get("visible_count")
    if type(visible_count) is not int or visible_count < 0:
        _fail("result_payload_identity_mismatch")
    ordered_codes = _stock_code_list(
        raw.get("ordered_stock_codes"),
        "result_payload_identity_mismatch",
    )
    if (
        set(raw) != expected_fields
        or raw.get("schema_version") != expected_result_schema
        or raw.get("verification_status") != "reader_verified"
        or raw.get("query_json") != query_json
        or raw.get("query_identity_sha256") != query_identity_sha256
        or raw.get("projection_group_session_identity_sha256")
        != projection_group_session_identity_sha256
        or raw.get("operation_identity_sha256") != result_identity_sha256
        or type(counts) is not dict
        or _sha256_json(counts) != result_counts_identity_sha256
        or raw.get("result_status") != result_status
        or raw.get("official_source_coverage_status")
        != official_source_coverage_status
        or _source_pins_from_dict(raw.get("source_pins")) != source_pins
        or raw.get("scope") != "current_only"
        or raw.get("official_available_at") is not None
        or raw.get("availability_status") != "unknown"
        or raw.get("historical_pit_eligible") is not False
        or len(ordered_codes) != visible_count
        or len(set(ordered_codes)) != len(ordered_codes)
        or _sha256_json(result_body) != result_identity_sha256
        or _require_sha(raw.get("ordered_keys_sha256"), "result_ordered_keys_identity_invalid")
        != raw.get("ordered_keys_sha256")
        or query.query_identity_sha256 != query_identity_sha256
        or query.projection_group_session_identity_sha256
        != projection_group_session_identity_sha256
    ):
        _fail("result_payload_identity_mismatch")
    return raw


def _selection_body(
    selection: DailyMarketTechnicalOfficialDispositionCompositeSelectionV2,
) -> dict[str, object]:
    return {
        "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_SELECTION_SCHEMA_V2,
        "query_json": selection.query_json,
        "query_identity_sha256": selection.query_identity_sha256,
        "base_query_identity_sha256": selection.base_query_identity_sha256,
        "f17_query_identity_sha256": selection.f17_query_identity_sha256,
        "projection_group_session_identity_sha256": selection.projection_group_session_identity_sha256,
        "result_identity_sha256": selection.result_identity_sha256,
        "result_counts_identity_sha256": selection.result_counts_identity_sha256,
        "page_index": selection.page_index,
        "page_size": selection.page_size,
        "page_count": selection.page_count,
        "request_identity_sha256": selection.request_identity_sha256,
        "page_identity_sha256": selection.page_identity_sha256,
        "page_json": selection.page_json,
        "stock_code": selection.stock_code,
        "row_json": selection.row_json,
        "row_identity_sha256": selection.row_identity_sha256,
        "source_pins": _pins_payload(selection.source_pins),
        **_BOOKMARK_SCOPE,
    }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionCompositeSelectionV2:
    """V2 頁面內一列的完整身份；序列化資料本身不授予來源資格。"""

    query_json: str
    query_identity_sha256: str
    base_query_identity_sha256: str
    f17_query_identity_sha256: str
    projection_group_session_identity_sha256: str
    result_identity_sha256: str
    result_counts_identity_sha256: str
    page_index: int
    page_size: int
    page_count: int
    request_identity_sha256: str
    page_identity_sha256: str
    page_json: str
    stock_code: str
    row_json: str
    row_identity_sha256: str
    source_pins: tuple[tuple[str, str], ...]
    selection_identity_sha256: str
    schema_version: str = DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_SELECTION_SCHEMA_V2

    def __post_init__(self) -> None:
        if (
            self.schema_version != DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_SELECTION_SCHEMA_V2
            or type(self.query_json) is not str
            or not self.query_json
            or len(self.query_json.encode("utf-8"))
            > composite.DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_QUERY_BYTES
            or type(self.stock_code) is not str
            or _STOCK_CODE_RE.fullmatch(self.stock_code) is None
            or type(self.row_json) is not str
            or not self.row_json
            or len(self.row_json.encode("utf-8"))
            > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_SELECTION_MAX_ROW_BYTES_V2
            or type(self.page_index) is not int
            or self.page_index < 0
            or type(self.page_size) is not int
            or not 1 <= self.page_size <= composite.DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_PAGE_SIZE
            or type(self.page_count) is not int
            or self.page_count < 1
            or self.page_index >= self.page_count
            or type(self.page_json) is not str
            or not self.page_json
        ):
            _fail("selection_fields_invalid")
        for value in (
            self.query_identity_sha256,
            self.base_query_identity_sha256,
            self.f17_query_identity_sha256,
            self.projection_group_session_identity_sha256,
            self.result_identity_sha256,
            self.result_counts_identity_sha256,
            self.request_identity_sha256,
            self.page_identity_sha256,
            self.row_identity_sha256,
            self.selection_identity_sha256,
        ):
            _require_sha(value, "selection_identity_invalid")
        query = composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV2.from_json(
            self.query_json
        )
        base_query = query.base_query
        if (
            query.query_identity_sha256 != self.query_identity_sha256
            or query.base_query_identity_sha256 != self.base_query_identity_sha256
            or base_query.f17_query_identity_sha256 != self.f17_query_identity_sha256
            or query.projection_group_session_identity_sha256
            != self.projection_group_session_identity_sha256
        ):
            _fail("selection_query_identity_mismatch")
        pins = _source_pins(self.source_pins)
        page_payload, _ = _parse_json(
            self.page_json,
            maximum_bytes=composite.DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_PAGE_BYTES,
        )
        expected_page_fields = {
            "schema_version", "query_json", "query_identity_sha256",
            "request_identity_sha256", "operation_identity_sha256",
            "page_identity_sha256", "page_index", "page_size", "page_count",
            "visible_count", "counts", "rows", "source_pins", "result_status",
            "official_source_coverage_status", "scope", "official_available_at",
            "availability_status", "historical_pit_eligible",
        }
        row_payload, _ = _parse_json(
            self.row_json,
            maximum_bytes=DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_SELECTION_MAX_ROW_BYTES_V2,
        )
        row_payload = _mapping_payload(row_payload, "selection_row_invalid")
        page_payload = _mapping_payload(page_payload, "selection_page_invalid")
        page_rows_value = page_payload.get("rows")
        if type(page_rows_value) is not list:
            _fail("selection_page_rows_invalid")
        page_rows = _mapping_rows(
            page_rows_value,
            "selection_row_invalid",
        )
        visible_count = page_payload.get("visible_count")
        if type(visible_count) is not int or visible_count < 0:
            _fail("selection_page_visible_count_invalid")
        row_fields = {
            "schema_version", "query_identity_sha256", "stock_code", "base_row",
            "price_fact", "price_state", "evaluation", "row_identity_sha256",
            "scope", "official_available_at", "availability_status",
            "historical_pit_eligible",
        }
        if (
            set(page_payload) != expected_page_fields
            or page_payload.get("schema_version")
            != composite.DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_PAGE_V2_SCHEMA
            or page_payload.get("query_json") != self.query_json
            or page_payload.get("query_identity_sha256") != self.query_identity_sha256
            or type(page_payload.get("page_index")) is not int
            or type(page_payload.get("page_size")) is not int
            or type(page_payload.get("page_count")) is not int
            or type(page_payload.get("visible_count")) is not int
            or page_payload.get("request_identity_sha256") != self.request_identity_sha256
            or self.request_identity_sha256
            != _page_request_identity(self.query_identity_sha256, self.page_index, self.page_size)
            or page_payload.get("operation_identity_sha256") != self.result_identity_sha256
            or page_payload.get("page_identity_sha256") != self.page_identity_sha256
            or page_payload.get("page_index") != self.page_index
            or page_payload.get("page_size") != self.page_size
            or page_payload.get("page_count") != self.page_count
            or page_payload.get("page_count")
            != (visible_count + self.page_size - 1) // self.page_size
            or type(page_payload.get("counts")) is not dict
            or _sha256_json(page_payload.get("counts")) != self.result_counts_identity_sha256
            or len(page_rows) > self.page_size
            or any(not _row_payload_is_visible(item) for item in page_rows)
            or _page_identity_from_payload(page_payload) != self.page_identity_sha256
            or not any(
                item.get("stock_code") == self.stock_code
                and _canonical_json_bytes(item).decode("utf-8") == self.row_json
                for item in page_rows
            )
            or _source_pins_from_dict(page_payload.get("source_pins")) != pins
            or page_payload.get("scope") != "current_only"
            or page_payload.get("official_available_at") is not None
            or page_payload.get("availability_status") != "unknown"
            or page_payload.get("historical_pit_eligible") is not False
            or page_payload.get("result_status") not in {"complete", "partial"}
            or page_payload.get("official_source_coverage_status") not in {"complete", "partial"}
            or set(row_payload) != row_fields
            or row_payload.get("schema_version")
            != "daily-market-technical-official-disposition-composite-result-row.v2"
            or row_payload.get("query_identity_sha256") != self.query_identity_sha256
            or row_payload.get("stock_code") != self.stock_code
            or row_payload.get("row_identity_sha256") != self.row_identity_sha256
            or not _row_payload_is_visible(row_payload)
            or row_payload.get("scope") != "current_only"
            or row_payload.get("official_available_at") is not None
            or row_payload.get("availability_status") != "unknown"
            or row_payload.get("historical_pit_eligible") is not False
            or _row_identity_from_payload(row_payload, query) != self.row_identity_sha256
        ):
            _fail("selection_row_invalid")
        if self.selection_identity_sha256 != _sha256_json(_selection_body(self)):
            _fail("selection_identity_mismatch")
        if pins != self.source_pins:
            _fail("selection_source_pins_invalid")

    @classmethod
    def from_real_row_context(
        cls,
        result: composite.DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2,
        page: composite.DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2,
        stock_code: str,
    ) -> DailyMarketTechnicalOfficialDispositionCompositeSelectionV2:
        """僅從同一 result/page 已發行且可見的列建立 selection。"""
        if (
            type(result)
            is not composite.DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2
            or type(page)
            is not composite.DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2
            or type(stock_code) is not str
        ):
            _fail("selection_context_invalid")
        try:
            result.__post_init__()
            page.__post_init__()
            result_json = result.to_json()
            page.to_json()
        except Exception as exc:
            raise DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2Error(
                "selection_context_not_reader_issued"
            ) from exc
        if (
            page._result is not result
            or page.query is not result.query
            or page.operation_identity_sha256 != result.operation_identity_sha256
            or page.source_pins != result.source_pins
            or page.counts != result.counts
        ):
            _fail("selection_result_page_mismatch")
        row = next((item for item in page.rows if item.stock_code == stock_code), None)
        if row is None:
            _fail("selection_row_not_visible")
        row_payload = _canonical_json_bytes(row.to_dict())
        if len(row_payload) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_SELECTION_MAX_ROW_BYTES_V2:
            _fail("selection_row_byte_limit")
        query = result.query
        request_identity = page.request_identity_sha256
        if (
            page.page_index < 0
            or page.page_index >= page.page_count
            or page.page_size < 1
            or len(result_json.encode("utf-8"))
            > composite.DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_RESULT_BYTES
        ):
            _fail("selection_page_invalid")
        base_query = query.base_query
        pins = _source_pins(result.source_pins)
        query_json = query.to_json()
        counts_identity = _counts_identity(result)
        page_json = page.to_json()
        row_json = row_payload.decode("utf-8")
        identity_payload = {
            "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_SELECTION_SCHEMA_V2,
            "query_json": query_json,
            "query_identity_sha256": query.query_identity_sha256,
            "base_query_identity_sha256": query.base_query_identity_sha256,
            "f17_query_identity_sha256": base_query.f17_query_identity_sha256,
            "projection_group_session_identity_sha256": query.projection_group_session_identity_sha256,
            "result_identity_sha256": result.operation_identity_sha256,
            "result_counts_identity_sha256": counts_identity,
            "page_index": page.page_index,
            "page_size": page.page_size,
            "page_count": page.page_count,
            "request_identity_sha256": request_identity,
            "page_identity_sha256": page.page_identity_sha256,
            "page_json": page_json,
            "stock_code": row.stock_code,
            "row_json": row_json,
            "row_identity_sha256": row.row_identity_sha256,
            "source_pins": _pins_payload(pins),
            **_BOOKMARK_SCOPE,
        }
        return cls(
            query_json=query_json,
            query_identity_sha256=query.query_identity_sha256,
            base_query_identity_sha256=query.base_query_identity_sha256,
            f17_query_identity_sha256=base_query.f17_query_identity_sha256,
            projection_group_session_identity_sha256=query.projection_group_session_identity_sha256,
            result_identity_sha256=result.operation_identity_sha256,
            result_counts_identity_sha256=counts_identity,
            page_index=page.page_index,
            page_size=page.page_size,
            page_count=page.page_count,
            request_identity_sha256=request_identity,
            page_identity_sha256=page.page_identity_sha256,
            page_json=page_json,
            stock_code=row.stock_code,
            row_json=row_json,
            row_identity_sha256=row.row_identity_sha256,
            source_pins=pins,
            selection_identity_sha256=_sha256_json(identity_payload),
        )

    @classmethod
    def from_dict(
        cls,
        value: object,
    ) -> DailyMarketTechnicalOfficialDispositionCompositeSelectionV2:
        expected = {
            "schema_version", "query_json", "query_identity_sha256",
            "base_query_identity_sha256", "f17_query_identity_sha256",
            "projection_group_session_identity_sha256", "result_identity_sha256",
            "result_counts_identity_sha256", "page_index", "page_size", "page_count",
            "request_identity_sha256", "page_identity_sha256", "stock_code",
            "page_json", "row_json", "row_identity_sha256", "source_pins", "scope",
            "official_available_at", "availability_status", "historical_pit_eligible",
            "bookmark_is_reader_certification", "selection_identity_sha256",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            _fail("selection_fields_invalid")
        if (
            value.get("scope") != "current_only"
            or value.get("official_available_at") is not None
            or value.get("availability_status") != "unknown"
            or value.get("historical_pit_eligible") is not False
            or value.get("bookmark_is_reader_certification") is not False
        ):
            _fail("selection_scope_invalid")
        selection = cls(
            query_json=cast(str, value.get("query_json")),
            query_identity_sha256=cast(str, value.get("query_identity_sha256")),
            base_query_identity_sha256=cast(str, value.get("base_query_identity_sha256")),
            f17_query_identity_sha256=cast(str, value.get("f17_query_identity_sha256")),
            projection_group_session_identity_sha256=cast(
                str, value.get("projection_group_session_identity_sha256"),
            ),
            result_identity_sha256=cast(str, value.get("result_identity_sha256")),
            result_counts_identity_sha256=cast(str, value.get("result_counts_identity_sha256")),
            page_index=cast(int, value.get("page_index")),
            page_size=cast(int, value.get("page_size")),
            page_count=cast(int, value.get("page_count")),
            request_identity_sha256=cast(str, value.get("request_identity_sha256")),
            page_identity_sha256=cast(str, value.get("page_identity_sha256")),
            page_json=cast(str, value.get("page_json")),
            stock_code=cast(str, value.get("stock_code")),
            row_json=cast(str, value.get("row_json")),
            row_identity_sha256=cast(str, value.get("row_identity_sha256")),
            source_pins=_source_pins_from_dict(value.get("source_pins")),
            selection_identity_sha256=cast(str, value.get("selection_identity_sha256")),
            schema_version=cast(str, value.get("schema_version")),
        )
        if selection.to_dict() != dict(value):
            _fail("selection_noncanonical")
        return selection

    def to_dict(self) -> dict[str, object]:
        return {
            **_selection_body(self),
            "selection_identity_sha256": self.selection_identity_sha256,
        }


def _bookmark_body(
    bookmark: DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2,
) -> dict[str, object]:
    return {
        "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_SCHEMA_V2,
        "query_json": bookmark.query_json,
        "query_identity_sha256": bookmark.query_identity_sha256,
        "base_query_identity_sha256": bookmark.base_query_identity_sha256,
        "f17_query_identity_sha256": bookmark.f17_query_identity_sha256,
        "projection_group_session_identity_sha256": bookmark.projection_group_session_identity_sha256,
        "result_json": bookmark.result_json,
        "result_identity_sha256": bookmark.result_identity_sha256,
        "result_counts_identity_sha256": bookmark.result_counts_identity_sha256,
        "result_status": bookmark.result_status,
        "official_source_coverage_status": bookmark.official_source_coverage_status,
        "selected": bookmark.selected.to_dict(),
        "comparison_selections": [item.to_dict() for item in bookmark.comparison_selections],
        "basket_stock_codes": list(bookmark.basket_stock_codes),
        "scroll_position": bookmark.scroll_position,
        "source_pins": _pins_payload(bookmark.source_pins),
        **_BOOKMARK_SCOPE,
    }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2:
    """可攜收藏；只有帶入既有 V3 session 精確重讀後才取得 verified context。"""

    query_json: str
    query_identity_sha256: str
    base_query_identity_sha256: str
    f17_query_identity_sha256: str
    projection_group_session_identity_sha256: str
    result_json: str
    result_identity_sha256: str
    result_counts_identity_sha256: str
    result_status: str
    official_source_coverage_status: str
    selected: DailyMarketTechnicalOfficialDispositionCompositeSelectionV2
    comparison_selections: tuple[DailyMarketTechnicalOfficialDispositionCompositeSelectionV2, ...]
    basket_stock_codes: tuple[str, ...]
    scroll_position: int
    source_pins: tuple[tuple[str, str], ...]
    bookmark_identity_sha256: str
    schema_version: str = DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_SCHEMA_V2

    def __post_init__(self) -> None:
        if (
            self.schema_version != DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_SCHEMA_V2
            or type(self.query_json) is not str
            or not self.query_json
            or type(self.result_json) is not str
            or not self.result_json
            or type(self.comparison_selections) is not tuple
            or type(self.selected) is not DailyMarketTechnicalOfficialDispositionCompositeSelectionV2
            or len(self.comparison_selections)
            > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_MAX_SELECTIONS_V2 - 1
            or any(type(item) is not DailyMarketTechnicalOfficialDispositionCompositeSelectionV2 for item in self.comparison_selections)
            or type(self.basket_stock_codes) is not tuple
            or type(self.source_pins) is not tuple
            or type(self.scroll_position) is not int
            or not 0 <= self.scroll_position <= DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_MAX_SCROLL_V2
            or type(self.result_status) is not str
            or self.result_status not in {"complete", "partial"}
            or type(self.official_source_coverage_status) is not str
            or self.official_source_coverage_status not in {"complete", "partial"}
        ):
            _fail("bookmark_fields_invalid")
        for value in (
            self.query_identity_sha256,
            self.base_query_identity_sha256,
            self.f17_query_identity_sha256,
            self.projection_group_session_identity_sha256,
            self.result_identity_sha256,
            self.result_counts_identity_sha256,
            self.bookmark_identity_sha256,
        ):
            _require_sha(value, "bookmark_identity_invalid")
        query = composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV2.from_json(
            self.query_json
        )
        base_query = query.base_query
        pins = _source_pins(self.source_pins)
        selections = (self.selected, *self.comparison_selections)
        selected_codes = tuple(item.stock_code for item in selections)
        if (
            query.query_identity_sha256 != self.query_identity_sha256
            or query.base_query_identity_sha256 != self.base_query_identity_sha256
            or base_query.f17_query_identity_sha256 != self.f17_query_identity_sha256
            or query.projection_group_session_identity_sha256
            != self.projection_group_session_identity_sha256
            or len(set(selected_codes)) != len(selected_codes)
            or any(
                item.query_json != self.query_json
                or item.query_identity_sha256 != self.query_identity_sha256
                or item.base_query_identity_sha256 != self.base_query_identity_sha256
                or item.f17_query_identity_sha256 != self.f17_query_identity_sha256
                or item.projection_group_session_identity_sha256
                != self.projection_group_session_identity_sha256
                or item.result_identity_sha256 != self.result_identity_sha256
                or item.result_counts_identity_sha256 != self.result_counts_identity_sha256
                or item.source_pins != pins
                for item in selections
            )
            or not self.basket_stock_codes
            or any(type(item) is not str or _STOCK_CODE_RE.fullmatch(item) is None for item in self.basket_stock_codes)
            or len(set(self.basket_stock_codes)) != len(self.basket_stock_codes)
            or set(self.basket_stock_codes) != set(selected_codes)
            or pins != self.source_pins
        ):
            _fail("bookmark_source_identity_mismatch")
        result_payload = _result_payload(
            self.result_json,
            query_json=self.query_json,
            query_identity_sha256=self.query_identity_sha256,
            projection_group_session_identity_sha256=self.projection_group_session_identity_sha256,
            result_identity_sha256=self.result_identity_sha256,
            result_counts_identity_sha256=self.result_counts_identity_sha256,
            result_status=self.result_status,
            official_source_coverage_status=self.official_source_coverage_status,
            source_pins=pins,
        )
        for selection in selections:
            page_payload, _ = _parse_json(
                selection.page_json,
                maximum_bytes=composite.DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_PAGE_BYTES,
            )
            page_payload = _mapping_payload(page_payload, "bookmark_page_payload_invalid")
            ordered_codes_value = result_payload.get("ordered_stock_codes")
            if type(ordered_codes_value) is not list:
                _fail("bookmark_result_order_invalid")
            ordered_codes = _stock_code_list(
                ordered_codes_value,
                "bookmark_page_result_mismatch",
            )
            start = selection.page_index * selection.page_size
            expected_codes = ordered_codes[start:start + selection.page_size]
            page_rows_value = page_payload.get("rows")
            if type(page_rows_value) is not list:
                _fail("bookmark_page_result_mismatch")
            page_rows = _mapping_rows(
                page_rows_value,
                "bookmark_page_result_mismatch",
            )
            page_codes = _stock_code_list(
                [item.get("stock_code") for item in page_rows],
                "bookmark_page_result_mismatch",
            )
            if (
                page_payload.get("visible_count") != result_payload.get("visible_count")
                or page_payload.get("counts") != result_payload.get("counts")
                or page_payload.get("result_status") != result_payload.get("result_status")
                or page_payload.get("official_source_coverage_status")
                != result_payload.get("official_source_coverage_status")
                or page_payload.get("source_pins") != result_payload.get("source_pins")
                or page_codes != expected_codes
            ):
                _fail("bookmark_page_result_mismatch")
        if self.bookmark_identity_sha256 != _sha256_json(_bookmark_body(self)):
            _fail("bookmark_identity_mismatch")
        if len(_canonical_json_bytes(self.to_dict())) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_MAX_BYTES_V2:
            _fail("byte_limit")

    @classmethod
    def create_from_real_row_context(
        cls,
        result: composite.DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2,
        page: composite.DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2,
        stock_code: str,
        *,
        scroll_position: int = 0,
        comparison_contexts: Sequence[
            tuple[composite.DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2, str]
        ] = (),
        basket_stock_codes: Sequence[str] | None = None,
    ) -> DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2:
        """只從 reader-issued result/page 和其中可見列建立保存資料。"""
        if (
            type(result)
            is not composite.DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2
            or type(page)
            is not composite.DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2
        ):
            _fail("bookmark_context_invalid")
        if (
            type(scroll_position) is not int
            or not 0 <= scroll_position
            <= DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_MAX_SCROLL_V2
        ):
            _fail("scroll_position_invalid")
        try:
            result.__post_init__()
            result_json = result.to_json()
            page.__post_init__()
            page.to_json()
        except Exception as exc:
            raise DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2Error(
                "bookmark_context_not_reader_issued"
            ) from exc
        if page._result is not result or page.query is not result.query:
            _fail("bookmark_result_page_mismatch")
        selected = DailyMarketTechnicalOfficialDispositionCompositeSelectionV2.from_real_row_context(
            result,
            page,
            stock_code,
        )
        comparisons_input = _bounded_items(
            comparison_contexts,
            DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_MAX_SELECTIONS_V2 - 1,
            "comparison_contexts_invalid",
        )
        comparisons: list[DailyMarketTechnicalOfficialDispositionCompositeSelectionV2] = []
        for item in comparisons_input:
            if type(item) is not tuple or len(item) != 2:
                _fail("comparison_contexts_invalid")
            compare_page, compare_code = cast(tuple[object, object], item)
            if (
                type(compare_page)
                is not composite.DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2
                or type(compare_code) is not str
            ):
                _fail("comparison_contexts_invalid")
            comparisons.append(
                DailyMarketTechnicalOfficialDispositionCompositeSelectionV2.from_real_row_context(
                    result,
                    compare_page,
                    compare_code,
                )
            )
        selections = (selected, *comparisons)
        codes = tuple(item.stock_code for item in selections)
        if len(set(codes)) != len(codes):
            _fail("selection_stock_code_duplicate")
        if basket_stock_codes is None:
            basket = codes
        else:
            basket = _stock_codes(basket_stock_codes, code="basket_stock_codes_invalid")
            if set(basket) != set(codes):
                _fail("basket_selection_membership_mismatch")
        query = result.query
        base_query = query.base_query
        pins = _source_pins(result.source_pins)
        query_json = query.to_json()
        result_counts_identity = _counts_identity(result)
        comparison_selections = tuple(comparisons)
        identity_payload = {
            "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_SCHEMA_V2,
            "query_json": query_json,
            "query_identity_sha256": query.query_identity_sha256,
            "base_query_identity_sha256": query.base_query_identity_sha256,
            "f17_query_identity_sha256": base_query.f17_query_identity_sha256,
            "projection_group_session_identity_sha256": query.projection_group_session_identity_sha256,
            "result_json": result_json,
            "result_identity_sha256": result.operation_identity_sha256,
            "result_counts_identity_sha256": result_counts_identity,
            "result_status": result.result_status,
            "official_source_coverage_status": result.official_source_coverage_status,
            "selected": selected.to_dict(),
            "comparison_selections": [item.to_dict() for item in comparison_selections],
            "basket_stock_codes": list(basket),
            "scroll_position": scroll_position,
            "source_pins": _pins_payload(pins),
            **_BOOKMARK_SCOPE,
        }
        return cls(
            query_json=query_json,
            query_identity_sha256=query.query_identity_sha256,
            base_query_identity_sha256=query.base_query_identity_sha256,
            f17_query_identity_sha256=base_query.f17_query_identity_sha256,
            projection_group_session_identity_sha256=query.projection_group_session_identity_sha256,
            result_json=result_json,
            result_identity_sha256=result.operation_identity_sha256,
            result_counts_identity_sha256=result_counts_identity,
            result_status=result.result_status,
            official_source_coverage_status=result.official_source_coverage_status,
            selected=selected,
            comparison_selections=comparison_selections,
            basket_stock_codes=basket,
            scroll_position=scroll_position,
            source_pins=pins,
            bookmark_identity_sha256=_sha256_json(identity_payload),
        )

    @classmethod
    def from_dict(
        cls,
        value: object,
    ) -> DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2:
        expected = {
            "schema_version", "query_json", "query_identity_sha256",
            "base_query_identity_sha256", "f17_query_identity_sha256",
            "projection_group_session_identity_sha256", "result_json",
            "result_identity_sha256", "result_counts_identity_sha256",
            "result_status", "official_source_coverage_status", "selected",
            "comparison_selections", "basket_stock_codes", "scroll_position",
            "source_pins", "scope", "official_available_at", "availability_status",
            "historical_pit_eligible", "bookmark_is_reader_certification",
            "bookmark_identity_sha256",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            _fail("bookmark_fields_invalid")
        if (
            value.get("scope") != "current_only"
            or value.get("official_available_at") is not None
            or value.get("availability_status") != "unknown"
            or value.get("historical_pit_eligible") is not False
            or value.get("bookmark_is_reader_certification") is not False
            or type(value.get("scroll_position")) is not int
        ):
            _fail("bookmark_scope_invalid")
        raw_comparisons = value.get("comparison_selections")
        if (
            type(raw_comparisons) is not list
            or len(raw_comparisons)
            > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_MAX_SELECTIONS_V2 - 1
        ):
            _fail("comparison_contexts_invalid")
        raw_basket = value.get("basket_stock_codes")
        if type(raw_basket) is not list:
            _fail("basket_stock_codes_invalid")
        bookmark = cls(
            query_json=cast(str, value.get("query_json")),
            query_identity_sha256=cast(str, value.get("query_identity_sha256")),
            base_query_identity_sha256=cast(str, value.get("base_query_identity_sha256")),
            f17_query_identity_sha256=cast(str, value.get("f17_query_identity_sha256")),
            projection_group_session_identity_sha256=cast(
                str, value.get("projection_group_session_identity_sha256"),
            ),
            result_json=cast(str, value.get("result_json")),
            result_identity_sha256=cast(str, value.get("result_identity_sha256")),
            result_counts_identity_sha256=cast(str, value.get("result_counts_identity_sha256")),
            result_status=cast(str, value.get("result_status")),
            official_source_coverage_status=cast(
                str, value.get("official_source_coverage_status"),
            ),
            selected=DailyMarketTechnicalOfficialDispositionCompositeSelectionV2.from_dict(
                value.get("selected"),
            ),
            comparison_selections=tuple(
                DailyMarketTechnicalOfficialDispositionCompositeSelectionV2.from_dict(item)
                for item in raw_comparisons
            ),
            basket_stock_codes=_stock_codes(raw_basket, code="basket_stock_codes_invalid"),
            scroll_position=cast(int, value.get("scroll_position")),
            source_pins=_source_pins_from_dict(value.get("source_pins")),
            bookmark_identity_sha256=cast(str, value.get("bookmark_identity_sha256")),
            schema_version=cast(str, value.get("schema_version")),
        )
        if bookmark.to_dict() != dict(value):
            _fail("bookmark_noncanonical")
        return bookmark

    @classmethod
    def from_json(
        cls,
        raw: bytes | str,
    ) -> DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2:
        payload, text = _parse_json(raw)
        bookmark = cls.from_dict(payload)
        if bookmark.to_json() != text:
            _fail("bookmark_noncanonical")
        return bookmark

    @property
    def query(self) -> composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV2:
        return composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV2.from_json(
            self.query_json
        )

    @property
    def bookmark_id(self) -> str:
        return self.bookmark_identity_sha256

    @property
    def stock_code(self) -> str:
        return self.selected.stock_code

    @property
    def source(self) -> str:
        return DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_SOURCE_V2

    def to_dict(self) -> dict[str, object]:
        return {
            **_bookmark_body(self),
            "bookmark_identity_sha256": self.bookmark_identity_sha256,
        }

    def to_json(self) -> str:
        raw = _canonical_json_bytes(self.to_dict())
        if len(raw) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_MAX_BYTES_V2:
            _fail("byte_limit")
        return raw.decode("utf-8")


def _stock_codes(value: object, *, code: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _fail(code)
    if len(value) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_MAX_SELECTIONS_V2:
        _fail(code)
    codes: list[str] = []
    for item in value:
        if type(item) is not str or _STOCK_CODE_RE.fullmatch(item) is None:
            _fail(code)
        codes.append(item)
    result = tuple(codes)
    if not result or len(result) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_MAX_SELECTIONS_V2 or len(set(result)) != len(result):
        _fail(code)
    return result


def _bounded_items(value: object, maximum: int, code: str) -> tuple[object, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _fail(code)
    items: list[object] = []
    try:
        for index, item in enumerate(value):
            if index >= maximum:
                _fail(code)
            items.append(item)
    except DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2Error:
        raise
    except Exception as exc:
        raise DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2Error(code) from exc
    return tuple(items)


def _validate_result_page(
    result: composite.DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2,
    page: composite.DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2,
) -> None:
    if (
        type(result)
        is not composite.DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2
        or type(page)
        is not composite.DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2
    ):
        _fail("restore_page_invalid")
    result.__post_init__()
    page.__post_init__()
    page.to_json()
    if (
        page._result is not result
        or page.query is not result.query
        or page.operation_identity_sha256 != result.operation_identity_sha256
        or page.source_pins != result.source_pins
        or page.counts != result.counts
    ):
        _fail("restore_page_result_mismatch")


def _verify_selection_against_fresh_page(
    selection: DailyMarketTechnicalOfficialDispositionCompositeSelectionV2,
    result: composite.DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2,
    page: composite.DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2,
) -> composite.DailyMarketTechnicalOfficialDispositionCompositeResultRowV2:
    _validate_result_page(result, page)
    if (
        result.query.to_json() != selection.query_json
        or result.query.query_identity_sha256 != selection.query_identity_sha256
        or result.query.base_query_identity_sha256 != selection.base_query_identity_sha256
        or result.query.base_query.f17_query_identity_sha256
        != selection.f17_query_identity_sha256
        or result.query.projection_group_session_identity_sha256
        != selection.projection_group_session_identity_sha256
        or result.operation_identity_sha256 != selection.result_identity_sha256
        or _counts_identity(result) != selection.result_counts_identity_sha256
        or result.source_pins != selection.source_pins
        or page.to_json() != selection.page_json
        or page.page_index != selection.page_index
        or page.page_size != selection.page_size
        or page.page_count != selection.page_count
        or page.request_identity_sha256 != selection.request_identity_sha256
        or page.page_identity_sha256 != selection.page_identity_sha256
    ):
        _fail("restore_identity_mismatch")
    row = next((item for item in page.rows if item.stock_code == selection.stock_code), None)
    if (
        row is None
        or type(row) is not composite.DailyMarketTechnicalOfficialDispositionCompositeResultRowV2
        or row.query_identity_sha256 != selection.query_identity_sha256
        or row.row_identity_sha256 != selection.row_identity_sha256
        or _canonical_json_bytes(row.to_dict()).decode("utf-8") != selection.row_json
    ):
        _fail("restore_row_identity_mismatch")
    return row


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionCompositeVerifiedSelectionV2:
    """精確重開後發行的可見列參照。"""

    selection: DailyMarketTechnicalOfficialDispositionCompositeSelectionV2
    page: composite.DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2
    row: composite.DailyMarketTechnicalOfficialDispositionCompositeResultRowV2
    _result: composite.DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2 = field(repr=False, compare=False)
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            self._seal is not _SELECTION_SEAL_V2
            or type(self.selection) is not DailyMarketTechnicalOfficialDispositionCompositeSelectionV2
        ):
            _fail("verified_selection_not_reader_issued")
        expected = _verify_selection_against_fresh_page(
            self.selection,
            self._result,
            self.page,
        )
        if expected is not self.row:
            _fail("verified_selection_row_mismatch")


class _RestoreContextAnchorV2:
    __slots__ = ("bookmark", "result", "verified", "subject")

    bookmark: DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2
    result: composite.DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2
    verified: tuple[DailyMarketTechnicalOfficialDispositionCompositeVerifiedSelectionV2, ...]
    subject: object | None

    def __init__(
        self,
        bookmark: DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2,
        result: composite.DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2,
        verified: tuple[DailyMarketTechnicalOfficialDispositionCompositeVerifiedSelectionV2, ...],
    ) -> None:
        object.__setattr__(self, "bookmark", bookmark)
        object.__setattr__(self, "result", result)
        object.__setattr__(self, "verified", verified)
        object.__setattr__(self, "subject", None)

    def can_claim(self, subject: object) -> bool:
        return self.subject is None or self.subject is subject

    def claim(self, subject: object) -> None:
        if not self.can_claim(subject):
            _fail("restore_context_already_claimed")
        object.__setattr__(self, "subject", subject)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("composite bookmark restore anchor is immutable")


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionCompositeBookmarkRestoreContextV2:
    """呼叫端提供單一已開啟 V3 session 後的 reader-verified result/page/rows。"""

    bookmark: DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2
    result: composite.DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2
    selected: DailyMarketTechnicalOfficialDispositionCompositeVerifiedSelectionV2
    comparison_selections: tuple[DailyMarketTechnicalOfficialDispositionCompositeVerifiedSelectionV2, ...]
    basket_stock_codes: tuple[str, ...]
    scroll_position: int
    scope: str
    official_available_at: None
    availability_status: str
    historical_pit_eligible: bool
    bookmark_is_reader_certification: bool
    _anchor: _RestoreContextAnchorV2 = field(repr=False, compare=False)
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            self._seal is not _RESTORE_CONTEXT_SEAL_V2
            or type(self._anchor) is not _RestoreContextAnchorV2
            or not self._anchor.can_claim(self)
            or type(self.comparison_selections) is not tuple
            or any(
                type(item) is not DailyMarketTechnicalOfficialDispositionCompositeVerifiedSelectionV2
                for item in self.comparison_selections
            )
            or self._anchor.bookmark is not self.bookmark
            or self._anchor.result is not self.result
            or self._anchor.verified != (self.selected, *self.comparison_selections)
            or self.basket_stock_codes != self.bookmark.basket_stock_codes
            or self.scroll_position != self.bookmark.scroll_position
            or self.scope != "current_only"
            or self.official_available_at is not None
            or self.availability_status != "unknown"
            or self.historical_pit_eligible is not False
            or self.bookmark_is_reader_certification is not False
        ):
            _fail("restore_context_not_reader_issued")
        already_claimed = self._anchor.subject is self
        self.result.__post_init__()
        if (
            self.result.query.to_json() != self.bookmark.query_json
            or self.result.query.query_identity_sha256 != self.bookmark.query_identity_sha256
            or self.result.operation_identity_sha256 != self.bookmark.result_identity_sha256
            or _counts_identity(self.result) != self.bookmark.result_counts_identity_sha256
            or self.result.source_pins != self.bookmark.source_pins
            or self.result.result_status != self.bookmark.result_status
            or self.result.official_source_coverage_status
            != self.bookmark.official_source_coverage_status
        ):
            _fail("restore_context_source_mismatch")
        for verified in (self.selected, *self.comparison_selections):
            verified.__post_init__()
            if verified._result is not self.result:
                _fail("restore_context_selection_mismatch")
        if not already_claimed:
            self._anchor.claim(self)

    @property
    def query(self) -> composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV2:
        self.__post_init__()
        return self.result.query

    def read_page(
        self,
        page_index: int,
        page_size: int,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> composite.DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2:
        """只沿收藏所綁的同次 reader result 讀取此查詢的其他頁。"""
        _check_cancel(cancel_callback)
        self.__post_init__()
        try:
            page = self.result.read_page(
                page_index,
                page_size,
                cancel_callback=cancel_callback,
            )
            _validate_result_page(self.result, page)
            _check_cancel(cancel_callback)
            return page
        except DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2Error:
            raise
        except Exception as exc:
            _check_cancel(cancel_callback)
            raise DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2Error(
                "restore_page_read_failed"
            ) from exc


def read_daily_market_technical_official_disposition_composite_bookmark_context_v2(
    bookmark: DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2 | bytes | str,
    *,
    projection_group_session: DailyMarketTechnicalUniverseProjectionGroupSessionV3,
    cancel_callback: Callable[[], object] | None = None,
) -> DailyMarketTechnicalOfficialDispositionCompositeBookmarkRestoreContextV2:
    """以呼叫端既有 V3 session 精確重跑一次，不另開 parent reader。"""
    _check_cancel(cancel_callback)
    if isinstance(bookmark, (bytes, str)):
        saved = DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2.from_json(bookmark)
    elif type(bookmark) is DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2:
        saved = DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2.from_dict(
            bookmark.to_dict()
        )
    else:
        _fail("bookmark_type_invalid")
    if type(projection_group_session) is not DailyMarketTechnicalUniverseProjectionGroupSessionV3:
        _fail("projection_group_session_invalid")
    if (
        projection_group_session.identity_sha256
        != saved.projection_group_session_identity_sha256
    ):
        _fail("projection_group_session_identity_mismatch")
    try:
        _check_cancel(cancel_callback)
        result = composite.DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2.from_json(
            saved.result_json,
            projection_group_session=projection_group_session,
            cancel_callback=cancel_callback,
        )
        if (
            result._projection_group_session is not projection_group_session
            or result.query.to_json() != saved.query_json
            or result.query.query_identity_sha256 != saved.query_identity_sha256
            or result.query.base_query_identity_sha256 != saved.base_query_identity_sha256
            or result.query.base_query.f17_query_identity_sha256
            != saved.f17_query_identity_sha256
            or result.operation_identity_sha256 != saved.result_identity_sha256
            or _counts_identity(result) != saved.result_counts_identity_sha256
            or result.source_pins != saved.source_pins
            or result.result_status != saved.result_status
            or result.official_source_coverage_status
            != saved.official_source_coverage_status
        ):
            _fail("restore_result_identity_mismatch")
        _check_cancel(cancel_callback)

        verified_items: list[DailyMarketTechnicalOfficialDispositionCompositeVerifiedSelectionV2] = []
        page_cache: dict[
            tuple[int, int],
            composite.DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2,
        ] = {}
        for selection in (saved.selected, *saved.comparison_selections):
            _check_cancel(cancel_callback)
            key = (selection.page_index, selection.page_size)
            page = page_cache.get(key)
            if page is None:
                page = result.read_page(
                    selection.page_index,
                    selection.page_size,
                    cancel_callback=cancel_callback,
                )
                _validate_result_page(result, page)
                page_cache[key] = page
            row = _verify_selection_against_fresh_page(selection, result, page)
            verified_items.append(
                DailyMarketTechnicalOfficialDispositionCompositeVerifiedSelectionV2(
                    selection=selection,
                    page=page,
                    row=row,
                    _result=result,
                    _seal=_SELECTION_SEAL_V2,
                )
            )
            _check_cancel(cancel_callback)
        if not verified_items:
            _fail("restore_selection_missing")
        verified = tuple(verified_items)
        anchor = _RestoreContextAnchorV2(saved, result, verified)
        context = DailyMarketTechnicalOfficialDispositionCompositeBookmarkRestoreContextV2(
            bookmark=saved,
            result=result,
            selected=verified[0],
            comparison_selections=verified[1:],
            basket_stock_codes=saved.basket_stock_codes,
            scroll_position=saved.scroll_position,
            scope="current_only",
            official_available_at=None,
            availability_status="unknown",
            historical_pit_eligible=False,
            bookmark_is_reader_certification=False,
            _anchor=anchor,
            _seal=_RESTORE_CONTEXT_SEAL_V2,
        )
        _check_cancel(cancel_callback)
        return context
    except DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2Error:
        raise
    except Exception as exc:
        _check_cancel(cancel_callback)
        raise DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2Error(
            "restore_exact_reopen_failed"
        ) from exc


__all__ = (
    "DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_MAX_BYTES_V2",
    "DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_MAX_SCROLL_V2",
    "DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_MAX_SELECTIONS_V2",
    "DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_SCHEMA_V2",
    "DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_SOURCE_V2",
    "DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_SELECTION_MAX_ROW_BYTES_V2",
    "DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_SELECTION_SCHEMA_V2",
    "DailyMarketTechnicalOfficialDispositionCompositeBookmarkRestoreContextV2",
    "DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2",
    "DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2Error",
    "DailyMarketTechnicalOfficialDispositionCompositeSelectionV2",
    "DailyMarketTechnicalOfficialDispositionCompositeVerifiedSelectionV2",
    "read_daily_market_technical_official_disposition_composite_bookmark_context_v2",
)
