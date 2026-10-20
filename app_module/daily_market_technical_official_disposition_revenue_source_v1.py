"""以固定 F17 bundle 與月營收 V2 archive 原子重建 F12 查詢。"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import stat
from threading import get_ident
from typing import TYPE_CHECKING, Literal, NoReturn, cast

from app_module.daily_market_monthly_revenue_yoy_index_v1 import (
    MAX_CODES_PER_BATCH,
    DailyMarketMonthlyRevenueYoyIndexCancelled,
    DailyMarketMonthlyRevenueYoyIndexError,
    DailyMarketMonthlyRevenueYoyIndexSessionV1,
)
from app_module.daily_market_technical_official_disposition_ma_query_v1 import (
    DailyMarketTechnicalOfficialDispositionMaSortClauseV1,
    MaState,
)
from app_module.daily_market_technical_official_disposition_revenue_query_v1 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_MAX_SORT_CLAUSES_V1,
    DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1,
    DailyMarketTechnicalOfficialDispositionRevenueQueryV1,
    DailyMarketTechnicalOfficialDispositionRevenueQueryPageV1,
    DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV1,
    UnknownPolicy,
    CombineMode,
)
from data_module.daily_market_monthly_revenue_read_session_v1 import (
    DailyMarketMonthlyRevenueSourceReferenceV2,
)
from data_module.recommendation_current_fundamental_provider import (
    RecommendationCurrentFundamentalProvider,
)
from decision_module.factors.selection_fundamental_chip_rules import (
    SELECTION_REVENUE_YOY_METHOD_ID,
    SELECTION_REVENUE_YOY_METHOD_VERSION,
)

if TYPE_CHECKING:
    from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
        DailyMarketTechnicalOfficialDispositionReadSessionV1,
        DailyMarketTechnicalOfficialDispositionSortClauseV1,
        RowScope,
    )
    from app_module.daily_market_technical_official_disposition_query_v1 import (
        DailyMarketTechnicalOfficialDispositionQueryV1,
    )
    from app_module.daily_market_technical_parent_v4_query import (
        DailyMarketTechnicalRuleStateFilterV4,
    )


DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_SOURCE_SCHEMA_V1 = (
    "daily-market-technical-official-disposition-revenue-source.v1"
)
_SOURCE_ISSUER = object()
_REPARSE_POINT = 0x400
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_RECIPE_SCHEMA_V1 = (
    "daily-market-technical-official-disposition-revenue-saved-recipe.v1"
)
_MAX_RECIPE_BYTES = 64 * 1024 * 1024
_MAX_RECIPE_DEPTH = 32
_RECIPE_MA_STATE_ORDER = ("match", "no_match", "unknown")


class DailyMarketTechnicalOfficialDispositionRevenueSourceV1Error(ValueError):
    """雙來源重開與合併的穩定拒絕錯誤。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"technical_official_revenue_source_v1_{code}")


class DailyMarketTechnicalOfficialDispositionRevenueSourceV1Cancelled(
    DailyMarketTechnicalOfficialDispositionRevenueSourceV1Error
):
    """雙來源重開或查詢收到 cooperative cancellation。"""


def _fail(code: str) -> NoReturn:
    raise DailyMarketTechnicalOfficialDispositionRevenueSourceV1Error(code)


def _canonical_sha256(value: object) -> str:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise DailyMarketTechnicalOfficialDispositionRevenueSourceV1Error(
            "identity_payload_invalid"
        ) from exc
    return hashlib.sha256(payload).hexdigest()


def _recipe_decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if type(value) is not Decimal or not value.is_finite():
        _fail("saved_recipe_decimal_invalid")
    parts = value.as_tuple()
    if type(parts.exponent) is not int or len(parts.digits) > 64 or abs(parts.exponent) > 128:
        _fail("saved_recipe_decimal_bounds_invalid")
    if value == 0:
        return "0"
    rendered = format(value, "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def _recipe_canonical_bytes(value: object) -> bytes:
    def reject(value_to_check: object, depth: int = 0) -> None:
        if depth > _MAX_RECIPE_DEPTH:
            _fail("saved_recipe_json_depth_limit")
        if isinstance(value_to_check, float):
            _fail("saved_recipe_float_forbidden")
        if isinstance(value_to_check, dict):
            for key, item in value_to_check.items():
                if not isinstance(key, str):
                    _fail("saved_recipe_json_key_invalid")
                reject(item, depth + 1)
        elif isinstance(value_to_check, list):
            for item in value_to_check:
                reject(item, depth + 1)

    reject(value)
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise DailyMarketTechnicalOfficialDispositionRevenueSourceV1Error(
            "saved_recipe_json_invalid"
        ) from exc


def _recipe_depth_preflight(text: str) -> None:
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
            if depth > _MAX_RECIPE_DEPTH:
                _fail("saved_recipe_json_depth_limit")
        elif char in "]}":
            depth -= 1
            if depth < 0:
                _fail("saved_recipe_json_invalid")
    if quoted or escaped or depth != 0:
        _fail("saved_recipe_json_invalid")


def _parse_recipe_json(raw: str | bytes) -> object:
    try:
        encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
        if type(encoded) is not bytes or len(encoded) > _MAX_RECIPE_BYTES:
            _fail("saved_recipe_json_byte_limit")
        text = encoded.decode("utf-8")
        _recipe_depth_preflight(text)

        def unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in pairs:
                if key in result:
                    _fail("saved_recipe_duplicate_json_key")
                result[key] = value
            return result

        payload = json.loads(
            text,
            object_pairs_hook=unique_pairs,
            parse_float=lambda _value: _fail("saved_recipe_float_forbidden"),
            parse_constant=lambda _value: _fail("saved_recipe_json_invalid"),
        )
        if _recipe_canonical_bytes(payload) != encoded:
            _fail("saved_recipe_json_noncanonical")
        return payload
    except DailyMarketTechnicalOfficialDispositionRevenueSourceV1Error:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalOfficialDispositionRevenueSourceV1Error(
            "saved_recipe_json_invalid"
        ) from exc


def _poll_cancel(callback: Callable[[], object] | None) -> None:
    if callback is None:
        return
    if not callable(callback):
        _fail("cancel_callback_invalid")
    try:
        value = callback()
    except Exception as exc:
        raise DailyMarketTechnicalOfficialDispositionRevenueSourceV1Error(
            "cancel_check_failed"
        ) from exc
    if type(value) is not bool:
        _fail("cancel_callback_invalid")
    if value:
        raise DailyMarketTechnicalOfficialDispositionRevenueSourceV1Cancelled(
            "cancelled"
        )


def _parse_cutoff(value: object, code: str) -> datetime:
    if not isinstance(value, str) or len(value) > 128:
        _fail(code)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise DailyMarketTechnicalOfficialDispositionRevenueSourceV1Error(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail(code)
    return parsed.astimezone(timezone.utc)


def _overlaps(left: Path, right: Path) -> bool:
    left_text = os.path.normcase(os.path.abspath(str(left)))
    right_text = os.path.normcase(os.path.abspath(str(right)))
    try:
        common = os.path.normcase(os.path.commonpath((left_text, right_text)))
    except ValueError:
        return False
    return common in {left_text, right_text}


def _reject_reparse_ancestors(path: Path, *, leaf_may_not_exist: bool) -> None:
    """只檢查本次 operation 路徑，不對歷史來源路徑做實體解析。"""

    absolute = Path(os.path.abspath(str(path)))
    components: list[Path] = []
    current = absolute
    while current != current.parent:
        components.append(current)
        current = current.parent
    for component in reversed(components):
        try:
            info = component.lstat()
        except FileNotFoundError:
            if leaf_may_not_exist and component == absolute:
                continue
            _fail("operation_root_ancestor_missing")
        if stat.S_ISLNK(info.st_mode) or (
            getattr(info, "st_file_attributes", 0) & _REPARSE_POINT
        ):
            _fail("operation_root_reparse_component")


def _new_operation_root(
    operation_root: Path | str,
    *,
    f17_query: DailyMarketTechnicalOfficialDispositionQueryV1,
    source_reference: DailyMarketMonthlyRevenueSourceReferenceV2,
) -> Path:
    if not isinstance(operation_root, (Path, str)):
        _fail("operation_root_invalid")
    raw = Path(operation_root).expanduser()
    if not raw.is_absolute() or ".." in raw.parts:
        _fail("operation_root_must_be_absolute_and_normalized")
    root = Path(os.path.abspath(str(raw)))
    if root.exists() or root.is_symlink():
        _fail("operation_root_must_be_new")
    if not root.parent.is_dir():
        _fail("operation_root_parent_missing")
    _reject_reparse_ancestors(root, leaf_may_not_exist=True)

    snapshot = Path(source_reference.snapshot_reference.snapshot_root)
    archive = Path(source_reference.raw_archive_reference.raw_archive_root)
    protected: tuple[Path, ...] = (
        Path(f17_query.bundle_output_root),
        snapshot,
        archive,
        Path(source_reference.raw_archive_reference.archived_monthly_source_root),
        Path(source_reference.raw_archive_reference.original_monthly_source_root),
        Path(os.environ.get("DATA_ROOT", "F:/Min/Python/Project/FA_Data")),
    )
    output_env = os.environ.get("OUTPUT_ROOT")
    if output_env:
        protected = (*protected, Path(output_env))
    if any(_overlaps(root, other) for other in protected):
        _fail("operation_root_overlaps_source_or_formal_root")
    try:
        root.mkdir(exist_ok=False)
    except FileExistsError as exc:
        raise DailyMarketTechnicalOfficialDispositionRevenueSourceV1Error(
            "operation_root_must_be_new"
        ) from exc
    except OSError as exc:
        raise DailyMarketTechnicalOfficialDispositionRevenueSourceV1Error(
            "operation_root_create_failed"
        ) from exc
    _reject_reparse_ancestors(root, leaf_may_not_exist=False)
    return root


class _ExactReadStateV1:
    __slots__ = (
        "owner_thread_id",
        "f17_session",
        "monthly_index_session",
        "combined_session",
        "result",
        "request",
        "page",
        "closed",
        "monthly_connection_closed",
    )

    def __init__(
        self,
        *,
        f17_session: object,
        monthly_index_session: DailyMarketMonthlyRevenueYoyIndexSessionV1,
        combined_session: object,
        result: DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV1,
        request: DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1,
        page: DailyMarketTechnicalOfficialDispositionRevenueQueryPageV1,
    ) -> None:
        self.owner_thread_id = get_ident()
        self.f17_session: object | None = f17_session
        self.monthly_index_session: DailyMarketMonthlyRevenueYoyIndexSessionV1 | None = (
            monthly_index_session
        )
        self.combined_session: object | None = combined_session
        self.result: DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV1 | None = result
        self.request: DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1 | None = request
        self.page: DailyMarketTechnicalOfficialDispositionRevenueQueryPageV1 | None = page
        self.closed = False
        self.monthly_connection_closed = monthly_index_session.closed


class _ExactReadAnchorV1:
    __slots__ = ("identity_sha256", "subject", "locked")

    def __init__(self, identity_sha256: str, *, issuer: object) -> None:
        if issuer is not _SOURCE_ISSUER:
            _fail("source_anchor_issuer_invalid")
        self.identity_sha256 = identity_sha256
        self.subject: object | None = None
        self.locked = True

    def claim(self, subject: object) -> None:
        if self.subject is None:
            object.__setattr__(self, "subject", subject)
        elif self.subject is not subject:
            _fail("source_anchor_subject_mismatch")

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "locked", False):
            raise AttributeError("source operation anchor is immutable")
        object.__setattr__(self, name, value)


class DailyMarketTechnicalOfficialDispositionRevenueExactReadV1:
    """兩來源已 exact-open、全母體執行並發行的可翻頁 operation。"""

    _state: _ExactReadStateV1
    _query: DailyMarketTechnicalOfficialDispositionRevenueQueryV1 | None
    _f17_query: DailyMarketTechnicalOfficialDispositionQueryV1
    _monthly_source_reference: DailyMarketMonthlyRevenueSourceReferenceV2
    _source_pair_identity_sha256: str
    _anchor: _ExactReadAnchorV1
    _locked: bool

    __slots__ = (
        "_state",
        "_query",
        "_f17_query",
        "_monthly_source_reference",
        "_source_pair_identity_sha256",
        "_anchor",
        "_locked",
    )

    def __init__(
        self,
        *,
        f17_query: DailyMarketTechnicalOfficialDispositionQueryV1,
        monthly_source_reference: DailyMarketMonthlyRevenueSourceReferenceV2,
        source_pair_identity_sha256: str,
        state: _ExactReadStateV1,
        issuer: object,
    ) -> None:
        if issuer is not _SOURCE_ISSUER:
            _fail("source_result_not_reader_issued")
        object.__setattr__(self, "_locked", False)
        object.__setattr__(self, "_state", state)
        object.__setattr__(self, "_query", state.result.query if state.result is not None else None)
        object.__setattr__(self, "_f17_query", f17_query)
        object.__setattr__(self, "_monthly_source_reference", monthly_source_reference)
        object.__setattr__(self, "_source_pair_identity_sha256", source_pair_identity_sha256)
        anchor = _ExactReadAnchorV1(source_pair_identity_sha256, issuer=_SOURCE_ISSUER)
        object.__setattr__(self, "_anchor", anchor)
        anchor.claim(self)
        self._validate_open()
        object.__setattr__(self, "_locked", True)

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_locked", False):
            raise AttributeError("exact read is immutable")
        object.__setattr__(self, name, value)

    @property
    def closed(self) -> bool:
        return self._state.closed

    @property
    def source_pair_identity_sha256(self) -> str:
        self._validate_open()
        return self._source_pair_identity_sha256

    @property
    def query(self) -> DailyMarketTechnicalOfficialDispositionRevenueQueryV1:
        self._validate_open()
        query = self._query
        if query is None:
            _fail("source_query_closed")
        return query

    @property
    def result(self) -> DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV1:
        self._validate_open()
        result = self._state.result
        if result is None:
            _fail("source_result_closed")
        return result

    @property
    def page_request(self) -> DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1:
        self._validate_open()
        request = self._state.request
        if request is None:
            _fail("source_page_request_unavailable")
        return request

    @property
    def page(self) -> DailyMarketTechnicalOfficialDispositionRevenueQueryPageV1:
        self._validate_open()
        page = self._state.page
        if page is None:
            _fail("source_page_unavailable")
        return page

    @property
    def f17_query(self) -> DailyMarketTechnicalOfficialDispositionQueryV1:
        self._validate_open()
        return self._f17_query

    @property
    def monthly_source_reference(self) -> DailyMarketMonthlyRevenueSourceReferenceV2:
        self._validate_open()
        return self._monthly_source_reference

    @property
    def saved_recipe(self) -> DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1:
        """建立不含本次 operation identity 的可攜式保存 recipe。"""

        return DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1.from_exact_read(
            self
        )

    @property
    def monthly_source_clock_identity_sha256(self) -> str:
        """原封存來源的 clock pin；其身分不隨本次 operation 根目錄變動。"""

        self._validate_open()
        return self._monthly_source_reference.snapshot_reference.source_clock_identity_sha256

    @property
    def monthly_operation_clock_identity_sha256(self) -> str:
        """本次 exact reopen 綁定的 operation clock identity。"""

        self._validate_open()
        index_session = self._state.monthly_index_session
        if index_session is None:
            _fail("monthly_reader_unavailable")
        return index_session.index.source_clock_identity_sha256

    @property
    def monthly_sqlite_connection_closed(self) -> bool:
        return self._state.monthly_connection_closed

    @property
    def monthly_reader_database_path(self) -> Path:
        """回傳本次 operation 專屬 SQLite 副本路徑，供資源邊界核對。"""

        self._validate_open()
        index_session = self._state.monthly_index_session
        if index_session is None:
            _fail("monthly_reader_unavailable")
        return index_session.reader_database_path

    @property
    def source_scope(self) -> Literal["current_only"]:
        self._validate_open()
        return "current_only"

    @property
    def availability_status(self) -> Literal["unknown"]:
        self._validate_open()
        return "unknown"

    @property
    def official_available_at(self) -> None:
        self._validate_open()
        return None

    @property
    def monthly_official_available_at(self) -> None:
        self._validate_open()
        return None

    @property
    def historical_pit_eligible(self) -> Literal[False]:
        self._validate_open()
        return False

    def read_page(
        self,
        page_index: int,
        page_size: int,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalOfficialDispositionRevenueQueryPageV1:
        _poll_cancel(cancel_callback)
        self._validate_open()
        query = self.query
        request = DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1.create(
            query,
            page_index=page_index,
            page_size=page_size,
        )
        return self.read_page_request(request, cancel_callback=cancel_callback)

    def read_page_request(
        self,
        request: DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1 | str | bytes,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalOfficialDispositionRevenueQueryPageV1:
        _poll_cancel(cancel_callback)
        self._validate_open()
        if isinstance(request, (str, bytes)):
            request = DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1.from_json(
                request
            )
        if type(request) is not DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1:
            _fail("page_request_invalid")
        query = self.query
        if request.query.query_identity_sha256 != query.query_identity_sha256:
            _fail("page_request_query_mismatch")
        result = self._state.result
        if result is None:
            _fail("source_result_closed")
        page = result.read_page_request(request, cancel_callback=cancel_callback)
        _poll_cancel(cancel_callback)
        page.to_dict()
        self._state.request = request
        self._state.page = page
        return page

    def close(self) -> None:
        state = self._state
        if state.closed:
            return
        if get_ident() != state.owner_thread_id:
            _fail("wrong_owner_thread")
        index_session = state.monthly_index_session
        cleanup_error: BaseException | None = None
        try:
            if index_session is not None:
                index_session.close()
                if not index_session.closed:
                    _fail("monthly_reader_connection_not_closed")
        except BaseException as exc:
            cleanup_error = exc
        finally:
            # F17 及其 technical/MA reader 是 sealed 記憶體索引，沒有長駐連線。
            state.monthly_connection_closed = (
                index_session is None or index_session.closed
            )
            state.closed = True
            state.f17_session = None
            state.combined_session = None
            state.monthly_index_session = None
            state.result = None
            state.request = None
            state.page = None
        if cleanup_error is not None:
            raise cleanup_error

    def __enter__(self) -> DailyMarketTechnicalOfficialDispositionRevenueExactReadV1:
        self._validate_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> Literal[False]:
        try:
            self.close()
        except BaseException as cleanup_error:
            if exc is not None:
                raise DailyMarketTechnicalOfficialDispositionRevenueSourceV1Error(
                    "context_close_failed"
                ) from BaseExceptionGroup(
                    "primary revenue read error and close error", [exc, cleanup_error]
                )
            raise
        return False

    def _validate_open(self) -> None:
        if self._state.closed:
            _fail("source_operation_closed")
        if get_ident() != self._state.owner_thread_id:
            _fail("wrong_owner_thread")
        if (
            type(self._anchor) is not _ExactReadAnchorV1
            or self._anchor.subject is not self
            or self._anchor.identity_sha256 != self._source_pair_identity_sha256
            or self._query is None
            or self._state.result is None
            or self._query.query_identity_sha256
            != self._state.result.query.query_identity_sha256
        ):
            _fail("source_operation_not_reader_issued")


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1:
    """可攜的條件與雙來源固定參照；本 DTO 本身不授予來源核驗資格。"""

    f17_query_json: str
    monthly_source_reference_json: str
    monthly_source_reference_identity_sha256: str
    monthly_source_content_identity_sha256: str
    monthly_source_clock_identity_sha256: str
    monthly_fact_ledger_identity_sha256: str
    monthly_cutoff_utc: str
    declared_stock_codes_sha256: str
    declared_stock_count: int
    ma_states: tuple[MaState, ...] | None
    minimum_yoy_percent: Decimal | None
    condition_combine_mode: CombineMode
    unknown_policy: UnknownPolicy
    sort_clauses: tuple[DailyMarketTechnicalOfficialDispositionMaSortClauseV1, ...]
    page_index: int
    page_size: int
    recipe_identity_sha256: str

    @classmethod
    def from_exact_read(
        cls,
        exact_read: DailyMarketTechnicalOfficialDispositionRevenueExactReadV1,
    ) -> DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1:
        if type(exact_read) is not DailyMarketTechnicalOfficialDispositionRevenueExactReadV1:
            _fail("saved_recipe_exact_read_invalid")
        exact_read._validate_open()
        query = exact_read.query
        request = exact_read.page_request
        reference = exact_read.monthly_source_reference
        return cls._from_parts(
            f17_query=exact_read.f17_query,
            reference=reference,
            ma_states=query.ma_query.ma_states,
            minimum_yoy_percent=query.minimum_yoy_percent,
            condition_combine_mode=query.condition_combine_mode,
            unknown_policy=query.unknown_policy,
            sort_clauses=query.sort_clauses,
            page_index=request.page_index,
            page_size=request.page_size,
        )

    @classmethod
    def from_saved_query(
        cls,
        saved_query: DailyMarketTechnicalOfficialDispositionRevenueQueryV1 | str | bytes,
        monthly_source_reference: DailyMarketMonthlyRevenueSourceReferenceV2 | str | bytes,
        saved_page_request: DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1 | str | bytes,
    ) -> DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1:
        """把第一代 query-only 保存內容升為穩定 recipe request。"""

        query = _parse_saved_query(saved_query)
        reference = _parse_monthly_reference(monthly_source_reference)
        request = _parse_saved_request(saved_page_request, query)
        f17_query = query.ma_query.f17_query
        _preflight_cutoff_and_reference(f17_query, reference)
        _verify_saved_query_reference(query, reference)
        return cls._from_parts(
            f17_query=f17_query,
            reference=reference,
            ma_states=query.ma_query.ma_states,
            minimum_yoy_percent=query.minimum_yoy_percent,
            condition_combine_mode=query.condition_combine_mode,
            unknown_policy=query.unknown_policy,
            sort_clauses=query.sort_clauses,
            page_index=request.page_index,
            page_size=request.page_size,
        )

    @classmethod
    def _from_parts(
        cls,
        *,
        f17_query: DailyMarketTechnicalOfficialDispositionQueryV1,
        reference: DailyMarketMonthlyRevenueSourceReferenceV2,
        ma_states: Sequence[MaState] | None,
        minimum_yoy_percent: Decimal | None,
        condition_combine_mode: CombineMode,
        unknown_policy: UnknownPolicy,
        sort_clauses: Sequence[DailyMarketTechnicalOfficialDispositionMaSortClauseV1],
        page_index: int,
        page_size: int,
    ) -> DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1:
        ref_json = reference.to_json()
        state_tuple = None if ma_states is None else tuple(ma_states)
        clauses_tuple = tuple(sort_clauses)
        body: dict[str, object] = {
            "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_RECIPE_SCHEMA_V1,
            "f17_query_json": f17_query.to_json(),
            "monthly_source_reference_json": ref_json,
            "monthly_source_reference_identity_sha256": reference.identity_sha256,
            "monthly_source_content_identity_sha256": reference.source_content_identity_sha256,
            "monthly_source_clock_identity_sha256": reference.snapshot_reference.source_clock_identity_sha256,
            "monthly_fact_ledger_identity_sha256": reference.fact_ledger_identity_sha256,
            "monthly_cutoff_utc": _parse_cutoff(reference.decision_cutoff, "monthly_cutoff_invalid").isoformat(),
            "declared_stock_codes_sha256": _canonical_sha256(list(reference.declared_stock_codes)),
            "declared_stock_count": len(reference.declared_stock_codes),
            "ma_states": None if state_tuple is None else list(state_tuple),
            "minimum_yoy_percent": _recipe_decimal_text(minimum_yoy_percent),
            "condition_combine_mode": condition_combine_mode,
            "unknown_policy": unknown_policy,
            "sort_clauses": [item.to_dict() for item in clauses_tuple],
            "page_index": page_index,
            "page_size": page_size,
        }
        return cls.from_dict({**body, "recipe_identity_sha256": _canonical_sha256(body)})

    def with_conditions(
        self,
        *,
        ma_states: Sequence[MaState] | None,
        minimum_yoy_percent: Decimal | None,
        condition_combine_mode: CombineMode,
        unknown_policy: UnknownPolicy,
        sort_clauses: Sequence[DailyMarketTechnicalOfficialDispositionMaSortClauseV1],
        page_index: int | None = None,
        page_size: int | None = None,
    ) -> DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1:
        """建立新條件的 recipe；條件變動會改 recipe identity。"""

        if any(
            type(item) is not DailyMarketTechnicalOfficialDispositionMaSortClauseV1
            for item in sort_clauses
        ):
            _fail("saved_recipe_sort_invalid")
        body = _saved_recipe_body(self)
        body.update({
            "ma_states": None if ma_states is None else list(ma_states),
            "minimum_yoy_percent": _recipe_decimal_text(minimum_yoy_percent),
            "condition_combine_mode": condition_combine_mode,
            "unknown_policy": unknown_policy,
            "sort_clauses": [item.to_dict() for item in sort_clauses],
            "page_index": self.page_index if page_index is None else page_index,
            "page_size": self.page_size if page_size is None else page_size,
        })
        return type(self).from_dict({
            **body,
            "recipe_identity_sha256": _canonical_sha256(body),
        })

    def to_dict(self) -> dict[str, object]:
        body = _saved_recipe_body(self)
        _validate_saved_recipe(self)
        if _canonical_sha256(body) != self.recipe_identity_sha256:
            _fail("saved_recipe_identity_mismatch")
        return {**body, "recipe_identity_sha256": self.recipe_identity_sha256}

    def to_json(self) -> str:
        raw = _recipe_canonical_bytes(self.to_dict())
        if len(raw) > _MAX_RECIPE_BYTES:
            _fail("saved_recipe_json_byte_limit")
        return raw.decode("utf-8")

    @classmethod
    def from_dict(
        cls, value: object
    ) -> DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1:
        expected = {
            "schema_version", "f17_query_json", "monthly_source_reference_json",
            "monthly_source_reference_identity_sha256", "monthly_source_content_identity_sha256",
            "monthly_source_clock_identity_sha256", "monthly_fact_ledger_identity_sha256",
            "monthly_cutoff_utc", "declared_stock_codes_sha256", "declared_stock_count",
            "ma_states", "minimum_yoy_percent", "condition_combine_mode", "unknown_policy",
            "sort_clauses", "page_index", "page_size", "recipe_identity_sha256",
        }
        if not isinstance(value, dict) or set(value) != expected:
            _fail("saved_recipe_fields_invalid")
        if value.get("schema_version") != DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_RECIPE_SCHEMA_V1:
            _fail("saved_recipe_schema_unsupported")
        state_raw = value.get("ma_states")
        if state_raw is None:
            states = None
        elif type(state_raw) is list:
            if (
                not state_raw
                or any(type(item) is not str or item not in _RECIPE_MA_STATE_ORDER for item in state_raw)
                or len(set(state_raw)) != len(state_raw)
                or state_raw != [item for item in _RECIPE_MA_STATE_ORDER if item in state_raw]
            ):
                _fail("saved_recipe_ma_states_invalid")
            states = cast(tuple[MaState, ...], tuple(state_raw))
        else:
            _fail("saved_recipe_ma_states_invalid")
        minimum_raw = value.get("minimum_yoy_percent")
        if minimum_raw is None:
            minimum = None
        elif type(minimum_raw) is str and len(minimum_raw) <= 256:
            try:
                minimum = Decimal(minimum_raw)
            except InvalidOperation as exc:
                raise DailyMarketTechnicalOfficialDispositionRevenueSourceV1Error(
                    "saved_recipe_decimal_invalid"
                ) from exc
            if _recipe_decimal_text(minimum) != minimum_raw:
                _fail("saved_recipe_decimal_noncanonical")
        else:
            _fail("saved_recipe_decimal_invalid")
        raw_sort = value.get("sort_clauses")
        if type(raw_sort) is not list or not raw_sort:
            _fail("saved_recipe_sort_invalid")
        clauses = tuple(
            DailyMarketTechnicalOfficialDispositionMaSortClauseV1.from_dict(item)
            for item in raw_sort
        )
        recipe = cls(
            f17_query_json=_recipe_str(value.get("f17_query_json"), "saved_recipe_f17_query_invalid"),
            monthly_source_reference_json=_recipe_str(
                value.get("monthly_source_reference_json"), "saved_recipe_monthly_reference_invalid"
            ),
            monthly_source_reference_identity_sha256=_recipe_str(
                value.get("monthly_source_reference_identity_sha256"), "saved_recipe_pin_invalid"
            ),
            monthly_source_content_identity_sha256=_recipe_str(
                value.get("monthly_source_content_identity_sha256"), "saved_recipe_pin_invalid"
            ),
            monthly_source_clock_identity_sha256=_recipe_str(
                value.get("monthly_source_clock_identity_sha256"), "saved_recipe_pin_invalid"
            ),
            monthly_fact_ledger_identity_sha256=_recipe_str(
                value.get("monthly_fact_ledger_identity_sha256"), "saved_recipe_pin_invalid"
            ),
            monthly_cutoff_utc=_recipe_str(value.get("monthly_cutoff_utc"), "saved_recipe_cutoff_invalid"),
            declared_stock_codes_sha256=_recipe_str(
                value.get("declared_stock_codes_sha256"), "saved_recipe_pin_invalid"
            ),
            declared_stock_count=_recipe_int(value.get("declared_stock_count"), "saved_recipe_cohort_invalid"),
            ma_states=states,
            minimum_yoy_percent=minimum,
            condition_combine_mode=cast(CombineMode, value.get("condition_combine_mode")),
            unknown_policy=cast(UnknownPolicy, value.get("unknown_policy")),
            sort_clauses=clauses,
            page_index=_recipe_int(value.get("page_index"), "saved_recipe_page_invalid"),
            page_size=_recipe_int(value.get("page_size"), "saved_recipe_page_invalid"),
            recipe_identity_sha256=_recipe_str(
                value.get("recipe_identity_sha256"), "saved_recipe_identity_invalid"
            ),
        )
        _validate_saved_recipe(recipe)
        if _canonical_sha256(_saved_recipe_body(recipe)) != recipe.recipe_identity_sha256:
            _fail("saved_recipe_identity_mismatch")
        return recipe

    @classmethod
    def from_json(
        cls, raw: str | bytes
    ) -> DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1:
        if type(raw) not in {str, bytes}:
            _fail("saved_recipe_json_invalid")
        payload = _parse_recipe_json(cast(str | bytes, raw))
        recipe = cls.from_dict(payload)
        if recipe.to_json() != (raw.decode("utf-8") if isinstance(raw, bytes) else raw):
            _fail("saved_recipe_json_noncanonical")
        return recipe


def _recipe_str(value: object, code: str) -> str:
    if type(value) is not str or len(value.encode("utf-8")) > _MAX_RECIPE_BYTES:
        _fail(code)
    return cast(str, value)


def _recipe_int(value: object, code: str) -> int:
    if type(value) is not int:
        _fail(code)
    return cast(int, value)


def _saved_recipe_body(
    recipe: DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1,
) -> dict[str, object]:
    return {
        "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_RECIPE_SCHEMA_V1,
        "f17_query_json": recipe.f17_query_json,
        "monthly_source_reference_json": recipe.monthly_source_reference_json,
        "monthly_source_reference_identity_sha256": recipe.monthly_source_reference_identity_sha256,
        "monthly_source_content_identity_sha256": recipe.monthly_source_content_identity_sha256,
        "monthly_source_clock_identity_sha256": recipe.monthly_source_clock_identity_sha256,
        "monthly_fact_ledger_identity_sha256": recipe.monthly_fact_ledger_identity_sha256,
        "monthly_cutoff_utc": recipe.monthly_cutoff_utc,
        "declared_stock_codes_sha256": recipe.declared_stock_codes_sha256,
        "declared_stock_count": recipe.declared_stock_count,
        "ma_states": None if recipe.ma_states is None else list(recipe.ma_states),
        "minimum_yoy_percent": _recipe_decimal_text(recipe.minimum_yoy_percent),
        "condition_combine_mode": recipe.condition_combine_mode,
        "unknown_policy": recipe.unknown_policy,
        "sort_clauses": [item.to_dict() for item in recipe.sort_clauses],
        "page_index": recipe.page_index,
        "page_size": recipe.page_size,
    }


def _validate_saved_recipe(
    recipe: DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1,
) -> None:
    from app_module.daily_market_technical_official_disposition_query_v1 import (
        DailyMarketTechnicalOfficialDispositionQueryV1,
    )

    if type(recipe) is not DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1:
        _fail("saved_recipe_invalid")
    if (
        not recipe.f17_query_json
        or not recipe.monthly_source_reference_json
        or not all(
            len(pin) == 64 and all(char in "0123456789abcdef" for char in pin)
            for pin in (
                recipe.monthly_source_reference_identity_sha256,
                recipe.monthly_source_content_identity_sha256,
                recipe.monthly_source_clock_identity_sha256,
                recipe.monthly_fact_ledger_identity_sha256,
                recipe.declared_stock_codes_sha256,
                recipe.recipe_identity_sha256,
            )
        )
        or recipe.condition_combine_mode not in {"AND", "OR"}
        or recipe.unknown_policy not in {"include", "exclude", "only"}
        or type(recipe.declared_stock_count) is not int
        or recipe.declared_stock_count <= 0
        or type(recipe.page_index) is not int
        or not 0 <= recipe.page_index <= 1_000_000
        or type(recipe.page_size) is not int
        or not 1 <= recipe.page_size <= 256
        or not recipe.sort_clauses
        or len(recipe.sort_clauses) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_MAX_SORT_CLAUSES_V1
        or any(type(item) is not DailyMarketTechnicalOfficialDispositionMaSortClauseV1 for item in recipe.sort_clauses)
        or len({item.field for item in recipe.sort_clauses}) != len(recipe.sort_clauses)
        or (
            recipe.ma_states is not None
            and (
                not recipe.ma_states
                or tuple(item for item in _RECIPE_MA_STATE_ORDER if item in recipe.ma_states)
                != recipe.ma_states
            )
        )
    ):
        _fail("saved_recipe_fields_invalid")
    f17_query, reference = _parse_source_inputs(
        recipe.f17_query_json,
        recipe.monthly_source_reference_json,
    )
    if type(f17_query) is not DailyMarketTechnicalOfficialDispositionQueryV1:
        _fail("saved_recipe_f17_query_invalid")
    _preflight_cutoff_and_reference(f17_query, reference)
    if (
        reference.identity_sha256 != recipe.monthly_source_reference_identity_sha256
        or reference.source_content_identity_sha256 != recipe.monthly_source_content_identity_sha256
        or reference.snapshot_reference.source_clock_identity_sha256
        != recipe.monthly_source_clock_identity_sha256
        or reference.fact_ledger_identity_sha256 != recipe.monthly_fact_ledger_identity_sha256
        or _parse_cutoff(reference.decision_cutoff, "monthly_cutoff_invalid").isoformat()
        != recipe.monthly_cutoff_utc
        or _canonical_sha256(list(reference.declared_stock_codes))
        != recipe.declared_stock_codes_sha256
        or len(reference.declared_stock_codes) != recipe.declared_stock_count
    ):
        _fail("saved_recipe_monthly_reference_mismatch")
    if recipe.minimum_yoy_percent is not None:
        _recipe_decimal_text(recipe.minimum_yoy_percent)
    active_count = (
        int(bool(f17_query.technical_query.rule_state_filters))
        + int(recipe.ma_states is not None)
        + int(recipe.minimum_yoy_percent is not None)
    )
    if (
        (active_count < 2 and recipe.condition_combine_mode != "AND")
        or (active_count == 0 and recipe.unknown_policy != "include")
        or (recipe.unknown_policy == "only" and active_count == 0)
    ):
        _fail("saved_recipe_policy_noncanonical")


def open_daily_market_technical_official_disposition_revenue_source_v1(
    f17_query: DailyMarketTechnicalOfficialDispositionQueryV1 | str | bytes,
    monthly_source_reference: DailyMarketMonthlyRevenueSourceReferenceV2 | str | bytes,
    *,
    operation_root: Path | str,
    ma_states: Sequence[MaState] | None = None,
    minimum_yoy_percent: Decimal | None = None,
    condition_combine_mode: CombineMode = "AND",
    unknown_policy: UnknownPolicy = "include",
    sort_clauses: Sequence[DailyMarketTechnicalOfficialDispositionMaSortClauseV1] = (),
    page_index: int = 0,
    page_size: int = 50,
    cancel_callback: Callable[[], object] | None = None,
) -> DailyMarketTechnicalOfficialDispositionRevenueExactReadV1:
    """Exact-open 兩固定來源、重建完整 index，再執行全母體查詢與頁面。"""

    _poll_cancel(cancel_callback)
    f17, reference = _parse_source_inputs(f17_query, monthly_source_reference)
    _preflight_cutoff_and_reference(f17, reference)
    root = _new_operation_root(
        operation_root,
        f17_query=f17,
        source_reference=reference,
    )
    return _open_and_publish(
        f17,
        reference,
        root=root,
        recipe=(ma_states, minimum_yoy_percent, condition_combine_mode, unknown_policy, sort_clauses),
        saved_query=None,
        saved_request=None,
        cancel_callback=cancel_callback,
        page_index=page_index,
        page_size=page_size,
    )


def open_daily_market_technical_official_disposition_revenue_bundle_source_v1(
    *,
    bundle_output_root: str | Path,
    bundle_identity_sha256: str,
    expected_manifest_sha256: str,
    row_scope_filter: Sequence[RowScope],
    monthly_source_reference: DailyMarketMonthlyRevenueSourceReferenceV2 | str | bytes,
    operation_root: Path | str,
    rule_state_filters: Sequence[DailyMarketTechnicalRuleStateFilterV4] = (),
    combine_mode: Literal["AND", "OR"] = "AND",
    market_assignment_states: Sequence[str] = (),
    official_disposal_states: Sequence[str] = (),
    outer_stock_filter_mode: Literal["all", "explicit_codes"] = "all",
    outer_stock_codes: Sequence[str] = (),
    f17_sort_clauses: Sequence[DailyMarketTechnicalOfficialDispositionSortClauseV1] = (),
    ma_states: Sequence[MaState] | None = None,
    minimum_yoy_percent: Decimal | None = None,
    condition_combine_mode: CombineMode = "AND",
    unknown_policy: UnknownPolicy = "include",
    sort_clauses: Sequence[DailyMarketTechnicalOfficialDispositionMaSortClauseV1] = (),
    page_index: int = 0,
    page_size: int = 50,
    cancel_callback: Callable[[], object] | None = None,
) -> DailyMarketTechnicalOfficialDispositionRevenueExactReadV1:
    """以明示 F17 pins 單次核驗，再沿同一 session 建立 YoY 複合查詢。"""

    _poll_cancel(cancel_callback)
    reference = _parse_monthly_reference(monthly_source_reference)
    from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
        open_daily_market_technical_official_disposition_bundle_session_v1,
    )

    f17_session = open_daily_market_technical_official_disposition_bundle_session_v1(
        bundle_output_root=bundle_output_root,
        bundle_identity_sha256=bundle_identity_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        row_scope_filter=row_scope_filter,
        rule_state_filters=rule_state_filters,
        combine_mode=combine_mode,
        market_assignment_states=market_assignment_states,
        official_disposal_states=official_disposal_states,
        outer_stock_filter_mode=outer_stock_filter_mode,
        outer_stock_codes=outer_stock_codes,
        sort_clauses=f17_sort_clauses,
        cancel_callback=cancel_callback,
    )
    f17_query = f17_session.query
    _preflight_cutoff_and_reference(f17_query, reference)
    root = _new_operation_root(
        operation_root,
        f17_query=f17_query,
        source_reference=reference,
    )
    return _open_and_publish(
        f17_query,
        reference,
        root=root,
        recipe=(ma_states, minimum_yoy_percent, condition_combine_mode, unknown_policy, sort_clauses),
        saved_query=None,
        saved_request=None,
        cancel_callback=cancel_callback,
        page_index=page_index,
        page_size=page_size,
        preopened_f17_session=f17_session,
    )


def reopen_daily_market_technical_official_disposition_revenue_source_v1(
    saved_query: DailyMarketTechnicalOfficialDispositionRevenueQueryV1 | str | bytes,
    monthly_source_reference: DailyMarketMonthlyRevenueSourceReferenceV2 | str | bytes,
    *,
    operation_root: Path | str,
    saved_page_request: DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1 | str | bytes,
    cancel_callback: Callable[[], object] | None = None,
) -> DailyMarketTechnicalOfficialDispositionRevenueExactReadV1:
    """從明示 F17 query 與月營收 V2 archive 重建新 operation，保留原 recipe。"""

    _poll_cancel(cancel_callback)
    query = _parse_saved_query(saved_query)
    request = _parse_saved_request(saved_page_request, query)
    ma_query = query.ma_query
    f17 = ma_query.f17_query
    reference = _parse_monthly_reference(monthly_source_reference)
    _preflight_cutoff_and_reference(f17, reference)
    _verify_saved_query_reference(query, reference)
    root = _new_operation_root(
        operation_root,
        f17_query=f17,
        source_reference=reference,
    )
    return _open_and_publish(
        f17,
        reference,
        root=root,
        recipe=(
            ma_query.ma_states,
            query.minimum_yoy_percent,
            query.condition_combine_mode,
            query.unknown_policy,
            query.sort_clauses,
        ),
        saved_query=query,
        saved_request=request,
        cancel_callback=cancel_callback,
        page_index=request.page_index,
        page_size=request.page_size,
    )


def reopen_daily_market_technical_official_disposition_revenue_from_recipe_v1(
    saved_recipe: DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1 | str | bytes,
    *,
    operation_root: Path | str,
    cancel_callback: Callable[[], object] | None = None,
) -> DailyMarketTechnicalOfficialDispositionRevenueExactReadV1:
    """從穩定 recipe 重新 exact-open；每次都重核封存來源並發行新 operation。"""

    _poll_cancel(cancel_callback)
    recipe = _parse_saved_recipe(saved_recipe)
    f17_query, reference = _parse_source_inputs(
        recipe.f17_query_json,
        recipe.monthly_source_reference_json,
    )
    _preflight_cutoff_and_reference(f17_query, reference)
    _validate_saved_recipe(recipe)
    root = _new_operation_root(
        operation_root,
        f17_query=f17_query,
        source_reference=reference,
    )
    exact_read = _open_and_publish(
        f17_query,
        reference,
        root=root,
        recipe=(
            recipe.ma_states,
            recipe.minimum_yoy_percent,
            recipe.condition_combine_mode,
            recipe.unknown_policy,
            recipe.sort_clauses,
        ),
        saved_query=None,
        saved_request=None,
        saved_recipe=recipe,
        cancel_callback=cancel_callback,
        page_index=recipe.page_index,
        page_size=recipe.page_size,
    )
    try:
        if exact_read.saved_recipe.to_json() != recipe.to_json():
            _fail("saved_recipe_reissued_query_mismatch")
        return exact_read
    except BaseException:
        exact_read.close()
        raise


def _parse_source_inputs(
    f17_query: DailyMarketTechnicalOfficialDispositionQueryV1 | str | bytes,
    monthly_source_reference: DailyMarketMonthlyRevenueSourceReferenceV2 | str | bytes,
) -> tuple[DailyMarketTechnicalOfficialDispositionQueryV1, DailyMarketMonthlyRevenueSourceReferenceV2]:
    from app_module.daily_market_technical_official_disposition_query_v1 import (
        DailyMarketTechnicalOfficialDispositionQueryV1,
    )

    if type(f17_query) is DailyMarketTechnicalOfficialDispositionQueryV1:
        parsed_f17 = cast(DailyMarketTechnicalOfficialDispositionQueryV1, f17_query)
    elif type(f17_query) in {str, bytes}:
        parsed_f17 = DailyMarketTechnicalOfficialDispositionQueryV1.from_json(
            cast(str | bytes, f17_query)
        )
    else:
        _fail("f17_query_invalid")
    parsed_f17.to_json()
    return parsed_f17, _parse_monthly_reference(monthly_source_reference)


def _parse_monthly_reference(
    source_reference: DailyMarketMonthlyRevenueSourceReferenceV2 | str | bytes,
) -> DailyMarketMonthlyRevenueSourceReferenceV2:
    if type(source_reference) is DailyMarketMonthlyRevenueSourceReferenceV2:
        reference = cast(DailyMarketMonthlyRevenueSourceReferenceV2, source_reference)
    elif type(source_reference) in {str, bytes}:
        reference = DailyMarketMonthlyRevenueSourceReferenceV2.from_json(
            cast(str | bytes, source_reference)
        )
    else:
        _fail("monthly_source_reference_invalid")
    reference.to_json()
    return reference


def _parse_saved_query(
    saved_query: DailyMarketTechnicalOfficialDispositionRevenueQueryV1 | str | bytes,
) -> DailyMarketTechnicalOfficialDispositionRevenueQueryV1:
    if type(saved_query) is DailyMarketTechnicalOfficialDispositionRevenueQueryV1:
        query = cast(DailyMarketTechnicalOfficialDispositionRevenueQueryV1, saved_query)
    elif type(saved_query) in {str, bytes}:
        query = DailyMarketTechnicalOfficialDispositionRevenueQueryV1.from_json(
            cast(str | bytes, saved_query)
        )
    else:
        _fail("saved_query_invalid")
    query.to_json()
    return query


def _parse_saved_request(
    saved_request: DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1 | str | bytes,
    query: DailyMarketTechnicalOfficialDispositionRevenueQueryV1,
) -> DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1:
    if type(saved_request) is DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1:
        request = cast(DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1, saved_request)
    elif type(saved_request) in {str, bytes}:
        request = DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1.from_json(
            cast(str | bytes, saved_request)
        )
    else:
        _fail("saved_page_request_invalid")
    request.to_json()
    if request.query.query_identity_sha256 != query.query_identity_sha256:
        _fail("saved_page_request_query_mismatch")
    return request


def _parse_saved_recipe(
    saved_recipe: DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1 | str | bytes,
) -> DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1:
    if type(saved_recipe) is DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1:
        recipe = cast(DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1, saved_recipe)
        recipe.to_json()
    elif type(saved_recipe) in {str, bytes}:
        recipe = DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1.from_json(
            cast(str | bytes, saved_recipe)
        )
    else:
        _fail("saved_recipe_invalid")
    return recipe


def _preflight_cutoff_and_reference(
    f17_query: DailyMarketTechnicalOfficialDispositionQueryV1,
    reference: DailyMarketMonthlyRevenueSourceReferenceV2,
) -> None:
    if (
        reference.source_scope != "current_observed_only"
        or reference.availability_status != "unknown"
        or reference.historical_pit_eligible is not False
        or reference.formal_pit_eligible is not False
        or reference.method_id != "current-monthly-revenue-yoy.v1"
    ):
        _fail("monthly_source_scope_invalid")
    f17_cutoff = f17_query.decision_cutoff
    if type(f17_cutoff) is not datetime or f17_cutoff.tzinfo is None or f17_cutoff.utcoffset() is None:
        _fail("f17_cutoff_not_aware")
    monthly_cutoff = _parse_cutoff(reference.decision_cutoff, "monthly_cutoff_invalid")
    if f17_cutoff.astimezone(timezone.utc) != monthly_cutoff:
        _fail("source_cutoff_mismatch")
    if (
        not reference.declared_stock_codes
        or reference.declared_stock_codes
        != reference.snapshot_reference.declared_stock_codes
        or reference.declared_stock_codes
        != reference.raw_archive_reference.declared_stock_codes
        or len(reference.fact_identity_by_stock) != len(reference.declared_stock_codes)
    ):
        _fail("monthly_source_cohort_invalid")


def _open_and_publish(
    f17_query: DailyMarketTechnicalOfficialDispositionQueryV1,
    source_reference: DailyMarketMonthlyRevenueSourceReferenceV2,
    *,
    root: Path,
    recipe: tuple[
        Sequence[MaState] | None,
        Decimal | None,
        CombineMode,
        UnknownPolicy,
        Sequence[DailyMarketTechnicalOfficialDispositionMaSortClauseV1],
    ],
    saved_query: DailyMarketTechnicalOfficialDispositionRevenueQueryV1 | None,
    saved_request: DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1 | None,
    saved_recipe: DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1 | None = None,
    cancel_callback: Callable[[], object] | None,
    page_index: int,
    page_size: int,
    preopened_f17_session: DailyMarketTechnicalOfficialDispositionReadSessionV1 | None = None,
) -> DailyMarketTechnicalOfficialDispositionRevenueExactReadV1:
    from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
        DailyMarketTechnicalOfficialDispositionQueryReaderV1Error,
        DailyMarketTechnicalOfficialDispositionReadSessionV1 as _ReadSessionV1,
        open_daily_market_technical_official_disposition_read_session_v1,
    )

    _poll_cancel(cancel_callback)
    f17_session: DailyMarketTechnicalOfficialDispositionReadSessionV1 | None = None
    index_session: DailyMarketMonthlyRevenueYoyIndexSessionV1 | None = None
    try:
        if preopened_f17_session is None:
            f17_session = open_daily_market_technical_official_disposition_read_session_v1(
                f17_query,
                cancel_callback=cancel_callback,
            )
        else:
            if type(preopened_f17_session) is not _ReadSessionV1:
                _fail("f17_exact_session_type_invalid")
            f17_session = preopened_f17_session
        if f17_session.query.to_json() != f17_query.to_json():
            _fail("f17_exact_query_changed")
        _poll_cancel(cancel_callback)
        declared_codes = f17_session.verified_declared_stock_codes(
            cancel_callback=cancel_callback,
        )
        if declared_codes != source_reference.declared_stock_codes:
            _fail("source_cohort_mismatch")

        guard_root = root / "neutral_provider_guard"
        provider = RecommendationCurrentFundamentalProvider(
            db_file=guard_root / "never-open-this.sqlite",
            output_root=guard_root / "output",
            monthly_source_root=guard_root / "monthly-source",
            calendar_cache_path=guard_root / "calendar-cache",
            temporary_closure_path=guard_root / "temporary-closures",
        )
        index_session = DailyMarketMonthlyRevenueYoyIndexSessionV1.open_exact_archived(
            provider,
            snapshot_root=root / "monthly_snapshot_operations",
            source_reference=source_reference,
            cancel_callback=cancel_callback,
        )
        if (
            index_session.declared_stock_codes != declared_codes
            or index_session.decision_cutoff.astimezone(timezone.utc)
            != f17_query.decision_cutoff.astimezone(timezone.utc)
        ):
            _fail("opened_monthly_scope_mismatch")
        for offset in range(0, len(declared_codes), MAX_CODES_PER_BATCH):
            _poll_cancel(cancel_callback)
            index_session.load_batch(
                declared_codes[offset:offset + MAX_CODES_PER_BATCH],
                cancel_callback=cancel_callback,
            )
        monthly_index = index_session.finish(cancel_callback=cancel_callback)
        if not index_session.closed:
            _fail("monthly_reader_connection_not_closed_after_finish")
        if not monthly_index.is_reader_issued:
            _fail("monthly_index_not_reader_issued")
        if monthly_index.declared_stock_codes != declared_codes:
            _fail("monthly_index_declared_cohort_mismatch")
        if (
            monthly_index.source_clock.source_content_identity_sha256
            != source_reference.source_content_identity_sha256
        ):
            _fail("monthly_index_source_content_mismatch")
        if (
            monthly_index.source_clock.decision_cutoff.astimezone(timezone.utc)
            != f17_query.decision_cutoff.astimezone(timezone.utc)
        ):
            _fail("monthly_index_source_cutoff_mismatch")
        if (
            tuple(
                (entry.stock_code, entry.source_fact.identity_sha256)
                for entry in monthly_index.entries
            ) != source_reference.fact_identity_by_stock
        ):
            _fail("monthly_index_fact_ledger_mismatch")
        if index_session.source_reference.to_json() != source_reference.to_json():
            _fail("monthly_index_source_reference_mismatch")
        if saved_query is not None:
            _verify_saved_query_source(saved_query, source_reference, index_session)

        _poll_cancel(cancel_callback)
        combined_session = f17_session.with_monthly_revenue_yoy_index(
            index_session,
            cancel_callback=cancel_callback,
        )
        ma_states, minimum_yoy, combine_mode, unknown_policy, sort_clauses = recipe
        query = combined_session.create_revenue_query_v1(
            ma_states=ma_states,
            minimum_yoy_percent=minimum_yoy,
            condition_combine_mode=combine_mode,
            unknown_policy=unknown_policy,
            sort_clauses=sort_clauses,
        )
        if saved_query is not None:
            _verify_recipe_preserved(saved_query, query, f17_query)
        if saved_recipe is not None:
            _verify_saved_recipe_query(saved_recipe, query, f17_query)
        result = combined_session.execute_revenue_query_v1(
            query,
            cancel_callback=cancel_callback,
        )
        if result.query.query_identity_sha256 != query.query_identity_sha256:
            _fail("revenue_result_query_mismatch")
        if saved_request is None:
            request = DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1.create(
                query,
                page_index=page_index,
                page_size=page_size,
            )
        else:
            request = DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1.create(
                query,
                page_index=saved_request.page_index,
                page_size=saved_request.page_size,
            )
        page = result.read_page_request(request, cancel_callback=cancel_callback)
        _poll_cancel(cancel_callback)
        if (
            page.operation_identity_sha256 != result.operation_identity_sha256
            or page.query.query_identity_sha256 != query.query_identity_sha256
            or page.request_identity_sha256 != request.request_identity_sha256
        ):
            _fail("initial_page_result_mismatch")

        source_pair_identity = _canonical_sha256({
            "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_SOURCE_SCHEMA_V1,
            "f17_query_identity_sha256": f17_query.query_identity_sha256,
            "bundle_identity_sha256": f17_query.bundle_identity_sha256,
            "bundle_manifest_sha256": f17_query.expected_manifest_sha256,
            "monthly_source_reference_identity_sha256": source_reference.identity_sha256,
            "monthly_source_clock_identity_sha256": (
                source_reference.snapshot_reference.source_clock_identity_sha256
            ),
            "monthly_operation_clock_identity_sha256": monthly_index.source_clock_identity_sha256,
            "monthly_fact_ledger_identity_sha256": source_reference.fact_ledger_identity_sha256,
            "monthly_read_session_identity_sha256": index_session.read_session_identity_sha256,
            "monthly_index_identity_sha256": monthly_index.index_identity_sha256,
            "revenue_query_identity_sha256": query.query_identity_sha256,
            "operation_identity_sha256": result.operation_identity_sha256,
            "initial_page_identity_sha256": page.page_identity_sha256,
        })
        state = _ExactReadStateV1(
            f17_session=f17_session,
            monthly_index_session=index_session,
            combined_session=combined_session,
            result=result,
            request=request,
            page=page,
        )
        _poll_cancel(cancel_callback)
        return DailyMarketTechnicalOfficialDispositionRevenueExactReadV1(
            f17_query=f17_query,
            monthly_source_reference=source_reference,
            source_pair_identity_sha256=source_pair_identity,
            state=state,
            issuer=_SOURCE_ISSUER,
        )
    except BaseException as exc:
        cleanup_errors: list[BaseException] = []
        if index_session is not None:
            try:
                index_session.close()
                if not index_session.closed:
                    _fail("monthly_reader_connection_not_closed_during_cleanup")
            except BaseException as cleanup_exc:
                cleanup_errors.append(cleanup_exc)
        # F17 reader持有 immutable in-memory source state，沒有長駐連線可 close。
        f17_session = None
        if cleanup_errors:
            raise DailyMarketTechnicalOfficialDispositionRevenueSourceV1Error(
                "operation_failed_and_monthly_cleanup_failed"
            ) from BaseExceptionGroup(
                "primary exact-source operation failure and monthly cleanup failure",
                [exc, *cleanup_errors],
            )
        if isinstance(exc, DailyMarketMonthlyRevenueYoyIndexCancelled):
            raise DailyMarketTechnicalOfficialDispositionRevenueSourceV1Cancelled(
                "monthly_source_cancelled"
            ) from exc
        if isinstance(exc, DailyMarketTechnicalOfficialDispositionQueryReaderV1Error):
            code = str(getattr(exc, "code", ""))
            if "cancelled" in code:
                raise DailyMarketTechnicalOfficialDispositionRevenueSourceV1Cancelled(
                    "f17_source_cancelled"
                ) from exc
        raise


def _verify_saved_query_source(
    saved_query: DailyMarketTechnicalOfficialDispositionRevenueQueryV1,
    source_reference: DailyMarketMonthlyRevenueSourceReferenceV2,
    index_session: DailyMarketMonthlyRevenueYoyIndexSessionV1,
) -> None:
    index = index_session.index
    if (
        saved_query.monthly_yoy_source_clock_identity_sha256
        != source_reference.snapshot_reference.source_clock_identity_sha256
        or saved_query.monthly_yoy_cutoff
        != index.decision_cutoff.astimezone(timezone.utc).isoformat()
        or saved_query.monthly_yoy_method_id
        != index.to_dict()["method_id"]
        or saved_query.monthly_yoy_method_version
        != index.to_dict()["method_version"]
        or source_reference.source_content_identity_sha256
        != index.source_clock.source_content_identity_sha256
    ):
        _fail("saved_query_monthly_source_mismatch")


def _verify_saved_query_reference(
    saved_query: DailyMarketTechnicalOfficialDispositionRevenueQueryV1,
    source_reference: DailyMarketMonthlyRevenueSourceReferenceV2,
) -> None:
    """在建立 operation 前，先比對收藏 query 綁定的原封存 source pin。"""

    if (
        saved_query.monthly_yoy_source_clock_identity_sha256
        != source_reference.snapshot_reference.source_clock_identity_sha256
        or saved_query.monthly_yoy_cutoff
        != datetime.fromisoformat(
            source_reference.snapshot_reference.decision_cutoff
        ).astimezone(timezone.utc).isoformat()
        or saved_query.monthly_yoy_method_id != SELECTION_REVENUE_YOY_METHOD_ID
        or saved_query.monthly_yoy_method_version
        != SELECTION_REVENUE_YOY_METHOD_VERSION
    ):
        _fail("saved_query_monthly_source_reference_mismatch")


def _verify_recipe_preserved(
    saved_query: DailyMarketTechnicalOfficialDispositionRevenueQueryV1,
    reopened_query: DailyMarketTechnicalOfficialDispositionRevenueQueryV1,
    f17_query: DailyMarketTechnicalOfficialDispositionQueryV1,
) -> None:
    old_ma = saved_query.ma_query
    new_ma = reopened_query.ma_query
    if (
        old_ma.f17_query.to_json() != f17_query.to_json()
        or new_ma.f17_query.to_json() != f17_query.to_json()
        or old_ma.ma_states != new_ma.ma_states
        or old_ma.condition_combine_mode != new_ma.condition_combine_mode
        or old_ma.unknown_policy != new_ma.unknown_policy
        or old_ma.sort_clauses != new_ma.sort_clauses
        or saved_query.minimum_yoy_percent != reopened_query.minimum_yoy_percent
        or saved_query.condition_combine_mode != reopened_query.condition_combine_mode
        or saved_query.unknown_policy != reopened_query.unknown_policy
        or saved_query.sort_clauses != reopened_query.sort_clauses
    ):
        _fail("saved_query_recipe_changed")


def _verify_saved_recipe_query(
    recipe: DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1,
    reopened_query: DailyMarketTechnicalOfficialDispositionRevenueQueryV1,
    f17_query: DailyMarketTechnicalOfficialDispositionQueryV1,
) -> None:
    """確認 exact reader 依穩定條件重新發行，允許 operation identity 更新。"""

    if (
        f17_query.to_json() != recipe.f17_query_json
        or reopened_query.ma_query.f17_query.to_json() != recipe.f17_query_json
        or reopened_query.ma_query.ma_states != recipe.ma_states
        or reopened_query.minimum_yoy_percent != recipe.minimum_yoy_percent
        or reopened_query.condition_combine_mode != recipe.condition_combine_mode
        or reopened_query.unknown_policy != recipe.unknown_policy
        or reopened_query.sort_clauses != recipe.sort_clauses
        or reopened_query.monthly_yoy_cutoff != recipe.monthly_cutoff_utc
        or reopened_query.monthly_yoy_method_id != SELECTION_REVENUE_YOY_METHOD_ID
        or reopened_query.monthly_yoy_method_version != SELECTION_REVENUE_YOY_METHOD_VERSION
    ):
        _fail("saved_recipe_reissued_query_mismatch")
