"""官方 ISIN／上市櫃證券頁的 bounded security typing adapter。

產業分類與證券型態是兩個不同的來源 component。本模組只用官方頁面保存的
``Stocks`` section、explicit type、CFI 與 market 欄位判斷；缺欄位、同代號
市場衝突或無法辨識的型態一律回傳 unknown／拋出 fail-closed 錯誤，不把
ETF、TDR、特別股或 foreign issuer 自動排除成普通股。
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
from html.parser import HTMLParser
import json
import re
from typing import Any


PIT_TAXONOMY_SECURITY_ADAPTER_VERSION = "official-isin-security-adapter.v1"
PIT_TAXONOMY_SECURITY_MAX_SOURCE_BYTES = 64 * 1024 * 1024
TWSE_ISIN_ALL_SECURITIES_ENDPOINT = "https://isin.twse.com.tw/isin/e_single_main.jsp"
TWSE_ISIN_LISTED_ENDPOINT = "https://isin.twse.com.tw/isin/e_C_public.jsp?strMode=2"
TPEX_ISIN_LISTED_ENDPOINT = "https://isin.twse.com.tw/isin/e_C_public.jsp?strMode=4"
TPEX_ISIN_EMERGING_ENDPOINT = "https://isin.twse.com.tw/isin/e_C_public.jsp?strMode=5"

_SYMBOL_RE = re.compile(r"(?<![0-9])([0-9]{4,6})(?![0-9])")
# ISIN pages put preferred shares and other variants in cells such as
# ``1101B TCCPSB``.  Capture the whole leading security-code token first so
# those rows cannot be silently truncated to the common-stock code ``1101``.
_SYMBOL_TOKEN_RE = re.compile(r"^\s*([A-Z0-9]+)(?:\s|$)", re.IGNORECASE)
_ISIN_RE = re.compile(r"\b[A-Z]{2}[A-Z0-9]{9,12}\b")
_CFI_RE = re.compile(r"\b[A-Z]{6}\b")
_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "isin_code": ("isin code", "isin", "isin代碼"),
    "symbol": (
        "security code",
        "security code & security name",
        "code",
        "證券代號",
        "證券代碼",
    ),
    "security_name": ("security name", "name", "證券名稱"),
    "market": ("market", "市場", "市場別"),
    "security_type": (
        "type of security",
        "type of securities",
        "security type",
        "證券種類",
        "證券類別",
    ),
    "industry_group": ("industrial group", "industry group", "產業別"),
    "cfi_code": ("cficode", "cfi code", "cfi", "cfIcode"),
    "remarks": ("remarks", "remark", "備註"),
    "section": ("section", "分類", "區段"),
}


class OfficialSecurityTypingError(ValueError):
    """官方證券來源無法建立可重驗型態 evidence。"""


@dataclass(frozen=True)
class OfficialSecurityRecord:
    symbol: str
    market_scope: str
    section: str
    security_type: str
    cfi_code: str
    isin_code: str
    security_name: str
    market_label: str
    industry_group: str
    row_hash: str
    parser_version: str = PIT_TAXONOMY_SECURITY_ADAPTER_VERSION

    @property
    def eligible_common_equity(self) -> bool:
        return (
            self.security_type == "common_equity"
            and self.section.casefold() == "stocks"
            and self.cfi_code.startswith("ES")
            and self.market_scope in {"twse_listed", "tpex_otc", "tpex_emerging"}
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "market_scope": self.market_scope,
            "section": self.section,
            "security_type": self.security_type,
            "cfi_code": self.cfi_code,
            "isin_code": self.isin_code,
            "security_name": self.security_name,
            "market_label": self.market_label,
            "industry_group": self.industry_group,
            "row_hash": self.row_hash,
            "parser_version": self.parser_version,
        }


def parse_official_isin_security_source(
    raw_payload: bytes,
    *,
    default_market_scope: str | None = None,
    parser_version: str = PIT_TAXONOMY_SECURITY_ADAPTER_VERSION,
) -> tuple[OfficialSecurityRecord, ...]:
    """解析官方 HTML 或明確標註的結構化 JSON security bytes。"""

    if not isinstance(raw_payload, bytes) or not raw_payload:
        raise OfficialSecurityTypingError("security raw payload must be non-empty bytes")
    if len(raw_payload) > PIT_TAXONOMY_SECURITY_MAX_SOURCE_BYTES:
        raise OfficialSecurityTypingError(
            "security raw payload exceeds 64 MiB bound"
        )
    text = _decode_payload(raw_payload)
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        records = _parse_json_records(
            text,
            default_market_scope=default_market_scope,
            parser_version=parser_version,
        )
    else:
        records = _parse_html_records(
            text,
            default_market_scope=default_market_scope,
            parser_version=parser_version,
        )
    if not records:
        raise OfficialSecurityTypingError("security source contains no typed security rows")
    return tuple(records)


def build_security_evidence_map(
    records: Sequence[OfficialSecurityRecord],
    *,
    expected_symbols: Sequence[str],
    market_by_symbol: Mapping[str, str],
) -> tuple[
    dict[str, str],
    dict[str, dict[str, object]],
    dict[str, OfficialSecurityRecord],
]:
    """建立 full-denominator security map 與 explicit eligible projection。

    回傳 ``security_type_by_symbol``、``security_eligibility_by_symbol`` 及
    實際選中的 records。expected symbol 若沒有 exact market evidence 會保留
    為 unknown，並以例外中止 bundle；同一 security 在 all／listed 多來源
    的展示名稱差異不影響 semantic dedup，但不同 ISIN、type、CFI、market
    或 eligibility 仍以例外中止，避免缺件／衝突被當成 excluded 掩蓋。
    """

    expected = _normalize_symbols(expected_symbols)
    normalized_market = {
        symbol: _normalize_market_scope(value)
        for symbol, value in market_by_symbol.items()
    }
    by_key: dict[tuple[str, str], list[OfficialSecurityRecord]] = defaultdict(list)
    for record in records:
        by_key[(record.symbol, record.market_scope)].append(record)

    selected: dict[str, OfficialSecurityRecord] = {}
    missing: list[str] = []
    conflicts: list[str] = []
    for symbol in expected:
        market = normalized_market.get(symbol)
        if market is None:
            missing.append(f"{symbol}:market_missing")
            continue
        candidates = by_key.get((symbol, market), [])
        if not candidates:
            missing.append(f"{symbol}:{market}:security_source_missing")
            continue
        identity_keys = {
            (
                item.isin_code,
                item.security_type,
                item.section,
                item.cfi_code,
                item.market_scope,
            )
            for item in candidates
        }
        if len(identity_keys) != 1:
            conflicts.append(f"{symbol}:{market}:security_type_or_market_conflict")
            continue
        selected[symbol] = candidates[0]
    if missing:
        raise OfficialSecurityTypingError(
            "full denominator security evidence is missing: " + ",".join(missing[:16])
        )
    if conflicts:
        raise OfficialSecurityTypingError(
            "full denominator security evidence conflicts: " + ",".join(conflicts[:16])
        )

    unknown = sorted(
        symbol
        for symbol, record in selected.items()
        if record.security_type == "unknown"
        or not record.section
        or not record.cfi_code
        or not record.market_scope
    )
    if unknown:
        raise OfficialSecurityTypingError(
            "full denominator security type is unknown: " + ",".join(unknown[:16])
        )

    type_by_symbol = {symbol: selected[symbol].security_type for symbol in expected}
    eligibility: dict[str, dict[str, object]] = {}
    for symbol in expected:
        record = selected[symbol]
        if record.eligible_common_equity:
            eligibility[symbol] = {
                "eligible": True,
                "reason": "official_stocks_section_cfi_es_market",
                "security_type": record.security_type,
                "market_scope": record.market_scope,
                "section": record.section,
                "cfi_code": record.cfi_code,
                "isin_code": record.isin_code,
                "evidence_row_hash": record.row_hash,
            }
        else:
            reason = _exclusion_reason(record)
            eligibility[symbol] = {
                "eligible": False,
                "reason": reason,
                "security_type": record.security_type,
                "market_scope": record.market_scope,
                "section": record.section,
                "cfi_code": record.cfi_code,
                "isin_code": record.isin_code,
                "evidence_row_hash": record.row_hash,
            }
    return type_by_symbol, eligibility, selected


def _parse_html_records(
    text: str,
    *,
    default_market_scope: str | None,
    parser_version: str,
) -> list[OfficialSecurityRecord]:
    parser = _HTMLTableParser()
    parser.feed(text)
    parser.close()
    result: list[OfficialSecurityRecord] = []
    current_section = ""
    header: dict[str, int] | None = None
    for cells in parser.rows:
        clean = [_clean_text(item) for item in cells]
        if not any(clean):
            continue
        candidate_header = _header_indices(clean)
        if candidate_header is not None:
            header = candidate_header
            continue
        if header is None:
            section = _extract_section(clean)
            if section:
                current_section = section
            continue
        record = _record_from_cells(
            clean,
            header,
            current_section=current_section,
            default_market_scope=default_market_scope,
            parser_version=parser_version,
        )
        if record is not None:
            result.append(record)
            continue
        section = _extract_section(clean)
        if section:
            current_section = section
    return result


def _parse_json_records(
    text: str,
    *,
    default_market_scope: str | None,
    parser_version: str,
) -> list[OfficialSecurityRecord]:
    try:
        value: Any = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, ValueError) as error:
        raise OfficialSecurityTypingError("security source JSON is invalid") from error
    raw_rows: object = value.get("rows") if isinstance(value, Mapping) else value
    if not isinstance(raw_rows, list):
        raise OfficialSecurityTypingError("security source JSON rows are invalid")
    result: list[OfficialSecurityRecord] = []
    for raw in raw_rows:
        if not isinstance(raw, Mapping):
            raise OfficialSecurityTypingError("security source JSON row is invalid")
        symbol = _first(raw, "symbol", "security_code", "code", "證券代號")
        isin = _first(raw, "isin_code", "isin", "ISIN Code")
        if symbol is None or isin is None:
            raise OfficialSecurityTypingError("security source JSON row misses symbol or ISIN")
        market_label = str(_first(raw, "market", "market_label", "市場") or "")
        market = _normalize_market_scope(market_label or default_market_scope)
        section = _normalize_section(str(_first(raw, "section", "分類") or ""))
        explicit_type = str(
            _first(raw, "security_type", "type", "type_of_security", "Type of security")
            or ""
        )
        cfi = str(_first(raw, "cfi_code", "cfi", "CFICode") or "").strip().upper()
        security_type = _classify_security_type(
            explicit_type,
            section=section,
            cfi_code=cfi,
            remarks=str(_first(raw, "remarks", "備註") or ""),
        )
        result.append(
            _make_record(
                symbol=_normalize_symbol(symbol),
                market_scope=market,
                section=section,
                security_type=security_type,
                cfi_code=cfi,
                isin_code=str(isin).strip().upper(),
                security_name=str(_first(raw, "security_name", "name", "證券名稱") or ""),
                market_label=market_label,
                industry_group=str(_first(raw, "industry_group", "產業別") or ""),
                parser_version=parser_version,
            )
        )
    return result


def _record_from_cells(
    cells: Sequence[str],
    header: Mapping[str, int],
    *,
    current_section: str,
    default_market_scope: str | None,
    parser_version: str,
) -> OfficialSecurityRecord | None:
    isin = _cell(cells, header.get("isin_code"))
    if isin is None:
        return None
    isin_match = _ISIN_RE.search(isin.upper())
    if isin_match is None:
        return None
    symbol_cell = _cell(cells, header.get("symbol")) or ""
    symbol_match = _SYMBOL_TOKEN_RE.search(symbol_cell)
    if symbol_match is None or not symbol_match.group(1).isdigit():
        # A suffixed code (for example 1101B) is a different security.  The
        # PIT denominator contains numeric codes only, so do not truncate it
        # into a false match for the common-stock row.
        return None
    symbol = _normalize_symbol(symbol_match.group(1))
    market_label = _cell(cells, header.get("market")) or ""
    try:
        market = _normalize_market_scope(market_label or default_market_scope)
    except OfficialSecurityTypingError:
        # The all-securities page contains section/header rows and occasional
        # records without a market label.  Ignore those rows at parse time;
        # an expected denominator symbol still fails closed later when its
        # exact market evidence is absent.
        return None
    explicit_type = _cell(cells, header.get("security_type")) or ""
    section = _normalize_section(
        _cell(cells, header.get("section")) or current_section
    )
    # The all-securities table encodes the main section in its
    # ``Type of security`` column (the value is literally ``Stocks``), while
    # the listed-equities table carries it as a section heading.  Normalize
    # both forms before applying the CFI rule.
    if not section and _normalize_section(explicit_type) == "Stocks":
        section = "Stocks"
    elif section == "Other" and _normalize_section(explicit_type) == "Stocks":
        section = "Stocks"
    cfi = (_cell(cells, header.get("cfi_code")) or "").strip().upper()
    cfi_match = _CFI_RE.search(cfi)
    if cfi_match is not None:
        cfi = cfi_match.group(0)
    remarks = _cell(cells, header.get("remarks")) or ""
    security_type = _classify_security_type(
        explicit_type,
        section=section,
        cfi_code=cfi,
        remarks=remarks,
    )
    return _make_record(
        symbol=symbol,
        market_scope=market,
        section=section,
        security_type=security_type,
        cfi_code=cfi,
        isin_code=isin_match.group(0).upper(),
        security_name=_cell(cells, header.get("security_name")) or symbol_cell,
        market_label=market_label,
        industry_group=_cell(cells, header.get("industry_group")) or "",
        parser_version=parser_version,
    )


def _classify_security_type(
    explicit_type: str,
    *,
    section: str,
    cfi_code: str,
    remarks: str,
) -> str:
    text = " ".join((explicit_type, remarks)).casefold()
    if (
        re.search(r"\btdr\b|\bdepositary\s+receipts?\b", text) is not None
        or any(token in text for token in ("存託", "存托"))
    ):
        return "tdr"
    if (
        re.search(r"\betf\b|\bexchange\s+traded\s+fund\b", text) is not None
        or "指數股票型" in text
    ):
        return "etf"
    if re.search(r"\betn\b", text) is not None:
        return "etn"
    if re.search(r"\bwarrants?\b", text) is not None or "權證" in text:
        return "warrant"
    if re.search(r"\bpreferred\b", text) is not None or any(
        token in text for token in ("特別股", "優先股")
    ):
        return "preferred_equity"
    if re.search(r"\bbonds?\b", text) is not None or "債券" in text:
        return "bond"
    if (
        re.search(r"\bcommon\s+(?:stock|share)s?\b|\bordinary\b", text)
        is not None
        or "普通股" in text
    ):
        return "common_equity" if section.casefold() == "stocks" and cfi_code.startswith("ES") else "unknown"
    if section.casefold() == "stocks" and cfi_code.startswith("ES"):
        return "common_equity"
    return "unknown"


def _exclusion_reason(record: OfficialSecurityRecord) -> str:
    if record.security_type == "unknown":
        return "unknown_security_type"
    return "official_security_type_" + record.security_type


def _header_indices(cells: Sequence[str]) -> dict[str, int] | None:
    indices: dict[str, int] = {}
    normalized = [_header_text(cell) for cell in cells]
    for field, aliases in _HEADER_ALIASES.items():
        alias_set = {_header_text(alias) for alias in aliases}
        for index, value in enumerate(normalized):
            if value in alias_set:
                indices[field] = index
                break
    if "isin_code" not in indices or "symbol" not in indices:
        return None
    return indices


def _extract_section(cells: Sequence[str]) -> str | None:
    normalized = {_header_text(cell) for cell in cells if cell}
    if normalized & {"stocks", "stock", "股票"}:
        return "Stocks"
    if normalized & {"etf", "etn", "warrants", "warrant", "權證"}:
        return "Other"
    return None


def _normalize_section(value: str) -> str:
    text = _header_text(value)
    if text in {"stocks", "stock", "股票"}:
        return "Stocks"
    if text in {"", "none", "null"}:
        return ""
    return value.strip()


def _normalize_market_scope(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OfficialSecurityTypingError("security market is missing")
    text = value.strip().casefold().replace(" ", "")
    if text in {
        "emerging",
        "tpexemerging",
        "tpexemergingboard",
        "tpex_emerging",
        "興櫃",
        "興櫃股票",
    }:
        return "tpex_emerging"
    if text in {
        "twse",
        "listed",
        "twselisted",
        "twse_listed",
        "上市",
        "上市股票",
        "taiwaninnovationboard",
        "tib",
        "創新板",
    } or text.startswith("twselisted"):
        return "twse_listed"
    if text in {
        "tpex",
        "otc",
        "tpexotc",
        "tpexlisted",
        "tpex_otc",
        "上櫃",
        "櫃買",
    } or text.startswith(("tpexotc", "tpexlisted", "otc")):
        return "tpex_otc"
    raise OfficialSecurityTypingError(f"security market is unsupported: {value}")


def _make_record(
    *,
    symbol: str,
    market_scope: str,
    section: str,
    security_type: str,
    cfi_code: str,
    isin_code: str,
    security_name: str,
    market_label: str,
    industry_group: str,
    parser_version: str,
) -> OfficialSecurityRecord:
    if not _ISIN_RE.fullmatch(isin_code):
        raise OfficialSecurityTypingError(f"security ISIN is invalid: {isin_code}")
    row_body = {
        "symbol": symbol,
        "market_scope": market_scope,
        "section": section,
        "security_type": security_type,
        "cfi_code": cfi_code,
        "isin_code": isin_code,
        "security_name": security_name.strip(),
        "market_label": market_label.strip(),
        "industry_group": industry_group.strip(),
    }
    row_hash = "sha256:" + hashlib.sha256(
        json.dumps(row_body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return OfficialSecurityRecord(
        **row_body,
        row_hash=row_hash,
        parser_version=parser_version,
    )


def _decode_payload(raw_payload: bytes) -> str:
    try:
        return raw_payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        # TWSE's public ISIN pages currently declare ``charset=big5``.  Keep
        # the fallback bounded and explicit; the raw bytes and HTTP content
        # type remain the source evidence, while this only decodes the HTML
        # needed by the deterministic parser.
        try:
            return raw_payload.decode("cp950")
        except UnicodeDecodeError as error:
            raise OfficialSecurityTypingError(
                "security source must be UTF-8 or Big5 HTML/JSON"
            ) from error


def _normalize_symbols(value: Sequence[str]) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise OfficialSecurityTypingError("expected security symbols must be non-empty")
    normalized = tuple(_normalize_symbol(item) for item in value)
    if normalized != tuple(sorted(set(normalized))):
        raise OfficialSecurityTypingError("expected security symbols must be sorted and unique")
    return normalized


def _normalize_symbol(value: object) -> str:
    symbol = str(value).strip()
    if _SYMBOL_RE.fullmatch(symbol) is None:
        raise OfficialSecurityTypingError(f"security symbol is invalid: {symbol}")
    return symbol


def _first(value: Mapping[object, object], *keys: str) -> object | None:
    normalized = {_header_text(str(key)): item for key, item in value.items()}
    for key in keys:
        item = normalized.get(_header_text(key))
        if item not in (None, ""):
            return item
    return None


def _cell(cells: Sequence[str], index: int | None) -> str | None:
    if index is None or index >= len(cells):
        return None
    value = cells[index].strip()
    return value or None


def _clean_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split()).strip()


def _header_text(value: str) -> str:
    return "".join(_clean_text(value).casefold().split()).replace("&", "&")


class _HTMLTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower = tag.casefold()
        if lower in {"script", "style"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if lower == "tr":
            if self._row is not None:
                self._finish_row()
            self._row = []
        elif lower in {"td", "th"} and self._row is not None:
            self._cell = []
        elif lower == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag: str) -> None:
        lower = tag.casefold()
        if lower in {"script", "style"}:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if lower in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(_clean_text("".join(self._cell)))
            self._cell = None
        elif lower == "tr" and self._row is not None:
            self._finish_row()

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and self._cell is not None:
            self._cell.append(data)

    def _finish_row(self) -> None:
        if self._row is not None and self._row:
            self.rows.append(self._row)
        self._row = None
        self._cell = None


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


__all__ = [
    "OfficialSecurityRecord",
    "OfficialSecurityTypingError",
    "PIT_TAXONOMY_SECURITY_ADAPTER_VERSION",
    "PIT_TAXONOMY_SECURITY_MAX_SOURCE_BYTES",
    "TPEX_ISIN_EMERGING_ENDPOINT",
    "TPEX_ISIN_LISTED_ENDPOINT",
    "TWSE_ISIN_ALL_SECURITIES_ENDPOINT",
    "TWSE_ISIN_LISTED_ENDPOINT",
    "build_security_evidence_map",
    "parse_official_isin_security_source",
]
