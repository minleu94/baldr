from __future__ import annotations

from copy import copy, deepcopy
import hashlib
import os
from pathlib import Path
import json
import pickle
import re
from typing import Any, Mapping

import pytest

from app_module.recommendation_calibration_consumer import (
    RecommendationCalibrationConsumer,
)


@pytest.fixture(scope="module")
def active_consumer(tmp_path_factory: pytest.TempPathFactory) -> tuple[Any, Path, Path]:
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

    root = tmp_path_factory.mktemp("r26cap")
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


def _capability(consumer: Any, *, scope: str, identity: dict[str, Any]) -> Any:
    return consumer.resolve_invocation_projection_capability(
        invocation_scope_id=scope,
        decision_date="2026-07-27",
        expected_identity=identity,
    )


def _project(
    capability: Any,
    consumer: Any,
    *,
    scope: str,
    identity: dict[str, Any],
    inference_provenance: dict[str, Any] | None = None,
) -> Any:
    from test_daily_recommendation_learning_loop import FEATURE_SCHEMA

    return capability.project_many(
        owner=consumer,
        invocation_scope_id=scope,
        expected_identity=identity,
        feature_values_by_symbol={"AAA": tuple(0 for _ in FEATURE_SCHEMA)},
        rule_probability_by_symbol={"AAA": 5_000},
        decision_date="2026-07-27",
        inference_provenance=inference_provenance,
    )


def _legacy_project(consumer: Any) -> Any:
    from test_daily_recommendation_learning_loop import FEATURE_SCHEMA

    return consumer.project_many(
        feature_values_by_symbol={"AAA": tuple(0 for _ in FEATURE_SCHEMA)},
        rule_probability_by_symbol={"AAA": 5_000},
        decision_date="2026-07-27",
    )


def _write_pointer_with_valid_receipt(pointer_path: Path, pointer: dict[str, Any]) -> None:
    """Rewrite a synthetic pointer and its matching receipt content binding."""

    import hashlib

    receipt_path = Path(str(pointer["decision_receipt_path"]))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    pointer_base = {
        key: value
        for key, value in pointer.items()
        if key not in {"decision_receipt_path", "decision_receipt_hash"}
    }
    canonical_pointer = json.dumps(
        pointer_base,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    receipt["pointer_content_hash"] = "sha256:" + hashlib.sha256(
        canonical_pointer
    ).hexdigest()
    receipt_bytes = (
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    receipt_path.write_bytes(receipt_bytes)
    pointer["decision_receipt_hash"] = "sha256:" + hashlib.sha256(
        receipt_bytes
    ).hexdigest()
    pointer_path.write_text(
        json.dumps(pointer, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("candidate_root", r"C:\conflicting\candidate"),
        ("candidate_manifest_hash", "sha256:" + "f" * 64),
        ("candidate_artifact_hash", "sha256:" + "e" * 64),
        ("candidate_freeze_hash", "sha256:" + "d" * 64),
        ("dataset_hash", "sha256:" + "c" * 64),
    ],
)
def test_capability_rejects_same_id_active_lineage_identity_conflict(
    active_consumer: tuple[Any, Path, Path],
    field: str,
    replacement: str,
) -> None:
    consumer, pointer_path, _candidate_root = active_consumer
    original_pointer_bytes = pointer_path.read_bytes()
    original_pointer = json.loads(original_pointer_bytes.decode("utf-8"))
    original_receipt_path = Path(str(original_pointer["decision_receipt_path"]))
    original_receipt_bytes = original_receipt_path.read_bytes()
    try:
        pointer = json.loads(original_pointer_bytes.decode("utf-8"))
        lineage = pointer["probability_lineage"]
        active_node = lineage[-1]
        assert active_node["candidate_id"] == pointer["candidate_id"]
        active_node[field] = replacement
        _write_pointer_with_valid_receipt(pointer_path, pointer)

        # 舊一般 reload 仍保留原相容路徑；只有 capability resolve 須拒絕矛盾。
        assert consumer.reload(decision_date="2026-07-27") == "active"
        identity = consumer.active_identity(decision_date="2026-07-27")
        assert identity is not None
        assert (
            _capability(
                consumer,
                scope=f"live-call-lineage-conflict-{field}",
                identity=identity,
            )
            is None
        )
    finally:
        original_receipt_path.write_bytes(original_receipt_bytes)
        pointer_path.write_bytes(original_pointer_bytes)
        assert consumer.reload(decision_date="2026-07-27") == "active"


def test_capability_rejects_repeated_active_id_before_terminal_lineage_node(
    active_consumer: tuple[Any, Path, Path]
) -> None:
    consumer, pointer_path, _candidate_root = active_consumer
    original_pointer_bytes = pointer_path.read_bytes()
    original_pointer = json.loads(original_pointer_bytes.decode("utf-8"))
    original_receipt_path = Path(str(original_pointer["decision_receipt_path"]))
    original_receipt_bytes = original_receipt_path.read_bytes()
    try:
        pointer = json.loads(original_pointer_bytes.decode("utf-8"))
        active_node = dict(pointer["probability_lineage"][-1])
        active_node["baseline_id"] = str(active_node["candidate_id"])
        active_node["baseline_kind"] = "active_model"
        pointer["probability_lineage"].append(active_node)
        _write_pointer_with_valid_receipt(pointer_path, pointer)

        assert consumer.reload(decision_date="2026-07-27") == "active"
        identity = consumer.active_identity(decision_date="2026-07-27")
        assert identity is not None
        assert (
            _capability(
                consumer,
                scope="live-call-repeated-active-lineage-0001",
                identity=identity,
            )
            is None
        )
    finally:
        original_receipt_path.write_bytes(original_receipt_bytes)
        pointer_path.write_bytes(original_pointer_bytes)
        assert consumer.reload(decision_date="2026-07-27") == "active"


def test_capability_uses_fresh_model_lineage_and_no_projection_time_io(
    active_consumer: tuple[Any, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    consumer, _pointer_path, _candidate_root = active_consumer
    identity = consumer.active_identity(decision_date="2026-07-27")
    assert identity is not None
    legacy_projection = _legacy_project(consumer)
    identity_for_use = deepcopy(identity)
    capability = _capability(
        consumer, scope="live-call-a-0001", identity=identity
    )
    assert capability is not None
    artifact_evidence = capability.loaded_artifact_lineage
    assert tuple(node.kind for node in artifact_evidence.nodes) == (
        "null_benchmark",
        "active_model",
    )
    active_artifact = artifact_evidence.nodes[-1]
    import hashlib

    manifest = json.loads((_candidate_root / "manifest.json").read_text(encoding="utf-8"))
    artifact_path = _candidate_root / str(manifest["artifact_filename"])
    assert active_artifact.loaded_serialized_bytes_sha256 == (
        "sha256:" + hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    )
    assert active_artifact.loaded_serialized_bytes_sha256 == (
        active_artifact.declared_artifact_hash
    )
    assert capability.model_resolution_evidence.artifact.loaded_bytes_sha256 is None

    resolved = capability._InvocationProjectionCapability__resolved_consumer
    assert resolved is not consumer
    assert resolved._model is not consumer._model
    assert len(resolved._lineage_models) == len(consumer._lineage_models)
    assert all(
        resolved_node is not original_node
        and resolved_model is not original_model
        for (resolved_node, resolved_model), (original_node, original_model)
        in zip(resolved._lineage_models, consumer._lineage_models, strict=True)
    )
    for field_name in (
        "return_model",
        "upside_model",
        "after_cost_model",
        "upside_calibrator",
        "after_cost_calibrator",
    ):
        original_component = getattr(consumer._model, field_name)
        resolved_component = getattr(resolved._model, field_name)
        if original_component is not None:
            assert resolved_component is not original_component

    original_kind = consumer._probability_lineage[0]["kind"]
    identity["probability_lineage"][0]["kind"] = "caller_mutation"
    consumer._probability_lineage[0]["kind"] = "owner_mutation"

    import app_module.recommendation_calibration_consumer as consumer_module
    from ml_module.model_artifact_loader import SafeShadowModelArtifactLoader

    def no_path_stat(_path: Path) -> None:
        pytest.fail("capability projection must not stat pointer or artifact paths")

    def no_loader(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("capability projection must not reload an artifact")

    monkeypatch.setattr(consumer_module, "_path_stat", no_path_stat)
    monkeypatch.setattr(SafeShadowModelArtifactLoader, "load", no_loader)
    monkeypatch.setattr(SafeShadowModelArtifactLoader, "load_same_bytes_v1", no_loader)
    monkeypatch.setattr(
        SafeShadowModelArtifactLoader,
        "load_same_bytes_with_manifest_v1",
        no_loader,
    )
    try:
        projections = _project(
            capability,
            consumer,
            scope="live-call-a-0001",
            identity=identity_for_use,
        )
    finally:
        consumer._probability_lineage[0]["kind"] = original_kind

    assert projections["AAA"].status == "active_candidate"
    assert projections["AAA"].to_dict() == legacy_projection["AAA"].to_dict()
    with pytest.raises(RuntimeError, match="already consumed"):
        _project(
            capability,
            consumer,
            scope="live-call-a-0001",
            identity=identity_for_use,
        )


def test_capability_captures_ordered_same_bytes_lineage_without_partial_failure(
    active_consumer: tuple[Any, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hashlib

    from app_module.recommendation_calibration_consumer import (
        NULL_BENCHMARK_BASELINE_ID,
        _model_lineage_node,
    )
    from ml_module.model_artifact_loader import SafeShadowModelArtifactLoader
    from test_recommendation_service_calibration_integration import _verified_candidate

    consumer, pointer_path, active_root = active_consumer
    root = active_root.parent
    ancestor_model, ancestor_root, ancestor_metadata = _verified_candidate(
        root / "ancestor-package",
        candidate_day="2026-06-01",
        training_as_of="2026-05-31",
        dataset_id="dataset-capability-ancestor",
    )
    ancestor_identity = dict(ancestor_metadata)
    ancestor_identity["candidate_root"] = str(ancestor_root.resolve())
    ancestor_identity["candidate_manifest_hash"] = ancestor_metadata["manifest_hash"]
    ancestor_identity["candidate_artifact_hash"] = ancestor_metadata["artifact_hash"]

    original_pointer_bytes = pointer_path.read_bytes()
    pointer = json.loads(original_pointer_bytes.decode("utf-8"))
    original_receipt_path = Path(str(pointer["decision_receipt_path"]))
    original_receipt_bytes = original_receipt_path.read_bytes()
    ancestor_manifest_path = ancestor_root / "manifest.json"
    original_ancestor_manifest_bytes = ancestor_manifest_path.read_bytes()
    ancestor_manifest = json.loads(original_ancestor_manifest_bytes.decode("utf-8"))
    ancestor_artifact_path = ancestor_root / str(ancestor_manifest["artifact_filename"])
    original_ancestor_artifact = ancestor_artifact_path.read_bytes()
    ancestor_candidate_path = ancestor_root / "candidate.json"
    original_ancestor_candidate_bytes = ancestor_candidate_path.read_bytes()
    active_candidate_bytes = (active_root / "candidate.json").read_bytes()
    original_same_bytes = SafeShadowModelArtifactLoader.load_same_bytes_with_manifest_v1
    original_legacy_load = SafeShadowModelArtifactLoader.load
    try:
        lineage = pointer["probability_lineage"]
        null_node = dict(lineage[0])
        active_node = dict(lineage[-1])
        ancestor_node = _model_lineage_node(
            ancestor_identity,
            baseline_id=NULL_BENCHMARK_BASELINE_ID,
            baseline_kind="null_benchmark",
            cap=int(pointer["maximum_probability_change_bp"]),
        )
        active_node["baseline_id"] = str(ancestor_model.candidate_id)
        active_node["baseline_kind"] = "active_model"
        pointer["probability_lineage"] = [null_node, ancestor_node, active_node]
        _write_pointer_with_valid_receipt(pointer_path, pointer)
        assert consumer.reload(decision_date="2026-07-27") == "active", consumer._blocker
        identity = consumer.active_identity(decision_date="2026-07-27")
        assert identity is not None

        same_byte_loads: list[Path] = []
        def record_same_bytes_load(
            loader: SafeShadowModelArtifactLoader,
            artifact_root: str | Path,
            *,
            expectation: Any,
        ) -> Any:
            same_byte_loads.append(Path(artifact_root).resolve())
            return original_same_bytes(
                loader, artifact_root, expectation=expectation
            )

        def legacy_loader_must_not_be_used(*_args: Any, **_kwargs: Any) -> Any:
            pytest.fail("fresh capability must use the opt-in same-bytes loader")

        monkeypatch.setattr(
            SafeShadowModelArtifactLoader,
            "load_same_bytes_with_manifest_v1",
            record_same_bytes_load,
        )
        monkeypatch.setattr(
            SafeShadowModelArtifactLoader, "load", legacy_loader_must_not_be_used
        )
        capability = _capability(
            consumer,
            scope="live-call-artifact-lineage-success-0001",
            identity=identity,
        )
        assert capability is not None
        evidence = capability.loaded_artifact_lineage
        assert tuple(node.candidate_id for node in evidence.nodes) == (
            None,
            str(ancestor_model.candidate_id),
            str(pointer["candidate_id"]),
        )
        candidate_evidence = capability.candidate_json_bytes_lineage
        assert candidate_evidence.schema_version == (
            "recommendation-capability-candidate-json-bytes.v1"
        )
        assert tuple(node.candidate_id for node in candidate_evidence.nodes) == (
            None,
            str(ancestor_model.candidate_id),
            str(pointer["candidate_id"]),
        )
        assert candidate_evidence.nodes[0].raw_bytes_sha256 is None
        assert candidate_evidence.nodes[1].raw_bytes_sha256 == (
            "sha256:" + hashlib.sha256(original_ancestor_candidate_bytes).hexdigest()
        )
        assert candidate_evidence.nodes[2].raw_bytes_sha256 == (
            "sha256:" + hashlib.sha256(active_candidate_bytes).hexdigest()
        )
        assert candidate_evidence.nodes[1].canonical_payload_sha256 == (
            _canonical_pointer_payload_sha256(
                json.loads(original_ancestor_candidate_bytes.decode("utf-8"))
            )
        )
        manifest_evidence = capability.model_manifest_bytes_lineage
        assert manifest_evidence.schema_version == (
            "recommendation-capability-model-manifest-bytes.v1"
        )
        assert tuple(node.candidate_id for node in manifest_evidence.nodes) == (
            None,
            str(ancestor_model.candidate_id),
            str(pointer["candidate_id"]),
        )
        active_manifest_bytes = (active_root / "manifest.json").read_bytes()
        ancestor_manifest_bytes = (ancestor_root / "manifest.json").read_bytes()
        assert manifest_evidence.nodes[0].raw_bytes_sha256 is None
        assert manifest_evidence.nodes[1].raw_bytes_sha256 == (
            "sha256:" + hashlib.sha256(ancestor_manifest_bytes).hexdigest()
        )
        assert manifest_evidence.nodes[2].raw_bytes_sha256 == (
            "sha256:" + hashlib.sha256(active_manifest_bytes).hexdigest()
        )
        assert manifest_evidence.nodes[1].canonical_manifest_hash == (
            ancestor_identity["candidate_manifest_hash"]
        )
        assert manifest_evidence.nodes[2].canonical_manifest_hash == (
            pointer["candidate_manifest_hash"]
        )
        assert same_byte_loads == [active_root.resolve(), ancestor_root.resolve()]
        assert evidence.nodes[1].loaded_serialized_bytes_sha256 == (
            "sha256:" + hashlib.sha256(original_ancestor_artifact).hexdigest()
        )
        assert evidence.nodes[2].loaded_serialized_bytes_sha256 == (
            evidence.nodes[2].declared_artifact_hash
        )
        assert evidence.evidence_sha256.startswith("sha256:")
        exported = evidence.to_payload()
        exported["nodes"][1]["candidate_id"] = "caller-mutation"
        assert evidence.nodes[1].candidate_id == str(ancestor_model.candidate_id)
        from dataclasses import FrozenInstanceError

        with pytest.raises(FrozenInstanceError):
            evidence.nodes[1].candidate_id = "caller-mutation"  # type: ignore[misc]

        live_capability_count = len(consumer._invocation_capabilities)
        replacement_manifest_bytes = original_ancestor_manifest_bytes + b" \n"

        def load_then_replace_ancestor_manifest(
            loader: SafeShadowModelArtifactLoader,
            artifact_root: str | Path,
            *,
            expectation: Any,
        ) -> Any:
            result = original_same_bytes(
                loader, artifact_root, expectation=expectation
            )
            if Path(artifact_root).resolve() == ancestor_root.resolve():
                ancestor_manifest_path.write_bytes(replacement_manifest_bytes)
            return result

        monkeypatch.setattr(
            SafeShadowModelArtifactLoader,
            "load_same_bytes_with_manifest_v1",
            load_then_replace_ancestor_manifest,
        )
        failed_manifest_capability = _capability(
            consumer,
            scope="live-call-manifest-lineage-ancestor-swap-0001",
            identity=identity,
        )
        assert failed_manifest_capability is None
        assert ancestor_manifest_path.read_bytes() == replacement_manifest_bytes
        assert len(consumer._invocation_capabilities) == live_capability_count
        ancestor_manifest_path.write_bytes(original_ancestor_manifest_bytes)
        monkeypatch.setattr(
            SafeShadowModelArtifactLoader,
            "load_same_bytes_with_manifest_v1",
            record_same_bytes_load,
        )

        ancestor_artifact_path.write_bytes(original_ancestor_artifact + b"changed")
        failed_capability = _capability(
            consumer,
            scope="live-call-artifact-lineage-ancestor-failure-0001",
            identity=identity,
        )
        assert failed_capability is None
        assert len(consumer._invocation_capabilities) == live_capability_count
        assert len(capability.loaded_artifact_lineage.nodes) == 3
    finally:
        monkeypatch.setattr(
            SafeShadowModelArtifactLoader, "load", original_legacy_load
        )
        monkeypatch.setattr(
            SafeShadowModelArtifactLoader,
            "load_same_bytes_with_manifest_v1",
            original_same_bytes,
        )
        ancestor_artifact_path.write_bytes(original_ancestor_artifact)
        ancestor_manifest_path.write_bytes(original_ancestor_manifest_bytes)
        original_receipt_path.write_bytes(original_receipt_bytes)
        pointer_path.write_bytes(original_pointer_bytes)
        assert consumer.reload(decision_date="2026-07-27") == "active"


def test_capability_rechecks_captured_manifest_bytes_before_return(
    active_consumer: tuple[Any, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from ml_module.model_artifact_loader import SafeShadowModelArtifactLoader

    consumer, _pointer_path, candidate_root = active_consumer
    identity = consumer.active_identity(decision_date="2026-07-27")
    assert identity is not None
    manifest_path = candidate_root / "manifest.json"
    original_bytes = manifest_path.read_bytes()
    replacement_bytes = original_bytes + b" \n"
    assert replacement_bytes != original_bytes
    assert json.loads(replacement_bytes.decode("utf-8")) == json.loads(
        original_bytes.decode("utf-8")
    )
    original_load = SafeShadowModelArtifactLoader.load_same_bytes_with_manifest_v1
    replaced = False

    def capture_then_replace_manifest(
        loader: SafeShadowModelArtifactLoader,
        artifact_root: str | Path,
        *,
        expectation: Any,
    ) -> Any:
        nonlocal replaced
        result = original_load(loader, artifact_root, expectation=expectation)
        if Path(artifact_root).resolve() == candidate_root.resolve():
            manifest_path.write_bytes(replacement_bytes)
            replaced = True
        return result

    monkeypatch.setattr(
        SafeShadowModelArtifactLoader,
        "load_same_bytes_with_manifest_v1",
        capture_then_replace_manifest,
    )
    try:
        capability = _capability(
            consumer,
            scope="live-call-active-manifest-swap-0001",
            identity=identity,
        )
        assert capability is None
        assert replaced
        assert manifest_path.read_bytes() == replacement_bytes
    finally:
        manifest_path.write_bytes(original_bytes)
    assert consumer.reload(decision_date="2026-07-27") == "active"


def test_capability_rejects_filesystem_bound_provenance_without_io(
    active_consumer: tuple[Any, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    consumer, _pointer_path, _candidate_root = active_consumer
    identity = consumer.active_identity(decision_date="2026-07-27")
    assert identity is not None
    capability = _capability(consumer, scope="live-call-source-bound-0001", identity=identity)
    assert capability is not None

    def no_filesystem(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("capability rejected the binding before provenance filesystem access")

    import builtins
    from ml_module.model_artifact_loader import SafeShadowModelArtifactLoader

    monkeypatch.setattr(builtins, "open", no_filesystem)
    monkeypatch.setattr(Path, "open", no_filesystem)
    monkeypatch.setattr(Path, "read_text", no_filesystem)
    monkeypatch.setattr(Path, "is_file", no_filesystem)
    monkeypatch.setattr(Path, "stat", no_filesystem)
    monkeypatch.setattr(Path, "resolve", no_filesystem)
    monkeypatch.setattr(SafeShadowModelArtifactLoader, "load", no_filesystem)
    with pytest.raises(ValueError, match="filesystem-bound source contracts"):
        _project(
            capability,
            consumer,
            scope="live-call-source-bound-0001",
            identity=identity,
            inference_provenance={"source_contract_binding": {"schema_version": "synthetic"}},
        )


def test_capability_rejects_unreviewed_runtime_before_pointer_or_loader_io(
    active_consumer: tuple[Any, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    import app_module.recommendation_calibration_consumer as consumer_module
    from ml_module.model_artifact_loader import SafeShadowModelArtifactLoader

    consumer, _pointer_path, _candidate_root = active_consumer
    identity = consumer.active_identity(decision_date="2026-07-27")
    assert identity is not None

    def no_io(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("unsupported runtime must be rejected before pointer/loader I/O")

    monkeypatch.setattr(consumer_module.np, "__version__", "999.0")
    monkeypatch.setattr(Path, "read_bytes", no_io)
    monkeypatch.setattr(SafeShadowModelArtifactLoader, "load", no_io)
    assert (
        _capability(
            consumer,
            scope="live-call-unreviewed-runtime-0001",
            identity=identity,
        )
        is None
    )
    assert _legacy_project(consumer)["AAA"].status == "active_candidate"


def test_capability_uses_fresh_pointer_bytes_even_if_owner_stat_cache_matches(
    active_consumer: tuple[Any, Path, Path]
) -> None:
    consumer, pointer_path, _candidate_root = active_consumer
    identity = consumer.active_identity(decision_date="2026-07-27")
    assert identity is not None
    original_bytes = pointer_path.read_bytes()
    original_stat = pointer_path.stat()
    try:
        pointer = json.loads(original_bytes.decode("utf-8"))
        candidate_id = str(pointer["candidate_id"])
        changed_bytes = re.sub(
            rb'("candidate_id"\s*:\s*)"[^"]+"',
            lambda match: match.group(1)
            + json.dumps("x" * len(candidate_id)).encode("utf-8"),
            original_bytes,
            count=1,
        )
        assert len(changed_bytes) == len(original_bytes)
        pointer_path.write_bytes(changed_bytes)
        os.utime(
            pointer_path,
            ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
        )
        assert pointer_path.stat().st_size == original_stat.st_size
        assert pointer_path.stat().st_mtime_ns == original_stat.st_mtime_ns
        # The legacy cached accessor can still see its previous snapshot; the
        # capability resolver must bypass that stat cache and safe-load bytes.
        assert consumer.active_identity(decision_date="2026-07-27") == identity
        assert (
            _capability(
                consumer,
                scope="live-call-same-stat-stale-pointer-0001",
                identity=identity,
            )
            is None
        )
    finally:
        pointer_path.write_bytes(original_bytes)
        os.utime(
            pointer_path,
            ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
        )
    assert consumer.reload(decision_date="2026-07-27") == "active"


def _replace_pointer_only_during_fresh_capability_reload(
    *,
    consumer: Any,
    pointer_path: Path,
    original_bytes: bytes,
    replacement_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[str, Mapping[str, Any] | None]]:
    original_reload = RecommendationCalibrationConsumer.reload
    observed: list[tuple[str, Mapping[str, Any] | None]] = []

    def replace_then_reload(
        self: RecommendationCalibrationConsumer,
        *,
        decision_date: str | None = None,
    ) -> str:
        if self is consumer:
            return original_reload(self, decision_date=decision_date)
        pointer_path.write_bytes(replacement_bytes)
        try:
            result = original_reload(self, decision_date=decision_date)
            observed.append((result, self._loaded_pointer))
            return result
        finally:
            pointer_path.write_bytes(original_bytes)

    monkeypatch.setattr(RecommendationCalibrationConsumer, "reload", replace_then_reload)
    return observed


def _canonical_pointer_payload_sha256(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def test_capability_reload_uses_captured_pointer_if_path_changes_and_is_restored(
    active_consumer: tuple[Any, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    consumer, pointer_path, _candidate_root = active_consumer
    identity = consumer.active_identity(decision_date="2026-07-27")
    assert identity is not None
    original_bytes = pointer_path.read_bytes()
    original_pointer = json.loads(original_bytes.decode("utf-8"))
    replacement_pointer = dict(original_pointer)
    replacement_pointer["status"] = "rule_only"
    replacement_pointer["rollback_reason"] = "synthetic_transient_pointer"
    replacement_bytes = json.dumps(
        replacement_pointer, ensure_ascii=False, sort_keys=True
    ).encode("utf-8")
    assert json.loads(replacement_bytes.decode("utf-8")) != original_pointer

    observed = _replace_pointer_only_during_fresh_capability_reload(
        consumer=consumer,
        pointer_path=pointer_path,
        original_bytes=original_bytes,
        replacement_bytes=replacement_bytes,
        monkeypatch=monkeypatch,
    )
    capability = _capability(
        consumer,
        scope="live-call-captured-pointer-replacement-0001",
        identity=identity,
    )

    assert observed and all(
        result == "active" and loaded_pointer == original_pointer
        for result, loaded_pointer in observed
    )
    assert capability is not None
    evidence = capability.pointer_bytes_evidence
    assert evidence.raw_bytes_sha256 == (
        "sha256:" + hashlib.sha256(original_bytes).hexdigest()
    )
    assert evidence.canonical_payload_sha256 == _canonical_pointer_payload_sha256(
        original_pointer
    )
    assert pointer_path.read_bytes() == original_bytes


def test_capability_pointer_evidence_distinguishes_raw_and_canonical_bytes(
    active_consumer: tuple[Any, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    import app_module.recommendation_calibration_consumer as consumer_module

    consumer, pointer_path, _candidate_root = active_consumer
    identity = consumer.active_identity(decision_date="2026-07-27")
    assert identity is not None
    original_bytes = pointer_path.read_bytes()
    original_pointer = json.loads(original_bytes.decode("utf-8"))
    same_payload_bytes = json.dumps(
        original_pointer,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert same_payload_bytes != original_bytes
    assert json.loads(same_payload_bytes.decode("utf-8")) == original_pointer
    assert hashlib.sha256(same_payload_bytes).digest() != hashlib.sha256(
        original_bytes
    ).digest()

    observed = _replace_pointer_only_during_fresh_capability_reload(
        consumer=consumer,
        pointer_path=pointer_path,
        original_bytes=original_bytes,
        replacement_bytes=same_payload_bytes,
        monkeypatch=monkeypatch,
    )
    original_loads = json.loads
    pointer_json_inputs: list[str] = []

    def record_pointer_json_input(value: Any, *args: Any, **kwargs: Any) -> Any:
        result = original_loads(value, *args, **kwargs)
        if isinstance(result, dict) and result == original_pointer:
            pointer_json_inputs.append(
                value.decode("utf-8") if isinstance(value, bytes) else value
            )
        return result

    monkeypatch.setattr(consumer_module.json, "loads", record_pointer_json_input)
    capability = _capability(
        consumer,
        scope="live-call-captured-pointer-format-0001",
        identity=identity,
    )

    assert observed and all(
        result == "active" and loaded_pointer == original_pointer
        for result, loaded_pointer in observed
    )
    assert capability is not None
    # The outer identity parse and the fresh consumer reload must both consume
    # the originally captured serialization, even while the path temporarily
    # contains different bytes with the same JSON value.
    assert len(pointer_json_inputs) >= 2
    assert all(value == original_bytes.decode("utf-8") for value in pointer_json_inputs)
    evidence = capability.pointer_bytes_evidence
    assert evidence.raw_bytes_sha256 == (
        "sha256:" + hashlib.sha256(original_bytes).hexdigest()
    )
    assert evidence.canonical_payload_sha256 == _canonical_pointer_payload_sha256(
        original_pointer
    )
    assert evidence.canonical_payload_sha256 == _canonical_pointer_payload_sha256(
        json.loads(same_payload_bytes.decode("utf-8"))
    )
    assert evidence.raw_bytes_sha256 != (
        "sha256:" + hashlib.sha256(same_payload_bytes).hexdigest()
    )
    assert pointer_path.read_bytes() == original_bytes


def test_pointer_capture_does_not_change_legacy_reload_or_projection(
    active_consumer: tuple[Any, Path, Path]
) -> None:
    consumer, pointer_path, _candidate_root = active_consumer
    identity = consumer.active_identity(decision_date="2026-07-27")
    assert identity is not None
    original_bytes = pointer_path.read_bytes()
    before = _legacy_project(consumer)["AAA"]

    capability = _capability(
        consumer,
        scope="live-call-capture-legacy-isolation-0001",
        identity=identity,
    )

    assert capability is not None
    assert pointer_path.read_bytes() == original_bytes
    assert consumer.active_identity(decision_date="2026-07-27") == identity
    assert consumer.reload(decision_date="2026-07-27") == "active"
    after = _legacy_project(consumer)["AAA"]
    assert after == before
    assert getattr(consumer, "_captured_pointer_bytes_for_reload", None) is None


def test_active_candidate_json_changed_after_capture_fails_closed(
    active_consumer: tuple[Any, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    import app_module.recommendation_calibration_consumer as consumer_module

    consumer, _pointer_path, candidate_root = active_consumer
    identity = consumer.active_identity(decision_date="2026-07-27")
    assert identity is not None
    candidate_path = candidate_root / "candidate.json"
    original_bytes = candidate_path.read_bytes()
    original_text = original_bytes.decode("utf-8")
    payload = json.loads(original_text)
    replacement_payload = dict(payload)
    replacement_payload["transient_unbound_claim"] = "different-content"
    replacement_bytes = json.dumps(
        replacement_payload, ensure_ascii=False, sort_keys=True
    ).encode("utf-8")
    assert replacement_bytes != original_bytes
    parsed_candidate_inputs: list[str] = []
    original_loads = json.loads

    def replace_after_candidate_parse(value: Any, *args: Any, **kwargs: Any) -> Any:
        result = original_loads(value, *args, **kwargs)
        if isinstance(result, dict) and result == payload:
            parsed_candidate_inputs.append(
                value.decode("utf-8") if isinstance(value, bytes) else value
            )
            candidate_path.write_bytes(replacement_bytes)
        return result

    monkeypatch.setattr(consumer_module.json, "loads", replace_after_candidate_parse)
    try:
        capability = _capability(
            consumer,
            scope="live-call-active-candidate-json-swap-0001",
            identity=identity,
        )
        assert capability is None
        assert parsed_candidate_inputs == [original_text]
        assert candidate_path.read_bytes() == replacement_bytes
    finally:
        candidate_path.write_bytes(original_bytes)


def test_active_candidate_json_same_payload_different_bytes_fails_closed(
    active_consumer: tuple[Any, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    import app_module.recommendation_calibration_consumer as consumer_module

    consumer, _pointer_path, candidate_root = active_consumer
    identity = consumer.active_identity(decision_date="2026-07-27")
    assert identity is not None
    candidate_path = candidate_root / "candidate.json"
    original_bytes = candidate_path.read_bytes()
    original_text = original_bytes.decode("utf-8")
    payload = json.loads(original_text)
    replacement_bytes = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    assert replacement_bytes != original_bytes
    assert json.loads(replacement_bytes.decode("utf-8")) == payload
    parsed_candidate_inputs: list[str] = []
    original_loads = json.loads

    def replace_after_candidate_parse(value: Any, *args: Any, **kwargs: Any) -> Any:
        result = original_loads(value, *args, **kwargs)
        if isinstance(result, dict) and result == payload:
            parsed_candidate_inputs.append(
                value.decode("utf-8") if isinstance(value, bytes) else value
            )
            candidate_path.write_bytes(replacement_bytes)
        return result

    monkeypatch.setattr(consumer_module.json, "loads", replace_after_candidate_parse)
    try:
        capability = _capability(
            consumer,
            scope="live-call-active-candidate-json-format-swap-0001",
            identity=identity,
        )
        assert capability is None
        assert parsed_candidate_inputs == [original_text]
        assert candidate_path.read_bytes() == replacement_bytes
    finally:
        candidate_path.write_bytes(original_bytes)


def test_active_candidate_json_is_parsed_from_captured_bytes_after_restore(
    active_consumer: tuple[Any, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    import app_module.recommendation_calibration_consumer as consumer_module

    consumer, _pointer_path, candidate_root = active_consumer
    identity = consumer.active_identity(decision_date="2026-07-27")
    assert identity is not None
    candidate_path = candidate_root / "candidate.json"
    original_bytes = candidate_path.read_bytes()
    original_text = original_bytes.decode("utf-8")
    payload = json.loads(original_text)
    replacement_payload = dict(payload)
    replacement_payload["temporary_unbound_claim"] = "during-parse"
    replacement_bytes = json.dumps(
        replacement_payload, ensure_ascii=False, sort_keys=True
    ).encode("utf-8")
    parsed_candidate_inputs: list[str] = []
    original_loads = json.loads

    def replace_during_candidate_parse(value: Any, *args: Any, **kwargs: Any) -> Any:
        is_candidate = isinstance(value, str) and value == original_text
        if is_candidate:
            parsed_candidate_inputs.append(value)
            candidate_path.write_bytes(replacement_bytes)
            try:
                return original_loads(value, *args, **kwargs)
            finally:
                candidate_path.write_bytes(original_bytes)
        return original_loads(value, *args, **kwargs)

    monkeypatch.setattr(consumer_module.json, "loads", replace_during_candidate_parse)
    capability = _capability(
        consumer,
        scope="live-call-active-candidate-json-transient-swap-0001",
        identity=identity,
    )

    assert capability is not None
    assert parsed_candidate_inputs == [original_text]
    assert candidate_path.read_bytes() == original_bytes
    node = capability.candidate_json_bytes_lineage.nodes[-1]
    assert node.raw_bytes_sha256 == (
        "sha256:" + hashlib.sha256(original_bytes).hexdigest()
    )
    assert node.canonical_payload_sha256 == _canonical_pointer_payload_sha256(payload)


def test_ancestor_candidate_json_tamper_fails_entire_capability(
    active_consumer: tuple[Any, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    import app_module.recommendation_calibration_consumer as consumer_module

    from app_module.recommendation_calibration_consumer import (
        NULL_BENCHMARK_BASELINE_ID,
        _model_lineage_node,
    )
    from test_recommendation_service_calibration_integration import _verified_candidate

    consumer, pointer_path, active_root = active_consumer
    root = active_root.parent
    ancestor_model, ancestor_root, ancestor_metadata = _verified_candidate(
        root / "ancestor-json-tamper-package",
        candidate_day="2026-06-01",
        training_as_of="2026-05-31",
        dataset_id="dataset-capability-ancestor-json-tamper",
    )
    ancestor_identity = dict(ancestor_metadata)
    ancestor_identity["candidate_root"] = str(ancestor_root.resolve())
    ancestor_identity["candidate_manifest_hash"] = ancestor_metadata["manifest_hash"]
    ancestor_identity["candidate_artifact_hash"] = ancestor_metadata["artifact_hash"]

    original_pointer_bytes = pointer_path.read_bytes()
    pointer = json.loads(original_pointer_bytes.decode("utf-8"))
    receipt_path = Path(str(pointer["decision_receipt_path"]))
    original_receipt_bytes = receipt_path.read_bytes()
    ancestor_candidate_path = ancestor_root / "candidate.json"
    original_ancestor_candidate_bytes = ancestor_candidate_path.read_bytes()
    original_ancestor_text = original_ancestor_candidate_bytes.decode("utf-8")
    ancestor_payload = json.loads(original_ancestor_text)
    replacement_payload = dict(ancestor_payload)
    replacement_payload["transient_unbound_claim"] = "ancestor-different-content"
    replacement_bytes = json.dumps(
        replacement_payload, ensure_ascii=False, sort_keys=True
    ).encode("utf-8")
    observed_candidate_inputs: list[str] = []
    original_loads = json.loads
    try:
        lineage = pointer["probability_lineage"]
        null_node = dict(lineage[0])
        active_node = dict(lineage[-1])
        ancestor_node = _model_lineage_node(
            ancestor_identity,
            baseline_id=NULL_BENCHMARK_BASELINE_ID,
            baseline_kind="null_benchmark",
            cap=int(pointer["maximum_probability_change_bp"]),
        )
        active_node["baseline_id"] = str(ancestor_model.candidate_id)
        active_node["baseline_kind"] = "active_model"
        pointer["probability_lineage"] = [null_node, ancestor_node, active_node]
        _write_pointer_with_valid_receipt(pointer_path, pointer)
        assert consumer.reload(decision_date="2026-07-27") == "active", consumer._blocker
        identity = consumer.active_identity(decision_date="2026-07-27")
        assert identity is not None

        def replace_after_ancestor_parse(
            value: Any, *args: Any, **kwargs: Any
        ) -> Any:
            result = original_loads(value, *args, **kwargs)
            if isinstance(value, str) and value == original_ancestor_text:
                observed_candidate_inputs.append(value)
                ancestor_candidate_path.write_bytes(replacement_bytes)
            return result

        monkeypatch.setattr(consumer_module.json, "loads", replace_after_ancestor_parse)
        capability = _capability(
            consumer,
            scope="live-call-ancestor-candidate-json-swap-0001",
            identity=identity,
        )

        assert capability is None
        assert observed_candidate_inputs == [original_ancestor_text]
        assert ancestor_candidate_path.read_bytes() == replacement_bytes
    finally:
        ancestor_candidate_path.write_bytes(original_ancestor_candidate_bytes)
        receipt_path.write_bytes(original_receipt_bytes)
        pointer_path.write_bytes(original_pointer_bytes)
        assert consumer.reload(decision_date="2026-07-27") == "active"


@pytest.mark.parametrize("reuse_kind", ["singleton", "nested_estimator"])
def test_capability_rejects_custom_memoizing_deserializers(
    active_consumer: tuple[Any, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    reuse_kind: str,
) -> None:
    consumer, _pointer_path, _candidate_root = active_consumer
    identity = consumer.active_identity(decision_date="2026-07-27")
    assert identity is not None
    source_model = consumer._model
    assert source_model is not None
    from ml_module.model_artifact_loader import SafeShadowModelArtifactLoader

    def unexpected_loader(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("custom deserializer must be rejected before artifact loading")

    monkeypatch.setattr(SafeShadowModelArtifactLoader, "load", unexpected_loader)
    original_deserializer = consumer._loader._deserializer
    try:
        if reuse_kind == "singleton":
            consumer._loader._deserializer = lambda _path: source_model
        else:
            assert getattr(source_model, "return_model", None) is not None
            consumer._loader._deserializer = lambda _path: _model_copy_with_shared_estimator(
                source_model
            )
        assert (
            _capability(
                consumer,
                scope=f"live-call-alias-{reuse_kind}-0001",
                identity=identity,
            )
            is None
        )
    finally:
        consumer._loader._deserializer = original_deserializer


def test_alias_guard_detects_a_shared_nested_estimator(
    active_consumer: tuple[Any, Path, Path]
) -> None:
    from app_module.recommendation_calibration_consumer import (
        _loaded_model_state_aliases,
    )

    source, _pointer_path, _candidate_root = active_consumer
    assert source._model is not None
    fresh = RecommendationCalibrationConsumer(
        pointer_path=source.pointer_path,
        feature_schema=source.feature_schema,
        feature_registry_hash=source.feature_registry_hash,
        data_root=source._loader._data_root,
    )
    fresh._model = _model_copy_with_shared_estimator(source._model)
    fresh._lineage_models = tuple(
        (dict(node), fresh._model if model is source._model else model)
        for node, model in source._lineage_models
    )
    assert _loaded_model_state_aliases(source, fresh)


@pytest.mark.parametrize(
    "alias_kind",
    [
        "nested_estimator",
        "nested_calibrator_estimator",
        "array_view",
        "interpolation_array_view",
        "training_provenance_dict",
        "pointer_lineage_list",
    ],
)
def test_alias_guard_detects_nested_mutable_graph_aliases(
    active_consumer: tuple[Any, Path, Path], alias_kind: str
) -> None:
    from app_module.recommendation_calibration_consumer import (
        _loaded_model_state_aliases,
    )

    source, _pointer_path, _candidate_root = active_consumer
    fresh = _consumer_with_deepcopied_loaded_state(source)
    assert source._model is not None and fresh._model is not None

    if alias_kind == "nested_estimator":
        source_estimator = source._model.return_model.steps[2][1]
        _replace_pipeline_step(fresh._model.return_model, "model", source_estimator)
    elif alias_kind == "nested_calibrator_estimator":
        object.__setattr__(
            fresh._model.upside_calibrator,
            "estimator",
            source._model.upside_calibrator.estimator,
        )
    elif alias_kind == "array_view":
        source_array = source._model.return_model.steps[0][1].statistics_
        fresh_array_view = source_array.view()
        fresh._model.return_model.steps[0][1].statistics_ = fresh_array_view
    elif alias_kind == "interpolation_array_view":
        source_array = source._model.upside_calibrator.estimator.f_.x
        fresh._model.upside_calibrator.estimator.f_.x = source_array.view()
    elif alias_kind == "training_provenance_dict":
        source_contract = source._training_provenance["feature_transform_contract"]
        fresh._training_provenance["feature_transform_contract"] = source_contract
    else:
        assert source._loaded_pointer is not None
        assert fresh._loaded_pointer is not None
        fresh._loaded_pointer["probability_lineage"] = source._loaded_pointer[
            "probability_lineage"
        ]

    assert _loaded_model_state_aliases(source, fresh)


def test_alias_guard_rejects_cycles_and_unknown_model_state(
    active_consumer: tuple[Any, Path, Path]
) -> None:
    from app_module.recommendation_calibration_consumer import (
        _loaded_model_state_aliases,
    )

    source, _pointer_path, _candidate_root = active_consumer
    cyclic = _consumer_with_deepcopied_loaded_state(source)
    cyclic._training_provenance["cycle"] = cyclic._training_provenance
    assert _loaded_model_state_aliases(source, cyclic)

    unknown = _consumer_with_deepcopied_loaded_state(source)
    assert unknown._model is not None
    unknown._model.return_model.unknown_mutable_state = object()
    assert _loaded_model_state_aliases(source, unknown)

    object_array = _consumer_with_deepcopied_loaded_state(source)
    assert object_array._model is not None
    import numpy as np

    object_array._model.return_model.steps[0][1].statistics_ = np.asarray(
        [object()], dtype=object
    )
    assert _loaded_model_state_aliases(source, object_array)

    callable_graph = _consumer_with_deepcopied_loaded_state(source)
    assert callable_graph._model is not None
    captured: list[int] = []

    def make_interpolator_callable() -> Any:
        state = captured

        def interpolator(_values: Any) -> Any:
            return state

        return interpolator

    callable_graph._model.upside_calibrator.estimator.f_._call = (
        make_interpolator_callable()
    )
    assert _loaded_model_state_aliases(source, callable_graph)

    oversized = _consumer_with_deepcopied_loaded_state(source)
    oversized._training_provenance["oversized_state"] = list(range(5000))
    assert _loaded_model_state_aliases(source, oversized)


def _unreviewed_interpolator(_values: Any) -> Any:
    return None


def test_interp1d_allowlist_does_not_follow_runtime_class_replacement(
    active_consumer: tuple[Any, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app_module.recommendation_calibration_consumer import (
        _loaded_model_state_aliases,
    )
    import app_module.recommendation_calibration_consumer as consumer_module

    source, _pointer_path, _candidate_root = active_consumer
    fresh = _consumer_with_deepcopied_loaded_state(source)
    assert fresh._model is not None
    unreviewed = _unreviewed_interpolator
    assert unreviewed.__closure__ is None

    # The allowlist is captured from the reviewed SciPy runtime at module load;
    # rebinding the class cannot make a new, closure-free callable trusted.
    monkeypatch.setattr(consumer_module._ScipyInterp1d, "_call_linear_np", unreviewed)
    fresh._model.upside_calibrator.estimator.f_._call = unreviewed
    assert _loaded_model_state_aliases(source, fresh)


def test_second_capability_rejects_nested_array_alias_with_live_capability(
    active_consumer: tuple[Any, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    consumer, _pointer_path, _candidate_root = active_consumer
    identity = consumer.active_identity(decision_date="2026-07-27")
    assert identity is not None
    first = _capability(consumer, scope="live-call-graph-a-0001", identity=identity)
    assert first is not None
    first_resolved = first._InvocationProjectionCapability__resolved_consumer
    assert first_resolved._model is not None
    shared_array = first_resolved._model.return_model.steps[0][1].statistics_

    original_reload = RecommendationCalibrationConsumer.reload

    def reload_with_cross_capability_view(
        resolved: RecommendationCalibrationConsumer,
        *,
        decision_date: str | None = None,
    ) -> str:
        status = original_reload(resolved, decision_date=decision_date)
        if resolved is not consumer and status == "active" and resolved._model is not None:
            pipeline = resolved._model.return_model
            _replace_pipeline_step(
                pipeline,
                "imputer",
                _imputer_with_statistics_view(pipeline.steps[0][1], shared_array),
            )
        return status

    monkeypatch.setattr(RecommendationCalibrationConsumer, "reload", reload_with_cross_capability_view)
    second = _capability(consumer, scope="live-call-graph-b-0001", identity=identity)
    assert second is None


def _consumer_with_deepcopied_loaded_state(source: Any) -> Any:
    fresh = RecommendationCalibrationConsumer(
        pointer_path=source.pointer_path,
        feature_schema=source.feature_schema,
        feature_registry_hash=source.feature_registry_hash,
        data_root=source._loader._data_root,
        expected_model_family=source.expected_model_family,
    )
    (
        fresh._model,
        fresh._baseline_model,
        fresh._lineage_models,
        fresh._probability_lineage,
        fresh._loaded_pointer,
        fresh._baseline_identity,
        fresh._training_provenance,
        fresh._cost_scenario,
    ) = deepcopy(
        (
            source._model,
            source._baseline_model,
            source._lineage_models,
            source._probability_lineage,
            source._loaded_pointer,
            source._baseline_identity,
            source._training_provenance,
            source._cost_scenario,
        )
    )
    return fresh


def _replace_pipeline_step(pipeline: Any, step_name: str, estimator: Any) -> None:
    steps = list(pipeline.steps)
    for index, (name, _existing) in enumerate(steps):
        if name == step_name:
            steps[index] = (name, estimator)
            pipeline.steps = steps
            return
    raise AssertionError(f"missing pipeline step: {step_name}")


def _imputer_with_statistics_view(imputer: Any, shared_array: Any) -> Any:
    cloned = deepcopy(imputer)
    cloned.statistics_ = shared_array.view()
    return cloned


def _model_copy_with_shared_estimator(model: Any) -> Any:
    cloned = copy(model)
    assert cloned is not model
    assert cloned.return_model is model.return_model
    return cloned


def test_capabilities_are_bound_to_owner_scope_date_and_identity(
    active_consumer: tuple[Any, Path, Path]
) -> None:
    consumer, _pointer_path, _candidate_root = active_consumer
    identity = consumer.active_identity(decision_date="2026-07-27")
    assert identity is not None
    first = _capability(consumer, scope="live-call-a-0002", identity=identity)
    duplicate_scope = _capability(
        consumer, scope="live-call-a-0002", identity=identity
    )
    second = _capability(consumer, scope="live-call-b-0002", identity=identity)
    assert first is not None and second is not None
    assert duplicate_scope is None
    assert (
        first._InvocationProjectionCapability__resolved_consumer
        is not second._InvocationProjectionCapability__resolved_consumer
    )
    assert first.loaded_artifact_lineage is not second.loaded_artifact_lineage
    assert first.loaded_artifact_lineage.to_payload() == second.loaded_artifact_lineage.to_payload()
    with pytest.raises(TypeError, match="cannot be copied"):
        deepcopy(first)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(first)

    changed = deepcopy(identity)
    changed["probability_lineage"][0]["kind"] = "wrong-lineage"
    with pytest.raises(ValueError, match="scope or identity mismatch"):
        _project(first, consumer, scope="live-call-b-0002", identity=identity)
    with pytest.raises(ValueError, match="scope or identity mismatch"):
        _project(second, consumer, scope="live-call-b-0002", identity=changed)

    other_consumer = RecommendationCalibrationConsumer(
        pointer_path=consumer.pointer_path,
        feature_schema=consumer.feature_schema,
        feature_registry_hash=consumer.feature_registry_hash,
        data_root=consumer._loader._data_root,
    )
    with pytest.raises(ValueError, match="different consumer"):
        _project(first, other_consumer, scope="live-call-a-0002", identity=identity)

    # 錯誤 owner/scope 不會消耗能力；兩個同日呼叫仍可各自安全完成。
    assert _project(second, consumer, scope="live-call-b-0002", identity=identity)["AAA"].status == "active_candidate"
    assert _project(first, consumer, scope="live-call-a-0002", identity=identity)["AAA"].status == "active_candidate"


def test_capability_fails_closed_on_active_pointer_race(
    active_consumer: tuple[Any, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    consumer, pointer_path, _candidate_root = active_consumer
    identity = consumer.active_identity(decision_date="2026-07-27")
    assert identity is not None
    original_bytes = pointer_path.read_bytes()

    from ml_module.model_artifact_loader import SafeShadowModelArtifactLoader

    original_load_same_bytes = SafeShadowModelArtifactLoader.load_same_bytes_with_manifest_v1
    changed = False

    def load_same_bytes_then_change_pointer(
        loader: SafeShadowModelArtifactLoader,
        artifact_root: str | Path,
        *,
        expectation: Any,
    ) -> Any:
        nonlocal changed
        result = original_load_same_bytes(
            loader, artifact_root, expectation=expectation
        )
        if not changed:
            pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
            pointer["status"] = "rule_only"
            pointer["rollback_reason"] = "synthetic_pointer_race"
            pointer_path.write_text(
                json.dumps(pointer, sort_keys=True) + "\n", encoding="utf-8"
            )
            changed = True
        return result

    monkeypatch.setattr(
        SafeShadowModelArtifactLoader,
        "load_same_bytes_with_manifest_v1",
        load_same_bytes_then_change_pointer,
    )
    try:
        capability = _capability(
            consumer, scope="live-call-race-0001", identity=identity
        )
        assert capability is None
        assert changed
    finally:
        pointer_path.write_bytes(original_bytes)
    assert consumer.reload(decision_date="2026-07-27") == "active"


def test_capability_rejects_safe_loader_artifact_hash_failure(
    active_consumer: tuple[Any, Path, Path]
) -> None:
    consumer, _pointer_path, candidate_root = active_consumer
    identity = consumer.active_identity(decision_date="2026-07-27")
    assert identity is not None
    manifest = json.loads((candidate_root / "manifest.json").read_text(encoding="utf-8"))
    artifact_path = candidate_root / str(manifest["artifact_filename"])
    original_artifact = artifact_path.read_bytes()
    try:
        artifact_path.write_bytes(original_artifact + b"tamper")
        assert (
            _capability(
                consumer, scope="live-call-rejected-0001", identity=identity
            )
            is None
        )
    finally:
        artifact_path.write_bytes(original_artifact)


def test_capability_rejects_quarantined_or_nonactive_pointer(
    active_consumer: tuple[Any, Path, Path]
) -> None:
    consumer, pointer_path, _candidate_root = active_consumer
    identity = consumer.active_identity(decision_date="2026-07-27")
    assert identity is not None
    original_bytes = pointer_path.read_bytes()
    try:
        pointer = json.loads(original_bytes.decode("utf-8"))
        pointer["status"] = "quarantined"
        pointer_path.write_text(
            json.dumps(pointer, sort_keys=True) + "\n", encoding="utf-8"
        )
        assert (
            _capability(
                consumer, scope="live-call-quarantine-0001", identity=identity
            )
            is None
        )
    finally:
        pointer_path.write_bytes(original_bytes)
    assert consumer.reload(decision_date="2026-07-27") == "active"
