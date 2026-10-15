"""V2 複合研究收藏的 typed Watchlist envelope；不授予來源驗證資格。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import re
from typing import NoReturn

from app_module.daily_market_technical_official_disposition_composite_bookmark_v2 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_MAX_BYTES_V2,
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_MAX_SELECTIONS_V2,
    DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2,
)


COMPOSITE_VIEW_BOOKMARK_ENVELOPE_SCHEMA_V2 = (
    "daily-market-technical-official-disposition-composite-view-state.v2"
)
COMPOSITE_VIEW_BOOKMARK_SOURCE_V2 = (
    "technical_official_disposition_composite_research_bookmark_v2"
)
_SCHEMA = COMPOSITE_VIEW_BOOKMARK_ENVELOPE_SCHEMA_V2
_SOURCE = COMPOSITE_VIEW_BOOKMARK_SOURCE_V2
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STOCK_CODE_RE = re.compile(r"^[A-Z0-9]{1,16}$")
_MAX_JSON_DEPTH_V2 = 32
_MAX_SELECTIONS_V2 = (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_MAX_SELECTIONS_V2
)
_MAX_BYTES_V2 = (
    2 * DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_MAX_BYTES_V2
    + 4096
)
_SCOPE_FIELDS = {
    "scope": "current_only",
    "official_available_at": None,
    "availability_status": "unknown",
    "historical_pit_eligible": False,
    "storage_envelope_is_reader_certification": False,
}


class CompositeBookmarkStorageEnvelopeV2Error(ValueError):
    """V2 複合收藏 envelope 的穩定拒絕碼。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"composite_view_bookmark_storage_v2_{code}")


def _fail(code: str) -> NoReturn:
    raise CompositeBookmarkStorageEnvelopeV2Error(code)


def _reject_float_tree(value: object, *, depth: int = 0) -> None:
    """拒絕浮點與過深 mapping；內層 V2 bookmark 另由其 strict parser 核驗。"""
    if depth > _MAX_JSON_DEPTH_V2:
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
        raise CompositeBookmarkStorageEnvelopeV2Error("json_invalid") from exc


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _require_sha(value: object, code: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        _fail(code)
    return value


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
            continue
        if char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > _MAX_JSON_DEPTH_V2:
                _fail("json_depth_limit")
        elif char in "]}":
            depth -= 1
            if depth < 0:
                return


def _body(
    *,
    bookmark_json: str,
    bookmark_sha256: str,
    bookmark_identity_sha256: str,
    stock_code: str,
    source: str,
) -> dict[str, object]:
    return {
        "schema_version": _SCHEMA,
        "bookmark_json": bookmark_json,
        "bookmark_sha256": bookmark_sha256,
        "bookmark_identity_sha256": bookmark_identity_sha256,
        "stock_code": stock_code,
        "source": source,
        **_SCOPE_FIELDS,
    }


_EXPECTED_FIELDS = frozenset(
    {
        "schema_version",
        "bookmark_json",
        "bookmark_sha256",
        "bookmark_identity_sha256",
        "stock_code",
        "source",
        "scope",
        "official_available_at",
        "availability_status",
        "historical_pit_eligible",
        "storage_envelope_is_reader_certification",
        "view_bookmark_identity_sha256",
    }
)


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2:
    """包住 canonical V2 bookmark；basket 與 scroll 僅保存在內層一次。"""

    bookmark_json: str
    bookmark_sha256: str
    bookmark_identity_sha256: str
    stock_code: str
    source: str
    view_bookmark_identity_sha256: str
    schema_version: str = _SCHEMA

    def __post_init__(self) -> None:
        if (
            self.schema_version != _SCHEMA
            or type(self.bookmark_json) is not str
            or not self.bookmark_json
            or type(self.stock_code) is not str
            or _STOCK_CODE_RE.fullmatch(self.stock_code) is None
            or type(self.source) is not str
            or self.source != _SOURCE
        ):
            _fail("envelope_fields_invalid")
        _require_sha(self.bookmark_sha256, "bookmark_sha256_invalid")
        _require_sha(self.bookmark_identity_sha256, "bookmark_identity_invalid")
        _require_sha(self.view_bookmark_identity_sha256, "view_bookmark_identity_invalid")
        try:
            encoded_bookmark = self.bookmark_json.encode("utf-8")
        except UnicodeError as exc:
            raise CompositeBookmarkStorageEnvelopeV2Error("bookmark_json_invalid") from exc
        if len(encoded_bookmark) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_MAX_BYTES_V2:
            _fail("bookmark_byte_limit")
        if hashlib.sha256(encoded_bookmark).hexdigest() != self.bookmark_sha256:
            _fail("bookmark_sha256_mismatch")
        try:
            bookmark = DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2.from_json(
                self.bookmark_json
            )
        except Exception as exc:
            raise CompositeBookmarkStorageEnvelopeV2Error("bookmark_invalid") from exc
        if (
            len(bookmark.comparison_selections) + 1 > _MAX_SELECTIONS_V2
            or len(bookmark.basket_stock_codes) > _MAX_SELECTIONS_V2
        ):
            _fail("bookmark_count_limit")
        if (
            bookmark.to_json() != self.bookmark_json
            or bookmark.bookmark_id != self.bookmark_identity_sha256
            or bookmark.stock_code != self.stock_code
            or bookmark.source != self.source
        ):
            _fail("bookmark_identity_mismatch")
        identity = _sha256_json(
            _body(
                bookmark_json=self.bookmark_json,
                bookmark_sha256=self.bookmark_sha256,
                bookmark_identity_sha256=self.bookmark_identity_sha256,
                stock_code=self.stock_code,
                source=self.source,
            )
        )
        if identity != self.view_bookmark_identity_sha256:
            _fail("view_bookmark_identity_mismatch")
        encoded_envelope = _canonical_json_bytes(
            _body(
                bookmark_json=self.bookmark_json,
                bookmark_sha256=self.bookmark_sha256,
                bookmark_identity_sha256=self.bookmark_identity_sha256,
                stock_code=self.stock_code,
                source=self.source,
            )
            | {"view_bookmark_identity_sha256": self.view_bookmark_identity_sha256}
        )
        if len(encoded_envelope) > _MAX_BYTES_V2:
            _fail("byte_limit")

    @classmethod
    def create(
        cls,
        bookmark: DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2,
    ) -> DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2:
        if type(bookmark) is not DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2:
            _fail("bookmark_type_invalid")
        try:
            bookmark_json = bookmark.to_json()
            canonical_bookmark = DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2.from_json(
                bookmark_json
            )
        except Exception as exc:
            raise CompositeBookmarkStorageEnvelopeV2Error("bookmark_invalid") from exc
        encoded_bookmark = bookmark_json.encode("utf-8")
        bookmark_sha256 = hashlib.sha256(encoded_bookmark).hexdigest()
        body = _body(
            bookmark_json=bookmark_json,
            bookmark_sha256=bookmark_sha256,
            bookmark_identity_sha256=canonical_bookmark.bookmark_id,
            stock_code=canonical_bookmark.stock_code,
            source=canonical_bookmark.source,
        )
        return cls(
            bookmark_json=bookmark_json,
            bookmark_sha256=bookmark_sha256,
            bookmark_identity_sha256=canonical_bookmark.bookmark_id,
            stock_code=canonical_bookmark.stock_code,
            source=canonical_bookmark.source,
            view_bookmark_identity_sha256=_sha256_json(body),
        )

    def to_dict(self) -> dict[str, object]:
        self.__post_init__()
        body = _body(
            bookmark_json=self.bookmark_json,
            bookmark_sha256=self.bookmark_sha256,
            bookmark_identity_sha256=self.bookmark_identity_sha256,
            stock_code=self.stock_code,
            source=self.source,
        )
        result = body | {
            "view_bookmark_identity_sha256": self.view_bookmark_identity_sha256,
        }
        if len(_canonical_json_bytes(result)) > _MAX_BYTES_V2:
            _fail("byte_limit")
        return result

    def to_json(self) -> str:
        encoded = _canonical_json_bytes(self.to_dict())
        if len(encoded) > _MAX_BYTES_V2:
            _fail("byte_limit")
        return encoded.decode("utf-8")

    @classmethod
    def from_dict(
        cls,
        value: object,
    ) -> DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2:
        if not isinstance(value, Mapping) or set(value) != _EXPECTED_FIELDS:
            _fail("envelope_fields_invalid")
        raw_bookmark = value.get("bookmark_json")
        if type(raw_bookmark) is not str:
            _fail("envelope_fields_invalid")
        try:
            if len(raw_bookmark.encode("utf-8")) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_MAX_BYTES_V2:
                _fail("bookmark_byte_limit")
        except UnicodeError as exc:
            raise CompositeBookmarkStorageEnvelopeV2Error("bookmark_json_invalid") from exc
        for field_name in (
            "schema_version",
            "bookmark_json",
            "bookmark_sha256",
            "bookmark_identity_sha256",
            "stock_code",
            "source",
            "view_bookmark_identity_sha256",
            "scope",
            "availability_status",
        ):
            if type(value.get(field_name)) is not str:
                _fail("envelope_fields_invalid")
        if (
            value.get("official_available_at") is not None
            or type(value.get("historical_pit_eligible")) is not bool
            or type(value.get("storage_envelope_is_reader_certification")) is not bool
        ):
            _fail("envelope_fields_invalid")
        encoded_text_bytes = 0
        for field_name in _EXPECTED_FIELDS:
            field_value = value[field_name]
            if type(field_value) is str:
                try:
                    encoded_text_bytes += len(field_value.encode("utf-8"))
                except UnicodeError as exc:
                    raise CompositeBookmarkStorageEnvelopeV2Error(
                        "json_invalid"
                    ) from exc
                if encoded_text_bytes + 1024 > _MAX_BYTES_V2:
                    _fail("byte_limit")
        encoded = _canonical_json_bytes(dict(value))
        if len(encoded) > _MAX_BYTES_V2:
            _fail("byte_limit")
        return cls.from_json(encoded)

    @classmethod
    def from_json(
        cls,
        raw: bytes | str,
    ) -> DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2:
        if type(raw) not in (bytes, str):
            _fail("json_invalid")
        if type(raw) is str and len(raw) > _MAX_BYTES_V2:
            _fail("byte_limit")
        try:
            encoded = raw if isinstance(raw, bytes) else raw.encode("utf-8")
        except UnicodeError as exc:
            raise CompositeBookmarkStorageEnvelopeV2Error("json_invalid") from exc
        if len(encoded) > _MAX_BYTES_V2:
            _fail("byte_limit")
        try:
            text = encoded.decode("utf-8")
            _preflight_json_depth(text)
            payload = json.loads(
                text,
                object_pairs_hook=_unique_pairs,
                parse_float=lambda _value: _fail("float_forbidden"),
                parse_constant=lambda _value: _fail("json_constant_invalid"),
            )
        except CompositeBookmarkStorageEnvelopeV2Error:
            raise
        except (UnicodeError, json.JSONDecodeError, RecursionError, TypeError, ValueError) as exc:
            raise CompositeBookmarkStorageEnvelopeV2Error("json_invalid") from exc
        if not isinstance(payload, Mapping) or set(payload) != _EXPECTED_FIELDS:
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
        result = cls(
            bookmark_json=payload["bookmark_json"],
            bookmark_sha256=payload["bookmark_sha256"],
            bookmark_identity_sha256=payload["bookmark_identity_sha256"],
            stock_code=payload["stock_code"],
            source=payload["source"],
            view_bookmark_identity_sha256=payload["view_bookmark_identity_sha256"],
            schema_version=payload["schema_version"],
        )
        if result.to_json().encode("utf-8") != encoded:
            _fail("json_noncanonical")
        return result


__all__ = (
    "COMPOSITE_VIEW_BOOKMARK_ENVELOPE_SCHEMA_V2",
    "COMPOSITE_VIEW_BOOKMARK_SOURCE_V2",
    "CompositeBookmarkStorageEnvelopeV2Error",
    "DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2",
)
