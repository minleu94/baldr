from __future__ import annotations

import json
import subprocess
import sys

from app_module.decision_desk_snapshot_repository import DecisionDeskSnapshotRepository
from app_module.evidence_event_importer_dtos import capture_context_is_valid
from data_module.config import TWStockConfig


def _config(tmp_path):
    config = TWStockConfig(data_root=tmp_path / "data", output_root=tmp_path / "output")
    config.db_file = tmp_path / "evidence.db"
    config.db_file.parent.mkdir(parents=True, exist_ok=True)
    return config


def _run(tmp_path, *args):
    config = _config(tmp_path)
    command = [
        sys.executable,
        "scripts/capture_decision_desk_snapshot.py",
        "--decision-date",
        "2026-06-30",
        "--db-path",
        str(config.db_file),
        "--data-root",
        str(config.data_root),
        "--output-root",
        str(config.output_root),
        "--json-output",
        *args,
    ]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(completed.stdout), config


def test_dry_run_does_not_write_snapshot(tmp_path):
    summary, config = _run(tmp_path, "--dry-run")

    assert summary["dry_run"] is True
    assert summary["saved"] is False
    assert DecisionDeskSnapshotRepository(config).list_snapshots() == []


def test_confirm_writes_snapshot_and_duplicate_is_skipped(tmp_path):
    first, config = _run(tmp_path, "--confirm")
    second, _ = _run(tmp_path, "--confirm")

    assert first["dry_run"] is False
    assert first["saved"] is True
    assert second["skipped_duplicate"] is True
    assert len(DecisionDeskSnapshotRepository(config).list_snapshots()) == 1


def test_explicit_capture_clock_is_persisted_without_preopen_authority(tmp_path):
    summary, config = _run(
        tmp_path,
        "--as-of",
        "2026-06-30",
        "--decision-at",
        "2026-06-30T20:10:00+08:00",
        "--captured-at",
        "2026-06-30T20:25:00+08:00",
        "--capture-mode",
        "eod_research",
        "--confirm",
    )

    stored = DecisionDeskSnapshotRepository(config).list_snapshots()[0]
    context = stored.metadata_json["capture_context"]
    assert summary["decision_at"] == "2026-06-30T20:10:00+08:00"
    assert summary["as_of"] == "2026-06-30"
    assert summary["captured_at"] == "2026-06-30T20:25:00+08:00"
    assert summary["capture_mode"] == "eod_research"
    assert summary["research_only"] is True
    assert summary["preopen_authority"] is False
    assert summary["natural_authority"] is False
    assert stored.metadata_json["generated_at"] == "2026-06-30T20:25:00+08:00"
    assert capture_context_is_valid(context)
    assert stored.hash_payload()["metadata_json"]["capture_context"] == {
        key: value
        for key, value in context.items()
        if key not in {"captured_at", "capture_context_hash", "capture_context_identity_hash"}
    }


def test_inspect_decision_desk_snapshots_cli_reports_latest(tmp_path):
    _, config = _run(tmp_path, "--confirm")
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/inspect_decision_desk_snapshots.py",
            "--db-path",
            str(config.db_file),
            "--json-output",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    summary = json.loads(completed.stdout)
    assert summary["snapshots_count"] == 1
    assert summary["latest_decision_date"] == "2026-06-30"


def test_snapshot_clis_do_not_import_ui_modules():
    for path in (
        "scripts/capture_decision_desk_snapshot.py",
        "scripts/inspect_decision_desk_snapshots.py",
    ):
        text = open(path, encoding="utf-8").read()
        assert "ui_qt" not in text
