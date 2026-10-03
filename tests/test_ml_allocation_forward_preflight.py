from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import scripts.scheduled.prepare_ml_allocation_forward_config as config_module
from scripts.scheduled.run_ml_allocation_forward_daily import run_preflight


def _prepare_preflight_inputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    artifact_hash: str,
) -> tuple[Path, bytes]:
    files_root = tmp_path / "files"
    for name in ("output", "archive", "calendar", "temporary", "release"):
        (files_root / name).mkdir(parents=True, exist_ok=True)
    database = files_root / "market.sqlite"
    paper_state = files_root / "paper-state.sqlite"
    paper_ledger = files_root / "paper-ledger.sqlite"
    derived_script = files_root / "derived.py"
    for path in (database, paper_state, paper_ledger, derived_script):
        path.write_bytes(b"fixture")

    release_root = files_root / "release"
    release_manifest = release_root / "release_manifest.json"
    manifest_bytes = json.dumps(
        {"artifact_hash": artifact_hash},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    release_manifest.write_bytes(manifest_bytes)

    monkeypatch.setattr(config_module, "default_archive_root", lambda: files_root / "archive")
    monkeypatch.setattr(config_module, "default_calendar_cache_root", lambda: files_root / "calendar")
    monkeypatch.setattr(config_module, "default_database", lambda: database)
    monkeypatch.setattr(config_module, "default_output_root", lambda: files_root / "output")
    monkeypatch.setattr(config_module, "default_paper_state_db", lambda: paper_state)
    monkeypatch.setattr(config_module, "default_paper_trade_ledger_db", lambda: paper_ledger)
    monkeypatch.setattr(config_module, "default_release_root", lambda: release_root)
    monkeypatch.setattr(
        config_module,
        "default_release_manifest_file_hash",
        lambda: "sha256:" + hashlib.sha256(manifest_bytes).hexdigest(),
    )
    monkeypatch.setattr(
        config_module,
        "default_temporary_closure_path",
        lambda: files_root / "temporary",
    )
    return derived_script, manifest_bytes


def test_forward_preflight_blocks_quarantined_release_before_child(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    v1_artifact_hash = (
        "sha256:5c851d94b4a9385b30317b345ff084cdc47cdc165394e5463061272fbad67a52"
    )
    derived_script, _ = _prepare_preflight_inputs(
        monkeypatch,
        tmp_path,
        artifact_hash=v1_artifact_hash,
    )

    payload, exit_code = run_preflight(derived_script=derived_script)

    assert exit_code == 2
    assert payload["status"] == "blocked"
    assert payload["deployment_path_ready"] is True
    assert payload["model_source_ready"] is False
    assert payload["model_source_quarantined"] is True
    assert payload["model_source_blocker"] == "known_source_revision_quarantine"
    assert payload["blockers"] == [
        "model_source:known_source_revision_quarantine"
    ]
    assert payload["config_producer_called"] is False
    assert payload["child_started"] is False
    assert payload["forward_credit_granted"] is False


def test_forward_preflight_keeps_valid_pinned_source_ready(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    derived_script, _ = _prepare_preflight_inputs(
        monkeypatch,
        tmp_path,
        artifact_hash="sha256:" + "b" * 64,
    )

    payload, exit_code = run_preflight(derived_script=derived_script)

    assert exit_code == 0
    assert payload["status"] == "ready"
    assert payload["deployment_path_ready"] is True
    assert payload["model_source_ready"] is True
    assert payload["model_source_quarantined"] is False
    assert payload["model_source_blocker"] is None
    assert payload["config_producer_called"] is False
    assert payload["child_started"] is False


def test_forward_preflight_rejects_release_manifest_pin_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    derived_script, manifest_bytes = _prepare_preflight_inputs(
        monkeypatch,
        tmp_path,
        artifact_hash="sha256:" + "b" * 64,
    )
    manifest_path = derived_script.parent / "release" / "release_manifest.json"
    manifest_path.write_bytes(manifest_bytes + b" ")

    payload, exit_code = run_preflight(derived_script=derived_script)

    assert exit_code == 2
    assert payload["status"] == "blocked"
    assert payload["deployment_path_ready"] is False
    assert payload["model_source_ready"] is False
    assert payload["model_source_quarantined"] is False
    assert payload["model_source_blocker"] == "release_pin_unverified"
    assert payload["blockers"] == [
        "release_pin:release manifest file hash mismatch",
        "model_source:release_pin_unverified",
    ]
    assert payload["config_producer_called"] is False
    assert payload["child_started"] is False
