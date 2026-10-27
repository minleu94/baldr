"""Save a revalidated weekly candidate disposition into working-copy history."""

from __future__ import annotations

from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Any

from app_module.evidence_operations_history_repository import (
    EvidenceOperationsHistoryRepository,
)
from app_module.evidence_operations_service import EvidenceOperationsService
from app_module.research_run_dtos import canonical_json
from app_module.evidence_weekly_history_decision_bridge import (
    load_and_validate_weekly_review_decision_artifact,
)
from app_module.weekly_review_history_source import resolve_weekly_review_working_copy_path
from runtime.sqlite_file_set_fingerprint import fingerprint_sqlite_file_set


def save_candidate_weekly_review_history(
    config: Any,
    *,
    db_path: str | Path,
    start_date: str,
    end_date: str,
    decision_artifact_path: str | Path,
    sidecar_path: str | Path,
    authorized_receipt_root: str | Path | None = None,
) -> Any:
    """Rebuild a weekly report, bind the candidate decision, and save/read back.

    Only an explicitly selected non-production LEGACY_COMPAT working-copy DB
    is writable. The collection sidecar and candidate artifact remain read-only;
    this operation does not approve the resulting history or write Action Items.
    """

    start = _date_text(start_date, "start_date")
    end = _date_text(end_date, "end_date")
    if start > end:
        raise ValueError("start_date must not be after end_date")
    working_copy = resolve_weekly_review_working_copy_path(config, db_path)
    source_fingerprint = fingerprint_sqlite_file_set(working_copy)
    _require_checkpointed(source_fingerprint)

    report_service = EvidenceOperationsService(
        config,
        db_path=working_copy,
        read_only=True,
    )
    report = report_service.build_weekly_review(
        start_date=start,
        end_date=end,
    )
    if fingerprint_sqlite_file_set(working_copy) != source_fingerprint:
        raise ValueError("working-copy changed while rebuilding weekly report")
    decision = _validated_decision(
        decision_artifact_path,
        sidecar_path,
        root=authorized_receipt_root,
        start=start,
        end=end,
    )
    payload = report.to_dict()
    if report_service.source_lineage:
        payload["source_lineage"] = report_service.source_lineage
    payload["candidate_review_decision"] = decision
    payload["write_performed"] = True

    # Revalidate immediately before the only write, then prove the saved
    # identity and payload by reading the same record back from the DB.
    latest_decision = _validated_decision(
        decision_artifact_path,
        sidecar_path,
        root=authorized_receipt_root,
        start=start,
        end=end,
    )
    if latest_decision != decision:
        raise ValueError("candidate decision changed before weekly history save")
    if fingerprint_sqlite_file_set(working_copy) != source_fingerprint:
        raise ValueError("working-copy changed before weekly history save")
    repository = EvidenceOperationsHistoryRepository(
        config,
        db_path=working_copy,
        read_only=False,
    )
    saved = repository.save_weekly_review(
        report,
        generated_by="evidence_review_candidate_decision_ui",
        payload_json=payload,
    )
    readback = repository.get_weekly_review(saved.review_id)
    if readback is None:
        raise RuntimeError("weekly history record missing after save")
    expected_review_hash = "sha256:" + sha256(
        canonical_json(payload).encode("utf-8")
    ).hexdigest()
    if (
        readback.review_id != saved.review_id
        or readback.review_hash != expected_review_hash
        or saved.review_hash != expected_review_hash
        or readback.period_start != start
        or readback.period_end != end
        or readback.payload_json != payload
        or readback.payload_json.get("candidate_review_decision") != decision
    ):
        raise RuntimeError("weekly history readback does not match the saved candidate decision")
    return readback


def _validated_decision(
    artifact_path: str | Path,
    sidecar_path: str | Path,
    *,
    root: str | Path | None,
    start: str,
    end: str,
) -> dict[str, Any]:
    return load_and_validate_weekly_review_decision_artifact(
        artifact_path,
        expected_period_start=start,
        expected_period_end=end,
        expected_sidecar_path=sidecar_path,
        authorized_receipt_root=root,
    )


def _date_text(value: object, field: str) -> str:
    result = str(value or "").strip()
    try:
        parsed = date.fromisoformat(result)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date") from exc
    if parsed.isoformat() != result:
        raise ValueError(f"{field} must be a canonical ISO date")
    return result


def _require_checkpointed(fingerprint: dict[str, Any]) -> None:
    for item in fingerprint.get("files", []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("file") or "")
        if name.endswith(("-wal", "-journal")) and int(item.get("bytes_count") or 0) > 0:
            raise ValueError("working-copy must be checkpointed before weekly history save")


__all__ = ["save_candidate_weekly_review_history"]
