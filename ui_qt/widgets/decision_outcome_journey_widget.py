"""個股研究中的 Decision → Outcome Journey 視圖。

資料區只消費 ``DecisionOutcomeJourney`` read model；下方研究動作控制項
只寫既有 Journal append-only history，不建立交易、不採用 Advice，也不以
同股同日猜測 ``result_id``。所有背景讀取都透過 ``TaskWorker``，以 request
generation + stock code + result id 丟棄過期回傳，避免切股後舊結果污染畫面。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any, Protocol

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGroupBox,
    QHeaderView,
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
from ui_qt.widgets.layout_helpers import (
    ensure_visible_rows,
    set_scroll_content_constraints,
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
        *,
        tooltips: Sequence[Sequence[str]] | None = None,
    ) -> None:
        super().__init__(parent)
        self._columns = tuple(str(column) for column in columns)
        self._rows = tuple(tuple(str(cell) for cell in row) for row in rows)
        self._tooltips = (
            None
            if tooltips is None
            else tuple(tuple(str(cell) for cell in row) for row in tooltips)
        )

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
        if role == Qt.DisplayRole:
            return value
        if role == Qt.ToolTipRole:
            if self._tooltips is None:
                return value
            if index.row() >= len(self._tooltips):
                return None
            tooltip_row = self._tooltips[index.row()]
            if index.column() >= len(tooltip_row):
                return None
            return tooltip_row[index.column()]
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
        set_scroll_content_constraints(content)

        maturity_group = QGroupBox("後續結果（5／10／20／60 個交易日）")
        maturity_layout = QVBoxLayout(maturity_group)
        maturity_layout.addWidget(
            self._wrapped_label(
                "每個期限會分開呈現連結狀態與結果狀態；"
                "連結成功不等於結果已成熟。計畫目標日與實際取價日分列；"
                "未提供的日期不由目前日曆或舊價格列推算。"
            )
        )
        self.maturity_shared_limits_label = self._wrapped_label("")
        self.maturity_shared_limits_label.setObjectName(
            "decisionOutcomeJourneyMaturitySharedLimits"
        )
        self.maturity_shared_limits_label.setAccessibleName("所列期限共同來源限制")
        self.maturity_shared_limits_label.setVisible(False)
        maturity_layout.addWidget(self.maturity_shared_limits_label)
        self.maturity_table = self._make_table(
            "maturity",
            (
                "期限",
                "連結狀態",
                "結果狀態",
                "說明",
                "計畫目標日",
                "實際取價日",
            ),
            220,
        )
        maturity_layout.addWidget(self.maturity_table)
        maturity_layout.addWidget(self._empty_labels["maturity"])
        content_layout.addWidget(maturity_group)

        personal_choice_group = QGroupBox("此推薦結果的個人決定歷史")
        personal_choice_layout = QVBoxLayout(personal_choice_group)
        personal_choice_layout.addWidget(
            self._wrapped_label(
                "採用、拒絕或推翻理由只會從同一 result、股票、決策日與來源 snapshot 的已驗證 Journal 讀取；"
                "每列是一筆 append-only 歷史，依記錄時間排列；較早決定會保留，不代表多筆決定同時有效。"
                "這是研究紀錄，不是成交或績效結果。"
            )
        )
        self.personal_choice_table = self._make_table(
            "personalChoices",
            ("結果／股票", "個人決定", "推翻理由", "記錄時間", "連結狀態"),
            180,
        )
        personal_choice_layout.addWidget(self.personal_choice_table)
        personal_choice_layout.addWidget(self._empty_labels["personalChoices"])
        content_layout.addWidget(personal_choice_group)

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
        self._set_table_rows(
            "personalChoices",
            (),
            "尚未載入；缺少可核驗的同一推薦結果個人決定。",
        )
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
        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
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
        ensure_visible_rows(table, 5)
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
        is_recommendation = context.source_workspace == "recommendation"
        snapshot_title = "Universe snapshot" if is_recommendation else "來源 snapshot"
        snapshot_id_name = "universe_snapshot_id" if is_recommendation else "source_snapshot_id"
        snapshot_hash_name = "universe_snapshot_hash" if is_recommendation else "source_snapshot_hash"
        source_id_name = "推薦結果 ID" if is_recommendation else "source_id"
        self.context_label.setText(
            f"來源：{source}｜工作區：{context.source_workspace or '未標示'}｜"
            f"決策日：{context.decision_date or '未知'}｜資料日：{context.data_date or '未知'}｜"
            f"{snapshot_title}：{context.source_snapshot_id or context.source_snapshot_hash or '未知'}｜"
            "期限：5／10／20／60 個交易日"
        )
        self.technical_identity_label.setText(
            f"result_id：{context.result_id or '未知'}\n"
            f"candidate_key：{context.result_id or '未知'}:{context.stock_code}\n"
            f"{source_id_name}：{context.source_id or '未知'}\n"
            f"{snapshot_id_name}：{context.source_snapshot_id or '未知'}｜"
            f"{snapshot_hash_name}：{context.source_snapshot_hash or '未知'}\n"
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
        self._set_table_rows(
            "personalChoices",
            (),
            "Journey 讀取失敗；沒有顯示未核驗的個人決定。",
        )
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
        self._set_table_rows("personalChoices", (), "正在驗證同一 result／股票／來源 identity…")
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
            "personalChoices",
            (),
            "未連結：缺少完整 result／股票／決策日／來源 snapshot identity。",
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

    def _set_maturity_shared_limits(
        self,
        maturity: Sequence[OutcomeMaturityRecord],
        shared_limits: Sequence[str],
    ) -> None:
        if not shared_limits:
            self._clear_maturity_shared_limits()
            return
        horizons = tuple(dict.fromkeys(item.window_days for item in maturity))
        if len(horizons) < 2:
            self._clear_maturity_shared_limits()
            return
        listed_horizons = "／".join(str(window) for window in horizons)
        visible_limits = tuple(
            "所列期限結果均未獲正式採認"
            if limit == "此期限結果未獲正式採認"
            else limit
            for limit in shared_limits
        )
        self.maturity_shared_limits_label.setText(
            f"所列期限（{listed_horizons} 個交易日）共有以下來源限制：\n"
            + "；".join(visible_limits)
        )
        self.maturity_shared_limits_label.setVisible(True)

    def _clear_maturity_shared_limits(self) -> None:
        self.maturity_shared_limits_label.clear()
        self.maturity_shared_limits_label.setVisible(False)

    def _set_table_rows(
        self,
        table_id: str,
        rows: Sequence[Sequence[str]],
        empty_text: str,
        *,
        tooltips: Sequence[Sequence[str]] | None = None,
    ) -> None:
        table = self._tables[table_id]
        columns = self._table_columns[table_id]
        table.setModel(JourneyTableModel(columns, rows, table, tooltips=tooltips))
        table.setVisible(bool(rows))
        if table_id == "maturity" and not rows:
            self._clear_maturity_shared_limits()
        empty = self._empty_labels[table_id]
        empty.setText(empty_text)
        empty.setVisible(not rows)
        if rows:
            table.resizeColumnsToContents()
            if table_id == "maturity":
                header = table.horizontalHeader()
                header.setStretchLastSection(False)
                for column in (0, 1, 2, 4, 5):
                    header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
                header.setSectionResizeMode(3, QHeaderView.Stretch)

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
                "personalChoices",
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
        shared_limits = _shared_maturity_source_limits(maturity)
        self._set_maturity_shared_limits(maturity, shared_limits)
        maturity_rows: list[tuple[str, ...]] = []
        maturity_tooltips: list[tuple[str, ...]] = []
        for item in maturity:
            horizon = f"{item.window_days}個交易日"
            link_status = _link_status_text(item.status)
            outcome_status = _outcome_status_text(item.outcome_status)
            display_reason = _maturity_reason_with_source_limits(
                item,
                exclude_shared_limits=shared_limits,
                prioritize_target=True,
            )
            original_reason = _maturity_reason_with_source_limits(item)
            planned_date = item.planned_official_maturity_date or "未提供"
            actual_date = item.outcome_price_date or "未提供"
            maturity_rows.append(
                (
                    horizon,
                    link_status,
                    outcome_status,
                    display_reason,
                    planned_date,
                    actual_date,
                )
            )
            maturity_tooltips.append(
                (
                    horizon,
                    link_status,
                    outcome_status,
                    original_reason,
                    planned_date,
                    actual_date,
                )
            )
        self._set_table_rows(
            "maturity",
            maturity_rows,
            "此 candidate 尚無 5/10/20/60 maturity row；不補造 outcome。",
            tooltips=maturity_tooltips,
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
        personal_choice_rows = tuple(
            sorted(
                (
                    row
                    for item in journals
                    if (
                        row := _personal_choice_row(
                            item,
                            self.context,
                            journey,
                            result_id,
                            code,
                        )
                    )
                    is not None
                ),
                key=lambda row: row[3],
            )
        )
        self._set_table_rows(
            "personalChoices",
            personal_choice_rows,
            "尚無同一推薦結果、股票、決策日與來源 snapshot 的可核驗個人決定；缺件不會以同股同日補接。",
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
        market_fingerprint = (
            f"sha256:{identity.market_data_fingerprint}"
            if identity.market_data_fingerprint
            else "未知"
        )
        self.technical_identity_label.setText(
            f"result_id：{result_id}\n"
            f"candidate_key：{_candidate_text(candidate_key)}\n"
            f"來源 provider：{identity.source_provider_id or '未知'}\n"
            f"決策日：{identity.decision_date or '未知'}｜行情資料日：{identity.market_data_as_of_date or '未知'}\n"
            f"行情來源：{identity.market_data_source_id or '未知'}｜行情指紋：{market_fingerprint}\n"
            f"來源 snapshot：{identity.source_snapshot_id or identity.source_snapshot_hash or '未知'}\n"
            f"Universe snapshot：{identity.universe_snapshot_id or identity.universe_snapshot_hash or '未知'}\n"
            f"策略版本：{identity.strategy_version_id or '未知'}｜設定：{identity.strategy_config_id or '未知'}"
        )
        quality = _journey_quality(journey.status, maturity)
        summary = _journey_summary(journey.status, maturity)
        if quality == "conflict":
            self._set_status(summary, "conflict")
        elif pending:
            self._set_status(summary, "warning")
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
        "missing_price": "缺結果價格",
        "unknown": "未知",
        "deferred": "待可得",
        "error": "讀取失敗",
    }.get(token, token)


def _maturity_reason_text(reason: str) -> str:
    return {
        "outcome_available_at_query_boundary": "已取得該期限的來源結果；是否成熟請看結果狀態。",
        "outcome_visible_at_query_boundary": "在指定查詢時點可見；是否成熟請看結果狀態。",
        "outcome_not_available_at_query_boundary": "指定查詢時點尚不可得。",
        "outcome_return_basis_mismatch": "結果計算基準與原推薦不同。",
        "outcome_key_missing": "找不到該期限的精確結果。",
        "conflicting_duplicate_outcome": "該期限有重複且衝突的結果。",
        "evidence_event_key_ambiguous": "原推薦對應多個證據事件，無法唯一連結。",
        "evidence_event_key_missing": "找不到原推薦的精確證據事件。",
        "evidence_read_failure": "證據讀取失敗。",
        "evidence_reader_not_configured": "未設定證據讀取來源。",
    }.get(reason, reason or "—")


def _maturity_source_limits(item: OutcomeMaturityRecord) -> tuple[str, ...]:
    limits: list[str] = []
    if item.source_data_quality == "degraded":
        limits.append("結果資料品質：降級")
    if "source_not_ingested" in item.source_warning_codes:
        limits.append("結果引用來源尚未完成納入")
    if item.planned_official_calendar_status == "annual_plan_only":
        limits.append("交易日曆僅有年度計畫，臨時休市未核")
    if item.formal_credit_granted is False:
        limits.append("此期限結果未獲正式採認")
    return tuple(limits)


def _shared_maturity_source_limits(
    maturity: Sequence[OutcomeMaturityRecord],
) -> tuple[str, ...]:
    """只回傳至少兩個期限的每一列都共有的來源限制文字。"""

    if not maturity:
        return ()
    if len(tuple(dict.fromkeys(item.window_days for item in maturity))) < 2:
        return ()
    first_limits = _maturity_source_limits(maturity[0])
    common = set(first_limits)
    for item in maturity[1:]:
        common.intersection_update(_maturity_source_limits(item))
    return tuple(dict.fromkeys(limit for limit in first_limits if limit in common))


def _maturity_reason_with_source_limits(
    item: OutcomeMaturityRecord,
    *,
    exclude_shared_limits: Sequence[str] = (),
    prioritize_target: bool = False,
) -> str:
    reason = _maturity_reason_text(item.reason)
    excluded = set(exclude_shared_limits)
    source_limits = [
        limit
        for limit in _maturity_source_limits(item)
        if limit not in excluded
    ]
    target = {
        "waiting_for_verified_official_session": "來源尚缺可核對的目標交易日",
        "waiting_for_planned_official_session": "來源標示等待計畫目標日",
        "missing_at_planned_official_session": "來源標示計畫目標日缺收盤價，需補來源",
        "observed_on_planned_official_session": "來源標示已取得計畫目標日價格",
    }.get(item.target_price_state or "")
    gap = (
        "不以後一筆價格替代缺價日"
        if item.source_price_gap_reason == "no_close_on_planned_official_session"
        else None
    )
    source_as_of = (
        "來源資料截止：" + item.source_data_as_of_date
        if item.source_data_as_of_date
        else None
    )
    if (
        prioritize_target
        and item.status is JourneyLinkStatus.LINKED
        and (target or gap)
    ):
        ordered_details = [detail for detail in (target, gap) if detail]
        ordered_details.extend(source_limits)
        if reason:
            ordered_details.append(reason.rstrip("。"))
        if source_as_of:
            ordered_details.append(source_as_of)
        return "；".join(ordered_details) + "。"

    limits = list(source_limits)
    if target:
        limits.append(target)
    if gap:
        limits.append(gap)
    if source_as_of:
        limits.append(source_as_of)
    if not limits:
        return reason
    return f"{reason} {'；'.join(limits)}。"


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
    if any(_maturity_source_limits(item) for item in maturity):
        return "warning"
    return "linked"


def _journey_summary(
    status: JourneyStatus,
    maturity: Sequence[OutcomeMaturityRecord],
) -> str:
    def windows(items: Sequence[OutcomeMaturityRecord]) -> str:
        ordered = sorted(items, key=lambda item: item.window_days)
        return "／".join(str(item.window_days) for item in ordered)

    linked = tuple(item for item in maturity if item.status is JourneyLinkStatus.LINKED)
    ready = tuple(item for item in linked if item.outcome_status == "ready")
    observed = tuple(item for item in linked if item.outcome_status == "observed")
    pending = tuple(
        item for item in linked if item.outcome_status == "insufficient_future_data"
    )
    other = tuple(
        item
        for item in linked
        if item.outcome_status not in {"ready", "observed", "insufficient_future_data"}
    )
    unlinked = tuple(
        item for item in maturity if item.status is not JourneyLinkStatus.LINKED
    )
    parts = [f"推薦結果身分：{_status_label(status.value)}"]
    if ready:
        parts.append(f"{windows(ready)} 個交易日來源已標示 ready，仍須核對成熟與來源")
    if observed:
        parts.append(f"{windows(observed)} 個交易日來源已標示已觀測")
    if pending:
        parts.append(f"{windows(pending)} 個交易日尚待結果成熟（未有足夠未來資料）")
    if other:
        parts.append(f"{windows(other)} 個交易日結果狀態請看下表")
    if unlinked:
        parts.append(f"{windows(unlinked)} 個交易日連結未核實或衝突，請看下表")
    if any(_maturity_source_limits(item) for item in maturity):
        parts.append("部分期限的來源品質或採認有限，請看逐期原因")
    if not maturity:
        parts.append("尚無期限結果")
    return "；".join(parts) + "。此處不是實際成交損益。"


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


def _personal_choice_row(
    entry: JournalEntryRecord,
    context: ResearchStockContextDTO | None,
    journey: DecisionOutcomeJourney,
    result_id: str,
    stock_code: str,
) -> tuple[str, str, str, str, str] | None:
    """只呈現 Journey 與目前 UI context 完全相符的個人決定。"""

    if (
        entry.source_type != "personal_recommendation_choice"
        or entry.link_status is not JourneyLinkStatus.LINKED
        or entry.linked_type != "recommendation_result"
        or entry.linked_id != result_id
        or entry.source_id != result_id
        or context is None
        or context.identity_status != "linked"
        or context.result_id.strip() != result_id
        or context.stock_code.strip() != stock_code
        or not context.decision_date.strip()
        or not context.source_snapshot_id.strip()
        or not context.source_snapshot_hash.strip()
    ):
        return None

    raw_choice = entry.original_payload.get("personal_recommendation_choice")
    if not isinstance(raw_choice, Mapping):
        return None
    try:
        from app_module.personalization_contract import PersonalRecommendationChoice

        choice = PersonalRecommendationChoice.from_mapping(raw_choice)
    except (TypeError, ValueError):
        return None

    identity = entry.decision_identity
    root_identity = journey.recommendation_result.source_identity
    root_result = journey.recommendation_result
    if (
        identity is None
        or not identity.is_linked
        or identity.result_id != result_id
        or identity.stock_code != stock_code
        or identity.decision_date != choice.decision_date
        or identity.source_snapshot_id != choice.source_snapshot_id
        or identity.source_snapshot_hash != choice.source_snapshot_hash
        or entry.source_snapshot_hash != choice.source_snapshot_hash
        or choice.result_id != result_id
        or choice.stock_code != stock_code
        or choice.decision_date != context.decision_date
        or choice.source_snapshot_id != context.source_snapshot_id
        or choice.source_snapshot_hash != context.source_snapshot_hash
        or root_identity.result_id != result_id
        or root_identity.decision_date != choice.decision_date
        or root_identity.universe_snapshot_id != choice.source_snapshot_id
        or root_identity.universe_snapshot_hash != choice.source_snapshot_hash
        or not root_result.canonical_integrity_verified
        or not root_result.canonical_payload_hash
        or not root_result.raw_artifact_sha256
        or root_result.canonical_payload_hash != choice.canonical_payload_hash
        or root_result.raw_artifact_sha256 != choice.raw_artifact_sha256
    ):
        return None

    choice_label = {
        "adopt": "個人採用",
        "reject": "個人拒絕",
        "override": "推翻原建議",
    }.get(choice.choice)
    if choice_label is None:
        return None
    reason = (
        choice.override_reason.detail
        if choice.override_reason is not None
        else "—"
    )
    return (
        f"{choice.result_id}:{choice.stock_code}",
        choice_label,
        reason,
        choice.action_at,
        "已連結",
    )


def _quantity_side_text(side: str | None, quantity: int | None) -> str:
    side_text = side or "—"
    quantity_text = "—" if quantity is None else str(quantity)
    return f"{side_text} / {quantity_text}"


def _decimal_text(value: object) -> str:
    if value is None:
        return "—"
    return str(value)
