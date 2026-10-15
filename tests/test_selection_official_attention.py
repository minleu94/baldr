"""TWSE 官方單日注意公告的 pinned 原件與拒絕邊界。"""

from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from data_module.selection_official_attention import (
    OfficialAttentionError,
    OfficialAttentionReport,
    attention_query_parameters,
    attention_query_url,
    parse_official_attention_report,
)


QUERY_DATE = date(2026, 10, 15)
OBSERVED_DATE = date(2026, 10, 15)
EXPECTED_DATED_SHA256 = (
    "1e6458ff3b5458707e4d1fec87bb7fdc1d6ef8db752f069e49b3eea7e22cc4c8"
)
EXPECTED_PLACEHOLDER_SHA256 = (
    "4bd0ac94f01d8731e1e4407c90af24f3d16d4ff24e13e09b9247e92e5160e216"
)
FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "official_attention"
DATED_RESPONSE_PATH = FIXTURE_ROOT / "twse_20261015.json"
NO_DATE_PLACEHOLDER_PATH = FIXTURE_ROOT / "undated_placeholder.json"


def _dated_response() -> bytes:
    raw = DATED_RESPONSE_PATH.read_bytes()
    assert len(raw) == 4931
    assert hashlib.sha256(raw).hexdigest() == EXPECTED_DATED_SHA256
    return raw


def _placeholder_response() -> bytes:
    raw = NO_DATE_PLACEHOLDER_PATH.read_bytes()
    assert len(raw) == 132
    assert hashlib.sha256(raw).hexdigest() == EXPECTED_PLACEHOLDER_SHA256
    return raw


def _payload(raw: bytes | None = None) -> dict[str, object]:
    value = json.loads((raw if raw is not None else _dated_response()).decode("utf-8-sig"))
    assert isinstance(value, dict)
    return value


def _encode(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _parse(raw: bytes) -> OfficialAttentionReport:
    return parse_official_attention_report(
        raw,
        query_date=QUERY_DATE,
        observed_date=OBSERVED_DATE,
    )


def test_query_is_one_day_all_twse_securities_ordered_by_date() -> None:
    expected = {
        "querytype": "1",
        "startDate": "20261015",
        "endDate": "20261015",
        "sortKind": "DATE",
        "response": "json",
    }
    assert attention_query_parameters(QUERY_DATE) == expected

    parsed_url = urlsplit(attention_query_url(QUERY_DATE))
    assert parsed_url.scheme == "https"
    assert parsed_url.netloc == "www.twse.com.tw"
    assert parsed_url.path == "/rwd/zh/announcement/notice"
    assert parse_qs(parsed_url.query, keep_blank_values=True) == {
        key: [value] for key, value in expected.items()
    }


def test_pinned_report_preserves_all_18_original_security_rows_and_raw_values() -> None:
    raw_before = _dated_response()
    source = _payload(raw_before)

    report = _parse(raw_before)

    source_rows = source["data"]
    assert isinstance(source_rows, list)
    assert report.query_date == "2026-10-15"
    assert report.declared_security_count == source["count"] == 18
    assert report.declared_total == source["total"] == 18
    assert len(report.rows) == 18
    # Keep the official securities universe intact; do not filter to common stocks.
    assert tuple(row.stock_code for row in report.rows) == tuple(row[1] for row in source_rows)
    assert report.raw_sha256 == EXPECTED_DATED_SHA256
    assert _dated_response() == raw_before

    warrant_security = next(row for row in report.rows if row.stock_code == "053040")
    assert warrant_security.announcement_date == "2026-10-15"
    assert warrant_security.official_date_original_text == "115.10.15"
    assert warrant_security.announcement_count_original_text == "18"
    assert warrant_security.closing_price_original_text == "1.73"
    assert warrant_security.pe_original_text == "-----"

    red_font_row = next(row for row in report.rows if row.stock_code == "2308")
    assert "<font color='#FF0000'>" in red_font_row.reason_original_text
    assert "<font" not in red_font_row.reason_text
    assert "﹝第十一款﹞" in red_font_row.reason_text


def test_empty_complete_dated_report_is_distinct_from_placeholder() -> None:
    payload = _payload()
    payload["count"] = 0
    payload["total"] = 0
    payload["data"] = []

    report = _parse(_encode(payload))

    assert report.query_date == "2026-10-15"
    assert report.rows == ()
    assert report.declared_security_count == 0
    assert report.declared_total == 0

    with pytest.raises(OfficialAttentionError):
        _parse(_placeholder_response())


@pytest.mark.parametrize(
    ("count_field", "value"),
    (("count", 17), ("total", 17)),
)
def test_declared_count_and_total_must_match_the_original_rows(
    count_field: str, value: int
) -> None:
    payload = _payload()
    payload[count_field] = value

    with pytest.raises(OfficialAttentionError):
        _parse(_encode(payload))


@pytest.mark.parametrize("mutation", ("top_level_field", "row_width", "row_type"))
def test_missing_field_and_wrong_row_shape_or_type_are_rejected(mutation: str) -> None:
    payload = _payload()
    if mutation == "top_level_field":
        payload.pop("total")
    elif mutation == "row_width":
        rows = payload["data"]
        assert isinstance(rows, list)
        rows[0] = rows[0][:-1]
    else:
        rows = payload["data"]
        assert isinstance(rows, list)
        rows[0][1] = 53040

    with pytest.raises(OfficialAttentionError):
        _parse(_encode(payload))


def test_json_duplicate_keys_floats_and_truncated_body_are_rejected() -> None:
    with pytest.raises(ValueError):
        _parse(b'{"stat":"OK","stat":"OK"}')

    payload = _payload()
    rows = payload["data"]
    assert isinstance(rows, list)
    rows[0][6] = 1.73
    with pytest.raises(ValueError):
        _parse(_encode(payload))

    raw = _dated_response()
    for truncated in (b'{"stat":"OK","data":[', raw[:-1]):
        with pytest.raises(ValueError):
            _parse(truncated)


@pytest.mark.parametrize(
    ("parameter", "value"),
    (
        ("startDate", "20261014"),
        ("endDate", "20261016"),
        ("querytype", "2"),
        ("sortKind", "CODE"),
        ("controller", "tpex"),
        ("action", "notetrans"),
        ("stockNo", "2330"),
        ("selectType", "1"),
    ),
)
def test_report_must_be_the_same_full_twse_date_scope(
    parameter: str, value: str
) -> None:
    payload = _payload()
    params = payload["params"]
    assert isinstance(params, dict)
    params[parameter] = value

    with pytest.raises(OfficialAttentionError):
        _parse(_encode(payload))


def test_query_after_observation_date_is_rejected() -> None:
    with pytest.raises(OfficialAttentionError):
        parse_official_attention_report(
            _dated_response(),
            query_date=date(2026, 10, 16),
            observed_date=OBSERVED_DATE,
        )


def test_duplicate_security_and_unconfirmed_reason_html_are_rejected() -> None:
    payload = _payload()
    rows = payload["data"]
    assert isinstance(rows, list)
    rows.append(list(rows[0]))
    payload["count"] = 19
    payload["total"] = 19
    with pytest.raises(OfficialAttentionError):
        _parse(_encode(payload))

    payload = _payload()
    rows = payload["data"]
    assert isinstance(rows, list)
    rows[0][4] = "<span>未確認格式</span>"
    with pytest.raises(OfficialAttentionError):
        _parse(_encode(payload))
