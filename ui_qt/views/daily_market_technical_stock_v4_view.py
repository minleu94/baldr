"""呈現原保存五規則個股內容；不在展示邊界重算訊號。"""
from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QTextBrowser

from app_module.daily_market_technical_universe_v4_stock import DailyMarketTechnicalUniverseV4Stock


class DailyMarketTechnicalStockV4View(QWidget):
    returnRequested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._stock: DailyMarketTechnicalUniverseV4Stock | None = None
        layout = QVBoxLayout(self)
        self.summary = QLabel("請從保存的五規則研究名單選取股票。")
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setAccessibleName("保存五規則個股結論與資料日期")
        layout.addWidget(self.summary)
        self.evidence = QTextBrowser()
        self.evidence.setAccessibleName("五規則理由反證與來源限制")
        self.evidence.setOpenExternalLinks(False)
        layout.addWidget(self.evidence)
        self.return_button = QPushButton("返回原五規則名單")
        self.return_button.setEnabled(False)
        self.return_button.clicked.connect(self._return)
        layout.addWidget(self.return_button)

    def show_stock(self, stock: DailyMarketTechnicalUniverseV4Stock) -> None:
        if not isinstance(stock, DailyMarketTechnicalUniverseV4Stock):
            raise TypeError("需要已核驗的保存個股來源")
        snapshot = stock.snapshot
        # 展示前仍核DTO語義；資料日期沿保存來源，沒有讀取最新行情。
        snapshot.to_dict()
        labels = {"match": "符合", "no_match": "不符合", "unknown": "未知"}
        totals = {state: sum(rule.state == state for rule in snapshot.rules) for state in labels}
        latest = snapshot.current_session.feature_date.isoformat() if snapshot.current_session else "缺資料"
        self.summary.setText(
            f"{snapshot.stock_code}｜保存的五規則研究\n"
            f"符合 {totals['match']}／不符合 {totals['no_match']}／未知 {totals['unknown']}\n"
            f"決策日：{snapshot.decision_date}；截止：{snapshot.decision_cutoff.isoformat()}\n"
            f"最新特徵日：{latest}；原始資料列：{len(snapshot.rows)}\n"
            "資料可得時間尚未確認；這是研究條件，不能當作歷史可交易訊號或績效。"
        )
        parts = []
        names = {
            "ma5_20_golden_cross": "MA5／MA20 黃金交叉",
            "kd_golden_cross": "KD 黃金交叉",
            "macd_golden_cross": "MACD 黃金交叉",
            "volume_ratio_20_including_current": "20 日均量比（含當日）",
            "volume_ratio_5_including_current": "5 日均量比（含當日）",
        }
        for rule in snapshot.rules:
            parts.append(f"{names[rule.key]}（{rule.version}）：{labels[rule.state]}")
            parts.append(f"特徵日：{rule.feature_date or '未知'}；前一特徵日：{rule.previous_feature_date or '未知'}")
            if rule.supports:
                parts.append("支持依據：" + "；".join(rule.supports))
            if rule.counterevidence:
                parts.append("反證：" + "；".join(rule.counterevidence))
            if rule.unknown_reasons:
                parts.append("未知原因：" + "；".join(rule.unknown_reasons))
            if rule.ratio is not None:
                parts.append(f"比值：{rule.ratio}；分子：{rule.numerator}；分母：{rule.denominator}")
            parts.append("")
        parts.extend(("保存來源", f"研究版本：{stock.origin_query.receipt_identity_sha256}",
                      f"個股快照：{snapshot.snapshot_identity_sha256}",
                      f"計算版本：{snapshot.calculation_identity_sha256}"))
        self.evidence.setPlainText("\n".join(parts))
        self._stock = stock
        self.return_button.setEnabled(True)

    def _return(self) -> None:
        if self._stock is not None:
            self.returnRequested.emit(self._stock.origin_query)
