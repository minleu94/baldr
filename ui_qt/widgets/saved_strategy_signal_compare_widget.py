"""在原Registry明選run後查看逐日進場意圖，不混用績效比較。"""
from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from app_module.saved_strategy_rule_card import metadata_sha256
from app_module.saved_strategy_signal_comparison import SavedSignalComparison, read_saved_strategy_signal_comparison
from ui_qt.widgets.table_style import apply_financial_table_style
from ui_qt.workers.task_worker import TaskWorker


class SavedStrategySignalCompareWidget(QWidget):
    PAGE_SIZE = 100

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self._service = service
        self._selection = ()
        self._pins = ()
        self._generation = 0
        self._active_generation = 0
        self._worker = None
        self._closed = False
        self.result = None
        self._page = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.compare_button = QPushButton("逐日策略訊號對照")
        self.compare_button.setEnabled(False)
        self.compare_button.clicked.connect(self.compare)
        row.addWidget(self.compare_button)
        self.status = QLabel("選2至5筆不同單股策略；只讀原保存進場意圖，不作績效排名。")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        row.addWidget(self.status, 1)
        self.view_result_button = QPushButton("開啟已讀對照")
        self.view_result_button.setEnabled(False)
        row.addWidget(self.view_result_button)
        layout.addLayout(row)
        self.result_dialog = QDialog(self)
        self.result_dialog.setWindowTitle("原保存策略的逐日訊號對照")
        self.result_dialog.resize(1100, 650)
        self.result_dialog.setMinimumSize(760, 420)
        result_layout = QVBoxLayout(self.result_dialog)
        self.detail_status = QLabel()
        self.detail_status.setTextFormat(Qt.PlainText)
        self.detail_status.setWordWrap(True)
        result_layout.addWidget(self.detail_status)
        self.view_result_button.clicked.connect(self.result_dialog.show)
        self.result_controls = QWidget()
        controls = QHBoxLayout(self.result_controls)
        controls.setContentsMargins(0, 0, 0, 0)
        self.entry_only = QCheckBox("只看有進場意圖的日期")
        self.entry_only.toggled.connect(self._reset_page)
        controls.addWidget(self.entry_only)
        self.strategy_combo = QComboBox()
        self.strategy_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.strategy_combo.setMinimumContentsLength(12)
        self.strategy_combo.setMaximumWidth(400)
        controls.addWidget(self.strategy_combo, 1)
        self.rules_button = QPushButton("查看原保存規則")
        self.rules_button.clicked.connect(self.open_rules)
        controls.addWidget(self.rules_button)
        self.previous_button = QPushButton("上一頁")
        self.next_button = QPushButton("下一頁")
        self.previous_button.clicked.connect(lambda: self._change_page(-1))
        self.next_button.clicked.connect(lambda: self._change_page(1))
        self.page_label = QLabel()
        controls.addWidget(self.previous_button)
        controls.addWidget(self.page_label)
        controls.addWidget(self.next_button)
        result_layout.addWidget(self.result_controls)
        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setMinimumHeight(200)
        apply_financial_table_style(self.table)
        result_layout.addWidget(self.table, 1)
        self.result_controls.hide()
        self.table.hide()

    def set_selection(self, runs) -> None:
        pins = tuple((run.run_id, metadata_sha256(run)) for run in runs)
        if pins == self._pins:
            return
        self._pins = pins
        self._selection = tuple(deepcopy(run) for run in runs)
        self._generation += 1
        if self._worker is not None:
            self._worker.cancel(cooperative=True, wait=False)
        self.result = None
        self.result_dialog.hide()
        self.view_result_button.setEnabled(False)
        self.table.clearContents()
        self.table.setRowCount(0)
        self.table.hide()
        self.result_controls.hide()
        self.status.setText("已選" + str(len(runs)) + "筆；選2至5筆不同單股策略後按對照。訊號不是成交。")
        self._update_button()

    def _update_button(self) -> None:
        self.compare_button.setEnabled(not self._closed and self._worker is None and 2 <= len(self._selection) <= 5)

    def compare(self) -> None:
        if not self.compare_button.isEnabled():
            return
        self._generation += 1
        self._active_generation = generation = self._generation
        selection = deepcopy(self._selection)
        self.result = None
        self.result_dialog.hide()
        self.view_result_button.setEnabled(False)
        self.table.hide()
        self.result_controls.hide()
        def read(cancel_callback=None):
            return {"generation": generation, "result": read_saved_strategy_signal_comparison(
                self._service, selection, check_cancel=cancel_callback)}
        self._worker = TaskWorker(read)
        self._worker.finished.connect(self._loaded)
        self._worker.error.connect(self._failed)
        self._worker.native_thread_finished.connect(self._finished)
        self._worker.native_thread_finished.connect(self._worker.deleteLater)
        self.status.setText("正在核對原保存價量、規則與逐日訊號…")
        self._update_button()
        self._worker.start()

    def _loaded(self, payload) -> None:
        if self._closed or not isinstance(payload, dict) or payload.get("generation") != self._generation:
            return
        self.result = None
        self.table.hide()
        self.result_controls.hide()
        self.result_dialog.hide()
        self.view_result_button.setEnabled(False)
        result = payload.get("result")
        if not isinstance(result, SavedSignalComparison):
            self.status.setText("原保存訊號回傳格式不符。")
            return
        self.result = result
        if result.state != "available":
            self.status.setText("不可對照：" + "；".join(result.reasons))
            return
        families = len({strategy.family_id for strategy in result.strategies})
        matches = sum(row.common_entry_state == "match" for row in result.rows)
        unknown = sum(row.common_entry_state == "unknown" for row in result.rows)
        self.status.setText(f"{result.stock_code}｜{len(result.strategies)}策略／{families}家族｜"
            f"{len(result.rows)}觀測日；共同判定：{matches}日進場、{unknown}日未知。訊號不是成交；來源／PIT與績效資格另核。")
        self.status.setToolTip(f"提交期間 {result.requested_start} 至 {result.requested_end}\n"
            f"共同價量SHA {result.input_sha256}\n實際觀測 {result.rows[0].data_date} 至 {result.rows[-1].data_date}；不證明日曆完整。")
        counts = "、".join(strategy.run_name + "：" + str(sum(row.signals[index].state == "match" for row in result.rows)) + "次"
            for index, strategy in enumerate(result.strategies))
        self.detail_status.setText(self.status.text() + "\n各策略原進場意圖（非成交）：" + counts)
        self.detail_status.setToolTip(self.status.toolTip())
        self.strategy_combo.clear()
        for strategy in result.strategies:
            self.strategy_combo.addItem(f"{strategy.run_name}｜{strategy.strategy_version}｜{strategy.family_label}")
        self.result_controls.show()
        self.table.show()
        self._reset_page()
        self.view_result_button.setEnabled(True)
        self.result_dialog.show()

    def _failed(self, message) -> None:
        if not self._closed and self._active_generation == self._generation:
            self.result = None
            self.result_dialog.hide()
            self.view_result_button.setEnabled(False)
            self.status.setText("訊號來源核對失敗：" + str(message))

    def _finished(self) -> None:
        self._worker = None
        self._update_button()

    def _reset_page(self, *args) -> None:
        self._page = 0
        self._render()

    def _change_page(self, delta: int) -> None:
        self._page += delta
        self._render()

    def _render(self) -> None:
        result = self.result
        if result is None or result.state != "available":
            return
        rows = tuple(row for row in result.rows if not self.entry_only.isChecked() or row.matching_strategy_count > 0)
        pages = max(1, (len(rows) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self._page = max(0, min(self._page, pages - 1))
        page = rows[self._page * self.PAGE_SIZE:(self._page + 1) * self.PAGE_SIZE]
        headers = ["日期"] + [strategy.run_name for strategy in result.strategies] + ["共同進場", "命中策略／家族"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(page))
        for column, strategy in enumerate(result.strategies, 1):
            self.table.horizontalHeaderItem(column).setToolTip(f"{strategy.run_id}\n{strategy.strategy_id}@{strategy.strategy_version}\n{strategy.family_label}")
        for index, row in enumerate(page):
            values = [row.data_date]
            values.extend("未知" if signal.state == "unknown" else "進場意圖" if signal.signal == 1 else
                "出場意圖" if signal.signal == -1 else "未發進場意圖" for signal in row.signals)
            values.extend(({"match": "是", "no_match": "否", "unknown": "未知"}[row.common_entry_state],
                f"{row.matching_strategy_count}／{row.matching_family_count}"))
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if 1 <= column <= len(row.signals):
                    item.setToolTip(row.signals[column - 1].reason)
                self.table.setItem(index, column, item)
        self.table.resizeColumnsToContents()
        self.previous_button.setEnabled(self._page > 0)
        self.next_button.setEnabled(self._page + 1 < pages)
        self.page_label.setText(f"{self._page + 1}／{pages}頁（{len(rows)}日）")

    def open_rules(self) -> None:
        if self.result is None or self.result.state != "available":
            return
        from ui_qt.widgets.strategy_rule_card_dialog import StrategyRuleCardDialog
        strategy = self.result.strategies[self.strategy_combo.currentIndex()]
        StrategyRuleCardDialog(strategy.rule_source.rule_card, self.result_dialog, result=strategy.rule_source).exec()

    def begin_shutdown(self) -> None:
        self._closed = True
        self._generation += 1
        self.result_dialog.close()
        if self._worker is not None:
            self._worker.cancel(cooperative=True, wait=False)
        self._update_button()

    def closeEvent(self, event) -> None:
        self.begin_shutdown()
        super().closeEvent(event)
