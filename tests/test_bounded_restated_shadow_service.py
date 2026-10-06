from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest
from threadpoolctl import threadpool_limits

from app_module.bounded_restated_shadow_service import (
    _json_hash,
    _validate_registry_bridge,
    run_bounded_restated_current_heads,
)
from analysis_module.technical_analysis.technical_indicators import CAUSAL_INDICATOR_COLUMNS
from data_module.ml_restatement_research_dataset import expected_feature_contract, sha256_file
from ml_module.allocation_training_service import AllocationTrainingService, FeaturePackDefinition
from tests.fixtures.ml_allocation_training_support import _sample, folds  # noqa: F401
from tests.test_ml_restatement_current_inputs import _CAPTURE, _fixture_dataset


_HASH = "sha256:" + "a" * 64
_SOURCE = "sha256:" + "b" * 64
_TRAIN_AT = "2026-09-23T12:30:00+08:00"


def _packs():
    names, _ = expected_feature_contract()
    return (
        FeaturePackDefinition("data_quality", names[:10]),
        FeaturePackDefinition("market_sector_cross_section", names[10:21]),
        FeaturePackDefinition("price_liquidity_technical", names[21:]),
    )


@pytest.fixture(scope="module")
def samples():
    names, scales = expected_feature_contract()
    families = {name: pack.pack_id for pack in _packs() for name in pack.feature_ids}
    result = []
    for index in range(163):
        sample = _sample(index)
        features = tuple(replace(
            sample.row.features[1], feature_id=name, family_id=families[name], scale=scale,
            value_int=((index + offset) % 17) * scale,
        ) for offset, (name, scale) in enumerate(zip(names, scales)))
        result.append(replace(sample, row=replace(sample.row, features=features, missing_family_ids=())))
    return tuple(result)


@pytest.fixture(scope="module")
def fit_bundle(tmp_path_factory, samples, folds):
    root = tmp_path_factory.mktemp("bounded-current")
    fit = root / "fit"
    fit.mkdir()
    source = root / "training"
    source.mkdir()
    manifest = source / "manifest.json"
    manifest.write_text(json.dumps({
        "dataset_id": "bounded-synthetic-research", "dataset_identity_hash": _HASH,
        "manifest_hash": _HASH, "training_as_of": _TRAIN_AT, "feature_registry_hash": _HASH,
        "source_manifest_hashes": [["daily_prices", _SOURCE]],
    }), encoding="utf-8")
    with threadpool_limits(limits=2):
        trained = AllocationTrainingService(random_state=7, hgb_max_iter=2).fit(
            dataset_id="bounded-synthetic-research", samples=samples, feature_packs=_packs(), folds=folds,
            training_as_of=_TRAIN_AT, dataset_manifest_file_hash=sha256_file(manifest),
        )
    artifact = fit / "bounded_restated_research_model.joblib"
    artifact.write_bytes(trained.artifact_bytes)
    audit = fit / "allocation_training_audit.json"
    audit.write_text(json.dumps(trained.audit_payload()), encoding="utf-8")
    receipt = fit / "fit_receipt.json"
    receipt.write_text(json.dumps({
        "schema_version": "bounded-restated-research-fit-receipt.v1",
        "status": "completed_research_only", "dataset_temporality": "restated_research",
        "historical_pit": False, "formal_oos_allowed": False,
        "production_action_allowed": False, "promotion_eligible": False,
        "training_profile": {"horizons": [5, 10, 20, 60],
                             "algorithms": ["ridge_logistic", "hist_gradient_boosting"]},
        "dataset_id": "bounded-synthetic-research", "dataset_identity_hash": _HASH,
        "training_as_of": _TRAIN_AT, "source_publication_manifest_hash": _HASH,
        "dataset_manifest_sha256": sha256_file(manifest),
        "model_artifact_sha256": trained.artifact_hash, "audit_sha256": sha256_file(audit),
    }), encoding="utf-8")
    return fit, manifest


def _args(root: Path, fit_bundle):
    fit, manifest = fit_bundle
    current, _ = _fixture_dataset(root / "current")
    payload = json.loads(current.read_text(encoding="utf-8"))
    payload["feature_packs"] = [{"pack_id": pack.pack_id, "feature_ids": pack.feature_ids} for pack in _packs()]
    current.write_text(json.dumps(payload), encoding="utf-8")
    return dict(
        fit_directory=fit, expected_fit_receipt_hash=sha256_file(fit / "fit_receipt.json"),
        training_manifest=manifest, expected_training_manifest_hash=sha256_file(manifest),
        current_manifest=current, expected_current_manifest_hash=sha256_file(current),
        symbols=("1256", "1477"), output_root=root / "out", captured_at=_CAPTURE,
    )


def test_actual_both_algorithm_heads_keep_input_and_training_identities_separate(tmp_path, fit_bundle):
    args = _args(tmp_path, fit_bundle)
    result = run_bounded_restated_current_heads(**args)
    receipt = json.loads(Path(result["receipt_path"]).read_text(encoding="utf-8"))
    assert result["row_count"] == 2 and result["experts_per_row"] == 24
    assert receipt["training_dataset_identity_hash"] == _HASH
    assert receipt["prepared_input"]["dataset_identity_hash"] != _HASH
    assert receipt["allocation_proposal"] is None
    assert receipt["formal_oos_allowed"] is False
    assert receipt["production_blend_alpha_bp"] == 0
    assert receipt["broker_order_allowed"] is False
    assert all(len(row["experts"]) == 24 for row in receipt["rows"])


@pytest.mark.parametrize("failure", ["receipt_hash", "training_hash", "current_hash", "old_clock", "output_in_fit"])
def test_research_reader_rejects_unbound_or_unavailable_inputs(tmp_path, fit_bundle, failure):
    args = _args(tmp_path, fit_bundle)
    if failure in {"receipt_hash", "training_hash", "current_hash"}:
        name = {"receipt_hash": "expected_fit_receipt_hash", "training_hash": "expected_training_manifest_hash",
                "current_hash": "expected_current_manifest_hash"}[failure]
        args[name] = "sha256:" + "f" * 64
    elif failure == "old_clock":
        args["captured_at"] = _CAPTURE.replace(hour=11)
    else:
        args["output_root"] = args["fit_directory"] / "new"
    with pytest.raises(ValueError):
        run_bounded_restated_current_heads(**args)
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("failure", ["production", "algorithm", "audit", "artifact"])
def test_research_receipt_and_files_cannot_silently_change(tmp_path, fit_bundle, failure):
    import shutil

    fit, manifest = fit_bundle
    copied = tmp_path / "copied_fit"
    shutil.copytree(fit, copied)
    args = _args(tmp_path, (copied, manifest))
    receipt_path = copied / "fit_receipt.json"
    if failure in {"production", "algorithm"}:
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        if failure == "production":
            payload["production_action_allowed"] = True
        else:
            payload["training_profile"]["algorithms"] = ["ridge_logistic"]
        receipt_path.write_text(json.dumps(payload), encoding="utf-8")
        args["expected_fit_receipt_hash"] = sha256_file(receipt_path)
    else:
        path = copied / ("allocation_training_audit.json" if failure == "audit" else "bounded_restated_research_model.joblib")
        with path.open("ab") as stream:
            stream.write(b"changed")
    with pytest.raises(ValueError):
        run_bounded_restated_current_heads(**args)
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("failure", ["scale", "family", "missing_definition", "extra_metadata"])
def test_registry_bridge_rejects_self_consistent_but_incompatible_revision(failure):
    names, scales = expected_feature_contract()
    families = {name: pack.pack_id for pack in _packs() for name in pack.feature_ids}
    original = {"features": [{
        "feature_id": name, "scale": scale, "family_id": families[name],
        "source_id": "original", "table_name": "original", "record_hash": _HASH,
    } for name, scale in zip(names[10:], scales[10:])]}
    technical = sorted("technical_indicators." + name for name in CAUSAL_INDICATOR_COLUMNS)
    revised = json.loads(json.dumps(original))
    kernels = {"facade": _HASH, "kernel": _SOURCE}
    for definition in revised["features"]:
        if definition["feature_id"] in technical:
            definition["source_id"] = "derived:causal_technical_indicators"
            definition["table_name"] = "derived_technical_indicators"
            definition["record_hash"] = _json_hash({
                "schema_version": "restated-feature-definition.v1", "prior_record_hash": _HASH,
                "feature_id": definition["feature_id"], "scale": definition["scale"],
                "source_id": definition["source_id"], "table_name": definition["table_name"],
                "kernel_source_hashes": kernels,
            })
    revised["features"].sort(key=lambda item: item["feature_id"])
    original_hash = _json_hash(original)
    manifest = {
        "feature_registry": revised, "feature_registry_hash": _json_hash(revised),
        "restatement": {"kernel_source_hashes": kernels},
        "feature_registry_transition": {
            "original_registry": original, "original_registry_hash": original_hash,
            "restated_registry_hash": _json_hash(revised), "allowed_changed_feature_ids": technical,
            "allowed_definition_fields": ["source_id", "table_name", "record_hash"],
        },
    }
    assert _validate_registry_bridge(manifest, original_hash)["unchanged_numeric_slots"] == 62
    if failure == "scale":
        revised["features"][0]["scale"] += 1
    elif failure == "family":
        revised["features"][0]["family_id"] = "changed"
    elif failure == "missing_definition":
        revised["features"].pop()
    else:
        revised["features"][0]["normalization"] = "unapproved"
    manifest["feature_registry_hash"] = _json_hash(revised)
    manifest["feature_registry_transition"]["restated_registry_hash"] = _json_hash(revised)
    with pytest.raises(ValueError, match="outside the source revision"):
        _validate_registry_bridge(manifest, original_hash)
