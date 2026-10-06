"""UX02 純呈現詞彙；不推論資格、資料日期或股票風險。"""

from __future__ import annotations


_COMMON = {
    "missing": "資料缺件", "source_missing": "來源缺件",
    "degraded": "品質降級", "research_only_degraded": "研究限定／品質降級",
    "partial": "部分可用（資料缺件）",
    "machine_degraded": "品質降級", "stale": "資料較舊",
    "failed": "執行錯誤", "error": "執行錯誤",
    "loading": "載入中", "running": "執行中", "cancelled": "已取消",
    "waiting_for_time": "尚未到期", "not_due": "尚未到期",
    "market_closed": "休市跳過", "skipped_market_closed": "休市跳過",
    "skipped_non_trading_day": "休市跳過",
    "pending": "待確認", "unknown": "未知", "blocked": "受阻",
    "warning": "警告", "critical": "嚴重警告",
    "unavailable": "無法判讀", "not_ready": "尚未就緒",
    "formal_input_missing": "正式輸入缺件", "formal_inputs_missing": "正式輸入缺件",
    "waiting_for_formal_inputs": "等待正式輸入",
    "research_only": "正式資格未具備（研究限定）",
    "fitted_research_only": "研究訓練完成／正式資格未具備",
}
_DIMENSIONS = {
    "data": {"observed": "可供研究判讀", "ok": "可供研究判讀", "ready": "可供研究判讀"},
    "load": {"completed": "載入完成", "success": "載入完成", "ready": "載入完成"},
    "research": {"completed": "研究完成", "success": "研究完成", "observed": "已觀測"},
    "qualification": {"research_only": "正式資格未具備（研究限定）"},
    "event": {},
    "validation": {"pass": "驗證通過", "warning": "驗證有警告", "fail": "驗證未通過"},
}


def status_label(raw: object, *, dimension: str = "data") -> str:
    """只翻譯明確的碼；未知碼保留，completed 須有具名維度。"""
    value = getattr(raw, "value", raw)
    text = str(value if value is not None else "unknown").strip() or "unknown"
    key = text.lower()
    return _DIMENSIONS.get(dimension, {}).get(key, _COMMON.get(key, text))


def status_detail(raw: object, *, dimension: str = "data") -> str:
    """詳情保留來源原碼，與摘要使用同一詞彙。"""
    value = getattr(raw, "value", raw)
    text = str(value if value is not None else "unknown").strip() or "unknown"
    label = status_label(raw, dimension=dimension)
    return f"{label}（原始狀態：{text}）"
