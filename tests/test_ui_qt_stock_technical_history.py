"""原生 MA 覆蓋線的精度、斷線、幾何與表格替代驗證。"""
from dataclasses import replace
from datetime import date
from decimal import Decimal
import sqlite3
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QTableView

from app_module.stock_research_chart_payload import (
    StockChartTechnicalLineDTO, StockChartTechnicalPointDTO,
    project_stock_chart_payload,
)
from app_module.stock_research_report_dtos import StockPricePointDTO, StockResearchReportDTO
from app_module.stock_research_report_service import StockResearchReportReadService
from ui_qt.views.stock_research_report_view import StockPriceChartWidget, StockResearchReportView


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    yield instance


def _prices():
    return tuple(StockPricePointDTO(f"2026-09-0{i}", close_price=Decimal(str(i))) for i in range(1, 5))


def _line():
    return StockChartTechnicalLineDTO("MA20", "MA20", tuple(
        StockChartTechnicalPointDTO(point.data_date, value)
        for point, value in zip(_prices(), (Decimal("1.123456789123456789"), None, Decimal("3"), Decimal("4")))
    ))


def test_native_history_breaks_at_missing_value_and_preserves_geometry(app):
    chart = StockPriceChartWidget()
    chart.resize(700, 220)
    chart.set_points(_prices())
    chart._hover_index = 2
    geometry, mode = chart.geometry(), chart.display_mode
    chart.set_technical_lines((_line(),))
    assert chart.geometry() == geometry and chart.display_mode == mode
    assert chart._hover_index == 2
    assert chart._points == _prices()
    assert chart._technical_segments(_line()) == (
        ((0, Decimal("1.123456789123456789")),),
        ((2, Decimal("3")), (3, Decimal("4"))),
    )
    assert "1.123456789123456789" in chart._technical_tooltip("2026-09-01")
    assert "未提供" in chart._technical_tooltip("2026-09-02")
    assert not chart.grab().isNull()
    chart.close()


def test_native_missing_price_breaks_history_and_new_stock_clears_overlay(app):
    chart = StockPriceChartWidget()
    points = list(_prices())
    points[1] = replace(points[1], close_price=None)
    chart.set_points(points)
    line = StockChartTechnicalLineDTO("MA60", "MA60", tuple(
        StockChartTechnicalPointDTO(point.data_date, Decimal("2")) for point in points
    ))
    chart.set_technical_lines((line,))
    assert len(chart._technical_segments(line)) == 2
    chart.set_points((StockPricePointDTO("2026-09-04", close_price=Decimal("9")),))
    assert chart._technical_lines == () and chart._hover_index is None
    chart.close()


@pytest.mark.parametrize("fail", [False, True])
def test_history_table_uses_same_exact_projection_even_when_chart_fails(app, monkeypatch, fail):
    report = StockResearchReportDTO("2330", as_of="2026-09-04", price_points=_prices())
    result = project_stock_chart_payload(report)
    assert result.payload is not None
    result = replace(result, payload=replace(result.payload, technical_lines=(_line(),)))
    monkeypatch.setattr("ui_qt.views.stock_research_report_view.project_stock_chart_payload", lambda *a, **k: result)
    if fail:
        def failed(*_args):
            raise RuntimeError("overlay unavailable")
        monkeypatch.setattr(StockPriceChartWidget, "set_technical_lines", failed)
    view = StockResearchReportView(SimpleNamespace())
    view._active_code = "2330"
    view._render_price(report)
    table = view.findChild(QTableView, "stockResearchTechnicalHistoryTable")
    assert table is not None
    model = table.model()
    assert model.rowCount() == 4
    assert model.index(3, 1).data() == "1.123456789123456789"
    assert model.index(2, 1).data() == "—（未提供）"
    assert model.index(0, 2).data() == "—（未提供）"
    if fail:
        assert view.findChild(QLabel, "stockResearchPriceChartFallback") is not None
    view.close()


def test_snapshot_only_does_not_draw_or_construct_history_table(app):
    report = StockResearchReportDTO("2330", as_of="2026-09-04", price_points=_prices())
    view = StockResearchReportView(SimpleNamespace())
    view._active_code = "2330"
    view._render_price(report)
    assert view.findChild(QTableView, "stockResearchTechnicalHistoryTable") is None
    assert "不以單日快照" in view.findChild(QLabel, "stockResearchTechnicalHistoryStatus").text()
    view.close()


def test_isolated_sqlite_history_reaches_native_chart_and_exact_table(app, tmp_path):
    database = tmp_path / "market.sqlite"
    with sqlite3.connect(database) as conn:
        conn.execute("CREATE TABLE daily_prices (日期 TEXT, 證券代號 TEXT, 收盤價 TEXT)")
        conn.execute("CREATE TABLE technical_indicators (日期 TEXT, 證券代號 TEXT, MA20 TEXT, MA60 TEXT)")
        conn.executemany("INSERT INTO daily_prices VALUES (?, '2330', ?)", [
            (f"2026-09-0{i}", str(i)) for i in range(1, 6)
        ])
        conn.executemany("INSERT INTO technical_indicators VALUES (?, '2330', ?, ?)", [
            ("2026-09-01", "1.123456789123456789", None),
            ("2026-09-03", "3", "2"),
            ("2026-09-04", "4", "3"),
            ("2026-09-05", "999", "999"),
        ])
    service = StockResearchReportReadService(SimpleNamespace(db_file=database, output_root=tmp_path / "output"))
    report = service.read_report("2330", as_of_date=date(2026, 9, 4))
    assert len(report.technical_history) == 3
    view = StockResearchReportView(service)
    view._active_code = "2330"
    view._render_price(report)
    chart = view.findChild(StockPriceChartWidget)
    assert chart is not None and len(chart._technical_lines) == 2
    assert len(chart._technical_segments(chart._technical_lines[0])) == 2
    assert all(point.data_date <= "2026-09-04" for point in chart._points)
    table = view.findChild(QTableView, "stockResearchTechnicalHistoryTable")
    assert table is not None
    model = table.model()
    assert model.index(3, 1).data() == "1.123456789123456789"
    assert model.index(2, 1).data() == "—（未提供）"
    assert "sqlite.technical_indicators" in model.index(3, 1).data(Qt.ToolTipRole)
    assert report.technical_history[0].source_row_hash in model.index(3, 1).data(Qt.ToolTipRole)
    assert "999" not in chart._technical_tooltip("2026-09-04")
    assert not chart.grab().isNull()
    view.close()
