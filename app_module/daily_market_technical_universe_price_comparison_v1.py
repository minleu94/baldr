"""F07 價格研究比較；每一欄保留並重驗自己的 exact query 與來源。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import NoReturn, cast

from app_module.daily_market_technical_universe_price_query_v1 import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_PAGE_BYTES,
    DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_PAGE_SIZE,
    DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_QUERY_BYTES,
    DailyMarketTechnicalUniversePricePageRequestV1,
    DailyMarketTechnicalUniversePricePageV1,
    DailyMarketTechnicalUniversePriceQueryV1,
    DailyMarketTechnicalUniversePriceQueryV1Error,
    DailyMarketTechnicalUniversePriceReadSessionV1,
    DailyMarketTechnicalUniversePriceResultV1,
    DailyMarketTechnicalUniversePriceRowV1,
    open_daily_market_technical_universe_price_session_for_query_v1,
)


DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_COMPARISON_V1_SCHEMA = (
    "daily-market-technical-universe-price-comparison.v1"
)
DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_SELECTION_V1_SCHEMA = (
    "daily-market-technical-universe-price-selection.v1"
)
DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_COMPARISON_MAX_ITEMS = 256
DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_COMPARISON_MAX_BYTES = 64 * 1024 * 1024
DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_SELECTION_MAX_BYTES = (
    DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_QUERY_BYTES + 8192
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STOCK_CODE_RE = re.compile(r"^[A-Z0-9]{1,16}$")
_PRICE_STATES = frozenset({"pass", "unknown"})


class DailyMarketTechnicalUniversePriceComparisonV1Error(ValueError):
    """價格比較選取或其 fresh exact 重開無法核驗。"""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


def _fail(code: str, message: str | None = None) -> NoReturn:
    raise DailyMarketTechnicalUniversePriceComparisonV1Error(code, message)


def _check_cancel(cancel_callback: Callable[[], object] | None) -> None:
    if cancel_callback is not None and cancel_callback():
        raise InterruptedError("technical_universe_price_comparison_cancelled")


def _reject_float_tree(value: object) -> None:
    pending: list[tuple[object, int]] = [(value, 0)]
    while pending:
        current, depth = pending.pop()
        if depth > 32:
            _fail("technical_universe_price_comparison_json_depth_limit")
        if isinstance(current, float):
            _fail("technical_universe_price_comparison_float_forbidden")
        if isinstance(current, Mapping):
            for key, item in current.items():
                if not isinstance(key, str):
                    _fail("technical_universe_price_comparison_json_key_invalid")
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
        raise DailyMarketTechnicalUniversePriceComparisonV1Error(
            "technical_universe_price_comparison_json_invalid"
        ) from exc


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _parse_json(raw: bytes | str, *, maximum_bytes: int, code: str) -> object:
    try:
        encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
        if not isinstance(encoded, bytes) or len(encoded) > maximum_bytes:
            _fail("technical_universe_price_comparison_byte_limit")

        def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, item in pairs:
                if key in result:
                    _fail("technical_universe_price_comparison_duplicate_json_key")
                result[key] = item
            return result

        def reject_constant(value: str) -> NoReturn:
            _fail("technical_universe_price_comparison_json_constant_invalid", value)

        def reject_float(value: str) -> NoReturn:
            _fail("technical_universe_price_comparison_float_forbidden", value)

        value = json.loads(
            encoded.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
            parse_float=reject_float,
        )
        _reject_float_tree(value)
        if _canonical_json_bytes(value) != encoded:
            _fail("technical_universe_price_comparison_json_noncanonical")
        return value
    except DailyMarketTechnicalUniversePriceComparisonV1Error:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, RecursionError) as exc:
        raise DailyMarketTechnicalUniversePriceComparisonV1Error(code) from exc


def _require_sha(value: object, code: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail(code)
    return value


def _canonical_decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if not value.is_finite():
        _fail("technical_universe_price_comparison_decimal_invalid")
    parts = value.as_tuple()
    if (
        value <= 0
        or len(parts.digits) > 64
        or not isinstance(parts.exponent, int)
        or abs(parts.exponent) > 64
    ):
        _fail("technical_universe_price_comparison_decimal_invalid")
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    if len(rendered) > 128:
        _fail("technical_universe_price_comparison_decimal_invalid")
    return rendered


def _validate_decimal_text(value: object, *, nullable: bool, code: str) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value or len(value) > 128:
        _fail(code)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise DailyMarketTechnicalUniversePriceComparisonV1Error(code) from exc
    parts = parsed.as_tuple()
    if (
        not parsed.is_finite()
        or parsed <= 0
        or len(parts.digits) > 64
        or not isinstance(parts.exponent, int)
        or abs(parts.exponent) > 64
        or len(value) > 128
    ):
        _fail(code)
    rendered = format(parsed, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    if rendered != value:
        _fail(code)
    return value


def _query_from_json(value: str) -> DailyMarketTechnicalUniversePriceQueryV1:
    if not isinstance(value, str):
        _fail("technical_universe_price_selection_query_invalid")
    if len(value.encode("utf-8")) > DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_QUERY_BYTES:
        _fail("technical_universe_price_selection_query_byte_limit")
    try:
        result = DailyMarketTechnicalUniversePriceQueryV1.from_json(value)
    except (DailyMarketTechnicalUniversePriceQueryV1Error, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalUniversePriceComparisonV1Error(
            "technical_universe_price_selection_query_invalid"
        ) from exc
    if result.to_json() != value:
        _fail("technical_universe_price_selection_query_noncanonical")
    return result


def _request_from_json(value: str) -> DailyMarketTechnicalUniversePricePageRequestV1:
    if not isinstance(value, str) or len(value.encode("utf-8")) > 4096:
        _fail("technical_universe_price_selection_page_request_invalid")
    try:
        result = DailyMarketTechnicalUniversePricePageRequestV1.from_json(value)
    except (DailyMarketTechnicalUniversePriceQueryV1Error, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalUniversePriceComparisonV1Error(
            "technical_universe_price_selection_page_request_invalid"
        ) from exc
    if result.to_json() != value:
        _fail("technical_universe_price_selection_page_request_noncanonical")
    return result


def _row_source_fields(row: DailyMarketTechnicalUniversePriceRowV1) -> tuple[str, str, str]:
    fact = row.price_fact
    return (
        row.technical_row.snapshot_identity_sha256,
        row.technical_row.source_identity,
        fact.source_identity,
    )


def _selection_body(
    *,
    query_json: str,
    page_request_json: str,
    result_identity_sha256: str,
    page_identity_sha256: str,
    stock_code: str,
    price_state: str,
    close_price: str | None,
    observation_date: str | None,
    raw_row_fingerprint_sha256: str | None,
    snapshot_identity_sha256: str,
    row_source_identity: str,
    row_identity_sha256: str,
    source_identity_sha256: str,
    price_index_identity_sha256: str,
) -> dict[str, object]:
    return {
        "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_SELECTION_V1_SCHEMA,
        "query_json": query_json,
        "page_request_json": page_request_json,
        "result_identity_sha256": result_identity_sha256,
        "page_identity_sha256": page_identity_sha256,
        "stock_code": stock_code,
        "price_state": price_state,
        "close_price": close_price,
        "unit": "TWD/share",
        "observation_date": observation_date,
        "raw_row_fingerprint_sha256": raw_row_fingerprint_sha256,
        "snapshot_identity_sha256": snapshot_identity_sha256,
        "row_source_identity": row_source_identity,
        "row_identity_sha256": row_identity_sha256,
        "source_identity_sha256": source_identity_sha256,
        "price_index_identity_sha256": price_index_identity_sha256,
    }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniversePriceSelectionV1:
    """一筆比較／收藏錨點；它是重開請求，不代表目前仍已核驗。"""

    query_json: str
    page_request_json: str
    result_identity_sha256: str
    page_identity_sha256: str
    stock_code: str
    price_state: str
    close_price: str | None
    observation_date: str | None
    raw_row_fingerprint_sha256: str | None
    snapshot_identity_sha256: str
    row_source_identity: str
    row_identity_sha256: str
    source_identity_sha256: str
    price_index_identity_sha256: str
    selection_identity_sha256: str
    schema_version: str = DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_SELECTION_V1_SCHEMA

    def __post_init__(self) -> None:
        query = _query_from_json(self.query_json)
        request = _request_from_json(self.page_request_json)
        if self.schema_version != DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_SELECTION_V1_SCHEMA:
            _fail("technical_universe_price_selection_schema_invalid")
        if (
            request.query_identity_sha256 != query.query_identity_sha256
            or not _SHA256_RE.fullmatch(self.result_identity_sha256)
            or not _SHA256_RE.fullmatch(self.page_identity_sha256)
            or not isinstance(self.stock_code, str)
            or _STOCK_CODE_RE.fullmatch(self.stock_code) is None
            or self.price_state not in _PRICE_STATES
            or not isinstance(self.row_source_identity, str)
            or not self.row_source_identity
            or len(self.row_source_identity) > 256
        ):
            _fail("technical_universe_price_selection_identity_fields_invalid")
        _validate_decimal_text(self.close_price, nullable=True, code="technical_universe_price_selection_price_invalid")
        if self.observation_date is not None:
            if not isinstance(self.observation_date, str):
                _fail("technical_universe_price_selection_date_invalid")
            try:
                parsed_date = date.fromisoformat(self.observation_date)
            except ValueError as exc:
                raise DailyMarketTechnicalUniversePriceComparisonV1Error(
                    "technical_universe_price_selection_date_invalid"
                ) from exc
            if parsed_date.isoformat() != self.observation_date or parsed_date > query.source.decision_date:
                _fail("technical_universe_price_selection_date_invalid")
        _require_sha(self.snapshot_identity_sha256, "technical_universe_price_selection_snapshot_invalid")
        _require_sha(self.row_identity_sha256, "technical_universe_price_selection_row_invalid")
        _require_sha(self.source_identity_sha256, "technical_universe_price_selection_source_invalid")
        _require_sha(self.price_index_identity_sha256, "technical_universe_price_selection_index_invalid")
        if self.raw_row_fingerprint_sha256 is not None:
            _require_sha(self.raw_row_fingerprint_sha256, "technical_universe_price_selection_row_fingerprint_invalid")
        if (
            self.source_identity_sha256 != query.source.source_identity_sha256
            or self.price_index_identity_sha256 != query.source.price_index_identity_sha256
        ):
            _fail("technical_universe_price_selection_source_mismatch")
        if self.price_state == "pass":
            if self.close_price is None or self.observation_date is None or self.raw_row_fingerprint_sha256 is None:
                _fail("technical_universe_price_selection_known_fact_incomplete")
            if Decimal(self.close_price) <= 0:
                _fail("technical_universe_price_selection_known_price_invalid")
        elif self.close_price is not None:
            _fail("technical_universe_price_selection_unknown_fact_has_price")
        expected = _sha256_json(self._body_without_identity())
        if self.selection_identity_sha256 != expected:
            _fail("technical_universe_price_selection_identity_mismatch")

    @classmethod
    def from_page(
        cls,
        query: DailyMarketTechnicalUniversePriceQueryV1,
        page: DailyMarketTechnicalUniversePricePageV1,
        stock_code: str,
    ) -> DailyMarketTechnicalUniversePriceSelectionV1:
        if not isinstance(query, DailyMarketTechnicalUniversePriceQueryV1):
            _fail("technical_universe_price_selection_query_type_invalid")
        if not isinstance(page, DailyMarketTechnicalUniversePricePageV1):
            _fail("technical_universe_price_selection_page_type_invalid")
        # 讀取 to_dict 會重新驗證後端 reader-issued seal 與頁面身份。
        page.to_dict()
        if page.request.query_identity_sha256 != query.query_identity_sha256:
            _fail("technical_universe_price_selection_page_query_mismatch")
        row = next(
            (item for item in page.rows if item.technical_row.stock_code == stock_code),
            None,
        )
        if row is None:
            _fail("technical_universe_price_selection_stock_not_in_page")
        fact = row.price_fact
        query_json = query.to_json()
        request_json = page.request.to_json()
        body = _selection_body(
            query_json=query_json,
            page_request_json=request_json,
            result_identity_sha256=page.result_identity_sha256,
            page_identity_sha256=page.page_identity_sha256,
            stock_code=stock_code,
            price_state=row.price_state,
            close_price=_canonical_decimal_text(fact.close_price),
            observation_date=fact.observation_date.isoformat() if fact.observation_date else None,
            raw_row_fingerprint_sha256=fact.raw_row_fingerprint_sha256,
            snapshot_identity_sha256=fact.snapshot_identity_sha256,
            row_source_identity=fact.source_identity,
            row_identity_sha256=row.row_identity_sha256,
            source_identity_sha256=query.source.source_identity_sha256,
            price_index_identity_sha256=query.source.price_index_identity_sha256,
        )
        return cls(
            **{key: cast(str, value) for key, value in body.items() if key not in {"schema_version", "unit"}},
            selection_identity_sha256=_sha256_json(body),
        )

    @classmethod
    def from_dict(cls, payload: object) -> DailyMarketTechnicalUniversePriceSelectionV1:
        expected = {
            "schema_version", "query_json", "page_request_json", "result_identity_sha256",
            "page_identity_sha256", "stock_code", "price_state", "close_price", "unit",
            "observation_date", "raw_row_fingerprint_sha256", "snapshot_identity_sha256",
            "row_source_identity", "row_identity_sha256", "source_identity_sha256",
            "price_index_identity_sha256", "selection_identity_sha256",
        }
        if not isinstance(payload, Mapping) or set(payload) != expected:
            _fail("technical_universe_price_selection_fields_invalid")
        if payload.get("unit") != "TWD/share":
            _fail("technical_universe_price_selection_unit_invalid")
        result = cls(
            query_json=cast(str, payload["query_json"]),
            page_request_json=cast(str, payload["page_request_json"]),
            result_identity_sha256=cast(str, payload["result_identity_sha256"]),
            page_identity_sha256=cast(str, payload["page_identity_sha256"]),
            stock_code=cast(str, payload["stock_code"]),
            price_state=cast(str, payload["price_state"]),
            close_price=cast(str | None, payload["close_price"]),
            observation_date=cast(str | None, payload["observation_date"]),
            raw_row_fingerprint_sha256=cast(str | None, payload["raw_row_fingerprint_sha256"]),
            snapshot_identity_sha256=cast(str, payload["snapshot_identity_sha256"]),
            row_source_identity=cast(str, payload["row_source_identity"]),
            row_identity_sha256=cast(str, payload["row_identity_sha256"]),
            source_identity_sha256=cast(str, payload["source_identity_sha256"]),
            price_index_identity_sha256=cast(str, payload["price_index_identity_sha256"]),
            selection_identity_sha256=cast(str, payload["selection_identity_sha256"]),
            schema_version=cast(str, payload["schema_version"]),
        )
        if result.to_dict() != dict(payload):
            _fail("technical_universe_price_selection_noncanonical")
        return result

    @classmethod
    def from_json(cls, raw: bytes | str) -> DailyMarketTechnicalUniversePriceSelectionV1:
        result = cls.from_dict(_parse_json(
            raw,
            maximum_bytes=DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_SELECTION_MAX_BYTES,
            code="technical_universe_price_selection_json_invalid",
        ))
        encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
        if result.to_json().encode("utf-8") != encoded:
            _fail("technical_universe_price_selection_json_noncanonical")
        return result

    @property
    def query(self) -> DailyMarketTechnicalUniversePriceQueryV1:
        return _query_from_json(self.query_json)

    @property
    def page_request(self) -> DailyMarketTechnicalUniversePricePageRequestV1:
        return _request_from_json(self.page_request_json)

    @property
    def key(self) -> tuple[str, str, int, int, str]:
        query = self.query
        request = self.page_request
        return (
            query.source.source_identity_sha256,
            query.query_identity_sha256,
            request.page_index,
            request.page_size,
            self.stock_code,
        )

    def _body_without_identity(self) -> dict[str, object]:
        return _selection_body(
            query_json=self.query_json,
            page_request_json=self.page_request_json,
            result_identity_sha256=self.result_identity_sha256,
            page_identity_sha256=self.page_identity_sha256,
            stock_code=self.stock_code,
            price_state=self.price_state,
            close_price=self.close_price,
            observation_date=self.observation_date,
            raw_row_fingerprint_sha256=self.raw_row_fingerprint_sha256,
            snapshot_identity_sha256=self.snapshot_identity_sha256,
            row_source_identity=self.row_source_identity,
            row_identity_sha256=self.row_identity_sha256,
            source_identity_sha256=self.source_identity_sha256,
            price_index_identity_sha256=self.price_index_identity_sha256,
        )

    def to_dict(self) -> dict[str, object]:
        return {**self._body_without_identity(), "selection_identity_sha256": self.selection_identity_sha256}

    def to_json(self) -> str:
        raw = _canonical_json_bytes(self.to_dict())
        if len(raw) > DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_SELECTION_MAX_BYTES:
            _fail("technical_universe_price_selection_byte_limit")
        return raw.decode("utf-8")


@dataclass(frozen=True, slots=True)
class VerifiedPriceSelectionV1:
    """本次 fresh operation 已重新核驗的選取與其 exact 來源頁。"""

    selection: DailyMarketTechnicalUniversePriceSelectionV1
    session: DailyMarketTechnicalUniversePriceReadSessionV1
    query: DailyMarketTechnicalUniversePriceQueryV1
    result: DailyMarketTechnicalUniversePriceResultV1
    request: DailyMarketTechnicalUniversePricePageRequestV1
    page: DailyMarketTechnicalUniversePricePageV1
    row: DailyMarketTechnicalUniversePriceRowV1

    def __post_init__(self) -> None:
        if (
            not isinstance(self.session, DailyMarketTechnicalUniversePriceReadSessionV1)
            or not self.session.matches_query(self.query)
            or self.query.query_identity_sha256 != self.selection.query.query_identity_sha256
            or self.result.query != self.query
            or self.request.query_identity_sha256 != self.query.query_identity_sha256
            or self.request.page_index != self.selection.page_request.page_index
            or self.request.page_size != self.selection.page_request.page_size
            or self.page.request != self.request
            or self.page.result_identity_sha256 != self.result.result_identity_sha256
            or self.page.page_identity_sha256 != self.selection.page_identity_sha256
            or self.result.result_identity_sha256 != self.selection.result_identity_sha256
            or self.row.row_identity_sha256 != self.selection.row_identity_sha256
            or self.row.technical_row.stock_code != self.selection.stock_code
        ):
            _fail("technical_universe_price_verified_selection_mismatch")


def read_daily_market_technical_universe_price_selections_v1(
    selections: Sequence[DailyMarketTechnicalUniversePriceSelectionV1],
    *,
    cancel_callback: Callable[[], object] | None = None,
) -> tuple[VerifiedPriceSelectionV1, ...]:
    """在本次呼叫內按 exact source/query/page 去重並 fresh 重開選取。"""

    _check_cancel(cancel_callback)
    if isinstance(selections, (str, bytes)) or not isinstance(selections, Sequence):
        _fail("technical_universe_price_selection_sequence_invalid")
    if not 1 <= len(selections) <= DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_COMPARISON_MAX_ITEMS:
        _fail("technical_universe_price_selection_count_invalid")
    normalized_rows: list[DailyMarketTechnicalUniversePriceSelectionV1] = []
    total_selection_bytes = 0
    for item in selections:
        _check_cancel(cancel_callback)
        if isinstance(item, DailyMarketTechnicalUniversePriceSelectionV1):
            raw_selection = item.to_json().encode("utf-8")
            normalized_item = DailyMarketTechnicalUniversePriceSelectionV1.from_dict(item.to_dict())
        elif isinstance(item, Mapping):
            raw_selection = _canonical_json_bytes(item)
            normalized_item = DailyMarketTechnicalUniversePriceSelectionV1.from_dict(item)
        else:
            _fail("technical_universe_price_selection_type_invalid")
        if len(raw_selection) > DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_SELECTION_MAX_BYTES:
            _fail("technical_universe_price_selection_byte_limit")
        total_selection_bytes += len(raw_selection)
        if total_selection_bytes > DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_COMPARISON_MAX_BYTES:
            _fail("technical_universe_price_comparison_byte_limit")
        normalized_rows.append(normalized_item)
    normalized = tuple(normalized_rows)
    if len({item.key for item in normalized}) != len(normalized):
        _fail("technical_universe_price_selection_duplicate")

    # 完整 source descriptor 的 canonical bytes 才能共用同一次 session；
    # 相同 identity 卻有不同 payload 時 fail closed。
    groups: dict[str, list[int]] = {}
    query_by_id: dict[str, DailyMarketTechnicalUniversePriceQueryV1] = {}
    source_payloads: dict[str, bytes] = {}
    for index, item in enumerate(normalized):
        _check_cancel(cancel_callback)
        query = item.query
        source_key = query.source.source_identity_sha256
        source_bytes = _canonical_json_bytes(query.source.to_dict())
        previous_source = source_payloads.setdefault(source_key, source_bytes)
        if previous_source != source_bytes:
            _fail("technical_universe_price_source_identity_collision")
        groups.setdefault(source_key, []).append(index)
        previous_query = query_by_id.setdefault(query.query_identity_sha256, query)
        if previous_query.to_json() != query.to_json():
            _fail("technical_universe_price_query_identity_collision")

    verified: list[VerifiedPriceSelectionV1 | None] = [None] * len(normalized)
    for source_key, indices in groups.items():
        _check_cancel(cancel_callback)
        first_query = normalized[indices[0]].query
        try:
            session, reopened_query = open_daily_market_technical_universe_price_session_for_query_v1(
                first_query,
                cancel_callback=cancel_callback,
            )
        except (DailyMarketTechnicalUniversePriceQueryV1Error, OSError, ValueError) as exc:
            if isinstance(exc, InterruptedError):
                raise
            raise DailyMarketTechnicalUniversePriceComparisonV1Error(
                getattr(exc, "code", "technical_universe_price_selection_source_reopen_failed"),
                str(exc),
            ) from exc
        if (
            not isinstance(session, DailyMarketTechnicalUniversePriceReadSessionV1)
            or not isinstance(reopened_query, DailyMarketTechnicalUniversePriceQueryV1)
            or reopened_query.to_json() != first_query.to_json()
            or session.source.source_identity_sha256 != source_key
            or _canonical_json_bytes(session.source.to_dict()) != source_payloads[source_key]
        ):
            _fail("technical_universe_price_selection_source_reopen_mismatch")

        # 同一 exact source 下，每個 query 只執行一次，每個 page 只重讀一次。
        results: dict[str, DailyMarketTechnicalUniversePriceResultV1] = {}
        pages: dict[tuple[str, int, int], tuple[
            DailyMarketTechnicalUniversePriceResultV1,
            DailyMarketTechnicalUniversePricePageRequestV1,
            DailyMarketTechnicalUniversePricePageV1,
        ]] = {}
        for index in indices:
            _check_cancel(cancel_callback)
            saved = normalized[index]
            query = saved.query
            if query.query_identity_sha256 not in results:
                if not session.matches_query(query):
                    _fail("technical_universe_price_selection_query_source_mismatch")
                results[query.query_identity_sha256] = session.execute(
                    query,
                    cancel_callback=cancel_callback,
                )
            result = results[query.query_identity_sha256]
            saved_request = saved.page_request
            page_key = (query.query_identity_sha256, saved_request.page_index, saved_request.page_size)
            page_data = pages.get(page_key)
            if page_data is None:
                request = result.create_page_request(
                    saved_request.page_index,
                    page_size=saved_request.page_size,
                )
                if request.to_json() != saved.page_request_json:
                    _fail("technical_universe_price_selection_request_pin_mismatch")
                page = result.read_page(request, cancel_callback=cancel_callback)
                if not isinstance(page, DailyMarketTechnicalUniversePricePageV1):
                    _fail("technical_universe_price_selection_page_type_invalid")
                page.to_dict()
                page_data = (result, request, page)
                pages[page_key] = page_data
            result, request, page = page_data
            actual = DailyMarketTechnicalUniversePriceSelectionV1.from_page(
                query,
                page,
                saved.stock_code,
            )
            if actual.to_dict() != saved.to_dict():
                _fail("technical_universe_price_selection_pin_mismatch")
            row = next(
                row for row in page.rows if row.technical_row.stock_code == saved.stock_code
            )
            verified[index] = VerifiedPriceSelectionV1(
                selection=saved,
                session=session,
                query=query,
                result=result,
                request=request,
                page=page,
                row=row,
            )
    _check_cancel(cancel_callback)
    if any(item is None for item in verified):
        _fail("technical_universe_price_selection_publish_incomplete")
    return tuple(cast(VerifiedPriceSelectionV1, item) for item in verified)


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniversePriceComparisonColumnV1:
    """比較欄保留原 selection 與 fresh row，不混合不同來源的日期。"""

    verified: VerifiedPriceSelectionV1

    def __post_init__(self) -> None:
        if not isinstance(self.verified, VerifiedPriceSelectionV1):
            _fail("technical_universe_price_comparison_column_invalid")

    @property
    def selection(self) -> DailyMarketTechnicalUniversePriceSelectionV1:
        return self.verified.selection

    @property
    def row(self) -> DailyMarketTechnicalUniversePriceRowV1:
        return self.verified.row

    def to_dict(self) -> dict[str, object]:
        return {
            "selection": self.selection.to_dict(),
            "query_identity_sha256": self.verified.query.query_identity_sha256,
            "page_identity_sha256": self.verified.page.page_identity_sha256,
            "source_identity_sha256": self.verified.query.source.source_identity_sha256,
            "decision_date": self.verified.query.source.decision_date.isoformat(),
            "row": self.row.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniversePriceComparisonV1:
    """fresh verified 價格比較；各欄保留自己的日期與來源識別。"""

    columns: tuple[DailyMarketTechnicalUniversePriceComparisonColumnV1, ...]
    comparison_identity_sha256: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.columns, tuple)
            or not 2 <= len(self.columns) <= DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_COMPARISON_MAX_ITEMS
            or len({item.selection.key for item in self.columns}) != len(self.columns)
        ):
            _fail("technical_universe_price_comparison_columns_invalid")
        if self.comparison_identity_sha256 != _sha256_json(self._body_without_identity()):
            _fail("technical_universe_price_comparison_identity_mismatch")

    @classmethod
    def create(
        cls,
        columns: Sequence[DailyMarketTechnicalUniversePriceComparisonColumnV1],
    ) -> DailyMarketTechnicalUniversePriceComparisonV1:
        if isinstance(columns, (str, bytes)) or not isinstance(columns, Sequence):
            _fail("technical_universe_price_comparison_columns_invalid")
        values = tuple(columns)
        if any(not isinstance(item, DailyMarketTechnicalUniversePriceComparisonColumnV1) for item in values):
            _fail("technical_universe_price_comparison_columns_invalid")
        provisional = cls.__new__(cls)
        object.__setattr__(provisional, "columns", values)
        return cls(columns=values, comparison_identity_sha256=_sha256_json(provisional._body_without_identity()))

    def _body_without_identity(self) -> dict[str, object]:
        return {
            "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_COMPARISON_V1_SCHEMA,
            "columns": [item.to_dict() for item in self.columns],
            "source_available_at": None,
            "availability_status": "unknown",
            "historical_pit_eligible": False,
            "full_market_claim": False,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body_without_identity(), "comparison_identity_sha256": self.comparison_identity_sha256}

    def to_json(self) -> str:
        raw = _canonical_json_bytes(self.to_dict())
        if len(raw) > DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_COMPARISON_MAX_BYTES:
            _fail("technical_universe_price_comparison_byte_limit")
        return raw.decode("utf-8")


def read_daily_market_technical_universe_price_comparison_v1(
    selections: Sequence[DailyMarketTechnicalUniversePriceSelectionV1],
    *,
    cancel_callback: Callable[[], object] | None = None,
) -> DailyMarketTechnicalUniversePriceComparisonV1:
    """fresh 重開全部欄位；任一欄取消或 pins 不符便不發布部分結果。"""

    if isinstance(selections, (str, bytes)) or not isinstance(selections, Sequence):
        _fail("technical_universe_price_comparison_selection_sequence_invalid")
    if not 2 <= len(selections) <= DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_COMPARISON_MAX_ITEMS:
        _fail("technical_universe_price_comparison_count_invalid")
    verified = read_daily_market_technical_universe_price_selections_v1(
        selections,
        cancel_callback=cancel_callback,
    )
    columns = tuple(DailyMarketTechnicalUniversePriceComparisonColumnV1(item) for item in verified)
    _check_cancel(cancel_callback)
    comparison = DailyMarketTechnicalUniversePriceComparisonV1.create(columns)
    _check_cancel(cancel_callback)
    # 最後序列化檢查總大小；超限時不回傳部分比較。
    comparison.to_json()
    _check_cancel(cancel_callback)
    return comparison
