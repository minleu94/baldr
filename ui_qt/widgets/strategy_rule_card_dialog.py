"""按需唯讀規則說明，不接回測摘要或建立執行器。"""
from __future__ import annotations

import json
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPlainTextEdit, QPushButton, QDialogButtonBox, QWidget
from app_module.strategy_rule_card_readmodel import StrategyRuleCard

_LABELS = {
    "entry": "入場條件", "exit": "出場條件", "parameters": "此次參數",
    "universe": "適用範圍", "period": "期間", "cost": "費用與稅",
    "signal_time": "訊號時點", "earliest_execution": "最早可成交時點",
    "holding_period": "持有期間", "stop_loss": "停損", "take_profit": "停利",
    "position_limits": "部位限制", "gap_suspension_unfilled": "跳空、停牌與未成交",
    "benchmark": "比較基準", "required_features": "必要資料", "units": "單位",
}


def rule_card_text(card: StrategyRuleCard) -> str:
    lines = []
    description = card.field("description").value
    if description:
        lines.append(str(description))
    for key, label in _LABELS.items():
        field = card.field(key)
        value = "未知：來源未提供完整契約" if field.missing_reason else json.dumps(field.value, ensure_ascii=False)
        lines.append(f"{label}：{value}")
    return "\n\n".join(lines)


class StrategyRuleCardDialog(QDialog):
    def __init__(self, card: StrategyRuleCard, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("版本化規則說明")
        self.resize(750, 520)
        layout = QVBoxLayout(self)
        name = card.field("name").value or card.identity.rule_id or "未知策略"
        self.summary = QLabel(f"{name}｜版本 {card.identity.rule_version or '未知'}\n目前回測設定；尚未連結執行結果。")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.qualification = QLabel("完整交易規則與績效：尚不可評估。缺少的契約保留未知，參數說明不能代替入場、出場或獲利證據。")
        self.qualification.setWordWrap(True)
        self.qualification.setToolTip("\n".join(card.reasons))
        layout.addWidget(self.qualification)
        self.rules = QPlainTextEdit(rule_card_text(card))
        self.rules.setReadOnly(True)
        layout.addWidget(self.rules)
        audit_button = QPushButton("查看來源與版本核對")
        layout.addWidget(audit_button)
        self.audit = QPlainTextEdit(json.dumps(card.to_dict(), ensure_ascii=False, indent=2))
        self.audit.setReadOnly(True)
        self.audit.setVisible(False)
        layout.addWidget(self.audit)
        audit_button.clicked.connect(lambda: self.audit.setVisible(not self.audit.isVisible()))
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)
