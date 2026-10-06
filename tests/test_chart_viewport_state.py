"""UX08 範圍契約與既有 renderer 的隔離測試。"""

from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
import os

import pytest

from app_module.chart_viewport_state import ChartViewportIdentity, ChartViewportState


def dates(count=10, start=0):
    return tuple((date(2026, 1, 1) + timedelta(days=i)).isoformat() for i in range(start, start + count))


def identity(**changes):
    return replace(ChartViewportIdentity("2330", "saved", "sha256:fixture-v1", "2026-12-31", (("scope", "fixture"),)), **changes)


def loaded(count=10):
    state = ChartViewportState()
    state.load(dates(count), identity())
    return state


def test_empty_single_reset():
    state = loaded(0)
    assert state.zoom(1, 2).count == state.pan(100).count == 0
    assert state.nearest_index(5, 0, 10) is None
    state.load(dates(1), identity())
    assert state.zoom(1, 10).count == state.pan(-100).count == 1
    assert state.nearest_index(5, 0, 10) == 0
    assert state.reset().is_full


def test_zoom_pan_reset_and_anchor():
    state = loaded()
    assert state.zoom(1, 2, anchor=9).start == 5
    assert state.range.stop == 10
    assert state.pan(-100).start == 0
    assert state.pan(100).stop == 10
    assert state.zoom(2).is_full
    state.set_range(2, 8)
    assert state.zoom(1, 2, anchor=2).start == 2
    assert state.reset().is_full


def test_ranges_and_repeated_rounding_stay_bounded():
    state = loaded(20)
    assert state.set_range(-100, -95).count == 5
    assert state.set_range(100, 105).start == 15
    for _ in range(30):
        state.zoom(99, 100)
    assert state.range.count == 1
    for _ in range(30):
        state.zoom(101, 100)
    assert state.range.is_full
    assert state.set_range(-1000, 1000).is_full


def test_preserve_by_dates_when_rows_inserted_or_removed():
    state = loaded()
    state.set_range(3, 7)
    state.load(dates(12), identity())
    assert state.visible_dates == dates(4, 3)
    state.load(dates(8, 2), identity())
    assert (state.range.start, state.range.stop) == (1, 5)
    state.load((dates()[4], dates()[6]), identity())
    assert state.visible_dates == (dates()[4], dates()[6])


def test_full_no_overlap_empty_and_explicit_reset():
    state = loaded()
    assert state.load(dates(20), identity()).is_full
    state.set_range(2, 4)
    assert state.load(dates(3, 30), identity()).is_full
    state.set_range(1, 2)
    assert state.load(dates(3, 30), identity(), preserve=False).is_full
    state.load((), identity())
    assert state.load(dates(), identity()).is_full


@pytest.mark.parametrize("change", [
    {"stock_code": "2317"}, {"source_id": "live"}, {"version": "v2"},
    {"cutoff_date": "2026-11-30"}, {"source_context": (("scope", "other"),)},
    {"version": ""}, {"source_id": ""}, {"version": "unknown"},
])
def test_identity_changes_never_reuse_range(change):
    state = loaded()
    state.set_range(2, 4)
    assert state.load(dates(), identity(**change)).is_full


@pytest.mark.parametrize("version", ["", "unknown", "未知", " N/A "])
def test_unknown_identity_never_preserves_even_if_equal(version):
    state = ChartViewportState()
    unknown = identity(version=version)
    state.load(dates(), unknown)
    state.set_range(2, 4)
    assert state.load(dates(), unknown).is_full


def test_context_order_is_canonical():
    first = identity(source_context=(("b", "2"), ("a", "1")))
    assert first == identity(source_context=(("a", "1"), ("b", "2")))
    with pytest.raises(ValueError):
        identity(source_context=(("a", "1"), ("a", "2")))


@pytest.mark.parametrize("incoming", [
    ("2026-01-02", "2026-01-01"), ("2026-01-01", "2026-01-01"),
    ("2027-01-01",), ("20260101",), ("2026-02-30",),
])
def test_invalid_load_is_atomic(incoming):
    state = loaded()
    state.set_range(2, 4)
    before = state.range
    with pytest.raises(ValueError):
        state.load(incoming, identity())
    assert state.range == before


@pytest.mark.parametrize("operation", [
    lambda s: s.zoom(0), lambda s: s.zoom(-1), lambda s: s.zoom(1, 0),
    lambda s: s.zoom(1, 2, anchor=100), lambda s: s.set_range(2, 2),
    lambda s: s.nearest_index(1, 2, 2),
])
def test_invalid_operations_do_not_mutate(operation):
    state = loaded()
    before = state.range
    with pytest.raises(ValueError):
        operation(state)
    assert state.range == before


@pytest.mark.parametrize("operation", [lambda s: s.pan(True), lambda s: s.zoom(0.5), lambda s: s.set_range(1.5, 3)])
def test_noninteger_operations_rejected(operation):
    with pytest.raises(TypeError):
        operation(loaded())


def test_gaps_slots_slice_and_hover_share_indices():
    @dataclass(frozen=True)
    class Point:
        data_date: str
        close_price: Decimal | None

    points = tuple(Point(d, None if i == 2 else Decimal(i)) for i, d in enumerate(dates(5)))
    state = loaded(5)
    state.set_range(1, 4)
    visible = state.slice_points(points)
    assert visible == points[1:4] and visible[1].close_price is None
    assert state.nearest_index(50, 0, 100) == 2
    assert state.nearest_index(-1, 0, 100) is None
    assert state.nearest_index(100, 0, 100) == 3
    with pytest.raises(ValueError):
        state.slice_points(points[:-1])
    with pytest.raises(ValueError):
        state.slice_points(tuple(reversed(points)))


def test_existing_native_renderer_accepts_controller_slice_offscreen():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from app_module.stock_research_report_dtos import StockPricePointDTO
    from app_module.stock_research_chart_payload import StockChartTechnicalLineDTO, StockChartTechnicalPointDTO
    from ui_qt.views.stock_research_report_view import StockPriceChartWidget

    app = QApplication.instance() or QApplication([])
    points = tuple(StockPricePointDTO(data_date=d, close_price=Decimal(i + 100)) for i, d in enumerate(dates()))
    line = StockChartTechnicalLineDTO("ma20", "MA20", tuple(StockChartTechnicalPointDTO(d, Decimal(101) if i != 5 else None) for i, d in enumerate(dates())))
    state = loaded()
    state.set_range(3, 8)
    chart = StockPriceChartWidget()
    try:
        chart.set_points(state.slice_points(points))
        chart.set_technical_lines((line,))
        assert chart._drawable_points() == points[3:8]
        assert [len(segment) for segment in chart._technical_segments(line)] == [2, 2]
        state.pan(2)
        chart.set_points(state.slice_points(points))
        chart.set_technical_lines((line,))
        assert chart._drawable_points() == points[5:10]
        state.reset()
        chart.set_points(state.slice_points(points))
        assert chart._drawable_points() == points
    finally:
        chart.close()
        chart.deleteLater()
        app.processEvents()
