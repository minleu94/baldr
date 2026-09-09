from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from app_module.v4_effectiveness_read_model import (
    V4EffectivenessReadModel,
    load_v4_effectiveness_rows_from_evidence_db,
)
from data_module.evidence_event_migration import apply_evidence_event_schema
from scripts.inspect_v4_effectiveness import main


def _row(day: str, outcome: str, status: str = "ready") -> dict[str, object]:
    return {
        "decision_date": day,
        "outcome_id": outcome,
        "horizon_days": 5,
        "strategy_version": "rule-v4",
        "universe_id": "twse-liquid",
        "cost_model": "paper-v1",
        "benchmark_id": "twse-ew",
        "status": status,
        "score_bp": 9000,
        "return_bp": 100,
    }


def test_read_model_keeps_strict_cohort_and_boundary() -> None:
    report = V4EffectivenessReadModel(
        k=1,
        minimum_decision_days=2,
        minimum_mature_outcomes=2,
    ).build_report(
        rows=(
            _row("2026-09-01", "a"),
            _row("2026-09-02", "b"),
            _row("2026-09-03", "pending", "pending"),
        )
    )

    payload = report.to_dict()
    assert payload["access_boundary"]["read_only"] is True
    assert payload["access_boundary"]["production_scheduler_allowed"] is False
    assert payload["slices"][0]["mature_outcome_count"] == 2
    assert payload["slices"][0]["pending_outcome_count"] == 1


def test_v4_cli_reads_json_object_and_writes_markdown(tmp_path: Path) -> None:
    input_path = tmp_path / "evidence.json"
    output_path = tmp_path / "report.md"
    input_path.write_text(
        json.dumps({"rows": [_row("2026-09-01", "a")]}, ensure_ascii=False),
        encoding="utf-8",
    )

    assert main(
        [
            "--input",
            str(input_path),
            "--format",
            "markdown",
            "--output",
            str(output_path),
            "--minimum-decision-days",
            "1",
            "--minimum-mature-outcomes",
            "1",
        ]
    ) == 0
    text = output_path.read_text(encoding="utf-8")
    assert "V4 Effectiveness Evidence" in text
    assert "rule-v4" in text


def _write_evidence_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        apply_evidence_event_schema(conn)
        for index, decision_date in enumerate(("2026-09-01", "2026-09-02"), start=1):
            event_id = f"event-{index}"
            conn.execute(
                """
                INSERT INTO evidence_events (
                    event_id, event_hash, event_date, decision_date, symbol,
                    event_type, event_family, source_type, strategy_version_id,
                    score_bp, data_quality, as_of_date, available_date,
                    cost_model_id, benchmark_id, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    f"hash-{index}",
                    decision_date,
                    decision_date,
                    f"23{index:02d}",
                    "recommendation_included",
                    "recommendation",
                    "paper",
                    "rule-v4",
                    9000 - index,
                    "observed",
                    decision_date,
                    decision_date,
                    "paper-v1",
                    "twse-ew",
                    json.dumps({"universe_id": "twse-liquid"}),
                ),
            )
            conn.execute(
                """
                INSERT INTO evidence_outcomes (
                    outcome_id, event_id, window_days, forward_return_bp,
                    benchmark_excess_bp, industry_excess_bp, outcome_status,
                    data_quality
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (f"outcome-{index}", event_id, 5, 100, 20, 10, "ready", "observed"),
            )


def test_read_model_reads_evidence_sqlite_without_writing(tmp_path: Path) -> None:
    db_path = tmp_path / "evidence.sqlite"
    _write_evidence_db(db_path)
    before = db_path.read_bytes()

    report = V4EffectivenessReadModel(
        k=1,
        minimum_decision_days=2,
        minimum_mature_outcomes=2,
    ).build_report_from_evidence_db(db_path=db_path)

    assert db_path.read_bytes() == before
    assert report.slices[0].mature_outcome_count == 2
    assert report.slices[0].decision_day_count == 2
    assert report.slices[0].evaluation_status == "ready_for_manual_review"
    assert "evidence_rows_missing_universe_id" not in report.warnings


def test_evidence_db_loader_is_explicit_about_missing_db_and_filters(tmp_path: Path) -> None:
    missing = tmp_path / "missing.sqlite"
    rows, warnings = load_v4_effectiveness_rows_from_evidence_db(missing)
    assert rows == []
    assert warnings == ("evidence_db_missing",)
    assert not missing.exists()

    db_path = tmp_path / "evidence.sqlite"
    _write_evidence_db(db_path)
    rows, warnings = load_v4_effectiveness_rows_from_evidence_db(
        db_path,
        decision_date="2026-09-02",
        window_days=5,
        limit=1,
    )
    assert len(rows) == 1
    assert rows[0]["decision_date"] == "2026-09-02"
    assert rows[0]["universe_id"] == "twse-liquid"
    assert warnings == ()


def test_v4_cli_reads_evidence_db(tmp_path: Path) -> None:
    db_path = tmp_path / "evidence.sqlite"
    output_path = tmp_path / "report.json"
    _write_evidence_db(db_path)

    assert main(
        [
            "--db-path",
            str(db_path),
            "--format",
            "json",
            "--output",
            str(output_path),
            "--minimum-decision-days",
            "1",
            "--minimum-mature-outcomes",
            "1",
        ]
    ) == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["slices"][0]["mature_outcome_count"] == 2
    assert payload["access_boundary"]["production_scheduler_allowed"] is False
