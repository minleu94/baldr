from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QFont, QIntValidator
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app_module.decision_quality_dashboard_dtos import DecisionQualityDashboardRequest, DecisionQualityDashboardResult
from ui_qt.decision_quality_labels import label_with_raw_value
from ui_qt.models.decision_quality_table_model import DecisionQualityTableModel
from ui_qt.theme import MIDNIGHT_ANALYST
from ui_qt.widgets.date_filter_edit import OptionalDateFilterEdit, date_filter_value
from ui_qt.widgets.table_style import apply_financial_table_style
from ui_qt.workers.task_worker import TaskWorker


SEVERITY_ITEMS = (
    ("", ""),
    ("低", "low"),
    ("中", "medium"),
    ("高", "high"),
)
STATUS_ITEMS = (
    ("", ""),
    ("待處理", "open"),
    ("已覆盤", "reviewed"),
    ("已略過", "dismissed"),
)
CARD_TITLES = {
    "decision_quality_score": "決策品質 / 10000",
    "process_adherence_score": "流程遵循 / 10000",
    "evidence_usage_score": "證據使用 / 10000",
    "risk_discipline_score": "風險紀律 / 10000",
    "review_completeness_score": "覆盤完整度 / 10000",
    "open_items": "待處理",
    "reviewed_items": "已覆盤",
    "dismissed_items": "已略過",
    "warnings_count": "警告",
}


class DecisionQualityView(QWidget):
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
        self._current_result: DecisionQualityDashboardResult | None = None
        self.filter_panel: QWidget | None = None
        self._setup_ui()
        if auto_refresh:
            self.refresh_dashboard()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        body = QSplitter(Qt.Horizontal)
        root.addWidget(body, stretch=1)

        filter_box = QGroupBox("決策品質篩選")
        filter_layout = QFormLayout(filter_box)
        filter_layout.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.review_type_input = QLineEdit()
        self.start_date_input = OptionalDateFilterEdit()
        self.end_date_input = OptionalDateFilterEdit()
        self.symbol_input = QLineEdit()
        self.symbol_scope_hint = QLabel(
            "股票代號只篩下方項目列。上方卡片仍顯示所選覆盤範圍的最新整體分數，不是單股分數。"
        )
        self.symbol_scope_hint.setObjectName("decisionQualitySymbolScopeHint")
        self.symbol_scope_hint.setWordWrap(True)
        self.symbol_scope_hint.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_secondary};")
        self.portfolio_id_input = QLineEdit()
        self.item_type_input = QLineEdit()
        self.severity_combo = QComboBox()
        for label, value in SEVERITY_ITEMS:
            self.severity_combo.addItem(label, value)
        self.status_combo = QComboBox()
        for label, value in STATUS_ITEMS:
            self.status_combo.addItem(label, value)
        self.min_score_input = QLineEdit()
        self.min_score_input.setPlaceholderText("0-10000")
        self.min_score_input.setValidator(QIntValidator(0, 10000, self.min_score_input))
        self.min_score_scope_hint = QLabel(
            "以篩選後最新覆盤的整體決策品質分數作顯示門檻，不是逐項分數；未達時只清空項目列，分數卡保留原分數。"
        )
        self.min_score_scope_hint.setObjectName("decisionQualityMinScoreScopeHint")
        self.min_score_scope_hint.setWordWrap(True)
        self.min_score_scope_hint.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_secondary};")
        for label, widget in (
            ("覆盤類型", self.review_type_input),
            ("開始日期", self.start_date_input),
            ("結束日期", self.end_date_input),
            ("股票代號", self.symbol_input),
            ("Portfolio ID", self.portfolio_id_input),
            ("項目類型", self.item_type_input),
            ("嚴重度", self.severity_combo),
            ("狀態", self.status_combo),
            ("最低分數 (0–10000)", self.min_score_input),
        ):
            filter_layout.addRow(label, widget)
            if widget is self.symbol_input:
                filter_layout.addRow("", self.symbol_scope_hint)
            elif widget is self.min_score_input:
                filter_layout.addRow("", self.min_score_scope_hint)
        self.min_score_error_label = QLabel("")
        self.min_score_error_label.setWordWrap(True)
        self.min_score_error_label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.warning};")
        self.min_score_error_label.hide()
        filter_layout.addRow("", self.min_score_error_label)
        self.refresh_button = QPushButton("重新整理")
        self.refresh_button.setProperty("variant", "primary")
        self.refresh_button.setAccessibleName("重新整理決策品質")
        self.refresh_button.clicked.connect(self.refresh_dashboard)
        self.filter_scroll_area = QScrollArea()
        self.filter_scroll_area.setObjectName("decisionQualityFilterScrollArea")
        self.filter_scroll_area.setWidgetResizable(True)
        self.filter_scroll_area.setFrameShape(QScrollArea.NoFrame)
        self.filter_scroll_area.setWidget(filter_box)
        filter_panel = QWidget()
        filter_panel.setObjectName("decisionQualityFilterPanel")
        filter_panel_layout = QVBoxLayout(filter_panel)
        filter_panel_layout.setContentsMargins(0, 0, 0, 0)
        filter_panel_layout.setSpacing(8)
        filter_panel_layout.addWidget(self.filter_scroll_area, stretch=1)
        filter_panel_layout.addWidget(self.refresh_button, stretch=0)
        self.filter_panel = filter_panel
        self._update_filter_panel_height_limit()
        body.addWidget(filter_panel)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        cards = QGridLayout()
        self.cards = {
            "decision_quality_score": self._make_card(CARD_TITLES["decision_quality_score"]),
            "process_adherence_score": self._make_card(CARD_TITLES["process_adherence_score"]),
            "evidence_usage_score": self._make_card(CARD_TITLES["evidence_usage_score"]),
            "risk_discipline_score": self._make_card(CARD_TITLES["risk_discipline_score"]),
            "review_completeness_score": self._make_card(CARD_TITLES["review_completeness_score"]),
            "open_items": self._make_card(CARD_TITLES["open_items"]),
            "reviewed_items": self._make_card(CARD_TITLES["reviewed_items"]),
            "dismissed_items": self._make_card(CARD_TITLES["dismissed_items"]),
            "warnings_count": self._make_card(CARD_TITLES["warnings_count"]),
        }
        for index, widget in enumerate(self.cards.values()):
            cards.addWidget(widget, index // 5, index % 5)
        right_layout.addLayout(cards)

        self.empty_state_label = QLabel("")
        self.empty_state_label.setWordWrap(True)
        self.empty_state_label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.warning};")
        right_layout.addWidget(self.empty_state_label)

        self.table_model = DecisionQualityTableModel()
        self.summary_table = QTableView()
        self.summary_table.setModel(self.table_model)
        apply_financial_table_style(self.summary_table)
        self.summary_table.setSelectionBehavior(QTableView.SelectRows)
        self.summary_table.setFont(QFont("Consolas", 9))
        self.summary_table.clicked.connect(self._on_table_row_clicked)
        right_layout.addWidget(self.summary_table, stretch=3)

        self.detail_panel = QTextEdit()
        self.detail_panel.setReadOnly(True)
        self.detail_panel.setFont(QFont("Consolas", 9))
        right_layout.addWidget(self.detail_panel, stretch=1)
        body.addWidget(right)
        body.setSizes([260, 900])

    def event(self, event: QEvent) -> bool:
        result = super().event(event)
        if event.type() == QEvent.Type.ScreenChangeInternal:
            self._update_filter_panel_height_limit()
        return result

    def _update_filter_panel_height_limit(self) -> None:
        """依目前螢幕的邏輯可用高度限制左側控制，避免外層長頁撐開。"""

        if self.filter_panel is None:
            return
        screen = self.screen()
        available_height = screen.availableGeometry().height() if screen is not None else 0
        maximum_height = min(520, int(available_height * 0.62)) if available_height > 0 else 520
        self.filter_panel.setMaximumHeight(max(120, maximum_height))

    def refresh_dashboard(self) -> None:
        validation_error = _min_score_validation_error(self.min_score_input)
        if validation_error is not None:
            self._clear_dashboard_for_input_error(validation_error)
            return
        self.min_score_error_label.clear()
        self.min_score_error_label.hide()
        request = self._request_from_controls()
        self._active_request_id += 1
        request_id = self._active_request_id
        self.refresh_button.setEnabled(False)
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

    def _clear_dashboard_for_input_error(self, message: str) -> None:
        """避免篩選值無效時舊資料看起來仍是目前結果。"""

        self._active_request_id += 1
        self.refresh_button.setEnabled(True)
        self.min_score_error_label.setText(message)
        self.min_score_error_label.show()
        self._current_result = None
        for field_name, card in self.cards.items():
            self._set_card(card, card.property("title"), "尚未載入")
        self.table_model.set_rows(())
        self.empty_state_label.setText(message)
        self.detail_panel.setPlainText("")

    def _request_from_controls(self) -> DecisionQualityDashboardRequest:
        return DecisionQualityDashboardRequest(
            review_type=_text_or_none(self.review_type_input),
            start_date=date_filter_value(self.start_date_input),
            end_date=date_filter_value(self.end_date_input),
            symbol=_text_or_none(self.symbol_input),
            portfolio_id=_text_or_none(self.portfolio_id_input),
            item_type=_text_or_none(self.item_type_input),
            severity=_combo_or_none(self.severity_combo),
            status=_combo_or_none(self.status_combo),
            min_score=_int_or_none(self.min_score_input),
        )

    def _on_dashboard_loaded(self, result: DecisionQualityDashboardResult, request_id: int) -> None:
        if request_id != self._active_request_id:
            return
        self.refresh_button.setEnabled(True)
        self._current_result = result
        for field_name, card in self.cards.items():
            value = getattr(result.cards, field_name)
            if not result.source_available:
                display_value = "未知"
            elif field_name.endswith("_score") and result.review_count == 0:
                display_value = "未提供"
            else:
                display_value = str(value)
            self._set_card(card, card.property("title"), display_value)
        message = result.empty_state_message
        if result.diagnostics:
            message = "\n".join((message, "診斷: " + ", ".join(result.diagnostics))).strip()
        self.empty_state_label.setText(message)
        self.table_model.set_rows(result.rows)
        self.summary_table.resizeColumnsToContents()
        if result.rows:
            self._render_details(result.rows[0], result)
        else:
            self.detail_panel.setPlainText("\n".join(result.limitations))

    def _on_dashboard_error(self, message: str, request_id: int) -> None:
        if request_id != self._active_request_id:
            return
        self.refresh_button.setEnabled(True)
        for field_name, card in self.cards.items():
            self._set_card(card, card.property("title"), "未知")
        self.table_model.set_rows(())
        self.empty_state_label.setText(f"決策品質證據載入失敗：{message.splitlines()[0]}")
        self.detail_panel.setPlainText("")

    def _on_table_row_clicked(self, index) -> None:
        row = self.table_model.row_at(index.row())
        if row is not None and self._current_result is not None:
            self._render_details(row, self._current_result)

    def _render_details(self, row, result: DecisionQualityDashboardResult) -> None:
        self.detail_panel.setPlainText(
            "\n".join(
                [
                    f"項目類型: {label_with_raw_value('item_type', row.item_type)}",
                    f"股票 / 來源: {row.symbol or '全部'} / {row.source_type or '未知'}",
                    "嚴重度 / 狀態: "
                    f"{label_with_raw_value('severity', row.severity)} / "
                    f"{label_with_raw_value('status', row.status)}",
                    f"原因代碼: {', '.join(row.reason_codes) or '無'}",
                    f"相關落差 ID: {row.related_gap_id or '無'}",
                    f"相關衰退 ID: {row.related_decay_id or '無'}",
                    f"資料品質: {row.quality}",
                    f"警告: {', '.join(row.warnings) or '無'}",
                    f"覆盤問題: {row.suggested_review_question}",
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

    def _set_card(self, card: QLabel, title: str, value: str | int) -> None:
        card.setText(f"{title}\n{value}")

    def _release_worker(self, worker: TaskWorker) -> None:
        if worker in self._workers:
            self._workers.remove(worker)


def _text_or_none(widget: QLineEdit) -> str | None:
    text = widget.text().strip()
    return text or None


def _combo_or_none(widget: QComboBox) -> str | None:
    data = widget.currentData()
    text = str(data).strip() if data is not None else widget.currentText().strip()
    return text or None


def _int_or_none(widget: QLineEdit) -> int | None:
    text = widget.text().strip()
    return int(text) if text else None


def _min_score_validation_error(widget: QLineEdit) -> str | None:
    text = widget.text().strip()
    if not text:
        return None
    try:
        value = int(text)
    except ValueError:
        return "最低分數需為 0–10000 的整數，或留空。"
    if not 0 <= value <= 10000:
        return "最低分數需介於 0 至 10000，或留空。"
    return None
