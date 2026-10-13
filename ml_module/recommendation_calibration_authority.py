"""推薦 calibration adapter 的證據綁定 gate、pointer 與 decision receipt。

這不是 allocation evaluator 的平行替身。它沿用既有
``baldr-ml-promotion-authority-daily`` 的 authority family/custody 命名，但
只負責 recommendation calibration adapter；allocation bundle、DPAPI signing
與 broker/order authorization 仍由 ``scripts/run_ml_promotion_authority.py``
負責，本 adapter 永遠輸出 ``formal_order_allowed=False``。

採用 gate 不接受裸的 matured count 或 caller bool。自然前瞻 evidence 必須是
可驗證的 receipt，且要綁定 frozen candidate 的 candidate/manifest/artifact
hash、同樣本 fingerprint、同成本 contract、candidate/champion prediction
hash 與觀測到的 matured comparison metrics。發布順序是 immutable receipt
先行、pointer 後行；若程序在兩者之間中斷，下次執行會以 receipt 恢復 pointer。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
import hashlib
import json
from pathlib import Path
from runtime.file_io_path import (
    canonical_path_from_os_result as _canonical_io_result,
    canonical_scandir_child as _canonical_io_child,
    io_path as _io_path,
    iterdir_canonical as _iterdir_io,
    resolve_canonical_path as _resolve_io_path,
    to_internal_io_path as _to_internal_io_path,
)
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from ml_module.model_artifact_manifest import ModelArtifactManifest
from ml_module.promotion_authority_family import (
    AUTHORITY_FAMILY,
    RECOMMENDATION_SCOPE,
)
from ml_module.recommendation_calibration_training import (
    candidate_freeze_hash,
    feature_schema_hash,
    recommendation_cost_contract_hash,
)
from ml_module.recommendation_cost_scenario import (
    RecommendationCostScenario,
    RecommendationCostScenarioError,
    cost_scenario_from_metadata,
    verify_estimated_cost_observation,
)
from ml_module.recommendation_probability_transform import (
    NULL_BENCHMARK_BASELINE_ID,
    PROBABILITY_LINEAGE_SCHEMA_VERSION,
    PROBABILITY_TRANSFORM_ID,
    RecommendationProbabilityTransform,
)


AUTHORITY_SCOPE = RECOMMENDATION_SCOPE
NATURAL_EVIDENCE_STATUSES = frozenset({"ready", "matured"})
UNKNOWN_STATUSES = frozenset({"", "unknown", "not_checked", "missing", "unavailable", "failed"})


@dataclass(frozen=True)
class RecommendationPromotionPolicy:
    """固定、可追溯且不可由 candidate/evidence 自行變更的 thresholds。"""

    minimum_natural_matured_samples: int = 20
    minimum_natural_matured_decision_dates: int = 20
    minimum_brier_improvement_bp: int = 50
    maximum_calibration_gap_bp: int = 1_000
    maximum_probability_change_bp: int = 1_000
    cooldown_calendar_days: int = 20

    def __post_init__(self) -> None:
        if self.minimum_natural_matured_samples <= 0:
            raise ValueError("minimum_natural_matured_samples must be positive")
        if self.minimum_natural_matured_decision_dates <= 0:
            raise ValueError("minimum_natural_matured_decision_dates must be positive")
        if self.minimum_brier_improvement_bp < 0 or self.maximum_calibration_gap_bp < 0:
            raise ValueError("promotion thresholds must be non-negative")
        if not 0 <= self.maximum_probability_change_bp <= 10_000:
            raise ValueError("maximum_probability_change_bp must be within 0..10000")
        if self.cooldown_calendar_days < 0:
            raise ValueError("cooldown_calendar_days must be non-negative")

    def to_dict(self) -> dict[str, int]:
        return {
            "minimum_natural_matured_samples": self.minimum_natural_matured_samples,
            "minimum_natural_matured_decision_dates": self.minimum_natural_matured_decision_dates,
            "minimum_brier_improvement_bp": self.minimum_brier_improvement_bp,
            "maximum_calibration_gap_bp": self.maximum_calibration_gap_bp,
            "maximum_probability_change_bp": self.maximum_probability_change_bp,
            "cooldown_calendar_days": self.cooldown_calendar_days,
        }

    @property
    def policy_hash(self) -> str:
        return _hash_payload(self.to_dict())


@dataclass(frozen=True)
class RecommendationPromotionDecision:
    decision_id: str
    decision_date: str
    decision: str
    reason: str
    candidate_id: str | None
    previous_candidate_id: str | None
    pointer_version: int
    pointer_status: str
    receipt_path: str
    pointer_path: str
    natural_evidence_receipt_hash: str | None
    natural_matured_sample_count: int
    old_brier_bp: int | None
    new_brier_bp: int | None
    brier_improvement_bp: int | None
    calibration_gap_bp: int | None
    maximum_probability_change_bp: int
    natural_matured_decision_date_count: int = 0
    candidate_freeze_hash: str | None = None
    authority_family: str = AUTHORITY_FAMILY
    authority_scope: str = AUTHORITY_SCOPE
    formal_order_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "recommendation-calibration-decision-receipt.v2",
            "decision_id": self.decision_id,
            "decision_date": self.decision_date,
            "decision": self.decision,
            "reason": self.reason,
            "candidate_id": self.candidate_id,
            "previous_candidate_id": self.previous_candidate_id,
            "pointer_version": self.pointer_version,
            "pointer_status": self.pointer_status,
            "receipt_path": self.receipt_path,
            "pointer_path": self.pointer_path,
            "natural_evidence_receipt_hash": self.natural_evidence_receipt_hash,
            "natural_matured_sample_count": self.natural_matured_sample_count,
            "natural_matured_decision_date_count": self.natural_matured_decision_date_count,
            "old_brier_bp": self.old_brier_bp,
            "new_brier_bp": self.new_brier_bp,
            "brier_improvement_bp": self.brier_improvement_bp,
            "calibration_gap_bp": self.calibration_gap_bp,
            "maximum_probability_change_bp": self.maximum_probability_change_bp,
            "candidate_freeze_hash": self.candidate_freeze_hash,
            "authority_family": self.authority_family,
            "authority_scope": self.authority_scope,
            "formal_order_allowed": False,
        }


@dataclass(frozen=True)
class RecommendationNaturalEvidenceComparison:
    """單筆已通過 authority natural-evidence gate 的比較列。

    這個 DTO 只保存 read-only projection 需要的欄位；它不暴露 ranking
    score 作為機率，也不接受 caller 傳入的 label／return。
    """

    capture_row_id: str
    symbol: str
    capture_as_of_date: str
    label_end_date: str
    label_available_date: str
    candidate_probability_bp: int
    champion_probability_bp: int
    upside_label: int
    stock_return_bp: int
    candidate_after_cost_probability_bp: int | None = None
    champion_after_cost_probability_bp: int | None = None
    after_cost_profit_label: int | None = None
    observed_liquidity_cost_bp: int | None = None
    observed_liquidity_cost_source: str | None = None
    cost_scenario_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "capture_row_id": self.capture_row_id,
            "symbol": self.symbol,
            "capture_as_of_date": self.capture_as_of_date,
            "label_end_date": self.label_end_date,
            "label_available_date": self.label_available_date,
            "candidate_probability_bp": self.candidate_probability_bp,
            "champion_probability_bp": self.champion_probability_bp,
            "upside_label": self.upside_label,
            "stock_return_bp": self.stock_return_bp,
            "candidate_after_cost_probability_bp": self.candidate_after_cost_probability_bp,
            "champion_after_cost_probability_bp": self.champion_after_cost_probability_bp,
            "after_cost_profit_label": self.after_cost_profit_label,
            "observed_liquidity_cost_bp": self.observed_liquidity_cost_bp,
            "observed_liquidity_cost_source": self.observed_liquidity_cost_source,
            "cost_scenario_hash": self.cost_scenario_hash,
        }


@dataclass(frozen=True)
class RecommendationNaturalEvidenceScope:
    """Evidence receipt 的日期、來源、capture 與成本 scope。"""

    source_id: str
    source_kind: str
    capture_origin: str
    as_of_date: str
    capture_as_of_date: str
    captured_at: str
    candidate_frozen_at: str
    candidate_id: str
    capture_id: str
    capture_hash: str
    candidate_freeze_hash: str
    same_date_same_cost: bool
    source_capture_ids: tuple[str, ...]
    source_capture_hashes: tuple[str, ...]
    source_capture_paths: tuple[str, ...]
    cost_basis: str
    cost_scenario_id: str
    cost_scenario_version: str
    cost_scenario_hash: str
    fixed_round_trip_cost_bp: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_kind": self.source_kind,
            "capture_origin": self.capture_origin,
            "as_of_date": self.as_of_date,
            "capture_as_of_date": self.capture_as_of_date,
            "captured_at": self.captured_at,
            "candidate_frozen_at": self.candidate_frozen_at,
            "candidate_id": self.candidate_id,
            "capture_id": self.capture_id,
            "capture_hash": self.capture_hash,
            "candidate_freeze_hash": self.candidate_freeze_hash,
            "same_date_same_cost": self.same_date_same_cost,
            "source_capture_ids": list(self.source_capture_ids),
            "source_capture_hashes": list(self.source_capture_hashes),
            "source_capture_paths": list(self.source_capture_paths),
            "cost_basis": self.cost_basis,
            "cost_scenario_id": self.cost_scenario_id,
            "cost_scenario_version": self.cost_scenario_version,
            "cost_scenario_hash": self.cost_scenario_hash,
            "fixed_round_trip_cost_bp": self.fixed_round_trip_cost_bp,
        }


@dataclass(frozen=True)
class RecommendationNaturalEvidenceVerification:
    """Typed, successful result of the existing natural-evidence verifier."""

    evidence_id: str
    receipt_path: str
    receipt_hash: str
    matured_sample_count: int
    matured_unique_decision_date_count: int
    observed_champion_brier_bp: int
    observed_candidate_brier_bp: int
    observed_brier_improvement_bp: int
    observed_calibration_gap_bp: int
    after_cost_evaluation_status: str
    after_cost_matured_sample_count: int
    observed_champion_after_cost_brier_bp: int | None
    observed_candidate_after_cost_brier_bp: int | None
    observed_after_cost_brier_improvement_bp: int | None
    observed_after_cost_calibration_gap_bp: int | None
    scope: RecommendationNaturalEvidenceScope
    comparisons: tuple[RecommendationNaturalEvidenceComparison, ...]
    status: str = "verified"

    def __post_init__(self) -> None:
        if self.status != "verified":
            raise ValueError("successful natural evidence verification must be verified")
        if self.matured_sample_count != len(self.comparisons):
            raise ValueError("natural evidence verification count mismatch")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "recommendation-natural-evidence-verification.v1",
            "status": self.status,
            "evidence_id": self.evidence_id,
            "receipt_path": self.receipt_path,
            "receipt_hash": self.receipt_hash,
            "matured_sample_count": self.matured_sample_count,
            "matured_unique_decision_date_count": self.matured_unique_decision_date_count,
            "observed_champion_brier_bp": self.observed_champion_brier_bp,
            "observed_candidate_brier_bp": self.observed_candidate_brier_bp,
            "observed_brier_improvement_bp": self.observed_brier_improvement_bp,
            "observed_calibration_gap_bp": self.observed_calibration_gap_bp,
            "after_cost_evaluation_status": self.after_cost_evaluation_status,
            "after_cost_matured_sample_count": self.after_cost_matured_sample_count,
            "observed_champion_after_cost_brier_bp": self.observed_champion_after_cost_brier_bp,
            "observed_candidate_after_cost_brier_bp": self.observed_candidate_after_cost_brier_bp,
            "observed_after_cost_brier_improvement_bp": self.observed_after_cost_brier_improvement_bp,
            "observed_after_cost_calibration_gap_bp": self.observed_after_cost_calibration_gap_bp,
            "scope": self.scope.to_dict(),
            "comparisons": [item.to_dict() for item in self.comparisons],
        }


def verify_natural_evidence_read_only(
    evidence: Any,
    *,
    decision_date: str,
    candidate_id: str,
    candidate_root: str | Path,
    candidate_metadata: Mapping[str, Any],
    policy_hash: str | None = None,
    maximum_probability_change_bp: int | None = None,
) -> RecommendationNaturalEvidenceVerification:
    """Expose the existing authority verifier as a side-effect-free public API.

    This is deliberately a thin boundary around ``_verify_natural_evidence``.
    It performs no promotion decision and never writes a receipt or pointer;
    callers receive a typed scope plus the rows that the existing verifier
    already accepted.  Invalid hashes, dates, costs, identity, scope, or
    historical-sample reuse still raise ``ValueError`` from the same gate.
    """

    policy = RecommendationPromotionPolicy()
    resolved_policy_hash = policy_hash or policy.policy_hash
    resolved_probability_cap = (
        policy.maximum_probability_change_bp
        if maximum_probability_change_bp is None
        else int(maximum_probability_change_bp)
    )
    identity_error = _verify_candidate_identity(
        candidate_id=candidate_id,
        candidate_root=candidate_root,
        candidate_metadata=candidate_metadata,
    )
    if identity_error is not None:
        raise ValueError(identity_error)
    result = _verify_natural_evidence(
        evidence,
        decision_date=decision_date,
        candidate_id=candidate_id,
        candidate_metadata=candidate_metadata,
        policy_hash=resolved_policy_hash,
        maximum_probability_change_bp=resolved_probability_cap,
    )
    error = result.get("error")
    if error:
        raise ValueError(str(error))
    receipt_path_text, _receipt_hash_expected = _natural_evidence_reference(evidence)
    if not receipt_path_text:
        raise ValueError("natural_forward_evidence_receipt_missing")
    receipt_path = _resolve_io_path(Path(receipt_path_text))
    try:
        receipt_bytes = _io_path(receipt_path).read_bytes()
    except OSError as exc:
        raise ValueError("natural_evidence_receipt_invalid") from exc
    receipt_hash_from_same_read = "sha256:" + hashlib.sha256(receipt_bytes).hexdigest()
    if receipt_hash_from_same_read != str(result.get("receipt_hash") or ""):
        raise ValueError("natural_evidence_receipt_changed_after_verification")
    try:
        receipt_payload = json.loads(receipt_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
        raise ValueError("natural_evidence_receipt_invalid") from exc
    if not isinstance(receipt_payload, Mapping):
        raise ValueError("natural_evidence_receipt_invalid")
    scenario = _scenario_from_metadata(receipt_payload)
    raw_source_ids = receipt_payload.get("source_capture_ids") or [receipt_payload.get("capture_id")]
    raw_source_hashes = receipt_payload.get("source_capture_hashes") or [receipt_payload.get("capture_hash")]
    raw_source_paths = receipt_payload.get("source_capture_paths") or [receipt_payload.get("capture_path")]
    comparisons = tuple(
        RecommendationNaturalEvidenceComparison(
            capture_row_id=str(row["capture_row_id"]),
            symbol=str(row["symbol"]),
            capture_as_of_date=_date_text(str(row["capture_as_of_date"])),
            label_end_date=_date_text(str(row["label_end_date"])),
            label_available_date=_date_text(str(row["label_available_date"])),
            candidate_probability_bp=int(row["candidate_probability_bp"]),
            champion_probability_bp=int(row["champion_probability_bp"]),
            upside_label=int(row["upside_label"]),
            stock_return_bp=int(row["stock_return_bp"]),
            candidate_after_cost_probability_bp=_optional_int(row.get("candidate_after_cost_probability_bp")),
            champion_after_cost_probability_bp=_optional_int(row.get("champion_after_cost_probability_bp")),
            after_cost_profit_label=_optional_int(row.get("after_cost_profit_label")),
            observed_liquidity_cost_bp=_optional_int(row.get("observed_liquidity_cost_bp")),
            observed_liquidity_cost_source=(
                str(row.get("observed_liquidity_cost_source"))
                if row.get("observed_liquidity_cost_source") is not None
                else None
            ),
            cost_scenario_hash=(
                str(row.get("cost_scenario_hash"))
                if row.get("cost_scenario_hash") is not None
                else scenario.scenario_hash
            ),
        )
        for row in receipt_payload.get("comparisons", ())
        if isinstance(row, Mapping)
    )
    scope = RecommendationNaturalEvidenceScope(
        source_id=str(receipt_payload.get("source_id") or ""),
        source_kind=str(receipt_payload.get("source_kind") or ""),
        capture_origin=str(receipt_payload.get("capture_origin") or ""),
        as_of_date=_date_text(str(receipt_payload["as_of_date"])),
        capture_as_of_date=_date_text(str(receipt_payload["capture_as_of_date"])),
        captured_at=str(receipt_payload.get("captured_at") or ""),
        candidate_frozen_at=str(receipt_payload.get("candidate_frozen_at") or ""),
        candidate_id=str(receipt_payload.get("candidate_id") or ""),
        capture_id=str(receipt_payload.get("capture_id") or ""),
        capture_hash=str(receipt_payload.get("capture_hash") or ""),
        candidate_freeze_hash=str(receipt_payload.get("candidate_freeze_hash") or ""),
        same_date_same_cost=bool(receipt_payload.get("same_date_same_cost")),
        source_capture_ids=tuple(str(value) for value in raw_source_ids if value),
        source_capture_hashes=tuple(str(value) for value in raw_source_hashes if value),
        source_capture_paths=tuple(str(value) for value in raw_source_paths if value),
        cost_basis=scenario.cost_basis,
        cost_scenario_id=scenario.scenario_id,
        cost_scenario_version=scenario.scenario_version,
        cost_scenario_hash=scenario.scenario_hash,
        fixed_round_trip_cost_bp=scenario.fixed_round_trip_cost_bp,
    )
    return RecommendationNaturalEvidenceVerification(
        evidence_id=str(receipt_payload.get("evidence_id") or ""),
        receipt_path=str(receipt_path),
        receipt_hash=str(result["receipt_hash"]),
        matured_sample_count=int(result.get("matured_sample_count") or 0),
        matured_unique_decision_date_count=int(result.get("matured_unique_decision_date_count") or 0),
        observed_champion_brier_bp=int(result.get("observed_champion_brier_bp") or 0),
        observed_candidate_brier_bp=int(result.get("observed_candidate_brier_bp") or 0),
        observed_brier_improvement_bp=int(result.get("observed_brier_improvement_bp") or 0),
        observed_calibration_gap_bp=int(result.get("observed_calibration_gap_bp") or 0),
        after_cost_evaluation_status=str(receipt_payload.get("after_cost_evaluation_status") or "unknown"),
        after_cost_matured_sample_count=int(receipt_payload.get("after_cost_matured_sample_count") or 0),
        observed_champion_after_cost_brier_bp=_optional_int(
            receipt_payload.get("observed_champion_after_cost_brier_bp")
        ),
        observed_candidate_after_cost_brier_bp=_optional_int(
            receipt_payload.get("observed_candidate_after_cost_brier_bp")
        ),
        observed_after_cost_brier_improvement_bp=_optional_int(
            receipt_payload.get("observed_after_cost_brier_improvement_bp")
        ),
        observed_after_cost_calibration_gap_bp=_optional_int(
            receipt_payload.get("observed_after_cost_calibration_gap_bp")
        ),
        scope=scope,
        comparisons=comparisons,
    )


def _natural_evidence_reference(evidence: Any) -> tuple[str | None, str | None]:
    if isinstance(evidence, Mapping):
        return (
            str(evidence.get("receipt_path")) if evidence.get("receipt_path") else None,
            str(evidence.get("receipt_hash")) if evidence.get("receipt_hash") else None,
        )
    receipt_path = getattr(evidence, "receipt_path", evidence)
    receipt_hash = getattr(evidence, "receipt_hash", None)
    return (
        str(receipt_path) if receipt_path else None,
        str(receipt_hash) if receipt_hash else None,
    )


class RecommendationCalibrationPromotionAuthority:
    """只採用證據完整且改善達標的 candidate，其他狀況保留 last-good/rule。"""

    def __init__(
        self,
        output_root: str | Path,
        *,
        policy: RecommendationPromotionPolicy | None = None,
    ) -> None:
        self.root = _resolve_io_path(Path(output_root))
        self.policy = policy or RecommendationPromotionPolicy()
        self.decisions_root = self.root / "decisions"
        self.pointer_path = self.root / "recommendation-calibration-active-pointer.json"

    def evaluate_and_apply(
        self,
        *,
        decision_date: str,
        candidate_id: str | None,
        candidate_root: str | Path | None,
        candidate_metadata: Mapping[str, Any] | None,
        natural_evidence: Any,
        data_status: str = "not_checked",
        drift_status: str = "not_checked",
        emergency_rollback: bool = False,
    ) -> RecommendationPromotionDecision:
        day = _date_text(decision_date)
        data_state = data_status.lower().strip()
        drift_state = drift_status.lower().strip()
        data_ready = data_state in {"ready", "observed"}
        # ``pending`` is an explicit model-performance state, not a clean
        # claim.  It permits the natural same-sample gate to decide while the
        # daily report remains visibly pending; only an observed ``drifted``
        # state can trigger automatic rollback.
        drift_clean = drift_state in {"clean", "none", "pending"}
        # ``not_checked`` is an unknown promotion prerequisite: it blocks
        # adoption, but by itself must not manufacture an emergency rollback.
        # A real dependency fault or an explicit operator rollback does use the
        # same-day emergency path so a stale receipt cannot short-circuit it.
        health_fault = data_state in {"failed", "missing", "unavailable", "degraded"} or drift_state in {
            "failed", "missing", "unavailable", "degraded", "drifted"
        }
        unhealthy = not data_ready or not drift_clean
        emergency = emergency_rollback or health_fault
        standard_path = self.decisions_root / f"recommendation-calibration-{day}.json"
        retry_token = ""
        if not emergency:
            self._reconcile_receipt(standard_path)
            if _io_path(standard_path).is_file():
                existing_payload = json.loads(_io_path(standard_path).read_text(encoding="utf-8"))
                supplied_evidence_hash = _receipt_hash(natural_evidence)
                existing_evidence_hash = existing_payload.get("natural_evidence_receipt_hash")
                retryable_existing = (
                    str(existing_payload.get("decision")) == "retain_current"
                    and (
                        supplied_evidence_hash is not None
                        and supplied_evidence_hash != existing_evidence_hash
                    )
                )
                if not retryable_existing:
                    return _decision_from_dict(existing_payload)
                # Keep the receipt filename portable on Windows; the token is
                # still part of the immutable decision identity below.
                retry_token = f"-retry-{str(supplied_evidence_hash)[7:19]}"

        suffix = "-emergency-rollback" if emergency else ""
        receipt_path = self.decisions_root / f"recommendation-calibration-{day}{suffix}{retry_token}.json"
        if _io_path(receipt_path).is_file():
            self._reconcile_receipt(receipt_path)
            return _decision_from_dict(json.loads(_io_path(receipt_path).read_text(encoding="utf-8")))

        pointer, pointer_error = self._read_pointer()
        previous = _pointer_identity(pointer) if pointer_error is None else None
        previous_id = previous.get("candidate_id") if previous else None
        pointer_version = int(pointer.get("pointer_version", 0)) if pointer else 0
        metadata = dict(candidate_metadata or {})
        candidate_identity_error = _verify_candidate_identity(
            candidate_id=candidate_id,
            candidate_root=candidate_root,
            candidate_metadata=metadata,
        )
        natural = _verify_natural_evidence(
            natural_evidence,
            decision_date=day,
            candidate_id=candidate_id,
            candidate_metadata=metadata,
            policy_hash=self.policy.policy_hash,
            maximum_probability_change_bp=self.policy.maximum_probability_change_bp,
        )
        reason = ""
        decision = "retain_current"
        pointer_status = pointer.get("status", "none") if pointer else "none"
        target_identity: dict[str, Any] | None = None
        if pointer_error is not None and not emergency:
            reason = pointer_error
        elif emergency_rollback:
            reason = "explicit_emergency_rollback"
            rollback_identity = self._valid_previous_identity(pointer)
            if rollback_identity is not None:
                decision = "rollback"
                pointer_status = "active"
                target_identity = rollback_identity
            else:
                decision = "rollback"
                pointer_status = "rule_only"
        elif health_fault:
            reason = "data_or_drift_status_fault_fail_closed"
            rollback_identity = self._valid_previous_identity(pointer)
            if rollback_identity is not None:
                decision = "rollback"
                pointer_status = "active"
                target_identity = rollback_identity
            else:
                decision = "rollback"
                pointer_status = "rule_only"
        elif unhealthy:
            reason = "data_or_drift_status_not_checked_fail_closed"
        elif candidate_identity_error is not None:
            reason = candidate_identity_error
        elif _candidate_training_after_decision(metadata, day):
            reason = "candidate_training_as_of_after_decision_fail_closed"
        elif natural["error"] is not None:
            reason = str(natural["error"])
        elif _candidate_gate_blockers(metadata):
            reason = "candidate_forward_data_contract_not_proven"
        elif int(natural["matured_sample_count"]) < self.policy.minimum_natural_matured_samples:
            reason = "natural_forward_evidence_insufficient"
        elif int(natural.get("matured_unique_decision_date_count", 0)) < self.policy.minimum_natural_matured_decision_dates:
            reason = "natural_forward_distinct_decision_dates_insufficient"
        elif int(natural["observed_brier_improvement_bp"]) < self.policy.minimum_brier_improvement_bp:
            reason = "no_predeclared_natural_brier_improvement"
        elif int(natural["observed_calibration_gap_bp"]) > self.policy.maximum_calibration_gap_bp:
            reason = "natural_calibration_gap_exceeds_threshold"
        elif _cooldown_active(pointer, day, self.policy.cooldown_calendar_days):
            reason = "promotion_cooldown_active"
        else:
            decision = "adopt"
            pointer_status = "active"
            reason = "natural_same_sample_same_cost_gates_qualified"
            target_identity = _candidate_identity_from_metadata(candidate_root, metadata)

        if decision == "rollback" and pointer_status == "rule_only":
            target_identity = None
        next_pointer_base: dict[str, Any] | None = None
        decision_id = f"recommendation-calibration:{day}{':emergency-rollback' if emergency else ''}{retry_token}"
        if decision in {"adopt", "rollback"}:
            pointer_version += 1
            next_pointer_base = self._build_pointer_base(
                day=day,
                decision_id=decision_id,
                pointer_version=pointer_version,
                pointer_status=pointer_status,
                target_identity=target_identity,
                current_pointer=pointer,
                decision=decision,
                candidate_metadata=metadata,
                natural_evidence=natural_evidence,
            )
        natural_count = int(natural.get("matured_sample_count", 0))
        old_brier = _optional_int(natural.get("observed_champion_brier_bp"))
        new_brier = _optional_int(natural.get("observed_candidate_brier_bp"))
        improvement = _optional_int(natural.get("observed_brier_improvement_bp"))
        gap = _optional_int(natural.get("observed_calibration_gap_bp"))
        pointer_hash = _pointer_content_hash(next_pointer_base) if next_pointer_base else None
        receipt_payload: dict[str, Any] = {
            "schema_version": "recommendation-calibration-decision-receipt.v2",
            "decision_id": decision_id,
            "decision_date": day,
            "decision": decision,
            "reason": reason,
            "candidate_id": target_identity.get("candidate_id") if target_identity else previous_id,
            "previous_candidate_id": previous_id,
            "pointer_version": pointer_version,
            "pointer_status": pointer_status,
            "pointer_content_hash": pointer_hash,
            "next_pointer_base": next_pointer_base,
            "natural_evidence_receipt_hash": natural.get("receipt_hash"),
            "natural_matured_sample_count": natural_count,
            "natural_matured_decision_date_count": int(natural.get("matured_unique_decision_date_count", 0)),
            "old_brier_bp": old_brier,
            "new_brier_bp": new_brier,
            "brier_improvement_bp": improvement,
            "calibration_gap_bp": gap,
            "maximum_probability_change_bp": self.policy.maximum_probability_change_bp,
            "candidate_freeze_hash": metadata.get("candidate_freeze_hash"),
            "authority_family": AUTHORITY_FAMILY,
            "authority_scope": AUTHORITY_SCOPE,
            "formal_order_allowed": False,
            "receipt_path": str(receipt_path),
            "pointer_path": str(self.pointer_path),
        }
        try:
            receipt_scenario = _scenario_from_metadata(
                target_identity or metadata or (pointer or {})
            )
        except (TypeError, ValueError, RecommendationCostScenarioError):
            receipt_scenario = None
        if receipt_scenario is not None and receipt_scenario.is_estimated:
            receipt_payload.update(
                _scenario_identity_fields(
                    receipt_scenario,
                    target_identity or metadata or (pointer or {}),
                )
            )
            receipt_payload["liquidity_cost_role"] = (
                "diagnostic_only_not_in_fees_tax_only_label"
            )
        # Receipt first makes an interrupted publication recoverable/reconcilable.
        _write_json_once(receipt_path, receipt_payload)
        if next_pointer_base is not None:
            next_pointer = dict(next_pointer_base)
            next_pointer["decision_receipt_path"] = str(receipt_path)
            next_pointer["decision_receipt_hash"] = _sha256_file(receipt_path)
            self._write_pointer(next_pointer)
        _write_json(self.root / "latest_decision.json", receipt_payload)
        return _decision_from_dict(receipt_payload)

    def _build_pointer_base(
        self,
        *,
        day: str,
        decision_id: str,
        pointer_version: int,
        pointer_status: str,
        target_identity: Mapping[str, Any] | None,
        current_pointer: Mapping[str, Any] | None,
        decision: str,
        candidate_metadata: Mapping[str, Any],
        natural_evidence: Any,
    ) -> dict[str, Any]:
        target = dict(target_identity or {})
        current = dict(current_pointer or {})
        is_adopt = decision == "adopt"
        current_lineage = _pointer_probability_lineage(current_pointer)
        desired_scenario: RecommendationCostScenario | None = None
        try:
            desired_scenario = _scenario_from_metadata(
                candidate_metadata if is_adopt else target if target else current
            )
        except (TypeError, ValueError, RecommendationCostScenarioError):
            pass
        same_cost_lane = True
        if is_adopt and desired_scenario is not None and current:
            try:
                same_cost_lane = (
                    _scenario_from_metadata(current).scenario_hash
                    == desired_scenario.scenario_hash
                )
            except (TypeError, ValueError, RecommendationCostScenarioError):
                same_cost_lane = False
            if not same_cost_lane:
                # A new cost contract starts an isolated active lineage.  A
                # legacy champion is not silently used as a same-cost baseline.
                current_lineage = [
                    _probability_lineage_null_node(
                        self.policy.maximum_probability_change_bp
                    )
                ]
        if is_adopt:
            previous_lineage = current_lineage
            target_lineage = previous_lineage + [
                _probability_lineage_model_node(
                    _candidate_identity_from_metadata(target.get("candidate_root"), candidate_metadata),
                    baseline_id=(
                        str(previous_lineage[-1].get("candidate_id") or "")
                        if previous_lineage and previous_lineage[-1].get("kind") == "active_model"
                        else NULL_BENCHMARK_BASELINE_ID
                    ),
                    baseline_kind=(
                        "active_model"
                        if previous_lineage and previous_lineage[-1].get("kind") == "active_model"
                        else "null_benchmark"
                    ),
                    maximum_probability_change_bp=self.policy.maximum_probability_change_bp,
                )
            ]
        elif pointer_status == "active" and target:
            # A rollback restores the complete lineage that produced the
            # previous champion.  Keeping only the previous raw model would
            # make the next cap relative to the wrong (untransformed) value.
            target_lineage = _pointer_previous_probability_lineage(current_pointer)
            if not target_lineage or target_lineage[-1].get("candidate_id") != target.get("candidate_id"):
                target_lineage = [
                    _probability_lineage_null_node(self.policy.maximum_probability_change_bp),
                    _probability_lineage_model_node(
                        target,
                        baseline_id=NULL_BENCHMARK_BASELINE_ID,
                        baseline_kind="null_benchmark",
                        maximum_probability_change_bp=self.policy.maximum_probability_change_bp,
                    ),
                ]
            previous_lineage = target_lineage[:-1] or [
                _probability_lineage_null_node(self.policy.maximum_probability_change_bp)
            ]
        else:
            target_lineage = [_probability_lineage_null_node(self.policy.maximum_probability_change_bp)]
            previous_lineage = target_lineage
        scenario_metadata: Mapping[str, Any] = (
            candidate_metadata if is_adopt else target if target else current
        )
        try:
            pointer_scenario = _scenario_from_metadata(scenario_metadata)
        except (TypeError, ValueError, RecommendationCostScenarioError):
            pointer_scenario = None
        fixed_cost_value = (
            candidate_metadata.get("fixed_round_trip_cost_bp")
            if is_adopt and candidate_metadata.get("fixed_round_trip_cost_bp") is not None
            else target.get("fixed_round_trip_cost_bp")
            if not is_adopt and target.get("fixed_round_trip_cost_bp") is not None
            else current.get("fixed_round_trip_cost_bp")
        )
        pointer_base: dict[str, Any] = {
            "schema_version": "recommendation-calibration-active-pointer.v2",
            "pointer_version": pointer_version,
            "status": pointer_status,
            "effective_date": day,
            "decision_id": decision_id,
            "candidate_id": target.get("candidate_id"),
            "candidate_root": target.get("candidate_root"),
            "candidate_manifest_hash": target.get("candidate_manifest_hash"),
            "candidate_artifact_hash": target.get("candidate_artifact_hash"),
            "candidate_freeze_hash": target.get("candidate_freeze_hash"),
            "dataset_hash": target.get("dataset_hash"),
            "previous_candidate_id": current.get("candidate_id") if is_adopt and same_cost_lane else target.get("previous_candidate_id"),
            "previous_candidate_root": current.get("candidate_root") if is_adopt and same_cost_lane else target.get("previous_candidate_root"),
            "previous_candidate_manifest_hash": current.get("candidate_manifest_hash") if is_adopt and same_cost_lane else target.get("previous_candidate_manifest_hash"),
            "previous_candidate_artifact_hash": current.get("candidate_artifact_hash") if is_adopt and same_cost_lane else target.get("previous_candidate_artifact_hash"),
            "previous_candidate_freeze_hash": current.get("candidate_freeze_hash") if is_adopt and same_cost_lane else target.get("previous_candidate_freeze_hash"),
            "previous_dataset_hash": current.get("dataset_hash") if is_adopt and same_cost_lane else target.get("previous_dataset_hash"),
            "previous_previous_candidate_id": current.get("previous_candidate_id") if is_adopt and same_cost_lane else target.get("previous_previous_candidate_id"),
            "previous_previous_candidate_root": current.get("previous_candidate_root") if is_adopt and same_cost_lane else target.get("previous_previous_candidate_root"),
            "previous_previous_candidate_manifest_hash": current.get("previous_candidate_manifest_hash") if is_adopt and same_cost_lane else target.get("previous_previous_candidate_manifest_hash"),
            "previous_previous_candidate_artifact_hash": current.get("previous_candidate_artifact_hash") if is_adopt and same_cost_lane else target.get("previous_previous_candidate_artifact_hash"),
            "previous_previous_candidate_freeze_hash": current.get("previous_candidate_freeze_hash") if is_adopt and same_cost_lane else target.get("previous_previous_candidate_freeze_hash"),
            "last_good_candidate_id": target.get("candidate_id") if is_adopt else current.get("last_good_candidate_id"),
            "fixed_round_trip_cost_bp": fixed_cost_value,
            "maximum_probability_change_bp": self.policy.maximum_probability_change_bp,
            "probability_lineage_schema_version": PROBABILITY_LINEAGE_SCHEMA_VERSION,
            "probability_lineage": target_lineage,
            "previous_probability_lineage": previous_lineage,
            "policy_hash": self.policy.policy_hash,
            "natural_evidence_receipt_hash": _receipt_hash(natural_evidence) or current.get("natural_evidence_receipt_hash"),
            "authority_family": AUTHORITY_FAMILY,
            "authority_scope": AUTHORITY_SCOPE,
            "formal_order_allowed": False,
        }
        if pointer_scenario is not None and pointer_scenario.is_estimated:
            pointer_base.update(_scenario_identity_fields(pointer_scenario, scenario_metadata))
            if is_adopt and same_cost_lane:
                for field_name in (
                    "label_registry_hash", "cost_contract_hash", "fixed_round_trip_cost_bp",
                    "cost_scenario_id", "cost_scenario_version", "cost_scenario_hash",
                    "cost_basis", "cost_policy_id", "cost_policy_version",
                    "policy_estimate_date", "research_order_amount_twd",
                    "research_order_quantity_shares", "lot_type", "instrument_type",
                    "cost_scenario",
                ):
                    if field_name in current:
                        pointer_base[f"previous_{field_name}"] = current[field_name]
        return pointer_base

    def _valid_previous_identity(self, pointer: Mapping[str, Any] | None) -> dict[str, Any] | None:
        if not pointer or pointer.get("status") != "active":
            return None
        previous = {
            "candidate_id": pointer.get("previous_candidate_id"),
            "candidate_root": pointer.get("previous_candidate_root"),
            "candidate_manifest_hash": pointer.get("previous_candidate_manifest_hash"),
            "candidate_artifact_hash": pointer.get("previous_candidate_artifact_hash"),
            "candidate_freeze_hash": pointer.get("previous_candidate_freeze_hash"),
            "dataset_hash": pointer.get("previous_dataset_hash"),
            "previous_candidate_id": pointer.get("previous_previous_candidate_id"),
            "previous_candidate_root": pointer.get("previous_previous_candidate_root"),
            "previous_candidate_manifest_hash": pointer.get("previous_previous_candidate_manifest_hash"),
            "previous_candidate_artifact_hash": pointer.get("previous_previous_candidate_artifact_hash"),
            "previous_candidate_freeze_hash": pointer.get("previous_previous_candidate_freeze_hash"),
            "previous_dataset_hash": pointer.get("previous_previous_dataset_hash"),
        }
        previous_field_map = {
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
        for target, source in previous_field_map.items():
            if source in pointer:
                previous[target] = pointer[source]
        required = (
            "candidate_id", "candidate_root", "candidate_manifest_hash",
            "candidate_artifact_hash", "candidate_freeze_hash",
        )
        if not all(previous.get(key) for key in required):
            return None
        if _verify_candidate_identity(
            candidate_id=str(previous["candidate_id"]),
            candidate_root=str(previous["candidate_root"]),
            candidate_metadata={
                "candidate_id": previous["candidate_id"],
                "candidate_freeze_hash": previous["candidate_freeze_hash"],
                "manifest_hash": previous["candidate_manifest_hash"],
                "artifact_hash": previous["candidate_artifact_hash"],
                "dataset_hash": previous.get("dataset_hash"),
            },
        ) is not None:
            return None
        return previous

    def _read_pointer(self) -> tuple[dict[str, Any] | None, str | None]:
        if not _io_path(self.pointer_path).is_file():
            return None, None
        try:
            payload = json.loads(_io_path(self.pointer_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None, "active_pointer_invalid_json"
        if not isinstance(payload, Mapping):
            return None, "active_pointer_invalid_payload"
        pointer = dict(payload)
        if pointer.get("schema_version") not in {
            "recommendation-calibration-active-pointer.v1",
            "recommendation-calibration-active-pointer.v2",
        }:
            return None, "active_pointer_schema_invalid"
        if pointer.get("policy_hash") != self.policy.policy_hash:
            return None, "active_pointer_policy_hash_mismatch"
        try:
            pointer_scenario = _scenario_from_metadata(pointer)
        except (TypeError, ValueError, RecommendationCostScenarioError):
            return None, "active_pointer_cost_scenario_invalid"
        expected_label_hash = _label_registry_hash(pointer_scenario)
        if pointer.get("label_registry_hash") not in (None, expected_label_hash):
            return None, "active_pointer_label_registry_mismatch"
        expected_cost_hash = _cost_contract_hash(pointer_scenario)
        if pointer.get("cost_contract_hash") not in (None, expected_cost_hash):
            return None, "active_pointer_cost_contract_mismatch"
        if pointer_scenario.is_estimated and pointer.get("fixed_round_trip_cost_bp") is not None:
            return None, "active_pointer_estimated_fixed_cost_mismatch"
        if pointer.get("status") == "active" and not all(pointer.get(key) for key in (
            "candidate_id", "candidate_root", "candidate_manifest_hash",
            "candidate_artifact_hash", "candidate_freeze_hash",
        )):
            return None, "active_pointer_identity_incomplete"
        if pointer.get("status") == "active" and not _valid_probability_lineage(pointer, self.policy.maximum_probability_change_bp):
            return None, "active_pointer_probability_lineage_invalid"
        if pointer.get("decision_receipt_path"):
            receipt_path = Path(str(pointer["decision_receipt_path"]))
            if not _io_path(receipt_path).is_file() or pointer.get("decision_receipt_hash") != _sha256_file(receipt_path):
                return None, "active_pointer_receipt_mismatch"
            if pointer.get("decision_id") != _safe_json_field(receipt_path, "decision_id"):
                return None, "active_pointer_receipt_decision_mismatch"
        return pointer, None

    def _reconcile_receipt(self, receipt_path: Path) -> None:
        if not _io_path(receipt_path).is_file():
            return
        try:
            payload = json.loads(_io_path(receipt_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        next_pointer = payload.get("next_pointer_base")
        if not isinstance(next_pointer, Mapping):
            return
        pointer = dict(next_pointer)
        pointer["decision_receipt_path"] = str(receipt_path)
        pointer["decision_receipt_hash"] = _sha256_file(receipt_path)
        if _io_path(self.pointer_path).is_file():
            try:
                existing = json.loads(_io_path(self.pointer_path).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                existing = None
            if isinstance(existing, Mapping):
                existing_version = _optional_int(existing.get("pointer_version")) or 0
                next_version = _optional_int(pointer.get("pointer_version")) or 0
                # An old receipt can never overwrite a newer active/revoked pointer.
                if existing_version > next_version:
                    return
                if existing_version == next_version and existing != pointer:
                    return
                if existing == pointer:
                    return
        self._write_pointer(pointer)

    def _write_pointer(self, payload: Mapping[str, Any]) -> None:
        _write_json(self.pointer_path, payload)


def _verify_candidate_identity(
    *,
    candidate_id: str | None,
    candidate_root: str | Path | None,
    candidate_metadata: Mapping[str, Any],
) -> str | None:
    if not candidate_id or not candidate_root:
        return "candidate_identity_missing"
    root = _resolve_io_path(Path(candidate_root))
    manifest_path = root / "manifest.json"
    candidate_path = root / "candidate.json"
    if not _io_path(root).is_dir() or not _io_path(manifest_path).is_file() or not _io_path(candidate_path).is_file():
        return "candidate_freeze_files_missing"
    try:
        manifest_payload = json.loads(_io_path(manifest_path).read_text(encoding="utf-8"))
        manifest = ModelArtifactManifest.from_dict(manifest_payload)
        candidate_payload = json.loads(_io_path(candidate_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return "candidate_freeze_metadata_invalid"
    artifact_path = root / manifest.artifact_filename
    if not _io_path(artifact_path).is_file() or _sha256_file(artifact_path) != manifest.artifact_hash:
        return "candidate_artifact_hash_mismatch"
    if manifest.model_id != candidate_id or candidate_payload.get("candidate_id") != candidate_id:
        return "candidate_identity_mismatch"
    if candidate_payload.get("manifest_hash") != manifest.manifest_hash:
        return "candidate_manifest_hash_mismatch"
    if str(candidate_metadata.get("artifact_hash") or manifest.artifact_hash) != manifest.artifact_hash:
        return "candidate_metadata_artifact_hash_mismatch"
    if str(candidate_metadata.get("manifest_hash") or manifest.manifest_hash) != manifest.manifest_hash:
        return "candidate_metadata_manifest_hash_mismatch"
    for field_name in (
        "dataset_id",
        "dataset_hash",
        "feature_registry_hash",
        "feature_schema_hash",
        "label_registry_hash",
        "model_id",
        "model_family",
        "training_as_of",
        "horizon_trading_days",
    ):
        supplied = candidate_metadata.get(field_name)
        actual = candidate_payload.get(field_name)
        if supplied is not None and str(supplied) != str(actual):
            return f"candidate_metadata_{field_name}_mismatch"
    try:
        actual_scenario = cost_scenario_from_metadata(
            candidate_payload,
            fixed_round_trip_cost_bp=_optional_int(candidate_payload.get("fixed_round_trip_cost_bp")),
        )
        supplied_scenario = cost_scenario_from_metadata(
            candidate_metadata,
            fixed_round_trip_cost_bp=_optional_int(candidate_metadata.get("fixed_round_trip_cost_bp")),
        )
    except (TypeError, ValueError, RecommendationCostScenarioError):
        return "candidate_cost_scenario_invalid"
    if actual_scenario.scenario_hash != supplied_scenario.scenario_hash:
        return "candidate_cost_scenario_mismatch"
    expected_label_hash = _label_registry_hash(actual_scenario)
    if candidate_payload.get("label_registry_hash") != expected_label_hash:
        return "candidate_label_registry_contract_mismatch"
    expected_cost_hash = _cost_contract_hash(actual_scenario)
    if candidate_payload.get("cost_contract_hash") not in (None, expected_cost_hash):
        return "candidate_cost_contract_mismatch"
    supplied_label_hash = candidate_metadata.get("label_registry_hash")
    if supplied_label_hash is not None and str(supplied_label_hash) != expected_label_hash:
        return "candidate_metadata_label_registry_contract_mismatch"
    supplied_cost_hash = candidate_metadata.get("cost_contract_hash")
    if supplied_cost_hash is not None and str(supplied_cost_hash) != expected_cost_hash:
        return "candidate_metadata_cost_contract_mismatch"
    expected_freeze = candidate_freeze_hash(
        candidate_id=candidate_id,
        dataset_hash=str(candidate_payload.get("dataset_hash") or candidate_metadata.get("dataset_hash") or ""),
        manifest_hash=manifest.manifest_hash,
        artifact_hash=manifest.artifact_hash,
        evaluation=_mapping(candidate_payload.get("evaluation")),
    )
    supplied_freeze = str(candidate_metadata.get("candidate_freeze_hash") or candidate_payload.get("candidate_freeze_hash") or "")
    if supplied_freeze != expected_freeze:
        return "candidate_freeze_hash_mismatch"
    if candidate_payload.get("shadow_only") is not True or candidate_payload.get("production_action_allowed") is not False:
        return "candidate_shadow_flags_invalid"
    return None


def _verify_natural_evidence(
    evidence: Any,
    *,
    decision_date: str,
    candidate_id: str | None,
    candidate_metadata: Mapping[str, Any],
    policy_hash: str,
    maximum_probability_change_bp: int,
) -> dict[str, Any]:
    """Read the receipt as SSOT and recompute metrics from its matched rows."""

    result: dict[str, Any] = {
        "error": None,
        "matured_sample_count": 0,
        "matured_unique_decision_date_count": 0,
        "receipt_hash": None,
        "observed_champion_brier_bp": None,
        "observed_candidate_brier_bp": None,
        "observed_brier_improvement_bp": None,
        "observed_calibration_gap_bp": None,
    }
    if isinstance(evidence, Mapping):
        receipt_path_text = evidence.get("receipt_path")
        receipt_hash_expected = evidence.get("receipt_hash")
    else:
        receipt_path_text = getattr(evidence, "receipt_path", evidence)
        receipt_hash_expected = getattr(evidence, "receipt_hash", None)
    if not receipt_path_text:
        result["error"] = "natural_forward_evidence_receipt_missing"
        return result
    receipt_path = _resolve_io_path(Path(str(receipt_path_text)))
    if not _io_path(receipt_path).is_file():
        result["error"] = "natural_forward_evidence_receipt_missing"
        return result
    receipt_hash = _sha256_file(receipt_path)
    if receipt_hash_expected and str(receipt_hash_expected) != receipt_hash:
        result["error"] = "natural_evidence_receipt_hash_mismatch"
        return result
    try:
        receipt_payload = json.loads(_io_path(receipt_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        result["error"] = "natural_evidence_receipt_invalid"
        return result
    if not isinstance(receipt_payload, Mapping):
        result["error"] = "natural_evidence_receipt_invalid"
        return result
    semantic_body = {
        key: value
        for key, value in receipt_payload.items()
        if key not in {"receipt_body_hash", "receipt_hash", "receipt_path"}
    }
    if receipt_payload.get("receipt_body_hash") != _hash_payload(semantic_body):
        result["error"] = "natural_evidence_receipt_body_hash_mismatch"
        return result
    required = (
        "schema_version", "evidence_id", "source_id", "source_kind", "status", "as_of_date",
        "capture_id", "capture_hash", "capture_as_of_date", "captured_at", "candidate_frozen_at",
        "candidate_id", "candidate_freeze_hash", "candidate_manifest_hash", "candidate_artifact_hash",
        "dataset_hash", "feature_registry_hash", "feature_schema_hash", "feature_schema",
        "label_registry_hash", "cost_contract_hash", "fixed_round_trip_cost_bp",
        "maximum_probability_change_bp", "policy_hash",
        "evaluation_at", "maturity_session_resolver_id",
        "maturity_session_resolver_version",
        "probability_transform_id", "probability_baseline_id", "probability_baseline_kind",
        "probability_lineage",
        "champion_model_id", "champion_candidate_id", "champion_candidate_root",
        "champion_manifest_hash", "champion_artifact_hash", "champion_freeze_hash",
        "champion_pointer_version", "source_capture_ids", "source_capture_hashes",
        "source_capture_paths",
        "matured_sample_count", "comparison_sample_fingerprint", "candidate_prediction_hash",
        "champion_prediction_hash", "same_date_same_cost", "comparisons",
        "observed_champion_brier_bp", "observed_candidate_brier_bp",
        "observed_brier_improvement_bp", "observed_calibration_gap_bp",
        "capture_path", "after_cost_evaluation_status", "after_cost_matured_sample_count",
        "observed_champion_after_cost_brier_bp", "observed_candidate_after_cost_brier_bp",
        "observed_after_cost_brier_improvement_bp", "observed_after_cost_calibration_gap_bp",
        "after_cost_candidate_prediction_hash", "after_cost_champion_prediction_hash",
        "capture_origin",
    )
    if any(key not in receipt_payload for key in required):
        result["error"] = "natural_evidence_field_missing"
        return result
    if receipt_payload.get("schema_version") not in {
        "recommendation-natural-forward-evidence.v2",
        "recommendation-natural-forward-evidence.v3",
    }:
        result["error"] = "natural_evidence_schema_invalid"
        return result
    if str(receipt_payload.get("source_kind")) != "matured_forward_prediction_capture":
        result["error"] = "natural_evidence_source_not_prediction_capture"
        return result
    if str(receipt_payload.get("status")).lower() not in NATURAL_EVIDENCE_STATUSES:
        result["error"] = "natural_forward_evidence_status_not_matured"
        return result
    if receipt_payload.get("same_date_same_cost") is not True:
        result["error"] = "natural_evidence_same_date_same_cost_not_proven"
        return result
    source_id = str(receipt_payload.get("source_id") or "").lower()
    if not source_id or any(token in source_id for token in ("fixture", "synthetic", "test")):
        result["error"] = "natural_evidence_source_not_trusted"
        return result
    capture_path_text = str(receipt_payload.get("capture_path") or "").strip()
    capture_path = _resolve_io_path(Path(capture_path_text)) if capture_path_text else None
    if capture_path is None or not _io_path(capture_path).is_file():
        result["error"] = "natural_evidence_capture_artifact_missing"
        return result
    expected_source_db_path: Path | None = None
    try:
        from ml_module.recommendation_calibration_evidence import (
            _verify_capture_bundle_payload,
            _verify_capture_payload,
            verified_source_database_for_capture,
        )
        capture_payload = json.loads(_io_path(capture_path).read_text(encoding="utf-8"))
        if not isinstance(capture_payload, Mapping):
            raise ValueError
        if capture_payload.get("schema_version") == "recommendation-prediction-capture-bundle.v1":
            _verify_capture_bundle_payload(capture_payload)
        else:
            _verify_capture_payload(capture_payload)
        if capture_payload.get("capture_hash") != receipt_payload.get("capture_hash"):
            raise ValueError("receipt capture hash mismatch")
        for field_name in (
            "capture_id", "capture_as_of_date", "candidate_id", "candidate_freeze_hash",
            "candidate_manifest_hash", "candidate_artifact_hash", "dataset_hash",
            "feature_registry_hash", "feature_schema_hash", "label_registry_hash",
            "cost_contract_hash", "fixed_round_trip_cost_bp", "maximum_probability_change_bp", "policy_hash",
            "probability_transform_id", "probability_baseline_id", "probability_baseline_kind",
            "probability_lineage",
            "champion_model_id", "champion_candidate_id", "champion_candidate_root",
            "champion_manifest_hash", "champion_artifact_hash", "champion_freeze_hash",
            "champion_pointer_version", "source_capture_ids", "source_capture_hashes",
            "source_capture_paths",
            "capture_origin",
        ):
            capture_value = capture_payload.get(field_name)
            if field_name == "source_capture_ids" and capture_value is None:
                capture_value = [capture_payload.get("capture_id")]
            elif field_name == "source_capture_hashes" and capture_value is None:
                capture_value = [capture_payload.get("capture_hash")]
            elif field_name == "source_capture_paths" and capture_value is None:
                capture_value = [capture_payload.get("capture_path")]
            if capture_value != receipt_payload.get(field_name):
                raise ValueError(f"capture binding mismatch: {field_name}")
        if str(capture_payload.get("capture_origin")) not in {
            "scheduled_live", "live_forward", "scheduled_live_bundle"
        }:
            raise ValueError("capture origin is not live")
        expected_source_db_path = verified_source_database_for_capture(capture_payload)
        if int(capture_payload.get("maximum_probability_change_bp", -1)) != int(
            receipt_payload.get("maximum_probability_change_bp", -2)
        ):
            raise ValueError("capture probability cap binding mismatch")
        candidate_scenario = _scenario_from_metadata(candidate_metadata)
        capture_scenario = _scenario_from_metadata(capture_payload)
        receipt_scenario = _scenario_from_metadata(receipt_payload)
        if capture_scenario.scenario_hash != candidate_scenario.scenario_hash:
            raise ValueError("capture cost scenario does not match candidate")
        if receipt_scenario.scenario_hash != candidate_scenario.scenario_hash:
            raise ValueError("natural evidence cost scenario does not match candidate")
        if receipt_payload.get("schema_version") == "recommendation-natural-forward-evidence.v3" and not candidate_scenario.is_estimated:
            raise ValueError("natural evidence v3 must use estimated cost scenario")
        if receipt_payload.get("schema_version") == "recommendation-natural-forward-evidence.v2" and candidate_scenario.is_estimated:
            raise ValueError("natural evidence v2 cannot use estimated cost scenario")
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        result["error"] = "natural_evidence_capture_artifact_invalid"
        return result
    try:
        as_of = _date_text(str(receipt_payload["as_of_date"]))
        evaluation_at = _strict_evaluation_at(str(receipt_payload["evaluation_at"]))
        if evaluation_at.astimezone(ZoneInfo("Asia/Taipei")).date().isoformat() != as_of:
            raise ValueError
        if evaluation_at > datetime.now(timezone.utc):
            raise ValueError
        capture_day = _date_text(str(receipt_payload["capture_as_of_date"]))
        decision_day = _date_text(decision_date)
        if as_of > decision_day or capture_day > as_of:
            raise ValueError
        if _date_text(str(receipt_payload["captured_at"])) > capture_day:
            raise ValueError
        if _datetime_text(str(receipt_payload["candidate_frozen_at"])) > _datetime_text(str(receipt_payload["captured_at"])):
            raise ValueError
    except ValueError:
        result["error"] = "natural_evidence_timestamp_or_as_of_invalid"
        return result
    try:
        candidate_scenario = _scenario_from_metadata(candidate_metadata)
        fixed_cost = candidate_scenario.fixed_round_trip_cost_bp
        expected_cost_hash = _cost_contract_hash(candidate_scenario)
        expected_label_hash = _label_registry_hash(candidate_scenario)
    except (TypeError, ValueError, RecommendationCostScenarioError):
        result["error"] = "natural_evidence_candidate_cost_contract_invalid"
        return result
    expected_metadata = {
        "candidate_id": candidate_id,
        "candidate_freeze_hash": candidate_metadata.get("candidate_freeze_hash"),
        "candidate_manifest_hash": candidate_metadata.get("manifest_hash"),
        "candidate_artifact_hash": candidate_metadata.get("artifact_hash"),
        "dataset_hash": candidate_metadata.get("dataset_hash"),
        "feature_registry_hash": candidate_metadata.get("feature_registry_hash"),
        "feature_schema_hash": candidate_metadata.get("feature_schema_hash"),
        "label_registry_hash": expected_label_hash,
        "cost_contract_hash": expected_cost_hash,
        "fixed_round_trip_cost_bp": fixed_cost,
        "maximum_probability_change_bp": maximum_probability_change_bp,
        "policy_hash": policy_hash,
    }
    for key, expected_value in expected_metadata.items():
        if (
            key == "fixed_round_trip_cost_bp"
            and candidate_scenario.is_estimated
            and expected_value is None
        ):
            # The estimated fees/tax-only lane deliberately carries no fixed
            # bp value.  ``None`` is a meaningful contract value here, not a
            # missing binding.
            if receipt_payload.get(key) is not None:
                result["error"] = f"natural_evidence_candidate_binding_mismatch:{key}"
                return result
            continue
        if expected_value is None or str(receipt_payload.get(key)) != str(expected_value):
            result["error"] = f"natural_evidence_candidate_binding_mismatch:{key}"
            return result
    if candidate_scenario.is_estimated:
        for key in (
            "cost_scenario_id", "cost_scenario_version", "cost_scenario_hash",
            "cost_basis", "cost_policy_id", "cost_policy_version",
            "policy_estimate_date", "research_order_amount_twd",
            "research_order_quantity_shares", "lot_type", "instrument_type",
            "cost_scenario",
        ):
            if receipt_payload.get(key) != candidate_metadata.get(key):
                result["error"] = f"natural_evidence_candidate_binding_mismatch:{key}"
                return result
    try:
        if int(receipt_payload["maximum_probability_change_bp"]) != int(maximum_probability_change_bp):
            result["error"] = "natural_evidence_probability_cap_mismatch"
            return result
    except (KeyError, TypeError, ValueError):
        result["error"] = "natural_evidence_probability_cap_invalid"
        return result
    try:
        candidate_frozen_at = _datetime_text(str(candidate_metadata.get("candidate_frozen_at") or ""))
        if candidate_frozen_at > _datetime_text(str(receipt_payload["captured_at"])):
            result["error"] = "candidate_freeze_after_prediction_capture"
            return result
    except ValueError:
        result["error"] = "candidate_freeze_timestamp_invalid"
        return result
    comparisons = receipt_payload.get("comparisons")
    if not isinstance(comparisons, list) or not comparisons:
        result["error"] = "natural_evidence_comparisons_missing"
        return result
    if not str(receipt_payload.get("maturity_session_resolver_id") or "").strip():
        result["error"] = "natural_evidence_session_resolver_missing"
        return result
    if not str(receipt_payload.get("maturity_session_resolver_version") or "").strip():
        result["error"] = "natural_evidence_session_resolver_missing"
        return result
    if expected_source_db_path is None:
        result["error"] = "natural_evidence_source_database_anchor_missing"
        return result
    if int(receipt_payload["matured_sample_count"]) != len(comparisons):
        result["error"] = "natural_evidence_count_mismatch"
        return result
    row_ids: list[str] = []
    comparison_keys: set[tuple[str, str, str, int]] = set()
    decision_dates: set[str] = set()
    candidate_probabilities: list[int] = []
    champion_probabilities: list[int] = []
    labels: list[int] = []
    for row in comparisons:
        if not isinstance(row, Mapping):
            result["error"] = "natural_evidence_comparison_invalid"
            return result
        row_id = str(row.get("capture_row_id") or "")
        if not row_id or row_id in row_ids:
            result["error"] = "natural_evidence_comparison_row_id_invalid"
            return result
        row_ids.append(row_id)
        try:
            row_capture_day = _date_text(str(row["capture_as_of_date"]))
            comparison_key = (
                candidate_scenario.scenario_hash
                if candidate_scenario.is_estimated
                else "legacy-fixed-round-trip-bp",
                str(row.get("symbol") or ""),
                row_capture_day,
                20,
            )
            if comparison_key in comparison_keys:
                raise ValueError("duplicate symbol decision horizon comparison")
            comparison_keys.add(comparison_key)
            decision_dates.add(row_capture_day)
            candidate_probability = int(row["candidate_probability_bp"])
            champion_probability = int(row["champion_probability_bp"])
            stock_return = int(row["stock_return_bp"])
            candidate_label = int(row["upside_label"])
            if not 0 <= candidate_probability <= 10_000 or not 0 <= champion_probability <= 10_000:
                raise ValueError
            if candidate_label != int(stock_return > 0):
                raise ValueError
            capture_rows = capture_payload.get("rows")
            if not isinstance(capture_rows, list):
                raise ValueError
            capture_row = next(
                (item for item in capture_rows if isinstance(item, Mapping) and str(item.get("row_id")) == row_id),
                None,
            )
            if capture_row is None:
                raise ValueError
            if _required_int(capture_row.get("candidate_probability_bp"), "candidate_probability_bp") != candidate_probability:
                raise ValueError
            if _required_int(capture_row.get("champion_probability_bp"), "champion_probability_bp") != champion_probability:
                raise ValueError
            for field_name in (
                "probability_transform_id",
                "probability_baseline_id",
                "probability_baseline_kind",
                "champion_probability_lineage",
            ):
                if row.get(field_name) != capture_row.get(field_name):
                    raise ValueError
            raw_candidate_probability = int(capture_row["candidate_model_probability_bp"])
            if _required_int(row.get("candidate_model_probability_bp"), "candidate_model_probability_bp") != raw_candidate_probability:
                raise ValueError
            transform = RecommendationProbabilityTransform(
                baseline_id=str(row.get("probability_baseline_id") or receipt_payload["probability_baseline_id"]),
                maximum_probability_change_bp=maximum_probability_change_bp,
            )
            if candidate_probability != transform.apply(
                raw_candidate_probability,
                champion_probability,
            ):
                raise ValueError
            if row.get("candidate_model_after_cost_probability_bp") != capture_row.get(
                "candidate_model_after_cost_probability_bp"
            ):
                raise ValueError
            if row.get("candidate_after_cost_probability_bp") != capture_row.get("candidate_after_cost_probability_bp"):
                raise ValueError
            if row.get("champion_after_cost_probability_bp") != capture_row.get("champion_after_cost_probability_bp"):
                raise ValueError
            raw_after_cost_probability = capture_row.get("candidate_model_after_cost_probability_bp")
            champion_after_cost_probability = capture_row.get("champion_after_cost_probability_bp")
            effective_after_cost_probability = capture_row.get("candidate_after_cost_probability_bp")
            if raw_after_cost_probability is None:
                if effective_after_cost_probability is not None:
                    raise ValueError
            elif effective_after_cost_probability != transform.apply(
                int(raw_after_cost_probability),
                int(champion_after_cost_probability) if champion_after_cost_probability is not None else None,
            ):
                raise ValueError
            if str(row.get("symbol")) != str(capture_row.get("symbol")):
                raise ValueError
            session_proof = row.get("maturity_session_proof")
            if not isinstance(session_proof, Mapping):
                raise ValueError("natural evidence official session proof is missing")
            from ml_module.recommendation_calibration_evidence import (
                verify_natural_maturity_session_proof,
            )

            verified_session_proof = verify_natural_maturity_session_proof(
                session_proof,
                capture_date=row_capture_day,
                label_end_date=str(row.get("label_end_date") or ""),
                evaluation_at=evaluation_at,
                expected_db_path=expected_source_db_path,
            )
            if (
                verified_session_proof.get("resolver_id")
                != receipt_payload.get("maturity_session_resolver_id")
                or verified_session_proof.get("resolver_version")
                != receipt_payload.get("maturity_session_resolver_version")
            ):
                raise ValueError("natural evidence session resolver identity mismatch")
            if _date_text(str(row["label_available_date"])) > as_of:
                raise ValueError
            if _date_text(str(row["label_end_date"])) <= row_capture_day:
                raise ValueError
            liquidity = row.get("observed_liquidity_cost_bp")
            after_label = row.get("after_cost_profit_label")
            liquidity_source = str(row.get("observed_liquidity_cost_source") or "").strip()
            if candidate_scenario.is_estimated:
                if row.get("cost_scenario_hash") != candidate_scenario.scenario_hash:
                    raise ValueError
                # Re-run the versioned fee/tax policy from typed, outcome-bound
                # prices and sizing.  A receipt body hash only proves that a
                # producer wrote a self-consistent document; it does not make
                # producer-supplied costs authoritative.
                verify_estimated_cost_observation(
                    candidate_scenario,
                    row,
                    expected_market_replay_date=row_capture_day,
                )
                if row.get("buy_price_twd") is not None and row.get("sell_price_twd") is not None:
                    buy_price = Decimal(str(row["buy_price_twd"]))
                    sell_price = Decimal(str(row["sell_price_twd"]))
                    expected_stock_return = int(
                        ((sell_price / buy_price - Decimal("1")) * Decimal("10000")).quantize(
                            Decimal("1"), rounding=ROUND_HALF_EVEN
                        )
                    )
                    if int(row["stock_return_bp"]) != expected_stock_return:
                        raise ValueError
                if liquidity is not None and int(liquidity) < 0:
                    raise ValueError
            elif liquidity is None:
                if after_label is not None:
                    raise ValueError
            else:
                if int(liquidity) < 0:
                    raise ValueError
                # An untraceable cost cannot be used to manufacture an
                # after-cost label.  Price-only promotion remains possible;
                # after-cost metrics stay explicitly missing.
                if liquidity_source:
                    if _required_int(after_label, "after_cost_profit_label") != int(
                        stock_return > int(receipt_payload["fixed_round_trip_cost_bp"]) + int(liquidity)
                    ):
                        raise ValueError
                elif after_label is not None:
                    raise ValueError
                    raise ValueError
        except (KeyError, TypeError, ValueError):
            result["error"] = "natural_evidence_comparison_label_invalid"
            return result
        candidate_probabilities.append(candidate_probability)
        champion_probabilities.append(champion_probability)
        labels.append(candidate_label)
    fingerprint_rows = [
        {
            "capture_row_id": row["capture_row_id"],
            "label_end_date": row["label_end_date"],
            "label_available_date": row["label_available_date"],
            "stock_return_bp": row["stock_return_bp"],
            "observed_liquidity_cost_bp": row.get("observed_liquidity_cost_bp"),
            "observed_liquidity_cost_source": row.get("observed_liquidity_cost_source"),
        }
        for row in comparisons
    ]
    if candidate_scenario.is_estimated:
        fingerprint_rows = [
            {
                **row,
                "observed_liquidity_cost_bp": None,
                "observed_liquidity_cost_source": None,
                **{
                    key: comparison.get(key)
                    for key in (
                        "cost_scenario_hash", "policy_estimate_date", "market_replay_date",
                        "buy_price_twd", "sell_price_twd",
                        "estimated_buy_cost_twd", "estimated_sell_cost_twd",
                        "estimated_round_trip_cost_twd", "estimated_round_trip_cost_bp",
                        "gross_buy_amount_twd", "gross_sell_amount_twd", "net_profit_twd",
                        "cost_estimate_status",
                    )
                },
            }
            for row, comparison in zip(fingerprint_rows, comparisons)
        ]
    expected_sample_fingerprint = _hash_payload(
        {"capture_id": receipt_payload["capture_id"], "rows": fingerprint_rows}
    )
    expected_candidate_prediction_hash = _hash_payload(
        {"row_ids": row_ids, "probabilities_bp": candidate_probabilities}
    )
    expected_champion_prediction_hash = _hash_payload(
        {"row_ids": row_ids, "probabilities_bp": champion_probabilities}
    )
    if receipt_payload["comparison_sample_fingerprint"] != expected_sample_fingerprint:
        result["error"] = "natural_evidence_sample_fingerprint_mismatch"
        return result
    if receipt_payload["candidate_prediction_hash"] != expected_candidate_prediction_hash:
        result["error"] = "natural_evidence_candidate_prediction_hash_mismatch"
        return result
    if receipt_payload["champion_prediction_hash"] != expected_champion_prediction_hash:
        result["error"] = "natural_evidence_champion_prediction_hash_mismatch"
        return result
    candidate_brier = _brier_bp(candidate_probabilities, labels)
    champion_brier = _brier_bp(champion_probabilities, labels)
    candidate_gap = _calibration_gap_bp(candidate_probabilities, labels)
    if (
        int(receipt_payload["observed_candidate_brier_bp"]) != candidate_brier
        or int(receipt_payload["observed_champion_brier_bp"]) != champion_brier
        or int(receipt_payload["observed_brier_improvement_bp"]) != champion_brier - candidate_brier
        or int(receipt_payload["observed_calibration_gap_bp"]) != candidate_gap
    ):
        result["error"] = "natural_evidence_metrics_recalculation_mismatch"
        return result
    after_rows = tuple(
        row
        for row in comparisons
        if row.get("after_cost_profit_label") is not None
        and row.get("candidate_after_cost_probability_bp") is not None
        and row.get("champion_after_cost_probability_bp") is not None
    )
    if any(
        row.get(field_name) is not None
        and not 0 <= int(row[field_name]) <= 10_000
        for row in comparisons
        for field_name in ("candidate_after_cost_probability_bp", "champion_after_cost_probability_bp")
    ):
        result["error"] = "natural_evidence_after_cost_probability_invalid"
        return result
    expected_after_count = len(after_rows)
    if int(receipt_payload["after_cost_matured_sample_count"]) != expected_after_count:
        result["error"] = "natural_evidence_after_cost_count_mismatch"
        return result
    if after_rows:
        after_candidate = [int(row["candidate_after_cost_probability_bp"]) for row in after_rows]
        after_champion = [int(row["champion_after_cost_probability_bp"]) for row in after_rows]
        after_labels = [int(row["after_cost_profit_label"]) for row in after_rows]
        expected_after_candidate_brier = _brier_bp(after_candidate, after_labels)
        expected_after_champion_brier = _brier_bp(after_champion, after_labels)
        expected_after_gap = _calibration_gap_bp(after_candidate, after_labels)
        if (
            int(receipt_payload["observed_candidate_after_cost_brier_bp"]) != expected_after_candidate_brier
            or int(receipt_payload["observed_champion_after_cost_brier_bp"]) != expected_after_champion_brier
            or int(receipt_payload["observed_after_cost_brier_improvement_bp"]) != expected_after_champion_brier - expected_after_candidate_brier
            or int(receipt_payload["observed_after_cost_calibration_gap_bp"]) != expected_after_gap
            or receipt_payload["after_cost_candidate_prediction_hash"]
            != _hash_payload({"row_ids": [row["capture_row_id"] for row in after_rows], "probabilities_bp": after_candidate})
            or receipt_payload["after_cost_champion_prediction_hash"]
            != _hash_payload({"row_ids": [row["capture_row_id"] for row in after_rows], "probabilities_bp": after_champion})
        ):
            result["error"] = "natural_evidence_after_cost_metrics_recalculation_mismatch"
            return result
    elif any(
        receipt_payload.get(field_name) is not None
        for field_name in (
            "observed_champion_after_cost_brier_bp",
            "observed_candidate_after_cost_brier_bp",
            "observed_after_cost_brier_improvement_bp",
            "observed_after_cost_calibration_gap_bp",
            "after_cost_candidate_prediction_hash",
            "after_cost_champion_prediction_hash",
        )
    ):
        result["error"] = "natural_evidence_after_cost_metrics_without_rows"
        return result
    historical_eval = _mapping(candidate_metadata.get("evaluation"))
    if receipt_payload["comparison_sample_fingerprint"] == historical_eval.get("evaluation_sample_fingerprint"):
        result["error"] = "natural_evidence_reuses_historical_evaluation_sample"
        return result
    result.update(
        matured_sample_count=len(comparisons),
        matured_unique_decision_date_count=len(decision_dates),
        receipt_hash=receipt_hash,
        observed_champion_brier_bp=champion_brier,
        observed_candidate_brier_bp=candidate_brier,
        observed_brier_improvement_bp=champion_brier - candidate_brier,
        observed_calibration_gap_bp=candidate_gap,
    )
    return result


def _candidate_identity_from_metadata(candidate_root: str | Path | None, metadata: Mapping[str, Any]) -> dict[str, Any]:
    identity = {
        "candidate_id": metadata.get("candidate_id") or metadata.get("model_id"),
        "candidate_root": str(_resolve_io_path(Path(candidate_root))) if candidate_root else None,
        "candidate_manifest_hash": metadata.get("manifest_hash"),
        "candidate_artifact_hash": metadata.get("artifact_hash"),
        "candidate_freeze_hash": metadata.get("candidate_freeze_hash"),
        "dataset_hash": metadata.get("dataset_hash"),
    }
    try:
        scenario = cost_scenario_from_metadata(
            metadata,
            fixed_round_trip_cost_bp=_optional_int(metadata.get("fixed_round_trip_cost_bp")),
        )
    except (TypeError, ValueError, RecommendationCostScenarioError):
        scenario = None
    if scenario is not None and scenario.is_estimated:
        identity.update(_scenario_identity_fields(scenario, metadata))
    return identity


def _probability_lineage_null_node(maximum_probability_change_bp: int) -> dict[str, Any]:
    return {
        "kind": "null_benchmark",
        "baseline_id": NULL_BENCHMARK_BASELINE_ID,
        "baseline_kind": "null_benchmark",
        "model_id": None,
        "candidate_id": None,
        "transform_id": PROBABILITY_TRANSFORM_ID,
        "maximum_probability_change_bp": maximum_probability_change_bp,
        "effective_prediction": "identity_from_explicit_baseline",
    }


def _probability_lineage_model_node(
    identity: Mapping[str, Any],
    *,
    baseline_id: str,
    baseline_kind: str,
    maximum_probability_change_bp: int,
) -> dict[str, Any]:
    candidate_id = identity.get("candidate_id") or identity.get("model_id")
    node = {
        "kind": "active_model",
        "baseline_id": baseline_id,
        "baseline_kind": baseline_kind,
        "model_id": candidate_id,
        "candidate_id": candidate_id,
        "candidate_root": identity.get("candidate_root"),
        "candidate_manifest_hash": identity.get("candidate_manifest_hash"),
        "candidate_artifact_hash": identity.get("candidate_artifact_hash"),
        "candidate_freeze_hash": identity.get("candidate_freeze_hash"),
        "dataset_hash": identity.get("dataset_hash"),
        "transform_id": PROBABILITY_TRANSFORM_ID,
        "maximum_probability_change_bp": maximum_probability_change_bp,
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


def _pointer_probability_lineage(pointer: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not pointer or pointer.get("status") != "active":
        return [_probability_lineage_null_node(1_000)]
    raw = pointer.get("probability_lineage")
    if isinstance(raw, list) and raw and all(isinstance(item, Mapping) for item in raw):
        return [dict(item) for item in raw]
    # Compatibility for pointers produced before the effective-lineage
    # contract was introduced.  New adoptions always persist the full chain.
    cap = _optional_int(pointer.get("maximum_probability_change_bp")) or 1_000
    lineage = [_probability_lineage_null_node(cap)]
    previous = _pointer_previous_identity_for_lineage(pointer)
    if previous is not None:
        lineage.append(
            _probability_lineage_model_node(
                previous,
                baseline_id=NULL_BENCHMARK_BASELINE_ID,
                baseline_kind="null_benchmark",
                maximum_probability_change_bp=cap,
            )
        )
    current = _pointer_identity(pointer)
    if current is not None:
        lineage.append(
            _probability_lineage_model_node(
                current,
                baseline_id=(
                    str(lineage[-1].get("candidate_id") or "")
                    if lineage[-1].get("kind") == "active_model"
                    else NULL_BENCHMARK_BASELINE_ID
                ),
                baseline_kind=("active_model" if lineage[-1].get("kind") == "active_model" else "null_benchmark"),
                maximum_probability_change_bp=cap,
            )
        )
    return lineage


def _pointer_previous_probability_lineage(pointer: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not pointer or pointer.get("status") != "active":
        return [_probability_lineage_null_node(1_000)]
    raw = pointer.get("previous_probability_lineage")
    if isinstance(raw, list) and raw and all(isinstance(item, Mapping) for item in raw):
        return [dict(item) for item in raw]
    lineage = _pointer_probability_lineage(pointer)
    if len(lineage) > 1:
        return lineage[:-1]
    return [_probability_lineage_null_node(_optional_int(pointer.get("maximum_probability_change_bp")) or 1_000)]


def _pointer_previous_identity_for_lineage(pointer: Mapping[str, Any]) -> dict[str, Any] | None:
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


def _valid_probability_lineage(pointer: Mapping[str, Any], maximum_probability_change_bp: int) -> bool:
    raw = pointer.get("probability_lineage")
    if not isinstance(raw, list) or not raw or not all(isinstance(item, Mapping) for item in raw):
        # Older pointers are accepted and are upgraded on the next adoption.
        return raw is None
    first = raw[0]
    if (
        first.get("kind") != "null_benchmark"
        or first.get("baseline_id") != NULL_BENCHMARK_BASELINE_ID
        or first.get("transform_id") != PROBABILITY_TRANSFORM_ID
    ):
        return False
    seen: set[str] = set()
    for index, item in enumerate(raw):
        if item.get("transform_id") != PROBABILITY_TRANSFORM_ID:
            return False
        try:
            item_cap = int(item.get("maximum_probability_change_bp", -1))
        except (TypeError, ValueError):
            return False
        if item_cap != maximum_probability_change_bp:
            return False
        if index == 0:
            continue
        candidate_id = str(item.get("candidate_id") or "")
        if not candidate_id or candidate_id in seen:
            return False
        seen.add(candidate_id)
        if item.get("kind") != "active_model" or item.get("model_id") != candidate_id:
            return False
        if not all(item.get(key) for key in (
            "candidate_root", "candidate_manifest_hash", "candidate_artifact_hash", "candidate_freeze_hash",
        )):
            return False
        parent = raw[index - 1]
        expected_baseline = str(parent.get("candidate_id") or "") if parent.get("kind") == "active_model" else NULL_BENCHMARK_BASELINE_ID
        expected_kind = "active_model" if parent.get("kind") == "active_model" else "null_benchmark"
        if item.get("baseline_id") != expected_baseline or item.get("baseline_kind") != expected_kind:
            return False
    last = raw[-1]
    if last.get("kind") != "active_model" or last.get("candidate_id") != pointer.get("candidate_id"):
        return False
    previous = pointer.get("previous_probability_lineage")
    if previous is not None and (not isinstance(previous, list) or previous != raw[:-1]):
        return False
    return True


def _candidate_training_after_decision(metadata: Mapping[str, Any], decision_date: str) -> bool:
    decision = date.fromisoformat(decision_date[:10])
    for field_name in ("training_as_of", "training_cutoff"):
        value = metadata.get(field_name)
        if value in (None, ""):
            continue
        try:
            if date.fromisoformat(str(value)[:10]) > decision:
                return True
        except (TypeError, ValueError):
            return True

    semantics = metadata.get("training_semantics")
    if semantics not in (None, "decision_time"):
        return True
    if "decision_time_eligible" in metadata and metadata.get("decision_time_eligible") is not True:
        return True
    return False


def _pointer_identity(pointer: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not pointer or pointer.get("status") != "active":
        return None
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


def _cooldown_active(pointer: Mapping[str, Any] | None, decision_date: str, cooldown_days: int) -> bool:
    if not pointer or pointer.get("status") != "active" or cooldown_days <= 0:
        return False
    try:
        return (date.fromisoformat(decision_date) - date.fromisoformat(str(pointer.get("effective_date"))[:10])).days < cooldown_days
    except ValueError:
        return True


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _scenario_identity_fields(
    scenario: RecommendationCostScenario,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "label_registry_hash": metadata.get("label_registry_hash") or _label_registry_hash(scenario),
        "cost_contract_hash": metadata.get("cost_contract_hash") or _cost_contract_hash(scenario),
        "fixed_round_trip_cost_bp": scenario.fixed_round_trip_cost_bp,
        "cost_scenario_id": scenario.scenario_id,
        "cost_scenario_version": scenario.scenario_version,
        "cost_scenario_hash": scenario.scenario_hash,
        "cost_basis": scenario.cost_basis,
        "cost_policy_id": scenario.policy_id,
        "cost_policy_version": scenario.policy_version,
        "policy_estimate_date": scenario.policy_estimate_date,
        "research_order_amount_twd": (
            str(scenario.research_order_amount_twd)
            if scenario.research_order_amount_twd is not None
            else None
        ),
        "research_order_quantity_shares": scenario.research_order_quantity_shares,
        "lot_type": scenario.lot_type,
        "instrument_type": scenario.instrument_type,
        "cost_scenario": scenario.metadata(),
    }


def _label_registry_hash(scenario: RecommendationCostScenario) -> str:
    from ml_module.recommendation_calibration_training import recommendation_label_registry_hash

    return recommendation_label_registry_hash(
        cost_scenario=scenario if scenario.is_estimated else None
    )


def _cost_contract_hash(scenario: RecommendationCostScenario) -> str:
    return recommendation_cost_contract_hash(
        scenario.fixed_round_trip_cost_bp,
        cost_scenario=scenario if scenario.is_estimated else None,
    )


def _scenario_from_metadata(metadata: Mapping[str, Any]) -> RecommendationCostScenario:
    return cost_scenario_from_metadata(
        metadata,
        fixed_round_trip_cost_bp=_optional_int(metadata.get("fixed_round_trip_cost_bp")),
    )


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _candidate_gate_blockers(metadata: Mapping[str, Any]) -> tuple[str, ...]:
    """Apply lane-aware gates without converting replay into forward proof.

    A ready prospective price-up source contract supersedes only the two
    historical-publication blockers that describe missing historical PIT
    authority.  Observed-cost and broker-actual blockers are never ignored by
    this helper; they remain separate promotion lanes.
    """

    ignored = {
        "historical_replay_is_not_natural_forward_evidence",
        "training_artifact_is_shadow_only",
        "natural_forward_evidence_must_be_supplied_to_authority",
    }
    if (
        metadata.get("prospective_price_up_promotion_ready") is True
        and metadata.get("promotion_target", "price_up_calibration") == "price_up_calibration"
    ):
        ignored.update(
            {
                "technical_publication_time_unverified",
                "corporate_action_source_or_adjustment_unverified",
            }
        )
    return tuple(
        str(item)
        for item in metadata.get("candidate_blockers", ())
        if str(item).strip() and str(item) not in ignored
    )


def _required_int(value: Any, field_name: str) -> int:
    if value is None or isinstance(value, bool):
        raise ValueError(f"{field_name} is required")
    return int(value)


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clamp_to_baseline(value: int | None, baseline: int | None, cap: int) -> int | None:
    if value is None or baseline is None:
        return None
    return max(0, min(10_000, max(int(baseline) - cap, min(int(baseline) + cap, int(value)))))


def _receipt_hash(value: Any) -> str | None:
    if isinstance(value, Mapping):
        item = value.get("receipt_hash")
    else:
        item = getattr(value, "receipt_hash", None)
    return str(item) if item else None


def _date_text(value: str) -> str:
    return date.fromisoformat(str(value)[:10]).isoformat()


def _datetime_text(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _strict_evaluation_at(value: str) -> datetime:
    """嚴格解析綁定交易日 session 的 evaluation clock，不默認轉換 naive UTC。"""

    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("session-bound evaluation_at must contain a timezone")
    return parsed.astimezone(timezone.utc)


def _hash_payload(payload: Mapping[str, Any] | Any) -> str:
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"sha256:{digest}"


def _pointer_content_hash(payload: Mapping[str, Any] | None) -> str | None:
    return _hash_payload(payload) if payload is not None else None


def _brier_bp(probabilities: list[int], labels: list[int]) -> int:
    if not probabilities or len(probabilities) != len(labels):
        raise ValueError("natural evidence probability/label length mismatch")
    return sum((probability - label * 10_000) ** 2 for probability, label in zip(probabilities, labels)) // (
        len(labels) * 10_000
    )


def _calibration_gap_bp(probabilities: list[int], labels: list[int]) -> int:
    if not probabilities or len(probabilities) != len(labels):
        raise ValueError("natural evidence probability/label length mismatch")
    return abs(sum(probabilities) // len(probabilities) - sum(labels) * 10_000 // len(labels))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with _io_path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _safe_json_field(path: Path, field: str) -> Any:
    try:
        payload = json.loads(_io_path(path).read_text(encoding="utf-8"))
        return payload.get(field) if isinstance(payload, Mapping) else None
    except (OSError, json.JSONDecodeError):
        return None


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    _io_path(path.parent).mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    _io_path(temporary).write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    _io_path(temporary).replace(_io_path(path))


def _write_json_once(path: Path, payload: Mapping[str, Any]) -> None:
    _io_path(path.parent).mkdir(parents=True, exist_ok=True)
    if _io_path(path).exists():
        existing = json.loads(_io_path(path).read_text(encoding="utf-8"))
        if existing != payload:
            raise RuntimeError("immutable recommendation decision receipt conflict")
        return
    _io_path(path).write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _decision_from_dict(payload: Mapping[str, Any]) -> RecommendationPromotionDecision:
    return RecommendationPromotionDecision(
        decision_id=str(payload["decision_id"]),
        decision_date=str(payload["decision_date"]),
        decision=str(payload["decision"]),
        reason=str(payload["reason"]),
        candidate_id=payload.get("candidate_id"),
        previous_candidate_id=payload.get("previous_candidate_id"),
        pointer_version=int(payload.get("pointer_version", 0)),
        pointer_status=str(payload.get("pointer_status", "none")),
        receipt_path=str(payload.get("receipt_path", "")),
        pointer_path=str(payload.get("pointer_path", "")),
        natural_evidence_receipt_hash=payload.get("natural_evidence_receipt_hash"),
        natural_matured_sample_count=int(payload.get("natural_matured_sample_count", 0)),
        natural_matured_decision_date_count=int(payload.get("natural_matured_decision_date_count", 0)),
        old_brier_bp=_optional_int(payload.get("old_brier_bp")),
        new_brier_bp=_optional_int(payload.get("new_brier_bp")),
        brier_improvement_bp=_optional_int(payload.get("brier_improvement_bp")),
        calibration_gap_bp=_optional_int(payload.get("calibration_gap_bp")),
        maximum_probability_change_bp=int(payload.get("maximum_probability_change_bp", 1000)),
        candidate_freeze_hash=payload.get("candidate_freeze_hash"),
    )
