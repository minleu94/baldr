"""具名年度POST原件封套與舊monthly wire的相容邊界。"""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path

import pytest

from data_module.official_calendar_bundle import (
    TPEX_ANNUAL_TRADING_DATE_URL,
    parse_tpex_annual_stock_schedule_v1,
)
from data_module.official_calendar_transport_v1 import (
    OfficialCalendarJsonTransportV1,
    OfficialCalendarTransportError,
    calendar_request_v1,
)
from data_module.tpex_annual_calendar_transport_v1 import (
    OfficialCalendarTpexAnnualJsonTransportV1,
    TPEX_ANNUAL_CALENDAR_TRANSPORT_SCHEMA_V1,
)


_START = datetime(2026, 10, 15, 4, 30, tzinfo=timezone.utc)
_RAW_PATH = Path(__file__).parent / "fixtures/p0_official_sources/tpex_trading_date_2026_qa49.json"


def _transport() -> OfficialCalendarTpexAnnualJsonTransportV1:
    raw = _RAW_PATH.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "c5cea6bd3a10bc7cd3e577d9ad78e600ae7d64508a1bc9b09be32fb396d0dc41"
    # 測試時鐘為合成；真HTTP原件不因此取得日常用途或可用時間。
    return OfficialCalendarTpexAnnualJsonTransportV1(
        year=2026, request_url=TPEX_ANNUAL_TRADING_DATE_URL,
        response_url=TPEX_ANNUAL_TRADING_DATE_URL, request_method="POST",
        request_body=b"date=2026&id=", http_status=200,
        headers=(("content-length", str(len(raw))), ("content-type", "application/json; charset=utf-8")),
        started_at=_START, body_completed_at=_START + timedelta(seconds=6),
        raw_bytes=raw, raw_sha256=hashlib.sha256(raw).hexdigest(),
        received_body_bytes=len(raw), eof_observed=True,
    )


def test_named_post_roundtrip_keeps_original_bytes_and_parse_without_monthly_cast() -> None:
    original = _transport()
    wire = original.to_dict()
    assert wire["schema_version"] == TPEX_ANNUAL_CALENDAR_TRANSPORT_SCHEMA_V1
    assert wire["request_method"] == "POST" and wire["year"] == 2026
    assert "kind" not in wire and "key" not in wire
    loaded = OfficialCalendarTpexAnnualJsonTransportV1.from_dict(wire)
    assert loaded == original and loaded.raw_bytes == _RAW_PATH.read_bytes()
    assert loaded.request_body == b"date=2026&id="
    schedule = parse_tpex_annual_stock_schedule_v1(
        loaded.raw_bytes, expected_year=loaded.year, expected_sha256=loaded.raw_sha256,
    )
    assert schedule.stock_settlement_only_dates == ("2026-02-12", "2026-02-13")
    assert not hasattr(loaded, "to_response") and not hasattr(loaded, "available_hour")
    assert not hasattr(loaded, "accepted")
    with pytest.raises(OfficialCalendarTransportError):
        OfficialCalendarJsonTransportV1.from_dict(wire)
    assert calendar_request_v1("tpex", "202610") == (
        "https://info.tpex.org.tw/api/mktCalendar", {"ym": "202610", "lang": "zh-tw"},
    )


@pytest.mark.parametrize(("field", "value"), [
    ("year", True), ("year", 1911), ("year", "2026"), ("year", 2027),
    ("request_method", "GET"), ("request_method", "post"),
    ("request_body", b"date=115&id="), ("request_body", b"date=2026&id=&date=2026"),
    ("request_body", "date=2026&id="),
    ("request_url", TPEX_ANNUAL_TRADING_DATE_URL + "?date=2026"),
    ("response_url", TPEX_ANNUAL_TRADING_DATE_URL + "#same"),
    ("request_url", "https://user@www.tpex.org.tw/www/zh-tw/bulletin/tradingDate"),
    ("response_url", "https://info.tpex.org.tw/api/mktCalendar?ym=202610&lang=zh-tw"),
    ("http_status", True), ("http_status", 206),
    ("eof_observed", False), ("eof_observed", 1),
    ("received_body_bytes", 8791), ("received_body_bytes", True),
    ("raw_sha256", "0" * 64), ("raw_bytes", b"{}"),
    ("started_at", _START.replace(tzinfo=None)),
    ("body_completed_at", _START - timedelta(seconds=1)),
    ("headers", (("content-type", "text/html"),)),
    ("headers", (("content-type", "application/json"), ("content-length", "1"))),
    ("headers", (("content-type", "application/json"), ("content-encoding", "gzip"))),
    ("headers", (("content-type", "application/json"), ("authorization", "not-secret"))),
    ("headers", (("content-type", "application/json"), ("content-type", "application/json"))),
])
def test_post_identity_and_shared_complete_body_guards_cannot_be_bypassed(field: str, value: object) -> None:
    with pytest.raises(OfficialCalendarTransportError):
        replace(_transport(), **{field: value})


@pytest.mark.parametrize(("field", "value"), [
    ("schema_version", "official-calendar-json-transport.v1"),
    ("extra", "unexpected"),
    ("raw_base64", "e30=\n"),
    pytest.param("raw_base64", "x" * (6 * 1024**2), id="oversized-raw-base64"),
    ("request_body_base64", "x" * 100),
    ("request_body_base64", "ZGF0ZT0yMDI2JmlkPQ==\n"),
    ("headers", {"content-type": "application/json"}),
    ("started_at", "2026-10-15T04:30:00Z"),
    ("started_at", 0),
])
def test_codec_rejects_other_schema_or_noncanonical_and_unbounded_fields(field: str, value: object) -> None:
    wire = _transport().to_dict()
    wire[field] = value
    with pytest.raises(OfficialCalendarTransportError):
        OfficialCalendarTpexAnnualJsonTransportV1.from_dict(wire)


def test_codec_rejects_missing_fields_and_tuple_headers() -> None:
    wire = _transport().to_dict()
    del wire["request_body_base64"]
    with pytest.raises(OfficialCalendarTransportError):
        OfficialCalendarTpexAnnualJsonTransportV1.from_dict(wire)
    wire = _transport().to_dict()
    wire["headers"] = [tuple(pair) for pair in wire["headers"]]
    with pytest.raises(OfficialCalendarTransportError):
        OfficialCalendarTpexAnnualJsonTransportV1.from_dict(wire)


def test_constructor_normalizes_clocks_and_headers_without_reencoding_body() -> None:
    original = _transport()
    taipei = timezone(timedelta(hours=8))
    changed = replace(original, started_at=original.started_at.astimezone(taipei),
                      body_completed_at=original.body_completed_at.astimezone(taipei),
                      headers=tuple(reversed(original.headers)))
    assert changed == original and changed.raw_bytes is original.raw_bytes
    assert changed.request_body is original.request_body
