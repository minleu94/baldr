"""並列呈現 F07 價格比較；每欄保留自己的查詢與來源時鐘。"""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app_module.daily_market_technical_universe_price_comparison_v1 import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_COMPARISON_MAX_ITEMS,
    DailyMarketTechnicalUniversePriceComparisonV1,
    DailyMarketTechnicalUniversePriceSelectionV1,
)
from app_module.daily_market_technical_universe_price_query_v1 import (
    DailyMarketTechnicalUniversePriceRowV1,
)
from ui_qt.widgets.comparison_evidence_panel import ComparisonEvidencePanel, compact_comparison_audit
from ui_qt.widgets.theme_widgets import CollapsibleSectionPanel


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
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
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
        self.table.verticalHeader().setDefaultSectionSize(max(26, self.fontMetrics().height() + 8))
        self.table.horizontalHeader().setMinimumSectionSize(140)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerItem)
        layout.addWidget(self.table, 1)
        self.evidence_summary = ComparisonEvidencePanel(self)
        layout.addWidget(self.evidence_summary)
        self.source_details = CollapsibleSectionPanel("完整原條件、理由與來源稽核", collapsed=True)
        compact_comparison_audit(self.source_details)

        self.evidence = QTextBrowser()
        self.evidence.setOpenExternalLinks(False)
        self.evidence.setAccessibleName("所選比較欄的原查詢條件、技術理由與來源 pins")
        self.evidence.setMaximumHeight(240)
        self.source_details.content_layout.addWidget(self.evidence)
        layout.addWidget(self.source_details)
        self.table.currentCellChanged.connect(self._show_column_evidence)

        self.return_button = QPushButton("返回所選欄的原價格研究")
        self.return_button.setEnabled(False)
        self.return_button.clicked.connect(self._return_to_origin)
        layout.addWidget(self.return_button)

    def show_comparison(self, comparison: DailyMarketTechnicalUniversePriceComparisonV1) -> None:
        if not isinstance(comparison, DailyMarketTechnicalUniversePriceComparisonV1):
            raise TypeError("需要 reader 發行的 F07 價格比較")
        comparison.to_json()
        if not 2 <= len(comparison.columns) <= DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_COMPARISON_MAX_ITEMS:
            raise ValueError("價格比較欄數超出 reader 契約")
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
        del previous_row, previous_column
        comparison = self._comparison
        if comparison is None or not 0 <= column_index < len(comparison.columns):
            self.evidence.clear()
            self.evidence_summary.set_evidence(heading="尚未選取比較欄。", context="", supports=(), counterevidence=(), unknown_reasons=())
            return
        column = comparison.columns[column_index]
        selection = column.selection
        query = selection.query
        row = column.row
        rules = (
            tuple(rule for rule in row.technical_row.rules if rule.key == _RULE_KEYS[row_index - 5])
            if 5 <= row_index <= 9 else row.technical_row.rules
        )
        supports, counter, unknown = [], [], list(row.price_fact.reason_codes)
        for rule in rules:
            prefix = _RULE_LABELS.get(rule.key, rule.key) + "：" if len(rules) > 1 else ""
            supports.extend(prefix + text for text in rule.supports)
            counter.extend(prefix + text for text in rule.counterevidence)
            unknown.extend(prefix + text for text in rule.unknown_reasons)
        context = (
            f"價格 {_price_text(row.price_fact.close_price)}｜價格日 {row.price_fact.observation_date or '未知'}"
            f"｜決策日 {row.technical_row.decision_date}｜技術特徵日 {row.technical_row.latest_feature_date or '未知'}"
        )
        title = "原價格與五項規則"
        if len(rules) == 1:
            rule = rules[0]
            title = _RULE_LABELS.get(rule.key, rule.key) + "｜" + _STATE_LABELS.get(rule.state, rule.state)
            context += f"｜規則特徵日 {rule.feature_date or '未知'}｜決策截止 {rule.decision_cutoff.isoformat()}"
            ratio_text = f"約 {rule.ratio:.4f}（原精度見稽核）" if rule.ratio is not None else "未知"
            context += f"｜分子 {rule.numerator if rule.numerator is not None else '未知'}／分母 {rule.denominator if rule.denominator is not None else '未知'}｜比率 {ratio_text}"
        filters = "；".join(
            _RULE_LABELS.get(item.rule_key, item.rule_key) + "＝"
            + "／".join(_STATE_LABELS.get(state, state) for state in item.states)
            for item in query.rule_state_filters
        ) or "技術規則不限狀態"
        lower = "未設下限" if query.min_close_price is None else f"{'≥' if query.min_inclusive else '>'}{query.min_close_price}"
        upper = "未設上限" if query.max_close_price is None else f"{'≤' if query.max_inclusive else '<'}{query.max_close_price}"
        unknown_policy_text = {"include": "納入未知", "exclude": "排除未知", "only": "只看未知"}[query.unknown_price_policy]
        conditions = f"原價格條件：{lower}／{upper} TWD／股；{unknown_policy_text}。技術 {query.combine_mode}：{filters}。"
        conditions += f"技術代碼 {len(query.technical_stock_filter)} 檔（清單見稽核）。" if query.technical_stock_filter else "技術代碼不限。"
        conditions += "候選範圍：全納入清冊。" if query.eligible_stock_codes is None else f"候選範圍：明選 {len(query.eligible_stock_codes)} 檔（清單見稽核）。"
        counts = query.source.counts
        conditions += f"技術來源納入 {counts.included_count}／宣告 {counts.declared_count} 檔（排除 {counts.excluded_count}、待處理 {counts.pending_count}）；不是全市場分母。"
        self.evidence_summary.set_evidence(
            heading=f"{selection.stock_code}｜{title}", context=context,
            supports=supports, counterevidence=counter, unknown_reasons=unknown, conditions=conditions,
        )
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
            parts.append(f"分子：{rule.numerator}；分母：{rule.denominator}；比率：{rule.ratio}")
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
