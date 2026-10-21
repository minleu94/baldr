"""主程式內的個股研究工作區，共用報告與決策結果讀取元件。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtCore import QSize, Signal, Qt, QSignalBlocker
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QGroupBox, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QStackedWidget, QTabWidget, QVBoxLayout, QWidget,
)

from app_module.decision_continuity_controller import DecisionContinuityController
from app_module.decision_outcome_journey import DecisionOutcomeJourneyService
from app_module.research_session import ResearchStockContextDTO
from app_module.pinned_stock_research_notes import PinnedStockResearchNoteService
from app_module.stock_research_report_notes import StockResearchReportNoteService
from app_module.stock_research_report_snapshot_codec import (
    StockResearchReportProjectionSnapshot,
    read_stock_research_report_projection_snapshot,
)
from app_module.stock_research_report_service import StockResearchReportReadService
from app_module.daily_market_technical_universe_price_comparison_v1 import (
    DailyMarketTechnicalUniversePriceSelectionV1,
)
from ui_qt.views.stock_research_report_view import StockResearchReportView
from ui_qt.widgets.decision_outcome_journey_widget import DecisionOutcomeJourneyWidget
from ui_qt.widgets.info_button import InfoButton
from ui_qt.widgets.pinned_stock_research_notes_widget import PinnedStockResearchNotesWidget
from ui_qt.widgets.stock_research_report_notes_widget import StockResearchReportNotesWidget


@dataclass(frozen=True)
class HistoricalResearchViewToken:
    """保留可精確返回的保存報告或價格原來源元件。"""

    saved_snapshot: StockResearchReportProjectionSnapshot | None = None
    price_selection: DailyMarketTechnicalUniversePriceSelectionV1 | None = None
    saved_report_view: QWidget | None = None
    price_page: QWidget | None = None
    price_view: QWidget | None = None
    price_context: ResearchStockContextDTO | None = None


class StockResearchWorkspace(QWidget):
    """切離頁面保留研究內容；僅主程式關閉時取消背景讀取。"""

    returnRequested = Signal()
    personalH20SavedRecheckRequested = Signal()
    priceResearchReturnRequested = Signal(object)
    sourceContextShown = Signal(object)
    priceNoteSourceRequested = Signal(object)
    favoriteRequested = Signal(object)
    priceComparisonRequested = Signal(object)
    prepareBacktestRequested = Signal(object)
    latestResearchRequested = Signal(object)

    def __init__(
        self,
        service: StockResearchReportReadService,
        *,
        journey_service: DecisionOutcomeJourneyService | None = None,
        continuity_controller: DecisionContinuityController | None = None,
        price_note_service: PinnedStockResearchNoteService | None = None,
        report_note_service: StockResearchReportNoteService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("stockResearchWorkspace")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        title_layout = QHBoxLayout()
        self.workspace_title = QLabel("個股研究")
        title_layout.addWidget(self.workspace_title)
        title_layout.addStretch()
        title_layout.addWidget(InfoButton("stock_research", self))
        self.general_lookup_button = QPushButton("改用一般個股查詢", self)
        self.general_lookup_button.setObjectName("stockResearchGeneralLookupButton")
        self.general_lookup_button.setToolTip("離開原選股來源，使用一般個股頁已配置的價庫；不會把兩份資料合併。")
        self.general_lookup_button.clicked.connect(self._open_general_lookup)
        self.general_lookup_button.hide()
        title_layout.addWidget(self.general_lookup_button)
        layout.addLayout(title_layout)
        self.product_action_row = QWidget(self)
        product_action_layout = QHBoxLayout(self.product_action_row)
        product_action_layout.setContentsMargins(0, 0, 0, 0)
        product_action_layout.setSpacing(6)
        self.favorite_action = QPushButton("☆自選", self.product_action_row)
        self.favorite_action.setObjectName("stockResearchFavoriteAction")
        self.favorite_action.setAccessibleName("加入純自選")
        self.favorite_action.setToolTip("只以股票代號與名稱加入純自選，不保存原選股 Query。")
        self.favorite_action.clicked.connect(self._emit_favorite_request)
        product_action_layout.addWidget(self.favorite_action)
        self.price_comparison_action = QPushButton("＋比較", self.product_action_row)
        self.price_comparison_action.setObjectName("stockResearchPriceComparisonAction")
        self.price_comparison_action.setAccessibleName("加入來源內比較")
        self.price_comparison_action.setToolTip("只有母體價量原來源可加入同來源比較；其他來源請回來源頁建立比較。")
        self.price_comparison_action.clicked.connect(self._emit_price_comparison_request)
        product_action_layout.addWidget(self.price_comparison_action)
        self.prepare_backtest_action = QPushButton("準備回測", self.product_action_row)
        self.prepare_backtest_action.setObjectName("stockResearchPrepareBacktestAction")
        self.prepare_backtest_action.setAccessibleName("以目前一般個股報告準備回測")
        self.prepare_backtest_action.setToolTip("只為已載入的一般最新可用個股報告預填，不會執行回測。")
        self.prepare_backtest_action.clicked.connect(self._emit_prepare_backtest_request)
        product_action_layout.addWidget(self.prepare_backtest_action)
        self._product_action_group = QButtonGroup(self)
        self._product_action_group.setExclusive(True)
        self.research_content_action = QPushButton("研究內容", self.product_action_row)
        self.research_content_action.setObjectName("stockResearchContentAction")
        self.save_judgment_action = QPushButton("保存判斷", self.product_action_row)
        self.save_judgment_action.setObjectName("stockResearchJudgmentAction")
        self.outcome_tracking_action = QPushButton("成果追蹤", self.product_action_row)
        self.outcome_tracking_action.setObjectName("stockResearchOutcomeAction")
        for key, button in (
            ("content", self.research_content_action),
            ("judgment", self.save_judgment_action),
            ("outcomes", self.outcome_tracking_action),
        ):
            button.setCheckable(True)
            button.clicked.connect(
                lambda _checked=False, action=key: self._activate_product_action(action)
            )
            self._product_action_group.addButton(button)
            product_action_layout.addWidget(button)
        product_action_layout.addStretch(1)
        layout.addWidget(self.product_action_row)
        self.content_stack = QStackedWidget(self)
        self.content_stack.currentChanged.connect(self._sync_product_action_state)
        self.general_report_page = QWidget(self.content_stack)
        general_layout = QVBoxLayout(self.general_report_page)
        general_layout.setContentsMargins(0, 0, 0, 0)
        self.personal_h20_saved_group = QGroupBox("保存的個人 H20 研究預測", self)
        self.personal_h20_saved_group.setObjectName("stockResearchSavedH20Summary")
        self.personal_h20_saved_group.setAccessibleName("已保存個人 H20 預測摘要")
        saved_h20_layout = QVBoxLayout(self.personal_h20_saved_group)
        self.personal_h20_saved_summary = QLabel(
            "尚未選取已保存的個人 H20 來源。", self.personal_h20_saved_group
        )
        self.personal_h20_saved_summary.setObjectName("stockResearchSavedH20SummaryText")
        self.personal_h20_saved_summary.setAccessibleName("已保存個人 H20 預測與日期")
        self.personal_h20_saved_summary.setWordWrap(True)
        self.personal_h20_saved_summary.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        saved_h20_layout.addWidget(self.personal_h20_saved_summary)
        self.personal_h20_saved_recheck_button = QPushButton("重新核驗保存預測", self.personal_h20_saved_group)
        self.personal_h20_saved_recheck_button.setObjectName("stockResearchSavedH20Recheck")
        self.personal_h20_saved_recheck_button.setAccessibleName("重新核驗目前選取的保存 H20 預測")
        self.personal_h20_saved_recheck_button.setToolTip(
            "只重讀目前精確選取的保存來源與原 pins，不改讀最新預測。"
        )
        self.personal_h20_saved_recheck_button.clicked.connect(
            self.personalH20SavedRecheckRequested.emit
        )
        saved_h20_layout.addWidget(self.personal_h20_saved_recheck_button)
        self.personal_h20_saved_evidence = None
        self.personal_h20_saved_busy = False
        self.personal_h20_saved_retry_allowed = False
        self.personal_h20_saved_group.setVisible(False)
        general_layout.addWidget(self.personal_h20_saved_group)
        self.report_tabs = QTabWidget(self)
        self.report_tabs.setDocumentMode(True)
        self.report_view = StockResearchReportView(service, parent=self)
        self.report_view.latestResearchRequested.connect(self.latestResearchRequested.emit)
        self.report_view.activeContextChanged.connect(self._sync_general_lookup_action)
        self.report_view.returnRequested.connect(self.returnRequested.emit)
        self.report_tabs.addTab(self.report_view, "個股研究報告")
        self.report_notes_widget: StockResearchReportNotesWidget | None = None
        self.report_notes_page: QScrollArea | None = None
        self.saved_report_view: StockResearchReportView | None = None
        if report_note_service is not None:
            self.report_notes_widget = StockResearchReportNotesWidget(report_note_service, self)
            self.report_notes_page = QScrollArea(self)
            self.report_notes_page.setWidgetResizable(True)
            self.report_notes_page.setWidget(self.report_notes_widget)
            self.report_tabs.addTab(self.report_notes_page, "我的判斷")
            self.report_notes_widget.openSnapshotRequested.connect(self.show_saved_report_snapshot)
            self.report_view.activeContextChanged.connect(self._invalidate_report_snapshot)
            self.report_view.reportLoaded.connect(self._capture_report_snapshot)
            self.report_view.reportFailed.connect(self._invalidate_report_snapshot)
        self.report_tabs.currentChanged.connect(self._on_report_notes_tab_changed)
        self.report_view.activeContextChanged.connect(self._sync_product_action_state)
        self.report_view.reportLoaded.connect(self._sync_product_action_state)
        self.report_view.reportFailed.connect(self._sync_product_action_state)
        self.journey_view: DecisionOutcomeJourneyWidget | None = None
        if journey_service is not None:
            self.journey_view = DecisionOutcomeJourneyWidget(
                journey_service,
                continuity_controller=continuity_controller,
                parent=self,
            )
            self.report_view.activeContextChanged.connect(self.journey_view.set_context)
            self.report_tabs.addTab(self.journey_view, "決策 → 結果")
        general_layout.addWidget(self.report_tabs)
        self.content_stack.addWidget(self.general_report_page)
        self.price_research_view = None
        self.price_research_page: QWidget | None = None
        self.price_source_header: QLabel | None = None
        self.price_section_selector: QComboBox | None = None
        self.price_research_context: ResearchStockContextDTO | None = None
        self.price_notes_widget: PinnedStockResearchNotesWidget | None = None
        self.price_notes_page: QScrollArea | None = None
        if price_note_service is not None:
            self.price_notes_widget = PinnedStockResearchNotesWidget(price_note_service, self)
            self.price_notes_widget.open_source_requested.connect(self.priceNoteSourceRequested.emit)
            self.price_notes_page = QScrollArea(self)
            self.price_notes_page.setWidgetResizable(True)
            self.price_notes_page.setWidget(self.price_notes_widget)
            self.price_notes_page.hide()
        layout.addWidget(self.content_stack)
        self.enable_product_layout()

    def _invalidate_report_snapshot(self, _context: object = None) -> None:
        if getattr(self, "_product_content_report", self.report_view) is not self.report_view:
            return
        if self.report_notes_widget is not None:
            self.report_notes_widget.set_snapshot(None, stock_code=self.report_view.stock_search.text().strip())

    def _on_report_notes_tab_changed(self, _index: int) -> None:
        current = self.report_tabs.currentWidget()
        if isinstance(current, StockResearchReportView):
            self._product_content_report = current
            if getattr(self, "journey_view", None) is not None:
                self.journey_view.set_context(current.context)
        if (
            self.report_notes_widget is not None
            and self.report_tabs.currentWidget() is self.report_notes_page
        ):
            self.report_notes_widget.refresh_notes()
        self._sync_product_action_state()

    def enable_product_layout(self) -> None:
        """以工作區動作列與章節選擇器呈現既有研究頁面。"""

        self.report_tabs.tabBar().hide()
        self.report_view.enable_product_layout()
        if self.saved_report_view is not None:
            self.saved_report_view.enable_product_layout()
        if self.price_research_view is not None:
            self.price_research_view.detail_tabs.tabBar().hide()
        self.product_action_row.show()
        self._sync_product_action_state()

    def focus_section(self, key: str) -> bool:
        """提供主殼層可呼叫的研究章節定位入口。"""

        if self._is_price_research_active():
            candidate = self.price_research_view
            if candidate is None:
                return False
            if key in ("price", "main_chart", "price_chart"):
                candidate.detail_tabs.setCurrentIndex(0)
                return True
            if key in ("rules", "price_rules", "evidence"):
                candidate.detail_tabs.setCurrentIndex(1)
                return True
            if key in ("judgment", "notes") and self.price_notes_page is not None:
                index = candidate.detail_tabs.indexOf(self.price_notes_page)
                if index >= 0:
                    candidate.detail_tabs.setCurrentIndex(index)
                    return True
            return False
        report_target = self.report_tabs.currentWidget()
        if isinstance(report_target, StockResearchReportView):
            return report_target.focus_section(key)
        if report_target is self.report_notes_page or report_target is self.journey_view:
            self.report_tabs.setCurrentWidget(getattr(self, "_product_content_report", self.report_view))
            self._sync_product_action_state()
        return getattr(self, "_product_content_report", self.report_view).focus_section(key)

    def _activate_product_action(self, action: str) -> None:
        if self._is_price_research_active():
            candidate = self.price_research_view
            if candidate is None:
                return
            if action == "content":
                candidate.detail_tabs.setCurrentIndex(0)
            elif action == "judgment" and self.price_notes_page is not None:
                index = candidate.detail_tabs.indexOf(self.price_notes_page)
                if index >= 0:
                    candidate.detail_tabs.setCurrentIndex(index)
        elif action == "content":
            self.report_tabs.setCurrentWidget(getattr(self, "_product_content_report", self.report_view))
        elif action == "judgment" and self.report_notes_page is not None:
            self.report_tabs.setCurrentWidget(self.report_notes_page)
        elif action == "outcomes" and self.journey_view is not None:
            self.report_tabs.setCurrentWidget(self.journey_view)
        self._sync_product_action_state()

    def _is_price_research_active(self) -> bool:
        price_page = getattr(self, "price_research_page", None)
        return (
            price_page is not None
            and self.content_stack.currentWidget() is price_page
        )

    def _active_detail_context(self) -> ResearchStockContextDTO | None:
        """回傳目前可見且股票代號一致的原始研究脈絡。"""
        if self._is_price_research_active():
            view = self.price_research_view
            context = self.price_research_context
            selection = getattr(view, "origin_selection", None)
            if (
                type(selection) is DailyMarketTechnicalUniversePriceSelectionV1
                and isinstance(context, ResearchStockContextDTO)
                and selection.stock_code == context.stock_code
            ):
                return context
            return None

        if self.content_stack.currentWidget() is not self.general_report_page:
            return None
        report_page = self.report_tabs.currentWidget()
        if not isinstance(report_page, StockResearchReportView):
            report_page = getattr(self, "_product_content_report", self.report_view)
        if not isinstance(report_page, StockResearchReportView):
            return None
        try:
            snapshot = report_page.get_loaded_report_snapshot()
        except (AttributeError, ValueError):
            return None
        if snapshot is None or snapshot.context is None:
            return None
        if snapshot.stock_code != snapshot.context.stock_code:
            return None
        return snapshot.context

    def capture_historical_view(self) -> HistoricalResearchViewToken | None:
        """記錄目前可見的固定報告或原價格詳情，以供 host 重核後返回。"""
        if self._is_price_research_active():
            view = self.price_research_view
            page = self.price_research_page
            context = self.price_research_context
            selection = getattr(view, "origin_selection", None)
            if (
                view is not None
                and page is not None
                and type(selection) is DailyMarketTechnicalUniversePriceSelectionV1
                and isinstance(context, ResearchStockContextDTO)
                and context.stock_code == selection.stock_code
                and self.content_stack.indexOf(page) >= 0
            ):
                return HistoricalResearchViewToken(
                    price_selection=selection,
                    price_page=page,
                    price_view=view,
                    price_context=context,
                )
            return None

        if (
            self.content_stack.currentWidget() is not self.general_report_page
            or self.saved_report_view is None
            or self.report_tabs.currentWidget() is not self.saved_report_view
        ):
            return None
        try:
            snapshot = self.saved_report_view.get_loaded_report_snapshot()
        except (AttributeError, ValueError):
            return None
        if type(snapshot) is not StockResearchReportProjectionSnapshot:
            return None
        return HistoricalResearchViewToken(
            saved_snapshot=snapshot,
            saved_report_view=self.saved_report_view,
        )

    def restore_historical_view(self, token: HistoricalResearchViewToken) -> bool:
        """只還原同一個仍保留的歷史元件；不把舊 context 當成新查詢。"""
        if type(token) is not HistoricalResearchViewToken:
            return False
        if token.saved_snapshot is not None:
            if type(token.saved_snapshot) is not StockResearchReportProjectionSnapshot:
                return False
            view = token.saved_report_view
            if view is None or view is not self.saved_report_view:
                return False
            current = getattr(view, "_saved_projection_snapshot", None)
            if (
                type(current) is not StockResearchReportProjectionSnapshot
                or current.canonical_json != token.saved_snapshot.canonical_json
                or current.identity_sha256 != token.saved_snapshot.identity_sha256
            ):
                return False
            try:
                verified = read_stock_research_report_projection_snapshot(
                    current.canonical_json,
                    expected_identity_sha256=current.identity_sha256,
                )
            except (TypeError, ValueError):
                return False
            if verified.canonical_json != token.saved_snapshot.canonical_json:
                return False
            self._show_general_report()
            self.report_tabs.setCurrentWidget(view)
            self._sync_product_action_state()
            return self.report_tabs.currentWidget() is view

        selection = token.price_selection
        page = token.price_page
        view = token.price_view
        context = token.price_context
        if (
            type(selection) is not DailyMarketTechnicalUniversePriceSelectionV1
            or page is None
            or view is None
            or not isinstance(context, ResearchStockContextDTO)
            or self.price_research_view is not view
            or self.price_research_page is not page
            or self.price_research_context != context
            or getattr(view, "origin_selection", None) is not selection
            or self.content_stack.indexOf(page) < 0
        ):
            return False
        self.content_stack.setCurrentWidget(page)
        self.workspace_title.setText("個股研究｜價格選股原來源")
        self.general_lookup_button.show()
        self._sync_general_lookup_action()
        self._sync_product_action_state()
        return self.content_stack.currentWidget() is page

    def _live_general_backtest_context(self) -> ResearchStockContextDTO | None:
        """只讓明選的一般最新報告進入單股回測預填。"""
        if (
            self._is_price_research_active()
            or self.content_stack.currentWidget() is not self.general_report_page
            or self.report_tabs.currentWidget() is not self.report_view
        ):
            return None
        try:
            snapshot = self.report_view.get_loaded_report_snapshot()
        except ValueError:
            return None
        if snapshot is None:
            return None
        context = snapshot.context
        if (
            context is None
            or context.source_kind != "explicit_latest_stock_research"
            or snapshot.stock_code != context.stock_code
        ):
            return None
        return context

    def _emit_favorite_request(self) -> None:
        context = self._active_detail_context()
        if context is not None:
            self.favoriteRequested.emit(context)

    def _emit_price_comparison_request(self) -> None:
        if not self._is_price_research_active():
            return
        view = self.price_research_view
        selection = getattr(view, "origin_selection", None)
        context = self.price_research_context
        if (
            type(selection) is DailyMarketTechnicalUniversePriceSelectionV1
            and isinstance(context, ResearchStockContextDTO)
            and selection.stock_code == context.stock_code
        ):
            self.priceComparisonRequested.emit(selection)

    def _emit_prepare_backtest_request(self) -> None:
        context = self._live_general_backtest_context()
        if context is not None:
            self.prepareBacktestRequested.emit(context)

    def _sync_product_action_state(self, _index: int = -1) -> None:
        if not hasattr(self, "research_content_action"):
            return
        price_active = self._is_price_research_active()
        report_current = self.report_tabs.currentWidget()
        price_view = getattr(self, "price_research_view", None)
        price_notes_page = getattr(self, "price_notes_page", None)
        report_notes_page = getattr(self, "report_notes_page", None)
        journey_view = getattr(self, "journey_view", None)
        if price_active:
            price_notes_active = bool(
                price_view is not None
                and price_notes_page is not None
                and price_view.detail_tabs.currentWidget() is price_notes_page
            )
            current_action = "judgment" if price_notes_active else "content"
        elif report_current is report_notes_page:
            current_action = "judgment"
        elif journey_view is not None and report_current is journey_view:
            current_action = "outcomes"
        else:
            current_action = "content"

        self.research_content_action.setChecked(current_action == "content")
        self.save_judgment_action.setChecked(current_action == "judgment")
        self.outcome_tracking_action.setChecked(current_action == "outcomes")
        has_notes = report_notes_page is not None or price_notes_page is not None
        self.save_judgment_action.setVisible(has_notes)
        self.save_judgment_action.setEnabled(
            price_notes_page is not None
            if price_active
            else report_notes_page is not None
        )
        self.outcome_tracking_action.setVisible(journey_view is not None)
        self.outcome_tracking_action.setEnabled(
            journey_view is not None and not price_active
        )
        active_context = self._active_detail_context()
        self.favorite_action.setEnabled(active_context is not None)
        self.price_comparison_action.setEnabled(
            price_active
            and active_context is not None
            and type(getattr(price_view, "origin_selection", None))
            is DailyMarketTechnicalUniversePriceSelectionV1
        )
        backtest_context = self._live_general_backtest_context()
        self.prepare_backtest_action.setEnabled(backtest_context is not None)
        if price_active:
            self.price_comparison_action.setToolTip(
                "加入目前已核驗的母體價量原來源比較清單。"
                if self.price_comparison_action.isEnabled()
                else "原選取身份無法核驗；請回來源頁建立同源比較。"
            )
            self.prepare_backtest_action.setToolTip(
                "原來源已釘定；不能套用一般最新價庫。請先明選一般個股查詢。"
            )
        else:
            self.price_comparison_action.setToolTip(
                "此來源沒有同源比較資格；請回來源頁建立比較。"
            )
            displayed_context = self._active_detail_context()
            if displayed_context is not None and (
                displayed_context.source_kind != "explicit_latest_stock_research"
                or self.report_tabs.currentWidget() is self.saved_report_view
            ):
                self.prepare_backtest_action.setToolTip(
                    "此報告來自保存或釘定來源；不能套用一般最新價庫。"
                )
            else:
                self.prepare_backtest_action.setToolTip(
                    "準備回測僅適用於已載入的一般最新可用個股報告；不會執行回測。"
                )

    def _sync_price_section_selector(self, candidate: QWidget, index: int) -> None:
        if (
            candidate is not self.price_research_view
            or self.price_section_selector is None
            or index < 0
        ):
            return
        blocker = QSignalBlocker(self.price_section_selector)
        self.price_section_selector.setCurrentIndex(
            self.price_section_selector.findData(index, Qt.ItemDataRole.UserRole)
        )
        del blocker
        self._sync_product_action_state()

    def _select_price_section(self, index: int) -> None:
        candidate = self.price_research_view
        if candidate is None or self.price_section_selector is None:
            return
        tab_index = self.price_section_selector.itemData(
            index, Qt.ItemDataRole.UserRole
        )
        if isinstance(tab_index, int) and 0 <= tab_index < candidate.detail_tabs.count():
            candidate.detail_tabs.setCurrentIndex(tab_index)

    def _capture_report_snapshot(self, _report: object) -> None:
        if getattr(self, "_product_content_report", self.report_view) is not self.report_view:
            return
        notes = self.report_notes_widget
        if notes is None:
            return
        try:
            snapshot = self.report_view.get_loaded_report_snapshot()
        except ValueError as exc:
            self._invalidate_report_snapshot()
            notes.source_label.setText(f"本次報告無法保存：{exc}；仍可讀取已保存判斷。")
            return
        notes.set_snapshot(
            snapshot,
            stock_code=snapshot.stock_code if snapshot is not None else self.report_view.stock_search.text().strip(),
        )

    def show_saved_report_snapshot(self, snapshot: StockResearchReportProjectionSnapshot) -> None:
        """獨立只讀報告頁不接 Main 的即時資料 providers，也不替換一般報告。"""
        if self.saved_report_view is None:
            self.saved_report_view = StockResearchReportView(
                self.report_view.service, parent=self, saved_snapshot_only=True,
            )
            self.saved_report_view.returnRequested.connect(self._return_to_report_notes)
            self.saved_report_view.latestResearchRequested.connect(self.latestResearchRequested.emit)
            self.report_tabs.addTab(self.saved_report_view, "保存時報告")
        self.saved_report_view.enable_product_layout()
        self.saved_report_view.show_saved_report_snapshot(snapshot)
        self._show_general_report()
        self.report_tabs.setCurrentWidget(self.saved_report_view)
        if self.report_notes_widget is not None:
            self.report_notes_widget.set_snapshot(snapshot, stock_code=snapshot.stock_code)

    def _return_to_report_notes(self) -> None:
        if self.report_notes_page is not None:
            self.report_tabs.setCurrentWidget(self.report_notes_page)
        self._sync_product_action_state()

    def show_price_research(self, stock: object, selection: object) -> None:
        """原 reader 發出的同源選取在正常工作區顯示，不轉一般報告 context。"""
        from ui_qt.views.daily_market_technical_price_stock_v1_view import DailyMarketTechnicalPriceStockV1View

        candidate = DailyMarketTechnicalPriceStockV1View(self)
        try:
            candidate.show_stock(stock, selection)
        except (TypeError, ValueError):
            candidate.deleteLater()
            raise
        candidate.returnRequested.connect(self.priceResearchReturnRequested.emit)
        candidate.latestResearchRequested.connect(
            lambda current=candidate: self._request_latest_research_from_price(current)
        )
        previous = self.price_research_view
        previous_page = self.price_research_page
        if self.price_notes_widget is not None and self.price_notes_page is not None:
            from app_module.daily_market_technical_universe_price_bookmark_v1 import (
                DailyMarketTechnicalUniversePriceBookmarkV1,
            )

            # 原 selection 已由同源頁交叉核對；後台保存仍會 fresh exact 重驗。
            bookmark = DailyMarketTechnicalUniversePriceBookmarkV1.create(
                selected=selection, scroll_position=0,
            )
            if previous is not None:
                tab_index = previous.detail_tabs.indexOf(self.price_notes_page)
                if tab_index >= 0:
                    previous.detail_tabs.removeTab(tab_index)
            candidate.detail_tabs.addTab(self.price_notes_page, "我的判斷")
            self.price_notes_widget.set_source(bookmark)

        price_page = QWidget(self.content_stack)
        price_layout = QVBoxLayout(price_page)
        price_layout.setContentsMargins(0, 0, 0, 0)
        self.price_source_header = QLabel(price_page)
        self.price_source_header.setObjectName("stockResearchPriceSourceHeader")
        self.price_source_header.setAccessibleName("價格研究來源與資料日期")
        self.price_source_header.setWordWrap(True)
        price_layout.addWidget(self.price_source_header)
        section_row = QHBoxLayout()
        section_row.addWidget(QLabel("研究情境", price_page))
        self.price_section_selector = QComboBox(price_page)
        self.price_section_selector.setObjectName("stockResearchPriceSectionSelector")
        self.price_section_selector.setAccessibleName("價格研究章節選擇")
        for index in range(candidate.detail_tabs.count()):
            self.price_section_selector.addItem(
                candidate.detail_tabs.tabText(index), index
            )
        self.price_section_selector.currentIndexChanged.connect(
            self._select_price_section
        )
        section_row.addWidget(self.price_section_selector, 1)
        price_layout.addLayout(section_row)
        candidate.detail_tabs.tabBar().hide()
        price_layout.addWidget(candidate, 1)
        self.content_stack.addWidget(price_page)
        self.price_research_view = candidate
        self.price_research_page = price_page
        candidate.detail_tabs.currentChanged.connect(
            lambda index, current=candidate: self._sync_price_section_selector(
                current, index
            )
        )
        self.content_stack.setCurrentWidget(price_page)
        self.workspace_title.setText("個股研究｜價格選股原來源")
        self.general_lookup_button.show()
        self.clear_personal_h20_saved_summary()
        source = selection.query.source
        self.price_research_context = ResearchStockContextDTO(
            stock_code=stock.stock_code,
            decision_date=source.decision_date.isoformat(),
            data_date=selection.observation_date or "",
            result_id=selection.result_identity_sha256,
            identity_status="exact_saved_selection",
            source_snapshot_id=stock.snapshot.snapshot_identity_sha256,
            source_snapshot_hash=stock.snapshot.snapshot_identity_sha256,
            source_id=stock.snapshot.source_id,
            source_version=source.source_identity_sha256,
            source_kind="technical_price_saved_source",
            source_label="價格選股原來源（可得時間未知）",
            source_workspace="recommendation",
        )
        self.price_source_header.setText(
            f"{self.price_research_context.source_label}｜{stock.stock_code}｜"
            f"決策日 {self.price_research_context.decision_date or '未知'}｜"
            f"資料日 {self.price_research_context.data_date or '未知'}"
        )
        self.sourceContextShown.emit(self.price_research_context)
        if previous_page is not None:
            self.content_stack.removeWidget(previous_page)
            previous_page.deleteLater()
        self._sync_general_lookup_action()
        self._sync_product_action_state()

    def _request_latest_research_from_price(self, view: QWidget) -> None:
        """把原價格 context 交給 Main；由 Main 建立乾淨的目前資料 context。"""
        selection = getattr(view, "origin_selection", None)
        context = self.price_research_context
        if (
            not self._is_price_research_active()
            or view is not self.price_research_view
            or type(selection) is not DailyMarketTechnicalUniversePriceSelectionV1
            or not isinstance(context, ResearchStockContextDTO)
            or context.stock_code != selection.stock_code
        ):
            return
        self.latestResearchRequested.emit(context)

    def _show_general_report(self) -> None:
        self.content_stack.setCurrentWidget(self.general_report_page)
        self.workspace_title.setText("個股研究")
        self._sync_general_lookup_action()
        self._sync_product_action_state()

    def _sync_general_lookup_action(self, _context: object = None) -> None:
        context = self.report_view.context
        bound_source = bool(
            self._is_price_research_active()
            or context is not None and context.source_kind
            and context.source_kind != "explicit_latest_stock_research"
        )
        self.general_lookup_button.setVisible(bound_source)
        self.report_view.load_button.setText("重讀原來源報告" if bound_source else "載入個股報告")
        self.general_lookup_button.setToolTip(
            "使用目前輸入的代號另開一般價庫查詢；原保存來源不會獲得另一份行情或名稱資格。"
        )

    def _open_general_lookup(self) -> None:
        if self.is_busy():
            self.report_view._set_status("請等目前讀取或筆記保存完成，再另開一般個股查詢。", "warning")
            return
        context = self.price_research_context if self._is_price_research_active() else None
        code = context.stock_code if context is not None else self.report_view.stock_search.text().strip()
        if not code:
            self.report_view.stock_search.setFocus()
            return
        self._show_general_report()
        self.clear_personal_h20_saved_summary()
        self.report_tabs.setCurrentWidget(self.report_view)
        independent = ResearchStockContextDTO(
            stock_code=code,
            source_kind="explicit_latest_stock_research",
            source_label="使用者明選的一般個股查詢（獨立現況）",
            source_workspace="stock_research",
            ml_scope_mode="current_stock_research",
        )
        self.report_view.set_context(independent)
        self.sourceContextShown.emit(independent)

    def clear_personal_h20_saved_summary(self) -> None:
        self.personal_h20_saved_evidence = None
        self.personal_h20_saved_busy = False
        self.personal_h20_saved_retry_allowed = False
        for name in ("sourceStockCode", "decisionDate", "sourceDate", "featureDate"):
            self.personal_h20_saved_summary.setProperty(name, "")
        self.personal_h20_saved_summary.setText("尚未選取已保存的個人 H20 來源。")
        self.personal_h20_saved_summary.setToolTip("")
        self.personal_h20_saved_recheck_button.setEnabled(False)
        self.personal_h20_saved_group.setVisible(False)

    def show_personal_h20_saved_loading(self, context: object, *, feature_date: str = "") -> None:
        stock_code = str(getattr(context, "stock_code", "") or "未知股票")
        decision_date = str(getattr(context, "decision_date", "") or "待來源核驗")
        source_date = str(getattr(context, "data_date", "") or "待來源核驗")
        feature_text = feature_date or "待來源核驗"
        self.personal_h20_saved_summary.setProperty("sourceStockCode", stock_code)
        self.personal_h20_saved_summary.setProperty("decisionDate", decision_date)
        self.personal_h20_saved_summary.setProperty("sourceDate", source_date)
        self.personal_h20_saved_summary.setProperty("featureDate", feature_date)
        self.personal_h20_saved_summary.setText(
            f"{stock_code}｜正在核驗原保存的 H20 預測…\n"
            f"預測日 {decision_date}｜來源日 {source_date}｜特徵截至 {feature_text}\n"
            "實際結果：尚無已核驗結果。"
        )
        self.personal_h20_saved_summary.setToolTip("正在重新核對已選取的 manifest、預測與來源 pins。")
        self.personal_h20_saved_retry_allowed = True
        self.personal_h20_saved_recheck_button.setEnabled(False)
        self.personal_h20_saved_group.setVisible(True)

    def set_personal_h20_saved_busy(self, busy: bool) -> None:
        self.personal_h20_saved_busy = bool(busy)
        self.personal_h20_saved_recheck_button.setEnabled(
            not self.personal_h20_saved_group.isHidden()
            and self.personal_h20_saved_retry_allowed
            and not self.personal_h20_saved_busy
        )

    def set_personal_h20_saved_evidence(
        self, evidence: object, *, context: object = None, retry_allowed: bool = True
    ) -> None:
        """呈現保存 H20 證據；技術識別碼只放在提示中。"""

        from app_module.recommendation.personal_h20_product_evidence import (
            PersonalH20ProductEvidence,
            personal_h20_product_text,
        )

        if not isinstance(evidence, PersonalH20ProductEvidence):
            self.clear_personal_h20_saved_summary()
            return
        self.personal_h20_saved_evidence = evidence
        stock_code = evidence.stock_code
        decision_date = str(
            evidence.decision_date or getattr(context, "decision_date", "") or "待來源核驗"
        )
        source_date = str(
            evidence.source_date or getattr(context, "data_date", "") or "待來源核驗"
        )
        feature_date = str(
            evidence.feature_date
            or self.personal_h20_saved_summary.property("featureDate")
            or "待來源核驗"
        )
        self.personal_h20_saved_summary.setProperty("sourceStockCode", stock_code)
        self.personal_h20_saved_summary.setProperty("decisionDate", decision_date)
        self.personal_h20_saved_summary.setProperty("sourceDate", source_date)
        self.personal_h20_saved_summary.setProperty(
            "featureDate", "" if feature_date == "待來源核驗" else feature_date
        )
        if evidence.status == "available" and evidence.gross_return_bp is not None:
            magnitude = abs(evidence.gross_return_bp)
            sign = "-" if evidence.gross_return_bp < 0 else "+"
            percent = f"{sign}{magnitude // 100}.{magnitude % 100:02d}%"
            text = (
                f"{stock_code}｜保存的個人 H20 研究預測（未扣成本）：{percent}\n"
                f"預測日 {decision_date}｜來源日 {source_date}｜特徵截至 {feature_date}\n"
                "實際結果：目前尚無已核驗結果；預測不等於實際報酬。"
            )
        elif evidence.status == "pending":
            text = (
                f"{stock_code}｜保存的 H20 預測目前尚無可讀證據。\n"
                f"預測日 {decision_date}｜來源日 {source_date}｜特徵截至 {feature_date}\n"
                "實際結果：尚無已核驗結果；未使用其他日期或來源。"
            )
        elif evidence.status == "disabled":
            text = f"{stock_code}｜保存的個人 H20 模型目前停用；未使用替代預測。"
        else:
            reason = str(evidence.reason or "")
            lowered = reason.casefold()
            if "selection_reference_pin_mismatch" in lowered:
                reason_text = "保存來源與目前選取不一致，未顯示預測"
            elif "activation" in lowered or "啟用" in reason:
                reason_text = "啟用設定無法核驗"
            elif any(token in lowered for token in ("identity", "candidate", "stock", "prediction")):
                reason_text = "選取的模型或預測身份不一致"
            elif any(token in lowered for token in ("manifest", "receipt", "capture", "pin", "hash", "reference")):
                reason_text = "保存來源或版本校驗未通過"
            elif "changed" in lowered or "變動" in reason:
                reason_text = "保存來源已變動，請重新讀取名單"
            elif any(token in lowered for token in ("missing", "not found", "no such file")):
                reason_text = "保存來源檔案缺漏"
            else:
                reason_text = "保存來源讀取失敗，請查看診斷提示"
            text = (
                f"{stock_code}｜{reason_text}。\n"
                f"預測日 {decision_date}｜來源日 {source_date}｜特徵截至 {feature_date}\n"
                "實際結果：尚無已核驗結果；未使用其他日期或來源。"
            )
        self.personal_h20_saved_summary.setText(text)
        self.personal_h20_saved_summary.setToolTip(personal_h20_product_text(evidence))
        self.personal_h20_saved_retry_allowed = retry_allowed
        self.personal_h20_saved_group.setVisible(True)
        self.set_personal_h20_saved_busy(self.personal_h20_saved_busy)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(320, 0)

    def set_context(
        self,
        context: ResearchStockContextDTO,
        *,
        stock_codes: Sequence[str] = (),
    ) -> None:
        self.report_view.set_stock_codes(stock_codes)
        self._show_general_report()
        self.report_tabs.setCurrentWidget(self.report_view)
        self.report_view.set_context(context)

    def is_busy(self) -> bool:
        return self.personal_h20_saved_busy or self.report_view.is_busy() or bool(
            self.journey_view is not None and self.journey_view.is_busy()
        ) or bool(
            self.price_notes_widget is not None and self.price_notes_widget.is_busy()
        ) or bool(
            self.report_notes_widget is not None and self.report_notes_widget.is_busy()
        )

    def request_close(self) -> bool:
        """兩個讀取元件均須收到取消，不使用短路運算漏掉 Journey。"""

        report_ready = self.report_view.request_close()
        journey_ready = self.journey_view is None or self.journey_view.request_close()
        notes_ready = True
        price_notes = getattr(self, "price_notes_widget", None)
        if price_notes is not None:
            price_notes.shutdown()
            notes_ready = not price_notes.is_busy()
        if self.report_notes_widget is not None:
            self.report_notes_widget.shutdown()
            notes_ready = notes_ready and not self.report_notes_widget.is_busy()
        return report_ready and journey_ready and notes_ready
