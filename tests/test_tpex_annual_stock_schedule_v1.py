"""重用完整官方年度原件，核股票範圍、跨列與拒絕邊界。"""

from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re

import pytest

from data_module.official_calendar_bundle import (
    OfficialCalendarBundleError,
    parse_tpex_annual_stock_schedule_v1,
)
from data_module.tpex_trading_date_html_v1 import (
    TpexTradingDateHtmlError,
    decode_tpex_trading_date_rows_v1,
)


FIXTURE = Path(__file__).parent / "fixtures/p0_official_sources/tpex_trading_date_2026_qa49.json"
RAW_SHA = "c5cea6bd3a10bc7cd3e577d9ad78e600ae7d64508a1bc9b09be32fb396d0dc41"
HTML_SHA = "b7c0ae6990f4e14aff19decf1932243a0d867f1abbad51d5ebc28eb7c05d7432"


def _raw() -> bytes:
    raw = FIXTURE.read_bytes()
    assert len(raw) == 8792 and hashlib.sha256(raw).hexdigest() == RAW_SHA
    return raw


def _html() -> str:
    return json.loads(_raw())["data"]["html"]


def _from_html(html: str) -> bytes:
    return json.dumps({"stat": "ok", "data": {"html": html}, "endDate": "20260101"},
                      ensure_ascii=False).encode("utf-8")


def _changed(old: str, new: str) -> bytes:
    html = _html()
    assert old in html
    return _from_html(html.replace(old, new, 1))


def _decode(raw: bytes):
    return decode_tpex_trading_date_rows_v1(
        raw, expected_year=2026, expected_sha256=hashlib.sha256(raw).hexdigest(),
    )


def _parse(raw: bytes):
    return parse_tpex_annual_stock_schedule_v1(
        raw, expected_year=2026, expected_sha256=hashlib.sha256(raw).hexdigest(),
    )


def test_saved_raw_preserves_hashes_rowspans_multidates_and_optional_td_end() -> None:
    result = _decode(_raw())
    assert result.raw_sha256 == RAW_SHA and result.html_sha256 == HTML_SHA
    assert result.year == 2026 and result.source_baseline_date == "20260101"
    assert len(result.rows) == 23
    assert [row.date_text for row in result.rows if row.name == "和平紀念日"] == ["2月27日", "2月28日"]
    assert [row.date_text for row in result.rows if row.name == "兒童節及民族掃墓節"] == [
        "4月3日", "4月4日", "4月5日", "4月6日",
    ]
    spring = next(row for row in result.rows if row.name == "農曆除夕及春節")
    assert spring.date_text.split() == ["2月15日", "2月16日", "2月17日", "2月18日", "2月19日", "2月20日"]
    dragon = next(row for row in result.rows if row.name == "端午節")
    assert dragon.description == "依規定放假1日。"
    stock = next(row for row in result.rows if "股票交易系統" in row.name)
    bond = next(row for row in result.rows if "債券等殖成交系統" in row.name)
    assert stock.date_text == bond.date_text == "2月11日"
    assert stock.description == bond.description == "2月12日及2月13日市場無交易，僅辦理給付結算。"


def test_stock_sessions_ignore_bond_closures_and_keep_settlement_only_days_closed() -> None:
    schedule = _parse(_raw())
    assert schedule.stock_settlement_only_dates == ("2026-02-12", "2026-02-13")
    assert len(schedule.ignored_non_stock_rows) == 3
    assert schedule.expected_session_dates(date(2026, 2, 1), date(2026, 2, 28)) == tuple(
        f"2026-02-{day:02d}" for day in (2, 3, 4, 5, 6, 9, 10, 11, 23, 24, 25, 26)
    )
    assert "2026-02-11" in schedule.open_marker_dates
    assert "2026-02-23" in schedule.open_marker_dates
    october = schedule.expected_session_dates(date(2026, 10, 1), date(2026, 10, 31))
    assert len(october) == 20
    assert "2026-10-09" not in october and "2026-10-26" not in october
    assert schedule.expected_session_dates(date(2026, 6, 19), date(2026, 6, 19)) == ()
    assert schedule.candidate_only and not schedule.historical_pit_eligible
    assert not schedule.performance_eligible
    assert not hasattr(schedule, "available_hour")


def test_93_day_inclusive_limit_and_wrong_year_or_datetime_rejected() -> None:
    schedule = _parse(_raw())
    assert schedule.expected_session_dates(date(2026, 1, 1), date(2026, 4, 3))
    for start, end in (
        (date(2026, 1, 1), date(2026, 4, 4)),
        (date(2026, 2, 2), date(2026, 2, 1)),
        (date(2025, 12, 31), date(2026, 1, 1)),
        (datetime(2026, 1, 1), date(2026, 1, 2)),
    ):
        with pytest.raises(OfficialCalendarBundleError):
            schedule.expected_session_dates(start, end)


@pytest.mark.parametrize("year", [True, "2026", 1911, 2200])
def test_decoder_rejects_year_outside_exact_contract(year: object) -> None:
    with pytest.raises(TpexTradingDateHtmlError):
        decode_tpex_trading_date_rows_v1(_raw(), expected_year=year, expected_sha256=RAW_SHA)


def test_external_hash_raw_type_size_and_actual_year_are_required() -> None:
    for raw, sha, year in (
        (_raw() + b" ", RAW_SHA, 2026),
        (_raw(), RAW_SHA.upper(), 2026),
        (bytearray(_raw()), RAW_SHA, 2026),
        (b"x" * (4 * 1024**2 + 1), "0" * 64, 2026),
        (_raw(), RAW_SHA, 2027),
    ):
        with pytest.raises(TpexTradingDateHtmlError):
            decode_tpex_trading_date_rows_v1(raw, expected_year=year, expected_sha256=sha)


@pytest.mark.parametrize("raw", [
    b'{"stat":"ok","stat":"ok","data":{},"endDate":"20260101"}',
    b'{"stat":"ok","data":{"html":NaN},"endDate":"20260101"}',
    b'{"stat":"ok","data":{"html":Infinity},"endDate":"20260101"}',
    b'{"stat":"ok","data":{"html":"\\ud800"},"endDate":"20260101"}',
    b'{"stat":"ok","data":{"html":"\xff"},"endDate":"20260101"}',
    b'{"stat":"ok",',
])
def test_rejects_duplicate_nonfinite_non_utf8_surrogate_or_partial_json(raw: bytes) -> None:
    with pytest.raises(TpexTradingDateHtmlError):
        _decode(raw)


@pytest.mark.parametrize(("field", "value"), [
    ("stat", "success"), ("endDate", "20261015"),
    ("data", {"html": "", "extra": 1}), ("extra", True),
])
def test_schema_and_baseline_are_exact(field: str, value: object) -> None:
    source = json.loads(_raw())
    source[field] = value
    with pytest.raises(TpexTradingDateHtmlError):
        _decode(json.dumps(source).encode("utf-8"))


@pytest.mark.parametrize(("old", "new"), [
    ("中華民國115年", "中華民國114年"),
    ("紀念節日名稱", "事件名稱"),
    ('rowspan="4"', 'rowspan="0"'),
    ('rowspan="4"', 'rowspan="65"'),
    ('rowspan="4"', 'rowspan="64"'),
    ('rowspan="4"', 'rowspan="2" rowspan="4"'),
    ('rowspan="4"', 'colspan="2"'),
    ("<strong>股票交易系統</strong>", "<strong>股票交易系統"),
    ("<strong>股票交易系統</strong>", "<table><tr><td>股票</td></tr></table>"),
    ("</table>", "</table><script>blocked()</script>"),
    ("</table>", "</table><iframe></iframe>"),
])
def test_html_invalid_structure_and_active_content_are_rejected(old: str, new: str) -> None:
    with pytest.raises(TpexTradingDateHtmlError):
        _decode(_changed(old, new))


def test_complete_json_does_not_make_eof_open_html_valid() -> None:
    html = _html()
    for broken in (html[:html.rfind("</table>")], html[:html.rfind("</tr>")], html[:html.rfind("</td>")]):
        with pytest.raises(TpexTradingDateHtmlError):
            _decode(_from_html(broken))


def test_legal_omitted_cell_end_tags_preserve_the_same_values() -> None:
    html = _html().replace("</td>", "").replace("</th>", "")
    changed = _decode(_from_html(html))
    original = _decode(_raw())
    assert changed.rows == original.rows
    assert changed.html_sha256 != original.html_sha256


@pytest.mark.parametrize(("old", "new", "reason"), [
    ("中秋節", "新假日", "unknown_row_name"),
    ("6月19日", "6月31日", "date_invalid"),
    ("6月19日", "6月18日", "date_weekday_mismatch"),
    ("2月12日及2月13日市場無交易", "2月11日及2月13日市場無交易", "stock_settlement_order_invalid"),
    ("2月12日及2月13日市場無交易", "2月13日市場無交易", "spring_stock_gap_missing"),
    ("2月12日及2月13日市場無交易", "股票市場休市", "stock_settlement_description_invalid"),
])
def test_financial_schema_drift_and_incomplete_spring_gap_fail_closed(
    old: str, new: str, reason: str,
) -> None:
    # 國際債券描述也有相同尾字，指定股票列後面的原文以避免改錯市場。
    html = _html()
    stock_start = html.index("<strong>股票交易系統</strong>")
    assert old in html[stock_start:]
    raw = _from_html(html[:stock_start] + html[stock_start:].replace(old, new, 1))
    with pytest.raises(OfficialCalendarBundleError, match=reason):
        _parse(raw)


def test_missing_description_is_not_filled_and_not_accepted_as_holiday() -> None:
    html = _html()
    start = html.index('<td class="page-table-body-left">端午節</td>')
    end = html.index("</tr>", start)
    row = html[start:end]
    assert '<td class="page-table-body-left">依規定放假1日。' in row
    row = row[:row.rindex('<td class="page-table-body-left">')]
    missing = _from_html(html[:start] + row + html[end:])
    assert next(item for item in _decode(missing).rows if item.name == "端午節").description is None
    with pytest.raises(OfficialCalendarBundleError, match="holiday_description_missing"):
        _parse(missing)


def test_required_row_missing_and_open_closed_conflict_are_rejected() -> None:
    html = _html()
    without_newyear = re.sub(r"<tr>\s*<td[^>]*>國曆新年開始交易日.*?</tr>", "", html, count=1, flags=re.S)
    assert without_newyear != html
    with pytest.raises(OfficialCalendarBundleError, match="required_rows_missing"):
        _parse(_from_html(without_newyear))
    # 2026/1/2也是星期五；改成勞動節仍不得覆蓋已宣告交易的日期。
    with pytest.raises(OfficialCalendarBundleError, match="conflicting_stock_state"):
        _parse(_changed("5月1日", "1月2日"))


def test_duplicate_single_holiday_different_valid_weekday_does_not_close_an_extra_day() -> None:
    html = _html()
    added = '<tr><td>端午節</td><td>6月22日</td><td>一</td><td>依規定放假1日。</td></tr>'
    end = html.rfind("</table>")
    with pytest.raises(OfficialCalendarBundleError, match="duplicate_holiday_row"):
        _parse(_from_html(html[:end] + added + html[end:]))


def test_repeated_holiday_row_must_remain_a_consecutive_group() -> None:
    with pytest.raises(OfficialCalendarBundleError, match="holiday_group_nonconsecutive"):
        _parse(_changed("2月28日</td>", "3月7日</td>"))
