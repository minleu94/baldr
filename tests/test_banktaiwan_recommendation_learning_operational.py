from __future__ import annotations

from argparse import Namespace
from dataclasses import replace
from datetime import date, datetime
import gc
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from app_module.recommendation.contracts import RecommendationResultConfigSnapshot
from app_module.recommendation.persistence import RecommendationExecutionPersistence
from app_module.saved_recommendation_queries import build_recommendation_execution_queries
from data_module.result_artifact_store import ResultArtifactStore
from scripts.scheduled import run_banktaiwan_recommendation_learning_daily as operational


def _write_snapshot_invocation(
    snapshot_root: Path,
    *,
    decision_date: str,
    result_id: str,
    cohort: dict[str, object],
    run_id: str,
) -> tuple[Path, str, int]:
    payload = {
        "task": "baldr-recommendation-snapshot-daily",
        "status": "passed",
        "decision_date": decision_date,
        "output_root": str(snapshot_root.resolve()),
        "result_id": result_id,
        "snapshot_cohort": cohort,
    }
    raw = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    pipeline_runs_root = (
        snapshot_root
        / "scheduled"
        / "recommendation_calibration_learning"
        / "runs"
    )
    invocation_dir = pipeline_runs_root / run_id
    invocation_dir.mkdir(parents=True, exist_ok=False)
    invocation_path = invocation_dir / "recommendation_snapshot.stdout.bin"
    with invocation_path.open("xb") as stream:
        stream.write(raw)
    invocation_hash = "sha256:" + hashlib.sha256(raw).hexdigest()
    pipeline_status = {
        "schema_version": "daily-recommendation-learning-pipeline.v1",
        "task": "baldr-recommendation-calibration-learning-daily",
        "status": "passed",
        "run_id": run_id,
        "decision_date": decision_date,
        "output_root": str(snapshot_root.resolve()),
        "steps": {
            "recommendation_snapshot": {
                "name": "recommendation_snapshot",
                "returncode": 0,
                "status": "passed",
                "child_status": payload,
                "child_status_source": "invocation_stdout_json",
                "child_stdout_artifact_path": str(invocation_path.resolve()),
                "child_stdout_artifact_size": len(raw),
                "child_stdout_sha256": invocation_hash,
                "child_receipt_error": None,
            }
        },
    }
    pipeline_latest_status = (
        snapshot_root
        / "scheduled"
        / "recommendation_calibration_learning"
        / "latest_status.json"
    )
    pipeline_latest_status.parent.mkdir(parents=True, exist_ok=True)
    pipeline_latest_status.write_text(
        json.dumps(pipeline_status, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return invocation_path, invocation_hash, len(raw)


def _write_canonical_snapshot(snapshot_root: Path, *, decision_date: str) -> dict[str, object]:
    helper_path = Path(__file__).with_name("test_c1_forward_consumer_readiness.py")
    spec = importlib.util.spec_from_file_location(
        "bank_operational_canonical_execution_fixture", helper_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("無法載入 canonical execution 測試 fixture")
    fixture_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture_module)
    fixture, _manifest_entry = fixture_module._fixture()
    execution = fixture_module._execution(fixture)

    context = execution.context
    original_result_config = context.result_config_snapshot
    assert original_result_config is not None
    result_config = json.loads(original_result_config.raw_result_config_json)
    result_config["scheduled_snapshot"] = True
    result_config["decision_date"] = decision_date
    result_config["as_of_date"] = context.as_of_date.isoformat()
    result_config["data_as_of_date"] = context.as_of_date.isoformat()
    result_config_text = json.dumps(
        result_config,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    result_config_snapshot = RecommendationResultConfigSnapshot(
        raw_result_config_json=result_config_text,
        config_sha256="sha256:" + hashlib.sha256(result_config_text.encode("utf-8")).hexdigest(),
    )
    result_id = f"bank-snapshot-{decision_date.replace('-', '')}"
    decision_at = datetime.fromisoformat(f"{decision_date}T05:10:06+08:00")
    execution = replace(
        execution,
        result_id=result_id,
        context=replace(
            context,
            created_at=datetime.fromisoformat(f"{decision_date}T05:09:00+08:00"),
            available_at=datetime.fromisoformat(f"{decision_date}T05:09:30+08:00"),
            decision_at=decision_at,
            result_config_snapshot=result_config_snapshot,
        ),
    )

    runs_dir = snapshot_root / "recommendation" / "runs"
    store = ResultArtifactStore(
        artifact_root=runs_dir / "execution_artifacts",
        database_path=runs_dir / "recommendation_runs.db",
    )
    RecommendationExecutionPersistence(store).save(
        execution,
        label="隔離合成 scheduled recommendation snapshot",
        notes="只供 Bank canonical reader 測試使用",
        now=lambda: datetime.fromisoformat(f"{decision_date}T04:00:00+00:00"),
    )
    read_model = build_recommendation_execution_queries(
        None,
        runs_dir=runs_dir,
    ).get(result_id)
    assert read_model is not None
    assert read_model.result_id == result_id
    assert read_model.integrity_basis == "canonical_payload_and_index_verified"
    assert read_model.execution is not None
    assert read_model.execution.context.result_config_snapshot is not None
    cohort = json.loads(
        read_model.execution.context.result_config_snapshot.raw_result_config_json
    )["snapshot_cohort"]
    snapshot_latest_status = {
        "schema_version": "scheduled-recommendation-snapshot.v1",
        "task": "baldr-recommendation-snapshot-daily",
        "status": "passed",
        "decision_date": decision_date,
        "result_id": result_id,
        "output_root": str(snapshot_root.resolve()),
        "snapshot_cohort": cohort,
    }
    snapshot_status_path = (
        snapshot_root / "scheduled" / "recommendation_snapshot" / "latest_status.json"
    )
    snapshot_status_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_status_path.write_text(
        json.dumps(snapshot_latest_status, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    run_id = f"{decision_date.replace('-', '')}-fixture"
    invocation_path, invocation_hash, invocation_size = _write_snapshot_invocation(
        snapshot_root,
        decision_date=decision_date,
        result_id=result_id,
        cohort=cohort,
        run_id=run_id,
    )
    return {
        "result_id": result_id,
        "cohort": cohort,
        "run_id": run_id,
        "invocation_path": invocation_path,
        "invocation_sha256": invocation_hash,
        "invocation_size": invocation_size,
        "decision_at": decision_at.isoformat(),
    }


def _fixture_args(tmp_path: Path, *, decision_date: str = "2026-09-22") -> Namespace:
    data_root = tmp_path / "formal-data"
    lane_root = tmp_path / "banktaiwan-shadow"
    snapshot_root = tmp_path / "formal-output"
    source_root = tmp_path / "legacy-shadow"
    source_db = data_root / "sqlite" / "twstock.db"
    source_db.parent.mkdir(parents=True)
    source_db.write_bytes(b"fixture-source-db")
    source_root.mkdir(parents=True)
    _write_canonical_snapshot(snapshot_root, decision_date=decision_date)
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


def _rewrite_snapshot_result_id(snapshot_root: Path, result_id: str) -> None:
    snapshot_status_path = (
        snapshot_root / "scheduled" / "recommendation_snapshot" / "latest_status.json"
    )
    snapshot_status = json.loads(snapshot_status_path.read_text(encoding="utf-8"))
    snapshot_status["result_id"] = result_id
    snapshot_status_path.write_text(
        json.dumps(snapshot_status, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    pipeline_status_path = (
        snapshot_root
        / "scheduled"
        / "recommendation_calibration_learning"
        / "latest_status.json"
    )
    pipeline_status = json.loads(pipeline_status_path.read_text(encoding="utf-8"))
    snapshot_step = pipeline_status["steps"]["recommendation_snapshot"]
    invocation_path = Path(snapshot_step["child_stdout_artifact_path"])
    invocation_payload = json.loads(invocation_path.read_bytes())
    invocation_payload["result_id"] = result_id
    raw = json.dumps(
        invocation_payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")
    invocation_path.write_bytes(raw)
    invocation_hash = "sha256:" + hashlib.sha256(raw).hexdigest()
    snapshot_step["child_status"]["result_id"] = result_id
    snapshot_step["child_stdout_artifact_size"] = len(raw)
    snapshot_step["child_stdout_sha256"] = invocation_hash
    pipeline_status_path.write_text(
        json.dumps(pipeline_status, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_legacy_snapshot_decoy(snapshot_root: Path, *, decision_date: str) -> Path:
    path = snapshot_root / "recommendation" / "runs" / "legacy_same_day_decoy.json"
    path.write_text(
        json.dumps(
            {
                "created_at": f"{decision_date}T05:10:00+08:00",
                "config": {
                    "scheduled_snapshot": True,
                    "decision_date": decision_date,
                    "snapshot_cohort": {
                        "cohort_hash": "sha256:legacy-decoy",
                        "eligible_symbols": ["1101", "2330"],
                    },
                },
                "recommendations": [{"stock_code": "2330"}],
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


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
    snapshot = first["snapshot"]
    assert snapshot["file_sha256"] == "sha256:" + hashlib.sha256(
        Path(snapshot["path"]).read_bytes()
    ).hexdigest()
    assert snapshot["file_sha256"] == snapshot["invocation_output_sha256"]
    assert snapshot["canonical_artifact_sha256"].startswith("sha256:")


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
    snapshot, reason = operational.load_same_day_snapshot(
        output_root=paths.snapshot_output_root,
        decision_date=decision_date,
    )
    assert snapshot is not None, reason
    command = operational._child_command(
        paths=paths,
        decision_date=decision_date,
        scenario=scenario,
        args=args,
        snapshot=snapshot,
    )
    joined = " ".join(command)
    assert "run_daily_recommendation_learning.py" in joined
    assert "--cost-scenario banktaiwan_estimated_research" in joined
    assert "--snapshot-output-root" in command
    assert "--source-artifact-root" in command
    assert "--research-order-quantity-shares" in command
    assert command[command.index("--snapshot-result-id") + 1] == snapshot.result_id
    assert command[command.index("--snapshot-cohort-hash") + 1] == snapshot.cohort_hash
    assert (
        command[command.index("--snapshot-invocation-output-sha256") + 1]
        == snapshot.invocation_output_sha256
    )
    assert (
        Path(command[command.index("--snapshot-invocation-output-path") + 1])
        == snapshot.invocation_output_path
    )
    assert scenario.research_order_quantity_shares == 1000
    assert paths.lane_output_root != paths.source_artifact_root
    assert paths.lane_learning_root.is_relative_to(paths.lane_output_root)


def test_same_day_reader_uses_canonical_result_not_legacy_json_decoys(
    tmp_path: Path,
) -> None:
    args = _fixture_args(tmp_path)
    decoy_path = _write_legacy_snapshot_decoy(
        args.snapshot_output_root,
        decision_date=args.decision_date,
    )

    snapshot, reason = operational.load_same_day_snapshot(
        output_root=args.snapshot_output_root,
        decision_date=date.fromisoformat(args.decision_date),
    )

    assert snapshot is not None, reason
    assert snapshot.result_id == "bank-snapshot-20260922"
    assert snapshot.integrity_basis == "canonical_payload_and_index_verified"
    assert snapshot.symbols == ("AAA", "BET")
    assert snapshot.path == snapshot.invocation_output_path
    assert snapshot.file_sha256 == snapshot.invocation_output_sha256
    assert snapshot.canonical_artifact_sha256 != snapshot.file_sha256
    assert decoy_path.is_file()
    assert snapshot.path != decoy_path


@pytest.mark.parametrize(
    ("status_kind", "relative_path"),
    [
        ("snapshot", Path("scheduled/recommendation_snapshot/latest_status.json")),
        (
            "pipeline",
            Path(
                "scheduled/recommendation_calibration_learning/latest_status.json"
            ),
        ),
    ],
)
def test_same_day_reader_rejects_oversized_status_files(
    tmp_path: Path,
    status_kind: str,
    relative_path: Path,
) -> None:
    args = _fixture_args(tmp_path)
    status_path = args.snapshot_output_root / relative_path
    status_payload = json.loads(status_path.read_text(encoding="utf-8"))
    status_payload["test_padding"] = "x" * operational._MAX_SNAPSHOT_STATUS_BYTES
    status_path.write_text(
        json.dumps(status_payload, ensure_ascii=False),
        encoding="utf-8",
    )

    snapshot, reason = operational.load_same_day_snapshot(
        output_root=args.snapshot_output_root,
        decision_date=date.fromisoformat(args.decision_date),
    )

    assert snapshot is None
    assert reason == f"recommendation_{status_kind}_status_unreadable_or_unsafe"


@pytest.mark.parametrize(
    ("status_kind", "relative_path"),
    [
        ("snapshot", Path("scheduled/recommendation_snapshot/latest_status.json")),
        (
            "pipeline",
            Path(
                "scheduled/recommendation_calibration_learning/latest_status.json"
            ),
        ),
    ],
)
def test_same_day_reader_rejects_status_symlinks_when_supported(
    tmp_path: Path,
    status_kind: str,
    relative_path: Path,
) -> None:
    args = _fixture_args(tmp_path)
    status_path = args.snapshot_output_root / relative_path
    target_path = args.snapshot_output_root / f"{status_kind}-status-target.json"
    target_path.write_bytes(status_path.read_bytes())
    status_path.unlink()
    try:
        os.symlink(target_path, status_path)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"此環境不能建立測試 symlink：{exc}")

    snapshot, reason = operational.load_same_day_snapshot(
        output_root=args.snapshot_output_root,
        decision_date=date.fromisoformat(args.decision_date),
    )

    assert snapshot is None
    assert reason == f"recommendation_{status_kind}_status_unreadable_or_unsafe"


def test_same_day_reader_fails_closed_when_status_identity_changes_during_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app_module.recommendation import queries

    args = _fixture_args(tmp_path)
    original_key = queries._stat_stability_key
    key_calls = 0

    def simulate_identity_change(info: os.stat_result) -> tuple[int, ...]:
        nonlocal key_calls
        key_calls += 1
        key = original_key(info)
        if key_calls == 2:
            return (*key[:-1], key[-1] + 1)
        return key

    monkeypatch.setattr(queries, "_stat_stability_key", simulate_identity_change)
    monkeypatch.setattr(
        operational,
        "_read_json",
        lambda _path: (_ for _ in ()).throw(
            AssertionError("status read must not fall back to unbounded read_text")
        ),
    )

    snapshot, reason = operational.load_same_day_snapshot(
        output_root=args.snapshot_output_root,
        decision_date=date.fromisoformat(args.decision_date),
    )

    assert snapshot is None
    assert reason == "recommendation_snapshot_status_unreadable_or_unsafe"
    assert key_calls == 2


def test_same_day_reader_rejects_missing_result_id_even_with_legacy_decoy(
    tmp_path: Path,
) -> None:
    args = _fixture_args(tmp_path)
    _write_legacy_snapshot_decoy(
        args.snapshot_output_root,
        decision_date=args.decision_date,
    )
    status_path = (
        args.snapshot_output_root
        / "scheduled"
        / "recommendation_snapshot"
        / "latest_status.json"
    )
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status.pop("result_id")
    status_path.write_text(json.dumps(status), encoding="utf-8")

    snapshot, reason = operational.load_same_day_snapshot(
        output_root=args.snapshot_output_root,
        decision_date=date.fromisoformat(args.decision_date),
    )

    assert snapshot is None
    assert reason == "recommendation_snapshot_status_result_id_missing_or_invalid"


def test_same_day_reader_rejects_pipeline_result_id_mismatch(
    tmp_path: Path,
) -> None:
    args = _fixture_args(tmp_path)
    pipeline_status_path = (
        args.snapshot_output_root
        / "scheduled"
        / "recommendation_calibration_learning"
        / "latest_status.json"
    )
    pipeline_status = json.loads(pipeline_status_path.read_text(encoding="utf-8"))
    pipeline_status["steps"]["recommendation_snapshot"]["child_status"][
        "result_id"
    ] = "different-snapshot-result"
    pipeline_status_path.write_text(
        json.dumps(pipeline_status),
        encoding="utf-8",
    )

    snapshot, reason = operational.load_same_day_snapshot(
        output_root=args.snapshot_output_root,
        decision_date=date.fromisoformat(args.decision_date),
    )

    assert snapshot is None
    assert reason == "recommendation_pipeline_snapshot_identity_mismatch"


def test_same_day_reader_rejects_unavailable_canonical_result_with_legacy_decoy(
    tmp_path: Path,
) -> None:
    args = _fixture_args(tmp_path)
    _write_legacy_snapshot_decoy(
        args.snapshot_output_root,
        decision_date=args.decision_date,
    )
    _rewrite_snapshot_result_id(
        args.snapshot_output_root,
        "bank-snapshot-not-saved",
    )

    snapshot, reason = operational.load_same_day_snapshot(
        output_root=args.snapshot_output_root,
        decision_date=date.fromisoformat(args.decision_date),
    )

    assert snapshot is None
    assert reason is not None
    assert reason.startswith("recommendation_snapshot_canonical_readback_failed:")
    assert "未讀到保存 artifact" in reason


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
