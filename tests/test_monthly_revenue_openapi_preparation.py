from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json

import pytest

import data_module.monthly_revenue_openapi_preparation as preparation_module
from data_module.monthly_revenue_openapi_preparation import (
    AMOUNT_FIELDS,
    PERCENTAGE_FIELDS,
    TWSE_MONTHLY_REVENUE_OPENAPI_SOURCE_ID,
    TWSE_MONTHLY_REVENUE_OPENAPI_URL,
    TwseMonthlyRevenueOpenApiRawCapture,
    TwseMonthlyRevenuePreparationError,
    prepare_twse_monthly_revenue_openapi_capture,
)


BODY_COMPLETED_AT = datetime(2026, 10, 14, 7, 15, tzinfo=timezone.utc)
BATCH_COMPLETED_AT = datetime(2026, 10, 14, 7, 16, tzinfo=timezone.utc)


def _row(
    stock_code: str = "2330",
    period: str = "11509",
    *,
    amount: str = "1000.250",
    report_date: str = "1151010",
    blank_percentages: bool = True,
) -> dict[str, str]:
    return {
        "資料年月": period,
        "公司代號": stock_code,
        "公司名稱": f"測試公司{stock_code}",
        "營業收入-當月營收": amount,
        "營業收入-上月營收": "900",
        "營業收入-去年當月營收": "800",
        "營業收入-上月比較增減(%)": "" if blank_percentages else "11.25",
        "營業收入-去年同月增減(%)": "" if blank_percentages else "25.00",
        "累計營業收入-當月累計營收": "7000",
        "累計營業收入-去年累計營收": "6000",
        "累計營業收入-前期比較增減(%)": "" if blank_percentages else "16.66",
        "出表日期": report_date,
        "備註": "官方原值備註",
    }


def _capture(
    rows: list[dict[str, str]] | None = None,
    *,
    raw_bytes: bytes | None = None,
    **changes: object,
) -> TwseMonthlyRevenueOpenApiRawCapture:
    if raw_bytes is None:
        raw_bytes = json.dumps(
            rows if rows is not None else [_row()],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    values: dict[str, object] = {
        "requested_url": TWSE_MONTHLY_REVENUE_OPENAPI_URL,
        "response_url": TWSE_MONTHLY_REVENUE_OPENAPI_URL,
        "response_status": 200,
        "content_type_original_text": "application/json; charset=utf-8",
        "content_encoding_original_text": "identity",
        "content_length_original_text": str(len(raw_bytes)),
        "response_body_complete": True,
        "eof_observed": True,
        "received_body_bytes": len(raw_bytes),
        "body_observation_ended_at": BODY_COMPLETED_AT,
        "body_completed_at": BODY_COMPLETED_AT,
        "raw_response_bytes": raw_bytes,
    }
    values.update(changes)
    return TwseMonthlyRevenueOpenApiRawCapture(**values)  # type: ignore[arg-type]


def _prepare(
    capture: TwseMonthlyRevenueOpenApiRawCapture,
    *,
    stock_code: str = "2330",
    period: str = "2026-09",
    batch_completed_at: datetime = BATCH_COMPLETED_AT,
):
    return prepare_twse_monthly_revenue_openapi_capture(
        capture=capture,
        stock_code=stock_code,
        period=period,
        successful_batch_completed_at=batch_completed_at,
    )


def test_single_target_preparation_preserves_raw_body_date_clocks_and_unknown_unit():
    raw_rows = [_row("2317", period="11509"), _row("2330"), _row("2330", period="11508")]
    capture = _capture(raw_rows)

    prepared = _prepare(capture)
    payload = prepared.to_dict()

    assert prepared.raw_response_bytes == capture.raw_response_bytes
    assert capture.raw_response_sha256 == hashlib.sha256(capture.raw_response_bytes).hexdigest()
    assert prepared.response_row_count == 3
    assert prepared.stock_code == "2330"
    assert prepared.period == "2026-09"
    assert prepared.roc_period == "11509"
    assert prepared.company_name == "測試公司2330"
    assert prepared.report_date.isoformat() == "2026-10-10"
    assert not isinstance(prepared.report_date, datetime)
    assert prepared.report_date_original_text == "1151010"
    assert dict(prepared.amount_values)[AMOUNT_FIELDS[0]] == Decimal("1000.250")
    assert dict(prepared.source_values)[AMOUNT_FIELDS[0]] == "1000.250"
    assert dict(prepared.percentage_values) == {field: None for field in PERCENTAGE_FIELDS}
    assert dict(prepared.percentage_missing_reasons) == {
        field: "source_cell_blank" for field in PERCENTAGE_FIELDS
    }
    assert payload["source_id"] == TWSE_MONTHLY_REVENUE_OPENAPI_SOURCE_ID
    assert payload["capture_scope"] == "single_stock_period_target_row"
    assert payload["coverage_claim"] == "none"
    assert payload["official_publication_at"] is None
    assert payload["availability_clock_evidence"] == {
        "available_at": "2026-10-14T16:00:00+08:00",
        "time_basis": "daily-hour.v1",
        "basis": "batch_completion_missing_official_hour",
        "report_date_is_date_only": True,
        "successful_batch_clock_available": True,
        "scope": "clock_evidence_only",
    }
    assert payload["response_body_completed_at"] == "2026-10-14T07:15:00+00:00"
    assert payload["successful_batch_completed_at"] == "2026-10-14T07:16:00+00:00"
    assert payload["unit_evidence"]["unit_status"] == "unverified"
    assert payload["unit_evidence"]["unit_evidence_status"] == "missing_official_strong_anchor"
    assert payload["unit_evidence"]["conversion_to_twd"] is None
    assert payload["use_scope"]["allowed"] == ["shadow", "diagnostics"]
    assert all(value is False for key, value in payload["use_scope"].items() if key != "allowed")
    assert "mops" not in prepared.source_version.lower()
    assert capture.raw_response_sha256 in prepared.source_version


def test_nonblank_percentages_are_decimal_and_source_unit_is_still_unverified():
    prepared = _prepare(_capture([_row(blank_percentages=False)]))

    assert dict(prepared.percentage_values) == {
        PERCENTAGE_FIELDS[0]: Decimal("11.25"),
        PERCENTAGE_FIELDS[1]: Decimal("25.00"),
        PERCENTAGE_FIELDS[2]: Decimal("16.66"),
    }
    assert prepared.percentage_missing_reasons == ()
    assert prepared.to_dict()["unit_evidence"]["unit_status"] == "unverified"


def test_missing_required_target_field_is_not_silently_filled():
    row = _row()
    row.pop("營業收入-上月營收")

    with pytest.raises(TwseMonthlyRevenuePreparationError) as exc_info:
        _prepare(_capture([row]))

    assert exc_info.value.reason_code == "target_required_fields_missing:營業收入-上月營收"


@pytest.mark.parametrize(
    ("rows", "reason"),
    [
        ([_row("2317")], "target_row_missing"),
        ([_row("2330", period="11508")], "target_row_missing"),
        ([_row(), _row()], "target_row_duplicate"),
    ],
    ids=("wrong-stock", "wrong-period", "duplicate-target"),
)
def test_exact_stock_period_match_is_required(rows, reason: str):
    with pytest.raises(TwseMonthlyRevenuePreparationError) as exc_info:
        _prepare(_capture(rows))

    assert exc_info.value.reason_code == reason


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"requested_url": "https://example.invalid/api"}, "requested_url_mismatch"),
        ({"response_url": "https://openapi.twse.com.tw/redirect"}, "response_url_redirect_or_mismatch"),
        ({"response_status": 206}, "http_status_not_200"),
        ({"content_type_original_text": "text/html"}, "content_type_not_json"),
        ({"content_encoding_original_text": "gzip"}, "content_encoding_not_identity"),
        ({"response_body_complete": False}, "response_body_incomplete_or_eof_missing"),
        ({"eof_observed": False}, "response_body_incomplete_or_eof_missing"),
        ({"received_body_bytes": 1}, "received_body_byte_count_mismatch"),
        ({"content_length_original_text": "not-a-length"}, "content_length_invalid"),
        ({"content_length_original_text": "1"}, "content_length_mismatch"),
    ],
    ids=(
        "wrong-request-url", "redirect", "status", "content-type", "encoding",
        "incomplete", "missing-eof", "byte-count", "bad-content-length", "length-mismatch",
    ),
)
def test_transport_evidence_fails_closed(changes: dict[str, object], reason: str):
    with pytest.raises(TwseMonthlyRevenuePreparationError) as exc_info:
        _prepare(_capture([_row()], **changes))

    assert exc_info.value.reason_code == reason


def test_absent_content_length_is_allowed_only_with_eof_and_complete_body():
    capture = _capture([_row()], content_length_original_text=None)

    assert _prepare(capture).capture.eof_observed is True


def test_partial_raw_capture_remains_hashable_but_never_prepares_a_row():
    partial = "[{\"公司代號\":\"2330\"}".encode("utf-8")
    capture = _capture(
        raw_bytes=partial,
        response_body_complete=False,
        eof_observed=False,
        content_length_original_text="100",
        body_completed_at=None,
    )

    assert capture.raw_response_bytes == partial
    assert capture.raw_response_sha256 == hashlib.sha256(partial).hexdigest()
    assert capture.receipt_fields()["body_completed_at"] is None
    with pytest.raises(TwseMonthlyRevenuePreparationError) as exc_info:
        _prepare(capture)
    assert exc_info.value.reason_code == "response_body_incomplete_or_eof_missing"


@pytest.mark.parametrize(
    ("raw_bytes", "reason"),
    [
        (b"\xff", "json_utf8_decode_failed"),
        (b"{}", "json_root_must_be_nonempty_array"),
        (b"[]", "json_root_must_be_nonempty_array"),
        (b"[null]", "json_row_not_object"),
    ],
    ids=("invalid-utf8", "wrong-root", "empty-array", "non-object-row"),
)
def test_json_root_and_row_shape_are_strict(raw_bytes: bytes, reason: str):
    with pytest.raises(TwseMonthlyRevenuePreparationError) as exc_info:
        _prepare(_capture(raw_bytes=raw_bytes))

    assert exc_info.value.reason_code == reason


@pytest.mark.parametrize(
    ("raw_text", "reason"),
    [
        ('[{"公司代號":"2330","公司代號":"2330","資料年月":"11509"}]', "json_key_duplicate_after_normalization"),
        ('[{"公司代號":"2330"," 公司代號 ":"2330","資料年月":"11509"}]', "json_key_duplicate_after_normalization"),
        ('[{"公司代號":"2330","資料年月":11509}]', "source_row_identity_invalid:0:identity_fields_missing_or_non_text"),
        ('[{"公司代號":"2330","資料年月":"11513"}]', "source_row_identity_invalid:0:roc_period_invalid"),
    ],
    ids=("duplicate-json-key", "normalized-key-collision", "numeric-period", "invalid-month"),
)
def test_all_rows_must_have_unambiguous_identity(raw_text: str, reason: str):
    raw_bytes = raw_text.encode("utf-8")
    with pytest.raises(TwseMonthlyRevenuePreparationError) as exc_info:
        _prepare(_capture(raw_bytes=raw_bytes))

    assert exc_info.value.reason_code == reason


@pytest.mark.parametrize(
    ("field", "value", "reason_fragment"),
    [
        ("公司名稱", None, "target_required_fields_non_text"),
        ("營業收入-當月營收", "", "value_missing"),
        ("營業收入-當月營收", "NaN", "value_not_finite"),
        ("營業收入-當月營收", "Infinity", "value_not_finite"),
        ("營業收入-去年當月營收", "bad", "value_invalid_decimal"),
        ("營業收入-去年同月增減(%)", "--", "value_invalid_decimal"),
        ("營業收入-當月營收", "1" * 129, "value_decimal_token_too_long"),
        ("營業收入-當月營收", "1" * 65, "value_decimal_digits_exceeded"),
        ("營業收入-當月營收", "1e33", "value_decimal_exponent_exceeded"),
    ],
    ids=(
        "nontext-company", "blank-amount", "nan-amount", "infinite-amount",
        "bad-amount", "bad-percent", "decimal-token-limit", "decimal-digit-limit",
        "decimal-exponent-limit",
    ),
)
def test_target_required_fields_and_decimal_values_fail_with_field_reasons(
    field: str, value: str | None, reason_fragment: str
):
    row = _row()
    if value is None:
        row[field] = None  # type: ignore[assignment]
    else:
        row[field] = value

    with pytest.raises(TwseMonthlyRevenuePreparationError) as exc_info:
        _prepare(_capture([row]))

    assert reason_fragment in exc_info.value.reason_code


@pytest.mark.parametrize(
    ("period", "reason"),
    [
        ("11509", "requested_period_invalid"),
        ("2026-13", "requested_period_invalid"),
        ("0001-01", "requested_period_out_of_range"),
    ],
)
def test_requested_period_must_be_valid_gregorian_year_month(period: str, reason: str):
    with pytest.raises(TwseMonthlyRevenuePreparationError) as exc_info:
        _prepare(_capture([_row()]), period=period)

    assert exc_info.value.reason_code == reason


def test_report_date_is_date_only_and_batch_clock_cannot_precede_body_completion():
    with pytest.raises(TwseMonthlyRevenuePreparationError, match="target_report_date_not_date_only"):
        _prepare(_capture([_row(report_date="2026-10-10T09:30:00+08:00")]))

    with pytest.raises(TwseMonthlyRevenuePreparationError) as exc_info:
        _prepare(
            _capture([_row()]),
            batch_completed_at=datetime(2026, 10, 14, 7, 14, tzinfo=timezone.utc),
        )
    assert exc_info.value.reason_code == "successful_batch_clock_precedes_body_completion"


def test_report_date_and_requested_period_cannot_be_after_successful_batch():
    with pytest.raises(TwseMonthlyRevenuePreparationError) as report_date_error:
        _prepare(_capture([_row(report_date="1151015")]))
    assert report_date_error.value.reason_code == (
        "target_report_date_after_successful_batch_date"
    )

    with pytest.raises(TwseMonthlyRevenuePreparationError) as period_error:
        _prepare(_capture([_row()]), period="2026-11")
    assert period_error.value.reason_code == (
        "requested_period_after_successful_batch_month"
    )


def test_declared_big5_charset_is_rejected_instead_of_decoding_as_utf8():
    with pytest.raises(TwseMonthlyRevenuePreparationError) as exc_info:
        _prepare(
            _capture(
                [_row()],
                content_type_original_text="application/json; charset=Big5",
            )
        )
    assert exc_info.value.reason_code == "content_type_charset_not_utf8"


def test_json_nonfinite_constants_are_rejected():
    with pytest.raises(TwseMonthlyRevenuePreparationError) as exc_info:
        _prepare(_capture(raw_bytes=b"[NaN]"))
    assert exc_info.value.reason_code == "json_non_finite_constant"


def test_json_nesting_depth_is_bounded_before_parsing(monkeypatch):
    monkeypatch.setattr(preparation_module, "MAX_JSON_NESTING_DEPTH", 8)
    raw_bytes = b'[{"extra":' + b"[" * 8 + b"0" + b"]" * 8 + b"}]"

    with pytest.raises(TwseMonthlyRevenuePreparationError) as exc_info:
        _prepare(_capture(raw_bytes=raw_bytes))
    assert exc_info.value.reason_code == "json_nesting_depth_exceeds_limit"


def test_json_row_count_is_bounded_before_target_selection(monkeypatch):
    monkeypatch.setattr(preparation_module, "MAX_JSON_ROWS", 2)
    rows = [
        _row("2330", period="11509"),
        _row("2317", period="11509"),
        _row("2454", period="11509"),
    ]

    with pytest.raises(TwseMonthlyRevenuePreparationError) as exc_info:
        _prepare(_capture(rows))
    assert exc_info.value.reason_code == "json_row_count_exceeds_limit"
