"""官方日曆 JSON 完整傳輸收據；完整性不等於來源用途或歷史 PIT 接受。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import hashlib
import json
import re
import time
from typing import Any, Callable, Literal, Mapping, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit

from data_module.official_calendar_bundle import (
    CapturedCalendarResponse, TPEX_MARKET_CALENDAR_URL,
    TWSE_HOLIDAY_SCHEDULE_URL, hash_response_bytes,
)

MAX_CALENDAR_RESPONSE_BYTES = 4 * 1024**2
CALENDAR_TRANSPORT_SCHEMA_V1 = "official-calendar-json-transport.v1"
_HEADERS = frozenset({
    "content-type", "content-length", "content-encoding", "date", "last-modified", "etag",
})
_FIELDS = frozenset({
    "schema_version", "kind", "key", "request_url", "response_url", "http_status",
    "headers", "started_at", "body_completed_at", "raw_base64", "raw_sha256",
    "received_body_bytes", "eof_observed",
})


class OfficialCalendarTransportError(ValueError):
    """保留有界失敗原件，不把非 EOF／錯來源回應當完整收據。"""

    def __init__(self, reason: str, *, partial_raw_bytes: bytes = b"") -> None:
        super().__init__(reason)
        self.partial_raw_bytes = partial_raw_bytes[:MAX_CALENDAR_RESPONSE_BYTES]


def _clock(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise OfficialCalendarTransportError("calendar_transport_aware_clock_required")
    return value.astimezone(timezone.utc)


def calendar_request_v1(kind: str, key: str) -> tuple[str, dict[str, str]]:
    """沿原官方 API 的年份／月份參數，不新增資料來源。"""
    if type(key) is not str:
        raise OfficialCalendarTransportError("calendar_transport_key_invalid")
    if kind == "twse" and re.fullmatch(r"[0-9]{4}", key):
        if 1912 <= int(key) <= 2199:
            return TWSE_HOLIDAY_SCHEDULE_URL, {"queryYear": str(int(key) - 1911)}
    if kind == "tpex" and re.fullmatch(r"[0-9]{6}", key):
        if 1912 <= int(key[:4]) <= 2199 and 1 <= int(key[4:]) <= 12:
            return TPEX_MARKET_CALENDAR_URL, {"ym": key, "lang": "zh-tw"}
    raise OfficialCalendarTransportError("calendar_transport_kind_or_key_invalid")


def _source_url(kind: str, key: str) -> str:
    endpoint, params = calendar_request_v1(kind, key)
    return endpoint + "?" + urlencode(params)


def _matches_url(value: str, expected: str) -> bool:
    if type(value) is not str or len(value) > 2048:
        return False
    try:
        parsed, wanted = urlsplit(value), urlsplit(expected)
        return (
            parsed.scheme == "https" and parsed.netloc == wanted.netloc
            and parsed.path == wanted.path and not parsed.fragment
            and sorted(parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True))
            == sorted(parse_qsl(wanted.query, keep_blank_values=True, strict_parsing=True))
        )
    except ValueError:
        return False


def _json_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise OfficialCalendarTransportError("calendar_transport_duplicate_json_key")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise OfficialCalendarTransportError("calendar_transport_nonfinite_json")


def _payload(raw: bytes) -> object:
    try:
        value = json.loads(raw.decode("utf-8-sig", errors="strict"),
                           object_pairs_hook=_json_pairs, parse_constant=_reject_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise OfficialCalendarTransportError("calendar_transport_json_invalid") from exc
    if type(value) not in (dict, list):
        raise OfficialCalendarTransportError("calendar_transport_json_container_required")
    return value


class _CalendarJsonBodyV1(Protocol):
    """共用原件完整性欄位；來源URL及method由具名transport核對。"""

    @property
    def http_status(self) -> int: ...
    @property
    def headers(self) -> tuple[tuple[str, str], ...]: ...
    @property
    def started_at(self) -> datetime: ...
    @property
    def body_completed_at(self) -> datetime: ...
    @property
    def raw_bytes(self) -> bytes: ...
    @property
    def raw_sha256(self) -> str: ...
    @property
    def received_body_bytes(self) -> int: ...
    @property
    def eof_observed(self) -> bool: ...


def _validate_calendar_json_body_v1(
    body: _CalendarJsonBodyV1,
) -> tuple[datetime, datetime, tuple[tuple[str, str], ...]]:
    """原V1完整body守衛共用；不解析來源schema或授予用途資格。"""
    if type(body.http_status) is not int or body.http_status != 200:
        raise OfficialCalendarTransportError("calendar_transport_http_status_invalid")
    if (type(body.raw_bytes) is not bytes
            or not 0 < len(body.raw_bytes) <= MAX_CALENDAR_RESPONSE_BYTES):
        raise OfficialCalendarTransportError("calendar_transport_body_size_invalid")
    if (type(body.received_body_bytes) is not int
            or body.received_body_bytes != len(body.raw_bytes)
            or body.eof_observed is not True):
        raise OfficialCalendarTransportError("calendar_transport_body_incomplete")
    if (type(body.raw_sha256) is not str
            or hashlib.sha256(body.raw_bytes).hexdigest() != body.raw_sha256):
        raise OfficialCalendarTransportError("calendar_transport_raw_sha_mismatch")
    if type(body.headers) is not tuple or len(body.headers) > len(_HEADERS):
        raise OfficialCalendarTransportError("calendar_transport_headers_invalid")
    names: set[str] = set()
    for pair in body.headers:
        if (type(pair) is not tuple or len(pair) != 2
                or type(pair[0]) is not str or pair[0] not in _HEADERS
                or pair[0] in names or type(pair[1]) is not str
                or len(pair[1]) > 4096 or "\r" in pair[1] or "\n" in pair[1]):
            raise OfficialCalendarTransportError("calendar_transport_headers_invalid")
        names.add(pair[0])
    headers = dict(body.headers)
    if headers.get("content-encoding", "identity").strip().lower() not in ("", "identity"):
        # 沒有混淆 compressed Content-Length 與 requests 解壓後長度的比較。
        raise OfficialCalendarTransportError("calendar_transport_content_encoding_unsupported")
    if headers.get("content-type", "").split(";", 1)[0].strip().lower() not in (
        "application/json", "text/json",
    ):
        raise OfficialCalendarTransportError("calendar_transport_json_content_type_required")
    if "content-length" in headers:
        length = headers["content-length"]
        if (not re.fullmatch(r"[0-9]{1,10}", length)
                or int(length) != len(body.raw_bytes)):
            raise OfficialCalendarTransportError("calendar_transport_content_length_mismatch")
    start, completed = _clock(body.started_at), _clock(body.body_completed_at)
    if completed < start:
        raise OfficialCalendarTransportError("calendar_transport_clock_reversed")
    _payload(body.raw_bytes)
    return start, completed, tuple(sorted(body.headers))


@dataclass(frozen=True, slots=True)
class OfficialCalendarJsonTransportV1:
    """固定 JSON 原件及擷取證據；單一收據不授每日批次或官方時間資格。"""

    kind: Literal["twse", "tpex"]
    key: str
    request_url: str
    response_url: str
    http_status: int
    headers: tuple[tuple[str, str], ...]
    started_at: datetime
    body_completed_at: datetime
    raw_bytes: bytes
    raw_sha256: str
    received_body_bytes: int
    eof_observed: bool

    def __post_init__(self) -> None:
        expected = _source_url(self.kind, self.key)
        if not _matches_url(self.request_url, expected) or not _matches_url(self.response_url, expected):
            raise OfficialCalendarTransportError("calendar_transport_source_url_mismatch")
        start, completed, headers = _validate_calendar_json_body_v1(self)
        object.__setattr__(self, "started_at", start)
        object.__setattr__(self, "body_completed_at", completed)
        object.__setattr__(self, "headers", headers)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": CALENDAR_TRANSPORT_SCHEMA_V1,
            "kind": self.kind, "key": self.key, "request_url": self.request_url,
            "response_url": self.response_url, "http_status": self.http_status,
            "headers": [list(pair) for pair in self.headers],
            "started_at": self.started_at.isoformat(),
            "body_completed_at": self.body_completed_at.isoformat(),
            "raw_base64": base64.b64encode(self.raw_bytes).decode("ascii"),
            "raw_sha256": self.raw_sha256, "received_body_bytes": self.received_body_bytes,
            "eof_observed": self.eof_observed,
        }

    @classmethod
    def from_dict(cls, value: object) -> OfficialCalendarJsonTransportV1:
        if type(value) is not dict or set(value) != _FIELDS:
            raise OfficialCalendarTransportError("calendar_transport_fields_invalid")
        if value["schema_version"] != CALENDAR_TRANSPORT_SCHEMA_V1:
            raise OfficialCalendarTransportError("calendar_transport_schema_invalid")
        try:
            text = value["raw_base64"]
            if type(text) is not str or len(text) > ((MAX_CALENDAR_RESPONSE_BYTES + 2) // 3) * 4:
                raise ValueError("raw base64 size")
            raw = base64.b64decode(text, validate=True)
            if base64.b64encode(raw).decode("ascii") != text:
                raise ValueError("noncanonical base64")
            headers = value["headers"]
            if type(headers) is not list or any(type(pair) is not list for pair in headers):
                raise ValueError("header shape")
            result = cls(
                kind=value["kind"], key=value["key"], request_url=value["request_url"],
                response_url=value["response_url"], http_status=value["http_status"],
                headers=tuple(tuple(pair) for pair in headers),
                started_at=datetime.fromisoformat(value["started_at"]),
                body_completed_at=datetime.fromisoformat(value["body_completed_at"]),
                raw_bytes=raw, raw_sha256=value["raw_sha256"],
                received_body_bytes=value["received_body_bytes"], eof_observed=value["eof_observed"],
            )
        except (TypeError, ValueError, KeyError) as exc:
            raise OfficialCalendarTransportError("calendar_transport_decode_failed") from exc
        if result.to_dict() != value:
            raise OfficialCalendarTransportError("calendar_transport_noncanonical_fields")
        return result

    def to_response(self) -> CapturedCalendarResponse:
        return CapturedCalendarResponse(
            kind=self.kind, key=self.key, source=self.request_url,
            source_hash=hash_response_bytes(self.raw_bytes), payload=_payload(self.raw_bytes),
            raw_bytes=self.raw_bytes,
            metadata={
                "transport_schema": CALENDAR_TRANSPORT_SCHEMA_V1,
                "http_status": self.http_status, "response_headers": dict(self.headers),
                "request_url": self.request_url, "response_url": self.response_url,
                "started_at_utc": self.started_at.isoformat(),
                "body_completed_at_utc": self.body_completed_at.isoformat(),
                "eof_observed": True, "received_body_bytes": self.received_body_bytes,
            },
        )


def capture_calendar_json_transport_v1(
    kind: Literal["twse", "tpex"], key: str, *,
    request_fn: Callable[..., Any] | None = None,
    clock: Callable[[], datetime] | None = None,
    check_cancel: Callable[[], bool] | None = None,
) -> OfficialCalendarJsonTransportV1:
    """單次4MiB擷取，10秒檢查點與socket期限；不補造缺EOF的原件。"""
    endpoint, params = calendar_request_v1(kind, key)
    if check_cancel is not None and not callable(check_cancel):
        raise OfficialCalendarTransportError("calendar_transport_cancel_callback_invalid")
    if request_fn is None:
        import requests
        request_fn = requests.get
    get_clock = clock or (lambda: datetime.now(timezone.utc))
    started = _clock(get_clock())
    deadline = time.monotonic() + 10
    chunks = bytearray()
    response = None
    failure: OfficialCalendarTransportError | None = None

    def checkpoint() -> None:
        if check_cancel is not None and check_cancel():
            raise OfficialCalendarTransportError("calendar_transport_cancelled")
        if time.monotonic() >= deadline:
            raise OfficialCalendarTransportError("calendar_transport_deadline_exceeded")

    try:
        checkpoint()
        from data_module.official_phase3c_fetcher import HEADERS
        response = request_fn(
            endpoint, params=params, headers={**HEADERS, "Accept-Encoding": "identity"},
            timeout=(10, 1), stream=True, allow_redirects=False,
        )
        checkpoint()
        headers = getattr(response, "headers", None)
        if not isinstance(headers, Mapping):
            raise OfficialCalendarTransportError("calendar_transport_response_headers_required")
        selected = tuple(sorted(
            (str(key).lower(), str(value)) for key, value in headers.items()
            if str(key).lower() in _HEADERS
        ))
        selected_map = dict(selected)
        if selected_map.get("content-encoding", "identity").strip().lower() not in ("", "identity"):
            raise OfficialCalendarTransportError("calendar_transport_content_encoding_unsupported")
        # read1不等待湊滿64KiB；每個實際socket read之間都可檢查期限／取消。
        read1 = getattr(getattr(response, "raw", None), "read1", None)
        if not callable(read1):
            raise OfficialCalendarTransportError("calendar_transport_bounded_read1_required")
        while True:
            checkpoint()
            chunk = read1(64 * 1024, decode_content=False)
            if type(chunk) is not bytes:
                raise OfficialCalendarTransportError("calendar_transport_chunk_invalid")
            if not chunk:
                break
            if len(chunks) + len(chunk) > MAX_CALENDAR_RESPONSE_BYTES:
                chunks.extend(chunk[:MAX_CALENDAR_RESPONSE_BYTES - len(chunks)])
                raise OfficialCalendarTransportError("calendar_transport_body_size_exceeded")
            chunks.extend(chunk)
        checkpoint()
        completed = _clock(get_clock())
        raw = bytes(chunks)
        http_status = getattr(response, "status_code", None)
        if type(http_status) is not int:
            raise OfficialCalendarTransportError("calendar_transport_http_status_invalid")
        return OfficialCalendarJsonTransportV1(
            kind=kind, key=key, request_url=_source_url(kind, key),
            response_url=getattr(response, "url", ""), http_status=http_status,
            headers=selected, started_at=started, body_completed_at=completed,
            raw_bytes=raw, raw_sha256=hashlib.sha256(raw).hexdigest(),
            received_body_bytes=len(raw), eof_observed=True,
        )
    except Exception as exc:
        failure = OfficialCalendarTransportError(
            str(exc) if isinstance(exc, OfficialCalendarTransportError)
            else "calendar_transport_request_failed",
            partial_raw_bytes=bytes(chunks),
        )
        raise failure from exc
    finally:
        if response is not None:
            try:
                response.close()
            except Exception as exc:
                if failure is not None:
                    failure.add_note("calendar_transport_close_failed:" + type(exc).__name__)
                else:
                    raise OfficialCalendarTransportError(
                        "calendar_transport_close_failed", partial_raw_bytes=bytes(chunks),
                    ) from exc
