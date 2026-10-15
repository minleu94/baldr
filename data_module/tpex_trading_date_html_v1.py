"""TPEx 年度開休市原件的純結構 HTML 解碼器。"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import hashlib
import re
from typing import NoReturn

from data_module.official_calendar_transport_v1 import (
    MAX_CALENDAR_RESPONSE_BYTES,
    OfficialCalendarTransportError,
    _payload,
)


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_ROWSPAN = re.compile(r"[0-9]{1,2}\Z")
_FORBIDDEN_TAGS = frozenset({"script", "iframe", "object", "embed"})
_SECTION_TAGS = frozenset({"thead", "tbody"})
_CELL_TAGS = frozenset({"td", "th"})
_INLINE_TAGS = frozenset({
    "a", "abbr", "b", "bdi", "bdo", "cite", "del", "dfn", "em", "i", "ins",
    "kbd", "mark", "q", "s", "small", "span", "strong", "sub", "sup", "u", "var",
})
_BR_MARKER = "\u0000"
_EXPECTED_HEADERS = ("紀念節日名稱", "日期", "星期", "說明")


class TpexTradingDateHtmlError(ValueError):
    """TPEx 年度原件不符合有界、明示的結構契約。"""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class TpexTradingDateRowV1:
    name: str
    date_text: str
    weekday_text: str
    description: str | None


@dataclass(frozen=True, slots=True)
class TpexTradingDateHtmlRowsV1:
    year: int
    raw_sha256: str
    html_sha256: str
    source_baseline_date: str
    rows: tuple[TpexTradingDateRowV1, ...]


@dataclass(frozen=True, slots=True)
class _Cell:
    tag: str
    text: str
    rowspan: int
    colspan: int


class _TpexHtmlParser(HTMLParser):
    """只收集兩個指定 table；不執行標記或解讀金融語義。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[_Cell]]] = []
        self._table: list[list[_Cell]] | None = None
        self._row: list[_Cell] | None = None
        self._cell_tag: str | None = None
        self._cell_parts: list[str] | None = None
        self._rowspan = 1
        self._colspan = 1
        self._inline_stack: list[str] = []
        self._section: str | None = None

    @staticmethod
    def _fail() -> NoReturn:
        raise TpexTradingDateHtmlError("tpex_trading_date_html_structure_invalid")

    @staticmethod
    def _attributes(attrs: list[tuple[str, str | None]]) -> dict[str, str | None]:
        result: dict[str, str | None] = {}
        for name, value in attrs:
            if name in result:
                _TpexHtmlParser._fail()
            result[name] = value
        return result

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attributes = self._attributes(attrs)
        if tag in _FORBIDDEN_TAGS:
            self._fail()
        if tag == "table":
            if self._table is not None or len(self.tables) >= 2:
                self._fail()
            self._table = []
            return
        if self._table is None:
            self._fail()
        if tag in _SECTION_TAGS:
            if self._section is not None or self._row is not None or self._cell_tag is not None:
                self._fail()
            self._section = tag
            return
        if tag == "tr":
            if self._row is not None or self._cell_tag is not None:
                self._fail()
            self._row = []
            return
        if tag in _CELL_TAGS:
            if self._row is None:
                self._fail()
            if self._cell_tag is not None:
                if self._inline_stack:
                    self._fail()
                # WHATWG 允許在下一個 td/th 前省略 cell 結尾；未閉合 inline 仍拒絕。
                self._finish_cell()
            if "rowspan" not in attributes:
                rowspan = 1
            else:
                rowspan_value = attributes["rowspan"]
                if type(rowspan_value) is not str or _ROWSPAN.fullmatch(rowspan_value) is None:
                    self._fail()
                rowspan = int(rowspan_value)
            if not 1 <= rowspan <= 64:
                self._fail()
            if "colspan" in attributes and attributes["colspan"] != "1":
                self._fail()
            self._cell_tag = tag
            self._cell_parts = []
            self._rowspan = rowspan
            self._colspan = 1
            self._inline_stack = []
            return
        if tag == "br":
            if self._cell_parts is None:
                self._fail()
            self._cell_parts.append(_BR_MARKER)
            return
        if tag in _INLINE_TAGS:
            if self._cell_parts is None:
                self._fail()
            self._inline_stack.append(tag)
            return
        self._fail()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.lower()
        self.handle_starttag(normalized, attrs)
        if normalized != "br":
            self.handle_endtag(normalized)

    def handle_data(self, data: str) -> None:
        if self._cell_parts is None:
            if data.strip():
                self._fail()
            return
        self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _FORBIDDEN_TAGS or tag == "br":
            self._fail()
        if tag == "table":
            if (self._table is None or self._row is not None or self._cell_tag is not None
                    or self._section is not None):
                self._fail()
            self.tables.append(self._table)
            self._table = None
            return
        if tag in _SECTION_TAGS:
            if self._section != tag or self._row is not None or self._cell_tag is not None:
                self._fail()
            self._section = None
            return
        if tag == "tr":
            if self._table is None or self._row is None:
                self._fail()
            if self._cell_tag is not None:
                if self._inline_stack:
                    self._fail()
                # 只在有效 </tr> 邊界隱式結束 cell；EOF 與其他父層邊界仍拒絕。
                self._finish_cell()
            self._table.append(self._row)
            self._row = None
            return
        if tag in _CELL_TAGS:
            if (self._row is None or self._cell_tag != tag or self._cell_parts is None
                    or self._inline_stack):
                self._fail()
            self._finish_cell()
            return
        if tag in _INLINE_TAGS:
            if self._cell_parts is None or not self._inline_stack or self._inline_stack[-1] != tag:
                self._fail()
            self._inline_stack.pop()
            return
        self._fail()

    def _finish_cell(self) -> None:
        if (self._row is None or self._cell_tag is None or self._cell_parts is None
                or self._inline_stack):
            self._fail()
        text = self._normalize_cell_text(self._cell_parts)
        self._row.append(_Cell(self._cell_tag, text, self._rowspan, self._colspan))
        self._cell_tag = None
        self._cell_parts = None
        self._rowspan = 1
        self._colspan = 1

    def handle_comment(self, data: str) -> None:
        # 註解不提供欄位內容；主動內容標記仍由 start tag 拒絕。
        del data

    def handle_pi(self, data: str) -> None:
        del data
        self._fail()

    @staticmethod
    def _normalize_cell_text(parts: list[str]) -> str:
        source = "".join(parts)
        return "\n".join(" ".join(line.split()) for line in source.split(_BR_MARKER))

    def finish(self) -> list[list[list[_Cell]]]:
        self.close()
        if (self._table is not None or self._row is not None or self._cell_tag is not None
                or self._section is not None or self._inline_stack or len(self.tables) != 2):
            self._fail()
        return self.tables


def _expand_rows(rows: list[list[_Cell]]) -> list[list[_Cell | None]]:
    expanded_rows: list[list[_Cell | None]] = []
    pending: dict[int, tuple[int, _Cell]] = {}
    for row in rows:
        if not row:
            raise TpexTradingDateHtmlError("tpex_trading_date_html_empty_row")
        occupied: dict[int, _Cell] = {}
        next_pending: dict[int, tuple[int, _Cell]] = {}
        for column, (remaining, cell) in pending.items():
            occupied[column] = cell
            if remaining > 1:
                next_pending[column] = (remaining - 1, cell)
        column = 0
        for cell in row:
            if cell.colspan != 1:
                raise TpexTradingDateHtmlError("tpex_trading_date_html_colspan_invalid")
            while column in occupied:
                column += 1
            occupied[column] = cell
            if cell.rowspan > 1:
                next_pending[column] = (cell.rowspan - 1, cell)
            column += 1
        width = max(occupied) + 1
        if width > 4 or any(index not in occupied for index in range(width)):
            raise TpexTradingDateHtmlError("tpex_trading_date_html_row_width_invalid")
        expanded_rows.append([occupied[index] for index in range(width)])
        pending = next_pending
    if pending:
        raise TpexTradingDateHtmlError("tpex_trading_date_html_rowspan_unresolved")
    return expanded_rows


def decode_tpex_trading_date_rows_v1(
    raw: bytes, *, expected_year: int, expected_sha256: str,
) -> TpexTradingDateHtmlRowsV1:
    """核對已保存年度原件，保留原始列；不裁決交易日或來源用途。"""
    if type(expected_year) is not int or not 1912 <= expected_year <= 2199:
        raise TpexTradingDateHtmlError("tpex_trading_date_year_invalid")
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_CALENDAR_RESPONSE_BYTES:
        raise TpexTradingDateHtmlError("tpex_trading_date_raw_size_invalid")
    if type(expected_sha256) is not str or _SHA256.fullmatch(expected_sha256) is None:
        raise TpexTradingDateHtmlError("tpex_trading_date_expected_sha_invalid")
    raw_sha256 = hashlib.sha256(raw).hexdigest()
    if raw_sha256 != expected_sha256:
        raise TpexTradingDateHtmlError("tpex_trading_date_raw_sha_mismatch")
    try:
        payload = _payload(raw)
    except OfficialCalendarTransportError as exc:
        raise TpexTradingDateHtmlError("tpex_trading_date_json_invalid") from exc
    if type(payload) is not dict or set(payload) != {"stat", "data", "endDate"}:
        raise TpexTradingDateHtmlError("tpex_trading_date_json_schema_invalid")
    stat, data, end_date = payload["stat"], payload["data"], payload["endDate"]
    if type(stat) is not str or stat != "ok" or type(data) is not dict or set(data) != {"html"}:
        raise TpexTradingDateHtmlError("tpex_trading_date_json_schema_invalid")
    html = data["html"]
    if (type(html) is not str or not html or type(end_date) is not str
            or end_date != f"{expected_year}0101"):
        raise TpexTradingDateHtmlError("tpex_trading_date_json_schema_invalid")
    try:
        html_raw = html.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise TpexTradingDateHtmlError("tpex_trading_date_html_unicode_invalid") from exc
    parser = _TpexHtmlParser()
    try:
        parser.feed(html)
        tables = parser.finish()
    except TpexTradingDateHtmlError:
        raise
    except (AssertionError, ValueError) as exc:
        raise TpexTradingDateHtmlError("tpex_trading_date_html_parse_failed") from exc
    expected_title = f"中華民國{expected_year - 1911}年有價證券櫃檯買賣市場開（休）市日期表"
    title_rows = tables[0]
    if len(title_rows) != 1 or len(title_rows[0]) != 1:
        raise TpexTradingDateHtmlError("tpex_trading_date_html_title_table_invalid")
    title_cell = title_rows[0][0]
    if title_cell.text != expected_title or title_cell.rowspan != 1 or title_cell.colspan != 1:
        raise TpexTradingDateHtmlError("tpex_trading_date_html_title_mismatch")

    source_rows = tables[1]
    if not source_rows or len(source_rows) - 1 > 256:
        raise TpexTradingDateHtmlError("tpex_trading_date_html_body_row_limit")
    header = source_rows[0]
    if (len(header) != 4 or any(cell.tag != "th" for cell in header)
            or any(cell.rowspan != 1 or cell.colspan != 1 for cell in header)
            or tuple(cell.text for cell in header) != _EXPECTED_HEADERS):
        raise TpexTradingDateHtmlError("tpex_trading_date_html_header_mismatch")
    body_rows = source_rows[1:]
    if any(any(cell.tag != "td" for cell in row) for row in body_rows):
        raise TpexTradingDateHtmlError("tpex_trading_date_html_body_cell_tag_invalid")
    expanded_body = _expand_rows(body_rows)
    result_rows: list[TpexTradingDateRowV1] = []
    for row in expanded_body:
        if len(row) == 3:
            row.append(None)
        if len(row) != 4 or any(cell is None for cell in row[:3]):
            raise TpexTradingDateHtmlError("tpex_trading_date_html_body_row_width_invalid")
        name, date_text, weekday_text = row[0], row[1], row[2]
        description = row[3]
        if (name is None or date_text is None or weekday_text is None
                or not name.text or not date_text.text or not weekday_text.text):
            raise TpexTradingDateHtmlError("tpex_trading_date_html_required_cell_empty")
        result_rows.append(TpexTradingDateRowV1(
            name=name.text, date_text=date_text.text, weekday_text=weekday_text.text,
            description=description.text if description is not None else None,
        ))
    return TpexTradingDateHtmlRowsV1(
        year=expected_year, raw_sha256=raw_sha256,
        html_sha256=hashlib.sha256(html_raw).hexdigest(),
        source_baseline_date=end_date, rows=tuple(result_rows),
    )
