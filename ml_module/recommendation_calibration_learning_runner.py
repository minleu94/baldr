"""Shadow-only daily recommendation learning orchestration。

這是 learning producer 的 canonical ML 邊界。它只讀取 caller 提供的 samples 與
dependency metadata，在隔離 Shadow root 產生 candidate、training lineage、run
receipt 與既有 authority decision；不讀寫正式資料庫、不寫 order state，也不
import ``app_module``。scheduled entrypoint 直接依賴本模組的 canonical runner，
保留既有 ``DailyRecommendationLearningRunner`` 的呼叫形狀。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
from runtime.file_io_path import (
    canonical_path_from_os_result as _canonical_io_result,
    canonical_scandir_child as _canonical_io_child,
    io_path as _io_path,
    iterdir_canonical as _iterdir_io,
    resolve_canonical_path as _resolve_io_path,
    to_internal_io_path as _to_internal_io_path,
)
import stat
from typing import Any, Mapping, Sequence

from ml_module.model_artifact_manifest import FeatureSchema, ModelArtifactManifest
from ml_module.recommendation_calibration_authority import (
    RecommendationCalibrationPromotionAuthority,
)
from ml_module.recommendation_calibration_training import (
    RecommendationCalibrationSample,
    RecommendationCalibrationTrainingConfig,
    RecommendationCalibrationTrainingResult,
    RecommendationCalibrationTrainingService,
    candidate_freeze_hash,
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
    _replay_manifest_lineage,
    _source_contract_payload,
    _source_group_lineage,
    build_recommendation_training_lineage,
    persist_recommendation_training_lineage,
    recommendation_training_dataset_hash,
    resolve_recommendation_training_context,
    read_recommendation_training_lineage,
    training_lineage_path,
)


DEFAULT_DATA_ROOT = Path("F:/Min/Python/Project/FA_Data")
RECOMMENDATION_LEARNING_OUTPUT_ROOT_ENV = "RECOMMENDATION_LEARNING_OUTPUT_ROOT"
_RUN_INPUT_IDENTITY_SCHEMA = "recommendation-learning-run-input-identity.v1"
_CANDIDATE_RUN_BINDING_SCHEMA = "recommendation-learning-candidate-run-binding.v1"
_FROZEN_CANDIDATE_PACKAGE_IDENTITY_SCHEMA = "recommendation-learning-frozen-candidate-package.v1"
_WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_SOURCE_ROLE_ALIASES = {
    "replay": "replay",
    "historical_replay": "replay",
    "bootstrap": "bootstrap_replay",
    "bootstrap_replay": "bootstrap_replay",
    "natural": "natural",
    "natural_forward": "natural",
}


class _SameRunInputConflict(ValueError):
    """同一 run ID 的輸入或已保存套件不一致；必須改用新 scope。"""


@dataclass(frozen=True)
class _VerifiedCandidatePackage:
    root: Path
    metadata: dict[str, Any]
    manifest: ModelArtifactManifest
    lineage_hash: str
    lineage_path: str


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

        run_input_identity: dict[str, Any] | None = None
        frozen_run_input_identity: dict[str, Any] | None = None
        recovered_candidate: _VerifiedCandidatePackage | None = None
        run_input_identity_path = run_dir / "run_input_identity.json"
        if not emergency_rollback:
            if frozen_candidate_root is None:
                run_input_identity = _build_run_input_identity(
                    run_id=run_id,
                    decision_date=day,
                    run_scope=scope,
                    training_as_of=training_cutoff,
                    samples=eligible_samples,
                    feature_names=self.feature_names,
                    feature_schema=self.feature_schema,
                    feature_registry_hash=self.feature_registry_hash,
                    training_config=self.training_config,
                    cost_scenario=self.cost_scenario,
                    dataset_quality=dataset_quality,
                    lineage_sources=lineage_sources,
                )
            elif _io_path(receipt_path).is_file() or _io_path(run_input_identity_path).exists():
                frozen_run_input_identity = _build_frozen_run_input_identity(
                    run_id=run_id,
                    decision_date=day,
                    run_scope=scope,
                    training_as_of=training_cutoff,
                    dataset_hash=dataset_hash,
                    dataset_quality=dataset_quality,
                    cost_scenario=self.cost_scenario,
                    frozen_candidate_root=Path(frozen_candidate_root),
                    fixed_round_trip_cost_bp=self.fixed_round_trip_cost_bp,
                )
            if run_input_identity is not None and _io_path(run_input_identity_path).exists():
                _load_or_create_run_input_identity(
                    run_input_identity_path,
                    run_input_identity,
                    allow_create=False,
                )
            if frozen_run_input_identity is not None:
                _load_or_create_run_input_identity(
                    run_input_identity_path,
                    frozen_run_input_identity,
                    allow_create=False,
                )
            if run_input_identity is not None:
                existing_candidate_directories = _candidate_directories(run_dir)
                if existing_candidate_directories and not _io_path(run_input_identity_path).exists():
                    raise _SameRunInputConflict(
                        "same_run_candidate_package_has_no_training_input_identity_use_new_run_scope"
                    )
                if len(existing_candidate_directories) > 1:
                    raise _SameRunInputConflict(
                        "same_run_has_multiple_candidate_packages_use_new_run_scope"
                    )
                if existing_candidate_directories:
                    recovered_candidate = _verify_candidate_run_package(
                        existing_candidate_directories[0],
                        expected_identity=run_input_identity,
                        expected_candidates_root=run_dir / "candidates",
                        expected_learning_root=self.root,
                        require_run_binding=True,
                    )

        if _io_path(receipt_path).is_file() and not emergency_rollback:
            existing = _read_mapping(receipt_path)
            if existing.get("status") == "completed" and existing.get("finalized") is True:
                candidate_id = _optional_text(existing.get("candidate_id"))
                candidate_root: Path | None = None
                candidate_metadata: dict[str, Any] | None = None
                if candidate_id:
                    if frozen_candidate_root is None:
                        if run_input_identity is None or recovered_candidate is None:
                            raise _SameRunInputConflict(
                                "legacy_completed_run_lacks_verifiable_candidate_package_use_new_run_scope"
                            )
                        candidate_root = recovered_candidate.root
                        candidate_metadata = recovered_candidate.metadata
                        _verify_completed_receipt_binding(
                            existing,
                            candidate_root=candidate_root,
                            candidate_metadata=candidate_metadata,
                            decision_date=day,
                            run_scope=scope,
                            dataset_hash=dataset_hash,
                            training_as_of=training_cutoff,
                            cost_scenario=self.cost_scenario,
                        )
                    else:
                        candidate_root = _resolve_io_path(Path(str(existing.get("candidate_root") or "")))
                        if candidate_root != _resolve_io_path(Path(frozen_candidate_root)):
                            raise _SameRunInputConflict(
                                "same_run_frozen_candidate_root_changed_use_new_run_scope"
                            )
                        try:
                            candidate_metadata = _read_mapping(candidate_root / "candidate.json")
                        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
                            raise _SameRunInputConflict(
                                "same_run_frozen_candidate_unreadable_use_new_run_scope"
                            ) from exc
                        if frozen_run_input_identity is None:
                            raise _SameRunInputConflict(
                                "same_run_frozen_candidate_identity_unavailable_use_new_run_scope"
                            )
                        _verify_completed_frozen_receipt_binding(
                            existing,
                            identity=frozen_run_input_identity,
                            candidate_metadata=candidate_metadata,
                        )
                else:
                    _verify_completed_no_candidate_receipt(
                        existing,
                        run_id=run_id,
                        decision_date=day,
                        run_scope=scope,
                        dataset_hash=dataset_hash,
                        cost_scenario=self.cost_scenario,
                    )

                if (
                    natural_evidence is not None
                    and existing.get("decision") == "retain_current"
                    and candidate_root is not None
                    and candidate_metadata is not None
                ):
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

        frozen_input_root = (
            Path(frozen_candidate_root) if frozen_candidate_root is not None else None
        )
        if frozen_input_root is not None and (
            not _is_plain_directory(frozen_input_root)
            or not _path_has_no_reparse_components(frozen_input_root)
        ):
            return self._write_skip(
                day=day,
                run_id=run_id,
                run_dir=run_dir,
                run_scope=scope,
                reason="frozen_challenger_root_not_regular_directory",
                status="failed_candidate",
                dataset_hash=dataset_hash,
                decision="retain_current",
                decision_reason="frozen_challenger_root_not_regular_directory_fail_closed",
                natural_matured_sample_count=_evidence_count(natural_evidence),
                data_dependency_status=data_dependency_status,
                outcome_dependency_status=outcome_dependency_status,
                drift_status=drift_status,
            )
        frozen_root = _resolve_io_path(frozen_input_root) if frozen_input_root is not None else None
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

        if frozen_root is None:
            if run_input_identity is None:
                raise RuntimeError("訓練 run 缺少輸入 identity")
            _load_or_create_run_input_identity(
                run_input_identity_path,
                run_input_identity,
                allow_create=True,
            )

        dataset_id = f"recommendation-dataset-{dataset_hash[7:23]}"
        result: RecommendationCalibrationTrainingResult | None = None
        lineage_hash: str | None = None
        lineage_path: str | None = None
        lineage_status = "not_available"
        candidate_available_at: str | None = None
        if frozen_root is None and recovered_candidate is not None:
            candidate_root = recovered_candidate.root
            candidate_metadata = recovered_candidate.metadata
            lineage_hash = recovered_candidate.lineage_hash
            lineage_path = recovered_candidate.lineage_path
            lineage_status = "verified"
            candidate_available_at = _available_at_after_freeze(
                recovered_candidate.manifest.created_at
            )
        elif frozen_root is None:
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
                _verify_persisted_candidate_package(
                    result=result,
                    candidate_root=candidate_root,
                    candidate_payload=candidate_payload,
                    lineage=lineage,
                    lineage_path=persisted_lineage_path,
                )
                if run_input_identity is None:
                    raise RuntimeError("訓練 run 缺少輸入 identity")
                binding = _candidate_binding_payload(
                    identity_hash=str(run_input_identity.get("identity_hash") or ""),
                    candidate_metadata=candidate_payload,
                )
                _write_json_once(candidate_root / "run_input_binding.json", binding)
                _verify_candidate_run_package(
                    candidate_root,
                    expected_identity=run_input_identity,
                    expected_candidates_root=run_dir / "candidates",
                    expected_learning_root=self.root,
                    require_run_binding=True,
                )
                frozen_at = datetime.fromisoformat(result.manifest.created_at)
                available_at = datetime.now(timezone.utc)
                if (
                    frozen_at.tzinfo is None
                    or frozen_at.utcoffset() != timedelta(0)
                    or available_at < frozen_at
                ):
                    raise RuntimeError("候選凍結時間不是有效 UTC 或晚於可用時鐘")
                candidate_available_at = available_at.isoformat(timespec="microseconds")
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
                frozen_run_input_identity = _build_frozen_run_input_identity(
                    run_id=run_id,
                    decision_date=day,
                    run_scope=scope,
                    training_as_of=training_cutoff,
                    dataset_hash=dataset_hash,
                    dataset_quality=dataset_quality,
                    cost_scenario=self.cost_scenario,
                    frozen_candidate_root=frozen_root,
                    fixed_round_trip_cost_bp=self.fixed_round_trip_cost_bp,
                )
                _load_or_create_run_input_identity(
                    run_input_identity_path,
                    frozen_run_input_identity,
                    allow_create=True,
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
        if candidate_available_at is not None:
            receipt["candidate_available_at"] = candidate_available_at
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
    formal_root = _resolve_io_path(Path(data_root or os.environ.get("DATA_ROOT") or DEFAULT_DATA_ROOT))
    resolved = _resolve_io_path(raw_output)
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
    root = _resolve_io_path(candidate_root)
    if _io_path(root).exists() and any(_iterdir_io(root)):
        raise FileExistsError(f"candidate directory already contains files: {root}")
    _io_path(root).mkdir(parents=True, exist_ok=True)
    _io_path(root / result.manifest.artifact_filename).write_bytes(result.artifact_bytes)
    _write_json_once(root / "manifest.json", result.manifest.to_dict())
    _write_json_once(root / "candidate.json", candidate_payload)


def _verify_persisted_candidate_package(
    *,
    result: RecommendationCalibrationTrainingResult,
    candidate_root: Path,
    candidate_payload: Mapping[str, Any],
    lineage: Any,
    lineage_path: Path,
) -> None:
    """讀回並核對候選 bytes，成功後才允許記錄可用時間。"""

    root = _resolve_io_path(candidate_root)
    artifact_path = root / result.manifest.artifact_filename
    manifest_path = root / "manifest.json"
    candidate_path = root / "candidate.json"
    for path in (artifact_path, manifest_path, candidate_path):
        if not _io_path(path).is_file():
            raise RuntimeError(f"候選套件讀回缺少一般檔案: {path}")

    artifact_bytes = _io_path(artifact_path).read_bytes()
    artifact_hash = "sha256:" + hashlib.sha256(artifact_bytes).hexdigest()
    if artifact_bytes != result.artifact_bytes or artifact_hash != result.artifact_hash:
        raise RuntimeError("候選模型 bytes/hash 讀回不一致")

    manifest_payload = _read_mapping(manifest_path)
    expected_manifest = result.manifest.to_dict()
    if _canonical_json(manifest_payload) != _canonical_json(expected_manifest):
        raise RuntimeError("候選 manifest schema/內容讀回不一致")

    persisted_candidate = _read_mapping(candidate_path)
    if _canonical_json(persisted_candidate) != _canonical_json(candidate_payload):
        raise RuntimeError("候選 metadata schema/內容讀回不一致")
    if persisted_candidate.get("candidate_frozen_at") != result.manifest.created_at:
        raise RuntimeError("候選凍結時間與訓練 manifest 不一致")

    lineage_hash = str(getattr(lineage, "manifest_hash", ""))
    lineage_readback = read_recommendation_training_lineage(
        lineage_path,
        expected_manifest_hash=lineage_hash,
        expected_dataset_hash=result.dataset_hash,
        expected_candidate_id=result.candidate_id,
    )
    if lineage_readback.to_dict() != lineage.to_dict():
        raise RuntimeError("候選 lineage schema/內容讀回不一致")
    if (
        persisted_candidate.get("training_lineage_manifest_hash") != lineage_hash
        or persisted_candidate.get("training_lineage_manifest_path")
        != str(lineage_path)
    ):
        raise RuntimeError("候選 metadata 與 lineage 讀回綁定不一致")


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _build_run_input_identity(
    *,
    run_id: str,
    decision_date: str,
    run_scope: str | None,
    training_as_of: str,
    samples: Sequence[RecommendationCalibrationSample],
    feature_names: tuple[str, ...],
    feature_schema: FeatureSchema,
    feature_registry_hash: str,
    training_config: RecommendationCalibrationTrainingConfig,
    cost_scenario: RecommendationCostScenario,
    dataset_quality: Mapping[str, Any] | None,
    lineage_sources: Mapping[str, Sequence[RecommendationCalibrationSample]] | None,
) -> dict[str, Any]:
    """建立只含訓練輸入與來源 lineage 的穩定 run identity。"""

    quality = dataset_quality if isinstance(dataset_quality, Mapping) else {}
    try:
        training_semantics, decision_time_eligible = resolve_recommendation_training_context(
            decision_date=decision_date,
            training_as_of=training_as_of,
            dataset_quality=quality,
        )
        training_context: dict[str, Any] = {
            "status": "valid",
            "semantics": training_semantics,
            "decision_time_eligible": decision_time_eligible,
        }
    except RecommendationTrainingLineageError as exc:
        training_context = {
            "status": "invalid",
            "reason": _compact_exception_text(exc),
            "research_only": quality.get("research_only"),
            "training_semantics": quality.get("training_semantics"),
            "decision_time_eligible": quality.get("decision_time_eligible"),
        }

    ordered_samples = tuple(
        sorted(samples, key=lambda row: (row.decision_date, row.symbol, row.row_id))
    )
    try:
        group_payload, dedup_payload, source_role_ids = _source_group_lineage(
            ordered_samples,
            lineage_sources,
        )
        source_groups: Any = {
            "groups": group_payload,
            "deduplication": dedup_payload,
            "source_role_row_ids": source_role_ids,
        }
    except (TypeError, ValueError, RecommendationTrainingLineageError) as exc:
        source_groups = {
            "invalid": type(exc).__name__,
            "reason": _compact_exception_text(exc),
        }
    try:
        replay_manifests: Any = _replay_manifest_lineage(quality)
    except (OSError, TypeError, ValueError, RecommendationTrainingLineageError) as exc:
        replay_manifests = {
            "invalid": type(exc).__name__,
            "reason": _compact_exception_text(exc),
        }

    # 這些欄位只描述候選／自然證據門檻，不改變 fit 輸入；訓練語意已由
    # training_context 記錄，樣本選擇則由資料與來源 lineage 記錄。
    quality_keys = ("training_data_eligible",)
    stable_quality: dict[str, Any] = {
        key: _stable_json_value(quality[key])
        for key in quality_keys
        if key in quality
    }
    bootstrap = quality.get("historical_bootstrap")
    if isinstance(bootstrap, Mapping):
        stable_quality["historical_bootstrap"] = {
            key: _stable_json_value(bootstrap[key])
            for key in ("selection_method", "row_ids")
            if key in bootstrap
        }
    try:
        source_contract: Any = _source_contract_payload(quality)
    except (TypeError, ValueError, RecommendationTrainingLineageError) as exc:
        source_contract = {
            "invalid": type(exc).__name__,
            "reason": _compact_exception_text(exc),
        }

    body: dict[str, Any] = {
        "run_id": run_id,
        "decision_date": decision_date,
        "run_scope": run_scope,
        "training_as_of": training_as_of,
        "training_context": training_context,
        "dataset_id": f"recommendation-dataset-{_dataset_hash(samples)[7:23]}",
        "dataset_hash": _dataset_hash(samples),
        "merged_samples_payload_hash": _hash_json_payload(
            [sample_payload(row) for row in ordered_samples]
        ),
        "merged_sample_ids": [row.row_id for row in ordered_samples],
        "feature_names": list(feature_names),
        "feature_schema": [list(item) for item in feature_schema],
        "feature_registry_hash": feature_registry_hash,
        "training_config": asdict(training_config),
        "cost_scenario": cost_scenario.to_dict(),
        "source_groups": source_groups,
        "source_contract": source_contract,
        "replay_manifests": replay_manifests,
        "training_quality": stable_quality,
    }
    return {
        "schema_version": _RUN_INPUT_IDENTITY_SCHEMA,
        "identity": body,
        "identity_hash": _hash_json_payload(body),
    }


def _build_frozen_run_input_identity(
    *,
    run_id: str,
    decision_date: str,
    run_scope: str | None,
    training_as_of: str,
    dataset_hash: str,
    dataset_quality: Mapping[str, Any] | None,
    cost_scenario: RecommendationCostScenario,
    frozen_candidate_root: Path,
    fixed_round_trip_cost_bp: int | None,
) -> dict[str, Any]:
    """為不重訓的凍結候選評估建立獨立的同 run 輸入身份。"""

    root = _resolve_io_path(frozen_candidate_root)
    if (
        not _is_plain_directory(frozen_candidate_root)
        or not _path_has_no_reparse_components(frozen_candidate_root)
        or not _is_plain_directory(root)
    ):
        raise _SameRunInputConflict(
            "same_run_frozen_candidate_root_is_not_regular_use_new_run_scope"
        )
    try:
        files = _candidate_package_file_inventory(root)
        metadata = _read_mapping(root / "candidate.json")
        _validate_frozen_candidate(metadata, cost_scenario, fixed_round_trip_cost_bp)
        lineage_hash, lineage_path, lineage_status = _frozen_candidate_lineage(root, metadata)
    except (OSError, UnicodeError, TypeError, ValueError, KeyError, RecommendationTrainingLineageError) as exc:
        raise _SameRunInputConflict(
            "same_run_frozen_candidate_package_invalid_use_new_run_scope"
        ) from exc

    quality = dataset_quality if isinstance(dataset_quality, Mapping) else {}
    try:
        semantics, decision_time_eligible = resolve_recommendation_training_context(
            decision_date=decision_date,
            training_as_of=training_as_of,
            dataset_quality=quality,
        )
        training_context: dict[str, Any] = {
            "status": "valid",
            "semantics": semantics,
            "decision_time_eligible": decision_time_eligible,
        }
    except RecommendationTrainingLineageError as exc:
        training_context = {"status": "invalid", "reason": _compact_exception_text(exc)}

    lineage_file_hash = None
    if lineage_path is not None:
        resolved_lineage_path = _resolve_io_path(Path(lineage_path))
        if not _is_plain_file(resolved_lineage_path) or not _path_has_no_reparse_components(
            resolved_lineage_path
        ):
            raise _SameRunInputConflict(
                "same_run_frozen_candidate_lineage_path_is_not_regular_use_new_run_scope"
            )
        lineage_file_hash = _sha256_path(resolved_lineage_path)

    body = {
        "mode": "frozen_candidate_evaluation",
        "run_id": run_id,
        "decision_date": decision_date,
        "run_scope": run_scope,
        "training_as_of": training_as_of,
        "dataset_hash": dataset_hash,
        "training_context": training_context,
        "cost_scenario": cost_scenario.to_dict(),
        "candidate_root": str(root),
        "candidate_id": metadata.get("candidate_id"),
        "candidate_dataset_hash": metadata.get("dataset_hash"),
        "candidate_manifest_hash": metadata.get("manifest_hash"),
        "candidate_artifact_hash": metadata.get("artifact_hash"),
        "candidate_freeze_hash": metadata.get("candidate_freeze_hash"),
        "candidate_package_files": files,
        "training_lineage_manifest_hash": lineage_hash,
        "training_lineage_manifest_path": lineage_path,
        "training_lineage_file_hash": lineage_file_hash,
        "training_lineage_status": lineage_status,
    }
    return {
        "schema_version": _RUN_INPUT_IDENTITY_SCHEMA,
        "identity": body,
        "identity_hash": _hash_json_payload(body),
    }


def _stable_json_value(value: Any) -> Any:
    """轉為 lineage 可保存的 JSON 值；無法序列化時保留明確錯誤身份。"""

    try:
        return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError):
        return {"invalid_json_value_type": type(value).__name__}


def _hash_json_payload(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _read_run_input_identity(path: Path) -> dict[str, Any]:
    try:
        payload = _read_mapping(path)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise _SameRunInputConflict(
            "same_run_input_identity_unreadable_use_new_run_scope"
        ) from exc
    identity = payload.get("identity")
    if (
        payload.get("schema_version") != _RUN_INPUT_IDENTITY_SCHEMA
        or not isinstance(identity, Mapping)
        or payload.get("identity_hash") != _hash_json_payload(identity)
    ):
        raise _SameRunInputConflict(
            "same_run_input_identity_invalid_use_new_run_scope"
        )
    return payload


def _load_or_create_run_input_identity(
    path: Path,
    expected: Mapping[str, Any],
    *,
    allow_create: bool,
) -> dict[str, Any]:
    if _io_path(path).exists():
        actual = _read_run_input_identity(path)
        if _canonical_json(actual) != _canonical_json(expected):
            raise _SameRunInputConflict(
                "same_run_input_conflict_data_config_cost_or_source_lineage_changed_use_new_run_scope"
            )
        return actual
    if not allow_create:
        raise _SameRunInputConflict(
            "same_run_input_identity_missing_for_existing_candidate_use_new_run_scope"
        )
    try:
        _write_json_once(path, expected)
        actual = _read_run_input_identity(path)
    except _SameRunInputConflict:
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise _SameRunInputConflict(
            "same_run_input_identity_could_not_be_persisted_use_new_run_scope"
        ) from exc
    if _canonical_json(actual) != _canonical_json(expected):
        raise _SameRunInputConflict(
            "same_run_input_identity_write_conflict_use_new_run_scope"
        )
    return actual


def _candidate_directories(run_dir: Path) -> tuple[Path, ...]:
    candidates_root = run_dir / "candidates"
    try:
        _io_path(candidates_root).lstat()
    except FileNotFoundError:
        return ()
    except OSError as exc:
        raise _SameRunInputConflict(
            "same_run_candidate_root_cannot_be_inspected_use_new_run_scope"
        ) from exc
    if not _is_plain_directory(candidates_root) or not _path_has_no_reparse_components(
        candidates_root
    ):
        raise _SameRunInputConflict(
            "same_run_candidate_root_is_not_a_regular_directory_use_new_run_scope"
        )
    resolved_candidates_root = _resolve_io_path(candidates_root)
    try:
        entries = tuple(sorted(_iterdir_io(candidates_root), key=lambda item: item.name))
    except OSError as exc:
        raise _SameRunInputConflict(
            "same_run_candidate_root_cannot_be_listed_use_new_run_scope"
        ) from exc
    for item in entries:
        if (
            not _is_plain_directory(item)
            or not _path_has_no_reparse_components(item)
            or _resolve_io_path(item).parent != resolved_candidates_root
        ):
            raise _SameRunInputConflict(
                "same_run_candidate_root_contains_unrecognized_entry_use_new_run_scope"
            )
    return entries


def _candidate_package_file_inventory(root: Path) -> list[dict[str, Any]]:
    """對凍結套件做不載入模型的普通檔案盤點與內容雜湊。"""

    if not _is_plain_directory(root) or not _path_has_no_reparse_components(root):
        raise ValueError("candidate package root is not a plain directory")
    pending = [root]
    files: list[dict[str, Any]] = []
    while pending:
        directory = pending.pop()
        with os.scandir(_io_path(directory)) as iterator:
            entries = sorted(iterator, key=lambda item: item.name)
        for entry in entries:
            path = _canonical_io_child(directory, entry.name, entry.path)
            details = _io_path(path).lstat()
            if _is_reparse_point(path):
                raise ValueError("candidate package contains a reparse point")
            if stat.S_ISDIR(details.st_mode):
                pending.append(path)
                continue
            if not stat.S_ISREG(details.st_mode):
                raise ValueError("candidate package contains a non-regular file")
            files.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "size_bytes": int(details.st_size),
                    "sha256": _sha256_path(path),
                }
            )
    files.sort(key=lambda item: str(item["path"]))
    if not any(item["path"] == "candidate.json" for item in files):
        raise ValueError("candidate package metadata is missing")
    return files


def _path_has_no_reparse_components(path: Path) -> bool:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        try:
            details = _io_path(current).lstat()
        except OSError:
            return False
        if stat.S_ISLNK(details.st_mode) or _is_reparse_point(current):
            return False
    return True


def _candidate_binding_payload(
    *,
    identity_hash: str,
    candidate_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    body = {
        "schema_version": _CANDIDATE_RUN_BINDING_SCHEMA,
        "run_input_identity_hash": identity_hash,
        "candidate_id": candidate_metadata.get("candidate_id"),
        "dataset_hash": candidate_metadata.get("dataset_hash"),
        "manifest_hash": candidate_metadata.get("manifest_hash"),
        "artifact_hash": candidate_metadata.get("artifact_hash"),
        "candidate_freeze_hash": candidate_metadata.get("candidate_freeze_hash"),
        "training_lineage_manifest_hash": candidate_metadata.get(
            "training_lineage_manifest_hash"
        ),
        "training_lineage_manifest_path": candidate_metadata.get(
            "training_lineage_manifest_path"
        ),
    }
    return {
        **body,
        "binding_hash": _candidate_run_binding_hash(body, candidate_metadata),
    }


def _candidate_run_binding_hash(
    binding_body: Mapping[str, Any],
    candidate_metadata: Mapping[str, Any],
) -> str:
    """將完整候選 metadata 綁到既有 binding checksum。"""

    return _hash_json_payload(
        {
            "binding": dict(binding_body),
            "candidate_metadata": dict(candidate_metadata),
        }
    )


def _verify_candidate_run_package(
    candidate_root: Path,
    *,
    expected_identity: Mapping[str, Any],
    expected_candidates_root: Path,
    expected_learning_root: Path,
    require_run_binding: bool,
) -> _VerifiedCandidatePackage:
    root = _resolve_io_path(candidate_root)
    candidates_root = _resolve_io_path(expected_candidates_root)
    if (
        not _is_plain_directory(candidate_root)
        or not _path_has_no_reparse_components(candidate_root)
        or not _is_plain_directory(expected_candidates_root)
        or not _path_has_no_reparse_components(expected_candidates_root)
        or root.parent != candidates_root
        or not _is_plain_directory(root)
    ):
        raise _SameRunInputConflict(
            "same_run_candidate_package_missing_or_not_directory_use_new_run_scope"
        )
    candidate_path = root / "candidate.json"
    manifest_path = root / "manifest.json"
    if not _is_plain_file(candidate_path) or not _is_plain_file(manifest_path):
        raise _SameRunInputConflict(
            "same_run_candidate_package_metadata_is_not_regular_file_use_new_run_scope"
        )
    try:
        metadata = _read_mapping(candidate_path)
        manifest_payload = _read_mapping(manifest_path)
        manifest = ModelArtifactManifest.from_dict(manifest_payload)
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise _SameRunInputConflict(
            "same_run_candidate_metadata_or_manifest_invalid_use_new_run_scope"
        ) from exc
    if _canonical_json(manifest.to_dict()) != _canonical_json(manifest_payload):
        raise _SameRunInputConflict(
            "same_run_candidate_manifest_has_unrecognized_fields_use_new_run_scope"
        )

    artifact_filename = manifest.artifact_filename
    if Path(artifact_filename).name != artifact_filename or artifact_filename in {"", ".", ".."}:
        raise _SameRunInputConflict(
            "same_run_candidate_artifact_path_invalid_use_new_run_scope"
        )
    artifact_path = root / artifact_filename
    if not _is_plain_file(artifact_path):
        raise _SameRunInputConflict(
            "same_run_candidate_artifact_missing_or_not_regular_use_new_run_scope"
        )
    artifact_hash = _sha256_path(artifact_path)
    if artifact_hash != manifest.artifact_hash:
        raise _SameRunInputConflict(
            "same_run_candidate_artifact_hash_mismatch_use_new_run_scope"
        )

    identity = expected_identity.get("identity")
    if not isinstance(identity, Mapping):
        raise _SameRunInputConflict("same_run_input_identity_invalid_use_new_run_scope")
    candidate_id = str(metadata.get("candidate_id") or "")
    if not candidate_id or root.name != candidate_id:
        raise _SameRunInputConflict(
            "same_run_candidate_directory_identity_mismatch_use_new_run_scope"
        )
    if (
        metadata.get("schema_version") != "recommendation-calibration-candidate.v1"
        or metadata.get("candidate_id") != manifest.model_id
        or metadata.get("model_id") != manifest.model_id
        or metadata.get("dataset_id") != identity.get("dataset_id")
        or metadata.get("dataset_hash") != identity.get("dataset_hash")
        or manifest.dataset_id != identity.get("dataset_id")
        or metadata.get("feature_names") != identity.get("feature_names")
        or metadata.get("feature_schema") != identity.get("feature_schema")
        or manifest.feature_schema != tuple(tuple(item) for item in identity.get("feature_schema", ()))
        or metadata.get("feature_registry_hash") != identity.get("feature_registry_hash")
        or manifest.feature_registry_hash != identity.get("feature_registry_hash")
        or metadata.get("training_cutoff") != identity.get("training_as_of")
        or metadata.get("horizon_trading_days")
        != identity.get("training_config", {}).get("horizon_trading_days")
        or metadata.get("cost_scenario") != identity.get("cost_scenario")
        or metadata.get("manifest_hash") != manifest.manifest_hash
        or metadata.get("artifact_hash") != manifest.artifact_hash
        or metadata.get("candidate_frozen_at") != manifest.created_at
        or metadata.get("training_semantics")
        != identity.get("training_context", {}).get("semantics")
        or metadata.get("decision_time_eligible")
        != identity.get("training_context", {}).get("decision_time_eligible")
        or metadata.get("model_family")
        != RecommendationCalibrationTrainingService.MODEL_FAMILY
    ):
        raise _SameRunInputConflict(
            "same_run_candidate_identity_or_training_contract_mismatch_use_new_run_scope"
        )
    if manifest.training_as_of != metadata.get("training_as_of"):
        raise _SameRunInputConflict(
            "same_run_candidate_training_cutoff_mismatch_use_new_run_scope"
        )
    expected_hyperparameters_hash = _hash_json_payload(
        {
            "model_family": RecommendationCalibrationTrainingService.MODEL_FAMILY,
            "random_state": identity.get("training_config", {}).get("random_state"),
            "calibration_method": "isotonic_oof",
            "target_definitions": metadata.get("target_definitions"),
        }
    )
    if manifest.hyperparameters_hash != expected_hyperparameters_hash:
        raise _SameRunInputConflict(
            "same_run_candidate_training_parameter_hash_mismatch_use_new_run_scope"
        )
    evaluation_value: object = metadata.get("evaluation")
    evaluation: Mapping[str, Any] = (
        evaluation_value if isinstance(evaluation_value, Mapping) else {}
    )
    if metadata.get("candidate_freeze_hash") != candidate_freeze_hash(
        candidate_id=candidate_id,
        dataset_hash=str(metadata.get("dataset_hash") or ""),
        manifest_hash=manifest.manifest_hash,
        artifact_hash=artifact_hash,
        evaluation=evaluation,
    ):
        raise _SameRunInputConflict(
            "same_run_candidate_freeze_hash_mismatch_use_new_run_scope"
        )

    lineage_hash = _optional_text(metadata.get("training_lineage_manifest_hash"))
    lineage_path_text = _optional_text(metadata.get("training_lineage_manifest_path"))
    if not lineage_hash or not lineage_path_text:
        raise _SameRunInputConflict(
            "same_run_candidate_lineage_missing_or_legacy_unproven_use_new_run_scope"
        )
    supplied_lineage_path = Path(lineage_path_text)
    lineage_path = _resolve_io_path(supplied_lineage_path)
    expected_lineage_directory = (
        _resolve_io_path(Path(expected_learning_root))
        / "training_lineage"
        / str(identity.get("decision_date") or "")
        / lineage_hash.split(":", 1)[-1]
    )
    if (
        lineage_path.parent != expected_lineage_directory
        or lineage_path.name != "lineage.json"
        or not _path_has_no_reparse_components(supplied_lineage_path)
        or not _plain_path_chain(
            _resolve_io_path(Path(expected_learning_root)),
            lineage_path,
            final_file=True,
        )
    ):
        raise _SameRunInputConflict(
            "same_run_candidate_lineage_path_outside_deterministic_store_use_new_run_scope"
        )
    try:
        lineage = read_recommendation_training_lineage(
            lineage_path,
            expected_manifest_hash=lineage_hash,
            expected_dataset_hash=str(identity.get("dataset_hash") or ""),
            expected_candidate_id=candidate_id,
        )
    except (OSError, UnicodeError, TypeError, ValueError, RecommendationTrainingLineageError) as exc:
        raise _SameRunInputConflict(
            "same_run_candidate_lineage_invalid_use_new_run_scope"
        ) from exc
    if training_lineage_path(expected_learning_root, lineage) != lineage_path:
        raise _SameRunInputConflict(
            "same_run_candidate_lineage_not_at_deterministic_writer_path_use_new_run_scope"
        )
    lineage_payload = lineage.payload
    quality_payload = lineage_payload.get("dataset_quality")
    quality_payload = quality_payload if isinstance(quality_payload, Mapping) else {}
    lineage_training_context = lineage_payload.get("training_context")
    if (
        lineage_payload.get("run_id") != identity.get("run_id")
        or lineage_payload.get("run_scope") != identity.get("run_scope")
        or lineage_payload.get("decision_date") != identity.get("decision_date")
        or lineage_payload.get("training_as_of") != identity.get("training_as_of")
        or lineage_payload.get("dataset_id") != identity.get("dataset_id")
        or lineage_payload.get("dataset_hash") != identity.get("dataset_hash")
        or lineage_payload.get("merged_samples_payload_hash")
        != identity.get("merged_samples_payload_hash")
        or lineage_payload.get("merged_sample_ids") != identity.get("merged_sample_ids")
        or lineage_payload.get("feature_schema") != identity.get("feature_schema")
        or lineage_payload.get("feature_registry_hash") != identity.get("feature_registry_hash")
        or lineage_payload.get("cost_scenario") != identity.get("cost_scenario")
        or lineage_payload.get("source_groups") != identity.get("source_groups", {}).get("groups")
        or lineage_payload.get("deduplication")
        != identity.get("source_groups", {}).get("deduplication")
        or lineage_payload.get("source_role_row_ids")
        != identity.get("source_groups", {}).get("source_role_row_ids")
        or lineage_payload.get("source_contract") != identity.get("source_contract")
        or lineage_payload.get("replay_manifests") != identity.get("replay_manifests")
        or _training_quality_projection(quality_payload)
        != identity.get("training_quality")
        or not isinstance(lineage_training_context, Mapping)
        or lineage_training_context.get("semantics")
        != identity.get("training_context", {}).get("semantics")
        or lineage_training_context.get("decision_time_eligible")
        != identity.get("training_context", {}).get("decision_time_eligible")
        or lineage_payload.get("candidate_manifest_hash") != manifest.manifest_hash
        or lineage_payload.get("candidate_artifact_hash") != artifact_hash
        or metadata.get("training_source_hash") != lineage_payload.get("training_source_hash")
        or metadata.get("training_pit_hash") != lineage_payload.get("training_pit_hash")
        or metadata.get("feature_transform_contract")
        != lineage_payload.get("feature_transform_contract")
    ):
        raise _SameRunInputConflict(
            "same_run_candidate_lineage_does_not_match_current_training_inputs_use_new_run_scope"
        )

    if require_run_binding:
        binding_path = root / "run_input_binding.json"
        if not _is_plain_file(binding_path):
            raise _SameRunInputConflict(
                "same_run_candidate_binding_is_not_regular_use_new_run_scope"
            )
        try:
            binding = _read_mapping(binding_path)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            raise _SameRunInputConflict(
                "same_run_candidate_binding_missing_or_unreadable_use_new_run_scope"
            ) from exc
        binding_body = dict(binding)
        supplied_binding_hash = binding_body.pop("binding_hash", None)
        if (
            binding_body.get("schema_version") != _CANDIDATE_RUN_BINDING_SCHEMA
            or supplied_binding_hash != _candidate_run_binding_hash(binding_body, metadata)
            or binding_body.get("run_input_identity_hash")
            != expected_identity.get("identity_hash")
            or binding_body.get("candidate_id") != candidate_id
            or binding_body.get("dataset_hash") != metadata.get("dataset_hash")
            or binding_body.get("manifest_hash") != manifest.manifest_hash
            or binding_body.get("artifact_hash") != artifact_hash
            or binding_body.get("candidate_freeze_hash") != metadata.get("candidate_freeze_hash")
            or binding_body.get("training_lineage_manifest_hash") != lineage_hash
            or binding_body.get("training_lineage_manifest_path") != str(lineage_path)
        ):
            raise _SameRunInputConflict(
                "same_run_candidate_binding_mismatch_use_new_run_scope"
            )
    return _VerifiedCandidatePackage(
        root=root,
        metadata=metadata,
        manifest=manifest,
        lineage_hash=lineage_hash,
        lineage_path=str(lineage_path),
    )


def _training_quality_projection(quality: Mapping[str, Any]) -> dict[str, Any]:
    keys = ("training_data_eligible",)
    output = {
        key: _stable_json_value(quality[key])
        for key in keys
        if key in quality
    }
    bootstrap = quality.get("historical_bootstrap")
    if isinstance(bootstrap, Mapping):
        output["historical_bootstrap"] = {
            key: _stable_json_value(bootstrap[key])
            for key in ("selection_method", "row_ids")
            if key in bootstrap
        }
    return output


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with _io_path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _is_reparse_point(path: Path) -> bool:
    try:
        details = _io_path(path).lstat()
    except OSError:
        return False
    return bool(
        int(getattr(details, "st_file_attributes", 0))
        & _WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT
    )


def _is_plain_directory(path: Path) -> bool:
    try:
        details = _io_path(path).lstat()
    except OSError:
        return False
    return stat.S_ISDIR(details.st_mode) and not _is_reparse_point(path)


def _is_plain_file(path: Path) -> bool:
    try:
        details = _io_path(path).lstat()
    except OSError:
        return False
    return stat.S_ISREG(details.st_mode) and not _is_reparse_point(path)


def _plain_path_chain(root: Path, path: Path, *, final_file: bool) -> bool:
    """拒絕沿 lineage store 的 reparse 點讀取未核准路徑。"""

    resolved_root = _resolve_io_path(root)
    resolved_path = _resolve_io_path(path)
    if resolved_root != resolved_path and resolved_root not in resolved_path.parents:
        return False
    relative = resolved_path.relative_to(resolved_root)
    current = resolved_root
    if not _is_plain_directory(current) or not _path_has_no_reparse_components(current):
        return False
    parts = relative.parts
    for index, part in enumerate(parts):
        current = current / part
        is_final = index == len(parts) - 1
        if is_final and final_file:
            if not _is_plain_file(current):
                return False
        elif not _is_plain_directory(current):
            return False
    return bool(parts) and final_file


def _verify_completed_frozen_receipt_binding(
    receipt: Mapping[str, Any],
    *,
    identity: Mapping[str, Any],
    candidate_metadata: Mapping[str, Any],
) -> None:
    body = identity.get("identity")
    if not isinstance(body, Mapping):
        raise _SameRunInputConflict(
            "same_run_frozen_candidate_identity_invalid_use_new_run_scope"
        )
    expected_lineage_path = body.get("training_lineage_manifest_path")
    checks = (
        receipt.get("run_id") == body.get("run_id"),
        receipt.get("decision_date") == body.get("decision_date"),
        receipt.get("run_scope") == body.get("run_scope"),
        receipt.get("dataset_hash") == body.get("dataset_hash"),
        receipt.get("training_as_of") == body.get("training_as_of"),
        receipt.get("training_semantics")
        == (body.get("training_context") or {}).get("semantics"),
        receipt.get("cost_scenario_hash")
        == (body.get("cost_scenario") or {}).get("scenario_hash"),
        str(_resolve_io_path(Path(str(receipt.get("candidate_root") or ""))))
        == body.get("candidate_root"),
        receipt.get("candidate_id") == body.get("candidate_id"),
        receipt.get("candidate_dataset_hash") == body.get("candidate_dataset_hash"),
        receipt.get("candidate_manifest_hash") == body.get("candidate_manifest_hash"),
        receipt.get("candidate_artifact_hash") == body.get("candidate_artifact_hash"),
        receipt.get("candidate_freeze_hash") == body.get("candidate_freeze_hash"),
        receipt.get("training_lineage_manifest_hash")
        == body.get("training_lineage_manifest_hash"),
        receipt.get("training_lineage_manifest_path") == expected_lineage_path,
        receipt.get("training_lineage_status") == body.get("training_lineage_status"),
        candidate_metadata.get("candidate_id") == body.get("candidate_id"),
    )
    if not all(checks):
        raise _SameRunInputConflict(
            "same_run_frozen_completed_receipt_does_not_match_package_use_new_run_scope"
        )


def _verify_completed_receipt_binding(
    receipt: Mapping[str, Any],
    *,
    candidate_root: Path,
    candidate_metadata: Mapping[str, Any],
    decision_date: str,
    run_scope: str | None,
    dataset_hash: str,
    training_as_of: str,
    cost_scenario: RecommendationCostScenario,
) -> None:
    expected_candidate_root = str(_resolve_io_path(candidate_root))
    if (
        receipt.get("run_id")
        != f"daily-recommendation-learning:{decision_date}"
        + (f":{run_scope}" if run_scope else "")
        or receipt.get("decision_date") != decision_date
        or receipt.get("run_scope") != run_scope
        or receipt.get("dataset_hash") != dataset_hash
        or receipt.get("training_as_of") != training_as_of
        or receipt.get("cost_scenario_hash") != cost_scenario.scenario_hash
        or str(_resolve_io_path(Path(str(receipt.get("candidate_root") or ""))))
        != expected_candidate_root
        or receipt.get("candidate_id") != candidate_metadata.get("candidate_id")
        or receipt.get("candidate_manifest_hash") != candidate_metadata.get("manifest_hash")
        or receipt.get("candidate_artifact_hash") != candidate_metadata.get("artifact_hash")
        or receipt.get("candidate_freeze_hash")
        != candidate_metadata.get("candidate_freeze_hash")
        or receipt.get("candidate_dataset_hash") != dataset_hash
        or receipt.get("training_lineage_manifest_hash")
        != candidate_metadata.get("training_lineage_manifest_hash")
        or receipt.get("training_lineage_manifest_path")
        != candidate_metadata.get("training_lineage_manifest_path")
        or receipt.get("training_lineage_status") != "verified"
    ):
        raise _SameRunInputConflict(
            "same_run_completed_receipt_does_not_match_verified_candidate_use_new_run_scope"
        )
    available_text = _optional_text(receipt.get("candidate_available_at"))
    try:
        available_at = datetime.fromisoformat(available_text or "")
        frozen_at = datetime.fromisoformat(str(candidate_metadata.get("candidate_frozen_at") or ""))
    except ValueError as exc:
        raise _SameRunInputConflict(
            "same_run_completed_receipt_has_invalid_candidate_clock_use_new_run_scope"
        ) from exc
    now = datetime.now(timezone.utc)
    if (
        available_at.tzinfo is None
        or available_at.utcoffset() != timedelta(0)
        or frozen_at.tzinfo is None
        or frozen_at.utcoffset() != timedelta(0)
        or available_at < frozen_at
        or available_at > now
    ):
        raise _SameRunInputConflict(
            "same_run_completed_receipt_candidate_clock_is_not_verified_utc_use_new_run_scope"
        )


def _verify_completed_no_candidate_receipt(
    receipt: Mapping[str, Any],
    *,
    run_id: str,
    decision_date: str,
    run_scope: str | None,
    dataset_hash: str,
    cost_scenario: RecommendationCostScenario,
) -> None:
    if (
        receipt.get("run_id") != run_id
        or receipt.get("decision_date") != decision_date
        or receipt.get("run_scope") != run_scope
        or receipt.get("dataset_hash") != dataset_hash
        or receipt.get("cost_scenario_hash") != cost_scenario.scenario_hash
        or receipt.get("candidate_id") is not None
        or receipt.get("candidate_root") is not None
    ):
        raise _SameRunInputConflict(
            "same_run_no_candidate_receipt_input_changed_use_new_run_scope"
        )


def _available_at_after_freeze(created_at: str) -> str:
    try:
        frozen_at = datetime.fromisoformat(created_at)
    except ValueError as exc:
        raise _SameRunInputConflict(
            "same_run_candidate_freeze_clock_invalid_use_new_run_scope"
        ) from exc
    available_at = datetime.now(timezone.utc)
    if (
        frozen_at.tzinfo is None
        or frozen_at.utcoffset() != timedelta(0)
        or available_at < frozen_at
    ):
        raise _SameRunInputConflict(
            "same_run_candidate_freeze_is_after_current_clock_investigate_clock_or_use_new_scope"
        )
    return available_at.isoformat(timespec="microseconds")


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
        lineage_path = _resolve_io_path(candidate_root / lineage_path)
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
    payload = json.loads(_io_path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"JSON payload must be an object: {path}")
    return dict(payload)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    _io_path(path.parent).mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    _io_path(temporary).write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    _io_path(temporary).replace(_io_path(path))


def _write_json_once(path: Path, payload: Mapping[str, Any]) -> None:
    _io_path(path.parent).mkdir(parents=True, exist_ok=True)
    if _io_path(path).exists():
        existing = _read_mapping(path)
        if existing != dict(payload):
            raise RuntimeError(f"immutable daily recommendation receipt conflict: {path}")
        return
    _io_path(path).write_text(
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
