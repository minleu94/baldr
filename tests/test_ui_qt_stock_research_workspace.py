"""個股研究內嵌、頁面重用、返回與合作式關閉的回歸。"""

from __future__ import annotations

import time
from types import SimpleNamespace

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMainWindow, QStackedWidget, QWidget

from app_module.research_session import ResearchSessionStore, ResearchStockContextDTO
from app_module.stock_research_report_dtos import StockResearchReportDTO
from ui_qt.main import MainWindow
from ui_qt.views.stock_research_workspace import StockResearchWorkspace


class _ReadService:
    def read_report(self, stock_code, **_kwargs):
        return StockResearchReportDTO(stock_code=stock_code)


def _wait_idle(app, workspace):
    deadline = time.monotonic() + 3
    while workspace.is_busy() and time.monotonic() < deadline:
        app.processEvents()
        QTest.qWait(10)
    app.processEvents()
    assert not workspace.is_busy()


def test_main_route_reuses_embedded_page_and_returns_current_stock():
    app = QApplication.instance() or QApplication([])

    class Harness(MainWindow):
        def __init__(self):
            QMainWindow.__init__(self)

    window = Harness()
    window.stock_research_report_service = _ReadService()
    window.research_session_store = ResearchSessionStore()
    workspace = StockResearchWorkspace(window.stock_research_report_service)
    window.stock_research_workspace = workspace
    source = QWidget()
    stack = QStackedWidget(window)
    stack.addWidget(source)
    stack.addWidget(workspace)
    window.setCentralWidget(stack)
    window.workspace_stack = stack
    window.workspace_widgets = {"stock_research": workspace, "watchlist": source}
    selected = []
    window.watchlist_view = SimpleNamespace(select_stock=lambda code, _result: selected.append(code))
    workspace.returnRequested.connect(window._return_from_stock_research_report)
    window.show()
    context = ResearchStockContextDTO(stock_code="2330", source_workspace="watchlist")
    window._open_stock_research_context(context)
    _wait_idle(app, workspace)
    assert stack.currentWidget() is workspace
    assert workspace.window() is window
    assert not workspace.isWindow()
    workspace.report_view.set_stock_codes(("2330", "1101"))
    workspace.report_view._step_stock(1)
    _wait_idle(app, workspace)
    workspace.report_view.return_button.click()
    assert stack.currentWidget() is source
    assert selected == ["1101"]
    assert not workspace.report_view._closing
    window._open_stock_research_context(context)
    _wait_idle(app, workspace)
    assert window.stock_research_workspace is workspace
    assert workspace.report_view._loaded_report.stock_code == "2330"
    assert stack.count() == 2
    workspace.request_close()
    window.hide()
    window.deleteLater()
    app.processEvents()


def test_embedded_shutdown_cancels_report_and_journey_even_when_report_busy():
    calls = []
    workspace = SimpleNamespace(
        report_view=SimpleNamespace(request_close=lambda: calls.append("report") or False),
        journey_view=SimpleNamespace(request_close=lambda: calls.append("journey") or True),
    )
    assert StockResearchWorkspace.request_close(workspace) is False
    assert calls == ["report", "journey"]
