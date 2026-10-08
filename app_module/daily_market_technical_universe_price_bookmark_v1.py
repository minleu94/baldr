"""F07 價格研究的 versioned bookmark 與 fresh exact 重開。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from typing import NoReturn, cast

from app_module.daily_market_technical_universe_price_comparison_v1 import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_COMPARISON_MAX_ITEMS,
    DailyMarketTechnicalUniversePriceComparisonColumnV1,
    DailyMarketTechnicalUniversePriceComparisonV1,
    DailyMarketTechnicalUniversePriceComparisonV1Error,
    DailyMarketTechnicalUniversePriceSelectionV1,
    VerifiedPriceSelectionV1,
    read_daily_market_technical_universe_price_selections_v1,
)
from app_module.daily_market_technical_universe_price_query_v1 import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_PAGE_BYTES,
    DailyMarketTechnicalUniversePricePageV1,
    DailyMarketTechnicalUniversePriceQueryV1,
    DailyMarketTechnicalUniversePriceQueryV1Error,
)


DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_BOOKMARK_V1_SCHEMA = (
    "daily-market-technical-universe-price-bookmark.v1"
)
DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_BOOKMARK_V1_MAX_BYTES = (
    DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_PAGE_BYTES
)
DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_BOOKMARK_V1_MAX_SCROLL = 2**31 - 1
DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_BOOKMARK_V1_MAX_COMPARISONS = (
    DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_COMPARISON_MAX_ITEMS
)


class DailyMarketTechnicalUniversePriceBookmarkV1Error(ValueError):
    """F07 bookmark 格式或其 fresh source pins 無法驗證。"""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


def _fail(code: str, message: str | None = None) -> NoReturn:
    raise DailyMarketTechnicalUniversePriceBookmarkV1Error(code, message)


def _check_cancel(cancel_callback: Callable[[], object] | None) -> None:
    if cancel_callback is not None and cancel_callback():
        raise InterruptedError("technical_universe_price_bookmark_cancelled")


def _reject_float_tree(value: object) -> None:
    pending: list[tuple[object, int]] = [(value, 0)]
    while pending:
        current, depth = pending.pop()
        if depth > 32:
            _fail("technical_universe_price_bookmark_json_depth_limit")
        if isinstance(current, float):
            _fail("technical_universe_price_bookmark_float_forbidden")
        if isinstance(current, Mapping):
            for key, item in current.items():
                if not isinstance(key, str):
                    _fail("technical_universe_price_bookmark_json_key_invalid")
                pending.append((item, depth + 1))
        elif isinstance(current, (list, tuple)):
            pending.extend((item, depth + 1) for item in current)


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
    except (TypeError, ValueError, RecursionError) as exc:
        raise DailyMarketTechnicalUniversePriceBookmarkV1Error(
            "technical_universe_price_bookmark_json_invalid"
        ) from exc


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _parse_json(raw: bytes | str) -> object:
    try:
        encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
        if not isinstance(encoded, bytes) or len(encoded) > DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_BOOKMARK_V1_MAX_BYTES:
            _fail("technical_universe_price_bookmark_byte_limit")

        def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, item in pairs:
                if key in result:
                    _fail("technical_universe_price_bookmark_duplicate_json_key")
                result[key] = item
            return result

        def reject_constant(value: str) -> NoReturn:
            _fail("technical_universe_price_bookmark_json_constant_invalid", value)

        def reject_float(value: str) -> NoReturn:
            _fail("technical_universe_price_bookmark_float_forbidden", value)

        value = json.loads(
            encoded.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
            parse_float=reject_float,
        )
        _reject_float_tree(value)
        if _canonical_json_bytes(value) != encoded:
            _fail("technical_universe_price_bookmark_json_noncanonical")
        return value
    except DailyMarketTechnicalUniversePriceBookmarkV1Error:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, RecursionError) as exc:
        raise DailyMarketTechnicalUniversePriceBookmarkV1Error(
            "technical_universe_price_bookmark_json_invalid"
        ) from exc


def _validate_comparison_count(value: object) -> None:
    if not isinstance(value, tuple):
        _fail("technical_universe_price_bookmark_comparisons_invalid")
    if len(value) not in {0} and not 2 <= len(value) <= DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_BOOKMARK_V1_MAX_COMPARISONS:
        _fail("technical_universe_price_bookmark_comparison_count_invalid")


def _bookmark_body(
    *,
    selected: DailyMarketTechnicalUniversePriceSelectionV1,
    scroll_position: int,
    comparison_selections: tuple[DailyMarketTechnicalUniversePriceSelectionV1, ...],
) -> dict[str, object]:
    return {
        "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_BOOKMARK_V1_SCHEMA,
        "selected": selected.to_dict(),
        "scroll_position": scroll_position,
        "comparison_selections": [item.to_dict() for item in comparison_selections],
        "source_available_at": None,
        "availability_status": "unknown",
        "historical_pit_eligible": False,
        "bookmark_is_reader_certification": False,
    }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniversePriceBookmarkV1:
    """可保存重開的 F07 請求錨點；收藏本身不授予 reader qualification。"""

    selected: DailyMarketTechnicalUniversePriceSelectionV1
    scroll_position: int
    comparison_selections: tuple[DailyMarketTechnicalUniversePriceSelectionV1, ...]
    bookmark_identity_sha256: str
    schema_version: str = DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_BOOKMARK_V1_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_BOOKMARK_V1_SCHEMA:
            _fail("technical_universe_price_bookmark_schema_invalid")
        if not isinstance(self.selected, DailyMarketTechnicalUniversePriceSelectionV1):
            _fail("technical_universe_price_bookmark_selection_invalid")
        if type(self.scroll_position) is not int or not 0 <= self.scroll_position <= DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_BOOKMARK_V1_MAX_SCROLL:
            _fail("technical_universe_price_bookmark_scroll_invalid")
        _validate_comparison_count(self.comparison_selections)
        if any(not isinstance(item, DailyMarketTechnicalUniversePriceSelectionV1) for item in self.comparison_selections):
            _fail("technical_universe_price_bookmark_comparison_invalid")
        items = (self.selected, *self.comparison_selections)
        component_bytes = 0
        for item in items:
            component_bytes += len(item.to_json().encode("utf-8"))
            if component_bytes > DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_BOOKMARK_V1_MAX_BYTES:
                _fail("technical_universe_price_bookmark_byte_limit")
        keys = tuple(item.key for item in self.comparison_selections)
        if len(set(keys)) != len(keys):
            _fail("technical_universe_price_bookmark_duplicate_selection")
        for item in self.comparison_selections:
            if item.key == self.selected.key and item.to_dict() != self.selected.to_dict():
                _fail("technical_universe_price_bookmark_selected_comparison_conflict")
        body = _bookmark_body(
            selected=self.selected,
            scroll_position=self.scroll_position,
            comparison_selections=self.comparison_selections,
        )
        if self.bookmark_identity_sha256 != _sha256_json(body):
            _fail("technical_universe_price_bookmark_identity_mismatch")
        if len(_canonical_json_bytes({**body, "bookmark_identity_sha256": self.bookmark_identity_sha256})) > DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_BOOKMARK_V1_MAX_BYTES:
            _fail("technical_universe_price_bookmark_byte_limit")

    @classmethod
    def create(
        cls,
        *,
        selected: DailyMarketTechnicalUniversePriceSelectionV1,
        scroll_position: int,
        comparison_selections: Sequence[DailyMarketTechnicalUniversePriceSelectionV1] = (),
    ) -> DailyMarketTechnicalUniversePriceBookmarkV1:
        if isinstance(comparison_selections, (str, bytes)) or not isinstance(comparison_selections, Sequence):
            _fail("technical_universe_price_bookmark_comparisons_invalid")
        comparisons = tuple(comparison_selections)
        _validate_comparison_count(comparisons)
        body = _bookmark_body(
            selected=selected,
            scroll_position=scroll_position,
            comparison_selections=comparisons,
        )
        return cls(
            selected=selected,
            scroll_position=scroll_position,
            comparison_selections=comparisons,
            bookmark_identity_sha256=_sha256_json(body),
        )

    @classmethod
    def from_dict(cls, payload: object) -> DailyMarketTechnicalUniversePriceBookmarkV1:
        expected = {
            "schema_version", "selected", "scroll_position", "comparison_selections",
            "source_available_at", "availability_status", "historical_pit_eligible",
            "bookmark_is_reader_certification", "bookmark_identity_sha256",
        }
        if not isinstance(payload, Mapping) or set(payload) != expected:
            _fail("technical_universe_price_bookmark_fields_invalid")
        if (
            payload["schema_version"] != DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_BOOKMARK_V1_SCHEMA
            or payload["source_available_at"] is not None
            or payload["availability_status"] != "unknown"
            or payload["historical_pit_eligible"] is not False
            or payload["bookmark_is_reader_certification"] is not False
            or type(payload["scroll_position"]) is not int
            or not isinstance(payload["comparison_selections"], list)
        ):
            _fail("technical_universe_price_bookmark_qualification_invalid")
        comparisons = tuple(
            DailyMarketTechnicalUniversePriceSelectionV1.from_dict(item)
            for item in cast(list[object], payload["comparison_selections"])
        )
        result = cls(
            selected=DailyMarketTechnicalUniversePriceSelectionV1.from_dict(payload["selected"]),
            scroll_position=cast(int, payload["scroll_position"]),
            comparison_selections=comparisons,
            bookmark_identity_sha256=cast(str, payload["bookmark_identity_sha256"]),
            schema_version=cast(str, payload["schema_version"]),
        )
        if result.to_dict() != dict(payload):
            _fail("technical_universe_price_bookmark_noncanonical")
        return result

    @classmethod
    def from_json(cls, raw: bytes | str) -> DailyMarketTechnicalUniversePriceBookmarkV1:
        result = cls.from_dict(_parse_json(raw))
        encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
        if result.to_json().encode("utf-8") != encoded:
            _fail("technical_universe_price_bookmark_json_noncanonical")
        return result

    @property
    def identity_sha256(self) -> str:
        return self.bookmark_identity_sha256

    @property
    def source_id(self) -> str:
        return self.bookmark_identity_sha256

    @property
    def bookmark_id(self) -> str:
        return self.bookmark_identity_sha256

    @property
    def stock_code(self) -> str:
        return self.selected.stock_code

    def to_dict(self) -> dict[str, object]:
        body = _bookmark_body(
            selected=self.selected,
            scroll_position=self.scroll_position,
            comparison_selections=self.comparison_selections,
        )
        payload = {**body, "bookmark_identity_sha256": self.bookmark_identity_sha256}
        if len(_canonical_json_bytes(payload)) > DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_BOOKMARK_V1_MAX_BYTES:
            _fail("technical_universe_price_bookmark_byte_limit")
        return payload

    def to_json(self) -> str:
        return _canonical_json_bytes(self.to_dict()).decode("utf-8")


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniversePriceBookmarkStateV1:
    """fresh exact reopen 結果；bookmark 只有在此狀態建立後才有可用頁面。"""

    bookmark: DailyMarketTechnicalUniversePriceBookmarkV1
    selected: VerifiedPriceSelectionV1
    comparison: DailyMarketTechnicalUniversePriceComparisonV1 | None

    def __post_init__(self) -> None:
        if self.selected.selection.to_dict() != self.bookmark.selected.to_dict():
            _fail("technical_universe_price_bookmark_state_selection_mismatch")
        expected_comparisons = self.bookmark.comparison_selections
        if not expected_comparisons and self.comparison is not None:
            _fail("technical_universe_price_bookmark_state_comparison_unexpected")
        if expected_comparisons:
            if self.comparison is None or tuple(
                column.selection.to_dict() for column in self.comparison.columns
            ) != tuple(item.to_dict() for item in expected_comparisons):
                _fail("technical_universe_price_bookmark_state_comparison_mismatch")


def create_daily_market_technical_universe_price_bookmark_v1(
    query: DailyMarketTechnicalUniversePriceQueryV1,
    page: DailyMarketTechnicalUniversePricePageV1,
    stock_code: str,
    *,
    scroll_position: int,
    comparison_selections: Sequence[DailyMarketTechnicalUniversePriceSelectionV1] = (),
) -> DailyMarketTechnicalUniversePriceBookmarkV1:
    """由目前已核頁面建立保存請求；不寫入 watchlist 或來源 store。"""

    try:
        selected = DailyMarketTechnicalUniversePriceSelectionV1.from_page(query, page, stock_code)
        return DailyMarketTechnicalUniversePriceBookmarkV1.create(
            selected=selected,
            scroll_position=scroll_position,
            comparison_selections=comparison_selections,
        )
    except (DailyMarketTechnicalUniversePriceComparisonV1Error, DailyMarketTechnicalUniversePriceQueryV1Error) as exc:
        raise DailyMarketTechnicalUniversePriceBookmarkV1Error(
            getattr(exc, "code", "technical_universe_price_bookmark_create_failed"),
            str(exc),
        ) from exc


def read_daily_market_technical_universe_price_bookmark_v1(
    bookmark: DailyMarketTechnicalUniversePriceBookmarkV1 | bytes | str,
    *,
    cancel_callback: Callable[[], object] | None = None,
) -> DailyMarketTechnicalUniversePriceBookmarkStateV1:
    """只按 bookmark 明示的 query/page/code fresh 重開；不找 latest。"""

    _check_cancel(cancel_callback)
    try:
        if isinstance(bookmark, (bytes, str)):
            saved = DailyMarketTechnicalUniversePriceBookmarkV1.from_json(bookmark)
        elif isinstance(bookmark, DailyMarketTechnicalUniversePriceBookmarkV1):
            saved = DailyMarketTechnicalUniversePriceBookmarkV1.from_dict(bookmark.to_dict())
        else:
            _fail("technical_universe_price_bookmark_type_invalid")
        selections = (saved.selected, *(
            item for item in saved.comparison_selections if item.key != saved.selected.key
        ))
        verified = read_daily_market_technical_universe_price_selections_v1(
            selections,
            cancel_callback=cancel_callback,
        )
    except (
        DailyMarketTechnicalUniversePriceBookmarkV1Error,
        DailyMarketTechnicalUniversePriceComparisonV1Error,
        DailyMarketTechnicalUniversePriceQueryV1Error,
        OSError,
        ValueError,
    ) as exc:
        if isinstance(exc, InterruptedError):
            raise
        raise DailyMarketTechnicalUniversePriceBookmarkV1Error(
            getattr(exc, "code", "technical_universe_price_bookmark_read_failed"),
            str(exc),
        ) from exc
    _check_cancel(cancel_callback)
    if len(verified) != len(selections):
        _fail("technical_universe_price_bookmark_state_incomplete")
    comparison = None
    if saved.comparison_selections:
        verified_by_key = {item.selection.key: item for item in verified}
        columns = tuple(
            DailyMarketTechnicalUniversePriceComparisonColumnV1(verified_by_key[item.key])
            for item in saved.comparison_selections
        )
        comparison = DailyMarketTechnicalUniversePriceComparisonV1.create(columns)
        comparison.to_json()
    _check_cancel(cancel_callback)
    state = DailyMarketTechnicalUniversePriceBookmarkStateV1(
        bookmark=saved,
        selected=verified[0],
        comparison=comparison,
    )
    _check_cancel(cancel_callback)
    return state
