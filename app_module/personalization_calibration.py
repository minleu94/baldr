"""V6 個人化 calibration 的固定、唯讀 fit/evaluate contract。

這個模組只做 offline/shadow 統計投影，不改變既有 recommendation score、
排序、global active pointer 或正式交易路徑。personal overlay 以 fit cohort
凍結，evaluation 只讀 untouched rows；所有 probability 與 metric 都以整數
bp 或 Decimal 保存。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from app_module.personalization_contract import (
    PERSONALIZATION_COHORT_CONTRACT_SCHEMA_VERSION,
    PERSONALIZATION_OUTCOME_TIERS,
    PERSONALIZATION_PREDICTION_RECEIPT_SCHEMA_VERSION,
    PERSONALIZATION_OUTCOME_STATUSES,
    PersonalizationEvaluationRow,
    canonical_payload_hash,
    parse_aware_datetime,
)


PERSONALIZATION_CALIBRATION_SCHEMA_VERSION = "personalization-calibration.v1"
FIXED_SHRINKAGE_POLICY_VERSION = "fixed-beta-shrinkage.v1"
DEFAULT_SHRINKAGE_STRENGTH = 10
DEFAULT_PROBABILITY_BIN_EDGES_BP = (0, 2_000, 4_000, 6_000, 8_000, 10_001)
_COHORT_REQUIRED_FIELDS = (
    "scope_id",
    "outcome_tier",
    "model_id",
    "dataset_id",
    "dataset_hash",
    "source_id",
    "prediction_receipt_schema_version",
    "prediction_receipt_hash",
    "universe_policy_hash",
    "label_contract_id",
    "return_basis",
)


class PersonalizationCalibrationError(ValueError):
    """Calibration contract 或 fit/evaluate 分割不合法。"""


def _date(value: object, field_name: str) -> str:
    text = str(value or "").strip()[:10]
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise PersonalizationCalibrationError(f"{field_name} must be ISO date") from exc


def _integer(value: object, field_name: str, *, default: int | None = None) -> int:
    if value is None and default is not None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise PersonalizationCalibrationError(f"{field_name} must be an integer")
    return value


def _hash_rows(rows: Sequence[PersonalizationEvaluationRow]) -> str:
    return canonical_payload_hash(
        {
            "rows": [
                row.to_dict()
                for row in sorted(rows, key=lambda item: (item.effective_row_id, item.prediction_id))
            ]
        }
    )


def _freeze(value: Any) -> Any:
    """Recursively freeze artifact values so hash inputs cannot drift in place."""

    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _required_text(value: object, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise PersonalizationCalibrationError(
            f"{field_name} is required for verified cohort"
        )
    return text


def _row_cohort_payload(row: PersonalizationEvaluationRow) -> dict[str, Any]:
    """Return the exact cohort contract carried by one evaluation row."""

    values = {
        "scope_id": row.scope_id,
        "outcome_tier": row.outcome_tier,
        "model_id": row.model_id,
        "dataset_id": row.dataset_id,
        "dataset_hash": row.dataset_hash,
        "source_id": row.source_id,
        "prediction_receipt_schema_version": row.prediction_receipt_schema_version,
        "prediction_receipt_hash": row.prediction_receipt_hash,
        "universe_policy_hash": row.universe_policy_hash,
        "label_contract_id": row.label_contract_id,
        "return_basis": row.return_basis,
        "horizon_days": row.horizon_days,
        "cost_scenario_hash": row.cost_scenario_hash,
    }
    for field_name in _COHORT_REQUIRED_FIELDS:
        values[field_name] = _required_text(values[field_name], field_name)
    if values["prediction_receipt_schema_version"] != PERSONALIZATION_PREDICTION_RECEIPT_SCHEMA_VERSION:
        raise PersonalizationCalibrationError(
            "prediction receipt schema is not verified"
        )
    if not str(values["prediction_receipt_hash"]).startswith("sha256:"):
        raise PersonalizationCalibrationError(
            "prediction_receipt_hash is not verified"
        )
    if row.outcome_tier not in PERSONALIZATION_OUTCOME_TIERS:
        raise PersonalizationCalibrationError("outcome tier is not verified")
    if row.cost_scenario_hash is None or not str(row.cost_scenario_hash).strip():
        raise PersonalizationCalibrationError("cost_scenario_hash is required for verified cohort")
    return values


def _policy_cohort_expectations(
    policy: "PersonalizationCalibrationPolicy",
) -> dict[str, Any]:
    return {
        "scope_id": policy.scope_id,
        "outcome_tier": policy.allowed_outcome_tiers[0],
        "model_id": policy.model_id,
        "dataset_id": policy.dataset_id,
        "dataset_hash": policy.dataset_hash,
        "source_id": policy.source_id,
        "prediction_receipt_schema_version": policy.receipt_schema_version,
        "universe_policy_hash": policy.universe_policy_hash,
        "label_contract_id": policy.label_contract_id,
        "return_basis": policy.return_basis,
        "horizon_days": policy.horizon_days,
        "cost_scenario_hash": policy.cost_scenario_hash,
    }


def _resolve_cohort_contract(
    rows: Sequence[PersonalizationEvaluationRow],
    policy: "PersonalizationCalibrationPolicy",
) -> dict[str, Any]:
    """Resolve one verified cohort; never infer a mixed cohort silently."""

    expectations = _policy_cohort_expectations(policy)
    if not rows:
        for field_name in _COHORT_REQUIRED_FIELDS:
            if field_name == "prediction_receipt_hash":
                continue
            _required_text(expectations.get(field_name), field_name)
        return {
            "schema_version": PERSONALIZATION_COHORT_CONTRACT_SCHEMA_VERSION,
            **expectations,
            "prediction_receipt_hash_policy": "per_prediction_exact_hash",
        }

    payloads = [_row_cohort_payload(row) for row in rows]
    first = payloads[0]
    for index, payload in enumerate(payloads[1:], start=1):
        for field_name in _COHORT_REQUIRED_FIELDS:
            if field_name == "prediction_receipt_hash":
                continue
            if payload[field_name] != first[field_name]:
                raise PersonalizationCalibrationError(
                    f"fit cohort is mixed at {field_name} row {index}"
                )
    for field_name, expected in expectations.items():
        if expected in (None, ""):
            continue
        if field_name == "prediction_receipt_hash":
            continue
        if first[field_name] != expected:
            raise PersonalizationCalibrationError(
                f"cohort contract mismatch at {field_name}"
            )
    return {
        "schema_version": PERSONALIZATION_COHORT_CONTRACT_SCHEMA_VERSION,
        **first,
        "prediction_receipt_hash_policy": "per_prediction_exact_hash",
    }


def _same_row(left: PersonalizationEvaluationRow, right: PersonalizationEvaluationRow) -> bool:
    return left.to_dict() == right.to_dict()


def _deduplicate_rows(
    rows: Sequence[PersonalizationEvaluationRow],
    *,
    phase: str,
) -> tuple[PersonalizationEvaluationRow, ...]:
    """Deduplicate exact retries and reject alias/conflicting identities."""

    seen: dict[tuple[str, str], PersonalizationEvaluationRow] = {}
    output: list[PersonalizationEvaluationRow] = []
    for row in rows:
        keys = (
            ("row_id", row.effective_row_id),
            ("prediction_id", row.prediction_id),
            ("statistical_id", row.effective_statistical_id),
        )
        duplicate_exact = False
        for key in keys:
            previous = seen.get(key)
            if previous is None:
                continue
            if _same_row(previous, row):
                duplicate_exact = True
                continue
            raise PersonalizationCalibrationError(
                f"{phase} duplicate identity conflict at {key[0]}={key[1]}"
            )
        if duplicate_exact:
            continue
        output.append(row)
        for key in keys:
            seen[key] = row
    return tuple(output)


def _overlay_payload(
    *,
    policy_hash: str,
    population_prior_bp: int,
    population_bin_rate_bp: Mapping[str, int],
    personal_bin_observation_count: Mapping[str, int],
    personal_bin_positive_count: Mapping[str, int],
) -> dict[str, Any]:
    return {
        "policy_hash": policy_hash,
        "population_prior_bp": population_prior_bp,
        "population_bin_rate_bp": dict(population_bin_rate_bp),
        "personal_bin_observation_count": dict(personal_bin_observation_count),
        "personal_bin_positive_count": dict(personal_bin_positive_count),
    }


def _fit_identity_fingerprint(
    *,
    fit_scope_id: str,
    fit_row_fingerprint: str,
    fit_row_ids: Sequence[str],
    fit_prediction_ids: Sequence[str],
    fit_statistical_ids: Sequence[str],
    fit_receipt_hashes: Sequence[str],
) -> str:
    return canonical_payload_hash(
        {
            "fit_scope_id": fit_scope_id,
            "fit_row_fingerprint": fit_row_fingerprint,
            "fit_row_ids": list(fit_row_ids),
            "fit_prediction_ids": list(fit_prediction_ids),
            "fit_statistical_ids": list(fit_statistical_ids),
            "fit_receipt_hashes": list(fit_receipt_hashes),
        }
    )


def _label_availability_status(
    row: PersonalizationEvaluationRow,
    *,
    cutoff: datetime | None,
) -> str | None:
    """Check label/outcome availability using an exact clock, not a date guess."""

    if row.outcome_status != "ready":
        return None
    if row.label_available_at is None:
        return "temporal_precision_unproven"
    label_available_at = parse_aware_datetime(
        row.label_available_at,
        "label_available_at",
    )
    if cutoff is None:
        return "temporal_precision_unproven"
    if label_available_at > cutoff:
        return "pending_maturity"
    if row.outcome_recorded_at is None:
        return "temporal_precision_unproven"
    if parse_aware_datetime(row.outcome_recorded_at, "outcome_recorded_at") > cutoff:
        return "pending_maturity"
    return None


def _validate_artifact_integrity(
    artifact: "PersonalizationCalibrationFitArtifact",
) -> None:
    """Re-check derived hashes at the evaluation boundary."""

    if artifact.cohort_contract_hash != canonical_payload_hash(
        dict(artifact.cohort_contract)
    ):
        raise PersonalizationCalibrationError("cohort contract hash mismatch")
    expected_identity = _fit_identity_fingerprint(
        fit_scope_id=artifact.fit_scope_id,
        fit_row_fingerprint=artifact.fit_row_fingerprint,
        fit_row_ids=artifact.fit_row_ids,
        fit_prediction_ids=artifact.fit_prediction_ids,
        fit_statistical_ids=artifact.fit_statistical_ids,
        fit_receipt_hashes=artifact.fit_receipt_hashes,
    )
    if artifact.fit_identity_fingerprint != expected_identity:
        raise PersonalizationCalibrationError("fit identity fingerprint mismatch")
    expected_overlay = canonical_payload_hash(
        _overlay_payload(
            policy_hash=artifact.fit_policy_hash,
            population_prior_bp=artifact.population_prior_bp,
            population_bin_rate_bp=artifact.population_bin_rate_bp,
            personal_bin_observation_count=artifact.personal_bin_observation_count,
            personal_bin_positive_count=artifact.personal_bin_positive_count,
        )
    )
    if artifact.overlay_hash != expected_overlay:
        raise PersonalizationCalibrationError("calibration overlay hash mismatch")


def _round_bp(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _probability(value: object, field_name: str = "probability") -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10_000:
        raise PersonalizationCalibrationError(
            f"{field_name} must be integer bp within 0..10000"
        )
    return value


def _coerce_row(
    value: PersonalizationEvaluationRow | Mapping[str, Any],
) -> PersonalizationEvaluationRow:
    if isinstance(value, PersonalizationEvaluationRow):
        return value
    if not isinstance(value, Mapping):
        raise PersonalizationCalibrationError("evaluation row must be an object")
    raw_label = value.get("label")
    label = None if raw_label is None else _integer(raw_label, "label")
    return PersonalizationEvaluationRow(
        prediction_id=str(value.get("prediction_id") or ""),
        scope_id=str(value.get("scope_id") or ""),
        symbol=str(value.get("symbol") or value.get("stock_code") or ""),
        decision_date=str(value.get("decision_date") or ""),
        label_available_date=str(
            value.get("label_available_date") or value.get("decision_date") or ""
        ),
        horizon_days=_integer(value.get("horizon_days"), "horizon_days", default=0),
        cost_scenario_hash=(
            str(value.get("cost_scenario_hash"))
            if value.get("cost_scenario_hash") is not None
            else None
        ),
        population_probability_bp=_probability(
            value.get("population_probability_bp"),
            "population_probability_bp",
        ),
        label=label,
        label_available_at=(
            str(value.get("label_available_at"))
            if value.get("label_available_at")
            else None
        ),
        outcome_recorded_at=(
            str(value.get("outcome_recorded_at"))
            if value.get("outcome_recorded_at")
            else None
        ),
        outcome_tier=str(value.get("outcome_tier") or "natural_forward"),
        action_state=str(value.get("action_state") or "not_recorded"),
        decision_at=(str(value.get("decision_at")) if value.get("decision_at") else None),
        available_at=(str(value.get("available_at")) if value.get("available_at") else None),
        receipt_created_at=(
            str(value.get("receipt_created_at"))
            if value.get("receipt_created_at")
            else None
        ),
        captured_at=(str(value.get("captured_at")) if value.get("captured_at") else None),
        decision_day_block=(
            str(value.get("decision_day_block"))
            if value.get("decision_day_block")
            else None
        ),
        row_id=str(value.get("row_id") or value.get("prediction_id") or ""),
        personal_observation_count=_integer(
            value.get("personal_observation_count"),
            "personal_observation_count",
            default=0,
        ),
        personal_positive_count=_integer(
            value.get("personal_positive_count"),
            "personal_positive_count",
            default=0,
        ),
        outcome_status=str(value.get("outcome_status") or "ready"),
        delivery_status=str(value.get("delivery_status") or "not_recorded"),
        late_delivery=bool(value.get("late_delivery", False)),
        source_result_id=str(value.get("source_result_id") or ""),
        prediction_receipt_hash=str(value.get("prediction_receipt_hash") or ""),
        model_id=str(value.get("model_id") or ""),
        dataset_id=str(value.get("dataset_id") or ""),
        dataset_hash=str(value.get("dataset_hash") or ""),
        cost_scenario_id=str(value.get("cost_scenario_id") or ""),
        cost_scenario_version=str(value.get("cost_scenario_version") or ""),
        universe_policy_hash=str(value.get("universe_policy_hash") or ""),
        label_contract_id=str(value.get("label_contract_id") or ""),
        return_basis=str(value.get("return_basis") or ""),
        source_id=str(value.get("source_id") or ""),
        prediction_receipt_schema_version=str(
            value.get("prediction_receipt_schema_version")
            or PERSONALIZATION_PREDICTION_RECEIPT_SCHEMA_VERSION
        ),
        statistical_id=str(value.get("statistical_id") or ""),
        outcome_id=str(value.get("outcome_id") or ""),
        event_id=str(value.get("event_id") or ""),
        window_days=(
            _integer(value.get("window_days"), "window_days")
            if value.get("window_days") is not None
            else None
        ),
    )


def _validate_temporal_row(row: PersonalizationEvaluationRow) -> str | None:
    """Return a blocking status; date-only PIT inference is never allowed."""

    if row.decision_at is None or row.available_at is None or row.captured_at is None:
        return "temporal_precision_unproven"
    decision = parse_aware_datetime(row.decision_at, "decision_at")
    available = parse_aware_datetime(row.available_at, "available_at")
    captured = parse_aware_datetime(row.captured_at, "captured_at")
    if available > decision:
        return "available_after_decision"
    if captured > decision:
        return "captured_after_decision"
    if row.receipt_created_at is not None:
        receipt = parse_aware_datetime(row.receipt_created_at, "receipt_created_at")
        if receipt < decision:
            return "receipt_before_decision"
    return None


def probability_bin_key(
    probability_bp: int,
    edges_bp: Sequence[int] = DEFAULT_PROBABILITY_BIN_EDGES_BP,
) -> str:
    """以 frozen probability bins 取得穩定 bin identity。"""

    probability = _probability(probability_bp, "probability_bp")
    if probability is None:
        raise PersonalizationCalibrationError("probability is required for binning")
    edges = tuple(edges_bp)
    if len(edges) < 2 or edges[0] != 0 or edges[-1] != 10_001:
        raise PersonalizationCalibrationError("probability bin edges must cover 0..10000 bp")
    for lower, upper in zip(edges, edges[1:]):
        if lower <= probability < upper:
            return f"{lower}:{upper - 1}"
    raise PersonalizationCalibrationError("probability is outside frozen bins")


@dataclass(frozen=True)
class PersonalizationCalibrationPolicy:
    """holdout 前固定的 personal overlay policy。"""

    horizon_days: int
    cost_scenario_hash: str | None
    shrinkage_strength: int = DEFAULT_SHRINKAGE_STRENGTH
    probability_bin_edges_bp: tuple[int, ...] = DEFAULT_PROBABILITY_BIN_EDGES_BP
    target: str = "binary_label"
    universe_policy_hash: str = ""
    label_contract_id: str = ""
    embargo_days: int | None = None
    population_prior_bp: int | None = None
    policy_version: str = FIXED_SHRINKAGE_POLICY_VERSION
    scope_id: str = ""
    source_id: str = ""
    model_id: str = ""
    dataset_id: str = ""
    dataset_hash: str = ""
    receipt_schema_version: str = PERSONALIZATION_PREDICTION_RECEIPT_SCHEMA_VERSION
    return_basis: str = ""
    allowed_outcome_tiers: tuple[str, ...] = ("natural_forward",)
    policy_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.horizon_days, bool) or not isinstance(self.horizon_days, int) or self.horizon_days <= 0:
            raise PersonalizationCalibrationError("horizon_days must be a positive integer")
        if isinstance(self.shrinkage_strength, bool) or not isinstance(self.shrinkage_strength, int) or self.shrinkage_strength <= 0:
            raise PersonalizationCalibrationError("shrinkage_strength must be a positive integer")
        edges = tuple(self.probability_bin_edges_bp)
        if len(edges) < 2 or edges[0] != 0 or edges[-1] != 10_001:
            raise PersonalizationCalibrationError("probability bins must cover 0..10000")
        if any(
            isinstance(edge, bool)
            or not isinstance(edge, int)
            or edge < 0
            or edge > 10_001
            for edge in edges
        ) or any(left >= right for left, right in zip(edges, edges[1:])):
            raise PersonalizationCalibrationError("probability bin edges must be increasing integers")
        embargo_days = self.horizon_days if self.embargo_days is None else self.embargo_days
        if isinstance(embargo_days, bool) or not isinstance(embargo_days, int) or embargo_days < 0:
            raise PersonalizationCalibrationError("embargo_days must be a non-negative integer")
        population_prior = _probability(self.population_prior_bp, "population_prior_bp")
        if self.policy_version != FIXED_SHRINKAGE_POLICY_VERSION:
            raise PersonalizationCalibrationError("unsupported shrinkage policy")
        object.__setattr__(self, "probability_bin_edges_bp", edges)
        object.__setattr__(self, "cost_scenario_hash", str(self.cost_scenario_hash) if self.cost_scenario_hash is not None else None)
        object.__setattr__(self, "universe_policy_hash", str(self.universe_policy_hash or "").strip())
        object.__setattr__(self, "label_contract_id", str(self.label_contract_id or "").strip())
        if not self.universe_policy_hash:
            raise PersonalizationCalibrationError(
                "universe_policy_hash is required for verified cohort"
            )
        if not self.label_contract_id:
            raise PersonalizationCalibrationError(
                "label_contract_id is required for verified cohort"
            )
        scope_id = str(self.scope_id or "").strip()
        source_id = str(self.source_id or "").strip()
        model_id = str(self.model_id or "").strip()
        dataset_id = str(self.dataset_id or "").strip()
        dataset_hash = str(self.dataset_hash or "").strip()
        receipt_schema_version = str(self.receipt_schema_version or "").strip()
        return_basis = str(self.return_basis or "").strip()
        tiers = tuple(str(item).strip() for item in self.allowed_outcome_tiers if str(item).strip())
        if len(tiers) != 1 or tiers[0] not in PERSONALIZATION_OUTCOME_TIERS:
            raise PersonalizationCalibrationError(
                "allowed_outcome_tiers must contain exactly one supported tier"
            )
        if receipt_schema_version != PERSONALIZATION_PREDICTION_RECEIPT_SCHEMA_VERSION:
            raise PersonalizationCalibrationError("unsupported receipt schema in cohort policy")
        object.__setattr__(self, "scope_id", scope_id)
        object.__setattr__(self, "source_id", source_id)
        object.__setattr__(self, "model_id", model_id)
        object.__setattr__(self, "dataset_id", dataset_id)
        object.__setattr__(self, "dataset_hash", dataset_hash)
        object.__setattr__(self, "receipt_schema_version", receipt_schema_version)
        object.__setattr__(self, "return_basis", return_basis)
        object.__setattr__(self, "allowed_outcome_tiers", tiers)
        object.__setattr__(self, "embargo_days", embargo_days)
        object.__setattr__(self, "population_prior_bp", population_prior)
        object.__setattr__(self, "policy_hash", canonical_payload_hash(self._hash_payload()))

    def _hash_payload(self) -> dict[str, Any]:
        return {
            "schema_version": PERSONALIZATION_CALIBRATION_SCHEMA_VERSION,
            "policy_version": self.policy_version,
            "horizon_days": self.horizon_days,
            "cost_scenario_hash": self.cost_scenario_hash,
            "shrinkage_strength": self.shrinkage_strength,
            "probability_bin_edges_bp": list(self.probability_bin_edges_bp),
            "target": self.target,
            "universe_policy_hash": self.universe_policy_hash,
            "label_contract_id": self.label_contract_id,
            "embargo_days": self.embargo_days,
            "population_prior_bp": self.population_prior_bp,
            "scope_id": self.scope_id,
            "source_id": self.source_id,
            "model_id": self.model_id,
            "dataset_id": self.dataset_id,
            "dataset_hash": self.dataset_hash,
            "receipt_schema_version": self.receipt_schema_version,
            "return_basis": self.return_basis,
            "allowed_outcome_tiers": list(self.allowed_outcome_tiers),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._hash_payload(), "policy_hash": self.policy_hash}


@dataclass(frozen=True)
class PersonalizationCalibrationFitArtifact:
    """Frozen calibration artifact；它不擁有 evaluation rows。"""

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
    population_bin_rate_bp: Mapping[str, int] = field(default_factory=dict)
    personal_bin_observation_count: Mapping[str, int] = field(default_factory=dict)
    personal_bin_positive_count: Mapping[str, int] = field(default_factory=dict)
    probability_bin_edges_bp: tuple[int, ...] = DEFAULT_PROBABILITY_BIN_EDGES_BP
    embargo_days: int = 0
    schema_version: str = PERSONALIZATION_CALIBRATION_SCHEMA_VERSION
    policy_version: str = FIXED_SHRINKAGE_POLICY_VERSION
    fit_prediction_ids: tuple[str, ...] = ()
    fit_statistical_ids: tuple[str, ...] = ()
    fit_receipt_hashes: tuple[str, ...] = ()
    fit_scope_id: str = ""
    fit_identity_fingerprint: str = ""
    cohort_contract_hash: str = ""
    cohort_contract: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
    ) -> "PersonalizationCalibrationFitArtifact":
        """Reload one persisted artifact without accepting envelope fields.

        The artifact remains the existing frozen calibration contract.  The
        caller may persist a separate source-binding envelope around it, but
        only the exact fields emitted by :meth:`to_dict` are passed to this
        constructor.  ``__post_init__`` therefore re-checks every derived
        identity, overlay and cohort hash on reload.
        """

        if not isinstance(value, Mapping):
            raise PersonalizationCalibrationError(
                "calibration fit artifact must be an object"
            )
        tuple_fields = {
            "fit_row_ids",
            "probability_bin_edges_bp",
            "fit_prediction_ids",
            "fit_statistical_ids",
            "fit_receipt_hashes",
        }
        mapping_fields = {
            "population_bin_rate_bp",
            "personal_bin_observation_count",
            "personal_bin_positive_count",
            "cohort_contract",
        }
        field_names = (
            "artifact_id",
            "fit_as_of",
            "fit_row_fingerprint",
            "fit_policy_hash",
            "overlay_hash",
            "horizon_days",
            "cost_scenario_hash",
            "fit_row_ids",
            "fit_row_count",
            "fit_positive_count",
            "population_prior_bp",
            "shrinkage_strength",
            "created_at",
            "population_bin_rate_bp",
            "personal_bin_observation_count",
            "personal_bin_positive_count",
            "probability_bin_edges_bp",
            "embargo_days",
            "schema_version",
            "policy_version",
            "fit_prediction_ids",
            "fit_statistical_ids",
            "fit_receipt_hashes",
            "fit_scope_id",
            "fit_identity_fingerprint",
            "cohort_contract_hash",
            "cohort_contract",
        )
        values: dict[str, Any] = {}
        for field_name in field_names:
            if field_name not in value:
                continue
            raw = value[field_name]
            if field_name in tuple_fields:
                if not isinstance(raw, (list, tuple)):
                    raise PersonalizationCalibrationError(
                        f"{field_name} must be an array"
                    )
                values[field_name] = tuple(raw)
            elif field_name in mapping_fields:
                if not isinstance(raw, Mapping):
                    raise PersonalizationCalibrationError(
                        f"{field_name} must be an object"
                    )
                values[field_name] = dict(raw)
            else:
                values[field_name] = raw
        try:
            return cls(**values)
        except TypeError as exc:
            raise PersonalizationCalibrationError(
                f"calibration fit artifact fields are incomplete: {exc}"
            ) from exc

    def __post_init__(self) -> None:
        if not self.artifact_id.strip():
            raise PersonalizationCalibrationError("artifact_id is required")
        _date(self.fit_as_of, "fit_as_of")
        for name in ("horizon_days", "shrinkage_strength"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise PersonalizationCalibrationError(f"{name} must be a positive integer")
        for name in ("fit_row_count", "fit_positive_count", "embargo_days"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise PersonalizationCalibrationError(f"{name} must be a non-negative integer")
        if self.fit_positive_count > self.fit_row_count:
            raise PersonalizationCalibrationError("fit_positive_count exceeds fit_row_count")
        if _probability(self.population_prior_bp, "population_prior_bp") is None:
            raise PersonalizationCalibrationError("population_prior_bp is required")
        fit_row_ids = tuple(str(item).strip() for item in self.fit_row_ids)
        if any(not item for item in fit_row_ids):
            raise PersonalizationCalibrationError("fit row identity is missing")
        if len(fit_row_ids) != self.fit_row_count:
            raise PersonalizationCalibrationError("fit_row_ids/count mismatch")
        if len(set(fit_row_ids)) != len(fit_row_ids):
            raise PersonalizationCalibrationError("fit row identity is duplicated")
        fit_prediction_ids = tuple(str(item).strip() for item in self.fit_prediction_ids)
        fit_statistical_ids = tuple(str(item).strip() for item in self.fit_statistical_ids)
        fit_receipt_hashes = tuple(str(item).strip() for item in self.fit_receipt_hashes)
        if len(fit_prediction_ids) != self.fit_row_count:
            raise PersonalizationCalibrationError("fit_prediction_ids/count mismatch")
        if len(fit_statistical_ids) != self.fit_row_count:
            raise PersonalizationCalibrationError("fit_statistical_ids/count mismatch")
        if len(fit_receipt_hashes) != self.fit_row_count:
            raise PersonalizationCalibrationError("fit_receipt_hashes/count mismatch")
        if len(set(fit_prediction_ids)) != len(fit_prediction_ids):
            raise PersonalizationCalibrationError("fit prediction identity is duplicated")
        if len(set(fit_statistical_ids)) != len(fit_statistical_ids):
            raise PersonalizationCalibrationError("fit statistical identity is duplicated")
        if any(not item.startswith("sha256:") for item in fit_receipt_hashes):
            raise PersonalizationCalibrationError("fit receipt identity is not verified")
        fit_scope_id = str(self.fit_scope_id or "").strip()
        if self.fit_row_count and not fit_scope_id:
            raise PersonalizationCalibrationError("fit_scope_id is required")
        expected_identity = _fit_identity_fingerprint(
            fit_scope_id=fit_scope_id,
            fit_row_fingerprint=self.fit_row_fingerprint,
            fit_row_ids=fit_row_ids,
            fit_prediction_ids=fit_prediction_ids,
            fit_statistical_ids=fit_statistical_ids,
            fit_receipt_hashes=fit_receipt_hashes,
        )
        if self.fit_identity_fingerprint != expected_identity:
            raise PersonalizationCalibrationError("fit identity fingerprint mismatch")
        if len(self.probability_bin_edges_bp) < 2 or self.probability_bin_edges_bp[-1] != 10_001:
            raise PersonalizationCalibrationError("artifact probability bins are invalid")
        probability_bin_edges_bp = tuple(self.probability_bin_edges_bp)
        for mapping_name in (
            "population_bin_rate_bp",
            "personal_bin_observation_count",
            "personal_bin_positive_count",
        ):
            for key, value in getattr(self, mapping_name).items():
                if mapping_name == "population_bin_rate_bp":
                    _probability(value, f"{mapping_name}.{key}")
                elif isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise PersonalizationCalibrationError(f"{mapping_name} contains invalid count")
        if self.schema_version != PERSONALIZATION_CALIBRATION_SCHEMA_VERSION:
            raise PersonalizationCalibrationError("unsupported calibration artifact schema")
        if self.policy_version != FIXED_SHRINKAGE_POLICY_VERSION:
            raise PersonalizationCalibrationError("unsupported shrinkage policy")
        if not str(self.fit_policy_hash).startswith("sha256:"):
            raise PersonalizationCalibrationError("fit_policy_hash is invalid")
        if not str(self.fit_row_fingerprint).startswith("sha256:"):
            raise PersonalizationCalibrationError("fit_row_fingerprint is invalid")
        cohort_contract = dict(self.cohort_contract)
        if cohort_contract.get("schema_version") != PERSONALIZATION_COHORT_CONTRACT_SCHEMA_VERSION:
            raise PersonalizationCalibrationError("cohort contract schema is unsupported")
        if self.cohort_contract_hash != canonical_payload_hash(cohort_contract):
            raise PersonalizationCalibrationError("cohort contract hash mismatch")
        if cohort_contract.get("scope_id") != fit_scope_id:
            raise PersonalizationCalibrationError("cohort contract scope mismatch")
        if sum(self.personal_bin_observation_count.values()) != self.fit_row_count:
            raise PersonalizationCalibrationError("fit observation count mismatch")
        if sum(self.personal_bin_positive_count.values()) != self.fit_positive_count:
            raise PersonalizationCalibrationError("fit positive count mismatch")
        for key, positive in self.personal_bin_positive_count.items():
            if positive > self.personal_bin_observation_count.get(key, 0):
                raise PersonalizationCalibrationError(
                    "personal positive count exceeds observation count"
                )
        expected_overlay = canonical_payload_hash(
            _overlay_payload(
                policy_hash=self.fit_policy_hash,
                population_prior_bp=self.population_prior_bp,
                population_bin_rate_bp=self.population_bin_rate_bp,
                personal_bin_observation_count=self.personal_bin_observation_count,
                personal_bin_positive_count=self.personal_bin_positive_count,
            )
        )
        if self.overlay_hash != expected_overlay:
            raise PersonalizationCalibrationError("calibration overlay hash mismatch")
        object.__setattr__(self, "fit_prediction_ids", fit_prediction_ids)
        object.__setattr__(self, "fit_statistical_ids", fit_statistical_ids)
        object.__setattr__(self, "fit_receipt_hashes", fit_receipt_hashes)
        object.__setattr__(self, "fit_row_ids", fit_row_ids)
        object.__setattr__(self, "probability_bin_edges_bp", probability_bin_edges_bp)
        object.__setattr__(self, "fit_scope_id", fit_scope_id)
        object.__setattr__(self, "cohort_contract", _freeze(cohort_contract))
        object.__setattr__(
            self,
            "population_bin_rate_bp",
            _freeze({str(key): int(value) for key, value in self.population_bin_rate_bp.items()}),
        )
        object.__setattr__(
            self,
            "personal_bin_observation_count",
            _freeze({str(key): int(value) for key, value in self.personal_bin_observation_count.items()}),
        )
        object.__setattr__(
            self,
            "personal_bin_positive_count",
            _freeze({str(key): int(value) for key, value in self.personal_bin_positive_count.items()}),
        )
        try:
            parse_aware_datetime(self.created_at, "created_at")
        except ValueError as exc:
            raise PersonalizationCalibrationError(str(exc)) from exc

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
            "population_bin_rate_bp": _thaw(self.population_bin_rate_bp),
            "personal_bin_observation_count": _thaw(self.personal_bin_observation_count),
            "personal_bin_positive_count": _thaw(self.personal_bin_positive_count),
            "probability_bin_edges_bp": list(self.probability_bin_edges_bp),
            "embargo_days": self.embargo_days,
            "fit_prediction_ids": list(self.fit_prediction_ids),
            "fit_statistical_ids": list(self.fit_statistical_ids),
            "fit_receipt_hashes": list(self.fit_receipt_hashes),
            "fit_scope_id": self.fit_scope_id,
            "fit_identity_fingerprint": self.fit_identity_fingerprint,
            "cohort_contract_hash": self.cohort_contract_hash,
            "cohort_contract": _thaw(self.cohort_contract),
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
    bin_key: str = ""
    outcome_status: str = "ready"
    action_state: str = "not_recorded"

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
            "bin_key": self.bin_key,
            "outcome_status": self.outcome_status,
            "action_state": self.action_state,
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
    adoption_confidence_reason: str = (
        "ordinary reliability intervals are descriptive only; dependency-aware adoption method is not in first slice"
    )
    baseline_metrics: Mapping[str, Any] = field(default_factory=dict)
    personal_challenger_metrics: Mapping[str, Any] = field(default_factory=dict)
    cohort_counts: Mapping[str, int] = field(default_factory=dict)
    matched_sample_fingerprint: str = ""
    independence_assumption: str = "descriptive_only"
    decision: str = "retain_population"
    reason: str = ""
    natural_forward_credit: bool = False
    shadow_only: bool = True
    formal_order_allowed: bool = False
    auto_action_allowed: bool = False
    evaluation_cutoff_at: str | None = None

    @property
    def sample_size(self) -> int:
        return sum(
            1
            for row in self.rows
            if row.status in {"population_cold_start", "shrunken_personal_overlay", "label_pending"}
            and row.label_matured
            and row.label is not None
            and row.calibrated_probability_bp is not None
        )

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
            "baseline_metrics": dict(self.baseline_metrics),
            "personal_challenger_metrics": dict(self.personal_challenger_metrics),
            "cohort_counts": dict(self.cohort_counts),
            "matched_sample_fingerprint": self.matched_sample_fingerprint,
            "independence_assumption": self.independence_assumption,
            "decision": self.decision,
            "reason": self.reason,
            "natural_forward_credit": self.natural_forward_credit,
            "shadow_only": self.shadow_only,
            "formal_order_allowed": self.formal_order_allowed,
            "auto_action_allowed": self.auto_action_allowed,
            "evaluation_cutoff_at": self.evaluation_cutoff_at,
        }


def _metric_rows(
    rows: Sequence[PersonalizationCalibrationRowResult],
    *,
    probability_field: str,
) -> list[tuple[PersonalizationCalibrationRowResult, int]]:
    result: list[tuple[PersonalizationCalibrationRowResult, int]] = []
    blocked = {
        "temporal_precision_unproven",
        "available_after_decision",
        "captured_after_decision",
        "receipt_before_decision",
        "not_delivered",
        "late_delivery_no_credit",
    }
    for row in rows:
        probability = getattr(row, probability_field)
        if (
            probability is not None
            and row.label_matured
            and row.label in {0, 1}
            and row.outcome_status == "ready"
            and row.status not in blocked
        ):
            result.append((row, int(row.label)))
    return result


def _brier_bp(pairs: Sequence[tuple[int, int]]) -> int | None:
    if not pairs:
        return None
    numerator = sum(
        (Decimal(probability) - Decimal(label * 10_000)) ** 2
        for probability, label in pairs
    )
    return _round_bp(numerator / (Decimal(len(pairs)) * Decimal(10_000)))


def _bin_keys(edges: Sequence[int]) -> tuple[str, ...]:
    return tuple(f"{lower}:{upper - 1}" for lower, upper in zip(edges, edges[1:]))


def _reliability(
    pairs: Sequence[tuple[PersonalizationCalibrationRowResult, int]],
    *,
    probability_field: str,
    bin_keys: Sequence[str],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for bin_key in bin_keys:
        grouped = [(row, label) for row, label in pairs if row.bin_key == bin_key]
        if not grouped:
            output.append(
                {
                    "bin": bin_key,
                    "count": 0,
                    "positive_count": 0,
                    "prediction_mean_bp": None,
                    "observed_rate_bp": None,
                    "ci_low_bp": None,
                    "ci_high_bp": None,
                    "status": "descriptive_only",
                }
            )
            continue
        probabilities = [int(getattr(row, probability_field)) for row, _ in grouped]
        positives = sum(label for _, label in grouped)
        count = len(grouped)
        prediction_mean = _round_bp(
            sum(Decimal(value) for value in probabilities) / Decimal(count)
        )
        observed_rate = _round_bp(Decimal(positives * 10_000) / Decimal(count))
        ci_low, ci_high = wilson_interval_bp(positives, count) or (None, None)
        output.append(
            {
                "bin": bin_key,
                "count": count,
                "positive_count": positives,
                "prediction_mean_bp": prediction_mean,
                "observed_rate_bp": observed_rate,
                "ci_low_bp": ci_low,
                "ci_high_bp": ci_high,
                "status": "descriptive_only",
            }
        )
    return output


def _metrics(
    rows: Sequence[PersonalizationCalibrationRowResult],
    *,
    probability_field: str,
    bin_keys: Sequence[str],
) -> dict[str, Any]:
    valid = _metric_rows(rows, probability_field=probability_field)
    pairs = [(int(getattr(row, probability_field)), label) for row, label in valid]
    reliability = _reliability(
        valid,
        probability_field=probability_field,
        bin_keys=bin_keys,
    )
    ece_numerator = Decimal(0)
    for item in reliability:
        if item["count"] and item["prediction_mean_bp"] is not None and item["observed_rate_bp"] is not None:
            ece_numerator += Decimal(abs(item["prediction_mean_bp"] - item["observed_rate_bp"])) * Decimal(item["count"])
    ece = _round_bp(ece_numerator / Decimal(len(valid))) if valid else None
    return {
        "sample_count": len(valid),
        "brier_bp": _brier_bp(pairs),
        "ece_bp": ece,
        "reliability": reliability,
        "status": "descriptive_only",
        "row_fingerprint": canonical_payload_hash(
            {"row_ids": sorted(row.row_id for row, _ in valid)}
        ),
    }


class PersonalizationCalibrationEvaluator:
    """固定 policy 的 fit/evaluate 服務。"""

    def fit(
        self,
        fit_rows: Sequence[PersonalizationEvaluationRow | Mapping[str, Any]],
        *,
        fit_as_of: str,
        horizon_days: int | None = None,
        cost_scenario_hash: str | None = None,
        shrinkage_strength: int = DEFAULT_SHRINKAGE_STRENGTH,
        artifact_id: str | None = None,
        created_at: str | None = None,
        policy: PersonalizationCalibrationPolicy | None = None,
    ) -> PersonalizationCalibrationFitArtifact:
        resolved_rows = _deduplicate_rows(
            tuple(_coerce_row(row) for row in fit_rows),
            phase="fit",
        )
        fit_day = _date(fit_as_of, "fit_as_of")
        fit_cutoff_date = date.fromisoformat(fit_day)
        resolved_created_at = created_at or datetime.now(timezone.utc).isoformat(timespec="microseconds")
        try:
            created_datetime = parse_aware_datetime(resolved_created_at, "created_at")
        except ValueError as exc:
            raise PersonalizationCalibrationError(str(exc)) from exc
        if created_datetime.date() < fit_cutoff_date:
            raise PersonalizationCalibrationError(
                "created_at must not precede fit_as_of date"
            )
        if policy is None:
            if horizon_days is None:
                raise PersonalizationCalibrationError("horizon_days is required")
            policy = PersonalizationCalibrationPolicy(
                horizon_days=horizon_days,
                cost_scenario_hash=cost_scenario_hash,
                shrinkage_strength=shrinkage_strength,
            )
        elif horizon_days is not None and horizon_days != policy.horizon_days:
            raise PersonalizationCalibrationError("fit horizon conflicts with policy")
        elif cost_scenario_hash is not None and cost_scenario_hash != policy.cost_scenario_hash:
            raise PersonalizationCalibrationError("fit cost scenario conflicts with policy")
        if any(row.horizon_days != policy.horizon_days for row in resolved_rows):
            raise PersonalizationCalibrationError("fit horizon contract is mixed")
        if any(row.cost_scenario_hash != policy.cost_scenario_hash for row in resolved_rows):
            raise PersonalizationCalibrationError("fit cost scenario contract is mixed")

        cohort_contract = _resolve_cohort_contract(resolved_rows, policy)

        population_values: list[int] = []
        bin_values: dict[str, list[int]] = {}
        bin_positive: dict[str, int] = {}
        for row in resolved_rows:
            if _date(row.decision_date, "decision_date") > fit_day:
                raise PersonalizationCalibrationError("fit row decision is after fit_as_of")
            if _date(row.label_available_date, "label_available_date") > fit_day:
                raise PersonalizationCalibrationError("fit row label is not available at fit_as_of")
            if row.label_available_at is None:
                raise PersonalizationCalibrationError(
                    "fit row label availability precision is unproven"
                )
            label_available_at = parse_aware_datetime(
                row.label_available_at,
                "label_available_at",
            )
            if label_available_at.date() > fit_cutoff_date:
                raise PersonalizationCalibrationError(
                    "fit row label is not available at fit_as_of"
                )
            if row.outcome_recorded_at is None:
                raise PersonalizationCalibrationError(
                    "fit row outcome_recorded_at precision is unproven"
                )
            outcome_recorded_at = parse_aware_datetime(
                row.outcome_recorded_at,
                "outcome_recorded_at",
            )
            if outcome_recorded_at.date() > fit_cutoff_date:
                raise PersonalizationCalibrationError(
                    "fit row outcome is recorded after fit_as_of"
                )
            if row.receipt_created_at is None:
                raise PersonalizationCalibrationError(
                    "fit row receipt_created_at precision is unproven"
                )
            receipt_created_at = parse_aware_datetime(
                row.receipt_created_at,
                "receipt_created_at",
            )
            for dependency_name, dependency_datetime in (
                ("label_available_at", label_available_at),
                ("outcome_recorded_at", outcome_recorded_at),
                ("receipt_created_at", receipt_created_at),
            ):
                if created_datetime < dependency_datetime:
                    raise PersonalizationCalibrationError(
                        f"created_at must not precede fit dependency {dependency_name}"
                    )
            temporal_status = _validate_temporal_row(row)
            if temporal_status is not None:
                raise PersonalizationCalibrationError(
                    f"fit row temporal contract blocked: {temporal_status}"
                )
            if row.outcome_status != "ready" or row.label is None:
                raise PersonalizationCalibrationError("fit row label must be matured and ready")
            if row.delivery_status != "delivered" or row.late_delivery:
                raise PersonalizationCalibrationError("fit row delivery is not eligible for calibration")
            if row.population_probability_bp is None:
                raise PersonalizationCalibrationError("fit row population probability is required")
            population_values.append(row.population_probability_bp)
            key = probability_bin_key(row.population_probability_bp, policy.probability_bin_edges_bp)
            bin_values.setdefault(key, []).append(row.population_probability_bp)
            bin_positive[key] = bin_positive.get(key, 0) + row.label

        if not resolved_rows and policy.population_prior_bp is None:
            raise PersonalizationCalibrationError("empty fit requires policy.population_prior_bp")
        population_prior = policy.population_prior_bp
        if population_prior is None:
            population_prior = _round_bp(
                sum(Decimal(value) for value in population_values)
                / Decimal(len(population_values))
            )
        bin_keys = _bin_keys(policy.probability_bin_edges_bp)
        population_bin_rate = {
            key: (
                _round_bp(
                    sum(Decimal(value) for value in bin_values[key])
                    / Decimal(len(bin_values[key]))
                )
                if key in bin_values
                else population_prior
            )
            for key in bin_keys
        }
        personal_counts = {key: len(bin_values.get(key, ())) for key in bin_keys}
        personal_positive = {key: bin_positive.get(key, 0) for key in bin_keys}
        overlay_hash = canonical_payload_hash(
            _overlay_payload(
                policy_hash=policy.policy_hash,
                population_prior_bp=population_prior,
                population_bin_rate_bp=population_bin_rate,
                personal_bin_observation_count=personal_counts,
                personal_bin_positive_count=personal_positive,
            )
        )
        artifact_digest = policy.policy_hash.split(":", 1)[1][:16]
        ordered_rows = tuple(sorted(resolved_rows, key=lambda item: item.effective_row_id))
        fit_row_fingerprint = _hash_rows(resolved_rows)
        fit_row_ids = tuple(row.effective_row_id for row in ordered_rows)
        fit_prediction_ids = tuple(row.prediction_id for row in ordered_rows)
        fit_statistical_ids = tuple(row.effective_statistical_id for row in ordered_rows)
        fit_receipt_hashes = tuple(row.prediction_receipt_hash for row in ordered_rows)
        fit_scope_id = str(cohort_contract.get("scope_id") or "")
        cohort_contract_hash = canonical_payload_hash(cohort_contract)
        return PersonalizationCalibrationFitArtifact(
            artifact_id=str(
                artifact_id
                or f"personalization_fit_{fit_day.replace('-', '')}_{artifact_digest}"
            ),
            fit_as_of=fit_day,
            fit_row_fingerprint=fit_row_fingerprint,
            fit_policy_hash=policy.policy_hash,
            overlay_hash=overlay_hash,
            horizon_days=policy.horizon_days,
            cost_scenario_hash=policy.cost_scenario_hash,
            fit_row_ids=fit_row_ids,
            fit_row_count=len(resolved_rows),
            fit_positive_count=sum(row.label or 0 for row in resolved_rows),
            population_prior_bp=population_prior,
            shrinkage_strength=policy.shrinkage_strength,
            created_at=resolved_created_at,
            population_bin_rate_bp=population_bin_rate,
            personal_bin_observation_count=personal_counts,
            personal_bin_positive_count=personal_positive,
            probability_bin_edges_bp=policy.probability_bin_edges_bp,
            embargo_days=policy.embargo_days or 0,
            fit_prediction_ids=fit_prediction_ids,
            fit_statistical_ids=fit_statistical_ids,
            fit_receipt_hashes=fit_receipt_hashes,
            fit_scope_id=fit_scope_id,
            fit_identity_fingerprint=_fit_identity_fingerprint(
                fit_scope_id=fit_scope_id,
                fit_row_fingerprint=fit_row_fingerprint,
                fit_row_ids=fit_row_ids,
                fit_prediction_ids=fit_prediction_ids,
                fit_statistical_ids=fit_statistical_ids,
                fit_receipt_hashes=fit_receipt_hashes,
            ),
            cohort_contract_hash=cohort_contract_hash,
            cohort_contract=cohort_contract,
        )

    def evaluate(
        self,
        artifact: PersonalizationCalibrationFitArtifact,
        evaluation_rows: Sequence[PersonalizationEvaluationRow | Mapping[str, Any]],
        *,
        evaluated_as_of: str,
        evaluation_cutoff_at: str | None = None,
        predeclared_adoption_method: str | None = None,
    ) -> PersonalizationCalibrationEvaluation:
        if not isinstance(artifact, PersonalizationCalibrationFitArtifact):
            raise PersonalizationCalibrationError("artifact type is invalid")
        _validate_artifact_integrity(artifact)
        resolved_rows = _deduplicate_rows(
            tuple(_coerce_row(row) for row in evaluation_rows),
            phase="evaluation",
        )
        evaluated_day = _date(evaluated_as_of, "evaluated_as_of")
        resolved_cutoff = None
        cutoff_datetime: datetime | None = None
        if evaluation_cutoff_at is not None:
            try:
                cutoff_datetime = parse_aware_datetime(
                    evaluation_cutoff_at,
                    "evaluation_cutoff_at",
                )
                resolved_cutoff = cutoff_datetime.isoformat(timespec="microseconds")
            except ValueError as exc:
                raise PersonalizationCalibrationError(str(exc)) from exc
            if cutoff_datetime.date() > date.fromisoformat(evaluated_day):
                raise PersonalizationCalibrationError(
                    "evaluation_cutoff_at cannot follow evaluated_as_of"
                )
        fit_ids = set(artifact.fit_row_ids)
        fit_prediction_ids = set(artifact.fit_prediction_ids)
        fit_statistical_ids = set(artifact.fit_statistical_ids)
        eval_ids = {row.effective_row_id for row in resolved_rows}
        eval_prediction_ids = {row.prediction_id for row in resolved_rows}
        eval_statistical_ids = {row.effective_statistical_id for row in resolved_rows}
        if (
            fit_ids.intersection(eval_ids)
            or fit_prediction_ids.intersection(eval_prediction_ids)
            or fit_statistical_ids.intersection(eval_statistical_ids)
        ):
            raise PersonalizationCalibrationError("fit/evaluation row overlap detected")
        expected_cohort = dict(artifact.cohort_contract)
        for row in resolved_rows:
            row_cohort = _row_cohort_payload(row)
            for field_name in _COHORT_REQUIRED_FIELDS:
                if field_name == "prediction_receipt_hash":
                    continue
                if row_cohort[field_name] != expected_cohort.get(field_name):
                    raise PersonalizationCalibrationError(
                        f"evaluation cohort contract mismatch at {field_name}"
                    )
        if any(row.horizon_days != artifact.horizon_days for row in resolved_rows):
            raise PersonalizationCalibrationError("evaluation horizon does not match fit artifact")
        if any(row.cost_scenario_hash != artifact.cost_scenario_hash for row in resolved_rows):
            raise PersonalizationCalibrationError("evaluation cost scenario does not match fit artifact")
        purge_cutoff = date.fromisoformat(artifact.fit_as_of) + timedelta(days=artifact.embargo_days)
        if any(date.fromisoformat(row.decision_date) <= purge_cutoff for row in resolved_rows):
            raise PersonalizationCalibrationError(
                "evaluation decision is inside purged/embargo interval"
            )

        results: list[PersonalizationCalibrationRowResult] = []
        missing_population = 0
        temporal_blocked = 0
        cohort_counts: dict[str, int] = {}
        bin_keys = _bin_keys(artifact.probability_bin_edges_bp)
        for row in resolved_rows:
            temporal_status = _validate_temporal_row(row)
            if temporal_status is not None:
                temporal_blocked += 1
            availability_status = _label_availability_status(
                row,
                cutoff=cutoff_datetime,
            )
            label_matured = availability_status is None and (
                row.outcome_status == "ready"
                and row.label_available_at is not None
            )
            outcome_status = row.outcome_status
            status = temporal_status or availability_status or outcome_status
            calibrated: int | None = None
            bin_key = ""
            if row.delivery_status != "delivered":
                status = "not_delivered"
            elif row.late_delivery:
                status = "late_delivery_no_credit"
            elif temporal_status is not None:
                status = temporal_status
            elif outcome_status not in PERSONALIZATION_OUTCOME_STATUSES:
                status = "invalid"
            elif outcome_status != "ready":
                status = outcome_status
            elif availability_status is not None:
                status = availability_status
            elif not label_matured:
                status = "temporal_precision_unproven"
            elif row.label is None:
                status = "matured_missing"
            elif row.population_probability_bp is None:
                missing_population += 1
                status = "population_probability_unavailable"
            else:
                bin_key = probability_bin_key(
                    row.population_probability_bp,
                    artifact.probability_bin_edges_bp,
                )
                n = artifact.personal_bin_observation_count.get(bin_key, 0)
                positive = artifact.personal_bin_positive_count.get(bin_key, 0)
                population_bin_rate = artifact.population_bin_rate_bp.get(
                    bin_key,
                    artifact.population_prior_bp,
                )
                if n == 0:
                    calibrated = row.population_probability_bp
                    status = "population_cold_start"
                else:
                    personal_rate = _round_bp(
                        Decimal(positive * 10_000) / Decimal(n)
                    )
                    numerator = (
                        Decimal(n) * Decimal(personal_rate)
                        + Decimal(artifact.shrinkage_strength) * Decimal(population_bin_rate)
                    )
                    denominator = Decimal(n + artifact.shrinkage_strength)
                    calibrated = max(0, min(10_000, _round_bp(numerator / denominator)))
                    status = "shrunken_personal_overlay"
            cohort_counts[status] = cohort_counts.get(status, 0) + 1
            results.append(
                PersonalizationCalibrationRowResult(
                    prediction_id=row.prediction_id,
                    row_id=row.effective_row_id,
                    population_probability_bp=row.population_probability_bp,
                    calibrated_probability_bp=calibrated,
                    personal_observation_count=(
                        artifact.personal_bin_observation_count.get(bin_key, 0)
                        if bin_key
                        else 0
                    ),
                    personal_positive_count=(
                        artifact.personal_bin_positive_count.get(bin_key, 0)
                        if bin_key
                        else 0
                    ),
                    status=status,
                    label=(
                        row.label
                        if label_matured
                        and row.label is not None
                        and row.outcome_status == "ready"
                        and temporal_status is None
                        else None
                    ),
                    label_matured=label_matured,
                    bin_key=bin_key,
                    outcome_status=outcome_status,
                    action_state=row.action_state,
                )
            )

        evaluation_fingerprint = _hash_rows(resolved_rows)
        matched_sample_fingerprint = canonical_payload_hash(
            {
                "row_ids": sorted(
                    row.row_id
                    for row in results
                    if row.label_matured and row.label is not None and row.outcome_status == "ready"
                )
            }
        )
        baseline_metrics = _metrics(
            results,
            probability_field="population_probability_bp",
            bin_keys=bin_keys,
        )
        personal_metrics = _metrics(
            results,
            probability_field="calibrated_probability_bp",
            bin_keys=bin_keys,
        )
        metrics_sample_count = int(baseline_metrics.get("sample_count") or 0)
        if temporal_blocked:
            overall_status = "temporal_contract_blocked"
        elif missing_population == len(results) and results:
            overall_status = "population_probability_unavailable"
        elif not metrics_sample_count:
            overall_status = "insufficient_evidence"
        else:
            overall_status = "evaluated"
        natural_count = sum(
            1
            for row, source in zip(resolved_rows, results)
            if row.outcome_tier == "natural_forward"
            and source.outcome_status == "ready"
            and source.label_matured
            and source.label is not None
            and row.delivery_status == "delivered"
            and not row.late_delivery
        )
        if not resolved_rows:
            decision = "retain_population"
            reason = "insufficient_natural_evidence:no_evaluation_rows"
        elif temporal_blocked:
            decision = "blocked"
            reason = "temporal_contract_blocked"
        elif natural_count == 0:
            decision = "retain_population"
            reason = "insufficient_natural_evidence"
        else:
            decision = "retain_population"
            reason = "first_slice_shadow_only;natural_adoption_not_evaluable"
        # ``predeclared_adoption_method`` is accepted for API compatibility,
        # but the first slice never upgrades its confidence status.
        _ = predeclared_adoption_method
        return PersonalizationCalibrationEvaluation(
            artifact_id=artifact.artifact_id,
            evaluated_as_of=evaluated_day,
            evaluation_row_fingerprint=evaluation_fingerprint,
            fit_row_fingerprint=artifact.fit_row_fingerprint,
            rows=tuple(results),
            status=overall_status,
            population_probability_missing_count=missing_population,
            temporal_blocked_count=temporal_blocked,
            baseline_metrics=baseline_metrics,
            personal_challenger_metrics=personal_metrics,
            cohort_counts=cohort_counts,
            matched_sample_fingerprint=matched_sample_fingerprint,
            decision=decision,
            reason=reason,
            natural_forward_credit=False,
            shadow_only=True,
            formal_order_allowed=False,
            auto_action_allowed=False,
            evaluation_cutoff_at=resolved_cutoff,
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
    "DEFAULT_PROBABILITY_BIN_EDGES_BP",
    "DEFAULT_SHRINKAGE_STRENGTH",
    "FIXED_SHRINKAGE_POLICY_VERSION",
    "PERSONALIZATION_CALIBRATION_SCHEMA_VERSION",
    "PersonalizationCalibrationError",
    "PersonalizationCalibrationEvaluation",
    "PersonalizationCalibrationEvaluator",
    "PersonalizationCalibrationFitArtifact",
    "PersonalizationCalibrationPolicy",
    "PersonalizationCalibrationRowResult",
    "probability_bin_key",
    "wilson_interval_bp",
]
