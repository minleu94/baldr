"""有界、可恢復、每日冪等的推薦 calibration runner。

上游資料更新與自然 forward outcome producer 由既有排程負責；本 runner 只接
收它們的唯讀 dependency status 與成熟樣本，然後建立版本化 dataset、candidate、
same-date/same-cost evaluation、promotion decision receipt。沒有新資料、成熟度
不足或任何 dependency fault 時保留 last-good/rule，不偽造自然時間成熟度。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from ml_module.model_artifact_manifest import FeatureSchema
from ml_module.recommendation_calibration_authority import (
    RecommendationCalibrationPromotionAuthority,
)
from ml_module.recommendation_calibration_training import (
    RecommendationCalibrationSample,
    RecommendationCalibrationTrainingConfig,
    RecommendationCalibrationTrainingResult,
    RecommendationCalibrationTrainingService,
)


@dataclass(frozen=True)
class DailyRecommendationLearningResult:
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


class DailyRecommendationLearningRunner:
    """Orchestrate one bounded day without writing formal data or order state."""

    def __init__(
        self,
        *,
        output_root: str | Path,
        feature_names: tuple[str, ...],
        feature_schema: FeatureSchema,
        feature_registry_hash: str,
        fixed_round_trip_cost_bp: int,
        training_config: RecommendationCalibrationTrainingConfig | None = None,
        training_service: RecommendationCalibrationTrainingService | None = None,
        authority: RecommendationCalibrationPromotionAuthority | None = None,
    ) -> None:
        self.root = Path(output_root).resolve() / "recommendation_learning"
        self.runs_root = self.root / "runs"
        self.feature_names = feature_names
        self.feature_schema = feature_schema
        self.feature_registry_hash = feature_registry_hash
        self.fixed_round_trip_cost_bp = fixed_round_trip_cost_bp
        self.training_config = training_config or RecommendationCalibrationTrainingConfig()
        self.training_service = training_service or RecommendationCalibrationTrainingService()
        self.authority = authority or RecommendationCalibrationPromotionAuthority(self.root)

    def run(
        self,
        *,
        decision_date: str,
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
    ) -> DailyRecommendationLearningResult:
        day = date.fromisoformat(decision_date[:10]).isoformat()
        run_id = f"daily-recommendation-learning:{day}"
        run_dir = self.runs_root / day
        receipt_path = run_dir / "run_receipt.json"
        latest_path = self.root / "latest_status.json"
        training_cutoff = day if training_as_of is None else date.fromisoformat(training_as_of[:10]).isoformat()
        eligible_samples = tuple(
            row
            for row in samples
            if date.fromisoformat(row.decision_date[:10]) <= date.fromisoformat(training_cutoff)
            and date.fromisoformat(row.label_available_date[:10]) <= date.fromisoformat(training_cutoff)
        )
        dataset_hash = _dataset_hash(eligible_samples)
        if receipt_path.is_file() and not emergency_rollback:
            existing = json.loads(receipt_path.read_text(encoding="utf-8"))
            if existing.get("dataset_hash") != dataset_hash:
                raise RuntimeError("same daily run id received a different dataset; refusing overwrite")
            if existing.get("decision") in {"adopt", "rollback"}:
                return _result_from_receipt(existing, idempotent=True, latest_status_path=latest_path)
            if (
                natural_evidence is not None
                and existing.get("decision") == "retain_current"
                and existing.get("candidate_root")
                and existing.get("candidate_id")
            ):
                candidate_root = Path(str(existing["candidate_root"])).resolve()
                candidate_metadata_path = candidate_root / "candidate.json"
                if candidate_metadata_path.is_file():
                    candidate_metadata = json.loads(candidate_metadata_path.read_text(encoding="utf-8"))
                    retry_evidence = natural_evidence
                    if callable(retry_evidence):
                        raise ValueError("same-day evidence retry requires a materialized receipt reference")
                    decision = self.authority.evaluate_and_apply(
                        decision_date=day,
                        candidate_id=str(existing["candidate_id"]),
                        candidate_root=candidate_root,
                        candidate_metadata=candidate_metadata,
                        natural_evidence=retry_evidence,
                        data_status=data_dependency_status,
                        drift_status=drift_status,
                    )
                    retry_receipt_path = run_dir / f"run_receipt-retry-{_evidence_id(retry_evidence)}.json"
                    retry_receipt = {
                        **existing,
                        "receipt_path": str(retry_receipt_path),
                        "reason": "same_day_natural_evidence_retry",
                        "natural_matured_sample_count": _evidence_count(retry_evidence),
                        "decision": decision.decision,
                        "decision_reason": decision.reason,
                        "decision_receipt": decision.to_dict(),
                        "steps": {
                            **dict(existing.get("steps", {})),
                            "same_date_same_cost_comparison": "recomputed_from_materialized_natural_receipt",
                            "promotion_gate": "completed",
                        },
                    }
                    _write_json_once(retry_receipt_path, retry_receipt)
                    _write_json(latest_path, retry_receipt)
                    return _result_from_receipt(retry_receipt, idempotent=False, latest_status_path=latest_path)
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
            receipt = {
                "schema_version": "daily-recommendation-learning-receipt.v1",
                "run_id": run_id,
                "decision_date": day,
                "receipt_path": str(receipt_path.with_name("run_receipt-emergency-rollback.json")),
                "status": "completed",
                "finalized": True,
                "recoverable": False,
                "reason": (
                    "explicit_emergency_rollback_evaluated_without_new_candidate"
                    if emergency_rollback
                    else "emergency_rollback_evaluated_without_new_candidate"
                ),
                "dataset_id": None,
                "dataset_hash": dataset_hash,
                "candidate_id": None,
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
                    "same_date_same_cost_comparison": "skipped",
                    "promotion_gate": "completed_rollback_or_rule_only",
                },
                "formal_order_allowed": False,
                "shadow_only": True,
            }
            emergency_receipt_path = run_dir / "run_receipt-emergency-rollback.json"
            _write_json_once(emergency_receipt_path, receipt)
            _write_json(latest_path, receipt)
            return DailyRecommendationLearningResult(
                run_id=run_id,
                status="completed",
                reason=(
                    "explicit_emergency_rollback_evaluated_without_new_candidate"
                    if emergency_rollback
                    else "emergency_rollback_evaluated_without_new_candidate"
                ),
                receipt_path=str(emergency_receipt_path),
                latest_status_path=str(latest_path),
                dataset_id=None,
                dataset_hash=dataset_hash,
                candidate_id=None,
                decision=decision.decision,
                decision_reason=decision.reason,
            )
        frozen_root = Path(frozen_candidate_root).resolve() if frozen_candidate_root is not None else None
        frozen_metadata: dict[str, Any] | None = None
        if frozen_root is not None:
            try:
                frozen_metadata = json.loads((frozen_root / "candidate.json").read_text(encoding="utf-8"))
                if not isinstance(frozen_metadata, dict) or not frozen_metadata.get("candidate_id"):
                    raise ValueError("frozen challenger identity is missing")
            except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
                return self._write_skip(
                    day=day,
                    run_id=run_id,
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
        if data_dependency_status.lower() not in {"ready", "observed", "not_checked"}:
            return self._write_skip(
                day=day,
                run_id=run_id,
                reason="data_dependency_failed_fail_closed",
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
                reason="outcome_dependency_unavailable_natural_evidence_not_fabricated",
                status="skipped_insufficient_evidence",
                dataset_hash=dataset_hash,
                decision="retain_current",
                decision_reason="outcome_dependency_unavailable_natural_evidence_not_fabricated",
                natural_matured_sample_count=_evidence_count(natural_evidence),
                data_dependency_status=data_dependency_status,
                outcome_dependency_status=outcome_dependency_status,
                drift_status=drift_status,
            )
        if not eligible_samples and frozen_root is None:
            return self._write_skip(
                day=day,
                run_id=run_id,
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
                    dataset_quality=dataset_quality,
                    created_at=f"{day}T00:00:00+00:00",
                    config=self.training_config,
                )
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                return self._write_skip(
                    day=day,
                    run_id=run_id,
                    reason=f"candidate_training_failed:{type(exc).__name__}",
                    status="failed_training",
                    dataset_hash=dataset_hash,
                    decision="retain_current",
                    decision_reason="candidate_training_failed_fail_closed",
                    natural_matured_sample_count=_evidence_count(natural_evidence),
                    data_dependency_status=data_dependency_status,
                    outcome_dependency_status=outcome_dependency_status,
                    drift_status=drift_status,
                )
            candidate_root = run_dir / "candidates" / result.candidate_id
            if not candidate_root.exists():
                result.persist(candidate_root)
            candidate_metadata = json.loads((candidate_root / "candidate.json").read_text(encoding="utf-8"))
        else:
            candidate_root = frozen_root
            candidate_metadata = frozen_metadata or {}
        candidate_id = str(candidate_metadata.get("candidate_id") or "")
        if fault_after_candidate:
            raise RuntimeError("injected_fault_after_candidate")
        resolved_evidence: Mapping[str, Any] | None
        if callable(natural_evidence):
            resolved_evidence = natural_evidence(result, candidate_metadata)
        else:
            resolved_evidence = natural_evidence
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
        receipt = {
            "schema_version": "daily-recommendation-learning-receipt.v1",
            "run_id": run_id,
            "decision_date": day,
            "receipt_path": str(receipt_path),
            "status": "completed",
            "finalized": True,
            "recoverable": False,
            "reason": "candidate_trained_and_gate_evaluated",
            "dataset_id": dataset_id,
            "dataset_hash": dataset_hash,
            "training_as_of": training_cutoff,
            "candidate_id": candidate_id,
            "candidate_root": str(candidate_root),
            "candidate_manifest_hash": candidate_metadata.get("manifest_hash"),
            "candidate_artifact_hash": candidate_metadata.get("artifact_hash"),
            "candidate_dataset_id": candidate_metadata.get("dataset_id"),
            "candidate_dataset_hash": candidate_metadata.get("dataset_hash"),
            "training_row_count": result.training_row_count if result is not None else candidate_metadata.get("training_row_count"),
            "calibration_sample_count": result.model.calibration_sample_count if result is not None else candidate_metadata.get("calibration_sample_count"),
            "calibration_gap_bp": result.calibration_gap_bp if result is not None else candidate_metadata.get("calibration_gap_bp"),
            "evaluation": dict(result.evaluation) if result is not None else dict(candidate_metadata.get("evaluation", {})),
            "natural_matured_sample_count": _evidence_count(resolved_evidence),
            "data_dependency_status": data_dependency_status,
            "outcome_dependency_status": outcome_dependency_status,
            "decision": decision.decision,
            "decision_reason": decision.reason,
            "next_step": _next_step(decision.decision, decision.reason),
            "decision_receipt": decision.to_dict(),
            "steps": {
                "dependency_check": "completed",
                "dataset_build": "completed",
                "candidate_training": "completed" if result is not None else "reused_frozen_challenger",
                "same_date_same_cost_comparison": "completed",
                "promotion_gate": "completed",
            },
            "formal_order_allowed": False,
            "shadow_only": True,
        }
        _write_json_once(receipt_path, receipt)
        _write_json(latest_path, receipt)
        return DailyRecommendationLearningResult(
            run_id=run_id,
            status="completed",
            reason="candidate_trained_and_gate_evaluated",
            receipt_path=str(receipt_path),
            latest_status_path=str(latest_path),
            dataset_id=dataset_id,
            dataset_hash=dataset_hash,
            candidate_id=candidate_id,
            decision=decision.decision,
            decision_reason=decision.reason,
            candidate_root=str(candidate_root),
        )

    def _write_skip(
        self,
        *,
        day: str,
        run_id: str,
        reason: str,
        status: str,
        dataset_hash: str,
        decision: str,
        decision_reason: str,
        natural_matured_sample_count: int,
        data_dependency_status: str = "not_checked",
        outcome_dependency_status: str = "not_checked",
        drift_status: str = "not_checked",
    ) -> DailyRecommendationLearningResult:
        run_dir = self.runs_root / day
        attempt_id = "attempt-" + hashlib.sha256(
            f"{run_id}|{status}|{reason}|{dataset_hash}".encode("utf-8")
        ).hexdigest()[:24]
        receipt_path = run_dir / "attempts" / f"{attempt_id}.json"
        latest_path = self.root / "latest_status.json"
        receipt = {
            "schema_version": "daily-recommendation-learning-receipt.v1",
            "run_id": run_id,
            "decision_date": day,
            "receipt_path": str(receipt_path),
            "attempt_id": attempt_id,
            "finalized": False,
            "recoverable": True,
            "status": status,
            "reason": reason,
            "dataset_id": None,
            "dataset_hash": dataset_hash,
            "candidate_id": None,
            "natural_matured_sample_count": natural_matured_sample_count,
            "data_dependency_status": data_dependency_status,
            "outcome_dependency_status": outcome_dependency_status,
            "drift_status": drift_status,
            "decision": decision,
            "decision_reason": decision_reason,
            "next_step": _next_step(decision, decision_reason),
            "steps": {
                "dependency_check": "completed",
                "dataset_build": "skipped",
                "candidate_training": "skipped",
                "same_date_same_cost_comparison": "skipped",
                "promotion_gate": "completed_retain_current",
            },
            "formal_order_allowed": False,
            "shadow_only": True,
        }
        _write_json_once(receipt_path, receipt)
        _write_json(latest_path, receipt)
        return DailyRecommendationLearningResult(
            run_id=run_id,
            status=status,
            reason=reason,
            receipt_path=str(receipt_path),
            latest_status_path=str(latest_path),
            dataset_id=None,
            dataset_hash=dataset_hash,
            candidate_id=None,
            decision=decision,
            decision_reason=decision_reason,
        )


def _dataset_hash(samples: Sequence[RecommendationCalibrationSample]) -> str:
    payload = [asdict(row) for row in sorted(samples, key=lambda item: (item.decision_date, item.row_id))]
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"sha256:{digest}"


def _evidence_count(evidence: Any) -> int:
    if not isinstance(evidence, Mapping):
        receipt_path = getattr(evidence, "receipt_path", None)
        if receipt_path:
            try:
                payload = json.loads(Path(str(receipt_path)).read_text(encoding="utf-8"))
                return max(0, int(payload.get("matured_sample_count", 0)))
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                return 0
        return 0
    try:
        value = evidence.get("matured_sample_count", 0)
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _write_json_once(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != payload:
            raise RuntimeError("immutable daily recommendation receipt conflict")
        return
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _result_from_receipt(
    payload: Mapping[str, Any],
    *,
    idempotent: bool,
    latest_status_path: Path | None = None,
) -> DailyRecommendationLearningResult:
    return DailyRecommendationLearningResult(
        run_id=str(payload["run_id"]),
        status=str(payload["status"]),
        reason=str(payload["reason"]),
        receipt_path=str(payload.get("receipt_path", "")),
        latest_status_path=str(latest_status_path) if latest_status_path is not None else str(payload.get("latest_status_path", "")),
        dataset_id=payload.get("dataset_id"),
        dataset_hash=payload.get("dataset_hash"),
        candidate_id=payload.get("candidate_id"),
        decision=str(payload.get("decision", "retain_current")),
        decision_reason=str(payload.get("decision_reason", "")),
        idempotent_replay=idempotent,
        candidate_root=payload.get("candidate_root"),
    )


def _evidence_id(evidence: Any) -> str:
    if isinstance(evidence, Mapping):
        value = evidence.get("evidence_id") or evidence.get("receipt_hash")
    else:
        value = getattr(evidence, "evidence_id", None) or getattr(evidence, "receipt_hash", None)
    text = str(value or "natural")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _next_step(decision: str, reason: str) -> str:
    if decision == "adopt":
        return "保留 shadow candidate 的自然 forward capture，確認 active pointer 與 consumer 仍可重載。"
    if decision == "rollback":
        return "檢查資料／drift fault 與 last-good pointer；修復後以新日重試，不覆寫當日 receipt。"
    if "no_data" in reason or "insufficient" in reason or "matured" in reason:
        return "等待新的成熟自然 forward outcomes；未達門檻前保留 current/rule-only。"
    if "fault" in reason or "failed" in reason or "unavailable" in reason:
        return "修復 dependency 或資料品質問題後，以新日重新執行 bounded runner。"
    return "保留 current；下一個排程日重新檢查同樣本、同成本與自然成熟度。"
