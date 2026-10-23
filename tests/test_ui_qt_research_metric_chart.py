"""研究圖表保留原始值、缺值語意及可讀性。"""

from decimal import Decimal

from PySide6.QtWidgets import QApplication, QLabel, QWidget

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
    chart = ResearchMetricChart(
        "法人籌碼", "股", points, "同一資料日；缺值不補零",
        detail_note="來源 official／v1｜品質原碼保留",
    )
    chart.resize(900, 320)
    chart.show()
    _app().processEvents()

    assert chart.points == points
    rows = chart.findChildren(QWidget, "researchMetricChartRow")
    assert len(rows) == 4
    assert rows[0].accessibleName() == "外資淨買賣"
    assert rows[0].accessibleDescription() == "外資淨買賣"
    assert "12345678901234567890.1234567890123456789 股" in [
        label.text() for label in chart.findChildren(QLabel, "researchMetricChartValue")
    ]
    assert "缺值" in [
        label.text() for label in chart.findChildren(QLabel, "researchMetricChartValue")
    ]
    assert chart.findChildren(QWidget, "researchMetricChartBar")
    details = chart.findChild(QWidget, "researchMetricChartDetails")
    assert details is not None and details.is_collapsed()
    exact_details = chart.findChildren(QLabel, "researchMetricChartExactDetail")
    assert "12345678901234567890.1234567890123456789 股" in exact_details[0].text()
    assert "來源：官方法人資料" in exact_details[0].text()
    assert chart.findChild(QLabel, "researchMetricChartSourceDetail").text() == "來源 official／v1｜品質原碼保留"
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


def test_narrow_chart_reflows_and_keeps_exact_value_visible_without_inner_scroll() -> None:
    _app()
    chart = ResearchMetricChart(
        "集保級距",
        "%",
        (ResearchMetricBar("1–999 股", Decimal("1.25"), "資料日：2026-10-16"),),
    )
    chart.resize(360, 220)
    chart.show()
    _app().processEvents()

    assert chart.width() == 360
    value_label = chart.findChildren(QLabel, "researchMetricChartValue")[0]
    assert value_label.isVisible()
    assert value_label.text() == "1.25 %"
    assert not chart.grab().isNull()
    chart.close()


def test_chart_keeps_all_long_series_rows_in_main_layout_without_fixed_inner_scroll() -> None:
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

    assert chart.findChild(QWidget, "researchMetricChartScrollArea") is None
    rows = chart.findChildren(QWidget, "researchMetricChartRow")
    assert len(rows) == 12
    assert all(row.isVisible() for row in rows)
    assert all(row.mapTo(chart, row.rect().bottomLeft()).y() <= chart.height() for row in rows)
    details = chart.findChild(QWidget, "researchMetricChartDetails")
    assert details is not None and details.is_collapsed()
    chart.close()


def test_month_columns_keep_calendar_gap_without_duplicate_bar_rows_and_details_are_collapsible() -> None:
    _app()
    points = (ResearchMetricBar("2026-01", Decimal("1.125"), "來源原值"),
              ResearchMetricBar("2026-03", Decimal("2"), "原始明細"))
    chart = ResearchMetricChart("月營收", "千元", points, orientation="column", periods=("2026-01", "2026-03"))
    plot = chart.findChild(QWidget, "researchMetricChartPlot")
    assert plot is not None
    assert plot._parse_period("2026-01") < plot._parse_period("2026-03")
    assert plot._parse_period("2026-01-15") is None
    assert plot._x_positions(365)[1] - plot._x_positions(365)[0] == 365
    assert chart.findChildren(QWidget, "researchMetricChartBar") == []
    assert chart.findChildren(QWidget, "researchMetricChartRow") == []
    details = chart.findChild(QWidget, "researchMetricChartDetails")
    assert details is not None and details.is_collapsed()
    details.toggle_button.click()
    assert not details.is_collapsed()
    assert [label.text() for label in chart.findChildren(QLabel, "researchMetricChartExactDetail")] == [
        "2026-01｜原值 1.125 千元｜來源原值",
        "2026-03｜原值 2 千元｜原始明細",
    ]
    chart.close()


def test_month_positions_follow_elapsed_calendar_days_and_invalid_periods_fall_back_to_categories() -> None:
    _app()
    from ui_qt.widgets.research_metric_chart import _PeriodColumnChart

    points = tuple(ResearchMetricBar(period, Decimal(index)) for index, period in enumerate(("2026-01", "2026-02", "2026-04"), 1))
    plot = _PeriodColumnChart(points, tuple(point.label for point in points), "TWD")
    positions = plot._x_positions(1000)
    assert positions[1] - positions[0] < positions[2] - positions[1]
    invalid = _PeriodColumnChart(points, ("2026-01", "2026-02-01", "2026-04"), "TWD")
    assert invalid._period_axis is False
    assert "不符合 YYYY-MM" in invalid.toolTip()


def test_positive_bar_uses_full_one_sided_scale_and_directional_colors_are_opt_in() -> None:
    _app()
    generic = ResearchMetricChart("餘額", "股", (ResearchMetricBar("x", Decimal(10)), ResearchMetricBar("y", Decimal(5))))
    directional = ResearchMetricChart("淨額", "股", (ResearchMetricBar("x", Decimal(10)), ResearchMetricBar("y", Decimal(-5))), directional=True)
    assert generic._signed is False
    assert directional._signed is True
    assert generic.directional is False and directional.directional is True
    generic.close()
    directional.close()


def test_single_observation_is_a_value_card_without_a_normalized_full_bar() -> None:
    _app()
    chart = ResearchMetricChart("融資餘額", "交易單位", (ResearchMetricBar("融資餘額", Decimal(125)),))
    assert not chart.findChildren(QWidget, "researchMetricChartBar")
    assert any("不能判定趨勢" in label.text() for label in chart.findChildren(QLabel))
    chart.close()


def test_single_month_column_keeps_exact_value_and_period_visible_without_a_trend_plot() -> None:
    _app()
    chart = ResearchMetricChart(
        "月營收", "千元", (ResearchMetricBar("月營收", Decimal("123.4500")),),
        orientation="column", periods=("2026-09",),
    )
    card = chart.findChild(QLabel, "researchMetricChartSingleColumnValue")
    assert card is not None
    assert "123.4500 千元" in card.text()
    assert "2026-09" in card.text()
    assert "不能判定趨勢" in card.text()
    assert chart.findChild(QWidget, "researchMetricChartPlot") is None
    assert chart.findChild(QWidget, "researchMetricChartDetails").is_collapsed()
    chart.close()


def test_paired_columns_keep_each_exact_original_value_in_visible_legend() -> None:
    _app()
    chart = ResearchMetricChart(
        "營收比較", "千元",
        (ResearchMetricBar("去年同期", Decimal("100.125")),
         ResearchMetricBar("本期", Decimal("123.4500"))),
        orientation="paired_column", periods=("去年同期", "本期"),
    )
    chart.resize(720, 340)
    chart.show()
    _app().processEvents()
    legend = chart.findChild(QLabel, "researchMetricChartPairedValues")
    assert legend is not None and legend.isVisibleTo(chart)
    assert "去年同期：100.125 千元" in legend.text()
    assert "本期：123.4500 千元" in legend.text()
    legend_bottom = legend.mapTo(chart, legend.rect().bottomLeft()).y()
    assert legend_bottom <= chart.height()
    assert not chart.grab().isNull()
    chart.close()


def test_narrow_month_and_paired_column_labels_render_inside_all_plot_edges() -> None:
    _app()
    from PySide6.QtCore import QRectF
    from ui_qt.widgets.research_metric_chart import _PeriodColumnChart

    cases = (
        _PeriodColumnChart(
            (ResearchMetricBar("2026-01", Decimal("1200")),
             ResearchMetricBar("2026-09", Decimal("1410"))),
            ("2026-01", "2026-09"), "千元",
        ),
        _PeriodColumnChart(
            (ResearchMetricBar("去年同期", Decimal("100")),
             ResearchMetricBar("本期", Decimal("120"))),
            ("去年同期", "本期"), "千元", paired=True,
        ),
    )
    for plot in cases:
        plot.resize(900, 210)
        plot.show()
        _app().processEvents()
        points = plot._points
        period_labels = plot._periods
        value_labels = [f"{format(point.value, 'f')} 千元" for point in points]
        margin, plot_width = plot._edge_label_layout(
            plot.width() - 16, (*period_labels, *value_labels)
        )
        x_positions = [8 + margin + x for x in plot._x_positions(plot_width)]
        area = QRectF(plot.rect()).adjusted(8, 30, -8, -34)
        for index, x in enumerate(x_positions):
            period_rect = plot._centered_label_rect(period_labels[index], x, area.bottom() + 4)
            value_rect = plot._centered_label_rect(value_labels[index], x, area.top() + 6)
            assert period_rect.left() >= 0 and period_rect.right() <= plot.width()
            assert period_rect.bottom() <= plot.height()
            assert value_rect.left() >= 0 and value_rect.right() <= plot.width()
            assert value_rect.top() >= 0
        assert not plot.grab().isNull()
        plot.close()
