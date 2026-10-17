"""呈現 F07 價格研究的已核驗個股事實與原查詢返回點。"""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QTabWidget, QTextBrowser, QVBoxLayout, QWidget,
)

from app_module.daily_market_technical_universe_price_comparison_v1 import (
    DailyMarketTechnicalUniversePriceSelectionV1,
)
from app_module.daily_market_technical_universe_price_query_v1 import (
    DailyMarketTechnicalUniversePriceStockV1,
)
from app_module.stock_research_report_dtos import StockPricePointDTO
from ui_qt.views.stock_research_report_view import StockPriceChartWidget


_RULE_LABELS: dict[str, str] = {
    "ma5_20_golden_cross": "MA5／MA20 黃金交叉",
    "kd_golden_cross": "KD 黃金交叉",
    "macd_golden_cross": "MACD 黃金交叉",
    "volume_ratio_20_including_current": "20 日均量比（含當日）",
    "volume_ratio_5_including_current": "5 日均量比（含當日）",
}
_STATE_LABELS: dict[str, str] = {"match": "符合", "no_match": "不符合", "unknown": "未知"}


def _price_text(value: Decimal | None) -> str:
    return format(value, "f") if value is not None else "未知"


def _canonical_decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def _query_conditions(selection: DailyMarketTechnicalUniversePriceSelectionV1) -> str:
    query = selection.query
    lower = "未設下限" if query.min_close_price is None else (
        f"{_price_text(query.min_close_price)}（{'含' if query.min_inclusive else '不含'}）"
    )
    upper = "未設上限" if query.max_close_price is None else (
        f"{_price_text(query.max_close_price)}（{'含' if query.max_inclusive else '不含'}）"
    )
    rule_filters = "、".join(
        f"{_RULE_LABELS.get(item.rule_key, item.rule_key)}："
        + "／".join(_STATE_LABELS.get(state, state) for state in item.states)
        for item in query.rule_state_filters
    ) or "技術規則不限制狀態"
    code_filter = "、".join(query.technical_stock_filter) or "技術股票代碼不限制"
    eligible = (
        "全納入清冊"
        if query.eligible_stock_codes is None
        else "、".join(query.eligible_stock_codes) or "明示空清單"
    )
    unknown_policy = {"include": "納入未知", "exclude": "排除未知", "only": "只看未知"}[
        query.unknown_price_policy
    ]
    return (
        f"價格範圍：{lower} 至 {upper} TWD／股；未知價格：{unknown_policy}。\n"
        f"技術條件：{query.combine_mode}；{rule_filters}。\n"
        f"技術股票代碼：{code_filter}。候選納入清冊：{eligible}。"
    )


def _validate_origin_pair(
    stock: DailyMarketTechnicalUniversePriceStockV1,
    selection: DailyMarketTechnicalUniversePriceSelectionV1,
) -> None:
    if not isinstance(stock, DailyMarketTechnicalUniversePriceStockV1):
        raise TypeError("需要 reader 發行的 F07 價格個股")
    if not isinstance(selection, DailyMarketTechnicalUniversePriceSelectionV1):
        raise TypeError("需要原結果頁發行的 F07 查詢錨點")
    stock.to_dict()
    selection.to_dict()
    fact = stock.row.price_fact
    query = selection.query
    checks = {
        "stock_code": stock.stock_code == selection.stock_code,
        "result_identity": stock.result_identity_sha256 == selection.result_identity_sha256,
        "page_request": stock.request.to_json() == selection.page_request_json,
        "row_identity": stock.row.row_identity_sha256 == selection.row_identity_sha256,
        "price_state": stock.row.price_state == selection.price_state,
        "snapshot_identity": stock.snapshot.snapshot_identity_sha256 == selection.snapshot_identity_sha256,
        "row_source_identity": stock.snapshot.source_identity == selection.row_source_identity,
        "fact_stock_code": fact.stock_code == selection.stock_code,
        "fact_snapshot": fact.snapshot_identity_sha256 == selection.snapshot_identity_sha256,
        "fact_source": fact.source_identity == selection.row_source_identity,
        "query_source": query.source.source_identity_sha256 == selection.source_identity_sha256,
        "price_index": query.source.price_index_identity_sha256 == selection.price_index_identity_sha256,
        "close_price": _canonical_decimal_text(fact.close_price) == selection.close_price,
        "observation_date": (fact.observation_date.isoformat() if fact.observation_date else None)
        == selection.observation_date,
        "raw_row_fingerprint": fact.raw_row_fingerprint_sha256 == selection.raw_row_fingerprint_sha256,
        "availability_unknown": query.source.source_available_at is None
        and query.source.availability_status == "unknown",
        "pit_not_eligible": query.source.historical_pit_eligible is False,
    }
    mismatches = tuple(key for key, matched in checks.items() if not matched)
    if mismatches:
        raise ValueError("technical_price_stock_origin_selection_mismatch:" + ",".join(mismatches))


class DailyMarketTechnicalPriceStockV1View(QWidget):
    """展示保存來源中的價格與五規則原始理由，不重算訊號。"""

    returnRequested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._stock: DailyMarketTechnicalUniversePriceStockV1 | None = None
        self._origin_selection: DailyMarketTechnicalUniversePriceSelectionV1 | None = None

        layout = QVBoxLayout(self)
        self.summary = QLabel("請從已核驗的價格研究結果選取股票。")
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setAccessibleName("價格研究個股摘要與日期限制")
        layout.addWidget(self.summary)

        self.conditions = QLabel()
        self.conditions.setWordWrap(True)
        self.conditions.setTextFormat(Qt.TextFormat.PlainText)
        self.conditions.setAccessibleName("原價格與技術查詢條件")
        layout.addWidget(self.conditions)

        self.evidence = QTextBrowser()
        self.evidence.setOpenExternalLinks(False)
        self.evidence.setAccessibleName("個股價格與五條技術規則理由、反證及未知原因")
        self.detail_tabs = QTabWidget(self)
        price_page = QWidget(self.detail_tabs)
        price_layout = QVBoxLayout(price_page)
        self.price_scope = QLabel()
        self.price_scope.setWordWrap(True)
        self.price_scope.setTextFormat(Qt.TextFormat.PlainText)
        price_layout.addWidget(self.price_scope)
        self.price_chart = StockPriceChartWidget(price_page)
        price_layout.addWidget(self.price_chart)
        self.price_table = QTableWidget(0, 7, price_page)
        self.price_table.setAccessibleName("原價格研究保存價量明細")
        self.price_table.setHorizontalHeaderLabels(["日期", "開盤", "最高", "最低", "收盤", "成交股數", "品質"])
        self.price_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.price_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.price_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.price_table.horizontalHeader().setStretchLastSection(True)
        price_layout.addWidget(self.price_table, 1)
        self.detail_tabs.addTab(price_page, "價格／技術")
        self.detail_tabs.addTab(self.evidence, "原選股規則")
        layout.addWidget(self.detail_tabs, 1)

        self.audit_toggle = QPushButton("顯示來源識別與核驗版本")
        self.audit_toggle.setCheckable(True)
        self.audit_toggle.setChecked(False)
        self.audit_toggle.toggled.connect(self._set_audit_visible)
        layout.addWidget(self.audit_toggle)
        self.audit = QTextBrowser()
        self.audit.setOpenExternalLinks(False)
        self.audit.setAccessibleName("F07 原查詢、收據、來源時鐘與個股識別")
        self.audit.setMaximumHeight(180)
        self.audit.hide()
        layout.addWidget(self.audit)

        self.return_button = QPushButton("返回原價格研究結果")
        self.return_button.setEnabled(False)
        self.return_button.clicked.connect(self._return_to_origin)
        layout.addWidget(self.return_button)

    def show_stock(
        self,
        stock: DailyMarketTechnicalUniversePriceStockV1,
        origin_selection: DailyMarketTechnicalUniversePriceSelectionV1,
    ) -> None:
        _validate_origin_pair(stock, origin_selection)
        points = self._price_points(stock)
        snapshot = stock.snapshot
        fact = stock.row.price_fact
        query = origin_selection.query
        source = query.source

        price_status = "符合原價格範圍" if stock.row.price_state == "pass" else "價格未知"
        price = f"{_price_text(fact.close_price)} TWD／股" if fact.close_price is not None else "未知"
        observation_date = fact.observation_date.isoformat() if fact.observation_date else "未知"
        reason_text = "、".join(fact.reason_codes) if fact.reason_codes else "無額外未知原因"
        self.summary.setText(
            f"{stock.stock_code}｜F07 當下價格與技術研究\n"
            f"價格：{price}；價格狀態：{price_status}；觀測日：{observation_date}\n"
            f"決策日：{source.decision_date.isoformat()}；技術最新特徵日："
            f"{snapshot.current_session.feature_date.isoformat() if snapshot.current_session else '未知'}\n"
            f"可得時間未知；僅保存當下研究，不宣稱全市場完整，未證明歷史 PIT，也不是交易建議。\n"
            f"價格未知原因：{reason_text}"
        )
        self.conditions.setText("原查詢條件\n" + _query_conditions(origin_selection))
        self.price_chart.set_points(points)
        self.price_scope.setText(
            f"原來源保存 {len(snapshot.rows)} 列價量；圖表可定位 {len(points)} 個日期。"
            "均線等訊號見「原選股規則」；未保存的歷史指標不繪製。"
            "缺值維持未知，可得時間未知，不作歷史可交易證據。"
        )
        self.price_table.setRowCount(len(snapshot.rows))
        for index, row in enumerate(reversed(snapshot.rows)):
            values = (
                row.feature_date.isoformat() if row.feature_date else row.raw_date,
                *(_price_text(value) if row.ohlc_valid else "未知" for value in (
                    row.open_price, row.high_price, row.low_price, row.close_price,
                )),
                _price_text(row.volume_shares) if row.volume_valid else "未知",
                "；".join(row.invalid_reasons) or "原列有效；可得時間未知",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(f"原列 SHA-256：{row.row_fingerprint_sha256}")
                self.price_table.setItem(index, column, item)
        self.detail_tabs.setCurrentIndex(0)

        parts: list[str] = [
            "價格來源事實",
            f"狀態：{price_status}",
            f"收盤價：{price}",
            f"價格觀測日：{observation_date}",
            f"決策日：{source.decision_date.isoformat()}",
            "",
            "已保存的五條技術規則",
        ]
        for rule in snapshot.rules:
            parts.append(f"{_RULE_LABELS.get(rule.key, rule.key)}（{rule.version}）：{_STATE_LABELS.get(rule.state, rule.state)}")
            parts.append(f"規則特徵日：{rule.feature_date.isoformat() if rule.feature_date else '未知'}；決策截止：{rule.decision_cutoff.isoformat()}")
            if rule.supports:
                parts.append("支持依據：" + "；".join(rule.supports))
            if rule.counterevidence:
                parts.append("反證：" + "；".join(rule.counterevidence))
            if rule.unknown_reasons:
                parts.append("未知原因：" + "；".join(rule.unknown_reasons))
            if rule.ratio is not None:
                parts.append(f"原保存比值：{rule.ratio}；分子：{rule.numerator}；分母：{rule.denominator}")
            parts.append("")
        parts.extend((
            "來源限制",
            "來源資料可得時間未知；historical PIT 不合格。此頁重述已保存的當下研究，不推定歷史可交易時間。",
        ))
        self.evidence.setPlainText("\n".join(parts))
        self.audit_toggle.setChecked(False)
        self.audit.setPlainText(
            "\n".join((
                f"selection_identity_sha256: {origin_selection.selection_identity_sha256}",
                f"query_identity_sha256: {query.query_identity_sha256}",
                f"page_identity_sha256: {origin_selection.page_identity_sha256}",
                f"result_identity_sha256: {origin_selection.result_identity_sha256}",
                f"source_identity_sha256: {source.source_identity_sha256}",
                f"source_clock_identity_sha256: {source.source_clock_identity_sha256}",
                f"method_contracts_sha256: {source.method_contracts_sha256}",
                f"generation_identity_sha256: {source.generation_identity_sha256}",
                f"plan_identity_sha256: {source.plan_identity_sha256}",
                f"plan_sha256: {source.plan_sha256}",
                f"receipt_identity_sha256: {source.receipt_identity_sha256}",
                f"receipt_sha256: {source.receipt_sha256}",
                f"price_index_identity_sha256: {source.price_index_identity_sha256}",
                f"stock_identity_sha256: {stock.stock_identity_sha256}",
                f"snapshot_identity_sha256: {snapshot.snapshot_identity_sha256}",
                f"raw_row_fingerprint_sha256: {fact.raw_row_fingerprint_sha256 or 'unknown'}",
            ))
        )
        self._stock = stock
        self._origin_selection = origin_selection
        self.return_button.setEnabled(True)

    @staticmethod
    def _price_points(stock: DailyMarketTechnicalUniversePriceStockV1) -> tuple[StockPricePointDTO, ...]:
        """只投影核驗原列；不補漲跌、不重算指標或宣稱歷史可得。"""
        rows = stock.snapshot.rows
        if len(rows) > 120:
            raise ValueError("technical_price_chart_row_limit")
        points: list[StockPricePointDTO] = []
        previous = ""
        for row in rows:
            if row.stock_code != stock.stock_code:
                raise ValueError("technical_price_chart_stock_mismatch")
            if row.feature_date is None:
                continue
            day = row.feature_date.isoformat()
            if day <= previous or row.feature_date > stock.snapshot.decision_date:
                raise ValueError("technical_price_chart_date_mismatch")
            previous = day
            volume = row.volume_shares
            points.append(StockPricePointDTO(
                data_date=day,
                open_price=row.open_price if row.ohlc_valid else None,
                high_price=row.high_price if row.ohlc_valid else None,
                low_price=row.low_price if row.ohlc_valid else None,
                close_price=row.close_price if row.ohlc_valid else None,
                volume=(int(volume) if row.volume_valid and volume is not None
                        and volume.is_finite() and volume >= 0 and volume == volume.to_integral_value() else None),
                source_id=stock.snapshot.source_id,
                source_snapshot_hash=row.row_fingerprint_sha256,
                quality="unknown",
            ))
        return tuple(points)

    def _set_audit_visible(self, visible: bool) -> None:
        self.audit.setVisible(visible)
        self.audit_toggle.setText("隱藏來源識別與核驗版本" if visible else "顯示來源識別與核驗版本")

    def _return_to_origin(self) -> None:
        if self._stock is not None and self._origin_selection is not None:
            _validate_origin_pair(self._stock, self._origin_selection)
            self.returnRequested.emit(self._origin_selection)
