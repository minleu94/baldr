"""固定 full-N v4 查詢、個股與比較選取的唯讀研究收藏。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, NoReturn, cast

from app_module.daily_market_technical_universe_v4_comparison import (
    DailyMarketTechnicalUniverseV4Comparison,
    DailyMarketTechnicalUniverseV4ComparisonError,
    read_daily_market_technical_universe_v4_comparison,
)
from app_module.daily_market_technical_universe_v4_query import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_BYTES,
    DailyMarketTechnicalUniverseV4Page,
    DailyMarketTechnicalUniverseV4Query,
    DailyMarketTechnicalUniverseV4QueryError,
    read_daily_market_technical_universe_v4_page,
)
from app_module.daily_market_technical_universe_v4_stock import (
    DailyMarketTechnicalUniverseV4Stock,
    DailyMarketTechnicalUniverseV4StockError,
    read_daily_market_technical_universe_v4_stock,
)


DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_SCHEMA = "technical-universe-bookmark.v1"
DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_SOURCE = "technical_universe_research_bookmark"
DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_MAX_BYTES = 64 * 1024 * 1024
DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_MAX_COMPARISONS = 256
DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_MAX_SCROLL = 2**31 - 1

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STOCK_CODE_RE = re.compile(r"^[A-Z0-9]{1,16}$")
_SOURCE_IDENTITY_MAX_CHARS = 160
_SELECTION_KEYS = frozenset({
    "query_json",
    "stock_code",
    "snapshot_identity_sha256",
    "source_identity",
})
_BOOKMARK_BODY_KEYS = frozenset({
    "schema_version",
    "source",
    "origin_query_json",
    "selected_stock_code",
    "selected_snapshot_identity_sha256",
    "selected_source_identity",
    "scroll_position",
    "comparison_selections",
})
_BOOKMARK_KEYS = _BOOKMARK_BODY_KEYS | {"bookmark_identity_sha256"}


class DailyMarketTechnicalUniverseV4BookmarkError(ValueError):
    """bookmark 格式或固定來源 pin 無法驗證。"""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


def _fail(code: str, message: str | None = None) -> NoReturn:
    raise DailyMarketTechnicalUniverseV4BookmarkError(code, message)


def _reject_float_tree(value: object) -> None:
    if isinstance(value, float):
        _fail("technical_universe_v4_bookmark_float_forbidden")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                _fail("technical_universe_v4_bookmark_json_key_invalid")
            _reject_float_tree(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_float_tree(item)


def _canonical_json_bytes(value: object) -> bytes:
    _reject_float_tree(value)
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise DailyMarketTechnicalUniverseV4BookmarkError(
            "technical_universe_v4_bookmark_json_invalid"
        ) from exc


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _parse_json(raw: bytes | str) -> object:
    try:
        encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
        if len(encoded) > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_MAX_BYTES:
            _fail("technical_universe_v4_bookmark_byte_limit")

        def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, item in pairs:
                if key in result:
                    _fail("technical_universe_v4_bookmark_duplicate_json_key")
                result[key] = item
            return result

        def reject_constant(value: str) -> NoReturn:
            _fail("technical_universe_v4_bookmark_json_constant_invalid", value)

        def reject_float(value: str) -> NoReturn:
            _fail("technical_universe_v4_bookmark_float_forbidden", value)

        value = json.loads(
            encoded.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
            parse_float=reject_float,
        )
        _reject_float_tree(value)
        if _canonical_json_bytes(value) != encoded:
            _fail("technical_universe_v4_bookmark_json_noncanonical")
        return value
    except DailyMarketTechnicalUniverseV4BookmarkError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalUniverseV4BookmarkError(
            "technical_universe_v4_bookmark_json_invalid"
        ) from exc


def _validate_stock_code(value: object) -> str:
    if not isinstance(value, str) or _STOCK_CODE_RE.fullmatch(value) is None:
        _fail("technical_universe_v4_bookmark_stock_code_invalid")
    return value


def _validate_sha256(value: object, code: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail(code)
    return value


def _validate_source_identity(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > _SOURCE_IDENTITY_MAX_CHARS
    ):
        _fail("technical_universe_v4_bookmark_source_identity_invalid")
    return value


def _query_from_json(value: object) -> DailyMarketTechnicalUniverseV4Query:
    if not isinstance(value, str):
        _fail("technical_universe_v4_bookmark_query_json_invalid")
    if len(value.encode("utf-8")) > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_BYTES:
        _fail("technical_universe_v4_bookmark_query_byte_limit")
    try:
        query = DailyMarketTechnicalUniverseV4Query.from_json(value)
    except (DailyMarketTechnicalUniverseV4QueryError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalUniverseV4BookmarkError(
            "technical_universe_v4_bookmark_query_invalid"
        ) from exc
    if query.to_json() != value:
        _fail("technical_universe_v4_bookmark_query_json_noncanonical")
    return query


def _source_stock_key(query: DailyMarketTechnicalUniverseV4Query, stock_code: str) -> tuple[str, str, str, str]:
    return (
        query.store_output_root,
        query.generation_identity_sha256,
        query.receipt_identity_sha256,
        stock_code,
    )


def _validate_comparison_count(value: object) -> None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        _fail("technical_universe_v4_bookmark_comparisons_invalid")
    count = len(value)
    if count != 0 and not 2 <= count <= DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_MAX_COMPARISONS:
        _fail("technical_universe_v4_bookmark_comparison_count_invalid")


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniverseV4BookmarkSelection:
    """單一比較欄保留原查詢、股票與已核驗的來源身份。"""

    query_json: str
    stock_code: str
    snapshot_identity_sha256: str
    source_identity: str

    def __post_init__(self) -> None:
        _query_from_json(self.query_json)
        _validate_stock_code(self.stock_code)
        _validate_sha256(
            self.snapshot_identity_sha256,
            "technical_universe_v4_bookmark_snapshot_identity_invalid",
        )
        _validate_source_identity(self.source_identity)

    @classmethod
    def from_dict(cls, payload: object) -> DailyMarketTechnicalUniverseV4BookmarkSelection:
        if not isinstance(payload, Mapping) or set(payload) != _SELECTION_KEYS:
            _fail("technical_universe_v4_bookmark_selection_fields_invalid")
        return cls(
            query_json=cast(str, payload["query_json"]),
            stock_code=cast(str, payload["stock_code"]),
            snapshot_identity_sha256=cast(str, payload["snapshot_identity_sha256"]),
            source_identity=cast(str, payload["source_identity"]),
        )

    def to_dict(self) -> dict[str, str]:
        payload = {
            "query_json": self.query_json,
            "stock_code": self.stock_code,
            "snapshot_identity_sha256": self.snapshot_identity_sha256,
            "source_identity": self.source_identity,
        }
        self.from_dict(payload)
        return payload

    @property
    def query(self) -> DailyMarketTechnicalUniverseV4Query:
        return _query_from_json(self.query_json)


def _selection_source_key(
    selection: DailyMarketTechnicalUniverseV4BookmarkSelection,
) -> tuple[str, str, str, str]:
    return _source_stock_key(selection.query, selection.stock_code)


def _bookmark_body(
    *,
    origin_query_json: str,
    selected_stock_code: str,
    selected_snapshot_identity_sha256: str,
    selected_source_identity: str,
    scroll_position: int,
    comparison_selections: tuple[DailyMarketTechnicalUniverseV4BookmarkSelection, ...],
) -> dict[str, Any]:
    return {
        "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_SCHEMA,
        "source": DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_SOURCE,
        "origin_query_json": origin_query_json,
        "selected_stock_code": selected_stock_code,
        "selected_snapshot_identity_sha256": selected_snapshot_identity_sha256,
        "selected_source_identity": selected_source_identity,
        "scroll_position": scroll_position,
        "comparison_selections": [item.to_dict() for item in comparison_selections],
    }


def _validate_bookmark_payload(payload: object) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or set(payload) != _BOOKMARK_KEYS:
        _fail("technical_universe_v4_bookmark_fields_invalid")
    body = dict(payload)
    if body["schema_version"] != DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_SCHEMA:
        _fail("technical_universe_v4_bookmark_schema_invalid")
    if body["source"] != DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_SOURCE:
        _fail("technical_universe_v4_bookmark_source_invalid")
    _query_from_json(body["origin_query_json"])
    _validate_stock_code(body["selected_stock_code"])
    _validate_sha256(
        body["selected_snapshot_identity_sha256"],
        "technical_universe_v4_bookmark_snapshot_identity_invalid",
    )
    _validate_source_identity(body["selected_source_identity"])
    scroll_position = body["scroll_position"]
    if (
        type(scroll_position) is not int
        or not 0 <= scroll_position <= DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_MAX_SCROLL
    ):
        _fail("technical_universe_v4_bookmark_scroll_invalid")
    selections = body["comparison_selections"]
    _validate_comparison_count(selections)
    parsed_selections = tuple(
        DailyMarketTechnicalUniverseV4BookmarkSelection.from_dict(item)
        for item in cast(Sequence[object], selections)
    )
    keys = tuple(_selection_source_key(item) for item in parsed_selections)
    if len(set(keys)) != len(keys):
        _fail("technical_universe_v4_bookmark_duplicate_comparison")
    identity = _validate_sha256(
        body["bookmark_identity_sha256"],
        "technical_universe_v4_bookmark_identity_invalid",
    )
    identity_body = {key: value for key, value in body.items() if key != "bookmark_identity_sha256"}
    if _sha256_json(identity_body) != identity:
        _fail("technical_universe_v4_bookmark_identity_mismatch")
    body["comparison_selections"] = parsed_selections
    return body


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniverseV4Bookmark:
    """不變的原查詢、下鑽身份、捲動位置與比較欄保存契約。"""

    origin_query_json: str
    selected_stock_code: str
    selected_snapshot_identity_sha256: str
    selected_source_identity: str
    scroll_position: int
    comparison_selections: tuple[DailyMarketTechnicalUniverseV4BookmarkSelection, ...]
    bookmark_identity_sha256: str

    def __post_init__(self) -> None:
        payload = _bookmark_body(
            origin_query_json=self.origin_query_json,
            selected_stock_code=self.selected_stock_code,
            selected_snapshot_identity_sha256=self.selected_snapshot_identity_sha256,
            selected_source_identity=self.selected_source_identity,
            scroll_position=self.scroll_position,
            comparison_selections=self.comparison_selections,
        )
        payload["bookmark_identity_sha256"] = self.bookmark_identity_sha256
        _validate_bookmark_payload(payload)

    @classmethod
    def from_dict(cls, payload: object) -> DailyMarketTechnicalUniverseV4Bookmark:
        parsed = _validate_bookmark_payload(payload)
        return cls(
            origin_query_json=cast(str, parsed["origin_query_json"]),
            selected_stock_code=cast(str, parsed["selected_stock_code"]),
            selected_snapshot_identity_sha256=cast(
                str, parsed["selected_snapshot_identity_sha256"]
            ),
            selected_source_identity=cast(str, parsed["selected_source_identity"]),
            scroll_position=cast(int, parsed["scroll_position"]),
            comparison_selections=cast(
                tuple[DailyMarketTechnicalUniverseV4BookmarkSelection, ...],
                parsed["comparison_selections"],
            ),
            bookmark_identity_sha256=cast(str, parsed["bookmark_identity_sha256"]),
        )

    @classmethod
    def from_json(cls, raw: bytes | str) -> DailyMarketTechnicalUniverseV4Bookmark:
        return cls.from_dict(_parse_json(raw))

    def to_dict(self) -> dict[str, Any]:
        body = _bookmark_body(
            origin_query_json=self.origin_query_json,
            selected_stock_code=self.selected_stock_code,
            selected_snapshot_identity_sha256=self.selected_snapshot_identity_sha256,
            selected_source_identity=self.selected_source_identity,
            scroll_position=self.scroll_position,
            comparison_selections=self.comparison_selections,
        )
        payload = {**body, "bookmark_identity_sha256": self.bookmark_identity_sha256}
        _validate_bookmark_payload(payload)
        if len(_canonical_json_bytes(payload)) > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_MAX_BYTES:
            _fail("technical_universe_v4_bookmark_byte_limit")
        return payload

    def to_json(self) -> str:
        return _canonical_json_bytes(self.to_dict()).decode("utf-8")

    @property
    def identity_sha256(self) -> str:
        return self.bookmark_identity_sha256

    @property
    def bookmark_id(self) -> str:
        return self.bookmark_identity_sha256

    @property
    def source_id(self) -> str:
        return self.bookmark_identity_sha256

    @property
    def stock_code(self) -> str:
        return self.selected_stock_code

    @property
    def stock_name(self) -> str:
        return ""

    @property
    def source(self) -> str:
        return DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_SOURCE

    @property
    def origin_query(self) -> DailyMarketTechnicalUniverseV4Query:
        return _query_from_json(self.origin_query_json)


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniverseV4BookmarkState:
    """bookmark 精確重開後可交給 UI 還原的已驗證唯讀結果。"""

    bookmark: DailyMarketTechnicalUniverseV4Bookmark
    origin_page: DailyMarketTechnicalUniverseV4Page
    selected_stock: DailyMarketTechnicalUniverseV4Stock
    comparison: DailyMarketTechnicalUniverseV4Comparison | None


def _check_cancel(callback: Callable[[], bool] | None) -> None:
    if callback is None:
        return
    try:
        value = callback()
    except Exception as exc:
        raise DailyMarketTechnicalUniverseV4BookmarkError(
            "technical_universe_v4_bookmark_cancel_check_failed"
        ) from exc
    if type(value) is not bool:
        _fail("technical_universe_v4_bookmark_cancel_callback_invalid")
    if value:
        _fail("technical_universe_v4_bookmark_cancelled")


def _raise_reader_error(exc: Exception) -> NoReturn:
    code = getattr(exc, "code", "technical_universe_v4_bookmark_source_read_failed")
    if "cancel" in str(code).lower():
        _fail("technical_universe_v4_bookmark_cancelled")
    _fail(f"technical_universe_v4_bookmark_source_rejected_{code}")


def _read_page(
    query: DailyMarketTechnicalUniverseV4Query,
    cancel_callback: Callable[[], bool] | None,
) -> DailyMarketTechnicalUniverseV4Page:
    try:
        return read_daily_market_technical_universe_v4_page(
            query,
            cancel_callback=cancel_callback,
        )
    except DailyMarketTechnicalUniverseV4QueryError as exc:
        _raise_reader_error(exc)


def _read_stock(
    query: DailyMarketTechnicalUniverseV4Query,
    stock_code: str,
    cancel_callback: Callable[[], bool] | None,
) -> DailyMarketTechnicalUniverseV4Stock:
    try:
        return read_daily_market_technical_universe_v4_stock(
            query,
            stock_code,
            cancel_callback=cancel_callback,
        )
    except DailyMarketTechnicalUniverseV4StockError as exc:
        _raise_reader_error(exc)


def _parse_selection_requests(
    value: object,
) -> tuple[tuple[DailyMarketTechnicalUniverseV4Query, str], ...]:
    _validate_comparison_count(value)
    results: list[tuple[DailyMarketTechnicalUniverseV4Query, str]] = []
    keys: set[tuple[str, str, str, str]] = set()
    for item in cast(Sequence[object], value):
        if not isinstance(item, tuple) or len(item) != 2:
            _fail("technical_universe_v4_bookmark_comparison_invalid")
        query, raw_stock_code = item
        if not isinstance(query, DailyMarketTechnicalUniverseV4Query):
            _fail("technical_universe_v4_bookmark_query_invalid")
        stock_code = _validate_stock_code(raw_stock_code)
        key = _source_stock_key(query, stock_code)
        if key in keys:
            _fail("technical_universe_v4_bookmark_duplicate_comparison")
        keys.add(key)
        results.append((query, stock_code))
    return tuple(results)


def _read_comparison(
    selections: tuple[tuple[DailyMarketTechnicalUniverseV4Query, str], ...],
    cancel_callback: Callable[[], bool] | None,
) -> DailyMarketTechnicalUniverseV4Comparison:
    try:
        return read_daily_market_technical_universe_v4_comparison(
            selections,
            cancel_callback=cancel_callback,
        )
    except DailyMarketTechnicalUniverseV4ComparisonError as exc:
        _raise_reader_error(exc)


def _comparison_pins(
    comparison: DailyMarketTechnicalUniverseV4Comparison,
    expected: tuple[tuple[DailyMarketTechnicalUniverseV4Query, str], ...],
) -> tuple[DailyMarketTechnicalUniverseV4BookmarkSelection, ...]:
    if len(comparison.columns) != len(expected):
        _fail("technical_universe_v4_bookmark_comparison_count_mismatch")
    selections: list[DailyMarketTechnicalUniverseV4BookmarkSelection] = []
    for column, (query, stock_code) in zip(comparison.columns, expected, strict=True):
        row = column.row
        if column.origin_query != query or row.stock_code != stock_code:
            _fail("technical_universe_v4_bookmark_comparison_source_mismatch")
        selections.append(
            DailyMarketTechnicalUniverseV4BookmarkSelection(
                query_json=query.to_json(),
                stock_code=row.stock_code,
                snapshot_identity_sha256=row.snapshot_identity_sha256,
                source_identity=row.source_identity,
            )
        )
    return tuple(selections)


def _new_bookmark(
    *,
    query: DailyMarketTechnicalUniverseV4Query,
    selected_stock_code: str,
    selected_snapshot_identity_sha256: str,
    selected_source_identity: str,
    scroll_position: int,
    comparison_selections: tuple[DailyMarketTechnicalUniverseV4BookmarkSelection, ...],
) -> DailyMarketTechnicalUniverseV4Bookmark:
    body = _bookmark_body(
        origin_query_json=query.to_json(),
        selected_stock_code=selected_stock_code,
        selected_snapshot_identity_sha256=selected_snapshot_identity_sha256,
        selected_source_identity=selected_source_identity,
        scroll_position=scroll_position,
        comparison_selections=comparison_selections,
    )
    body["bookmark_identity_sha256"] = _sha256_json(body)
    if len(_canonical_json_bytes(body)) > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_MAX_BYTES:
        _fail("technical_universe_v4_bookmark_byte_limit")
    return DailyMarketTechnicalUniverseV4Bookmark.from_dict(body)


def create_daily_market_technical_universe_v4_bookmark(
    query: DailyMarketTechnicalUniverseV4Query,
    selected_stock_code: str,
    *,
    scroll_position: int,
    comparison_selections: Sequence[
        tuple[DailyMarketTechnicalUniverseV4Query, str]
    ] = (),
    cancel_callback: Callable[[], bool] | None = None,
) -> DailyMarketTechnicalUniverseV4Bookmark:
    """由真實 strict 頁面、個股與比較 reader 建立固定研究收藏。"""

    if not isinstance(query, DailyMarketTechnicalUniverseV4Query):
        _fail("technical_universe_v4_bookmark_query_invalid")
    code = _validate_stock_code(selected_stock_code)
    if (
        type(scroll_position) is not int
        or not 0 <= scroll_position <= DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_MAX_SCROLL
    ):
        _fail("technical_universe_v4_bookmark_scroll_invalid")
    selections = _parse_selection_requests(comparison_selections)
    _check_cancel(cancel_callback)
    page = _read_page(query, cancel_callback)
    row = next((item for item in page.rows if item.stock_code == code), None)
    if row is None:
        _fail("technical_universe_v4_bookmark_selected_stock_not_in_page")
    _check_cancel(cancel_callback)
    stock = _read_stock(query, code, cancel_callback)
    if (
        stock.origin_query != query
        or stock.snapshot.stock_code != row.stock_code
        or stock.snapshot.snapshot_identity_sha256 != row.snapshot_identity_sha256
        or stock.snapshot.source_identity != row.source_identity
    ):
        _fail("technical_universe_v4_bookmark_selected_stock_pin_mismatch")
    persisted_comparisons: tuple[DailyMarketTechnicalUniverseV4BookmarkSelection, ...] = ()
    if selections:
        _check_cancel(cancel_callback)
        comparison = _read_comparison(selections, cancel_callback)
        persisted_comparisons = _comparison_pins(comparison, selections)
    _check_cancel(cancel_callback)
    return _new_bookmark(
        query=query,
        selected_stock_code=code,
        selected_snapshot_identity_sha256=stock.snapshot.snapshot_identity_sha256,
        selected_source_identity=stock.snapshot.source_identity,
        scroll_position=scroll_position,
        comparison_selections=persisted_comparisons,
    )


def _coerce_bookmark(
    value: DailyMarketTechnicalUniverseV4Bookmark | Mapping[str, object] | bytes | str,
) -> DailyMarketTechnicalUniverseV4Bookmark:
    if isinstance(value, DailyMarketTechnicalUniverseV4Bookmark):
        return DailyMarketTechnicalUniverseV4Bookmark.from_dict(value.to_dict())
    if isinstance(value, (bytes, str)):
        return DailyMarketTechnicalUniverseV4Bookmark.from_json(value)
    return DailyMarketTechnicalUniverseV4Bookmark.from_dict(value)


def read_daily_market_technical_universe_v4_bookmark(
    bookmark: DailyMarketTechnicalUniverseV4Bookmark | Mapping[str, object] | bytes | str,
    *,
    cancel_callback: Callable[[], bool] | None = None,
) -> DailyMarketTechnicalUniverseV4BookmarkState:
    """固定重開 bookmark 所存 query/stock/comparison；不讀 latest 或來源 DB。"""

    saved = _coerce_bookmark(bookmark)
    _check_cancel(cancel_callback)
    query = saved.origin_query
    page = _read_page(query, cancel_callback)
    row = next((item for item in page.rows if item.stock_code == saved.selected_stock_code), None)
    if row is None:
        _fail("technical_universe_v4_bookmark_selected_stock_not_in_page")
    if (
        row.snapshot_identity_sha256 != saved.selected_snapshot_identity_sha256
        or row.source_identity != saved.selected_source_identity
    ):
        _fail("technical_universe_v4_bookmark_selected_stock_pin_mismatch")
    _check_cancel(cancel_callback)
    stock = _read_stock(query, saved.selected_stock_code, cancel_callback)
    if (
        stock.snapshot.snapshot_identity_sha256 != saved.selected_snapshot_identity_sha256
        or stock.snapshot.source_identity != saved.selected_source_identity
    ):
        _fail("technical_universe_v4_bookmark_selected_snapshot_changed")

    comparison: DailyMarketTechnicalUniverseV4Comparison | None = None
    if saved.comparison_selections:
        _check_cancel(cancel_callback)
        expected = tuple(
            (item.query, item.stock_code)
            for item in saved.comparison_selections
        )
        comparison = _read_comparison(expected, cancel_callback)
        actual_pins = _comparison_pins(comparison, expected)
        if actual_pins != saved.comparison_selections:
            _fail("technical_universe_v4_bookmark_comparison_pin_mismatch")
    _check_cancel(cancel_callback)
    return DailyMarketTechnicalUniverseV4BookmarkState(
        bookmark=saved,
        origin_page=page,
        selected_stock=stock,
        comparison=comparison,
    )
