from __future__ import annotations

from dataclasses import replace

from app_module.evidence_event_dtos import EvidenceEventType
from app_module.recommendation_calibration import (
    RecommendationCalibrationConfig,
    _build_folds,
    build_recommendation_calibration_dataset,
    evaluate_recommendation_calibration,
    sample_evidence_rows,
    sample_recommendation_calibration_dataset,
)


def test_sample_slice_measures_primary_and_auxiliary_oos() -> None:
    config = RecommendationCalibrationConfig(fixed_round_trip_cost_bp=80)
    dataset = sample_recommendation_calibration_dataset(config=config)
    report = evaluate_recommendation_calibration(dataset, config=config)

    assert report["status"] == "measured_research_only"
    assert report["access_boundary"]["production_eligible"] is False
    assert report["lookahead_checks"]["test_rows_never_used_for_fit"] is True
    primary = report["oos"]["targets"]["upside_20d"]["feature_sets"]["score_percentile_v1"]
    auxiliary = report["oos"]["targets"]["upside_5d"]["feature_sets"]["score_percentile_v1"]
    assert primary["calibrated"]["status"] == "measured"
    assert auxiliary["calibrated"]["status"] == "measured"
    assert primary["calibrated"]["brier_score_bp"] is not None
    assert len(primary["calibrated"]["probability_bins"]) == config.probability_bin_count
    assert primary["calibrated"]["performance"]["benchmark_excess_bp"]["sample_count"] > 0


def test_predictions_keep_ranking_probability_action_and_evidence_separate() -> None:
    report = evaluate_recommendation_calibration(sample_recommendation_calibration_dataset())
    row = report["predictions"][0]

    assert "ranking_score_bp" in row
    assert "upside_probability_bp" in row
    assert "after_cost_profit_probability_bp" in row
    assert row["action_suitability"] in {
        "research_candidate",
        "research_watch",
        "research_review",
        "not_evaluable",
    }
    assert row["evidence_confidence"] in {"observed", "degraded", "low"}
    assert row["ranking_score_bp"] != row["upside_probability_bp"] or row["ranking_score_bp"] is None


def test_walk_forward_purges_matured_labels_before_calibration_and_test() -> None:
    config = RecommendationCalibrationConfig()
    dataset = sample_recommendation_calibration_dataset(config=config)
    folds = _build_folds(dataset.observations, config)

    assert folds
    for fold in folds:
        assert all(row.decision_date < fold.calibration_start_date for row in fold.train_rows)
        assert all(row.label_end_date < fold.calibration_start_date for row in fold.train_rows)
        assert all(row.label_end_date < fold.test_start_date for row in fold.calibration_rows)
        assert all(row.decision_date >= fold.test_start_date for row in fold.test_rows)
        assert {
            row.row_id for row in fold.train_rows
        }.isdisjoint(row.row_id for row in fold.test_rows)


def test_future_dated_event_input_is_fail_closed_without_backfill() -> None:
    events, outcomes = sample_evidence_rows()
    original = events[0]
    future_event = replace(
        original,
        as_of_date="2099-01-01",
        event_type=EvidenceEventType.RECOMMENDATION_INCLUDED,
    )
    dataset = build_recommendation_calibration_dataset(
        (future_event,),
        outcomes,
        source_mode="test_only",
    )

    assert dataset.observations == ()
    assert dataset.excluded_row_count == 0
    assert any(item.startswith("event_as_of_date_after_decision:") for item in dataset.diagnostics)


def test_missing_liquidity_cost_is_not_zero_filled_for_after_cost_target() -> None:
    events, outcomes = sample_evidence_rows()
    missing_cost_outcome = replace(outcomes[0], liquidity_cost_bp=None)
    dataset = build_recommendation_calibration_dataset(
        events[:1],
        (missing_cost_outcome, outcomes[1]),
        source_mode="test_only",
    )

    assert dataset.observations
    assert dataset.observations[0].liquidity_cost_bp is None
    assert dataset.observations[0].evidence_confidence == "degraded"
    report = evaluate_recommendation_calibration(
        dataset,
        config=RecommendationCalibrationConfig(
            minimum_train_dates=1,
            calibration_date_count=1,
            test_date_count=1,
            purge_trading_days=1,
            minimum_calibration_samples=1,
            minimum_test_samples=1,
        ),
    )
    assert "fixed_round_trip_plus_observed_liquidity_v1" in report["contract"]["cost_definition"]["model_id"]

