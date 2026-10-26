from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from app_module.approved_weekly_history_projection import SCHEMA_VERSION
from scripts.rehearse_weekly_review_recovery import run_rehearsal


def _source_db(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """CREATE TABLE evidence_operations_weekly_reviews (
                review_id TEXT PRIMARY KEY,
                review_hash TEXT NOT NULL,
                period_start TEXT NOT NULL,
                period_end TEXT NOT NULL
            )"""
        )
        connection.execute(
            "INSERT INTO evidence_operations_weekly_reviews VALUES (?,?,?,?)",
            ("fixture-review-1", "sha256:" + "a" * 64, "2026-10-19", "2026-10-25"),
        )


def _projection(path: Path, *, formal_credit: bool = False) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "formal_credit_authorized": formal_credit,
                "records": [],
            }
        ),
        encoding="utf-8",
    )


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_rehearsal_restores_scratch_copies_and_preserves_sources(tmp_path: Path) -> None:
    source_db = tmp_path / "working-copy.sqlite"
    source_projection = tmp_path / "approval.json"
    scratch = tmp_path / "scratch" / "run-1"
    scratch.parent.mkdir()
    _source_db(source_db)
    _projection(source_projection)
    db_before = _digest(source_db)
    projection_before = _digest(source_projection)

    result = run_rehearsal(
        source_db_path=source_db,
        source_projection_path=source_projection,
        scratch_root=scratch,
        data_root=tmp_path / "formal-data",
        output_root=tmp_path / "formal-output",
    )

    assert result["passed"] is True
    assert result["engineering_only"] is True
    assert result["formal_credit_authorized"] is False
    assert result["task_scheduler_api_called"] is False
    assert result["source_files_unchanged"] is True
    assert result["source_db_sha256_before"] == result["source_db_sha256_after"] == db_before
    assert result["source_projection_sha256_before"] == result["source_projection_sha256_after"] == projection_before
    assert result["recovery"]["database"]["quick_check_after"] == "ok"
    assert result["recovery"]["database"]["restored"] is True
    assert result["recovery"]["database"]["weekly_review_identity_after"]["record_count"] == 1
    assert result["recovery"]["approval_projection"]["restored"] is True
    assert json.loads((scratch / "scheduler-state.simulated.json").read_text()) == {
        "enabled": False,
        "simulation_only": True,
    }
    assert json.loads((scratch / "recovery-rehearsal.json").read_text())["passed"] is True


def test_rehearsal_rejects_formal_database_path_before_creating_scratch(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    formal_db = data_root / "sqlite" / "twstock.db"
    formal_db.parent.mkdir(parents=True)
    _source_db(formal_db)
    source_projection = tmp_path / "approval.json"
    _projection(source_projection)
    scratch = tmp_path / "scratch"

    with pytest.raises(ValueError, match="weekly_review_formal_db_forbidden"):
        run_rehearsal(
            source_db_path=formal_db,
            source_projection_path=source_projection,
            scratch_root=scratch,
            data_root=data_root,
            output_root=tmp_path / "output",
        )

    assert not scratch.exists()


def test_rehearsal_rejects_nonempty_wal_and_projection_credit_flag(tmp_path: Path) -> None:
    source_db = tmp_path / "working-copy.sqlite"
    source_projection = tmp_path / "approval.json"
    _source_db(source_db)
    _projection(source_projection)
    Path(str(source_db) + "-wal").write_bytes(b"pending WAL state")

    with pytest.raises(ValueError, match="source_db_has_nonempty_wal"):
        run_rehearsal(
            source_db_path=source_db,
            source_projection_path=source_projection,
            scratch_root=tmp_path / "scratch-wal",
            data_root=tmp_path / "formal-data",
            output_root=tmp_path / "formal-output",
        )

    Path(str(source_db) + "-wal").unlink()
    Path(str(source_db) + "-journal").write_bytes(b"pending rollback journal")
    with pytest.raises(ValueError, match="source_db_has_nonempty_journal"):
        run_rehearsal(
            source_db_path=source_db,
            source_projection_path=source_projection,
            scratch_root=tmp_path / "scratch-journal",
            data_root=tmp_path / "formal-data",
            output_root=tmp_path / "formal-output",
        )

    Path(str(source_db) + "-journal").unlink()
    _projection(source_projection, formal_credit=True)
    with pytest.raises(ValueError, match="must_not_authorize_formal_credit"):
        run_rehearsal(
            source_db_path=source_db,
            source_projection_path=source_projection,
            scratch_root=tmp_path / "scratch-credit",
            data_root=tmp_path / "formal-data",
            output_root=tmp_path / "formal-output",
        )
