"""每週歷史搬遷例外的封閉身份與即時重驗。"""

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from data_module import scheduled_research_acquisition_binding as binding


@pytest.fixture
def migration_bytes(monkeypatch):
    """隔離檔案讀取；固定散列信任根另由真原件整合檢查核對。"""
    pin = binding.DEFAULT_PINNED_WEEKLY_MIGRATION_BINDING
    db = b"d" * 28672
    locator = b"l" * 503
    db_sha = "78fb7ea950e4613d7718d6a2415d4b52274b258dc3e042445a31e7f9d9d5201c"
    locator_sha = "eb419c7bbe8ef2de20c56f055952e1a17832650e2a5db4472320b2a4bd16bac9"
    entries = []
    for name, raw, digest in (("evidence_scheduler.db", db, db_sha), ("latest_status.json", locator, locator_sha)):
        entries.append({"Root": "FA_Data", "Relative": "output\\scheduled\\v2_2_weekly_collection\\" + name,
                        "DBytes": len(raw), "FBytes": len(raw), "D_SHA256": digest,
                        "F_SHA256": digest, "Status": "PASS"})
    state = {"entries": entries, "db": db, "locator": locator, "missing": False, "proof_valid": True}
    real_sha = binding.sha256_bytes

    def proof_raw():
        return "\n".join(json.dumps(item) for item in state["entries"]).encode()

    def read(path, *, max_bytes):
        if path == pin.migration_proof_path:
            if state["missing"]:
                raise FileNotFoundError(path)
            return proof_raw()
        if path == Path(pin.current_sidecar_db_path):
            return state["db"]
        if path == Path(pin.current_output_root) / binding.WEEKLY_LOCATOR_RELATIVE_PATH:
            return state["locator"]
        raise AssertionError(path)

    def digest(raw):
        if raw == proof_raw():
            return pin.migration_proof_sha256 if state["proof_valid"] else "0" * 64
        if raw == db:
            return db_sha
        if raw == locator:
            return locator_sha
        return real_sha(raw)

    monkeypatch.setattr(binding, "_read_stable_bytes", read)
    monkeypatch.setattr(binding, "sha256_bytes", digest)
    return pin, state


def test_exact_mapping_rechecks_current_bytes(migration_bytes):
    pin, state = migration_bytes
    assert binding._verify_pinned_weekly_migration_binding(pin)
    state["db"] = b"x" * 28672
    assert not binding._verify_pinned_weekly_migration_binding(pin)


def test_original_migration_uppercase_hex_is_supported(migration_bytes):
    pin, state = migration_bytes
    for entry in state["entries"]:
        entry["D_SHA256"] = entry["D_SHA256"].upper()
        entry["F_SHA256"] = entry["F_SHA256"].upper()
    assert binding._verify_pinned_weekly_migration_binding(pin)


def test_general_artifact_hash_contract_stays_lowercase():
    with pytest.raises(binding.ResearchBindingError):
        binding._normalize_sha256("A" * 64)


def test_success_does_not_cache_missing_proof(migration_bytes):
    pin, state = migration_bytes
    assert binding._verify_pinned_weekly_migration_binding(pin)
    state["missing"] = True
    assert not binding._verify_pinned_weekly_migration_binding(pin)


def test_proof_digest_changed_after_success_rejected(migration_bytes):
    pin, state = migration_bytes
    assert binding._verify_pinned_weekly_migration_binding(pin)
    state["proof_valid"] = False
    assert not binding._verify_pinned_weekly_migration_binding(pin)


def test_current_locator_change_rejected(migration_bytes):
    pin, state = migration_bytes
    state["locator"] = b"x" * 503
    assert not binding._verify_pinned_weekly_migration_binding(pin)


@pytest.mark.parametrize("field", ["original_output_root", "current_output_root", "original_sidecar_db_path", "current_sidecar_db_path", "run_id", "receipt_sha256"])
def test_binding_cannot_authorize_another_identity(migration_bytes, field):
    pin, _ = migration_bytes
    assert not binding._verify_pinned_weekly_migration_binding(replace(pin, **{field: "other"}))


@pytest.mark.parametrize("field,value", [("DBytes", 1), ("FBytes", True), ("D_SHA256", "0" * 64), ("F_SHA256", "0" * 64), ("Root", "other"), ("Status", "FAIL"), ("Relative", "output/other")])
def test_migration_entry_contract_is_exact(migration_bytes, field, value):
    pin, state = migration_bytes
    state["entries"][0][field] = value
    assert not binding._verify_pinned_weekly_migration_binding(pin)


def test_duplicate_migration_entry_rejected(migration_bytes):
    pin, state = migration_bytes
    state["entries"].append(dict(state["entries"][0]))
    assert not binding._verify_pinned_weekly_migration_binding(pin)


def test_same_root_new_parent_never_receives_historical_migration(tmp_path, monkeypatch):
    relative = "scheduled/v2_2_weekly_collection/controller_runs/new/terminal.json"
    path = tmp_path / Path(relative)
    now = datetime(2026, 10, 22, tzinfo=timezone.utc)
    payload = {"schema_version": binding.WEEKLY_RECEIPT_SCHEMA, "run_id": "new",
               "receipt_relative_path": relative, "output_root": str(tmp_path),
               "started_at_utc": now.isoformat(), "completed_at_utc": now.isoformat(),
               "state": "terminal", "completion_clock_observation": {"status": "verified", "observed_raw": now.isoformat()}}
    monkeypatch.setattr(binding, "_controller_receipt_path", lambda *_: path)
    monkeypatch.setattr(binding, "read_bound_json", lambda *_, **__: binding.BoundJson(path, b"", payload, "0" * 64))
    monkeypatch.setattr(binding, "_validate_weekly_timing_budget", lambda *_: None)
    seen = []

    def core(*_, migration_binding=None):
        seen.append(migration_binding)
        raise binding.ResearchBindingError("test_stopped_after_core_boundary")

    monkeypatch.setattr(binding, "_verify_core_binding", core)
    result = binding.verify_weekly_acquisition(tmp_path, now=now, receipt_path=path, expected_sha256="0" * 64)
    assert result["status"] == "blocked"
    assert result["reason"] == "test_stopped_after_core_boundary"
    assert seen == [None]
