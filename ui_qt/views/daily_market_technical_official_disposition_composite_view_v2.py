"""官方市場、技術四群與 F07 價格閘門的唯讀 V2 研究視圖。"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
from typing import Literal, cast

from PySide6.QtCore import QModelIndex, QTimer, Qt, Signal
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
    QSizePolicy,
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
from app_module.daily_market_technical_official_disposition_composite_query_v1 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_PAGE_SIZE,
    DailyMarketTechnicalOfficialDispositionCompositeQueryV1,
    DailyMarketTechnicalOfficialDispositionCompositeSortClauseV1,
    KDJState,
    MaState,
)
from app_module.daily_market_technical_official_disposition_composite_query_v2 import (
    DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2,
    DailyMarketTechnicalOfficialDispositionCompositeQueryV2,
    DailyMarketTechnicalOfficialDispositionCompositeResultRowV2,
    DailyMarketTechnicalOfficialDispositionCompositeSortClauseV2,
    DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2,
    execute_composite_query_v2,
)
from app_module.daily_market_technical_official_disposition_composite_bookmark_v2 import (
    DailyMarketTechnicalOfficialDispositionCompositeBookmarkRestoreContextV2,
    DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2,
    DailyMarketTechnicalOfficialDispositionCompositeSelectionV2,
    DailyMarketTechnicalOfficialDispositionCompositeVerifiedSelectionV2,
    read_daily_market_technical_official_disposition_composite_bookmark_context_v2,
)
from app_module.daily_market_technical_official_disposition_composite_bookmark_storage_v2 import (
    DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2,
)
from app_module.daily_market_technical_official_disposition_query_v1 import (
    DailyMarketTechnicalOfficialDispositionSortClauseV1,
    RowScope,
)
from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
    open_daily_market_technical_official_disposition_bundle_projection_group_session_v3,
)
from app_module.daily_market_technical_parent_v4_query import (
    DailyMarketTechnicalRuleStateFilterV4,
)
from app_module.daily_market_technical_universe_v4_query import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS,
)
from app_module.daily_market_technical_universe_projection_group_session_v3 import (
    DailyMarketTechnicalUniverseProjectionGroupSessionV3,
)
from ui_qt.models.saved_research_page_table_model import (
    SavedResearchPageTableModel,
    SavedResearchTableRow,
)
from ui_qt.technical_official_composite_research_presenter_v2 import (
    format_composite_counts_v2,
    format_composite_row_v2,
    present_composite_page_v2,
    present_composite_row_v2,
)
from ui_qt.workers.task_worker import TaskWorker


_STATE_ORDER: tuple[Literal["match"], Literal["no_match"], Literal["unknown"]] = (
    "match", "no_match", "unknown",
)
_SCOPES: tuple[RowScope, ...] = (
    "included_processed", "included_pending", "excluded",
)
_SCOPE_LABELS = {
    "included_processed": "納入且已處理",
    "included_pending": "納入但待處理",
    "excluded": "明示排除",
}
_RULE_LABELS = {
    "ma5_20_golden_cross": "MA5／MA20 金叉",
    "kd_golden_cross": "K／D 金叉",
    "macd_golden_cross": "MACD 金叉",
    "volume_ratio_20_including_current": "量能比 20（含當日）",
    "volume_ratio_5_including_current": "量能比 5（含當日）",
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
    "reported_elapsed_only": "只有已經過的處置紀錄",
    "unknown": "未知",
}
_SORT_OPTIONS = (
    ("stock_code", "股票代碼（固定升冪）"),
    ("decision_date", "決策日期"),
    ("latest_feature_date", "最新技術觀測日"),
    ("raw_row_count", "保存來源列數"),
    ("market_assignment.state", "市場狀態"),
    ("official_disposal.state", "處置狀態"),
    ("ma_alignment_state", "四均線狀態"),
    ("kdj_state", "KDJ 狀態"),
    ("bollinger_bandwidth_pct", "Bandwidth（percent）"),
    ("atr14_pct", "ATR14 SMA（percent）"),
    ("price.close_price", "F07 收盤價"),
)
_TRUTH_LABELS = {
    "match": "符合",
    "no_match": "不符合",
    "unknown": "未知",
    "not_evaluated": "未評估",
    "not_applicable": "不適用",
}
_STOCK_CODE_RE = re.compile(r"^[A-Z0-9]{1,16}$")
_WORKERS_V2: set[TaskWorker] = set()
_RESTORE_SCROLL_MAX_ATTEMPTS_V2 = 12


@dataclass(frozen=True, slots=True)
class _SourceChoiceV2:
    output_root: str
    bundle_identity_sha256: str
    manifest_sha256: str


@dataclass(frozen=True, slots=True)
class _ConditionsV2:
    row_scope_filter: tuple[RowScope, ...]
    rule_state_filters: tuple[DailyMarketTechnicalRuleStateFilterV4, ...]
    technical_combine_mode: Literal["AND", "OR"]
    market_assignment_states: tuple[str, ...]
    official_disposal_states: tuple[str, ...]
    outer_stock_filter_mode: Literal["all", "explicit_codes"]
    outer_stock_codes: tuple[str, ...]
    ma_states: tuple[MaState, ...] | None
    kdj_states: tuple[KDJState, ...] | None
    bandwidth_min_pct: Decimal | None
    bandwidth_max_pct: Decimal | None
    atr14_min_pct: Decimal | None
    atr14_max_pct: Decimal | None
    condition_combine_mode: Literal["AND", "OR"]
    unknown_policy: Literal["include", "exclude", "only"]
    min_close_price: Decimal | None
    max_close_price: Decimal | None
    min_inclusive: bool
    max_inclusive: bool
    unknown_price_policy: Literal["include", "exclude", "only"]
    sort_field: str
    sort_direction: Literal["asc", "desc"]


@dataclass(frozen=True, slots=True)
class _OpenedQueryV2:
    source: _SourceChoiceV2
    projection_group_session: DailyMarketTechnicalUniverseProjectionGroupSessionV3
    result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2
    page: DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2
    page_size: int


@dataclass(frozen=True, slots=True)
class _RestoredBookmarkV2:
    envelope: DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2
    projection_group_session: DailyMarketTechnicalUniverseProjectionGroupSessionV3
    context: DailyMarketTechnicalOfficialDispositionCompositeBookmarkRestoreContextV2


@dataclass(frozen=True, slots=True)
class _BasketItemV2:
    selection: DailyMarketTechnicalOfficialDispositionCompositeSelectionV2
    page: DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2


@dataclass(slots=True)
class _PendingScrollRestoreV2:
    generation: int
    operation_kind: str
    result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2
    page: DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2
    operation_identity_sha256: str
    page_identity_sha256: str
    stock_code: str
    row_identity_sha256: str
    target_value: int
    attempts: int = 0
    last_minimum: int | None = None
    last_maximum: int | None = None
    stable_range_observations: int = 0


def _cancel_check_v2(callback: Callable[[], object] | None) -> None:
    if callback is None:
        return
    if not callable(callback):
        raise ValueError("technical_official_composite_view_v2_cancel_callback_invalid")
    value = callback()
    if type(value) is not bool:
        raise ValueError("technical_official_composite_view_v2_cancel_callback_invalid")
    if value:
        raise ValueError("technical_official_composite_view_v2_cancelled")


def _parse_codes_v2(raw: str, *, was_truncated: bool) -> tuple[str, ...]:
    if was_truncated:
        raise ValueError("technical_official_composite_view_v2_stock_filter_truncated")
    codes = tuple(sorted(set(part.strip().upper() for part in re.split(r"[,\s]+", raw) if part.strip())))
    if (
        not codes
        or len(codes) > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS
        or any(_STOCK_CODE_RE.fullmatch(code) is None for code in codes)
    ):
        raise ValueError("technical_official_composite_view_v2_stock_filter_invalid")
    return codes


def _decimal_input_v2(edit: QLineEdit) -> Decimal | None:
    raw = edit.text().strip()
    if not raw:
        return None
    if len(raw.encode("utf-8")) > 128:
        raise ValueError("technical_official_composite_view_v2_decimal_too_long")
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("technical_official_composite_view_v2_decimal_invalid") from exc
    if not value.is_finite():
        raise ValueError("technical_official_composite_view_v2_decimal_invalid")
    return value


def _neutral_f17_sort_v2() -> tuple[DailyMarketTechnicalOfficialDispositionSortClauseV1, ...]:
    return (DailyMarketTechnicalOfficialDispositionSortClauseV1("stock_code", "asc"),)


def _execute_fresh_query_v2(
    source: _SourceChoiceV2,
    conditions: _ConditionsV2,
    *,
    page_size: int,
    cancel_callback: Callable[[], object] | None,
) -> _OpenedQueryV2:
    """沿同一 caller-owned V3 exact group 執行四群與共通 F07 gate。"""
    _cancel_check_v2(cancel_callback)
    group = open_daily_market_technical_official_disposition_bundle_projection_group_session_v3(
        bundle_output_root=source.output_root,
        bundle_identity_sha256=source.bundle_identity_sha256,
        expected_manifest_sha256=source.manifest_sha256,
        row_scope_filter=conditions.row_scope_filter,
        rule_state_filters=conditions.rule_state_filters,
        combine_mode=conditions.technical_combine_mode,
        market_assignment_states=conditions.market_assignment_states,
        official_disposal_states=conditions.official_disposal_states,
        outer_stock_filter_mode=conditions.outer_stock_filter_mode,
        outer_stock_codes=conditions.outer_stock_codes,
        sort_clauses=_neutral_f17_sort_v2(),
        cancel_callback=cancel_callback,
    )
    _cancel_check_v2(cancel_callback)
    f17_query = group.exact_f17_query
    base_query = DailyMarketTechnicalOfficialDispositionCompositeQueryV1.create(
        f17_query,
        projection_group_session_identity_sha256=group.identity_sha256,
        ma_states=conditions.ma_states,
        kdj_states=conditions.kdj_states,
        bandwidth_min_pct=conditions.bandwidth_min_pct,
        bandwidth_max_pct=conditions.bandwidth_max_pct,
        atr14_min_pct=conditions.atr14_min_pct,
        atr14_max_pct=conditions.atr14_max_pct,
        condition_combine_mode=conditions.condition_combine_mode,
        unknown_policy=conditions.unknown_policy,
        sort_clauses=(DailyMarketTechnicalOfficialDispositionCompositeSortClauseV1(
            "stock_code", "asc",
        ),),
    )
    query = DailyMarketTechnicalOfficialDispositionCompositeQueryV2.create(
        base_query,
        min_close_price=conditions.min_close_price,
        max_close_price=conditions.max_close_price,
        min_inclusive=conditions.min_inclusive,
        max_inclusive=conditions.max_inclusive,
        unknown_price_policy=conditions.unknown_price_policy,
        sort_clauses=(DailyMarketTechnicalOfficialDispositionCompositeSortClauseV2(
            conditions.sort_field,
            conditions.sort_direction,
        ),),
    )
    result = execute_composite_query_v2(
        query,
        group,
        cancel_callback=cancel_callback,
    )
    page = result.read_page(0, page_size, cancel_callback=cancel_callback)
    _cancel_check_v2(cancel_callback)
    return _OpenedQueryV2(source, group, result, page, page_size)


def _restore_bookmark_v2(
    envelope: DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2,
    *,
    cancel_callback: Callable[[], object] | None,
) -> _RestoredBookmarkV2:
    """從收藏內 saved F17 pins exact-open 一次，再由 bookmark reader 重驗。"""
    _cancel_check_v2(cancel_callback)
    typed_envelope = DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2.from_json(
        envelope.to_json()
    )
    bookmark = DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2.from_json(
        typed_envelope.bookmark_json
    )
    f17 = bookmark.query.base_query.f17_query
    source = _SourceChoiceV2(
        f17.bundle_output_root,
        f17.bundle_identity_sha256,
        f17.expected_manifest_sha256,
    )
    group = open_daily_market_technical_official_disposition_bundle_projection_group_session_v3(
        bundle_output_root=source.output_root,
        bundle_identity_sha256=source.bundle_identity_sha256,
        expected_manifest_sha256=source.manifest_sha256,
        row_scope_filter=f17.row_scope_filter,
        rule_state_filters=f17.technical_query.rule_state_filters,
        combine_mode=f17.technical_query.combine_mode,
        market_assignment_states=f17.market_assignment_states,
        official_disposal_states=f17.official_disposal_states,
        outer_stock_filter_mode=f17.outer_stock_filter_mode,
        outer_stock_codes=f17.outer_stock_codes,
        sort_clauses=f17.sort_clauses,
        cancel_callback=cancel_callback,
    )
    _cancel_check_v2(cancel_callback)
    if group.exact_f17_query.to_json() != f17.to_json():
        raise ValueError("technical_official_composite_view_v2_restore_f17_identity_mismatch")
    context = read_daily_market_technical_official_disposition_composite_bookmark_context_v2(
        bookmark,
        projection_group_session=group,
        cancel_callback=cancel_callback,
    )
    _cancel_check_v2(cancel_callback)
    return _RestoredBookmarkV2(typed_envelope, group, context)


class _StockCodeLineEditV2(QLineEdit):
    """記錄 Qt 靜默截斷，避免把代碼前綴當作完整條件。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._was_truncated = False
        self.setMaxLength(DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS * 17 - 1)
        self.inputRejected.connect(lambda: setattr(self, "_was_truncated", True))
        self.textChanged.connect(lambda _text: setattr(self, "_was_truncated", False))

    @property
    def was_truncated(self) -> bool:
        return self._was_truncated


class DailyMarketTechnicalOfficialDispositionCompositeViewV2(QWidget):
    """明選一個保存來源；展示四群複合結果與 F07 價格 AND gate。"""

    bookmarkPrepared = Signal(object)
    operationSettled = Signal(str, bool)

    def __init__(
        self,
        bundle_output_root: str | Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.bundle_output_root = Path(bundle_output_root) if bundle_output_root is not None else None
        self._catalog_cursor: str | None = None
        self._catalog_entries: tuple[DailyMarketTechnicalOfficialDispositionBundleCatalogEntryV1, ...] = ()
        self._source: _SourceChoiceV2 | None = None
        self._projection_group_session: DailyMarketTechnicalUniverseProjectionGroupSessionV3 | None = None
        self._restore_context: DailyMarketTechnicalOfficialDispositionCompositeBookmarkRestoreContextV2 | None = None
        self._result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2 | None = None
        self._page: DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2 | None = None
        self._page_size = 100
        self._selected_row: DailyMarketTechnicalOfficialDispositionCompositeResultRowV2 | None = None
        self._detail_selection: DailyMarketTechnicalOfficialDispositionCompositeSelectionV2 | None = None
        self._detail_page: DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2 | None = None
        self._detail_row: DailyMarketTechnicalOfficialDispositionCompositeResultRowV2 | None = None
        self._detail_view_scroll = 0
        self._basket: list[_BasketItemV2] = []
        self._comparison_dialog: QDialog | None = None
        self._busy_worker: TaskWorker | None = None
        self._live_workers: set[TaskWorker] = set()
        self._pending_scroll_restore: _PendingScrollRestoreV2 | None = None
        self._revision = 0
        self._busy_token = 0
        self._worker_kind = ""
        self._worker_apply: Callable[[object], None] | None = None
        self._closing = False
        self._build_ui()
        self._set_status(
            "尚未選擇保存來源資料夾；候選只列 metadata，尚未核驗。"
            if self.bundle_output_root is None
            else "請更新保存來源清單，再明確選取版本。"
        )

    @property
    def current_result(self) -> DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2 | None:
        return self._result

    @property
    def current_page(self) -> DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2 | None:
        return self._page

    @property
    def active_worker(self) -> TaskWorker | None:
        return self._busy_worker

    def _set_root_label(self, root: str | Path | None) -> None:
        if root is None:
            self.root_label.setText("尚未選擇保存來源資料夾")
            self.root_label.setToolTip("")
            self.root_label.setAccessibleDescription("尚未選擇保存來源資料夾")
            return
        exact_root = str(Path(root))
        self.root_label.setText("已選擇保存來源資料夾（完整路徑可停留查看）")
        self.root_label.setToolTip(f"完整保存來源路徑：\n{exact_root}")
        self.root_label.setAccessibleDescription(f"完整保存來源路徑：{exact_root}")

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        self.page_scroll = QScrollArea(self)
        self.page_scroll.setObjectName("technicalOfficialCompositeV2PageScroll")
        self.page_scroll.setWidgetResizable(True)
        body_widget = QWidget()
        body = QVBoxLayout(body_widget)
        self.page_scroll.setWidget(body_widget)
        outer.addWidget(self.page_scroll, 1)
        body.addWidget(QLabel("官方市場、技術四群與 F07 價格研究"))
        disclosure = QLabel(
            "研究用途；只讀明示保存版本。四群條件先依 AND／OR 計算，F07 價格另作共通 AND 閘門。"
            "官方資料可得時間未知，不具歷史 PIT 資格；不監看或更新來源。"
        )
        disclosure.setWordWrap(True)
        body.addWidget(disclosure)

        source_box = QGroupBox("已保存來源（需明確選取）")
        source_layout = QVBoxLayout(source_box)
        self.root_label = QLabel()
        self.root_label.setWordWrap(True)
        self.root_label.setMinimumWidth(0)
        self.root_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._set_root_label(self.bundle_output_root)
        self.choose_root_button = QPushButton("選擇保存來源資料夾")
        self.choose_root_button.clicked.connect(self.choose_bundle_output_root)
        self.refresh_catalog_button = QPushButton("更新來源清單")
        self.refresh_catalog_button.clicked.connect(self.refresh_catalog)
        self.next_catalog_button = QPushButton("下一頁候選")
        self.next_catalog_button.clicked.connect(self.load_next_catalog_page)
        source_layout.addWidget(self.root_label)
        source_actions = QGridLayout()
        for index, button in enumerate((
            self.choose_root_button, self.refresh_catalog_button, self.next_catalog_button,
        )):
            source_actions.addWidget(button, index // 2, index % 2)
        source_layout.addLayout(source_actions)
        self.catalog_list = QListWidget()
        self.catalog_list.setMinimumHeight(90)
        source_layout.addWidget(self.catalog_list)
        self.open_candidate_button = QPushButton("核驗並開啟所選保存版本")
        self.open_candidate_button.clicked.connect(self.open_selected_candidate)
        source_layout.addWidget(self.open_candidate_button)
        body.addWidget(source_box)

        self.filter_panel = self._build_filter_panel()
        body.addWidget(self.filter_panel)
        action_row = QGridLayout()
        self.apply_query_button = QPushButton("套用條件並重新全域查詢")
        self.apply_query_button.clicked.connect(self.apply_filters)
        self.clear_filters_button = QPushButton("清除條件")
        self.clear_filters_button.clicked.connect(self.clear_filters)
        self.cancel_button = QPushButton("取消背景工作")
        self.cancel_button.clicked.connect(self.cancel_current_operation)
        action_row.addWidget(self.apply_query_button, 0, 0, 1, 2)
        action_row.addWidget(self.clear_filters_button, 1, 0)
        action_row.addWidget(self.cancel_button, 1, 1)
        body.addLayout(action_row)

        self.results_stack = QStackedWidget()
        result_panel = QWidget()
        result_layout = QVBoxLayout(result_panel)
        self.counts_label = QLabel("尚未核驗保存來源。")
        self.counts_label.setWordWrap(True)
        result_layout.addWidget(self.counts_label)
        nav = QHBoxLayout()
        self.previous_page_button = QPushButton("上一頁")
        self.previous_page_button.clicked.connect(lambda: self.navigate_page(self._page_index() - 1))
        self.page_label = QLabel("第 0 / 0 頁；本頁 0 列")
        self.page_label.setObjectName("technicalOfficialCompositeV2PageLabel")
        self.page_label.setMinimumWidth(0)
        self.page_label.setWordWrap(True)
        self.next_page_button = QPushButton("下一頁")
        self.next_page_button.clicked.connect(lambda: self.navigate_page(self._page_index() + 1))
        nav.addWidget(self.previous_page_button)
        nav.addWidget(self.page_label)
        nav.addWidget(self.next_page_button)
        result_layout.addLayout(nav)
        self.results_table = QTableView()
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.results_table.setSortingEnabled(False)
        self.results_table.setMinimumHeight(240)
        self.results_model = SavedResearchPageTableModel[
            DailyMarketTechnicalOfficialDispositionCompositeResultRowV2
        ](
            ("代碼", "範圍", "技術", "四均線", "KDJ", "波動", "四群結果", "F07 價格閘門", "最終 AND"),
            maximum_page_size=DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_PAGE_SIZE,
            parent=self.results_table,
        )
        self.results_table.setModel(self.results_model)
        self.results_table.selectionModel().selectionChanged.connect(
            lambda _selected, _deselected: self._table_selection_changed()
        )
        result_layout.addWidget(self.results_table)
        row_actions = QGridLayout()
        self.detail_button = QPushButton("查看保存事實與原因")
        self.detail_button.clicked.connect(self.show_selected_detail)
        self.add_comparison_button = QPushButton("加入比較籃")
        self.add_comparison_button.clicked.connect(self.add_selected_to_comparison)
        self.remove_comparison_button = QPushButton("從比較籃移除")
        self.remove_comparison_button.clicked.connect(self.remove_selected_from_comparison)
        self.compare_button = QPushButton("顯示 2–5 檔保存事實")
        self.compare_button.clicked.connect(self.compare_basket)
        self.bookmark_button = QPushButton("準備 V2 研究收藏")
        self.bookmark_button.clicked.connect(self.prepare_bookmark)
        for index, button in enumerate((
            self.detail_button,
            self.add_comparison_button,
            self.remove_comparison_button,
            self.compare_button,
            self.bookmark_button,
        )):
            row_actions.addWidget(button, index // 2, index % 2)
        result_layout.addLayout(row_actions)
        self.basket_label = QLabel("比較籃：0 檔")
        self.basket_label.setWordWrap(True)
        result_layout.addWidget(self.basket_label)
        self.results_stack.addWidget(result_panel)

        detail_panel = QWidget()
        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.addWidget(QLabel("同一 V2 已核列的保存事實；返回後保留原頁與選取。"))
        self.detail_text = QPlainTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setMinimumHeight(280)
        detail_layout.addWidget(self.detail_text, 1)
        self.audit_text = QPlainTextEdit()
        self.audit_text.setReadOnly(True)
        self.audit_text.setMinimumHeight(240)
        detail_layout.addWidget(self.audit_text, 1)
        self.back_button = QPushButton("返回原結果頁")
        self.back_button.clicked.connect(self.return_to_results)
        detail_layout.addWidget(self.back_button)
        self.results_stack.addWidget(detail_panel)
        body.addWidget(self.results_stack, 1)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        outer.addWidget(self.status_label)
        self.next_catalog_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self._set_result_actions_enabled(False)

    def _build_filter_panel(self) -> QWidget:
        panel = QGroupBox("四群條件、F07 價格閘門、全域排序與分頁")
        layout = QVBoxLayout(panel)
        scope_box = QGroupBox("母體列範圍（外層 hard filter）")
        scope_layout = QGridLayout(scope_box)
        self.scope_checks: dict[RowScope, QCheckBox] = {}
        for index, scope in enumerate(_SCOPES):
            check = QCheckBox(_SCOPE_LABELS[scope])
            check.setChecked(True)
            self.scope_checks[scope] = check
            scope_layout.addWidget(check, index // 2, index % 2)
        layout.addWidget(scope_box)

        tech_box = QGroupBox("技術條件（第一群）")
        tech_layout = QVBoxLayout(tech_box)
        self.technical_combine_box = QComboBox()
        self.technical_combine_box.addItem("規則間 AND", "AND")
        self.technical_combine_box.addItem("規則間 OR", "OR")
        tech_layout.addWidget(self.technical_combine_box)
        self.rule_state_checks: dict[str, dict[str, QCheckBox]] = {}
        for key in DAILY_MARKET_TECHNICAL_RULE_KEYS_V4:
            rule_row = QGridLayout()
            rule_row.addWidget(QLabel(_RULE_LABELS.get(key, key)), 0, 0, 1, len(_STATE_ORDER))
            self.rule_state_checks[key] = {}
            for index, state in enumerate(_STATE_ORDER):
                check = QCheckBox({"match": "符合", "no_match": "不符合", "unknown": "未知"}[state])
                self.rule_state_checks[key][state] = check
                rule_row.addWidget(check, 1, index)
            for index in range(len(_STATE_ORDER)):
                rule_row.setColumnStretch(index, 1)
            tech_layout.addLayout(rule_row)
        layout.addWidget(tech_box)

        projection_box = QGroupBox("投影條件（四均線、KDJ、波動率；仍依四群 AND／OR 計算）")
        projection_layout = QVBoxLayout(projection_box)
        self.ma_state_checks: dict[str, QCheckBox] = {}
        self.kdj_state_checks: dict[str, QCheckBox] = {}
        for title, target in (("四均線", self.ma_state_checks), ("KDJ", self.kdj_state_checks)):
            row = QHBoxLayout()
            row.addWidget(QLabel(title))
            for state in _STATE_ORDER:
                check = QCheckBox({"match": "符合", "no_match": "不符合", "unknown": "未知"}[state])
                target[state] = check
                row.addWidget(check)
            projection_layout.addLayout(row)
        numeric = QFormLayout()
        self.bandwidth_min_input = QLineEdit()
        self.bandwidth_max_input = QLineEdit()
        self.atr14_min_input = QLineEdit()
        self.atr14_max_input = QLineEdit()
        for edit in (self.bandwidth_min_input, self.bandwidth_max_input,
                     self.atr14_min_input, self.atr14_max_input):
            edit.setPlaceholderText("空白代表不設界限；以十進位字串輸入")
        numeric.addRow("Bandwidth 最小值（percent）", self.bandwidth_min_input)
        numeric.addRow("Bandwidth 最大值（percent）", self.bandwidth_max_input)
        numeric.addRow("ATR14 SMA 最小值（percent）", self.atr14_min_input)
        numeric.addRow("ATR14 SMA 最大值（percent）", self.atr14_max_input)
        projection_layout.addLayout(numeric)
        layout.addWidget(projection_box)

        combine_box = QGroupBox("四群合併；F07 價格閘門在四群結果之後作 AND")
        combine_layout = QFormLayout(combine_box)
        self.combine_box = QComboBox()
        self.combine_box.addItem("啟用群組 AND", "AND")
        self.combine_box.addItem("啟用群組 OR", "OR")
        combine_layout.addRow("四群合併", self.combine_box)
        self.unknown_box = QComboBox()
        self.unknown_box.addItem("四群未知納入", "include")
        self.unknown_box.addItem("四群未知排除", "exclude")
        self.unknown_box.addItem("四群只看未知", "only")
        combine_layout.addRow("四群未知政策", self.unknown_box)
        layout.addWidget(combine_box)

        price_box = QGroupBox("F07 價格閘門（獨立政策；與四群結果共通 AND）")
        price_layout = QFormLayout(price_box)
        self.price_min_input = QLineEdit()
        self.price_max_input = QLineEdit()
        self.price_min_input.setObjectName("f07MinClosePriceInput")
        self.price_max_input.setObjectName("f07MaxClosePriceInput")
        self.price_min_input.setPlaceholderText("空白代表無下限；以十進位字串輸入")
        self.price_max_input.setPlaceholderText("空白代表無上限；以十進位字串輸入")
        self.price_min_inclusive = QCheckBox("下限包含等值")
        self.price_min_inclusive.setChecked(True)
        self.price_max_inclusive = QCheckBox("上限包含等值")
        self.price_max_inclusive.setChecked(True)
        min_row = QHBoxLayout()
        min_row.addWidget(self.price_min_input, 1)
        min_row.addWidget(self.price_min_inclusive)
        max_row = QHBoxLayout()
        max_row.addWidget(self.price_max_input, 1)
        max_row.addWidget(self.price_max_inclusive)
        price_layout.addRow("收盤價下限", min_row)
        price_layout.addRow("收盤價上限", max_row)
        self.unknown_price_box = QComboBox()
        self.unknown_price_box.addItem("未知價格納入", "include")
        self.unknown_price_box.addItem("未知價格排除", "exclude")
        self.unknown_price_box.addItem("只看未知價格", "only")
        self.unknown_price_box.setObjectName("f07UnknownPricePolicy")
        price_layout.addRow("F07 未知價格政策", self.unknown_price_box)
        layout.addWidget(price_box)

        outer_box = QGroupBox("官方市場、處置與指定代碼")
        outer_layout = QVBoxLayout(outer_box)
        outer_layout.addWidget(QLabel("這些條件先限制保存母體；四群 OR 與 F07 AND 均不能繞過。"))
        self.market_enabled = QCheckBox("限制市場狀態")
        outer_layout.addWidget(self.market_enabled)
        self.market_checks = self._add_state_checks(outer_layout, _MARKET_STATES, _MARKET_LABELS, "v2_market")
        self.market_enabled.toggled.connect(
            lambda enabled: [check.setEnabled(enabled) for check in self.market_checks.values()]
        )
        self.disposal_enabled = QCheckBox("限制官方處置狀態")
        outer_layout.addWidget(self.disposal_enabled)
        self.disposal_checks = self._add_state_checks(outer_layout, _DISPOSAL_STATES, _DISPOSAL_LABELS, "v2_disposal")
        self.disposal_enabled.toggled.connect(
            lambda enabled: [check.setEnabled(enabled) for check in self.disposal_checks.values()]
        )
        for check in (*self.market_checks.values(), *self.disposal_checks.values()):
            check.setEnabled(False)
        self.stock_filter_enabled = QCheckBox("只查指定代碼")
        self.stock_code_input = _StockCodeLineEditV2()
        self.stock_filter_enabled.toggled.connect(self.stock_code_input.setEnabled)
        self.stock_code_input.setPlaceholderText("以逗號或空白分隔；只作外層母體限制")
        self.stock_code_input.setEnabled(False)
        outer_layout.addWidget(self.stock_filter_enabled)
        outer_layout.addWidget(self.stock_code_input)
        layout.addWidget(outer_box)

        sort_page = QGridLayout()
        sort_page.addWidget(QLabel("全母體排序"), 0, 0)
        self.sort_field_box = QComboBox()
        for field, label in _SORT_OPTIONS:
            self.sort_field_box.addItem(label, field)
        self.sort_direction_box = QComboBox()
        self.sort_direction_box.addItem("升冪", "asc")
        self.sort_direction_box.addItem("降冪", "desc")
        self.sort_field_box.currentIndexChanged.connect(self._sync_sort_direction)
        sort_page.addWidget(self.sort_field_box, 0, 1, 1, 3)
        sort_page.addWidget(QLabel("排序方向"), 1, 0)
        sort_page.addWidget(self.sort_direction_box, 1, 1)
        sort_page.addWidget(QLabel("每頁最多 256 列"), 1, 2)
        self.page_size_box = QSpinBox()
        self.page_size_box.setRange(1, DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_MAX_PAGE_SIZE)
        self.page_size_box.setValue(100)
        sort_page.addWidget(self.page_size_box, 1, 3)
        layout.addLayout(sort_page)
        self._sync_sort_direction()
        return panel

    @staticmethod
    def _add_state_checks(
        parent_layout: QVBoxLayout,
        states: Sequence[str],
        labels: dict[str, str],
        prefix: str,
    ) -> dict[str, QCheckBox]:
        row = QGridLayout()
        checks: dict[str, QCheckBox] = {}
        for index, state in enumerate(states):
            check = QCheckBox(labels[state])
            check.setObjectName(f"{prefix}_{state}")
            checks[state] = check
            row.addWidget(check, index // 2, index % 2)
        row.setColumnStretch(0, 1)
        row.setColumnStretch(1, 1)
        parent_layout.addLayout(row)
        return checks

    def _sync_sort_direction(self) -> None:
        self.sort_direction_box.setEnabled(self.sort_field_box.currentData() != "stock_code")
        if self.sort_field_box.currentData() == "stock_code":
            self.sort_direction_box.setCurrentIndex(self.sort_direction_box.findData("asc"))

    def _read_conditions(self) -> _ConditionsV2:
        scopes = tuple(scope for scope in _SCOPES if self.scope_checks[scope].isChecked())
        if not scopes:
            raise ValueError("technical_official_composite_view_v2_row_scope_empty")
        rule_filters = tuple(
            DailyMarketTechnicalRuleStateFilterV4.create(
                key,
                tuple(state for state in _STATE_ORDER if checks[state].isChecked()),
            )
            for key, checks in self.rule_state_checks.items()
            if any(checks[state].isChecked() for state in _STATE_ORDER)
        )
        market_states = tuple(state for state in _MARKET_STATES if self.market_checks[state].isChecked())
        disposal_states = tuple(state for state in _DISPOSAL_STATES if self.disposal_checks[state].isChecked())
        if self.market_enabled.isChecked() and not market_states:
            raise ValueError("technical_official_composite_view_v2_market_state_required")
        if not self.market_enabled.isChecked() and market_states:
            raise ValueError("technical_official_composite_view_v2_market_filter_disabled_with_values")
        if self.disposal_enabled.isChecked() and not disposal_states:
            raise ValueError("technical_official_composite_view_v2_disposal_state_required")
        if not self.disposal_enabled.isChecked() and disposal_states:
            raise ValueError("technical_official_composite_view_v2_disposal_filter_disabled_with_values")
        if self.stock_filter_enabled.isChecked():
            codes = _parse_codes_v2(
                self.stock_code_input.text(),
                was_truncated=self.stock_code_input.was_truncated,
            )
            stock_mode: Literal["all", "explicit_codes"] = "explicit_codes"
        else:
            if self.stock_code_input.text().strip():
                raise ValueError("technical_official_composite_view_v2_stock_filter_disabled")
            codes = ()
            stock_mode = "all"
        ma_states = tuple(state for state in _STATE_ORDER if self.ma_state_checks[state].isChecked())
        kdj_states = tuple(state for state in _STATE_ORDER if self.kdj_state_checks[state].isChecked())
        bandwidth_min = _decimal_input_v2(self.bandwidth_min_input)
        bandwidth_max = _decimal_input_v2(self.bandwidth_max_input)
        atr_min = _decimal_input_v2(self.atr14_min_input)
        atr_max = _decimal_input_v2(self.atr14_max_input)
        price_min = _decimal_input_v2(self.price_min_input)
        price_max = _decimal_input_v2(self.price_max_input)
        if bandwidth_min is not None and bandwidth_max is not None and bandwidth_min > bandwidth_max:
            raise ValueError("technical_official_composite_view_v2_bandwidth_range_invalid")
        if atr_min is not None and atr_max is not None and atr_min > atr_max:
            raise ValueError("technical_official_composite_view_v2_atr_range_invalid")
        if price_min is not None and price_max is not None and price_min > price_max:
            raise ValueError("technical_official_composite_view_v2_price_range_invalid")
        active = sum((
            bool(rule_filters),
            bool(ma_states),
            bool(kdj_states),
            any(value is not None for value in (bandwidth_min, bandwidth_max, atr_min, atr_max)),
        ))
        sort_field = self.sort_field_box.currentData()
        sort_direction = self.sort_direction_box.currentData()
        if type(sort_field) is not str or type(sort_direction) is not str:
            raise ValueError("technical_official_composite_view_v2_sort_invalid")
        if sort_field == "stock_code" and sort_direction != "asc":
            raise ValueError("technical_official_composite_view_v2_stock_sort_must_asc")
        return _ConditionsV2(
            row_scope_filter=scopes,
            rule_state_filters=rule_filters,
            technical_combine_mode=cast(Literal["AND", "OR"], self.technical_combine_box.currentData()),
            market_assignment_states=market_states if self.market_enabled.isChecked() else (),
            official_disposal_states=disposal_states if self.disposal_enabled.isChecked() else (),
            outer_stock_filter_mode=stock_mode,
            outer_stock_codes=codes,
            ma_states=cast(tuple[MaState, ...] | None, ma_states or None),
            kdj_states=cast(tuple[KDJState, ...] | None, kdj_states or None),
            bandwidth_min_pct=bandwidth_min,
            bandwidth_max_pct=bandwidth_max,
            atr14_min_pct=atr_min,
            atr14_max_pct=atr_max,
            condition_combine_mode=cast(Literal["AND", "OR"], self.combine_box.currentData()) if active >= 2 else "AND",
            unknown_policy=cast(Literal["include", "exclude", "only"], self.unknown_box.currentData()) if active else "include",
            min_close_price=price_min,
            max_close_price=price_max,
            min_inclusive=self.price_min_inclusive.isChecked(),
            max_inclusive=self.price_max_inclusive.isChecked(),
            unknown_price_policy=cast(Literal["include", "exclude", "only"], self.unknown_price_box.currentData()),
            sort_field=sort_field,
            sort_direction=cast(Literal["asc", "desc"], sort_direction),
        )

    def choose_bundle_output_root(self) -> None:
        if not self._can_start():
            self._set_status("背景工作中或畫面正在關閉；不能更換來源。")
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
        candidate = Path(root)
        if not self._can_start() or not candidate.is_absolute() or not candidate.exists() or not candidate.is_dir():
            self._set_status("來源必須是已存在的絕對資料夾，且目前沒有背景工作。")
            return False
        self.bundle_output_root = candidate
        self._set_root_label(candidate)
        self._catalog_cursor = None
        self._catalog_entries = ()
        self.catalog_list.clear()
        self._source = None
        self._projection_group_session = None
        self._restore_context = None
        self._result = None
        self._page = None
        self._detail_selection = None
        self._detail_page = None
        self._detail_row = None
        self._basket.clear()
        self.results_stack.setCurrentIndex(0)
        self._render_page()
        self._update_basket_label()
        self._set_status("來源資料夾已選；按更新清單後再明確選取保存版本。")
        return True

    def refresh_catalog(self) -> None:
        if self.bundle_output_root is None:
            self._set_status("尚未選擇來源資料夾。")
            return
        root = self.bundle_output_root

        def task(cancel_callback: Callable[[], object] | None = None) -> DailyMarketTechnicalOfficialDispositionBundleCatalogPageV1:
            return DailyMarketTechnicalOfficialDispositionBundleCatalogV1(root).list_page(
                limit=DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_CATALOG_DEFAULT_LIMIT,
                cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
            )

        self._start_task("盤點已保存來源清單", task, self._apply_catalog)

    def load_next_catalog_page(self) -> None:
        if self.bundle_output_root is None or self._catalog_cursor is None:
            self._set_status("沒有可安全續讀的來源清單。")
            return
        root, cursor = self.bundle_output_root, self._catalog_cursor

        def task(cancel_callback: Callable[[], object] | None = None) -> DailyMarketTechnicalOfficialDispositionBundleCatalogPageV1:
            return DailyMarketTechnicalOfficialDispositionBundleCatalogV1(root).list_page(
                limit=DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_CATALOG_DEFAULT_LIMIT,
                cursor=cursor,
                cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
            )

        self._start_task("續讀保存來源清單", task, self._append_catalog)

    def _apply_catalog(self, value: object) -> None:
        if type(value) is not DailyMarketTechnicalOfficialDispositionBundleCatalogPageV1:
            raise ValueError("technical_official_composite_view_v2_catalog_invalid")
        self._catalog_entries = value.entries
        self._catalog_cursor = value.next_cursor if value.scan_complete else None
        self._render_catalog()
        self._set_status(
            "候選資訊尚未核驗；請明確選取一個保存版本。"
            if value.scan_complete else f"清單不完整：{value.diagnostic_code or 'unknown'}。"
        )

    def _append_catalog(self, value: object) -> None:
        if type(value) is not DailyMarketTechnicalOfficialDispositionBundleCatalogPageV1 or not value.scan_complete:
            self._catalog_cursor = None
            self._set_status("來源清單漂移或不完整；不能續讀。")
            return
        self._catalog_entries = (*self._catalog_entries, *value.entries)
        self._catalog_cursor = value.next_cursor
        self._render_catalog()

    def _render_catalog(self) -> None:
        self.catalog_list.clear()
        for index, entry in enumerate(self._catalog_entries):
            metadata = entry.metadata
            if metadata is None:
                label = f"資訊不完整｜{entry.diagnostic_code or '未提供診斷'}"
            else:
                label = (
                    f"{metadata.decision_date_label.isoformat()}｜宣告 {metadata.declared_count}、"
                    f"納入 {metadata.included_count}、排除 {metadata.excluded_count}｜尚未核驗"
                )
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setToolTip(entry.diagnostic_code or entry.relative_path)
            if not entry.can_attempt_exact_read:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled & ~Qt.ItemFlag.ItemIsSelectable)
            self.catalog_list.addItem(item)
        self.next_catalog_button.setEnabled(self._catalog_cursor is not None)

    def open_selected_candidate(self) -> None:
        index = self.catalog_list.currentRow()
        if not 0 <= index < len(self._catalog_entries):
            self._set_status("請明確選取可精確核驗的保存版本。")
            return
        entry = self._catalog_entries[index]
        if entry.metadata is None or not entry.can_attempt_exact_read or self.bundle_output_root is None:
            self._set_status("此列只供來源診斷，不能開啟研究。")
            return
        self._start_for_candidate(_SourceChoiceV2(
            str(self.bundle_output_root),
            entry.metadata.bundle_identity_sha256,
            entry.metadata.manifest_sha256,
        ))

    def _start_for_candidate(self, source: _SourceChoiceV2) -> None:
        try:
            conditions = self._read_conditions()
        except (TypeError, ValueError) as exc:
            self._set_status(f"條件無效：{exc}")
            return
        page_size = self.page_size_box.value()

        def task(cancel_callback: Callable[[], object] | None = None) -> _OpenedQueryV2:
            return _execute_fresh_query_v2(
                source,
                conditions,
                page_size=page_size,
                cancel_callback=cancel_callback,
            )

        self._start_task("精確核驗並執行 V2 全域複合查詢", task, self._apply_opened_query)

    def apply_filters(self) -> None:
        if self._source is None:
            self._set_status("請先明確選取一個已保存版本。")
            return
        self._start_for_candidate(self._source)

    def clear_filters(self) -> None:
        for check in self.scope_checks.values():
            check.setChecked(True)
        for group in self.rule_state_checks.values():
            for check in group.values():
                check.setChecked(False)
        for check in (*self.ma_state_checks.values(), *self.kdj_state_checks.values()):
            check.setChecked(False)
        self.technical_combine_box.setCurrentIndex(self.technical_combine_box.findData("AND"))
        self.combine_box.setCurrentIndex(self.combine_box.findData("AND"))
        self.unknown_box.setCurrentIndex(self.unknown_box.findData("include"))
        self.unknown_price_box.setCurrentIndex(self.unknown_price_box.findData("include"))
        self.price_min_inclusive.setChecked(True)
        self.price_max_inclusive.setChecked(True)
        for check in (*self.market_checks.values(), *self.disposal_checks.values()):
            check.setChecked(False)
        self.market_enabled.setChecked(False)
        self.disposal_enabled.setChecked(False)
        self.stock_filter_enabled.setChecked(False)
        self.stock_code_input.clear()
        for edit in (
            self.bandwidth_min_input, self.bandwidth_max_input,
            self.atr14_min_input, self.atr14_max_input,
            self.price_min_input, self.price_max_input,
        ):
            edit.clear()
        self.sort_field_box.setCurrentIndex(self.sort_field_box.findData("stock_code"))
        self.sort_direction_box.setCurrentIndex(self.sort_direction_box.findData("asc"))
        self.apply_filters()

    def _apply_opened_query(self, value: object) -> None:
        if type(value) is not _OpenedQueryV2:
            raise ValueError("technical_official_composite_view_v2_query_result_invalid")
        result, page = value.result, value.page
        result.__post_init__()
        page.__post_init__()
        present_composite_page_v2(result, page)
        if (
            page._result is not result
            or page.operation_identity_sha256 != result.operation_identity_sha256
            or page.query.query_identity_sha256 != result.query.query_identity_sha256
            or page.source_pins != result.source_pins
            or page.page_index != 0
            or page.page_size != value.page_size
            or result._projection_group_session is not value.projection_group_session
        ):
            raise ValueError("technical_official_composite_view_v2_page_result_mismatch")
        self._source = value.source
        self._projection_group_session = value.projection_group_session
        self._restore_context = None
        self._result = result
        self._page = page
        self._page_size = value.page_size
        self._selected_row = None
        self._detail_selection = None
        self._detail_page = None
        self._detail_row = None
        self._basket.clear()
        self.results_stack.setCurrentIndex(0)
        self.page_size_box.setValue(value.page_size)
        self._apply_query_controls(result.query)
        self._render_page()
        self._set_result_actions_enabled(True)
        self._set_status(
            "已沿明選來源完成 V2 全母體查詢；official available_at 未知，歷史 PIT 不適用。"
        )

    def navigate_page(self, page_index: int) -> None:
        if self._closing or self._busy_worker is not None or self._result is None or self._page is None:
            return
        if not 0 <= page_index < self._page.page_count:
            self._set_status("頁碼超出目前 V2 全域結果範圍。")
            return
        result = self._result
        page_size = self._page_size

        def task(cancel_callback: Callable[[], object] | None = None) -> tuple[
            DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2,
            DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2,
        ]:
            page = result.read_page(page_index, page_size, cancel_callback=cancel_callback)
            _cancel_check_v2(cancel_callback)
            return result, page

        self._start_task("讀取 V2 全域排序結果的指定頁", task, self._apply_page)

    def _apply_page(self, value: object) -> None:
        if type(value) is not tuple or len(value) != 2:
            raise ValueError("technical_official_composite_view_v2_page_invalid")
        result, page = value
        if (
            type(result) is not DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2
            or type(page) is not DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2
        ):
            raise ValueError("technical_official_composite_view_v2_page_invalid")
        if self._result is None or result is not self._result:
            raise ValueError("technical_official_composite_view_v2_page_owner_missing")
        page.__post_init__()
        present_composite_page_v2(result, page)
        if page._result is not result or page.operation_identity_sha256 != result.operation_identity_sha256:
            raise ValueError("technical_official_composite_view_v2_page_owner_mismatch")
        self._page = page
        self._selected_row = None
        self._detail_selection = None
        self._detail_page = None
        self._detail_row = None
        self.results_stack.setCurrentIndex(0)
        self._render_page()
        self._set_status("已由同一 V2 reader result 讀取另一頁並重核頁列身份。")

    def _render_page(self) -> None:
        self.results_table.clearSelection()
        self.results_table.setCurrentIndex(QModelIndex())
        self._selected_row = None
        page, result = self._page, self._result
        if page is None or result is None:
            self.results_model.replace_page(())
            self.counts_label.setText("尚未核驗保存來源。")
            self.page_label.setText("第 0 / 0 頁；本頁 0 列")
            return
        presentation = present_composite_page_v2(result, page)
        self.counts_label.setText(format_composite_counts_v2(result))
        table_rows: list[SavedResearchTableRow[DailyMarketTechnicalOfficialDispositionCompositeResultRowV2]] = []
        for row, row_view in zip(page.rows, presentation.rows, strict=True):
            truths = {name: _TRUTH_LABELS[truth] for name, truth, _active in row_view.four_group_truths}
            cells = (
                row.stock_code,
                _SCOPE_LABELS.get(cast(RowScope, row_view.base_four_group.row_scope), row_view.base_four_group.row_scope),
                truths["technical"],
                truths["ma"],
                truths["kdj"],
                truths["volatility"],
                _TRUTH_LABELS[row_view.base_four_group.composite_truth],
                _TRUTH_LABELS[row_view.price_gate.truth],
                _TRUTH_LABELS[row_view.final_composite_truth],
            )
            full_reason = format_composite_row_v2(row)
            table_rows.append(SavedResearchTableRow(row.stock_code, row, cells, (full_reason,) * len(cells)))
        self.results_model.replace_page(tuple(table_rows))
        self.page_label.setText(
            f"第 {page.page_index + 1} / {page.page_count} 頁；本頁 {len(page.rows)} 列／"
            f"每頁 {page.page_size} 列；F07 gate 後全域可見 {result.visible_count} 列"
        )
        self.previous_page_button.setEnabled(page.page_index > 0)
        self.next_page_button.setEnabled(page.page_index + 1 < page.page_count)
        self._update_basket_label()

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

    def show_selected_detail(self) -> None:
        result, page, row = self._result, self._page, self._selected_row
        if result is None or page is None or row is None:
            self._set_status("請先選取目前 V2 已核頁面的一列。")
            return
        try:
            selection = DailyMarketTechnicalOfficialDispositionCompositeSelectionV2.from_real_row_context(
                result, page, row.stock_code,
            )
        except (TypeError, ValueError) as exc:
            self._set_status(f"無法核對 V2 個股頁：{exc}")
            return
        self._detail_view_scroll = self.page_scroll.verticalScrollBar().value()
        self._detail_selection = selection
        self._detail_page = page
        self._detail_row = row
        self.detail_text.setPlainText(format_composite_row_v2(row))
        self.audit_text.setPlainText(json.dumps(row.to_dict(), ensure_ascii=False, indent=2, default=str))
        self.results_stack.setCurrentIndex(1)

    def return_to_results(self) -> None:
        selection, result, page, row = (
            self._detail_selection, self._result, self._detail_page, self._detail_row,
        )
        if selection is None or result is None or page is None or row is None:
            self._set_status("目前沒有可返回的 V2 列身份。")
            self.results_stack.setCurrentIndex(0)
            return
        try:
            current = DailyMarketTechnicalOfficialDispositionCompositeSelectionV2.from_real_row_context(
                result, page, selection.stock_code,
            )
        except (TypeError, ValueError):
            current = None
        if (
            current is None
            or current.to_dict() != selection.to_dict()
            or page is not self._page
            or row.row_identity_sha256 != selection.row_identity_sha256
        ):
            self._set_status("原 V2 查詢、頁面或列身份已改變；請重新選取。")
            self._detail_selection = None
            self._detail_page = None
            self._detail_row = None
            self.results_stack.setCurrentIndex(0)
            return
        self.results_stack.setCurrentIndex(0)
        self.select_stock_code(selection.stock_code)
        self.page_scroll.verticalScrollBar().setValue(self._detail_view_scroll)

    def add_selected_to_comparison(self) -> None:
        result, page, row = self._result, self._page, self._selected_row
        if result is None or page is None or row is None:
            self._set_status("請先選取目前 V2 已核頁面的一列。")
            return
        view = present_composite_row_v2(row)
        if not view.base_four_group.hard_eligible:
            self._set_status("比較籃只收納外層 hard eligible 的 V2 列。")
            return
        if any(item.selection.stock_code == row.stock_code for item in self._basket):
            self._set_status("這檔股票已在 V2 比較籃。")
            return
        if len(self._basket) >= 5:
            self._set_status("比較籃最多 5 檔。")
            return
        try:
            selection = DailyMarketTechnicalOfficialDispositionCompositeSelectionV2.from_real_row_context(
                result, page, row.stock_code,
            )
        except (TypeError, ValueError) as exc:
            self._set_status(f"無法加入 V2 比較：{exc}")
            return
        self._basket.append(_BasketItemV2(selection, page))
        self._update_basket_label()

    def remove_selected_from_comparison(self) -> None:
        if self._selected_row is None:
            self._set_status("請先選取要移除的股票。")
            return
        code = self._selected_row.stock_code
        self._basket = [item for item in self._basket if item.selection.stock_code != code]
        self._update_basket_label()

    def compare_basket(self) -> None:
        result = self._result
        if result is None or not 2 <= len(self._basket) <= 5:
            self._set_status("比較需要同一 V2 result 內 2–5 檔已核列。")
            return
        verified_rows: list[DailyMarketTechnicalOfficialDispositionCompositeResultRowV2] = []
        try:
            for item in self._basket:
                fresh = DailyMarketTechnicalOfficialDispositionCompositeSelectionV2.from_real_row_context(
                    result, item.page, item.selection.stock_code,
                )
                if (
                    fresh.to_dict() != item.selection.to_dict()
                    or item.page._result is not result
                    or item.page.source_pins != result.source_pins
                ):
                    raise ValueError("basket_page_identity_mismatch")
                row = next((row for row in item.page.rows if row.stock_code == item.selection.stock_code), None)
                if row is None or row.row_identity_sha256 != item.selection.row_identity_sha256:
                    raise ValueError("basket_row_identity_mismatch")
                verified_rows.append(row)
        except (TypeError, ValueError) as exc:
            self._set_status(f"V2 比較籃與目前完整結果不一致：{exc}")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("同來源 V2 四群／F07 保存事實比較")
        layout = QVBoxLayout(dialog)
        hint = QLabel("同一 V2 query、來源 pins 與 reader-issued rows；未知保持未知，不新增交易判斷。")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        scroll = QScrollArea(dialog)
        scroll.setWidgetResizable(True)
        columns = QWidget()
        column_layout = QHBoxLayout(columns)
        for row in verified_rows:
            group = QGroupBox(row.stock_code)
            content = QVBoxLayout(group)
            facts = QPlainTextEdit()
            facts.setReadOnly(True)
            facts.setPlainText(format_composite_row_v2(row))
            content.addWidget(facts)
            column_layout.addWidget(group)
        scroll.setWidget(columns)
        layout.addWidget(scroll, 1)
        close = QPushButton("關閉比較，返回原結果")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.resize(1000, 680)
        dialog.show()
        self._comparison_dialog = dialog
        self._set_status("已核驗並呈現 V2 比較籃原列；未重新查詢或排序。")

    def _update_basket_label(self) -> None:
        codes = tuple(item.selection.stock_code for item in self._basket)
        self.basket_label.setText(f"比較籃：{len(codes)} 檔" + (f"（{'、'.join(codes)}）" if codes else ""))
        self.compare_button.setEnabled(
            self._busy_worker is None and self._result is not None and 2 <= len(codes) <= 5
        )

    def prepare_bookmark(self) -> None:
        result, page, row = self._result, self._page, self._selected_row
        if result is None or page is None or row is None:
            self._set_status("請先選取目前 V2 已核頁面的一列，再準備收藏。")
            return
        try:
            selected_code = row.stock_code
            comparison_contexts = tuple(
                (item.page, item.selection.stock_code)
                for item in self._basket
                if item.selection.stock_code != selected_code
            )
            for item in self._basket:
                if (
                    item.selection.query_identity_sha256 != result.query.query_identity_sha256
                    or item.selection.result_identity_sha256 != result.operation_identity_sha256
                    or item.page._result is not result
                ):
                    raise ValueError("basket_context_not_current_result")
            basket_codes = tuple(item.selection.stock_code for item in self._basket)
            if selected_code not in basket_codes:
                basket_codes = (*basket_codes, selected_code)
            bookmark = DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2.create_from_real_row_context(
                result,
                page,
                selected_code,
                scroll_position=self.page_scroll.verticalScrollBar().value(),
                comparison_contexts=comparison_contexts,
                basket_stock_codes=basket_codes,
            )
            envelope = DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2.create(bookmark)
        except (TypeError, ValueError) as exc:
            self._set_status(f"無法準備 V2 複合收藏：{exc}")
            return
        self.bookmarkPrepared.emit(envelope)
        self._set_status("已準備 V2 strict 收藏；重新開啟會沿保存 pins fresh exact 重核。")

    def restore_bookmark(
        self,
        value: DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2 | bytes | str,
    ) -> bool:
        if not self._can_start():
            self._set_status("背景工作中或畫面正在關閉；V2 收藏尚未重開。")
            return False
        try:
            if type(value) is DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2:
                envelope = DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2.from_json(
                    value.to_json()
                )
            elif isinstance(value, (bytes, str)):
                envelope = DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2.from_json(value)
            else:
                raise ValueError("composite_view_v2_bookmark_envelope_type_invalid")
            bookmark = DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2.from_json(
                envelope.bookmark_json
            )
            self._validate_supported_sort(bookmark.query)
        except (TypeError, ValueError) as exc:
            self._set_status(f"V2 收藏無效：{exc}")
            return False

        def task(cancel_callback: Callable[[], object] | None = None) -> _RestoredBookmarkV2:
            return _restore_bookmark_v2(envelope, cancel_callback=cancel_callback)

        self._start_task("saved pins fresh exact 重開 V2 複合收藏", task, self._apply_restored_bookmark)
        return True

    def _apply_restored_bookmark(self, value: object) -> None:
        if type(value) is not _RestoredBookmarkV2:
            raise ValueError("technical_official_composite_view_v2_restore_invalid")
        context = value.context
        result = context.result
        result.__post_init__()
        verified = (context.selected, *context.comparison_selections)
        verified_by_code = {item.selection.stock_code: item for item in verified}
        if len(verified_by_code) != len(verified):
            raise ValueError("technical_official_composite_view_v2_restore_basket_duplicate")
        if any(code not in verified_by_code for code in context.basket_stock_codes):
            raise ValueError("technical_official_composite_view_v2_restore_basket_missing")
        bookmark = context.bookmark
        f17 = bookmark.query.base_query.f17_query
        self._source = _SourceChoiceV2(
            f17.bundle_output_root,
            f17.bundle_identity_sha256,
            f17.expected_manifest_sha256,
        )
        self.bundle_output_root = Path(self._source.output_root)
        self._set_root_label(self.bundle_output_root)
        self._projection_group_session = value.projection_group_session
        self._restore_context = context
        self._result = result
        restored_page = context.selected.page
        self._page = restored_page
        self._page_size = context.selected.selection.page_size
        self._selected_row = context.selected.row
        self._detail_selection = None
        self._detail_page = None
        self._detail_row = None
        self._basket = [
            _BasketItemV2(verified_by_code[code].selection, verified_by_code[code].page)
            for code in context.basket_stock_codes
        ]
        self.page_size_box.setValue(self._page_size)
        self._apply_query_controls(result.query)
        self.results_stack.setCurrentIndex(0)
        self._render_page()
        if not self.select_stock_code(context.selected.selection.stock_code):
            raise ValueError("technical_official_composite_view_v2_restore_selection_missing")
        self._set_result_actions_enabled(True)
        selected_row = self._selected_row
        if selected_row is None:
            raise ValueError("technical_official_composite_view_v2_restore_selection_missing")
        self._schedule_scroll_restore_v2(
            target_value=context.scroll_position,
            result=result,
            page=restored_page,
            selected_row=selected_row,
        )

    def _schedule_scroll_restore_v2(
        self,
        *,
        target_value: int,
        result: DailyMarketTechnicalOfficialDispositionCompositeVerifiedQueryResultV2,
        page: DailyMarketTechnicalOfficialDispositionCompositeQueryPageV2,
        selected_row: DailyMarketTechnicalOfficialDispositionCompositeResultRowV2,
    ) -> None:
        if (
            type(target_value) is not int
            or target_value < 0
            or self._revision != self._busy_token
            or self._result is not result
            or self._page is not page
            or page._result is not result
            or page.operation_identity_sha256 != result.operation_identity_sha256
            or not any(
                row.stock_code == selected_row.stock_code
                and row.row_identity_sha256 == selected_row.row_identity_sha256
                for row in page.rows
            )
        ):
            raise ValueError("technical_official_composite_view_v2_restore_scroll_context_invalid")
        pending = _PendingScrollRestoreV2(
            generation=self._revision,
            operation_kind=self._worker_kind,
            result=result,
            page=page,
            operation_identity_sha256=result.operation_identity_sha256,
            page_identity_sha256=page.page_identity_sha256,
            stock_code=selected_row.stock_code,
            row_identity_sha256=selected_row.row_identity_sha256,
            target_value=target_value,
        )
        self._pending_scroll_restore = pending
        self._set_controls_busy(True)
        self._set_status("保存查詢與選列已重核；正在等待版面範圍後精確恢復捲動位置。")
        QTimer.singleShot(16, lambda current=pending: self._restore_scroll_step_v2(current))

    def _restore_scroll_layout_metrics_v2(self) -> tuple[int, int, int]:
        """讀取垂直捲軸範圍；獨立成小 seam 供 UI 測試延遲版面案例。"""
        scrollbar = self.page_scroll.verticalScrollBar()
        return scrollbar.minimum(), scrollbar.maximum(), scrollbar.value()

    def _activate_scroll_layout_v2(self) -> None:
        self.ensurePolished()
        self.page_scroll.ensurePolished()
        content = self.page_scroll.widget()
        if content is not None:
            content.ensurePolished()
            content_layout = content.layout()
            if content_layout is not None:
                content_layout.activate()
        view_layout = self.layout()
        if view_layout is not None:
            view_layout.activate()
        self.page_scroll.updateGeometry()
        self.page_scroll.viewport().updateGeometry()

    def _restore_scroll_ticket_is_current_v2(
        self,
        pending: _PendingScrollRestoreV2,
    ) -> bool:
        selected = self._selected_row
        return (
            self._pending_scroll_restore is pending
            and not self._closing
            and self._revision == pending.generation
            and self._result is pending.result
            and self._page is pending.page
            and pending.result.operation_identity_sha256 == pending.operation_identity_sha256
            and pending.page.page_identity_sha256 == pending.page_identity_sha256
            and pending.page._result is pending.result
            and pending.page.operation_identity_sha256 == pending.operation_identity_sha256
            and selected is not None
            and selected.stock_code == pending.stock_code
            and selected.row_identity_sha256 == pending.row_identity_sha256
        )

    def _restore_scroll_step_v2(self, pending: _PendingScrollRestoreV2) -> None:
        if self._pending_scroll_restore is not pending:
            return
        if not self._restore_scroll_ticket_is_current_v2(pending):
            self._settle_scroll_restore_v2(
                pending,
                success=False,
                message="V2 收藏捲動恢復因查詢、頁面、選列或畫面狀態改變而取消。",
            )
            return

        pending.attempts += 1
        self._activate_scroll_layout_v2()
        minimum, maximum, _current = self._restore_scroll_layout_metrics_v2()
        if minimum <= pending.target_value <= maximum:
            if (minimum, maximum) == (pending.last_minimum, pending.last_maximum):
                pending.stable_range_observations += 1
            else:
                pending.stable_range_observations = 1
        else:
            pending.stable_range_observations = 0
        pending.last_minimum = minimum
        pending.last_maximum = maximum

        if pending.stable_range_observations >= 2:
            self.page_scroll.verticalScrollBar().setValue(pending.target_value)
            if self.page_scroll.verticalScrollBar().value() == pending.target_value:
                self._settle_scroll_restore_v2(
                    pending,
                    success=True,
                    message="V2 收藏已沿原保存 pins fresh exact 重核，並精確恢復捲動位置。",
                )
                return

        if pending.attempts >= _RESTORE_SCROLL_MAX_ATTEMPTS_V2:
            self._settle_scroll_restore_v2(
                pending,
                success=False,
                message=(
                    "V2 收藏資料已重核，但目前視窗版面無法容納保存的捲動位置；"
                    "未以截斷位置回報成功。"
                ),
            )
            return
        QTimer.singleShot(16, lambda current=pending: self._restore_scroll_step_v2(current))

    def _settle_scroll_restore_v2(
        self,
        pending: _PendingScrollRestoreV2,
        *,
        success: bool,
        message: str,
    ) -> None:
        if self._pending_scroll_restore is not pending:
            return
        self._pending_scroll_restore = None
        if not self._closing and self._busy_worker is None:
            self._set_controls_busy(False)
        self._set_status(message)
        self.operationSettled.emit(pending.operation_kind, success)

    def _invalidate_scroll_restore_v2(self, message: str) -> None:
        pending = self._pending_scroll_restore
        if pending is not None:
            self._settle_scroll_restore_v2(pending, success=False, message=message)

    @staticmethod
    def _validate_supported_sort(query: DailyMarketTechnicalOfficialDispositionCompositeQueryV2) -> None:
        """只恢復控制項能完整呈現的主排序與股票穩定次序。"""
        clauses = query.sort_clauses
        if (
            not clauses
            or clauses[0].field not in {field for field, _label in _SORT_OPTIONS}
            or len(clauses) > 2
            or len(clauses) == 2 and (clauses[1].field, clauses[1].direction) != ("stock_code", "asc")
        ):
            raise ValueError("composite_view_v2_sort_not_supported")

    def _apply_query_controls(self, query: DailyMarketTechnicalOfficialDispositionCompositeQueryV2) -> None:
        self._validate_supported_sort(query)
        f17 = query.base_query.f17_query
        for scope, check in self.scope_checks.items():
            check.setChecked(scope in f17.row_scope_filter)
        saved_rules = {item.rule_key: item for item in f17.technical_query.rule_state_filters}
        for key, checks in self.rule_state_checks.items():
            saved = saved_rules.get(key)
            for state, check in checks.items():
                check.setChecked(saved is not None and state in saved.states)
        self.technical_combine_box.setCurrentIndex(
            self.technical_combine_box.findData(f17.technical_query.combine_mode)
        )
        base = query.base_query
        for state, check in self.ma_state_checks.items():
            check.setChecked(base.ma_states is not None and state in base.ma_states)
        for state, check in self.kdj_state_checks.items():
            check.setChecked(base.kdj_states is not None and state in base.kdj_states)
        self.bandwidth_min_input.setText(str(base.bandwidth_min_pct) if base.bandwidth_min_pct is not None else "")
        self.bandwidth_max_input.setText(str(base.bandwidth_max_pct) if base.bandwidth_max_pct is not None else "")
        self.atr14_min_input.setText(str(base.atr14_min_pct) if base.atr14_min_pct is not None else "")
        self.atr14_max_input.setText(str(base.atr14_max_pct) if base.atr14_max_pct is not None else "")
        self.combine_box.setCurrentIndex(self.combine_box.findData(base.condition_combine_mode))
        self.unknown_box.setCurrentIndex(self.unknown_box.findData(base.unknown_policy))
        self.price_min_input.setText(str(query.min_close_price) if query.min_close_price is not None else "")
        self.price_max_input.setText(str(query.max_close_price) if query.max_close_price is not None else "")
        self.price_min_inclusive.setChecked(query.min_inclusive)
        self.price_max_inclusive.setChecked(query.max_inclusive)
        self.unknown_price_box.setCurrentIndex(self.unknown_price_box.findData(query.unknown_price_policy))
        for state, check in self.market_checks.items():
            check.setChecked(state in f17.market_assignment_states)
        self.market_enabled.setChecked(bool(f17.market_assignment_states))
        for state, check in self.disposal_checks.items():
            check.setChecked(state in f17.official_disposal_states)
        self.disposal_enabled.setChecked(bool(f17.official_disposal_states))
        explicit = f17.outer_stock_filter_mode == "explicit_codes"
        self.stock_filter_enabled.setChecked(explicit)
        self.stock_code_input.setText(",".join(f17.outer_stock_codes) if explicit else "")
        if not query.sort_clauses:
            raise ValueError("technical_official_composite_view_v2_restore_sort_missing")
        sort = query.sort_clauses[0]
        field_index = self.sort_field_box.findData(sort.field)
        direction_index = self.sort_direction_box.findData(sort.direction)
        if field_index < 0 or direction_index < 0:
            raise ValueError("technical_official_composite_view_v2_restore_sort_invalid")
        self.sort_field_box.setCurrentIndex(field_index)
        self.sort_direction_box.setCurrentIndex(direction_index)

    def _set_result_actions_enabled(self, enabled: bool) -> None:
        for widget in (
            self.detail_button, self.add_comparison_button, self.remove_comparison_button,
            self.bookmark_button,
        ):
            widget.setEnabled(enabled)
        self.compare_button.setEnabled(enabled and 2 <= len(self._basket) <= 5)
        self.previous_page_button.setEnabled(enabled and self._page is not None and self._page.page_index > 0)
        self.next_page_button.setEnabled(
            enabled and self._page is not None and self._page.page_index + 1 < self._page.page_count
        )

    def _can_start(self) -> bool:
        return not self._closing and self._busy_worker is None and not self._has_running_worker()

    def _has_running_worker(self) -> bool:
        if self._pending_scroll_restore is not None:
            return True
        for worker in tuple(self._live_workers):
            try:
                if worker.isRunning():
                    return True
            except RuntimeError:
                self._live_workers.discard(worker)
        return False

    def _start_task(self, kind: str, task: Callable[..., object], apply: Callable[[object], None]) -> None:
        self._invalidate_scroll_restore_v2("V2 收藏捲動恢復已被新的研究操作取代。")
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
        _WORKERS_V2.add(worker)
        worker.finished.connect(lambda value, current=token: self._task_finished(current, value))
        worker.error.connect(lambda message, current=token: self._task_error(current, message))
        worker.cancelled.connect(lambda current=token: self._task_cancelled(current))
        worker.native_thread_finished.connect(lambda current=worker: self._native_worker_finished(current))
        worker.finished.connect(lambda _value, current=worker: _WORKERS_V2.discard(current))
        worker.error.connect(lambda _message, current=worker: _WORKERS_V2.discard(current))
        worker.cancelled.connect(lambda current=worker: _WORKERS_V2.discard(current))
        self._set_controls_busy(True)
        self._set_status(f"背景工作中：{kind}…")
        worker.start()

    def _set_controls_busy(self, busy: bool) -> None:
        for widget in (
            self.choose_root_button, self.refresh_catalog_button, self.next_catalog_button,
            self.catalog_list, self.open_candidate_button, self.filter_panel,
            self.apply_query_button, self.clear_filters_button, self.page_size_box,
            self.sort_field_box, self.sort_direction_box, self.results_table,
            self.cancel_button,
        ):
            widget.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self._set_result_actions_enabled(not busy and self._page is not None)
        if not busy:
            self.next_catalog_button.setEnabled(self._catalog_cursor is not None)
            self._sync_sort_direction()

    def _native_worker_finished(self, worker: TaskWorker) -> None:
        self._live_workers.discard(worker)

    def _finish_task(self, token: int) -> bool:
        if token == self._busy_token:
            self._busy_worker = None
            self._worker_apply = None
            self._set_controls_busy(False)
        return token == self._busy_token and token == self._revision and not self._closing

    def _task_finished(self, token: int, value: object) -> None:
        kind, apply = self._worker_kind, self._worker_apply
        if self._finish_task(token):
            try:
                if apply is not None:
                    apply(value)
                pending = self._pending_scroll_restore
                if pending is not None and pending.generation == token:
                    return
                self.operationSettled.emit(kind, True)
            except Exception as exc:
                self._set_status(f"V2 結果未套用，保留目前已核結果：{exc}")
                self.operationSettled.emit(kind, False)
        else:
            self.operationSettled.emit(kind, False)

    def _task_error(self, token: int, message: str) -> None:
        kind = self._worker_kind
        if self._finish_task(token):
            code = message.splitlines()[0] if message else "unknown"
            self._set_status(f"{kind} 失敗；目前完整 V2 結果維持不變：{code}")
        self.operationSettled.emit(kind, False)

    def _task_cancelled(self, token: int) -> None:
        kind = self._worker_kind
        if self._finish_task(token):
            self._set_status(f"{kind} 已取消；沒有套用部分 V2 結果。")
        self.operationSettled.emit(kind, False)

    def cancel_current_operation(self) -> None:
        if self._pending_scroll_restore is not None:
            self._invalidate_scroll_restore_v2("V2 收藏捲動恢復已取消；未回報位置恢復成功。")
            return
        if self._busy_worker is None:
            return
        self._revision += 1
        self._busy_worker.cancel()
        self._set_status("已送出合作式取消；目前完整 V2 結果保持不變。")

    def begin_shutdown(self) -> bool:
        if not self._closing:
            self._closing = True
            self._revision += 1
        self._invalidate_scroll_restore_v2("畫面關閉；V2 收藏捲動恢復取消。")
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

    def _set_status(self, message: str) -> None:
        self.status_label.setText(message)


__all__ = ["DailyMarketTechnicalOfficialDispositionCompositeViewV2"]
