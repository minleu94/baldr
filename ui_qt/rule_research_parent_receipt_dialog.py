"""明示選取的 parent 收據背景唯讀瀏覽；不開市場 DB 或 producer。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from app_module.rule_research_parent_capture import BoundedRuleResearchParentWriter
from app_module.rule_research_sample_readiness import read_saved_parent_rule_sample_readiness
from ui_qt.workers.task_worker import TaskWorker


def read_parent_receipt_selection(path: str, *, outcome_input_path: str = "", cancel_callback: Callable[[], bool] | None = None) -> dict[str, Any]:
    """只按所選 exact envelope 反查已驗證 roots，再沿原 readiness 重讀。"""
    cancel = cancel_callback or (lambda: False)
    selected = Path(path).absolute()
    if selected.name != "receipt.json" or selected.parent.parent.name != "parents":
        raise ValueError("請選擇保存母體 parents/<身份>/receipt.json")
    if cancel():
        return {"cancelled": True}
    writer = BoundedRuleResearchParentWriter(selected.parent.parent)
    package = writer.read(selected.parent.name)
    body = package["capture"]
    if str(selected.parent.parent.parent.resolve()) != body["capture_root"]:
        raise ValueError("parent_root_binding_mismatch")
    if cancel():
        return {"cancelled": True}
    ready, readiness_error = None, ""
    try:
        ready = read_saved_parent_rule_sample_readiness(
            body["snapshot_root"], body["capture_root"], universe_path=body["universe"]["source_ref"],
            identity_sha256=selected.parent.name,
        )
    except Exception as exc:
        # envelope 已驗證但 child/source readiness 拒絕；保留記錄中的發布結果。
        readiness_error = str(exc)
    # 第二次原子 envelope 檢查，拒絕讀取期間被另一份有效 parent 置換。
    if writer.read(selected.parent.name) != package:
        raise ValueError("parent_selection_changed_during_read")
    if cancel():
        return {"cancelled": True}
    outcome, outcome_error = None, ""
    if outcome_input_path and ready is not None:
        from app_module.rule_research_forward_outcome_reader import read_saved_parent_forward_outcome
        try:
            outcome = read_saved_parent_forward_outcome(path, outcome_input_path, cancel_callback=cancel)
            if outcome.get("cancelled"):
                return {"cancelled": True}
        except Exception as exc:
            outcome_error = str(exc)
    if writer.read(selected.parent.name) != package:
        raise ValueError("parent_selection_changed_during_read")
    if cancel():
        return {"cancelled": True}
    return {"cancelled": False, "readiness": ready, "readiness_error": readiness_error,
            "outcome": outcome, "outcome_error": outcome_error,
            "saved_capture": body, "methods": body["method_contracts"],
            "audit": {"selected_receipt": str(selected), "snapshot_root": body["snapshot_root"],
                      "universe_source": body["universe"], "method_hash": body["method_contracts_sha256"],
                      "source_binding": body["source_binding"], "receipt": package["receipt"]}}


_STATUS = {
    "published_complete": "已發布完整快照", "published_partial": "已發布部分快照",
    "unchanged": "既有快照未變", "not_started": "未開始", "interrupted_unknown": "中斷，發布結果待核對",
    "published": "樣本已保存", "duplicate": "沿用相同保存收據", "rejected": "拒絕保存",
    "captured": "樣本已核對", "snapshot_ready": "快照已備妥，樣本未完成",
    "pending": "尚未處理", "failed": "失敗", "cancelled": "已取消",
}

_MEMBER_STATUS = {"matched": "符合方法", "notmatched": "不符合方法", "unknown": "方法未知",
                  "excluded": "明示排除", "uncaptured": "未捕捉"}
_OUTCOME_STATUS = {"ready_research": "可看毛報酬", "pending": "未成熟", "unknown": "資料不足",
                   "unavailable": "缺價／停牌", "excluded": "排除", "uncaptured": "未捕捉"}


def _outcome_reasons(horizon: dict[str, Any]) -> str:
    """白話摘要保守呈現，原始理由留 tooltip／收合診斷。"""
    labels = []
    for reason in horizon["reason_codes"]:
        if reason == "horizon_not_matured_as_of":
            labels.append("尚未到結束日")
        elif "calendar" in reason or "decision_date" in reason:
            labels.append("日曆缺件或未可得")
        elif "not_available" in reason:
            labels.append("價格晚於評估日可得")
        elif "suspended" in reason:
            labels.append("端點停牌，不跳日")
        elif "benchmark" in reason:
            labels.append("基準缺件／基礎不相容")
        elif "price" in reason:
            labels.append("端點價格缺件或未知")
        elif "captured" in reason:
            labels.append("未捕捉，不當負樣本")
        elif "excluded" in reason:
            labels.append("依聲明排除")
    if horizon["calculation_status"] == "ready_research" and horizon["target"]["cost_status"] != "explicit":
        labels.append("成本未知或不完整")
    availability = horizon.get("input_availability", {}).get("as_of_status")
    if availability == "unknown":
        labels.append("來源可得時間未知")
    return "；".join(dict.fromkeys(labels)) or "僅端點研究"


class RuleResearchParentReceiptDialog(QDialog):
    """同一視窗重讀、合作取消及返回；generation 拒絕舊 callback。"""
    def __init__(self, parent: QWidget | None = None, *, reader: Callable[..., dict[str, Any]] = read_parent_receipt_selection) -> None:
        super().__init__(parent)
        self.setWindowTitle("保存研究母體")
        self.resize(1000, 720)
        self._reader = reader
        self._worker: TaskWorker | None = None
        self._generation = 0
        self._worker_generation = 0
        self._selected_path = ""
        self._outcome_input_path = ""
        self._outcome_projection: dict[str, Any] | None = None
        self._returned = False
        layout = QVBoxLayout(self)
        self.summary = QLabel("選擇本次保存的母體收據，唯讀核對母體與每批結果。")
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.summary)
        self.methods = QLabel("方法與分母尚未核對。")
        self.methods.setWordWrap(True)
        self.methods.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.methods)
        self.batch_table = QTableWidget(0, 4)
        self.batch_table.setHorizontalHeaderLabels(["批次", "成員", "快照產生結果", "樣本保存結果"])
        self.batch_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.batch_table.horizontalHeader().setStretchLastSection(True)
        self.result_tabs = QTabWidget()
        self.result_tabs.addTab(self.batch_table, "各批保存結果")
        outcome_page = QWidget()
        outcome_layout = QVBoxLayout(outcome_page)
        self.outcome_summary = QLabel()
        self.outcome_summary.setWordWrap(True)
        self.outcome_summary.setTextFormat(Qt.TextFormat.PlainText)
        self.outcome_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        outcome_layout.addWidget(self.outcome_summary)
        controls = QHBoxLayout()
        self.outcome_input_button = QPushButton("選擇研究結果輸入")
        self.outcome_input_button.clicked.connect(self.choose_outcome_input)
        controls.addWidget(self.outcome_input_button)
        self.outcome_clear_button = QPushButton("清除結果輸入")
        self.outcome_clear_button.clicked.connect(self.clear_outcome_input)
        controls.addWidget(self.outcome_clear_button)
        self.outcome_method = QComboBox()
        self.outcome_method.currentIndexChanged.connect(self._render_outcome_rows)
        controls.addWidget(self.outcome_method)
        self.outcome_horizon = QComboBox()
        self.outcome_horizon.addItems(["H5", "H10", "H20"])
        self.outcome_horizon.currentIndexChanged.connect(self._render_outcome_rows)
        controls.addWidget(self.outcome_horizon)
        outcome_layout.addLayout(controls)
        self.outcome_table = QTableWidget(0, 9)
        self.outcome_table.setHorizontalHeaderLabels([
            "股票", "方法判定", "研究結果", "結束日期", "毛報酬 bp", "成本後 bp",
            "毛超額 bp", "成本後超額 bp", "缺件／限制",
        ])
        self.outcome_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.outcome_table.horizontalHeader().setStretchLastSection(True)
        outcome_layout.addWidget(self.outcome_table, 1)
        self.outcome_note = QLabel(
            "符合方法不是交易入選；成本未知不補零。bp 為整數基點（100 bp＝1%）。"
            "只看決策日到 H5／H10／H20 收盤端點，不評估 MFE／MAE、期間停牌或可成交性；"
            "日曆是明示研究宣告，來源可得時間／官方 custody 未證明，不授 PIT、ML 或交易資格。"
        )
        self.outcome_note.setWordWrap(True)
        outcome_layout.addWidget(self.outcome_note)
        self.result_tabs.addTab(outcome_page, "H5／H10／H20 研究結果")
        layout.addWidget(self.result_tabs, 1)
        self._clear_outcome("資料不足：尚未選擇綁定本收據的日曆、價格、benchmark、成本及評估日輸入。")
        self.next_step = QLabel("瀏覽不產生資料。來源可得時間、交易日曆及成熟結果未知，不授訓練或正式資格。")
        self.next_step.setWordWrap(True)
        self.next_step.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.next_step)
        self.audit_button = QPushButton("展開來源與診斷")
        self.audit_button.setCheckable(True)
        self.audit_button.toggled.connect(self._toggle_audit)
        layout.addWidget(self.audit_button)
        self.audit = QTextEdit()
        self.audit.setReadOnly(True)
        self.audit.setVisible(False)
        layout.addWidget(self.audit)
        row = QHBoxLayout()
        self.choose_button = QPushButton("選擇保存收據")
        self.choose_button.clicked.connect(self.choose_receipt)
        row.addWidget(self.choose_button)
        self.reload_button = QPushButton("重讀／重試核對")
        self.reload_button.setEnabled(False)
        self.reload_button.clicked.connect(self.reload_receipt)
        row.addWidget(self.reload_button)
        self.cancel_button = QPushButton("取消讀取")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_read)
        row.addWidget(self.cancel_button)
        self.return_button = QPushButton("返回每日研究")
        self.return_button.clicked.connect(self.reject)
        row.addWidget(self.return_button)
        layout.addLayout(row)
        self._busy(False)

    def _toggle_audit(self, expanded: bool) -> None:
        self.audit.setVisible(expanded)
        self.audit_button.setText("收合來源與診斷" if expanded else "展開來源與診斷")

    def choose_receipt(self) -> None:
        if self._worker is not None:
            return
        path, _ = QFileDialog.getOpenFileName(self, "選擇保存母體收據", "", "母體收據 (receipt.json)")
        if path:
            self.read_receipt(path)

    def reload_receipt(self) -> None:
        if self._selected_path:
            self.read_receipt(self._selected_path)

    def choose_outcome_input(self) -> None:
        if self._worker is not None or not self._selected_path:
            return
        path, _ = QFileDialog.getOpenFileName(self, "選擇明示研究結果輸入", "", "研究輸入 (*.json)")
        if path:
            self._outcome_input_path = path
            self.reload_receipt()

    def clear_outcome_input(self) -> None:
        if self._worker is None:
            self._outcome_input_path = ""
            self.reload_receipt()

    def _clear_outcome(self, message: str) -> None:
        self._outcome_projection = None
        self.outcome_summary.setText(message)
        self.outcome_method.clear()
        self.outcome_table.setRowCount(0)

    def read_receipt(self, path: str) -> None:
        if self._worker is not None:
            return
        self._returned = False
        self._generation += 1
        generation = self._generation
        self._worker_generation = generation
        if path != self._selected_path:
            self._outcome_input_path = ""
        self._selected_path = path
        self.summary.setText("正在唯讀核對所選母體收據…")
        self.methods.setText("方法與分母核對中。")
        self.batch_table.setRowCount(0)
        self._clear_outcome("研究結果核對中；不沿用上次結果。")
        self.audit.clear()
        self.audit_button.setChecked(False)
        self.next_step.setText("等待有限來源讀取；可取消或返回，保存內容不會改動。")
        self._busy(True)
        kwargs = {"outcome_input_path": self._outcome_input_path} if self._outcome_input_path else {}
        worker = TaskWorker(self._reader, path, **kwargs)
        self._worker = worker
        worker.finished.connect(self._receive_result, Qt.ConnectionType.QueuedConnection)
        worker.error.connect(self._receive_error, Qt.ConnectionType.QueuedConnection)
        worker.cancelled.connect(self._receive_cancel, Qt.ConnectionType.QueuedConnection)
        worker.native_thread_finished.connect(self._receive_settled, Qt.ConnectionType.QueuedConnection)
        worker.start()

    @Slot(object)
    def _receive_result(self, result: dict[str, Any]) -> None:
        if self.sender() is self._worker:
            self._completed(self._worker_generation, result)

    @Slot(str)
    def _receive_error(self, error: str) -> None:
        if self.sender() is self._worker:
            self._failed(self._worker_generation, error)

    @Slot()
    def _receive_cancel(self) -> None:
        if self.sender() is self._worker:
            self._cancelled(self._worker_generation)

    @Slot()
    def _receive_settled(self) -> None:
        worker = self.sender()
        if isinstance(worker, TaskWorker):
            self._settled(worker)

    def _busy(self, busy: bool) -> None:
        self.choose_button.setEnabled(not busy)
        self.reload_button.setEnabled(not busy and bool(self._selected_path))
        self.cancel_button.setEnabled(busy)
        self.outcome_input_button.setEnabled(not busy and bool(self._selected_path))
        self.outcome_clear_button.setEnabled(not busy and bool(self._outcome_input_path))

    def _current(self, generation: int) -> bool:
        return generation == self._generation and not self._returned

    def _completed(self, generation: int, result: dict[str, Any]) -> None:
        if not self._current(generation):
            return
        if result.get("cancelled"):
            self._cancelled(generation)
            return
        r = result["readiness"]
        if r is None:
            body = result["saved_capture"]
            u = body["universe"]["value"]
            self._failed(generation, result["readiness_error"])
            self.summary.setText(
                f"{u['universe_id']} · 版本 {u['version']} · 保存資料日 {u['as_of_date']}\n"
                "保存包身份已核對，來源 readiness 核對失敗；母體完整資格未確認。\n"
                f"保存記錄的決策截止 {body['decision_cutoff']}；觀測 {body['as_of']}。"
            )
            self._render_batches(body["batches"])
            self.audit.setPlainText(json.dumps({"source": result["audit"], "saved_batches": body["batches"],
                "readiness_error": result["readiness_error"]}, ensure_ascii=False, indent=2))
            return
        complete = r["cohort_status"] == "complete"
        state = "完整保存" if complete else "保存未完整" + ("（已取消）" if r["cohort_status"] == "cancelled" else "")
        self.summary.setText(
            f"{r['universe_id']} · 版本 {r['version']} · 資料日 {r['decision_date']}\n"
            f"{state}：{r['batches_count']} 批，聲明 {r['represented_denominator']} 名成員；"
            f"已捕捉 {r['captured_member_count']}，未捕捉 {r['uncaptured_member_count']}。\n"
            f"決策截止 {r['decision_cutoff']}；本次觀測 {r['as_of']}。"
        )
        lines = []
        contracts = {c["method_id"]: c for c in result["methods"].values()}
        for c in r["method_counts"]:
            contract = contracts[c["method_id"]]
            lines.append(f"收盤價高於 MA{contract['parameters']['window']} · 版本 {contract['version']}：符合方法 {c['matched']}／不符合 {c['notmatched']}／未知 {c['unknown']}／排除 {c['excluded']}／未捕捉 {c['uncaptured']}")
        self.methods.setText("\n".join(lines))
        self._render_batches(r["batches"])
        self.next_step.setText(
            ("母體保存已核對；可重讀相同收據。" if complete else
             "母體未完整；重讀僅核對保存內容。先查看各批結果；相同來源及固定觀測時刻可由原保存工具重試，來源／方法變更需新的明示保存。保存中斷請保留舊件，依操作手冊使用新的隔離位置。")
            + " 來源可得時間、交易日曆與成熟結果未知；未捕捉不是負樣本，不授PIT、訓練或正式資格。"
        )
        self.audit.setPlainText(json.dumps({"source": result["audit"], "readiness": r}, ensure_ascii=False, indent=2))
        outcome = result.get("outcome")
        if outcome is not None:
            self._render_outcome(outcome["projection"], contracts)
            self.audit.setPlainText(self.audit.toPlainText() + "\n" + json.dumps({"forward_outcome": outcome}, ensure_ascii=False, indent=2))
            self.next_step.setText("母體保存與明示研究輸入已核對；H5／H10／H20 的可看報酬、資料不足與未成熟分列於結果頁。"
                                   "來源可得時間與官方日曆／custody 仍未證明；未捕捉不是負樣本，不授 PIT、訓練或交易資格。")
        else:
            self._clear_outcome("資料不足：研究輸入核對失敗，請核對原收據及輸入版本後重試。" if result.get("outcome_error") else
                                "資料不足：尚未選擇綁定本收據的明示研究輸入；H5／H10／H20 未評估。")
            if result.get("outcome_error"):
                self.audit.setPlainText(self.audit.toPlainText() + "\n" + str(result["outcome_error"]))

    def _render_outcome(self, projection: dict[str, Any], contracts: dict[str, Any]) -> None:
        self._outcome_projection = projection
        self.outcome_method.blockSignals(True)
        self.outcome_method.clear()
        lines = [f"決策日 {projection['decision_date']} · 評估截至 {projection['as_of_date']} · "
                 f"每方法完整分母 {projection['population']['represented_denominator']}（含排除／未捕捉）；正式入選未知。"]
        for method_id in projection["population"]["method_state_counts"]:
            label = "MA" + str(contracts[method_id]["parameters"]["window"])
            self.outcome_method.addItem(label, method_id)
            members = [m for m in projection["members"] if m["method_id"] == method_id]
            for index, horizon in enumerate(("H5", "H10", "H20")):
                counts: dict[str, int] = {}
                for member in members:
                    state = member["horizons"][index]["calculation_status"]
                    counts[state] = counts.get(state, 0) + 1
                lines.append(label + " " + horizon + "：" + "／".join(
                    f"{_OUTCOME_STATUS.get(state, state)} {count}" for state, count in counts.items()))
        cost = projection["cost_policy"]
        if cost is None:
            lines.append("成本未知：毛報酬可判讀時保留，成本後及成本後超額不評估。")
        else:
            fields = ("target_entry_bp", "target_exit_bp", "benchmark_entry_bp", "benchmark_exit_bp")
            values = ["未知" if cost[f] is None else str(cost[f]) for f in fields]
            lines.append(f"成本版本 {cost['version']} · 標的進／出 {values[0]}/{values[1]} bp · 基準進／出 {values[2]}/{values[3]} bp。")
        self.outcome_summary.setText("\n".join(lines))
        self.outcome_method.blockSignals(False)
        self._render_outcome_rows()

    def _render_outcome_rows(self, *_args: Any) -> None:
        projection = self._outcome_projection
        if projection is None:
            return
        rows = [m for m in projection["members"] if m["method_id"] == self.outcome_method.currentData()]
        self.outcome_table.setRowCount(len(rows))
        index = self.outcome_horizon.currentIndex()
        for row, member in enumerate(rows):
            horizon = member["horizons"][index]
            def bp(measure: dict[str, Any]) -> str:
                value = measure["integer_bp_half_even"]
                return "—" if value is None else str(value)
            reasons = _outcome_reasons(horizon)
            values = [member["stock_code"], _MEMBER_STATUS[member["member_state"]],
                      _OUTCOME_STATUS.get(horizon["calculation_status"], "未知"),
                      horizon["expected_end_date"] or "未知", bp(horizon["target"]["gross_return"]),
                      bp(horizon["target"]["net_return"]), bp(horizon["comparison"]["gross_excess_return"]),
                      bp(horizon["comparison"]["net_excess_return"]), reasons]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(json.dumps({"member_reason": member["member_reason"], "horizon": horizon}, ensure_ascii=False))
                self.outcome_table.setItem(row, col, item)
        self.outcome_table.resizeColumnsToContents()

    def _render_batches(self, batches: list[dict[str, Any]]) -> None:
        self.batch_table.setRowCount(len(batches))
        for row, b in enumerate(batches):
            values = [b["batch_id"], f"{len(b['included_stock_codes'])}納入＋{len(b['excluded_stock_codes'])}排除",
                      _STATUS.get(b["production_status"], "結果待核對"),
                      _STATUS.get(b["sample_capture_status"], "結果待核對")]
            for col, value in enumerate(values):
                self.batch_table.setItem(row, col, QTableWidgetItem(value))
        self.batch_table.resizeColumnsToContents()

    def _failed(self, generation: int, error: str) -> None:
        if not self._current(generation):
            return
        self.summary.setText("保存來源核對失敗；目前不能確認母體完整度。")
        self.methods.setText("方法與分母未核對，不借目前資料補齊。")
        self.batch_table.setRowCount(0)
        self._clear_outcome("資料不足：保存來源未核對，H5／H10／H20 不評估。")
        self.next_step.setText("核對選取的母體收據、原配置與保存來源；可按重讀／重試核對，或返回改選收據。保留原件，不刪資料繞過。此錯誤不代表producer沒有發布快照。")
        self.audit.setPlainText(error)

    def _cancelled(self, generation: int) -> None:
        if self._current(generation):
            self.summary.setText("已取消讀取；保存內容保留。")
            self._clear_outcome("已取消研究結果讀取；保存內容保留。")
            self.next_step.setText("等待背景讀取安全結束後，可重讀相同收據或改選。")

    def cancel_read(self) -> None:
        if self._worker is None:
            return
        self._generation += 1
        self._clear_outcome("已取消研究結果讀取；不套用晚到結果。")
        self.summary.setText("已取消顯示，等待有限背景讀取安全返回；保存內容保留。")
        self.next_step.setText("背景讀取結束後可重讀；取消不表示producer或capture未曾保存。")
        self.cancel_button.setEnabled(False)
        self._worker.cancel(cooperative=True, wait=False)

    def _settled(self, worker: TaskWorker) -> None:
        if self._worker is worker:
            self._worker = None
            worker.deleteLater()
            self._busy(False)

    def reject(self) -> None:
        self.cancel_read()
        self._returned = True
        self._generation += 1
        super().reject()
