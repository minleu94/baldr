"""MOPS 公告快易查季度財報發布時間的唯讀、研究用途 adapter。"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import gzip
import io
import json
import re
from typing import Any, Iterable, Mapping, Protocol
from urllib.parse import urlparse
import zlib

from data_module.fundamental_availability import (
    FORMAL_AVAILABILITY_CONTRACT_VERSION,
    OFFICIAL_ANNOUNCEMENT_EVIDENCE_CLASS,
)

MOPS_EZSEARCH_URL = "https://mopsov.twse.com.tw/mops/web/ezsearch"
MOPS_EZSEARCH_QUERY_URL = "https://mopsov.twse.com.tw/mops/web/ezsearch_query"
MOPS_STATEMENT_AVAILABILITY_SOURCE = "mops.ezsearch.statement_publication"
MOPS_STATEMENT_AVAILABILITY_SCHEMA = "mops-ezsearch-statement-availability.v1"
MOPS_STATEMENT_AVAILABILITY_SOURCE_VERSION = "mops-ezsearch-statement-publication.v1"
MOPS_RESPONSE_ROW_LIMIT = 1000
MOPS_RESPONSE_MAX_BYTES = 8 * 1024 * 1024
MOPS_RESPONSE_MAX_DECODED_BYTES = 8 * 1024 * 1024
MOPS_RESPONSE_PREFIX_BYTES = 64 * 1024
MOPS_RESPONSE_READ_CHUNK_BYTES = 64 * 1024
TAIPEI_TIMEZONE = timezone(timedelta(hours=8))

# EZSearch uses ``status=fail`` for a valid response with no matching rows.
# Keep that separate from transport/parser errors so a bounded capture does
# not present an official empty result as an outage.
_QUERY_SUCCESS_STATUS = "success"
_QUERY_OFFICIAL_NO_DATA_STATUS = "fail"
_QUERY_ERROR_STATUS = "error"

MOPS_STATEMENT_ITEMS: dict[str, str] = {
    "F26": "balance_sheet",
    "F27": "income_statement",
    "F28": "cash_flows_statement",
    "F29": "equity_changes_statement",
}
MOPS_MARKETS = ("sii", "otc", "rotc", "pub")

_PERIOD_PATTERN = re.compile(r"(?P<roc_year>\d{3})年第(?P<quarter>[1-4])季")
_STOCK_CODE_PATTERN = re.compile(r"^\d{4,6}$")


class MOPSEzSearchSession(Protocol):
    def post(
        self,
        url: str,
        *,
        data: Mapping[str, str],
        headers: Mapping[str, str],
        timeout: int,
        stream: bool = False,
        allow_redirects: bool = True,
    ) -> Any: ...


@dataclass(frozen=True)
class MOPSQueryAttempt:
    """單次 HTTP 嘗試的有限、可追溯收據。"""

    attempt_number: int
    started_at_utc: str
    completed_at_utc: str
    source_status: str
    error_code: str = ""
    error_type: str = ""
    error_reason: str = ""
    http_status: int | None = None
    http_reason: str = ""
    content_type: str = ""
    content_length_header: str = ""
    raw_body_sha256: str = ""
    raw_body_bytes_read: int = 0
    raw_body_hash_scope: str = "unavailable"
    content_encoding: str = ""
    raw_body_prefix: bytes = field(default=b"", repr=False, compare=False)
    raw_body_prefix_path: str = ""
    retryable: bool = False
    response_url: str = ""
    transfer_encoding: str = ""
    success_entity_bytes: bytes = field(default=b"", repr=False, compare=False)

    @property
    def raw_body_prefix_sha256(self) -> str:
        if not self.raw_body_prefix:
            return ""
        return sha256(self.raw_body_prefix).hexdigest()

    def to_manifest_item(self) -> dict[str, Any]:
        """輸出 metadata，不把 response bytes 展開到 JSON artifact。"""

        return {
            "attempt": self.attempt_number,
            "started_at_utc": self.started_at_utc,
            "completed_at_utc": self.completed_at_utc,
            "source_status": self.source_status,
            "error_code": self.error_code,
            "error_type": self.error_type,
            "error_reason": self.error_reason,
            "http_status": self.http_status,
            "http_reason": self.http_reason,
            "content_type": self.content_type,
            "content_length_header": self.content_length_header,
            "content_encoding": self.content_encoding,
            "raw_body_sha256": self.raw_body_sha256,
            "raw_body_bytes_read": self.raw_body_bytes_read,
            "raw_body_hash_scope": self.raw_body_hash_scope,
            "raw_body_prefix_path": self.raw_body_prefix_path or None,
            "raw_body_prefix_bytes": len(self.raw_body_prefix),
            "raw_body_prefix_sha256": self.raw_body_prefix_sha256,
            "retryable": self.retryable,
        }


@dataclass(frozen=True)
class MOPSQueryResult:
    market: str
    announcement_item: str
    rows: tuple[dict[str, str], ...]
    response_sha256: str
    source_status: str
    error_code: str = ""
    query_start_date: date | None = None
    query_end_date: date | None = None
    attempt_count: int = 1
    retry_error_codes: tuple[str, ...] = ()
    attempts: tuple[MOPSQueryAttempt, ...] = ()


class MOPSQueryResponseError(ValueError):
    """附帶有限 response metadata 的 MOPS HTTP／解析錯誤。"""

    def __init__(self, attempt: MOPSQueryAttempt) -> None:
        self.attempt = attempt
        super().__init__(attempt.error_reason or attempt.error_code)


def build_query_payload(
    *,
    market: str,
    announcement_item: str,
    start_date: date,
    end_date: date,
) -> dict[str, str]:
    if market not in MOPS_MARKETS:
        raise ValueError(f"unsupported MOPS market: {market}")
    if announcement_item not in MOPS_STATEMENT_ITEMS:
        raise ValueError(f"unsupported MOPS statement item: {announcement_item}")
    if end_date < start_date:
        raise ValueError("end_date must not be earlier than start_date")
    return {
        "step": "00",
        "RADIO_CM": "1",
        "TYPEK": market,
        "CO_MARKET": "",
        "CO_ID": "",
        "PRO_ITEM": announcement_item,
        "SUBJECT": "",
        "SDATE": _gregorian_to_roc_date(start_date),
        "EDATE": _gregorian_to_roc_date(end_date),
        "lang": "TW",
        "AN": "",
    }


def query_mops_ezsearch(
    session: MOPSEzSearchSession,
    *,
    market: str,
    announcement_item: str,
    start_date: date,
    end_date: date,
    timeout_seconds: int = 30,
    attempt_number: int = 1,
    capture_success_entity: bool = False,
) -> MOPSQueryResult:
    payload = build_query_payload(
        market=market,
        announcement_item=announcement_item,
        start_date=start_date,
        end_date=end_date,
    )
    started_at_utc = datetime.now(timezone.utc).isoformat()
    post_kwargs: dict[str, Any] = {
        "data": payload,
        "headers": {
            "Referer": MOPS_EZSEARCH_URL,
            "User-Agent": "technical-analysis-research-readonly/1.0",
            # Ask for an identity entity so the retained response hash is over
            # the exact response-body bytes rather than an auto-decoded stream.
            "Accept-Encoding": "identity",
        },
        "timeout": timeout_seconds,
        "stream": True,
    }
    if capture_success_entity:
        # Candidate custody only accepts a response from the configured URL;
        # redirects are left visible as non-200 responses.
        post_kwargs["allow_redirects"] = False
    response = session.post(MOPS_EZSEARCH_QUERY_URL, **post_kwargs)
    http_status = _response_status(response)
    http_reason = str(getattr(response, "reason", "") or "")
    content_type = _response_header(response, "Content-Type")
    content_length = _response_header(response, "Content-Length")
    content_encoding = _response_header(response, "Content-Encoding")
    transfer_encoding = _response_header(response, "Transfer-Encoding")
    response_url = str(getattr(response, "url", MOPS_EZSEARCH_QUERY_URL) or "")
    capture = _read_response_body(response, content_encoding=content_encoding)
    completed_at_utc = datetime.now(timezone.utc).isoformat()

    if http_status != 200:
        retryable_http = http_status == 429 or (http_status is not None and http_status >= 500)
        attempt = _make_attempt(
            attempt_number=attempt_number,
            started_at_utc=started_at_utc,
            completed_at_utc=completed_at_utc,
            source_status=_QUERY_ERROR_STATUS,
            error_code="http_transport_error" if retryable_http else "http_error",
            error=ValueError(f"MOPS EZSearch returned HTTP {http_status} {http_reason}".strip()),
            http_status=http_status,
            http_reason=http_reason,
            content_type=content_type,
            content_length=content_length,
            content_encoding=content_encoding,
            capture=capture,
            retryable=retryable_http,
        )
        _close_response(response)
        raise MOPSQueryResponseError(attempt)

    if capture.read_error is not None:
        attempt = _make_attempt(
            attempt_number=attempt_number,
            started_at_utc=started_at_utc,
            completed_at_utc=completed_at_utc,
            source_status=_QUERY_ERROR_STATUS,
            error_code="response_read_error",
            error=capture.read_error,
            http_status=http_status,
            http_reason=http_reason,
            content_type=content_type,
            content_length=content_length,
            content_encoding=content_encoding,
            capture=capture,
            retryable=_is_transient_response_read_error(capture.read_error),
        )
        _close_response(response)
        raise MOPSQueryResponseError(attempt)

    if not capture.complete:
        attempt = _make_attempt(
            attempt_number=attempt_number,
            started_at_utc=started_at_utc,
            completed_at_utc=completed_at_utc,
            source_status=_QUERY_ERROR_STATUS,
            error_code="response_body_limit",
            error=ValueError(
                f"MOPS EZSearch response reached the {MOPS_RESPONSE_MAX_BYTES}-byte read limit"
            ),
            http_status=http_status,
            http_reason=http_reason,
            content_type=content_type,
            content_length=content_length,
            content_encoding=content_encoding,
            capture=capture,
            retryable=False,
        )
        _close_response(response)
        raise MOPSQueryResponseError(attempt)

    if capture.decoded_body_limit_exceeded:
        attempt = _make_attempt(
            attempt_number=attempt_number,
            started_at_utc=started_at_utc,
            completed_at_utc=completed_at_utc,
            source_status=_QUERY_ERROR_STATUS,
            error_code="decoded_body_limit",
            error=ValueError(
                "MOPS EZSearch decoded response exceeded the "
                f"{MOPS_RESPONSE_MAX_DECODED_BYTES}-byte parse limit"
            ),
            http_status=http_status,
            http_reason=http_reason,
            content_type=content_type,
            content_length=content_length,
            content_encoding=content_encoding,
            capture=capture,
        )
        _close_response(response)
        raise MOPSQueryResponseError(attempt)

    if capture.decode_error is not None:
        attempt = _make_attempt(
            attempt_number=attempt_number,
            started_at_utc=started_at_utc,
            completed_at_utc=completed_at_utc,
            source_status=_QUERY_ERROR_STATUS,
            error_code="unsupported_content_encoding"
            if str(capture.decode_error).startswith("unsupported Content-Encoding")
            else "invalid_content_encoding",
            error=capture.decode_error,
            http_status=http_status,
            http_reason=http_reason,
            content_type=content_type,
            content_length=content_length,
            content_encoding=content_encoding,
            capture=capture,
        )
        _close_response(response)
        raise MOPSQueryResponseError(attempt)

    try:
        assert capture.body is not None
        body_text = capture.body.decode("utf-8-sig", errors="strict")
        body = json.loads(body_text)
    except (UnicodeError, json.JSONDecodeError) as error:
        attempt = _make_attempt(
            attempt_number=attempt_number,
            started_at_utc=started_at_utc,
            completed_at_utc=completed_at_utc,
            source_status=_QUERY_ERROR_STATUS,
            error_code="invalid_json",
            error=error,
            http_status=http_status,
            http_reason=http_reason,
            content_type=content_type,
            content_length=content_length,
            content_encoding=content_encoding,
            capture=capture,
            retryable=True,
        )
        _close_response(response)
        raise MOPSQueryResponseError(attempt)

    if not isinstance(body, Mapping):
        _raise_invalid_response(
            "MOPS EZSearch response must be a JSON object",
            attempt_number=attempt_number,
            started_at_utc=started_at_utc,
            completed_at_utc=completed_at_utc,
            http_status=http_status,
            http_reason=http_reason,
            content_type=content_type,
            content_length=content_length,
            content_encoding=content_encoding,
            capture=capture,
            response=response,
        )
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    rows = body.get("data")
    if rows is None:
        rows = []
    if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
        _raise_invalid_response(
            "MOPS EZSearch response data must be a list of objects",
            attempt_number=attempt_number,
            started_at_utc=started_at_utc,
            completed_at_utc=completed_at_utc,
            http_status=http_status,
            http_reason=http_reason,
            content_type=content_type,
            content_length=content_length,
            content_encoding=content_encoding,
            capture=capture,
            response=response,
        )
    if len(rows) >= MOPS_RESPONSE_ROW_LIMIT:
        attempt = _make_attempt(
            attempt_number=attempt_number,
            started_at_utc=started_at_utc,
            completed_at_utc=completed_at_utc,
            source_status=_QUERY_ERROR_STATUS,
            error_code="response_row_cap",
            error=ValueError(
                "MOPS EZSearch response reached the 1000-row cap; narrow the date range"
            ),
            http_status=http_status,
            http_reason=http_reason,
            content_type=content_type,
            content_length=content_length,
            content_encoding=content_encoding,
            capture=capture,
            retryable=False,
        )
        _close_response(response)
        raise MOPSQueryResponseError(attempt)
    status = str(body.get("status", "")).strip()
    if status not in {"success", "fail"}:
        _raise_invalid_response(
            "MOPS EZSearch response has an unsupported status",
            attempt_number=attempt_number,
            started_at_utc=started_at_utc,
            completed_at_utc=completed_at_utc,
            http_status=http_status,
            http_reason=http_reason,
            content_type=content_type,
            content_length=content_length,
            content_encoding=content_encoding,
            capture=capture,
            response=response,
        )
    if status == "fail" and rows:
        _raise_invalid_response(
            "MOPS EZSearch failed response must not contain rows",
            attempt_number=attempt_number,
            started_at_utc=started_at_utc,
            completed_at_utc=completed_at_utc,
            http_status=http_status,
            http_reason=http_reason,
            content_type=content_type,
            content_length=content_length,
            content_encoding=content_encoding,
            capture=capture,
            response=response,
        )
    normalized_rows = tuple({str(key): str(value) for key, value in row.items()} for row in rows)
    attempt = _make_attempt(
        attempt_number=attempt_number,
        started_at_utc=started_at_utc,
        completed_at_utc=completed_at_utc,
        source_status=status,
        http_status=http_status,
        http_reason=http_reason,
        content_type=content_type,
        content_length=content_length,
        content_encoding=content_encoding,
        transfer_encoding=transfer_encoding,
        response_url=response_url,
        capture=capture,
        capture_success_entity=capture_success_entity,
    )
    _close_response(response)
    return MOPSQueryResult(
        market=market,
        announcement_item=announcement_item,
        rows=normalized_rows,
        response_sha256=sha256(canonical.encode("utf-8")).hexdigest(),
        source_status=status,
        query_start_date=start_date,
        query_end_date=end_date,
        attempts=(attempt,),
    )


@dataclass(frozen=True)
class _ResponseBodyCapture:
    body: bytes | None
    raw_entity: bytes | None
    prefix: bytes
    body_sha256: str
    bytes_read: int
    complete: bool
    read_error: Exception | None = None
    decode_error: Exception | None = None
    decoded_body_limit_exceeded: bool = False


def _read_response_body(response: Any, *, content_encoding: str) -> _ResponseBodyCapture:
    """界限內讀取 entity bytes、計算原始雜湊並界限解碼供 JSON parser 使用。"""

    raw = getattr(response, "raw", None)
    reader = getattr(raw, "read", None)
    digest = sha256()
    body = bytearray()
    read_error: Exception | None = None
    complete = False
    if not callable(reader):
        read_error = TypeError("streaming MOPS response has no raw byte reader")
    else:
        while len(body) < MOPS_RESPONSE_MAX_BYTES:
            requested = min(
                MOPS_RESPONSE_READ_CHUNK_BYTES,
                MOPS_RESPONSE_MAX_BYTES - len(body),
            )
            try:
                chunk = reader(requested, decode_content=False)
            except Exception as error:  # transport failure after partial body
                read_error = error
                break
            if not chunk:
                complete = True
                break
            chunk_bytes = bytes(chunk)
            remaining = MOPS_RESPONSE_MAX_BYTES - len(body)
            accepted = chunk_bytes[:remaining]
            body.extend(accepted)
            digest.update(accepted)
            if len(chunk_bytes) > remaining:
                # 不把 raw reader 違反 read(size) 的額外 bytes 偽稱成完整 response。
                read_error = ValueError("MOPS response reader exceeded the requested byte limit")
                break

    if not complete and read_error is None and len(body) < MOPS_RESPONSE_MAX_BYTES:
        # 若讀取器在 budget 耗盡前正常返回 EOF，上面的分支已標記 complete；
        # 其他未完成狀況一律保留為 bounded prefix。
        complete = False
    if len(body) == MOPS_RESPONSE_MAX_BYTES and read_error is None:
        content_length = _response_header(response, "Content-Length")
        try:
            declared_length = int(content_length)
        except (TypeError, ValueError):
            declared_length = -1
        # raw reader 未解碼 Content-Encoding；Content-Length 仍描述同一組
        # entity bytes，因此只有明確相符時才可把上限處的雜湊視為完整。
        complete = declared_length == len(body)

    raw_body = bytes(body) if complete and read_error is None else None
    decoded_body: bytes | None = None
    decode_error: Exception | None = None
    decoded_body_limit_exceeded = False
    if raw_body is not None:
        decoded_body, decode_error, decoded_body_limit_exceeded = _decode_response_body(
            raw_body,
            content_encoding=content_encoding,
        )
    return _ResponseBodyCapture(
        body=decoded_body,
        raw_entity=raw_body,
        prefix=bytes(body[:MOPS_RESPONSE_PREFIX_BYTES]),
        body_sha256=(
            digest.hexdigest()
            if (complete and read_error is None) or body
            else ""
        ),
        bytes_read=len(body),
        complete=complete and read_error is None,
        read_error=read_error,
        decode_error=decode_error,
        decoded_body_limit_exceeded=decoded_body_limit_exceeded,
    )


def _decode_response_body(
    raw_body: bytes,
    *,
    content_encoding: str,
) -> tuple[bytes | None, Exception | None, bool]:
    encoding = content_encoding.strip().lower()
    if encoding in {"", "identity"}:
        if len(raw_body) > MOPS_RESPONSE_MAX_DECODED_BYTES:
            return None, None, True
        return raw_body, None, False
    if encoding == "gzip":
        try:
            decoded = bytearray()
            with gzip.GzipFile(fileobj=io.BytesIO(raw_body), mode="rb") as stream:
                while True:
                    remaining = MOPS_RESPONSE_MAX_DECODED_BYTES - len(decoded)
                    chunk = stream.read(min(MOPS_RESPONSE_READ_CHUNK_BYTES, remaining + 1))
                    if not chunk:
                        return bytes(decoded), None, False
                    decoded.extend(chunk)
                    if len(decoded) > MOPS_RESPONSE_MAX_DECODED_BYTES:
                        return None, None, True
        except (OSError, EOFError, zlib.error) as error:
            return None, ValueError(f"invalid gzip response body: {error}"), False
    if encoding == "deflate":
        try:
            return _bounded_zlib_decode(raw_body, wbits=zlib.MAX_WBITS), None, False
        except _DecodedBodyLimitExceeded:
            return None, None, True
        except zlib.error:
            try:
                return _bounded_zlib_decode(raw_body, wbits=-zlib.MAX_WBITS), None, False
            except _DecodedBodyLimitExceeded:
                return None, None, True
            except zlib.error as error:
                return None, ValueError(f"invalid deflate response body: {error}"), False
    return (
        None,
        ValueError(f"unsupported Content-Encoding: {content_encoding[:80]}"),
        False,
    )


class _DecodedBodyLimitExceeded(Exception):
    """內部訊號：解碼輸出超出固定 parser budget。"""


def _bounded_zlib_decode(raw_body: bytes, *, wbits: int) -> bytes:
    decoder = zlib.decompressobj(wbits=wbits)
    decoded = bytearray()
    for offset in range(0, len(raw_body), MOPS_RESPONSE_READ_CHUNK_BYTES):
        pending = raw_body[offset : offset + MOPS_RESPONSE_READ_CHUNK_BYTES]
        while pending:
            remaining = MOPS_RESPONSE_MAX_DECODED_BYTES - len(decoded)
            chunk = decoder.decompress(pending, remaining + 1)
            decoded.extend(chunk)
            if len(decoded) > MOPS_RESPONSE_MAX_DECODED_BYTES:
                raise _DecodedBodyLimitExceeded
            pending = decoder.unconsumed_tail
    remaining = MOPS_RESPONSE_MAX_DECODED_BYTES - len(decoded)
    decoded.extend(decoder.flush(remaining + 1))
    if len(decoded) > MOPS_RESPONSE_MAX_DECODED_BYTES:
        raise _DecodedBodyLimitExceeded
    if not decoder.eof:
        raise zlib.error("incomplete deflate response body")
    return bytes(decoded)


def _is_transient_response_read_error(error: Exception) -> bool:
    if isinstance(error, (TimeoutError, ConnectionError, OSError)):
        return True
    return type(error).__name__ in {
        "ChunkedEncodingError",
        "IncompleteRead",
        "MaxRetryError",
        "NewConnectionError",
        "ProtocolError",
        "ReadTimeoutError",
    }


def _response_header(response: Any, name: str) -> str:
    headers = getattr(response, "headers", {})
    if not isinstance(headers, Mapping):
        return ""
    direct = headers.get(name)
    if direct is not None:
        return str(direct)
    wanted = name.lower()
    for key, value in headers.items():
        if str(key).lower() == wanted:
            return str(value)
    return ""


def _response_status(response: Any) -> int | None:
    value = getattr(response, "status_code", None)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _make_attempt(
    *,
    attempt_number: int,
    started_at_utc: str,
    completed_at_utc: str,
    source_status: str,
    http_status: int | None = None,
    http_reason: str = "",
    content_type: str = "",
    content_length: str = "",
    content_encoding: str = "",
    transfer_encoding: str = "",
    response_url: str = "",
    capture: _ResponseBodyCapture | None = None,
    capture_success_entity: bool = False,
    error_code: str = "",
    error: Exception | None = None,
    retryable: bool = False,
) -> MOPSQueryAttempt:
    reason = " ".join(str(error).split())[:512] if error is not None else ""
    return MOPSQueryAttempt(
        attempt_number=attempt_number,
        started_at_utc=started_at_utc,
        completed_at_utc=completed_at_utc,
        source_status=source_status,
        error_code=error_code,
        error_type=type(error).__name__ if error is not None else "",
        error_reason=reason,
        http_status=http_status,
        http_reason=" ".join(http_reason.split())[:160],
        content_type=" ".join(content_type.split())[:160],
        content_length_header=content_length[:32],
        content_encoding=" ".join(content_encoding.split())[:80],
        response_url=response_url[:512],
        transfer_encoding=" ".join(transfer_encoding.split())[:80],
        raw_body_sha256=capture.body_sha256 if capture else "",
        raw_body_bytes_read=capture.bytes_read if capture else 0,
        raw_body_hash_scope=(
            "full_body" if capture and capture.complete else "read_prefix" if capture and capture.bytes_read else "unavailable"
        ),
        raw_body_prefix=capture.prefix if capture else b"",
        success_entity_bytes=(
            capture.raw_entity or b""
            if capture_success_entity
            and source_status in {_QUERY_SUCCESS_STATUS, _QUERY_OFFICIAL_NO_DATA_STATUS}
            and capture is not None
            and capture.complete
            else b""
        ),
        retryable=retryable,
    )


def _raise_invalid_response(
    reason: str,
    *,
    attempt_number: int,
    started_at_utc: str,
    completed_at_utc: str,
    http_status: int | None,
    http_reason: str,
    content_type: str,
    content_length: str,
    content_encoding: str,
    capture: _ResponseBodyCapture,
    response: Any,
) -> None:
    attempt = _make_attempt(
        attempt_number=attempt_number,
        started_at_utc=started_at_utc,
        completed_at_utc=completed_at_utc,
        source_status=_QUERY_ERROR_STATUS,
        error_code="invalid_response",
        error=ValueError(reason),
        http_status=http_status,
        http_reason=http_reason,
        content_type=content_type,
        content_length=content_length,
        content_encoding=content_encoding,
        capture=capture,
    )
    _close_response(response)
    raise MOPSQueryResponseError(attempt)


def _close_response(response: Any) -> None:
    close = getattr(response, "close", None)
    if callable(close):
        close()


def build_statement_availability_artifact(
    query_results: Iterable[MOPSQueryResult],
    *,
    start_date: date,
    end_date: date,
    captured_at: str,
) -> dict[str, Any]:
    captured = _parse_timestamp(captured_at)
    parsed_rows: list[dict[str, Any]] = []
    query_manifest: list[dict[str, Any]] = []
    seen_event_hashes: set[str] = set()
    duplicate_event_count = 0
    invalid_event_errors: Counter[str] = Counter()
    invalid_event_samples: list[dict[str, Any]] = []

    for result in query_results:
        if result.market not in MOPS_MARKETS:
            raise ValueError(f"unsupported MOPS market: {result.market}")
        if result.announcement_item not in MOPS_STATEMENT_ITEMS:
            raise ValueError(f"unsupported MOPS statement item: {result.announcement_item}")
        if re.fullmatch(r"[0-9a-fA-F]{64}", result.response_sha256) is None:
            raise ValueError("MOPS query result response_sha256 must be a SHA-256 hex digest")
        query_status = str(result.source_status).strip().lower()
        if query_status not in {
            _QUERY_SUCCESS_STATUS,
            _QUERY_OFFICIAL_NO_DATA_STATUS,
            _QUERY_ERROR_STATUS,
        }:
            raise ValueError(f"unsupported MOPS query source status: {result.source_status}")
        if query_status == _QUERY_OFFICIAL_NO_DATA_STATUS and result.rows:
            raise ValueError("MOPS official no-data query must not contain rows")
        manifest_item: dict[str, Any] = {
            "market": result.market,
            "announcement_item": result.announcement_item,
            "response_sha256": result.response_sha256,
            "source_status": query_status,
            "row_count": len(result.rows),
            "error_code": result.error_code,
        }
        if result.query_start_date is not None:
            manifest_item["query_start_date"] = result.query_start_date.isoformat()
        if result.query_end_date is not None:
            manifest_item["query_end_date"] = result.query_end_date.isoformat()
        if result.attempt_count != 1:
            manifest_item["attempt_count"] = result.attempt_count
        if result.retry_error_codes:
            manifest_item["retry_error_codes"] = list(result.retry_error_codes)
        if result.attempts and (
            result.source_status == _QUERY_ERROR_STATUS or result.attempt_count > 1
        ):
            # 未重試的成功 query 保持既有 payload ABI；失敗或實際重試才加
            # 有界 attempts lineage，且每筆只含 metadata／raw-prefix reference。
            manifest_item["attempts"] = [
                attempt.to_manifest_item() for attempt in result.attempts
            ]
        query_manifest.append(manifest_item)
        for row_index, raw_row in enumerate(result.rows, start=1):
            try:
                row = _parse_statement_row(
                    raw_row,
                    expected_market=result.market,
                    expected_item=result.announcement_item,
                    start_date=start_date,
                    end_date=end_date,
                    captured_at=captured,
                    source_hash=f"sha256:{result.response_sha256}",
                )
            except ValueError as error:
                # Historical EZSearch responses are not schema-stable (for
                # example, older rows can omit CTIME). Keep valid rows from
                # the same response, but never silently turn malformed rows
                # into availability evidence. The bounded sample and
                # aggregated error count make the degraded result actionable
                # without copying the raw response into the artifact.
                error_text = str(error) or type(error).__name__
                invalid_event_errors[error_text] += 1
                if len(invalid_event_samples) < 20:
                    invalid_event_samples.append(
                        {
                            "market": result.market,
                            "announcement_item": result.announcement_item,
                            "row_index": row_index,
                            "error": error_text,
                        }
                    )
                continue
            if row["event_hash"] in seen_event_hashes:
                duplicate_event_count += 1
                continue
            seen_event_hashes.add(row["event_hash"])
            parsed_rows.append(row)

    parsed_rows.sort(
        key=lambda item: (
            item["announcement_at"],
            item["stock_code"],
            item["announcement_item"],
        )
    )
    projection_rows = build_availability_projection(parsed_rows)
    return {
        "schema_version": MOPS_STATEMENT_AVAILABILITY_SCHEMA,
        "source_id": MOPS_STATEMENT_AVAILABILITY_SOURCE,
        "source_version": MOPS_STATEMENT_AVAILABILITY_SOURCE_VERSION,
        "source_url": MOPS_EZSEARCH_URL,
        "query_start_date": start_date.isoformat(),
        "query_end_date": end_date.isoformat(),
        "captured_at": captured.isoformat(),
        "timezone": "Asia/Taipei (+08:00)",
        "research_only": True,
        "read_only_source": True,
        "formal_oos_allowed": False,
        "formal_credit_authorized": False,
        "production_scheduler_allowed": False,
        "production_blend_alpha_bp": 0,
        "availability_policy": (
            "preserve official announcement_at; date-only projection becomes available "
            "on the next calendar day to prevent same-day intraday look-ahead"
        ),
        "authoritative_announcement_items": sorted(MOPS_STATEMENT_ITEMS),
        "excluded_umbrella_items": {
            "M31": (
                "mixed semantics: contains both future board-meeting notices and completed "
                "financial-report approvals; not used as statement publication evidence"
            )
        },
        "query_manifest": query_manifest,
        "quality_summary": {
            "event_count": len(parsed_rows),
            "projection_count": len(projection_rows),
            "duplicate_event_count": duplicate_event_count,
            "future_event_count": 0,
            "invalid_event_count": sum(invalid_event_errors.values()),
            "invalid_event_error_counts": dict(sorted(invalid_event_errors.items())),
            "invalid_event_samples": invalid_event_samples,
            "query_count": len(query_manifest),
            "successful_query_count": sum(
                1
                for item in query_manifest
                if item["source_status"] == _QUERY_SUCCESS_STATUS
            ),
            "official_no_data_query_count": sum(
                1
                for item in query_manifest
                if item["source_status"] == _QUERY_OFFICIAL_NO_DATA_STATUS
            ),
            "failed_query_count": sum(
                1
                for item in query_manifest
                if item["source_status"] == _QUERY_ERROR_STATUS
            ),
        },
        "rows": parsed_rows,
        "availability_projection": projection_rows,
    }


def build_availability_projection(
    rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, str]]:
    earliest: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for row in rows:
        key = (
            str(row["stock_code"]),
            str(row["statement_type"]),
            str(row["period"]),
        )
        current = earliest.get(key)
        if current is None or str(row["announcement_at"]) < str(current["announcement_at"]):
            earliest[key] = row

    projected: list[dict[str, str]] = []
    for key in sorted(earliest):
        row = earliest[key]
        announcement_at = _parse_timestamp(str(row["announcement_at"]))
        projected.append(
            {
                "stock_code": str(row["stock_code"]),
                "statement_type": str(row["statement_type"]),
                "period": str(row["period"]),
                "as_of_date": str(row["period_end"]),
                "announced_date": announcement_at.date().isoformat(),
                "available_date": (announcement_at.date() + timedelta(days=1)).isoformat(),
                "source": MOPS_STATEMENT_AVAILABILITY_SOURCE,
                "source_version": MOPS_STATEMENT_AVAILABILITY_SOURCE_VERSION,
                "availability_contract_version": FORMAL_AVAILABILITY_CONTRACT_VERSION,
                "evidence_class": OFFICIAL_ANNOUNCEMENT_EVIDENCE_CLASS,
                "source_hash": str(row["source_hash"]),
                "revision": "1",
                "parent_revision": "",
            }
        )
    return projected


def _parse_statement_row(
    raw_row: Mapping[str, str],
    *,
    expected_market: str,
    expected_item: str,
    start_date: date,
    end_date: date,
    captured_at: datetime,
    source_hash: str,
) -> dict[str, Any]:
    required = {
        "CDATE",
        "CTIME",
        "TYPEK",
        "COMPANY_ID",
        "COMPANY_NAME",
        "AN_CODE",
        "AN_NAME",
        "SUBJECT",
        "HYPERLINK",
    }
    missing = sorted(field for field in required if not str(raw_row.get(field, "")).strip())
    if missing:
        raise ValueError(f"MOPS statement row is missing required fields: {','.join(missing)}")
    item = str(raw_row["AN_CODE"]).strip()
    if item != expected_item:
        raise ValueError("MOPS statement row announcement item does not match the query")
    stock_code = str(raw_row["COMPANY_ID"]).strip()
    if not _STOCK_CODE_PATTERN.fullmatch(stock_code):
        raise ValueError("MOPS statement row has an invalid company id")
    period, period_end = _parse_period(str(raw_row["SUBJECT"]))
    announcement_at = _parse_roc_timestamp(
        str(raw_row["CDATE"]).strip(),
        str(raw_row["CTIME"]).strip(),
    )
    if not start_date <= announcement_at.date() <= end_date:
        raise ValueError("MOPS statement row timestamp is outside the requested date range")
    if announcement_at > captured_at.astimezone(TAIPEI_TIMEZONE):
        raise ValueError("MOPS statement row timestamp is later than captured_at")
    detail_url = str(raw_row["HYPERLINK"]).strip()
    parsed_url = urlparse(detail_url)
    if parsed_url.scheme != "https" or parsed_url.hostname != "mopsov.twse.com.tw":
        raise ValueError("MOPS statement row detail URL is not an official HTTPS URL")
    event_material = {
        "announcement_at": announcement_at.isoformat(),
        "announcement_item": item,
        "detail_url": detail_url,
        "period": period,
        "stock_code": stock_code,
    }
    event_hash = sha256(
        json.dumps(
            event_material,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "stock_code": stock_code,
        "company_name": str(raw_row["COMPANY_NAME"]).strip(),
        "market": expected_market,
        "market_name": str(raw_row["TYPEK"]).strip(),
        "industry": str(raw_row.get("CODE_NAME", "")).strip(),
        "announcement_item": item,
        "announcement_name": str(raw_row["AN_NAME"]).strip(),
        "statement_type": MOPS_STATEMENT_ITEMS[item],
        "subject": str(raw_row["SUBJECT"]).strip(),
        "period": period,
        "period_end": period_end.isoformat(),
        "announcement_at": announcement_at.isoformat(),
        "detail_url": detail_url,
        "event_hash": event_hash,
        "source_hash": source_hash,
    }


def _parse_period(subject: str) -> tuple[str, date]:
    normalized = re.sub(r"\s+", "", subject)
    match = _PERIOD_PATTERN.search(normalized)
    if match is None:
        raise ValueError("MOPS statement subject does not contain an ROC year and quarter")
    gregorian_year = int(match.group("roc_year")) + 1911
    quarter = int(match.group("quarter"))
    end_month = quarter * 3
    end_day = (31, 30, 30, 31)[quarter - 1]
    return (
        f"{gregorian_year}-Q{quarter}",
        date(gregorian_year, end_month, end_day),
    )


def _parse_roc_timestamp(roc_date: str, clock: str) -> datetime:
    match = re.fullmatch(r"(\d{3})/(\d{2})/(\d{2})", roc_date)
    if match is None:
        raise ValueError("MOPS statement row has an invalid ROC date")
    parsed_clock = datetime.strptime(clock, "%H:%M:%S").time()
    return datetime(
        int(match.group(1)) + 1911,
        int(match.group(2)),
        int(match.group(3)),
        parsed_clock.hour,
        parsed_clock.minute,
        parsed_clock.second,
        tzinfo=TAIPEI_TIMEZONE,
    )


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("captured_at must include a timezone")
    return parsed


def _gregorian_to_roc_date(value: date) -> str:
    if value.year <= 1911:
        raise ValueError("MOPS ROC date requires a Gregorian year after 1911")
    return f"{value.year - 1911:03d}/{value.month:02d}/{value.day:02d}"
