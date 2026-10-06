"""R026 的 app-side、非完整 ModelBinding 模型解析事實。"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence

from ml_module.model_artifact_manifest import ModelArtifactManifest


MODEL_RESOLUTION_EVIDENCE_SCHEMA_V1 = "recommendation-model-resolution-evidence.v1"
_EVIDENCE_HASH_DOMAIN = b"r026-recommendation-model-resolution-evidence.v1\0"
_CANDIDATE_HASH_DOMAIN = b"r026-candidate-identity-claim.v1\0"
_LINEAGE_HASH_DOMAIN = b"r026-probability-lineage-node.v1\0"
_LINEAGE_SEQUENCE_HASH_DOMAIN = b"r026-probability-lineage-sequence.v1\0"
_CAPABILITY_ARTIFACT_LINEAGE_HASH_DOMAIN = (
    b"r026-capability-loaded-artifact-lineage.v1\0"
)


@dataclass(frozen=True, slots=True)
class ModelResolutionLibraryVersionV1:
    """分開保存 artifact 記錄版本與當次執行環境版本。"""

    library: str
    version: str

    def __post_init__(self) -> None:
        _require_text(self.library, "library")
        _require_text(self.version, "version")


@dataclass(frozen=True, slots=True)
class CandidateResolutionIdentityV1:
    candidate_id: str
    manifest_hash: str
    artifact_hash: str
    freeze_hash: str
    dataset_hash: str
    candidate_training_cutoff: str | None
    candidate_identity_claim_hash: str
    pointer_schema_version: str
    pointer_bytes_check: str
    candidate_path_check: str

    def __post_init__(self) -> None:
        for name in (
            "candidate_id",
            "manifest_hash",
            "artifact_hash",
            "freeze_hash",
            "dataset_hash",
            "pointer_schema_version",
            "pointer_bytes_check",
            "candidate_path_check",
        ):
            _require_text(getattr(self, name), name)
        for name in (
            "manifest_hash",
            "artifact_hash",
            "freeze_hash",
            "dataset_hash",
            "candidate_identity_claim_hash",
        ):
            _require_sha256(getattr(self, name), name)
        if self.candidate_training_cutoff is not None:
            _require_date(self.candidate_training_cutoff, "candidate_training_cutoff")
        if self.pointer_bytes_check != "equal_before_after_resolve":
            raise ValueError("pointer bytes check status is invalid")
        if self.candidate_path_check != "identity_rechecked_by_path_read_same_bytes_not_proven":
            raise ValueError("candidate path check status is invalid")


@dataclass(frozen=True, slots=True)
class ModelArtifactDeclarationV1:
    manifest_schema_version: str
    model_id: str
    dataset_id: str
    created_run_id: str
    created_at: str
    model_family: str
    feature_registry_hash: str
    label_registry_hash: str
    feature_schema: tuple[tuple[str, str, str], ...]
    training_as_of: str
    loaded_model_training_as_of: str | None
    hyperparameters_hash: str
    research_alpha_bp: int
    production_alpha_bp: int
    blend_selection_metric: str
    blend_selection_label_cutoff: str
    blend_selection_threshold_bp: int
    serialization_format: str
    artifact_filename: str
    artifact_hash: str
    manifest_hash: str
    recorded_library_versions: tuple[ModelResolutionLibraryVersionV1, ...]
    frozen: bool
    shadow_only: bool
    production_eligible: bool
    production_action_allowed: bool

    def __post_init__(self) -> None:
        for name in (
            "manifest_schema_version",
            "model_id",
            "dataset_id",
            "created_run_id",
            "created_at",
            "model_family",
            "training_as_of",
            "blend_selection_metric",
            "blend_selection_label_cutoff",
            "serialization_format",
            "artifact_filename",
        ):
            _require_text(getattr(self, name), name)
        for name in (
            "feature_registry_hash",
            "label_registry_hash",
            "hyperparameters_hash",
            "artifact_hash",
            "manifest_hash",
        ):
            _require_sha256(getattr(self, name), name)
        _require_date(self.training_as_of, "training_as_of")
        if self.loaded_model_training_as_of is not None:
            _require_date(self.loaded_model_training_as_of, "loaded_model_training_as_of")
        _require_date(self.blend_selection_label_cutoff, "blend_selection_label_cutoff")
        for name in ("research_alpha_bp", "production_alpha_bp", "blend_selection_threshold_bp"):
            if type(getattr(self, name)) is not int:
                raise TypeError(f"{name} must be an integer basis-point value")
        # Manifest cutoff 與已載入 model cutoff 是不同 declarations；保留各自原值，
        # 不以其中一者覆寫另一者，也不在這裡推導 training provenance。
        if not self.feature_schema:
            raise ValueError("feature_schema is required")
        for entry in self.feature_schema:
            if type(entry) is not tuple or len(entry) != 3 or any(type(item) is not str or not item for item in entry):
                raise TypeError("feature_schema must contain immutable text triples")
        if type(self.recorded_library_versions) is not tuple or not self.recorded_library_versions:
            raise ValueError("recorded_library_versions must be a non-empty tuple")
        names = tuple(item.library for item in self.recorded_library_versions)
        if len(names) != len(set(names)):
            raise ValueError("recorded library versions must be unique")
        for name in ("frozen", "shadow_only", "production_eligible", "production_action_allowed"):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be bool")


@dataclass(frozen=True, slots=True)
class ArtifactPathVerificationV1:
    declared_artifact_hash: str
    path_verified_artifact_hash: str
    loaded_bytes_sha256: None = None
    same_bytes_binding_status: str = "not_verified"
    hash_check_profile: str = "path_hash_before_deserializer_reopen_then_path_recheck"

    def __post_init__(self) -> None:
        _require_sha256(self.declared_artifact_hash, "declared_artifact_hash")
        _require_sha256(self.path_verified_artifact_hash, "path_verified_artifact_hash")
        if self.path_verified_artifact_hash != self.declared_artifact_hash:
            raise ValueError("verified artifact path hash must match its declaration")
        if self.loaded_bytes_sha256 is not None:
            raise ValueError("loaded artifact bytes hash is not captured by this contract")
        if self.same_bytes_binding_status != "not_verified":
            raise ValueError("same-bytes binding must remain explicitly unverified")
        if self.hash_check_profile != "path_hash_before_deserializer_reopen_then_path_recheck":
            raise ValueError("artifact path verification profile is invalid")


@dataclass(frozen=True, slots=True)
class TrainingLineageResolutionV1:
    status: str
    reason: str | None
    provenance_schema_version: str
    manifest_hash: str | None
    training_source_hash: str | None
    training_pit_hash: str | None
    feature_registry_hash: str | None
    feature_schema_hash: str | None
    feature_transform_contract_hash: str | None
    transform_status: str
    dataset_id: str | None
    dataset_hash: str | None
    decision_date: str | None
    training_as_of: str | None
    training_semantics: str | None
    decision_time_eligible: bool | None
    research_only: bool | None
    cost_scenario_hash: str | None

    def __post_init__(self) -> None:
        if self.status not in {"verified", "legacy_unproven"}:
            raise ValueError("training lineage status is unsupported")
        _require_text(self.provenance_schema_version, "provenance_schema_version")
        for name in (
            "manifest_hash",
            "training_source_hash",
            "training_pit_hash",
            "feature_registry_hash",
            "feature_schema_hash",
            "feature_transform_contract_hash",
            "dataset_hash",
            "cost_scenario_hash",
        ):
            _optional_sha256(getattr(self, name), name)
        for name in ("dataset_id", "training_semantics"):
            _optional_text(getattr(self, name), name)
        for name in ("decision_date", "training_as_of"):
            value = getattr(self, name)
            if value is not None:
                _require_date(value, name)
        for name in ("decision_time_eligible", "research_only"):
            value = getattr(self, name)
            if value is not None and type(value) is not bool:
                raise TypeError(f"{name} must be bool or None")
        if self.status == "verified":
            if (
                self.training_source_hash is None
                or self.training_pit_hash is None
                or self.feature_transform_contract_hash is None
                or self.transform_status != "verified"
            ):
                raise ValueError("verified training lineage requires verified source/PIT/transform hashes")
        elif (
            self.training_source_hash is not None
            or self.training_pit_hash is not None
            or self.feature_transform_contract_hash is not None
            or self.transform_status != "legacy_unproven"
        ):
            raise ValueError("legacy training lineage cannot be upgraded from inference facts")


@dataclass(frozen=True, slots=True)
class ProbabilityLineageIdentityV1:
    position: int
    kind: str
    candidate_id: str | None
    model_id: str | None
    manifest_hash: str | None
    artifact_hash: str | None
    freeze_hash: str | None
    dataset_hash: str | None
    baseline_id: str
    baseline_kind: str
    transform_id: str
    maximum_probability_change_bp: int
    node_sha256: str

    def __post_init__(self) -> None:
        if type(self.position) is not int or self.position < 0:
            raise ValueError("probability lineage position must be non-negative")
        for name in ("kind", "baseline_id", "baseline_kind", "transform_id"):
            _require_text(getattr(self, name), name)
        for name in ("candidate_id", "model_id"):
            _optional_text(getattr(self, name), name)
        for name in ("manifest_hash", "artifact_hash", "freeze_hash", "dataset_hash"):
            _optional_sha256(getattr(self, name), name)
        if type(self.maximum_probability_change_bp) is not int or self.maximum_probability_change_bp < 0:
            raise ValueError("maximum_probability_change_bp must be a non-negative int")
        _require_sha256(self.node_sha256, "node_sha256")


@dataclass(frozen=True, slots=True)
class ModelRuntimeProfileV1:
    platform: str
    python_version: tuple[int, int, int]
    library_versions: tuple[ModelResolutionLibraryVersionV1, ...]

    def __post_init__(self) -> None:
        _require_text(self.platform, "platform")
        if (
            type(self.python_version) is not tuple
            or len(self.python_version) != 3
            or any(type(value) is not int or value < 0 for value in self.python_version)
        ):
            raise TypeError("python_version must be a three-part integer tuple")
        if type(self.library_versions) is not tuple or not self.library_versions:
            raise ValueError("runtime library_versions must be a non-empty tuple")
        names = tuple(item.library for item in self.library_versions)
        if len(names) != len(set(names)):
            raise ValueError("runtime library versions must be unique")


@dataclass(frozen=True, slots=True)
class UnknownModelBindingFieldsV1:
    release_id: None = None
    artifact_declared_qualified_class_path: None = None
    quarantine_status: str = "unknown"
    permission_status: str = "unknown"
    transform_status: str = "unknown"

    def __post_init__(self) -> None:
        if any(
            value is not None
            for value in (self.release_id, self.artifact_declared_qualified_class_path)
        ):
            raise ValueError("unavailable binding fields must remain None")
        if self.quarantine_status != "unknown" or self.permission_status != "unknown":
            raise ValueError("quarantine and permission status must remain unknown")
        if self.transform_status not in {"unknown", "legacy_unproven"}:
            raise ValueError("transform status is unsupported")


@dataclass(frozen=True, slots=True)
class RecommendationModelResolutionEvidenceV1:
    decision_date: str
    candidate: CandidateResolutionIdentityV1
    manifest: ModelArtifactDeclarationV1
    artifact: ArtifactPathVerificationV1
    training: TrainingLineageResolutionV1
    probability_lineage: tuple[ProbabilityLineageIdentityV1, ...]
    probability_lineage_sha256: str
    runtime_profile: ModelRuntimeProfileV1
    missing_model_binding: UnknownModelBindingFieldsV1
    model_binding_status: str = "incomplete_unknown_fields"
    schema_version: str = MODEL_RESOLUTION_EVIDENCE_SCHEMA_V1
    evidence_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        _require_date(self.decision_date, "decision_date")
        if self.schema_version != MODEL_RESOLUTION_EVIDENCE_SCHEMA_V1:
            raise ValueError("unsupported model-resolution evidence schema")
        if self.model_binding_status != "incomplete_unknown_fields":
            raise ValueError("this evidence cannot represent a complete ModelBinding")
        if type(self.probability_lineage) is not tuple or not self.probability_lineage:
            raise ValueError("ordered probability lineage must be a non-empty tuple")
        if tuple(node.position for node in self.probability_lineage) != tuple(
            range(len(self.probability_lineage))
        ):
            raise ValueError("probability lineage positions must be contiguous and ordered")
        _require_sha256(self.probability_lineage_sha256, "probability_lineage_sha256")
        if self.candidate.candidate_id != self.manifest.model_id:
            raise ValueError("candidate and manifest model identities do not match")
        if self.candidate.manifest_hash != self.manifest.manifest_hash:
            raise ValueError("candidate and model manifest hashes do not match")
        if self.candidate.artifact_hash != self.manifest.artifact_hash:
            raise ValueError("candidate and model artifact hashes do not match")
        if self.artifact.declared_artifact_hash != self.manifest.artifact_hash:
            raise ValueError("artifact verification and manifest declarations do not match")
        if self.training.status == "legacy_unproven" and self.missing_model_binding.transform_status != "legacy_unproven":
            raise ValueError("legacy transform provenance must remain unproven")
        if self.training.status == "verified" and self.missing_model_binding.transform_status != "unknown":
            raise ValueError("verified training transform is not an artifact class/permission binding")
        last_candidate = self.probability_lineage[-1].candidate_id
        if last_candidate != self.candidate.candidate_id:
            raise ValueError("probability lineage does not end at the active candidate")
        object.__setattr__(self, "evidence_sha256", _domain_hash(_EVIDENCE_HASH_DOMAIN, self._payload()))

    def to_payload(self) -> dict[str, Any]:
        """回傳新建 mutable payload；修改它不會改動 frozen facts。"""

        payload = self._payload()
        payload["evidence_sha256"] = self.evidence_sha256
        return payload

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "decision_date": self.decision_date,
            "model_binding_status": self.model_binding_status,
            "candidate": _candidate_payload(self.candidate),
            "manifest": _manifest_payload(self.manifest),
            "artifact": _artifact_payload(self.artifact),
            "training": _training_payload(self.training),
            "probability_lineage": [_probability_node_payload(item) for item in self.probability_lineage],
            "probability_lineage_sha256": self.probability_lineage_sha256,
            "runtime_profile": _runtime_payload(self.runtime_profile),
            "missing_model_binding": _missing_binding_payload(self.missing_model_binding),
        }


@dataclass(frozen=True, slots=True)
class CapabilityLoadedArtifactLineageNodeV1:
    """Fresh capability-local declaration plus same-buffer artifact digest."""

    position: int
    kind: str
    candidate_id: str | None
    model_id: str | None
    normalized_candidate_root: str | None
    manifest_hash: str | None
    declared_artifact_hash: str | None
    freeze_hash: str | None
    dataset_hash: str | None
    loaded_serialized_bytes_sha256: str | None

    def __post_init__(self) -> None:
        if type(self.position) is not int or self.position < 0:
            raise ValueError("artifact lineage position must be non-negative")
        if self.kind == "null_benchmark":
            if any(
                value is not None
                for value in (
                    self.candidate_id,
                    self.model_id,
                    self.normalized_candidate_root,
                    self.manifest_hash,
                    self.declared_artifact_hash,
                    self.freeze_hash,
                    self.dataset_hash,
                    self.loaded_serialized_bytes_sha256,
                )
            ):
                raise ValueError("null benchmark cannot carry artifact identity")
            return
        if self.kind != "active_model":
            raise ValueError("artifact lineage node kind is unsupported")
        for name in (
            "candidate_id",
            "model_id",
            "normalized_candidate_root",
        ):
            _require_text(getattr(self, name), name)
        for name in (
            "manifest_hash",
            "declared_artifact_hash",
            "freeze_hash",
            "dataset_hash",
            "loaded_serialized_bytes_sha256",
        ):
            _require_sha256(getattr(self, name), name)
        if self.model_id != self.candidate_id:
            raise ValueError("artifact lineage model and candidate IDs differ")
        if self.loaded_serialized_bytes_sha256 != self.declared_artifact_hash:
            raise ValueError("loaded artifact bytes differ from the node declaration")

    def to_payload(self) -> dict[str, Any]:
        return {
            "position": self.position,
            "kind": self.kind,
            "candidate_id": self.candidate_id,
            "model_id": self.model_id,
            "normalized_candidate_root": self.normalized_candidate_root,
            "manifest_hash": self.manifest_hash,
            "declared_artifact_hash": self.declared_artifact_hash,
            "freeze_hash": self.freeze_hash,
            "dataset_hash": self.dataset_hash,
            "loaded_serialized_bytes_sha256": self.loaded_serialized_bytes_sha256,
        }


@dataclass(frozen=True, slots=True)
class CapabilityLoadedArtifactLineageEvidenceV1:
    """Ordered per-artifact same-buffer evidence for one fresh capability."""

    nodes: tuple[CapabilityLoadedArtifactLineageNodeV1, ...]
    schema_version: str = "r026-capability-loaded-artifact-lineage.v1"
    evidence_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if self.schema_version != "r026-capability-loaded-artifact-lineage.v1":
            raise ValueError("unsupported capability artifact lineage schema")
        if type(self.nodes) is not tuple or len(self.nodes) < 2:
            raise ValueError("capability artifact lineage must include null and active nodes")
        if any(type(item) is not CapabilityLoadedArtifactLineageNodeV1 for item in self.nodes):
            raise TypeError("capability artifact lineage nodes must use the exact typed contract")
        if tuple(item.position for item in self.nodes) != tuple(range(len(self.nodes))):
            raise ValueError("capability artifact lineage positions must be contiguous")
        if self.nodes[0].kind != "null_benchmark" or any(
            item.kind == "null_benchmark" for item in self.nodes[1:]
        ):
            raise ValueError("capability artifact lineage null benchmark placement is invalid")
        active_id = self.nodes[-1].candidate_id
        if self.nodes[-1].kind != "active_model" or active_id is None:
            raise ValueError("capability artifact lineage must terminate at an active model")
        if sum(item.candidate_id == active_id for item in self.nodes) != 1:
            raise ValueError("active candidate must occur exactly once at the terminal node")
        payload = {
            "schema_version": self.schema_version,
            "nodes": [item.to_payload() for item in self.nodes],
        }
        object.__setattr__(
            self,
            "evidence_sha256",
            _domain_hash(_CAPABILITY_ARTIFACT_LINEAGE_HASH_DOMAIN, payload),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "nodes": [item.to_payload() for item in self.nodes],
            "evidence_sha256": self.evidence_sha256,
        }


def capture_model_resolution_evidence_v1(
    *,
    pointer: Mapping[str, Any],
    candidate_payload: Mapping[str, Any],
    manifest: ModelArtifactManifest,
    loaded_model_training_as_of: Any,
    training_provenance: Mapping[str, Any],
    probability_lineage: Sequence[Mapping[str, Any]],
    runtime_profile: tuple[Any, ...],
    decision_date: str,
    pointer_bytes_equal: bool,
    candidate_identity_path_rechecked: bool,
) -> RecommendationModelResolutionEvidenceV1:
    """把同一次已驗證 resolve 的現有讀值轉成 immutable facts。"""

    if pointer_bytes_equal is not True or candidate_identity_path_rechecked is not True:
        raise ValueError("model resolution capture requires completed pointer/candidate checks")
    if type(manifest) is not ModelArtifactManifest:
        raise TypeError("manifest must be the exact safe-loader manifest type")
    if not isinstance(pointer, Mapping) or not isinstance(candidate_payload, Mapping):
        raise TypeError("pointer and candidate payload must be mappings")
    if not isinstance(training_provenance, Mapping):
        raise TypeError("training_provenance must be a mapping")
    if not probability_lineage or any(not isinstance(item, Mapping) for item in probability_lineage):
        raise ValueError("probability_lineage must be a non-empty ordered mapping sequence")

    pointer_schema = _required_text(pointer.get("schema_version"), "pointer schema_version")
    candidate_values = {
        "candidate_id": _required_text(pointer.get("candidate_id"), "pointer candidate_id"),
        "manifest_hash": _required_text(pointer.get("candidate_manifest_hash"), "pointer manifest hash"),
        "artifact_hash": _required_text(pointer.get("candidate_artifact_hash"), "pointer artifact hash"),
        "freeze_hash": _required_text(pointer.get("candidate_freeze_hash"), "pointer freeze hash"),
        "dataset_hash": _required_text(pointer.get("dataset_hash"), "pointer dataset hash"),
    }
    payload_values = {
        "candidate_id": _required_text(candidate_payload.get("candidate_id"), "candidate_id"),
        "manifest_hash": _required_text(candidate_payload.get("manifest_hash"), "candidate manifest_hash"),
        "artifact_hash": _required_text(candidate_payload.get("artifact_hash"), "candidate artifact_hash"),
        "freeze_hash": _required_text(candidate_payload.get("candidate_freeze_hash"), "candidate_freeze_hash"),
        "dataset_hash": _required_text(candidate_payload.get("dataset_hash"), "candidate dataset_hash"),
    }
    if payload_values != candidate_values:
        raise ValueError("initial candidate declaration does not match the validated pointer")
    candidate_claim_hash = _domain_hash(
        _CANDIDATE_HASH_DOMAIN,
        {
            **payload_values,
            "training_cutoff": _optional_date(candidate_payload.get("training_cutoff")),
        },
    )
    candidate = CandidateResolutionIdentityV1(
        candidate_id=candidate_values["candidate_id"],
        manifest_hash=candidate_values["manifest_hash"],
        artifact_hash=candidate_values["artifact_hash"],
        freeze_hash=candidate_values["freeze_hash"],
        dataset_hash=candidate_values["dataset_hash"],
        candidate_training_cutoff=_optional_date(candidate_payload.get("training_cutoff")),
        candidate_identity_claim_hash=candidate_claim_hash,
        pointer_schema_version=pointer_schema,
        pointer_bytes_check="equal_before_after_resolve",
        candidate_path_check="identity_rechecked_by_path_read_same_bytes_not_proven",
    )

    model = _model_declaration(manifest, loaded_model_training_as_of)
    artifact = ArtifactPathVerificationV1(
        declared_artifact_hash=manifest.artifact_hash,
        path_verified_artifact_hash=manifest.artifact_hash,
    )
    training = _training_lineage(training_provenance)
    lineage_nodes = tuple(
        _probability_lineage_identity(position, item)
        for position, item in enumerate(probability_lineage)
    )
    lineage_digest = _domain_hash(
        _LINEAGE_SEQUENCE_HASH_DOMAIN,
        [{"position": item.position, "node_sha256": item.node_sha256} for item in lineage_nodes],
    )
    runtime = _runtime_profile(runtime_profile)
    missing_binding = UnknownModelBindingFieldsV1(
        transform_status=("legacy_unproven" if training.status == "legacy_unproven" else "unknown")
    )
    return RecommendationModelResolutionEvidenceV1(
        decision_date=decision_date,
        candidate=candidate,
        manifest=model,
        artifact=artifact,
        training=training,
        probability_lineage=lineage_nodes,
        probability_lineage_sha256=lineage_digest,
        runtime_profile=runtime,
        missing_model_binding=missing_binding,
    )


def _model_declaration(
    manifest: ModelArtifactManifest,
    loaded_model_training_as_of: Any,
) -> ModelArtifactDeclarationV1:
    versions = _library_versions(manifest.library_versions, "artifact library_versions")
    raw_schema = manifest.feature_schema
    if type(raw_schema) is not tuple:
        raise TypeError("manifest feature_schema must be a tuple")
    if any(
        type(item) is not tuple
        or len(item) != 3
        or any(type(part) is not str or not part for part in item)
        for item in raw_schema
    ):
        raise TypeError("manifest feature_schema must contain immutable text triples")
    schema = tuple((item[0], item[1], item[2]) for item in raw_schema)
    return ModelArtifactDeclarationV1(
        manifest_schema_version=manifest.schema_version,
        model_id=manifest.model_id,
        dataset_id=manifest.dataset_id,
        created_run_id=manifest.created_run_id,
        created_at=manifest.created_at,
        model_family=manifest.model_family,
        feature_registry_hash=manifest.feature_registry_hash,
        label_registry_hash=manifest.label_registry_hash,
        feature_schema=schema,
        training_as_of=manifest.training_as_of,
        loaded_model_training_as_of=_optional_date(loaded_model_training_as_of),
        hyperparameters_hash=manifest.hyperparameters_hash,
        research_alpha_bp=manifest.research_alpha_bp,
        production_alpha_bp=manifest.production_alpha_bp,
        blend_selection_metric=manifest.blend_selection_metric,
        blend_selection_label_cutoff=manifest.blend_selection_label_cutoff,
        blend_selection_threshold_bp=manifest.blend_selection_threshold_bp,
        serialization_format=manifest.serialization_format,
        artifact_filename=manifest.artifact_filename,
        artifact_hash=manifest.artifact_hash,
        manifest_hash=manifest.manifest_hash,
        recorded_library_versions=versions,
        frozen=manifest.frozen,
        shadow_only=manifest.shadow_only,
        production_eligible=manifest.production_eligible,
        production_action_allowed=manifest.production_action_allowed,
    )


def _training_lineage(provenance: Mapping[str, Any]) -> TrainingLineageResolutionV1:
    status = _required_text(provenance.get("status"), "training provenance status")
    if status not in {"verified", "legacy_unproven"}:
        raise ValueError("training provenance status is not supported by model facts")
    transform_hash = _optional_string(provenance.get("feature_transform_contract_hash"))
    transform_status = "verified" if status == "verified" and transform_hash else (
        "legacy_unproven" if status == "legacy_unproven" else "unknown"
    )
    return TrainingLineageResolutionV1(
        status=status,
        reason=_optional_string(provenance.get("reason")),
        provenance_schema_version=_required_text(
            provenance.get("schema_version"), "training provenance schema_version"
        ),
        manifest_hash=_optional_string(provenance.get("manifest_hash")),
        training_source_hash=_optional_string(provenance.get("training_source_hash")),
        training_pit_hash=_optional_string(provenance.get("training_pit_hash")),
        feature_registry_hash=_optional_string(provenance.get("feature_registry_hash")),
        feature_schema_hash=_optional_string(provenance.get("feature_schema_hash")),
        feature_transform_contract_hash=transform_hash,
        transform_status=transform_status,
        dataset_id=_optional_string(provenance.get("dataset_id")),
        dataset_hash=_optional_string(provenance.get("dataset_hash")),
        decision_date=_optional_date(provenance.get("decision_date")),
        training_as_of=_optional_date(provenance.get("training_as_of")),
        training_semantics=_optional_string(provenance.get("training_semantics")),
        decision_time_eligible=_optional_bool(provenance.get("decision_time_eligible")),
        research_only=_optional_bool(provenance.get("research_only")),
        cost_scenario_hash=_optional_string(provenance.get("cost_scenario_hash")),
    )


def _probability_lineage_identity(
    position: int,
    node: Mapping[str, Any],
) -> ProbabilityLineageIdentityV1:
    max_change = node.get("maximum_probability_change_bp")
    if type(max_change) is not int:
        raise TypeError("probability lineage cap must be int")
    return ProbabilityLineageIdentityV1(
        position=position,
        kind=_required_text(node.get("kind"), "lineage kind"),
        candidate_id=_optional_string(node.get("candidate_id")),
        model_id=_optional_string(node.get("model_id")),
        manifest_hash=_optional_string(node.get("candidate_manifest_hash")),
        artifact_hash=_optional_string(node.get("candidate_artifact_hash")),
        freeze_hash=_optional_string(node.get("candidate_freeze_hash")),
        dataset_hash=_optional_string(node.get("dataset_hash")),
        baseline_id=_required_text(node.get("baseline_id"), "lineage baseline_id"),
        baseline_kind=_required_text(node.get("baseline_kind"), "lineage baseline_kind"),
        transform_id=_required_text(node.get("transform_id"), "lineage transform_id"),
        maximum_probability_change_bp=max_change,
        node_sha256=_domain_hash(_LINEAGE_HASH_DOMAIN, _json_compatible_mapping(node)),
    )


def _runtime_profile(profile: tuple[Any, ...]) -> ModelRuntimeProfileV1:
    if type(profile) is not tuple or len(profile) != 6:
        raise TypeError("runtime profile must match the existing six-field gate")
    platform, python_version, numpy_version, sklearn_version, scipy_version, joblib_version = profile
    versions = tuple(
        ModelResolutionLibraryVersionV1(library=name, version=value)
        for name, value in (
            ("joblib", joblib_version),
            ("numpy", numpy_version),
            ("scikit-learn", sklearn_version),
            ("scipy", scipy_version),
        )
    )
    if type(python_version) is not tuple:
        raise TypeError("runtime Python version must be a tuple")
    return ModelRuntimeProfileV1(
        platform=_required_text(platform, "runtime platform"),
        python_version=python_version,
        library_versions=versions,
    )


def _library_versions(
    values: Mapping[str, str],
    field_name: str,
) -> tuple[ModelResolutionLibraryVersionV1, ...]:
    if not isinstance(values, Mapping) or not values:
        raise ValueError(f"{field_name} must be a non-empty mapping")
    entries: list[ModelResolutionLibraryVersionV1] = []
    for library, version in sorted(values.items()):
        entries.append(
            ModelResolutionLibraryVersionV1(
                library=_required_text(library, f"{field_name} library"),
                version=_required_text(version, f"{field_name} version"),
            )
        )
    return tuple(entries)


def _json_compatible_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    def normalize(item: Any) -> Any:
        if item is None or type(item) in (str, int, bool):
            return item
        if type(item) is float:
            raise TypeError("model-resolution evidence does not accept float payload values")
        if isinstance(item, Mapping):
            normalized: dict[str, Any] = {}
            for key, nested in item.items():
                if type(key) is not str:
                    raise TypeError("lineage mapping keys must be strings")
                normalized[key] = normalize(nested)
            return normalized
        if type(item) in (list, tuple):
            return [normalize(nested) for nested in item]
        raise TypeError(f"unsupported lineage identity value: {type(item).__name__}")

    normalized = normalize(value)
    if not isinstance(normalized, dict):
        raise TypeError("probability lineage node must be a mapping")
    return normalized


def _candidate_payload(value: CandidateResolutionIdentityV1) -> dict[str, Any]:
    return {
        "candidate_id": value.candidate_id,
        "manifest_hash": value.manifest_hash,
        "artifact_hash": value.artifact_hash,
        "freeze_hash": value.freeze_hash,
        "dataset_hash": value.dataset_hash,
        "candidate_training_cutoff": value.candidate_training_cutoff,
        "candidate_identity_claim_hash": value.candidate_identity_claim_hash,
        "pointer_schema_version": value.pointer_schema_version,
        "pointer_bytes_check": value.pointer_bytes_check,
        "candidate_path_check": value.candidate_path_check,
    }


def _manifest_payload(value: ModelArtifactDeclarationV1) -> dict[str, Any]:
    return {
        "manifest_schema_version": value.manifest_schema_version,
        "model_id": value.model_id,
        "dataset_id": value.dataset_id,
        "created_run_id": value.created_run_id,
        "created_at": value.created_at,
        "model_family": value.model_family,
        "feature_registry_hash": value.feature_registry_hash,
        "label_registry_hash": value.label_registry_hash,
        "feature_schema": [list(item) for item in value.feature_schema],
        "training_as_of": value.training_as_of,
        "loaded_model_training_as_of": value.loaded_model_training_as_of,
        "hyperparameters_hash": value.hyperparameters_hash,
        "research_alpha_bp": value.research_alpha_bp,
        "production_alpha_bp": value.production_alpha_bp,
        "blend_selection_metric": value.blend_selection_metric,
        "blend_selection_label_cutoff": value.blend_selection_label_cutoff,
        "blend_selection_threshold_bp": value.blend_selection_threshold_bp,
        "serialization_format": value.serialization_format,
        "artifact_filename": value.artifact_filename,
        "artifact_hash": value.artifact_hash,
        "manifest_hash": value.manifest_hash,
        "recorded_library_versions": _versions_payload(value.recorded_library_versions),
        "frozen": value.frozen,
        "shadow_only": value.shadow_only,
        "production_eligible": value.production_eligible,
        "production_action_allowed": value.production_action_allowed,
    }


def _artifact_payload(value: ArtifactPathVerificationV1) -> dict[str, Any]:
    return {
        "declared_artifact_hash": value.declared_artifact_hash,
        "path_verified_artifact_hash": value.path_verified_artifact_hash,
        "loaded_bytes_sha256": value.loaded_bytes_sha256,
        "same_bytes_binding_status": value.same_bytes_binding_status,
        "hash_check_profile": value.hash_check_profile,
    }


def _training_payload(value: TrainingLineageResolutionV1) -> dict[str, Any]:
    return {
        "status": value.status,
        "reason": value.reason,
        "provenance_schema_version": value.provenance_schema_version,
        "manifest_hash": value.manifest_hash,
        "training_source_hash": value.training_source_hash,
        "training_pit_hash": value.training_pit_hash,
        "feature_registry_hash": value.feature_registry_hash,
        "feature_schema_hash": value.feature_schema_hash,
        "feature_transform_contract_hash": value.feature_transform_contract_hash,
        "transform_status": value.transform_status,
        "dataset_id": value.dataset_id,
        "dataset_hash": value.dataset_hash,
        "decision_date": value.decision_date,
        "training_as_of": value.training_as_of,
        "training_semantics": value.training_semantics,
        "decision_time_eligible": value.decision_time_eligible,
        "research_only": value.research_only,
        "cost_scenario_hash": value.cost_scenario_hash,
    }


def _probability_node_payload(value: ProbabilityLineageIdentityV1) -> dict[str, Any]:
    return {
        "position": value.position,
        "kind": value.kind,
        "candidate_id": value.candidate_id,
        "model_id": value.model_id,
        "manifest_hash": value.manifest_hash,
        "artifact_hash": value.artifact_hash,
        "freeze_hash": value.freeze_hash,
        "dataset_hash": value.dataset_hash,
        "baseline_id": value.baseline_id,
        "baseline_kind": value.baseline_kind,
        "transform_id": value.transform_id,
        "maximum_probability_change_bp": value.maximum_probability_change_bp,
        "node_sha256": value.node_sha256,
    }


def _runtime_payload(value: ModelRuntimeProfileV1) -> dict[str, Any]:
    return {
        "platform": value.platform,
        "python_version": list(value.python_version),
        "library_versions": _versions_payload(value.library_versions),
    }


def _versions_payload(value: tuple[ModelResolutionLibraryVersionV1, ...]) -> list[dict[str, str]]:
    return [{"library": item.library, "version": item.version} for item in value]


def _missing_binding_payload(value: UnknownModelBindingFieldsV1) -> dict[str, Any]:
    return {
        "release_id": value.release_id,
        "artifact_declared_qualified_class_path": value.artifact_declared_qualified_class_path,
        "quarantine_status": value.quarantine_status,
        "permission_status": value.permission_status,
        "transform_status": value.transform_status,
    }


def _domain_hash(domain: bytes, payload: Any) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + sha256(domain + canonical).hexdigest()


def _require_sha256(value: Any, field_name: str) -> str:
    if type(value) is not str or not value.startswith("sha256:") or len(value) != 71:
        raise ValueError(f"{field_name} must be a prefixed sha256 digest")
    if any(character not in "0123456789abcdef" for character in value[7:]):
        raise ValueError(f"{field_name} must be a lowercase sha256 digest")
    return value


def _optional_sha256(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_sha256(value, field_name)


def _require_text(value: Any, field_name: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text")
    return value


def _required_text(value: Any, field_name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be text")
    return _require_text(value, field_name)


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, field_name)


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if type(value) is not str:
        raise TypeError("optional model-resolution text must be str or None")
    return value


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if type(value) is not bool:
        raise TypeError("optional model-resolution flag must be bool or None")
    return value


def _optional_date(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if type(value) is not str:
        raise TypeError("optional model-resolution date must be str or None")
    return _require_date(value, "date")


def _require_date(value: str, field_name: str) -> str:
    from datetime import date

    try:
        normalized = date.fromisoformat(value).isoformat()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be ISO date") from exc
    if normalized != value:
        raise ValueError(f"{field_name} must use canonical ISO date")
    return value
