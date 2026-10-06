from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from scripts.experiments.r027.observation_clock import R027ObservationClock
from scripts.experiments.r027.run_experiment import (
    collect_exact_differences,
    flatten_comparable,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _run_clock_subprocess() -> dict[str, object]:
    source = "\n".join(
        (
            "import json, os",
            "from scripts.experiments.r027.observation_clock import R027ObservationClock",
            "clock = R027ObservationClock(mode='deterministic', case='clean')",
            "stamps = [clock.stamp('calculate_start'), clock.stamp('publish_end')]",
            "print(json.dumps({'pid': os.getpid(), 'stamps': stamps, 'receipt': clock.receipt()}, sort_keys=True))",
        )
    )
    env = dict(os.environ)
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(REPOSITORY_ROOT)
        if not existing_pythonpath
        else str(REPOSITORY_ROOT) + os.pathsep + existing_pythonpath
    )
    completed = subprocess.run(
        [sys.executable, "-c", source],
        cwd=REPOSITORY_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)
    assert isinstance(result, dict)
    return result


def test_deterministic_observer_clock_matches_across_independent_processes() -> None:
    first = _run_clock_subprocess()
    second = _run_clock_subprocess()

    assert first["pid"] != second["pid"]
    assert first["stamps"] == second["stamps"]
    first_receipt = first["receipt"]
    second_receipt = second["receipt"]
    assert isinstance(first_receipt, dict)
    assert isinstance(second_receipt, dict)
    assert first_receipt["schedule_sha256"] == second_receipt["schedule_sha256"]
    assert first_receipt["call_sequence"] == second_receipt["call_sequence"]
    assert first_receipt["call_count"] == second_receipt["call_count"] == 2
    assert first_receipt["raw_os_observation_count"] == 2
    assert second_receipt["raw_os_observation_count"] == 2
    assert first_receipt["all_raw_os_observations_present"] is True
    assert second_receipt["all_raw_os_observations_present"] is True
    for receipt in (first_receipt, second_receipt):
        observations = receipt["raw_os_observations"]
        assert isinstance(observations, list)
        assert [item["sequence"] for item in observations] == [0, 1]
        assert all(item["raw_os_wall_time_utc"] for item in observations)
        assert all(isinstance(item["raw_os_perf_counter_ns"], int) for item in observations)


def test_extra_clock_call_and_changed_publication_phase_are_exact_differences() -> None:
    clock = R027ObservationClock(mode="deterministic", case="clean")
    first_stamp = clock.stamp("publication_start")
    base_receipt = {
        "events": [{"seq": 0, "kind": "publication_start", **first_stamp}],
        "phases": [
            {
                "label": "clean_publication",
                "publication_paths": ["data/test.csv"],
                "files": {"data/test.csv": {"sha256": "sha256:abc", "size_bytes": 3}},
                "technical_rows": {"row_count": 1},
                "source_mutated": False,
                "result": {"success": True},
            }
        ],
        "final_outputs": {
            "publication_paths": ["data/test.csv"],
            "files": {"data/test.csv": {"sha256": "sha256:abc", "size_bytes": 3}},
            "technical_rows": {"row_count": 1},
        },
        "direct_checkpoint_fixtures": {"same_identity_resume_accepted": True},
        "observation_clock": clock.receipt(),
    }
    second_receipt = json.loads(json.dumps(base_receipt))
    second_clock = R027ObservationClock(mode="deterministic", case="clean")
    second_clock.stamp("publication_start")
    second_stamp = second_clock.stamp("extra_observer_call")
    second_receipt["events"].append(
        {"seq": 1, "kind": "extra_observer_call", **second_stamp}
    )
    second_receipt["observation_clock"] = second_clock.receipt()

    clock_differences = collect_exact_differences(
        flatten_comparable(base_receipt),
        flatten_comparable(second_receipt),
    )
    assert any("call_count" in item.get("path", "") for item in clock_differences)
    assert any("call_sequence" in item.get("path", "") for item in clock_differences)

    phase_receipt = json.loads(json.dumps(base_receipt))
    phase_receipt["phases"][0]["label"] = "different_publication_phase"
    phase_differences = collect_exact_differences(
        flatten_comparable(base_receipt),
        flatten_comparable(phase_receipt),
    )
    assert any("phases[0].label" in item.get("path", "") for item in phase_differences)
