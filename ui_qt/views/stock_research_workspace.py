"""主程式內的個股研究工作區，共用報告與決策結果讀取元件。"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from app_module.decision_continuity_controller import DecisionContinuityController
from app_module.decision_outcome_journey import DecisionOutcomeJourneyService
from app_module.research_session import ResearchStockContextDTO
from app_module.stock_research_report_service import StockResearchReportReadService
from ui_qt.views.stock_research_report_view import StockResearchReportView
from ui_qt.widgets.decision_outcome_journey_widget import DecisionOutcomeJourneyWidget


class StockResearchWorkspace(QWidget):
    """切離頁面保留研究內容；僅主程式關閉時取消背景讀取。"""

    returnRequested = Signal()

    def __init__(
        self,
        service: StockResearchReportReadService,
        *,
        journey_service: DecisionOutcomeJourneyService | None = None,
        continuity_controller: DecisionContinuityController | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("stockResearchWorkspace")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
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
        layout.addWidget(self.report_tabs)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(320, 0)

    def set_context(
        self,
        context: ResearchStockContextDTO,
        *,
        stock_codes: Sequence[str] = (),
    ) -> None:
        self.report_view.set_stock_codes(stock_codes)
        self.report_tabs.setCurrentWidget(self.report_view)
        self.report_view.set_context(context)

    def is_busy(self) -> bool:
        return self.report_view.is_busy() or bool(
            self.journey_view is not None and self.journey_view.is_busy()
        )

    def request_close(self) -> bool:
        """兩個讀取元件均須收到取消，不使用短路運算漏掉 Journey。"""

        report_ready = self.report_view.request_close()
        journey_ready = self.journey_view is None or self.journey_view.request_close()
        return report_ready and journey_ready
