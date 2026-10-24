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


def test_canvas_html_reports_tokenized_draw_state_after_sized_draw() -> None:
    html = _build_html(_equity_payload("Ready", 10), render_token="2:3")

    assert '<html data-chart-token="2:3" data-chart-state="pending">' in html
    assert "window.addEventListener('error'" in html
    assert "root.dataset.chartState = state" in html
    assert "canvas.clientWidth <= 0 || canvas.clientHeight <= 0" in html
    assert "canvas.width <= 0 || canvas.height <= 0" in html
    draw_body = html.split("function draw() {", 1)[1].split(
        "function drawChartFrame()", 1
    )[0]
    assert draw_body.index("canvas.width <= 0 || canvas.height <= 0") < draw_body.index(
        "drawChartFrame();"
    ) < draw_body.index("reportCanvasState('ready');")
    assert "reportCanvasState('error');" in draw_body


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
        self.javascript_scripts = []
        self.javascript_callbacks = []

    def setBackgroundColor(self, _color) -> None:
        pass

    def runJavaScript(self, source, callback) -> None:
        self.javascript_scripts.append(source)
        self.javascript_callbacks.append(callback)

    def take_javascript_callback(self):
        return self.javascript_callbacks.pop(0)


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


def _finish_document_and_capture_readiness(widget):
    widget.web_view.loadFinished.emit(True)
    assert widget._webengine_loading
    widget.web_view.loadFinished.emit(True)
    assert widget._readiness_pending
    return widget.web_view.page().take_javascript_callback()


def _capture_readiness_after_active_document(widget):
    widget.web_view.loadFinished.emit(True)
    assert widget._readiness_pending
    return widget.web_view.page().take_javascript_callback()


def _report_canvas_state(widget, state: str) -> None:
    token = widget._active_render_token
    callback = widget.web_view.page().take_javascript_callback()
    callback(f"{token}|{state}")


def test_fast_chart_exposes_loading_and_valid_empty_states(fast_chart) -> None:
    widget, _app = fast_chart

    assert not widget.status_label.isHidden()
    assert "載入中" in widget.status_label.text()
    assert "目前沒有可顯示的數值資料" in widget.numeric_text.text()

    widget.web_view.loadFinished.emit(True)

    assert "正在確認畫布繪製" in widget.status_label.text()
    _report_canvas_state(widget, "ready")

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

    assert "正在確認畫布繪製" in widget.status_label.text()
    _report_canvas_state(widget, "ready")
    assert "畫布繪製完成" in widget.status_label.text()


def test_fast_chart_load_failure_keeps_latest_values_and_retries(fast_chart) -> None:
    widget, _app = fast_chart
    latest = _equity_payload("待重試結果", 303)
    widget._set_payload(latest)
    # 初始頁取消後送出最新結果；最新結果本身再回報載入失敗。
    widget.web_view.loadFinished.emit(False)
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


def test_fast_chart_javascript_draw_error_is_visible_and_retryable(fast_chart) -> None:
    widget, _app = fast_chart
    widget._set_payload(_equity_payload("JS 失敗結果", 505))
    callback = _finish_document_and_capture_readiness(widget)

    callback(f"{widget._active_render_token}|error")

    assert "JavaScript 繪製失敗" in widget.status_label.text()
    assert not widget.retry_button.isHidden()
    assert "505" in widget.numeric_text.text()

    old_view = widget.web_view
    widget.retry_button.click()
    assert widget.web_view is old_view
    assert "JS 失敗結果" in widget.web_view.html_history[-1]
    assert "載入中" in widget.status_label.text()


def test_fast_chart_pending_readiness_times_out_as_unconfirmed_and_retries(fast_chart) -> None:
    widget, _app = fast_chart
    widget._set_payload(_equity_payload("逾時結果", 606))
    callback = _finish_document_and_capture_readiness(widget)
    generation = widget._webengine_generation
    sequence = widget._load_sequence
    token = widget._active_render_token

    callback(f"{token}|pending")
    widget._poll_canvas_readiness()
    late_callback = widget.web_view.page().take_javascript_callback()
    widget._on_canvas_readiness_timeout(generation, sequence)

    assert "無法確認畫布" in widget.status_label.text()
    assert "JavaScript 繪製失敗" not in widget.status_label.text()
    assert not widget.retry_button.isHidden()
    assert "606" in widget.numeric_text.text()

    previous_count = len(widget.web_view.html_history)
    widget.retry_button.click()
    assert len(widget.web_view.html_history) == previous_count + 1
    assert "逾時結果" in widget.web_view.html_history[-1]
    assert widget._load_sequence != sequence

    late_callback(f"{token}|ready")
    assert "載入中" in widget.status_label.text()
    assert "畫布繪製完成" not in widget.status_label.text()


def test_fast_chart_late_readiness_callback_cannot_replace_queued_latest(fast_chart) -> None:
    widget, _app = fast_chart
    widget._set_payload(_equity_payload("等待結果", 707))
    old_callback = _finish_document_and_capture_readiness(widget)
    old_token = widget._active_render_token
    widget._set_payload(_equity_payload("最新結果", 808))

    old_callback(f"{old_token}|ready")

    assert "最新結果" in widget.web_view.html_history[-1]
    assert "載入中" in widget.status_label.text()
    new_sequence = widget._load_sequence
    old_callback(f"{old_token}|error")
    assert widget._load_sequence == new_sequence
    assert "載入中" in widget.status_label.text()

    callback = _capture_readiness_after_active_document(widget)
    callback(f"{widget._active_render_token}|ready")
    assert "畫布繪製完成" in widget.status_label.text()


def test_fast_chart_closed_widget_ignores_pending_readiness_callback(fast_chart) -> None:
    widget, _app = fast_chart
    widget._set_payload(_equity_payload("關閉結果", 909))
    callback = _finish_document_and_capture_readiness(widget)
    prior_status = widget.status_label.text()

    widget.close()
    widget.web_view.loadFinished.emit(True)
    callback(f"{widget._active_render_token}|ready")

    assert widget.status_label.text() == prior_status
    assert widget._widget_closed


def test_fast_chart_reopens_with_latest_payload_and_new_callback_guard(fast_chart) -> None:
    widget, _app = fast_chart
    widget._set_payload(_equity_payload("重開結果", 919))
    old_callback = _finish_document_and_capture_readiness(widget)
    old_token = widget._active_render_token
    previous_count = len(widget.web_view.html_history)

    widget.close()
    widget.show()

    assert not widget._widget_closed
    assert widget._callback_guard["alive"]
    assert len(widget.web_view.html_history) == previous_count + 1
    assert "重開結果" in widget.web_view.html_history[-1]
    assert "載入中" in widget.status_label.text()

    old_callback(f"{old_token}|ready")
    assert "載入中" in widget.status_label.text()


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
    callback = _capture_readiness_after_active_document(widget)
    callback(f"{widget._active_render_token}|ready")
    assert "畫布繪製完成" in widget.status_label.text()
