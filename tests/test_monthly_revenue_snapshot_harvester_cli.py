from __future__ import annotations

import csv
import io
import sys

from data_module.current_monthly_revenue_materialization import plan_current_revenue
from data_module.monthly_revenue_snapshot_selection import (
    select_latest_monthly_revenue_snapshot,
)
from scripts import fetch_mops_monthly_revenue_snapshot


MOPS_SAMPLE_HTML = """
<html>
  <body>
    <h1>\u4e0a\u5e02\u516c\u53f8115\u5e743\u6708\u4efd</h1>
    <p>\u55ae\u4f4d\uff1a\u5343\u5143</p>
    <div>出表日期：115/04/10</div>
    <table>
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
    </table>
  </body>
</html>
"""


def test_mops_snapshot_cli_retries_same_date_without_replacing_prior_capture(
    tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(
        fetch_mops_monthly_revenue_snapshot,
        "fetch_mops_static_monthly_revenue_html",
        lambda *, market, period: (
            MOPS_SAMPLE_HTML.replace("\u4e0a\u5e02", "\u4e0a\u6ac3").replace(
                "<td>2330</td>", "<td>6488</td>"
            )
            if market == "tpex"
            else MOPS_SAMPLE_HTML
        ),
    )

    exit_code = fetch_mops_monthly_revenue_snapshot.main(
        [
            "--start-period",
            "2026-03",
            "--end-period",
            "2026-03",
            "--markets",
            "twse,tpex",
            "--output-dir",
            str(tmp_path),
            "--fetch-date",
            "2026-06-16",
        ]
    )

    assert exit_code == 0
    first_csv = next((tmp_path / "captures").glob("run_*/mops_monthly_revenue_snapshot_*.csv"))
    first_csv_bytes = first_csv.read_bytes()
    first_raw_paths = tuple(sorted((first_csv.parent / "raw_html").glob("*.html")))
    first_raw_bytes = {path.name: path.read_bytes() for path in first_raw_paths}
    assert set(first_raw_bytes) == {"twse_2026-03.html", "tpex_2026-03.html"}
    rows = list(csv.DictReader(first_csv.open(encoding="utf-8-sig")))
    assert {row["stock_code"] for row in rows} == {"2330", "6488"}
    assert rows[0]["source"] == "mops.monthly_revenue_static_snapshot"
    first_plan = plan_current_revenue(first_csv)
    assert first_plan.custody["snapshot_sha256"]
    assert first_plan.custody["raw_artifacts"][0]["sha256"]
    assert all(row["unit"] == "TWD" for row in first_plan.records)
    assert all(row["period_basis"] == "monthly_flow" for row in first_plan.records)

    second_exit_code = fetch_mops_monthly_revenue_snapshot.main(
        [
            "--start-period", "2026-03", "--end-period", "2026-03",
            "--markets", "twse,tpex", "--output-dir", str(tmp_path),
            "--fetch-date", "2026-06-16",
        ]
    )
    assert second_exit_code == 0
    capture_csvs = tuple((tmp_path / "captures").glob("run_*/mops_monthly_revenue_snapshot_*.csv"))
    assert len(capture_csvs) == 2
    second_csv = next(path for path in capture_csvs if path != first_csv)
    second_raw_paths = tuple(sorted((second_csv.parent / "raw_html").glob("*.html")))
    second_plan = plan_current_revenue(second_csv)
    assert first_csv.read_bytes() == first_csv_bytes
    assert {path.name: path.read_bytes() for path in first_raw_paths} == first_raw_bytes
    assert {path.name: path.read_bytes() for path in second_raw_paths} == first_raw_bytes
    assert second_plan.custody["snapshot_sha256"]
    assert second_plan.custody["raw_artifacts"][0]["sha256"] == first_plan.custody["raw_artifacts"][0]["sha256"]
    assert all(row["unit"] == "TWD" for row in second_plan.records)
    assert all(row["period_basis"] == "monthly_flow" for row in second_plan.records)
    assert select_latest_monthly_revenue_snapshot(tmp_path) == second_csv
    assert "output_csv" in capsys.readouterr().out


def test_mops_snapshot_cli_does_not_crash_when_stdout_cannot_encode_chinese(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        fetch_mops_monthly_revenue_snapshot,
        "fetch_mops_static_monthly_revenue_html",
        lambda *, market, period: MOPS_SAMPLE_HTML,
    )
    stdout = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    monkeypatch.setattr(sys, "stdout", stdout)

    exit_code = fetch_mops_monthly_revenue_snapshot.main(
        [
            "--start-period",
            "2026-03",
            "--end-period",
            "2026-03",
            "--markets",
            "twse",
            "--output-dir",
            str(tmp_path),
            "--fetch-date",
            "2026-06-16",
        ]
    )

    assert exit_code == 0
