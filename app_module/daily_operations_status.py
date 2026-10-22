"""以唯讀觀察與同次收據保守分類每日營運狀態。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath
from typing import Any, Mapping


SCHEMA = "daily-operations-observation.v1"
MAX_COMPONENTS = 128
MAX_TEXT = 2048
MAX_LIST = 128
SUCCESS_STATUSES = frozenset({"passed", "succeeded", "completed"})
SOURCE_BLOCKED_STATUSES = frozenset({"blocked", "rejected", "blocked_source", "source_blocked"})
SOURCE_PENDING_STATUSES = frozenset({"pending", "unmatured", "not_mature", "waiting_for_maturity"})
FAILURE_STATUSES = frozenset({"failed", "failure", "error", "exception", "cancelled"})
STALE_STATUSES = frozenset({"stale", "expired", "receipt_expired", "evidence_expired"})
STATES = frozenset({"HEALTHY", "DEGRADED", "STALE", "BLOCKED_SOURCE", "EXECUTION_FAILED", "UNKNOWN"})
_TAIPEI_TIMEZONE = timezone(timedelta(hours=8), name="Asia/Taipei")

TRACK_KEYS = (
    "windows_execution",
    "application_receipt",
    "source_freshness",
    "financial_qualification",
    "dependency_readiness",
    "observability",
)


class ObservationError(ValueError):
    """觀察清單不符合有界輸入契約。"""


def parse_aware_timestamp(value: object, field: str) -> datetime:
    """只接受明確時區的有限長度 ISO 時間。"""
    if not isinstance(value, str) or not value.strip() or len(value) > 80:
        raise ObservationError(f"{field}:expected_iso_timestamp")
    try:
        result = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ObservationError(f"{field}:invalid_iso_timestamp") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ObservationError(f"{field}:timezone_required")
    return result.astimezone(timezone.utc)


def validate_manifest(value: object) -> dict[str, Any]:
    """驗證觀察輸入的schema、大小範圍與欄位型別。"""
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise ObservationError("manifest:schema_mismatch")
    observed = parse_aware_timestamp(value.get("observed_at"), "observed_at")
    if observed > datetime.now(timezone.utc):
        raise ObservationError("observed_at:future_timestamp")
    components = value.get("components")
    if not isinstance(components, list) or len(components) > MAX_COMPONENTS:
        raise ObservationError("components:invalid_count")
    seen: set[str] = set()
    required = {
        "id", "enabled", "expected_enabled", "scheduler_result",
        "scheduler_last_run_at", "producer_status", "producer_run_id",
        "receipt_ref", "receipt_identity_verified", "blockers", "stale",
        "writes_formal_data", "downstream_ids",
    }
    for index, row in enumerate(components):
        if not isinstance(row, dict) or not required.issubset(row):
            raise ObservationError(f"components[{index}]:missing_fields")
        ident = row["id"]
        if not isinstance(ident, str) or not ident.strip() or len(ident) > MAX_TEXT:
            raise ObservationError(f"components[{index}].id:invalid")
        if ident in seen:
            raise ObservationError(f"components[{index}].id:duplicate")
        seen.add(ident)
        for key in ("enabled", "expected_enabled", "receipt_identity_verified", "stale", "writes_formal_data"):
            if type(row[key]) is not bool:
                raise ObservationError(f"components[{index}].{key}:expected_boolean")
        scheduler_result = row["scheduler_result"]
        if scheduler_result is not None and type(scheduler_result) is not int:
            raise ObservationError(f"components[{index}].scheduler_result:expected_integer_or_null")
        last_run = row["scheduler_last_run_at"]
        if last_run is not None:
            parse_aware_timestamp(last_run, f"components[{index}].scheduler_last_run_at")
        for key in ("producer_status", "producer_run_id"):
            if row[key] is not None and (not isinstance(row[key], str) or len(row[key]) > MAX_TEXT):
                raise ObservationError(f"components[{index}].{key}:invalid")
        ref = row["receipt_ref"]
        if ref is not None and (
            not isinstance(ref, dict)
            or set(ref) != {"path", "sha256"}
            or not isinstance(ref.get("path"), str)
            or not ref["path"]
            or len(ref["path"]) > MAX_TEXT
            or not isinstance(ref.get("sha256"), str)
            or len(ref["sha256"]) != 64
            or any(ch not in "0123456789abcdefABCDEF" for ch in ref["sha256"])
        ):
            raise ObservationError(f"components[{index}].receipt_ref:invalid")
        for key in ("blockers", "downstream_ids"):
            items = row[key]
            if not isinstance(items, list) or len(items) > MAX_LIST or any(
                not isinstance(item, str) or not item.strip() or len(item) > MAX_TEXT for item in items
            ):
                raise ObservationError(f"components[{index}].{key}:invalid")
        if len(set(row["downstream_ids"])) != len(row["downstream_ids"]):
            raise ObservationError(f"components[{index}].downstream_ids:duplicate")
    value["_observed_at_utc"] = observed
    return value


def _track(status: str, raw: object, reasons: list[str]) -> dict[str, Any]:
    if status not in STATES:
        status = "UNKNOWN"
    return {"status": status, "raw": raw, "reason": reasons or ["no_supported_observation"]}


def _identity_errors(
    row: Mapping[str, Any], receipt: Mapping[str, Any], observed: datetime
) -> tuple[list[str], datetime | None]:
    reasons: list[str] = []
    receipt_run_id = receipt.get("run_id")
    expected_run_id = row.get("producer_run_id")
    receipt_task = receipt.get("producer_task")
    if receipt_task is not None and receipt_task != row.get("id"):
        reasons.append("receipt_task_mismatch")
    if not isinstance(receipt_run_id, str) or not receipt_run_id.strip():
        reasons.append("receipt_run_id_missing")
    elif not isinstance(expected_run_id, str) or not expected_run_id.strip():
        reasons.append("producer_run_id_unbound")
    elif receipt_run_id != expected_run_id:
        reasons.append("receipt_run_id_mismatch")

    started: datetime | None = None
    try:
        started = parse_aware_timestamp(receipt.get("started_at"), "receipt.started_at")
    except ObservationError:
        reasons.append("receipt_started_at_missing_or_invalid")
    if started is not None and started > observed:
        reasons.append("receipt_timestamp_future")
        started = None

    completed: datetime | None = None
    try:
        completed = parse_aware_timestamp(receipt.get("completed_at"), "receipt.completed_at")
    except ObservationError:
        reasons.append("receipt_completed_at_missing_or_invalid")
    if completed is not None:
        if started is not None and completed < started:
            reasons.append("receipt_completed_before_started")
        if completed > observed:
            reasons.append("receipt_completed_at_future")

    scheduler_raw = row.get("scheduler_last_run_at")
    if scheduler_raw is None:
        reasons.append("scheduler_run_unbound")
    else:
        try:
            scheduler_at = parse_aware_timestamp(scheduler_raw, "scheduler_last_run_at")
        except ObservationError:
            reasons.append("scheduler_run_time_invalid")
        else:
            if scheduler_at > observed:
                reasons.append("scheduler_timestamp_future")
            if started is not None and abs((started - scheduler_at).total_seconds()) > 300:
                reasons.append("receipt_scheduler_time_mismatch")
    return reasons, started


def _paper_eod_projection_is_correlated(
    row: Mapping[str, Any],
    projection: object,
    *,
    observed_at: datetime,
) -> bool:
    """驗證專用Paper gate摘要；不把時間關聯冒充producer run ID。"""
    expected_keys = {
        "schema",
        "source_schema",
        "raw_sha256_verified",
        "evidence_kind",
        "target_date",
        "observed_at",
        "receipt_path",
        "raw_sha256",
        "blocker_count",
        "blockers_validation",
        "source_basis",
        "source_db_written",
        "source_files_written",
    }
    if not isinstance(projection, Mapping) or set(projection) != expected_keys:
        return False
    if (
        projection.get("schema") != "paper-eod-blocked-reader-projection.v1"
        or projection.get("source_schema") != "paper-execution-dependency-gate.v1"
        or projection.get("raw_sha256_verified") is not True
        or projection.get("evidence_kind")
        != "scheduler_time_correlated_not_producer_run_id"
        or projection.get("blockers_validation") != "not_performed_above_128"
        or projection.get("source_basis")
        != "sqlite.daily_prices_stale_and_target_mismatch"
        or projection.get("source_db_written") is not False
        or projection.get("source_files_written") is not False
        or type(projection.get("blocker_count")) is not int
        or projection["blocker_count"] <= MAX_LIST
    ):
        return False

    receipt_ref = row.get("receipt_ref")
    expected_hash = projection.get("raw_sha256")
    receipt_hash = receipt_ref.get("sha256") if isinstance(receipt_ref, Mapping) else None
    projection_path = projection.get("receipt_path")
    path_parts = PurePosixPath(projection_path).parts if isinstance(projection_path, str) else ()
    if (
        row.get("id") != "baldr-paper-execution-eod-replay-daily"
        or row.get("enabled") is not True
        or row.get("expected_enabled") is not True
        or row.get("scheduler_result") != 2
        or type(row.get("scheduler_result")) is not int
        or row.get("stale") is not False
        or row.get("writes_formal_data") is not False
        or row.get("producer_status") != "blocked"
        or row.get("producer_run_id") is not None
        or row.get("receipt_identity_verified") is not False
        or not isinstance(receipt_ref, Mapping)
        or not isinstance(projection_path, str)
        or not projection_path
        or PurePosixPath(projection_path).is_absolute()
        or any(part in {"", ".", ".."} for part in path_parts)
        or "\\" in projection_path
        or receipt_ref.get("path") != projection_path
        or not isinstance(expected_hash, str)
        or len(expected_hash) != 64
        or any(character not in "0123456789abcdef" for character in expected_hash)
        or not isinstance(receipt_hash, str)
        or receipt_hash.lower() != expected_hash
    ):
        return False

    target_date = projection.get("target_date")
    try:
        target = datetime.fromisoformat(target_date) if isinstance(target_date, str) else None
        gate_time = datetime.fromisoformat(
            str(projection.get("observed_at")).replace("Z", "+00:00")
        )
        scheduler_time = datetime.fromisoformat(
            str(row.get("scheduler_last_run_at")).replace("Z", "+00:00")
        )
    except ValueError:
        return False
    if (
        target is None
        or target.date().isoformat() != target_date
        or gate_time.tzinfo is None
        or gate_time.utcoffset() is None
        or scheduler_time.tzinfo is None
        or scheduler_time.utcoffset() is None
        or gate_time.astimezone(_TAIPEI_TIMEZONE).date().isoformat() != target_date
        or scheduler_time.astimezone(_TAIPEI_TIMEZONE).date().isoformat() != target_date
    ):
        return False
    gate_utc = gate_time.astimezone(timezone.utc)
    scheduler_utc = scheduler_time.astimezone(timezone.utc)
    if (
        gate_utc < scheduler_utc
        or gate_utc - scheduler_utc > timedelta(minutes=5)
        or gate_utc > observed_at.astimezone(timezone.utc)
    ):
        return False
    return True


def _adapter_track(
    name: str,
    adapted: Mapping[str, Any],
    *,
    same_run: bool,
    identity_reasons: list[str],
) -> dict[str, Any]:
    data = adapted.get(name)
    data = data if isinstance(data, Mapping) else {}
    raw = data.get("raw_status")
    if not same_run:
        return _track("UNKNOWN", raw, identity_reasons or ["receipt_not_same_run_verified"])
    semantic = data.get("semantic")
    raw_values = [item.strip().lower() for item in raw if isinstance(item, str)] if isinstance(raw, list) else []
    normalized = raw.strip().lower() if isinstance(raw, str) else ""
    if name == "source_freshness":
        if normalized in {"current", "fresh"} or (raw_values and all(item in {"current", "fresh"} for item in raw_values)) or (semantic == "passed" and not raw_values):
            status, reasons = "HEALTHY", ["same_run_source_freshness_verified"]
        elif normalized == "stale" or "stale" in raw_values:
            status, reasons = "STALE", ["same_run_source_stale"]
        elif normalized in {"failed", "blocked", "rejected"} or any(item in {"failed", "blocked", "rejected"} for item in raw_values):
            status, reasons = "BLOCKED_SOURCE", ["same_run_source_not_usable"]
        elif semantic in {"degraded", "not_applicable"} or normalized in {"partial", "expected_wait", "not_applicable"} or any(
            item in {"partial", "expected_wait", "not_applicable"} for item in raw_values
        ):
            status, reasons = "DEGRADED", [f"same_run_source_status:{normalized or 'degraded'}"]
        else:
            status, reasons = "UNKNOWN", ["source_freshness_missing_or_unsupported"]
    elif name == "financial_qualification":
        if semantic == "not_qualified" or normalized in {"not_qualified", "disqualified", "false", "unqualified"} or any(item in {"not_qualified", "disqualified", "false", "unqualified"} for item in raw_values):
            status, reasons = "BLOCKED_SOURCE", ["explicit_financial_qualification_not_accepted"]
        elif semantic == "qualified" or normalized in {"qualified", "passed", "true"} or any(item in {"qualified", "passed", "true"} for item in raw_values):
            status, reasons = "UNKNOWN", ["positive_claim_lacks_external_accepted_evidence"]
        else:
            status, reasons = "UNKNOWN", ["financial_qualification_not_observed"]
    elif name == "dependency_readiness":
        if semantic == "passed":
            status, reasons = "HEALTHY", ["same_run_dependency_ready"]
        elif semantic == "degraded":
            status, reasons = "DEGRADED", ["same_run_dependency_degraded"]
        elif semantic == "blocked":
            status, reasons = "BLOCKED_SOURCE", ["same_run_dependency_blocked"]
        elif semantic == "failed":
            status, reasons = "EXECUTION_FAILED", ["same_run_dependency_failed"]
        else:
            status, reasons = "UNKNOWN", ["dependency_readiness_missing_or_unsupported"]
    else:
        # CLI已核對有界唯讀檔案、SHA-256、run ID及排程時鐘；producer自述不構成身份證據。
        status, reasons = "HEALTHY", ["exact_identity_hash_clock_verified"]
    return _track(status, raw, reasons)


def _known_root_cause(
    *,
    expected_disabled: bool,
    stale: bool,
    raw_status: object,
    reason_codes: list[str],
    evidence_text: list[str],
) -> tuple[str, str, str, str | None]:
    if expected_disabled:
        return "EXPECTED_FAIL_CLOSED", "policy", "none_expected_disabled", None
    normalized_status = raw_status.strip().lower() if isinstance(raw_status, str) else ""
    normalized_evidence = [item.strip().lower() for item in evidence_text if isinstance(item, str)]
    known_codes = {item.lower() for item in reason_codes}
    evidence_codes = set(normalized_evidence)
    all_text = " ".join(normalized_evidence)
    if (
        normalized_status in {"db_path_mismatch", "database_path_mismatch", "receipt_db_path_mismatch"}
        or any(code in known_codes for code in {"db_path_mismatch", "database_path_mismatch", "receipt_db_path_mismatch"})
        or bool(evidence_codes & {"db_path_mismatch", "database_path_mismatch", "receipt_db_path_mismatch"})
        or "database path mismatch" in all_text
        or "db path mismatch" in all_text
    ):
        return "PATH_OR_CUSTODY_MISMATCH", "source_identity", "verify_source_and_destination_identity", "review_migration_custody"
    runtime_expired = lambda item: item == "runtime_config_expired" or item.startswith("runtime_config_expired:")
    if (
        runtime_expired(normalized_status)
        or any(runtime_expired(item) for item in known_codes)
        or any(runtime_expired(item) for item in evidence_codes)
    ):
        return "CONFIG_DEFECT", "configuration", "inspect_runtime_config_expiry", "review_runtime_configuration"
    if stale or normalized_status in {"expired", "receipt_expired", "evidence_expired", "stale"} or bool(
        evidence_codes & {"expired", "receipt_expired", "evidence_expired", "stale_evidence"}
    ):
        return "STALE_EVIDENCE", "freshness", "obtain_a_fresh_observation", "review_observation_age"
    if (
        any(code.startswith(("receipt_missing", "receipt_ref_missing", "receipt_schema_unsupported", "schema_unsupported")) for code in known_codes)
        or bool(known_codes & {"receipt_sha256_mismatch", "receipt_not_object", "json_invalid", "schema_mismatch"})
        or bool(evidence_codes & {"receipt_sha256_mismatch", "receipt_not_object", "json_invalid", "schema_mismatch", "schema_unsupported"})
        or bool(known_codes & {
            "receipt_run_id_missing", "producer_run_id_unbound", "receipt_run_id_mismatch",
            "receipt_task_mismatch",
            "receipt_started_at_missing_or_invalid", "receipt_completed_at_missing_or_invalid",
            "scheduler_run_unbound", "scheduler_run_time_invalid", "receipt_scheduler_time_mismatch",
        })
        or normalized_status in {"unsupported_schema", "missing_receipt", "receipt_missing"}
        or any(token in all_text for token in ("unsupported schema", "missing receipt", "receipt missing"))
    ):
        return "OBSERVABILITY_GAP", "observability", "collect_a_supported_same_run_receipt", "obtain_supported_receipt_evidence"
    return "UNKNOWN", "unknown", "reconcile_named_evidence_without_guessing", None


def classify_component(
    row: Mapping[str, Any],
    *,
    receipt: Mapping[str, Any] | None = None,
    receipt_error: str | None = None,
    observed_at: datetime | None = None,
) -> dict[str, Any]:
    """分類單筆觀察；收據必須由CLI唯讀讀取並通過固定SHA驗證。"""
    ident = str(row["id"])
    observed = observed_at or datetime.now(timezone.utc)
    expected_disabled = row.get("expected_enabled") is False
    windows_enabled = row.get("enabled") is True
    scheduler_result = row.get("scheduler_result")
    if expected_disabled:
        windows = _track("DEGRADED", scheduler_result, ["expected_disabled"])
    elif not windows_enabled:
        windows = _track("DEGRADED", scheduler_result, ["expected_enabled_but_disabled"])
    elif scheduler_result is None:
        windows = _track("UNKNOWN", None, ["scheduler_result_missing"])
    elif scheduler_result == 0:
        windows = _track("HEALTHY", 0, ["windows_task_exit_zero"])
    else:
        windows = _track("EXECUTION_FAILED", scheduler_result, [f"scheduler_execution_failed:{scheduler_result}"])
    windows["raw"] = {
        "enabled": row.get("enabled"),
        "expected_enabled": row.get("expected_enabled"),
        "scheduler_result": scheduler_result,
        "scheduler_last_run_at": row.get("scheduler_last_run_at"),
    }

    stale = row.get("stale") is True
    source_observation = _track("STALE", "stale", ["observation_marked_stale"]) if stale else None
    adapted: Mapping[str, Any] = receipt or {}
    receipt_kind = adapted.get("kind")
    identity_reasons: list[str] = []
    same_run = False
    if receipt_error:
        identity_reasons.append(f"receipt_unverified:{receipt_error}")
    if receipt is None:
        identity_reasons.append("receipt_missing_or_unbound")
    elif receipt_kind != "producer" or adapted.get("supported") is not True:
        identity_reasons.append("receipt_schema_unsupported_or_non_producer")
    else:
        identity_reasons.extend(_identity_errors(row, adapted, observed)[0])
        same_run = not identity_reasons and receipt_error is None
    if row.get("receipt_identity_verified"):
        identity_reasons.append("manifest_identity_claim_not_trusted")

    raw_status = adapted.get("producer_status") if isinstance(adapted.get("producer_status"), str) else None
    producer_semantic = adapted.get("producer_status_semantic")
    application_raw = {
        "schema": adapted.get("schema"),
        "kind": receipt_kind,
        "run_id": adapted.get("run_id"),
        "started_at": adapted.get("started_at"),
        "completed_at": adapted.get("completed_at"),
        "status": raw_status,
        "gate_reference_verification": adapted.get("gate_reference_verification"),
    }
    bounded_projection = adapted.get("_bounded_paper_eod_projection")
    projection_correlated = (
        receipt_error is None
        and _paper_eod_projection_is_correlated(
            row, bounded_projection, observed_at=observed
        )
    )
    if projection_correlated:
        application_raw["evidence_kind"] = (
            "scheduler_time_correlated_not_producer_run_id"
        )
        application_raw["bounded_gate_projection"] = dict(bounded_projection)  # type: ignore[arg-type]
    normalized_status = raw_status.strip().lower() if isinstance(raw_status, str) else ""
    receipt_blockers = adapted.get("blockers")
    blockers = list(receipt_blockers) if isinstance(receipt_blockers, list) else []
    app_reasons = list(identity_reasons)
    app_status = "UNKNOWN"
    if projection_correlated:
        app_status = "BLOCKED_SOURCE"
        app_reasons = [
            "pinned_paper_eod_gate_source_blocked_bounded_projection",
            "blockers_not_validated_above_128:"
            f"{bounded_projection['blocker_count']}",  # type: ignore[index]
        ]
    elif same_run:
        if blockers:
            app_status, app_reasons = "BLOCKED_SOURCE", [f"named_blocker:{item}" for item in blockers]
        elif producer_semantic == "passed" or normalized_status in SUCCESS_STATUSES:
            app_status, app_reasons = "HEALTHY", ["same_run_application_receipt_succeeded"]
        elif normalized_status in SOURCE_BLOCKED_STATUSES:
            app_reasons = ["source_blocked_without_named_blocker"]
        elif producer_semantic == "blocked":
            app_reasons = ["source_blocked_without_named_blocker"]
        elif producer_semantic == "degraded" or producer_semantic == "not_applicable" or normalized_status in SOURCE_PENDING_STATUSES:
            app_status, app_reasons = "DEGRADED", [f"source_not_mature:{normalized_status}"]
        elif normalized_status in STALE_STATUSES:
            app_status, app_reasons = "STALE", [f"receipt_evidence_stale:{normalized_status}"]
        elif producer_semantic == "failed" or normalized_status in FAILURE_STATUSES:
            app_status, app_reasons = "EXECUTION_FAILED", [f"producer_execution_failed:{normalized_status}"]
        elif blockers:
            app_status, app_reasons = "BLOCKED_SOURCE", [f"named_blocker:{item}" for item in blockers]
        else:
            app_reasons = [f"unsupported_receipt_status:{normalized_status or 'missing'}"]
    elif normalized_status in FAILURE_STATUSES:
        app_reasons.append("unverified_failure_not_attributed_to_this_run")

    tracks: dict[str, dict[str, Any]] = {
        "windows_execution": windows,
        "application_receipt": _track(app_status, application_raw, app_reasons),
    }
    for name in ("source_freshness", "financial_qualification", "dependency_readiness", "observability"):
        tracks[name] = _adapter_track(
            name, adapted, same_run=same_run, identity_reasons=identity_reasons
        )
    if source_observation is not None and tracks["source_freshness"]["status"] == "UNKNOWN":
        tracks["source_freshness"] = source_observation

    if expected_disabled:
        status = "DEGRADED"
        reasons = ["expected_disabled"]
    elif scheduler_result not in (None, 0):
        status = "EXECUTION_FAILED"
        reasons = [f"scheduler_execution_failed:{scheduler_result}"]
    elif stale:
        status = "STALE"
        reasons = ["observation_marked_stale"]
    elif app_status != "HEALTHY":
        status = app_status
        reasons = list(tracks["application_receipt"]["reason"])
    elif windows["status"] != "HEALTHY":
        status = windows["status"]
        reasons = list(windows["reason"])
    else:
        status = "HEALTHY"
        reasons = ["same_run_success_receipt_verified"]
    if row.get("blockers"):
        reasons.extend(f"observation_blocker:{item}" for item in row["blockers"])
        if status not in {"EXECUTION_FAILED", "STALE", "DEGRADED"}:
            status = "BLOCKED_SOURCE"

    evidence_text: list[str] = list(row["blockers"])
    if receipt_error:
        evidence_text.append(receipt_error)
    if same_run:
        for field in ("blockers", "errors", "warnings", "blocker"):
            value = adapted.get(field)
            if isinstance(value, str):
                evidence_text.append(value)
            elif isinstance(value, list):
                evidence_text.extend(item for item in value if isinstance(item, str))
    for track in tracks.values():
        evidence_text.extend(item for item in track["reason"] if isinstance(item, str))
    root_cause, category, next_check, owner_action = _known_root_cause(
        expected_disabled=expected_disabled,
        stale=stale,
        raw_status=raw_status if same_run else None,
        reason_codes=reasons,
        evidence_text=evidence_text,
    )
    if status == "HEALTHY":
        next_check = "continue_next_natural_observation"
        owner_action = None
    return {
        "id": ident,
        "status": status,
        "reason": reasons,
        "tracks": tracks,
        "root_cause": root_cause,
        "category": category,
        "next_natural_verification": next_check,
        "owner_action_required": owner_action,
        "alert_recommended": not expected_disabled and status != "HEALTHY",
        "auto_action": "none_read_only_audit",
        "safe_retry": False,
        "downstream_hold": status != "HEALTHY",
        "downstream_ids": list(row["downstream_ids"]),
    }


def classify_manifest(
    manifest: Mapping[str, Any],
    receipts: Mapping[str, Mapping[str, Any] | None],
    receipt_errors: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """輸出逐task狀態；維持未知值，不把缺測折算成零或成功。"""
    observed_at = manifest.get("_observed_at_utc")
    if not isinstance(observed_at, datetime):
        observed_at = parse_aware_timestamp(manifest.get("observed_at"), "observed_at")
    errors = receipt_errors or {}
    return {
        "schema": "daily-operations-audit.v1",
        "observed_at": manifest["observed_at"],
        "components": [
            classify_component(
                row,
                receipt=receipts.get(row["id"]),
                receipt_error=errors.get(row["id"]),
                observed_at=observed_at,
            )
            for row in manifest["components"]
        ],
    }
