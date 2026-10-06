"""原 bounded 家族重訓後的當日研究預測；不產生配置或正式交易權限。"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from analysis_module.technical_analysis.technical_indicators import CAUSAL_INDICATOR_COLUMNS
from app_module.ml_allocation_inference_service import (
    MLAllocationInferenceService,
    _expert_output_payload,
)
from data_module.ml_restatement_current_inputs import prepare_restated_current_inputs
from data_module.ml_restatement_research_dataset import expected_feature_contract, sha256_file


def _read_bound(path: Path, expected_hash: str) -> dict[str, Any]:
    raw = path.read_bytes()
    if "sha256:" + hashlib.sha256(raw).hexdigest() != expected_hash:
        raise ValueError("bounded research file hash mismatch")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("bounded research metadata must be an object")
    return value


def _child(root: Path, name: object) -> Path:
    if not isinstance(name, str) or not name or Path(name).name != name:
        raise ValueError("bounded artifact filename must be a basename")
    result = (root / name).resolve(strict=True)
    if not result.is_relative_to(root):
        raise ValueError("bounded artifact path escapes the fit directory")
    return result


def validate_bounded_output_root(
    *, fit_directory: Path, training_manifest: Path, current_manifest: Path, output_root: Path,
) -> Path:
    """任何擷取／輸出開始前，拒絕寫入封存的模型與資料來源。"""
    root = output_root.resolve()
    destinations = (root, (root / "input_captures").resolve(), (root / "bounded_current_heads").resolve())
    sources = (fit_directory.resolve(), training_manifest.resolve().parent, current_manifest.resolve().parent)
    if any(target == source or target.is_relative_to(source) for target in destinations for source in sources):
        raise ValueError("bounded research output must be outside immutable inputs")
    return root


def _validate_fit_receipt(receipt: Mapping[str, Any]) -> None:
    if (
        receipt.get("schema_version") != "bounded-restated-research-fit-receipt.v1"
        or receipt.get("status") != "completed_research_only"
        or receipt.get("dataset_temporality") != "restated_research"
        or any(receipt.get(name) is not False for name in (
            "historical_pit", "formal_oos_allowed", "production_action_allowed", "promotion_eligible",
        ))
    ):
        raise ValueError("explicit bounded restated research fit receipt is required")
    profile = receipt.get("training_profile")
    if (
        not isinstance(profile, dict)
        or profile.get("horizons") != [5, 10, 20, 60]
        or sorted(profile.get("algorithms", ())) != ["hist_gradient_boosting", "ridge_logistic"]
    ):
        raise ValueError("bounded research requires both original algorithms and four horizons")


def _json_hash(value: object) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _validate_registry_bridge(manifest: Mapping[str, Any], current_registry_hash: str) -> dict[str, object]:
    """核對技術欄來源的合法修訂，兩個 registry 身分仍各自保留。"""
    from data_module.bounded_official_market_restatement import OFFICIAL_RESTATEMENT_SCHEMA, validate_official_registry_bridge

    if manifest.get("restatement", {}).get("schema_version") == OFFICIAL_RESTATEMENT_SCHEMA:
        return validate_official_registry_bridge(manifest, current_registry_hash)
    training_hash = manifest["feature_registry_hash"]
    if training_hash == current_registry_hash:
        return {"status": "identical_registry", "training": training_hash, "current": current_registry_hash}
    transition = manifest.get("feature_registry_transition")
    if not isinstance(transition, dict):
        raise ValueError("different bounded registries require an explicit transition")
    original = transition.get("original_registry")
    restated = manifest.get("feature_registry")
    names, scales = expected_feature_contract()
    technical = tuple(sorted("technical_indicators." + name for name in CAUSAL_INDICATOR_COLUMNS))
    if (
        len(technical) != 20
        or not isinstance(original, dict) or not isinstance(restated, dict)
        or _json_hash(original) != current_registry_hash
        or _json_hash(restated) != training_hash
        or transition.get("original_registry_hash") != current_registry_hash
        or transition.get("restated_registry_hash") != training_hash
        or sorted(transition.get("allowed_changed_feature_ids", ())) != sorted(technical)
        or sorted(transition.get("allowed_definition_fields", ())) != ["record_hash", "source_id", "table_name"]
    ):
        raise ValueError("bounded registry transition differs from the fixed research contract")
    expected = json.loads(json.dumps(original))
    definitions = expected.get("features")
    if not isinstance(definitions, list):
        raise ValueError("original bounded registry has no feature definitions")
    seen = set()
    scale_by_id = dict(zip(names, scales))
    kernel_hashes = manifest["restatement"]["kernel_source_hashes"]
    for definition in definitions:
        name = definition["feature_id"]
        if name in seen or name not in scale_by_id or definition["scale"] != scale_by_id[name]:
            raise ValueError("bounded registry changed the numeric feature contract")
        seen.add(name)
        if name not in technical:
            continue
        prior_record_hash = definition["record_hash"]
        definition["source_id"] = "derived:causal_technical_indicators"
        definition["table_name"] = "derived_technical_indicators"
        definition["record_hash"] = _json_hash({
            "schema_version": "restated-feature-definition.v1", "prior_record_hash": prior_record_hash,
            "feature_id": name, "source_id": definition["source_id"],
            "table_name": definition["table_name"], "scale": definition["scale"],
            "kernel_source_hashes": kernel_hashes,
        })
    if seen != set(names[10:]):
        raise ValueError("bounded registry lost or added a source feature")
    expected["features"].sort(key=lambda item: str(item["feature_id"]))
    if expected != restated:
        raise ValueError("bounded registry changed fields outside the source revision")
    return {"status": "verified_technical_source_revision", "training": training_hash,
            "current": current_registry_hash, "unchanged_numeric_slots": 62,
            "revised_source_definitions": len(technical)}


def run_bounded_restated_current_heads(
    *, fit_directory: Path, expected_fit_receipt_hash: str,
    training_manifest: Path, expected_training_manifest_hash: str,
    current_manifest: Path, expected_current_manifest_hash: str,
    symbols: Sequence[str], output_root: Path, captured_at: datetime | None = None,
) -> dict[str, object]:
    """核對雙方來源身分後重用純 expert predictor，不走歷史 PIT 或配置流程。

    修訂後訓練與當日輸入保留各自身分，不改寫模型 bytes、profile、row identity，
    也不將歷史修訂資料偽裝成當時已知資料。僅使用既有整數 bp 輸出轉換。
    """
    root = validate_bounded_output_root(
        fit_directory=fit_directory, training_manifest=training_manifest,
        current_manifest=current_manifest, output_root=output_root,
    )
    capture = captured_at or datetime.now(timezone.utc)
    if capture.tzinfo is None or capture.utcoffset() is None:
        raise ValueError("bounded research capture requires an actual timezone-aware clock")
    fit_root = fit_directory.resolve(strict=True)
    receipt_path = _child(fit_root, "fit_receipt.json")
    receipt = _read_bound(receipt_path, expected_fit_receipt_hash)
    _validate_fit_receipt(receipt)
    manifest = _read_bound(training_manifest, expected_training_manifest_hash)
    if (
        receipt.get("dataset_manifest_sha256") != expected_training_manifest_hash
        or any(receipt.get(name) != manifest.get(name) for name in (
            "dataset_id", "dataset_identity_hash", "training_as_of",
        ))
        or receipt.get("source_publication_manifest_hash") != manifest.get("manifest_hash")
    ):
        raise ValueError("bounded fit receipt differs from its training manifest")
    trained_at = datetime.fromisoformat(str(receipt["training_as_of"]).replace("Z", "+00:00"))
    if trained_at.tzinfo is None or trained_at > capture:
        raise ValueError("bounded training data was not available at current capture")
    artifact_path = _child(fit_root, receipt.get("model_artifact_file", "bounded_restated_research_model.joblib"))
    audit_path = _child(fit_root, "allocation_training_audit.json")
    if sha256_file(audit_path) != receipt["audit_sha256"]:
        raise ValueError("bounded training audit hash differs")
    # constructor 會在反序列化前核對 bytes SHA／事故隔離，再檢查完整 artifact 契約。
    service = MLAllocationInferenceService(
        artifact_bytes=artifact_path.read_bytes(),
        expected_artifact_hash=receipt["model_artifact_sha256"],
        expected_dataset_id=receipt["dataset_id"],
    )
    artifact = service._artifact
    names, scales = expected_feature_contract()
    if (
        artifact.dataset_identity_hash != receipt["dataset_identity_hash"]
        or artifact.dataset_manifest_file_hash != expected_training_manifest_hash
        or datetime.fromisoformat(artifact.training_as_of.replace("Z", "+00:00")) != trained_at
        or artifact.feature_registry_hash != manifest["feature_registry_hash"]
        or artifact.source_manifest_hashes != tuple(sorted(tuple(item) for item in manifest["source_manifest_hashes"]))
        or tuple(feature for pack in artifact.feature_packs for feature in pack.feature_ids) != names
        or artifact.horizons != (5, 10, 20, 60)
        or len(artifact.expert_keys) != 24
        or {key.rsplit("|", 1)[-1] for key in artifact.expert_keys} != {"hist_gradient_boosting", "ridge_logistic"}
    ):
        raise ValueError("bounded artifact differs from the audited original family contract")
    prepared = prepare_restated_current_inputs(
        manifest_path=current_manifest, expected_manifest_file_hash=expected_current_manifest_hash,
        symbols=symbols, captured_at=capture,
    )
    if prepared.binding.ordered_features != tuple(zip(names, scales)):
        raise ValueError("current inputs differ from the bounded training feature contract")
    prepared.binding.require_compatible_training_sources(
        artifact.source_manifest_hashes
    )
    registry_bridge = _validate_registry_bridge(manifest, prepared.binding.feature_registry_hash)
    expected_families = {name: pack.pack_id for pack in artifact.feature_packs for name in pack.feature_ids}
    if any(feature.family_id != expected_families[feature.feature_id]
           for row in prepared.rows for feature in row.features):
        raise ValueError("current feature families differ from bounded training")
    # 這是獨立研究 consumer，僅呼叫已存在的數值 predictor；不授予正常 infer 權限。
    from threadpoolctl import threadpool_limits

    with threadpool_limits(limits=2):
        predictions = service._predict_experts(
            rows=prepared.rows, pack_coverage=service._pack_coverage(prepared.rows),
            allow_research_shadow=True,
        )
    rows = [{
        "symbol": row.symbol, "input_row_id": row.row_id,
        "experts": [{"expert_key": key, **_expert_output_payload(predictions[row.row_id][key])}
                    for key in artifact.expert_keys],
    } for row in prepared.rows]
    for path, expected in (
        (receipt_path, expected_fit_receipt_hash), (training_manifest, expected_training_manifest_hash),
        (current_manifest, expected_current_manifest_hash), (artifact_path, receipt["model_artifact_sha256"]),
        (audit_path, receipt["audit_sha256"]),
    ):
        if sha256_file(path) != expected:
            raise ValueError("bounded research input changed during inference")
    result = {
        "schema_version": "bounded-restated-current-heads.v1",
        "status": "completed_research_predictions",
        "captured_at": prepared.binding.captured_at,
        "training_fit_receipt_sha256": expected_fit_receipt_hash,
        "training_dataset_id": artifact.dataset_id,
        "training_dataset_identity_hash": artifact.dataset_identity_hash,
        "training_manifest_sha256": expected_training_manifest_hash,
        "model_artifact_sha256": receipt["model_artifact_sha256"],
        "prepared_input": prepared.receipt(), "rows": rows,
        "feature_registry_compatibility": registry_bridge,
        "horizons": [5, 10, 20, 60], "experts_per_row": len(artifact.expert_keys),
        "historical_pit": False, "formal_oos_allowed": False,
        "production_action_allowed": False, "production_blend_alpha_bp": 0,
        "broker_order_allowed": False, "promotion_eligible": False,
        "allocation_proposal": None,
        "interpretation": "修訂後原 bounded 家族的當日研究預測；未產生持股比例或買賣指令。",
    }
    body = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    fingerprint = "sha256:" + hashlib.sha256(body).hexdigest()
    result["receipt_hash"] = fingerprint
    encoded = (json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    validate_bounded_output_root(
        fit_directory=fit_root, training_manifest=training_manifest,
        current_manifest=current_manifest, output_root=root,
    )
    destination = root / "bounded_current_heads" / (fingerprint[7:] + ".json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    return {
        "status": result["status"], "receipt_path": str(destination), "receipt_hash": fingerprint,
        "row_count": len(rows), "experts_per_row": len(artifact.expert_keys),
        "captured_at": prepared.binding.captured_at, "feature_asof_date": prepared.feature_asof_date,
        "formal_oos_allowed": False, "production_blend_alpha_bp": 0,
    }
