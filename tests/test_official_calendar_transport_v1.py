from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
from typing import Callable
from urllib.parse import urlencode

import pytest

from data_module import official_calendar_transport_v1 as transport
from data_module.official_calendar_bundle import (
    TPEX_MARKET_CALENDAR_URL,
    TWSE_HOLIDAY_SCHEDULE_URL,
    CapturedCalendarResponse,
    hash_response_bytes,
)


_STARTED = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
_TWSE_RAW = b"\xef\xbb\xbf" + '[{"Date":"1150901","Name":"中秋節"}]'.encode("utf-8")
_TPEX_RAW = '{"calendar":{"status":"success","data":{}}}'.encode("utf-8")
_CONTENT_TYPE = "application/json; charset=utf-8"


class _ChunkedRaw:
    """模擬 bounded raw stream，逐次回傳指定區塊或拋出錯誤。"""

    def __init__(self, chunks: list[bytes | BaseException]) -> None:
        self._chunks = list(chunks)
        self.calls: list[tuple[int, bool]] = []

    def read1(self, amount: int, *, decode_content: bool = False) -> bytes:
        self.calls.append((amount, decode_content))
        assert amount == 64 * 1024
        assert decode_content is False
        if not self._chunks:
            return b""
        chunk = self._chunks.pop(0)
        if isinstance(chunk, BaseException):
            raise chunk
        return chunk


class _Response:
    def __init__(
        self,
        *,
        url: str,
        chunks: list[bytes | BaseException],
        headers: dict[str, str],
        status_code: int = 200,
        close_error: BaseException | None = None,
    ) -> None:
        self.url = url
        self.raw = _ChunkedRaw(chunks)
        self.headers = headers
        self.status_code = status_code
        self.close_error = close_error
        self.closed = False

    def close(self) -> None:
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


def _request_url(kind: str, key: str) -> str:
    endpoint, params = transport.calendar_request_v1(kind, key)
    return endpoint + "?" + urlencode(params)


def _response(
    kind: str = "twse",
    key: str = "2026",
    *,
    raw: bytes = _TWSE_RAW,
    chunks: list[bytes | BaseException] | None = None,
    headers: dict[str, str] | None = None,
    url: str | None = None,
    status_code: int = 200,
    close_error: BaseException | None = None,
) -> _Response:
    selected_headers = headers or {
        "Content-Type": _CONTENT_TYPE,
        "Content-Length": str(len(raw)),
    }
    return _Response(
        url=url or _request_url(kind, key),
        chunks=[raw] if chunks is None else chunks,
        headers=selected_headers,
        status_code=status_code,
        close_error=close_error,
    )


def _request_fn(response: _Response, calls: list[tuple[str, dict[str, object]]]):
    def request_fn(url: str, **kwargs: object) -> _Response:
        calls.append((url, kwargs))
        return response

    return request_fn


def _reverse_headers(value: dict[str, object]) -> None:
    headers = value["headers"]
    assert type(headers) is list
    value["headers"] = list(reversed(headers))


def _capture(
    response: _Response,
    *,
    kind: str = "twse",
    key: str = "2026",
    clock: Callable[[], datetime] = lambda: _STARTED,
    check_cancel: Callable[[], bool] | None = None,
) -> tuple[transport.OfficialCalendarJsonTransportV1, list[tuple[str, dict[str, object]]]]:
    calls: list[tuple[str, dict[str, object]]] = []
    result = transport.capture_calendar_json_transport_v1(
        kind,
        key,
        request_fn=_request_fn(response, calls),
        clock=clock,
        check_cancel=check_cancel,
    )
    return result, calls


@pytest.mark.parametrize(
    ("kind", "key", "endpoint", "params", "request_url", "body"),
    [
        (
            "twse",
            "2026",
            "https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule",
            {"queryYear": "115"},
            "https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule?queryYear=115",
            _TWSE_RAW,
        ),
        (
            "tpex",
            "202609",
            "https://info.tpex.org.tw/api/mktCalendar",
            {"ym": "202609", "lang": "zh-tw"},
            "https://info.tpex.org.tw/api/mktCalendar?ym=202609&lang=zh-tw",
            _TPEX_RAW,
        ),
    ],
)
def test_capture_keeps_fixed_official_endpoint_params_and_stream_request(
    kind: str,
    key: str,
    endpoint: str,
    params: dict[str, str],
    request_url: str,
    body: bytes,
) -> None:
    if kind == "twse":
        assert TWSE_HOLIDAY_SCHEDULE_URL == endpoint
    else:
        assert TPEX_MARKET_CALENDAR_URL == endpoint
    response = _response(kind, key, raw=body)

    result, calls = _capture(response, kind=kind, key=key)

    assert transport.calendar_request_v1(kind, key) == (endpoint, params)
    assert result.request_url == request_url
    assert len(calls) == 1
    assert calls[0][0] == endpoint
    assert calls[0][1]["params"] == params
    assert calls[0][1]["stream"] is True
    assert calls[0][1]["allow_redirects"] is False
    assert calls[0][1]["timeout"] == (10, 1)
    assert calls[0][1]["headers"]["Accept-Encoding"] == "identity"  # type: ignore[index]
    assert response.raw.calls[-1] == (64 * 1024, False)
    assert response.closed is True


def test_transport_preserves_utf8_bom_raw_bytes_hash_and_response() -> None:
    response = _response(raw=_TWSE_RAW)

    result, _ = _capture(response)
    captured = result.to_response()

    assert result.raw_bytes == _TWSE_RAW
    assert result.raw_sha256 == hashlib.sha256(_TWSE_RAW).hexdigest()
    assert captured.raw_bytes == _TWSE_RAW
    assert captured.source_hash == hash_response_bytes(_TWSE_RAW)
    assert captured.payload == [{"Date": "1150901", "Name": "中秋節"}]
    assert isinstance(captured, CapturedCalendarResponse)


def test_transport_codec_roundtrips_canonical_original_bytes() -> None:
    result, _ = _capture(_response(raw=_TWSE_RAW))

    encoded = result.to_dict()
    decoded = transport.OfficialCalendarJsonTransportV1.from_dict(encoded)

    assert encoded["schema_version"] == transport.CALENDAR_TRANSPORT_SCHEMA_V1
    assert decoded == result
    assert decoded.to_dict() == encoded
    assert decoded.raw_bytes == _TWSE_RAW


@pytest.mark.parametrize(
    ("case", "mutate", "reason", "cause"),
    [
        (
            "missing_field",
            lambda value: value.pop("kind"),
            "calendar_transport_fields_invalid",
            None,
        ),
        (
            "wrong_version",
            lambda value: value.__setitem__("schema_version", "official-calendar-json-transport.v2"),
            "calendar_transport_schema_invalid",
            None,
        ),
        (
            "wrong_hash",
            lambda value: value.__setitem__("raw_sha256", "0" * 64),
            "calendar_transport_decode_failed",
            "calendar_transport_raw_sha_mismatch",
        ),
        (
            "invalid_base64",
            lambda value: value.__setitem__("raw_base64", "!!!!"),
            "calendar_transport_decode_failed",
            None,
        ),
        (
            "unknown_header",
            lambda value: value.__setitem__("headers", [["server", "example"]]),
            "calendar_transport_decode_failed",
            "calendar_transport_headers_invalid",
        ),
        (
            "duplicate_header",
            lambda value: value.__setitem__(
                "headers",
                [["content-type", _CONTENT_TYPE], ["content-type", _CONTENT_TYPE]],
            ),
            "calendar_transport_decode_failed",
            "calendar_transport_headers_invalid",
        ),
        (
            "header_line_break",
            lambda value: value.__setitem__("headers", [["etag", "x\r\ninjected: y"]]),
            "calendar_transport_decode_failed",
            "calendar_transport_headers_invalid",
        ),
        (
            "wrong_content_type",
            lambda value: value.__setitem__("headers", [["content-type", "text/plain"]]),
            "calendar_transport_decode_failed",
            "calendar_transport_json_content_type_required",
        ),
        (
            "noncanonical_header_order",
            _reverse_headers,
            "calendar_transport_noncanonical_fields",
            None,
        ),
    ],
)
def test_transport_codec_rejects_tampered_fields_version_hash_base64_and_headers(
    case: str,
    mutate: Callable[[dict[str, object]], object],
    reason: str,
    cause: str | None,
) -> None:
    del case
    result, _ = _capture(_response(raw=_TWSE_RAW))
    value = result.to_dict()
    mutate(value)

    with pytest.raises(transport.OfficialCalendarTransportError, match=reason) as exc_info:
        transport.OfficialCalendarJsonTransportV1.from_dict(value)

    if cause is not None:
        assert str(exc_info.value.__cause__) == cause


@pytest.mark.parametrize(
    ("status_code", "url", "headers", "reason", "partial"),
    [
        (
            503,
            None,
            {"Content-Type": _CONTENT_TYPE},
            "calendar_transport_http_status_invalid",
            _TWSE_RAW,
        ),
        (
            200,
            "https://example.invalid/calendar?queryYear=115",
            {"Content-Type": _CONTENT_TYPE},
            "calendar_transport_source_url_mismatch",
            _TWSE_RAW,
        ),
        (
            200,
            None,
            {"Content-Type": _CONTENT_TYPE, "Content-Encoding": "gzip"},
            "calendar_transport_content_encoding_unsupported",
            b"",
        ),
    ],
)
def test_capture_rejects_wrong_status_url_and_compressed_response(
    status_code: int,
    url: str | None,
    headers: dict[str, str],
    reason: str,
    partial: bytes,
) -> None:
    response = _response(
        raw=_TWSE_RAW,
        status_code=status_code,
        url=url or _request_url("twse", "2026"),
        headers=headers,
    )

    with pytest.raises(transport.OfficialCalendarTransportError, match=reason) as exc_info:
        _capture(response)

    assert exc_info.value.partial_raw_bytes == partial
    assert response.closed is True


def test_capture_requires_eof_and_matching_content_length() -> None:
    response = _response(raw=_TWSE_RAW)

    result, _ = _capture(response)

    assert result.eof_observed is True
    assert result.received_body_bytes == len(_TWSE_RAW)
    assert response.raw.calls[-1] == (64 * 1024, False)

    bad_length = _response(
        raw=_TWSE_RAW,
        headers={"Content-Type": _CONTENT_TYPE, "Content-Length": str(len(_TWSE_RAW) + 1)},
    )
    with pytest.raises(
        transport.OfficialCalendarTransportError,
        match="calendar_transport_content_length_mismatch",
    ) as exc_info:
        _capture(bad_length)
    assert exc_info.value.partial_raw_bytes == _TWSE_RAW


@pytest.mark.parametrize(
    ("field", "value"),
    [("eof_observed", False), ("received_body_bytes", len(_TWSE_RAW) + 1)],
)
def test_transport_constructor_rejects_incomplete_eof_or_byte_count(
    field: str,
    value: object,
) -> None:
    result, _ = _capture(_response(raw=_TWSE_RAW))

    with pytest.raises(
        transport.OfficialCalendarTransportError,
        match="calendar_transport_body_incomplete",
    ):
        if field == "eof_observed":
            replace(result, eof_observed=False)
        else:
            assert isinstance(value, int)
            replace(result, received_body_bytes=value)


def test_capture_caps_body_at_four_mib_and_keeps_only_bounded_partial_bytes() -> None:
    piece = b"x" * (64 * 1024)
    response = _response(
        chunks=[piece] * 65,
        headers={"Content-Type": _CONTENT_TYPE},
    )

    with pytest.raises(
        transport.OfficialCalendarTransportError,
        match="calendar_transport_body_size_exceeded",
    ) as exc_info:
        _capture(response)

    cap = transport.MAX_CALENDAR_RESPONSE_BYTES
    assert cap == 4 * 1024 * 1024
    assert len(exc_info.value.partial_raw_bytes) == cap
    assert exc_info.value.partial_raw_bytes == b"x" * cap
    assert len(response.raw.calls) == 65
    assert response.closed is True


def test_capture_read_error_preserves_partial_bytes_and_close_error_note() -> None:
    response = _response(
        chunks=[b"partial-json", OSError("socket reset")],
        headers={"Content-Type": _CONTENT_TYPE},
        close_error=RuntimeError("close failed"),
    )

    with pytest.raises(
        transport.OfficialCalendarTransportError,
        match="calendar_transport_request_failed",
    ) as exc_info:
        _capture(response)

    assert exc_info.value.partial_raw_bytes == b"partial-json"
    assert any("calendar_transport_close_failed:RuntimeError" in note
               for note in getattr(exc_info.value, "__notes__", []))
    assert response.closed is True


def test_capture_cancel_preserves_partial_bytes() -> None:
    response = _response(
        chunks=[b"partial-json", b"unused"],
        headers={"Content-Type": _CONTENT_TYPE},
    )

    with pytest.raises(
        transport.OfficialCalendarTransportError,
        match="calendar_transport_cancelled",
    ) as exc_info:
        _capture(response, check_cancel=lambda: len(response.raw.calls) >= 1)

    assert exc_info.value.partial_raw_bytes == b"partial-json"
    assert len(response.raw.calls) == 1
    assert response.closed is True


def test_capture_enforces_monotonic_deadline_without_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    ticks = iter((0.0, 0.1, 0.2, 0.3, 10.0))
    monkeypatch.setattr(transport.time, "monotonic", lambda: next(ticks))
    response = _response(
        chunks=[b"partial-json", b"unused"],
        headers={"Content-Type": _CONTENT_TYPE},
    )

    with pytest.raises(
        transport.OfficialCalendarTransportError,
        match="calendar_transport_deadline_exceeded",
    ) as exc_info:
        _capture(response)

    assert exc_info.value.partial_raw_bytes == b"partial-json"
    assert len(response.raw.calls) == 1
    assert response.closed is True


def test_http_dates_remain_headers_without_official_time_daily_or_pit_qualification() -> None:
    response = _response(
        raw=_TWSE_RAW,
        headers={
            "Content-Type": _CONTENT_TYPE,
            "Date": "Wed, 14 Oct 2026 12:00:00 GMT",
            "Last-Modified": "Tue, 13 Oct 2026 08:00:00 GMT",
        },
    )

    result, _ = _capture(response)
    captured = result.to_response()
    metadata = dict(captured.metadata or {})
    response_headers = metadata["response_headers"]

    assert response_headers["date"] == "Wed, 14 Oct 2026 12:00:00 GMT"  # type: ignore[index]
    assert response_headers["last-modified"] == "Tue, 13 Oct 2026 08:00:00 GMT"  # type: ignore[index]
    assert metadata["eof_observed"] is True
    assert "official_time" not in metadata
    assert "daily_qualified" not in metadata
    assert "pit_qualified" not in metadata
    assert not hasattr(captured, "official_time")
    assert not hasattr(captured, "daily_qualified")
    assert not hasattr(captured, "pit_qualified")
