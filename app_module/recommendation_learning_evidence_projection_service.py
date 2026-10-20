"""Recommendation learning／natural evidence 的唯讀 typed projection。

這個 service 是 UI read model 的單一入口：只讀隔離 learning root、active
consumer 與既有 verifier，不執行 learning runner、forward outcome、promotion
或任何寫入。latest_status 的 count／bool 只用來描述「排程回報」，只有
verifier 成功回傳的 comparison 才能進入 reliability bins。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from app_module.recommendation_calibration_consumer import (
    RecommendationCalibrationConsumer,
)
from app_module.recommendation_learning_paths import (
    RecommendationLearningPathError,
    RecommendationLearningPaths,
    resolve_recommendation_learning_paths,
)
from ml_module.recommendation_calibration_authority import (
    RecommendationNaturalEvidenceComparison,
    RecommendationNaturalEvidenceVerification,
    RecommendationPromotionPolicy,
    verify_natural_evidence_read_only,
)
from ml_module.recommendation_cost_scenario import (
    RecommendationCostScenario,
    RecommendationCostScenarioError,
    cost_scenario_from_metadata,
)
from ml_module.recommendation_natural_outcome_service import (
    verify_active_model_evidence_payload,
)
from ml_module.recommendation_calibration_evidence import (
    RecommendationPredictionCaptureVerification,
    verify_prediction_capture_read_only,
)
from app_module.sqlite_read_only import (
    ReadOperationCancelled,
    check_read_cancelled,
    cooperative_read_cancellation,
)


PROJECTION_SCHEMA_VERSION = "recommendation-learning-evidence-projection.v1"
DEFAULT_HORIZON_TRADING_DAYS = 20
PROBABILITY_BINS_BP: tuple[tuple[int, int], ...] = (
    (0, 2_000),
    (2_000, 4_000),
    (4_000, 6_000),
    (6_000, 8_000),
    (8_000, 10_001),
)


@dataclass(frozen=True)
class LearningHorizonProjection:
    horizon_days: int
    capture_count: int = 0
    recorded_row_count: int = 0
    matured_sample_count: int = 0
    matured_decision_date_count: int = 0
    status: str = "unknown"
    reason: str = ""
    valid_prediction_row_count: int = 0
    valid_prediction_decision_date_count: int = 0
    pending_prediction_row_count: int = 0
    pending_prediction_decision_date_count: int = 0
    pending_prediction_status: str = "unknown"
    invalid_capture_count: int = 0
    capture_conflict_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "horizon_days": self.horizon_days,
            "capture_count": self.capture_count,
            "recorded_row_count": self.recorded_row_count,
            "matured_sample_count": self.matured_sample_count,
            "matured_decision_date_count": self.matured_decision_date_count,
            "status": self.status,
            "reason": self.reason,
            "valid_prediction_row_count": self.valid_prediction_row_count,
            "valid_prediction_decision_date_count": self.valid_prediction_decision_date_count,
            "pending_prediction_row_count": self.pending_prediction_row_count,
            "pending_prediction_decision_date_count": self.pending_prediction_decision_date_count,
            "pending_prediction_status": self.pending_prediction_status,
            "invalid_capture_count": self.invalid_capture_count,
            "capture_conflict_count": self.capture_conflict_count,
        }


@dataclass(frozen=True)
class LearningReliabilityBin:
    """已驗證的 predicted probability → observed outcome bucket。"""

    target: str
    lower_probability_bp: int
    upper_probability_bp_exclusive: int
    predicted_probability_bp: int
    matured_actual_up_ratio_bp: int
    sample_count: int
    decision_date_count: int
    period_start: str | None
    period_end: str | None
    lane_id: str
    status: str = "verified"
    research_only: bool = False

    @property
    def upper_probability_bp(self) -> int:
        return min(10_000, self.upper_probability_bp_exclusive)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "lower_probability_bp": self.lower_probability_bp,
            "upper_probability_bp_exclusive": self.upper_probability_bp_exclusive,
            "predicted_probability_bp": self.predicted_probability_bp,
            "matured_actual_up_ratio_bp": self.matured_actual_up_ratio_bp,
            "sample_count": self.sample_count,
            "decision_date_count": self.decision_date_count,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "lane_id": self.lane_id,
            "status": self.status,
            "research_only": self.research_only,
        }


@dataclass(frozen=True)
class LearningLaneProjection:
    lane_id: str
    label: str
    status: str
    reason: str
    candidate_id: str | None = None
    model_version: str | None = None
    dataset_version: str | None = None
    training_as_of: str | None = None
    cost_basis: str | None = None
    cost_scenario_id: str | None = None
    cost_scenario_version: str | None = None
    cost_scenario_hash: str | None = None
    cost_estimate_status: str | None = None
    after_cost_lane_status: str = "not_available"
    capture_status: str = "not_recorded"
    capture_count: int = 0
    recorded_row_count: int = 0
    matured_sample_count: int = 0
    matured_decision_date_count: int = 0
    valid_prediction_row_count: int = 0
    valid_prediction_decision_date_count: int = 0
    pending_prediction_row_count: int = 0
    pending_prediction_decision_date_count: int = 0
    pending_prediction_status: str = "unknown"
    invalid_capture_count: int = 0
    capture_conflict_count: int = 0
    capture_scan_status: str = "not_scanned"
    latest_snapshot_row_count: int = 0
    latest_snapshot_capture_count: int = 0
    latest_snapshot_lane_id: str | None = None
    latest_snapshot_candidate_id: str | None = None
    latest_snapshot_cost_scenario_id: str | None = None
    latest_snapshot_cost_scenario_hash: str | None = None
    latest_snapshot_horizon_days: int | None = None
    latest_snapshot_decision_date: str | None = None
    policy_binding_status: str = "unknown"
    policy_hash: str | None = None
    policy_minimum_natural_matured_samples: int | None = None
    policy_minimum_natural_matured_decision_dates: int | None = None
    period_start: str | None = None
    period_end: str | None = None
    brier_bp: int | None = None
    calibration_gap_bp: int | None = None
    brier_improvement_bp: int | None = None
    after_cost_brier_bp: int | None = None
    after_cost_calibration_gap_bp: int | None = None
    evidence_id: str | None = None
    receipt_path: str | None = None
    receipt_hash: str | None = None
    horizons: tuple[LearningHorizonProjection, ...] = ()
    reliability_bins: tuple[LearningReliabilityBin, ...] = ()
    diagnostics: tuple[str, ...] = ()
    source_trace: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "horizons", tuple(self.horizons))
        object.__setattr__(self, "reliability_bins", tuple(self.reliability_bins))
        object.__setattr__(self, "diagnostics", tuple(str(item) for item in self.diagnostics))
        object.__setattr__(self, "source_trace", tuple(str(item) for item in self.source_trace))

    @property
    def verified(self) -> bool:
        return self.status == "verified"

    def to_dict(self) -> dict[str, Any]:
        return {
            "lane_id": self.lane_id,
            "label": self.label,
            "status": self.status,
            "reason": self.reason,
            "candidate_id": self.candidate_id,
            "model_version": self.model_version,
            "dataset_version": self.dataset_version,
            "training_as_of": self.training_as_of,
            "cost_basis": self.cost_basis,
            "cost_scenario_id": self.cost_scenario_id,
            "cost_scenario_version": self.cost_scenario_version,
            "cost_scenario_hash": self.cost_scenario_hash,
            "cost_estimate_status": self.cost_estimate_status,
            "after_cost_lane_status": self.after_cost_lane_status,
            "capture_status": self.capture_status,
            "capture_count": self.capture_count,
            "recorded_row_count": self.recorded_row_count,
            "matured_sample_count": self.matured_sample_count,
            "matured_decision_date_count": self.matured_decision_date_count,
            "valid_prediction_row_count": self.valid_prediction_row_count,
            "valid_prediction_decision_date_count": self.valid_prediction_decision_date_count,
            "pending_prediction_row_count": self.pending_prediction_row_count,
            "pending_prediction_decision_date_count": self.pending_prediction_decision_date_count,
            "pending_prediction_status": self.pending_prediction_status,
            "invalid_capture_count": self.invalid_capture_count,
            "capture_conflict_count": self.capture_conflict_count,
            "capture_scan_status": self.capture_scan_status,
            "latest_snapshot_row_count": self.latest_snapshot_row_count,
            "latest_snapshot_capture_count": self.latest_snapshot_capture_count,
            "latest_snapshot_lane_id": self.latest_snapshot_lane_id,
            "latest_snapshot_candidate_id": self.latest_snapshot_candidate_id,
            "latest_snapshot_cost_scenario_id": self.latest_snapshot_cost_scenario_id,
            "latest_snapshot_cost_scenario_hash": self.latest_snapshot_cost_scenario_hash,
            "latest_snapshot_horizon_days": self.latest_snapshot_horizon_days,
            "latest_snapshot_decision_date": self.latest_snapshot_decision_date,
            "policy_binding_status": self.policy_binding_status,
            "policy_hash": self.policy_hash,
            "policy_minimum_natural_matured_samples": self.policy_minimum_natural_matured_samples,
            "policy_minimum_natural_matured_decision_dates": self.policy_minimum_natural_matured_decision_dates,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "brier_bp": self.brier_bp,
            "calibration_gap_bp": self.calibration_gap_bp,
            "brier_improvement_bp": self.brier_improvement_bp,
            "after_cost_brier_bp": self.after_cost_brier_bp,
            "after_cost_calibration_gap_bp": self.after_cost_calibration_gap_bp,
            "evidence_id": self.evidence_id,
            "receipt_path": self.receipt_path,
            "receipt_hash": self.receipt_hash,
            "horizons": [item.to_dict() for item in self.horizons],
            "reliability_bins": [item.to_dict() for item in self.reliability_bins],
            "diagnostics": list(self.diagnostics),
            "source_trace": list(self.source_trace),
        }


@dataclass(frozen=True)
class RecommendationLearningEvidenceProjection:
    """Workbench／Research Console 共用的唯讀 learning read model。"""

    schema_version: str
    status: str
    requested_date: str | None
    learning_decision_date: str | None
    checked_at: str | None
    decision: str
    decision_reason: str
    candidate_id: str | None
    candidate_model_version: str | None
    candidate_training_as_of: str | None
    data_recorded_status: str
    data_recorded_reason: str
    next_gap: str
    adoption_reason: str
    candidate_lane: LearningLaneProjection
    active_lane: LearningLaneProjection
    horizons: tuple[LearningHorizonProjection, ...] = ()
    horizon_scope_lane_id: str | None = None
    horizon_scope_label: str | None = None
    horizon_scope_model_version: str | None = None
    horizon_scope_cost_scenario_id: str | None = None
    historical_evaluation_status: str = "research_only_not_natural"
    historical_evaluation_sample_count: int = 0
    historical_evaluation_note: str = (
        "evaluation／untouched test 僅為 historical replay，不能與 natural evidence 混算。"
    )
    warnings: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()
    source_trace: tuple[str, ...] = ()
    read_only: bool = True
    cost_lane: str = "banktaiwan_estimated_research"

    def __post_init__(self) -> None:
        if not self.read_only:
            raise ValueError("learning evidence projection must remain read-only")
        object.__setattr__(self, "horizons", tuple(self.horizons))
        object.__setattr__(self, "warnings", tuple(str(item) for item in self.warnings))
        object.__setattr__(self, "diagnostics", tuple(str(item) for item in self.diagnostics))
        object.__setattr__(self, "source_trace", tuple(str(item) for item in self.source_trace))

    @property
    def verified_lane(self) -> LearningLaneProjection | None:
        for lane in (self.active_lane, self.candidate_lane):
            if lane.verified:
                return lane
        return None

    @property
    def reliability_bins(self) -> tuple[LearningReliabilityBin, ...]:
        lane = self.verified_lane
        return lane.reliability_bins if lane is not None else ()

    @property
    def latest_evaluation_label(self) -> str:
        lane = self.verified_lane
        if lane is None:
            return "尚無已驗證 natural matured evaluation"
        return (
            f"{lane.label}｜{lane.matured_sample_count} 筆／"
            f"{lane.matured_decision_date_count} 個決策日｜"
            f"Brier {lane.brier_bp if lane.brier_bp is not None else '未知'} bp｜"
            f"calibration gap {lane.calibration_gap_bp if lane.calibration_gap_bp is not None else '未知'} bp"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "requested_date": self.requested_date,
            "learning_decision_date": self.learning_decision_date,
            "checked_at": self.checked_at,
            "decision": self.decision,
            "decision_reason": self.decision_reason,
            "candidate_id": self.candidate_id,
            "candidate_model_version": self.candidate_model_version,
            "candidate_training_as_of": self.candidate_training_as_of,
            "data_recorded_status": self.data_recorded_status,
            "data_recorded_reason": self.data_recorded_reason,
            "next_gap": self.next_gap,
            "adoption_reason": self.adoption_reason,
            "candidate_lane": self.candidate_lane.to_dict(),
            "active_lane": self.active_lane.to_dict(),
            "horizons": [item.to_dict() for item in self.horizons],
            "horizon_scope_lane_id": self.horizon_scope_lane_id,
            "horizon_scope_label": self.horizon_scope_label,
            "horizon_scope_model_version": self.horizon_scope_model_version,
            "horizon_scope_cost_scenario_id": self.horizon_scope_cost_scenario_id,
            "historical_evaluation_status": self.historical_evaluation_status,
            "historical_evaluation_sample_count": self.historical_evaluation_sample_count,
            "historical_evaluation_note": self.historical_evaluation_note,
            "latest_evaluation": self.latest_evaluation_label,
            "warnings": list(self.warnings),
            "diagnostics": list(self.diagnostics),
            "source_trace": list(self.source_trace),
            "read_only": self.read_only,
            "cost_lane": self.cost_lane,
        }


@dataclass(frozen=True)
class _ObservedRow:
    probability_bp: int
    label: int
    after_cost_probability_bp: int | None
    after_cost_label: int | None
    decision_date: str
    label_end_date: str | None


@dataclass(frozen=True)
class _CaptureDenominator:
    """將已驗證 capture 累積分母與 latest snapshot 分開保存。"""

    valid_capture_count: int = 0
    valid_prediction_row_count: int = 0
    valid_prediction_decision_date_count: int = 0
    invalid_capture_count: int = 0
    capture_conflict_count: int = 0
    capture_scan_status: str = "not_scanned"
    diagnostics: tuple[str, ...] = ()
    valid_decision_dates: tuple[str, ...] = ()
    latest_snapshot_row_count: int = 0
    latest_snapshot_capture_count: int = 0
    latest_snapshot_candidate_id: str | None = None
    latest_snapshot_cost_scenario_id: str | None = None
    latest_snapshot_cost_scenario_hash: str | None = None
    latest_snapshot_decision_date: str | None = None


@dataclass(frozen=True)
class _PolicyBinding:
    """只有既有 authority verifier 證明綁定後才暴露 policy 門檻。"""

    status: str = "unknown"
    policy_hash: str | None = None
    minimum_natural_matured_samples: int | None = None
    minimum_natural_matured_decision_dates: int | None = None
    reason: str = "promotion_policy_binding_unknown"


class RecommendationLearningEvidenceProjectionService:
    """Read-only adapter for daily learning status and natural evidence."""

    def __init__(
        self,
        config: Any | None = None,
        *,
        paths: RecommendationLearningPaths | None = None,
        latest_status_path: str | Path | None = None,
        active_pointer_path: str | Path | None = None,
        learning_root: str | Path | None = None,
        cost_lane: str = "banktaiwan_estimated_research",
        consumer: RecommendationCalibrationConsumer | None = None,
        candidate_verifier: Callable[..., RecommendationNaturalEvidenceVerification] = verify_natural_evidence_read_only,
        active_verifier: Callable[..., None] = verify_active_model_evidence_payload,
        capture_verifier: Callable[..., RecommendationPredictionCaptureVerification] = verify_prediction_capture_read_only,
        requested_date_resolver: Callable[[], str | None] | None = None,
        capture_scan_limit: int = 256,
    ) -> None:
        self.config = config
        self.cost_lane = _normalize_cost_lane(cost_lane)
        if paths is None:
            if learning_root is None:
                try:
                    paths = resolve_recommendation_learning_paths(
                        data_root=getattr(config, "data_root", None),
                        explicit_output_root=_default_lane_output_root(
                            getattr(config, "data_root", None),
                            self.cost_lane,
                        ),
                    )
                except RecommendationLearningPathError:
                    paths = None
            else:
                resolved_output_root = Path(learning_root).resolve()
                paths = RecommendationLearningPaths(
                    data_root=Path(getattr(config, "data_root", "F:/Min/Python/Project/FA_Data")).resolve(),
                    output_root=resolved_output_root,
                )
        self.paths = paths
        resolved_root: Path | None = (
            Path(learning_root).resolve()
            if learning_root is not None
            else (paths.learning_root if paths is not None else None)
        )
        self.learning_root = resolved_root
        self.latest_status_path: Path | None = (
            Path(latest_status_path).resolve()
            if latest_status_path is not None
            else (paths.latest_status_path if paths is not None else None)
        )
        self.active_pointer_path: Path | None = (
            Path(active_pointer_path).resolve()
            if active_pointer_path is not None
            else (paths.active_pointer_path if paths is not None else None)
        )
        self.consumer = consumer
        if self.consumer is None and config is not None and paths is not None:
            self.consumer = _build_consumer_for_paths(config, paths)
        self.candidate_verifier = candidate_verifier
        self.active_verifier = active_verifier
        self.capture_verifier = capture_verifier
        self.requested_date_resolver = requested_date_resolver
        if isinstance(capture_scan_limit, bool) or int(capture_scan_limit) < 0:
            raise ValueError("capture_scan_limit must be a non-negative integer")
        self.capture_scan_limit = int(capture_scan_limit)

    def _configured_source_database_anchor(self) -> Path | None:
        """讀取既有設定提供的市場資料庫錨點，不採用 receipt 自報路徑。"""

        configured = getattr(self.config, "db_file", None)
        if configured is None:
            return None
        try:
            path = Path(configured).expanduser().resolve()
        except (OSError, TypeError, ValueError):
            return None
        if path.is_symlink() or not path.is_file():
            return None
        return path

    def inspect(
        self,
        requested_date: str | None = None,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> RecommendationLearningEvidenceProjection:
        with cooperative_read_cancellation(cancel_callback):
            return self._inspect(requested_date)

    def _inspect(self, requested_date: str | None = None) -> RecommendationLearningEvidenceProjection:
        check_read_cancelled()
        diagnostics: list[str] = []
        warnings: list[str] = []
        if self.latest_status_path is None:
            return self._empty_projection(
                requested_date=_date_key(requested_date),
                status="missing",
                reason="recommendation_learning_output_root_invalid",
                diagnostics=["recommendation_learning_output_root_invalid"],
            )
        status_payload, status_error = _read_json_object(self.latest_status_path)
        check_read_cancelled()
        if status_error is not None:
            return self._empty_projection(
                requested_date=_date_key(requested_date),
                status="read_failure" if self.latest_status_path.exists() else "missing",
                reason=status_error,
                diagnostics=[status_error],
            )
        assert status_payload is not None
        learning_date = _date_key(status_payload.get("decision_date"))
        requested = _date_key(requested_date)
        if requested is None:
            try:
                resolved_requested_date = (
                    self.requested_date_resolver()
                    if self.requested_date_resolver is not None
                    else _resolve_default_requested_date(self.config)
                )
            except (OSError, TypeError, ValueError, KeyError):
                check_read_cancelled()
                resolved_requested_date = None
            requested = _date_key(resolved_requested_date)
            check_read_cancelled()
        date_status = _date_scope_status(learning_date, requested)
        if date_status in {"future_blocked", "stale", "unknown"}:
            diagnostics.append(
                f"recommendation_learning_{date_status}:{learning_date or 'unknown'}:requested={requested or 'unknown'}"
            )

        candidate, candidate_metadata, candidate_root, candidate_diagnostics = self._candidate_context(
            status_payload,
            requested_date=requested,
        )
        check_read_cancelled()
        diagnostics.extend(candidate_diagnostics)
        candidate_lane = self._candidate_lane(
            status_payload,
            candidate=candidate,
            candidate_metadata=candidate_metadata,
            candidate_root=candidate_root,
            requested_date=requested,
            date_status=date_status,
            diagnostics=diagnostics,
        )
        check_read_cancelled()
        active_lane = self._active_lane(
            status_payload,
            requested_date=requested,
            date_status=date_status,
            diagnostics=diagnostics,
        )
        check_read_cancelled()

        live_capture = _mapping(status_payload.get("live_capture"))
        candidate_capture = _mapping(live_capture.get("candidate")) or live_capture
        data_recorded_status, data_recorded_reason = _capture_surface(
            candidate_capture,
            candidate_id=candidate_lane.candidate_id,
            learning_root=self.learning_root,
            requested_date=requested,
            date_status=date_status,
            conflict_symbols=(
                _strings(candidate_capture.get("cross_capture_feature_conflict_symbols"))
                + _strings(candidate_capture.get("cross_capture_source_conflict_symbols"))
            ),
            capture_verifier=self.capture_verifier,
        )
        check_read_cancelled()
        if candidate_lane.status == "blocked_provenance" and data_recorded_status == "recorded":
            data_recorded_status = "blocked_provenance"
            data_recorded_reason = candidate_lane.reason
        if candidate_lane.capture_scan_status != "not_scanned":
            data_recorded_reason = (
                f"{data_recorded_reason}; scanned-scope cumulative valid rows="
                f"{candidate_lane.valid_prediction_row_count}, distinct dates="
                f"{candidate_lane.valid_prediction_decision_date_count}, latest snapshot rows="
                f"{candidate_lane.latest_snapshot_row_count}, invalid captures="
                f"{candidate_lane.invalid_capture_count}, scan="
                f"{candidate_lane.capture_scan_status}"
            )

        horizon_scope = _horizon_scope_lane(candidate_lane, active_lane)
        historical = _mapping(status_payload.get("evaluation"))
        historical_count = _int_or_zero(historical.get("untouched_test_sample_count"))
        historical_status = "research_only_historical_replay" if historical else "research_only_not_natural"
        if historical:
            warnings.append(
                "evaluation／untouched test 是 historical replay；不與 natural matured evidence 混算"
            )
        if status_payload.get("natural_evidence_supplied") is True and not (
            candidate_lane.verified or active_lane.verified
        ):
            warnings.append("latest_status 宣稱 evidence supplied，但目前沒有通過 typed verifier 的 evidence")
        if not candidate_lane.verified and not active_lane.verified:
            warnings.append("尚無已驗證 natural matured sample；80% 機率可靠度未知")
        warnings.extend(_strings(status_payload.get("warnings")))
        diagnostics.extend(candidate_lane.diagnostics)
        diagnostics.extend(active_lane.diagnostics)
        source_trace = [
            f"learning.latest_status={self.latest_status_path}",
            f"learning.active_pointer={self.active_pointer_path or 'unknown'}",
            f"learning.requested_date={requested or 'unknown'}",
        ]
        source_trace.extend(candidate_lane.source_trace)
        source_trace.extend(active_lane.source_trace)
        overall_status = _projection_status(
            date_status=date_status,
            candidate_lane=candidate_lane,
            active_lane=active_lane,
            data_recorded_status=data_recorded_status,
        )
        return RecommendationLearningEvidenceProjection(
            schema_version=PROJECTION_SCHEMA_VERSION,
            status=overall_status,
            requested_date=requested,
            learning_decision_date=learning_date,
            checked_at=_text(
                status_payload.get("cli_result_updated_at")
                or status_payload.get("checked_at")
                or status_payload.get("completed_at")
            ),
            decision=_text(status_payload.get("decision")) or "unknown",
            decision_reason=_text(status_payload.get("decision_reason")) or "",
            candidate_id=candidate_lane.candidate_id,
            candidate_model_version=candidate_lane.model_version,
            candidate_training_as_of=candidate_lane.training_as_of,
            data_recorded_status=data_recorded_status,
            data_recorded_reason=data_recorded_reason,
            next_gap=_next_gap(
                candidate_lane=candidate_lane,
                active_lane=active_lane,
                data_recorded_status=data_recorded_status,
            ),
            adoption_reason=(
                _text(status_payload.get("decision_reason"))
                or _text(status_payload.get("next_step"))
                or candidate_lane.reason
                or active_lane.reason
                or "未知"
            ),
            candidate_lane=candidate_lane,
            active_lane=active_lane,
            horizons=horizon_scope.horizons,
            horizon_scope_lane_id=horizon_scope.lane_id,
            horizon_scope_label=horizon_scope.label,
            horizon_scope_model_version=horizon_scope.model_version,
            horizon_scope_cost_scenario_id=horizon_scope.cost_scenario_id,
            historical_evaluation_status=historical_status,
            historical_evaluation_sample_count=historical_count,
            warnings=tuple(dict.fromkeys(warnings)),
            diagnostics=tuple(dict.fromkeys(diagnostics)),
            source_trace=tuple(dict.fromkeys(source_trace)),
            cost_lane=self.cost_lane,
        )

    def _candidate_context(
        self,
        payload: Mapping[str, Any],
        *,
        requested_date: str | None,
    ) -> tuple[Mapping[str, Any], Mapping[str, Any] | None, Path | None, list[str]]:
        diagnostics: list[str] = []
        challenger = _mapping(payload.get("challenger"))
        candidate_id = _text(payload.get("candidate_id")) or _text(challenger.get("candidate_id"))
        candidate_root_text = _text(payload.get("candidate_root")) or _text(challenger.get("candidate_root"))
        if not candidate_id or not candidate_root_text:
            return challenger, None, None, ["recommendation_learning_candidate_identity_missing"]
        candidate_root = _safe_root(self.learning_root, candidate_root_text)
        if candidate_root is None:
            return challenger, None, None, ["recommendation_learning_candidate_root_outside_learning_root"]
        candidate_json = candidate_root / "candidate.json"
        candidate_metadata, error = _read_json_object(candidate_json)
        if error is not None or candidate_metadata is None:
            return challenger, None, candidate_root, [f"recommendation_learning_candidate_read_failure:{error or 'unknown'}"]
        if _text(candidate_metadata.get("candidate_id") or candidate_metadata.get("model_id")) != candidate_id:
            diagnostics.append("recommendation_learning_candidate_id_mismatch")
        training_as_of = _date_key(candidate_metadata.get("training_as_of"))
        if requested_date and training_as_of and training_as_of > requested_date:
            diagnostics.append("recommendation_learning_candidate_training_future_dated")
        return challenger, candidate_metadata, candidate_root, diagnostics

    def _candidate_lane(
        self,
        payload: Mapping[str, Any],
        *,
        candidate: Mapping[str, Any],
        candidate_metadata: Mapping[str, Any] | None,
        candidate_root: Path | None,
        requested_date: str | None,
        date_status: str,
        diagnostics: list[str],
    ) -> LearningLaneProjection:
        candidate_id = _text(payload.get("candidate_id")) or _text(candidate.get("candidate_id"))
        if candidate_metadata is None or candidate_root is None or not candidate_id:
            return LearningLaneProjection(
                lane_id="candidate_natural",
                label="候選 natural evidence",
                status="missing",
                reason="candidate_identity_or_artifact_missing",
                candidate_id=candidate_id or None,
                capture_status="not_recorded",
                diagnostics=("candidate metadata unavailable",),
                source_trace=(f"candidate_root={candidate_root or 'unknown'}",),
            )
        scenario, scenario_error = _scenario(candidate_metadata)
        base: dict[str, Any] = dict(
            lane_id="candidate_natural",
            label="候選 natural evidence",
            candidate_id=candidate_id,
            model_version=_text(candidate_metadata.get("model_id")) or candidate_id,
            dataset_version=_text(candidate_metadata.get("dataset_id")),
            training_as_of=_date_key(candidate_metadata.get("training_as_of")),
            cost_basis=scenario.cost_basis if scenario else None,
            cost_scenario_id=scenario.scenario_id if scenario else None,
            cost_scenario_version=scenario.scenario_version if scenario else None,
            cost_scenario_hash=scenario.scenario_hash if scenario else None,
            cost_estimate_status="research_only_estimated" if scenario and scenario.is_estimated else "fixed_legacy",
            capture_status="not_recorded",
            diagnostics=tuple(
                [scenario_error] if scenario_error else []
            ),
            source_trace=(f"candidate_root={candidate_root}", f"candidate_id={candidate_id}"),
        )
        if scenario is None:
            return LearningLaneProjection(
                status="blocked_provenance",
                reason="candidate_cost_scenario_invalid",
                **base,
            )
        if not _scenario_matches_lane(scenario, self.cost_lane):
            return LearningLaneProjection(
                status="blocked_provenance",
                reason=f"blocked_cost_scope:selected={self.cost_lane}:artifact={scenario.scenario_id}",
                **base,
            )
        natural = _mapping(payload.get("natural_evidence"))
        evidence_ref = _mapping(natural.get("evidence")) or natural
        capture = _mapping(_mapping(payload.get("live_capture")).get("candidate"))
        live_capture = _mapping(payload.get("live_capture"))
        candidate_capture = _mapping(live_capture.get("candidate"))
        horizon_days = _int_or_default(candidate_metadata.get("horizon_trading_days"))
        latest_capture_path = _text(candidate_capture.get("capture_path")) or _text(capture.get("capture_path"))
        capture_paths = (
            *_strings(natural.get("capture_paths")),
            latest_capture_path,
        )
        denominator = self._capture_denominator(
            capture_paths=capture_paths,
            latest_capture_path=latest_capture_path,
            candidate_id=candidate_id,
            expected_cost_scenario=scenario,
            requested_date=requested_date,
            horizon_days=horizon_days,
        )
        recorded_rows = denominator.latest_snapshot_row_count
        capture_status, capture_reason = _capture_surface(
            capture,
            candidate_id=candidate_id,
            learning_root=self.learning_root,
            requested_date=requested_date,
            date_status=date_status,
            expected_cost_scenario=scenario,
            conflict_symbols=(
                _strings(capture.get("cross_capture_feature_conflict_symbols"))
                + _strings(capture.get("cross_capture_source_conflict_symbols"))
            ),
            capture_verifier=self.capture_verifier,
        )
        if capture_status != "recorded" and capture_reason:
            base["diagnostics"] = tuple([*tuple(base.get("diagnostics", ())), capture_reason])
        base["capture_status"] = capture_status
        base["capture_count"] = denominator.valid_capture_count
        base["recorded_row_count"] = recorded_rows
        base.update(
            _denominator_lane_fields(
                denominator,
                lane_id="candidate_natural",
                horizon_days=horizon_days,
            )
        )
        base["diagnostics"] = tuple(
            [
                *tuple(base.get("diagnostics", ())),
                *denominator.diagnostics,
                _denominator_summary(denominator, horizon_days=horizon_days),
            ]
        )

        if date_status != "current":
            return LearningLaneProjection(
                status=date_status,
                reason=f"learning_status_{date_status}",
                **base,
            )
        if capture_status in {"stale", "future_blocked", "unknown"}:
            return LearningLaneProjection(
                status=capture_status,
                reason=capture_reason or f"candidate capture is {capture_status}",
                **base,
            )
        if capture_status == "blocked_provenance":
            return LearningLaneProjection(
                status="blocked_provenance",
                reason=capture_reason or "capture_provenance_invalid",
                **base,
        )
        if not evidence_ref.get("receipt_path"):
            pending_reason = _text(natural.get("reason")) or "natural_forward_evidence_receipt_missing"
            base["pending_prediction_row_count"] = denominator.valid_prediction_row_count
            base["pending_prediction_decision_date_count"] = denominator.valid_prediction_decision_date_count
            pending_status = "awaiting_typed_natural_verification"
            if denominator.capture_conflict_count:
                pending_status = "awaiting_typed_natural_verification_with_scope_conflicts"
            base["pending_prediction_status"] = pending_status
            base["diagnostics"] = tuple(
                [
                    *tuple(base.get("diagnostics", ())),
                    "pending counts mean valid captures await typed natural verification; maturity is not inferred",
                ]
            )
            horizon = _pending_horizon(
                candidate_metadata,
                capture_count=denominator.valid_capture_count,
                recorded_row_count=recorded_rows,
                matured_sample_count=0,
                reason=pending_reason,
                valid_prediction_row_count=denominator.valid_prediction_row_count,
                valid_prediction_decision_date_count=denominator.valid_prediction_decision_date_count,
                pending_prediction_row_count=denominator.valid_prediction_row_count,
                pending_prediction_decision_date_count=denominator.valid_prediction_decision_date_count,
                pending_prediction_status=pending_status,
                invalid_capture_count=denominator.invalid_capture_count,
                capture_conflict_count=denominator.capture_conflict_count,
            )
            return LearningLaneProjection(
                status="pending",
                reason=pending_reason,
                matured_sample_count=0,
                matured_decision_date_count=0,
                horizons=(horizon,),
                **base,
            )
        receipt_path = _safe_root(self.learning_root, _text(evidence_ref.get("receipt_path")))
        if receipt_path is None or not receipt_path.is_file():
            branch_base = dict(base)
            branch_base["diagnostics"] = tuple(
                [*tuple(base.get("diagnostics", ())), "receipt_path_missing_or_outside_learning_root"]
            )
            return LearningLaneProjection(
                status="blocked_provenance",
                reason="natural_evidence_receipt_path_invalid",
                **branch_base,
            )
        source_paths = _receipt_source_paths(receipt_path)
        if any(_safe_root(self.learning_root, path) is None for path in source_paths):
            branch_base = dict(base)
            branch_base["diagnostics"] = tuple(
                [*tuple(base.get("diagnostics", ())), "source_capture_path_outside_learning_root"]
            )
            return LearningLaneProjection(
                status="blocked_provenance",
                reason="natural_evidence_source_path_outside_learning_root",
                **branch_base,
            )
        try:
            verification = self.candidate_verifier(
                evidence_ref,
                decision_date=requested_date or "",
                candidate_id=candidate_id,
                candidate_root=candidate_root,
                candidate_metadata=candidate_metadata,
            )
        except (OSError, TypeError, ValueError, KeyError) as exc:
            branch_base = dict(base)
            branch_base["diagnostics"] = tuple(
                [*tuple(base.get("diagnostics", ())), type(exc).__name__]
            )
            return LearningLaneProjection(
                status="blocked_provenance",
                reason=f"natural_evidence_verification_failed:{str(exc)}",
                receipt_path=str(receipt_path),
                receipt_hash=_text(evidence_ref.get("receipt_hash")),
                **branch_base,
            )
        return self._lane_from_candidate_verification(
            verification,
            base=base,
            horizon_days=horizon_days,
            denominator=denominator,
            policy_binding_trusted=self.candidate_verifier is verify_natural_evidence_read_only,
        )

    def _capture_denominator(
        self,
        *,
        capture_paths: Sequence[str],
        latest_capture_path: str,
        candidate_id: str,
        expected_cost_scenario: RecommendationCostScenario,
        requested_date: str | None,
        horizon_days: int,
    ) -> _CaptureDenominator:
        """以既有 verifier 掃描同 scope immutable captures。

        ``latest_status`` 的 path list 只提供掃描範圍，累積 valid rows 只取
        verifier 成功結果。目錄補掃描有明確上限；其他 candidate 不列入本 lane
        的 invalid。duplicate id 或 symbol/date 衝突整組排除，避免順序影響分母。
        """

        explicit_paths: list[Path] = []
        diagnostics: list[str] = []
        seen: set[str] = set()
        excluded_scope_count = 0

        def add_path(value: str, *, explicit: bool) -> None:
            if not value:
                return
            path = _safe_root(self.learning_root, value)
            if path is None:
                diagnostics.append(
                    "capture_scan_path_outside_learning_root:" + Path(value).name
                )
                return
            resolved = str(path)
            if resolved in seen or not path.is_file():
                if explicit and resolved not in seen:
                    diagnostics.append("capture_scan_path_missing:" + path.name)
                return
            seen.add(resolved)
            explicit_paths.append(path)

        for value in capture_paths:
            add_path(value, explicit=True)

        capture_root = self.learning_root / "captures" if self.learning_root is not None else None
        scan_status = "listed_only" if explicit_paths else "not_scanned"
        if capture_root is not None and capture_root.is_dir() and self.capture_scan_limit > 0:
            discovered_count = 0
            truncated = False
            try:
                for path in capture_root.rglob("*.json"):
                    check_read_cancelled()
                    if path.is_symlink() or not path.is_file():
                        continue
                    discovered_count += 1
                    if discovered_count > self.capture_scan_limit:
                        truncated = True
                        break
                    try:
                        raw_payload, raw_error = _read_json_object(path)
                    except (OSError, TypeError, ValueError):
                        check_read_cancelled()
                        raw_payload, raw_error = None, "read_failure"
                    raw_candidate_id = _text(raw_payload.get("candidate_id")) if raw_payload else ""
                    if raw_candidate_id and raw_candidate_id != candidate_id:
                        excluded_scope_count += 1
                        continue
                    if raw_error is not None and str(path) not in seen:
                        diagnostics.append("capture_scan_unreadable:" + path.name)
                    add_path(str(path), explicit=False)
            except ReadOperationCancelled:
                raise
            except (OSError, RuntimeError) as exc:
                check_read_cancelled()
                truncated = True
                diagnostics.append(f"capture_scan_truncated:{type(exc).__name__}")
            scan_status = "truncated" if truncated else "complete"
            if truncated:
                diagnostics.append(f"capture_scan_truncated:limit={self.capture_scan_limit}")
        elif capture_root is not None and capture_root.is_dir() and self.capture_scan_limit == 0:
            scan_status = "truncated"
            diagnostics.append("capture_scan_truncated:scan_limit=0")
        elif explicit_paths:
            diagnostics.append("capture_scan_listed_only:capture_directory_missing")

        latest_path = _safe_root(self.learning_root, latest_capture_path)
        invalid_capture_count = 0
        seen_capture_ids: dict[str, tuple[Path, str, str, Any, str | None, int]] = {}
        conflicting_capture_ids: set[str] = set()
        conflicting_symbol_dates: set[tuple[str, str]] = set()
        seen_symbol_dates: dict[tuple[str, str], tuple[str, str]] = {}
        symbol_date_capture_ids: dict[tuple[str, str], set[str]] = {}
        latest_row_count = 0
        latest_capture_count = 0
        latest_candidate_id: str | None = None
        latest_scenario_id: str | None = None
        latest_scenario_hash: str | None = None
        latest_decision_date: str | None = None

        for path in explicit_paths:
            check_read_cancelled()
            try:
                verified = self.capture_verifier(path)
                check_read_cancelled()
                capture_date = _date_key(verified.capture_as_of_date)
                if verified.candidate_id != candidate_id:
                    raise ValueError("candidate capture identity mismatch")
                if capture_date is None:
                    raise ValueError("candidate capture decision date missing or invalid")
                if requested_date and capture_date > requested_date:
                    diagnostics.append("capture_future_excluded:" + path.name)
                    continue
                if verified.capture_origin not in {"scheduled_live", "live_forward"}:
                    raise ValueError("candidate capture origin is not live")
                if verified.source_contract_status != "ready":
                    raise ValueError("candidate capture source contract is not ready")
                if verified.cost_scenario_hash != expected_cost_scenario.scenario_hash:
                    raise ValueError("candidate capture cost scenario mismatch")
            except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
                check_read_cancelled()
                invalid_capture_count += 1
                diagnostics.append(f"capture_invalid:{path.name}:{type(exc).__name__}")
                continue
            raw_payload, _raw_error = _read_json_object(path)
            if latest_path is not None and path == latest_path:
                latest_capture_count = 1
                latest_row_count = max(0, int(verified.row_count))
                latest_candidate_id = verified.candidate_id
                latest_scenario_id = verified.cost_scenario_id
                latest_scenario_hash = verified.cost_scenario_hash
                latest_decision_date = capture_date
            prior_capture = seen_capture_ids.get(verified.capture_id)
            if prior_capture is not None:
                if prior_capture[1] != verified.capture_hash:
                    conflicting_capture_ids.add(verified.capture_id)
                    diagnostics.append("capture_duplicate_id_conflict:" + verified.capture_id)
                else:
                    diagnostics.append("capture_duplicate_id_deduped:" + verified.capture_id)
                continue
            raw_rows = raw_payload.get("rows", ()) if raw_payload else ()
            local_rows: list[tuple[tuple[str, str], str]] = []
            duplicate_row_count = 0
            local_conflict = False
            if isinstance(raw_rows, list):
                for raw_row in raw_rows:
                    check_read_cancelled()
                    if not isinstance(raw_row, Mapping):
                        continue
                    symbol = _text(raw_row.get("symbol"))
                    row_date = _date_key(raw_row.get("decision_date")) or capture_date
                    if not symbol or row_date is None:
                        continue
                    key = (symbol, row_date)
                    fingerprint = _hash_payload(raw_row)
                    local_previous = next(
                        (item[1] for item in local_rows if item[0] == key),
                        None,
                    )
                    if local_previous is not None:
                        if local_previous != fingerprint:
                            local_conflict = True
                            conflicting_symbol_dates.add(key)
                            diagnostics.append(
                                "capture_symbol_date_conflict:" + symbol + ":" + row_date
                            )
                        else:
                            duplicate_row_count += 1
                            diagnostics.append(
                                "capture_symbol_date_duplicate_same_capture:" + symbol + ":" + row_date
                            )
                        continue
                    previous = seen_symbol_dates.get(key)
                    if previous is not None:
                        if (
                            key in conflicting_symbol_dates
                            or previous[1] != fingerprint
                            or previous[0] in conflicting_capture_ids
                        ):
                            conflicting_capture_ids.update(symbol_date_capture_ids.get(key, {previous[0]}))
                            conflicting_capture_ids.add(verified.capture_id)
                            conflicting_symbol_dates.add(key)
                            local_conflict = True
                            diagnostics.append(
                                "capture_symbol_date_conflict:" + symbol + ":" + row_date
                            )
                        else:
                            duplicate_row_count += 1
                            diagnostics.append(
                                "capture_symbol_date_duplicate_same_content:" + symbol + ":" + row_date
                            )
                    local_rows.append((key, fingerprint))
            if local_conflict:
                conflicting_capture_ids.add(verified.capture_id)
            else:
                for key, fingerprint in local_rows:
                    check_read_cancelled()
                    if key not in seen_symbol_dates:
                        seen_symbol_dates[key] = (verified.capture_id, fingerprint)
                    symbol_date_capture_ids.setdefault(key, set()).add(verified.capture_id)
            seen_capture_ids[verified.capture_id] = (
                path,
                verified.capture_hash,
                capture_date,
                verified,
                str(raw_payload.get("candidate_id")) if raw_payload else None,
                duplicate_row_count,
            )

        valid_capture_count = 0
        valid_row_count = 0
        valid_dates: set[str] = set()
        capture_conflict_count = len(conflicting_capture_ids)
        for capture_id, (path, _capture_hash, capture_date, verified, _raw_candidate_id, duplicate_row_count) in seen_capture_ids.items():
            if capture_id in conflicting_capture_ids:
                continue
            valid_capture_count += 1
            valid_row_count += max(0, int(verified.row_count) - duplicate_row_count)
            valid_dates.add(capture_date)

        if latest_path is not None and latest_capture_count == 0:
            diagnostics.append("latest_snapshot_not_verified; row count remains unknown")
        if scan_status in {"complete", "truncated"} and invalid_capture_count:
            diagnostics.append(f"capture_scan_invalid_count:{invalid_capture_count}")
        if capture_conflict_count:
            diagnostics.append(f"capture_scan_conflict_count:{capture_conflict_count}")
        if excluded_scope_count:
            diagnostics.append(f"capture_scan_excluded_other_candidate:{excluded_scope_count}")
        return _CaptureDenominator(
            valid_capture_count=valid_capture_count,
            valid_prediction_row_count=valid_row_count,
            valid_prediction_decision_date_count=len(valid_dates),
            invalid_capture_count=invalid_capture_count,
            capture_conflict_count=capture_conflict_count,
            capture_scan_status=scan_status,
            diagnostics=tuple(dict.fromkeys(diagnostics)),
            valid_decision_dates=tuple(sorted(valid_dates)),
            latest_snapshot_row_count=latest_row_count,
            latest_snapshot_capture_count=latest_capture_count,
            latest_snapshot_candidate_id=latest_candidate_id,
            latest_snapshot_cost_scenario_id=latest_scenario_id,
            latest_snapshot_cost_scenario_hash=latest_scenario_hash,
            latest_snapshot_decision_date=latest_decision_date,
        )

    def _lane_from_candidate_verification(
        self,
        verification: RecommendationNaturalEvidenceVerification,
        *,
        base: Mapping[str, Any],
        horizon_days: int,
        denominator: _CaptureDenominator,
        policy_binding_trusted: bool,
    ) -> LearningLaneProjection:
        rows = tuple(
            _ObservedRow(
                probability_bp=item.candidate_probability_bp,
                label=item.upside_label,
                after_cost_probability_bp=item.candidate_after_cost_probability_bp,
                after_cost_label=item.after_cost_profit_label,
                decision_date=item.capture_as_of_date,
                label_end_date=item.label_end_date,
            )
            for item in verification.comparisons
        )
        after_cost_status = _after_cost_status(
            verification.scope.cost_basis,
            verification.after_cost_evaluation_status,
            verification.after_cost_matured_sample_count,
        )
        policy_binding = _policy_binding_from_receipt(
            Path(verification.receipt_path),
            trusted_verifier=policy_binding_trusted,
            expected_receipt_hash=verification.receipt_hash,
        )
        lane_base = dict(base)
        lane_base.update(_policy_binding_lane_fields(policy_binding))
        matured_dates = {row.decision_date for row in rows}
        valid_dates = set(denominator.valid_decision_dates)
        pending_dates = valid_dates - matured_dates
        pending_rows = max(0, denominator.valid_prediction_row_count - verification.matured_sample_count)
        pending_status = (
            "none"
            if pending_rows == 0 and not pending_dates
            else "awaiting_natural_maturity"
        )
        if verification.matured_sample_count > denominator.valid_prediction_row_count:
            lane_base["diagnostics"] = tuple(
                [
                    *tuple(lane_base.get("diagnostics", ())),
                    "matured rows exceed scanned valid capture rows; scope counts remain conservative",
                ]
            )
            pending_status = "scope_count_mismatch"
        lane_base["pending_prediction_row_count"] = pending_rows
        lane_base["pending_prediction_decision_date_count"] = len(pending_dates)
        lane_base["pending_prediction_status"] = pending_status
        if policy_binding.status != "verified":
            lane_base["diagnostics"] = tuple(
                [*tuple(lane_base.get("diagnostics", ())), policy_binding.reason]
            )
        return LearningLaneProjection(
            status="verified",
            reason="typed_natural_evidence_verified",
            capture_status="recorded",
            matured_sample_count=verification.matured_sample_count,
            matured_decision_date_count=verification.matured_unique_decision_date_count,
            period_start=min((row.decision_date for row in rows), default=None),
            period_end=max((row.decision_date for row in rows), default=None),
            brier_bp=verification.observed_candidate_brier_bp,
            calibration_gap_bp=verification.observed_calibration_gap_bp,
            brier_improvement_bp=verification.observed_brier_improvement_bp,
            after_cost_brier_bp=verification.observed_candidate_after_cost_brier_bp,
            after_cost_calibration_gap_bp=verification.observed_after_cost_calibration_gap_bp,
            after_cost_lane_status=after_cost_status,
            evidence_id=verification.evidence_id,
            receipt_path=verification.receipt_path,
            receipt_hash=verification.receipt_hash,
            horizons=(
                LearningHorizonProjection(
                    horizon_days=horizon_days,
                    capture_count=denominator.valid_capture_count,
                    recorded_row_count=denominator.latest_snapshot_row_count,
                    matured_sample_count=len(rows),
                    matured_decision_date_count=verification.matured_unique_decision_date_count,
                    status="matured",
                    reason="typed_verifier_passed",
                    valid_prediction_row_count=denominator.valid_prediction_row_count,
                    valid_prediction_decision_date_count=denominator.valid_prediction_decision_date_count,
                    pending_prediction_row_count=pending_rows,
                    pending_prediction_decision_date_count=len(pending_dates),
                    pending_prediction_status=pending_status,
                    invalid_capture_count=denominator.invalid_capture_count,
                    capture_conflict_count=denominator.capture_conflict_count,
                ),
            ),
            reliability_bins=_reliability_bins(
                lane_id="candidate_natural",
                rows=rows,
                research_only=verification.scope.cost_basis == "estimated_research_only",
            ),
            diagnostics=tuple(lane_base.get("diagnostics", ())),
            source_trace=tuple(
                [
                    *lane_base.get("source_trace", ()),
                    f"receipt={verification.receipt_path}",
                    f"evidence_id={verification.evidence_id}",
                    _denominator_summary(denominator, horizon_days=horizon_days),
                ]
            ),
            **{
                key: value
                for key, value in lane_base.items()
                if key not in {"status", "reason", "capture_status", "diagnostics", "source_trace"}
            },
        )

    def _active_lane(
        self,
        payload: Mapping[str, Any],
        *,
        requested_date: str | None,
        date_status: str,
        diagnostics: list[str],
    ) -> LearningLaneProjection:
        pointer = _mapping(payload.get("active_pointer"))
        pointer_status = _text(pointer.get("status")) or "unknown"
        active_evidence = _mapping(payload.get("active_model_natural_evidence"))
        base: dict[str, Any] = dict(
            lane_id="active_model_natural",
            label="active model natural evidence",
            candidate_id=_text(pointer.get("candidate_id")) or None,
            model_version=_text(pointer.get("candidate_id")) or None,
            cost_basis=None,
            cost_scenario_id=None,
            cost_scenario_version=None,
            cost_scenario_hash=None,
            capture_status="not_recorded",
            source_trace=(f"active_pointer.status={pointer_status}",),
        )
        if pointer_status != "active":
            return LearningLaneProjection(
                status="not_applicable",
                reason=_text(active_evidence.get("reason")) or "active_pointer_not_active",
                diagnostics=("active pointer is not active; rule-only path remains in force",),
                **base,
            )
        if date_status != "current":
            return LearningLaneProjection(
                status=date_status,
                reason=f"learning_status_{date_status}",
                **base,
            )
        if self.consumer is None:
            return LearningLaneProjection(
                status="blocked_provenance",
                reason="active_consumer_unavailable",
                diagnostics=("active calibration consumer unavailable",),
                **base,
            )
        try:
            consumer_status = self.consumer.reload(decision_date=requested_date)
            active_identity = self.consumer.active_identity(decision_date=requested_date or "")
        except (OSError, TypeError, ValueError, KeyError) as exc:
            return LearningLaneProjection(
                status="blocked_provenance",
                reason=f"active_consumer_read_failure:{str(exc)}",
                diagnostics=(type(exc).__name__,),
                **base,
            )
        if consumer_status != "active" or active_identity is None:
            return LearningLaneProjection(
                status="blocked_provenance",
                reason="active_pointer_not_verified_by_consumer",
                diagnostics=("active consumer returned rule_only",),
                **base,
            )
        evidence_ref = _mapping(active_evidence.get("evidence")) or active_evidence
        receipt_path_text = _text(evidence_ref.get("receipt_path"))
        if not receipt_path_text:
            return LearningLaneProjection(
                status="pending",
                reason=_text(active_evidence.get("reason")) or "active_model_natural_evidence_missing",
                horizons=(_pending_horizon({}, capture_count=0, recorded_row_count=0, matured_sample_count=0, reason="等待 active model natural maturity"),),
                **base,
            )
        receipt_path = _safe_root(self.learning_root, receipt_path_text)
        if receipt_path is None or not receipt_path.is_file():
            return LearningLaneProjection(
                status="blocked_provenance",
                reason="active_model_evidence_receipt_path_invalid",
                diagnostics=("active evidence path missing or outside learning root",),
                **base,
            )
        receipt_payload, error = _read_json_object(receipt_path)
        if error is not None or receipt_payload is None:
            return LearningLaneProjection(
                status="blocked_provenance",
                reason=f"active_model_evidence_read_failure:{error or 'unknown'}",
                receipt_path=str(receipt_path),
                **base,
            )
        active_candidate_id = _text(active_identity.get("candidate_id"))
        identity_hash = _hash_payload(active_identity)
        try:
            verifier_kwargs: dict[str, Any] = {
                "active_candidate_id": active_candidate_id,
                "active_identity_hash": identity_hash,
                "decision_date": requested_date or "",
            }
            source_database = self._configured_source_database_anchor()
            if source_database is not None:
                verifier_kwargs["expected_db_path"] = str(source_database)
            self.active_verifier(receipt_payload, **verifier_kwargs)
        except (OSError, TypeError, ValueError, KeyError) as exc:
            return LearningLaneProjection(
                status="blocked_provenance",
                reason=f"active_model_evidence_verification_failed:{str(exc)}",
                receipt_path=str(receipt_path),
                receipt_hash=_sha256_file(receipt_path),
                diagnostics=(type(exc).__name__,),
            **base,
        )
        scenario, scenario_error = _scenario(receipt_payload)
        if scenario is None:
            return LearningLaneProjection(
                status="blocked_provenance",
                reason="active_model_evidence_cost_scenario_invalid",
                receipt_path=str(receipt_path),
                diagnostics=(scenario_error or "cost scenario invalid",),
                **base,
            )
        if not _scenario_matches_lane(scenario, self.cost_lane):
            return LearningLaneProjection(
                status="blocked_provenance",
                reason=f"blocked_cost_scope:selected={self.cost_lane}:artifact={scenario.scenario_id}",
                receipt_path=str(receipt_path),
                receipt_hash=_sha256_file(receipt_path),
                **base,
            )
        comparisons = tuple(
            item
            for item in receipt_payload.get("comparisons", ())
            if isinstance(item, Mapping)
        )
        rows = tuple(
            _ObservedRow(
                probability_bp=int(item["active_probability_bp"]),
                label=int(item["upside_label"]),
                after_cost_probability_bp=_optional_int(item.get("active_after_cost_probability_bp")),
                after_cost_label=_optional_int(item.get("after_cost_profit_label")),
                decision_date=_date_key(item.get("capture_as_of_date")) or "unknown",
                label_end_date=_date_key(item.get("label_end_date")),
            )
            for item in comparisons
        )
        active_status = _after_cost_status(
            scenario.cost_basis,
            _text(receipt_payload.get("after_cost_evaluation_status")),
            _int_or_zero(receipt_payload.get("after_cost_matured_sample_count")),
        )
        active_policy_binding = _policy_binding_from_receipt(
            receipt_path,
            trusted_verifier=False,
        )
        active_policy_fields = _policy_binding_lane_fields(active_policy_binding)
        active_policy_diagnostics = (
            (active_policy_binding.reason,)
            if active_policy_binding.status != "verified"
            else ()
        )
        active_dates = {row.decision_date for row in rows}
        active_source_capture_ids = _strings(receipt_payload.get("source_capture_ids"))
        return LearningLaneProjection(
            lane_id="active_model_natural",
            label="active model natural evidence",
            status="verified",
            reason="typed_active_model_evidence_verified",
            candidate_id=active_candidate_id or None,
            model_version=_text(active_identity.get("model_id")) or active_candidate_id or None,
            dataset_version=None,
            training_as_of=_date_key(pointer.get("training_as_of")),
            cost_basis=scenario.cost_basis,
            cost_scenario_id=scenario.scenario_id,
            cost_scenario_version=scenario.scenario_version,
            cost_scenario_hash=scenario.scenario_hash,
            cost_estimate_status="research_only_estimated" if scenario.is_estimated else "fixed_legacy",
            after_cost_lane_status=active_status,
            capture_status="recorded",
            capture_count=len(active_source_capture_ids),
            recorded_row_count=len(rows),
            matured_sample_count=_int_or_zero(receipt_payload.get("matured_sample_count")),
            matured_decision_date_count=_int_or_zero(receipt_payload.get("matured_unique_decision_date_count")),
            valid_prediction_row_count=len(rows),
            valid_prediction_decision_date_count=len(active_dates),
            pending_prediction_row_count=0,
            pending_prediction_decision_date_count=0,
            pending_prediction_status="none",
            invalid_capture_count=0,
            capture_conflict_count=0,
            capture_scan_status="receipt_verified",
            latest_snapshot_row_count=len(rows),
            latest_snapshot_capture_count=1 if active_source_capture_ids else 0,
            latest_snapshot_lane_id="active_model_natural",
            latest_snapshot_candidate_id=active_candidate_id or None,
            latest_snapshot_cost_scenario_id=scenario.scenario_id,
            latest_snapshot_cost_scenario_hash=scenario.scenario_hash,
            latest_snapshot_horizon_days=DEFAULT_HORIZON_TRADING_DAYS,
            latest_snapshot_decision_date=max(active_dates, default=None),
            period_start=min((row.decision_date for row in rows), default=None),
            period_end=max((row.decision_date for row in rows), default=None),
            brier_bp=_optional_int(receipt_payload.get("observed_brier_bp")),
            calibration_gap_bp=_optional_int(receipt_payload.get("observed_calibration_gap_bp")),
            after_cost_brier_bp=_optional_int(receipt_payload.get("observed_after_cost_brier_bp")),
            after_cost_calibration_gap_bp=_optional_int(receipt_payload.get("observed_after_cost_calibration_gap_bp")),
            evidence_id=_text(receipt_payload.get("evidence_id")) or None,
            receipt_path=str(receipt_path),
            receipt_hash=_sha256_file(receipt_path),
            horizons=(
                LearningHorizonProjection(
                    horizon_days=DEFAULT_HORIZON_TRADING_DAYS,
                    capture_count=len(_strings(receipt_payload.get("source_capture_ids"))),
                    recorded_row_count=len(rows),
                    matured_sample_count=len(rows),
                    matured_decision_date_count=len({row.decision_date for row in rows}),
                    status="matured",
                    reason="typed_verifier_passed",
                    valid_prediction_row_count=len(rows),
                    valid_prediction_decision_date_count=len(active_dates),
                    pending_prediction_status="none",
                ),
            ),
            reliability_bins=_reliability_bins(
                lane_id="active_model_natural",
                rows=rows,
                research_only=scenario.is_estimated,
            ),
            source_trace=(
                *tuple(base.get("source_trace", ())),
                f"active_identity_hash={identity_hash}",
                f"receipt={receipt_path}",
                _denominator_summary(
                    _CaptureDenominator(
                        valid_capture_count=len(active_source_capture_ids),
                        valid_prediction_row_count=len(rows),
                        valid_prediction_decision_date_count=len(active_dates),
                        capture_scan_status="receipt_verified",
                        latest_snapshot_row_count=len(rows),
                        latest_snapshot_capture_count=1 if active_source_capture_ids else 0,
                    ),
                    horizon_days=DEFAULT_HORIZON_TRADING_DAYS,
                ),
            ),
            diagnostics=active_policy_diagnostics,
            **active_policy_fields,
        )

    def _empty_projection(
        self,
        *,
        requested_date: str | None,
        status: str,
        reason: str,
        diagnostics: Sequence[str],
    ) -> RecommendationLearningEvidenceProjection:
        empty = LearningLaneProjection(
            lane_id="candidate_natural",
            label="候選 natural evidence",
            status=status,
            reason=reason,
            diagnostics=tuple(diagnostics),
        )
        active = LearningLaneProjection(
            lane_id="active_model_natural",
            label="active model natural evidence",
            status="not_applicable" if status == "missing" else status,
            reason=reason,
            diagnostics=tuple(diagnostics),
        )
        return RecommendationLearningEvidenceProjection(
            schema_version=PROJECTION_SCHEMA_VERSION,
            status=status,
            requested_date=requested_date,
            learning_decision_date=None,
            checked_at=None,
            decision="unknown",
            decision_reason=reason,
            candidate_id=None,
            candidate_model_version=None,
            candidate_training_as_of=None,
            data_recorded_status="not_recorded",
            data_recorded_reason=reason,
            next_gap="先確認隔離 learning latest_status 與候選 artifact 可讀。",
            adoption_reason=reason,
            candidate_lane=empty,
            active_lane=active,
            horizons=empty.horizons,
            horizon_scope_lane_id=empty.lane_id,
            horizon_scope_label=empty.label,
            horizon_scope_model_version=empty.model_version,
            horizon_scope_cost_scenario_id=empty.cost_scenario_id,
            warnings=("learning projection unavailable; 不推定沒有資料或沒有風險",),
            diagnostics=tuple(diagnostics),
            source_trace=(f"learning.latest_status={self.latest_status_path or 'unknown'}",),
            cost_lane=self.cost_lane,
        )


def _read_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    check_read_cancelled()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        check_read_cancelled()
        return None, type(exc).__name__
    check_read_cancelled()
    if not isinstance(payload, dict):
        return None, "json_object_required"
    return payload, None


def _safe_root(root: Path | None, value: str | Path | None) -> Path | None:
    if root is None or value is None or not str(value).strip():
        return None
    path = Path(str(value)).expanduser().resolve()
    if path.is_symlink():
        return None
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return None
    return path


def _capture_surface(
    capture: Mapping[str, Any],
    *,
    candidate_id: str | None,
    learning_root: Path | None,
    requested_date: str | None,
    date_status: str,
    conflict_symbols: Sequence[str],
    expected_cost_scenario: RecommendationCostScenario | None = None,
    capture_verifier: Callable[..., RecommendationPredictionCaptureVerification] = verify_prediction_capture_read_only,
) -> tuple[str, str]:
    if date_status != "current":
        return date_status, f"learning status is {date_status}"
    if conflict_symbols:
        return "blocked_provenance", "cross-capture feature/source conflict: " + ",".join(sorted(set(conflict_symbols))[:8])
    if not capture:
        return "not_recorded", "candidate live capture not supplied"
    if _text(capture.get("status")) not in {"captured", "completed", "matured"}:
        return "not_recorded", _text(capture.get("reason")) or "candidate live capture not recorded"
    path = _safe_root(learning_root, _text(capture.get("capture_path")))
    if path is None or not path.is_file():
        return "blocked_provenance", "candidate capture path missing or outside learning root"
    try:
        verified = capture_verifier(path)
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return "blocked_provenance", f"candidate capture verification failed: {str(exc)}"
    if candidate_id and verified.candidate_id != candidate_id:
        return "blocked_provenance", "candidate capture identity mismatch"
    capture_date = _date_key(verified.capture_as_of_date)
    if capture_date is None:
        return "blocked_provenance", "candidate capture decision date missing or invalid"
    if requested_date and capture_date and capture_date > requested_date:
        return "future_blocked", "candidate capture is future-dated"
    if requested_date and capture_date and capture_date < requested_date:
        return "stale", "candidate capture is stale for requested decision date"
    if expected_cost_scenario is not None and verified.cost_scenario_hash != expected_cost_scenario.scenario_hash:
        return "blocked_provenance", "candidate capture cost scenario mismatch"
    if verified.capture_origin not in {"scheduled_live", "live_forward"}:
        return "blocked_provenance", "candidate capture origin is not live"
    return "recorded", "scheduled live prediction capture is recorded; natural verifier still pending"


def _receipt_source_paths(receipt_path: Path) -> tuple[str, ...]:
    payload, error = _read_json_object(receipt_path)
    if error is not None or payload is None:
        return ()
    paths = payload.get("source_capture_paths") or [payload.get("capture_path")]
    return tuple(str(item) for item in paths if item)


def _denominator_lane_fields(
    denominator: _CaptureDenominator,
    *,
    lane_id: str,
    horizon_days: int,
) -> dict[str, Any]:
    return {
        "valid_prediction_row_count": denominator.valid_prediction_row_count,
        "valid_prediction_decision_date_count": denominator.valid_prediction_decision_date_count,
        "pending_prediction_row_count": 0,
        "pending_prediction_decision_date_count": 0,
        "pending_prediction_status": "unknown",
        "invalid_capture_count": denominator.invalid_capture_count,
        "capture_conflict_count": denominator.capture_conflict_count,
        "capture_scan_status": denominator.capture_scan_status,
        "latest_snapshot_row_count": denominator.latest_snapshot_row_count,
        "latest_snapshot_capture_count": denominator.latest_snapshot_capture_count,
        "latest_snapshot_lane_id": lane_id if denominator.latest_snapshot_capture_count else None,
        "latest_snapshot_candidate_id": denominator.latest_snapshot_candidate_id,
        "latest_snapshot_cost_scenario_id": denominator.latest_snapshot_cost_scenario_id,
        "latest_snapshot_cost_scenario_hash": denominator.latest_snapshot_cost_scenario_hash,
        "latest_snapshot_horizon_days": horizon_days if denominator.latest_snapshot_capture_count else None,
        "latest_snapshot_decision_date": denominator.latest_snapshot_decision_date,
    }


def _denominator_summary(denominator: _CaptureDenominator, *, horizon_days: int) -> str:
    return (
        "capture denominator: "
        f"{denominator.valid_capture_count} valid captures / "
        f"{denominator.valid_prediction_row_count} valid prediction rows / "
        f"{denominator.valid_prediction_decision_date_count} distinct decision dates; "
        f"latest snapshot={denominator.latest_snapshot_capture_count} capture / "
        f"{denominator.latest_snapshot_row_count} rows / horizon={horizon_days}; "
        f"invalid captures={denominator.invalid_capture_count}; "
        f"conflict captures={denominator.capture_conflict_count}; "
        f"scan={denominator.capture_scan_status}"
    )


def _policy_binding_from_receipt(
    receipt_path: Path | None,
    *,
    trusted_verifier: bool,
    expected_receipt_hash: str | None = None,
) -> _PolicyBinding:
    """只在既有 authority verifier 證明後使用 immutable policy binding。

    receipt 的 hash 本身只是自報值；門檻永遠取固定 authority policy，candidate
    或 capture payload 不能提供替代門檻。active monitor verifier 沒有這個證明，
    因此保留 unknown。
    """

    if not trusted_verifier:
        return _PolicyBinding(reason="promotion_policy_binding_unknown:authority_proof_missing")
    if receipt_path is None or not receipt_path.is_file():
        return _PolicyBinding(reason="promotion_policy_binding_unknown:receipt_missing")
    if expected_receipt_hash is None:
        return _PolicyBinding(reason="promotion_policy_binding_unknown:receipt_hash_unbound")
    try:
        receipt_bytes = receipt_path.read_bytes()
        receipt_hash = "sha256:" + hashlib.sha256(receipt_bytes).hexdigest()
        if receipt_hash != expected_receipt_hash:
            return _PolicyBinding(reason="promotion_policy_binding_unknown:receipt_hash_mismatch")
    except OSError:
        return _PolicyBinding(reason="promotion_policy_binding_unknown:receipt_unreadable")
    try:
        payload = json.loads(receipt_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        payload = None
    if not isinstance(payload, Mapping):
        return _PolicyBinding(reason="promotion_policy_binding_unknown:receipt_unreadable")
    declared_hash = _text(payload.get("policy_hash"))
    if not declared_hash:
        return _PolicyBinding(reason="promotion_policy_binding_unknown:receipt_policy_hash_missing")
    policy = RecommendationPromotionPolicy()
    if declared_hash != policy.policy_hash:
        return _PolicyBinding(
            status="mismatch",
            reason="promotion_policy_binding_mismatch:receipt_hash_not_authority_policy",
        )
    return _PolicyBinding(
        status="verified",
        policy_hash=policy.policy_hash,
        minimum_natural_matured_samples=policy.minimum_natural_matured_samples,
        minimum_natural_matured_decision_dates=policy.minimum_natural_matured_decision_dates,
        reason="promotion_policy_binding_verified",
    )


def _policy_binding_lane_fields(binding: _PolicyBinding) -> dict[str, Any]:
    return {
        "policy_binding_status": binding.status,
        "policy_hash": binding.policy_hash,
        "policy_minimum_natural_matured_samples": binding.minimum_natural_matured_samples,
        "policy_minimum_natural_matured_decision_dates": binding.minimum_natural_matured_decision_dates,
    }


def _scenario(payload: Mapping[str, Any]) -> tuple[RecommendationCostScenario | None, str | None]:
    try:
        fixed = _optional_int(payload.get("fixed_round_trip_cost_bp"))
        return cost_scenario_from_metadata(payload, fixed_round_trip_cost_bp=fixed), None
    except (TypeError, ValueError, RecommendationCostScenarioError) as exc:
        return None, str(exc)


def _pending_horizon(
    candidate_metadata: Mapping[str, Any],
    *,
    capture_count: int,
    recorded_row_count: int,
    matured_sample_count: int,
    reason: str,
    valid_prediction_row_count: int = 0,
    valid_prediction_decision_date_count: int = 0,
    pending_prediction_row_count: int = 0,
    pending_prediction_decision_date_count: int = 0,
    pending_prediction_status: str = "unknown",
    invalid_capture_count: int = 0,
    capture_conflict_count: int = 0,
) -> LearningHorizonProjection:
    return LearningHorizonProjection(
        horizon_days=_int_or_default(candidate_metadata.get("horizon_trading_days")),
        capture_count=capture_count,
        recorded_row_count=recorded_row_count,
        matured_sample_count=matured_sample_count,
        matured_decision_date_count=0,
        status="pending" if capture_count or recorded_row_count else "not_recorded",
        reason=reason,
        valid_prediction_row_count=valid_prediction_row_count,
        valid_prediction_decision_date_count=valid_prediction_decision_date_count,
        pending_prediction_row_count=pending_prediction_row_count,
        pending_prediction_decision_date_count=pending_prediction_decision_date_count,
        pending_prediction_status=pending_prediction_status,
        invalid_capture_count=invalid_capture_count,
        capture_conflict_count=capture_conflict_count,
    )


def _reliability_bins(
    *,
    lane_id: str,
    rows: Sequence[_ObservedRow],
    research_only: bool,
) -> tuple[LearningReliabilityBin, ...]:
    result: list[LearningReliabilityBin] = []
    for target, probability_getter, label_getter in (
        ("upside_probability", lambda row: row.probability_bp, lambda row: row.label),
        (
            "after_cost_profit_probability",
            lambda row: row.after_cost_probability_bp,
            lambda row: row.after_cost_label,
        ),
    ):
        target_rows = [
            row
            for row in rows
            if probability_getter(row) is not None and label_getter(row) is not None
        ]
        for lower, upper in PROBABILITY_BINS_BP:
            bucket = [
                row
                for row in target_rows
                if lower <= int(probability_getter(row)) < upper  # type: ignore[arg-type]
            ]
            if not bucket:
                continue
            probabilities = [int(probability_getter(row)) for row in bucket]  # type: ignore[arg-type]
            labels = [int(label_getter(row)) for row in bucket]  # type: ignore[arg-type]
            result.append(
                LearningReliabilityBin(
                    target=target,
                    lower_probability_bp=lower,
                    upper_probability_bp_exclusive=upper,
                    predicted_probability_bp=sum(probabilities) // len(probabilities),
                    matured_actual_up_ratio_bp=sum(labels) * 10_000 // len(labels),
                    sample_count=len(bucket),
                    decision_date_count=len({row.decision_date for row in bucket}),
                    period_start=min((row.decision_date for row in bucket), default=None),
                    period_end=max((row.decision_date for row in bucket), default=None),
                    lane_id=lane_id,
                    status="research_only_estimated_cost" if research_only and target.startswith("after_cost") else "verified",
                    research_only=research_only and target.startswith("after_cost"),
                )
            )
    return tuple(result)


def _after_cost_status(cost_basis: str, receipt_status: str, sample_count: int) -> str:
    if sample_count <= 0:
        return receipt_status or "not_available"
    if cost_basis == "estimated_research_only":
        return "research_only_estimated_cost"
    return receipt_status or "verified_observed_cost"


def _scenario_matches_lane(scenario: RecommendationCostScenario, cost_lane: str) -> bool:
    if cost_lane == "banktaiwan_estimated_research":
        return scenario.is_estimated
    if cost_lane == "legacy_fixed_bp":
        return not scenario.is_estimated
    return False


def _horizon_scope_lane(
    candidate_lane: LearningLaneProjection,
    active_lane: LearningLaneProjection,
) -> LearningLaneProjection:
    """Choose one lane for the top-level horizon summary.

    Candidate and active evidence have different model/cost identities.  Their
    rows must stay in their lane objects; selecting one lane here prevents the
    top-level summary from manufacturing a mixed ``20 samples / 10 dates``
    horizon out of two unrelated receipts.
    """

    if active_lane.verified:
        return active_lane
    if candidate_lane.verified:
        return candidate_lane
    if candidate_lane.horizons:
        return candidate_lane
    if active_lane.horizons:
        return active_lane
    return candidate_lane


def _projection_status(
    *,
    date_status: str,
    candidate_lane: LearningLaneProjection,
    active_lane: LearningLaneProjection,
    data_recorded_status: str,
) -> str:
    if date_status != "current":
        return date_status
    if data_recorded_status in {"stale", "future_blocked"}:
        return data_recorded_status
    if candidate_lane.status == "blocked_provenance" or active_lane.status == "blocked_provenance":
        return "blocked_provenance"
    if candidate_lane.verified or active_lane.verified:
        return "verified"
    if data_recorded_status == "recorded" or candidate_lane.status == "pending":
        return "pending"
    return "unknown"


def _next_gap(
    *,
    candidate_lane: LearningLaneProjection,
    active_lane: LearningLaneProjection,
    data_recorded_status: str,
) -> str:
    lane = active_lane if active_lane.verified else candidate_lane
    if lane.verified:
        if (
            lane.policy_binding_status != "verified"
            or lane.policy_minimum_natural_matured_samples is None
            or lane.policy_minimum_natural_matured_decision_dates is None
        ):
            return (
                f"{lane.policy_binding_status} promotion policy binding；"
                "不計算 adoption samples／dates 缺口，需同 scope 的 verified natural receipt 綁定 authority policy；"
                f"{_lane_scan_note(lane)}。"
            )
        sample_gap = max(
            0,
            lane.policy_minimum_natural_matured_samples - lane.matured_sample_count,
        )
        date_gap = max(
            0,
            lane.policy_minimum_natural_matured_decision_dates - lane.matured_decision_date_count,
        )
        if sample_gap or date_gap:
            return (
                "已驗證同 scope natural evidence；"
                f"距已綁定 promotion policy 尚差 {sample_gap} 筆、{date_gap} 個決策日；"
                f"累積 valid rows={lane.valid_prediction_row_count}／"
                f"dates={lane.valid_prediction_decision_date_count}，"
                f"latest snapshot rows={lane.latest_snapshot_row_count}；"
                f"{_lane_scan_note(lane)}"
            )
        return (
            "已具備已綁定 policy 的自然成熟樣本；仍只作研究／自動 gate 輸入，"
            "formal order 旗標不由 UI 改動。"
        )
    if lane.status == "blocked_provenance":
        return f"先修復 provenance：{lane.reason}；修復前不顯示 reliability。"
    if data_recorded_status == "recorded":
        horizon = lane.horizons[0].horizon_days if lane.horizons else DEFAULT_HORIZON_TRADING_DAYS
        return (
            f"等待 {horizon} 交易日自然成熟與 typed receipt；"
            f"目前掃描 scope 的累積 valid rows={lane.valid_prediction_row_count}／"
            f"distinct dates={lane.valid_prediction_decision_date_count}，"
            f"pending={lane.pending_prediction_row_count} rows／"
            f"{lane.pending_prediction_decision_date_count} dates（{lane.pending_prediction_status}），"
            f"latest snapshot={lane.latest_snapshot_row_count} rows；{_lane_scan_note(lane)}；"
            "目前不能把預測機率當成準確率。"
        )
    return "先取得同一 candidate、同一決策日的 scheduled live prediction capture。"


def _lane_scan_note(lane: LearningLaneProjection) -> str:
    note = (
        f"capture scan={lane.capture_scan_status}；"
        f"invalid captures={lane.invalid_capture_count}；"
        f"conflict captures={lane.capture_conflict_count}"
    )
    if lane.capture_scan_status not in {"complete", "receipt_verified"}:
        return note + "；目前只覆蓋已掃描 scope，累積數字可能不完整"
    return note


def _hash_payload(payload: Any) -> str:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            check_read_cancelled()
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple, set)):
        return ()
    return tuple(str(item) for item in value if str(item).strip())


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _int_or_zero(value: Any) -> int:
    parsed = _optional_int(value)
    return max(0, parsed) if parsed is not None else 0


def _int_or_default(value: Any) -> int:
    parsed = _optional_int(value)
    return parsed if parsed is not None and parsed > 0 else DEFAULT_HORIZON_TRADING_DAYS


def _date_key(value: Any) -> str | None:
    if value is None or not str(value).strip():
        return None
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except (TypeError, ValueError):
        return None


def _date_scope_status(learning_date: str | None, requested_date: str | None) -> str:
    if not learning_date or not requested_date:
        return "unknown"
    if learning_date > requested_date:
        return "future_blocked"
    if learning_date < requested_date:
        return "stale"
    return "current"


def _resolve_default_requested_date(config: Any | None) -> str | None:
    """Resolve one trusted current Taiwan session without using receipt date.

    The Workbench normally supplies the selected snapshot's decision date.  A
    standalone Research Console still needs a safe default, so it asks the
    existing official-calendar resolver for the latest resolved session.  The
    lookup is local/query-only; an unavailable calendar returns ``None`` and
    therefore keeps the projection unknown instead of silently treating its
    own receipt date as current.
    """

    from app_module.paper_portfolio_time import taiwan_market_today
    from data_module.official_trading_calendar import OfficialTradingCalendar

    calendar = OfficialTradingCalendar(db_path=getattr(config, "db_file", None))
    try:
        sessions = calendar.get_recent_official_trading_days(
            taiwan_market_today(),
            1,
            include_reference=True,
            allow_online_probe=False,
        )
    except ReadOperationCancelled:
        raise
    except (OSError, TypeError, ValueError, RuntimeError):
        check_read_cancelled()
        return None
    if not sessions:
        return None
    return _date_key(sessions[-1].get("date_str"))


def _normalize_cost_lane(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {
        "banktaiwan",
        "banktaiwan_estimated",
        "banktaiwan_estimated_research",
        "estimated_research_only",
    }:
        return "banktaiwan_estimated_research"
    if normalized in {"legacy", "legacy_fixed_bp", "legacy-fixed-round-trip-bp"}:
        return "legacy_fixed_bp"
    raise ValueError(f"unsupported learning cost lane: {value!r}")


def _default_lane_output_root(data_root: str | Path | None, cost_lane: str) -> Path:
    formal_root = Path(data_root or "F:/Min/Python/Project/FA_Data").resolve()
    if cost_lane == "banktaiwan_estimated_research":
        configured = os.environ.get("BANKTAIWAN_RECOMMENDATION_LEARNING_OUTPUT_ROOT")
        return Path(configured).resolve() if configured else formal_root.parent / "FA_Data_Shadow_BankTaiwan"
    configured = os.environ.get("RECOMMENDATION_LEARNING_OUTPUT_ROOT")
    if configured:
        return Path(configured).resolve()
    return formal_root.parent / "FA_Data_Shadow"


def _build_consumer_for_paths(config: Any, paths: RecommendationLearningPaths) -> RecommendationCalibrationConsumer | None:
    data_root = getattr(config, "data_root", None)
    if data_root is None:
        return None
    from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY

    return RecommendationCalibrationConsumer(
        pointer_path=paths.active_pointer_path,
        feature_schema=CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_schema,
        feature_registry_hash=CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
        data_root=data_root,
    )
