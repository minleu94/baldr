"""Shadow-only daily recommendation learning orchestration。

這是 learning producer 的 canonical ML 邊界。它只讀取 caller 提供的 samples 與
dependency metadata，在隔離 Shadow root 產生 candidate、training lineage、run
receipt 與既有 authority decision；不讀寫正式資料庫、不寫 order state，也不
import ``app_module``。scheduled entrypoint 直接依賴本模組的 canonical runner，
保留既有 ``DailyRecommendationLearningRunner`` 的呼叫形狀。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from ml_module.model_artifact_manifest import FeatureSchema
from ml_module.recommendation_calibration_authority import (
    RecommendationCalibrationPromotionAuthority,
)
from ml_module.recommendation_calibration_training import (
    RecommendationCalibrationSample,
    RecommendationCalibrationTrainingConfig,
    RecommendationCalibrationTrainingResult,
    RecommendationCalibrationTrainingService,
    sample_payload,
)
from ml_module.recommendation_cost_scenario import (
    RecommendationCostScenario,
    RecommendationCostScenarioError,
    normalize_cost_scenario,
)
from ml_module.recommendation_training_lineage import (
    RECOMMENDATION_TRAINING_CONTEXT_HISTORICAL_RESEARCH,
    RecommendationTrainingLineageError,
    build_recommendation_training_lineage,
    persist_recommendation_training_lineage,
    recommendation_training_dataset_hash,
    resolve_recommendation_training_context,
    read_recommendation_training_lineage,
)


DEFAULT_DATA_ROOT = Path("D:/Min/Python/Project/FA_Data")
RECOMMENDATION_LEARNING_OUTPUT_ROOT_ENV = "RECOMMENDATION_LEARNING_OUTPUT_ROOT"


@dataclass(frozen=True)
class DailyRecommendationLearningResult:
    """每日 bounded runner 的簡潔結果 contract。"""

    run_id: str
    status: str
    reason: str
    receipt_path: str
    latest_status_path: str
    dataset_id: str | None
    dataset_hash: str | None
    candidate_id: str | None
    decision: str
    decision_reason: str
    idempotent_replay: bool = False
    candidate_root: str | None = None
    training_lineage_manifest_hash: str | None = None
    training_lineage_manifest_path: str | None = None
    training_lineage_status: str = "not_available"


class DailyRecommendationLearningRunner:
    """在 ML／Shadow namespace 內執行一個可恢復的 learning day。"""

    def __init__(
        self,
        *,
        output_root: str | Path,
        feature_names: tuple[str, ...],
        feature_schema: FeatureSchema,
        feature_registry_hash: str,
        fixed_round_trip_cost_bp: int | None,
        cost_scenario: RecommendationCostScenario | Mapping[str, Any] | None = None,
        data_root: str | Path | None = None,
        training_config: RecommendationCalibrationTrainingConfig | None = None,
        training_service: RecommendationCalibrationTrainingService | None = None,
        authority: RecommendationCalibrationPromotionAuthority | None = None,
    ) -> None:
        resolved_output_root = _resolve_shadow_output_root(output_root, data_root=data_root)
        self.root = resolved_output_root / "recommendation_learning"
        self.runs_root = self.root / "runs"
        self.feature_names = feature_names
        self.feature_schema = feature_schema
        self.feature_registry_hash = feature_registry_hash
        try:
            self.cost_scenario = normalize_cost_scenario(
                cost_scenario,
                fixed_round_trip_cost_bp=fixed_round_trip_cost_bp,
            )
        except RecommendationCostScenarioError as exc:
            raise ValueError(str(exc)) from exc
        if self.cost_scenario.is_estimated and fixed_round_trip_cost_bp is not None:
            raise ValueError("estimated runner must not carry fixed_round_trip_cost_bp")
        self.fixed_round_trip_cost_bp = self.cost_scenario.fixed_round_trip_cost_bp
        self.training_config = training_config or RecommendationCalibrationTrainingConfig()
        self.training_service = training_service or RecommendationCalibrationTrainingService()
        self.authority = authority or RecommendationCalibrationPromotionAuthority(self.root)

    def run(
        self,
        *,
        decision_date: str,
        run_scope: str | None = None,
        samples: Sequence[RecommendationCalibrationSample],
        natural_evidence: Any,
        data_dependency_status: str = "ready",
        outcome_dependency_status: str = "ready",
        drift_status: str = "not_checked",
        dataset_quality: Mapping[str, Any] | None = None,
        training_as_of: str | None = None,
        frozen_candidate_root: str | Path | None = None,
        fault_after_candidate: bool = False,
        emergency_rollback: bool = False,
        dependency_failure_reason: str | None = None,
        lineage_sources: Mapping[str, Sequence[RecommendationCalibrationSample]] | None = None,
    ) -> DailyRecommendationLearningResult:
        """訓練、固化 lineage、寫 candidate/run receipt 並交給 authority。"""

        day = _date_text(decision_date, "decision_date")
        scope = _safe_run_scope(run_scope)
        run_id = f"daily-recommendation-learning:{day}" + (f":{scope}" if scope else "")
        run_dir = _scoped_run_dir(self.runs_root, day, scope)
        receipt_path = run_dir / "run_receipt.json"
        latest_path = self.root / "latest_status.json"
        training_cutoff = day if training_as_of is None else _date_text(training_as_of, "training_as_of")
        eligible_samples = tuple(
            row
            for row in samples
            if _date_text(row.decision_date, "sample.decision_date") <= training_cutoff
            and _date_text(row.label_available_date, "sample.label_available_date") <= training_cutoff
        )
        dataset_hash = _dataset_hash(eligible_samples)

        if receipt_path.is_file() and not emergency_rollback:
            existing = _read_mapping(receipt_path)
            if existing.get("status") == "completed" and existing.get("finalized") is True:
                if (
                    natural_evidence is not None
                    and existing.get("decision") == "retain_current"
                    and existing.get("candidate_root")
                    and existing.get("candidate_id")
                ):
                    candidate_root = Path(str(existing["candidate_root"])).resolve()
                    candidate_path = candidate_root / "candidate.json"
                    if candidate_path.is_file():
                        candidate_metadata = _read_mapping(candidate_path)
                        if callable(natural_evidence):
                            raise ValueError(
                                "same-day evidence retry requires a materialized receipt reference"
                            )
                        retry_decision = self.authority.evaluate_and_apply(
                            decision_date=day,
                            candidate_id=str(existing["candidate_id"]),
                            candidate_root=candidate_root,
                            candidate_metadata=candidate_metadata,
                            natural_evidence=natural_evidence,
                            data_status=data_dependency_status,
                            drift_status=drift_status,
                        )
                        retry_path = run_dir / (
                            f"run_receipt-retry-{_evidence_id(natural_evidence)}.json"
                        )
                        retry_receipt = {
                            **existing,
                            "receipt_path": str(retry_path),
                            "reason": "same_day_natural_evidence_retry",
                            "natural_matured_sample_count": _evidence_count(natural_evidence),
                            "decision": retry_decision.decision,
                            "decision_reason": retry_decision.reason,
                            "decision_receipt": retry_decision.to_dict(),
                            "steps": {
                                **dict(existing.get("steps", {})),
                                "same_date_same_cost_comparison": (
                                    "recomputed_from_materialized_natural_receipt"
                                ),
                                "promotion_gate": "completed",
                            },
                        }
                        _write_json_once(retry_path, retry_receipt)
                        _write_json(latest_path, retry_receipt)
                        return _result_from_receipt(
                            retry_receipt,
                            idempotent=False,
                            latest_status_path=latest_path,
                        )
                return _result_from_receipt(existing, idempotent=True, latest_status_path=latest_path)

        if emergency_rollback:
            decision = self.authority.evaluate_and_apply(
                decision_date=day,
                candidate_id=None,
                candidate_root=None,
                candidate_metadata=None,
                natural_evidence=None,
                data_status=data_dependency_status,
                drift_status=drift_status,
                emergency_rollback=True,
            )
            emergency_receipt_path = run_dir / "run_receipt-emergency-rollback.json"
            receipt = {
                "schema_version": "daily-recommendation-learning-receipt.v1",
                "run_id": run_id,
                "run_scope": scope,
                "decision_date": day,
                "receipt_path": str(emergency_receipt_path),
                "status": "completed",
                "finalized": True,
                "recoverable": False,
                "dependency_failure_reason": dependency_failure_reason,
                **_scenario_receipt_metadata(self.cost_scenario),
                "reason": "explicit_emergency_rollback_evaluated_without_new_candidate",
                "dataset_id": None,
                "dataset_hash": dataset_hash,
                "candidate_id": None,
                "training_lineage_status": "skipped",
                "natural_matured_sample_count": 0,
                "data_dependency_status": data_dependency_status,
                "outcome_dependency_status": outcome_dependency_status,
                "drift_status": drift_status,
                "decision": decision.decision,
                "decision_reason": decision.reason,
                "next_step": _next_step(decision.decision, decision.reason),
                "decision_receipt": decision.to_dict(),
                "steps": {
                    "dependency_check": "failed_emergency_path",
                    "dataset_build": "skipped",
                    "candidate_training": "skipped",
                    "training_lineage": "skipped",
                    "same_date_same_cost_comparison": "skipped",
                    "promotion_gate": "completed_rollback_or_rule_only",
                },
                "formal_order_allowed": False,
                "shadow_only": True,
            }
            _write_json_once(emergency_receipt_path, receipt)
            _write_json(latest_path, receipt)
            return _result_from_receipt(receipt, idempotent=False, latest_status_path=latest_path)

        if data_dependency_status.lower() not in {"ready", "observed", "not_checked"}:
            return self._write_skip(
                day=day,
                run_id=run_id,
                run_dir=run_dir,
                run_scope=scope,
                reason=dependency_failure_reason or "data_dependency_failed_fail_closed",
                status="failed_dependency",
                dataset_hash=dataset_hash,
                decision="retain_current",
                decision_reason="data_dependency_failed_fail_closed",
                natural_matured_sample_count=_evidence_count(natural_evidence),
                data_dependency_status=data_dependency_status,
                outcome_dependency_status=outcome_dependency_status,
                drift_status=drift_status,
            )
        if outcome_dependency_status.lower() not in {"ready", "observed", "not_checked"}:
            return self._write_skip(
                day=day,
                run_id=run_id,
                run_dir=run_dir,
                run_scope=scope,
                reason=(
                    dependency_failure_reason
                    or "outcome_dependency_unavailable_natural_evidence_not_fabricated"
                ),
                status="skipped_insufficient_evidence",
                dataset_hash=dataset_hash,
                decision="retain_current",
                decision_reason="outcome_dependency_unavailable_natural_evidence_not_fabricated",
                natural_matured_sample_count=_evidence_count(natural_evidence),
                data_dependency_status=data_dependency_status,
                outcome_dependency_status=outcome_dependency_status,
                drift_status=drift_status,
            )

        try:
            training_semantics, decision_time_eligible = resolve_recommendation_training_context(
                decision_date=day,
                training_as_of=training_cutoff,
                dataset_quality=dataset_quality,
            )
        except RecommendationTrainingLineageError as exc:
            return self._write_skip(
                day=day,
                run_id=run_id,
                run_dir=run_dir,
                run_scope=scope,
                reason=f"training_cutoff_invalid:{_compact_exception_text(exc)}",
                status="failed_training",
                dataset_hash=dataset_hash,
                decision="retain_current",
                decision_reason="training_cutoff_invalid_fail_closed",
                natural_matured_sample_count=_evidence_count(natural_evidence),
                data_dependency_status=data_dependency_status,
                outcome_dependency_status=outcome_dependency_status,
                drift_status=drift_status,
                training_diagnostics=_training_sample_diagnostics(
                    eligible_samples,
                    training_as_of=training_cutoff,
                    dataset_quality=dataset_quality,
                ),
                training_lineage_status="failed",
            )

        frozen_root = Path(frozen_candidate_root).resolve() if frozen_candidate_root is not None else None
        frozen_metadata: dict[str, Any] | None = None
        if frozen_root is not None:
            try:
                frozen_metadata = _read_mapping(frozen_root / "candidate.json")
                _validate_frozen_candidate(frozen_metadata, self.cost_scenario, self.fixed_round_trip_cost_bp)
            except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
                return self._write_skip(
                    day=day,
                    run_id=run_id,
                    run_dir=run_dir,
                    run_scope=scope,
                    reason=f"frozen_challenger_unavailable:{type(exc).__name__}",
                    status="failed_candidate",
                    dataset_hash=dataset_hash,
                    decision="retain_current",
                    decision_reason="frozen_challenger_unavailable_fail_closed",
                    natural_matured_sample_count=_evidence_count(natural_evidence),
                    data_dependency_status=data_dependency_status,
                    outcome_dependency_status=outcome_dependency_status,
                    drift_status=drift_status,
                )

        if not eligible_samples and frozen_root is None:
            return self._write_skip(
                day=day,
                run_id=run_id,
                run_dir=run_dir,
                run_scope=scope,
                reason="no_new_matured_or_historical_rows",
                status="skipped_no_data",
                dataset_hash=dataset_hash,
                decision="retain_current",
                decision_reason="no_new_matured_or_historical_rows",
                natural_matured_sample_count=_evidence_count(natural_evidence),
                data_dependency_status=data_dependency_status,
                outcome_dependency_status=outcome_dependency_status,
                drift_status=drift_status,
            )

        dataset_id = f"recommendation-dataset-{dataset_hash[7:23]}"
        result: RecommendationCalibrationTrainingResult | None = None
        lineage_hash: str | None = None
        lineage_path: str | None = None
        lineage_status = "not_available"
        if frozen_root is None:
            try:
                result = self.training_service.fit(
                    dataset_id=dataset_id,
                    dataset_hash=dataset_hash,
                    samples=eligible_samples,
                    feature_names=self.feature_names,
                    feature_schema=self.feature_schema,
                    feature_registry_hash=self.feature_registry_hash,
                    training_as_of=training_cutoff,
                    fixed_round_trip_cost_bp=self.fixed_round_trip_cost_bp,
                    cost_scenario=self.cost_scenario,
                    dataset_quality=dataset_quality,
                    created_at=f"{day}T00:00:00+00:00",
                    config=self.training_config,
                )
                lineage = build_recommendation_training_lineage(
                    learning_root=self.root,
                    run_id=run_id,
                    run_scope=scope,
                    decision_date=day,
                    training_as_of=training_cutoff,
                    dataset_id=dataset_id,
                    dataset_hash=dataset_hash,
                    samples=eligible_samples,
                    feature_schema=self.feature_schema,
                    feature_registry_hash=self.feature_registry_hash,
                    fixed_round_trip_cost_bp=self.fixed_round_trip_cost_bp,
                    cost_scenario=self.cost_scenario,
                    dataset_quality=dataset_quality,
                    training_result=result,
                    training_config=self.training_config,
                    candidate_id=result.candidate_id,
                    candidate_manifest_hash=result.manifest.manifest_hash,
                    candidate_artifact_hash=result.artifact_hash,
                    source_groups=lineage_sources,
                )
                persisted_lineage_path = persist_recommendation_training_lineage(self.root, lineage)
                lineage_hash = lineage.manifest_hash
                lineage_path = str(persisted_lineage_path)
                lineage_status = "verified"
                candidate_root = run_dir / "candidates" / result.candidate_id
                candidate_payload = result.to_dict()
                candidate_payload.update(
                    {
                        "training_lineage_manifest_hash": lineage_hash,
                        "training_lineage_manifest_path": lineage_path,
                        "training_source_hash": lineage.payload.get("training_source_hash"),
                        "training_pit_hash": lineage.payload.get("training_pit_hash"),
                        "feature_registry_hash": lineage.payload.get("feature_registry_hash"),
                        "feature_transform_contract": lineage.payload.get(
                            "feature_transform_contract"
                        ),
                        "feature_transform_contract_hash": (
                            lineage.payload.get("feature_transform_contract", {}).get("contract_hash")
                            if isinstance(lineage.payload.get("feature_transform_contract"), Mapping)
                            else None
                        ),
                        "training_cutoff": training_cutoff,
                        "training_semantics": training_semantics,
                        "decision_time_eligible": decision_time_eligible,
                        "research_only": (
                            training_semantics
                            == RECOMMENDATION_TRAINING_CONTEXT_HISTORICAL_RESEARCH
                        ),
                    }
                )
                _persist_candidate_package(result, candidate_root, candidate_payload)
                candidate_metadata = candidate_payload
            except (OSError, RuntimeError, TypeError, ValueError, RecommendationTrainingLineageError) as exc:
                reason = (
                    f"candidate_training_failed:{type(exc).__name__}:"
                    f"{_compact_exception_text(exc)}"
                    if result is None
                    else f"training_lineage_failed:{type(exc).__name__}:{_compact_exception_text(exc)}"
                )
                return self._write_skip(
                    day=day,
                    run_id=run_id,
                    run_dir=run_dir,
                    run_scope=scope,
                    reason=reason,
                    status="failed_training" if result is None else "failed_lineage",
                    dataset_hash=dataset_hash,
                    decision="retain_current",
                    decision_reason=(
                        "candidate_training_failed_fail_closed"
                        if result is None
                        else "training_lineage_failed_fail_closed"
                    ),
                    natural_matured_sample_count=_evidence_count(natural_evidence),
                    data_dependency_status=data_dependency_status,
                    outcome_dependency_status=outcome_dependency_status,
                    drift_status=drift_status,
                    training_diagnostics=_training_sample_diagnostics(
                        eligible_samples,
                        training_as_of=training_cutoff,
                        dataset_quality=dataset_quality,
                    ),
                    training_lineage_status="failed",
                )
        else:
            candidate_root = frozen_root
            candidate_metadata = frozen_metadata or {}
            try:
                lineage_hash, lineage_path, lineage_status = _frozen_candidate_lineage(
                    candidate_root,
                    candidate_metadata,
                )
            except (OSError, UnicodeError, TypeError, ValueError, RecommendationTrainingLineageError) as exc:
                return self._write_skip(
                    day=day,
                    run_id=run_id,
                    run_dir=run_dir,
                    run_scope=scope,
                    reason=f"frozen_candidate_lineage_invalid:{type(exc).__name__}",
                    status="failed_lineage",
                    dataset_hash=dataset_hash,
                    decision="retain_current",
                    decision_reason="frozen_candidate_lineage_invalid_fail_closed",
                    natural_matured_sample_count=_evidence_count(natural_evidence),
                    data_dependency_status=data_dependency_status,
                    outcome_dependency_status=outcome_dependency_status,
                    drift_status=drift_status,
                    training_lineage_status="invalid",
                )

        candidate_id = str(candidate_metadata.get("candidate_id") or "")
        if fault_after_candidate:
            raise RuntimeError("injected_fault_after_candidate")
        resolved_evidence = (
            natural_evidence(result, candidate_metadata)
            if callable(natural_evidence)
            else natural_evidence
        )
        decision = self.authority.evaluate_and_apply(
            decision_date=day,
            candidate_id=candidate_id,
            candidate_root=candidate_root,
            candidate_metadata=candidate_metadata,
            natural_evidence=resolved_evidence,
            data_status=data_dependency_status,
            drift_status=drift_status,
            emergency_rollback=emergency_rollback,
        )
        quality = dataset_quality if isinstance(dataset_quality, Mapping) else {}
        historical_bootstrap = quality.get("historical_bootstrap")
        historical_bootstrap = (
            dict(historical_bootstrap) if isinstance(historical_bootstrap, Mapping) else None
        )
        receipt = {
            "schema_version": "daily-recommendation-learning-receipt.v1",
            "run_id": run_id,
            "run_scope": scope,
            "decision_date": day,
            "receipt_path": str(receipt_path),
            "status": "completed",
            "finalized": True,
            "recoverable": False,
            "reason": "candidate_trained_and_gate_evaluated",
            "dataset_id": dataset_id,
            "dataset_hash": dataset_hash,
            "training_as_of": training_cutoff,
            "training_semantics": training_semantics,
            "decision_time_eligible": decision_time_eligible,
            "research_only": (
                training_semantics == RECOMMENDATION_TRAINING_CONTEXT_HISTORICAL_RESEARCH
            ),
            **_scenario_receipt_metadata(self.cost_scenario),
            "candidate_id": candidate_id,
            "candidate_root": str(candidate_root),
            "candidate_manifest_hash": candidate_metadata.get("manifest_hash"),
            "candidate_artifact_hash": candidate_metadata.get("artifact_hash"),
            "candidate_freeze_hash": candidate_metadata.get("candidate_freeze_hash"),
            "candidate_dataset_id": candidate_metadata.get("dataset_id"),
            "candidate_dataset_hash": candidate_metadata.get("dataset_hash"),
            "training_lineage_manifest_hash": lineage_hash,
            "training_lineage_manifest_path": lineage_path,
            "training_lineage_status": lineage_status,
            "training_source_hash": candidate_metadata.get("training_source_hash"),
            "training_pit_hash": candidate_metadata.get("training_pit_hash"),
            "feature_transform_contract_hash": candidate_metadata.get(
                "feature_transform_contract_hash"
            ),
            "training_row_count": (
                result.training_row_count if result is not None else candidate_metadata.get("training_row_count")
            ),
            "calibration_sample_count": (
                result.model.calibration_sample_count
                if result is not None
                else candidate_metadata.get("calibration_sample_count")
            ),
            "calibration_gap_bp": (
                result.calibration_gap_bp if result is not None else candidate_metadata.get("calibration_gap_bp")
            ),
            "evaluation": (
                dict(result.evaluation)
                if result is not None
                else dict(candidate_metadata.get("evaluation", {}))
            ),
            "training_diagnostics": _training_sample_diagnostics(
                eligible_samples,
                training_as_of=training_cutoff,
                dataset_quality=dataset_quality,
            ),
            "historical_bootstrap": historical_bootstrap,
            "natural_matured_sample_count": _evidence_count(resolved_evidence),
            "data_dependency_status": data_dependency_status,
            "outcome_dependency_status": outcome_dependency_status,
            "drift_status": drift_status,
            "decision": decision.decision,
            "decision_reason": decision.reason,
            "next_step": _next_step(decision.decision, decision.reason),
            "decision_receipt": decision.to_dict(),
            "steps": {
                "dependency_check": "completed",
                "dataset_build": "completed",
                "candidate_training": "completed" if result is not None else "reused_frozen_challenger",
                "training_lineage": (
                    "completed"
                    if lineage_status == "verified"
                    else "legacy_unproven"
                    if lineage_status == "legacy_unproven"
                    else "not_available_for_frozen_challenger"
                ),
                "same_date_same_cost_comparison": "completed",
                "promotion_gate": "completed",
            },
            "formal_order_allowed": False,
            "shadow_only": True,
        }
        _write_json_once(receipt_path, receipt)
        _write_json(latest_path, receipt)
        return _result_from_receipt(receipt, idempotent=False, latest_status_path=latest_path)

    def _write_skip(
        self,
        *,
        day: str,
        run_id: str,
        run_dir: Path,
        run_scope: str | None,
        reason: str,
        status: str,
        dataset_hash: str,
        decision: str,
        decision_reason: str,
        natural_matured_sample_count: int,
        data_dependency_status: str,
        outcome_dependency_status: str,
        drift_status: str,
        training_diagnostics: Mapping[str, Any] | None = None,
        training_lineage_status: str = "not_available",
    ) -> DailyRecommendationLearningResult:
        attempt_id = "attempt-" + hashlib.sha256(
            f"{run_id}|{status}|{reason}|{dataset_hash}".encode("utf-8")
        ).hexdigest()[:24]
        receipt_path = run_dir / "attempts" / f"{attempt_id}.json"
        latest_path = self.root / "latest_status.json"
        receipt = {
            "schema_version": "daily-recommendation-learning-receipt.v1",
            "run_id": run_id,
            "run_scope": run_scope,
            "decision_date": day,
            "receipt_path": str(receipt_path),
            "attempt_id": attempt_id,
            "finalized": False,
            "recoverable": True,
            "status": status,
            "reason": reason,
            "training_diagnostics": dict(training_diagnostics or {}),
            "dataset_id": None,
            "dataset_hash": dataset_hash,
            "candidate_id": None,
            "training_lineage_manifest_hash": None,
            "training_lineage_manifest_path": None,
            "training_lineage_status": training_lineage_status,
            "natural_matured_sample_count": natural_matured_sample_count,
            "data_dependency_status": data_dependency_status,
            "outcome_dependency_status": outcome_dependency_status,
            "drift_status": drift_status,
            **_scenario_receipt_metadata(self.cost_scenario),
            "decision": decision,
            "decision_reason": decision_reason,
            "next_step": _next_step(decision, decision_reason),
            "steps": {
                "dependency_check": "completed",
                "dataset_build": "skipped",
                "candidate_training": "skipped",
                "training_lineage": (
                    "failed"
                    if training_lineage_status in {"failed", "invalid"}
                    else "skipped"
                ),
                "same_date_same_cost_comparison": "skipped",
                "promotion_gate": "completed_retain_current",
            },
            "formal_order_allowed": False,
            "shadow_only": True,
        }
        receipt_path = _write_recoverable_attempt(receipt_path, receipt)
        _write_json(latest_path, receipt)
        return _result_from_receipt(receipt, idempotent=False, latest_status_path=latest_path)


def _resolve_shadow_output_root(output_root: str | Path, *, data_root: str | Path | None) -> Path:
    raw_output = Path(output_root)
    if not raw_output.is_absolute():
        raise ValueError("recommendation learning output root must be absolute")
    formal_root = Path(data_root or os.environ.get("DATA_ROOT") or DEFAULT_DATA_ROOT).resolve()
    resolved = raw_output.resolve()
    if resolved == formal_root or formal_root in resolved.parents:
        raise ValueError(
            "recommendation learning output root is unsafe: it must be outside DATA_ROOT"
        )
    return resolved


def _persist_candidate_package(
    result: RecommendationCalibrationTrainingResult,
    candidate_root: Path,
    candidate_payload: Mapping[str, Any],
) -> None:
    root = candidate_root.resolve()
    if root.exists() and any(root.iterdir()):
        raise FileExistsError(f"candidate directory already contains files: {root}")
    root.mkdir(parents=True, exist_ok=True)
    (root / result.manifest.artifact_filename).write_bytes(result.artifact_bytes)
    _write_json_once(root / "manifest.json", result.manifest.to_dict())
    _write_json_once(root / "candidate.json", candidate_payload)


def _validate_frozen_candidate(
    payload: Mapping[str, Any],
    scenario: RecommendationCostScenario,
    fixed_round_trip_cost_bp: int | None,
) -> None:
    if not payload.get("candidate_id"):
        raise ValueError("frozen challenger identity is missing")
    declared_hash = str(payload.get("cost_scenario_hash") or "")
    declared_basis = str(payload.get("cost_basis") or "")
    if scenario.is_estimated:
        if declared_hash != scenario.scenario_hash:
            raise ValueError("frozen challenger cost scenario does not match runner lane")
        return
    if declared_hash and declared_hash != scenario.scenario_hash:
        raise ValueError("frozen challenger legacy cost scenario does not match runner lane")
    if declared_basis and declared_basis != "fixed_round_trip_bp":
        raise ValueError("frozen challenger legacy cost basis is invalid")
    declared_fixed = payload.get("fixed_round_trip_cost_bp")
    if declared_fixed is not None and int(declared_fixed) != int(fixed_round_trip_cost_bp or 0):
        raise ValueError("frozen challenger legacy fixed cost does not match runner lane")


def _frozen_candidate_lineage(
    candidate_root: Path,
    candidate_metadata: Mapping[str, Any],
) -> tuple[str | None, str | None, str]:
    """Verify declared lineage; leave pre-lineage candidates explicitly unproven."""

    hash_declared = "training_lineage_manifest_hash" in candidate_metadata
    path_declared = "training_lineage_manifest_path" in candidate_metadata
    lineage_hash = _optional_text(candidate_metadata.get("training_lineage_manifest_hash"))
    lineage_path_text = _optional_text(candidate_metadata.get("training_lineage_manifest_path"))
    if not hash_declared and not path_declared:
        return None, None, "legacy_unproven"
    if not lineage_hash or not lineage_path_text:
        raise RecommendationTrainingLineageError(
            "frozen candidate lineage declaration is incomplete"
        )
    lineage_path = Path(lineage_path_text)
    if not lineage_path.is_absolute():
        lineage_path = (candidate_root / lineage_path).resolve()
    read_recommendation_training_lineage(
        lineage_path,
        expected_manifest_hash=lineage_hash,
        expected_dataset_hash=_optional_text(candidate_metadata.get("dataset_hash")),
        expected_candidate_id=_optional_text(candidate_metadata.get("candidate_id")),
    )
    return lineage_hash, str(lineage_path), "verified"


def _dataset_hash(samples: Sequence[RecommendationCalibrationSample]) -> str:
    return recommendation_training_dataset_hash(samples)


def _training_sample_diagnostics(
    samples: Sequence[RecommendationCalibrationSample],
    *,
    training_as_of: str,
    dataset_quality: Mapping[str, Any] | None,
) -> dict[str, Any]:
    decision_dates = sorted({str(row.decision_date)[:10] for row in samples})
    source_quality: dict[str, int] = {}
    for row in samples:
        value = str(getattr(row, "source_quality", "unknown") or "unknown")
        source_quality[value] = source_quality.get(value, 0) + 1
    quality = dataset_quality if isinstance(dataset_quality, Mapping) else {}
    replay_coverage = quality.get("replay_coverage")
    replay_coverage = replay_coverage if isinstance(replay_coverage, Mapping) else {}
    return {
        "eligible_sample_count": len(samples),
        "eligible_decision_date_count": len(decision_dates),
        "eligible_decision_date_start": decision_dates[0] if decision_dates else None,
        "eligible_decision_date_end": decision_dates[-1] if decision_dates else None,
        "source_quality_distribution": dict(sorted(source_quality.items())),
        "bootstrap_selection": {
            "training_as_of": training_as_of,
            "selection_method": "caller_merged_samples_with_immutable_lineage",
            "replay_selection_policy": quality.get("replay_selection_policy"),
            "replay_max_decision_dates": replay_coverage.get("max_decision_dates"),
            "replay_selected_decision_date_count": replay_coverage.get("selected_decision_date_count"),
            "replay_sample_count": quality.get("replay_sample_count"),
            "natural_sample_count": quality.get("natural_training_sample_count"),
        },
    }


def _scenario_receipt_metadata(scenario: RecommendationCostScenario) -> dict[str, Any]:
    metadata = scenario.to_dict()
    return {
        "cost_scenario_id": metadata.get("scenario_id"),
        "cost_scenario_version": metadata.get("scenario_version"),
        "cost_scenario_hash": metadata.get("scenario_hash"),
        "cost_basis": metadata.get("cost_basis"),
        "cost_policy_id": metadata.get("policy_id"),
        "cost_policy_version": metadata.get("policy_version"),
        "policy_estimate_date": metadata.get("policy_estimate_date"),
        "research_order_amount_twd": metadata.get("research_order_amount_twd"),
        "research_order_quantity_shares": metadata.get("research_order_quantity_shares"),
        "lot_type": metadata.get("lot_type"),
        "instrument_type": metadata.get("instrument_type"),
        "cost_scenario": metadata,
    }


def _read_mapping(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"JSON payload must be an object: {path}")
    return dict(payload)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _write_json_once(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = _read_mapping(path)
        if existing != dict(payload):
            raise RuntimeError(f"immutable daily recommendation receipt conflict: {path}")
        return
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_recoverable_attempt(path: Path, payload: dict[str, Any]) -> Path:
    """Keep a prior recoverable attempt immutable while allowing a retry."""

    try:
        _write_json_once(path, payload)
        return path
    except RuntimeError as exc:
        if not str(exc).startswith("immutable daily recommendation receipt conflict:"):
            raise
    identity = {
        key: value
        for key, value in payload.items()
        if key not in {"attempt_id", "receipt_path"}
    }
    suffix = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:12]
    attempt_id = f"{payload['attempt_id']}-{suffix}"
    retry_path = path.with_name(f"{attempt_id}.json")
    payload["attempt_id"] = attempt_id
    payload["receipt_path"] = str(retry_path)
    _write_json_once(retry_path, payload)
    return retry_path


def _result_from_receipt(
    payload: Mapping[str, Any],
    *,
    idempotent: bool,
    latest_status_path: Path,
) -> DailyRecommendationLearningResult:
    return DailyRecommendationLearningResult(
        run_id=str(payload.get("run_id") or ""),
        status=str(payload.get("status") or ""),
        reason=str(payload.get("reason") or ""),
        receipt_path=str(payload.get("receipt_path") or ""),
        latest_status_path=str(latest_status_path),
        dataset_id=payload.get("dataset_id"),
        dataset_hash=payload.get("dataset_hash"),
        candidate_id=payload.get("candidate_id"),
        decision=str(payload.get("decision") or "retain_current"),
        decision_reason=str(payload.get("decision_reason") or ""),
        idempotent_replay=idempotent,
        candidate_root=payload.get("candidate_root"),
        training_lineage_manifest_hash=payload.get("training_lineage_manifest_hash"),
        training_lineage_manifest_path=payload.get("training_lineage_manifest_path"),
        training_lineage_status=str(payload.get("training_lineage_status") or "not_available"),
    )


def _date_text(value: str, field_name: str) -> str:
    text = str(value or "")[:10]
    try:
        return date.fromisoformat(text).isoformat()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} is not ISO date") from exc


def _safe_run_scope(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    safe = "".join(char if char.isalnum() or char in {"-", "_", "."} else "-" for char in text)
    return safe.strip("-._") or None


def _scoped_run_dir(runs_root: Path, day: str, scope: str | None) -> Path:
    base = runs_root / day
    if not scope:
        return base
    scoped = base / scope
    if len(str(scoped)) > 170:
        directory_hash = hashlib.sha256(scope.encode("utf-8")).hexdigest()[:16]
        return base / f"scope-{directory_hash}"
    return scoped


def _evidence_count(evidence: Any) -> int:
    if isinstance(evidence, Mapping):
        try:
            return max(0, int(evidence.get("matured_sample_count", 0)))
        except (TypeError, ValueError):
            return 0
    receipt_path = getattr(evidence, "receipt_path", None)
    if not receipt_path:
        return 0
    try:
        payload = _read_mapping(Path(str(receipt_path)))
        return max(0, int(payload.get("matured_sample_count", 0)))
    except (OSError, UnicodeError, TypeError, ValueError, json.JSONDecodeError):
        return 0


def _evidence_id(evidence: Any) -> str:
    if isinstance(evidence, Mapping):
        value = evidence.get("evidence_id") or evidence.get("receipt_hash")
    else:
        value = getattr(evidence, "evidence_id", None) or getattr(evidence, "receipt_hash", None)
    return hashlib.sha256(str(value or "natural").encode("utf-8")).hexdigest()[:16]


def _compact_exception_text(exc: BaseException, *, limit: int = 2400) -> str:
    text = " ".join(str(exc).split())
    return text[:limit] if text else "unspecified_error"


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _next_step(decision: str, reason: str) -> str:
    if decision == "adopt":
        return "保留 shadow candidate 的自然 forward capture，確認 active pointer 與 consumer 仍可重載。"
    if decision == "rollback":
        return "檢查資料／drift fault 與 last-good pointer；修復後以新日重試，不覆寫當日 receipt。"
    if any(token in reason for token in ("no_data", "insufficient", "matured")):
        return "等待新的成熟自然 forward outcomes；未達門檻前保留 current/rule-only。"
    if any(token in reason for token in ("dependency", "preflight")):
        return "修復 dependency 後以同一 decision date 的新受控 receipt 重試，不覆寫既有 receipt。"
    if any(token in reason for token in ("fault", "failed", "unavailable")):
        return "修復 dependency 或資料品質問題後，以新日重新執行 bounded runner。"
    return "保留 current；下一個排程日重新檢查同樣本、同成本與自然成熟度。"
