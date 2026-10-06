from __future__ import annotations

from datetime import date
from hashlib import sha256
from pathlib import Path

import pytest

import data_module.monthly_revenue_snapshot_harvester as harvester
from data_module.monthly_revenue_snapshot_harvester import (
    build_mops_monthly_revenue_snapshot,
    parse_mops_monthly_revenue_snapshot_html,
    write_mops_snapshot_csv,
)


MOPS_SAMPLE_HTML = """
<html>
  <body>
    <div>出表日期：115/04/10</div>
    <table>
      <tr><td>產業別</td><td>半導體業</td></tr>
      <tr>
        <th>公司代號</th><th>公司名稱</th><th>當月營收</th><th>上月營收</th>
        <th>去年當月營收</th><th>上月比較增減(%)</th><th>去年同月增減(%)</th>
        <th>當月累計營收</th><th>去年累計營收</th><th>前期比較增減(%)</th><th>備註</th>
      </tr>
      <tr>
        <td>2330</td><td>台積電</td><td>195,211,000</td><td>180,000,000</td>
        <td>160,000,000</td><td>8.45</td><td>22.00</td>
        <td>580,000,000</td><td>500,000,000</td><td>16.00</td><td></td>
      </tr>
      <tr>
        <td>合計</td><td></td><td>195,211,000</td>
      </tr>
    </table>
  </body>
</html>
"""


def test_parse_mops_snapshot_extracts_full_revenue_rows_without_available_date() -> None:
    rows, diagnostics = parse_mops_monthly_revenue_snapshot_html(
        MOPS_SAMPLE_HTML,
        market="twse",
        period="2026-03",
        fetched_at="2026-06-16T01:02:03Z",
        source_version="mops-static-2026-06-16",
    )

    assert diagnostics == ()
    assert len(rows) == 1
    row = rows[0]
    assert row["market"] == "twse"
    assert row["period"] == "2026-03"
    assert row["stock_code"] == "2330"
    assert row["company_name"] == "台積電"
    assert row["current_month_revenue"] == "195211000"
    assert row["previous_month_revenue"] == "180000000"
    assert row["previous_year_month_revenue"] == "160000000"
    assert row["mom_pct"] == "8.45"
    assert row["yoy_pct"] == "22.00"
    assert row["cumulative_revenue"] == "580000000"
    assert row["previous_year_cumulative_revenue"] == "500000000"
    assert row["cumulative_yoy_pct"] == "16.00"
    assert row["source"] == "mops.monthly_revenue_static_snapshot"
    assert "available_date" not in row


def test_parse_mops_snapshot_reports_diagnostic_when_headers_shift() -> None:
    html = "<html><body><table><tr><th>公司代號</th><th>公司名稱</th></tr><tr><td>2330</td><td>台積電</td></tr></table></body></html>"

    rows, diagnostics = parse_mops_monthly_revenue_snapshot_html(
        html,
        market="twse",
        period="2026-03",
        fetched_at="2026-06-16T01:02:03Z",
        source_version="mops-static-2026-06-16",
    )

    assert rows == []
    assert diagnostics
    assert diagnostics[0].code == "monthly_revenue_snapshot.mops_missing_required_columns"


def test_parse_mops_snapshot_deduplicates_repeated_company_rows() -> None:
    duplicated_html = MOPS_SAMPLE_HTML.replace(
        "</table>",
        """
      <tr>
        <td>2330</td><td>台積電</td><td>195,211,000</td><td>180,000,000</td>
        <td>160,000,000</td><td>8.45</td><td>22.00</td>
        <td>580,000,000</td><td>500,000,000</td><td>16.00</td><td></td>
      </tr>
    </table>
""",
    )

    rows, diagnostics = parse_mops_monthly_revenue_snapshot_html(
        duplicated_html,
        market="twse",
        period="2026-03",
        fetched_at="2026-06-16T01:02:03Z",
        source_version="mops-static-2026-06-16",
    )

    assert diagnostics == ()
    assert len(rows) == 1
    assert rows[0]["stock_code"] == "2330"


def test_build_mops_snapshot_fetches_markets_and_periods_with_summary() -> None:
    calls: list[tuple[str, str]] = []
    sleeps: list[float] = []

    def fake_fetch(*, market: str, period: str) -> str:
        calls.append((market, period))
        return MOPS_SAMPLE_HTML

    result = build_mops_monthly_revenue_snapshot(
        start_period="2026-03",
        end_period="2026-04",
        markets=("twse",),
        fetch_date=date(2026, 6, 16),
        fetch_html=fake_fetch,
        sleep_seconds=0.25,
        sleep=sleeps.append,
    )

    assert calls == [("twse", "2026-03"), ("twse", "2026-04")]
    assert sleeps == [0.25]
    assert len(result.rows) == 2
    assert result.requested_periods == ("2026-03", "2026-04")
    assert result.fetched_periods == ("2026-03", "2026-04")
    assert "parsed_rows: 2" in result.to_markdown()
    for row in result.rows:
        assert row["source_version"].startswith(
            f"mops-static-snapshot.v2:twse:{row['period']}:body_completed_at:"
        )
        assert row["source_version"].endswith(
            f":sha256:{sha256(MOPS_SAMPLE_HTML.encode('utf-8')).hexdigest()}"
        )


def test_build_records_each_source_time_after_its_response_completes(monkeypatch) -> None:
    source_times = iter(("2026-10-04T00:01:02.123456Z", "2026-10-04T00:03:04.654321Z"))
    monkeypatch.setattr(harvester, "_utc_now_text", lambda: next(source_times))

    result = build_mops_monthly_revenue_snapshot(
        start_period="2026-03",
        end_period="2026-03",
        markets=("twse", "tpex"),
        fetch_date=date(2026, 10, 4),
        fetch_html=lambda **_kwargs: MOPS_SAMPLE_HTML,
    )

    assert [(row["market"], row["fetched_at"]) for row in result.rows] == [
        ("tpex", "2026-10-04T00:03:04.654321Z"),
        ("twse", "2026-10-04T00:01:02.123456Z"),
    ]
    assert all("body_completed_at:" in row["source_version"] for row in result.rows)
    assert "2026-10-04T00:03:04.654321+00:00" in result.rows[0]["source_version"]
    assert "2026-10-04T00:01:02.123456+00:00" in result.rows[1]["source_version"]


def test_monthly_snapshot_cooperative_cancel_keeps_completed_market_rows() -> None:
    cancellation = {"requested": False}
    calls: list[str] = []

    def fake_fetch(*, market: str, period: str) -> str:
        calls.append(market)
        cancellation["requested"] = True
        return MOPS_SAMPLE_HTML

    result = build_mops_monthly_revenue_snapshot(
        start_period="2026-03",
        end_period="2026-03",
        markets=("twse", "tpex"),
        fetch_date=date(2026, 6, 16),
        fetch_html=fake_fetch,
        cancel_callback=lambda: cancellation["requested"],
    )

    assert result.cancelled is True
    assert calls == ["twse"]
    assert result.fetched_periods == ("2026-03",)
    assert len(result.rows) == 1
    assert result.rows[0]["market"] == "twse"


def test_raw_capture_target_collision_refuses_to_replace_existing_bytes(tmp_path) -> None:
    raw_dir = tmp_path / "raw_html"
    raw_dir.mkdir()
    raw_path = raw_dir / "twse_2026-03.html"
    original = b"previous raw capture\x00bytes"
    raw_path.write_bytes(original)

    with pytest.raises(FileExistsError):
        build_mops_monthly_revenue_snapshot(
            start_period="2026-03",
            end_period="2026-03",
            markets=("twse",),
            fetch_date=date(2026, 10, 4),
            fetch_html=lambda **_kwargs: MOPS_SAMPLE_HTML,
            save_html_dir=raw_dir,
        )

    assert raw_path.read_bytes() == original


def test_csv_capture_target_collision_refuses_to_replace_existing_bytes(tmp_path) -> None:
    csv_path = tmp_path / "snapshot.csv"
    original = b"previous csv capture\x00bytes"
    csv_path.write_bytes(original)

    with pytest.raises(FileExistsError):
        write_mops_snapshot_csv(csv_path, [])

    assert csv_path.read_bytes() == original


def test_capture_directory_creation_rejects_reparse_output_root(tmp_path, monkeypatch) -> None:
    output_base = tmp_path / "snapshots"
    output_base.mkdir()
    monkeypatch.setattr(
        harvester,
        "_is_reparse_point",
        lambda path: Path(path) == output_base,
    )

    with pytest.raises(ValueError, match="reparse point"):
        harvester.create_monthly_revenue_snapshot_capture_directory(
            output_base, fetch_date=date(2026, 10, 4)
        )

    assert not (output_base / "captures").exists()
