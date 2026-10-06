"""官方市場狀態的即時觀測。

此契約與歷史市場事件回補分開，並將上市名錄、終止上市公告和交易限制保留
為獨立證據。缺少報價或名錄列不得推論為停牌或下市。本模組的擷取結果僅供
現況註記，不能用於時間點回放（PIT）。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo


SCHEMA_VERSION = "current-market-status-observation.v1"
SCOPE = "current_only"
PIT_ELIGIBLE = False
SHA256_PREFIX = "sha256:"
_SYMBOL_RE = re.compile(r"^\d{4,6}$")
_CODE_IN_TEXT_RE = re.compile(r"^\s*(\d{4,6})\b")
_ROC_DATE_RE = re.compile(r"(?P<year>\d{2,4})\s*(?:年|/|-|\.\s*)\s*(?P<month>\d{1,2})\s*(?:月|/|-|\.\s*)\s*(?P<day>\d{1,2})\s*日?")


class CurrentMarketStatusError(ValueError):
    """現況快照格式錯誤或違反範圍限制。"""


@dataclass(frozen=True)
class OfficialMarketNoticeStatement:
    """由官方公告正文解析出的有限狀態聲明。"""

    symbol: str
    statement_type: str
    published_date: date
    effective_date: date
    notice_reference: str
    market: str
    name: str | None
    details: str
    effective_to: date | None = None
    resumed_on: date | None = None


_TPEX_NOTICE_PATH_RE = re.compile(
    r"^/storage/eb_data/\d{5}/\d{11,12}\.html?$", re.IGNORECASE
)
_TWSE_NOTICE_API_PATH = "/rwd/zh/announcement/announcement_detail"
_TWSE_NOTICE_ID_RE = re.compile(r"^[A-F0-9]{32}$")
_ROC_DATE_TOKEN_RE = re.compile(
    r"(?P<year>\d{2,4})\s*(?:年|/|-|\.\s*)\s*"
    r"(?P<month>\d{1,2})\s*(?:月|/|-|\.\s*)\s*"
    r"(?P<day>\d{1,2})\s*日?"
)


def validate_official_notice_url(source_url: str) -> None:
    """只允許 TPEx 官方儲存區的公文原件 URL。"""
    parsed_url = urlsplit(source_url)
    if (
        parsed_url.scheme == "https"
        and parsed_url.hostname == "www.twse.com.tw"
        and parsed_url.path == _TWSE_NOTICE_API_PATH
        and not parsed_url.fragment
    ):
        from urllib.parse import parse_qsl

        query_items = parse_qsl(parsed_url.query, keep_blank_values=True)
        query = dict(query_items)
        if (
            len(query_items) == 2
            and len(query) == 2
            and set(query) == {"id", "response"}
            and _TWSE_NOTICE_ID_RE.fullmatch(query.get("id", ""))
            and query.get("response") == "json"
        ):
            return
    if (
        parsed_url.scheme != "https"
        or parsed_url.hostname not in {"www.tpex.org.tw", "tpex.org.tw"}
        or parsed_url.query
        or parsed_url.fragment
        or not _TPEX_NOTICE_PATH_RE.fullmatch(parsed_url.path)
    ):
        raise CurrentMarketStatusError("official_notice_url_not_allowlisted")


def _official_notice_visible_text(raw: bytes) -> str:
    """抽取公告 HTML 可見文字，略過樣式與指令碼區塊。"""
    from html.parser import HTMLParser

    class _VisibleText(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.parts: list[str] = []
            self._ignored_depth = 0

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag.lower() in {"style", "script", "noscript"}:
                self._ignored_depth += 1

        def handle_endtag(self, tag: str) -> None:
            if tag.lower() in {"style", "script", "noscript"} and self._ignored_depth:
                self._ignored_depth -= 1

        def handle_data(self, data: str) -> None:
            if self._ignored_depth:
                return
            cleaned = _text(data)
            if cleaned:
                self.parts.append(cleaned)

    parser = _VisibleText()
    parser.feed(raw.decode("utf-8-sig", errors="strict"))
    return "\n".join(parser.parts)


def _notice_field_date(text: str, field_name: str) -> date:
    pattern = re.compile(re.escape(field_name) + r"\s*[:：]?\s*(?:中華民國)?")
    match = pattern.search(text)
    if match is None:
        raise CurrentMarketStatusError(f"official_notice_{field_name}_missing")
    date_match = _ROC_DATE_TOKEN_RE.search(text, match.end(), match.end() + 64)
    if date_match is None:
        raise CurrentMarketStatusError(f"official_notice_{field_name}_invalid")
    parsed = parse_source_date(date_match.group(0))
    if parsed is None:
        raise CurrentMarketStatusError(f"official_notice_{field_name}_invalid")
    return parsed


def _notice_clauses(text: str) -> list[str]:
    return [
        clause.strip()
        for clause in re.split(r"[\r\n。；;，,]+", text)
        if clause.strip()
    ]


def _notice_effective_date(clause: str, statement_type: str) -> date | None:
    if "申請" in clause or "申報" in clause:
        return None
    if statement_type == "trading_suspension":
        marker = re.search(r"(?:停止|暫停)[^。；;，,\r\n]{0,24}(?:櫃檯買賣|上櫃買賣|上市買賣|股票交易|交易)", clause)
        if marker is None:
            marker = re.search(r"(?:櫃檯買賣|上櫃買賣|上市買賣|股票交易|交易)[^。；;，,\r\n]{0,24}(?:停止|暫停)", clause)
    else:
        marker = re.search(r"終止[^。；;，,\r\n]{0,18}(?:櫃檯買賣|上櫃|上市)", clause)
        if marker is None:
            marker = re.search(r"(?:櫃檯買賣|上櫃|上市)[^。；;，,\r\n]{0,18}終止", clause)
    if marker is None:
        return None
    dates = list(_ROC_DATE_TOKEN_RE.finditer(clause))
    if not dates:
        return None
    nearest = min(dates, key=lambda item: min(abs(item.start() - marker.start()), abs(item.start() - marker.end())))
    parsed = parse_source_date(nearest.group(0))
    if parsed is None:
        return None
    return parsed


def _parse_twse_announcement_notice(
    raw: bytes,
    *,
    source_url: str,
    observed_at: datetime,
) -> tuple[OfficialMarketNoticeStatement, ...]:
    validate_official_notice_url(source_url)
    try:
        payload = json.loads(raw.decode("utf-8-sig", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CurrentMarketStatusError("twse_notice_json_invalid") from error
    if not isinstance(payload, Mapping) or str(payload.get("stat", "")).lower() != "ok":
        raise CurrentMarketStatusError("twse_notice_api_not_success")
    fields = payload.get("fields")
    rows = payload.get("data")
    required_fields = {"發文機關", "發文日期", "發文字號", "主旨", "公告事項"}
    if (
        not isinstance(fields, list)
        or not all(isinstance(item, str) for item in fields)
        or len(set(fields)) != len(fields)
        or not required_fields.issubset(fields)
        or not isinstance(rows, list)
        or len(rows) != 1
        or not isinstance(rows[0], list)
        or len(rows[0]) != len(fields)
    ):
        raise CurrentMarketStatusError("twse_notice_api_schema_invalid")
    row = dict(zip(fields, rows[0]))
    issuer = _text(row.get("發文機關"))
    publication_text = _text(row.get("發文日期"))
    reference_text = _text(row.get("發文字號"))
    subject = _text(row.get("主旨"))
    details = str(row.get("公告事項") or "").strip()
    if "臺灣證券交易所" not in issuer or not details:
        raise CurrentMarketStatusError("twse_notice_official_issuer_or_details_missing")
    publication_match = _ROC_DATE_TOKEN_RE.search(publication_text)
    if publication_match is None:
        raise CurrentMarketStatusError("twse_notice_publication_date_missing")
    published_date = parse_source_date(publication_match.group(0))
    if published_date is None:
        raise CurrentMarketStatusError("twse_notice_publication_date_invalid")
    reference_match = re.search(r"[\u4e00-\u9fffA-Za-z]{2,20}第\d{8,12}號", reference_text)
    if reference_match is None:
        raise CurrentMarketStatusError("twse_notice_reference_invalid")
    notice_reference = reference_match.group(0)
    codes = set(re.findall(r"公司代號\s*[:：]\s*(\d{4,6})\b", subject))
    if len(codes) != 1:
        raise CurrentMarketStatusError("twse_notice_subject_symbol_ambiguous_or_missing")
    symbol = next(iter(codes))
    if not _SYMBOL_RE.fullmatch(symbol):
        raise CurrentMarketStatusError("twse_notice_subject_symbol_invalid")
    taipei_today = observed_at.astimezone(ZoneInfo("Asia/Taipei")).date()
    if published_date > taipei_today:
        raise CurrentMarketStatusError("twse_notice_publication_after_capture")

    clauses = [part.strip() for part in re.split(r"[\r\n]+", details) if part.strip()]
    suspension_clause = next(
        (
            clause
            for clause in clauses
            if "舊股票停止在市場買賣日期" in clause
            or "舊股票停止上市買賣日期" in clause
        ),
        None,
    )
    if suspension_clause is None:
        raise CurrentMarketStatusError("twse_notice_explicit_suspension_period_missing")
    suspension_dates = [
        parse_source_date(match.group(0))
        for match in _ROC_DATE_TOKEN_RE.finditer(suspension_clause)
    ]
    valid_suspension_dates = [item for item in suspension_dates if item is not None]
    if len(valid_suspension_dates) != 2 or valid_suspension_dates[1] < valid_suspension_dates[0]:
        raise CurrentMarketStatusError("twse_notice_suspension_period_invalid")

    resume_clause = next(
        (
            clause
            for clause in clauses
            if "新股票上市開始買賣" in clause
            or "新股票開始上市買賣" in clause
        ),
        None,
    )
    resumed_on: date | None = None
    if resume_clause is not None:
        resume_dates = [
            parse_source_date(match.group(0))
            for match in _ROC_DATE_TOKEN_RE.finditer(resume_clause)
        ]
        valid_resume_dates = [item for item in resume_dates if item is not None]
        if len(valid_resume_dates) == 1:
            resumed_on = valid_resume_dates[0]

    return (
        OfficialMarketNoticeStatement(
            symbol=symbol,
            statement_type="trading_suspension",
            published_date=published_date,
            effective_date=valid_suspension_dates[0],
            effective_to=valid_suspension_dates[1],
            resumed_on=resumed_on,
            notice_reference=notice_reference,
            market="twse",
            name=None,
            details=suspension_clause[:600],
        ),
    )


def parse_official_market_notice(
    raw: bytes,
    *,
    source_url: str,
    observed_at: datetime,
) -> tuple[OfficialMarketNoticeStatement, ...]:
    """解析 TPEx 官方公文，只辨識正文中明確的停交易及終止聲明。"""
    if urlsplit(source_url).hostname == "www.twse.com.tw":
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise CurrentMarketStatusError("official_notice_observed_at_must_be_timezone_aware")
        return _parse_twse_announcement_notice(
            raw,
            source_url=source_url,
            observed_at=observed_at,
        )
    validate_official_notice_url(source_url)
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise CurrentMarketStatusError("official_notice_observed_at_must_be_timezone_aware")

    text = _official_notice_visible_text(raw)
    if "財團法人中華民國證券櫃檯買賣中心" not in text or not re.search(r"(?:^|\n)公告(?:\n|$)", text):
        raise CurrentMarketStatusError("official_notice_issuer_marker_missing")
    published_date = _notice_field_date(text, "發文日期")
    reference_match = re.search(r"證櫃[\w\u4e00-\u9fff]{0,8}字第\d{8,12}號", text)
    if reference_match is None:
        raise CurrentMarketStatusError("official_notice_reference_missing")
    notice_reference = reference_match.group(0)

    subject_match = re.search(r"主旨\s*[:：]?\s*(.*?)(?=\n\s*依據\s*[:：]?|$)", text, re.DOTALL)
    if subject_match is None:
        raise CurrentMarketStatusError("official_notice_subject_missing")
    subject = _text(subject_match.group(1))
    code_matches = set(
        re.findall(
            r"(?:證券|股票)\s*代號\s*[:：]?\s*[（(]?\s*(\d{4,6})\b",
            subject,
        )
    )
    if len(code_matches) != 1:
        raise CurrentMarketStatusError("official_notice_subject_symbol_ambiguous_or_missing")
    symbol = next(iter(code_matches))
    if not _SYMBOL_RE.fullmatch(symbol):
        raise CurrentMarketStatusError("official_notice_subject_symbol_invalid")

    company_match = re.search(
        r"([\u4e00-\u9fffA-Za-z0-9]{2,32}(?:股份有限公司|有限公司|公司))",
        subject,
    )
    name = _text(company_match.group(1)) if company_match else None
    if name:
        name = re.sub(r"^公告\s*", "", name)
    if published_date > observed_at.astimezone(ZoneInfo("Asia/Taipei")).date():
        raise CurrentMarketStatusError("official_notice_publication_after_capture")
    clauses = _notice_clauses(text)
    statements: dict[tuple[str, date], OfficialMarketNoticeStatement] = {}
    for clause in clauses:
        for statement_type in ("trading_suspension", "listing_termination"):
            effective_date = _notice_effective_date(clause, statement_type)
            if effective_date is None:
                continue
            statement = OfficialMarketNoticeStatement(
                symbol=symbol,
                statement_type=statement_type,
                published_date=published_date,
                effective_date=effective_date,
                notice_reference=notice_reference,
                market="tpex",
                name=name,
                details=clause[:600],
            )
            statements[(statement_type, effective_date)] = statement
    if not statements:
        raise CurrentMarketStatusError("official_notice_has_no_typed_market_status_statement")
    return tuple(
        statements[key]
        for key in sorted(statements, key=lambda item: (item[1], item[0]))
    )


def sha256_bytes(value: bytes) -> str:
    return SHA256_PREFIX + hashlib.sha256(value).hexdigest()


def parse_source_date(value: object) -> date | None:
    """解析來源明確提供的西元或民國日期。"""
    text = str(value or "").strip()
    compact = re.fullmatch(r"(?P<year>\d{7,8})", text)
    if compact:
        digits = compact.group("year")
        if len(digits) == 8:
            year = int(digits[:4])
            month = int(digits[4:6])
            day = int(digits[6:8])
        else:
            year = int(digits[:3]) + 1911
            month = int(digits[3:5])
            day = int(digits[5:7])
        try:
            return date(year, month, day)
        except ValueError:
            return None
    match = _ROC_DATE_RE.search(text)
    if match is None:
        return None
    year = int(match.group("year"))
    if year < 1912:
        year += 1911
    try:
        return date(year, int(match.group("month")), int(match.group("day")))
    except ValueError:
        return None


def _text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _norm_key(value: object) -> str:
    return re.sub(r"[\s_\-（）()：:、,./]+", "", str(value or "")).lower()


_CODE_KEYS = {
    _norm_key(value)
    for value in (
        "公司代號", "公司代碼", "股票代號", "證券代號", "有價證券代號",
        "證券代碼", "代號", "上市編號", "上櫃代號", "SecuritiesCode", "SecuritiesCompanyCode", "SecurityCode", "StockCode",
        "公司代號及名稱", "證券代號及名稱", "股票代號及名稱",
        "CompanyCode", "Code", "Symbol",
    )
}
_NAME_KEYS = {
    _norm_key(value)
    for value in (
        "公司名稱", "公司簡稱", "證券名稱", "有價證券名稱", "股票名稱",
        "SecuritiesName", "SecurityName", "StockName", "CompanyName", "Name",
    )
}
_SOURCE_DATE_KEYS = {
    _norm_key(value)
    for value in ("出表日期", "資料日期", "統計日期", "更新日期")
}
_START_DATE_KEYS = {
    _norm_key(value)
    for value in (
        "暫停交易起日", "停止交易起日", "停牌起日", "生效日期", "生效日",
        "開始日期", "開始日", "起始日期", "起日", "生效日(起)",
        "暫停交易日期", "DateOfSuspendedTrading",
    )
}
_END_DATE_KEYS = {
    _norm_key(value)
    for value in (
        "暫停交易迄日", "停止交易迄日", "停牌迄日",
        "終止日期", "終止日", "迄日", "截止日期", "最後交易日",
    )
}
_TERMINATION_DATE_KEYS = {
    _norm_key(value)
    for value in ("終止上市日期", "終止上櫃日期", "下櫃日期", "終止日期", "TerminationDate", "DelistingDate")
}
_RESUME_DATE_KEYS = {
    _norm_key(value)
    for value in ("恢復交易日", "恢復交易日期", "復牌日", "復牌日期", "DateOfResumedTrading")
}


def extract_symbol(row: Mapping[str, object]) -> str | None:
    for key, value in row.items():
        if _norm_key(key) in _CODE_KEYS:
            match = _CODE_IN_TEXT_RE.match(_text(value))
            candidate = match.group(1) if match else _text(value)
            if _SYMBOL_RE.fullmatch(candidate):
                return candidate
    return None


def extract_name(row: Mapping[str, object]) -> str | None:
    for key, value in row.items():
        if _norm_key(key) in _NAME_KEYS and _text(value):
            return _text(value)
    return None


def _field_value(row: Mapping[str, object], aliases: set[str]) -> object | None:
    for key, value in row.items():
        if _norm_key(key) in aliases and _text(value):
            return value
    return None


def extract_row_dates(row: Mapping[str, object]) -> tuple[date | None, date | None]:
    start = parse_source_date(_field_value(row, _START_DATE_KEYS))
    end = parse_source_date(_field_value(row, _END_DATE_KEYS))
    return start, end


def extract_termination_date(row: Mapping[str, object]) -> date | None:
    return parse_source_date(_field_value(row, _TERMINATION_DATE_KEYS))


def extract_resume_date(row: Mapping[str, object]) -> date | None:
    """解析復牌日期；此日期不代表最後一個停牌日。"""
    return parse_source_date(_field_value(row, _RESUME_DATE_KEYS))


def explicit_source_dates(rows: Sequence[Mapping[str, object]]) -> list[str]:
    """只回傳來源標示的資料日期；事件生效日另行保存。"""
    found: set[str] = set()
    for row in rows:
        value = _field_value(row, _SOURCE_DATE_KEYS)
        parsed = parse_source_date(value)
        if parsed is not None:
            found.add(parsed.isoformat())
    return sorted(found)


def source_dates_for_aliases(
    rows: Sequence[Mapping[str, object]], aliases: Sequence[str]
) -> list[str]:
    normalized_aliases = {_norm_key(alias) for alias in aliases}
    found: set[str] = set()
    for row in rows:
        value = _field_value(row, normalized_aliases)
        parsed = parse_source_date(value)
        if parsed is not None:
            found.add(parsed.isoformat())
    return sorted(found)


def explicit_payload_source_dates(raw: bytes) -> list[str]:
    """只讀取來源層級的日期中繼資料，不讀取列級事件日期。"""
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return []
    if not isinstance(payload, Mapping):
        return []
    source_keys = _SOURCE_DATE_KEYS | {_norm_key("date"), _norm_key("資料基準日")}
    found: set[str] = set()
    for key, value in payload.items():
        if _norm_key(key) in source_keys:
            parsed = parse_source_date(value)
            if parsed is not None:
                found.add(parsed.isoformat())
    return sorted(found)


def _decode_tpex_terminated_listing_tables(
    payload: Mapping[str, object],
) -> list[dict[str, object]]:
    """Decode TPEx official tables without accepting partial rows."""
    if str(payload.get("stat", "")).strip().casefold() != "ok":
        raise CurrentMarketStatusError("tpex_terminated_listing_api_not_success")
    tables = payload.get("tables")
    if not isinstance(tables, list) or len(tables) != 1 or not isinstance(tables[0], Mapping):
        raise CurrentMarketStatusError("tpex_terminated_listing_tables_invalid")
    table = tables[0]
    fields = table.get("fields")
    rows = table.get("data")
    required_fields = {
        _norm_key("股票代號"),
        _norm_key("公司名稱"),
        _norm_key("終止上櫃日期"),
        _norm_key("終止上櫃原因"),
        _norm_key("公司資料網址"),
    }
    if (
        not isinstance(fields, list)
        or not fields
        or not all(isinstance(field, str) and field.strip() for field in fields)
    ):
        raise CurrentMarketStatusError("tpex_terminated_listing_fields_invalid")
    normalized_fields = [_norm_key(field) for field in fields]
    if (
        len(set(normalized_fields)) != len(normalized_fields)
        or not required_fields.issubset(normalized_fields)
    ):
        raise CurrentMarketStatusError("tpex_terminated_listing_required_fields_missing")
    if not isinstance(rows, list) or not rows:
        raise CurrentMarketStatusError("tpex_terminated_listing_table_empty")
    mapped_rows: list[dict[str, object]] = []
    termination_key = next(field for field in fields if _norm_key(field) == _norm_key("終止上櫃日期"))
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) != len(fields):
            raise CurrentMarketStatusError("tpex_terminated_listing_row_shape_invalid")
        record = dict(zip(fields, row))
        if extract_symbol(record) is None or extract_name(record) is None:
            raise CurrentMarketStatusError("tpex_terminated_listing_identity_missing")
        termination_value = record.get(termination_key)
        if not isinstance(termination_value, str) or parse_source_date(termination_value) is None:
            raise CurrentMarketStatusError("tpex_terminated_listing_date_invalid")
        mapped_rows.append(record)
    total_count = table.get("totalCount")
    if total_count is not None and (
        isinstance(total_count, bool)
        or not isinstance(total_count, int)
        or total_count != len(mapped_rows)
    ):
        raise CurrentMarketStatusError("tpex_terminated_listing_total_count_invalid")
    return mapped_rows


def decode_official_rows(raw: bytes, content_type: str = "") -> list[dict[str, object]]:
    """解析常見的 TWSE／TPEx JSON 結構與靜態 HTML 表格。

    遇到未知回應結構時採取封閉失敗。呼叫端保留原始擷取並標記解析不可用，
    不會把空結果當成狀態證據。
    """
    text = raw.decode("utf-8-sig", errors="replace")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None
    if payload is not None:
        if isinstance(payload, list) and all(isinstance(item, dict) for item in payload):
            return [dict(item) for item in payload]
        if isinstance(payload, dict):
            if "tables" in payload:
                return _decode_tpex_terminated_listing_tables(payload)
            for key in ("data", "result", "records", "rows"):
                value = payload.get(key)
                if isinstance(value, list):
                    fields = payload.get("fields") or payload.get("columns")
                    if (
                        isinstance(fields, list)
                        and fields
                        and all(isinstance(field, str) for field in fields)
                        and all(isinstance(item, (list, tuple)) for item in value)
                    ):
                        return [dict(zip(fields, item)) for item in value]
                    if all(isinstance(item, dict) for item in value):
                        return [dict(item) for item in value]
                    if value and all(isinstance(item, (list, tuple)) for item in value):
                        # TWSE 回應常將欄位定義包在內層區段。
                        for section in payload.get("data", []):
                            if isinstance(section, dict) and isinstance(section.get("fields"), list):
                                section_rows = section.get("data", [])
                                if isinstance(section_rows, list) and all(isinstance(item, (list, tuple)) for item in section_rows):
                                    return [dict(zip(section["fields"], item)) for item in section_rows]
                    if not value:
                        return []
            # TWSE 也可能在 data 陣列中以單一表格項目包住 fields 和 data。
            sections = payload.get("data")
            if isinstance(sections, list):
                for section in sections:
                    if isinstance(section, dict) and isinstance(section.get("fields"), list):
                        section_rows = section.get("data", [])
                        if isinstance(section_rows, list) and all(isinstance(item, (list, tuple)) for item in section_rows):
                            return [dict(zip(section["fields"], item)) for item in section_rows]
            if payload.get("stat") not in (None, "OK", "200", 200) and not payload.get("data"):
                raise CurrentMarketStatusError("official_json_reports_non_success")
    if "html" in content_type.lower() or "<table" in text.lower():
        return _decode_html_tables(text)
    raise CurrentMarketStatusError("official_response_schema_unrecognized")


def _decode_html_tables(text: str) -> list[dict[str, object]]:
    from html.parser import HTMLParser

    class _Tables(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.tables: list[list[list[str]]] = []
            self._row: list[str] | None = None
            self._cell: list[str] | None = None
            self._inside_table = False

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag.lower() == "table":
                self._inside_table = True
                self.tables.append([])
            elif self._inside_table and tag.lower() == "tr":
                self._row = []
            elif self._inside_table and tag.lower() in {"th", "td"}:
                self._cell = []

        def handle_data(self, data: str) -> None:
            if self._cell is not None:
                self._cell.append(data)

        def handle_endtag(self, tag: str) -> None:
            tag = tag.lower()
            if self._inside_table and tag in {"th", "td"} and self._cell is not None:
                if self._row is not None:
                    self._row.append(_text("".join(self._cell)))
                self._cell = None
            elif self._inside_table and tag == "tr" and self._row is not None:
                if any(self._row):
                    self.tables[-1].append(self._row)
                self._row = None
            elif tag == "table" and self._inside_table:
                self._inside_table = False

    parser = _Tables()
    parser.feed(text)
    result: list[dict[str, object]] = []
    for table in parser.tables:
        if len(table) < 2:
            continue
        header_index = next(
            (
                index
                for index, row in enumerate(table)
                if any(_norm_key(header) in _CODE_KEYS for header in row)
                and any(
                    _norm_key(header) in _TERMINATION_DATE_KEYS
                    or _norm_key(header) in {_norm_key("暫停交易起日"), _norm_key("停止交易日期")}
                    for header in row
                )
            ),
            None,
        )
        if header_index is None:
            header_index = next(
                (index for index, row in enumerate(table) if any(_norm_key(header) in _CODE_KEYS for header in row)),
                None,
            )
        if header_index is None:
            continue
        headers = table[header_index]
        for values in table[header_index + 1 :]:
            if len(values) == len(headers) and extract_symbol(dict(zip(headers, values))):
                result.append(dict(zip(headers, values)))
    if not result:
        raise CurrentMarketStatusError("official_html_table_schema_unrecognized")
    return result


@dataclass(frozen=True)
class MarketStatusEvidence:
    symbol: str
    source_id: str
    evidence_type: str
    observed_at: str
    raw_sha256: str
    source_url: str
    source_data_dates: tuple[str, ...] = ()
    effective_from: str | None = None
    effective_to: str | None = None
    resumed_on: str | None = None
    market: str | None = None
    name: str | None = None
    details: str | None = None
    restriction_type: str | None = None
    restriction_state: str | None = None
    published_date: str | None = None
    notice_reference: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "source_id": self.source_id,
            "evidence_type": self.evidence_type,
            "observed_at": self.observed_at,
            "raw_sha256": self.raw_sha256,
            "source_url": self.source_url,
            "source_data_dates": list(self.source_data_dates),
            "effective_from": self.effective_from,
            "effective_to": self.effective_to,
            "resumed_on": self.resumed_on,
            "market": self.market,
            "name": self.name,
            "details": self.details,
            "restriction_type": self.restriction_type,
            "restriction_state": self.restriction_state,
            "published_date": self.published_date,
            "notice_reference": self.notice_reference,
        }


def build_snapshot(
    *,
    observed_at: datetime,
    source_captures: Sequence[Mapping[str, object]],
    evidence: Sequence[MarketStatusEvidence],
) -> dict[str, object]:
    """建立僅供現況使用的快照；缺少證據時一律保留為未知。"""
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise CurrentMarketStatusError("observed_at_must_be_timezone_aware")
    utc_observed = observed_at.astimezone(timezone.utc).isoformat()
    taipei_observed_date = observed_at.astimezone(ZoneInfo("Asia/Taipei")).date()
    per_symbol: dict[str, list[MarketStatusEvidence]] = {}
    for item in evidence:
        if not _SYMBOL_RE.fullmatch(item.symbol):
            raise CurrentMarketStatusError("invalid_symbol_in_evidence")
        per_symbol.setdefault(item.symbol, []).append(item)

    securities: list[dict[str, object]] = []
    for symbol in sorted(per_symbol):
        entries = per_symbol[symbol]
        listing = [
            item for item in entries
            if item.evidence_type in {"current_roster", "current_market_status_report", "terminated"}
        ]
        rosters = [
            item for item in listing
            if item.evidence_type in {"current_roster", "current_market_status_report"}
        ]
        terminated = [
            item for item in listing
            if item.evidence_type == "terminated"
            and item.effective_from is not None
            and date.fromisoformat(item.effective_from) <= taipei_observed_date
        ]
        if rosters and terminated:
            listing_status = "conflict"
        elif terminated:
            listing_status = "delisted"
        elif rosters:
            listing_status = "listed"
        else:
            listing_status = "unknown"
        securities.append(
            {
                "symbol": symbol,
                "name": next((item.name for item in reversed(entries) if item.name), None),
                "listing_status": listing_status,
                "market": next((item.market for item in reversed(entries) if item.market), None),
                "trading_restrictions": [
                    item.to_dict() for item in entries if item.evidence_type == "trading_restriction"
                ],
                "evidence": [item.to_dict() for item in entries],
                "status_reason": (
                    "official_roster_and_termination_conflict" if listing_status == "conflict"
                    else "explicit_official_termination_notice" if listing_status == "delisted"
                    else "present_in_current_official_roster_or_market_status_report" if listing_status == "listed"
                    else "no_positive_official_status_evidence"
                ),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "scope": SCOPE,
        "pit_eligible": PIT_ELIGIBLE,
        "observed_at": utc_observed,
        "source_captures": [dict(item) for item in source_captures],
        "securities": securities,
        "contract": {
            "missing_roster_row_means": "unknown",
            "missing_quote_means": "no_status_evidence",
                "status_is_annotation_only": True,
                "historical_replay_allowed": False,
                "termination_requires_explicit_effective_date_not_after_observation": True,
        },
    }


@dataclass(frozen=True)
class CurrentStatusObservation:
    """提供給排名、ML 和 UI 消費端的型別化註記。"""

    symbol: str
    observed_at: str
    listing_status: str
    market: str | None
    name: str | None
    trading_restrictions: tuple[Mapping[str, object], ...]
    status_evidence: tuple[Mapping[str, object], ...]
    source_ids: tuple[str, ...]
    source_data_dates: tuple[str, ...]
    source_warnings: tuple[str, ...]
    partial_failure: bool
    status_reason: str
    scope: str = SCOPE
    pit_eligible: bool = PIT_ELIGIBLE


class CurrentMarketStatusReader:
    """讀取已驗證的現況快照，不授予排名閘門判斷權。"""

    def __init__(self, payload: Mapping[str, object], *, verify_raw_files: bool = False) -> None:
        if payload.get("schema_version") != SCHEMA_VERSION:
            raise CurrentMarketStatusError("unsupported_schema_version")
        if payload.get("scope") != SCOPE or payload.get("pit_eligible") is not False:
            raise CurrentMarketStatusError("current_only_scope_invariant_failed")
        if not isinstance(payload.get("securities"), list):
            raise CurrentMarketStatusError("securities_must_be_list")
        captures = payload.get("source_captures", [])
        if not isinstance(captures, list):
            raise CurrentMarketStatusError("source_captures_must_be_list")
        if verify_raw_files:
            if not isinstance(captures, list):
                raise CurrentMarketStatusError("source_captures_must_be_list")
            for capture in captures:
                if not isinstance(capture, Mapping) or capture.get("status") != "captured":
                    continue
                raw_path = Path(str(capture.get("raw_path") or ""))
                expected = str(capture.get("raw_sha256") or "")
                if raw_path.is_symlink() or not raw_path.is_file():
                    raise CurrentMarketStatusError("captured_raw_file_missing")
                if not re.fullmatch(r"sha256:[0-9a-f]{64}", expected):
                    raise CurrentMarketStatusError("captured_raw_hash_invalid")
                if sha256_bytes(raw_path.read_bytes()) != expected:
                    raise CurrentMarketStatusError("captured_raw_hash_mismatch")
        self._payload = payload
        self._observed_at = _text(payload.get("observed_at"))
        self._source_warnings = tuple(
            f"{item.get('source_id', 'unknown_source')}:{item.get('status', 'missing')}/{item.get('parse_status', 'unparsed')}"
            for item in captures
            if isinstance(item, Mapping)
            and (item.get("status") != "captured" or item.get("parse_status") != "parsed")
        )
        security_rows = payload.get("securities")
        if not isinstance(security_rows, list):
            raise CurrentMarketStatusError("securities_must_be_list")
        self._rows = {
            str(item.get("symbol")): item
            for item in security_rows
            if isinstance(item, Mapping) and _SYMBOL_RE.fullmatch(str(item.get("symbol", "")))
        }

    @classmethod
    def from_path(cls, path: str | Path) -> "CurrentMarketStatusReader":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")), verify_raw_files=True)

    @classmethod
    def from_pointer(cls, pointer_path: str | Path) -> "CurrentMarketStatusReader":
        """從固定指標解析指定 run；不掃描或猜測最新目錄。"""
        pointer_path = Path(pointer_path).expanduser().resolve()
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        if (
            not isinstance(pointer, Mapping)
            or pointer.get("schema_version") != "current-market-status-pointer.v1"
            or pointer.get("scope") != SCOPE
            or pointer.get("pit_eligible") is not False
        ):
            raise CurrentMarketStatusError("invalid_current_status_pointer")
        root = pointer_path.parent.resolve()

        def _bound_file(field: str, digest_field: str) -> Path:
            rel = Path(str(pointer.get(field) or ""))
            path = (root / rel).resolve()
            if not path.is_relative_to(root) or path.is_symlink() or not path.is_file():
                raise CurrentMarketStatusError(f"pointer_{field}_invalid")
            expected = str(pointer.get(digest_field) or "")
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", expected):
                raise CurrentMarketStatusError(f"pointer_{digest_field}_invalid")
            if sha256_bytes(path.read_bytes()) != expected:
                raise CurrentMarketStatusError(f"pointer_{field}_hash_mismatch")
            return path

        snapshot_path = _bound_file("snapshot_path", "snapshot_sha256")
        manifest_path = _bound_file("manifest_path", "manifest_sha256")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        run_id = str(pointer.get("run_id") or "")
        if (
            not run_id
            or manifest.get("run_id") != run_id
            or snapshot.get("run_id") != run_id
            or manifest.get("snapshot_sha256") != pointer.get("snapshot_sha256")
        ):
            raise CurrentMarketStatusError("pointer_run_binding_mismatch")
        return cls(snapshot, verify_raw_files=True)

    def get(self, symbol: str) -> CurrentStatusObservation:
        normalized = str(symbol).strip()
        if not _SYMBOL_RE.fullmatch(normalized):
            raise CurrentMarketStatusError("symbol_must_be_4_to_6_digits")
        row = self._rows.get(normalized)
        if row is None:
            return CurrentStatusObservation(
                symbol=normalized,
                observed_at=self._observed_at,
                listing_status="unknown",
                market=None,
                name=None,
                trading_restrictions=(),
                status_evidence=(),
                source_ids=(),
                source_data_dates=(),
                source_warnings=self._source_warnings,
                partial_failure=bool(self._payload.get("partial_failure", False)),
                status_reason="not_observed_in_captured_sources",
            )
        evidence = row.get("evidence", [])
        source_ids = tuple(sorted({str(item.get("source_id")) for item in evidence if isinstance(item, Mapping) and item.get("source_id")}))
        source_data_dates = tuple(sorted({
            str(value)
            for item in evidence if isinstance(item, Mapping)
            for value in item.get("source_data_dates", []) if value
        }))
        restrictions = row.get("trading_restrictions", [])
        return CurrentStatusObservation(
            symbol=normalized,
            observed_at=self._observed_at,
            listing_status=str(row.get("listing_status", "unknown")),
            market=str(row["market"]) if row.get("market") else None,
            name=str(row["name"]) if row.get("name") else None,
            trading_restrictions=tuple(item for item in restrictions if isinstance(item, Mapping)),
            status_evidence=tuple(item for item in evidence if isinstance(item, Mapping)),
            source_ids=source_ids,
            source_data_dates=source_data_dates,
            source_warnings=self._source_warnings,
            partial_failure=bool(self._payload.get("partial_failure", False)),
            status_reason=str(row.get("status_reason", "no_positive_official_status_evidence")),
        )


def read_current_status(path: str | Path, symbol: str) -> CurrentStatusObservation:
    """供應用程式和 ML 消費端使用的型別化讀取入口。"""
    return CurrentMarketStatusReader.from_path(path).get(symbol)
