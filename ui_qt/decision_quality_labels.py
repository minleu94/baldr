"""Decision Quality 的唯讀 UI 顯示標籤。"""

from __future__ import annotations


ITEM_TYPE_LABELS = {
    "ignored_portfolio_alert": "忽略投資組合警示",
    "manual_override_without_evidence": "缺少依據的手動覆寫",
    "trade_without_source_trace": "交易缺少來源追溯",
    "missed_high_quality_signal": "遺漏高品質訊號",
    "unreviewed_signal_decay": "訊號衰退未覆盤",
    "large_live_research_gap": "實際與研究落差偏大",
    "low_quality_data_used": "使用低品質資料",
    "regime_profile_mismatch": "市場狀態與設定不符",
}

SEVERITY_LABELS = {
    "low": "低",
    "medium": "中",
    "high": "高",
}

STATUS_LABELS = {
    "open": "待處理",
    "reviewed": "已覆盤",
    "dismissed": "已略過",
}

LABELS_BY_FIELD = {
    "item_type": ITEM_TYPE_LABELS,
    "severity": SEVERITY_LABELS,
    "status": STATUS_LABELS,
}


def display_label(field_name: str, value: object) -> str:
    """回傳有界標籤；未知及缺值保留可辨識的原值或未知提示。"""

    raw_value = "" if value is None else str(value)
    if not raw_value:
        return "未知"
    return LABELS_BY_FIELD.get(field_name, {}).get(raw_value, raw_value)


def label_with_raw_value(field_name: str, value: object) -> str:
    """詳情中顯示中文標籤並保留原始鍵；未知鍵仍原樣呈現。"""

    raw_value = "" if value is None else str(value)
    if not raw_value:
        return "未知"
    label = LABELS_BY_FIELD.get(field_name, {}).get(raw_value)
    if label is None:
        return f"{raw_value}（未知代碼）"
    return f"{label}（原始值：{raw_value}）"
