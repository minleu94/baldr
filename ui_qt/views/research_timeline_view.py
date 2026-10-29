"""顯示既有研究原文與精確連結的 Forward 成熟度。"""

from __future__ import annotations

from ui_qt.research_display import research_saved_time

from typing import Any, Callable, Protocol

from PySide6.QtCore import QSignalBlocker, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
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

from app_module.dtos.decision_continuity_dtos import DecisionContinuityRevision
from app_module.research_session.session_dtos import ResearchStockContextDTO
from app_module.research_evidence_comparison_dtos import ResearchEvidenceComparison
from app_module.research_timeline_dtos import ResearchTimelineEntry, ResearchTimelineReadResult
from ui_qt.widgets.decision_outcome_journey_widget import (
    DecisionOutcomeJourneyReadPort,
    DecisionOutcomeJourneyWidget,
)
from ui_qt.widgets.research_evidence_comparison_widget import ResearchEvidenceComparisonWidget
from ui_qt.workers.task_worker import TaskWorker


_KIND_LABELS = {
    "manual": "手動筆記",
    "decision": "研究決定",
    "price": "價格研究",
    "report": "報告判斷",
    "theme": "題材研究",
}


class ResearchTimelineReadPort(Protocol):
    def read(
        self,
        cancel_callback: Callable[[], bool] | None = None,
        *,
        search_query: str = "",
    ) -> ResearchTimelineReadResult: ...


class ResearchTimelineView(QWidget):
    """把原始筆記、保存版本資訊與受限 Forward 旅程放在同一頁。"""

    openOriginalRequested = Signal(object)
    readyToClose = Signal()
    resultReady = Signal(object)
    readUnavailable = Signal(str)
    compareEvidenceRequested = Signal(object)
    paperPrerequisitesRequested = Signal(object)

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
        self._comparison_loading = False
        self._evidence_comparison_revision = 0
        self.last_result: ResearchTimelineReadResult | None = None
        self._full_history_limited = False
        self._pending_search_query = ""
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

        controls_group = QGroupBox("查找已保存研究紀錄", self)
        controls_group.setObjectName("researchTimelineSearchControls")
        controls = QHBoxLayout(controls_group)
        controls.setContentsMargins(10, 7, 10, 7)
        controls.setSpacing(6)
        self.source_filter = QComboBox(self)
        self.source_filter.setObjectName("researchTimelineSourceFilter")
        self.source_filter.setAccessibleName("研究時間軸來源篩選")
        self.source_filter.addItem("所有來源", "all")
        for kind, label in _KIND_LABELS.items():
            self.source_filter.addItem(label, kind)
        controls.addWidget(QLabel("來源", controls_group))
        controls.addWidget(self.source_filter)
        self.stock_filter = QLineEdit(self)
        self.stock_filter.setObjectName("researchTimelineStockFilter")
        self.stock_filter.setPlaceholderText("股票代號或完整 result ID")
        self.stock_filter.setAccessibleName("依股票代號或 result ID 篩選研究紀錄")
        controls.addWidget(QLabel("股票／結果 ID", controls_group))
        controls.addWidget(self.stock_filter, 1)
        self.refresh_button = QPushButton("重新讀取", self)
        self.refresh_button.setObjectName("researchTimelineRefresh")
        self.refresh_button.setAccessibleName("重新讀取研究時間軸")
        controls.addWidget(self.refresh_button)
        root.addWidget(controls_group)

        self.search_hint_label = QLabel(
            "研究決定會保留在 Journal，不依賴今日 Advice 清單；貼上完整 result ID 可找回同一筆。",
            self,
        )
        self.search_hint_label.setObjectName("researchTimelineSearchHint")
        self.search_hint_label.setWordWrap(True)
        self.search_hint_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        root.addWidget(self.search_hint_label)

        self.status_label = QLabel("正在讀取原始研究紀錄…", self)
        self.status_label.setObjectName("researchTimelineStatus")
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.setObjectName("researchTimelineSplitter")
        entries_panel = QWidget(splitter)
        entries_layout = QVBoxLayout(entries_panel)
        entries_layout.setContentsMargins(0, 0, 0, 0)
        entries_title = QLabel("研究紀錄清單", entries_panel)
        entries_title.setObjectName("researchTimelineEntriesHeading")
        entries_layout.addWidget(entries_title)
        self.entries_table = QTableWidget(0, 4, entries_panel)
        self.entries_table.setObjectName("researchTimelineEntries")
        self.entries_table.setHorizontalHeaderLabels(("來源", "股票", "保存時間", "原文摘要"))
        self.entries_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.entries_table.setSelectionMode(QTableWidget.SingleSelection)
        self.entries_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.entries_table.setAlternatingRowColors(True)
        self.entries_table.setAccessibleName("研究紀錄時間軸")
        header = self.entries_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.entries_table.setColumnWidth(2, 175)
        header.setStretchLastSection(True)
        entries_layout.addWidget(self.entries_table, 1)
        detail = QWidget(splitter)
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(6, 0, 0, 0)
        detail_title = QLabel("所選紀錄與延伸操作", detail)
        detail_title.setObjectName("researchTimelineDetailHeading")
        detail_layout.addWidget(detail_title)
        self.detail_label = QLabel("選取一筆研究紀錄", detail)
        self.detail_label.setObjectName("researchTimelineDetailMetadata")
        self.detail_label.setTextFormat(Qt.TextFormat.PlainText)
        self.detail_label.setWordWrap(True)
        self.original_text = QTextEdit(detail)
        self.original_text.setObjectName("researchTimelineOriginalText")
        self.original_text.setReadOnly(True)
        self.original_text.setAccessibleName("所選研究紀錄內容（唯讀）")
        self.open_original_button = QPushButton("回訪原版本", detail)
        self.open_original_button.setObjectName("researchTimelineOpenOriginal")
        self.open_original_button.setAccessibleName("回訪所選筆記保存時的原版本")
        self.open_original_button.setEnabled(False)
        detail_layout.addWidget(self.detail_label)
        detail_layout.addWidget(self.original_text, 1)
        detail_layout.addWidget(self.open_original_button)
        self.compare_evidence_button = QPushButton("對照目前可讀資料", detail)
        self.compare_evidence_button.setObjectName("researchTimelineCompareEvidence")
        self.compare_evidence_button.setAccessibleName("對照所選紀錄的固定證據與目前可讀資料")
        self.compare_evidence_button.setEnabled(False)
        self.paper_prerequisites_button = QPushButton("檢查 Paper 條件", detail)
        self.paper_prerequisites_button.setObjectName("researchTimelinePaperPrerequisites")
        self.paper_prerequisites_button.setAccessibleName("檢查所選研究紀錄的 Paper 條件")
        self.paper_prerequisites_button.setEnabled(False)
        evidence_actions = QHBoxLayout()
        evidence_actions.addWidget(self.compare_evidence_button)
        evidence_actions.addWidget(self.paper_prerequisites_button)
        detail_layout.addLayout(evidence_actions)
        self.evidence_comparison_widget = ResearchEvidenceComparisonWidget(detail)
        self.evidence_comparison_widget.setMinimumHeight(150)
        detail_layout.addWidget(self.evidence_comparison_widget, 1)
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
        splitter.addWidget(entries_panel)
        splitter.addWidget(detail)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([460, 700])
        root.addWidget(splitter, 1)

        self.source_filter.currentIndexChanged.connect(self._apply_filters)
        self.stock_filter.textChanged.connect(self._stock_filter_changed)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self._search_full_history)
        self.refresh_button.clicked.connect(self.refresh)
        self.entries_table.itemSelectionChanged.connect(self._selection_changed)
        self.open_original_button.clicked.connect(self._open_original)
        self.compare_evidence_button.clicked.connect(self._request_evidence_comparison)
        self.paper_prerequisites_button.clicked.connect(self._request_paper_prerequisites)

    def refresh(self, *, search_query: str | None = None) -> None:
        if self._closing:
            return
        query = (
            self.stock_filter.text().strip()
            if search_query is None and self._full_history_limited
            else str(search_query or "").strip()
        )
        self._pending_search_query = query
        self._clear_evidence_comparison("重新讀取後需重新選取並對照資料。")
        self.compare_evidence_button.setEnabled(False)
        self.paper_prerequisites_button.setEnabled(False)
        self._generation += 1
        generation = self._generation
        previous = self._active_worker
        if previous is not None and previous.isRunning():
            previous.cancel(cooperative=True, wait=False)
        worker = (
            TaskWorker(self.timeline_service.read, search_query=query)
            if query
            else TaskWorker(self.timeline_service.read)
        )
        self._workers.add(worker)
        self._active_worker = worker
        self.status_label.setText(
            "正在完整 Journal 歷史中搜尋…" if query else "正在背景讀取既有研究紀錄…"
        )
        worker.finished.connect(lambda result, current=generation: self._receive(current, result))
        worker.error.connect(lambda message, current=generation: self._receive_error(current, message))
        worker.cancelled.connect(lambda current=generation: self._receive_cancelled(current))
        worker.native_thread_finished.connect(lambda current=worker: self._worker_finished(current))
        worker.start()

    def search_result_id(self, result_id: str) -> bool:
        """在研究時間軸以 Advice 的保存結果 ID 篩選／搜尋完整歷史。"""

        query = str(result_id or "").strip()
        if self._closing or not query:
            return False
        self.stock_filter.setText(query)
        if self._full_history_limited:
            self._search_timer.stop()
            self.refresh(search_query=query)
        return True

    def _receive(self, generation: int, result: object) -> None:
        if self._closing or generation != self._generation:
            return
        if not isinstance(result, ResearchTimelineReadResult):
            self._receive_error(generation, "timeline reader 回傳無效資料")
            return
        self._entries = result.entries
        self.last_result = result
        if not self._pending_search_query:
            self._full_history_limited = result.limited
            if self._full_history_limited and self.stock_filter.text().strip():
                self._search_timer.start()
        self._render_entries()
        warning = "；".join(result.warnings)
        if result.limited:
            limit_message = (
                "搜尋命中超過 500 筆，顯示最新 500 筆；可用完整 result ID 縮小範圍。"
                if self._pending_search_query
                else "已達 500 筆清單上限；輸入股票代號或 result ID 可搜尋完整 Journal 歷史。"
            )
            warning = limit_message + (" " + warning if warning else "")
        query = self.stock_filter.text().strip()
        visible_count = len(self._filtered_entries())
        if query:
            if self._pending_search_query == query:
                message = (
                    f"完整 Journal 歷史中沒有符合「{query}」的研究紀錄。"
                    if not self._entries
                    else f"完整 Journal 搜尋「{query}」找到 {visible_count} 筆研究紀錄。"
                )
            elif result.limited:
                message = (
                    f"目前已載入的最新紀錄中，「{query}」符合 {visible_count} 筆；"
                    "正在搜尋完整 Journal 歷史。"
                )
            else:
                message = (
                    f"完整已載入的研究紀錄中沒有符合「{query}」的資料。"
                    if visible_count == 0
                    else f"完整已載入的研究紀錄中，「{query}」符合 {visible_count} 筆。"
                )
        elif not self._entries:
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
        selected_is_comparable = (
            self._selected is not None and self._selected.kind != "decision"
        )
        self.compare_evidence_button.setEnabled(selected_is_comparable)
        self.paper_prerequisites_button.setEnabled(selected_is_comparable)
        self.readUnavailable.emit(status)

    def _receive_cancelled(self, generation: int) -> None:
        if not self._closing and generation == self._generation:
            status = "讀取已安全取消；保留目前可用紀錄。"
            self.status_label.setText(status)
            selected_is_comparable = (
                self._selected is not None and self._selected.kind != "decision"
            )
            self.compare_evidence_button.setEnabled(selected_is_comparable)
            self.paper_prerequisites_button.setEnabled(selected_is_comparable)
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
            values = (_KIND_LABELS.get(entry.kind, entry.kind), entry.stock_code, research_saved_time(entry.recorded_at), summary)
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
        query = self.stock_filter.text().strip()
        return tuple(
            entry for entry in self._entries
            if (kind == "all" or entry.kind == kind)
            and (
                not query
                or query in entry.stock_code
                or query in entry.result_id
            )
        )

    def _apply_filters(self, *_args: object) -> None:
        self._render_entries()
        self._update_search_status()

    def _stock_filter_changed(self, *_args: object) -> None:
        self._render_entries()
        if self._full_history_limited:
            self._update_search_status(searching_full_history=True)
            self._search_timer.start()
        else:
            self._update_search_status()

    def _update_search_status(self, *, searching_full_history: bool = False) -> None:
        """明確區分完整歷史的零符合與清單讀取狀態。"""

        result = self.last_result
        if result is None:
            return
        query = self.stock_filter.text().strip()
        visible_count = len(self._filtered_entries())
        if query:
            if searching_full_history:
                message = (
                    f"目前已載入的最新紀錄中，「{query}」符合 {visible_count} 筆；"
                    "正在搜尋完整 Journal 歷史。"
                )
            else:
                message = (
                    f"完整已載入的研究紀錄中沒有符合「{query}」的資料。"
                    if visible_count == 0
                    else f"完整已載入的研究紀錄中，「{query}」符合 {visible_count} 筆。"
                )
        elif result.limited:
            message = (
                f"已讀取最新 {len(self._entries)} 筆研究紀錄；輸入股票代號或完整 result ID，"
                "可搜尋完整 Journal 歷史。"
            )
        elif self._entries:
            message = f"已讀取完整歷史 {len(self._entries)} 筆研究紀錄。"
        else:
            message = "目前沒有可查看的研究紀錄。"
        warning = "；".join(result.warnings)
        if warning:
            message += " " + warning
        self.status_label.setText(message)

    def _search_full_history(self) -> None:
        if self._closing or not self._full_history_limited:
            return
        self.refresh(search_query=self.stock_filter.text().strip())

    def _selection_changed(self) -> None:
        row = self.entries_table.currentRow()
        visible = self._filtered_entries()
        self._show_entry(visible[row] if 0 <= row < len(visible) else None)

    def _show_entry(self, entry: ResearchTimelineEntry | None) -> None:
        is_decision = entry is not None and entry.kind == "decision"
        self._clear_evidence_comparison(
            "選取研究紀錄後可對照當時固定證據與目前可讀資料。"
            if entry is None
            else (
                "研究決定歷史是 Journal 中的動作紀錄；沒有可對照的筆記原件。"
                if is_decision
                else "按「對照目前可讀資料」讀取此筆紀錄的雙欄證據。"
            )
        )
        self._selected = entry
        self._selected_identity = None if entry is None else (entry.kind, entry.record_id)
        self.original_text.setPlainText("" if entry is None else entry.text)
        self.compare_evidence_button.setEnabled(
            entry is not None and entry.kind != "decision" and not self._closing
        )
        self.paper_prerequisites_button.setEnabled(
            entry is not None and entry.kind != "decision" and not self._closing
        )
        if entry is None:
            self.detail_label.setText("選取一筆研究紀錄")
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
        if entry.kind == "decision" and isinstance(
            entry.reference, DecisionContinuityRevision
        ):
            revision = entry.reference
            identity = revision.decision_identity
            action = _KIND_LABELS.get(entry.kind, entry.kind)
            self.detail_label.setText(
                f"{action}｜{entry.stock_code or '股票未知'}｜保存時間 "
                f"{revision.created_at or '未知'}\n"
                f"決策日 {identity.decision_date or '未知'}｜"
                f"result ID {identity.result_id or '未知'}｜"
                f"來源 snapshot {identity.source_snapshot_id or '未提供'}"
            )
            self.detail_label.setToolTip(
                f"revision ID：{revision.revision_id}\n"
                f"來源 snapshot ID：{identity.source_snapshot_id or '未提供'}\n"
                f"來源 snapshot hash：{identity.source_snapshot_hash or '未提供'}\n"
                f"決策日：{identity.decision_date or '未知'}"
            )
            details = [
                entry.text,
                f"動作：{revision.action}",
                f"股票：{identity.stock_code or '未知'}",
                f"result ID：{identity.result_id or '未知'}",
                f"決策日：{identity.decision_date or '未知'}",
                f"來源 snapshot ID：{identity.source_snapshot_id or '未提供'}",
                f"來源 snapshot hash：{identity.source_snapshot_hash or '未提供'}",
                f"revision ID：{revision.revision_id}",
            ]
            if revision.next_review_at:
                details.append(f"下次檢視：{revision.next_review_at}")
            self.original_text.setPlainText("\n".join(details))
            if self.journey_widget is not None:
                self.journey_widget.set_context(None)
                self.journey_widget.hide()
            if self.journey_placeholder is not None:
                self.journey_placeholder.setText(
                    "此為研究決定歷史；可在此查找，不依賴候選再次出現在 Advice。"
                )
                self.journey_placeholder.show()
            return
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

    def _request_evidence_comparison(self) -> None:
        entry = self._selected
        if entry is None or self._closing or self._comparison_loading:
            return
        self._comparison_loading = True
        self._evidence_comparison_revision += 1
        self.compare_evidence_button.setEnabled(False)
        self.evidence_comparison_widget.clear("正在讀取目前可讀資料…")
        self.compareEvidenceRequested.emit(entry)

    def _request_paper_prerequisites(self) -> None:
        """只傳遞目前選取的原件；前置條件讀取由 Main 負責。"""
        entry = self._selected
        if entry is None or self._closing:
            return
        self.paperPrerequisitesRequested.emit(entry)

    def set_evidence_comparison(
        self,
        entry: ResearchTimelineEntry,
        result: ResearchEvidenceComparison,
        *,
        expected_revision: int | None = None,
    ) -> bool:
        """只接受目前仍選取的同一筆原件之比較結果。"""
        if (
            self._closing
            or self._selected is not entry
            or (
                expected_revision is not None
                and expected_revision != self._evidence_comparison_revision
            )
        ):
            return False
        self._comparison_loading = False
        self.evidence_comparison_widget.show_comparison(result)
        self.compare_evidence_button.setEnabled(True)
        return True

    def set_evidence_comparison_error(
        self,
        entry: ResearchTimelineEntry,
        message: str,
        *,
        expected_revision: int | None = None,
    ) -> bool:
        if (
            self._closing
            or self._selected is not entry
            or (
                expected_revision is not None
                and expected_revision != self._evidence_comparison_revision
            )
        ):
            return False
        self._comparison_loading = False
        self.evidence_comparison_widget.clear(f"目前資料對照不可用：{message}")
        self.compare_evidence_button.setEnabled(True)
        return True

    def _clear_evidence_comparison(self, message: str) -> None:
        self._evidence_comparison_revision += 1
        self._comparison_loading = False
        if hasattr(self, "compare_evidence_button"):
            self.compare_evidence_button.setEnabled(self._selected is not None and not self._closing)
        if hasattr(self, "evidence_comparison_widget"):
            self.evidence_comparison_widget.clear(message)

    def invalidate_evidence_comparison(self) -> None:
        """離開頁面即丟棄當次對照；再次返回必須明選重新讀取。"""
        self._clear_evidence_comparison("返回研究紀錄後，請重新對照目前可讀資料。")

    @property
    def evidence_comparison_revision(self) -> int:
        """目前比較請求的唯讀版號，供呼叫端配對非同步回應。"""
        return self._evidence_comparison_revision

    @property
    def selected_entry(self) -> ResearchTimelineEntry | None:
        """目前選取的原始時間軸 entry；供外部讀取，不可直接改寫。"""
        return self._selected

    def _open_original(self) -> None:
        entry = self._selected
        if entry is not None and entry.kind in {"price", "report", "theme"}:
            self.openOriginalRequested.emit(entry)

    def request_close(self) -> bool:
        self._closing = True
        self._search_timer.stop()
        self._clear_evidence_comparison("時間軸已關閉；不再套用延遲到達的對照結果。")
        self.paper_prerequisites_button.setEnabled(False)
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
