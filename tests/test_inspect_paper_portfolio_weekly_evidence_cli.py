from __future__ import annotations

import json
from pathlib import Path

from scripts.inspect_paper_portfolio_weekly_evidence import main
from tests.test_paper_portfolio_weekly_evidence_service import _build_inputs


def test_cli_json_reports_read_only_weekly_evidence(tmp_path: Path, capsys) -> None:
    output_root, benchmark_db, cost_db = _build_inputs(tmp_path)
    state_db = output_root / "paper_portfolio" / "paper_portfolio.sqlite"
    code = main(
        [
            "--output-root",
            str(output_root),
            "--state-db",
            str(state_db),
            "--benchmark-db",
            str(benchmark_db),
            "--cost-ledger-db",
            str(cost_db),
            "--period-start",
            "2026-08-20",
            "--period-end",
            "2026-08-21",
            "--expected-trading-days",
            "2",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    assert payload["schema_version"] == "paper-portfolio-weekly-evidence.v2"
    assert payload["status"] == "degraded"
    assert payload["weekly_report_status"] == "not_computable"
    assert payload["report"] is None
    assert "paper_weekly_snapshot_cost_basis_unknown" in payload["blockers"]
    assert "paper_weekly_snapshot_ledger_window_unproven" in payload["blockers"]
    assert payload["observed_cost_disclosure_total"] == "1.10"
    assert payload["cost_disclosure_complete"] is False
    assert payload["writes_allowed"] is False


def test_cli_markdown_discloses_incomplete_week(tmp_path: Path, capsys) -> None:
    output_root, benchmark_db, cost_db = _build_inputs(tmp_path)
    code = main(
        [
            "--output-root",
            str(output_root),
            "--benchmark-db",
            str(benchmark_db),
            "--cost-ledger-db",
            str(cost_db),
            "--period-start",
            "2026-08-20",
            "--period-end",
            "2026-08-21",
            "--expected-trading-days",
            "5",
            "--format",
            "markdown",
        ]
    )

    output = capsys.readouterr().out
    assert code == 2
    assert "Paper Portfolio Weekly Evidence" in output
    assert "incomplete_trading_week" in output
    assert "paper_weekly_snapshot_cost_basis_unknown" in output
    assert "paper_weekly_snapshot_ledger_window_unproven" in output


def test_cli_returns_nonzero_when_inputs_are_missing(tmp_path: Path, capsys) -> None:
    code = main(
        [
            "--output-root",
            str(tmp_path / "output"),
            "--period-start",
            "2026-08-20",
            "--period-end",
            "2026-08-21",
            "--expected-trading-days",
            "2",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    assert payload["status"] == "not_configured"
    assert payload["report"] is None


def test_cli_rejects_invalid_period_without_touching_output(tmp_path: Path, capsys) -> None:
    output_root = tmp_path / "output"
    code = main(
        [
            "--output-root",
            str(output_root),
            "--period-start",
            "not-a-date",
            "--period-end",
            "2026-08-21",
            "--expected-trading-days",
            "2",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    assert payload["status"] == "rejected"
    assert not output_root.exists()
