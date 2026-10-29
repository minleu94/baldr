"""
Smart Money Flow - Terminal Style Scanner 主視圖
整合 Summary Strip 與使用 Custom Delegate 的 Scanner Table。
已優化：採用左右分欄、增加股票資訊摘要面板、整合雙向资金長條圖分點明細表、美化控制列與表格樣式。
"""

import inspect
import pandas as pd
from datetime import date
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableView, QMessageBox, QLineEdit,
    QTabWidget, QSplitter, QComboBox, QHeaderView, QFrame, QSizePolicy,
    QGridLayout,
)
from PySide6.QtCore import (
    QEvent, QItemSelectionModel, QModelIndex, QSortFilterProxyModel, QTimer, Qt,
)
from PySide6.QtGui import QColor

from ui_qt.widgets.info_button import InfoButton
from app_module.broker_flow_service import BrokerFlowService
from app_module.broker_flow_dashboard_dtos import BrokerFlowDashboardQuery
from app_module.paper_portfolio_time import taiwan_market_today
from app_module.watchlist_service import WatchlistService
from ui_qt.views.smart_money.summary_strip import SummaryStrip
from ui_qt.views.smart_money.terminal_table_model import (
    ROLE_BADGES,
    TerminalTableModel,
    BranchTrackerTableModel,
)
from ui_qt.views.smart_money.terminal_delegate import TerminalScannerDelegate
from ui_qt.views.smart_money.detail_table_delegate import DetailTableDelegate
from ui_qt.models.pandas_table_model import PandasTableModel # 給 Detail Table 用
from ui_qt.workers.task_worker import TaskWorker
from ui_qt.widgets.layout_helpers import create_scroll_area, ensure_visible_rows


class SmartMoneyScannerProxyModel(QSortFilterProxyModel):
    """在目前 scanner model 範圍內篩選代號／名稱，並沿用原始排序語意。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._search_text = ""
        self.setDynamicSortFilter(True)

    def set_search_text(self, value: str) -> None:
        normalized = str(value or "").strip().casefold()
        if normalized == self._search_text:
            return
        self.beginFilterChange()
        self._search_text = normalized
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def matches_signal(self, signal) -> bool:
        if not self._search_text:
            return True
        stock_code = str(getattr(signal, "stock_code", "") or "").casefold()
        stock_name = str(getattr(signal, "stock_name", "") or "").casefold()
        return self._search_text in stock_code or self._search_text in stock_name

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        if column in {0, 1, 2, 3, 4}:
            super().sort(column, order)

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:  # noqa: N802
        source_model = self.sourceModel()
        if not isinstance(source_model, TerminalTableModel):
            return True
        return self.matches_signal(source_model.get_signal_at(source_row))

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:  # noqa: N802
        source_model = self.sourceModel()
        if not isinstance(source_model, TerminalTableModel):
            return super().lessThan(left, right)
        left_signal = source_model.get_signal_at(left.row())
        right_signal = source_model.get_signal_at(right.row())
        if left_signal is None or right_signal is None:
            return super().lessThan(left, right)

        column = left.column()
        if column == 0:
            return left_signal.smart_money_score < right_signal.smart_money_score
        if column == 1:
            return (left_signal.stock_code, left_signal.stock_name) < (
                right_signal.stock_code,
                right_signal.stock_name,
            )
        if column == 2:
            return left_signal.aggregation.total_net_qty < right_signal.aggregation.total_net_qty
        if column == 3:
            return left_signal.branch_concentration < right_signal.branch_concentration
        if column == 4:
            left_semantic = source_model.semantics_by_code.get(left_signal.stock_code)
            right_semantic = source_model.semantics_by_code.get(right_signal.stock_code)
            return str(getattr(left_semantic, "primary_state", "")) < str(
                getattr(right_semantic, "primary_state", "")
            )
        return False

    def get_signal_at(self, row: int):
        if not (0 <= row < self.rowCount()):
            return None
        source_model = self.sourceModel()
        if not isinstance(source_model, TerminalTableModel):
            return None
        source_index = self.mapToSource(self.index(row, 0))
        return source_model.get_signal_at(source_index.row())


class SmartMoneyFlowView(QWidget):
    """Terminal Style Smart Money Scanner 主視圖"""

    RESPONSIVE_BREAKPOINT = 1120

    def __init__(
        self,
        broker_flow_service: BrokerFlowService,
        watchlist_service: WatchlistService = None,
        smart_money_semantic_service=None,
        parent=None,
        task_worker_factory=TaskWorker,
    ):
        super().__init__(parent)
        self.flow_service = broker_flow_service
        self.watchlist_service = watchlist_service
        self.smart_money_semantic_service = smart_money_semantic_service
        self._data_loaded = False
        self._all_scanner_signals = []
        self._task_worker_factory = task_worker_factory
        self._request_ids = {"dashboard": 0, "detail": 0, "branch": 0}
        self._workers = {}
        self._retired_workers = []
        # Details must share the dashboard's verified Taiwan-market cutoff.
        # Until the first snapshot arrives, there is no safe as-of date to use.
        self._dashboard_as_of_date: date | None = None
        self._dashboard_snapshot = None
        self._dashboard_period: str | None = None
        self._dashboard_scope: str | None = None
        self._branch_request_context: tuple[str, str, date] | None = None
        self._requested_stock_code: str | None = None
        self._scanner_source_model: TerminalTableModel | None = None
        self._scanner_has_result = False
        self._scanner_width_cache_model: object | None = None
        self._scanner_width_cache_font_signature: tuple[str, float, int, int] | None = None
        self._scanner_width_cache: tuple[int, int, int, int] | None = None

        # 色彩設定 (更為精緻的深藍黑背景)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), QColor("#0b0f19"))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        # 設置全域控制元件樣式
        self.setStyleSheet("""
            QComboBox {
                background-color: #1e293b;
                color: #f1f5f9;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 5px 10px;
                min-width: 90px;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox QAbstractItemView {
                background-color: #1e293b;
                color: #f1f5f9;
                selection-background-color: #3b82f6;
                border: 1px solid #334155;
            }
            QLineEdit {
                background-color: #1e293b;
                color: #f1f5f9;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 5px 10px;
                min-width: 150px;
            }
        """)

        self._setup_ui()
        self.installEventFilter(self)

    def _setup_ui(self):
        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)
        page_content = QWidget()
        main_layout = QVBoxLayout(page_content)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # --- Top: Summary Strip ---
        self.summary_strip = SummaryStrip(self)
        main_layout.addWidget(self.summary_strip)

        # --- Controls Bar ---
        control_widget = QWidget()
        self.control_widget = control_widget
        control_widget.setStyleSheet("background-color: #0f172a; border-bottom: 1px solid #1e293b;")
        control_layout = QGridLayout(control_widget)
        self.control_layout = control_layout
        control_layout.setContentsMargins(14, 8, 14, 8)
        control_layout.setHorizontalSpacing(8)
        control_layout.setVerticalSpacing(6)

        self.control_title_label = QLabel("主力流向掃描器")
        self.control_title_label.setStyleSheet(
            "color: #f1f5f9; font-weight: bold; font-size: 14px;"
        )

        self.control_info_button = InfoButton("smart_money_flow", self)

        self.period_label = QLabel("週期")
        self.period_label.setStyleSheet("color: #94a3b8; font-weight: bold;")
        self.period_combo = QComboBox()
        self.period_combo.addItems(["日線 (DAY)", "週線 (WEEK)", "月線 (MONTH)"])
        self.period_combo.setCurrentIndex(1)
        self.period_combo.currentIndexChanged.connect(self._on_period_changed)
        self.scope_label = QLabel("顯示範圍")
        self.scope_label.setStyleSheet("color: #94a3b8; font-weight: bold;")
        self.scope_combo = QComboBox()
        self.scope_combo.addItem("Top / Bottom 50", "top_bottom_50")
        self.scope_combo.addItem("Top 50 買超", "top50")
        self.scope_combo.addItem("Bottom 50 賣超", "bottom50")
        self.scope_combo.addItem("全部", "all")
        self.scope_combo.setToolTip("主表預設顯示買超前 50 與賣超前 50；Summary Strip 仍以全市場訊號為統計母體。")
        self.scope_combo.currentIndexChanged.connect(lambda _idx=False: self._on_scope_changed())
        self.search_label = QLabel("搜尋")
        self.search_label.setStyleSheet("color: #94a3b8; font-weight: bold;")
        self.scanner_search_input = QLineEdit()
        self.scanner_search_input.setPlaceholderText("代號或名稱")
        self.scanner_search_input.setAccessibleName("搜尋目前主表")
        self.scanner_search_input.setAccessibleDescription(
            "只搜尋目前已載入的 Top／Bottom／All 主表範圍，不擴大市場範圍，也不重新查詢資料。"
        )
        self.scanner_search_input.setToolTip(
            "只搜尋目前主表範圍內的股票代號或名稱；不會搜尋全市場或重新讀取資料。"
        )
        self.scanner_search_input.setClearButtonEnabled(True)
        self.scanner_search_input.setMinimumWidth(110)
        self.scanner_search_input.setMaximumWidth(190)
        self.scanner_search_input.textChanged.connect(self._on_scanner_search_changed)
        self.scanner_row_count_label = QLabel("尚未載入")
        self.scanner_row_count_label.setAccessibleName("主表顯示筆數")
        self.scanner_row_count_label.setAccessibleDescription(
            "計算目前所選主表範圍與搜尋條件的符合列，不代表市場完整母體。"
        )
        self.scanner_row_count_label.setToolTip(
            "只計算目前所選主表範圍與搜尋條件的符合列，不代表市場完整母體。"
        )
        self.scanner_row_count_label.setStyleSheet("color: #94a3b8; margin-left: 4px;")
        self.scanner_quality_label = QLabel("品質：尚未載入")
        self.scanner_quality_label.setAccessibleName("主表顯示列品質分類筆數")
        self.scanner_quality_label.setAccessibleDescription(
            "統計目前主表顯示列中含估算事件、張數未知事件及事件分類未知的股票列數；"
            "不代表市場完整母體。"
        )
        self.scanner_quality_label.setToolTip(
            "統計目前主表顯示列。含估算事件或張數未知事件的列，只要至少有一筆相應事件便計一檔。"
            "張數未知表示無法折算，不代表沒有交易或 0 張。事件分類計數合計為 0 時，品質按未知顯示。"
            "這些數字不代表市場完整母體。"
        )
        self.scanner_quality_label.setStyleSheet("color: #94a3b8; margin-left: 6px;")
        self.scanner_quality_label.setWordWrap(True)
        self.scanner_quality_label.setMaximumWidth(240)

        self.chart_label = QLabel("趨勢圖")
        self.chart_label.setStyleSheet("color: #94a3b8; font-weight: bold;")
        self.chart_combo = QComboBox()
        self.chart_combo.addItems(["直方 (BAR)", "折線 (LINE)", "面積 (AREA)"])
        self.chart_combo.setCurrentIndex(0)
        self.chart_combo.currentIndexChanged.connect(self._on_chart_changed)
        # 按鈕美化
        self.refresh_btn = QPushButton("開始掃描")
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                padding: 5px 10px;
            }
            QPushButton:hover {
                background-color: #3b82f6;
            }
            QPushButton:pressed {
                background-color: #1d4ed8;
            }
        """)
        self.refresh_btn.clicked.connect(self._refresh_data)
        self.refresh_btn.setAccessibleName("依目前週期與範圍開始掃描")

        self.load_status_label = QLabel("就緒")
        self.load_status_label.setAccessibleName("主力掃描狀態")
        self.load_status_label.setAccessibleDescription(
            "顯示主力主表最近一次載入或刷新狀態。"
        )
        self.load_status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.load_status_label.setWordWrap(True)
        self.load_status_label.setStyleSheet("color: #94a3b8; margin-left: 8px;")

        if self.watchlist_service:
            self.add_watchlist_btn = QPushButton("+ 觀察清單")
            self.add_watchlist_btn.setStyleSheet("""
                QPushButton {
                    background-color: #059669;
                    color: white;
                    font-weight: bold;
                    border: none;
                    border-radius: 6px;
                    padding: 5px 10px;
                }
                QPushButton:hover {
                    background-color: #10b981;
                }
                QPushButton:pressed {
                    background-color: #047857;
                }
            """)
            self.add_watchlist_btn.clicked.connect(self._add_to_watchlist)
        self._control_layout_widgets = [
            self.control_title_label,
            self.control_info_button,
            self.period_label,
            self.period_combo,
            self.scope_label,
            self.scope_combo,
            self.search_label,
            self.scanner_search_input,
            self.scanner_row_count_label,
            self.scanner_quality_label,
            self.chart_label,
            self.chart_combo,
            self.refresh_btn,
        ]
        if self.watchlist_service:
            self._control_layout_widgets.append(self.add_watchlist_btn)
        self._control_layout_mode: str | None = None
        self._apply_control_layout(force=True)
        main_layout.addWidget(control_widget)
        main_layout.addWidget(self.load_status_label)

        # --- Body: Tabs ---
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #1e293b; background-color: #0b0f19; }
            QTabBar::tab { background: #0f172a; color: #94a3b8; padding: 10px 24px; font-weight: bold; border-right: 1px solid #1e293b; }
            QTabBar::tab:selected { background: #0b0f19; color: #3b82f6; border-bottom: 2px solid #3b82f6; }
        """)
        main_layout.addWidget(self.tab_widget)

        # === Tab 1: Stock Overview ===
        tab1 = QWidget()
        tab1_layout = QVBoxLayout(tab1)
        tab1_layout.setContentsMargins(10, 10, 10, 10)

        # 改為左右分欄 (Qt.Horizontal)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setStyleSheet("QSplitter::handle { background-color: #1e293b; width: 4px; }")

        # Master: Terminal Scanner Table
        self.scanner_table = QTableView()
        self.scanner_table.setSelectionBehavior(QTableView.SelectRows)
        self.scanner_table.setFocusPolicy(Qt.StrongFocus)
        self.scanner_table.setTabKeyNavigation(True)
        self.scanner_table.setAccessibleName("主力資金流向掃描結果")
        self.scanner_table.setAccessibleDescription(
            "使用方向鍵或 Tab 瀏覽股票；信號與近期趨勢提供文字數值替代。"
        )
        self._scanner_proxy_model = SmartMoneyScannerProxyModel(self)
        self.scanner_table.setModel(self._scanner_proxy_model)
        self.scanner_table.selectionModel().selectionChanged.connect(
            self._on_scanner_selection_changed
        )
        self.scanner_table.setSortingEnabled(True)
        self.scanner_table.setMinimumWidth(0)
        self.scanner_table.horizontalHeader().setStretchLastSection(False)
        self.scanner_table.verticalHeader().setVisible(False)
        self.scanner_table.setShowGrid(False)
        self.scanner_table.setStyleSheet("""
            QTableView {
                background-color: #0b0f19;
                color: #e2e8f0;
                gridline-color: #1e293b;
                border: 1px solid #1e293b;
                border-radius: 8px;
            }
            QHeaderView::section {
                background-color: #111827;
                color: #94a3b8;
                border: none;
                border-bottom: 2px solid #3b82f6;
                font-family: 'Segoe UI', Arial;
                font-weight: bold;
                padding: 8px;
            }
            QTableView::item:selected {
                background-color: transparent;
            }
        """)

        # 套用自定義委派
        self.delegate = TerminalScannerDelegate(self.scanner_table)
        self.scanner_table.setItemDelegate(self.delegate)
        # 增加 Row Height 以容納 Badges 與 Sparklines
        self.scanner_table.verticalHeader().setDefaultSectionSize(48)
        ensure_visible_rows(self.scanner_table, rows=5)

        self.splitter.addWidget(self.scanner_table)

        # Detail: Drill-down Card Panel (高質感卡片化與左右排版)
        detail_widget = QFrame()
        detail_widget.setObjectName("DetailCardFrame")
        detail_widget.setMinimumWidth(240)
        detail_widget.setStyleSheet("""
            QFrame#DetailCardFrame {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 8px;
            }
        """)
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.setContentsMargins(15, 15, 15, 15)
        detail_layout.setSpacing(12)

        # 1. 股票摘要與雷達訊號原因卡片
        self.detail_sub_card = QFrame()
        self.detail_sub_card.setStyleSheet("""
            QFrame {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 6px;
            }
            QLabel {
                border: none;
                background: transparent;
            }
        """)
        sub_card_layout = QVBoxLayout(self.detail_sub_card)
        sub_card_layout.setContentsMargins(14, 12, 14, 12)
        sub_card_layout.setSpacing(6)

        self.sub_card_title = QLabel("未選取股票")
        self.sub_card_title.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: bold;")

        self.sub_card_stats = QLabel("請從左側表格點選股票以查看主力分點進出明細與原因")
        self.sub_card_stats.setStyleSheet("color: #94a3b8; font-size: 12px; line-height: 1.5;")
        self.sub_card_stats.setWordWrap(True)

        sub_card_layout.addWidget(self.sub_card_title)
        sub_card_layout.addWidget(self.sub_card_stats)
        detail_layout.addWidget(self.detail_sub_card)

        # 2. 分點明細表標題
        self.detail_label = QLabel("分點買賣明細 (BRANCH DRILL-DOWN)")
        self.detail_label.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: bold; letter-spacing: 0.5px;")
        detail_layout.addWidget(self.detail_label)

        self.detail_status_label = QLabel("選取股票後查看分點資料")
        self.detail_status_label.setAccessibleName("個股分點明細狀態")
        self.detail_status_label.setAccessibleDescription(
            "顯示目前選取股票、資料日，以及分點明細的載入或結果狀態。"
        )
        self.detail_status_label.setWordWrap(True)
        self.detail_status_label.setStyleSheet("color: #94a3b8; font-size: 11px;")
        detail_layout.addWidget(self.detail_status_label)

        # 3. 分點明細表格 (套用雙向水平長條圖 Delegate)
        self.detail_table = QTableView()
        self.detail_table.setSelectionBehavior(QTableView.SelectRows)
        self.detail_table.setFocusPolicy(Qt.StrongFocus)
        self.detail_table.setTabKeyNavigation(True)
        self.detail_table.setAccessibleName("個股分點明細")
        self.detail_table.setAccessibleDescription("使用方向鍵或 Tab 瀏覽分點買賣明細。")
        self.detail_table.installEventFilter(self)
        self.detail_table.setSortingEnabled(True)
        self.detail_table.setShowGrid(False)
        self.detail_table.horizontalHeader().setStretchLastSection(False)
        self.detail_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.detail_table.verticalHeader().setVisible(False)
        self.detail_table.verticalHeader().setDefaultSectionSize(38)
        ensure_visible_rows(self.detail_table, rows=5)
        self.detail_table.setStyleSheet("""
            QTableView {
                background-color: #0b0f19;
                color: #e2e8f0;
                border: 1px solid #1e293b;
                border-radius: 6px;
            }
            QHeaderView::section {
                background-color: #111827;
                color: #94a3b8;
                border: none;
                border-bottom: 2px solid #10b981;
                font-family: 'Segoe UI', Arial;
                font-weight: bold;
                padding: 6px;
            }
            QTableView::item:selected {
                background-color: transparent;
            }
        """)

        self.detail_delegate = DetailTableDelegate(self.detail_table)
        self.detail_table.setItemDelegate(self.detail_delegate)
        self.detail_table.doubleClicked.connect(self._drill_down_branch_from_detail)

        detail_layout.addWidget(self.detail_table)
        self.splitter.addWidget(detail_widget)

        # 設定比例：主表依內容貼合寬度，右側明細保留較大的預設閱讀空間。
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        self.splitter.setSizes([980, 360])
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 1)
        tab1_layout.addWidget(self.splitter)
        self.tab_widget.addTab(tab1, "個股資金流向 (STOCK OVERVIEW)")

        # === Tab 2: Branch Tracker ===
        tab2 = QWidget()
        tab2_layout = QVBoxLayout(tab2)
        tab2_layout.setContentsMargins(10, 10, 10, 10)

        b_control_widget = QWidget()
        b_control_widget.setStyleSheet("background-color: #0f172a; border-radius: 8px; margin-bottom: 8px;")
        b_control_layout = QHBoxLayout(b_control_widget)
        b_control_layout.setContentsMargins(15, 10, 15, 10)
        b_control_layout.addWidget(QLabel("追蹤券商分點:", styleSheet="color: #94a3b8; font-weight: bold;"))

        self.branch_combo = QComboBox()
        self.branch_combo.setMinimumWidth(280)
        self.branch_combo.currentIndexChanged.connect(self._on_branch_changed)
        b_control_layout.addWidget(self.branch_combo)
        b_control_layout.addStretch()
        tab2_layout.addWidget(b_control_widget)

        self.branch_status_label = QLabel("尚未載入分點追蹤資料。")
        self.branch_status_label.setAccessibleName("分點追蹤載入狀態")
        self.branch_status_label.setAccessibleDescription(
            "顯示分點追蹤目前選取的分點、資料日與載入結果。"
        )
        self.branch_status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.branch_status_label.setWordWrap(True)
        self.branch_status_label.setStyleSheet("color: #94a3b8;")
        tab2_layout.addWidget(self.branch_status_label)

        self.branch_table = QTableView()
        self.branch_table.setSelectionBehavior(QTableView.SelectRows)
        self.branch_table.setFocusPolicy(Qt.StrongFocus)
        self.branch_table.setTabKeyNavigation(True)
        self.branch_table.setAccessibleName("分點追蹤結果")
        self.branch_table.setAccessibleDescription(
            "使用方向鍵或 Tab 瀏覽股票；信號與近期趨勢提供文字數值替代。"
        )
        self.branch_table.setSortingEnabled(True)
        self.branch_table.horizontalHeader().setStretchLastSection(False)
        self.branch_table.verticalHeader().setVisible(False)
        self.branch_table.setShowGrid(False)
        self.branch_table.setStyleSheet(self.scanner_table.styleSheet())
        self.branch_table.verticalHeader().setDefaultSectionSize(48)
        ensure_visible_rows(self.branch_table, rows=5)

        self.branch_delegate = TerminalScannerDelegate(self.branch_table)
        self.branch_table.setItemDelegate(self.branch_delegate)
        tab2_layout.addWidget(self.branch_table)

        self.tab_widget.addTab(tab2, "分點進出追蹤 (BRANCH TRACKER)")

        self._on_chart_changed()
        self._smart_money_narrow: bool | None = None
        self._apply_responsive_layout(force=True)
        self.page_scroll_area = create_scroll_area(
            page_content, object_name="smartMoneyPageScrollArea"
        )
        page_layout.addWidget(self.page_scroll_area)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_responsive_layout()

    def eventFilter(self, watched, event):  # noqa: N802 - Qt override
        if watched is self and event.type() == QEvent.Type.Resize:
            self._apply_responsive_layout()
        elif watched is getattr(self, "detail_table", None) and event.type() == QEvent.Type.Resize:
            QTimer.singleShot(0, self._fit_detail_table_columns)
        return super().eventFilter(watched, event)

    def _apply_responsive_layout(self, *, force: bool = False) -> None:
        self._apply_control_layout()
        if not hasattr(self, "splitter"):
            return
        narrow = self.width() < self.RESPONSIVE_BREAKPOINT
        if not force and narrow == self._smart_money_narrow:
            return
        self.splitter.setOrientation(
            Qt.Orientation.Vertical if narrow else Qt.Orientation.Horizontal
        )
        self.splitter.setSizes([560, 360] if narrow else [980, 360])
        self._smart_money_narrow = narrow

    def _apply_control_layout(self, *, force: bool = False) -> None:
        layout = getattr(self, "control_layout", None)
        if layout is None or not hasattr(self, "control_title_label"):
            return
        width = self.width()
        mode = "wide" if width >= 1450 else "medium" if width >= 1050 else "compact"
        if not force and mode == self._control_layout_mode:
            return
        while layout.count():
            item = layout.takeAt(0)
            if item.widget() is not None:
                layout.removeWidget(item.widget())
        for column in range(14):
            layout.setColumnStretch(column, 0)

        title = self.control_title_label
        info = self.control_info_button
        period_label, period = self.period_label, self.period_combo
        scope_label, scope = self.scope_label, self.scope_combo
        search_label, search = self.search_label, self.scanner_search_input
        row_count, quality = self.scanner_row_count_label, self.scanner_quality_label
        chart_label, chart = self.chart_label, self.chart_combo
        refresh = self.refresh_btn
        watchlist = getattr(self, "add_watchlist_btn", None)

        if mode == "wide":
            row = 0
            controls = (
                title, info, period_label, period, scope_label, scope,
                search_label, search, row_count, quality,
                chart_label, chart, refresh, watchlist,
            )
            column = 0
            for widget in controls:
                if widget is not None:
                    layout.addWidget(widget, row, column)
                    column += 1
        elif mode == "medium":
            layout.addWidget(title, 0, 0)
            layout.addWidget(info, 0, 1)
            layout.setColumnStretch(2, 1)
            layout.addWidget(refresh, 0, 3)
            if watchlist is not None:
                layout.addWidget(watchlist, 0, 4)
            for column, widget in enumerate(
                (period_label, period, scope_label, scope, search_label,
                 search, chart_label, chart, row_count, quality)
            ):
                layout.addWidget(widget, 1, column)
        else:
            layout.addWidget(title, 0, 0)
            layout.addWidget(info, 0, 1)
            layout.setColumnStretch(2, 1)
            layout.addWidget(refresh, 0, 3)
            if watchlist is not None:
                layout.addWidget(watchlist, 0, 4)
            for column, widget in enumerate(
                (period_label, period, scope_label, scope, chart_label, chart)
            ):
                layout.addWidget(widget, 1, column)
            for column, widget in enumerate((search_label, search, row_count, quality)):
                layout.addWidget(widget, 2, column)

        self._control_layout_mode = mode

    def _get_current_period_val(self) -> str:
        idx = self.period_combo.currentIndex()
        if idx == 0: return 'day'
        if idx == 2: return 'month'
        return 'week'

    def _on_period_changed(self):
        self._refresh_data()

    def _on_chart_changed(self):
        chart_text = self.chart_combo.currentText()
        if "BAR" in chart_text:
            chart_type = 'bar'
        elif "LINE" in chart_text:
            chart_type = 'line'
        else:
            chart_type = 'area'

        self.delegate.chart_type = chart_type
        self.branch_delegate.chart_type = chart_type
        self.scanner_table.viewport().update()
        self.branch_table.viewport().update()

    def _on_scope_changed(self):
        if self._data_loaded or self._all_scanner_signals:
            self._refresh_data()

    def _filter_scanner_signals(self, signals):
        mode = self.scope_combo.currentData() if hasattr(self, "scope_combo") else "top_bottom_50"
        signals = list(signals or [])
        if mode == "all":
            return signals

        positive = [s for s in signals if s.aggregation.total_net_qty > 0]
        negative = [s for s in signals if s.aggregation.total_net_qty < 0]

        top = sorted(positive, key=lambda s: s.smart_money_score, reverse=True)[:50]
        bottom = sorted(negative, key=lambda s: s.aggregation.total_net_qty)[:50]

        if mode == "top50":
            return top
        if mode == "bottom50":
            return bottom

        filtered = []
        seen_codes = set()
        for signal in [*top, *bottom]:
            if signal.stock_code in seen_codes:
                continue
            filtered.append(signal)
            seen_codes.add(signal.stock_code)
        return filtered

    def _apply_scanner_signals(self, signals, *, semantics_by_code=None):
        filtered_signals = self._filter_scanner_signals(signals)
        semantics_by_code = semantics_by_code or {}
        self._scanner_source_model = TerminalTableModel(
            filtered_signals, semantics_by_code=semantics_by_code
        )
        self._scanner_proxy_model.setSourceModel(self._scanner_source_model)
        self._scanner_proxy_model.set_search_text(self.scanner_search_input.text())
        self.scanner_model = self._scanner_proxy_model
        self._scanner_has_result = True
        self._scanner_width_cache_model = None
        self._scanner_width_cache_font_signature = None
        self._scanner_width_cache = None
        self.scanner_table.clearSelection()
        self._update_scanner_search_summary()

        scanner_header = self.scanner_table.horizontalHeader()
        scanner_header.setStretchLastSection(False)
        scanner_header.setSectionResizeMode(QHeaderView.Interactive)
        scanner_widths = {
            0: 64,   # 分數
            1: 180,  # 股票
            2: 82,   # 淨量
            3: 68,   # 集中度
            4: 78,   # 語意狀態
            6: 150,  # Badges
            7: 190,  # Trend
        }
        for col, width in scanner_widths.items():
            scanner_header.setSectionResizeMode(col, QHeaderView.Interactive)
            self.scanner_table.setColumnWidth(col, width)
        scanner_header.setSectionResizeMode(5, QHeaderView.Interactive)
        self._fit_scanner_diagnostic_column()

        self.sub_card_title.setText("未選取股票")
        self.sub_card_stats.setText("請從左側表格點選股票以查看主力分點進出明細與原因")
        self.detail_table.setModel(PandasTableModel(pd.DataFrame(columns=['分點名稱', '買進張數', '賣出張數', '淨買賣超'])))

    def _update_scanner_search_summary(self) -> None:
        source_model = self._scanner_source_model
        if not self._scanner_has_result or source_model is None:
            self.scanner_row_count_label.setText("尚未載入")
            self.scanner_quality_label.setText("品質：尚未載入")
            return

        scope_count = source_model.rowCount()
        matching_count = self._scanner_proxy_model.rowCount()
        query = self.scanner_search_input.text().strip()
        if scope_count == 0:
            count_text = "顯示 0 檔"
        elif query and matching_count == 0:
            count_text = f"此範圍無符合標的（0／{scope_count}）"
        elif query:
            count_text = f"符合 {matching_count}／範圍 {scope_count} 檔"
        else:
            count_text = f"顯示 {scope_count} 檔"
        self.scanner_row_count_label.setText(count_text)

        estimated_rows = 0
        unavailable_rows = 0
        unclassified_rows = 0
        for row in range(matching_count):
            signal = self._scanner_proxy_model.get_signal_at(row)
            if signal is None:
                continue
            try:
                observed_count = int(
                    getattr(signal, "observed_event_count", 0) or 0
                )
                estimated_count = int(
                    getattr(signal, "estimated_event_count", 0) or 0
                )
                unavailable_count = int(
                    getattr(signal, "unavailable_event_count", 0) or 0
                )
            except (TypeError, ValueError):
                unclassified_rows += 1
                continue
            if min(observed_count, estimated_count, unavailable_count) < 0:
                unclassified_rows += 1
                continue
            if observed_count + estimated_count + unavailable_count <= 0:
                unclassified_rows += 1
                continue
            if estimated_count > 0:
                estimated_rows += 1
            if unavailable_count > 0:
                unavailable_rows += 1
        self.scanner_quality_label.setText(
            f"品質：估算 {estimated_rows}／張數未知 {unavailable_rows}／"
            f"未分類 {unclassified_rows}"
        )

    def _on_scanner_search_changed(self, text: str) -> None:
        selection = self.scanner_table.selectionModel().selectedRows()
        selected_signal = (
            self._scanner_proxy_model.get_signal_at(selection[0].row())
            if selection and self._scanner_source_model is not None
            else None
        )
        self._scanner_proxy_model.set_search_text(text)
        self._update_scanner_search_summary()
        if selected_signal is not None and not self._scanner_proxy_model.matches_signal(selected_signal):
            self.scanner_table.clearSelection()
            self._clear_hidden_scanner_selection(selected_signal)

    def _clear_hidden_scanner_selection(self, signal) -> None:
        self._requested_stock_code = None
        self._request_ids["detail"] += 1
        worker = self._workers.pop("detail", None)
        if worker is not None:
            worker.cancel(cooperative=True, wait=False)
            self._retired_workers.append(worker)
        self._clear_stock_detail()
        self.detail_label.setText("分點買賣明細 (BRANCH DRILL-DOWN)")
        self.detail_status_label.setText(
            f"搜尋已隱藏 {signal.stock_name}（{signal.stock_code}）；調整搜尋或重新選股以查看分點資料。"
        )
        self.detail_status_label.setToolTip("")
        self.sub_card_title.setText("未選取股票")
        self.sub_card_stats.setText("請從左側表格點選股票以查看主力分點進出明細與原因")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "scanner_table") and self.scanner_table.model() is not None:
            self._fit_scanner_diagnostic_column()
        if hasattr(self, "detail_table") and self.detail_table.model() is not None:
            self._fit_detail_table_columns()

    def _fit_scanner_diagnostic_column(self):
        model = self.scanner_table.model()
        content_model = self._scanner_source_model
        if model is None or content_model is None:
            self._scanner_width_cache_model = None
            self._scanner_width_cache_font_signature = None
            self._scanner_width_cache = None
            return

        concentration_col = 3
        semantic_col = 4
        diagnostic_col = 5
        badges_col = 6
        trend_col = 7

        font_metrics = self.scanner_table.fontMetrics()
        (
            concentration_width,
            semantic_width,
            badges_width,
            diagnostic_content_width,
        ) = self._scanner_column_content_widths(content_model, font_metrics)
        trend_width = 190
        self.scanner_table.setColumnWidth(concentration_col, concentration_width)
        self.scanner_table.setColumnWidth(semantic_col, semantic_width)
        self.scanner_table.setColumnWidth(badges_col, badges_width)
        self.scanner_table.setColumnWidth(trend_col, trend_width)

        left_and_middle_width = sum(
            self.scanner_table.columnWidth(col)
            for col in range(model.columnCount())
            if col != diagnostic_col
        )
        viewport_width = max(0, self.scanner_table.viewport().width() - 18)
        diagnostic_available_width = max(220, viewport_width - left_and_middle_width)
        diagnostic_width = min(diagnostic_content_width, diagnostic_available_width)
        self.scanner_table.setColumnWidth(diagnostic_col, diagnostic_width)

        total_column_width = sum(
            self.scanner_table.columnWidth(col)
            for col in range(model.columnCount())
        )
        preferred_table_width = total_column_width + 24
        self.scanner_table.setMaximumWidth(max(920, preferred_table_width))

    def _scanner_column_content_widths(
        self, model, font_metrics
    ) -> tuple[int, int, int, int]:
        font_signature = (
            self.scanner_table.font().toString(),
            self.scanner_table.devicePixelRatioF(),
            font_metrics.height(),
            font_metrics.horizontalAdvance("MW測試"),
        )
        if (
            self._scanner_width_cache_model is not model
            or self._scanner_width_cache_font_signature != font_signature
            or self._scanner_width_cache is None
        ):
            self._scanner_width_cache = (
                self._fit_text_column_width(
                    model, 3, minimum=54, maximum=70, padding=18
                ),
                self._fit_text_column_width(
                    model, 4, minimum=66, maximum=86, padding=18
                ),
                self._fit_badges_column_width(model, 6, font_metrics),
                self._fit_text_column_width(
                    model, 5, minimum=250, maximum=420, padding=34
                ),
            )
            self._scanner_width_cache_model = model
            self._scanner_width_cache_font_signature = font_signature
        return self._scanner_width_cache

    def _fit_text_column_width(self, model, column: int, minimum: int, maximum: int, padding: int) -> int:
        font_metrics = self.scanner_table.fontMetrics()
        header_text = str(model.headerData(column, Qt.Horizontal) or "")
        content_width = font_metrics.horizontalAdvance(header_text) + padding
        for row in range(model.rowCount()):
            text = str(model.data(model.index(row, column), Qt.DisplayRole) or "")
            content_width = max(content_width, font_metrics.horizontalAdvance(text) + padding)
        return min(max(content_width, minimum), maximum)

    def _fit_badges_column_width(self, model, column: int, font_metrics) -> int:
        header_text = str(model.headerData(column, Qt.Horizontal) or "")
        content_width = font_metrics.horizontalAdvance(header_text) + 24
        for row in range(model.rowCount()):
            badges = model.data(model.index(row, column), ROLE_BADGES) or []
            if not badges:
                continue
            badge_width = 20
            for badge in badges:
                badge_width += font_metrics.horizontalAdvance(str(badge)) + 22
            badge_width += max(0, len(badges) - 1) * 4
            content_width = max(content_width, badge_width)
        return min(max(content_width, 128), 280)

    def _drill_down_branch_from_detail(self, index):
        if not index.isValid() or self.detail_table.model() is None:
            return
        model = self.detail_table.model()
        if not hasattr(model, "getDataFrame"):
            return
        df = model.getDataFrame()
        if index.row() >= len(df) or "分點名稱" not in df.columns:
            return

        branch_name = str(df.iloc[index.row()].get("分點名稱", "")).strip()
        if not branch_name:
            return

        match_idx = self.branch_combo.findText(branch_name)
        if match_idx < 0:
            QMessageBox.warning(self, "找不到分點", f"分點追蹤清單中找不到「{branch_name}」。")
            return

        self.tab_widget.setCurrentIndex(1)
        self.branch_combo.setCurrentIndex(match_idx)
        self._on_branch_changed()

    def _period_display_label(self, period):
        return {
            "day": "日線 (DAY)",
            "week": "週線 (WEEK)",
            "month": "月線 (MONTH)",
        }.get(str(period), str(period))

    def _scope_display_label(self, scope):
        index = self.scope_combo.findData(scope)
        return self.scope_combo.itemText(index) if index >= 0 else "範圍未知"

    def _dashboard_query_label(self, period, scope):
        return (
            f"{self._period_display_label(period)}／"
            f"{self._scope_display_label(scope)}"
        )

    def _current_dashboard_query_label(self):
        return self._dashboard_query_label(
            self._get_current_period_val(), self.scope_combo.currentData()
        )

    def _retained_dashboard_notice(self):
        snapshot = self._dashboard_snapshot
        if snapshot is None:
            return ""
        previous_query = self._dashboard_query_label(
            self._dashboard_period, self._dashboard_scope
        )
        return (
            f"畫面仍顯示前次成功結果「{previous_query}」"
            f"（資料日：{snapshot.as_of_date.isoformat()}）"
        )

    def _refresh_data(self):
        try:
            requested_as_of_date = taiwan_market_today()
        except Exception as exc:
            # Do not start a request with the workstation's local date. Keep an
            # already-rendered snapshot intact, but make the failed refresh clear.
            previous = self._workers.get("dashboard")
            if previous is not None:
                previous.cancel(cooperative=True, wait=False)
                self._retired_workers.append(previous)
            self._request_ids["dashboard"] += 1
            self._workers.pop("dashboard", None)
            self.refresh_btn.setEnabled(True)
            self.period_combo.setEnabled(True)
            self.scope_combo.setEnabled(True)
            detail = str(exc).strip().splitlines()
            retained_notice = self._retained_dashboard_notice()
            retained_suffix = (
                f"｜目前選擇「{self._current_dashboard_query_label()}」；{retained_notice}"
                if retained_notice
                else ""
            )
            self.load_status_label.setText(
                f"主力資料日期無法取得：{detail[0] if detail else type(exc).__name__}"
                f"{retained_suffix}"
            )
            return

        query = BrokerFlowDashboardQuery(
            period=self._get_current_period_val(),
            scope=str(self.scope_combo.currentData()),
            requested_as_of_date=requested_as_of_date,
            limit_per_side=50,
        )
        self.refresh_btn.setEnabled(False)
        self.period_combo.setEnabled(False)
        self.scope_combo.setEnabled(False)
        retained_notice = self._retained_dashboard_notice()
        loading_status = "主力資料更新中…" if retained_notice else "主力資料載入中…"
        retained_suffix = (
            f"｜目前選擇「{self._current_dashboard_query_label()}」；{retained_notice}"
            if retained_notice
            else ""
        )
        self.load_status_label.setText(f"{loading_status}{retained_suffix}")
        self._start_request(
            "dashboard",
            lambda: self.flow_service.load_dashboard_snapshot(query),
            lambda snapshot, requested_scope=query.scope: self._apply_dashboard_snapshot(
                snapshot, scope=requested_scope
            ),
        )

    def _start_request(self, kind, task, on_success):
        previous = self._workers.get(kind)
        if previous is not None:
            previous.cancel(cooperative=True, wait=False)
            self._retired_workers.append(previous)
        self._request_ids[kind] += 1
        request_id = self._request_ids[kind]
        worker = self._task_worker_factory(task)
        self._workers[kind] = worker
        worker.finished.connect(
            lambda result, k=kind, rid=request_id: self._finish_request(
                k, rid, lambda: on_success(result)
            )
        )
        worker.error.connect(
            lambda message, k=kind, rid=request_id: self._finish_request(
                k, rid, lambda: self._show_request_error(k, message)
            )
        )
        worker.cancelled.connect(
            lambda k=kind, rid=request_id: self._finish_request(k, rid, lambda: None)
        )
        worker.finished.connect(lambda _result, item=worker: self._release_worker(item))
        worker.error.connect(lambda _message, item=worker: self._release_worker(item))
        worker.cancelled.connect(lambda item=worker: self._release_worker(item))
        worker.start()

    def _release_worker(self, worker):
        if worker in self._retired_workers:
            self._retired_workers.remove(worker)

    def _finish_request(self, kind, request_id, callback):
        if request_id != self._request_ids[kind]:
            return
        self._workers.pop(kind, None)
        callback()
        if kind == "dashboard":
            self.refresh_btn.setEnabled(True)
            self.period_combo.setEnabled(True)
            self.scope_combo.setEnabled(True)

    def _show_request_error(self, kind, message):
        error_lines = str(message).strip().splitlines()
        error_summary = error_lines[0] if error_lines else "未知錯誤"
        if kind == "dashboard":
            retained_notice = self._retained_dashboard_notice()
            action = "更新" if retained_notice else "載入"
            retained_suffix = (
                f"｜目前選擇「{self._current_dashboard_query_label()}」；{retained_notice}"
                if retained_notice
                else ""
            )
            self.load_status_label.setText(
                f"主力資料{action}失敗：{error_summary}{retained_suffix}"
            )
            return
        if kind == "branch":
            context = self._branch_request_context
            if context is None:
                prefix = "分點追蹤"
            else:
                branch_name, period, as_of_date = context
                prefix = (
                    f"{branch_name}｜{self._period_display_label(period)}｜"
                    f"資料日 {as_of_date.isoformat()}｜分點追蹤"
                )
            self.branch_status_label.setText(f"{prefix}載入失敗：{error_summary}")
            self.branch_status_label.setToolTip(str(message).strip())
            return
        if kind == "detail":
            self._clear_stock_detail()
            self.detail_label.setText("分點買賣明細 (BRANCH DRILL-DOWN)")
            stock_code = self._requested_stock_code or "目前選取股票"
            as_of_date = (
                self._dashboard_as_of_date.isoformat()
                if self._dashboard_as_of_date is not None
                else "日期未知"
            )
            self.detail_status_label.setText(
                f"{stock_code}｜資料日 {as_of_date}｜分點明細載入失敗，請重新選取或刷新"
            )
            self.detail_status_label.setToolTip(str(message).strip())
            return
        self.load_status_label.setText(f"載入失敗：{error_summary}")

    def _apply_dashboard_snapshot(self, snapshot, *, scope=None):
        self._dashboard_snapshot = snapshot
        current_scope = self.scope_combo.currentData() if scope is None else scope
        self._dashboard_scope = str(current_scope) if current_scope is not None else None
        self._dashboard_period = getattr(
            snapshot, "period", self._get_current_period_val()
        )
        self._dashboard_as_of_date = snapshot.as_of_date
        self._all_scanner_signals = list((*snapshot.top_signals, *snapshot.bottom_signals))
        self.summary_strip.update_summary(snapshot.summary)
        self._apply_scanner_signals(
            self._all_scanner_signals,
            semantics_by_code=snapshot.semantics_by_code,
        )
        current_branch = self.branch_combo.currentData()
        self.branch_combo.blockSignals(True)
        self.branch_combo.clear()
        selected_index = 0
        for index, (system_key, display_name) in enumerate(snapshot.tracked_branches):
            self.branch_combo.addItem(display_name, system_key)
            if system_key == current_branch:
                selected_index = index
        if snapshot.tracked_branches:
            self.branch_combo.setCurrentIndex(selected_index)
        self.branch_combo.blockSignals(False)
        self._data_loaded = True
        query_label = self._dashboard_query_label(
            self._dashboard_period, self._dashboard_scope
        )
        self.load_status_label.setText(
            f"主力資料完成｜{query_label}｜資料日 {snapshot.as_of_date.isoformat()}｜"
            f"{snapshot.quality}"
        )
        self._on_branch_changed()

        if self._requested_stock_code:
            self.select_stock(self._requested_stock_code)

    def _on_scanner_selection_changed(self):
        if self._dashboard_as_of_date is None:
            return
        selection = self.scanner_table.selectionModel().selectedRows()
        if not selection:
            return

        row = selection[0].row()
        signal = self.scanner_model.get_signal_at(row)
        if not signal:
            return
        self._requested_stock_code = signal.stock_code

        # 1. 更新股票摘要卡片
        self.sub_card_title.setText(f"{signal.stock_name} ({signal.stock_code})")

        warning_html = ""
        if getattr(signal, 'has_estimated_lots', False):
            warning_html = "<div style='color:#f97316; font-weight:bold; margin-bottom:6px;'>注意：本訊號包含歷史金額與股價折算之估計張數資料</div>"

        stats_html = warning_html + (
            f"<span style='color:#94a3b8;'>主力分數：</span><b><font color='#ffffff'>{signal.smart_money_score:.1f}</font></b>"
            f" &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"<span style='color:#94a3b8;'>籌碼集中度：</span><b><font color='#ffffff'>{signal.branch_concentration:.0%}</font></b><br/>"
        )
        if signal.explainable_reasons:
            stats_html += "<br/><b><span style='color:#3b82f6;'>訊號解析原因：</span></b><br/>"
            for reason in signal.explainable_reasons:
                stats_html += f"• {reason}<br/>"
        self.sub_card_stats.setText(stats_html)

        # 2. 載入 Detail
        period = self._get_current_period_val()
        as_of_date = self._dashboard_as_of_date
        dashboard_snapshot = self._dashboard_snapshot
        self._clear_stock_detail()
        self.detail_label.setText("分點買賣明細 (BRANCH DRILL-DOWN)｜載入中…")
        self.detail_status_label.setText(
            f"{signal.stock_code}｜資料日 {as_of_date.isoformat()}｜"
            "分點明細載入中…"
        )
        self.detail_status_label.setToolTip("")
        detail_task = self._stock_detail_task(
            signal.stock_code, period, as_of_date, dashboard_snapshot
        )
        self._start_request(
            "detail",
            detail_task,
            self._apply_stock_detail,
        )

    def _stock_detail_task(self, stock_code, period, as_of_date, dashboard_snapshot):
        loader = self.flow_service.load_stock_branch_detail
        if dashboard_snapshot is not None:
            try:
                inspect.signature(loader).bind(
                    stock_code,
                    period,
                    as_of_date,
                    dashboard_snapshot=dashboard_snapshot,
                )
            except (TypeError, ValueError):
                pass
            else:
                return lambda: loader(
                    stock_code,
                    period,
                    as_of_date,
                    dashboard_snapshot=dashboard_snapshot,
                )
        return lambda: loader(stock_code, period, as_of_date)

    def _apply_stock_detail(self, snapshot):
        self.detail_label.setText("分點買賣明細 (BRANCH DRILL-DOWN)")
        details = snapshot.rows

        # 先按淨買賣超數值進行數值排序 (None 視為極小)
        details_sorted = sorted(
            details,
            key=lambda x: x.total_net_qty if x.total_net_qty is not None else -99999999,
            reverse=True
        )

        data = []
        for d in details_sorted:
            if d.usable_event_count == 0:
                buy_val = "—"
                sell_val = "—"
                net_val = "不可用"
            else:
                if d.has_estimated_lots:
                    buy_val = f"{d.total_buy_qty:,}*(估)" if d.total_buy_qty is not None else "—"
                    sell_val = f"{d.total_sell_qty:,}*(估)" if d.total_sell_qty is not None else "—"
                    net_val = f"{d.total_net_qty:+,}*(估)" if d.total_net_qty is not None else "0*(估)"
                else:
                    buy_val = f"{d.total_buy_qty:,}" if d.total_buy_qty is not None else "—"
                    sell_val = f"{d.total_sell_qty:,}" if d.total_sell_qty is not None else "—"
                    net_val = f"{d.total_net_qty:+,}" if d.total_net_qty is not None else "0"

            data.append({
                '分點名稱': d.branch_display_name,
                '買進張數': buy_val,
                '賣出張數': sell_val,
                '淨買賣超': net_val
            })

        df_detail = pd.DataFrame(data) if data else pd.DataFrame(columns=['分點名稱', '買進張數', '賣出張數', '淨買賣超'])
        self.detail_table.setModel(PandasTableModel(df_detail))
        self._fit_detail_table_columns()
        status_prefix = (
            f"{snapshot.stock_code}｜資料日 {snapshot.as_of_date.isoformat()}｜品質 {snapshot.quality}"
        )
        self.detail_status_label.setToolTip("\n".join(snapshot.warnings))
        if details:
            self.detail_status_label.setText(f"{status_prefix}｜{len(details)} 個分點")
        elif snapshot.quality in {"missing", "unavailable"}:
            self.detail_status_label.setText(
                f"{status_prefix}｜來源資料不可用，無法確認是否有分點交易"
            )
        elif snapshot.quality == "degraded":
            self.detail_status_label.setText(
                f"{status_prefix}｜沒有可呈現的分點資料；請檢查來源警示"
            )
        else:
            self.detail_status_label.setText(f"{status_prefix}｜本次沒有可呈現的分點資料")

    def _clear_stock_detail(self):
        self.detail_table.setModel(
            PandasTableModel(
                pd.DataFrame(columns=['分點名稱', '買進張數', '賣出張數', '淨買賣超'])
            )
        )

    def _fit_detail_table_columns(self):
        model = self.detail_table.model()
        if model is None or model.columnCount() == 0:
            return

        header = self.detail_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.Interactive)

        viewport_width = max(0, self.detail_table.viewport().width() - 18)
        if viewport_width <= 0:
            return

        column_count = min(model.columnCount(), 4)
        font_metrics = self.detail_table.fontMetrics()
        minimums = [98, 56, 56, 128]
        paddings = [16, 12, 12, 56]
        desired_widths = []
        for col in range(column_count):
            header_text = str(model.headerData(col, Qt.Horizontal) or "")
            content_width = font_metrics.horizontalAdvance(header_text) + paddings[col]
            for row in range(model.rowCount()):
                text = str(model.data(model.index(row, col), Qt.DisplayRole) or "")
                content_width = max(content_width, font_metrics.horizontalAdvance(text) + paddings[col])
            desired_widths.append(max(minimums[col], content_width))

        total_desired = sum(desired_widths)
        if total_desired < viewport_width:
            extra = viewport_width - total_desired
            weights = [2, 1, 1, 3]
            total_weight = sum(weights[:column_count])
            widths = [
                desired_widths[col] + int(extra * weights[col] / total_weight)
                for col in range(column_count)
            ]
            widths[-1] += viewport_width - sum(widths)
        else:
            widths = desired_widths
            overflow = total_desired - viewport_width
            for col in (0, 1, 2, 3):
                if col >= column_count or overflow <= 0:
                    break
                reducible = max(0, widths[col] - minimums[col])
                reduction = min(reducible, overflow)
                widths[col] -= reduction
                overflow -= reduction

        for col, width in enumerate(widths):
            self.detail_table.setColumnWidth(col, max(48, width))

    def _on_branch_changed(self):
        branch_key = self.branch_combo.currentData()
        if not branch_key or self._dashboard_as_of_date is None:
            return

        period = self._get_current_period_val()
        as_of_date = self._dashboard_as_of_date
        branch_name = self.branch_combo.currentText()
        self._branch_request_context = (branch_name, period, as_of_date)
        self.branch_table.setModel(BranchTrackerTableModel([]))
        self.branch_status_label.setToolTip("")
        self.branch_status_label.setText(
            f"{branch_name}｜{self._period_display_label(period)}｜"
            f"資料日 {as_of_date.isoformat()}｜分點追蹤載入中…"
        )
        self._start_request(
            "branch",
            lambda: self.flow_service.load_branch_tracker(
                branch_key, period, as_of_date
            ),
            self._apply_branch_tracker,
        )

    def _apply_branch_tracker(self, snapshot):
        branch_flows = snapshot.rows

        self.branch_model = BranchTrackerTableModel(branch_flows)
        self.branch_table.setModel(self.branch_model)

        # 調整欄寬
        branch_header = self.branch_table.horizontalHeader()
        branch_header.setStretchLastSection(False)
        branch_header.setSectionResizeMode(QHeaderView.Interactive)
        self.branch_table.setColumnWidth(0, 110) # 淨量分數
        self.branch_table.setColumnWidth(1, 160) # 股票
        self.branch_table.setColumnWidth(2, 90)  # 買進
        self.branch_table.setColumnWidth(3, 90)  # 賣出
        self.branch_table.setColumnWidth(4, 200) # Badges
        self.branch_table.setColumnWidth(5, 150) # Sparkline
        self.branch_status_label.setToolTip("\n".join(snapshot.warnings))
        self.branch_status_label.setText(
            f"{self.branch_combo.currentText()}｜{self._period_display_label(snapshot.period)}｜"
            f"資料日 {snapshot.as_of_date.isoformat()}｜{snapshot.quality}｜"
            f"{len(branch_flows)} 檔"
        )

    def _add_to_watchlist(self):
        if not self.watchlist_service:
            return

        selection = self.scanner_table.selectionModel().selectedRows()
        if not selection:
            QMessageBox.warning(self, "提示", "請先選擇要加入觀察清單的股票")
            return

        stocks_to_add = []
        for index in selection:
            signal = self.scanner_model.get_signal_at(index.row())
            if signal:
                stocks_to_add.append({
                    'stock_code': signal.stock_code,
                    'stock_name': signal.stock_name
                })

        if stocks_to_add:
            try:
                added_count = self.watchlist_service.add_stocks(stocks_to_add, source='smart_money')
                if added_count > 0:
                    QMessageBox.information(self, "成功", f"已將 {added_count} 檔股票加入觀察清單")
                else:
                    QMessageBox.warning(self, "提示", "選中的股票已在觀察清單中")
            except Exception as e:
                QMessageBox.critical(self, "錯誤", f"加入觀察清單失敗：\n{str(e)}")

    def load_data_if_needed(self):
        if not self._data_loaded:
            self._refresh_data()

    @staticmethod
    def _worker_is_running(worker) -> bool:
        """回報 worker 是否仍在執行；未知實作一律保守視為執行中。"""
        is_running = getattr(worker, "isRunning", None)
        if callable(is_running):
            return bool(is_running())
        # 測試替身或外部注入 worker 若不提供生命週期查詢，不能假設它已安全停止。
        return True

    def closeEvent(self, event):
        workers = (*tuple(self._workers.values()), *tuple(self._retired_workers))
        for worker in workers:
            if self._worker_is_running(worker):
                worker.cancel(cooperative=True, wait=False)
        if any(self._worker_is_running(worker) for worker in workers):
            event.ignore()
            return
        self._workers.clear()
        super().closeEvent(event)

    def select_stock(self, stock_code: str):
        """開啟指定個股；未入掃描榜仍可查分點，初次載入後重套選取。"""
        stock_code = str(stock_code).strip()
        if not stock_code:
            return
        self._requested_stock_code = stock_code
        self.load_data_if_needed()
        if self._dashboard_as_of_date is None:
            return
        source_model = self._scanner_source_model
        if source_model is None:
            return

        stock_code = str(stock_code).strip()
        row_idx = -1
        for r in range(source_model.rowCount()):
            sig = source_model.get_signal_at(r)
            if sig and sig.stock_code == stock_code:
                row_idx = r
                break

        if row_idx != -1:
            view_index = self._scanner_proxy_model.mapFromSource(
                source_model.index(row_idx, 0)
            )
            if not view_index.isValid():
                self.scanner_search_input.clear()
                view_index = self._scanner_proxy_model.mapFromSource(
                    source_model.index(row_idx, 0)
                )
            selection_model = self.scanner_table.selectionModel()
            if selection_model and view_index.isValid():
                selection_model.select(
                    view_index,
                    QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows
                )
                self.scanner_table.scrollTo(view_index)
                self._on_scanner_selection_changed()
        else:
            self.scanner_table.clearSelection()
            self.sub_card_title.setText(stock_code)
            self.sub_card_stats.setText("此股票未列入目前掃描榜；未提供榜單分數，仍可查看分點資料。")
            self._clear_stock_detail()
            self.detail_label.setText("分點買賣明細 (BRANCH DRILL-DOWN)｜載入中…")
            self.detail_status_label.setText(
                f"{stock_code}｜資料日 {self._dashboard_as_of_date.isoformat()}｜"
                "分點明細載入中…"
            )
            self.detail_status_label.setToolTip("")
            period = self._get_current_period_val()
            as_of_date = self._dashboard_as_of_date
            dashboard_snapshot = self._dashboard_snapshot
            detail_task = self._stock_detail_task(
                stock_code, period, as_of_date, dashboard_snapshot
            )
            self._start_request(
                "detail",
                detail_task,
                self._apply_stock_detail,
            )
