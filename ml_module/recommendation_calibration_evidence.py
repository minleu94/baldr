"""真正的 forward prediction capture 與成熟 outcome comparison producer。

Capture 只寫在 decision cutoff 當下可取得的 feature、candidate/champion
prediction 與 immutable candidate identity；它不包含未來 label。等到 outcome
自然成熟後，``NaturalForwardEvidenceBuilder`` 才讀取 capture 與 matured
outcomes，重算同樣本、同成本的 metrics 並產生可驗證 receipt。這條路徑與
historical untouched test 完全分離，不能用歷史考卷冒充自然前瞻證據。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from ml_module.model_artifact_loader import ArtifactCompatibilityExpectation, SafeShadowModelArtifactLoader
from ml_module.model_artifact_manifest import FeatureSchema
from ml_module.recommendation_calibration_authority import RecommendationPromotionPolicy
from ml_module.recommendation_calibration_training import (
    RecommendationPrediction,
    recommendation_cost_contract_hash,
    recommendation_label_registry_hash,
    feature_schema_hash,
    candidate_freeze_hash,
)
from ml_module.recommendation_probability_transform import (
    NULL_BENCHMARK_BASELINE_ID,
    NULL_BENCHMARK_PROBABILITY_BP,
    PROBABILITY_TRANSFORM_ID,
    RecommendationProbabilityTransform,
)


@dataclass(frozen=True)
class RecommendationPredictionCaptureInput:
    row_id: str
    symbol: str
    decision_date: str
    feature_as_of_date: str
    feature_available_date: str
    feature_values: tuple[int | None, ...]
    rule_probability_bp: int
    rule_after_cost_probability_bp: int | None = None
    rule_baseline_id: str = NULL_BENCHMARK_BASELINE_ID

    def __post_init__(self) -> None:
        if not self.row_id.strip() or not self.symbol.strip():
            raise ValueError("capture row_id and symbol are required")
        decision = _date(self.decision_date)
        if _date(self.feature_as_of_date) >= decision:
            raise ValueError("capture feature_as_of_date must be before decision_date")
        if _date(self.feature_available_date) > decision:
            raise ValueError("capture feature_available_date must not be later than decision_date")
        _probability(self.rule_probability_bp, "rule_probability_bp")
        if not self.rule_baseline_id.strip():
            raise ValueError("rule_baseline_id is required")
        if self.rule_after_cost_probability_bp is not None:
            _probability(self.rule_after_cost_probability_bp, "rule_after_cost_probability_bp")


@dataclass(frozen=True)
class RecommendationPredictionCapture:
    capture_id: str
    capture_as_of_date: str
    captured_at: str
    candidate_id: str
    candidate_root: str
    candidate_freeze_hash: str
    candidate_frozen_at: str
    candidate_manifest_hash: str
    candidate_artifact_hash: str
    dataset_hash: str
    feature_registry_hash: str
    feature_schema_hash: str
    feature_schema: FeatureSchema
    label_registry_hash: str
    cost_contract_hash: str
    fixed_round_trip_cost_bp: int
    maximum_probability_change_bp: int
    policy_hash: str
    rows: tuple[Mapping[str, Any], ...]
    capture_hash: str
    probability_transform_id: str = PROBABILITY_TRANSFORM_ID
    probability_baseline_id: str = NULL_BENCHMARK_BASELINE_ID
    probability_baseline_kind: str = "null_benchmark"
    probability_lineage: tuple[Mapping[str, Any], ...] = ()
    champion_model_id: str = ""
    champion_candidate_id: str = ""
    champion_candidate_root: str = ""
    champion_manifest_hash: str = ""
    champion_artifact_hash: str = ""
    champion_freeze_hash: str = ""
    champion_pointer_version: int | None = None
    capture_path: str | None = None
    capture_origin: str = "scheduled_live"
    source_contract_binding: Mapping[str, Any] | None = None
    schema_version: str = "recommendation-prediction-capture.v2"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "capture_id": self.capture_id,
            "capture_as_of_date": self.capture_as_of_date,
            "captured_at": self.captured_at,
            "candidate_id": self.candidate_id,
            "candidate_root": self.candidate_root,
            "candidate_freeze_hash": self.candidate_freeze_hash,
            "candidate_frozen_at": self.candidate_frozen_at,
            "candidate_manifest_hash": self.candidate_manifest_hash,
            "candidate_artifact_hash": self.candidate_artifact_hash,
            "dataset_hash": self.dataset_hash,
            "feature_registry_hash": self.feature_registry_hash,
            "feature_schema_hash": self.feature_schema_hash,
            "feature_schema": [list(item) for item in self.feature_schema],
            "label_registry_hash": self.label_registry_hash,
            "cost_contract_hash": self.cost_contract_hash,
            "fixed_round_trip_cost_bp": self.fixed_round_trip_cost_bp,
            "maximum_probability_change_bp": self.maximum_probability_change_bp,
            "policy_hash": self.policy_hash,
            "rows": [dict(row) for row in self.rows],
            "capture_hash": self.capture_hash,
            "probability_transform_id": self.probability_transform_id,
            "probability_baseline_id": self.probability_baseline_id,
            "probability_baseline_kind": self.probability_baseline_kind,
            "probability_lineage": [dict(item) for item in self.probability_lineage],
            "champion_model_id": self.champion_model_id,
            "champion_candidate_id": self.champion_candidate_id,
            "champion_candidate_root": self.champion_candidate_root,
            "champion_manifest_hash": self.champion_manifest_hash,
            "champion_artifact_hash": self.champion_artifact_hash,
            "champion_freeze_hash": self.champion_freeze_hash,
            "champion_pointer_version": self.champion_pointer_version,
            "capture_path": self.capture_path,
            "capture_origin": self.capture_origin,
            "source_contract_binding": (
                dict(self.source_contract_binding)
                if self.source_contract_binding is not None
                else None
            ),
        }

    def persist(self, path: str | Path) -> Path:
        destination = Path(path).resolve()
        object.__setattr__(self, "capture_path", str(destination))
        _write_json_once(destination, self.to_dict())
        return destination


@dataclass(frozen=True)
class ActiveModelPredictionCapture:
    """一個已 active pointer 的有效輸出觀測，與 challenger capture 分離。"""

    capture_id: str
    capture_as_of_date: str
    captured_at: str
    active_identity: Mapping[str, Any]
    active_identity_hash: str
    active_candidate_id: str
    active_model_id: str
    active_candidate_root: str
    active_candidate_frozen_at: str
    active_manifest_hash: str
    active_artifact_hash: str
    active_freeze_hash: str
    active_dataset_hash: str | None
    active_pointer_version: int
    active_effective_date: str
    feature_registry_hash: str
    feature_schema_hash: str
    feature_schema: FeatureSchema
    label_registry_hash: str
    cost_contract_hash: str
    fixed_round_trip_cost_bp: int
    maximum_probability_change_bp: int
    policy_hash: str
    probability_transform_id: str
    probability_lineage: tuple[Mapping[str, Any], ...]
    rows: tuple[Mapping[str, Any], ...]
    capture_hash: str
    capture_path: str | None = None
    capture_origin: str = "scheduled_active_monitor"
    schema_version: str = "recommendation-active-model-prediction-capture.v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "capture_id": self.capture_id,
            "capture_as_of_date": self.capture_as_of_date,
            "captured_at": self.captured_at,
            "active_identity": dict(self.active_identity),
            "active_identity_hash": self.active_identity_hash,
            "active_candidate_id": self.active_candidate_id,
            "active_model_id": self.active_model_id,
            "active_candidate_root": self.active_candidate_root,
            "active_candidate_frozen_at": self.active_candidate_frozen_at,
            "active_manifest_hash": self.active_manifest_hash,
            "active_artifact_hash": self.active_artifact_hash,
            "active_freeze_hash": self.active_freeze_hash,
            "active_dataset_hash": self.active_dataset_hash,
            "active_pointer_version": self.active_pointer_version,
            "active_effective_date": self.active_effective_date,
            "feature_registry_hash": self.feature_registry_hash,
            "feature_schema_hash": self.feature_schema_hash,
            "feature_schema": [list(item) for item in self.feature_schema],
            "label_registry_hash": self.label_registry_hash,
            "cost_contract_hash": self.cost_contract_hash,
            "fixed_round_trip_cost_bp": self.fixed_round_trip_cost_bp,
            "maximum_probability_change_bp": self.maximum_probability_change_bp,
            "policy_hash": self.policy_hash,
            "probability_transform_id": self.probability_transform_id,
            "probability_lineage": [dict(item) for item in self.probability_lineage],
            "rows": [dict(row) for row in self.rows],
            "capture_hash": self.capture_hash,
            "capture_path": self.capture_path,
            "capture_origin": self.capture_origin,
        }

    def persist(self, path: str | Path) -> Path:
        destination = Path(path).resolve()
        object.__setattr__(self, "capture_path", str(destination))
        _write_json_once(destination, self.to_dict())
        return destination


class ActiveModelPredictionCaptureService:
    """Capture only the currently delivered active model output for drift monitoring."""

    def capture(
        self,
        *,
        consumer: Any,
        feature_schema: FeatureSchema,
        feature_registry_hash: str,
        policy_hash: str,
        decision_date: str,
        captured_at: str,
        inputs: Sequence[RecommendationPredictionCaptureInput],
        fixed_round_trip_cost_bp: int,
        maximum_probability_change_bp: int = 1_000,
    ) -> ActiveModelPredictionCapture:
        capture_day = _date(decision_date).isoformat()
        if _date(captured_at) > _date(decision_date):
            raise ValueError("active model capture must not be after decision cutoff")
        if not inputs:
            raise ValueError("active model capture requires at least one input row")
        if consumer.reload(decision_date=capture_day) != "active":
            raise ValueError("active pointer is unavailable for monitoring capture")
        identity = consumer.active_identity(decision_date=capture_day)
        if not isinstance(identity, Mapping):
            raise ValueError("active pointer identity is unavailable")
        candidate_id = str(identity.get("candidate_id") or "")
        model_id = str(identity.get("model_id") or candidate_id)
        candidate_root = Path(str(identity.get("candidate_root") or "")).resolve()
        if not candidate_id or not model_id or not candidate_root.is_dir():
            raise ValueError("active pointer identity is incomplete")
        candidate_payload = _read_json(candidate_root / "candidate.json")
        manifest_payload = _read_json(candidate_root / "manifest.json")
        candidate_frozen_at = str(manifest_payload.get("created_at") or "")
        if not candidate_frozen_at:
            raise ValueError("active candidate freeze timestamp is missing")
        if _datetime(candidate_frozen_at) > _datetime(captured_at):
            raise ValueError("active candidate freeze must precede monitoring capture")
        if str(candidate_payload.get("candidate_id") or "") != candidate_id:
            raise ValueError("active candidate identity mismatch")
        if str(manifest_payload.get("manifest_hash") or "") != str(identity.get("candidate_manifest_hash") or ""):
            raise ValueError("active candidate manifest hash mismatch")
        if str(manifest_payload.get("artifact_hash") or "") != str(identity.get("candidate_artifact_hash") or ""):
            raise ValueError("active candidate artifact hash mismatch")
        if tuple(tuple(item) for item in manifest_payload.get("feature_schema", ())) != feature_schema:
            raise ValueError("active candidate feature schema mismatch")
        lineage_payload = identity.get("probability_lineage")
        if not isinstance(lineage_payload, list) or not lineage_payload:
            raise ValueError("active probability lineage is missing")
        lineage = tuple(dict(item) for item in lineage_payload if isinstance(item, Mapping))
        if len(lineage) != len(lineage_payload):
            raise ValueError("active probability lineage is invalid")
        rows: list[Mapping[str, Any]] = []
        for item in sorted(inputs, key=lambda row: (row.row_id, row.symbol)):
            if _date(item.decision_date) != _date(decision_date):
                raise ValueError("all active monitoring rows must use capture decision_date")
            projection = consumer.project(
                stock_code=item.symbol,
                feature_values=item.feature_values,
                rule_probability_bp=item.rule_probability_bp,
                after_cost_rule_probability_bp=item.rule_after_cost_probability_bp,
                rule_baseline_id=item.rule_baseline_id,
                decision_date=capture_day,
                data_quality="observed",
            )
            if projection.status != "active_candidate" or projection.calibrated_probability_bp is None:
                raise ValueError("active effective probability is unavailable")
            if projection.raw_calibrated_probability_bp is None:
                raise ValueError("active raw probability is unavailable")
            rows.append(
                {
                    "row_id": item.row_id,
                    "symbol": item.symbol,
                    "decision_date": capture_day,
                    "feature_as_of_date": _date(item.feature_as_of_date).isoformat(),
                    "feature_available_date": _date(item.feature_available_date).isoformat(),
                    "feature_values": list(item.feature_values),
                    "probability_transform_id": projection.probability_transform_id,
                    "probability_baseline_id": projection.probability_baseline_id,
                    "probability_baseline_kind": projection.probability_baseline_kind,
                    "probability_baseline_probability_bp": projection.probability_baseline_probability_bp,
                    "probability_lineage": [dict(node) for node in lineage],
                    "active_probability_bp": projection.calibrated_probability_bp,
                    "active_after_cost_probability_bp": projection.after_cost_profit_probability_bp,
                    "active_raw_probability_bp": projection.raw_calibrated_probability_bp,
                    "active_raw_after_cost_probability_bp": projection.raw_after_cost_profit_probability_bp,
                }
            )
        identity_hash = _hash_payload(identity)
        capture_id = "active-capture-" + hashlib.sha256(
            json.dumps(
                {"active_identity_hash": identity_hash, "capture_as_of_date": capture_day, "rows": rows},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:24]
        active_effective_date = str(
            consumer._loaded_pointer.get("effective_date")
            if getattr(consumer, "_loaded_pointer", None)
            else ""
        )[:10]
        body: dict[str, Any] = {
            "schema_version": "recommendation-active-model-prediction-capture.v1",
            "capture_id": capture_id,
            "capture_as_of_date": capture_day,
            "captured_at": captured_at,
            "active_identity": dict(identity),
            "active_identity_hash": identity_hash,
            "active_candidate_id": candidate_id,
            "active_model_id": model_id,
            "active_candidate_root": str(candidate_root),
            "active_candidate_frozen_at": candidate_frozen_at,
            "active_manifest_hash": str(identity.get("candidate_manifest_hash") or ""),
            "active_artifact_hash": str(identity.get("candidate_artifact_hash") or ""),
            "active_freeze_hash": str(identity.get("candidate_freeze_hash") or ""),
            "active_dataset_hash": identity.get("dataset_hash"),
            "active_pointer_version": int(identity.get("pointer_version", 0)),
            "active_effective_date": active_effective_date,
            "feature_registry_hash": feature_registry_hash,
            "feature_schema_hash": feature_schema_hash(feature_schema),
            "feature_schema": [list(item) for item in feature_schema],
            "label_registry_hash": recommendation_label_registry_hash(),
            "cost_contract_hash": recommendation_cost_contract_hash(fixed_round_trip_cost_bp),
            "fixed_round_trip_cost_bp": fixed_round_trip_cost_bp,
            "maximum_probability_change_bp": maximum_probability_change_bp,
            "policy_hash": policy_hash,
            "probability_transform_id": PROBABILITY_TRANSFORM_ID,
            "probability_lineage": [dict(item) for item in lineage],
            "rows": rows,
            "capture_origin": "scheduled_active_monitor",
        }
        body["capture_hash"] = _hash_payload(body)
        return ActiveModelPredictionCapture(
            capture_id=capture_id,
            capture_as_of_date=capture_day,
            captured_at=captured_at,
            active_identity=dict(identity),
            active_identity_hash=identity_hash,
            active_candidate_id=candidate_id,
            active_model_id=model_id,
            active_candidate_root=str(candidate_root),
            active_candidate_frozen_at=candidate_frozen_at,
            active_manifest_hash=str(identity.get("candidate_manifest_hash") or ""),
            active_artifact_hash=str(identity.get("candidate_artifact_hash") or ""),
            active_freeze_hash=str(identity.get("candidate_freeze_hash") or ""),
            active_dataset_hash=(str(identity.get("dataset_hash")) if identity.get("dataset_hash") else None),
            active_pointer_version=int(identity.get("pointer_version", 0)),
            active_effective_date=active_effective_date,
            feature_registry_hash=feature_registry_hash,
            feature_schema_hash=feature_schema_hash(feature_schema),
            feature_schema=feature_schema,
            label_registry_hash=recommendation_label_registry_hash(),
            cost_contract_hash=recommendation_cost_contract_hash(fixed_round_trip_cost_bp),
            fixed_round_trip_cost_bp=fixed_round_trip_cost_bp,
            maximum_probability_change_bp=maximum_probability_change_bp,
            policy_hash=policy_hash,
            probability_transform_id=PROBABILITY_TRANSFORM_ID,
            probability_lineage=lineage,
            rows=tuple(rows),
            capture_hash=str(body["capture_hash"]),
        )


@dataclass(frozen=True)
class MaturedRecommendationOutcome:
    capture_row_id: str
    label_end_date: str
    label_available_date: str
    stock_return_bp: int
    observed_liquidity_cost_bp: int | None
    benchmark_return_bp: int | None = None
    observed_liquidity_cost_source: str | None = None

    def __post_init__(self) -> None:
        if _date(self.label_available_date) < _date(self.label_end_date):
            raise ValueError("label_available_date must not precede label_end_date")
        if self.observed_liquidity_cost_bp is not None and self.observed_liquidity_cost_bp < 0:
            raise ValueError("observed_liquidity_cost_bp must be non-negative")


@dataclass(frozen=True)
class NaturalEvidenceReceiptReference:
    receipt_path: str
    receipt_hash: str
    evidence_id: str

    def to_dict(self) -> dict[str, str]:
        return {
            "receipt_path": self.receipt_path,
            "receipt_hash": self.receipt_hash,
            "evidence_id": self.evidence_id,
        }


class RecommendationPredictionCaptureService:
    """Capture inference after candidate freeze and before future outcomes."""

    def capture(
        self,
        *,
        candidate_root: str | Path,
        feature_schema: FeatureSchema,
        feature_registry_hash: str,
        policy_hash: str,
        decision_date: str,
        captured_at: str,
        inputs: Sequence[RecommendationPredictionCaptureInput],
        fixed_round_trip_cost_bp: int,
        maximum_probability_change_bp: int = 1_000,
        data_root: str | Path | None = None,
        champion_pointer_path: str | Path | None = None,
        capture_origin: str = "scheduled_live",
        source_contract_binding: Mapping[str, Any] | None = None,
    ) -> RecommendationPredictionCapture:
        candidate_path = Path(candidate_root).resolve()
        if capture_origin not in {"scheduled_live", "live_forward"}:
            raise ValueError("capture_origin must identify a live scheduled forward capture")
        if source_contract_binding is not None:
            _verify_source_contract_binding(
                source_contract_binding,
                require_ready=True,
                capture_at=captured_at,
            )
        if not 0 <= maximum_probability_change_bp <= 10_000:
            raise ValueError("maximum_probability_change_bp must be within 0..10000")
        candidate_payload = _read_json(candidate_path / "candidate.json")
        manifest_payload = _read_json(candidate_path / "manifest.json")
        candidate_id = str(candidate_payload.get("candidate_id") or "")
        if not candidate_id:
            raise ValueError("candidate identity is missing")
        if candidate_payload.get("feature_schema_hash") != feature_schema_hash(feature_schema):
            raise ValueError("candidate feature schema hash mismatch")
        evaluation_payload = candidate_payload.get("evaluation")
        evaluation = evaluation_payload if isinstance(evaluation_payload, Mapping) else {}
        expected_freeze = candidate_freeze_hash(
            candidate_id=candidate_id,
            dataset_hash=str(candidate_payload.get("dataset_hash") or ""),
            manifest_hash=str(candidate_payload.get("manifest_hash") or ""),
            artifact_hash=str(candidate_payload.get("artifact_hash") or ""),
            evaluation=evaluation,
        )
        if candidate_payload.get("candidate_freeze_hash") != expected_freeze:
            raise ValueError("candidate freeze hash mismatch")
        if manifest_payload.get("manifest_hash") != candidate_payload.get("manifest_hash"):
            raise ValueError("candidate manifest identity mismatch")
        if manifest_payload.get("artifact_hash") != candidate_payload.get("artifact_hash"):
            raise ValueError("candidate artifact identity mismatch")
        if manifest_payload.get("feature_registry_hash") != feature_registry_hash:
            raise ValueError("candidate feature registry hash mismatch")
        if tuple(tuple(item) for item in manifest_payload.get("feature_schema", ())) != feature_schema:
            raise ValueError("candidate feature schema mismatch")
        if manifest_payload.get("production_action_allowed") is not False:
            raise ValueError("candidate must remain shadow-only")
        manifest_created_at = str(manifest_payload.get("created_at") or "")
        candidate_frozen_at = _datetime(manifest_created_at)
        captured_datetime = _datetime(captured_at)
        if candidate_frozen_at > captured_datetime:
            raise ValueError("candidate freeze must precede prediction capture")
        capture_day = _date(decision_date).isoformat()
        if _date(captured_at) > _date(decision_date):
            raise ValueError("prediction capture must not be after decision cutoff")
        if not inputs:
            raise ValueError("prediction capture requires at least one input row")
        expectation = ArtifactCompatibilityExpectation(
            expected_model_family=str(manifest_payload.get("model_family")),
            expected_feature_registry_hash=feature_registry_hash,
            expected_label_registry_hash=recommendation_label_registry_hash(),
            expected_feature_schema=feature_schema,
            installed_library_versions=_library_versions(),
        )
        loaded = SafeShadowModelArtifactLoader(data_root=data_root).load(
            candidate_path,
            expectation=expectation,
        )
        if loaded.status != "shadow_model_ready" or loaded.model is None:
            raise ValueError(f"candidate artifact is not loadable: {loaded.blockers}")
        champion_consumer: Any | None = None
        champion_identity: Mapping[str, Any] | None = None
        if champion_pointer_path is not None:
            from app_module.recommendation_calibration_consumer import RecommendationCalibrationConsumer

            champion_consumer = RecommendationCalibrationConsumer(
                pointer_path=champion_pointer_path,
                feature_schema=feature_schema,
                feature_registry_hash=feature_registry_hash,
                data_root=data_root,
            )
            if champion_consumer.reload(decision_date=capture_day) != "active":
                champion_consumer = None
            else:
                champion_identity = champion_consumer.active_identity(decision_date=capture_day)
        baseline_id = (
            str(champion_identity.get("model_id") or "")
            if champion_identity is not None
            else str(inputs[0].rule_baseline_id)
        )
        baseline_kind = "active_model" if champion_identity is not None else (
            "null_benchmark"
            if baseline_id == NULL_BENCHMARK_BASELINE_ID
            else "declared_baseline"
        )
        if not baseline_id:
            raise ValueError("capture probability baseline identity is missing")
        transform = RecommendationProbabilityTransform(
            baseline_id=baseline_id,
            maximum_probability_change_bp=maximum_probability_change_bp,
        )
        champion_lineage = (
            tuple(dict(item) for item in champion_identity.get("probability_lineage", ()))
            if champion_identity is not None
            else ({
                "kind": "null_benchmark",
                "baseline_id": NULL_BENCHMARK_BASELINE_ID,
                "baseline_kind": "null_benchmark",
                "model_id": None,
                "candidate_id": None,
                "transform_id": PROBABILITY_TRANSFORM_ID,
                "maximum_probability_change_bp": maximum_probability_change_bp,
                "effective_prediction": "identity_from_explicit_baseline",
            },)
        )
        rows: list[Mapping[str, Any]] = []
        for item in sorted(inputs, key=lambda row: (row.row_id, row.symbol)):
            if _date(item.decision_date) != _date(decision_date):
                raise ValueError("all capture rows must use capture decision_date")
            prediction: RecommendationPrediction = loaded.model.predict(item.feature_values)
            champion_prediction = (
                champion_consumer.predict_active(
                    feature_values=item.feature_values,
                    decision_date=capture_day,
                    baseline_probability_bp=item.rule_probability_bp,
                    baseline_after_cost_probability_bp=item.rule_after_cost_probability_bp,
                )
                if champion_consumer is not None
                else None
            )
            champion_probability = (
                champion_prediction.calibrated_probability_bp
                if champion_prediction is not None
                else item.rule_probability_bp
            )
            champion_after_cost = (
                champion_prediction.after_cost_profit_probability_bp
                if champion_prediction is not None
                else item.rule_after_cost_probability_bp
            )
            if champion_probability is None:
                raise ValueError("active champion probability is unavailable")
            effective_probability = transform.apply(
                prediction.calibrated_probability_bp,
                champion_probability,
            )
            if effective_probability is None:
                raise ValueError("candidate probability is unavailable")
            effective_after_cost = (
                transform.apply(
                    prediction.after_cost_profit_probability_bp,
                    champion_after_cost,
                )
                if champion_after_cost is not None
                else None
            )
            rows.append(
                {
                    "row_id": item.row_id,
                    "symbol": item.symbol,
                    "decision_date": _date(item.decision_date).isoformat(),
                    "feature_as_of_date": _date(item.feature_as_of_date).isoformat(),
                    "feature_available_date": _date(item.feature_available_date).isoformat(),
                    "feature_values": list(item.feature_values),
                    "probability_transform_id": transform.transform_id,
                    "probability_baseline_id": baseline_id,
                    "probability_baseline_kind": baseline_kind,
                    "champion_probability_lineage": [dict(item) for item in champion_lineage],
                    "candidate_ranking_score_bp": prediction.ranking_score_bp,
                    # This is the final value consumed by the application. The
                    # raw model output remains separately auditable.
                    "candidate_model_probability_bp": prediction.calibrated_probability_bp,
                    "candidate_probability_bp": effective_probability,
                    "candidate_model_after_cost_probability_bp": prediction.after_cost_profit_probability_bp,
                    "candidate_after_cost_probability_bp": effective_after_cost,
                    "champion_model_probability_bp": (
                        champion_prediction.calibrated_probability_bp
                        if champion_prediction is not None
                        else None
                    ),
                    "champion_model_after_cost_probability_bp": (
                        champion_prediction.after_cost_profit_probability_bp
                        if champion_prediction is not None
                        else None
                    ),
                    "champion_probability_bp": champion_probability,
                    "champion_after_cost_probability_bp": champion_after_cost,
                }
            )
        resolved_source_contract_binding = (
            dict(source_contract_binding) if source_contract_binding is not None else None
        )
        if resolved_source_contract_binding is not None:
            resolved_source_contract_binding.update(
                {
                    "capture_decision_date": capture_day,
                    "capture_symbols": sorted({str(row["symbol"]) for row in rows}),
                    "feature_row_count": len(rows),
                    "feature_snapshot_fingerprint": _feature_snapshot_fingerprint(
                        capture_day,
                        rows,
                    ),
                }
            )
            _verify_source_contract_binding(
                resolved_source_contract_binding,
                require_ready=True,
                capture_day=_date(capture_day),
                capture_rows=rows,
                capture_at=captured_at,
            )
        capture_id = "capture-" + hashlib.sha256(
            json.dumps(
                {
                    "candidate_freeze_hash": candidate_payload["candidate_freeze_hash"],
                    "capture_as_of_date": capture_day,
                    "rows": rows,
                    "source_contract_binding": resolved_source_contract_binding
                    if resolved_source_contract_binding is not None
                    else None,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:24]
        body = {
            "schema_version": "recommendation-prediction-capture.v2",
            "capture_id": capture_id,
            "capture_as_of_date": capture_day,
            "captured_at": captured_at,
            "candidate_id": candidate_id,
            "candidate_root": str(candidate_path),
            "candidate_freeze_hash": candidate_payload["candidate_freeze_hash"],
            "candidate_frozen_at": manifest_created_at,
            "candidate_manifest_hash": candidate_payload["manifest_hash"],
            "candidate_artifact_hash": candidate_payload["artifact_hash"],
            "dataset_hash": candidate_payload["dataset_hash"],
            "feature_registry_hash": feature_registry_hash,
            "feature_schema_hash": feature_schema_hash(feature_schema),
            "feature_schema": [list(item) for item in feature_schema],
            "label_registry_hash": recommendation_label_registry_hash(),
            "cost_contract_hash": recommendation_cost_contract_hash(fixed_round_trip_cost_bp),
            "fixed_round_trip_cost_bp": fixed_round_trip_cost_bp,
            "maximum_probability_change_bp": maximum_probability_change_bp,
            "policy_hash": policy_hash,
            "probability_transform_id": transform.transform_id,
            "probability_baseline_id": baseline_id,
            "probability_baseline_kind": baseline_kind,
            "probability_lineage": [dict(item) for item in champion_lineage],
            "champion_model_id": str(champion_identity.get("model_id") or "") if champion_identity else "",
            "champion_candidate_id": str(champion_identity.get("candidate_id") or "") if champion_identity else "",
            "champion_candidate_root": str(champion_identity.get("candidate_root") or "") if champion_identity else "",
            "champion_manifest_hash": str(champion_identity.get("candidate_manifest_hash") or "") if champion_identity else "",
            "champion_artifact_hash": str(champion_identity.get("candidate_artifact_hash") or "") if champion_identity else "",
            "champion_freeze_hash": str(champion_identity.get("candidate_freeze_hash") or "") if champion_identity else "",
            "champion_pointer_version": champion_identity.get("pointer_version") if champion_identity else None,
            "rows": rows,
            "capture_origin": capture_origin,
            "source_contract_binding": (
                resolved_source_contract_binding
                if resolved_source_contract_binding is not None
                else None
            ),
        }
        capture_hash = _hash_payload(body)
        return RecommendationPredictionCapture(
            capture_id=capture_id,
            capture_as_of_date=capture_day,
            captured_at=captured_at,
            candidate_id=candidate_id,
            candidate_root=str(candidate_path),
            candidate_freeze_hash=str(candidate_payload["candidate_freeze_hash"]),
            candidate_frozen_at=manifest_created_at,
            candidate_manifest_hash=str(candidate_payload["manifest_hash"]),
            candidate_artifact_hash=str(candidate_payload["artifact_hash"]),
            dataset_hash=str(candidate_payload["dataset_hash"]),
            feature_registry_hash=feature_registry_hash,
            feature_schema_hash=feature_schema_hash(feature_schema),
            feature_schema=feature_schema,
            label_registry_hash=recommendation_label_registry_hash(),
            cost_contract_hash=recommendation_cost_contract_hash(fixed_round_trip_cost_bp),
            fixed_round_trip_cost_bp=fixed_round_trip_cost_bp,
            maximum_probability_change_bp=maximum_probability_change_bp,
            policy_hash=policy_hash,
            rows=tuple(rows),
            capture_hash=capture_hash,
            probability_transform_id=transform.transform_id,
            probability_baseline_id=baseline_id,
            probability_baseline_kind=baseline_kind,
            probability_lineage=tuple(dict(item) for item in champion_lineage),
            champion_model_id=str(champion_identity.get("model_id") or "") if champion_identity else "",
            champion_candidate_id=str(champion_identity.get("candidate_id") or "") if champion_identity else "",
            champion_candidate_root=str(champion_identity.get("candidate_root") or "") if champion_identity else "",
            champion_manifest_hash=str(champion_identity.get("candidate_manifest_hash") or "") if champion_identity else "",
            champion_artifact_hash=str(champion_identity.get("candidate_artifact_hash") or "") if champion_identity else "",
            champion_freeze_hash=str(champion_identity.get("candidate_freeze_hash") or "") if champion_identity else "",
            champion_pointer_version=(
                int(champion_identity["pointer_version"])
                if champion_identity and champion_identity.get("pointer_version") is not None
                else None
            ),
            capture_origin=capture_origin,
            source_contract_binding=(
                resolved_source_contract_binding
                if resolved_source_contract_binding is not None
                else None
            ),
        )


class NaturalForwardEvidenceBuilder:
    """Read a capture plus matured outcomes and recompute all comparison metrics."""

    def build(
        self,
        *,
        capture: RecommendationPredictionCapture | str | Path,
        outcomes: Sequence[MaturedRecommendationOutcome],
        evaluation_date: str,
        output_path: str | Path,
        source_id: str = "scheduled_forward_outcomes",
    ) -> NaturalEvidenceReceiptReference:
        if isinstance(capture, RecommendationPredictionCapture) and capture.capture_path is None:
            # A capture must become a durable first-stage artifact before a
            # mature receipt can be built.  The automatic adjacent path keeps
            # the helper safe for callers while preserving the two-stage audit.
            capture.persist(Path(output_path).resolve().with_suffix(".capture.json"))
        capture_payload = _capture_payload(capture)
        _verify_capture_document(capture_payload)
        return self._build_from_payload(
            capture_payload=capture_payload,
            outcomes=outcomes,
            evaluation_date=evaluation_date,
            output_path=output_path,
            source_id=source_id,
        )

    def build_many(
        self,
        *,
        captures: Sequence[str | Path],
        outcomes: Sequence[MaturedRecommendationOutcome],
        evaluation_date: str,
        output_path: str | Path,
        source_id: str = "scheduled_forward_outcomes",
    ) -> NaturalEvidenceReceiptReference:
        """Build one receipt from multiple immutable daily captures.

        The bundle is only a durable index of source captures and copied
        prediction rows.  It never creates a prediction or a label; every
        source capture is re-hashed and re-verified before the aggregate is
        written.  This lets one frozen challenger accumulate a bounded
        cross-day natural cohort without evaluating a different candidate.
        """

        capture_paths = tuple(Path(item).resolve() for item in captures)
        if not capture_paths:
            raise ValueError("at least one prediction capture is required")
        payloads: list[dict[str, Any]] = []
        for path in capture_paths:
            payload = _read_json(path)
            _verify_capture_payload(payload)
            payload["capture_path"] = str(path)
            payloads.append(payload)
        bundle = _build_capture_bundle(payloads, capture_paths)
        bundle_path = Path(output_path).resolve().with_suffix(".capture-bundle.json")
        bundle["capture_path"] = str(bundle_path)
        _write_json_once(bundle_path, bundle)
        _verify_capture_bundle_payload(bundle)
        return self._build_from_payload(
            capture_payload=bundle,
            outcomes=outcomes,
            evaluation_date=evaluation_date,
            output_path=output_path,
            source_id=source_id,
        )

    def _build_from_payload(
        self,
        *,
        capture_payload: Mapping[str, Any],
        outcomes: Sequence[MaturedRecommendationOutcome],
        evaluation_date: str,
        output_path: str | Path,
        source_id: str,
    ) -> NaturalEvidenceReceiptReference:
        evaluation_day = _date(evaluation_date)
        by_id = {str(row["row_id"]): row for row in capture_payload["rows"]}
        if len(by_id) != len(capture_payload["rows"]):
            raise ValueError("prediction capture row ids must be unique")
        outcome_ids = [row.capture_row_id for row in outcomes]
        if len(outcome_ids) != len(set(outcome_ids)):
            raise ValueError("matured outcomes must not duplicate capture row ids")
        outcome_by_id = {row.capture_row_id: row for row in outcomes}
        comparisons: list[dict[str, Any]] = []
        for row_id, outcome in sorted(outcome_by_id.items()):
            capture_row = by_id.get(row_id)
            if capture_row is None:
                raise ValueError(f"outcome has no matching capture row: {row_id}")
            if _date(outcome.label_available_date) > evaluation_day:
                continue
            capture_day = _date(str(capture_row["decision_date"]))
            if evaluation_day < capture_day:
                raise ValueError("evaluation_date must follow prediction capture")
            if _date(outcome.label_end_date) <= capture_day:
                raise ValueError("matured label end must follow prediction capture")
            if capture_row.get("candidate_probability_bp") is None or capture_row.get("champion_probability_bp") is None:
                raise ValueError("capture probability missing")
            row_payload = {
                "capture_row_id": row_id,
                "symbol": capture_row["symbol"],
                "capture_as_of_date": capture_row["decision_date"],
                "feature_as_of_date": capture_row.get("feature_as_of_date"),
                "feature_available_date": capture_row.get("feature_available_date"),
                "feature_values": capture_row.get("feature_values"),
                "label_end_date": _date(outcome.label_end_date).isoformat(),
                "label_available_date": _date(outcome.label_available_date).isoformat(),
                "stock_return_bp": outcome.stock_return_bp,
                "observed_liquidity_cost_bp": outcome.observed_liquidity_cost_bp,
                "observed_liquidity_cost_source": outcome.observed_liquidity_cost_source,
                "benchmark_return_bp": outcome.benchmark_return_bp,
                "probability_transform_id": capture_row.get("probability_transform_id"),
                "probability_baseline_id": capture_row.get("probability_baseline_id"),
                "probability_baseline_kind": capture_row.get("probability_baseline_kind"),
                "champion_probability_lineage": capture_row.get("champion_probability_lineage"),
                "candidate_model_probability_bp": capture_row.get("candidate_model_probability_bp"),
                "candidate_probability_bp": int(capture_row["candidate_probability_bp"]),
                "candidate_model_after_cost_probability_bp": capture_row.get("candidate_model_after_cost_probability_bp"),
                "champion_probability_bp": int(capture_row["champion_probability_bp"]),
                "candidate_after_cost_probability_bp": capture_row.get("candidate_after_cost_probability_bp"),
                "champion_after_cost_probability_bp": capture_row.get("champion_after_cost_probability_bp"),
            }
            row_payload["upside_label"] = int(outcome.stock_return_bp > 0)
            if (
                outcome.observed_liquidity_cost_bp is None
                or outcome.observed_liquidity_cost_source is None
            ):
                row_payload["after_cost_profit_label"] = None
            else:
                row_payload["after_cost_profit_label"] = int(
                    outcome.stock_return_bp
                    > int(capture_payload["fixed_round_trip_cost_bp"]) + outcome.observed_liquidity_cost_bp
                )
            comparisons.append(row_payload)
        if not comparisons:
            raise ValueError("no naturally matured outcome matches the prediction capture")
        candidate_probabilities = [int(row["candidate_probability_bp"]) for row in comparisons]
        champion_probabilities = [int(row["champion_probability_bp"]) for row in comparisons]
        labels = [int(row["upside_label"]) for row in comparisons]
        candidate_brier = _brier_bp(candidate_probabilities, labels)
        champion_brier = _brier_bp(champion_probabilities, labels)
        candidate_gap = _calibration_gap_bp(candidate_probabilities, labels)
        after_cost_rows = tuple(
            row
            for row in comparisons
            if row["after_cost_profit_label"] is not None
            and row["candidate_after_cost_probability_bp"] is not None
            and row["champion_after_cost_probability_bp"] is not None
        )
        after_cost_status = "observed" if after_cost_rows else "missing_liquidity_or_baseline"
        after_cost_candidate_brier: int | None = None
        after_cost_champion_brier: int | None = None
        after_cost_improvement: int | None = None
        after_cost_gap: int | None = None
        after_cost_candidate_hash: str | None = None
        after_cost_champion_hash: str | None = None
        if after_cost_rows:
            after_candidate_probabilities = [int(row["candidate_after_cost_probability_bp"]) for row in after_cost_rows]
            after_champion_probabilities = [int(row["champion_after_cost_probability_bp"]) for row in after_cost_rows]
            after_labels = [int(row["after_cost_profit_label"]) for row in after_cost_rows]
            after_cost_candidate_brier = _brier_bp(after_candidate_probabilities, after_labels)
            after_cost_champion_brier = _brier_bp(after_champion_probabilities, after_labels)
            after_cost_improvement = after_cost_champion_brier - after_cost_candidate_brier
            after_cost_gap = _calibration_gap_bp(after_candidate_probabilities, after_labels)
            after_cost_candidate_hash = _hash_payload(
                {
                    "row_ids": [row["capture_row_id"] for row in after_cost_rows],
                    "probabilities_bp": after_candidate_probabilities,
                }
            )
            after_cost_champion_hash = _hash_payload(
                {
                    "row_ids": [row["capture_row_id"] for row in after_cost_rows],
                    "probabilities_bp": after_champion_probabilities,
                }
            )
        comparison_fingerprint = _hash_payload(
            {
                "capture_id": capture_payload["capture_id"],
                "rows": [
                    {
                        "capture_row_id": row["capture_row_id"],
                        "label_end_date": row["label_end_date"],
                        "label_available_date": row["label_available_date"],
                        "stock_return_bp": row["stock_return_bp"],
                        "observed_liquidity_cost_bp": row["observed_liquidity_cost_bp"],
                        "observed_liquidity_cost_source": row.get("observed_liquidity_cost_source"),
                    }
                    for row in comparisons
                ],
            }
        )
        candidate_prediction_hash = _hash_payload(
            {"row_ids": [row["capture_row_id"] for row in comparisons], "probabilities_bp": candidate_probabilities}
        )
        champion_prediction_hash = _hash_payload(
            {"row_ids": [row["capture_row_id"] for row in comparisons], "probabilities_bp": champion_probabilities}
        )
        evidence_id = "natural-evidence-" + hashlib.sha256(
            f"{capture_payload['capture_hash']}|{comparison_fingerprint}|{evaluation_day.isoformat()}".encode("utf-8")
        ).hexdigest()[:24]
        body: dict[str, Any] = {
            "schema_version": "recommendation-natural-forward-evidence.v2",
            "evidence_id": evidence_id,
            "source_id": source_id,
            "source_kind": "matured_forward_prediction_capture",
            "status": "matured",
            "as_of_date": evaluation_day.isoformat(),
            "capture_id": capture_payload["capture_id"],
            "capture_hash": capture_payload["capture_hash"],
            "capture_as_of_date": capture_payload["capture_as_of_date"],
            "captured_at": capture_payload["captured_at"],
            "candidate_frozen_at": capture_payload["candidate_frozen_at"],
            "candidate_id": capture_payload["candidate_id"],
            "candidate_freeze_hash": capture_payload["candidate_freeze_hash"],
            "candidate_manifest_hash": capture_payload["candidate_manifest_hash"],
            "candidate_artifact_hash": capture_payload["candidate_artifact_hash"],
            "dataset_hash": capture_payload["dataset_hash"],
            "feature_registry_hash": capture_payload["feature_registry_hash"],
            "feature_schema_hash": capture_payload["feature_schema_hash"],
            "feature_schema": capture_payload["feature_schema"],
            "label_registry_hash": capture_payload["label_registry_hash"],
            "cost_contract_hash": capture_payload["cost_contract_hash"],
            "fixed_round_trip_cost_bp": capture_payload["fixed_round_trip_cost_bp"],
            "maximum_probability_change_bp": capture_payload["maximum_probability_change_bp"],
            "policy_hash": capture_payload["policy_hash"],
            "probability_transform_id": capture_payload.get("probability_transform_id", PROBABILITY_TRANSFORM_ID),
            "probability_baseline_id": capture_payload.get("probability_baseline_id"),
            "probability_baseline_kind": capture_payload.get("probability_baseline_kind"),
            "probability_lineage": capture_payload.get("probability_lineage"),
            "champion_model_id": capture_payload.get("champion_model_id"),
            "champion_candidate_id": capture_payload.get("champion_candidate_id"),
            "champion_candidate_root": capture_payload.get("champion_candidate_root"),
            "champion_manifest_hash": capture_payload.get("champion_manifest_hash"),
            "champion_artifact_hash": capture_payload.get("champion_artifact_hash"),
            "champion_freeze_hash": capture_payload.get("champion_freeze_hash"),
            "champion_pointer_version": capture_payload.get("champion_pointer_version"),
            "source_capture_ids": capture_payload.get("source_capture_ids", [capture_payload["capture_id"]]),
            "source_capture_hashes": capture_payload.get("source_capture_hashes", [capture_payload["capture_hash"]]),
            "source_capture_paths": capture_payload.get("source_capture_paths", [capture_payload.get("capture_path")]),
            "source_contract_bindings": capture_payload.get(
                "source_contract_bindings",
                [capture_payload.get("source_contract_binding")],
            ),
            "matured_sample_count": len(comparisons),
            "comparison_sample_fingerprint": comparison_fingerprint,
            "candidate_prediction_hash": candidate_prediction_hash,
            "champion_prediction_hash": champion_prediction_hash,
            "same_date_same_cost": True,
            "observed_champion_brier_bp": champion_brier,
            "observed_candidate_brier_bp": candidate_brier,
            "observed_brier_improvement_bp": champion_brier - candidate_brier,
            "observed_calibration_gap_bp": candidate_gap,
            "after_cost_evaluation_status": after_cost_status,
            "after_cost_matured_sample_count": len(after_cost_rows),
            "observed_champion_after_cost_brier_bp": after_cost_champion_brier,
            "observed_candidate_after_cost_brier_bp": after_cost_candidate_brier,
            "observed_after_cost_brier_improvement_bp": after_cost_improvement,
            "observed_after_cost_calibration_gap_bp": after_cost_gap,
            "after_cost_candidate_prediction_hash": after_cost_candidate_hash,
            "after_cost_champion_prediction_hash": after_cost_champion_hash,
            "capture_path": capture_payload.get("capture_path"),
            "capture_origin": capture_payload.get("capture_origin"),
            "comparisons": comparisons,
        }
        body["receipt_body_hash"] = _hash_payload(body)
        destination = Path(output_path).resolve()
        _write_json_once(destination, body)
        return NaturalEvidenceReceiptReference(
            receipt_path=str(destination),
            receipt_hash=_sha256_file(destination),
            evidence_id=evidence_id,
        )


def _capture_payload(capture: RecommendationPredictionCapture | str | Path) -> dict[str, Any]:
    if isinstance(capture, RecommendationPredictionCapture):
        if capture.capture_path:
            return _read_json(Path(capture.capture_path).resolve())
        return capture.to_dict()
    return _read_json(Path(capture).resolve())


def _verify_capture_document(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") == "recommendation-prediction-capture-bundle.v1":
        _verify_capture_bundle_payload(payload)
        return
    _verify_capture_payload(payload)


def _build_capture_bundle(
    payloads: Sequence[Mapping[str, Any]],
    paths: Sequence[Path],
) -> dict[str, Any]:
    if not payloads or len(payloads) != len(paths):
        raise ValueError("capture bundle sources are missing")
    first = payloads[0]
    common_fields = (
        "candidate_id", "candidate_root", "candidate_freeze_hash",
        "candidate_frozen_at", "candidate_manifest_hash", "candidate_artifact_hash",
        "dataset_hash", "feature_registry_hash", "feature_schema_hash",
        "cost_contract_hash", "fixed_round_trip_cost_bp",
        "maximum_probability_change_bp", "policy_hash", "probability_transform_id",
    )
    for payload in payloads[1:]:
        for field_name in common_fields:
            if str(payload.get(field_name)) != str(first.get(field_name)):
                raise ValueError(f"capture bundle source mismatch: {field_name}")
    source_rows: list[Mapping[str, Any]] = []
    source_ids: list[str] = []
    source_hashes: list[str] = []
    source_paths: list[str] = []
    for payload, path in zip(payloads, paths):
        rows = payload.get("rows")
        if not isinstance(rows, list):
            raise ValueError("capture bundle source rows are invalid")
        source_rows.extend(rows)
        source_ids.append(str(payload["capture_id"]))
        source_hashes.append(str(payload["capture_hash"]))
        source_paths.append(str(path.resolve()))
    row_ids = [str(row.get("row_id")) for row in source_rows if isinstance(row, Mapping)]
    if len(row_ids) != len(set(row_ids)):
        raise ValueError("capture bundle row ids must be unique")
    capture_days = sorted(_date(str(row["decision_date"])) for row in source_rows)
    if not capture_days:
        raise ValueError("capture bundle has no rows")
    bundle_id = "capture-bundle-" + hashlib.sha256(
        json.dumps(
            {"candidate_freeze_hash": first["candidate_freeze_hash"], "source_ids": source_ids},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:24]
    body: dict[str, Any] = {
        "schema_version": "recommendation-prediction-capture-bundle.v1",
        "capture_id": bundle_id,
        "capture_as_of_date": capture_days[0].isoformat(),
        "capture_as_of_date_max": capture_days[-1].isoformat(),
        "captured_at": min(str(payload["captured_at"]) for payload in payloads),
        "candidate_id": first["candidate_id"],
        "candidate_root": first["candidate_root"],
        "candidate_freeze_hash": first["candidate_freeze_hash"],
        "candidate_frozen_at": first["candidate_frozen_at"],
        "candidate_manifest_hash": first["candidate_manifest_hash"],
        "candidate_artifact_hash": first["candidate_artifact_hash"],
        "dataset_hash": first["dataset_hash"],
        "feature_registry_hash": first["feature_registry_hash"],
        "feature_schema_hash": first["feature_schema_hash"],
        "feature_schema": first.get("feature_schema", []),
        "label_registry_hash": first.get("label_registry_hash"),
        "cost_contract_hash": first["cost_contract_hash"],
        "fixed_round_trip_cost_bp": first["fixed_round_trip_cost_bp"],
        "maximum_probability_change_bp": first["maximum_probability_change_bp"],
        "policy_hash": first["policy_hash"],
        "probability_transform_id": first["probability_transform_id"],
        "probability_lineage": "per_capture_source",
        "probability_baseline_id": "per_capture_source",
        "probability_baseline_kind": "per_capture_source",
        "champion_model_id": "per_capture_source",
        "champion_candidate_id": "per_capture_source",
        "champion_candidate_root": "per_capture_source",
        "champion_manifest_hash": "per_capture_source",
        "champion_artifact_hash": "per_capture_source",
        "champion_freeze_hash": "per_capture_source",
        "champion_pointer_version": None,
        "source_capture_ids": source_ids,
        "source_capture_hashes": source_hashes,
        "source_capture_paths": source_paths,
        "source_contract_bindings": [
            payload.get("source_contract_binding") for payload in payloads
        ],
        "rows": source_rows,
        "capture_origin": "scheduled_live_bundle",
    }
    body["capture_hash"] = _hash_payload(body)
    body["capture_path"] = None
    return body


def _verify_capture_bundle_payload(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != "recommendation-prediction-capture-bundle.v1":
        raise ValueError("capture bundle schema is unsupported")
    required = (
        "capture_id", "capture_as_of_date", "capture_as_of_date_max", "captured_at",
        "candidate_id", "candidate_root", "candidate_freeze_hash", "candidate_frozen_at",
        "candidate_manifest_hash", "candidate_artifact_hash", "dataset_hash",
        "feature_registry_hash", "feature_schema_hash", "cost_contract_hash",
        "fixed_round_trip_cost_bp", "maximum_probability_change_bp", "policy_hash",
        "probability_transform_id", "probability_lineage", "source_capture_ids", "source_capture_hashes",
        "source_capture_paths", "rows", "capture_hash", "capture_origin",
    )
    if any(key not in payload for key in required):
        raise ValueError("capture bundle metadata is incomplete")
    body = {
        key: value
        for key, value in payload.items()
        if key not in {"capture_hash", "capture_path"}
    }
    if _hash_payload(body) != payload["capture_hash"]:
        raise ValueError("capture bundle hash mismatch")
    if payload.get("probability_lineage") != "per_capture_source":
        raise ValueError("capture bundle probability lineage marker is invalid")
    source_ids_value = payload.get("source_capture_ids")
    source_hashes_value = payload.get("source_capture_hashes")
    source_paths_value = payload.get("source_capture_paths")
    if not (
        isinstance(source_ids_value, list)
        and isinstance(source_hashes_value, list)
        and isinstance(source_paths_value, list)
    ):
        raise ValueError("capture bundle source index is invalid")
    source_ids: list[Any] = source_ids_value
    source_hashes: list[Any] = source_hashes_value
    source_paths: list[Any] = source_paths_value
    if not source_ids or not (len(source_ids) == len(source_hashes) == len(source_paths)):
        raise ValueError("capture bundle source index is empty or misaligned")
    source_rows: list[Mapping[str, Any]] = []
    common_fields = (
        "candidate_id", "candidate_freeze_hash", "candidate_manifest_hash",
        "candidate_artifact_hash", "dataset_hash", "feature_registry_hash",
        "feature_schema_hash", "cost_contract_hash", "fixed_round_trip_cost_bp",
        "maximum_probability_change_bp", "policy_hash", "probability_transform_id",
    )
    for source_id, source_hash, source_path in zip(source_ids, source_hashes, source_paths):
        path = Path(str(source_path)).resolve()
        source = _read_json(path)
        _verify_capture_payload(source)
        if str(source.get("capture_id")) != str(source_id) or str(source.get("capture_hash")) != str(source_hash):
            raise ValueError("capture bundle source hash or identity mismatch")
        for field_name in common_fields:
            if str(source.get(field_name)) != str(payload.get(field_name)):
                raise ValueError(f"capture bundle source binding mismatch: {field_name}")
        rows = source.get("rows")
        if not isinstance(rows, list):
            raise ValueError("capture bundle source rows are invalid")
        source_rows.extend(row for row in rows if isinstance(row, Mapping))
    rows = payload.get("rows")
    if not isinstance(rows, list) or rows != source_rows:
        raise ValueError("capture bundle rows do not match immutable sources")
    row_ids = [str(row.get("row_id")) for row in rows if isinstance(row, Mapping)]
    if len(row_ids) != len(rows) or len(row_ids) != len(set(row_ids)):
        raise ValueError("capture bundle row ids are invalid")
    capture_days = sorted(_date(str(row["decision_date"])) for row in rows if isinstance(row, Mapping))
    if not capture_days:
        raise ValueError("capture bundle has no rows")
    if payload.get("capture_as_of_date") != capture_days[0].isoformat() or payload.get("capture_as_of_date_max") != capture_days[-1].isoformat():
        raise ValueError("capture bundle date bounds mismatch")
    if payload.get("capture_origin") != "scheduled_live_bundle":
        raise ValueError("capture bundle origin is invalid")


def _verify_capture_payload(payload: Mapping[str, Any]) -> None:
    required = (
        "capture_id", "capture_as_of_date", "captured_at", "candidate_id",
        "candidate_freeze_hash", "candidate_frozen_at", "candidate_manifest_hash",
        "candidate_artifact_hash", "feature_registry_hash", "feature_schema_hash",
        "cost_contract_hash", "fixed_round_trip_cost_bp", "maximum_probability_change_bp",
        "policy_hash", "probability_transform_id", "probability_baseline_id",
        "probability_baseline_kind", "probability_lineage", "champion_model_id", "champion_candidate_id",
        "champion_candidate_root", "champion_manifest_hash", "champion_artifact_hash",
        "champion_freeze_hash", "champion_pointer_version", "rows", "capture_hash",
        "capture_origin",
    )
    if any(key not in payload for key in required):
        raise ValueError("prediction capture metadata is incomplete")
    if payload.get("schema_version") != "recommendation-prediction-capture.v2":
        raise ValueError("prediction capture schema is unsupported")
    body = {
        key: value
        for key, value in payload.items()
        if key not in {"capture_hash", "capture_path"}
    }
    if _hash_payload(body) != payload["capture_hash"]:
        raise ValueError("prediction capture hash mismatch")
    if _date(str(payload["captured_at"])) > _date(str(payload["capture_as_of_date"])):
        raise ValueError("prediction capture timestamp is after decision cutoff")
    if _datetime(str(payload["candidate_frozen_at"])) > _datetime(str(payload["captured_at"])):
        raise ValueError("candidate freeze is after prediction capture")
    if str(payload.get("capture_origin")) not in {"scheduled_live", "live_forward"}:
        raise ValueError("prediction capture origin is not a live forward capture")
    maximum_change = int(payload["maximum_probability_change_bp"])
    if not 0 <= maximum_change <= 10_000:
        raise ValueError("prediction capture probability cap is invalid")
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("prediction capture rows are missing")
    baseline_id = str(payload.get("probability_baseline_id") or "")
    baseline_kind = str(payload.get("probability_baseline_kind") or "")
    if not baseline_id or baseline_kind not in {
        "active_model", "null_benchmark", "declared_baseline"
    }:
        raise ValueError("prediction capture baseline identity is invalid")
    if payload.get("probability_transform_id") != PROBABILITY_TRANSFORM_ID:
        raise ValueError("prediction capture probability transform is unsupported")
    if payload.get("source_contract_binding") is not None:
        _verify_source_contract_binding(
            payload["source_contract_binding"],
            require_ready=True,
            capture_at=str(payload["captured_at"]),
        )
    lineage = payload.get("probability_lineage")
    if not isinstance(lineage, list) or not lineage:
        raise ValueError("prediction capture probability lineage is missing")
    if baseline_kind == "null_benchmark" and baseline_id != NULL_BENCHMARK_BASELINE_ID:
        raise ValueError("null benchmark baseline identity mismatch")
    if baseline_kind == "active_model" and not payload.get("champion_model_id"):
        raise ValueError("active champion model identity is missing")
    transform = RecommendationProbabilityTransform(
        baseline_id=baseline_id,
        maximum_probability_change_bp=maximum_change,
    )
    row_ids: set[str] = set()
    capture_day = _date(str(payload["capture_as_of_date"]))
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("prediction capture row is invalid")
        row_id = str(row.get("row_id") or "")
        if not row_id or row_id in row_ids:
            raise ValueError("prediction capture row ids must be unique")
        row_ids.add(row_id)
        if _date(str(row.get("decision_date"))) != capture_day:
            raise ValueError("prediction capture row decision date mismatch")
        if _date(str(row.get("feature_as_of_date"))) >= capture_day:
            raise ValueError("prediction capture feature is not point-in-time")
        if _date(str(row.get("feature_available_date"))) > capture_day:
            raise ValueError("prediction capture feature availability is after decision")
        for field_name in ("candidate_probability_bp", "champion_probability_bp"):
            _probability(int(row[field_name]), field_name)
        if row.get("probability_transform_id") != payload.get("probability_transform_id"):
            raise ValueError("prediction capture row probability transform mismatch")
        if row.get("probability_baseline_id") != payload.get("probability_baseline_id"):
            raise ValueError("prediction capture row probability baseline mismatch")
        if row.get("probability_baseline_kind") != payload.get("probability_baseline_kind"):
            raise ValueError("prediction capture row probability baseline kind mismatch")
        if row.get("champion_probability_lineage") != lineage:
            raise ValueError("prediction capture row probability lineage mismatch")
        raw_probability = row.get("candidate_model_probability_bp")
        if raw_probability is None or not isinstance(raw_probability, int):
            raise ValueError("prediction capture raw candidate probability is missing")
        _probability(raw_probability, "candidate_model_probability_bp")
        if int(row["candidate_probability_bp"]) != transform.apply(
            raw_probability,
            int(row["champion_probability_bp"]),
        ):
            raise ValueError("prediction capture candidate probability cap mismatch")
        raw_after_cost = row.get("candidate_model_after_cost_probability_bp")
        effective_after_cost = row.get("candidate_after_cost_probability_bp")
        if raw_after_cost is None:
            if effective_after_cost is not None:
                raise ValueError("prediction capture after-cost probability cap mismatch")
        else:
            if not isinstance(raw_after_cost, int):
                raise ValueError("prediction capture raw after-cost probability is invalid")
            _probability(raw_after_cost, "candidate_model_after_cost_probability_bp")
            champion_after_cost = row.get("champion_after_cost_probability_bp")
            if champion_after_cost is None or effective_after_cost != transform.apply(
                raw_after_cost,
                int(champion_after_cost),
            ):
                raise ValueError("prediction capture after-cost probability cap mismatch")
        champion_model_probability = row.get("champion_model_probability_bp")
        champion_model_after_cost = row.get("champion_model_after_cost_probability_bp")
        if baseline_kind == "active_model":
            if champion_model_probability != int(row["champion_probability_bp"]):
                raise ValueError("active champion probability identity mismatch")
            if champion_model_after_cost is not None and row.get("champion_after_cost_probability_bp") != champion_model_after_cost:
                raise ValueError("active champion after-cost probability identity mismatch")
        elif champion_model_probability is not None or champion_model_after_cost is not None:
            raise ValueError("null or declared baseline cannot carry active model prediction")
    if payload.get("source_contract_binding") is not None:
        _verify_source_contract_binding(
            payload["source_contract_binding"],
            require_ready=True,
            capture_day=capture_day,
            capture_rows=rows,
            capture_at=str(payload["captured_at"]),
        )


def _verify_source_contract_binding(
    binding: object,
    *,
    require_ready: bool,
    expected_contract_file_sha256: str | None = None,
    capture_day: date | None = None,
    capture_rows: Sequence[Mapping[str, Any]] | None = None,
    capture_at: str | None = None,
) -> None:
    """Verify a capture's immutable prospective-input source binding."""

    if not isinstance(binding, Mapping):
        raise ValueError("capture source contract binding is invalid")
    if binding.get("schema_version") != "recommendation-calibration-capture-source-binding.v1":
        raise ValueError("capture source contract binding schema is unsupported")
    if binding.get("historical_pit_eligible") is not False:
        raise ValueError("capture source contract binding cannot claim historical PIT")
    if require_ready and binding.get("price_up_prospective_status") != "ready":
        raise ValueError("capture source contract prospective price-up source is not ready")
    contract_path = Path(str(binding.get("contract_path") or "")).expanduser().resolve()
    contract_file_hash = str(binding.get("contract_file_sha256") or "")
    contract_content_hash = str(binding.get("contract_content_sha256") or "")
    if not contract_path.is_file() or contract_path.is_symlink():
        raise ValueError("capture source contract receipt is missing")
    if not contract_file_hash.startswith("sha256:") or len(contract_file_hash) != 71:
        raise ValueError("capture source contract file hash is invalid")
    if _sha256_file(contract_path) != contract_file_hash:
        raise ValueError("capture source contract file hash mismatch")
    if expected_contract_file_sha256 is not None and contract_file_hash != expected_contract_file_sha256:
        raise ValueError("capture source contract has changed since capture")
    if not contract_content_hash.startswith("sha256:") or len(contract_content_hash) != 71:
        raise ValueError("capture source contract content hash is invalid")
    contract_payload = _read_json(contract_path)
    contract_body = {
        key: value
        for key, value in contract_payload.items()
        if key not in {"contract_sha256", "checked_at"}
    }
    if contract_payload.get("contract_sha256") != _hash_payload(contract_body):
        raise ValueError("capture source contract self-hash mismatch")
    if contract_payload.get("contract_sha256") != contract_content_hash:
        raise ValueError("capture source contract content hash mismatch")
    if str(binding.get("decision_date") or "")[:10] != str(contract_payload.get("decision_date") or "")[:10]:
        raise ValueError("capture source contract decision identity mismatch")
    lanes = contract_payload.get("lanes")
    lanes = lanes if isinstance(lanes, Mapping) else {}
    price_up = lanes.get("price_up_calibration")
    price_up = price_up if isinstance(price_up, Mapping) else {}
    if price_up.get("prospective_status") != binding.get("price_up_prospective_status"):
        raise ValueError("capture source contract prospective status mismatch")
    if require_ready and price_up.get("prospective_status") != "ready":
        raise ValueError("capture source contract receipt is not ready")
    contract_symbols = {
        str(symbol).strip()
        for symbol in contract_payload.get("symbols", [])
        if str(symbol).strip()
    }
    binding_symbols = {
        str(symbol).strip()
        for symbol in binding.get("symbols", [])
        if str(symbol).strip()
    }
    if not contract_symbols or contract_symbols != binding_symbols:
        raise ValueError("capture source contract symbol identity mismatch")
    if capture_day is not None and str(binding.get("decision_date") or "")[:10] != capture_day.isoformat():
        raise ValueError("capture source contract decision cutoff mismatch")
    if capture_rows is not None:
        if capture_day is None:
            raise ValueError("capture source contract capture date is missing")
        capture_day_text = capture_day.isoformat()
        capture_symbols = {
            str(row.get("symbol") or "").strip()
            for row in capture_rows
            if str(row.get("symbol") or "").strip()
        }
        if capture_symbols != contract_symbols:
            raise ValueError("capture source contract does not cover capture symbols")
        if binding.get("capture_decision_date") != capture_day_text:
            raise ValueError("capture source contract capture date mismatch")
        if binding.get("capture_symbols") != sorted(capture_symbols):
            raise ValueError("capture source contract capture symbol fingerprint mismatch")
        if binding.get("feature_row_count") != len(capture_rows):
            raise ValueError("capture source contract feature row count mismatch")
        expected_fingerprint = _feature_snapshot_fingerprint(
            capture_day_text,
            capture_rows,
        )
        if binding.get("feature_snapshot_fingerprint") != expected_fingerprint:
            raise ValueError("capture source contract feature snapshot fingerprint mismatch")
        technical = contract_payload.get("technical")
        technical = technical if isinstance(technical, Mapping) else {}
        feature_snapshot = technical.get("prospective_feature_snapshot")
        if not isinstance(feature_snapshot, Mapping):
            raise ValueError("capture source contract feature snapshot missing")
        if not _verified_content_hash(feature_snapshot, "content_sha256"):
            raise ValueError("capture source contract feature snapshot hash mismatch")
        if binding.get("feature_snapshot_content_sha256") != feature_snapshot.get(
            "content_sha256"
        ):
            raise ValueError("capture source contract feature snapshot identity mismatch")
        expected_rows = feature_snapshot.get("rows")
        if not isinstance(expected_rows, list):
            raise ValueError("capture source contract feature snapshot rows missing")
        expected_by_symbol = {
            str(row.get("symbol") or ""): row
            for row in expected_rows
            if isinstance(row, Mapping) and str(row.get("symbol") or "")
        }
        actual_by_symbol = {
            str(row.get("symbol") or ""): row
            for row in capture_rows
            if str(row.get("symbol") or "")
        }
        if set(expected_by_symbol) != set(actual_by_symbol):
            raise ValueError("capture source contract feature symbol coverage mismatch")
        for symbol, actual in actual_by_symbol.items():
            expected = expected_by_symbol[symbol]
            for field_name in (
                "decision_date",
                "feature_as_of_date",
                "feature_available_date",
            ):
                if str(actual.get(field_name) or "")[:10] != str(expected.get(field_name) or "")[:10]:
                    raise ValueError(
                        "capture source contract feature timing/value identity mismatch"
                    )
            if list(actual.get("feature_values") or []) != list(
                expected.get("feature_values") or []
            ):
                raise ValueError("capture source contract feature values mismatch")
    technical = contract_payload.get("technical")
    technical = technical if isinstance(technical, Mapping) else {}
    feature_snapshot = technical.get("prospective_feature_snapshot")
    if not isinstance(feature_snapshot, Mapping):
        raise ValueError("capture source contract feature snapshot missing")
    if not _verified_content_hash(feature_snapshot, "content_sha256"):
        raise ValueError("capture source contract feature snapshot hash mismatch")
    if binding.get("feature_snapshot_content_sha256") != feature_snapshot.get(
        "content_sha256"
    ):
        raise ValueError("capture source contract feature snapshot identity mismatch")
    if capture_at is not None:
        _verify_source_availability(
            contract_payload,
            binding,
            capture_at=capture_at,
        )
    _verify_source_contract_dependencies(contract_payload, binding)


def _verify_source_availability(
    contract_payload: Mapping[str, Any],
    binding: Mapping[str, Any],
    *,
    capture_at: str,
) -> None:
    """Reject any source artifact that was unavailable at live capture time."""

    try:
        cutoff = _datetime(str(capture_at)).astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("capture source contract capture timestamp is invalid") from exc

    def require_available(
        label: str,
        value: object,
        *,
        binding_key: str | None = None,
    ) -> None:
        if value in (None, ""):
            raise ValueError(f"capture source contract {label} availability is missing")
        try:
            available_at = _datetime(str(value)).astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"capture source contract {label} availability is invalid") from exc
        if binding_key is not None:
            bound_value = binding.get(binding_key)
            if bound_value in (None, ""):
                raise ValueError(f"capture source contract {binding_key} is missing")
            try:
                bound_at = _datetime(str(bound_value)).astimezone(timezone.utc)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError(f"capture source contract {binding_key} is invalid") from exc
            if bound_at != available_at:
                raise ValueError(f"capture source contract {label} availability identity mismatch")
        if available_at > cutoff:
            raise ValueError(f"capture source contract {label} available after capture cutoff")

    technical = contract_payload.get("technical")
    technical = technical if isinstance(technical, Mapping) else {}
    require_available(
        "technical publication",
        technical.get("publication_available_at"),
        binding_key="technical_publication_available_at",
    )
    source_available_ats = technical.get("source_receipt_available_ats")
    if not isinstance(source_available_ats, list) or not source_available_ats:
        raise ValueError("capture source contract technical source availability is missing")
    bound_source_available_ats = binding.get("technical_source_available_ats")
    if not isinstance(bound_source_available_ats, list) or len(bound_source_available_ats) != len(source_available_ats):
        raise ValueError("capture source contract technical source availability identity is missing")
    for index, available_at in enumerate(source_available_ats):
        if _datetime(str(bound_source_available_ats[index])).astimezone(timezone.utc) != _datetime(
            str(available_at)
        ).astimezone(timezone.utc):
            raise ValueError("capture source contract technical source availability identity mismatch")
        require_available(f"technical source receipt {index}", available_at)

    feature_snapshot = technical.get("prospective_feature_snapshot")
    if not isinstance(feature_snapshot, Mapping):
        raise ValueError("capture source contract feature snapshot missing")
    require_available(
        "feature snapshot",
        feature_snapshot.get("captured_at"),
        binding_key="feature_snapshot_captured_at",
    )

    corporate = contract_payload.get("corporate_actions")
    corporate = corporate if isinstance(corporate, Mapping) else {}
    adjustment = corporate.get("adjustment_custody")
    adjustment = adjustment if isinstance(adjustment, Mapping) else {}
    require_available(
        "corporate adjustment manifest",
        adjustment.get("available_at"),
        binding_key="corporate_adjustment_available_at",
    )
    event_publication = corporate.get("event_publication")
    event_publication = event_publication if isinstance(event_publication, Mapping) else {}
    require_available(
        "official event publication",
        event_publication.get("source_publication_available_at"),
        binding_key="official_event_available_at",
    )


def _feature_snapshot_fingerprint(
    capture_day: str | date,
    rows: Sequence[Mapping[str, Any]],
) -> str:
    return _hash_payload(
        {
            "capture_decision_date": (
                capture_day.isoformat() if isinstance(capture_day, date) else str(capture_day)[:10]
            ),
            "rows": [
                {
                    "row_id": row.get("row_id"),
                    "symbol": row.get("symbol"),
                    "decision_date": row.get("decision_date"),
                    "feature_as_of_date": row.get("feature_as_of_date"),
                    "feature_available_date": row.get("feature_available_date"),
                    "feature_values": row.get("feature_values"),
                }
                for row in sorted(rows, key=lambda item: (str(item.get("row_id")), str(item.get("symbol"))))
            ],
        }
    )


def _verify_source_contract_dependencies(
    contract_payload: Mapping[str, Any],
    binding: Mapping[str, Any],
) -> None:
    """Re-check the immutable raw/technical/event lineage named by a contract."""

    technical = contract_payload.get("technical")
    technical = technical if isinstance(technical, Mapping) else {}
    publication = technical.get("publication_receipt")
    if not isinstance(publication, Mapping):
        raise ValueError("capture source contract technical publication lineage missing")
    publication_path = Path(str(publication.get("path") or "")).expanduser().resolve()
    if publication_path.is_symlink() or not publication_path.is_file():
        raise ValueError("capture source contract technical publication missing")
    if _sha256_file(publication_path) != publication.get("sha256"):
        raise ValueError("capture source contract technical publication hash mismatch")
    if (
        binding.get("technical_publication_receipt_file_sha256") is not None
        and binding.get("technical_publication_receipt_file_sha256") != publication.get("sha256")
    ):
        raise ValueError("capture source contract technical publication binding mismatch")
    publication_payload = _read_json(publication_path)
    if not _verified_payload_hash(publication_payload, "content_sha256"):
        raise ValueError("capture source contract technical publication content hash mismatch")
    technical_output = publication_payload.get("technical_output")
    if not isinstance(technical_output, Mapping) or not _verified_content_hash(
        technical_output, "content_sha256"
    ):
        raise ValueError("capture source contract technical output hash mismatch")
    if not isinstance(technical_output.get("rows_sha256"), str):
        raise ValueError("capture source contract technical output value hash missing")
    if publication_payload.get("technical_step_status") == "passed" and (
        publication_payload.get("technical_computation_evidence_status") != "verified"
        or not isinstance(publication_payload.get("technical_computation_evidence"), Mapping)
    ):
        raise ValueError("capture source contract technical computation witness missing")
    source_receipts = publication_payload.get("source_receipts")
    if not isinstance(source_receipts, list) or not source_receipts:
        raise ValueError("capture source contract technical source lineage missing")
    for reference in source_receipts:
        if not isinstance(reference, Mapping):
            raise ValueError("capture source contract daily receipt lineage invalid")
        receipt_path = Path(str(reference.get("receipt_path") or "")).expanduser().resolve()
        if receipt_path.is_symlink() or not receipt_path.is_file():
            raise ValueError("capture source contract daily receipt missing")
        if _sha256_file(receipt_path) != reference.get("receipt_sha256"):
            raise ValueError("capture source contract daily receipt hash mismatch")
        receipt_payload = _read_json(receipt_path)
        if not _verified_payload_hash(receipt_payload, "content_sha256"):
            raise ValueError("capture source contract daily receipt content hash mismatch")
        raw_path = Path(str(reference.get("raw_response_path") or "")).expanduser().resolve()
        if raw_path.is_symlink() or not raw_path.is_file() or not raw_path.is_relative_to(receipt_path.parent):
            raise ValueError("capture source contract raw response lineage invalid")
        if _sha256_file(raw_path) != reference.get("raw_response_sha256"):
            raise ValueError("capture source contract raw response hash mismatch")

    corporate = contract_payload.get("corporate_actions")
    corporate = corporate if isinstance(corporate, Mapping) else {}
    adjustment = corporate.get("adjustment_custody")
    adjustment = adjustment if isinstance(adjustment, Mapping) else {}
    if adjustment.get("prospective_verified") is not True:
        raise ValueError("capture source contract corporate adjustment custody is not ready")
    adjustment_path = Path(str(adjustment.get("manifest_path") or "")).expanduser().resolve()
    adjustment_file_hash = adjustment.get("manifest_file_hash")
    if adjustment_path.is_symlink() or not adjustment_path.is_file() or _sha256_file(adjustment_path) != adjustment_file_hash:
        raise ValueError("capture source contract adjustment manifest hash mismatch")
    if (
        binding.get("corporate_adjustment_manifest_hash") is not None
        and binding.get("corporate_adjustment_manifest_hash") != adjustment.get("manifest_hash")
    ):
        raise ValueError("capture source contract adjustment binding mismatch")
    adjustment_manifest = _read_json(adjustment_path)
    if not _verified_payload_hash(adjustment_manifest, "manifest_hash"):
        raise ValueError("capture source contract adjustment manifest content hash mismatch")
    adjustment_sections = (
        adjustment_manifest.get("adjustments"),
        adjustment_manifest.get("coverage"),
    )
    for section in adjustment_sections:
        if not isinstance(section, Mapping):
            raise ValueError("capture source contract adjustment section missing")
        section_path = (adjustment_path.parent / str(section.get("path") or "")).resolve()
        if section_path.is_symlink() or not section_path.is_file() or _sha256_file(section_path) != section.get("file_hash"):
            raise ValueError("capture source contract adjustment section hash mismatch")
    event_publication = corporate.get("event_publication")
    event_publication = event_publication if isinstance(event_publication, Mapping) else {}
    event_path = Path(str(event_publication.get("manifest_path") or "")).expanduser().resolve()
    if event_path.is_symlink() or not event_path.is_file() or _sha256_file(event_path) != event_publication.get("manifest_file_sha256"):
        raise ValueError("capture source contract event manifest hash mismatch")
    event_manifest = _read_json(event_path)
    if not _verified_payload_hash(event_manifest, "manifest_hash"):
        raise ValueError("capture source contract event manifest content hash mismatch")


def _verified_payload_hash(payload: Mapping[str, Any], field_name: str) -> bool:
    declared = payload.get(field_name)
    if not isinstance(declared, str) or not declared.startswith("sha256:"):
        return False
    body = {key: value for key, value in payload.items() if key != field_name}
    return _hash_payload(body) == declared


def _verify_active_model_capture_payload(payload: Mapping[str, Any]) -> None:
    """Verify an immutable active-model monitor capture before outcome use."""

    required = (
        "schema_version", "capture_id", "capture_as_of_date", "captured_at",
        "active_identity", "active_identity_hash", "active_candidate_id",
        "active_model_id", "active_candidate_root", "active_candidate_frozen_at",
        "active_manifest_hash", "active_artifact_hash", "active_freeze_hash",
        "active_pointer_version", "active_effective_date", "feature_registry_hash",
        "feature_schema_hash", "feature_schema", "label_registry_hash",
        "cost_contract_hash", "fixed_round_trip_cost_bp",
        "maximum_probability_change_bp", "policy_hash", "probability_transform_id",
        "probability_lineage", "rows", "capture_hash", "capture_origin",
    )
    if any(key not in payload for key in required):
        raise ValueError("active model capture metadata is incomplete")
    if payload.get("schema_version") != "recommendation-active-model-prediction-capture.v1":
        raise ValueError("active model capture schema is unsupported")
    body = {
        key: value
        for key, value in payload.items()
        if key not in {"capture_hash", "capture_path"}
    }
    if _hash_payload(body) != payload.get("capture_hash"):
        raise ValueError("active model capture hash mismatch")
    capture_day = _date(str(payload["capture_as_of_date"]))
    if _date(str(payload["captured_at"])) > capture_day:
        raise ValueError("active model capture timestamp is after decision cutoff")
    if _datetime(str(payload["active_candidate_frozen_at"])) > _datetime(str(payload["captured_at"])):
        raise ValueError("active candidate freeze is after monitoring capture")
    if payload.get("capture_origin") != "scheduled_active_monitor":
        raise ValueError("active model capture origin is invalid")
    identity = payload.get("active_identity")
    if not isinstance(identity, Mapping):
        raise ValueError("active model identity is invalid")
    if _hash_payload(identity) != payload.get("active_identity_hash"):
        raise ValueError("active model identity hash mismatch")
    for payload_key, identity_key in (
        ("active_candidate_id", "candidate_id"),
        ("active_model_id", "model_id"),
        ("active_candidate_root", "candidate_root"),
        ("active_manifest_hash", "candidate_manifest_hash"),
        ("active_artifact_hash", "candidate_artifact_hash"),
        ("active_freeze_hash", "candidate_freeze_hash"),
    ):
        if str(payload.get(payload_key) or "") != str(identity.get(identity_key) or ""):
            raise ValueError(f"active model identity mismatch: {payload_key}")
    if int(payload["active_pointer_version"]) < 0:
        raise ValueError("active model pointer version is invalid")
    lineage = payload.get("probability_lineage")
    if not isinstance(lineage, list) or not lineage:
        raise ValueError("active model probability lineage is missing")
    if payload.get("probability_transform_id") != PROBABILITY_TRANSFORM_ID:
        raise ValueError("active model probability transform is unsupported")
    identity_lineage = identity.get("probability_lineage")
    if identity_lineage != lineage:
        raise ValueError("active model probability lineage mismatch")
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("active model capture rows are missing")
    row_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("active model capture row is invalid")
        row_id = str(row.get("row_id") or "")
        if not row_id or row_id in row_ids:
            raise ValueError("active model capture row ids must be unique")
        row_ids.add(row_id)
        if _date(str(row.get("decision_date"))) != capture_day:
            raise ValueError("active model capture row decision date mismatch")
        if _date(str(row.get("feature_as_of_date"))) >= capture_day:
            raise ValueError("active model capture feature is not point-in-time")
        if _date(str(row.get("feature_available_date"))) > capture_day:
            raise ValueError("active model capture feature availability is after decision")
        for field_name in ("active_probability_bp", "active_raw_probability_bp"):
            value = row.get(field_name)
            if not isinstance(value, int):
                raise ValueError(f"active model capture {field_name} is missing")
            _probability(value, field_name)
        active_after_cost = row.get("active_after_cost_probability_bp")
        if active_after_cost is not None:
            _probability(int(active_after_cost), "active_after_cost_probability_bp")
        raw_after_cost = row.get("active_raw_after_cost_probability_bp")
        if raw_after_cost is not None:
            _probability(int(raw_after_cost), "active_raw_after_cost_probability_bp")
        if row.get("probability_transform_id") != payload.get("probability_transform_id"):
            raise ValueError("active model capture row probability transform mismatch")
        if row.get("probability_lineage") != lineage:
            raise ValueError("active model capture row probability lineage mismatch")


def _brier_bp(probabilities: Sequence[int], labels: Sequence[int]) -> int:
    return sum((int(probability) - int(label) * 10_000) ** 2 for probability, label in zip(probabilities, labels)) // (
        len(labels) * 10_000
    )


def _calibration_gap_bp(probabilities: Sequence[int], labels: Sequence[int]) -> int:
    return abs(sum(probabilities) // len(probabilities) - sum(labels) * 10_000 // len(labels))


def _probability(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10_000:
        raise ValueError(f"{field_name} must be an integer probability bp")


def _clamp_to_baseline(value: int | None, baseline: int | None, cap: int) -> int | None:
    if value is None or baseline is None:
        return None
    return max(0, min(10_000, max(int(baseline) - cap, min(int(baseline) + cap, int(value)))))


def _date(value: str) -> date:
    return date.fromisoformat(str(value)[:10])


def _datetime(value: str) -> datetime:
    text = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _hash_payload(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _verified_content_hash(payload: Mapping[str, Any], field_name: str) -> bool:
    declared = payload.get(field_name)
    if not isinstance(declared, str) or not declared.startswith("sha256:"):
        return False
    body = {key: value for key, value in payload.items() if key != field_name}
    return _hash_payload(body) == declared


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def _write_json_once(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = _read_json(path)
        if existing != payload:
            raise RuntimeError("immutable JSON receipt conflict")
        return
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _library_versions() -> dict[str, str]:
    import joblib
    import sklearn

    return {"joblib": str(joblib.__version__), "numpy": str(np.__version__), "scikit-learn": str(sklearn.__version__)}
