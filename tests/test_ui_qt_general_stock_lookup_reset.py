"""明確一般查詢必須離開保存脈絡，不能借名或混入原版本。"""
import time

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app_module.research_session import ResearchStockContextDTO
from app_module.stock_research_report_dtos import StockResearchReportDTO
from ui_qt.views.stock_research_workspace import StockResearchWorkspace


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


def _idle(app, workspace):
    deadline = time.monotonic() + 3
    while workspace.is_busy() and time.monotonic() < deadline:
        app.processEvents()
        QTest.qWait(10)
    app.processEvents()
    assert not workspace.is_busy()


def test_explicit_general_lookup_uses_input_and_removes_saved_scope(app):
    calls = []
    class Service:
        def read_report(self, code, **kwargs):
            calls.append((code, kwargs.get("context")))
            return StockResearchReportDTO(stock_code=code, stock_name="台積電" if code == "2330" else "原保存名稱")
    workspace = StockResearchWorkspace(Service())
    original = ResearchStockContextDTO(stock_code="1512", source_kind="daily_market_research_snapshot",
                                       result_id="saved-result", decision_date="2026-10-16")
    workspace.set_context(original)
    workspace.show()
    _idle(app, workspace)
    assert not workspace.general_lookup_button.isHidden()
    workspace.report_view.stock_search.setText("2330")
    workspace.general_lookup_button.click()
    _idle(app, workspace)
    code, context = calls[-1]
    assert code == "2330" and context.stock_name == ""
    assert context.source_kind == "explicit_latest_stock_research"
    assert not context.result_id and not context.decision_date and not context.source_snapshot_hash
    assert workspace.report_view._loaded_report.stock_name == "台積電"
    assert original.stock_code == "1512" and original.result_id == "saved-result"
    assert workspace.report_tabs.currentWidget() is workspace.report_view
    assert workspace.general_lookup_button.isHidden()
    workspace.request_close()
    workspace.close()
    workspace.deleteLater()
    app.processEvents()


def test_general_lookup_refuses_during_other_note_write(app, monkeypatch):
    class Service:
        def read_report(self, *_args, **_kwargs):
            raise AssertionError("忙碌時不能啟動另一個查詢")
    workspace = StockResearchWorkspace(Service())
    workspace.report_view.stock_search.setText("2330")
    monkeypatch.setattr(workspace, "is_busy", lambda: True)
    workspace._open_general_lookup()
    assert workspace.report_view.context is None
    workspace.request_close()
    workspace.close()
    workspace.deleteLater()
    app.processEvents()
