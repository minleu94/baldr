"""Fast canvas 圖表 hover 文案、載入狀態與 HTML 輸出契約。"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QWidget

from ui_qt.widgets.fast_chart_widget import (
    FastEquityCurveWidget,
    _build_html,
    _hover_tooltip_semantics,
)


def test_equity_hover_uses_chinese_label_without_assuming_currency() -> None:
    payload = {
        "title": "Equity Curve",
        "equity": [{"time": "2026-10-01", "value": 12345.67}],
        "benchmark": [],
        "markers": [],
    }

    assert _hover_tooltip_semantics(payload) == ("策略淨值", "")
    html = _build_html(payload)
    assert 'const hoverLabel = "策略淨值";' in html
    assert 'const hoverSuffix = "";' in html
    assert "const prefix = payload.equity" not in html
    assert "tooltip.textContent =" in html


def test_drawdown_hover_adds_percent_suffix_without_changing_value() -> None:
    payload = {
        "kind": "lineArea",
        "title": "Drawdown Curve",
        "yLabel": "Drawdown (%)",
        "series": [{"time": "2026-10-01", "value": -2.5}],
    }

    assert _hover_tooltip_semantics(payload) == ("回撤", "%")
    html = _build_html(payload)
    assert 'const hoverLabel = "回撤";' in html
    assert 'const hoverSuffix = "%";' in html
    assert "point.value.toLocaleString(undefined, {maximumFractionDigits: 2})" in html
    assert "${value}${hoverSuffix}" in html


def test_other_line_area_payload_does_not_reuse_drawdown_unit() -> None:
    payload = {
        "kind": "lineArea",
        "title": "Other Series",
        "yLabel": "Count",
        "series": [{"time": "2026-10-01", "value": 7}],
    }

    assert _hover_tooltip_semantics(payload) == ("Count", "")


def test_chart_title_stays_escaped_in_canvas_accessible_label() -> None:
    html = _build_html({"title": '策略" onmouseover="alert(1)', "equity": []})

    assert 'aria-label="策略&quot; onmouseover=&quot;alert(1)' in html
    assert 'aria-label="策略" onmouseover="alert(1)' not in html


class _FakeSignal:
    def __init__(self) -> None:
        self._callbacks = []

    def connect(self, callback) -> None:
        self._callbacks.append(callback)

    def emit(self, *args) -> None:
        for callback in tuple(self._callbacks):
            callback(*args)


class _FakePage:
    def __init__(self) -> None:
        self.renderProcessTerminated = _FakeSignal()

    def setBackgroundColor(self, _color) -> None:
        pass


class _FakeWebEngineView(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.loadStarted = _FakeSignal()
        self.loadFinished = _FakeSignal()
        self._page = _FakePage()
        self.html_history = []

    def page(self):
        return self._page

    def setHtml(self, content: str) -> None:
        self.html_history.append(content)
        self.loadStarted.emit()


@pytest.fixture
def fast_chart(monkeypatch):
    import ui_qt.widgets.fast_chart_widget as chart_module

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(chart_module, "HAS_QTWEBENGINE", True)
    monkeypatch.setattr(chart_module, "QWebEngineView", _FakeWebEngineView)
    widget = FastEquityCurveWidget()
    yield widget, app
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def _equity_payload(title: str, value: int) -> dict:
    return {
        "title": title,
        "equity": [{"time": "2026-10-01", "value": value}],
        "benchmark": [],
        "markers": [],
    }


def test_fast_chart_exposes_loading_and_valid_empty_states(fast_chart) -> None:
    widget, _app = fast_chart

    assert not widget.status_label.isHidden()
    assert "載入中" in widget.status_label.text()
    assert "目前沒有可顯示的數值資料" in widget.numeric_text.text()

    widget.web_view.loadFinished.emit(True)

    assert not widget.status_label.isHidden()
    assert "目前沒有可繪製的圖表資料" in widget.status_label.text()
    assert widget.retry_button.isHidden()


def test_fast_chart_coalesces_updates_until_active_load_finishes(fast_chart) -> None:
    widget, _app = fast_chart
    first = _equity_payload("較早結果", 101)
    latest = _equity_payload("最新結果", 202)

    assert len(widget.web_view.html_history) == 1
    widget._set_payload(first)
    widget._set_payload(latest)
    assert len(widget.web_view.html_history) == 1
    assert "202" in widget.numeric_text.text()

    # 初始化空頁即使以取消訊號結束，也只送出最新 payload，不誤報載入失敗。
    widget.web_view.loadFinished.emit(False)

    assert len(widget.web_view.html_history) == 2
    assert "最新結果" in widget.web_view.html_history[-1]
    assert "較早結果" not in widget.web_view.html_history[-1]
    assert not widget.status_label.isHidden()
    assert "載入中" in widget.status_label.text()
    assert "載入失敗" not in widget.status_label.text()

    widget.web_view.loadFinished.emit(True)

    assert "文件載入完成" in widget.status_label.text()
    assert "畫布已成功" not in widget.status_label.text()


def test_fast_chart_load_failure_keeps_latest_values_and_retries(fast_chart) -> None:
    widget, _app = fast_chart
    latest = _equity_payload("待重試結果", 303)
    widget._set_payload(latest)
    widget.web_view.loadFinished.emit(True)
    assert widget._webengine_loading
    assert "待重試結果" in widget.web_view.html_history[-1]

    widget.web_view.loadFinished.emit(False)

    assert "載入失敗" in widget.status_label.text()
    assert not widget.retry_button.isHidden()
    assert "303" in widget.numeric_text.text()
    # 重複／遲到的完成訊號不能清掉已顯示的失敗態。
    widget.web_view.loadFinished.emit(True)
    assert "載入失敗" in widget.status_label.text()

    previous_load_count = len(widget.web_view.html_history)
    widget.retry_button.click()

    assert len(widget.web_view.html_history) == previous_load_count + 1
    assert "待重試結果" in widget.web_view.html_history[-1]
    assert "載入中" in widget.status_label.text()
    assert widget.retry_button.isHidden()


def test_fast_chart_renderer_termination_is_visible_and_retryable(fast_chart) -> None:
    widget, _app = fast_chart
    latest = _equity_payload("Renderer 結果", 404)
    widget._set_payload(latest)
    widget.web_view.loadFinished.emit(True)

    terminated_view = widget.web_view
    terminated_view.page().renderProcessTerminated.emit("crashed", 1)

    assert "呈現程序已停止" in widget.status_label.text()
    assert not widget.retry_button.isHidden()
    assert "404" in widget.numeric_text.text()

    # Renderer 終止後的失敗完成訊號不能覆蓋較明確的終止狀態。
    terminated_view.loadFinished.emit(False)
    assert "呈現程序已停止" in widget.status_label.text()

    widget.retry_button.click()
    assert widget.web_view is not terminated_view
    # 重試建立新 view；舊 view 遲到的 finish 不得蓋掉新載入狀態。
    terminated_view.loadFinished.emit(False)
    assert "載入中" in widget.status_label.text()
    assert "Renderer 結果" in widget.web_view.html_history[-1]
    widget.web_view.loadFinished.emit(True)
    assert "文件載入完成" in widget.status_label.text()
