"""V6 個人化 calibration 的固定 shrinkage fit/evaluate contract。

這裡只做可重現的統計投影，不改變既有 recommendation score、排序或正式
交易路徑。輸入 row 必須在同一個 horizon/cost contract 下，fit 與 evaluate
的 row identity 也必須完全分離。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Mapping, Sequence

from app_module.personalization_contract import (
    PersonalizationEvaluationRow,
    canonical_payload_hash,
    parse_aware_datetime,
)


PERSONALIZATION_CALIBRATION_SCHEMA_VERSION = "personalization-calibration.v1"
FIXED_SHRINKAGE_POLICY_VERSION = "fixed-beta-shrinkage.v1"
DEFAULT_SHRINKAGE_STRENGTH = 10


class PersonalizationCalibrationError(ValueError):
    """Calibration contract 或 fit/evaluate 分割不合法。"""


def _date(value: object, field_name: str) -> str:
    text = str(value or "").strip()[:10]
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise PersonalizationCalibrationError(f"{field_name} must be ISO date") from exc


def _hash_rows(rows: Sequence[PersonalizationEvaluationRow]) -> str:
    return canonical_payload_hash(
        {"rows": [row.to_dict() for row in sorted(rows, key=lambda item: item.effective_row_id)]}
    )


def _round_bp(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _probability(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10_000:
        raise PersonalizationCalibrationError("probability must be integer bp within 0..10000")
    return value


def _coerce_row(value: PersonalizationEvaluationRow | Mapping[str, Any]) -> PersonalizationEvaluationRow:
    if isinstance(value, PersonalizationEvaluationRow):
        return value
    if not isinstance(value, Mapping):
        raise PersonalizationCalibrationError("evaluation row must be an object")
    return PersonalizationEvaluationRow(
        prediction_id=str(value.get("prediction_id") or ""),
        scope_id=str(value.get("scope_id") or ""),
        symbol=str(value.get("symbol") or value.get("stock_code") or ""),
        decision_date=str(value.get("decision_date") or ""),
        label_available_date=str(value.get("label_available_date") or value.get("decision_date") or ""),
        horizon_days=int(value.get("horizon_days") or 0),
        cost_scenario_hash=(
            str(value.get("cost_scenario_hash"))
            if value.get("cost_scenario_hash") is not None
            else None
        ),
        population_probability_bp=_probability(value.get("population_probability_bp")),
        label=(int(value["label"]) if value.get("label") is not None else None),
        outcome_tier=str(value.get("outcome_tier") or "natural_forward"),
        action_state=str(value.get("action_state") or "not_recorded"),
        decision_at=(str(value.get("decision_at")) if value.get("decision_at") else None),
        available_at=(str(value.get("available_at")) if value.get("available_at") else None),
        receipt_created_at=(
            str(value.get("receipt_created_at")) if value.get("receipt_created_at") else None
        ),
        decision_day_block=(
            str(value.get("decision_day_block")) if value.get("decision_day_block") else None
        ),
        row_id=str(value.get("row_id") or value.get("prediction_id") or ""),
        personal_observation_count=int(value.get("personal_observation_count") or 0),
        personal_positive_count=int(value.get("personal_positive_count") or 0),
    )


def _validate_temporal_row(row: PersonalizationEvaluationRow) -> str | None:
    """Return a blocking status; no date-only PIT inference is allowed."""

    if row.decision_at is None or row.available_at is None:
        return "temporal_precision_unproven"
    decision = parse_aware_datetime(row.decision_at, "decision_at")
    available = parse_aware_datetime(row.available_at, "available_at")
    if available > decision:
        return "available_after_decision"
    if row.receipt_created_at is not None:
        receipt = parse_aware_datetime(row.receipt_created_at, "receipt_created_at")
        if receipt < decision:
            return "receipt_before_decision"
    return None


@dataclass(frozen=True)
class PersonalizationCalibrationFitArtifact:
    """Frozen calibration artifact; it never owns evaluation rows."""

    artifact_id: str
    fit_as_of: str
    fit_row_fingerprint: str
    fit_policy_hash: str
    overlay_hash: str
    horizon_days: int
    cost_scenario_hash: str | None
    fit_row_ids: tuple[str, ...]
    fit_row_count: int
    fit_positive_count: int
    population_prior_bp: int
    shrinkage_strength: int
    created_at: str
    schema_version: str = PERSONALIZATION_CALIBRATION_SCHEMA_VERSION
    policy_version: str = FIXED_SHRINKAGE_POLICY_VERSION

    def __post_init__(self) -> None:
        if not self.artifact_id.strip():
            raise PersonalizationCalibrationError("artifact_id is required")
        _date(self.fit_as_of, "fit_as_of")
        for name in ("horizon_days", "fit_row_count", "fit_positive_count", "shrinkage_strength"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise PersonalizationCalibrationError(f"{name} must be a positive integer")
        if self.fit_positive_count > self.fit_row_count:
            raise PersonalizationCalibrationError("fit_positive_count exceeds fit_row_count")
        if _probability(self.population_prior_bp) is None:
            raise PersonalizationCalibrationError("population_prior_bp is required")
        if len(self.fit_row_ids) != self.fit_row_count:
            raise PersonalizationCalibrationError("fit_row_ids/count mismatch")
        if len(set(self.fit_row_ids)) != len(self.fit_row_ids):
            raise PersonalizationCalibrationError("fit row identity is duplicated")
        try:
            parse_aware_datetime(self.created_at, "created_at")
        except ValueError as exc:
            raise PersonalizationCalibrationError(str(exc)) from exc
        if self.schema_version != PERSONALIZATION_CALIBRATION_SCHEMA_VERSION:
            raise PersonalizationCalibrationError("unsupported calibration artifact schema")
        if self.policy_version != FIXED_SHRINKAGE_POLICY_VERSION:
            raise PersonalizationCalibrationError("unsupported shrinkage policy")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_version": self.policy_version,
            "artifact_id": self.artifact_id,
            "fit_as_of": self.fit_as_of,
            "fit_row_fingerprint": self.fit_row_fingerprint,
            "fit_policy_hash": self.fit_policy_hash,
            "overlay_hash": self.overlay_hash,
            "horizon_days": self.horizon_days,
            "cost_scenario_hash": self.cost_scenario_hash,
            "fit_row_ids": list(self.fit_row_ids),
            "fit_row_count": self.fit_row_count,
            "fit_positive_count": self.fit_positive_count,
            "population_prior_bp": self.population_prior_bp,
            "shrinkage_strength": self.shrinkage_strength,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class PersonalizationCalibrationRowResult:
    prediction_id: str
    row_id: str
    population_probability_bp: int | None
    calibrated_probability_bp: int | None
    personal_observation_count: int
    personal_positive_count: int
    status: str
    label: int | None
    label_matured: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "prediction_id": self.prediction_id,
            "row_id": self.row_id,
            "population_probability_bp": self.population_probability_bp,
            "calibrated_probability_bp": self.calibrated_probability_bp,
            "personal_observation_count": self.personal_observation_count,
            "personal_positive_count": self.personal_positive_count,
            "status": self.status,
            "label": self.label,
            "label_matured": self.label_matured,
        }


@dataclass(frozen=True)
class PersonalizationCalibrationEvaluation:
    artifact_id: str
    evaluated_as_of: str
    evaluation_row_fingerprint: str
    fit_row_fingerprint: str
    rows: tuple[PersonalizationCalibrationRowResult, ...]
    status: str
    population_probability_missing_count: int
    temporal_blocked_count: int
    adoption_confidence_status: str = "adoption_not_evaluable"
    adoption_confidence_reason: str = "predeclared dependency-aware method is required"

    @property
    def sample_size(self) -> int:
        return sum(1 for row in self.rows if row.label_matured and row.label is not None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PERSONALIZATION_CALIBRATION_SCHEMA_VERSION,
            "artifact_id": self.artifact_id,
            "evaluated_as_of": self.evaluated_as_of,
            "evaluation_row_fingerprint": self.evaluation_row_fingerprint,
            "fit_row_fingerprint": self.fit_row_fingerprint,
            "rows": [row.to_dict() for row in self.rows],
            "status": self.status,
            "sample_size": self.sample_size,
            "population_probability_missing_count": self.population_probability_missing_count,
            "temporal_blocked_count": self.temporal_blocked_count,
            "adoption_confidence_status": self.adoption_confidence_status,
            "adoption_confidence_reason": self.adoption_confidence_reason,
        }


class PersonalizationCalibrationEvaluator:
    """固定 policy 的 fit/evaluate 服務。"""

    def fit(
        self,
        fit_rows: Sequence[PersonalizationEvaluationRow | Mapping[str, Any]],
        *,
        fit_as_of: str,
        horizon_days: int,
        cost_scenario_hash: str | None,
        shrinkage_strength: int = DEFAULT_SHRINKAGE_STRENGTH,
        artifact_id: str | None = None,
        created_at: str | None = None,
    ) -> PersonalizationCalibrationFitArtifact:
        resolved_rows = tuple(_coerce_row(row) for row in fit_rows)
        if not resolved_rows:
            raise PersonalizationCalibrationError("fit rows cannot be empty")
        fit_day = _date(fit_as_of, "fit_as_of")
        if isinstance(horizon_days, bool) or horizon_days <= 0:
            raise PersonalizationCalibrationError("horizon_days must be positive")
        if isinstance(shrinkage_strength, bool) or shrinkage_strength <= 0:
            raise PersonalizationCalibrationError("shrinkage_strength must be positive")
        if any(row.horizon_days != horizon_days for row in resolved_rows):
            raise PersonalizationCalibrationError("fit horizon contract is mixed")
        if any(row.cost_scenario_hash != cost_scenario_hash for row in resolved_rows):
            raise PersonalizationCalibrationError("fit cost scenario contract is mixed")
        seen: set[str] = set()
        population_values: list[int] = []
        positive_count = 0
        for row in resolved_rows:
            if row.effective_row_id in seen or row.prediction_id in seen:
                raise PersonalizationCalibrationError("fit row identity is duplicated")
            seen.add(row.effective_row_id)
            seen.add(row.prediction_id)
            if _date(row.label_available_date, "label_available_date") > fit_day:
                raise PersonalizationCalibrationError("fit row label is not available at fit_as_of")
            temporal_status = _validate_temporal_row(row)
            if temporal_status is not None:
                raise PersonalizationCalibrationError(f"fit row temporal contract blocked: {temporal_status}")
            if row.label is None:
                raise PersonalizationCalibrationError("fit row label is required")
            if row.population_probability_bp is None:
                raise PersonalizationCalibrationError("fit row population probability is required")
            population_values.append(row.population_probability_bp)
            positive_count += row.label
        population_prior = _round_bp(
            sum(Decimal(value) for value in population_values) / Decimal(len(population_values))
        )
        policy = {
            "policy_version": FIXED_SHRINKAGE_POLICY_VERSION,
            "shrinkage_strength": shrinkage_strength,
            "probability_units": "basis_points",
            "population_probability_required": True,
            "n_zero_rule": "exact_population_probability",
            "rank_fallback": False,
        }
        policy_hash = canonical_payload_hash(policy)
        overlay_hash = canonical_payload_hash(
            {
                "policy_hash": policy_hash,
                "population_prior_bp": population_prior,
                "fit_positive_count": positive_count,
                "fit_row_count": len(resolved_rows),
            }
        )
        resolved_created_at = created_at or datetime.now(timezone.utc).isoformat(timespec="microseconds")
        return PersonalizationCalibrationFitArtifact(
            artifact_id=str(artifact_id or f"personalization_fit_{fit_day.replace('-', '')}_{policy_hash.split(':', 1)[1][:16]}"),
            fit_as_of=fit_day,
            fit_row_fingerprint=_hash_rows(resolved_rows),
            fit_policy_hash=policy_hash,
            overlay_hash=overlay_hash,
            horizon_days=horizon_days,
            cost_scenario_hash=cost_scenario_hash,
            fit_row_ids=tuple(sorted(row.effective_row_id for row in resolved_rows)),
            fit_row_count=len(resolved_rows),
            fit_positive_count=positive_count,
            population_prior_bp=population_prior,
            shrinkage_strength=shrinkage_strength,
            created_at=resolved_created_at,
        )

    def evaluate(
        self,
        artifact: PersonalizationCalibrationFitArtifact,
        evaluation_rows: Sequence[PersonalizationEvaluationRow | Mapping[str, Any]],
        *,
        evaluated_as_of: str,
        predeclared_adoption_method: str | None = None,
    ) -> PersonalizationCalibrationEvaluation:
        if not isinstance(artifact, PersonalizationCalibrationFitArtifact):
            raise PersonalizationCalibrationError("artifact type is invalid")
        resolved_rows = tuple(_coerce_row(row) for row in evaluation_rows)
        if not resolved_rows:
            raise PersonalizationCalibrationError("evaluation rows cannot be empty")
        evaluated_day = _date(evaluated_as_of, "evaluated_as_of")
        fit_ids = set(artifact.fit_row_ids)
        eval_ids = {row.effective_row_id for row in resolved_rows}
        eval_prediction_ids = {row.prediction_id for row in resolved_rows}
        if fit_ids.intersection(eval_ids) or fit_ids.intersection(eval_prediction_ids):
            raise PersonalizationCalibrationError("fit/evaluation row overlap detected")
        if any(row.horizon_days != artifact.horizon_days for row in resolved_rows):
            raise PersonalizationCalibrationError("evaluation horizon does not match fit artifact")
        if any(row.cost_scenario_hash != artifact.cost_scenario_hash for row in resolved_rows):
            raise PersonalizationCalibrationError("evaluation cost scenario does not match fit artifact")

        results: list[PersonalizationCalibrationRowResult] = []
        missing_population = 0
        temporal_blocked = 0
        for row in resolved_rows:
            temporal_status = _validate_temporal_row(row)
            label_matured = _date(row.label_available_date, "label_available_date") <= evaluated_day
            status = temporal_status or "available"
            calibrated: int | None = None
            if temporal_status is not None:
                temporal_blocked += 1
            elif row.population_probability_bp is None:
                missing_population += 1
                status = "population_probability_unavailable"
            else:
                n = row.personal_observation_count
                if n == 0:
                    # Exact population probability is the explicit n=0 rule.
                    calibrated = row.population_probability_bp
                else:
                    numerator = Decimal(row.personal_positive_count * 10_000) + (
                        Decimal(artifact.shrinkage_strength)
                        * Decimal(row.population_probability_bp)
                    )
                    denominator = Decimal(n + artifact.shrinkage_strength)
                    calibrated = max(0, min(10_000, _round_bp(numerator / denominator)))
                    status = "shrunken_personal_overlay"
                if not label_matured:
                    status = "label_pending" if status == "available" else status
            results.append(
                PersonalizationCalibrationRowResult(
                    prediction_id=row.prediction_id,
                    row_id=row.effective_row_id,
                    population_probability_bp=row.population_probability_bp,
                    calibrated_probability_bp=calibrated,
                    personal_observation_count=row.personal_observation_count,
                    personal_positive_count=row.personal_positive_count,
                    status=status,
                    label=row.label if label_matured else None,
                    label_matured=label_matured,
                )
            )
        if temporal_blocked:
            overall_status = "temporal_contract_blocked"
        elif missing_population == len(results):
            overall_status = "population_probability_unavailable"
        else:
            overall_status = "evaluated"
        adoption_status = "adoption_evaluable" if predeclared_adoption_method else "adoption_not_evaluable"
        adoption_reason = (
            "predeclared dependency-aware paired/day/block method declared"
            if predeclared_adoption_method
            else "Wilson interval is descriptive only; adoption needs a predeclared dependency-aware method"
        )
        return PersonalizationCalibrationEvaluation(
            artifact_id=artifact.artifact_id,
            evaluated_as_of=evaluated_day,
            evaluation_row_fingerprint=_hash_rows(resolved_rows),
            fit_row_fingerprint=artifact.fit_row_fingerprint,
            rows=tuple(results),
            status=overall_status,
            population_probability_missing_count=missing_population,
            temporal_blocked_count=temporal_blocked,
            adoption_confidence_status=adoption_status,
            adoption_confidence_reason=adoption_reason,
        )


def wilson_interval_bp(successes: int, trials: int) -> tuple[int, int] | None:
    """描述性 Wilson bin CI；不得被解讀為 adoption causal CI。"""

    if isinstance(successes, bool) or isinstance(trials, bool) or trials <= 0:
        return None
    if successes < 0 or successes > trials:
        raise PersonalizationCalibrationError("successes/trials are invalid")
    z = Decimal("1.959963984540054")
    n = Decimal(trials)
    phat = Decimal(successes) / n
    denominator = Decimal(1) + (z * z) / n
    center = (phat + (z * z) / (Decimal(2) * n)) / denominator
    margin = (
        z
        * ((phat * (Decimal(1) - phat) / n + (z * z) / (Decimal(4) * n * n)).sqrt())
        / denominator
    )
    return max(0, _round_bp((center - margin) * Decimal(10_000))), min(
        10_000, _round_bp((center + margin) * Decimal(10_000))
    )


__all__ = [
    "DEFAULT_SHRINKAGE_STRENGTH",
    "FIXED_SHRINKAGE_POLICY_VERSION",
    "PERSONALIZATION_CALIBRATION_SCHEMA_VERSION",
    "PersonalizationCalibrationError",
    "PersonalizationCalibrationEvaluation",
    "PersonalizationCalibrationEvaluator",
    "PersonalizationCalibrationFitArtifact",
    "PersonalizationCalibrationRowResult",
    "wilson_interval_bp",
]
