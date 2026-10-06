"""修訂模型的當日研究推論；prepare 完成後不再讀來源資料。"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Sequence

from app_module.allocation_release_adapter import AllocationReleaseAdapter
from data_module.ml_restatement_current_inputs import prepare_restated_current_inputs


def validate_restated_output_root(
    *, release_root: Path, dataset_manifest: Path, output_root: Path,
) -> Path:
    """在任何擷取或結果寫入前，保護已封存的來源與模型目錄。"""
    root = output_root.resolve()
    destinations = (root, (root / "input_captures").resolve(), (root / "current_shadow").resolve())
    for source_root in (release_root.resolve(), dataset_manifest.resolve().parent):
        if any(destination == source_root or destination.is_relative_to(source_root) for destination in destinations):
            raise ValueError("research outputs must be outside immutable source/release roots")
    return root


def run_restated_current_shadow(
    *,
    release_root: Path,
    expected_release_identity_hash: str,
    dataset_manifest: Path,
    expected_dataset_manifest_hash: str,
    symbols: Sequence[str],
    output_root: Path,
    captured_at: datetime | None = None,
) -> dict[str, object]:
    """產出當次不可覆寫的判讀 receipt，不變更正式模型或排程設定。"""
    root = validate_restated_output_root(
        release_root=release_root, dataset_manifest=dataset_manifest, output_root=output_root,
    )
    capture = captured_at or datetime.now(timezone.utc)
    loaded = AllocationReleaseAdapter().load(
        release_root,
        expected_release_identity_hash=expected_release_identity_hash,
    )
    prepared = prepare_restated_current_inputs(
        manifest_path=dataset_manifest,
        expected_manifest_file_hash=expected_dataset_manifest_hash,
        symbols=symbols,
        captured_at=capture,
    )
    if tuple(name for name, _ in prepared.binding.ordered_features) != loaded.manifest.feature_order:
        raise ValueError("prepared feature order differs from the release")
    prepared.binding.require_compatible_training_sources(
        loaded.manifest.source_manifest_hashes
    )
    result = loaded.infer_research_shadow(
        rows=prepared.rows,
        universe_id="restated-current-" + prepared.binding.binding_hash[7:31],
        policy_hash=loaded.manifest.missing_policy.policy_hash,
        research_input_binding=prepared.binding,
    )
    audit = result.audit_payload()
    target_summary = audit.get("target_summary")
    if not isinstance(target_summary, dict) or target_summary.get("model_learned_allocation") is not False:
        raise ValueError("restated current entry requires the explicit neutral allocation policy")
    if (
        result.formal_oos_allowed is not False
        or result.production_action_allowed is not False
        or result.production_blend_alpha_bp != 0
        or audit.get("broker_order_allowed") is not False
    ):
        raise ValueError("research inference unexpectedly grants production authority")
    receipt = {
        "schema_version": "restated-allocation-current-shadow.v1",
        "status": "completed_research_inference",
        "captured_at": prepared.binding.captured_at,
        "training_release": {
            "release_root": str(loaded.release_root),
            "release_id": loaded.release_id,
            "release_identity_hash": loaded.manifest.release_identity_hash,
            "release_manifest_file_hash": loaded.release_manifest_file_hash,
            "model_artifact_hash": loaded.artifact_hash,
            "training_dataset_id": loaded.dataset_id,
            "training_dataset_identity_hash": loaded.manifest.dataset_identity_hash,
            "training_source_manifest_hashes": list(loaded.manifest.source_manifest_hashes),
        },
        "prepared_input": prepared.receipt(),
        "inference_audit": audit,
        "proposal": result.proposal.to_dict(),
        "historical_pit": False,
        "formal_oos_allowed": False,
        "production_action_allowed": False,
        "production_blend_alpha_bp": 0,
        "broker_order_allowed": False,
        "model_learned_allocation": False,
        "interpretation": "修訂後研究預測；固定現金配置不代表模型學會持股比例。",
    }
    encoded_body = json.dumps(
        receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    receipt_hash = "sha256:" + hashlib.sha256(encoded_body).hexdigest()
    receipt["receipt_hash"] = receipt_hash
    encoded = (json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    validate_restated_output_root(
        release_root=release_root, dataset_manifest=dataset_manifest, output_root=root,
    )
    destination = root / "current_shadow" / (receipt_hash[7:] + ".json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        if destination.read_bytes() != encoded:
            raise ValueError("research receipt collision; refusing to replace existing output")
    return {
        "status": receipt["status"],
        "receipt_path": str(destination),
        "receipt_hash": receipt_hash,
        "release_id": loaded.release_id,
        "row_count": len(prepared.rows),
        "symbols": [row.symbol for row in prepared.rows],
        "feature_asof_date": prepared.feature_asof_date,
        "captured_at": prepared.binding.captured_at,
        "formal_oos_allowed": False,
        "production_blend_alpha_bp": 0,
    }
