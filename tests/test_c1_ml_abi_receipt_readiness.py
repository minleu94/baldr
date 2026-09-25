"""C1 ML-P/ML-N synthetic ABI and immutable receipt readiness checks.

All produced artifacts live below pytest's ``tmp_path``.  These checks exercise
the OOC public builder, artifact public loader, recommendation receipt reader,
and U4 query view.  They do not invoke inference, scheduled jobs, or DATA_ROOT.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import gzip
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from typing import Any, Mapping

import joblib
import numpy as np
import pytest

from app_module.recommendation.contracts import (
    Context,
    ExecutionStatus,
    MLAvailability,
    MLAvailabilityStatus,
    MLReceiptBinding,
    RecommendationExecution,
    ReferenceKind,
    Request,
    VersionReference,
)
from app_module.recommendation.persistence import RecommendationExecutionPersistence
from app_module.recommendation.queries import RecommendationExecutionQueries
from data_module.contracts.market import SourceRef
from data_module.portfolio_ml_out_of_core_store import (
    PortfolioMLOutOfCoreStoreBuilder,
    PortfolioMLOutOfCoreStoreRequest,
)
from data_module.result_artifact_store import ResultArtifactStore
from decision_module.recommendation.contracts import (
    DecisionBatch,
    RecommendationItem,
    UniverseReference,
)
from ml_module.allocation_contracts import (
    AllocationTargets,
    AllocationWeightContract,
    CausalPortfolioState,
    PITFeatureValue,
    PortfolioMLDatasetRow,
)
from ml_module.allocation_training_service import AllocationHorizonLabel, AllocationTrainingSample
from ml_module.model_artifact_loader import (
    ArtifactCompatibilityExpectation,
    SafeShadowModelArtifactLoader,
)
from ml_module.model_artifact_manifest import ModelArtifactManifest
from ml_module.recommendation_inference_provenance import (
    RecommendationProvenanceError,
    build_inference_projection_receipt,
    build_inference_provenance,
    build_training_provenance,
    persist_inference_projection_receipt,
    read_inference_projection_receipt,
    validate_provenance_compatibility,
)
from ml_module.recommendation_probability_transform import PROBABILITY_TRANSFORM_ID


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "c1_consumer_readiness" / "ml_abi_manifest.json"
FIXTURE_BYTES = FIXTURE_PATH.read_bytes()
FIXTURE: dict[str, Any] = json.loads(FIXTURE_BYTES)
FIXTURE_SHA256 = "c143b1c545319d2e3092e5d4a23ee45d86919be0093c8b889a5866a1e86b1f05"
_ZERO = "sha256:" + "0" * 64


def _canonical_json(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _logical_hash(payload: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(payload)).hexdigest()


def _file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _synthetic_sample(row_index: int) -> AllocationTrainingSample:
    decision_day = date(2024, 1, 1) + timedelta(days=row_index)
    decision_at = f"{decision_day.isoformat()}T08:30:00+08:00"
    available_at = f"{(decision_day - timedelta(days=1)).isoformat()}T16:00:00+08:00"
    event_at = available_at
    source_hash = FIXTURE["source_identity"]["source_manifest_hash"]
    feature_values = {
        "price.momentum_bp": PITFeatureValue(
            feature_id="price.momentum_bp",
            family_id="price",
            source_id="synthetic_market",
            value_int=12_345 + row_index,
            scale=100,
            event_at=event_at,
            available_at=available_at,
            revision_id=f"price-r{row_index}",
            quality="observed",
            content_hash=_logical_hash({"feature": "price", "row": row_index}),
            observed=True,
        ),
        "risk.volatility_bp": PITFeatureValue(
            feature_id="risk.volatility_bp",
            family_id="risk",
            source_id="synthetic_market",
            value_int=None if row_index == 0 else 700 + row_index,
            scale=10_000,
            event_at=event_at,
            available_at=available_at,
            revision_id=f"risk-r{row_index}",
            quality="missing" if row_index == 0 else "observed",
            content_hash=_logical_hash({"feature": "risk", "row": row_index}),
            observed=row_index != 0,
        ),
    }
    # The input feature order intentionally differs from the declared model/store
    # schema. The producer must materialize values in the manifest's exact order.
    feature_tuple = (
        feature_values["risk.volatility_bp"],
        feature_values["price.momentum_bp"],
    )
    weights = AllocationWeightContract(positions_bp=(("2330", 10_000),), cash_bp=0)
    state = CausalPortfolioState.create(
        as_of_date=(decision_day - timedelta(days=1)).isoformat(),
        weights=weights,
        weekly_turnover_used_bp=0,
    )
    horizon_end = (decision_day + timedelta(days=5)).isoformat()
    targets = AllocationTargets(
        decision_date=decision_day.isoformat(),
        horizon_end_date=horizon_end,
        available_at=f"{(decision_day + timedelta(days=6)).isoformat()}T08:30:00+08:00",
        target_weights=weights,
        delta_weights_bp=(),
        risk_contributions_bp=(("2330", 10_000),),
        risky_budget_bp=10_000,
        cash_bp=0,
        rebalance_worthwhile=False,
    )
    row = PortfolioMLDatasetRow(
        row_id=f"synthetic-row-{row_index}",
        decision_at=decision_at,
        symbol="2330",
        features=feature_tuple,
        missing_family_ids=("risk",) if row_index == 0 else (),
        portfolio_state=state,
        dataset_identity_hash=FIXTURE["source_identity"]["dataset_identity_hash"],
        feature_registry_hash=FIXTURE["source_identity"]["feature_registry_hash"],
        source_manifest_hashes=(("synthetic_market", source_hash),),
        targets=targets,
    )
    label = AllocationHorizonLabel(
        horizon_trading_days=5,
        horizon_end_date=horizon_end,
        available_at=f"{(decision_day + timedelta(days=6)).isoformat()}T08:30:00+08:00",
        benchmark_excess_return_bp=25,
        sector_excess_return_bp=None,
        sector_excess_observed=False,
        sector_excess_missing_reason="synthetic_sector_unavailable",
        downside_observed=False,
        mae_bp=100,
        mfe_bp=120,
        realized_volatility_bp=80,
        max_drawdown_bp=60,
        tail_loss_bp=50,
        fill_feasible_observed=True,
    )
    return AllocationTrainingSample(row=row, horizon_labels=(label,))


def _folds() -> list[dict[str, Any]]:
    rows = FIXTURE["folds"]
    return [
        {
            "fold_id": item["fold_id"],
            "train_end_date": (date(2024, 1, 1) + timedelta(days=item["train_row"])).isoformat(),
            "test_start": (date(2024, 1, 1) + timedelta(days=item["test_row"])).isoformat(),
            "test_end": (date(2024, 1, 1) + timedelta(days=item["test_row"])).isoformat(),
            "purge_trading_days": 60,
            "embargo_trading_days": 5,
        }
        for item in rows
    ]


def _create_ooc_source(root: Path, *, mutation: str | None = None) -> Path:
    source_root = root / "source"
    source_root.mkdir(parents=True, exist_ok=True)
    feature_ids = list(FIXTURE["feature_order"])
    feature_packs = [{"pack_id": "price-risk", "feature_ids": feature_ids}]
    folds = _folds()
    source_hashes = [["synthetic_market", FIXTURE["source_identity"]["source_manifest_hash"]]]
    source_header = {
        "record_type": "header",
        "schema_version": "allocation-training-jsonl-v2",
        "direct_training_input": True,
        "dataset_id": FIXTURE["source_identity"]["dataset_id"],
        "dataset_identity_hash": FIXTURE["source_identity"]["dataset_identity_hash"],
        "feature_registry_hash": FIXTURE["source_identity"]["feature_registry_hash"],
        "training_as_of": "2024-01-12T08:30:00+08:00",
        "horizons": [5],
        "feature_packs": feature_packs,
        "folds": folds,
        "source_manifest_hashes": source_hashes,
        "year": 2024,
    }
    records = [_canonical_json(source_header) + b"\n"]
    for row_index in range(5):
        sample = asdict(_synthetic_sample(row_index))
        if mutation == "scale" and row_index == 0:
            for feature in sample["row"]["features"]:
                if feature["feature_id"] == "risk.volatility_bp":
                    feature["scale"] = 9_999
        elif mutation == "mask" and row_index == 0:
            for feature in sample["row"]["features"]:
                if feature["feature_id"] == "risk.volatility_bp":
                    feature["value_int"] = 0
        records.append(
            _canonical_json({"record_type": "sample", "sample": sample}) + b"\n"
        )
    uncompressed = b"".join(records)
    shard_bytes = gzip.compress(uncompressed, mtime=0)
    shard_path = source_root / "year-2024.jsonl.gz"
    shard_path.write_bytes(shard_bytes)
    manifest: dict[str, Any] = {
        "schema_version": "portfolio-ml-training-shards.v2",
        "direct_training_input": True,
        "formal_oos_allowed": False,
        "research_only": False,
        "formal_consumer_compatible": True,
        "research_shadow_included": False,
        "formal_source_only": True,
        "promotion_eligible": False,
        "dataset_id": FIXTURE["source_identity"]["dataset_id"],
        "dataset_identity_hash": FIXTURE["source_identity"]["dataset_identity_hash"],
        "feature_registry_hash": FIXTURE["source_identity"]["feature_registry_hash"],
        "training_as_of": "2024-01-12T08:30:00+08:00",
        "horizons": [5],
        "feature_packs": feature_packs,
        "feature_registry": {
            "features": [
                {"feature_id": feature["feature_id"], "scale": feature["scale"]}
                for feature in FIXTURE["features"]
            ]
        },
        "folds": folds,
        "source_manifest_hashes": source_hashes,
        "shards": [
            {
                "year": 2024,
                "path": shard_path.name,
                "sample_count": 5,
                "compressed_sha256": "sha256:" + hashlib.sha256(shard_bytes).hexdigest(),
                "content_sha256": "sha256:" + hashlib.sha256(uncompressed).hexdigest(),
            }
        ],
    }
    manifest["manifest_hash"] = _logical_hash(manifest)
    manifest_path = source_root / "training_manifest.json"
    _write_json(manifest_path, manifest)
    if mutation == "source_hash":
        # Corrupt only the temporary compressed source bytes; the declared source
        # digest remains pinned and the public builder must reject the shard.
        shard_path.write_bytes(shard_path.read_bytes() + b"tampered")
    return manifest_path


def _build_ooc(root: Path, *, mutation: str | None = None):
    source_path = _create_ooc_source(root, mutation=mutation)
    output_root = root / "new-ooc-run"
    publication = PortfolioMLOutOfCoreStoreBuilder().build(
        PortfolioMLOutOfCoreStoreRequest(
            training_manifest_path=source_path,
            output_root=output_root,
            batch_size=2,
            workers=1,
            memory_budget_mb=256,
            resume=False,
            lane="formal",
        )
    )
    return publication, output_root


def test_c1_ooc_abi_emits_ordered_scaled_masked_rows_and_fold_refs(tmp_path: Path) -> None:
    fixture_before = FIXTURE_PATH.read_bytes()
    publication, output_root = _build_ooc(tmp_path / "positive")
    manifest = json.loads(publication.manifest_path.read_text(encoding="utf-8"))
    assert manifest["feature_ids"] == FIXTURE["feature_order"]
    assert manifest["feature_scales"] == FIXTURE["feature_scales"]
    assert manifest["source_training_manifest_hash"].startswith("sha256:")
    assert manifest["source_training_manifest_file_hash"].startswith("sha256:")
    assert manifest["row_count"] == 5
    assert publication.fold_count == 4
    assert publication.run_directory.is_relative_to(tmp_path.resolve())
    assert publication.latest_manifest_path.is_relative_to(tmp_path.resolve())
    assert publication.latest_manifest_path.parent == output_root.resolve()
    pointer = json.loads(publication.latest_manifest_path.read_text(encoding="utf-8"))
    assert pointer["run_id"] == publication.run_id
    assert pointer["manifest_hash"] == publication.manifest_hash
    assert _file_hash(publication.manifest_path) == publication.manifest_file_hash

    year = manifest["years"][0]
    year_root = publication.run_directory / "year=2024"
    artifacts = {item["path"]: item for item in year["artifacts"]}
    for relative, metadata in artifacts.items():
        artifact_path = year_root / relative
        assert artifact_path.stat().st_size == metadata["byte_count"]
        assert _file_hash(artifact_path) == metadata["file_sha256"]

    values = np.fromfile(year_root / "features.values.i64", dtype="<i8").reshape(5, 2)
    masks = np.fromfile(year_root / "features.masks.u8", dtype="u1").reshape(5, 2)
    assert values.dtype == np.dtype("<i8")
    assert masks.dtype == np.dtype("u1")
    assert values[0].tolist() == [FIXTURE["features"][0]["first_row_value_int"], 0]
    assert masks[0].tolist() == [0, FIXTURE["features"][1]["first_row_mask"]]
    assert masks[1:, 1].tolist() == [0, 0, 0, 0]
    assert np.asarray(values[:, 0], dtype="<i8").tolist() == [12_345, 12_346, 12_347, 12_348, 12_349]

    with sqlite3.connect(year_root / "rows.sqlite") as connection:
        rows = connection.execute(
            "SELECT local_row_index, row_id, decision_date FROM rows ORDER BY local_row_index"
        ).fetchall()
    assert [(row[0], row[1]) for row in rows] == [
        (index, f"synthetic-row-{index}") for index in range(5)
    ]
    expected_first_ref_shape = tuple(FIXTURE["row_reference"]["shape"])
    for fold, expected in zip(manifest["folds"], FIXTURE["folds"], strict=True):
        assert fold["fold_id"] == expected["fold_id"]
        assert fold["train"]["dtype"] == FIXTURE["row_reference"]["dtype"]
        assert fold["test"]["dtype"] == FIXTURE["row_reference"]["dtype"]
        expected_train = [
            [0, index] for index in range(expected["train_row"] + 1)
        ]
        expected_test = [[0, expected["test_row"]]]
        expected_train_shape = [len(expected_train), 2]
        expected_test_shape = [len(expected_test), 2]
        assert fold["train"]["row_count"] == len(expected_train)
        assert fold["test"]["row_count"] == len(expected_test)
        assert fold["train"]["shape"] == expected_train_shape
        assert fold["test"]["shape"] == expected_test_shape
        train = np.fromfile(
            publication.run_directory / "folds" / fold["train"]["path"],
            dtype="<i8",
        ).reshape(fold["train"]["row_count"], 2)
        test = np.fromfile(
            publication.run_directory / "folds" / fold["test"]["path"],
            dtype="<i8",
        ).reshape(fold["test"]["row_count"], 2)
        assert train.shape == tuple(expected_train_shape)
        assert test.shape == tuple(expected_test_shape)
        assert train.tolist() == expected_train
        assert test.tolist() == expected_test
        if expected["fold_id"] == FIXTURE["folds"][0]["fold_id"]:
            assert train[:1].shape == expected_first_ref_shape
            assert train[0].tolist() == FIXTURE["row_reference"]["first_row"]
        assert _file_hash(publication.run_directory / "folds" / fold["train"]["path"]) == fold["train"]["file_sha256"]
        assert _file_hash(publication.run_directory / "folds" / fold["test"]["path"]) == fold["test"]["file_sha256"]
    assert FIXTURE_PATH.read_bytes() == fixture_before


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("scale", "feature scale drift"),
        ("mask", "unobserved feature value_int must be missing"),
        ("source_hash", "source shard compressed hash mismatch"),
    ),
)
def test_c1_ooc_abi_rejects_scale_mask_and_source_hash_mutations(
    tmp_path: Path, mutation: str, message: str
) -> None:
    with pytest.raises((ValueError, TypeError), match=message):
        _build_ooc(tmp_path / mutation, mutation=mutation)
    assert not (tmp_path / mutation / "new-ooc-run" / "latest_manifest.json").exists()


@dataclass(frozen=True)
class _SyntheticShadowModel:
    model_id: str
    dataset_id: str
    model_family: str
    shadow_only: bool = True
    production_eligible: bool = False
    production_action_allowed: bool = False


def _runtime_libraries() -> dict[str, str]:
    return {name: importlib.metadata.version(name) for name in FIXTURE["model_artifact"]["library_names"]}


def _write_model_package(
    root: Path,
    *,
    feature_schema: tuple[tuple[str, str, str], ...] | None = None,
    library_versions: Mapping[str, str] | None = None,
    model_id: str | None = None,
) -> tuple[Path, ArtifactCompatibilityExpectation]:
    root.mkdir(parents=True, exist_ok=True)
    model = _SyntheticShadowModel(
        model_id=model_id or FIXTURE["model_artifact"]["model_id"],
        dataset_id=FIXTURE["source_identity"]["dataset_id"],
        model_family=FIXTURE["model_artifact"]["model_family"],
    )
    artifact_path = root / "model.joblib"
    joblib.dump(model, artifact_path)
    schema = feature_schema or tuple(tuple(item) for item in FIXTURE["feature_schema"])
    libraries = dict(library_versions or _runtime_libraries())
    manifest = ModelArtifactManifest.create(
        model_id=FIXTURE["model_artifact"]["model_id"],
        dataset_id=FIXTURE["source_identity"]["dataset_id"],
        created_run_id="c1-synthetic-run",
        created_at="2026-09-22T12:00:00+00:00",
        model_family=FIXTURE["model_artifact"]["model_family"],
        feature_registry_hash=FIXTURE["source_identity"]["feature_registry_hash"],
        label_registry_hash="sha256:" + "e" * 64,
        feature_schema=schema,
        training_as_of="2024-01-12T08:30:00+08:00",
        hyperparameters_hash="sha256:" + "f" * 64,
        library_versions=libraries,
        serialization_format="joblib",
        artifact_filename=artifact_path.name,
        artifact_hash=_file_hash(artifact_path),
    )
    _write_json(root / "manifest.json", manifest.to_dict())
    expectation = ArtifactCompatibilityExpectation(
        expected_model_family=FIXTURE["model_artifact"]["model_family"],
        expected_feature_registry_hash=FIXTURE["source_identity"]["feature_registry_hash"],
        expected_label_registry_hash="sha256:" + "e" * 64,
        expected_feature_schema=tuple(tuple(item) for item in FIXTURE["feature_schema"]),
        installed_library_versions=_runtime_libraries(),
    )
    return root, expectation


def test_c1_model_artifact_loader_binds_schema_dtype_library_and_artifact_identity(
    tmp_path: Path,
) -> None:
    package, expectation = _write_model_package(tmp_path / "model-positive")
    result = SafeShadowModelArtifactLoader(data_root=tmp_path / "formal-data").load(
        package, expectation=expectation
    )
    assert result.status == "shadow_model_ready"
    assert result.manifest is not None
    assert result.manifest.feature_schema == tuple(tuple(item) for item in FIXTURE["feature_schema"])
    assert result.model is not None and result.model.model_id == FIXTURE["model_artifact"]["model_id"]
    assert result.formal_rule_unchanged is True
    assert result.production_action_allowed is False


@pytest.mark.parametrize("mismatch", ("feature_order", "dtype", "library", "schema", "artifact", "model_identity"))
def test_c1_model_artifact_loader_rejects_abi_and_identity_mutations(
    tmp_path: Path, mismatch: str
) -> None:
    package, expectation = _write_model_package(tmp_path / mismatch)
    manifest_path = package / "manifest.json"
    if mismatch in {"feature_order", "dtype", "library"}:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if mismatch == "feature_order":
            manifest["feature_schema"].reverse()
        elif mismatch == "dtype":
            manifest["feature_schema"][0][1] = "float32"
        else:
            manifest["library_versions"]["numpy"] = "0.0.0"
        # Rebuild through the real immutable manifest constructor so the
        # compatibility validator receives a self-consistent mutated manifest.
        changed = ModelArtifactManifest.create(
            model_id=manifest["model_id"],
            dataset_id=manifest["dataset_id"],
            created_run_id=manifest["created_run_id"],
            created_at=manifest["created_at"],
            model_family=manifest["model_family"],
            feature_registry_hash=manifest["feature_registry_hash"],
            label_registry_hash=manifest["label_registry_hash"],
            feature_schema=tuple(tuple(item) for item in manifest["feature_schema"]),
            training_as_of=manifest["training_as_of"],
            hyperparameters_hash=manifest["hyperparameters_hash"],
            library_versions=manifest["library_versions"],
            serialization_format=manifest["serialization_format"],
            artifact_filename=manifest["artifact_filename"],
            artifact_hash=manifest["artifact_hash"],
        )
        _write_json(manifest_path, changed.to_dict())
    elif mismatch == "schema":
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["schema_version"] = "ml-model-artifact-manifest.v999"
        _write_json(manifest_path, manifest)
    elif mismatch == "artifact":
        (package / "model.joblib").write_bytes(b"synthetic artifact mutation")
    else:
        package, expectation = _write_model_package(
            tmp_path / "model-identity-mismatch",
            model_id="different-model-id",
        )

    result = SafeShadowModelArtifactLoader(data_root=tmp_path / "formal-data").load(
        package, expectation=expectation
    )
    assert result.status == "rule_only_fallback"
    assert result.model is None
    assert result.formal_rule_unchanged is True
    assert result.production_action_allowed is False
    expected_blockers = {
        "feature_order": "feature_schema_mismatch",
        "dtype": "feature_schema_mismatch",
        "library": "library_version_mismatch",
        "schema": "manifest_schema_version_mismatch",
        "artifact": "artifact_hash_mismatch",
        "model_identity": "deserialized_model_identity_mismatch",
    }
    assert expected_blockers[mismatch] in result.blockers


def _synthetic_receipt(tmp_path: Path):
    decision_day = date(2025, 5, 1)
    decision_text = decision_day.isoformat()
    feature_as_of = (decision_day - timedelta(days=1)).isoformat()
    candidate_id = FIXTURE["receipt_binding"]["candidate_id"]
    cost_hash = FIXTURE["receipt_binding"]["cost_scenario_hash"]
    schema = tuple(tuple(item) for item in FIXTURE["feature_schema"])
    feature_ids = tuple(item[0] for item in schema)
    snapshot = SimpleNamespace(
        decision_date=decision_text,
        feature_as_of_date=feature_as_of,
        source_fingerprint="synthetic-source-fingerprint-v1",
        source_tables=("prices", "technicals"),
        query_count=2,
        prices=(),
        technicals=(),
        market=(),
        industries=(),
    )
    feature_rows = tuple(
        SimpleNamespace(
            symbol=symbol,
            decision_date=decision_text,
            feature_as_of_date=feature_as_of,
            feature_available_date=feature_as_of,
            feature_ids=feature_ids,
            values=(12_345, None),
            row_id=f"c1-inference:{symbol}",
            snapshot_hash=_logical_hash({"snapshot": symbol}),
        )
        for symbol in ("1101", "2330")
    )
    inference = build_inference_provenance(
        snapshot=snapshot,
        feature_rows=feature_rows,
        feature_schema=schema,
        feature_registry_hash=FIXTURE["source_identity"]["feature_registry_hash"],
        feature_builder_schema_hash="sha256:" + "1" * 64,
        source_database="synthetic://readiness",
        history_start_date="2025-01-01",
        cost_scenario_hash=cost_hash,
        cost_scenario_id="synthetic-cost",
        cost_scenario_version="v1",
        probability_transform_id=PROBABILITY_TRANSFORM_ID,
    )
    training = build_training_provenance(lineage_payload=None)
    candidate_root = tmp_path / "candidate-package"
    candidate_root.mkdir(parents=True, exist_ok=True)
    candidate_artifact = candidate_root / "candidate.bin"
    candidate_artifact.write_bytes(b"c1-synthetic-shadow-candidate-artifact-v1\n")
    candidate_artifact_hash = _file_hash(candidate_artifact)
    candidate_manifest_body = {
        "schema_version": "c1-synthetic-candidate-manifest.v1",
        "artifact_filename": candidate_artifact.name,
        "artifact_hash": candidate_artifact_hash,
    }
    candidate_manifest_hash = _logical_hash(candidate_manifest_body)
    candidate_manifest = {
        **candidate_manifest_body,
        "manifest_hash": candidate_manifest_hash,
    }
    _write_json(candidate_root / "manifest.json", candidate_manifest)
    _write_json(
        candidate_root / "candidate.json",
        {
            "candidate_id": candidate_id,
            "dataset_hash": "sha256:" + "2" * 64,
            "cost_scenario_hash": cost_hash,
            "manifest_hash": candidate_manifest_hash,
            "artifact_hash": candidate_artifact_hash,
        },
    )
    candidate = {
        "candidate_id": candidate_id,
        "candidate_root": str(candidate_root.resolve()),
        "candidate_manifest_hash": candidate_manifest_hash,
        "candidate_artifact_hash": candidate_artifact_hash,
        "dataset_hash": "sha256:" + "2" * 64,
        "cost_scenario_hash": cost_hash,
    }
    compatibility = validate_provenance_compatibility(
        training,
        inference,
        expected_cost_scenario_hash=cost_hash,
        expected_probability_transform_id=PROBABILITY_TRANSFORM_ID,
    )
    receipt = build_inference_projection_receipt(
        decision_date=decision_text,
        result_id=FIXTURE["receipt_binding"]["result_id"],
        candidate_identity=candidate,
        training_provenance=training,
        inference_provenance=inference,
        compatibility=compatibility,
        projections=(
            {
                "stock_code": "1101",
                "status": "active_candidate",
                "model_version": candidate_id,
                "ranking_score_bp": 7_300,
                "ranking_percentile_bp": 8_200,
                "cost_scenario_hash": cost_hash,
            },
            {
                "stock_code": "2330",
                "status": "active_candidate",
                "model_version": candidate_id,
                "ranking_score_bp": 7_200,
                "ranking_percentile_bp": 8_100,
                "cost_scenario_hash": cost_hash,
            },
        ),
    )
    receipt_path = persist_inference_projection_receipt(tmp_path / "learning", receipt)
    as_of = decision_day
    common_item = RecommendationItem(
        stock_code="2330",
        rule_score=Decimal("82.5000"),
        rank=0,
        universe_ref=UniverseReference(
            policy_id="synthetic-listed-v1",
            snapshot_id="synthetic-members-2025-05-01",
            as_of_date=as_of,
            members_hash="synthetic-members-hash",
        ),
        reasons=("synthetic saved execution",),
    )
    items = (replace(common_item, stock_code="1101"), common_item)
    binding = MLReceiptBinding(
        receipt_ref=VersionReference(ReferenceKind.ML_RECEIPT, str(receipt_path)),
        receipt_hash=receipt.receipt_hash,
        result_id=FIXTURE["receipt_binding"]["result_id"],
        decision_date=as_of,
        model_candidate_id=candidate_id,
        projected_stock_codes=tuple(FIXTURE["receipt_binding"]["projected_stock_codes"]),
        cost_scenario_hash=cost_hash,
    )
    execution = RecommendationExecution(
        result_id=FIXTURE["receipt_binding"]["result_id"],
        request=Request(as_of_date=as_of),
        context=Context(
            as_of_date=as_of,
            decision_at=datetime(2025, 5, 1, 12, tzinfo=timezone.utc),
            source_refs=(SourceRef("synthetic-source", revision=1, snapshot_id="synthetic-v1"),),
        ),
        status=ExecutionStatus.COMPLETED,
        decision=DecisionBatch(items=items, regime="Trend"),
        ml_availability=MLAvailability(status=MLAvailabilityStatus.AVAILABLE),
        ml_projection_refs=(
            VersionReference(ReferenceKind.ML_PROJECTION, str(receipt.payload["projection_rows_sha256"])),
        ),
        ml_receipt_refs=(binding,),
    )
    return execution, receipt, receipt_path


def _query_stack(root: Path):
    runs_dir = root / "recommendation" / "runs"
    store = ResultArtifactStore(
        artifact_root=runs_dir / "execution_artifacts",
        database_path=runs_dir / "recommendation_runs.db",
    )
    persistence = RecommendationExecutionPersistence(store)
    return persistence, RecommendationExecutionQueries(persistence)


def _receipt_tamper_copy(
    tmp_path: Path,
    receipt_path: Path,
    *,
    mutation: str,
) -> tuple[Path, str]:
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    payload.pop("receipt_hash", None)
    inference = payload["inference_provenance"]
    if mutation == "feature_order":
        inference["feature_rows"][0]["feature_ids"].reverse()
    elif mutation == "dtype":
        inference["feature_transform_contract"]["canonical_schema"][0][1] = "float32"
    elif mutation == "unit_scale":
        inference["feature_transform_contract"]["canonical_schema"][0][2] = "raw"
    elif mutation == "mask_missing_policy":
        inference["feature_transform_contract"]["missing_policy"] = "missing_is_zero"
    elif mutation == "source_dependency_hash":
        inference["source_fingerprint"] = "mutated-source-fingerprint"
    elif mutation == "schema":
        payload["schema_version"] = "recommendation-inference-projection.v999"
    else:
        raise AssertionError(f"unknown tamper case: {mutation}")
    new_hash = _logical_hash(payload)
    payload["receipt_hash"] = new_hash
    target = tmp_path / "corrupted-receipt-copies" / mutation / f"{new_hash.split(':', 1)[1]}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return target, new_hash


def test_c1_u4_read_view_exposes_only_exact_verified_receipt_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture_before = FIXTURE_PATH.read_bytes()
    execution, receipt, receipt_path = _synthetic_receipt(tmp_path)
    receipt_before = receipt_path.read_bytes()
    payload = receipt.payload
    assert payload["result_id"] == execution.result_id
    assert payload["decision_date"] == execution.context.as_of_date.isoformat()
    assert payload["candidate_identity"]["candidate_id"] == execution.ml_receipt_refs[0].model_candidate_id
    assert payload["cost_scenario_hash"] == execution.ml_receipt_refs[0].cost_scenario_hash
    assert tuple(row["stock_code"] for row in payload["projections"]) == execution.ml_receipt_refs[0].projected_stock_codes
    assert tuple(payload["inference_provenance"]["feature_rows"][0]["feature_ids"]) == tuple(FIXTURE["feature_order"])
    assert payload["inference_provenance"]["feature_rows"][0]["feature_values"] == [12_345, None]
    assert payload["inference_provenance"]["inference_source_hash"].startswith("sha256:")
    assert payload["inference_provenance"]["feature_rows_sha256"].startswith("sha256:")

    mismatches = (
        {"expected_result_id": "different-result"},
        {"expected_candidate_id": "different-candidate"},
        {"expected_decision_date": "2025-05-02"},
        {"expected_cost_scenario_hash": _ZERO},
        {"expected_stock_code": "9999"},
    )
    for expected in mismatches:
        with pytest.raises(RecommendationProvenanceError):
            read_inference_projection_receipt(receipt_path, **expected)

    def no_rebuild(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("U4 query readback must not rebuild or re-infer ML")

    import ml_module.recommendation_inference_provenance as provenance_module

    monkeypatch.setattr(provenance_module, "build_inference_provenance", no_rebuild)
    monkeypatch.setattr(provenance_module, "build_inference_projection_receipt", no_rebuild)
    monkeypatch.setattr(provenance_module, "persist_inference_projection_receipt", no_rebuild)
    persistence, queries = _query_stack(tmp_path / "canonical")
    persistence.save(
        execution,
        now=lambda: datetime(2026, 9, 22, 12, tzinfo=timezone.utc),
    )
    loaded = queries.get(execution.result_id)
    assert loaded is not None
    assert loaded.execution == execution
    assert loaded.execution.decision == execution.decision
    assert loaded.ml_read_status == "verified"
    assert tuple(row["stock_code"] for row in loaded.ml_projection_rows) == tuple(
        FIXTURE["receipt_binding"]["projected_stock_codes"]
    )
    assert all(row["model_version"] == execution.ml_receipt_refs[0].model_candidate_id for row in loaded.ml_projection_rows)
    assert all(row["cost_scenario_hash"] == execution.ml_receipt_refs[0].cost_scenario_hash for row in loaded.ml_projection_rows)
    assert receipt_path.read_bytes() == receipt_before
    assert FIXTURE_PATH.read_bytes() == fixture_before


@pytest.mark.parametrize(
    "mutation",
    (
        "feature_order",
        "dtype",
        "unit_scale",
        "mask_missing_policy",
        "source_dependency_hash",
        "schema",
        "candidate_artifact",
    ),
)
def test_c1_u4_read_view_fails_closed_on_receipt_abi_mutations(
    tmp_path: Path, mutation: str
) -> None:
    execution, _receipt, receipt_path = _synthetic_receipt(tmp_path)
    if mutation == "candidate_artifact":
        candidate_root = Path(
            _receipt.payload["candidate_identity"]["candidate_root"]
        )
        candidate_package = json.loads(
            (candidate_root / "manifest.json").read_text(encoding="utf-8")
        )
        (candidate_root / candidate_package["artifact_filename"]).write_bytes(
            b"mutated candidate artifact bytes\n"
        )
        corrupted_path = receipt_path
        corrupted_hash = execution.ml_receipt_refs[0].receipt_hash
    else:
        corrupted_path, corrupted_hash = _receipt_tamper_copy(
            tmp_path, receipt_path, mutation=mutation
        )
    original_binding = execution.ml_receipt_refs[0]
    binding = replace(
        original_binding,
        receipt_ref=VersionReference(ReferenceKind.ML_RECEIPT, str(corrupted_path)),
        receipt_hash=corrupted_hash,
    )
    tampered_execution = replace(execution, ml_receipt_refs=(binding,))
    persistence, queries = _query_stack(tmp_path / "query")
    persistence.save(
        tampered_execution,
        now=lambda: datetime(2026, 9, 22, 12, tzinfo=timezone.utc),
    )
    loaded = queries.get(tampered_execution.result_id)
    assert loaded is not None
    assert loaded.execution == tampered_execution
    assert loaded.execution.decision == execution.decision
    assert loaded.ml_read_status == "unavailable"
    assert loaded.ml_projection_rows == ()
    assert loaded.diagnostics


@pytest.mark.parametrize("mismatch", ("candidate", "cost", "projected_order", "row_hash", "receipt_hash"))
def test_c1_u4_read_view_keeps_rule_outcome_when_receipt_binding_changes(
    tmp_path: Path, mismatch: str
) -> None:
    execution, _receipt, receipt_path = _synthetic_receipt(tmp_path)
    binding = execution.ml_receipt_refs[0]
    changes: dict[str, Any] = {}
    if mismatch == "candidate":
        changes["model_candidate_id"] = "candidate-mutated"
    elif mismatch == "cost":
        changes["cost_scenario_hash"] = _ZERO
    elif mismatch == "projected_order":
        changes["projected_stock_codes"] = tuple(reversed(binding.projected_stock_codes))
    elif mismatch == "receipt_hash":
        changes["receipt_hash"] = _ZERO
    bad_binding = replace(binding, **changes)
    bad_execution = replace(execution, ml_receipt_refs=(bad_binding,))
    if mismatch == "row_hash":
        bad_execution = replace(
            bad_execution,
            ml_projection_refs=(
                VersionReference(ReferenceKind.ML_PROJECTION, _ZERO),
            ),
        )
    assert receipt_path.is_file()
    persistence, queries = _query_stack(tmp_path / "query")
    persistence.save(
        bad_execution,
        now=lambda: datetime(2026, 9, 22, 12, tzinfo=timezone.utc),
    )
    loaded = queries.get(bad_execution.result_id)
    assert loaded is not None
    assert loaded.execution == bad_execution
    assert loaded.execution.decision == execution.decision
    assert loaded.ml_read_status == "unavailable"
    assert loaded.ml_projection_rows == ()


def test_c1_fixture_bytes_are_read_back_exactly() -> None:
    assert len(FIXTURE_BYTES) == 2_230
    assert hashlib.sha256(FIXTURE_BYTES).hexdigest() == FIXTURE_SHA256
    assert FIXTURE_PATH.read_bytes() == FIXTURE_BYTES
    assert json.loads(FIXTURE_BYTES) == FIXTURE
