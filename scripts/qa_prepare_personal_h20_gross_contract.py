"""以 caller 已核原 fit 收據建立 H20 精確 pins；不 fit、decode 或啟用。"""

from __future__ import annotations

import argparse
from dataclasses import fields
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _read_pinned(path: Path, expected: str) -> tuple[bytes, dict[str, Any]]:
    if not path.is_absolute():
        raise ValueError("absolute_receipt_path_required")
    expected = expected.removeprefix("sha256:")
    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise ValueError("exact_raw_sha256_required")
    with path.open("rb") as stream:
        raw = stream.read(64 * 1024 * 1024 + 1)
    if len(raw) > 64 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("receipt_bytes_pin_mismatch:" + path.name)
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("receipt_object_required")
    return raw, value


def prepare_contract(fit_receipt: Path, *, expected_fit_receipt_sha256: str) -> dict[str, Any]:
    """可信 raw pin 由 caller 提供；候選自述不是原訓練收據的替代品。"""
    from ml_module.personal_h20_gross_model_contract import H20GrossModelContract
    from ml_module.recommendation_training_lineage import read_recommendation_training_lineage

    _, receipt = _read_pinned(fit_receipt, expected_fit_receipt_sha256)
    if (receipt.get("schema_version") != "personal-source-unified-replay-fit.v1"
            or receipt.get("status") != "completed_candidate_created"
            or receipt.get("fit", {}).get("training_lineage_status") != "verified"):
        raise ValueError("original_verified_fit_receipt_required")
    saved = receipt["candidate"]
    root = Path(saved["candidate_root"])
    _, candidate = _read_pinned(root / "candidate.json", saved["candidate_json_sha256"])
    _, manifest = _read_pinned(root / "manifest.json", saved["manifest_sha256"])
    lineage_path = Path(saved["training_lineage_manifest_path"])
    _, lineage = _read_pinned(lineage_path, saved["training_lineage_manifest_sha256"])
    if (candidate["candidate_id"] != saved["candidate_id"]
            or candidate["artifact_hash"] != saved["artifact_hash"]
            or manifest["artifact_hash"] != saved["artifact_hash"]
            or candidate["manifest_hash"] != manifest["manifest_hash"]
            or candidate["training_lineage_manifest_path"] != str(lineage_path)):
        raise ValueError("original_fit_candidate_identity_mismatch")
    verified = read_recommendation_training_lineage(
        lineage_path,
        expected_manifest_hash=candidate["training_lineage_manifest_hash"],
        expected_dataset_hash=candidate["dataset_hash"],
        expected_candidate_id=candidate["candidate_id"],
    )
    if verified.manifest_hash != receipt["fit"]["training_lineage_manifest_hash"]:
        raise ValueError("fit_lineage_identity_mismatch")
    for field in ("training_source_hash", "training_pit_hash"):
        if candidate[field] != lineage[field]:
            raise ValueError("candidate_lineage_identity_mismatch:" + field)
    if candidate["training_cutoff"] != lineage["training_as_of"]:
        raise ValueError("candidate_lineage_cutoff_mismatch")
    contract = H20GrossModelContract(
        artifact_root=str(root), lineage_path=str(lineage_path),
        model_id=candidate["model_id"], model_version=candidate["model_version"],
        dataset_id=candidate["dataset_id"], dataset_hash=candidate["dataset_hash"],
        candidate_id=candidate["candidate_id"], model_family=candidate["model_family"],
        feature_schema=tuple(tuple(row) for row in candidate["feature_schema"]),
        feature_registry_hash=candidate["feature_registry_hash"],
        label_registry_hash=candidate["label_registry_hash"],
        manifest_hash=candidate["manifest_hash"],
        manifest_raw_sha256="sha256:" + saved["manifest_sha256"],
        artifact_hash=candidate["artifact_hash"],
        candidate_raw_sha256="sha256:" + saved["candidate_json_sha256"],
        lineage_hash=verified.manifest_hash,
        lineage_raw_sha256="sha256:" + saved["training_lineage_manifest_sha256"],
        training_source_hash=lineage["training_source_hash"],
        training_pit_hash=lineage["training_pit_hash"],
        training_as_of=candidate["training_as_of"],
        lineage_training_as_of=lineage["training_as_of"],
        installed_library_versions=manifest["library_versions"],
    )
    payload = {field.name: getattr(contract, field.name) for field in fields(contract)}
    payload["installed_library_versions"] = dict(contract.installed_library_versions)
    return {
        "schema_version": "personal-h20-gross-contract-preflight.v1",
        "fit_receipt": str(fit_receipt),
        "fit_receipt_raw_sha256": expected_fit_receipt_sha256,
        "contract": payload, "contract_hash": contract.contract_hash,
        "source_disclosures": receipt.get("replay", {}).get("source_disclosures", {}),
        "candidate_blockers": candidate.get("candidate_blockers", []),
        "holdout_evaluation": candidate.get("evaluation", {}),
        "lineage_reader": "ml_module.recommendation_training_lineage.read_recommendation_training_lineage",
        "artifact_deserialized": False, "fit_performed": False,
        "policy_activated": False, "task_changed": False,
        "daily_live_source_bound": False, "formal_eligible": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fit-receipt", required=True, type=Path)
    parser.add_argument("--fit-receipt-sha256", required=True)
    args = parser.parse_args(argv)
    payload = prepare_contract(args.fit_receipt, expected_fit_receipt_sha256=args.fit_receipt_sha256)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
