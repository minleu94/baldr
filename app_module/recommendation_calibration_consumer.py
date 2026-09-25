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
from pathlib import Path
from threading import Lock, get_ident
from types import FunctionType
from typing import Any, Mapping, NoReturn, Sequence, SupportsIndex
from weakref import WeakValueDictionary

import joblib
import numpy as np
from scipy.interpolate import interp1d as _ScipyInterp1d
from sklearn.impute import SimpleImputer
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app_module.recommendation_learning_paths import (
    resolve_recommendation_learning_paths,
)
from ml_module.model_artifact_loader import ArtifactCompatibilityExpectation, SafeShadowModelArtifactLoader
from ml_module.model_artifact_manifest import FeatureSchema
from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY
from ml_module.recommendation_calibration_training import (
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


_MODEL_GRAPH_SCHEMA_VERSION = "r026-known-model-graph.v1"
_MAX_MODEL_GRAPH_DEPTH = 24
_MAX_MODEL_GRAPH_NODES = 4096
_MAX_MODEL_GRAPH_ARRAYS = 512
_MAX_MODEL_GRAPH_ARRAY_BYTES = 64 * 1024 * 1024
_MAX_MODEL_GRAPH_ARRAY_ELEMENTS = 1_000_000
_MAX_LIVE_INVOCATION_CAPABILITIES = 16
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
    ) -> None:
        self.pointer_path = Path(pointer_path).resolve()
        self.feature_schema = feature_schema
        self.feature_registry_hash = feature_registry_hash
        self.expected_model_family = expected_model_family
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
            str, _InvocationProjectionCapability
        ] = WeakValueDictionary()

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
        with self._invocation_capability_lock:
            if invocation_scope_id in self._invocation_capabilities:
                return None
        try:
            expected_hash = _hash_payload(expected_identity)
            pointer_bytes_before = self.pointer_path.read_bytes()
            parsed_pointer_before = json.loads(pointer_bytes_before.decode("utf-8"))
            if not isinstance(parsed_pointer_before, Mapping):
                return None

            resolved = RecommendationCalibrationConsumer(
                pointer_path=self.pointer_path,
                feature_schema=self.feature_schema,
                feature_registry_hash=self.feature_registry_hash,
                data_root=self._loader._data_root,
                expected_model_family=self.expected_model_family,
            )
            # Preserve only the loader implementation/configuration.  The newly
            # deserialized model and every lineage model remain private to this
            # invocation-owned consumer.
            resolved._loader = SafeShadowModelArtifactLoader(
                data_root=self._loader._data_root,
                deserializer=joblib.load,
            )
            if resolved.reload(decision_date=current_day) != "active":
                return None
            pointer_bytes_after = self.pointer_path.read_bytes()
            if pointer_bytes_after != pointer_bytes_before:
                return None
            if resolved._loaded_pointer != parsed_pointer_before:
                return None
            resolved_identity = resolved.active_identity(decision_date=current_day)
            if resolved_identity is None or _hash_payload(resolved_identity) != expected_hash:
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

    def reload(self, *, decision_date: str | None = None) -> str:
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
        if not self.pointer_path.is_file():
            return "rule_only"
        try:
            pointer = json.loads(self.pointer_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._blocker = "active_pointer_invalid_json"
            return "rule_only"
        if not isinstance(pointer, Mapping) or pointer.get("schema_version") not in {
            "recommendation-calibration-active-pointer.v1",
            "recommendation-calibration-active-pointer.v2",
        }:
            self._blocker = "active_pointer_schema_invalid"
            return "rule_only"
        pointer_status = str(pointer.get("status") or "")
        if pointer_status == "rule_only":
            self._loaded_pointer = pointer
            self._pointer_stat = _path_stat(self.pointer_path)
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
        try:
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
        loaded = self._loader.load(candidate_root, expectation=expectation)
        if loaded.status != "shadow_model_ready" or loaded.model is None:
            self._blocker = loaded.blockers[0] if loaded.blockers else "candidate_load_failed"
            return "rule_only"
        if str(pointer.get("candidate_id") or "") != str(getattr(loaded.model, "model_id", "")):
            self._blocker = "active_pointer_candidate_identity_mismatch"
            return "rule_only"
        if not _pointer_candidate_hashes_match(pointer, candidate_root, loaded.manifest):
            self._blocker = "active_pointer_candidate_hash_mismatch"
            return "rule_only"
        if pointer.get("policy_hash") != RecommendationPromotionPolicy().policy_hash:
            self._blocker = "active_pointer_policy_hash_mismatch"
            return "rule_only"
        if int(pointer.get("maximum_probability_change_bp", -1)) != RecommendationPromotionPolicy().maximum_probability_change_bp:
            self._blocker = "active_pointer_cap_mismatch"
            return "rule_only"
        receipt_error = _pointer_receipt_error(pointer)
        if receipt_error is not None:
            self._blocker = receipt_error
            return "rule_only"
        training_as_of = _date_text_or_none(str(getattr(loaded.model, "training_as_of", "")))
        if training_as_of is None or training_as_of > current_day:
            self._blocker = "candidate_training_cutoff_after_decision"
            return "rule_only"
        training_provenance, training_error = _load_candidate_training_provenance(
            candidate_root=candidate_root,
            candidate_payload=candidate_payload,
            decision_date=current_day,
        )
        if training_error is not None:
            self._blocker = training_error
            return "rule_only"
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
        self._pointer_stat = _path_stat(self.pointer_path)
        self._loaded_decision_date = current_day
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
            or self._pointer_stat != _path_stat(self.pointer_path)
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
            or self._pointer_stat != _path_stat(self.pointer_path)
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
        _invocation_capability: "_InvocationProjectionCapability | None" = None,
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
            or self._pointer_stat != _path_stat(self.pointer_path)
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
        loaded_models: list[tuple[Mapping[str, Any], Any]] = []
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
        _invocation_capability: "_InvocationProjectionCapability | None" = None,
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
            _reject_capability_source_contract_binding(inference_provenance)
        elif (
            self._model is None
            or self._loaded_pointer is None
            or self._pointer_stat != _path_stat(self.pointer_path)
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
        _invocation_capability: "_InvocationProjectionCapability | None" = None,
    ) -> dict[str, RecommendationCalibrationProjection]:
        if _invocation_capability is not None:
            _invocation_capability.assert_projection_use(self, decision_date)
            _reject_capability_source_contract_binding(inference_provenance)
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
    ) -> None:
        self.__owner = owner
        self.__resolved_consumer = resolved_consumer
        self.__invocation_scope_id = invocation_scope_id
        self.__decision_date = decision_date
        self.__identity_hash = identity_hash
        self.__lock = Lock()
        self.__used = False
        self.__active_thread: int | None = None

    def __repr__(self) -> str:
        return "<invocation-local calibration projection capability>"

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
            _reject_capability_source_contract_binding(inference_provenance)
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
                selection_authority=selection_authority,
                selection_score_kind=selection_score_kind,
                selection_percentile_kind=selection_percentile_kind,
                top_n_changed_by_model=top_n_changed_by_model,
                _invocation_capability=self,
            )
        finally:
            with self.__lock:
                self.__active_thread = None

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


def _reject_capability_source_contract_binding(
    inference_provenance: Mapping[str, Any] | None,
) -> None:
    """Keep the capability profile free of provenance-time filesystem reads."""

    if (
        inference_provenance is not None
        and inference_provenance.get("source_contract_binding") is not None
    ):
        raise ValueError(
            "invocation capability does not support filesystem-bound source contracts"
        )


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
