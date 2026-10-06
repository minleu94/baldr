from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

from app_module.decision_quality_dtos import DecisionQualityItem, DecisionQualityReview
from app_module.decision_quality_repository import DecisionQualityRepository
from data_module.config import TWStockConfig


def test_weekly_review_cli_outputs_json_without_enabling_scheduler(tmp_path: Path) -> None:
    config = TWStockConfig(data_root=tmp_path / "data", output_root=tmp_path / "output")
    db_path = tmp_path / "evidence-ops-cli.db"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_evidence_operations_weekly_review.py",
            "--start-date",
            "2026-06-24",
            "--end-date",
            "2026-06-30",
            "--db-path",
            str(db_path),
            "--data-root",
            str(config.data_root),
            "--output-root",
            str(config.output_root),
            "--json-output",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["manual_approval"]["production_scheduler_allowed"] is False
    assert payload["status"] in {"coverage_only", "needs_manual_review", "ready_for_weekly_closeout"}
    assert payload["write_performed"] is False


def test_weekly_review_cli_action_item_plan_dry_run_does_not_write(tmp_path: Path) -> None:
    db_path = tmp_path / "evidence-ops-cli.db"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_evidence_operations_weekly_review.py",
            "--start-date",
            "2026-06-24",
            "--end-date",
            "2026-06-30",
            "--db-path",
            str(db_path),
            "--plan-action-items",
            "--json-output",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["action_item_plan"]["dry_run"] is True
    assert payload["action_item_plan"]["action_items_created"] == 0
    assert payload["write_performed"] is False


def test_weekly_review_cli_save_history_and_list_history(tmp_path: Path) -> None:
    db_path = tmp_path / "evidence-ops-cli.db"

    saved = subprocess.run(
        [
            sys.executable,
            "scripts/build_evidence_operations_weekly_review.py",
            "--start-date",
            "2026-07-06",
            "--end-date",
            "2026-07-12",
            "--db-path",
            str(db_path),
            "--save-history",
            "--json-output",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert saved.returncode == 0, saved.stderr
    saved_payload = json.loads(saved.stdout)
    assert saved_payload["history_record"]["period_end"] == "2026-07-12"
    assert saved_payload["history_record"]["production_scheduler_allowed"] is False
    assert saved_payload["write_performed"] is True

    listed = subprocess.run(
        [
            sys.executable,
            "scripts/build_evidence_operations_weekly_review.py",
            "--start-date",
            "2026-07-06",
            "--end-date",
            "2026-07-12",
            "--db-path",
            str(db_path),
            "--list-history",
            "--json-output",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert listed.returncode == 0, listed.stderr
    listed_payload = json.loads(listed.stdout)
    assert len(listed_payload["history_records"]) == 1
    assert listed_payload["history_records"][0]["period_start"] == "2026-07-06"
    assert listed_payload["history_records"][0]["payload_json"]["status"] == saved_payload["status"]


def test_list_history_missing_database_is_diagnostic_and_never_creates_it(tmp_path: Path) -> None:
    db_path = tmp_path / "missing" / "history.db"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_evidence_operations_weekly_review.py",
            "--start-date",
            "2026-07-06",
            "--end-date",
            "2026-07-12",
            "--db-path",
            str(db_path),
            "--list-history",
            "--json-output",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["history_records"] == []
    assert payload["diagnostics"] == ["evidence_operations_history_db_missing"]
    assert payload["write_performed"] is False
    assert not db_path.exists()
    assert not db_path.parent.exists()


def test_list_history_data_root_override_does_not_create_db_parent_or_logs(tmp_path: Path) -> None:
    qa_data_root = tmp_path / "qa-data"
    qa_output_root = tmp_path / "qa-output"
    expected_db_path = qa_data_root / "sqlite" / "twstock.db"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_evidence_operations_weekly_review.py",
            "--start-date",
            "2026-07-06",
            "--end-date",
            "2026-07-12",
            "--data-root",
            str(qa_data_root),
            "--output-root",
            str(qa_output_root),
            "--list-history",
            "--json-output",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["diagnostics"] == ["evidence_operations_history_db_missing"]
    assert not expected_db_path.exists()
    assert not expected_db_path.parent.exists()
    assert not (qa_data_root / "logs").exists()
    assert not qa_data_root.exists()
    assert not qa_output_root.exists()


def test_list_history_missing_table_is_diagnostic_and_does_not_create_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "history-without-table.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE unrelated_table (value TEXT NOT NULL)")

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_evidence_operations_weekly_review.py",
            "--start-date",
            "2026-07-06",
            "--end-date",
            "2026-07-12",
            "--db-path",
            str(db_path),
            "--list-history",
            "--json-output",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["history_records"] == []
    assert payload["diagnostics"] == ["evidence_operations_history_table_missing"]
    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        indexes = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")
        }
    assert tables == {"unrelated_table"}
    assert indexes == set()


def test_confirmed_action_owner_is_persisted_and_traceable_in_history_snapshot(tmp_path: Path) -> None:
    db_path = tmp_path / "evidence-ops-cli.db"
    config = TWStockConfig(data_root=tmp_path / "data", output_root=tmp_path / "output")
    config.db_file = db_path
    repository = DecisionQualityRepository(config)
    repository.save_review(
        DecisionQualityReview(
            review_id="dqr-weekly",
            review_hash="sha256:dqr-weekly",
            review_period_start="2026-07-06",
            review_period_end="2026-07-12",
            review_type="weekly",
            review_status="needs_review",
        ),
        items=[
            DecisionQualityItem(
                item_id="dqi-weekly",
                review_id="dqr-weekly",
                item_type="trade_without_source_trace",
                status="open",
            )
        ],
    )

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_evidence_operations_weekly_review.py",
            "--start-date",
            "2026-07-06",
            "--end-date",
            "2026-07-12",
            "--db-path",
            str(db_path),
            "--confirm-action-items",
            "--save-history",
            "--action-owner",
            "weekly-reviewer",
            "--json-output",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["action_item_plan"]["action_items_created"] == 1
    assert payload["history_record"]["payload_json"]["action_owner"] == "weekly-reviewer"
    assert payload["history_record"]["payload_json"]["action_item_plan"]["planned_action_items"][0]["owner"] == "weekly-reviewer"
    assert repository.list_action_items(review_id="dqr-weekly")[0].owner == "weekly-reviewer"


def test_production_like_db_is_rejected_without_escape_hatch(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    production_like_db = data_root / "sqlite" / "twstock.db"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_evidence_operations_weekly_review.py",
            "--start-date",
            "2026-07-06",
            "--end-date",
            "2026-07-12",
            "--data-root",
            str(data_root),
            "--db-path",
            str(production_like_db),
            "--save-history",
            "--json-output",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert completed.returncode == 2
    assert "production-like DB" in completed.stderr
    assert not production_like_db.exists()

    help_output = subprocess.run(
        [sys.executable, "scripts/build_evidence_operations_weekly_review.py", "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert help_output.returncode == 0
    assert "--allow-production-like-db" not in help_output.stdout


def test_data_root_override_cannot_bypass_configured_production_db_guard(tmp_path: Path) -> None:
    configured_production_root = tmp_path / "configured-production"
    overridden_qa_root = tmp_path / "overridden-qa"
    production_like_db = configured_production_root / "sqlite" / "twstock.db"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_evidence_operations_weekly_review.py",
            "--start-date",
            "2026-07-06",
            "--end-date",
            "2026-07-12",
            "--data-root",
            str(overridden_qa_root),
            "--db-path",
            str(production_like_db),
            "--save-history",
            "--json-output",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={
            **os.environ,
            "DATA_ROOT": str(configured_production_root),
            "OUTPUT_ROOT": str(tmp_path / "output"),
            "PYTHONIOENCODING": "utf-8",
        },
        check=False,
    )

    assert completed.returncode == 2
    assert "production-like DB" in completed.stderr
    assert not production_like_db.exists()


def test_personal_weekly_history_cli_saves_and_lists_selected_store(tmp_path: Path) -> None:
    working_copy = tmp_path / "approved-synthetic-working.sqlite"
    with sqlite3.connect(working_copy) as conn:
        conn.execute("CREATE TABLE synthetic_source(value TEXT)")
        conn.execute("INSERT INTO synthetic_source VALUES ('unchanged')")
    before = working_copy.read_bytes()
    private = tmp_path / "private"
    args = [sys.executable, "-B", "scripts/build_evidence_operations_weekly_review.py",
        "--start-date", "2026-07-06", "--end-date", "2026-07-12", "--db-path", str(working_copy),
        "--data-root", str(tmp_path / "data"), "--output-root", str(tmp_path / "output"),
        "--personal-store-root", str(private), "--personal-store-mode", "personal", "--json-output"]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    for field in ("PERSONAL_STORE_ROOT", "PERSONAL_STORE_MODE", "DATA_ROOT", "OUTPUT_ROOT"):
        env.pop(field, None)
    saved = subprocess.run([*args, "--save-history"], capture_output=True, text=True, encoding="utf-8", env=env)
    assert saved.returncode == 0, saved.stderr
    payload = json.loads(saved.stdout)
    assert payload["source_lineage"]["review_store_path"] == str(private / "reviews" / "decision_quality.sqlite")
    assert payload["source_lineage"]["market_source_db"] == str(working_copy)
    assert payload["source_lineage"]["source_snapshot_qualification"] == "unknown"
    private_before = (private / "reviews" / "decision_quality.sqlite").read_bytes()
    listed = subprocess.run([*args, "--list-history"], capture_output=True, text=True, encoding="utf-8", env=env)
    assert listed.returncode == 0, listed.stderr
    records = json.loads(listed.stdout)["history_records"]
    assert len(records) == 1 and records[0]["review_hash"] == payload["history_record"]["review_hash"]
    assert records[0]["payload_json"]["source_lineage"] == payload["source_lineage"]
    assert working_copy.read_bytes() == before
    assert (private / "reviews" / "decision_quality.sqlite").read_bytes() == private_before


def test_personal_list_history_empty_is_side_effect_free_and_blank_root_rejected(tmp_path: Path) -> None:
    private = tmp_path / "private"
    args = [sys.executable, "-B", "scripts/build_evidence_operations_weekly_review.py",
        "--start-date", "2026-07-06", "--end-date", "2026-07-12", "--db-path", str(tmp_path / "source.sqlite"),
        "--data-root", str(tmp_path / "data"), "--personal-store-mode", "personal", "--list-history", "--json-output"]
    env = {**os.environ, "PERSONAL_STORE_ROOT": str(private), "PYTHONIOENCODING": "utf-8"}
    empty = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", env=env)
    assert empty.returncode == 0, empty.stderr
    payload = json.loads(empty.stdout)
    assert payload["history_records"] == [] and not payload["write_performed"]
    assert not private.exists() and not (tmp_path / "data").exists()
    blank = subprocess.run([*args, "--personal-store-root", ""], capture_output=True, text=True, encoding="utf-8", env=env)
    assert blank.returncode != 0
    assert not private.exists() and not (tmp_path / "data").exists()
