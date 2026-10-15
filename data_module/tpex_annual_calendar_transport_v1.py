"""具名 TPEx 年度 HTML JSON 原件的完整 POST 傳輸收據。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import base64

from data_module.official_calendar_bundle import TPEX_ANNUAL_TRADING_DATE_URL
from data_module.official_calendar_transport_v1 import (
    MAX_CALENDAR_RESPONSE_BYTES,
    OfficialCalendarTransportError,
    _validate_calendar_json_body_v1,
)


TPEX_ANNUAL_CALENDAR_TRANSPORT_SCHEMA_V1 = (
    "official-calendar-tpex-annual-json-transport.v1"
)
_RAW_BASE64_MAX_CHARS = ((MAX_CALENDAR_RESPONSE_BYTES + 2) // 3) * 4
_REQUEST_BASE64_MAX_CHARS = 64
_FIELDS = frozenset({
    "schema_version", "year", "request_url", "response_url", "request_method",
    "request_body_base64", "http_status", "headers", "started_at", "body_completed_at",
    "raw_base64", "raw_sha256", "received_body_bytes", "eof_observed",
})


def _error(reason: str) -> OfficialCalendarTransportError:
    return OfficialCalendarTransportError("calendar_tpex_annual_" + reason)


@dataclass(frozen=True, slots=True)
class OfficialCalendarTpexAnnualJsonTransportV1:
    """保留年度 POST 的原始 request 與完整 response；不授來源用途資格。"""

    year: int
    request_url: str
    response_url: str
    request_method: str
    request_body: bytes
    http_status: int
    headers: tuple[tuple[str, str], ...]
    started_at: datetime
    body_completed_at: datetime
    raw_bytes: bytes
    raw_sha256: str
    received_body_bytes: int
    eof_observed: bool

    def __post_init__(self) -> None:
        if type(self.year) is not int or not 1912 <= self.year <= 2199:
            raise _error("year_invalid")
        if (type(self.request_url) is not str or self.request_url != TPEX_ANNUAL_TRADING_DATE_URL
                or type(self.response_url) is not str
                or self.response_url != TPEX_ANNUAL_TRADING_DATE_URL):
            raise _error("source_url_mismatch")
        if type(self.request_method) is not str or self.request_method != "POST":
            raise _error("request_method_invalid")
        expected_body = f"date={self.year}&id=".encode("ascii")
        if type(self.request_body) is not bytes or self.request_body != expected_body:
            raise _error("request_body_mismatch")
        try:
            started, completed, headers = _validate_calendar_json_body_v1(self)
        except OfficialCalendarTransportError as exc:
            raise _error("body_invalid:" + str(exc)) from exc
        object.__setattr__(self, "started_at", started)
        object.__setattr__(self, "body_completed_at", completed)
        object.__setattr__(self, "headers", headers)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": TPEX_ANNUAL_CALENDAR_TRANSPORT_SCHEMA_V1,
            "year": self.year,
            "request_url": self.request_url,
            "response_url": self.response_url,
            "request_method": self.request_method,
            "request_body_base64": base64.b64encode(self.request_body).decode("ascii"),
            "http_status": self.http_status,
            "headers": [list(pair) for pair in self.headers],
            "started_at": self.started_at.isoformat(),
            "body_completed_at": self.body_completed_at.isoformat(),
            "raw_base64": base64.b64encode(self.raw_bytes).decode("ascii"),
            "raw_sha256": self.raw_sha256,
            "received_body_bytes": self.received_body_bytes,
            "eof_observed": self.eof_observed,
        }

    @classmethod
    def from_dict(cls, value: object) -> OfficialCalendarTpexAnnualJsonTransportV1:
        if type(value) is not dict or set(value) != _FIELDS:
            raise _error("fields_invalid")
        if value["schema_version"] != TPEX_ANNUAL_CALENDAR_TRANSPORT_SCHEMA_V1:
            raise _error("schema_invalid")
        try:
            request_text = value["request_body_base64"]
            raw_text = value["raw_base64"]
            if type(request_text) is not str or len(request_text) > _REQUEST_BASE64_MAX_CHARS:
                raise ValueError("request body base64 size")
            if type(raw_text) is not str or len(raw_text) > _RAW_BASE64_MAX_CHARS:
                raise ValueError("raw body base64 size")
            request_body = base64.b64decode(request_text, validate=True)
            raw_bytes = base64.b64decode(raw_text, validate=True)
            if (base64.b64encode(request_body).decode("ascii") != request_text
                    or base64.b64encode(raw_bytes).decode("ascii") != raw_text):
                raise ValueError("noncanonical base64")
            headers = value["headers"]
            if (type(headers) is not list
                    or any(type(pair) is not list or len(pair) != 2
                           or any(type(item) is not str for item in pair) for pair in headers)):
                raise ValueError("header shape")
            result = cls(
                year=value["year"], request_url=value["request_url"],
                response_url=value["response_url"], request_method=value["request_method"],
                request_body=request_body, http_status=value["http_status"],
                headers=tuple(tuple(pair) for pair in headers),
                started_at=datetime.fromisoformat(value["started_at"]),
                body_completed_at=datetime.fromisoformat(value["body_completed_at"]),
                raw_bytes=raw_bytes, raw_sha256=value["raw_sha256"],
                received_body_bytes=value["received_body_bytes"], eof_observed=value["eof_observed"],
            )
        except OfficialCalendarTransportError as exc:
            raise _error("decode_failed:" + str(exc)) from exc
        except (TypeError, ValueError, KeyError) as exc:
            raise _error("decode_failed") from exc
        if result.to_dict() != value:
            raise _error("noncanonical_fields")
        return result
