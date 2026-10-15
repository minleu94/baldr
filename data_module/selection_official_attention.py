"""TWSE 明示單日注意公告；原值、資料日與完整查詢範圍各自核驗。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from html.parser import HTMLParser
import json
import re
from typing import Any

from app_module.recommendation_portfolio_calendar_artifact_v1 import (
    _reject_constant, _reject_duplicate_keys, _reject_float, _validate_json_depth,
)

ATTENTION_PARSER_VERSION = "twse-attention-dated-report.v1"
ATTENTION_FIELDS = ("編號", "證券代號", "證券名稱", "累計次數", "注意交易資訊", "日期", "收盤價", "本益比")
MAX_ATTENTION_RAW_BYTES = 2 * 1024 * 1024
MAX_ATTENTION_ROWS = 10000


class OfficialAttentionError(ValueError):
    """來源或時鐘缺件時拒絕，不把空白回應當無注意事件。"""


@dataclass(frozen=True, slots=True)
class OfficialAttentionRow:
    stock_code: str
    stock_name: str
    announcement_date: str
    official_date_original_text: str
    announcement_count_original_text: str
    reason_original_text: str
    reason_text: str
    closing_price_original_text: str
    pe_original_text: str
    raw_row_sha256: str


@dataclass(frozen=True, slots=True)
class OfficialAttentionReport:
    query_date: str
    rows: tuple[OfficialAttentionRow, ...]
    raw_sha256: str
    declared_security_count: int
    declared_total: int
    parser_version: str = ATTENTION_PARSER_VERSION


def attention_query_parameters(query_date: date) -> dict[str, str]:
    value = query_date.strftime("%Y%m%d")
    return {"querytype": "1", "startDate": value, "endDate": value, "sortKind": "DATE", "response": "json"}


def attention_query_url(query_date: date) -> str:
    from urllib.parse import urlencode
    return "https://www.twse.com.tw/rwd/zh/announcement/notice?" + urlencode(attention_query_parameters(query_date))


def _load(raw: bytes) -> Any:
    if not raw or len(raw) > MAX_ATTENTION_RAW_BYTES:
        raise OfficialAttentionError("注意公告原件空白或超過大小上限")
    _validate_json_depth(raw)
    return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_reject_duplicate_keys,
                      parse_float=_reject_float, parse_constant=_reject_constant)


class _ReasonText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "font" or attrs != [("color", "#FF0000")]:
            raise OfficialAttentionError("注意理由含未確認的HTML格式")
        self.depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag != "font" or self.depth <= 0:
            raise OfficialAttentionError("注意理由HTML結尾不符")
        self.depth -= 1

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_comment(self, data: str) -> None:
        raise OfficialAttentionError("注意理由含未確認的HTML註解")


def parse_official_attention_report(raw: bytes, *, query_date: date, observed_date: date) -> OfficialAttentionReport:
    """只解析具日期完整查詢；金額／比率保留原字串，不進行金融計算。"""
    if query_date > observed_date:
        raise OfficialAttentionError("公告查詢日不得晚於實際取得日")
    payload = _load(raw)
    expected_params = {**attention_query_parameters(query_date), "controller": "announcement", "action": "notice",
                       "lang": "zh", "stockNo": "", "selectType": ""}
    roc = f"{query_date.year - 1911}年{query_date.month:02d}月{query_date.day:02d}日"
    title = f"公布注意有價證券資訊 ({roc} 至 {roc} 全部上市有價證券)"
    if (not isinstance(payload, dict) or set(payload) != {"count", "data", "fields", "params", "stat", "title", "total"}
            or payload.get("stat") != "OK" or payload.get("fields") != list(ATTENTION_FIELDS)
            or payload.get("params") != expected_params or payload.get("title") != title):
        raise OfficialAttentionError("需要同一公告日／TWSE完整範圍的官方報表；空白佔位不是無事件證明")
    source_rows = payload["data"]
    if not isinstance(source_rows, list) or len(source_rows) > MAX_ATTENTION_ROWS:
        raise OfficialAttentionError("注意公告資料列格式或上限不符")
    if any(type(payload[key]) is not int or payload[key] < 0 for key in ("count", "total")):
        raise OfficialAttentionError("注意公告宣告筆數必須是非負整數")
    if payload["total"] != len(source_rows):
        raise OfficialAttentionError("注意公告宣告總次數與完整原列數不符")
    rows: list[OfficialAttentionRow] = []
    seen: set[str] = set()
    expected_date = f"{query_date.year - 1911:03d}.{query_date.month:02d}.{query_date.day:02d}"
    for row in source_rows:
        if (not isinstance(row, list) or len(row) != len(ATTENTION_FIELDS) or type(row[0]) is not int or row[0] < 1
                or any(type(value) is not str for value in row[1:])):
            raise OfficialAttentionError("注意公告原列欄位／型別不符")
        _, code, name, count_text, reason, original_date, closing, pe = row
        if (not re.fullmatch(r"[0-9A-Z]{4,6}", code) or not name.strip() or len(name) > 128
                or not re.fullmatch(r"[0-9]{1,8}", count_text) or not reason.strip() or len(reason) > 16384
                or original_date != expected_date or not closing or len(closing) > 128 or not pe or len(pe) > 128
                or any("\x00" in value for value in row[1:])):
            raise OfficialAttentionError("注意公告代碼／日期／原值不符")
        if code in seen:
            raise OfficialAttentionError("單日注意公告有重複證券，不能當完整單日報表")
        seen.add(code)
        text = _ReasonText()
        text.feed(reason)
        text.close()
        if text.depth:
            raise OfficialAttentionError("注意理由HTML未完整結束")
        row_hash = sha256(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        rows.append(OfficialAttentionRow(code, name, query_date.isoformat(), original_date, count_text, reason,
            "".join(text.parts), closing, pe, row_hash))
    if payload["count"] != len(seen):
        raise OfficialAttentionError("注意公告宣告證券個數與原列代碼不符")
    return OfficialAttentionReport(query_date.isoformat(), tuple(rows), sha256(raw).hexdigest(), len(seen), len(rows))
