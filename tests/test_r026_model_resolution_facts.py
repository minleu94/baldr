from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app_module.recommendation_calibration_consumer import (
    RecommendationCalibrationConsumer,
)


@pytest.fixture(scope="module")
def active_context(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[RecommendationCalibrationConsumer, Path, Path]:
    from app_module.recommendation_calibration_consumer import (
        RecommendationCalibrationConsumer,
    )
    from ml_module.recommendation_calibration_authority import (
        RecommendationCalibrationPromotionAuthority,
    )
    from test_daily_recommendation_learning_loop import (
        FEATURE_REGISTRY_HASH,
        FEATURE_SCHEMA,
        _natural_receipt,
    )
    from test_recommendation_service_calibration_integration import (
        _verified_candidate,
    )

    root = tmp_path_factory.mktemp("r026model-facts")
    trained, candidate_root, metadata = _verified_candidate(
        root,
        candidate_day="2026-06-01",
        training_as_of="2026-05-31",
    )
    natural_evidence = _natural_receipt(
        root,
        root=candidate_root,
        candidate_day="2026-06-01",
        evaluation_day="2026-07-27",
    )
    authority = RecommendationCalibrationPromotionAuthority(root / "authority")
    decision = authority.evaluate_and_apply(
        decision_date="2026-07-27",
        candidate_id=trained.candidate_id,
        candidate_root=candidate_root,
        candidate_metadata=metadata,
        natural_evidence=natural_evidence,
        data_status="ready",
        drift_status="clean",
    )
    assert decision.decision == "adopt"

    pointer_path = root / "authority" / "recommendation-calibration-active-pointer.json"
    consumer = RecommendationCalibrationConsumer(
        pointer_path=pointer_path,
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash=FEATURE_REGISTRY_HASH,
        data_root=root / "formal-data",
    )
    assert consumer.reload(decision_date="2026-07-27") == "active"
    return consumer, pointer_path, candidate_root


def _capability(
    consumer: RecommendationCalibrationConsumer,
    *,
    scope: str,
    identity: dict[str, Any],
) -> Any:
    return consumer.resolve_invocation_projection_capability(
        invocation_scope_id=scope,
        decision_date="2026-07-27",
        expected_identity=identity,
    )


def test_capability_carries_deep_immutable_same_resolve_model_evidence(
    active_context: tuple[RecommendationCalibrationConsumer, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    consumer, _pointer_path, candidate_root = active_context
    identity = consumer.active_identity(decision_date="2026-07-27")
    assert identity is not None
    capability = _capability(
        consumer, scope="resolution-facts-success-0001", identity=identity
    )
    assert capability is not None

    evidence = capability.model_resolution_evidence
    assert evidence.schema_version == "recommendation-model-resolution-evidence.v1"
    assert evidence.candidate.candidate_id == identity["candidate_id"]
    assert evidence.candidate.manifest_hash == identity["candidate_manifest_hash"]
    assert evidence.candidate.artifact_hash == identity["candidate_artifact_hash"]
    assert evidence.manifest.model_id == identity["model_id"]
    assert evidence.manifest.manifest_hash == identity["candidate_manifest_hash"]
    assert evidence.manifest.artifact_hash == identity["candidate_artifact_hash"]
    assert evidence.manifest.dataset_id
    assert evidence.manifest.feature_registry_hash
    assert evidence.manifest.label_registry_hash
    assert evidence.manifest.serialization_format
    assert evidence.manifest.recorded_library_versions
    assert type(evidence.manifest.research_alpha_bp) is int
    assert type(evidence.manifest.production_alpha_bp) is int
    assert evidence.manifest.blend_selection_metric
    assert evidence.manifest.blend_selection_label_cutoff
    assert type(evidence.manifest.blend_selection_threshold_bp) is int
    assert evidence.runtime_profile.library_versions
    assert evidence.manifest.recorded_library_versions != ()
    assert evidence.artifact.loaded_bytes_sha256 is None
    assert evidence.artifact.same_bytes_binding_status == "not_verified"
    assert evidence.artifact.hash_check_profile == (
        "path_hash_before_deserializer_reopen_then_path_recheck"
    )
    assert evidence.candidate.candidate_path_check == (
        "identity_rechecked_by_path_read_same_bytes_not_proven"
    )
    assert evidence.training.status == "verified"
    assert evidence.training.feature_transform_contract_hash is not None
    assert evidence.probability_lineage
    assert tuple(item.position for item in evidence.probability_lineage) == tuple(
        range(len(evidence.probability_lineage))
    )
    assert evidence.probability_lineage[-1].candidate_id == identity["candidate_id"]
    assert evidence.missing_model_binding.release_id is None
    assert evidence.missing_model_binding.artifact_declared_qualified_class_path is None
    assert evidence.missing_model_binding.quarantine_status == "unknown"
    assert evidence.missing_model_binding.permission_status == "unknown"
    assert evidence.model_binding_status == "incomplete_unknown_fields"

    manifest_payload = json.loads((candidate_root / "manifest.json").read_text(encoding="utf-8"))
    assert tuple(item.library for item in evidence.manifest.recorded_library_versions) == tuple(
        sorted(manifest_payload["library_versions"])
    )
    assert evidence.runtime_profile.library_versions is not evidence.manifest.recorded_library_versions
    assert tuple(item.library for item in evidence.runtime_profile.library_versions) == (
        "joblib",
        "numpy",
        "scikit-learn",
        "scipy",
    )
    assert len(evidence.evidence_sha256) == len("sha256:") + 64

    import builtins

    def no_io(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("model-resolution evidence access must not perform I/O")

    monkeypatch.setattr(builtins, "open", no_io)
    monkeypatch.setattr(Path, "open", no_io)
    monkeypatch.setattr(Path, "read_text", no_io)
    monkeypatch.setattr(Path, "read_bytes", no_io)
    assert capability.model_resolution_evidence is evidence
    assert evidence.to_payload()["evidence_sha256"] == evidence.evidence_sha256
    with pytest.raises((AttributeError, TypeError)):
        evidence.training.status = "verified-but-mutated"


def test_legacy_training_lineage_stays_unproven_in_model_evidence(
    active_context: tuple[RecommendationCalibrationConsumer, Path, Path],
) -> None:
    consumer, _pointer_path, candidate_root = active_context
    candidate_path = candidate_root / "candidate.json"
    original = candidate_path.read_bytes()
    payload = json.loads(original.decode("utf-8"))
    for key in (
        "training_lineage_manifest_hash",
        "training_lineage_manifest_path",
        "training_source_hash",
        "training_pit_hash",
        "feature_transform_contract",
        "feature_transform_contract_hash",
    ):
        payload.pop(key, None)
    candidate_path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    try:
        assert consumer.reload(decision_date="2026-07-27") == "active"
        identity = consumer.active_identity(decision_date="2026-07-27")
        assert identity is not None
        capability = _capability(
            consumer, scope="resolution-facts-legacy-0001", identity=identity
        )
        assert capability is not None
        assert capability.model_resolution_evidence.training.status == "legacy_unproven"
        assert capability.model_resolution_evidence.training.training_source_hash is None
        assert capability.model_resolution_evidence.training.training_pit_hash is None
        assert capability.model_resolution_evidence.training.feature_transform_contract_hash is None
        assert capability.model_resolution_evidence.missing_model_binding.transform_status == (
            "legacy_unproven"
        )
    finally:
        candidate_path.write_bytes(original)


def test_candidate_manifest_mismatch_never_yields_model_evidence(
    active_context: tuple[RecommendationCalibrationConsumer, Path, Path],
) -> None:
    consumer, _pointer_path, candidate_root = active_context
    identity = consumer.active_identity(decision_date="2026-07-27")
    assert identity is not None
    candidate_path = candidate_root / "candidate.json"
    original = candidate_path.read_bytes()
    payload = json.loads(original.decode("utf-8"))
    payload["manifest_hash"] = "sha256:" + "f" * 64
    candidate_path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    try:
        assert (
            _capability(
                consumer,
                scope="resolution-facts-mismatch-0001",
                identity=identity,
            )
            is None
        )
    finally:
        candidate_path.write_bytes(original)


def test_malformed_model_resolution_claim_fails_closed_without_leaking_exception(
    active_context: tuple[RecommendationCalibrationConsumer, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    consumer, _pointer_path, _candidate_root = active_context
    identity = consumer.active_identity(decision_date="2026-07-27")
    assert identity is not None

    import app_module.recommendation_calibration_consumer as consumer_module

    original_factory = consumer_module.capture_model_resolution_evidence_v1

    def reject_claim(**kwargs: Any) -> Any:
        changed_payload = dict(kwargs["candidate_payload"])
        changed_payload["candidate_id"] = "malformed-claim"
        return original_factory(**{**kwargs, "candidate_payload": changed_payload})

    monkeypatch.setattr(
        consumer_module,
        "capture_model_resolution_evidence_v1",
        reject_claim,
    )
    assert (
        _capability(
            consumer,
            scope="resolution-facts-malformed-claim-0001",
            identity=identity,
        )
        is None
    )


def test_pointer_mutation_during_safe_resolve_prevents_evidence_publication(
    active_context: tuple[RecommendationCalibrationConsumer, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    consumer, pointer_path, _candidate_root = active_context
    identity = consumer.active_identity(decision_date="2026-07-27")
    assert identity is not None
    original_pointer = pointer_path.read_bytes()
    from ml_module.model_artifact_loader import SafeShadowModelArtifactLoader

    original_load = SafeShadowModelArtifactLoader.load

    def mutate_after_load(
        loader: SafeShadowModelArtifactLoader,
        artifact_root: str | Path,
        *,
        expectation: Any,
    ) -> Any:
        result = original_load(loader, artifact_root, expectation=expectation)
        changed = json.loads(original_pointer.decode("utf-8"))
        changed["candidate_id"] = "mutated-during-resolve"
        pointer_path.write_text(
            json.dumps(changed, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        return result

    monkeypatch.setattr(SafeShadowModelArtifactLoader, "load", mutate_after_load)
    try:
        assert (
            _capability(
                consumer,
                scope="resolution-facts-pointer-race-0001",
                identity=identity,
            )
            is None
        )
    finally:
        pointer_path.write_bytes(original_pointer)


def test_ab_resolutions_return_separate_immutable_evidence_objects(
    active_context: tuple[RecommendationCalibrationConsumer, Path, Path],
) -> None:
    consumer, _pointer_path, _candidate_root = active_context
    identity = consumer.active_identity(decision_date="2026-07-27")
    assert identity is not None
    first = _capability(
        consumer, scope="resolution-facts-ab-a-0001", identity=identity
    )
    second = _capability(
        consumer, scope="resolution-facts-ab-b-0001", identity=identity
    )
    assert first is not None and second is not None
    first_evidence = first.model_resolution_evidence
    second_evidence = second.model_resolution_evidence
    assert first_evidence is not second_evidence
    assert first_evidence == second_evidence
    assert first_evidence.probability_lineage is not second_evidence.probability_lineage
    assert first._resolved_consumer_for_isolation()._model_resolution_capture_inputs is None
    assert second._resolved_consumer_for_isolation()._model_resolution_capture_inputs is None
    assert first.model_resolution_evidence is first_evidence
    assert second.model_resolution_evidence is second_evidence
