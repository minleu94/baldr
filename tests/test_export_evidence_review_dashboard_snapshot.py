from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

import scripts.export_evidence_review_dashboard_snapshot as exporter


def _config(root: Path) -> SimpleNamespace:
    data_root = root / "formal-data-root"
    return SimpleNamespace(
        data_root=data_root,
        db_file=data_root / "sqlite" / "twstock.db",
        output_root=root / "output",
    )


def _create_history_db(path: Path, *, include_table: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        if not include_table:
            connection.execute("CREATE TABLE unrelated (value TEXT)")
            return
        connection.execute(
            """
            CREATE TABLE evidence_operations_weekly_reviews (
                review_id TEXT PRIMARY KEY,
                review_hash TEXT NOT NULL UNIQUE,
                period_start TEXT NOT NULL,
                period_end TEXT NOT NULL,
                review_status TEXT NOT NULL,
                scheduler_readiness TEXT NOT NULL,
                production_scheduler_allowed INTEGER NOT NULL DEFAULT 0,
                decision_quality_reviews_count INTEGER NOT NULL DEFAULT 0,
                signal_decay_observations_count INTEGER NOT NULL DEFAULT 0,
                manual_lifecycle_candidate_count INTEGER NOT NULL DEFAULT 0,
                warnings_count INTEGER NOT NULL DEFAULT 0,
                generated_by TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO evidence_operations_weekly_reviews (
                review_id, review_hash, period_start, period_end, review_status,
                scheduler_readiness, production_scheduler_allowed,
                decision_quality_reviews_count, signal_decay_observations_count,
                manual_lifecycle_candidate_count, warnings_count, generated_by,
                payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    f"review-{day}",
                    f"sha256:{day * 64}",
                    f"2026-10-{day}",
                    f"2026-10-{day}",
                    "needs_manual_review",
                    "not_ready",
                    0,
                    2,
                    1,
                    0,
                    3,
                    "synthetic-test",
                    '{"synthetic":true}',
                    f"2026-10-{day}T18:00:00+08:00",
                )
                for day in (1, 2, 3)
            ],
        )


def _database_bytes(path: Path) -> bytes:
    return path.read_bytes()


def test_exports_one_pinned_page_and_exposes_next_cursor(tmp_path: Path) -> None:
    db_path = tmp_path / "review-working-copy.sqlite"
    output_path = tmp_path / "snapshot.json"
    _create_history_db(db_path)
    before = _database_bytes(db_path)

    envelope = exporter.build_snapshot(
        db_path=db_path,
        output_path=output_path,
        period_start="2026-10-01",
        period_end="2026-10-31",
        limit=2,
        config=_config(tmp_path),
    )

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    payload = saved["payload"]
    assert envelope == saved
    assert saved["schema_version"] == "baldr-weekly-runbook-artifact.v1"
    assert saved["artifact_role"] == "evidence_review_dashboard"
    assert saved["period_start"] == "2026-10-01"
    assert saved["period_end"] == "2026-10-31"
    assert saved["database_identity"]["role"] == "review_store"
    assert saved["database_identity"]["fingerprint_method"] == "sha256_sqlite_file_set.v1"
    assert saved["database_identity"]["stable_during_read"] is True
    assert saved["database_identity"]["fingerprint_before"] == saved["database_identity"]["fingerprint_after"]
    assert saved["safety"]["write_performed"] is False
    assert saved["safety"]["formal_credit_authorized"] is False
    assert saved["safety"]["production_scheduler_allowed"] is False
    assert payload["dashboard_verified"] is True
    assert payload["weekly_period_bound"] is True
    assert payload["pagination_complete"] is False
    assert payload["has_more_rows"] is True
    assert payload["next_cursor"]["review_id"] == "review-2"
    assert [row["review_id"] for row in payload["rows"]] == ["review-3", "review-2"]
    assert all(row["review_hash"].startswith("sha256:") for row in payload["rows"])
    assert payload["cards"]["reviews_count"] == 2
    assert payload["cards"]["warnings_count"] == 6
    assert _database_bytes(db_path) == before


def test_missing_history_table_is_diagnostic_not_verified_dashboard(tmp_path: Path) -> None:
    db_path = tmp_path / "review-working-copy.sqlite"
    output_path = tmp_path / "diagnostic.json"
    _create_history_db(db_path, include_table=False)
    before = _database_bytes(db_path)

    envelope = exporter.build_snapshot(
        db_path=db_path,
        output_path=output_path,
        config=_config(tmp_path),
    )

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert envelope == saved
    assert saved["payload"]["source_available"] is False
    assert saved["payload"]["dashboard_verified"] is False
    assert saved["payload"]["rows"] == []
    assert "evidence_operations_history_table_missing" in " ".join(saved["diagnostics"])
    assert saved["database_identity"]["stable_during_read"] is True
    assert _database_bytes(db_path) == before
    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert tables == {"unrelated"}


def test_successful_dashboard_without_explicit_week_period_is_not_runbook_verified(tmp_path: Path) -> None:
    db_path = tmp_path / "review-working-copy.sqlite"
    output_path = tmp_path / "unbounded-dashboard.json"
    _create_history_db(db_path)

    envelope = exporter.build_snapshot(
        db_path=db_path,
        output_path=output_path,
        config=_config(tmp_path),
    )

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert envelope == saved
    assert saved["payload"]["source_available"] is True
    assert saved["payload"]["dashboard_verified"] is False
    assert saved["payload"]["weekly_period_bound"] is False
    assert "dashboard_weekly_period_unbound" in saved["diagnostics"]


def test_output_uses_exclusive_create_and_preserves_existing_file(tmp_path: Path) -> None:
    db_path = tmp_path / "review-working-copy.sqlite"
    output_path = tmp_path / "snapshot.json"
    _create_history_db(db_path)
    original = "existing artifact\n"
    output_path.write_text(original, encoding="utf-8")

    with pytest.raises(FileExistsError):
        exporter.build_snapshot(
            db_path=db_path,
            output_path=output_path,
            config=_config(tmp_path),
        )

    assert output_path.read_text(encoding="utf-8") == original


def test_formal_db_path_is_rejected_before_fingerprinting(tmp_path: Path) -> None:
    config = _config(tmp_path)
    formal_path = config.db_file
    formal_path.parent.mkdir(parents=True, exist_ok=True)
    formal_path.write_bytes(b"synthetic formal-path sentinel")
    before = _database_bytes(formal_path)
    output_path = tmp_path / "formal-path-diagnostic.json"

    envelope = exporter.build_snapshot(
        db_path=formal_path,
        output_path=output_path,
        config=config,
    )

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert envelope == saved
    assert saved["payload"]["dashboard_verified"] is False
    assert saved["database_identity"]["fingerprint_before"] is None
    assert saved["database_identity"]["fingerprint_after"] is None
    assert "weekly_review_formal_db_forbidden" in " ".join(saved["diagnostics"])
    assert _database_bytes(formal_path) == before
