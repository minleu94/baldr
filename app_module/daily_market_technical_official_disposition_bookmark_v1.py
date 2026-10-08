"""官方處置研究收藏的純資料契約，不依賴 Qt 或 UI。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import re
from typing import cast

from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
    DailyMarketTechnicalOfficialDispositionPageRequestV1,
    DailyMarketTechnicalOfficialDispositionQueryResultRowV1,
)


_SCHEMA = "daily-market-technical-official-disposition-bookmark.v1"
_MAX_BYTES = 2 * 1024 * 1024
_STOCK_CODE_RE = re.compile(r"^[A-Za-z0-9]{1,16}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_RESEARCH_BOOKMARK_SOURCE = (
    "technical_official_disposition_research_bookmark"
)


def canonical_daily_market_technical_official_disposition_bookmark_json_v1(
    value: object,
) -> str:
    """以固定、無浮點 NaN 的 JSON 編碼純收藏資料。"""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def daily_market_technical_official_disposition_bookmark_identity_v1(
    body: Mapping[str, object],
) -> str:
    raw = canonical_daily_market_technical_official_disposition_bookmark_json_v1(
        body
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("technical_official_bookmark_duplicate_json_key")
        result[key] = value
    return result


def _text(value: object, code: str) -> str:
    if not isinstance(value, str):
        raise ValueError(code)
    return value


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionBookmarkComparisonV1:
    """一個跨頁比較欄的 public 頁請求與來源列 pin。"""

    page_request_json: str
    stock_code: str
    row_identity_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.page_request_json, str):
            raise ValueError("technical_official_bookmark_comparison_invalid")
        request = DailyMarketTechnicalOfficialDispositionPageRequestV1.from_json(
            self.page_request_json
        )
        if (
            not isinstance(self.stock_code, str)
            or _STOCK_CODE_RE.fullmatch(self.stock_code) is None
            or not isinstance(self.row_identity_sha256, str)
            or _SHA256_RE.fullmatch(self.row_identity_sha256) is None
            or request.page_index < 0
        ):
            raise ValueError("technical_official_bookmark_comparison_invalid")

    def to_dict(self) -> dict[str, str]:
        return {
            "page_request_json": self.page_request_json,
            "stock_code": self.stock_code,
            "row_identity_sha256": self.row_identity_sha256,
        }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionBookmarkV1:
    """供 host 儲存的 exact F17 個股與比較來源錨點；不持有 session。"""

    origin_page_request_json: str
    selected_stock_code: str
    selected_row_identity_sha256: str
    comparison_items: tuple[DailyMarketTechnicalOfficialDispositionBookmarkComparisonV1, ...]
    query_identity_sha256: str
    bundle_identity_sha256: str
    manifest_sha256: str
    market_assignment_pin_identity_sha256: str
    official_disposal_pin_identity_sha256: str
    bookmark_identity_sha256: str

    @property
    def bookmark_id(self) -> str:
        return self.bookmark_identity_sha256

    @property
    def stock_code(self) -> str:
        return self.selected_stock_code

    @property
    def stock_name(self) -> str:
        return f"{self.selected_stock_code}／研究收藏"

    @property
    def source(self) -> str:
        return DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_RESEARCH_BOOKMARK_SOURCE

    def __post_init__(self) -> None:
        if not isinstance(self.origin_page_request_json, str):
            raise ValueError("technical_official_bookmark_identity_invalid")
        request = DailyMarketTechnicalOfficialDispositionPageRequestV1.from_json(
            self.origin_page_request_json
        )
        query = request.query
        if (
            _STOCK_CODE_RE.fullmatch(self.selected_stock_code) is None
            or _SHA256_RE.fullmatch(self.selected_row_identity_sha256) is None
            or _SHA256_RE.fullmatch(self.query_identity_sha256) is None
            or _SHA256_RE.fullmatch(self.bundle_identity_sha256) is None
            or _SHA256_RE.fullmatch(self.manifest_sha256) is None
            or _SHA256_RE.fullmatch(self.market_assignment_pin_identity_sha256) is None
            or _SHA256_RE.fullmatch(self.official_disposal_pin_identity_sha256) is None
            or not isinstance(self.comparison_items, tuple)
            or any(
                type(item)
                is not DailyMarketTechnicalOfficialDispositionBookmarkComparisonV1
                for item in self.comparison_items
            )
            or query.query_identity_sha256 != self.query_identity_sha256
            or query.bundle_identity_sha256 != self.bundle_identity_sha256
            or query.expected_manifest_sha256 != self.manifest_sha256
            or query.market_assignment_pin_identity_sha256
            != self.market_assignment_pin_identity_sha256
            or query.official_disposal_pin_identity_sha256
            != self.official_disposal_pin_identity_sha256
            or len(self.comparison_items) not in {0, 2, 3, 4, 5}
            or len({item.stock_code for item in self.comparison_items})
            != len(self.comparison_items)
        ):
            raise ValueError("technical_official_bookmark_identity_invalid")

        for item in self.comparison_items:
            item_request = DailyMarketTechnicalOfficialDispositionPageRequestV1.from_json(
                item.page_request_json
            )
            if (
                item_request.query.query_identity_sha256 != self.query_identity_sha256
                or item_request.query.bundle_identity_sha256 != self.bundle_identity_sha256
                or item_request.query.expected_manifest_sha256 != self.manifest_sha256
                or item_request.query.market_assignment_pin_identity_sha256
                != self.market_assignment_pin_identity_sha256
                or item_request.query.official_disposal_pin_identity_sha256
                != self.official_disposal_pin_identity_sha256
            ):
                raise ValueError("technical_official_bookmark_query_mismatch")

        if self.bookmark_identity_sha256 != daily_market_technical_official_disposition_bookmark_identity_v1(
            self._body_dict()
        ):
            raise ValueError("technical_official_bookmark_digest_mismatch")

    @classmethod
    def create(
        cls,
        *,
        origin_page_request: DailyMarketTechnicalOfficialDispositionPageRequestV1,
        selected_row: DailyMarketTechnicalOfficialDispositionQueryResultRowV1,
        comparison_items: Sequence[DailyMarketTechnicalOfficialDispositionBookmarkComparisonV1] = (),
    ) -> DailyMarketTechnicalOfficialDispositionBookmarkV1:
        if (
            type(origin_page_request)
            is not DailyMarketTechnicalOfficialDispositionPageRequestV1
            or type(selected_row)
            is not DailyMarketTechnicalOfficialDispositionQueryResultRowV1
        ):
            raise ValueError("technical_official_bookmark_selected_row_invalid")
        items = tuple(comparison_items)
        if any(
            type(item)
            is not DailyMarketTechnicalOfficialDispositionBookmarkComparisonV1
            for item in items
        ):
            raise ValueError("technical_official_bookmark_comparison_invalid")
        query = origin_page_request.query
        body: dict[str, object] = {
            "schema_version": _SCHEMA,
            "origin_page_request_json": origin_page_request.to_json(),
            "selected_stock_code": selected_row.stock_code,
            "selected_row_identity_sha256": selected_row.row_identity_sha256,
            "comparison_items": [item.to_dict() for item in items],
            "query_identity_sha256": query.query_identity_sha256,
            "bundle_identity_sha256": query.bundle_identity_sha256,
            "manifest_sha256": query.expected_manifest_sha256,
            "market_assignment_pin_identity_sha256": query.market_assignment_pin_identity_sha256,
            "official_disposal_pin_identity_sha256": query.official_disposal_pin_identity_sha256,
        }
        bookmark = cls(
            origin_page_request_json=origin_page_request.to_json(),
            selected_stock_code=selected_row.stock_code,
            selected_row_identity_sha256=selected_row.row_identity_sha256,
            comparison_items=items,
            query_identity_sha256=query.query_identity_sha256,
            bundle_identity_sha256=query.bundle_identity_sha256,
            manifest_sha256=query.expected_manifest_sha256,
            market_assignment_pin_identity_sha256=query.market_assignment_pin_identity_sha256,
            official_disposal_pin_identity_sha256=query.official_disposal_pin_identity_sha256,
            bookmark_identity_sha256=daily_market_technical_official_disposition_bookmark_identity_v1(
                body
            ),
        )
        if len(bookmark.to_json().encode("utf-8")) > _MAX_BYTES:
            raise ValueError("technical_official_bookmark_size_limit")
        return bookmark

    @classmethod
    def from_json(
        cls, raw: str | bytes
    ) -> DailyMarketTechnicalOfficialDispositionBookmarkV1:
        if isinstance(raw, str):
            try:
                encoded = raw.encode("utf-8")
            except UnicodeError as exc:
                raise ValueError("technical_official_bookmark_json_invalid") from exc
        elif isinstance(raw, bytes):
            encoded = raw
        else:
            raise ValueError("technical_official_bookmark_json_invalid")
        if len(encoded) > _MAX_BYTES:
            raise ValueError("technical_official_bookmark_size_limit")
        try:
            payload = json.loads(
                encoded.decode("utf-8"), object_pairs_hook=_unique_pairs
            )
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("technical_official_bookmark_json_invalid") from exc
        expected = {
            "schema_version",
            "origin_page_request_json",
            "selected_stock_code",
            "selected_row_identity_sha256",
            "comparison_items",
            "query_identity_sha256",
            "bundle_identity_sha256",
            "manifest_sha256",
            "market_assignment_pin_identity_sha256",
            "official_disposal_pin_identity_sha256",
            "bookmark_identity_sha256",
        }
        if not isinstance(payload, Mapping) or set(payload) != expected:
            raise ValueError("technical_official_bookmark_schema_invalid")
        if payload.get("schema_version") != _SCHEMA:
            raise ValueError("technical_official_bookmark_schema_unsupported")
        raw_items = payload.get("comparison_items")
        if not isinstance(raw_items, list):
            raise ValueError("technical_official_bookmark_comparison_invalid")
        items: list[DailyMarketTechnicalOfficialDispositionBookmarkComparisonV1] = []
        for value in raw_items:
            if not isinstance(value, Mapping) or set(value) != {
                "page_request_json",
                "stock_code",
                "row_identity_sha256",
            }:
                raise ValueError("technical_official_bookmark_comparison_invalid")
            items.append(
                DailyMarketTechnicalOfficialDispositionBookmarkComparisonV1(
                    page_request_json=_text(
                        value["page_request_json"],
                        "technical_official_bookmark_comparison_invalid",
                    ),
                    stock_code=_text(
                        value["stock_code"],
                        "technical_official_bookmark_comparison_invalid",
                    ),
                    row_identity_sha256=_text(
                        value["row_identity_sha256"],
                        "technical_official_bookmark_comparison_invalid",
                    ),
                )
            )
        bookmark = cls(
            origin_page_request_json=_text(
                payload["origin_page_request_json"],
                "technical_official_bookmark_schema_invalid",
            ),
            selected_stock_code=_text(
                payload["selected_stock_code"],
                "technical_official_bookmark_schema_invalid",
            ),
            selected_row_identity_sha256=_text(
                payload["selected_row_identity_sha256"],
                "technical_official_bookmark_schema_invalid",
            ),
            comparison_items=tuple(items),
            query_identity_sha256=_text(
                payload["query_identity_sha256"],
                "technical_official_bookmark_schema_invalid",
            ),
            bundle_identity_sha256=_text(
                payload["bundle_identity_sha256"],
                "technical_official_bookmark_schema_invalid",
            ),
            manifest_sha256=_text(
                payload["manifest_sha256"],
                "technical_official_bookmark_schema_invalid",
            ),
            market_assignment_pin_identity_sha256=_text(
                payload["market_assignment_pin_identity_sha256"],
                "technical_official_bookmark_schema_invalid",
            ),
            official_disposal_pin_identity_sha256=_text(
                payload["official_disposal_pin_identity_sha256"],
                "technical_official_bookmark_schema_invalid",
            ),
            bookmark_identity_sha256=_text(
                payload["bookmark_identity_sha256"],
                "technical_official_bookmark_schema_invalid",
            ),
        )
        if bookmark.to_json().encode("utf-8") != encoded:
            raise ValueError("technical_official_bookmark_noncanonical")
        return bookmark

    def _body_dict(self) -> dict[str, object]:
        return {
            "schema_version": _SCHEMA,
            "origin_page_request_json": self.origin_page_request_json,
            "selected_stock_code": self.selected_stock_code,
            "selected_row_identity_sha256": self.selected_row_identity_sha256,
            "comparison_items": [item.to_dict() for item in self.comparison_items],
            "query_identity_sha256": self.query_identity_sha256,
            "bundle_identity_sha256": self.bundle_identity_sha256,
            "manifest_sha256": self.manifest_sha256,
            "market_assignment_pin_identity_sha256": self.market_assignment_pin_identity_sha256,
            "official_disposal_pin_identity_sha256": self.official_disposal_pin_identity_sha256,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            **self._body_dict(),
            "bookmark_identity_sha256": self.bookmark_identity_sha256,
        }

    def to_json(self) -> str:
        raw = canonical_daily_market_technical_official_disposition_bookmark_json_v1(
            self.to_dict()
        )
        if len(raw.encode("utf-8")) > _MAX_BYTES:
            raise ValueError("technical_official_bookmark_size_limit")
        return raw
