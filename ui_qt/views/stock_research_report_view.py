"""可互動的單股研究報告視圖。

畫面只呈現 ``StockResearchReportDTO``；所有真資料查詢都由
``TaskWorker`` 執行，且以 request id + stock code 丟棄過期回傳。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from decimal import Decimal
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush
from PySide6.QtWidgets import (
    QDialog,
    QAbstractItemView,
    QFrame,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QTableView,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from app_module.research_session import (
    ResearchStockContextDTO,
    format_research_workflow_path,
)
from app_module.stock_research_report_dtos import (
    ReportSectionStatus,
    StockAdviceSnapshotDTO,
    StockEvidenceEventDTO,
    StockFlowObservationDTO,
    StockFundamentalObservationDTO,
    StockMetricDTO,
    StockPositionSnapshotDTO,
    StockPricePointDTO,
    StockResearchReportDTO,
)
from app_module.decision_presentation import (
    DecisionPresentationService,
    format_decision_presentation,
)
from app_module.decision_continuity_controller import DecisionContinuityController
from app_module.decision_outcome_journey import DecisionOutcomeJourneyService
from app_module.research_result_presentation import (
    ResearchTablePresentation,
    build_shareholding_tier_table,
    build_stock_research_event_table,
)
from app_module.stock_research_report_service import StockResearchReportReadService
from ui_qt.theme import MIDNIGHT_ANALYST
from ui_qt.widgets.decision_outcome_journey_widget import DecisionOutcomeJourneyWidget
from ui_qt.widgets.layout_helpers import (
    ensure_visible_rows,
    set_scroll_content_constraints,
)
from ui_qt.widgets.theme_widgets import StatusBadge
from ui_qt.widgets.table_style import apply_financial_table_style
from ui_qt.widgets.v5_research_summary import V5ResearchSummary
from ui_qt.workers.task_worker import TaskWorker


class StockReportTableModel(QAbstractTableModel):
    """針對有限 DTO rows 的小型 Qt model，保留完整 tooltip 文字。"""

    def __init__(
        self,
        columns: Sequence[str],
        rows: Sequence[Sequence[str]],
        parent: QWidget | None = None,
        *,
        tooltips: Sequence[Sequence[str]] | None = None,
        numeric_columns: Sequence[int] = (),
    ) -> None:
        super().__init__(parent)
        self._columns = tuple(columns)
        self._rows = tuple(tuple(str(cell) for cell in row) for row in rows)
        self._tooltips = (
            tuple(tuple(str(cell) for cell in row) for row in tooltips)
            if tooltips is not None
            else ()
        )
        self._numeric_columns = frozenset(int(column) for column in numeric_columns)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._columns)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or index.row() >= len(self._rows):
            return None
        row = self._rows[index.row()]
        if index.column() >= len(row):
            return None
        value = row[index.column()]
        if role == Qt.DisplayRole:
            return value
        if role == Qt.ToolTipRole:
            if index.row() < len(self._tooltips):
                tooltip_row = self._tooltips[index.row()]
                if index.column() < len(tooltip_row) and tooltip_row[index.column()]:
                    return tooltip_row[index.column()]
            return value
        if role == Qt.TextAlignmentRole:
            if index.column() in self._numeric_columns:
                return Qt.AlignRight | Qt.AlignVCenter
            return Qt.AlignLeft | Qt.AlignVCenter
        return None

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.DisplayRole,
    ) -> Any:
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal and section < len(self._columns):
            return self._columns[section]
        if orientation == Qt.Vertical:
            return str(section + 1)
        return None


class StockPriceChartWidget(QWidget):
    """無第三方互動依賴的 bounded 價格圖，資料不足時明示收盤圖。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._points: tuple[StockPricePointDTO, ...] = ()
        self._mode = "close"
        self._hover_index: int | None = None
        self._base_tooltip = "目前沒有可繪製的價格資料。"
        self.setMinimumHeight(188)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)
        self.setAccessibleName("個股收盤價走勢圖")
        self.setAccessibleDescription(
            "最近有限交易日的價格圖；下方價格表提供可選取的日期與數值。"
        )

    def set_points(self, points: Sequence[StockPricePointDTO]) -> None:
        self._points = tuple(points)
        self._mode = self._resolve_mode(self._points)
        self._hover_index = None
        QToolTip.hideText()
        if self._points:
            last = self._points[-1]
            mode_text = {
                "ohlc_volume": "K 線與成交量",
                "ohlc": "K 線（成交量資料不足）",
                "close": "收盤價走勢",
            }[self._mode]
            self._base_tooltip = (
                f"{mode_text}；{_price_chart_range_text(self._points)}；"
                f"最新收盤價：{_decimal_text(last.close_price)}。"
                "將游標移到各資料點查看該日日期、開高低收與成交量；"
                "圖表只作視覺化，不代表預測。"
            )
            self.setToolTip(self._base_tooltip)
            self.setAccessibleDescription(
                f"{mode_text}；{_price_chart_range_text(self._points)}；"
                "將游標移到各資料點查看該日日期、開高低收與成交量；"
                "下方價格表提供可選取的日期與數值。"
            )
        else:
            self._base_tooltip = "目前沒有可繪製的價格資料。"
            self.setToolTip(self._base_tooltip)
            self.setAccessibleDescription("目前沒有可繪製的價格資料。")
        self.update()

    def _drawable_points(self) -> tuple[StockPricePointDTO, ...]:
        return tuple(point for point in self._points if point.close_price is not None)

    def _plot_x_bounds(self) -> tuple[int, int]:
        left = 58
        return left, max(left + 40, self.width() - 18)

    def _nearest_point_index(self, x: int) -> int | None:
        points = self._drawable_points()
        if not points:
            return None
        left, right = self._plot_x_bounds()
        if x < left or x > right:
            return None
        span = max(1, right - left)
        relative_x = max(0, min(span, x - left))
        index = (
            relative_x * (len(points) - 1) + span // 2
        ) // span
        return min(len(points) - 1, index)

    @staticmethod
    def _point_tooltip(point: StockPricePointDTO) -> str:
        return "\n".join(
            (
                f"日期：{point.data_date or '未提供'}",
                "｜".join(
                    (
                        f"開盤：{_chart_decimal_text(point.open_price)}",
                        f"最高：{_chart_decimal_text(point.high_price)}",
                        f"最低：{_chart_decimal_text(point.low_price)}",
                        f"收盤：{_chart_decimal_text(point.close_price)}",
                    )
                ),
                f"成交量：{_chart_integer_text(point.volume)}",
            )
        )

    def _clear_hover(self) -> None:
        self._hover_index = None
        self.setToolTip(self._base_tooltip)
        QToolTip.hideText()

    def mouseMoveEvent(self, event: Any) -> None:  # noqa: N802 - Qt override
        index = self._nearest_point_index(int(event.position().x()))
        if index is None:
            self._clear_hover()
        elif index != self._hover_index:
            points = self._drawable_points()
            self._hover_index = index
            text = self._point_tooltip(points[index])
            self.setToolTip(text)
            QToolTip.showText(
                self.mapToGlobal(event.position().toPoint()),
                text,
                self,
            )
        event.accept()

    def leaveEvent(self, event: Any) -> None:  # noqa: N802 - Qt override
        self._clear_hover()
        super().leaveEvent(event)

    @staticmethod
    def _resolve_mode(points: Sequence[StockPricePointDTO]) -> str:
        """只有每一列都有 OHLC 才進入 K 線模式，不補造缺失欄位。"""

        complete_ohlc = bool(points) and all(
            point.open_price is not None
            and point.high_price is not None
            and point.low_price is not None
            and point.close_price is not None
            for point in points
        )
        if not complete_ohlc:
            return "close"
        if all(point.volume is not None for point in points):
            return "ohlc_volume"
        return "ohlc"

    @property
    def display_mode(self) -> str:
        """供 Qt focused test 與無障礙檢查讀取目前圖表型態。"""

        return self._mode

    def paintEvent(self, event: Any) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.fillRect(
                self.rect(), QBrush(QColor(MIDNIGHT_ANALYST.surface_1))
            )
            points = self._drawable_points()
            if not points:
                painter.setPen(QPen(QColor(MIDNIGHT_ANALYST.text_muted)))
                painter.drawText(self.rect(), Qt.AlignCenter, "無價格資料")
                return

            left, right = self._plot_x_bounds()
            top = 25
            volume_enabled = self._mode == "ohlc_volume"
            volume_top = max(top + 70, self.height() - 48)
            bottom = max(top + 50, volume_top - 12 if volume_enabled else self.height() - 32)
            if self._mode in {"ohlc", "ohlc_volume"}:
                values = tuple(
                    value
                    for point in points
                    for value in (point.high_price, point.low_price)
                    if value is not None
                )
            else:
                values = tuple(
                    point.close_price
                    for point in points
                    if point.close_price is not None
                )
            low = min(values)
            high = max(values)
            span = high - low
            if span == 0:
                span = Decimal("1")

            painter.setPen(QPen(QColor(MIDNIGHT_ANALYST.border)))
            painter.drawLine(left, bottom, right, bottom)
            painter.drawLine(left, top, left, bottom)
            painter.setPen(QPen(QColor(MIDNIGHT_ANALYST.text_secondary)))
            painter.drawText(
                6,
                top + 4,
                (
                    "K 線（TWD）"
                    if self._mode in {"ohlc", "ohlc_volume"}
                    else "收盤價（TWD）"
                ),
            )
            painter.drawText(left, self.height() - 8, points[0].data_date)
            last_date = points[-1].data_date
            painter.drawText(max(left, right - 88), self.height() - 8, last_date)
            painter.drawText(6, top + 22, _decimal_text(high))
            painter.drawText(6, bottom - 5, _decimal_text(low))

            denominator = max(1, len(points) - 1)
            if self._mode in {"ohlc", "ohlc_volume"}:
                body_width = max(2, min(10, (right - left) // max(1, len(points) * 2)))
                for index, point in enumerate(points):
                    assert (
                        point.open_price is not None
                        and point.high_price is not None
                        and point.low_price is not None
                        and point.close_price is not None
                    )
                    x = left + int(
                        Decimal(right - left) * Decimal(index) / Decimal(denominator)
                    )
                    y_high = bottom - int(
                        Decimal(bottom - top) * (point.high_price - low) / span
                    )
                    y_low = bottom - int(
                        Decimal(bottom - top) * (point.low_price - low) / span
                    )
                    y_open = bottom - int(
                        Decimal(bottom - top) * (point.open_price - low) / span
                    )
                    y_close = bottom - int(
                        Decimal(bottom - top) * (point.close_price - low) / span
                    )
                    rising = point.close_price >= point.open_price
                    color = (
                        MIDNIGHT_ANALYST.data_positive
                        if rising
                        else MIDNIGHT_ANALYST.data_negative
                    )
                    pen = QPen(QColor(color))
                    pen.setWidth(1)
                    painter.setPen(pen)
                    painter.drawLine(x, y_high, x, y_low)
                    body_top = min(y_open, y_close)
                    body_height = max(1, abs(y_close - y_open))
                    painter.fillRect(
                        x - body_width // 2,
                        body_top,
                        body_width,
                        body_height,
                        QBrush(QColor(color)),
                    )
                if volume_enabled:
                    volumes = tuple(
                        int(point.volume or 0) for point in points
                    )
                    max_volume = max(volumes, default=0)
                    volume_base = max(volume_top + 1, self.height() - 27)
                    volume_area_top = volume_top + 4
                    volume_area_height = max(1, volume_base - volume_area_top)
                    painter.setPen(QPen(QColor(MIDNIGHT_ANALYST.border)))
                    painter.drawLine(left, volume_top, right, volume_top)
                    painter.setPen(QPen(QColor(MIDNIGHT_ANALYST.text_secondary)))
                    painter.drawText(6, volume_top + 14, "成交量")
                    for index, volume in enumerate(volumes):
                        x = left + int(
                            Decimal(right - left) * Decimal(index) / Decimal(denominator)
                        )
                        bar_height = (
                            int(
                                Decimal(volume_area_height)
                                * Decimal(volume)
                                / Decimal(max_volume)
                            )
                            if max_volume
                            else 0
                        )
                        color = (
                            MIDNIGHT_ANALYST.data_positive
                            if points[index].close_price is not None
                            and points[index].open_price is not None
                            and points[index].close_price >= points[index].open_price
                            else MIDNIGHT_ANALYST.data_negative
                        )
                        painter.fillRect(
                            x - body_width // 2,
                            volume_base - bar_height,
                            body_width,
                            max(1, bar_height),
                            QBrush(QColor(color)),
                        )
            else:
                path_points: list[QPoint] = []
                for index, point in enumerate(points):
                    assert point.close_price is not None
                    x = left + int(
                        Decimal(right - left) * Decimal(index) / Decimal(denominator)
                    )
                    y = bottom - int(
                        Decimal(bottom - top) * (point.close_price - low) / span
                    )
                    path_points.append(QPoint(x, y))
                line_pen = QPen(QColor(MIDNIGHT_ANALYST.accent))
                line_pen.setWidth(2)
                painter.setPen(line_pen)
                for first, second in zip(path_points, path_points[1:]):
                    painter.drawLine(first, second)
                painter.setBrush(QBrush(QColor(MIDNIGHT_ANALYST.accent)))
                painter.setPen(QPen(QColor(MIDNIGHT_ANALYST.accent)))
                painter.drawEllipse(path_points[-1], 3, 3)
        finally:
            if painter.isActive():
                painter.end()


class StockResearchReportView(QWidget):
    """報告內容本體，可被非模態 QDialog 或測試直接使用。"""

    reportLoaded = Signal(object)
    reportFailed = Signal(str)
    activeStockChanged = Signal(str)
    activeContextChanged = Signal(object)
    returnRequested = Signal()
    readyToClose = Signal()

    def __init__(
        self,
        service: StockResearchReportReadService,
        context: ResearchStockContextDTO | None = None,
        *,
        stock_codes: Sequence[str] = (),
        parent: QWidget | None = None,
        presentation_service: DecisionPresentationService | None = None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.context = context
        self.presentation_service = presentation_service or DecisionPresentationService()
        self.stock_codes = tuple(str(code).strip() for code in stock_codes if str(code).strip())
        self._request_id = 0
        self._active_code = ""
        self._active_worker: TaskWorker | None = None
        self._workers: set[TaskWorker] = set()
        self._closing = False
        self._loaded_report: StockResearchReportDTO | None = None
        self._rendered_report_tabs: set[str] = set()
        self._setup_ui()
        if context is not None and context.stock_code:
            self.set_context(context)

    def minimumSizeHint(self) -> Any:  # noqa: N802 - Qt override
        return QSize(320, 0)

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        search_row = QHBoxLayout()
        self.stock_search = QLineEdit()
        self.stock_search.setObjectName("stockResearchSearch")
        self.stock_search.setPlaceholderText("輸入股票代碼，例如 2330")
        self.stock_search.setMaxLength(12)
        self.stock_search.setAccessibleName("搜尋個股代碼")
        self.stock_search.setToolTip("輸入代碼後按 Enter 或按「載入個股報告」。")
        self.stock_search.returnPressed.connect(self._load_from_search)
        search_row.addWidget(self.stock_search, 1)

        self.load_button = QPushButton("載入個股報告")
        self.load_button.setProperty("variant", "primary")
        self.load_button.setAccessibleName("載入個股研究報告")
        self.load_button.clicked.connect(self._load_from_search)
        search_row.addWidget(self.load_button)
        self.reload_button = QPushButton("重新載入")
        self.reload_button.setAccessibleName("重新讀取目前個股報告")
        self.reload_button.clicked.connect(self._reload)
        search_row.addWidget(self.reload_button)
        root.addLayout(search_row)

        navigation_row = QHBoxLayout()
        self.previous_button = QPushButton("上一檔")
        self.previous_button.setAccessibleName("載入上一檔個股")
        self.previous_button.setToolTip("在來源清單代碼中載入上一檔；沒有清單時停用。")
        self.previous_button.clicked.connect(lambda: self._step_stock(-1))
        navigation_row.addWidget(self.previous_button)
        self.next_button = QPushButton("下一檔")
        self.next_button.setAccessibleName("載入下一檔個股")
        self.next_button.setToolTip("在來源清單代碼中載入下一檔；沒有清單時停用。")
        self.next_button.clicked.connect(lambda: self._step_stock(1))
        navigation_row.addWidget(self.next_button)
        self.return_button = QPushButton("返回來源清單")
        self.return_button.setAccessibleName("返回原持倉或觀察清單")
        self.return_button.setToolTip("關閉報告並回到原清單；原篩選與選取由來源頁保留。")
        self.return_button.clicked.connect(self._return_to_source)
        navigation_row.addWidget(self.return_button)
        navigation_row.addStretch()
        root.addLayout(navigation_row)

        self.identity_label = QLabel("尚未選取股票")
        identity_font = QFont()
        identity_font.setBold(True)
        identity_font.setPointSize(14)
        self.identity_label.setFont(identity_font)
        self.identity_label.setAccessibleName("個股識別")
        root.addWidget(self.identity_label)

        self.context_path_label = QLabel("研究路徑：" + format_research_workflow_path())
        self.context_path_label.setWordWrap(True)
        self.context_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.context_path_label.setAccessibleName("個股研究來源脈絡")
        self.context_path_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary}; font-size: 11px;"
        )
        root.addWidget(self.context_path_label)

        status_row = QHBoxLayout()
        self.status_badge = StatusBadge("尚未載入", "info")
        self.status_badge.setObjectName("stockResearchStatusBadge")
        self.status_badge.setAccessibleName("報告讀取狀態")
        status_row.addWidget(self.status_badge)
        self.status_label = QLabel("選取股票後載入既有研究來源。")
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        status_row.addWidget(self.status_label, 1)
        root.addLayout(status_row)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("stockResearchTabs")
        self.tabs.setDocumentMode(True)
        self.tabs.currentChanged.connect(self._on_report_tab_changed)
        root.addWidget(self.tabs, 1)
        self._page_layouts: dict[str, QVBoxLayout] = {}
        self._create_page("summary", "摘要")
        self._create_page("price", "價格／技術")
        self._create_page("fundamental", "基本面／營收財報")
        self._create_page("flows", "籌碼／產業事件")
        self._create_page("position", "持倉／Health／Exit")
        self._create_page("decision", "Rule／ML／歷史")

        self._summary_values: dict[str, QLabel] = {}
        self._build_summary_shell()
        self._render_context_path()
        QWidget.setTabOrder(self.stock_search, self.load_button)
        QWidget.setTabOrder(self.load_button, self.reload_button)
        QWidget.setTabOrder(self.reload_button, self.previous_button)
        QWidget.setTabOrder(self.previous_button, self.next_button)
        QWidget.setTabOrder(self.next_button, self.return_button)
        QWidget.setTabOrder(self.return_button, self.tabs)
        self._set_navigation_state()

    def _create_page(self, page_id: str, title: str) -> None:
        inner = QWidget()
        inner.setObjectName(f"stockResearchPage_{page_id}")
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(10)
        set_scroll_content_constraints(inner, horizontal_scroll=True)
        layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setMinimumSize(0, 0)
        scroll.setObjectName(f"stockResearchScroll_{page_id}")
        scroll.setWidget(inner)
        scroll.setAccessibleName(f"{title}內容")
        self.tabs.addTab(scroll, title)
        self._page_layouts[page_id] = layout

    def _build_summary_shell(self) -> None:
        layout = self._page_layouts["summary"]
        self._remove_all_content(layout)
        self.summary_focus = V5ResearchSummary("第一眼先看五個問題")
        self.summary_focus.setAccessibleName("個股研究日常摘要")
        self.summary_focus.setToolTip(
            "摘要只整理報告 DTO 已提供的證據；完整來源、代碼與歷史請開啟進階內容。"
        )
        layout.addWidget(self.summary_focus)

        self.summary_limitations_panel = self._label_panel(
            "資料缺口（先看）",
            "目前尚未載入。",
            "stockResearchLimitations",
        )
        layout.addWidget(self.summary_limitations_panel)

        self.summary_detail_toggle = QPushButton("顯示進階：逐項證據與欄位")
        self.summary_detail_toggle.setCheckable(True)
        self.summary_detail_toggle.setProperty("variant", "secondary")
        self.summary_detail_toggle.setAccessibleName("顯示個股研究逐項證據")
        self.summary_detail_toggle.setToolTip(
            "展開完整欄位用途與讀取值；不會重新評分或重新讀取資料。"
        )
        self.summary_detail_toggle.toggled.connect(self._toggle_summary_details)
        layout.addWidget(self.summary_detail_toggle)

        self.summary_detail_group = QGroupBox("進階：逐項證據與欄位")
        form = QVBoxLayout(self.summary_detail_group)
        form.setSpacing(6)
        for key, label in (
            ("latest_price", "最新可用價格"),
            ("attention", "值得看原因"),
            ("change", "較前變化"),
            ("risk", "主要風險／反證"),
            ("sufficiency", "資料是否足夠"),
            ("freshness", "資料更新狀態"),
            ("advice", "現有建議"),
            ("next_step", "下一步"),
        ):
            value = QLabel("—")
            value.setObjectName(f"stockResearch_{key}")
            value.setWordWrap(True)
            value.setTextInteractionFlags(
                Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
            )
            form.addWidget(QLabel(label))
            form.addWidget(value)
            self._summary_values[key] = value
        detail_limitations = QGroupBox("完整限制與資料缺口")
        detail_limitations_layout = QVBoxLayout(detail_limitations)
        self.summary_limitations_detail_label = self._wrapped_label("目前尚未載入。")
        self.summary_limitations_detail_label.setObjectName(
            "stockResearchLimitationsDetail"
        )
        detail_limitations_layout.addWidget(self.summary_limitations_detail_label)
        form.addWidget(detail_limitations)
        self.summary_detail_group.setVisible(False)
        layout.addWidget(self.summary_detail_group)
        self.summary_source_toggle = QPushButton("顯示進階：來源與各區塊日期")
        self.summary_source_toggle.setCheckable(True)
        self.summary_source_toggle.setProperty("variant", "secondary")
        self.summary_source_toggle.setAccessibleName("顯示個股研究來源與日期明細")
        self.summary_source_toggle.setToolTip(
            "展開來源、品質、資料日、可得時間與版本；不會重新讀取報告。"
        )
        self.summary_source_toggle.toggled.connect(self._toggle_summary_sources)
        layout.addWidget(self.summary_source_toggle)
        self.summary_source_group = QGroupBox("進階：來源與各區塊日期")
        source_layout = QVBoxLayout(self.summary_source_group)
        self.summary_source_trace_label = self._wrapped_label(
            "完整來源 trace：尚未選取股票。"
        )
        self.summary_source_trace_label.setObjectName("stockResearchSourceTrace")
        self.summary_source_trace_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary}; "
            f"background: {MIDNIGHT_ANALYST.surface_1}; "
            f"border: 1px solid {MIDNIGHT_ANALYST.border}; padding: 6px;"
        )
        self.summary_source_trace_label.setAccessibleName("個股研究完整來源 trace")
        source_layout.addWidget(self.summary_source_trace_label)
        self.sources_table = QTableView()
        apply_financial_table_style(self.sources_table)
        self.sources_table.setAccessibleName("個股研究報告來源表")
        self.sources_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.sources_table.setFocusPolicy(Qt.StrongFocus)
        self.sources_table.setTabKeyNavigation(True)
        self.sources_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.sources_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.sources_table.verticalHeader().setDefaultSectionSize(28)
        self.sources_table.verticalHeader().setMinimumSectionSize(28)
        ensure_visible_rows(self.sources_table, 5)
        source_layout.addWidget(self.sources_table)
        self.summary_source_group.setVisible(False)
        layout.addWidget(self.summary_source_group)
        layout.addStretch()

    def _toggle_summary_details(self, expanded: bool) -> None:
        """展開逐項證據，日常摘要仍維持固定高度。"""

        self.summary_detail_group.setVisible(expanded)
        self.summary_detail_toggle.setText(
            "隱藏進階：逐項證據與欄位"
            if expanded
            else "顯示進階：逐項證據與欄位"
        )

    def _toggle_summary_sources(self, expanded: bool) -> None:
        """切換來源明細；來源 model 已載入時只改變可見性。"""

        self.summary_source_group.setVisible(expanded)
        self.summary_source_toggle.setText(
            "隱藏進階：來源與各區塊日期"
            if expanded
            else "顯示進階：來源與各區塊日期"
        )

    def set_stock_codes(self, stock_codes: Sequence[str]) -> None:
        self.stock_codes = tuple(str(code).strip() for code in stock_codes if str(code).strip())
        self._set_navigation_state()

    def set_context(self, context: ResearchStockContextDTO) -> None:
        self.context = context
        self.stock_search.setText(context.stock_code)
        self._render_context_path()
        self._load_stock(context.stock_code)

    def _render_context_path(self) -> None:
        """日常只留必要脈絡，完整 identity 保留在來源進階與 tooltip。"""

        context = self.context
        if context is None:
            visible = "來源：未標示｜決策日：未知｜資料日：未知｜沒有可返回來源"
            full_trace = (
                "研究路徑：" + format_research_workflow_path() + "\n" + visible
            )
            self.context_path_label.setText(visible)
            self.context_path_label.setToolTip(full_trace)
            self.context_path_label.setAccessibleDescription(full_trace)
            self.summary_source_trace_label.setText("完整來源 trace：\n" + full_trace)
            return
        source = context.source_label or context.source_id or "未標示"
        return_text = "可返回來源" if context.has_source else "沒有可返回來源"
        visible = (
            f"來源：{source}｜決策日：{context.decision_date or '未知'}｜"
            f"資料日：{context.data_date or '未知'}｜{return_text}"
        )
        full_trace = _context_trace_text(context, source=source, return_text=return_text)
        self.context_path_label.setText(visible)
        self.context_path_label.setToolTip(full_trace)
        self.context_path_label.setAccessibleDescription(full_trace)
        self.summary_source_trace_label.setText("完整來源 trace：\n" + full_trace)

    def _load_from_search(self) -> None:
        self._load_stock(self.stock_search.text())

    def _reload(self) -> None:
        if self._active_code:
            self._load_stock(self._active_code)
        else:
            self._load_from_search()

    def _step_stock(self, step: int) -> None:
        if not self.stock_codes:
            return
        current = self._active_code or self.stock_search.text().strip()
        try:
            index = self.stock_codes.index(current)
        except ValueError:
            index = 0 if step > 0 else len(self.stock_codes) - 1
        next_index = (index + step) % len(self.stock_codes)
        self._load_stock(self.stock_codes[next_index])

    def _load_stock(self, value: object) -> None:
        code = str(value or "").strip()
        if not code:
            self._set_status("請輸入股票代碼。", "warning")
            return
        self._request_id += 1
        request_id = self._request_id
        self._active_code = code
        self.stock_search.setText(code)
        self.activeStockChanged.emit(code)
        self._cancel_active_worker()
        self._set_loading_state(code)

        context = self.context
        if context is not None and context.stock_code.strip() != code:
            # 來源清單切到另一檔時保留 result/source lineage，但不能把原股票
            # 名稱／身份快取帶到新代碼；service 會再以新代碼的實際資料辨識名稱。
            context = replace(context, stock_code=code, stock_name="")
            self.context = context
            self._render_context_path()
        self.activeContextChanged.emit(context)

        def task(cancel_callback=None) -> StockResearchReportDTO:
            return self.service.read_report(
                code,
                context=context,
                cancel_callback=cancel_callback,
            )

        worker = TaskWorker(task)
        self._workers.add(worker)
        self._active_worker = worker
        worker.started.connect(
            lambda rid=request_id, requested_code=code: self._on_report_started(
                rid, requested_code
            )
        )
        worker.finished.connect(
            lambda report, rid=request_id, requested_code=code: self._on_report_loaded(
                rid, requested_code, report
            )
        )
        worker.error.connect(
            lambda error, rid=request_id, requested_code=code: self._on_report_error(
                rid, requested_code, error
            )
        )
        worker.cancelled.connect(
            lambda rid=request_id, requested_code=code: self._on_report_cancelled(
                rid, requested_code
            )
        )
        worker.native_thread_finished.connect(lambda current=worker: self._worker_finished(current))
        worker.start()

    def _cancel_active_worker(self) -> None:
        worker = self._active_worker
        if worker is not None and worker.isRunning():
            worker.cancel(cooperative=True, wait=False)

    def request_close(self) -> bool:
        """取消目前 worker；回傳 True 表示現在可安全關閉。"""

        self._closing = True
        self._request_id += 1
        worker = self._active_worker
        active_workers = [item for item in self._workers if item.isRunning()]
        if worker is not None and worker.isRunning() and worker not in active_workers:
            active_workers.append(worker)
        if active_workers:
            for current in active_workers:
                current.cancel(cooperative=True, wait=False)
            self._set_status("正在安全取消報告讀取…", "warning")
            return False
        return True

    def is_busy(self) -> bool:
        return any(worker.isRunning() for worker in self._workers)

    def closeEvent(self, event: Any) -> None:  # noqa: N802 - Qt override
        if not self.request_close():
            event.ignore()
            return
        super().closeEvent(event)

    def _worker_finished(self, worker: TaskWorker) -> None:
        self._workers.discard(worker)
        if self._active_worker is worker:
            self._active_worker = None
        # 報告結果訊號可能早於 native thread 完成送達；依實際 worker 集合
        # 同步導覽狀態，讓剛完成清理的載入仍可安全返回來源。
        self._set_navigation_state()
        worker.deleteLater()
        if self._closing and not self.is_busy():
            self.readyToClose.emit()

    def _on_report_started(self, request_id: int, code: str) -> None:
        """忽略切股後才送達的舊 worker started 訊號。"""

        if request_id != self._request_id or code != self._active_code:
            return
        self._set_status("背景讀取中…", "info")

    def _on_report_loaded(
        self,
        request_id: int,
        code: str,
        report: object,
    ) -> None:
        if request_id != self._request_id or code != self._active_code:
            return
        if not isinstance(report, StockResearchReportDTO):
            self._on_report_error(request_id, code, "service returned an invalid report DTO")
            return
        self._render_report(report)
        self._set_status("報告已載入；內容只讀取既有來源。", "observed")
        self.reportLoaded.emit(report)

    def _on_report_error(self, request_id: int, code: str, error: object) -> None:
        if request_id != self._request_id or code != self._active_code:
            return
        message = str(error).splitlines()[0].strip() or "未知讀取錯誤"
        previous_report = self._loaded_report
        if previous_report is not None and str(previous_report.stock_code).strip() == code:
            self._show_last_good_state(
                previous_report,
                conclusion="重新讀取失敗；畫面仍保留同一檔股票的上次可用資料。",
                reason=f"本次讀取失敗：{message}",
                next_step="確認資料來源狀態後按「重新載入」再試一次。",
            )
        else:
            self._show_unavailable_state(
                code,
                conclusion="目前沒有可閱讀的個股報告。",
                reason=f"本次讀取失敗：{message}",
                next_step="確認資料來源狀態後重新載入，或返回來源清單。",
            )
        self._set_status(f"報告讀取失敗：{message}", "error")
        self.reportFailed.emit(message)

    def _on_report_cancelled(self, request_id: int, code: str) -> None:
        if request_id == self._request_id and code == self._active_code and not self._closing:
            previous_report = self._loaded_report
            if previous_report is not None and str(previous_report.stock_code).strip() == code:
                self._show_last_good_state(
                    previous_report,
                    conclusion="讀取已取消；畫面仍保留同一檔股票的上次可用資料。",
                    reason="本次讀取未完成，未以不完整內容覆蓋上次資料。",
                    next_step="需要最新內容時按「重新載入」再試一次。",
                )
            else:
                self._show_unavailable_state(
                    code,
                    conclusion="讀取已取消，尚無可閱讀的個股報告。",
                    reason="本次讀取未完成。",
                    next_step="按「重新載入」再試一次，或返回來源清單。",
                )
            self._set_status("報告讀取已取消。", "warning")

    def _set_loading_state(self, code: str) -> None:
        previous_report = self._loaded_report
        if previous_report is not None and str(previous_report.stock_code).strip() == code:
            self._show_last_good_state(
                previous_report,
                conclusion="重新載入中；以下內容是同一檔股票的上次可用資料。",
                reason="背景讀取尚未完成，畫面不會把新股票或半成品資料混入目前報告。",
                next_step="等待載入完成；若取消，仍保留這筆上次可用資料。",
            )
        else:
            self._clear_loaded_report()
            self._show_unavailable_state(
                code,
                conclusion="報告載入中，尚不能形成判讀。",
                reason="資料仍在背景讀取。",
                next_step="等待載入完成；若取消，保持目前股票與來源脈絡。",
            )
        self._set_status("正在背景讀取有限研究資料…", "info")
        self._set_navigation_state()

    def _clear_loaded_report(self) -> None:
        """跨股票切換時清掉可見舊頁，避免新代碼下殘留舊 DTO。"""

        self._loaded_report = None
        self._rendered_report_tabs = set()
        for value in self._summary_values.values():
            value.setText("尚未載入。")
        self.summary_detail_toggle.setChecked(False)
        self.summary_source_toggle.setChecked(False)
        self.sources_table.setModel(None)
        self.summary_limitations_detail_label.setText("目前尚未載入。")
        self._find_widget("stockResearchLimitations").setText("目前尚未載入。")
        for page_id in ("price", "fundamental", "flows", "position", "decision"):
            layout = self._reset_page(page_id)
            layout.addWidget(self._wrapped_label("尚未載入此股票的報告內容。"))
            layout.addStretch()

    def _show_unavailable_state(
        self,
        code: str,
        *,
        conclusion: str,
        reason: str,
        next_step: str,
    ) -> None:
        self.identity_label.setText(f"{code}｜尚無可用報告")
        self.summary_focus.set_summary(
            conclusion=conclusion,
            reasons=(reason,),
            next_step=next_step,
        )
        self.summary_limitations_detail_label.setText(reason)
        self._find_widget("stockResearchLimitations").setText(reason)

    def _show_last_good_state(
        self,
        report: StockResearchReportDTO,
        *,
        conclusion: str,
        reason: str,
        next_step: str,
    ) -> None:
        data_date = _report_data_date(report)
        identity = (
            f"{report.stock_code} {report.stock_name or '未提供名稱'}｜{report.market}"
            f"｜上次可用資料 {data_date}"
        )
        if report.industry:
            identity += f"｜{report.industry}"
        self.identity_label.setText(identity)
        self.summary_focus.set_summary(
            conclusion=conclusion,
            reasons=(f"上次可用資料：{data_date}", reason),
            next_step=next_step,
            evidence=_report_evidence_text(report),
            change=_price_change_text(report.price_points),
            risk=_join_or_missing(
                report.key_risks,
                "目前沒有可呈現的風險／反證 row；不代表風險不存在。",
            ),
            sufficiency=_report_sufficiency_text(report),
            reasons_title="目前狀態",
        )

    def _set_status(self, text: str, quality: str) -> None:
        self.status_label.setText(text)
        self.status_badge.setText(_quality_label(quality))
        self.status_badge.set_quality(_quality_tone(quality))
        self.status_badge.setAccessibleDescription(f"報告狀態：{text}")

    def _set_navigation_state(self) -> None:
        has_codes = bool(self.stock_codes)
        self.previous_button.setEnabled(has_codes)
        self.next_button.setEnabled(has_codes)
        self.load_button.setEnabled(not self._closing)
        self.reload_button.setEnabled(bool(self._active_code) and not self._closing)
        # 返回來源本身就是取消載入的安全路徑；關閉 dialog 時由
        # request_close() 合作式取消 worker，不應因 native thread／queued
        # signal 的短暫競態讓使用者失去返回按鈕。
        self.return_button.setEnabled(not self._closing)
        self.return_button.setVisible(bool(self.context and self.context.has_source))

    def _render_report(self, report: StockResearchReportDTO) -> None:
        self._loaded_report = report
        self._rendered_report_tabs = {"summary"}
        self.identity_label.setText(
            f"{report.stock_code} {report.stock_name or '未提供名稱'}｜{report.market}"
            + (f"｜{report.industry}" if report.industry else "")
        )
        self._summary_values["latest_price"].setText(_latest_price_text(report.price_points))
        self._summary_values["attention"].setText(
            _join_or_missing(
                report.attention_reasons,
                "目前沒有足夠資料支持額外關注理由。",
            )
        )
        self._summary_values["change"].setText(_price_change_text(report.price_points))
        self._summary_values["risk"].setText(
            _join_or_missing(
                report.key_risks,
                "目前沒有可呈現的風險／反證 row；不代表風險不存在。",
            )
        )
        self._summary_values["sufficiency"].setText(_report_sufficiency_text(report))
        self._summary_values["freshness"].setText(_freshness_text(report))
        self._summary_values["advice"].setText(_advice_summary(report.advice))
        next_step = _report_next_step(report)
        self._summary_values["next_step"].setText(next_step)
        summary_reasons = []
        if report.attention_reasons:
            summary_reasons.append(report.attention_reasons[0])
        if report.key_risks:
            summary_reasons.append(report.key_risks[0])
        if not summary_reasons and report.limitations:
            summary_reasons.append(report.limitations[0])
        self.summary_focus.set_summary(
            conclusion=_report_conclusion(report),
            reasons=summary_reasons,
            next_step=next_step,
            evidence=_report_evidence_text(report),
            change=_price_change_text(report.price_points),
            risk=_join_or_missing(
                report.key_risks,
                "目前沒有可呈現的風險／反證 row；不代表風險不存在。",
            ),
            sufficiency=_report_sufficiency_text(report),
            reasons_title="重點",
        )
        limitations = _join_or_missing(
            report.limitations,
            "來源未提供其他限制說明。",
        )
        visible_limitations = "；".join(
            item.strip() for item in limitations.split("；")[:2] if item.strip()
        )
        if len(limitations.split("；")) > 2:
            visible_limitations += "；其餘限制請開啟進階內容。"
        self._find_widget("stockResearchLimitations").setText(visible_limitations)
        self.summary_limitations_detail_label.setText(limitations)

        self._render_sources(report)
        self._render_report_tab(self.tabs.currentIndex())
        self._set_navigation_state()

    def _on_report_tab_changed(self, index: int) -> None:
        """只在使用者進入分頁時繪製有限內容，不重讀 service。"""

        self._render_report_tab(index)

    def _render_report_tab(self, index: int) -> None:
        report = self._loaded_report
        page_ids = ("summary", "price", "fundamental", "flows", "position", "decision")
        if report is None or index < 0 or index >= len(page_ids):
            return
        page_id = page_ids[index]
        if page_id in self._rendered_report_tabs:
            return
        if page_id == "price":
            self._render_price(report)
        elif page_id == "fundamental":
            self._render_fundamental(report)
        elif page_id == "flows":
            self._render_flows(report)
        elif page_id == "position":
            self._render_position(report.position)
        elif page_id == "decision":
            self._render_decision(report)
        self._rendered_report_tabs.add(page_id)

    def _render_sources(self, report: StockResearchReportDTO) -> None:
        rows = []
        for source in report.sources:
            rows.append(
                (
                    source.source_label,
                    _quality_label(source.status),
                    _quality_label(source.quality),
                    source.data_as_of or "—",
                    source.available_at or "—",
                    _quality_label(source.freshness),
                    source.version or "—",
                    str(source.row_count),
                    source.frequency or "—",
                    source.expected_period or "—",
                    source.freshness_reason or "—",
                )
            )
        if not rows:
            rows = [("—", "缺資料", "—", "—", "—", "未知", "—", "0", "—", "—", "—")]
        self.sources_table.setModel(
            StockReportTableModel(
                (
                    "來源",
                    "來源狀態",
                    "品質",
                    "資料日",
                    "資料可得時間",
                    "更新狀態",
                    "版本",
                    "筆數",
                    "更新週期",
                    "預期資料期",
                    "更新說明",
                ),
                rows,
                self.sources_table,
            )
        )
        self.sources_table.resizeColumnsToContents()
        ensure_visible_rows(self.sources_table, 5)

    def _render_price(self, report: StockResearchReportDTO) -> None:
        layout = self._reset_page("price")
        layout.addWidget(self._section_heading("價格與成交量", report, "price"))
        chart = StockPriceChartWidget()
        chart.set_points(report.price_points)
        layout.addWidget(chart)
        chart_mode_label = QLabel(
            {
                "ohlc_volume": "圖表型態：完整開高低收 K 線＋成交量；僅使用既有價格資料。",
                "ohlc": "圖表型態：完整開高低收 K 線；成交量資料不足，未繪製量柱。",
                "close": "圖表型態：收盤價走勢；開高低收欄位不完整，未補造 K 線。",
            }[chart.display_mode]
        )
        chart_mode_label.setObjectName("stockResearchPriceChartMode")
        chart_mode_label.setProperty("role", "muted")
        chart_mode_label.setWordWrap(True)
        layout.addWidget(chart_mode_label)
        chart_range_label = QLabel(
            f"{_price_chart_range_text(report.price_points)}；"
            "將游標移到每根 K 線／折線點查看該日日期、開高低收與成交量。"
            if report.price_points
            else "圖表範圍：目前沒有可繪製的價格資料。"
        )
        chart_range_label.setObjectName("stockResearchPriceChartRange")
        chart_range_label.setProperty("role", "muted")
        chart_range_label.setWordWrap(True)
        layout.addWidget(chart_range_label)
        if report.price_points:
            rows = tuple(
                (
                    point.data_date,
                    _decimal_text(point.close_price),
                    _decimal_text(point.change),
                    _integer_text(point.volume),
                    _decimal_text(point.turnover),
                )
                for point in reversed(report.price_points)
            )
            self._add_table(layout, ("日期", "收盤價", "漲跌價差", "成交股數", "成交金額"), rows, 310)
        else:
            layout.addWidget(self._missing_panel("價格資料不足；請從「數據更新」檢查 daily_prices。"))
        if report.technical is not None:
            group = QGroupBox(f"技術指標｜資料日 {report.technical.data_date or '—'}")
            group_layout = QVBoxLayout(group)
            rows = tuple(
                (metric.label, _metric_text(metric), metric.data_as_of or "—", metric.quality)
                for metric in report.technical.indicators
            )
            self._add_table(group_layout, ("指標", "值", "資料日", "品質"), rows, 240)
            if report.technical.limitations:
                group_layout.addWidget(self._wrapped_label(_join_or_missing(report.technical.limitations, "")))
            layout.addWidget(group)
        else:
            layout.addWidget(self._missing_panel("技術指標不足；不以缺欄位推論趨勢。"))
        layout.addStretch()

    def _render_fundamental(self, report: StockResearchReportDTO) -> None:
        layout = self._reset_page("fundamental")
        layout.addWidget(self._section_heading("基本面／營收財報", report, "fundamental"))
        if not report.fundamentals:
            layout.addWidget(self._missing_panel("沒有可用的公告／可得日基本面 row；不補零。"))
            layout.addStretch()
            return
        rows = tuple(
            (
                {"monthly_revenue": "月營收", "statement_item": "財報項目", "valuation": "估值"}.get(item.kind, item.kind),
                item.label,
                item.period or "—",
                item.as_of_date or "—",
                item.announced_date or "—",
                item.available_at or "—",
                _metric_text(item),
                item.quality,
                item.source_version or "—",
            )
            for item in report.fundamentals
        )
        self._add_table(
            layout,
            ("類型", "項目", "期間", "資料日", "公告日", "資料可得時間", "值", "品質", "版本"),
            rows,
            420,
        )
        layout.addWidget(
            self._wrapped_label(
                "目前查閱含已實際觀測的官方快照；歷史日期查詢只使用符合可得日限制的資料。"
                "現況快照沒有原公告日，不作歷史回測證據；各項資料日期可能不同。"
            )
        )
        layout.addStretch()

    def _render_flows(self, report: StockResearchReportDTO) -> None:
        layout = self._reset_page("flows")
        layout.addWidget(self._section_heading("籌碼資料與產業事件", report, "flows"))
        layout.addWidget(
            self._wrapped_label(
                "本頁分開顯示分點、法人、信用、集保與產業／事件。"
                "各區資料日與品質以來源實際提供內容為準；缺資料不補零。"
            )
        )
        if report.flows:
            rows = tuple(
                (
                    flow.data_date,
                    flow.branch_name,
                    _integer_text(flow.buy_shares),
                    _integer_text(flow.sell_shares),
                    _integer_text(flow.net_shares),
                    _decimal_text(flow.net_amount_thousand),
                    flow.trade_type or "—",
                    flow.quality,
                )
                for flow in report.flows
            )
            self._add_table(
                layout,
                ("日期", "分點", "買進股數", "賣出股數", "買賣超股數", "淨額千元", "類型", "品質"),
                rows,
                350,
            )
        else:
            layout.addWidget(self._missing_panel("沒有可用分點 row；請檢查 broker_flows 更新狀態。"))

        layout.addWidget(
            self._render_metric_group(
                "法人資料",
                report.institutional,
                missing_text="目前沒有法人資料；不補零。",
            )
        )
        layout.addWidget(
            self._render_metric_group(
                "信用資料",
                report.credit,
                missing_text="目前沒有信用資料；不補零。",
            )
        )
        layout.addWidget(self._render_shareholding_group(report.shareholding))

        events = QGroupBox("產業／事件證據")
        event_layout = QVBoxLayout(events)
        self._add_event_table(event_layout, report.events)
        layout.addWidget(events)
        layout.addStretch()

    def _render_metric_group(
        self,
        title: str,
        metrics: Sequence[StockMetricDTO],
        *,
        missing_text: str,
    ) -> QGroupBox:
        group = QGroupBox(title)
        group_layout = QVBoxLayout(group)
        if not metrics:
            group_layout.addWidget(self._missing_panel(missing_text))
            return group
        rows = tuple(
            (
                metric.label,
                _ownership_metric_text(metric),
                metric.data_as_of or "—",
                _quality_label(metric.quality),
            )
            for metric in metrics
        )
        tooltips = tuple(_metric_tooltip_row(metric) for metric in metrics)
        self._add_table(
            group_layout,
            ("項目", "值", "資料日", "品質"),
            rows,
            300,
            tooltips=tooltips,
            compact_columns=True,
            numeric_columns=(1,),
        )
        group_layout.addWidget(
            self._wrapped_label("資料可得時間與來源識別請滑過列中內容查看；完整來源仍保留在摘要的來源明細。")
        )
        return group

    def _render_shareholding_group(
        self,
        metrics: Sequence[StockMetricDTO],
    ) -> QGroupBox:
        group = QGroupBox("集保股權分散")
        group_layout = QVBoxLayout(group)
        summary_metrics = tuple(
            metric for metric in metrics if metric.key != "shareholding_tiers"
        )
        if summary_metrics:
            rows = tuple(
                (
                    metric.label,
                    _ownership_metric_text(metric),
                    metric.data_as_of or "—",
                    _quality_label(metric.quality),
                )
                for metric in summary_metrics
            )
            tooltips = tuple(_metric_tooltip_row(metric) for metric in summary_metrics)
            self._add_table(
                group_layout,
                ("摘要項目", "值", "資料日", "品質"),
                rows,
                220,
                tooltips=tooltips,
                compact_columns=True,
                numeric_columns=(1,),
            )
        tier_metric = next(
            (metric for metric in metrics if metric.key == "shareholding_tiers"),
            None,
        )
        if tier_metric is None:
            group_layout.addWidget(self._missing_panel("目前沒有持股級距明細；不補零。"))
            return group

        tier_group = QGroupBox("持股級距明細")
        tier_layout = QVBoxLayout(tier_group)
        tier_layout.addWidget(
            self._wrapped_label(
                "每列顯示級距、人數、持有股數與占集保庫存比例。"
                "滑過資料列可查看來源明細；「—」表示未提供。"
            )
        )
        tier_presentation = build_shareholding_tier_table(tier_metric.value_text)
        if tier_presentation.rows:
            self._add_presentation_table(
                tier_layout,
                ("級距", "人數", "股數", "比例"),
                tier_presentation,
                560,
                object_name="stockResearchShareholdingTiers",
                compact_columns=False,
                numeric_columns=(1, 2, 3),
                max_visible_rows=None,
                balanced_columns=True,
            )
            if tier_presentation.note:
                tier_layout.addWidget(self._wrapped_label(tier_presentation.note))
        else:
            missing = tier_presentation.note or "目前沒有可辨識的持股級距明細。"
            missing_panel = self._missing_panel(missing)
            missing_panel.setToolTip(tier_metric.value_text or "來源未提供原始級距內容。")
            tier_layout.addWidget(missing_panel)
        group_layout.addWidget(tier_group)
        return group

    def _render_position(self, position: StockPositionSnapshotDTO | None) -> None:
        layout = self._reset_page("position")
        layout.addWidget(QLabel("此區只顯示既有 PortfolioService、Health／Exit read contract 的內容。"))
        if position is None:
            layout.addWidget(self._missing_panel("沒有此股票的持倉 row；Health／Exit 不對非持倉股票推導動作。"))
            layout.addStretch()
            return
        group = QGroupBox("持倉成本／損益／曝險")
        group_layout = QVBoxLayout(group)
        rows = (
            ("持倉狀態", "持有中" if position.is_holding else "非持倉"),
            ("持有股數", _decimal_text(position.quantity)),
            ("平均成本", _decimal_text(position.average_cost)),
            ("投入金額", _decimal_text(position.invested_amount)),
            ("最新持倉價格", _decimal_text(position.current_price)),
            ("未實現損益", _decimal_text(position.unrealized_pnl)),
            ("未實現損益%", _percent_text(position.unrealized_pnl_pct)),
            ("曝險", _bp_text(position.exposure_bp)),
            ("來源", position.source_type or position.source_id or "—"),
            ("最後交易日", position.last_trade_date or "—"),
        )
        self._add_table(group_layout, ("欄位", "值"), rows, 300)
        layout.addWidget(group)
        health = QGroupBox(f"Health｜{position.health_label or position.health_status or '資料不足'}")
        health_layout = QVBoxLayout(health)
        health_layout.addWidget(self._wrapped_label(_join_or_missing(position.health_reasons, "沒有 Health 理由。")))
        if position.health_source_trace:
            health_layout.addWidget(self._wrapped_label("Health source trace：" + "；".join(position.health_source_trace)))
        layout.addWidget(health)
        exit_group = QGroupBox(f"Exit｜{position.exit_status or 'unavailable'}")
        exit_layout = QVBoxLayout(exit_group)
        exit_layout.addWidget(self._wrapped_label(_join_or_missing(position.exit_reasons, "目前沒有可用的持倉 Exit 分析；不推導賣出動作。")))
        layout.addWidget(exit_group)
        if position.limitations:
            layout.addWidget(self._missing_panel(_join_or_missing(position.limitations, "")))
        layout.addStretch()

    def _render_decision(self, report: StockResearchReportDTO) -> None:
        layout = self._reset_page("decision")
        advice_group = QGroupBox("Advice（沿用既有 AdviceComposer）")
        advice_layout = QVBoxLayout(advice_group)
        self._render_advice_content(advice_layout, report.advice, report.position)
        layout.addWidget(advice_group)

        rule_group = QGroupBox("Rule 證據")
        rule_layout = QVBoxLayout(rule_group)
        rule_layout.addWidget(self._wrapped_label(_join_or_missing(report.rule_reasons, "目前沒有可追溯 Rule reason。")))
        layout.addWidget(rule_group)

        ml_group = QGroupBox("ML（有合格結果才顯示）")
        ml_layout = QVBoxLayout(ml_group)
        ml = report.ml
        if ml.status not in {"unavailable", "missing"} and ml.model_version and ml.dataset_version:
            ml_layout.addWidget(self._wrapped_label(
                f"狀態：{ml.status}\n模型版本：{ml.model_version}\nDataset：{ml.dataset_version}\n"
                f"推論時間：{ml.inference_at or '—'}\nLane：{ml.research_or_formal or '—'}"
            ))
            ml_layout.addWidget(self._wrapped_label("可解釋輸出：" + _join_or_missing(ml.explanations, "未提供")))
        else:
            ml_layout.addWidget(self._missing_panel(_join_or_missing(ml.limitations, "目前沒有可用的個股 ML 分析。")))
        if ml.limitations:
            ml_layout.addWidget(self._wrapped_label("ML 限制：" + "；".join(ml.limitations)))
        layout.addWidget(ml_group)

        history_group = QGroupBox("歷史建議與後續結果")
        history_layout = QVBoxLayout(history_group)
        self._add_event_table(history_layout, report.events)
        layout.addWidget(history_group)
        layout.addWidget(self._wrapped_label("研究報告不觸發自動下單；持倉修改仍沿既有確認與記錄流程。"))
        layout.addStretch()

    def _render_advice_content(
        self,
        layout: QVBoxLayout,
        advice: StockAdviceSnapshotDTO,
        position: StockPositionSnapshotDTO | None = None,
    ) -> None:
        presentation = self.presentation_service.from_report_parts(advice, position)
        if presentation is not None:
            layout.addWidget(
                self._wrapped_label(
                    "共用呈現契約（唯讀）\n" + format_decision_presentation(presentation)
                )
            )
        if advice.recommendation is None:
            if advice.saved_analysis is not None:
                saved = advice.saved_analysis
                layout.addWidget(self._wrapped_label(
                    f"保存分析狀態：{saved.status}\n{saved.message or '沒有可顯示的保存分析。'}"
                ))
            layout.addWidget(self._missing_panel(_join_or_missing(advice.limitations, "目前沒有適用 Advice。")))
            return
        rec = advice.recommendation
        action = _advice_action_label(rec.advice_action.value)
        text = (
            f"適用狀態：{action}\n"
            f"分類：{rec.classification.value}\n"
            f"資料品質：{rec.data_quality or '—'}\n"
            f"決策日：{rec.decision_date or '—'}｜資料日：{rec.data_as_of_date or '—'}\n"
            f"適用期間：{rec.holding_horizon or '未提供'}"
        )
        layout.addWidget(self._wrapped_label(text))
        for title, values in (
            ("觸發條件／進場論點", (rec.entry_thesis,) if rec.entry_thesis else ()),
            ("支持理由", rec.why_reasons),
            ("反對證據／政策限制", rec.why_not_reasons),
            ("失效條件", rec.invalidation_conditions),
            ("主要風險", rec.risk_reasons),
            ("警告／拒絕理由", (*rec.warnings, *rec.refusal_reasons)),
        ):
            if values:
                layout.addWidget(self._wrapped_label(f"{title}：" + "；".join(values)))
        if rec.source_trace:
            layout.addWidget(self._wrapped_label("來源追溯：" + "；".join(rec.source_trace)))
        if advice.rule_reasons:
            layout.addWidget(self._wrapped_label("Rule reasons：" + "；".join(advice.rule_reasons)))
        if advice.ml_reasons:
            layout.addWidget(self._wrapped_label("ML reasons（分開呈現）：" + "；".join(advice.ml_reasons)))
        layout.addWidget(self._wrapped_label(
            f"Rule／ML 關係：{advice.agreement}\n"
            "此 Advice 不代表機率、目標價、勝率或自動交易指令。"
        ))
        if advice.portfolio is not None:
            portfolio = advice.portfolio
            layout.addWidget(self._wrapped_label(
                "持倉風控限制：已有既有 Portfolio Advice snapshot；"
                f"目前權重 {_bp_text(portfolio.current_weight_bp)}、"
                f"可執行權重 {_bp_text(portfolio.executable_weight_bp)}，詳見持倉分頁。"
            ))
        elif position is None or not position.is_holding:
            layout.addWidget(self._wrapped_label(
                "持倉風控限制：目前沒有持有中的持倉 row，未套用持倉限制。"
            ))
        else:
            layout.addWidget(self._wrapped_label(
                "持倉風控限制：已有持倉，但本次沒有既有 Portfolio Advice snapshot；"
                "請依持倉／Health／Exit 既有 read contract 判讀，不由報告 UI 推導。"
            ))

    def _section_heading(
        self,
        title: str,
        report: StockResearchReportDTO,
        section_id: str,
    ) -> QWidget:
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background: {MIDNIGHT_ANALYST.surface_2}; border: 1px solid {MIDNIGHT_ANALYST.border}; "
            f"border-left: 4px solid {MIDNIGHT_ANALYST.accent}; border-radius: {MIDNIGHT_ANALYST.radius_panel}px; }}"
        )
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 7, 10, 7)
        label = QLabel(title)
        label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_primary}; font-weight: 700;")
        layout.addWidget(label)
        section = next((item for item in report.sections if item.section_id == section_id), None)
        status = section.status if section is not None else "missing"
        badge = StatusBadge(_quality_label(status), _quality_tone(status))
        badge.setAccessibleDescription(
            f"{title}狀態：{_quality_label(status)}；資料日：{section.data_as_of if section else '—'}；"
            f"資料可得時間：{section.available_at if section else '—'}"
        )
        layout.addStretch()
        layout.addWidget(badge)
        data_as_of = section.data_as_of if section and section.data_as_of else "—"
        available_at = section.available_at if section and section.available_at else "—"
        date_label = QLabel(f"資料日：{data_as_of}\n可得時間：{available_at}")
        date_label.setWordWrap(True)
        date_label.setToolTip(
            f"資料日：{data_as_of}\n資料可得時間：{available_at}"
        )
        date_label.setAccessibleName(f"{title}資料日期與可得時間")
        date_label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_secondary};")
        layout.addWidget(date_label)
        return frame

    def _reset_page(self, page_id: str) -> QVBoxLayout:
        layout = self._page_layouts[page_id]
        self._remove_all_content(layout)
        return layout

    @staticmethod
    def _remove_all_content(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            child = item.layout()
            if child is not None:
                StockResearchReportView._remove_all_content(child)

    def _add_table(
        self,
        layout: QVBoxLayout,
        columns: Sequence[str],
        rows: Sequence[Sequence[str]],
        maximum_height: int,
        *,
        tooltips: Sequence[Sequence[str]] | None = None,
        object_name: str = "",
        compact_columns: bool = False,
        numeric_columns: Sequence[int] = (),
        max_visible_rows: int | None = 15,
        balanced_columns: bool = False,
    ) -> QTableView:
        table = QTableView()
        apply_financial_table_style(table)
        table.setModel(
            StockReportTableModel(
                columns,
                rows,
                table,
                tooltips=tooltips,
                numeric_columns=numeric_columns,
            )
        )
        if object_name:
            table.setObjectName(object_name)
        table.setWordWrap(False)
        preferred_visible_rows = (
            len(rows) if max_visible_rows is None else min(len(rows), max_visible_rows)
        )
        header_height = max(30, table.horizontalHeader().sizeHint().height())
        row_height = max(28, table.verticalHeader().defaultSectionSize())
        horizontal_scroll_height = (
            table.horizontalScrollBar().sizeHint().height() if not compact_columns else 0
        )
        preferred_height = max(
            72,
            header_height
            + max(5, preferred_visible_rows) * row_height
            + 2 * table.frameWidth()
            + horizontal_scroll_height
            + 4,
        )
        # 舊參數保留作為預設展示高度提示；它不再限制可見列或縮放高度。
        table.setMinimumHeight(min(maximum_height, preferred_height))
        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setFocusPolicy(Qt.StrongFocus)
        table.setTabKeyNavigation(True)
        table.verticalHeader().setDefaultSectionSize(28)
        table.verticalHeader().setMinimumSectionSize(28)
        table.setAccessibleDescription("可使用鍵盤方向鍵選取；完整欄位文字可由 tooltip 讀取。")
        table.resizeColumnsToContents()
        if compact_columns:
            header = table.horizontalHeader()
            for column in range(len(columns)):
                header.setSectionResizeMode(column, QHeaderView.Stretch)
            table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        elif balanced_columns:
            header = table.horizontalHeader()
            header.setStretchLastSection(False)
            header.setMinimumSectionSize(105)
            for column in range(len(columns)):
                header.setSectionResizeMode(column, QHeaderView.Stretch)
            if columns:
                header.setSectionResizeMode(0, QHeaderView.Interactive)
                header.resizeSection(0, 165)
            table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        ensure_visible_rows(table, 5)
        layout.addWidget(table)
        return table

    def _add_presentation_table(
        self,
        layout: QVBoxLayout,
        columns: Sequence[str],
        presentation: ResearchTablePresentation,
        maximum_height: int,
        *,
        object_name: str = "",
        compact_columns: bool = True,
        numeric_columns: Sequence[int] = (),
        max_visible_rows: int | None = 15,
        balanced_columns: bool = False,
    ) -> QTableView:
        return self._add_table(
            layout,
            columns,
            presentation.rows,
            maximum_height,
            tooltips=presentation.tooltips,
            object_name=object_name,
            compact_columns=compact_columns,
            numeric_columns=numeric_columns,
            max_visible_rows=max_visible_rows,
            balanced_columns=balanced_columns,
        )

    def _add_event_table(
        self,
        layout: QVBoxLayout,
        events: Sequence[StockEvidenceEventDTO],
    ) -> None:
        if not events:
            layout.addWidget(self._missing_panel("目前沒有可追溯的 Evidence event 或後續 outcome。"))
            return
        presentation = build_stock_research_event_table(events)
        layout.addWidget(
            self._wrapped_label(
                "表格先列日期、事件、品質與摘要；選取一列查看來源、原因、風險與後續結果。"
            )
        )
        table = self._add_presentation_table(
            layout,
            ("日期", "事件", "品質", "摘要"),
            presentation,
            420,
            object_name="stockResearchEvidenceEvents",
        )
        details_label = self._wrapped_label("選取事件查看詳細說明。")
        details_label.setObjectName("stockResearchEvidenceEventDetails")
        details_label.setProperty("role", "muted")
        layout.addWidget(details_label)
        if presentation.details:
            details_label.setText(presentation.details[0])
            selection_model = table.selectionModel()
            if selection_model is not None:
                selection_model.currentChanged.connect(
                    lambda current, _previous, label=details_label, data=presentation.details:
                    label.setText(data[current.row()] if 0 <= current.row() < len(data) else "選取事件查看詳細說明。")
                )
            table.selectRow(0)

    def _label_panel(self, title: str, text: str, object_name: str) -> QWidget:
        group = QGroupBox(title)
        group_layout = QVBoxLayout(group)
        label = self._wrapped_label(text)
        label.setObjectName(object_name)
        group_layout.addWidget(label)
        return group

    def _missing_panel(self, text: str) -> QWidget:
        label = self._wrapped_label(f"資料不足：{text}")
        label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.warning}; background: {MIDNIGHT_ANALYST.surface_2}; "
            f"border: 1px solid {MIDNIGHT_ANALYST.border}; padding: 8px;"
        )
        label.setAccessibleDescription("資料不足；此狀態不等於看多或看空。" + text)
        return label

    @staticmethod
    def _wrapped_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        return label

    def _find_widget(self, object_name: str) -> QLabel:
        widget = self.findChild(QLabel, object_name)
        if widget is None:
            raise RuntimeError(f"missing report widget: {object_name}")
        return widget

    def _return_to_source(self) -> None:
        self.returnRequested.emit()
        parent = self.parentWidget()
        if isinstance(parent, QDialog):
            parent.close()


class StockResearchReportDialog(QDialog):
    """非模態單股報告視窗；關閉前會合作式取消背景讀取。"""

    def __init__(
        self,
        service: StockResearchReportReadService,
        context: ResearchStockContextDTO,
        *,
        stock_codes: Sequence[str] = (),
        journey_service: DecisionOutcomeJourneyService | None = None,
        continuity_controller: DecisionContinuityController | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setModal(False)
        self.setWindowTitle(f"個股研究報告｜{context.stock_code}")
        self.setMinimumSize(360, 280)
        self.resize(1120, 760)
        layout = QVBoxLayout(self)
        self.dialog_tabs = QTabWidget()
        self.dialog_tabs.setObjectName("stockResearchDialogTabs")
        self.dialog_tabs.setDocumentMode(True)
        self.report_view = StockResearchReportView(
            service,
            context,
            stock_codes=stock_codes,
            parent=self,
        )
        self.report_view.activeStockChanged.connect(self._on_report_stock_changed)
        self.report_view.activeContextChanged.connect(self._on_report_context_changed)
        self.dialog_tabs.addTab(self.report_view, "個股研究報告")
        self.journey_view: DecisionOutcomeJourneyWidget | None = None
        if journey_service is not None:
            self.journey_view = DecisionOutcomeJourneyWidget(
                journey_service,
                context,
                continuity_controller=continuity_controller,
                parent=self,
            )
            self.dialog_tabs.addTab(self.journey_view, "決策 → 結果")
        layout.addWidget(self.dialog_tabs)
        self._close_requested = False
        self.report_view.readyToClose.connect(self._maybe_accept_after_close)
        self.report_view.returnRequested.connect(self._begin_close)
        if self.journey_view is not None:
            self.journey_view.readyToClose.connect(self._maybe_accept_after_close)

    def set_context(
        self,
        context: ResearchStockContextDTO,
        *,
        stock_codes: Sequence[str] | None = None,
    ) -> None:
        self.setWindowTitle(f"個股研究報告｜{context.stock_code}")
        if stock_codes is not None:
            self.report_view.set_stock_codes(stock_codes)
        self.report_view.set_context(context)

    def _on_report_stock_changed(self, stock_code: str) -> None:
        """同步報告頁內搜尋／上一檔切換後的外層視窗標題。"""

        code = str(stock_code).strip()
        if code:
            self.setWindowTitle(f"個股研究報告｜{code}")

    def _on_report_context_changed(
        self,
        context: ResearchStockContextDTO | None,
    ) -> None:
        """讓 Journey 重新以 exact result_id + stock_code 驗證候選。"""

        if self.journey_view is not None:
            self.journey_view.set_context(context)

    def closeEvent(self, event: Any) -> None:  # noqa: N802 - Qt override
        self._close_requested = True
        report_ready = self.report_view.request_close()
        journey_ready = (
            True
            if self.journey_view is None
            else self.journey_view.request_close()
        )
        if not report_ready or not journey_ready:
            event.ignore()
            return
        super().closeEvent(event)

    def _begin_close(self) -> None:
        self._close_requested = True
        self.close()

    def _maybe_accept_after_close(self) -> None:
        if self._close_requested and not self.is_busy():
            self.accept()

    def is_busy(self) -> bool:
        return self.report_view.is_busy() or bool(
            self.journey_view is not None and self.journey_view.is_busy()
        )


def _quality_label(value: str) -> str:
    labels = {
        "available": "可用",
        "observed": "已觀測",
        "partial": "部分可用",
        "stale": "過期",
        "fresh": "新鮮",
        "missing": "缺資料",
        "error": "讀取失敗",
        "degraded": "品質降級",
        "estimated": "估計",
        "unavailable": "不可用",
        "unknown": "未知",
        "info": "讀取中",
        "warning": "注意",
    }
    return labels.get(str(value).lower(), str(value) or "未知")


def _quality_tone(value: str) -> str:
    token = str(value).lower()
    if token in {"available", "observed", "fresh"}:
        return "observed"
    if token in {"partial", "stale", "degraded", "estimated", "warning"}:
        return "warning"
    if token in {"missing", "error", "unavailable"}:
        return "missing"
    return "info"


def _decimal_text(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return f"{value:,}"


def _integer_text(value: int | None) -> str:
    return "—" if value is None else f"{value:,}"


def _chart_decimal_text(value: Decimal | None) -> str:
    return _decimal_text(value) if value is not None else "未提供"


def _chart_integer_text(value: int | None) -> str:
    return _integer_text(value) if value is not None else "未提供"


def _price_chart_range_text(points: Sequence[StockPricePointDTO]) -> str:
    if not points:
        return "圖表範圍：目前沒有可繪製的價格資料"
    first_date = str(points[0].data_date or "未提供")
    latest_date = str(points[-1].data_date or "未提供")
    drawable_count = sum(point.close_price is not None for point in points)
    range_label = "圖表範圍" if drawable_count == len(points) else "資料範圍"
    if drawable_count == 0:
        count_text = f"共 {len(points)} 筆原始價格資料，沒有可繪製價格點"
    elif drawable_count == len(points):
        count_text = f"共 {len(points)} 個資料點"
    else:
        count_text = (
            f"共 {len(points)} 筆原始價格資料，圖上可繪製 {drawable_count} 點"
        )
    return (
        f"{range_label}：{first_date} 至 {latest_date}（{count_text}）；"
        f"最新涵蓋日：{latest_date}"
    )


def _percent_text(value: Decimal | None) -> str:
    return "—" if value is None else f"{value * Decimal('100'):+.2f}%"


def _bp_text(value: int | None) -> str:
    return "—" if value is None else f"{value:,} bp"


def _metric_text(metric: StockMetricDTO | StockFundamentalObservationDTO) -> str:
    if metric.value is not None:
        return _decimal_text(metric.value) + (f" {metric.unit}" if metric.unit else "")
    return metric.value_text or "—"


def _ownership_metric_text(metric: StockMetricDTO) -> str:
    """將法人／信用／集保摘要轉成帶語意的值，不改變 DTO 數值。"""

    if metric.value is not None and metric.key.endswith("_bp"):
        return f"{(metric.value / Decimal('100')).quantize(Decimal('0.01'))}%"
    return _metric_text(metric)


def _metric_tooltip_row(metric: StockMetricDTO) -> tuple[str, ...]:
    detail = (
        f"原始項目：{metric.label}\n"
        f"原始 key：{metric.key}\n"
        f"資料可得時間：{metric.available_at or '未提供'}\n"
        f"來源：{metric.source_id or '未提供'}\n"
        f"原始品質：{metric.quality or '未提供'}"
    )
    return (detail, detail, detail, detail)


def _latest_price_text(points: Sequence[StockPricePointDTO]) -> str:
    if not points:
        return "資料不足：沒有不晚於查詢日的價格。"
    point = points[-1]
    return (
        f"{_decimal_text(point.close_price)} TWD｜資料日 {point.data_date}｜"
        f"成交股數 {_integer_text(point.volume)}｜成交金額 {_decimal_text(point.turnover)}"
    )


def _report_data_date(report: StockResearchReportDTO) -> str:
    """取得可對使用者說明的最後資料日，不建立新的資料判斷。"""

    if report.price_points:
        return str(report.price_points[-1].data_date or report.as_of or "未知")
    if report.technical is not None and report.technical.data_date:
        return str(report.technical.data_date)
    for section in report.sections:
        if section.data_as_of:
            return str(section.data_as_of)
    return str(report.as_of or "未知")


def _context_trace_text(
    context: ResearchStockContextDTO,
    *,
    source: str,
    return_text: str,
) -> str:
    """保留跨頁 context 的完整可查 identity，避免日常標籤塞滿 metadata。"""

    return "\n".join(
        (
            f"研究路徑：{format_research_workflow_path()}",
            f"股票：{context.stock_code} {context.stock_name or '未提供名稱'}",
            f"來源：{source}｜來源 ID：{context.source_id or '未知'}｜"
            f"工作區：{context.source_workspace or '未知'}｜"
            f"來源型態：{context.source_kind or '未知'}｜狀態：{return_text}",
            f"決策日：{context.decision_date or '未知'}｜資料日：{context.data_date or '未知'}",
            f"source_snapshot_id：{context.source_snapshot_id or '未知'}｜"
            f"source_snapshot_hash：{context.source_snapshot_hash or '未知'}",
            f"source_version：{context.source_version or '未知'}｜"
            f"mapping_source_id：{context.mapping_source_id or '未知'}｜"
            f"mapping_version：{context.mapping_version or '未知'}｜"
            f"mapping_observed_date：{context.mapping_observed_date or '未知'}",
            f"profile_id：{context.profile_id or '未知'}｜"
            f"profile_version：{context.profile_version or '未知'}",
        )
    )


def _price_change_text(points: Sequence[StockPricePointDTO]) -> str:
    """只使用 DTO 已提供的漲跌欄位，沒有欄位就明示無法比較。"""

    if not points:
        return "沒有價格資料，無法比較。"
    point = points[-1]
    if point.change is None:
        return "漲跌資料或方向不足，無法確認。"
    return f"最新一日漲跌：{point.change:+,} TWD（資料日 {point.data_date}）。"


def _report_evidence_text(report: StockResearchReportDTO) -> str:
    """整理首屏可引用的主要證據與日期，不建立新金融指標。"""

    parts: list[str] = []
    if report.price_points:
        point = report.price_points[-1]
        parts.append(
            f"價格 {point.data_date} 收盤 {_decimal_text(point.close_price)} TWD"
        )
    if report.technical is not None and report.technical.data_date:
        parts.append(f"技術指標 {report.technical.data_date}")
    for item in report.fundamentals:
        date_text = item.as_of_date or item.period
        if date_text:
            parts.append(f"基本面 {date_text}")
            break
    if report.flows and report.flows[0].data_date:
        parts.append(f"籌碼 {report.flows[0].data_date}")
    return "；".join(parts) if parts else "目前沒有可引用的主要資料日期。"


def _report_sufficiency_text(report: StockResearchReportDTO) -> str:
    """依既有 section status 說明覆蓋，不把缺資料補成正常。"""

    if not report.sections:
        return "未知：報告沒有可用的區塊狀態。"
    missing = tuple(
        section.label
        for section in report.sections
        if section.status in {
            ReportSectionStatus.MISSING.value,
            ReportSectionStatus.ERROR.value,
        }
    )
    partial = tuple(
        section.label
        for section in report.sections
        if section.status in {
            ReportSectionStatus.PARTIAL.value,
            ReportSectionStatus.STALE.value,
        }
    )
    if missing:
        return "不足：" + "、".join(missing[:3]) + " 缺資料或讀取失敗。"
    if partial:
        return "部分可用：" + "、".join(partial[:3]) + " 需要核對日期與品質。"
    return "目前主要區塊都有可讀狀態；仍需逐區核對資料日。"


def _report_conclusion(report: StockResearchReportDTO) -> str:
    """挑出既有 evidence 的一句話作結，不生成新投資結論。"""

    if report.attention_reasons:
        return f"值得看：{report.attention_reasons[0]}"
    if report.rule_reasons:
        return f"值得深入核對：{report.rule_reasons[0]}"
    return "目前沒有足夠資料支持「值得看」結論。"


def _report_next_step(report: StockResearchReportDTO) -> str:
    """依缺件與既有入口給出可執行的研究下一步。"""

    price_section = next(
        (section for section in report.sections if section.section_id == "price"),
        None,
    )
    if not report.price_points or (
        price_section is not None
        and price_section.status in {
            ReportSectionStatus.MISSING.value,
            ReportSectionStatus.ERROR.value,
        }
    ):
        return "先從「數據更新」補齊價格資料，再回來查看價格／技術分頁。"
    if report.advice.recommendation is None and report.advice.limitations:
        return "若要核對推薦理由，回到推薦分析明確選定原始來源；不要用同股或最新結果代替。"
    if report.position is not None:
        return "若是持倉，先到持倉／Health／Exit 分頁核對成本、資料日與失效條件。"
    return "先核對價格、基本面與籌碼的資料日，再按需開啟進階來源與歷史內容。"


def _join_or_missing(values: Sequence[str], fallback: str) -> str:
    cleaned = tuple(str(value).strip() for value in values if str(value).strip())
    return "；".join(cleaned) if cleaned else fallback


def _freshness_text(report: StockResearchReportDTO) -> str:
    parts = [f"查詢日期：{report.as_of or '—'}"]
    for section in report.sections:
        parts.append(f"{section.label}：{_quality_label(section.freshness)}（{section.data_as_of or '—'}）")
    return "；".join(parts)


def _advice_summary(advice: StockAdviceSnapshotDTO) -> str:
    if advice.recommendation is None:
        return _join_or_missing(advice.limitations, "目前沒有適用 Advice；資料不足不等於看空。")
    rec = advice.recommendation
    return (
        f"{_advice_action_label(rec.advice_action.value)}｜"
        f"資料品質 {rec.data_quality or '—'}｜"
        f"依據 {_join_or_missing(rec.why_reasons, '未提供')}"
    )


def _advice_action_label(value: str) -> str:
    return {
        "RESEARCH": "觀察／資料不足",
        "ADD_CANDIDATE": "買進候選",
        "HOLD": "續抱",
        "REDUCE_CANDIDATE": "減碼候選",
        "EXIT_CANDIDATE": "賣出候選",
        "AVOID": "避免／觀察",
        "NO_NEW_POSITION": "暫不新增",
    }.get(value, value or "資料不足")
