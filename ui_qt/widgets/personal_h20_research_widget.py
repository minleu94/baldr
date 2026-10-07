"""完整已保存 H20 母體的研究列表與 exact 返回；主工作區由中央接線。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QLabel, QPlainTextEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app_module.recommendation.personal_h20_research_cohort import (
    PersonalH20ResearchCohort, PersonalH20ResearchRow, PersonalH20ResearchSelection,
    sort_personal_h20_research_rows,
)


class PersonalH20ResearchWidget(QWidget):
    researchRequested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cohort: PersonalH20ResearchCohort | None = None
        self._closing = False
        self.summary_label = QLabel("請讀取明確指定的原保存 H20 manifest。")
        self.summary_label.setWordWrap(True)
        self.scope_label = QLabel("尚無已核保存母體")
        self.scope_label.setWordWrap(True)
        self.limit_label = QLabel("H20 gross 是未扣成本的20交易日預測，不是勝率或機率。\n"
            "效果尚未成熟；成本後有效性未證明。高預測不代表值得買，不授自動交易。")
        self.limit_label.setWordWrap(True)
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["預測毛報酬由高到低", "預測毛報酬由低到高"])
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["股票", "H20 毛報酬（bp）", "狀態", "決策日", "來源日", "特徵截至", "原因"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(False)
        self.diagnostic_text = QPlainTextEdit()
        self.diagnostic_text.setObjectName("personalH20RowDiagnostic")
        self.diagnostic_text.setReadOnly(True)
        self.diagnostic_text.setPlaceholderText("選取一列可查看完整來源核驗原因與修復前置條件。")
        self.diagnostic_text.setMaximumBlockCount(80)
        self.research_button = QPushButton("研究選取股票")
        self.research_button.setEnabled(False)
        layout = QVBoxLayout(self)
        for widget in (self.summary_label, self.scope_label, self.limit_label, self.sort_combo,
                       self.table, self.diagnostic_text, self.research_button):
            layout.addWidget(widget)
        self.sort_combo.currentIndexChanged.connect(self._render)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.itemDoubleClicked.connect(self._request_item)
        self.research_button.clicked.connect(self._request_current)

    def set_cohort(self, cohort: PersonalH20ResearchCohort) -> None:
        if self._closing:
            return
        # 本 widget 無 background reader；中央須先核其 worker generation，再送此同步 API。
        if (not isinstance(cohort, PersonalH20ResearchCohort)
                or not 1 <= len(cohort.symbols) <= 50
                or tuple(sorted(row.symbol for row in cohort.rows)) != cohort.symbols
                or len(set(cohort.symbols)) != len(cohort.symbols)
                or any(row.decision_date != cohort.decision_date for row in cohort.rows)):
            raise ValueError("personal_h20_research_widget_complete_cohort_required")
        sort_personal_h20_research_rows(cohort)
        self._cohort = cohort
        self.summary_label.setText(f"已保存 H20 研究母體：{len(cohort.symbols)} 股｜決策日 {cohort.decision_date}\n"
            "排序僅涵蓋此原 manifest 成員；缺件保留未知，不代表全市場。")
        self.scope_label.setText(f"模型 {cohort.candidate_id}｜cycle {cohort.cycle_id}\n"
            f"contract {cohort.contract_hash}\nmanifest {cohort.manifest_path}\nraw pin {cohort.manifest_sha256}")
        self._render()

    def _selection(self, row: PersonalH20ResearchRow) -> PersonalH20ResearchSelection:
        assert self._cohort is not None
        cohort = self._cohort
        return PersonalH20ResearchSelection(cohort.manifest_sha256, cohort.candidate_id,
            cohort.contract_hash, cohort.cycle_id, row.symbol, row.sample_id,
            row.prediction_id, row.capture_sha256)

    def _render(self, *_args: object) -> None:
        if self._closing or self._cohort is None:
            return
        self.table.clearSelection()
        self.diagnostic_text.clear()
        rows = sort_personal_h20_research_rows(self._cohort, descending=self.sort_combo.currentIndex() == 0)
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            values = (row.symbol, str(row.gross_return_bp) if row.gross_return_bp is not None else "—",
                "可核原預測" if row.status == "available" else "未知", row.decision_date,
                row.source_date or "未知", row.feature_as_of_date or "未知", row.reason)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, self._selection(row))
                item.setData(Qt.ItemDataRole.UserRole + 1, row)
                item.setToolTip(f"sample {row.sample_id}\nprediction {row.prediction_id}\n"
                    f"capture {row.capture_path}\nraw {row.capture_sha256}\n"
                    f"完整原因：{row.reason or '原 reader 未提供文字原因'}")
                self.table.setItem(index, column, item)
        self.table.setCurrentItem(None)
        self.research_button.setEnabled(False)

    def _accepted(self, selection: object) -> bool:
        return (not self._closing and self._cohort is not None
            and isinstance(selection, PersonalH20ResearchSelection)
            and any(row.status == "available" and self._selection(row) == selection for row in self._cohort.rows))

    def restore_selection(self, selection: PersonalH20ResearchSelection) -> bool:
        self.table.clearSelection()
        self.table.setCurrentItem(None)
        if not self._accepted(selection):
            self.research_button.setEnabled(False)
            return False
        for index in range(self.table.rowCount()):
            item = self.table.item(index, 0)
            if item.data(Qt.ItemDataRole.UserRole) == selection:
                self.table.setCurrentItem(item)
                self.table.selectRow(index)
                return True
        return False

    def _selection_changed(self) -> None:
        selected = self.table.selectedItems()
        current = self.table.currentItem()
        row_index = (
            current.row() if current is not None else selected[0].row()
        ) if selected else -1
        item = self.table.item(row_index, 0) if row_index >= 0 else None
        self.research_button.setEnabled(bool(selected) and item is not None
            and self._accepted(item.data(Qt.ItemDataRole.UserRole)))
        row = item.data(Qt.ItemDataRole.UserRole + 1) if item is not None else None
        self.diagnostic_text.setPlainText(
            self._row_diagnostic(row) if isinstance(row, PersonalH20ResearchRow) else ""
        )

    @staticmethod
    def _row_diagnostic(row: PersonalH20ResearchRow) -> str:
        """呈現可複製的原保存 reader 原因與修復前置條件。"""
        lines = [
            f"股票：{row.symbol}",
            f"狀態：{'原保存預測已核驗' if row.status == 'available' else '未知；研究操作停用'}",
            f"決策日：{row.decision_date}",
            f"來源日：{row.source_date or '未知'}",
            f"特徵截至：{row.feature_as_of_date or '未知'}",
            f"sample：{row.sample_id}",
            f"prediction：{row.prediction_id}",
            f"原 capture：{row.capture_path}",
            f"capture SHA：{row.capture_sha256}",
            "",
            "原保存來源核驗原因：",
            row.reason or "reader 未提供文字原因。",
        ]
        if row.status == "unknown":
            lines.extend((
                "",
                "研究按鈕維持停用，直到這列以原 manifest 與原 capture pin 通過核驗。",
                "修復前置條件：依上方完整原因修復或恢復它指出的原來源、設定或檔案；重讀同一保存版本並保持原 SHA。不可改指最新 cycle、借其他股票或重算值替代。",
            ))
            prefix = "current-observed immutable path is outside approved research roots:"
            if row.reason.startswith(prefix):
                field = row.reason[len(prefix):].strip() or "原始來源路徑"
                lines.extend((
                    "",
                    f"來源定位：原 capture 所 pin 的 {field} 不在目前核准研究來源根內，或無法依目前路徑設定解析。",
                    "具體前置條件：讓該保存版本的原檔在核准 current-observed research root 下可讀，並維持 capture 內記錄的原 SHA；若使用了不同儲存根，先修正該版本的核准根設定，再讀回原 capture。",
                ))
        else:
            lines.extend(("", "研究操作只沿此列精確保存的原預測下鑽；自然結果仍須另外核驗。"))
        return "\n".join(lines)

    def _request_item(self, item: QTableWidgetItem) -> None:
        selection = item.data(Qt.ItemDataRole.UserRole)
        if self._accepted(selection):
            self.researchRequested.emit(selection)

    def _request_current(self) -> None:
        item = self.table.currentItem()
        if item is None:
            selected = self.table.selectedItems()
            item = self.table.item(selected[0].row(), 0) if selected else None
        if item is not None and self.table.selectedItems():
            self._request_item(item)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._closing = True
        self._cohort = None
        self.table.clearSelection()
        self.research_button.setEnabled(False)
        super().closeEvent(event)
