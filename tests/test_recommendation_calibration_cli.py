from __future__ import annotations

import json

from scripts.inspect_recommendation_calibration import main


def test_recommendation_calibration_cli_sample_json(capsys) -> None:
    assert main(["--sample", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "measured_research_only"
    assert payload["access_boundary"]["writes_allowed"] is False
    assert payload["dataset_manifest"]["production_eligible"] is False
    assert payload["contract"]["primary_target"]["horizon_days"] == 20

