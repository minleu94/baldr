from __future__ import annotations

import csv

import pytest

from scripts import fetch_finmind_cashflow_candidate


def test_finmind_cashflow_cli_writes_candidate_only_rows(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(fetch_finmind_cashflow_candidate, "load_finmind_token", lambda token_file=None: "secret")
    monkeypatch.setattr(
        fetch_finmind_cashflow_candidate,
        "fetch_finmind_cashflow_rows",
        lambda stock_code, start_date, end_date, token: [
            {
                "stock_id": stock_code,
                "date": "2026-06-30",
                "type": "CashFlowsFromOperatingActivities",
                "value": "123.5",
                "origin_name": "營業活動之淨現金流入（流出）",
            }
        ],
    )

    output_dir = tmp_path / "out"
    exit_code = fetch_finmind_cashflow_candidate.main(
        [
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-06-30",
            "--output-dir",
            str(output_dir),
            "--stock-code",
            "2330",
            "--max-requests-per-hour",
            "0",
            "--fetch-date",
            "2026-09-08",
            "--observed-at",
            "2026-09-08T10:00:00+00:00",
        ]
    )

    assert exit_code == 0
    rows_path = output_dir / "finmind_cashflow_candidate_2026-09-08.csv"
    assert rows_path.exists()
    rows = list(csv.DictReader(rows_path.open(encoding="utf-8-sig")))
    assert rows[0]["stock_code"] == "2330"
    assert rows[0]["eligibility"] == "numeric_only"
    assert rows[0]["available_date_candidate"] == ""


def test_finmind_cashflow_cli_requires_explicit_resumable_bulk_opt_in(tmp_path) -> None:
    with pytest.raises(SystemExit, match="2"):
        fetch_finmind_cashflow_candidate.main(
            [
                "--start-date",
                "2026-01-01",
                "--end-date",
                "2026-06-30",
                "--raw-dir",
                str(tmp_path),
            ]
        )

    with pytest.raises(SystemExit, match="2"):
        fetch_finmind_cashflow_candidate.main(
            [
                "--start-date",
                "2026-01-01",
                "--end-date",
                "2026-06-30",
                "--raw-dir",
                str(tmp_path),
                "--all-raw-stock-codes",
            ]
        )
