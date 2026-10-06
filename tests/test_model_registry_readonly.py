"""純 synthetic registry；不讀取私有 DB 或執行模型。"""

from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from app_module import model_registry_readonly as reader_module
from app_module.model_registry_readonly import ModelRegistryReadonly, ModelRegistryReadError
from app_module.rule_research_shadow_acceptance import _validate_lifecycle
from ml_module.model_lifecycle_registry import (
    ModelLifecycleEvent, ModelLifecycleRegistry, initialize_model_lifecycle_registry,
)
from ml_module.model_prediction_registries import (
    MLModelRecord, MLModelRegistry, initialize_shadow_registry,
)
from tests.test_rule_research_forward_isolated import pipeline

OBSERVED = "2026-10-06T06:30:00+00:00"


def test_reviewed_registry_modules_import_in_fresh_process_without_data_io():
    """新程序載入實際 module，阻斷資料 I/O；stdlib bootstrap 與原碼載入除外。"""
    probe = r'''
import builtins, dataclasses, datetime, decimal, json, math, os, pathlib, sqlite3, sys, typing
from unittest.mock import patch
assert "ml_module.model_lifecycle_registry" not in sys.modules
assert "ml_module.model_prediction_registries" not in sys.modules
def forbidden(*args, **kwargs):
    raise AssertionError("registry import performed data I/O")
with patch.object(sqlite3, "connect", forbidden), \
     patch.object(builtins, "open", forbidden), \
     patch.object(os, "open", forbidden), \
     patch.object(pathlib.Path, "open", forbidden), \
     patch.object(pathlib.Path, "read_bytes", forbidden), \
     patch.object(pathlib.Path, "mkdir", forbidden):
    from ml_module.model_lifecycle_registry import ModelLifecycleEvent, _ALLOWED_TRANSITIONS
    from ml_module.model_prediction_registries import MLModelRecord
    model = MLModelRecord("synthetic", "dataset", "2026-10-05T00:00:00+00:00", "synthetic",
                          ("feature",), "never-open.bin", "sha256:" + "a" * 64)
    event = ModelLifecycleEvent("event", model.model_id, "activated_for_shadow",
                                "2026-10-06T00:00:00+00:00", "synthetic")
    assert event.event_type in _ALLOWED_TRANSITIONS[None]
    assert event.to_dict()["model_id"] == model.model_id
print("reviewed import and DTO paths: no data I/O")
'''
    result = subprocess.run(
        [sys.executable, "-B", "-c", probe], cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "no data I/O" in result.stdout


@pytest.fixture
def registry(tmp_path):
    path = tmp_path / "registry synthetic.db"
    model = MLModelRecord(
        model_id="synthetic-v1", dataset_id="synthetic-dataset-v1",
        created_at="2026-10-05T00:00:00+00:00", model_family="synthetic",
        feature_names=("synthetic-feature",), artifact_path=str(tmp_path / "never-open.bin"),
        artifact_hash="sha256:" + "a" * 64,
    )
    initialize_shadow_registry(path)
    initialize_model_lifecycle_registry(path)
    MLModelRegistry(path).append(model)
    pin = asdict(model)
    pin["feature_names"] = list(model.feature_names)
    pin.update(training_audit={"status": "unknown"}, target_contract={"status": "unknown"})
    return path, model, pin


def read(registry, **kwargs):
    path, model, pin = registry
    return ModelRegistryReadonly(path).read(model.model_id, expected_metadata=pin, observed_at=OBSERVED, **kwargs)


def event(registry, kind="activated_for_shadow", identity="event-1"):
    path, model, _ = registry
    value = ModelLifecycleEvent(identity, model.model_id, kind, "2026-10-06T00:00:00+00:00", "synthetic")
    ModelLifecycleRegistry(path).append(value)
    return value


def mutate_model(registry, **changes):
    path, model, pin = registry
    with sqlite3.connect(path) as conn:
        raw = json.loads(conn.execute("SELECT payload_json FROM ml_models").fetchone()[0])
        raw.update(changes)
        conn.execute("UPDATE ml_models SET payload_json=?", (json.dumps(raw),))


def assert_error(registry, code):
    with pytest.raises(ModelRegistryReadError, match="^" + code + "$"):
        read(registry)


def test_existing_dtos_export_consumer_and_bytes_mtime_unchanged(registry):
    path, model, pin = registry
    first = event(registry)
    before = path.read_bytes(), path.stat().st_mtime_ns, set(path.parent.iterdir())
    result = read(registry)
    assert result.model == model
    assert result.events == (first,)
    assert result.current_status == "activated_for_shadow"
    assert result.unverified_metadata_fields == ("target_contract", "training_audit")
    assert _validate_lifecycle(result.lifecycle_export, pin, OBSERVED)["valid"] is True
    assert (path.read_bytes(), path.stat().st_mtime_ns, set(path.parent.iterdir())) == before
    assert result.safety_flags["qualified_count"] == 0
    assert result.safety_flags["production_blend_alpha_bp"] == 0
    assert result.safety_flags["selection_status"] == "unknown"
    assert all(value is False for key, value in result.safety_flags.items()
               if key.endswith("eligible") or key in {"shadow_enabled", "natural_authority", "production_action_allowed"})


def test_empty_events_keep_candidate_without_activation(registry):
    result = read(registry)
    assert result.current_status is None and result.events == ()
    assert result.model.lifecycle_status == "shadow_candidate"
    assert result.safety_flags["shadow_enabled"] is False


def test_reviewed_dto_construction_and_transition_validation_have_no_indirect_io(registry, monkeypatch):
    """直接阻斷 I/O，驗證新三符號的 DTO 路徑不呼叫 writer 或讀模型。"""
    _, model, _ = registry

    def forbidden(*args, **kwargs):
        pytest.fail("DTO／轉移表不應讀寫檔案、開 DB 或呼叫 registry")

    with monkeypatch.context() as blocked:
        blocked.setattr(sqlite3, "connect", forbidden)
        blocked.setattr(Path, "open", forbidden)
        blocked.setattr(Path, "read_bytes", forbidden)
        blocked.setattr(MLModelRegistry, "append", forbidden)
        blocked.setattr(ModelLifecycleRegistry, "append", forbidden)
        constructed = reader_module.MLModelRecord(**asdict(model))
        value = reader_module.ModelLifecycleEvent(
            "synthetic-no-io", model.model_id, "activated_for_shadow", OBSERVED, "synthetic",
        )
        assert value.event_type in reader_module._ALLOWED_TRANSITIONS[None]
        assert "disabled" in reader_module._ALLOWED_TRANSITIONS[value.event_type]
        assert value.to_dict()["model_id"] == constructed.model_id
        with pytest.raises(ValueError, match="unsupported lifecycle event"):
            reader_module.ModelLifecycleEvent("bad", model.model_id, "unknown", OBSERVED, "synthetic")
        with pytest.raises(ValueError, match="shadow-only"):
            reader_module.MLModelRecord(**{**asdict(model), "production_eligible": True})


@pytest.mark.parametrize("state", ["disabled", "superseded", "review_required", "rollback_requested"])
def test_terminal_state_stops_existing_consumer_without_control(registry, state):
    event(registry)
    event(registry, state, "event-2")
    result = read(registry)
    assert result.current_status == state
    assert _validate_lifecycle(result.lifecycle_export, registry[2], OBSERVED)["status"] == "stopped"
    assert not any(hasattr(ModelRegistryReadonly, name) for name in ("append", "adopt", "rollback", "disable", "predict", "fit", "load"))


def test_missing_database_never_creates_parent_or_database(tmp_path):
    path = tmp_path / "absent-parent" / "missing.db"
    with pytest.raises(ModelRegistryReadError, match="registry_expected_metadata_invalid"):
        ModelRegistryReadonly(path).read("test", expected_metadata={}, observed_at=OBSERVED)
    assert not path.parent.exists()


def test_missing_registry_with_valid_pin(registry):
    path, model, pin = registry
    missing = path.parent / "not-created.db"
    with pytest.raises(ModelRegistryReadError, match="registry_missing"):
        ModelRegistryReadonly(missing).read(model.model_id, expected_metadata=pin, observed_at=OBSERVED)
    assert not missing.exists()


@pytest.mark.parametrize("kind", ["empty", "old", "view", "future_column"])
def test_schema_missing_old_view_and_future_fail_closed(registry, kind):
    path = registry[0]
    with sqlite3.connect(path) as conn:
        if kind == "empty":
            conn.execute("DROP TABLE ml_model_lifecycle_events")
        elif kind == "old":
            conn.execute("ALTER TABLE ml_models RENAME COLUMN payload_json TO metadata")
        elif kind == "view":
            conn.execute("ALTER TABLE ml_models RENAME TO old_models")
            conn.execute("CREATE VIEW ml_models AS SELECT * FROM old_models")
        else:
            conn.execute("ALTER TABLE ml_models ADD COLUMN version TEXT")
    before = path.read_bytes(), path.stat().st_mtime_ns
    assert_error(registry, "registry_schema_mismatch")
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_corrupt_database_unchanged(registry):
    path = registry[0]
    path.write_bytes(b"synthetic corrupt database")
    before = path.read_bytes(), path.stat().st_mtime_ns
    assert_error(registry, "registry_corrupt")
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


@pytest.mark.parametrize("field,value", [
    ("artifact_hash", "sha256:" + "b" * 64), ("dataset_id", "synthetic-v2"),
    ("model_family", "synthetic-v2"), ("calibration_id", "calibration-v2"),
])
def test_version_mismatch(registry, field, value):
    mutate_model(registry, **{field: value})
    assert_error(registry, "registry_version_mismatch")


@pytest.mark.parametrize("changes,code", [
    ({"lifecycle_status": "active"}, "registry_unknown_model_status"),
    ({"shadow_only": False}, "registry_qualification_rejected"),
    ({"production_eligible": True}, "registry_qualification_rejected"),
    ({"production_eligible": 0}, "registry_qualification_rejected"),
    ({"model_id": "other"}, "registry_model_identity_invalid"),
    ({"created_at": "2027-01-01T00:00:00+00:00"}, "registry_future_metadata"),
    ({"created_at": "2026-10-05"}, "registry_time_invalid"),
])
def test_unknown_status_unsafe_metadata_and_future_rejected(registry, changes, code):
    mutate_model(registry, **changes)
    assert_error(registry, code)


@pytest.mark.parametrize("change,code", [
    ({"event_type": "production_active"}, "registry_unknown_event_status"),
    ({"event_type": "disabled"}, "registry_transition_invalid"),
    ({"created_at": "2027-01-01T00:00:00+00:00"}, "registry_event_time_invalid"),
])
def test_invalid_lifecycle_rows(registry, change, code):
    first = event(registry)
    raw = {**first.to_dict(), **change}
    with sqlite3.connect(registry[0]) as conn:
        conn.execute("UPDATE ml_model_lifecycle_events SET event_type=?, created_at=?, payload_json=?",
                     (raw["event_type"], raw["created_at"], json.dumps(raw)))
    assert_error(registry, code)


def test_event_sql_json_identity_mismatch(registry):
    event(registry)
    with sqlite3.connect(registry[0]) as conn:
        conn.execute("UPDATE ml_model_lifecycle_events SET event_type='disabled'")
    assert_error(registry, "registry_event_identity_mismatch")


def test_locked_database_fails_without_lockfile_or_wait(registry):
    path = registry[0]
    with sqlite3.connect(path) as writer:
        writer.execute("BEGIN EXCLUSIVE")
        before = path.read_bytes(), path.stat().st_mtime_ns, set(path.parent.iterdir())
        assert_error(registry, "registry_locked")
        assert (path.read_bytes(), path.stat().st_mtime_ns, set(path.parent.iterdir())) == before


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_sidecars_rejected_without_reading_or_modifying(registry, suffix):
    sidecar = Path(str(registry[0]) + suffix)
    sidecar.write_bytes(b"synthetic residual")
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in registry[0].parent.iterdir()}
    assert_error(registry, "registry_sidecar_requires_snapshot")
    assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in registry[0].parent.iterdir()} == before


def test_wal_header_rejected_before_sqlite_can_create_shm(registry):
    with sqlite3.connect(registry[0]) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
    before = set(registry[0].parent.iterdir())
    assert_error(registry, "registry_sidecar_requires_snapshot")
    assert set(registry[0].parent.iterdir()) == before


def test_model_missing_and_parameterized_identity(registry):
    path, _, pin = registry
    with pytest.raises(ModelRegistryReadError, match="registry_model_missing"):
        ModelRegistryReadonly(path).read("' OR 1=1 --", expected_metadata=pin, observed_at=OBSERVED)


def test_connection_mode_query_only_authorizer_and_no_live_calls(registry, monkeypatch):
    connect = sqlite3.connect
    connections = []
    def probe(*args, **kwargs):
        assert args[0].endswith("?mode=ro") and kwargs["uri"] is True
        conn = connect(*args, **kwargs)
        connections.append(conn)
        return conn
    monkeypatch.setattr(reader_module.sqlite3, "connect", probe)
    def forbidden(*args, **kwargs):
        pytest.fail("唯讀 reader 呼叫 live registry")
    monkeypatch.setattr(MLModelRegistry, "get", forbidden)
    monkeypatch.setattr(ModelLifecycleRegistry, "list_events", forbidden)
    original = ModelRegistryReadonly._read
    def inspect(conn, *args):
        assert conn.execute("PRAGMA query_only").fetchone() == (1,)
        assert conn.execute("PRAGMA table_info(ml_models)").fetchall()
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("UPDATE ml_models SET model_id='forbidden'")
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("ATTACH DATABASE ':memory:' AS other")
        return original(conn, *args)
    monkeypatch.setattr(ModelRegistryReadonly, "_read", staticmethod(inspect))
    read(registry)
    assert len(connections) == 1
    with pytest.raises(sqlite3.ProgrammingError):
        connections[0].execute("SELECT 1")


def test_source_changed_during_read_rejected(registry, monkeypatch):
    original = reader_module._source
    count = 0
    def changed(path):
        nonlocal count
        count += 1
        value = original(path)
        return value if count == 1 else ("changed", *value[1:])
    monkeypatch.setattr(reader_module, "_source", changed)
    assert_error(registry, "registry_source_changed")


def test_explicit_absolute_path_required():
    with pytest.raises(ModelRegistryReadError, match="registry_explicit_absolute_path_required"):
        ModelRegistryReadonly("registry.db")


def test_payload_and_event_bounds(registry, monkeypatch):
    monkeypatch.setattr(reader_module, "MAX_PAYLOAD_BYTES", 16)
    assert_error(registry, "registry_payload_bound")


def test_export_bound(registry, monkeypatch):
    monkeypatch.setattr(reader_module, "MAX_EXPORT_BYTES", 16)
    assert_error(registry, "registry_export_bound")


def test_event_bound_no_partial_history(registry, monkeypatch):
    event(registry)
    event(registry, "review_required", "event-2")
    monkeypatch.setattr(reader_module, "MAX_EVENTS", 1)
    assert_error(registry, "registry_event_bound")


def test_database_bound(registry, monkeypatch):
    monkeypatch.setattr(reader_module, "MAX_DATABASE_BYTES", 16)
    assert_error(registry, "registry_database_bound")


@pytest.mark.parametrize("raw,code", [
    ("not json", "registry_payload_invalid"),
    ('{"model_id":"first","model_id":"second"}', "registry_payload_duplicate_key"),
    ('{"model_id":"old-partial-record"}', "registry_payload_schema_mismatch"),
])
def test_corrupt_and_old_payloads(registry, raw, code):
    with sqlite3.connect(registry[0]) as conn:
        conn.execute("UPDATE ml_models SET payload_json=?", (raw,))
    assert_error(registry, code)


def test_encoded_uri_filename_and_artifact_path_never_opened(registry, monkeypatch):
    path, model, pin = registry
    renamed = path.with_name("registry # & % synthetic.db")
    renamed.write_bytes(path.read_bytes())
    original = Path.open
    def guarded(path, *args, **kwargs):
        assert path != Path(model.artifact_path)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", guarded)
    result = read((renamed, model, pin))
    assert result.model == model


def test_mutated_export_pin_does_not_mutate_callers_metadata(registry):
    result = read(registry)
    result.lifecycle_export["metadata"]["training_audit"]["status"] = "changed"
    assert registry[2]["training_audit"]["status"] == "unknown"
    assert result.safety_flags["training_eligible"] is False


def test_reader_export_actual_shadow_consumer_keeps_three_axes_closed(pipeline, tmp_path):
    from tests.test_rule_research_shadow_acceptance import _inputs, _build
    inputs = _inputs(pipeline)
    pin = inputs[-1]
    path = tmp_path / "shadow-metadata.db"
    initialize_shadow_registry(path)
    initialize_model_lifecycle_registry(path)
    raw = {key: value for key, value in pin.items() if key in reader_module._MODEL_FIELDS}
    raw["feature_names"] = tuple(raw["feature_names"])
    MLModelRegistry(path).append(MLModelRecord(**raw))
    # 本 fixture 使用既有受控 pipeline；觀測時間不回填 prediction clock。
    from datetime import datetime, timezone
    result = ModelRegistryReadonly(path).read(
        pin["model_id"], expected_metadata=pin, observed_at=datetime.now(timezone.utc).isoformat(),
    )
    report = _build(inputs, lifecycle=result.lifecycle_export)
    assert report["status"] == "shadow_engineering_executable_research_only"
    assert report["data_effect_status"] == "not_qualified_research_only"
    assert report["activation_status"] == "not_enabled"
    assert report["safety_flags"]["qualified_count"] == 0
    assert report["safety_flags"]["shadow_enabled"] is False
