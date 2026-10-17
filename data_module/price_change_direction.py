"""日價差方向文字與 TWSE 原欄位正規化；不以顏色推斷金融值。"""

from __future__ import annotations

from html.parser import HTMLParser


CHANGE_SIGN_COLUMNS = ("漲跌(+/-)", "漲跌", "涨跌")
TWSE_DIRECTION_PARSER_ID = "twse.mi_index.direction_text.v2"
TWSE_PRICE_PARSER_IDS = frozenset({"twse.mi_index.v1", TWSE_DIRECTION_PARSER_ID})


def normalize_change_sign(value: object) -> str | None:
    """將已知繁中方向標記正規化；未知標記回傳 None。"""

    text = str(value or "").strip()
    if text in {"-", "−", "－", "跌", "▼"}:
        return "-"
    if text in {"+", "＋", "漲", "▲"}:
        return "+"
    return None


class _DirectionText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.unsupported = False

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # 僅接受原欄位的文字容器；script、隱藏內容等不作可見方向證據。
        if tag not in {"p", "span", "font", "b", "strong", "i", "em"}:
            self.unsupported = True
        for name, value in attrs:
            if name == "hidden" or (name == "style" and value is not None and any(
                marker in "".join(value.lower().split())
                for marker in ("display:none", "visibility:hidden")
            )):
                self.unsupported = True


def normalize_twse_change_sign(value: object) -> str:
    """保存四種狀態：+、-、空缺及 unknown；HTML/entity 只解碼一次。"""

    if value is None or (not isinstance(value, str) and str(value) in {"nan", "<NA>", "NaT"}):
        return ""
    raw = str(value).strip()
    if not raw:
        return ""
    parser = _DirectionText()
    try:
        parser.feed(raw)
        parser.close()
    except (ValueError, AssertionError):
        return "unknown"
    if parser.unsupported:
        return "unknown"
    return normalize_change_sign("".join(parser.parts).strip()) or "unknown"
