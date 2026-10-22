"""研究圖表保留原始值、缺值語意及可讀性。"""

from decimal import Decimal

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import QApplication, QLabel, QScrollArea, QWidget

from ui_qt.theme import MIDNIGHT_ANALYST
from ui_qt.widgets.research_metric_chart import ResearchMetricBar, ResearchMetricChart


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_chart_preserves_exact_values_and_exposes_row_details_accessibly() -> None:
    _app()
    exact = Decimal("12345678901234567890.1234567890123456789")
    points = (
        ResearchMetricBar("外資淨買賣", exact, "資料日：2026-10-21；來源：官方法人資料"),
        ResearchMetricBar("投信淨買賣", Decimal("-25.50"), "資料日：2026-10-21"),
        ResearchMetricBar("自營商淨買賣", Decimal(0), "資料日：2026-10-21"),
        ResearchMetricBar("信用資料", None, "來源沒有此觀察值"),
    )
    chart = ResearchMetricChart("法人籌碼", "股", points, "同一資料日；缺值不補零")
    chart.resize(900, 320)
    chart.show()
    _app().processEvents()

    assert chart.points == points
    rows = chart.findChildren(QWidget, "researchMetricChartRow")
    assert len(rows) == 4
    assert rows[0].accessibleName() == "外資淨買賣"
    assert rows[0].accessibleDescription() == "資料日：2026-10-21；來源：官方法人資料"
    assert "12345678901234567890.1234567890123456789 股" in [
        label.text() for label in chart.findChildren(QLabel, "researchMetricChartValue")
    ]
    assert "缺值" in [
        label.text() for label in chart.findChildren(QLabel, "researchMetricChartValue")
    ]
    assert chart.findChildren(QWidget, "researchMetricChartBar")
    assert not chart.grab().isNull()
    chart.close()


def test_positive_and_negative_values_keep_sign_text_with_neutral_label_color() -> None:
    _app()
    chart = ResearchMetricChart(
        "法人淨額",
        "股",
        (
            ResearchMetricBar("外資淨額", Decimal("125"), "單日原觀測"),
            ResearchMetricBar("投信淨額", Decimal("-80"), "單日原觀測"),
        ),
    )
    chart.resize(800, 260)
    chart.show()
    _app().processEvents()

    values = chart.findChildren(QLabel, "researchMetricChartValue")
    bars = chart.findChildren(QWidget, "researchMetricChartBar")
    assert [label.text() for label in values] == ["125 股", "-80 股"]
    assert values[0].styleSheet() == values[1].styleSheet()
    assert f"color: {MIDNIGHT_ANALYST.text_primary}" in values[0].styleSheet()
    assert [bar.accessibleDescription() for bar in bars] == [
        "原始數值：125",
        "原始數值：-80",
    ]
    chart.close()


def test_empty_or_only_missing_points_show_missing_state_not_zero_bars() -> None:
    _app()
    for points in ((), (ResearchMetricBar("月營收", None, "單位未核"),)):
        chart = ResearchMetricChart("月營收", "TWD", points)
        assert chart.points == points
        assert chart.findChild(QLabel, "researchMetricChartMissing") is not None
        assert not chart.findChildren(QWidget, "researchMetricChartBar")
        chart.close()


def test_narrow_chart_reflows_without_horizontal_page_growth_and_keeps_value_visible() -> None:
    _app()
    chart = ResearchMetricChart(
        "集保級距",
        "%",
        (ResearchMetricBar("1–999 股", Decimal("1.25"), "資料日：2026-10-16"),),
    )
    chart.resize(360, 220)
    chart.show()
    _app().processEvents()

    scroll = chart.findChild(QScrollArea, "researchMetricChartScrollArea")
    assert scroll is not None
    assert scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    assert chart.width() == 360
    assert scroll.horizontalScrollBar().maximum() == 0
    value_label = chart.findChildren(QLabel, "researchMetricChartValue")[0]
    value_top_left = value_label.mapTo(scroll.viewport(), QPoint(0, 0))
    value_rect = QRect(value_top_left, value_label.size())
    assert value_label.isVisible()
    assert value_label.text() == "1.25 %"
    assert scroll.viewport().rect().intersects(value_rect)
    assert not chart.grab().isNull()
    chart.close()


def test_chart_limits_visible_rows_and_scrolls_long_series_vertically() -> None:
    _app()
    chart = ResearchMetricChart(
        "月營收",
        "TWD",
        tuple(ResearchMetricBar(f"2026-{month:02d}", Decimal(month), f"資料日：2026-{month:02d}-10")
              for month in range(1, 13)),
    )
    chart.resize(500, 900)
    chart.show()
    _app().processEvents()

    scroll = chart.findChild(QScrollArea, "researchMetricChartScrollArea")
    assert scroll is not None
    assert scroll.minimumHeight() == 516
    assert scroll.maximumHeight() == 516
    assert scroll.verticalScrollBar().maximum() > 0
    assert scroll.horizontalScrollBar().maximum() == 0
    chart.close()


def test_single_observation_is_a_value_card_without_a_normalized_full_bar() -> None:
    _app()
    chart = ResearchMetricChart("融資餘額", "交易單位", (ResearchMetricBar("融資餘額", Decimal(125)),))
    assert not chart.findChildren(QWidget, "researchMetricChartBar")
    assert any("不能判定趨勢" in label.text() for label in chart.findChildren(QLabel))
    chart.close()
