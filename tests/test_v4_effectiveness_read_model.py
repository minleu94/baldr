from __future__ import annotations

import json
from pathlib import Path

from app_module.v4_effectiveness_read_model import V4EffectivenessReadModel
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
