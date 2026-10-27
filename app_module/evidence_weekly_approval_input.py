"""Build a read-only owner/reviewer input from the weekly collection sidecar.

The sidecar is an automatic collection store.  This module deliberately emits a
separate candidate packet rather than mutating the sidecar or producing an
``approved-weekly-history-projection.v1``.  A human must still fill the review
fields and publish any approved projection through the existing governed path.
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import stat
from typing import Any, Mapping


SCHEMA_VERSION = "evidence-weekly-approval-input.v1"
PENDING_STATUS = "pending_human_review"
FAILED_STATUS = "collection_failed"
APPROVAL_STATUS = "pending_owner_reviewer"
SOURCE_COVERAGE_STATUSES = {"degraded", "observed_no_basic_integrity_gaps"}
RUNBOOK_MANIFEST_SCHEMA_VERSION = "baldr-weekly-runbook-manifest.v1"
RUNBOOK_ARTIFACT_SCHEMA_VERSION = "baldr-weekly-runbook-artifact.v1"
RUNBOOK_MANIFEST_MAX_BYTES = 256 * 1024
RUNBOOK_ARTIFACT_MAX_BYTES = 4 * 1024 * 1024
RUNBOOK_MANIFEST_ROLES = {
    "working_copy_smoke",
    "weekly_review_report",
    "evidence_review_dashboard",
    "scheduled_pipeline_dry_run",
    "manual_pipeline_dry_run",
}
RUNBOOK_EVIDENCE_SPECS = (
    ("working_copy_smoke", "Working-copy smoke：重複執行與冪等收據"),
    ("freshness_snapshot", "本週 freshness 快照"),
    ("source_coverage_snapshot", "來源 coverage 快照"),
    ("scheduled_pipeline_dry_run", "Scheduled pipeline dry-run 收據"),
    ("manual_pipeline_dry_run", "Manual pipeline dry-run 收據"),
    ("evidence_review_dashboard", "Evidence Review dashboard 證據"),
    ("weekly_review_report", "Weekly review report dry-run 收據"),
    ("write_safety_assertions", "write／scheduler／apply_action 安全斷言"),
    ("warnings_blocking_gaps", "Warnings、blocking gaps 與 degraded reasons"),
    ("review_identity_and_history", "具名 review、review ID／hash／status 與 action plan"),
    ("backup_rollback_recovery", "Backup／rollback／recovery 狀態與證據"),
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def read_verified_official_receipt(
    authorized_root: str | Path,
    receipt_path: str | Path,
    expected_sha256: str,
    *,
    max_bytes: int = 256 * 1024,
) -> dict[str, Any]:
    """Read one receipt only after root containment and content hash checks.

    The returned text is the exact byte sequence that was hashed. This helper
    never follows a path outside the configured root and never opens a file
    whose recorded hash is absent or malformed.
    """

    if not isinstance(expected_sha256, str) or not expected_sha256.startswith("sha256:"):
        raise ValueError("official receipt SHA-256 is missing or malformed")
    expected_digest = expected_sha256.removeprefix("sha256:")
    if len(expected_digest) != 64 or any(char not in "0123456789abcdef" for char in expected_digest.lower()):
        raise ValueError("official receipt SHA-256 is missing or malformed")
    if max_bytes <= 0:
        raise ValueError("maximum receipt size must be positive")

    # strict=False still canonicalizes existing symlinks/reparse points. On
    # Windows sandbox roots, strict=True can fail querying directory metadata
    # even when the same file can be opened; existence is checked below.
    root = Path(authorized_root).expanduser().resolve(strict=False)
    if not root.is_dir():
        raise ValueError("authorized receipt root is not a directory")
    candidate = Path(receipt_path).expanduser().resolve(strict=False)
    if not candidate.is_relative_to(root) or candidate == root:
        raise ValueError("official receipt path is outside the authorized root")
    if not candidate.is_file():
        raise ValueError("official receipt is not a regular file")
    if candidate.stat().st_size > max_bytes:
        raise ValueError("official receipt exceeds the preview size limit")

    with candidate.open("rb") as handle:
        raw = handle.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError("official receipt exceeds the preview size limit")
    actual = "sha256:" + sha256(raw).hexdigest()
    if actual.casefold() != expected_sha256.casefold():
        raise ValueError("official receipt SHA-256 does not match the recorded hash")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("official receipt is not valid UTF-8 text") from exc
    return {
        "path": str(candidate),
        "sha256": actual,
        "byte_count": len(raw),
        "text": text,
    }


def _read_only_connection(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise FileNotFoundError(str(path))
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None


def _non_empty(value: object, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"weekly collection row missing {field}")
    return text


def _payload(value: object, collection_id: str) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"weekly collection payload invalid: {collection_id}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"weekly collection payload must be an object: {collection_id}")
    return parsed


def _record_from_row(
    row: sqlite3.Row,
    *,
    owner_role: str,
    reviewer_role: str,
) -> dict[str, Any]:
    collection_id = _non_empty(row["collection_id"], "collection_id")
    period_start = _non_empty(row["period_start"], "period_start")
    period_end = _non_empty(row["period_end"], "period_end")
    source_path = _non_empty(row["source_path"], "source_path")
    source_hash = _non_empty(row["source_hash"], "source_hash")
    if not source_hash.startswith("sha256:"):
        raise ValueError(f"weekly collection source hash is not immutable: {collection_id}")
    status = _non_empty(row["status"], "status")
    if status not in {PENDING_STATUS, FAILED_STATUS}:
        raise ValueError(f"unsupported weekly collection status: {status}")
    payload = _payload(row["payload_json"], collection_id)
    runbook_evidence = _build_runbook_evidence(
        payload,
        collection_id=collection_id,
        period_start=period_start,
        period_end=period_end,
    )
    error_type = str(row["error_type"] or "")
    error_message = str(row["error_message"] or "")
    if status == PENDING_STATUS and (error_type or error_message):
        raise ValueError(f"pending weekly collection contains an error: {collection_id}")

    payload_last_trading_date = str(payload.get("last_trading_date") or "").strip()
    source_coverage = payload.get("source_coverage")
    reviewability_reasons: list[str] = []
    if status == FAILED_STATUS:
        reviewability_status = FAILED_STATUS
        reviewability_reasons.append("collection_failed")
    elif not isinstance(source_coverage, Mapping):
        reviewability_status = "recollection_required"
        reviewability_reasons.append("source_coverage_not_captured")
    elif not str(source_coverage.get("status") or "").strip():
        reviewability_status = "recollection_required"
        reviewability_reasons.append("source_coverage_status_missing")
    elif str(source_coverage.get("status") or "").strip().casefold() not in SOURCE_COVERAGE_STATUSES:
        reviewability_status = "recollection_required"
        reviewability_reasons.append(
            "source_coverage_status_unrecognized:"
            + str(source_coverage.get("status") or "").strip()[:80]
        )
    else:
        reviewability_status = "reviewable_candidate"

    return {
        "collection_id": collection_id,
        "period_start": period_start,
        "period_end": period_end,
        "source_path": source_path,
        "source_hash": source_hash,
        "collection_status": status,
        "created_at": str(row["created_at"] or "").strip(),
        "last_trading_date": payload_last_trading_date,
        "collection_payload": payload,
        "runbook_evidence": runbook_evidence,
        "reviewability_status": reviewability_status,
        "reviewability_reasons": reviewability_reasons,
        "error": {
            "type": error_type,
            "message": error_message,
        },
        "review": {
            "approval_status": (
                FAILED_STATUS
                if status == FAILED_STATUS
                else (
                    "recollection_required"
                    if reviewability_status == "recollection_required"
                    else APPROVAL_STATUS
                )
            ),
            "owner_role": owner_role,
            "reviewer_role": reviewer_role,
            "review_decision": "",
            "reviewed_at": "",
            "review_note": "",
        },
        "formal_credit_authorized": False,
        "production_scheduler_allowed": False,
        "downstream_eligibility": "none",
    }


def _canonical_period(value: object, field: str) -> str:
    text = str(value or "").strip()
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"runbook {field} must be canonical YYYY-MM-DD") from exc
    if parsed.isoformat() != text:
        raise ValueError(f"runbook {field} must be canonical YYYY-MM-DD")
    return text


def _reject_link_components(path: Path, *, boundary: Path | None = None) -> None:
    """Reject links below a canonical root while allowing a configured mount root."""

    candidate = path.absolute()
    stop = boundary.absolute() if boundary is not None else None
    if stop is not None and not candidate.is_relative_to(stop):
        raise ValueError("runbook path escapes its authorized root")
    components = (candidate, *candidate.parents)
    for component in components:
        if stop is not None and component == stop:
            break
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x0400:
            raise ValueError("runbook manifest path contains a link or reparse point")


def _bounded_json(path: Path, *, max_bytes: int) -> tuple[dict[str, Any], bytes]:
    _reject_link_components(path)
    if not path.is_file():
        raise ValueError("runbook artifact is not a regular file")
    if path.stat().st_size > max_bytes:
        raise ValueError("runbook artifact exceeds the size limit")
    raw = path.read_bytes()
    if len(raw) > max_bytes:
        raise ValueError("runbook artifact exceeds the size limit")
    try:
        decoded = raw.decode("utf-8-sig")
        parsed = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("runbook artifact is not valid UTF-8 JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("runbook artifact root must be an object")
    return parsed, raw


def _load_runbook_manifest(
    manifest_path: str | Path,
    *,
    authorized_root: str | Path | None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    manifest_input = Path(manifest_path).expanduser().absolute()
    root_input = Path(authorized_root).expanduser().absolute() if authorized_root else manifest_input.parent
    root = root_input.resolve(strict=False)
    _reject_link_components(manifest_input, boundary=root_input)
    manifest = manifest_input.resolve(strict=False)
    if not root.is_dir() or not manifest.is_relative_to(root) or manifest == root:
        raise ValueError("runbook manifest is outside the authorized receipt root")
    _reject_link_components(root)
    manifest_data, manifest_raw = _bounded_json(manifest, max_bytes=RUNBOOK_MANIFEST_MAX_BYTES)
    if manifest_data.get("schema_version") != RUNBOOK_MANIFEST_SCHEMA_VERSION:
        raise ValueError("runbook manifest schema is unsupported")
    collection_id = _non_empty(manifest_data.get("collection_id"), "manifest collection_id")
    period_start = _canonical_period(manifest_data.get("period_start"), "period_start")
    period_end = _canonical_period(manifest_data.get("period_end"), "period_end")
    if period_start > period_end:
        raise ValueError("runbook manifest period_start is after period_end")
    references = manifest_data.get("artifacts")
    if not isinstance(references, list):
        raise ValueError("runbook manifest artifacts must be an array")
    artifacts: dict[str, dict[str, Any]] = {}
    base = manifest.parent
    for reference in references:
        if not isinstance(reference, Mapping):
            raise ValueError("runbook manifest artifact entry must be an object")
        role = _non_empty(reference.get("artifact_role"), "artifact_role")
        if role not in RUNBOOK_MANIFEST_ROLES:
            raise ValueError(f"runbook manifest artifact role is unsupported: {role}")
        if role in artifacts:
            raise ValueError(f"runbook manifest contains duplicate artifact role: {role}")
        relative = _non_empty(reference.get("path"), "artifact path")
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError("runbook artifact path must stay below the manifest directory")
        artifact_input = (base / relative_path).absolute()
        _reject_link_components(artifact_input, boundary=base)
        artifact_path = artifact_input.resolve(strict=False)
        if not artifact_path.is_relative_to(base) or artifact_path == base:
            raise ValueError("runbook artifact path escapes the manifest directory")
        _reject_link_components(artifact_path)
        expected_hash = _non_empty(reference.get("sha256"), "artifact sha256")
        if not expected_hash.startswith("sha256:") or len(expected_hash) != 71:
            raise ValueError("runbook artifact SHA-256 is missing or malformed")
        artifact, raw = _bounded_json(artifact_path, max_bytes=RUNBOOK_ARTIFACT_MAX_BYTES)
        actual_hash = "sha256:" + sha256(raw).hexdigest()
        if actual_hash.casefold() != expected_hash.casefold():
            raise ValueError(f"runbook artifact hash mismatch: {role}")
        artifacts[role] = {
            "path": str(artifact_path),
            "sha256": actual_hash,
            "payload": artifact,
        }
    if manifest.read_bytes() != manifest_raw:
        raise ValueError("runbook manifest changed while artifacts were being verified")
    return {
        "path": str(manifest),
        "collection_id": collection_id,
        "period_start": period_start,
        "period_end": period_end,
        "sha256": "sha256:" + sha256(manifest_raw).hexdigest(),
    }, artifacts


def _set_evidence_status(items: list[dict[str, Any]], evidence_id: str, status: str, detail: str = "") -> None:
    for item in items:
        if item["evidence_id"] == evidence_id:
            item["status"] = status
            if detail:
                item["details"] = detail[:240]
            return


def _as_mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _apply_runbook_manifest(
    items: list[dict[str, Any]],
    *,
    artifacts: Mapping[str, Mapping[str, Any]],
    collection_id: str,
    period_start: str,
    period_end: str,
) -> list[str]:
    """Promote only artifact roles whose bytes, period and identity reconcile."""

    diagnostics: list[str] = []
    expected_period = (period_start, period_end)
    smoke = artifacts.get("working_copy_smoke")
    report = artifacts.get("weekly_review_report")
    dashboard = artifacts.get("evidence_review_dashboard")
    checked: dict[str, dict[str, Any]] = {}
    for role, entry in artifacts.items():
        artifact = entry["payload"]
        expected_artifact_role = role
        if role in {"scheduled_pipeline_dry_run", "manual_pipeline_dry_run"}:
            if artifact.get("schema_version") == "baldr-evidence-pipeline-terminal-receipt.v1":
                checked[role] = artifact
                _set_evidence_status(
                    items, role, "partial",
                    "每日終態收據未綁週期間與 SQLite file-set identity，僅作佐證。",
                )
                continue
        if (
            artifact.get("schema_version") != RUNBOOK_ARTIFACT_SCHEMA_VERSION
            or artifact.get("artifact_role") != expected_artifact_role
        ):
            diagnostics.append(f"artifact_contract_mismatch:{role}")
            continue
        if (artifact.get("period_start"), artifact.get("period_end")) != expected_period:
            diagnostics.append(f"artifact_period_mismatch:{role}")
            continue
        checked[role] = artifact

    smoke_ok = False
    if smoke is not None and "working_copy_smoke" in checked:
        p = checked["working_copy_smoke"]
        period_is_valid = False
        try:
            decision_date = _canonical_period(p.get("decision_date"), "decision_date")
            period_is_valid = period_start <= decision_date <= period_end
        except ValueError:
            period_is_valid = False
        smoke_ok = bool(
            _as_mapping(p.get("idempotency_check")).get("passed") is True
            and p.get("source_identity_stable") is True
            and p.get("source_write_performed") is False
            and p.get("working_copy_write_performed") is True
            and period_is_valid
            and p.get("working_copy_db_path")
            and p.get("working_copy_fingerprint_after")
            and p.get("fingerprint_method") == "sha256_sqlite_file_set.v1"
        )
        if smoke_ok:
            _set_evidence_status(items, "working_copy_smoke", "verified", "冪等、期間、來源穩定及隔離工作副本欄位齊全。")
        else:
            diagnostics.append("working_copy_smoke_identity_or_safety_incomplete")

    report_ok = False
    if report is not None and "weekly_review_report" in checked:
        p = checked["weekly_review_report"]
        db = p.get("database_identity")
        safety = p.get("safety_flags_verified")
        report_payload = p.get("report_payload")
        report_ok = bool(
            isinstance(db, Mapping)
            and db.get("role") == "working_copy"
            and bool(db.get("path"))
            and db.get("stable") is True
            and db.get("fingerprint_before")
            and db.get("fingerprint_before") == db.get("fingerprint_after")
            and db.get("fingerprint_method") == "sha256_sqlite_file_set.v1"
            and isinstance(safety, Mapping)
            and bool(safety)
            and all(value is True for value in safety.values())
            and isinstance(report_payload, Mapping)
            and "warnings" in report_payload
            and isinstance(report_payload.get("warnings"), list)
            and isinstance(_as_mapping(report_payload.get("manual_approval")).get("blocking_gaps"), list)
        )
        if report_ok:
            _set_evidence_status(items, "weekly_review_report", "verified", "週報 dry-run、工作副本身分、前後 fingerprint 與安全旗標齊全。")
        else:
            diagnostics.append("weekly_review_report_identity_or_safety_incomplete")

    if smoke_ok and report_ok and smoke is not None and report is not None:
        smoke_payload = checked["working_copy_smoke"]
        report_db = _as_mapping(
            checked["weekly_review_report"].get("database_identity")
        )
        if (
            str(smoke_payload.get("working_copy_db_path")) != str(report_db.get("path"))
            or smoke_payload.get("working_copy_fingerprint_after") != report_db.get("fingerprint_before")
            or report_db.get("fingerprint_before") != report_db.get("fingerprint_after")
        ):
            smoke_ok = report_ok = False
            diagnostics.append("smoke_weekly_review_database_identity_mismatch")
            _set_evidence_status(items, "working_copy_smoke", "partial", "Smoke 與 weekly report 的工作副本 fingerprint 不一致。")
            _set_evidence_status(items, "weekly_review_report", "partial", "Smoke 與 weekly report 的工作副本 fingerprint 不一致。")

    if dashboard is not None and "evidence_review_dashboard" in checked:
        p = checked["evidence_review_dashboard"]
        db = p.get("database_identity")
        payload = p.get("payload")
        dashboard_ok = bool(
            isinstance(db, Mapping)
            and db.get("role") == "review_store"
            and db.get("stable_during_read") is True
            and bool(db.get("fingerprint_before"))
            and db.get("fingerprint_before") == db.get("fingerprint_after")
            and db.get("fingerprint_method") == "sha256_sqlite_file_set.v1"
            and isinstance(payload, Mapping)
            and payload.get("dashboard_verified") is True
            and isinstance(payload.get("cards"), Mapping)
            and isinstance(payload.get("rows"), list)
            and payload.get("pagination_complete") is True
        )
        if dashboard_ok:
            _set_evidence_status(items, "evidence_review_dashboard", "verified", "Dashboard rows/cards、期間、分頁與 review-store fingerprint 齊全。")
            dashboard_payload = _as_mapping(payload)
            dashboard_rows = dashboard_payload.get("rows")
            rows_for_matching = (
                dashboard_rows if isinstance(dashboard_rows, list) else []
            )
            matching_rows = [
                row for row in rows_for_matching
                if isinstance(row, Mapping)
                and row.get("period_start") == period_start
                and row.get("period_end") == period_end
                and row.get("review_id")
                and row.get("review_hash")
            ]
            if matching_rows:
                _set_evidence_status(items, "review_identity_and_history", "partial", "找到同週期 review ID／hash；仍未代替當週具名人工決定。")
            else:
                diagnostics.append("matching_weekly_review_history_not_found")
        else:
            diagnostics.append("evidence_review_dashboard_identity_or_pagination_incomplete")

    # These roles are structural observations from the attached artifacts only.
    # They do not imply that a source is accepted or a Gate has passed.
    warning_covered = True
    warning_seen = False
    if smoke is not None and "working_copy_smoke" in checked:
        warning_seen = True
        warning_covered &= isinstance(checked["working_copy_smoke"].get("blocking_gaps"), list)
    if report is not None and "weekly_review_report" in checked:
        warning_seen = True
        data = checked["weekly_review_report"].get("report_payload")
        manual_approval = _as_mapping(data).get("manual_approval")
        warning_covered &= (
            isinstance(data, Mapping)
            and isinstance(data.get("warnings"), list)
            and isinstance(_as_mapping(manual_approval).get("blocking_gaps"), list)
        )
    if dashboard is not None and "evidence_review_dashboard" in checked:
        warning_seen = True
        data = checked["evidence_review_dashboard"].get("payload")
        warning_covered &= isinstance(data, Mapping) and isinstance(data.get("diagnostics"), list) and isinstance(data.get("limitations"), list)
    if warning_seen and warning_covered:
        _set_evidence_status(items, "warnings_blocking_gaps", "verified", "已檢查附件的 warnings/errors/blocking-gaps 欄位（空清單亦明確記錄）。")
    elif warning_seen:
        _set_evidence_status(items, "warnings_blocking_gaps", "partial", "附件只提供部分 warnings／errors／blocking-gaps 欄位。")
    if smoke_ok and report_ok:
        _set_evidence_status(items, "write_safety_assertions", "partial", "Smoke 與週報安全旗標可核；scheduled/manual 尚未用週期封套綁定。")
        _set_evidence_status(items, "source_coverage_snapshot", "partial", "Sidecar coverage 有摘要，但不是全市場母體／來源接受驗證。")
        _set_evidence_status(items, "freshness_snapshot", "partial", "附件含決策日期／資料 freshness 摘要，尚缺週期化獨立 freshness 收據。")
    if dashboard is not None and "evidence_review_dashboard" in checked:
        _set_evidence_status(items, "backup_rollback_recovery", "missing", "Dashboard 不含 backup／rollback／recovery 演練證據。")
    if diagnostics:
        diagnostics = list(dict.fromkeys(diagnostics))
    return diagnostics


def _build_runbook_evidence(
    payload: Mapping[str, Any],
    *,
    collection_id: str,
    period_start: str,
    period_end: str,
    manifest: tuple[dict[str, Any], dict[str, dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Report Runbook evidence gaps without inferring identity or Gate readiness."""

    coverage = payload.get("source_coverage")
    coverage_present = isinstance(coverage, Mapping) and bool(
        str(coverage.get("status") or "").strip()
    )
    quality_details_present = False
    if isinstance(coverage, Mapping):
        quality_details_present = coverage_present and bool(
            coverage.get("quality_findings") or coverage.get("integrity_examples")
        )
    statuses = {
        "source_coverage_snapshot": "unverified" if coverage_present else "missing",
        "warnings_blocking_gaps": "partial" if quality_details_present else "missing",
    }
    items = [
        {
            "evidence_id": evidence_id,
            "label": label,
            "required": True,
            "status": statuses.get(evidence_id, "missing"),
        }
        for evidence_id, label in RUNBOOK_EVIDENCE_SPECS
    ]
    limitations = [
        "Sidecar 內嵌的 coverage／quality findings 不是已核驗的 Runbook 附件。",
        "附件 manifest 缺件或身份不符時維持 missing／partial，不推測同週期或同 DB。",
        "verified 只表示附件 bytes／契約／身分可核對，不代表 Gate 2 核准、來源接受或排程啟用。",
        "此清單不改變 packet_status、人工決定或 Gate credit。",
    ]
    manifest_status = "not_supplied"
    manifest_sha256 = None
    manifest_diagnostics: list[str] = []
    if manifest is not None:
        manifest_identity, artifacts = manifest
        manifest_sha256 = manifest_identity["sha256"]
        if (
            manifest_identity["collection_id"] == collection_id
            and manifest_identity["period_start"] == period_start
            and manifest_identity["period_end"] == period_end
        ):
            manifest_status = "matched"
            manifest_diagnostics = _apply_runbook_manifest(
                items,
                artifacts=artifacts,
                collection_id=collection_id,
                period_start=period_start,
                period_end=period_end,
            )
        else:
            manifest_status = "identity_mismatch_not_applied"
            manifest_diagnostics.append("manifest_collection_or_period_mismatch")
    verified_count = sum(item["status"] == "verified" for item in items)
    partial_count = sum(item["status"] in {"partial", "unverified"} for item in items)
    missing_count = sum(item["status"] == "missing" for item in items)
    all_artifacts_verified = verified_count == len(items) and partial_count == 0 and missing_count == 0
    return {
        "status": (
            "all_required_artifacts_verified_gate_review_still_required"
            if all_artifacts_verified
            else "incomplete_required_evidence"
        ),
        "required_count": len(items),
        "verified_count": verified_count,
        "partial_count": partial_count,
        "missing_count": missing_count,
        "items": items,
        "manifest_status": manifest_status,
        "manifest_sha256": manifest_sha256,
        "artifact_sha256_by_role": (
            {
                role: str(artifact.get("sha256") or "")
                for role, artifact in sorted(manifest[1].items())
                if isinstance(artifact, Mapping)
            }
            if manifest is not None
            else {}
        ),
        "manifest_diagnostics": manifest_diagnostics,
        "limitations": limitations,
    }


def build_weekly_approval_input(
    sidecar_path: str | Path,
    *,
    owner_role: str = "",
    reviewer_role: str = "",
    include_failed: bool = False,
    artifact_manifest_path: str | Path | None = None,
    authorized_receipt_root: str | Path | None = None,
) -> dict[str, Any]:
    """Read pending sidecar rows and return a non-approving review packet."""

    resolved_sidecar = Path(sidecar_path).expanduser().resolve()
    normalized_owner = owner_role.strip()
    normalized_reviewer = reviewer_role.strip()
    manifest = (
        _load_runbook_manifest(
            artifact_manifest_path,
            authorized_root=authorized_receipt_root,
        )
        if artifact_manifest_path is not None
        else None
    )
    statuses = (PENDING_STATUS, FAILED_STATUS) if include_failed else (PENDING_STATUS,)
    placeholders = ", ".join("?" for _ in statuses)
    try:
        with _read_only_connection(resolved_sidecar) as connection:
            if not _table_exists(connection, "evidence_weekly_collections"):
                raise ValueError("weekly collection sidecar table missing")
            rows = connection.execute(
                f"""
                SELECT collection_id, period_start, period_end, source_path,
                       source_hash, status, payload_json, error_type,
                       error_message, created_at
                FROM evidence_weekly_collections
                WHERE status IN ({placeholders})
                ORDER BY period_start, period_end, collection_id
                """,
                statuses,
            ).fetchall()
    except sqlite3.Error as exc:
        raise ValueError(f"weekly collection sidecar unavailable: {exc}") from exc

    records: list[dict[str, Any]] = []
    for row in rows:
        record = _record_from_row(
            row,
            owner_role=normalized_owner,
            reviewer_role=normalized_reviewer,
        )
        record["runbook_evidence"] = _build_runbook_evidence(
            record["collection_payload"],
            collection_id=record["collection_id"],
            period_start=record["period_start"],
            period_end=record["period_end"],
            manifest=manifest,
        )
        records.append(record)
    pending_count = sum(
        1 for record in records if record["collection_status"] == PENDING_STATUS
    )
    failed_count = sum(
        1 for record in records if record["collection_status"] == FAILED_STATUS
    )
    recollection_required_count = sum(
        1 for record in records if record["reviewability_status"] == "recollection_required"
    )
    evidence_items = [
        item
        for record in records
        for item in record["runbook_evidence"]["items"]
    ]
    runbook_evidence_summary = {
        "status": "incomplete_required_evidence" if records else "not_assessed_no_records",
        "required_count": len(evidence_items),
        "verified_count": sum(item["status"] == "verified" for item in evidence_items),
        "partial_count": sum(item["status"] in {"partial", "unverified"} for item in evidence_items),
        "missing_count": sum(item["status"] == "missing" for item in evidence_items),
    }
    source_paths = sorted({record["source_path"] for record in records})
    source_hashes = sorted({record["source_hash"] for record in records})
    if recollection_required_count:
        packet_status = "recollection_required"
    elif pending_count == 0 and failed_count:
        packet_status = "collection_failed"
    elif pending_count == 0:
        packet_status = "no_pending_reviews"
    elif normalized_owner and normalized_reviewer:
        packet_status = "ready_for_human_review"
    else:
        packet_status = "needs_named_owner_reviewer"
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "packet_status": packet_status,
        "sidecar_path": str(resolved_sidecar),
        "sidecar_sha256": _sha256_file(resolved_sidecar),
        "artifact_manifest_path": manifest[0]["path"] if manifest is not None else None,
        "artifact_manifest_sha256": manifest[0]["sha256"] if manifest is not None else None,
        "source_paths": source_paths,
        "source_hashes": source_hashes,
        "record_count": len(records),
        "pending_human_review_count": pending_count,
        "collection_failed_count": failed_count,
        "recollection_required_count": recollection_required_count,
        "reviewable_pending_count": pending_count - recollection_required_count,
        "runbook_evidence": runbook_evidence_summary,
        "owner_reviewer_required": True,
        "owner_role": normalized_owner,
        "reviewer_role": normalized_reviewer,
        "formal_credit_authorized": False,
        "production_scheduler_allowed": False,
        "downstream_eligibility": "none",
        "candidate_only": True,
        "write_performed": False,
        "approved_projection_emitted": False,
        "records": records,
        "limitations": [
            "自動 sidecar collection 只代表 pending_human_review，不是人工核准。",
            "本 packet 不會寫 sidecar、正式 Evidence DB、Registry 或 approved weekly projection。",
            "必須由具名 owner／reviewer 填寫 review_decision、reviewed_at 與 review_note；此 packet 本身不授予 Formal credit。",
            "collection payload 的 source hash 只綁定收集時讀到的來源快照，不替代 quality、coverage、PIT 或 license acceptance。",
            "packet_status=ready_for_human_review 只表示候選可開始人工檢視，不表示 Runbook 附件齊備或 Gate 2 就緒。",
        ],
    }


def render_markdown(packet: Mapping[str, Any]) -> str:
    records = packet.get("records", [])
    lines = [
        "# Evidence Weekly Approval Input (Candidate)",
        "",
        f"- Packet status: `{packet.get('packet_status', '')}`",
        f"- Generated at: `{packet.get('generated_at', '')}`",
        f"- Sidecar: `{packet.get('sidecar_path', '')}`",
        f"- Sidecar SHA-256: `{packet.get('sidecar_sha256', '')}`",
        f"- Pending human review: `{packet.get('pending_human_review_count', 0)}`",
        f"- Collection failed: `{packet.get('collection_failed_count', 0)}`",
        f"- Recollection required: `{packet.get('recollection_required_count', 0)}`",
        f"- Runbook evidence: `{packet.get('runbook_evidence', {}).get('status', 'not_assessed')}` "
        f"({packet.get('runbook_evidence', {}).get('verified_count', 0)}/"
        f"{packet.get('runbook_evidence', {}).get('required_count', 0)} verified; "
        f"{packet.get('runbook_evidence', {}).get('missing_count', 0)} missing; "
        f"{packet.get('runbook_evidence', {}).get('partial_count', 0)} partial)",
        f"- Owner role: `{packet.get('owner_role', '') or 'REQUIRES_NAMED_OWNER'}`",
        f"- Reviewer role: `{packet.get('reviewer_role', '') or 'REQUIRES_NAMED_REVIEWER'}`",
        "- Formal credit authorized: `false`",
        "- Production scheduler allowed: `false`",
        "- Downstream eligibility: `none`",
        "- Write performed: `false`",
        "- `ready_for_human_review` 僅指可開始人工檢視；Runbook 證據完整度另列，不代表 Gate 就緒。",
        "",
        "## Review records",
        "",
        "| Period | Collection ID | Source hash | Last trading date | Reviewability | Observed coverage | Findings | Runbook evidence | Approval status | Decision |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for record in records:
        review = record.get("review", {})
        collection_payload = record.get("collection_payload", {})
        coverage = collection_payload.get("source_coverage", {})
        findings = coverage.get("quality_findings", [])
        evidence = record.get("runbook_evidence", {})
        lines.append(
            "| {start}..{end} | `{collection}` | `{source_hash}` | `{last_trading}` | `{reviewability}` | "
            "{coverage_status} / {trading_days} dates / {rows} rows / {duplicates} duplicates | "
            "{findings} | `{evidence_status}` ({verified}/{required} verified; {missing} missing; {partial} partial) | "
            "`{approval}` | `{decision}` |".format(
                start=record.get("period_start", ""),
                end=record.get("period_end", ""),
                collection=record.get("collection_id", ""),
                source_hash=record.get("source_hash", ""),
                last_trading=record.get("last_trading_date", "") or "unknown",
                reviewability=record.get("reviewability_status", "unknown"),
                coverage_status=coverage.get("status", "not_collected"),
                trading_days=coverage.get("trading_day_count", "unknown"),
                rows=coverage.get("observed_row_count", "unknown"),
                duplicates=coverage.get("duplicate_symbol_rows", "unknown"),
                findings=(", ".join(str(item) for item in findings) or "none_observed"),
                evidence_status=evidence.get("status", "not_assessed"),
                verified=evidence.get("verified_count", 0),
                required=evidence.get("required_count", 0),
                missing=evidence.get("missing_count", 0),
                partial=evidence.get("partial_count", 0),
                approval=review.get("approval_status", APPROVAL_STATUS),
                decision=review.get("review_decision", "") or "pending",
            )
        )
    if records:
        lines.extend(["", "## Runbook evidence checklist", ""])
        for record in records:
            evidence = record.get("runbook_evidence", {})
            lines.append(
                f"### {record.get('period_start', '')}..{record.get('period_end', '')} "
                f"`{record.get('collection_id', '')}` — "
                f"`{evidence.get('status', 'not_assessed')}`"
            )
            for item in evidence.get("items", []):
                if isinstance(item, Mapping):
                    lines.append(
                        f"- `{item.get('status', 'not_assessed')}`: "
                        f"{item.get('label', item.get('evidence_id', 'unknown'))}"
                    )
    recollection_records = [
        record for record in records if record.get("reviewability_status") == "recollection_required"
    ]
    if recollection_records:
        lines.extend(["", "## Recollection required before review", ""])
        for record in recollection_records:
            reasons = record.get("reviewability_reasons", [])
            lines.append(
                f"- {record.get('period_start', '')}..{record.get('period_end', '')} "
                f"`{record.get('collection_id', '')}`: "
                + (", ".join(str(item) for item in reasons) or "review evidence incomplete")
            )
    integrity_records = [
        record
        for record in records
        if record.get("collection_payload", {}).get("source_coverage", {}).get(
            "integrity_examples"
        )
    ]
    if integrity_records:
        lines.extend(["", "## Source integrity details", ""])
        for record in integrity_records:
            coverage = record["collection_payload"]["source_coverage"]
            lines.append(
                f"### {record.get('period_start', '')}..{record.get('period_end', '')}"
            )
            lines.append(
                f"- Incomplete rows: `{coverage.get('incomplete_row_count', 'unknown')}`"
            )
            for item in coverage.get("integrity_examples", []):
                lines.append(
                    "- `{date}` / `{symbol}`: missing {fields}; `{classification}`; official `{official}`; receipt `{receipt}`; activity {activity}".format(
                        date=item.get("date", "unknown"),
                        symbol=item.get("symbol", "unknown"),
                        fields=", ".join(item.get("missing_fields", [])) or "unknown",
                        classification=item.get("classification", "cause_unverified"),
                        official=json.dumps(item.get("official_ohlc", {}), ensure_ascii=False, sort_keys=True),
                        receipt=item.get("official_receipt_sha256") or "unverified",
                        activity=json.dumps(item.get("activity", {}), ensure_ascii=False, sort_keys=True),
                    )
                )
            if coverage.get("integrity_examples_truncated"):
                lines.append("- More rows omitted; see the JSON packet.")
    lines.extend(
        [
            "",
            "## Required human input",
            "",
            "- 逐期確認 source freshness、quality、warnings、blocking gaps 與 follow-up。",
            "- 填寫具名 owner／reviewer、review decision（reviewed／dismissed／follow_up）、reviewed_at 與 note。",
            "- 只有人工核准流程另外產生相容的 approved-weekly-history projection 後，UI 才能揭露核准期數；本 packet 不會自動轉換。",
        ]
    )
    return "\n".join(lines) + "\n"


def validate_output_path(output_path: str | Path, *, sidecar_path: str | Path) -> Path:
    """Reject destructive or misleading output targets before writing a packet."""

    output = Path(output_path).expanduser().resolve()
    sidecar = Path(sidecar_path).expanduser().resolve()
    if output == sidecar:
        raise ValueError("approval packet output must not overwrite the source sidecar")
    if output.name.lower() == "twstock.db":
        raise ValueError("approval packet output must not overwrite a source database")
    if not output.parent.exists():
        raise ValueError("approval packet output parent must already exist")
    return output


def write_weekly_approval_input_packet(
    packet: Mapping[str, Any],
    output_path: str | Path,
    *,
    sidecar_path: str | Path,
) -> Path:
    """Write a candidate packet to a new path and refuse replacement."""

    if packet.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("approval packet schema is unsupported")
    if packet.get("candidate_only") is not True:
        raise ValueError("approval packet must remain candidate-only")
    for key in (
        "formal_credit_authorized",
        "production_scheduler_allowed",
        "write_performed",
        "approved_projection_emitted",
    ):
        if packet.get(key) is not False:
            raise ValueError(f"approval packet flag must remain false: {key}")
    output = validate_output_path(output_path, sidecar_path=sidecar_path)
    serialized = json.dumps(packet, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    created = False
    try:
        handle = output.open("x", encoding="utf-8", newline="\n")
        created = True
        with handle:
            handle.write(serialized)
            handle.flush()
    except FileExistsError as exc:
        raise ValueError("approval packet output already exists; choose a new file") from exc
    except Exception:
        # The file was created exclusively by this call; remove only that partial artifact.
        if created and output.exists():
            output.unlink()
        raise
    return output

