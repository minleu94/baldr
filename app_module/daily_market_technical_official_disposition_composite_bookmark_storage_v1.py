"""複合研究收藏的型別化儲存封套與路由契約。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import re
from typing import NoReturn, Protocol

from app_module.daily_market_technical_official_disposition_composite_bookmark_v1 import (
    DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1,
)


COMPOSITE_VIEW_BOOKMARK_ENVELOPE_SCHEMA_V1 = (
    "daily-market-technical-official-disposition-composite-view-state.v1"
)
COMPOSITE_VIEW_BOOKMARK_SOURCE = (
    "technical_official_disposition_composite_research_bookmark"
)
_SCHEMA = COMPOSITE_VIEW_BOOKMARK_ENVELOPE_SCHEMA_V1
_SOURCE = COMPOSITE_VIEW_BOOKMARK_SOURCE
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STOCK_CODE_RE = re.compile(r"^[A-Z0-9]{1,16}$")
_MAX_BASKET_CODES = 5
_MAX_BYTES = 64 * 1024 * 1024


class CompositeBookmarkStorageEnvelopeError(ValueError):
    """複合研究 UI 狀態收藏的穩定拒絕碼。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"composite_view_bookmark_storage_v1_{code}")


def _fail(code: str) -> NoReturn:
    raise CompositeBookmarkStorageEnvelopeError(code)


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise CompositeBookmarkStorageEnvelopeError("json_invalid") from exc


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail("json_duplicate_key")
        result[key] = value
    return result


def _basket_codes(value: object) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _fail("comparison_basket_invalid")
    codes = tuple(value)
    if (
        len(codes) > _MAX_BASKET_CODES
        or any(type(code) is not str or _STOCK_CODE_RE.fullmatch(code) is None for code in codes)
        or len(set(codes)) != len(codes)
    ):
        _fail("comparison_basket_invalid")
    return codes


def _body(
    bookmark_json: str,
    bookmark_id: str,
    basket_codes: tuple[str, ...],
    selected_was_in_comparison_basket: bool,
) -> dict[str, object]:
    return {
        "schema_version": _SCHEMA,
        "bookmark_json": bookmark_json,
        "bookmark_id": bookmark_id,
        "comparison_basket_stock_codes": list(basket_codes),
        "selected_was_in_comparison_basket": selected_was_in_comparison_basket,
        "scope": "current_only",
        "official_available_at": None,
        "availability_status": "unknown",
        "historical_pit_eligible": False,
        "storage_envelope_is_reader_certification": False,
    }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV1:
    """保存 strict bookmark 與原比較籃 membership；自身不授予來源資格。"""

    bookmark_json: str
    bookmark_id: str
    comparison_basket_stock_codes: tuple[str, ...]
    selected_was_in_comparison_basket: bool
    envelope_identity_sha256: str
    schema_version: str = _SCHEMA

    def __post_init__(self) -> None:
        if (
            self.schema_version != _SCHEMA
            or type(self.bookmark_json) is not str
            or not self.bookmark_json
            or type(self.bookmark_id) is not str
            or _SHA256_RE.fullmatch(self.bookmark_id) is None
            or type(self.comparison_basket_stock_codes) is not tuple
            or type(self.selected_was_in_comparison_basket) is not bool
            or type(self.envelope_identity_sha256) is not str
            or _SHA256_RE.fullmatch(self.envelope_identity_sha256) is None
        ):
            _fail("envelope_fields_invalid")
        try:
            bookmark = DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1.from_json(
                self.bookmark_json
            )
        except Exception as exc:
            raise CompositeBookmarkStorageEnvelopeError("bookmark_invalid") from exc
        codes = _basket_codes(self.comparison_basket_stock_codes)
        if self.bookmark_id != bookmark.bookmark_id:
            _fail("bookmark_identity_mismatch")
        selected_code = bookmark.selected.stock_code
        selected_is_member = selected_code in codes
        saved_comparison_codes = tuple(
            item.stock_code for item in bookmark.comparison_selections
        )
        expected_members = set(saved_comparison_codes)
        if selected_is_member:
            expected_members.add(selected_code)
        if (
            selected_is_member is not self.selected_was_in_comparison_basket
            or set(codes) != expected_members
            or len(saved_comparison_codes) != len(set(saved_comparison_codes))
        ):
            _fail("comparison_basket_context_mismatch")
        if self.envelope_identity_sha256 != _sha256(
            _body(
                self.bookmark_json,
                self.bookmark_id,
                codes,
                self.selected_was_in_comparison_basket,
            )
        ):
            _fail("envelope_identity_mismatch")
        encoded = _canonical_json({
            **_body(
                self.bookmark_json,
                self.bookmark_id,
                codes,
                self.selected_was_in_comparison_basket,
            ),
            "envelope_identity_sha256": self.envelope_identity_sha256,
        })
        if len(encoded) > _MAX_BYTES:
            _fail("byte_limit")

    @classmethod
    def create(
        cls,
        bookmark: DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1,
        comparison_basket_stock_codes: Sequence[str],
    ) -> DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV1:
        if type(bookmark) is not DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1:
            _fail("bookmark_type_invalid")
        canonical_bookmark = DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1.from_json(
            bookmark.to_json()
        )
        codes = _basket_codes(comparison_basket_stock_codes)
        selected_in_basket = canonical_bookmark.selected.stock_code in codes
        body = _body(
            canonical_bookmark.to_json(),
            canonical_bookmark.bookmark_id,
            codes,
            selected_in_basket,
        )
        return cls(
            bookmark_json=canonical_bookmark.to_json(),
            bookmark_id=canonical_bookmark.bookmark_id,
            comparison_basket_stock_codes=codes,
            selected_was_in_comparison_basket=selected_in_basket,
            envelope_identity_sha256=_sha256(body),
        )

    def to_dict(self) -> dict[str, object]:
        self.__post_init__()
        return {
            **_body(
                self.bookmark_json,
                self.bookmark_id,
                _basket_codes(self.comparison_basket_stock_codes),
                self.selected_was_in_comparison_basket,
            ),
            "envelope_identity_sha256": self.envelope_identity_sha256,
        }

    def to_json(self) -> str:
        encoded = _canonical_json(self.to_dict())
        if len(encoded) > _MAX_BYTES:
            _fail("byte_limit")
        return encoded.decode("utf-8")

    @classmethod
    def from_dict(
        cls,
        value: object,
    ) -> DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV1:
        if not isinstance(value, Mapping):
            _fail("envelope_fields_invalid")
        return cls.from_json(_canonical_json(dict(value)))

    @classmethod
    def from_json(
        cls,
        raw: bytes | str,
    ) -> DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV1:
        if type(raw) not in (bytes, str):
            _fail("json_invalid")
        try:
            if type(raw) is bytes:
                encoded = raw
            elif type(raw) is str:
                encoded = raw.encode("utf-8")
            else:
                _fail("json_invalid")
            if len(encoded) > _MAX_BYTES:
                _fail("byte_limit")
            payload = json.loads(
                encoded.decode("utf-8"),
                object_pairs_hook=_unique_pairs,
                parse_float=lambda _value: _fail("float_forbidden"),
                parse_constant=lambda _value: _fail("json_constant_invalid"),
            )
        except CompositeBookmarkStorageEnvelopeError:
            raise
        except (UnicodeError, json.JSONDecodeError, RecursionError, TypeError, ValueError) as exc:
            raise CompositeBookmarkStorageEnvelopeError("json_invalid") from exc
        expected = {
            "schema_version", "bookmark_json", "bookmark_id", "comparison_basket_stock_codes",
            "selected_was_in_comparison_basket", "scope", "official_available_at",
            "availability_status", "historical_pit_eligible",
            "storage_envelope_is_reader_certification", "envelope_identity_sha256",
        }
        if not isinstance(payload, Mapping) or set(payload) != expected:
            _fail("envelope_fields_invalid")
        if (
            payload.get("schema_version") != _SCHEMA
            or payload.get("scope") != "current_only"
            or payload.get("official_available_at") is not None
            or payload.get("availability_status") != "unknown"
            or payload.get("historical_pit_eligible") is not False
            or payload.get("storage_envelope_is_reader_certification") is not False
        ):
            _fail("envelope_qualification_invalid")
        bookmark_json = payload.get("bookmark_json")
        bookmark_id = payload.get("bookmark_id")
        selected_member = payload.get("selected_was_in_comparison_basket")
        identity = payload.get("envelope_identity_sha256")
        if (type(bookmark_json) is not str or type(bookmark_id) is not str
                or type(selected_member) is not bool or type(identity) is not str):
            _fail("envelope_fields_invalid")
        result = cls(
            bookmark_json=bookmark_json,
            bookmark_id=bookmark_id,
            comparison_basket_stock_codes=_basket_codes(
                payload.get("comparison_basket_stock_codes")
            ),
            selected_was_in_comparison_basket=selected_member,
            envelope_identity_sha256=identity,
        )
        if result.to_json().encode("utf-8") != encoded:
            _fail("json_noncanonical")
        return result

    @property
    def stock_code(self) -> str:
        return DailyMarketTechnicalOfficialDispositionCompositeBookmarkV1.from_json(
            self.bookmark_json
        ).stock_code

    @property
    def source(self) -> str:
        return _SOURCE


class CompositeBookmarkStorageRouteV1(Protocol):
    """觀察清單服務提供的複合收藏精確儲存與讀回路由。"""

    def add_composite_research_bookmark(
        self,
        envelope: DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV1,
    ) -> object: ...

    def read_composite_research_bookmark(
        self,
        envelope_identity_sha256: str,
    ) -> DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV1 | None: ...


__all__ = [
    "COMPOSITE_VIEW_BOOKMARK_ENVELOPE_SCHEMA_V1",
    "COMPOSITE_VIEW_BOOKMARK_SOURCE",
    "CompositeBookmarkStorageEnvelopeError",
    "CompositeBookmarkStorageRouteV1",
    "DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV1",
]
