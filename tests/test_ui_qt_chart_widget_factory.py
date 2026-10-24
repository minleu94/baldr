from datetime import datetime
from types import SimpleNamespace

import matplotlib
from matplotlib.figure import Figure

from ui_qt.theme import MIDNIGHT_ANALYST
import ui_qt.widgets.chart_widget as chart_widget_module
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


def test_mplcursors_buy_and_sell_annotations_use_dark_palette_and_keep_text(
    monkeypatch,
):
    cursors = []

    class _Cursor:
        def __init__(self):
            self.add_callback = None

        def connect(self, event, callback):
            assert event == "add"
            self.add_callback = callback

    def cursor(_artist, *, hover):
        assert hover is True
        result = _Cursor()
        cursors.append(result)
        return result

    class _Bbox:
        def __init__(self):
            self.facecolor = None
            self.edgecolor = None

        def set_facecolor(self, color):
            self.facecolor = color

        def set_edgecolor(self, color):
            self.edgecolor = color

    class _Annotation:
        def __init__(self):
            self.text = ""
            self.color = None
            self.bbox = _Bbox()

        def set_text(self, value):
            self.text = value

        def set_color(self, value):
            self.color = value

        def get_bbox_patch(self):
            return self.bbox

    monkeypatch.setattr(chart_widget_module, "HAS_MPLCURSORS", True)
    monkeypatch.setattr(
        chart_widget_module,
        "mplcursors",
        SimpleNamespace(cursor=cursor),
    )
    chart = SimpleNamespace(
        _buy_meta={
            0: {
                "date": datetime(2026, 10, 22),
                "price": 123.45,
                "shares": 2,
                "tags": "entry",
            }
        },
        _sell_meta={
            0: {
                "date": datetime(2026, 10, 23),
                "price": 125.00,
                "shares": 2,
                "profit": 3.10,
                "return_pct": 1.25,
                "holding_days": 4,
                "tags": "exit",
            }
        },
        _mplcursors_handles=[],
    )

    chart_widget_module.EquityCurveWidget._enable_hover_tooltip(
        chart,
        equity_series=None,
        benchmark_normalized=None,
        buy_scatter=object(),
        sell_scatter=object(),
    )

    assert len(cursors) == 2
    expected_texts = (
        "BUY @ 2026-10-22\nBuy Price: $123.45\nShares: 2\nTags: entry",
        "SELL @ 2026-10-23\nSell Price: $125.00\nShares: 2\n"
        "Profit: $3.10\nReturn%: 1.25%\nHolding Days: 4\nTags: exit",
    )
    for cursor_item, expected_text in zip(cursors, expected_texts):
        annotation = _Annotation()
        selection = SimpleNamespace(
            target=SimpleNamespace(index=0),
            annotation=annotation,
        )
        cursor_item.add_callback(selection)

        assert annotation.text == expected_text
        assert annotation.color == MIDNIGHT_ANALYST.text_primary
        assert annotation.bbox.facecolor == MIDNIGHT_ANALYST.surface_3
        assert annotation.bbox.edgecolor == MIDNIGHT_ANALYST.border
    assert len(chart._mplcursors_handles) == 2


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
