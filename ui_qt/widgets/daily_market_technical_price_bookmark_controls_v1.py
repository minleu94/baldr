"""觀察清單中的 F07 價格研究收藏選取與 fresh exact 重開。"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
import re
from typing import Any, Literal, cast

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app_module.daily_market_research_bookmark import DailyMarketResearchBookmarkError
from app_module.daily_market_technical_universe_price_bookmark_v1 import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_BOOKMARK_V1_MAX_BYTES,
    DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_BOOKMARK_V1_SCHEMA,
    DailyMarketTechnicalUniversePriceBookmarkStateV1,
    DailyMarketTechnicalUniversePriceBookmarkV1,
    read_daily_market_technical_universe_price_bookmark_v1,
)
from app_module.watchlist_service import (
    TECHNICAL_UNIVERSE_PRICE_BOOKMARK_SOURCE,
    WatchlistService,
)
from ui_qt.workers.task_worker import TaskWorker


DailyMarketTechnicalPriceBookmarkRestoreResult = Literal["selected", "queued", "rejected"]
DailyMarketTechnicalPriceBookmarkOpenResult = Literal["started", "queued", "rejected"]
_MAX_WATCHLIST_ROWS = 100_000
_MAX_PRICE_BOOKMARKS = 10_000
_MAX_TOTAL_BOOKMARK_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class _PriceBookmarkEntry:
    bookmark_id: str
    stock_code: str
    label: str
    bookmark: DailyMarketTechnicalUniversePriceBookmarkV1 | None = None
    error_code: str = ""
    error_detail: str = ""


def _check_cancel(cancel_callback: Any = None) -> None:
    if cancel_callback is None:
        return
    try:
        cancelled = cancel_callback()
    except Exception as exc:
        raise RuntimeError("technical_price_bookmark_cancel_check_failed") from exc
    if type(cancelled) is not bool:
        raise TypeError("technical_price_bookmark_cancel_callback_invalid")
    if cancelled:
        raise InterruptedError("technical_price_bookmark_cancelled")


def _text(row: Mapping[str, Any], key: str) -> str:
    value = row.get(key)
    return value if isinstance(value, str) else ""


def _is_price_bookmark_candidate(row: Mapping[str, Any]) -> bool:
    payload = row.get("research_bookmark")
    payload_schema = payload.get("schema_version") if isinstance(payload, Mapping) else None
    return (
        row.get("source") == TECHNICAL_UNIVERSE_PRICE_BOOKMARK_SOURCE
        or payload_schema == DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_BOOKMARK_V1_SCHEMA
    )


def _invalid_entry(
    *, bookmark_id: str, stock_code: str, index: int, code: str, detail: str = "",
) -> _PriceBookmarkEntry:
    display_code = stock_code or f"第 {index + 1} 筆"
    return _PriceBookmarkEntry(
        bookmark_id=bookmark_id,
        stock_code=stock_code,
        label=f"{display_code}｜原價格條件收藏無法核驗（{code}）",
        error_code=code,
        error_detail=(detail or code)[:2048],
    )


def _bookmark_label(bookmark: DailyMarketTechnicalUniversePriceBookmarkV1) -> str:
    selection = bookmark.selected
    price = selection.close_price if selection.price_state == "pass" else "未知"
    date = selection.observation_date or selection.query.source.decision_date.isoformat()
    state = "保存時有價格" if selection.price_state == "pass" else "保存時價格未知"
    return f"{selection.query.source.decision_date.isoformat()}｜{bookmark.stock_code}｜{state} {price}｜觀測 {date}"


def _list_price_bookmarks(
    service: WatchlistService,
    watchlist_id: str,
    cancel_callback: Any = None,
) -> tuple[_PriceBookmarkEntry, ...]:
    """只列出精確 F07 typed 收藏；格式錯誤的候選仍保留為診斷列。"""

    _check_cancel(cancel_callback)
    rows = service.get_stocks(watchlist_id)
    _check_cancel(cancel_callback)
    if not isinstance(rows, list) or len(rows) > _MAX_WATCHLIST_ROWS:
        raise ValueError("technical_price_bookmark_watchlist_row_limit_or_shape")
    normalized_rows: list[Mapping[str, Any]] = []
    for row in rows:
        _check_cancel(cancel_callback)
        if not isinstance(row, Mapping):
            raise ValueError("technical_price_bookmark_watchlist_row_invalid")
        normalized_rows.append(row)

    candidates = tuple(
        (index, row)
        for index, row in enumerate(normalized_rows)
        if _is_price_bookmark_candidate(row)
    )
    if len(candidates) > _MAX_PRICE_BOOKMARKS:
        raise ValueError("technical_price_bookmark_count_limit")
    identity_counts = Counter(_text(row, "source_id") for row in normalized_rows if _text(row, "source_id"))
    entries: list[_PriceBookmarkEntry] = []
    total_bytes = 0
    for index, row in candidates:
        _check_cancel(cancel_callback)
        stock_code = _text(row, "stock_code")
        bookmark_id = _text(row, "source_id")
        payload = row.get("research_bookmark")
        schema = payload.get("schema_version") if isinstance(payload, Mapping) else ""
        if not bookmark_id:
            entries.append(_invalid_entry(
                bookmark_id=f"missing-source-id-{index}", stock_code=stock_code,
                index=index, code="technical_price_bookmark_source_id_missing",
            ))
            continue
        if identity_counts[bookmark_id] != 1:
            entries.append(_invalid_entry(
                bookmark_id=bookmark_id, stock_code=stock_code, index=index,
                code="technical_price_bookmark_identity_ambiguous",
            ))
            continue
        if (
            row.get("source") != TECHNICAL_UNIVERSE_PRICE_BOOKMARK_SOURCE
            or schema != DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_BOOKMARK_V1_SCHEMA
        ):
            entries.append(_invalid_entry(
                bookmark_id=bookmark_id, stock_code=stock_code, index=index,
                code="technical_price_bookmark_source_schema_mismatch",
            ))
            continue
        try:
            bookmark = service.get_research_bookmark(bookmark_id, watchlist_id)
        except Exception as exc:
            code = str(getattr(exc, "code", "technical_price_bookmark_decode_failed"))
            entries.append(_invalid_entry(
                bookmark_id=bookmark_id, stock_code=stock_code, index=index,
                code=code, detail=f"{code}: {exc}",
            ))
            continue
        if type(bookmark) is not DailyMarketTechnicalUniversePriceBookmarkV1:
            entries.append(_invalid_entry(
                bookmark_id=bookmark_id, stock_code=stock_code, index=index,
                code="technical_price_bookmark_typed_payload_required",
            ))
            continue
        if (
            bookmark.bookmark_id != bookmark_id
            or bookmark.source_id != bookmark_id
            or bookmark.stock_code != stock_code
            or _text(row, "stock_name") != bookmark.stock_code
        ):
            entries.append(_invalid_entry(
                bookmark_id=bookmark_id, stock_code=stock_code, index=index,
                code="technical_price_bookmark_watchlist_identity_mismatch",
            ))
            continue
        payload_bytes = len(bookmark.to_json().encode("utf-8"))
        total_bytes += payload_bytes
        if payload_bytes > DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_BOOKMARK_V1_MAX_BYTES or total_bytes > _MAX_TOTAL_BOOKMARK_BYTES:
            raise ValueError("technical_price_bookmark_total_byte_limit")
        entries.append(_PriceBookmarkEntry(
            bookmark_id=bookmark.bookmark_id,
            stock_code=bookmark.stock_code,
            label=_bookmark_label(bookmark),
            bookmark=bookmark,
        ))
    _check_cancel(cancel_callback)
    return tuple(entries)


def _read_price_bookmark_state(
    service: WatchlistService,
    bookmark_id: str,
    watchlist_id: str,
    expected: DailyMarketTechnicalUniversePriceBookmarkV1,
    cancel_callback: Any = None,
) -> DailyMarketTechnicalUniversePriceBookmarkStateV1:
    """在同一 worker 內核對 watchlist identity 前後並 fresh 重開 exact bookmark。"""

    _check_cancel(cancel_callback)
    current = service.get_research_bookmark(bookmark_id, watchlist_id)
    if type(current) is not DailyMarketTechnicalUniversePriceBookmarkV1:
        raise ValueError("technical_price_bookmark_exact_typed_payload_required")
    expected_dict = expected.to_dict()
    if (
        current.bookmark_id != bookmark_id
        or current.to_dict() != expected_dict
        or current.stock_code != expected.stock_code
    ):
        raise ValueError("technical_price_bookmark_changed_before_reopen")
    _check_cancel(cancel_callback)
    state = read_daily_market_technical_universe_price_bookmark_v1(
        current,
        cancel_callback=cancel_callback,
    )
    if (
        not isinstance(state, DailyMarketTechnicalUniversePriceBookmarkStateV1)
        or state.bookmark.to_dict() != expected_dict
        or state.selected.selection.to_dict() != expected.selected.to_dict()
    ):
        raise ValueError("technical_price_bookmark_reader_result_mismatch")
    _check_cancel(cancel_callback)
    terminal = service.get_research_bookmark(bookmark_id, watchlist_id)
    if (
        type(terminal) is not DailyMarketTechnicalUniversePriceBookmarkV1
        or terminal.to_dict() != expected_dict
    ):
        raise ValueError("technical_price_bookmark_changed_during_reopen")
    _check_cancel(cancel_callback)
    return state


class DailyMarketTechnicalPriceBookmarkControlsV1(QWidget):
    """背景列出原價格條件收藏，並以其保存來源 fresh 重開研究。"""

    stateReady = Signal(object)
    statusChanged = Signal(str)
    cancelRequested = Signal()

    def __init__(
        self,
        watchlist_service: WatchlistService,
        *,
        watchlist_id: str = "default",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.watchlist_service = watchlist_service
        self.watchlist_id = watchlist_id
        self._generation = 0
        self._active_generation = 0
        self._selection_generation = 0
        self._opening_selection_generation = 0
        self._opening_bookmark_id = ""
        self._opening_bookmark: DailyMarketTechnicalUniversePriceBookmarkV1 | None = None
        self._worker: TaskWorker | None = None
        self._operation = ""
        self._list_worker_succeeded = False
        self._refresh_pending = False
        self._restore_selection_id = ""
        self._pending_open_bookmark_id = ""
        self._entries: tuple[_PriceBookmarkEntry, ...] = ()
        self._has_loaded_list = False
        self._closing = False
        self._setup_ui()

    @property
    def busy(self) -> bool:
        return self._worker is not None

    @property
    def workers_remaining(self) -> int:
        return int(self._worker is not None and self._worker.isRunning())

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        title = QLabel("原價格條件研究收藏")
        title.setObjectName("dailyMarketTechnicalPriceBookmarkTitleV1")
        layout.addWidget(title)

        self.bookmarks = QListWidget(self)
        self.bookmarks.setObjectName("dailyMarketTechnicalPriceBookmarksV1")
        self.bookmarks.setAccessibleName("原價格條件研究收藏列表")
        self.bookmarks.currentRowChanged.connect(self._selection_changed)
        layout.addWidget(self.bookmarks, 1)

        self.refresh_button = QPushButton("重新整理價格收藏", self)
        self.refresh_button.setObjectName("dailyMarketTechnicalPriceBookmarkRefreshV1")
        self.open_button = QPushButton("重開所選價格研究", self)
        self.open_button.setObjectName("dailyMarketTechnicalPriceBookmarkOpenV1")
        self.cancel_button = QPushButton("取消目前讀取", self)
        self.cancel_button.setObjectName("dailyMarketTechnicalPriceBookmarkCancelV1")
        for button in (self.refresh_button, self.open_button, self.cancel_button):
            button.setMinimumHeight(32)
            layout.addWidget(button)

        self.status_label = QLabel("只列出原價格條件收藏；重開沿收藏保存的條件、頁面與資料來源。", self)
        self.status_label.setObjectName("dailyMarketTechnicalPriceBookmarkStatusV1")
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status_label)

        self.diagnostic_text = QPlainTextEdit(self)
        self.diagnostic_text.setObjectName("dailyMarketTechnicalPriceBookmarkDiagnosticV1")
        self.diagnostic_text.setAccessibleName("原價格條件收藏來源與拒絕原因")
        self.diagnostic_text.setReadOnly(True)
        self.diagnostic_text.setMaximumBlockCount(100)
        self.diagnostic_text.setMinimumHeight(88)
        self.diagnostic_text.setPlaceholderText("選取一列可查看保存時的條件、來源資料與限制。")
        layout.addWidget(self.diagnostic_text, 1)

        self.refresh_button.clicked.connect(self.refresh_bookmarks)
        self.open_button.clicked.connect(self.open_selected)
        self.cancel_button.clicked.connect(self.cancel)
        self._refresh_controls()

    def refresh_bookmarks(self) -> None:
        if self._closing:
            return
        if self._worker is not None:
            self._refresh_pending = True
            self._status("目前唯讀工作結束後會合併刷新一次收藏列表。")
            return
        worker = TaskWorker(_list_price_bookmarks, self.watchlist_service, self.watchlist_id)
        self._start_worker(worker, "list")
        self._status("正在背景讀取觀察清單中的原價格條件收藏；目前列表會保留到新結果完成。")

    def open_selected(self) -> None:
        if not self._can_start():
            return
        entry = self._current_entry()
        if entry is None:
            self._status("請先選取一筆原價格條件收藏。")
            return
        if entry.error_code or entry.bookmark is None or not entry.bookmark_id:
            self._set_invalid_status(entry)
            return
        self._opening_bookmark_id = entry.bookmark_id
        self._opening_bookmark = entry.bookmark
        self._opening_selection_generation = self._selection_generation
        worker = TaskWorker(
            _read_price_bookmark_state,
            self.watchlist_service,
            entry.bookmark_id,
            self.watchlist_id,
            entry.bookmark,
        )
        self._start_worker(worker, "open")
        self._status("正在背景依收藏保存的價格條件與來源資料重新核驗；不查目前行情。")

    def open_bookmark(self, bookmark_id: str) -> DailyMarketTechnicalPriceBookmarkOpenResult:
        """按明示身份開啟；未載入或刷新中時等原工作結束再讀新 typed 列。"""

        if (
            self._closing
            or type(bookmark_id) is not str
            or re.fullmatch(r"[0-9a-f]{64}", bookmark_id) is None
        ):
            self._status("拒絕開啟原價格條件收藏：身份格式無效或控制項已關閉。")
            return "rejected"
        if self._worker is not None:
            self._pending_open_bookmark_id = bookmark_id
            if self._operation != "list":
                self._generation += 1
                self._worker.cancel(cooperative=True, wait=False)
                self._status("已排定精確收藏；等待目前工作安全停止，再刷新並重開一次。")
            else:
                self._status("正在更新收藏列表；完成後會按指定身份重開一次。")
            self._refresh_controls()
            return "queued"
        if self._has_loaded_list:
            matches = tuple(entry for entry in self._entries if entry.bookmark_id == bookmark_id)
            if matches:
                if len(matches) != 1 or matches[0].bookmark is None or matches[0].error_code:
                    self._apply_exact_selection(bookmark_id)
                    return "rejected"
                if not self._apply_exact_selection(bookmark_id):
                    return "rejected"
                self.open_selected()
                return "started" if self._worker is not None else "rejected"
        self._pending_open_bookmark_id = bookmark_id
        self.refresh_bookmarks()
        if self._worker is None:
            self._pending_open_bookmark_id = ""
            return "rejected"
        self._status("正在刷新指定收藏；列表完成後會沿新核對的 typed 內容 fresh 重開。")
        return "queued"

    def restore_selection(self, bookmark_id: str) -> Literal["selected", "queued", "rejected"]:
        if self._closing or type(bookmark_id) is not str or not bookmark_id or bookmark_id != bookmark_id.strip():
            self._status("拒絕恢復價格收藏選取：bookmark_id 格式無效。")
            return "rejected"
        if self._worker is not None:
            if self._operation == "list" or self._refresh_pending:
                self._restore_selection_id = bookmark_id
                self._status("已排定精確價格收藏選取；列表更新後會核對身份。")
                return "queued"
            self._status("目前背景讀取尚未完成；未變更價格收藏選取。")
            return "rejected"
        if not self._has_loaded_list:
            self._restore_selection_id = bookmark_id
            self.refresh_bookmarks()
            if self._worker is None:
                self._restore_selection_id = ""
                return "rejected"
            self._status("已排定精確價格收藏選取；列表完成後會核對身份。")
            return "queued"
        return "selected" if self._apply_exact_selection(bookmark_id) else "rejected"

    def cancel(self) -> None:
        self._refresh_pending = False
        self._restore_selection_id = ""
        self._pending_open_bookmark_id = ""
        worker = self._worker
        if worker is None:
            return
        self._generation += 1
        worker.cancel(cooperative=True, wait=False)
        self._status("已要求取消；等待讀取安全停止，晚到結果會丟棄。")
        self._refresh_controls()
        self.cancelRequested.emit()

    def begin_shutdown(self) -> bool:
        self._closing = True
        self._generation += 1
        self._refresh_pending = False
        self._restore_selection_id = ""
        self._pending_open_bookmark_id = ""
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.cancel(cooperative=True, wait=False)
            self.cancelRequested.emit()
        self._refresh_controls()
        return worker is None or not worker.isRunning()

    def closeEvent(self, event: Any) -> None:  # noqa: N802 - Qt callback name.
        self.begin_shutdown()
        event.accept()

    def _start_worker(self, worker: TaskWorker, operation: str) -> None:
        self._generation += 1
        self._active_generation = self._generation
        self._operation = operation
        if operation == "list":
            self._list_worker_succeeded = False
        self._worker = worker
        worker.finished.connect(self._on_worker_finished)
        worker.error.connect(self._on_worker_error)
        worker.cancelled.connect(self._on_worker_cancelled)
        worker.native_thread_finished.connect(self._on_worker_thread_finished)
        self._refresh_controls()
        worker.start()

    @Slot(object)
    def _on_worker_finished(self, value: object) -> None:
        worker = self.sender()
        if worker is not self._worker or self._closing or self._active_generation != self._generation:
            return
        if self._operation == "list":
            if not isinstance(value, tuple) or any(type(item) is not _PriceBookmarkEntry for item in value):
                self._status("價格收藏列表格式錯誤；舊列表保留。")
                return
            self._show_entries(cast(tuple[_PriceBookmarkEntry, ...], value))
            self._list_worker_succeeded = True
            return
        if self._operation == "open":
            entry = self._current_entry()
            expected = self._opening_bookmark
            if (
                not isinstance(value, DailyMarketTechnicalUniversePriceBookmarkStateV1)
                or expected is None
                or entry is None
                or entry.error_code
                or entry.bookmark_id != self._opening_bookmark_id
                or entry.bookmark is None
                or entry.bookmark.to_dict() != expected.to_dict()
                or value.bookmark.to_dict() != expected.to_dict()
                or self._selection_generation != self._opening_selection_generation
            ):
                self._status("收藏或選取已變更；fresh 重開結果未發布。")
                return
            value.bookmark.to_json()
            self._status(
                f"已沿原保存來源重新核驗 {value.bookmark.stock_code}；"
                f"保存時決策日 {value.bookmark.selected.query.source.decision_date.isoformat()}。"
                "來源資料沒有可得時間，不代表目前行情或可交易資格。"
            )
            self.stateReady.emit(value)
            return
        self._status("未知的價格收藏背景工作；未發布狀態。")

    @Slot(str)
    def _on_worker_error(self, message: str) -> None:
        worker = self.sender()
        if worker is not self._worker or self._closing or self._active_generation != self._generation:
            return
        first_line = message.splitlines()[0].strip() if message.splitlines() else "reader_error"
        self.diagnostic_text.setPlainText(message[:16_384])
        if self._operation == "list":
            self._status(f"價格收藏列表讀取失敗；舊列表保留（{first_line}）。")
        else:
            self._status(f"原價格條件收藏重開失敗；未發出狀態（{first_line}）。")

    @Slot()
    def _on_worker_cancelled(self) -> None:
        worker = self.sender()
        if worker is self._worker and not self._closing and self._active_generation == self._generation:
            self._status("價格收藏讀取已取消；沒有套用或發出晚到結果。")

    @Slot()
    def _on_worker_thread_finished(self) -> None:
        worker = self.sender()
        if worker is not self._worker:
            if isinstance(worker, TaskWorker):
                worker.deleteLater()
            return
        refresh_pending = False
        finished_operation = self._operation
        if worker is self._worker:
            self._worker = None
            self._operation = ""
            self._opening_bookmark_id = ""
            self._opening_bookmark = None
            refresh_pending = self._refresh_pending
            self._refresh_pending = False
            self._refresh_controls()
        if isinstance(worker, TaskWorker):
            worker.deleteLater()
        if self._pending_open_bookmark_id and not self._closing:
            if finished_operation == "list" and self._list_worker_succeeded and not refresh_pending:
                self._open_pending_bookmark_from_list()
            elif finished_operation == "list" and not self._list_worker_succeeded:
                self._pending_open_bookmark_id = ""
                self._status("收藏列表刷新失敗；指定收藏沒有重開。")
            else:
                self.refresh_bookmarks()
            return
        if refresh_pending and not self._closing:
            self.refresh_bookmarks()

    def _open_pending_bookmark_from_list(self) -> None:
        bookmark_id = self._pending_open_bookmark_id
        self._pending_open_bookmark_id = ""
        if not bookmark_id or not self._apply_exact_selection(bookmark_id):
            self._status(f"刷新後找不到可核驗的指定收藏 {bookmark_id}；沒有改開其他列。")
            return
        self.open_selected()

    def _show_entries(self, entries: tuple[_PriceBookmarkEntry, ...]) -> None:
        current = self._current_entry()
        previous_id = (
            current.bookmark_id
            if current is not None and current.bookmark is not None and not current.error_code
            else ""
        )
        restore_id = self._restore_selection_id or previous_id
        self._restore_selection_id = restore_id if self._refresh_pending else ""
        self.bookmarks.clear()
        self.bookmarks.setCurrentRow(-1)
        for entry in entries:
            item = QListWidgetItem(entry.label, self.bookmarks)
            item.setData(Qt.ItemDataRole.UserRole, entry)
            if entry.bookmark is not None:
                item.setToolTip(self._bookmark_diagnostic(entry.bookmark))
            if entry.error_code:
                item.setForeground(Qt.GlobalColor.darkRed)
        self._entries = entries
        self._has_loaded_list = True
        restored = self._apply_exact_selection(restore_id) if restore_id else True
        invalid_count = sum(bool(entry.error_code) for entry in entries)
        if not entries:
            self._status("此觀察清單沒有原價格條件研究收藏。")
        else:
            self._status(f"已列出 {len(entries)} 筆原價格條件收藏；{invalid_count} 筆身份或格式無法核驗，仍保留顯示。")
        if restore_id and not restored:
            self._status(f"列表已更新，但無法恢復收藏 {restore_id}；未改選其他列。")
        self._refresh_controls()

    def _apply_exact_selection(self, bookmark_id: str) -> bool:
        matches = [
            (index, entry)
            for index, entry in enumerate(self._entries)
            if entry.bookmark_id == bookmark_id
        ]
        if len(matches) == 1 and matches[0][1].bookmark is not None and not matches[0][1].error_code:
            self.bookmarks.setCurrentRow(matches[0][0])
            return True
        self.bookmarks.setCurrentRow(-1)
        if not matches:
            code = "technical_price_bookmark_restore_target_missing"
            detail = f"找不到指定收藏身份 {bookmark_id}。"
        elif len(matches) > 1:
            code = "technical_price_bookmark_restore_target_ambiguous"
            detail = "指定身份對應多列，拒絕猜選。"
        else:
            code = matches[0][1].error_code or "technical_price_bookmark_restore_target_invalid"
            detail = matches[0][1].error_detail or code
        self.diagnostic_text.setPlainText(f"拒絕恢復選取：{detail}\n拒絕代碼：{code}")
        self._refresh_controls()
        return False

    def _selection_changed(self, _row: int) -> None:
        self._selection_generation += 1
        entry = self._current_entry()
        if entry is None:
            self.diagnostic_text.clear()
        elif entry.error_code or entry.bookmark is None:
            self.diagnostic_text.setPlainText(
                f"股票：{entry.stock_code or '未知'}\n收藏身份：{entry.bookmark_id}\n"
                f"拒絕原因：{entry.error_detail or entry.error_code}"
            )
        else:
            self.diagnostic_text.setPlainText(self._bookmark_diagnostic(entry.bookmark))
        if (
            self._worker is not None
            and self._operation == "open"
            and self._selection_generation != self._opening_selection_generation
        ):
            self._generation += 1
            self._worker.cancel(cooperative=True, wait=False)
            self._status("收藏選取已變更；正在取消舊來源重開並丟棄晚到結果。")
        self._refresh_controls()

    def _bookmark_diagnostic(self, bookmark: DailyMarketTechnicalUniversePriceBookmarkV1) -> str:
        selection = bookmark.selected
        query = selection.query
        lines = [
            f"股票：{bookmark.stock_code}",
            f"收藏身份：{bookmark.bookmark_id}",
            f"保存決策日：{query.source.decision_date.isoformat()}",
            f"保存時價格：{selection.close_price or '未知'} TWD／股（狀態：{selection.price_state}）",
            f"觀測日：{selection.observation_date or '未知'}；原始列 fingerprint：{selection.raw_row_fingerprint_sha256 or '未知'}",
            f"保存來源標記（批次／計畫／收據）：{query.source.generation_identity_sha256}／{query.source.plan_identity_sha256}／{query.source.receipt_identity_sha256}",
            f"來源識別／價格索引：{query.source.source_identity_sha256}／{query.source.price_index_identity_sha256}",
            f"原篩選條件／頁次／股票錨點：{query.query_identity_sha256}／{selection.page_identity_sha256}／{selection.selection_identity_sha256}",
            f"比較收藏：{len(bookmark.comparison_selections)} 欄；捲動位置：{bookmark.scroll_position}",
            "來源資料沒有可得時間；只重讀收藏明示的保存資料，不代表目前行情或可交易資格。",
        ]
        if selection.price_state == "unknown":
            lines.append("保存時價格未知；收藏不會用其他日期或目前行情補值。")
        return "\n".join(lines)

    def _current_entry(self) -> _PriceBookmarkEntry | None:
        item = self.bookmarks.currentItem()
        value = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        return value if isinstance(value, _PriceBookmarkEntry) else None

    def _can_start(self) -> bool:
        if self._closing:
            self._status("價格收藏控制項已關閉，沒有啟動工作。")
            return False
        if self._worker is not None:
            self._status("目前仍有背景工作；請等待或取消後再操作。")
            return False
        return True

    def _set_invalid_status(self, entry: _PriceBookmarkEntry) -> None:
        self.diagnostic_text.setPlainText(entry.error_detail or entry.error_code)
        self._status(f"此列無法 exact 核驗，已拒絕重開（{entry.error_code}）。")

    def _refresh_controls(self) -> None:
        idle = self._worker is None and not self._closing
        entry = self._current_entry()
        actionable = (
            entry is not None
            and entry.bookmark is not None
            and not entry.error_code
            and bool(entry.bookmark_id)
        )
        self.refresh_button.setEnabled(idle)
        self.open_button.setEnabled(idle and actionable)
        self.cancel_button.setEnabled(self._worker is not None and not self._closing)

    def _status(self, value: str) -> None:
        self.status_label.setText(value)
        self.statusChanged.emit(value)


__all__ = ["DailyMarketTechnicalPriceBookmarkControlsV1"]
