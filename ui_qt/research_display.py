"""研究紀錄的展示格式；不變更原件、排序值或來源身份。"""

from datetime import datetime
from zoneinfo import ZoneInfo


def research_saved_time(value: str) -> str:
    """以台北分鐘顯示已知時區的保存時間；未知時區不自行假設。"""
    if not value:
        return "未知"
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return value
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        return value + "（時區未提供）"
    return stamp.astimezone(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M") + "（台北）"
