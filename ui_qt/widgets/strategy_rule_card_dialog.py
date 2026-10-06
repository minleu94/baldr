"""按需唯讀規則說明，不接回測摘要或建立執行器。"""
from __future__ import annotations

import json
from decimal import Decimal
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPlainTextEdit, QPushButton, QDialogButtonBox, QWidget
from app_module.strategy_rule_card_readmodel import StrategyRuleCard
from app_module.saved_strategy_rule_card import SavedStrategyRuleCard

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
    def __init__(self, card: StrategyRuleCard, parent: QWidget | None = None, *, result: SavedStrategyRuleCard | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("版本化規則說明")
        self.resize(750, 520)
        layout = QVBoxLayout(self)
        name = card.field("name").value or card.identity.rule_id or "未知策略"
        self.summary = QLabel(f"{name}｜版本 {card.identity.rule_version or '未知'}\n目前回測設定；尚未連結執行結果。")
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        if result is not None:
            origin = result.origin
            kind = {"historical_backtest": "歷史回測", "research_forward": "研究追蹤"}.get(result.result_kind, "結果類別未知")
            self.summary.setText(f"{origin['run_name']}｜{kind}｜規則版本 {origin['strategy_version'] or '未知'}")
            costs = origin["costs"]
            cost_text = "未知；不補預設" if costs is None else (
                f"費率 {Decimal(costs['fee_bp_x100']) / Decimal('100')} bp、"
                f"滑價 {Decimal(costs['slippage_bp_x100']) / Decimal('100')} bp；其餘稅費未核對")
            source_text = "保存身份已核對，可連結同版說明" if result.source_status == "source_ref_only" else "尚不能連結保存規則；來源缺件或身份不符"
            benchmark_text = "有保存聲明，尚未核對" if origin["benchmark"] is not None else "未知；不補預設"
            universe_text = ', '.join(str(code) for code in origin['universe'][:3]) or '未知'
            if len(origin['universe']) > 3:
                universe_text += f"…（共 {len(origin['universe'])} 筆保存標的）"
            execution_text = {"next-session-open.v2": "次一交易時段開盤（v2）", "legacy-same-day-close.v1": "舊同日收盤（v1）"}.get(origin["execution_contract"], "未知；不推測成交")
            self.result_source = QLabel(
                f"期間：{origin['start_date'] or '未知'}～{origin['end_date'] or '未知'}｜資料截止：{origin['data_cutoff_date'] or '未知'}\n"
                f"保存標的：{universe_text}｜保存成交假設：{execution_text}\n"
                f"保存費率：{cost_text}｜基準：{benchmark_text}\n來源連結：{source_text}；正式資格未授予。")
            self.result_source.setTextFormat(Qt.TextFormat.PlainText)
            self.result_source.setWordWrap(True)
            layout.addWidget(self.result_source)
        self.qualification = QLabel("完整交易規則與績效：尚不可評估。缺少的契約保留未知，參數說明不能代替入場、出場或獲利證據。")
        self.qualification.setTextFormat(Qt.TextFormat.PlainText)
        self.qualification.setWordWrap(True)
        if result is not None and result.source_status != "source_ref_only":
            self.qualification.setText("不可評估：尚未核對保存時的規則來源。下方僅為Registry說明與保存參數，不當作該結果的執行規則或績效證明。")
        self.qualification.setToolTip("\n".join(card.reasons))
        layout.addWidget(self.qualification)
        self.rules = QPlainTextEdit(rule_card_text(card))
        self.rules.setReadOnly(True)
        layout.addWidget(self.rules)
        audit_button = QPushButton("查看來源與版本核對")
        layout.addWidget(audit_button)
        self.audit = QPlainTextEdit(json.dumps(result.to_dict() if result is not None else card.to_dict(), ensure_ascii=False, indent=2))
        self.audit.setReadOnly(True)
        self.audit.setVisible(False)
        layout.addWidget(self.audit)
        audit_button.clicked.connect(lambda: self.audit.setVisible(not self.audit.isVisible()))
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)
