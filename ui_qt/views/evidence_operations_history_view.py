from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QResizeEvent
from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton, QTableView, QTextEdit, QVBoxLayout, QWidget

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
        auto_refresh: bool = True,
        async_refresh: bool = True,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.dashboard_service = dashboard_service
        self.async_refresh = async_refresh
        self._active_request_id = 0
        self._workers: list[TaskWorker] = []
        self._current_result: EvidenceOperationsHistoryDashboardResult | None = None
        self._cursor_stack = [None]
        self._page_index = 0
        self._loading = False
        self._filters_dirty = False
        self._active_filter = (None, None)
        self._card_columns = 0
        self._setup_ui()
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
        root.addLayout(filter_row)

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
            self._loading
            or self._filters_dirty
            or self._current_result is None
            or self._current_result.next_cursor is None
        ):
            return
        self._cursor_stack.append(self._current_result.next_cursor)
        self._page_index += 1
        self._request_dashboard(self._current_page_request())

    def previous_page(self) -> None:
        if self._loading or self._filters_dirty or self._page_index <= 0:
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
        self._active_request_id += 1
        request_id = self._active_request_id
        self._loading = True
        self._current_result = None
        self.refresh_button.setEnabled(False)
        self.previous_button.setEnabled(False)
        self.next_button.setEnabled(False)
        self._set_all_cards("載入中")
        self.table_model.set_rows(())
        self.empty_state_label.setText("")
        self.scope_label.setText("")
        self.detail_panel.setPlainText("")
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
        self.refresh_button.setEnabled(True)
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
        else:
            self.detail_panel.setPlainText("\n".join(result.limitations))

    def _on_dashboard_error(self, message: str, request_id: int) -> None:
        if request_id != self._active_request_id:
            return
        self._loading = False
        self.refresh_button.setEnabled(True)
        self._current_result = None
        self._set_all_cards("未知")
        self.table_model.set_rows(())
        self.empty_state_label.setText(f"Evidence operations history 載入失敗：{message.splitlines()[0]}")
        self.scope_label.setText("")
        self.detail_panel.setPlainText("")
        self._update_pagination_buttons(None)

    def _update_pagination_buttons(self, result: EvidenceOperationsHistoryDashboardResult | None) -> None:
        self.previous_button.setEnabled(
            not self._loading and not self._filters_dirty and self._page_index > 0
        )
        self.next_button.setEnabled(
            not self._loading
            and not self._filters_dirty
            and result is not None
            and result.next_cursor is not None
        )

    def _on_filter_changed(self, _date) -> None:
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
            self._render_details(row, self._current_result)

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
