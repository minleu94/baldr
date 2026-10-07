"""並排呈現已嚴格讀回的原保存研究，不在 UI 重算訊號。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QTextBrowser, QVBoxLayout, QWidget,
)

from app_module.daily_market_technical_universe_v4_comparison import DailyMarketTechnicalUniverseV4Comparison


class DailyMarketTechnicalComparisonV4View(QWidget):
    originRequested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._comparison: DailyMarketTechnicalUniverseV4Comparison | None = None
        layout = QVBoxLayout(self)
        self.summary = QLabel("請選取至少兩筆原保存研究。")
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.summary)
        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectColumns)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAccessibleName("原保存五規則研究比較")
        layout.addWidget(self.table)
        self.evidence = QTextBrowser()
        self.evidence.setAccessibleName("所選比較格的原保存理由與來源")
        self.evidence.setOpenExternalLinks(False)
        self.evidence.setMaximumHeight(200)
        layout.addWidget(self.evidence)
        self.table.currentCellChanged.connect(self._show_evidence)
        self.return_button = QPushButton("返回所選欄的原查詢")
        self.return_button.setEnabled(False)
        self.return_button.clicked.connect(self._return)
        layout.addWidget(self.return_button)

    def show_comparison(self, comparison: DailyMarketTechnicalUniverseV4Comparison) -> None:
        if not isinstance(comparison, DailyMarketTechnicalUniverseV4Comparison) or not 2 <= len(comparison.columns) <= 256:
            raise ValueError("需要至少兩筆已核驗的研究比較")
        states = {"match": "符合", "no_match": "不符合", "unknown": "未知"}
        labels = ("決策日期", "決策截止", "最新特徵日期", "原始資料列數", "MA5／MA20 金叉", "KD 金叉", "MACD 金叉",
                  "20 日均量比（含當日）", "5 日均量比（含當日）", "原查詢版本")
        rule_keys = ("ma5_20_golden_cross", "kd_golden_cross", "macd_golden_cross",
                     "volume_ratio_20_including_current", "volume_ratio_5_including_current")
        self.table.setRowCount(len(labels))
        self.table.setColumnCount(len(comparison.columns))
        self.table.setVerticalHeaderLabels(labels)
        self.table.setHorizontalHeaderLabels([column.row.stock_code for column in comparison.columns])
        for index, column in enumerate(comparison.columns):
            row = column.row
            cutoffs = sorted({rule.decision_cutoff.isoformat() for rule in row.rules})
            values = [str(row.decision_date), "；".join(cutoffs),
                      str(row.latest_feature_date or "未知"), str(row.raw_row_count)]
            for key in rule_keys:
                rule = row.rule(key)
                text = states[rule.state]
                if rule.ratio is not None:
                    text += f"；比值 {rule.ratio}"
                values.append(text)
            values.append(column.origin_query.receipt_identity_sha256)
            for position, value in enumerate(values):
                item = QTableWidgetItem(value)
                detail = column.origin_query.to_json()
                if 4 <= position <= 8:
                    rule = row.rule(rule_keys[position - 4])
                    detail = (
                        f"決策截止：{rule.decision_cutoff}\n特徵日：{rule.feature_date or '未知'}\n"
                        f"方法版本：{rule.version}\n"
                        + "支持依據：" + "；".join(rule.supports) + "\n"
                        + "反證：" + "；".join(rule.counterevidence) + "\n"
                        + "未知原因：" + "；".join(rule.unknown_reasons) + "\n\n" + detail
                    )
                item.setToolTip(detail)
                self.table.setItem(position, index, item)
        differences = []
        if comparison.has_mixed_cutoffs:
            differences.append("決策截止不同")
        if comparison.has_mixed_methods:
            differences.append("方法版本不同")
        if comparison.has_mixed_source_clocks:
            differences.append("來源時鐘不同")
        self.summary.setText(
            f"原保存研究比較：{len(comparison.columns)} 檔。"
            + ("口徑差異：" + "、".join(differences) + "。" if differences else "保存口徑一致。")
            + "\n資料可得時間未知；僅供當下重述研究，不授歷史 PIT 或可交易資格。"
        )
        self._comparison = comparison
        self.table.setCurrentCell(0, 0)
        self._show_evidence(0, 0, -1, -1)
        self.table.resizeColumnsToContents()
        self.return_button.setEnabled(True)

    def _show_evidence(self, row: int, column: int, previous_row: int, previous_column: int) -> None:
        item = self.table.item(row, column)
        self.evidence.setPlainText(item.toolTip() if item is not None else "")

    def _return(self) -> None:
        index = self.table.currentColumn()
        if self._comparison is not None and 0 <= index < len(self._comparison.columns):
            column = self._comparison.columns[index]
            self.originRequested.emit((column.origin_query, column.row.stock_code))
