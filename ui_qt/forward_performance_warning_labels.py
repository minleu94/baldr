from __future__ import annotations

from collections.abc import Mapping


FORWARD_WARNING_LABELS = {
    "corporate_action_source_not_ingested": "企業行動資料來源尚未納入",
    "trading_restriction_source_not_ingested": "交易限制資料來源尚未納入",
    "source_not_ingested": "來源尚未完成納入（類型未細分）",
    "forward_summary_status:DEGRADED": "前瞻摘要品質降級",
    "missing_event_price": "缺少事件日收盤價",
    "missing_outcome_price": "缺少觀察目標日收盤價",
    "missing_benchmark": "缺少大盤基準",
    "missing_industry_benchmark": "缺少產業基準",
    "insufficient_future_data": "未取得完整觀察期間資料",
}


def format_forward_warning_counts(counts: Mapping[str, int]) -> str:
    """以中文說明已知警告，同時保留原碼與精確筆數。"""
    parts = []
    for code, count in sorted(counts.items()):
        label = FORWARD_WARNING_LABELS.get(code)
        display_code = f"{label}（{code}）" if label else code
        parts.append(f"{display_code}:{count}")
    return ", ".join(parts) or "無"
