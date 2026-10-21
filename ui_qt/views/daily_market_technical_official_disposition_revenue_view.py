"""F12 月營收／F17 保存來源全母體研究介面。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Literal, cast
from uuid import uuid4

from PySide6.QtCore import QModelIndex, Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from data_module.daily_market_monthly_revenue_read_session_v1 import (
    DailyMarketMonthlyRevenueSourceReferenceV2,
)
from app_module.daily_market_technical_method_contract_v4 import (
    DAILY_MARKET_TECHNICAL_RULE_KEYS_V4,
)
from app_module.daily_market_technical_official_disposition_bundle_catalog_v1 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_CATALOG_DEFAULT_LIMIT,
    DailyMarketTechnicalOfficialDispositionBundleCatalogEntryV1,
    DailyMarketTechnicalOfficialDispositionBundleCatalogPageV1,
    DailyMarketTechnicalOfficialDispositionBundleCatalogV1,
)
from app_module.daily_market_technical_official_disposition_ma_query_v1 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_PAGE_SIZE,
    DailyMarketTechnicalOfficialDispositionMaSortClauseV1,
    MaState,
    UnknownPolicy,
)
from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
    DailyMarketTechnicalOfficialDispositionSortClauseV1,
    DailyMarketTechnicalRuleStateFilterV4,
)
from app_module.daily_market_technical_official_disposition_query_v1 import (
    DailyMarketTechnicalOfficialDispositionQueryV1,
    RowScope,
)
from app_module.daily_market_technical_official_disposition_revenue_bookmark_v1 import (
    DailyMarketTechnicalOfficialDispositionRevenueBookmarkV1,
)
from app_module.daily_market_technical_official_disposition_revenue_query_v1 import (
    DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1,
    DailyMarketTechnicalOfficialDispositionRevenueQueryPageV1,
    DailyMarketTechnicalOfficialDispositionRevenueQueryV1,
    DailyMarketTechnicalOfficialDispositionRevenueResultRowV1,
    DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV1,
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_MAX_PAGE_SIZE_V1,
)
from app_module.daily_market_technical_official_disposition_revenue_source_v1 import (
    DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1,
    open_daily_market_technical_official_disposition_revenue_bundle_source_v1,
    reopen_daily_market_technical_official_disposition_revenue_from_recipe_v1,
)
from app_module.daily_market_technical_universe_v4_query import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS,
)
from ui_qt.models.saved_research_page_table_model import (
    SavedResearchPageTableModel,
    SavedResearchTableRow,
)
from ui_qt.technical_official_revenue_research_presenter import (
    format_technical_official_revenue_counts_v1,
    format_technical_official_revenue_research_row_v1,
    revenue_row_cells_v1,
)
from ui_qt.workers.task_worker import TaskWorker
from ui_qt.workers.revenue_source_actor_v2 import RevenueSourceActorV2, ClosableHandle
from data_module.daily_monthly_revenue_cohort import DailyMonthlyRevenueCohortPin, DailyMonthlyRevenueCohortReader
from data_module.recommendation_current_fundamental_provider import RecommendationCurrentFundamentalProvider
from app_module.daily_market_technical_official_disposition_revenue_query_v2 import (
    DailyMarketTechnicalOfficialDispositionRevenueQueryV2,
    DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2,
    DailyMarketTechnicalOfficialDispositionRevenueQueryPageV2,
    DailyMarketTechnicalOfficialDispositionRevenueResultRowV2,
    DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV2,
    DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2,
)
from app_module.daily_market_technical_official_disposition_revenue_source_v2 import (
    DailyMarketTechnicalOfficialDispositionRevenueExactReadV2,
    DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2,
    open_daily_market_technical_official_disposition_revenue_bundle_source_v2,
    reopen_daily_market_technical_official_disposition_revenue_from_recipe_v2,
)
from app_module.daily_market_technical_official_disposition_revenue_bookmark_v2 import DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2
from app_module.daily_market_technical_official_disposition_revenue_archived_recipe_v3 import (
    DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3,
)
from app_module.daily_market_technical_official_disposition_revenue_archived_source_v3 import (
    DailyMarketTechnicalOfficialDispositionRevenueArchivedExactReadV3,
    open_daily_market_technical_official_disposition_revenue_archived_bundle_source_v3,
    reopen_daily_market_technical_official_disposition_revenue_archived_from_recipe_v3,
)
from app_module.daily_market_technical_official_disposition_revenue_archived_bookmark_v3 import (
    DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3,
    archived_revenue_query_matches_recipe_v3,
)
from app_module.daily_market_technical_official_disposition_revenue_archived_storage_v3 import (
    ArchivedRevenueResearchStorageV3,
    prepare_archived_revenue_research_storage_v3,
)
from ui_qt.technical_official_revenue_research_presenter_v2 import (
    format_technical_official_revenue_research_row_v2,
    format_technical_official_revenue_counts_v2,
    revenue_row_cells_v2,
)
from ui_qt.views.revenue_stock_research_origin import RevenueStockResearchOrigin

_RecipeBase = DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1 | DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2
_Recipe = _RecipeBase | DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3
_ExactDaily = DailyMarketTechnicalOfficialDispositionRevenueExactReadV2 | DailyMarketTechnicalOfficialDispositionRevenueArchivedExactReadV3
_Query = DailyMarketTechnicalOfficialDispositionRevenueQueryV1 | DailyMarketTechnicalOfficialDispositionRevenueQueryV2
_Result = DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV1 | DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV2
_PageRequest = DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1 | DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2
_Page = DailyMarketTechnicalOfficialDispositionRevenueQueryPageV1 | DailyMarketTechnicalOfficialDispositionRevenueQueryPageV2
_Row = DailyMarketTechnicalOfficialDispositionRevenueResultRowV1 | DailyMarketTechnicalOfficialDispositionRevenueResultRowV2


@dataclass(frozen=True, slots=True)
class DailyRevenueSourceConfigV2:
    """正常組裝注入固定接受與 reader，開啟前不讀取每日 catalog。"""

    provider: RecommendationCurrentFundamentalProvider
    protected_roots: tuple[Path, ...]
    reader: DailyMonthlyRevenueCohortReader | None = None
    reader_factory: Callable[[datetime], DailyMonthlyRevenueCohortReader] | None = None
    exact_reader_factory: Callable[[DailyMonthlyRevenueCohortPin, datetime], DailyMonthlyRevenueCohortReader] | None = None
    use_archived_sources: bool = False
    source_roots: tuple[Path, ...] = ()
    source_roots_provider: Callable[[], tuple[Path, ...]] | None = None


def _row_detail(row: _Row) -> str:
    if type(row) is DailyMarketTechnicalOfficialDispositionRevenueResultRowV2:
        return format_technical_official_revenue_research_row_v2(row)
    return format_technical_official_revenue_research_row_v1(row)


_STATES: tuple[MaState, ...] = ("match", "no_match", "unknown")
_STATE_LABELS = {"match": "符合", "no_match": "不符合", "unknown": "未知"}
_SCOPE_ORDER: tuple[RowScope, ...] = (
    "included_processed", "included_pending", "excluded",
)
_SCOPE_LABELS = {
    "included_processed": "納入且已處理",
    "included_pending": "納入但待處理",
    "excluded": "明示排除",
}
_MARKET_STATES = ("assigned_twse", "assigned_tpex", "unknown")
_MARKET_LABELS = {
    "assigned_twse": "上市（TWSE）",
    "assigned_tpex": "上櫃（TPEx）",
    "unknown": "未知",
}
_DISPOSAL_STATES = (
    "reported_upcoming", "reported_active", "reported_elapsed_only", "unknown",
)
_DISPOSAL_LABELS = {
    "reported_upcoming": "已公告、尚未生效",
    "reported_active": "公告處置中",
    "reported_elapsed_only": "僅有已經過的處置紀錄",
    "unknown": "未知",
}
_RULE_LABELS = {
    "ma5_20_golden_cross": "MA5／MA20 金叉",
    "kd_golden_cross": "K／D 金叉",
    "macd_golden_cross": "MACD 金叉",
    "volume_ratio_20_including_current": "量能比 20（含當日）",
    "volume_ratio_5_including_current": "量能比 5（含當日）",
}
_STOCK_CODE_RE = re.compile(r"^[A-Z0-9]{1,16}$")
_MAX_STOCK_FILTER_CHARS = DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS * 17 - 1
_REFERENCE_MAX_BYTES = 8 * 1024 * 1024
_WORKERS: set[TaskWorker] = set()

_SORT_FIELD_LABELS: tuple[tuple[str, str], ...] = (
    ("stock_code", "股票代碼"),
    ("monthly_revenue_yoy_percent", "月營收 YoY 百分比"),
    ("ma_alignment_state", "四均線排列狀態"),
    ("decision_date", "決策日期"),
    ("latest_feature_date", "最新技術觀測日"),
    ("raw_row_count", "已保存技術列數"),
    ("market_assignment.state", "市場狀態"),
    ("market_assignment.snapshot_observed_at", "市場觀察時間"),
    ("official_disposal.state", "處置狀態"),
    ("official_disposal.observed_at", "處置觀察時間"),
    ("official_disposal.observed_date", "處置觀察日期"),
)
_REVENUE_TABLE_HEADERS: tuple[str, ...] = (
    "股票代碼", "技術條件", "四均線", "YoY 資料", "YoY 百分比", "複合結果",
)
for _rule_key in DAILY_MARKET_TECHNICAL_RULE_KEYS_V4:
    for _metric in ("ratio", "numerator", "denominator"):
        _SORT_FIELD_LABELS += ((f"{_rule_key}.{_metric}", f"{_RULE_LABELS[_rule_key]}｜{_metric}"),)


def _parse_stock_codes(raw: object, *, was_truncated: bool) -> tuple[str, ...]:
    if was_truncated:
        raise ValueError("technical_official_revenue_view_stock_filter_too_long")
    if not isinstance(raw, str) or len(raw) > _MAX_STOCK_FILTER_CHARS:
        raise ValueError("technical_official_revenue_view_stock_filter_invalid")
    if not raw.strip():
        raise ValueError("technical_official_revenue_view_stock_filter_empty")
    groups = re.split(r"[,，]", raw)
    if any(not item.strip() for item in groups):
        raise ValueError("technical_official_revenue_view_stock_filter_invalid")
    codes = tuple(token for group in groups for token in group.split())
    if not codes or len(codes) > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS:
        raise ValueError("technical_official_revenue_view_stock_filter_limit")
    if any(_STOCK_CODE_RE.fullmatch(code) is None for code in codes):
        raise ValueError("technical_official_revenue_view_stock_code_invalid")
    if len(set(codes)) != len(codes):
        raise ValueError("technical_official_revenue_view_stock_code_duplicate")
    return tuple(sorted(codes))


class _StockCodeLineEdit(QLineEdit):
    """防止 Qt 靜默截短代碼輸入。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._was_truncated = False
        self.setMaxLength(_MAX_STOCK_FILTER_CHARS)
        self.inputRejected.connect(self._mark_truncated)
        self.textChanged.connect(lambda _text: setattr(self, "_was_truncated", False))

    @property
    def was_truncated(self) -> bool:
        return self._was_truncated

    def setText(self, text: str) -> None:
        super().setText(text)
        self._was_truncated = len(text) > self.maxLength()

    def _mark_truncated(self) -> None:
        self._was_truncated = True


@dataclass(frozen=True, slots=True)
class _SourceChoice:
    bundle_output_root: str
    bundle_identity_sha256: str
    manifest_sha256: str
    monthly_reference_json: str
    mode: Literal["legacy_v1", "daily_v2", "daily_archived_v3"] = "legacy_v1"


@dataclass(frozen=True, slots=True)
class _Conditions:
    row_scope_filter: tuple[RowScope, ...]
    rule_state_filters: tuple[DailyMarketTechnicalRuleStateFilterV4, ...]
    combine_mode: Literal["AND", "OR"]
    market_assignment_states: tuple[str, ...]
    official_disposal_states: tuple[str, ...]
    outer_stock_filter_mode: Literal["all", "explicit_codes"]
    outer_stock_codes: tuple[str, ...]
    ma_states: tuple[MaState, ...] | None
    minimum_yoy_percent: Decimal | None
    condition_combine_mode: Literal["AND", "OR"]
    unknown_policy: UnknownPolicy
    sort_clauses: tuple[DailyMarketTechnicalOfficialDispositionMaSortClauseV1, ...]


@dataclass(frozen=True, slots=True)
class _OpenedQuery:
    source: _SourceChoice
    recipe: _Recipe
    query: _Query
    result: _Result
    page_request: _PageRequest
    page: _Page
    selected_stock_code: str | None = None


def _project_revenue_page_table_rows(
    rows: tuple[_Row, ...] | None,
) -> tuple[SavedResearchTableRow[_Row], ...]:
    """先完成一頁的文字投影，讓表格驗證失敗不會改動目前研究狀態。"""

    if rows is None:
        return ()
    if type(rows) is not tuple or len(rows) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_MAX_PAGE_SIZE_V1:
        raise ValueError("technical_official_revenue_view_page_limit_exceeded")
    projected: list[SavedResearchTableRow[_Row]] = []
    for row in rows:
        cells = revenue_row_cells_v2(row) if type(row) is DailyMarketTechnicalOfficialDispositionRevenueResultRowV2 else revenue_row_cells_v1(row)
        if type(cells) is not tuple or len(cells) != len(_REVENUE_TABLE_HEADERS):
            raise ValueError("technical_official_revenue_view_table_projection_invalid")
        details = _row_detail(row)
        tooltips = tuple(
            f"{header}：{cell}\n\n雙擊查看完整已保存事實。\n{details}"
            for header, cell in zip(_REVENUE_TABLE_HEADERS, cells)
        )
        projected.append(SavedResearchTableRow(row.stock_code, row, cells, tooltips))
    return tuple(projected)


@dataclass(frozen=True, slots=True)
class _BasketItem:
    stock_code: str
    page_index: int
    scope_identity_sha256: str


def _scope_identity(recipe: _Recipe) -> str:
    payload = _recipe_base(recipe).to_dict()
    payload.pop("page_index")
    payload.pop("page_size")
    payload.pop("recipe_identity_sha256")
    payload.pop("page_request_json", None)
    if type(recipe) is DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3:
        payload["archive_descriptor_sha256"] = recipe.archive_artifact_descriptor_external_sha256
        payload["archive_reference_sha256"] = recipe.archive_reference_external_sha256
    return hashlib.sha256(json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def _recipe_base(recipe: _Recipe) -> _RecipeBase:
    if type(recipe) is DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3:
        return recipe.base_recipe
    return recipe


def _recipe_for_page(
    recipe: _Recipe,
    *,
    page_index: int,
    page_size: int | None = None,
) -> _Recipe:
    if type(recipe) is DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3:
        return recipe.with_page(page_index=page_index, page_size=recipe.base_recipe.page_size if page_size is None else page_size)
    if type(recipe) is DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2:
        query = DailyMarketTechnicalOfficialDispositionRevenueQueryV2.from_json(recipe.revenue_query_json)
        request = DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2.create(query, page_index=page_index, page_size=recipe.page_size if page_size is None else page_size)
        payload = recipe.to_dict()
        payload.update(page_index=request.page_index, page_size=request.page_size, page_request_json=request.to_json())
        payload.pop("recipe_identity_sha256")
        payload["recipe_identity_sha256"] = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        return DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2.from_dict(payload)
    return recipe.with_conditions(
        ma_states=recipe.ma_states,
        minimum_yoy_percent=recipe.minimum_yoy_percent,
        condition_combine_mode=recipe.condition_combine_mode,
        unknown_policy=recipe.unknown_policy,
        sort_clauses=recipe.sort_clauses,
        page_index=page_index,
        page_size=recipe.page_size if page_size is None else page_size,
    )


def _query_matches_recipe(
    query: _Query,
    recipe: _Recipe,
) -> bool:
    if type(recipe) is DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3:
        return type(query) is DailyMarketTechnicalOfficialDispositionRevenueQueryV2 and archived_revenue_query_matches_recipe_v3(query, recipe)
    if type(recipe) is DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2:
        return type(query) is DailyMarketTechnicalOfficialDispositionRevenueQueryV2 and query.to_json() == recipe.revenue_query_json
    if type(query) is not DailyMarketTechnicalOfficialDispositionRevenueQueryV1:
        return False
    return (
        query.ma_query.f17_query.to_json() == recipe.f17_query_json
        and query.ma_query.ma_states == recipe.ma_states
        and query.minimum_yoy_percent == recipe.minimum_yoy_percent
        and query.condition_combine_mode == recipe.condition_combine_mode
        and query.unknown_policy == recipe.unknown_policy
        and tuple(item.to_dict() for item in query.sort_clauses)
        == tuple(item.to_dict() for item in recipe.sort_clauses)
    )


def _read_reference_file(path_text: str) -> DailyMarketMonthlyRevenueSourceReferenceV2:
    path = Path(path_text)
    if not path.is_absolute() or not path.is_file():
        raise ValueError("technical_official_revenue_view_monthly_reference_missing")
    stat = path.stat()
    if stat.st_size <= 0 or stat.st_size > _REFERENCE_MAX_BYTES:
        raise ValueError("technical_official_revenue_view_monthly_reference_size_invalid")
    raw = path.read_bytes()
    if len(raw) != stat.st_size:
        raise ValueError("technical_official_revenue_view_monthly_reference_changed")
    return DailyMarketMonthlyRevenueSourceReferenceV2.from_json(raw)


def _new_operation_root(parent: Path, cancel_callback: Callable[[], object] | None) -> Path:
    if cancel_callback is not None:
        cancelled = cancel_callback()
        if type(cancelled) is not bool:
            raise ValueError("technical_official_revenue_view_cancel_callback_invalid")
        if cancelled:
            raise ValueError("technical_official_revenue_view_cancelled")
    if not parent.is_absolute() or not parent.is_dir():
        raise ValueError("technical_official_revenue_view_operation_parent_invalid")
    return parent / f"f12-revenue-{uuid4().hex}"


def _open_from_bundle(
    source: _SourceChoice,
    conditions: _Conditions,
    operation_parent: Path,
    *,
    page_index: int,
    page_size: int,
    cancel_callback: Callable[[], object] | None,
) -> _OpenedQuery:
    from app_module.daily_market_technical_official_disposition_revenue_source_v1 import (
        open_daily_market_technical_official_disposition_revenue_bundle_source_v1,
    )

    exact = open_daily_market_technical_official_disposition_revenue_bundle_source_v1(
        bundle_output_root=source.bundle_output_root,
        bundle_identity_sha256=source.bundle_identity_sha256,
        expected_manifest_sha256=source.manifest_sha256,
        row_scope_filter=conditions.row_scope_filter,
        monthly_source_reference=source.monthly_reference_json,
        operation_root=_new_operation_root(operation_parent, cancel_callback),
        rule_state_filters=conditions.rule_state_filters,
        combine_mode=conditions.combine_mode,
        market_assignment_states=conditions.market_assignment_states,
        official_disposal_states=conditions.official_disposal_states,
        outer_stock_filter_mode=conditions.outer_stock_filter_mode,
        outer_stock_codes=conditions.outer_stock_codes,
        f17_sort_clauses=(DailyMarketTechnicalOfficialDispositionSortClauseV1("stock_code", "asc"),),
        ma_states=conditions.ma_states,
        minimum_yoy_percent=conditions.minimum_yoy_percent,
        condition_combine_mode=conditions.condition_combine_mode,
        unknown_policy=conditions.unknown_policy,
        sort_clauses=conditions.sort_clauses,
        page_index=page_index,
        page_size=page_size,
        cancel_callback=cancel_callback,
    )
    try:
        source_choice = _SourceChoice(
            exact.f17_query.bundle_output_root,
            exact.f17_query.bundle_identity_sha256,
            exact.f17_query.expected_manifest_sha256,
            exact.monthly_source_reference.to_json(),
        )
        recipe = exact.saved_recipe
        opened = _OpenedQuery(
            source_choice,
            recipe,
            exact.query,
            exact.result,
            exact.page_request,
            exact.page,
        )
        if cancel_callback is not None:
            cancelled = cancel_callback()
            if type(cancelled) is not bool:
                raise ValueError("technical_official_revenue_view_cancel_callback_invalid")
            if cancelled:
                raise ValueError("technical_official_revenue_view_cancelled")
        return opened
    finally:
        exact.close()


def _open_from_recipe(
    recipe: DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1,
    operation_parent: Path,
    *,
    cancel_callback: Callable[[], object] | None,
) -> _OpenedQuery:
    exact = reopen_daily_market_technical_official_disposition_revenue_from_recipe_v1(
        recipe,
        operation_root=_new_operation_root(operation_parent, cancel_callback),
        cancel_callback=cancel_callback,
    )
    try:
        opened = _OpenedQuery(
            _SourceChoice(
                exact.f17_query.bundle_output_root,
                exact.f17_query.bundle_identity_sha256,
                exact.f17_query.expected_manifest_sha256,
                exact.monthly_source_reference.to_json(),
            ),
            exact.saved_recipe,
            exact.query,
            exact.result,
            exact.page_request,
            exact.page,
        )
        if cancel_callback is not None:
            cancelled = cancel_callback()
            if type(cancelled) is not bool:
                raise ValueError("technical_official_revenue_view_cancel_callback_invalid")
            if cancelled:
                raise ValueError("technical_official_revenue_view_cancelled")
        return opened
    finally:
        exact.close()


def _restore_bookmark(
    bookmark: DailyMarketTechnicalOfficialDispositionRevenueBookmarkV1,
    operation_parent: Path,
    *,
    cancel_callback: Callable[[], object] | None,
) -> _OpenedQuery:
    exact = reopen_daily_market_technical_official_disposition_revenue_from_recipe_v1(
        bookmark.saved_recipe,
        operation_root=_new_operation_root(operation_parent, cancel_callback),
        cancel_callback=cancel_callback,
    )
    try:
        bookmark.verify_exact_row(exact, cancel_callback=cancel_callback)
        opened = _OpenedQuery(
            _SourceChoice(
                exact.f17_query.bundle_output_root,
                exact.f17_query.bundle_identity_sha256,
                exact.f17_query.expected_manifest_sha256,
                exact.monthly_source_reference.to_json(),
            ),
            exact.saved_recipe,
            exact.query,
            exact.result,
            exact.page_request,
            exact.page,
            bookmark.selected_stock_code,
        )
        if cancel_callback is not None:
            cancelled = cancel_callback()
            if type(cancelled) is not bool:
                raise ValueError("technical_official_revenue_view_cancel_callback_invalid")
            if cancelled:
                raise ValueError("technical_official_revenue_view_cancelled")
        return opened
    finally:
        exact.close()


def _read_comparison_rows(
    result: DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV1,
    recipe: DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1,
    basket: tuple[_BasketItem, ...],
    *,
    cancel_callback: Callable[[], object] | None,
) -> tuple[DailyMarketTechnicalOfficialDispositionRevenueResultRowV1, ...]:
    if not 2 <= len(basket) <= 5:
        raise ValueError("technical_official_revenue_view_comparison_count_invalid")
    expected_scope = _scope_identity(recipe)
    if any(item.scope_identity_sha256 != expected_scope for item in basket):
        raise ValueError("technical_official_revenue_view_comparison_scope_mismatch")
    if not _query_matches_recipe(result.query, recipe):
        raise ValueError("technical_official_revenue_view_comparison_query_mismatch")
    rows_by_code: dict[str, DailyMarketTechnicalOfficialDispositionRevenueResultRowV1] = {}
    pages: dict[int, DailyMarketTechnicalOfficialDispositionRevenueQueryPageV1] = {}
    for item in basket:
        if cancel_callback is not None:
            cancelled = cancel_callback()
            if type(cancelled) is not bool:
                raise ValueError("technical_official_revenue_view_cancel_callback_invalid")
            if cancelled:
                raise ValueError("technical_official_revenue_view_cancelled")
        page = pages.get(item.page_index)
        if page is None:
            page = result.read_page(item.page_index, recipe.page_size, cancel_callback=cancel_callback)
            pages[item.page_index] = page
        row = next((candidate for candidate in page.rows if candidate.stock_code == item.stock_code), None)
        if row is None:
            raise ValueError("technical_official_revenue_view_comparison_stock_missing")
        rows_by_code[item.stock_code] = row
    compared = tuple(rows_by_code[item.stock_code] for item in basket)
    if len(compared) != len(basket):
        raise ValueError("technical_official_revenue_view_comparison_duplicate")
    if cancel_callback is not None:
        cancelled = cancel_callback()
        if type(cancelled) is not bool:
            raise ValueError("technical_official_revenue_view_cancel_callback_invalid")
        if cancelled:
            raise ValueError("technical_official_revenue_view_cancelled")
    return compared


def _read_page_from_result(
    source: _SourceChoice,
    recipe: DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV1,
    result: DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV1,
    *,
    page_index: int,
    page_size: int,
    cancel_callback: Callable[[], object] | None,
) -> _OpenedQuery:
    """從已 exact 核驗的全域 result 讀一頁，不重新開來源或重做 full-N join。"""

    if type(result) is not DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV1:
        raise ValueError("technical_official_revenue_view_result_invalid")
    if not _query_matches_recipe(result.query, recipe):
        raise ValueError("technical_official_revenue_view_result_query_mismatch")
    request = DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1.create(
        result.query,
        page_index=page_index,
        page_size=page_size,
    )
    page = result.read_page_request(request, cancel_callback=cancel_callback)
    target_recipe = _recipe_for_page(recipe, page_index=page_index, page_size=page_size)
    if cancel_callback is not None:
        cancelled = cancel_callback()
        if type(cancelled) is not bool:
            raise ValueError("technical_official_revenue_view_cancel_callback_invalid")
        if cancelled:
            raise ValueError("technical_official_revenue_view_cancelled")
    return _OpenedQuery(source, target_recipe, result.query, result, request, page)


class _RevenueStockCodeLineEdit(_StockCodeLineEdit):
    pass


def _exact_v2(handle: ClosableHandle) -> _ExactDaily:
    if type(handle) is DailyMarketTechnicalOfficialDispositionRevenueExactReadV2:
        return handle
    if type(handle) is DailyMarketTechnicalOfficialDispositionRevenueArchivedExactReadV3:
        return handle
    raise ValueError("technical_official_revenue_view_v2_handle_invalid")


def _project_exact_v2(handle: ClosableHandle, cancel: Callable[[], bool], selected: str | None = None) -> _OpenedQuery:
    exact = _exact_v2(handle)
    page = exact.page
    # 候選提交前完成投影驗證，失敗時 actor 仍保留原來源。
    _project_revenue_page_table_rows(page.rows)
    if cancel():
        raise ValueError("technical_official_revenue_view_cancelled")
    return _OpenedQuery(
        _SourceChoice(exact.f17_query.bundle_output_root, exact.f17_query.bundle_identity_sha256,
                      exact.f17_query.expected_manifest_sha256, exact.monthly_reference.to_json(),
                      "daily_archived_v3" if type(exact) is DailyMarketTechnicalOfficialDispositionRevenueArchivedExactReadV3 else "daily_v2"),
        exact.saved_recipe, exact.query, exact.result, exact.request, page, selected,
    )


def _open_daily_v2(
    source: _SourceChoice, conditions: _Conditions, config: DailyRevenueSourceConfigV2,
    operation_parent: Path, artifact_root: Path, page_size: int,
    cancel: Callable[[], bool], *, reader: DailyMonthlyRevenueCohortReader | None = None,
) -> _ExactDaily:
    fixed_reader = config.reader if reader is None else reader
    provider = config.provider if fixed_reader is None else _provider_with_exact_reader(config.provider, fixed_reader)
    factory: Callable[..., _ExactDaily] = open_daily_market_technical_official_disposition_revenue_bundle_source_v2
    extra: dict[str, object] = {}
    if config.use_archived_sources:
        storage = _archived_storage(config, artifact_root, source, operation_parent)
        artifact_root = storage.monthly_reference_artifact_root
        factory = open_daily_market_technical_official_disposition_revenue_archived_bundle_source_v3
        extra = dict(archive_parent=storage.raw_archive_parent,
                     archived_reference_artifact_root=storage.archived_reference_artifact_root,
                     archived_artifact_id=f"ui-archive-{uuid4().hex}")
    return factory(
        **extra,
        bundle_output_root=source.bundle_output_root, bundle_identity_sha256=source.bundle_identity_sha256,
        expected_manifest_sha256=source.manifest_sha256, row_scope_filter=conditions.row_scope_filter,
        operation_root=_new_operation_root(operation_parent, cancel), monthly_provider=provider,
        monthly_reference_artifact_root=artifact_root, artifact_id=f"ui-{uuid4().hex}",
        protected_roots=config.protected_roots, daily_monthly_cohort_reader=fixed_reader,
        daily_monthly_cohort_reader_factory=config.reader_factory if fixed_reader is None else None,
        rule_state_filters=conditions.rule_state_filters, combine_mode=conditions.combine_mode,
        market_assignment_states=conditions.market_assignment_states, official_disposal_states=conditions.official_disposal_states,
        outer_stock_filter_mode=conditions.outer_stock_filter_mode, outer_stock_codes=conditions.outer_stock_codes,
        f17_sort_clauses=(DailyMarketTechnicalOfficialDispositionSortClauseV1("stock_code", "asc"),),
        ma_states=conditions.ma_states, minimum_yoy_percent=conditions.minimum_yoy_percent,
        condition_combine_mode=conditions.condition_combine_mode, unknown_policy=conditions.unknown_policy,
        sort_clauses=tuple(DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2(item.field, item.direction) for item in conditions.sort_clauses),
        page_index=0, page_size=page_size, cancel_callback=cancel,
    )


def _archived_storage(
    config: DailyRevenueSourceConfigV2, root: Path, source: _SourceChoice, operation_parent: Path,
) -> ArchivedRevenueResearchStorageV3:
    """固定 binding 只提供保護目錄；來源資格仍由 application exact reader 核驗。"""
    extra = config.source_roots_provider() if config.source_roots_provider is not None else ()
    return prepare_archived_revenue_research_storage_v3(
        root, protected_roots=config.protected_roots,
        source_roots=(*config.source_roots, *extra, config.provider.db_file.parent,
                      config.provider.output_root, config.provider.monthly_source_root,
                      Path(source.bundle_output_root)),
        operation_root_parent=operation_parent,
    )


def _provider_with_exact_reader(provider: RecommendationCurrentFundamentalProvider, reader: DailyMonthlyRevenueCohortReader) -> RecommendationCurrentFundamentalProvider:
    if provider.daily_source_snapshot_reader is reader:
        return provider
    paired = provider.with_daily_source_snapshot_reader(reader)
    if type(paired) is not RecommendationCurrentFundamentalProvider or paired.daily_source_snapshot_reader is not reader:
        raise ValueError("technical_official_revenue_view_provider_reader_mismatch")
    return paired


class DailyMarketTechnicalOfficialDispositionRevenueView(QWidget):
    """以明示保存 F17 bundle 與月營收 V2 封存來源進行全母體 YoY 研究。"""

    stockSelected = Signal(object)
    stockResearchRequested = Signal(object)
    bookmarkPrepared = Signal(object)
    comparisonReady = Signal(object)
    operationSettled = Signal(str, bool)

    def __init__(
        self,
        bundle_output_root: str | Path | None = None,
        monthly_reference_path: str | Path | None = None,
        operation_root_parent: str | Path | None = None,
        parent: QWidget | None = None,
        *,
        daily_source_config_v2: DailyRevenueSourceConfigV2 | None = None,
        monthly_artifact_root: str | Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.bundle_output_root = Path(bundle_output_root) if bundle_output_root is not None else None
        self.monthly_reference_path = Path(monthly_reference_path) if monthly_reference_path is not None else None
        self.operation_root_parent = Path(operation_root_parent) if operation_root_parent is not None else None
        self.daily_source_config_v2 = daily_source_config_v2
        self.monthly_artifact_root = Path(monthly_artifact_root) if monthly_artifact_root is not None else None
        self._source_actor_v2: RevenueSourceActorV2 | None = None
        self._v2_busy = False
        self._catalog_cursor: str | None = None
        self._catalog_entries: tuple[DailyMarketTechnicalOfficialDispositionBundleCatalogEntryV1, ...] = ()
        self._source: _SourceChoice | None = None
        self._recipe: _Recipe | None = None
        self._query: _Query | None = None
        self._result: _Result | None = None
        self._page_request: _PageRequest | None = None
        self._page: _Page | None = None
        self._selected_row: _Row | None = None
        self._basket: list[_BasketItem] = []
        self._busy_worker: TaskWorker | None = None
        self._live_workers: set[TaskWorker] = set()
        self._revision = 0
        self._busy_token = 0
        self._worker_kind = ""
        self._worker_apply: Callable[[object], None] | None = None
        self._closing = False
        self._build_ui()
        self._set_status(
            "每日來源設定已載入；請明示 F17 保存資料夾、版本參照保存資料夾與 operation 暫存資料夾，再選保存版本核驗。"
            if self.daily_source_config_v2 is not None else
            "候選清單只讀保存來源 manifest，尚未核驗。請選擇保存資料夾與月營收 V2 參照。"
            if self.bundle_output_root is None or self.monthly_reference_path is None
            else "來源僅為明示路徑；按更新清單並選取保存版本後才進行核驗。"
        )

    @property
    def current_result(self) -> _Result | None:
        return self._result

    @property
    def current_query(self) -> _Query | None:
        return self._query

    @property
    def current_page(self) -> _Page | None:
        return self._page

    @property
    def current_recipe(self) -> _Recipe | None:
        return self._recipe

    @property
    def current_selected_row(self) -> _Row | None:
        return self._selected_row

    @property
    def active_worker(self) -> TaskWorker | None:
        return self._busy_worker

    @property
    def comparison_basket(self) -> tuple[tuple[str, int], ...]:
        return tuple((item.stock_code, item.page_index) for item in self._basket)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        self.page_scroll = QScrollArea(self)
        self.page_scroll.setObjectName("technicalOfficialRevenuePageScroll")
        self.page_scroll.setWidgetResizable(True)
        self.page_body = QWidget()
        self.page_body.setObjectName("technicalOfficialRevenuePageBody")
        body = QVBoxLayout(self.page_body)
        body.setContentsMargins(5, 6, 5, 6)
        self.page_scroll.setWidget(self.page_body)
        outer.addWidget(self.page_scroll, 1)

        heading = QLabel("官方來源與月營收 YoY 全母體研究")
        heading.setStyleSheet("font-size: 18px; font-weight: 600;")
        body.addWidget(heading)
        self.qualification_label = QLabel(
            "月營收僅 current-observed；官方與月營收 available_at 未知；不具歷史 PIT 資格。"
            "每次查詢、翻頁或收藏重開都使用明示保存版本，不自動尋找 latest，也不執行 producer。"
        )
        self.qualification_label.setWordWrap(True)
        if self.daily_source_config_v2 is not None:
            self.qualification_label.setText("每日快照沿固定接受選定：月營收 cohort 小時可用；官方／整體 F17 可用時間仍未知，current-only、非歷史 PIT。翻頁與收藏重開沿原版本，不重新選批次。")
        body.addWidget(self.qualification_label)

        source_box = QGroupBox("明示保存來源")
        source_layout = QVBoxLayout(source_box)
        self.root_label = QLabel(str(self.bundle_output_root) if self.bundle_output_root else "尚未選擇")
        self.root_label.setObjectName("technicalOfficialRevenueBundleRoot")
        self.root_label.setWordWrap(True)
        self.monthly_reference_label = QLabel(str(self.monthly_reference_path) if self.monthly_reference_path else "尚未選擇月營收 V2 參照")
        self.monthly_reference_label.setObjectName("technicalOfficialRevenueMonthlyReference")
        self.monthly_reference_label.setWordWrap(True)
        self.operation_root_label = QLabel(str(self.operation_root_parent) if self.operation_root_parent else "尚未選擇 operation 暫存父資料夾")
        self.operation_root_label.setObjectName("technicalOfficialRevenueOperationRoot")
        self.operation_root_label.setWordWrap(True)
        source_layout.addWidget(self.root_label)
        source_layout.addWidget(self.monthly_reference_label)
        source_layout.addWidget(self.operation_root_label)
        archive_mode = self.daily_source_config_v2 is not None and self.daily_source_config_v2.use_archived_sources
        self.monthly_artifact_label = QLabel(str(self.monthly_artifact_root) if self.monthly_artifact_root else
            "需選擇研究保存資料夾；原件與版本一併保存，供收藏精確重開。" if archive_mode else
            "每日快照需選擇已存在的版本參照保存資料夾")
        self.monthly_artifact_label.setWordWrap(True)
        source_layout.addWidget(self.monthly_artifact_label)
        source_actions = QGridLayout()
        self.choose_root_button = QPushButton("選擇 F17 保存來源資料夾")
        self.choose_root_button.clicked.connect(self.choose_bundle_output_root)
        self.choose_reference_button = QPushButton("選擇月營收 V2 參照")
        self.choose_reference_button.clicked.connect(self.choose_monthly_reference)
        self.choose_operation_root_button = QPushButton("選擇 operation 暫存資料夾")
        self.choose_operation_root_button.clicked.connect(self.choose_operation_root_parent)
        self.choose_artifact_root_button = QPushButton("選擇研究保存資料夾" if archive_mode else "選擇每日快照參照保存資料夾")
        self.choose_artifact_root_button.clicked.connect(self.choose_monthly_artifact_root)
        self.choose_artifact_root_button.setVisible(self.daily_source_config_v2 is not None)
        self.monthly_artifact_label.setVisible(self.daily_source_config_v2 is not None)
        if self.daily_source_config_v2 is not None:
            self.monthly_reference_label.setText("使用已驗證的每日快照接受；按所選 F17 cutoff 選定完整 cohort。")
            self.choose_reference_button.setVisible(False)
        self.refresh_catalog_button = QPushButton("更新保存來源清單")
        self.refresh_catalog_button.clicked.connect(self.refresh_catalog)
        self.next_catalog_button = QPushButton("下一頁候選")
        self.next_catalog_button.clicked.connect(self.load_next_catalog_page)
        for row, button in enumerate((
            self.choose_root_button,
            self.choose_reference_button,
            self.choose_operation_root_button,
            self.choose_artifact_root_button,
            self.refresh_catalog_button,
            self.next_catalog_button,
        )):
            source_actions.addWidget(button, row, 0, 1, 2)
        source_layout.addLayout(source_actions)
        self.catalog_list = QListWidget()
        self.catalog_list.setObjectName("technicalOfficialRevenueCatalog")
        self.catalog_list.setMinimumHeight(105)
        source_layout.addWidget(self.catalog_list)
        self.open_candidate_button = QPushButton("核驗所選 F17 版本並執行全母體查詢")
        self.open_candidate_button.setMinimumHeight(36)
        self.open_candidate_button.clicked.connect(self.open_selected_candidate)
        source_layout.addWidget(self.open_candidate_button)
        body.addWidget(source_box)

        self.filter_panel = self._build_filter_panel()
        body.addWidget(self.filter_panel)
        action_grid = QGridLayout()
        self.apply_query_button = QPushButton("套用條件並全母體重新查詢")
        self.apply_query_button.clicked.connect(self.apply_filters)
        self.clear_filters_button = QPushButton("清除條件並恢復全母體")
        self.clear_filters_button.clicked.connect(self.clear_filters)
        self.cancel_button = QPushButton("取消目前工作")
        self.cancel_button.clicked.connect(self.cancel_current_operation)
        action_grid.addWidget(self.apply_query_button, 0, 0)
        action_grid.addWidget(self.clear_filters_button, 0, 1)
        action_grid.addWidget(self.cancel_button, 1, 0, 1, 2)
        body.addLayout(action_grid)

        self.summary_label = QLabel("尚無已核驗查詢結果。")
        self.summary_label.setObjectName("technicalOfficialRevenueCounts")
        self.summary_label.setWordWrap(True)
        body.addWidget(self.summary_label)

        self.results_stack = QStackedWidget()
        self.results_stack.setObjectName("technicalOfficialRevenueResultsStack")
        results_panel = QWidget()
        results_layout = QVBoxLayout(results_panel)
        self.results_table = QTableView()
        self.results_table.setObjectName("technicalOfficialRevenueTable")
        self.results_table.setMinimumHeight(270)
        self.results_table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.results_table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.results_table.setAlternatingRowColors(True)
        self.table_model: SavedResearchPageTableModel[_Row] = SavedResearchPageTableModel(
            _REVENUE_TABLE_HEADERS,
            maximum_page_size=DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_MAX_PAGE_SIZE_V1,
            parent=self,
        )
        self.results_table.setModel(self.table_model)
        self.results_table.clicked.connect(self._table_selection_changed)
        self.results_table.doubleClicked.connect(lambda _index: self.show_selected_detail())
        results_layout.addWidget(self.results_table)
        page_actions = QGridLayout()
        self.previous_page_button = QPushButton("上一頁")
        self.previous_page_button.clicked.connect(lambda: self.navigate_page(self._page_index() - 1))
        self.page_label = QLabel("第 0 頁")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.next_page_button = QPushButton("下一頁")
        self.next_page_button.clicked.connect(lambda: self.navigate_page(self._page_index() + 1))
        page_actions.addWidget(self.previous_page_button, 0, 0)
        page_actions.addWidget(self.page_label, 0, 1)
        page_actions.addWidget(self.next_page_button, 0, 2)
        results_layout.addLayout(page_actions)

        self.detail_button = QPushButton("查看已保存事實")
        self.detail_button.clicked.connect(self.show_selected_detail)
        self.add_comparison_button = QPushButton("加入跨頁比較")
        self.add_comparison_button.clicked.connect(self.add_selected_to_comparison)
        self.remove_comparison_button = QPushButton("移除所選比較")
        self.remove_comparison_button.clicked.connect(self.remove_selected_from_comparison)
        self.clear_comparison_button = QPushButton("清空比較")
        self.clear_comparison_button.clicked.connect(self.clear_comparison)
        self.compare_button = QPushButton("比較 2–5 檔")
        self.compare_button.clicked.connect(self.compare_basket)
        self.bookmark_button = QPushButton("保存原研究與選取股票")
        self.bookmark_button.clicked.connect(self.prepare_bookmark)
        actions = QGridLayout()
        for idx, widget in enumerate((
            self.detail_button,
            self.add_comparison_button,
            self.remove_comparison_button,
            self.clear_comparison_button,
            self.compare_button,
            self.bookmark_button,
        )):
            actions.addWidget(widget, idx // 2, idx % 2)
        results_layout.addLayout(actions)
        self.basket_label = QLabel("比較籃：0／5")
        self.basket_label.setWordWrap(True)
        results_layout.addWidget(self.basket_label)
        self.results_stack.addWidget(results_panel)

        detail_panel = QWidget()
        detail_layout = QVBoxLayout(detail_panel)
        self.detail_text = QPlainTextEdit()
        self.detail_text.setObjectName("technicalOfficialRevenueDetail")
        self.detail_text.setReadOnly(True)
        self.detail_text.setMinimumHeight(420)
        detail_layout.addWidget(self.detail_text, 1)
        self.audit_toggle = QCheckBox("展開完整來源欄位 JSON（稽核用）")
        self.audit_toggle.toggled.connect(self._set_audit_visible)
        detail_layout.addWidget(self.audit_toggle)
        self.audit_text = QPlainTextEdit()
        self.audit_text.setObjectName("technicalOfficialRevenueAudit")
        self.audit_text.setReadOnly(True)
        self.audit_text.setMinimumHeight(260)
        self.audit_text.setVisible(False)
        detail_layout.addWidget(self.audit_text, 1)
        self.return_button = QPushButton("返回原研究結果頁")
        self.return_button.clicked.connect(self.return_to_results)
        self.open_stock_research_button = QPushButton("開啟一般個股研究")
        self.open_stock_research_button.setObjectName("openRevenueStockResearch")
        self.open_stock_research_button.clicked.connect(self.request_stock_research)
        detail_actions = QHBoxLayout()
        detail_actions.addWidget(self.open_stock_research_button)
        detail_actions.addWidget(self.return_button)
        detail_layout.addLayout(detail_actions)
        self.results_stack.addWidget(detail_panel)
        body.addWidget(self.results_stack, 1)

        self.status_label = QLabel("")
        self.status_label.setObjectName("technicalOfficialRevenueStatus")
        self.status_label.setWordWrap(True)
        outer.addWidget(self.status_label)
        self.next_catalog_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self._set_result_actions_enabled(False)

    def _build_filter_panel(self) -> QWidget:
        panel = QGroupBox("全母體條件與全域排序")
        panel.setObjectName("technicalOfficialRevenueFilterPanel")
        panel_layout = QVBoxLayout(panel)

        scope_box = QGroupBox("母體列範圍（hard eligibility 外層）")
        scope_grid = QGridLayout(scope_box)
        self.scope_checks: dict[RowScope, QCheckBox] = {}
        for index, scope in enumerate(_SCOPE_ORDER):
            check = QCheckBox(_SCOPE_LABELS[scope])
            check.setChecked(True)
            self.scope_checks[scope] = check
            scope_grid.addWidget(check, index // 2, index % 2)
        panel_layout.addWidget(scope_box)

        tech_box = QGroupBox("五項技術規則（每規則選擇保存 state）")
        tech_layout = QVBoxLayout(tech_box)
        self.technical_combine_box = QComboBox()
        self.technical_combine_box.addItem("技術規則 AND", "AND")
        self.technical_combine_box.addItem("技術規則 OR", "OR")
        tech_layout.addWidget(self.technical_combine_box)
        self.rule_state_checks: dict[str, dict[MaState, QCheckBox]] = {}
        for key in DAILY_MARKET_TECHNICAL_RULE_KEYS_V4:
            rule_box = QGroupBox(_RULE_LABELS[key])
            state_grid = QGridLayout(rule_box)
            self.rule_state_checks[key] = {}
            for index, state in enumerate(_STATES):
                check = QCheckBox(_STATE_LABELS[state])
                self.rule_state_checks[key][state] = check
                state_grid.addWidget(check, 0, index)
            tech_layout.addWidget(rule_box)
        panel_layout.addWidget(tech_box)

        ma_box = QGroupBox("四均線排列條件（獨立群組）")
        ma_grid = QGridLayout(ma_box)
        self.ma_state_checks: dict[MaState, QCheckBox] = {}
        for index, state in enumerate(_STATES):
            check = QCheckBox(_STATE_LABELS[state])
            self.ma_state_checks[state] = check
            ma_grid.addWidget(check, 0, index)
        panel_layout.addWidget(ma_box)

        revenue_box = QGroupBox("月營收 YoY 條件（沒有數值即未啟用）")
        revenue_layout = QGridLayout(revenue_box)
        self.yoy_filter_enabled = QCheckBox("啟用 YoY 最低門檻")
        self.yoy_threshold_input = QLineEdit()
        self.yoy_threshold_input.setPlaceholderText("有限 Decimal，例 10.5；端點依方法契約包含")
        revenue_layout.addWidget(self.yoy_filter_enabled, 0, 0)
        revenue_layout.addWidget(self.yoy_threshold_input, 0, 1)
        panel_layout.addWidget(revenue_box)

        policy_box = QGroupBox("已啟用條件群組的 AND／OR 與未知政策")
        policy_layout = QFormLayout(policy_box)
        self.condition_combine_box = QComboBox()
        self.condition_combine_box.addItem("AND", "AND")
        self.condition_combine_box.addItem("OR", "OR")
        self.unknown_policy_box = QComboBox()
        self.unknown_policy_box.addItem("未知列納入可見結果", "include")
        self.unknown_policy_box.addItem("未知列排除", "exclude")
        self.unknown_policy_box.addItem("只看未知列", "only")
        policy_layout.addRow("合併方式", self.condition_combine_box)
        policy_layout.addRow("未知政策", self.unknown_policy_box)
        panel_layout.addWidget(policy_box)
        self.ma_state_checks["match"].stateChanged.connect(self._refresh_policy_controls)
        self.yoy_filter_enabled.stateChanged.connect(self._refresh_policy_controls)
        for checks in self.rule_state_checks.values():
            for check in checks.values():
                check.stateChanged.connect(self._refresh_policy_controls)

        official_box = QGroupBox("官方市場／處置條件（外層硬條件，不受 OR 繞過）")
        official_layout = QVBoxLayout(official_box)
        self.market_filter_enabled = QCheckBox("限制官方市場狀態")
        official_layout.addWidget(self.market_filter_enabled)
        self.market_checks = self._check_group(official_layout, _MARKET_STATES, _MARKET_LABELS, "market")
        self.disposal_filter_enabled = QCheckBox("限制官方處置狀態")
        official_layout.addWidget(self.disposal_filter_enabled)
        self.disposal_checks = self._check_group(official_layout, _DISPOSAL_STATES, _DISPOSAL_LABELS, "disposal")
        panel_layout.addWidget(official_box)

        stock_box = QGroupBox("明示股票代碼交集（非 AND／OR 群組）")
        stock_grid = QGridLayout(stock_box)
        self.stock_filter_enabled = QCheckBox("限制股票代碼")
        self.stock_code_input = _RevenueStockCodeLineEdit()
        self.stock_code_input.setPlaceholderText("逗號、中文逗號或空白分隔；代碼會完整驗證")
        stock_grid.addWidget(self.stock_filter_enabled, 0, 0)
        stock_grid.addWidget(self.stock_code_input, 0, 1)
        panel_layout.addWidget(stock_box)

        page_row = QHBoxLayout()
        page_row.addWidget(QLabel("每頁筆數（最多 256）"))
        self.page_size_box = QSpinBox()
        self.page_size_box.setRange(1, DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_MAX_PAGE_SIZE_V1)
        self.page_size_box.setValue(100)
        self.page_size_box.valueChanged.connect(self._page_size_changed)
        page_row.addWidget(self.page_size_box)
        panel_layout.addLayout(page_row)

        sort_box = QGroupBox("全母體排序（先全域排序再分頁；未知值雙向置尾）")
        self.sort_rows_layout = QVBoxLayout(sort_box)
        self.sort_rows: list[tuple[QComboBox, QComboBox, QPushButton, QWidget]] = []
        self.add_sort_button = QPushButton("增加排序欄")
        self.add_sort_button.clicked.connect(self.add_sort_clause)
        self.sort_rows_layout.addWidget(self.add_sort_button)
        self._add_sort_clause_row("stock_code", "asc")
        panel_layout.addWidget(sort_box)
        self._refresh_policy_controls()
        return panel

    @staticmethod
    def _check_group(
        parent_layout: QVBoxLayout,
        states: Sequence[str],
        labels: Mapping[str, str],
        prefix: str,
    ) -> dict[str, QCheckBox]:
        grid = QGridLayout()
        checks: dict[str, QCheckBox] = {}
        for index, state in enumerate(states):
            check = QCheckBox(labels[state])
            check.setObjectName(f"{prefix}_{state}")
            checks[state] = check
            grid.addWidget(check, index // 2, index % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        parent_layout.addLayout(grid)
        return checks

    def _add_sort_clause_row(self, field: str | None = None, direction: str = "asc") -> None:
        row_widget = QWidget()
        row_layout = QGridLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        field_box = QComboBox()
        field_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        field_box.setMinimumContentsLength(12)
        field_box.setMinimumWidth(0)
        for value, label in _SORT_FIELD_LABELS:
            field_box.addItem(label, value)
        if field is not None:
            found = field_box.findData(field)
            if found >= 0:
                field_box.setCurrentIndex(found)
        direction_box = QComboBox()
        direction_box.addItem("升冪", "asc")
        direction_box.addItem("降冪", "desc")
        found_direction = direction_box.findData(direction)
        if found_direction >= 0:
            direction_box.setCurrentIndex(found_direction)
        remove_button = QPushButton("移除")
        controls = (field_box, direction_box, remove_button, row_widget)
        remove_button.clicked.connect(lambda _checked=False, items=controls: self._remove_sort_clause_row(items))
        field_box.currentIndexChanged.connect(
            lambda _index, f=field_box, d=direction_box: self._sync_stock_sort_direction(f, d)
        )
        row_layout.addWidget(field_box, 0, 0)
        row_layout.addWidget(direction_box, 0, 1)
        row_layout.addWidget(remove_button, 0, 2)
        self.sort_rows_layout.insertWidget(max(0, self.sort_rows_layout.count() - 1), row_widget)
        self.sort_rows.append(controls)
        self.add_sort_button.setEnabled(len(self.sort_rows) < 34)

    @staticmethod
    def _sync_stock_sort_direction(field_box: QComboBox, direction_box: QComboBox) -> None:
        is_stock = field_box.currentData() == "stock_code"
        if is_stock and direction_box.currentData() != "asc":
            direction_box.setCurrentIndex(direction_box.findData("asc"))
        direction_box.setEnabled(not is_stock)

    def _remove_sort_clause_row(self, controls: tuple[QComboBox, QComboBox, QPushButton, QWidget]) -> None:
        if len(self.sort_rows) <= 1:
            self._set_status("至少保留一個全域排序欄。")
            return
        if controls not in self.sort_rows:
            return
        self.sort_rows.remove(controls)
        self.sort_rows_layout.removeWidget(controls[3])
        controls[3].deleteLater()
        self.add_sort_button.setEnabled(len(self.sort_rows) < 34)

    def add_sort_clause(self) -> None:
        if len(self.sort_rows) >= 34:
            self._set_status("排序欄已達方法上限。")
            return
        self._add_sort_clause_row("stock_code", "asc")

    def _refresh_policy_controls(self, *_args: object) -> None:
        technical_active = any(check.isChecked() for group in self.rule_state_checks.values() for check in group.values())
        ma_active = any(check.isChecked() for check in self.ma_state_checks.values())
        revenue_active = self.yoy_filter_enabled.isChecked()
        active_count = int(technical_active) + int(ma_active) + int(revenue_active)
        self.condition_combine_box.setEnabled(active_count >= 2)
        self.unknown_policy_box.setEnabled(active_count > 0)
        if active_count < 2:
            self.condition_combine_box.setCurrentIndex(self.condition_combine_box.findData("AND"))
        if active_count == 0:
            self.unknown_policy_box.setCurrentIndex(self.unknown_policy_box.findData("include"))

    def choose_bundle_output_root(self) -> None:
        if not self._can_start():
            self._set_status("背景工作中或畫面正在關閉，暫時不能更換來源。")
            return
        selected = QFileDialog.getExistingDirectory(
            self, "選擇已保存的 F17 bundle 資料夾", str(self.bundle_output_root or ""),
            QFileDialog.Option.ShowDirsOnly,
        )
        if selected:
            self.set_bundle_output_root(selected)

    def set_bundle_output_root(self, root: str | Path) -> bool:
        candidate = Path(root)
        if not self._can_start() or not candidate.is_absolute() or not candidate.is_dir():
            self._set_status("F17 保存來源必須是已存在的絕對資料夾，且目前沒有背景工作。")
            return False
        self.bundle_output_root = candidate
        self.root_label.setText(str(candidate))
        self._catalog_cursor = None
        self._catalog_entries = ()
        self.catalog_list.clear()
        self._clear_issued_state()
        self._set_status("來源資料夾已更新；metadata 尚未核驗。請更新清單並明確選取版本。")
        return True

    def choose_monthly_reference(self) -> None:
        if not self._can_start():
            self._set_status("背景工作中或畫面正在關閉，暫時不能更換月營收參照。")
            return
        selected, _filter = QFileDialog.getOpenFileName(
            self, "選擇月營收 V2 保存參照", str(self.monthly_reference_path or ""),
            "JSON (*.json);;All files (*.*)",
        )
        if selected:
            self.set_monthly_reference_path(selected)

    def set_monthly_reference_path(self, path: str | Path) -> bool:
        candidate = Path(path)
        if not self._can_start() or not candidate.is_absolute() or not candidate.is_file():
            self._set_status("月營收參照必須是已存在的絕對檔案路徑。")
            return False
        self.monthly_reference_path = candidate
        self.monthly_reference_label.setText(str(candidate))
        self._clear_issued_state()
        self._set_status("已選擇月營收 V2 參照；內容與封存來源仍待 exact 核驗。")
        return True

    def choose_operation_root_parent(self) -> None:
        if not self._can_start():
            self._set_status("背景工作中或畫面正在關閉，暫時不能更換 operation 暫存父資料夾。")
            return
        selected = QFileDialog.getExistingDirectory(
            self, "選擇已存在的 operation 暫存父資料夾", str(self.operation_root_parent or ""),
            QFileDialog.Option.ShowDirsOnly,
        )
        if selected:
            self.set_operation_root_parent(selected)

    def set_operation_root_parent(self, path: str | Path) -> bool:
        candidate = Path(path)
        if not self._can_start() or not candidate.is_absolute() or not candidate.is_dir():
            self._set_status("operation 暫存父資料夾必須是已存在的絕對路徑。")
            return False
        self.operation_root_parent = candidate
        self.operation_root_label.setText(str(candidate))
        return True

    def choose_monthly_artifact_root(self) -> None:
        if not self._can_start():
            return
        title = "選擇已存在的研究保存資料夾" if self.daily_source_config_v2 is not None and self.daily_source_config_v2.use_archived_sources else "選擇已存在的每日快照參照保存資料夾"
        selected = QFileDialog.getExistingDirectory(self, title, str(self.monthly_artifact_root or ""))
        if selected:
            self.set_monthly_artifact_root(selected)

    def set_monthly_artifact_root(self, path: str | Path) -> bool:
        candidate = Path(path)
        if not self._can_start() or not candidate.is_absolute() or not candidate.is_dir():
            self._set_status("版本參照保存資料夾必須是已存在的絕對路徑。")
            return False
        self.monthly_artifact_root = candidate
        self.monthly_artifact_label.setText(str(candidate))
        return True

    def refresh_catalog(self) -> None:
        if self.bundle_output_root is None:
            self._set_status("尚未選擇保存來源資料夾；不會自動掃描或建立資料夾。")
            return
        root = self.bundle_output_root

        def task(cancel_callback: Callable[[], object] | None = None) -> DailyMarketTechnicalOfficialDispositionBundleCatalogPageV1:
            return DailyMarketTechnicalOfficialDispositionBundleCatalogV1(root).list_page(
                limit=DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_CATALOG_DEFAULT_LIMIT,
                cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
            )

        self._start_task("盤點保存來源 metadata", task, self._apply_catalog_page)

    def load_next_catalog_page(self) -> None:
        if self.bundle_output_root is None or self._catalog_cursor is None:
            self._set_status("沒有可安全續讀的完整來源清單。")
            return
        root, cursor = self.bundle_output_root, self._catalog_cursor

        def task(cancel_callback: Callable[[], object] | None = None) -> DailyMarketTechnicalOfficialDispositionBundleCatalogPageV1:
            return DailyMarketTechnicalOfficialDispositionBundleCatalogV1(root).list_page(
                limit=DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_CATALOG_DEFAULT_LIMIT,
                cursor=cursor,
                cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
            )

        self._start_task("續讀保存來源 metadata", task, self._append_catalog_page)

    def _apply_catalog_page(self, value: object) -> None:
        if not isinstance(value, DailyMarketTechnicalOfficialDispositionBundleCatalogPageV1):
            raise ValueError("technical_official_revenue_view_catalog_result_invalid")
        self._catalog_entries = value.entries
        self._catalog_cursor = value.next_cursor if value.scan_complete else None
        self._render_catalog()
        self.next_catalog_button.setEnabled(value.scan_complete and value.next_cursor is not None)
        if value.scan_complete:
            self._set_status(f"metadata 清單盤點 {value.scanned_entry_count} 項；資訊未核驗，請明確選取版本。")
        else:
            self._set_status(f"清單不完整：{value.diagnostic_code or '未提供診斷'}；不能續讀或開啟。")

    def _append_catalog_page(self, value: object) -> None:
        if not isinstance(value, DailyMarketTechnicalOfficialDispositionBundleCatalogPageV1):
            raise ValueError("technical_official_revenue_view_catalog_result_invalid")
        if not value.scan_complete:
            self._catalog_cursor = None
            self._set_status(f"來源清單漂移／不完整：{value.diagnostic_code or '未提供診斷'}。")
            return
        self._catalog_entries = (*self._catalog_entries, *value.entries)
        self._catalog_cursor = value.next_cursor
        self._render_catalog()
        self.next_catalog_button.setEnabled(value.next_cursor is not None)
        self._set_status("metadata 清單已續讀；仍未授予來源核驗資格。")

    def _render_catalog(self) -> None:
        self.catalog_list.blockSignals(True)
        self.catalog_list.clear()
        for index, entry in enumerate(self._catalog_entries):
            metadata = entry.metadata
            if metadata is None:
                label = f"資訊不完整｜診斷：{entry.diagnostic_code or '未提供'}"
            else:
                label = (
                    f"{metadata.decision_date_label.isoformat()}｜宣告 {metadata.declared_count}、"
                    f"納入 {metadata.included_count}、排除 {metadata.excluded_count}｜"
                    f"來源覆蓋標示 {metadata.source_coverage_status_label}｜尚未核驗"
                )
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setToolTip(entry.diagnostic_code or entry.relative_path)
            if entry.can_attempt_exact_read:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            else:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled & ~Qt.ItemFlag.ItemIsSelectable)
            self.catalog_list.addItem(item)
        self.catalog_list.blockSignals(False)

    def open_selected_candidate(self) -> None:
        index = self.catalog_list.currentRow()
        if not 0 <= index < len(self._catalog_entries):
            self._set_status("請明確選取一個可嘗試核驗的 F17 保存版本。")
            return
        if self.bundle_output_root is None or (self.daily_source_config_v2 is None and self.monthly_reference_path is None):
            self._set_status("需明示 F17 資料夾與月營收 V2 參照。")
            return
        if self.operation_root_parent is None:
            self._set_status("需選擇已存在的 operation 暫存父資料夾。")
            return
        entry = self._catalog_entries[index]
        if not entry.can_attempt_exact_read or entry.metadata is None:
            self._set_status("此列只是診斷或 metadata，不能開啟研究結果。")
            return
        try:
            conditions = self._read_conditions()
        except (TypeError, ValueError) as exc:
            self._set_status(f"條件無效：{exc}")
            return
        source = _SourceChoice(
            str(self.bundle_output_root),
            entry.metadata.bundle_identity_sha256,
            entry.metadata.manifest_sha256,
            "",
        )
        reference_path = str(self.monthly_reference_path)
        operation_parent = self.operation_root_parent
        page_size = self.page_size_box.value()

        if self.daily_source_config_v2 is not None:
            config, artifact_root = self.daily_source_config_v2, self.monthly_artifact_root
            if artifact_root is None:
                self._set_status("需選擇每日版本參照保存資料夾，且須與來源及 operation 資料夾分開。")
                return
            self._start_v2_open("核驗每日快照並執行全母體查詢", lambda cancel: _open_daily_v2(
                source, conditions, config, operation_parent, artifact_root, page_size, cancel,
            ))
            return

        def task(cancel_callback: Callable[[], object] | None = None) -> _OpenedQuery:
            reference = _read_reference_file(reference_path)
            resolved = _SourceChoice(
                source.bundle_output_root,
                source.bundle_identity_sha256,
                source.manifest_sha256,
                reference.to_json(),
            )
            return _open_from_bundle(
                resolved,
                conditions,
                operation_parent,
                page_index=0,
                page_size=page_size,
                cancel_callback=cancel_callback,
            )

        self._start_task("核驗雙來源並執行全母體查詢", task, self._apply_opened_query)

    def _read_conditions(self) -> _Conditions:
        scopes = tuple(scope for scope in _SCOPE_ORDER if self.scope_checks[scope].isChecked())
        if not scopes:
            raise ValueError("technical_official_revenue_view_row_scope_empty")
        filters: list[DailyMarketTechnicalRuleStateFilterV4] = []
        for rule_key, checks in self.rule_state_checks.items():
            states = tuple(state for state in _STATES if checks[state].isChecked())
            if states:
                filters.append(DailyMarketTechnicalRuleStateFilterV4.create(rule_key, states))
        market = tuple(state for state in _MARKET_STATES if self.market_checks[state].isChecked())
        disposal = tuple(state for state in _DISPOSAL_STATES if self.disposal_checks[state].isChecked())
        if self.market_filter_enabled.isChecked() and not market:
            raise ValueError("technical_official_revenue_view_market_state_required")
        if not self.market_filter_enabled.isChecked() and market:
            raise ValueError("technical_official_revenue_view_market_filter_disabled_with_values")
        if self.disposal_filter_enabled.isChecked() and not disposal:
            raise ValueError("technical_official_revenue_view_disposal_state_required")
        if not self.disposal_filter_enabled.isChecked() and disposal:
            raise ValueError("technical_official_revenue_view_disposal_filter_disabled_with_values")
        if self.stock_filter_enabled.isChecked():
            codes = _parse_stock_codes(
                self.stock_code_input.text(),
                was_truncated=self.stock_code_input.was_truncated,
            )
            stock_mode: Literal["all", "explicit_codes"] = "explicit_codes"
        else:
            if self.stock_code_input.text().strip():
                raise ValueError("technical_official_revenue_view_stock_filter_disabled_with_values")
            codes = ()
            stock_mode = "all"
        ma_states = tuple(state for state in _STATES if self.ma_state_checks[state].isChecked())
        if not ma_states:
            normalized_ma: tuple[MaState, ...] | None = None
        else:
            normalized_ma = ma_states
        threshold: Decimal | None = None
        if self.yoy_filter_enabled.isChecked():
            raw = self.yoy_threshold_input.text().strip()
            if not raw:
                raise ValueError("technical_official_revenue_view_yoy_threshold_required")
            try:
                threshold = Decimal(raw)
            except (InvalidOperation, ValueError) as exc:
                raise ValueError("technical_official_revenue_view_yoy_threshold_invalid") from exc
            if not threshold.is_finite():
                raise ValueError("technical_official_revenue_view_yoy_threshold_nonfinite")
        elif self.yoy_threshold_input.text().strip():
            raise ValueError("technical_official_revenue_view_yoy_filter_disabled_with_value")
        sort: list[DailyMarketTechnicalOfficialDispositionMaSortClauseV1] = []
        seen: set[str] = set()
        if not self.sort_rows or len(self.sort_rows) > 34:
            raise ValueError("technical_official_revenue_view_sort_count_invalid")
        for field_box, direction_box, _remove, _widget in self.sort_rows:
            field = field_box.currentData()
            direction = direction_box.currentData()
            if not isinstance(field, str) or direction not in {"asc", "desc"}:
                raise ValueError("technical_official_revenue_view_sort_invalid")
            if field in seen:
                raise ValueError("technical_official_revenue_view_sort_duplicate")
            seen.add(field)
            sort.append(DailyMarketTechnicalOfficialDispositionMaSortClauseV1(
                field, cast(Literal["asc", "desc"], direction),
            ))
        active_count = int(bool(filters)) + int(normalized_ma is not None) + int(threshold is not None)
        combine: Literal["AND", "OR"] = cast(Literal["AND", "OR"], self.condition_combine_box.currentData())
        unknown: UnknownPolicy = cast(UnknownPolicy, self.unknown_policy_box.currentData())
        if active_count < 2:
            combine = "AND"
        if active_count == 0:
            unknown = "include"
        return _Conditions(
            cast(tuple[RowScope, ...], scopes),
            tuple(filters),
            cast(Literal["AND", "OR"], self.technical_combine_box.currentData()),
            market,
            disposal,
            stock_mode,
            codes,
            normalized_ma,
            threshold,
            combine,
            unknown,
            tuple(sort),
        )

    def apply_filters(self) -> None:
        if self.operation_root_parent is None:
            self._set_status("需選擇已存在的 operation 暫存父資料夾。")
            return
        try:
            conditions = self._read_conditions()
        except (TypeError, ValueError) as exc:
            self._set_status(f"條件無效：{exc}")
            return
        if self._source is None:
            self.open_selected_candidate()
            return
        source = self._source
        parent = self.operation_root_parent
        page_size = self.page_size_box.value()

        if source.mode in ("daily_v2", "daily_archived_v3"):
            recipe, config, artifact_root = self._recipe, self.daily_source_config_v2, self.monthly_artifact_root
            if type(recipe) not in (DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2, DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3) or config is None or artifact_root is None:
                self._set_status("每日來源設定或已核驗 recipe 不完整。")
                return
            def open_filtered(cancel: Callable[[], bool]) -> _ExactDaily:
                if cancel():
                    raise ValueError("technical_official_revenue_view_cancelled")
                reader = self._exact_daily_reader(config, recipe)
                if cancel():
                    raise ValueError("technical_official_revenue_view_cancelled")
                return _open_daily_v2(source, conditions, config, parent, artifact_root, page_size, cancel, reader=reader)
            self._start_v2_open("沿同一每日 cohort 重新查詢", open_filtered)
            return

        def task(cancel_callback: Callable[[], object] | None = None) -> _OpenedQuery:
            return _open_from_bundle(
                source,
                conditions,
                parent,
                page_index=0,
                page_size=page_size,
                cancel_callback=cancel_callback,
            )

        self._start_task("沿保存雙來源重新核驗並全域查詢", task, self._apply_opened_query)

    def clear_filters(self) -> None:
        for check in self.scope_checks.values():
            check.setChecked(True)
        for group in self.rule_state_checks.values():
            for check in group.values():
                check.setChecked(False)
        for check in self.ma_state_checks.values():
            check.setChecked(False)
        self.yoy_filter_enabled.setChecked(False)
        self.yoy_threshold_input.clear()
        self.technical_combine_box.setCurrentIndex(self.technical_combine_box.findData("AND"))
        self.condition_combine_box.setCurrentIndex(self.condition_combine_box.findData("AND"))
        self.unknown_policy_box.setCurrentIndex(self.unknown_policy_box.findData("include"))
        self.market_filter_enabled.setChecked(False)
        self.disposal_filter_enabled.setChecked(False)
        for check in (*self.market_checks.values(), *self.disposal_checks.values()):
            check.setChecked(False)
        self.stock_filter_enabled.setChecked(False)
        self.stock_code_input.clear()
        while len(self.sort_rows) > 1:
            self._remove_sort_clause_row(self.sort_rows[-1])
        self.sort_rows[0][0].setCurrentIndex(self.sort_rows[0][0].findData("stock_code"))
        self.sort_rows[0][1].setCurrentIndex(self.sort_rows[0][1].findData("asc"))
        self.page_size_box.setValue(100)
        self._clear_basket()
        self.apply_filters()

    def _page_index(self) -> int:
        """提供換頁按鈕目前已核頁碼；尚無結果時從零開始。"""
        return self._page.page_index if self._page is not None else 0

    def navigate_page(self, page_index: int) -> None:
        if (
            self._recipe is None
            or self._source is None
            or self._result is None
            or self._page is None
        ):
            return
        if type(page_index) is not int or not 0 <= page_index < self._page.page_count:
            return
        recipe = self._recipe
        source = self._source
        result = self._result
        page_size = self.page_size_box.value()

        if type(recipe) in (DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2, DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3):
            def read_daily_page(handle: ClosableHandle, cancel: Callable[[], bool]) -> _OpenedQuery:
                exact = _exact_v2(handle)
                if exact.result is not result or not _query_matches_recipe(exact.query, recipe):
                    raise ValueError("technical_official_revenue_view_v2_result_changed")
                request = DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2.create(exact.query, page_index=page_index, page_size=page_size)
                page = exact.result.read_page_request(request, cancel_callback=cancel)
                projected_recipe = _recipe_for_page(recipe, page_index=page_index, page_size=page_size)
                _project_revenue_page_table_rows(page.rows)
                if cancel():
                    raise ValueError("technical_official_revenue_view_cancelled")
                return _OpenedQuery(source, projected_recipe, exact.query, exact.result, request, page)
            self._start_v2_task("讀取同一每日來源已核驗結果頁", read_daily_page, self._apply_page_change)
            return
        if type(result) is not DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV1:
            return

        def task(cancel_callback: Callable[[], object] | None = None) -> _OpenedQuery:
            return _read_page_from_result(
                source,
                recipe,
                result,
                page_index=page_index,
                page_size=page_size,
                cancel_callback=cancel_callback,
            )

        self._start_task("讀取已核驗全域排序結果的指定頁", task, self._apply_page_change)

    def _apply_page_change(self, value: object) -> None:
        if not isinstance(value, _OpenedQuery):
            raise ValueError("technical_official_revenue_view_page_result_invalid")
        if (
            self._result is None
            or value.result is not self._result
            or self._query is None
            or value.query.query_identity_sha256 != self._query.query_identity_sha256
            or value.page.query.query_identity_sha256 != self._query.query_identity_sha256
            or not _query_matches_recipe(value.query, value.recipe)
        ):
            raise ValueError("technical_official_revenue_view_page_operation_changed")
        if len(value.page.rows) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_MAX_PAGE_SIZE_V1:
            raise ValueError("technical_official_revenue_view_page_limit_exceeded")
        expected_scope = _scope_identity(value.recipe)
        if any(item.scope_identity_sha256 != expected_scope for item in self._basket):
            raise ValueError("technical_official_revenue_view_page_basket_scope_mismatch")
        projected_rows = _project_revenue_page_table_rows(value.page.rows)
        self.table_model.replace_page(projected_rows)
        self._source = value.source
        self._recipe = value.recipe
        self._page_request = value.page_request
        self._page = value.page
        self._selected_row = None
        self._apply_query_controls(value.query, value.page_request)
        self._render_page(replace_table=False)
        self._update_basket_label()
        self._set_status("本頁由同一個已核驗全域結果讀回；來源不會在背景持續監測。")

    def _apply_opened_query(self, value: object) -> None:
        if not isinstance(value, _OpenedQuery):
            raise ValueError("technical_official_revenue_view_query_result_invalid")
        if len(value.page.rows) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_MAX_PAGE_SIZE_V1:
            raise ValueError("technical_official_revenue_view_page_limit_exceeded")
        projected_rows = _project_revenue_page_table_rows(value.page.rows)
        self.table_model.replace_page(projected_rows)
        self._source = value.source
        self._recipe = value.recipe
        self._query = value.query
        self._result = value.result
        self._page_request = value.page_request
        self._page = value.page
        self._selected_row = None
        self._clear_basket()
        self._apply_query_controls(value.query, value.page_request)
        if type(value.result) is DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV2:
            summary = format_technical_official_revenue_counts_v2(value.result.counts, result_status=value.result.result_status, official_coverage_status=value.result.official_source_coverage_status)
        else:
            summary = format_technical_official_revenue_counts_v1(value.result.counts, result_status=value.result.result_status, official_coverage_status=value.result.official_source_coverage_status)
        self.summary_label.setText(summary)
        self.results_stack.setCurrentIndex(0)
        self._render_page(replace_table=False)
        if value.selected_stock_code:
            self.select_stock_code(value.selected_stock_code)
        self._set_status(
            "每日 cohort 小時已核驗；官方與整體 F17 可用時間仍未知、current-only、非歷史 PIT。"
            if value.source.mode in ("daily_v2", "daily_archived_v3") else "來源已 exact 核驗；官方／月營收可用時間仍未知、current-only、非歷史 PIT。"
        )

    def _render_page(self, *, replace_table: bool = True) -> None:
        page = self._page
        if replace_table:
            self.table_model.replace_page(
                _project_revenue_page_table_rows(page.rows if page is not None else None)
            )
        self.page_label.setText(
            f"第 {page.page_index + 1}／{page.page_count} 頁；本頁 {len(page.rows)} 列"
            if page is not None and page.page_count
            else "目前沒有符合未知政策與外層條件的列"
        )
        self._set_result_actions_enabled(page is not None)

    def _apply_query_controls(
        self,
        query: _Query,
        request: _PageRequest,
    ) -> None:
        f17 = query.ma_query.f17_query
        for scope, check in self.scope_checks.items():
            check.setChecked(scope in f17.row_scope_filter)
        filters = {item.rule_key: item for item in f17.technical_query.rule_state_filters}
        for rule_key, checks in self.rule_state_checks.items():
            selected = set(filters[rule_key].states) if rule_key in filters else set()
            for state, check in checks.items():
                check.setChecked(state in selected)
        self.technical_combine_box.setCurrentIndex(self.technical_combine_box.findData(f17.technical_query.combine_mode))
        for state, check in self.ma_state_checks.items():
            check.setChecked(
                state in query.ma_query.ma_states
                if query.ma_query.ma_states is not None
                else False
            )
        self.yoy_filter_enabled.setChecked(query.minimum_yoy_percent is not None)
        self.yoy_threshold_input.setText(
            str(query.minimum_yoy_percent) if query.minimum_yoy_percent is not None else ""
        )
        self.condition_combine_box.setCurrentIndex(self.condition_combine_box.findData(query.condition_combine_mode))
        self.unknown_policy_box.setCurrentIndex(self.unknown_policy_box.findData(query.unknown_policy))
        self._refresh_policy_controls()
        self.market_filter_enabled.setChecked(bool(f17.market_assignment_states))
        self.disposal_filter_enabled.setChecked(bool(f17.official_disposal_states))
        for state, check in self.market_checks.items():
            check.setChecked(state in f17.market_assignment_states)
        for state, check in self.disposal_checks.items():
            check.setChecked(state in f17.official_disposal_states)
        explicit = f17.outer_stock_filter_mode == "explicit_codes"
        self.stock_filter_enabled.setChecked(explicit)
        self.stock_code_input.setText(", ".join(f17.outer_stock_codes) if explicit else "")
        self.page_size_box.setValue(request.page_size)
        while len(self.sort_rows) > 1:
            self._remove_sort_clause_row(self.sort_rows[-1])
        first = query.sort_clauses[0]
        self.sort_rows[0][0].setCurrentIndex(self.sort_rows[0][0].findData(first.field))
        self.sort_rows[0][1].setCurrentIndex(self.sort_rows[0][1].findData(first.direction))
        for clause in query.sort_clauses[1:]:
            self._add_sort_clause_row(clause.field, clause.direction)

    def _table_selection_changed(self, index: QModelIndex) -> None:
        row = self.table_model.row_at(index.row())
        if row is None:
            self._selected_row = None
            return
        self._selected_row = row

    def select_stock_code(self, stock_code: str) -> bool:
        index = self.table_model.index_for_stock(stock_code)
        if not index.isValid():
            return False
        self.results_table.setCurrentIndex(index)
        self.results_table.selectRow(index.row())
        self._selected_row = self.table_model.row_at(index.row())
        return self._selected_row is not None and self._selected_row.stock_code == stock_code

    def show_selected_detail(self) -> None:
        row = self._selected_row
        if row is None:
            self._set_status("請先選取目前頁面的一檔股票。")
            return
        self.detail_text.setPlainText(_row_detail(row))
        self.audit_text.setPlainText(json.dumps(row.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
        self.audit_toggle.setChecked(False)
        self.results_stack.setCurrentIndex(1)
        self.stockSelected.emit(row)

    def _source_identity_sha256(self) -> str | None:
        source, page = self._source, self._page
        if source is None or page is None:
            return None
        pins = getattr(page, "source_pins", None)
        if type(pins) is not tuple:
            return None
        try:
            payload = {
                "schema": "official-revenue-verified-source.v1",
                "mode": source.mode,
                "bundle_identity_sha256": source.bundle_identity_sha256,
                "manifest_sha256": source.manifest_sha256,
                "source_pins": [[key, value] for key, value in pins],
            }
            encoded = json.dumps(
                payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        except (AttributeError, TypeError, ValueError):
            return None
        return hashlib.sha256(encoded).hexdigest()

    def _origin_for_row(self, row: _Row) -> RevenueStockResearchOrigin | None:
        if self._closing or not self._can_start():
            return None
        source, recipe = self._source, self._recipe
        query, result, request, page = (
            self._query, self._result, self._page_request, self._page
        )
        if any(value is None for value in (source, recipe, query, result, request, page)):
            return None
        assert source is not None and recipe is not None and query is not None
        assert result is not None and request is not None and page is not None
        try:
            query_identity = query.query_identity_sha256
            if (
                result.query.query_identity_sha256 != query_identity
                or request.query.query_identity_sha256 != query_identity
                or page.query.query_identity_sha256 != query_identity
                or page.request_identity_sha256 != request.request_identity_sha256
                or page.page_index != request.page_index
                or not _query_matches_recipe(query, recipe)
                or not any(
                    candidate.stock_code == row.stock_code
                    and candidate.row_identity_sha256 == row.row_identity_sha256
                    for candidate in page.rows
                )
            ):
                return None
            source_identity = self._source_identity_sha256()
            if source_identity is None:
                return None
            recipe_identity = hashlib.sha256(recipe.to_json().encode("utf-8")).hexdigest()
            return RevenueStockResearchOrigin.create(
                stock_code=row.stock_code,
                source_identity_sha256=source_identity,
                recipe_identity_sha256=recipe_identity,
                query_identity_sha256=query_identity,
                page_identity_sha256=page.page_identity_sha256,
                request_identity_sha256=request.request_identity_sha256,
                row_identity_sha256=row.row_identity_sha256,
                page_index=page.page_index,
            )
        except (AttributeError, TypeError, ValueError):
            return None

    def create_stock_research_origin(self) -> RevenueStockResearchOrigin | None:
        """只為目前已核驗結果頁中的選取列建立身份，不觸發查詢。"""
        row = self._selected_row
        return None if row is None else self._origin_for_row(row)

    def request_stock_research(self) -> None:
        origin = self.create_stock_research_origin()
        if origin is None:
            self._set_status("目前沒有可用的已核驗選取列，或來源／頁面正在變動。")
            return
        self.stockResearchRequested.emit(origin)

    def restore_stock_research_origin(self, origin: object) -> bool:
        """只回到仍在目前已核快照中的原頁原列；不重新開啟磁碟來源。"""
        if type(origin) is not RevenueStockResearchOrigin or self._closing or not self._can_start():
            return False
        page = self._page
        selected = self._selected_row
        if (
            page is None
            or selected is None
            or selected.stock_code != origin.stock_code
            or selected.row_identity_sha256 != origin.row_identity_sha256
        ):
            return False
        current_row = next(
            (
                row for row in page.rows
                if row.stock_code == origin.stock_code
                and row.row_identity_sha256 == origin.row_identity_sha256
            ),
            None,
        )
        if current_row is None or self._origin_for_row(current_row) != origin:
            return False
        if not self.select_stock_code(origin.stock_code):
            return False
        selected = self._selected_row
        if (
            selected is None
            or selected.stock_code != origin.stock_code
            or selected.row_identity_sha256 != origin.row_identity_sha256
        ):
            return False
        self.return_to_results()
        return True

    def _set_audit_visible(self, visible: bool) -> None:
        self.audit_text.setVisible(visible)

    def return_to_results(self) -> None:
        self.results_stack.setCurrentIndex(0)

    def add_selected_to_comparison(self) -> None:
        row = self._selected_row
        recipe = self._recipe
        if row is None or recipe is None or self._page is None:
            self._set_status("請先選取目前頁面的一檔股票。")
            return
        if any(item.stock_code == row.stock_code for item in self._basket):
            self._set_status("比較籃不可重複加入同一股票。")
            return
        if len(self._basket) >= 5:
            self._set_status("比較籃最多五檔股票。")
            return
        self._basket.append(_BasketItem(row.stock_code, self._page.page_index, _scope_identity(recipe)))
        self._update_basket_label()

    def remove_selected_from_comparison(self) -> None:
        row = self._selected_row
        if row is None:
            return
        self._basket = [item for item in self._basket if item.stock_code != row.stock_code]
        self._update_basket_label()

    def clear_comparison(self) -> None:
        self._clear_basket()

    def _clear_basket(self) -> None:
        self._basket.clear()
        self._update_basket_label()

    def _update_basket_label(self) -> None:
        entries = "、".join(f"{item.stock_code}（第 {item.page_index + 1} 頁）" for item in self._basket)
        self.basket_label.setText(f"比較籃：{len(self._basket)}／5" + (f"｜{entries}" if entries else ""))
        self.compare_button.setEnabled(2 <= len(self._basket) <= 5 and not self._has_running_worker())

    def compare_basket(self) -> None:
        if self._recipe is None or self._result is None:
            return
        if not 2 <= len(self._basket) <= 5:
            self._set_status("比較需選擇 2–5 檔股票；未知列仍保留其原始狀態。")
            return
        recipe = self._recipe
        result = self._result
        basket = tuple(self._basket)

        if type(recipe) in (DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2, DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3):
            def compare_daily(handle: ClosableHandle, cancel: Callable[[], bool]) -> tuple[_Row, ...]:
                exact = _exact_v2(handle)
                if exact.result is not result or not _query_matches_recipe(exact.query, recipe):
                    raise ValueError("technical_official_revenue_view_v2_comparison_changed")
                if any(item.scope_identity_sha256 != _scope_identity(recipe) for item in basket):
                    raise ValueError("technical_official_revenue_view_v2_comparison_scope_mismatch")
                found: list[_Row] = []
                for item in basket:
                    page = exact.result.read_page(item.page_index, _recipe_base(recipe).page_size, cancel_callback=cancel)
                    row = next((row for row in page.rows if row.stock_code == item.stock_code), None)
                    if row is None:
                        raise ValueError("technical_official_revenue_view_comparison_stock_missing")
                    found.append(row)
                return tuple(found)
            self._start_v2_task("比較同一每日來源跨頁結果", compare_daily, self._show_comparison)
            return
        if type(result) is not DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV1:
            return

        def task(cancel_callback: Callable[[], object] | None = None) -> tuple[DailyMarketTechnicalOfficialDispositionRevenueResultRowV1, ...]:
            return _read_comparison_rows(
                result, recipe, basket, cancel_callback=cancel_callback,
            )

        self._start_task("比較同一已核驗全域結果中的選取列", task, self._show_comparison)

    def _show_comparison(self, value: object) -> None:
        if not isinstance(value, tuple) or not all(
            type(row) in (DailyMarketTechnicalOfficialDispositionRevenueResultRowV1, DailyMarketTechnicalOfficialDispositionRevenueResultRowV2) for row in value
        ):
            raise ValueError("technical_official_revenue_view_comparison_invalid")
        dialog = QDialog(self)
        dialog.setWindowTitle("月營收研究跨頁比較")
        dialog.resize(1000, 650)
        layout = QVBoxLayout(dialog)
        split = QSplitter(Qt.Orientation.Horizontal, dialog)
        for row in value:
            card = QWidget(split)
            card_layout = QVBoxLayout(card)
            card_layout.addWidget(QLabel(row.stock_code))
            text = QPlainTextEdit(card)
            text.setReadOnly(True)
            text.setPlainText(_row_detail(row))
            card_layout.addWidget(text, 1)
            split.addWidget(card)
        layout.addWidget(split, 1)
        close_button = QPushButton("關閉比較")
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button)
        self.comparisonReady.emit(value)
        dialog.exec()

    def prepare_bookmark(self) -> None:
        if self._selected_row is None or self._page is None or self._recipe is None or self._page_request is None:
            self._set_status("請先選取目前頁面的一檔股票。")
            return
        if type(self._recipe) in (DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2, DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3):
            stock_code = self._selected_row.stock_code
            recipe, page, request, result = self._recipe, self._page, self._page_request, self._result
            if type(page) is not DailyMarketTechnicalOfficialDispositionRevenueQueryPageV2 or type(request) is not DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2:
                return
            def prepare_daily(handle: ClosableHandle, cancel: Callable[[], bool]) -> DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2 | DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3:
                if cancel():
                    raise ValueError("technical_official_revenue_view_cancelled")
                exact = _exact_v2(handle)
                if exact.result is not result or not _query_matches_recipe(exact.query, recipe):
                    raise ValueError("technical_official_revenue_view_v2_bookmark_result_changed")
                if type(recipe) is DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3:
                    if type(exact) is not DailyMarketTechnicalOfficialDispositionRevenueArchivedExactReadV3:
                        raise ValueError("technical_official_revenue_view_archived_bookmark_source_invalid")
                    exact.read_page_request(request, cancel_callback=cancel)
                    return DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3.from_exact_read(exact, stock_code=stock_code, cancel_callback=cancel)
                if type(recipe) is not DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2:
                    raise ValueError("technical_official_revenue_view_v2_bookmark_recipe_invalid")
                return DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2.from_issued_result_page(recipe=recipe, page_request=request, page=page, stock_code=stock_code)
            self._start_v2_task("保存原每日快照研究收藏", prepare_daily, self.bookmarkPrepared.emit)
            return
        if type(self._page) is not DailyMarketTechnicalOfficialDispositionRevenueQueryPageV1 or type(self._page_request) is not DailyMarketTechnicalOfficialDispositionRevenuePageRequestV1:
            return
        try:
            bookmark = DailyMarketTechnicalOfficialDispositionRevenueBookmarkV1.from_issued_result_page(
                recipe=self._recipe,
                page_request=self._page_request,
                page=self._page,
                stock_code=self._selected_row.stock_code,
            )
        except (TypeError, ValueError) as exc:
            self._set_status(f"收藏未建立：{exc}")
            return
        self.bookmarkPrepared.emit(bookmark)
        self._set_status("已準備原月營收研究收藏；儲存不代表重新核驗，重開時會依固定原版本 exact 核驗。")

    def restore_bookmark(self, value: DailyMarketTechnicalOfficialDispositionRevenueBookmarkV1 | DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2 | DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3 | str | bytes) -> bool:
        if not self._can_start() or self.operation_root_parent is None:
            self._set_status("目前忙碌／關閉中，或尚未設定 operation 暫存資料夾。")
            return False
        if type(value) is DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3:
            return self._restore_archived_bookmark(value)
        if type(value) is DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2:
            return self._restore_daily_bookmark(value)
        if isinstance(value, (str, bytes)):
            try:
                archived_bookmark = DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3.from_json(value)
            except (TypeError, ValueError):
                pass
            else:
                return self._restore_archived_bookmark(archived_bookmark)
            try:
                daily_bookmark = DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2.from_json(value)
            except (TypeError, ValueError):
                pass
            else:
                return self._restore_daily_bookmark(daily_bookmark)
        try:
            bookmark = value if type(value) is DailyMarketTechnicalOfficialDispositionRevenueBookmarkV1 else DailyMarketTechnicalOfficialDispositionRevenueBookmarkV1.from_json(value)
        except (TypeError, ValueError) as exc:
            self._set_status(f"研究收藏格式無效：{exc}")
            return False
        parent = self.operation_root_parent

        def task(cancel_callback: Callable[[], object] | None = None) -> _OpenedQuery:
            return _restore_bookmark(bookmark, parent, cancel_callback=cancel_callback)

        self._start_task("依收藏固定雙來源重新核驗", task, self._apply_opened_query)
        return True

    @staticmethod
    def _exact_daily_reader(config: DailyRevenueSourceConfigV2, recipe: DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2 | DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3) -> DailyMonthlyRevenueCohortReader:
        base = recipe.base_recipe if type(recipe) is DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3 else recipe
        pin = DailyMonthlyRevenueCohortPin.from_json(base.monthly_cohort_pin_json)
        cutoff = DailyMarketTechnicalOfficialDispositionQueryV1.from_json(base.f17_query_json).decision_cutoff
        if config.exact_reader_factory is not None:
            reader = config.exact_reader_factory(pin, cutoff)
        elif config.reader is not None:
            reader = config.reader
        else:
            raise ValueError("technical_official_revenue_view_exact_daily_reader_unavailable")
        if reader.pin != pin:
            raise ValueError("technical_official_revenue_view_saved_daily_pin_mismatch")
        return reader

    def _restore_daily_bookmark(self, bookmark: DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2) -> bool:
        config, artifact_root, parent = self.daily_source_config_v2, self.monthly_artifact_root, self.operation_root_parent
        if config is None or artifact_root is None or parent is None:
            self._set_status("每日收藏需原版本參照保存資料夾、operation 資料夾與固定接受設定。")
            return False
        recipe = bookmark.saved_recipe
        def open_saved(cancel: Callable[[], bool]) -> DailyMarketTechnicalOfficialDispositionRevenueExactReadV2:
            if cancel():
                raise ValueError("technical_official_revenue_view_cancelled")
            reader = self._exact_daily_reader(config, recipe)
            if cancel():
                raise ValueError("technical_official_revenue_view_cancelled")
            return reopen_daily_market_technical_official_disposition_revenue_from_recipe_v2(
                recipe, operation_root=_new_operation_root(parent, cancel), monthly_provider=_provider_with_exact_reader(config.provider, reader),
                daily_monthly_cohort_reader=reader, monthly_reference_artifact_root=artifact_root,
                artifact_id=f"ui-{uuid4().hex}", protected_roots=config.protected_roots,
                expected_descriptor_sha256=bookmark.artifact_descriptor_external_sha256,
                expected_monthly_source_reference_sha256=bookmark.monthly_source_reference_external_sha256,
                cancel_callback=cancel,
            )
        def project_saved(handle: ClosableHandle, cancel: Callable[[], bool]) -> _OpenedQuery:
            exact = _exact_v2(handle)
            bookmark.verify_exact_row(exact, cancel_callback=cancel)
            return _project_exact_v2(exact, cancel, bookmark.stock_code)
        return self._start_v2_open("核驗收藏原每日快照與固定雙 SHA", open_saved, project_saved)

    def _restore_archived_bookmark(self, bookmark: DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3) -> bool:
        config, root, parent = self.daily_source_config_v2, self.monthly_artifact_root, self.operation_root_parent
        if config is None or root is None or parent is None:
            self._set_status("封存收藏需原研究保存資料夾、operation 資料夾與固定接受設定。")
            return False
        recipe = bookmark.saved_recipe
        f17 = DailyMarketTechnicalOfficialDispositionQueryV1.from_json(recipe.base_recipe.f17_query_json)
        source = _SourceChoice(f17.bundle_output_root, f17.bundle_identity_sha256,
                               f17.expected_manifest_sha256, recipe.base_recipe.monthly_source_reference_json, "daily_archived_v3")
        def open_saved(cancel: Callable[[], bool]) -> DailyMarketTechnicalOfficialDispositionRevenueArchivedExactReadV3:
            if cancel():
                raise ValueError("technical_official_revenue_view_cancelled")
            reader = self._exact_daily_reader(config, recipe)
            storage = _archived_storage(config, root, source, parent)
            return reopen_daily_market_technical_official_disposition_revenue_archived_from_recipe_v3(
                recipe, operation_root=_new_operation_root(parent, cancel),
                monthly_provider=_provider_with_exact_reader(config.provider, reader), daily_monthly_cohort_reader=reader,
                monthly_reference_artifact_root=storage.monthly_reference_artifact_root, artifact_id=f"ui-{uuid4().hex}",
                archived_reference_artifact_root=storage.archived_reference_artifact_root,
                expected_archive_descriptor_sha256=bookmark.archive_artifact_descriptor_external_sha256,
                expected_archive_reference_sha256=bookmark.archive_reference_external_sha256,
                expected_monthly_source_reference_sha256=bookmark.original_monthly_source_reference_external_sha256,
                protected_roots=config.protected_roots, cancel_callback=cancel,
            )
        def project_saved(handle: ClosableHandle, cancel: Callable[[], bool]) -> _OpenedQuery:
            exact = _exact_v2(handle)
            if type(exact) is not DailyMarketTechnicalOfficialDispositionRevenueArchivedExactReadV3:
                raise ValueError("technical_official_revenue_view_archived_bookmark_source_invalid")
            bookmark.verify_exact_row(exact, cancel_callback=cancel)
            return _project_exact_v2(exact, cancel, bookmark.stock_code)
        return self._start_v2_open("核驗收藏原封存快照與固定版本", open_saved, project_saved)

    def _page_size_changed(self, _value: int) -> None:
        if self._basket:
            self._clear_basket()

    def _clear_issued_state(self) -> None:
        self._source = None
        self._recipe = None
        self._query = None
        self._result = None
        self._page_request = None
        self._page = None
        self._selected_row = None
        self._clear_basket()
        self.results_stack.setCurrentIndex(0)
        self.detail_text.clear()
        self.audit_text.clear()
        self.summary_label.setText("尚無已核驗查詢結果。")
        self.table_model.replace_page(())
        self._set_result_actions_enabled(False)

    def _set_result_actions_enabled(self, enabled: bool) -> None:
        for widget in (
            self.detail_button, self.add_comparison_button, self.remove_comparison_button,
            self.clear_comparison_button, self.compare_button, self.bookmark_button,
            self.open_stock_research_button,
        ):
            widget.setEnabled(enabled)
        page = self._page
        self.previous_page_button.setEnabled(enabled and page is not None and page.page_index > 0)
        self.next_page_button.setEnabled(
            enabled and page is not None and page.page_index + 1 < page.page_count
        )

    def _set_status(self, message: str) -> None:
        self.status_label.setText(message)

    def _can_start(self) -> bool:
        return not self._closing and self._busy_worker is None and not self._v2_busy and not self._has_running_worker()

    def _has_running_worker(self) -> bool:
        if self._source_actor_v2 is not None and self._source_actor_v2.busy:
            return True
        for worker in tuple(self._live_workers):
            try:
                if worker.isRunning():
                    return True
            except RuntimeError:
                self._live_workers.discard(worker)
        return False

    def _ensure_source_actor_v2(self) -> RevenueSourceActorV2:
        if self._source_actor_v2 is None:
            actor = RevenueSourceActorV2()
            self._source_actor_v2 = actor
            actor.succeeded.connect(self._task_finished)
            actor.failed.connect(self._task_error)
            actor.cancelled.connect(self._task_cancelled)
            actor.finished.connect(self._source_actor_finished_v2)
        return self._source_actor_v2

    def _source_actor_finished_v2(self) -> None:
        if self._closing:
            self.close()

    def _reserve_v2_ui(self, kind: str, apply: Callable[[object], None]) -> int | None:
        if not self._can_start():
            self._set_status("已有背景工作；請等待或合作取消後再操作。")
            return None
        self._revision += 1
        self._busy_token = self._revision
        self._worker_kind, self._worker_apply = kind, apply
        self._v2_busy = True
        self._set_controls_busy(True)
        self._set_status(f"背景工作中：{kind}…")
        return self._revision

    def _start_v2_open(self, kind: str, opener: Callable[[Callable[[], bool]], ClosableHandle], project: Callable[[ClosableHandle, Callable[[], bool]], object] = _project_exact_v2) -> bool:
        token = self._reserve_v2_ui(kind, self._apply_opened_query)
        if token is None:
            return False
        if not self._ensure_source_actor_v2().submit_open(token, opener, project):
            self._task_error(token, "來源 actor 拒絕重疊或停止中的請求")
            return False
        return True

    def _start_v2_task(self, kind: str, task: Callable[[ClosableHandle, Callable[[], bool]], object], apply: Callable[[object], None]) -> bool:
        token = self._reserve_v2_ui(kind, apply)
        if token is None:
            return False
        if not self._ensure_source_actor_v2().submit_task(token, task):
            self._task_error(token, "來源 actor 尚無可用來源或已停止")
            return False
        return True

    def _start_task(self, kind: str, task: Callable[..., object], apply: Callable[[object], None]) -> None:
        if not self._can_start():
            self._set_status("已有背景工作；請等待或合作取消後再操作。")
            return
        self._revision += 1
        token = self._revision
        worker = TaskWorker(task)
        self._busy_worker = worker
        self._live_workers.add(worker)
        self._busy_token = token
        self._worker_kind = kind
        self._worker_apply = apply
        _WORKERS.add(worker)
        worker.finished.connect(lambda value, current=token: self._task_finished(current, value))
        worker.error.connect(lambda message, current=token: self._task_error(current, message))
        worker.cancelled.connect(lambda current=token: self._task_cancelled(current))
        worker.native_thread_finished.connect(lambda current=worker: self._native_worker_finished(current))
        worker.finished.connect(lambda _value, current=worker: _WORKERS.discard(current))
        worker.error.connect(lambda _message, current=worker: _WORKERS.discard(current))
        worker.cancelled.connect(lambda current=worker: _WORKERS.discard(current))
        self._set_controls_busy(True)
        self._set_status(f"背景工作中：{kind}…")
        worker.start()

    def _set_controls_busy(self, busy: bool) -> None:
        for widget in (
            self.choose_root_button, self.choose_reference_button, self.choose_operation_root_button,
            self.choose_artifact_root_button,
            self.refresh_catalog_button, self.next_catalog_button, self.catalog_list,
            self.open_candidate_button, self.filter_panel, self.apply_query_button,
            self.clear_filters_button, self.results_table, self.cancel_button,
        ):
            widget.setEnabled(not busy)
        for widget in (
            self.detail_button, self.add_comparison_button, self.remove_comparison_button,
            self.clear_comparison_button, self.compare_button, self.bookmark_button,
        ):
            widget.setEnabled(not busy and self._page is not None)
        self.cancel_button.setEnabled(busy)
        if not busy:
            self.next_catalog_button.setEnabled(self._catalog_cursor is not None)
            self._set_result_actions_enabled(self._page is not None)
            self._update_basket_label()

    def _native_worker_finished(self, worker: TaskWorker) -> None:
        self._live_workers.discard(worker)

    def _finish_task(self, token: int) -> bool:
        current = token == self._busy_token
        if current:
            self._busy_worker = None
            self._v2_busy = False
            self._worker_apply = None
            self._set_controls_busy(False)
        return current and token == self._revision and not self._closing

    def _task_finished(self, token: int, value: object) -> None:
        kind, apply = self._worker_kind, self._worker_apply
        if self._finish_task(token):
            try:
                if apply is not None:
                    apply(value)
                self.operationSettled.emit(kind, True)
            except Exception as exc:
                self._set_status(f"結果未套用，保留目前已核內容：{exc}")
                self.operationSettled.emit(kind, False)
        else:
            self.operationSettled.emit(kind, False)

    def _task_error(self, token: int, message: str) -> None:
        kind = self._worker_kind
        if self._finish_task(token):
            first_line = message.splitlines()[0] if message else "背景工作失敗"
            self._set_status(f"{kind} 失敗；保留目前已核結果：{first_line}")
        self.operationSettled.emit(kind, False)

    def _task_cancelled(self, token: int) -> None:
        kind = self._worker_kind
        if self._finish_task(token):
            self._set_status(f"{kind} 已取消；目前結果維持不變。")
        self.operationSettled.emit(kind, False)

    def cancel_current_operation(self) -> None:
        if self._busy_worker is None and not self._v2_busy:
            return
        if not self._v2_busy:
            self._revision += 1
        if self._busy_worker is not None:
            self._busy_worker.cancel()
        if self._v2_busy and self._source_actor_v2 is not None:
            self._source_actor_v2.cancel_current()
        self._set_status("已送出合作式取消；目前已核結果維持不變。")

    def begin_shutdown(self) -> bool:
        if not self._closing:
            self._closing = True
            self._revision += 1
        running = False
        if self._source_actor_v2 is not None:
            self._source_actor_v2.request_shutdown()
            running = self._source_actor_v2.isRunning()
        for worker in tuple(self._live_workers):
            try:
                worker.cancel(cooperative=True, wait=False)
                if worker.isRunning():
                    running = True
                else:
                    self._live_workers.discard(worker)
            except RuntimeError:
                self._live_workers.discard(worker)
        return not running

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.begin_shutdown():
            super().closeEvent(event)
        else:
            event.ignore()


__all__ = ["DailyMarketTechnicalOfficialDispositionRevenueView"]
