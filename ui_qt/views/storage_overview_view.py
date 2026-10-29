"""系統管理的唯讀儲存維護頁。"""

from pathlib import Path
from typing import Mapping

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGroupBox,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app_module.storage_overview import StorageOverview, inspect_storage
from ui_qt.workers.task_worker import TaskWorker


class StorageOverviewView(QWidget):
    def __init__(self, roots: Mapping[str, Path], trial_root: Path | None = None,
                 parent=None, *, package_root: Path | None = None):
        super().__init__(parent)
        self._roots = dict(roots)
        self._trial_root = trial_root
        self._package_root = package_root
        self._worker: TaskWorker | None = None
        self._loaded = False
        self._closing = False
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        notice = QLabel(
            "儲存維護｜唯讀盤點，不會自動刪除。\n"
            "磁碟容量列是整顆磁碟用量；不同位置可能共用同一磁碟，不可相加。"
            "明示盤點根最多列 64 個版本／4096 項；套件根只呈現一列。"
            "引用、備份與回退尚未逐件核對，清理前需另外確認。"
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.refresh_button = QPushButton("重新盤點儲存位置與明示根")
        self.refresh_button.setObjectName("storageOverviewRefresh")
        self.refresh_button.clicked.connect(self.refresh)
        layout.addWidget(self.refresh_button)
        self.status_label = QLabel("開啟本頁後讀取儲存狀態。")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.locations_group = QGroupBox(
            "磁碟容量｜逐列查看可用空間，不跨位置相加"
        )
        locations_layout = QVBoxLayout(self.locations_group)
        self.locations_summary_label = QLabel("尚未盤點磁碟位置。")
        self.locations_summary_label.setWordWrap(True)
        locations_layout.addWidget(self.locations_summary_label)
        self.locations_table = QTableWidget(0, 5)
        self.locations_table.setObjectName("storageLocationsTable")
        self.locations_table.setHorizontalHeaderLabels(("位置", "路徑", "磁碟總量 MiB", "磁碟可用 MiB", "狀態"))
        locations_layout.addWidget(self.locations_table)
        layout.addWidget(self.locations_group, 1)

        self.artifacts_group = QGroupBox(
            "明示根內盤點項目｜大小完整度與保留狀態"
        )
        artifacts_layout = QVBoxLayout(self.artifacts_group)
        self.artifacts_summary_label = QLabel("尚未讀取明示根的盤點項目。")
        self.artifacts_summary_label.setWordWrap(True)
        artifacts_layout.addWidget(self.artifacts_summary_label)
        self.artifacts_table = QTableWidget(0, 4)
        self.artifacts_table.setObjectName("storageArtifactsTable")
        self.artifacts_table.setHorizontalHeaderLabels(("盤點項目", "已量測 MiB", "大小完整", "引用與保留狀態"))
        artifacts_layout.addWidget(self.artifacts_table)
        layout.addWidget(self.artifacts_group, 1)

        for table, widths in (
            (self.locations_table, (110, 280, 125, 125, 250)),
            (self.artifacts_table, (190, 120, 110, 330)),
        ):
            table.setEditTriggers(QTableWidget.NoEditTriggers)
            table.setSelectionBehavior(QTableWidget.SelectRows)
            table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            header = table.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.Interactive)
            table.horizontalHeader().setStretchLastSection(True)
            for column, width in enumerate(widths):
                table.setColumnWidth(column, width)

    def refresh_if_needed(self) -> None:
        if not self._loaded:
            self.refresh()

    def refresh(self) -> None:
        if self._closing or self._worker is not None:
            return
        worker = TaskWorker(inspect_storage, self._roots, self._trial_root,
                            package_root=self._package_root)
        self._worker = worker
        self.refresh_button.setEnabled(False)
        self.status_label.setText("正在唯讀盤點；未檢查引用的版本一律保留。")
        worker.finished.connect(self._apply)
        worker.error.connect(lambda error: self.status_label.setText(
            f"盤點未完成：{self._inventory_target()}（{str(error).splitlines()[0]}）"))

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
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                self.locations_table.setItem(row, column, item)
        self.artifacts_table.setRowCount(len(value.artifacts))
        for row, artifact in enumerate(value.artifacts):
            cells = (artifact.name, self._mib(artifact.measured_bytes), "是" if artifact.complete else "否／部分", artifact.status)
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                self.artifacts_table.setItem(row, column, item)
        complete_count = sum(1 for item in value.artifacts if item.complete)
        self.locations_summary_label.setText(
            f"磁碟位置 {len(value.locations)} 個。每列容量是整顆磁碟的總量與可用量。"
        )
        self.artifacts_summary_label.setText(
            f"盤點項目 {len(value.artifacts)} 個；大小完整 {complete_count} 個、"
            f"部分或不完整 {len(value.artifacts) - complete_count} 個。"
            + ("已達盤點上限，清單或大小可能不完整。" if value.limited else "")
        )
        detail = f"{value.inventory_path or '未提供盤點位置'}；{value.inventory_status}"
        if value.inventory_available:
            self.status_label.setText(
                f"{detail}。所有版本仍保留，清理須另行核對引用與 Owner 授權。")
        else:
            self.status_label.setText(f"盤點未完成：{detail}。未將缺失或不可讀位置視為空清單。")

    def _inventory_target(self) -> str:
        root = self._package_root if self._package_root is not None else self._trial_root
        return str(root) if root is not None else "未提供盤點位置"

    @staticmethod
    def _mib(value: int | None) -> str:
        return "未提供" if value is None else str(value // (1024 * 1024))

    def request_close(self) -> bool:
        self._closing = True
        if self._worker is not None:
            self._worker.cancel(cooperative=True, wait=False)
            return not self._worker.isRunning()
        return True
