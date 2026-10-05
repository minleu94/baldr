"""每日市場研究快照的唯讀瀏覽與明示更新入口。"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

from PySide6.QtCore import QDate, QSignalBlocker, Qt, QTime, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from app_module.research_session import ResearchStockContextDTO
from ui_qt.theme import MIDNIGHT_ANALYST
from ui_qt.widgets.table_style import apply_financial_table_style
from ui_qt.workers.task_worker import TaskWorker


_TAIPEI = ZoneInfo("Asia/Taipei")
_CONDITION_LABELS = {
    "close_above_ma20": "收盤價高於 MA20",
    "close_above_ma60": "收盤價高於 MA60",
}
_STATE_LABELS = {
    "match": "符合",
    "no_match": "不符合",
    "unknown": "未知",
}
_RELATION_LABELS = {
    "above": "高於",
    "below": "低於",
    "equal": "相等",
    "unknown": "關係未知",
}
_FILTER_VALUES = ("all", "match", "no_match", "unknown")


class DailyMarketResearchView(QWidget):
    """只讀呈現已發布快照，並由使用者明示啟動有界更新。"""

    stockResearchRequested = Signal(object)

    def __init__(self, service: object | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self._snapshot: object | None = None
        self._all_rows: tuple[object, ...] = ()
        self._visible_rows: tuple[object, ...] = ()
        self._manifest_sha256 = ""
        self._manifest_identity_sha256 = ""
        self._loaded_cohort_id = ""
        self._loaded_decision_date = ""
        self._worker: TaskWorker | None = None
        self._operation_generation = 0
        self._initial_read_started = False
        self._shutting_down = False
        self._selected_stock_code = ""
        self._build_ui()
        self._set_service_availability()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        title = QLabel("每日研究條件")
        title.setObjectName("dailyMarketResearchTitle")
        title.setAccessibleName("每日研究條件")
        title.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_primary}; font-size: 15px; font-weight: 700;"
        )
        root.addWidget(title)

        self.disclaimer_label = QLabel(
            "研究快照：僅表示明示 cohort 的既有 close／MA20／MA60 條件，"
            "不是全市場、正式推薦、獲利機率或交易資格。未知條件會保留為未知。"
        )
        self.disclaimer_label.setObjectName("dailyMarketResearchDisclaimer")
        self.disclaimer_label.setAccessibleName("每日研究條件安全說明")
        self.disclaimer_label.setWordWrap(True)
        self.disclaimer_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary}; "
            f"background: {MIDNIGHT_ANALYST.surface_2}; "
            f"border-left: 4px solid {MIDNIGHT_ANALYST.accent}; padding: 7px;"
        )
        root.addWidget(self.disclaimer_label)

        inputs = QGroupBox("研究範圍與條件")
        inputs.setObjectName("dailyMarketResearchInputs")
        form = QFormLayout(inputs)
        form.setContentsMargins(10, 8, 10, 8)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(7)

        self.stock_codes_input = QLineEdit("2382,1477")
        self.stock_codes_input.setObjectName("dailyMarketResearchStockCodes")
        self.stock_codes_input.setAccessibleName("每日研究股票代碼")
        self.stock_codes_input.setPlaceholderText("以逗號分隔，最多 16 檔，例如 2382,1477")
        self.stock_codes_input.setMaxLength(256)
        form.addRow("股票代碼（最多 16 檔）", self.stock_codes_input)

        self.cohort_id_input = QLineEdit("daily-market-research")
        self.cohort_id_input.setObjectName("dailyMarketResearchCohortId")
        self.cohort_id_input.setAccessibleName("每日研究 cohort 識別")
        self.cohort_id_input.setMaxLength(160)
        form.addRow("研究 cohort", self.cohort_id_input)

        cutoff_row = QHBoxLayout()
        taipei_now = datetime.now(_TAIPEI)
        self.decision_date_edit = QDateEdit(
            QDate.fromString(taipei_now.date().isoformat(), Qt.DateFormat.ISODate)
        )
        self.decision_date_edit.setObjectName("dailyMarketResearchDecisionDate")
        self.decision_date_edit.setAccessibleName("每日研究基準日期")
        self.decision_date_edit.setCalendarPopup(True)
        self.decision_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.decision_date_edit.setMaximumDate(
            QDate.fromString(taipei_now.date().isoformat(), Qt.DateFormat.ISODate)
        )
        self.decision_date_edit.setMinimumDate(QDate(1990, 1, 1))
        cutoff_row.addWidget(self.decision_date_edit)

        self.decision_time_edit = QTimeEdit(
            QTime.fromString(taipei_now.strftime("%H:%M:%S"), "HH:mm:ss")
        )
        self.decision_time_edit.setObjectName("dailyMarketResearchDecisionTime")
        self.decision_time_edit.setAccessibleName("每日研究台北時間截止時刻")
        self.decision_time_edit.setDisplayFormat("HH:mm:ss")
        cutoff_row.addWidget(QLabel("Asia/Taipei"))
        cutoff_row.addWidget(self.decision_time_edit)
        cutoff_row.addStretch(1)
        form.addRow("決策基準／截止時間", cutoff_row)

        condition_row = QHBoxLayout()
        self.ma20_checkbox = QCheckBox("收盤價高於 MA20")
        self.ma20_checkbox.setObjectName("dailyMarketResearchMa20")
        self.ma20_checkbox.setAccessibleName("使用收盤價高於 MA20 條件")
        self.ma20_checkbox.setChecked(True)
        condition_row.addWidget(self.ma20_checkbox)
        self.ma60_checkbox = QCheckBox("收盤價高於 MA60")
        self.ma60_checkbox.setObjectName("dailyMarketResearchMa60")
        self.ma60_checkbox.setAccessibleName("使用收盤價高於 MA60 條件")
        self.ma60_checkbox.setChecked(True)
        condition_row.addWidget(self.ma60_checkbox)
        self.combine_mode_combo = QComboBox()
        self.combine_mode_combo.setObjectName("dailyMarketResearchCombineMode")
        self.combine_mode_combo.setAccessibleName("每日研究條件組合方式")
        self.combine_mode_combo.addItem("全部符合（AND）", "AND")
        self.combine_mode_combo.addItem("任一符合（OR）", "OR")
        condition_row.addWidget(self.combine_mode_combo)
        condition_row.addStretch(1)
        form.addRow("條件規則", condition_row)
        root.addWidget(inputs)

        action_row = QHBoxLayout()
        self.refresh_button = QPushButton("更新研究快照")
        self.refresh_button.setObjectName("dailyMarketResearchUpdateSnapshot")
        self.refresh_button.setAccessibleName("明示更新有界每日研究快照")
        self.refresh_button.setProperty("variant", "primary")
        self.refresh_button.setToolTip(
            "只有按此按鈕才執行有界快照產生；開啟頁面、排序與篩選不會產生資料。"
        )
        self.refresh_button.clicked.connect(self.start_snapshot_update)
        action_row.addWidget(self.refresh_button)

        self.reload_button = QPushButton("重讀已發布快照")
        self.reload_button.setObjectName("dailyMarketResearchReloadSnapshot")
        self.reload_button.setAccessibleName("唯讀重新核對每日研究快照")
        self.reload_button.setToolTip(
            "唯讀核對已發布的快照與目前來源；不會執行 producer。"
        )
        self.reload_button.clicked.connect(self.reload_published_snapshot)
        action_row.addWidget(self.reload_button)

        self.cancel_button = QPushButton("取消更新")
        self.cancel_button.setObjectName("dailyMarketResearchCancel")
        self.cancel_button.setAccessibleName("取消每日研究快照工作")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_active_operation)
        action_row.addWidget(self.cancel_button)

        self.filter_state_combo = QComboBox()
        self.filter_state_combo.setObjectName("dailyMarketResearchFilterState")
        self.filter_state_combo.setAccessibleName("每日研究狀態篩選")
        for label, value in (
            ("全部", "all"),
            ("符合", "match"),
            ("不符合", "no_match"),
            ("未知", "unknown"),
        ):
            self.filter_state_combo.addItem(label, value)
        action_row.addStretch(1)
        action_row.addWidget(QLabel("顯示"))
        action_row.addWidget(self.filter_state_combo)
        root.addLayout(action_row)

        self.summary_label = QLabel("尚未載入已發布研究快照。")
        self.summary_label.setObjectName("dailyMarketResearchSummary")
        self.summary_label.setAccessibleName("每日研究快照與狀態計數")
        self.summary_label.setWordWrap(True)
        self.summary_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.summary_label)

        self.status_label = QLabel("首次開啟時只會唯讀核對已發布快照；不會自動更新。")
        self.status_label.setObjectName("dailyMarketResearchStatus")
        self.status_label.setAccessibleName("每日研究快照讀取狀態")
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.status_label)

        self.results_table = QTableWidget(0, 6)
        self.results_table.setObjectName("dailyMarketResearchResults")
        self.results_table.setAccessibleName("每日研究條件結果")
        self.results_table.setHorizontalHeaderLabels(
            ("股票代碼", "資料日", "收盤／MA20", "收盤／MA60", "整體狀態", "理由／未知原因")
        )
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.results_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setSortingEnabled(True)
        self.results_table.horizontalHeader().setStretchLastSection(True)
        self.results_table.horizontalHeader().setSectionResizeMode(
            0, self.results_table.horizontalHeader().ResizeMode.ResizeToContents
        )
        self.results_table.horizontalHeader().setSectionResizeMode(
            1, self.results_table.horizontalHeader().ResizeMode.ResizeToContents
        )
        apply_financial_table_style(self.results_table)
        self.results_table.itemSelectionChanged.connect(self._sync_open_button)
        self.results_table.itemDoubleClicked.connect(lambda _item: self.open_selected_stock())
        root.addWidget(self.results_table, 1)

        self.open_selected_stock_button = QPushButton("開啟選中個股研究報告")
        self.open_selected_stock_button.setObjectName("dailyMarketResearchOpenStock")
        self.open_selected_stock_button.setAccessibleName("由研究快照開啟選中個股報告")
        self.open_selected_stock_button.setEnabled(False)
        self.open_selected_stock_button.clicked.connect(self.open_selected_stock)
        root.addWidget(self.open_selected_stock_button)

        for widget in (
            self.stock_codes_input,
            self.cohort_id_input,
            self.decision_date_edit,
            self.decision_time_edit,
            self.ma20_checkbox,
            self.ma60_checkbox,
            self.combine_mode_combo,
            self.filter_state_combo,
        ):
            if isinstance(widget, QCheckBox):
                widget.toggled.connect(self._apply_filter_controls)
            elif isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(self._apply_filter_controls)

    def _set_service_availability(self) -> None:
        available = self.service is not None
        self.refresh_button.setEnabled(available)
        self.reload_button.setEnabled(available)
        if not available:
            self.status_label.setText("每日研究快照服務尚未接線；目前不會執行讀取或更新。")

    def on_first_open(self) -> None:
        """第一次切入此來源時唯讀核對 latest，不啟動 producer。"""

        if self._initial_read_started or self._shutting_down or self.service is None:
            return
        self._initial_read_started = True
        reader = getattr(self.service, "read_latest", None)
        if not callable(reader):
            self.status_label.setText("讀取服務尚未提供 latest 核對入口；可按「重讀已發布快照」。")
            return
        cohort_id = self.cohort_id_input.text().strip()
        if not cohort_id:
            self.status_label.setText("請先輸入研究 cohort，再唯讀核對已發布快照。")
            return

        def operation(cancel_callback: Callable[[], bool]) -> object:
            return reader(cohort_id, cancel_callback=cancel_callback)

        self._start_operation("initial_read", operation)

    def reload_published_snapshot(self) -> None:
        """唯讀重讀指定 cohort／日期的已發布快照。"""

        if self.service is None or self._shutting_down:
            return
        cohort_id = self.cohort_id_input.text().strip()
        if not cohort_id:
            self._show_input_error("請輸入研究 cohort。")
            return
        reader = getattr(self.service, "read_snapshot", None)
        if not callable(reader):
            self._show_input_error("快照讀取服務尚未提供。")
            return
        try:
            selected_date = self._selected_decision_date()
        except ValueError as exc:
            self._show_input_error(str(exc))
            return

        def operation(cancel_callback: Callable[[], bool]) -> object:
            return reader(
                cohort_id,
                selected_date,
                cancel_callback=cancel_callback,
            )

        self._start_operation("read", operation)

    def start_snapshot_update(self) -> None:
        """只有明示按下更新按鈕才執行 bounded producer。"""

        if self.service is None or self._shutting_down:
            return
        producer = getattr(self.service, "produce_snapshot", None)
        if not callable(producer):
            self._show_input_error("快照更新服務尚未提供。")
            return
        try:
            stock_codes = self._selected_stock_codes()
            cohort_id = self.cohort_id_input.text().strip()
            if not cohort_id:
                raise ValueError("請輸入研究 cohort。")
            condition_keys = self._selected_condition_keys()
            if not condition_keys:
                raise ValueError("至少選擇一條研究條件。")
            decision_cutoff = self._selected_decision_cutoff()
        except ValueError as exc:
            self._show_input_error(str(exc))
            return

        self._start_operation(
            "produce",
            lambda cancel_callback: self._produce_then_read(
                producer,
                cohort_id=cohort_id,
                stock_codes=stock_codes,
                decision_cutoff=decision_cutoff,
                cancel_callback=cancel_callback,
            ),
        )

    def _produce_then_read(
        self,
        producer: Callable[..., object],
        *,
        cohort_id: str,
        stock_codes: tuple[str, ...],
        decision_cutoff: datetime,
        cancel_callback: Callable[[], bool],
    ) -> dict[str, object]:
        result = producer(
            stock_codes,
            decision_cutoff,
            cohort_id,
            cancel_callback=cancel_callback,
        )
        status = str(getattr(result, "status", ""))
        if status not in {"published_complete", "unchanged"}:
            code = str(getattr(result, "error_code", "") or status or "update_not_published")
            message = str(getattr(result, "error_message", "") or "快照未發布。")
            raise RuntimeError(f"{code}: {message}")
        manifest_sha256 = str(getattr(result, "manifest_sha256", "") or "")
        if len(manifest_sha256) != 64:
            raise RuntimeError("producer_missing_manifest_sha256: 更新結果缺少已發布 manifest 身份。")
        reader = getattr(self.service, "read_snapshot", None)
        if not callable(reader):
            raise RuntimeError("snapshot_reader_missing: 快照讀取服務尚未提供。")
        snapshot = reader(
            cohort_id,
            decision_cutoff.date(),
            manifest_sha256=manifest_sha256,
            cancel_callback=cancel_callback,
        )
        return {"kind": "produce", "production": result, "snapshot": snapshot}

    def _start_operation(
        self,
        kind: str,
        operation: Callable[[Callable[[], bool]], object],
    ) -> None:
        if self._worker is not None and self._worker.isRunning():
            self.status_label.setText("已有快照讀取／更新工作進行中；請等待或先取消。")
            return
        self._operation_generation += 1
        generation = self._operation_generation
        self._initial_read_started = self._initial_read_started or kind == "initial_read"
        self._set_busy(True, kind)

        def task(cancel_callback: Callable[[], bool] | None = None) -> object:
            callback = cancel_callback or (lambda: False)
            try:
                return operation(callback)
            except Exception as exc:
                if type(exc).__name__ == "DailyMarketResearchCancelled" and callback():
                    return {"cancelled": True, "kind": kind}
                raise

        worker = TaskWorker(task)
        self._worker = worker
        worker.started.connect(lambda g=generation, op=kind: self._on_operation_started(g, op))
        worker.finished.connect(
            lambda result, g=generation, op=kind: self._on_operation_finished(g, op, result)
        )
        worker.error.connect(lambda message, g=generation: self._on_operation_error(g, message))
        worker.cancelled.connect(lambda g=generation: self._on_operation_cancelled(g))
        worker.native_thread_finished.connect(
            lambda current=worker, g=generation: self._on_worker_native_finished(current, g)
        )
        worker.start()

    def _set_busy(self, busy: bool, kind: str = "") -> None:
        if busy:
            self.status_label.setText(
                "正在明示更新有界研究快照；來源仍是研究用途。"
                if kind == "produce"
                else "正在唯讀核對已發布快照及當前來源身份…"
            )
        if not self._shutting_down:
            available = self.service is not None
            self.refresh_button.setEnabled(available and not busy)
            self.reload_button.setEnabled(available and not busy)
            self.cancel_button.setEnabled(busy)
            self.open_selected_stock_button.setEnabled(not busy and self._has_selected_row())
            for widget in (
                self.stock_codes_input,
                self.cohort_id_input,
                self.decision_date_edit,
                self.decision_time_edit,
                self.ma20_checkbox,
                self.ma60_checkbox,
                self.combine_mode_combo,
                self.filter_state_combo,
            ):
                widget.setEnabled(not busy)

    def _on_operation_started(self, generation: int, kind: str) -> None:
        if generation == self._operation_generation and not self._shutting_down:
            self._set_busy(True, kind)

    def _on_operation_finished(self, generation: int, kind: str, result: object) -> None:
        if generation != self._operation_generation or self._shutting_down:
            return
        if isinstance(result, Mapping) and result.get("cancelled") is True:
            self._on_operation_cancelled(generation)
            return
        if kind == "produce" and isinstance(result, Mapping):
            production = result.get("production")
            snapshot = result.get("snapshot")
            if production is None or snapshot is None:
                self._on_operation_error(generation, "快照更新後未取得可核驗讀回。")
                return
            self._render_production_result(production)
            self._accept_snapshot(snapshot, sync_cutoff=True)
            if self._snapshot is snapshot:
                self.status_label.setText(
                    f"{self.status_label.text()}；讀回 manifest 與來源核驗完成。"
                )
            return
        self._accept_snapshot(result, sync_cutoff=kind == "initial_read")

    def _on_operation_error(self, generation: int, message: str) -> None:
        if generation != self._operation_generation or self._shutting_down:
            return
        short_message = str(message).splitlines()[0].strip() or "未知快照讀取錯誤"
        self.status_label.setText(
            f"已發布快照無法核驗，條件視為未知；{short_message}。"
            "返回每日研究條件更新快照，按「重讀已發布快照」核對，或明示更新。"
        )
        self.status_label.setToolTip(str(message))
        self._clear_current_snapshot()

    def _on_operation_cancelled(self, generation: int) -> None:
        if generation != self._operation_generation or self._shutting_down:
            return
        self.status_label.setText("快照工作已取消；未把未完成讀取呈現為有效結果。")

    def _on_worker_native_finished(self, worker: TaskWorker, generation: int) -> None:
        if self._worker is not worker:
            return
        self._worker = None
        if not self._shutting_down and generation == self._operation_generation:
            self._set_busy(False)
            self._sync_open_button()

    def cancel_active_operation(self) -> None:
        worker = self._worker
        if worker is None or not worker.isRunning():
            return
        self.status_label.setText("已送出合作式取消；等待目前有限來源讀取安全返回…")
        self.cancel_button.setEnabled(False)
        worker.cancel(cooperative=True, wait=False)

    def _accept_snapshot(self, snapshot: object, *, sync_cutoff: bool) -> None:
        manifest = getattr(snapshot, "manifest", None)
        if not isinstance(manifest, Mapping):
            self._on_operation_error(self._operation_generation, "快照讀回未提供已核驗 manifest。")
            return
        cohort_id = str(manifest.get("cohort_id") or "").strip()
        decision_date = str(manifest.get("decision_date") or "").strip()
        manifest_sha256 = str(getattr(snapshot, "manifest_sha256", "") or "")
        manifest_identity = str(getattr(snapshot, "manifest_identity_sha256", "") or "")
        if not cohort_id or not decision_date or len(manifest_sha256) != 64 or len(manifest_identity) != 64:
            self._on_operation_error(self._operation_generation, "快照 manifest 缺少 cohort／日期／hash 身份。")
            return
        try:
            parsed_date = date.fromisoformat(decision_date)
        except ValueError:
            self._on_operation_error(self._operation_generation, "快照決策日期不是 YYYY-MM-DD。")
            return
        if parsed_date.isoformat() != decision_date:
            self._on_operation_error(self._operation_generation, "快照決策日期不是 YYYY-MM-DD。")
            return
        self._snapshot = snapshot
        self._manifest_sha256 = manifest_sha256
        self._manifest_identity_sha256 = manifest_identity
        self._loaded_cohort_id = cohort_id
        self._loaded_decision_date = decision_date
        if sync_cutoff:
            blocker_date = QSignalBlocker(self.decision_date_edit)
            blocker_time = QSignalBlocker(self.decision_time_edit)
            self.decision_date_edit.setDate(
                QDate.fromString(decision_date, Qt.DateFormat.ISODate)
            )
            cutoff_text = str(manifest.get("decision_cutoff") or "")
            try:
                cutoff = datetime.fromisoformat(cutoff_text)
            except ValueError:
                cutoff = None
            if cutoff is not None:
                self.decision_time_edit.setTime(
                    QTime.fromString(cutoff.astimezone(_TAIPEI).strftime("%H:%M:%S"), "HH:mm:ss")
                )
            del blocker_date, blocker_time
        self._render_snapshot()
        self.status_label.setText(
            f"已唯讀核驗 cohort {cohort_id}、決策日 {decision_date} 與當前來源身份；"
            "只呈現研究快照，不代表正式推薦或 historical PIT。"
        )

    def _render_production_result(self, result: object) -> None:
        status = str(getattr(result, "status", "unknown") or "unknown")
        reused = tuple(getattr(result, "reused_stock_codes", ()) or ())
        recomputed = tuple(getattr(result, "recomputed_stock_codes", ()) or ())
        self.status_label.setText(
            f"快照更新回報：{status}；重用 {len(reused)} 檔、重新投影 {len(recomputed)} 檔；"
            "以下為同一 manifest 的驗證讀回。"
        )

    def _render_snapshot(self) -> None:
        self._apply_filter_controls()

    def _apply_filter_controls(self, *_args: object) -> None:
        if self._snapshot is None or self.service is None:
            return
        condition_keys = self._selected_condition_keys()
        if not condition_keys:
            self._all_rows = ()
            self._visible_rows = ()
            self._render_rows()
            self.summary_label.setText(
                f"{self._loaded_decision_date}｜{self._loaded_cohort_id}｜"
                "請至少選擇一條研究條件；既有快照未變更。"
            )
            return
        filter_rows = getattr(self.service, "filter_rows", None)
        if not callable(filter_rows):
            self.status_label.setText("研究條件篩選服務尚未提供；快照保持已核驗但不展示推論。")
            return
        try:
            self._all_rows = tuple(
                filter_rows(
                    self._snapshot,
                    condition_keys,
                    str(self.combine_mode_combo.currentData() or "AND"),
                )
            )
        except Exception as exc:
            self._all_rows = ()
            self._visible_rows = ()
            self._render_rows()
            self.status_label.setText(
                f"研究條件篩選失敗；條件保持未知：{type(exc).__name__}: {exc}"
            )
            return
        self._render_summary()
        self._render_rows()

    def _render_summary(self) -> None:
        counts = {state: 0 for state in _STATE_LABELS}
        for row in self._all_rows:
            state = str(getattr(row, "combined_state", "unknown") or "unknown")
            counts[state if state in counts else "unknown"] += 1
        manifest = getattr(self._snapshot, "manifest", {})
        completeness = str(manifest.get("completeness") or "未提供")
        scope_label = "明示研究 cohort；非全市場／非正式推薦"
        if self._all_rows:
            scope_label = str(getattr(self._all_rows[0], "research_scope_label", scope_label) or scope_label)
        condition_names = "、".join(
            _CONDITION_LABELS.get(key, key) for key in self._selected_condition_keys()
        )
        combine_mode = str(self.combine_mode_combo.currentData() or "AND")
        self.summary_label.setText(
            f"基準日 {self._loaded_decision_date}｜cohort {self._loaded_cohort_id}｜"
            f"範圍 {scope_label}｜完整性 {completeness}｜條件 {condition_names}（{combine_mode}）｜"
            f"共 {len(self._all_rows)} 檔：符合 {counts['match']}、"
            f"不符合 {counts['no_match']}、未知 {counts['unknown']}。"
        )
        self.summary_label.setToolTip(
            f"manifest_identity_sha256: {self._manifest_identity_sha256}\n"
            f"manifest_sha256: {self._manifest_sha256}\n"
            f"completeness: {completeness}\n"
            "研究快照不代表完整市場母體、正式推薦或 historical PIT 資格。"
        )

    def _render_rows(self) -> None:
        selected_filter = str(self.filter_state_combo.currentData() or "all")
        rows = tuple(
            row
            for row in self._all_rows
            if selected_filter == "all"
            or str(getattr(row, "combined_state", "unknown") or "unknown") == selected_filter
        )
        self._visible_rows = rows
        self.results_table.setSortingEnabled(False)
        self.results_table.clearContents()
        self.results_table.setRowCount(len(rows))
        for row_number, row in enumerate(rows):
            stock_code = str(getattr(row, "stock_code", "") or "")
            condition_map = {
                str(getattr(condition, "key", "")): condition
                for condition in (getattr(row, "conditions", ()) or ())
            }
            values = (
                stock_code,
                str(getattr(row, "data_date", "") or "未知"),
                self._condition_text(condition_map.get("close_above_ma20")),
                self._condition_text(condition_map.get("close_above_ma60")),
                self._state_text(getattr(row, "combined_state", "unknown")),
                self._reason_text(row),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, row)
                if column == 0:
                    item.setData(
                        Qt.ItemDataRole.AccessibleTextRole,
                        f"股票代碼 {stock_code}",
                    )
                self.results_table.setItem(row_number, column, item)
        self.results_table.setSortingEnabled(True)
        self._sync_open_button()

    @staticmethod
    def _condition_text(condition: object | None) -> str:
        if condition is None:
            return "未知（條件缺件）"
        state = str(getattr(condition, "state", "unknown") or "unknown")
        label = _STATE_LABELS.get(state, "未知")
        relation = _RELATION_LABELS.get(
            str(getattr(condition, "relation", "unknown") or "unknown"),
            "",
        )
        reason = str(getattr(condition, "reason", "") or "").strip()
        text = f"{label}｜{relation}" if relation else label
        if state == "unknown" and reason:
            text += f"（{reason}）"
        return text

    @classmethod
    def _reason_text(cls, row: object) -> str:
        state = str(getattr(row, "combined_state", "unknown") or "unknown")
        reasons: list[str] = []
        if state == "match":
            reasons.extend(cls._as_texts(getattr(row, "why", ())))
        else:
            reasons.extend(cls._as_texts(getattr(row, "why_not", ())))
        if state == "unknown":
            for condition in (getattr(row, "conditions", ()) or ()):
                if str(getattr(condition, "state", "")) == "unknown":
                    reason = str(getattr(condition, "reason", "") or "").strip()
                    if reason:
                        reasons.append(reason)
        if not reasons:
            reasons.append(_STATE_LABELS.get(state, "未知"))
        return "；".join(dict.fromkeys(reasons))

    @staticmethod
    def _as_texts(value: object) -> list[str]:
        if isinstance(value, str):
            text = value.strip()
            return [text] if text else []
        if isinstance(value, Sequence):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value or "").strip()
        return [text] if text else []

    @staticmethod
    def _state_text(value: object) -> str:
        state = str(value or "unknown")
        label = _STATE_LABELS.get(state, "未知")
        return f"{label}（{state}）" if state not in _STATE_LABELS else label

    def _selected_stock_codes(self) -> tuple[str, ...]:
        raw_codes = self.stock_codes_input.text().replace("\n", ",").split(",")
        codes = tuple(code.strip() for code in raw_codes if code.strip())
        if not codes:
            raise ValueError("請至少輸入一個股票代碼。")
        if len(codes) > 16:
            raise ValueError("每日研究快照每次最多接受 16 檔股票。")
        if len(set(codes)) != len(codes):
            raise ValueError("股票代碼不可重複。")
        return codes

    def _selected_condition_keys(self) -> tuple[str, ...]:
        keys: list[str] = []
        if self.ma20_checkbox.isChecked():
            keys.append("close_above_ma20")
        if self.ma60_checkbox.isChecked():
            keys.append("close_above_ma60")
        return tuple(keys)

    def _selected_decision_date(self) -> date:
        value = self.decision_date_edit.date().toString(Qt.DateFormat.ISODate)
        return date.fromisoformat(value)

    def _selected_decision_cutoff(self) -> datetime:
        selected_date = self._selected_decision_date()
        selected_time = time.fromisoformat(
            self.decision_time_edit.time().toString("HH:mm:ss")
        )
        cutoff = datetime.combine(selected_date, selected_time, tzinfo=_TAIPEI)
        if cutoff > datetime.now(_TAIPEI):
            raise ValueError("研究截止時間不可晚於目前 Asia/Taipei 時間。")
        return cutoff

    def _show_input_error(self, message: str) -> None:
        self.status_label.setText(f"無法開始每日研究工作：{message}")
        self.status_label.setToolTip(message)

    def _has_selected_row(self) -> bool:
        return bool(self.results_table.selectionModel().selectedRows())

    def _sync_open_button(self) -> None:
        self.open_selected_stock_button.setEnabled(
            not self._shutting_down
            and (self._worker is None or not self._worker.isRunning())
            and self._has_selected_row()
        )

    def open_selected_stock(self) -> bool:
        if self.service is None or self._snapshot is None or self._shutting_down:
            return False
        selected = self.results_table.selectionModel().selectedRows()
        if len(selected) != 1:
            self.status_label.setText("請先選取一檔每日研究條件結果。")
            return False
        item = self.results_table.item(selected[0].row(), 0)
        row = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if row is None:
            self.status_label.setText("選取列缺少已核驗的快照身份；請重讀已發布快照。")
            return False
        context_builder = getattr(self.service, "context_for_stock", None)
        if not callable(context_builder):
            self.status_label.setText("個股下鑽 context builder 尚未接線。")
            return False
        try:
            context = context_builder(row, stock_name="")
        except Exception as exc:
            self.status_label.setText(
                f"無法建立釘選快照 context：{type(exc).__name__}: {exc}"
            )
            return False
        stock_code = str(getattr(row, "stock_code", "") or "").strip()
        expected = {
            "stock_code": stock_code,
            "source_kind": "daily_market_research_snapshot",
            "source_workspace": "recommendation",
            "decision_date": str(getattr(row, "decision_date", "") or ""),
            "source_snapshot_id": str(getattr(row, "source_snapshot_id", "") or ""),
            "source_snapshot_hash": str(getattr(row, "source_snapshot_hash", "") or ""),
        }
        for name, value in expected.items():
            if str(getattr(context, name, "") or "").strip() != value:
                self.status_label.setText(
                    f"下鑽 context 的 {name} 與選取列身份不一致；未開啟報告。"
                )
                return False
        if expected["source_snapshot_hash"] != self._manifest_sha256:
            self.status_label.setText("選取列不屬於目前驗證的 manifest；未開啟報告。")
            return False
        condition_keys = ",".join(self._selected_condition_keys())
        if str(getattr(context, "daily_snapshot_condition_keys", "") or "") != condition_keys:
            self.status_label.setText("下鑽 context 的條件範圍不一致；未開啟報告。")
            return False
        if str(getattr(context, "daily_snapshot_combine_mode", "") or "") != str(
            self.combine_mode_combo.currentData() or "AND"
        ):
            self.status_label.setText("下鑽 context 的 AND／OR 組合方式不一致；未開啟報告。")
            return False
        self._selected_stock_code = stock_code
        self.stockResearchRequested.emit(context)
        self.status_label.setText(
            f"已開啟 {stock_code} 的唯讀個股研究；來源仍釘選於目前 cohort／manifest。"
        )
        return True

    def research_snapshot_stock_codes(self) -> tuple[str, ...]:
        """返回目前已核驗 snapshot 的完整 cohort 股票清單。"""

        return tuple(
            str(getattr(row, "stock_code", "") or "").strip()
            for row in self._all_rows
            if str(getattr(row, "stock_code", "") or "").strip()
        )

    def restore_research_snapshot_stock(
        self,
        code: str,
        manifest_sha256: str | None = None,
    ) -> bool:
        """只在同一份已核驗 manifest 與目前篩選下還原原選取列。"""

        requested = str(code or "").strip()
        expected_hash = str(manifest_sha256 or self._manifest_sha256).strip()
        if (
            not requested
            or self._snapshot is None
            or not expected_hash
            or expected_hash != self._manifest_sha256
        ):
            self.status_label.setText(
                "原每日研究快照尚未載入或 manifest 已變；請返回每日研究條件重讀／更新快照。"
            )
            return False
        if requested not in self.research_snapshot_stock_codes():
            self.status_label.setText(
                f"{requested} 不在原 cohort 清單；請返回每日研究條件確認來源。"
            )
            return False
        for row_number in range(self.results_table.rowCount()):
            item = self.results_table.item(row_number, 0)
            if item is not None and item.text().strip() == requested:
                self.results_table.selectRow(row_number)
                self._selected_stock_code = requested
                return True
        self.status_label.setText(
            f"{requested} 仍屬原 cohort，但目前條件篩選未顯示該列；已保留現有篩選。"
        )
        return False

    def begin_shutdown(self) -> bool:
        """凍結本頁回呼並合作取消自己的來源讀取／更新工作。"""

        if self._shutting_down:
            worker = self._worker
            return worker is None or not worker.isRunning()
        self._shutting_down = True
        self._operation_generation += 1
        for widget in (
            self.refresh_button,
            self.reload_button,
            self.cancel_button,
            self.open_selected_stock_button,
            self.stock_codes_input,
            self.cohort_id_input,
            self.decision_date_edit,
            self.decision_time_edit,
            self.ma20_checkbox,
            self.ma60_checkbox,
            self.combine_mode_combo,
            self.filter_state_combo,
            self.results_table,
        ):
            widget.setEnabled(False)
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.cancel(cooperative=True, wait=False)
            return False
        return True

    def _clear_current_snapshot(self) -> None:
        self._snapshot = None
        self._all_rows = ()
        self._visible_rows = ()
        self._manifest_sha256 = ""
        self._manifest_identity_sha256 = ""
        self._loaded_cohort_id = ""
        self._loaded_decision_date = ""
        self.results_table.setRowCount(0)
        self.summary_label.setText("目前沒有可核驗快照；未知條件不會視為不符合。")
        self.open_selected_stock_button.setEnabled(False)
