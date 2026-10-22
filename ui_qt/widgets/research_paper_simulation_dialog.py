"""保存研究原件起始的明確 Paper 模擬確認流程。"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Callable, Protocol, TYPE_CHECKING
from uuid import uuid4

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from app_module.research_timeline_dtos import ResearchTimelineEntry
from ui_qt.workers.task_worker import TaskWorker

if TYPE_CHECKING:
    from app_module.research_paper_producer import (
        HumanConfirmedPaperIntent,
        VerifiedPaperContext,
    )


class ResearchPaperEvidenceBindingReader(Protocol):
    """讀取並在送出前重新核對保存研究所需的 Paper 證據。"""

    def preview(self, entry: ResearchTimelineEntry) -> VerifiedPaperContext: ...

    def verify(
        self,
        entry: ResearchTimelineEntry,
        intent: HumanConfirmedPaperIntent,
    ) -> VerifiedPaperContext: ...


class ResearchPaperProducerLike(Protocol):
    def produce(self, entry: ResearchTimelineEntry, intent: HumanConfirmedPaperIntent) -> object: ...


def _abbreviated(value: object) -> str:
    text = str(value or "")
    if text.startswith("sha256:"):
        return text[:19] + "…"
    return text or "未提供"


class ResearchPaperSimulationDialog(QDialog):
    """先顯示純預覽，再由明確人工確認呼叫既有 Paper producer。"""

    paperProduced = Signal(object)
    returnToEntryRequested = Signal(object)
    paperStatusRequested = Signal()

    def __init__(
        self,
        entry: ResearchTimelineEntry,
        provider: ResearchPaperEvidenceBindingReader | None,
        producer_factory: Callable[[HumanConfirmedPaperIntent], ResearchPaperProducerLike] | None,
        parent: QWidget | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__(parent)
        self.entry = entry
        self.provider = provider
        self.producer_factory = producer_factory
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._context: object | None = None
        self._intent: object | None = None
        self._preview_values: tuple[object, object] | None = None
        self._confirmation_frozen = False
        self._worker: TaskWorker | None = None
        self._operation = ""
        self._generation = 0
        self._closing = False
        self._succeeded = False

        self.setObjectName("researchPaperSimulationDialog")
        self.setWindowTitle("從保存研究預覽 Paper 模擬")
        self.resize(760, 740)
        root = QVBoxLayout(self)
        intro = QLabel(
            "此流程只產生 Paper 模擬事件，不建立帳戶、不連接券商，也不會送出真實委託。"
            "必須由你明選證據、方向與整手數量，並再次確認才會保存。",
            self,
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        self.status_label = QLabel("尚未核驗來源；目前沒有可用的 Paper 預覽。", self)
        self.status_label.setObjectName("researchPaperSimulationStatus")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.preview_source_button = QPushButton("重新核驗這筆研究與 Paper 證據", self)
        self.preview_source_button.setObjectName("researchPaperSimulationVerifySource")
        root.addWidget(self.preview_source_button)

        form = QFormLayout()
        self.account_combo = QComboBox(self)
        self.account_combo.setObjectName("researchPaperSimulationAccount")
        self.account_combo.addItem("請明確選擇已核驗 Paper 帳戶", None)
        self.strategy_combo = QComboBox(self)
        self.strategy_combo.setObjectName("researchPaperSimulationStrategy")
        self.strategy_combo.addItem("請明確選擇已核驗策略版本", None)
        self.side_combo = QComboBox(self)
        self.side_combo.setObjectName("researchPaperSimulationSide")
        self.side_combo.addItem("請選擇買進或賣出", None)
        self.side_combo.addItem("買進", "buy")
        self.side_combo.addItem("賣出", "sell")
        self.quantity_edit = QLineEdit(self)
        self.quantity_edit.setObjectName("researchPaperSimulationQuantity")
        self.quantity_edit.setPlaceholderText("輸入股數；每筆須為 1,000 股整數倍")
        self.quantity_edit.setValidator(QIntValidator(1, 2_000_000_000, self))
        self.event_date_label = QLabel("尚無經核驗的行情日期", self)
        self.event_date_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("Paper 帳戶命名空間", self.account_combo)
        form.addRow("策略版本", self.strategy_combo)
        form.addRow("方向", self.side_combo)
        form.addRow("數量（股）", self.quantity_edit)
        form.addRow("行情事件日", self.event_date_label)
        root.addLayout(form)

        self.evidence_details = QPlainTextEdit(self)
        self.evidence_details.setObjectName("researchPaperSimulationEvidenceDetails")
        self.evidence_details.setReadOnly(True)
        self.evidence_details.setPlaceholderText("成功核驗後顯示帳戶、現金、同日行情與成本證據。")
        self.evidence_details.setMaximumBlockCount(80)
        root.addWidget(self.evidence_details, 1)

        self.preview_summary = QPlainTextEdit(self)
        self.preview_summary.setObjectName("researchPaperSimulationPreviewSummary")
        self.preview_summary.setReadOnly(True)
        self.preview_summary.setPlaceholderText("選取帳戶、策略、方向與股數後按「預覽模擬」。")
        self.preview_summary.setMaximumBlockCount(80)
        root.addWidget(self.preview_summary, 1)

        actions = QHBoxLayout()
        self.preview_button = QPushButton("預覽模擬", self)
        self.preview_button.setObjectName("researchPaperSimulationPreview")
        self.confirm_button = QPushButton("我確認這筆 Paper 模擬", self)
        self.confirm_button.setObjectName("researchPaperSimulationConfirm")
        self.confirm_button.setEnabled(False)
        self.retry_button = QPushButton("以同一筆確認重試", self)
        self.retry_button.setObjectName("researchPaperSimulationRetry")
        self.retry_button.setEnabled(False)
        self.return_button = QPushButton("返回原研究", self)
        self.return_button.setObjectName("researchPaperSimulationReturn")
        self.paper_status_button = QPushButton("查看既有 Paper", self)
        self.paper_status_button.setObjectName("researchPaperSimulationStatusRoute")
        actions.addWidget(self.preview_button)
        actions.addWidget(self.confirm_button)
        actions.addWidget(self.retry_button)
        actions.addWidget(self.return_button)
        actions.addWidget(self.paper_status_button)
        root.addLayout(actions)

        self.preview_source_button.clicked.connect(self._start_source_preview)
        self.preview_button.clicked.connect(self._start_simulation_preview)
        self.confirm_button.clicked.connect(self._confirm)
        self.retry_button.clicked.connect(self._confirm)
        self.return_button.clicked.connect(self._return_to_entry)
        self.paper_status_button.clicked.connect(self._request_paper_status)
        self.account_combo.currentIndexChanged.connect(self._input_changed)
        self.strategy_combo.currentIndexChanged.connect(self._input_changed)
        self.side_combo.currentIndexChanged.connect(self._input_changed)
        self.quantity_edit.textChanged.connect(self._input_changed)
        self._set_inputs_enabled(False)
        if self.provider is None:
            self.status_label.setText("Paper 證據讀取器未設定；流程已安全停用。")
            self.preview_source_button.setEnabled(False)
        if self.producer_factory is None:
            self.status_label.setText("Paper producer 未設定；可檢視來源，但不能確認或保存模擬。")

    def _set_inputs_enabled(self, enabled: bool) -> None:
        for widget in (self.account_combo, self.strategy_combo, self.side_combo,
                       self.quantity_edit, self.preview_button):
            widget.setEnabled(enabled and self._worker is None and not self._closing)

    def _start_worker(self, operation: str, task: Callable[[], object], receive: Callable[[object], None]) -> None:
        if self._closing or self._worker is not None:
            self.status_label.setText("上一項工作尚未自然結束；未送出新工作。")
            return
        self._generation += 1
        generation = self._generation
        worker = TaskWorker(task)
        self._worker = worker
        self._operation = operation
        self._sync_controls()
        worker.finished.connect(
            lambda value: receive(value) if generation == self._generation and not self._closing else None
        )
        worker.error.connect(
            lambda message: self._on_worker_error(generation, message)
        )
        worker.native_thread_finished.connect(lambda: self._release_worker(worker))
        worker.start()

    def _start_source_preview(self) -> None:
        if self.provider is None:
            self.status_label.setText("缺少 Paper 證據讀取器；未核驗來源。")
            return
        self._invalidate_preview()
        provider = self.provider
        entry = self.entry
        self.status_label.setText("正在背景核驗研究原件、帳戶、現金及同日行情…")

        def task() -> object:
            return provider.preview(entry)

        self._start_worker("source", task, self._receive_source_preview)

    def _receive_source_preview(self, value: object) -> None:
        try:
            candidate = getattr(value, "candidate")
            binding = getattr(value, "binding")
            cash = getattr(value, "cash")
            marks = getattr(value, "marks")
            if getattr(candidate, "stock_code", None) != self.entry.stock_code:
                raise ValueError("核驗候選股票與所選研究原件不符")
            matching = tuple(mark for mark in marks if getattr(mark, "stock_code", None) == self.entry.stock_code)
            if len(matching) != 1:
                raise ValueError("沒有唯一且同股的行情事件；不能推定行情或日期")
            mark = matching[0]
            event_date = getattr(mark, "event_date", None)
            if not isinstance(event_date, str) or not event_date:
                raise ValueError("行情來源沒有明確 event_date")
            policy = getattr(value, "policy")
            strategy_id = getattr(binding, "strategy_version_id", "")
            account_namespace = getattr(binding, "account_namespace", "")
            if not strategy_id or not account_namespace:
                raise ValueError("核驗結果缺少明確帳戶或策略版本身份")
        except Exception as exc:
            self._context = None
            self._set_inputs_enabled(False)
            self.status_label.setText(f"Paper 證據不完整，流程已停用：{exc}")
            return

        self._context = value
        self.event_date_label.setText(event_date)
        for combo in (self.account_combo, self.strategy_combo):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("請明確選擇", None)
            combo.blockSignals(False)
        self.account_combo.addItem(account_namespace, account_namespace)
        self.strategy_combo.addItem(strategy_id, strategy_id)
        self.evidence_details.setPlainText("\n".join((
            f"研究原件：{self.entry.kind}／{self.entry.record_id}／{self.entry.stock_code}",
            f"研究來源：{self.entry.source_identity or '未提供'}",
            f"候選身份：{_abbreviated(getattr(candidate, 'identity_sha256', ''))}",
            f"帳戶命名空間：{account_namespace}",
            f"帳戶 binding：{_abbreviated(getattr(binding, 'binding_sha256', ''))}",
            f"策略版本：{strategy_id}",
            f"Paper 現金：{getattr(cash, 'amount', '未提供')} {getattr(cash, 'currency', '')}",
            f"現金來源：{getattr(cash, 'source_id', '未提供')}／{_abbreviated(getattr(cash, 'source_sha256', ''))}",
            f"行情事件日：{event_date}",
            f"標記價格：{getattr(mark, 'mark_price', '未提供')} {getattr(mark, 'currency', '')}",
            f"執行參考價：{getattr(mark, 'execution_reference_price', '未提供')}",
            f"行情來源：{getattr(mark, 'source_id', '未提供')}／{_abbreviated(getattr(mark, 'source_sha256', ''))}",
            f"策略政策：{getattr(value, 'policy_use_id', '')}／{getattr(value, 'policy_artifact_sha256', '')[:19]}…",
            f"交易成本：{getattr(value, 'cost_use_id', '')}；佣金 {getattr(value, 'cost_commission_bp_per_side', '')} bp/邊，"
            f"滑價 {getattr(value, 'cost_slippage_bp_per_side', '')} bp/邊，賣出稅 {getattr(value, 'cost_sell_tax_bp', '')} bp，"
            f"最低手續費 {getattr(value, 'cost_minimum_fee', '')} TWD",
            "限制：此為 Paper 模擬證據，不代表真實帳戶、即時行情、可交易資格或券商委託。",
        )))
        self._set_inputs_enabled(True)
        self.status_label.setText("來源已核驗。請明選帳戶、策略、方向與股數，再查看完整模擬預覽。")
        self._sync_controls()

    def _input_changed(self, *_args: object) -> None:
        if self._intent is not None:
            self._invalidate_preview()
            self.status_label.setText("輸入已變更；舊確認已失效。請重新預覽並核對新模擬。")
        self._sync_controls()

    def _invalidate_preview(self) -> None:
        self._intent = None
        self._preview_values = None
        self._confirmation_frozen = False
        self.confirm_button.setEnabled(False)
        self.retry_button.setEnabled(False)
        self.preview_summary.clear()

    def _validated_inputs(self) -> tuple[str, str, str, int, str] | None:
        if self._context is None:
            return None
        account = self.account_combo.currentData()
        strategy = self.strategy_combo.currentData()
        side = self.side_combo.currentData()
        raw_quantity = self.quantity_edit.text().strip()
        if not isinstance(account, str) or not account or not isinstance(strategy, str) or not strategy:
            return None
        if side not in {"buy", "sell"} or not raw_quantity.isdigit():
            return None
        quantity = int(raw_quantity)
        if quantity < 1000 or quantity % 1000:
            return None
        marks = tuple(getattr(self._context, "marks", ()))
        matching = tuple(mark for mark in marks if getattr(mark, "stock_code", None) == self.entry.stock_code)
        if len(matching) != 1:
            return None
        event_date = getattr(matching[0], "event_date", None)
        return (account, strategy, side, quantity, event_date)

    def _start_simulation_preview(self) -> None:
        values = self._validated_inputs()
        if values is None:
            self.status_label.setText("請明選帳戶、策略、方向，並輸入至少 1,000 股的整數倍。")
            self._invalidate_preview()
            return
        if self._worker is not None:
            return
        account, _strategy, side, quantity, event_date = values
        context = self._context
        entry = self.entry
        confirmed_at = self._clock()
        if confirmed_at.tzinfo is None or confirmed_at.utcoffset() is None:
            self.status_label.setText("UTC clock 無有效時區；未建立預覽意圖。")
            return
        confirmed_at = confirmed_at.astimezone(timezone.utc).isoformat()
        operation_id = f"research-paper-operation:{uuid4().hex}"
        confirmation_id = f"research-paper-confirmation:{uuid4().hex}"
        self.status_label.setText("正在以既有 Paper 純預覽函式計算費用與帳戶變化…")

        def task() -> object:
            from app_module.research_paper_producer import (
                HumanConfirmedPaperIntent,
                research_candidate_identity_sha256,
                verified_context_fingerprint_sha256,
            )
            from app_module.research_paper_producer import preview_research_paper_simulation

            intent = HumanConfirmedPaperIntent(
                operation_id=operation_id,
                confirmation_id=confirmation_id,
                candidate_identity_sha256=research_candidate_identity_sha256(entry),
                account_namespace=account,
                binding_sha256=getattr(getattr(context, "binding"), "binding_sha256"),
                evidence_fingerprint_sha256=verified_context_fingerprint_sha256(context),
                side=side,
                quantity=quantity,
                event_date=event_date,
                confirmed_at=confirmed_at,
            )
            fill, transition = preview_research_paper_simulation(entry, intent, context)
            return intent, fill, transition

        self._start_worker("simulation_preview", task, self._receive_simulation_preview)

    def _receive_simulation_preview(self, value: object) -> None:
        if not isinstance(value, tuple) or len(value) != 3:
            self.status_label.setText("Paper 純預覽回傳格式不符；不能確認或保存。")
            return
        intent, fill, transition = value
        self._intent = intent
        self._preview_values = (fill, transition)
        self._confirmation_frozen = False
        self.preview_summary.setPlainText("\n".join((
            f"方向與數量：{'買進' if getattr(intent, 'side', '') == 'buy' else '賣出'} {getattr(intent, 'quantity', '')} 股",
            f"行情日期：{getattr(intent, 'event_date', '')}",
            f"標記價格：{getattr(next((m for m in getattr(self._context, 'marks', ()) if getattr(m, 'stock_code', None) == self.entry.stock_code), None), 'mark_price', '未提供')} TWD",
            f"執行參考價：{getattr(fill, 'reference_price', '未提供')} TWD",
            f"模擬成交價：{getattr(fill, 'fill_price', '未提供')} TWD",
            f"佣金：{getattr(fill, 'commission', '未提供')} TWD",
            f"交易稅：{getattr(fill, 'tax', '未提供')} TWD",
            f"滑價成本：{getattr(fill, 'slippage_cost', '未提供')} TWD",
            f"模擬後現金：{getattr(transition, 'post_cash', '未提供')} TWD",
            f"Paper 帳戶：{getattr(intent, 'account_namespace', '')}",
            f"候選身份：{_abbreviated(getattr(intent, 'candidate_identity_sha256', ''))}",
            f"證據版本：{_abbreviated(getattr(intent, 'evidence_fingerprint_sha256', ''))}",
            f"確認編號：{getattr(intent, 'confirmation_id', '')}",
            "此頁只顯示研究用途的模擬結果；沒有建立帳戶或送出券商委託。",
        )))
        self.confirm_button.setEnabled(self.producer_factory is not None)
        self.retry_button.setEnabled(False)
        self.status_label.setText("預覽完成。核對日期、價格、成本及現金後，才按下明確確認按鈕。")

    def _confirm(self) -> None:
        intent = self._intent
        if intent is None or self._preview_values is None:
            self.status_label.setText("沒有有效且未失效的預覽意圖；未呼叫 Paper producer。")
            return
        if self.producer_factory is None:
            self.status_label.setText("Paper producer 未設定；沒有保存模擬。")
            return
        if not self._confirmation_frozen:
            confirmed_at = self._clock()
            if confirmed_at.tzinfo is None or confirmed_at.utcoffset() is None:
                self.status_label.setText("UTC clock 無有效時區；預覽仍未確認，也未呼叫 Paper producer。")
                return
            try:
                intent = replace(
                    intent,
                    confirmed_at=confirmed_at.astimezone(timezone.utc).isoformat(),
                )
            except (TypeError, ValueError) as exc:
                self._invalidate_preview()
                self.status_label.setText(
                    f"確認時間已跨行情事件日或無效；舊預覽已清除，請重新核驗來源：{exc}。未建立 Paper producer。"
                )
                self._sync_controls()
                return
            self._intent = intent
            self._confirmation_frozen = True
            self.preview_summary.appendPlainText(
                f"明確確認時間（UTC）：{intent.confirmed_at}"
            )
        entry = self.entry
        factory = self.producer_factory
        provider = self.provider
        displayed_preview = self._preview_values
        self.status_label.setText("已明確確認；正在背景重核來源並保存同一筆 Paper 模擬…")

        def task() -> object:
            if provider is None:
                raise RuntimeError("Paper evidence reader is not configured")
            verified = provider.verify(entry, intent)
            from app_module.research_paper_producer import verified_context_fingerprint_sha256

            if verified_context_fingerprint_sha256(verified) != getattr(
                intent, "evidence_fingerprint_sha256", None
            ):
                raise RuntimeError("來源或帳戶證據已變更；請重新核驗並產生新預覽")
            from app_module.research_paper_producer import preview_research_paper_simulation

            final_preview = preview_research_paper_simulation(entry, intent, verified)
            if displayed_preview is None or not _same_visible_preview(displayed_preview, final_preview):
                raise RuntimeError("最終確認的 Paper 預覽與畫面金額不同；未保存")
            producer = factory(intent)
            return producer.produce(entry, intent)

        self._start_worker("produce", task, self._receive_production)

    def _receive_production(self, value: object) -> None:
        self._succeeded = True
        self.confirm_button.setEnabled(False)
        self.retry_button.setEnabled(False)
        self.status_label.setText("Paper 模擬已保存；原研究原件身份保留。可返回原研究或前往既有 Paper 頁面。")
        self.paperProduced.emit(value)
        return_entry = getattr(value, "return_entry", self.entry)
        self.returnToEntryRequested.emit(return_entry)

    def _on_worker_error(self, generation: int, message: str) -> None:
        if generation != self._generation or self._closing:
            return
        detail = str(message).splitlines()[0][:500]
        if self._operation == "produce" and self._intent is not None:
            self.confirm_button.setEnabled(False)
            self.retry_button.setEnabled(self.producer_factory is not None)
            self.status_label.setText(
                f"Paper 保存失敗或結果未確認：{detail}。可重試同一不可變確認意圖；不要改數量或方向。"
            )
        else:
            self._invalidate_preview()
            if self._operation == "source":
                self._context = None
                self._set_inputs_enabled(False)
            self.status_label.setText(f"{detail}；未使用其他來源或預設值。")

    def _release_worker(self, worker: TaskWorker) -> None:
        if self._worker is worker:
            self._worker = None
            self._operation = ""
            self._sync_controls()
        worker.deleteLater()

    def _sync_controls(self) -> None:
        busy = self._worker is not None
        retry_pending = "Paper 保存失敗或結果未確認" in self.status_label.text()
        self.preview_source_button.setEnabled(self.provider is not None and not busy and not self._closing)
        inputs_enabled = self._context is not None and not busy and not self._closing and not self._succeeded
        for widget in (self.account_combo, self.strategy_combo, self.side_combo, self.quantity_edit):
            widget.setEnabled(inputs_enabled)
        self.preview_button.setEnabled(inputs_enabled)
        self.confirm_button.setEnabled(
            inputs_enabled and self._intent is not None and self._preview_values is not None
            and self.producer_factory is not None and not retry_pending
        )
        self.retry_button.setEnabled(
            inputs_enabled and self._operation == "" and self._intent is not None
            and self.producer_factory is not None and retry_pending
        )
        self.return_button.setEnabled(not busy and not self._closing)
        self.paper_status_button.setEnabled(not busy and not self._closing)

    def _return_to_entry(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self.status_label.setText("背景工作尚未自然結束；視窗暫不離開。")
            return
        self.returnToEntryRequested.emit(self.entry)
        self.reject()

    def _request_paper_status(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self.status_label.setText("背景工作尚未自然結束；請等待完成後再查看 Paper 頁面。")
            return
        if self._closing:
            return
        self.paperStatusRequested.emit()

    def reject(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self.status_label.setText("背景工作尚未自然結束；請等待結果後再離開。")
            return
        self._closing = True
        self._generation += 1
        super().reject()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._worker is not None and self._worker.isRunning():
            self.status_label.setText("背景工作尚未自然結束；視窗暫不關閉。")
            event.ignore()
            return
        self._closing = True
        self._generation += 1
        super().closeEvent(event)


def _same_visible_preview(
    displayed: tuple[object, object],
    final: tuple[object, object],
) -> bool:
    """確認最後確認意圖的價格、費用及帳戶變化與畫面相同。"""
    old_fill, old_transition = displayed
    new_fill, new_transition = final
    fill_fields = (
        "stock_code", "side", "requested_quantity", "filled_quantity",
        "reference_price", "fill_price", "commission", "tax", "slippage_cost",
    )
    transition_fields = (
        "post_cash", "post_total_value", "post_positions", "pre_cash", "pre_total_value",
    )
    return (
        all(getattr(old_fill, name, None) == getattr(new_fill, name, None) for name in fill_fields)
        and all(
            getattr(old_transition, name, None) == getattr(new_transition, name, None)
            for name in transition_fields
        )
    )


__all__ = [
    "ResearchPaperEvidenceBindingReader",
    "ResearchPaperProducerLike",
    "ResearchPaperSimulationDialog",
]
