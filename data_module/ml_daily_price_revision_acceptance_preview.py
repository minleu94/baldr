"""建立修訂資料的唯讀、prospective research acceptance preview。

此入口只稽核已封存的 research-only 證據，不建立訓練列、不呼叫正式 PIT
gate、不寫入 SQLite，也不載入或訓練模型。所有缺少的 availability、feature
dependency 與 label maturity 證據都保持 pending，不以日曆推算補造標籤時間。
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
from typing import Any, Mapping


TRANSFER_SCHEMA = "research-only-artifact-transfer.v1"
MANIFEST_SCHEMA = "ml-daily-price-revision-research-dataset.v1"
EXPECTED_TRANSFER_RECEIPT_SHA256 = (
    "sha256:c0e0cb823d172c052db201351d7db0dc3d170f6b436003d37d4815ce28015fe4"
)
EXPECTED_DATASET_ID = "research_shadow_daily_price_revision_recovered_source_20260922"
EXPECTED_RUN_ID = "7e2f19cc5a00f20ba5b3890a"
EXPECTED_MANIFEST_SHA256 = (
    "sha256:f9a19b704fab86d0701091073d74353dec51dd1a8d3902fc46a6fb24ec1ba772"
)
EXPECTED_ROWS_SHA256 = (
    "sha256:506f464d92ead313c4fc0d15eaa4eb490b553e86e084701f7d4e93c34e796fb4"
)
EXPECTED_SNAPSHOT_SHA256 = (
    "sha256:38ab1d1dfd201285ed817c8e94f689f91a50b39dc30cdbb8a90a49b7ce898771"
)
EXPECTED_ROWS = 868
EXPECTED_FULL_REPAIR_COVERAGE = {
    "affected_rows": 75442,
    "after_cells": 1277135,
    "after_matches": 1277135,
    "after_mismatches": 0,
    "missing_current_rows": 0,
    "untouched_cells": 2117755,
    "untouched_mismatches": 0,
}
SUPPORTED_HORIZONS_TRADING_DAYS = (5, 10, 20, 60)

REQUIRED_ARCHIVE_PATHS = {
    "manifest": "revision_20260922_run02/research_source_dataset/runs/7e2f19cc5a00f20ba5b3890a/manifest.json",
    "rows": "revision_20260922_run02/research_source_dataset/runs/7e2f19cc5a00f20ba5b3890a/recovered_source_rows.jsonl",
    "snapshot": "revision_20260922_run02/inputs/twstock_snapshot_run02.db",
    "recovery": "revision_20260922_run02/evidence/recovery_receipt.json",
    "recovery_cell_diff": "revision_20260922_run02/evidence/recovery_cell_diff.jsonl",
    "recovery_affected_rows": "revision_20260922_run02/evidence/affected_row_hashes.jsonl",
    "verification": "revision_20260922_run02/evidence/technical_snapshot_verification.json",
    "gate_probe": "revision_20260922_run02/evidence/revision_training_gate_probe.json",
    "price_pending": "revision_20260922_run01/receipts/price_pending.json",
    "price_receipt": "revision_20260922_run01/receipts/price_receipt.json",
    "technical_pending": "revision_20260922_run01/receipts/technical_pending.json",
    "technical_receipt": "revision_20260922_run01/receipts/technical_receipt.json",
}
RECOVERY_INPUT_METADATA_PATHS = {
    "dryrun_manifest": "revision_20260922_run01/inputs/technical_repair_dryrun_manifest.json",
    "technical_before_backup": "revision_20260922_run01/inputs/technical_before_repair.db",
    "run02_before": "revision_20260922_run01/inputs/twstock_snapshot.db",
}

CONTRACT_SOURCE_PATHS = (
    "data_module/portfolio_ml_dataset_assembler.py",
    "ml_module/historical_contracts.py",
    "ml_module/allocation_contracts.py",
    "ml_module/feature_registry.py",
    "ml_module/allocation_feature_contract.py",
)
REPO_ROOT = Path(__file__).resolve().parents[1]


class AcceptancePreviewError(ValueError):
    """封存資料、時間或輸出邊界不符合 preview 契約。"""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _no_reparse_path(path: Path, *, stop: Path | None = None) -> None:
    """拒絕符號連結或 Windows reparse point，避免跨越隔離根。"""
    current = path
    stop_resolved = stop.resolve() if stop is not None and stop.exists() else stop
    while True:
        if current.exists():
            info = current.lstat()
            reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
            if current.is_symlink() or getattr(info, "st_file_attributes", 0) & reparse:
                raise AcceptancePreviewError(f"reparse path is not allowed: {current}")
        if stop_resolved is not None and current == stop_resolved:
            break
        parent = current.parent
        if parent == current:
            break
        current = parent


def _json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptancePreviewError(f"{label} is unreadable: {path}") from exc
    if not isinstance(payload, dict):
        raise AcceptancePreviewError(f"{label} must be a JSON object")
    return payload


def _aware(value: object, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise AcceptancePreviewError(f"{label} must be an aware ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AcceptancePreviewError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _sealed_body_hash(payload: Mapping[str, Any], field: str, label: str) -> str:
    supplied = payload.get(field)
    body = dict(payload)
    body.pop(field, None)
    expected = _sha256_bytes(_canonical(body) + b"\n")
    if supplied != expected:
        raise AcceptancePreviewError(f"{label} body hash does not match")
    return str(supplied)


def _resolve_archive_file(root: Path, relative: str) -> Path:
    pure = PurePosixPath(relative.replace("\\", "/"))
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise AcceptancePreviewError(f"unsafe archive-relative path: {relative}")
    path = root.joinpath(*pure.parts)
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise AcceptancePreviewError(f"archive path escaped its root: {relative}") from exc
    _no_reparse_path(path, stop=root)
    if not path.is_file():
        raise AcceptancePreviewError(f"archive file is missing: {relative}")
    return path


def _transfer_inventory(root: Path, expected_receipt_sha256: str) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    transfer_path = root / "transfer_receipt.json"
    _no_reparse_path(transfer_path, stop=root)
    if not transfer_path.is_file():
        raise AcceptancePreviewError("transfer_receipt.json is missing")
    actual_transfer_hash = _sha256_file(transfer_path)
    if actual_transfer_hash != expected_receipt_sha256:
        raise AcceptancePreviewError("transfer receipt SHA-256 does not match the approved archive")
    receipt = _json_object(transfer_path, "transfer receipt")
    if receipt.get("schema_version") != TRANSFER_SCHEMA:
        raise AcceptancePreviewError("transfer receipt schema is unsupported")
    if receipt.get("purpose") != "immutable research and audit custody; not a model release or formal data source":
        raise AcceptancePreviewError("archive purpose is not research-only custody")
    if receipt.get("destination_preexisted") is not False:
        raise AcceptancePreviewError("archive destination was not create-only")
    declared_root = Path(str(receipt.get("destination_root", ""))).resolve()
    if os.path.normcase(str(declared_root)) != os.path.normcase(str(root.resolve())):
        raise AcceptancePreviewError("transfer receipt destination does not match archive root")
    files = receipt.get("files")
    if not isinstance(files, list) or len(files) != receipt.get("total_file_count"):
        raise AcceptancePreviewError("transfer receipt file inventory is incomplete")
    if not 1 <= len(files) <= 100:
        raise AcceptancePreviewError("transfer receipt inventory exceeds bounded limit")
    inventory: dict[str, dict[str, Any]] = {}
    total_size = 0
    for item in files:
        if not isinstance(item, Mapping):
            raise AcceptancePreviewError("transfer receipt contains an invalid file entry")
        relative = str(item.get("destination_relative_path", ""))
        if relative in inventory:
            raise AcceptancePreviewError(f"duplicate transfer inventory path: {relative}")
        path = _resolve_archive_file(root, relative)
        size = item.get("size_bytes")
        sha = item.get("sha256")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise AcceptancePreviewError(f"invalid transfer size for {relative}")
        if path.stat().st_size != size or not isinstance(sha, str):
            raise AcceptancePreviewError(f"transfer size metadata differs for {relative}")
        inventory[relative] = {"path": path, "size_bytes": size, "sha256": sha}
        total_size += size
    if total_size != receipt.get("total_size_bytes"):
        raise AcceptancePreviewError("transfer receipt total size does not match inventory")
    return inventory, {
        "receipt_path": str(transfer_path.resolve()),
        "receipt_sha256": actual_transfer_hash,
        "declared_file_count": len(files),
        "declared_total_size_bytes": total_size,
    }


def _verify_selected_file(
    inventory: Mapping[str, Mapping[str, Any]], relative: str, label: str
) -> tuple[Path, str]:
    entry = inventory.get(relative)
    if not isinstance(entry, Mapping):
        raise AcceptancePreviewError(f"transfer receipt lacks required {label}: {relative}")
    path = Path(str(entry["path"]))
    actual = _sha256_file(path)
    if actual != entry.get("sha256"):
        raise AcceptancePreviewError(f"archived {label} SHA-256 differs from transfer receipt")
    return path, actual


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                raise AcceptancePreviewError(f"blank source row at line {number}")
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AcceptancePreviewError(f"invalid JSON source row at line {number}") from exc
            if not isinstance(value, dict):
                raise AcceptancePreviewError(f"source row {number} is not an object")
            rows.append(value)
            if len(rows) > EXPECTED_ROWS:
                raise AcceptancePreviewError("source row count exceeds the bounded limit")
    return rows


def _validate_rows(rows: list[dict[str, Any]], manifest: Mapping[str, Any]) -> dict[str, int]:
    artifact = manifest.get("artifact")
    if not isinstance(artifact, Mapping) or artifact.get("row_count") != EXPECTED_ROWS:
        raise AcceptancePreviewError("manifest row count is not the approved 868-row source")
    if len(rows) != EXPECTED_ROWS:
        raise AcceptancePreviewError("recovered source rows do not contain exactly 868 records")
    keys: set[tuple[str, str]] = set()
    complete = 0
    missing = 0
    source_revision = manifest.get("source_revision")
    technical_evidence = manifest.get("technical_repair_evidence")
    if not isinstance(source_revision, Mapping) or not isinstance(technical_evidence, Mapping):
        raise AcceptancePreviewError("manifest source revision/technical evidence block is missing")
    observed_at = source_revision.get("observed_at") or manifest.get("created_at")
    if not isinstance(observed_at, str):
        observed_at = manifest.get("created_at")
    _aware(observed_at, "source observed_at")
    for index, row in enumerate(rows, 1):
        key = (str(row.get("date", "")), str(row.get("symbol", "")))
        if not all(key) or key in keys:
            raise AcceptancePreviewError(f"source row {index} has an empty or duplicate identity")
        keys.add(key)
        revision = row.get("source_revision")
        technical = row.get("technical_indicators")
        if (
            row.get("dataset_id") != EXPECTED_DATASET_ID
            or not isinstance(revision, Mapping)
            or not isinstance(technical, Mapping)
            or not technical
        ):
            raise AcceptancePreviewError(f"source row {index} lacks price/technical custody")
        if (
            revision.get("availability_status") != "late_obtained"
            or revision.get("historical_available_at") is not None
            or revision.get("historical_decision_time_available") is not False
            or revision.get("source_db_snapshot_sha256") != EXPECTED_SNAPSHOT_SHA256
            or revision.get("observed_at") != manifest.get("created_at")
            or revision.get("repair_receipt_sha256") != source_revision.get("final_receipt_sha256")
            or revision.get("isolated_recovery_receipt_sha256")
            != technical_evidence.get("recovery_receipt_sha256")
            or revision.get("technical_repair_receipt_sha256")
            != technical_evidence.get("receipt_file_sha256")
        ):
            raise AcceptancePreviewError(f"source row {index} makes an unsupported historical-availability claim")
        if row.get("feature_contract_status") != "not_assessed":
            raise AcceptancePreviewError(f"source row {index} has an unexpected feature-contract status")
        if row.get("label_status") != "not_materialized":
            raise AcceptancePreviewError(f"source row {index} has an unexpected label status")
        status = row.get("price_row_status")
        missing_fields = row.get("missing_source_fields")
        if not isinstance(missing_fields, list):
            raise AcceptancePreviewError(f"source row {index} lacks missing-field evidence")
        if status == "complete_ohlc" and not missing_fields:
            complete += 1
        elif status == "missing_ohlc_excluded_from_fit" and missing_fields:
            missing += 1
        else:
            raise AcceptancePreviewError(f"source row {index} has inconsistent OHLC completeness")
    quality = manifest.get("price_row_quality")
    if not isinstance(quality, Mapping) or (
        quality.get("total_rows"), quality.get("complete_ohlc_rows"), quality.get("missing_ohlc_rows")
    ) != (EXPECTED_ROWS, complete, missing):
        raise AcceptancePreviewError("manifest complete/missing OHLC counts do not match source rows")
    return {"total_rows": len(rows), "complete_ohlc_rows": complete, "missing_ohlc_rows": missing}


def _validate_lineage(
    *, manifest: Mapping[str, Any], inventory: Mapping[str, Mapping[str, Any]],
    selected_hashes: Mapping[str, str],
) -> dict[str, Any]:
    identity = manifest.get("authoritative_identity")
    if manifest.get("schema_version") != MANIFEST_SCHEMA or not isinstance(identity, Mapping):
        raise AcceptancePreviewError("research-source manifest schema/identity is unsupported")
    if (
        manifest.get("dataset_id") != EXPECTED_DATASET_ID
        or manifest.get("run_id") != EXPECTED_RUN_ID
        or identity.get("dataset_id") != EXPECTED_DATASET_ID
        or identity.get("run_id") != EXPECTED_RUN_ID
    ):
        raise AcceptancePreviewError("preview input is not the authoritative v2 research-source identity")
    if selected_hashes.get(REQUIRED_ARCHIVE_PATHS["manifest"]) != EXPECTED_MANIFEST_SHA256:
        raise AcceptancePreviewError("authoritative v2 manifest file hash differs")
    if selected_hashes.get(REQUIRED_ARCHIVE_PATHS["rows"]) != EXPECTED_ROWS_SHA256:
        raise AcceptancePreviewError("authoritative v2 source rows hash differs")
    if selected_hashes.get(REQUIRED_ARCHIVE_PATHS["snapshot"]) != EXPECTED_SNAPSHOT_SHA256:
        raise AcceptancePreviewError("run02 SQLite snapshot hash differs")
    artifact = manifest.get("artifact")
    snapshot = manifest.get("snapshot")
    revision = manifest.get("source_revision")
    technical = manifest.get("technical_repair_evidence")
    coverage = manifest.get("coverage")
    eligibility = manifest.get("eligibility")
    if not all(isinstance(block, Mapping) for block in (artifact, snapshot, revision, technical, coverage, eligibility)):
        raise AcceptancePreviewError("manifest is missing a required evidence block")
    if (
        artifact.get("sha256") != EXPECTED_ROWS_SHA256
        or snapshot.get("sha256") != EXPECTED_SNAPSHOT_SHA256
        or snapshot.get("size_bytes") != inventory[REQUIRED_ARCHIVE_PATHS["snapshot"]]["size_bytes"]
        or revision.get("final_receipt_sha256") != selected_hashes[REQUIRED_ARCHIVE_PATHS["price_receipt"]]
        or revision.get("pending_receipt_sha256") != selected_hashes[REQUIRED_ARCHIVE_PATHS["price_pending"]]
        or revision.get("technical_pending_marker_sha256") != selected_hashes[REQUIRED_ARCHIVE_PATHS["technical_pending"]]
        or technical.get("receipt_file_sha256") != selected_hashes[REQUIRED_ARCHIVE_PATHS["technical_receipt"]]
        or technical.get("recovery_receipt_sha256") != selected_hashes[REQUIRED_ARCHIVE_PATHS["recovery"]]
        or technical.get("tracked_verification_file_sha256") != selected_hashes[REQUIRED_ARCHIVE_PATHS["verification"]]
        or technical.get("recovery_cell_diff_sha256") != selected_hashes[REQUIRED_ARCHIVE_PATHS["recovery_cell_diff"]]
        or technical.get("recovery_row_hashes_sha256") != selected_hashes[REQUIRED_ARCHIVE_PATHS["recovery_affected_rows"]]
        or snapshot.get("sqlite_mode") != "read_only_query_only"
        or not isinstance(snapshot.get("sidecars"), Mapping)
        or snapshot["sidecars"].get("-wal") != 0
        or inventory.get(REQUIRED_ARCHIVE_PATHS["snapshot"] + "-wal", {}).get("size_bytes") != 0
        or snapshot["sidecars"].get("-shm") != inventory.get(
            REQUIRED_ARCHIVE_PATHS["snapshot"] + "-shm", {}
        ).get("size_bytes")
    ):
        raise AcceptancePreviewError("manifest is not bound to the selected archived source bytes")
    if (
        revision.get("availability_status") != "late_obtained"
        or revision.get("historical_available_at") is not None
        or revision.get("historical_decision_time_available") is not False
        or revision.get("pending_marker_preserved") is not True
        or revision.get("pending_marker_still_blocks_formal_pit") is not True
    ):
        raise AcceptancePreviewError("source revision must remain late-obtained and PIT-blocked")
    if (
        artifact.get("feature_contract_status") != "not_assessed"
        or artifact.get("labels_materialized") is not False
        or artifact.get("label_maturity_status") != "not_materialized"
        or artifact.get("model_training_input_compatible") is not False
    ):
        raise AcceptancePreviewError("source manifest does not preserve the expected fit blockers")
    if eligibility.get("research_only") is not True or any(eligibility.get(key) is not False for key in (
        "formal_training_allowed", "formal_oos_allowed", "historical_pit_allowed",
        "promotion_eligible", "labels_available_for_fit",
    )) or eligibility.get("production_alpha_bp") != 0:
        raise AcceptancePreviewError("source manifest contains an enabled formal/release flag")
    if coverage.get("full_repair_window_after_cells_verified") != EXPECTED_FULL_REPAIR_COVERAGE["after_cells"] or coverage.get(
        "full_repair_window_untouched_cells_verified"
    ) != EXPECTED_FULL_REPAIR_COVERAGE["untouched_cells"]:
        raise AcceptancePreviewError("full repair-window coverage differs from verified evidence")
    return {"identity": dict(identity), "created_at": str(manifest.get("created_at"))}


def build_revision_acceptance_preview(
    *, archive_root: Path, training_as_of: str,
    expected_transfer_receipt_sha256: str = EXPECTED_TRANSFER_RECEIPT_SHA256,
    output_root: Path | None = None,
) -> dict[str, Any]:
    """驗證封存 lineage 並 create-only 產生 research eligibility preview。"""
    raw_root = archive_root.expanduser().absolute()
    if not raw_root.exists() or not raw_root.is_dir():
        raise AcceptancePreviewError("archive root must be a directory")
    _no_reparse_path(raw_root)
    root = raw_root.resolve(strict=True)
    as_of = _aware(training_as_of, "training_as_of")
    inventory, transfer = _transfer_inventory(root, expected_transfer_receipt_sha256)
    selected_paths = tuple(REQUIRED_ARCHIVE_PATHS.values())
    selected_hashes: dict[str, str] = {}
    selected_files: dict[str, Path] = {}
    for label, relative in REQUIRED_ARCHIVE_PATHS.items():
        path, actual = _verify_selected_file(inventory, relative, label)
        selected_files[label] = path
        selected_hashes[relative] = actual

    manifest = _json_object(selected_files["manifest"], "research-source manifest")
    row_bytes = selected_files["rows"].read_bytes()
    if _sha256_bytes(row_bytes) != EXPECTED_ROWS_SHA256:
        raise AcceptancePreviewError("source-row JSONL SHA-256 differs")
    rows = _read_jsonl(selected_files["rows"])
    row_counts = _validate_rows(rows, manifest)
    source_identity = _validate_lineage(
        manifest=manifest, inventory=inventory, selected_hashes=selected_hashes
    )

    price_pending = _json_object(selected_files["price_pending"], "price pending marker")
    price_receipt = _json_object(selected_files["price_receipt"], "price repair receipt")
    technical_pending = _json_object(selected_files["technical_pending"], "technical pending marker")
    technical_receipt = _json_object(selected_files["technical_receipt"], "technical repair receipt")
    recovery = _json_object(selected_files["recovery"], "isolated recovery receipt")
    verification = _json_object(selected_files["verification"], "tracked technical verifier evidence")
    gate_probe = _json_object(selected_files["gate_probe"], "archived negative gate probe")

    price_body_hash = _sealed_body_hash(price_receipt, "receipt_sha256", "price repair receipt")
    technical_body_hash = _sealed_body_hash(technical_receipt, "receipt_sha256", "technical repair receipt")
    recovery_body_hash = _sealed_body_hash(recovery, "receipt_sha256", "recovery receipt")
    verification_hash = _sealed_body_hash(verification, "evidence_sha256", "technical verifier evidence")
    if (
        price_pending.get("status") != "applied_receipt_written"
        or price_receipt.get("status") != "applied"
        or price_receipt.get("available_at") is not None
        or price_receipt.get("historical_decision_time_available") is not False
        or price_receipt.get("formal_training_allowed") is not False
        or price_receipt.get("promotion_eligible") is not False
        or technical_pending.get("status") != "receipt_written"
        or technical_receipt.get("status") != "applied"
        or technical_receipt.get("available_at") is not None
        or technical_receipt.get("formal_training_allowed") is not False
        or technical_receipt.get("promotion_eligible") is not False
        or technical_receipt.get("price_receipt_sha256") != price_receipt.get("receipt_sha256")
    ):
        raise AcceptancePreviewError("source/pending receipt state no longer matches sealed research evidence")
    if (
        recovery.get("status") != "passed"
        or recovery.get("research_candidate_only") is not True
        or recovery.get("formal_data_written") is not False
        or recovery.get("formal_training_allowed") is not False
        or recovery.get("historical_pit_eligible") is not False
        or recovery.get("promotion_eligible") is not False
        or recovery.get("database_sha256_after") != EXPECTED_SNAPSHOT_SHA256
        or not isinstance(recovery.get("pending_state"), Mapping)
        or recovery["pending_state"].get("changed") is not False
        or not isinstance(recovery.get("rows"), Mapping)
        or recovery["rows"].get("plan_external_before_sha256") != recovery["rows"].get("plan_external_after_sha256")
    ):
        raise AcceptancePreviewError("isolated recovery receipt is not a passed non-release recovery")
    recovery_inputs = recovery.get("input_hashes")
    expected_recovery_inputs = {
        "price_pending_file": selected_hashes[REQUIRED_ARCHIVE_PATHS["price_pending"]],
        "price_receipt_file": selected_hashes[REQUIRED_ARCHIVE_PATHS["price_receipt"]],
        "technical_pending_file": selected_hashes[REQUIRED_ARCHIVE_PATHS["technical_pending"]],
        "technical_receipt_file": selected_hashes[REQUIRED_ARCHIVE_PATHS["technical_receipt"]],
    }
    if not isinstance(recovery_inputs, Mapping) or any(
        recovery_inputs.get(key) != value for key, value in expected_recovery_inputs.items()
    ):
        raise AcceptancePreviewError("recovery receipt input hashes differ from archived source receipts")
    if any(
        recovery_inputs.get(key) != inventory[relative]["sha256"]
        for key, relative in RECOVERY_INPUT_METADATA_PATHS.items()
    ):
        raise AcceptancePreviewError("recovery receipt backup/plan inputs differ from transfer inventory")
    verifier_coverage = verification.get("coverage")
    if (
        verification.get("status") != "passed"
        or verification.get("purpose") != "late_obtained_research_source_evidence_only"
        or verification.get("formal_pit_gate_changed") is not False
        or verification.get("historical_available_at") is not None
        or not isinstance(verification.get("snapshot"), Mapping)
        or verification["snapshot"].get("sha256_after") != EXPECTED_SNAPSHOT_SHA256
        or not isinstance(verifier_coverage, Mapping)
        or any(verifier_coverage.get(key) != value for key, value in EXPECTED_FULL_REPAIR_COVERAGE.items())
    ):
        raise AcceptancePreviewError("tracked verifier evidence does not prove the sealed repair window")
    verifier_identity = verification.get("receipt_identity")
    if not isinstance(verifier_identity, Mapping) or any(
        verifier_identity.get(key) != value for key, value in {
            "price_receipt_file_sha256": selected_hashes[REQUIRED_ARCHIVE_PATHS["price_receipt"]],
            "technical_receipt_file_sha256": selected_hashes[REQUIRED_ARCHIVE_PATHS["technical_receipt"]],
            "price_receipt_body_sha256": price_body_hash,
            "technical_receipt_body_sha256": technical_body_hash,
            "technical_price_receipt_identity_match": True,
        }.items()
    ):
        raise AcceptancePreviewError("tracked verifier receipt identities differ from archived receipts")
    technical_evidence = manifest.get("technical_repair_evidence")
    if not isinstance(technical_evidence, Mapping) or (
        technical_evidence.get("recovery_receipt_body_sha256") != recovery_body_hash
        or technical_evidence.get("tracked_verification_evidence_sha256") != verification_hash
    ):
        raise AcceptancePreviewError("manifest does not bind recovery/verifier body identities")
    gate_results = gate_probe.get("results")
    if not isinstance(gate_results, list):
        raise AcceptancePreviewError("archived gate probe is missing result records")
    formal_failures = {
        str(item.get("symbols", [""])[0]): item.get("error_type")
        for item in gate_results
        if isinstance(item, Mapping) and item.get("call") == "check_daily_price_source_revision"
    }
    union_failure = next((item for item in gate_results if isinstance(item, Mapping) and item.get("call") == "validate_research_training_publication"), None)
    if set(formal_failures) != {"0050", "1256", "1477"} or any(
        value != "DailyPriceSourceRevisionError" for value in formal_failures.values()
    ) or not isinstance(union_failure, Mapping) or union_failure.get("error_type") != "ValueError":
        raise AcceptancePreviewError("archived negative gate probe does not contain expected bounded refusals")
    if (
        gate_probe.get("dataset_manifest_sha256") != selected_hashes[REQUIRED_ARCHIVE_PATHS["manifest"]]
        or gate_probe.get("dataset_rows_sha256") != selected_hashes[REQUIRED_ARCHIVE_PATHS["rows"]]
        or gate_probe.get("snapshot_sha256") != EXPECTED_SNAPSHOT_SHA256
    ):
        raise AcceptancePreviewError("archived negative gate probe is bound to different source bytes")

    observed = _aware(manifest.get("created_at"), "manifest.created_at")
    rows_preview: list[dict[str, Any]] = []
    for row in rows:
        revision = row["source_revision"]
        source_observed = _aware(revision.get("observed_at"), "row.source_revision.observed_at")
        known_by_training_as_of = source_observed <= as_of
        labels = [
            {
                "horizon_trading_days": horizon,
                "horizon_end_date": None,
                "horizon_end_date_status": "not_materialized_in_source_artifact",
                "label_available_at": None,
                "availability_evidence_status": "missing",
                "available_by_training_as_of": None,
                "maturity_status": "pending_evidence",
            }
            for horizon in SUPPORTED_HORIZONS_TRADING_DAYS
        ]
        rows_preview.append({
            "symbol": str(row["symbol"]),
            "decision_source_date": str(row["date"]),
            "price_row_status": str(row["price_row_status"]),
            "missing_source_fields": list(row["missing_source_fields"]),
            "source_revision": {
                "availability_status": "late_obtained",
                "corrected_at": manifest["source_revision"].get("corrected_at"),
                "historical_available_at": None,
                "exact_source_available_at": None,
                "custody_observed_at": source_observed.isoformat(),
                "custody_observed_by_training_as_of": known_by_training_as_of,
                "historical_decision_time_available": False,
                "late_obtained": True,
            },
            "feature_dependency": {
                "price_and_technical_source_row_present": True,
                "source_row_technical_keys": len(row["technical_indicators"]),
                "repair_window_source_row_verified": True,
                "full_repair_window_after_cells_verified": EXPECTED_FULL_REPAIR_COVERAGE["after_cells"],
                "downstream_feature_dependency_recomputed": False,
                "model_feature_registry_bound": False,
                "feature_order_dtype_missing_policy_verified": False,
                "decision_time_feature_eligibility": False,
                "status": "pending_full_feature_rebuild_and_contract_validation",
            },
            "labels": labels,
            "fit_eligible": False,
        })

    blockers = [
        "complete model feature dependency and recomputation lineage is not present in the custody artifact",
        "feature names, order, dtypes, and missing-value policy have not been checked against a selected model contract",
        "label rows and per-horizon available_at evidence are not materialized; maturity remains unproven",
        "historical available_at is null, so the corrected value cannot support a 2026-05-20 PIT claim",
    ]
    if as_of < observed:
        blockers.append("training_as_of predates the first verified custody snapshot")
    contract_hashes: dict[str, str] = {}
    repo_root = REPO_ROOT
    for relative in CONTRACT_SOURCE_PATHS:
        source = repo_root / relative
        if not source.is_file():
            raise AcceptancePreviewError(f"required contract source is missing: {relative}")
        contract_hashes[relative] = _sha256_file(source)

    preview: dict[str, Any] = {
        "schema_version": "ml-daily-price-revision-acceptance-preview.v1",
        "status": "preview_complete_candidate_not_accepted",
        "research_only": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "training_as_of": as_of.isoformat(),
        "research_candidate_semantics": "late_obtained_corrected_history_for_future_research_only",
        "identity": source_identity["identity"],
        "archive_provenance": {
            **transfer,
            "archive_root": str(root),
            "archive_inventory_sizes_checked": transfer["declared_file_count"],
            "selected_content_hashes_recomputed": len(selected_hashes),
            "selected_content_hash_paths": sorted(selected_hashes),
            "full_26_file_content_hashes_recomputed": False,
            "selected_sha256": dict(sorted(selected_hashes.items())),
        },
        "source_custody": {
            "row_counts": row_counts,
            "rows_sha256": EXPECTED_ROWS_SHA256,
            "snapshot_sha256": EXPECTED_SNAPSHOT_SHA256,
            "snapshot_bytes_rehashed": True,
            "price_receipt_sha256": selected_hashes[REQUIRED_ARCHIVE_PATHS["price_receipt"]],
            "technical_receipt_sha256": selected_hashes[REQUIRED_ARCHIVE_PATHS["technical_receipt"]],
            "recovery_receipt_sha256": selected_hashes[REQUIRED_ARCHIVE_PATHS["recovery"]],
            "technical_verifier_file_sha256": selected_hashes[REQUIRED_ARCHIVE_PATHS["verification"]],
            "technical_verifier_body_sha256": verification_hash,
            "revision_gate_probe_sha256": selected_hashes[REQUIRED_ARCHIVE_PATHS["gate_probe"]],
            "pending_markers_preserved": True,
            "late_obtained": True,
            "custody_observed_at": observed.isoformat(),
            "exact_source_available_at": None,
        },
        "feature_assessment": {
            "status": "not_assessed_for_selected_model_contract",
            "full_repair_window_rows": EXPECTED_FULL_REPAIR_COVERAGE["affected_rows"],
            "full_repair_window_after_cells_verified": EXPECTED_FULL_REPAIR_COVERAGE["after_cells"],
            "full_repair_window_untouched_cells_verified": EXPECTED_FULL_REPAIR_COVERAGE["untouched_cells"],
            "repair_window_verifier_status": "passed",
            "downstream_feature_rebuild_evidence": False,
            "feature_order_dtype_missing_policy_verified": False,
            "feature_contract_source_sha256": contract_hashes,
            "required_evidence": [
                "selected model family and authoritative feature registry identity",
                "complete corrected price/technical rolling dependency rebuild for every fit row",
                "exact feature names, order, dtypes, and missing-value behavior",
                "row-level source availability compatible with the declared future-research semantics",
            ],
        },
        "label_assessment": {
            "status": "pending_label_materialization_and_availability_proof",
            "supported_horizons_trading_days": list(SUPPORTED_HORIZONS_TRADING_DAYS),
            "historical_core_label_registry_horizon_trading_days": 20,
            "horizon_end_dates_materialized": False,
            "label_available_at_evidence_present": False,
            "maturity_at_training_as_of": "unproven",
            "required_contract_source_sha256": {
                path: contract_hashes[path]
                for path in CONTRACT_SOURCE_PATHS
                if path in {
                    "data_module/portfolio_ml_dataset_assembler.py",
                    "ml_module/historical_contracts.py",
                    "ml_module/allocation_contracts.py",
                }
            },
            "required_evidence": [
                "derive each horizon_end_date from the exact trading-session sequence",
                "prove label.available_at <= training_as_of from source publication evidence",
                "apply existing gap, corporate-action, dtype, and missing-label exclusions",
            ],
        },
        "existing_gate_probe": {
            "formal_gate_failures": formal_failures,
            "research_union_validator_error_type": union_failure.get("error_type"),
            "research_union_validator_error": union_failure.get("error"),
            "probe_reused_without_rerunning_formal_gate": True,
        },
        "decision": {
            "future_research_candidate_accepted": False,
            "future_research_candidate_status": "pending_feature_and_label_evidence",
            "historical_pit_eligible": False,
            "formal_training_allowed": False,
            "formal_oos_allowed": False,
            "formal_data_written": False,
            "promotion_eligible": False,
            "production_alpha_bp": 0,
            "model_training_input_compatible": False,
            "database_write_performed": False,
            "fit_performed": False,
            "model_loaded": False,
            "blockers": blockers,
        },
        "rows": rows_preview,
    }
    run_identity = {
        "transfer_receipt_sha256": transfer["receipt_sha256"],
        "selected_sha256": selected_hashes,
        "training_as_of": as_of.isoformat(),
        "contract_source_sha256": contract_hashes,
    }
    run_id = hashlib.sha256(_canonical(run_identity)).hexdigest()[:24]
    preview["preview_run_id"] = run_id
    output_base = output_root or repo_root / "output" / "qa" / "revision_aware_acceptance_preview"
    base = output_base.expanduser().resolve(strict=False)
    safe_root = (repo_root / "output" / "qa").resolve(strict=False)
    try:
        base.relative_to(safe_root)
    except ValueError as exc:
        raise AcceptancePreviewError("preview output must stay under ignored output/qa") from exc
    _no_reparse_path(base, stop=safe_root if safe_root.exists() else None)
    run_dir = base / "runs" / run_id
    if run_dir.exists():
        raise FileExistsError(f"create-only preview already exists: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=False)
    output_path = run_dir / "acceptance_preview.json"
    payload = _canonical(preview) + b"\n"
    temporary = run_dir / ".acceptance_preview.json.tmp"
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.rename(output_path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return {
        "status": preview["status"],
        "preview_run_id": run_id,
        "output_path": str(output_path.resolve()),
        "output_sha256": _sha256_file(output_path),
        "row_count": row_counts["total_rows"],
        "complete_ohlc_rows": row_counts["complete_ohlc_rows"],
        "missing_ohlc_rows": row_counts["missing_ohlc_rows"],
        "fit_performed": False,
        "formal_training_allowed": False,
        "historical_pit_eligible": False,
    }
