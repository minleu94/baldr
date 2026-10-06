"""K 線 hover 保留價量／事件，來源驗證與保存讀回維持原契約。"""
from decimal import Decimal
import hashlib

import pytest
from PySide6.QtWidgets import QApplication

from app_module.saved_stock_technical_chart import SavedTechnicalChartError, read_saved_technical_chart
from app_module.stock_research_chart_payload import (
    StockChartTechnicalLineDTO, StockChartTechnicalPointDTO, project_stock_chart_payload,
)
from app_module.stock_research_report_dtos import StockPricePointDTO
from tests.test_baldr_b05_chart_markers import evidence
from tests.test_saved_stock_technical_chart import _produce, _reader, DAY
from ui_qt.views.stock_research_report_view import StockPriceChartWidget, _price_point_source_tooltip


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


def _assert_no_audit(text):
    for token in ("來源：", "可得時間", "SHA-256", "SHA256", "source_id", "available_at"):
        assert token not in text


def test_hover_exact_date_price_volume_ma_and_marker_meaning(app):
    marker, _pin = evidence()
    day = marker.event_date
    points = (
        StockPricePointDTO(data_date="2026-10-07", close_price=None),
        StockPricePointDTO(data_date=day, open_price=Decimal("100.123456789"),
            high_price=Decimal("104"), low_price=Decimal("99"), close_price=Decimal("102"),
            volume=1234567, source_id="sqlite.daily_prices", source_snapshot_hash="a" * 64,
            available_at="2026-10-08T15:00:00+08:00"),
    )
    technical = StockChartTechnicalPointDTO(data_date=day, value=Decimal("101.123456789"),
        source_id="sqlite.technical_indicators", source_row_hash="b" * 64,
        available_at="2026-10-08T15:00:00+08:00")
    chart = StockPriceChartWidget()
    try:
        chart.resize(600, 250)
        chart.set_points(points)
        chart.set_technical_lines((StockChartTechnicalLineDTO("ma20", "MA20", (technical,)),))
        chart.set_markers((marker,))
        selected = []
        chart.dateSelected.connect(selected.append)
        left, right = chart._plot_x_bounds()
        assert chart._nearest_point_index(left) == 0
        assert chart._nearest_point_index(right) == 1
        chart._select_point(1)
        text = chart.toolTip()
        assert selected == [day]
        assert f"資料日：{day}" in text
        assert "開：100.123456789｜高：104｜低：99｜收：102" in text
        assert "成交量：1,234,567" in text
        assert "MA20：101.123456789" in text
        assert marker.label in text and f"帳本：{marker.account_id}" in text
        _assert_no_audit(text)
        assert text in chart.accessibleDescription()
        assert "資料範圍：" in chart.accessibleDescription()
        assert chart._points == points and chart._technical_lines[0].points == (technical,)
        assert "資料列 SHA-256：" in _price_point_source_tooltip(points[1])
        chart._select_point(0)
        assert "收：—（未提供）" in chart.toolTip()
        assert "MA20：—（未提供）" in chart.toolTip()
        assert marker.label not in chart.toolTip()
        _assert_no_audit(chart.toolTip())
        chart._clear_hover()
        assert chart._hover_index is None
    finally:
        chart.close()


def test_saved_snapshot_readback_hover_keeps_pins_and_gaps(app, tmp_path):
    _database, _snapshot, context = _produce(tmp_path)
    pins = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (tmp_path / "snapshots").rglob("*") if p.is_file()}
    report = _reader(tmp_path, tmp_path / "missing.sqlite").read_report(
        "2330", as_of_date=DAY, context=context)
    projection = project_stock_chart_payload(report, expected_source_context=context)
    assert projection.payload is not None
    payload = projection.payload
    chart = StockPriceChartWidget()
    try:
        chart.set_points(payload.price_points)
        chart.set_technical_lines(payload.technical_lines)
        chart._select_point(len(payload.price_points) - 1)
        assert "收：100.125" in chart.toolTip() and "MA20：24" in chart.toolTip()
        _assert_no_audit(chart.toolTip())
        assert payload.table_rows == report.price_points
        assert payload.historical_pit_eligible is False
        assert report.price_points[-1].source_snapshot_hash
        assert payload.technical_lines[0].points[-1].source_row_hash
    finally:
        chart.close()
    assert pins == {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (tmp_path / "snapshots").rglob("*") if p.is_file()}


def test_saved_snapshot_hash_mismatch_still_rejected(tmp_path):
    _database, snapshot, _context = _produce(tmp_path)
    stock = snapshot.stock_snapshots["2330"]
    envelope = {**stock["saved_technical_chart"], "content_sha256": "0" * 64}
    with pytest.raises(SavedTechnicalChartError):
        read_saved_technical_chart(envelope, stock_code="2330", decision_date=DAY,
            scope_identity=stock["scope_identity"], input_fingerprint_sha256=stock["input_fingerprint_sha256"])
