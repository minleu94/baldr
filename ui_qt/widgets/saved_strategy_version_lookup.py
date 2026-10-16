"""明確查找保存策略版本，並唯讀開啟其 exact 原始研究來源。"""

from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app_module.saved_strategy_version_reader import (
    SavedStrategyVersionEntry,
    SavedStrategyVersionPage,
    SavedStrategyVersionSource,
)
from ui_qt.workers.task_worker import TaskWorker


class SavedStrategyVersionLookupWidget(QWidget):
    """按使用者明示操作列版本；不推定資格、不重跑來源。"""

    def __init__(self, reader, on_open, parent=None, *, owner=None):
        super().__init__(parent)
        self.reader = reader
        self.on_open = on_open
        self.owner = owner if owner is not None else getattr(on_open, "__self__", None)
        self.worker: TaskWorker | None = None
        self._generation = 0
        self._worker_generation = 0
        self._worker_owner_generation = None
        self._closing = False
        self._loading_entries = False
        self._entries: tuple[SavedStrategyVersionEntry, ...] = ()
        self._page_offset = 0
        self._page_limit = 200
        self._page_total = 0

        layout = QVBoxLayout(self)
        title = QLabel("保存策略版本查找", self)
        title.setAccessibleName("保存策略版本查找")
        title.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(title)

        instructions = QLabel(
            "按下「刷新保存版本」才會讀取清單。保存版號是版本紀錄標籤；"
            "來源執行版號取自原 Registry metadata。狀態欄僅顯示保存聲明，不代表資格。",
            self,
        )
        instructions.setWordWrap(True)
        instructions.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(instructions)

        controls = QGridLayout()
        self.refresh = QPushButton("刷新保存版本", self)
        self.refresh.setAccessibleName("刷新保存策略版本")
        self.refresh.clicked.connect(self.refresh_versions)
        self.cancel = QPushButton("取消讀取", self)
        self.cancel.setAccessibleName("取消保存策略版本讀取")
        self.cancel.clicked.connect(self.cancel_pending)
        controls.addWidget(self.refresh, 0, 0)
        controls.addWidget(self.cancel, 0, 1)
        self.previous_page = QPushButton("上一頁版本", self)
        self.next_page = QPushButton("下一頁版本", self)
        self.previous_page.clicked.connect(lambda: self.refresh_versions(offset=max(0, self._page_offset - self._page_limit)))
        self.next_page.clicked.connect(lambda: self.refresh_versions(offset=self._page_offset + self._page_limit))
        controls.addWidget(self.previous_page, 1, 0)
        controls.addWidget(self.next_page, 1, 1)
        layout.addLayout(controls)

        self.entries = QListWidget(self)
        self.entries.setAccessibleName("已保存策略版本清單")
        self.entries.setWordWrap(True)
        self.entries.setMaximumHeight(160)
        self.entries.currentItemChanged.connect(self._selection_changed)
        layout.addWidget(self.entries, 1)

        self.status = QLabel("尚未讀取；請明確按「刷新保存版本」。", self)
        self.status.setAccessibleName("保存策略版本查找狀態")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status)

        actions = QGridLayout()
        self.open_result = QPushButton("開啟原研究結果", self)
        self.open_result.setAccessibleName("開啟保存策略版本的原研究結果")
        self.open_result.clicked.connect(lambda: self.open_selected_source())
        self.open_rule = QPushButton("查看原執行規則", self)
        self.open_rule.setAccessibleName("查看保存策略版本的原執行規則")
        self.open_rule.clicked.connect(lambda: self.open_selected_source(rule=True))
        actions.addWidget(self.open_result, 0, 0)
        actions.addWidget(self.open_rule, 0, 1)
        layout.addLayout(actions)
        self._sync_enabled()

    def _owner_generation(self):
        return getattr(self.owner, "_execution_generation", None)

    def _is_current(self, generation: int, owner_generation) -> bool:
        return (
            not self._closing
            and generation == self._generation
            and owner_generation == self._owner_generation()
        )

    @staticmethod
    def _source_execution_version(entry: SavedStrategyVersionEntry) -> str:
        source_entry = entry.source_entry
        if source_entry is None:
            return "未知；來源缺件"
        try:
            metadata = json.loads(source_entry.metadata_json)
        except (TypeError, ValueError):
            return "未知；metadata 無法讀取"
        value = metadata.get("strategy_version") if isinstance(metadata, dict) else None
        return value if isinstance(value, str) and value.strip() else "未知；未提供"

    @classmethod
    def _entry_label(cls, entry: SavedStrategyVersionEntry) -> str:
        source_entry = entry.source_entry
        name = source_entry.run_name if source_entry is not None else entry.strategy_id
        source_version = cls._source_execution_version(entry)
        label = (
            f"{name}｜保存版本 {entry.strategy_version}｜來源執行版本 {source_version}\n"
            f"策略 {entry.strategy_id}｜來源 run {entry.source_run_id}｜"
            f"保存狀態聲明 {entry.validation_status}（不代表資格）"
        )
        if entry.diagnostics:
            label += "\n來源診斷：" + "；".join(entry.diagnostics)
        return label

    @staticmethod
    def _valid_page(value: object) -> bool:
        if type(value) is not SavedStrategyVersionPage:
            return False
        if (
            type(value.entries) is not tuple
            or type(value.diagnostics) is not tuple
            or type(value.total_catalog_count) is not int
            or value.total_catalog_count < 0
            or type(value.limit) is not int
            or not 1 <= value.limit <= 1000
            or len(value.entries) > value.limit
            or type(value.offset) is not int or value.offset < 0
        ):
            return False
        seen: set[str] = set()
        for entry in value.entries:
            if type(entry) is not SavedStrategyVersionEntry or entry.version_id in seen:
                return False
            if any(type(reason) is not str for reason in entry.diagnostics):
                return False
            seen.add(entry.version_id)
        return all(type(reason) is str for reason in value.diagnostics)

    def _selected_entry(self) -> SavedStrategyVersionEntry | None:
        item = self.entries.currentItem()
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return value if type(value) is SavedStrategyVersionEntry else None

    def _entry_openable(self, entry: SavedStrategyVersionEntry | None) -> bool:
        return bool(
            entry is not None
            and entry.source_entry is not None
            and not entry.diagnostics
        )

    def _sync_enabled(self) -> None:
        busy = self.worker is not None
        self.refresh.setEnabled(not self._closing and self.reader is not None and not busy)
        self.cancel.setEnabled(not self._closing and busy)
        can_open = not self._closing and not busy and self._entry_openable(self._selected_entry())
        self.open_result.setEnabled(can_open)
        self.open_rule.setEnabled(can_open)
        self.previous_page.setEnabled(not self._closing and not busy and self._page_offset > 0)
        self.next_page.setEnabled(not self._closing and not busy and self._page_offset + self._page_limit < self._page_total)

    def _cancel_worker(self) -> None:
        worker = self.worker
        if worker is not None:
            try:
                worker.cancel(cooperative=True, wait=False)
            except RuntimeError:
                pass

    def _clear_entries(self) -> None:
        self._loading_entries = True
        self.entries.clear()
        self._entries = ()
        self._loading_entries = False

    def _selection_changed(self, *_args: object) -> None:
        if self._loading_entries or self._closing:
            return
        self._generation += 1
        self._cancel_worker()
        entry = self._selected_entry()
        if entry is None:
            self.status.setText("尚未選取保存策略版本。")
        elif not self._entry_openable(entry):
            details = "；".join(entry.diagnostics) if entry.diagnostics else "原來源不存在"
            self.status.setText(f"此保存版本缺少可核對的原來源，不能開啟：{details[:500]}")
        else:
            source_version = self._source_execution_version(entry)
            self.status.setText(
                f"已選取保存版本 {entry.strategy_version}；原 run 執行版本 {source_version}。"
                "選擇開啟原結果或原規則；不重跑，也不授予資格。"
            )
        self._sync_enabled()

    def _start_worker(self, task, *, generation: int, owner_generation, apply) -> None:
        if self._closing or self.worker is not None or generation != self._generation:
            return
        worker = TaskWorker(task)
        self.worker = worker
        self._worker_generation = generation
        self._worker_owner_generation = owner_generation

        def finished(value: object) -> None:
            if not self._is_current(generation, owner_generation) or self.worker is not worker:
                return
            try:
                apply(value)
            except Exception as exc:
                self.status.setText("讀取結果無法呈現，沒有套用部分內容。原因：" + self._bounded_error(exc))

        def failed(message: str) -> None:
            if not self._is_current(generation, owner_generation) or self.worker is not worker:
                return
            self.status.setText("保存版本讀取失敗，沒有套用部分內容。原因：" + self._bounded_error(message))

        def cancelled() -> None:
            if self._is_current(generation, owner_generation) and self.worker is worker:
                self.status.setText("保存版本讀取已取消；未套用未完成結果。")

        def native_finished() -> None:
            if self.worker is worker:
                self.worker = None
            worker.deleteLater()
            self._sync_enabled()

        worker.finished.connect(finished, Qt.ConnectionType.QueuedConnection)
        worker.error.connect(failed, Qt.ConnectionType.QueuedConnection)
        worker.cancelled.connect(cancelled, Qt.ConnectionType.QueuedConnection)
        worker.native_thread_finished.connect(native_finished, Qt.ConnectionType.QueuedConnection)
        self._sync_enabled()
        worker.start()

    @staticmethod
    def _bounded_error(value: object) -> str:
        return str(value).replace("\r", " ").replace("\n", " ")[:500]

    def refresh_versions(self, *, offset: int = 0) -> None:
        if self._closing:
            return
        if self.reader is None:
            self.status.setText("保存策略版本 reader 尚未配置。")
            return
        if self.worker is not None:
            self.status.setText("前一項讀取仍在收尾；完成後請再刷新。")
            return
        self._generation += 1
        generation = self._generation
        owner_generation = self._owner_generation()
        self._page_offset = offset
        self._page_total = 0
        self._clear_entries()
        self.status.setText("正在讀取保存策略版本清單……")

        def task(cancel_callback=None):
            def check_cancel() -> bool:
                return bool(cancel_callback and cancel_callback()) or not self._is_current(
                    generation, owner_generation
                )

            return self.reader.list_versions(limit=self._page_limit, offset=offset, check_cancel=check_cancel)

        def apply(value: object) -> None:
            if not self._valid_page(value) or value.offset != offset:
                self.status.setText("保存版本清單格式不符；未套用。")
                return
            self._entries = value.entries
            self._page_total = value.total_catalog_count
            self._loading_entries = True
            for entry in value.entries:
                item = QListWidgetItem(self._entry_label(entry))
                item.setData(Qt.ItemDataRole.UserRole, entry)
                item.setToolTip(
                    f"保存版本 ID：{entry.version_id}\n來源 run：{entry.source_run_id}\n"
                    f"版本聲明：{entry.validation_status}（不代表資格）"
                )
                self.entries.addItem(item)
            self._loading_entries = False
            detail = "；".join(value.diagnostics)
            self.status.setText(
                f"目錄第 {offset // self._page_limit + 1} 頁，顯示 {len(value.entries)} 筆保存版本；共 {value.total_catalog_count} 筆。"
                + ("部分項目診斷：" + self._bounded_error(detail) if detail else "請明確選取一筆。")
            )
            self._sync_enabled()

        self._start_worker(task, generation=generation, owner_generation=owner_generation, apply=apply)

    def open_selected_source(self, *, rule: bool = False) -> None:
        if self._closing:
            return
        if self.worker is not None:
            return
        selected = self._selected_entry()
        if not self._entry_openable(selected):
            self.status.setText("請選取一筆有可核對原來源的保存版本。")
            self._sync_enabled()
            return
        generation = self._generation + 1
        self._generation = generation
        owner_generation = self._owner_generation()
        version_sha256 = selected.version_sha256
        self.status.setText("正在 exact 重讀所選版本與其原 Registry run……")

        def task(cancel_callback=None):
            def check_cancel() -> bool:
                return bool(cancel_callback and cancel_callback()) or not self._is_current(
                    generation, owner_generation
                )

            return self.reader.read_source(selected, check_cancel=check_cancel)

        def apply(value: object) -> None:
            current = self._selected_entry()
            if (
                type(value) is not SavedStrategyVersionSource
                or value.selection != selected
                or value.history_result.entry != selected.source_entry
                or current is None
                or current.version_id != selected.version_id
                or current.version_sha256 != version_sha256
            ):
                self.status.setText("保存版本選取已變更；舊讀取結果已忽略。")
                return
            if rule:
                self._show_rule(value, selected)
            else:
                self.on_open(value.history_result)
            self.status.setText("已開啟所選保存版本連結的原 Registry 來源；沒有重跑或改寫來源。")

        self._start_worker(task, generation=generation, owner_generation=owner_generation, apply=apply)

    def _show_rule(self, source: SavedStrategyVersionSource, entry: SavedStrategyVersionEntry) -> None:
        from ui_qt.widgets.strategy_rule_card_dialog import StrategyRuleCardDialog

        dialog = StrategyRuleCardDialog(source.rule_card.rule_card, result=source.rule_card, parent=self)
        saved_version = entry.strategy_version
        execution_version = self._source_execution_version(entry)
        dialog.summary.setText(
            f"保存版號：{saved_version}｜來源執行版號：{execution_version}\n"
            "下方規則來自所選版本連結的原 Registry run；保存狀態聲明不代表資格。"
        )
        dialog.exec()

    def cancel_pending(self) -> None:
        self._generation += 1
        self._cancel_worker()
        self.status.setText("保存版本讀取已取消；未套用未完成結果。")
        self._sync_enabled()

    def invalidate_and_clear(self) -> None:
        self._generation += 1
        self._cancel_worker()
        self._clear_entries()
        self._page_offset = 0
        self._page_total = 0
        self.status.setText("保存版本清單已清除；請重新明確刷新。")
        self._sync_enabled()

    def begin_shutdown(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._generation += 1
        self._cancel_worker()
        self._clear_entries()
        self.status.setText("保存版本查找已隨視窗關閉；背景工作正在安全收尾。")
        self._sync_enabled()

    def has_running_worker(self) -> bool:
        return self.worker is not None

    def closeEvent(self, event: QCloseEvent) -> None:
        self.begin_shutdown()
        if self.has_running_worker():
            event.ignore()
            return
        event.accept()
