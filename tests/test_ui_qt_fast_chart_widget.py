"""Fast canvas 圖表的 hover 文案與 HTML 輸出契約。"""

from ui_qt.widgets.fast_chart_widget import (
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
