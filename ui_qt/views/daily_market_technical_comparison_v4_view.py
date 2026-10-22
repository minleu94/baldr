"""並排呈現已嚴格讀回的原保存研究，不在 UI 重算訊號。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QTextBrowser, QVBoxLayout, QWidget,
)

from app_module.daily_market_technical_universe_v4_comparison import DailyMarketTechnicalUniverseV4Comparison
from ui_qt.widgets.comparison_evidence_panel import ComparisonEvidencePanel, compact_comparison_audit
from ui_qt.widgets.theme_widgets import CollapsibleSectionPanel

_RULE_KEYS = ("ma5_20_golden_cross", "kd_golden_cross", "macd_golden_cross",
              "volume_ratio_20_including_current", "volume_ratio_5_including_current")
_RULE_TITLES = ("MA5／MA20 金叉", "KD 金叉", "MACD 金叉", "20 日均量比（含當日）", "5 日均量比（含當日）")


class DailyMarketTechnicalComparisonV4View(QWidget):
    originRequested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
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
        self.table.verticalHeader().setDefaultSectionSize(max(26, self.fontMetrics().height() + 8))
        self.table.horizontalHeader().setMinimumSectionSize(140)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerItem)
        layout.addWidget(self.table, 1)
        self.evidence_summary = ComparisonEvidencePanel(self)
        layout.addWidget(self.evidence_summary)
        self.source_details = CollapsibleSectionPanel("完整原查詢與來源稽核", collapsed=True)
        compact_comparison_audit(self.source_details)
        self.evidence = QTextBrowser()
        self.evidence.setAccessibleName("所選比較格的原保存理由與來源")
        self.evidence.setOpenExternalLinks(False)
        self.evidence.setMaximumHeight(200)
        self.source_details.content_layout.addWidget(self.evidence)
        layout.addWidget(self.source_details)
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
                  "20 日均量比（含當日）", "5 日均量比（含當日）", "原查詢版本（短碼）")
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
                    text += f"；比值約 {rule.ratio:.4f}"
                values.append(text)
            values.append(column.origin_query.receipt_identity_sha256[:12] + "…")
            for position, value in enumerate(values):
                item = QTableWidgetItem(value)
                detail = column.origin_query.to_json()
                if 4 <= position <= 8:
                    rule = row.rule(rule_keys[position - 4])
                    detail = (
                        f"決策截止：{rule.decision_cutoff}\n特徵日：{rule.feature_date or '未知'}\n"
                        f"方法版本：{rule.version}\n"
                        f"分子：{rule.numerator}；分母：{rule.denominator}；比率：{rule.ratio}\n"
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
        self.table.setCurrentCell(4, 0)
        self._show_evidence(4, 0, -1, -1)
        self.return_button.setEnabled(True)

    def _show_evidence(self, row: int, column: int, previous_row: int, previous_column: int) -> None:
        item = self.table.item(row, column)
        self.evidence.setPlainText(item.toolTip() if item is not None else "")
        comparison = self._comparison
        if comparison is None or not 0 <= column < len(comparison.columns):
            self.evidence_summary.set_evidence(heading="尚未選取比較欄。", context="", supports=(), counterevidence=(), unknown_reasons=())
            return
        selected = comparison.columns[column].row
        rules = (selected.rule(_RULE_KEYS[row - 4]),) if 4 <= row <= 8 else selected.rules
        supports, counter, unknown = [], [], []
        for rule in rules:
            prefix = _RULE_TITLES[_RULE_KEYS.index(rule.key)] + "：" if len(rules) > 1 else ""
            supports.extend(prefix + text for text in rule.supports)
            counter.extend(prefix + text for text in rule.counterevidence)
            unknown.extend(prefix + text for text in rule.unknown_reasons)
        title = self.table.verticalHeaderItem(row).text() if 4 <= row <= 8 else "五項原規則"
        context = f"決策日 {selected.decision_date}｜最新特徵日 {selected.latest_feature_date or '未知'}"
        if len(rules) == 1:
            rule = rules[0]
            state = {"match": "符合", "no_match": "不符合", "unknown": "未知"}[rule.state]
            title += f"｜{state}"
            context += f"｜規則特徵日 {rule.feature_date or '未知'}｜決策截止 {rule.decision_cutoff.isoformat()}"
            ratio_text = f"約 {rule.ratio:.4f}（原精度見稽核）" if rule.ratio is not None else "未知"
            context += f"｜分子 {rule.numerator if rule.numerator is not None else '未知'}／分母 {rule.denominator if rule.denominator is not None else '未知'}｜比率 {ratio_text}"
        query = comparison.columns[column].origin_query
        filters = "；".join(
            _RULE_TITLES[_RULE_KEYS.index(item.rule_key)] + "＝"
            + "／".join({"match": "符合", "no_match": "不符合", "unknown": "未知"}[state] for state in item.states)
            for item in query.rule_state_filters
        ) or "技術規則不限狀態"
        conditions = (
            f"原條件 {query.combine_mode}：{filters}｜納入 {query.included_count}／宣告 {query.declared_count} 檔"
            f"｜排除 {query.excluded_count} 檔；不是全市場分母。"
            + (f"代碼條件 {len(query.stock_filter)} 檔（完整清單見稽核）。" if query.stock_filter else "代碼不限。")
        )
        self.evidence_summary.set_evidence(
            heading=f"{selected.stock_code}｜{title}", context=context,
            supports=supports, counterevidence=counter, unknown_reasons=unknown, conditions=conditions,
        )

    def _return(self) -> None:
        index = self.table.currentColumn()
        if self._comparison is not None and 0 <= index < len(self._comparison.columns):
            column = self._comparison.columns[index]
            self.originRequested.emit((column.origin_query, column.row.stock_code))
