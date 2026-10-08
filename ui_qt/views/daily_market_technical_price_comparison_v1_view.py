"""並列呈現 F07 價格比較；每欄保留自己的查詢與來源時鐘。"""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app_module.daily_market_technical_universe_price_comparison_v1 import (
    DailyMarketTechnicalUniversePriceComparisonV1,
    DailyMarketTechnicalUniversePriceSelectionV1,
)
from app_module.daily_market_technical_universe_price_query_v1 import (
    DailyMarketTechnicalUniversePriceRowV1,
)


_RULE_LABELS: dict[str, str] = {
    "ma5_20_golden_cross": "MA5／MA20 黃金交叉",
    "kd_golden_cross": "KD 黃金交叉",
    "macd_golden_cross": "MACD 黃金交叉",
    "volume_ratio_20_including_current": "20 日均量比（含當日）",
    "volume_ratio_5_including_current": "5 日均量比（含當日）",
}
_STATE_LABELS: dict[str, str] = {"match": "符合", "no_match": "不符合", "unknown": "未知"}
_PRICE_STATE_LABELS = {"pass": "符合價格條件", "unknown": "未知價格"}
_RULE_KEYS = tuple(_RULE_LABELS)


def _price_text(value: Decimal | None) -> str:
    return f"{value} TWD／股" if value is not None else "未知"


def _row_values(row: DailyMarketTechnicalUniversePriceRowV1) -> dict[str, str]:
    fact = row.price_fact
    values = {
        "價格": _price_text(fact.close_price),
        "價格狀態": _PRICE_STATE_LABELS[row.price_state],
        "價格觀測日": fact.observation_date.isoformat() if fact.observation_date else "未知",
        "決策日": row.technical_row.decision_date.isoformat(),
        "技術最新特徵日": row.technical_row.latest_feature_date.isoformat() if row.technical_row.latest_feature_date else "未知",
    }
    for rule in row.technical_row.rules:
        values[_RULE_LABELS.get(rule.key, rule.key)] = _STATE_LABELS.get(rule.state, rule.state)
    return values


class DailyMarketTechnicalPriceComparisonV1View(QWidget):
    """顯示 fresh comparison 的原始事實與逐欄返回錨點。"""

    originRequested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._comparison: DailyMarketTechnicalUniversePriceComparisonV1 | None = None
        layout = QVBoxLayout(self)
        self.summary = QLabel("請選取已 fresh 核驗的 F07 比較。")
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.summary)

        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectColumns)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAccessibleName("F07 價格與五規則比較；每欄使用自身來源")
        layout.addWidget(self.table, 1)

        self.evidence = QTextBrowser()
        self.evidence.setOpenExternalLinks(False)
        self.evidence.setAccessibleName("所選比較欄的原查詢條件、技術理由與來源 pins")
        self.evidence.setMaximumHeight(240)
        layout.addWidget(self.evidence)
        self.table.currentCellChanged.connect(self._show_column_evidence)

        self.return_button = QPushButton("返回所選欄的原價格研究")
        self.return_button.setEnabled(False)
        self.return_button.clicked.connect(self._return_to_origin)
        layout.addWidget(self.return_button)

    def show_comparison(self, comparison: DailyMarketTechnicalUniversePriceComparisonV1) -> None:
        if not isinstance(comparison, DailyMarketTechnicalUniversePriceComparisonV1):
            raise TypeError("需要 reader 發行的 F07 價格比較")
        comparison.to_json()
        if not 2 <= len(comparison.columns) <= 5:
            raise ValueError("F07 比較畫面接受 2 至 5 檔")
        for column in comparison.columns:
            column.selection.to_json()
            column.row.to_dict()

        labels = (
            "價格", "價格狀態", "價格觀測日", "決策日", "技術最新特徵日",
            *(_RULE_LABELS[key] for key in _RULE_KEYS),
        )
        self.table.clear()
        self.table.setRowCount(len(labels))
        self.table.setColumnCount(len(comparison.columns))
        self.table.setVerticalHeaderLabels(list(labels))
        self.table.setHorizontalHeaderLabels([item.selection.stock_code for item in comparison.columns])
        for column_index, column in enumerate(comparison.columns):
            values = _row_values(column.row)
            for row_index, label in enumerate(labels):
                value = values.get(label, "未提供")
                item = QTableWidgetItem(value)
                item.setToolTip(
                    f"股票：{column.selection.stock_code}\n"
                    f"查詢：{column.selection.query.query_identity_sha256}\n"
                    f"來源：{column.selection.source_identity_sha256}"
                )
                self.table.setItem(row_index, column_index, item)
        self.table.resizeColumnsToContents()
        self._comparison = comparison
        self.summary.setText(
            f"已核驗 {len(comparison.columns)} 檔；逐欄分別列出價格觀測日、決策日與技術規則狀態。\n"
            "每欄可能使用不同查詢版本與來源時鐘；資料可得時間未知，不宣稱全市場完整，也不授歷史 PIT 或交易資格。"
        )
        self.table.setCurrentCell(0, 0)
        self._show_column_evidence(0, 0, -1, -1)
        self.return_button.setEnabled(True)

    def _show_column_evidence(
        self,
        row_index: int,
        column_index: int,
        previous_row: int,
        previous_column: int,
    ) -> None:
        del row_index, previous_row, previous_column
        comparison = self._comparison
        if comparison is None or not 0 <= column_index < len(comparison.columns):
            self.evidence.clear()
            return
        column = comparison.columns[column_index]
        selection = column.selection
        query = selection.query
        row = column.row
        unknown_policy = {
            "include": "納入未知",
            "exclude": "排除未知",
            "only": "只看未知",
        }[query.unknown_price_policy]
        parts = [
            f"股票：{selection.stock_code}",
            f"價格：{_price_text(row.price_fact.close_price)}；觀測日：{row.price_fact.observation_date.isoformat() if row.price_fact.observation_date else '未知'}",
            f"決策日：{query.source.decision_date.isoformat()}；技術最新特徵日：{row.technical_row.latest_feature_date.isoformat() if row.technical_row.latest_feature_date else '未知'}",
            f"本欄價格條件：{unknown_policy}；價格下限：{query.min_close_price if query.min_close_price is not None else '未設定'}；上限：{query.max_close_price if query.max_close_price is not None else '未設定'}",
            f"技術條件組合：{query.combine_mode}",
        ]
        if row.price_fact.reason_codes:
            parts.append("價格未知原因：" + "、".join(row.price_fact.reason_codes))
        if query.rule_state_filters:
            for item in query.rule_state_filters:
                states = "／".join(_STATE_LABELS.get(state, state) for state in item.states)
                parts.append(f"條件：{_RULE_LABELS.get(item.rule_key, item.rule_key)}＝{states}")
        for rule in row.technical_row.rules:
            parts.append(f"{_RULE_LABELS.get(rule.key, rule.key)}（{rule.version}）：{_STATE_LABELS.get(rule.state, rule.state)}")
            if rule.supports:
                parts.append("支持依據：" + "；".join(rule.supports))
            if rule.counterevidence:
                parts.append("反證：" + "；".join(rule.counterevidence))
            if rule.unknown_reasons:
                parts.append("未知原因：" + "；".join(rule.unknown_reasons))
        source = query.source
        parts.extend((
            "",
            "來源限制：可得時間未知；historical PIT 不合格。",
            "本欄來源識別（稽核）",
            f"來源：{source.source_identity_sha256}",
            f"時鐘：{source.source_clock_identity_sha256}",
            f"方法：{source.method_contracts_sha256}",
            f"generation：{source.generation_identity_sha256}",
            f"plan：{source.plan_identity_sha256}／{source.plan_sha256}",
            f"receipt：{source.receipt_identity_sha256}／{source.receipt_sha256}",
            f"價格索引：{source.price_index_identity_sha256}",
            f"query：{query.query_identity_sha256}",
            f"page：{selection.page_identity_sha256}",
        ))
        self.evidence.setPlainText("\n".join(parts))

    def _return_to_origin(self) -> None:
        comparison = self._comparison
        if comparison is None:
            return
        index = self.table.currentColumn()
        if 0 <= index < len(comparison.columns):
            selection = comparison.columns[index].selection
            selection.to_json()
            self.originRequested.emit(selection)
