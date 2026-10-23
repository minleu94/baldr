"""圖卡沿原保存報告呈現，切換及降級不得損失原表。"""

from decimal import Decimal
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication, QLabel, QTableView, QToolButton

from app_module.stock_research_report_dtos import StockMetricDTO, StockResearchReportDTO
from ui_qt.views.stock_research_report_view import StockResearchReportView
from ui_qt.widgets.research_metric_chart import ResearchMetricChart


def test_ownership_chart_is_same_report_and_missing_next_report_clears_it():
    app = QApplication.instance() or QApplication([])
    view = StockResearchReportView(SimpleNamespace())
    report = StockResearchReportDTO(stock_code="2330", institutional=(
        StockMetricDTO("foreign", "外資淨買賣", Decimal("-1200"), unit="股",
                       data_as_of="2026-10-21", source_id="official"),))
    view._render_flows(report)
    charts = view.findChildren(ResearchMetricChart)
    assert len(charts) == 1
    assert charts[0].points[0].value == report.institutional[0].value
    assert view.findChildren(QTableView)
    view.show()
    assert view.focus_section("flows")
    app.processEvents()
    details = view.findChild(QToolButton, "stockResearchFlowDetailsToggle")
    assert details is not None and not details.isChecked()
    details.setChecked(True)
    app.processEvents()
    assert charts[0].isVisibleTo(view)

    view._render_flows(StockResearchReportDTO(stock_code="2317"))
    app.processEvents()
    assert all(not chart.isVisibleTo(view) for chart in charts)
    visible_text = "\n".join(
        label.text() for label in view.findChildren(QLabel) if label.isVisibleTo(view)
    )
    assert "外資淨買賣" not in visible_text
    assert "-1,200" not in visible_text
    app.processEvents()
    view.close()


def test_chart_construction_failure_retains_original_ownership_table(monkeypatch):
    app = QApplication.instance() or QApplication([])
    view = StockResearchReportView(SimpleNamespace())
    def fail(*args, **kwargs):
        raise RuntimeError("繪圖不可用")
    monkeypatch.setattr("ui_qt.views.stock_research_report_view.ResearchMetricChart", fail)
    view._render_flows(StockResearchReportDTO(stock_code="2330", institutional=(
        StockMetricDTO("foreign", "外資淨買賣", Decimal("123"), unit="股",
                       data_as_of="2026-10-21", source_id="official"),)))
    assert any("圖卡暫時無法顯示" in item.text() for item in view.findChildren(QLabel))
    assert view.findChildren(QTableView)
    app.processEvents()
    view.close()
