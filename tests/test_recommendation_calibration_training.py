from __future__ import annotations

from datetime import date, timedelta
from dataclasses import replace
import json
from pathlib import Path

from ml_module.model_artifact_loader import ArtifactCompatibilityExpectation, SafeShadowModelArtifactLoader
from ml_module.recommendation_calibration_training import (
    RECOMMENDATION_HORIZON_TRADING_DAYS,
    RecommendationCalibrationSample,
    RecommendationCalibrationTrainingConfig,
    RecommendationCalibrationTrainingService,
    recommendation_label_registry_hash,
)


FEATURE_NAMES = ("momentum_bp", "volume_ratio_bp")
FEATURE_SCHEMA = (("momentum_bp", "int", "bp"), ("volume_ratio_bp", "int", "bp"))
FEATURE_REGISTRY_HASH = "sha256:" + "1" * 64
DATASET_HASH = "sha256:" + "2" * 64


def _samples() -> tuple[RecommendationCalibrationSample, ...]:
    rows: list[RecommendationCalibrationSample] = []
    start = date(2026, 1, 2)
    for day_index in range(110):
        decision = start + timedelta(days=day_index)
        label_end = decision + timedelta(days=20)
        for symbol_index, symbol in enumerate(("1101", "2330")):
            momentum = ((day_index % 6) - 2) * 1000 + symbol_index * 170
            volume = 1000 + (day_index % 7) * 100
            stock_return = momentum + symbol_index * 120
            # Make the current rule deliberately less informative than the feature model.
            rule_probability = 5000 + (symbol_index * 400) + ((day_index % 5) - 2) * 80
            rows.append(
                RecommendationCalibrationSample.from_forward_return(
                    row_id=f"{decision.isoformat()}-{symbol}",
                    symbol=symbol,
                    decision_date=decision.isoformat(),
                    feature_as_of_date=(decision - timedelta(days=1)).isoformat(),
                    feature_available_date=(decision - timedelta(days=1)).isoformat(),
                    label_end_date=label_end.isoformat(),
                    label_available_date=label_end.isoformat(),
                    feature_values=(momentum, volume),
                    stock_return_bp=stock_return,
                    benchmark_return_bp=100 if day_index % 3 == 0 else -100,
                    fixed_round_trip_cost_bp=50,
                    observed_liquidity_cost_bp=20,
                    rule_probability_bp=rule_probability,
                    rule_after_cost_probability_bp=rule_probability,
                )
            )
    return tuple(rows)


def test_candidate_persists_full_runnable_artifact_and_absolute_targets(tmp_path: Path) -> None:
    result = RecommendationCalibrationTrainingService().fit(
        dataset_id="recommendation-dataset-v1",
        dataset_hash=DATASET_HASH,
        samples=_samples(),
        feature_names=FEATURE_NAMES,
        feature_schema=FEATURE_SCHEMA,
        feature_registry_hash=FEATURE_REGISTRY_HASH,
        training_as_of="2026-12-31",
        fixed_round_trip_cost_bp=50,
        config=RecommendationCalibrationTrainingConfig(
            minimum_calibration_samples=10,
            minimum_train_dates=30,
            test_date_count=5,
            purge_trading_days=20,
        ),
    )

    root = result.persist(tmp_path / "candidate")
    payload = json.loads((root / "candidate.json").read_text(encoding="utf-8"))
    assert payload["target_definitions"]["upside"].startswith("absolute forward stock return")
    assert payload["target_definitions"]["after_cost_profit"].startswith("absolute forward stock return")
    assert payload["benchmark_role"].endswith("not a target")
    assert payload["horizon_trading_days"] == RECOMMENDATION_HORIZON_TRADING_DAYS
    assert payload["training_as_of"]
    assert payload["feature_schema"] == [list(item) for item in FEATURE_SCHEMA]
    assert payload["artifact_hash"] == result.artifact_hash
    assert result.model.shadow_only is True
    assert result.manifest.production_action_allowed is False

    loaded = SafeShadowModelArtifactLoader(data_root=tmp_path / "formal-data").load(
        root,
        expectation=ArtifactCompatibilityExpectation(
            expected_model_family="recommendation_absolute_calibration_v1",
            expected_feature_registry_hash=FEATURE_REGISTRY_HASH,
            expected_label_registry_hash=recommendation_label_registry_hash(),
            expected_feature_schema=FEATURE_SCHEMA,
            installed_library_versions={
                "joblib": __import__("joblib").__version__,
                "numpy": __import__("numpy").__version__,
                "scikit-learn": __import__("sklearn").__version__,
            },
        ),
    )
    assert loaded.status == "shadow_model_ready"
    assert loaded.model is not None
    prediction = loaded.model.predict((450, 1300))
    assert 0 <= prediction.calibrated_probability_bp <= 10_000
    assert prediction.after_cost_profit_probability_bp is not None
    assert prediction.model_id == result.candidate_id


def test_sample_rejects_benchmark_relative_target_substitution() -> None:
    try:
        RecommendationCalibrationSample(
            row_id="bad",
            symbol="1101",
            decision_date="2026-01-02",
            feature_as_of_date="2026-01-01",
            feature_available_date="2026-01-01",
            label_end_date="2026-01-22",
            label_available_date="2026-01-22",
            feature_values=(1, 2),
            stock_return_bp=-10,
            benchmark_return_bp=-1000,
            fixed_round_trip_cost_bp=50,
            observed_liquidity_cost_bp=20,
            rule_probability_bp=5000,
            upside_label=1,
            after_cost_profit_label=0,
        )
    except ValueError as exc:
        assert "absolute stock return" in str(exc)
    else:
        raise AssertionError("benchmark-relative target must not be accepted")


def test_after_cost_training_uses_independent_null_baseline_and_missing_cost_stays_unavailable() -> None:
    observed = RecommendationCalibrationSample.from_forward_return(
        row_id="observed-cost",
        symbol="1101",
        decision_date="2026-01-02",
        feature_as_of_date="2026-01-01",
        feature_available_date="2026-01-01",
        label_end_date="2026-01-22",
        label_available_date="2026-01-22",
        feature_values=(1, 2),
        stock_return_bp=200,
        benchmark_return_bp=0,
        fixed_round_trip_cost_bp=50,
        observed_liquidity_cost_bp=20,
        rule_probability_bp=5000,
    )
    assert observed.after_cost_profit_label == 1
    assert observed.rule_after_cost_probability_bp == 5000
    assert observed.rule_after_cost_baseline_id == "after_cost_null_benchmark_50pct_v1"

    no_cost = replace(
        observed,
        row_id="missing-cost",
        observed_liquidity_cost_bp=None,
        after_cost_profit_label=None,
        rule_after_cost_probability_bp=None,
        rule_after_cost_baseline_id=None,
    )
    assert no_cost.after_cost_profit_label is None
    assert no_cost.rule_after_cost_probability_bp is None
    assert no_cost.rule_after_cost_baseline_id is None
