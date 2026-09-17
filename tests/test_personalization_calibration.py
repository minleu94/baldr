from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import pytest

from app_module.personalization_calibration import (
    PersonalizationCalibrationError,
    PersonalizationCalibrationEvaluator,
    PersonalizationCalibrationPolicy,
    wilson_interval_bp,
)
from app_module.personalization_contract import PersonalizationEvaluationRow


COST_HASH = "sha256:" + ("d" * 64)
SCOPE_ID = "scope_calibration_user_001"
RECEIPT_HASH = "sha256:" + ("c" * 64)
UNIVERSE_HASH = "sha256:" + ("e" * 64)
DATASET_HASH = "sha256:" + ("f" * 64)


def _row(
    prediction_id: str,
    decision_date: str,
    *,
    label_available_date: str | None = None,
    probability: int | None = 5000,
    label: int | None = 1,
    outcome_status: str = "ready",
    outcome_tier: str = "natural_forward",
    delivery_status: str = "delivered",
    late_delivery: bool = False,
    symbol: str = "2330",
    row_id: str | None = None,
) -> PersonalizationEvaluationRow:
    available_day = date.fromisoformat(decision_date)
    decision_at = f"{decision_date}T09:00:00+00:00"
    available_at = f"{decision_date}T08:55:00+00:00"
    label_at = (
        date.fromisoformat(label_available_date or (available_day + timedelta(days=20)).isoformat())
        .isoformat()
        + "T00:00:00+00:00"
    )
    return PersonalizationEvaluationRow(
        prediction_id=prediction_id,
        scope_id=SCOPE_ID,
        symbol=symbol,
        decision_date=decision_date,
        label_available_date=label_available_date or (available_day + timedelta(days=20)).isoformat(),
        horizon_days=20,
        cost_scenario_hash=COST_HASH,
        population_probability_bp=probability,
        label=label,
        label_available_at=label_at,
        outcome_recorded_at=label_at,
        outcome_tier=outcome_tier,
        action_state="not_recorded",
        decision_at=decision_at,
        available_at=available_at,
        captured_at=available_at,
        receipt_created_at=f"{decision_date}T09:01:00+00:00",
        outcome_status=outcome_status,
        delivery_status=delivery_status,
        late_delivery=late_delivery,
        row_id=row_id or prediction_id,
        source_id="recommendation_service",
        prediction_receipt_hash=RECEIPT_HASH,
        model_id="model_calibration_v1",
        dataset_id="dataset_calibration_v1",
        dataset_hash=DATASET_HASH,
        universe_policy_hash=UNIVERSE_HASH,
        label_contract_id="label_contract_v1",
        return_basis="close_to_close_event_date",
    )


def _policy(*, embargo_days: int = 5) -> PersonalizationCalibrationPolicy:
    return PersonalizationCalibrationPolicy(
        horizon_days=20,
        cost_scenario_hash=COST_HASH,
        shrinkage_strength=2,
        embargo_days=embargo_days,
        universe_policy_hash="sha256:" + ("e" * 64),
        label_contract_id="label_contract_v1",
        scope_id=SCOPE_ID,
        source_id="recommendation_service",
        model_id="model_calibration_v1",
        dataset_id="dataset_calibration_v1",
        dataset_hash=DATASET_HASH,
        return_basis="close_to_close_event_date",
    )


def test_fixed_bin_shrinkage_uses_decimal_bp_and_same_eval_population_rows() -> None:
    evaluator = PersonalizationCalibrationEvaluator()
    policy = _policy()
    artifact = evaluator.fit(
        (
            _row("fit_001", "2025-01-01", label=1),
            _row("fit_002", "2025-01-02", label=0),
        ),
        fit_as_of="2025-01-31",
        policy=policy,
        artifact_id="fit_artifact_001",
        created_at="2025-02-01T00:00:00+00:00",
    )
    evaluation = evaluator.evaluate(
        artifact,
        (
            _row("eval_001", "2025-02-10", label=1),
            _row("eval_002", "2025-02-11", label=0),
        ),
        evaluated_as_of="2025-03-05",
        evaluation_cutoff_at="2025-03-05T00:00:00+00:00",
    )

    assert evaluation.status == "evaluated"
    assert [row.calibrated_probability_bp for row in evaluation.rows] == [5000, 5000]
    assert evaluation.baseline_metrics["brier_bp"] == 2500
    assert evaluation.personal_challenger_metrics["brier_bp"] == 2500
    assert evaluation.baseline_metrics["row_fingerprint"] == evaluation.personal_challenger_metrics["row_fingerprint"]
    assert evaluation.natural_forward_credit is False
    assert evaluation.adoption_confidence_status == "adoption_not_evaluable"
    assert evaluation.evaluation_cutoff_at == "2025-03-05T00:00:00.000000+00:00"
    assert evaluation.decision == "retain_population"


def test_fit_eval_overlap_and_purge_embargo_are_hard_boundaries() -> None:
    evaluator = PersonalizationCalibrationEvaluator()
    artifact = evaluator.fit(
        (_row("fit_001", "2025-01-01", label=1),),
        fit_as_of="2025-01-31",
        policy=_policy(embargo_days=5),
    )
    with pytest.raises(PersonalizationCalibrationError, match="overlap"):
        evaluator.evaluate(
            artifact,
            (_row("fit_001", "2025-02-10", label=1),),
            evaluated_as_of="2025-03-05",
        )
    with pytest.raises(PersonalizationCalibrationError, match="purged"):
        evaluator.evaluate(
            artifact,
            (_row("eval_inside_purge", "2025-02-05", label=1),),
            evaluated_as_of="2025-03-05",
        )


def test_missing_population_probability_has_no_rank_or_probability_fallback() -> None:
    evaluator = PersonalizationCalibrationEvaluator()
    artifact = evaluator.fit(
        (_row("fit_001", "2025-01-01", label=1),),
        fit_as_of="2025-01-31",
        policy=_policy(),
    )
    evaluation = evaluator.evaluate(
        artifact,
        (_row("eval_missing", "2025-02-10", probability=None, label=1),),
        evaluated_as_of="2025-03-05",
        evaluation_cutoff_at="2025-03-05T00:00:00+00:00",
    )
    row = evaluation.rows[0]
    assert row.status == "population_probability_unavailable"
    assert row.calibrated_probability_bp is None
    assert evaluation.population_probability_missing_count == 1
    assert evaluation.baseline_metrics["sample_count"] == 0


def test_pending_matured_missing_invalid_and_undelivered_are_distinct() -> None:
    evaluator = PersonalizationCalibrationEvaluator()
    artifact = evaluator.fit(
        (_row("fit_001", "2025-01-01", label=1),),
        fit_as_of="2025-01-31",
        policy=_policy(),
    )
    rows = (
        _row("pending", "2025-02-10", label_available_date="2025-04-01", label=1),
        _row("matured_missing", "2025-02-11", label=None, outcome_status="matured_missing"),
        _row("invalid", "2025-02-12", label=1, outcome_status="invalid"),
        _row("undelivered", "2025-02-13", label=1, delivery_status="persisted"),
        _row("late", "2025-02-14", label=1, late_delivery=True),
    )
    evaluation = evaluator.evaluate(
        artifact,
        rows,
        evaluated_as_of="2025-03-05",
        evaluation_cutoff_at="2025-03-05T00:00:00+00:00",
    )

    statuses = {row.prediction_id: row.status for row in evaluation.rows}
    assert statuses == {
        "pending": "pending_maturity",
        "matured_missing": "matured_missing",
        "invalid": "invalid",
        "undelivered": "not_delivered",
        "late": "late_delivery_no_credit",
    }
    assert evaluation.baseline_metrics["sample_count"] == 0
    assert evaluation.natural_forward_credit is False


def test_wilson_interval_is_descriptive_only() -> None:
    interval = wilson_interval_bp(1, 2)
    assert interval is not None
    assert interval[0] < 5000 < interval[1]


def test_evaluation_exact_retries_are_deduplicated_and_aliases_cannot_bypass_overlap() -> None:
    evaluator = PersonalizationCalibrationEvaluator()
    policy = _policy()
    artifact = evaluator.fit(
        (_row("fit_prediction", "2025-01-01", label=1, symbol="2330"),),
        fit_as_of="2025-01-31",
        policy=policy,
    )
    evaluation_row = _row("eval_prediction", "2025-02-10", label=1)
    evaluation = evaluator.evaluate(
        artifact,
        (evaluation_row, evaluation_row),
        evaluated_as_of="2025-03-05",
        evaluation_cutoff_at="2025-03-05T00:00:00+00:00",
    )
    assert len(evaluation.rows) == 1
    assert evaluation.baseline_metrics["sample_count"] == 1

    fit_alias = _row("shared_prediction", "2025-01-02", row_id="fit_alias")
    alias_artifact = evaluator.fit(
        (fit_alias,),
        fit_as_of="2025-01-31",
        policy=policy,
    )
    eval_alias = _row("shared_prediction", "2025-02-10", row_id="eval_alias")
    with pytest.raises(PersonalizationCalibrationError, match="overlap"):
        evaluator.evaluate(
            alias_artifact,
            (eval_alias,),
            evaluated_as_of="2025-03-05",
            evaluation_cutoff_at="2025-03-05T00:00:00+00:00",
        )

    with pytest.raises(PersonalizationCalibrationError, match="duplicate identity conflict"):
        evaluator.evaluate(
            artifact,
            (evaluation_row, replace(evaluation_row, label=0)),
            evaluated_as_of="2025-03-05",
            evaluation_cutoff_at="2025-03-05T00:00:00+00:00",
        )


def test_scope_and_cohort_contract_mismatches_are_not_evaluated() -> None:
    evaluator = PersonalizationCalibrationEvaluator()
    policy = _policy()
    artifact = evaluator.fit(
        (_row("fit_001", "2025-01-01", label=1),),
        fit_as_of="2025-01-31",
        policy=policy,
    )
    base = _row("eval_001", "2025-02-10", label=1)
    for changed in (
        replace(base, scope_id="scope_other"),
        replace(base, universe_policy_hash="sha256:" + ("9" * 64)),
        replace(base, label_contract_id="label_other"),
        replace(base, outcome_tier="historical_replay"),
        replace(base, model_id="model_other"),
        replace(base, source_id="source_other"),
    ):
        with pytest.raises(PersonalizationCalibrationError, match="cohort contract mismatch"):
            evaluator.evaluate(
                artifact,
                (changed,),
                evaluated_as_of="2025-03-05",
                evaluation_cutoff_at="2025-03-05T00:00:00+00:00",
            )


def test_cutoff_is_a_real_outcome_availability_boundary() -> None:
    evaluator = PersonalizationCalibrationEvaluator()
    artifact = evaluator.fit(
        (_row("fit_001", "2025-01-01", label=1),),
        fit_as_of="2025-01-31",
        policy=_policy(),
    )
    late_label = _row(
        "eval_late_label",
        "2025-02-10",
        label_available_date="2025-03-02",
        label=1,
    )
    evaluation = evaluator.evaluate(
        artifact,
        (late_label,),
        evaluated_as_of="2025-03-05",
        evaluation_cutoff_at="2025-02-11T00:00:00+00:00",
    )
    assert evaluation.rows[0].status == "pending_maturity"
    assert evaluation.baseline_metrics["sample_count"] == 0

    with pytest.raises(PersonalizationCalibrationError, match="cannot follow"):
        evaluator.evaluate(
            artifact,
            (late_label,),
            evaluated_as_of="2025-03-05",
            evaluation_cutoff_at="2025-03-06T00:00:00+00:00",
        )


def test_fit_artifact_is_deep_immutable_and_revalidates_derived_hashes() -> None:
    evaluator = PersonalizationCalibrationEvaluator()
    artifact = evaluator.fit(
        (_row("fit_001", "2025-01-01", label=1),),
        fit_as_of="2025-01-31",
        policy=_policy(),
    )
    with pytest.raises(TypeError):
        artifact.personal_bin_positive_count["0:1999"] = 99  # type: ignore[index]
    tampered = dict(artifact.personal_bin_positive_count)
    tampered["0:1999"] = 99
    with pytest.raises(PersonalizationCalibrationError, match="positive count|overlay hash"):
        replace(artifact, personal_bin_positive_count=tampered)


def test_fit_requires_recorded_outcome_clock_before_accepting_ready_label() -> None:
    evaluator = PersonalizationCalibrationEvaluator()
    with pytest.raises(PersonalizationCalibrationError, match="outcome_recorded_at"):
        evaluator.fit(
            (replace(_row("fit_missing_recorded", "2025-01-01"), outcome_recorded_at=None),),
            fit_as_of="2025-01-31",
            policy=_policy(),
            created_at="2025-02-01T00:00:00+00:00",
        )


def test_fit_artifact_created_at_cannot_precede_fit_cutoff_or_dependencies() -> None:
    evaluator = PersonalizationCalibrationEvaluator()
    with pytest.raises(PersonalizationCalibrationError, match="created_at"):
        evaluator.fit(
            (_row("fit_created_too_early", "2025-01-01"),),
            fit_as_of="2025-01-31",
            policy=_policy(),
            created_at="2025-01-02T00:00:00+00:00",
        )
    dependency_row = _row(
        "fit_dependency_late",
        "2025-01-01",
        label_available_date="2025-01-31",
    )
    dependency_row = replace(
        dependency_row,
        label_available_at="2025-01-31T12:00:00+00:00",
        outcome_recorded_at="2025-01-31T12:00:00+00:00",
    )
    with pytest.raises(PersonalizationCalibrationError, match="fit dependency"):
        evaluator.fit(
            (dependency_row,),
            fit_as_of="2025-01-31",
            policy=_policy(),
            created_at="2025-01-31T09:00:00+00:00",
        )
