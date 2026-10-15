"""沿明確選取的已保存帳本瀏覽與另存研究配置假設。"""

from __future__ import annotations

from typing import Any

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
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app_module.portfolio_allocation_dtos import AllocationWeightContract
from app_module.portfolio_research_scenario_repository import SavedPortfolioResearchScenario
from app_module.portfolio_research_scenario_service import PortfolioResearchScenarioComparison
from app_module.portfolio_research_scenario_workspace import PortfolioResearchScenarioWorkspace
from ui_qt.workers.task_worker import TaskWorker


class PortfolioResearchScenarioWidget(QWidget):
    """必須明選帳種、portfolio 與 artifact；只沿 frozen workspace 讀寫。"""

    stockResearchRequested = Signal(str)

    def __init__(
        self,
        workspace: PortfolioResearchScenarioWorkspace | None,
        disabled_reason: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.workspace = workspace
        self.disabled_reason = disabled_reason
        self._generation = 0
        self._worker: TaskWorker | None = None
        self._worker_action: str | None = None
        self._worker_generation = 0
        self._pending: tuple[int, str, tuple[Any, ...]] | None = None
        self._closing = False
        self._updating_artifact_combo = False
        self._current_saved: SavedPortfolioResearchScenario | None = None
        self._current_artifact_id = ""
        self._preview_comparison: PortfolioResearchScenarioComparison | None = None
        self._target_symbols: tuple[str, ...] = ()
        self.target_spinboxes: dict[str, QSpinBox] = {}

        layout = QVBoxLayout(self)
        identity_group = QGroupBox("明確選取已保存的人選帳本", self)
        identity_layout = QFormLayout(identity_group)
        self.account_kind_combo = QComboBox(identity_group)
        self.account_kind_combo.addItem("請選帳種", None)
        for kind in ("manual", "user_declared", "paper"):
            self.account_kind_combo.addItem(kind, kind)
        self.account_kind_combo.currentIndexChanged.connect(self._on_identity_changed)
        identity_layout.addRow("帳種", self.account_kind_combo)

        self.portfolio_id_edit = QLineEdit(identity_group)
        self.portfolio_id_edit.setPlaceholderText("請輸入 exact portfolio_id")
        self.portfolio_id_edit.textChanged.connect(self._on_identity_changed)
        identity_layout.addRow("Portfolio ID", self.portfolio_id_edit)

        saved_controls = QHBoxLayout()
        self.load_saved_button = QPushButton("載入已保存情境", identity_group)
        self.load_saved_button.clicked.connect(self.load_saved)
        saved_controls.addWidget(self.load_saved_button)
        self.saved_artifact_combo = QComboBox(identity_group)
        self.saved_artifact_combo.setAccessibleName("已保存情境 artifact ID")
        self.saved_artifact_combo.setMinimumContentsLength(30)
        self.saved_artifact_combo.addItem("請明確選擇 artifact", None)
        self.saved_artifact_combo.currentIndexChanged.connect(self._on_artifact_selection_changed)
        saved_controls.addWidget(self.saved_artifact_combo, 1)
        self.open_button = QPushButton("開啟所選", identity_group)
        self.open_button.clicked.connect(self.open_selected)
        saved_controls.addWidget(self.open_button)
        identity_layout.addRow("已保存情境", saved_controls)
        layout.addWidget(identity_group)

        self.status_label = QLabel(
            disabled_reason or "尚未載入情境；不會自動選取或套用 latest。", self
        )
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setAccessibleName("人選研究情境狀態")
        layout.addWidget(self.status_label)
        self.scope_notice_label = QLabel(
            "依已保存情境事實重研究；原時鐘不變，不代表今日帳本或重新核驗來源，不下單。",
            self,
        )
        self.scope_notice_label.setWordWrap(True)
        self.scope_notice_label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.scope_notice_label)

        self.account_summary_label = QLabel("尚無已開啟帳本。", self)
        self.account_summary_label.setWordWrap(True)
        self.account_summary_label.setTextFormat(Qt.TextFormat.PlainText)
        self.account_summary_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.account_summary_label.setAccessibleName("已保存帳本來源與時鐘")
        layout.addWidget(self.account_summary_label)
        self.valuation_summary_label = QLabel("精確現金與 NAV 尚未載入。", self)
        self.valuation_summary_label.setWordWrap(True)
        self.valuation_summary_label.setTextFormat(Qt.TextFormat.PlainText)
        self.valuation_summary_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.valuation_summary_label.setAccessibleName("已保存帳本精確估值")
        layout.addWidget(self.valuation_summary_label)

        self.positions_table = QTableWidget(0, 4, self)
        self.positions_table.setHorizontalHeaderLabels(("股票代碼", "原股數", "原標記價格", "原市場價值"))
        self.positions_table.setAccessibleName("已保存帳本原持倉")
        self.positions_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.positions_table)

        target_group = QGroupBox("明示新的研究 target（bp）", self)
        target_layout = QVBoxLayout(target_group)
        self.target_table = QTableWidget(0, 2, target_group)
        self.target_table.setHorizontalHeaderLabels(("股票代碼", "目標權重 bp"))
        self.target_table.setAccessibleName("人選研究明示目標權重")
        self.target_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        target_layout.addWidget(self.target_table)
        cash_row = QHBoxLayout()
        cash_row.addWidget(QLabel("現金目標權重 bp", target_group))
        self.cash_weight_spin = QSpinBox(target_group)
        self.cash_weight_spin.setRange(0, 10000)
        self.cash_weight_spin.setKeyboardTracking(False)
        self.cash_weight_spin.valueChanged.connect(self._on_target_changed)
        cash_row.addWidget(self.cash_weight_spin)
        cash_row.addStretch(1)
        target_layout.addLayout(cash_row)
        self.target_status_label = QLabel("請先開啟一份已保存情境。", target_group)
        self.target_status_label.setWordWrap(True)
        self.target_status_label.setTextFormat(Qt.TextFormat.PlainText)
        target_layout.addWidget(self.target_status_label)
        layout.addWidget(target_group)

        self.scenario_table = QTableWidget(0, 11, self)
        self.scenario_table.setHorizontalHeaderLabels((
            "情境", "股票代碼／名稱", "請求 bp", "目標 bp", "現有 bp", "差額 bp",
            "可執行 bp", "可執行股數", "可執行金額", "估計成本", "診斷",
        ))
        self.scenario_table.setAccessibleName("已保存與新目標研究情境比較")
        self.scenario_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.scenario_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.scenario_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.scenario_table.itemSelectionChanged.connect(self._on_scenario_selection_changed)
        layout.addWidget(self.scenario_table, 1)
        self.scenario_summary_label = QLabel("尚無情境出口與診斷。", self)
        self.scenario_summary_label.setWordWrap(True)
        self.scenario_summary_label.setTextFormat(Qt.TextFormat.PlainText)
        self.scenario_summary_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.scenario_summary_label.setAccessibleName("各情境風控與現金出口")
        layout.addWidget(self.scenario_summary_label)

        action_row = QHBoxLayout()
        self.compare_button = QPushButton("比較這份舊證據的新 target", self)
        self.compare_button.clicked.connect(self.compare_target)
        action_row.addWidget(self.compare_button)
        self.save_button = QPushButton("另存研究假設", self)
        self.save_button.clicked.connect(self.save_target)
        action_row.addWidget(self.save_button)
        self.cancel_button = QPushButton("取消讀取／比較", self)
        self.cancel_button.clicked.connect(self.cancel_current_operation)
        action_row.addWidget(self.cancel_button)
        self.stock_research_button = QPushButton("開啟所選股票研究", self)
        self.stock_research_button.clicked.connect(self._open_selected_stock_research)
        action_row.addWidget(self.stock_research_button)
        layout.addLayout(action_row)

        if disabled_reason and workspace is None:
            self.account_kind_combo.setEnabled(False)
            self.portfolio_id_edit.setEnabled(False)
        self._sync_enabled()

    @property
    def current_comparison(self) -> PortfolioResearchScenarioComparison | None:
        """回傳目前預覽或原始 saved comparison，不暴露可變設定。"""

        if self._preview_comparison is not None:
            return self._preview_comparison
        return self._current_saved.comparison if self._current_saved is not None else None

    @property
    def current_artifact_id(self) -> str:
        """預覽仍綁原封存 ID；成功另存後才改為新 ID。"""

        return self._current_artifact_id

    def load_saved(self) -> None:
        identity = self._selected_identity()
        if identity is None:
            self.status_label.setText("請明確選取帳種並輸入 portfolio_id。")
            return
        if self.workspace is None:
            self.status_label.setText(self.disabled_reason or "研究情境 workspace 尚未配置。")
            return
        self._queue("list", identity)

    def open_selected(self) -> None:
        identity = self._selected_identity()
        artifact_id = self.saved_artifact_combo.currentData()
        if identity is None or not isinstance(artifact_id, str) or not artifact_id:
            self.status_label.setText("請先載入清單，並明確選取 artifact ID。")
            return
        if self.workspace is None:
            self.status_label.setText(self.disabled_reason or "研究情境 workspace 尚未配置。")
            return
        self._queue("open", (artifact_id, *identity))

    def compare_target(self) -> None:
        identity = self._selected_identity()
        target = self._current_target_contract()
        if identity is None or self._current_saved is None or not self._current_artifact_id:
            self.status_label.setText("請先 exact 開啟一份已保存情境。")
            return
        if target is None:
            self.target_status_label.setText("各股票與現金權重合計必須正好為 10000 bp。")
            return
        if self.workspace is None:
            self.status_label.setText(self.disabled_reason or "研究情境 workspace 尚未配置。")
            return
        self._queue("compare", (self._current_artifact_id, *identity, target))

    def save_target(self) -> None:
        if self.workspace is None or not self.workspace.can_save:
            self.status_label.setText("目前資料路由為唯讀；可查看與比較，不能另存。")
            self._sync_enabled()
            return
        if self._preview_comparison is None or self._current_saved is None:
            self.status_label.setText("請先比較明示 target，完成預覽後才能另存。")
            return
        identity = self._selected_identity()
        if identity is None:
            self.status_label.setText("目前帳本選取已失效，不能另存。")
            return
        self._queue("save", (self._current_artifact_id, self._preview_comparison, *identity))

    def restore_artifact(self, artifact_id: str, stock_code: str) -> bool:
        """只在目前 exact artifact 的原股票 universe 中恢復選取。"""

        comparison = self.current_comparison
        if (
            not isinstance(artifact_id, str)
            or artifact_id != self._current_artifact_id
            or comparison is None
            or not isinstance(stock_code, str)
            or stock_code not in self._stock_universe(comparison)
        ):
            return False
        for row_index in range(self.scenario_table.rowCount()):
            item = self.scenario_table.item(row_index, 1)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == stock_code:
                self.scenario_table.selectRow(row_index)
                self.scenario_table.setCurrentCell(row_index, 1)
                return True
        return False

    def cancel_current_operation(self) -> None:
        worker = self._worker
        if worker is None or self._worker_action == "save":
            return
        self._generation += 1
        self._pending = None
        try:
            worker.cancel(cooperative=True, wait=False)
        except RuntimeError:
            pass
        self.status_label.setText("已送出合作式取消；未完成結果不會套用。")
        self._sync_enabled()

    def begin_shutdown(self) -> None:
        self._closing = True
        self._pending = None
        if self._worker is not None and self._worker_action != "save":
            self._generation += 1
            try:
                self._worker.cancel(cooperative=True, wait=False)
            except RuntimeError:
                pass

    def has_running_worker(self) -> bool:
        # finished(object) 早於 native QThread 完成；直到 native slot 才釋放參照。
        return self._worker is not None

    def closeEvent(self, event: QCloseEvent) -> None:
        self.begin_shutdown()
        if self.has_running_worker():
            event.ignore()
            return
        event.accept()

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

    def _on_identity_changed(self, *_args: Any) -> None:
        if self._worker_action == "save":
            return
        self._invalidate_pending_work()
        self._current_saved = None
        self._current_artifact_id = ""
        self._preview_comparison = None
        self._clear_artifact_ids()
        self._clear_display()
        self.status_label.setText("帳種或 portfolio_id 已變更；請重新載入並明確選取。")
        self._sync_enabled()

    @Slot(int)
    def _on_artifact_selection_changed(self, *_args: Any) -> None:
        if self._updating_artifact_combo or self._worker_action == "save":
            return
        self._invalidate_pending_work()
        self._current_saved = None
        self._current_artifact_id = ""
        self._preview_comparison = None
        self._clear_display()
        selected = self.saved_artifact_combo.currentData()
        self.status_label.setText(
            "已選取 artifact；按「開啟所選」exact 重讀。"
            if isinstance(selected, str)
            else "尚未 exact 開啟 artifact。"
        )
        self._sync_enabled()

    @Slot(int)
    def _on_target_changed(self, _value: int) -> None:
        if self._worker_action == "save":
            return
        self._generation += 1
        self._pending = None
        if self._worker is not None and self._worker_action != "save":
            try:
                self._worker.cancel(cooperative=True, wait=False)
            except RuntimeError:
                pass
        self._preview_comparison = None
        if self._current_saved is not None:
            self._render_comparison(self._current_saved.comparison)
            self.target_status_label.setText("預覽已清除；原已保存比較仍保留，重新比較以檢視新 target。")
        self._sync_enabled()

    @Slot()
    def _on_scenario_selection_changed(self) -> None:
        selected = self.scenario_table.currentRow() >= 0
        self.stock_research_button.setEnabled(
            selected and self._worker is None and not self._closing
        )

    @Slot()
    def _open_selected_stock_research(self) -> None:
        if self._worker is not None or self._closing:
            return
        row = self.scenario_table.currentRow()
        if row < 0:
            return
        item = self.scenario_table.item(row, 1)
        symbol = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        comparison = self.current_comparison
        if isinstance(symbol, str) and comparison is not None and symbol in self._stock_universe(comparison):
            self.stockResearchRequested.emit(symbol)

    def _invalidate_pending_work(self) -> None:
        self._generation += 1
        self._pending = None
        if self._worker is not None and self._worker_action != "save":
            try:
                self._worker.cancel(cooperative=True, wait=False)
            except RuntimeError:
                pass

    def _queue(self, action: str, args: tuple[Any, ...]) -> None:
        if self._closing or self.workspace is None:
            return
        self._generation += 1
        generation = self._generation
        if self._worker is not None:
            self._pending = (generation, action, args)
            if self._worker_action != "save":
                try:
                    self._worker.cancel(cooperative=True, wait=False)
                except RuntimeError:
                    pass
            self.status_label.setText("正在收尾前一項操作；新操作將在 worker 完成後開始。")
            self._sync_enabled()
            return
        self._launch(generation, action, args)

    def _launch(self, generation: int, action: str, args: tuple[Any, ...]) -> None:
        if self._closing or generation != self._generation or self.workspace is None:
            return
        if action == "list":
            account_kind, portfolio_id = args
            task = TaskWorker(_list_saved_task, self.workspace, account_kind, portfolio_id)
            self.status_label.setText("正在有界載入最多 25 份已保存情境……")
        elif action == "open":
            artifact_id, account_kind, portfolio_id = args
            task = TaskWorker(_open_exact_task, self.workspace, artifact_id, account_kind, portfolio_id)
            self.status_label.setText("正在 exact 重讀明確選取的 artifact……")
        elif action == "compare":
            artifact_id, account_kind, portfolio_id, target = args
            task = TaskWorker(
                _compare_target_task, self.workspace, artifact_id, account_kind, portfolio_id, target
            )
            self.status_label.setText("正在沿原封存帳本比較明示 target……")
        elif action == "save":
            artifact_id, comparison, account_kind, portfolio_id = args
            task = TaskWorker(
                _save_target_task, self.workspace, artifact_id, comparison, account_kind, portfolio_id
            )
            self.status_label.setText("正在另存研究假設；寫入期間不可取消或切換帳本。")
        else:
            raise ValueError("portfolio_research_scenario_action_invalid")
        self._worker = task
        self._worker_action = action
        self._worker_generation = generation
        task.finished.connect(self._on_worker_finished, Qt.ConnectionType.QueuedConnection)
        task.error.connect(self._on_worker_error, Qt.ConnectionType.QueuedConnection)
        task.cancelled.connect(self._on_worker_cancelled, Qt.ConnectionType.QueuedConnection)
        task.native_thread_finished.connect(
            self._on_worker_native_finished, Qt.ConnectionType.QueuedConnection
        )
        self._sync_enabled()
        task.start()

    @Slot(object)
    def _on_worker_finished(self, value: object) -> None:
        action = self._worker_action
        generation = self._worker_generation
        if action is None:
            return
        if action != "save" and (self._closing or generation != self._generation):
            return
        if action == "list":
            if not isinstance(value, tuple) or any(not isinstance(item, str) for item in value):
                self.status_label.setText("已保存清單回傳格式不符；未套用。")
                return
            self._replace_artifact_ids(value)
            self.status_label.setText(
                f"已載入 {len(value)} 份有界清單；請明確選擇 artifact 後開啟。"
                if value else "目前沒有已保存情境；未查詢或套用 latest。"
            )
        elif action == "open":
            if not isinstance(value, SavedPortfolioResearchScenario):
                self.status_label.setText("exact read 回傳型別不符；未套用。")
                return
            expected_id = self.saved_artifact_combo.currentData()
            identity = self._selected_identity()
            account = value.comparison.account
            if (
                value.artifact_id != expected_id
                or identity != (account.account_kind, account.portfolio_id)
            ):
                self.status_label.setText("exact artifact 或帳本 identity 已改變；讀取結果未套用。")
                return
            self._apply_saved(value)
            self.status_label.setText(f"已 exact 開啟已保存情境：{value.artifact_id}")
        elif action == "compare":
            if not isinstance(value, PortfolioResearchScenarioComparison):
                self.status_label.setText("比較結果型別不符；未套用。")
                return
            if self._current_saved is None or value.account != self._current_saved.comparison.account:
                self.status_label.setText("比較結果帳本與目前封存不同；未套用。")
                return
            self._preview_comparison = value
            self._render_comparison(value)
            self.target_status_label.setText("預覽尚未保存；原始 artifact 與原時鐘仍保留。")
            self.status_label.setText("已完成明示 target 比較；尚未另存。")
        elif action == "save":
            if not isinstance(value, SavedPortfolioResearchScenario):
                self.status_label.setText("另存結果型別不符；請以清單 exact 重讀。")
                return
            identity = self._selected_identity()
            if (
                self._preview_comparison is None
                or value.comparison != self._preview_comparison
                or identity != (value.comparison.account.account_kind, value.comparison.account.portfolio_id)
                or PortfolioResearchScenarioWorkspace.artifact_id(value.comparison) != value.artifact_id
            ):
                self.status_label.setText("另存回傳內容與目前預覽、帳本或 canonical artifact ID 不符。")
                return
            self._apply_saved(value)
            self._replace_artifact_ids((value.artifact_id, *self._listed_artifact_ids()))
            self.status_label.setText(
                f"研究假設已另存並選取新 artifact：{value.artifact_id}；來源帳本與時鐘未改寫。"
            )
        self._sync_enabled()

    @Slot(str)
    def _on_worker_error(self, message: str) -> None:
        action = self._worker_action
        generation = self._worker_generation
        if action != "save" and (self._closing or generation != self._generation):
            return
        identity = self._selected_identity()
        account_label = (
            f"{identity[0]}／{identity[1]}" if identity is not None else "未選取帳本"
        )
        artifact_label = self._current_artifact_id or "未 exact 開啟"
        bounded_message = message.replace("\r", " ").replace("\n", " ")[:500]
        operation = "另存失敗" if action == "save" else "讀取或比較失敗"
        self.status_label.setText(
            f"{operation}；帳本 {account_label}；artifact {artifact_label}；"
            f"原件仍保留，未套用未完成結果。原因：{bounded_message}"
        )
        self._sync_enabled()

    @Slot()
    def _on_worker_cancelled(self) -> None:
        if self._worker_action != "save" and not self._closing and self._worker_generation == self._generation:
            self.status_label.setText("操作已取消；未套用未完成結果。")

    @Slot()
    def _on_worker_native_finished(self) -> None:
        worker = self._worker
        if worker is None:
            return
        worker.deleteLater()
        self._worker = None
        self._worker_action = None
        pending = self._pending
        self._pending = None
        self._sync_enabled()
        if (
            pending is not None
            and not self._closing
            and pending[0] == self._generation
        ):
            self._launch(*pending)

    def _apply_saved(self, saved: SavedPortfolioResearchScenario) -> None:
        self._current_saved = saved
        self._current_artifact_id = saved.artifact_id
        self._preview_comparison = None
        self._initialize_target_controls(saved.comparison)
        self._render_comparison(saved.comparison)
        self._select_artifact_id(saved.artifact_id)

    def _initialize_target_controls(self, comparison: PortfolioResearchScenarioComparison) -> None:
        symbols = self._stock_universe(comparison)
        target = comparison.request.explicit_weights or comparison.account.current_weights
        self._target_symbols = tuple(sorted(symbols))
        self.target_spinboxes = {}
        self.target_table.setRowCount(len(self._target_symbols))
        blockers = []
        for row_index, symbol in enumerate(self._target_symbols):
            self.target_table.setItem(row_index, 0, QTableWidgetItem(symbol))
            spin = QSpinBox(self.target_table)
            spin.setRange(0, 10000)
            spin.setKeyboardTracking(False)
            blockers.append(QSignalBlocker(spin))
            spin.setValue(target.weight_for(symbol))
            spin.valueChanged.connect(self._on_target_changed)
            self.target_table.setCellWidget(row_index, 1, spin)
            self.target_spinboxes[symbol] = spin
        blockers.append(QSignalBlocker(self.cash_weight_spin))
        self.cash_weight_spin.setValue(target.cash_weight_bp)
        del blockers
        self._update_target_status()

    def _current_target_contract(self) -> AllocationWeightContract | None:
        if self._current_saved is None:
            return None
        try:
            return AllocationWeightContract(
                {symbol: self.target_spinboxes[symbol].value() for symbol in self._target_symbols},
                self.cash_weight_spin.value(),
            )
        except (KeyError, ValueError):
            return None

    def _update_target_status(self) -> None:
        contract = self._current_target_contract()
        if contract is None:
            total = sum(spin.value() for spin in self.target_spinboxes.values()) + self.cash_weight_spin.value()
            self.target_status_label.setText(f"目前合計 {total} bp；比較前須正好為 10000 bp。")
        else:
            self.target_status_label.setText("目前明示 target 合計 10000 bp；此設定只供研究，不會下單。")

    def _render_comparison(self, comparison: PortfolioResearchScenarioComparison) -> None:
        account = comparison.account
        self.account_summary_label.setText(
            f"帳種：{account.account_kind}｜Portfolio ID：{account.portfolio_id}｜"
            f"Snapshot：{account.snapshot_id}｜as of：{account.as_of_date}｜"
            f"來源可得：{account.available_at.isoformat()}｜決策時鐘：{comparison.decision_at.isoformat()}\n"
            f"來源 SHA：{account.source_hash}｜研究來源 SHA：{comparison.research_source_hash}｜"
            f"輸入 SHA：{comparison.input_hash}"
        )
        self.valuation_summary_label.setText(
            f"精確現金：{str(account.valuation.cash_amount)}｜精確 NAV：{str(account.valuation.total_value)}"
        )
        positions = account.valuation.positions
        self.positions_table.setRowCount(len(positions))
        for row_index, position in enumerate(positions):
            values = (
                position.stock_code,
                str(position.quantity),
                str(position.mark_price),
                str(position.market_value),
            )
            for column, value in enumerate(values):
                self.positions_table.setItem(row_index, column, self._exact_item(value))

        rows = [
            (scenario.scenario_kind, row)
            for scenario in comparison.scenarios
            for row in scenario.result.projection.rows
        ]
        self.scenario_table.setRowCount(len(rows))
        for row_index, (scenario_kind, row) in enumerate(rows):
            values = (
                scenario_kind,
                f"{row.stock_code}／{row.stock_name}",
                str(row.rule_requested_weight_bp),
                str(row.target_weight_bp),
                "未提供" if row.current_weight_bp is None else str(row.current_weight_bp),
                "未提供" if row.gap_weight_bp is None else str(row.gap_weight_bp),
                "未提供" if row.executable_weight_bp is None else str(row.executable_weight_bp),
                "未提供" if row.executable_shares is None else str(row.executable_shares),
                str(row.executable_amount),
                str(row.estimated_cost),
                "；".join(row.diagnostics) if row.diagnostics else "未提供",
            )
            for column, value in enumerate(values):
                item = self._exact_item(value)
                if column == 1:
                    item.setData(Qt.ItemDataRole.UserRole, row.stock_code)
                self.scenario_table.setItem(row_index, column, item)
        self.scenario_table.clearSelection()
        self.scenario_table.setCurrentCell(-1, -1)
        summaries = []
        for scenario in comparison.scenarios:
            projection = scenario.result.projection
            reasons = "；".join(projection.reasons) if projection.reasons else "未提供"
            summaries.append(
                f"{scenario.scenario_kind}｜建議動作：{projection.advice_action}｜"
                f"交易後現金：{str(projection.post_cost_cash_amount)}｜"
                f"估計總成本：{str(projection.total_estimated_cost)}｜原因：{reasons}"
            )
        self.scenario_summary_label.setText("\n".join(summaries) if summaries else "尚無情境出口與診斷。")
        self._update_target_status()
        self._on_scenario_selection_changed()

    @staticmethod
    def _exact_item(value: str) -> QTableWidgetItem:
        item = QTableWidgetItem(value)
        item.setToolTip(value)
        return item

    @staticmethod
    def _stock_universe(comparison: PortfolioResearchScenarioComparison) -> set[str]:
        return (
            set(comparison.request.candidate_symbols)
            | set(comparison.account.current_weights.symbol_weights_bp)
            | {row.stock_code for row in comparison.account.positions}
            | {row.stock_code for row in comparison.account.valuation.positions}
        )

    def _replace_artifact_ids(self, artifact_ids: tuple[str, ...]) -> None:
        bounded = tuple(dict.fromkeys(artifact_ids))[:25]
        self._updating_artifact_combo = True
        blocker = QSignalBlocker(self.saved_artifact_combo)
        self.saved_artifact_combo.clear()
        self.saved_artifact_combo.addItem("請明確選擇 artifact", None)
        for artifact_id in bounded:
            self.saved_artifact_combo.addItem(artifact_id, artifact_id)
        if self._current_artifact_id and self._current_artifact_id in bounded:
            self.saved_artifact_combo.setCurrentIndex(
                self.saved_artifact_combo.findData(self._current_artifact_id)
            )
        else:
            self.saved_artifact_combo.setCurrentIndex(0)
        del blocker
        self._updating_artifact_combo = False

    def _select_artifact_id(self, artifact_id: str) -> None:
        self._updating_artifact_combo = True
        blocker = QSignalBlocker(self.saved_artifact_combo)
        index = self.saved_artifact_combo.findData(artifact_id)
        if index < 0:
            self.saved_artifact_combo.addItem(artifact_id, artifact_id)
            index = self.saved_artifact_combo.findData(artifact_id)
        self.saved_artifact_combo.setCurrentIndex(index)
        del blocker
        self._updating_artifact_combo = False

    def _listed_artifact_ids(self) -> tuple[str, ...]:
        return tuple(
            str(self.saved_artifact_combo.itemData(index))
            for index in range(self.saved_artifact_combo.count())
            if isinstance(self.saved_artifact_combo.itemData(index), str)
        )

    def _clear_artifact_ids(self) -> None:
        self._updating_artifact_combo = True
        blocker = QSignalBlocker(self.saved_artifact_combo)
        self.saved_artifact_combo.clear()
        self.saved_artifact_combo.addItem("請明確選擇 artifact", None)
        del blocker
        self._updating_artifact_combo = False

    def _clear_display(self) -> None:
        self.account_summary_label.setText("尚無已開啟帳本。")
        self.valuation_summary_label.setText("精確現金與 NAV 尚未載入。")
        self.positions_table.setRowCount(0)
        self.scenario_table.setRowCount(0)
        self.scenario_summary_label.setText("尚無情境出口與診斷。")
        self.target_table.setRowCount(0)
        self.target_spinboxes = {}
        self._target_symbols = ()
        blocker = QSignalBlocker(self.cash_weight_spin)
        self.cash_weight_spin.setValue(0)
        del blocker
        self.target_status_label.setText("請先開啟一份已保存情境。")
        self.stock_research_button.setEnabled(False)

    def _sync_enabled(self) -> None:
        if self.workspace is None:
            self.load_saved_button.setEnabled(False)
            self.open_button.setEnabled(False)
            self.compare_button.setEnabled(False)
            self.save_button.setEnabled(False)
            self.cancel_button.setEnabled(False)
            self.stock_research_button.setEnabled(False)
            return
        locked = self._worker_action == "save"
        identity = self._selected_identity() is not None
        selected_id = isinstance(self.saved_artifact_combo.currentData(), str)
        busy = self._worker is not None
        self.account_kind_combo.setEnabled(not locked and not self._closing)
        self.portfolio_id_edit.setEnabled(not locked and not self._closing)
        self.load_saved_button.setEnabled(identity and not locked and not self._closing)
        self.saved_artifact_combo.setEnabled(not locked and not self._closing)
        self.open_button.setEnabled(selected_id and not busy and not self._closing)
        has_saved = self._current_saved is not None and bool(self._current_artifact_id)
        self.target_table.setEnabled(has_saved and not locked and not self._closing)
        self.cash_weight_spin.setEnabled(has_saved and not locked and not self._closing)
        self.compare_button.setEnabled(
            has_saved and self._current_target_contract() is not None and not busy and not self._closing
        )
        can_save = bool(getattr(self.workspace, "can_save", False))
        self.save_button.setEnabled(
            can_save and self._preview_comparison is not None and has_saved and not busy and not self._closing
        )
        self.cancel_button.setEnabled(
            busy and self._worker_action != "save" and not self._closing
        )
        self.stock_research_button.setEnabled(
            self.scenario_table.currentRow() >= 0
            and self._worker is None
            and not self._closing
        )


def _list_saved_task(
    workspace: PortfolioResearchScenarioWorkspace,
    account_kind: str,
    portfolio_id: str,
    cancel_callback=None,
) -> tuple[str, ...]:
    return workspace.list_saved(
        account_kind=account_kind,
        portfolio_id=portfolio_id,
        cancel_callback=cancel_callback,
    )


def _open_exact_task(
    workspace: PortfolioResearchScenarioWorkspace,
    artifact_id: str,
    account_kind: str,
    portfolio_id: str,
    cancel_callback=None,
) -> SavedPortfolioResearchScenario:
    return workspace.open_exact(
        artifact_id,
        account_kind=account_kind,
        portfolio_id=portfolio_id,
        cancel_callback=cancel_callback,
    )


def _compare_target_task(
    workspace: PortfolioResearchScenarioWorkspace,
    artifact_id: str,
    account_kind: str,
    portfolio_id: str,
    target: AllocationWeightContract,
    cancel_callback=None,
) -> PortfolioResearchScenarioComparison:
    return workspace.compare_target(
        artifact_id,
        account_kind=account_kind,
        portfolio_id=portfolio_id,
        explicit_weights=target,
        cancel_callback=cancel_callback,
    )


def _save_target_task(
    workspace: PortfolioResearchScenarioWorkspace,
    artifact_id: str,
    comparison: PortfolioResearchScenarioComparison,
    account_kind: str,
    portfolio_id: str,
) -> SavedPortfolioResearchScenario:
    return workspace.save_target(
        artifact_id,
        comparison,
        account_kind=account_kind,
        portfolio_id=portfolio_id,
    )
