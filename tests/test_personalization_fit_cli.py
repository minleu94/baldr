from __future__ import annotations

import json
from pathlib import Path

from scripts.run_personalization_fit import main


def test_fit_cli_fails_closed_for_missing_real_sources(tmp_path: Path, capsys: object) -> None:
    output_path = tmp_path / "fit.json"
    exit_code = main(
        [
            "--scope-id",
            "scope_missing",
            "--fit-as-of",
            "2025-01-31",
            "--evaluated-as-of",
            "2025-04-01",
            "--evaluation-cutoff-at",
            "2025-04-01T23:59:00+00:00",
            "--output-path",
            str(output_path),
            "--output-root",
            str(tmp_path / "missing-output"),
            "--evidence-db",
            str(tmp_path / "missing.sqlite"),
        ]
    )

    captured = capsys.readouterr()  # type: ignore[attr-defined]
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert payload["status"] == "blocked"
    assert payload["blocked_reason"] == "read_source_failed"
    assert not output_path.exists()
