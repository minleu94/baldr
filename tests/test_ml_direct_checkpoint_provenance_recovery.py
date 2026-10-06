from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from data_module import portfolio_ml_direct_numeric_store as direct_store
from scripts import continue_ml_direct_ooc_after_store as ooc_continuation


def _dependencies() -> tuple[dict[str, Any], str]:
    payload = direct_store._direct_computation_dependency_payload()
    return payload, direct_store._sha256_json(payload)


def _checkpoint_base(run_id: str) -> dict[str, Any]:
    return {
        "schema_version": direct_store.DIRECT_CHECKPOINT_SCHEMA_VERSION,
        "run_id": run_id,
        "raw_manifest_hash": "sha256:" + "a" * 64,
        "completed_years": [],
        "peak_temporary_bytes": 0,
        "complete": False,
    }


def test_stable_computation_identity_excludes_runtime_state() -> None:
    dependencies, _dependency_hash = _dependencies()
    baseline = direct_store._stable_direct_computation_identity_hash(
        dependencies
    )
    changed = copy.deepcopy(dependencies)
    for item in changed["files"]:
        item["loaded_module"] = "runtime.reloaded.module"
        item["loaded_code_fingerprint"] = "sha256:" + "b" * 64
        item["loaded_code_matches_source"] = False
        item["loaded_constants"] = {"runtime_nonce": "different"}
    assert (
        direct_store._stable_direct_computation_identity_hash(changed)
        == baseline
    )


def test_legacy_complete_checkpoint_is_audit_only_and_not_rehashed(
    tmp_path: Path,
) -> None:
    dependencies, _dependency_hash = _dependencies()
    root = tmp_path / "direct-store"
    run_directory = root / "runs" / "legacy-run"
    run_directory.mkdir(parents=True)
    checkpoint_path = run_directory / "checkpoint.json"
    checkpoint = {
        **_checkpoint_base("legacy-run"),
        "complete": True,
        "completed_years": [{"year": 2024}],
    }
    checkpoint_path.write_text(
        json.dumps(checkpoint, sort_keys=True),
        encoding="utf-8",
    )
    manifest = {"schema_version": "legacy", "status": "complete"}
    manifest["manifest_hash"] = direct_store._sha256_json(manifest)
    (run_directory / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True),
        encoding="utf-8",
    )
    before = checkpoint_path.read_bytes()

    plan = direct_store.inspect_direct_checkpoint_provenance(
        root,
        current_computation_dependencies=dependencies,
    )

    record = plan["runs"][0]
    assert plan["status"] == "blocked_legacy_provenance"
    assert plan["automatic_recovery_allowed"] is False
    assert record["provenance_classification"] == (
        "legacy_missing_computation_provenance"
    )
    assert record["resume_allowed"] is False
    assert record["checkpoint_complete"] is True
    assert record["manifest_status"] == "complete"
    assert record["manifest_hash_valid"] is True
    assert checkpoint_path.read_bytes() == before
    reread = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert "computation_identity_hash" not in reread


def test_stable_identity_drift_is_not_misclassified_as_legacy(
    tmp_path: Path,
) -> None:
    dependencies, _dependency_hash = _dependencies()
    changed = copy.deepcopy(dependencies)
    changed["files"][0]["sha256"] = "sha256:" + "c" * 64
    stored_identity = direct_store._stable_direct_computation_identity_payload(
        changed
    )
    stored_identity_hash = direct_store._sha256_json(stored_identity)
    stored_dependency_hash = direct_store._sha256_json(changed)
    root = tmp_path / "direct-store"
    run_directory = root / "runs" / "drift-run"
    run_directory.mkdir(parents=True)
    checkpoint_path = run_directory / "checkpoint.json"
    checkpoint_path.write_text(
        json.dumps(
            {
                **_checkpoint_base("drift-run"),
                "computation_identity_hash": stored_identity_hash,
                "computation_identity": stored_identity,
                "computation_dependency_hash": stored_dependency_hash,
                "computation_dependencies": changed,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    plan = direct_store.inspect_direct_checkpoint_provenance(
        root,
        current_computation_dependencies=dependencies,
    )

    record = plan["runs"][0]
    assert plan["status"] == "blocked_computation_identity_drift"
    assert record["provenance_classification"] == "computation_identity_drift"
    assert record["resume_allowed"] is False
    assert "legacy_missing" not in record["provenance_classification"]


def test_current_checkpoint_is_only_resume_candidate_after_full_readback(
    tmp_path: Path,
) -> None:
    dependencies, dependency_hash = _dependencies()
    root = tmp_path / "direct-store"
    run_directory = root / "runs" / "current-run"
    run_directory.mkdir(parents=True)
    checkpoint_path = run_directory / "checkpoint.json"
    direct_store._write_incomplete_checkpoint(
        checkpoint_path=checkpoint_path,
        run_id="current-run",
        raw_manifest_hash="sha256:" + "a" * 64,
        computation_dependency_hash=dependency_hash,
        computation_dependencies=dependencies,
        completed={},
        peak_temporary_bytes=0,
    )

    plan = direct_store.inspect_direct_checkpoint_provenance(
        root,
        current_computation_dependencies=dependencies,
    )

    record = plan["runs"][0]
    assert plan["status"] == "ready_for_root_review"
    assert record["provenance_classification"] == (
        "resumable_under_current_computation_identity"
    )
    assert record["resume_allowed"] is True
    assert plan["recovery_policy"]["new_run"].startswith(
        "for legacy or drifted artifacts"
    )


def test_lock_custody_probe_is_read_only_and_retains_hashes(
    tmp_path: Path,
) -> None:
    release_root = tmp_path / "release_v4"
    store_root = release_root / "direct-store"
    store_root.mkdir(parents=True)
    lock_path = release_root / ".ml_heavy_chain.lock"
    lock_path.write_bytes(b"ml_heavy_chain_lock.v1\n")
    maintenance_root = release_root / "ooc-training"

    before = lock_path.read_bytes()
    custody = direct_store.inspect_direct_heavy_chain_custody(
        store_root,
        maintenance_output_dir=maintenance_root,
    )

    canonical = custody["canonical_lock"]
    assert custody["read_only"] is True
    assert custody["status"] == "no_active_lock_observed"
    assert canonical["probe_stage"] == "advisory_lock"
    assert canonical["status"] == "free_observed"
    assert canonical["read_open"] is True
    assert canonical["lock_acquired"] is True
    assert canonical["bytes_unchanged"] is True
    assert canonical["file_hash_before"] == canonical["file_hash_after"]
    assert canonical["errno"] is None
    assert canonical["winerror"] is None
    assert lock_path.read_bytes() == before
    assert not (maintenance_root / ".ml_direct_chain_maintenance.lock").exists()


def test_lock_custody_changed_bytes_cannot_aggregate_as_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release_root = tmp_path / "release_v4"
    store_root = release_root / "direct-store"
    store_root.mkdir(parents=True)
    lock_path = release_root / ".ml_heavy_chain.lock"
    lock_path.write_bytes(b"ml_heavy_chain_lock.v1\n")
    real_file_sha256 = direct_store._file_sha256
    calls = 0

    def changing_file_sha256(path: Path) -> str:
        nonlocal calls
        if path.resolve() == lock_path.resolve():
            calls += 1
            return "sha256:" + ("a" if calls == 1 else "b") * 64
        return real_file_sha256(path)

    monkeypatch.setattr(
        direct_store,
        "_file_sha256",
        changing_file_sha256,
    )
    custody = direct_store.inspect_direct_heavy_chain_custody(store_root)

    assert custody["canonical_lock"]["status"] == "probe_file_changed"
    assert custody["canonical_lock"]["bytes_unchanged"] is False
    assert custody["status"] == "probe_file_changed"
    assert custody["status"] != "no_active_lock_observed"


def test_lock_custody_gate_enumeration_failure_is_incomplete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release_root = tmp_path / "release_v4"
    store_root = release_root / "direct-store"
    store_root.mkdir(parents=True)
    (release_root / ".ml_heavy_chain.lock").write_bytes(
        b"ml_heavy_chain_lock.v1\n"
    )
    real_glob = Path.glob

    def failing_glob(path: Path, pattern: str) -> Any:
        if pattern.startswith(".ml_heavy_chain.lock.handoff."):
            raise OSError(13, "synthetic gate enumeration denial")
        return real_glob(path, pattern)

    monkeypatch.setattr(Path, "glob", failing_glob)
    custody = direct_store.inspect_direct_heavy_chain_custody(store_root)

    assert custody["handoff_gate_count"] == 0
    assert custody["handoff_gate_discovery"]["status"] == "incomplete"
    assert custody["handoff_gate_discovery"]["error"]["errno"] == 13
    assert custody["status"] == "handoff_gate_enumeration_incomplete"
    assert custody["status"] != "no_active_lock_observed"


def test_manifest_custody_failure_blocks_full_resume_but_keeps_checkpoint_readback(
    tmp_path: Path,
) -> None:
    dependencies, dependency_hash = _dependencies()
    identity = direct_store._stable_direct_computation_identity_payload(
        dependencies
    )
    identity_hash = direct_store._sha256_json(identity)
    root = tmp_path / "direct-store"
    run_directory = root / "runs" / "manifest-run"
    run_directory.mkdir(parents=True)
    checkpoint_path = run_directory / "checkpoint.json"
    direct_store._write_incomplete_checkpoint(
        checkpoint_path=checkpoint_path,
        run_id="manifest-run",
        raw_manifest_hash="sha256:" + "a" * 64,
        computation_dependency_hash=dependency_hash,
        computation_dependencies=dependencies,
        completed={},
        peak_temporary_bytes=0,
    )
    manifest_path = run_directory / "manifest.json"
    manifest_path.write_text("{broken json", encoding="utf-8")

    plan = direct_store.inspect_direct_checkpoint_provenance(
        root,
        current_computation_dependencies=dependencies,
    )

    record = plan["runs"][0]
    assert plan["status"] == "blocked_checkpoint_provenance"
    assert record["checkpoint_provenance_valid"] is True
    assert record["checkpoint_resume_allowed"] is True
    assert record["resume_allowed"] is False
    assert record["full_resume_classification"] == "manifest_custody_invalid"
    assert record["provenance_classification"] == "manifest_custody_invalid"
    assert record["manifest_hash_valid"] is False
    assert record["manifest_custody_valid"] is False
    assert isinstance(record["manifest_file_hash"], str)
    assert record["manifest_file_hash"].startswith("sha256:")
    assert identity_hash == plan["current_computation_identity_hash"]


def test_manifest_tamper_or_identity_mismatch_blocks_full_resume(
    tmp_path: Path,
) -> None:
    dependencies, dependency_hash = _dependencies()
    identity = direct_store._stable_direct_computation_identity_payload(
        dependencies
    )
    identity_hash = direct_store._sha256_json(identity)
    for case in ("tampered", "identity_mismatch"):
        root = tmp_path / case
        run_directory = root / "runs" / case
        run_directory.mkdir(parents=True)
        direct_store._write_incomplete_checkpoint(
            checkpoint_path=run_directory / "checkpoint.json",
            run_id=case,
            raw_manifest_hash="sha256:" + "a" * 64,
            computation_dependency_hash=dependency_hash,
            computation_dependencies=dependencies,
            completed={},
            peak_temporary_bytes=0,
        )
        manifest: dict[str, Any] = {
            "schema_version": direct_store.store_module.STORE_SCHEMA_VERSION,
            "status": "complete",
            "run_id": case,
            "store_identity": {
                "computation_identity_hash": (
                    identity_hash
                    if case == "tampered"
                    else "sha256:" + "f" * 64
                )
            },
        }
        manifest["manifest_hash"] = direct_store._sha256_json(manifest)
        manifest_path = run_directory / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, sort_keys=True),
            encoding="utf-8",
        )
        if case == "tampered":
            manifest["status"] = "blocked"
            manifest_path.write_text(
                json.dumps(manifest, sort_keys=True),
                encoding="utf-8",
            )

        plan = direct_store.inspect_direct_checkpoint_provenance(
            root,
            current_computation_dependencies=dependencies,
        )

        record = plan["runs"][0]
        assert record["resume_allowed"] is False
        assert record["provenance_classification"] == "manifest_custody_invalid"
        assert record["manifest_custody_valid"] is False
        if case == "tampered":
            assert record["manifest_hash_valid"] is False
        else:
            assert record["manifest_hash_valid"] is True


def test_dependency_snapshot_corruption_remains_distinct_from_identity_drift(
    tmp_path: Path,
) -> None:
    dependencies, dependency_hash = _dependencies()
    identity = direct_store._stable_direct_computation_identity_payload(
        dependencies
    )
    root = tmp_path / "direct-store"
    run_directory = root / "runs" / "corrupt-run"
    run_directory.mkdir(parents=True)
    checkpoint_path = run_directory / "checkpoint.json"
    checkpoint_path.write_text(
        json.dumps(
            {
                **_checkpoint_base("corrupt-run"),
                "computation_identity_hash": direct_store._sha256_json(identity),
                "computation_identity": identity,
                "computation_dependency_hash": dependency_hash,
                "computation_dependencies": {
                    **dependencies,
                    "files": list(dependencies["files"][:-1]),
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    plan = direct_store.inspect_direct_checkpoint_provenance(
        root,
        current_computation_dependencies=dependencies,
    )

    assert plan["runs"][0]["provenance_classification"] == (
        "checkpoint_dependency_snapshot_corrupt"
    )


def test_ooc_gate_rejects_legacy_current_v4_manifest(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "runs" / "legacy" / "manifest.json"
    manifest_path.parent.mkdir(parents=True)

    with pytest.raises(
        direct_store.DirectCheckpointProvenanceError,
        match="direct manifest computation provenance is legacy and missing",
    ) as error:
        ooc_continuation._validate_current_direct_computation_provenance(
            manifest_path=manifest_path,
            manifest={},
        )

    assert error.value.classification == "legacy_missing_computation_provenance"


def test_ooc_gate_accepts_current_manifest_and_checkpoint_identity(
    tmp_path: Path,
) -> None:
    dependencies, dependency_hash = _dependencies()
    identity = direct_store._stable_direct_computation_identity_payload(
        dependencies
    )
    identity_hash = direct_store._sha256_json(identity)
    run_directory = tmp_path / "runs" / "current"
    run_directory.mkdir(parents=True)
    manifest_path = run_directory / "manifest.json"
    manifest = {
        "computation_identity_hash": identity_hash,
        "computation_identity": identity,
        "computation_dependency_hash": dependency_hash,
        "computation_dependencies": dependencies,
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    (run_directory / "checkpoint.json").write_text(
        json.dumps(
            {
                **manifest,
                "complete": True,
            }
        ),
        encoding="utf-8",
    )

    ooc_continuation._validate_current_direct_computation_provenance(
        manifest_path=manifest_path,
        manifest=manifest,
    )
