from __future__ import annotations

import builtins
from dataclasses import dataclass
from io import BytesIO
import hashlib
import json
from pathlib import Path

import joblib
import pytest

import ml_module.model_artifact_loader as loader_module
from ml_module.model_artifact_loader import (
    ArtifactCompatibilityExpectation,
    SafeShadowModelArtifactLoader,
    SameBytesShadowModelArtifactWithManifestLoadResultV1,
    SameBytesShadowModelArtifactLoadResultV1,
)
from ml_module.model_artifact_manifest import ModelArtifactManifest


_SCHEMA = (("score_bp", "int", "bp"),)


@dataclass(frozen=True)
class _ParameterizedShadowBundle:
    model_id: str = "model-1"
    dataset_id: str = "dataset-1"
    model_family: str = "fixture_family"
    shadow_only: bool = True
    production_eligible: bool = False
    production_action_allowed: bool = False
    parameter: str = "original"


def _sha256(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _expectation(**overrides: object) -> ArtifactCompatibilityExpectation:
    values: dict[str, object] = {
        "expected_model_family": "fixture_family",
        "expected_feature_registry_hash": _sha256(b"features"),
        "expected_label_registry_hash": _sha256(b"labels"),
        "expected_feature_schema": _SCHEMA,
        "installed_library_versions": {"python": "3.11.9"},
    }
    values.update(overrides)
    return ArtifactCompatibilityExpectation(**values)  # type: ignore[arg-type]


def _write_fixture(root: Path, bundle: _ParameterizedShadowBundle) -> ModelArtifactManifest:
    root.mkdir(parents=True)
    artifact_path = root / "model-1.joblib"
    buffer = BytesIO()
    joblib.dump(bundle, buffer, compress=0)
    artifact_bytes = buffer.getvalue()
    artifact_path.write_bytes(artifact_bytes)
    manifest = ModelArtifactManifest.create(
        model_id="model-1",
        dataset_id="dataset-1",
        created_run_id="run-1",
        created_at="2026-07-13T12:00:00+00:00",
        model_family="fixture_family",
        feature_registry_hash=_sha256(b"features"),
        label_registry_hash=_sha256(b"labels"),
        feature_schema=_SCHEMA,
        training_as_of="2024-12-31",
        hyperparameters_hash=_sha256(b"params"),
        library_versions={"python": "3.11.9"},
        serialization_format="joblib",
        artifact_filename=artifact_path.name,
        artifact_hash=_sha256(artifact_bytes),
    )
    (root / "manifest.json").write_text(
        json.dumps(manifest.to_dict(), sort_keys=True), encoding="utf-8"
    )
    return manifest


def _alternate_bytes(parameter: str) -> bytes:
    buffer = BytesIO()
    joblib.dump(_ParameterizedShadowBundle(parameter=parameter), buffer, compress=0)
    return buffer.getvalue()


def test_same_bytes_loader_closes_hash_then_reopen_toctou_without_changing_legacy_path(
    tmp_path: Path, monkeypatch: object
) -> None:
    root = tmp_path / "shadow-model"
    manifest = _write_fixture(root, _ParameterizedShadowBundle(parameter="original"))
    artifact_path = root / manifest.artifact_filename
    replacement_bytes = _alternate_bytes("replacement-same-identity")
    real_open = builtins.open
    real_hash_file = loader_module._sha256_file
    state = {"armed": False, "replaced": False}

    def arm_after_hash(path: Path) -> str:
        result = real_hash_file(path)
        if path == artifact_path:
            state["armed"] = True
        return result

    def replace_at_deserializer_open(file: object, *args: object, **kwargs: object):
        try:
            matches_artifact = Path(file) == artifact_path  # type: ignore[arg-type]
        except (TypeError, ValueError):
            matches_artifact = False
        if state["armed"] and not state["replaced"] and matches_artifact:
            state["replaced"] = True
            return BytesIO(replacement_bytes)
        return real_open(file, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(loader_module, "_sha256_file", arm_after_hash)  # type: ignore[attr-defined]
    monkeypatch.setattr(builtins, "open", replace_at_deserializer_open)  # type: ignore[attr-defined]
    loader = SafeShadowModelArtifactLoader(data_root=tmp_path / "formal-data")

    legacy_result = loader.load(root, expectation=_expectation())

    assert state["replaced"] is True
    assert legacy_result.status == "shadow_model_ready"
    assert legacy_result.model == _ParameterizedShadowBundle(
        parameter="replacement-same-identity"
    )

    state.update(armed=True, replaced=False)
    same_bytes_result = loader.load_same_bytes_v1(root, expectation=_expectation())

    assert isinstance(same_bytes_result, SameBytesShadowModelArtifactLoadResultV1)
    assert state["replaced"] is False
    assert same_bytes_result.status == "shadow_model_ready"
    assert same_bytes_result.model == _ParameterizedShadowBundle(parameter="original")
    assert same_bytes_result.loaded_serialized_bytes_sha256 == manifest.artifact_hash
    assert same_bytes_result.captured_artifact_sha256 == manifest.artifact_hash


def test_same_bytes_loader_hash_mismatch_never_calls_deserializer(
    tmp_path: Path, monkeypatch: object
) -> None:
    root = tmp_path / "shadow-model"
    _write_fixture(root, _ParameterizedShadowBundle())
    artifact_path = root / "model-1.joblib"
    artifact_path.write_bytes(b"tampered before capture")
    calls = 0
    real_deserialize = loader_module._deserialize_verified_joblib_buffer

    def count_deserialization(buffer: object) -> object:
        nonlocal calls
        calls += 1
        return real_deserialize(buffer)

    monkeypatch.setattr(  # type: ignore[attr-defined]
        loader_module, "_deserialize_verified_joblib_buffer", count_deserialization
    )
    result = SafeShadowModelArtifactLoader(
        data_root=tmp_path / "formal-data"
    ).load_same_bytes_v1(root, expectation=_expectation())

    assert result.status == "rule_only_fallback"
    assert result.blockers == ("artifact_hash_mismatch",)
    assert result.model is None
    assert result.loaded_serialized_bytes_sha256 is None
    assert result.captured_artifact_sha256 == _sha256(b"tampered before capture")
    assert calls == 0


def test_same_bytes_loader_preserves_old_path_api_and_accepts_active_and_lineage_artifacts(
    tmp_path: Path,
) -> None:
    loader = SafeShadowModelArtifactLoader(data_root=tmp_path / "formal-data")
    expected_hashes: list[str] = []
    for role, parameter in (("active", "active-model"), ("lineage", "prior-model")):
        root = tmp_path / role
        manifest = _write_fixture(
            root, _ParameterizedShadowBundle(parameter=parameter)
        )
        expected_hashes.append(manifest.artifact_hash)
        legacy = loader.load(root, expectation=_expectation())
        verified = loader.load_same_bytes_v1(root, expectation=_expectation())

        assert legacy.status == verified.status == "shadow_model_ready"
        assert legacy.model == verified.model == _ParameterizedShadowBundle(parameter=parameter)
        assert verified.loaded_serialized_bytes_sha256 == manifest.artifact_hash
        assert verified.captured_artifact_sha256 == manifest.artifact_hash

    assert len(set(expected_hashes)) == 2


def test_verified_buffer_path_rejects_custom_path_deserializer(
    tmp_path: Path,
) -> None:
    root = tmp_path / "shadow-model"
    _write_fixture(root, _ParameterizedShadowBundle())
    calls: list[Path] = []

    def path_deserializer(path: Path) -> object:
        calls.append(path)
        return joblib.load(path)

    loader = SafeShadowModelArtifactLoader(
        data_root=tmp_path / "formal-data", deserializer=path_deserializer
    )
    legacy = loader.load(root, expectation=_expectation())
    verified = loader.load_same_bytes_v1(root, expectation=_expectation())

    assert legacy.status == "shadow_model_ready"
    assert calls == [root / "model-1.joblib"]
    assert verified.status == "rule_only_fallback"
    assert verified.blockers == ("verified_buffer_requires_default_joblib",)
    assert verified.loaded_serialized_bytes_sha256 is None
    assert verified.captured_artifact_sha256 is None


def test_same_bytes_loader_keeps_path_library_and_model_identity_guards(
    tmp_path: Path,
) -> None:
    root = tmp_path / "shadow-model"
    manifest = _write_fixture(
        root, _ParameterizedShadowBundle(model_id="unexpected-model")
    )
    loader = SafeShadowModelArtifactLoader(data_root=tmp_path / "formal-data")

    incompatible = loader.load_same_bytes_v1(
        root,
        expectation=_expectation(installed_library_versions={"python": "3.10.0"}),
    )
    identity_mismatch = loader.load_same_bytes_v1(root, expectation=_expectation())
    formal_root_loader = SafeShadowModelArtifactLoader(data_root=root)
    root_rejected = formal_root_loader.load_same_bytes_v1(
        root, expectation=_expectation()
    )

    assert incompatible.blockers == ("library_version_mismatch",)
    assert incompatible.captured_artifact_sha256 is None
    assert incompatible.loaded_serialized_bytes_sha256 is None
    assert identity_mismatch.blockers == ("deserialized_model_identity_mismatch",)
    assert identity_mismatch.captured_artifact_sha256 == manifest.artifact_hash
    assert identity_mismatch.loaded_serialized_bytes_sha256 == manifest.artifact_hash
    assert root_rejected.blockers == ("artifact_root_not_shadow_safe",)
    assert root_rejected.captured_artifact_sha256 is None


def test_same_bytes_loader_malformed_manifest_container_fails_closed(
    tmp_path: Path,
) -> None:
    root = tmp_path / "shadow-model"
    root.mkdir()
    (root / "manifest.json").write_text("[]", encoding="utf-8")

    result = SafeShadowModelArtifactLoader(
        data_root=tmp_path / "formal-data"
    ).load_same_bytes_v1(root, expectation=_expectation())

    assert result.status == "rule_only_fallback"
    assert result.blockers == ("manifest_invalid",)
    assert result.model is None
    assert result.captured_artifact_sha256 is None
    assert result.loaded_serialized_bytes_sha256 is None


def test_manifest_same_bytes_v1_binds_raw_and_canonical_identity_from_one_capture(
    tmp_path: Path, monkeypatch: object
) -> None:
    root = tmp_path / "shadow-model"
    manifest = _write_fixture(root, _ParameterizedShadowBundle())
    manifest_path = root / "manifest.json"
    original_bytes = manifest_path.read_bytes()
    reads = 0
    original_read_bytes = Path.read_bytes

    def count_manifest_capture(path: Path) -> bytes:
        nonlocal reads
        if path == manifest_path:
            reads += 1
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", count_manifest_capture)  # type: ignore[attr-defined]
    result = SafeShadowModelArtifactLoader(
        data_root=tmp_path / "formal-data"
    ).load_same_bytes_with_manifest_v1(root, expectation=_expectation())

    assert isinstance(result, SameBytesShadowModelArtifactWithManifestLoadResultV1)
    assert result.status == "shadow_model_ready"
    assert result.manifest_raw_bytes_sha256 == _sha256(original_bytes)
    assert result.canonical_manifest_payload_sha256 == manifest.manifest_hash
    assert result.captured_manifest_bytes == original_bytes
    assert result.captured_artifact_sha256 == manifest.artifact_hash
    assert result.loaded_serialized_bytes_sha256 == manifest.artifact_hash
    assert reads == 1


@pytest.mark.parametrize(
    ("corruption", "expected_blocker"),
    [
        ("invalid_utf8", "manifest_invalid"),
        ("invalid_json", "manifest_invalid"),
        ("self_hash", "manifest_hash_mismatch"),
    ],
)
def test_manifest_same_bytes_v1_rejects_invalid_encoding_json_and_self_hash(
    tmp_path: Path,
    corruption: str,
    expected_blocker: str,
) -> None:
    root = tmp_path / "shadow-model"
    manifest = _write_fixture(root, _ParameterizedShadowBundle())
    if corruption == "invalid_utf8":
        manifest_bytes = b"\xff"
    elif corruption == "invalid_json":
        manifest_bytes = b"{not-json"
    else:
        payload = manifest.to_dict()
        payload["manifest_hash"] = _sha256(b"wrong-self-hash")
        manifest_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
    (root / "manifest.json").write_bytes(manifest_bytes)

    result = SafeShadowModelArtifactLoader(
        data_root=tmp_path / "formal-data"
    ).load_same_bytes_with_manifest_v1(root, expectation=_expectation())

    assert result.status == "rule_only_fallback"
    assert result.blockers == (expected_blocker,)
    assert result.model is None
    assert result.captured_manifest_bytes == manifest_bytes
    assert result.manifest_raw_bytes_sha256 == _sha256(manifest_bytes)
    assert result.canonical_manifest_payload_sha256 is None
