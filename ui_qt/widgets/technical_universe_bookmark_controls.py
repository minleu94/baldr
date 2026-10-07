"""觀察清單內完整母體技術研究收藏的唯讀重開控制項。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, cast

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app_module.daily_market_technical_universe_v4_bookmark import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_SCHEMA,
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_SOURCE,
    DailyMarketTechnicalUniverseV4Bookmark,
    DailyMarketTechnicalUniverseV4BookmarkError,
    DailyMarketTechnicalUniverseV4BookmarkState,
)
from app_module.watchlist_service import WatchlistService
from ui_qt.workers.task_worker import TaskWorker


@dataclass(frozen=True, slots=True)
class _BookmarkListEntry:
    """由觀察清單公開列建立的列項；錯誤列可見但不可重開。"""

    bookmark_id: str
    stock_code: str
    label: str
    error_code: str = ""


def _check_cancel(cancel_callback: Callable[[], bool] | None) -> None:
    if cancel_callback is not None and cancel_callback():
        raise DailyMarketTechnicalUniverseV4BookmarkError(
            "technical_universe_v4_bookmark_cancelled"
        )


def _row_value(row: Mapping[str, Any], key: str) -> str:
    value = row.get(key)
    return value if isinstance(value, str) else ""


def _format_valid_entry(bookmark: DailyMarketTechnicalUniverseV4Bookmark) -> str:
    query = bookmark.origin_query
    return (
        f"{query.decision_date.isoformat()}｜{bookmark.stock_code}｜"
        f"{query.universe_id}（{query.population_version}）"
    )


def _entry_from_watchlist_row(
    row: Mapping[str, Any],
    index: int,
) -> _BookmarkListEntry | None:
    payload = row.get("research_bookmark")
    payload_schema = payload.get("schema_version") if isinstance(payload, Mapping) else None
    source = row.get("source")
    if (
        source != DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_SOURCE
        and payload_schema != DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_SCHEMA
    ):
        return None

    source_id = _row_value(row, "source_id")
    stock_code = _row_value(row, "stock_code")
    raw_name = _row_value(row, "stock_name")
    fallback = stock_code or f"第 {index + 1} 筆"
    if not isinstance(payload, Mapping):
        return _BookmarkListEntry(
            source_id,
            stock_code,
            f"{fallback}｜收藏格式錯誤（沒有完整母體收藏 payload）",
            "technical_universe_v4_bookmark_payload_missing",
        )
    try:
        bookmark = DailyMarketTechnicalUniverseV4Bookmark.from_dict(payload)
    except (DailyMarketTechnicalUniverseV4BookmarkError, TypeError, ValueError) as exc:
        code = getattr(exc, "code", "technical_universe_v4_bookmark_wrong_kind")
        return _BookmarkListEntry(
            source_id,
            stock_code,
            f"{fallback}｜收藏格式錯誤（{code}）",
            str(code),
        )

    if (
        source != DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_SOURCE
        or source_id != bookmark.bookmark_id
        or stock_code != bookmark.stock_code
        or raw_name != bookmark.stock_code
    ):
        return _BookmarkListEntry(
            source_id,
            stock_code or bookmark.stock_code,
            f"{fallback}｜收藏種類或身份不符（拒絕讀回）",
            "technical_universe_v4_bookmark_watchlist_identity_mismatch",
        )
    return _BookmarkListEntry(
        bookmark.bookmark_id,
        bookmark.stock_code,
        _format_valid_entry(bookmark),
    )


def _list_full_n_bookmarks(
    service: WatchlistService,
    watchlist_id: str,
    *,
    cancel_callback: Callable[[], bool] | None = None,
) -> tuple[_BookmarkListEntry, ...]:
    """只讀取 WatchlistService 的公開列，不重開研究或建立來源。"""

    _check_cancel(cancel_callback)
    rows = service.get_stocks(watchlist_id)
    if not isinstance(rows, list):
        raise DailyMarketTechnicalUniverseV4BookmarkError(
            "technical_universe_v4_bookmark_watchlist_rows_invalid"
        )
    entries: list[_BookmarkListEntry] = []
    for index, raw_row in enumerate(rows):
        _check_cancel(cancel_callback)
        if not isinstance(raw_row, Mapping):
            raise DailyMarketTechnicalUniverseV4BookmarkError(
                "technical_universe_v4_bookmark_watchlist_row_invalid"
            )
        entry = _entry_from_watchlist_row(raw_row, index)
        if entry is not None:
            entries.append(entry)
    _check_cancel(cancel_callback)
    return tuple(entries)


def _reopen_bookmark_state(
    service: WatchlistService,
    bookmark_id: str,
    watchlist_id: str,
    *,
    cancel_callback: Callable[[], bool] | None = None,
) -> DailyMarketTechnicalUniverseV4BookmarkState:
    """委派給 WatchlistService 的 typed exact-source reader。"""

    return cast(
        DailyMarketTechnicalUniverseV4BookmarkState,
        service.get_technical_universe_research_bookmark_state(
            bookmark_id,
            watchlist_id,
            cancel_callback=cancel_callback,
        ),
    )


class DailyMarketTechnicalUniverseV4BookmarkControls(QWidget):
    """列出並背景重開已收藏的 full-N 技術研究，不執行產製。"""

    stateReady = Signal(object)

    def __init__(
        self,
        watchlist_service: WatchlistService,
        watchlist_id: str = "default",
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.watchlist_service = watchlist_service
        self.watchlist_id = watchlist_id
        self._generation = 0
        self._active_generation = 0
        self._selection_generation = 0
        self._opening_bookmark_id = ""
        self._opening_selection_generation = 0
        self._operation = ""
        self._refresh_pending = False
        self._worker: TaskWorker | None = None
        self._closing = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.bookmarks = QListWidget(self)
        self.bookmarks.setObjectName("technicalUniverseBookmarks")
        self.bookmarks.setAccessibleName("完整母體技術研究收藏")
        self.bookmarks.currentRowChanged.connect(self._selection_changed)
        layout.addWidget(self.bookmarks)

        buttons = QHBoxLayout()
        self.refresh_button = QPushButton("重新整理收藏", self)
        self.refresh_button.setAccessibleName("重新整理完整母體研究收藏")
        self.open_button = QPushButton("重開所選研究", self)
        self.open_button.setAccessibleName("重開所選完整母體研究")
        self.cancel_button = QPushButton("取消讀取", self)
        self.cancel_button.setAccessibleName("取消完整母體收藏讀取")
        buttons.addWidget(self.refresh_button)
        buttons.addWidget(self.open_button)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)

        self.status_label = QLabel(
            "只列出此觀察清單中的完整母體技術研究收藏；重開時依原保存 pins 唯讀核驗。",
            self,
        )
        self.status_label.setObjectName("technicalUniverseBookmarkStatus")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.refresh_button.clicked.connect(self.refresh_bookmarks)
        self.open_button.clicked.connect(self.open_selected)
        self.cancel_button.clicked.connect(self.cancel)
        self._refresh_controls()

    def refresh_bookmarks(self) -> None:
        """背景讀取公開觀察清單列並更新完整母體收藏選項。"""

        if self._closing:
            self._can_start()
            return
        if self._worker is not None:
            self._refresh_pending = True
            if self._operation == "open":
                self.status_label.setText(
                    "目前的唯讀重開會先完成；之後只刷新一次收藏列表。"
                )
            else:
                self.status_label.setText(
                    "目前的列表讀取會先完成；之後只再刷新一次收藏列表。"
                )
            return
        self._refresh_pending = False
        worker = TaskWorker(
            _list_full_n_bookmarks,
            self.watchlist_service,
            self.watchlist_id,
        )
        self._start_worker(worker, "list")
        self.status_label.setText("正在背景讀取已保存的完整母體研究收藏…")

    def open_selected(self) -> None:
        """以固定收藏身份背景重開並核驗原頁、個股與比較來源。"""

        if not self._can_start():
            return
        item = self.bookmarks.currentItem()
        entry = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if not isinstance(entry, _BookmarkListEntry):
            self.status_label.setText("請先選取完整母體技術研究收藏。")
            return
        if entry.error_code:
            self.status_label.setText(
                f"此列的收藏種類或身份不符，已拒絕讀回（{entry.error_code}）。"
            )
            self._refresh_controls()
            return
        if not entry.bookmark_id:
            self.status_label.setText("收藏缺少明確 source_id，已拒絕讀回。")
            self._refresh_controls()
            return

        self._opening_bookmark_id = entry.bookmark_id
        self._opening_selection_generation = self._selection_generation
        worker = TaskWorker(
            _reopen_bookmark_state,
            self.watchlist_service,
            entry.bookmark_id,
            self.watchlist_id,
        )
        self._start_worker(worker, "open")
        self.status_label.setText("正在背景核驗所選收藏的原保存來源…")

    def cancel(self) -> None:
        """使目前請求失效並合作式取消；晚到結果不會送到導覽端。"""

        self._refresh_pending = False
        if self._worker is not None:
            self._generation += 1
            self._worker.cancel(cooperative=True, wait=False)
            self.status_label.setText("已取消讀取；晚到的舊結果會丟棄。")
        self._refresh_controls()

    def begin_shutdown(self) -> bool:
        """取消待處理讀取；回傳背景執行緒是否已安全停止。"""

        self._closing = True
        self._generation += 1
        self._refresh_pending = False
        if self._worker is not None:
            self._worker.cancel(cooperative=True, wait=False)
        self._refresh_controls()
        return self._worker is None or not self._worker.isRunning()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt 覆寫命名遵循 Qt API
        self.begin_shutdown()
        event.accept()

    def _can_start(self) -> bool:
        if self._closing:
            self.status_label.setText("收藏控制項已關閉，未啟動讀取。")
            return False
        if self._worker is not None:
            self.status_label.setText("目前仍有背景工作；請先等待或取消。")
            return False
        return True

    def _start_worker(self, worker: TaskWorker, operation: str) -> None:
        self._generation += 1
        self._active_generation = self._generation
        self._operation = operation
        self._worker = worker
        worker.finished.connect(self._on_worker_finished)
        worker.error.connect(self._on_worker_error)
        worker.cancelled.connect(self._on_worker_cancelled)
        worker.native_thread_finished.connect(self._on_worker_thread_finished)
        self._refresh_controls()
        worker.start()

    @Slot(int)
    def _selection_changed(self, _row: int) -> None:
        self._selection_generation += 1
        entry = self._current_entry()
        if entry is not None and entry.error_code and self._worker is None:
            self.status_label.setText(
                f"此列的收藏種類或身份不符，已拒絕讀回（{entry.error_code}）。"
            )
        self._refresh_controls()

    def _current_entry(self) -> _BookmarkListEntry | None:
        item = self.bookmarks.currentItem()
        value = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        return value if isinstance(value, _BookmarkListEntry) else None

    def _refresh_controls(self) -> None:
        idle = self._worker is None and not self._closing
        entry = self._current_entry()
        self.refresh_button.setEnabled(idle)
        self.open_button.setEnabled(
            idle and entry is not None and not entry.error_code and bool(entry.bookmark_id)
        )
        self.cancel_button.setEnabled(self._worker is not None and not self._closing)

    @Slot(object)
    def _on_worker_finished(self, value: object) -> None:
        worker = self.sender()
        if worker is not self._worker:
            return
        if self._closing or self._active_generation != self._generation:
            return
        if self._operation == "list":
            if not isinstance(value, tuple) or any(
                not isinstance(entry, _BookmarkListEntry) for entry in value
            ):
                self.status_label.setText("收藏列回傳格式不符；原列表保留。")
                return
            self._show_entries(cast(tuple[_BookmarkListEntry, ...], value))
            return
        if self._operation != "open":
            self.status_label.setText("背景收藏工作類型不符；未切換研究頁。")
            return
        if not isinstance(value, DailyMarketTechnicalUniverseV4BookmarkState):
            self.status_label.setText("收藏 reader 未回傳完整母體 typed 狀態；未切換研究頁。")
            return
        if value.bookmark.bookmark_id != self._opening_bookmark_id:
            self.status_label.setText("重開結果與所選 source_id 不符；未切換研究頁。")
            return
        if self._selection_generation != self._opening_selection_generation:
            self.status_label.setText("選取的收藏已變更，已忽略晚到的舊讀取結果。")
            return
        self.status_label.setText(
            f"已核驗並重開 {value.bookmark.origin_query.decision_date.isoformat()} "
            f"完整母體研究；來源 pins 保持原值。"
        )
        self.stateReady.emit(value)

    def _show_entries(self, entries: tuple[_BookmarkListEntry, ...]) -> None:
        selected = self._current_entry()
        selected_bookmark_id = (
            selected.bookmark_id
            if selected is not None and not selected.error_code
            else ""
        )
        self.bookmarks.clear()
        for entry in entries:
            item = QListWidgetItem(entry.label, self.bookmarks)
            item.setData(Qt.ItemDataRole.UserRole, entry)
            if entry.bookmark_id:
                item.setToolTip(f"固定收藏 source_id：{entry.bookmark_id}")
            if entry.error_code:
                item.setForeground(Qt.GlobalColor.darkRed)
        if selected_bookmark_id:
            matching_rows = [
                row_number
                for row_number, entry in enumerate(entries)
                if entry.bookmark_id == selected_bookmark_id and not entry.error_code
            ]
            if len(matching_rows) == 1:
                self.bookmarks.setCurrentRow(matching_rows[0])
        self.status_label.setText(
            f"已列出 {len(entries)} 筆完整母體技術收藏；錯誤種類列已標示且不可重開。"
            if entries
            else "此觀察清單沒有完整母體技術研究收藏。"
        )
        self._refresh_controls()

    @Slot(str)
    def _on_worker_error(self, message: str) -> None:
        worker = self.sender()
        if worker is not self._worker:
            return
        if self._closing or self._active_generation != self._generation:
            return
        first_line = message.splitlines()[0].strip() if message.splitlines() else "讀取失敗"
        if self._operation == "list":
            self.status_label.setText(f"收藏列表讀取失敗，原列表保留：{first_line}")
        else:
            self.status_label.setText(f"唯讀重開失敗，沒有切換研究頁：{first_line}")

    @Slot()
    def _on_worker_cancelled(self) -> None:
        worker = self.sender()
        if worker is self._worker and not self._closing and self._active_generation == self._generation:
            self.status_label.setText("背景收藏讀取已取消；沒有套用舊結果。")

    @Slot()
    def _on_worker_thread_finished(self) -> None:
        worker = self.sender()
        refresh_pending = False
        if worker is self._worker:
            self._worker = None
            self._operation = ""
            self._opening_bookmark_id = ""
            refresh_pending = self._refresh_pending
            self._refresh_pending = False
            self._refresh_controls()
        if isinstance(worker, TaskWorker):
            worker.deleteLater()
        if refresh_pending and not self._closing:
            self.refresh_bookmarks()
