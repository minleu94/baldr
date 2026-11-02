from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QResizeEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app_module.evidence_operations_history_dashboard_dtos import (
    EvidenceOperationsHistoryDashboardRequest,
    EvidenceOperationsHistoryDashboardResult,
)
from ui_qt.evidence_operations_history_labels import (
    EVIDENCE_REVIEW_STATUS_LABELS,
    EVIDENCE_SCHEDULER_READINESS_LABELS,
)
from ui_qt.models.evidence_operations_history_table_model import EvidenceOperationsHistoryTableModel
from ui_qt.theme import MIDNIGHT_ANALYST
from ui_qt.widgets.date_filter_edit import OptionalDateFilterEdit, date_filter_value
from ui_qt.widgets.layout_helpers import create_more_actions_button
from ui_qt.widgets.table_style import apply_financial_table_style
from ui_qt.workers.task_worker import TaskWorker


CARD_TITLES = {
    "reviews_count": "週報紀錄",
    "needs_manual_review_count": "需人工覆盤",
    "coverage_only_count": "僅覆蓋率",
    "ready_for_closeout_count": "可收尾",
    "production_scheduler_allowed_count": "允許正式排程",
    "warnings_count": "警告",
}
WIDE_CARD_ROW_MIN_WIDTH = 1050
CARD_COLUMNS_PER_ROW = 3

class EvidenceOperationsHistoryView(QWidget):
    def __init__(
        self,
        dashboard_service,
        *,
        approval_service=None,
        history_service_factory=None,
        approval_service_factory=None,
        action_lifecycle_service_factory=None,
        candidate_history_save_service_factory=None,
        history_source_path: str = "",
        auto_refresh: bool = True,
        async_refresh: bool = True,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.dashboard_service = dashboard_service
        self.approval_service = approval_service
        self.history_service_factory = history_service_factory
        self.approval_service_factory = approval_service_factory
        self.action_lifecycle_service_factory = action_lifecycle_service_factory
        self.candidate_history_save_service_factory = candidate_history_save_service_factory
        self.history_source_path = str(history_source_path or "").strip()
        self._history_source_is_explicit = False
        self.action_item_projection_path = ""
        self.async_refresh = async_refresh
        self._active_request_id = 0
        self._workers: list[TaskWorker] = []
        self._current_result: EvidenceOperationsHistoryDashboardResult | None = None
        self._selected_row = None
        self._cursor_stack = [None]
        self._page_index = 0
        self._loading = False
        self._candidate_history_save_in_progress = False
        self._filters_dirty = False
        self._active_filter = (None, None)
        self._card_columns = 0
        self._setup_ui()
        self._update_candidate_history_save_state()
        self._update_pagination_buttons(None)
        self._set_all_cards("尚未載入")
        if auto_refresh:
            self.refresh_dashboard()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        filter_row = QGridLayout()
        self.start_date_input = OptionalDateFilterEdit()
        self.end_date_input = OptionalDateFilterEdit()
        self.start_date_input.dateChanged.connect(self._on_filter_changed)
        self.end_date_input.dateChanged.connect(self._on_filter_changed)
        self.refresh_button = QPushButton("重新整理")
        self.refresh_button.setProperty("variant", "primary")
        self.refresh_button.clicked.connect(self.refresh_dashboard)
        self.previous_button = QPushButton("上一頁")
        self.previous_button.clicked.connect(self.previous_page)
        self.next_button = QPushButton("下一頁")
        self.next_button.clicked.connect(self.next_page)
        filter_row.addWidget(QLabel("開始日"), 0, 0)
        filter_row.addWidget(self.start_date_input, 0, 1)
        filter_row.addWidget(QLabel("結束日"), 0, 2)
        filter_row.addWidget(self.end_date_input, 0, 3)
        filter_row.addWidget(self.refresh_button, 0, 4)
        filter_row.addWidget(self.previous_button, 0, 5)
        filter_row.addWidget(self.next_button, 0, 6)

        self.operations_drawer = QWidget(self)
        self.operations_drawer.setObjectName("evidenceOperationsHistoryDrawer")
        drawer_layout = QVBoxLayout(self.operations_drawer)
        drawer_layout.setContentsMargins(0, 0, 0, 0)
        drawer_layout.setSpacing(6)

        history_source_row = QHBoxLayout()
        self.history_source_label = QLabel(
            f"週報歷史來源：{self.history_source_path or '應用程式預設路由'}（列表唯讀；僅明選 working-copy 可追加候選週報）"
        )
        self.history_source_label.setWordWrap(True)
        self.history_source_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        history_source_row.addWidget(self.history_source_label, stretch=1)
        self.choose_history_source_button = QPushButton("選擇 working-copy DB…")
        self.choose_history_source_button.setToolTip(
            "只讀取你明選的週報歷史 working-copy，不建立 DB 或 schema。PERSONAL store 路由不接受自訂路徑。"
        )
        self.choose_history_source_button.setEnabled(
            self.history_service_factory is not None
            and self.approval_service_factory is not None
        )
        self.choose_history_source_button.clicked.connect(self._choose_history_source)
        history_source_row.addWidget(self.choose_history_source_button)
        self.default_history_source_button = QPushButton("還原預設")
        self.default_history_source_button.setEnabled(
            self.history_service_factory is not None
            and self.approval_service_factory is not None
        )
        self.default_history_source_button.clicked.connect(
            lambda: self._apply_history_source(None)
        )
        history_source_row.addWidget(self.default_history_source_button)
        drawer_layout.addLayout(history_source_row)

        action_lifecycle_row = QHBoxLayout()
        self.action_item_projection_label = QLabel("Action Item 狀態投影：尚未選擇（唯讀週報來源不會被修改）")
        self.action_item_projection_label.setWordWrap(True)
        self.action_item_projection_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        action_lifecycle_row.addWidget(self.action_item_projection_label, stretch=1)
        self.choose_action_item_projection_button = QPushButton("選擇 Action Item 投影檔…")
        self.choose_action_item_projection_button.setEnabled(
            self.action_lifecycle_service_factory is not None
            and self._history_source_is_explicit
        )
        self.choose_action_item_projection_button.setToolTip(
            "選擇獨立的 append-only JSON 投影；不會寫週報 SQLite 或 Owner 核准投影。"
        )
        self.choose_action_item_projection_button.clicked.connect(
            self._choose_action_item_projection
        )
        action_lifecycle_row.addWidget(self.choose_action_item_projection_button)
        self.review_action_items_button = QPushButton("檢視／更新 Action Items…")
        self.review_action_items_button.setEnabled(False)
        self.review_action_items_button.setToolTip(
            "需先明選安全的 working-copy DB 與獨立 Action Item 投影檔。"
        )
        self.review_action_items_button.clicked.connect(self._review_action_items)
        action_lifecycle_row.addWidget(self.review_action_items_button)
        drawer_layout.addLayout(action_lifecycle_row)
        self.action_item_lifecycle_status_label = QLabel(
            "Action Item 處置是人工自我聲明，不代表週報核准或 Gate 2 通過。"
        )
        self.action_item_lifecycle_status_label.setWordWrap(True)
        drawer_layout.addWidget(self.action_item_lifecycle_status_label)

        approval_row = QGridLayout()
        self.owner_approval_button = QPushButton("Owner 覆核此週報…")
        self.owner_approval_button.setToolTip(
            "以具名 owner 核准所選週報快照，建立 append-only 人工覆核紀錄；不會啟用排程或授予來源／Gate 資格。"
        )
        self.owner_approval_button.setEnabled(False)
        self.owner_approval_button.clicked.connect(self._approve_selected_weekly_review)
        self.owner_approval_status_label = QLabel(
            "請先選取一筆週報。Owner 覆核是人工聲明，程式不會驗證登入身分。"
        )
        self.owner_approval_status_label.setWordWrap(True)
        approval_row.addWidget(self.owner_approval_button, 0, 0)
        approval_row.addWidget(self.owner_approval_status_label, 0, 1)
        self.save_candidate_history_button = QPushButton("保存候選決定至週報 history…")
        self.save_candidate_history_button.setToolTip(
            "重新核驗候選 artifact 與 sidecar，重建週報並只保存至明選的非正式 working-copy DB。"
        )
        self.save_candidate_history_button.clicked.connect(
            self._save_candidate_decision_to_history
        )
        approval_row.addWidget(self.save_candidate_history_button, 1, 0)
        self.save_candidate_history_status_label = QLabel(
            "這只保存週報 history；不建立 Owner 核准、不處理 Action Items，也不授 Gate credit。"
        )
        self.save_candidate_history_status_label.setWordWrap(True)
        approval_row.addWidget(self.save_candidate_history_status_label, 1, 1)
        drawer_layout.addLayout(approval_row)

        self.operations_more_button = create_more_actions_button(
            "展開來源切換、Action Item 與進階覆核工具",
            targets=[self.operations_drawer],
            expanded=False,
            tooltip_collapsed="展開來源切換、Action Item 與進階覆核工具",
            tooltip_expanded="收合來源切換、Action Item 與進階覆核工具",
            object_name="evidenceOperationsHistoryMoreButton",
            accessible_name="展開或收合週報歷史來源與進階覆核工具",
            parent=self,
        )
        filter_row.addWidget(self.operations_more_button, 0, 7)
        root.addLayout(filter_row)
        root.addWidget(self.operations_drawer)

        self.cards_layout = QGridLayout()
        self.cards_layout.setHorizontalSpacing(8)
        self.cards_layout.setVerticalSpacing(8)
        self.cards = {field: self._make_card(title) for field, title in CARD_TITLES.items()}
        root.addLayout(self.cards_layout)
        self._update_card_layout(self.width())

        self.empty_state_label = QLabel("")
        self.empty_state_label.setWordWrap(True)
        self.empty_state_label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.warning};")
        root.addWidget(self.empty_state_label)

        self.scope_label = QLabel("")
        self.scope_label.setWordWrap(True)
        root.addWidget(self.scope_label)

        self.table_model = EvidenceOperationsHistoryTableModel()
        self.summary_table = QTableView()
        self.summary_table.setModel(self.table_model)
        apply_financial_table_style(self.summary_table)
        self.summary_table.setSelectionBehavior(QTableView.SelectRows)
        self.summary_table.setFont(QFont("Consolas", 9))
        self.summary_table.clicked.connect(self._on_table_row_clicked)
        root.addWidget(self.summary_table, stretch=3)

        self.detail_panel = QTextEdit()
        self.detail_panel.setReadOnly(True)
        self.detail_panel.setFont(QFont("Consolas", 9))
        root.addWidget(self.detail_panel, stretch=1)

    def _choose_history_source(self) -> None:
        if (
            self._candidate_history_save_in_progress
            or self.history_service_factory is None
            or self.approval_service_factory is None
        ):
            return
        selected_path, _ = QFileDialog.getOpenFileName(
            self,
            "選擇 Evidence weekly-review working-copy DB",
            self.history_source_path,
            "SQLite database (*.db *.sqlite *.sqlite3);;All files (*.*)",
        )
        if selected_path:
            self._apply_history_source(selected_path)

    def _choose_action_item_projection(self) -> None:
        if (
            self._candidate_history_save_in_progress
            or self.action_lifecycle_service_factory is None
            or not self._history_source_is_explicit
        ):
            return
        selected_path, _ = QFileDialog.getSaveFileName(
            self,
            "選擇 Action Item append-only 投影檔",
            self.action_item_projection_path,
            "JSON files (*.json)",
        )
        if not selected_path:
            return
        try:
            service = self.action_lifecycle_service_factory(
                self.history_source_path, selected_path
            )
            service.list_action_items()
        except Exception as exc:  # noqa: BLE001 - show a concise safe-path diagnostic.
            QMessageBox.warning(self, "Action Item 投影未設定", str(exc))
            return
        self.action_item_projection_path = selected_path
        self.action_item_projection_label.setText(
            f"Action Item 狀態投影：{selected_path}（append-only；formal credit=false）"
        )
        self._update_action_lifecycle_controls()

    def _apply_history_source(self, db_path: str | None) -> bool:
        if (
            self._candidate_history_save_in_progress
            or self.history_service_factory is None
            or self.approval_service_factory is None
        ):
            return False
        try:
            dashboard_service = self.history_service_factory(db_path)
            approval_service = self.approval_service_factory(db_path)
        except Exception as exc:  # noqa: BLE001 - show a concise safe-path diagnostic.
            QMessageBox.warning(
                self,
                "週報歷史來源未切換",
                _history_source_error_message(exc),
            )
            return False
        selected_path = str(db_path or "").strip()
        if selected_path != self.history_source_path:
            self.action_item_projection_path = ""
            if hasattr(self, "action_item_projection_label"):
                self.action_item_projection_label.setText(
                    "Action Item 狀態投影：尚未選擇（唯讀週報來源不會被修改）"
                )
        self.dashboard_service = dashboard_service
        self.approval_service = approval_service
        self.history_source_path = selected_path
        self._history_source_is_explicit = bool(self.history_source_path)
        self.history_source_label.setText(
            f"週報歷史來源：{self.history_source_path or '應用程式預設路由'}（列表唯讀；僅明選 working-copy 可追加候選週報）"
        )
        self.refresh_dashboard()
        self._update_action_lifecycle_controls()
        self._update_candidate_history_save_state()
        return True

    def _update_action_lifecycle_controls(self) -> None:
        available = not self._candidate_history_save_in_progress
        if hasattr(self, "review_action_items_button"):
            self.review_action_items_button.setEnabled(
                available
                and self.action_lifecycle_service_factory is not None
                and self._history_source_is_explicit
                and bool(self.action_item_projection_path)
            )
        if hasattr(self, "choose_action_item_projection_button"):
            self.choose_action_item_projection_button.setEnabled(
                available
                and self.action_lifecycle_service_factory is not None
                and self._history_source_is_explicit
            )

    def _set_candidate_history_operation_busy(self, busy: bool) -> None:
        """Freeze source and review controls while a candidate write is in flight."""
        self._candidate_history_save_in_progress = busy
        source_available = (
            self.history_service_factory is not None
            and self.approval_service_factory is not None
        )
        self.choose_history_source_button.setEnabled(source_available and not busy)
        self.default_history_source_button.setEnabled(source_available and not busy)
        self.start_date_input.setEnabled(not busy)
        self.end_date_input.setEnabled(not busy)
        self.refresh_button.setEnabled(not busy and not self._loading)
        self._update_pagination_buttons(self._current_result)
        self._update_owner_approval_state()
        self._update_action_lifecycle_controls()
        self._update_candidate_history_save_state()

    def _update_candidate_history_save_state(self) -> None:
        button = getattr(self, "save_candidate_history_button", None)
        if button is None:
            return
        button.setEnabled(
            self.candidate_history_save_service_factory is not None
            and self._history_source_is_explicit
            and not self._loading
            and not self._candidate_history_save_in_progress
        )

    def _save_candidate_decision_to_history(self) -> None:
        if (
            self._candidate_history_save_in_progress
            or self._loading
            or self.candidate_history_save_service_factory is None
            or not self._history_source_is_explicit
        ):
            return
        start_date = date_filter_value(self.start_date_input)
        end_date = date_filter_value(self.end_date_input)
        if not start_date or not end_date:
            QMessageBox.warning(
                self,
                "需要明確週期",
                "請先填入開始日與結束日；系統會用這兩天重建週報並核對候選期別。",
            )
            return

        artifact_path, _ = QFileDialog.getOpenFileName(
            self,
            "選擇候選覆核決定 artifact",
            self.history_source_path,
            "JSON artifact (*.json)",
        )
        if not artifact_path:
            return
        sidecar_path, _ = QFileDialog.getOpenFileName(
            self,
            "選擇 artifact 綁定的 weekly collection sidecar",
            str(Path(artifact_path).parent),
            "SQLite database (*.db *.sqlite *.sqlite3);;All files (*.*)",
        )
        if not sidecar_path:
            return
        confirmation = (
            "將重建指定期間週報並把候選處置附加到所選 history working-copy。\n\n"
            f"期間：{start_date} 至 {end_date}\n"
            f"Working-copy：{self.history_source_path}\n"
            f"Candidate artifact：{artifact_path}\n"
            f"Collection sidecar：{sidecar_path}\n\n"
            "只寫週報 history。Owner 核准仍需下一步另行執行；不寫 sidecar／正式資料、不建立 Action Items、不授 Gate 或排程資格。"
        )
        if (
            QMessageBox.question(
                self,
                "確認保存候選決定至週報 history",
                confirmation,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self._set_candidate_history_operation_busy(True)
        self.save_candidate_history_status_label.setText(
            "正在重建週報並重新核驗候選 artifact、sidecar 與工作副本；完成前不會寫入。"
        )
        if self.async_refresh:
            worker = TaskWorker(
                self.candidate_history_save_service_factory,
                self.history_source_path,
                start_date=start_date,
                end_date=end_date,
                decision_artifact_path=artifact_path,
                sidecar_path=sidecar_path,
            )
            worker.finished.connect(self._on_candidate_history_saved)
            worker.error.connect(self._on_candidate_history_save_error)
            worker.finished.connect(lambda _result, item=worker: self._release_worker(item))
            worker.error.connect(lambda _message, item=worker: self._release_worker(item))
            self._workers.append(worker)
            worker.start()
            return
        try:
            record = self.candidate_history_save_service_factory(
                self.history_source_path,
                start_date=start_date,
                end_date=end_date,
                decision_artifact_path=artifact_path,
                sidecar_path=sidecar_path,
            )
        except Exception as exc:  # noqa: BLE001 - preserve bridge validation diagnostics.
            self._on_candidate_history_save_error(f"{type(exc).__name__}: {exc}")
            return
        self._on_candidate_history_saved(record)

    def _on_candidate_history_saved(self, record: Any) -> None:
        self.save_candidate_history_status_label.setText(
            f"已保存並讀回週報 history：{record.review_id}／{record.review_hash}。"
            "下一步請重新整理、核對相同 ID/hash，再由 Owner 另行覆核；這不是 Gate 2 通過。"
        )
        self._set_candidate_history_operation_busy(False)
        self.refresh_dashboard()

    def _on_candidate_history_save_error(self, message: str) -> None:
        QMessageBox.warning(
            self,
            "週報 history 未保存",
            f"{message.splitlines()[0]}\n\n未能確認候選與週期一致；請修正來源後重試。",
        )
        self.save_candidate_history_status_label.setText(
            "保存失敗；沒有核准或 Gate 資格變更。請確認 artifact、sidecar、期間與 working-copy。"
        )
        self._set_candidate_history_operation_busy(False)

    def _review_action_items(self) -> None:
        if (
            self._candidate_history_save_in_progress
            or not self.review_action_items_button.isEnabled()
        ):
            return
        try:
            service = self.action_lifecycle_service_factory(
                self.history_source_path, self.action_item_projection_path
            )
            items = service.list_action_items()
        except Exception as exc:  # noqa: BLE001 - projection/source errors remain visible.
            QMessageBox.warning(self, "Action Items 無法載入", str(exc))
            return
        if not items:
            QMessageBox.information(self, "Action Items", "此 working-copy 尚無 Action Item。")
            return
        dialog = ActionItemLifecycleDialog(items, self)
        if dialog.exec() != QDialog.Accepted:
            return
        selection = dialog.selection()
        try:
            event = service.record_transition(
                selection["action_item_id"],
                new_status=selection["new_status"],
                actor_name=selection["actor_name"],
                actor_role=selection["actor_role"],
                note=selection["note"],
            )
        except Exception as exc:  # noqa: BLE001 - do not conceal stale source or broken history.
            QMessageBox.warning(self, "Action Item 未保存", str(exc))
            return
        self.action_item_lifecycle_status_label.setText(
            f"已追加 {event['to_status']} 處置事件（{event['event_sha256']}）；"
            "僅為人工追蹤紀錄，不代表週報核准或 Gate 2 通過。"
        )

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._update_card_layout(event.size().width())

    def _update_card_layout(self, width: int) -> None:
        columns = len(self.cards) if width >= WIDE_CARD_ROW_MIN_WIDTH else CARD_COLUMNS_PER_ROW
        if columns == self._card_columns:
            return
        for card in self.cards.values():
            self.cards_layout.removeWidget(card)
        for index, card in enumerate(self.cards.values()):
            self.cards_layout.addWidget(card, index // columns, index % columns)
        self._card_columns = columns

    def refresh_dashboard(self) -> None:
        if self._candidate_history_save_in_progress:
            return
        self._active_filter = (
            date_filter_value(self.start_date_input),
            date_filter_value(self.end_date_input),
        )
        self._filters_dirty = False
        request = EvidenceOperationsHistoryDashboardRequest(
            start_date=self._active_filter[0],
            end_date=self._active_filter[1],
        )
        self._cursor_stack = [None]
        self._page_index = 0
        self._request_dashboard(request)

    def next_page(self) -> None:
        if (
            self._candidate_history_save_in_progress
            or self._loading
            or self._filters_dirty
            or self._current_result is None
            or self._current_result.next_cursor is None
        ):
            return
        self._cursor_stack.append(self._current_result.next_cursor)
        self._page_index += 1
        self._request_dashboard(self._current_page_request())

    def previous_page(self) -> None:
        if (
            self._candidate_history_save_in_progress
            or self._loading
            or self._filters_dirty
            or self._page_index <= 0
        ):
            return
        self._cursor_stack.pop()
        self._page_index -= 1
        self._request_dashboard(self._current_page_request())

    def _current_page_request(self) -> EvidenceOperationsHistoryDashboardRequest:
        return EvidenceOperationsHistoryDashboardRequest(
            start_date=self._active_filter[0],
            end_date=self._active_filter[1],
            cursor=self._cursor_stack[self._page_index],
        )

    def _request_dashboard(self, request: EvidenceOperationsHistoryDashboardRequest) -> None:
        if self._candidate_history_save_in_progress:
            return
        self._active_request_id += 1
        request_id = self._active_request_id
        self._loading = True
        self._update_candidate_history_save_state()
        self._current_result = None
        self.refresh_button.setEnabled(False)
        self.previous_button.setEnabled(False)
        self.next_button.setEnabled(False)
        self._set_all_cards("載入中")
        self.table_model.set_rows(())
        self.empty_state_label.setText("")
        self.scope_label.setText("")
        self.detail_panel.setPlainText("")
        self._selected_row = None
        self.owner_approval_button.setEnabled(False)
        if self.async_refresh:
            worker = TaskWorker(self.dashboard_service.load_dashboard, request)
            worker.finished.connect(lambda result, rid=request_id: self._on_dashboard_loaded(result, rid))
            worker.error.connect(lambda message, rid=request_id: self._on_dashboard_error(message, rid))
            worker.finished.connect(lambda _result, item=worker: self._release_worker(item))
            worker.error.connect(lambda _message, item=worker: self._release_worker(item))
            self._workers.append(worker)
            worker.start()
            return
        try:
            self._on_dashboard_loaded(self.dashboard_service.load_dashboard(request), request_id=request_id)
        except Exception as exc:  # noqa: BLE001
            self._on_dashboard_error(str(exc), request_id=request_id)

    def _on_dashboard_loaded(self, result: EvidenceOperationsHistoryDashboardResult, request_id: int) -> None:
        if request_id != self._active_request_id:
            return
        self._loading = False
        self.refresh_button.setEnabled(not self._candidate_history_save_in_progress)
        self._update_candidate_history_save_state()
        self._current_result = result
        if result.source_available:
            for field_name, card in self.cards.items():
                self._set_card(card, card.property("title"), getattr(result.cards, field_name))
        else:
            self._set_all_cards("未知")
        self.empty_state_label.setText(result.empty_state_message)
        self.scope_label.setText(_scope_message(result, self._page_index))
        self._update_pagination_buttons(result)
        self.table_model.set_rows(result.rows)
        self.summary_table.resizeColumnsToContents()
        if result.rows:
            self._render_details(result.rows[0], result)
            self._selected_row = result.rows[0]
            self._update_owner_approval_state()
        else:
            self.detail_panel.setPlainText("\n".join(result.limitations))

    def _on_dashboard_error(self, message: str, request_id: int) -> None:
        if request_id != self._active_request_id:
            return
        self._loading = False
        self.refresh_button.setEnabled(not self._candidate_history_save_in_progress)
        self._update_candidate_history_save_state()
        self._current_result = None
        self._set_all_cards("未知")
        self.table_model.set_rows(())
        self._selected_row = None
        self.owner_approval_button.setEnabled(False)
        self.empty_state_label.setText(f"Evidence operations history 載入失敗：{message.splitlines()[0]}")
        self.scope_label.setText("")
        self.detail_panel.setPlainText("")
        self._update_pagination_buttons(None)

    def _update_pagination_buttons(self, result: EvidenceOperationsHistoryDashboardResult | None) -> None:
        self.previous_button.setEnabled(
            not self._candidate_history_save_in_progress
            and not self._loading
            and not self._filters_dirty
            and self._page_index > 0
        )
        self.next_button.setEnabled(
            not self._candidate_history_save_in_progress
            and not self._loading
            and not self._filters_dirty
            and result is not None
            and result.next_cursor is not None
        )

    def _on_filter_changed(self, _date) -> None:
        if self._candidate_history_save_in_progress:
            return
        current_filter = (
            date_filter_value(self.start_date_input),
            date_filter_value(self.end_date_input),
        )
        if current_filter == self._active_filter:
            return
        self._active_request_id += 1
        self._filters_dirty = True
        self._loading = False
        self._current_result = None
        self._cursor_stack = [None]
        self._page_index = 0
        self.refresh_button.setEnabled(True)
        self._set_all_cards("待重新整理")
        self.table_model.set_rows(())
        self.empty_state_label.setText("日期篩選已變更；請按重新整理載入結果。")
        self.scope_label.setText("")
        self.detail_panel.setPlainText("")
        self._update_pagination_buttons(None)

    def _on_table_row_clicked(self, index) -> None:
        row = self.table_model.row_at(index.row())
        if row is not None and self._current_result is not None:
            self._selected_row = row
            self._render_details(row, self._current_result)
            self._update_owner_approval_state()

    def _update_owner_approval_state(self) -> None:
        row = self._selected_row
        enabled = (
            not self._candidate_history_save_in_progress
            and self.approval_service is not None
            and bool(getattr(self.approval_service, "projection_configured", False))
            and row is not None
            and bool(row.review_id)
            and bool(row.review_hash)
        )
        self.owner_approval_button.setEnabled(bool(enabled))
        if self.approval_service is None:
            self.owner_approval_status_label.setText(
                "Owner 覆核尚未接線；目前只讀取歷史。"
            )
        elif not bool(getattr(self.approval_service, "projection_configured", False)):
            self.owner_approval_status_label.setText(
                "尚未設定覆核投影檔；設定 WEEKLY_EVIDENCE_HISTORY_PROJECTION_PATH 並重啟程式後才能保存。"
            )
        elif row is None:
            self.owner_approval_status_label.setText("請先選取一筆週報。")
        elif not row.review_hash:
            self.owner_approval_status_label.setText(
                "此舊週報沒有可核對的 SHA-256，不能建立 hash-pinned 覆核。"
            )
        else:
            self.owner_approval_status_label.setText(
                "覆核只綁定目前選取的報告 hash；不授予來源接受、Gate credit 或正式排程權限。"
            )

    def _approve_selected_weekly_review(self) -> None:
        if self._candidate_history_save_in_progress:
            return
        row = self._selected_row
        if self.approval_service is None or row is None or not row.review_hash:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Owner 覆核週報快照")
        layout = QVBoxLayout(dialog)
        identity = QLineEdit()
        identity.setPlaceholderText("輸入實際覆核者姓名或可追溯識別")
        role = QLineEdit()
        role.setPlaceholderText("例如：Portfolio Owner")
        note = QTextEdit()
        note.setPlaceholderText("記錄已檢查的證據、資料品質、未解缺口與覆核理由")
        note.setMinimumHeight(100)
        form = QFormLayout()
        form.addRow("覆核者（自我聲明）", identity)
        form.addRow("Owner 角色", role)
        form.addRow("覆核理由與後續", note)
        layout.addLayout(form)
        pin = QLabel(_weekly_review_approval_text(row))
        pin.setWordWrap(True)
        pin.setTextInteractionFlags(pin.textInteractionFlags() | Qt.TextSelectableByMouse)
        layout.addWidget(pin)
        confirmed = QCheckBox("我已核對上述週期與 hash，並確認自己是本次覆核者。")
        layout.addWidget(confirmed)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("追加覆核紀錄")
        buttons.button(QDialogButtonBox.Ok).setEnabled(False)
        confirmed.toggled.connect(buttons.button(QDialogButtonBox.Ok).setEnabled)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.Accepted:
            return
        owner_name = identity.text().strip()
        owner_role = role.text().strip()
        review_note = note.toPlainText().strip()
        if not owner_name or not owner_role or not review_note:
            QMessageBox.warning(
                self,
                "覆核資訊未完成",
                "請填寫覆核者、Owner 角色與覆核理由。尚未保存任何內容。",
            )
            return

        self._save_owner_approval(row, owner_name, owner_role, review_note)

    def _save_owner_approval(self, row, owner_name: str, owner_role: str, review_note: str) -> bool:
        if self._candidate_history_save_in_progress or self.approval_service is None:
            return False
        result = self.approval_service.approve_weekly_review(
            review_id=row.review_id,
            review_hash=row.review_hash,
            period_start=row.period_start,
            period_end=row.period_end,
            owner_name=owner_name,
            owner_role=owner_role,
            review_note=review_note,
        )
        if not result.saved:
            QMessageBox.warning(
                self,
                "Owner 覆核未保存",
                result.message or result.error_code or "未知錯誤。",
            )
            return False
        QMessageBox.information(
            self,
            "覆核紀錄已追加",
            "已保存此週報快照的 owner 覆核。這不代表正式排程、資料來源接受或 Gate／ML 通過。",
        )
        self.refresh_dashboard()
        return True

    def _render_details(self, row, result: EvidenceOperationsHistoryDashboardResult) -> None:
        self.detail_panel.setPlainText(
            "\n".join(
                [
                    f"週期: {row.period_start} 至 {row.period_end}",
                    f"覆盤狀態: {_state_text(row.review_status, EVIDENCE_REVIEW_STATUS_LABELS)}",
                    f"保存時間: {row.created_at or '未提供'}",
                    f"正式排程條件: {_state_text(row.scheduler_readiness, EVIDENCE_SCHEDULER_READINESS_LABELS)}",
                    f"正式排程允許: {'是' if row.production_scheduler_allowed else '否'}",
                    f"Decision Quality reviews: {row.decision_quality_reviews_count}",
                    f"Signal Decay observations: {row.signal_decay_observations_count}",
                    f"Manual lifecycle candidates: {row.manual_lifecycle_candidate_count}",
                    f"Warnings: {row.warnings_count}",
                    f"Record ID: {row.review_id}",
                    f"報告 SHA-256：{row.review_hash or '未知（歷史紀錄未提供）'}",
                    *(
                        ["候選人工處置（已綁定此週報 hash）：", *row.candidate_review_decision_summary]
                        if row.candidate_review_decision_summary
                        else []
                    ),
                    "限制: " + " ".join(result.limitations),
                ]
            )
        )

    def _make_card(self, title: str) -> QLabel:
        card = QLabel(f"{title}\n尚未載入")
        card.setProperty("title", title)
        card.setAlignment(Qt.AlignCenter)
        card.setMinimumHeight(58)
        card.setStyleSheet(
            f"background: {MIDNIGHT_ANALYST.surface_2}; color: {MIDNIGHT_ANALYST.text_primary}; "
            f"border: 1px solid {MIDNIGHT_ANALYST.border}; border-radius: 6px; padding: 6px;"
        )
        return card

    def _set_card(self, card: QLabel, title: str, value: int | str) -> None:
        card.setText(f"{title}\n{value}")

    def _set_all_cards(self, value: str) -> None:
        for card in self.cards.values():
            self._set_card(card, card.property("title"), value)

    def _release_worker(self, worker: TaskWorker) -> None:
        if worker in self._workers:
            self._workers.remove(worker)


def _state_text(raw: object, labels: dict[str, str]) -> str:
    token = str(raw or "").strip()
    if not token:
        return "未知（原始碼：未提供）"
    label = labels.get(token.lower())
    if label is None:
        return f"未識別狀態（原始碼：{token}）"
    return f"{label}（原始碼：{token}）"


def _weekly_review_approval_text(row) -> str:
    lines = [
        f"週期：{row.period_start} 至 {row.period_end}",
        f"週報 ID：{row.review_id}",
        f"SHA-256：{row.review_hash}",
    ]
    if row.candidate_review_decision_summary:
        lines.extend(
            ["", "候選人工處置（已綁定此週報 hash）：", *row.candidate_review_decision_summary]
        )
    lines.extend(
        [
            "",
            "這只記錄對週報快照的人工覆核，不會批准 production scheduler、接受資料來源或授予 Gate／ML 資格。",
        ]
    )
    return "\n".join(lines)


class ActionItemLifecycleDialog(QDialog):
    """Collect a self-declared action-item transition and its review note."""

    _NEXT_STATUSES = {
        "open": (("reviewed", "已覆盤"), ("dismissed", "不適用／結案"), ("follow_up", "列入後續")),
        "reviewed": (("follow_up", "列入後續"),),
        "dismissed": (("follow_up", "重新追蹤"),),
        "follow_up": (("reviewed", "已覆盤"), ("dismissed", "不適用／結案")),
    }

    def __init__(self, action_items: list[dict], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Action Item 人工處置")
        self.setMinimumWidth(560)
        self._items_by_id = {str(item["action_item_id"]): item for item in action_items}
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.action_combo = QComboBox()
        for item in action_items:
            label = (
                f"{item['description']}｜{item['lifecycle_status']}｜"
                f"{item['period_start']}–{item['period_end']}"
            )
            self.action_combo.addItem(label, str(item["action_item_id"]))
        self.status_combo = QComboBox()
        self.action_combo.currentIndexChanged.connect(self._refresh_status_choices)
        self.action_combo.currentIndexChanged.connect(self._refresh_action_details)
        self.action_detail = QTextEdit()
        self.action_detail.setReadOnly(True)
        self.action_detail.setMaximumHeight(135)
        self.actor_name_input = QLineEdit()
        self.actor_role_input = QLineEdit()
        self.note_input = QTextEdit()
        self.note_input.setPlaceholderText("記錄處置理由、剩餘資料缺口或下一步；必填。")
        form.addRow("Action Item", self.action_combo)
        form.addRow("來源與最近歷程", self.action_detail)
        form.addRow("新狀態", self.status_combo)
        form.addRow("處置者姓名（自我聲明）", self.actor_name_input)
        form.addRow("處置者角色（自我聲明）", self.actor_role_input)
        form.addRow("處置說明", self.note_input)
        layout.addLayout(form)
        layout.addWidget(
            QLabel("此處置只追加追蹤事件，不核准週報、不變更來源 DB，也不授予 Gate credit。")
        )
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept_if_complete)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._refresh_status_choices()
        self._refresh_action_details()

    def _refresh_status_choices(self) -> None:
        self.status_combo.clear()
        action_id = str(self.action_combo.currentData() or "")
        item = self._items_by_id.get(action_id)
        current_status = str(item.get("lifecycle_status") or "open") if item else "open"
        for status, label in self._NEXT_STATUSES.get(current_status, ()):
            self.status_combo.addItem(label, status)

    def _refresh_action_details(self) -> None:
        action_id = str(self.action_combo.currentData() or "")
        item = self._items_by_id.get(action_id)
        if item is None:
            self.action_detail.clear()
            return
        latest = item.get("latest_event")
        lines = [
            f"Action Item ID: {item['action_item_id']}",
            f"來源 Item ID: {item['item_id']}",
            f"週報 Review ID / hash: {item['review_id']} / {item['review_hash']}",
            f"期間: {item['period_start']} 至 {item['period_end']}",
            f"原始負責人: {item['owner'] or '未提供'}",
        ]
        if latest:
            lines.append("完整 append-only 處置歷程:")
            for event in item.get("lifecycle_history", []):
                lines.append(
                    f"{event['recorded_at']}｜{event['from_status']} → {event['to_status']}｜"
                    f"{event['actor_name']}（{event['actor_role']}）｜{event['note']}"
                )
        self.action_detail.setPlainText("\n".join(lines))

    def _accept_if_complete(self) -> None:
        if not self.actor_name_input.text().strip():
            QMessageBox.warning(self, "資料未完成", "請填寫處置者姓名。")
            return
        if not self.actor_role_input.text().strip():
            QMessageBox.warning(self, "資料未完成", "請填寫處置者角色。")
            return
        if not self.note_input.toPlainText().strip():
            QMessageBox.warning(self, "資料未完成", "請填寫處置說明。")
            return
        if self.status_combo.currentData() is None:
            QMessageBox.warning(self, "沒有可用狀態", "請先選擇允許的 Action Item 狀態。")
            return
        self.accept()

    def selection(self) -> dict[str, str]:
        return {
            "action_item_id": str(self.action_combo.currentData() or ""),
            "new_status": str(self.status_combo.currentData() or ""),
            "actor_name": self.actor_name_input.text().strip(),
            "actor_role": self.actor_role_input.text().strip(),
            "note": self.note_input.toPlainText().strip(),
        }


def _scope_message(result: EvidenceOperationsHistoryDashboardResult, page_index: int = 0) -> str:
    if not result.source_available:
        return "顯示範圍未知；卡片統計範圍未知。"
    count = len(result.rows)
    page_size = min(50, max(1, int(result.request.limit)))
    if count:
        first_index = page_index * page_size + 1
        last_index = first_index + count - 1
        page_range = f"第 {page_index + 1} 頁；本頁索引 {first_index}–{last_index}。"
    else:
        page_range = f"第 {page_index + 1} 頁；本頁索引 0。"
    if result.has_more_rows:
        return (
            f"{page_range}後面還有較舊週報；卡片僅統計本頁 {count} 筆。"
        )
    return f"{page_range}卡片統計本頁 {count} 筆。"


def _history_source_error_message(error: Exception) -> str:
    code = str(error).splitlines()[0]
    messages = {
        "weekly_review_custom_db_requires_legacy_compat": (
            "此個人資料路由不允許指定其他資料庫；請使用目前應用程式路由。"
        ),
        "weekly_review_working_copy_unavailable": "找不到該 working-copy 資料庫。",
        "weekly_review_working_copy_not_file": "所選來源不是可讀取的資料庫檔案。",
        "weekly_review_formal_db_forbidden": (
            "正式 twstock.db 不可作為 weekly-review working-copy 來源。"
        ),
    }
    return messages.get(code, "無法切換週報歷史來源；請確認檔案與資料路由。")
