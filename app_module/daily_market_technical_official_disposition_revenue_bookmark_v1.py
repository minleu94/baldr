"""月營收保存研究的純應用收藏 DTO。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Callable, NoReturn, cast

from app_module.daily_market_technical_official_disposition_revenue_query_v1 import (
    DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1,
    DailyMarketTechnicalOfficialDispositionRevenueResultRowV1,
)
from app_module.daily_market_technical_official_disposition_revenue_source_v1 import (
    DailyMarketTechnicalOfficialDispositionRevenueExactReadV1,
    DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1,
)


DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_BOOKMARK_SCHEMA_V1 = (
    "daily-market-technical-official-disposition-revenue-bookmark.v1"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_BOOKMARK_SOURCE = (
    "technical_official_disposition_revenue_research_bookmark"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_BOOKMARK_MAX_BYTES = 64 * 1024 * 1024
_MAX_JSON_DEPTH = 32
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STOCK_CODE_RE = re.compile(r"^[A-Z0-9]{1,16}$")


class DailyMarketTechnicalOfficialDispositionRevenueBookmarkV1Error(ValueError):
    """月營收研究收藏的穩定拒絕碼。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise DailyMarketTechnicalOfficialDispositionRevenueBookmarkV1Error(
        f"technical_official_disposition_revenue_bookmark_v1_{code}"
    )


def _canonical_bytes(value: object) -> bytes:
    def reject(item: object, depth: int) -> None:
        if depth > _MAX_JSON_DEPTH:
            _fail("json_depth_limit")
        if isinstance(item, float):
            _fail("json_float_forbidden")
        if isinstance(item, Mapping):
            for key, child in item.items():
                if not isinstance(key, str):
                    _fail("json_key_invalid")
                reject(child, depth + 1)
        elif isinstance(item, (list, tuple)):
            for child in item:
                reject(child, depth + 1)

    reject(value, 0)
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise DailyMarketTechnicalOfficialDispositionRevenueBookmarkV1Error(
            "technical_official_disposition_revenue_bookmark_v1_json_invalid"
        ) from exc


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _preflight_depth(text: str) -> None:
    depth = 0
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > _MAX_JSON_DEPTH:
                _fail("json_depth_limit")
        elif char in "]}":
            depth -= 1
            if depth < 0:
                _fail("json_invalid")
    if in_string or depth != 0:
        _fail("json_invalid")


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail("json_duplicate_key")
        result[key] = value
    return result


def _parse_json(raw: str | bytes) -> object:
    if isinstance(raw, bytes):
        if len(raw) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_BOOKMARK_MAX_BYTES:
            _fail("json_byte_limit")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DailyMarketTechnicalOfficialDispositionRevenueBookmarkV1Error(
                "technical_official_disposition_revenue_bookmark_v1_json_encoding_invalid"
            ) from exc
    elif isinstance(raw, str):
        if len(raw.encode("utf-8")) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_BOOKMARK_MAX_BYTES:
            _fail("json_byte_limit")
        text = raw
    else:
        _fail("json_type_invalid")
    _preflight_depth(text)
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_pairs,
            parse_constant=lambda _value: _fail("json_nonfinite_invalid"),
        )
    except DailyMarketTechnicalOfficialDispositionRevenueBookmarkV1Error:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise DailyMarketTechnicalOfficialDispositionRevenueBookmarkV1Error(
            "technical_official_disposition_revenue_bookmark_v1_json_invalid"
        ) from exc
    if _canonical_bytes(value) != text.encode("utf-8"):
        _fail("json_noncanonical")
    return value


def _row_fact_context(row: DailyMarketTechnicalOfficialDispositionRevenueResultRowV1) -> dict[str, object]:
    """保留跨 operation 穩定的實際來源事實；不把 operation SHA 當永久來源 pin。"""

    return {
        "stock_code": row.stock_code,
        "f17_fact": row.fact_row.to_dict(),
        "technical_row": None if row.technical_row is None else row.technical_row.to_dict(),
        "ma_entry": None if row.ma_entry is None else row.ma_entry.to_dict(),
        "monthly_source_fact": row.monthly_entry.source_fact.to_dict(),
        "monthly_projected_fact": row.monthly_entry.projected_fact.to_dict(),
        "filter_evaluation": {
            "row_scope": row.filter_evaluation.row_scope,
            "row_scope_match": row.filter_evaluation.row_scope_match,
            "stock_filter_match": row.filter_evaluation.stock_filter_match,
            "market_assignment_match": row.filter_evaluation.market_assignment_match,
            "market_assignment_truth": row.filter_evaluation.market_assignment_truth,
            "official_disposal_match": row.filter_evaluation.official_disposal_match,
            "official_disposal_truth": row.filter_evaluation.official_disposal_truth,
        },
        "technical_condition_truth": row.technical_condition_truth,
        "ma_condition_truth": row.ma_condition_truth,
        "revenue_condition_truth": row.revenue_condition_truth,
        "composite_condition_truth": row.composite_condition_truth,
        "hard_filter_match": row.hard_filter_match,
        "included_by_unknown_policy": row.included_by_unknown_policy,
        "scope": "current_only",
        "official_available_at": None,
        "monthly_official_available_at": None,
        "monthly_availability_status": "unknown",
        "historical_pit_eligible": False,
    }


def _bookmark_body(
    *,
    saved_recipe_json: str,
    selected_page_request_json: str,
    selected_stock_code: str,
    selected_stock_name: str,
    selected_result_identity_sha256: str,
    selected_query_identity_sha256: str,
    selected_row_identity_sha256: str,
    selected_fact_context_json: str,
    selected_fact_context_identity_sha256: str,
) -> dict[str, object]:
    return {
        "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_BOOKMARK_SCHEMA_V1,
        "saved_recipe_json": saved_recipe_json,
        "selected_page_request_json": selected_page_request_json,
        "selected_stock_code": selected_stock_code,
        "selected_stock_name": selected_stock_name,
        "selected_result_identity_sha256": selected_result_identity_sha256,
        "selected_query_identity_sha256": selected_query_identity_sha256,
        "selected_row_identity_sha256": selected_row_identity_sha256,
        "selected_fact_context_json": selected_fact_context_json,
        "selected_fact_context_identity_sha256": selected_fact_context_identity_sha256,
        "source_scope": "current_only",
        "monthly_availability_status": "unknown",
        "historical_pit_eligible": False,
        "bookmark_is_reader_qualification": False,
    }


def _validate_stock_code(value: object) -> str:
    if type(value) is not str or _STOCK_CODE_RE.fullmatch(value) is None:
        _fail("stock_code_invalid")
    return value


def _validate_sha(value: object, code: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        _fail(code)
    return value


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionRevenueBookmarkV1:
    """Watchlist 可保存的研究參照；自身 JSON 不代表來源核驗資格。"""

    saved_recipe_json: str
    selected_page_request_json: str
    selected_stock_code: str
    selected_stock_name: str
    selected_result_identity_sha256: str
    selected_query_identity_sha256: str
    selected_row_identity_sha256: str
    selected_fact_context_json: str
    selected_fact_context_identity_sha256: str
    bookmark_identity_sha256: str
    schema_version: str = DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_BOOKMARK_SCHEMA_V1

    def __post_init__(self) -> None:
        if self.schema_version != DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_BOOKMARK_SCHEMA_V1:
            _fail("schema_unsupported")
        _validate_stock_code(self.selected_stock_code)
        if self.selected_stock_name != self.selected_stock_code:
            _fail("stock_name_must_be_source_label")
        _validate_sha(self.selected_result_identity_sha256, "result_identity_invalid")
        _validate_sha(self.selected_query_identity_sha256, "query_identity_invalid")
        _validate_sha(self.selected_row_identity_sha256, "row_identity_invalid")
        _validate_sha(self.selected_fact_context_identity_sha256, "fact_context_identity_invalid")
        recipe = DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1.from_json(
            self.saved_recipe_json
        )
        request = DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1.from_json(
            self.selected_page_request_json
        )
        if (
            recipe.to_json() != self.saved_recipe_json
            or request.to_json() != self.selected_page_request_json
            or request.page_index != recipe.page_index
            or request.page_size != recipe.page_size
            or request.query.query_identity_sha256 != self.selected_query_identity_sha256
        ):
            _fail("recipe_page_context_mismatch")
        context = _parse_json(self.selected_fact_context_json)
        if not isinstance(context, Mapping) or context.get("stock_code") != self.selected_stock_code:
            _fail("fact_context_invalid")
        if _sha256(context) != self.selected_fact_context_identity_sha256:
            _fail("fact_context_identity_mismatch")
        body = _bookmark_body(
            saved_recipe_json=self.saved_recipe_json,
            selected_page_request_json=self.selected_page_request_json,
            selected_stock_code=self.selected_stock_code,
            selected_stock_name=self.selected_stock_name,
            selected_result_identity_sha256=self.selected_result_identity_sha256,
            selected_query_identity_sha256=self.selected_query_identity_sha256,
            selected_row_identity_sha256=self.selected_row_identity_sha256,
            selected_fact_context_json=self.selected_fact_context_json,
            selected_fact_context_identity_sha256=self.selected_fact_context_identity_sha256,
        )
        _validate_sha(self.bookmark_identity_sha256, "bookmark_identity_invalid")
        if _sha256(body) != self.bookmark_identity_sha256:
            _fail("bookmark_identity_mismatch")
        if len(_canonical_bytes(self.to_dict())) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_BOOKMARK_MAX_BYTES:
            _fail("byte_limit")

    @classmethod
    def from_exact_read(
        cls,
        exact_read: DailyMarketTechnicalOfficialDispositionRevenueExactReadV1,
        stock_code: str,
    ) -> DailyMarketTechnicalOfficialDispositionRevenueBookmarkV1:
        if type(exact_read) is not DailyMarketTechnicalOfficialDispositionRevenueExactReadV1:
            _fail("exact_read_invalid")
        code = _validate_stock_code(stock_code)
        recipe = DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1.from_exact_read(exact_read)
        return cls.from_issued_result_page(
            recipe=recipe,
            page_request=exact_read.page_request,
            page=exact_read.page,
            stock_code=code,
        )

    @classmethod
    def from_issued_result_page(
        cls,
        *,
        recipe: DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1,
        page_request: DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1,
        page: object,
        stock_code: str,
    ) -> DailyMarketTechnicalOfficialDispositionRevenueBookmarkV1:
        """從同一 reader-issued result/page 建立收藏，不能以 archive JSON 自行發行。"""

        from app_module.daily_market_technical_official_disposition_revenue_query_v1 import (
            DailyMarketTechnicalOfficialDispositionRevenueQueryPageV1,
        )

        if type(recipe) is not DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1:
            _fail("saved_recipe_invalid")
        if type(page_request) is not DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1:
            _fail("page_request_invalid")
        if type(page) is not DailyMarketTechnicalOfficialDispositionRevenueQueryPageV1:
            _fail("page_invalid")
        code = _validate_stock_code(stock_code)
        page_dict = page.to_dict()
        query = page.query
        request_query = page_request.query
        if (
            request_query.query_identity_sha256 != query.query_identity_sha256
            or page_request.request_identity_sha256 != page.request_identity_sha256
            or page_request.page_index != page.page_index
            or page_request.page_size != page.page_size
            or page_dict.get("operation_identity_sha256") != page.operation_identity_sha256
            or page_request.page_index != recipe.page_index
            or page_request.page_size != recipe.page_size
        ):
            _fail("issued_page_context_mismatch")
        row = next((item for item in page.rows if item.stock_code == code), None)
        if type(row) is not DailyMarketTechnicalOfficialDispositionRevenueResultRowV1:
            _fail("selected_stock_not_on_issued_page")
        if row.row_identity_sha256 not in {
            cast(str, _mapping_row.get("row_identity_sha256"))
            for _mapping_row in cast(list[object], page_dict.get("rows", []))
            if isinstance(_mapping_row, Mapping)
            and _mapping_row.get("stock_code") == code
        }:
            _fail("issued_row_context_mismatch")
        recipe_query = DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1.from_json(
            recipe.to_json()
        )
        f17_query = query.ma_query.f17_query
        if (
            recipe_query.f17_query_json != f17_query.to_json()
            or recipe_query.ma_states != query.ma_query.ma_states
            or recipe_query.minimum_yoy_percent != query.minimum_yoy_percent
            or recipe_query.condition_combine_mode != query.condition_combine_mode
            or recipe_query.unknown_policy != query.unknown_policy
            or tuple(item.to_dict() for item in recipe_query.sort_clauses)
            != tuple(item.to_dict() for item in query.sort_clauses)
        ):
            _fail("recipe_query_context_mismatch")
        context = _row_fact_context(row)
        context_json = _canonical_bytes(context).decode("utf-8")
        body = _bookmark_body(
            saved_recipe_json=recipe.to_json(),
            selected_page_request_json=page_request.to_json(),
            selected_stock_code=code,
            selected_stock_name=code,
            selected_result_identity_sha256=page.operation_identity_sha256,
            selected_query_identity_sha256=query.query_identity_sha256,
            selected_row_identity_sha256=row.row_identity_sha256,
            selected_fact_context_json=context_json,
            selected_fact_context_identity_sha256=_sha256(context),
        )
        return cls(
            saved_recipe_json=recipe.to_json(),
            selected_page_request_json=page_request.to_json(),
            selected_stock_code=code,
            selected_stock_name=code,
            selected_result_identity_sha256=page.operation_identity_sha256,
            selected_query_identity_sha256=query.query_identity_sha256,
            selected_row_identity_sha256=row.row_identity_sha256,
            selected_fact_context_json=context_json,
            selected_fact_context_identity_sha256=_sha256(context),
            bookmark_identity_sha256=_sha256(body),
        )

    @classmethod
    def from_dict(cls, payload: object) -> DailyMarketTechnicalOfficialDispositionRevenueBookmarkV1:
        expected = {
            "schema_version", "saved_recipe_json", "selected_page_request_json",
            "selected_stock_code", "selected_stock_name", "selected_result_identity_sha256",
            "selected_query_identity_sha256", "selected_row_identity_sha256",
            "selected_fact_context_json", "selected_fact_context_identity_sha256",
            "source_scope", "monthly_availability_status", "historical_pit_eligible",
            "bookmark_is_reader_qualification", "bookmark_identity_sha256", "source",
        }
        if not isinstance(payload, Mapping) or set(payload) != expected:
            _fail("fields_invalid")
        if (
            payload.get("source") != DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_BOOKMARK_SOURCE
            or payload.get("source_scope") != "current_only"
            or payload.get("monthly_availability_status") != "unknown"
            or payload.get("historical_pit_eligible") is not False
            or payload.get("bookmark_is_reader_qualification") is not False
        ):
            _fail("qualification_invalid")
        result = cls(
            saved_recipe_json=cast(str, payload.get("saved_recipe_json")),
            selected_page_request_json=cast(str, payload.get("selected_page_request_json")),
            selected_stock_code=cast(str, payload.get("selected_stock_code")),
            selected_stock_name=cast(str, payload.get("selected_stock_name")),
            selected_result_identity_sha256=cast(str, payload.get("selected_result_identity_sha256")),
            selected_query_identity_sha256=cast(str, payload.get("selected_query_identity_sha256")),
            selected_row_identity_sha256=cast(str, payload.get("selected_row_identity_sha256")),
            selected_fact_context_json=cast(str, payload.get("selected_fact_context_json")),
            selected_fact_context_identity_sha256=cast(str, payload.get("selected_fact_context_identity_sha256")),
            bookmark_identity_sha256=cast(str, payload.get("bookmark_identity_sha256")),
            schema_version=cast(str, payload.get("schema_version")),
        )
        if result.to_dict() != dict(payload):
            _fail("noncanonical")
        return result

    @classmethod
    def from_json(cls, raw: str | bytes) -> DailyMarketTechnicalOfficialDispositionRevenueBookmarkV1:
        payload = _parse_json(raw)
        result = cls.from_dict(payload)
        encoded = raw if isinstance(raw, bytes) else raw.encode("utf-8")
        if result.to_json().encode("utf-8") != encoded:
            _fail("noncanonical")
        return result

    @property
    def bookmark_id(self) -> str:
        return self.bookmark_identity_sha256

    @property
    def stock_code(self) -> str:
        return self.selected_stock_code

    @property
    def stock_name(self) -> str:
        return self.selected_stock_name

    @property
    def source(self) -> str:
        return DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_BOOKMARK_SOURCE

    @property
    def saved_recipe(self) -> DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1:
        return DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1.from_json(
            self.saved_recipe_json
        )

    def to_dict(self) -> dict[str, object]:
        body = _bookmark_body(
            saved_recipe_json=self.saved_recipe_json,
            selected_page_request_json=self.selected_page_request_json,
            selected_stock_code=self.selected_stock_code,
            selected_stock_name=self.selected_stock_name,
            selected_result_identity_sha256=self.selected_result_identity_sha256,
            selected_query_identity_sha256=self.selected_query_identity_sha256,
            selected_row_identity_sha256=self.selected_row_identity_sha256,
            selected_fact_context_json=self.selected_fact_context_json,
            selected_fact_context_identity_sha256=self.selected_fact_context_identity_sha256,
        )
        return {
            **body,
            "source": self.source,
            "bookmark_identity_sha256": self.bookmark_identity_sha256,
        }

    def to_json(self) -> str:
        raw = _canonical_bytes(self.to_dict())
        if len(raw) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_BOOKMARK_MAX_BYTES:
            _fail("byte_limit")
        return raw.decode("utf-8")

    def verify_exact_row(
        self,
        exact_read: DailyMarketTechnicalOfficialDispositionRevenueExactReadV1,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalOfficialDispositionRevenueResultRowV1:
        """在 fresh exact read 已完成後，核選取股票與穩定事實；不可只信 transport SHA。"""

        if cancel_callback is not None:
            cancelled = cancel_callback()
            if type(cancelled) is not bool:
                _fail("cancel_callback_invalid")
            if cancelled:
                _fail("cancelled")
        if type(exact_read) is not DailyMarketTechnicalOfficialDispositionRevenueExactReadV1:
            _fail("exact_read_invalid")
        if exact_read.saved_recipe.to_json() != self.saved_recipe_json:
            _fail("saved_recipe_mismatch")
        recipe = self.saved_recipe
        page_request = exact_read.page_request
        if (
            page_request.page_index != recipe.page_index
            or page_request.page_size != recipe.page_size
            or page_request.query.query_identity_sha256
            != exact_read.query.query_identity_sha256
        ):
            _fail("page_context_mismatch")
        row = next(
            (item for item in exact_read.page.rows if item.stock_code == self.selected_stock_code),
            None,
        )
        if type(row) is not DailyMarketTechnicalOfficialDispositionRevenueResultRowV1:
            _fail("selected_stock_not_on_reopened_page")
        actual_context = _row_fact_context(row)
        if (
            _sha256(actual_context) != self.selected_fact_context_identity_sha256
            or _canonical_bytes(actual_context).decode("utf-8") != self.selected_fact_context_json
        ):
            _fail("selected_fact_context_mismatch")
        if cancel_callback is not None:
            cancelled = cancel_callback()
            if type(cancelled) is not bool:
                _fail("cancel_callback_invalid")
            if cancelled:
                _fail("cancelled")
        return row
