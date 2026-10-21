"""系統管理的唯讀儲存維護頁。"""

from pathlib import Path
from typing import Mapping

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from app_module.storage_overview import StorageOverview, inspect_storage
from ui_qt.workers.task_worker import TaskWorker


class StorageOverviewView(QWidget):
    def __init__(self, roots: Mapping[str, Path], trial_root: Path, parent=None):
        super().__init__(parent)
        self._roots = dict(roots)
        self._trial_root = trial_root
        self._worker: TaskWorker | None = None
        self._loaded = False
        self._closing = False
        layout = QVBoxLayout(self)
        notice = QLabel("儲存維護（唯讀）｜同一磁碟的容量不可跨位置相加。\n"
                        "Trial 盤點限64個版本／4096項；引用、備份與回退尚未逐件核對，沒有自動刪除操作。")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.refresh_button = QPushButton("重新盤點儲存位置與 Trial")
        self.refresh_button.clicked.connect(self.refresh)
        layout.addWidget(self.refresh_button)
        self.status_label = QLabel("開啟本頁後讀取儲存狀態。")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.locations_table = QTableWidget(0, 5)
        self.locations_table.setHorizontalHeaderLabels(("位置", "路徑", "磁碟總量 MiB", "磁碟可用 MiB", "狀態"))
        self.artifacts_table = QTableWidget(0, 4)
        self.artifacts_table.setHorizontalHeaderLabels(("Trial 版本", "已量測 MiB", "大小完整", "引用與保留狀態"))
        for table in (self.locations_table, self.artifacts_table):
            table.setEditTriggers(QTableWidget.NoEditTriggers)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
            table.horizontalHeader().setStretchLastSection(True)
            table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
            layout.addWidget(table, 1)

    def refresh_if_needed(self) -> None:
        if not self._loaded:
            self.refresh()

    def refresh(self) -> None:
        if self._closing or self._worker is not None:
            return
        worker = TaskWorker(inspect_storage, self._roots, self._trial_root)
        self._worker = worker
        self.refresh_button.setEnabled(False)
        self.status_label.setText("正在唯讀盤點；未檢查引用的版本一律保留。")
        worker.finished.connect(self._apply)
        worker.error.connect(lambda error: self.status_label.setText("盤點未完成：" + str(error).splitlines()[0]))

        def cleanup():
            self._worker = None
            if not self._closing:
                self.refresh_button.setEnabled(True)
            worker.deleteLater()

        worker.native_thread_finished.connect(cleanup)
        worker.start()

    def _apply(self, value: object) -> None:
        if self._closing or not isinstance(value, StorageOverview):
            return
        self._loaded = True
        self.locations_table.setRowCount(len(value.locations))
        for row, location in enumerate(value.locations):
            cells = (location.name, location.path, self._mib(location.total_bytes), self._mib(location.free_bytes), location.status)
            for column, text in enumerate(cells):
                self.locations_table.setItem(row, column, QTableWidgetItem(text))
        self.artifacts_table.setRowCount(len(value.artifacts))
        for row, artifact in enumerate(value.artifacts):
            cells = (artifact.name, self._mib(artifact.measured_bytes), "是" if artifact.complete else "否／部分", artifact.status)
            for column, text in enumerate(cells):
                self.artifacts_table.setItem(row, column, QTableWidgetItem(text))
        self.status_label.setText("有界盤點完成；" + ("已達上限，部分版本未量測。" if value.limited else "") + "所有版本仍保留，清理須另行核對引用與 Owner 授權。")

    @staticmethod
    def _mib(value: int | None) -> str:
        return "未提供" if value is None else str(value // (1024 * 1024))

    def request_close(self) -> bool:
        self._closing = True
        if self._worker is not None:
            self._worker.cancel(cooperative=True, wait=False)
            return not self._worker.isRunning()
        return True
