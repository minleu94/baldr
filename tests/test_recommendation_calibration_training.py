from __future__ import annotations

from datetime import date, timedelta
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys

import pytest

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


def test_calibration_error_reexport_preserves_class_identity_and_legacy_except() -> None:
    from artifact_contracts.recommendation_calibration_errors import InvalidCalibrationOutputError
    from ml_module.recommendation_calibration_training import InvalidCalibrationOutputError as LegacyError

    assert LegacyError is InvalidCalibrationOutputError
    assert InvalidCalibrationOutputError.__bases__ == (ValueError,)
    with pytest.raises(LegacyError, match="invalid output"):
        raise InvalidCalibrationOutputError("invalid output")
    with pytest.raises(InvalidCalibrationOutputError, match="legacy output"):
        raise LegacyError("legacy output")


@pytest.mark.parametrize("output", ("nan", "inf", "-inf", "-0.01", "1.01"))
def test_invalid_calibrated_output_raises_neutral_and_legacy_error(output: str) -> None:
    from artifact_contracts.recommendation_calibration_errors import InvalidCalibrationOutputError
    from ml_module.probability_calibration import FittedShadowProbabilityCalibrator
    from ml_module.recommendation_calibration_training import _calibrated_bp

    class OutputEstimator:
        def predict(self, _values):
            return [float(output)]

    calibrator = FittedShadowProbabilityCalibrator(
        calibration_id="synthetic", model_id="synthetic", estimator=OutputEstimator(),
        sample_count=10, fold_count=2,
    )
    with pytest.raises(InvalidCalibrationOutputError, match="finite within 0..1"):
        _calibrated_bp(calibrator, 0.5)


@pytest.mark.parametrize("output,expected", (("0", 0), ("0.5", 5000), ("0.1234", 1234), ("1", 10000)))
def test_valid_calibrated_output_preserves_integer_basis_points(output: str, expected: int) -> None:
    from ml_module.probability_calibration import FittedShadowProbabilityCalibrator
    from ml_module.recommendation_calibration_training import _calibrated_bp

    class OutputEstimator:
        def predict(self, _values):
            return [float(output)]

    calibrator = FittedShadowProbabilityCalibrator(
        calibration_id="synthetic", model_id="synthetic", estimator=OutputEstimator(),
        sample_count=10, fold_count=2,
    )
    result = _calibrated_bp(calibrator, 0.5)
    assert type(result) is int
    assert result == expected


def test_neutral_calibration_error_cold_import_has_no_data_io_or_training() -> None:
    code = r'''
import importlib.abc
import os
import sys

blocked = ("ml_module", "app_module", "joblib", "sklearn", "numpy")
import_dirs = {os.getcwd(), os.path.join(os.getcwd(), "artifact_contracts")}
class RejectTraining(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in blocked:
            raise RuntimeError("blocked training dependency:" + fullname)
sys.meta_path.insert(0, RejectTraining())
data_io = []
def audit(event, args):
    if event == "open":
        path, mode, flags = args
        if not isinstance(path, str) or not path.endswith((".py", ".pyc")) or flags & 3:
            data_io.append(event)
            raise AssertionError("data I/O during contract import")
    elif event == "os.listdir" and os.path.abspath(args[0]) in import_dirs:
        # Python 的來源模組尋找可列來源目錄，不允許列資料目錄。
        return
    elif event.startswith(("sqlite3.", "socket.", "subprocess.")) or event in ("os.mkdir", "os.remove", "os.rename", "os.listdir", "os.scandir"):
        data_io.append(event)
        raise AssertionError("data I/O during contract import")
sys.addaudithook(audit)
from artifact_contracts.recommendation_calibration_errors import InvalidCalibrationOutputError
assert InvalidCalibrationOutputError.__bases__ == (ValueError,)
assert str(InvalidCalibrationOutputError("synthetic")) == "synthetic"
assert not data_io
assert not any(name.split(".")[0] in blocked for name in sys.modules)
try:
    __import__("ml_module.recommendation_calibration_training")
except RuntimeError as exc:
    assert "blocked training dependency" in str(exc)
else:
    raise AssertionError("training import negative control did not reject")
print("cold neutral import: zero data I/O; training negative control rejected")
'''
    result = subprocess.run(
        [sys.executable, "-B", "-c", code],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "zero data I/O" in result.stdout
