"""將已知排程收據映射為每日營運狀態的唯讀輸入。"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any


# 僅接受已核對過的 producer 契約；schema 字串不做前綴或相似度比對。
_SCHEMAS: dict[str, str] = {
    "decision-evidence-capture.v1": "producer",
    "formal-input-daily-producer-receipt.v1": "producer",
    "formal-input-producer-terminal-receipt.v1": "producer",
    "formal-pit-sidecar-scheduled-status.v1": "producer",
    "scheduled-forward-outcomes.v1": "producer",
    "ml-allocation-daily-orchestration.v3": "producer",
    "ml-forward-scheduled-status.v1": "producer",
    "baldr-ml-promotion-authority-status.v1": "producer",
    "ml-promotion-evidence-pipeline-status.v3": "producer",
    "ml-raw-pit-refresh-status.v1": "producer",
    "scheduled-official-market-events-wrapper-pointer.v1": "pointer",
    "scheduled-official-market-status-bundle.v1": "producer",
    "paper-portfolio-daily-status.v1": "producer",
    "paper-execution-dependency-gate.v1": "producer",
    "paper-execution-dependency-gate-latest.v1": "pointer",
    "pit-preopen-capture-scheduled-status.v1": "producer",
    "banktaiwan-recommendation-learning-operational.v1": "producer",
    "daily-recommendation-learning-pipeline.v1": "producer",
    "daily-recommendation-learning-terminal-receipt.v1": "producer",
    "scheduled-weekly-collection-locator.v1": "pointer",
    "scheduled-weekly-collection-controller-receipt.v2": "producer",
    "scheduled-weekly-collection-controller-result.v1": "producer",
    "scheduled-hidden-launch.v1": "launcher",
    "baldr-data-freshness-terminal-receipt.v1": "producer",
    "baldr-evidence-pipeline-terminal-receipt.v1": "producer",
}

_STATUS_SEMANTICS = {
    "passed": "passed",
    "succeeded": "passed",
    "completed": "passed",
    "passed_with_warnings": "degraded",
    "passed_rule_only": "degraded",
    "completed_with_pending": "degraded",
    "partial": "degraded",
    "ready_with_advisories": "degraded",
    "degraded": "degraded",
    "blocked": "blocked",
    "blocked_source": "blocked",
    "blocked_config_producer": "blocked",
    "blocked_source_revision": "blocked",
    "failed": "failed",
    "execution_failed": "failed",
    "failed_dependency": "failed",
    "skipped_evidence_unavailable": "unknown",
    "skipped_non_trading_day": "not_applicable",
    "running": "in_progress",
    "authorized": "authorized",
    "exited": "launcher_completed",
    "unknown": "unknown",
    "formal_inputs_machine_verified": "passed",
    "individual_sources_verified": "degraded",
    "candidate_only": "degraded",
}

_FORMAL_TERMINAL_FIELDS = frozenset(
    {
        "schema_version",
        "task",
        "run_id",
        "started_at",
        "completed_at",
        "code_version",
        "exit_code",
        "failure_code",
        "status",
        "blockers",
        "financial_qualification_status",
        "dependency_readiness_status",
        "status_payload",
    }
)


def _formal_terminal_valid(payload: Mapping[str, Any]) -> bool:
    """核對 Formal terminal envelope 的精確欄位與 nested producer identity。"""
    if set(payload) != _FORMAL_TERMINAL_FIELDS:
        return False
    if payload.get("task") != "baldr-formal-input-producer-daily":
        return False
    run_id = payload.get("run_id")
    if not isinstance(run_id, str) or len(run_id) != 32 or run_id != run_id.lower():
        return False
    try:
        if uuid.UUID(hex=run_id).hex != run_id:
            return False
    except (ValueError, AttributeError):
        return False
    code_version = payload.get("code_version")
    if (
        not isinstance(code_version, str)
        or code_version != code_version.lower()
        or not code_version.startswith("sha256:")
        or len(code_version) != 71
        or any(
            character not in "0123456789abcdef"
            for character in code_version[7:].lower()
        )
    ):
        return False
    exit_code = payload.get("exit_code")
    if (
        not isinstance(exit_code, int)
        or isinstance(exit_code, bool)
        or exit_code not in {0, 2}
    ):
        return False
    started_at = payload.get("started_at")
    completed_at = payload.get("completed_at")
    if not isinstance(started_at, str) or not isinstance(completed_at, str):
        return False
    try:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        completed = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if (
        started.tzinfo is None
        or completed.tzinfo is None
        or started.utcoffset() != timedelta(0)
        or completed.utcoffset() != timedelta(0)
        or completed < started
    ):
        return False
    if payload.get("financial_qualification_status") != "unknown":
        return False

    nested = payload.get("status_payload")
    if not isinstance(nested, Mapping):
        return False
    if (
        nested.get("schema_version") != "formal-input-daily-producer-receipt.v1"
        or nested.get("task") != payload.get("task")
        or nested.get("run_id") != run_id
        or nested.get("wrapper_started_at") != started_at
        or nested.get("completed_at") != completed_at
        or nested.get("status") != payload.get("status")
    ):
        return False
    nested_exit_code = nested.get("exit_code")
    if (
        not isinstance(nested_exit_code, int)
        or isinstance(nested_exit_code, bool)
        or nested_exit_code != exit_code
    ):
        return False
    status = payload.get("status")
    if not isinstance(status, str) or status not in {
        "formal_inputs_machine_verified",
        "individual_sources_verified",
        "candidate_only",
        "blocked",
        "skipped_non_trading_day",
    }:
        return False
    blockers = nested.get("blockers")
    expected_receipt_blockers = list(blockers) if isinstance(blockers, list) else []
    observability_blocker = nested.get("observability_blocker")
    if (
        isinstance(observability_blocker, str)
        and observability_blocker not in expected_receipt_blockers
    ):
        expected_receipt_blockers.append(observability_blocker)
    if (
        not isinstance(blockers, list)
        or len(blockers) > 128
        or any(not isinstance(item, str) or not item.strip() for item in blockers)
        or payload.get("blockers") != expected_receipt_blockers
    ):
        return False
    first_blocker = (
        blockers[0]
        if isinstance(blockers, list)
        and blockers
        and isinstance(blockers[0], str)
        else None
    )
    expected_failure = observability_blocker or first_blocker
    failure_code = payload.get("failure_code")
    if failure_code is not None and (
        not isinstance(failure_code, str) or not failure_code.strip()
    ):
        return False
    if failure_code != expected_failure:
        return False
    if status == "formal_inputs_machine_verified":
        if exit_code == 0:
            if blockers or observability_blocker:
                return False
        elif not (
            isinstance(observability_blocker, str)
            and observability_blocker.strip()
        ):
            return False
    elif status == "skipped_non_trading_day":
        if exit_code != 0:
            return False
    elif exit_code != 2:
        return False
    expected_dependency = (
        "blocked"
        if observability_blocker
        else "passed"
        if exit_code == 0 and status == "formal_inputs_machine_verified"
        else "not_applicable"
        if status == "skipped_non_trading_day"
        else "blocked"
    )
    return payload.get("dependency_readiness_status") == expected_dependency

_TRACK_STATUS_KEYS = {
    "source_freshness": ("freshness_status", "source_status", "freshness"),
    "financial_qualification": ("financial_qualification_status", "financial_status"),
    "dependency_readiness": ("dependency_readiness_status", "dependency_status"),
    "observability": ("observability_status", "receipt_status"),
}

_TRACK_SEMANTICS = {
    "source_freshness": {
        "current": "passed", "fresh": "passed", "expected_wait": "not_applicable",
        "stale": "degraded", "partial": "degraded", "failed": "failed",
        "not_applicable": "not_applicable", "unknown": "unknown",
    },
    "financial_qualification": {
        "qualified": "qualified", "passed": "qualified", "not_qualified": "not_qualified",
        "disqualified": "not_qualified", "unknown": "unknown", "not_assessed": "not_applicable",
    },
    "dependency_readiness": {
        "ready": "passed", "passed": "passed", "degraded": "degraded",
        "partial": "degraded", "blocked": "blocked", "failed": "failed", "unknown": "unknown",
    },
    "observability": {
        "verified": "passed", "same_run_verified": "passed", "same_day_status_only": "degraded",
        "stale_or_mismatch": "failed", "missing": "unknown", "unknown": "unknown",
    },
}


def _semantic(status: object) -> str:
    """只翻譯明列的原始狀態值，未知值維持未知。"""
    if not isinstance(status, str):
        return "unknown"
    return _STATUS_SEMANTICS.get(status, "unknown")


def _track_semantic(name: str, raw: object) -> str:
    """依收據軌道的專屬詞彙分類，不借用 producer 狀態表。"""
    mapping = _TRACK_SEMANTICS[name]
    if isinstance(raw, list):
        values = [mapping.get(item, "unknown") for item in raw if isinstance(item, str)]
        applicable = [value for value in values if value != "not_applicable"]
        return "unknown" if not values else (
            "failed" if "failed" in values else "degraded" if "degraded" in values
            else "blocked" if "blocked" in values else "passed" if all(value == "passed" for value in values)
            else "passed" if applicable and all(value == "passed" for value in applicable)
            else "not_applicable" if not applicable and "not_applicable" in values else "unknown"
        )
    return mapping.get(raw, "unknown") if isinstance(raw, str) else "unknown"


def _legacy_contract(payload: Mapping[str, Any]) -> str | None:
    """以 producer 的固定 task 與欄位形狀識別未帶版本的舊契約。"""
    task = payload.get("task")
    if (
        task == "baldr-data-update-quick-daily"
        and all(key in payload for key in ("run_id", "started_at", "completed_at", "status"))
    ):
        return "legacy:baldr-data-update-quick-daily"
    if (
        task == "baldr-data-freshness-check-daily"
        and all(key in payload for key in ("checked_at", "source_statuses", "status_vocabulary"))
        and payload.get("status_vocabulary")
        == ["current", "expected_wait", "stale", "failed", "partial", "not_applicable", "unknown"]
    ):
        return "legacy:baldr-data-freshness-check-daily"
    if (
        task == "baldr-evidence-pipeline-dry-run-daily"
        and payload.get("dry_run") is True
        and payload.get("confirm") is False
        and isinstance(payload.get("exit_code"), int)
        and not isinstance(payload.get("exit_code"), bool)
        and isinstance(payload.get("pipeline_execution_started"), bool)
        and isinstance(payload.get("status"), str)
    ):
        return "legacy:baldr-evidence-pipeline-dry-run-daily"
    return None


def _track(payload: Mapping[str, Any], name: str) -> dict[str, Any]:
    keys = _TRACK_STATUS_KEYS[name]
    raw = next((payload[key] for key in keys if isinstance(payload.get(key), str)), None)
    missing = [] if raw is not None else [f"{name}.status"]
    if name == "source_freshness" and isinstance(payload.get("source_statuses"), list):
        values = [
            item.get("freshness_status")
            for item in payload["source_statuses"]
            if isinstance(item, Mapping) and isinstance(item.get("freshness_status"), str)
        ]
        if values:
            raw = values
            missing = []
    return {
        "raw_status": raw,
        "semantic": _track_semantic(name, raw),
        "blockers": payload.get("blockers") if isinstance(payload.get("blockers"), list) else [],
        "missing_fields": missing,
    }


def adapt_receipt(payload: object) -> dict[str, Any]:
    """將單筆 JSON 收據正規化；不讀檔、不推導身份或補造時間。"""
    source: Mapping[str, Any] = payload if isinstance(payload, Mapping) else {}
    raw_schema = source.get("schema_version")
    schema = raw_schema if isinstance(raw_schema, str) and raw_schema in _SCHEMAS else None
    legacy = _legacy_contract(source) if "schema_version" not in source else None
    kind = _SCHEMAS.get(schema) if schema is not None else ("producer" if legacy else None)
    formal_terminal_valid = (
        schema == "formal-input-producer-terminal-receipt.v1"
        and _formal_terminal_valid(source)
    )
    if (
        schema == "formal-input-producer-terminal-receipt.v1"
        and not formal_terminal_valid
    ):
        kind = None
    supported = kind is not None

    status_payload = source.get("status_payload") if formal_terminal_valid else None
    status = (
        status_payload.get("status")
        if isinstance(status_payload, Mapping)
        else source.get("overall_status")
        if schema == "scheduled-official-market-status-bundle.v1"
        else source.get("status")
    )
    if not isinstance(status, str) and schema == "scheduled-weekly-collection-controller-result.v1":
        status = source.get("status")
    if kind == "pointer":
        status = source.get("overall_status") if isinstance(source.get("overall_status"), str) else source.get("status")

    run_id = source.get("run_id")
    if formal_terminal_valid:
        run_id = source.get("run_id")
    elif schema == "scheduled-official-market-status-bundle.v1":
        run_id = source.get("wrapper_run_id")
    elif schema == "daily-recommendation-learning-terminal-receipt.v1":
        run_id = source.get("run_id")
    elif schema == "scheduled-weekly-collection-controller-receipt.v2":
        run_id = source.get("run_id")

    started_at = source.get("started_at")
    if formal_terminal_valid:
        started_at = source.get("started_at")
    elif schema == "decision-evidence-capture.v1":
        started_at = source.get("run_started_at")
    elif schema == "scheduled-weekly-collection-controller-receipt.v2":
        started_at = source.get("started_at_utc")
    completed_at = source.get("completed_at")
    if schema == "scheduled-official-market-status-bundle.v1":
        completed_at = source.get("finished_at")
    elif schema == "decision-evidence-capture.v1":
        completed_at = source.get("run_completed_at", source.get("completed_at"))
    elif schema == "scheduled-weekly-collection-controller-receipt.v2":
        completed_at = source.get("completed_at_utc")

    blockers = (
        source.get("blockers")
        if isinstance(source.get("blockers"), list)
        else []
    )
    missing_fields: list[str] = []
    if not supported:
        missing_fields.append(
            "formal_terminal_contract_invalid"
            if schema == "formal-input-producer-terminal-receipt.v1"
            else "schema_version_or_exact_legacy_contract"
        )
    if supported and kind == "producer":
        if not isinstance(status, str):
            missing_fields.append("status")
        if not isinstance(run_id, str) or not run_id:
            missing_fields.append("run_id")

    tracks = {name: _track(source, name) for name in _TRACK_STATUS_KEYS}
    if kind == "pointer":
        tracks["observability"] = {
            "raw_status": "pointer_only",
            "semantic": "pointer_only",
            "blockers": [],
            "missing_fields": [],
        }
    if kind == "launcher":
        tracks["observability"] = {
            "raw_status": status,
            "semantic": "launcher_only",
            "blockers": [],
            "missing_fields": [],
        }
    producer_semantic = (
        "pointer_only" if kind == "pointer"
        else "launcher_only" if kind == "launcher"
        else "unknown" if not supported
        else _semantic(status)
    )
    if legacy == "legacy:baldr-evidence-pipeline-dry-run-daily" and (
        not isinstance(run_id, str) or not isinstance(started_at, str)
    ):
        producer_semantic = "unknown"
        if not isinstance(run_id, str) or not run_id:
            if "run_id" not in missing_fields:
                missing_fields.append("run_id")
        if not isinstance(started_at, str) or not started_at:
            if "started_at" not in missing_fields:
                missing_fields.append("started_at")

    return {
        "supported": supported,
        "kind": kind,
        "schema": schema,
        "producer_task": source.get("task"),
        "run_id": run_id if isinstance(run_id, str) else None,
        "started_at": started_at if isinstance(started_at, str) else None,
        "completed_at": completed_at if isinstance(completed_at, str) else None,
        "producer_status": status if isinstance(status, str) else None,
        "producer_status_semantic": producer_semantic,
        "failure_code": source.get("failure_code") if formal_terminal_valid else None,
        "blockers": blockers,
        "missing_fields": missing_fields,
        **tracks,
    }
