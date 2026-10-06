"""UX08 產品按鈕／同源全表／日期槽hover／背景來源安全驗證。"""
from dataclasses import replace
from decimal import Decimal
from threading import Event
from types import SimpleNamespace
import time

import pytest
from PySide6.QtCore import QPointF, QEvent, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QPushButton, QTableView, QLabel
from app_module.stock_research_report_dtos import StockPricePointDTO, StockResearchReportDTO
from app_module.stock_research_report_service import StockResearchReportCancelled
from ui_qt.views.stock_research_report_view import StockPriceChartWidget, StockResearchReportView
from tests.test_ui_qt_saved_stock_chart import app, _wait
from tests.test_recommendation_saved_chart_integration import produce, reader


def button(view, action):
    return view.findChildren(QPushButton, "stockResearchChart" + action)[-1]


def visible(view):
    return view._chart_widget._points


def render(view, report):
    view._active_code = report.stock_code
    view._render_price(report)


def test_saved_controls_full_table_hover_repeat_and_reset(app, tmp_path):
    *_, cfg, context = produce(tmp_path)
    report = reader(cfg).read_report("2330", as_of_date="2026-05-20", context=context)
    view = StockResearchReportView(SimpleNamespace())
    view._loaded_request_context = context
    try:
        render(view, report)
        chart = view._chart_widget
        table = view.findChild(QTableView, "stockResearchPriceHistoryTable")
        technical_table = view.findChild(QTableView, "stockResearchTechnicalHistoryTable")
        full_rows = tuple(table.model().index(i, 4).data() for i in range(20))
        button(view,"ZoomIn").click()
        assert len(visible(view)) == 10
        first_window = tuple(p.data_date for p in visible(view))
        button(view,"PanNewer").click()
        assert tuple(p.data_date for p in visible(view)) != first_window
        assert table.model().rowCount() == technical_table.model().rowCount() == 20
        assert tuple(table.model().index(i,4).data() for i in range(20)) == full_rows
        left,right = chart._plot_x_bounds()
        event = QMouseEvent(QEvent.MouseMove,QPointF(right,70),QPointF(right,70),Qt.NoButton,Qt.NoButton,Qt.NoModifier)
        chart.mouseMoveEvent(event)
        assert visible(view)[-1].data_date in chart.toolTip()
        assert "100.125" in chart.toolTip() and "99.123456" in chart.toolTip()
        assert chart._technical_lines
        assert table.currentIndex().data() == technical_table.currentIndex().data() == visible(view)[-1].data_date
        for _ in range(30): button(view,"ZoomIn").click()
        assert len(visible(view)) == 1 and not button(view,"ZoomIn").isEnabled()
        for _ in range(30): button(view,"PanOlder").click()
        assert visible(view)[0].data_date == report.price_points[0].data_date
        assert not button(view,"PanOlder").isEnabled()
        button(view,"Reset").click()
        assert visible(view) == report.price_points and chart._hover_index is None
        assert not button(view,"Reset").isEnabled()
    finally: view.close()


@pytest.mark.parametrize("change", ["version", "source", "cutoff", "context", "stock"])
def test_identity_changes_reset_and_old_control_callback_is_ignored(app, tmp_path, change):
    *_, cfg, context = produce(tmp_path)
    original = reader(cfg).read_report("2330",as_of_date="2026-05-20",context=context)
    view = StockResearchReportView(SimpleNamespace())
    try:
        view._loaded_request_context = context
        render(view, original)
        button(view,"ZoomIn").click()
        old_button = button(view,"PanOlder")
        report = original
        payload_context = dict(original.research_context)
        if change == "version":
            # 同股另一個合法列版本：改精確價格並重算既有列指紋，改成live研究DTO。
            from app_module.stock_research_report_provider_adapters import stock_price_row_fingerprint_sha256
            points = list(original.price_points)
            point = replace(points[-1], close_price=Decimal("101.125"))
            point = replace(point,source_snapshot_hash=stock_price_row_fingerprint_sha256(stock_code="2330",data_date=point.data_date,
                open_price=point.open_price,high_price=point.high_price,low_price=point.low_price,close_price=point.close_price,
                volume=point.volume,turnover=point.turnover))
            points[-1] = point
            report = replace(report, price_points=tuple(points), saved_technical_chart_json="", technical_history=(),research_context={})
        elif change == "source":
            report = replace(report, saved_technical_chart_json="", technical_history=(), research_context={},
                             price_points=tuple(replace(p, source_id="other-source") for p in report.price_points),sources=())
        elif change == "cutoff":
            report = replace(report, as_of="2026-05-21",saved_technical_chart_json="",technical_history=(),research_context={})
        elif change == "context":
            payload_context["source_workspace"] = "watchlist"
            report = replace(report,research_context=payload_context)
        else:
            report = replace(report, stock_code="2317",saved_technical_chart_json="",technical_history=(),research_context={},sources=())
        view._loaded_request_context = None
        render(view, report)
        if view._chart_widget is not None:
            assert view._chart_viewport.range.is_full
            bounds = view._chart_viewport.range
            old_button.click()
            assert view._chart_viewport.range == bounds
        else:
            assert view._chart_viewport.range.count == 0
    finally:view.close()


def test_missing_slots_hover_and_ma_segments_share_original_dates(app):
    chart = StockPriceChartWidget()
    chart.resize(500,220)
    points = (StockPricePointDTO("2026-05-01",close_price=Decimal("10")),
              StockPricePointDTO("2026-05-03",close_price=None),
              StockPricePointDTO("2026-05-07",close_price=Decimal("20")))
    from app_module.stock_research_chart_payload import StockChartTechnicalLineDTO, StockChartTechnicalPointDTO
    line = StockChartTechnicalLineDTO("MA20","MA20",tuple(StockChartTechnicalPointDTO(p.data_date,Decimal("15")) for p in points))
    chart.set_points(points);chart.set_technical_lines((line,))
    left,right=chart._plot_x_bounds();middle=(left+right)//2
    assert chart._nearest_point_index(middle)==1
    chart.mouseMoveEvent(QMouseEvent(QEvent.MouseMove,QPointF(middle,70),QPointF(middle,70),Qt.NoButton,Qt.NoButton,Qt.NoModifier))
    assert "2026-05-03" in chart.toolTip() and "未提供" in chart.toolTip()
    assert chart._technical_segments(line)==(((0,Decimal("15")),),((2,Decimal("15")),))
    assert not chart.grab().isNull()
    chart.close()


def test_empty_and_unknown_versions_reset_no_stale_chart(app):
    view=StockResearchReportView(SimpleNamespace())
    try:
        report=StockResearchReportDTO("2330",as_of="2026-05-20",price_points=tuple(
            StockPricePointDTO(f"2026-05-{i:02d}",close_price=Decimal(i)) for i in range(1,6)))
        render(view,report);button(view,"ZoomIn").click();assert len(visible(view))<5
        render(view,report);assert len(visible(view))==5
        render(view,replace(report,price_points=()))
        assert not visible(view) and all(not button(view,k).isEnabled() for k in ("ZoomIn","ZoomOut","PanOlder","PanNewer","Reset"))
    finally:view.close()


def test_background_cancel_retry_preserves_window_same_saved_reopen_and_return(app,tmp_path):
    *_,cfg,context=produce(tmp_path)
    service=reader(cfg);original=service.read_report;hold=[False];started=Event()
    def controlled(*args,**kwargs):
        if hold[0]:
            started.set()
            while hold[0]:
                if kwargs["cancel_callback"]():raise StockResearchReportCancelled("合作取消")
                time.sleep(.01)
        return original(*args,**kwargs)
    service.read_report=controlled
    view=StockResearchReportView(service,context)
    try:
        _wait(app,lambda:view._loaded_report is not None and not view._workers)
        view.tabs.setCurrentIndex(1);app.processEvents();button(view,"ZoomIn").click()
        bounds=view._chart_viewport.range;report=view._loaded_report
        hold[0]=True;view.reload_button.click();_wait(app,started.is_set)
        request=view._request_id;view._cancel_active_worker();_wait(app,lambda:not view._workers)
        assert view._chart_viewport.range==bounds
        hold[0]=False;view.reload_button.click();_wait(app,lambda:not view._workers)
        assert view._chart_viewport.range==bounds and len(visible(view))==10
        view._on_report_loaded(request,"2330",replace(report,price_points=()),context)
        assert view._chart_viewport.range==bounds
        returned=[];view.returnRequested.connect(lambda:returned.append(view.context));view.return_button.click()
        assert returned==[context]
    finally:
        hold[0]=False;view.close();_wait(app,lambda:not view._workers)



def test_saved_reopen_new_view_starts_full_with_same_artifact(app,tmp_path):
    *_,cfg,context=produce(tmp_path)
    first=StockResearchReportView(reader(cfg),context)
    try:
        _wait(app,lambda:first._loaded_report is not None and not first._workers)
        first.tabs.setCurrentIndex(1);app.processEvents();button(first,"ZoomIn").click()
        chart_bytes=first._loaded_report.saved_technical_chart_json
        assert len(visible(first))==10
    finally:first.close();_wait(app,lambda:not first._workers)
    second=StockResearchReportView(reader(cfg),context)
    try:
        _wait(app,lambda:second._loaded_report is not None and not second._workers)
        second.tabs.setCurrentIndex(1);app.processEvents()
        assert second._loaded_report.saved_technical_chart_json==chart_bytes
        assert len(visible(second))==20 and second._chart_viewport.range.is_full
    finally:second.close();_wait(app,lambda:not second._workers)


def test_interaction_renderer_failure_keeps_complete_exact_table(app,tmp_path,monkeypatch):
    *_,cfg,context=produce(tmp_path)
    report=reader(cfg).read_report("2330",as_of_date="2026-05-20",context=context)
    view=StockResearchReportView(SimpleNamespace())
    view._loaded_request_context=context
    try:
        render(view,report)
        table=view.findChild(QTableView,"stockResearchPriceHistoryTable")
        def fail(*args):raise RuntimeError("隔離重畫失敗")
        monkeypatch.setattr(view._chart_widget,"set_points",fail)
        button(view,"ZoomIn").click()
        assert view._chart_widget is None and table.model().rowCount()==20
        assert "精確表仍完整" in view.findChildren(QLabel,"stockResearchChartViewportRange")[-1].text()
        assert not button(view,"ZoomIn").isEnabled()
    finally:view.close()



def test_b05_keyboard_crosshair_same_date_exact_table_and_focus(app):
    from PySide6.QtTest import QTest
    report = StockResearchReportDTO("2330", as_of="2026-05-20", price_points=tuple(
        StockPricePointDTO(f"2026-05-{i:02d}", close_price=Decimal(f"{i}.123456789")) for i in range(1,6)))
    view = StockResearchReportView(SimpleNamespace())
    try:
        render(view, report)
        chart=view._chart_widget
        table=view.findChild(QTableView,"stockResearchPriceHistoryTable")
        assert chart.focusPolicy()==Qt.StrongFocus
        QTest.keyClick(chart, Qt.Key_Home)
        assert chart._hover_index==0 and table.currentIndex().data()=="2026-05-01"
        assert "1.123456789" in chart.toolTip() and chart.accessibleDescription()==chart.toolTip()
        QTest.keyClick(chart, Qt.Key_Right)
        assert chart._hover_index==1 and table.currentIndex().data()=="2026-05-02"
        assert not chart.grab().isNull()
        QTest.keyClick(chart, Qt.Key_End)
        assert table.currentIndex().data()=="2026-05-05"
        for name in ("ZoomIn","ZoomOut","PanOlder","PanNewer","Reset"):
            assert button(view,name).focusPolicy()==Qt.StrongFocus
        QTest.keyClick(button(view,"ZoomIn"), Qt.Key_Space)
        assert len(visible(view)) < 5 and table.model().rowCount()==5
        QTest.keyClick(chart, Qt.Key_Home)
        assert table.currentIndex().data()==visible(view)[0].data_date
        QTest.keyClick(chart, Qt.Key_Escape)
        assert chart._hover_index is None
    finally: view.close()


def test_b05_typed_markers_scope_stale_and_viewport(app):
    from tests.test_baldr_b05_chart_markers import evidence
    from tests.test_stock_research_chart_payload import _point, _report
    marker,pin=evidence()
    report=_report(_point("2026-10-07"),_point("2026-10-08"))
    view=StockResearchReportView(SimpleNamespace())
    try:
        view.set_chart_marker_evidence((marker,),(pin,))
        render(view,report)
        chart=view._chart_widget
        assert chart._markers==(marker,)
        assert view.findChild(QTableView,"stockResearchChartMarkerTable").model().index(0,1).data()=="推薦確認（研究）"
        assert not chart.grab().isNull()
        changed=replace(report,research_context={**report.research_context,"result_id":"other"})
        render(view,changed)
        assert view._chart_widget._markers==()
        chart._select_point(1)
        tables=view.findChildren(QTableView,"stockResearchPriceHistoryTable")
        assert not tables[-1].currentIndex().isValid()
    finally:view.close()


def test_b05_external_reference_known_unknown_and_stale_callback(app,monkeypatch):
    from ui_qt.views import stock_research_report_view as module
    calls=[]
    monkeypatch.setattr(module.QDesktopServices,"openUrl",lambda url:calls.append(url.toString()) or True)
    view=StockResearchReportView(SimpleNamespace())
    try:
        report=StockResearchReportDTO("2382",as_of="2026-05-20",price_points=(StockPricePointDTO("2026-05-20",close_price=Decimal("10")),))
        render(view,report)
        external=view.findChildren(QPushButton,"stockResearchExternalChart")[-1]
        assert external.isEnabled()
        external.click()
        assert calls==["https://tw.tradingview.com/symbols/TWSE-2382/"]
        assert "外部價格" in external.toolTip()
        render(view,replace(report,stock_code="2330"))
        assert not view.findChildren(QPushButton,"stockResearchExternalChart")[-1].isEnabled()
        external.click()
        assert len(calls)==1
    finally:view.close()



def test_b05_research_and_actual_markers_same_day_stay_distinct(app):
    from app_module.stock_research_chart_markers import StockChartMarkerKind, stock_chart_marker_fingerprint
    from tests.test_baldr_b05_chart_markers import evidence
    from tests.test_stock_research_chart_payload import _point,_report
    markers=[];pins=[]
    for kind in StockChartMarkerKind:
        marker,pin=evidence(kind)
        marker=replace(marker,record_id=kind.value)
        marker=replace(marker,content_sha256=stock_chart_marker_fingerprint(marker))
        markers.append(marker);pins.append(replace(pin,record_id=kind.value))
    view=StockResearchReportView(SimpleNamespace())
    try:
        view.set_chart_marker_evidence(markers,pins)
        render(view,_report(_point("2026-10-08")))
        chart=view._chart_widget
        assert chart._markers==tuple(markers)
        chart._select_point(0)
        assert all(marker.label in chart.toolTip() for marker in markers)
        assert not chart.grab().isNull()
        assert view.findChild(QTableView,"stockResearchChartMarkerTable").model().rowCount()==3
    finally:view.close()
