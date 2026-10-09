"""F17 與四均線保存研究的全母體唯讀介面。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
import re
import time
from typing import Literal, Protocol, cast

from PySide6.QtCore import QModelIndex, Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
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
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
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
from app_module.daily_market_technical_official_disposition_ma_bookmark_v1 import (
    DailyMarketTechnicalOfficialDispositionMaBookmarkRestoreContextV1,
    DailyMarketTechnicalOfficialDispositionMaBookmarkV1,
    read_daily_market_technical_official_disposition_ma_bookmark_context_v1,
)
from app_module.daily_market_technical_official_disposition_ma_comparison_v1 import (
    DailyMarketTechnicalOfficialDispositionMaComparisonV1,
    DailyMarketTechnicalOfficialDispositionMaSelectionV1,
)
from app_module.daily_market_technical_official_disposition_ma_query_v1 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_PAGE_SIZE,
    DailyMarketTechnicalOfficialDispositionMaPageRequestV1,
    DailyMarketTechnicalOfficialDispositionMaQueryPageV1,
    DailyMarketTechnicalOfficialDispositionMaQueryV1,
    DailyMarketTechnicalOfficialDispositionMaResultRowV1,
    DailyMarketTechnicalOfficialDispositionMaSortClauseV1,
    DailyMarketTechnicalOfficialDispositionMaVerifiedQueryResultV1,
    MaState,
    UnknownPolicy,
)
from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
    DailyMarketTechnicalOfficialDispositionSortClauseV1,
    DailyMarketTechnicalOfficialDispositionReadSessionV1,
    open_daily_market_technical_official_disposition_bundle_session_v1,
)
from app_module.daily_market_technical_parent_v4_query import (
    DailyMarketTechnicalRuleStateFilterV4,
)
from app_module.daily_market_technical_official_disposition_query_v1 import (
    DailyMarketTechnicalOfficialDispositionQueryV1,
)
from app_module.daily_market_technical_universe_v4_query import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS,
)
from app_module.daily_market_technical_official_disposition_query_v1 import RowScope
from ui_qt.models.saved_research_page_table_model import (
    SavedResearchPageTableModel,
    SavedResearchTableRow,
)
from ui_qt.technical_official_ma_research_presenter import (
    format_technical_official_ma_counts_v1,
    format_technical_official_ma_research_row_v1,
)
from ui_qt.workers.task_worker import TaskWorker


_STATES: tuple[MaState, ...] = ("match", "no_match", "unknown")
_STATE_LABELS = {"match": "符合", "no_match": "不符合", "unknown": "未知"}
_SCOPE_ORDER: tuple[RowScope, ...] = (
    "included_processed",
    "included_pending",
    "excluded",
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
    "reported_upcoming",
    "reported_active",
    "reported_elapsed_only",
    "unknown",
)
_DISPOSAL_LABELS = {
    "reported_upcoming": "已公告、尚未生效",
    "reported_active": "公告處置中",
    "reported_elapsed_only": "只有已經過的處置紀錄",
    "unknown": "未知",
}
_RULE_LABELS = {
    "ma5_20_golden_cross": "MA5／MA20 金叉",
    "kd_golden_cross": "K／D 金叉",
    "macd_golden_cross": "MACD 金叉",
    "volume_ratio_20_including_current": "量能比 20（含當日）",
    "volume_ratio_5_including_current": "量能比 5（含當日）",
}
_SCOPE_SENTINEL = "all_scopes"
_STOCK_CODE_RE = re.compile(r"^[A-Z0-9]{1,16}$")
_MAX_STOCK_FILTER_CHARS = DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS * 17 - 1
_WORKERS: set[TaskWorker] = set()

_SORT_FIELD_LABELS: tuple[tuple[str, str], ...] = (
    ("stock_code", "股票代碼"),
    ("decision_date", "決策日期"),
    ("latest_feature_date", "最新技術觀測日"),
    ("raw_row_count", "已保存來源列數"),
    ("ma_alignment_state", "四均線排列狀態"),
    ("market_assignment.state", "市場狀態"),
    ("market_assignment.snapshot_observed_at", "市場觀察時間"),
    ("official_disposal.state", "處置狀態"),
    ("official_disposal.observed_at", "處置觀察時間"),
    ("official_disposal.observed_date", "處置觀察日期"),
)
for _rule_key in DAILY_MARKET_TECHNICAL_RULE_KEYS_V4:
    for _metric in ("ratio", "numerator", "denominator"):
        _SORT_FIELD_LABELS += (
            (f"{_rule_key}.{_metric}", f"{_RULE_LABELS[_rule_key]}｜{_metric}"),
        )


class _RestoreConditionExecutor(Protocol):
    """bookmark exact context 的公開同來源條件查詢能力。"""

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
    ) -> DailyMarketTechnicalOfficialDispositionMaVerifiedQueryResultV1: ...


@dataclass(frozen=True, slots=True)
class _SourceChoice:
    output_root: str
    bundle_identity_sha256: str
    manifest_sha256: str


@dataclass(frozen=True, slots=True)
class _Conditions:
    row_scope_filter: tuple[RowScope, ...]
    rule_state_filters: tuple[DailyMarketTechnicalRuleStateFilterV4, ...]
    combine_mode: Literal["AND", "OR"]
    market_assignment_states: tuple[str, ...]
    official_disposal_states: tuple[str, ...]
    outer_stock_filter_mode: Literal["all", "explicit_codes"]
    outer_stock_codes: tuple[str, ...]
    f17_sort_clauses: tuple[DailyMarketTechnicalOfficialDispositionSortClauseV1, ...]
    ma_states: tuple[MaState, ...] | None
    condition_combine_mode: Literal["AND", "OR"]
    unknown_policy: UnknownPolicy
    sort_clauses: tuple[DailyMarketTechnicalOfficialDispositionMaSortClauseV1, ...]


@dataclass(frozen=True, slots=True)
class _QueryOpened:
    source: _SourceChoice
    session: DailyMarketTechnicalOfficialDispositionReadSessionV1 | None
    result: DailyMarketTechnicalOfficialDispositionMaVerifiedQueryResultV1
    request: DailyMarketTechnicalOfficialDispositionMaPageRequestV1
    page: DailyMarketTechnicalOfficialDispositionMaQueryPageV1
    restore_context: DailyMarketTechnicalOfficialDispositionMaBookmarkRestoreContextV1 | None = None


@dataclass(frozen=True, slots=True)
class _RestoredBookmark:
    bookmark: DailyMarketTechnicalOfficialDispositionMaBookmarkV1
    context: DailyMarketTechnicalOfficialDispositionMaBookmarkRestoreContextV1
    source: _SourceChoice
    request: DailyMarketTechnicalOfficialDispositionMaPageRequestV1
    page: DailyMarketTechnicalOfficialDispositionMaQueryPageV1
    basket: tuple[DailyMarketTechnicalOfficialDispositionMaSelectionV1, ...]


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionMaViewComparisonV1:
    """本 view 在目前已核 result 上讀出的比較列；不是獨立 source certification。"""

    comparison: DailyMarketTechnicalOfficialDispositionMaComparisonV1
    rows: tuple[DailyMarketTechnicalOfficialDispositionMaResultRowV1, ...]


def _parse_stock_codes(raw: object, *, was_truncated: bool) -> tuple[str, ...]:
    if was_truncated:
        raise ValueError("technical_official_ma_view_stock_filter_too_long")
    if not isinstance(raw, str) or len(raw) > _MAX_STOCK_FILTER_CHARS:
        raise ValueError("technical_official_ma_view_stock_filter_invalid")
    if not raw.strip():
        raise ValueError("technical_official_ma_view_stock_filter_empty")
    groups = re.split(r"[,，]", raw)
    if any(not item.strip() for item in groups):
        raise ValueError("technical_official_ma_view_stock_filter_invalid")
    codes = tuple(token for group in groups for token in group.split())
    if not codes or len(codes) > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS:
        raise ValueError("technical_official_ma_view_stock_filter_limit")
    if any(_STOCK_CODE_RE.fullmatch(code) is None for code in codes):
        raise ValueError("technical_official_ma_view_stock_code_invalid")
    if len(set(codes)) != len(codes):
        raise ValueError("technical_official_ma_view_stock_code_duplicate")
    return tuple(sorted(codes))


class _StockCodeLineEdit(QLineEdit):
    """記錄 Qt 靜默截斷的輸入，不能把有效前綴當成使用者完整條件。"""

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


def _neutral_f17_sort() -> tuple[DailyMarketTechnicalOfficialDispositionSortClauseV1, ...]:
    return (DailyMarketTechnicalOfficialDispositionSortClauseV1("stock_code", "asc"),)


def _execute_new_query(
    source: _SourceChoice,
    conditions: _Conditions,
    *,
    page_index: int,
    page_size: int,
    cancel_callback: Callable[[], object] | None,
) -> _QueryOpened:
    session = open_daily_market_technical_official_disposition_bundle_session_v1(
        bundle_output_root=source.output_root,
        bundle_identity_sha256=source.bundle_identity_sha256,
        expected_manifest_sha256=source.manifest_sha256,
        row_scope_filter=conditions.row_scope_filter,
        rule_state_filters=conditions.rule_state_filters,
        combine_mode=conditions.combine_mode,
        market_assignment_states=conditions.market_assignment_states,
        official_disposal_states=conditions.official_disposal_states,
        outer_stock_filter_mode=conditions.outer_stock_filter_mode,
        outer_stock_codes=conditions.outer_stock_codes,
        sort_clauses=conditions.f17_sort_clauses,
        cancel_callback=cancel_callback,
    )
    query = session.create_ma_query_v1(
        ma_states=conditions.ma_states,
        condition_combine_mode=conditions.condition_combine_mode,
        unknown_policy=conditions.unknown_policy,
        sort_clauses=conditions.sort_clauses,
    )
    result = session.execute_ma_query_v1(query, cancel_callback=cancel_callback)
    request = DailyMarketTechnicalOfficialDispositionMaPageRequestV1.create(
        result.query, page_index=page_index, page_size=page_size,
    )
    page = result.read_page_request(request, cancel_callback=cancel_callback)
    if cancel_callback is not None:
        value = cancel_callback()
        if type(value) is not bool:
            raise ValueError("technical_official_ma_view_cancel_callback_invalid")
        if value:
            raise ValueError("technical_official_ma_view_cancelled")
    return _QueryOpened(source, session, result, request, page)


def _execute_same_session_query(
    session: DailyMarketTechnicalOfficialDispositionReadSessionV1,
    source: _SourceChoice,
    conditions: _Conditions,
    *,
    page_index: int,
    page_size: int,
    cancel_callback: Callable[[], object] | None,
) -> _QueryOpened:
    conditioned = session.with_conditions(
        row_scope_filter=conditions.row_scope_filter,
        rule_state_filters=conditions.rule_state_filters,
        combine_mode=conditions.combine_mode,
        market_assignment_states=conditions.market_assignment_states,
        official_disposal_states=conditions.official_disposal_states,
        outer_stock_filter_mode=conditions.outer_stock_filter_mode,
        outer_stock_codes=conditions.outer_stock_codes,
        sort_clauses=conditions.f17_sort_clauses,
        cancel_callback=cancel_callback,
    )
    query = conditioned.create_ma_query_v1(
        ma_states=conditions.ma_states,
        condition_combine_mode=conditions.condition_combine_mode,
        unknown_policy=conditions.unknown_policy,
        sort_clauses=conditions.sort_clauses,
    )
    result = conditioned.execute_ma_query_v1(query, cancel_callback=cancel_callback)
    request = DailyMarketTechnicalOfficialDispositionMaPageRequestV1.create(
        query, page_index=page_index, page_size=page_size,
    )
    page = result.read_page_request(request, cancel_callback=cancel_callback)
    return _QueryOpened(source, conditioned, result, request, page)


def _execute_restored_conditions(
    context: DailyMarketTechnicalOfficialDispositionMaBookmarkRestoreContextV1,
    source: _SourceChoice,
    conditions: _Conditions,
    *,
    page_index: int,
    page_size: int,
    cancel_callback: Callable[[], object] | None,
) -> _QueryOpened:
    method = getattr(context, "execute_query_conditions", None)
    if not callable(method):
        raise ValueError("restore_condition_requery_unavailable")
    executor = cast(_RestoreConditionExecutor, context)
    result = executor.execute_query_conditions(
        row_scope_filter=conditions.row_scope_filter,
        rule_state_filters=conditions.rule_state_filters,
        combine_mode=conditions.combine_mode,
        market_assignment_states=conditions.market_assignment_states,
        official_disposal_states=conditions.official_disposal_states,
        outer_stock_filter_mode=conditions.outer_stock_filter_mode,
        outer_stock_codes=conditions.outer_stock_codes,
        f17_sort_clauses=conditions.f17_sort_clauses,
        ma_states=conditions.ma_states,
        condition_combine_mode=conditions.condition_combine_mode,
        unknown_policy=conditions.unknown_policy,
        sort_clauses=conditions.sort_clauses,
        cancel_callback=cancel_callback,
    )
    request = DailyMarketTechnicalOfficialDispositionMaPageRequestV1.create(
        result.query, page_index=page_index, page_size=page_size,
    )
    page = result.read_page_request(request, cancel_callback=cancel_callback)
    return _QueryOpened(source, None, result, request, page, context)


def _read_bookmark_context(
    bookmark: DailyMarketTechnicalOfficialDispositionMaBookmarkV1,
    *,
    cancel_callback: Callable[[], object] | None,
) -> _RestoredBookmark:
    context = read_daily_market_technical_official_disposition_ma_bookmark_context_v1(
        bookmark,
        cancel_callback=cancel_callback,
    )
    state = context.state
    query = context.query
    selected = state.selected.selection
    request = DailyMarketTechnicalOfficialDispositionMaPageRequestV1.create(
        query,
        page_index=selected.page_index,
        page_size=selected.page_size,
    )
    if request.request_identity_sha256 != selected.page_request_identity_sha256:
        raise ValueError("technical_official_ma_view_restore_request_mismatch")
    page = context.read_page_request(request, cancel_callback=cancel_callback)
    exact_selected = DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_page(
        page, selected.stock_code,
    )
    if exact_selected.to_dict() != selected.to_dict():
        raise ValueError("technical_official_ma_view_restore_selection_mismatch")
    comparisons = tuple(item.selection for item in state.comparison_selections)
    if tuple(item.to_dict() for item in comparisons) != tuple(
        item.to_dict() for item in bookmark.comparison_selections
    ):
        raise ValueError("technical_official_ma_view_restore_comparison_mismatch")
    if cancel_callback is not None:
        value = cancel_callback()
        if type(value) is not bool or value:
            raise ValueError("technical_official_ma_view_cancelled")
    source = _SourceChoice(
        query.f17_query.bundle_output_root,
        query.f17_query.bundle_identity_sha256,
        query.f17_query.expected_manifest_sha256,
    )
    return _RestoredBookmark(bookmark, context, source, request, page, comparisons)


class DailyMarketTechnicalOfficialDispositionMaView(QWidget):
    """以明示保存來源建立 MA/F17 全母體結果，不使用 latest 或 producer。"""

    stockSelected = Signal(object)
    bookmarkPrepared = Signal(object)
    comparisonReady = Signal(object)
    operationSettled = Signal(str, bool)

    def __init__(self, bundle_output_root: str | Path | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.bundle_output_root = Path(bundle_output_root) if bundle_output_root is not None else None
        self._catalog_cursor: str | None = None
        self._catalog_entries: tuple[DailyMarketTechnicalOfficialDispositionBundleCatalogEntryV1, ...] = ()
        self._source: _SourceChoice | None = None
        self._session: DailyMarketTechnicalOfficialDispositionReadSessionV1 | None = None
        self._restore_context: DailyMarketTechnicalOfficialDispositionMaBookmarkRestoreContextV1 | None = None
        self._result: DailyMarketTechnicalOfficialDispositionMaVerifiedQueryResultV1 | None = None
        self._page_request: DailyMarketTechnicalOfficialDispositionMaPageRequestV1 | None = None
        self._page: DailyMarketTechnicalOfficialDispositionMaQueryPageV1 | None = None
        self._selected_row: DailyMarketTechnicalOfficialDispositionMaResultRowV1 | None = None
        self._detail_selection: DailyMarketTechnicalOfficialDispositionMaSelectionV1 | None = None
        self._basket: list[DailyMarketTechnicalOfficialDispositionMaSelectionV1] = []
        self._busy_worker: TaskWorker | None = None
        self._live_workers: set[TaskWorker] = set()
        self._revision = 0
        self._busy_token = 0
        self._worker_kind = ""
        self._worker_apply: Callable[[object], None] | None = None
        self._closing = False
        self._build_ui()
        self._set_status(
            "尚未選擇保存來源資料夾；候選清單只讀 manifest，尚未核驗。"
            if self.bundle_output_root is None
            else "請更新已保存來源清單，再明確選取一個版本。"
        )

    @property
    def current_result(self) -> DailyMarketTechnicalOfficialDispositionMaVerifiedQueryResultV1 | None:
        return self._result

    @property
    def current_query(self) -> DailyMarketTechnicalOfficialDispositionMaQueryV1 | None:
        if self._result is not None:
            return self._result.query
        if self._restore_context is not None:
            return self._restore_context.query
        return None

    @property
    def current_page(self) -> DailyMarketTechnicalOfficialDispositionMaQueryPageV1 | None:
        return self._page

    @property
    def comparison_basket(self) -> tuple[DailyMarketTechnicalOfficialDispositionMaSelectionV1, ...]:
        return tuple(self._basket)

    @property
    def active_worker(self) -> TaskWorker | None:
        return self._busy_worker

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        self.page_scroll = QScrollArea(self)
        self.page_scroll.setObjectName("technicalOfficialMaPageScroll")
        self.page_scroll.setWidgetResizable(True)
        page_body = QWidget()
        page_body.setObjectName("technicalOfficialMaPageBody")
        self.page_body = page_body
        body = QVBoxLayout(page_body)
        body_margins = body.contentsMargins()
        body.setContentsMargins(5, body_margins.top(), 5, body_margins.bottom())
        self.page_scroll.setWidget(page_body)
        outer.addWidget(self.page_scroll, 1)

        heading = QLabel("官方市場／處置與四均線研究")
        heading.setStyleSheet("font-size: 18px; font-weight: 600;")
        body.addWidget(heading)
        self.qualification_label = QLabel(
            "研究範圍：current-only；官方 available_at 未知；不具歷史 PIT 資格。"
            "來源沿明示保存版本核驗，來源不持續監測。"
        )
        self.qualification_label.setWordWrap(True)
        body.addWidget(self.qualification_label)

        source_box = QGroupBox("保存來源")
        source_box.setObjectName("technicalOfficialMaSourceBox")
        source_layout = QVBoxLayout(source_box)
        self.root_label = QLabel(str(self.bundle_output_root) if self.bundle_output_root else "尚未選擇")
        self.root_label.setObjectName("technicalOfficialMaSourceRoot")
        self.root_label.setWordWrap(True)
        self.choose_root_button = QPushButton("選擇保存來源資料夾")
        self.choose_root_button.setObjectName("technicalOfficialMaChooseRoot")
        self.choose_root_button.clicked.connect(self.choose_bundle_output_root)
        self.refresh_catalog_button = QPushButton("更新來源清單")
        self.refresh_catalog_button.setObjectName("technicalOfficialMaRefreshCatalog")
        self.refresh_catalog_button.clicked.connect(self.refresh_catalog)
        self.next_catalog_button = QPushButton("下一頁候選")
        self.next_catalog_button.setObjectName("technicalOfficialMaNextCatalog")
        self.next_catalog_button.clicked.connect(self.load_next_catalog_page)
        source_layout.addWidget(self.root_label)
        source_actions = QGridLayout()
        source_actions.addWidget(self.choose_root_button, 0, 0, 1, 2)
        source_actions.addWidget(self.refresh_catalog_button, 1, 0, 1, 2)
        source_actions.addWidget(self.next_catalog_button, 2, 0, 1, 2)
        source_layout.addLayout(source_actions)
        self.catalog_list = QListWidget()
        self.catalog_list.setObjectName("technicalOfficialMaCatalog")
        self.catalog_list.setMinimumHeight(100)
        source_layout.addWidget(self.catalog_list)
        candidate_row = QHBoxLayout()
        self.open_candidate_button = QPushButton("核驗並開啟所選保存版本")
        self.open_candidate_button.setObjectName("technicalOfficialMaOpenCandidate")
        self.open_candidate_button.clicked.connect(self.open_selected_candidate)
        self.open_candidate_button.setMinimumHeight(36)
        candidate_row.addWidget(self.open_candidate_button)
        source_layout.addLayout(candidate_row)
        body.addWidget(source_box)

        self.filter_panel = self._build_filter_panel()
        body.addWidget(self.filter_panel)
        self.apply_query_button = QPushButton("套用條件並重新全域查詢")
        self.apply_query_button.clicked.connect(self.apply_filters)
        self.clear_filters_button = QPushButton("清除條件")
        self.clear_filters_button.clicked.connect(self.clear_filters)
        self.cancel_button = QPushButton("取消背景工作")
        self.cancel_button.clicked.connect(self.cancel_current_operation)
        action_row = QGridLayout()
        action_row.addWidget(self.apply_query_button, 0, 0, 1, 2)
        action_row.addWidget(self.clear_filters_button, 1, 0)
        action_row.addWidget(self.cancel_button, 1, 1)
        for button in (self.apply_query_button, self.clear_filters_button, self.cancel_button):
            button.setMinimumHeight(36)
        body.addLayout(action_row)

        self.results_stack = QStackedWidget()
        self.results_stack.setObjectName("technicalOfficialMaResultStack")
        results_panel = QWidget()
        results = QVBoxLayout(results_panel)
        self.counts_label = QLabel("尚未核驗保存來源。")
        self.counts_label.setWordWrap(True)
        results.addWidget(self.counts_label)
        nav = QHBoxLayout()
        self.previous_page_button = QPushButton("上一頁")
        self.previous_page_button.clicked.connect(lambda: self.navigate_page(self._page_index() - 1))
        self.page_label = QLabel("第 0 / 0 頁")
        self.next_page_button = QPushButton("下一頁")
        self.next_page_button.clicked.connect(lambda: self.navigate_page(self._page_index() + 1))
        nav.addWidget(self.previous_page_button)
        nav.addWidget(self.page_label)
        nav.addWidget(self.next_page_button)
        results.addLayout(nav)
        self.results_table = QTableView()
        self.results_table.setObjectName("technicalOfficialMaResults")
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.results_table.setSortingEnabled(False)
        self.results_table.setMinimumHeight(240)
        self.results_model = SavedResearchPageTableModel[
            DailyMarketTechnicalOfficialDispositionMaResultRowV1
        ](
            ("代碼", "範圍", "技術 truth", "均線 truth", "複合 truth", "市場", "處置", "觀測日"),
            maximum_page_size=DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_PAGE_SIZE,
            parent=self.results_table,
        )
        self.results_table.setModel(self.results_model)
        self.results_table.selectionModel().selectionChanged.connect(
            lambda _selected, _deselected: self._table_selection_changed()
        )
        results.addWidget(self.results_table)
        row_actions = QGridLayout()
        self.detail_button = QPushButton("查看保存事實")
        self.detail_button.clicked.connect(self.show_selected_detail)
        self.add_comparison_button = QPushButton("加入跨頁比較")
        self.add_comparison_button.clicked.connect(self.add_selected_to_comparison)
        self.remove_comparison_button = QPushButton("從比較移除")
        self.remove_comparison_button.clicked.connect(self.remove_selected_from_comparison)
        self.compare_button = QPushButton("讀取並比較 2–5 檔")
        self.compare_button.clicked.connect(self.compare_basket)
        self.bookmark_button = QPushButton("準備四均線研究收藏")
        self.bookmark_button.clicked.connect(self.prepare_bookmark)
        self.result_action_buttons = (
            self.detail_button,
            self.add_comparison_button,
            self.remove_comparison_button,
            self.compare_button,
            self.bookmark_button,
        )
        for button in self.result_action_buttons:
            button.setMinimumHeight(38)
        row_actions.addWidget(self.detail_button, 0, 0)
        row_actions.addWidget(self.add_comparison_button, 0, 1)
        row_actions.addWidget(self.remove_comparison_button, 1, 0)
        row_actions.addWidget(self.compare_button, 1, 1)
        row_actions.addWidget(self.bookmark_button, 2, 0, 1, 2)
        results.addLayout(row_actions)
        self.basket_label = QLabel("比較清單：0 檔")
        self.basket_label.setWordWrap(True)
        results.addWidget(self.basket_label)
        self.results_stack.addWidget(results_panel)

        detail_panel = QWidget()
        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.addWidget(QLabel("個股保存事實；返回後保留原查詢與選取。"))
        self.detail_text = QPlainTextEdit()
        self.detail_text.setObjectName("technicalOfficialMaDetailText")
        self.detail_text.setReadOnly(True)
        self.detail_text.setMinimumHeight(260)
        detail_layout.addWidget(self.detail_text, 1)
        self.audit_toggle = QCheckBox("展開完整稽核資料")
        self.audit_toggle.toggled.connect(self._set_audit_visible)
        detail_layout.addWidget(self.audit_toggle)
        self.audit_text = QPlainTextEdit()
        self.audit_text.setObjectName("technicalOfficialMaAuditJson")
        self.audit_text.setReadOnly(True)
        self.audit_text.setMinimumHeight(260)
        self.audit_text.setVisible(False)
        detail_layout.addWidget(self.audit_text, 1)
        self.back_button = QPushButton("返回原結果頁")
        self.back_button.clicked.connect(self.return_to_results)
        detail_layout.addWidget(self.back_button)
        self.results_stack.addWidget(detail_panel)
        body.addWidget(self.results_stack, 1)

        self.status_label = QLabel("")
        self.status_label.setObjectName("technicalOfficialMaStatus")
        self.status_label.setWordWrap(True)
        outer.addWidget(self.status_label)
        self.next_catalog_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self._set_result_actions_enabled(False)

    def _build_filter_panel(self) -> QWidget:
        panel = QGroupBox("全母體條件與排序")
        panel_layout = QVBoxLayout(panel)
        scope_box = QGroupBox("母體列範圍（固定外層資格）")
        scope_layout = QHBoxLayout(scope_box)
        self.scope_checks: dict[RowScope, QCheckBox] = {}
        for value in _SCOPE_ORDER:
            check = QCheckBox(_SCOPE_LABELS[value])
            check.setChecked(True)
            self.scope_checks[value] = check
            scope_layout.addWidget(check)
        panel_layout.addWidget(scope_box)

        technical_box = QGroupBox("五項技術規則；每項可選一種以上保存狀態")
        technical_layout = QVBoxLayout(technical_box)
        self.technical_combine_box = QComboBox()
        self.technical_combine_box.addItem("五規則 AND", "AND")
        self.technical_combine_box.addItem("五規則 OR", "OR")
        technical_layout.addWidget(self.technical_combine_box)
        self.rule_state_checks: dict[str, dict[MaState, QCheckBox]] = {}
        for key in DAILY_MARKET_TECHNICAL_RULE_KEYS_V4:
            row = QVBoxLayout()
            row.addWidget(QLabel(_RULE_LABELS[key]))
            state_row = QHBoxLayout()
            self.rule_state_checks[key] = {}
            for state in _STATES:
                check = QCheckBox(_STATE_LABELS[state])
                self.rule_state_checks[key][state] = check
                state_row.addWidget(check)
            row.addLayout(state_row)
            technical_layout.addLayout(row)
        panel_layout.addWidget(technical_box)

        ma_box = QGroupBox("四均線排列條件")
        ma_layout = QHBoxLayout(ma_box)
        self.ma_state_checks: dict[MaState, QCheckBox] = {}
        for state in _STATES:
            check = QCheckBox(_STATE_LABELS[state])
            self.ma_state_checks[state] = check
            ma_layout.addWidget(check)
        panel_layout.addWidget(ma_box)

        combo_box = QGroupBox("技術與四均線的合併及未知政策")
        combo_layout = QFormLayout(combo_box)
        self.condition_combine_box = QComboBox()
        self.condition_combine_box.addItem("技術 AND 四均線", "AND")
        self.condition_combine_box.addItem("技術 OR 四均線", "OR")
        combo_layout.addRow("合併方式", self.condition_combine_box)
        self.unknown_policy_box = QComboBox()
        self.unknown_policy_box.addItem("未知列納入結果", "include")
        self.unknown_policy_box.addItem("未知列排除", "exclude")
        self.unknown_policy_box.addItem("只看未知列", "only")
        combo_layout.addRow("未知政策", self.unknown_policy_box)
        panel_layout.addWidget(combo_box)

        official_box = QGroupBox("官方來源條件（外層硬條件，不受 OR 繞過）")
        official_layout = QVBoxLayout(official_box)
        self.market_filter_enabled = QCheckBox("限制市場狀態")
        official_layout.addWidget(self.market_filter_enabled)
        self.market_checks = self._check_group(
            official_layout,
            _MARKET_STATES,
            _MARKET_LABELS,
            prefix="market",
        )
        self.disposal_filter_enabled = QCheckBox("限制處置狀態")
        official_layout.addWidget(self.disposal_filter_enabled)
        self.disposal_checks = self._check_group(
            official_layout,
            _DISPOSAL_STATES,
            _DISPOSAL_LABELS,
            prefix="disposal",
        )
        panel_layout.addWidget(official_box)

        stock_box = QGroupBox("股票代碼條件（全母體交集）")
        stock_layout = QHBoxLayout(stock_box)
        self.stock_filter_enabled = QCheckBox("啟用")
        self.stock_code_input = _StockCodeLineEdit()
        self.stock_code_input.setPlaceholderText("逗號、中文逗號或空白分隔，例如 2330, 2317")
        stock_layout.addWidget(self.stock_filter_enabled)
        stock_layout.addWidget(self.stock_code_input, 1)
        panel_layout.addWidget(stock_box)

        page_row = QHBoxLayout()
        page_row.addWidget(QLabel("每頁筆數"))
        self.page_size_box = QSpinBox()
        self.page_size_box.setRange(1, DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_MA_MAX_PAGE_SIZE)
        self.page_size_box.setValue(100)
        page_row.addWidget(self.page_size_box)
        panel_layout.addLayout(page_row)

        sort_box = QGroupBox("全母體排序（升降序未知值皆置尾，股票代碼穩定排序）")
        self.sort_rows_layout = QVBoxLayout(sort_box)
        self.sort_rows: list[tuple[QComboBox, QComboBox, QPushButton, QWidget]] = []
        self._add_sort_clause_row("stock_code", "asc")
        sort_actions = QHBoxLayout()
        self.add_sort_button = QPushButton("增加排序欄")
        self.add_sort_button.clicked.connect(self.add_sort_clause)
        sort_actions.addWidget(self.add_sort_button)
        self.sort_rows_layout.addLayout(sort_actions)
        panel_layout.addWidget(sort_box)
        return panel

    @staticmethod
    def _check_group(
        parent_layout: QVBoxLayout,
        states: Sequence[str],
        labels: Mapping[str, str],
        *,
        prefix: str,
    ) -> dict[str, QCheckBox]:
        grid = QGridLayout()
        checks: dict[str, QCheckBox] = {}
        for index, value in enumerate(states):
            check = QCheckBox(labels[value])
            check.setObjectName(f"{prefix}_{value}")
            checks[value] = check
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
        field_box.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        field_box.setMinimumContentsLength(12)
        field_box.setMinimumWidth(0)
        for value, label in _SORT_FIELD_LABELS:
            field_box.addItem(label, value)
        if field is not None:
            index = field_box.findData(field)
            if index >= 0:
                field_box.setCurrentIndex(index)
        direction_box = QComboBox()
        direction_box.addItem("升冪", "asc")
        direction_box.addItem("降冪", "desc")
        direction_index = direction_box.findData(direction)
        if direction_index >= 0:
            direction_box.setCurrentIndex(direction_index)
        remove_button = QPushButton("移除")
        remove_button.clicked.connect(
            lambda _checked=False, controls=(field_box, direction_box, remove_button, row_widget): self._remove_sort_clause_row(controls)
        )
        field_box.currentIndexChanged.connect(
            lambda _index, current_field=field_box, current_direction=direction_box: self._sync_stock_sort_direction(current_field, current_direction)
        )
        row_layout.addWidget(field_box, 0, 0, 1, 2)
        row_layout.addWidget(direction_box, 1, 0)
        row_layout.addWidget(remove_button, 1, 1)
        row_layout.setColumnStretch(0, 1)
        self.sort_rows_layout.addWidget(row_widget)
        self.sort_rows.append((field_box, direction_box, remove_button, row_widget))
        self._sync_stock_sort_direction(field_box, direction_box)

    @staticmethod
    def _sync_stock_sort_direction(field_box: QComboBox, direction_box: QComboBox) -> None:
        del field_box
        direction_box.setEnabled(True)

    def _remove_sort_clause_row(
        self,
        controls: tuple[QComboBox, QComboBox, QPushButton, QWidget],
    ) -> None:
        if controls not in self.sort_rows or len(self.sort_rows) <= 1:
            return
        self.sort_rows.remove(controls)
        self.sort_rows_layout.removeWidget(controls[3])
        controls[3].deleteLater()
        self.add_sort_button.setEnabled(len(self.sort_rows) < 33)

    def add_sort_clause(self) -> None:
        if len(self.sort_rows) >= 33:
            self._set_status("排序欄位最多 33 個。")
            return
        self._add_sort_clause_row("latest_feature_date", "desc")
        self.add_sort_button.setEnabled(len(self.sort_rows) < 33)

    def choose_bundle_output_root(self) -> None:
        if not self._can_start():
            self._set_status("背景工作進行中或畫面正在關閉，暫時不能更換來源資料夾。")
            return
        selected = QFileDialog.getExistingDirectory(
            self,
            "選擇已保存來源資料夾",
            str(self.bundle_output_root) if self.bundle_output_root else "",
            QFileDialog.Option.ShowDirsOnly,
        )
        if selected:
            self.set_bundle_output_root(selected)

    def set_bundle_output_root(self, root: str | Path) -> bool:
        if not self._can_start():
            self._set_status("背景工作進行中或畫面正在關閉，不能更換來源。")
            return False
        candidate = Path(root)
        if not candidate.is_absolute() or not candidate.exists() or not candidate.is_dir():
            self._set_status("來源資料夾必須是已存在的絕對路徑。")
            return False
        self.bundle_output_root = candidate
        self.root_label.setText(str(candidate))
        self._catalog_cursor = None
        self._catalog_entries = ()
        self.catalog_list.clear()
        self._source = None
        self._session = None
        self._restore_context = None
        self._result = None
        self._page_request = None
        self._page = None
        self._selected_row = None
        self._detail_selection = None
        self._basket.clear()
        self.results_stack.setCurrentIndex(0)
        self.detail_text.clear()
        self.audit_text.clear()
        self._render_page()
        self._update_basket_label()
        self._set_status("來源資料夾已選擇；按「更新來源清單」後才盤點候選版本。")
        return True

    def refresh_catalog(self) -> None:
        if self.bundle_output_root is None:
            self._set_status("尚未選擇保存來源資料夾；沒有掃描候選。")
            return
        root = self.bundle_output_root

        def task(cancel_callback: Callable[[], object] | None = None) -> DailyMarketTechnicalOfficialDispositionBundleCatalogPageV1:
            return DailyMarketTechnicalOfficialDispositionBundleCatalogV1(root).list_page(
                limit=DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_CATALOG_DEFAULT_LIMIT,
                cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
            )

        self._start_task("盤點保存來源清單", task, self._apply_catalog_page)

    def load_next_catalog_page(self) -> None:
        if self.bundle_output_root is None or self._catalog_cursor is None:
            self._set_status("目前沒有可安全續讀的來源清單。")
            return
        root = self.bundle_output_root
        cursor = self._catalog_cursor

        def task(cancel_callback: Callable[[], object] | None = None) -> DailyMarketTechnicalOfficialDispositionBundleCatalogPageV1:
            return DailyMarketTechnicalOfficialDispositionBundleCatalogV1(root).list_page(
                limit=DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_CATALOG_DEFAULT_LIMIT,
                cursor=cursor,
                cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
            )

        self._start_task("續讀保存來源清單", task, self._append_catalog_page)

    def _apply_catalog_page(self, value: object) -> None:
        if not isinstance(value, DailyMarketTechnicalOfficialDispositionBundleCatalogPageV1):
            raise ValueError("technical_official_ma_view_catalog_result_invalid")
        self._catalog_entries = value.entries
        self._catalog_cursor = value.next_cursor if value.scan_complete else None
        self._render_catalog()
        self.next_catalog_button.setEnabled(value.scan_complete and value.next_cursor is not None)
        self._set_status(
            f"候選清單盤點 {value.scanned_entry_count} 項；列出的資訊未核驗，請明確選取版本。"
            if value.scan_complete
            else f"來源清單不完整：{value.diagnostic_code or 'unknown'}；不能續讀。"
        )

    def _append_catalog_page(self, value: object) -> None:
        if not isinstance(value, DailyMarketTechnicalOfficialDispositionBundleCatalogPageV1):
            raise ValueError("technical_official_ma_view_catalog_result_invalid")
        if not value.scan_complete:
            self._catalog_cursor = None
            self._set_status(f"來源清單漂移或不完整：{value.diagnostic_code or 'unknown'}。")
            return
        self._catalog_entries = (*self._catalog_entries, *value.entries)
        self._catalog_cursor = value.next_cursor
        self._render_catalog()
        self.next_catalog_button.setEnabled(value.next_cursor is not None)
        self._set_status("來源清單已續讀；metadata 仍未授予研究資格。")

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
            self._set_status("請明確選取一個可嘗試核驗的保存版本。")
            return
        entry = self._catalog_entries[index]
        if not entry.can_attempt_exact_read or entry.metadata is None or self.bundle_output_root is None:
            self._set_status("此候選只是診斷或 metadata，不能開啟研究結果。")
            return
        source = _SourceChoice(
            str(self.bundle_output_root),
            entry.metadata.bundle_identity_sha256,
            entry.metadata.manifest_sha256,
        )
        try:
            conditions = self._read_conditions()
        except (TypeError, ValueError) as exc:
            self._set_status(f"條件無效：{exc}")
            return
        page_size = self.page_size_box.value()

        def task(cancel_callback: Callable[[], object] | None = None) -> _QueryOpened:
            return _execute_new_query(
                source, conditions, page_index=0, page_size=page_size,
                cancel_callback=cancel_callback,
            )

        self._start_task("核驗並執行全母體查詢", task, self._apply_opened_query)

    def _read_conditions(self) -> _Conditions:
        scopes = tuple(scope for scope in _SCOPE_ORDER if self.scope_checks[scope].isChecked())
        if not scopes:
            raise ValueError("technical_official_ma_view_row_scope_empty")
        rule_filters: list[DailyMarketTechnicalRuleStateFilterV4] = []
        for rule_key, checks in self.rule_state_checks.items():
            states = tuple(state for state in _STATES if checks[state].isChecked())
            if states:
                rule_filters.append(DailyMarketTechnicalRuleStateFilterV4.create(rule_key, states))
        market_states = tuple(value for value in _MARKET_STATES if self.market_checks[value].isChecked())
        disposal_states = tuple(value for value in _DISPOSAL_STATES if self.disposal_checks[value].isChecked())
        if self.market_filter_enabled.isChecked() and not market_states:
            raise ValueError("technical_official_ma_view_market_state_required")
        if not self.market_filter_enabled.isChecked() and market_states:
            raise ValueError("technical_official_ma_view_market_filter_disabled_with_values")
        if self.disposal_filter_enabled.isChecked() and not disposal_states:
            raise ValueError("technical_official_ma_view_disposal_state_required")
        if not self.disposal_filter_enabled.isChecked() and disposal_states:
            raise ValueError("technical_official_ma_view_disposal_filter_disabled_with_values")
        if self.stock_filter_enabled.isChecked():
            codes = _parse_stock_codes(
                self.stock_code_input.text(),
                was_truncated=self.stock_code_input.was_truncated,
            )
            stock_mode: Literal["all", "explicit_codes"] = "explicit_codes"
        else:
            if self.stock_code_input.text().strip():
                raise ValueError("technical_official_ma_view_stock_filter_disabled_with_values")
            codes = ()
            stock_mode = "all"

        ma_states = tuple(state for state in _STATES if self.ma_state_checks[state].isChecked())
        sort_clauses: list[DailyMarketTechnicalOfficialDispositionMaSortClauseV1] = []
        seen: set[str] = set()
        if not self.sort_rows or len(self.sort_rows) > 33:
            raise ValueError("technical_official_ma_view_sort_count_invalid")
        for field_box, direction_box, _remove, _widget in self.sort_rows:
            field = field_box.currentData()
            direction = direction_box.currentData()
            if not isinstance(field, str) or not isinstance(direction, str) or direction not in {"asc", "desc"}:
                raise ValueError("technical_official_ma_view_sort_invalid")
            if field in seen:
                raise ValueError("technical_official_ma_view_sort_duplicate")
            seen.add(field)
            sort_clauses.append(
                DailyMarketTechnicalOfficialDispositionMaSortClauseV1(
                    field,
                    cast(Literal["asc", "desc"], direction),
                )
            )
        f17_sort = _neutral_f17_sort()
        return _Conditions(
            row_scope_filter=scopes,
            rule_state_filters=tuple(rule_filters),
            combine_mode=cast(Literal["AND", "OR"], self.technical_combine_box.currentData()),
            market_assignment_states=market_states if self.market_filter_enabled.isChecked() else (),
            official_disposal_states=disposal_states if self.disposal_filter_enabled.isChecked() else (),
            outer_stock_filter_mode=stock_mode,
            outer_stock_codes=codes,
            f17_sort_clauses=f17_sort,
            ma_states=ma_states or None,
            condition_combine_mode=cast(Literal["AND", "OR"], self.condition_combine_box.currentData()),
            unknown_policy=cast(UnknownPolicy, self.unknown_policy_box.currentData()),
            sort_clauses=tuple(sort_clauses),
        )

    def apply_filters(self) -> None:
        if self._source is None:
            self._set_status("請先從保存來源清單明確選取一個版本。")
            return
        try:
            conditions = self._read_conditions()
        except (TypeError, ValueError) as exc:
            self._set_status(f"條件無效：{exc}")
            return
        page_size = self.page_size_box.value()
        source = self._source
        session = self._session
        context = self._restore_context
        if session is None and context is None:
            self._set_status("目前來源沒有可重用的已核工作階段；請重新選取保存版本。")
            return

        def task(cancel_callback: Callable[[], object] | None = None) -> _QueryOpened:
            if context is not None:
                return _execute_restored_conditions(
                    context, source, conditions, page_index=0, page_size=page_size,
                    cancel_callback=cancel_callback,
                )
            return _execute_same_session_query(
                cast(DailyMarketTechnicalOfficialDispositionReadSessionV1, session),
                source, conditions, page_index=0, page_size=page_size,
                cancel_callback=cancel_callback,
            )

        self._start_task("沿原保存來源重新全域查詢", task, self._apply_opened_query)

    def clear_filters(self) -> None:
        for scope in _SCOPE_ORDER:
            self.scope_checks[scope].setChecked(True)
        for checks in self.rule_state_checks.values():
            for check in checks.values():
                check.setChecked(False)
        for check in self.ma_state_checks.values():
            check.setChecked(False)
        self.technical_combine_box.setCurrentIndex(self.technical_combine_box.findData("AND"))
        self.condition_combine_box.setCurrentIndex(self.condition_combine_box.findData("AND"))
        self.unknown_policy_box.setCurrentIndex(self.unknown_policy_box.findData("include"))
        self.market_filter_enabled.setChecked(False)
        self.disposal_filter_enabled.setChecked(False)
        for check in (*self.market_checks.values(), *self.disposal_checks.values()):
            check.setChecked(False)
        self.stock_filter_enabled.setChecked(False)
        self.stock_code_input.clear()
        for controls in tuple(self.sort_rows[1:]):
            self._remove_sort_clause_row(controls)
        field_box, direction_box, _remove, _row = self.sort_rows[0]
        field_box.setCurrentIndex(field_box.findData("stock_code"))
        direction_box.setCurrentIndex(direction_box.findData("asc"))
        self.apply_filters()

    def _apply_opened_query(self, value: object) -> None:
        if type(value) is not _QueryOpened:
            raise ValueError("technical_official_ma_view_query_result_invalid")
        result = value.result
        page = value.page
        if (
            page.operation_identity_sha256 != result.operation_identity_sha256
            or page.query.query_identity_sha256 != result.query.query_identity_sha256
            or page.source_pins != result.source_pins
        ):
            raise ValueError("technical_official_ma_view_page_result_mismatch")
        self._source = value.source
        self._session = value.session
        self._restore_context = value.restore_context
        self._result = result
        self._page_request = value.request
        self._page = page
        self._selected_row = None
        self._detail_selection = None
        self._basket.clear()
        self.results_stack.setCurrentIndex(0)
        self._render_page()
        self._set_result_actions_enabled(True)
        self._set_status("已沿選取保存版本完成全母體查詢；official available_at 仍未知。")

    def navigate_page(self, page_index: int) -> None:
        if self._closing or self._busy_worker is not None or self._page is None:
            return
        if not 0 <= page_index < self._page.page_count:
            self._set_status("頁碼超出目前全域結果範圍。")
            return
        query = self._page.query
        request = DailyMarketTechnicalOfficialDispositionMaPageRequestV1.create(
            query,
            page_index=page_index,
            page_size=self._page_size_for_query(),
        )
        result = self._result
        context = self._restore_context

        def task(cancel_callback: Callable[[], object] | None = None) -> tuple[
            DailyMarketTechnicalOfficialDispositionMaPageRequestV1,
            DailyMarketTechnicalOfficialDispositionMaQueryPageV1,
        ]:
            if result is not None and result.query.query_identity_sha256 == query.query_identity_sha256:
                page = result.read_page_request(request, cancel_callback=cancel_callback)
            elif context is not None:
                page = context.read_page_request(request, cancel_callback=cancel_callback)
            else:
                raise ValueError("technical_official_ma_view_page_context_unavailable")
            return request, page

        self._start_task("讀取全域排序中的指定頁", task, self._apply_page)

    def _apply_page(self, value: object) -> None:
        if (
            not isinstance(value, tuple)
            or len(value) != 2
            or not isinstance(value[0], DailyMarketTechnicalOfficialDispositionMaPageRequestV1)
            or not isinstance(value[1], DailyMarketTechnicalOfficialDispositionMaQueryPageV1)
        ):
            raise ValueError("technical_official_ma_view_page_result_invalid")
        request, page = value
        if page.request_identity_sha256 != request.request_identity_sha256:
            raise ValueError("technical_official_ma_view_page_request_mismatch")
        self._page_request = request
        self._page = page
        self._selected_row = None
        self._detail_selection = None
        self.results_stack.setCurrentIndex(0)
        self._render_page()
        self._set_status("已讀取同一全域排序結果的另一頁。")

    def _render_page(self) -> None:
        self.results_table.clearSelection()
        self.results_table.setCurrentIndex(QModelIndex())
        self._selected_row = None
        page = self._page
        if page is None:
            self.results_model.replace_page(())
            self.counts_label.setText("尚未核驗保存來源。")
            self.page_label.setText("第 0 / 0 頁")
            self.previous_page_button.setEnabled(False)
            self.next_page_button.setEnabled(False)
            return
        self.counts_label.setText(format_technical_official_ma_counts_v1(
            page.counts,
            result_status=page.result_status,
            official_coverage_status=page.official_source_coverage_status,
        ))
        table_rows: list[SavedResearchTableRow[DailyMarketTechnicalOfficialDispositionMaResultRowV1]] = []
        for row in page.rows:
            fact = row.fact_row.to_dict()
            market = fact.get("market_assignment")
            disposal = fact.get("official_disposal")
            market_state = market.get("state") if isinstance(market, Mapping) else "unknown"
            disposal_state = disposal.get("state") if isinstance(disposal, Mapping) else "unknown"
            feature_day = row.technical_row.latest_feature_date if row.technical_row is not None else None
            cells = (
                row.stock_code,
                _SCOPE_LABELS.get(row.filter_evaluation.row_scope, "未知"),
                _STATE_LABELS.get(row.technical_condition_truth, "未評估"),
                _STATE_LABELS.get(row.ma_condition_truth, "未評估"),
                _STATE_LABELS.get(row.composite_condition_truth, "未知"),
                _MARKET_LABELS.get(str(market_state), "未知"),
                _DISPOSAL_LABELS.get(str(disposal_state), "未知"),
                feature_day.isoformat() if feature_day is not None else "未提供",
            )
            table_rows.append(SavedResearchTableRow(row.stock_code, row, cells, cells))
        self.results_model.replace_page(tuple(table_rows))
        self.page_label.setText(
            "第 0 / 0 頁（0 筆可見）"
            if page.page_count == 0
            else f"第 {page.page_index + 1} / {page.page_count} 頁"
        )
        self.previous_page_button.setEnabled(page.page_index > 0)
        self.next_page_button.setEnabled(page.page_index + 1 < page.page_count)
        self._update_basket_label()

    def _page_size_for_query(self) -> int:
        if self._page_request is not None:
            return self._page_request.page_size
        return self.page_size_box.value()

    def _page_index(self) -> int:
        return self._page.page_index if self._page is not None else 0

    def _table_selection_changed(self) -> None:
        index = self.results_table.currentIndex()
        self._selected_row = self.results_model.row_at(index.row()) if index.isValid() else None

    def select_stock_code(self, stock_code: str) -> bool:
        index = self.results_model.index_for_stock(stock_code)
        if not index.isValid():
            return False
        self.results_table.setCurrentIndex(index)
        self.results_table.selectRow(index.row())
        self._selected_row = self.results_model.row_at(index.row())
        return self._selected_row is not None

    def _selection_for_row(self, row: DailyMarketTechnicalOfficialDispositionMaResultRowV1) -> DailyMarketTechnicalOfficialDispositionMaSelectionV1:
        if self._page is None:
            raise ValueError("technical_official_ma_view_page_unavailable")
        return DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_page(
            self._page, row.stock_code,
        )

    def show_selected_detail(self) -> None:
        row = self._selected_row
        if row is None or self._page is None:
            self._set_status("請先選取一列。")
            return
        try:
            selection = self._selection_for_row(row)
        except (TypeError, ValueError) as exc:
            self._set_status(f"無法核對個股頁：{exc}")
            return
        self._detail_selection = selection
        self.detail_text.setPlainText(format_technical_official_ma_research_row_v1(row))
        self.audit_text.setPlainText(
            json.dumps(row.to_dict(), ensure_ascii=False, indent=2, default=str)
        )
        self.audit_toggle.setChecked(False)
        self.audit_toggle.setText("展開完整稽核資料")
        self.results_stack.setCurrentIndex(1)
        self.stockSelected.emit(selection)

    def _set_audit_visible(self, visible: bool) -> None:
        self.audit_text.setVisible(visible)
        self.audit_toggle.setText("收合完整稽核資料" if visible else "展開完整稽核資料")

    def return_to_results(self) -> None:
        if self._detail_selection is not None and self._page is not None:
            if (
                self._detail_selection.query_identity_sha256
                != self._page.query.query_identity_sha256
                or self._detail_selection.page_identity_sha256 != self._page.page_identity_sha256
            ):
                self._set_status("返回頁面身份已改變；請重新選取股票。")
                self._detail_selection = None
                self.results_stack.setCurrentIndex(0)
                return
        self.results_stack.setCurrentIndex(0)

    def add_selected_to_comparison(self) -> None:
        row = self._selected_row
        if row is None:
            self._set_status("請先選取一列。")
            return
        if row.filter_evaluation.row_scope != "included_processed" or not row.hard_filter_match:
            self._set_status("比較籃只收納外層資格成立且已處理的列；條件未知仍保留未知，不補數值。")
            return
        if any(item.stock_code == row.stock_code for item in self._basket):
            self._set_status("這檔股票已在比較籃。")
            return
        if len(self._basket) >= 5:
            self._set_status("比較籃最多 5 檔。")
            return
        try:
            self._basket.append(self._selection_for_row(row))
        except (TypeError, ValueError) as exc:
            self._set_status(f"不能加入比較：{exc}")
            return
        self._update_basket_label()
        self._set_status("已加入此頁核驗列；比較籃可跨頁並固定同一來源與查詢。")

    def remove_selected_from_comparison(self) -> None:
        if self._selected_row is None:
            self._set_status("請先選取要移除的股票。")
            return
        self._basket = [item for item in self._basket if item.stock_code != self._selected_row.stock_code]
        self._update_basket_label()

    def _update_basket_label(self) -> None:
        codes = "、".join(item.stock_code for item in self._basket)
        self.basket_label.setText(f"比較清單：{len(self._basket)} 檔" + (f"（{codes}）" if codes else ""))
        self.compare_button.setEnabled(
            self._busy_worker is None and 2 <= len(self._basket) <= 5 and not self._closing
        )

    def compare_basket(self) -> None:
        query = self.current_query
        if query is None or not 2 <= len(self._basket) <= 5:
            self._set_status("比較需要同一已核研究條件下 2–5 檔；可跨頁選取。")
            return
        selections = tuple(self._basket)
        if any(item.query_identity_sha256 != query.query_identity_sha256 for item in selections):
            self._set_status("比較籃與目前查詢不一致；先清除條件或重新加入。")
            return

        def task(cancel_callback: Callable[[], object] | None = None) -> DailyMarketTechnicalOfficialDispositionMaViewComparisonV1:
            pages: dict[str, DailyMarketTechnicalOfficialDispositionMaQueryPageV1] = {}
            verified_rows: list[DailyMarketTechnicalOfficialDispositionMaResultRowV1] = []
            for selection in selections:
                if cancel_callback is not None:
                    value = cancel_callback()
                    if type(value) is not bool or value:
                        raise ValueError("technical_official_ma_view_cancelled")
                request = DailyMarketTechnicalOfficialDispositionMaPageRequestV1.create(
                    query, page_index=selection.page_index, page_size=selection.page_size,
                )
                if request.request_identity_sha256 != selection.page_request_identity_sha256:
                    raise ValueError("technical_official_ma_view_comparison_request_mismatch")
                page = pages.get(request.request_identity_sha256)
                if page is None:
                    page = self._read_page_for_query(request, cancel_callback)
                    page.to_dict()
                    pages[request.request_identity_sha256] = page
                actual = DailyMarketTechnicalOfficialDispositionMaSelectionV1.from_page(
                    page, selection.stock_code,
                )
                if actual.to_dict() != selection.to_dict():
                    raise ValueError("technical_official_ma_view_comparison_selection_mismatch")
                row = next((item for item in page.rows if item.stock_code == selection.stock_code), None)
                if row is None:
                    raise ValueError("technical_official_ma_view_comparison_row_missing")
                verified_rows.append(row)
            comparison = DailyMarketTechnicalOfficialDispositionMaComparisonV1.create(query, selections)
            if cancel_callback is not None:
                value = cancel_callback()
                if type(value) is not bool or value:
                    raise ValueError("technical_official_ma_view_cancelled")
            return DailyMarketTechnicalOfficialDispositionMaViewComparisonV1(comparison, tuple(verified_rows))

        self._start_task("重讀跨頁比較列", task, self._apply_comparison)

    def _read_page_for_query(
        self,
        request: DailyMarketTechnicalOfficialDispositionMaPageRequestV1,
        cancel_callback: Callable[[], object] | None,
    ) -> DailyMarketTechnicalOfficialDispositionMaQueryPageV1:
        result = self._result
        context = self._restore_context
        if result is not None and result.query.query_identity_sha256 == request.query.query_identity_sha256:
            return result.read_page_request(request, cancel_callback=cancel_callback)
        if context is not None:
            return context.read_page_request(request, cancel_callback=cancel_callback)
        raise ValueError("technical_official_ma_view_comparison_context_unavailable")

    def _apply_comparison(self, value: object) -> None:
        if type(value) is not DailyMarketTechnicalOfficialDispositionMaViewComparisonV1:
            raise ValueError("technical_official_ma_view_comparison_result_invalid")
        if len(value.rows) != len(value.comparison.selections):
            raise ValueError("technical_official_ma_view_comparison_result_incomplete")
        self.comparisonReady.emit(value)
        dialog = QDialog(self)
        dialog.setWindowTitle("同一研究查詢的跨頁比較")
        dialog.resize(900, 620)
        layout = QVBoxLayout(dialog)
        intro = QLabel("各欄依原頁請求重讀；來源 pin 逐欄保留，不推定官方可用時間或歷史 PIT。")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        scroll = QScrollArea(dialog)
        scroll.setWidgetResizable(True)
        content = QWidget()
        columns = QHBoxLayout(content)
        for row in value.rows:
            column = QPlainTextEdit(content)
            column.setReadOnly(True)
            column.setMinimumWidth(320)
            column.setPlainText(format_technical_official_ma_research_row_v1(row))
            columns.addWidget(column)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        close_button = QPushButton("關閉")
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button)
        dialog.show()
        self._comparison_dialog = dialog
        self._set_status("已按原 query／來源重讀並呈現跨頁比較列。")

    def prepare_bookmark(self) -> None:
        if self._page is None or self._page_request is None or self._selected_row is None:
            self._set_status("請先選取一列，再準備原研究收藏。")
            return
        try:
            bookmark = DailyMarketTechnicalOfficialDispositionMaBookmarkV1.create(
                query=self._page.query,
                page=self._page,
                stock_code=self._selected_row.stock_code,
                scroll_position=self.page_scroll.verticalScrollBar().value(),
                comparison_selections=tuple(self._basket),
            )
        except (TypeError, ValueError) as exc:
            self._set_status(f"無法準備收藏：{exc}")
            return
        self.bookmarkPrepared.emit(bookmark)
        self._set_status("已準備四均線原研究收藏；重新開啟會依保存來源 fresh exact 核驗。")

    def restore_bookmark(self, value: DailyMarketTechnicalOfficialDispositionMaBookmarkV1 | str | bytes) -> bool:
        """以一個 background exact open 原子重開收藏並回報是否已啟動。"""

        if self._closing or self._busy_worker is not None or self._has_running_worker():
            self._set_status("背景工作中或畫面正在關閉；收藏尚未重開。")
            return False
        try:
            if type(value) is DailyMarketTechnicalOfficialDispositionMaBookmarkV1:
                bookmark = DailyMarketTechnicalOfficialDispositionMaBookmarkV1.from_json(value.to_json())
            elif isinstance(value, (str, bytes)):
                bookmark = DailyMarketTechnicalOfficialDispositionMaBookmarkV1.from_json(value)
            else:
                raise ValueError("technical_official_ma_view_bookmark_type_invalid")
        except (TypeError, ValueError) as exc:
            self._set_status(f"收藏無效：{exc}")
            return False

        def task(cancel_callback: Callable[[], object] | None = None) -> _RestoredBookmark:
            return _read_bookmark_context(bookmark, cancel_callback=cancel_callback)

        self._start_task("重開四均線研究收藏", task, self._apply_restored_bookmark)
        return True

    def _apply_restored_bookmark(self, value: object) -> None:
        if type(value) is not _RestoredBookmark:
            raise ValueError("technical_official_ma_view_restore_result_invalid")
        self._source = value.source
        self._session = None
        self._restore_context = value.context
        self._result = None
        self._page_request = value.request
        self._page = value.page
        self._selected_row = next(
            (row for row in value.page.rows if row.stock_code == value.bookmark.selected.stock_code),
            None,
        )
        if self._selected_row is None:
            raise ValueError("technical_official_ma_view_restore_selected_row_missing")
        self._basket = list(value.basket)
        self.page_size_box.setValue(value.request.page_size)
        self._apply_query_controls(value.bookmark.query)
        self.results_stack.setCurrentIndex(0)
        self._render_page()
        self.select_stock_code(value.bookmark.selected.stock_code)
        self._set_result_actions_enabled(True)
        self._set_status("收藏已沿原保存來源完成 fresh exact 重開；來源不持續監測。")

    def _apply_query_controls(self, query: DailyMarketTechnicalOfficialDispositionMaQueryV1) -> None:
        f17 = query.f17_query
        for scope, check in self.scope_checks.items():
            check.setChecked(scope in f17.row_scope_filter)
        for rule_key, checks in self.rule_state_checks.items():
            saved = next(
                (item for item in f17.technical_query.rule_state_filters if item.rule_key == rule_key),
                None,
            )
            for state, check in checks.items():
                check.setChecked(saved is not None and state in saved.states)
        self.technical_combine_box.setCurrentIndex(self.technical_combine_box.findData(f17.technical_query.combine_mode))
        for state, check in self.ma_state_checks.items():
            check.setChecked(query.ma_states is not None and state in query.ma_states)
        self.condition_combine_box.setCurrentIndex(self.condition_combine_box.findData(query.condition_combine_mode))
        self.unknown_policy_box.setCurrentIndex(self.unknown_policy_box.findData(query.unknown_policy))
        self.market_filter_enabled.setChecked(bool(f17.market_assignment_states))
        for state, check in self.market_checks.items():
            check.setChecked(state in f17.market_assignment_states)
        self.disposal_filter_enabled.setChecked(bool(f17.official_disposal_states))
        for state, check in self.disposal_checks.items():
            check.setChecked(state in f17.official_disposal_states)
        explicit = f17.outer_stock_filter_mode == "explicit_codes"
        self.stock_filter_enabled.setChecked(explicit)
        self.stock_code_input.setText(",".join(f17.outer_stock_codes) if explicit else "")
        clauses = query.sort_clauses
        if not clauses:
            raise ValueError("technical_official_ma_view_restore_ma_sort_missing")
        while len(self.sort_rows) > 1:
            self._remove_sort_clause_row(self.sort_rows[-1])
        first_field, first_direction, _remove, _row = self.sort_rows[0]
        field_index = first_field.findData(clauses[0].field)
        if field_index < 0:
            raise ValueError("technical_official_ma_view_restore_sort_field_invalid")
        first_field.setCurrentIndex(field_index)
        direction_index = first_direction.findData(clauses[0].direction)
        if direction_index < 0:
            raise ValueError("technical_official_ma_view_restore_sort_direction_invalid")
        first_direction.setCurrentIndex(direction_index)
        for clause in clauses[1:]:
            self._add_sort_clause_row(clause.field, clause.direction)
        self.add_sort_button.setEnabled(len(self.sort_rows) < 33)

    def _set_result_actions_enabled(self, enabled: bool) -> None:
        for widget in (
            self.detail_button,
            self.add_comparison_button,
            self.remove_comparison_button,
            self.compare_button,
            self.bookmark_button,
        ):
            widget.setEnabled(enabled)
        page = self._page
        can_navigate = enabled and page is not None
        self.previous_page_button.setEnabled(
            can_navigate and page is not None and page.page_index > 0
        )
        self.next_page_button.setEnabled(
            can_navigate and page is not None and page.page_index + 1 < page.page_count
        )

    def _set_status(self, message: str) -> None:
        self.status_label.setText(message)

    def _can_start(self) -> bool:
        return not self._closing and self._busy_worker is None and not self._has_running_worker()

    def _has_running_worker(self) -> bool:
        for worker in tuple(self._live_workers):
            try:
                if worker.isRunning():
                    return True
            except RuntimeError:
                self._live_workers.discard(worker)
        return False

    def _start_task(self, kind: str, task: Callable[..., object], apply: Callable[[object], None]) -> None:
        if not self._can_start():
            self._set_status("已有背景工作；請等待或取消後再操作。")
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
            self.choose_root_button,
            self.refresh_catalog_button,
            self.next_catalog_button,
            self.catalog_list,
            self.open_candidate_button,
            self.filter_panel,
            self.apply_query_button,
            self.clear_filters_button,
            self.page_size_box,
            self.results_table,
            self.cancel_button,
        ):
            widget.setEnabled(not busy)
        for widget in self.result_action_buttons:
            widget.setEnabled(not busy and self._page is not None)
        self.previous_page_button.setEnabled(
            not busy and self._page is not None and self._page.page_index > 0
        )
        self.next_page_button.setEnabled(
            not busy
            and self._page is not None
            and self._page.page_index + 1 < self._page.page_count
        )
        self.cancel_button.setEnabled(busy)
        if not busy:
            self.next_catalog_button.setEnabled(self._catalog_cursor is not None)
            self._set_result_actions_enabled(self._page is not None)
            self._update_basket_label()

    def _native_worker_finished(self, worker: TaskWorker) -> None:
        self._live_workers.discard(worker)

    def _finish_task(self, token: int) -> bool:
        if token == self._busy_token:
            self._busy_worker = None
            self._worker_apply = None
            self._set_controls_busy(False)
        return token == self._busy_token and token == self._revision and not self._closing

    def _task_finished(self, token: int, value: object) -> None:
        kind = self._worker_kind
        apply = self._worker_apply
        if self._finish_task(token):
            try:
                if apply is not None:
                    apply(value)
                self.operationSettled.emit(kind, True)
            except Exception as exc:
                self._set_status(f"結果未套用，保留目前內容：{exc}")
                self.operationSettled.emit(kind, False)
        else:
            self.operationSettled.emit(kind, False)

    def _task_error(self, token: int, message: str) -> None:
        kind = self._worker_kind
        if self._finish_task(token):
            code = message.splitlines()[0] if message else "背景工作失敗"
            self._set_status(f"{kind} 失敗；保留目前已核結果：{code}")
        self.operationSettled.emit(kind, False)

    def _task_cancelled(self, token: int) -> None:
        kind = self._worker_kind
        if self._finish_task(token):
            self._set_status(f"{kind} 已取消；目前結果維持不變。")
        self.operationSettled.emit(kind, False)

    def cancel_current_operation(self) -> None:
        if self._busy_worker is None:
            return
        self._revision += 1
        self._busy_worker.cancel()
        self._set_status("已送出合作式取消；目前已核結果維持不變。")

    def begin_shutdown(self) -> bool:
        """合作取消背景工作，僅在所有 native QThread 終止後回傳 True。"""

        if not self._closing:
            self._closing = True
            self._revision += 1
        still_running = False
        for worker in tuple(self._live_workers):
            try:
                worker.cancel(cooperative=True, wait=False)
                if worker.isRunning():
                    still_running = True
                else:
                    self._live_workers.discard(worker)
            except RuntimeError:
                self._live_workers.discard(worker)
        return not still_running

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.begin_shutdown():
            super().closeEvent(event)
        else:
            event.ignore()


__all__ = [
    "DailyMarketTechnicalOfficialDispositionMaView",
    "DailyMarketTechnicalOfficialDispositionMaViewComparisonV1",
    "format_technical_official_ma_counts_v1",
    "format_technical_official_ma_research_row_v1",
]
