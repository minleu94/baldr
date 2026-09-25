from dataclasses import dataclass
import json
from pathlib import Path
import hashlib
from typing import Any

import joblib
import numpy as np

from data_module.portfolio_ml_out_of_core_store import (
    LABEL_DTYPE,
    LABEL_FIELDS,
    MASK_DTYPE,
    ROW_REF_DTYPE,
    TARGET_DTYPE,
    TARGET_FIELDS,
    VALUE_DTYPE,
)
from ml_module.model_artifact_loader import (
    SafeShadowModelArtifactLoader,
    ArtifactCompatibilityExpectation,
)
from ml_module.model_artifact_manifest import ModelArtifactManifest, FeatureSchema
from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY
from ml_module.historical_training_service import HistoricalTrainingSample, _matrix


class DummyModel:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


@dataclass(frozen=True)
class ControlledFixtureModel:
    model_id: str
    dataset_id: str
    model_family: str
    shadow_only: bool = True
    production_eligible: bool = False
    production_action_allowed: bool = False


def _create_valid_manifest(artifact_hash: str) -> dict:
    return ModelArtifactManifest.create(
        model_id="model_1",
        dataset_id="ds_1",
        created_run_id="run_1",
        created_at="2026-09-01T00:00:00Z",
        model_family="LGBMRegressor",
        feature_registry_hash="sha256:" + "a" * 64,
        label_registry_hash="sha256:" + "b" * 64,
        feature_schema=(("A", "float32", "ratio"), ("B", "float32", "bp")),
        training_as_of="2026-09-01",
        hyperparameters_hash="sha256:" + "c" * 64,
        library_versions={"scikit-learn": "1.3.0", "lightgbm": "4.0.0"},
        serialization_format="joblib",
        artifact_filename="model.bin",
        artifact_hash=artifact_hash,
    ).to_dict()


def test_safe_loader_accepts_controlled_joblib_fixture_after_contract_checks(tmp_path):
    root = tmp_path / "controlled_shadow_fixture"
    root.mkdir()
    artifact_path = root / "fixture.joblib"
    fixture_model = ControlledFixtureModel(
        model_id="controlled_model",
        dataset_id="controlled_dataset",
        model_family="FixtureRegressor",
    )
    joblib.dump(fixture_model, artifact_path)
    artifact_hash = "sha256:" + hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    label_registry_hash = "sha256:" + "b" * 64
    feature_schema = CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_schema
    installed_library_versions = {"joblib": joblib.__version__}

    manifest = ModelArtifactManifest.create(
        model_id=fixture_model.model_id,
        dataset_id=fixture_model.dataset_id,
        created_run_id="controlled_fixture_run",
        created_at="2026-09-01T00:00:00Z",
        model_family=fixture_model.model_family,
        feature_registry_hash=CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
        label_registry_hash=label_registry_hash,
        feature_schema=feature_schema,
        training_as_of="2026-09-01",
        hyperparameters_hash="sha256:" + "c" * 64,
        library_versions=installed_library_versions,
        serialization_format="joblib",
        artifact_filename=artifact_path.name,
        artifact_hash=artifact_hash,
    )
    (root / "manifest.json").write_text(
        json.dumps(manifest.to_dict(), sort_keys=True), encoding="utf-8"
    )

    loader = SafeShadowModelArtifactLoader(data_root=tmp_path / "fake_data_root")
    expectation = ArtifactCompatibilityExpectation(
        expected_model_family=fixture_model.model_family,
        expected_feature_registry_hash=CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash,
        expected_label_registry_hash=label_registry_hash,
        expected_feature_schema=feature_schema,
        installed_library_versions=installed_library_versions,
    )

    result = loader.load(root, expectation=expectation)

    assert result.status == "shadow_model_ready"
    assert result.model == fixture_model
    assert type(result.model) is ControlledFixtureModel
    assert (
        f"{type(result.model).__module__}.{type(result.model).__qualname__}"
        == f"{__name__}.ControlledFixtureModel"
    )


def test_safe_loader_accepts_injected_model_after_contract_checks(tmp_path):
    root = tmp_path / "artifact"
    root.mkdir()

    artifact_path = root / "model.bin"
    artifact_path.write_bytes(b"dummy_bytes")

    digest = hashlib.sha256(b"dummy_bytes").hexdigest()
    artifact_hash = f"sha256:{digest}"

    manifest_dict = _create_valid_manifest(artifact_hash)

    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest_dict), encoding="utf-8")

    dummy_model = DummyModel(
        model_id="model_1",
        dataset_id="ds_1",
        model_family="LGBMRegressor",
        shadow_only=True,
        production_eligible=False,
        production_action_allowed=False
    )

    loader = SafeShadowModelArtifactLoader(
        data_root=tmp_path / "fake_data_root",
        deserializer=lambda path: dummy_model
    )

    expectation = ArtifactCompatibilityExpectation(
        expected_model_family="LGBMRegressor",
        expected_feature_registry_hash="sha256:" + "a" * 64,
        expected_label_registry_hash="sha256:" + "b" * 64,
        expected_feature_schema=(
            ("A", "float32", "ratio"),
            ("B", "float32", "bp")
        ),
        installed_library_versions={"scikit-learn": "1.3.0", "lightgbm": "4.0.0"}
    )

    result = loader.load(root, expectation=expectation)
    assert result.status == "shadow_model_ready"
    assert result.model is dummy_model


def test_safe_loader_rejects_missing_manifest(tmp_path):
    root = tmp_path / "artifact2"
    root.mkdir()

    loader = SafeShadowModelArtifactLoader(
        data_root=tmp_path / "fake_data_root",
        deserializer=lambda path: DummyModel()
    )

    expectation = ArtifactCompatibilityExpectation(
        expected_model_family="M",
        expected_feature_registry_hash="sha256:" + "a" * 64,
        expected_label_registry_hash="sha256:" + "a" * 64,
        expected_feature_schema=(("A", "f", "u"),),
        installed_library_versions={}
    )

    result = loader.load(root, expectation=expectation)
    assert result.status == "rule_only_fallback"
    assert "manifest_missing" in result.blockers


def test_safe_loader_rejects_hash_mismatch(tmp_path):
    root = tmp_path / "artifact3"
    root.mkdir()

    artifact_path = root / "model.bin"
    artifact_path.write_bytes(b"tampered")

    # 刻意提供不相符的 artifact hash。
    manifest_dict = _create_valid_manifest("sha256:" + "a" * 64)

    (root / "manifest.json").write_text(json.dumps(manifest_dict))

    loader = SafeShadowModelArtifactLoader(
        data_root=tmp_path / "fake_data_root",
        deserializer=lambda path: DummyModel()
    )

    expectation = ArtifactCompatibilityExpectation(
        expected_model_family="LGBMRegressor",
        expected_feature_registry_hash="sha256:" + "a" * 64,
        expected_label_registry_hash="sha256:" + "b" * 64,
        expected_feature_schema=(
            ("A", "float32", "ratio"),
            ("B", "float32", "bp")
        ),
        installed_library_versions={"scikit-learn": "1.3.0", "lightgbm": "4.0.0"}
    )

    result = loader.load(root, expectation=expectation)
    assert result.status == "rule_only_fallback"
    assert "artifact_hash_mismatch" in result.blockers


def test_safe_loader_rejects_schema_mismatch(tmp_path):
    root = tmp_path / "artifact4"
    root.mkdir()

    artifact_path = root / "model.bin"
    artifact_path.write_bytes(b"dummy_bytes")
    digest = hashlib.sha256(b"dummy_bytes").hexdigest()
    artifact_hash = f"sha256:{digest}"

    manifest_dict = _create_valid_manifest(artifact_hash)
    (root / "manifest.json").write_text(json.dumps(manifest_dict))

    loader = SafeShadowModelArtifactLoader(
        data_root=tmp_path / "fake_data_root",
        deserializer=lambda path: DummyModel()
    )

    # 預期 family 為 M2，但 manifest 記錄的是 LGBMRegressor。
    expectation = ArtifactCompatibilityExpectation(
        expected_model_family="M2",
        expected_feature_registry_hash="sha256:" + "a" * 64,
        expected_label_registry_hash="sha256:" + "b" * 64,
        expected_feature_schema=(
            ("A", "float32", "ratio"),
            ("B", "float32", "bp")
        ),
        installed_library_versions={"scikit-learn": "1.3.0", "lightgbm": "4.0.0"}
    )

    result = loader.load(root, expectation=expectation)
    assert result.status == "rule_only_fallback"
    assert "model_family_mismatch" in result.blockers


def test_historical_feature_registry_preserves_canonical_20_feature_abi():
    expected_ids = (
        "stock_return_1d_bp",
        "stock_return_5d_bp",
        "stock_return_20d_bp",
        "stock_return_60d_bp",
        "trailing_volatility_20d_bp",
        "high_low_range_20d_bp",
        "close_to_ma_5d_bp",
        "close_to_ma_20d_bp",
        "close_to_ma_60d_bp",
        "rsi_normalized_bp",
        "adx_normalized_bp",
        "macd_normalized_bp",
        "volume_ratio_5d_bp",
        "volume_ratio_20d_bp",
        "turnover_amount_minor",
        "market_return_5d_bp",
        "market_return_20d_bp",
        "market_return_60d_bp",
        "stock_minus_market_20d_bp",
        "industry_relative_return_20d_bp",
    )
    specs = CORE_LONG_HISTORY_FEATURE_REGISTRY.specs

    assert CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_id == "core-long-history-features-v1"
    assert tuple(spec.feature_id for spec in specs) == expected_ids
    assert tuple(spec.dtype for spec in specs) == ("int",) * 20
    assert tuple(spec.unit for spec in specs) == tuple(
        "minor_currency_unit" if feature_id == "turnover_amount_minor" else "bp"
        for feature_id in expected_ids
    )
    assert tuple(spec.missing_policy for spec in specs) == ("missing_is_not_zero",) * 20
    assert tuple(spec.availability_policy for spec in specs) == (
        "feature_as_of_before_decision",
    ) * 20


def test_historical_training_matrix_keeps_missing_distinct_from_zero():
    feature_values = (None, 0, *range(2, 20))
    row = HistoricalTrainingSample(
        row_id="historical-fixture-row",
        decision_date="2024-06-03",
        label_end_date="2024-06-10",
        label_available_date="2024-06-11",
        feature_values=feature_values,
        return_target_bp=0,
        downside_target=0,
        rule_score_bp=0,
    )

    matrix = _matrix((row,))

    assert matrix.shape == (1, 20)
    assert matrix.dtype == np.dtype(float)
    assert np.isnan(matrix[0, 0])
    assert matrix[0, 1] == 0.0


def test_out_of_core_store_dtype_and_field_order_contract():
    assert VALUE_DTYPE == np.dtype("<i8")
    assert MASK_DTYPE == np.dtype("u1")
    assert TARGET_DTYPE == np.dtype("<i4")
    assert LABEL_DTYPE == np.dtype("<i4")
    assert ROW_REF_DTYPE == np.dtype("<i8")
    assert TARGET_FIELDS == (
        "target_weight_bp",
        "delta_weight_bp",
        "risk_contribution_bp",
        "risky_budget_bp",
        "cash_bp",
        "rebalance_worthwhile",
    )
    assert LABEL_FIELDS == (
        "benchmark_excess_return_bp",
        "sector_excess_return_bp",
        "downside_observed",
        "mae_bp",
        "mfe_bp",
        "realized_volatility_bp",
        "max_drawdown_bp",
        "tail_loss_bp",
        "fill_feasible_observed",
    )
