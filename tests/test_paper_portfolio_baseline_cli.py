from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


def test_cli_reads_saved_recommendation_and_writes_research_artifact(tmp_path: Path) -> None:
    source = tmp_path / "recommendation.json"
    output = tmp_path / "paper_baseline.json"
    source.write_text(
        json.dumps(
            {
                "result_id": "scheduled_rec_20260712_051002",
                "created_at": "2026-07-12T05:10:02",
                "recommendations": [
                    {"證券代號": "2330", "證券名稱": "台積電", "收盤價": "1000", "總分": "65.00", "產業": "半導體"}
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_paper_portfolio_baseline.py",
            "--recommendation-json",
            str(source),
            "--output",
            str(output),
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["source_result_id"] == "scheduled_rec_20260712_051002"
    assert payload["research_only"] is True
    assert payload["writes_positions_db"] is False
    assert payload["broker_order_allowed"] is False
    assert json.loads(completed.stdout)["output_path"] == str(output.resolve())


@pytest.mark.parametrize("preexisting_output", [False, True])
def test_cli_rejects_unknown_candidate_value_without_writing_output(
    tmp_path: Path,
    preexisting_output: bool,
) -> None:
    source = tmp_path / "recommendation.json"
    output = tmp_path / "new" / "paper_baseline.json"
    output.parent.mkdir()
    original_output = b"preserve existing artifact\n"
    if preexisting_output:
        output.write_bytes(original_output)
    source.write_text(
        json.dumps(
            {
                "result_id": "missing-score",
                "created_at": "2026-07-12T05:10:02",
                "recommendations": [
                    {"證券代號": "2330", "證券名稱": "台積電", "收盤價": "1000", "總分": None}
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_paper_portfolio_baseline.py",
            "--recommendation-json",
            str(source),
            "--output",
            str(output),
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert completed.returncode != 0
    assert "總分" in completed.stderr
    if preexisting_output:
        assert output.read_bytes() == original_output
    else:
        assert not output.exists()
