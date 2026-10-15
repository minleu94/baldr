"""明確瀏覽已登錄的配置研究紀錄；不呈現回測績效。"""

from __future__ import annotations

from datetime import datetime
from typing import TypeGuard

from PySide6.QtCore import QSignalBlocker, Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app_module.portfolio_research_registry import (
    ScenarioRegistryEntry,
    ScenarioRegistrySelection,
)
from app_module.portfolio_research_scenario_workspace import PortfolioResearchScenarioWorkspace
from ui_qt.workers.task_worker import TaskWorker


class PortfolioScenarioRegistryWidget(QWidget):
    """從明示帳戶載入有界登錄清單，僅在按下開啟時送出 exact selection。"""

    openRequested = Signal(object)

    def __init__(
        self,
        workspace: PortfolioResearchScenarioWorkspace | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.workspace = workspace
        self._generation = 0
        self._worker: TaskWorker | None = None
        self._worker_generation = 0
        self._worker_identity: tuple[str, str] | None = None
        self._loaded_identity: tuple[str, str] | None = None
        self._closing = False

        layout = QVBoxLayout(self)
        title = QLabel("配置研究紀錄（非回測績效）", self)
        title.setAccessibleName("配置研究紀錄；非回測績效")
        title.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(title)

        identity_group = QGroupBox("明確選取帳戶與組合", self)
        identity_layout = QFormLayout(identity_group)
        self.account_kind_combo = QComboBox(identity_group)
        self.account_kind_combo.setAccessibleName("配置研究紀錄帳種")
        self.account_kind_combo.addItem("請選帳種", None)
        for account_kind in ("manual", "user_declared", "paper"):
            self.account_kind_combo.addItem(account_kind, account_kind)
        self.account_kind_combo.currentIndexChanged.connect(self._on_identity_changed)
        identity_layout.addRow("帳種", self.account_kind_combo)

        self.portfolio_id_edit = QLineEdit(identity_group)
        self.portfolio_id_edit.setAccessibleName("配置研究紀錄 portfolio_id")
        self.portfolio_id_edit.setPlaceholderText("請輸入 exact portfolio_id")
        self.portfolio_id_edit.textChanged.connect(self._on_identity_changed)
        identity_layout.addRow("Portfolio ID", self.portfolio_id_edit)

        controls = QHBoxLayout()
        self.load_button = QPushButton("載入已登錄紀錄", identity_group)
        self.load_button.clicked.connect(self.load_registered)
        controls.addWidget(self.load_button)

        self.entry_combo = QComboBox(identity_group)
        self.entry_combo.setAccessibleName("已登錄配置研究紀錄")
        self.entry_combo.setMinimumContentsLength(35)
        self.entry_combo.addItem("請明確選擇研究紀錄", None)
        self.entry_combo.currentIndexChanged.connect(self._on_entry_changed)
        controls.addWidget(self.entry_combo, 1)

        self.open_button = QPushButton("開啟所選紀錄", identity_group)
        self.open_button.clicked.connect(self.open_selected)
        controls.addWidget(self.open_button)
        identity_layout.addRow("研究紀錄", controls)
        layout.addWidget(identity_group)

        self.status_label = QLabel("請選擇帳種並輸入 portfolio_id，再明確載入登錄清單。", self)
        self.status_label.setAccessibleName("配置研究紀錄狀態")
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status_label)

        if self.workspace is None:
            self.status_label.setText("配置研究情境 workspace 尚未配置。")
        self._sync_enabled()

    def _selected_identity(self) -> tuple[str, str] | None:
        account_kind = self.account_kind_combo.currentData()
        portfolio_id = self.portfolio_id_edit.text()
        if (
            not isinstance(account_kind, str)
            or account_kind not in {"manual", "user_declared", "paper"}
            or not isinstance(portfolio_id, str)
            or not portfolio_id.strip()
        ):
            return None
        return account_kind, portfolio_id

    def _on_identity_changed(self, *_args: object) -> None:
        if self._closing:
            return
        self._generation += 1
        self._loaded_identity = None
        self._clear_entries()
        worker = self._worker
        if worker is not None:
            try:
                worker.cancel(cooperative=True, wait=False)
            except RuntimeError:
                pass
        self.status_label.setText("帳種或 portfolio_id 已變更；舊清單已清除，請重新明確載入。")
        self._sync_enabled()

    @Slot(int)
    def _on_entry_changed(self, _index: int) -> None:
        if self.entry_combo.currentData() is None:
            self.status_label.setText("尚未選取配置研究紀錄。")
        else:
            self.status_label.setText("已選取一筆登錄紀錄；按「開啟所選紀錄」送出 exact 選擇。")
        self._sync_enabled()

    def load_registered(self) -> None:
        identity = self._selected_identity()
        if identity is None:
            self.status_label.setText("請明確選取帳種並輸入 portfolio_id。")
            self._sync_enabled()
            return
        if self.workspace is None:
            self.status_label.setText("配置研究情境 workspace 尚未配置。")
            return
        if self._closing:
            return
        if self._worker is not None:
            self.status_label.setText("前一項讀取仍在收尾；完成後請再載入。")
            return

        self._generation += 1
        generation = self._generation
        self._loaded_identity = None
        self._clear_entries()
        self._worker_generation = generation
        self._worker_identity = identity
        worker = TaskWorker(_list_registered_task, self.workspace, identity[0], identity[1])
        self._worker = worker
        worker.finished.connect(self._on_worker_finished, Qt.ConnectionType.QueuedConnection)
        worker.error.connect(self._on_worker_error, Qt.ConnectionType.QueuedConnection)
        worker.cancelled.connect(self._on_worker_cancelled, Qt.ConnectionType.QueuedConnection)
        worker.native_thread_finished.connect(
            self._on_worker_native_finished, Qt.ConnectionType.QueuedConnection
        )
        self.status_label.setText("正在背景載入最多 25 筆配置研究紀錄……")
        self._sync_enabled()
        worker.start()

    @Slot()
    def open_selected(self) -> None:
        if self._closing:
            return
        identity = self._selected_identity()
        entry = self.entry_combo.currentData()
        if identity is None or identity != self._loaded_identity:
            self.status_label.setText("目前帳戶與已載入清單不一致；請重新載入。")
            self._sync_enabled()
            return
        if not isinstance(entry, ScenarioRegistryEntry):
            self.status_label.setText("請明確選取一筆配置研究紀錄。")
            self._sync_enabled()
            return
        selection = self._selection_for_entry(entry, identity)
        if selection is None:
            self._clear_entries()
            self._loaded_identity = None
            self.status_label.setText("所選紀錄與目前帳戶身分不一致；已清除清單。")
            self._sync_enabled()
            return
        self.openRequested.emit(selection)
        self.status_label.setText("已送出所選登錄紀錄；目標 workspace 將 exact 重讀 scenario。")
        self._sync_enabled()

    def begin_shutdown(self) -> None:
        self._closing = True
        self._generation += 1
        self._loaded_identity = None
        worker = self._worker
        if worker is not None:
            try:
                worker.cancel(cooperative=True, wait=False)
            except RuntimeError:
                pass
        self._sync_enabled()

    def has_running_worker(self) -> bool:
        # 保留 worker 到 native_thread_finished，避免結果 signal 早於 QThread 收尾。
        return self._worker is not None

    def closeEvent(self, event: QCloseEvent) -> None:
        self.begin_shutdown()
        if self.has_running_worker():
            event.ignore()
            return
        event.accept()

    @Slot(object)
    def _on_worker_finished(self, value: object) -> None:
        identity = self._worker_identity
        if (
            self._closing
            or self._worker_generation != self._generation
            or identity is None
            or identity != self._selected_identity()
        ):
            return
        if not self._valid_entries(value, identity):
            self._loaded_identity = None
            self.status_label.setText("登錄清單回傳格式或帳戶身分不符；未套用。")
            self._sync_enabled()
            return

        entries = value
        blocker = QSignalBlocker(self.entry_combo)
        self.entry_combo.clear()
        self.entry_combo.addItem("請明確選擇研究紀錄", None)
        for entry in entries:
            self.entry_combo.addItem(self._entry_label(entry), entry)
        del blocker
        self._loaded_identity = identity
        self.status_label.setText(
            f"已載入 {len(entries)} 筆有界配置研究紀錄；請明確選取後開啟。"
            if entries
            else "目前沒有符合明示帳戶的登錄紀錄；未選取 latest。"
        )
        self._sync_enabled()

    @Slot(str)
    def _on_worker_error(self, message: str) -> None:
        if (
            self._closing
            or self._worker_generation != self._generation
            or self._worker_identity != self._selected_identity()
        ):
            return
        bounded_message = message.replace("\r", " ").replace("\n", " ")[:500]
        self._loaded_identity = None
        self.status_label.setText(f"載入失敗，未套用登錄清單。原因：{bounded_message}")
        self._sync_enabled()

    @Slot()
    def _on_worker_cancelled(self) -> None:
        if (
            not self._closing
            and self._worker_generation == self._generation
            and self._worker_identity == self._selected_identity()
        ):
            self._loaded_identity = None
            self.status_label.setText("登錄清單讀取已取消；未套用未完成結果。")
            self._sync_enabled()

    @Slot()
    def _on_worker_native_finished(self) -> None:
        worker = self._worker
        if worker is None:
            return
        worker.deleteLater()
        self._worker = None
        self._worker_identity = None
        self._sync_enabled()

    def _clear_entries(self) -> None:
        blocker = QSignalBlocker(self.entry_combo)
        self.entry_combo.clear()
        self.entry_combo.addItem("請明確選擇研究紀錄", None)
        del blocker

    @staticmethod
    def _entry_label(entry: ScenarioRegistryEntry) -> str:
        return (
            f"{entry.registered_at.isoformat()} · 決策 {entry.decision_at.isoformat()} · "
            f"{entry.record_id} · "
            f"snapshot {entry.snapshot_id} · {entry.artifact_id}"
        )

    @staticmethod
    def _selection_for_entry(
        entry: ScenarioRegistryEntry,
        identity: tuple[str, str],
    ) -> ScenarioRegistrySelection | None:
        if (entry.account_kind, entry.portfolio_id) != identity:
            return None
        try:
            selection = entry.selection()
        except (AttributeError, TypeError, ValueError):
            return None
        if not isinstance(selection, ScenarioRegistrySelection):
            return None
        if (
            selection.record_id,
            selection.reference_sha256,
            selection.account_kind,
            selection.portfolio_id,
            selection.artifact_id,
        ) != (
            entry.record_id,
            entry.reference_sha256,
            entry.account_kind,
            entry.portfolio_id,
            entry.artifact_id,
        ):
            return None
        return selection

    @classmethod
    def _valid_entries(
        cls,
        value: object,
        identity: tuple[str, str],
    ) -> TypeGuard[tuple[ScenarioRegistryEntry, ...]]:
        if type(value) is not tuple or len(value) > 25:
            return False
        record_ids: set[str] = set()
        for entry in value:
            if not isinstance(entry, ScenarioRegistryEntry):
                return False
            if any(
                type(field_value) is not str
                for field_value in (
                    entry.record_id,
                    entry.reference_sha256,
                    entry.account_kind,
                    entry.portfolio_id,
                    entry.artifact_id,
                    entry.snapshot_id,
                    entry.input_hash,
                )
            ):
                return False
            if any(
                not isinstance(field_value, datetime)
                for field_value in (entry.decision_at, entry.source_saved_at, entry.registered_at)
            ):
                return False
            if cls._selection_for_entry(entry, identity) is None:
                return False
            if not entry.record_id:
                return False
            if entry.record_id in record_ids:
                return False
            record_ids.add(entry.record_id)
        return True

    def _sync_enabled(self) -> None:
        identity_valid = self._selected_identity() is not None
        active = self._worker is not None
        available = self.workspace is not None and not self._closing
        self.account_kind_combo.setEnabled(not self._closing)
        self.portfolio_id_edit.setEnabled(not self._closing)
        self.load_button.setEnabled(available and identity_valid and not active)
        loaded = self._loaded_identity is not None and self._loaded_identity == self._selected_identity()
        self.entry_combo.setEnabled(available and loaded and not active)
        self.open_button.setEnabled(
            available
            and loaded
            and not active
            and isinstance(self.entry_combo.currentData(), ScenarioRegistryEntry)
        )


def _list_registered_task(
    workspace: PortfolioResearchScenarioWorkspace,
    account_kind: str,
    portfolio_id: str,
    cancel_callback=None,
) -> tuple[ScenarioRegistryEntry, ...]:
    return workspace.list_registered(
        account_kind=account_kind,
        portfolio_id=portfolio_id,
        cancel_callback=cancel_callback,
    )
