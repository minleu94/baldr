"""每日排程觀察資料的保守、唯讀狀態分類。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping


SCHEMA = "daily-operations-observation.v1"
MAX_COMPONENTS = 128
MAX_TEXT = 2048
MAX_LIST = 128
SUCCESS_STATUSES = frozenset({"passed", "succeeded", "completed"})
SOURCE_BLOCKED_STATUSES = frozenset({"blocked", "rejected", "blocked_source", "source_blocked"})
SOURCE_PENDING_STATUSES = frozenset({"pending", "unmatured", "not_mature", "waiting_for_maturity"})
FAILURE_STATUSES = frozenset({"failed", "failure", "error", "exception", "cancelled"})


class ObservationError(ValueError):
    """觀察清單不符合有界輸入契約。"""


def parse_aware_timestamp(value: object, field: str) -> datetime:
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


def classify_component(
    row: Mapping[str, Any],
    *,
    receipt: Mapping[str, Any] | None = None,
    receipt_error: str | None = None,
    observed_at: datetime | None = None,
) -> dict[str, Any]:
    """分類單筆觀察；``receipt`` 必須來自 CLI 的有界讀取器。"""
    ident = str(row["id"])
    expected_enabled = row["expected_enabled"]
    enabled = row["enabled"]
    blockers = list(row["blockers"])
    status = "UNKNOWN"
    reasons: list[str] = []

    if not expected_enabled:
        reasons.append("expected_disabled")
        status = "DEGRADED"
    elif not enabled:
        reasons.append("expected_enabled_but_disabled")
        status = "DEGRADED"
    elif row["stale"]:
        reasons.append("observation_marked_stale")
        status = "STALE"
    elif blockers:
        reasons.extend(f"blocker:{item}" for item in blockers)
        status = "BLOCKED_SOURCE"
    else:
        observed = observed_at
        if observed is None:
            observed = datetime.now(timezone.utc)
        if receipt_error:
            reasons.append(f"receipt_unverified:{receipt_error}")
        if receipt is None:
            reasons.append("receipt_missing_or_unbound")
        else:
            raw_status = receipt.get("producer_status") or receipt.get("status")
            normalized = raw_status.strip().lower() if isinstance(raw_status, str) else ""
            receipt_blockers = receipt.get("blockers", [])
            if isinstance(receipt_blockers, list):
                blockers.extend(
                    item for item in receipt_blockers
                    if isinstance(item, str) and item.strip() and item not in blockers
                )
            receipt_run_id = receipt.get("run_id")
            receipt_started_raw = receipt.get("started_at")
            expected_run_id = row.get("producer_run_id")
            scheduler_raw = row.get("scheduler_last_run_at")
            if not isinstance(receipt_run_id, str) or not receipt_run_id.strip():
                reasons.append("receipt_run_id_missing")
            elif not isinstance(expected_run_id, str) or not expected_run_id.strip():
                reasons.append("producer_run_id_unbound")
            elif receipt_run_id != expected_run_id:
                reasons.append("receipt_run_id_mismatch")
            try:
                receipt_started = parse_aware_timestamp(receipt_started_raw, "receipt.started_at")
            except ObservationError:
                receipt_started = None
                reasons.append("receipt_started_at_missing_or_invalid")
            if receipt_started is not None and receipt_started > observed:
                reasons.append("receipt_timestamp_future")
                receipt_started = None
            completed_raw = receipt.get("completed_at")
            completed_at: datetime | None = None
            if completed_raw is None:
                reasons.append("receipt_completed_at_missing")
            else:
                try:
                    completed_at = parse_aware_timestamp(completed_raw, "receipt.completed_at")
                except ObservationError:
                    reasons.append("receipt_completed_at_invalid")
            if completed_at is not None:
                if receipt_started is not None and completed_at < receipt_started:
                    reasons.append("receipt_completed_before_started")
                if completed_at > observed:
                    reasons.append("receipt_completed_at_future")
            if scheduler_raw is None:
                reasons.append("scheduler_run_unbound")
            elif receipt_started is not None:
                scheduler_at = parse_aware_timestamp(scheduler_raw, "scheduler_last_run_at")
                if scheduler_at > observed:
                    reasons.append("scheduler_timestamp_future")
                elif abs((receipt_started - scheduler_at).total_seconds()) > 300:
                    reasons.append("receipt_scheduler_time_mismatch")
            if not isinstance(raw_status, str) or not normalized:
                reasons.append("receipt_status_missing")
            elif normalized in SOURCE_BLOCKED_STATUSES:
                if blockers:
                    reasons.extend(f"blocker:{item}" for item in blockers if f"blocker:{item}" not in reasons)
                    status = "BLOCKED_SOURCE"
                else:
                    reasons.append("source_blocked_without_named_blocker")
            elif normalized in SOURCE_PENDING_STATUSES:
                reasons.append(f"source_not_mature:{normalized}")
                status = "DEGRADED"
            elif normalized in FAILURE_STATUSES:
                reasons.append(f"producer_execution_failed:{normalized}")
                status = "EXECUTION_FAILED"
            elif blockers:
                reasons.extend(f"blocker:{item}" for item in blockers if f"blocker:{item}" not in reasons)
                status = "BLOCKED_SOURCE"
            elif normalized not in SUCCESS_STATUSES:
                reasons.append(f"unsupported_receipt_status:{normalized}")
            elif not any(reason in reasons for reason in (
                "receipt_run_id_missing", "receipt_run_id_mismatch",
                "producer_run_id_unbound",
                "receipt_started_at_missing_or_invalid", "receipt_timestamp_future",
                "receipt_completed_at_missing", "receipt_completed_at_invalid",
                "receipt_completed_before_started", "receipt_completed_at_future",
                "scheduler_run_unbound", "scheduler_timestamp_future", "receipt_scheduler_time_mismatch",
            )) and receipt_error is None and row.get("scheduler_result") == 0:
                status = "HEALTHY"
                reasons.append("same_run_success_receipt_verified")

        scheduler_result = row.get("scheduler_result")
        if scheduler_result not in (None, 0) and status not in {"BLOCKED_SOURCE", "DEGRADED", "STALE"}:
            status = "EXECUTION_FAILED"
            reasons.append(f"scheduler_execution_failed:{scheduler_result}")

    if not reasons:
        reasons.append("insufficient_verified_evidence")
    return {
        "id": ident,
        "status": status,
        "reason": reasons,
        "auto_action": "none_read_only_audit",
        "manual_action": _manual_action(status, reasons),
        "safe_retry": False,
        "downstream_hold": status != "HEALTHY",
        "downstream_ids": list(row["downstream_ids"]),
    }


def classify_manifest(
    manifest: Mapping[str, Any],
    receipts: Mapping[str, Mapping[str, Any] | None],
    receipt_errors: Mapping[str, str] | None = None,
) -> dict[str, Any]:
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


def _manual_action(status: str, reasons: list[str]) -> str:
    if status == "HEALTHY":
        return "none"
    if status == "DEGRADED":
        return "review_maturity_or_expected_disabled_state"
    if status == "BLOCKED_SOURCE":
        return "inspect_named_source_blockers"
    if status == "STALE":
        return "inspect_observation_freshness_before_any_run"
    if status == "EXECUTION_FAILED":
        return "inspect_task_and_producer_logs_before_deciding"
    return "obtain_supported_same_run_receipt_and_reconcile_identity"
