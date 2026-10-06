"""保存圖表的實際背景consumer、精確表、取消／重試／返回與舊版入口。"""
from dataclasses import replace
from decimal import Decimal
from threading import Event
import time

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QTableView

from app_module.research_session import ResearchStockContextDTO
from app_module.stock_research_report_service import StockResearchReportCancelled
from ui_qt.views.stock_research_report_view import StockPriceChartWidget, StockResearchReportView
from tests.test_saved_stock_technical_chart import _produce, _reader, DAY


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    yield instance


def _wait(app, predicate):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    assert predicate()


def test_saved_background_chart_table_cancel_retry_return_and_stale_callback(app, tmp_path):
    _database, _snapshot, mapping = _produce(tmp_path)
    context = ResearchStockContextDTO(**mapping, source_workspace="watchlist")
    reader = _reader(tmp_path, tmp_path / "missing.sqlite")
    original = reader.read_report
    started = Event()
    hold = [False]

    def controlled(*args, **kwargs):
        if hold[0]:
            started.set()
            while hold[0]:
                if kwargs["cancel_callback"]():
                    raise StockResearchReportCancelled("測試合作取消")
                time.sleep(0.01)
        return original(*args, **kwargs)

    reader.read_report = controlled
    view = StockResearchReportView(reader, context)
    try:
        _wait(app, lambda: view._loaded_report is not None and not view._workers)
        view.tabs.setCurrentIndex(1)
        app.processEvents()
        report = view._loaded_report
        chart = view.findChild(StockPriceChartWidget)
        assert chart is not None and chart._points[-1].close_price == Decimal("100.125")
        assert len(chart._technical_segments(chart._technical_lines[0])) == 2
        table = view.findChild(QTableView, "stockResearchTechnicalHistoryTable")
        assert table.model().index(0, 1).data() == "24"
        assert table.model().index(1, 1).data() == "—（未提供）"
        hold[0] = True
        view.reload_button.click()
        _wait(app, started.is_set)
        cancelled_id = view._request_id
        view._cancel_active_worker()
        _wait(app, lambda: not view._workers)
        assert view._loaded_report == report
        hold[0] = False
        view.reload_button.click()
        _wait(app, lambda: not view._workers and view._request_id > cancelled_id)
        assert view._loaded_report.saved_technical_chart_json == report.saved_technical_chart_json
        view._on_report_loaded(cancelled_id, "2330", replace(report, price_points=()), context)
        assert view._loaded_report.price_points == report.price_points
        returned = []
        view.returnRequested.connect(lambda: returned.append(view.context))
        view.return_button.click()
        assert returned == [context]
    finally:
        hold[0] = False
        view.close()
        _wait(app, lambda: not view._workers)


def test_legacy_saved_missing_chart_offers_explicit_independent_latest_entry(app, tmp_path):
    database, _snapshot, _mapping = _produce(tmp_path)
    context = ResearchStockContextDTO(stock_code="2330", decision_date=DAY.isoformat(),
                                      result_id="legacy-result", source_kind="recommendation", source_workspace="watchlist")
    reader = _reader(tmp_path, database)
    report = reader.read_report("2330", as_of_date=DAY, context=context)
    assert not report.price_points and not report.technical_history
    view = StockResearchReportView(reader)
    try:
        view.context = context
        view._active_code = "2330"
        view._request_id = 1
        view._on_report_loaded(1, "2330", report, context)
        view.tabs.setCurrentIndex(1)
        app.processEvents()
        label = view.findChild(QLabel, "stockResearchSavedChartMissing")
        assert label is not None and "不借今天資料" in label.text()
        assert not view.open_latest_rank_research_button.isHidden()
        opened = []
        view.latestResearchRequested.connect(opened.append)
        view.open_latest_rank_research_button.click()
        assert len(opened) == 1 and opened[0].source_kind == "explicit_latest_stock_research"
        assert not opened[0].result_id and not opened[0].source_snapshot_hash
        assert view.context == context
        current = reader.read_report("2330", as_of_date=DAY, context=opened[0])
        assert current.price_points and current.technical_history
    finally:
        view.close()
