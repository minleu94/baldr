from __future__ import annotations

from collections import Counter

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app_module.live_research_gap_dashboard_dtos import LiveResearchGapDashboardRequest, LiveResearchGapDashboardResult
from ui_qt.models.live_research_gap_table_model import LiveResearchGapTableModel
from ui_qt.theme import MIDNIGHT_ANALYST
from ui_qt.widgets.date_filter_edit import OptionalDateFilterEdit, date_filter_value
from ui_qt.widgets.table_style import apply_financial_table_style
from ui_qt.workers.task_worker import TaskWorker


PORTFOLIO_MODE_ITEMS = (
    ("", ""),
    ("模擬", "simulated"),
    ("未知", "unknown"),
    ("實際", "real"),
)
DATA_QUALITY_ITEMS = (
    ("", ""),
    ("已觀測", "observed"),
    ("降級", "degraded"),
    ("缺失", "missing"),
)
CARD_TITLES = {
    "positions_seen": "持倉筆數",
    "positions_linked": "已連結",
    "missing_source_trace": "缺來源追蹤",
    "missing_research_run": "缺研究 Run",
    "missing_evidence_event": "缺事件",
    "missing_evidence_outcome": "缺結果",
    "simulated_count": "模擬",
    "unknown_count": "未知",
    "large_gap_count": "大落差",
    "warnings_count": "警告",
}


class LiveResearchGapView(QWidget):
    def __init__(self, dashboard_service, *, auto_refresh: bool = True, async_refresh: bool = True, parent=None) -> None:
        super().__init__(parent)
        self.dashboard_service = dashboard_service
        self.async_refresh = async_refresh
        self._active_request_id = 0
        self._workers: list[TaskWorker] = []
        self._current_result: LiveResearchGapDashboardResult | None = None
        self._setup_ui()
        if auto_refresh:
            self.refresh_dashboard()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        body = QSplitter(Qt.Horizontal)
        root.addWidget(body, stretch=1)

        filter_box = QGroupBox("研究落差篩選")
        form = QFormLayout(filter_box)
        self.observation_date_input = OptionalDateFilterEdit()
        self.symbol_input = QLineEdit()
        self.portfolio_id_input = QLineEdit()
        self.source_type_input = QLineEdit()
        self.strategy_version_id_input = QLineEdit()
        self.portfolio_mode_combo = QComboBox()
        for label, value in PORTFOLIO_MODE_ITEMS:
            self.portfolio_mode_combo.addItem(label, value)
        self.attribution_category_input = QLineEdit()
        self.data_quality_combo = QComboBox()
        for label, value in DATA_QUALITY_ITEMS:
            self.data_quality_combo.addItem(label, value)
        for label, widget in (
            ("觀測日期", self.observation_date_input),
            ("股票代號", self.symbol_input),
            ("Portfolio ID", self.portfolio_id_input),
            ("來源類型", self.source_type_input),
            ("策略版本", self.strategy_version_id_input),
            ("持倉模式", self.portfolio_mode_combo),
            ("歸因類別", self.attribution_category_input),
            ("資料品質", self.data_quality_combo),
        ):
            form.addRow(label, widget)
        self.refresh_button = QPushButton("重新整理")
        self.refresh_button.setProperty("variant", "primary")
        self.refresh_button.clicked.connect(self.refresh_dashboard)
        form.addRow(self.refresh_button)
        body.addWidget(filter_box)

        right = QWidget()
        layout = QVBoxLayout(right)
        grid = QGridLayout()
        self.cards = {
            "positions_seen": self._make_card(CARD_TITLES["positions_seen"]),
            "positions_linked": self._make_card(CARD_TITLES["positions_linked"]),
            "missing_source_trace": self._make_card(CARD_TITLES["missing_source_trace"]),
            "missing_research_run": self._make_card(CARD_TITLES["missing_research_run"]),
            "missing_evidence_event": self._make_card(CARD_TITLES["missing_evidence_event"]),
            "missing_evidence_outcome": self._make_card(CARD_TITLES["missing_evidence_outcome"]),
            "simulated_count": self._make_card(CARD_TITLES["simulated_count"]),
            "unknown_count": self._make_card(CARD_TITLES["unknown_count"]),
            "large_gap_count": self._make_card(CARD_TITLES["large_gap_count"]),
            "warnings_count": self._make_card(CARD_TITLES["warnings_count"]),
        }
        for index, widget in enumerate(self.cards.values()):
            grid.addWidget(widget, index // 5, index % 5)
        layout.addLayout(grid)

        self.empty_state_label = QLabel("")
        self.empty_state_label.setWordWrap(True)
        self.empty_state_label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.warning};")
        layout.addWidget(self.empty_state_label)

        self.quality_summary_label = QLabel("資料品質分布尚未載入")
        self.quality_summary_label.setWordWrap(True)
        layout.addWidget(self.quality_summary_label)
        self.quality_bars: dict[str, QProgressBar] = {}
        self.quality_counts_labels: dict[str, QLabel] = {}
        self.quality_layout = QGridLayout()
        for index, (quality, title) in enumerate(
            (("observed", "已觀測"), ("degraded", "降級"), ("missing", "缺失"), ("__other__", "其他品質代碼"))
        ):
            row = index // 2
            column = (index % 2) * 3
            self.quality_layout.addWidget(QLabel(title), row, column)
            bar = QProgressBar()
            bar.setTextVisible(False)
            bar.setFixedHeight(14)
            color = {
                "observed": "#5B8DB8",
                "degraded": "#D39B35",
                "missing": "#7C8794",
                "__other__": "#7D6DA7",
            }[quality]
            bar.setStyleSheet(
                f"QProgressBar {{ border: 1px solid {MIDNIGHT_ANALYST.border}; border-radius: 3px; }}"
                f"QProgressBar::chunk {{ background-color: {color}; border-radius: 2px; }}"
            )
            self.quality_bars[quality] = bar
            self.quality_layout.addWidget(bar, row, column + 1)
            count_label = QLabel("—")
            self.quality_counts_labels[quality] = count_label
            self.quality_layout.addWidget(count_label, row, column + 2)
        self.quality_layout.setColumnStretch(1, 1)
        self.quality_layout.setColumnStretch(4, 1)
        layout.addLayout(self.quality_layout)

        self.warning_distribution_group = QGroupBox("警示文字頻次（未知）")
        self.warning_distribution_group.setObjectName("liveResearchGapWarningDistribution")
        self.warning_distribution_group.setCheckable(True)
        self.warning_distribution_group.setChecked(False)
        warning_group_layout = QVBoxLayout(self.warning_distribution_group)
        self.warning_summary_label = QLabel("警示頻次尚未載入。")
        self.warning_summary_label.setWordWrap(True)
        self.warning_summary_label.setTextFormat(Qt.TextFormat.PlainText)
        warning_group_layout.addWidget(self.warning_summary_label)
        self.warning_summary_label.hide()
        self.warning_rows_widget = QWidget()
        self.warning_rows_layout = QGridLayout(self.warning_rows_widget)
        self.warning_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.warning_rows_layout.setColumnStretch(1, 1)
        warning_group_layout.addWidget(self.warning_rows_widget)
        self.warning_rows_widget.hide()
        self.warning_distribution_group.toggled.connect(self._toggle_warning_distribution)
        self.warning_bar_rows: list[tuple[QLabel, QProgressBar | None, QLabel | None]] = []
        layout.addWidget(self.warning_distribution_group)

        self.trace_summary_label = QLabel("追溯 ID：尚未載入選列。")
        self.trace_summary_label.setObjectName("liveResearchGapSelectedTraceIds")
        self.trace_summary_label.setAccessibleName("所選資料缺口列的追溯 ID")
        self.trace_summary_label.setWordWrap(True)
        self.trace_summary_label.setTextFormat(Qt.TextFormat.PlainText)
        self.trace_summary_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.trace_summary_label)

        self.table_model = LiveResearchGapTableModel()
        self.summary_table = QTableView()
        self.summary_table.setModel(self.table_model)
        apply_financial_table_style(self.summary_table)
        self.summary_table.setSelectionBehavior(QTableView.SelectRows)
        self.summary_table.setFont(QFont("Consolas", 9))
        self.summary_table.clicked.connect(self._on_table_row_clicked)
        layout.addWidget(self.summary_table, stretch=3)

        self.detail_panel = QTextEdit()
        self.detail_panel.setReadOnly(True)
        self.detail_panel.setFont(QFont("Consolas", 9))
        self.detail_panel.setMinimumHeight(190)
        layout.addWidget(self.detail_panel, stretch=1)
        body.addWidget(right)
        body.setSizes([260, 900])

    def refresh_dashboard(self) -> None:
        request = self._request_from_controls()
        self._active_request_id += 1
        request_id = self._active_request_id
        self.refresh_button.setEnabled(False)
        self._current_result = None
        self.table_model.set_rows(())
        self._clear_quality_distribution("資料品質分布載入中…")
        self._clear_warning_distribution("警示頻次載入中…")
        self.trace_summary_label.setText("追溯 ID：載入中…")
        for field_name, card in self.cards.items():
            self._set_card(card, card.property("title"), "載入中")
        self.empty_state_label.setText("研究落差證據載入中…")
        self.detail_panel.setPlainText("研究落差明細載入中…")
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

    def _request_from_controls(self) -> LiveResearchGapDashboardRequest:
        return LiveResearchGapDashboardRequest(
            observation_date=date_filter_value(self.observation_date_input),
            symbol=_text_or_none(self.symbol_input),
            portfolio_id=_text_or_none(self.portfolio_id_input),
            source_type=_text_or_none(self.source_type_input),
            strategy_version_id=_text_or_none(self.strategy_version_id_input),
            portfolio_mode=_combo_or_none(self.portfolio_mode_combo),
            attribution_category=_text_or_none(self.attribution_category_input),
            data_quality=_combo_or_none(self.data_quality_combo),
        )

    def _on_dashboard_loaded(self, result: LiveResearchGapDashboardResult, request_id: int) -> None:
        if request_id != self._active_request_id:
            return
        self.refresh_button.setEnabled(True)
        self._current_result = result
        for field_name, card in self.cards.items():
            value = "未知" if result.diagnostics else getattr(result.cards, field_name)
            self._set_card(card, card.property("title"), value)
        self._render_quality_distribution(result)
        self._render_warning_distribution(result)
        self.empty_state_label.setText(result.empty_state_message)
        self.table_model.set_rows(result.rows)
        self.summary_table.resizeColumnsToContents()
        if result.rows:
            self._render_details(result.rows[0], result)
        else:
            self.trace_summary_label.setText("追溯 ID：目前沒有可選列。")
            self.detail_panel.setPlainText("\n".join(result.limitations))

    def _on_dashboard_error(self, message: str, request_id: int) -> None:
        if request_id != self._active_request_id:
            return
        self.refresh_button.setEnabled(True)
        self._current_result = None
        self.table_model.set_rows(())
        for card in self.cards.values():
            self._set_card(card, card.property("title"), "未知")
        self._clear_quality_distribution("資料品質分布未知；證據來源載入失敗。")
        self._clear_warning_distribution("警示頻次未知；證據來源載入失敗。")
        self.trace_summary_label.setText("追溯 ID：來源載入失敗，狀態未知。")
        self.empty_state_label.setText(f"研究落差證據載入失敗：{message.splitlines()[0]}")
        self.detail_panel.setPlainText("")

    def _on_table_row_clicked(self, index) -> None:
        row = self.table_model.row_at(index.row())
        if row is not None and self._current_result is not None:
            self._render_details(row, self._current_result)

    def _render_details(self, row, result: LiveResearchGapDashboardResult) -> None:
        self.trace_summary_label.setText(
            "所選列追溯 ID｜Research Run: "
            f"{row.research_run_id or '未提供'}｜Evidence Event: "
            f"{row.evidence_event_id or '未提供'}｜Evidence Outcome: "
            f"{row.evidence_outcome_id or '未提供'}"
        )
        self.trace_summary_label.setToolTip(
            self.trace_summary_label.text()
            + "\n僅依所選列的保存值顯示，不表示匹配或來源資格。"
        )
        self.detail_panel.setPlainText(
            "\n".join(
                [
                    f"股票 / 模式: {row.symbol} / {row.portfolio_mode}",
                    f"來源: {row.source_type or '缺失'} / {row.source_id or '缺失'}",
                    f"策略版本: {row.strategy_version_id or '無'}",
                    f"連結信心: {row.match_confidence}",
                    "追溯識別碼（依本列保存值；不表示匹配或來源資格）:",
                    f"Research Run ID: {row.research_run_id or '未提供'}",
                    f"Evidence Event ID: {row.evidence_event_id or '未提供'}",
                    f"Evidence Outcome ID: {row.evidence_outcome_id or '未提供'}",
                    f"歸因: {', '.join(row.attribution_categories) or '無'}",
                    f"資料品質: {row.quality}",
                    f"警告: {', '.join(row.warnings) or '無'}",
                    "限制: " + " ".join(result.limitations),
                ]
            )
        )

    def _render_quality_distribution(self, result: LiveResearchGapDashboardResult) -> None:
        counts = result.quality_counts
        total = len(result.rows)
        if result.diagnostics:
            self._clear_quality_distribution("資料品質分布未知；來源回報診斷，不能視為空集合。")
            return
        if not isinstance(counts, dict) or (total > 0 and not counts):
            self._clear_quality_distribution("資料品質分布未知；服務未提供完整品質計數。")
            return
        if result.cards.positions_seen != total or any(
            not isinstance(code, str)
            or not code.strip()
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
            for code, count in counts.items()
        ) or sum(counts.values()) != total:
            self._clear_quality_distribution("資料品質分布未知；品質計數與已載入列數不一致。")
            return

        known = ("observed", "degraded", "missing")
        other_codes = sorted(code for code in counts if code not in known)
        displayed = {code: counts.get(code, 0) for code in known}
        displayed["__other__"] = sum(counts[code] for code in other_codes)
        for code, count in displayed.items():
            bar = self.quality_bars[code]
            bar.setRange(0, max(1, total))
            bar.setValue(count)
            self.quality_counts_labels[code].setText(str(count))
        if total == 0:
            self.quality_summary_label.setText(
                "已載入 0 筆；目前沒有可呈現的品質分布。品質狀態不代表來源資格。"
            )
        else:
            details = "；".join(f"{code} {counts[code]}" for code in other_codes)
            suffix = f"；其他代碼：{details}" if details else ""
            self.quality_summary_label.setText(
                f"資料品質分布（服務回報計數；已載入 {total} 筆）{suffix}；"
                "僅描述資料狀態，不代表投資績效或來源資格。"
            )
        self.quality_summary_label.setToolTip(
            "品質分類只描述本次載入觀測的資料狀態，不代表投資績效或來源已取得資格。"
            + ("其他代碼：" + ", ".join(f"{code}={counts[code]}" for code in other_codes) if other_codes else "")
        )

    def _clear_quality_distribution(self, message: str) -> None:
        self.quality_summary_label.setText(message)
        self.quality_summary_label.setToolTip(
            "品質分類只描述本次載入觀測的資料狀態，不代表投資績效或來源已取得資格。"
        )
        for bar in self.quality_bars.values():
            bar.setRange(0, 1)
            bar.setValue(0)
        for label in self.quality_counts_labels.values():
            label.setText("—")

    def _render_warning_distribution(self, result: LiveResearchGapDashboardResult) -> None:
        counts = result.warning_counts
        rows = result.rows
        card_count = result.cards.warnings_count
        positions_seen = result.cards.positions_seen
        valid_counts = (
            isinstance(counts, dict)
            and all(
                isinstance(text, str)
                and bool(text.strip())
                and not isinstance(count, bool)
                and isinstance(count, int)
                and count >= 0
                for text, count in counts.items()
            )
        )
        if result.diagnostics:
            self._clear_warning_distribution("警示頻次未知；來源回報診斷，不能視為空集合。")
            return
        if (
            not valid_counts
            or not isinstance(rows, (tuple, list))
            or isinstance(card_count, bool)
            or not isinstance(card_count, int)
            or card_count < 0
            or isinstance(positions_seen, bool)
            or not isinstance(positions_seen, int)
            or positions_seen != len(rows)
        ):
            self._clear_warning_distribution("警示頻次未知；警示計數與本次載入列不一致。")
            return

        row_warnings = [getattr(row, "warnings", None) for row in rows]
        if any(
            not isinstance(warnings, (tuple, list))
            or any(not isinstance(warning, str) or not warning.strip() for warning in warnings)
            for warnings in row_warnings
        ):
            self._clear_warning_distribution("警示頻次未知；列內警示文字格式不完整。")
            return
        occurrence_count = sum(len(warnings) for warnings in row_warnings)
        row_counts = Counter(warning for warnings in row_warnings for warning in warnings)
        if (
            occurrence_count != card_count
            or sum(counts.values()) != card_count
            or dict(row_counts) != counts
        ):
            self._clear_warning_distribution("警示頻次未知；警示計數與本次載入列不一致。")
            return

        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        displayed = ordered[:5]
        overflow = ordered[5:]
        self._clear_warning_rows()
        for index, (warning, count) in enumerate(displayed):
            warning_label = QLabel()
            warning_label.setTextFormat(Qt.TextFormat.PlainText)
            warning_label.setText(warning)
            warning_label.setWordWrap(True)
            bar = QProgressBar()
            bar.setTextVisible(False)
            bar.setFixedHeight(12)
            bar.setRange(0, max(1, card_count))
            bar.setValue(count)
            count_label = QLabel(str(count))
            count_label.setToolTip("警示文字出現次數")
            self.warning_rows_layout.addWidget(warning_label, index, 0)
            self.warning_rows_layout.addWidget(bar, index, 1)
            self.warning_rows_layout.addWidget(count_label, index, 2)
            self.warning_bar_rows.append((warning_label, bar, count_label))
        if overflow:
            overflow_occurrences = sum(count for _, count in overflow)
            overflow_label = QLabel(
                f"其餘 {len(overflow)} 種警示文字：{overflow_occurrences} 次（完整內容見下方列明細）"
            )
            overflow_label.setWordWrap(True)
            overflow_label.setTextFormat(Qt.TextFormat.PlainText)
            overflow_label.setToolTip("")
            self.warning_rows_layout.addWidget(overflow_label, len(displayed), 0, 1, 3)
            self.warning_bar_rows.append((overflow_label, None, None))
        if card_count == 0:
            summary = "警示文字出現 0 次；已載入列目前沒有警示。"
        else:
            summary = (
                f"警示文字頻次：{card_count} 次出現、{len(counts)} 種文字；"
                "分母為本次警示出現總次數，同一列可包含多則警示。"
            )
        self.warning_summary_label.setText(summary)
        self.warning_summary_label.setToolTip(
            "依本次篩選讀取的列與服務警示計數核對；此處統計警示文字出現次數，"
            "不是有警示的列數，同一列可能包含多則警示。"
        )
        self.warning_distribution_group.setTitle(
            f"警示文字頻次（{card_count} 次／{len(counts)} 種）"
        )

    def _clear_warning_distribution(self, message: str) -> None:
        self._clear_warning_rows()
        self.warning_summary_label.setText(message)
        self.warning_summary_label.setToolTip(
            "警示文字頻次未知時不沿用前次結果；同一列可能包含多則警示。"
        )
        self.warning_distribution_group.setTitle("警示文字頻次（未知）")

    def _clear_warning_rows(self) -> None:
        while self.warning_rows_layout.count():
            item = self.warning_rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self.warning_bar_rows.clear()

    def _toggle_warning_distribution(self, checked: bool) -> None:
        self.warning_summary_label.setVisible(checked)
        self.warning_rows_widget.setVisible(checked)

    def _make_card(self, title: str) -> QLabel:
        card = QLabel(f"{title}\n0")
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
