from pathlib import Path
from dataclasses import fields
from datetime import datetime, timezone
import sqlite3
import subprocess
import sys
import json

import pytest

from app_module.rule_research_shadow_acceptance import read_shadow_acceptance, save_shadow_acceptance
from ml_module.model_prediction_registries import MLModelRecord, MLModelRegistry, initialize_shadow_registry
from ml_module.model_lifecycle_registry import initialize_model_lifecycle_registry
from tests.test_rule_research_forward_isolated import pipeline
from tests.test_rule_research_shadow_acceptance import _inputs, _build, _lifecycle


def snapshot(tmp_path, pin):
    path = tmp_path / "registry.db"
    initialize_shadow_registry(path)
    initialize_model_lifecycle_registry(path)
    data = {f.name: pin[f.name] for f in fields(MLModelRecord)}
    data["feature_names"] = tuple(data["feature_names"])
    MLModelRegistry(path).append(MLModelRecord(**data))
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    return path


def test_metadata_read_exact_save_reload_and_unchanged_bytes(pipeline, tmp_path):
    inputs = _inputs(pipeline)
    path = snapshot(tmp_path, inputs[-1])
    before = path.read_bytes(), path.stat().st_mtime_ns
    report = _build(inputs, registry_snapshot=path)
    readback = report["diagnostics"]["registry_readback"]
    assert readback["status"] == "metadata_verified"
    assert readback["mode"] == "registry_snapshot_read"
    assert readback["unverified_metadata_fields"] == ["target_contract", "training_audit"]
    assert report["safety_flags"]["training_eligible"] is False
    assert report["safety_flags"]["shadow_enabled"] is False
    saved = save_shadow_acceptance(report, tmp_path / "saved", revalidate=lambda: _build(inputs, registry_snapshot=path))
    assert read_shadow_acceptance(tmp_path / "saved", saved["receipt"]["capture_identity_sha256"])["capture"] == report
    fresh = subprocess.run([sys.executable, "scripts/run_rule_research_shadow_acceptance.py",
        "--store", str(tmp_path / "saved"), "--identity", saved["receipt"]["capture_identity_sha256"], "--json"],
        capture_output=True, text=True, encoding="utf-8", check=True)
    assert json.loads(fresh.stdout)["capture"] == report
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


@pytest.mark.parametrize("mode", ["missing", "wal", "sidecar", "wrong_source", "locked", "version"])
def test_registry_failure_has_no_export_fallback(pipeline, tmp_path, mode):
    inputs = _inputs(pipeline)
    path = snapshot(tmp_path, inputs[-1])
    connection = None
    if mode == "missing":
        path = tmp_path / "absent.db"
    elif mode == "wal":
        with sqlite3.connect(path) as db:
            db.execute("PRAGMA journal_mode=WAL")
    elif mode == "sidecar":
        Path(str(path) + "-wal").write_bytes(b"synthetic")
    elif mode == "wrong_source":
        path = tmp_path / "other.db"
        initialize_shadow_registry(path)
        initialize_model_lifecycle_registry(path)
    elif mode == "version":
        with sqlite3.connect(path) as db:
            db.execute("ALTER TABLE ml_models ADD COLUMN version TEXT")
    else:
        connection = sqlite3.connect(path)
        connection.execute("BEGIN EXCLUSIVE")
    try:
        report = _build(inputs, registry_snapshot=path)
    finally:
        if connection is not None:
            connection.close()
    assert report["status"] == "rule_only_fallback"
    assert report["diagnostics"]["registry_readback"]["status"] == "unavailable"
    assert report["diagnostics"]["registry_readback"]["reason_codes"]
    assert report["lifecycle"]["valid"] is False


def test_export_declaration_separate_and_mutually_exclusive(pipeline, tmp_path):
    inputs = _inputs(pipeline)
    report = _build(inputs, lifecycle=_lifecycle(inputs[-1]))
    assert report["diagnostics"]["registry_readback"]["mode"] == "exported_declaration"
    assert report["diagnostics"]["registry_readback"]["source_sha256"] is None
    with pytest.raises(ValueError, match="mutually_exclusive"):
        _build(inputs, lifecycle=_lifecycle(inputs[-1]), registry_snapshot=tmp_path / "missing")


def test_observed_time_rejects_future_metadata(pipeline, tmp_path):
    inputs = _inputs(pipeline)
    path = snapshot(tmp_path, inputs[-1])
    report = _build(inputs, registry_snapshot=path, observed_at=datetime(2000, 1, 1, tzinfo=timezone.utc))
    assert report["diagnostics"]["registry_readback"]["status"] == "unavailable"


def test_revalidation_rejects_registry_revision(pipeline, tmp_path):
    inputs = _inputs(pipeline)
    path = snapshot(tmp_path, inputs[-1])
    report = _build(inputs, registry_snapshot=path)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE changed_source (value TEXT)")
    with pytest.raises(ValueError, match="source_revision"):
        save_shadow_acceptance(report, tmp_path / "saved", revalidate=lambda: _build(inputs, registry_snapshot=path))


def test_cancel_after_registry_read_can_retry(pipeline, tmp_path, monkeypatch):
    from app_module.model_registry_readonly import ModelRegistryReadonly
    inputs = _inputs(pipeline)
    path = snapshot(tmp_path, inputs[-1])
    state = {"cancel": False}
    original = ModelRegistryReadonly.read
    def read(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        state["cancel"] = True
        return result
    monkeypatch.setattr(ModelRegistryReadonly, "read", read)
    report = _build(inputs, registry_snapshot=path, cancel_callback=lambda: state["cancel"])
    assert report["status"] == "cancelled"
    monkeypatch.setattr(ModelRegistryReadonly, "read", original)
    assert _build(inputs, registry_snapshot=path)["diagnostics"]["registry_readback"]["status"] == "metadata_verified"
