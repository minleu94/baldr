"""兩市場年度原件、完整分區與新evidence wire的限定驗證。"""

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import pytest

from app_module.recommendation_portfolio_annual_calendar_evidence_v1 import (
    PortfolioPeriodAnnualCalendarEvidenceV1,
    PortfolioPeriodAnnualCalendarEvidenceV1Error,
)
from app_module.recommendation_portfolio_calendar_evidence_v1 import (
    PortfolioPeriodCalendarEvidenceV1,
    PortfolioPeriodCalendarEvidenceV1Error,
)
from data_module.official_calendar_bundle import (
    OfficialCalendarBundleError,
    TPEX_ANNUAL_TRADING_DATE_URL,
    TWSE_HOLIDAY_SCHEDULE_URL,
    derive_annual_calendar_sessions_v1,
)
from data_module.official_calendar_transport_v1 import OfficialCalendarJsonTransportV1
from data_module.tpex_annual_calendar_transport_v1 import OfficialCalendarTpexAnnualJsonTransportV1


_FIXTURES = Path(__file__).parent / "fixtures/p0_official_sources"
_CLOCK = datetime(2026, 10, 15, 5, 0, tzinfo=timezone.utc)


def _transports():
    twse_raw = (_FIXTURES / "twse_holiday_schedule_2026_qa27.json").read_bytes()
    tpex_raw = (_FIXTURES / "tpex_trading_date_2026_qa49.json").read_bytes()
    assert hashlib.sha256(twse_raw).hexdigest() == "7644c1a8af784c09f54670fd7413f536b13eb76c54d658058e8873d1aee32117"
    assert hashlib.sha256(tpex_raw).hexdigest() == "c5cea6bd3a10bc7cd3e577d9ad78e600ae7d64508a1bc9b09be32fb396d0dc41"
    # 只重用真raw；這裡的時鐘為合成，並非原取得或成功批次時間。
    twse = OfficialCalendarJsonTransportV1(
        kind="twse", key="2026", request_url=TWSE_HOLIDAY_SCHEDULE_URL + "?queryYear=115",
        response_url=TWSE_HOLIDAY_SCHEDULE_URL + "?queryYear=115", http_status=200,
        headers=(("content-type", "application/json"), ("content-length", str(len(twse_raw)))),
        started_at=_CLOCK, body_completed_at=_CLOCK + timedelta(seconds=1),
        raw_bytes=twse_raw, raw_sha256=hashlib.sha256(twse_raw).hexdigest(),
        received_body_bytes=len(twse_raw), eof_observed=True,
    )
    tpex = OfficialCalendarTpexAnnualJsonTransportV1(
        year=2026, request_url=TPEX_ANNUAL_TRADING_DATE_URL, response_url=TPEX_ANNUAL_TRADING_DATE_URL,
        request_method="POST", request_body=b"date=2026&id=", http_status=200,
        headers=(("content-type", "application/json"), ("content-length", str(len(tpex_raw)))),
        started_at=_CLOCK, body_completed_at=_CLOCK + timedelta(seconds=2),
        raw_bytes=tpex_raw, raw_sha256=hashlib.sha256(tpex_raw).hexdigest(),
        received_body_bytes=len(tpex_raw), eof_observed=True,
    )
    return twse, tpex


def _build():
    twse, tpex = _transports()
    return PortfolioPeriodAnnualCalendarEvidenceV1.build(
        start_date=date(2026, 2, 1), end_date=date(2026, 2, 28),
        twse_transports=[twse], tpex_transports=[tpex],
    )


def _changed_twse(field: str, value: str, *, row_index: int = 0):
    twse, tpex = _transports()
    rows = json.loads(twse.raw_bytes)
    rows[row_index][field] = value
    raw = json.dumps(rows, ensure_ascii=False).encode("utf-8")
    return replace(twse, raw_bytes=raw, raw_sha256=hashlib.sha256(raw).hexdigest(),
                   received_body_bytes=len(raw), headers=(("content-type", "application/json"),)), tpex


def test_annual_evidence_preserves_both_raws_and_february_stock_sessions() -> None:
    evidence = _build()
    expected = tuple(f"2026-02-{day:02d}" for day in (2, 3, 4, 5, 6, 9, 10, 11, 23, 24, 25, 26))
    assert evidence.start_date == "2026-02-01" and evidence.end_date == "2026-02-28"
    assert evidence.expected_session_dates("twse") == expected
    assert evidence.expected_session_dates("tpex") == expected
    assert evidence.captured_at == (_CLOCK + timedelta(seconds=2)).isoformat()
    wire = evidence.to_dict()
    assert len(wire["twse_transports"]) == len(wire["tpex_transports"]) == 1
    assert PortfolioPeriodAnnualCalendarEvidenceV1.from_json(evidence.to_json()) == evidence
    assert evidence.candidate_only and not evidence.historical_pit_eligible
    assert not evidence.performance_eligible and not evidence.formal_clock_eligible
    with pytest.raises(PortfolioPeriodCalendarEvidenceV1Error):
        PortfolioPeriodCalendarEvidenceV1.from_json(evidence.to_json())
    with pytest.raises(PortfolioPeriodAnnualCalendarEvidenceV1Error):
        evidence.expected_session_dates("unknown")


@pytest.mark.parametrize(("twse_count", "tpex_count"), [(0, 1), (1, 0), (2, 1), (1, 2)])
def test_missing_or_duplicate_market_partition_is_not_a_full_calendar(twse_count: int, tpex_count: int) -> None:
    twse, tpex = _transports()
    with pytest.raises((OfficialCalendarBundleError, PortfolioPeriodAnnualCalendarEvidenceV1Error)):
        PortfolioPeriodAnnualCalendarEvidenceV1.build(
            start_date=date(2026, 2, 1), end_date=date(2026, 2, 28),
            twse_transports=[twse] * twse_count, tpex_transports=[tpex] * tpex_count,
        )


def test_cross_year_missing_year_and_94_days_rejected_while_93_inclusive_allowed() -> None:
    twse, tpex = _transports()
    assert derive_annual_calendar_sessions_v1(
        start_date=date(2026, 1, 1), end_date=date(2026, 4, 3),
        twse_transports=[twse], tpex_transports=[tpex],
    )
    for first, last in ((date(2026, 1, 1), date(2026, 4, 4)),
                        (date(2025, 12, 31), date(2026, 1, 1))):
        with pytest.raises(OfficialCalendarBundleError):
            derive_annual_calendar_sessions_v1(
                start_date=first, end_date=last, twse_transports=[twse], tpex_transports=[tpex],
            )


@pytest.mark.parametrize(("field", "value", "reason"), [
    ("Weekday", "五", "weekday_mismatch"),
    ("Name", "未識別事件", "unknown_row_name"),
    ("Description", "<script>drift</script>", "description_markup_unknown"),
    ("Date", "1140101", "year_duplicate_or_order_invalid"),
    ("extra", "unexpected", "row_schema_invalid"),
])
def test_twse_annual_new_scope_checks_real_schema_and_weekday(field: str, value: str, reason: str) -> None:
    twse, tpex = _changed_twse(field, value)
    with pytest.raises(OfficialCalendarBundleError, match=reason):
        derive_annual_calendar_sessions_v1(
            start_date=date(2026, 2, 1), end_date=date(2026, 2, 28),
            twse_transports=[twse], tpex_transports=[tpex],
        )


def test_unknown_or_malformed_twse_outside_requested_month_is_still_rejected() -> None:
    twse, tpex = _changed_twse("Name", "年底未知事件", row_index=-1)
    with pytest.raises(OfficialCalendarBundleError, match="unknown_row_name"):
        derive_annual_calendar_sessions_v1(
            start_date=date(2026, 2, 1), end_date=date(2026, 2, 28),
            twse_transports=[twse], tpex_transports=[tpex],
        )


@pytest.mark.parametrize(("field", "value"), [
    ("candidate_only", 1), ("historical_pit_eligible", 0),
    ("performance_eligible", True), ("formal_clock_eligible", True),
    ("captured_at", "2020-01-01T00:00:00+00:00"),
    ("evidence_sha256", "0" * 64),
    ("expected_session_dates", {"twse": ["2026-02-12"], "tpex": ["2026-02-12"]}),
    ("extra", True),
])
def test_annual_codec_rederives_dates_clock_flags_and_hash(field: str, value: object) -> None:
    wire = _build().to_dict()
    wire[field] = value
    with pytest.raises(PortfolioPeriodAnnualCalendarEvidenceV1Error):
        PortfolioPeriodAnnualCalendarEvidenceV1.from_dict(wire)


def test_json_duplicate_nonfinite_noncanonical_and_size_are_rejected() -> None:
    evidence = _build()
    raw = evidence.to_json()
    bad = [raw + " ", '{"schema_version":1,"schema_version":1}', '{"x":NaN}', b"\xff"]
    for value in bad:
        with pytest.raises(PortfolioPeriodAnnualCalendarEvidenceV1Error):
            PortfolioPeriodAnnualCalendarEvidenceV1.from_json(value)
    with pytest.raises(PortfolioPeriodAnnualCalendarEvidenceV1Error):
        PortfolioPeriodAnnualCalendarEvidenceV1.from_json(b"x" * (32 * 1024**2 + 1))


def test_frozen_evidence_rechecks_bypassed_mutation_on_read() -> None:
    evidence = _build()
    object.__setattr__(evidence, "start_date", "2026-02-02")
    with pytest.raises(PortfolioPeriodAnnualCalendarEvidenceV1Error):
        evidence.expected_session_dates("twse")


def test_build_freezes_input_sequences_before_external_list_changes() -> None:
    twse, tpex = _transports()
    twse_values, tpex_values = [twse], [tpex]
    evidence = PortfolioPeriodAnnualCalendarEvidenceV1.build(
        start_date=date(2026, 2, 1), end_date=date(2026, 2, 28),
        twse_transports=twse_values, tpex_transports=tpex_values,
    )
    expected = evidence.to_json()
    twse_values.clear()
    tpex_values.clear()
    assert evidence.to_json() == expected


def test_missing_twse_substitute_holiday_cannot_become_an_open_weekday() -> None:
    twse, tpex = _transports()
    rows = json.loads(twse.raw_bytes)
    remaining = [row for row in rows if row["Date"] != "1150227"]
    assert len(remaining) == len(rows) - 1
    # 真2/28說明只有放假1日，不能從這段文字猜出已遺失的2/27列。
    assert next(row for row in remaining if row["Date"] == "1150228")["Description"] == "依規定放假1日。"
    raw = json.dumps(remaining, ensure_ascii=False).encode("utf-8")
    incomplete = replace(twse, raw_bytes=raw, raw_sha256=hashlib.sha256(raw).hexdigest(),
                         received_body_bytes=len(raw), headers=(("content-type", "application/json"),))
    with pytest.raises(OfficialCalendarBundleError, match="annual_calendar_holiday_dates_disagree"):
        derive_annual_calendar_sessions_v1(
            start_date=date(2026, 2, 1), end_date=date(2026, 2, 28),
            twse_transports=[incomplete], tpex_transports=[tpex],
        )


def test_holiday_quality_guard_does_not_replace_one_markets_stock_settlement_dates() -> None:
    twse, tpex = _transports()
    rows = json.loads(twse.raw_bytes)
    index = next(i for i, row in enumerate(rows) if row["Name"] == "農曆春節前最後交易日")
    # 明示合成變體：股票最後交易提早一天，國定假日完全不變。
    rows[index]["Date"], rows[index]["Weekday"] = "1150210", "二"
    rows.insert(index + 1, {"Name": "市場無交易，僅辦理結算交割作業", "Date": "1150211",
                            "Weekday": "三", "Description": ""})
    raw = json.dumps(rows, ensure_ascii=False).encode("utf-8")
    altered = replace(twse, raw_bytes=raw, raw_sha256=hashlib.sha256(raw).hexdigest(),
                      received_body_bytes=len(raw), headers=(("content-type", "application/json"),))
    left, right = derive_annual_calendar_sessions_v1(
        start_date=date(2026, 2, 1), end_date=date(2026, 2, 28),
        twse_transports=[altered], tpex_transports=[tpex],
    )
    assert "2026-02-11" not in left and "2026-02-11" in right
