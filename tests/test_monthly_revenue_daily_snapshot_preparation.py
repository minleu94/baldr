from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import hashlib
from zoneinfo import ZoneInfo

import pytest

from data_module.daily_source_snapshot import (
    DailySourceSnapshotError, DailySourceTransportCapture, DailySourceUseScope,
)
from data_module.monthly_revenue_daily_snapshot_preparation import prepare_daily_monthly_revenue_capture


TAIPEI = ZoneInfo("Asia/Taipei")
HEADERS = (
    "公司代號", "公司名稱", "當月營收", "上月營收", "去年當月營收",
    "當月累計營收", "去年累計營收",
)


def _html(*, second_code: str = "2317", amount: str = "1,000", suffix: str = "") -> str:
    header = "<tr>" + "".join(f"<th>{item}</th>" for item in HEADERS) + "</tr>"
    rows = "".join(
        "<tr>" + "".join(f"<td>{item}</td>" for item in cells) + "</tr>"
        for cells in (
            ("2330", "台積電", amount, "900", "800", "9,000", "8,000"),
            (second_code, "鴻海", "2,000", "1,800", "1,600", "18,000", "16,000"),
        )
    )
    return f"<html><head></head><body>上市公司115年9月份 單位：新臺幣千元<table>{header}{rows}{suffix}</table></body></html>"


def _scope() -> DailySourceUseScope:
    return DailySourceUseScope(
        dataset_id="fundamental_current_observations.monthly_revenue",
        source_id="mops.monthly_revenue_static_snapshot", market="twse",
        parser_version="mops-current-revenue-normalizer.v2",
        source_schema_version="mops-static-snapshot.v2", unit="TWD",
        intended_use="recommendation_current_fundamental",
    )


def _capture(html: str) -> DailySourceTransportCapture:
    raw = html.encode("big5")
    return DailySourceTransportCapture(
        raw_response_bytes=raw,
        official_source_url="https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_115_9_0.html",
        response_status=200, content_type="text/html; charset=big5",
        declared_decoding_encoding="big5", decoding_basis="http_content_type_charset",
        html_meta_charset_original_text=None,
        body_completed_at=datetime(2026, 10, 14, 15, 35, tzinfo=TAIPEI),
        transport_sha256=hashlib.sha256(raw).hexdigest(),
        response_body_complete=True, received_body_bytes=len(raw),
        content_length_original_text=str(len(raw)),
        body_completion_evidence_ref="eof:synthetic-complete-source-fixture",
    )


def _prepare(html: str, **changes: str):
    return prepare_daily_monthly_revenue_capture(
        capture=_capture(html), scope=_scope(), period=changes.get("period", "2026-09"),
        validation_id="synthetic-monthly-complete-partition",
    )


def test_big5_complete_market_partition_preserves_canonical_version_and_missing_official_hour():
    html = _html()
    result = _prepare(html)
    assert result.canonical_source_bytes == html.encode("utf-8")
    assert result.transport_capture.raw_response_bytes == html.encode("big5")
    assert result.records[0].raw_source_sha256 != result.transport_capture.transport_sha256
    assert [row["stock_code"] for row in result.rows] == ["2330", "2317"]
    assert result.validation.expected_record_count == result.validation.actual_record_count == 2
    assert result.validation.expected_partition_ids == ("twse:2026-09:source_report_rows",)
    assert result.validation.official_timestamp_parse_check.reason_code == "official_timestamp_not_provided"
    assert all(record.official_timestamp is None for record in result.records)
    assert result.source_version.endswith("sha256:" + hashlib.sha256(html.encode("utf-8")).hexdigest())
    assert "body_completed_at:2026-10-14T07:35:00+00:00" in result.source_version
    # 仍是來源千元；交由既有 Decimal normalizer 轉 TWD，不能在候選重複乘。
    assert result.rows[0]["current_month_revenue"] == "1000"
    assert result.source_unit == "TWD-thousand"
    mutated = result.rows
    mutated[0]["current_month_revenue"] = "999"
    assert result.rows[0]["current_month_revenue"] == "1000"


@pytest.mark.parametrize("html,reason", [
    (_html(second_code="2330"), "missing_or_duplicate_source_rows"),
    (_html(suffix="<tr><td>2454</td><td>截短行</td></tr>"), "data_row_width_or_nesting_invalid"),
    (_html().replace("</html>", ""), "report_end_missing"),
    (_html().replace("<th>上月營收</th>", "<th>當月營收</th>"), "header_ambiguous"),
    (_html().replace("<table>", "<table><tr><td><table>").replace("</table>", "</table></td></tr></table>"), "nested_source_table_not_supported"),
    (_html(amount="NaN"), "value_not_finite"),
    (_html(amount=""), "value_missing_or_invalid"),
    (_html().replace("新臺幣千元", "元"), "unit_not_explicit"),
    (_html().replace("115年9月份", "115年8月份"), "title_mismatch"),
    (_html().replace("上市公司", "上櫃公司"), "title_mismatch"),
])
def test_source_failures_are_rejected_before_snapshot_acceptance(html: str, reason: str):
    with pytest.raises(DailySourceSnapshotError, match=reason):
        _prepare(html)


def test_new_scope_and_future_period_do_not_reuse_monthly_acceptance():
    with pytest.raises(DailySourceSnapshotError, match="scope_mismatch"):
        prepare_daily_monthly_revenue_capture(
            capture=_capture(_html()), scope=replace(_scope(), unit="USD"),
            period="2026-09", validation_id="synthetic-scope-reject",
        )
    with pytest.raises(DailySourceSnapshotError, match="period_not_completed"):
        _prepare(_html(), period="2026-10")
