"""將已通過受控 pointer 的 shadow calibration 投影到推薦展示邊界。

Consumer 只讀取隔離 output root 的 active pointer 與 candidate artifact。pointer
不存在、artifact 不相容、feature vector 缺欄或資料品質不足時，一律回傳
rule-only/unavailable；不補零、不回填、不把 shadow model 變成正式下單模型。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from app_module.recommendation_learning_paths import (
    resolve_recommendation_learning_paths,
)
from ml_module.model_artifact_loader import ArtifactCompatibilityExpectation, SafeShadowModelArtifactLoader
from ml_module.model_artifact_manifest import FeatureSchema
from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY
from ml_module.recommendation_calibration_training import (
    RECOMMENDATION_LABEL_CONTRACT_ID,
    RecommendationPrediction,
    recommendation_label_registry_hash,
    candidate_freeze_hash,
)
from ml_module.recommendation_calibration_authority import RecommendationPromotionPolicy
from ml_module.recommendation_probability_transform import (
    NULL_BENCHMARK_BASELINE_ID,
    NULL_BENCHMARK_PROBABILITY_BP,
    PROBABILITY_LINEAGE_SCHEMA_VERSION,
    PROBABILITY_TRANSFORM_ID,
    RecommendationProbabilityTransform,
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
            "raw_calibrated_probability_bp": self.raw_calibrated_probability_bp,
            "raw_after_cost_profit_probability_bp": self.raw_after_cost_profit_probability_bp,
            "warnings": list(self.warnings),
            "status": self.status,
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
        self._blocker: str = "active_pointer_missing"
        self._pointer_stat: tuple[int, int] | None = None
        self._loaded_decision_date: str | None = None

    def reload(self, *, decision_date: str | None = None) -> str:
        """Load and validate the pointer once; return machine-readable status."""

        self._loaded_pointer = None
        self._model = None
        self._baseline_model = None
        self._baseline_identity = None
        self._lineage_models = ()
        self._probability_lineage = ()
        self._blocker = "active_pointer_missing"
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
        expectation = ArtifactCompatibilityExpectation(
            expected_model_family=self.expected_model_family,
            expected_feature_registry_hash=self.feature_registry_hash,
            expected_label_registry_hash=recommendation_label_registry_hash(),
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
        self._loaded_pointer = pointer
        self._model = loaded.model
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
        return {
            "kind": "active_model",
            "pointer_version": self._loaded_pointer.get("pointer_version"),
            "candidate_id": self._loaded_pointer.get("candidate_id"),
            "candidate_root": self._loaded_pointer.get("candidate_root"),
            "candidate_manifest_hash": self._loaded_pointer.get("candidate_manifest_hash"),
            "candidate_artifact_hash": self._loaded_pointer.get("candidate_artifact_hash"),
            "candidate_freeze_hash": self._loaded_pointer.get("candidate_freeze_hash"),
            "model_id": getattr(self._model, "model_id", ""),
            "probability_lineage_schema_version": PROBABILITY_LINEAGE_SCHEMA_VERSION,
            "probability_lineage": [dict(item) for item in self._probability_lineage],
            "probability_lineage_hash": _hash_payload(self._probability_lineage),
        }

    def champion_baseline(
        self,
        *,
        feature_values: Sequence[int | None],
        decision_date: str,
        baseline_probability_bp: int = NULL_BENCHMARK_PROBABILITY_BP,
        baseline_after_cost_probability_bp: int | None = None,
    ) -> RecommendationPrediction | None:
        """Return the previous champion's effective, already-delivered output."""

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
            identity = {
                "candidate_id": node.get("candidate_id"),
                "candidate_root": node.get("candidate_root"),
                "candidate_manifest_hash": node.get("candidate_manifest_hash"),
                "candidate_artifact_hash": node.get("candidate_artifact_hash"),
                "candidate_freeze_hash": node.get("candidate_freeze_hash"),
                "dataset_hash": node.get("dataset_hash"),
            }
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
            expected_label_registry_hash=recommendation_label_registry_hash(),
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
        rule_baseline_id: str = NULL_BENCHMARK_BASELINE_ID,
        ranking_percentile_bp: int | None = None,
        decision_date: str = "",
        data_quality: str = "observed",
    ) -> RecommendationCalibrationProjection:
        current_day = _date_text_or_none(decision_date)
        if current_day is None:
            return RecommendationCalibrationProjection.unavailable(
                stock_code=stock_code,
                warning="decision_date_invalid_fail_closed",
                ranking_percentile_bp=ranking_percentile_bp,
            )
        if (
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
        source_trace = (
            "recommendation_calibration_consumer",
            f"pointer:{self._loaded_pointer.get('pointer_version', '')}",
            f"candidate:{prediction.model_id}",
            f"baseline:{baseline_id}",
            f"baseline_kind:{baseline_kind}",
            f"probability_transform:{transform.transform_id}",
            f"probability_lineage:{_hash_payload(self._probability_lineage)}",
            f"dataset:{prediction.dataset_id}",
            f"training_as_of:{prediction.training_as_of}",
            f"label_contract:{RECOMMENDATION_LABEL_CONTRACT_ID}",
            "benchmark_role:evaluation_only",
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
            cost_basis=f"fixed_round_trip_bp={self._loaded_pointer.get('fixed_round_trip_cost_bp', 'unknown')}; observed liquidity",
            cost_basis_bp=_optional_int(self._loaded_pointer.get("fixed_round_trip_cost_bp")),
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
        )

    def project_many(
        self,
        *,
        feature_values_by_symbol: Mapping[str, Sequence[int | None]],
        rule_probability_by_symbol: Mapping[str, int],
        decision_date: str,
        after_cost_rule_probability_by_symbol: Mapping[str, int] | None = None,
        rule_baseline_id: str = NULL_BENCHMARK_BASELINE_ID,
        ranking_percentile_by_symbol: Mapping[str, int] | None = None,
        data_quality: str = "observed",
    ) -> dict[str, RecommendationCalibrationProjection]:
        percentiles = ranking_percentile_by_symbol or {}
        after_cost_baselines = after_cost_rule_probability_by_symbol or {}
        symbols = tuple(sorted(set(feature_values_by_symbol) | set(rule_probability_by_symbol)))
        return {
            symbol: self.project(
                stock_code=symbol,
                feature_values=feature_values_by_symbol.get(symbol),
                rule_probability_bp=rule_probability_by_symbol.get(symbol),
                after_cost_rule_probability_bp=after_cost_baselines.get(symbol),
                rule_baseline_id=rule_baseline_id,
                ranking_percentile_bp=percentiles.get(symbol),
                decision_date=decision_date,
                data_quality=data_quality,
            )
            for symbol in symbols
        }


def _clamp_to_baseline(value: int | None, baseline: int, cap: int) -> int | None:
    if value is None:
        return None
    return max(0, min(10_000, max(baseline - cap, min(baseline + cap, int(value)))))


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
    return {
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


def _pointer_identity(pointer: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": pointer.get("candidate_id"),
        "candidate_root": pointer.get("candidate_root"),
        "candidate_manifest_hash": pointer.get("candidate_manifest_hash"),
        "candidate_artifact_hash": pointer.get("candidate_artifact_hash"),
        "candidate_freeze_hash": pointer.get("candidate_freeze_hash"),
        "dataset_hash": pointer.get("dataset_hash"),
    }


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
    return {
        "candidate_id": pointer.get("previous_candidate_id"),
        "candidate_root": pointer.get("previous_candidate_root"),
        "candidate_manifest_hash": pointer.get("previous_candidate_manifest_hash"),
        "candidate_artifact_hash": pointer.get("previous_candidate_artifact_hash"),
        "candidate_freeze_hash": pointer.get("previous_candidate_freeze_hash"),
        "dataset_hash": pointer.get("previous_dataset_hash"),
    }


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
