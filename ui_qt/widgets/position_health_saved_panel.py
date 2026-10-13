"""Portfolio 內獨立的已保存 Position Health exact selector panel。"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Callable

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app_module.position_health_exact_paper_scope import PositionHealthExactPaperScopeFactory
from app_module.position_health_saved_archive import (
    SavedHealthReceiptCandidate,
    SavedHealthReceiptSelector,
)
from app_module.position_health_saved_selection import (
    SavedHealthSelection,
    SavedHealthSelectionStore,
    new_selection_from_open_result,
)
from app_module.position_health_transition_read_service import PositionHealthTransitionReadService
from app_module.decision_presentation import format_position_health_presentation
from ui_qt.models.workbench_table_models import PositionHealthTableModel
from ui_qt.workers.task_worker import TaskWorker


class _PositionHealthWorkerEvents(QObject):
    """將 worker 回呼排回 panel 所在的 Qt thread。"""

    completed = Signal(int, str, object)
    failed = Signal(int, str)
    cancelled = Signal(int)
    native_finished = Signal(int, object)


class PositionHealthSavedPanel(QGroupBox):
    """只顯示使用者明確選取的 immutable receipt，不自動選 latest。"""

    def __init__(
        self,
        *,
        reader: PositionHealthTransitionReadService,
        scope_factory: PositionHealthExactPaperScopeFactory,
        selection_store: SavedHealthSelectionStore,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("已保存健康評估（Paper main exact snapshot）", parent)
        self.reader = reader
        self.scope_factory = scope_factory
        self.selection_store = selection_store
        self._generation = 0
        self._closing = False
        self._worker: TaskWorker | None = None
        self._worker_generation = 0
        self._pending: tuple[int, str, tuple[Any, ...]] | None = None
        self._current_record: SavedHealthSelection | None = None
        self._candidates: tuple[SavedHealthReceiptCandidate, ...] = ()
        self._model = PositionHealthTableModel()
        self._worker_events = _PositionHealthWorkerEvents(self)
        self._worker_events.completed.connect(self._on_finished)
        self._worker_events.failed.connect(self._on_error)
        self._worker_events.cancelled.connect(self._on_cancelled)
        self._worker_events.native_finished.connect(self._on_native_finished)

        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.saved_receipt_selector = QComboBox(self)
        self.saved_receipt_selector.setAccessibleName("已保存健康評估選擇")
        self.saved_receipt_selector.setMinimumContentsLength(32)
        controls.addWidget(self.saved_receipt_selector, 1)
        self.saved_refresh_button = QPushButton("載入已保存評估", self)
        self.saved_refresh_button.clicked.connect(self.load_candidates)
        controls.addWidget(self.saved_refresh_button)
        self.saved_open_button = QPushButton("開啟所選評估", self)
        self.saved_open_button.clicked.connect(self.open_selected)
        controls.addWidget(self.saved_open_button)
        layout.addLayout(controls)

        self.saved_status_label = QLabel(
            "尚未選取已保存評估；不會自動套用 latest。", self
        )
        self.saved_status_label.setWordWrap(True)
        self.saved_status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.saved_status_label.setAccessibleName("已保存健康評估狀態")
        layout.addWidget(self.saved_status_label)

        self.saved_table = QTableView(self)
        self.saved_table.setModel(self._model)
        self.saved_table.setSelectionBehavior(QTableView.SelectRows)
        self.saved_table.setEditTriggers(QTableView.NoEditTriggers)
        self.saved_table.setAccessibleName("已保存健康評估持倉")
        self.saved_table.clicked.connect(self._save_selected_position)
        layout.addWidget(self.saved_table)

        self.saved_detail_label = QLabel("選取列以保存並回訪該 position identity。", self)
        self.saved_detail_label.setWordWrap(True)
        self.saved_detail_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.saved_detail_label.setAccessibleName("已保存健康評估詳情")
        layout.addWidget(self.saved_detail_label)

        self.saved_diagnostics_toggle = QToolButton(self)
        self.saved_diagnostics_toggle.setText("展開來源與驗證細節")
        self.saved_diagnostics_toggle.setCheckable(True)
        self.saved_diagnostics_toggle.setArrowType(Qt.RightArrow)
        self.saved_diagnostics_toggle.toggled.connect(self._set_diagnostics_visible)
        layout.addWidget(self.saved_diagnostics_toggle)

        self.saved_diagnostics_label = QLabel("尚無已開啟評估的來源細節。", self)
        self.saved_diagnostics_label.setWordWrap(True)
        self.saved_diagnostics_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.saved_diagnostics_label.setAccessibleName("已保存健康評估來源與驗證細節")
        self.saved_diagnostics_label.setVisible(False)
        layout.addWidget(self.saved_diagnostics_label)

    def reload_persisted_selection(self) -> None:
        """每次返回 Portfolio 以保存 receipt_id 重開，不查 latest。"""

        if self._closing:
            return
        try:
            record = self.selection_store.read()
        except Exception as exc:  # noqa: BLE001 - preference failure must stay visible
            self.saved_status_label.setText(
                f"已保存評估選擇檔無法安全讀取（{type(exc).__name__}）；未改用 latest。"
            )
            return
        if record is None:
            self.load_candidates()
            return
        self._queue("open_saved", record)

    def load_candidates(self) -> None:
        if self._closing:
            return
        self._queue("list_candidates")

    def open_selected(self) -> None:
        if self._closing:
            return
        candidate = self.saved_receipt_selector.currentData()
        if not isinstance(candidate, SavedHealthReceiptCandidate):
            self.saved_status_label.setText("請先載入並明確選取一份已保存評估。")
            return
        self._queue("open_candidate", candidate)

    def _set_diagnostics_visible(self, visible: bool) -> None:
        self.saved_diagnostics_label.setVisible(visible)
        self.saved_diagnostics_toggle.setArrowType(
            Qt.DownArrow if visible else Qt.RightArrow
        )
        self.saved_diagnostics_toggle.setText(
            "收合來源與驗證細節" if visible else "展開來源與驗證細節"
        )

    def _queue(self, action: str, *args: Any) -> None:
        if self._closing:
            return
        self._generation += 1
        generation = self._generation
        worker = self._worker
        if worker is not None:
            self._pending = (generation, action, args)
            try:
                worker.cancel(cooperative=True, wait=False)
            except RuntimeError:
                self.saved_status_label.setText(
                    "上一個 exact read 正在收尾；新選擇尚未套用。"
                )
                return
            self.saved_status_label.setText("正在取消上一個 exact read；新選擇尚未套用。")
            return
        self._launch(generation, action, args)

    def _launch(self, generation: int, action: str, args: tuple[Any, ...]) -> None:
        if self._closing or generation != self._generation:
            return
        if self._worker is not None:
            self._pending = (generation, action, args)
            try:
                self._worker.cancel(cooperative=True, wait=False)
            except RuntimeError:
                self.saved_status_label.setText(
                    "上一個 exact read 正在收尾；新選擇尚未套用。"
                )
                return
            self.saved_status_label.setText("正在取消上一個 exact read；新選擇尚未套用。")
            return
        self._worker_generation = generation
        if action == "list_candidates":
            task: Callable[..., Any] = _list_candidates_task
            task_args = (self.reader,)
            self.saved_status_label.setText("正在有界讀取已保存評估清單……")
        elif action == "open_candidate":
            candidate = args[0]
            task = _open_candidate_task
            task_args = (self.scope_factory, candidate)
            self.saved_status_label.setText("正在 exact 重讀所選 receipt 與 Paper snapshot……")
        elif action == "open_saved":
            record = args[0]
            task = _open_saved_task
            task_args = (self.scope_factory, record)
            self.saved_status_label.setText("正在以保存的 receipt identity 回訪……")
        elif action == "save_position":
            record = args[0]
            task = _save_selection_task
            task_args = (record,)
            self.saved_status_label.setText("正在確認明確的 position 選取……")
        else:
            raise ValueError("saved_health_panel_task_invalid")

        worker = TaskWorker(task, *task_args)
        self._worker = worker
        worker.finished.connect(
            lambda result, expected=generation, selected_action=action: (
                self._worker_events.completed.emit(expected, selected_action, result)
            )
        )
        worker.error.connect(
            lambda message, expected=generation: self._worker_events.failed.emit(expected, message)
        )
        worker.cancelled.connect(
            lambda expected=generation: self._worker_events.cancelled.emit(expected)
        )
        worker.native_thread_finished.connect(
            lambda expected=generation, current=worker: (
                self._worker_events.native_finished.emit(expected, current)
            )
        )
        worker.native_thread_finished.connect(worker.deleteLater)
        worker.start()

    def _on_finished(self, generation: int, action: str, value: Any) -> None:
        if self._closing or generation != self._generation:
            return
        if action == "list_candidates":
            self._candidates = tuple(value)
            self.saved_receipt_selector.blockSignals(True)
            self.saved_receipt_selector.clear()
            for candidate in self._candidates:
                label = (
                    f"{candidate.decision_date or '日期未知'}｜{candidate.status}｜"
                    f"{candidate.snapshot_id or 'snapshot 未知'}｜{candidate.receipt_id[-12:]}"
                )
                self.saved_receipt_selector.addItem(label, candidate)
            self.saved_receipt_selector.blockSignals(False)
            # 不將排序第一份當成使用者選擇；必須有明確互動才可開啟。
            self.saved_receipt_selector.setCurrentIndex(-1)
            self.saved_status_label.setText(
                f"已載入 {len(self._candidates)} 份有界候選；請明確選擇後開啟。"
                if self._candidates
                else "目前沒有可選的已保存評估；未以 latest 替代。"
            )
            return
        if action == "save_position":
            record = value
        else:
            # open_candidate must decode its result before committing the choice.
            # open_saved also returns this pair, but intentionally does not save it again.
            opened, record = value
        if action in {"save_position", "open_candidate"}:
            try:
                # The current generation commits on the panel's UI thread only.
                # A cancelled or stale worker cannot persist a superseded choice.
                self.selection_store.save(record)
            except Exception as exc:  # noqa: BLE001 - keep bounded preference failures visible
                self.saved_status_label.setText(
                    f"評估已讀取，但無法安全保存回訪選擇（{type(exc).__name__}）；"
                    "畫面保留原選擇。"
                )
                return
        if action == "save_position":
            self._current_record = record
            self.saved_status_label.setText(_format_saved_position_status(record))
            self.saved_diagnostics_label.setText(_format_selection_diagnostics(record))
            return
        self._current_record = record
        read_model = opened.read_model
        self._model.set_rows(read_model.positions)
        self.saved_table.setVisible(bool(read_model.positions))
        self.saved_status_label.setText(_format_opened_status(opened, record))
        self.saved_diagnostics_label.setText(_format_opened_diagnostics(opened, record))
        self.saved_detail_label.setText(
            "此面板只讀 immutable result 與同 route exact Paper snapshot。"
            " availability、source observation 與 result observation 時鐘分開呈現。"
        )
        if record.selected_position_id:
            self._select_saved_position(record.selected_position_id)

    def _on_error(self, generation: int, message: str) -> None:
        if self._closing or generation != self._generation:
            return
        del message  # 取消帶路徑的底層錯誤字串，UI 僅顯示安全分類。
        self.saved_status_label.setText(
            "已保存評估無法 exact reopen；未知狀態保留，未改用 latest。"
            "來源路徑與檔案內容不會放入此訊息。"
        )
        self._model.set_rows(())
        self.saved_table.setVisible(False)

    def _on_cancelled(self, generation: int) -> None:
        if not self._closing and generation == self._generation:
            self.saved_status_label.setText("exact read 已取消；未套用未完成結果。")

    def _on_native_finished(self, generation: int, worker: TaskWorker) -> None:
        if self._worker is not worker or self._worker_generation != generation:
            return
        self._worker = None
        pending = self._pending
        self._pending = None
        if pending is not None and not self._closing:
            pending_generation, action, args = pending
            if pending_generation == self._generation:
                self._launch(pending_generation, action, args)

    def _save_selected_position(self, index: Any) -> None:
        if self._current_record is None:
            return
        row = self._model.row_at(index.row())
        position_id = getattr(row, "position_id", None)
        if not isinstance(position_id, str) or not position_id:
            return
        updated = replace(
            self._current_record,
            selected_position_id=position_id,
            selected_at=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        )
        self._queue("save_position", updated)

    def _select_saved_position(self, position_id: str) -> None:
        for row_index in range(self._model.rowCount()):
            item = self._model.row_at(row_index)
            if getattr(item, "position_id", None) == position_id:
                self.saved_table.selectRow(row_index)
                self.saved_detail_label.setText(format_position_health_presentation(item))
                return
        self.saved_detail_label.setText(
            "保存的 position identity 不在此次 exact 評估列；未以股票代號替代。"
        )

    def begin_shutdown(self) -> None:
        self._closing = True
        self._generation += 1
        self._pending = None
        worker = self._worker
        if worker is not None:
            try:
                worker.cancel(cooperative=True, wait=False)
            except RuntimeError:
                pass

    def has_running_worker(self) -> bool:
        # Native completion, not isRunning(), releases the panel's ownership.
        return self._worker is not None


def _list_candidates_task(reader: PositionHealthTransitionReadService, cancel_callback=None):
    return reader.list_saved_receipts(cancel_callback=cancel_callback)


def _open_candidate_task(
    factory: PositionHealthExactPaperScopeFactory,
    candidate: SavedHealthReceiptCandidate,
    cancel_callback=None,
):
    opened = factory.open_saved_selection(
        SavedHealthReceiptSelector(candidate.receipt_id),
        cancel_callback=cancel_callback,
        expected_receipt_sha256=candidate.receipt_sha256,
        expected_result_sha256=candidate.result_sha256,
        expected_snapshot_rows_sha256=candidate.source_snapshot_rows_sha256,
        expected_snapshot_id=candidate.snapshot_id,
        expected_decision_date=(None if candidate.decision_date is None else candidate.decision_date.isoformat()),
    )
    if cancel_callback is not None and cancel_callback():
        raise RuntimeError("saved_health_exact_selection_cancelled")
    record = new_selection_from_open_result(opened)
    return opened, record


def _open_saved_task(
    factory: PositionHealthExactPaperScopeFactory,
    record: SavedHealthSelection,
    cancel_callback=None,
):
    opened = factory.open_saved_selection(
        SavedHealthReceiptSelector(record.receipt_id),
        cancel_callback=cancel_callback,
        expected_receipt_sha256=record.receipt_sha256,
        expected_result_sha256=record.result_sha256,
        expected_snapshot_rows_sha256=record.snapshot_rows_sha256,
        expected_snapshot_id=record.snapshot_id,
        expected_decision_date=record.decision_date,
    )
    _validate_reopened_record(opened, record)
    if cancel_callback is not None and cancel_callback():
        raise RuntimeError("saved_health_exact_selection_cancelled")
    return opened, record


def _save_selection_task(record: SavedHealthSelection, cancel_callback=None):
    if cancel_callback is not None and cancel_callback():
        raise RuntimeError("saved_health_selection_save_cancelled")
    return record


def _validate_reopened_record(opened: Any, record: SavedHealthSelection) -> None:
    source = opened.source
    model = opened.read_model
    expected = {
        "receipt_id": record.receipt_id,
        "receipt_sha256": record.receipt_sha256,
        "result_sha256": record.result_sha256,
        "snapshot_id": record.snapshot_id,
        "snapshot_rows_sha256": record.snapshot_rows_sha256,
        "decision_date": record.decision_date,
        "saved_receipt_available_at": record.saved_receipt_available_at,
        "health_observed_at": record.health_observed_at,
        "source_observed_at": record.source_observed_at,
        "source_available_at": record.source_available_at,
        "baseline_saved_available_at": record.baseline_saved_available_at,
        "health_source_available_at": record.health_source_available_at,
    }
    actual = {
        "receipt_id": source.receipt_id,
        "receipt_sha256": source.receipt_sha256,
        "result_sha256": source.result_sha256,
        "snapshot_id": opened.snapshot.snapshot_id,
        "snapshot_rows_sha256": opened.snapshot.source_snapshot_rows_sha256,
        "decision_date": opened.snapshot.decision_date.isoformat(),
        "saved_receipt_available_at": model.saved_receipt_available_at,
        "health_observed_at": model.observed_at,
        "source_observed_at": model.source_observed_at,
        "source_available_at": model.source_available_at,
        "baseline_saved_available_at": model.baseline_saved_available_at,
        "health_source_available_at": model.health_source_available_at,
    }
    if actual != expected:
        raise ValueError("saved_health_selection_reopen_metadata_mismatch")
    if model.source_witness_status != record.source_witness_status:
        raise ValueError("saved_health_selection_reopen_witness_status_mismatch")


def _format_opened_status(opened: Any, record: SavedHealthSelection) -> str:
    model = opened.read_model
    status_text = {
        "passed": "來源與評估資料已核對",
        "degraded": "評估資料有來源限制",
        "blocked": "評估資料受阻，結果保持未知",
        "stale": "評估資料已過期，結果保持未知",
    }.get(model.status, "評估狀態未知")
    return "\n".join((
        f"已開啟 {record.decision_date} 的已保存健康評估：{status_text}。",
        f"帳戶：{record.account_kind}／{record.portfolio_id}；namespace：未命名。",
        f"來源觀察：{_clock_or_missing(record.source_observed_at)}；"
        f"來源可用：{_clock_or_missing(record.source_available_at)}。",
        f"健康評估觀察：{_clock_or_missing(model.observed_at)}；"
        f"健康來源可用：{_clock_or_missing(model.health_source_available_at)}。",
        f"基準保存可用：{_clock_or_missing(model.baseline_saved_available_at)}；"
        f"評估收據保存可用：{_clock_or_missing(model.saved_receipt_available_at or opened.source.available_at)}。",
    ))


def _format_opened_diagnostics(opened: Any, record: SavedHealthSelection) -> str:
    source = opened.source
    model = opened.read_model
    return "｜".join((
        f"status={model.status}",
        f"account_kind={record.account_kind}",
        f"namespace={record.namespace or 'unnamed'}",
        f"portfolio_id={record.portfolio_id}",
        f"snapshot_id={record.snapshot_id}",
        f"snapshot_rows_sha256={record.snapshot_rows_sha256}",
        f"receipt_id={record.receipt_id}",
        f"receipt_sha256={record.receipt_sha256}",
        f"result_sha256={record.result_sha256}",
        f"source_observed_at={source.source_observed_at}",
        f"source_available_at={source.source_available_at or '未提供'}",
        f"baseline_saved_available_at={model.baseline_saved_available_at or '未提供'}",
        f"health_source_available_at={model.health_source_available_at or '未提供'}",
        f"health_observed_at={model.observed_at or '未提供'}",
        f"receipt_saved_available_at={model.saved_receipt_available_at or source.available_at}",
        f"source_witness_status={model.source_witness_status}",
        f"paper_snapshot_receipt_present={opened.paper_snapshot_receipt_present}",
    ))


def _format_selection_diagnostics(record: SavedHealthSelection) -> str:
    return "｜".join((
        f"receipt_id={record.receipt_id}",
        f"receipt_sha256={record.receipt_sha256}",
        f"result_sha256={record.result_sha256}",
        f"snapshot_id={record.snapshot_id}",
        f"snapshot_rows_sha256={record.snapshot_rows_sha256}",
        f"selected_position_id={record.selected_position_id or 'none'}",
        f"source_witness_status={record.source_witness_status}",
    ))


def _format_saved_position_status(record: SavedHealthSelection) -> str:
    return "\n".join((
        f"已保存所選評估與 position identity，可在下次開啟 Main 時回訪 {record.decision_date} 評估。",
        f"來源觀察：{_clock_or_missing(record.source_observed_at)}；"
        f"來源可用：{_clock_or_missing(record.source_available_at)}。",
        f"健康評估觀察：{_clock_or_missing(record.health_observed_at)}；"
        f"基準保存可用：{_clock_or_missing(record.baseline_saved_available_at)}；"
        f"評估收據保存可用：{_clock_or_missing(record.saved_receipt_available_at)}。",
    ))


def _clock_or_missing(value: str | None) -> str:
    return value if isinstance(value, str) and value else "未提供"
