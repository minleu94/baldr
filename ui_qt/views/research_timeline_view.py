"""顯示既有研究原文與精確連結的 Forward 成熟度。"""

from __future__ import annotations

from typing import Any, Callable, Protocol

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app_module.research_session.session_dtos import ResearchStockContextDTO
from app_module.research_timeline_dtos import ResearchTimelineEntry, ResearchTimelineReadResult
from ui_qt.widgets.decision_outcome_journey_widget import (
    DecisionOutcomeJourneyReadPort,
    DecisionOutcomeJourneyWidget,
)
from ui_qt.workers.task_worker import TaskWorker


_KIND_LABELS = {
    "manual": "手動筆記",
    "price": "價格研究",
    "report": "報告判斷",
    "theme": "題材研究",
}


class ResearchTimelineReadPort(Protocol):
    def read(
        self,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> ResearchTimelineReadResult: ...


class ResearchTimelineView(QWidget):
    """把原始筆記、保存版本資訊與受限 Forward 旅程放在同一頁。"""

    openOriginalRequested = Signal(object)
    readyToClose = Signal()
    resultReady = Signal(object)
    readUnavailable = Signal(str)

    def __init__(
        self,
        timeline_service: ResearchTimelineReadPort,
        journey_service: DecisionOutcomeJourneyReadPort | None = None,
        parent: QWidget | None = None,
        *,
        auto_refresh: bool = True,
    ) -> None:
        super().__init__(parent)
        self.timeline_service = timeline_service
        self._generation = 0
        self._entries: tuple[ResearchTimelineEntry, ...] = ()
        self._selected: ResearchTimelineEntry | None = None
        self._selected_identity: tuple[str, str] | None = None
        self._workers: set[TaskWorker] = set()
        self._active_worker: TaskWorker | None = None
        self._closing = False
        self.last_result: ResearchTimelineReadResult | None = None
        self._setup_ui(journey_service)
        if auto_refresh:
            self.refresh()

    def _setup_ui(
        self,
        journey_service: DecisionOutcomeJourneyReadPort | None,
    ) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(6)

        controls = QHBoxLayout()
        self.source_filter = QComboBox(self)
        self.source_filter.setObjectName("researchTimelineSourceFilter")
        self.source_filter.setAccessibleName("研究時間軸來源篩選")
        self.source_filter.addItem("所有來源", "all")
        for kind, label in _KIND_LABELS.items():
            self.source_filter.addItem(label, kind)
        controls.addWidget(self.source_filter)
        self.stock_filter = QLineEdit(self)
        self.stock_filter.setObjectName("researchTimelineStockFilter")
        self.stock_filter.setPlaceholderText("股票代號")
        self.stock_filter.setAccessibleName("依股票代號篩選研究紀錄")
        controls.addWidget(self.stock_filter, 1)
        self.refresh_button = QPushButton("重新讀取", self)
        self.refresh_button.setObjectName("researchTimelineRefresh")
        self.refresh_button.setAccessibleName("重新讀取研究時間軸")
        controls.addWidget(self.refresh_button)
        root.addLayout(controls)

        self.status_label = QLabel("正在讀取原始研究紀錄…", self)
        self.status_label.setObjectName("researchTimelineStatus")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.setObjectName("researchTimelineSplitter")
        self.entries_table = QTableWidget(0, 4, splitter)
        self.entries_table.setObjectName("researchTimelineEntries")
        self.entries_table.setHorizontalHeaderLabels(("來源", "股票", "保存時間", "原文摘要"))
        self.entries_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.entries_table.setSelectionMode(QTableWidget.SingleSelection)
        self.entries_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.entries_table.setAlternatingRowColors(True)
        self.entries_table.setAccessibleName("研究筆記時間軸")
        header = self.entries_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.entries_table.setColumnWidth(2, 175)
        header.setStretchLastSection(True)
        detail = QWidget(splitter)
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(6, 0, 0, 0)
        self.detail_label = QLabel("選取一筆原始研究紀錄", detail)
        self.detail_label.setObjectName("researchTimelineDetailMetadata")
        self.detail_label.setWordWrap(True)
        self.original_text = QTextEdit(detail)
        self.original_text.setObjectName("researchTimelineOriginalText")
        self.original_text.setReadOnly(True)
        self.original_text.setAccessibleName("保存當時的完整原文")
        self.open_original_button = QPushButton("回訪原版本", detail)
        self.open_original_button.setObjectName("researchTimelineOpenOriginal")
        self.open_original_button.setAccessibleName("回訪所選筆記保存時的原版本")
        self.open_original_button.setEnabled(False)
        detail_layout.addWidget(self.detail_label)
        detail_layout.addWidget(self.original_text, 1)
        detail_layout.addWidget(self.open_original_button)
        if journey_service is None:
            self.journey_widget = None
            self.journey_placeholder = QLabel("Forward 成熟度需提供既有唯讀 journey reader。", detail)
            self.journey_placeholder.setObjectName("researchTimelineJourneyUnavailable")
            self.journey_placeholder.setWordWrap(True)
            detail_layout.addWidget(self.journey_placeholder)
        else:
            self.journey_placeholder = QLabel("選取研究紀錄後可查看已連結的後續結果。", detail)
            self.journey_placeholder.setWordWrap(True)
            detail_layout.addWidget(self.journey_placeholder)
            self.journey_widget = DecisionOutcomeJourneyWidget(
                journey_service,
                continuity_controller=None,
                parent=detail,
            )
            self.journey_widget.readyToClose.connect(self._journey_ready_to_close)
            detail_layout.addWidget(self.journey_widget, 1)
            self.journey_widget.hide()
        splitter.addWidget(self.entries_table)
        splitter.addWidget(detail)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([460, 700])
        root.addWidget(splitter, 1)

        self.source_filter.currentIndexChanged.connect(self._apply_filters)
        self.stock_filter.textChanged.connect(self._apply_filters)
        self.refresh_button.clicked.connect(self.refresh)
        self.entries_table.itemSelectionChanged.connect(self._selection_changed)
        self.open_original_button.clicked.connect(self._open_original)

    def refresh(self) -> None:
        if self._closing:
            return
        self._generation += 1
        generation = self._generation
        previous = self._active_worker
        if previous is not None and previous.isRunning():
            previous.cancel(cooperative=True, wait=False)
        worker = TaskWorker(self.timeline_service.read)
        self._workers.add(worker)
        self._active_worker = worker
        self.status_label.setText("正在背景讀取既有研究紀錄…")
        worker.finished.connect(lambda result, current=generation: self._receive(current, result))
        worker.error.connect(lambda message, current=generation: self._receive_error(current, message))
        worker.cancelled.connect(lambda current=generation: self._receive_cancelled(current))
        worker.native_thread_finished.connect(lambda current=worker: self._worker_finished(current))
        worker.start()

    def _receive(self, generation: int, result: object) -> None:
        if self._closing or generation != self._generation:
            return
        if not isinstance(result, ResearchTimelineReadResult):
            self._receive_error(generation, "timeline reader 回傳無效資料")
            return
        self._entries = result.entries
        self.last_result = result
        self._render_entries()
        warning = "；".join(result.warnings)
        if result.limited:
            warning = "已達最多 500 筆的顯示上限。" + (" " + warning if warning else "")
        if not self._entries:
            message = "目前沒有可查看的研究紀錄。"
        else:
            message = f"已讀取 {len(self._entries)} 筆唯讀研究紀錄。"
        if self._selected is not None and not self._selected.result_id:
            warning = (warning + "；" if warning else "") + (
                "此筆原文未連結保存的推薦結果；後續結果尚無可追蹤來源。"
            )
        self.status_label.setText(message + (" " + warning if warning else ""))
        self.resultReady.emit(result)

    def select_entry(self, entry: ResearchTimelineEntry) -> bool:
        """首頁只可選回同次讀取的原紀錄；舊結果不以同ID新原件替代。"""
        if self._closing or not any(current is entry for current in self._entries):
            return False
        self._selected_identity = (entry.kind, entry.record_id)
        with QSignalBlocker(self.source_filter), QSignalBlocker(self.stock_filter):
            self.source_filter.setCurrentIndex(self.source_filter.findData("all"))
            self.stock_filter.clear()
        self._render_entries()
        return self._selected is entry

    def _receive_error(self, generation: int, message: str) -> None:
        if self._closing or generation != self._generation:
            return
        status = f"讀取失敗；保留原畫面：{message}"
        self.status_label.setText(status)
        self.readUnavailable.emit(status)

    def _receive_cancelled(self, generation: int) -> None:
        if not self._closing and generation == self._generation:
            status = "讀取已安全取消；保留目前可用紀錄。"
            self.status_label.setText(status)
            self.readUnavailable.emit(status)

    def _render_entries(self) -> None:
        previous = self._selected_identity
        self.entries_table.clearSelection()
        self.entries_table.setRowCount(0)
        visible = self._filtered_entries()
        restore_row = -1
        for row, entry in enumerate(visible):
            self.entries_table.insertRow(row)
            identity = (entry.kind, entry.record_id)
            summary = entry.text.replace("\n", " ↵ ")[:160]
            values = (_KIND_LABELS.get(entry.kind, entry.kind), entry.stock_code, entry.recorded_at, summary)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                item.setData(Qt.UserRole, identity)
                self.entries_table.setItem(row, column, item)
            if identity == previous:
                restore_row = row
        if restore_row >= 0:
            self.entries_table.selectRow(restore_row)
        elif visible:
            self.entries_table.selectRow(0)
        else:
            self._show_entry(None)

    def _filtered_entries(self) -> tuple[ResearchTimelineEntry, ...]:
        kind = self.source_filter.currentData()
        stock = self.stock_filter.text().strip()
        return tuple(
            entry for entry in self._entries
            if (kind == "all" or entry.kind == kind)
            and (not stock or stock in entry.stock_code)
        )

    def _apply_filters(self, *_args: object) -> None:
        self._render_entries()

    def _selection_changed(self) -> None:
        row = self.entries_table.currentRow()
        visible = self._filtered_entries()
        self._show_entry(visible[row] if 0 <= row < len(visible) else None)

    def _show_entry(self, entry: ResearchTimelineEntry | None) -> None:
        self._selected = entry
        self._selected_identity = None if entry is None else (entry.kind, entry.record_id)
        self.original_text.setPlainText("" if entry is None else entry.text)
        if entry is None:
            self.detail_label.setText("選取一筆原始研究紀錄")
            self.open_original_button.setEnabled(False)
            if self.journey_widget is not None:
                self.journey_widget.set_context(None)
                self.journey_widget.hide()
            if self.journey_placeholder is not None:
                self.journey_placeholder.setText("選取研究紀錄後可查看已連結的後續結果。")
                self.journey_placeholder.show()
            return
        revision = entry.revision_of or "此筆為修訂根"
        stock = entry.stock_code or "不適用"
        data_date = entry.data_date or "原件未提供資料日"
        source_identity = entry.source_identity or "未提供來源 identity"
        displayed_identity = source_identity[:12] + "…" if len(source_identity) == 64 else source_identity
        self.detail_label.setText(
            f"{_KIND_LABELS.get(entry.kind, entry.kind)}｜{stock}｜保存時間 {entry.recorded_at or '未知'}\n"
            f"來源資料日 {data_date}｜來源版本 {displayed_identity}｜前版 {revision}"
        )
        self.detail_label.setToolTip(f"完整來源版本：{source_identity}")
        self.open_original_button.setEnabled(entry.kind in {"price", "report", "theme"})
        if self.journey_widget is not None:
            if entry.result_id and entry.stock_code:
                self.journey_widget.show()
                if self.journey_placeholder is not None:
                    self.journey_placeholder.hide()
                context = ResearchStockContextDTO(
                    stock_code=entry.stock_code,
                    data_date=entry.data_date,
                    result_id=entry.result_id,
                    source_snapshot_id=entry.source_identity,
                    source_id=entry.source_identity,
                    source_kind=entry.kind,
                    source_label=_KIND_LABELS.get(entry.kind, entry.kind),
                    source_workspace="research_timeline",
                )
                self.journey_widget.set_context(context)
            else:
                self.journey_widget.hide()
                if self.journey_placeholder is not None:
                    self.journey_placeholder.setText("此筆原文未連結保存的推薦結果；後續結果尚無可追蹤來源。")
                    self.journey_placeholder.show()
                self.journey_widget.set_context(
                    ResearchStockContextDTO(stock_code=entry.stock_code or "未知")
                    if entry.stock_code else None
                )

    def _open_original(self) -> None:
        entry = self._selected
        if entry is not None and entry.kind in {"price", "report", "theme"}:
            self.openOriginalRequested.emit(entry)

    def request_close(self) -> bool:
        self._closing = True
        self._generation += 1
        workers = [worker for worker in self._workers if worker.isRunning()]
        for worker in workers:
            worker.cancel(cooperative=True, wait=False)
        journey_ready = True
        if self.journey_widget is not None:
            journey_ready = self.journey_widget.request_close()
        if workers or not journey_ready:
            return False
        return True

    def closeEvent(self, event: Any) -> None:  # noqa: N802 - Qt覆寫方法
        if not self.request_close():
            event.ignore()
            return
        super().closeEvent(event)

    def is_busy(self) -> bool:
        return any(worker.isRunning() for worker in self._workers) or bool(
            self.journey_widget is not None and self.journey_widget.is_busy()
        )

    def _worker_finished(self, worker: TaskWorker) -> None:
        self._workers.discard(worker)
        if self._active_worker is worker:
            self._active_worker = None
        worker.deleteLater()
        if self._closing and not self.is_busy():
            self.readyToClose.emit()

    def _journey_ready_to_close(self) -> None:
        if self._closing and not self.is_busy():
            self.readyToClose.emit()


__all__ = ["ResearchTimelineView"]
