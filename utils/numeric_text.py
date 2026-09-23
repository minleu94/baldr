"""純文字數值正規化；不補缺值、不執行浮點數或金融計算。"""

from __future__ import annotations

import re


_GROUPED_DECIMAL = re.compile(r"[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?", flags=re.ASCII)


def normalize_grouped_numeric_text(value: object) -> object:
    """只移除合法十進位千分位逗號；壞格式原樣交給既有缺值檢查。"""
    if not isinstance(value, str) or "," not in value:
        return value
    stripped = value.strip()
    if _GROUPED_DECIMAL.fullmatch(stripped) is None:
        return value
    return stripped.replace(",", "")
