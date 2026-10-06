"""Portfolio 可嵌入的使用者聲明持倉研究元件。

元件只呼叫 ``UserDeclaredHoldingResearchService`` 的 append-only write/read
介面；它不寫交易帳本、不建立 Paper identity，也不把研究建議轉成 order。
技術 identity、PIT source trace 與排除 cohort 收在可展開詳情，首屏維持中文
研究流程與待確認語氣。
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Sequence
from zoneinfo import ZoneInfo

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QDate, Qt, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDateEdit,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableView,
    QHeaderView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app_module.market_session_cadence import MarketSessionCadence
from app_module.user_declared_holding_research import (
    ConditionObservation,
    SavedRecommendationConditionContextProvider,
    FilesystemDailyMarketObservationProvider,
    PortfolioConditionResearchProvider,
    SOURCE_STATUS_USER_DECLARED,
    UserDeclaredHoldingDraft,
    UserDeclaredHoldingRecord,
    UserDeclaredHoldingResearchReadModel,
    UserDeclaredHoldingResearchRow,
    UserDeclaredHoldingResearchService,
    format_user_declared_research_summary,
    format_user_declared_research_technical,
    research_action_label,
    research_status_label,
)
from ui_qt.theme import MIDNIGHT_ANALYST
from ui_qt.widgets.layout_helpers import ensure_visible_rows
from ui_qt.widgets.table_style import apply_financial_table_style
from ui_qt.workers.task_worker import TaskWorker


TAIPEI = ZoneInfo("Asia/Taipei")


def _safe_now(provider: Any) -> datetime:
    value = provider()
    if not isinstance(value, datetime):
        raise ValueError("now_provider 必須回傳 datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _money_text(value: Decimal | None) -> str:
    return "未知" if value is None else format(value, "f")


_REASON_LABELS = {
    "market_data_missing": "缺少目前價格",
    "condition_data_missing": "缺少 condition／Advice 來源",
    "market_stale": "目前價格已過期",
    "condition_stale": "condition 來源已過期",
    "market_as_of_date_future": "目前價格日期超出評估日",
    "condition_as_of_date_future": "condition 日期超出評估日",
    "market_available_at_future": "目前價格在 cutoff 後才可取得",
    "condition_available_at_future": "condition 在 cutoff 後才可取得",
    "market_quality_unknown": "市場來源品質未知",
    "condition_quality_unknown": "condition 來源品質未知",
    "market_source_hash_invalid": "市場來源 hash 無效",
    "condition_source_hash_invalid": "condition 來源 hash 無效",
    "market_availability_custody_missing": "市場來源沒有歷史 availability custody",
    "condition_availability_custody_missing": "condition 沒有歷史 availability custody",
    "condition_rule_missing": "沒有可追溯的研究規則",
    "condition_rule_not_comparable": "研究規則缺少可比較的目前訊號",
    "condition_source_not_usable": "condition 來源不可安全使用",
    "market_source_error": "市場來源讀取失敗",
    "condition_source_error": "condition 來源讀取失敗",
    "holding_revision_available_at_future": "聲明 revision 在 cutoff 後才存在",
    "research_baseline_missing": "缺少聲明時點以前的研究基準快照",
    "research_baseline_not_independent": "研究基準與目前快照不是獨立結果",
    "research_snapshot_date_missing": "研究快照日期無法確認",
    "research_analysis_identity_mismatch": "研究基準與目前分析身份不同，不能比較分數",
    "user_thesis_missing": "尚未提供研究假設",
    "condition_action_unknown": "condition 沒有可用研究動作",
    "holding_archived": "持倉已封存",
}


def _reason_text(row: UserDeclaredHoldingResearchRow) -> str:
    if row.research_status == "ready":
        return row.advice_reason or "來源完整，仍需人工檢視"
    return "；".join(_REASON_LABELS.get(item, item) for item in row.reason_codes) or "待補來源後確認"


def _table_action_text(action: str) -> str:
    """在主表以短中文顯示建議；完整 action 留在明細／技術詳情。"""

    return {
        "HOLD": "持有",
        "REDUCE_CANDIDATE": "減碼候選",
        "EXIT_CANDIDATE": "退出候選",
        "WAIT_CONFIRMATION": "待確認",
    }.get(action, "待確認")


def _table_status_text(status: str) -> str:
    """在主表保持狀態可讀；完整狀態語意仍由詳情與 technical view 提供。"""

    return {
        "ready": "可檢視",
        "unknown": "待確認",
        "archived": "已封存",
        "empty": "尚無持倉",
    }.get(status, "待確認")


class UserDeclaredHoldingResearchTableModel(QAbstractTableModel):
    """把 typed research rows 轉成 Portfolio 內可讀的表格。"""

    HEADERS = (
        "股票",
        "股數",
        "聲明成本",
        "研究建議",
        "研究狀態",
        "目前價格",
        "估值日期",
        "帳面變化",
        "原因",
    )

    def __init__(self, rows: Sequence[UserDeclaredHoldingResearchRow] = (), parent=None):
        super().__init__(parent)
        self._rows: tuple[UserDeclaredHoldingResearchRow, ...] = tuple(rows)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> Any:  # noqa: N802
        if role != Qt.DisplayRole or orientation != Qt.Horizontal:
            return None
        return self.HEADERS[section] if 0 <= section < len(self.HEADERS) else None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        row = self._rows[index.row()]
        if role == Qt.DisplayRole:
            return (
                row.stock_code,
                str(row.record.quantity),
                _money_text(row.record.declared_cost),
                _table_action_text(row.advice_action),
                _table_status_text(row.research_status),
                _money_text(row.market_price),
                row.market_as_of_date.isoformat() if row.market_as_of_date is not None else "未知",
                _money_text(row.mark_to_declared_cost_delta),
                _reason_text(row),
            )[index.column()]
        if role == Qt.ToolTipRole:
            return format_user_declared_research_technical(row)
        if role == Qt.TextAlignmentRole and index.column() in {1, 2, 5, 7}:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def set_rows(self, rows: Sequence[UserDeclaredHoldingResearchRow]) -> None:
        self.beginResetModel()
        self._rows = tuple(rows)
        self.endResetModel()

    def row_at(self, row: int) -> UserDeclaredHoldingResearchRow | None:
        return self._rows[row] if 0 <= row < len(self._rows) else None


class UserDeclaredHoldingResearchWidget(QWidget):
    """使用者聲明持倉的新增、保存、修訂、封存與日常研究檢視流程。"""

    researchChanged = Signal(object)

    def __init__(
        self,
        service: UserDeclaredHoldingResearchService,
        *,
        portfolio_service: Any | None = None,
        condition_monitor: Any | None = None,
        market_source: Any | None = None,
        condition_source: Any | None = None,
        portfolio_id: str = "default",
        now_provider: Any | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.service = service
        self.portfolio_service = portfolio_service
        self.portfolio_id = portfolio_id
        self._now_provider = now_provider or getattr(service, "now", lambda: datetime.now(timezone.utc))
        self.market_source = market_source or self._default_market_source()
        config = getattr(self.portfolio_service, "config", None)
        quote_cadence = (
            MarketSessionCadence.for_config(
                config, clock=lambda: _safe_now(self._now_provider)
            )
            if config is not None
            else None
        )
        self.condition_source = condition_source or (
            PortfolioConditionResearchProvider(
                self.market_source,
                condition_monitor=condition_monitor,
                condition_context_source=self._default_condition_context_source(),
                quote_cadence=quote_cadence,
                now_provider=lambda: _safe_now(self._now_provider),
            )
            if self.market_source is not None
            else None
        )
        self.read_model: UserDeclaredHoldingResearchReadModel | None = None
        self._editing_holding_id = ""
        self._editing_revision_number: int | None = None
        self._refresh_generation = 0
        self._refresh_worker: TaskWorker | None = None
        self._refresh_worker_contexts: dict[
            int, tuple[TaskWorker, int, tuple[str, int | None] | None]
        ] = {}
        self._refresh_pending = False
        self._pending_request: tuple[date, datetime] | None = None
        self._pending_selection: tuple[str, int | None] | None = None
        self._closing = False
        self._setup_ui()
        self.refresh_research()

    def _default_market_source(self) -> FilesystemDailyMarketObservationProvider | None:
        config = getattr(self.portfolio_service, "config", None)
        if config is None:
            return None
        daily_price_dir = getattr(config, "daily_price_dir", None)
        if daily_price_dir is None:
            data_dir = getattr(config, "data_dir", None)
            if data_dir is None:
                return None
            daily_price_dir = Path(data_dir) / "daily_price"
        return FilesystemDailyMarketObservationProvider(
            daily_price_dir,
            now_provider=lambda: _safe_now(self._now_provider),
        )

    def _default_condition_context_source(self) -> Any | None:
        config = getattr(self.portfolio_service, "config", None)
        if config is None:
            return None
        return SavedRecommendationConditionContextProvider(config)

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        title = QLabel("使用者聲明持倉研究")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title.setFont(title_font)
        root.addWidget(title)

        self.boundary_label = QLabel(
            "這裡保存的是 user_declared 研究上下文，不是券商成交或 Paper Portfolio。"
            "聲明成本只作資訊性帳面變化；不代表已實現績效、滑價、校準或交易指令。"
        )
        self.boundary_label.setWordWrap(True)
        self.boundary_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.boundary_label.setStyleSheet(
            f"background: {MIDNIGHT_ANALYST.surface_2}; color: {MIDNIGHT_ANALYST.warning}; "
            f"border: 1px solid {MIDNIGHT_ANALYST.border}; padding: 7px;"
        )
        self.boundary_label.setAccessibleName("使用者聲明持倉研究安全邊界")
        root.addWidget(self.boundary_label)

        review_row = QHBoxLayout()
        review_row.addWidget(QLabel("評估日期"))
        self.evaluation_date_input = QDateEdit()
        self.evaluation_date_input.setCalendarPopup(True)
        self.evaluation_date_input.setAccessibleName("聲明持倉研究評估日期")
        review_row.addWidget(self.evaluation_date_input)
        self.refresh_button = QPushButton("重新讀取研究")
        self.refresh_button.setProperty("variant", "secondary")
        self.refresh_button.setAccessibleName("重新讀取使用者聲明持倉研究")
        self.refresh_button.clicked.connect(self.refresh_research)
        review_row.addWidget(self.refresh_button)
        review_row.addStretch()
        root.addLayout(review_row)

        self.summary_label = QLabel("尚未讀取 user_declared 研究。")
        self.summary_label.setWordWrap(True)
        self.summary_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.summary_label.setAccessibleName("使用者聲明持倉研究摘要")
        root.addWidget(self.summary_label)

        self.form_toggle = QPushButton("展開新增／修訂表單")
        self.form_toggle.setCheckable(True)
        self.form_toggle.setProperty("variant", "secondary")
        self.form_toggle.setAccessibleName("展開使用者聲明新增修訂表單")
        self.form_toggle.toggled.connect(self._toggle_form)
        root.addWidget(self.form_toggle, 0, Qt.AlignLeft)

        form_group = QGroupBox("新增／修訂聲明（保存後可重開讀回）")
        self.form_group = form_group
        form = QFormLayout(form_group)
        self.stock_code_input = QLineEdit()
        self.stock_code_input.setPlaceholderText("例如 2330")
        self.stock_code_input.setAccessibleName("聲明股票代號")
        form.addRow("股票代號", self.stock_code_input)
        self.quantity_input = QSpinBox()
        self.quantity_input.setRange(1, 2_000_000_000)
        self.quantity_input.setAccessibleName("聲明持有整數股數")
        form.addRow("整數股數", self.quantity_input)
        self.declared_cost_input = QLineEdit()
        self.declared_cost_input.setPlaceholderText("Decimal，例如 612.50")
        self.declared_cost_input.setAccessibleName("聲明成本 Decimal")
        form.addRow("聲明成本", self.declared_cost_input)
        self.declared_date_input = QDateEdit()
        self.declared_date_input.setCalendarPopup(True)
        self.declared_date_input.setAccessibleName("持倉聲明日期")
        form.addRow("聲明日期", self.declared_date_input)
        self.notes_input = QPlainTextEdit()
        self.notes_input.setMaximumHeight(66)
        self.notes_input.setPlaceholderText("選填：日常檢視筆記")
        self.notes_input.setAccessibleName("聲明持倉備註")
        form.addRow("備註", self.notes_input)
        self.thesis_input = QPlainTextEdit()
        self.thesis_input.setMaximumHeight(92)
        self.thesis_input.setPlaceholderText("選填：研究假設；未提供時建議會維持待確認")
        self.thesis_input.setAccessibleName("聲明持倉研究假設")
        form.addRow("研究假設", self.thesis_input)

        form_actions = QHBoxLayout()
        self.save_button = QPushButton("新增保存")
        self.save_button.setAccessibleName("新增保存使用者聲明持倉")
        self.save_button.clicked.connect(self.save_new)
        form_actions.addWidget(self.save_button)
        self.revise_button = QPushButton("修訂保存")
        self.revise_button.setProperty("variant", "secondary")
        self.revise_button.setEnabled(False)
        self.revise_button.setAccessibleName("修訂保存選取聲明持倉")
        self.revise_button.clicked.connect(self.save_revision)
        form_actions.addWidget(self.revise_button)
        self.archive_button = QPushButton("封存選取")
        self.archive_button.setProperty("variant", "danger")
        self.archive_button.setEnabled(False)
        self.archive_button.setAccessibleName("封存選取使用者聲明持倉")
        self.archive_button.clicked.connect(self.archive_selected)
        form_actions.addWidget(self.archive_button)
        self.clear_button = QPushButton("清除表單")
        self.clear_button.setProperty("variant", "ghost")
        self.clear_button.clicked.connect(self.clear_form)
        form_actions.addWidget(self.clear_button)
        form_actions.addStretch()
        form.addRow(form_actions)
        root.addWidget(form_group)

        self.table_model = UserDeclaredHoldingResearchTableModel(parent=self)
        self.holdings_table = QTableView()
        self.holdings_table.setModel(self.table_model)
        apply_financial_table_style(self.holdings_table)
        self.holdings_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.holdings_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.holdings_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.holdings_table.setAlternatingRowColors(True)
        self.holdings_table.setWordWrap(False)
        self.holdings_table.setAccessibleName("使用者聲明持倉研究表")
        self.holdings_table.setAccessibleDescription(
            "只顯示 user_declared research-only rows；同股以 exact holding identity 管理。"
        )
        # 研究表是主檢視；依自訂 row/header 高度重新確保至少五列可見。
        # 完整技術欄位仍留在可選詳情。
        self.holdings_table.verticalHeader().setDefaultSectionSize(28)
        self.holdings_table.verticalHeader().setMinimumSectionSize(28)
        holdings_header = self.holdings_table.horizontalHeader()
        holdings_header.setMinimumSectionSize(48)
        holdings_header.setStretchLastSection(True)
        compact_widths = (60, 50, 70, 100, 88, 70, 76)
        for column, width in enumerate(compact_widths):
            holdings_header.setSectionResizeMode(column, QHeaderView.Fixed)
            holdings_header.resizeSection(column, width)
        ensure_visible_rows(self.holdings_table, 5)
        self.holdings_table.clicked.connect(self._on_row_selected)
        root.addWidget(self.holdings_table, 1)

        self.detail_label = QLabel("選取一列後查看研究建議與待確認原因。")
        self.detail_label.setWordWrap(True)
        self.detail_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.detail_label.setAccessibleName("使用者聲明持倉研究明細")
        root.addWidget(self.detail_label)
        self.technical_toggle = QPushButton("查看技術詳情")
        self.technical_toggle.setCheckable(True)
        self.technical_toggle.setProperty("variant", "secondary")
        self.technical_toggle.clicked.connect(self._toggle_technical)
        root.addWidget(self.technical_toggle, 0, Qt.AlignRight)
        self.technical_detail = QTextEdit()
        self.technical_detail.setReadOnly(True)
        self.technical_detail.setMaximumHeight(150)
        self.technical_detail.setVisible(False)
        self.technical_detail.setAccessibleName("使用者聲明持倉研究技術詳情")
        root.addWidget(self.technical_detail)

        self._set_default_dates()
        self._set_form_expanded(False)

    def _set_form_expanded(self, expanded: bool) -> None:
        expanded = bool(expanded)
        if self.form_toggle.isChecked() != expanded:
            self.form_toggle.blockSignals(True)
            self.form_toggle.setChecked(expanded)
            self.form_toggle.blockSignals(False)
        self.form_group.setVisible(expanded)
        self.form_toggle.setText(
            "收合新增／修訂表單" if expanded else "展開新增／修訂表單"
        )

    def _toggle_form(self, checked: bool) -> None:
        self._set_form_expanded(bool(checked))

    def _set_default_dates(self) -> None:
        now = _safe_now(self._now_provider).astimezone(TAIPEI).date()
        qdate = QDate(now.year, now.month, now.day)
        self.evaluation_date_input.setDate(qdate)
        self.declared_date_input.setDate(qdate)

    def _selected_dates(self) -> tuple[date, datetime]:
        evaluation_date = self.evaluation_date_input.date().toPython()
        if not isinstance(evaluation_date, date):
            raise ValueError("評估日期無效")
        now = _safe_now(self._now_provider)
        if evaluation_date == now.astimezone(TAIPEI).date():
            return evaluation_date, now
        cutoff = datetime.combine(
            evaluation_date,
            time.max,
            tzinfo=TAIPEI,
        ).astimezone(timezone.utc)
        return evaluation_date, cutoff

    def _draft_from_form(self) -> UserDeclaredHoldingDraft:
        declared_date = self.declared_date_input.date().toPython()
        if not isinstance(declared_date, date):
            raise ValueError("聲明日期無效")
        return UserDeclaredHoldingDraft(
            stock_code=self.stock_code_input.text(),
            quantity=int(self.quantity_input.value()),
            declared_cost=self.declared_cost_input.text(),
            declared_date=declared_date,
            notes=self.notes_input.toPlainText(),
            thesis=self.thesis_input.toPlainText(),
            portfolio_id=self.portfolio_id,
        )

    @staticmethod
    def _read_research_task(
        service: UserDeclaredHoldingResearchService,
        evaluation_date: date,
        cutoff: datetime,
        portfolio_id: str,
        market_source: Any,
        condition_source: Any,
        cancel_callback=None,
    ) -> UserDeclaredHoldingResearchReadModel:
        """在 worker 中讀取純 domain snapshot；不接觸 Qt model/widget。"""

        if callable(cancel_callback) and cancel_callback():
            raise RuntimeError("user_declared research refresh cancelled before read")
        model = service.read_research(
            evaluation_date=evaluation_date,
            evaluated_at=cutoff,
            portfolio_id=portfolio_id,
            market_source=market_source,
            condition_source=condition_source,
            cancel_callback=cancel_callback,
        )
        if callable(cancel_callback) and cancel_callback():
            raise RuntimeError("user_declared research refresh cancelled after read")
        return model

    def refresh_research(
        self,
        *,
        select_holding_id: str | None = None,
        select_revision_number: int | None = None,
    ) -> None:
        """以合作式背景 worker 讀取研究，主執行緒只套用最新 generation。"""

        if self._closing:
            return
        try:
            evaluation_date, cutoff = self._selected_dates()
        except Exception as exc:  # noqa: BLE001 - UI 顯示 fail-closed 狀態
            self._show_refresh_error(exc)
            return

        if select_holding_id:
            self._pending_selection = (str(select_holding_id), select_revision_number)
        elif self._editing_holding_id and self._editing_revision_number is not None:
            self._pending_selection = (
                self._editing_holding_id,
                self._editing_revision_number,
            )
        else:
            self._pending_selection = None
        self._refresh_generation += 1
        self._pending_request = (evaluation_date, cutoff)
        if self._refresh_worker is not None and self.is_refresh_running():
            self._refresh_pending = True
            self._refresh_worker.cancel(cooperative=True, wait=False)
            self.summary_label.setText("研究背景刷新已排隊；正在取消較早一輪，保留最新日期。")
            self.summary_label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_secondary};")
            return
        self._start_research_worker(evaluation_date, cutoff)

    def _start_research_worker(self, evaluation_date: date, cutoff: datetime) -> None:
        if self._closing:
            return
        self._refresh_pending = False
        generation = self._refresh_generation
        selection = self._pending_selection
        self.refresh_button.setEnabled(False)
        self.summary_label.setText(
            "研究資料背景讀取中；目前畫面保留最近一次結果。"
        )
        self.summary_label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_secondary};")
        worker = TaskWorker(
            self._read_research_task,
            self.service,
            evaluation_date,
            cutoff,
            self.portfolio_id,
            self.market_source,
            self.condition_source,
        )
        self._refresh_worker = worker
        self._refresh_worker_contexts[id(worker)] = (worker, generation, selection)
        worker.finished.connect(self._receive_research_worker_finished)
        worker.error.connect(self._receive_research_worker_error)
        worker.cancelled.connect(self._receive_research_worker_cancelled)
        worker.start()

    def _take_research_worker_context(
        self,
    ) -> tuple[TaskWorker, int, tuple[str, int | None] | None] | None:
        sender = self.sender()
        if not isinstance(sender, TaskWorker):
            return None
        context = self._refresh_worker_contexts.pop(id(sender), None)
        if context is None or context[0] is not sender:
            return None
        return context

    @Slot(object)
    def _receive_research_worker_finished(self, model: object) -> None:
        context = self._take_research_worker_context()
        if context is None:
            return
        worker, generation, selection = context
        self._on_research_worker_finished(model, generation, worker, selection)

    @Slot(str)
    def _receive_research_worker_error(self, message: str) -> None:
        context = self._take_research_worker_context()
        if context is None:
            return
        worker, generation, _selection = context
        self._on_research_worker_error(message, generation, worker)

    @Slot()
    def _receive_research_worker_cancelled(self) -> None:
        context = self._take_research_worker_context()
        if context is None:
            return
        worker, generation, _selection = context
        self._on_research_worker_cancelled(generation, worker)

    def _on_research_worker_finished(
        self,
        model: object,
        generation: int,
        worker: TaskWorker,
        selection: tuple[str, int | None] | None,
    ) -> None:
        if worker is not self._refresh_worker:
            worker.deleteLater()
            return
        if generation == self._refresh_generation and not self._closing:
            if isinstance(model, UserDeclaredHoldingResearchReadModel):
                self._apply_research_read_model(model, selection)
            else:
                self._show_refresh_error(TypeError("研究 worker 回傳非 read model"))
        self._release_research_worker(worker)

    def _on_research_worker_error(
        self,
        message: str,
        generation: int,
        worker: TaskWorker,
    ) -> None:
        if worker is not self._refresh_worker:
            worker.deleteLater()
            return
        if generation == self._refresh_generation and not self._closing:
            self._show_refresh_error(message)
        self._release_research_worker(worker)

    def _on_research_worker_cancelled(self, generation: int, worker: TaskWorker) -> None:
        if worker is not self._refresh_worker:
            worker.deleteLater()
            return
        if generation == self._refresh_generation and not self._closing:
            self.summary_label.setText("研究背景刷新已取消；畫面保留最近一次結果。")
            self.summary_label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.warning};")
        self._release_research_worker(worker)

    def _release_research_worker(self, worker: TaskWorker) -> None:
        self._refresh_worker_contexts.pop(id(worker), None)
        if worker is not self._refresh_worker:
            worker.deleteLater()
            return
        self._refresh_worker = None
        worker.deleteLater()
        if self._refresh_pending and not self._closing:
            request = self._pending_request
            if request is not None:
                self._start_research_worker(*request)
            else:
                self.refresh_button.setEnabled(True)
            return
        self.refresh_button.setEnabled(not self._closing)

    def _apply_research_read_model(
        self,
        model: UserDeclaredHoldingResearchReadModel,
        selection: tuple[str, int | None] | None,
    ) -> None:
        self.read_model = model
        self.table_model.set_rows(model.rows)
        self.summary_label.setText(format_user_declared_research_summary(model))
        self.summary_label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_secondary};")
        if selection is not None and self._select_exact(*selection):
            self.researchChanged.emit(model)
            return
        # evaluation date 切換後若 revision 不同，清掉 exact editor identity；
        # 不得讓歷史 row 悄悄修訂目前 revision。
        self.holdings_table.clearSelection()
        self._clear_selection_state()
        self.researchChanged.emit(model)

    def _show_refresh_error(self, exc: object) -> None:
        self.read_model = None
        self.table_model.set_rows(())
        self.holdings_table.clearSelection()
        self._clear_selection_state()
        self.summary_label.setText(f"持倉研究讀取失敗；維持未知。原因：{exc}")
        self.summary_label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.warning};")
        self.researchChanged.emit(None)

    def is_refresh_running(self) -> bool:
        worker = self._refresh_worker
        if worker is None:
            return False
        try:
            return bool(worker.isRunning())
        except RuntimeError:
            return False

    def _select_exact(self, holding_id: str, revision_number: int | None) -> bool:
        for row_number in range(self.table_model.rowCount()):
            row = self.table_model.row_at(row_number)
            if (
                row is not None
                and row.holding_id == holding_id
                and revision_number is not None
                and row.record.revision_number == revision_number
            ):
                self.holdings_table.selectRow(row_number)
                self._on_row_selected(self.table_model.index(row_number, 0))
                return True
        return False

    def _on_row_selected(self, index: QModelIndex) -> None:
        row = self.table_model.row_at(index.row())
        if row is None:
            return
        self._editing_holding_id = row.holding_id
        self._editing_revision_number = row.record.revision_number
        self._set_form_expanded(True)
        self._load_record(row.record)
        self.revise_button.setEnabled(not row.record.archived)
        self.archive_button.setEnabled(not row.record.archived)
        self.detail_label.setText(
            f"{row.stock_code}｜研究建議：{research_action_label(row.advice_action)}｜"
            f"狀態：{research_status_label(row.research_status)}｜原因：{_reason_text(row)}\n"
            f"聲明研究帳｜估值日期：{row.market_as_of_date.isoformat() if row.market_as_of_date else '未知'}｜"
            f"評估日：{row.evaluation_date.isoformat()}｜成本口徑：使用者聲明單價 {_money_text(row.record.declared_cost)}\n"
            "費稅／滑價／換手率／集中度影響：未提供，未知；帳面變化不是已實現績效。"
            "過期或缺件時維持待確認，不以研究建議判定安全；同股原研究身份見技術詳情。"
        )
        self.technical_detail.setText(format_user_declared_research_technical(row))

    def _load_record(self, record: UserDeclaredHoldingRecord) -> None:
        self.stock_code_input.setText(record.stock_code)
        self.quantity_input.setValue(record.quantity)
        self.declared_cost_input.setText(format(record.declared_cost, "f"))
        self.declared_date_input.setDate(
            QDate(record.declared_date.year, record.declared_date.month, record.declared_date.day)
        )
        self.notes_input.setPlainText(record.notes)
        self.thesis_input.setPlainText(record.thesis)

    def _clear_selection_state(self) -> None:
        self._editing_holding_id = ""
        self._editing_revision_number = None
        self.revise_button.setEnabled(False)
        self.archive_button.setEnabled(False)
        self.detail_label.setText("選取一列後查看研究建議與待確認原因。")
        self.technical_detail.clear()

    def clear_form(self) -> None:
        self._clear_selection_state()
        self.stock_code_input.clear()
        self.quantity_input.setValue(1)
        self.declared_cost_input.clear()
        self.notes_input.clear()
        self.thesis_input.clear()
        self._set_default_dates()
        self._set_form_expanded(False)
        self.holdings_table.clearSelection()

    def save_new(self) -> None:
        try:
            record = self.service.create_holding(self._draft_from_form())
        except Exception as exc:  # noqa: BLE001 - UI 顯示 fail-closed 錯誤
            self.summary_label.setText(f"新增聲明未保存：{exc}")
            self.summary_label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.warning};")
            return
        self.summary_label.setText(f"已保存 user_declared 聲明：{record.stock_code}，revision 1。")
        self.refresh_research(
            select_holding_id=record.holding_id,
            select_revision_number=record.revision_number,
        )

    def save_revision(self) -> None:
        if not self._editing_holding_id or self._editing_revision_number is None:
            self.summary_label.setText("請先選取要修訂的 user_declared 持倉。")
            return
        try:
            record = self.service.revise_holding(
                self._editing_holding_id,
                self._draft_from_form(),
                expected_revision_number=self._editing_revision_number,
            )
        except Exception as exc:  # noqa: BLE001 - UI 顯示 CAS／輸入錯誤
            self.summary_label.setText(f"修訂未保存；請重新讀取後確認。原因：{exc}")
            self.summary_label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.warning};")
            return
        self.summary_label.setText(f"已保存修訂：{record.stock_code}，revision {record.revision_number}。")
        self.refresh_research(
            select_holding_id=record.holding_id,
            select_revision_number=record.revision_number,
        )

    def archive_selected(self, *, confirm: bool = True) -> None:
        if not self._editing_holding_id or self._editing_revision_number is None:
            self.summary_label.setText("請先選取要封存的 user_declared 持倉。")
            return
        if confirm:
            answer = QMessageBox.question(
                self,
                "封存使用者聲明持倉",
                "封存只會停止 active research view，完整 revision history 仍會保留。是否繼續？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        holding_id = self._editing_holding_id
        revision_number = self._editing_revision_number
        try:
            record = self.service.archive_holding(
                holding_id,
                expected_revision_number=revision_number,
                reason="由 Portfolio user_declared 研究面板封存",
            )
        except Exception as exc:  # noqa: BLE001 - UI 顯示 CAS／輸入錯誤
            self.summary_label.setText(f"封存未完成；請重新讀取後確認。原因：{exc}")
            self.summary_label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.warning};")
            return
        self.clear_form()
        self.summary_label.setText(f"已封存 {record.stock_code}；歷史 revision 仍可追溯。")
        self.refresh_research()

    def _toggle_technical(self, checked: bool) -> None:
        self.technical_detail.setVisible(bool(checked))
        self.technical_toggle.setText("收合技術詳情" if checked else "查看技術詳情")

    def begin_shutdown(self) -> None:
        """鎖住新的研究刷新並合作式取消目前 worker。"""

        self._closing = True
        self._refresh_generation += 1
        self._refresh_pending = False
        self._pending_request = None
        worker = self._refresh_worker
        if worker is not None and self.is_refresh_running():
            worker.cancel(cooperative=True, wait=False)

    def closeEvent(self, event) -> None:
        """關閉前不強制終止研究 worker，避免讀檔資源被中斷。"""

        self.begin_shutdown()
        if self.is_refresh_running():
            event.ignore()
            return
        worker = self._refresh_worker
        self._refresh_worker = None
        if worker is not None:
            worker.deleteLater()
        super().closeEvent(event)


__all__ = [
    "UserDeclaredHoldingResearchTableModel",
    "UserDeclaredHoldingResearchWidget",
]
