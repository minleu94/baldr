"""F17／P01／MA／KDJ／波動率複合查詢的有型別收藏與精確來源還原。

收藏只保存已發行 query/result/page/row 的完整身份與來源 pins。還原時會用
保存的 F17 query 呼叫正式精確群組 opener，重新發行 composite result/page，並逐項
比對所有原身份；bookmark 本身不授予資料資格，也不提供最新資料替代路徑。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import NoReturn, cast

import app_module.daily_market_technical_official_disposition_composite_query_v1 as composite
from app_module.daily_market_technical_official_disposition_composite_query_v1 import (
    DailyMarketTechnicalOfficialDispositionCompositePageRequestV1,
    DailyMarketTechnicalOfficialDispositionCompositeQueryPageV1,
    DailyMarketTechnicalOfficialDispositionCompositeQueryV1,
    DailyMarketTechnicalOfficialDispositionCompositeResultRowV1,
    DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
)
from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
    DailyMarketTechnicalOfficialDispositionReadSessionV1,
    open_daily_market_technical_official_disposition_projection_group_session_v2,
)
from app_module.daily_market_technical_universe_projection_group_session_v2 import (
    DailyMarketTechnicalUniverseProjectionGroupSessionV2,
)


DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_SCHEMA_V1 = (
    "daily-market-technical-official-disposition-composite-bookmark.v1"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_SELECTION_SCHEMA_V1 = (
    "daily-market-technical-official-disposition-composite-selection.v1"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_SOURCE = (
    "technical_official_disposition_composite_research_bookmark"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_MAX_BYTES = 64 * 1024 * 1024
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_MAX_SCROLL = 10_000_000
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_MAX_SELECTIONS = 64
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_SELECTION_MAX_ROW_BYTES = 4 * 1024 * 1024

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_BOOKMARK_SEAL_V1 = object()
_SELECTION_SEAL_V1 = object()
_RESTORE_CONTEXT_SEAL_V1 = object()


class DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1Error(ValueError):
    """複合收藏資料格式或精確重開契約的穩定拒絕碼。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"technical_official_composite_bookmark_v1_{code}")


def _fail(code: str) -> NoReturn:
    raise DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1Error(code)


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1Error(
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
    for key, value in pairs:
        if key in result:
            _fail("duplicate_json_key")
        result[key] = value
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
            if depth > 32:
                _fail("json_depth_limit")
        elif char in "]}":
            depth -= 1
            if depth < 0:
                _fail("json_invalid")
    if quoted or escaped or depth != 0:
        _fail("json_invalid")


def _parse_json(raw: bytes | str) -> object:
    try:
        encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
        if type(encoded) is not bytes or len(encoded) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_MAX_BYTES:
            _fail("byte_limit")
        text = encoded.decode("utf-8")
        _preflight_json_depth(text)
        payload = json.loads(
            text,
            object_pairs_hook=_unique_pairs,
            parse_float=lambda _value: _fail("float_forbidden"),
            parse_constant=lambda _value: _fail("json_constant_invalid"),
        )
        if _canonical_json_bytes(payload) != encoded:
            _fail("json_noncanonical")
        return payload
    except DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1Error:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1Error(
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
        raise DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1Error(
            "cancel_check_failed"
        ) from exc
    if type(value) is not bool:
        _fail("cancel_callback_invalid")
    if value:
        _fail("cancelled")


def _source_pins(value: object) -> tuple[tuple[str, str], ...]:
    if type(value) is not tuple or len(value) != len(composite._SOURCE_PIN_KEYS):
        _fail("source_pins_invalid")
    pins: list[tuple[str, str]] = []
    for item in value:
        if (
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not str
            or type(item[1]) is not str
        ):
            _fail("source_pins_invalid")
        pins.append((item[0], item[1]))
    result = tuple(pins)
    if tuple(key for key, _item in result) != composite._SOURCE_PIN_KEYS:
        _fail("source_pins_invalid")
    return result


def _source_pins_from_dict(value: object) -> tuple[tuple[str, str], ...]:
    if type(value) is not list or len(value) != len(composite._SOURCE_PIN_KEYS):
        _fail("source_pins_invalid")
    pins: list[tuple[str, str]] = []
    for item in value:
        if (
            type(item) is not list
            or len(item) != 2
            or type(item[0]) is not str
            or type(item[1]) is not str
        ):
            _fail("source_pins_invalid")
        pins.append((item[0], item[1]))
    return _source_pins(tuple(pins))


def _bounded_items(value: object, maximum: int, code: str) -> tuple[object, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _fail(code)
    items: list[object] = []
    try:
        iterator = iter(value)
        for _index in range(maximum + 1):
            try:
                items.append(next(iterator))
            except StopIteration:
                return tuple(items)
    except DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1Error:
        raise
    except Exception as exc:
        raise DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1Error(code) from exc
    _fail(code)


def _pins_payload(value: tuple[tuple[str, str], ...]) -> list[list[str]]:
    return [[key, item] for key, item in _source_pins(value)]


def _validate_query_and_pins(
    query: DailyMarketTechnicalOfficialDispositionCompositeQueryV1,
    source_pins: tuple[tuple[str, str], ...],
) -> None:
    if type(query) is not DailyMarketTechnicalOfficialDispositionCompositeQueryV1:
        _fail("query_invalid")
    try:
        query.to_json()
        composite._validate_result_source_pins(
            query,
            source_pins,
            f17_query=query.f17_query,
        )
    except DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1Error:
        raise
    except Exception as exc:
        raise DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1Error(
            "source_pins_invalid"
        ) from exc


def _counts_identity(
    result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
) -> str:
    return _sha256_json(result.counts.to_dict())


def _selection_body(selection: DailyMarketTechnicalOfficialDispositionCompositeSelectionV1) -> dict[str, object]:
    return {
        "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_SELECTION_SCHEMA_V1,
        "query_json": selection.query_json,
        "query_identity_sha256": selection.query_identity_sha256,
        "f17_query_identity_sha256": selection.f17_query_identity_sha256,
        "projection_group_session_identity_sha256": selection.projection_group_session_identity_sha256,
        "result_identity_sha256": selection.result_identity_sha256,
        "result_counts_identity_sha256": selection.result_counts_identity_sha256,
        "page_index": selection.page_index,
        "page_size": selection.page_size,
        "page_count": selection.page_count,
        "page_request_identity_sha256": selection.page_request_identity_sha256,
        "page_identity_sha256": selection.page_identity_sha256,
        "stock_code": selection.stock_code,
        "row_json": selection.row_json,
        "row_identity_sha256": selection.row_identity_sha256,
        "source_pins": _pins_payload(selection.source_pins),
        "scope": "current_only",
        "official_available_at": None,
        "availability_status": "unknown",
        "historical_pit_eligible": False,
    }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionCompositeSelectionV1:
    """一列已發行複合頁的精確身份；本 DTO 不授予 reader 資格。"""

    query_json: str
    query_identity_sha256: str
    f17_query_identity_sha256: str
    projection_group_session_identity_sha256: str
    result_identity_sha256: str
    result_counts_identity_sha256: str
    page_index: int
    page_size: int
    page_count: int
    page_request_identity_sha256: str
    page_identity_sha256: str
    stock_code: str
    row_json: str
    row_identity_sha256: str
    source_pins: tuple[tuple[str, str], ...]
    selection_identity_sha256: str
    schema_version: str = DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_SELECTION_SCHEMA_V1

    def __post_init__(self) -> None:
        if (
            self.schema_version != DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_SELECTION_SCHEMA_V1
            or type(self.query_json) is not str
            or not self.query_json
            or len(self.query_json.encode("utf-8")) > composite.DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_QUERY_BYTES
            or type(self.stock_code) is not str
            or re.fullmatch(r"[A-Z0-9]{1,16}", self.stock_code) is None
            or type(self.row_json) is not str
            or not self.row_json
            or len(self.row_json.encode("utf-8")) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_SELECTION_MAX_ROW_BYTES
            or type(self.page_index) is not int
            or self.page_index < 0
            or type(self.page_size) is not int
            or self.page_size < 1
            or type(self.page_count) is not int
            or self.page_count < 1
            or self.page_index >= self.page_count
        ):
            _fail("selection_fields_invalid")
        for value in (
            self.query_identity_sha256,
            self.f17_query_identity_sha256,
            self.projection_group_session_identity_sha256,
            self.result_identity_sha256,
            self.result_counts_identity_sha256,
            self.page_request_identity_sha256,
            self.page_identity_sha256,
            self.row_identity_sha256,
            self.selection_identity_sha256,
        ):
            _require_sha(value, "selection_identity_invalid")
        query = DailyMarketTechnicalOfficialDispositionCompositeQueryV1.from_json(self.query_json)
        if (
            query.query_identity_sha256 != self.query_identity_sha256
            or query.f17_query_identity_sha256 != self.f17_query_identity_sha256
            or query.projection_group_session_identity_sha256
            != self.projection_group_session_identity_sha256
        ):
            _fail("selection_query_identity_mismatch")
        pins = _source_pins(self.source_pins)
        _validate_query_and_pins(query, pins)
        request = DailyMarketTechnicalOfficialDispositionCompositePageRequestV1.create(
            query,
            page_index=self.page_index,
            page_size=self.page_size,
        )
        if request.request_identity_sha256 != self.page_request_identity_sha256:
            _fail("selection_request_identity_mismatch")
        row_payload = _parse_json(self.row_json)
        if (
            _canonical_json_bytes(row_payload).decode("utf-8") != self.row_json
            or not isinstance(row_payload, Mapping)
            or row_payload.get("schema_version")
            != "daily-market-technical-official-disposition-composite-result-row.v1"
            or row_payload.get("query_identity_sha256") != self.query_identity_sha256
            or row_payload.get("stock_code") != self.stock_code
            or row_payload.get("row_identity_sha256") != self.row_identity_sha256
            or row_payload.get("scope") != "current_only"
            or row_payload.get("official_available_at") is not None
            or row_payload.get("availability_status") != "unknown"
            or row_payload.get("historical_pit_eligible") is not False
        ):
            _fail("selection_row_invalid")
        if self.selection_identity_sha256 != _sha256_json(_selection_body(self)):
            _fail("selection_identity_mismatch")

    @classmethod
    def from_real_row_context(
        cls,
        result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
        page: DailyMarketTechnicalOfficialDispositionCompositeQueryPageV1,
        stock_code: str,
    ) -> DailyMarketTechnicalOfficialDispositionCompositeSelectionV1:
        """只從同一 reader 發行的 result/page 可見列建立，不接受呼叫端自備列。"""
        if (
            type(result) is not DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1
            or type(page) is not DailyMarketTechnicalOfficialDispositionCompositeQueryPageV1
            or type(stock_code) is not str
        ):
            _fail("selection_context_invalid")
        try:
            result.__post_init__()
            page.__post_init__()
            page.to_dict()
        except Exception as exc:
            raise DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1Error(
                "selection_context_not_reader_issued"
            ) from exc
        query = result.query
        if (
            page._result is not result
            or page.query is not query
            or page.operation_identity_sha256 != result.operation_identity_sha256
            or page.source_pins != result.source_pins
            or result.query.to_json() != page.query.to_json()
        ):
            _fail("selection_result_page_mismatch")
        row = next((item for item in page.rows if item.stock_code == stock_code), None)
        if row is None:
            _fail("selection_row_not_visible")
        if type(row) is not DailyMarketTechnicalOfficialDispositionCompositeResultRowV1:
            _fail("selection_row_invalid")
        row_json = _canonical_json_bytes(row.to_dict()).decode("utf-8")
        source_pins = _source_pins(result.source_pins)
        _validate_query_and_pins(query, source_pins)
        request = DailyMarketTechnicalOfficialDispositionCompositePageRequestV1.create(
            query,
            page_index=page.page_index,
            page_size=page.page_size,
        )
        if request.request_identity_sha256 != page.request_identity_sha256:
            _fail("selection_request_identity_mismatch")
        identity_payload = {
            "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_SELECTION_SCHEMA_V1,
            "query_json": query.to_json(),
            "query_identity_sha256": query.query_identity_sha256,
            "f17_query_identity_sha256": query.f17_query_identity_sha256,
            "projection_group_session_identity_sha256": query.projection_group_session_identity_sha256,
            "result_identity_sha256": result.operation_identity_sha256,
            "result_counts_identity_sha256": _counts_identity(result),
            "page_index": page.page_index,
            "page_size": page.page_size,
            "page_count": page.page_count,
            "page_request_identity_sha256": request.request_identity_sha256,
            "page_identity_sha256": page.page_identity_sha256,
            "stock_code": stock_code,
            "row_json": row_json,
            "row_identity_sha256": row.row_identity_sha256,
            "source_pins": _pins_payload(source_pins),
            "scope": "current_only",
            "official_available_at": None,
            "availability_status": "unknown",
            "historical_pit_eligible": False,
        }
        return cls(
            query_json=query.to_json(),
            query_identity_sha256=query.query_identity_sha256,
            f17_query_identity_sha256=query.f17_query_identity_sha256,
            projection_group_session_identity_sha256=query.projection_group_session_identity_sha256,
            result_identity_sha256=result.operation_identity_sha256,
            result_counts_identity_sha256=_counts_identity(result),
            page_index=page.page_index,
            page_size=page.page_size,
            page_count=page.page_count,
            page_request_identity_sha256=request.request_identity_sha256,
            page_identity_sha256=page.page_identity_sha256,
            stock_code=stock_code,
            row_json=row_json,
            row_identity_sha256=row.row_identity_sha256,
            source_pins=source_pins,
            selection_identity_sha256=_sha256_json(identity_payload),
        )

    @classmethod
    def from_dict(
        cls,
        value: object,
    ) -> DailyMarketTechnicalOfficialDispositionCompositeSelectionV1:
        expected = {
            "schema_version", "query_json", "query_identity_sha256",
            "f17_query_identity_sha256", "projection_group_session_identity_sha256",
            "result_identity_sha256", "result_counts_identity_sha256", "page_index",
            "page_size", "page_count", "page_request_identity_sha256",
            "page_identity_sha256", "stock_code", "row_json", "row_identity_sha256",
            "source_pins", "scope", "official_available_at", "availability_status",
            "historical_pit_eligible", "selection_identity_sha256",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            _fail("selection_fields_invalid")
        if (
            value.get("scope") != "current_only"
            or value.get("official_available_at") is not None
            or value.get("availability_status") != "unknown"
            or value.get("historical_pit_eligible") is not False
        ):
            _fail("selection_qualification_invalid")
        return cls(
            query_json=cast(str, value.get("query_json")),
            query_identity_sha256=cast(str, value.get("query_identity_sha256")),
            f17_query_identity_sha256=cast(str, value.get("f17_query_identity_sha256")),
            projection_group_session_identity_sha256=cast(
                str, value.get("projection_group_session_identity_sha256"),
            ),
            result_identity_sha256=cast(str, value.get("result_identity_sha256")),
            result_counts_identity_sha256=cast(str, value.get("result_counts_identity_sha256")),
            page_index=cast(int, value.get("page_index")),
            page_size=cast(int, value.get("page_size")),
            page_count=cast(int, value.get("page_count")),
            page_request_identity_sha256=cast(str, value.get("page_request_identity_sha256")),
            page_identity_sha256=cast(str, value.get("page_identity_sha256")),
            stock_code=cast(str, value.get("stock_code")),
            row_json=cast(str, value.get("row_json")),
            row_identity_sha256=cast(str, value.get("row_identity_sha256")),
            source_pins=_source_pins_from_dict(value.get("source_pins")),
            selection_identity_sha256=cast(str, value.get("selection_identity_sha256")),
            schema_version=cast(str, value.get("schema_version")),
        )

    @property
    def query(self) -> DailyMarketTechnicalOfficialDispositionCompositeQueryV1:
        return DailyMarketTechnicalOfficialDispositionCompositeQueryV1.from_json(self.query_json)

    def to_dict(self) -> dict[str, object]:
        return {
            **_selection_body(self),
            "selection_identity_sha256": self.selection_identity_sha256,
        }


def _bookmark_body(bookmark: DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1) -> dict[str, object]:
    return {
        "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_SCHEMA_V1,
        "query_json": bookmark.query_json,
        "query_identity_sha256": bookmark.query_identity_sha256,
        "f17_query_identity_sha256": bookmark.f17_query_identity_sha256,
        "projection_group_session_identity_sha256": bookmark.projection_group_session_identity_sha256,
        "result_identity_sha256": bookmark.result_identity_sha256,
        "result_counts_identity_sha256": bookmark.result_counts_identity_sha256,
        "result_status": bookmark.result_status,
        "official_source_coverage_status": bookmark.official_source_coverage_status,
        "selected": bookmark.selected.to_dict(),
        "comparison_selections": [item.to_dict() for item in bookmark.comparison_selections],
        "scroll_position": bookmark.scroll_position,
        "source_pins": _pins_payload(bookmark.source_pins),
        "scope": "current_only",
        "official_available_at": None,
        "availability_status": "unknown",
        "historical_pit_eligible": False,
        "bookmark_is_reader_certification": False,
    }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1:
    """複合研究收藏；自我摘要僅檢查序列化一致，不代表來源已重新核驗。"""

    query_json: str
    query_identity_sha256: str
    f17_query_identity_sha256: str
    projection_group_session_identity_sha256: str
    result_identity_sha256: str
    result_counts_identity_sha256: str
    result_status: str
    official_source_coverage_status: str
    selected: DailyMarketTechnicalOfficialDispositionCompositeSelectionV1
    comparison_selections: tuple[DailyMarketTechnicalOfficialDispositionCompositeSelectionV1, ...]
    scroll_position: int
    source_pins: tuple[tuple[str, str], ...]
    bookmark_identity_sha256: str
    schema_version: str = DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_SCHEMA_V1

    def __post_init__(self) -> None:
        if (
            self.schema_version != DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_SCHEMA_V1
            or type(self.query_json) is not str
            or type(self.comparison_selections) is not tuple
            or type(self.selected) is not DailyMarketTechnicalOfficialDispositionCompositeSelectionV1
            or len(self.comparison_selections) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_MAX_SELECTIONS - 1
            or any(type(item) is not DailyMarketTechnicalOfficialDispositionCompositeSelectionV1 for item in self.comparison_selections)
            or type(self.scroll_position) is not int
            or not 0 <= self.scroll_position <= DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_MAX_SCROLL
            or type(self.result_status) is not str
            or self.result_status not in {"complete", "partial"}
            or type(self.official_source_coverage_status) is not str
            or self.official_source_coverage_status not in {"complete", "partial"}
        ):
            _fail("bookmark_fields_invalid")
        for value in (
            self.query_identity_sha256,
            self.f17_query_identity_sha256,
            self.projection_group_session_identity_sha256,
            self.result_identity_sha256,
            self.result_counts_identity_sha256,
            self.bookmark_identity_sha256,
        ):
            _require_sha(value, "bookmark_identity_invalid")
        query = DailyMarketTechnicalOfficialDispositionCompositeQueryV1.from_json(self.query_json)
        pins = _source_pins(self.source_pins)
        _validate_query_and_pins(query, pins)
        selections = (self.selected, *self.comparison_selections)
        if (
            query.query_identity_sha256 != self.query_identity_sha256
            or query.f17_query_identity_sha256 != self.f17_query_identity_sha256
            or query.projection_group_session_identity_sha256
            != self.projection_group_session_identity_sha256
            or self.selected.query_json != self.query_json
            or len({item.stock_code for item in selections}) != len(selections)
            or any(
                item.query_json != self.query_json
                or item.query_identity_sha256 != self.query_identity_sha256
                or item.f17_query_identity_sha256 != self.f17_query_identity_sha256
                or item.projection_group_session_identity_sha256
                != self.projection_group_session_identity_sha256
                or item.result_identity_sha256 != self.result_identity_sha256
                or item.result_counts_identity_sha256 != self.result_counts_identity_sha256
                or item.source_pins != pins
                for item in selections
            )
        ):
            _fail("bookmark_source_identity_mismatch")
        if self.bookmark_identity_sha256 != _sha256_json(_bookmark_body(self)):
            _fail("bookmark_identity_mismatch")
        if len(_canonical_json_bytes(self.to_dict())) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_MAX_BYTES:
            _fail("byte_limit")

    @classmethod
    def create_from_real_row_context(
        cls,
        result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
        page: DailyMarketTechnicalOfficialDispositionCompositeQueryPageV1,
        stock_code: str,
        *,
        scroll_position: int = 0,
        comparison_contexts: Sequence[
            tuple[DailyMarketTechnicalOfficialDispositionCompositeQueryPageV1, str]
        ] = (),
    ) -> DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1:
        """從目前真實頁列建立收藏；不接受呼叫端自備列或來源身份。"""
        if (
            type(result) is not DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1
            or type(page) is not DailyMarketTechnicalOfficialDispositionCompositeQueryPageV1
        ):
            _fail("bookmark_context_invalid")
        if type(scroll_position) is not int or not 0 <= scroll_position <= DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_MAX_SCROLL:
            _fail("scroll_position_invalid")
        try:
            result.__post_init__()
            page.__post_init__()
            result_json = result.query.to_json()
            page.to_dict()
        except Exception as exc:
            raise DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1Error(
                "bookmark_context_not_reader_issued"
            ) from exc
        if page._result is not result or page.query is not result.query:
            _fail("bookmark_result_page_mismatch")
        selected = DailyMarketTechnicalOfficialDispositionCompositeSelectionV1.from_real_row_context(
            result, page, stock_code,
        )
        comparison_items = _bounded_items(
            comparison_contexts,
            DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_MAX_SELECTIONS - 1,
            "comparison_contexts_invalid",
        )
        comparisons: list[DailyMarketTechnicalOfficialDispositionCompositeSelectionV1] = []
        for pair in comparison_items:
            if type(pair) is not tuple or len(pair) != 2:
                _fail("comparison_contexts_invalid")
            comparison_page, comparison_code = pair
            comparisons.append(
                DailyMarketTechnicalOfficialDispositionCompositeSelectionV1.from_real_row_context(
                    result,
                    comparison_page,
                    comparison_code,
                )
            )
        if len(comparisons) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_MAX_SELECTIONS - 1:
            _fail("comparison_count_invalid")
        pins = _source_pins(result.source_pins)
        query = result.query
        identity_payload = {
            "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_SCHEMA_V1,
            "query_json": result_json,
            "query_identity_sha256": query.query_identity_sha256,
            "f17_query_identity_sha256": query.f17_query_identity_sha256,
            "projection_group_session_identity_sha256": query.projection_group_session_identity_sha256,
            "result_identity_sha256": result.operation_identity_sha256,
            "result_counts_identity_sha256": _counts_identity(result),
            "result_status": result.result_status,
            "official_source_coverage_status": result.official_source_coverage_status,
            "selected": selected.to_dict(),
            "comparison_selections": [item.to_dict() for item in comparisons],
            "scroll_position": scroll_position,
            "source_pins": _pins_payload(pins),
            "scope": "current_only",
            "official_available_at": None,
            "availability_status": "unknown",
            "historical_pit_eligible": False,
            "bookmark_is_reader_certification": False,
        }
        return cls(
            query_json=result_json,
            query_identity_sha256=query.query_identity_sha256,
            f17_query_identity_sha256=query.f17_query_identity_sha256,
            projection_group_session_identity_sha256=query.projection_group_session_identity_sha256,
            result_identity_sha256=result.operation_identity_sha256,
            result_counts_identity_sha256=_counts_identity(result),
            result_status=result.result_status,
            official_source_coverage_status=result.official_source_coverage_status,
            selected=selected,
            comparison_selections=tuple(comparisons),
            scroll_position=scroll_position,
            source_pins=pins,
            bookmark_identity_sha256=_sha256_json(identity_payload),
        )

    @classmethod
    def from_dict(
        cls,
        value: object,
    ) -> DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1:
        expected = {
            "schema_version", "query_json", "query_identity_sha256",
            "f17_query_identity_sha256", "projection_group_session_identity_sha256",
            "result_identity_sha256", "result_counts_identity_sha256", "result_status",
            "official_source_coverage_status", "selected", "comparison_selections",
            "scroll_position", "source_pins", "scope", "official_available_at",
            "availability_status", "historical_pit_eligible",
            "bookmark_is_reader_certification", "bookmark_identity_sha256",
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
            _fail("bookmark_qualification_invalid")
        raw_comparisons = value.get("comparison_selections")
        if (
            type(raw_comparisons) is not list
            or len(raw_comparisons)
            > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_MAX_SELECTIONS - 1
        ):
            _fail("comparison_contexts_invalid")
        comparisons = tuple(
            DailyMarketTechnicalOfficialDispositionCompositeSelectionV1.from_dict(item)
            for item in raw_comparisons
        )
        bookmark = cls(
            query_json=cast(str, value.get("query_json")),
            query_identity_sha256=cast(str, value.get("query_identity_sha256")),
            f17_query_identity_sha256=cast(str, value.get("f17_query_identity_sha256")),
            projection_group_session_identity_sha256=cast(
                str, value.get("projection_group_session_identity_sha256"),
            ),
            result_identity_sha256=cast(str, value.get("result_identity_sha256")),
            result_counts_identity_sha256=cast(str, value.get("result_counts_identity_sha256")),
            result_status=cast(str, value.get("result_status")),
            official_source_coverage_status=cast(
                str, value.get("official_source_coverage_status"),
            ),
            selected=DailyMarketTechnicalOfficialDispositionCompositeSelectionV1.from_dict(
                value.get("selected"),
            ),
            comparison_selections=comparisons,
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
    ) -> DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1:
        payload = _parse_json(raw)
        bookmark = cls.from_dict(payload)
        encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
        if bookmark.to_json().encode("utf-8") != encoded:
            _fail("bookmark_noncanonical")
        return bookmark

    @property
    def query(self) -> DailyMarketTechnicalOfficialDispositionCompositeQueryV1:
        return DailyMarketTechnicalOfficialDispositionCompositeQueryV1.from_json(self.query_json)

    @property
    def bookmark_id(self) -> str:
        return self.bookmark_identity_sha256

    @property
    def stock_code(self) -> str:
        return self.selected.stock_code

    @property
    def source(self) -> str:
        return DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_SOURCE

    def to_dict(self) -> dict[str, object]:
        return {
            **_bookmark_body(self),
            "bookmark_identity_sha256": self.bookmark_identity_sha256,
        }

    def to_json(self) -> str:
        raw = _canonical_json_bytes(self.to_dict())
        if len(raw) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_MAX_BYTES:
            _fail("byte_limit")
        return raw.decode("utf-8")


def _validate_result_page(
    result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
    page: DailyMarketTechnicalOfficialDispositionCompositeQueryPageV1,
) -> None:
    if (
        type(result) is not DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1
        or type(page) is not DailyMarketTechnicalOfficialDispositionCompositeQueryPageV1
    ):
        _fail("restore_page_invalid")
    result.__post_init__()
    page.__post_init__()
    page.to_dict()
    if (
        page._result is not result
        or page.query is not result.query
        or page.operation_identity_sha256 != result.operation_identity_sha256
        or page.source_pins != result.source_pins
        or page.counts is not result.counts
    ):
        _fail("restore_page_result_mismatch")


def _verify_selection_against_fresh_page(
    selection: DailyMarketTechnicalOfficialDispositionCompositeSelectionV1,
    result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
    page: DailyMarketTechnicalOfficialDispositionCompositeQueryPageV1,
) -> DailyMarketTechnicalOfficialDispositionCompositeResultRowV1:
    _validate_result_page(result, page)
    if (
        result.query.to_json() != selection.query_json
        or result.query.query_identity_sha256 != selection.query_identity_sha256
        or result.query.f17_query_identity_sha256 != selection.f17_query_identity_sha256
        or result.query.projection_group_session_identity_sha256
        != selection.projection_group_session_identity_sha256
        or result.operation_identity_sha256 != selection.result_identity_sha256
        or _counts_identity(result) != selection.result_counts_identity_sha256
        or result.source_pins != selection.source_pins
        or page.page_index != selection.page_index
        or page.page_size != selection.page_size
        or page.page_count != selection.page_count
        or page.request_identity_sha256 != selection.page_request_identity_sha256
        or page.page_identity_sha256 != selection.page_identity_sha256
    ):
        _fail("restore_identity_mismatch")
    row = next((item for item in page.rows if item.stock_code == selection.stock_code), None)
    if (
        row is None
        or type(row) is not DailyMarketTechnicalOfficialDispositionCompositeResultRowV1
        or row.query_identity_sha256 != selection.query_identity_sha256
        or row.row_identity_sha256 != selection.row_identity_sha256
        or _canonical_json_bytes(row.to_dict()).decode("utf-8") != selection.row_json
    ):
        _fail("restore_row_identity_mismatch")
    return row


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionCompositeVerifiedSelectionV1:
    """精確重開後由 bookmark context 內部發行的可見列參照。"""

    selection: DailyMarketTechnicalOfficialDispositionCompositeSelectionV1
    page: DailyMarketTechnicalOfficialDispositionCompositeQueryPageV1
    row: DailyMarketTechnicalOfficialDispositionCompositeResultRowV1
    _result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1 = field(repr=False, compare=False)
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            self._seal is not _SELECTION_SEAL_V1
            or type(self.selection) is not DailyMarketTechnicalOfficialDispositionCompositeSelectionV1
        ):
            _fail("verified_selection_not_reader_issued")
        expected = _verify_selection_against_fresh_page(
            self.selection,
            self._result,
            self.page,
        )
        if expected is not self.row:
            _fail("verified_selection_row_mismatch")


class _RestoreContextAnchorV1:
    __slots__ = ("bookmark", "result", "verified", "subject")
    bookmark: DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1
    result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1
    verified: tuple[DailyMarketTechnicalOfficialDispositionCompositeVerifiedSelectionV1, ...]
    subject: object | None

    def __init__(
        self,
        bookmark: DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1,
        result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1,
        verified: tuple[DailyMarketTechnicalOfficialDispositionCompositeVerifiedSelectionV1, ...],
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
class DailyMarketTechnicalOfficialDispositionCompositeBookmarkRestoreContextV1:
    """全新精確重開後的有型別 result 與選取列；不暴露額外資格。"""

    bookmark: DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1
    result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1
    selected: DailyMarketTechnicalOfficialDispositionCompositeVerifiedSelectionV1
    comparison_selections: tuple[DailyMarketTechnicalOfficialDispositionCompositeVerifiedSelectionV1, ...]
    scope: str
    official_available_at: None
    availability_status: str
    historical_pit_eligible: bool
    bookmark_is_reader_certification: bool
    _anchor: _RestoreContextAnchorV1 = field(repr=False, compare=False)
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            self._seal is not _RESTORE_CONTEXT_SEAL_V1
            or type(self._anchor) is not _RestoreContextAnchorV1
            or not self._anchor.can_claim(self)
            or type(self.comparison_selections) is not tuple
            or any(
                type(item) is not DailyMarketTechnicalOfficialDispositionCompositeVerifiedSelectionV1
                for item in self.comparison_selections
            )
            or self._anchor.bookmark is not self.bookmark
            or self._anchor.result is not self.result
            or self._anchor.verified != (self.selected, *self.comparison_selections)
            or self.scope != "current_only"
            or self.official_available_at is not None
            or self.availability_status != "unknown"
            or self.historical_pit_eligible is not False
            or self.bookmark_is_reader_certification is not False
        ):
            _fail("restore_context_not_reader_issued")
        already_claimed = self._anchor.subject is self
        try:
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
        except DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1Error:
            raise
        except Exception as exc:
            raise DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1Error(
                "restore_context_invalid"
            ) from exc
        if not already_claimed:
            self._anchor.claim(self)

    @property
    def query(self) -> DailyMarketTechnicalOfficialDispositionCompositeQueryV1:
        self.__post_init__()
        return self.result.query

    def read_page_request(
        self,
        request: DailyMarketTechnicalOfficialDispositionCompositePageRequestV1 | bytes | str,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalOfficialDispositionCompositeQueryPageV1:
        """只沿同次 verified result 讀取同一完整複合 query 的新頁。"""
        _check_cancel(cancel_callback)
        self.__post_init__()
        if isinstance(request, (bytes, str)):
            try:
                request = DailyMarketTechnicalOfficialDispositionCompositePageRequestV1.from_json(request)
            except Exception as exc:
                raise DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1Error(
                    "restore_page_request_invalid"
                ) from exc
        if type(request) is not DailyMarketTechnicalOfficialDispositionCompositePageRequestV1:
            _fail("restore_page_request_invalid")
        try:
            request_json = request.to_json()
            if (
                request.query_json != self.bookmark.query_json
                or request.query.query_identity_sha256 != self.bookmark.query_identity_sha256
            ):
                _fail("restore_page_request_query_mismatch")
            expected = DailyMarketTechnicalOfficialDispositionCompositePageRequestV1.create(
                self.result.query,
                page_index=request.page_index,
                page_size=request.page_size,
            )
            if request_json != expected.to_json():
                _fail("restore_page_request_identity_mismatch")
            _check_cancel(cancel_callback)
            page = self.result.read_page_request(request, cancel_callback=cancel_callback)
            _validate_result_page(self.result, page)
            _check_cancel(cancel_callback)
            return page
        except DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1Error:
            raise
        except Exception as exc:
            _check_cancel(cancel_callback)
            raise DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1Error(
                "restore_page_read_failed"
            ) from exc


def read_daily_market_technical_official_disposition_composite_bookmark_context_v1(
    bookmark: DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1 | bytes | str,
    *,
    cancel_callback: Callable[[], object] | None = None,
) -> DailyMarketTechnicalOfficialDispositionCompositeBookmarkRestoreContextV1:
    """以原 F17 query 精確重開，重發 result/page/row 並逐一核對完整身份。"""
    _check_cancel(cancel_callback)
    if isinstance(bookmark, (bytes, str)):
        saved = DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1.from_json(bookmark)
    elif type(bookmark) is DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1:
        saved = DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1.from_dict(bookmark.to_dict())
    else:
        _fail("bookmark_type_invalid")

    saved_query = saved.query
    try:
        _check_cancel(cancel_callback)
        read_session = open_daily_market_technical_official_disposition_projection_group_session_v2(
            saved_query.f17_query,
            cancel_callback=cancel_callback,
        )
        if type(read_session) is not DailyMarketTechnicalOfficialDispositionReadSessionV1:
            _fail("restore_reader_session_invalid")
        read_session.__post_init__()
        group = read_session.projection_group_session
        if type(group) is not DailyMarketTechnicalUniverseProjectionGroupSessionV2:
            _fail("restore_projection_group_unavailable")
        if read_session.query.to_json() != saved_query.f17_query_json:
            _fail("restore_f17_query_identity_mismatch")
        _check_cancel(cancel_callback)
        query = DailyMarketTechnicalOfficialDispositionCompositeQueryV1.create(
            read_session.query,
            projection_group_session_identity_sha256=group.identity_sha256,
            ma_states=saved_query.ma_states,
            kdj_states=saved_query.kdj_states,
            bandwidth_min_pct=saved_query.bandwidth_min_pct,
            bandwidth_max_pct=saved_query.bandwidth_max_pct,
            atr14_min_pct=saved_query.atr14_min_pct,
            atr14_max_pct=saved_query.atr14_max_pct,
            condition_combine_mode=saved_query.condition_combine_mode,
            unknown_policy=saved_query.unknown_policy,
            sort_clauses=saved_query.sort_clauses,
        )
        query.validate_reader_binding(read_session.query, group)
        if query.to_json() != saved.query_json:
            _fail("restore_query_identity_mismatch")
        _check_cancel(cancel_callback)
        result = read_session.execute_composite_query_v1(
            query,
            cancel_callback=cancel_callback,
        )
        if type(result) is not DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV1:
            _fail("restore_result_invalid")
        result.__post_init__()
        if (
            result._read_session is not read_session
            or result._projection_group_session is not group
            or result.query is not query
            or result.query.to_json() != saved.query_json
            or result.query.query_identity_sha256 != saved.query_identity_sha256
            or result.query.f17_query_identity_sha256 != saved.f17_query_identity_sha256
            or result.query.projection_group_session_identity_sha256
            != saved.projection_group_session_identity_sha256
            or result.operation_identity_sha256 != saved.result_identity_sha256
            or _counts_identity(result) != saved.result_counts_identity_sha256
            or result.result_status != saved.result_status
            or result.official_source_coverage_status
            != saved.official_source_coverage_status
            or result.source_pins != saved.source_pins
        ):
            _fail("restore_result_identity_mismatch")
        _check_cancel(cancel_callback)

        verified_items: list[DailyMarketTechnicalOfficialDispositionCompositeVerifiedSelectionV1] = []
        page_cache: dict[tuple[int, int], DailyMarketTechnicalOfficialDispositionCompositeQueryPageV1] = {}
        for selection in (saved.selected, *saved.comparison_selections):
            _check_cancel(cancel_callback)
            key = (selection.page_index, selection.page_size)
            page = page_cache.get(key)
            if page is None:
                request = DailyMarketTechnicalOfficialDispositionCompositePageRequestV1.create(
                    result.query,
                    page_index=selection.page_index,
                    page_size=selection.page_size,
                )
                if request.request_identity_sha256 != selection.page_request_identity_sha256:
                    _fail("restore_request_identity_mismatch")
                page = result.read_page_request(request, cancel_callback=cancel_callback)
                _validate_result_page(result, page)
                page_cache[key] = page
            row = _verify_selection_against_fresh_page(selection, result, page)
            verified_items.append(
                DailyMarketTechnicalOfficialDispositionCompositeVerifiedSelectionV1(
                    selection=selection,
                    page=page,
                    row=row,
                    _result=result,
                    _seal=_SELECTION_SEAL_V1,
                )
            )
            _check_cancel(cancel_callback)
        if not verified_items:
            _fail("restore_selection_missing")
        _check_cancel(cancel_callback)
        verified = tuple(verified_items)
        anchor = _RestoreContextAnchorV1(saved, result, verified)
        context = DailyMarketTechnicalOfficialDispositionCompositeBookmarkRestoreContextV1(
            bookmark=saved,
            result=result,
            selected=verified[0],
            comparison_selections=verified[1:],
            scope="current_only",
            official_available_at=None,
            availability_status="unknown",
            historical_pit_eligible=False,
            bookmark_is_reader_certification=False,
            _anchor=anchor,
            _seal=_RESTORE_CONTEXT_SEAL_V1,
        )
        _check_cancel(cancel_callback)
        return context
    except DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1Error:
        raise
    except Exception as exc:
        _check_cancel(cancel_callback)
        raise DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1Error(
            "restore_exact_reopen_failed"
        ) from exc
