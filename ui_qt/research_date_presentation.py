"""研究畫面的來源資料日；不拿判讀日或主機日期補缺。"""

from datetime import date


def source_data_date_text(value: object, *, cutoff: object = None) -> str:
    """只呈現明示、正規的資料日；有截止日時另拒絕未來來源。"""
    if type(value) is date:
        parsed = value
    elif isinstance(value, str) and len(value) == 10:
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            return "未知"
        if parsed.isoformat() != value:
            return "未知"
    else:
        return "未知"
    if cutoff is not None and (type(cutoff) is not date or parsed > cutoff):
        return "未知"
    return parsed.isoformat()
