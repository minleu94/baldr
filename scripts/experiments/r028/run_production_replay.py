"""R028 named job production replay runner。

此 runner 以原凍結整份服務作 baseline，並透過正式 facade→job 呼叫 candidate。
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

from scripts.experiments.r027 import run_experiment as strict
from scripts.experiments.r027.worker import DIRECT_PATHS, R006_RAW_SHA256
from scripts.experiments.r028.worker import _method_ast_sha256


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
UPDATE_SERVICE_PATH = REPOSITORY_ROOT / "app_module" / "update_service.py"
TECHNICAL_INDICATOR_JOB_PATH = REPOSITORY_ROOT / "app_module" / "technical_indicator_job.py"
WORKER_PATH = Path(__file__).with_name("worker.py")
BASELINE_FIXTURE_ROOT = Path(__file__).parent / "frozen_baseline"
BASELINE_SOURCE_PATH = BASELINE_FIXTURE_ROOT / "app_module" / "update_service.py"
BASELINE_SOURCE_MANIFEST_PATH = BASELINE_FIXTURE_ROOT / "manifest.json"
BASELINE_SOURCE_SHA256 = (
    "sha256:697c3bd89aa256867f964e3cd01c253a28284f75a1c6d2d963354223e6daedec"
)
BASELINE_SOURCE_MANIFEST_SHA256 = (
    "sha256:36f65c3cf52943161ba613d32681657f697aa61bcea59b81a8b86dce5935a85f"
)
APPROVED_FACADE_SHA256 = (
    "sha256:27d0dd226ca8d9ac18b039a7778d74c5381b987f3d9f36b29053fa00175cf8b4"
)
APPROVED_JOB_SHA256 = (
    "sha256:77d34c79ff63ec82a928b7e62dfa0f8395ae9307f54723752d2c270ebf81c97e"
)
PINNED_FIXTURES = {
    "tests/fixtures/c1_cross_boundary/ab_interleave_scenarios.json": (
        "5112d36aafb67e323bb14759e7cfbda6b5d448cc8a008fd764d2ae63a7d500e3"
    ),
    "tests/fixtures/c1_consumer_readiness/r014_saved_execution.json": (
        "ebe481f425be3efa1c3635a71df5ba7c3e1b4054662b53fb980426fe79c11099"
    ),
    "tests/fixtures/c1_consumer_readiness/r016_legacy_run_zh.json": (
        "f625d43792688b35beb78ea1e93e965e79858ee94293c786351d6511f9de5552"
    ),
    "tests/fixtures/c1_consumer_readiness/ml_abi_manifest.json": (
        "c143b1c545319d2e3092e5d4a23ee45d86919be0093c8b889a5866a1e86b1f05"
    ),
    "tests/fixtures/c1_replay_bridge/r017_stored_annotation_snapshot.json": (
        "bea89c9d6e11e024a9a8481550e7161d1dc068b2e44a8db9038a130319215e3d"
    ),
}
SOURCE_CONTROL_IDS = (
    "delete_aggregate_csv_completed",
    "duplicate_run_started",
    "reorder_run_started_input_loaded",
)
DATABASE_CONTROL_ID = "main_db_user_version_mutation"
RECEIPT_CONTROL_IDS = (
    "artifact_bytes",
    "row_identity",
    "sqlite_visibility",
    "recovery_outcome",
)


def _build_replay_manifest(root: Path) -> tuple[Path, str, dict[str, Any]]:
    """以兩個已凍結 source 版本建立本次 worker 共用的不可變來源清單。"""

    static_raw = BASELINE_SOURCE_MANIFEST_PATH.read_bytes()
    static_sha256 = _sha256_bytes(static_raw)
    if static_sha256 != BASELINE_SOURCE_MANIFEST_SHA256:
        raise RuntimeError("R028 frozen baseline manifest hash mismatch")
    static_manifest = json.loads(static_raw.decode("utf-8"))
    baseline_record = static_manifest.get("baseline")
    candidate_method_reference = static_manifest.get("candidate_method_reference")
    approved = static_manifest.get("approved_r028_migration")
    if not all(isinstance(value, dict) for value in (baseline_record, approved)):
        raise RuntimeError("R028 pinned fixture manifest has an invalid schema")
    if not isinstance(candidate_method_reference, dict):
        raise RuntimeError("R028 pinned fixture lacks the approved job method AST")
    approved_facade = approved.get("facade")
    approved_job = approved.get("job")
    if not isinstance(approved_facade, dict) or not isinstance(approved_job, dict):
        raise RuntimeError("R028 pinned migration mapping is incomplete")

    baseline_source = (
        REPOSITORY_ROOT / str(baseline_record.get("source_path"))
    ).resolve(strict=True)
    facade_source = UPDATE_SERVICE_PATH.resolve(strict=True)
    job_source = TECHNICAL_INDICATOR_JOB_PATH.resolve(strict=True)
    observed_sources = {
        "baseline": _sha256_bytes(baseline_source.read_bytes()),
        "facade": _sha256_bytes(facade_source.read_bytes()),
        "job": _sha256_bytes(job_source.read_bytes()),
    }
    expected_sources = {
        "baseline": "sha256:" + str(baseline_record.get("source_sha256")),
        "facade": approved_facade.get("source_sha256"),
        "job": approved_job.get("source_sha256"),
    }
    if observed_sources != expected_sources:
        raise RuntimeError("R028 baseline/facade/job source hash differs from pinned map")
    baseline_method_ast = _method_ast_sha256(
        baseline_source,
        class_name="UpdateService",
        method_name="calculate_technical_indicators",
    )
    facade_method_ast = _method_ast_sha256(
        facade_source,
        class_name="UpdateService",
        method_name="calculate_technical_indicators",
    )
    job_method_ast = _method_ast_sha256(
        job_source,
        class_name="TechnicalIndicatorJob",
        method_name="run",
    )
    if baseline_method_ast != baseline_record.get("method_ast_sha256"):
        raise RuntimeError("R028 frozen baseline method AST differs from pinned map")
    if facade_method_ast != approved_facade.get("method_ast_sha256"):
        raise RuntimeError("R028 facade method AST differs from approved migration map")
    if job_method_ast != approved_job.get("method_ast_sha256"):
        raise RuntimeError("R028 production job method AST differs from approved map")
    if job_method_ast != candidate_method_reference.get("method_ast_sha256"):
        raise RuntimeError("R028 production job no longer matches frozen candidate method")

    replay_manifest: dict[str, Any] = {
        "schema": "r028-production-replay-provenance.v1",
        "baseline_source_manifest": {
            "path": str(BASELINE_SOURCE_MANIFEST_PATH.resolve(strict=True)),
            "sha256": static_sha256,
            "fixture_source_path": str(baseline_source),
            "fixture_source_sha256": observed_sources["baseline"],
        },
        "baseline": {
            "source_path": str(baseline_source),
            "source_sha256": observed_sources["baseline"],
            "module_name": baseline_record.get("module_name"),
            "owner_class": baseline_record.get("owner_class"),
            "method_name": baseline_record.get("method_name"),
            "method_ast_sha256": baseline_method_ast,
        },
        "candidate": {
            "facade_path": str(facade_source),
            "facade_sha256": observed_sources["facade"],
            "facade_module_name": approved_facade.get("module_name"),
            "facade_class_name": approved_facade.get("owner_class"),
            "facade_method_name": approved_facade.get("method_name"),
            "facade_method_ast_sha256": facade_method_ast,
            "job_path": str(job_source),
            "job_sha256": observed_sources["job"],
            "job_module_name": approved_job.get("module_name"),
            "job_class_name": approved_job.get("owner_class"),
            "job_method_name": approved_job.get("method_name"),
            "job_method_ast_sha256": job_method_ast,
            "port_names": approved_job.get("port_names"),
            "delegation": approved.get("delegation"),
        },
        "migration_map": {
            "static_manifest_path": str(BASELINE_SOURCE_MANIFEST_PATH.resolve()),
            "static_manifest_sha256": static_sha256,
            "frozen_baseline_module_loaded_as": "app_module.update_service",
            "production_candidate_entry": (
                "UpdateService.calculate_technical_indicators"
            ),
            "production_candidate_delegation": approved.get("delegation"),
            "job_writer_ownership": approved.get("writer_ownership"),
            "full_baseline_module_loaded_under_original_key": True,
            "candidate_called_through_production_facade": True,
            "method_ast_reference_sha256": candidate_method_reference.get(
                "method_ast_sha256"
            ),
        },
    }
    manifest_path = root / "r028_replay_provenance.json"
    manifest_raw = json.dumps(
        replay_manifest,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    manifest_path.write_bytes(manifest_raw)
    return manifest_path.resolve(), _sha256_bytes(manifest_raw), replay_manifest


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_sha256(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _git_path_list() -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=REPOSITORY_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "git ls-files failed while recording source scope: "
            + completed.stderr.decode("utf-8", errors="replace")
        )
    paths = {
        raw.decode("utf-8", errors="surrogateescape")
        for raw in completed.stdout.split(b"\0")
        if raw
    }
    return sorted(paths)


def _worktree_source_inventory() -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for relative in _git_path_list():
        path = REPOSITORY_ROOT / relative
        if path.is_symlink():
            target = os.readlink(path)
            raw = os.fsencode(target)
            records[relative] = {
                "kind": "symlink",
                "target": target,
                "size_bytes": len(raw),
                "sha256": _sha256_bytes(raw),
            }
            continue
        if not path.is_file():
            records[relative] = {"kind": "missing"}
            continue
        raw = path.read_bytes()
        records[relative] = {
            "kind": "file",
            "size_bytes": len(raw),
            "sha256": _sha256_bytes(raw),
        }
    return records


def _git_head_and_status() -> dict[str, Any]:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        text=True,
        encoding="utf-8",
    )
    status = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all"],
        cwd=REPOSITORY_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        text=True,
        encoding="utf-8",
    )
    if head.returncode != 0 or status.returncode != 0:
        raise RuntimeError("could not record git HEAD/status")
    return {
        "head": head.stdout.strip(),
        "status_lines": status.stdout.splitlines(),
        "status_sha256": _sha256_bytes(status.stdout.encode("utf-8")),
    }


def _direct_and_pinned_custody() -> dict[str, Any]:
    direct_files: list[dict[str, Any]] = []
    observed_direct_hashes: dict[str, str] = {}
    for relative in DIRECT_PATHS:
        path = REPOSITORY_ROOT / relative
        raw = path.read_bytes()
        digest = _sha256_bytes(raw)
        observed_direct_hashes[relative] = digest
        direct_files.append(
            {
                "path": relative,
                "size_bytes": len(raw),
                "sha256": digest,
                "expected_r006_sha256": R006_RAW_SHA256.get(relative),
            }
        )
    pinned_files: list[dict[str, Any]] = []
    for relative, expected in PINNED_FIXTURES.items():
        path = REPOSITORY_ROOT / relative
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        pinned_files.append(
            {
                "path": relative,
                "size_bytes": len(raw),
                "sha256": digest,
                "expected_sha256": expected,
                "matches_expected": digest == expected,
            }
        )
    return {
        "direct15": {
            "expected_paths": list(DIRECT_PATHS),
            "observed_paths": [item["path"] for item in direct_files],
            "files": direct_files,
            "all_match_r006_raw_sha256": observed_direct_hashes == R006_RAW_SHA256,
        },
        "pinned5": {
            "count": len(pinned_files),
            "files": pinned_files,
            "all_match_expected": all(
                item["matches_expected"] for item in pinned_files
            ),
        },
    }


def _source_scope_snapshot() -> dict[str, Any]:
    inventory = _worktree_source_inventory()
    return {
        "file_count": len(inventory),
        "inventory_sha256": _canonical_sha256(inventory),
        "files": inventory,
    }


def _make_phase_mutation(
    original_source: Path,
    destination: Path,
    control_id: str,
) -> dict[str, Any]:
    raw = original_source.read_bytes()
    text = raw.decode("utf-8")
    lines = text.splitlines(keepends=True)

    def indexes_for(phase: str) -> list[int]:
        expected = f'record_publication_phase("{phase}")'
        return [
            index
            for index, line in enumerate(lines)
            if line.strip() == expected
        ]

    if control_id == "delete_aggregate_csv_completed":
        indexes = indexes_for("aggregate_csv_write_completed")
        if len(indexes) != 1:
            raise RuntimeError("expected exactly one aggregate completion callsite")
        del lines[indexes[0]]
        mutated_phase = "aggregate_csv_write_completed"
        expected_baseline_count = 1
        expected_candidate_count = 0
        expected_order = None
    elif control_id == "duplicate_run_started":
        indexes = indexes_for("run_started")
        if len(indexes) != 1:
            raise RuntimeError("expected exactly one run_started callsite")
        lines.insert(indexes[0] + 1, lines[indexes[0]])
        mutated_phase = "run_started"
        expected_baseline_count = 1
        expected_candidate_count = 2
        expected_order = None
    elif control_id == "reorder_run_started_input_loaded":
        run_started = indexes_for("run_started")
        input_loaded = indexes_for("input_loaded")
        if len(run_started) != 1 or len(input_loaded) != 1:
            raise RuntimeError("expected unique run_started/input_loaded callsites")
        original_order: list[str] = []
        for line in lines:
            for name in ("run_started", "input_loaded"):
                if line.strip() == f'record_publication_phase("{name}")':
                    original_order.append(name)
        if original_order != ["run_started", "input_loaded"]:
            raise RuntimeError("phase source callsites no longer have expected order")
        lines[run_started[0]] = lines[run_started[0]].replace(
            '"run_started"', '"input_loaded"', 1
        )
        lines[input_loaded[0]] = lines[input_loaded[0]].replace(
            '"input_loaded"', '"run_started"', 1
        )
        mutated_phase = "run_started/input_loaded order"
        expected_baseline_count = 1
        expected_candidate_count = 1
        expected_order = ["input_loaded", "run_started"]
    else:
        raise ValueError(f"unsupported R027 phase control: {control_id}")

    mutated = "".join(lines).encode("utf-8")
    import ast

    ast.parse(mutated.decode("utf-8"), filename=str(destination))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(mutated)
    return {
        "control_id": control_id,
        "original_source_path": str(original_source.resolve()),
        "original_source_sha256": _sha256_bytes(raw),
        "mutated_source_path": str(destination.resolve()),
        "mutated_source_sha256": _sha256_bytes(mutated),
        "mutated_phase": mutated_phase,
        "expected_baseline_count": expected_baseline_count,
        "expected_candidate_count": expected_candidate_count,
        "expected_order": expected_order,
        "source_callsite_mutation_only": True,
        "candidate_outputs_expected_unchanged": True,
    }


def _entry_for_worker(worker: dict[str, Any], source_path: Path) -> dict[str, Any]:
    receipt_path = Path(str(worker["receipt_path"]))
    receipt = worker["receipt"]
    migration_provenance = receipt.get("r028_migration_provenance")
    return {
        "return_code": worker["return_code"],
        "receipt": receipt,
        "source_path": str(source_path.resolve()),
        "source_sha256": _sha256_bytes(source_path.read_bytes()),
        "command_argv": list(worker.get("command", [])),
        "manifest_path": worker["manifest_path"],
        "manifest_sha256": worker["manifest_sha256"],
        "role": worker["mode"],
        "loaded_module_evidence": migration_provenance,
        "delegation_evidence": (
            {
                "facade": migration_provenance.get("candidate", {}).get(
                    "facade_delegation_evidence"
                ),
                "job_load": migration_provenance.get("job_load_evidence"),
            }
            if isinstance(migration_provenance, dict)
            else None
        ),
        "receipt_path": str(receipt_path.resolve()),
        "receipt_sha256": worker.get("receipt_sha256"),
        "workspace": worker.get("workspace"),
        "stdout_path": worker.get("stdout_path"),
        "stderr_path": worker.get("stderr_path"),
    }


def _launch_worker(
    *,
    root: Path,
    context: dict[str, Any],
    case: str,
    mode: str,
    candidate_module: Path | None = None,
    source_control_id: str | None = None,
    mutate_user_version: bool = False,
) -> dict[str, Any]:
    workspace = root / "workers" / case / f"{mode}-{root.name}-" \
        f"{len(list((root / 'workers' / case).glob('*'))) if (root / 'workers' / case).exists() else 0}"
    workspace.mkdir(parents=True, exist_ok=False)
    receipt_path = root / "worker_receipts" / case / f"{workspace.name}.json"
    stdout_path = root / "logs" / case / f"{workspace.name}.stdout.txt"
    stderr_path = root / "logs" / case / f"{workspace.name}.stderr.txt"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_source = Path(str(context["baseline_source"]))
    candidate_facade = Path(str(context["candidate_facade"]))
    candidate_job_source = Path(str(context["candidate_job_source"]))
    replay_manifest_path = Path(str(context["replay_manifest_path"]))
    replay_manifest_sha256 = str(context["replay_manifest_sha256"])
    candidate_runtime_source = candidate_module or candidate_job_source
    command = [
        sys.executable,
        "-B",
        str(WORKER_PATH),
        "--mode",
        mode,
        "--case",
        case,
        "--workspace",
        str(workspace),
        "--replay-manifest",
        str(replay_manifest_path),
        "--replay-manifest-sha256",
        replay_manifest_sha256,
        "--baseline-source",
        str(baseline_source),
        "--candidate-facade",
        str(candidate_facade),
        "--candidate-facade-sha256",
        str(context["candidate_facade_sha256"]),
        "--candidate-job-source",
        str(candidate_job_source),
        "--candidate-job-source-sha256",
        str(context["candidate_job_source_sha256"]),
        "--source-variant",
        "original",
        "--observer-clock-mode",
        "deterministic",
        "--logical-phase-port",
        "--receipt",
        str(receipt_path),
    ]
    if mode == "candidate":
        command.extend(
            (
                "--candidate-module",
                str(candidate_runtime_source.resolve()),
                "--candidate-module-sha256",
                _sha256_bytes(candidate_runtime_source.read_bytes()),
            )
        )
        if source_control_id is not None:
            command.extend(("--source-control-id", source_control_id))
    if mutate_user_version:
        command.append("--mutate-temp-sqlite-user-version")

    env = strict.worker_environment(workspace)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    stdout_path.write_bytes(completed.stdout)
    stderr_path.write_bytes(completed.stderr)
    receipt: dict[str, Any] = {}
    if receipt_path.is_file():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    return {
        "mode": mode,
        "case": case,
        "manifest_path": str(replay_manifest_path.resolve()),
        "manifest_sha256": replay_manifest_sha256,
        "return_code": completed.returncode,
        "receipt_path": str(receipt_path.resolve()),
        "receipt_sha256": (
            _sha256_bytes(receipt_path.read_bytes()) if receipt_path.is_file() else None
        ),
        "stdout_path": str(stdout_path.resolve()),
        "stderr_path": str(stderr_path.resolve()),
        "workspace": str(workspace.resolve()),
        "command": command,
        "receipt": receipt,
    }


def _entry_for_mutated_receipt(
    *,
    original_entry: dict[str, Any],
    receipt: dict[str, Any],
    receipt_path: Path,
) -> dict[str, Any]:
    raw = json.dumps(
        receipt,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_bytes(raw)
    return {
        "return_code": original_entry["return_code"],
        "receipt": receipt,
        "source_path": original_entry["source_path"],
        "source_sha256": original_entry["source_sha256"],
        "command_argv": list(original_entry.get("command_argv", [])),
        "manifest_path": original_entry["manifest_path"],
        "manifest_sha256": original_entry["manifest_sha256"],
        "role": original_entry["role"],
        "loaded_module_evidence": original_entry["loaded_module_evidence"],
        "delegation_evidence": original_entry["delegation_evidence"],
        "receipt_path": str(receipt_path.resolve()),
        "receipt_sha256": _sha256_bytes(raw),
        "derived_from_receipt_path": original_entry["receipt_path"],
        "derived_from_receipt_sha256": original_entry["receipt_sha256"],
    }


def _logical_ports(receipt: dict[str, Any]) -> list[dict[str, Any]]:
    ports = receipt.get("logical_publication_phase_ports")
    if not isinstance(ports, dict):
        return []
    result: list[dict[str, Any]] = []
    for scenario_phase in ports:
        port = ports[scenario_phase]
        if isinstance(port, dict):
            result.extend(
                event
                for event in port.get("events", [])
                if isinstance(event, dict)
            )
    return result


def _build_source_controls(
    *,
    root: Path,
    context: dict[str, Any],
    baseline_entry: dict[str, Any],
    positive_candidate: dict[str, Any],
) -> dict[str, Any]:
    controls: dict[str, Any] = {}
    candidate_source = Path(str(context["candidate_job_source"]))
    original_events = _logical_ports(positive_candidate["receipt"])
    baseline_events = _logical_ports(baseline_entry["receipt"])
    for control_id in SOURCE_CONTROL_IDS:
        mutated_source = root / "source_mutations" / f"{control_id}.py"
        mutation = _make_phase_mutation(candidate_source, mutated_source, control_id)
        worker = _launch_worker(
            root=root,
            context=context,
            case="clean",
            mode="candidate",
            candidate_module=mutated_source,
            source_control_id=control_id,
        )
        mutated_entry = _entry_for_worker(worker, mutated_source)
        phase_name = mutation["mutated_phase"]
        if control_id == "reorder_run_started_input_loaded":
            original_order = [
                item["phase"]
                for item in original_events
                if item.get("phase") in {"run_started", "input_loaded"}
            ]
            baseline_order = [
                item["phase"]
                for item in baseline_events
                if item.get("phase") in {"run_started", "input_loaded"}
            ]
            if original_order != ["run_started", "input_loaded"]:
                raise RuntimeError("positive candidate phase order changed")
            if baseline_order != ["run_started", "input_loaded"]:
                raise RuntimeError("baseline phase order changed")
            mutated_order = [
                item.get("phase")
                for item in _logical_ports(mutated_entry["receipt"])
                if item.get("phase") in {"run_started", "input_loaded"}
            ]
            mutation["expected_order"] = ["input_loaded", "run_started"]
            mutation["expected_baseline_order"] = [
                "run_started",
                "input_loaded",
            ]
            mutation["observed_baseline_order"] = baseline_order
            mutation["observed_mutated_order"] = mutated_order
        else:
            observed_baseline_count = sum(
                item.get("phase") == phase_name for item in baseline_events
            )
            observed_original_candidate_count = sum(
                item.get("phase") == phase_name for item in original_events
            )
            if observed_baseline_count != mutation["expected_baseline_count"]:
                raise RuntimeError(
                    f"baseline phase count changed for {control_id}: "
                    f"{observed_baseline_count}"
                )
            if observed_original_candidate_count != mutation["expected_baseline_count"]:
                raise RuntimeError(
                    f"positive candidate phase count changed for {control_id}: "
                    f"{observed_original_candidate_count}"
                )
            mutation["observed_baseline_count"] = sum(
                item.get("phase") == phase_name for item in baseline_events
            )
            mutation["observed_original_candidate_count"] = (
                observed_original_candidate_count
            )
            mutation["observed_mutated_count"] = sum(
                item.get("phase") == phase_name
                for item in _logical_ports(mutated_entry["receipt"])
            )
        controls[control_id] = {
            "source_case": "clean",
            "original_entry": positive_candidate,
            "mutated_entry": mutated_entry,
            "source_mutation": mutation,
        }
    return controls


def _build_database_control(
    *,
    root: Path,
    context: dict[str, Any],
    positive_candidate: dict[str, Any],
) -> dict[str, Any]:
    worker = _launch_worker(
        root=root,
        context=context,
        case="clean",
        mode="candidate",
        mutate_user_version=True,
    )
    mutated_entry = _entry_for_worker(
        worker,
        Path(str(context["candidate_job_source"])),
    )
    mutation = mutated_entry["receipt"].get("logical_main_db_mutation")
    if not isinstance(mutation, dict):
        raise RuntimeError("SQLite user_version worker did not record mutation evidence")
    return {
        DATABASE_CONTROL_ID: {
            "source_case": "clean",
            "original_entry": positive_candidate,
            "mutated_entry": mutated_entry,
            "database_mutation": {
                "operation": mutation.get("operation"),
                "database_workspace_relative_path": mutation.get(
                    "database_workspace_relative_path"
                ),
                "old_user_version": mutation.get("old_user_version"),
                "mutated_user_version": mutation.get("mutated_user_version"),
                "readback_user_version": mutation.get("readback_user_version"),
                "connection_closed": mutation.get("connection_closed"),
                "before_main_database": mutation.get("before_main_database"),
                "after_main_database": mutation.get("after_main_database"),
                "application_tables_unchanged": mutation.get(
                    "application_tables_unchanged"
                ),
                "actual_final_phase_main_database": (
                    (mutated_entry["receipt"].get("final_outputs") or {}).get(
                        "sqlite_main_db_before_checkpoint"
                    )
                ),
                "source_path": mutated_entry["source_path"],
                "source_sha256": mutated_entry["source_sha256"],
                "expected_product_phase_calls_unchanged": True,
            },
        }
    }


def _find_first_artifact_file(
    receipt: dict[str, Any],
) -> tuple[dict[str, Any], str, list[str | int]]:
    for phase_index, phase in enumerate(receipt.get("phases", [])):
        outputs = phase.get("outputs") or {}
        files = outputs.get("files") or {}
        if files:
            key = sorted(files)[0]
            return files[key], key, ["phases", phase_index, "outputs", "files", key]
    files = (receipt.get("final_outputs") or {}).get("files") or {}
    if files:
        key = sorted(files)[0]
        return files[key], key, ["final_outputs", "files", key]
    raise RuntimeError("clean positive worker has no output artifact file to mutate")


def _mutate_receipt_field(
    *,
    control_id: str,
    receipt: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    mutated = copy.deepcopy(receipt)
    if control_id == "artifact_bytes":
        details, relative_path, artifact_tokens = _find_first_artifact_file(mutated)
        before = details.get("sha256")
        if not isinstance(before, str) or not before.startswith("sha256:"):
            raise RuntimeError("artifact mutation target lacks a readable SHA")
        details["sha256"] = "sha256:" + "0" * 64
        metadata = {
            "mutation_path": f"artifact_file_sha256[{relative_path}]",
            "mutation_paths": [artifact_tokens + ["sha256"]],
            "before_value": before,
            "after_value": details["sha256"],
        }
    elif control_id == "row_identity":
        phase = (mutated.get("phases") or [])[0]
        logical = phase["outputs"]["logical_sqlite_snapshot"]
        readers = logical["fresh_readers"]
        if len(readers) != 2:
            raise RuntimeError("daily_prices receipt lacks two fresh readers")
        before_symbol: str | None = None
        symbol_index: int | None = None
        name_index: int | None = None
        for reader in readers:
            source = reader["daily_prices_source"]
            columns = [item["name"] for item in source["table_columns"]]
            current_symbol_index = columns.index("證券代號")
            current_name_index = columns.index("證券名稱") if "證券名稱" in columns else None
            if symbol_index is not None and current_symbol_index != symbol_index:
                raise RuntimeError("fresh readers have different daily_prices column order")
            if name_index is not None and current_name_index != name_index:
                raise RuntimeError("fresh readers have different daily_prices column order")
            symbol_index = current_symbol_index
            name_index = current_name_index
            if not source["rows"]:
                raise RuntimeError("daily_prices receipt has no row identity to mutate")
            previous_symbol = source["rows"][0][current_symbol_index].get("value")
            if not isinstance(previous_symbol, str):
                raise RuntimeError("daily_prices first symbol is not text")
            if source["rows"][0][current_symbol_index].get("type") != "text":
                raise RuntimeError("daily_prices first symbol has an unexpected type")
            if previous_symbol == "00999":
                raise RuntimeError("row-identity mutation target is already present")
            source["rows"][0][current_symbol_index] = {
                "type": "text",
                "value": "00999",
            }
            if current_name_index is not None:
                source["rows"][0][current_name_index] = {
                    "type": "text",
                    "value": "fixture-00999",
                }
            source["row_keys"][0][0] = {"type": "text", "value": "00999"}
            source["rows_sha256"] = _canonical_sha256(source["rows"])
            source["row_keys_sha256"] = _canonical_sha256(source["row_keys"])
            if reader is readers[0]:
                before_symbol = previous_symbol
            elif previous_symbol != before_symbol:
                raise RuntimeError("fresh readers have different original row identity")
        if before_symbol is None:
            raise RuntimeError("daily_prices row identity was not mutated")
        if symbol_index is None:
            raise RuntimeError("daily_prices symbol column was not identified")
        mutation_paths: list[list[str | int]] = []
        for reader_index in range(2):
            source_prefix: list[str | int] = [
                "phases",
                0,
                "outputs",
                "logical_sqlite_snapshot",
                "fresh_readers",
                reader_index,
                "daily_prices_source",
            ]
            mutation_paths.extend(
                [
                    source_prefix + ["rows", 0, symbol_index],
                    source_prefix + ["row_keys", 0, 0],
                    source_prefix + ["rows_sha256"],
                    source_prefix + ["row_keys_sha256"],
                ]
            )
            if name_index is not None:
                mutation_paths.append(source_prefix + ["rows", 0, name_index])
        metadata = {
            "mutation_path": "phases[0].outputs.logical_sqlite_snapshot.fresh_readers[*].daily_prices_source.rows[0].證券代號",
            "mutation_paths": mutation_paths,
            "before_value": before_symbol,
            "after_value": "00999",
            "symbol_index": symbol_index,
            "name_index": name_index,
            "both_fresh_readers_updated_consistently": True,
        }
    elif control_id == "sqlite_visibility":
        phase = (mutated.get("phases") or [])[0]
        logical = phase["outputs"]["logical_sqlite_snapshot"]
        readers = logical["fresh_readers"]
        if len(readers) != 2:
            raise RuntimeError("technical receipt lacks two fresh readers")
        columns = [item["name"] for item in readers[0]["table_columns"]]
        if "RSI" not in columns:
            raise RuntimeError("technical reader lacks the RSI column")
        value_index = columns.index("RSI")
        selected_row_index: int | None = None
        before_hex: str | None = None
        for row_index, row in enumerate(readers[0]["rows"]):
            if value_index >= len(row):
                continue
            cell = row[value_index]
            if cell.get("type") != "real":
                continue
            hex_value = cell.get("hex")
            if not isinstance(hex_value, str):
                continue
            numeric_value = float.fromhex(hex_value)
            if math.isfinite(numeric_value):
                selected_row_index = row_index
                before_hex = hex_value
                break
        if selected_row_index is None or before_hex is None:
            raise RuntimeError("technical receipt has no finite real RSI value")
        replacement = float.fromhex(before_hex) + 1.0
        for reader in readers:
            if [item["name"] for item in reader["table_columns"]] != columns:
                raise RuntimeError("fresh reader schema changed before mutation")
            row = reader["rows"][selected_row_index]
            if row[value_index].get("type") != "real":
                raise RuntimeError("fresh reader RSI primitive type differs")
            row[value_index] = {"type": "real", "hex": replacement.hex()}
            reader["rows_sha256"] = _canonical_sha256(reader["rows"])
        mutation_paths = []
        for reader_index in range(2):
            reader_prefix: list[str | int] = [
                "phases",
                0,
                "outputs",
                "logical_sqlite_snapshot",
                "fresh_readers",
                reader_index,
            ]
            mutation_paths.extend(
                [
                    reader_prefix + ["rows", selected_row_index, value_index],
                    reader_prefix + ["rows_sha256"],
                ]
            )
        metadata = {
            "mutation_path": (
                "phases[0].outputs.logical_sqlite_snapshot.fresh_readers[*].rows"
                f"[{selected_row_index}].RSI"
            ),
            "mutation_paths": mutation_paths,
            "column": "RSI",
            "row_index": selected_row_index,
            "before_hex": before_hex,
            "after_hex": replacement.hex(),
            "both_fresh_readers_updated_consistently": True,
        }
    elif control_id == "recovery_outcome":
        phases = mutated.get("phases") or []
        target_index = next(
            (
                index
                for index, item in enumerate(phases)
                if item.get("label") == "calculation_failure_recovery"
            ),
            None,
        )
        target = phases[target_index] if target_index is not None else None
        if (
            target_index is None
            or target is None
            or not isinstance(target.get("result"), dict)
        ):
            raise RuntimeError("failure recovery case lacks its recovery result")
        previous = target["result"].get("success")
        if type(previous) is not bool:
            raise RuntimeError("recovery result success is not a boolean")
        target["result"]["success"] = not previous
        metadata = {
            "mutation_path": "phases[calculation_failure_recovery].result.success",
            "mutation_paths": [["phases", target_index, "result", "success"]],
            "before_value": previous,
            "after_value": not previous,
        }
    else:
        raise ValueError(f"unsupported receipt field control: {control_id}")
    return mutated, metadata


def _build_receipt_field_controls(
    *,
    root: Path,
    workers: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    controls: dict[str, Any] = {}
    source_cases = {
        "artifact_bytes": "clean",
        "row_identity": "clean",
        "sqlite_visibility": "clean",
        "recovery_outcome": "failure_recovery",
    }
    for control_id in RECEIPT_CONTROL_IDS:
        source_case = source_cases[control_id]
        original_entry = workers[source_case]["candidate"]
        mutated_receipt, mutation = _mutate_receipt_field(
            control_id=control_id,
            receipt=original_entry["receipt"],
        )
        derived_path = root / "receipt_field_mutations" / f"{control_id}.json"
        mutated_entry = _entry_for_mutated_receipt(
            original_entry=original_entry,
            receipt=mutated_receipt,
            receipt_path=derived_path,
        )
        controls[control_id] = {
            "source_case": source_case,
            "source_mode": "candidate",
            "original_entry": original_entry,
            "mutated_entry": mutated_entry,
            "mutation_path": mutation["mutation_path"],
            "mutation_paths": mutation["mutation_paths"],
            "before_canonical_sha256": _canonical_sha256(original_entry["receipt"]),
            "after_canonical_sha256": _canonical_sha256(mutated_receipt),
            "expected_verdict": "FAIL",
            "mutation": mutation,
        }
    return controls


def _run_workers(root: Path, context: dict[str, Any]) -> dict[str, Any]:
    workers: dict[str, dict[str, dict[str, Any]]] = {}
    for case in strict.CASES:
        workers[case] = {}
        for mode in ("baseline", "candidate"):
            worker = _launch_worker(
                root=root,
                context=context,
                case=case,
                mode=mode,
            )
            actual_source = (
                Path(str(context["baseline_source"]))
                if mode == "baseline"
                else Path(str(context["candidate_job_source"]))
            )
            workers[case][mode] = _entry_for_worker(worker, actual_source)
    return workers


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.temp_parent).expanduser().resolve() / args.run_name
    if root.exists():
        raise FileExistsError(f"R028 production replay root already exists: {root}")
    strict.assert_isolated_root(root)
    root.mkdir(parents=True, exist_ok=False)

    before_git = _git_head_and_status()
    before_scope = _source_scope_snapshot()
    before_custody = _direct_and_pinned_custody()
    replay_manifest_path, replay_manifest_sha256, replay_manifest = (
        _build_replay_manifest(root)
    )
    context: dict[str, Any] = {
        "replay_manifest_path": str(replay_manifest_path),
        "replay_manifest_sha256": replay_manifest_sha256,
        "baseline_source": str(BASELINE_SOURCE_PATH.resolve(strict=True)),
        "candidate_facade": str(UPDATE_SERVICE_PATH.resolve(strict=True)),
        "candidate_facade_sha256": APPROVED_FACADE_SHA256,
        "candidate_job_source": str(TECHNICAL_INDICATOR_JOB_PATH.resolve(strict=True)),
        "candidate_job_source_sha256": APPROVED_JOB_SHA256,
    }

    by_case = _run_workers(root, context)
    source_controls = _build_source_controls(
        root=root,
        context=context,
        baseline_entry=by_case["clean"]["baseline"],
        positive_candidate=by_case["clean"]["candidate"],
    )
    database_controls = _build_database_control(
        root=root,
        context=context,
        positive_candidate=by_case["clean"]["candidate"],
    )
    receipt_field_controls = _build_receipt_field_controls(
        root=root,
        workers=by_case,
    )

    comparisons = {
        case: strict.compare_workers(
            case_workers["baseline"], case_workers["candidate"]
        )
        for case, case_workers in by_case.items()
    }
    old_strict_controls = strict.validate_negative_controls(
        by_case["clean"]["baseline"]["receipt"]
    )
    old_strict_verdict = strict.strict_gate_verdict(
        strict.CASES,
        comparisons,
        old_strict_controls,
    )
    gate_workers = {
        "selected_cases": list(strict.CASES),
        "by_case": by_case,
    }
    negative_controls = {
        "source_controls": source_controls,
        "database_controls": database_controls,
        "receipt_field_mutation_controls": receipt_field_controls,
    }
    gate_manifest = {
        **replay_manifest,
        "path": str(replay_manifest_path),
        "sha256": replay_manifest_sha256,
    }
    gate_input = {
        "schema": "r028-production-logical-time-gate-input.v1",
        "manifest": gate_manifest,
        "workers": gate_workers,
        "negative_controls": negative_controls,
    }
    gate_input_path = root / "r028_logical_time_gate_input.json"
    gate_input_bytes = json.dumps(
        gate_input,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    gate_input_path.write_bytes(gate_input_bytes)

    try:
        from scripts.experiments.r028.logical_time_gate import (
            evaluate_r028_logical_time_revision,
        )
    except ImportError as exc:
        raise RuntimeError("R028 independent gate module is not available") from exc

    logical_gate_result = evaluate_r028_logical_time_revision(gate_input)
    gate_verdict = (
        logical_gate_result.get("verdict")
        if isinstance(logical_gate_result, dict)
        else None
    )
    if gate_verdict not in {"PASS", "FAIL", "INCONCLUSIVE"}:
        gate_verdict = "INCONCLUSIVE"

    after_git = _git_head_and_status()
    after_scope = _source_scope_snapshot()
    after_custody = _direct_and_pinned_custody()
    scope_differences = strict.collect_exact_differences(
        before_scope["files"], after_scope["files"]
    )
    custody_stable = (
        before_custody == after_custody
        and before_custody["direct15"]["all_match_r006_raw_sha256"]
        and before_custody["pinned5"]["all_match_expected"]
        and after_custody["direct15"]["all_match_r006_raw_sha256"]
        and after_custody["pinned5"]["all_match_expected"]
    )
    migration_source_hashes_after = {
        "static_manifest": _sha256_bytes(BASELINE_SOURCE_MANIFEST_PATH.read_bytes()),
        "baseline_source": _sha256_bytes(BASELINE_SOURCE_PATH.read_bytes()),
        "candidate_facade": _sha256_bytes(UPDATE_SERVICE_PATH.read_bytes()),
        "candidate_job": _sha256_bytes(TECHNICAL_INDICATOR_JOB_PATH.read_bytes()),
    }
    migration_source_hashes_before = {
        "static_manifest": replay_manifest["baseline_source_manifest"]["sha256"],
        "baseline_source": replay_manifest["baseline"]["source_sha256"],
        "candidate_facade": replay_manifest["candidate"]["facade_sha256"],
        "candidate_job": replay_manifest["candidate"]["job_sha256"],
    }
    runner_integrity_checks = {
        "source_scope_stable": not scope_differences,
        "git_head_unchanged": before_git["head"] == after_git["head"],
        "git_status_unchanged": before_git["status_lines"] == after_git["status_lines"],
        "direct15_and_pinned5_stable": custody_stable,
        "pinned_migration_sources_stable": (
            migration_source_hashes_before == migration_source_hashes_after
        ),
        "replay_manifest_unchanged": (
            _sha256_bytes(replay_manifest_path.read_bytes())
            == replay_manifest_sha256
        ),
    }
    runner_integrity_passed = all(runner_integrity_checks.values())
    if gate_verdict == "PASS" and not runner_integrity_passed:
        runner_verdict = "FAIL"
    else:
        runner_verdict = gate_verdict
    return {
        "schema": "r028-production-logical-time-replay-runner.v1",
        "run_name": args.run_name,
        "run_root": str(root.resolve()),
        "repository_root": str(REPOSITORY_ROOT),
        "python_executable": sys.executable,
        "selected_cases": list(strict.CASES),
        "migration_provenance": replay_manifest,
        "migration_manifest_path": str(replay_manifest_path),
        "migration_manifest_sha256": replay_manifest_sha256,
        "legacy_strict_comparison_diagnostic": {
            "verdict": old_strict_verdict,
            "comparisons": comparisons,
            "baseline_negative_controls": old_strict_controls,
            "interpretation": (
                "此欄只記舊 comparator 對本次 baseline/candidate 的診斷；"
                "不覆寫既有 R027 strict 歷史收據或其 INCONCLUSIVE 狀態。"
            ),
        },
        "r028_logical_time_replay": {
            "verdict": runner_verdict,
            "gate_verdict": gate_verdict,
            "gate_result": logical_gate_result,
            "runner_integrity_checks": runner_integrity_checks,
            "runner_integrity_passed": runner_integrity_passed,
            "gate_input_path": str(gate_input_path.resolve()),
            "gate_input_sha256": _sha256_bytes(gate_input_bytes),
            "gate_input_schema": gate_input["schema"],
            "migration_source_hashes_before": migration_source_hashes_before,
            "migration_source_hashes_after": migration_source_hashes_after,
            "acceptance_limits": {
                "raw_os_clock_observations_retained": True,
                "file_mtime_wal_shm_retained": True,
                "main_database_bytes_exact_at_original_snapshot_phases": True,
                "no_product_timestamp_or_schema_added": True,
                "baseline_and_candidate_are_independent_source_graphs": True,
                "candidate_uses_production_facade_and_named_job": True,
                "full_acceptance_requires_boundary_and_root_review": True,
            },
        },
        "source_scope_before": before_scope,
        "source_scope_after": after_scope,
        "source_scope_stable": not scope_differences,
        "source_scope_differences": scope_differences,
        "git_before": before_git,
        "git_after": after_git,
        "git_head_unchanged": before_git["head"] == after_git["head"],
        "git_status_unchanged": before_git["status_lines"] == after_git["status_lines"],
        "custody_before": before_custody,
        "custody_after": after_custody,
        "direct15_and_pinned5_stable": custody_stable,
        "formal_data_touched": False,
        "production_source_write_performed": False,
        "r028_full_replay_accepted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--temp-parent", default=tempfile.gettempdir())
    parser.add_argument(
        "--run-name",
        default="r028-production-replay-" + next(tempfile._get_candidate_names()),
    )
    parser.add_argument("--receipt", default="")
    args = parser.parse_args()
    result = run(args)
    root = Path(result["run_root"])
    receipt_path = (
        Path(args.receipt).expanduser().resolve()
        if args.receipt
        else root / "r028_production_replay.json"
    )
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(
        result,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    receipt_path.write_bytes(raw)
    print(
        json.dumps(
            {
                "legacy_strict_diagnostic": result["legacy_strict_comparison_diagnostic"]["verdict"],
                "r028_replay_verdict": result["r028_logical_time_replay"]["verdict"],
                "receipt": str(receipt_path),
                "run_root": str(root),
                "cases": result["selected_cases"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result["r028_logical_time_replay"]["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
