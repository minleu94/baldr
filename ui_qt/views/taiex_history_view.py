"""TAIEX 歷史原值檢視頁。"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Callable, Sequence
from zoneinfo import ZoneInfo

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from app_module.taiex_history_presentation import (
    TaiexHistoryBarDTO,
    TaiexHistoryDTO,
)
from ui_qt.theme import MIDNIGHT_ANALYST
from ui_qt.workers.task_worker import TaskWorker


MAX_VISIBLE_BARS = 120
SOURCE_ID = "sqlite.market_indices:TAIEX"
TAIPEI_TIMEZONE = ZoneInfo("Asia/Taipei")
SESSION_WINDOWS = (20, 60, 120)
QUALITY_LABELS = {
    "complete": "完整",
    "partial": "部分",
    "missing": "缺件",
    "unavailable": "來源不可用",
}
EMPTY_CHART_HINT = "尚未載入 TAIEX 歷史資料。"
LOADING_CHART_HINT = "歷史指數載入中…"
ERROR_CHART_HINT = "歷史指數載入失敗；請重新整理或檢查來源。"
CANCELLED_CHART_HINT = "歷史指數讀取已取消；可重新整理。"
UNAVAILABLE_CHART_HINT = "歷史指數來源不可用；請檢查來源狀態後重新整理。"
NO_CLOSE_CHART_HINT = "沒有可繪製的收盤值；缺值保留未知。"
LOADED_CHART_HINT = "將游標移至資料點查看日期、SQLite 現存指數值與成交量；鍵盤方向鍵可選取日期。"


def _decimal_text(value: Decimal | None) -> str:
    return "未提供" if value is None else format(value, "f")


def _bar_direction_color(bar: TaiexHistoryBarDTO) -> str:
    """只對完整 OHLC 觀測值按 close/open 選擇市場方向色。"""

    if not _has_ohlc(bar):
        return MIDNIGHT_ANALYST.accent
    open_value, close_value = bar.open, bar.close
    if open_value is None or close_value is None:
        return MIDNIGHT_ANALYST.accent
    if close_value > open_value:
        return MIDNIGHT_ANALYST.market_up
    if close_value < open_value:
        return MIDNIGHT_ANALYST.market_down
    return MIDNIGHT_ANALYST.market_flat


def _bounded_warning_text(lines: Sequence[str], *, limit: int = 480) -> str:
    """只在次要警示區顯示有限原始診斷，不把任意例外放入狀態首行。"""

    first_lines = []
    for line in lines[:3]:
        parts = str(line).splitlines()
        first_lines.append((parts[0] if parts else "未提供技術細節")[:160])
    detail = "；".join(first_lines)
    return detail[:limit]


def _read_history(reader: Callable[..., TaiexHistoryDTO], as_of_date: date) -> TaiexHistoryDTO:
    """在 worker 中呼叫注入的唯讀 reader。"""

    return reader(as_of_date, max_sessions=MAX_VISIBLE_BARS)


class TaiexHistoryChart(QWidget):
    """以原始日值繪製收盤線或完整 OHLC 蠟燭圖。"""

    dateSelected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._bars: tuple[TaiexHistoryBarDTO, ...] = ()
        self._selected_index: int | None = None
        self._hover_index: int | None = None
        self._mode = "empty"
        self._empty_state_message = EMPTY_CHART_HINT
        self.setMinimumHeight(300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("TAIEX 歷史走勢圖")
        self.setAccessibleDescription(EMPTY_CHART_HINT)
        self.setToolTip(EMPTY_CHART_HINT)

    @property
    def bars(self) -> tuple[TaiexHistoryBarDTO, ...]:
        return self._bars

    @property
    def selected_date(self) -> str | None:
        if self._selected_index is None:
            return None
        return self._bars[self._selected_index].trade_date.isoformat()

    @property
    def render_mode(self) -> str:
        return self._mode

    @property
    def empty_state_message(self) -> str:
        return self._empty_state_message

    def set_empty_state(self, message: str) -> None:
        QToolTip.hideText()
        self._bars = ()
        self._selected_index = None
        self._hover_index = None
        self._mode = "empty"
        self._empty_state_message = message
        self.setToolTip(message)
        self.setAccessibleDescription(message)
        self.update()

    def clear(self, message: str = EMPTY_CHART_HINT) -> None:
        self.set_empty_state(message)

    def set_bars(self, bars: Sequence[TaiexHistoryBarDTO]) -> None:
        QToolTip.hideText()
        visible = tuple(bars[-MAX_VISIBLE_BARS:])
        self._bars = visible
        self._selected_index = None
        self._hover_index = None
        self._mode = "ohlc" if visible and all(_has_ohlc(bar) for bar in visible) else "close"
        if not any(bar.close is not None for bar in visible):
            self._mode = "empty"
            self._empty_state_message = NO_CLOSE_CHART_HINT
            self.setToolTip(NO_CLOSE_CHART_HINT)
            self.setAccessibleDescription(
                NO_CLOSE_CHART_HINT + ("；可用方向鍵查看原始日值。" if visible else "")
            )
            self.update()
            return
        self._empty_state_message = ""
        self.setToolTip(LOADED_CHART_HINT)
        self.setAccessibleDescription(LOADED_CHART_HINT)
        self.update()

    def _plot_rect(self):
        volume_complete = bool(self._bars) and all(bar.volume is not None for bar in self._bars)
        left, top, right = 66.0, 18.0, max(70.0, float(self.width()) - 18.0)
        bottom = max(top + 40.0, float(self.height()) - (88.0 if volume_complete else 46.0))
        return left, top, right, bottom, volume_complete

    def _index_at_x(self, x: float) -> int | None:
        if not self._bars:
            return None
        left, _top, right, _bottom, _volume = self._plot_rect()
        if x < left or x > right:
            return None
        span = max(1.0, right - left)
        index = round((x - left) / span * max(0, len(self._bars) - 1))
        return max(0, min(len(self._bars) - 1, index))

    def _select_index(self, index: int) -> None:
        if not self._bars:
            return
        self._selected_index = max(0, min(len(self._bars) - 1, index))
        bar = self._bars[self._selected_index]
        self.setToolTip(_bar_tooltip(bar))
        self.setAccessibleDescription(_bar_tooltip(bar))
        self.dateSelected.emit(bar.trade_date.isoformat())
        self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        point = event.position().toPoint()
        index = self._index_at_x(float(point.x()))
        self._hover_index = index
        if index is not None:
            self.setToolTip(_bar_tooltip(self._bars[index]))
        self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._hover_index = None
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            index = self._index_at_x(float(event.position().x()))
            if index is not None:
                self._select_index(index)
                event.accept()
                return
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        key = event.key()
        if self._bars and key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Home, Qt.Key.Key_End):
            current = self._selected_index if self._selected_index is not None else len(self._bars) - 1
            target = 0 if key == Qt.Key.Key_Home else len(self._bars) - 1 if key == Qt.Key.Key_End else current - 1 if key == Qt.Key.Key_Left else current + 1
            self._select_index(target)
            event.accept()
            return
        if key == Qt.Key.Key_Escape:
            self._selected_index = None
            hint = LOADED_CHART_HINT if self._mode != "empty" else self._empty_state_message
            self.setToolTip(hint)
            self.setAccessibleDescription(
                hint + ("；可用方向鍵查看原始日值。" if self._mode == "empty" and self._bars else "")
            )
            self.dateSelected.emit("")
            self.update()
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(MIDNIGHT_ANALYST.surface_1))
        if self._mode == "empty":
            painter.setPen(QColor(MIDNIGHT_ANALYST.text_muted))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._empty_state_message)
            painter.end()
            return

        left, top, right, bottom, volume_complete = self._plot_rect()
        values = [bar.close for bar in self._bars if bar.close is not None]
        if self._mode == "ohlc":
            values.extend(value for bar in self._bars for value in (bar.high, bar.low) if value is not None)
        low_value, high_value = min(values), max(values)
        numeric_low, numeric_high = float(low_value), float(high_value)
        span = numeric_high - numeric_low
        if span == 0:
            span = 1.0
        y = lambda value: bottom - (float(value) - numeric_low) / span * (bottom - top)

        grid_pen = QPen(QColor(MIDNIGHT_ANALYST.border_subtle))
        grid_pen.setWidth(1)
        painter.setPen(grid_pen)
        for step in range(4):
            grid_y = top + (bottom - top) * step / 3
            painter.drawLine(QPointF(left, grid_y), QPointF(right, grid_y))
        painter.setPen(QColor(MIDNIGHT_ANALYST.text_muted))
        painter.drawText(4, int(top + 5), _decimal_text(high_value))
        painter.drawText(4, int(bottom), _decimal_text(low_value))

        usable = max(1.0, right - left)
        count = len(self._bars)
        x_for = lambda index: left + (usable * index / max(1, count - 1))
        accent = QColor(MIDNIGHT_ANALYST.accent)
        series_pen = QPen(accent, 1.8)
        painter.setPen(series_pen)
        if self._mode == "ohlc":
            spacing = usable / max(1, count - 1) if count > 1 else usable
            candle_width = max(2.0, min(9.0, spacing * 0.56))
            for index, bar in enumerate(self._bars):
                x = x_for(index)
                high_y, low_y, open_y, close_y = (y(bar.high), y(bar.low), y(bar.open), y(bar.close))
                direction = QColor(_bar_direction_color(bar))
                painter.setPen(QPen(direction, 1.4))
                painter.setBrush(direction)
                painter.drawLine(QPointF(x, high_y), QPointF(x, low_y))
                body_top, body_bottom = min(open_y, close_y), max(open_y, close_y)
                painter.drawRect(int(x - candle_width / 2), int(body_top), int(candle_width), max(1, int(body_bottom - body_top)))
        else:
            path = QPainterPath()
            started = False
            for index, bar in enumerate(self._bars):
                if bar.close is None:
                    started = False
                    continue
                point = QPointF(x_for(index), y(bar.close))
                if started:
                    path.lineTo(point)
                else:
                    path.moveTo(point)
                    started = True
            painter.drawPath(path)

        for index in {self._hover_index, self._selected_index} - {None}:
            bar = self._bars[index]
            value = bar.close
            if value is None:
                continue
            x, point_y = x_for(index), y(value)
            painter.setPen(QPen(QColor(MIDNIGHT_ANALYST.warning), 1.2))
            painter.drawLine(QPointF(x, top), QPointF(x, bottom))
            painter.drawEllipse(QPointF(x, point_y), 4.0, 4.0)

        if volume_complete:
            volume_top = bottom + 23.0
            volume_bottom = float(self.height()) - 24.0
            max_volume = max((bar.volume or 0 for bar in self._bars), default=0)
            baseline_pen = QPen(QColor(MIDNIGHT_ANALYST.border_subtle))
            painter.setPen(baseline_pen)
            painter.drawLine(QPointF(left, volume_top), QPointF(right, volume_top))
            painter.setPen(QColor(MIDNIGHT_ANALYST.text_muted))
            painter.drawText(int(left), int(volume_top - 5), "成交量（原欄位單位未核）")
            slot = usable / max(1, count)
            if max_volume > 0:
                for index, bar in enumerate(self._bars):
                    volume_y = volume_bottom - (bar.volume or 0) / max_volume * (volume_bottom - volume_top)
                    x = x_for(index)
                    painter.setPen(QPen(QColor(_bar_direction_color(bar)), max(1.0, min(5.0, slot * 0.7))))
                    painter.drawLine(QPointF(x, volume_bottom), QPointF(x, volume_y))

        painter.setPen(QColor(MIDNIGHT_ANALYST.text_secondary))
        painter.drawText(int(left), self.height() - 4, self._bars[0].trade_date.isoformat())
        last_date = self._bars[-1].trade_date.isoformat()
        painter.drawText(int(right - 90), self.height() - 4, last_date)
        painter.end()


class TaiexHistoryView(QWidget):
    """注入唯讀 reader，首次進入時背景載入有限 TAIEX 歷史原值。"""

    def __init__(
        self,
        reader: Callable[..., TaiexHistoryDTO],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.reader = reader
        self._active_request_id = 0
        self._workers: list[TaskWorker] = []
        self._loaded = False
        self._current_result: TaiexHistoryDTO | None = None
        self._selected_session_count = MAX_VISIBLE_BARS
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)
        heading = QLabel("TAIEX 歷史走勢")
        heading.setObjectName("TaiexHistoryTitle")
        heading.setStyleSheet(f"font-size: 16pt; font-weight: 600; color: {MIDNIGHT_ANALYST.text_primary};")
        root.addWidget(heading)

        top = QHBoxLayout()
        self.status_label = QLabel("尚未載入；首次開啟時讀取最近可用資料。")
        self.status_label.setObjectName("TaiexHistoryStatus")
        self.status_label.setWordWrap(True)
        top.addWidget(self.status_label, 1)
        self.refresh_button = QPushButton("重新整理")
        self.refresh_button.setObjectName("TaiexHistoryRefresh")
        self.refresh_button.clicked.connect(self.refresh)
        top.addWidget(self.refresh_button)
        root.addLayout(top)

        period_row = QHBoxLayout()
        period_row.addWidget(QLabel("走勢範圍："))
        self.period_selector = QComboBox()
        self.period_selector.setObjectName("TaiexHistoryPeriod")
        self.period_selector.setAccessibleName("TAIEX 最近資料日範圍")
        for session_count in SESSION_WINDOWS:
            self.period_selector.addItem(f"最近 {session_count} 個資料日", session_count)
        self.period_selector.setCurrentIndex(self.period_selector.findData(MAX_VISIBLE_BARS))
        self.period_selector.currentIndexChanged.connect(self._on_period_changed)
        period_row.addWidget(self.period_selector)
        period_row.addStretch(1)
        root.addLayout(period_row)

        self.metadata_label = QLabel(
            f"來源：{SOURCE_ID}；可得時間：未知；歷史 PIT：未建立；成交量單位：原欄位單位未核"
        )
        self.metadata_label.setObjectName("TaiexHistoryMetadata")
        self.metadata_label.setWordWrap(True)
        self.metadata_label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_secondary};")
        root.addWidget(self.metadata_label)

        self.selection_label = QLabel("選取日期：尚未選取")
        self.selection_label.setObjectName("TaiexHistorySelection")
        root.addWidget(self.selection_label)
        self.chart = TaiexHistoryChart(self)
        self.chart.dateSelected.connect(self._on_date_selected)
        root.addWidget(self.chart, 1)
        self.warning_label = QLabel("")
        self.warning_label.setObjectName("TaiexHistoryWarnings")
        self.warning_label.setWordWrap(True)
        self.warning_label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.warning};")
        root.addWidget(self.warning_label)

    def load_data_if_needed(self) -> None:
        if not self._loaded and not self._workers:
            self.refresh()

    def refresh(self) -> None:
        self._active_request_id += 1
        request_id = self._active_request_id
        self._loaded = False
        self._current_result = None
        self.chart.set_empty_state(LOADING_CHART_HINT)
        self.selection_label.setText("選取日期：尚未選取")
        self.warning_label.clear()
        self.metadata_label.setText(
            f"來源：{SOURCE_ID}；可得時間：未知；歷史 PIT：未建立；成交量單位：原欄位單位未核"
        )
        self.status_label.setText("歷史指數載入中…")
        self.status_label.setToolTip("")
        self.status_label.setAccessibleDescription("歷史指數資料載入中。")
        self.refresh_button.setEnabled(False)
        try:
            as_of_date = datetime.now(TAIPEI_TIMEZONE).date()
        except Exception as exc:  # noqa: BLE001 - 顯示明確失敗狀態
            self._on_history_error(str(exc), request_id)
            return
        worker = TaskWorker(_read_history, self.reader, as_of_date)
        worker.finished.connect(lambda result, rid=request_id: self._on_history_loaded(result, rid))
        worker.error.connect(lambda message, rid=request_id: self._on_history_error(message, rid))
        worker.cancelled.connect(lambda rid=request_id: self._on_history_cancelled(rid))
        worker.native_thread_finished.connect(lambda item=worker: self._release_worker(item))
        self._workers.append(worker)
        worker.start()

    def _on_history_loaded(self, result: TaiexHistoryDTO, request_id: int) -> None:
        if request_id != self._active_request_id:
            return
        self._loaded = True
        self.refresh_button.setEnabled(True)
        self._current_result = result
        self._render_current_period()

    def _on_period_changed(self, _index: int) -> None:
        value = self.period_selector.currentData()
        if type(value) is not int or value not in SESSION_WINDOWS:
            return
        self._selected_session_count = value
        self.chart.clear(self.chart.empty_state_message)
        self.selection_label.setText("選取日期：尚未選取")
        if self._current_result is not None:
            self._render_current_period()

    def _render_current_period(self) -> None:
        result = self._current_result
        if result is None:
            return
        requested_count = self._selected_session_count
        bars = tuple(result.bars[-requested_count:])
        self.chart.set_bars(bars)
        effective = result.effective_date.isoformat() if result.effective_date else "未知"
        self.metadata_label.setText(
            f"來源：{result.source_id}；SQLite 觀測截至：{effective}；顯示 {len(bars)} 筆；"
            "可得時間：未知；歷史 PIT：未建立；成交量單位：原欄位單位未核"
        )
        self.warning_label.setText(_bounded_warning_text(result.warnings))
        quality_code = result.quality
        quality_label = QUALITY_LABELS.get(quality_code.casefold(), "狀態未知")
        quality_detail = f"資料品質：{quality_label}；讀取狀態原碼：{quality_code}"
        self.status_label.setToolTip(quality_detail)
        self.status_label.setAccessibleDescription(quality_detail)
        count_detail = f"最近 {requested_count} 個資料日；實際顯示 {len(bars)} 筆"
        if result.quality.casefold() == "unavailable":
            self.chart.set_empty_state(UNAVAILABLE_CHART_HINT)
            self.status_label.setText(f"來源不可用；{count_detail}。請檢查來源狀態後重新整理。")
        elif not bars or not any(bar.close is not None for bar in bars):
            self.status_label.setText(f"{quality_label}；{count_detail}；沒有可顯示的收盤值，缺值保留未知。")
        else:
            self.status_label.setText(f"{quality_label}；{count_detail}；顯示 SQLite 現存觀測值。")

    def _on_history_error(self, message: str, request_id: int) -> None:
        if request_id != self._active_request_id:
            return
        self._loaded = False
        self._current_result = None
        self.refresh_button.setEnabled(True)
        self.chart.set_empty_state(ERROR_CHART_HINT)
        self.selection_label.setText("選取日期：尚未選取")
        self.status_label.setText("歷史指數載入失敗；請重新整理或檢查來源。")
        self.status_label.setToolTip("")
        self.status_label.setAccessibleDescription("歷史指數來源讀取失敗。")
        self.warning_label.setText(f"技術細節：{_bounded_warning_text((message,))}")

    def _on_history_cancelled(self, request_id: int) -> None:
        if request_id != self._active_request_id:
            return
        self._loaded = False
        self._current_result = None
        self.refresh_button.setEnabled(True)
        self.chart.set_empty_state(CANCELLED_CHART_HINT)
        self.selection_label.setText("選取日期：尚未選取")
        self.warning_label.clear()
        self.status_label.setText("歷史指數讀取已取消；可重新整理。")
        self.status_label.setToolTip("")
        self.status_label.setAccessibleDescription("歷史指數讀取已取消。")

    def _on_date_selected(self, selected_date: str) -> None:
        self.selection_label.setText(
            f"選取日期：{selected_date or '尚未選取'}"
        )

    def _release_worker(self, worker: TaskWorker) -> None:
        if worker in self._workers:
            self._workers.remove(worker)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._active_request_id += 1
        for worker in tuple(self._workers):
            try:
                worker.cancel(cooperative=True, wait=False)
                # TaskWorker defers deletion until its native thread exits.
                worker.deleteLater()
            except RuntimeError:
                if worker in self._workers:
                    self._workers.remove(worker)
        super().closeEvent(event)


def _has_ohlc(bar: TaiexHistoryBarDTO) -> bool:
    return all(value is not None for value in (bar.open, bar.high, bar.low, bar.close))


def _bar_tooltip(bar: TaiexHistoryBarDTO) -> str:
    return "\n".join(
        (
            f"資料日：{bar.trade_date.isoformat()}",
            f"開：{_decimal_text(bar.open)}",
            f"高：{_decimal_text(bar.high)}",
            f"低：{_decimal_text(bar.low)}",
            f"收：{_decimal_text(bar.close)}",
            f"成交量（原欄位單位未核）：{'未提供' if bar.volume is None else str(bar.volume)}",
        )
    )
