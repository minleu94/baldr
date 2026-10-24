from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from threading import Event
from zoneinfo import ZoneInfo

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from app_module.taiex_history_presentation import TaiexHistoryBarDTO, TaiexHistoryDTO
from ui_qt.theme import MIDNIGHT_ANALYST
from ui_qt.views.taiex_history_view import (
    MAX_VISIBLE_BARS,
    SOURCE_ID,
    TaiexHistoryView,
    _bar_direction_color,
)


@pytest.fixture
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _bar(
    day: int,
    *,
    open_value: str | None = "22000.00",
    high: str | None = "22100.00",
    low: str | None = "21900.00",
    close: str | None = "22050.00",
    volume: int | None = 1234,
) -> TaiexHistoryBarDTO:
    return TaiexHistoryBarDTO(
        trade_date=date(2026, 10, day),
        open=Decimal(open_value) if open_value is not None else None,
        high=Decimal(high) if high is not None else None,
        low=Decimal(low) if low is not None else None,
        close=Decimal(close) if close is not None else None,
        volume=volume,
    )


def _result(
    bars: tuple[TaiexHistoryBarDTO, ...], *, quality: str = "complete", warnings: tuple[str, ...] = ()
) -> TaiexHistoryDTO:
    return TaiexHistoryDTO(
        requested_as_of=date(2026, 10, 23),
        effective_date=bars[-1].trade_date if bars else None,
        bars=bars,
        quality=quality,
        warnings=warnings,
    )


def test_initial_and_lazy_loading_states_use_injected_reader(app: QApplication) -> None:
    calls: list[tuple[date, int]] = []

    def reader(as_of_date: date, *, max_sessions: int = 60) -> TaiexHistoryDTO:
        calls.append((as_of_date, max_sessions))
        return _result((_bar(22),))

    view = TaiexHistoryView(reader)
    assert tuple(view.period_selector.itemText(i) for i in range(view.period_selector.count())) == (
        "最近 20 個資料日",
        "最近 60 個資料日",
        "最近 120 個資料日",
    )
    assert view.status_label.text().startswith("尚未載入")
    assert calls == []

    view.load_data_if_needed()
    assert view.status_label.text() == "歷史指數載入中…"
    view.period_selector.setCurrentIndex(view.period_selector.findData(20))
    assert view.status_label.text() == "歷史指數載入中…"
    assert view.chart.empty_state_message == "歷史指數載入中…"
    view.load_data_if_needed()
    assert len(view._workers) == 1
    worker = view._workers[0]
    assert worker.wait(2000)
    app.processEvents()
    assert len(calls) == 1
    assert calls[0][0] == datetime.now(ZoneInfo("Asia/Taipei")).date()
    assert calls[0][1] == MAX_VISIBLE_BARS
    assert view.status_label.text().startswith("完整")
    assert "最近 20 個資料日；實際顯示 1 筆" in view.status_label.text()
    assert SOURCE_ID in view.metadata_label.text()
    assert "可得時間：未知" in view.metadata_label.text()
    assert "歷史 PIT：未建立" in view.metadata_label.text()
    assert "成交量單位：原欄位單位未核" in view.metadata_label.text()
    assert "信心" not in view.metadata_label.text()
    assert "報酬" not in view.metadata_label.text()
    assert len(view.chart.bars) == 1


def test_ready_partial_missing_and_unavailable_states(app: QApplication) -> None:
    view = TaiexHistoryView(lambda _as_of, **_kwargs: _result(()))

    view._on_history_loaded(_result((_bar(22),)), request_id=0)
    assert view.status_label.text().startswith("完整")
    assert view.chart.render_mode == "ohlc"

    view._on_history_loaded(
        _result((_bar(21, high=None),), quality="partial", warnings=("欄位缺漏",)),
        request_id=0,
    )
    assert view.status_label.text().startswith("部分")
    assert view.chart.render_mode == "close"
    assert "欄位缺漏" in view.warning_label.text()

    view._on_history_loaded(_result((), quality="missing"), request_id=0)
    assert "沒有可顯示" in view.status_label.text()
    assert view.chart.bars == ()
    assert view.chart.empty_state_message == "沒有可繪製的收盤值；缺值保留未知。"

    view._on_history_loaded(_result((), quality="unavailable"), request_id=0)
    assert "來源不可用" in view.status_label.text()
    assert view.chart.empty_state_message.startswith("歷史指數來源不可用")

    view._on_history_error("C:\\private\\market.db read failed\ntraceback details", request_id=0)
    assert view.status_label.text().startswith("歷史指數載入失敗")
    assert "private" not in view.status_label.text()
    assert "private" in view.warning_label.text()
    assert len(view.warning_label.text()) <= 500
    assert view.chart.bars == ()
    assert view.chart.empty_state_message.startswith("歷史指數載入失敗")

    unknown = _result((_bar(22),), quality="future-code")
    view._on_history_loaded(unknown, request_id=0)
    assert view.status_label.text().startswith("狀態未知")
    assert "future-code" in view.status_label.toolTip()
    assert "future-code" in view.status_label.accessibleDescription()


def test_zero_volume_and_missing_close_remain_distinct_in_tooltip(app: QApplication) -> None:
    bar = _bar(22, open_value=None, high=None, low=None, close=None, volume=0)
    view = TaiexHistoryView(lambda _as_of, **_kwargs: _result((bar,), quality="partial"))
    view._on_history_loaded(_result((bar,), quality="partial"), request_id=0)

    assert view.chart.bars == (bar,)
    view.chart._select_index(0)
    tooltip = view.chart.toolTip()
    assert "開：未提供" in tooltip
    assert "高：未提供" in tooltip
    assert "低：未提供" in tooltip
    assert "收：未提供" in tooltip
    assert "成交量（原欄位單位未核）：0" in tooltip
    assert view.chart.render_mode == "empty"
    assert view.chart.empty_state_message == "沒有可繪製的收盤值；缺值保留未知。"
    assert view.chart._plot_rect()[-1] is True
    assert view.chart.selected_date == "2026-10-22"
    assert view.selection_label.text() == "選取日期：2026-10-22"
    view.chart.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    assert view.chart.selected_date is None
    assert view.chart.toolTip() == view.chart.empty_state_message
    assert "收：未提供" not in view.chart.accessibleDescription()


def test_candle_direction_colors_require_complete_ohlc(app: QApplication) -> None:
    assert _bar_direction_color(_bar(20, open_value="100", close="101")) == MIDNIGHT_ANALYST.market_up
    assert _bar_direction_color(_bar(21, open_value="101", close="100")) == MIDNIGHT_ANALYST.market_down
    assert _bar_direction_color(_bar(22, open_value="100", close="100")) == MIDNIGHT_ANALYST.market_flat
    assert _bar_direction_color(_bar(23, high=None, close="101")) == MIDNIGHT_ANALYST.accent


def test_refresh_clears_old_series_selection_and_late_result_is_ignored(app: QApplication) -> None:
    old = _result((_bar(21),))
    new = _result((_bar(22, close="22100.00"),))
    view = TaiexHistoryView(lambda _as_of, **_kwargs: new)
    view._on_history_loaded(old, request_id=0)
    view.chart._select_index(0)
    assert view.chart.selected_date == "2026-10-21"

    view.refresh()
    request_id = view._active_request_id
    assert view.status_label.text() == "歷史指數載入中…"
    assert view.chart.bars == ()
    assert view._current_result is None
    assert view.chart.selected_date is None
    assert view.selection_label.text() == "選取日期：尚未選取"
    assert view.chart.empty_state_message == "歷史指數載入中…"
    assert view.chart.toolTip() == view.chart.empty_state_message
    assert view.chart.accessibleDescription() == view.chart.empty_state_message

    view._on_history_loaded(old, request_id=request_id - 1)
    assert view.chart.bars == ()
    worker = view._workers[0]
    assert worker.wait(2000)
    app.processEvents()
    assert view.chart.bars == new.bars


def _dated_bars(count: int, *, start_index: int = 0) -> tuple[TaiexHistoryBarDTO, ...]:
    first_day = date(2026, 1, 1)
    return tuple(
        TaiexHistoryBarDTO(
            trade_date=first_day + timedelta(days=index),
            open=Decimal("100.00"),
            high=Decimal("102.00"),
            low=Decimal("99.00"),
            close=Decimal(f"{100 + index}.1200"),
            volume=0 if index == 3 else 123,
        )
        for index in range(start_index, start_index + count)
    )


def test_period_selector_slices_same_loaded_dto_and_clears_tooltip(app: QApplication) -> None:
    calls: list[date] = []
    bars = _dated_bars(80)

    def reader(as_of_date: date, *, max_sessions: int = 60) -> TaiexHistoryDTO:
        calls.append(as_of_date)
        assert max_sessions == MAX_VISIBLE_BARS
        return _result(bars)

    view = TaiexHistoryView(reader)
    view.load_data_if_needed()
    worker = view._workers[0]
    assert worker.wait(2000)
    app.processEvents()
    assert len(calls) == 1
    assert len(view.chart.bars) == 80
    view.chart._select_index(79)
    assert view.chart.selected_date == bars[-1].trade_date.isoformat()
    assert "收：179.1200" in view.chart.toolTip()
    assert "收：179.1200" in view.chart.accessibleDescription()

    view.period_selector.setCurrentIndex(view.period_selector.findData(20))
    assert len(calls) == 1
    assert view.chart.bars == bars[-20:]
    assert view.chart.selected_date is None
    assert "收：179.1200" not in view.chart.toolTip()
    assert "收：179.1200" not in view.chart.accessibleDescription()
    assert "最近 20 個資料日；實際顯示 20 筆" in view.status_label.text()
    assert "SQLite 觀測截至：2026-03-21" in view.metadata_label.text()
    assert "可得時間：未知" in view.metadata_label.text()
    assert "歷史 PIT：未建立" in view.metadata_label.text()
    assert "成交量單位：原欄位單位未核" in view.metadata_label.text()


def test_short_history_reports_actual_count_and_keeps_missing_close_unknown(app: QApplication) -> None:
    bars = list(_dated_bars(7))
    bars[3] = TaiexHistoryBarDTO(
        trade_date=bars[3].trade_date,
        open=None,
        high=None,
        low=None,
        close=None,
        volume=0,
    )
    result = _result(tuple(bars), quality="partial")
    view = TaiexHistoryView(lambda _as_of, **_kwargs: result)
    view._on_history_loaded(result, request_id=0)
    view.period_selector.setCurrentIndex(view.period_selector.findData(20))

    assert view.chart.bars == result.bars
    assert view.status_label.text().startswith("部分")
    assert "最近 20 個資料日；實際顯示 7 筆" in view.status_label.text()
    assert view.chart.bars[3].close is None
    view.chart._select_index(3)
    assert "收：未提供" in view.chart.toolTip()
    assert "成交量（原欄位單位未核）：0" in view.chart.toolTip()


def test_chart_caps_rows_and_keeps_raw_decimal_scale(app: QApplication) -> None:
    first_day = date(2026, 1, 1)
    bars = tuple(
        TaiexHistoryBarDTO(
            trade_date=first_day + timedelta(days=index),
            open=None,
            high=None,
            low=None,
            close=Decimal(f"{index}.1200"),
            volume=None,
        )
        for index in range(MAX_VISIBLE_BARS + 5)
    )
    view = TaiexHistoryView(lambda _as_of, **_kwargs: _result(bars))
    view._on_history_loaded(_result(bars), request_id=0)
    assert len(view.chart.bars) == MAX_VISIBLE_BARS
    view.chart._select_index(0)
    assert "收：5.1200" in view.chart.toolTip()


def test_close_invalidates_request_and_cooperatively_cancels_without_waiting(app: QApplication) -> None:
    started = Event()
    release = Event()

    def blocking_reader(_as_of: date, *, max_sessions: int = 60) -> TaiexHistoryDTO:
        started.set()
        release.wait(2)
        return _result((_bar(22),))

    view = TaiexHistoryView(blocking_reader)
    view.refresh()
    request_id = view._active_request_id
    assert started.wait(2)
    worker = view._workers[0]

    view.close()
    assert view._active_request_id == request_id + 1
    release.set()
    assert worker.wait(2000)
    app.processEvents()

    view._on_history_loaded(_result((_bar(22),)), request_id=request_id)
    assert view.chart.bars == ()
    assert view.status_label.text() == "歷史指數載入中…"
    assert view.chart.empty_state_message == "歷史指數載入中…"


def test_chart_empty_state_messages_transition_and_clear_old_selection(app: QApplication) -> None:
    ready = _result((_bar(22),))
    view = TaiexHistoryView(lambda _as_of, **_kwargs: ready)
    assert view.chart.empty_state_message == "尚未載入 TAIEX 歷史資料。"

    view._on_history_loaded(ready, request_id=0)
    view.chart._select_index(0)
    assert view.chart.selected_date == "2026-10-22"
    assert "收：22050.00" in view.chart.toolTip()

    view._active_request_id += 1
    request_id = view._active_request_id
    view.chart.set_empty_state("歷史指數載入中…")
    view._on_history_error("technical detail", request_id=request_id)
    assert view.chart.bars == ()
    assert view.chart.selected_date is None
    assert view.selection_label.text() == "選取日期：尚未選取"
    assert view.chart.empty_state_message.startswith("歷史指數載入失敗")
    assert "收：22050.00" not in view.chart.toolTip()
    assert "收：22050.00" not in view.chart.accessibleDescription()

    view._on_history_cancelled(request_id=request_id)
    assert view.chart.empty_state_message.startswith("歷史指數讀取已取消")
    assert view.chart.bars == ()
    assert view.chart.toolTip() == view.chart.empty_state_message
    assert view.chart.accessibleDescription() == view.chart.empty_state_message
    assert view.warning_label.text() == ""
