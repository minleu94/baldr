from __future__ import annotations

from datetime import date
import hashlib
from pathlib import Path
from types import SimpleNamespace

from data_module.monthly_revenue_snapshot_selection import (
    expected_latest_monthly_revenue_period,
    select_latest_monthly_revenue_snapshot,
)
from scripts import capture_mops_monthly_revenue_candidate as capture


def _row(market: str) -> dict[str, str]:
    return {
        "market": market,
        "period": "2026-08",
        "stock_code": "2330" if market == "twse" else "6488",
        "company_name": "測試公司",
        "current_month_revenue": "100",
        "previous_month_revenue": "90",
        "previous_year_month_revenue": "80",
        "mom_pct": "11.11",
        "yoy_pct": "25",
        "cumulative_revenue": "1000",
        "previous_year_cumulative_revenue": "900",
        "cumulative_yoy_pct": "11.11",
        "note": "",
        "fetched_at": "2026-10-29T00:00:00+00:00",
        "source": "mops.monthly_revenue_static_snapshot",
        "source_version": f"version-{market}",
    }


def test_expected_monthly_period_rolls_weekend_deadline_and_year_boundary() -> None:
    assert expected_latest_monthly_revenue_period(date(2026, 10, 10)) == "2026-08"
    assert expected_latest_monthly_revenue_period(date(2026, 10, 12)) == "2026-08"
    assert expected_latest_monthly_revenue_period(date(2026, 10, 13)) == "2026-09"
    assert expected_latest_monthly_revenue_period(date(2026, 1, 13)) == "2025-12"


def test_complete_capture_publishes_selector_visible_candidate_with_hashes(
    tmp_path: Path, monkeypatch
) -> None:
    rows = [_row("twse"), _row("tpex")]

    def fake_build(**kwargs):
        raw_dir = kwargs["save_html_dir"]
        raw_dir.mkdir(parents=True)
        (raw_dir / "twse_2026-08.html").write_text("TWSE raw", encoding="utf-8")
        (raw_dir / "tpex_2026-08.html").write_text("TPEX raw", encoding="utf-8")
        return SimpleNamespace(
            rows=rows,
            requested_periods=("2026-08",),
            fetched_periods=("2026-08",),
            diagnostics=(),
            cancelled=False,
        )

    monkeypatch.setattr(capture, "build_mops_monthly_revenue_snapshot", fake_build)
    result = capture.capture_candidate(tmp_path / "output", today=date(2026, 10, 10))

    candidate = Path(str(result["candidate_csv"]))
    assert result["status"] == "captured"
    assert result["formal_database_written"] is False
    assert result["availability_mapping_emitted"] is False
    assert select_latest_monthly_revenue_snapshot(candidate.parents[2]) == candidate
    assert result["candidate_csv_sha256"] == hashlib.sha256(candidate.read_bytes()).hexdigest()
    assert (candidate.parent / "capture_complete.json").is_file()
    assert set(result["market_row_counts"]) == {"twse", "tpex"}
    (candidate.parent / "capture_complete.json").unlink()
    assert select_latest_monthly_revenue_snapshot(candidate.parents[2]) is None


def test_incomplete_market_capture_never_becomes_selector_visible(
    tmp_path: Path, monkeypatch
) -> None:
    rows = [_row("twse")]

    def fake_build(**kwargs):
        raw_dir = kwargs["save_html_dir"]
        raw_dir.mkdir(parents=True)
        (raw_dir / "twse_2026-08.html").write_text("TWSE raw", encoding="utf-8")
        return SimpleNamespace(
            rows=rows,
            requested_periods=("2026-08",),
            fetched_periods=("2026-08",),
            diagnostics=(),
            cancelled=False,
        )

    monkeypatch.setattr(capture, "build_mops_monthly_revenue_snapshot", fake_build)
    result = capture.capture_candidate(tmp_path / "output", today=date(2026, 10, 10))

    assert result["status"] == "rejected"
    assert result["candidate_csv"] is None
    assert select_latest_monthly_revenue_snapshot(tmp_path / "output" / "monthly_revenue_mops_snapshots") is None
    assert Path(str(result["receipt_path"])).is_file()
