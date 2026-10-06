from __future__ import annotations

import csv
from datetime import date
import json

import pytest

from data_module.finmind_cashflow_candidate import (
    FINMIND_CASHFLOW_SOURCE,
    harvest_finmind_cashflow_candidate,
)


def test_harvest_normalizes_quarter_and_preserves_numeric_only_boundary(tmp_path) -> None:
    responses = {
        "2330": [
            {
                "stock_id": "2330",
                "date": "2026-06-30",
                "type": "CashFlowsFromOperatingActivities",
                "value": 123456789.0,
                "origin_name": "營業活動之淨現金流入（流出）",
            },
            {
                "stock_id": "2330",
                "date": "2026-06-30",
                "type": "CashFlowsFromInvestingActivities",
                "value": 0,
                "origin_name": "投資活動之淨現金流入（流出）",
            },
            {
                "stock_id": "3207",
                "date": "2026-06-30",
                "type": "WrongStock",
                "value": 1,
            },
            {"stock_id": "2330", "date": "bad", "type": "Bad", "value": 1},
        ]
    }

    def fake_fetch(stock_code: str, start: str, end: str, token: str) -> list[dict]:
        assert (stock_code, start, end, token) == ("2330", "2026-01-01", "2026-06-30", "secret")
        return responses[stock_code]

    result = harvest_finmind_cashflow_candidate(
        stock_codes=("2330",),
        start_date="2026-01-01",
        end_date="2026-06-30",
        token="secret",
        fetch_rows=fake_fetch,
        output_dir=tmp_path,
        fetch_date=date(2026, 9, 8),
        observed_at="2026-09-08T10:00:00+00:00",
    )

    assert len(result.rows) == 2
    assert result.rows[0]["period"] == "2026-Q2"
    assert result.rows[0]["source"] == FINMIND_CASHFLOW_SOURCE
    assert result.rows[0]["eligibility"] == "numeric_only"
    assert result.rows[0]["available_date_candidate"] == ""
    assert next(row for row in result.rows if row["item_code"].endswith("InvestingActivities"))["value"] == "0"
    assert result.rows[0]["source_row_hash"].startswith("sha256:")
    assert result.rejected_row_count == 2
    assert result.rejection_reasons == (("invalid_date", 1), ("stock_code_mismatch", 1))
    assert "secret" not in result.to_markdown()

    rows = list(csv.DictReader((tmp_path / "finmind_cashflow_candidate_2026-09-08.csv").open(encoding="utf-8-sig")))
    assert rows[0]["observed_at"] == "2026-09-08T10:00:00+00:00"


def test_harvest_resume_skips_completed_stock_and_writes_state(tmp_path) -> None:
    state_file = tmp_path / "state.json"
    state_file.write_text(
        json.dumps({"completed_stock_codes": ["2330"], "failed_stock_codes": []}),
        encoding="utf-8",
    )
    fetched: list[str] = []

    def fake_fetch(stock_code: str, start: str, end: str, token: str) -> list[dict]:
        fetched.append(stock_code)
        return []

    result = harvest_finmind_cashflow_candidate(
        stock_codes=("2330", "3207"),
        start_date="2026-01-01",
        end_date="2026-06-30",
        token="secret",
        fetch_rows=fake_fetch,
        output_dir=tmp_path,
        state_file=state_file,
        resume=True,
        fetch_date=date(2026, 9, 8),
        observed_at="2026-09-08T10:00:00+00:00",
    )

    assert fetched == ["3207"]
    assert result.requested_stock_count == 2
    assert result.fetched_stock_count == 1
    assert result.state["completed_stock_codes"] == ["2330", "3207"]


def test_harvest_rejects_observed_at_without_timezone() -> None:
    with pytest.raises(ValueError, match="explicit timezone"):
        harvest_finmind_cashflow_candidate(
            stock_codes=("2330",),
            start_date="2026-01-01",
            end_date="2026-06-30",
            token="secret",
            fetch_rows=lambda *_args: [],
            observed_at="2026-09-08T10:00:00",
        )
