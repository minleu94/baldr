"""將已知排程收據映射為每日營運狀態的唯讀輸入。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


# 僅接受已核對過的 producer 契約；schema 字串不做前綴或相似度比對。
_SCHEMAS: dict[str, str] = {
    "decision-evidence-capture.v1": "producer",
    "formal-input-daily-producer-receipt.v1": "producer",
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
}

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
    supported = kind is not None

    status = source.get("overall_status") if schema == "scheduled-official-market-status-bundle.v1" else source.get("status")
    if not isinstance(status, str) and schema == "scheduled-weekly-collection-controller-result.v1":
        status = source.get("status")
    if kind == "pointer":
        status = source.get("overall_status") if isinstance(source.get("overall_status"), str) else source.get("status")

    run_id = source.get("run_id")
    if schema == "scheduled-official-market-status-bundle.v1":
        run_id = source.get("wrapper_run_id")
    elif schema == "daily-recommendation-learning-terminal-receipt.v1":
        run_id = source.get("run_id")
    elif schema == "scheduled-weekly-collection-controller-receipt.v2":
        run_id = source.get("run_id")

    started_at = source.get("started_at")
    if schema == "decision-evidence-capture.v1":
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

    blockers = source.get("blockers") if isinstance(source.get("blockers"), list) else []
    missing_fields: list[str] = []
    if not supported:
        missing_fields.append("schema_version_or_exact_legacy_contract")
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
        "blockers": blockers,
        "missing_fields": missing_fields,
        **tracks,
    }
