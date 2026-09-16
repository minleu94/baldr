"""個股研究中的 Decision → Outcome Journey 視圖。

資料區只消費 ``DecisionOutcomeJourney`` read model；下方研究動作控制項
只寫既有 Journal append-only history，不建立交易、不採用 Advice，也不以
同股同日猜測 ``result_id``。所有背景讀取都透過 ``TaskWorker``，以 request
generation + stock code + result id 丟棄過期回傳，避免切股後舊結果污染畫面。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Any, Protocol

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app_module.decision_outcome_journey import (
    DecisionOutcomeJourney,
    EvidenceEventRecord,
    JourneyLinkStatus,
    JourneyStatus,
    JournalEntryRecord,
    OutcomeMaturityRecord,
    PortfolioLedgerRecord,
    PortfolioTradeRecord,
    project_outcome_maturity,
)
from app_module.decision_continuity_controller import DecisionContinuityController
from app_module.dtos.decision_continuity_dtos import IDENTITY_STATUS_UNKNOWN
from app_module.research_session import ResearchStockContextDTO
from ui_qt.theme import MIDNIGHT_ANALYST
from ui_qt.widgets.decision_continuity_controls import (
    DecisionContinuityControlsWidget,
)
from ui_qt.widgets.table_style import apply_financial_table_style
from ui_qt.widgets.theme_widgets import StatusBadge
from ui_qt.workers.task_worker import TaskWorker


class DecisionOutcomeJourneyReadPort(Protocol):
    """DecisionOutcomeJourneyService 的最小唯讀 UI port。"""

    def build(
        self,
        result_id: str,
        *,
        query_boundary: str | None = None,
    ) -> DecisionOutcomeJourney: ...


class JourneyTableModel(QAbstractTableModel):
    """有限、唯讀的 journey table model；完整 cell 文字保留在 tooltip。"""

    def __init__(
        self,
        columns: Sequence[str],
        rows: Sequence[Sequence[str]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._columns = tuple(str(column) for column in columns)
        self._rows = tuple(tuple(str(cell) for cell in row) for row in rows)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._columns)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or index.row() >= len(self._rows):
            return None
        row = self._rows[index.row()]
        if index.column() >= len(row):
            return None
        value = row[index.column()]
        if role in (Qt.DisplayRole, Qt.ToolTipRole):
            return value
        if role == Qt.TextAlignmentRole:
            return Qt.AlignLeft | Qt.AlignVCenter
        return None

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.DisplayRole,
    ) -> Any:
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal and section < len(self._columns):
            return self._columns[section]
        if orientation == Qt.Vertical:
            return str(section + 1)
        return None


class DecisionOutcomeJourneyWidget(QWidget):
    """以精確 candidate key 顯示決策後續 evidence／outcome／個人紀錄。"""

    journeyLoaded = Signal(object)
    journeyFailed = Signal(str)
    readyToClose = Signal()

    def __init__(
        self,
        journey_service: DecisionOutcomeJourneyReadPort,
        context: ResearchStockContextDTO | None = None,
        *,
        continuity_controller: DecisionContinuityController | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.journey_service = journey_service
        self.continuity_controller = continuity_controller
        self.context = context
        self.journey: DecisionOutcomeJourney | None = None
        self._request_id = 0
        self._active_code = ""
        self._active_result_id = ""
        self._active_worker: TaskWorker | None = None
        self._workers: set[TaskWorker] = set()
        self._closing = False
        self._empty_labels: dict[str, QLabel] = {}
        self._tables: dict[str, QTableView] = {}
        self._table_columns: dict[str, tuple[str, ...]] = {}
        self._setup_ui()
        if context is not None:
            self.set_context(context)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return QSize(320, 0)

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        heading = QFrame()
        heading.setObjectName("decisionOutcomeJourneyHeading")
        heading.setStyleSheet(
            f"#decisionOutcomeJourneyHeading {{ background: {MIDNIGHT_ANALYST.surface_2}; "
            f"border: 1px solid {MIDNIGHT_ANALYST.border}; "
            f"border-left: 4px solid {MIDNIGHT_ANALYST.accent}; "
            f"border-radius: {MIDNIGHT_ANALYST.radius_panel}px; }}"
        )
        heading_layout = QVBoxLayout(heading)
        heading_layout.setContentsMargins(12, 10, 12, 10)
        heading_layout.setSpacing(6)

        title_row = QHBoxLayout()
        self.title_label = QLabel("決策與後續結果")
        self.title_label.setObjectName("decisionOutcomeJourneyTitle")
        self.title_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_primary}; font-size: 14pt; font-weight: 700;"
        )
        self.title_label.setWordWrap(True)
        title_row.addWidget(self.title_label, 1)
        self.reload_button = QPushButton("重新讀取")
        self.reload_button.setObjectName("decisionOutcomeJourneyReload")
        self.reload_button.setProperty("variant", "secondary")
        self.reload_button.setAccessibleName("重新讀取決策結果旅程")
        self.reload_button.clicked.connect(self._reload)
        title_row.addWidget(self.reload_button)
        heading_layout.addLayout(title_row)

        self.identity_label = QLabel("尚未連結推薦結果")
        self.identity_label.setObjectName("decisionOutcomeJourneyIdentity")
        self.identity_label.setWordWrap(True)
        self.identity_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.identity_label.setAccessibleName("決策結果旅程識別")
        heading_layout.addWidget(self.identity_label)

        status_row = QHBoxLayout()
        self.status_badge = StatusBadge("未連結", "warning")
        self.status_badge.setObjectName("decisionOutcomeJourneyStatusBadge")
        self.status_badge.setAccessibleName("決策結果旅程狀態")
        status_row.addWidget(self.status_badge)
        self.status_label = QLabel("需要帶有推薦結果的研究上下文。")
        self.status_label.setObjectName("decisionOutcomeJourneyStatusLabel")
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        status_row.addWidget(self.status_label, 1)
        heading_layout.addLayout(status_row)

        self.context_label = QLabel("來源：未標示｜決策日：未知｜資料日：未知")
        self.context_label.setObjectName("decisionOutcomeJourneyContext")
        self.context_label.setWordWrap(True)
        self.context_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.context_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary}; font-size: 10pt;"
        )
        heading_layout.addWidget(self.context_label)
        root.addWidget(heading)

        self.safety_label = QLabel(
            "研究資料唯讀；下方動作只保存目前 candidate 的研究狀態／筆記／"
            "下次檢視，與前瞻報酬及個人持倉事件分開；"
            "不代表實際成交損益或自動交易指令。"
        )
        self.safety_label.setObjectName("decisionOutcomeJourneySafety")
        self.safety_label.setWordWrap(True)
        self.safety_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.safety_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary}; background: {MIDNIGHT_ANALYST.surface_1}; "
            f"border: 1px solid {MIDNIGHT_ANALYST.border}; padding: 8px;"
        )
        root.addWidget(self.safety_label)

        self.continuity_controls: DecisionContinuityControlsWidget | None = None
        if self.continuity_controller is not None:
            self.continuity_controls = DecisionContinuityControlsWidget(
                self.continuity_controller,
                parent=self,
            )
            root.addWidget(self.continuity_controls)

        scroll = QScrollArea()
        scroll.setObjectName("decisionOutcomeJourneyScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setAccessibleName("決策結果旅程內容")
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)

        maturity_group = QGroupBox("後續結果（5／10／20／60 個交易日）")
        maturity_layout = QVBoxLayout(maturity_group)
        maturity_layout.addWidget(
            self._wrapped_label(
                "每個期限會分開呈現連結狀態與結果狀態；"
                "連結成功不等於結果已成熟。"
            )
        )
        self.maturity_table = self._make_table(
            "maturity",
            (
                "期限",
                "連結狀態",
                "結果狀態",
                "說明",
            ),
            220,
        )
        maturity_layout.addWidget(self.maturity_table)
        maturity_layout.addWidget(self._empty_labels["maturity"])
        content_layout.addWidget(maturity_group)

        self.details_toggle = QPushButton("顯示技術詳情")
        self.details_toggle.setObjectName("decisionOutcomeJourneyDetailsToggle")
        self.details_toggle.setProperty("variant", "secondary")
        self.details_toggle.setAccessibleName("展開或收合決策結果技術詳情")
        self.details_toggle.clicked.connect(self._toggle_details)
        content_layout.addWidget(self.details_toggle, 0, Qt.AlignLeft)

        self.technical_details = QWidget()
        self.technical_details.setObjectName("decisionOutcomeJourneyTechnicalDetails")
        technical_layout = QVBoxLayout(self.technical_details)
        technical_layout.setContentsMargins(0, 0, 0, 0)
        technical_layout.setSpacing(10)
        self.technical_identity_label = self._wrapped_label(
            "尚未載入 technical identity 詳情。"
        )
        self.technical_identity_label.setObjectName("decisionOutcomeJourneyTechnicalIdentity")
        self.technical_identity_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary}; background: {MIDNIGHT_ANALYST.surface_1}; "
            f"border: 1px solid {MIDNIGHT_ANALYST.border}; padding: 8px;"
        )
        technical_layout.addWidget(self.technical_identity_label)

        evidence_group = QGroupBox("證據事件（同一候選）")
        evidence_layout = QVBoxLayout(evidence_group)
        self.evidence_table = self._make_table(
            "evidence",
            (
                "事件日",
                "Event ID",
                "事件類型",
                "來源",
                "Identity link",
                "可得時間",
                "後續結果",
            ),
            300,
        )
        evidence_layout.addWidget(self.evidence_table)
        evidence_layout.addWidget(self._empty_labels["evidence"])
        technical_layout.addWidget(evidence_group)

        journal_group = QGroupBox("既有筆記與 thesis")
        journal_layout = QVBoxLayout(journal_group)
        self.journal_table = self._make_table(
            "journal",
            (
                "Journal ID",
                "範圍",
                "Linked type",
                "Linked ID",
                "Thesis",
                "Revision／reversal",
                "Link status",
                "建立時間",
            ),
            260,
        )
        journal_layout.addWidget(self.journal_table)
        journal_layout.addWidget(self._empty_labels["journal"])
        technical_layout.addWidget(journal_group)

        portfolio_group = QGroupBox("個人持倉事件（與研究結果分開）")
        portfolio_layout = QVBoxLayout(portfolio_group)
        self.portfolio_table = self._make_table(
            "portfolio",
            (
                "Record ID",
                "Namespace",
                "Event",
                "股票",
                "方向／數量",
                "價格",
                "執行語義",
                "Link status",
            ),
            300,
        )
        portfolio_layout.addWidget(self.portfolio_table)
        portfolio_layout.addWidget(self._empty_labels["portfolio"])
        technical_layout.addWidget(portfolio_group)

        content_layout.addWidget(self.technical_details)
        self.technical_details.setVisible(False)

        content_layout.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        self._set_table_rows("maturity", (), "尚未載入；需要 exact result_id 與 candidate_key。")
        self._set_table_rows("evidence", (), "尚未載入；不以同股同日猜測 Evidence event。")
        self._set_table_rows("journal", (), "尚未載入；缺少 Journal 不阻擋推薦追蹤。")
        self._set_table_rows(
            "portfolio",
            (),
            "尚未載入；缺少 Portfolio event 不建立交易紀錄。",
        )
        self._set_navigation_state()

    def _make_table(
        self,
        table_id: str,
        columns: Sequence[str],
        maximum_height: int,
    ) -> QTableView:
        table = QTableView()
        table.setObjectName(f"decisionOutcomeJourney{table_id.title()}Table")
        self._table_columns[table_id] = tuple(str(column) for column in columns)
        table.setAccessibleName(f"決策結果旅程{table_id}表")
        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        table.setMaximumHeight(maximum_height)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setFocusPolicy(Qt.StrongFocus)
        table.setTabKeyNavigation(True)
        table.verticalHeader().setDefaultSectionSize(28)
        table.verticalHeader().setMinimumSectionSize(28)
        table.setWordWrap(True)
        table.setAlternatingRowColors(True)
        table.setAccessibleDescription(
            "唯讀資料表；可用鍵盤選取，完整欄位文字可由 tooltip 讀取。"
        )
        apply_financial_table_style(table)
        self._tables[table_id] = table
        empty = self._wrapped_label("")
        empty.setObjectName(f"decisionOutcomeJourney{table_id.title()}Empty")
        empty.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary}; background: {MIDNIGHT_ANALYST.surface_2}; "
            f"border: 1px solid {MIDNIGHT_ANALYST.border}; padding: 8px;"
        )
        self._empty_labels[table_id] = empty
        return table

    def set_context(self, context: ResearchStockContextDTO | None) -> None:
        """切換研究上下文；缺 result_id 時不呼叫 service。"""

        self.context = context
        self.journey = None
        self._request_id += 1
        self._cancel_active_worker()
        if self.continuity_controls is not None:
            self.continuity_controls.set_context(context)
        if context is None or not context.stock_code.strip():
            self._active_code = ""
            self._active_result_id = ""
            self._render_context(context)
            self._set_unlinked("尚未選取股票；需要明示 result_id 才能開啟 journey。")
            return

        self._active_code = context.stock_code.strip()
        self._active_result_id = context.result_id.strip()
        self._render_context(context)
        if context.identity_status == "conflict":
            self._set_unlinked(
                f"{self._active_code} 未連結：研究來源 identity 衝突；"
                "不會把此 context 連到任何 Journal／Evidence。",
                quality="conflict",
            )
            return
        if not self._active_result_id:
            self._set_unlinked(
                f"{self._active_code} 未連結：研究上下文缺少 result_id；"
                "不以同股同日猜測推薦來源。"
            )
            return
        self._start_load(self._request_id, self._active_code, self._active_result_id)

    def _render_context(self, context: ResearchStockContextDTO | None) -> None:
        if context is None:
            self.identity_label.setText("尚未連結推薦結果")
            self.context_label.setText("來源：未標示｜決策日：未知｜資料日：未知")
            self.technical_identity_label.setText("尚未載入 technical identity 詳情。")
            return
        name = f" {context.stock_name}" if context.stock_name else ""
        self.identity_label.setText(f"{context.stock_code}{name}")
        source = context.source_label or context.source_id or "未標示"
        self.context_label.setText(
            f"來源：{source}｜工作區：{context.source_workspace or '未標示'}｜"
            f"決策日：{context.decision_date or '未知'}｜資料日：{context.data_date or '未知'}｜"
            f"來源 snapshot：{context.source_snapshot_id or context.source_snapshot_hash or '未知'}｜"
            "期限：5／10／20／60 個交易日"
        )
        self.technical_identity_label.setText(
            f"result_id：{context.result_id or '未知'}\n"
            f"candidate_key：{context.result_id or '未知'}:{context.stock_code}\n"
            f"source_snapshot_id：{context.source_snapshot_id or '未知'}｜"
            f"source_snapshot_hash：{context.source_snapshot_hash or '未知'}\n"
            f"identity_status：{context.identity_status or 'implicit'}\n"
            "完整來源 identity 會在載入後顯示。"
        )

    def _start_load(self, request_id: int, code: str, result_id: str) -> None:
        self._set_loading_state(code, result_id)

        def task(cancel_callback=None) -> DecisionOutcomeJourney:
            del cancel_callback
            return self.journey_service.build(result_id)

        worker = TaskWorker(task)
        self._workers.add(worker)
        self._active_worker = worker
        worker.started.connect(
            lambda rid=request_id, requested_code=code, requested_result=result_id:
            self._on_started(rid, requested_code, requested_result)
        )
        worker.finished.connect(
            lambda journey, rid=request_id, requested_code=code, requested_result=result_id:
            self._on_loaded(rid, requested_code, requested_result, journey)
        )
        worker.error.connect(
            lambda error, rid=request_id, requested_code=code, requested_result=result_id:
            self._on_error(rid, requested_code, requested_result, error)
        )
        worker.cancelled.connect(
            lambda rid=request_id, requested_code=code, requested_result=result_id:
            self._on_cancelled(rid, requested_code, requested_result)
        )
        worker.native_thread_finished.connect(
            lambda current=worker: self._worker_finished(current)
        )
        worker.start()

    def _reload(self) -> None:
        context = self.context
        if context is None or not context.stock_code.strip() or not context.result_id.strip():
            self.set_context(context)
            return
        self.set_context(context)

    def _cancel_active_worker(self) -> None:
        worker = self._active_worker
        if worker is not None and worker.isRunning():
            worker.cancel(cooperative=True, wait=False)

    def request_close(self) -> bool:
        """合作式取消所有 journey worker；不在 UI thread 同步等待。"""

        self._closing = True
        self._request_id += 1
        active_workers = [item for item in self._workers if item.isRunning()]
        if self._active_worker is not None and self._active_worker.isRunning():
            if self._active_worker not in active_workers:
                active_workers.append(self._active_worker)
        for worker in active_workers:
            worker.cancel(cooperative=True, wait=False)
        if active_workers:
            self._set_status("正在安全取消 Journey 讀取…", "warning")
            return False
        return True

    def is_busy(self) -> bool:
        return any(worker.isRunning() for worker in self._workers)

    def closeEvent(self, event: Any) -> None:  # noqa: N802 - Qt override
        if not self.request_close():
            event.ignore()
            return
        super().closeEvent(event)

    def _worker_finished(self, worker: TaskWorker) -> None:
        self._workers.discard(worker)
        if self._active_worker is worker:
            self._active_worker = None
        worker.deleteLater()
        if self._closing and not self.is_busy():
            self.readyToClose.emit()

    def _on_started(self, request_id: int, code: str, result_id: str) -> None:
        if self._is_current(request_id, code, result_id):
            self._set_status("背景讀取決策結果旅程中…", "info")

    def _on_loaded(
        self,
        request_id: int,
        code: str,
        result_id: str,
        journey: object,
    ) -> None:
        if not self._is_current(request_id, code, result_id):
            return
        if not isinstance(journey, DecisionOutcomeJourney):
            self._on_error(request_id, code, result_id, "service returned an invalid journey DTO")
            return
        if journey.recommendation_result.result_id != result_id:
            self._on_error(
                request_id,
                code,
                result_id,
                "journey result_id 與 request 不一致；已拒絕顯示",
            )
            return
        self.journey = journey
        self._render_journey(journey, code, result_id)
        self.journeyLoaded.emit(journey)

    def _on_error(
        self,
        request_id: int,
        code: str,
        result_id: str,
        error: object,
    ) -> None:
        if not self._is_current(request_id, code, result_id):
            return
        message = str(error).splitlines()[0].strip() or "未知讀取錯誤"
        self._restore_identity_label(code)
        self._set_status(f"決策與後續結果讀取失敗：{message}", "error")
        self._set_table_rows("maturity", (), "讀取失敗；可按「重新讀取」重試。")
        self._set_table_rows("evidence", (), "Journey 讀取失敗；尚未顯示 Evidence。")
        self._set_table_rows("journal", (), "Journal 尚未讀取；讀取失敗不建立任何紀錄。")
        self._set_table_rows("portfolio", (), "Portfolio 尚未讀取；讀取失敗不建立任何交易。")
        self._block_continuity_controls(
            f"Journey 讀取失敗；研究動作已停用：{message}"
        )
        self.journeyFailed.emit(message)

    def _on_cancelled(self, request_id: int, code: str, result_id: str) -> None:
        if self._is_current(request_id, code, result_id) and not self._closing:
            self._set_status("Journey 讀取已取消。", "warning")

    def _is_current(self, request_id: int, code: str, result_id: str) -> bool:
        return (
            request_id == self._request_id
            and code == self._active_code
            and result_id == self._active_result_id
        )

    def _set_loading_state(self, code: str, result_id: str) -> None:
        self.identity_label.setText(f"{code}｜決策與後續結果載入中")
        self._set_status("正在背景讀取決策與後續結果…", "info")
        self.technical_identity_label.setText(
            f"result_id：{result_id}\n完整來源 identity 讀取中…"
        )
        self._set_table_rows("maturity", (), "讀取中…")
        self._set_table_rows("evidence", (), "讀取中…")
        self._set_table_rows("journal", (), "讀取中…")
        self._set_table_rows("portfolio", (), "讀取中…")
        self._block_continuity_controls(
            "正在驗證 exact result_id + stock_code；驗證完成前研究動作已停用。"
        )
        self._set_navigation_state()

    def _set_unlinked(self, text: str, *, quality: str = "warning") -> None:
        self._set_status(text, quality)
        self._set_table_rows(
            "maturity",
            (),
            "未連結：需要 exact result_id + stock_code 才能列出 maturity。",
        )
        self._set_table_rows(
            "evidence",
            (),
            "未連結：不以同股同日猜測 Evidence event。",
        )
        self._set_table_rows(
            "journal",
            (),
            "未連結：缺少 result_id 時不列入既有 Journal。",
        )
        self._set_table_rows(
            "portfolio",
            (),
            "未連結：缺少 result_id 時不列入 Portfolio，也不建立交易紀錄。",
        )
        self._set_navigation_state()

    def _set_status(self, text: str, quality: str) -> None:
        self.status_label.setText(text)
        self.status_badge.setText(_status_label(quality))
        self.status_badge.set_quality(_status_tone(quality))
        self.status_badge.setAccessibleDescription(f"Journey 狀態：{text}")

    def _set_navigation_state(self) -> None:
        self.reload_button.setEnabled(
            not self._closing and bool(self._active_result_id) and not self.is_busy()
        )

    def _set_table_rows(
        self,
        table_id: str,
        rows: Sequence[Sequence[str]],
        empty_text: str,
    ) -> None:
        table = self._tables[table_id]
        columns = self._table_columns[table_id]
        table.setModel(JourneyTableModel(columns, rows, table))
        table.setVisible(bool(rows))
        empty = self._empty_labels[table_id]
        empty.setText(empty_text)
        empty.setVisible(not rows)
        if rows:
            table.resizeColumnsToContents()

    def _render_journey(
        self,
        journey: DecisionOutcomeJourney,
        code: str,
        result_id: str,
    ) -> None:
        candidate_key = (result_id, code)
        candidate = next(
            (
                item
                for item in journey.recommendation_result.candidates
                if item.candidate_key == candidate_key
            ),
            None,
        )
        self._restore_identity_label(
            code,
            stock_name=None if candidate is None else candidate.stock_name,
        )
        if candidate is None:
            self._set_status(
                f"未連結：此推薦結果沒有 {code} 的候選資料；不以同股同日補接。",
                "warning",
            )
            self._set_table_rows(
                "maturity",
                (),
                "此 result_id 沒有目前股票的 exact candidate_key。",
            )
            self._set_table_rows(
                "evidence",
                (),
                "沒有可安全顯示的 candidate Evidence event。",
            )
            self._set_table_rows("journal", (), "沒有可安全顯示的 candidate Journal。")
            self._set_table_rows(
                "portfolio",
                (),
                "沒有可安全顯示的 candidate Portfolio event。",
            )
            self._block_continuity_controls(
                "此 result_id 沒有目前股票的 exact candidate_key；研究動作已停用，"
                "不以同股同日猜測要綁定的結果。"
            )
            self._set_navigation_state()
            return

        if self.continuity_controls is not None:
            # Controls initially read Journal from the incoming context.  Keep
            # them blocked until the Journey read has proved that the same
            # result_id actually contains this stock's candidate row.
            self.continuity_controls.set_context(self.context)

        maturity = tuple(
            item
            for item in project_outcome_maturity(journey.outcome_maturity)
            if item.candidate_key == candidate_key
        )
        maturity_rows = tuple(
            (
                f"{item.window_days}個交易日",
                _link_status_text(item.status),
                _outcome_status_text(item.outcome_status),
                item.reason or "—",
            )
            for item in maturity
        )
        self._set_table_rows(
            "maturity",
            maturity_rows,
            "此 candidate 尚無 5/10/20/60 maturity row；不補造 outcome。",
        )

        events = tuple(
            item
            for item in journey.evidence_events
            if item.candidate_key == candidate_key
        )
        evidence_rows = tuple(
            (
                item.event_date or item.decision_date or "—",
                item.event_id,
                item.event_type or "—",
                item.source_type or "—",
                _link_status_text(item.link_status),
                item.available_date or "—",
                _event_outcome_text(item),
            )
            for item in events
        )
        self._set_table_rows(
            "evidence",
            evidence_rows,
            "沒有以 exact candidate_key 連入 Evidence event；不以日期／股票補接。",
        )

        candidate_trade_ledger = tuple(
            item
            for item in journey.portfolio_ledger_events
            if item.stock_code == code
        )
        candidate_ledger_ids = {item.record_id for item in candidate_trade_ledger}
        candidate_ledger = candidate_trade_ledger + tuple(
            item
            for item in journey.portfolio_ledger_events
            if item.event_type == "compensation"
            and item.reverses_event_id in candidate_ledger_ids
            and item.record_id not in candidate_ledger_ids
        )
        journals = tuple(
            item
            for item in journey.journal_entries
            if _journal_matches_candidate(
                item,
                result_id,
                candidate_ledger_ids,
                stock_code=code,
            )
        )
        journal_rows_list: list[tuple[str, ...]] = []
        for item in journals:
            scope = _journal_scope(
                item,
                result_id,
                candidate_ledger_ids,
                stock_code=code,
            )
            if scope is None:
                continue
            journal_rows_list.append(
                (
                    item.journal_id,
                    scope,
                    item.linked_type or "—",
                    item.linked_id or "—",
                    item.thesis_id or "—",
                    f"{item.relationship_type or '—'} → {item.relationship_target_id or '—'}",
                    _link_status_text(item.link_status),
                    item.created_at or "—",
                )
            )
        journal_rows = tuple(journal_rows_list)
        self._set_table_rows(
            "journal",
            journal_rows,
            "目前沒有以 exact result／candidate ledger key 連入的 Journal；缺少 Journal 不阻擋推薦追蹤。",
        )

        trades = tuple(
            item
            for item in journey.portfolio_trades
            if item.stock_code == code
        )
        portfolio_rows = tuple(
            (
                item.record_id,
                item.source_namespace or "legacy",
                item.event_type,
                item.stock_code or "—",
                _quantity_side_text(item.side, item.quantity),
                _decimal_text(item.price),
                item.execution_semantics,
                _link_status_text(item.link_status),
            )
            for item in candidate_ledger
        ) + tuple(
            (
                item.record_id,
                "legacy",
                "trade",
                item.stock_code or "—",
                _quantity_side_text(item.side, item.quantity),
                _decimal_text(item.price),
                item.execution_semantics,
                _link_status_text(item.link_status),
            )
            for item in trades
        )
        self._set_table_rows(
            "portfolio",
            portfolio_rows,
            "目前沒有此 candidate 的 Portfolio event；不建立交易紀錄，也不把研究報酬當成成交。",
        )

        pending = any(
            item.outcome_status == "insufficient_future_data" for item in maturity
        )
        identity = journey.recommendation_result.source_identity
        self.technical_identity_label.setText(
            f"result_id：{result_id}\n"
            f"candidate_key：{_candidate_text(candidate_key)}\n"
            f"來源 provider：{identity.source_provider_id or '未知'}\n"
            f"source snapshot：{identity.source_snapshot_id or identity.source_snapshot_hash or '未知'}\n"
            f"策略版本：{identity.strategy_version_id or '未知'}｜設定：{identity.strategy_config_id or '未知'}"
        )
        quality = _journey_quality(journey.status, maturity)
        summary = _journey_summary(journey.status, maturity)
        if quality == "conflict":
            if pending:
                summary += "；部分期限尚待結果成熟。"
            self._set_status(summary, "conflict")
        elif pending:
            self._set_status(
                "已連結；尚待結果成熟（未有足夠未來資料），不是實際成交損益。",
                "warning",
            )
        else:
            self._set_status(summary, quality)
        self._set_navigation_state()

    def _block_continuity_controls(self, message: str) -> None:
        """Fail closed when Journey has not verified a candidate row."""

        controls = self.continuity_controls
        if controls is None:
            return
        identity = controls.identity
        if identity is not None and identity.identity_status == "linked":
            identity = replace(identity, identity_status=IDENTITY_STATUS_UNKNOWN)
        controls.set_blocked(message, identity=identity)

    def _restore_identity_label(
        self,
        code: str,
        *,
        stock_name: str | None = None,
    ) -> None:
        name = stock_name or (
            self.context.stock_name
            if self.context is not None
            and self.context.stock_code.strip() == code
            else ""
        )
        self.identity_label.setText(f"{code}{(' ' + name) if name else ''}")

    def _toggle_details(self) -> None:
        visible = self.technical_details.isVisible()
        self.technical_details.setVisible(not visible)
        self.details_toggle.setText("收合技術詳情" if not visible else "顯示技術詳情")

    def _wrapped_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        return label


def _candidate_text(candidate_key: tuple[str, str] | None) -> str:
    if candidate_key is None:
        return "—"
    return f"{candidate_key[0]}:{candidate_key[1]}"


def _link_status_text(status: JourneyLinkStatus) -> str:
    return {
        JourneyLinkStatus.LINKED: "已連結",
        JourneyLinkStatus.UNKNOWN: "未知／未判定",
        JourneyLinkStatus.UNLINKED: "未連結",
        JourneyLinkStatus.CONFLICT: "衝突",
        JourneyLinkStatus.AMBIGUOUS: "歧義",
        JourneyLinkStatus.DEFERRED: "待可得",
    }.get(status, "未知／未判定")


def _outcome_status_text(status: str | None) -> str:
    token = str(status or "").strip() or "unknown"
    if token == "insufficient_future_data":
        return "待成熟（未有足夠未來資料）"
    return {
        "ready": "來源已標示 ready",
        "observed": "已觀測",
        "missing": "缺資料",
        "unknown": "未知",
        "deferred": "待可得",
        "error": "讀取失敗",
    }.get(token, token)


def _status_label(value: str) -> str:
    return {
        "linked": "已連結",
        "partial": "部分連結",
        "conflict": "衝突",
        "unknown": "未知",
        "warning": "注意",
        "error": "讀取失敗",
        "info": "讀取中",
    }.get(value, value or "未知")


def _status_tone(value: str) -> str:
    if value in {"linked", "observed"}:
        return "observed"
    if value in {"partial", "warning"}:
        return "warning"
    if value in {"conflict", "error"}:
        return "missing"
    return "info"


def _journey_quality(
    status: JourneyStatus,
    maturity: Sequence[OutcomeMaturityRecord],
) -> str:
    if status is JourneyStatus.CONFLICT or any(
        item.status in {JourneyLinkStatus.CONFLICT, JourneyLinkStatus.AMBIGUOUS}
        for item in maturity
    ):
        return "conflict"
    if status is JourneyStatus.PARTIAL or any(
        item.status in {JourneyLinkStatus.DEFERRED, JourneyLinkStatus.UNKNOWN}
        for item in maturity
    ):
        return "partial"
    return "linked"


def _journey_summary(
    status: JourneyStatus,
    maturity: Sequence[OutcomeMaturityRecord],
) -> str:
    if any(item.outcome_status in {None, "", "unknown"} for item in maturity):
        return f"Journey identity {_status_label(status.value)}；部分後續 outcome 未知。"
    return f"Journey identity {_status_label(status.value)}；結果狀態依每個 horizon 的 outcome_status 判讀。"


def _event_outcome_text(event: EvidenceEventRecord) -> str:
    if not event.outcomes:
        return "尚無後續結果"
    return "；".join(
        f"{outcome.window_days or '未知'}日：{_outcome_status_text(outcome.outcome_status)}"
        for outcome in event.outcomes
    )


def _journal_matches_candidate(
    entry: JournalEntryRecord,
    result_id: str,
    candidate_ledger_ids: set[str],
    *,
    stock_code: str = "",
) -> bool:
    return (
        _journal_scope(
            entry,
            result_id,
            candidate_ledger_ids,
            stock_code=stock_code,
        )
        is not None
    )


def _journal_scope(
    entry: JournalEntryRecord,
    result_id: str,
    candidate_ledger_ids: set[str],
    *,
    stock_code: str = "",
) -> str | None:
    """區分 typed 個股筆記、legacy 共用筆記與精確 ledger 關聯筆記。"""

    # typed identity 是較細的權威範圍；unknown／conflict 不得回退到
    # linked_id=result_id 的整次推薦共用標籤。
    if entry.decision_identity is not None:
        identity = entry.decision_identity
        if entry.link_status is not JourneyLinkStatus.LINKED or not identity.is_linked:
            return None
        if (
            not stock_code
            or identity.result_id != result_id
            or identity.stock_code != stock_code
        ):
            return None
        return "此股票關聯筆記"

    if entry.linked_id in candidate_ledger_ids:
        return "此股票關聯筆記"
    if entry.linked_id == result_id:
        return "本次推薦共用筆記"
    # A concrete linked_id has finer granularity than source_id.  Do not let a
    # shared result source promote an A-only trade note into every stock view.
    if entry.linked_id:
        return None
    if entry.source_id == result_id:
        return "本次推薦共用筆記"
    return None


def _quantity_side_text(side: str | None, quantity: int | None) -> str:
    side_text = side or "—"
    quantity_text = "—" if quantity is None else str(quantity)
    return f"{side_text} / {quantity_text}"


def _decimal_text(value: object) -> str:
    if value is None:
        return "—"
    return str(value)
