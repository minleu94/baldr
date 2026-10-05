from __future__ import annotations

from argparse import Namespace
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import gc
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from zoneinfo import ZoneInfo

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


def test_default_snapshot_root_follows_legacy_source_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BANKTAIWAN_SNAPSHOT_OUTPUT_ROOT", raising=False)
    monkeypatch.delenv("OUTPUT_ROOT", raising=False)
    source_root = tmp_path / "legacy-shadow"
    paths = operational.resolve_operational_paths(
        data_root=tmp_path / "formal-data",
        lane_output_root=tmp_path / "banktaiwan-shadow",
        source_artifact_root=source_root,
    )
    assert paths.snapshot_output_root == source_root.resolve()


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


def _open_calendar(
    monkeypatch: pytest.MonkeyPatch,
    is_trading_day: bool = True,
    *,
    evidence_sha256: str = "sha256:" + "a" * 64,
) -> None:
    class _Calendar:
        def __init__(self, **_kwargs: object) -> None:
            self._schedule_evidence: dict[int, dict[str, object]] = {}

        def is_official_trading_day(
            self,
            _target_date: date,
            *,
            allow_online_probe: bool,
        ) -> tuple[bool, str]:
            assert allow_online_probe is False
            self._schedule_evidence[_target_date.year] = {
                "mode": "hash_bound_official_calendar_cache",
                "cache_file_sha256": evidence_sha256,
                "source_hash": evidence_sha256,
                "captured_at": "2026-09-20T00:00:00+00:00",
                "validated_at": "2026-09-22T00:00:00+00:00",
            }
            return is_trading_day, "fixture_open" if is_trading_day else "weekend_closed"

    monkeypatch.setattr(operational, "OfficialTradingCalendar", _Calendar)


def _successful_child(
    paths: operational.OperationalPaths,
    decision_date: date,
    scenario: object,
    _args: Namespace,
    *,
    run_status: str = "completed",
) -> dict[str, object]:
    run_id = f"fixture-run-{decision_date.strftime('%Y%m%d')}"
    receipt_path = (
        paths.lane_learning_root
        / "runs"
        / decision_date.isoformat()
        / "fixture-scope"
        / "run_receipt.json"
    )
    cost_scenario_hash = str(getattr(scenario, "scenario_hash", ""))
    run_summary: dict[str, object] = {
        "run_id": run_id,
        "status": run_status,
        "reason": "fixture_run_reason",
        "receipt_path": str(receipt_path),
        "dataset_id": "fixture-dataset",
        "dataset_hash": "sha256:fixture-dataset",
        "candidate_id": "rec-cal-fixture",
        "candidate_root": "fixture-candidate",
        "training_lineage_manifest_hash": "sha256:fixture-lineage",
        "training_lineage_manifest_path": "fixture-lineage.json",
        "training_lineage_status": "verified",
        "decision": "retain_current",
        "decision_reason": "natural_forward_evidence_receipt_missing",
    }
    receipt = {
        "schema_version": "daily-recommendation-learning-receipt.v1",
        **run_summary,
        "decision_date": decision_date.isoformat(),
        "run_scope": "fixture-scope",
        "cost_scenario_hash": cost_scenario_hash,
        "finalized": run_status == "completed",
        "recoverable": run_status != "completed",
        "formal_order_allowed": False,
        "shadow_only": True,
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return {
        "status": "completed_process",
        "returncode": 0,
        "command": ["fixture-child"],
        "stdout_stderr_tail": "fixture",
        "child_payload_source": "fixture_terminal_json",
        "child_payload": {
            "schema_version": "daily-recommendation-learning-cli-result.v3",
            "decision_date": decision_date.isoformat(),
            "cost_scenario_hash": cost_scenario_hash,
            "formal_order_allowed": False,
            "shadow_only": True,
            "run": run_summary,
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
    terminal_receipt_bytes = Path(first["receipt_path"]).read_bytes()
    assert first["terminal_receipt_sha256"] == "sha256:" + hashlib.sha256(
        terminal_receipt_bytes
    ).hexdigest()
    assert second["terminal_receipt_sha256"] == first["terminal_receipt_sha256"]
    assert calls == ["called"]
    assert len(list((tmp_path / "banktaiwan-shadow" / "scheduled" / "recommendation_learning_banktaiwan" / "runs").glob("*.json"))) == 1
    snapshot = first["snapshot"]
    assert snapshot["file_sha256"] == "sha256:" + hashlib.sha256(
        Path(snapshot["path"]).read_bytes()
    ).hexdigest()
    assert snapshot["file_sha256"] == snapshot["invocation_output_sha256"]
    assert snapshot["canonical_artifact_sha256"].startswith("sha256:")


def test_production_child_stdout_over_status_bound_is_pinned_and_reusable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _fixture_args(tmp_path)
    _open_calendar(monkeypatch)
    paths, decision_date, scenario = operational._common_args(args)
    child_result = _successful_child(paths, decision_date, scenario, args)
    child_payload = child_result["child_payload"]
    assert isinstance(child_payload, dict)
    child_payload["test_only_large_report"] = "x" * (
        operational._MAX_OPERATIONAL_STATUS_BYTES + 1024
    )
    dependencies = child_payload["dependencies"]
    assert isinstance(dependencies, dict)
    dependencies["source_contract"] = {
        "status": "blocked",
        "decision_date": decision_date.isoformat(),
        "contract_sha256": "sha256:" + "a" * 64,
        "technical": {
            "reason": "prospective_feature_snapshot_failed:DailyPriceSourceRevisionError",
            "prospective_feature_snapshot": {
                "status": "blocked",
                "verified": False,
                "reason": "prospective_feature_snapshot_failed:DailyPriceSourceRevisionError",
            },
        },
        "lanes": {
            "price_up_calibration": {
                "prospective_status": "blocked",
                "prospective_blockers": ["formal_market_source_revision_blocks_pit"],
            }
        },
    }
    dependencies["source_contract_receipt"] = {
        "status": "blocked",
        "contract_path": str(paths.lane_learning_root / "source_contract" / "contract.json"),
        "contract_content_sha256": "sha256:" + "b" * 64,
        "contract_file_sha256": "sha256:" + "c" * 64,
        "decision_date": decision_date.isoformat(),
    }
    raw_stdout = json.dumps(
        child_payload,
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    assert len(raw_stdout) > operational._MAX_OPERATIONAL_STATUS_BYTES
    assert len(raw_stdout) <= operational._MAX_CHILD_CLI_STDOUT_ARTIFACT_BYTES
    invocations: list[object] = []

    def completed_process(command: object, **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        invocations.append(command)
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=raw_stdout,
            stderr=b"",
        )

    monkeypatch.setattr(operational.subprocess, "run", completed_process)
    first_code, first = operational.run_once(args)

    assert first_code == 0, (
        first.get("status"),
        first.get("reason"),
        (first.get("child_invocation") or {}).get("child_payload_source"),
        (first.get("child_invocation") or {}).get("stdout_artifact"),
        (first.get("child_invocation") or {}).get("terminal_readback"),
    )
    assert first["status"] == "completed_waiting_natural_maturity"
    artifact = first["child_invocation"]["stdout_artifact"]
    assert artifact["status"] == "verified"
    assert artifact["size_bytes"] == len(raw_stdout)
    artifact_path = Path(artifact["path"])
    assert artifact_path.read_bytes() == raw_stdout
    assert "sha256:" + hashlib.sha256(raw_stdout).hexdigest() == artifact["sha256"]
    assert "test_only_large_report" not in first["child_result"]
    assert first["child_result"]["dependencies"]["source_contract_receipt"][
        "contract_file_sha256"
    ] == "sha256:" + "c" * 64
    assert first["child_result"]["dependencies"]["price_up_calibration"][
        "prospective_status"
    ] == "blocked"
    receipt_path = Path(str(first["receipt_path"]))
    assert receipt_path.stat().st_size <= operational._MAX_OPERATIONAL_STATUS_BYTES
    assert paths.latest_status_path.stat().st_size <= operational._MAX_OPERATIONAL_STATUS_BYTES

    def unexpected_second_child(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        raise AssertionError("same input should reuse the verified terminal")

    monkeypatch.setattr(operational.subprocess, "run", unexpected_second_child)
    second_code, second = operational.run_once(args)
    assert second_code == 0
    assert second["idempotent_replay"] is True
    assert second["reused_run_id"] == first["run_id"]
    assert invocations and len(invocations) == 1
    assert receipt_path.stat().st_size <= operational._MAX_CHILD_RUN_RECEIPT_BYTES


def test_production_child_stdout_size_cap_blocks_without_parsing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _fixture_args(tmp_path)
    _open_calendar(monkeypatch)
    paths, decision_date, scenario = operational._common_args(args)
    _successful_child(paths, decision_date, scenario, args)
    raw_stdout = b"x" * (operational._MAX_CHILD_CLI_STDOUT_ARTIFACT_BYTES + 1)

    def completed_process(command: object, **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=raw_stdout,
            stderr=b"",
        )

    monkeypatch.setattr(operational.subprocess, "run", completed_process)
    monkeypatch.setattr(
        operational,
        "_extract_child_json",
        lambda _stdout: (_ for _ in ()).throw(AssertionError("over-cap stdout must not be parsed")),
    )
    code, payload = operational.run_once(args)

    assert code == 2
    assert payload["status"] == "failed_dependency"
    artifact = payload["child_invocation"]["stdout_artifact"]
    assert artifact["status"] == "blocked"
    assert artifact["reason"] == "child_stdout_artifact_size_limit_exceeded"
    assert artifact["observed_size_bytes"] == len(raw_stdout)
    assert "path" in artifact
    assert not Path(artifact["path"]).exists()
    receipt_path = Path(str(payload["receipt_path"]))
    assert receipt_path.stat().st_size <= operational._MAX_OPERATIONAL_STATUS_BYTES
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "failed_dependency"
    assert receipt["reason"] == payload["reason"]
    assert paths.latest_status_path.stat().st_size <= operational._MAX_OPERATIONAL_STATUS_BYTES


def test_child_stdout_artifact_readback_mismatch_keeps_artifact_and_blocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _fixture_args(tmp_path)
    _open_calendar(monkeypatch)
    paths, decision_date, scenario = operational._common_args(args)
    child_result = _successful_child(paths, decision_date, scenario, args)
    child_payload = child_result["child_payload"]
    assert isinstance(child_payload, dict)
    raw_stdout = json.dumps(child_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    original_reader = operational._read_child_stdout_artifact
    changed_paths: list[Path] = []

    def mutate_published_file(path: Path, *, root: Path) -> bytes:
        if not changed_paths:
            path.write_bytes(b"mutated-after-create-only-publish")
            changed_paths.append(path)
        return original_reader(path, root=root)

    def completed_process(command: object, **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(args=command, returncode=0, stdout=raw_stdout, stderr=b"")

    monkeypatch.setattr(operational.subprocess, "run", completed_process)
    monkeypatch.setattr(operational, "_read_child_stdout_artifact", mutate_published_file)
    code, payload = operational.run_once(args)

    assert code == 2
    assert payload["status"] == "failed_dependency"
    artifact = payload["child_invocation"]["stdout_artifact"]
    assert artifact["status"] == "blocked"
    assert artifact["reason"] == "child_stdout_artifact_publish_or_readback_failed"
    assert len(changed_paths) == 1
    assert changed_paths[0].read_bytes() == b"mutated-after-create-only-publish"
    assert paths.latest_status_path.stat().st_size <= operational._MAX_OPERATIONAL_STATUS_BYTES


def test_child_stdout_artifact_preflight_failure_does_not_start_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _fixture_args(tmp_path)
    _open_calendar(monkeypatch)
    monkeypatch.setattr(
        operational,
        "_prepare_child_stdout_artifact_target",
        lambda **_kwargs: (None, "child_stdout_artifact_root_unsafe"),
    )
    monkeypatch.setattr(
        operational.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("unsafe artifact root must block before child start")
        ),
    )

    code, payload = operational.run_once(args)

    assert code == 2
    assert payload["status"] == "failed_dependency"
    assert payload["reason"] == "child_stdout_artifact_root_unsafe"
    assert payload["child_invocation"]["status"] == "not_started"


def test_terminal_reuse_revalidates_complete_run_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _fixture_args(tmp_path)
    _open_calendar(monkeypatch)
    calls = 0

    def child(*child_args: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return _successful_child(*child_args)  # type: ignore[arg-type]

    first_code, first = operational.run_once(args, child_runner=child)
    wrapper_receipt_path = Path(str(first["receipt_path"]))
    wrapper_latest_path = (
        tmp_path
        / "banktaiwan-shadow"
        / "scheduled"
        / "recommendation_learning_banktaiwan"
        / "latest_status.json"
    )
    receipt = json.loads(wrapper_receipt_path.read_text(encoding="utf-8"))
    receipt["reason"] = "tampered_terminal_reason"
    wrapper_receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    latest = json.loads(wrapper_latest_path.read_text(encoding="utf-8"))
    latest["terminal_receipt_sha256"] = "sha256:" + hashlib.sha256(
        wrapper_receipt_path.read_bytes()
    ).hexdigest()
    wrapper_latest_path.write_text(
        json.dumps(latest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    second_code, second = operational.run_once(args, child_runner=child)

    assert first_code == second_code == 0
    assert second.get("idempotent_replay") is not True
    assert second["attempt_number"] == 2
    assert calls == 2


def test_terminal_reuse_checks_original_child_stdout_artifact_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _fixture_args(tmp_path)
    _open_calendar(monkeypatch)
    paths, decision_date, scenario = operational._common_args(args)
    child_result = _successful_child(paths, decision_date, scenario, args)
    child_payload = child_result["child_payload"]
    assert isinstance(child_payload, dict)
    raw_stdout = json.dumps(child_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")

    def completed_process(command: object, **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(args=command, returncode=0, stdout=raw_stdout, stderr=b"")

    monkeypatch.setattr(operational.subprocess, "run", completed_process)
    first_code, first = operational.run_once(args)
    assert first_code == 0
    stdout_artifact = Path(first["child_invocation"]["stdout_artifact"]["path"])
    stdout_artifact.write_bytes(raw_stdout + b"tampered")
    latest, latest_error = operational._read_bounded_snapshot_status(
        paths.latest_status_path,
        root=paths.operational_root,
    )
    assert latest is not None, latest_error
    assert not operational._reusable_terminal_receipt_matches(
        paths=paths,
        latest=latest,
        decision_date=decision_date,
        input_fingerprint=str(first["input_fingerprint"]),
    )


def test_terminal_receipt_size_guard_writes_small_blocked_fallback(
    tmp_path: Path,
) -> None:
    args = _fixture_args(tmp_path)
    paths, decision_date, scenario = operational._common_args(args)
    input_fingerprint = "sha256:" + "d" * 64
    run_id = operational._run_id(decision_date, input_fingerprint, 1)
    base = operational._base_payload(
        paths=paths,
        decision_date=decision_date,
        scenario=scenario,
        input_fingerprint=input_fingerprint,
    )
    base.update(
        {
            "status": "completed_shadow",
            "reason": "fixture_completed",
            "recoverable": False,
            "started_at": datetime.now(ZoneInfo("Asia/Taipei")).isoformat(),
            "attempt_number": 1,
            "child_invocation": {
                "status": "completed_process",
                "returncode": 0,
                "command": ["fixture-child"],
                "child_payload_source": "invocation_stdout_json",
                "stdout_artifact": {
                    "status": "verified",
                    "path": str(paths.operational_root / "child_cli_artifacts" / "fixture.stdout.bin"),
                    "size_bytes": 1,
                    "sha256": "sha256:" + "e" * 64,
                },
            },
            "child_result": {"unbounded_fixture": "x" * operational._MAX_OPERATIONAL_STATUS_BYTES},
        }
    )

    latest = operational._persist_terminal(paths=paths, payload=base, run_id=run_id)

    receipt_path = Path(str(latest["receipt_path"]))
    assert latest["status"] == "failed_dependency"
    assert latest["reason"] == "operational_terminal_payload_size_limit_exceeded"
    assert latest["original_operational_classification"]["status"] == "completed_shadow"
    assert receipt_path.stat().st_size <= operational._MAX_OPERATIONAL_STATUS_BYTES
    assert paths.latest_status_path.stat().st_size <= operational._MAX_OPERATIONAL_STATUS_BYTES
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["status"] == latest["status"]
    assert receipt["original_operational_classification"]["status"] == "completed_shadow"


@pytest.mark.parametrize("unsafe_target", ["latest_status", "run_receipt"])
def test_terminal_reuse_fails_closed_when_bounded_reader_rejects_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    unsafe_target: str,
) -> None:
    from app_module.recommendation import queries

    args = _fixture_args(tmp_path)
    _open_calendar(monkeypatch)
    first_code, first = operational.run_once(args, child_runner=_successful_child)
    assert first_code == 0
    paths, decision_date, _scenario = operational._common_args(args)
    rejected_path = (
        paths.latest_status_path
        if unsafe_target == "latest_status"
        else Path(str(first["receipt_path"]))
    ).resolve()
    original_reader = queries._read_regular_file_no_follow

    def reject_target(path: Path, *reader_args: object, **reader_kwargs: object) -> bytes:
        if Path(path).resolve() == rejected_path:
            raise queries.ExecutionArtifactIntegrityError("fixture unsafe file")
        return original_reader(path, *reader_args, **reader_kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(queries, "_read_regular_file_no_follow", reject_target)
    second_code, second = operational.run_once(args, child_runner=_successful_child)

    assert second_code == 0
    assert second.get("idempotent_replay") is not True
    assert second["attempt_number"] == 2


def test_terminal_reuse_fails_closed_when_receipt_exceeds_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _fixture_args(tmp_path)
    _open_calendar(monkeypatch)
    first_code, first = operational.run_once(args, child_runner=_successful_child)
    assert first_code == 0
    paths, decision_date, _scenario = operational._common_args(args)
    latest, error = operational._read_bounded_snapshot_status(
        paths.latest_status_path,
        root=paths.operational_root,
    )
    assert latest is not None, error
    monkeypatch.setattr(operational, "_MAX_CHILD_RUN_RECEIPT_BYTES", 1)

    assert not operational._reusable_terminal_receipt_matches(
        paths=paths,
        latest=latest,
        decision_date=decision_date,
        input_fingerprint=str(first["input_fingerprint"]),
    )


@pytest.mark.parametrize("link_kind", ["latest_status", "run_receipt"])
def test_terminal_reuse_rejects_symlinked_status_or_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    link_kind: str,
) -> None:
    args = _fixture_args(tmp_path)
    _open_calendar(monkeypatch)

    first_code, first = operational.run_once(args, child_runner=_successful_child)
    assert first_code == 0
    if link_kind == "latest_status":
        protected_path = (
            tmp_path
            / "banktaiwan-shadow"
            / "scheduled"
            / "recommendation_learning_banktaiwan"
            / "latest_status.json"
        )
    else:
        protected_path = Path(str(first["receipt_path"]))
    target_path = tmp_path / f"{link_kind}-target.json"
    target_bytes = protected_path.read_bytes()
    target_path.write_bytes(target_bytes)
    protected_path.unlink()
    try:
        protected_path.symlink_to(target_path)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"此環境不能建立測試 symlink：{exc}")

    second_code, second = operational.run_once(args, child_runner=_successful_child)

    assert second_code == 0
    assert second.get("idempotent_replay") is not True
    assert second["attempt_number"] == 2
    assert target_path.read_bytes() == target_bytes
    if link_kind == "latest_status":
        assert not protected_path.is_symlink()
    else:
        assert protected_path.is_symlink()
        assert Path(str(second["receipt_path"])) != protected_path


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


def test_failed_child_cannot_be_reclassified_as_closed_day_skip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _fixture_args(tmp_path)
    _open_calendar(monkeypatch, is_trading_day=True)

    def failed_but_closed(*child_args: object) -> dict[str, object]:
        result = _successful_child(
            *child_args,  # type: ignore[arg-type]
            run_status="failed_training",
        )
        payload = result["child_payload"]
        assert isinstance(payload, dict)
        payload["live_capture"] = {
            "status": "skipped",
            "reason": "non_trading_day_official_calendar",
        }
        return result

    first_code, first = operational.run_once(args, child_runner=failed_but_closed)
    second_code, second = operational.run_once(args, child_runner=_successful_child)

    assert first_code == 2
    assert first["status"] == "failed_dependency"
    assert first["reason"].startswith("child_run_failed:failed_training:")
    assert second_code == 0
    assert second["status"] == "completed_waiting_natural_maturity"
    assert second["attempt_number"] == 2
    assert second.get("idempotent_replay") is not True


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("history_start_date", "2015-01-01"),
        ("max_decision_dates", 6),
    ],
)
def test_terminal_fingerprint_binds_replay_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    replacement: object,
) -> None:
    args = _fixture_args(tmp_path)
    _open_calendar(monkeypatch)
    calls = 0

    def child(*child_args: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return _successful_child(*child_args)  # type: ignore[arg-type]

    first_code, first = operational.run_once(args, child_runner=child)
    setattr(args, field, replacement)
    second_code, second = operational.run_once(args, child_runner=child)

    assert first_code == second_code == 0
    assert first["input_fingerprint"] != second["input_fingerprint"]
    assert second.get("idempotent_replay") is not True
    assert second["attempt_number"] == 2
    assert calls == 2


def test_terminal_fingerprint_binds_official_calendar_cache_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _fixture_args(tmp_path)
    calls = 0

    def child(*child_args: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return _successful_child(*child_args)  # type: ignore[arg-type]

    _open_calendar(monkeypatch, evidence_sha256="sha256:" + "b" * 64)
    first_code, first = operational.run_once(args, child_runner=child)
    _open_calendar(monkeypatch, evidence_sha256="sha256:" + "c" * 64)
    second_code, second = operational.run_once(args, child_runner=child)

    assert first_code == second_code == 0
    assert first["calendar"]["input_identity"]["annual_schedule_evidence"][
        "cache_file_sha256"
    ] != second["calendar"]["input_identity"]["annual_schedule_evidence"][
        "cache_file_sha256"
    ]
    assert first["input_fingerprint"] != second["input_fingerprint"]
    assert second.get("idempotent_replay") is not True
    assert second["attempt_number"] == 2
    assert calls == 2


def test_operational_task_rejects_child_run_failure_with_zero_exit_and_retries(
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
            return _successful_child(
                *child_args,  # type: ignore[arg-type]
                run_status="failed_training",
            )
        return _successful_child(*child_args)  # type: ignore[arg-type]

    first_code, first = operational.run_once(args, child_runner=child)
    second_code, second = operational.run_once(args, child_runner=child)

    assert first_code == 2
    assert first["status"] == "failed_dependency"
    assert first["reason"].startswith("child_run_failed:failed_training:")
    assert first["child_invocation"]["terminal_readback"]["status"] == "verified"
    assert second_code == 0
    assert second["status"] == "completed_waiting_natural_maturity"
    assert second["attempt_number"] == 2
    assert attempts == 2


def test_operational_task_rejects_child_summary_that_differs_from_run_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _fixture_args(tmp_path)
    _open_calendar(monkeypatch)

    def mismatched_child(*child_args: object) -> dict[str, object]:
        child = _successful_child(*child_args)  # type: ignore[arg-type]
        payload = child["child_payload"]
        assert isinstance(payload, dict)
        run = payload["run"]
        assert isinstance(run, dict)
        receipt_path = Path(str(run["receipt_path"]))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["candidate_id"] = "different-candidate-than-stdout"
        receipt_path.write_text(
            json.dumps(receipt, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        return child

    code, payload = operational.run_once(args, child_runner=mismatched_child)

    assert code == 2
    assert payload["status"] == "failed_dependency"
    assert payload["reason"] == (
        "child_terminal_readback_failed:child_run_receipt_candidate_id_mismatch"
    )
    assert payload["child_invocation"]["terminal_readback"]["status"] == "failed"


def test_operational_task_rejects_missing_child_run_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _fixture_args(tmp_path)
    _open_calendar(monkeypatch)

    def missing_receipt(*child_args: object) -> dict[str, object]:
        child = _successful_child(*child_args)  # type: ignore[arg-type]
        payload = child["child_payload"]
        assert isinstance(payload, dict)
        run = payload["run"]
        assert isinstance(run, dict)
        Path(str(run["receipt_path"])).unlink()
        return child

    code, payload = operational.run_once(args, child_runner=missing_receipt)

    assert code == 2
    assert payload["status"] == "failed_dependency"
    assert payload["child_invocation"]["terminal_readback"]["status"] == "failed"
    assert "child_run_receipt_unreadable_or_unsafe" in payload["reason"]


def test_operational_task_does_not_use_stale_child_latest_status_without_stdout_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _fixture_args(tmp_path)
    _open_calendar(monkeypatch)
    paths, decision_date, scenario = operational._common_args(args)
    latest_child_status = paths.lane_learning_root / "latest_status.json"
    latest_child_status.parent.mkdir(parents=True, exist_ok=True)
    stale = {
        "schema_version": "daily-recommendation-learning-cli-result.v3",
        "decision_date": decision_date.isoformat(),
        "cost_scenario_hash": scenario.scenario_hash,
        "formal_order_allowed": False,
        "shadow_only": True,
        "run": {
            "run_id": "stale-run-from-earlier-invocation",
            "status": "completed",
            "decision_reason": "natural_forward_evidence_receipt_missing",
        },
        "live_capture": {"status": "captured", "reason": "stale"},
    }
    stale_bytes = json.dumps(stale, ensure_ascii=False, sort_keys=True).encode("utf-8")
    latest_child_status.write_bytes(stale_bytes)

    def child_without_json(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="child produced no terminal JSON\n",
            stderr="",
        )

    monkeypatch.setattr(operational.subprocess, "run", child_without_json)
    first_code, first = operational.run_once(args)
    assert first_code == 2
    assert first["status"] == "failed_dependency"
    assert first["reason"] == (
        "child_terminal_readback_failed:child_stdout_json_missing_or_invalid"
    )
    assert first["child_result"] == {}
    assert latest_child_status.read_bytes() == stale_bytes

    second_code, second = operational.run_once(args, child_runner=_successful_child)
    assert second_code == 0
    assert second["status"] == "completed_waiting_natural_maturity"
    assert second["attempt_number"] == 2


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


def test_same_day_reader_uses_bounded_shadow_projection_when_full_status_is_large(
    tmp_path: Path,
) -> None:
    from scripts.scheduled import run_daily_recommendation_learning_pipeline as pipeline

    args = _fixture_args(tmp_path)
    pipeline_root = (
        args.snapshot_output_root / "scheduled" / "recommendation_calibration_learning"
    )
    full_path = pipeline_root / "latest_status.json"
    full_status = json.loads(full_path.read_text(encoding="utf-8"))
    projection = pipeline._snapshot_source_projection(full_status)
    assert projection["schema_version"] == "daily-recommendation-snapshot-source.v1"
    assert projection["steps"]["recommendation_snapshot"]["child_status"]["result_id"] == (
        full_status["steps"]["recommendation_snapshot"]["child_status"]["result_id"]
    )
    projection_path = pipeline_root / "latest_snapshot_source_status.json"
    projection_path.write_text(json.dumps(projection), encoding="utf-8")
    full_status["large_learning_only_payload"] = "x" * operational._MAX_SNAPSHOT_STATUS_BYTES
    full_path.write_text(json.dumps(full_status), encoding="utf-8")

    snapshot, reason = operational.load_same_day_snapshot(
        output_root=args.snapshot_output_root,
        decision_date=date.fromisoformat(args.decision_date),
    )
    assert snapshot is not None, reason


def test_same_day_reader_accepts_snapshot_when_parent_learning_fails(
    tmp_path: Path,
) -> None:
    from scripts.scheduled import run_daily_recommendation_learning_pipeline as pipeline

    args = _fixture_args(tmp_path)
    pipeline_root = (
        args.snapshot_output_root / "scheduled" / "recommendation_calibration_learning"
    )
    full_path = pipeline_root / "latest_status.json"
    full_status = json.loads(full_path.read_text(encoding="utf-8"))
    full_status["status"] = "failed"
    full_status["failure_stage"] = "recommendation_learning"
    full_status["blockers"] = ["recommendation_learning_failed"]
    full_status["steps"]["data_update_quick"] = {
        "status": "passed",
        "returncode": 0,
    }
    full_status["steps"]["official_market_events"] = {
        "status": "passed",
        "returncode": 0,
    }
    full_status["steps"]["recommendation_learning"] = {
        "status": "failed",
        "returncode": 2,
    }
    projection = pipeline._snapshot_source_projection(full_status)
    projection_path = pipeline_root / "latest_snapshot_source_status.json"
    projection_path.write_text(
        json.dumps(projection, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )

    snapshot, reason = operational.load_same_day_snapshot(
        output_root=args.snapshot_output_root,
        decision_date=date.fromisoformat(args.decision_date),
    )

    assert snapshot is not None, reason
    assert snapshot.pipeline_status_payload["status"] == "failed"
    assert snapshot.result_id == "bank-snapshot-20260922"


def test_same_day_reader_rejects_corrupt_projection_without_full_status_fallback(
    tmp_path: Path,
) -> None:
    args = _fixture_args(tmp_path)
    projection_path = (
        args.snapshot_output_root / "scheduled" / "recommendation_calibration_learning"
        / "latest_snapshot_source_status.json"
    )
    projection_path.write_text("{broken", encoding="utf-8")
    snapshot, reason = operational.load_same_day_snapshot(
        output_root=args.snapshot_output_root,
        decision_date=date.fromisoformat(args.decision_date),
    )
    assert snapshot is None
    assert reason == "recommendation_pipeline_status_missing_or_invalid"


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


def _producer_run_id(decision_date: date, started_at: datetime) -> str:
    started_utc = started_at.astimezone(timezone.utc)
    return (
        f"{decision_date:%Y%m%d}-{started_utc.strftime('%Y%m%dT%H%M%S%fZ')}"
        "-a1b2c3d4e5f6"
    )


def _write_producer_terminal_snapshot_source(
    args: Namespace,
    *,
    run_id: str,
    completed_at: datetime,
    parent_status: str = "passed_with_warnings",
    corrupt_projection_hash: bool = False,
) -> dict[str, object]:
    """Use the producer's real projection/terminal-receipt builders in tests."""
    from scripts.scheduled import run_daily_recommendation_learning_pipeline as pipeline

    output_root = Path(args.snapshot_output_root).resolve()
    decision_date = date.fromisoformat(args.decision_date)
    pipeline_root = output_root / "scheduled" / "recommendation_calibration_learning"
    snapshot_status_path = output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json"
    snapshot_status = json.loads(snapshot_status_path.read_text(encoding="utf-8"))
    cohort = snapshot_status["snapshot_cohort"]
    result_id = snapshot_status["result_id"]
    invocation_dir = pipeline_root / "runs" / run_id
    invocation_dir.mkdir(parents=True, exist_ok=False)
    invocation_path = invocation_dir / "recommendation_snapshot.stdout.bin"
    invocation_payload = {
        "task": "baldr-recommendation-snapshot-daily",
        "status": "passed",
        "decision_date": decision_date.isoformat(),
        "output_root": str(output_root),
        "result_id": result_id,
        "snapshot_cohort": cohort,
    }
    invocation_raw = json.dumps(
        invocation_payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")
    invocation_path.write_bytes(invocation_raw)
    invocation_sha256 = "sha256:" + hashlib.sha256(invocation_raw).hexdigest()
    status_path = pipeline_root / "latest_status.json"
    log_path = pipeline_root / f"{decision_date:%Y%m%d}_pipeline.log"
    full_status: dict[str, object] = {
        "schema_version": "daily-recommendation-learning-pipeline.v1",
        "task": "baldr-recommendation-calibration-learning-daily",
        "status": parent_status,
        "run_id": run_id,
        "decision_date": decision_date.isoformat(),
        "decision_timezone": "Asia/Taipei",
        "output_root": str(output_root),
        "status_path": str(status_path.resolve()),
        "log_path": str(log_path.resolve()),
        "started_at": operational._parse_pipeline_run_id_start(run_id).isoformat(),
        "completed_at": completed_at.isoformat(),
        "blockers": (
            ["recommendation_learning_failed"]
            if parent_status == "failed"
            else []
        ),
        "warnings": [],
        "steps": {
            "recommendation_snapshot": {
                "name": "recommendation_snapshot",
                "status": "passed",
                "returncode": 0,
                "recoverable": False,
                "child_status": invocation_payload,
                "child_status_source": "invocation_stdout_json",
                "child_stdout_artifact_path": str(invocation_path.resolve()),
                "child_stdout_artifact_size": len(invocation_raw),
                "child_stdout_sha256": invocation_sha256,
                "child_receipt_error": None,
            },
            "recommendation_learning": {
                "name": "recommendation_learning",
                "status": "failed" if parent_status == "failed" else "passed",
                "returncode": 2 if parent_status == "failed" else 0,
                "recoverable": parent_status == "failed",
            },
        },
    }
    receipt_path = invocation_dir / "receipt.json"
    full_status["terminal_receipt_path"] = str(receipt_path.resolve())
    full_status["terminal_receipt_sha256"] = pipeline._write_terminal_receipt(
        receipt_path,
        pipeline._terminal_receipt_projection(full_status),
    )
    projection = pipeline._snapshot_source_projection(full_status)
    if corrupt_projection_hash:
        projected_step = projection["steps"]["recommendation_snapshot"]
        projected_step["child_stdout_sha256"] = "sha256:" + "f" * 64
    pipeline._write_json(
        pipeline_root / "latest_snapshot_source_status.json",
        projection,
    )
    pipeline._write_json(status_path, full_status)
    return {
        "status": full_status,
        "projection": projection,
        "receipt_path": receipt_path,
        "invocation_path": invocation_path,
        "result_id": result_id,
    }


def _write_producer_running_status(
    output_root: Path,
    *,
    decision_date: date,
    run_id: str,
    last_run_time: datetime,
    mtime_offset_seconds: float = 1.0,
) -> Path:
    from scripts.scheduled import run_daily_recommendation_learning_pipeline as pipeline

    pipeline_root = output_root / "scheduled" / "recommendation_calibration_learning"
    status_path = pipeline_root / "latest_status.json"
    payload = {
        "schema_version": "daily-recommendation-learning-pipeline.v1",
        "task": "baldr-recommendation-calibration-learning-daily",
        "status": "running",
        "run_id": run_id,
        "decision_date": decision_date.isoformat(),
        "decision_timezone": "Asia/Taipei",
        "output_root": str(output_root.resolve()),
        "status_path": str(status_path.resolve()),
        "log_path": str(
            (pipeline_root / f"{decision_date:%Y%m%d}_pipeline.log").resolve()
        ),
    }
    pipeline._write_json(status_path, payload)
    timestamp = last_run_time.timestamp() + mtime_offset_seconds
    os.utime(status_path, (timestamp, timestamp))
    return status_path


def _producer_task_observation(
    last_run_time: datetime,
    *,
    state: str = "Running",
    task_name: str = "baldr-recommendation-calibration-learning-daily",
    task_path: str = "\\",
) -> operational.ScheduledTaskObservation:
    return operational.ScheduledTaskObservation(
        task_name=task_name,
        task_path=task_path,
        state=state,
        last_run_time_utc=last_run_time,
    )


def test_upstream_task_not_running_reuses_verified_current_snapshot_without_wait(
    tmp_path: Path,
) -> None:
    args = _fixture_args(tmp_path, decision_date="2026-09-30")
    output_root = Path(args.snapshot_output_root).resolve()
    decision_date = date(2026, 9, 30)
    last_run = datetime(2026, 9, 30, 9, 0, tzinfo=timezone.utc)
    run_id = _producer_run_id(decision_date, last_run + timedelta(seconds=1))
    terminal = _write_producer_terminal_snapshot_source(
        args,
        run_id=run_id,
        completed_at=datetime(2026, 9, 30, 9, 1, tzinfo=timezone.utc),
    )
    projection_path = (
        output_root
        / "scheduled"
        / "recommendation_calibration_learning"
        / "latest_snapshot_source_status.json"
    )
    projection_mtime = datetime(2026, 9, 30, 9, 1, 1, tzinfo=timezone.utc)
    os.utime(
        projection_path,
        (projection_mtime.timestamp(), projection_mtime.timestamp()),
    )
    snapshot, reason = operational.load_same_day_snapshot(
        output_root=output_root,
        decision_date=decision_date,
    )
    assert snapshot is not None, reason
    assert snapshot.pipeline_run_id == run_id

    now = datetime(2026, 9, 30, 17, 5, tzinfo=ZoneInfo("Asia/Taipei"))
    sleeps: list[float] = []
    paths, _, _ = operational._common_args(args)
    result, result_reason, audit = operational._maybe_wait_for_current_upstream_projection(
        paths=paths,
        decision_date=decision_date,
        initial_snapshot=snapshot,
        initial_reason=None,
        wait_seconds=1800,
        attempt_deadline=6900.0,
        task_state_reader=lambda: _producer_task_observation(last_run, state="Ready"),
        monotonic=lambda: 0.0,
        sleep=sleeps.append,
        now_provider=lambda: now,
    )

    assert result is not None
    assert result.pipeline_run_id == snapshot.pipeline_run_id
    assert result.result_id == snapshot.result_id
    assert result.payload_hash == snapshot.payload_hash
    assert result_reason is None
    assert audit["status"] == "current_terminal_projection_available"
    assert sleeps == []
    assert Path(str(terminal["receipt_path"])).is_file()


@pytest.mark.parametrize(
    ("task_state_before", "task_state_after"),
    [("Running", "Ready"), ("Ready", "Ready")],
)
def test_task_accepts_matching_published_terminal_projection_without_parent_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    task_state_before: str,
    task_state_after: str,
) -> None:
    args = _fixture_args(tmp_path, decision_date="2026-09-30")
    output_root = Path(args.snapshot_output_root).resolve()
    decision_date = date(2026, 9, 30)
    last_run = datetime(2026, 9, 30, 9, 0, tzinfo=timezone.utc)
    run_id = _producer_run_id(decision_date, last_run + timedelta(seconds=1))
    completed_at = last_run + timedelta(minutes=2)
    _write_producer_terminal_snapshot_source(
        args,
        run_id=run_id,
        completed_at=completed_at,
        parent_status="failed",
    )
    projection_path = (
        output_root
        / "scheduled"
        / "recommendation_calibration_learning"
        / "latest_snapshot_source_status.json"
    )
    projection_mtime = completed_at + timedelta(seconds=1)
    os.utime(
        projection_path,
        (projection_mtime.timestamp(), projection_mtime.timestamp()),
    )
    initial_snapshot, initial_reason = operational.load_same_day_snapshot(
        output_root=output_root,
        decision_date=decision_date,
    )
    assert initial_snapshot is not None, initial_reason
    assert initial_snapshot.pipeline_run_id == run_id

    # 模擬 producer 已用大型 terminal payload 取代 parent latest；此路徑
    # 必須只依賴 bounded projection、terminal receipt 與 canonical readback。
    _pipeline_root, parent_status_path, _projection_path = operational._pipeline_paths(
        output_root
    )
    parent_status_path.write_bytes(
        b"x" * (operational._MAX_SNAPSHOT_STATUS_BYTES + 1)
    )
    original_projection_reader = operational._read_bounded_snapshot_status_with_mtime
    projection_reads: list[Path] = []

    def projection_reader(
        path: Path,
        *,
        root: Path,
    ) -> tuple[dict[str, object] | None, datetime | None, str | None]:
        projection_reads.append(path)
        assert path != parent_status_path
        return original_projection_reader(path, root=root)

    monkeypatch.setattr(
        operational,
        "_read_bounded_snapshot_status_with_mtime",
        projection_reader,
    )
    monkeypatch.setattr(
        operational,
        "_current_upstream_run_proof",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("terminal projection fast path must not read parent status")
        ),
    )

    observations = [
        _producer_task_observation(last_run, state=task_state_before),
        _producer_task_observation(last_run, state=task_state_after),
    ]
    paths, _, _ = operational._common_args(args)
    snapshot, reason, audit = operational._maybe_wait_for_current_upstream_projection(
        paths=paths,
        decision_date=decision_date,
        initial_snapshot=initial_snapshot,
        initial_reason=None,
        wait_seconds=1800,
        attempt_deadline=6900.0,
        task_state_reader=lambda: observations.pop(0),
        monotonic=lambda: 0.0,
        sleep=lambda _seconds: pytest.fail("published terminal projection must not wait"),
        now_provider=lambda: datetime(
            2026, 9, 30, 9, 5, tzinfo=timezone.utc
        ),
    )

    assert snapshot is not None
    assert snapshot.pipeline_run_id == run_id
    assert snapshot.result_id == initial_snapshot.result_id
    assert snapshot.payload_hash == initial_snapshot.payload_hash
    assert snapshot.canonical_artifact_sha256 == initial_snapshot.canonical_artifact_sha256
    assert reason is None
    assert audit["status"] == "current_terminal_projection_available"
    assert audit["terminal_receipt_verified"] is True
    assert audit["task_state_before"] == task_state_before
    assert audit["task_state_after"] == task_state_after
    assert audit["waited_seconds"] == 0.0
    assert len(projection_reads) == 2
    assert not observations


@pytest.mark.parametrize("initial_case", ["missing", "old_same_day"])
def test_running_task_accepts_new_terminal_projection_over_missing_or_old_initial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    initial_case: str,
) -> None:
    args = _fixture_args(tmp_path, decision_date="2026-09-30")
    output_root = Path(args.snapshot_output_root).resolve()
    decision_date = date(2026, 9, 30)
    last_run = datetime(2026, 9, 30, 9, 0, tzinfo=timezone.utc)
    initial_snapshot: operational.SnapshotSummary | None = None
    if initial_case == "old_same_day":
        old_run_id = _producer_run_id(decision_date, last_run - timedelta(minutes=10))
        _write_producer_terminal_snapshot_source(
            args,
            run_id=old_run_id,
            completed_at=last_run - timedelta(minutes=9),
            parent_status="failed",
        )
        initial_snapshot, initial_reason = operational.load_same_day_snapshot(
            output_root=output_root,
            decision_date=decision_date,
        )
        assert initial_snapshot is not None, initial_reason
        assert initial_snapshot.pipeline_run_id == old_run_id

    current_run_id = _producer_run_id(decision_date, last_run + timedelta(seconds=1))
    current_completed_at = last_run + timedelta(minutes=2)
    _write_producer_terminal_snapshot_source(
        args,
        run_id=current_run_id,
        completed_at=current_completed_at,
        parent_status="failed",
    )
    projection_path = (
        output_root
        / "scheduled"
        / "recommendation_calibration_learning"
        / "latest_snapshot_source_status.json"
    )
    projection_mtime = current_completed_at + timedelta(seconds=1)
    os.utime(
        projection_path,
        (projection_mtime.timestamp(), projection_mtime.timestamp()),
    )
    _pipeline_root, parent_status_path, _projection_path = operational._pipeline_paths(
        output_root
    )
    parent_status_path.write_bytes(
        b"x" * (operational._MAX_SNAPSHOT_STATUS_BYTES + 1)
    )
    monkeypatch.setattr(
        operational,
        "_current_upstream_run_proof",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("current terminal projection must not read parent status")
        ),
    )
    paths, _, _ = operational._common_args(args)
    observations = [
        _producer_task_observation(last_run, state="Running"),
        _producer_task_observation(last_run, state="Ready"),
    ]

    snapshot, reason, audit = operational._maybe_wait_for_current_upstream_projection(
        paths=paths,
        decision_date=decision_date,
        initial_snapshot=initial_snapshot,
        initial_reason="initial_snapshot_missing" if initial_snapshot is None else None,
        wait_seconds=1800,
        attempt_deadline=6900.0,
        task_state_reader=lambda: observations.pop(0),
        monotonic=lambda: 0.0,
        sleep=lambda _seconds: pytest.fail("current terminal publication must not wait"),
        now_provider=lambda: datetime(2026, 9, 30, 9, 5, tzinfo=timezone.utc),
    )

    assert snapshot is not None
    assert snapshot.pipeline_run_id == current_run_id
    assert snapshot.result_id
    assert reason is None
    assert audit["status"] == "current_terminal_projection_available"
    assert audit["terminal_receipt_verified"] is True
    assert audit["task_state_after"] == "Ready"
    assert not observations


@pytest.mark.parametrize("change_task_last_run_during_readback", [False, True])
def test_missing_initial_and_old_projection_wait_only_after_current_live_proof(
    tmp_path: Path,
    change_task_last_run_during_readback: bool,
) -> None:
    args = _fixture_args(tmp_path, decision_date="2026-09-30")
    output_root = Path(args.snapshot_output_root).resolve()
    decision_date = date(2026, 9, 30)
    last_run = datetime(2026, 9, 30, 9, 0, tzinfo=timezone.utc)
    # 模擬前一個極短 Task instance 在新 LastRun 前約三秒完成；僅因日期
    # 同為今天不能把這份舊 terminal projection 誤認成新 Task 的輸入。
    old_run_id = _producer_run_id(decision_date, last_run - timedelta(seconds=3))
    _write_producer_terminal_snapshot_source(
        args,
        run_id=old_run_id,
        completed_at=last_run - timedelta(seconds=2),
        parent_status="failed",
    )
    current_run_id = _producer_run_id(decision_date, last_run + timedelta(seconds=1))
    _write_producer_running_status(
        output_root,
        decision_date=decision_date,
        run_id=current_run_id,
        last_run_time=last_run,
    )
    paths, _, _ = operational._common_args(args)
    monotonic_now = [0.0]
    sleep_calls: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        monotonic_now[0] += seconds
        completed_at = last_run + timedelta(minutes=2)
        _write_producer_terminal_snapshot_source(
            args,
            run_id=current_run_id,
            completed_at=completed_at,
            parent_status="failed",
        )
        projection_path = (
            output_root
            / "scheduled"
            / "recommendation_calibration_learning"
            / "latest_snapshot_source_status.json"
        )
        projection_mtime = completed_at + timedelta(seconds=1)
        os.utime(
            projection_path,
            (projection_mtime.timestamp(), projection_mtime.timestamp()),
        )

    task_observations = [_producer_task_observation(last_run)] * 4 + [
        _producer_task_observation(last_run, state="Ready"),
        _producer_task_observation(
            last_run + timedelta(minutes=1)
            if change_task_last_run_during_readback
            else last_run,
            state="Ready",
        ),
    ]

    def task_reader() -> operational.ScheduledTaskObservation:
        assert task_observations
        return task_observations.pop(0)

    snapshot, reason, audit = operational._maybe_wait_for_current_upstream_projection(
        paths=paths,
        decision_date=decision_date,
        initial_snapshot=None,
        initial_reason="initial_snapshot_missing",
        wait_seconds=1800,
        attempt_deadline=6900.0,
        task_state_reader=task_reader,
        monotonic=lambda: monotonic_now[0],
        sleep=fake_sleep,
        now_provider=lambda: datetime(2026, 9, 30, 9, 5, tzinfo=timezone.utc),
    )

    if change_task_last_run_during_readback:
        assert snapshot is None
        assert reason is not None
        assert "upstream_task_observation_changed_during_terminal_readback" in reason
        assert audit["status"] == "blocked"
    else:
        assert snapshot is not None
        assert snapshot.pipeline_run_id == current_run_id
        assert reason is None
        assert audit["status"] == "ready"
        assert audit["upstream_run_id"] == current_run_id
        assert audit["last_projection_run_id"] == current_run_id
    assert sleep_calls == [5]
    assert not task_observations


def test_ready_task_does_not_reuse_old_same_day_source_after_new_run_started(
    tmp_path: Path,
) -> None:
    args = _fixture_args(tmp_path, decision_date="2026-09-30")
    output_root = Path(args.snapshot_output_root).resolve()
    decision_date = date(2026, 9, 30)
    last_run = datetime(2026, 9, 30, 9, 0, tzinfo=timezone.utc)
    old_run_id = _producer_run_id(decision_date, last_run - timedelta(seconds=3))
    _write_producer_terminal_snapshot_source(
        args,
        run_id=old_run_id,
        completed_at=last_run - timedelta(seconds=2),
        parent_status="failed",
    )
    initial_snapshot, initial_reason = operational.load_same_day_snapshot(
        output_root=output_root,
        decision_date=decision_date,
    )
    assert initial_snapshot is not None, initial_reason
    assert initial_snapshot.pipeline_run_id == old_run_id

    paths, _, _ = operational._common_args(args)
    snapshot, reason, audit = operational._maybe_wait_for_current_upstream_projection(
        paths=paths,
        decision_date=decision_date,
        initial_snapshot=initial_snapshot,
        initial_reason=None,
        wait_seconds=1800,
        attempt_deadline=6900.0,
        task_state_reader=lambda: _producer_task_observation(last_run, state="Ready"),
        monotonic=lambda: 0.0,
        sleep=lambda _seconds: pytest.fail("Ready Task cannot wait for a finished run"),
        now_provider=lambda: datetime(2026, 9, 30, 9, 5, tzinfo=timezone.utc),
    )

    assert snapshot is None
    assert reason == "recommendation_pipeline_stale_projection_after_task_completion"
    assert audit["status"] == "current_terminal_proof_invalid"


def test_running_task_rejects_matching_terminal_projection_with_mutated_receipt(
    tmp_path: Path,
) -> None:
    args = _fixture_args(tmp_path, decision_date="2026-09-30")
    output_root = Path(args.snapshot_output_root).resolve()
    decision_date = date(2026, 9, 30)
    last_run = datetime(2026, 9, 30, 9, 0, tzinfo=timezone.utc)
    run_id = _producer_run_id(decision_date, last_run + timedelta(seconds=1))
    terminal = _write_producer_terminal_snapshot_source(
        args,
        run_id=run_id,
        completed_at=last_run + timedelta(minutes=2),
    )
    projection_path = (
        output_root
        / "scheduled"
        / "recommendation_calibration_learning"
        / "latest_snapshot_source_status.json"
    )
    projection_mtime = last_run + timedelta(minutes=2, seconds=1)
    os.utime(
        projection_path,
        (projection_mtime.timestamp(), projection_mtime.timestamp()),
    )
    initial_snapshot, initial_reason = operational.load_same_day_snapshot(
        output_root=output_root,
        decision_date=decision_date,
    )
    assert initial_snapshot is not None, initial_reason

    receipt_path = Path(str(terminal["receipt_path"]))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["completed_at"] = (last_run + timedelta(minutes=3)).isoformat()
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    paths, _, _ = operational._common_args(args)
    snapshot, reason, audit = operational._maybe_wait_for_current_upstream_projection(
        paths=paths,
        decision_date=decision_date,
        initial_snapshot=initial_snapshot,
        initial_reason=None,
        wait_seconds=1800,
        attempt_deadline=6900.0,
        task_state_reader=lambda: _producer_task_observation(last_run),
        monotonic=lambda: 0.0,
        sleep=lambda _seconds: pytest.fail("mutated receipt must fail without waiting"),
        now_provider=lambda: datetime(
            2026, 9, 30, 9, 5, tzinfo=timezone.utc
        ),
    )

    assert snapshot is None
    assert reason is not None
    assert "terminal_receipt_identity_mismatch" in reason
    assert audit["status"] == "current_terminal_proof_invalid"


@pytest.mark.parametrize(
    ("clock_case", "expected_reason"),
    [
        ("task_last_run_future", "upstream_task_last_run_time_in_future"),
        (
            "run_start_future",
            "recommendation_pipeline_terminal_run_start_in_future",
        ),
        (
            "projection_mtime_before_run",
            "recommendation_pipeline_projection_mtime_precedes_run_start",
        ),
        (
            "projection_mtime_before_completed",
            "recommendation_pipeline_projection_mtime_precedes_terminal_completion",
        ),
        (
            "projection_mtime_future",
            "recommendation_pipeline_projection_mtime_in_future",
        ),
        (
            "completed_before_run",
            "recommendation_pipeline_terminal_completed_at_precedes_run_start",
        ),
        (
            "completed_future",
            "recommendation_pipeline_terminal_completed_at_in_future",
        ),
    ],
)
def test_running_task_rejects_current_terminal_projection_with_invalid_clock(
    tmp_path: Path,
    clock_case: str,
    expected_reason: str,
) -> None:
    args = _fixture_args(tmp_path, decision_date="2026-09-30")
    output_root = Path(args.snapshot_output_root).resolve()
    decision_date = date(2026, 9, 30)
    now = datetime(2026, 9, 30, 9, 5, tzinfo=timezone.utc)
    last_run = now + timedelta(seconds=3) if clock_case == "task_last_run_future" else now - timedelta(minutes=5)
    run_start = now + timedelta(seconds=3) if clock_case == "run_start_future" else last_run + timedelta(seconds=1)
    run_id = _producer_run_id(decision_date, run_start)
    completed_at = (
        run_start - timedelta(seconds=1)
        if clock_case == "completed_before_run"
        else now + timedelta(seconds=3)
        if clock_case == "completed_future"
        else now - timedelta(minutes=3)
    )
    _write_producer_terminal_snapshot_source(
        args,
        run_id=run_id,
        completed_at=completed_at,
    )
    projection_path = (
        output_root
        / "scheduled"
        / "recommendation_calibration_learning"
        / "latest_snapshot_source_status.json"
    )
    projection_mtime = (
        run_start - timedelta(seconds=1)
        if clock_case == "projection_mtime_before_run"
        else completed_at - timedelta(seconds=2)
        if clock_case == "projection_mtime_before_completed"
        else now + timedelta(seconds=3)
        if clock_case == "projection_mtime_future"
        else now - timedelta(minutes=2)
    )
    os.utime(
        projection_path,
        (projection_mtime.timestamp(), projection_mtime.timestamp()),
    )
    initial_snapshot, initial_reason = operational.load_same_day_snapshot(
        output_root=output_root,
        decision_date=decision_date,
    )
    assert initial_snapshot is not None, initial_reason
    paths, _, _ = operational._common_args(args)
    snapshot, reason, audit = operational._maybe_wait_for_current_upstream_projection(
        paths=paths,
        decision_date=decision_date,
        initial_snapshot=initial_snapshot,
        initial_reason=None,
        wait_seconds=1800,
        attempt_deadline=6900.0,
        task_state_reader=lambda: _producer_task_observation(last_run),
        monotonic=lambda: 0.0,
        sleep=lambda _seconds: pytest.fail("invalid terminal clock must fail immediately"),
        now_provider=lambda: now,
    )

    assert snapshot is None
    assert reason is not None
    assert expected_reason in reason
    assert audit["status"] == "current_terminal_proof_invalid"


def test_wait_pins_new_current_run_and_accepts_snapshot_after_parent_learning_failure(
    tmp_path: Path,
) -> None:
    args = _fixture_args(tmp_path, decision_date="2026-09-30")
    output_root = Path(args.snapshot_output_root).resolve()
    decision_date = date(2026, 9, 30)
    last_run = datetime(2026, 9, 30, 9, 0, tzinfo=timezone.utc)
    old_run_id = _producer_run_id(decision_date, last_run - timedelta(minutes=10))
    old_run = _write_producer_terminal_snapshot_source(
        args,
        run_id=old_run_id,
        completed_at=last_run - timedelta(minutes=1),
        parent_status="failed",
    )
    current_run_id = _producer_run_id(decision_date, last_run + timedelta(seconds=1))
    _write_producer_running_status(
        output_root,
        decision_date=decision_date,
        run_id=current_run_id,
        last_run_time=last_run,
    )
    initial_snapshot, initial_reason = operational.load_same_day_snapshot(
        output_root=output_root,
        decision_date=decision_date,
    )
    assert initial_snapshot is not None, initial_reason
    assert initial_snapshot.pipeline_run_id == old_run_id
    assert initial_snapshot.pipeline_status_payload["status"] == "failed"

    now = datetime(2026, 9, 30, 17, 5, tzinfo=ZoneInfo("Asia/Taipei"))
    task = _producer_task_observation(last_run)
    monotonic_now = [0.0]
    sleep_calls: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        monotonic_now[0] += seconds
        if len(sleep_calls) == 1:
            completed_at = datetime(2026, 9, 30, 9, 2, tzinfo=timezone.utc)
            _write_producer_terminal_snapshot_source(
                args,
                run_id=current_run_id,
                completed_at=completed_at,
                parent_status="failed",
            )
            projection_path = (
                output_root
                / "scheduled"
                / "recommendation_calibration_learning"
                / "latest_snapshot_source_status.json"
            )
            projection_mtime = completed_at + timedelta(seconds=1)
            os.utime(
                projection_path,
                (projection_mtime.timestamp(), projection_mtime.timestamp()),
            )

    paths, _, _ = operational._common_args(args)
    snapshot, reason, audit = operational._maybe_wait_for_current_upstream_projection(
        paths=paths,
        decision_date=decision_date,
        initial_snapshot=initial_snapshot,
        initial_reason=None,
        wait_seconds=1800,
        attempt_deadline=6900.0,
        task_state_reader=lambda: task,
        monotonic=lambda: monotonic_now[0],
        sleep=fake_sleep,
        now_provider=lambda: now,
    )

    assert snapshot is not None
    assert snapshot.pipeline_run_id == current_run_id
    assert snapshot.pipeline_run_id != old_run_id
    assert snapshot.pipeline_status_payload["status"] == "failed"
    assert snapshot.result_id == old_run["result_id"]
    assert reason is None
    assert audit["status"] == "ready"
    assert audit["upstream_run_id"] == current_run_id
    assert audit["last_projection_run_id"] == current_run_id
    assert len(sleep_calls) == 1
    heartbeat_path = Path(str(audit["heartbeat_path"]))
    heartbeat_rows = [json.loads(line) for line in heartbeat_path.read_text().splitlines()]
    assert heartbeat_rows[0]["status"] == "waiting"
    assert heartbeat_rows[-1]["status"] == "ready"


def test_running_task_proof_checks_real_identity_and_30_second_start_bound(
    tmp_path: Path,
) -> None:
    args = _fixture_args(tmp_path, decision_date="2026-09-30")
    output_root = Path(args.snapshot_output_root).resolve()
    decision_date = date(2026, 9, 30)
    last_run = datetime(2026, 9, 30, 9, 0, tzinfo=timezone.utc)
    now = last_run + timedelta(seconds=35)

    run_id_at_boundary = _producer_run_id(
        decision_date,
        last_run + timedelta(seconds=29),
    )
    _write_producer_running_status(
        output_root,
        decision_date=decision_date,
        run_id=run_id_at_boundary,
        last_run_time=last_run,
        mtime_offset_seconds=29.0,
    )
    proof, error = operational._current_upstream_run_proof(
        output_root=output_root,
        decision_date=decision_date,
        task_state_reader=lambda: _producer_task_observation(last_run),
        now=now,
    )
    assert error is None
    assert proof is not None
    assert proof.run_id == run_id_at_boundary
    assert (proof.status_mtime_utc - last_run).total_seconds() == pytest.approx(29.0)

    run_id_too_late = _producer_run_id(
        decision_date,
        last_run + timedelta(seconds=31),
    )
    _write_producer_running_status(
        output_root,
        decision_date=decision_date,
        run_id=run_id_too_late,
        last_run_time=last_run,
        mtime_offset_seconds=31.0,
    )
    proof, error = operational._current_upstream_run_proof(
        output_root=output_root,
        decision_date=decision_date,
        task_state_reader=lambda: _producer_task_observation(last_run),
        now=now,
    )
    assert proof is None
    assert error == "upstream_running_status_run_start_too_late"

    proof, error = operational._current_upstream_run_proof(
        output_root=output_root,
        decision_date=decision_date,
        task_state_reader=lambda: _producer_task_observation(
            last_run,
            task_name="different-task",
        ),
        now=now,
    )
    assert proof is None
    assert error == "upstream_task_identity_mismatch"


@pytest.mark.parametrize(
    ("run_offset_seconds", "mtime_offset_seconds", "expected_error"),
    [
        (-5.0, 1.0, "upstream_running_status_run_precedes_task_last_run"),
        (1.0, -2.0, "upstream_running_status_mtime_precedes_task_last_run"),
    ],
)
def test_same_day_running_proof_rejects_stale_run_or_status_mtime(
    tmp_path: Path,
    run_offset_seconds: float,
    mtime_offset_seconds: float,
    expected_error: str,
) -> None:
    args = _fixture_args(tmp_path, decision_date="2026-09-30")
    output_root = Path(args.snapshot_output_root).resolve()
    decision_date = date(2026, 9, 30)
    last_run = datetime(2026, 9, 30, 9, 0, tzinfo=timezone.utc)
    _write_producer_running_status(
        output_root,
        decision_date=decision_date,
        run_id=_producer_run_id(
            decision_date,
            last_run + timedelta(seconds=run_offset_seconds),
        ),
        last_run_time=last_run,
        mtime_offset_seconds=mtime_offset_seconds,
    )

    proof, error = operational._current_upstream_run_proof(
        output_root=output_root,
        decision_date=decision_date,
        task_state_reader=lambda: _producer_task_observation(last_run),
        now=last_run + timedelta(minutes=1),
    )

    assert proof is None
    assert error == expected_error


@pytest.mark.parametrize(
    ("clock_kind", "expected_error"),
    [
        ("task_last_run", "upstream_task_last_run_time_in_future"),
        ("run_start", "upstream_running_status_run_start_in_future"),
        ("status_mtime", "upstream_running_status_mtime_in_future"),
    ],
)
def test_running_proof_rejects_clocks_materially_after_observation(
    tmp_path: Path,
    clock_kind: str,
    expected_error: str,
) -> None:
    args = _fixture_args(tmp_path, decision_date="2026-09-30")
    output_root = Path(args.snapshot_output_root).resolve()
    decision_date = date(2026, 9, 30)
    now = datetime(2026, 9, 30, 9, 0, tzinfo=timezone.utc)
    last_run = now + timedelta(seconds=3) if clock_kind == "task_last_run" else now - timedelta(seconds=1)
    run_offset = 4.0 if clock_kind == "run_start" else 1.0
    mtime_offset = 4.0 if clock_kind == "status_mtime" else 1.0
    _write_producer_running_status(
        output_root,
        decision_date=decision_date,
        run_id=_producer_run_id(
            decision_date,
            last_run + timedelta(seconds=run_offset),
        ),
        last_run_time=last_run,
        mtime_offset_seconds=mtime_offset,
    )

    proof, error = operational._current_upstream_run_proof(
        output_root=output_root,
        decision_date=decision_date,
        task_state_reader=lambda: _producer_task_observation(last_run),
        now=now,
    )

    assert proof is None
    assert error == expected_error


def test_previous_day_without_live_task_proof_does_not_wait(
    tmp_path: Path,
) -> None:
    args = _fixture_args(tmp_path, decision_date="2026-09-29")
    paths, _, _ = operational._common_args(args)
    previous_day = date(2026, 9, 29)
    now = datetime(2026, 9, 30, 17, 5, tzinfo=ZoneInfo("Asia/Taipei"))
    sleeps: list[float] = []
    task_reads: list[str] = []

    def task_reader() -> operational.ScheduledTaskObservation | None:
        task_reads.append("read")
        return None

    snapshot, reason, audit = operational._maybe_wait_for_current_upstream_projection(
        paths=paths,
        decision_date=previous_day,
        initial_snapshot=None,
        initial_reason="previous_day_source_missing",
        wait_seconds=1800,
        attempt_deadline=6900.0,
        task_state_reader=task_reader,
        monotonic=lambda: 0.0,
        sleep=sleeps.append,
        now_provider=lambda: now,
    )

    assert snapshot is None
    assert reason == "previous_day_source_missing"
    assert audit["status"] == "not_current_taipei_day"
    assert task_reads == []
    assert sleeps == []


def test_current_projection_receipt_hash_mismatch_fails_without_waiting(
    tmp_path: Path,
) -> None:
    args = _fixture_args(tmp_path, decision_date="2026-09-30")
    output_root = Path(args.snapshot_output_root).resolve()
    decision_date = date(2026, 9, 30)
    last_run = datetime(2026, 9, 30, 9, 0, tzinfo=timezone.utc)
    run_id = _producer_run_id(decision_date, last_run + timedelta(seconds=1))
    _write_producer_terminal_snapshot_source(
        args,
        run_id=run_id,
        completed_at=datetime(2026, 9, 30, 9, 2, tzinfo=timezone.utc),
        corrupt_projection_hash=True,
    )
    projection_path = (
        output_root
        / "scheduled"
        / "recommendation_calibration_learning"
        / "latest_snapshot_source_status.json"
    )
    projection_mtime = datetime(2026, 9, 30, 9, 2, 1, tzinfo=timezone.utc)
    os.utime(
        projection_path,
        (projection_mtime.timestamp(), projection_mtime.timestamp()),
    )
    _write_producer_running_status(
        output_root,
        decision_date=decision_date,
        run_id=run_id,
        last_run_time=last_run,
    )
    initial_snapshot, initial_reason = operational.load_same_day_snapshot(
        output_root=output_root,
        decision_date=decision_date,
    )
    assert initial_snapshot is None
    assert initial_reason is not None

    now = datetime(2026, 9, 30, 17, 5, tzinfo=ZoneInfo("Asia/Taipei"))
    paths, _, _ = operational._common_args(args)
    sleeps: list[float] = []
    snapshot, reason, audit = operational._maybe_wait_for_current_upstream_projection(
        paths=paths,
        decision_date=decision_date,
        initial_snapshot=None,
        initial_reason=initial_reason,
        wait_seconds=1800,
        attempt_deadline=6900.0,
        task_state_reader=lambda: _producer_task_observation(last_run),
        monotonic=lambda: 0.0,
        sleep=sleeps.append,
        now_provider=lambda: now,
    )

    assert snapshot is None
    assert reason is not None
    assert "recommendation_pipeline_terminal_receipt_snapshot_binding_mismatch" in reason
    assert audit["status"] == "current_terminal_proof_invalid"
    assert audit["poll_count"] == 0
    assert sleeps == []


@pytest.mark.parametrize("terminal_state", ["stopped", "run_changed"])
def test_wait_stops_immediately_when_task_stops_or_last_run_changes(
    tmp_path: Path,
    terminal_state: str,
) -> None:
    args = _fixture_args(tmp_path, decision_date="2026-09-30")
    output_root = Path(args.snapshot_output_root).resolve()
    decision_date = date(2026, 9, 30)
    last_run = datetime(2026, 9, 30, 9, 0, tzinfo=timezone.utc)
    current_run_id = _producer_run_id(decision_date, last_run + timedelta(seconds=1))
    _write_producer_running_status(
        output_root,
        decision_date=decision_date,
        run_id=current_run_id,
        last_run_time=last_run,
    )
    if terminal_state == "stopped":
        observations = [_producer_task_observation(last_run)] * 3 + [
            _producer_task_observation(last_run, state="Ready")
        ]
        expected_reason = "recommendation_pipeline_stopped_without_current_projection"
    else:
        changed_last_run = last_run + timedelta(minutes=1)
        observations = [_producer_task_observation(last_run)] * 3 + [
            _producer_task_observation(changed_last_run)
        ]
        expected_reason = "recommendation_pipeline_task_last_run_changed"

    def task_reader() -> operational.ScheduledTaskObservation:
        return observations.pop(0) if len(observations) > 1 else observations[0]

    now = datetime(2026, 9, 30, 17, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    paths, _, _ = operational._common_args(args)
    sleeps: list[float] = []
    snapshot, reason, audit = operational._maybe_wait_for_current_upstream_projection(
        paths=paths,
        decision_date=decision_date,
        initial_snapshot=None,
        initial_reason="no_snapshot_yet",
        wait_seconds=1800,
        attempt_deadline=6900.0,
        task_state_reader=task_reader,
        monotonic=lambda: 0.0,
        sleep=sleeps.append,
        now_provider=lambda: now,
    )

    assert snapshot is None
    assert expected_reason in str(reason)
    assert audit["status"] in {"upstream_stopped", "blocked"}
    assert sleeps == []


def test_wait_deadline_emits_bounded_heartbeat_and_times_out(
    tmp_path: Path,
) -> None:
    args = _fixture_args(tmp_path, decision_date="2026-09-30")
    output_root = Path(args.snapshot_output_root).resolve()
    decision_date = date(2026, 9, 30)
    last_run = datetime(2026, 9, 30, 9, 0, tzinfo=timezone.utc)
    run_id = _producer_run_id(decision_date, last_run + timedelta(seconds=1))
    _write_producer_running_status(
        output_root,
        decision_date=decision_date,
        run_id=run_id,
        last_run_time=last_run,
    )
    now = datetime(2026, 9, 30, 17, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    monotonic_now = [0.0]
    paths, _, _ = operational._common_args(args)

    def fake_sleep(seconds: float) -> None:
        monotonic_now[0] += seconds

    snapshot, reason, audit = operational._maybe_wait_for_current_upstream_projection(
        paths=paths,
        decision_date=decision_date,
        initial_snapshot=None,
        initial_reason="no_snapshot_yet",
        wait_seconds=35,
        attempt_deadline=6900.0,
        task_state_reader=lambda: _producer_task_observation(last_run),
        monotonic=lambda: monotonic_now[0],
        sleep=fake_sleep,
        now_provider=lambda: now,
    )

    assert snapshot is None
    assert reason == "recommendation_pipeline_wait_timeout"
    assert audit["status"] == "timed_out"
    assert audit["waited_seconds"] == 35.0
    heartbeat_rows = [
        json.loads(line)
        for line in Path(str(audit["heartbeat_path"])).read_text().splitlines()
    ]
    assert [row["status"] for row in heartbeat_rows] == [
        "waiting",
        "waiting",
        "timed_out",
    ]
    assert any(row.get("waited_seconds", 0) >= 30 for row in heartbeat_rows)


def test_run_once_preserves_two_hour_child_within_five_hour_task_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _fixture_args(tmp_path, decision_date="2026-09-30")
    args.upstream_projection_wait_seconds = 1800
    _open_calendar(monkeypatch)
    observed_time = datetime(2026, 9, 30, 17, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    child_timeouts: list[int] = []

    def child(
        paths: operational.OperationalPaths,
        decision_date: date,
        scenario: object,
        child_args: Namespace,
    ) -> dict[str, object]:
        child_timeouts.append(child_args.child_timeout_seconds)
        return _successful_child(paths, decision_date, scenario, child_args)

    code, payload = operational.run_once(
        args,
        child_runner=child,
        task_state_reader=lambda: _producer_task_observation(
            datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc),
            state="Ready",
        ),
        monotonic=lambda: 100.0,
        now_provider=lambda: observed_time,
    )

    assert code == 0
    assert child_timeouts == [7200]
    assert payload["attempt_budget"]["total_limit_seconds"] == 18_000
    assert payload["attempt_budget"]["terminal_flush_reserve_seconds"] == 300
    assert payload["attempt_budget"]["effective_child_timeout_seconds"] == 7200
    assert payload["upstream_projection_wait"]["status"] == "upstream_not_running"


@pytest.mark.parametrize("terminal_case", ["timeout", "stopped"])
def test_run_once_wait_timeout_or_stopped_never_starts_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    terminal_case: str,
) -> None:
    args = _fixture_args(tmp_path, decision_date="2026-09-30")
    args.upstream_projection_wait_seconds = 5
    _open_calendar(monkeypatch)
    decision_date = date(2026, 9, 30)
    output_root = Path(args.snapshot_output_root).resolve()
    last_run = datetime(2026, 9, 30, 9, 0, tzinfo=timezone.utc)
    _write_producer_running_status(
        output_root,
        decision_date=decision_date,
        run_id=_producer_run_id(decision_date, last_run + timedelta(seconds=1)),
        last_run_time=last_run,
    )
    observations = [_producer_task_observation(last_run)] * 4
    if terminal_case == "stopped":
        observations[-1] = _producer_task_observation(last_run, state="Ready")
    child_calls: list[str] = []
    monotonic_now = [0.0]
    observed_time = last_run + timedelta(minutes=1)

    def task_reader() -> operational.ScheduledTaskObservation:
        return observations.pop(0) if len(observations) > 1 else observations[0]

    def fake_sleep(seconds: float) -> None:
        monotonic_now[0] += seconds

    def child(*_args: object) -> dict[str, object]:
        child_calls.append("started")
        return {}

    code, payload = operational.run_once(
        args,
        child_runner=child,
        task_state_reader=task_reader,
        monotonic=lambda: monotonic_now[0],
        sleep=fake_sleep,
        now_provider=lambda: observed_time,
    )

    expected_wait_status = "timed_out" if terminal_case == "timeout" else "upstream_stopped"
    expected_reason = (
        "recommendation_pipeline_wait_timeout"
        if terminal_case == "timeout"
        else "recommendation_pipeline_stopped_without_current_projection"
    )
    assert code == 2
    assert payload["status"] == "failed_dependency"
    assert payload["reason"] == expected_reason
    assert payload["upstream_projection_wait"]["status"] == expected_wait_status
    assert payload["child_invocation"] == "not_started"
    assert child_calls == []


def test_run_once_preserves_child_timeout_when_upstream_wait_fits_reserved_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _fixture_args(tmp_path, decision_date="2026-09-30")
    args.upstream_projection_wait_seconds = 1800
    _open_calendar(monkeypatch)
    decision_date = date(2026, 9, 30)
    output_root = Path(args.snapshot_output_root).resolve()
    last_run = datetime(2026, 9, 30, 9, 0, tzinfo=timezone.utc)
    current_run_id = _producer_run_id(decision_date, last_run + timedelta(seconds=1))
    _write_producer_running_status(
        output_root,
        decision_date=decision_date,
        run_id=current_run_id,
        last_run_time=last_run,
    )
    monotonic_now = [0.0]
    observed_time = last_run + timedelta(minutes=5)
    child_timeouts: list[int] = []

    def fake_sleep(_seconds: float) -> None:
        monotonic_now[0] += 125.0
        completed_at = last_run + timedelta(minutes=2)
        _write_producer_terminal_snapshot_source(
            args,
            run_id=current_run_id,
            completed_at=completed_at,
        )
        projection_path = (
            output_root
            / "scheduled"
            / "recommendation_calibration_learning"
            / "latest_snapshot_source_status.json"
        )
        projection_mtime = completed_at + timedelta(seconds=1)
        os.utime(
            projection_path,
            (projection_mtime.timestamp(), projection_mtime.timestamp()),
        )

    def child(
        paths: operational.OperationalPaths,
        decision_date: date,
        scenario: object,
        child_args: Namespace,
    ) -> dict[str, object]:
        child_timeouts.append(child_args.child_timeout_seconds)
        return _successful_child(paths, decision_date, scenario, child_args)

    code, payload = operational.run_once(
        args,
        child_runner=child,
        task_state_reader=lambda: _producer_task_observation(last_run),
        monotonic=lambda: monotonic_now[0],
        sleep=fake_sleep,
        now_provider=lambda: observed_time,
    )

    assert code == 0
    assert payload["upstream_projection_wait"]["status"] == "ready"
    assert payload["upstream_projection_wait"]["waited_seconds"] == 125.0
    # The 125-second wait consumes the dedicated upstream wait budget. The
    # original 2-hour child allowance still fits inside the 5-hour Task budget.
    assert child_timeouts == [7200]
    assert payload["attempt_budget"]["effective_child_timeout_seconds"] == 7200
    assert payload["attempt_budget"]["total_limit_seconds"] == 18_000


def test_upstream_wait_defaults_off_but_bank_wrapper_enables_fixed_cap() -> None:
    assert operational.build_parser().parse_args([]).upstream_projection_wait_seconds == 0
    wrapper = (
        Path(__file__).parents[1]
        / "scripts"
        / "scheduled"
        / "run_banktaiwan_recommendation_learning_daily.cmd"
    ).read_text(encoding="utf-8")
    assert 'set "BANKTAIWAN_UPSTREAM_PROJECTION_WAIT_SECONDS=10500"' in wrapper
    assert "--upstream-projection-wait-seconds" in wrapper
    assert operational._MAX_UPSTREAM_PROJECTION_WAIT_SECONDS == 10_500
    assert operational._BANK_TASK_EXECUTION_BUDGET_SECONDS == 5 * 60 * 60
    registration = (
        Path(__file__).parents[1]
        / "scripts"
        / "scheduled"
        / "register_banktaiwan_recommendation_learning_task.cmd"
    ).read_text(encoding="utf-8")
    assert "New-TimeSpan -Hours 5" in registration
