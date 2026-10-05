from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

import pytest

from scripts.scheduled import ml_daily_source_row_research_adapter as adapter


def _json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _with_content_hash(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result["content_sha256"] = _sha(_json_bytes(payload))
    return result


def _write(path: Path, payload: object) -> bytes:
    raw = _json_bytes(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


def _projection_fixture(repo: Path) -> dict[str, Any]:
    source_date = "2026-10-03"
    projection_id = "a" * 64
    research_root = adapter.get_ml_research_root(repository_root=repo)
    research_root.mkdir(parents=True, exist_ok=True)
    candidate_root = (
        research_root
        / adapter.PROJECTION_ROOT_RELATIVE
        / source_date
        / projection_id
    )
    observations = {
        "symbol": "2330",
        "venue": "twse",
        "source_date": source_date,
        "source_available_at": "2026-10-03T08:00:00+00:00",
        "source_values": {"證券代號": "2330", "收盤價": "100.00"},
    }
    observations_bytes = _json_bytes(observations) + b"\n"
    observation_sha = _sha(observations_bytes)
    capture_bytes = b'{"candidate":"verified"}'
    source_bytes = b"official source bytes"
    source_receipt = b'{"source":"verified"}'
    copied_files = {
        "i/candidate.json": (b'{"candidate":"verified"}',),
        "i/capture.json": (capture_bytes,),
        "i/twse.bin": (source_bytes,),
        "i/twse.json": (source_receipt,),
    }
    copied_pins: dict[str, dict[str, Any]] = {}
    for relative, (raw,) in copied_files.items():
        (candidate_root / relative).parent.mkdir(parents=True, exist_ok=True)
        (candidate_root / relative).write_bytes(raw)
        copied_pins[relative] = {"sha256": _sha(raw), "bytes": len(raw)}

    manifest_body: dict[str, Any] = {
        "schema_version": "ml-daily-source-row-research-projection.v1",
        "projection_id": projection_id,
        "projection_started_at": "2026-10-03T08:00:01+00:00",
        "source_date": source_date,
        "input_files": copied_pins,
        "observations_file": {
            "path": "observations.jsonl",
            "sha256": observation_sha,
            "bytes": len(observations_bytes),
            "row_count": 1,
        },
        "research_only": True,
        "formal_credit": False,
        "historical_pit_eligible": False,
        "formal_oos_allowed": False,
    }
    manifest = _with_content_hash(manifest_body)
    manifest_bytes = _write(candidate_root / "manifest.json", manifest)
    (candidate_root / "observations.jsonl").write_bytes(observations_bytes)

    completion = _with_content_hash(
        {
            "schema_version": "ml-daily-source-row-research-completion.v1",
            "projection_id": projection_id,
            "manifest_sha256": _sha(manifest_bytes),
            "observations_sha256": observation_sha,
            "completion_started_at": "2026-10-03T08:00:02+00:00",
            "completion_status": "awaiting_terminal_revision_validation",
            "formal_credit": False,
        }
    )
    completion_bytes = _write(candidate_root / "completion_receipt.json", completion)
    terminal = _with_content_hash(
        {
            "schema_version": "ml-daily-source-row-runner-terminal-receipt.v1",
            "terminal_status": "completed_research_only",
            "source_date": source_date,
            "formal_credit": False,
            "historical_pit_eligible": False,
            "formal_oos_allowed": False,
            "projection": {
                "projection_id": projection_id,
                "manifest_sha256": _sha(manifest_bytes),
                "observations_sha256": observation_sha,
                "intermediate_completion_receipt_sha256": _sha(completion_bytes),
                "verification_completed_at": "2026-10-03T08:00:03+00:00",
            },
        }
    )
    terminal_bytes = _write(
        candidate_root / "runner_terminal_verification_receipt.json", terminal
    )

    return {
        "status": "projected_research_only",
        "terminal_receipt_readback_verified": True,
        "source_date": source_date,
        "projection_id": projection_id,
        "projection_candidate_root": str(candidate_root),
        "projection_manifest_path": str(candidate_root / "manifest.json"),
        "projection_manifest_sha256": _sha(manifest_bytes),
        "projection_observations_path": str(candidate_root / "observations.jsonl"),
        "projection_observations_sha256": observation_sha,
        "projected_row_count": 1,
        "projection_intermediate_completion_receipt_path": str(
            candidate_root / "completion_receipt.json"
        ),
        "projection_intermediate_completion_receipt_sha256": _sha(completion_bytes),
        "terminal_receipt_path": str(
            candidate_root / "runner_terminal_verification_receipt.json"
        ),
        "terminal_receipt_sha256": _sha(terminal_bytes),
        "formal_credit": False,
        "historical_pit_eligible": False,
        "formal_source_contract_eligible": False,
        "formal_oos_allowed": False,
        "features_included": False,
        "labels_included": False,
        "model_use_claimed": False,
    }


def _successful_adapter_process(
    argv: list[str], *, projection: dict[str, Any]
) -> subprocess.CompletedProcess[bytes]:
    def argument(name: str) -> str:
        return argv[argv.index(name) + 1]

    assert Path(argument("--raw-candidate-manifest")) == Path(
        projection["projection_manifest_path"]
    )
    assert argument("--expected-candidate-manifest-bytes-sha256") == projection[
        "projection_manifest_sha256"
    ]
    assert argument("--training-as-of") == "2026-10-03T08:00:03+00:00"
    adapter_root = Path(argument("--output-dir"))
    store_root = Path(argument("--consume-direct-store"))
    adapted_manifest_path = adapter_root / "all_field_enriched" / "manifest.json"
    feature_registry = [{"feature_id": "daily_prices.close", "scale": 100}]
    feature_registry_sha = _sha(_json_bytes(feature_registry))
    adapted_body = {"schema_version": "ml-research-adapted-raw-manifest.v1", "row_count": 1}
    adapted_manifest = dict(adapted_body)
    adapted_manifest_hash = _sha(_json_bytes(adapted_body))
    adapted_manifest["manifest_hash"] = adapted_manifest_hash
    adapted_manifest_bytes = _write(adapted_manifest_path, adapted_manifest)
    adapter_receipt = {
        "schema_version": "ml-research-direct-ooc-adapter-receipt.v1",
        "status": "verified_numeric_observations_ready",
        "candidate_raw_manifest_path": projection["projection_manifest_path"],
        "candidate_manifest_bytes_sha256": projection["projection_manifest_sha256"],
        "adapted_manifest_path": str(adapted_manifest_path.resolve()),
        "adapted_manifest_bytes_sha256": _sha(adapted_manifest_bytes),
        "adapted_manifest_hash": adapted_manifest_hash,
        "feature_registry_sha256": feature_registry_sha,
        "training_as_of": "2026-10-03T08:00:03+00:00",
        "row_count": 1,
        "formal_release_v4_pointer_untouched": True,
        "formal_d_root_untouched": True,
        "research_only": True,
        "formal_credit": False,
        "historical_pit_eligible": False,
        "direct_ooc_status": "blocked_insufficient_context_or_mature_history",
    }
    adapter_receipt_path = adapter_root / "adapter_receipt.json"
    adapter_receipt_bytes = _write(adapter_receipt_path, adapter_receipt)

    _write(store_root / "feature_registry.json", feature_registry)
    shard_path = store_root / "shards" / "2026-10-03.jsonl.gz"
    shard_bytes = b"verified daily numeric shard fixture"
    shard_path.parent.mkdir(parents=True)
    shard_path.write_bytes(shard_bytes)
    stored_shards = [
        {
            "path": "shards/2026-10-03.jsonl.gz",
            "bytes_sha256": _sha(shard_bytes),
            "compressed_sha256": _sha(shard_bytes),
            "uncompressed_sha256": _sha(b"uncompressed fixture"),
            "row_count": 1,
        }
    ]
    store_metadata = {
        "schema_version": "ml-research-verified-numeric-observations.v1",
        "status": "verified_numeric_observations_ready",
        "record_count": 1,
        "feature_value_count": 1,
        "current_observation_freeze": "2026-10-03T08:00:03+00:00",
        "historical_pit_eligible": False,
        "formal_oos_allowed": False,
        "production_alpha_bp": 0,
        "stored_shards": stored_shards,
    }
    store_metadata_bytes = _write(store_root / "store_metadata.json", store_metadata)
    consumption_receipt = {
        "schema_version": "ml-research-direct-numeric-receipt.v1",
        "status": "verified_numeric_observations_ready",
        "adapter_receipt_bytes_sha256": _sha(adapter_receipt_bytes),
        "candidate_manifest_bytes_sha256": projection["projection_manifest_sha256"],
        "feature_registry_sha256": feature_registry_sha,
        "store_metadata_sha256": _sha(store_metadata_bytes),
        "current_observation_freeze": "2026-10-03T08:00:03+00:00",
        "record_count": 1,
        "feature_value_count": 1,
        "direct_ooc_status": "blocked_insufficient_context_or_mature_history",
        "historical_pit_eligible": False,
        "formal_release_v4_pointer_untouched": True,
        "formal_d_root_untouched": True,
        "formal_oos_allowed": False,
        "production_alpha_bp": 0,
        "stored_shards": stored_shards,
    }
    _write(store_root / "consumption_receipt.json", consumption_receipt)
    payload = {
        "status": "verified_numeric_observations_ready",
        "direct_ooc_status": "blocked_insufficient_context_or_mature_history",
        "formal_oos_allowed": False,
        "production_alpha_bp": 0,
        "formal_release_v4_pointer_untouched": True,
        "adapted_manifest_path": str(adapted_manifest_path.resolve()),
        "adapted_manifest_hash": adapted_manifest_hash,
        "adapter_receipt_path": str(adapter_receipt_path.resolve()),
        "row_count": 1,
        "direct_store_receipt": consumption_receipt,
    }
    return subprocess.CompletedProcess(argv, 0, _json_bytes(payload), b"")


def test_adapts_one_pinned_projection_and_preserves_research_only_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    active_research_root = tmp_path / "FA_ML_Research"
    active_research_root.mkdir()
    (repo / "output").mkdir()
    (repo / "output" / "ml_research_storage.json").write_text(
        json.dumps(
            {
                "schema_version": "ml-research-storage.v1",
                "active_root": str(active_research_root),
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(adapter, "PROJECTION_ROOT_RELATIVE", Path("o/p"))
    projection = _projection_fixture(repo)
    adapter_script = repo / "scripts" / "adapt_ml_research_direct_ooc.py"
    adapter_script.parent.mkdir(parents=True)
    adapter_script.write_text("# fixture", encoding="utf-8")
    now = datetime(2026, 10, 3, 8, 10, tzinfo=timezone.utc)

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        assert kwargs["cwd"] == str(repo)
        assert kwargs["timeout"] == 900
        return _successful_adapter_process(argv, projection=projection)

    monkeypatch.setattr(adapter.subprocess, "run", fake_run)
    result = adapter.run_daily_source_row_research_adapter(
        raw_run_id="r1",
        source_date="2026-10-03",
        projection_status=projection,
        repository_root=repo,
        research_output_root=active_research_root,
        adapter_script=adapter_script,
        now_provider=lambda: now,
    )

    assert result["status"] == "completed_research_only"
    assert result["raw_run_id"] == "r1"
    assert Path(result["research_output_root"]) == active_research_root
    assert result["event_date"] == "2026-10-03"
    assert result["current_observation_freeze"] == "2026-10-03T08:00:03+00:00"
    assert result["current_symbols"] == ["2330"]
    assert result["direct_ooc_status"] == "blocked_insufficient_context_or_mature_history"
    assert result["formal_credit"] is False
    assert result["historical_pit_eligible"] is False
    assert result["core19_direct_fit_input"] is False
    assert result["core19_bridge_input_compatible"] is True
    assert result["core19_bridge_status"] == (
        "not_run_missing_same_run_direct_prepared_core19"
    )
    assert result["output_root"] == result["research_artifact_root"]
    assert result["feature_registry_bytes_sha256"].startswith("sha256:")
    assert result["stored_shards"][0]["bytes_sha256"] == _sha(
        Path(result["stored_shards"][0]["path"]).read_bytes()
    )
    assert "raw_publication_manifest_path_and_sha256" in result[
        "current_restated_fit_evidence_not_provided"
    ]
    terminal_path = Path(result["terminal_receipt_path"])
    terminal_bytes = terminal_path.read_bytes()
    assert _sha(terminal_bytes) == result["terminal_receipt_sha256"]
    terminal = json.loads(terminal_bytes.decode("utf-8"))
    assert terminal["projection_manifest_sha256"] == projection["projection_manifest_sha256"]
    assert terminal["consumption_receipt_sha256"] == result["consumption_receipt_sha256"]
    assert terminal["model_created"] is False
    assert terminal["prediction_created"] is False
    assert terminal["outcome_created"] is False


def test_adapter_failure_gets_its_own_terminal_without_changing_parent_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(adapter, "PROJECTION_ROOT_RELATIVE", Path("o/p"))
    projection = _projection_fixture(repo)
    adapter_script = repo / "scripts" / "adapt_ml_research_direct_ooc.py"
    adapter_script.parent.mkdir(parents=True)
    adapter_script.write_text("# fixture", encoding="utf-8")
    now = datetime(2026, 10, 3, 8, 10, tzinfo=timezone.utc)

    def fail_run(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(argv, 2, b"", b"adapter rejected candidate")

    monkeypatch.setattr(adapter.subprocess, "run", fail_run)
    result = adapter.run_daily_source_row_research_adapter(
        raw_run_id="r2",
        source_date="2026-10-03",
        projection_status=projection,
        repository_root=repo,
        research_output_root=repo / "output" / "ml_research",
        adapter_script=adapter_script,
        now_provider=lambda: now,
    )

    assert result["status"] == "failed_closed"
    assert result["adapter_process"]["exit_code"] == 2
    terminal_path = Path(result["terminal_receipt_path"])
    terminal_bytes = terminal_path.read_bytes()
    assert _sha(terminal_bytes) == result["terminal_receipt_sha256"]
    assert json.loads(terminal_bytes.decode("utf-8"))["status"] == "failed_closed"
    assert Path(projection["projection_manifest_path"]).is_file()
    assert _sha(Path(projection["projection_manifest_path"]).read_bytes()) == projection[
        "projection_manifest_sha256"
    ]


def test_existing_request_path_is_never_reused_or_modified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(adapter, "PROJECTION_ROOT_RELATIVE", Path("o/p"))
    projection = _projection_fixture(repo)
    adapter_script = repo / "scripts" / "adapt_ml_research_direct_ooc.py"
    adapter_script.parent.mkdir(parents=True)
    adapter_script.write_text("# fixture", encoding="utf-8")
    now = datetime(2026, 10, 3, 8, 10, tzinfo=timezone.utc)
    monkeypatch.setattr(
        adapter.subprocess,
        "run",
        lambda argv, **_kwargs: _successful_adapter_process(argv, projection=projection),
    )
    kwargs = {
        "raw_run_id": "r3",
        "source_date": "2026-10-03",
        "projection_status": projection,
        "repository_root": repo,
        "research_output_root": repo / "output" / "ml_research",
        "adapter_script": adapter_script,
        "now_provider": lambda: now,
    }
    first = adapter.run_daily_source_row_research_adapter(**kwargs)
    original_terminal = Path(first["terminal_receipt_path"]).read_bytes()
    retry = adapter.run_daily_source_row_research_adapter(**kwargs)

    assert first["status"] == "completed_research_only"
    assert retry["status"] == "failed_closed"
    assert "already exists" in retry["error"]
    assert Path(first["terminal_receipt_path"]).read_bytes() == original_terminal


def test_projection_pin_mismatch_fails_before_creating_research_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(adapter, "PROJECTION_ROOT_RELATIVE", Path("o/p"))
    projection = _projection_fixture(repo)
    adapter_script = repo / "scripts" / "adapt_ml_research_direct_ooc.py"
    adapter_script.parent.mkdir(parents=True)
    adapter_script.write_text("# fixture", encoding="utf-8")

    def forbidden_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        raise AssertionError("B adapter must not run when the projection pin fails")

    monkeypatch.setattr(adapter.subprocess, "run", forbidden_run)
    projection["projection_manifest_sha256"] = "sha256:" + "0" * 64
    result = adapter.run_daily_source_row_research_adapter(
        raw_run_id="r4",
        source_date="2026-10-03",
        projection_status=projection,
        repository_root=repo,
        research_output_root=repo / "output" / "ml_research",
        adapter_script=adapter_script,
        now_provider=lambda: datetime(2026, 10, 3, 8, 10, tzinfo=timezone.utc),
    )

    assert result["status"] == "failed_closed"
    assert "bytes differ" in result["error"]
    assert not (repo / "output" / "ml_research" / "daily_source_rows").exists()
