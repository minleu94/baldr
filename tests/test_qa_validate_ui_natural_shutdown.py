from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import qa_validate_ui_natural_shutdown as natural_shutdown


def test_child_environment_pins_data_config_and_artifact_paths_to_run_dir(
    tmp_path: Path,
) -> None:
    inherited = {
        "DATA_ROOT": r"D:\production\data",
        "OUTPUT_ROOT": r"D:\production\output",
        "APPDATA": r"C:\Users\user\AppData\Roaming",
        "LOCALAPPDATA": r"C:\Users\user\AppData\Local",
        "RESEARCH_CONSOLE_PROJECTION": r"D:\production\projection.json",
        "FORMAL_DAILY_RUNTIME_ENVIRONMENT_FILE": r"D:\production\runtime.env",
    }

    environment = natural_shutdown.build_isolated_child_environment(
        tmp_path / "run",
        inherited,
    )
    run_root = (tmp_path / "run").resolve()

    assert environment["PROFILE"] == "test"
    assert environment["QT_QPA_PLATFORM"] == "offscreen"
    assert environment["PYTHONIOENCODING"] == "utf-8"
    for name in (
        "DATA_ROOT",
        "OUTPUT_ROOT",
        "APPDATA",
        "LOCALAPPDATA",
        "USERPROFILE",
        "TEMP",
        "TMP",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        natural_shutdown._POLICY_CONFIG_ENV,
        "FORMAL_DAILY_RUNTIME_CONFIG_ROOT",
        *natural_shutdown._ISOLATED_PATH_ENVIRONMENTS,
    ):
        assert Path(environment[name]).resolve().is_relative_to(run_root), name
    assert environment["DATA_ROOT"] != inherited["DATA_ROOT"]
    assert environment["OUTPUT_ROOT"] != inherited["OUTPUT_ROOT"]
    assert environment["APPDATA"] != inherited["APPDATA"]
    assert environment["RESEARCH_CONSOLE_PROJECTION"].endswith(
        "RESEARCH_CONSOLE_PROJECTION.missing"
    )


def _passing_receipt() -> dict[str, object]:
    return {
        "main_returned": True,
        "main_returncode": 0,
        "app_exec_returncode": 0,
        "window_shown": True,
        "close_requested": True,
        "close_event_accepted": True,
        "app_about_to_quit": True,
        "deferred_delete_drain_returned": True,
        "window_cpp_valid_after_drain": False,
        "watchdog_fired": False,
        "close_request_count": 1,
        "managed_workers_at_about_to_quit": 0,
        "update_background_process_at_about_to_quit": False,
        "all_config_paths_isolated": True,
    }


def test_natural_exit_gate_requires_actual_event_loop_and_os_exit() -> None:
    assert natural_shutdown.validate_natural_exit(
        child_returncode=0,
        timed_out=False,
        termination_requested=False,
        owned_descendants_naturally_exited=True,
        receipt=_passing_receipt(),
    ) == []

    errors = natural_shutdown.validate_natural_exit(
        child_returncode=0,
        timed_out=False,
        termination_requested=False,
        owned_descendants_naturally_exited=True,
        receipt={**_passing_receipt(), "app_exec_returncode": None},
    )

    assert "child_app_exec_returncode_not_zero:None" in errors


@pytest.mark.parametrize(
    ("changes", "expected_error"),
    [
        ({"close_event_accepted": False}, "close_event_not_accepted"),
        ({"deferred_delete_drain_returned": False}, "child_receipt_deferred_delete_drain_returned_not_true"),
        ({"window_cpp_valid_after_drain": True}, "window_cpp_object_not_confirmed_deleted_after_drain"),
        ({"watchdog_fired": True}, "child_watchdog_fired"),
    ],
)
def test_natural_exit_gate_rejects_incomplete_shutdown_evidence(
    changes: dict[str, object],
    expected_error: str,
) -> None:
    errors = natural_shutdown.validate_natural_exit(
        child_returncode=0,
        timed_out=False,
        termination_requested=False,
        owned_descendants_naturally_exited=True,
        receipt={**_passing_receipt(), **changes},
    )

    assert expected_error in errors


def test_natural_exit_gate_rejects_timeout_and_forced_cleanup() -> None:
    errors = natural_shutdown.validate_natural_exit(
        child_returncode=1,
        timed_out=True,
        termination_requested=True,
        owned_descendants_naturally_exited=False,
        receipt=_passing_receipt(),
    )

    assert "child_process_timeout" in errors
    assert "child_process_termination_was_requested" in errors
    assert "child_os_returncode_not_zero:1" in errors
    assert "owned_descendants_did_not_naturally_exit" in errors


def test_natural_exit_gate_requires_zero_workers_and_stopped_update_process() -> None:
    receipt = {
        **_passing_receipt(),
        "close_request_count": 2,
        "managed_workers_at_about_to_quit": None,
        "update_background_process_at_about_to_quit": None,
        "all_config_paths_isolated": False,
    }

    errors = natural_shutdown.validate_natural_exit(
        child_returncode=0,
        timed_out=False,
        termination_requested=False,
        owned_descendants_naturally_exited=True,
        receipt=receipt,
    )

    assert "close_request_count_not_one:2" in errors
    assert "managed_workers_remained_at_about_to_quit:None" in errors
    assert "update_background_process_not_confirmed_stopped_at_about_to_quit:None" in errors
    assert "config_paths_not_confirmed_isolated" in errors


@pytest.mark.parametrize(
    "scenario",
    ["slow_workbench_read", "slow_research_console_read"],
)
def test_slow_read_gate_rejects_blocked_heartbeat_and_close_delivery(
    scenario: str,
) -> None:
    receipt = {
        **_passing_receipt(),
        "scenario": scenario,
        "slow_read_call_count": 1,
        "slow_read_requested_ms": 500,
        "heartbeat_count": 20,
        "heartbeat_max_gap_ms": 512.0,
        "close_request_delay_ms": 450.0,
        "close_call_elapsed_ms": 300.0,
    }

    errors = natural_shutdown.validate_natural_exit(
        child_returncode=0,
        timed_out=False,
        termination_requested=False,
        owned_descendants_naturally_exited=True,
        receipt=receipt,
    )

    assert "ui_heartbeat_gap_exceeded:512.0ms" in errors
    assert "close_request_delivery_delayed:450.0ms" in errors
    assert "close_call_blocked:300.0ms" in errors


@pytest.mark.parametrize(
    "scenario",
    ["slow_workbench_read", "slow_research_console_read"],
)
def test_slow_read_scenarios_are_selectable_from_cli(scenario: str) -> None:
    args = natural_shutdown.parse_args(
        ["--scenario", scenario, "--timeout-seconds", "60"]
    )

    assert args.scenario == scenario


def test_heartbeat_measurement_includes_final_gap_before_quit() -> None:
    assert natural_shutdown._heartbeat_max_gap_ms([10.0, 10.01, 10.02], 10.22) == pytest.approx(
        200.0
    )


@pytest.mark.skipif(
    os.environ.get("BALDR_RUN_UI_NATURAL_SHUTDOWN_SUBPROCESS") != "1",
    reason="production MainWindow subprocess QA is opt-in; run its script explicitly",
)
def test_production_main_natural_shutdown_subprocess(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    output_root = tmp_path / "qa_output"
    result = subprocess.run(
        [
            sys.executable,
            "-u",
            str(project_root / "scripts" / "qa_validate_ui_natural_shutdown.py"),
            "--output-root",
            str(output_root),
            "--timeout-seconds",
            "90",
        ],
        cwd=project_root,
        check=False,
        timeout=120,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    run_dirs = list(output_root.glob("run_*"))
    assert len(run_dirs) == 1, result.stdout + result.stderr
    summary = json.loads((run_dirs[0] / "summary.json").read_text(encoding="utf-8"))
    assert result.returncode == 0, summary
    assert summary["status"] == "passed"
    assert summary["child_os_returncode"] == 0
    assert summary["child_receipt"]["app_exec_returncode"] == 0
    assert summary["owned_descendants_naturally_exited"] is True
