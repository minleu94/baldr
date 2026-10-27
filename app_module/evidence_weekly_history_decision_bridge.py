"""Revalidate candidate review decisions before attaching them to weekly history."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from app_module.evidence_weekly_approval_input import build_weekly_approval_input
from app_module.evidence_weekly_review_decision import (
    ALLOWED_DECISIONS,
    SCHEMA_VERSION as DECISION_SCHEMA_VERSION,
)
from app_module.evidence_weekly_approval_input import SCHEMA_VERSION as APPROVAL_PACKET_SCHEMA_VERSION
from runtime.sqlite_file_set_fingerprint import fingerprint_sqlite_file_set


_REQUIRED_FLAGS = {
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
}
_MAX_ARTIFACT_BYTES = 2 * 1024 * 1024


def _text(value: object, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValueError(f"{field} is required")
    return result


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _identity(value: object, field: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return {
        "name": _text(value.get("name"), f"{field}.name"),
        "role": _text(value.get("role"), f"{field}.role"),
    }


def _validate_timestamp(value: object) -> str:
    text = _text(value, "created_at")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("created_at must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("created_at must include a timezone")
    return text


def _runbook_binding(packet: Mapping[str, Any], record: Mapping[str, Any]) -> dict[str, Any]:
    evidence = record.get("runbook_evidence")
    if not isinstance(evidence, Mapping):
        evidence = {}
    hashes = evidence.get("artifact_sha256_by_role")
    if not isinstance(hashes, Mapping):
        hashes = {}
    return {
        "path": packet.get("artifact_manifest_path"),
        "sha256": evidence.get("manifest_sha256"),
        "status": evidence.get("manifest_status", "not_supplied"),
        "artifact_sha256_by_role": {
            str(role): str(digest)
            for role, digest in sorted(hashes.items())
            if isinstance(role, str) and isinstance(digest, str)
        },
    }


def load_and_validate_weekly_review_decision_artifact(
    artifact_path: str | Path,
    *,
    expected_period_start: str,
    expected_period_end: str,
    expected_sidecar_path: str | Path | None = None,
    authorized_receipt_root: str | Path | None = None,
) -> dict[str, Any]:
    """Read, hash and revalidate a candidate disposition against its live sidecar.

    The returned mapping is safe to place under a named field in the weekly
    history payload. It remains a candidate disposition and does not approve the
    history record, write a sidecar, or grant Gate/scheduler credit.
    """

    resolved_artifact = Path(artifact_path).expanduser().resolve(strict=False)
    if not resolved_artifact.is_file():
        raise ValueError("decision artifact must be a regular file")
    if resolved_artifact.stat().st_size > _MAX_ARTIFACT_BYTES:
        raise ValueError("decision artifact exceeds the 2 MiB size limit")
    artifact_bytes = resolved_artifact.read_bytes()
    artifact_sha256 = _sha256_bytes(artifact_bytes)
    if resolved_artifact.read_bytes() != artifact_bytes:
        raise ValueError("decision artifact changed while being read")
    try:
        artifact = json.loads(artifact_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("decision artifact must be valid UTF-8 JSON") from exc
    if not isinstance(artifact, Mapping):
        raise ValueError("decision artifact must be an object")
    if artifact.get("schema_version") != DECISION_SCHEMA_VERSION:
        raise ValueError("decision artifact schema is unsupported")
    for field, expected in _REQUIRED_FLAGS.items():
        if artifact.get(field) != expected:
            raise ValueError(f"decision artifact safety flag is invalid: {field}")

    decision = _text(artifact.get("decision"), "decision").casefold()
    if decision not in ALLOWED_DECISIONS:
        raise ValueError("decision must be reviewed, dismissed, or follow_up")
    note = _text(artifact.get("note"), "note")
    created_at = _validate_timestamp(artifact.get("created_at"))
    owner = _identity(artifact.get("owner"), "owner")
    reviewer = _identity(artifact.get("reviewer"), "reviewer")
    source = artifact.get("source")
    if not isinstance(source, Mapping):
        raise ValueError("source must be an object")
    if source.get("approval_packet_schema_version") != APPROVAL_PACKET_SCHEMA_VERSION:
        raise ValueError("source approval packet schema is unsupported")

    sidecar_text = _text(source.get("sidecar_path"), "source.sidecar_path")
    try:
        sidecar_path = Path(sidecar_text).expanduser().resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise ValueError("source sidecar path is unavailable") from exc
    if not sidecar_path.is_file():
        raise ValueError("source sidecar must be a regular file")
    if expected_sidecar_path is not None:
        try:
            expected_sidecar = Path(expected_sidecar_path).expanduser().resolve(strict=False)
        except (OSError, RuntimeError) as exc:
            raise ValueError("expected sidecar path is unavailable") from exc
        if not expected_sidecar.is_file() or expected_sidecar != sidecar_path:
            raise ValueError("decision artifact sidecar does not match the explicitly selected sidecar")
    expected_sidecar_sha = _text(source.get("sidecar_sha256"), "source.sidecar_sha256")
    sidecar_file_set_before = fingerprint_sqlite_file_set(sidecar_path)
    _require_checkpointed_sidecar(sidecar_file_set_before)
    sidecar_before = _sha256_file(sidecar_path)
    if sidecar_before != expected_sidecar_sha:
        raise ValueError("source sidecar SHA-256 is stale")

    manifest_binding = source.get("runbook_manifest_binding")
    if not isinstance(manifest_binding, Mapping):
        raise ValueError("source runbook manifest binding must be an object")
    manifest_path_value = manifest_binding.get("path")
    if manifest_path_value is None:
        if manifest_binding != {
            "path": None,
            "sha256": None,
            "status": "not_supplied",
            "artifact_sha256_by_role": {},
        }:
            raise ValueError("unsupplied runbook manifest binding is inconsistent")
        manifest_path = None
        root = None
    else:
        try:
            manifest_path = Path(_text(manifest_path_value, "manifest.path")).expanduser().resolve(strict=False)
        except (OSError, RuntimeError) as exc:
            raise ValueError("bound runbook manifest is unavailable") from exc
        if not manifest_path.is_file():
            raise ValueError("bound runbook manifest must be a regular file")
        if authorized_receipt_root is None:
            raise ValueError("authorized_receipt_root is required for a bound runbook manifest")
        root = Path(authorized_receipt_root).expanduser().resolve(strict=False)
        if not root.is_dir():
            raise ValueError("authorized_receipt_root must be an existing directory")

    sidecar_file_set_before_packet = fingerprint_sqlite_file_set(sidecar_path)
    if sidecar_file_set_before_packet != sidecar_file_set_before:
        raise ValueError("source sidecar file set changed before approval packet validation")
    sidecar_before_packet = _sha256_file(sidecar_path)
    current_packet = build_weekly_approval_input(
        sidecar_path,
        owner_role=owner["role"],
        reviewer_role=reviewer["role"],
        include_failed=False,
        artifact_manifest_path=manifest_path,
        authorized_receipt_root=root,
    )
    sidecar_after_packet = _sha256_file(sidecar_path)
    sidecar_file_set_after_packet = fingerprint_sqlite_file_set(sidecar_path)
    if not (
        sidecar_before == sidecar_before_packet == sidecar_after_packet
        and sidecar_file_set_before
        == sidecar_file_set_before_packet
        == sidecar_file_set_after_packet
    ):
        raise ValueError("source sidecar changed while rebuilding the approval packet")
    if current_packet.get("sidecar_sha256") != expected_sidecar_sha:
        raise ValueError("rebuilt approval packet sidecar SHA-256 does not match artifact")

    collection_id = _text(source.get("collection_id"), "source.collection_id")
    matches = [
        row for row in current_packet.get("records", [])
        if isinstance(row, Mapping) and row.get("collection_id") == collection_id
    ]
    if len(matches) != 1:
        raise ValueError("collection_id does not identify exactly one current approval record")
    record = matches[0]
    if source.get("collection_status") != record.get("collection_status"):
        raise ValueError("collection status no longer matches the decision artifact")
    if source.get("reviewability_status") != record.get("reviewability_status"):
        raise ValueError("collection reviewability no longer matches the decision artifact")
    if record.get("collection_status") != "pending_human_review":
        raise ValueError("collection is no longer pending human review")
    if record.get("reviewability_status") != "reviewable_candidate":
        raise ValueError("collection is no longer a reviewable candidate")
    review = record.get("review")
    if not isinstance(review, Mapping) or review.get("approval_status") != "pending_owner_reviewer":
        raise ValueError("collection is no longer awaiting owner/reviewer review")
    for field in ("source_hash", "period_start", "period_end"):
        if source.get(field) != record.get(field):
            raise ValueError(f"collection {field} no longer matches the decision artifact")
    if (source.get("period_start"), source.get("period_end")) != (
        expected_period_start,
        expected_period_end,
    ):
        raise ValueError("decision artifact period must exactly match weekly report period")
    if _runbook_binding(current_packet, record) != dict(manifest_binding):
        raise ValueError("runbook manifest binding no longer matches the decision artifact")
    if (
        _sha256_file(sidecar_path) != sidecar_after_packet
        or fingerprint_sqlite_file_set(sidecar_path) != sidecar_file_set_after_packet
    ):
        raise ValueError("source sidecar changed after approval packet validation")
    if resolved_artifact.read_bytes() != artifact_bytes:
        raise ValueError("decision artifact changed during validation")

    return {
        **dict(artifact),
        "artifact_path": str(resolved_artifact),
        "artifact_sha256": artifact_sha256,
    }


def _require_checkpointed_sidecar(fingerprint: Mapping[str, Any]) -> None:
    for item in fingerprint.get("files", []):
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("file") or "")
        if name.endswith(("-wal", "-journal")) and int(item.get("bytes_count") or 0) > 0:
            raise ValueError("source sidecar must be checkpointed before candidate review")


__all__ = ["load_and_validate_weekly_review_decision_artifact"]
