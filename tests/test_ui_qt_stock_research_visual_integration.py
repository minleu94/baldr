"""圖卡沿原保存報告呈現，切換及降級不得損失原表。"""

from decimal import Decimal
from dataclasses import replace
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication, QLabel, QTableView, QToolButton, QWidget

from app_module.stock_research_report_dtos import (
    StockFundamentalObservationDTO,
    StockMetricDTO,
    StockResearchReportDTO,
)
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


def _monthly_revenue_report() -> StockResearchReportDTO:
    first = StockFundamentalObservationDTO(
        kind="monthly_revenue",
        label="月營收",
        metric_name="revenue",
        market="TWSE",
        period="2026-01",
        as_of_date="2026-02-10",
        available_at="2026-02-11T08:00:00+08:00",
        value=Decimal("1000"),
        unit="千元",
        source_id="official.monthly_revenue",
        source_version="v1",
        period_basis="single_month",
        basis_verified=True,
    )
    second = replace(
        first,
        period="2026-02",
        as_of_date="2026-03-10",
        available_at="2026-03-11T08:00:00+08:00",
        value=Decimal("1200"),
    )
    return StockResearchReportDTO(stock_code="2330", fundamentals=(first, second))


def test_fully_charted_monthly_revenue_table_starts_collapsed_and_can_expand():
    app = QApplication.instance() or QApplication([])
    view = StockResearchReportView(SimpleNamespace())
    report = _monthly_revenue_report()

    view._render_fundamental(report)

    toggle = view.findChild(QToolButton, "fundamentalMonthlyRevenueTableToggle")
    details = view.findChild(QWidget, "fundamentalMonthlyRevenueTableDetails")
    table = view.findChild(QTableView, "fundamentalMonthlyRevenueTable")
    charts = view.findChildren(ResearchMetricChart)
    assert toggle is not None and not toggle.isChecked()
    assert details is not None and details.isHidden()
    assert table is not None and table.model().rowCount() == 2
    assert len(charts) == 1 and charts[0].orientation == "column"

    toggle.setChecked(True)
    assert not details.isHidden()
    assert toggle.text().startswith("收合逐筆月營收原值")
    toggle.setChecked(False)
    assert details.isHidden()
    app.processEvents()
    view.close()


def test_monthly_revenue_table_remains_visible_when_source_series_are_split():
    app = QApplication.instance() or QApplication([])
    view = StockResearchReportView(SimpleNamespace())
    report = _monthly_revenue_report()
    alternate = replace(
        report.fundamentals[1],
        period="2026-03",
        source_version="v2",
        value=Decimal("1500"),
    )

    view._render_fundamental(
        replace(report, fundamentals=(*report.fundamentals, alternate))
    )

    assert view.findChild(QToolButton, "fundamentalMonthlyRevenueTableToggle") is None
    table = view.findChild(QTableView, "fundamentalMonthlyRevenueTable")
    assert table is not None and not table.isHidden()
    assert table.model().rowCount() == 3
    app.processEvents()
    view.close()


def test_monthly_revenue_table_remains_visible_when_chart_construction_fails(monkeypatch):
    app = QApplication.instance() or QApplication([])
    view = StockResearchReportView(SimpleNamespace())

    def fail(*args, **kwargs):
        raise RuntimeError("繪圖不可用")

    monkeypatch.setattr("ui_qt.views.stock_research_report_view.ResearchMetricChart", fail)
    view._render_fundamental(_monthly_revenue_report())

    assert view.findChild(QToolButton, "fundamentalMonthlyRevenueTableToggle") is None
    assert any(
        "圖卡暫時無法顯示" in label.text()
        for label in view.findChildren(QLabel)
    )
    table = view.findChild(QTableView, "fundamentalMonthlyRevenueTable")
    assert table is not None and not table.isHidden()
    app.processEvents()
    view.close()
