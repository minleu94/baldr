"""UX08 推薦保存來源的實際 offscreen 圖表／表與取消、重試、stale 驗證。"""
from dataclasses import replace
from decimal import Decimal
from threading import Event
import time
from PySide6.QtWidgets import QTableView
from app_module.stock_research_report_service import StockResearchReportCancelled
from ui_qt.views.stock_research_report_view import StockPriceChartWidget, StockResearchReportView
from tests.test_ui_qt_saved_stock_chart import app, _wait
from tests.test_recommendation_saved_chart_integration import produce, reader as make_reader


def test_recommendation_background_chart_cancel_retry_return_and_stale_callback(app, tmp_path):
    *_, config, context = produce(tmp_path)
    reader = make_reader(config)
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
        assert chart._technical_lines[0].points[-1].value == Decimal("99.123456")
        table = view.findChild(QTableView, "stockResearchTechnicalHistoryTable")
        assert table.model().index(0, 1).data() == "99.123456"
        assert table.model().index(0, 2).data() == "—（未提供）"
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
