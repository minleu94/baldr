import matplotlib
from matplotlib.figure import Figure

from ui_qt.theme import MIDNIGHT_ANALYST
from ui_qt.widgets.chart_widget import (
    DrawdownCurveWidget,
    EquityCurveWidget,
    HoldingDaysHistogramWidget,
    TradeReturnHistogramWidget,
)
from ui_qt.widgets.chart_widget import _apply_dark_chart_theme
from ui_qt.widgets.fast_chart_widget import (
    FastDrawdownCurveWidget,
    FastEquityCurveWidget,
    FastHoldingDaysHistogramWidget,
    FastTradeReturnHistogramWidget,
    select_drawdown_curve_widget_class,
    select_equity_curve_widget_class,
    select_holding_days_histogram_widget_class,
    select_trade_return_histogram_widget_class,
    _load_webengine_payload,
)


def test_select_equity_curve_widget_class_uses_fast_widget_when_available():
    selected = select_equity_curve_widget_class(prefer_fast=True, webengine_available=True)

    assert selected is FastEquityCurveWidget


def test_select_equity_curve_widget_class_falls_back_when_disabled():
    selected = select_equity_curve_widget_class(prefer_fast=False, webengine_available=True)

    assert selected is EquityCurveWidget


def test_select_equity_curve_widget_class_falls_back_without_webengine():
    selected = select_equity_curve_widget_class(prefer_fast=True, webengine_available=False)

    assert selected is EquityCurveWidget


def test_select_remaining_chart_classes_use_fast_widgets_when_available():
    assert select_drawdown_curve_widget_class(prefer_fast=True, webengine_available=True) is FastDrawdownCurveWidget
    assert (
        select_trade_return_histogram_widget_class(prefer_fast=True, webengine_available=True)
        is FastTradeReturnHistogramWidget
    )
    assert (
        select_holding_days_histogram_widget_class(prefer_fast=True, webengine_available=True)
        is FastHoldingDaysHistogramWidget
    )


def test_select_remaining_chart_classes_fall_back_without_webengine():
    assert select_drawdown_curve_widget_class(prefer_fast=True, webengine_available=False) is DrawdownCurveWidget
    assert (
        select_trade_return_histogram_widget_class(prefer_fast=True, webengine_available=False)
        is TradeReturnHistogramWidget
    )
    assert (
        select_holding_days_histogram_widget_class(prefer_fast=True, webengine_available=False)
        is HoldingDaysHistogramWidget
    )


def test_dark_chart_theme_is_local_to_figure_and_does_not_mutate_matplotlib_rcparams():
    class _Canvas:
        def __init__(self):
            self.style = ""
            self.draw_count = 0

        def setStyleSheet(self, style):
            self.style = style

        def draw(self):
            self.draw_count += 1

    before = matplotlib.rcParams.copy()
    figure = Figure()
    axes = figure.add_subplot(111)
    axes.set_title("權益")
    canvas = _Canvas()

    _apply_dark_chart_theme(figure, canvas)

    assert matplotlib.rcParams == before
    assert figure.get_facecolor()[:3] == matplotlib.colors.to_rgb(MIDNIGHT_ANALYST.app_bg)
    assert axes.get_facecolor()[:3] == matplotlib.colors.to_rgb(MIDNIGHT_ANALYST.surface_1)
    assert axes.title.get_color() == MIDNIGHT_ANALYST.text_primary
    assert MIDNIGHT_ANALYST.surface_1 in canvas.style
    assert canvas.draw_count == 1


def test_fast_chart_page_and_initial_empty_html_have_local_dark_background():
    class _Page:
        def __init__(self):
            self.background = None

        def setBackgroundColor(self, color):
            self.background = color

    class _WebView:
        def __init__(self):
            self.style = ""
            self._page = _Page()
            self.html = ""

        def setStyleSheet(self, style):
            self.style = style

        def page(self):
            return self._page

        def setHtml(self, value):
            self.html = value

    web_view = _WebView()
    _load_webengine_payload(web_view, {"kind": "empty", "title": "Chart"})

    assert web_view.page().background.name() == MIDNIGHT_ANALYST.app_bg
    assert MIDNIGHT_ANALYST.app_bg in web_view.style
    assert "background: #0b1020" in web_view.html
    assert "No chart data" in web_view.html

    _load_webengine_payload(
        web_view,
        {"kind": "lineArea", "title": "權益", "equity": [{"time": "2026-01-01", "value": 1000}]},
    )
    assert web_view.page().background.name() == MIDNIGHT_ANALYST.app_bg
    assert '"value": 1000' in web_view.html
    assert "<script src=" not in web_view.html
