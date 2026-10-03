"""將已通過受控 pointer 的 shadow calibration 投影到推薦展示邊界。

Consumer 只讀取隔離 output root 的 active pointer 與 candidate artifact。pointer
不存在、artifact 不相容、feature vector 缺欄或資料品質不足時，一律回傳
rule-only/unavailable；不補零、不回填、不把 shadow model 變成正式下單模型。
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields as dataclass_fields, replace
from datetime import date
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sys
from threading import Lock, get_ident
from types import FunctionType
from typing import Any, Mapping, NoReturn, Protocol, Sequence, SupportsIndex, cast
from weakref import WeakValueDictionary

import joblib
import numpy as np
import scipy
import sklearn
from scipy.interpolate import interp1d as _ScipyInterp1d
from sklearn.impute import SimpleImputer
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app_module.recommendation_learning_paths import (
    resolve_recommendation_learning_paths,
)
from app_module.recommendation.personal_use_policy import (
    PERSONAL_CALIBRATED_PROBABILITY_MODE,
    PERSONAL_PROBABILITY_CHANGE_CAP_BP,
    PERSONAL_USE_POLICY_SCHEMA_V1,
    PersonalCalibrationCandidateV1,
    RecommendationPersonalUsePolicyV2,
    RecommendationPersonalUsePolicyV1,
)
from app_module.recommendation.model_resolution_facts import (
    CapabilityLoadedArtifactLineageEvidenceV1,
    CapabilityLoadedArtifactLineageNodeV1,
    RecommendationModelResolutionEvidenceV1,
    capture_model_resolution_evidence_v1,
)
from ml_module.model_artifact_loader import (
    ArtifactCompatibilityExpectation,
    SafeShadowModelArtifactLoader,
    SameBytesShadowModelArtifactWithManifestLoadResultV1,
)
from ml_module.model_artifact_manifest import FeatureSchema, ModelArtifactManifest
from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY
from ml_module.recommendation_calibration_training import (
    InvalidCalibrationOutputError,
    RECOMMENDATION_RETURN_BASIS,
    RunnableRecommendationCalibrationModel,
    RecommendationPrediction,
    recommendation_cost_contract_hash,
    recommendation_label_contract_id,
    recommendation_label_registry_hash,
    candidate_freeze_hash,
)
from ml_module.recommendation_cost_scenario import (
    LEGACY_RECOMMENDATION_COST_SCENARIO_ID,
    LEGACY_RECOMMENDATION_COST_SCENARIO_VERSION,
    RecommendationCostScenario,
    RecommendationCostScenarioError,
    cost_scenario_from_metadata,
)


from ml_module.probability_calibration import FittedShadowProbabilityCalibrator
from ml_module.recommendation_calibration_authority import RecommendationPromotionPolicy
from ml_module.recommendation_probability_transform import (
    AFTER_COST_NULL_BENCHMARK_BASELINE_ID,
    AFTER_COST_NULL_BENCHMARK_PROBABILITY_BP,
    NULL_BENCHMARK_BASELINE_ID,
    NULL_BENCHMARK_PROBABILITY_BP,
    PROBABILITY_LINEAGE_SCHEMA_VERSION,
    PROBABILITY_TRANSFORM_ID,
    RecommendationProbabilityTransform,
)
from ml_module.recommendation_training_lineage import (
    RecommendationTrainingLineageError,
    read_recommendation_training_lineage,
)
from ml_module.recommendation_inference_provenance import (
    RecommendationProvenanceError,
    build_training_provenance,
    validate_provenance_compatibility,
    verify_inference_provenance,
)
from ml_module.prepared_source_contract import VerifiedSourceContractEvidenceV1


_PERSONAL_USE_POLICY_SCHEMA_V2 = "recommendation-personal-use-policy.v2"
_MODEL_GRAPH_SCHEMA_VERSION = "r026-known-model-graph.v1"
_SUPPORTED_MODEL_GRAPH_RUNTIME_PROFILES: frozenset[tuple[Any, ...]] = frozenset(
    {
        (
            "win32",
            (3, 11, 9),
            "1.26.4",  # NumPy 1 組合
            "1.8.0",  # scikit-learn 版本
            "1.16.3",  # SciPy 版本
            "1.5.2",  # joblib 版本
        ),
        (
            "win32",
            (3, 11, 9),
            "2.3.5",  # NumPy 2 組合
            "1.8.0",  # scikit-learn 版本
            "1.16.3",  # SciPy 版本
            "1.5.2",  # joblib 版本
        ),
    }
)
_MAX_MODEL_GRAPH_DEPTH = 24
_MAX_MODEL_GRAPH_NODES = 4096
_MAX_MODEL_GRAPH_ARRAYS = 512
_MAX_MODEL_GRAPH_ARRAY_BYTES = 64 * 1024 * 1024
_MAX_MODEL_GRAPH_ARRAY_ELEMENTS = 1_000_000
_MAX_LIVE_INVOCATION_CAPABILITIES = 16
_NO_MODEL_PROJECTION_CAPABILITY_SEAL = object()
_POINTER_BYTES_UNSET = object()
# Capture the reviewed callables once; do not trust later runtime rebinding of
# SciPy's class attributes to widen the model-graph schema.
_VERIFIED_SCIPY_INTERP1D_CALLS = tuple(
    candidate
    for candidate in (
        getattr(_ScipyInterp1d, "_call_linear_np", None),
        getattr(_ScipyInterp1d, "_call_linear", None),
    )
    if type(candidate) is FunctionType
    and candidate.__closure__ is None
    and candidate.__defaults__ in (None, ())
    and candidate.__kwdefaults__ is None
    and not candidate.__dict__
)


@dataclass(frozen=True)
class _ModelResolutionCaptureInputs:
    """只在 fresh resolve 內暫存，待外層 bytes/identity checks 完成後封裝。"""

    pointer: Mapping[str, Any]
    candidate_payload: Mapping[str, Any]
    manifest: ModelArtifactManifest
    loaded_model_training_as_of: Any
    training_provenance: Mapping[str, Any]
    probability_lineage: tuple[Mapping[str, Any], ...]
    runtime_profile: tuple[Any, ...]


@dataclass(frozen=True)
class _CapabilityPointerBytesEvidenceV1:
    """Capability 專用 pointer 原始 bytes 與 canonical payload 摘要。"""

    raw_bytes_sha256: str
    canonical_payload_sha256: str
    canonicalization_id: str = "recommendation-consumer-json.v1"


@dataclass(frozen=True)
class _CapabilityCandidateJsonBytesNodeV1:
    """同次 candidate JSON parse 的 immutable bytes/identity evidence。"""

    position: int
    kind: str
    candidate_id: str | None
    model_id: str | None
    normalized_candidate_root: str | None
    manifest_hash: str | None
    artifact_hash: str | None
    freeze_hash: str | None
    dataset_hash: str | None
    raw_bytes_sha256: str | None
    canonical_payload_sha256: str | None

    def to_payload(self) -> dict[str, Any]:
        return {
            "position": self.position,
            "kind": self.kind,
            "candidate_id": self.candidate_id,
            "model_id": self.model_id,
            "normalized_candidate_root": self.normalized_candidate_root,
            "manifest_hash": self.manifest_hash,
            "artifact_hash": self.artifact_hash,
            "freeze_hash": self.freeze_hash,
            "dataset_hash": self.dataset_hash,
            "raw_bytes_sha256": self.raw_bytes_sha256,
            "canonical_payload_sha256": self.canonical_payload_sha256,
        }


@dataclass(frozen=True)
class _CapabilityCandidateJsonBytesLineageV1:
    """Capability-local ordered candidate JSON evidence, including null baseline."""

    nodes: tuple[_CapabilityCandidateJsonBytesNodeV1, ...]
    schema_version: str = "recommendation-capability-candidate-json-bytes.v1"
    canonicalization_id: str = "recommendation-candidate-json.v1"

    def __post_init__(self) -> None:
        if (
            type(self.nodes) is not tuple
            or not self.nodes
            or any(type(node) is not _CapabilityCandidateJsonBytesNodeV1 for node in self.nodes)
            or tuple(node.position for node in self.nodes) != tuple(range(len(self.nodes)))
            or self.nodes[0].kind != "null_benchmark"
            or any(node.kind == "null_benchmark" for node in self.nodes[1:])
            or any(node.kind != "active_model" for node in self.nodes[1:])
        ):
            raise ValueError("candidate JSON evidence lineage is invalid")

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "canonicalization_id": self.canonicalization_id,
            "nodes": [node.to_payload() for node in self.nodes],
        }


@dataclass(frozen=True)
class _CapabilityModelManifestBytesNodeV1:
    """保存單次解析之 manifest 身分與原始 bytes 摘要。"""

    position: int
    kind: str
    candidate_id: str | None
    model_id: str | None
    normalized_candidate_root: str | None
    raw_bytes_sha256: str | None
    canonical_manifest_hash: str | None

    def __post_init__(self) -> None:
        if type(self.position) is not int or self.position < 0:
            raise ValueError("manifest lineage position must be non-negative")
        if self.kind not in {"null_benchmark", "active_model"}:
            raise ValueError("manifest lineage node kind is unsupported")
        if self.kind == "null_benchmark":
            if any(
                value is not None
                for value in (
                    self.candidate_id,
                    self.model_id,
                    self.normalized_candidate_root,
                    self.raw_bytes_sha256,
                    self.canonical_manifest_hash,
                )
            ):
                raise ValueError("null benchmark cannot carry manifest evidence")
        elif (
            not self.candidate_id
            or not self.model_id
            or not self.normalized_candidate_root
            or not _is_prefixed_sha256(self.raw_bytes_sha256)
            or not _is_prefixed_sha256(self.canonical_manifest_hash)
        ):
            raise ValueError("active model requires captured manifest evidence")

    def to_payload(self) -> dict[str, Any]:
        return {
            "position": self.position,
            "kind": self.kind,
            "candidate_id": self.candidate_id,
            "model_id": self.model_id,
            "normalized_candidate_root": self.normalized_candidate_root,
            "raw_bytes_sha256": self.raw_bytes_sha256,
            "canonical_manifest_hash": self.canonical_manifest_hash,
        }


@dataclass(frozen=True)
class _CapabilityModelManifestBytesLineageV1:
    """保存單次 invocation capability 的 active 與 ancestor manifest 順序證據。"""

    nodes: tuple[_CapabilityModelManifestBytesNodeV1, ...]
    schema_version: str = "recommendation-capability-model-manifest-bytes.v1"
    canonicalization_id: str = "ml-model-artifact-manifest.self-hash.v1"

    def __post_init__(self) -> None:
        if (
            type(self.nodes) is not tuple
            or len(self.nodes) < 2
            or any(type(node) is not _CapabilityModelManifestBytesNodeV1 for node in self.nodes)
            or tuple(node.position for node in self.nodes) != tuple(range(len(self.nodes)))
            or self.nodes[0].kind != "null_benchmark"
            or any(node.kind != "active_model" for node in self.nodes[1:])
            or self.schema_version != "recommendation-capability-model-manifest-bytes.v1"
            or self.canonicalization_id != "ml-model-artifact-manifest.self-hash.v1"
        ):
            raise ValueError("model manifest evidence lineage is invalid")

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "canonicalization_id": self.canonicalization_id,
            "nodes": [node.to_payload() for node in self.nodes],
        }


@dataclass(frozen=True)
class RecommendationCalibrationProjection:
    stock_code: str
    ranking_score_bp: int | None
    ranking_percentile_bp: int | None
    ranking_method: str
    calibrated_probability_bp: int | None
    calibrated_probability_status: str
    after_cost_profit_probability_bp: int | None
    after_cost_profit_probability_status: str
    confidence_tier: str
    evidence_confidence: str
    sample_size: int | None
    horizon: str
    cost_basis: str
    cost_basis_bp: int | None
    model_version: str
    dataset_version: str
    source_trace: tuple[str, ...]
    probability_transform_id: str = PROBABILITY_TRANSFORM_ID
    probability_baseline_id: str = NULL_BENCHMARK_BASELINE_ID
    probability_baseline_kind: str = "null_benchmark"
    probability_baseline_probability_bp: int | None = None
    raw_calibrated_probability_bp: int | None = None
    raw_after_cost_profit_probability_bp: int | None = None
    warnings: tuple[str, ...] = ()
    status: str = "unavailable"
    cost_policy_id: str | None = None
    cost_policy_version: str | None = None
    cost_scenario_id: str = LEGACY_RECOMMENDATION_COST_SCENARIO_ID
    cost_scenario_version: str = LEGACY_RECOMMENDATION_COST_SCENARIO_VERSION
    cost_scenario_hash: str | None = None
    policy_estimate_date: str | None = None
    research_order_amount_twd: str | None = None
    research_order_quantity_shares: int | None = None
    lot_type: str | None = None
    instrument_type: str | None = None
    cost_estimate_source: str = "legacy_fixed_assumption"
    training_provenance: Mapping[str, Any] = field(default_factory=dict)
    inference_provenance: Mapping[str, Any] = field(default_factory=dict)
    provenance_compatibility: Mapping[str, Any] = field(default_factory=dict)
    provenance_status: str = "unavailable"
    projection_contract_hash: str | None = None
    selection_authority: str = "rule_top_n"
    selection_score_kind: str = "rule_total_score"
    selection_percentile_kind: str = "rule_percentile"
    model_ranking_kind: str = "model_return_bp"
    # These fields are part of the active model's forward-label contract, not
    # reader-time defaults.  Publishing them with each projection row lets a
    # later action/outcome retain the exact training/evaluation identity.
    label_registry_hash: str = ""
    label_contract_id: str = ""
    return_basis: str = ""

    def __post_init__(self) -> None:
        for field_name in (
            "calibrated_probability_bp",
            "after_cost_profit_probability_bp",
            "ranking_percentile_bp",
        ):
            value = getattr(self, field_name)
            if value is not None and not 0 <= value <= 10_000:
                raise ValueError(f"{field_name} must be within 0..10000 bp")
        if self.sample_size is not None and self.sample_size < 0:
            raise ValueError("sample_size must be non-negative")

    @classmethod
    def unavailable(
        cls,
        *,
        stock_code: str,
        warning: str,
        ranking_score_bp: int | None = None,
        ranking_percentile_bp: int | None = None,
    ) -> "RecommendationCalibrationProjection":
        return cls(
            stock_code=stock_code,
            ranking_score_bp=ranking_score_bp,
            ranking_percentile_bp=ranking_percentile_bp,
            ranking_method="rule_only",
            calibrated_probability_bp=None,
            calibrated_probability_status="unavailable",
            after_cost_profit_probability_bp=None,
            after_cost_profit_probability_status="unavailable",
            confidence_tier="unavailable",
            evidence_confidence="missing",
            sample_size=None,
            horizon="20 trading days",
            cost_basis="unavailable",
            cost_basis_bp=None,
            model_version="",
            dataset_version="",
            source_trace=("recommendation_calibration_consumer",),
            probability_transform_id=PROBABILITY_TRANSFORM_ID,
            probability_baseline_id=NULL_BENCHMARK_BASELINE_ID,
            probability_baseline_kind="unavailable",
            probability_baseline_probability_bp=None,
            raw_calibrated_probability_bp=None,
            raw_after_cost_profit_probability_bp=None,
            warnings=(warning,),
            status="rule_only",
            training_provenance=_legacy_training_provenance("projection_unavailable"),
            inference_provenance={},
            provenance_compatibility={
                "schema_version": "recommendation-calibration-provenance-compatibility.v1",
                "status": "blocked",
                "reason": warning,
            },
            provenance_status="unavailable",
            selection_authority="rule_top_n",
            selection_score_kind="rule_total_score",
            selection_percentile_kind="rule_percentile",
            model_ranking_kind="model_return_bp",
            label_registry_hash="",
            label_contract_id="",
            return_basis="",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "stock_code": self.stock_code,
            "ranking_score_bp": self.ranking_score_bp,
            "ranking_percentile_bp": self.ranking_percentile_bp,
            "ranking_method": self.ranking_method,
            "calibrated_probability_bp": self.calibrated_probability_bp,
            "calibrated_probability_status": self.calibrated_probability_status,
            "after_cost_profit_probability_bp": self.after_cost_profit_probability_bp,
            "after_cost_profit_probability_status": self.after_cost_profit_probability_status,
            "confidence_tier": self.confidence_tier,
            "evidence_confidence": self.evidence_confidence,
            "sample_size": self.sample_size,
            "horizon": self.horizon,
            "cost_basis": self.cost_basis,
            "cost_basis_bp": self.cost_basis_bp,
            "model_version": self.model_version,
            "dataset_version": self.dataset_version,
            "source_trace": list(self.source_trace),
            "probability_transform_id": self.probability_transform_id,
            "probability_baseline_id": self.probability_baseline_id,
            "probability_baseline_kind": self.probability_baseline_kind,
            "probability_baseline_probability_bp": self.probability_baseline_probability_bp,
            "population_probability_bp": self.probability_baseline_probability_bp,
            "raw_calibrated_probability_bp": self.raw_calibrated_probability_bp,
            "raw_after_cost_profit_probability_bp": self.raw_after_cost_profit_probability_bp,
            "warnings": list(self.warnings),
            "status": self.status,
            "cost_policy_id": self.cost_policy_id,
            "cost_policy_version": self.cost_policy_version,
            "cost_scenario_id": self.cost_scenario_id,
            "cost_scenario_version": self.cost_scenario_version,
            "cost_scenario_hash": self.cost_scenario_hash,
            "policy_estimate_date": self.policy_estimate_date,
            "research_order_amount_twd": self.research_order_amount_twd,
            "research_order_quantity_shares": self.research_order_quantity_shares,
            "lot_type": self.lot_type,
            "instrument_type": self.instrument_type,
            "cost_estimate_source": self.cost_estimate_source,
            "training_provenance": dict(self.training_provenance),
            "inference_provenance": dict(self.inference_provenance),
            "provenance_compatibility": dict(self.provenance_compatibility),
            "provenance_status": self.provenance_status,
            "projection_contract_hash": self.projection_contract_hash,
            "selection_authority": self.selection_authority,
            "selection_score_kind": self.selection_score_kind,
            "selection_percentile_kind": self.selection_percentile_kind,
            "model_ranking_kind": self.model_ranking_kind,
            "label_registry_hash": self.label_registry_hash,
            "label_contract_id": self.label_contract_id,
            "return_basis": self.return_basis,
        }


class _ProjectionInvocationCapabilityProtocol(Protocol):
    """限制原投影只接受持有本次執行權限的 capability。"""

    def assert_projection_use(
        self,
        consumer: RecommendationCalibrationConsumer,
        decision_date: str,
    ) -> None: ...


class RecommendationCalibrationConsumer:
    """Fail-closed inference adapter for Recommendation → Advice → Presentation."""

    def __init__(
        self,
        *,
        pointer_path: str | Path,
        feature_schema: FeatureSchema,
        feature_registry_hash: str,
        data_root: str | Path | None = None,
        expected_model_family: str = "recommendation_absolute_calibration_v1",
        personal_use_policy: Any | None = None,
        personal_use_policy_bytes: bytes | None = None,
    ) -> None:
        self.pointer_path = Path(pointer_path).resolve()
        self.feature_schema = feature_schema
        self.feature_registry_hash = feature_registry_hash
        self.expected_model_family = expected_model_family
        if personal_use_policy is not None:
            validate_snapshot = getattr(personal_use_policy, "validate_snapshot", None)
            if not callable(validate_snapshot):
                raise ValueError("personal consumer 需要可重驗 snapshot 的 policy")
            personal_use_policy = validate_snapshot()
        self._personal_use_policy_bytes = (
            personal_use_policy_bytes
            if personal_use_policy_bytes is not None
            else (
                personal_use_policy.storage_bytes
                if personal_use_policy is not None
                else None
            )
        )
        if personal_use_policy is not None:
            if (
                type(self._personal_use_policy_bytes) is not bytes
                or personal_use_policy.storage_path is None
                or self._personal_use_policy_bytes != personal_use_policy.storage_bytes
            ):
                raise ValueError("personal consumer 必須綁定已保存 policy bytes")
        self._personal_use_policy = personal_use_policy
        self._personal_selection_active = False
        self._loader = SafeShadowModelArtifactLoader(data_root=data_root)
        self._loaded_pointer: Mapping[str, Any] | None = None
        self._model: Any | None = None
        self._baseline_model: Any | None = None
        self._baseline_identity: Mapping[str, Any] | None = None
        self._lineage_models: tuple[tuple[Mapping[str, Any], Any], ...] = ()
        self._probability_lineage: tuple[Mapping[str, Any], ...] = ()
        self._training_provenance: Mapping[str, Any] = _legacy_training_provenance(
            "active_pointer_missing"
        )
        self._blocker: str = "active_pointer_missing"
        self._cost_scenario: RecommendationCostScenario | None = None
        self._pointer_stat: tuple[int, int] | None = None
        self._loaded_decision_date: str | None = None
        self._invocation_capability_lock = Lock()
        self._invocation_capabilities: WeakValueDictionary[
            str, _InvocationProjectionCapability | _NoModelProjectionCapability
        ] = WeakValueDictionary()
        self._capture_model_resolution_evidence = False
        self._model_resolution_runtime_profile: tuple[Any, ...] | None = None
        self._model_resolution_capture_inputs: _ModelResolutionCaptureInputs | None = None
        self._captured_pointer_bytes_for_reload: bytes | None = None
        self._model_resolution_captured_pointer_bytes_sha256: str | None = None
        self._model_resolution_active_artifact_sha256: str | None = None
        self._model_resolution_active_candidate_json_hashes: tuple[str, str] | None = None
        self._model_resolution_candidate_json_lineage: (
            _CapabilityCandidateJsonBytesLineageV1 | None
        ) = None
        self._model_resolution_active_manifest_result: (
            SameBytesShadowModelArtifactWithManifestLoadResultV1 | None
        ) = None
        self._model_resolution_manifest_nodes_by_position: dict[
            int, _CapabilityModelManifestBytesNodeV1
        ] = {}
        self._model_resolution_manifest_lineage: (
            _CapabilityModelManifestBytesLineageV1 | None
        ) = None
        self._model_resolution_captured_manifest_paths_and_bytes: list[
            tuple[Path, bytes]
        ] = []
        self._model_resolution_loaded_artifact_lineage: (
            CapabilityLoadedArtifactLineageEvidenceV1 | None
        ) = None

    def _current_pointer_stat(self) -> tuple[int, int] | None:
        if self._personal_use_policy is not None:
            raw = self._personal_use_policy_bytes
            if type(raw) is not bytes:
                return None
            digest_tail = self._personal_use_policy.policy_sha256[7:23]
            return len(raw), int(digest_tail, 16)
        return _path_stat(self.pointer_path)

    def _personal_policy_storage_is_current(self) -> bool:
        policy = self._personal_use_policy
        expected_bytes = self._personal_use_policy_bytes
        if policy is None:
            return True
        path = policy.storage_path
        if (
            path is None
            or type(expected_bytes) is not bytes
            or path.resolve() != self.pointer_path
            or path.is_symlink()
        ):
            return False
        try:
            return path.read_bytes() == expected_bytes
        except OSError:
            return False

    def resolve_invocation_projection_capability(
        self,
        *,
        invocation_scope_id: str,
        decision_date: str,
        expected_identity: Mapping[str, Any],
    ) -> "_InvocationProjectionCapability | None":
        """以 fresh safe-loader 解析結果建立一次性、invocation-local 投影能力。

        此路徑直接讀取 pointer bytes，再建立全新 consumer 重新走
        SafeShadowModelArtifactLoader；不依賴原 consumer 的 stat cache，也不複製其
        model、lineage 或 mutable provenance cache。只有呼叫端先前捕獲的 identity、
        fresh consumer identity 與 pointer bytes 前後讀值相符時才回傳能力。能力只
        保留 fresh consumer，不能序列化、複製或重用。這是 model-resolution
        capability，不是 pointer lease；resolve 返回後的 pointer 變更仍不在保護內。
        """

        if (
            type(invocation_scope_id) is not str
            or not invocation_scope_id
            or not invocation_scope_id.isascii()
            or any(not (char.isalnum() or char in "-_.") for char in invocation_scope_id)
        ):
            return None
        current_day = _date_text_or_none(decision_date)
        if current_day is None or not isinstance(expected_identity, Mapping):
            return None
        if (
            type(self) is not RecommendationCalibrationConsumer
            or type(self._loader) is not SafeShadowModelArtifactLoader
            or self._loader._deserializer is not joblib.load
        ):
            return None
        runtime_profile = _current_model_graph_runtime_profile()
        if runtime_profile not in _SUPPORTED_MODEL_GRAPH_RUNTIME_PROFILES:
            return None
        with self._invocation_capability_lock:
            if invocation_scope_id in self._invocation_capabilities:
                return None
        resolved: RecommendationCalibrationConsumer | None = None
        try:
            expected_hash = _hash_payload(expected_identity)
            pointer_bytes_before = (
                self._personal_use_policy_bytes
                if self._personal_use_policy is not None
                else self.pointer_path.read_bytes()
            )
            if type(pointer_bytes_before) is not bytes:
                return None
            parsed_pointer_before = json.loads(pointer_bytes_before.decode("utf-8"))
            if not isinstance(parsed_pointer_before, Mapping):
                return None

            resolved = RecommendationCalibrationConsumer(
                pointer_path=self.pointer_path,
                feature_schema=self.feature_schema,
                feature_registry_hash=self.feature_registry_hash,
                data_root=self._loader._data_root,
                expected_model_family=self.expected_model_family,
                personal_use_policy=self._personal_use_policy,
                personal_use_policy_bytes=self._personal_use_policy_bytes,
            )
            # Preserve only the loader implementation/configuration.  The newly
            # deserialized model and every lineage model remain private to this
            # invocation-owned consumer.
            resolved._loader = SafeShadowModelArtifactLoader(
                data_root=self._loader._data_root,
                deserializer=joblib.load,
            )
            resolved._capture_model_resolution_evidence = True
            resolved._model_resolution_runtime_profile = runtime_profile
            resolved._model_resolution_captured_manifest_paths_and_bytes = []
            resolved._captured_pointer_bytes_for_reload = pointer_bytes_before
            if resolved.reload(decision_date=current_day) != "active":
                return None
            pointer_bytes_after = (
                self._personal_use_policy_bytes
                if self._personal_use_policy is not None
                else self.pointer_path.read_bytes()
            )
            if pointer_bytes_after != pointer_bytes_before:
                return None
            if (
                resolved._model_resolution_captured_pointer_bytes_sha256
                != _sha256_bytes(pointer_bytes_before)
            ):
                return None
            if resolved._personal_use_policy is None:
                if resolved._loaded_pointer != parsed_pointer_before:
                    return None
            elif (
                resolved._personal_use_policy.to_dict() != parsed_pointer_before
                or resolved._loaded_pointer is None
            ):
                return None
            resolved_identity = resolved.active_identity(decision_date=current_day)
            if resolved_identity is None or _hash_payload(resolved_identity) != expected_hash:
                return None
            capture = resolved._model_resolution_capture_inputs
            if capture is None or capture.pointer != resolved._loaded_pointer:
                return None
            model_resolution_evidence = capture_model_resolution_evidence_v1(
                pointer=capture.pointer,
                candidate_payload=capture.candidate_payload,
                manifest=capture.manifest,
                loaded_model_training_as_of=capture.loaded_model_training_as_of,
                training_provenance=capture.training_provenance,
                probability_lineage=capture.probability_lineage,
                runtime_profile=capture.runtime_profile,
                decision_date=current_day,
                pointer_bytes_equal=True,
                candidate_identity_path_rechecked=True,
            )
            loaded_artifact_lineage = resolved._model_resolution_loaded_artifact_lineage
            if loaded_artifact_lineage is None:
                return None
            candidate_json_lineage = resolved._model_resolution_candidate_json_lineage
            if candidate_json_lineage is None:
                return None
            manifest_lineage = resolved._model_resolution_manifest_lineage
            if (
                manifest_lineage is None
                or len(resolved._model_resolution_captured_manifest_paths_and_bytes)
                != len(manifest_lineage.nodes) - 1
                or not resolved._recheck_captured_model_manifests()
            ):
                return None
            if type(resolved._model) is not RunnableRecommendationCalibrationModel:
                return None
            if any(
                type(model) is not RunnableRecommendationCalibrationModel
                for _node, model in resolved._lineage_models
            ):
                return None
            if _loaded_model_state_aliases(self, resolved):
                return None
            if resolved._model is None or not resolved._lineage_models:
                return None
            capability = _InvocationProjectionCapability(
                owner=self,
                resolved_consumer=resolved,
                invocation_scope_id=invocation_scope_id,
                decision_date=current_day,
                identity_hash=expected_hash,
                model_resolution_evidence=model_resolution_evidence,
                loaded_artifact_lineage=loaded_artifact_lineage,
                pointer_bytes_evidence=_CapabilityPointerBytesEvidenceV1(
                    raw_bytes_sha256=_sha256_bytes(pointer_bytes_before),
                    canonical_payload_sha256=_hash_payload(parsed_pointer_before),
                ),
                candidate_json_bytes_lineage=candidate_json_lineage,
                model_manifest_bytes_lineage=manifest_lineage,
            )
            with self._invocation_capability_lock:
                if invocation_scope_id in self._invocation_capabilities:
                    return None
                live_capabilities = tuple(self._invocation_capabilities.values())
                if len(live_capabilities) >= _MAX_LIVE_INVOCATION_CAPABILITIES:
                    return None
                if any(
                    _loaded_model_state_aliases(
                        existing._resolved_consumer_for_isolation(), resolved
                    )
                    for existing in live_capabilities
                ):
                    return None
                self._invocation_capabilities[invocation_scope_id] = capability
            return capability
        except Exception:
            # This optional shadow capability is fail-closed.  The existing
            # legacy projection route remains responsible for its own errors.
            return None
        finally:
            if resolved is not None:
                # The immutable facts outlive only the capability; raw mutable
                # capture mappings are never retained by its private consumer.
                resolved._model_resolution_capture_inputs = None
                resolved._captured_pointer_bytes_for_reload = None
                resolved._model_resolution_captured_pointer_bytes_sha256 = None
                resolved._capture_model_resolution_evidence = False
                resolved._model_resolution_runtime_profile = None
                resolved._model_resolution_active_manifest_result = None
                resolved._model_resolution_manifest_nodes_by_position.clear()
                resolved._model_resolution_captured_manifest_paths_and_bytes.clear()

    def resolve_invocation_no_model_projection_capability_v1(
        self,
        *,
        invocation_scope_id: str,
        decision_date: str,
        expected_identity: Mapping[str, Any],
    ) -> "_NoModelProjectionCapability | None":
        """封存 fresh baseline reload 明確回報的 rule-only/no-model 終止結果。"""

        from app_module.recommendation.prepared_runtime_input import (
            NoModelShadowIdentityV1,
        )

        if (
            type(invocation_scope_id) is not str
            or not invocation_scope_id
            or not invocation_scope_id.isascii()
            or any(not (char.isalnum() or char in "-_.") for char in invocation_scope_id)
        ):
            return None
        current_day = _date_text_or_none(decision_date)
        if current_day is None or not isinstance(expected_identity, Mapping):
            return None
        try:
            expected_hash = _hash_payload(expected_identity)
            empty_identity_hash = _hash_payload({})
        except Exception:
            return None
        if expected_hash != empty_identity_hash:
            return None
        runtime_profile = _current_model_graph_runtime_profile()
        if (
            type(self) is not RecommendationCalibrationConsumer
            or type(self._loader) is not SafeShadowModelArtifactLoader
            or self._loader._deserializer is not joblib.load
            or runtime_profile not in _SUPPORTED_MODEL_GRAPH_RUNTIME_PROFILES
        ):
            return None
        with self._invocation_capability_lock:
            if invocation_scope_id in self._invocation_capabilities:
                return None

        resolved: RecommendationCalibrationConsumer | None = None
        try:
            if self._personal_use_policy is not None:
                pointer_raw_bytes = self._personal_use_policy_bytes
            else:
                pointer_raw_bytes = (
                    self.pointer_path.read_bytes()
                    if self.pointer_path.is_file()
                    else None
                )
            resolved = RecommendationCalibrationConsumer(
                pointer_path=self.pointer_path,
                feature_schema=self.feature_schema,
                feature_registry_hash=self.feature_registry_hash,
                data_root=self._loader._data_root,
                expected_model_family=self.expected_model_family,
                personal_use_policy=self._personal_use_policy,
                personal_use_policy_bytes=self._personal_use_policy_bytes,
            )
            resolved._loader = SafeShadowModelArtifactLoader(
                data_root=self._loader._data_root,
                deserializer=joblib.load,
            )
            reload_status = resolved.reload(
                decision_date=current_day,
                _captured_pointer_bytes=pointer_raw_bytes,
            )
            if reload_status != "rule_only" or resolved._model is not None:
                return None
            if self._personal_use_policy is not None:
                if pointer_raw_bytes != self._personal_use_policy_bytes:
                    return None
            elif pointer_raw_bytes is None:
                if self.pointer_path.is_file():
                    return None
            else:
                if self.pointer_path.read_bytes() != pointer_raw_bytes:
                    return None

            pointer_status: str | None = None
            if pointer_raw_bytes is not None:
                try:
                    raw_pointer_payload = json.loads(
                        pointer_raw_bytes.decode("utf-8")
                    )
                except (UnicodeDecodeError, json.JSONDecodeError):
                    raw_pointer_payload = None
                if isinstance(raw_pointer_payload, Mapping):
                    raw_pointer_status = raw_pointer_payload.get("status")
                    if type(raw_pointer_status) is str:
                        pointer_status = raw_pointer_status
            identity = NoModelShadowIdentityV1(
                decision_date=current_day,
                reload_status="rule_only",
                blocker=resolved._blocker,
                pointer_status=pointer_status,
                pointer_raw_bytes=pointer_raw_bytes,
            )
            capability = _NoModelProjectionCapability(
                owner=self,
                resolved_consumer=resolved,
                invocation_scope_id=invocation_scope_id,
                decision_date=current_day,
                identity_hash=expected_hash,
                identity=identity,
                _seal=_NO_MODEL_PROJECTION_CAPABILITY_SEAL,
            )
            with self._invocation_capability_lock:
                if invocation_scope_id in self._invocation_capabilities:
                    return None
                live_capabilities = tuple(self._invocation_capabilities.values())
                if len(live_capabilities) >= _MAX_LIVE_INVOCATION_CAPABILITIES:
                    return None
                if any(
                    _loaded_model_state_aliases(
                        existing._resolved_consumer_for_isolation(), resolved
                    )
                    for existing in live_capabilities
                ):
                    return None
                self._invocation_capabilities[invocation_scope_id] = capability
            return capability
        except Exception:
            return None

    def reload(
        self,
        *,
        decision_date: str | None = None,
        _captured_pointer_bytes: bytes | None | object = _POINTER_BYTES_UNSET,
    ) -> str:
        """Load and validate the pointer once; return machine-readable status."""

        self._loaded_pointer = None
        self._model = None
        self._baseline_model = None
        self._baseline_identity = None
        self._lineage_models = ()
        self._probability_lineage = ()
        self._training_provenance = _legacy_training_provenance(
            "training_lineage_not_loaded"
        )
        self._blocker = "active_pointer_missing"
        self._cost_scenario = None
        self._pointer_stat = None
        self._loaded_decision_date = None
        self._personal_selection_active = False
        self._model_resolution_capture_inputs = None
        self._model_resolution_captured_pointer_bytes_sha256 = None
        self._model_resolution_active_artifact_sha256 = None
        self._model_resolution_active_candidate_json_hashes = None
        self._model_resolution_candidate_json_lineage = None
        self._model_resolution_active_manifest_result = None
        self._model_resolution_manifest_nodes_by_position.clear()
        self._model_resolution_manifest_lineage = None
        self._model_resolution_captured_manifest_paths_and_bytes.clear()
        self._model_resolution_loaded_artifact_lineage = None
        if not self._personal_policy_storage_is_current():
            self._blocker = "personal_use_policy_changed_since_load"
            return "rule_only"
        if _captured_pointer_bytes is _POINTER_BYTES_UNSET:
            if self._personal_use_policy is not None:
                if type(self._personal_use_policy_bytes) is not bytes:
                    self._blocker = "personal_use_policy_snapshot_missing"
                    return "rule_only"
            elif not self.pointer_path.is_file():
                return "rule_only"
        elif _captured_pointer_bytes is None:
            return "rule_only"
        elif type(_captured_pointer_bytes) is not bytes:
            raise TypeError("captured pointer bytes 必須是 bytes 或 None")
        try:
            captured_pointer_bytes = (
                self._captured_pointer_bytes_for_reload
                if self._capture_model_resolution_evidence
                else None
            )
            if _captured_pointer_bytes is not _POINTER_BYTES_UNSET:
                pointer_text = cast(bytes, _captured_pointer_bytes).decode("utf-8")
            elif self._personal_use_policy is not None:
                if type(self._personal_use_policy_bytes) is not bytes:
                    self._blocker = "personal_use_policy_snapshot_missing"
                    return "rule_only"
                if self._capture_model_resolution_evidence:
                    self._model_resolution_captured_pointer_bytes_sha256 = (
                        _sha256_bytes(self._personal_use_policy_bytes)
                    )
                pointer_text = self._personal_use_policy_bytes.decode("utf-8")
            elif captured_pointer_bytes is None:
                pointer_text = self.pointer_path.read_text(encoding="utf-8")
            else:
                self._model_resolution_captured_pointer_bytes_sha256 = _sha256_bytes(
                    captured_pointer_bytes
                )
                pointer_text = captured_pointer_bytes.decode("utf-8")
            pointer = json.loads(pointer_text)
        except UnicodeDecodeError:
            self._blocker = "active_pointer_invalid_encoding"
            return "rule_only"
        except (OSError, json.JSONDecodeError):
            self._blocker = "active_pointer_invalid_json"
            return "rule_only"
        if not isinstance(pointer, Mapping):
            self._blocker = "active_pointer_schema_invalid"
            return "rule_only"
        personal_candidate_payload: Mapping[str, Any] | None = None
        personal_candidate_bytes: bytes | None = None
        candidate_path: Path | None = None
        personal_source_time_policy: Any | None = None
        pointer_schema = pointer.get("schema_version")
        if pointer_schema in {
            PERSONAL_USE_POLICY_SCHEMA_V1,
            _PERSONAL_USE_POLICY_SCHEMA_V2,
        }:
            personal_policy = self._personal_use_policy
            policy_schema = (
                personal_policy.to_dict().get("schema_version")
                if personal_policy is not None
                else None
            )
            if (
                personal_policy is None
                or policy_schema != pointer_schema
                or (
                    pointer_schema == _PERSONAL_USE_POLICY_SCHEMA_V2
                    and (
                        type(personal_policy) is not RecommendationPersonalUsePolicyV2
                        or personal_policy.version != 2
                    )
                )
            ):
                self._blocker = "personal_use_policy_not_bound_to_consumer"
                return "rule_only"
            personal_policy_path = personal_policy.storage_path
            if personal_policy_path is None:
                self._blocker = "personal_use_policy_storage_path_missing"
                return "rule_only"
            if (
                personal_policy.to_dict() != pointer
                or personal_policy_path.resolve() != self.pointer_path
            ):
                self._blocker = "personal_use_policy_not_bound_to_consumer"
                return "rule_only"
            if personal_policy.mode != PERSONAL_CALIBRATED_PROBABILITY_MODE:
                self._loaded_pointer = dict(pointer)
                self._pointer_stat = self._current_pointer_stat()
                self._loaded_decision_date = _date_text_or_none(decision_date)
                self._blocker = "personal_use_policy_rule_only"
                return "rule_only"
            candidate_ref = personal_policy.candidate
            if candidate_ref is None:
                self._blocker = "personal_use_policy_candidate_missing"
                return "rule_only"
            source_time_trust = getattr(personal_policy, "source_time_trust", None)
            if pointer_schema == PERSONAL_USE_POLICY_SCHEMA_V1:
                # V1 沒有獨立保存的 user-declared source binding，不能從環境預設推定信任。
                self._blocker = "independent_source_time_authority_missing"
                return "rule_only"
            if not _personal_v2_source_trust_precheck(personal_policy):
                self._blocker = "personal_source_time_binding_missing_or_invalid"
                return "rule_only"
            personal_source_time_policy = personal_policy
            candidate_root = Path(candidate_ref.candidate_root)
            candidate_path = candidate_root / "candidate.json"
            try:
                if candidate_root.is_symlink() or candidate_path.is_symlink():
                    raise OSError("candidate identity path is a symlink")
                personal_candidate_bytes = candidate_path.read_bytes()
                if _sha256_bytes(personal_candidate_bytes) != candidate_ref.candidate_json_sha256:
                    raise ValueError("candidate JSON raw bytes changed")
                personal_candidate_payload = _read_json_object_bytes(
                    personal_candidate_bytes, candidate_path
                )
            except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
                self._blocker = "personal_use_policy_candidate_bytes_mismatch"
                return "rule_only"
            if not _personal_candidate_reference_matches(
                candidate_ref, personal_candidate_payload
            ):
                self._blocker = "personal_use_policy_candidate_identity_mismatch"
                return "rule_only"
            try:
                pointer = _personal_candidate_pointer(
                    personal_policy, personal_candidate_payload
                )
            except (TypeError, ValueError):
                self._blocker = "personal_use_policy_candidate_effective_date_invalid"
                return "rule_only"
            self._personal_selection_active = True
        elif pointer.get("schema_version") not in {
            "recommendation-calibration-active-pointer.v1",
            "recommendation-calibration-active-pointer.v2",
        }:
            self._blocker = "active_pointer_schema_invalid"
            return "rule_only"
        pointer_status = str(pointer.get("status") or "")
        if pointer_status == "rule_only":
            self._loaded_pointer = pointer
            self._pointer_stat = self._current_pointer_stat()
            self._loaded_decision_date = _date_text_or_none(decision_date)
            self._blocker = str(pointer.get("rollback_reason") or "rule_only_pointer")
            return "rule_only"
        if pointer_status != "active":
            self._blocker = str(pointer.get("status") or "active_pointer_not_active")
            return "rule_only"
        current_day = _date_text_or_none(decision_date)
        effective_day = _date_text_or_none(str(pointer.get("effective_date") or ""))
        if current_day is None or effective_day is None or effective_day > current_day:
            self._blocker = "active_pointer_effective_date_invalid"
            return "rule_only"
        candidate_text = str(pointer.get("candidate_root") or "").strip()
        if not candidate_text:
            self._blocker = "active_pointer_candidate_missing"
            return "rule_only"
        candidate_root = Path(candidate_text)
        if not candidate_root.is_absolute():
            candidate_root = (self.pointer_path.parent / candidate_root).resolve()
        try:
            scenario = cost_scenario_from_metadata(
                pointer,
                fixed_round_trip_cost_bp=_optional_int(pointer.get("fixed_round_trip_cost_bp")),
            )
        except (TypeError, ValueError, RecommendationCostScenarioError):
            self._blocker = "active_pointer_cost_scenario_invalid"
            return "rule_only"
        expected_label_hash = recommendation_label_registry_hash(
            cost_scenario=scenario if scenario.is_estimated else None
        )
        declared_label_hash = str(pointer.get("label_registry_hash") or "")
        if declared_label_hash and declared_label_hash != expected_label_hash:
            self._blocker = "active_pointer_label_registry_mismatch"
            return "rule_only"
        expected_cost_hash = recommendation_cost_contract_hash(
            scenario.fixed_round_trip_cost_bp,
            cost_scenario=scenario if scenario.is_estimated else None,
        )
        declared_cost_hash = str(pointer.get("cost_contract_hash") or "")
        if declared_cost_hash and declared_cost_hash != expected_cost_hash:
            self._blocker = "active_pointer_cost_contract_mismatch"
            return "rule_only"
        candidate_json_bytes: bytes | None = personal_candidate_bytes
        try:
            if personal_candidate_payload is not None:
                candidate_payload = personal_candidate_payload
            elif self._capture_model_resolution_evidence:
                candidate_json_bytes = (candidate_root / "candidate.json").read_bytes()
                candidate_payload = _read_json_object_bytes(
                    candidate_json_bytes, candidate_root / "candidate.json"
                )
            else:
                candidate_payload = _read_json(candidate_root / "candidate.json")
            candidate_scenario = cost_scenario_from_metadata(
                candidate_payload,
                fixed_round_trip_cost_bp=_optional_int(
                    candidate_payload.get("fixed_round_trip_cost_bp")
                ),
            )
        except (OSError, json.JSONDecodeError, TypeError, ValueError, RecommendationCostScenarioError):
            self._blocker = "active_pointer_candidate_cost_scenario_invalid"
            return "rule_only"
        declared_training_cutoff = "training_cutoff" in candidate_payload
        candidate_training_cutoff = _date_text_or_none(
            str(candidate_payload.get("training_cutoff") or "")
        )
        if declared_training_cutoff and candidate_training_cutoff is None:
            self._blocker = "candidate_training_cutoff_invalid"
            return "rule_only"
        if candidate_training_cutoff is not None and candidate_training_cutoff > current_day:
            self._blocker = "candidate_training_cutoff_after_decision"
            return "rule_only"
        if "training_semantics" in candidate_payload and candidate_payload.get("training_semantics") != "decision_time":
            self._blocker = "candidate_training_context_not_decision_time"
            return "rule_only"
        if "decision_time_eligible" in candidate_payload and candidate_payload.get("decision_time_eligible") is not True:
            self._blocker = "candidate_training_context_not_decision_time"
            return "rule_only"
        if "research_only" in candidate_payload and candidate_payload.get("research_only") is not False:
            self._blocker = "candidate_training_context_not_decision_time"
            return "rule_only"
        if candidate_scenario.scenario_hash != scenario.scenario_hash:
            self._blocker = "active_pointer_candidate_cost_scenario_mismatch"
            return "rule_only"
        if str(candidate_payload.get("label_registry_hash") or expected_label_hash) != expected_label_hash:
            self._blocker = "active_pointer_candidate_label_registry_mismatch"
            return "rule_only"
        expectation = ArtifactCompatibilityExpectation(
            expected_model_family=self.expected_model_family,
            expected_feature_registry_hash=self.feature_registry_hash,
            expected_label_registry_hash=expected_label_hash,
            expected_feature_schema=self.feature_schema,
            installed_library_versions=_library_versions(),
        )
        personal_training_provenance: Mapping[str, Any] | None = None
        if self._personal_selection_active:
            personal_training_provenance, training_error = (
                _load_candidate_training_provenance(
                    candidate_root=candidate_root,
                    candidate_payload=candidate_payload,
                    decision_date=current_day,
                    require_personal_source_time=True,
                    data_root=self._loader._data_root,
                    personal_use_policy=personal_source_time_policy,
                )
            )
            if training_error is not None:
                self._blocker = training_error
                return "rule_only"
            if not self._personal_policy_storage_is_current():
                self._blocker = "personal_use_policy_changed_since_load"
                return "rule_only"
            if (
                personal_training_provenance is None
                or personal_training_provenance.get("status") != "verified"
                or not candidate_payload.get("training_lineage_manifest_hash")
                or not candidate_payload.get("training_lineage_manifest_path")
                or personal_training_provenance.get("training_semantics")
                != "decision_time"
                or personal_training_provenance.get("decision_time_eligible") is not True
            ):
                self._blocker = "personal_candidate_training_lineage_unverified_fail_closed"
                return "rule_only"
        same_bytes_result = None
        if not self._personal_policy_storage_is_current():
            self._blocker = "personal_use_policy_changed_since_load"
            return "rule_only"
        if self._capture_model_resolution_evidence:
            same_bytes_result = self._loader.load_same_bytes_with_manifest_v1(
                candidate_root, expectation=expectation
            )
            loaded = same_bytes_result.artifact_result.artifact_result
        else:
            loaded = self._loader.load(candidate_root, expectation=expectation)
        if not self._personal_policy_storage_is_current():
            self._blocker = "personal_use_policy_changed_during_load"
            return "rule_only"
        if loaded.status != "shadow_model_ready" or loaded.model is None:
            self._blocker = loaded.blockers[0] if loaded.blockers else "candidate_load_failed"
            return "rule_only"
        if str(pointer.get("candidate_id") or "") != str(getattr(loaded.model, "model_id", "")):
            self._blocker = "active_pointer_candidate_identity_mismatch"
            return "rule_only"
        if self._capture_model_resolution_evidence:
            if (
                candidate_json_bytes is None
                or not _candidate_json_path_matches_bytes(
                    candidate_root, candidate_json_bytes
                )
                or not _pointer_candidate_payload_hashes_match(
                    pointer, candidate_root, loaded.manifest, candidate_payload
                )
            ):
                self._blocker = "active_pointer_candidate_hash_mismatch"
                return "rule_only"
            self._model_resolution_active_candidate_json_hashes = (
                _sha256_bytes(candidate_json_bytes),
                _hash_payload(candidate_payload),
            )
        elif not _pointer_candidate_hashes_match(
            pointer, candidate_root, loaded.manifest
        ):
            self._blocker = "active_pointer_candidate_hash_mismatch"
            return "rule_only"
        if self._personal_selection_active:
            if (
                type(pointer.get("maximum_probability_change_bp")) is not int
                or pointer.get("maximum_probability_change_bp")
                != PERSONAL_PROBABILITY_CHANGE_CAP_BP
            ):
                self._blocker = "personal_probability_change_cap_invalid"
                return "rule_only"
        elif pointer.get("policy_hash") != RecommendationPromotionPolicy().policy_hash:
            self._blocker = "active_pointer_policy_hash_mismatch"
            return "rule_only"
        elif int(pointer.get("maximum_probability_change_bp", -1)) != RecommendationPromotionPolicy().maximum_probability_change_bp:
            self._blocker = "active_pointer_cap_mismatch"
            return "rule_only"
        if not self._personal_selection_active:
            receipt_error = _pointer_receipt_error(pointer)
            if receipt_error is not None:
                self._blocker = receipt_error
                return "rule_only"
        training_as_of = _date_text_or_none(str(getattr(loaded.model, "training_as_of", "")))
        if training_as_of is None or training_as_of > current_day:
            self._blocker = "candidate_training_cutoff_after_decision"
            return "rule_only"
        if self._personal_selection_active:
            training_provenance = personal_training_provenance
            if training_provenance is None:
                self._blocker = "personal_candidate_training_lineage_unverified_fail_closed"
                return "rule_only"
        else:
            training_provenance, training_error = _load_candidate_training_provenance(
                candidate_root=candidate_root,
                candidate_payload=candidate_payload,
                decision_date=current_day,
                require_personal_source_time=False,
                data_root=self._loader._data_root,
            )
            if training_error is not None:
                self._blocker = training_error
                return "rule_only"
        if self._personal_selection_active and (
            training_provenance.get("status") != "verified"
            or not candidate_payload.get("training_lineage_manifest_hash")
            or not candidate_payload.get("training_lineage_manifest_path")
            or training_provenance.get("training_semantics") != "decision_time"
            or training_provenance.get("decision_time_eligible") is not True
        ):
            self._blocker = "personal_candidate_training_lineage_unverified_fail_closed"
            return "rule_only"
        if self._personal_selection_active:
            if candidate_path is None:
                self._blocker = "personal_use_policy_candidate_missing"
                return "rule_only"
            try:
                if candidate_path.read_bytes() != personal_candidate_bytes:
                    self._blocker = "personal_candidate_bytes_changed_during_load"
                    return "rule_only"
            except OSError:
                self._blocker = "personal_candidate_bytes_changed_during_load"
                return "rule_only"
        if self._capture_model_resolution_evidence:
            if (
                same_bytes_result is None
                or same_bytes_result.loaded_serialized_bytes_sha256 is None
                or same_bytes_result.captured_manifest_bytes is None
                or same_bytes_result.manifest_raw_bytes_sha256 is None
                or same_bytes_result.canonical_manifest_payload_sha256 is None
                or loaded.manifest is None
                or same_bytes_result.canonical_manifest_payload_sha256
                != loaded.manifest.manifest_hash
            ):
                self._blocker = "active_manifest_same_bytes_evidence_missing"
                return "rule_only"
            self._model_resolution_active_artifact_sha256 = (
                same_bytes_result.loaded_serialized_bytes_sha256
            )
            self._model_resolution_active_manifest_result = same_bytes_result
            self._model_resolution_captured_manifest_paths_and_bytes.append(
                (candidate_root / "manifest.json", same_bytes_result.captured_manifest_bytes)
            )
        self._loaded_pointer = pointer
        self._model = loaded.model
        self._cost_scenario = scenario
        self._training_provenance = training_provenance
        lineage, lineage_error = self._load_probability_lineage(pointer, loaded.model, current_day)
        if lineage_error is not None:
            self._loaded_pointer = None
            self._model = None
            self._blocker = lineage_error
            return "rule_only"
        self._probability_lineage = lineage
        if len(lineage) > 1:
            self._baseline_identity = lineage[-2]
            self._baseline_model = self._lineage_models[-2][1] if len(self._lineage_models) > 1 else None
        self._blocker = ""
        self._pointer_stat = self._current_pointer_stat()
        self._loaded_decision_date = current_day
        if self._capture_model_resolution_evidence:
            if loaded.manifest is None or self._model_resolution_runtime_profile is None:
                self._blocker = "model_resolution_capture_inputs_missing"
                self._model = None
                self._loaded_pointer = None
                self._probability_lineage = ()
                self._lineage_models = ()
                self._model_resolution_capture_inputs = None
                return "rule_only"
            self._model_resolution_capture_inputs = _ModelResolutionCaptureInputs(
                pointer=dict(pointer),
                candidate_payload=dict(candidate_payload),
                manifest=loaded.manifest,
                loaded_model_training_as_of=getattr(loaded.model, "training_as_of", None),
                training_provenance=dict(training_provenance),
                probability_lineage=tuple(dict(item) for item in lineage),
                runtime_profile=self._model_resolution_runtime_profile,
            )
        return "active"

    def active_after_cost_baseline(
        self,
        *,
        decision_date: str,
    ) -> tuple[str, int] | None:
        """Return a baseline only when the loaded candidate declares its contract.

        The independent null benchmark has a frozen 5,000 bp value.  A
        candidate using a different declared after-cost baseline does not carry
        its numeric rule value in the active model metadata, so the production
        recommendation path must leave that target unavailable rather than
        inventing one.
        """

        if self.reload(decision_date=decision_date) != "active" or self._model is None:
            return None
        baseline_id = str(getattr(self._model, "after_cost_baseline_id", "") or "").strip()
        if baseline_id != AFTER_COST_NULL_BENCHMARK_BASELINE_ID:
            return None
        return baseline_id, AFTER_COST_NULL_BENCHMARK_PROBABILITY_BP

    def _recheck_captured_model_manifests(self) -> bool:
        """比對能力建立前捕獲的每個 manifest path bytes。"""

        for manifest_path, captured_bytes in tuple(
            self._model_resolution_captured_manifest_paths_and_bytes
        ):
            try:
                if manifest_path.read_bytes() != captured_bytes:
                    return False
            except OSError:
                return False
        return bool(self._model_resolution_captured_manifest_paths_and_bytes)

    def active_cost_scenario(
        self,
        *,
        decision_date: str,
    ) -> RecommendationCostScenario | None:
        """Return the loaded cost lane without changing legacy identity shape."""

        if self.reload(decision_date=decision_date) != "active":
            return None
        return self._cost_scenario

    def predict_active(
        self,
        *,
        feature_values: Sequence[int | None],
        decision_date: str,
        baseline_probability_bp: int = NULL_BENCHMARK_PROBABILITY_BP,
        baseline_after_cost_probability_bp: int | None = None,
    ) -> RecommendationPrediction | None:
        """Return the effective active prediction after the frozen lineage cap."""

        current_day = _date_text_or_none(decision_date)
        if current_day is None:
            return None
        if (
            self._model is None
            or self._loaded_pointer is None
            or self._pointer_stat != self._current_pointer_stat()
            or self._loaded_decision_date != current_day
        ):
            self.reload(decision_date=current_day)
        if self._model is None or self._loaded_pointer is None or not self._lineage_models:
            return None
        try:
            return self._effective_prediction(
                feature_values=feature_values,
                baseline_probability_bp=baseline_probability_bp,
                baseline_after_cost_probability_bp=baseline_after_cost_probability_bp,
                node_index=len(self._lineage_models) - 1,
            )
        except (TypeError, ValueError, IndexError):
            return None

    def active_identity(self, *, decision_date: str) -> dict[str, Any] | None:
        current_day = _date_text_or_none(decision_date)
        if current_day is None:
            return None
        if (
            self._model is None
            or self._loaded_pointer is None
            or self._pointer_stat != self._current_pointer_stat()
            or self._loaded_decision_date != current_day
        ):
            self.reload(decision_date=current_day)
        if self._loaded_pointer is None or self._model is None:
            return None
        scenario_fields = (
            _scenario_identity_fields(self._cost_scenario, self._loaded_pointer)
            if self._cost_scenario is not None and self._cost_scenario.is_estimated
            else {}
        )
        return {
            "kind": "active_model",
            "pointer_version": self._loaded_pointer.get("pointer_version"),
            "candidate_id": self._loaded_pointer.get("candidate_id"),
            "candidate_root": self._loaded_pointer.get("candidate_root"),
            "candidate_manifest_hash": self._loaded_pointer.get("candidate_manifest_hash"),
            "candidate_artifact_hash": self._loaded_pointer.get("candidate_artifact_hash"),
            "candidate_freeze_hash": self._loaded_pointer.get("candidate_freeze_hash"),
            "dataset_hash": self._loaded_pointer.get("dataset_hash"),
            "effective_date": self._loaded_pointer.get("effective_date"),
            "model_id": getattr(self._model, "model_id", ""),
            "probability_lineage_schema_version": PROBABILITY_LINEAGE_SCHEMA_VERSION,
            "probability_lineage": [dict(item) for item in self._probability_lineage],
            "probability_lineage_hash": _hash_payload(self._probability_lineage),
            "training_provenance": dict(self._training_provenance),
            # 舊版 legacy pointer 的 active identity 必須維持原始欄位形狀，
            # 否則既有 active capture 的 identity hash 會被無意間改寫。
            **scenario_fields,
        }

    def champion_baseline(
        self,
        *,
        feature_values: Sequence[int | None],
        decision_date: str,
        baseline_probability_bp: int = NULL_BENCHMARK_PROBABILITY_BP,
        baseline_after_cost_probability_bp: int | None = None,
        _invocation_capability: _ProjectionInvocationCapabilityProtocol | None = None,
    ) -> RecommendationPrediction | None:
        """Return the previous champion's effective, already-delivered output."""

        current_day = _date_text_or_none(decision_date)
        if current_day is None:
            return None
        if _invocation_capability is not None:
            _invocation_capability.assert_projection_use(self, current_day)
        elif (
            self._model is None
            or self._loaded_pointer is None
            or self._pointer_stat != self._current_pointer_stat()
            or self._loaded_decision_date != current_day
        ):
            self.reload(decision_date=current_day)
        if self._baseline_model is None or len(self._lineage_models) < 2:
            return None
        try:
            return self._effective_prediction(
                feature_values=feature_values,
                baseline_probability_bp=baseline_probability_bp,
                baseline_after_cost_probability_bp=baseline_after_cost_probability_bp,
                node_index=len(self._lineage_models) - 2,
            )
        except (TypeError, ValueError, IndexError):
            return None

    def _load_probability_lineage(
        self,
        pointer: Mapping[str, Any],
        current_model: Any,
        decision_date: str,
    ) -> tuple[tuple[Mapping[str, Any], ...], str | None]:
        raw = pointer.get("probability_lineage")
        if raw is None:
            # Compatibility for a pre-lineage pointer.  It remains fail-closed
            # if its declared previous champion cannot be reloaded.
            lineage: list[Mapping[str, Any]] = [_null_lineage_node(int(pointer.get("maximum_probability_change_bp", 1_000)))]
            previous = _previous_identity(pointer)
            if previous is not None:
                lineage.append(_model_lineage_node(previous, baseline_id=NULL_BENCHMARK_BASELINE_ID, baseline_kind="null_benchmark", cap=int(pointer.get("maximum_probability_change_bp", 1_000))))
            lineage.append(_model_lineage_node(_pointer_identity(pointer), baseline_id=(str(lineage[-1].get("candidate_id") or "") if lineage[-1].get("kind") == "active_model" else NULL_BENCHMARK_BASELINE_ID), baseline_kind=("active_model" if lineage[-1].get("kind") == "active_model" else "null_benchmark"), cap=int(pointer.get("maximum_probability_change_bp", 1_000))))
        elif isinstance(raw, list) and raw and all(isinstance(item, Mapping) for item in raw):
            lineage = [dict(item) for item in raw]
        else:
            return (), "active_pointer_probability_lineage_invalid"
        if not lineage or lineage[0].get("kind") != "null_benchmark":
            return (), "active_pointer_probability_lineage_invalid"
        if lineage[0].get("baseline_id") != NULL_BENCHMARK_BASELINE_ID:
            return (), "active_pointer_probability_lineage_invalid"
        cap = int(pointer.get("maximum_probability_change_bp", -1))
        if cap < 0:
            return (), "active_pointer_cap_invalid"
        if self._capture_model_resolution_evidence:
            active_candidate_id = str(pointer.get("candidate_id") or "")
            active_positions = [
                index
                for index, node in enumerate(lineage)
                if str(node.get("candidate_id") or "") == active_candidate_id
            ]
            if (
                not active_candidate_id
                or active_positions != [len(lineage) - 1]
                or not _capability_active_lineage_node_matches_pointer(
                    lineage[-1], pointer, self.pointer_path.parent
                )
                or self._model_resolution_active_artifact_sha256 is None
            ):
                return (), "active_pointer_probability_lineage_identity_invalid"
        loaded_models: list[tuple[Mapping[str, Any], Any]] = []
        loaded_artifact_hashes_by_position: list[str | None] = [
            None for _node in lineage
        ]
        candidate_json_nodes_by_position: list[
            _CapabilityCandidateJsonBytesNodeV1 | None
        ] = [None for _node in lineage]
        for index, node in enumerate(lineage):
            if node.get("transform_id") != PROBABILITY_TRANSFORM_ID:
                return (), "active_pointer_probability_transform_invalid"
            if int(node.get("maximum_probability_change_bp", -1)) != cap:
                return (), "active_pointer_probability_lineage_cap_mismatch"
            if index == 0:
                continue
            expected_scenario = self._cost_scenario or _legacy_scenario_from_pointer(pointer)
            node_scenario_hash = str(node.get("cost_scenario_hash") or "")
            if expected_scenario.is_estimated and node_scenario_hash != expected_scenario.scenario_hash:
                return (), "active_pointer_probability_lineage_cost_scenario_mismatch"
            if node_scenario_hash and node_scenario_hash != expected_scenario.scenario_hash:
                return (), "active_pointer_probability_lineage_cost_scenario_mismatch"
            identity = {
                "candidate_id": node.get("candidate_id"),
                "model_id": node.get("model_id"),
                "candidate_root": node.get("candidate_root"),
                "candidate_manifest_hash": node.get("candidate_manifest_hash"),
                "candidate_artifact_hash": node.get("candidate_artifact_hash"),
                "candidate_freeze_hash": node.get("candidate_freeze_hash"),
                "dataset_hash": node.get("dataset_hash"),
            }
            for key in (
                "label_registry_hash", "cost_contract_hash", "fixed_round_trip_cost_bp",
                "cost_scenario_id", "cost_scenario_version", "cost_scenario_hash",
                "cost_basis", "cost_policy_id", "cost_policy_version",
                "policy_estimate_date", "research_order_amount_twd",
                "research_order_quantity_shares", "lot_type", "instrument_type",
                "cost_scenario",
            ):
                if key in node:
                    identity[key] = node[key]
            if not identity["candidate_id"] or node.get("model_id") != identity["candidate_id"]:
                return (), "active_pointer_probability_lineage_identity_invalid"
            parent = lineage[index - 1]
            expected_baseline = str(parent.get("candidate_id") or "") if parent.get("kind") == "active_model" else NULL_BENCHMARK_BASELINE_ID
            expected_kind = "active_model" if parent.get("kind") == "active_model" else "null_benchmark"
            if node.get("baseline_id") != expected_baseline or node.get("baseline_kind") != expected_kind:
                return (), "active_pointer_probability_lineage_baseline_invalid"
            if str(identity["candidate_id"]) == str(pointer.get("candidate_id")):
                model = current_model
                if self._capture_model_resolution_evidence:
                    loaded_artifact_hashes_by_position[index] = (
                        self._model_resolution_active_artifact_sha256
                    )
                    active_candidate_hashes = (
                        self._model_resolution_active_candidate_json_hashes
                    )
                    if active_candidate_hashes is None:
                        return (), "active_pointer_probability_lineage_candidate_json_missing"
                    candidate_json_node = _candidate_json_evidence_node(
                        position=index,
                        identity=node,
                        relative_to=self.pointer_path.parent,
                        raw_bytes_sha256=active_candidate_hashes[0],
                        canonical_payload_sha256=active_candidate_hashes[1],
                    )
                    if candidate_json_node is None:
                        return (), "active_pointer_probability_lineage_candidate_json_invalid"
                    candidate_json_nodes_by_position[index] = candidate_json_node
                    active_manifest_result = (
                        self._model_resolution_active_manifest_result
                    )
                    if active_manifest_result is None:
                        return (), "active_pointer_probability_lineage_manifest_bytes_missing"
                    manifest_node = _model_manifest_bytes_evidence_node(
                        position=index,
                        identity=node,
                        relative_to=self.pointer_path.parent,
                        load_result=active_manifest_result,
                    )
                    if manifest_node is None:
                        return (), "active_pointer_probability_lineage_manifest_bytes_invalid"
                    self._model_resolution_manifest_nodes_by_position[index] = (
                        manifest_node
                    )
            elif self._capture_model_resolution_evidence:
                (
                    model,
                    loaded_digest,
                    candidate_json_node,
                    manifest_node,
                ) = (
                    self._load_identity_model_same_bytes(identity, position=index)
                )
                if loaded_digest is not None:
                    loaded_artifact_hashes_by_position[index] = loaded_digest
                if candidate_json_node is None:
                    return (), "active_pointer_probability_lineage_candidate_json_invalid"
                candidate_json_nodes_by_position[index] = candidate_json_node
                if manifest_node is None:
                    return (), "active_pointer_probability_lineage_manifest_bytes_invalid"
                self._model_resolution_manifest_nodes_by_position[index] = manifest_node
            else:
                model = self._load_identity_model(identity)
            if model is None:
                return (), "active_pointer_probability_lineage_model_unavailable"
            loaded_models.append((node, model))
        if not loaded_models or str(loaded_models[-1][1].model_id) != str(pointer.get("candidate_id")):
            return (), "active_pointer_probability_lineage_current_mismatch"
        previous_identity = _previous_identity(pointer)
        if previous_identity is not None and str(loaded_models[-2][1].model_id) != str(previous_identity.get("candidate_id")):
            return (), "active_pointer_previous_candidate_mismatch"
        if self._capture_model_resolution_evidence:
            try:
                candidate_json_evidence_nodes = [
                    _null_benchmark_candidate_json_evidence_node()
                ]
                for index, lineage_node in enumerate(lineage[1:], start=1):
                    candidate_json_node = candidate_json_nodes_by_position[index]
                    if (
                        candidate_json_node is None
                        or not _candidate_json_evidence_matches_lineage_node(
                            candidate_json_node,
                            index=index,
                            lineage_node=lineage_node,
                            relative_to=self.pointer_path.parent,
                        )
                    ):
                        return (), "active_pointer_probability_lineage_candidate_json_invalid"
                    candidate_json_evidence_nodes.append(candidate_json_node)
                self._model_resolution_candidate_json_lineage = (
                    _CapabilityCandidateJsonBytesLineageV1(
                        nodes=tuple(candidate_json_evidence_nodes)
                    )
                )
                manifest_evidence_nodes = [
                    _null_benchmark_model_manifest_evidence_node()
                ]
                for index, lineage_node in enumerate(lineage[1:], start=1):
                    manifest_node = self._model_resolution_manifest_nodes_by_position.get(
                        index
                    )
                    if (
                        manifest_node is None
                        or manifest_node.candidate_id
                        != str(lineage_node.get("candidate_id") or "")
                        or manifest_node.canonical_manifest_hash
                        != str(lineage_node.get("candidate_manifest_hash") or "")
                    ):
                        return (), "active_pointer_probability_lineage_manifest_bytes_invalid"
                    manifest_evidence_nodes.append(manifest_node)
                self._model_resolution_manifest_lineage = (
                    _CapabilityModelManifestBytesLineageV1(
                        nodes=tuple(manifest_evidence_nodes)
                    )
                )
                artifact_nodes = [
                    CapabilityLoadedArtifactLineageNodeV1(
                        position=index,
                        kind=str(node.get("kind") or ""),
                        candidate_id=(
                            str(node.get("candidate_id"))
                            if node.get("candidate_id") is not None
                            else None
                        ),
                        model_id=(
                            str(node.get("model_id"))
                            if node.get("model_id") is not None
                            else None
                        ),
                        normalized_candidate_root=(
                            _normalize_candidate_root(
                                node.get("candidate_root"), self.pointer_path.parent
                            )
                            if node.get("kind") == "active_model"
                            else None
                        ),
                        manifest_hash=(
                            str(node.get("candidate_manifest_hash"))
                            if node.get("candidate_manifest_hash") is not None
                            else None
                        ),
                        declared_artifact_hash=(
                            str(node.get("candidate_artifact_hash"))
                            if node.get("candidate_artifact_hash") is not None
                            else None
                        ),
                        freeze_hash=(
                            str(node.get("candidate_freeze_hash"))
                            if node.get("candidate_freeze_hash") is not None
                            else None
                        ),
                        dataset_hash=(
                            str(node.get("dataset_hash"))
                            if node.get("dataset_hash") is not None
                            else None
                        ),
                        loaded_serialized_bytes_sha256=(
                            loaded_artifact_hashes_by_position[index]
                        ),
                    )
                    for index, node in enumerate(lineage)
                ]
                if any(
                    node.kind == "active_model"
                    and node.loaded_serialized_bytes_sha256 is None
                    for node in artifact_nodes
                ):
                    return (), "active_pointer_probability_lineage_same_bytes_missing"
                self._model_resolution_loaded_artifact_lineage = (
                    CapabilityLoadedArtifactLineageEvidenceV1(
                        nodes=tuple(artifact_nodes)
                    )
                )
            except (TypeError, ValueError, OSError, RuntimeError):
                return (), "active_pointer_probability_lineage_identity_invalid"
        self._lineage_models = tuple(loaded_models)
        return tuple(lineage), None

    def _effective_prediction(
        self,
        *,
        feature_values: Sequence[int | None],
        baseline_probability_bp: int,
        baseline_after_cost_probability_bp: int | None,
        node_index: int,
    ) -> RecommendationPrediction:
        if not 0 <= int(baseline_probability_bp) <= 10_000:
            raise ValueError("baseline_probability_bp must be within 0..10000")
        effective_probability: int | None = int(baseline_probability_bp)
        effective_after_cost: int | None = baseline_after_cost_probability_bp
        prediction: RecommendationPrediction | None = None
        for index, (node, model) in enumerate(self._lineage_models):
            if index > node_index:
                break
            raw = model.predict(feature_values)
            transform = RecommendationProbabilityTransform(
                baseline_id=str(node.get("baseline_id") or NULL_BENCHMARK_BASELINE_ID),
                maximum_probability_change_bp=int(node["maximum_probability_change_bp"]),
            )
            effective_probability = transform.apply(raw.calibrated_probability_bp, effective_probability)
            if effective_probability is None:
                raise ValueError("effective active probability is unavailable")
            if effective_after_cost is not None and not 0 <= int(effective_after_cost) <= 10_000:
                raise ValueError("baseline after-cost probability is invalid")
            effective_after_cost = transform.apply(
                raw.after_cost_profit_probability_bp,
                effective_after_cost,
            )
            prediction = replace(
                raw,
                calibrated_probability_bp=effective_probability,
                after_cost_profit_probability_bp=effective_after_cost,
                calibrated_probability_status="active_effective",
                after_cost_profit_probability_status=(
                    "active_effective" if effective_after_cost is not None else "unavailable"
                ),
                source="active_effective",
            )
        if prediction is None:
            raise ValueError("active probability lineage has no model")
        return prediction

    def _load_identity_model(self, identity: Mapping[str, Any]) -> Any | None:
        root_text = str(identity.get("candidate_root") or "").strip()
        if not root_text:
            return None
        root = Path(root_text)
        if not root.is_absolute():
            root = (self.pointer_path.parent / root).resolve()
        expectation = ArtifactCompatibilityExpectation(
            expected_model_family=self.expected_model_family,
            expected_feature_registry_hash=self.feature_registry_hash,
            expected_label_registry_hash=_identity_label_registry_hash(identity),
            expected_feature_schema=self.feature_schema,
            installed_library_versions=_library_versions(),
        )
        loaded = self._loader.load(root, expectation=expectation)
        if loaded.status != "shadow_model_ready" or loaded.model is None:
            return None
        if str(identity.get("candidate_id") or "") != str(getattr(loaded.model, "model_id", "")):
            return None
        if not _pointer_candidate_hashes_match(identity, root, loaded.manifest):
            return None
        return loaded.model

    def _load_identity_model_same_bytes(
        self, identity: Mapping[str, Any], *, position: int
    ) -> tuple[
        Any | None,
        str | None,
        _CapabilityCandidateJsonBytesNodeV1 | None,
        _CapabilityModelManifestBytesNodeV1 | None,
    ]:
        """Capability 專用 ancestor 載入，並保留 manifest/artifact 捕獲證據。"""

        root_text = str(identity.get("candidate_root") or "").strip()
        if not root_text:
            return None, None, None, None
        root = Path(root_text)
        if not root.is_absolute():
            root = (self.pointer_path.parent / root).resolve()
        expectation = ArtifactCompatibilityExpectation(
            expected_model_family=self.expected_model_family,
            expected_feature_registry_hash=self.feature_registry_hash,
            expected_label_registry_hash=_identity_label_registry_hash(identity),
            expected_feature_schema=self.feature_schema,
            installed_library_versions=_library_versions(),
        )
        loaded_result = self._loader.load_same_bytes_with_manifest_v1(
            root, expectation=expectation
        )
        loaded = loaded_result.artifact_result
        if loaded.status != "shadow_model_ready" or loaded.model is None:
            return None, None, None, None
        if (
            loaded_result.captured_manifest_bytes is None
            or loaded_result.manifest_raw_bytes_sha256 is None
            or loaded_result.canonical_manifest_payload_sha256 is None
            or loaded.manifest is None
            or loaded_result.canonical_manifest_payload_sha256
            != loaded.manifest.manifest_hash
        ):
            return None, None, None, None
        if str(identity.get("candidate_id") or "") != str(
            getattr(loaded.model, "model_id", "")
        ):
            return None, None, None, None
        self._model_resolution_captured_manifest_paths_and_bytes.append(
            (root / "manifest.json", loaded_result.captured_manifest_bytes)
        )
        candidate_path = root / "candidate.json"
        try:
            candidate_json_bytes = candidate_path.read_bytes()
            candidate_payload = _read_json_object_bytes(
                candidate_json_bytes, candidate_path
            )
        except (OSError, json.JSONDecodeError, UnicodeDecodeError, ValueError):
            return None, None, None, None
        if not _pointer_candidate_payload_hashes_match(
            identity, root, loaded.manifest, candidate_payload
        ):
            return None, None, None, None
        if candidate_path.read_bytes() != candidate_json_bytes:
            return None, None, None, None
        candidate_json_node = _candidate_json_evidence_node(
            position=position,
            identity=identity,
            relative_to=self.pointer_path.parent,
            raw_bytes_sha256=_sha256_bytes(candidate_json_bytes),
            canonical_payload_sha256=_hash_payload(candidate_payload),
        )
        if candidate_json_node is None:
            return None, None, None, None
        manifest_node = _model_manifest_bytes_evidence_node(
            position=position,
            identity=identity,
            relative_to=self.pointer_path.parent,
            load_result=loaded_result,
        )
        if manifest_node is None:
            return None, None, None, None
        return (
            loaded.model,
            loaded_result.loaded_serialized_bytes_sha256,
            candidate_json_node,
            manifest_node,
        )

    def project(
        self,
        *,
        stock_code: str,
        feature_values: Sequence[int | None] | None,
        rule_probability_bp: int | None,
        after_cost_rule_probability_bp: int | None = None,
        after_cost_rule_baseline_id: str | None = None,
        rule_baseline_id: str = NULL_BENCHMARK_BASELINE_ID,
        ranking_percentile_bp: int | None = None,
        decision_date: str = "",
        data_quality: str = "observed",
        inference_provenance: Mapping[str, Any] | None = None,
        selection_authority: str = "rule_top_n",
        selection_score_kind: str = "rule_total_score",
        selection_percentile_kind: str = "rule_percentile",
        top_n_changed_by_model: bool = False,
        _invocation_capability: _ProjectionInvocationCapabilityProtocol | None = None,
        _verified_source_contract_evidence: VerifiedSourceContractEvidenceV1 | None = None,
    ) -> RecommendationCalibrationProjection:
        current_day = _date_text_or_none(decision_date)
        if current_day is None:
            return RecommendationCalibrationProjection.unavailable(
                stock_code=stock_code,
                warning="decision_date_invalid_fail_closed",
                ranking_percentile_bp=ranking_percentile_bp,
            )
        if _invocation_capability is not None:
            _invocation_capability.assert_projection_use(self, current_day)
            _reject_capability_source_contract_binding(
                inference_provenance, _verified_source_contract_evidence
            )
        elif _verified_source_contract_evidence is not None:
            raise ValueError(
                "prepared source-contract evidence requires an invocation capability"
            )
        elif (
            self._model is None
            or self._loaded_pointer is None
            or self._pointer_stat != self._current_pointer_stat()
            or self._loaded_decision_date != current_day
        ):
            self.reload(decision_date=current_day)
        if self._model is None or self._loaded_pointer is None:
            return RecommendationCalibrationProjection.unavailable(
                stock_code=stock_code,
                warning=self._blocker or "active_pointer_unavailable",
                ranking_percentile_bp=ranking_percentile_bp,
            )
        scenario_for_provenance = self._cost_scenario or _legacy_scenario_from_pointer(
            self._loaded_pointer
        )
        try:
            label_registry_hash, label_contract_id, return_basis = (
                _verified_training_label_contract(
                    self._training_provenance,
                    scenario_for_provenance,
                )
            )
        except RecommendationProvenanceError:
            return RecommendationCalibrationProjection.unavailable(
                stock_code=stock_code,
                warning="active_training_label_contract_unavailable_fail_closed",
                ranking_percentile_bp=ranking_percentile_bp,
            )
        (
            resolved_inference_provenance,
            provenance_compatibility,
            provenance_status,
            provenance_warning,
        ) = _resolve_projection_provenance(
            training_provenance=self._training_provenance,
            inference_provenance=inference_provenance,
            decision_date=current_day,
            stock_code=stock_code,
            expected_registry_hash=self.feature_registry_hash,
            expected_schema=self.feature_schema,
            expected_cost_scenario_hash=scenario_for_provenance.scenario_hash,
            source_contract_evidence=_verified_source_contract_evidence,
        )
        if provenance_warning is not None:
            return RecommendationCalibrationProjection.unavailable(
                stock_code=stock_code,
                warning=provenance_warning,
                ranking_percentile_bp=ranking_percentile_bp,
            )
        if feature_values is None:
            return RecommendationCalibrationProjection.unavailable(
                stock_code=stock_code,
                warning="feature_vector_missing_fail_closed",
                ranking_percentile_bp=ranking_percentile_bp,
            )
        if rule_probability_bp is None or not 0 <= rule_probability_bp <= 10_000:
            return RecommendationCalibrationProjection.unavailable(
                stock_code=stock_code,
                warning="rule_probability_baseline_missing_fail_closed",
                ranking_percentile_bp=ranking_percentile_bp,
            )
        model_after_cost_baseline_id = str(
            getattr(self._model, "after_cost_baseline_id", "") or ""
        ).strip()
        after_cost_baseline_id = str(after_cost_rule_baseline_id or "").strip() or None
        if after_cost_rule_probability_bp is not None:
            if not model_after_cost_baseline_id:
                return RecommendationCalibrationProjection.unavailable(
                    stock_code=stock_code,
                    warning="after_cost_probability_baseline_missing_fail_closed",
                    ranking_percentile_bp=ranking_percentile_bp,
                )
            if after_cost_baseline_id is None:
                after_cost_baseline_id = model_after_cost_baseline_id
            if after_cost_baseline_id != model_after_cost_baseline_id:
                return RecommendationCalibrationProjection.unavailable(
                    stock_code=stock_code,
                    warning="after_cost_probability_baseline_mismatch_fail_closed",
                    ranking_percentile_bp=ranking_percentile_bp,
                )
            if (
                after_cost_baseline_id == AFTER_COST_NULL_BENCHMARK_BASELINE_ID
                and after_cost_rule_probability_bp != AFTER_COST_NULL_BENCHMARK_PROBABILITY_BP
            ):
                return RecommendationCalibrationProjection.unavailable(
                    stock_code=stock_code,
                    warning="after_cost_null_benchmark_probability_invalid_fail_closed",
                    ranking_percentile_bp=ranking_percentile_bp,
                )
        if data_quality.lower() in {"missing", "degraded", "unavailable", "not_checked"}:
            return RecommendationCalibrationProjection.unavailable(
                stock_code=stock_code,
                warning="recommendation_data_quality_not_eligible",
                ranking_percentile_bp=ranking_percentile_bp,
            )
        try:
            raw_prediction: RecommendationPrediction = self._model.predict(feature_values)
            prediction = self._effective_prediction(
                feature_values=feature_values,
                baseline_probability_bp=rule_probability_bp,
                baseline_after_cost_probability_bp=after_cost_rule_probability_bp,
                node_index=len(self._lineage_models) - 1,
            )
        except InvalidCalibrationOutputError:
            return RecommendationCalibrationProjection.unavailable(
                stock_code=stock_code,
                warning="model_probability_output_invalid_fail_closed",
                ranking_percentile_bp=ranking_percentile_bp,
            )
        except (TypeError, ValueError, IndexError):
            return RecommendationCalibrationProjection.unavailable(
                stock_code=stock_code,
                warning="feature_vector_schema_mismatch_fail_closed",
                ranking_percentile_bp=ranking_percentile_bp,
            )
        cap = int(self._loaded_pointer.get("maximum_probability_change_bp", 1000))
        if cap < 0:
            return RecommendationCalibrationProjection.unavailable(
                stock_code=stock_code,
                warning="active_pointer_cap_invalid",
                ranking_percentile_bp=ranking_percentile_bp,
            )
        baseline_kind = (
            "null_benchmark"
            if rule_baseline_id == NULL_BENCHMARK_BASELINE_ID
            else "declared_baseline"
        )
        baseline_id = rule_baseline_id
        baseline_probability = rule_probability_bp
        baseline_prediction = self.champion_baseline(
            feature_values=feature_values,
            decision_date=current_day,
            baseline_probability_bp=rule_probability_bp,
            baseline_after_cost_probability_bp=after_cost_rule_probability_bp,
            _invocation_capability=_invocation_capability,
        )
        if baseline_prediction is not None and baseline_prediction.calibrated_probability_bp is not None:
            baseline_kind = "active_model_previous_champion"
            baseline_id = str(self._probability_lineage[-2].get("candidate_id") or baseline_prediction.model_id)
            baseline_probability = baseline_prediction.calibrated_probability_bp
        transform = RecommendationProbabilityTransform(
            baseline_id=baseline_id,
            maximum_probability_change_bp=cap,
        )
        # ``prediction`` is already the recursively transformed effective
        # output.  Applying a second clamp here would make the consumer and
        # capture paths disagree, so only expose the frozen effective value.
        calibrated = prediction.calibrated_probability_bp
        after_cost = prediction.after_cost_profit_probability_bp
        after_cost_status = prediction.after_cost_profit_probability_status
        after_cost_baseline_kind = _after_cost_baseline_kind(after_cost_baseline_id)
        scenario = scenario_for_provenance
        if scenario.is_estimated:
            projection_cost_basis = (
                "estimated_research_only:banktaiwan-electronic-order-v1; "
                "fees_tax_only=commission+sell_tax; slippage_not_modeled; "
                f"policy_estimate_date={scenario.policy_estimate_date}; "
                f"research_order_amount_twd={scenario.research_order_amount_twd}; "
                f"research_order_quantity_shares={scenario.research_order_quantity_shares}; "
                f"scenario_hash={scenario.scenario_hash}; shadow_only"
            )
            projection_cost_basis_bp = None
            cost_estimate_source = "banktaiwan_policy_estimate_research_only"
        else:
            projection_cost_basis = (
                f"fixed_round_trip_bp={scenario.fixed_round_trip_cost_bp}; observed liquidity"
            )
            projection_cost_basis_bp = scenario.fixed_round_trip_cost_bp
            cost_estimate_source = "legacy_fixed_assumption"
        source_trace = (
            "recommendation_calibration_consumer",
            f"pointer:{self._loaded_pointer.get('pointer_version', '')}",
            f"candidate:{prediction.model_id}",
            f"baseline:{baseline_id}",
            f"baseline_kind:{baseline_kind}",
            f"after_cost_baseline:{after_cost_baseline_id or 'unavailable'}",
            f"after_cost_baseline_kind:{after_cost_baseline_kind}",
            f"after_cost_baseline_probability_bp:{after_cost_rule_probability_bp if after_cost_rule_probability_bp is not None else 'unavailable'}",
            (
                "after_cost_baseline_contract:independent_null_benchmark_v1"
                if after_cost_baseline_id == AFTER_COST_NULL_BENCHMARK_BASELINE_ID
                else "after_cost_baseline_contract:declared_or_unavailable"
            ),
            f"probability_transform:{transform.transform_id}",
            f"probability_lineage:{_hash_payload(self._probability_lineage)}",
            f"dataset:{prediction.dataset_id}",
            f"training_as_of:{prediction.training_as_of}",
            f"label_contract:{label_contract_id}",
            f"label_registry_hash:{label_registry_hash}",
            "benchmark_role:evaluation_only",
            f"cost_scenario:{scenario.scenario_hash}",
            f"cost_policy:{scenario.policy_id or 'legacy'}@{scenario.policy_version or 'v1'}",
            f"cost_estimate_source:{cost_estimate_source}",
            "cost_label_role:fees_tax_only" if scenario.is_estimated else "cost_label_role:legacy_fixed_plus_observed_liquidity",
            f"provenance_status:{provenance_status}",
            f"training_source_hash:{resolved_inference_provenance.get('training_source_hash') or self._training_provenance.get('training_source_hash') or 'unproven'}",
            f"training_pit_hash:{self._training_provenance.get('training_pit_hash') or 'unproven'}",
            f"inference_source_hash:{resolved_inference_provenance.get('inference_source_hash') or 'unproven'}",
            f"inference_pit_hash:{resolved_inference_provenance.get('inference_pit_hash') or 'unproven'}",
            f"feature_snapshot_fingerprint:{resolved_inference_provenance.get('feature_snapshot_fingerprint') or 'unproven'}",
            f"selection_authority:{selection_authority}",
            f"selection_score_kind:{selection_score_kind}",
            f"selection_percentile_kind:{selection_percentile_kind}",
            f"model_ranking_kind:model_return_bp",
        )
        projection_contract_hash = _projection_contract_hash(
            stock_code=stock_code,
            decision_date=current_day,
            candidate_id=str(prediction.model_id),
            prediction=prediction,
            inference_provenance=resolved_inference_provenance,
            training_provenance=self._training_provenance,
            provenance_compatibility=provenance_compatibility,
            selection_authority=selection_authority,
            selection_score_kind=selection_score_kind,
            selection_percentile_kind=selection_percentile_kind,
            top_n_changed_by_model=top_n_changed_by_model,
        )
        return RecommendationCalibrationProjection(
            stock_code=stock_code,
            ranking_score_bp=prediction.ranking_score_bp,
            ranking_percentile_bp=ranking_percentile_bp,
            ranking_method="absolute_return_shadow_candidate",
            calibrated_probability_bp=calibrated,
            calibrated_probability_status=prediction.calibrated_probability_status,
            after_cost_profit_probability_bp=after_cost,
            after_cost_profit_probability_status=after_cost_status,
            confidence_tier="research_candidate",
            evidence_confidence="shadow_candidate",
            sample_size=prediction.sample_size,
            horizon=f"{prediction.horizon_trading_days} trading days",
            cost_basis=projection_cost_basis,
            cost_basis_bp=projection_cost_basis_bp,
            model_version=prediction.model_id,
            dataset_version=prediction.dataset_id,
            source_trace=source_trace,
            probability_transform_id=transform.transform_id,
            probability_baseline_id=baseline_id,
            probability_baseline_kind=baseline_kind,
            probability_baseline_probability_bp=baseline_probability,
            raw_calibrated_probability_bp=raw_prediction.calibrated_probability_bp,
            raw_after_cost_profit_probability_bp=raw_prediction.after_cost_profit_probability_bp,
            warnings=(
                "shadow candidate projection; formal rule and order path unchanged",
                *(
                    ("50pct baseline is an explicit null benchmark",)
                    if baseline_kind == "null_benchmark"
                    else ()
                ),
            ),
            status="active_candidate",
            **_projection_scenario_fields(scenario, cost_estimate_source),
            training_provenance=dict(self._training_provenance),
            inference_provenance=dict(resolved_inference_provenance),
            provenance_compatibility=dict(provenance_compatibility),
            provenance_status=provenance_status,
            projection_contract_hash=projection_contract_hash,
            selection_authority=selection_authority,
            selection_score_kind=selection_score_kind,
            selection_percentile_kind=selection_percentile_kind,
            model_ranking_kind="model_return_bp",
            label_registry_hash=label_registry_hash,
            label_contract_id=label_contract_id,
            return_basis=return_basis,
        )

    def project_many(
        self,
        *,
        feature_values_by_symbol: Mapping[str, Sequence[int | None]],
        rule_probability_by_symbol: Mapping[str, int],
        decision_date: str,
        after_cost_rule_probability_by_symbol: Mapping[str, int] | None = None,
        after_cost_rule_baseline_id_by_symbol: Mapping[str, str] | None = None,
        rule_baseline_id: str = NULL_BENCHMARK_BASELINE_ID,
        ranking_percentile_by_symbol: Mapping[str, int] | None = None,
        data_quality: str = "observed",
        inference_provenance: Mapping[str, Any] | None = None,
        selection_authority: str = "rule_top_n",
        selection_score_kind: str = "rule_total_score",
        selection_percentile_kind: str = "rule_percentile",
        top_n_changed_by_model: bool = False,
        _invocation_capability: _ProjectionInvocationCapabilityProtocol | None = None,
        _verified_source_contract_evidence: VerifiedSourceContractEvidenceV1 | None = None,
    ) -> dict[str, RecommendationCalibrationProjection]:
        if _invocation_capability is not None:
            _invocation_capability.assert_projection_use(self, decision_date)
            _reject_capability_source_contract_binding(
                inference_provenance, _verified_source_contract_evidence
            )
        elif _verified_source_contract_evidence is not None:
            raise ValueError(
                "prepared source-contract evidence requires an invocation capability"
            )
        percentiles = ranking_percentile_by_symbol or {}
        after_cost_baselines = after_cost_rule_probability_by_symbol or {}
        after_cost_baseline_ids = after_cost_rule_baseline_id_by_symbol or {}
        symbols = tuple(sorted(set(feature_values_by_symbol) | set(rule_probability_by_symbol)))
        return {
            symbol: self.project(
                stock_code=symbol,
                feature_values=feature_values_by_symbol.get(symbol),
                rule_probability_bp=rule_probability_by_symbol.get(symbol),
                after_cost_rule_probability_bp=after_cost_baselines.get(symbol),
                after_cost_rule_baseline_id=after_cost_baseline_ids.get(symbol),
                rule_baseline_id=rule_baseline_id,
                ranking_percentile_bp=percentiles.get(symbol),
                decision_date=decision_date,
                data_quality=data_quality,
                inference_provenance=inference_provenance,
                selection_authority=selection_authority,
                selection_score_kind=selection_score_kind,
                selection_percentile_kind=selection_percentile_kind,
                top_n_changed_by_model=top_n_changed_by_model,
                _invocation_capability=_invocation_capability,
                _verified_source_contract_evidence=_verified_source_contract_evidence,
            )
            for symbol in symbols
        }


class _InvocationProjectionCapability:
    """不可複製、一次性持有 fresh model/lineage 的私有投影能力。"""

    __slots__ = (
        "__weakref__",
        "__owner",
        "__resolved_consumer",
        "__invocation_scope_id",
        "__decision_date",
        "__identity_hash",
        "__model_resolution_evidence",
        "__loaded_artifact_lineage",
        "__pointer_bytes_evidence",
        "__candidate_json_bytes_lineage",
        "__model_manifest_bytes_lineage",
        "__lock",
        "__used",
        "__active_thread",
    )

    def __init__(
        self,
        *,
        owner: RecommendationCalibrationConsumer,
        resolved_consumer: RecommendationCalibrationConsumer,
        invocation_scope_id: str,
        decision_date: str,
        identity_hash: str,
        model_resolution_evidence: RecommendationModelResolutionEvidenceV1,
        loaded_artifact_lineage: CapabilityLoadedArtifactLineageEvidenceV1,
        pointer_bytes_evidence: _CapabilityPointerBytesEvidenceV1,
        candidate_json_bytes_lineage: _CapabilityCandidateJsonBytesLineageV1,
        model_manifest_bytes_lineage: _CapabilityModelManifestBytesLineageV1,
    ) -> None:
        self.__owner = owner
        self.__resolved_consumer = resolved_consumer
        self.__invocation_scope_id = invocation_scope_id
        self.__decision_date = decision_date
        self.__identity_hash = identity_hash
        self.__model_resolution_evidence = model_resolution_evidence
        self.__loaded_artifact_lineage = loaded_artifact_lineage
        self.__pointer_bytes_evidence = pointer_bytes_evidence
        self.__candidate_json_bytes_lineage = candidate_json_bytes_lineage
        self.__model_manifest_bytes_lineage = model_manifest_bytes_lineage
        self.__lock = Lock()
        self.__used = False
        self.__active_thread: int | None = None

    def __repr__(self) -> str:
        return "<invocation-local calibration projection capability>"

    @property
    def model_resolution_evidence(self) -> RecommendationModelResolutionEvidenceV1:
        """Expose immutable evidence from the same fresh resolve, without I/O."""

        return self.__model_resolution_evidence

    @property
    def loaded_model_runtime_class(self) -> tuple[str, str]:
        """Return the actual loaded class identity without resolving or reading paths."""

        model = self.__resolved_consumer._model
        if model is None:
            raise RuntimeError("invocation capability no longer owns a loaded model")
        return type(model).__module__, type(model).__qualname__

    @property
    def loaded_artifact_lineage(self) -> CapabilityLoadedArtifactLineageEvidenceV1:
        """Expose ordered same-buffer artifact digests for this capability only."""

        return self.__loaded_artifact_lineage

    @property
    def pointer_bytes_evidence(self) -> _CapabilityPointerBytesEvidenceV1:
        """Expose raw and canonical hashes for the exact pointer bytes parsed."""

        return self.__pointer_bytes_evidence

    @property
    def candidate_json_bytes_lineage(
        self,
    ) -> _CapabilityCandidateJsonBytesLineageV1:
        """Expose ordered raw/canonical hashes for captured candidate JSON parses."""

        return self.__candidate_json_bytes_lineage

    @property
    def model_manifest_bytes_lineage(
        self,
    ) -> _CapabilityModelManifestBytesLineageV1:
        """提供此 invocation 讀取的 active 與 ancestor manifest 有序證據。"""

        return self.__model_manifest_bytes_lineage

    def __copy__(self) -> Any:
        raise TypeError("invocation projection capability cannot be copied")

    def __deepcopy__(self, _memo: dict[int, Any]) -> Any:
        raise TypeError("invocation projection capability cannot be copied")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> Any:
        raise TypeError("invocation projection capability cannot be serialized")

    def project_many(
        self,
        *,
        owner: RecommendationCalibrationConsumer,
        invocation_scope_id: str,
        expected_identity: Mapping[str, Any],
        feature_values_by_symbol: Mapping[str, Sequence[int | None]],
        rule_probability_by_symbol: Mapping[str, int],
        decision_date: str,
        after_cost_rule_probability_by_symbol: Mapping[str, int] | None = None,
        after_cost_rule_baseline_id_by_symbol: Mapping[str, str] | None = None,
        rule_baseline_id: str = NULL_BENCHMARK_BASELINE_ID,
        ranking_percentile_by_symbol: Mapping[str, int] | None = None,
        data_quality: str = "observed",
        inference_provenance: Mapping[str, Any] | None = None,
        source_contract_evidence: VerifiedSourceContractEvidenceV1 | None = None,
        selection_authority: str = "rule_top_n",
        selection_score_kind: str = "rule_total_score",
        selection_percentile_kind: str = "rule_percentile",
        top_n_changed_by_model: bool = False,
    ) -> dict[str, RecommendationCalibrationProjection]:
        current_day = _date_text_or_none(decision_date)
        try:
            supplied_identity_hash = _hash_payload(expected_identity)
        except Exception as exc:
            raise ValueError("invocation capability identity is invalid") from exc
        with self.__lock:
            if self.__used:
                raise RuntimeError("invocation projection capability is already consumed")
            if owner is not self.__owner:
                raise ValueError("invocation capability belongs to a different consumer")
            if (
                invocation_scope_id != self.__invocation_scope_id
                or current_day != self.__decision_date
                or supplied_identity_hash != self.__identity_hash
            ):
                raise ValueError("invocation capability scope or identity mismatch")
            _reject_capability_source_contract_binding(
                inference_provenance, source_contract_evidence
            )
            self.__used = True
            self.__active_thread = get_ident()

        try:
            return self.__resolved_consumer.project_many(
                feature_values_by_symbol=feature_values_by_symbol,
                rule_probability_by_symbol=rule_probability_by_symbol,
                decision_date=self.__decision_date,
                after_cost_rule_probability_by_symbol=after_cost_rule_probability_by_symbol,
                after_cost_rule_baseline_id_by_symbol=after_cost_rule_baseline_id_by_symbol,
                rule_baseline_id=rule_baseline_id,
                ranking_percentile_by_symbol=ranking_percentile_by_symbol,
                data_quality=data_quality,
                inference_provenance=inference_provenance,
                _verified_source_contract_evidence=source_contract_evidence,
                selection_authority=selection_authority,
                selection_score_kind=selection_score_kind,
                selection_percentile_kind=selection_percentile_kind,
                top_n_changed_by_model=top_n_changed_by_model,
                _invocation_capability=self,
            )
        finally:
            with self.__lock:
                self.__active_thread = None

    def project_prepared_runtime_input_v1(
        self, runtime_input: Any
    ) -> dict[str, RecommendationCalibrationProjection]:
        """以同一不可變 runtime input 呼叫此 capability 的一次性舊投影 seam。"""

        from app_module.recommendation.prepared_runtime_input import (
            LegacyShadowIdentityV1,
            LoadedModelRuntimeClassV1,
            PreparedMLRuntimeInputV1,
        )
        from app_module.recommendation.prepared_runtime_projector import (
            prepare_ml_projection_arguments_v1,
        )

        if type(runtime_input) is not PreparedMLRuntimeInputV1:
            raise TypeError("runtime_input 必須是 exact PreparedMLRuntimeInputV1")
        if runtime_input.invocation_capability is not self:
            raise ValueError("runtime input capability identity mismatch")
        identity = runtime_input.identity
        if type(identity) is not LegacyShadowIdentityV1:
            raise TypeError(
                "此 model-resolution capability 僅接受 legacy shadow identity"
            )
        if identity.model_resolution != self.__model_resolution_evidence:
            raise ValueError("runtime model-resolution facts 不符同次 capability")
        runtime_class = self.loaded_model_runtime_class
        if identity.loaded_model_runtime_class != LoadedModelRuntimeClassV1(
            module=runtime_class[0], qualified_name=runtime_class[1]
        ):
            raise ValueError("runtime loaded model class 不符同次 capability")

        arguments = prepare_ml_projection_arguments_v1(runtime_input)
        return self.project_many(
            owner=self.__owner,
            invocation_scope_id=arguments.invocation_scope_id,
            expected_identity=arguments.expected_identity,
            feature_values_by_symbol=arguments.feature_values_by_symbol,
            rule_probability_by_symbol=arguments.rule_probability_by_symbol,
            decision_date=arguments.decision_date,
            after_cost_rule_probability_by_symbol=(
                arguments.after_cost_rule_probability_by_symbol
            ),
            after_cost_rule_baseline_id_by_symbol=(
                arguments.after_cost_rule_baseline_id_by_symbol
            ),
            rule_baseline_id=arguments.rule_baseline_id,
            ranking_percentile_by_symbol=arguments.ranking_percentile_by_symbol,
            data_quality=arguments.data_quality,
            inference_provenance=arguments.inference_provenance,
            source_contract_evidence=arguments.source_contract_evidence,
            selection_authority=arguments.selection_authority,
            selection_score_kind=arguments.selection_score_kind,
            selection_percentile_kind=arguments.selection_percentile_kind,
            top_n_changed_by_model=arguments.top_n_changed_by_model,
        )

    def _resolved_consumer_for_isolation(self) -> RecommendationCalibrationConsumer:
        """Return the private resolved graph only to the capability owner."""

        return self.__resolved_consumer

    def assert_projection_use(
        self,
        consumer: RecommendationCalibrationConsumer,
        decision_date: str,
    ) -> None:
        if (
            consumer is not self.__resolved_consumer
            or _date_text_or_none(decision_date) != self.__decision_date
            or self.__active_thread != get_ident()
        ):
            raise ValueError("invocation capability is not active for this projection")


class _NoModelProjectionCapability:
    """不可複製、一次性持有 baseline rule-only/no-model 結果的私有能力。"""

    __slots__ = (
        "__weakref__",
        "__owner",
        "__resolved_consumer",
        "__invocation_scope_id",
        "__decision_date",
        "__identity_hash",
        "__identity",
        "__lock",
        "__used",
        "__active_thread",
    )

    def __init__(
        self,
        *,
        owner: RecommendationCalibrationConsumer,
        resolved_consumer: RecommendationCalibrationConsumer,
        invocation_scope_id: str,
        decision_date: str,
        identity_hash: str,
        identity: Any,
        _seal: object,
    ) -> None:
        from app_module.recommendation.prepared_runtime_input import (
            NoModelShadowIdentityV1,
        )

        if _seal is not _NO_MODEL_PROJECTION_CAPABILITY_SEAL:
            raise TypeError("no-model projection capability constructor is sealed")
        if type(identity) is not NoModelShadowIdentityV1:
            raise TypeError("identity 必須是 exact NoModelShadowIdentityV1")
        if resolved_consumer._model is not None:
            raise ValueError("no-model capability 不可持有 loaded model")
        if (
            identity.decision_date != decision_date
            or identity.reload_status != "rule_only"
            or identity.blocker != resolved_consumer._blocker
        ):
            raise ValueError("no-model identity 與 baseline reload 不一致")
        self.__owner = owner
        self.__resolved_consumer = resolved_consumer
        self.__invocation_scope_id = invocation_scope_id
        self.__decision_date = decision_date
        self.__identity_hash = identity_hash
        self.__identity = identity
        self.__lock = Lock()
        self.__used = False
        self.__active_thread: int | None = None

    def __repr__(self) -> str:
        return "<invocation-local no-model projection capability>"

    @property
    def no_model_identity(self) -> Any:
        """回傳由此 fresh baseline reload 封存的 immutable terminal identity。"""

        return self.__identity

    def __copy__(self) -> Any:
        raise TypeError("no-model projection capability cannot be copied")

    def __deepcopy__(self, _memo: dict[int, Any]) -> Any:
        raise TypeError("no-model projection capability cannot be copied")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> Any:
        raise TypeError("no-model projection capability cannot be serialized")

    def _resolved_consumer_for_isolation(
        self,
    ) -> RecommendationCalibrationConsumer:
        return self.__resolved_consumer

    def assert_projection_use(
        self,
        consumer: RecommendationCalibrationConsumer,
        decision_date: str,
    ) -> None:
        if (
            consumer is not self.__resolved_consumer
            or _date_text_or_none(decision_date) != self.__decision_date
            or self.__active_thread != get_ident()
            or consumer._model is not None
            or consumer._blocker != self.__identity.blocker
        ):
            raise ValueError("no-model capability is not active for this projection")

    def project_many(
        self,
        *,
        owner: RecommendationCalibrationConsumer,
        invocation_scope_id: str,
        expected_identity: Mapping[str, Any],
        feature_values_by_symbol: Mapping[str, Sequence[int | None]],
        rule_probability_by_symbol: Mapping[str, int],
        decision_date: str,
        after_cost_rule_probability_by_symbol: Mapping[str, int] | None = None,
        after_cost_rule_baseline_id_by_symbol: Mapping[str, str] | None = None,
        rule_baseline_id: str = NULL_BENCHMARK_BASELINE_ID,
        ranking_percentile_by_symbol: Mapping[str, int] | None = None,
        data_quality: str = "observed",
        inference_provenance: Mapping[str, Any] | None = None,
        source_contract_evidence: VerifiedSourceContractEvidenceV1 | None = None,
        selection_authority: str = "rule_top_n",
        selection_score_kind: str = "rule_total_score",
        selection_percentile_kind: str = "rule_percentile",
        top_n_changed_by_model: bool = False,
    ) -> dict[str, RecommendationCalibrationProjection]:
        current_day = _date_text_or_none(decision_date)
        try:
            supplied_identity_hash = _hash_payload(expected_identity)
        except Exception as exc:
            raise ValueError("no-model capability identity is invalid") from exc
        with self.__lock:
            if self.__used:
                raise RuntimeError("no-model projection capability is already consumed")
            if owner is not self.__owner:
                raise ValueError("no-model capability belongs to a different consumer")
            if (
                invocation_scope_id != self.__invocation_scope_id
                or current_day != self.__decision_date
                or supplied_identity_hash != self.__identity_hash
            ):
                raise ValueError("no-model capability scope or identity mismatch")
            _reject_capability_source_contract_binding(
                inference_provenance,
                source_contract_evidence,
            )
            self.__used = True
            self.__active_thread = get_ident()
        try:
            return self.__resolved_consumer.project_many(
                feature_values_by_symbol=feature_values_by_symbol,
                rule_probability_by_symbol=rule_probability_by_symbol,
                decision_date=self.__decision_date,
                after_cost_rule_probability_by_symbol=(
                    after_cost_rule_probability_by_symbol
                ),
                after_cost_rule_baseline_id_by_symbol=(
                    after_cost_rule_baseline_id_by_symbol
                ),
                rule_baseline_id=rule_baseline_id,
                ranking_percentile_by_symbol=ranking_percentile_by_symbol,
                data_quality=data_quality,
                inference_provenance=inference_provenance,
                _verified_source_contract_evidence=source_contract_evidence,
                selection_authority=selection_authority,
                selection_score_kind=selection_score_kind,
                selection_percentile_kind=selection_percentile_kind,
                top_n_changed_by_model=top_n_changed_by_model,
                _invocation_capability=self,
            )
        finally:
            with self.__lock:
                self.__active_thread = None

    def project_prepared_runtime_input_v1(
        self,
        runtime_input: Any,
    ) -> dict[str, RecommendationCalibrationProjection]:
        """只接受與此 no-model resolve 完全相同的 typed runtime input。"""

        from app_module.recommendation.prepared_runtime_input import (
            NoModelShadowIdentityV1,
            PreparedMLRuntimeInputV1,
        )
        from app_module.recommendation.prepared_runtime_projector import (
            prepare_ml_projection_arguments_v1,
        )

        if type(runtime_input) is not PreparedMLRuntimeInputV1:
            raise TypeError("runtime_input 必須是 exact PreparedMLRuntimeInputV1")
        if runtime_input.invocation_capability is not self:
            raise ValueError("runtime input capability identity mismatch")
        if type(runtime_input.identity) is not NoModelShadowIdentityV1:
            raise TypeError("no-model capability 僅接受 no-model shadow identity")
        if runtime_input.identity != self.__identity:
            raise ValueError("runtime no-model identity 不符同次 baseline reload")

        arguments = prepare_ml_projection_arguments_v1(runtime_input)
        return self.project_many(
            owner=self.__owner,
            invocation_scope_id=arguments.invocation_scope_id,
            expected_identity=arguments.expected_identity,
            feature_values_by_symbol=arguments.feature_values_by_symbol,
            rule_probability_by_symbol=arguments.rule_probability_by_symbol,
            decision_date=arguments.decision_date,
            after_cost_rule_probability_by_symbol=(
                arguments.after_cost_rule_probability_by_symbol
            ),
            after_cost_rule_baseline_id_by_symbol=(
                arguments.after_cost_rule_baseline_id_by_symbol
            ),
            rule_baseline_id=arguments.rule_baseline_id,
            ranking_percentile_by_symbol=arguments.ranking_percentile_by_symbol,
            data_quality=arguments.data_quality,
            inference_provenance=arguments.inference_provenance,
            source_contract_evidence=arguments.source_contract_evidence,
            selection_authority=arguments.selection_authority,
            selection_score_kind=arguments.selection_score_kind,
            selection_percentile_kind=arguments.selection_percentile_kind,
            top_n_changed_by_model=arguments.top_n_changed_by_model,
        )


def _reject_capability_source_contract_binding(
    inference_provenance: Mapping[str, Any] | None,
    evidence: VerifiedSourceContractEvidenceV1 | None = None,
) -> None:
    """Require same-call typed bytes for an opt-in source-contract binding."""

    binding = (
        inference_provenance.get("source_contract_binding")
        if inference_provenance is not None
        else None
    )
    if binding is None:
        if evidence is not None:
            raise ValueError("prepared source-contract evidence has no provenance binding")
        return
    if type(evidence) is not VerifiedSourceContractEvidenceV1:
        raise ValueError(
            "filesystem-bound source contracts require same-invocation verified bytes"
        )
    try:
        canonical_binding = json.dumps(
            dict(binding),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("source-contract binding is not canonicalizable") from exc
    if canonical_binding != evidence.binding_payload_json:
        raise ValueError("source-contract binding does not match prepared evidence")
    raw_source_database = (
        inference_provenance.get("source_database")
        if inference_provenance is not None
        else None
    )
    if raw_source_database and raw_source_database != evidence.source_database_original:
        raise ValueError("source database input does not match prepared evidence")


def _loaded_model_state_roots(
    consumer: RecommendationCalibrationConsumer,
) -> tuple[Any, ...]:
    """Return the complete known mutable model and lineage state roots."""

    return (
        consumer._model,
        consumer._baseline_model,
        consumer._lineage_models,
        consumer._probability_lineage,
        consumer._loaded_pointer,
        consumer._baseline_identity,
        consumer._training_provenance,
    )


@dataclass(frozen=True)
class _LoadedModelGraphSnapshot:
    schema_version: str
    mutable_object_ids: frozenset[int]
    arrays: tuple[np.ndarray, ...]


class _UnsupportedKnownModelGraph(ValueError):
    """The loaded graph is outside the bounded production allowlist."""


def _current_model_graph_runtime_profile() -> tuple[Any, ...]:
    """Return the exact runtime profile reviewed for this optional API."""

    return (
        sys.platform,
        tuple(sys.version_info[:3]),
        np.__version__,
        sklearn.__version__,
        scipy.__version__,
        joblib.__version__,
    )


def _loaded_model_graph_snapshot(
    consumer: RecommendationCalibrationConsumer,
) -> _LoadedModelGraphSnapshot:
    """Collect an exact-type, bounded snapshot of known mutable model state.

    The allowlist is deliberately version-sensitive.  New estimator classes,
    fitted fields, callables, object arrays, cycles, or oversized graphs make
    this optional capability unavailable instead of silently widening it.
    """

    mutable_ids: set[int] = set()
    arrays: list[np.ndarray] = []
    visited: set[int] = set()
    active: set[int] = set()
    node_count = 0
    total_array_bytes = 0

    def reject(message: str) -> NoReturn:
        raise _UnsupportedKnownModelGraph(message)

    def attrs_for(
        value: Any,
        *,
        allowed: frozenset[str],
        required: frozenset[str],
        exact: bool = False,
    ) -> dict[str, Any]:
        try:
            attrs = vars(value)
        except TypeError as exc:
            raise _UnsupportedKnownModelGraph("known node has no supported instance state") from exc
        if type(attrs) is not dict:
            reject("known node state is not a plain dict")
        keys = frozenset(attrs)
        if not required.issubset(keys) or not keys.issubset(allowed):
            reject("known node fields do not match the versioned allowlist")
        if exact and keys != allowed:
            reject("known node is missing a required allowlisted field")
        return attrs

    def dataclass_attrs(value: Any, expected_type: type[Any]) -> dict[str, Any]:
        if type(value) is not expected_type:
            reject("model or calibrator class is not the exact supported type")
        expected_fields = frozenset(field.name for field in dataclass_fields(expected_type))
        attrs = attrs_for(
            value,
            allowed=expected_fields,
            required=expected_fields,
            exact=True,
        )
        return attrs

    def pipeline_attrs(value: Any, *, final_type: type[Any]) -> dict[str, Any]:
        if type(value) is not Pipeline:
            reject("model component is not the exact sklearn Pipeline type")
        attrs = attrs_for(
            value,
            allowed=frozenset({"memory", "steps", "transform_input", "verbose"}),
            required=frozenset({"memory", "steps", "transform_input", "verbose"}),
            exact=True,
        )
        steps = attrs["steps"]
        if type(steps) is not list or len(steps) != 3:
            reject("Pipeline layout is outside the fitted recommendation profile")
        step_names: list[Any] = []
        for step in steps:
            if type(step) is not tuple or len(step) != 2:
                reject("Pipeline step is outside the fitted recommendation profile")
            step_names.append(step[0])
        if (
            tuple(step_names) != ("imputer", "scaler", "model")
            or type(steps[0][1]) is not SimpleImputer
            or type(steps[1][1]) is not StandardScaler
            or type(steps[2][1]) is not final_type
            or attrs["memory"] is not None
            or attrs["transform_input"] is not None
            or type(attrs["verbose"]) is not bool
        ):
            reject("Pipeline layout is outside the fitted recommendation profile")
        return attrs

    def known_children(value: Any) -> tuple[Any, ...] | None:
        value_type = type(value)
        if value_type is RunnableRecommendationCalibrationModel:
            attrs = dataclass_attrs(value, RunnableRecommendationCalibrationModel)
            if (
                type(attrs["return_model"]) is not Pipeline
                or type(attrs["upside_model"]) is not Pipeline
                or type(attrs["upside_calibrator"])
                is not FittedShadowProbabilityCalibrator
                or (
                    attrs["after_cost_model"] is not None
                    and type(attrs["after_cost_model"]) is not Pipeline
                )
                or (
                    attrs["after_cost_calibrator"] is not None
                    and type(attrs["after_cost_calibrator"])
                    is not FittedShadowProbabilityCalibrator
                )
            ):
                reject("recommendation model component graph has an unknown shape")
            pipeline_attrs(attrs["return_model"], final_type=Ridge)
            pipeline_attrs(attrs["upside_model"], final_type=LogisticRegression)
            if attrs["after_cost_model"] is not None:
                pipeline_attrs(attrs["after_cost_model"], final_type=LogisticRegression)
            return tuple(attrs.values())

        if value_type is FittedShadowProbabilityCalibrator:
            attrs = dataclass_attrs(value, FittedShadowProbabilityCalibrator)
            if type(attrs["estimator"]) is not IsotonicRegression:
                reject("calibrator estimator is outside the supported type")
            return tuple(attrs.values())

        if value_type is Pipeline:
            attrs = attrs_for(
                value,
                allowed=frozenset({"memory", "steps", "transform_input", "verbose"}),
                required=frozenset({"memory", "steps", "transform_input", "verbose"}),
                exact=True,
            )
            return tuple(attrs.values())

        estimator_fields: dict[type[Any], tuple[frozenset[str], frozenset[str]]] = {
            SimpleImputer: (
                frozenset(
                    {
                        "missing_values",
                        "add_indicator",
                        "keep_empty_features",
                        "strategy",
                        "fill_value",
                        "copy",
                        "n_features_in_",
                        "_fit_dtype",
                        "_fill_dtype",
                        "indicator_",
                        "statistics_",
                    }
                ),
                frozenset({"indicator_", "statistics_", "n_features_in_"}),
            ),
            StandardScaler: (
                frozenset(
                    {
                        "with_mean",
                        "with_std",
                        "copy",
                        "n_features_in_",
                        "n_samples_seen_",
                        "mean_",
                        "var_",
                        "scale_",
                    }
                ),
                frozenset(
                    {
                        "n_features_in_",
                        "n_samples_seen_",
                        "mean_",
                        "var_",
                        "scale_",
                    }
                ),
            ),
            Ridge: (
                frozenset(
                    {
                        "alpha",
                        "fit_intercept",
                        "copy_X",
                        "max_iter",
                        "tol",
                        "solver",
                        "positive",
                        "random_state",
                        "n_features_in_",
                        "coef_",
                        "n_iter_",
                        "solver_",
                        "intercept_",
                    }
                ),
                frozenset({"n_features_in_", "coef_", "intercept_"}),
            ),
            LogisticRegression: (
                frozenset(
                    {
                        "penalty",
                        "C",
                        "l1_ratio",
                        "dual",
                        "tol",
                        "fit_intercept",
                        "intercept_scaling",
                        "class_weight",
                        "random_state",
                        "solver",
                        "max_iter",
                        "verbose",
                        "warm_start",
                        "n_jobs",
                        "n_features_in_",
                        "classes_",
                        "n_iter_",
                        "coef_",
                        "intercept_",
                    }
                ),
                frozenset(
                    {
                        "n_features_in_",
                        "classes_",
                        "n_iter_",
                        "coef_",
                        "intercept_",
                    }
                ),
            ),
        }
        field_profile = estimator_fields.get(value_type)
        if field_profile is not None:
            attrs = attrs_for(
                value,
                allowed=field_profile[0],
                required=field_profile[1],
            )
            if value_type is SimpleImputer and attrs.get("indicator_") is not None:
                reject("SimpleImputer indicator graph is outside the supported profile")
            return tuple(attrs.values())

        if value_type is IsotonicRegression:
            attrs = attrs_for(
                value,
                allowed=frozenset(
                    {
                        "y_min",
                        "y_max",
                        "increasing",
                        "out_of_bounds",
                        "increasing_",
                        "X_min_",
                        "X_max_",
                        "X_thresholds_",
                        "y_thresholds_",
                        "f_",
                    }
                ),
                required=frozenset(
                    {"X_min_", "X_max_", "X_thresholds_", "y_thresholds_", "f_"}
                ),
            )
            if type(attrs["f_"]) is not _ScipyInterp1d:
                reject("isotonic interpolation function is outside the supported type")
            return tuple(attrs.values())

        if value_type is _ScipyInterp1d:
            attrs = attrs_for(
                value,
                allowed=frozenset(
                    {
                        "bounds_error",
                        "copy",
                        "axis",
                        "y",
                        "_y",
                        "x",
                        "_kind",
                        "_call",
                        "_fill_value_below",
                        "_fill_value_above",
                        "_extrapolate",
                        "_fill_value_orig",
                    }
                ),
                required=frozenset({"x", "y", "_y", "_call"}),
            )
            call = attrs["_call"]
            if (
                type(call) is not FunctionType
                or not any(
                    call is candidate for candidate in _VERIFIED_SCIPY_INTERP1D_CALLS
                )
                or call.__closure__ is not None
                or call.__defaults__ not in (None, ())
                or call.__kwdefaults__ is not None
                or bool(call.__dict__)
            ):
                reject("interpolation callable is outside the immutable allowlist")
            return tuple(value for name, value in attrs.items() if name != "_call")

        return None

    def walk(value: Any, *, depth: int) -> None:
        nonlocal node_count, total_array_bytes
        node_count += 1
        if node_count > _MAX_MODEL_GRAPH_NODES or depth > _MAX_MODEL_GRAPH_DEPTH:
            reject("model graph exceeded its node or depth budget")

        if value is None or type(value) in (bool, int, float, str, bytes, Decimal):
            return
        if isinstance(value, np.dtype):
            return
        if isinstance(value, np.generic):
            if value.dtype.kind not in "biufcUS":
                reject("numpy scalar dtype is outside the immutable allowlist")
            return

        value_type = type(value)
        known_object = False
        if value_type not in (np.ndarray, list, dict, tuple):
            children = known_children(value)
            if children is None:
                reject("model graph contains an unknown object type")
            known_object = True
        elif value_type is np.ndarray:
            if (
                value.dtype.kind not in "biufc"
                or value.dtype.hasobject
                or value.dtype.fields is not None
                or value.ndim > 2
                or value.size > _MAX_MODEL_GRAPH_ARRAY_ELEMENTS
            ):
                reject("numpy array dtype or shape is outside the supported profile")
            total_array_bytes += value.nbytes
            if (
                len(arrays) >= _MAX_MODEL_GRAPH_ARRAYS
                or total_array_bytes > _MAX_MODEL_GRAPH_ARRAY_BYTES
            ):
                reject("model graph exceeded its array budget")
            children = ()
            arrays.append(value)
        elif value_type is list:
            children = tuple(value)
        elif value_type is tuple:
            children = value
        else:
            children = tuple(item for pair in value.items() for item in pair)

        identity = id(value)
        if identity in active:
            reject("model graph contains a cycle")
        if identity in visited:
            return
        visited.add(identity)
        active.add(identity)
        if value_type in (np.ndarray, list, dict) or known_object:
            mutable_ids.add(identity)
        try:
            for child in children:
                walk(child, depth=depth + 1)
            if value_type is np.ndarray and value.base is not None:
                if type(value.base) is not np.ndarray:
                    if type(value.base) is not bytes:
                        reject("numpy array has an unsupported backing owner")
                else:
                    walk(value.base, depth=depth + 1)
        finally:
            active.remove(identity)

    for root in _loaded_model_state_roots(consumer):
        walk(root, depth=0)
    return _LoadedModelGraphSnapshot(
        schema_version=_MODEL_GRAPH_SCHEMA_VERSION,
        mutable_object_ids=frozenset(mutable_ids),
        arrays=tuple(arrays),
    )


def _loaded_model_state_aliases(
    source: RecommendationCalibrationConsumer,
    fresh: RecommendationCalibrationConsumer,
) -> bool:
    """Fail closed on unsupported graphs or shared mutable model/lineage state."""

    try:
        source_graph = _loaded_model_graph_snapshot(source)
        fresh_graph = _loaded_model_graph_snapshot(fresh)
    except Exception:
        return True
    if source_graph.schema_version != fresh_graph.schema_version:
        return True
    if source_graph.mutable_object_ids & fresh_graph.mutable_object_ids:
        return True
    try:
        for source_array in source_graph.arrays:
            for fresh_array in fresh_graph.arrays:
                if np.shares_memory(source_array, fresh_array, max_work=10_000):
                    return True
    except Exception:
        return True
    return False


def _legacy_training_provenance(reason: str) -> dict[str, Any]:
    return {
        "schema_version": "recommendation-inference-provenance.v1",
        "status": "legacy_unproven",
        "reason": reason,
        "training_source_hash": None,
        "training_pit_hash": None,
        "feature_registry_hash": None,
        "feature_schema_hash": None,
        "feature_transform_contract": None,
        "dataset_id": None,
        "dataset_hash": None,
        "decision_date": None,
        "training_as_of": None,
        "training_semantics": None,
        "decision_time_eligible": None,
        "research_only": None,
        "cost_scenario_hash": None,
    }


def _legacy_inference_provenance(decision_date: str, stock_code: str) -> dict[str, Any]:
    return {
        "schema_version": "recommendation-inference-provenance.v1",
        "status": "legacy_unproven",
        "reason": "inference_provenance_not_supplied",
        "decision_date": decision_date,
        "symbols": [str(stock_code)],
        "inference_source_hash": None,
        "inference_pit_hash": None,
        "feature_snapshot_fingerprint": None,
    }


def _verified_training_label_contract(
    training_provenance: Mapping[str, Any],
    scenario: RecommendationCostScenario,
) -> tuple[str, str, str]:
    """Resolve label identity only from the verified active training record."""

    if str(training_provenance.get("status") or "") != "verified":
        raise RecommendationProvenanceError(
            "active training provenance is not verified for projection labels"
        )
    expected_registry_hash = recommendation_label_registry_hash(
        cost_scenario=scenario if scenario.is_estimated else None
    )
    registry_hash = str(training_provenance.get("label_registry_hash") or "").strip()
    if not registry_hash or registry_hash != expected_registry_hash:
        raise RecommendationProvenanceError(
            "active training label registry hash is missing or mismatched"
        )
    label_contract_id = str(training_provenance.get("label_contract_id") or "").strip()
    expected_contract_id = recommendation_label_contract_id(
        scenario if scenario.is_estimated else None
    )
    if label_contract_id != expected_contract_id:
        raise RecommendationProvenanceError(
            "active training label contract is missing or mismatched"
        )
    return_basis = str(training_provenance.get("return_basis") or "").strip()
    if return_basis != RECOMMENDATION_RETURN_BASIS:
        raise RecommendationProvenanceError(
            "active training return basis is missing or mismatched"
        )
    return registry_hash, label_contract_id, return_basis


def _load_candidate_training_provenance(
    *,
    candidate_root: Path,
    candidate_payload: Mapping[str, Any],
    decision_date: str,
    require_personal_source_time: bool = False,
    data_root: str | Path | None = None,
    personal_use_policy: Any | None = None,
) -> tuple[Mapping[str, Any], str | None]:
    hash_declared = "training_lineage_manifest_hash" in candidate_payload
    path_declared = "training_lineage_manifest_path" in candidate_payload
    lineage_hash = str(candidate_payload.get("training_lineage_manifest_hash") or "").strip()
    lineage_path_text = str(candidate_payload.get("training_lineage_manifest_path") or "").strip()
    if not hash_declared and not path_declared:
        return _legacy_training_provenance("training_lineage_not_declared"), None
    if not lineage_hash or not lineage_path_text:
        return _legacy_training_provenance("training_lineage_declaration_incomplete"), (
            "candidate_training_lineage_declaration_incomplete"
        )
    lineage_path = Path(lineage_path_text)
    if not lineage_path.is_absolute():
        lineage_path = (candidate_root / lineage_path).resolve()
    if lineage_path.is_symlink() or not lineage_path.is_file():
        return _legacy_training_provenance("training_lineage_manifest_missing"), (
            "candidate_training_lineage_manifest_missing"
        )
    try:
        lineage = read_recommendation_training_lineage(
            lineage_path,
            expected_manifest_hash=lineage_hash,
            expected_dataset_hash=(
                str(candidate_payload.get("dataset_hash"))
                if candidate_payload.get("dataset_hash") not in (None, "")
                else None
            ),
            expected_candidate_id=(
                str(candidate_payload.get("candidate_id"))
                if candidate_payload.get("candidate_id") not in (None, "")
                else None
            ),
        )
        lineage_decision = _date_text_or_none(str(lineage.payload.get("decision_date") or ""))
        if lineage_decision is None or lineage_decision > decision_date:
            raise RecommendationTrainingLineageError(
                "training lineage decision date is after inference decision"
            )
        source_time_evidence: dict[str, Any] = {}
        if require_personal_source_time:
            from app_module.recommendation.personal_candidate_inventory import (
                learning_root_for_personal_candidate,
                verify_personal_training_source_time_proof,
                _saved_v2_source_binding_matches,
            )

            trust = getattr(personal_use_policy, "source_time_trust", None)
            if (
                personal_use_policy is None
                or type(personal_use_policy) is not RecommendationPersonalUsePolicyV2
                or personal_use_policy.version != 2
                or personal_use_policy.to_dict().get("schema_version")
                != _PERSONAL_USE_POLICY_SCHEMA_V2
                or trust is None
            ):
                source_time_error = verify_personal_training_source_time_proof(
                    lineage_payload=lineage.payload,
                    learning_root=learning_root_for_personal_candidate(candidate_root),
                    data_root=data_root,
                )
                if source_time_error is not None:
                    return _legacy_training_provenance(
                        "personal_historical_source_proof_unavailable"
                    ), "candidate_training_source_time_unverified_fail_closed"
                return _legacy_training_provenance(
                    "personal_source_time_binding_missing"
                ), "personal_source_time_binding_missing_or_invalid"
            source_time_error = verify_personal_training_source_time_proof(
                lineage_payload=lineage.payload,
                learning_root=learning_root_for_personal_candidate(candidate_root),
                data_root=data_root,
                source_database_path=trust.source_database_path,
                evidence_out=source_time_evidence,
            )
            if source_time_error is not None:
                return _legacy_training_provenance(
                    "personal_historical_source_proof_unavailable"
                ), "candidate_training_source_time_unverified_fail_closed"
            candidate_reference = getattr(personal_use_policy, "candidate", None)
            if (
                type(candidate_reference) is not PersonalCalibrationCandidateV1
                or not _saved_v2_source_binding_matches(
                    personal_use_policy,
                    candidate_ref=candidate_reference,
                    proof_evidence=source_time_evidence,
                )
            ):
                return _legacy_training_provenance(
                    "personal_source_time_binding_mismatch"
                ), "personal_source_time_binding_mismatch"
        provenance = build_training_provenance(
            lineage_payload=lineage.payload,
            manifest_hash=lineage.manifest_hash,
            manifest_path=str(lineage_path),
            candidate_payload=candidate_payload,
        )
        for key in ("feature_registry_hash", "feature_schema_hash"):
            candidate_value = candidate_payload.get(key)
            lineage_value = provenance.get(key)
            if candidate_value not in (None, "") and lineage_value not in (None, ""):
                if candidate_value != lineage_value:
                    raise RecommendationProvenanceError(
                        f"candidate training {key} does not match lineage"
                    )
        if require_personal_source_time and personal_use_policy is not None:
            trust = personal_use_policy.source_time_trust
            enriched_provenance = dict(provenance)
            enriched_provenance.update(
                {
                    "source_time_basis": "user_declared_source_time",
                    "source_time_confirmed_at": trust.confirmed_at,
                    "source_time_source_database_path": trust.source_database_path,
                    "source_time_slice_sha256": trust.source_slice_sha256,
                    "source_time_research_only": True,
                    "official_historical_pit_verified": False,
                }
            )
            provenance = enriched_provenance
        return provenance, None
    except (
        OSError,
        UnicodeError,
        TypeError,
        ValueError,
        RecommendationTrainingLineageError,
        RecommendationProvenanceError,
    ) as exc:
        return _legacy_training_provenance(type(exc).__name__), (
            "candidate_training_lineage_invalid_fail_closed"
        )


def _resolve_projection_provenance(
    *,
    training_provenance: Mapping[str, Any],
    inference_provenance: Mapping[str, Any] | None,
    decision_date: str,
    stock_code: str,
    expected_registry_hash: str,
    expected_schema: Any,
    expected_cost_scenario_hash: str,
    source_contract_evidence: VerifiedSourceContractEvidenceV1 | None = None,
) -> tuple[dict[str, Any], dict[str, Any], str, str | None]:
    if inference_provenance is None:
        legacy_inference = _legacy_inference_provenance(decision_date, stock_code)
        compatibility = validate_provenance_compatibility(
            training_provenance,
            legacy_inference,
            expected_cost_scenario_hash=None,
        )
        compatibility["status"] = "legacy_unproven"
        compatibility["reason"] = "inference_provenance_not_supplied"
        return legacy_inference, compatibility, "legacy_unproven", None
    try:
        verify_inference_provenance(
            inference_provenance,
            expected_decision_date=decision_date,
            expected_registry_hash=expected_registry_hash,
            expected_schema=expected_schema,
            expected_probability_transform_id=PROBABILITY_TRANSFORM_ID,
            source_contract_evidence=source_contract_evidence,
        )
        symbols = {
            str(item).strip()
            for item in inference_provenance.get("symbols", ())
            if str(item).strip()
        }
        if stock_code not in symbols:
            raise RecommendationProvenanceError(
                "inference provenance does not cover projected stock"
            )
        compatibility = validate_provenance_compatibility(
            training_provenance,
            inference_provenance,
            expected_cost_scenario_hash=expected_cost_scenario_hash,
            expected_probability_transform_id=PROBABILITY_TRANSFORM_ID,
        )
        if compatibility.get("status") == "blocked":
            return (
                dict(inference_provenance),
                compatibility,
                "unavailable",
                "provenance_compatibility_mismatch_fail_closed",
            )
        return (
            dict(inference_provenance),
            compatibility,
            str(compatibility.get("status") or "legacy_unproven"),
            None,
        )
    except (TypeError, ValueError, RecommendationProvenanceError):
        return (
            dict(inference_provenance),
            {
                "schema_version": "recommendation-calibration-provenance-compatibility.v1",
                "status": "blocked",
                "reason": "inference_provenance_invalid",
            },
            "unavailable",
            "inference_provenance_invalid_fail_closed",
        )


def _projection_contract_hash(
    *,
    stock_code: str,
    decision_date: str,
    candidate_id: str,
    prediction: RecommendationPrediction,
    inference_provenance: Mapping[str, Any],
    training_provenance: Mapping[str, Any],
    provenance_compatibility: Mapping[str, Any],
    selection_authority: str,
    selection_score_kind: str,
    selection_percentile_kind: str,
    top_n_changed_by_model: bool,
) -> str:
    return _hash_payload(
        {
            "schema_version": "recommendation-calibration-projection.v1",
            "stock_code": stock_code,
            "decision_date": decision_date,
            "candidate_id": candidate_id,
            "ranking_score_bp": prediction.ranking_score_bp,
            "calibrated_probability_bp": prediction.calibrated_probability_bp,
            "after_cost_profit_probability_bp": prediction.after_cost_profit_probability_bp,
            "dataset_id": prediction.dataset_id,
            "training_as_of": prediction.training_as_of,
            "horizon_trading_days": prediction.horizon_trading_days,
            "training_provenance": dict(training_provenance),
            "inference_provenance": dict(inference_provenance),
            "provenance_compatibility": dict(provenance_compatibility),
            "selection_authority": selection_authority,
            "selection_score_kind": selection_score_kind,
            "selection_percentile_kind": selection_percentile_kind,
            "model_ranking_kind": "model_return_bp",
            "top_n_changed_by_model": bool(top_n_changed_by_model),
        }
    )


def _clamp_to_baseline(value: int | None, baseline: int, cap: int) -> int | None:
    if value is None:
        return None
    return max(0, min(10_000, max(baseline - cap, min(baseline + cap, int(value)))))


def _after_cost_baseline_kind(baseline_id: str | None) -> str:
    if not baseline_id:
        return "unavailable"
    if baseline_id == AFTER_COST_NULL_BENCHMARK_BASELINE_ID:
        return "independent_null_benchmark"
    return "declared_baseline"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def _read_json_object_bytes(raw_bytes: bytes, source_path: Path) -> dict[str, Any]:
    payload = json.loads(raw_bytes.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {source_path}")
    return payload


def _candidate_json_path_matches_bytes(candidate_root: Path, expected_bytes: bytes) -> bool:
    try:
        return (candidate_root / "candidate.json").read_bytes() == expected_bytes
    except OSError:
        return False


def _legacy_scenario_from_pointer(pointer: Mapping[str, Any] | None) -> RecommendationCostScenario:
    if pointer is None:
        return cost_scenario_from_metadata({}, fixed_round_trip_cost_bp=50)
    return cost_scenario_from_metadata(
        pointer,
        fixed_round_trip_cost_bp=_optional_int(pointer.get("fixed_round_trip_cost_bp")),
    )


def _identity_label_registry_hash(identity: Mapping[str, Any]) -> str:
    declared = str(identity.get("label_registry_hash") or "")
    if declared:
        return declared
    scenario = cost_scenario_from_metadata(
        identity,
        fixed_round_trip_cost_bp=_optional_int(identity.get("fixed_round_trip_cost_bp")),
    )
    return recommendation_label_registry_hash(
        cost_scenario=scenario if scenario.is_estimated else None
    )


def _scenario_identity_fields(
    scenario: RecommendationCostScenario | None,
    pointer: Mapping[str, Any] | None,
) -> dict[str, Any]:
    resolved = scenario or _legacy_scenario_from_pointer(pointer)
    payload = resolved.metadata()
    return {
        "fixed_round_trip_cost_bp": resolved.fixed_round_trip_cost_bp,
        "label_registry_hash": (
            pointer.get("label_registry_hash")
            if pointer is not None and pointer.get("label_registry_hash")
            else recommendation_label_registry_hash(
                cost_scenario=resolved if resolved.is_estimated else None
            )
        ),
        "cost_contract_hash": recommendation_cost_contract_hash(
            resolved.fixed_round_trip_cost_bp,
            cost_scenario=resolved if resolved.is_estimated else None,
        ),
        "cost_scenario_id": resolved.scenario_id,
        "cost_scenario_version": resolved.scenario_version,
        "cost_scenario_hash": resolved.scenario_hash,
        "cost_basis": resolved.cost_basis,
        "cost_policy_id": resolved.policy_id,
        "cost_policy_version": resolved.policy_version,
        "policy_estimate_date": resolved.policy_estimate_date,
        "research_order_amount_twd": (
            str(resolved.research_order_amount_twd)
            if resolved.research_order_amount_twd is not None
            else None
        ),
        "research_order_quantity_shares": resolved.research_order_quantity_shares,
        "lot_type": resolved.lot_type,
        "instrument_type": resolved.instrument_type,
        "cost_scenario": payload,
    }


def _projection_scenario_fields(
    scenario: RecommendationCostScenario,
    cost_estimate_source: str,
) -> dict[str, Any]:
    return {
        "cost_policy_id": scenario.policy_id,
        "cost_policy_version": scenario.policy_version,
        "cost_scenario_id": scenario.scenario_id,
        "cost_scenario_version": scenario.scenario_version,
        "cost_scenario_hash": scenario.scenario_hash,
        "policy_estimate_date": scenario.policy_estimate_date,
        "research_order_amount_twd": (
            str(scenario.research_order_amount_twd)
            if scenario.research_order_amount_twd is not None
            else None
        ),
        "research_order_quantity_shares": scenario.research_order_quantity_shares,
        "lot_type": scenario.lot_type,
        "instrument_type": scenario.instrument_type,
        "cost_estimate_source": cost_estimate_source,
    }


def _null_lineage_node(cap: int) -> dict[str, Any]:
    return {
        "kind": "null_benchmark",
        "baseline_id": NULL_BENCHMARK_BASELINE_ID,
        "baseline_kind": "null_benchmark",
        "candidate_id": None,
        "model_id": None,
        "transform_id": PROBABILITY_TRANSFORM_ID,
        "maximum_probability_change_bp": cap,
        "effective_prediction": "identity_from_explicit_baseline",
    }


def _model_lineage_node(
    identity: Mapping[str, Any],
    *,
    baseline_id: str,
    baseline_kind: str,
    cap: int,
) -> dict[str, Any]:
    candidate_id = identity.get("candidate_id") or identity.get("model_id")
    node = {
        "kind": "active_model",
        "baseline_id": baseline_id,
        "baseline_kind": baseline_kind,
        "candidate_id": candidate_id,
        "model_id": candidate_id,
        "candidate_root": identity.get("candidate_root"),
        "candidate_manifest_hash": identity.get("candidate_manifest_hash"),
        "candidate_artifact_hash": identity.get("candidate_artifact_hash"),
        "candidate_freeze_hash": identity.get("candidate_freeze_hash"),
        "dataset_hash": identity.get("dataset_hash"),
        "transform_id": PROBABILITY_TRANSFORM_ID,
        "maximum_probability_change_bp": cap,
        "effective_prediction": "recursive_capped_model_probability",
    }
    for key in (
        "label_registry_hash", "cost_contract_hash", "fixed_round_trip_cost_bp",
        "cost_scenario_id", "cost_scenario_version", "cost_scenario_hash",
        "cost_basis", "cost_policy_id", "cost_policy_version",
        "policy_estimate_date", "research_order_amount_twd",
        "research_order_quantity_shares", "lot_type", "instrument_type",
        "cost_scenario",
    ):
        if key in identity:
            node[key] = identity[key]
    return node


def _pointer_identity(pointer: Mapping[str, Any]) -> dict[str, Any]:
    identity = {
        "candidate_id": pointer.get("candidate_id"),
        "candidate_root": pointer.get("candidate_root"),
        "candidate_manifest_hash": pointer.get("candidate_manifest_hash"),
        "candidate_artifact_hash": pointer.get("candidate_artifact_hash"),
        "candidate_freeze_hash": pointer.get("candidate_freeze_hash"),
        "dataset_hash": pointer.get("dataset_hash"),
    }
    for key in (
        "label_registry_hash", "cost_contract_hash", "fixed_round_trip_cost_bp",
        "cost_scenario_id", "cost_scenario_version", "cost_scenario_hash",
        "cost_basis", "cost_policy_id", "cost_policy_version",
        "policy_estimate_date", "research_order_amount_twd",
        "research_order_quantity_shares", "lot_type", "instrument_type",
        "cost_scenario",
    ):
        if key in pointer:
            identity[key] = pointer[key]
    return identity


def _personal_candidate_reference_matches(
    candidate_ref: Any,
    candidate_payload: Mapping[str, Any],
) -> bool:
    """比對個人設定 pin 與候選 JSON 中的不可變 artifact identity。"""

    return all(
        getattr(candidate_ref, ref_field, None) == candidate_payload.get(payload_field)
        for ref_field, payload_field in (
            ("candidate_id", "candidate_id"),
            ("candidate_manifest_hash", "manifest_hash"),
            ("candidate_artifact_hash", "artifact_hash"),
            ("candidate_freeze_hash", "candidate_freeze_hash"),
            ("dataset_hash", "dataset_hash"),
        )
    )


def _personal_candidate_pointer(
    policy: Any,
    candidate_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """將已 pin 的個人選擇映射為共用硬驗證器使用的唯讀欄位。"""

    candidate_ref = policy.candidate
    if candidate_ref is None:
        raise ValueError("personal candidate reference is missing")
    effective_date = _date_text_or_none(
        str(candidate_payload.get("candidate_frozen_at") or "")
    ) or _date_text_or_none(str(candidate_payload.get("training_as_of") or ""))
    if effective_date is None:
        raise ValueError("personal candidate effective date is missing")
    pointer = dict(candidate_payload)
    policy_schema = policy.to_dict().get("schema_version")
    if type(policy_schema) is not str or not policy_schema:
        raise ValueError("personal policy schema is missing")
    pointer.update(
        {
            "schema_version": policy_schema,
            "status": "active",
            "pointer_version": policy.revision,
            "candidate_root": candidate_ref.candidate_root,
            "candidate_manifest_hash": candidate_ref.candidate_manifest_hash,
            "candidate_artifact_hash": candidate_ref.candidate_artifact_hash,
            "candidate_freeze_hash": candidate_ref.candidate_freeze_hash,
            "dataset_hash": candidate_ref.dataset_hash,
            "effective_date": effective_date,
            "maximum_probability_change_bp": PERSONAL_PROBABILITY_CHANGE_CAP_BP,
            "personal_use_policy_sha256": policy.policy_sha256,
            "personal_use_policy_revision": policy.revision,
            "personal_use_scope_id": policy.scope_id,
            "personal_use_mode": policy.mode,
            "personal_candidate_json_sha256": candidate_ref.candidate_json_sha256,
        }
    )
    return pointer


def _personal_v2_source_trust_precheck(policy: Any) -> bool:
    """在讀候選 metadata 前檢查已確認的 V2 綁定形狀。"""

    if (
        type(policy) is not RecommendationPersonalUsePolicyV2
        or getattr(policy, "version", None) != 2
    ):
        return False
    try:
        if policy.to_dict().get("schema_version") != _PERSONAL_USE_POLICY_SCHEMA_V2:
            return False
    except (AttributeError, TypeError, ValueError):
        return False
    trust = getattr(policy, "source_time_trust", None)
    candidate = getattr(policy, "candidate", None)
    if trust is None or candidate is None:
        return False
    try:
        source_path = Path(trust.source_database_path)
        file_identity = trust.file_identity
        replay_scope = trust.replay_scope
        trust_candidate = trust.candidate
        return (
            source_path.is_absolute()
            and str(source_path) == trust.source_database_path
            and trust.schema_version == "personal-user-declared-source-time-trust.v1"
            and trust.basis == "user_declared_source_time"
            and trust.confirmed_at == policy.confirmed_at
            and type(file_identity.device) is int
            and file_identity.device >= 0
            and type(file_identity.inode) is int
            and file_identity.inode > 0
            and _is_prefixed_sha256(trust.source_slice_sha256)
            and type(replay_scope.sample_count) is int
            and replay_scope.sample_count > 0
            and bool(replay_scope.dataset_ids)
            and bool(replay_scope.decision_dates)
            and bool(replay_scope.symbols)
            and trust_candidate.to_dict() == candidate.to_dict()
            and trust.research_only is True
            and trust.official_historical_pit_verified is False
        )
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def _normalize_candidate_root(value: Any, relative_to: Path) -> str | None:
    if type(value) is not str or not value.strip():
        return None
    try:
        root = Path(value)
        if not root.is_absolute():
            root = relative_to / root
        resolved = root.resolve(strict=True)
    except (OSError, RuntimeError, TypeError, ValueError):
        return None
    return os.path.normcase(os.path.normpath(str(resolved)))


def _capability_active_lineage_node_matches_pointer(
    node: Mapping[str, Any], pointer: Mapping[str, Any], relative_to: Path
) -> bool:
    if node.get("kind") != "active_model":
        return False
    identity = _pointer_identity(pointer)
    active_candidate_id = identity.get("candidate_id")
    if (
        type(active_candidate_id) is not str
        or not active_candidate_id
        or node.get("candidate_id") != active_candidate_id
        or node.get("model_id") != active_candidate_id
    ):
        return False
    if _normalize_candidate_root(
        node.get("candidate_root"), relative_to
    ) != _normalize_candidate_root(identity.get("candidate_root"), relative_to):
        return False
    for node_key, pointer_key in (
        ("candidate_manifest_hash", "candidate_manifest_hash"),
        ("candidate_artifact_hash", "candidate_artifact_hash"),
        ("candidate_freeze_hash", "candidate_freeze_hash"),
        ("dataset_hash", "dataset_hash"),
    ):
        node_value = node.get(node_key)
        pointer_value = identity.get(pointer_key)
        if (
            type(node_value) is not str
            or not _is_prefixed_sha256(node_value)
            or node_value != pointer_value
        ):
            return False
    return True


def _null_benchmark_candidate_json_evidence_node(
) -> _CapabilityCandidateJsonBytesNodeV1:
    return _CapabilityCandidateJsonBytesNodeV1(
        position=0,
        kind="null_benchmark",
        candidate_id=None,
        model_id=None,
        normalized_candidate_root=None,
        manifest_hash=None,
        artifact_hash=None,
        freeze_hash=None,
        dataset_hash=None,
        raw_bytes_sha256=None,
        canonical_payload_sha256=None,
    )


def _null_benchmark_model_manifest_evidence_node(
) -> _CapabilityModelManifestBytesNodeV1:
    return _CapabilityModelManifestBytesNodeV1(
        position=0,
        kind="null_benchmark",
        candidate_id=None,
        model_id=None,
        normalized_candidate_root=None,
        raw_bytes_sha256=None,
        canonical_manifest_hash=None,
    )


def _model_manifest_bytes_evidence_node(
    *,
    position: int,
    identity: Mapping[str, Any],
    relative_to: Path,
    load_result: SameBytesShadowModelArtifactWithManifestLoadResultV1,
) -> _CapabilityModelManifestBytesNodeV1 | None:
    manifest = load_result.manifest
    candidate_id = identity.get("candidate_id")
    model_id = identity.get("model_id")
    normalized_root = _normalize_candidate_root(
        identity.get("candidate_root"), relative_to
    )
    manifest_hash = identity.get("candidate_manifest_hash")
    raw_bytes_hash = load_result.manifest_raw_bytes_sha256
    canonical_manifest_hash = load_result.canonical_manifest_payload_sha256
    if (
        type(position) is not int
        or position <= 0
        or type(candidate_id) is not str
        or not candidate_id
        or type(model_id) is not str
        or model_id != candidate_id
        or normalized_root is None
        or manifest is None
        or manifest.model_id != model_id
        or manifest.manifest_hash != manifest_hash
        or canonical_manifest_hash != manifest.manifest_hash
        or not _is_prefixed_sha256(raw_bytes_hash)
        or not _is_prefixed_sha256(canonical_manifest_hash)
    ):
        return None
    return _CapabilityModelManifestBytesNodeV1(
        position=position,
        kind="active_model",
        candidate_id=candidate_id,
        model_id=model_id,
        normalized_candidate_root=normalized_root,
        raw_bytes_sha256=raw_bytes_hash,
        canonical_manifest_hash=canonical_manifest_hash,
    )


def _candidate_json_evidence_node(
    *,
    position: int,
    identity: Mapping[str, Any],
    relative_to: Path,
    raw_bytes_sha256: str,
    canonical_payload_sha256: str,
) -> _CapabilityCandidateJsonBytesNodeV1 | None:
    candidate_id = identity.get("candidate_id")
    model_id = identity.get("model_id")
    normalized_root = _normalize_candidate_root(
        identity.get("candidate_root"), relative_to
    )
    manifest_hash = identity.get("candidate_manifest_hash")
    artifact_hash = identity.get("candidate_artifact_hash")
    freeze_hash = identity.get("candidate_freeze_hash")
    dataset_hash = identity.get("dataset_hash")
    if (
        type(position) is not int
        or position <= 0
        or type(candidate_id) is not str
        or not candidate_id
        or type(model_id) is not str
        or model_id != candidate_id
        or normalized_root is None
        or any(
            not _is_prefixed_sha256(value)
            for value in (manifest_hash, artifact_hash, freeze_hash, dataset_hash)
        )
        or not _is_prefixed_sha256(raw_bytes_sha256)
        or not _is_prefixed_sha256(canonical_payload_sha256)
    ):
        return None
    return _CapabilityCandidateJsonBytesNodeV1(
        position=position,
        kind="active_model",
        candidate_id=candidate_id,
        model_id=model_id,
        normalized_candidate_root=normalized_root,
        manifest_hash=str(manifest_hash),
        artifact_hash=str(artifact_hash),
        freeze_hash=str(freeze_hash),
        dataset_hash=str(dataset_hash),
        raw_bytes_sha256=raw_bytes_sha256,
        canonical_payload_sha256=canonical_payload_sha256,
    )


def _candidate_json_evidence_matches_lineage_node(
    evidence: _CapabilityCandidateJsonBytesNodeV1,
    *,
    index: int,
    lineage_node: Mapping[str, Any],
    relative_to: Path,
) -> bool:
    return (
        evidence.position == index
        and evidence.kind == lineage_node.get("kind") == "active_model"
        and evidence.candidate_id == lineage_node.get("candidate_id")
        and evidence.model_id == lineage_node.get("model_id")
        and evidence.normalized_candidate_root
        == _normalize_candidate_root(lineage_node.get("candidate_root"), relative_to)
        and evidence.manifest_hash == lineage_node.get("candidate_manifest_hash")
        and evidence.artifact_hash == lineage_node.get("candidate_artifact_hash")
        and evidence.freeze_hash == lineage_node.get("candidate_freeze_hash")
        and evidence.dataset_hash == lineage_node.get("dataset_hash")
    )


def _is_prefixed_sha256(value: Any) -> bool:
    return (
        type(value) is str
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _library_versions() -> dict[str, str]:
    import joblib
    import sklearn

    return {
        "joblib": str(joblib.__version__),
        "numpy": str(np.__version__),
        "scikit-learn": str(sklearn.__version__),
    }


def _path_stat(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return stat.st_size, stat.st_mtime_ns


def _date_text_or_none(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        return None


def build_default_recommendation_calibration_consumer(config: Any) -> RecommendationCalibrationConsumer | None:
    """Build the read-only consumer used by the normal application composition root."""

    data_root = getattr(config, "data_root", None)
    if data_root is None:
        return None
    paths = resolve_recommendation_learning_paths(data_root=data_root)
    return RecommendationCalibrationConsumer(
        pointer_path=paths.active_pointer_path,
        feature_schema=CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_schema,
        feature_registry_hash=CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
        data_root=data_root,
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _sha256_bytes(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _hash_payload(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _pointer_candidate_hashes_match(pointer: Mapping[str, Any], candidate_root: Path, manifest: Any) -> bool:
    candidate_path = candidate_root / "candidate.json"
    try:
        payload = json.loads(candidate_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(payload, Mapping):
        return False
    return _pointer_candidate_payload_hashes_match(
        pointer, candidate_root, manifest, payload
    )


def _pointer_candidate_payload_hashes_match(
    pointer: Mapping[str, Any],
    candidate_root: Path,
    manifest: Any,
    payload: Mapping[str, Any],
) -> bool:
    if payload.get("candidate_id") != pointer.get("candidate_id"):
        return False
    if payload.get("manifest_hash") != pointer.get("candidate_manifest_hash"):
        return False
    if payload.get("artifact_hash") != pointer.get("candidate_artifact_hash"):
        return False
    if payload.get("dataset_hash") != pointer.get("dataset_hash"):
        return False
    if payload.get("candidate_freeze_hash") != pointer.get("candidate_freeze_hash"):
        return False
    try:
        pointer_scenario = cost_scenario_from_metadata(
            pointer,
            fixed_round_trip_cost_bp=_optional_int(pointer.get("fixed_round_trip_cost_bp")),
        )
        candidate_scenario = cost_scenario_from_metadata(
            payload,
            fixed_round_trip_cost_bp=_optional_int(payload.get("fixed_round_trip_cost_bp")),
        )
    except (TypeError, ValueError, RecommendationCostScenarioError):
        return False
    if pointer_scenario.scenario_hash != candidate_scenario.scenario_hash:
        return False
    expected_label_hash = recommendation_label_registry_hash(
        cost_scenario=pointer_scenario if pointer_scenario.is_estimated else None
    )
    if payload.get("label_registry_hash") not in (None, expected_label_hash):
        return False
    if pointer.get("label_registry_hash") not in (None, expected_label_hash):
        return False
    if manifest.manifest_hash != pointer.get("candidate_manifest_hash"):
        return False
    artifact_path = candidate_root / manifest.artifact_filename
    if _sha256_file(artifact_path) != pointer.get("candidate_artifact_hash"):
        return False
    evaluation_payload = payload.get("evaluation")
    evaluation = evaluation_payload if isinstance(evaluation_payload, Mapping) else {}
    expected_freeze = candidate_freeze_hash(
        candidate_id=str(payload.get("candidate_id")),
        dataset_hash=str(payload.get("dataset_hash")),
        manifest_hash=str(payload.get("manifest_hash")),
        artifact_hash=str(payload.get("artifact_hash")),
        evaluation=evaluation,
    )
    return expected_freeze == payload.get("candidate_freeze_hash")


def _previous_identity(pointer: Mapping[str, Any]) -> dict[str, Any] | None:
    required = (
        "previous_candidate_id",
        "previous_candidate_root",
        "previous_candidate_manifest_hash",
        "previous_candidate_artifact_hash",
        "previous_candidate_freeze_hash",
    )
    if not all(pointer.get(key) for key in required):
        return None
    identity = {
        "candidate_id": pointer.get("previous_candidate_id"),
        "candidate_root": pointer.get("previous_candidate_root"),
        "candidate_manifest_hash": pointer.get("previous_candidate_manifest_hash"),
        "candidate_artifact_hash": pointer.get("previous_candidate_artifact_hash"),
        "candidate_freeze_hash": pointer.get("previous_candidate_freeze_hash"),
        "dataset_hash": pointer.get("previous_dataset_hash"),
    }
    prefix_map = {
        "label_registry_hash": "previous_label_registry_hash",
        "cost_contract_hash": "previous_cost_contract_hash",
        "fixed_round_trip_cost_bp": "previous_fixed_round_trip_cost_bp",
        "cost_scenario_id": "previous_cost_scenario_id",
        "cost_scenario_version": "previous_cost_scenario_version",
        "cost_scenario_hash": "previous_cost_scenario_hash",
        "cost_basis": "previous_cost_basis",
        "cost_policy_id": "previous_cost_policy_id",
        "cost_policy_version": "previous_cost_policy_version",
        "policy_estimate_date": "previous_policy_estimate_date",
        "research_order_amount_twd": "previous_research_order_amount_twd",
        "research_order_quantity_shares": "previous_research_order_quantity_shares",
        "lot_type": "previous_lot_type",
        "instrument_type": "previous_instrument_type",
        "cost_scenario": "previous_cost_scenario",
    }
    for target, source in prefix_map.items():
        if source in pointer:
            identity[target] = pointer[source]
    return identity


def _pointer_receipt_error(pointer: Mapping[str, Any]) -> str | None:
    path_text = str(pointer.get("decision_receipt_path") or "")
    receipt_hash = str(pointer.get("decision_receipt_hash") or "")
    if not path_text or not receipt_hash:
        return "active_pointer_receipt_missing"
    path = Path(path_text).resolve()
    if not path.is_file() or _sha256_file(path) != receipt_hash:
        return "active_pointer_receipt_mismatch"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "active_pointer_receipt_invalid"
    if not isinstance(payload, Mapping) or payload.get("decision_id") != pointer.get("decision_id"):
        return "active_pointer_receipt_decision_mismatch"
    if payload.get("pointer_content_hash") is None:
        return "active_pointer_content_hash_missing"
    base = {key: value for key, value in pointer.items() if key not in {"decision_receipt_path", "decision_receipt_hash"}}
    digest = hashlib.sha256(
        json.dumps(base, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if f"sha256:{digest}" != payload.get("pointer_content_hash"):
        return "active_pointer_content_hash_mismatch"
    return None
