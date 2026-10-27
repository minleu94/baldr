"""Save a candidate-only human disposition for one weekly collection row."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any, Mapping

from app_module.evidence_weekly_approval_input import (
    FAILED_STATUS,
    PENDING_STATUS,
    SCHEMA_VERSION as APPROVAL_PACKET_SCHEMA_VERSION,
    build_weekly_approval_input,
)


SCHEMA_VERSION = "evidence-weekly-review-decision.v1"
ALLOWED_DECISIONS = frozenset({"reviewed", "dismissed", "follow_up"})
_FORBIDDEN_PROJECTION_FLAGS = (
    "formal_credit_authorized",
    "production_scheduler_allowed",
    "write_performed",
    "approved_projection_emitted",
)


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _required_text(value: object, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    return text


def _review_timestamp(value: str | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        )
    text = _required_text(value, "reviewed_at")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("reviewed_at must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("reviewed_at must include a timezone")
    return text


def _is_formal_database_path(path: Path) -> bool:
    normalized = path.as_posix().casefold()
    return (
        path.name.casefold() == "twstock.db"
        or "/fa_data/sqlite/" in normalized
        or "/data_root/sqlite/" in normalized
    )


def _validate_output_path(output_path: str | Path, sidecar_path: Path) -> Path:
    output = Path(output_path).expanduser().resolve(strict=False)
    if output == sidecar_path:
        raise ValueError("review decision output must not overwrite the source sidecar")
    if _is_formal_database_path(output):
        raise ValueError("review decision output must not target a formal database path")
    if output.exists():
        raise ValueError("review decision output already exists; choose a new file")
    if not output.parent.is_dir():
        raise ValueError("review decision output parent must already exist")
    return output


def _validate_packet_matches_sidecar(
    packet: Mapping[str, Any],
    sidecar_path: Path,
    *,
    artifact_manifest_path: str | Path | None = None,
    authorized_receipt_root: str | Path | None = None,
) -> dict[str, Any]:
    if packet.get("schema_version") != APPROVAL_PACKET_SCHEMA_VERSION:
        raise ValueError("approval packet schema is unsupported")
    if packet.get("candidate_only") is not True:
        raise ValueError("approval packet must remain candidate-only")
    for flag in _FORBIDDEN_PROJECTION_FLAGS:
        if packet.get(flag) is not False:
            raise ValueError(f"approval packet flag must remain false: {flag}")

    try:
        packet_sidecar = Path(str(packet.get("sidecar_path") or "")).expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        raise ValueError("approval packet sidecar path is invalid") from exc
    if packet_sidecar != sidecar_path:
        raise ValueError("approval packet sidecar path does not match the supplied sidecar")

    records = packet.get("records")
    if not isinstance(records, list):
        raise ValueError("approval packet records must be an array")
    include_failed = any(
        isinstance(record, Mapping)
        and record.get("collection_status") == FAILED_STATUS
        for record in records
    )
    owner_role = str(packet.get("owner_role") or "")
    reviewer_role = str(packet.get("reviewer_role") or "")
    selected_manifest = artifact_manifest_path
    if selected_manifest is None:
        selected_manifest = packet.get("artifact_manifest_path")
    selected_root = authorized_receipt_root
    if selected_root is None and selected_manifest is not None:
        selected_root = Path(str(selected_manifest)).expanduser().resolve(strict=False).parent

    before_sha = _sha256_file(sidecar_path)
    current = build_weekly_approval_input(
        sidecar_path,
        owner_role=owner_role,
        reviewer_role=reviewer_role,
        include_failed=include_failed,
        artifact_manifest_path=selected_manifest,
        authorized_receipt_root=selected_root,
    )
    after_sha = _sha256_file(sidecar_path)
    if before_sha != after_sha or current.get("sidecar_sha256") != after_sha:
        raise ValueError("source sidecar changed while rebuilding the approval packet")
    if packet.get("sidecar_sha256") != after_sha:
        raise ValueError("approval packet sidecar SHA-256 is stale")

    generated_at = packet.get("generated_at")
    if not isinstance(generated_at, str) or not generated_at.strip():
        raise ValueError("approval packet generated_at is required")
    try:
        generated = datetime.fromisoformat(generated_at.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("approval packet generated_at is invalid") from exc
    if generated.tzinfo is None or generated.utcoffset() is None:
        raise ValueError("approval packet generated_at must include a timezone")

    expected = dict(current)
    expected["generated_at"] = generated_at
    if dict(packet) != expected:
        raise ValueError("approval packet does not match the current sidecar state")
    return current


def write_weekly_review_decision_artifact(
    packet: Mapping[str, Any],
    sidecar_path: str | Path,
    *,
    collection_id: str,
    owner_name: str,
    owner_role: str,
    reviewer_name: str,
    reviewer_role: str,
    decision: str,
    note: str,
    output_path: str | Path,
    reviewed_at: str | None = None,
    artifact_manifest_path: str | Path | None = None,
    authorized_receipt_root: str | Path | None = None,
) -> Path:
    """Write a new candidate-only decision artifact after revalidating its source.

    The artifact records a human disposition for one pending collection. It does
    not write weekly history, an approval projection, scheduler state, or Gate
    credit. ``reviewed`` is a disposition label, not a Gate acceptance.
    """

    if not isinstance(packet, Mapping):
        raise ValueError("approval packet must be an object")
    selected_collection_id = _required_text(collection_id, "collection_id")
    selected_owner_name = _required_text(owner_name, "owner_name")
    selected_owner_role = _required_text(owner_role, "owner_role")
    selected_reviewer_name = _required_text(reviewer_name, "reviewer_name")
    selected_reviewer_role = _required_text(reviewer_role, "reviewer_role")
    selected_decision = _required_text(decision, "decision").casefold()
    if selected_decision not in ALLOWED_DECISIONS:
        raise ValueError("decision must be reviewed, dismissed, or follow_up")
    selected_note = _required_text(note, "note")
    timestamp = _review_timestamp(reviewed_at)

    resolved_sidecar = Path(sidecar_path).expanduser().resolve(strict=False)
    if not resolved_sidecar.is_file():
        raise ValueError("source sidecar must be a regular file")
    current_packet = _validate_packet_matches_sidecar(
        packet,
        resolved_sidecar,
        artifact_manifest_path=artifact_manifest_path,
        authorized_receipt_root=authorized_receipt_root,
    )
    matches = [
        record
        for record in current_packet["records"]
        if record.get("collection_id") == selected_collection_id
    ]
    if len(matches) != 1:
        raise ValueError("collection_id must identify exactly one packet record")
    record = matches[0]
    if record.get("collection_status") != PENDING_STATUS:
        raise ValueError("collection must still be pending human review")
    if record.get("reviewability_status") != "reviewable_candidate":
        raise ValueError("collection is not a reviewable candidate")
    review = record.get("review")
    if not isinstance(review, Mapping) or review.get("approval_status") != "pending_owner_reviewer":
        raise ValueError("collection is not awaiting owner/reviewer review")
    if any(
        str(review.get(key) or "").strip()
        for key in ("review_decision", "reviewed_at", "review_note")
    ):
        raise ValueError("collection already contains a review decision")

    target = _validate_output_path(output_path, resolved_sidecar)
    source_hash = _required_text(record.get("source_hash"), "source_hash")
    if not source_hash.startswith("sha256:"):
        raise ValueError("collection source hash is invalid")
    runbook_evidence = record.get("runbook_evidence")
    if not isinstance(runbook_evidence, Mapping):
        runbook_evidence = {}
    role_hashes = runbook_evidence.get("artifact_sha256_by_role")
    if not isinstance(role_hashes, Mapping):
        role_hashes = {}
    runbook_manifest_binding = {
        "path": current_packet.get("artifact_manifest_path"),
        "sha256": runbook_evidence.get("manifest_sha256"),
        "status": runbook_evidence.get("manifest_status", "not_supplied"),
        "artifact_sha256_by_role": {
            str(role): str(digest)
            for role, digest in sorted(role_hashes.items())
            if isinstance(role, str) and isinstance(digest, str)
        },
    }
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "created_at": timestamp,
        "decision": selected_decision,
        "note": selected_note,
        "owner": {"name": selected_owner_name, "role": selected_owner_role},
        "reviewer": {"name": selected_reviewer_name, "role": selected_reviewer_role},
        "source": {
            "approval_packet_schema_version": APPROVAL_PACKET_SCHEMA_VERSION,
            "sidecar_path": str(resolved_sidecar),
            "sidecar_sha256": current_packet["sidecar_sha256"],
            "collection_id": selected_collection_id,
            "source_hash": source_hash,
            "period_start": record["period_start"],
            "period_end": record["period_end"],
            "collection_status": record["collection_status"],
            "reviewability_status": record["reviewability_status"],
            "runbook_manifest_binding": runbook_manifest_binding,
        },
        "candidate_only": True,
        "review_decision_recorded": True,
        "decision_artifact_written": True,
        "sidecar_written": False,
        "weekly_history_written": False,
        "formal_database_written": False,
        "formal_credit_authorized": False,
        "production_scheduler_allowed": False,
        "approved_projection_emitted": False,
        "downstream_eligibility": "none",
        "gate_credit_status": "pending_human_review",
        "limitations": [
            "reviewed／dismissed／follow_up 是對單筆候選的人工處置，不等於 Gate 2 通過。",
            "此 artifact 不寫 weekly history、approved projection、scheduler 或正式資料。",
        ],
    }
    serialized = json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    created = False
    try:
        with target.open("x", encoding="utf-8", newline="\n") as handle:
            created = True
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise ValueError("review decision output already exists; choose a new file") from exc
    except Exception:
        if created and target.exists():
            target.unlink()
        raise
    return target
