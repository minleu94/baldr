"""F17／MA 複合研究收藏 DTO 與 exact reader 重開。

此命名空間採 64 MiB canonical 序列化上限，與舊 F17 2 MiB bookmark DTO
分開解碼；接入 Watchlist 時必須按本 schema 使用此 decoder，禁止截斷後轉交舊 DTO。
目前 Watchlist primary 以整檔 bytes 讀取，沒有本 leaf 可依賴的全檔 byte cap。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import TYPE_CHECKING, Literal, NoReturn, cast

from app_module.daily_market_technical_official_disposition_ma_comparison_v1 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_COMPARISON_V1_MAX_ITEMS,
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_SELECTION_V1_MAX_ROW_BYTES,
    DailyMarketTechnicalOfficialDispositionMaComparisonV1,
    DailyMarketTechnicalOfficialDispositionMaComparisonV1Error,
    DailyMarketTechnicalOfficialDispositionMaSelectionV1,
    DailyMarketTechnicalOfficialDispositionMaVerifiedSelectionV1,
    DailyMarketTechnicalOfficialDispositionMaVerifiedQueryResultV1,
    _read_daily_market_technical_official_disposition_ma_selections_with_result_v1,
)
from app_module.daily_market_technical_official_disposition_ma_query_v1 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_QUERY_V1_MAX_BYTES,
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_SORT_CLAUSES,
    DailyMarketTechnicalOfficialDispositionMaPageRequestV1,
    DailyMarketTechnicalOfficialDispositionMaQueryPageV1,
    DailyMarketTechnicalOfficialDispositionMaQueryV1,
    DailyMarketTechnicalOfficialDispositionMaSortClauseV1,
    MaState,
    UnknownPolicy,
)
from app_module.daily_market_technical_method_contract_v4 import (
    DAILY_MARKET_TECHNICAL_RULE_KEYS_V4,
)
from app_module.daily_market_technical_parent_v4_query import (
    DailyMarketTechnicalRuleStateFilterV4,
)
from app_module.daily_market_technical_official_disposition_query_v1 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_QUERY_V1_MAX_SORT_CLAUSES,
    RowScope,
)
from app_module.daily_market_technical_universe_v4_query import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS,
)

if TYPE_CHECKING:
    from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
        DailyMarketTechnicalOfficialDispositionSortClauseV1,
    )


DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_BOOKMARK_V1_SCHEMA = (
    "daily-market-technical-official-disposition-ma-bookmark.v1"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_RESEARCH_BOOKMARK_SOURCE = (
    "technical_official_disposition_ma_research_bookmark"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_BOOKMARK_V1_MAX_BYTES = 64 * 1024 * 1024
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_BOOKMARK_V1_MAX_SCROLL = 10_000_000

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_BOOKMARK_SEAL = object()
_STATE_SEAL = object()
_RESTORE_CONTEXT_SEAL = object()


class DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error(ValueError):
    """MA 收藏資料格式錯誤。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error(
        f"technical_official_ma_bookmark_v1_{code}"
    )


def _bounded_sequence_items(
    value: object,
    *,
    maximum: int,
    code: str,
) -> tuple[object, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _fail(code)
    try:
        iterator = iter(value)
        items: list[object] = []
        for _ in range(maximum + 1):
            try:
                items.append(next(iterator))
            except StopIteration:
                return tuple(items)
    except DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error:
        raise
    except Exception as exc:
        raise DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error(
            f"technical_official_ma_bookmark_v1_{code}"
        ) from exc
    _fail(code)


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
        raise DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error(
            "technical_official_ma_bookmark_v1_json_invalid"
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
        if not isinstance(encoded, bytes) or len(encoded) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_BOOKMARK_V1_MAX_BYTES:
            _fail("byte_limit")
        text = encoded.decode("utf-8")
        _preflight_depth(text)
        payload = json.loads(
            text,
            object_pairs_hook=_unique_pairs,
            parse_float=lambda _value: _fail("float_forbidden"),
            parse_constant=lambda _value: _fail("json_constant_invalid"),
        )
        if _canonical_json_bytes(payload) != encoded:
            _fail("json_noncanonical")
        return payload
    except DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error(
            "technical_official_ma_bookmark_v1_json_invalid"
        ) from exc


def _check_cancel(callback: Callable[[], object] | None) -> None:
    if callback is None:
        return
    if not callable(callback):
        _fail("cancel_callback_invalid")
    try:
        value = callback()
    except Exception as exc:
        raise DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error(
            "technical_official_ma_bookmark_v1_cancel_check_failed"
        ) from exc
    if type(value) is not bool:
        _fail("cancel_callback_invalid")
    if value:
        _fail("cancelled")


def _selection_sequence(value: object, *, allow_empty: bool) -> tuple[DailyMarketTechnicalOfficialDispositionMaSelectionV1, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _fail("comparison_invalid")
    result: list[DailyMarketTechnicalOfficialDispositionMaSelectionV1] = []
    try:
        iterator = iter(value)
        for _ in range(DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_COMPARISON_V1_MAX_ITEMS + 1):
            try:
                item = next(iterator)
            except StopIteration:
                break
            if type(item) is not DailyMarketTechnicalOfficialDispositionMaSelectionV1:
                _fail("comparison_invalid")
            result.append(item)
    except DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error:
        raise
    except Exception as exc:
        raise DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error(
            "technical_official_ma_bookmark_v1_comparison_invalid"
        ) from exc
    if len(result) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_COMPARISON_V1_MAX_ITEMS:
        _fail("comparison_count_invalid")
    if (not allow_empty or result) and not 2 <= len(result) <= DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_COMPARISON_V1_MAX_ITEMS:
        _fail("comparison_count_invalid")
    if len({item.stock_code for item in result}) != len(result):
        _fail("comparison_duplicate_stock")
    return tuple(result)


def _validate_query_context(
    query_json: str,
    selection: DailyMarketTechnicalOfficialDispositionMaSelectionV1,
) -> DailyMarketTechnicalOfficialDispositionMaQueryV1:
    if not isinstance(query_json, str) or len(query_json.encode("utf-8")) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_QUERY_V1_MAX_BYTES:
        _fail("query_invalid")
    query = DailyMarketTechnicalOfficialDispositionMaQueryV1.from_json(query_json)
    if query.to_json() != query_json or query.query_identity_sha256 != selection.query_identity_sha256:
        _fail("query_selection_mismatch")
    request = DailyMarketTechnicalOfficialDispositionMaPageRequestV1.create(
        query, page_index=selection.page_index, page_size=selection.page_size,
    )
    if request.request_identity_sha256 != selection.page_request_identity_sha256:
        _fail("selection_request_mismatch")
    return query


def _validate_selection_context(
    query: DailyMarketTechnicalOfficialDispositionMaQueryV1,
    selection: DailyMarketTechnicalOfficialDispositionMaSelectionV1,
) -> None:
    if selection.query_identity_sha256 != query.query_identity_sha256:
        _fail("query_selection_mismatch")
    request = DailyMarketTechnicalOfficialDispositionMaPageRequestV1.create(
        query, page_index=selection.page_index, page_size=selection.page_size,
    )
    if request.request_identity_sha256 != selection.page_request_identity_sha256:
        _fail("selection_request_mismatch")


def _bookmark_body(
    *,
    query_json: str,
    selected: DailyMarketTechnicalOfficialDispositionMaSelectionV1,
    scroll_position: int,
    comparison_selections: tuple[DailyMarketTechnicalOfficialDispositionMaSelectionV1, ...],
) -> dict[str, object]:
    return {
        "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_BOOKMARK_V1_SCHEMA,
        "query_json": query_json,
        "selected": selected.to_dict(),
        "scroll_position": scroll_position,
        "comparison_selections": [item.to_dict() for item in comparison_selections],
        "source_pins": [[key, value] for key, value in selected.source_pins],
        "ma_alignment_read_session_identity_sha256": selected.ma_alignment_read_session_identity_sha256,
        "ma_alignment_index_identity_sha256": selected.ma_alignment_index_identity_sha256,
        "ma_source_request_identity_sha256": selected.ma_source_request_identity_sha256,
        "source_available_at": None,
        "availability_status": "unknown",
        "historical_pit_eligible": False,
        "bookmark_is_reader_certification": False,
    }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionMaBookmarkV1:
    """保存 canonical MA query、獨立頁請求與列身份，不保存 reader qualification。"""

    query_json: str
    selected: DailyMarketTechnicalOfficialDispositionMaSelectionV1
    scroll_position: int
    comparison_selections: tuple[DailyMarketTechnicalOfficialDispositionMaSelectionV1, ...]
    bookmark_identity_sha256: str
    schema_version: str = DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_BOOKMARK_V1_SCHEMA

    def __post_init__(self) -> None:
        query = _validate_query_context(self.query_json, self.selected)
        comparisons = _selection_sequence(self.comparison_selections, allow_empty=True)
        for item in comparisons:
            _validate_selection_context(query, item)
        if (
            self.schema_version != DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_BOOKMARK_V1_SCHEMA
            or type(self.scroll_position) is not int
            or not 0 <= self.scroll_position <= DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_BOOKMARK_V1_MAX_SCROLL
            or any(item.query_identity_sha256 != query.query_identity_sha256 for item in comparisons)
            or any(item.source_pins != self.selected.source_pins for item in comparisons)
            or any(item.result_identity_sha256 != self.selected.result_identity_sha256 for item in comparisons)
            or any(item.ma_alignment_read_session_identity_sha256 != self.selected.ma_alignment_read_session_identity_sha256 for item in comparisons)
            or any(item.ma_alignment_index_identity_sha256 != self.selected.ma_alignment_index_identity_sha256 for item in comparisons)
            or any(item.ma_source_request_identity_sha256 != self.selected.ma_source_request_identity_sha256 for item in comparisons)
            or any(item.stock_code == self.selected.stock_code and item.to_dict() != self.selected.to_dict() for item in comparisons)
        ):
            _fail("bookmark_fields_invalid")
        _require_digest(self.bookmark_identity_sha256, "bookmark_identity_invalid")
        if self.bookmark_identity_sha256 != _sha256_json(
            _bookmark_body(
                query_json=self.query_json,
                selected=self.selected,
                scroll_position=self.scroll_position,
                comparison_selections=comparisons,
            )
        ):
            _fail("bookmark_identity_mismatch")
        if len(_canonical_json_bytes(self.to_dict())) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_BOOKMARK_V1_MAX_BYTES:
            _fail("byte_limit")

    @classmethod
    def create(
        cls,
        *,
        query: DailyMarketTechnicalOfficialDispositionMaQueryV1,
        page: DailyMarketTechnicalOfficialDispositionMaQueryPageV1,
        stock_code: str,
        scroll_position: int,
        comparison_selections: Sequence[DailyMarketTechnicalOfficialDispositionMaSelectionV1] = (),
    ) -> DailyMarketTechnicalOfficialDispositionMaBookmarkV1:
        if type(query) is not DailyMarketTechnicalOfficialDispositionMaQueryV1:
            _fail("query_type_invalid")
        if type(page) is not DailyMarketTechnicalOfficialDispositionMaQueryPageV1:
            _fail("page_type_invalid")
        selected = DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_page(
            page, stock_code,
        )
        if selected.query_identity_sha256 != query.query_identity_sha256:
            _fail("selected_query_mismatch")
        comparisons = _selection_sequence(comparison_selections, allow_empty=True)
        body = _bookmark_body(
            query_json=query.to_json(),
            selected=selected,
            scroll_position=scroll_position,
            comparison_selections=comparisons,
        )
        return cls(
            query_json=query.to_json(),
            selected=selected,
            scroll_position=scroll_position,
            comparison_selections=comparisons,
            bookmark_identity_sha256=_sha256_json(body),
        )

    @classmethod
    def from_dict(cls, payload: object) -> DailyMarketTechnicalOfficialDispositionMaBookmarkV1:
        expected = {
            "schema_version", "query_json", "selected", "scroll_position",
            "comparison_selections", "source_pins",
            "ma_alignment_read_session_identity_sha256", "ma_alignment_index_identity_sha256",
            "ma_source_request_identity_sha256", "source_available_at", "availability_status",
            "historical_pit_eligible", "bookmark_is_reader_certification", "bookmark_identity_sha256",
        }
        if not isinstance(payload, Mapping) or set(payload) != expected:
            _fail("bookmark_fields_invalid")
        if (
            payload.get("schema_version") != DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_BOOKMARK_V1_SCHEMA
            or payload.get("source_available_at") is not None
            or payload.get("availability_status") != "unknown"
            or payload.get("historical_pit_eligible") is not False
            or payload.get("bookmark_is_reader_certification") is not False
            or type(payload.get("scroll_position")) is not int
        ):
            _fail("bookmark_qualification_invalid")
        selected = DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_dict(payload.get("selected"))
        raw_comparisons = payload.get("comparison_selections")
        if not isinstance(raw_comparisons, list):
            _fail("comparison_invalid")
        comparisons = tuple(DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_dict(item) for item in raw_comparisons)
        raw_pins = payload.get("source_pins")
        if not isinstance(raw_pins, list):
            _fail("source_pins_invalid")
        try:
            parsed_pins = tuple((cast(str, item[0]), cast(str, item[1])) for item in raw_pins if isinstance(item, list) and len(item) == 2)
        except (TypeError, IndexError) as exc:
            raise DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error(
                "technical_official_ma_bookmark_v1_source_pins_invalid"
            ) from exc
        if len(parsed_pins) != len(raw_pins) or parsed_pins != selected.source_pins:
            _fail("source_pins_mismatch")
        if (
            payload.get("ma_alignment_read_session_identity_sha256") != selected.ma_alignment_read_session_identity_sha256
            or payload.get("ma_alignment_index_identity_sha256") != selected.ma_alignment_index_identity_sha256
            or payload.get("ma_source_request_identity_sha256") != selected.ma_source_request_identity_sha256
        ):
            _fail("source_identity_mismatch")
        result = cls(
            query_json=cast(str, payload.get("query_json")),
            selected=selected,
            scroll_position=cast(int, payload.get("scroll_position")),
            comparison_selections=comparisons,
            bookmark_identity_sha256=cast(str, payload.get("bookmark_identity_sha256")),
            schema_version=cast(str, payload.get("schema_version")),
        )
        if result.to_dict() != dict(payload):
            _fail("bookmark_noncanonical")
        return result

    @classmethod
    def from_json(cls, raw: bytes | str) -> DailyMarketTechnicalOfficialDispositionMaBookmarkV1:
        payload = _parse_json(raw)
        result = cls.from_dict(payload)
        encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
        if result.to_json().encode("utf-8") != encoded:
            _fail("bookmark_noncanonical")
        return result

    @property
    def bookmark_id(self) -> str:
        return self.bookmark_identity_sha256

    @property
    def stock_code(self) -> str:
        return self.selected.stock_code

    @property
    def stock_name(self) -> str:
        return f"{self.selected.stock_code}／研究收藏"

    @property
    def source(self) -> str:
        return DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_RESEARCH_BOOKMARK_SOURCE

    @property
    def query(self) -> DailyMarketTechnicalOfficialDispositionMaQueryV1:
        return DailyMarketTechnicalOfficialDispositionMaQueryV1.from_json(self.query_json)

    def to_dict(self) -> dict[str, object]:
        body = _bookmark_body(
            query_json=self.query_json,
            selected=self.selected,
            scroll_position=self.scroll_position,
            comparison_selections=self.comparison_selections,
        )
        return {
            **body,
            "source_pins": [[key, value] for key, value in self.selected.source_pins],
            "ma_alignment_read_session_identity_sha256": self.selected.ma_alignment_read_session_identity_sha256,
            "ma_alignment_index_identity_sha256": self.selected.ma_alignment_index_identity_sha256,
            "ma_source_request_identity_sha256": self.selected.ma_source_request_identity_sha256,
            "bookmark_identity_sha256": self.bookmark_identity_sha256,
        }

    def to_json(self) -> str:
        raw = _canonical_json_bytes(self.to_dict())
        if len(raw) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_BOOKMARK_V1_MAX_BYTES:
            _fail("byte_limit")
        return raw.decode("utf-8")


def _require_digest(value: object, code: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail(code)
    return value


class _BookmarkStateAnchor:
    __slots__ = ("bookmark", "selected", "comparisons", "subject")
    bookmark: DailyMarketTechnicalOfficialDispositionMaBookmarkV1
    selected: DailyMarketTechnicalOfficialDispositionMaVerifiedSelectionV1
    comparisons: tuple[DailyMarketTechnicalOfficialDispositionMaVerifiedSelectionV1, ...]
    subject: object | None

    def __init__(self, bookmark: DailyMarketTechnicalOfficialDispositionMaBookmarkV1,
                 selected: DailyMarketTechnicalOfficialDispositionMaVerifiedSelectionV1,
                 comparisons: tuple[DailyMarketTechnicalOfficialDispositionMaVerifiedSelectionV1, ...]) -> None:
        object.__setattr__(self, "bookmark", bookmark)
        object.__setattr__(self, "selected", selected)
        object.__setattr__(self, "comparisons", comparisons)
        object.__setattr__(self, "subject", None)

    def claim(self, subject: object) -> None:
        if self.subject is not None and self.subject is not subject:
            _fail("state_already_claimed")
        object.__setattr__(self, "subject", subject)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("verified MA bookmark state is immutable")


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionMaBookmarkStateV1:
    """完成 exact reopen、全域 execute 與全部選取列核驗後簽發的狀態。"""

    bookmark: DailyMarketTechnicalOfficialDispositionMaBookmarkV1
    selected: DailyMarketTechnicalOfficialDispositionMaVerifiedSelectionV1
    comparison_selections: tuple[DailyMarketTechnicalOfficialDispositionMaVerifiedSelectionV1, ...]
    scope: str
    source_available_at: None
    availability_status: str
    historical_pit_eligible: bool
    _anchor: _BookmarkStateAnchor = field(repr=False, compare=False)
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            self._seal is not _STATE_SEAL
            or type(self._anchor) is not _BookmarkStateAnchor
            or (self._anchor.subject is not None and self._anchor.subject is not self)
            or self._anchor.bookmark is not self.bookmark
            or self._anchor.selected is not self.selected
            or self._anchor.comparisons is not self.comparison_selections
            or self.selected.selection.to_dict() != self.bookmark.selected.to_dict()
            or tuple(item.selection.to_dict() for item in self.comparison_selections)
            != tuple(item.to_dict() for item in self.bookmark.comparison_selections)
            or self.scope != "current_only"
            or self.source_available_at is not None
            or self.availability_status != "unknown"
            or self.historical_pit_eligible is not False
        ):
            _fail("state_invalid")
        self._anchor.claim(self)


class _BookmarkRestoreContextAnchor:
    __slots__ = ("state", "result", "subject")

    state: DailyMarketTechnicalOfficialDispositionMaBookmarkStateV1
    result: DailyMarketTechnicalOfficialDispositionMaVerifiedQueryResultV1
    subject: object | None

    def __init__(
        self,
        state: DailyMarketTechnicalOfficialDispositionMaBookmarkStateV1,
        result: DailyMarketTechnicalOfficialDispositionMaVerifiedQueryResultV1,
    ) -> None:
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "result", result)
        object.__setattr__(self, "subject", None)

    def can_claim(self, subject: object) -> bool:
        return self.subject is None or self.subject is subject

    def claim(self, subject: object) -> None:
        if not self.can_claim(subject):
            _fail("restore_context_already_claimed")
        object.__setattr__(self, "subject", subject)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("verified MA bookmark restore context anchor is immutable")


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionMaBookmarkRestoreContextV1:
    """同次 exact reopen 的公開 query/state 與受限翻頁入口；不暴露 session proof。"""

    state: DailyMarketTechnicalOfficialDispositionMaBookmarkStateV1
    _anchor: _BookmarkRestoreContextAnchor = field(repr=False, compare=False)
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        anchor = self._anchor
        if (
            self._seal is not _RESTORE_CONTEXT_SEAL
            or type(anchor) is not _BookmarkRestoreContextAnchor
            or not anchor.can_claim(self)
            or anchor.state is not self.state
        ):
            _fail("restore_context_not_reader_issued")
        already_claimed = anchor.subject is self
        try:
            self.state.__post_init__()
            result = anchor.result
            query = self.state.bookmark.query
            if (
                query.to_json() != self.state.bookmark.query_json
                or result.query.to_json() != self.state.bookmark.query_json
                or result.operation_identity_sha256
                != self.state.selected.selection.result_identity_sha256
                or result.source_pins != self.state.selected.selection.source_pins
            ):
                _fail("restore_context_source_mismatch")
            verified = (self.state.selected, *self.state.comparison_selections)
            for item in verified:
                item.__post_init__()
                if (
                    item._result is not result
                    or item._session is not result._read_session
                    or item.selection.result_identity_sha256 != result.operation_identity_sha256
                    or item.selection.source_pins != result.source_pins
                ):
                    _fail("restore_context_selection_mismatch")
            if not already_claimed:
                result.__post_init__()
        except DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error:
            raise
        except (TypeError, ValueError, AttributeError) as exc:
            raise DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error(
                "technical_official_ma_bookmark_v1_restore_context_invalid"
            ) from exc
        if not already_claimed:
            anchor.claim(self)

    @property
    def query(self) -> DailyMarketTechnicalOfficialDispositionMaQueryV1:
        self.__post_init__()
        return self.state.bookmark.query

    def read_page_request(
        self,
        request: DailyMarketTechnicalOfficialDispositionMaPageRequestV1 | bytes | str,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalOfficialDispositionMaQueryPageV1:
        """沿同一已核 result 讀指定頁；request 必須完整指向保存的 canonical query。"""

        _check_cancel(cancel_callback)
        self.__post_init__()
        if isinstance(request, (bytes, str)):
            try:
                request = DailyMarketTechnicalOfficialDispositionMaPageRequestV1.from_json(request)
            except (TypeError, ValueError) as exc:
                raise DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error(
                    "technical_official_ma_bookmark_v1_restore_page_request_invalid"
                ) from exc
        if type(request) is not DailyMarketTechnicalOfficialDispositionMaPageRequestV1:
            _fail("restore_page_request_invalid")
        try:
            request_json = request.to_json()
            request_query_json = request.query.to_json()
        except (TypeError, ValueError) as exc:
            raise DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error(
                "technical_official_ma_bookmark_v1_restore_page_request_invalid"
            ) from exc
        if (
            request_query_json != self.state.bookmark.query_json
            or request.query_json != self.state.bookmark.query_json
            or request_json != DailyMarketTechnicalOfficialDispositionMaPageRequestV1.from_json(
                request_json
            ).to_json()
        ):
            _fail("restore_page_request_query_mismatch")
        _check_cancel(cancel_callback)
        page = self._anchor.result.read_page_request(
            request,
            cancel_callback=cancel_callback,
        )
        page.to_dict()
        _check_cancel(cancel_callback)
        return page

    def execute_query_conditions(
        self,
        *,
        row_scope_filter: Sequence[RowScope],
        rule_state_filters: Sequence[DailyMarketTechnicalRuleStateFilterV4],
        combine_mode: Literal["AND", "OR"],
        market_assignment_states: Sequence[str],
        official_disposal_states: Sequence[str],
        outer_stock_filter_mode: Literal["all", "explicit_codes"],
        outer_stock_codes: Sequence[str],
        f17_sort_clauses: Sequence[DailyMarketTechnicalOfficialDispositionSortClauseV1],
        ma_states: Sequence[MaState] | None,
        condition_combine_mode: Literal["AND", "OR"],
        unknown_policy: UnknownPolicy,
        sort_clauses: Sequence[DailyMarketTechnicalOfficialDispositionMaSortClauseV1],
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalOfficialDispositionMaVerifiedQueryResultV1:
        """沿 bookmark 的同一 exact session 套用完整條件並重新全域查詢。"""

        _check_cancel(cancel_callback)
        self.__post_init__()
        scope_items = _bounded_sequence_items(
            row_scope_filter, maximum=3, code="restore_conditions_row_scope_invalid"
        )
        rule_items = _bounded_sequence_items(
            rule_state_filters,
            maximum=len(DAILY_MARKET_TECHNICAL_RULE_KEYS_V4),
            code="restore_conditions_rule_filters_invalid",
        )
        market_items = _bounded_sequence_items(
            market_assignment_states,
            maximum=3,
            code="restore_conditions_market_states_invalid",
        )
        disposal_items = _bounded_sequence_items(
            official_disposal_states,
            maximum=4,
            code="restore_conditions_disposal_states_invalid",
        )
        code_items = _bounded_sequence_items(
            outer_stock_codes,
            maximum=DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS,
            code="restore_conditions_stock_codes_invalid",
        )
        f17_sort_items = _bounded_sequence_items(
            f17_sort_clauses,
            maximum=DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_QUERY_V1_MAX_SORT_CLAUSES,
            code="restore_conditions_f17_sort_clauses_invalid",
        )
        ma_sort_items = _bounded_sequence_items(
            sort_clauses,
            maximum=DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_SORT_CLAUSES,
            code="restore_conditions_sort_clauses_invalid",
        )
        ma_state_items = (
            None
            if ma_states is None
            else _bounded_sequence_items(
                ma_states,
                maximum=3,
                code="restore_conditions_ma_states_invalid",
            )
        )
        allowed_scopes = {
            "included_processed",
            "included_pending",
            "excluded",
        }
        if (
            not scope_items
            or any(not isinstance(item, str) or item not in allowed_scopes for item in scope_items)
            or len(set(scope_items)) != len(scope_items)
        ):
            _fail("restore_conditions_row_scope_invalid")
        if any(
            type(item) is not DailyMarketTechnicalRuleStateFilterV4
            for item in rule_items
        ):
            _fail("restore_conditions_rule_filters_invalid")
        if any(
            not isinstance(item, str)
            for item in (*market_items, *disposal_items)
        ):
            _fail("restore_conditions_official_states_invalid")
        if ma_state_items is not None and (
            not ma_state_items
            or any(
                not isinstance(item, str)
                or item not in {"match", "no_match", "unknown"}
                for item in ma_state_items
            )
            or len(set(ma_state_items)) != len(ma_state_items)
        ):
            _fail("restore_conditions_ma_states_invalid")
        if any(not isinstance(code, str) for code in code_items):
            _fail("restore_conditions_stock_codes_invalid")
        if any(
            type(item) is not DailyMarketTechnicalOfficialDispositionMaSortClauseV1
            for item in ma_sort_items
        ):
            _fail("restore_conditions_sort_clauses_invalid")
        from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
            DailyMarketTechnicalOfficialDispositionSortClauseV1,
            DailyMarketTechnicalOfficialDispositionReadSessionV1,
        )

        if any(
            type(item) is not DailyMarketTechnicalOfficialDispositionSortClauseV1
            for item in f17_sort_items
        ):
            _fail("restore_conditions_f17_sort_clauses_invalid")
        if type(outer_stock_filter_mode) is not str or outer_stock_filter_mode not in {"all", "explicit_codes"}:
            _fail("restore_conditions_stock_filter_invalid")
        if (
            type(combine_mode) is not str
            or combine_mode not in {"AND", "OR"}
            or type(condition_combine_mode) is not str
            or condition_combine_mode not in {"AND", "OR"}
        ):
            _fail("restore_conditions_combine_mode_invalid")
        if type(unknown_policy) is not str or unknown_policy not in {"include", "exclude", "only"}:
            _fail("restore_conditions_unknown_policy_invalid")

        normalized_scopes = cast(tuple[RowScope, ...], scope_items)
        normalized_rules = cast(
            tuple[DailyMarketTechnicalRuleStateFilterV4, ...], rule_items
        )
        normalized_market = cast(tuple[str, ...], market_items)
        normalized_disposal = cast(tuple[str, ...], disposal_items)
        normalized_codes = cast(tuple[str, ...], code_items)
        normalized_f17_sort = cast(
            tuple[DailyMarketTechnicalOfficialDispositionSortClauseV1, ...],
            f17_sort_items,
        )
        normalized_ma_sort = cast(
            tuple[DailyMarketTechnicalOfficialDispositionMaSortClauseV1, ...],
            ma_sort_items,
        )
        normalized_ma_states = (
            None if ma_state_items is None else cast(tuple[MaState, ...], ma_state_items)
        )

        original_result = self._anchor.result
        original_query = self.state.bookmark.query
        if (
            original_result.query.to_json() != original_query.to_json()
            or original_result.source_pins != self.state.selected.selection.source_pins
        ):
            _fail("restore_conditions_source_context_invalid")
        read_session = original_result._read_session
        if type(read_session) is not DailyMarketTechnicalOfficialDispositionReadSessionV1:
            _fail("restore_conditions_session_unavailable")
        try:
            conditioned = read_session.with_conditions(
                row_scope_filter=normalized_scopes,
                rule_state_filters=normalized_rules,
                combine_mode=combine_mode,
                market_assignment_states=normalized_market,
                official_disposal_states=normalized_disposal,
                outer_stock_filter_mode=outer_stock_filter_mode,
                outer_stock_codes=normalized_codes,
                sort_clauses=normalized_f17_sort,
                cancel_callback=cancel_callback,
            )
            _check_cancel(cancel_callback)
            query = conditioned.create_ma_query_v1(
                ma_states=normalized_ma_states,
                condition_combine_mode=condition_combine_mode,
                unknown_policy=unknown_policy,
                sort_clauses=normalized_ma_sort,
            )
            _check_cancel(cancel_callback)
            result = conditioned.execute_ma_query_v1(
                query,
                cancel_callback=cancel_callback,
            )
        except DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error:
            raise
        except Exception as exc:
            _check_cancel(cancel_callback)
            raise DailyMarketTechnicalOfficialDispositionMaBookmarkV1Error(
                "technical_official_ma_bookmark_v1_restore_conditions_failed"
            ) from exc
        if (
            type(result) is not DailyMarketTechnicalOfficialDispositionMaVerifiedQueryResultV1
            or result.query.query_identity_sha256 != query.query_identity_sha256
            or result.source_pins != original_result.source_pins
            or query.ma_alignment_read_session_identity_sha256
            != original_query.ma_alignment_read_session_identity_sha256
            or query.ma_alignment_index_identity_sha256
            != original_query.ma_alignment_index_identity_sha256
            or query.ma_source_request_identity_sha256
            != original_query.ma_source_request_identity_sha256
            or query.ma_method_id != original_query.ma_method_id
            or query.ma_method_version != original_query.ma_method_version
            or result.scope != "current_only"
            or result.official_available_at is not None
            or result.availability_status != "unknown"
            or result.historical_pit_eligible is not False
        ):
            _fail("restore_conditions_result_scope_mismatch")
        result.__post_init__()
        _check_cancel(cancel_callback)
        return result


def _read_bookmark_and_result_v1(
    bookmark: DailyMarketTechnicalOfficialDispositionMaBookmarkV1 | bytes | str,
    *,
    cancel_callback: Callable[[], object] | None = None,
) -> tuple[
    DailyMarketTechnicalOfficialDispositionMaBookmarkStateV1,
    DailyMarketTechnicalOfficialDispositionMaVerifiedQueryResultV1,
]:
    """只依 bookmark 固定來源 exact 重開並保留同次 reader-issued result。"""

    _check_cancel(cancel_callback)
    if isinstance(bookmark, (bytes, str)):
        saved = DailyMarketTechnicalOfficialDispositionMaBookmarkV1.from_json(bookmark)
    elif type(bookmark) is DailyMarketTechnicalOfficialDispositionMaBookmarkV1:
        saved = DailyMarketTechnicalOfficialDispositionMaBookmarkV1.from_dict(bookmark.to_dict())
    else:
        _fail("bookmark_type_invalid")
    query = saved.query
    saved_selections = (saved.selected, *saved.comparison_selections)
    unique: list[DailyMarketTechnicalOfficialDispositionMaSelectionV1] = []
    seen_codes: dict[str, DailyMarketTechnicalOfficialDispositionMaSelectionV1] = {}
    for selection in saved_selections:
        _check_cancel(cancel_callback)
        previous = seen_codes.get(selection.stock_code)
        if previous is not None:
            if previous.to_dict() != selection.to_dict():
                _fail("selected_comparison_conflict")
            continue
        seen_codes[selection.stock_code] = selection
        unique.append(selection)
    verified, result = _read_daily_market_technical_official_disposition_ma_selections_with_result_v1(
        query,
        tuple(unique),
        cancel_callback=cancel_callback,
    )
    _check_cancel(cancel_callback)
    by_code = {item.selection.stock_code: item for item in verified}
    selected = by_code[saved.selected.stock_code]
    comparisons = tuple(by_code[item.stock_code] for item in saved.comparison_selections)
    _check_cancel(cancel_callback)
    anchor = _BookmarkStateAnchor(saved, selected, comparisons)
    state = DailyMarketTechnicalOfficialDispositionMaBookmarkStateV1(
        bookmark=saved,
        selected=selected,
        comparison_selections=comparisons,
        scope="current_only",
        source_available_at=None,
        availability_status="unknown",
        historical_pit_eligible=False,
        _anchor=anchor,
        _seal=_STATE_SEAL,
    )
    _check_cancel(cancel_callback)
    return state, result


def read_daily_market_technical_official_disposition_ma_bookmark_v1(
    bookmark: DailyMarketTechnicalOfficialDispositionMaBookmarkV1 | bytes | str,
    *,
    cancel_callback: Callable[[], object] | None = None,
) -> DailyMarketTechnicalOfficialDispositionMaBookmarkStateV1:
    """舊狀態 API 維持同一型別與來源身份；僅回傳已核 bookmark state。"""

    state, _result = _read_bookmark_and_result_v1(
        bookmark,
        cancel_callback=cancel_callback,
    )
    return state


def read_daily_market_technical_official_disposition_ma_bookmark_context_v1(
    bookmark: DailyMarketTechnicalOfficialDispositionMaBookmarkV1 | bytes | str,
    *,
    cancel_callback: Callable[[], object] | None = None,
) -> DailyMarketTechnicalOfficialDispositionMaBookmarkRestoreContextV1:
    """以一次 exact open 發行可繼續翻頁的 bookmark context，不序列化 session proof。"""

    _check_cancel(cancel_callback)
    state, result = _read_bookmark_and_result_v1(
        bookmark,
        cancel_callback=cancel_callback,
    )
    _check_cancel(cancel_callback)
    anchor = _BookmarkRestoreContextAnchor(state, result)
    context = DailyMarketTechnicalOfficialDispositionMaBookmarkRestoreContextV1(
        state=state,
        _anchor=anchor,
        _seal=_RESTORE_CONTEXT_SEAL,
    )
    _check_cancel(cancel_callback)
    return context

