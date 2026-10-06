"""官方終止買賣公告的獨立、research-only inactive 證明解析器。

本模組只解析呼叫端已保存的 HTTP response bytes，不執行網路、資料庫、
正式發布或 taxonomy 寫入。它不建立 ``OfficialSecurityRecord``，也不提供
ISIN、CFI 或正式 eligibility。使用者必須以同一份 raw bytes 重驗 proof。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
import codecs
import hashlib
from html.parser import HTMLParser
import re
from typing import Mapping
import unicodedata
from urllib.parse import urlsplit


PIT_INACTIVE_TERMINATION_PROOF_SCHEMA = (
    "pit-inactive-security-termination-proof.v1"
)
PIT_INACTIVE_TERMINATION_MAX_SOURCE_BYTES = 8 * 1024 * 1024
_SYMBOL_RE = re.compile(r"^[0-9]{4,6}$")
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_DATE_TOKEN = (
    r"(?:中華民國\s*)?(?:[0-9]{4}\s*[-/.]\s*[0-9]{1,2}\s*[-/.]\s*[0-9]{1,2}"
    r"|[0-9]{2,3}\s*年\s*[0-9]{1,2}\s*月\s*[0-9]{1,2}\s*日?"
    r"|[0-9]{2,3}\s*[-/.]\s*[0-9]{1,2}\s*[-/.]\s*[0-9]{1,2})"
)
_ROC_DATE_RE = re.compile(
    r"^\s*(?P<year>[0-9]{2,3})\s*年\s*(?P<month>[0-9]{1,2})\s*月\s*"
    r"(?P<day>[0-9]{1,2})\s*日?\s*$"
)
_NUMERIC_DATE_RE = re.compile(
    r"^\s*(?P<year>[0-9]{2,4})\s*[-/.]\s*(?P<month>[0-9]{1,2})\s*"
    r"[-/.]\s*(?P<day>[0-9]{1,2})\s*$"
)
_EVENT_DATE_RE = re.compile(rf"自\s*({_DATE_TOKEN})\s*起")


class InactiveTerminationEvidenceError(ValueError):
    """公告、HTTP custody 或決策時間不符合 inactive proof 契約。"""


@dataclass(frozen=True)
class OfficialTerminationSourceSpec:
    """呼叫端已核准的單一官方公告預期值；不是由公告內容反向猜測。"""

    source_url: str
    symbol: str
    issuer_name: str
    market_scope: str
    published_on: date
    suspension_effective_on: date
    termination_effective_on: date


@dataclass(frozen=True)
class InactiveSecurityTerminationProof:
    """可由同一 raw body 重算的非正式、不可替代 active record 證明。"""

    schema_version: str
    symbol: str
    issuer_name: str
    issuer_alias: str
    market_scope: str
    state: str
    eligible: bool
    research_only: bool
    formal_credit: bool
    historical_pit: bool
    active_security_record: bool
    isin_code: None
    cfi_code: None
    source_url: str
    source_raw_path: str
    source_raw_sha256: str
    source_raw_bytes: int
    response_status: int
    content_type: str
    charset: str
    charset_source: str
    captured_at: str
    real_cutoff: str
    published_on: str
    suspension_effective_on: str
    termination_effective_on: str
    evidence_facts: Mapping[str, bool]

    def to_dict(self) -> dict[str, object]:
        """回傳嚴格 schema 的 JSON-compatible mapping。"""

        return asdict(self)


class _VisibleTextParser(HTMLParser):
    """只讀取 HTML 可見文字，略過 script/style 內容。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._hidden_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.casefold() in {"script", "style", "noscript"}:
            self._hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"script", "style", "noscript"} and self._hidden_depth:
            self._hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._hidden_depth:
            self.parts.append(data)


def parse_official_termination_notice(
    raw_html: bytes,
    response_metadata: Mapping[str, object],
    spec: OfficialTerminationSourceSpec,
    actual_capture_at: datetime,
    real_cutoff: datetime,
) -> InactiveSecurityTerminationProof:
    """驗證一份已 custody 的官方 TPEx 終止公告並建立 research-only proof。

    ``response_metadata`` 必須提供 ``request_url``、``final_url``、
    ``status_code``、``content_type``、``charset``、``captured_at``、
    ``raw_sha256``、``raw_bytes`` 及 ``raw_path``。捕獲時間需同時等於
    HTTP metadata 時間且不晚於真實 cutoff；不接受事後補抓回填舊 cutoff。
    """

    _validate_spec(spec)
    capture_utc = _aware_utc(actual_capture_at, "actual_capture_at")
    cutoff_utc = _aware_utc(real_cutoff, "real_cutoff")
    metadata_capture = _aware_utc(
        _metadata_text(response_metadata, "captured_at"), "metadata captured_at"
    )
    if capture_utc != metadata_capture:
        raise InactiveTerminationEvidenceError(
            "actual capture time differs from HTTP metadata"
        )
    if capture_utc > cutoff_utc:
        raise InactiveTerminationEvidenceError(
            "source capture occurred after the real cutoff"
        )
    if spec.published_on > capture_utc.astimezone(_taipei_timezone()).date():
        raise InactiveTerminationEvidenceError(
            "announcement publication date is after the actual source capture date"
        )
    if cutoff_utc.astimezone(_taipei_timezone()).date() < spec.termination_effective_on:
        raise InactiveTerminationEvidenceError(
            "termination is not effective by the requested cutoff"
        )
    if not isinstance(raw_html, bytes) or not raw_html:
        raise InactiveTerminationEvidenceError("source body must be non-empty bytes")
    if len(raw_html) > PIT_INACTIVE_TERMINATION_MAX_SOURCE_BYTES:
        raise InactiveTerminationEvidenceError("source body exceeds the 8 MiB bound")

    request_url = _metadata_text(response_metadata, "request_url")
    final_url = _metadata_text(response_metadata, "final_url")
    if request_url != spec.source_url or final_url != spec.source_url:
        raise InactiveTerminationEvidenceError(
            "HTTP request/final URL does not match the exact source specification"
        )
    if response_metadata.get("status_code") != 200:
        raise InactiveTerminationEvidenceError("official source response is not HTTP 200")
    content_type = _metadata_text(response_metadata, "content_type")
    if content_type.split(";", 1)[0].strip().casefold() != "text/html":
        raise InactiveTerminationEvidenceError("official source is not HTML")
    codec_name, charset_source = _resolve_charset(
        raw_html,
        content_type,
        response_metadata.get("charset"),
    )
    try:
        decoded = raw_html.decode(codec_name, errors="strict")
    except UnicodeDecodeError as error:
        raise InactiveTerminationEvidenceError(
            "source bytes cannot be decoded with the recorded charset"
        ) from error

    raw_digest = "sha256:" + hashlib.sha256(raw_html).hexdigest()
    if response_metadata.get("raw_sha256") != raw_digest:
        raise InactiveTerminationEvidenceError("source raw SHA-256 does not match bytes")
    if response_metadata.get("raw_bytes") != len(raw_html):
        raise InactiveTerminationEvidenceError("source byte count does not match bytes")
    raw_path = _metadata_text(response_metadata, "raw_path")
    if "\x00" in raw_path or "\r" in raw_path or "\n" in raw_path:
        raise InactiveTerminationEvidenceError("source raw path is invalid")

    parser = _VisibleTextParser()
    try:
        parser.feed(decoded)
        parser.close()
    except Exception as error:  # HTMLParser may reject malformed markup.
        raise InactiveTerminationEvidenceError("source HTML cannot be parsed") from error
    text = " ".join(parser.parts)
    text = " ".join(unicodedata.normalize("NFKC", text).split())
    facts, issuer_alias = _validate_notice_facts(text, spec)

    return InactiveSecurityTerminationProof(
        schema_version=PIT_INACTIVE_TERMINATION_PROOF_SCHEMA,
        symbol=spec.symbol,
        issuer_name=spec.issuer_name,
        issuer_alias=issuer_alias,
        market_scope=spec.market_scope,
        state="proven_inactive_common_stock",
        eligible=False,
        research_only=True,
        formal_credit=False,
        historical_pit=False,
        active_security_record=False,
        isin_code=None,
        cfi_code=None,
        source_url=spec.source_url,
        source_raw_path=raw_path,
        source_raw_sha256=raw_digest,
        source_raw_bytes=len(raw_html),
        response_status=200,
        content_type=content_type,
        charset=codec_name,
        charset_source=charset_source,
        captured_at=capture_utc.isoformat().replace("+00:00", "Z"),
        real_cutoff=cutoff_utc.isoformat().replace("+00:00", "Z"),
        published_on=spec.published_on.isoformat(),
        suspension_effective_on=spec.suspension_effective_on.isoformat(),
        termination_effective_on=spec.termination_effective_on.isoformat(),
        evidence_facts=facts,
    )


def validate_official_termination_proof_readback(
    raw_html: bytes,
    response_metadata: Mapping[str, object],
    spec: OfficialTerminationSourceSpec,
    actual_capture_at: datetime,
    real_cutoff: datetime,
    serialized_proof: Mapping[str, object],
) -> InactiveSecurityTerminationProof:
    """以原始 bytes 重算 proof；任何缺欄、額外欄或變更都拒絕。"""

    if not isinstance(serialized_proof, Mapping):
        raise InactiveTerminationEvidenceError("serialized proof must be a mapping")
    recalculated = parse_official_termination_notice(
        raw_html,
        response_metadata,
        spec,
        actual_capture_at,
        real_cutoff,
    )
    if dict(serialized_proof) != recalculated.to_dict():
        raise InactiveTerminationEvidenceError(
            "serialized proof differs from source-byte recomputation"
        )
    return recalculated


def _validate_spec(spec: OfficialTerminationSourceSpec) -> None:
    if not isinstance(spec, OfficialTerminationSourceSpec):
        raise InactiveTerminationEvidenceError("source spec has an unsupported type")
    if not _SYMBOL_RE.fullmatch(spec.symbol):
        raise InactiveTerminationEvidenceError("source spec symbol is invalid")
    if not spec.issuer_name.strip():
        raise InactiveTerminationEvidenceError("source spec issuer name is empty")
    if spec.market_scope != "tpex_otc":
        raise InactiveTerminationEvidenceError("source spec market is not TPEx OTC")
    if not (
        isinstance(spec.published_on, date)
        and not isinstance(spec.published_on, datetime)
        and isinstance(spec.suspension_effective_on, date)
        and not isinstance(spec.suspension_effective_on, datetime)
        and isinstance(spec.termination_effective_on, date)
        and not isinstance(spec.termination_effective_on, datetime)
    ):
        raise InactiveTerminationEvidenceError("source spec dates must be calendar dates")
    if not (
        spec.published_on <= spec.suspension_effective_on
        < spec.termination_effective_on
    ):
        raise InactiveTerminationEvidenceError("source spec event-date order is invalid")
    parsed = urlsplit(spec.source_url)
    official_notice_path = re.fullmatch(
        r"/storage/eb_data/(?P<roc_year>[0-9]{3})(?P<month>0[1-9]|1[0-2])/(?P<notice_id>[A-Za-z0-9_-]{1,64})\.html",
        parsed.path,
    )
    if (
        parsed.scheme != "https"
        or parsed.hostname != "www.tpex.org.tw"
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or official_notice_path is None
    ):
        raise InactiveTerminationEvidenceError(
            "source spec URL is outside the official TPEx notice path"
        )
    if official_notice_path is not None:
        expected_roc_year = spec.published_on.year - 1911
        if (
            int(official_notice_path.group("roc_year")) != expected_roc_year
            or int(official_notice_path.group("month")) != spec.published_on.month
        ):
            raise InactiveTerminationEvidenceError(
                "official TPEx path year/month does not match publication date"
            )


def _validate_notice_facts(
    text: str, spec: OfficialTerminationSourceSpec
) -> tuple[dict[str, bool], str]:
    if spec.issuer_name not in text:
        raise InactiveTerminationEvidenceError("announcement issuer does not match spec")
    symbol_pattern = re.compile(
        rf"(?:股票代號|證券代號|代號)\s*[:：]?\s*#?\s*{re.escape(spec.symbol)}"
        r"(?![0-9])"
    )
    if not symbol_pattern.search(text):
        raise InactiveTerminationEvidenceError("announcement symbol does not match spec")
    subject_alias_pattern = re.compile(
        rf"{re.escape(spec.issuer_name)}.{{0,240}}?"
        rf"(?:股票代號|證券代號|代號)\s*[:：]?\s*{re.escape(spec.symbol)}(?![0-9])"
        r".{0,40}?以下簡稱\s*[「『\"']?"
        r"(?P<alias>[\w\u4e00-\u9fff_-]{1,32})"
    )
    subject_alias = subject_alias_pattern.search(text)
    if subject_alias is None:
        raise InactiveTerminationEvidenceError(
            "announcement subject does not bind issuer, symbol and official alias"
        )
    issuer_alias = subject_alias.group("alias").strip("_-")
    if not issuer_alias:
        raise InactiveTerminationEvidenceError("announcement official issuer alias is empty")
    if "上櫃" not in text or "櫃檯買賣" not in text:
        raise InactiveTerminationEvidenceError(
            "announcement does not establish the TPEx OTC market scope"
        )
    published = _extract_labeled_date(
        text, ("公告日期", "發文日期", "發布日期")
    )
    suspended = _extract_event_date(text, "停止櫃檯買賣")
    terminated = _extract_event_date(text, "終止櫃檯買賣")
    if published != spec.published_on:
        raise InactiveTerminationEvidenceError(
            "announcement publication date does not match source spec"
        )
    if suspended != spec.suspension_effective_on:
        raise InactiveTerminationEvidenceError(
            "announcement suspension date does not match source spec"
        )
    if terminated != spec.termination_effective_on:
        raise InactiveTerminationEvidenceError(
            "announcement termination date does not match source spec"
        )
    common_stock_conversion = any(
        re.search(
            rf"{re.escape(issuer_alias)}.{{0,80}}?每\s*(?:1|一)\s*股\s*普通股\s*換發"
            r".{0,120}?普通股",
            sentence,
        )
        is not None
        for sentence in re.split(r"[。；;\n]", text)
    )
    if not common_stock_conversion:
        raise InactiveTerminationEvidenceError(
            "announcement does not prove ordinary/common-stock conversion"
        )
    return (
        {
            "issuer_name_match": True,
            "symbol_match": True,
            "official_alias_match": True,
            "market_scope_match": True,
            "published_date_match": True,
            "suspension_date_match": True,
            "termination_date_match": True,
            "ordinary_stock_conversion_explicit": True,
            "issuer_common_stock_binding": True,
        },
        issuer_alias,
    )


def _extract_labeled_date(text: str, labels: tuple[str, ...]) -> date:
    for label in labels:
        pattern = re.compile(rf"{re.escape(label)}\s*[:：]?\s*({_DATE_TOKEN})")
        match = pattern.search(text)
        if match:
            return _parse_date_token(match.group(1))
    raise InactiveTerminationEvidenceError(
        "announcement has no labelled publication date"
    )


def _extract_event_date(text: str, event_phrase: str) -> date:
    event = re.search(re.escape(event_phrase), text)
    if not event:
        raise InactiveTerminationEvidenceError(
            f"announcement does not contain event {event_phrase}"
        )
    prefix = text[max(0, event.start() - 120) : event.start()]
    matches = list(_EVENT_DATE_RE.finditer(prefix))
    if not matches:
        raise InactiveTerminationEvidenceError(
            f"announcement event {event_phrase} has no effective date"
        )
    return _parse_date_token(matches[-1].group(1))


def _parse_date_token(value: str) -> date:
    normalized = " ".join(unicodedata.normalize("NFKC", value).split())
    normalized = re.sub(r"^中華民國\s*", "", normalized)
    roc = _ROC_DATE_RE.fullmatch(normalized)
    if roc:
        return _make_date(
            int(roc.group("year")) + 1911,
            int(roc.group("month")),
            int(roc.group("day")),
        )
    numeric = _NUMERIC_DATE_RE.fullmatch(normalized)
    if numeric:
        year = int(numeric.group("year"))
        if year < 1911:
            year += 1911
        return _make_date(year, int(numeric.group("month")), int(numeric.group("day")))
    raise InactiveTerminationEvidenceError("announcement contains an unsupported date")


def _make_date(year: int, month: int, day: int) -> date:
    try:
        return date(year, month, day)
    except ValueError as error:
        raise InactiveTerminationEvidenceError("announcement date is invalid") from error


def _metadata_text(metadata: Mapping[str, object], key: str) -> str:
    value = metadata.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InactiveTerminationEvidenceError(f"HTTP metadata {key} is missing")
    return value.strip()


def _resolve_charset(
    raw_html: bytes,
    content_type: str,
    metadata_charset: object,
) -> tuple[str, str]:
    """以 HTTP 標頭優先、HTML meta 補足，拒絕互相矛盾的 encoding。"""

    if metadata_charset is not None and not isinstance(metadata_charset, str):
        raise InactiveTerminationEvidenceError("HTTP metadata charset is invalid")
    declared: list[tuple[str, str]] = []
    if isinstance(metadata_charset, str) and metadata_charset.strip():
        declared.append((metadata_charset.strip(), "http_metadata"))
    header_match = re.search(r"(?:^|;)\s*charset\s*=\s*['\"]?([^;\s'\"]+)", content_type, re.I)
    if header_match:
        declared.append((header_match.group(1), "content_type_header"))
    head = raw_html[:8192]
    for meta_tag in re.findall(rb"(?is)<meta\b[^>]*>", head):
        direct = re.search(rb"(?i)\bcharset\s*=\s*['\"]?([a-z0-9._-]+)", meta_tag)
        if direct:
            declared.append((direct.group(1).decode("ascii"), "html_meta"))
    if not declared:
        raise InactiveTerminationEvidenceError(
            "HTTP response and HTML do not declare a source charset"
        )
    normalized: list[tuple[str, str]] = []
    for value, origin in declared:
        try:
            normalized.append((codecs.lookup(value).name, origin))
        except LookupError as error:
            raise InactiveTerminationEvidenceError(
                "source declares an unsupported charset"
            ) from error
    if len({name for name, _ in normalized}) != 1:
        raise InactiveTerminationEvidenceError(
            "HTTP and HTML charset declarations conflict"
        )
    selected_name, selected_origin = normalized[0]
    return selected_name, selected_origin


def _aware_utc(value: datetime | str, field: str) -> datetime:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise InactiveTerminationEvidenceError(f"{field} is not an ISO timestamp") from error
    elif isinstance(value, datetime):
        parsed = value
    else:
        raise InactiveTerminationEvidenceError(f"{field} must be a timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InactiveTerminationEvidenceError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _taipei_timezone():
    from zoneinfo import ZoneInfo

    return ZoneInfo("Asia/Taipei")
