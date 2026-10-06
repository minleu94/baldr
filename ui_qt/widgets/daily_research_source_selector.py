"""保存規則來源選擇器：讀原檔取得 pins，不要求手填 hash。"""
from __future__ import annotations

from pathlib import Path
from typing import Callable
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QComboBox, QLabel, QFileDialog
from app_module.daily_research_source_selection import (
    DailyResearchSourceSelection, list_daily_research_sources,
    resolve_daily_research_source_selection, read_selected_daily_research_source,
)
from ui_qt.workers.task_worker import TaskWorker


class DailyResearchSourceSelector(QWidget):
    """只管理當次選擇；持久化沿原收藏介面，不建平行 store。"""
    sourceSelected = Signal(object)
    sourceLoaded = Signal(object)
    otherSourceRequested = Signal(str)

    def __init__(self, config: object, *, snapshot_root: str | Path | None = None,
            parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.snapshot_root = snapshot_root
        self._generation = 0
        self._worker: TaskWorker | None = None
        self._closing = False
        self._external_busy = False
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.sources = QComboBox(self)
        self.sources.setAccessibleName("已保存每日規則來源")
        self.refresh_button = QPushButton("查詢已保存規則來源")
        self.browse_button = QPushButton("選擇原保存 manifest")
        self.open_button = QPushButton("讀取所選規則名單")
        self.cancel_button = QPushButton("取消來源讀取")
        for widget in (self.sources, self.refresh_button, self.browse_button, self.open_button, self.cancel_button):
            row.addWidget(widget)
        layout.addLayout(row)
        self.status = QLabel("規則名單、保存推薦與 H20 為不同來源；本頁不將三者混算。")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.refresh_button.clicked.connect(self.refresh_sources)
        self.browse_button.clicked.connect(self.browse_source)
        self.open_button.clicked.connect(self.open_selected)
        self.cancel_button.clicked.connect(self.cancel)

    def set_external_busy(self, busy: bool) -> None:
        self._external_busy = busy
        for button in (self.refresh_button, self.browse_button, self.open_button):
            button.setEnabled(not busy and self._worker is None and not self._closing)

    def _start(self, operation: Callable, apply: Callable) -> None:
        if self._closing or self._external_busy or self._worker is not None:
            self.status.setText("請等待目前來源工作完成；未切換來源。")
            return
        self._generation += 1
        generation = self._generation
        worker = TaskWorker(operation)
        self._worker = worker
        self.set_external_busy(self._external_busy)
        worker.finished.connect(lambda value: apply(value) if generation == self._generation and not self._closing else None)
        worker.error.connect(lambda message: self.status.setText(f"來源核對失敗，原名單保留：{message}") if generation == self._generation and not self._closing else None)
        worker.native_thread_finished.connect(lambda: self._release(worker))
        self.status.setText("正在背景唯讀核對原保存來源…")
        worker.start()

    def _release(self, worker: TaskWorker) -> None:
        if self._worker is worker:
            self._worker = None
            self.set_external_busy(self._external_busy)
        worker.deleteLater()

    def refresh_sources(self) -> None:
        self._start(lambda cancel_callback=None: list_daily_research_sources(
            self.config, snapshot_root=self.snapshot_root, cancel_callback=cancel_callback), self._show_sources)

    def _show_sources(self, values: object) -> None:
        if not isinstance(values, tuple) or any(not isinstance(x, DailyResearchSourceSelection) for x in values):
            self.status.setText("保存來源回傳格式不符；未替換原選擇。")
            return
        self.sources.clear()
        for value in values:
            self.sources.addItem(value.label, value)
        self.status.setText(f"已核對 {len(values)} 份保存規則來源；讀取才重驗當前資料。" if values else
            "原選定規則根沒有保存名單。既有保存推薦／H20 仍在各自入口；可選擇原 manifest，不需輸入 hash。")

    def browse_source(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "選擇原保存規則 manifest", str(self.snapshot_root or getattr(self.config, "output_root", "")), "JSON (*.json)")
        if path:
            self._start(lambda cancel_callback=None: (resolve_daily_research_source_selection(path),), self._show_sources)

    def open_selected(self) -> None:
        selected = self.sources.currentData()
        if not isinstance(selected, DailyResearchSourceSelection):
            self.status.setText("請先選擇已核對的保存規則來源。")
            return
        def apply(value: object) -> None:
            self.sourceSelected.emit(selected)
            self.sourceLoaded.emit(value)
            self.status.setText("已讀回原保存來源；來源選擇可透過既有收藏保存，未新建設定庫。")
        self._start(lambda cancel_callback=None: read_selected_daily_research_source(
            selected, self.config, cancel_callback=cancel_callback), apply)

    def cancel(self) -> None:
        self._generation += 1
        if self._worker is not None:
            self._worker.cancel(cooperative=True, wait=False)
        self.status.setText("已取消來源選擇；舊回呼不會換掉原名單。")

    def begin_shutdown(self) -> bool:
        self._closing = True
        self.cancel()
        return self._worker is None or not self._worker.isRunning()
