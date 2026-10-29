"""
Summary Strip
精緻的玻璃擬態卡片式狀態面板，位於 Scanner 上方。
已中文化標題與狀態呈現，並已調大字體以提升易讀性。
"""

from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QGridLayout,
    QVBoxLayout,
    QLabel,
    QFrame,
    QSizePolicy,
)
from decision_module.flow_contracts import SmartMoneySummaryDTO

class SummaryStrip(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        app = QApplication.instance()
        self._font_family = app.font().family() if app is not None else "Arial"
        
        # 設置透明背景，讓卡片疊加在主佈局上
        self.setAutoFillBackground(False)
        
        # 套用卡片全域樣式 (玻璃擬態微光邊框與懸停亮化)
        self.setStyleSheet("""
            QFrame#CardFrame {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(30, 41, 59, 0.45), 
                    stop:1 rgba(15, 23, 42, 0.6)
                );
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
            }
            QFrame#CardFrame:hover {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(51, 65, 85, 0.55), 
                    stop:1 rgba(30, 41, 59, 0.65)
                );
                border: 1px solid rgba(255, 255, 255, 0.16);
            }
        """)
        
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QGridLayout(self)
        layout.setContentsMargins(15, 8, 15, 8)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(8)
        
        # 建立卡片元件 (中文化標題且精簡字詞)
        self.lbl_regime = self._create_card("主力訊號方向")
        self.lbl_heat = self._create_card("偏多訊號占比")
        self.lbl_bull_bear = self._create_card("多空訊號家數")
        self.lbl_abnormal = self._create_card("異常訊號數")
        
        self._summary_cards = (
            self.lbl_regime["card"],
            self.lbl_heat["card"],
            self.lbl_bull_bear["card"],
            self.lbl_abnormal["card"],
        )
        self._summary_grid = layout
        self._summary_column_count = 0
        for card in self._summary_cards:
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            card.setMinimumWidth(0)
        self._relayout_summary_cards()

    def resizeEvent(self, event):  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._relayout_summary_cards()

    def _relayout_summary_cards(self) -> None:
        width = self.width()
        columns = 4 if width >= 1080 else 2 if width >= 420 else 1
        if columns == self._summary_column_count:
            return
        for card in self._summary_cards:
            self._summary_grid.removeWidget(card)
        while self._summary_grid.count():
            self._summary_grid.takeAt(0)
        self._summary_column_count = columns
        for column in range(4):
            self._summary_grid.setColumnStretch(column, 0)
        for index, card in enumerate(self._summary_cards):
            self._summary_grid.addWidget(card, index // columns, index % columns)
        for column in range(columns):
            self._summary_grid.setColumnStretch(column, 1)
        
    def _create_card(self, title: str) -> dict:
        card = QFrame()
        card.setObjectName("CardFrame")
        card.setAccessibleName(title)
        
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 8, 14, 8)
        card_layout.setSpacing(2)
        
        title_lbl = QLabel(title)
        title_lbl.setAccessibleName(title)
        # 字體大小由 9px 放大至 11px
        title_lbl.setStyleSheet(
            "color: #94a3b8; font-size: 11px; font-weight: bold; "
            f"font-family: '{self._font_family}';"
        )
        
        val_lbl = QLabel("--")
        val_lbl.setAccessibleName(f"{title}數值")
        # 數值字體大小由 13px 放大至 15px
        val_lbl.setStyleSheet(
            "color: #f8fafc; font-size: 15px; font-weight: bold; "
            f"font-family: '{self._font_family}';"
        )
        
        card_layout.addWidget(title_lbl)
        card_layout.addWidget(val_lbl)
        
        return {'card': card, 'title_lbl': title_lbl, 'val_lbl': val_lbl}

    def update_summary(self, summary: SmartMoneySummaryDTO):
        # 1. Regime (多空多語對照翻譯)
        regime_text = summary.market_regime
        if regime_text == "Bullish Flow":
            display_text = "偏多流向 (Bullish)"
            style = (
                "color: #10b981; font-size: 15px; font-weight: bold; "
                f"font-family: '{self._font_family}';"
            )
        elif regime_text == "Bearish Flow":
            display_text = "偏空流向 (Bearish)"
            style = (
                "color: #f43f5e; font-size: 15px; font-weight: bold; "
                f"font-family: '{self._font_family}';"
            )
        elif regime_text == "Neutral":
            display_text = "中性整理 (Neutral)"
            style = (
                "color: #f8fafc; font-size: 15px; font-weight: bold; "
                f"font-family: '{self._font_family}';"
            )
        else:
            display_text = "未知 (Unknown)"
            style = (
                "color: #94a3b8; font-size: 15px; font-weight: bold; "
                f"font-family: '{self._font_family}';"
            )
            
        self.lbl_regime['val_lbl'].setText(display_text)
        self.lbl_regime['val_lbl'].setStyleSheet(style)
        self.lbl_regime['val_lbl'].setToolTip(
            "依本次可分類的多空主力訊號比例判定：偏多高於 60%，偏空低於 40%，"
            "40%–60% 為中性；沒有可分類方向訊號時顯示未知。這不是價格指數或"
            "全市場漲跌廣度。"
        )
            
        # 2. Market Heat
        directional_count = summary.bullish_stock_count + summary.bearish_stock_count
        if directional_count <= 0:
            self.lbl_heat['val_lbl'].setText("—")
            self.lbl_heat['val_lbl'].setToolTip(
                "未知：沒有可分類的多空主力訊號。不可用或無方向訊號不納入比例。"
            )
            heat_color = "#94a3b8"
        else:
            self.lbl_heat['val_lbl'].setText(f"{summary.market_heat_score:.1f}%")
            self.lbl_heat['val_lbl'].setToolTip(
                f"計算方式：{summary.bullish_stock_count} ÷ "
                f"({summary.bullish_stock_count} + {summary.bearish_stock_count}) "
                f"= {summary.market_heat_score:.1f}%。只反映本次可分類的多空主力訊號；"
                "未知或不可用訊號不納入，不是全市場漲跌家數或報酬率。"
            )
            if summary.market_heat_score >= 70:
                heat_color = "#fb923c"
            elif summary.market_heat_score <= 30:
                heat_color = "#60a5fa"
            else:
                heat_color = "#f8fafc"
        self.lbl_heat['val_lbl'].setStyleSheet(
            f"color: {heat_color}; font-size: 15px; font-weight: bold; font-family: Consolas;"
        )
        
        # 3. Bull / Bear
        self.lbl_bull_bear['val_lbl'].setText(
            f"{summary.bullish_stock_count} 家偏多 / "
            f"{summary.bearish_stock_count} 家偏空"
        )
        self.lbl_bull_bear['val_lbl'].setToolTip(
            "只計本次可分類方向的主力訊號；未知或無方向訊號未列入，"
            "不代表完整市場股票母體家數。"
        )
        # 字體放大
        self.lbl_bull_bear['val_lbl'].setStyleSheet(
            "color: #f8fafc; font-size: 13px; font-weight: bold; "
            f"font-family: '{self._font_family}';"
        )
        
        # 4. Abnormal (主力異常警示)
        self.lbl_abnormal['val_lbl'].setText(f"{summary.abnormal_signal_count} 個")
        self.lbl_abnormal['val_lbl'].setToolTip(
            "本次帶有異常標記的訊號數，是風險提示，不代表已知主力意圖或交易指令。"
            "0 只表示本次沒有產生這類標記。"
        )
        if summary.abnormal_signal_count > 10:
            self.lbl_abnormal['val_lbl'].setStyleSheet(
                "color: #fbbf24; font-size: 15px; font-weight: bold; "
                f"font-family: '{self._font_family}';"
            )  # Alert Yellow
        else:
            self.lbl_abnormal['val_lbl'].setStyleSheet(
                "color: #f8fafc; font-size: 15px; font-weight: bold; "
                f"font-family: '{self._font_family}';"
            )
