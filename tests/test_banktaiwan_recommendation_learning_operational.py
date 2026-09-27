from __future__ import annotations

from argparse import Namespace
from datetime import date
import gc
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.scheduled import run_banktaiwan_recommendation_learning_daily as operational


def _fixture_args(tmp_path: Path, *, decision_date: str = "2026-09-15") -> Namespace:
    data_root = tmp_path / "formal-data"
    lane_root = tmp_path / "banktaiwan-shadow"
    snapshot_root = tmp_path / "formal-output"
    source_root = tmp_path / "legacy-shadow"
    source_db = data_root / "sqlite" / "twstock.db"
    source_db.parent.mkdir(parents=True)
    source_db.write_bytes(b"fixture-source-db")
    source_root.mkdir(parents=True)
    snapshot_runs = snapshot_root / "recommendation" / "runs"
    snapshot_runs.mkdir(parents=True)
    (snapshot_root / "scheduled" / "recommendation_snapshot").mkdir(parents=True)
    (snapshot_root / "scheduled" / "recommendation_snapshot" / "latest_status.json").write_text(
        json.dumps(
            {
                "schema_version": "scheduled-recommendation-snapshot.v1",
                "status": "passed",
                "decision_date": decision_date,
            }
        ),
        encoding="utf-8",
    )
    snapshot_payload = {
        "created_at": f"{decision_date}T05:10:00+08:00",
        "config": {
            "scheduled_snapshot": True,
            "decision_date": decision_date,
            "snapshot_cohort": {
                "cohort_hash": "sha256:fixture-cohort",
                "eligible_symbols": ["1101", "2330"],
            },
        },
        "recommendations": [],
    }
    (snapshot_runs / f"scheduled_{decision_date.replace('-', '')}.json").write_text(
        json.dumps(snapshot_payload, ensure_ascii=False),
        encoding="utf-8",
    )
    return operational.build_parser().parse_args(
        [
            "--data-root",
            str(data_root),
            "--output-root",
            str(lane_root),
            "--snapshot-output-root",
            str(snapshot_root),
            "--source-artifact-root",
            str(source_root),
            "--source-db",
            str(source_db),
            "--decision-date",
            decision_date,
            "--max-decision-dates",
            "5",
            "--research-order-quantity-shares",
            "1000",
        ]
    )


def _open_calendar(monkeypatch: pytest.MonkeyPatch, is_trading_day: bool = True) -> None:
    class _Calendar:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def is_official_trading_day(
            self,
            _target_date: date,
            *,
            allow_online_probe: bool,
        ) -> tuple[bool, str]:
            assert allow_online_probe is False
            return is_trading_day, "fixture_open" if is_trading_day else "weekend_closed"

    monkeypatch.setattr(operational, "OfficialTradingCalendar", _Calendar)


def _successful_child(
    _paths: operational.OperationalPaths,
    _decision_date: date,
    _scenario: object,
    _args: Namespace,
) -> dict[str, object]:
    return {
        "status": "completed_process",
        "returncode": 0,
        "command": ["fixture-child"],
        "stdout_stderr_tail": "fixture",
        "child_payload": {
            "run": {
                "decision": "retain_current",
                "decision_reason": "natural_forward_evidence_receipt_missing",
                "candidate_id": "rec-cal-fixture",
                "candidate_root": "fixture-candidate",
            },
            "dependencies": {"diagnostics": []},
            "live_capture": {"status": "captured", "reason": "fixture_capture"},
            "natural_evidence": {
                "status": "pending",
                "reason": "natural_forward_evidence_receipt_missing",
            },
            "active_pointer": {"status": "rule_only"},
            "challenger": {"status": "pending"},
            "formal_order_allowed": False,
            "shadow_only": True,
        },
    }


def test_operational_task_reuses_terminal_receipt_without_duplicate_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _fixture_args(tmp_path)
    _open_calendar(monkeypatch)
    calls: list[str] = []

    def child(*child_args: object) -> dict[str, object]:
        calls.append("called")
        return _successful_child(*child_args)  # type: ignore[arg-type]

    first_code, first = operational.run_once(args, child_runner=child)
    second_code, second = operational.run_once(args, child_runner=child)

    assert first_code == 0
    assert first["status"] == "completed_waiting_natural_maturity"
    assert second_code == 0
    assert second["idempotent_replay"] is True
    assert second["reused_run_id"] == first["run_id"]
    assert calls == ["called"]
    assert len(list((tmp_path / "banktaiwan-shadow" / "scheduled" / "recommendation_learning_banktaiwan" / "runs").glob("*.json"))) == 1


def test_operational_task_retries_failed_attempt_with_new_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _fixture_args(tmp_path)
    _open_calendar(monkeypatch)
    attempts = 0

    def child(*child_args: object) -> dict[str, object]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return {
                "status": "completed_process",
                "returncode": 2,
                "command": ["fixture-child"],
                "child_payload": {},
            }
        return _successful_child(*child_args)  # type: ignore[arg-type]

    first_code, first = operational.run_once(args, child_runner=child)
    second_code, second = operational.run_once(args, child_runner=child)

    assert first_code == 2
    assert first["status"] == "failed_dependency"
    assert first["recoverable"] is True
    assert second_code == 0
    assert second["status"] == "completed_waiting_natural_maturity"
    assert second["attempt_number"] == 2
    assert attempts == 2
    runs = tmp_path / "banktaiwan-shadow" / "scheduled" / "recommendation_learning_banktaiwan" / "runs"
    assert len(list(runs.glob("*.json"))) == 2


def test_operational_task_blocks_overlap_and_skips_non_trading_day(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _fixture_args(tmp_path / "overlap")
    _open_calendar(monkeypatch)
    paths = operational.resolve_operational_paths(
        data_root=args.data_root,
        lane_output_root=args.output_root,
        snapshot_output_root=args.snapshot_output_root,
        source_artifact_root=args.source_artifact_root,
        source_db=args.source_db,
    )
    lock = operational.OperationalRunLock(paths.lock_path)
    lock.acquire()
    try:
        code, payload = operational.run_once(args, child_runner=_successful_child)
    finally:
        lock.release()
    assert code == 0
    assert payload["status"] == "skipped_overlap"

    non_trading_args = _fixture_args(tmp_path / "closed")
    _open_calendar(monkeypatch, is_trading_day=False)
    monkeypatch.setattr(
        operational,
        "load_same_day_snapshot",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("closed day must not inspect snapshot")
        ),
    )
    code, payload = operational.run_once(non_trading_args, child_runner=_successful_child)
    assert code == 0
    assert payload["status"] == "skipped_non_trading_day"
    assert payload["child_invocation"] == "not_required_non_trading_day"
    assert payload["snapshot"]["status"] == "not_applicable"
    assert payload["snapshot"]["reason"] == "not_applicable_non_trading_day"
    assert payload["formal_order_allowed"] is False


def test_operational_command_keeps_source_and_lane_boundaries_and_cost_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _fixture_args(tmp_path)
    _open_calendar(monkeypatch)
    paths, decision_date, scenario = operational._common_args(args)
    command = operational._child_command(
        paths=paths,
        decision_date=decision_date,
        scenario=scenario,
        args=args,
    )
    joined = " ".join(command)
    assert "run_daily_recommendation_learning.py" in joined
    assert "--cost-scenario banktaiwan_estimated_research" in joined
    assert "--snapshot-output-root" in command
    assert "--source-artifact-root" in command
    assert "--research-order-quantity-shares" in command
    assert scenario.research_order_quantity_shares == 1000
    assert paths.lane_output_root != paths.source_artifact_root
    assert paths.lane_learning_root.is_relative_to(paths.lane_output_root)


def test_registration_wrapper_is_dedicated_and_has_no_aggregate_side_effect() -> None:
    path = Path(__file__).resolve().parents[1] / "scripts" / "scheduled" / "register_banktaiwan_recommendation_learning_task.cmd"
    text = path.read_text(encoding="utf-8")
    assert "baldr-recommendation-calibration-learning-banktaiwan-shadow-daily" in text
    assert "set \"TASK_TIME=05:50\"" in text
    assert "MultipleInstances IgnoreNew" in text
    assert "register_baldr_scheduled_tasks" not in text
    assert "/Create" in text and "/Change" in text


def test_windows_pid_probe_uses_query_api_without_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    if os.name != "nt":
        pytest.skip("Windows-specific process query contract")
    called = False

    def forbidden_signal(*_args: object) -> None:
        nonlocal called
        called = True
        raise AssertionError("Windows lock probe must not call os.kill")

    monkeypatch.setattr(operational.os, "kill", forbidden_signal)
    assert operational._windows_process_state(os.getpid()) == "running"
    assert operational._process_state(os.getpid()) == "running"
    assert called is False


@pytest.mark.parametrize("metadata", [{"pid": "malformed"}, {"pid": 999999999}])
def test_unknown_or_access_denied_pid_keeps_lock_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    metadata: dict[str, object],
) -> None:
    lock_path = tmp_path / "run.lock"
    lock_path.write_text(json.dumps(metadata), encoding="utf-8")
    monkeypatch.setattr(operational, "_windows_process_state", lambda _pid: "unknown")

    lock = operational.OperationalRunLock(lock_path)
    with pytest.raises(operational.OperationalOverlapError):
        lock.acquire()
    assert lock_path.read_text(encoding="utf-8") == json.dumps(metadata)


def test_only_explicitly_dead_pid_lock_is_reclaimed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_path = tmp_path / "run.lock"
    lock_path.write_text(json.dumps({"pid": 12345, "token": "stale"}), encoding="utf-8")
    monkeypatch.setattr(operational, "_windows_process_state", lambda _pid: "dead")

    lock = operational.OperationalRunLock(lock_path)
    lock.acquire()
    try:
        current = json.loads(lock_path.read_text(encoding="utf-8"))
        assert current["token"] == lock.token
    finally:
        lock.release()
    assert not lock_path.exists()


def test_naturally_ended_windows_pid_is_detected_as_dead_and_reclaimed(
    tmp_path: Path,
) -> None:
    if os.name != "nt":
        pytest.skip("Windows-specific process query contract")
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    pid = process.pid
    assert process.wait(timeout=10) == 0
    process = None  # type: ignore[assignment]
    gc.collect()

    assert operational._windows_process_state(pid) == "dead"
    lock_path = tmp_path / "run.lock"
    lock_path.write_text(json.dumps({"pid": pid, "token": "stale"}), encoding="utf-8")
    lock = operational.OperationalRunLock(lock_path)
    lock.acquire()
    try:
        current = json.loads(lock_path.read_text(encoding="utf-8"))
        assert current["token"] == lock.token
    finally:
        lock.release()
