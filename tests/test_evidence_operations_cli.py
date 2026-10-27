from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from app_module.decision_quality_dtos import DecisionQualityItem, DecisionQualityReview
from app_module.decision_quality_repository import DecisionQualityRepository
from app_module.evidence_weekly_approval_input import build_weekly_approval_input
from app_module.evidence_weekly_review_decision import write_weekly_review_decision_artifact
from data_module.config import TWStockConfig
from runtime.sqlite_file_set_fingerprint import (
    SQLITE_FILE_SET_FINGERPRINT_METHOD,
    fingerprint_sqlite_file_set,
)
from scripts import build_evidence_operations_weekly_review as weekly_review_script
from scripts import smoke_evidence_pipeline_working_copy as smoke_script
from scripts import export_evidence_review_dashboard_snapshot as dashboard_script


def _write_weekly_decision_fixture(tmp_path: Path) -> tuple[Path, Path]:
    sidecar_path = tmp_path / "weekly-sidecar.sqlite"
    coverage = {
        "status": "degraded",
        "trading_day_count": 2,
        "observed_row_count": 3,
        "duplicate_symbol_rows": 0,
        "quality_findings": ["required_price_values_missing"],
        "incomplete_row_count": 1,
        "integrity_examples": [],
        "integrity_examples_truncated": False,
    }
    with sqlite3.connect(sidecar_path) as connection:
        connection.execute(
            """
            CREATE TABLE evidence_weekly_collections (
                collection_id TEXT PRIMARY KEY, period_start TEXT NOT NULL,
                period_end TEXT NOT NULL, source_path TEXT NOT NULL,
                source_hash TEXT NOT NULL, status TEXT NOT NULL,
                payload_json TEXT NOT NULL, error_type TEXT NOT NULL DEFAULT '',
                error_message TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO evidence_weekly_collections (
                collection_id, period_start, period_end, source_path, source_hash,
                status, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ewc-cli-1", "2026-10-19", "2026-10-25", str(tmp_path / "source.json"),
                "sha256:" + "a" * 64, "pending_human_review",
                json.dumps({
                    "last_trading_date": "2026-10-22",
                    "human_approval_required": True,
                    "source_coverage": coverage,
                }),
                "2026-10-26T12:00:00+00:00",
            ),
        )
    packet = build_weekly_approval_input(
        sidecar_path, owner_role="portfolio_owner", reviewer_role="independent_reviewer"
    )
    artifact_path = tmp_path / "decision.json"
    write_weekly_review_decision_artifact(
        packet,
        sidecar_path,
        collection_id="ewc-cli-1",
        owner_name="Owner Example",
        owner_role="portfolio_owner",
        reviewer_name="Reviewer Example",
        reviewer_role="independent_reviewer",
        decision="follow_up",
        note="本週須跟進未解資料缺口。",
        output_path=artifact_path,
        reviewed_at="2026-10-26T12:30:00+08:00",
    )
    return sidecar_path, artifact_path


def test_runbook_producers_share_sqlite_file_set_fingerprint(tmp_path: Path) -> None:
    db_path = tmp_path / "shared-working-copy.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE fixture(value TEXT)")
    Path(str(db_path) + "-wal").write_bytes(b"fixture wal sidecar")

    shared = fingerprint_sqlite_file_set(db_path)
    smoke = smoke_script.fingerprint_sqlite_file_set(db_path)
    weekly = weekly_review_script._sqlite_file_set_fingerprint(db_path)
    dashboard = dashboard_script._fingerprint_sqlite_file_set(db_path)

    assert shared["method"] == SQLITE_FILE_SET_FINGERPRINT_METHOD
    assert smoke == shared
    assert weekly == dashboard == shared["sha256"]


def test_weekly_receipt_rejects_missing_lifecycle_apply_action(tmp_path: Path) -> None:
    db_path = tmp_path / "working-copy.sqlite"
    db_path.write_bytes(b"synthetic db identity")
    payload = {
        "start_date": "2026-10-19",
        "end_date": "2026-10-25",
        "write_performed": False,
        "manual_approval": {"production_scheduler_allowed": False},
        "signal_decay": {"demote_candidate_count": 1, "retire_candidate_count": 0},
        "manual_lifecycle_candidates": [{"suggested_lifecycle_action": "demote"}],
    }

    with pytest.raises(ValueError, match="safety assertions failed"):
        weekly_review_script._write_runbook_receipt(
            tmp_path / "must-not-exist.json",
            payload,
            start_date="2026-10-19",
            end_date="2026-10-25",
            db_path=db_path,
            fingerprint_before="sha256:stable",
            fingerprint_after="sha256:stable",
        )

    assert not (tmp_path / "must-not-exist.json").exists()


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
    assert payload["decision_quality"]["reviews_count"] == 0
    assert payload["decision_quality"]["warnings_count"] >= 1
    assert payload["signal_decay"]["status_counts"] == {"unknown": 1}
    assert not db_path.exists()


def test_weekly_review_cli_writes_self_describing_dry_run_receipt_exclusively(tmp_path: Path) -> None:
    db_path = tmp_path / "working-copy.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE fixture(value TEXT)")
    sqlite_files = [Path(f"{db_path}{suffix}") for suffix in ("", "-journal", "-wal", "-shm")]
    file_set_before = {
        path.name: path.read_bytes() if path.exists() else None
        for path in sqlite_files
    }
    data_root = tmp_path / "data"
    output_root = tmp_path / "output"
    receipt_path = tmp_path / "weekly-review-receipt.json"
    completed = subprocess.run(
        [
            sys.executable, "-B", "scripts/build_evidence_operations_weekly_review.py",
            "--start-date", "2026-10-19", "--end-date", "2026-10-25",
            "--db-path", str(db_path), "--data-root", str(data_root),
            "--output-root", str(output_root), "--receipt-output", str(receipt_path),
            "--json-output",
        ],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert {
        path.name: path.read_bytes() if path.exists() else None
        for path in sqlite_files
    } == file_set_before
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["schema_version"] == "baldr-weekly-runbook-artifact.v1"
    assert receipt["artifact_role"] == "weekly_review_report"
    assert receipt["period_start"] == "2026-10-19"
    assert receipt["period_end"] == receipt["decision_date"] == "2026-10-25"
    identity = receipt["database_identity"]
    assert identity["role"] == "working_copy"
    assert identity["fingerprint_method"] == SQLITE_FILE_SET_FINGERPRINT_METHOD
    assert identity["stable"] is True
    assert identity["fingerprint_before"] == identity["fingerprint_after"]
    assert identity["fingerprint_before"].startswith("sha256:")
    assert receipt["report_payload"]["action_item_plan"]["dry_run"] is True
    assert receipt["report_payload"]["decision_quality"]["reviews_count"] == 0
    assert receipt["report_payload"]["decision_quality"]["warnings_count"] >= 1
    assert receipt["report_payload"]["signal_decay"]["status_counts"] == {"unknown": 1}
    assert receipt["report_payload"]["warnings"] is not None
    assert all(receipt["safety_flags_verified"].values())
    assert receipt["safety_flags_verified"]["lifecycle_apply_action_all_false"] is True
    assert receipt["safety_flags_verified"]["report_period_matches_receipt"] is True
    assert receipt["production_scheduler_allowed"] is False
    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert tables == {"fixture"}

    original = receipt_path.read_bytes()
    repeated = subprocess.run(
        [
            sys.executable, "-B", "scripts/build_evidence_operations_weekly_review.py",
            "--start-date", "2026-10-19", "--end-date", "2026-10-25",
            "--db-path", str(db_path), "--data-root", str(data_root),
            "--output-root", str(output_root), "--receipt-output", str(receipt_path),
        ],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert repeated.returncode == 2
    assert receipt_path.read_bytes() == original


def test_weekly_review_cli_rejects_dry_run_receipt_with_write_request(tmp_path: Path) -> None:
    db_path = tmp_path / "working-copy.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE fixture(value TEXT)")
    data_root = tmp_path / "data"
    output_root = tmp_path / "output"
    receipt_path = tmp_path / "must-not-exist.json"
    completed = subprocess.run(
        [
            sys.executable, "-B", "scripts/build_evidence_operations_weekly_review.py",
            "--start-date", "2026-10-19", "--end-date", "2026-10-25",
            "--db-path", str(db_path), "--data-root", str(data_root),
            "--output-root", str(output_root), "--receipt-output", str(receipt_path),
            "--save-history",
        ],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert completed.returncode == 2
    assert "dry-run only" in completed.stderr
    assert not receipt_path.exists()


def test_weekly_review_cli_rejects_receipt_with_markdown_output_without_writing(tmp_path: Path) -> None:
    db_path = tmp_path / "working-copy.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE fixture(value TEXT)")
    data_root = tmp_path / "data"
    output_root = tmp_path / "output"
    receipt_path = tmp_path / "must-not-exist.json"
    markdown_path = tmp_path / "must-not-exist.md"
    completed = subprocess.run(
        [
            sys.executable, "-B", "scripts/build_evidence_operations_weekly_review.py",
            "--start-date", "2026-10-19", "--end-date", "2026-10-25",
            "--db-path", str(db_path), "--data-root", str(data_root),
            "--output-root", str(output_root), "--receipt-output", str(receipt_path),
            "--markdown-output", str(markdown_path),
        ],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert completed.returncode == 2
    assert "markdown-output" in completed.stderr
    assert not receipt_path.exists()
    assert not markdown_path.exists()


def test_weekly_review_cli_action_item_plan_dry_run_does_not_write(tmp_path: Path) -> None:
    db_path = tmp_path / "evidence-ops-cli.db"
    data_root = tmp_path / "data"
    output_root = tmp_path / "output"

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
            str(data_root),
            "--output-root",
            str(output_root),
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
    assert not db_path.exists()


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


def test_weekly_review_cli_embeds_valid_candidate_decision_in_saved_history(tmp_path: Path) -> None:
    sidecar_path, artifact_path = _write_weekly_decision_fixture(tmp_path)
    db_path = tmp_path / "approved-working-copy.sqlite"
    completed = subprocess.run(
        [
            sys.executable, "-B", "scripts/build_evidence_operations_weekly_review.py",
            "--start-date", "2026-10-19", "--end-date", "2026-10-25",
            "--db-path", str(db_path), "--data-root", str(tmp_path / "data"),
            "--output-root", str(tmp_path / "output"), "--save-history",
            "--candidate-review-artifact", str(artifact_path),
            "--candidate-review-sidecar-path", str(sidecar_path), "--json-output",
        ],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    decision = payload["history_record"]["payload_json"]["candidate_review_decision"]
    assert decision["decision"] == "follow_up"
    assert decision["source"]["collection_id"] == "ewc-cli-1"
    assert decision["source"]["sidecar_sha256"].startswith("sha256:")
    assert decision["artifact_sha256"].startswith("sha256:")
    assert decision["candidate_only"] is True
    assert decision["formal_credit_authorized"] is False
    assert decision["production_scheduler_allowed"] is False
    assert payload["history_record"]["production_scheduler_allowed"] is False


def test_weekly_review_cli_refuses_candidate_bridge_with_action_item_confirmation(
    tmp_path: Path,
) -> None:
    sidecar_path, artifact_path = _write_weekly_decision_fixture(tmp_path)
    db_path = tmp_path / "must-not-write.sqlite"
    completed = subprocess.run(
        [
            sys.executable, "-B", "scripts/build_evidence_operations_weekly_review.py",
            "--start-date", "2026-10-19", "--end-date", "2026-10-25",
            "--db-path", str(db_path), "--data-root", str(tmp_path / "data"),
            "--output-root", str(tmp_path / "output"), "--save-history",
            "--confirm-action-items", "--candidate-review-artifact", str(artifact_path),
            "--candidate-review-sidecar-path", str(sidecar_path),
        ],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )

    assert completed.returncode == 2
    assert "cannot be combined with action-item confirmation" in completed.stderr
    assert not db_path.exists()


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
