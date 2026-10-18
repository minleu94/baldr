"""主程式內的個股研究工作區，共用報告與決策結果讀取元件。"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QSize, Signal, Qt
from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QPushButton, QScrollArea, QStackedWidget, QTabWidget, QVBoxLayout, QWidget,
)

from app_module.decision_continuity_controller import DecisionContinuityController
from app_module.decision_outcome_journey import DecisionOutcomeJourneyService
from app_module.research_session import ResearchStockContextDTO
from app_module.pinned_stock_research_notes import PinnedStockResearchNoteService
from app_module.stock_research_report_service import StockResearchReportReadService
from ui_qt.views.stock_research_report_view import StockResearchReportView
from ui_qt.widgets.decision_outcome_journey_widget import DecisionOutcomeJourneyWidget
from ui_qt.widgets.info_button import InfoButton
from ui_qt.widgets.pinned_stock_research_notes_widget import PinnedStockResearchNotesWidget


class StockResearchWorkspace(QWidget):
    """切離頁面保留研究內容；僅主程式關閉時取消背景讀取。"""

    returnRequested = Signal()
    personalH20SavedRecheckRequested = Signal()
    priceResearchReturnRequested = Signal(object)
    sourceContextShown = Signal(object)
    priceNoteSourceRequested = Signal(object)

    def __init__(
        self,
        service: StockResearchReportReadService,
        *,
        journey_service: DecisionOutcomeJourneyService | None = None,
        continuity_controller: DecisionContinuityController | None = None,
        price_note_service: PinnedStockResearchNoteService | None = None,
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
        self.general_lookup_button.setToolTip("離開原選股來源，使用一般個股頁已配置的價庫；不會把兩份資料合併。")
        self.general_lookup_button.clicked.connect(self._open_general_lookup)
        self.general_lookup_button.hide()
        title_layout.addWidget(self.general_lookup_button)
        layout.addLayout(title_layout)
        self.content_stack = QStackedWidget(self)
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
        self.report_view.returnRequested.connect(self.returnRequested.emit)
        self.report_tabs.addTab(self.report_view, "個股研究報告")
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
        previous = self.price_research_view
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
        self.content_stack.addWidget(candidate)
        self.content_stack.setCurrentWidget(candidate)
        self.price_research_view = candidate
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
        self.sourceContextShown.emit(self.price_research_context)
        if previous is not None:
            self.content_stack.removeWidget(previous)
            previous.deleteLater()

    def _show_general_report(self) -> None:
        self.content_stack.setCurrentWidget(self.general_report_page)
        self.workspace_title.setText("個股研究")
        self.general_lookup_button.hide()

    def _open_general_lookup(self) -> None:
        self._show_general_report()
        self.sourceContextShown.emit(self.report_view.context)

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
        return report_ready and journey_ready and notes_ready
