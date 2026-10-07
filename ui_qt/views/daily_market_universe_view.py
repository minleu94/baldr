"""完整保存母體的有界頁面；全域查詢後分頁，不在切頁時產生資料。"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QComboBox, QCheckBox, QLineEdit, QTableWidget, QTableWidgetItem, QAbstractItemView)

from app_module.daily_market_universe_run import list_completed_runs
from app_module.daily_market_universe_selection import (UniverseResearchQuery,
    UniverseResearchPage, read_universe_research_page, resolve_universe_stock_snapshot)
from ui_qt.workers.task_worker import TaskWorker


class DailyMarketUniverseView(QWidget):
    """來源、query、頁碼與選股維持在同一個 verified generation。"""
    childSnapshotRequested = Signal(object)
    cancelRequested = Signal()

    @property
    def current_query(self) -> UniverseResearchQuery | None:
        return self._query

    def __init__(self, output_root: str | Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.output_root = Path(output_root).absolute()
        self._worker: TaskWorker | None = None
        self._generation = 0
        self._closing = False
        self._query: UniverseResearchQuery | None = None
        self._page: UniverseResearchPage | None = None
        self._source_cursor: str | None = None
        layout = QVBoxLayout(self)
        self.summary = QLabel("完整保存母體：請查詢已完成來源。瀏覽不更新行情或產生研究。")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        source_row = QGridLayout()
        self.sources = QComboBox()
        self.refresh_button = QPushButton("查詢完整保存母體")
        self.load_button = QPushButton("讀取所選母體")
        self.more_sources_button = QPushButton("更多保存來源")
        self.more_sources_button.setEnabled(False)
        self.cancel_button = QPushButton("取消")
        source_row.addWidget(self.sources, 0, 0, 1, 3)
        source_row.addWidget(self.refresh_button, 0, 3)
        source_row.addWidget(self.load_button, 1, 0)
        source_row.addWidget(self.more_sources_button, 1, 1)
        source_row.addWidget(self.cancel_button, 1, 3)
        source_row.setColumnStretch(2, 1)
        layout.addLayout(source_row)
        controls = QGridLayout()
        self.conditions: dict[str, QCheckBox] = {}
        for key, label in (("close_above_ma20", "價高於MA20"),
                ("close_above_ma60", "價高於MA60"), ("close_above_bbands30_upper", "價高於布林上軌30")):
            checkbox = QCheckBox(label)
            checkbox.setChecked(key == "close_above_ma20")
            self.conditions[key] = checkbox
            controls.addWidget(checkbox, 0, len(self.conditions) - 1)
        self.mode = QComboBox()
        self.mode.addItems(["AND", "OR"])
        self.mode.setAccessibleName("多條件組合方式")
        self.mode.setToolTip("AND 需要所有條件符合；OR 需要至少一個條件符合。缺件保留未知。")
        self.state = QComboBox()
        self.state.setAccessibleName("篩選結果狀態")
        for label, value in (("全部", "all"), ("符合", "match"), ("不符合", "no_match"),
                ("未知", "unknown"), ("排除", "excluded")):
            self.state.addItem(label, value)
        self.sort = QComboBox()
        self.sort.setAccessibleName("全母體排序欄位")
        for label, value in (("股票代碼", "stock_code"), ("價格", "close"), ("資料日期", "data_date"),
                ("MA20", "ma20"), ("MA60", "ma60"), ("布林上軌30", "bbands30_upper")):
            self.sort.addItem(label, value)
        self.descending = QCheckBox("降冪")
        self.stock_filter = QLineEdit()
        self.stock_filter.setPlaceholderText("找股票代碼")
        self.stock_filter.setMaxLength(16)
        self.apply_button = QPushButton("套用全域查詢")
        controls.addWidget(self.mode, 0, 3)
        controls.addWidget(self.state, 0, 4)
        controls.addWidget(self.sort, 1, 0)
        controls.addWidget(self.descending, 1, 1)
        controls.addWidget(self.stock_filter, 1, 2, 1, 2)
        controls.addWidget(self.apply_button, 1, 4)
        layout.addLayout(controls)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["股票", "資料日期", "價格（元／股）", "條件", "理由／限制"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(False)
        layout.addWidget(self.table)
        navigation = QHBoxLayout()
        self.previous_button = QPushButton("上一頁")
        self.next_button = QPushButton("下一頁")
        self.open_button = QPushButton("開啟原保存個股研究")
        for widget in (self.previous_button, self.next_button, self.open_button):
            navigation.addWidget(widget)
        layout.addLayout(navigation)
        self.status = QLabel("母體完整與資料完整分開判讀；研究條件不代表推薦或交易資格。")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.refresh_button.clicked.connect(self.refresh_sources)
        self.more_sources_button.clicked.connect(lambda: self.refresh_sources(append=True))
        self.load_button.clicked.connect(self.load_selected)
        self.apply_button.clicked.connect(self.apply_query)
        self.previous_button.clicked.connect(lambda: self.change_page(-1))
        self.next_button.clicked.connect(lambda: self.change_page(1))
        self.open_button.clicked.connect(self.open_stock)
        self.cancel_button.clicked.connect(self.cancel)

    def _start(self, operation: Callable, apply: Callable) -> None:
        if self._worker is not None or self._closing:
            return
        self._generation += 1
        generation = self._generation
        worker = TaskWorker(operation)
        self._worker = worker
        self._set_busy(True)
        worker.finished.connect(lambda value: apply(value) if generation == self._generation and not self._closing else None)
        worker.error.connect(lambda message: self.status.setText(f"來源／查詢拒絕；原結果保留：{message}")
            if generation == self._generation and not self._closing else None)
        worker.native_thread_finished.connect(lambda: self._release(worker))
        self.status.setText("正在背景核驗完整來源及查詢…")
        worker.start()

    def _release(self, worker: TaskWorker) -> None:
        if self._worker is worker:
            self._worker = None
            self._set_busy(False)
        worker.deleteLater()

    def refresh_sources(self, *, append: bool = False) -> None:
        cursor = self._source_cursor if append else None
        def apply(listing: object) -> None:
            if not append:
                self.sources.clear()
            for item in getattr(listing, "items", ()):
                if item.status == "complete":
                    self.sources.addItem(f"{item.decision_date}｜{item.universe_id}｜{item.population_version}", item)
            self._source_cursor = getattr(listing, "next_cursor", None)
            self.more_sources_button.setEnabled(bool(getattr(listing, "has_more", False)))
            self.status.setText("請選來源；未完成來源不會冒稱完整。" if self.sources.count()
                else "此根沒有完整保存母體；原單批來源仍可使用。")
        self._start(lambda cancel_callback=None: list_completed_runs(self.output_root,
            after_generation_identity=cursor), apply)

    def load_selected(self) -> None:
        selected = self.sources.currentData()
        if selected is None:
            return
        query = UniverseResearchQuery(str(self.output_root), selected.generation_identity_sha256,
            selected.manifest_sha256)
        self._read(query)

    def _read(self, query: UniverseResearchQuery) -> None:
        self._start(lambda cancel_callback=None: read_universe_research_page(query,
            cancel_callback=cancel_callback), self._show_page)

    def _show_page(self, value: object) -> None:
        if not isinstance(value, UniverseResearchPage):
            self.status.setText("完整母體回傳格式不符；原來源保留。")
            return
        selected_code = None
        selected = self.table.selectionModel().selectedRows()
        if self._query == value.query and len(selected) == 1:
            selected_item = self.table.item(selected[0].row(), 0)
            selected_code = selected_item.text() if selected_item is not None else None
        self._query, self._page = value.query, value
        for key, checkbox in self.conditions.items():
            checkbox.setChecked(key in value.query.condition_keys)
        self.mode.setCurrentText(value.query.combine_mode)
        self.state.setCurrentIndex(self.state.findData(value.query.state_filter))
        self.sort.setCurrentIndex(self.sort.findData(value.query.sort_key))
        self.descending.setChecked(value.query.descending)
        self.stock_filter.setText(value.query.stock_filter)
        counts = value.counts
        self.summary.setText(f"{value.source['universe_id']}｜{value.source['decision_date']}｜"
            f"宣告 {counts['declared_unique_count']}、納入 {counts['included_count']}、"
            f"排除 {counts['excluded_count']}、已處理 {counts['processed_count']}、"
            f"待處理 {counts['pending_count']}、缺資料 {counts['missing_data_stock_count']}；"
            f"查詢 {value.page.filtered_count} 筆，第 {value.query.page + 1} 頁。")
        self.table.clearSelection()
        self.table.setCurrentItem(None)
        self.table.setRowCount(len(value.page.rows))
        labels = {"match": "符合", "no_match": "不符合", "unknown": "未知", "excluded": "排除"}
        for index, row in enumerate(value.page.rows):
            reason = row.get("excluded_reason") or "；".join([*row.get("why", ()), *row.get("why_not", ())])
            cells = (row["stock_code"], row.get("data_date") or "未知", row.get("close") or "未知",
                labels.get(str(row.get("combined_state")), "未知"), reason)
            for column, text in enumerate(cells):
                item = QTableWidgetItem(str(text))
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, dict(row))
                self.table.setItem(index, column, item)
            if row["stock_code"] == selected_code:
                self.table.setCurrentCell(index, 0)
                self.table.selectRow(index)
        self.status.setText("全域篩選排序後分頁；未知值雙向置尾。")

    def apply_query(self) -> None:
        if self._query is None:
            return
        keys = tuple(key for key, checkbox in self.conditions.items() if checkbox.isChecked())
        if not keys:
            self.status.setText("請至少選擇一個條件。")
            return
        self._read(replace(self._query, condition_keys=keys, combine_mode=self.mode.currentText(),
            state_filter=str(self.state.currentData()), sort_key=str(self.sort.currentData()),
            descending=self.descending.isChecked(), stock_filter=self.stock_filter.text().strip(), page=0))

    def change_page(self, delta: int) -> None:
        if self._query is None or self._page is None:
            return
        page = self._query.page + delta
        if page < 0 or page * self._query.page_size >= self._page.page.filtered_count:
            return
        self._read(replace(self._query, page=page))

    def open_stock(self) -> None:
        selected = self.table.selectionModel().selectedRows()
        if self._query is None or len(selected) != 1:
            return
        item = self.table.item(selected[0].row(), 0)
        code = item.text()
        query = self._query
        self._start(lambda cancel_callback=None: (query, code,
            resolve_universe_stock_snapshot(query, code, cancel_callback=cancel_callback)),
            self.childSnapshotRequested.emit)

    def cancel(self) -> None:
        self._generation += 1
        if self._worker is not None:
            self._worker.cancel(cooperative=True, wait=False)
        self.cancelRequested.emit()
        self.status.setText("已取消；原來源與查詢保留，晚到回呼不替換畫面。")

    def begin_shutdown(self) -> bool:
        self._closing = True
        self._set_busy(True)
        self.cancel()
        return self._worker is None or not self._worker.isRunning()

    def _set_busy(self, busy: bool) -> None:
        for widget in (self.sources, self.refresh_button, self.load_button, self.apply_button,
                self.previous_button, self.next_button, self.open_button, self.table,
                self.mode, self.state, self.sort, self.descending, self.stock_filter,
                *self.conditions.values()):
            widget.setEnabled(not busy and not self._closing)
        self.more_sources_button.setEnabled(not busy and not self._closing and self._source_cursor is not None)
