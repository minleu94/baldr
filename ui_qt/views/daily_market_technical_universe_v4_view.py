"""固定 full-N v4 技術研究來源的有界歷史瀏覽與全域查詢。"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
import json
from pathlib import Path
import re
from typing import Any, cast

from PySide6.QtCore import QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app_module.daily_market_technical_parent_v4_query import (
    DailyMarketTechnicalParentV4Row,
    DailyMarketTechnicalRuleStateFilterV4,
    RuleState,
)
from app_module.daily_market_technical_universe_v4_catalog import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_CATALOG_DEFAULT_LIMIT,
    DailyMarketTechnicalUniverseV4Catalog,
    DailyMarketTechnicalUniverseV4CatalogEntry,
    DailyMarketTechnicalUniverseV4CatalogPage,
)
from app_module.daily_market_technical_universe_v4_bookmark import (
    DailyMarketTechnicalUniverseV4Bookmark,
    DailyMarketTechnicalUniverseV4BookmarkError,
    DailyMarketTechnicalUniverseV4BookmarkState,
    create_daily_market_technical_universe_v4_bookmark_fresh,
)
from app_module.daily_market_technical_universe_v4_comparison import (
    DailyMarketTechnicalUniverseV4Comparison,
    DailyMarketTechnicalUniverseV4ComparisonError,
    read_daily_market_technical_universe_v4_comparison,
)
from app_module.daily_market_technical_universe_v4_producer import (
    DailyMarketTechnicalUniverseV4ProductionRequest,
    DailyMarketTechnicalUniverseV4ProductionResult,
    produce_daily_market_technical_universe_v4,
)
from app_module.daily_market_technical_official_disposition_bundle_v1 import (
    DailyMarketTechnicalOfficialDispositionBundleReferenceV1,
)
from app_module.daily_market_technical_universe_v4_query import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_PAGE_SIZE,
    DailyMarketTechnicalUniverseV4Page,
    DailyMarketTechnicalUniverseV4Query,
    DailyMarketTechnicalUniverseV4ReadSelection,
    DailyMarketTechnicalUniverseV4ReadSelectionPage,
    DailyMarketTechnicalUniverseV4ReadSession,
    open_daily_market_technical_universe_v4_read_session,
)
from app_module.daily_market_technical_universe_v4_store import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS,
)
from app_module.daily_market_technical_universe_v4_stock import (
    DailyMarketTechnicalUniverseV4Stock,
    read_daily_market_technical_universe_v4_stock_from_selection,
)
from ui_qt.workers.task_worker import TaskWorker
from ui_qt.models.saved_research_page_table_model import (
    SavedResearchPageTableModel,
    SavedResearchTableRow,
)
from ui_qt.widgets.daily_market_technical_v4_production_setup import (
    DailyMarketTechnicalV4DeferredProductionSetup,
)


_STATE_LABELS: dict[str, str] = {
    "match": "符合",
    "no_match": "不符合",
    "unknown": "未知",
}
_STATE_VALUES: tuple[RuleState, ...] = ("match", "no_match", "unknown")
_NO_STATE_FILTER = "all"
_RULE_STATE_FILTER_OPTIONS: tuple[
    tuple[str, str], ...
] = (
    ("不限制", _NO_STATE_FILTER),
    ("符合", "match"),
    ("不符合", "no_match"),
    ("符合／不符合", "match|no_match"),
    ("未知", "unknown"),
    ("符合／未知", "match|unknown"),
    ("不符合／未知", "no_match|unknown"),
    ("全部狀態", "match|no_match|unknown"),
)
_RULE_STATE_FILTER_ID_TO_STATES: dict[str, tuple[RuleState, ...] | None] = {
    _NO_STATE_FILTER: None,
    "match": ("match",),
    "no_match": ("no_match",),
    "match|no_match": ("match", "no_match"),
    "unknown": ("unknown",),
    "match|unknown": ("match", "unknown"),
    "no_match|unknown": ("no_match", "unknown"),
    "match|no_match|unknown": ("match", "no_match", "unknown"),
}
_RULE_STATE_FILTER_STATES_TO_ID: dict[tuple[RuleState, ...], str] = {
    states: filter_id
    for filter_id, states in _RULE_STATE_FILTER_ID_TO_STATES.items()
    if states is not None
}
_STOCK_CODE_RE = re.compile(r"^[A-Z0-9]{1,16}$")
_MAX_STOCK_FILTER_TEXT_LENGTH = (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS * 16
    + (DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS - 1) * 2
)
_RULE_LABELS: dict[str, str] = {
    "ma5_20_golden_cross": "MA5／MA20 金叉",
    "kd_golden_cross": "K／D 金叉",
    "macd_golden_cross": "MACD 金叉",
    "volume_ratio_20_including_current": "量能比 20（含當日）",
    "volume_ratio_5_including_current": "量能比 5（含當日）",
}
_BASE_SORT_LABELS: dict[str, str] = {
    "stock_code": "股票代碼",
    "decision_date": "決策日期",
    "latest_feature_date": "最新特徵日期",
    "raw_row_count": "原始資料列數",
}
_RULE_SORT_LABELS: dict[str, str] = {
    "ratio": "比率",
    "numerator": "分子",
    "denominator": "分母",
}


@dataclass(frozen=True, slots=True)
class _QueryReadResult:
    query: DailyMarketTechnicalUniverseV4Query
    read_session: DailyMarketTechnicalUniverseV4ReadSession
    selection_query: DailyMarketTechnicalUniverseV4Query
    selection: DailyMarketTechnicalUniverseV4ReadSelection
    selection_page: DailyMarketTechnicalUniverseV4ReadSelectionPage
    source_clock: dict[str, object] | None = None

    @property
    def page(self) -> DailyMarketTechnicalUniverseV4Page | None:
        return self.selection_page.page


@dataclass(frozen=True, slots=True)
class _ProductionTaskOutcome:
    result: DailyMarketTechnicalUniverseV4ProductionResult | None
    # 背景工作器看到明確的布林取消欄位時，會保留產製器回報的取消結果。
    cancelled: bool
    official_bundle: DailyMarketTechnicalOfficialDispositionBundleReferenceV1 | None = None
    official_error: str | None = None


@dataclass(frozen=True, slots=True)
class _ComparisonBasketItem:
    query: DailyMarketTechnicalUniverseV4Query
    row: DailyMarketTechnicalParentV4Row


@dataclass(frozen=True, slots=True)
class _ComparisonTaskOutcome:
    comparison: DailyMarketTechnicalUniverseV4Comparison | None
    cancelled: bool


@dataclass(frozen=True, slots=True)
class _OriginRestoreResult:
    page: DailyMarketTechnicalUniverseV4Page
    stock_code: str
    read_session: DailyMarketTechnicalUniverseV4ReadSession
    selection_query: DailyMarketTechnicalUniverseV4Query
    selection: DailyMarketTechnicalUniverseV4ReadSelection


@dataclass(frozen=True, slots=True)
class _QueuedOperation:
    name: str
    operation: Callable[..., object]
    apply: Callable[[object], None]
    kind: str


ProductionRequestFactory = Callable[
    [DailyMarketTechnicalUniverseV4CatalogEntry | None],
    DailyMarketTechnicalUniverseV4ProductionRequest | DailyMarketTechnicalV4DeferredProductionSetup,
]


def _cancelled(cancel_callback: Callable[[], bool] | None) -> bool:
    return cancel_callback is not None and cancel_callback()


def _read_catalog_page(
    output_root: Path,
    cursor: str | None,
    *,
    cancel_callback: Callable[[], bool] | None = None,
) -> DailyMarketTechnicalUniverseV4CatalogPage:
    if _cancelled(cancel_callback):
        raise ValueError("technical_universe_v4_catalog_cancelled")
    result = DailyMarketTechnicalUniverseV4Catalog(output_root).list_page(
        limit=DAILY_MARKET_TECHNICAL_UNIVERSE_V4_CATALOG_DEFAULT_LIMIT,
        cursor=cursor,
    )
    # 來源清冊掃描目前沒有中途取消回呼。背景工作器會丟棄取消後
    # 才回來的結果；這裡再檢查一次，避免把晚到結果當成目前結果。
    if _cancelled(cancel_callback):
        raise ValueError("technical_universe_v4_catalog_cancelled")
    return result


def _read_entry_page(
    output_root: Path,
    entry: DailyMarketTechnicalUniverseV4CatalogEntry,
    *,
    cancel_callback: Callable[[], bool] | None = None,
) -> _QueryReadResult:
    if not entry.is_selectable:
        raise ValueError("technical_universe_v4_catalog_entry_not_selectable")
    if _cancelled(cancel_callback):
        raise ValueError("technical_universe_v4_query_cancelled")

    session = open_daily_market_technical_universe_v4_read_session(
        store_output_root=output_root,
        generation_identity_sha256=cast(str, entry.generation_identity_sha256),
        plan_identity_sha256=cast(str, entry.plan_identity_sha256),
        plan_sha256=cast(str, entry.plan_bytes_sha256),
        receipt_identity_sha256=cast(str, entry.receipt_identity_sha256),
        receipt_sha256=cast(str, entry.receipt_bytes_sha256),
        cancel_callback=cancel_callback,
    )
    query = session.create_query(page_size=50, cancel_callback=cancel_callback)
    if not _query_matches_entry(query, session, entry):
        raise ValueError("technical_universe_v4_catalog_entry_identity_mismatch")
    selection = session.select_stock_codes(
        query,
        cancel_callback=cancel_callback,
    )
    return _read_selection_page_result(
        session,
        query,
        selection,
        query,
        cancel_callback=cancel_callback,
    )


def _read_query_page(
    base: DailyMarketTechnicalUniverseV4Query,
    *,
    rule_state_filters: Sequence[DailyMarketTechnicalRuleStateFilterV4],
    combine_mode: str,
    stock_filter: Sequence[str],
    sort_key: str,
    descending: bool,
    page_index: int,
    page_size: int,
    read_session: DailyMarketTechnicalUniverseV4ReadSession | None = None,
    selection_query: DailyMarketTechnicalUniverseV4Query | None = None,
    selection: DailyMarketTechnicalUniverseV4ReadSelection | None = None,
    cancel_callback: Callable[[], bool] | None = None,
) -> _QueryReadResult:
    if _cancelled(cancel_callback):
        raise ValueError("technical_universe_v4_query_cancelled")
    session = read_session
    can_reuse_session = session is not None and session.matches_source(base)
    if not can_reuse_session:
        session = _open_read_session_for_query(base, cancel_callback=cancel_callback)
        selection_query = None
        selection = None
    if session is None:
        raise ValueError("technical_universe_v4_read_session_missing")
    _query_from_session(session, base, cancel_callback=cancel_callback)
    query = session.create_query(
        rule_state_filters=rule_state_filters,
        combine_mode=cast(Any, combine_mode),
        stock_filter=stock_filter,
        sort_key=sort_key,
        descending=descending,
        page_index=page_index,
        page_size=page_size,
        cancel_callback=cancel_callback,
    )
    if (
        selection is None
        or selection_query is None
        or not session.matches_source(selection_query)
        or not _same_query_selection_spec(selection_query, query)
    ):
        selection_query = query
        selection = session.select_stock_codes(
            selection_query,
            cancel_callback=cancel_callback,
        )
    else:
        _query_from_session(session, selection_query, cancel_callback=cancel_callback)
    return _read_selection_page_result(
        session,
        selection_query,
        selection,
        query,
        cancel_callback=cancel_callback,
    )


def _read_selected_stock(
    query: DailyMarketTechnicalUniverseV4Query,
    row: DailyMarketTechnicalParentV4Row,
    *,
    read_session: DailyMarketTechnicalUniverseV4ReadSession | None = None,
    selection_query: DailyMarketTechnicalUniverseV4Query | None = None,
    selection: DailyMarketTechnicalUniverseV4ReadSelection | None = None,
    cancel_callback: Callable[[], bool] | None = None,
) -> tuple[
    DailyMarketTechnicalUniverseV4Query,
    DailyMarketTechnicalParentV4Row,
    DailyMarketTechnicalUniverseV4Stock,
]:
    session = read_session
    can_reuse_session = session is not None and session.matches_source(query)
    if not can_reuse_session:
        session = _open_read_session_for_query(query, cancel_callback=cancel_callback)
        selection_query = None
        selection = None
    if session is None:
        raise ValueError("technical_universe_v4_read_session_missing")
    exact_query = _query_from_session(session, query, cancel_callback=cancel_callback)
    if (
        selection is None
        or selection_query is None
        or not session.matches_source(selection_query)
        or not _same_query_selection_spec(selection_query, exact_query)
    ):
        selection_query = exact_query
        selection = session.select_stock_codes(
            selection_query,
            cancel_callback=cancel_callback,
        )
    else:
        _query_from_session(session, selection_query, cancel_callback=cancel_callback)
    stock = read_daily_market_technical_universe_v4_stock_from_selection(
        selection,
        row.stock_code,
        session,
        page_index=query.page_index,
        page_size=query.page_size,
        cancel_callback=cancel_callback,
    )
    if (
        stock.origin_query != query
        or stock.snapshot.stock_code != row.stock_code
        or stock.snapshot.snapshot_identity_sha256 != row.snapshot_identity_sha256
        or stock.snapshot.source_identity != row.source_identity
    ):
        raise ValueError("technical_universe_v4_selected_stock_pin_mismatch")
    return query, row, stock


def _read_comparison(
    selections: Sequence[_ComparisonBasketItem],
    *,
    cancel_callback: Callable[[], bool] | None = None,
) -> _ComparisonTaskOutcome:
    try:
        comparison = read_daily_market_technical_universe_v4_comparison(
            tuple((item.query, item.row.stock_code) for item in selections),
            cancel_callback=cancel_callback,
        )
    except DailyMarketTechnicalUniverseV4ComparisonError as exc:
        if exc.code == "technical_universe_v4_comparison_cancelled":
            return _ComparisonTaskOutcome(comparison=None, cancelled=True)
        raise
    return _ComparisonTaskOutcome(comparison=comparison, cancelled=False)


def _read_origin_page(
    query: DailyMarketTechnicalUniverseV4Query,
    stock_code: str,
    *,
    read_session: DailyMarketTechnicalUniverseV4ReadSession | None = None,
    selection_query: DailyMarketTechnicalUniverseV4Query | None = None,
    selection: DailyMarketTechnicalUniverseV4ReadSelection | None = None,
    cancel_callback: Callable[[], bool] | None = None,
) -> _OriginRestoreResult:
    if _cancelled(cancel_callback):
        raise ValueError("technical_universe_v4_origin_restore_cancelled")
    session = read_session
    can_reuse_session = session is not None and session.matches_source(query)
    if not can_reuse_session:
        session = _open_read_session_for_query(query, cancel_callback=cancel_callback)
        selection_query = None
        selection = None
    if session is None:
        raise ValueError("technical_universe_v4_read_session_missing")
    exact_query = _query_from_session(session, query, cancel_callback=cancel_callback)
    if (
        selection is None
        or selection_query is None
        or not session.matches_source(selection_query)
        or not _same_query_selection_spec(selection_query, exact_query)
    ):
        selection_query = exact_query
        selection = session.select_stock_codes(
            selection_query,
            cancel_callback=cancel_callback,
        )
    else:
        _query_from_session(session, selection_query, cancel_callback=cancel_callback)
    result = _read_selection_page_result(
        session,
        selection_query,
        selection,
        exact_query,
        cancel_callback=cancel_callback,
    )
    page = result.page
    if page is None:
        raise ValueError("technical_universe_v4_origin_page_empty")
    if page.query != query or not any(row.stock_code == stock_code for row in page.rows):
        raise ValueError("technical_universe_v4_origin_stock_not_in_pinned_page")
    if _cancelled(cancel_callback):
        raise ValueError("technical_universe_v4_origin_restore_cancelled")
    return _OriginRestoreResult(
        page=page,
        stock_code=stock_code,
        read_session=session,
        selection_query=selection_query,
        selection=selection,
    )


def _query_matches_entry(
    query: DailyMarketTechnicalUniverseV4Query,
    read_session: DailyMarketTechnicalUniverseV4ReadSession,
    entry: DailyMarketTechnicalUniverseV4CatalogEntry,
) -> bool:
    return (
        read_session.matches_source(query)
        and Path(query.store_output_root) == Path(read_session.store_output_root)
        and query.generation_identity_sha256 == entry.generation_identity_sha256
        and query.plan_identity_sha256 == entry.plan_identity_sha256
        and query.plan_sha256 == entry.plan_bytes_sha256
        and query.receipt_identity_sha256 == entry.receipt_identity_sha256
        and query.receipt_sha256 == entry.receipt_bytes_sha256
        and query.receipt_status == entry.source_status
        and query.cohort_identity_sha256 == entry.cohort_identity_sha256
        and query.source_clock_identity_sha256 == entry.source_clock_identity_sha256
        and query.method_contracts_sha256 == entry.method_contracts_sha256
    )


def _open_read_session_for_query(
    query: DailyMarketTechnicalUniverseV4Query,
    *,
    cancel_callback: Callable[[], bool] | None,
) -> DailyMarketTechnicalUniverseV4ReadSession:
    return open_daily_market_technical_universe_v4_read_session(
        store_output_root=query.store_output_root,
        generation_identity_sha256=query.generation_identity_sha256,
        plan_identity_sha256=query.plan_identity_sha256,
        plan_sha256=query.plan_sha256,
        receipt_identity_sha256=query.receipt_identity_sha256,
        receipt_sha256=query.receipt_sha256,
        cancel_callback=cancel_callback,
    )


def _query_from_session(
    session: DailyMarketTechnicalUniverseV4ReadSession,
    query: DailyMarketTechnicalUniverseV4Query,
    *,
    cancel_callback: Callable[[], bool] | None,
) -> DailyMarketTechnicalUniverseV4Query:
    rebuilt = session.create_query(
        rule_state_filters=query.rule_state_filters,
        combine_mode=cast(Any, query.combine_mode),
        stock_filter=query.stock_filter,
        sort_key=query.sort_key,
        descending=query.descending,
        page_index=query.page_index,
        page_size=query.page_size,
        cancel_callback=cancel_callback,
    )
    if rebuilt != query or not session.matches_source(query):
        raise ValueError("technical_universe_v4_query_session_identity_mismatch")
    return rebuilt


def _same_query_selection_spec(
    left: DailyMarketTechnicalUniverseV4Query,
    right: DailyMarketTechnicalUniverseV4Query,
) -> bool:
    left_payload = left.to_dict()
    right_payload = right.to_dict()
    for payload in (left_payload, right_payload):
        payload.pop("page_index", None)
        payload.pop("page_size", None)
        payload.pop("query_identity_sha256", None)
    return left_payload == right_payload


def _read_selection_page_result(
    session: DailyMarketTechnicalUniverseV4ReadSession,
    selection_query: DailyMarketTechnicalUniverseV4Query,
    selection: DailyMarketTechnicalUniverseV4ReadSelection,
    query: DailyMarketTechnicalUniverseV4Query,
    *,
    cancel_callback: Callable[[], bool] | None,
) -> _QueryReadResult:
    if (
        not session.matches_source(selection_query)
        or not session.matches_source(query)
        or not _same_query_selection_spec(selection_query, query)
    ):
        raise ValueError("technical_universe_v4_read_selection_query_mismatch")
    selection_page = session.read_selection_page(
        selection,
        page_index=query.page_index,
        page_size=query.page_size,
        cancel_callback=cancel_callback,
    )
    page = selection_page.page
    if (
        selection_page.selection_identity_sha256 != selection.selection_identity_sha256
        or selection_page.page_index != query.page_index
        or selection_page.page_size != query.page_size
        or selection_page.matching_count != selection.matching_count
        or (page is not None and page.query != query)
    ):
        raise ValueError("technical_universe_v4_read_selection_page_mismatch")
    return _QueryReadResult(
        query=query,
        read_session=session,
        selection_query=selection_query,
        selection=selection,
        selection_page=selection_page,
    )


def _validate_bookmark_state(
    state: object,
    *,
    cancel_callback: Callable[[], bool] | None = None,
) -> DailyMarketTechnicalUniverseV4BookmarkState:
    """檢查 strict bookmark state 各結果與封存 query、股票 pin 的一致性。"""
    if _cancelled(cancel_callback):
        raise DailyMarketTechnicalUniverseV4BookmarkError(
            "technical_universe_v4_bookmark_cancelled"
        )
    if not isinstance(state, DailyMarketTechnicalUniverseV4BookmarkState):
        raise DailyMarketTechnicalUniverseV4BookmarkError(
            "technical_universe_v4_bookmark_state_type_invalid"
        )
    if (
        not isinstance(state.bookmark, DailyMarketTechnicalUniverseV4Bookmark)
        or not isinstance(state.origin_page, DailyMarketTechnicalUniverseV4Page)
        or not isinstance(state.selected_stock, DailyMarketTechnicalUniverseV4Stock)
    ):
        raise DailyMarketTechnicalUniverseV4BookmarkError(
            "technical_universe_v4_bookmark_state_components_invalid"
        )

    try:
        bookmark = DailyMarketTechnicalUniverseV4Bookmark.from_dict(
            state.bookmark.to_dict()
        )
        query = bookmark.origin_query
    except (DailyMarketTechnicalUniverseV4BookmarkError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalUniverseV4BookmarkError(
            "technical_universe_v4_bookmark_identity_invalid"
        ) from exc
    if (
        not isinstance(state.origin_page.query, DailyMarketTechnicalUniverseV4Query)
        or not isinstance(state.selected_stock.origin_query, DailyMarketTechnicalUniverseV4Query)
        or any(
            not isinstance(row, DailyMarketTechnicalParentV4Row)
            for row in state.origin_page.rows
        )
        or state.origin_page.query != query
        or state.selected_stock.origin_query != query
    ):
        raise DailyMarketTechnicalUniverseV4BookmarkError(
            "technical_universe_v4_bookmark_query_identity_mismatch"
        )

    code = bookmark.selected_stock_code
    selected_rows = tuple(
        row for row in state.origin_page.rows if row.stock_code == code
    )
    snapshot = state.selected_stock.snapshot
    if (
        len(selected_rows) != 1
        or snapshot.stock_code != code
        or snapshot.snapshot_identity_sha256 != bookmark.selected_snapshot_identity_sha256
        or snapshot.source_identity != bookmark.selected_source_identity
        or selected_rows[0].snapshot_identity_sha256 != bookmark.selected_snapshot_identity_sha256
        or selected_rows[0].source_identity != bookmark.selected_source_identity
    ):
        raise DailyMarketTechnicalUniverseV4BookmarkError(
            "technical_universe_v4_bookmark_selected_identity_mismatch"
        )

    saved_selections = bookmark.comparison_selections
    comparison = state.comparison
    if not saved_selections:
        if comparison is not None:
            raise DailyMarketTechnicalUniverseV4BookmarkError(
                "technical_universe_v4_bookmark_unexpected_comparison"
            )
    else:
        if (
            not isinstance(comparison, DailyMarketTechnicalUniverseV4Comparison)
            or len(comparison.columns) != len(saved_selections)
        ):
            raise DailyMarketTechnicalUniverseV4BookmarkError(
                "technical_universe_v4_bookmark_comparison_missing"
            )
        for saved, column in zip(saved_selections, comparison.columns, strict=True):
            if (
                not isinstance(column.origin_query, DailyMarketTechnicalUniverseV4Query)
                or not isinstance(column.row, DailyMarketTechnicalParentV4Row)
                or column.origin_query != saved.query
                or column.row.stock_code != saved.stock_code
                or column.row.snapshot_identity_sha256 != saved.snapshot_identity_sha256
                or column.row.source_identity != saved.source_identity
            ):
                raise DailyMarketTechnicalUniverseV4BookmarkError(
                    "technical_universe_v4_bookmark_comparison_identity_mismatch"
                )

    if _cancelled(cancel_callback):
        raise DailyMarketTechnicalUniverseV4BookmarkError(
            "technical_universe_v4_bookmark_cancelled"
        )
    return DailyMarketTechnicalUniverseV4BookmarkState(
        bookmark=bookmark,
        origin_page=state.origin_page,
        selected_stock=state.selected_stock,
        comparison=comparison,
    )


def _produce(
    request: DailyMarketTechnicalUniverseV4ProductionRequest,
    *,
    cancel_callback: Callable[[], bool] | None = None,
    official_pointer: Path | None = None,
) -> _ProductionTaskOutcome:
    original_callback = request.cancel_callback

    def is_cancelled() -> bool:
        return _cancelled(cancel_callback) or _cancelled(original_callback)

    prepared = replace(request, cancel_callback=is_cancelled)
    if official_pointer is not None:
        from app_module.selection_current_source_pair import produce_current_selection_bundle
        from app_module.daily_market_technical_official_disposition_bundle_v1 import (
            DailyMarketTechnicalOfficialDispositionBundleWriterV1,
        )
        scope = prepared.research_scope
        if scope is None:
            raise ValueError("official_bundle_explicit_research_scope_required")
        writer = DailyMarketTechnicalOfficialDispositionBundleWriterV1(
            scope.root / "technical_official_disposition", research_scope=scope)
        outcome = produce_current_selection_bundle(
            writer, production_request=prepared, pointer_path=official_pointer)
        return _ProductionTaskOutcome(
            result=outcome.technical_result, cancelled=outcome.technical_result.status == "cancelled",
            official_bundle=outcome.bundle_reference, official_error=outcome.bundle_error_code)
    result = produce_daily_market_technical_universe_v4(prepared)
    return _ProductionTaskOutcome(result=result, cancelled=result.status == "cancelled")


def _deferred_setup_matches_entry(
    setup: DailyMarketTechnicalV4DeferredProductionSetup,
    entry: DailyMarketTechnicalUniverseV4CatalogEntry | None,
) -> bool:
    if entry is None:
        return (
            setup.mode == "new"
            and setup.selected_entry is None
            and setup.selected_receipt_identity_sha256 is None
            and setup.selected_receipt_bytes_sha256 is None
        )
    return (
        setup.mode == "resume"
        and setup.selected_entry == entry
        and setup.selected_receipt_identity_sha256 == entry.receipt_identity_sha256
        and setup.selected_receipt_bytes_sha256 == entry.receipt_bytes_sha256
    )


def _prepared_request_matches_entry(
    request: DailyMarketTechnicalUniverseV4ProductionRequest,
    setup: DailyMarketTechnicalV4DeferredProductionSetup,
    entry: DailyMarketTechnicalUniverseV4CatalogEntry | None,
    *,
    store_output_root: Path,
) -> None:
    if (
        Path(setup.store_output_root).absolute() != store_output_root
        or Path(request.store_output_root).absolute() != store_output_root
    ):
        raise ValueError("producer_store_root_must_match_catalog_root")
    if entry is None:
        if (
            setup.mode != "new"
            or setup.selected_entry is not None
            or request.resume_receipt_identity_sha256 is not None
            or request.expected_resume_receipt_sha256 is not None
        ):
            raise ValueError("new_generation_cannot_carry_resume_pins")
        return
    if (
        not _deferred_setup_matches_entry(setup, entry)
        or request.resume_receipt_identity_sha256 != entry.receipt_identity_sha256
        or request.expected_resume_receipt_sha256 != entry.receipt_bytes_sha256
    ):
        raise ValueError("resume_request_must_match_selected_receipt_pins")


def _prepare_deferred_and_produce(
    setup: DailyMarketTechnicalV4DeferredProductionSetup,
    entry: DailyMarketTechnicalUniverseV4CatalogEntry | None,
    *,
    store_output_root: Path,
    cancel_callback: Callable[[], bool] | None = None,
    official_pointer: Path | None = None,
) -> _ProductionTaskOutcome:
    if _cancelled(cancel_callback):
        return _ProductionTaskOutcome(result=None, cancelled=True)
    request = setup.prepare_request(cancel_callback=cancel_callback)
    if _cancelled(cancel_callback):
        return _ProductionTaskOutcome(result=None, cancelled=True)
    if not isinstance(request, DailyMarketTechnicalUniverseV4ProductionRequest):
        raise TypeError("deferred setup 必須回傳 v4 ProductionRequest")
    _prepared_request_matches_entry(
        request,
        setup,
        entry,
        store_output_root=store_output_root,
    )
    if _cancelled(cancel_callback):
        return _ProductionTaskOutcome(result=None, cancelled=True)
    return _produce(request, cancel_callback=cancel_callback, official_pointer=official_pointer)


class DailyMarketTechnicalUniverseV4View(QWidget):
    """固定 full-N source 的 metadata 列表、strict query、分頁與原來源個股入口。"""

    stockSelected = Signal(object)
    comparisonReady = Signal(object)
    bookmarkPrepared = Signal(object)
    cancelRequested = Signal()
    productionFinished = Signal(object)
    officialBundleProduced = Signal(object)

    @property
    def current_query(self) -> DailyMarketTechnicalUniverseV4Query | None:
        return self._query

    @property
    def current_page(self) -> DailyMarketTechnicalUniverseV4Page | None:
        return self._page

    @property
    def selected_source(self) -> DailyMarketTechnicalUniverseV4CatalogEntry | None:
        item = self.sources.currentData()
        return item if isinstance(item, DailyMarketTechnicalUniverseV4CatalogEntry) else None

    def __init__(
        self,
        store_output_root: str | Path,
        parent: QWidget | None = None,
        *,
        production_request_factory: ProductionRequestFactory | None = None,
    ) -> None:
        super().__init__(parent)
        self.store_output_root = Path(store_output_root).absolute()
        self.production_request_factory = production_request_factory
        self._worker: TaskWorker | None = None
        self._worker_kind = ""
        self._generation = 0
        self._closing = False
        self._pending: _QueuedOperation | None = None
        self._query: DailyMarketTechnicalUniverseV4Query | None = None
        self._page: DailyMarketTechnicalUniverseV4Page | None = None
        self._read_session: DailyMarketTechnicalUniverseV4ReadSession | None = None
        self._selection_query: DailyMarketTechnicalUniverseV4Query | None = None
        self._selection: DailyMarketTechnicalUniverseV4ReadSelection | None = None
        self._source_clock: dict[str, object] | None = None
        self._source_cursor: str | None = None
        self._catalog_page: DailyMarketTechnicalUniverseV4CatalogPage | None = None
        self._current_entry: DailyMarketTechnicalUniverseV4CatalogEntry | None = None
        self._rule_filters: dict[str, QComboBox] = {}
        self._stock_filter_rejected_text: str | None = None
        self._comparison_basket: list[_ComparisonBasketItem] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(7)

        title = QLabel("每日技術規則研究（v4 保存來源）")
        title.setObjectName("dailyMarketTechnicalUniverseV4Title")
        title.setAccessibleName("每日技術規則研究 v4")
        root.addWidget(title)
        self.disclaimer = QLabel(
            "只瀏覽已保存的研究來源；五項規則顯示符合、不符合或未知。"
            "母體是來源清冊，不代表全市場、推薦、獲利機率或交易指令。"
            "資料可得時間未知；只供當下重述研究；不授歷史 PIT／可交易資格。"
        )
        self.disclaimer.setObjectName("dailyMarketTechnicalUniverseV4Disclaimer")
        self.disclaimer.setWordWrap(True)
        self.disclaimer.setTextFormat(Qt.TextFormat.PlainText)
        root.addWidget(self.disclaimer)

        source_group = QGroupBox("已保存來源")
        source_layout = QGridLayout(source_group)
        self.sources = QComboBox()
        self.sources.setObjectName("dailyMarketTechnicalUniverseV4Sources")
        self.sources.setAccessibleName("已保存的完整技術研究來源")
        self.refresh_button = QPushButton("查詢保存版本")
        self.refresh_button.setObjectName("dailyMarketTechnicalUniverseV4RefreshSources")
        self.load_button = QPushButton("嚴格核驗並讀取")
        self.load_button.setObjectName("dailyMarketTechnicalUniverseV4LoadSource")
        self.more_sources_button = QPushButton("更多版本")
        self.more_sources_button.setObjectName("dailyMarketTechnicalUniverseV4MoreSources")
        self.more_sources_button.setEnabled(False)
        self.produce_button = QPushButton("產製新研究版本")
        self.produce_button.setObjectName("dailyMarketTechnicalUniverseV4Produce")
        self.resume_button = QPushButton("續跑所選版本")
        self.resume_button.setObjectName("dailyMarketTechnicalUniverseV4Resume")
        self.cancel_button = QPushButton("取消目前工作")
        self.cancel_button.setObjectName("dailyMarketTechnicalUniverseV4Cancel")
        self.cancel_button.setEnabled(False)
        source_layout.addWidget(self.sources, 0, 0, 1, 4)
        source_layout.addWidget(self.refresh_button, 0, 4)
        source_layout.addWidget(self.load_button, 1, 0)
        source_layout.addWidget(self.more_sources_button, 1, 1)
        source_layout.addWidget(self.produce_button, 1, 2)
        source_layout.addWidget(self.resume_button, 1, 3)
        source_layout.addWidget(self.cancel_button, 1, 4)
        self.produce_official_button = QPushButton("產製技術與官方來源研究")
        self.produce_official_button.setObjectName("dailyMarketTechnicalUniverseV4ProduceOfficial")
        self.produce_official_button.setAccessibleName("選取官方保存來源並產製新研究")
        self.produce_official_button.setToolTip("先選取官方來源指標檔，再核對新研究母體與截止時間。")
        source_layout.addWidget(self.produce_official_button, 2, 0, 1, 5)
        self.official_publication_status = QLabel("官方聯合研究尚未產製。")
        self.official_publication_status.setWordWrap(True)
        self.official_publication_status.setTextFormat(Qt.TextFormat.PlainText)
        self.official_publication_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.official_publication_status.setObjectName("dailyMarketTechnicalUniverseV4OfficialPublication")
        source_layout.addWidget(self.official_publication_status, 3, 0, 1, 5)
        source_layout.setColumnStretch(0, 1)
        root.addWidget(source_group)

        self.source_pins = QLabel("尚未選取保存來源。")
        self.source_pins.setObjectName("dailyMarketTechnicalUniverseV4SourcePins")
        self.source_pins.setAccessibleName("保存來源狀態與完整識別資訊")
        self.source_pins.setWordWrap(True)
        self.source_pins.setTextFormat(Qt.TextFormat.PlainText)
        self.source_pins.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.source_pins)
        self.verified_pins = QLabel("尚未嚴格核驗查詢來源。")
        self.verified_pins.setObjectName("dailyMarketTechnicalUniverseV4VerifiedPins")
        self.verified_pins.setAccessibleName("目前表格使用的嚴格核驗來源 pin")
        self.verified_pins.setWordWrap(True)
        self.verified_pins.setTextFormat(Qt.TextFormat.PlainText)
        self.verified_pins.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.verified_pins)

        filter_group = QGroupBox("全母體規則篩選與排序")
        filter_layout = QGridLayout(filter_group)
        self.mode = QComboBox()
        self.mode.setObjectName("dailyMarketTechnicalUniverseV4CombineMode")
        self.mode.setAccessibleName("五項規則組合方式")
        self.mode.addItem("全部符合（AND）", "AND")
        self.mode.addItem("至少一項符合（OR）", "OR")
        self.stock_filter = QLineEdit()
        self.stock_filter.setObjectName("dailyMarketTechnicalUniverseV4StockFilter")
        self.stock_filter.setAccessibleName("依股票代碼篩選完整母體")
        self.stock_filter.setPlaceholderText("股票代碼，可用逗號分隔；最多 100,000 檔；空白表示全部")
        self.stock_filter.setMaxLength(_MAX_STOCK_FILTER_TEXT_LENGTH)
        self.stock_filter.inputRejected.connect(self._on_stock_filter_input_rejected)
        self.stock_filter.textEdited.connect(self._on_stock_filter_text_edited)
        filter_layout.addWidget(QLabel("組合方式"), 0, 0)
        filter_layout.addWidget(self.mode, 0, 1)
        filter_layout.addWidget(QLabel("股票"), 0, 2)
        filter_layout.addWidget(self.stock_filter, 0, 3, 1, 3)
        self.rule_filter_container = QWidget()
        self.rule_filter_layout = QGridLayout(self.rule_filter_container)
        self.rule_filter_layout.setContentsMargins(0, 0, 0, 0)
        self.rule_filter_layout.setHorizontalSpacing(8)
        self.rule_filter_layout.setVerticalSpacing(4)
        filter_layout.addWidget(self.rule_filter_container, 1, 0, 1, 6)

        self.sort = QComboBox()
        self.sort.setObjectName("dailyMarketTechnicalUniverseV4Sort")
        self.sort.setAccessibleName("全母體全域排序欄位")
        for key, label in _BASE_SORT_LABELS.items():
            self.sort.addItem(label, key)
        self.descending = QComboBox()
        self.descending.setObjectName("dailyMarketTechnicalUniverseV4SortDirection")
        self.descending.setAccessibleName("全域排序方向")
        self.descending.addItem("升冪", False)
        self.descending.addItem("降冪", True)
        self.page_size = QComboBox()
        self.page_size.setObjectName("dailyMarketTechnicalUniverseV4PageSize")
        self.page_size.setAccessibleName("每頁列數")
        for size in (25, 50, 100, 256):
            self.page_size.addItem(str(size), size)
        self.apply_button = QPushButton("套用全域查詢")
        self.apply_button.setObjectName("dailyMarketTechnicalUniverseV4Apply")
        filter_layout.addWidget(QLabel("排序"), 2, 0)
        filter_layout.addWidget(self.sort, 2, 1, 1, 2)
        filter_layout.addWidget(self.descending, 2, 3)
        filter_layout.addWidget(QLabel("每頁"), 2, 4)
        filter_layout.addWidget(self.page_size, 2, 5)
        filter_layout.addWidget(self.apply_button, 3, 0, 1, 6)
        root.addWidget(filter_group)

        self.summary = QLabel("尚未嚴格核驗保存來源。")
        self.summary.setObjectName("dailyMarketTechnicalUniverseV4Counts")
        self.summary.setAccessibleName("完整母體來源與資料計數")
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        root.addWidget(self.summary)

        self.table = QTableView()
        self.table.setObjectName("dailyMarketTechnicalUniverseV4Rows")
        self.results_model = SavedResearchPageTableModel[
            DailyMarketTechnicalParentV4Row
        ](
            (
                "股票",
                "決策日",
                "最新特徵日",
                "原始列數",
                "MA5／20",
                "K／D",
                "MACD",
                "量能比 20",
                "量能比 5",
            ),
            maximum_page_size=DAILY_MARKET_TECHNICAL_UNIVERSE_V4_QUERY_MAX_PAGE_SIZE,
            parent=self.table,
        )
        self.table.setModel(self.results_model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(False)
        root.addWidget(self.table)

        navigation = QHBoxLayout()
        self.previous_button = QPushButton("上一頁")
        self.previous_button.setObjectName("dailyMarketTechnicalUniverseV4Previous")
        self.next_button = QPushButton("下一頁")
        self.next_button.setObjectName("dailyMarketTechnicalUniverseV4Next")
        self.open_button = QPushButton("讀取原保存個股證據")
        self.open_button.setObjectName("dailyMarketTechnicalUniverseV4OpenStock")
        navigation.addWidget(self.previous_button)
        navigation.addWidget(self.next_button)
        navigation.addStretch(1)
        navigation.addWidget(self.open_button)
        root.addLayout(navigation)

        comparison_controls = QHBoxLayout()
        self.add_comparison_button = QPushButton("將所選股票加入比較")
        self.add_comparison_button.setObjectName("dailyMarketTechnicalUniverseV4AddComparison")
        self.clear_comparison_button = QPushButton("清空比較籃")
        self.clear_comparison_button.setObjectName("dailyMarketTechnicalUniverseV4ClearComparison")
        self.compare_button = QPushButton("比較原保存研究（2–256 檔）")
        self.compare_button.setObjectName("dailyMarketTechnicalUniverseV4Compare")
        self.compare_button.setEnabled(False)
        self.bookmark_button = QPushButton("收藏目前查詢與比較籃")
        self.bookmark_button.setObjectName("dailyMarketTechnicalUniverseV4Bookmark")
        self.bookmark_button.setEnabled(False)
        comparison_controls.addWidget(self.add_comparison_button)
        comparison_controls.addWidget(self.clear_comparison_button)
        comparison_controls.addWidget(self.compare_button)
        comparison_controls.addWidget(self.bookmark_button)
        root.addLayout(comparison_controls)
        self.comparison_basket_label = QLabel("比較籃 0／256；至少 2 檔可比較。")
        self.comparison_basket_label.setObjectName("dailyMarketTechnicalUniverseV4ComparisonBasket")
        self.comparison_basket_label.setAccessibleName("跨頁保留的原保存研究比較清單")
        self.comparison_basket_label.setWordWrap(True)
        self.comparison_basket_label.setTextFormat(Qt.TextFormat.PlainText)
        root.addWidget(self.comparison_basket_label)

        self.status = QLabel(
            "來源瀏覽不會讀取最新行情；查詢只讀明示保存的 v4 版本。"
        )
        self.status.setObjectName("dailyMarketTechnicalUniverseV4Status")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        root.addWidget(self.status)

        self.refresh_button.clicked.connect(self.refresh_sources)
        self.more_sources_button.clicked.connect(lambda: self.refresh_sources(append=True))
        self.load_button.clicked.connect(self.load_selected)
        self.produce_button.clicked.connect(self.produce_new)
        self.produce_official_button.clicked.connect(self.produce_with_official_sources)
        self.resume_button.clicked.connect(self.resume_selected)
        self.apply_button.clicked.connect(self.apply_query)
        self.previous_button.clicked.connect(lambda: self.change_page(-1))
        self.next_button.clicked.connect(lambda: self.change_page(1))
        self.open_button.clicked.connect(self.open_selected_stock)
        self.add_comparison_button.clicked.connect(self.add_selected_to_comparison)
        self.clear_comparison_button.clicked.connect(self.clear_comparison_basket)
        self.compare_button.clicked.connect(self.compare_basket)
        self.bookmark_button.clicked.connect(self.prepare_bookmark)
        self.cancel_button.clicked.connect(self.cancel)
        self.sources.currentIndexChanged.connect(self._show_selected_metadata)
        self.table.doubleClicked.connect(lambda _index: self.open_selected_stock())
        self._set_page_controls()
        if self.production_request_factory is None:
            self.produce_button.setEnabled(False)
            self.produce_official_button.setEnabled(False)
            self.resume_button.setEnabled(False)
            self.produce_button.setToolTip("由每日研究入口提供明示 source／cohort／cutoff 請求後啟用。")
            self.resume_button.setToolTip("由每日研究入口提供原 source／cohort／cutoff 請求後啟用。")

    def refresh_sources(self, *, append: bool = False) -> None:
        cursor = self._source_cursor if append else None
        if append and cursor is None:
            self.status.setText("目前沒有可續讀的 catalog cursor；重新查詢保存版本。")
            return

        def apply(value: object) -> None:
            if not isinstance(value, DailyMarketTechnicalUniverseV4CatalogPage):
                self.status.setText("保存版本列表格式不符；原列表保留。")
                return
            if not append:
                self.sources.clear()
            self._catalog_page = value
            for entry in value.rows:
                self.sources.addItem(self._catalog_label(entry), entry)
            self._source_cursor = value.next_cursor
            self.more_sources_button.setEnabled(value.next_cursor is not None)
            if not value.scan_complete:
                self.status.setText(
                    f"來源 inventory 尚未完整：掃描 {value.scanned_entry_count} 筆；"
                    "不能判定未列版本不存在。重新查詢可重新開始有界掃描。"
                )
            elif value.source_inventory_state == "no_saved_generations":
                self.status.setText("此保存根沒有已保存來源；空清單與零納入來源是不同狀態。")
            elif not value.rows:
                self.status.setText("已掃描保存根，沒有可列出的終端版本。")
            else:
                self.status.setText(
                    f"載入 {len(value.rows)} 筆 metadata 列；選取後仍要嚴格核驗來源鏈。"
                )
            if value.rows:
                self._show_selected_metadata()

        self._start(
            "查詢保存版本",
            lambda cancel_callback=None: _read_catalog_page(
                self.store_output_root,
                cursor,
                cancel_callback=cancel_callback,
            ),
            apply,
        )

    def load_selected(self) -> None:
        entry = self.selected_source
        if entry is None or not entry.is_selectable:
            self.status.setText("請選擇一筆可讀取的保存版本；診斷列不能載入。")
            return
        def apply(value: object) -> None:
            if not isinstance(value, _QueryReadResult):
                self.status.setText("嚴格來源查詢回傳格式不符；目前畫面保留。")
                return
            if self._show_query_result(value):
                self._current_entry = entry

        self._start(
            "嚴格核驗來源",
            lambda cancel_callback=None: _read_entry_page(
                self.store_output_root,
                entry,
                cancel_callback=cancel_callback,
            ),
            apply,
        )

    def apply_query(self) -> None:
        if self._stock_filter_rejected_text == self.stock_filter.text():
            self.status.setText("股票代碼輸入超過欄位上限，未套用；請縮短清單後再試。")
            return
        base = self._query
        if base is None:
            self.status.setText("請先嚴格核驗並讀取一筆保存來源。")
            return
        try:
            filters = self._selected_rule_state_filters()
            stock_codes = self._parse_stock_filter(self.stock_filter.text())
        except ValueError as exc:
            self.status.setText(f"查詢條件無效：{exc}")
            return

        combine_mode = str(self.mode.currentData())
        sort_key = str(self.sort.currentData())
        descending = bool(self.descending.currentData())
        page_size = int(self.page_size.currentData())
        read_session = self._read_session
        self._start(
            "更新全域查詢",
            lambda cancel_callback=None: _read_query_page(
                base,
                rule_state_filters=filters,
                combine_mode=combine_mode,
                stock_filter=stock_codes,
                sort_key=sort_key,
                descending=descending,
                page_index=0,
                page_size=page_size,
                read_session=read_session,
                cancel_callback=cancel_callback,
            ),
            self._apply_query_result,
        )

    def change_page(self, delta: int) -> None:
        base = self._query
        page = self._page
        if base is None or page is None:
            return
        next_index = base.page_index + delta
        if next_index < 0 or next_index >= page.page_count:
            return
        read_session = self._read_session
        selection_query = self._selection_query
        selection = self._selection
        self._start(
            f"讀取第 {next_index + 1} 頁",
            lambda cancel_callback=None: _read_query_page(
                base,
                rule_state_filters=base.rule_state_filters,
                combine_mode=base.combine_mode,
                stock_filter=base.stock_filter,
                sort_key=base.sort_key,
                descending=base.descending,
                page_index=next_index,
                page_size=base.page_size,
                read_session=read_session,
                selection_query=selection_query,
                selection=selection,
                cancel_callback=cancel_callback,
            ),
            self._apply_query_result,
        )

    def open_selected_stock(self) -> None:
        query = self._query
        row = self._selected_row()
        if query is None or row is None:
            self.status.setText("請選擇目前已核驗頁面的一檔股票。")
            return
        read_session = self._read_session
        selection_query = self._selection_query
        selection = self._selection
        self._start(
            f"讀取 {row.stock_code} 原保存證據",
            lambda cancel_callback=None: _read_selected_stock(
                query,
                row,
                read_session=read_session,
                selection_query=selection_query,
                selection=selection,
                cancel_callback=cancel_callback,
            ),
            self._emit_selected_stock,
        )

    def add_selected_to_comparison(self) -> None:
        query = self._query
        row = self._selected_row()
        if query is None or row is None:
            self.status.setText("請先選取目前嚴格核驗頁面中的股票，再加入比較籃。")
            return
        if len(self._comparison_basket) >= 256:
            self.status.setText("比較籃已達 256 檔上限；請先清空或移除研究後再加入。")
            return
        candidate = _ComparisonBasketItem(query=query, row=row)
        key = self._comparison_key(candidate)
        if any(self._comparison_key(item) == key for item in self._comparison_basket):
            self.status.setText(f"{row.stock_code} 已在比較籃中；同一保存來源不重複加入。")
            return
        self._invalidate_running_comparison()
        self._comparison_basket.append(candidate)
        self._render_comparison_basket()
        self.status.setText(f"已將 {row.stock_code} 的原查詢與保存列加入比較籃。")

    def clear_comparison_basket(self) -> None:
        self._invalidate_running_comparison()
        self._comparison_basket.clear()
        self._render_comparison_basket()
        self.status.setText("比較籃已清空；目前原查詢表格保留。")

    def compare_basket(self) -> None:
        if not 2 <= len(self._comparison_basket) <= 256:
            self.status.setText("比較需要至少 2 檔、最多 256 檔已加入的原保存研究。")
            return
        selections = tuple(self._comparison_basket)

        def apply(value: object) -> None:
            if not isinstance(value, _ComparisonTaskOutcome):
                self.status.setText("比較回傳格式不符；目前原查詢表格保留。")
                return
            if value.cancelled:
                self.status.setText("原保存研究比較已取消；目前查詢表格保留。")
                return
            comparison = value.comparison
            if comparison is None or len(comparison.columns) != len(selections):
                self.status.setText("比較來源數量與比較籃不符；目前查詢表格保留。")
                return
            self.comparisonReady.emit(comparison)
            self.status.setText(
                f"已嚴格重開比較籃內 {len(comparison.columns)} 檔的原保存研究；表格與來源 pin 保留。"
            )

        self._start(
            "比較原保存研究",
            lambda cancel_callback=None: _read_comparison(
                selections,
                cancel_callback=cancel_callback,
            ),
            apply,
            kind="comparison",
        )

    def restore_origin(
        self,
        query: DailyMarketTechnicalUniverseV4Query,
        stock_code: str,
    ) -> None:
        """依比較欄位保存的原 query pins 重開該頁並選回原股票。"""
        if not isinstance(query, DailyMarketTechnicalUniverseV4Query) or not isinstance(stock_code, str):
            self.status.setText("返回來源要求明確的原查詢與股票代碼。")
            return
        read_session = self._read_session
        selection_query = self._selection_query
        selection = self._selection

        def apply(value: object) -> None:
            if not isinstance(value, _OriginRestoreResult):
                self.status.setText("原查詢回傳格式不符；目前表格保留。")
                return
            if not any(
                row.stock_code == value.stock_code
                for row in value.page.rows
            ):
                self.status.setText("原股票不在嚴格核驗的保存頁；目前表格保留。")
                return
            self._current_entry = None
            self._show_page(
                value.page,
                read_session=value.read_session,
                selection_query=value.selection_query,
                selection=value.selection,
                selected_stock_code=value.stock_code,
            )
            self.source_pins.setText(
                "目前表格依本次已核驗保存版本返回，並重新核驗所選原 artifact；"
                "上方 catalog metadata 選取只代表候選列，表格實際來源見下方 verified pins。"
            )
            self.status.setText(
                f"已依原保存 query pins 返回 {value.stock_code}；沒有改讀其他保存版本。"
            )

        self._start(
            f"返回 {stock_code} 原查詢",
            lambda cancel_callback=None: _read_origin_page(
                query,
                stock_code,
                read_session=read_session,
                selection_query=selection_query,
                selection=selection,
                cancel_callback=cancel_callback,
            ),
            apply,
        )

    def prepare_bookmark(self) -> None:
        query = self._query
        row = self._selected_row()
        if query is None or row is None:
            self.status.setText("請先選取目前已嚴格核驗頁面中的股票，再準備收藏。")
            return
        if len(self._comparison_basket) == 1:
            self.status.setText(
                "比較籃只有 1 檔，無法收藏為比較；請清空比較籃或補足至少 2 檔。"
            )
            return
        if len(self._comparison_basket) > 256:
            self.status.setText("比較籃超過 256 檔上限，未準備收藏。")
            return

        scroll_position = int(self.table.verticalScrollBar().value())
        comparison_selections = tuple(
            (item.query, item.row.stock_code)
            for item in self._comparison_basket
        )

        def apply(value: object) -> None:
            if not isinstance(value, DailyMarketTechnicalUniverseV4Bookmark):
                self.status.setText("收藏準備回傳格式不符；未送出收藏。")
                return
            self.bookmarkPrepared.emit(value)
            self.status.setText(
                f"已準備 {row.stock_code} 的原 query 與比較籃收藏；尚未寫入觀察清單。"
            )

        self._start(
            "準備原保存研究收藏",
            lambda cancel_callback=None: create_daily_market_technical_universe_v4_bookmark_fresh(
                query,
                row.stock_code,
                scroll_position=scroll_position,
                comparison_selections=comparison_selections,
                cancel_callback=cancel_callback,
            ),
            apply,
            kind="bookmark",
        )

    def restore_bookmark_state(
        self,
        state: DailyMarketTechnicalUniverseV4BookmarkState,
    ) -> None:
        """還原 strict reader 已核驗的原 query、個股、捲動位置與比較籃。"""

        def apply(value: object) -> None:
            if not isinstance(value, DailyMarketTechnicalUniverseV4BookmarkState):
                self.status.setText("收藏狀態回傳格式不符；目前畫面保留。")
                return
            self._current_entry = None
            self._show_page(value.origin_page)
            self._select_stock_code(value.bookmark.selected_stock_code)
            comparison = value.comparison
            if comparison is None:
                self._comparison_basket = []
            else:
                self._comparison_basket = [
                    _ComparisonBasketItem(query=column.origin_query, row=column.row)
                    for column in comparison.columns
                ]
            self._render_comparison_basket()
            self.table.verticalScrollBar().setValue(value.bookmark.scroll_position)
            self.source_pins.setText(
                "目前表格與比較籃已還原自 strict bookmark state；"
                "上方 catalog metadata 僅是候選列，實際 query pins 見下方 verified pins。"
            )
            self.status.setText(
                f"已還原收藏 query、{value.bookmark.selected_stock_code}、捲動位置與"
                f"{len(self._comparison_basket)} 檔比較籃；沒有讀取最新來源。"
            )

        self._start(
            "驗證並還原研究收藏",
            lambda cancel_callback=None: _validate_bookmark_state(
                state,
                cancel_callback=cancel_callback,
            ),
            apply,
            kind="bookmark_restore",
        )

    @staticmethod
    def _comparison_key(item: _ComparisonBasketItem) -> tuple[str, str, str, str]:
        query = item.query
        return (
            query.store_output_root,
            query.generation_identity_sha256,
            query.receipt_identity_sha256,
            item.row.stock_code,
        )

    def _invalidate_running_comparison(self) -> None:
        worker = self._worker
        if worker is None or self._worker_kind != "comparison":
            return
        self._generation += 1
        self._pending = None
        worker.cancel(cooperative=True, wait=False)
        self.status.setText("比較籃已變更；已取消舊比較，原查詢表格保留。")

    def _render_comparison_basket(self) -> None:
        count = len(self._comparison_basket)
        stock_codes = [item.row.stock_code for item in self._comparison_basket]
        display_codes = "、".join(stock_codes) if stock_codes else "尚無股票"
        self.comparison_basket_label.setText(
            f"比較籃 {count}／256；{display_codes}；至少 2 檔才可比較。"
        )
        self.clear_comparison_button.setEnabled(count > 0 and not self._closing)
        self.compare_button.setEnabled(2 <= count <= 256 and not self._closing)

    def _select_stock_code(self, stock_code: str) -> bool:
        index = self.results_model.index_for_stock(stock_code)
        if not index.isValid():
            return False
        self.table.setCurrentIndex(index)
        self.table.selectRow(index.row())
        return True

    def produce_new(self) -> None:
        self._start_production(None)

    def produce_with_official_sources(self) -> None:
        if self.production_request_factory is None or self._closing:
            return
        selected, _filter = QFileDialog.getOpenFileName(
            self, "選取官方市場與處置來源指標", "", "官方來源指標 (*.json)")
        if not selected:
            return
        self._start_production(None, official_pointer=Path(selected).absolute())

    def resume_selected(self) -> None:
        entry = self.selected_source
        if entry is None or not entry.is_selectable:
            self.status.setText("續跑前請選擇一筆有明示收據 pin 的來源。")
            return
        self._start_production(entry)

    def _start_production(
        self,
        entry: DailyMarketTechnicalUniverseV4CatalogEntry | None,
        *,
        official_pointer: Path | None = None,
    ) -> None:
        factory = self.production_request_factory
        if factory is None:
            self.status.setText("每日研究入口尚未提供明示產製請求。")
            return
        try:
            factory_result = factory(entry)
            if isinstance(factory_result, DailyMarketTechnicalV4DeferredProductionSetup):
                setup = factory_result
                if not _deferred_setup_matches_entry(setup, entry):
                    raise ValueError("deferred_setup_must_match_selected_receipt_pins")
                request = None
            elif isinstance(factory_result, DailyMarketTechnicalUniverseV4ProductionRequest):
                # 保留舊同步 factory 呼叫方式；每日研究入口已改用 deferred setup。
                request = factory_result
                setup = None
                if Path(request.store_output_root).absolute() != self.store_output_root:
                    raise ValueError("producer_store_root_must_match_catalog_root")
                if entry is None:
                    if (
                        request.resume_receipt_identity_sha256 is not None
                        or request.expected_resume_receipt_sha256 is not None
                    ):
                        raise ValueError("new_generation_cannot_carry_resume_pins")
                elif (
                    request.resume_receipt_identity_sha256 != entry.receipt_identity_sha256
                    or request.expected_resume_receipt_sha256 != entry.receipt_bytes_sha256
                ):
                    raise ValueError("resume_request_must_match_selected_receipt_pins")
            else:
                raise TypeError(
                    "production_request_factory 必須回傳 v4 ProductionRequest 或 DeferredProductionSetup"
                )
        except Exception as exc:
            self.status.setText(f"產製請求未送出：{exc}")
            return

        operation_name = "產製新研究版本" if entry is None else "續跑所選研究版本"

        def apply(value: object) -> None:
            if not isinstance(value, _ProductionTaskOutcome):
                self.status.setText("產製回傳格式不符；請重新查詢收據。")
                return
            if value.result is None:
                self.status.setText("來源設定核驗已取消；未呼叫產製器，原保存來源保留。")
                return
            result = value.result
            self.productionFinished.emit(result)
            if official_pointer is not None:
                if value.official_bundle is not None:
                    reference = value.official_bundle
                    self.official_publication_status.setText(
                        "官方聯合研究已保存；到「官方處置與市場對照研究」選擇下列保存來源資料夾，再更新來源清單：\n"
                        + reference.output_root
                        + f"\n保存列數：{reference.row_count}；來源涵蓋：{reference.source_coverage_status}；只供當下研究。")
                    self.officialBundleProduced.emit(reference)
                else:
                    self.official_publication_status.setText(
                        "官方聯合研究未完成；"
                        + ("技術收據可另行查詢。" if result.receipt is not None else "未取得技術收據。")
                        + "原因："
                        + (value.official_error or result.error_code or result.status))
            self.status.setText(
                f"產製狀態：{result.status}；步驟：{result.step}；"
                f"已保存段：{len(result.completed_segment_indices)}；"
                f"錯誤：{result.error_code or '無'}。"
            )
            if result.receipt is not None:
                # 完成、取消或失敗的收據都會保留並可供查詢；產製器發布後重新掃描清冊。
                self.refresh_sources()

        if setup is not None:
            self._start(
                operation_name,
                lambda cancel_callback=None: _prepare_deferred_and_produce(
                    setup,
                    entry,
                    store_output_root=self.store_output_root,
                    cancel_callback=cancel_callback,
                    official_pointer=official_pointer,
                ),
                apply,
                kind="production",
            )
        else:
            if request is None:
                self.status.setText("產製請求沒有可執行內容。")
                return
            self._start(
                operation_name,
                lambda cancel_callback=None: _produce(
                    request,
                    cancel_callback=cancel_callback,
                    official_pointer=official_pointer,
                ),
                apply,
                kind="production",
            )

    def cancel(self) -> None:
        worker = self._worker
        if worker is None:
            return
        if self._worker_kind != "production":
            self._generation += 1
            self._pending = None
        worker.cancel(cooperative=True, wait=False)
        self.cancelRequested.emit()
        if self._worker_kind == "production":
            self.status.setText("已送出合作式取消；保存協調器會回報 partial/cancelled 收據。")
        else:
            self.status.setText(
                "已取消目前讀取；晚到結果不會替換畫面。metadata inventory scan 可能完成後才釋放工作。"
            )

    def begin_shutdown(self) -> bool:
        self._closing = True
        self._pending = None
        self.cancel()
        return self._worker is None or not self._worker.isRunning()

    def _start(
        self,
        name: str,
        operation: Callable[..., object],
        apply: Callable[[object], None],
        *,
        kind: str = "read",
    ) -> None:
        if self._closing:
            return
        self._generation += 1
        generation = self._generation
        pending = _QueuedOperation(name, operation, apply, kind)
        if self._worker is not None:
            self._pending = pending
            self._worker.cancel(cooperative=True, wait=False)
            self.status.setText(f"已要求目前工作停止；完成後開始：{name}。")
            return
        self._launch(pending, generation, kind)

    def _launch(
        self,
        pending: _QueuedOperation,
        generation: int,
        kind: str,
    ) -> None:
        if self._closing:
            return
        worker = TaskWorker(pending.operation)
        self._worker = worker
        self._worker_kind = kind
        worker.finished.connect(
            lambda value: pending.apply(value)
            if generation == self._generation and not self._closing
            else None
        )
        worker.error.connect(
            lambda message: self._show_worker_error(pending.name, message)
            if generation == self._generation and not self._closing
            else None
        )
        worker.cancelled.connect(
            lambda: self._show_worker_cancelled(pending.name)
            if generation == self._generation and not self._closing
            else None
        )
        worker.native_thread_finished.connect(lambda: self._release(worker))
        self.cancel_button.setEnabled(True)
        self.status.setText(f"背景工作中：{pending.name}。")
        worker.start()

    def _release(self, worker: TaskWorker) -> None:
        if self._worker is worker:
            self._worker = None
            self._worker_kind = ""
            self.cancel_button.setEnabled(False)
        worker.deleteLater()
        if self._pending is not None and not self._closing:
            pending = self._pending
            self._pending = None
            self._launch(pending, self._generation, pending.kind)

    def _show_worker_error(self, name: str, message: str) -> None:
        first_line = message.splitlines()[0] if message.splitlines() else "worker_error"
        self.status.setText(f"{name}失敗：{first_line}；目前已核驗結果保留。")

    def _show_worker_cancelled(self, name: str) -> None:
        self.status.setText(f"{name}已取消；目前已核驗結果保留。")

    def _show_selected_metadata(self, *_args: object) -> None:
        entry = self.selected_source
        self.resume_button.setEnabled(
            self.production_request_factory is not None
            and entry is not None
            and entry.is_selectable
            and not self._closing
        )
        if entry is None:
            self.source_pins.setText("尚未選取 catalog metadata；目前表格來源列於下方。")
            return
        if entry.metadata_state == "diagnostic":
            self.source_pins.setText(
                f"診斷列｜{entry.relative_path}｜{entry.diagnostic_code or 'metadata_invalid'}；"
                "此列不能作為查詢或續跑來源。下方若有表格，仍屬原先嚴格核驗來源。"
            )
            return
        self.source_pins.setText(
            "目前選取列的 metadata 尚未完成 strict 核驗；按「嚴格核驗並讀取」前不會替換表格。\n"
            f"版本：{entry.relative_path}\n"
            f"狀態：{entry.source_status}；母體：{entry.population_state}；日期：{entry.decision_date}\n"
            f"generation：{entry.generation_identity_sha256}\n"
            f"plan identity／bytes：{entry.plan_identity_sha256}／{entry.plan_bytes_sha256}\n"
            f"receipt identity／bytes：{entry.receipt_identity_sha256}／{entry.receipt_bytes_sha256}\n"
            f"cohort：{entry.cohort_identity_sha256}\n"
            f"source clock：{entry.source_clock_identity_sha256}\n"
            f"method contract：{entry.method_contracts_sha256}\n"
            "表格若已有內容，來源 pin 另列於下方。"
        )

    @staticmethod
    def _catalog_label(entry: DailyMarketTechnicalUniverseV4CatalogEntry) -> str:
        if entry.metadata_state == "diagnostic":
            return f"診斷｜{entry.relative_path}｜{entry.diagnostic_code or 'metadata_invalid'}"
        counts = entry.counts
        processed = counts.processed_count if counts is not None else 0
        pending = counts.pending_count if counts is not None else 0
        declared = counts.declared_count if counts is not None else 0
        return (
            f"{entry.decision_date}｜{entry.universe_id}｜{entry.population_version}｜"
            f"{entry.source_status}｜{entry.population_state}｜"
            f"宣告 {declared}／已處理 {processed}／待處理 {pending}｜metadata 未核"
        )

    def _show_query_result(self, value: _QueryReadResult) -> bool:
        return self._apply_query_result(value, source_clock=value.source_clock)

    def _apply_query_result(
        self,
        value: object,
        *,
        source_clock: dict[str, object] | None = None,
    ) -> bool:
        if not isinstance(value, _QueryReadResult):
            self.status.setText("查詢回傳格式不符；目前已核驗結果保留。")
            return False
        page = value.page
        if (
            not isinstance(value.query, DailyMarketTechnicalUniverseV4Query)
            or not isinstance(value.read_session, DailyMarketTechnicalUniverseV4ReadSession)
            or not isinstance(value.selection_query, DailyMarketTechnicalUniverseV4Query)
            or not isinstance(value.selection, DailyMarketTechnicalUniverseV4ReadSelection)
            or not isinstance(value.selection_page, DailyMarketTechnicalUniverseV4ReadSelectionPage)
            or not value.read_session.matches_source(value.query)
            or not value.read_session.matches_source(value.selection_query)
            or not _same_query_selection_spec(value.selection_query, value.query)
            or value.selection_page.selection_identity_sha256
            != value.selection.selection_identity_sha256
            or value.selection_page.matching_count != value.selection.matching_count
            or (page is not None and page.query != value.query)
        ):
            self.status.setText("查詢來源或 selection pin 不符；目前已核驗結果保留。")
            return False
        if page is None or page.matching_count == 0:
            previous_query = self._query
            same_source = (
                previous_query is not None
                and self._same_source_pins(previous_query, value.query)
            )
            source_counts = value.read_session.source_counts
            self._query = value.query
            self._page = None
            self._read_session = value.read_session
            self._selection_query = value.selection_query
            self._selection = value.selection
            if not same_source:
                self._source_clock = None
            self._ensure_rule_filters(value.query.method_rule_keys)
            self._set_filter_controls(value.query)
            self._replace_table_page(())
            empty_lines = [
                f"{value.query.universe_id}｜{value.query.population_version}｜"
                f"決策日 {value.query.decision_date}",
            ]
            empty_lines.append(
                f"已核驗母體計數：宣告 {source_counts.declared_count}、納入 {source_counts.included_count}、"
                f"排除 {source_counts.excluded_count}、已處理 {source_counts.processed_count}、"
                f"待處理 {source_counts.pending_count}、缺資料 {source_counts.missing_data_count}。"
            )
            empty_lines.extend((
                "符合目前篩選 0 筆；沒有可顯示頁面。",
                "全市場宣稱：否。可修改條件後重新查詢；目前沒有可研究列。",
            ))
            self.summary.setText("\n".join(empty_lines))
            self.verified_pins.setText(
                self._verified_pin_text(value.query, self._source_clock)
            )
            self._set_page_controls()
            self.status.setText("篩選完成：0 筆；可修改條件重新查詢。")
            return True
        self._show_page(
            page,
            source_clock=source_clock,
            read_session=value.read_session,
            selection_query=value.selection_query,
            selection=value.selection,
        )
        return True

    def _show_page(
        self,
        page: DailyMarketTechnicalUniverseV4Page,
        *,
        source_clock: dict[str, object] | None = None,
        read_session: DailyMarketTechnicalUniverseV4ReadSession | None = None,
        selection_query: DailyMarketTechnicalUniverseV4Query | None = None,
        selection: DailyMarketTechnicalUniverseV4ReadSelection | None = None,
        selected_stock_code: str | None = None,
    ) -> None:
        previous_query = self._query
        same_source = (
            previous_query is not None
            and self._same_source_pins(previous_query, page.query)
        )
        if self._query == page.query and self._page is not None:
            selected_row = self._selected_row()
            selected_code = selected_row.stock_code if selected_row is not None else None
        else:
            selected_code = None
        self._query = page.query
        self._page = page
        self._read_session = read_session
        self._selection_query = selection_query
        self._selection = selection
        if source_clock is not None:
            self._source_clock = source_clock
        elif not same_source:
            # source-clock payload 僅可沿同一組保存來源 pins 重用，不能讓舊內容
            # 與返回比較欄後的新 generation／receipt SHA 一起顯示。
            self._source_clock = None
        self._ensure_rule_filters(page.query.method_rule_keys)
        self._set_filter_controls(page.query)
        counts = page.counts
        state_text = "完整" if page.is_complete else f"{page.query.receipt_status}／未完整"
        pieces = [
            f"{page.query.universe_id}｜{page.query.population_version}｜決策日 {page.query.decision_date}",
            f"母體狀態：{state_text}；宣告 {counts.declared_count}、納入 {counts.included_count}、"
            f"排除 {counts.excluded_count}、已處理 {counts.processed_count}、待處理 {counts.pending_count}",
            f"缺資料 {counts.missing_data_count}、待處理缺資料 {counts.missing_data_pending_count}、"
            f"未知規則股票 {page.unknown_rule_count}",
            f"已核段 {page.processed_segment_count}/{page.query.segment_count}；"
            f"符合目前篩選 {page.matching_count} 筆，第 {page.query.page_index + 1}/{page.page_count} 頁",
            f"涵蓋：{page.coverage_scope}；聚合：{page.aggregation_scope}；全市場宣稱：否",
        ]
        if page.exclusion_reasons:
            pieces.append(
                "排除理由：" + "；".join(f"{code}：{reason}" for code, reason in page.exclusion_reasons)
            )
        self.summary.setText("\n".join(pieces))
        self.verified_pins.setText(self._verified_pin_text(page.query, self._source_clock))
        self._render_rows(
            page.rows,
            selected_code=(selected_stock_code or selected_code),
        )
        self._set_page_controls()
        self.status.setText(
            "全母體已先完成條件篩選與全域排序，再取目前頁；缺件與未知維持分開。"
        )

    @staticmethod
    def _same_source_pins(
        left: DailyMarketTechnicalUniverseV4Query,
        right: DailyMarketTechnicalUniverseV4Query,
    ) -> bool:
        return (
            left.store_output_root == right.store_output_root
            and left.generation_identity_sha256 == right.generation_identity_sha256
            and left.plan_identity_sha256 == right.plan_identity_sha256
            and left.plan_sha256 == right.plan_sha256
            and left.receipt_identity_sha256 == right.receipt_identity_sha256
            and left.receipt_sha256 == right.receipt_sha256
            and left.cohort_identity_sha256 == right.cohort_identity_sha256
            and left.source_clock_identity_sha256 == right.source_clock_identity_sha256
            and left.method_contracts_sha256 == right.method_contracts_sha256
        )

    @staticmethod
    def _verified_pin_text(
        query: DailyMarketTechnicalUniverseV4Query,
        source_clock: dict[str, object] | None,
    ) -> str:
        lines = [
            "此固定版本於 read-session 建立時通過 strict 核驗；本頁 child artifact 依 pin 重讀。",
            "此狀態不宣稱來源檔在核驗後未變；重新載入可再次完整 strict 核驗。",
            f"store root：{query.store_output_root}",
            f"generation：{query.generation_identity_sha256}",
            f"plan identity／bytes：{query.plan_identity_sha256}／{query.plan_sha256}",
            f"receipt identity／bytes：{query.receipt_identity_sha256}／{query.receipt_sha256}；狀態：{query.receipt_status}",
            f"cohort：{query.cohort_identity_sha256}；來源時計：{query.source_clock_identity_sha256}",
            f"method contract：{query.method_contracts_sha256}",
            "來源時計 payload 由 source-clock SHA 固定；查詢不重新讀取來源 DB。",
            "資料可得時間未知；只供當下重述研究；不授歷史 PIT／可交易資格。",
        ]
        if source_clock is not None:
            lines.append(
                "source clock 固定資訊：\n"
                + json.dumps(source_clock, ensure_ascii=False, sort_keys=True, indent=2)
            )
        return "\n".join(lines)

    def _ensure_rule_filters(self, rule_keys: Sequence[str]) -> None:
        while self.rule_filter_layout.count():
            item = self.rule_filter_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._rule_filters.clear()
        for index, key in enumerate(rule_keys):
            label_text = _RULE_LABELS.get(key, key)
            label = QLabel(label_text)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setAccessibleName(f"{label_text}規則篩選")
            combo = QComboBox()
            combo.setObjectName(f"dailyMarketTechnicalV4Filter_{key}")
            combo.setAccessibleName(f"{label_text}狀態篩選")
            for option_label, filter_id in _RULE_STATE_FILTER_OPTIONS:
                combo.addItem(option_label, filter_id)
            row, col = divmod(index, 2)
            self.rule_filter_layout.addWidget(label, row, col * 2)
            self.rule_filter_layout.addWidget(combo, row, col * 2 + 1)
            self._rule_filters[key] = combo

        sort = self.sort
        current_sort = str(sort.currentData())
        sort.clear()
        for key, label in _BASE_SORT_LABELS.items():
            sort.addItem(label, key)
        for key in rule_keys:
            label = _RULE_LABELS.get(key, key)
            for field_name, field_label in _RULE_SORT_LABELS.items():
                sort.addItem(f"{label}｜{field_label}", f"{key}.{field_name}")
        sort_index = sort.findData(current_sort)
        if sort_index >= 0:
            sort.setCurrentIndex(sort_index)

    def _set_filter_controls(self, query: DailyMarketTechnicalUniverseV4Query) -> None:
        self.mode.setCurrentIndex(self.mode.findData(query.combine_mode))
        self._stock_filter_rejected_text = None
        self.stock_filter.setText(", ".join(query.stock_filter))
        self.sort.setCurrentIndex(self.sort.findData(query.sort_key))
        self.descending.setCurrentIndex(self.descending.findData(query.descending))
        self.page_size.setCurrentIndex(self.page_size.findData(query.page_size))
        states_by_key = {
            item.rule_key: item.states
            for item in query.rule_state_filters
        }
        for key, combo in self._rule_filters.items():
            states = states_by_key.get(key)
            filter_id = _NO_STATE_FILTER
            if states is not None:
                filter_id = _RULE_STATE_FILTER_STATES_TO_ID.get(states, "")
                if not filter_id:
                    raise ValueError("daily_market_technical_universe_v4_filter_state_unavailable")
            selected_index = combo.findData(filter_id)
            if selected_index < 0:
                raise ValueError("daily_market_technical_universe_v4_filter_state_unavailable")
            combo.setCurrentIndex(selected_index)

    def _selected_rule_state_filters(
        self,
    ) -> tuple[DailyMarketTechnicalRuleStateFilterV4, ...]:
        filters: list[DailyMarketTechnicalRuleStateFilterV4] = []
        for key, combo in self._rule_filters.items():
            value = combo.currentData()
            if not isinstance(value, str) or value not in _RULE_STATE_FILTER_ID_TO_STATES:
                raise ValueError("規則狀態篩選格式無效")
            states = _RULE_STATE_FILTER_ID_TO_STATES[value]
            if states is None:
                continue
            if any(state not in _STATE_VALUES for state in states):
                raise ValueError("規則狀態篩選格式無效")
            filters.append(DailyMarketTechnicalRuleStateFilterV4.create(key, states))
        return tuple(filters)

    def _on_stock_filter_input_rejected(self) -> None:
        self._stock_filter_rejected_text = self.stock_filter.text()

    def _on_stock_filter_text_edited(self, text: str) -> None:
        if self._stock_filter_rejected_text is not None and text != self._stock_filter_rejected_text:
            self._stock_filter_rejected_text = None

    def _render_rows(
        self,
        rows: Sequence[DailyMarketTechnicalParentV4Row],
        *,
        selected_code: str | None = None,
    ) -> None:
        model_rows: list[SavedResearchTableRow[DailyMarketTechnicalParentV4Row]] = []
        for row in rows:
            if tuple(rule.key for rule in row.rules) != tuple(_RULE_LABELS):
                raise ValueError("daily_market_technical_universe_v4_view_rule_set_mismatch")
            stock_label = row.stock_code
            if row.raw_row_count == 0:
                stock_label += "（缺資料）"
            cells = [
                stock_label,
                row.decision_date.isoformat(),
                row.latest_feature_date.isoformat() if row.latest_feature_date else "未知",
                str(row.raw_row_count),
            ]
            tooltip_lines = [
                f"股票：{row.stock_code}",
                f"來源 identity：{row.source_identity}",
                f"保存 snapshot：{row.snapshot_identity_sha256}",
                f"觀測前綴連續：{'是' if row.observed_prefix_contiguous else '否'}",
                f"原始資料列：{row.raw_row_count}",
            ]
            for rule in row.rules:
                status = _STATE_LABELS.get(rule.state, "未知")
                if rule.ratio is not None:
                    status += f"｜比率 {rule.ratio}"
                cells.append(status)
                detail = [
                    f"{_RULE_LABELS.get(rule.key, rule.key)}：{_STATE_LABELS.get(rule.state, '未知')}",
                    f"方法：{rule.method_id} {rule.version}",
                    f"決策截止：{rule.decision_cutoff.isoformat()}；最新特徵日：{rule.feature_date or '未知'}；前一特徵日：{rule.previous_feature_date or '未知'}",
                    f"來源：{rule.source_identity}；lookahead：{rule.lookahead_check}；可得性：{rule.availability_result}",
                    "資料可得時間未知；只供當下重述研究；不授歷史 PIT／可交易資格。",
                    f"用途：{rule.to_dict().get('usage')}；歷史 PIT 資格：{'是' if rule.to_dict().get('pit_eligible') is True else '否'}",
                ]
                if rule.numerator is not None or rule.denominator is not None:
                    detail.append(f"分子：{rule.numerator}；分母：{rule.denominator}；比率：{rule.ratio}")
                if rule.supports:
                    detail.append("支持：" + "；".join(rule.supports))
                if rule.counterevidence:
                    detail.append("反證：" + "；".join(rule.counterevidence))
                if rule.unknown_reasons:
                    detail.append("未知原因：" + "；".join(rule.unknown_reasons))
                if rule.raw_fact_refs:
                    detail.append("原始事實引用：" + json.dumps(
                        [item.to_dict() for item in rule.raw_fact_refs],
                        ensure_ascii=False,
                        sort_keys=True,
                    ))
                tooltip_lines.extend(detail)
            full_tooltip = "\n".join(tooltip_lines)
            model_rows.append(
                SavedResearchTableRow(
                    stock_code=row.stock_code,
                    source_row=row,
                    cells=tuple(cells),
                    tooltips=(full_tooltip,) * len(cells),
                )
            )
        self._replace_table_page(tuple(model_rows), selected_code=selected_code)
        self.open_button.setEnabled(bool(model_rows) and not self._closing)

    def _replace_table_page(
        self,
        rows: tuple[SavedResearchTableRow[DailyMarketTechnicalParentV4Row], ...],
        *,
        selected_code: str | None = None,
    ) -> None:
        selection_model = self.table.selectionModel()
        if selection_model is not None:
            selection_model.clearSelection()
        self.table.setCurrentIndex(QModelIndex())
        self.results_model.replace_page(rows)
        if selected_code is not None:
            self._select_stock_code(selected_code)

    def _apply_filter_controls_for_query(self, query: DailyMarketTechnicalUniverseV4Query) -> None:
        self._ensure_rule_filters(query.method_rule_keys)
        self._set_filter_controls(query)

    def _set_page_controls(self) -> None:
        query = self._query
        page = self._page
        self.previous_button.setEnabled(
            query is not None
            and page is not None
            and query.page_index > 0
            and not self._closing
        )
        self.next_button.setEnabled(
            query is not None
            and page is not None
            and query.page_index + 1 < page.page_count
            and not self._closing
        )
        self.apply_button.setEnabled(query is not None and not self._closing)
        self.open_button.setEnabled(
            query is not None and page is not None and bool(page.rows) and not self._closing
        )
        self.add_comparison_button.setEnabled(
            query is not None and page is not None and bool(page.rows) and not self._closing
        )
        self.clear_comparison_button.setEnabled(bool(self._comparison_basket) and not self._closing)
        self.compare_button.setEnabled(
            2 <= len(self._comparison_basket) <= 256 and not self._closing
        )
        self.bookmark_button.setEnabled(
            query is not None and page is not None and bool(page.rows) and not self._closing
        )

    def _selected_row(self) -> DailyMarketTechnicalParentV4Row | None:
        selected = self.table.selectionModel().selectedRows()
        if len(selected) != 1:
            return None
        value = self.results_model.row_at(selected[0].row())
        return value if isinstance(value, DailyMarketTechnicalParentV4Row) else None

    def _emit_selected_stock(self, value: object) -> None:
        if (
            not isinstance(value, tuple)
            or len(value) != 3
            or not isinstance(value[0], DailyMarketTechnicalUniverseV4Query)
            or not isinstance(value[1], DailyMarketTechnicalParentV4Row)
            or not isinstance(value[2], DailyMarketTechnicalUniverseV4Stock)
        ):
            self.status.setText("個股保存證據回傳格式不符；目前來源保留。")
            return
        query, row, stock = value
        self.stockSelected.emit((query, row, stock))
        self.status.setText(
            f"已核驗 {row.stock_code} 原保存證據；個股畫面收到來源 query、row 與 strict snapshot。"
        )

    @staticmethod
    def _parse_stock_filter(text: str) -> tuple[str, ...]:
        if len(text) > _MAX_STOCK_FILTER_TEXT_LENGTH:
            raise ValueError("股票代碼清單超出欄位上限")
        if not text.strip():
            return ()
        raw = text.replace("，", ",")
        parts = raw.split(",")
        if any(not part.strip() for part in parts):
            raise ValueError("股票代碼清單不可有空欄位")
        pieces = tuple(part.strip().upper() for part in parts)
        if len(pieces) > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS:
            raise ValueError("股票代碼不可超過 100,000 檔")
        if any(_STOCK_CODE_RE.fullmatch(code) is None for code in pieces):
            raise ValueError("股票代碼須為 1 至 16 個英文字母或數字")
        if len(set(pieces)) != len(pieces):
            raise ValueError("股票代碼不可重複")
        return tuple(sorted(pieces))


__all__ = ["DailyMarketTechnicalUniverseV4View", "ProductionRequestFactory"]
