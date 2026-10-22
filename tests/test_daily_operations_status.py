"""每日營運唯讀分類器的合成契約測試。"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from app_module.daily_operations_status import (
    ObservationError,
    SCHEMA,
    TRACK_KEYS,
    classify_component,
    parse_aware_timestamp,
    validate_manifest,
)
from app_module.daily_operations_receipts import adapt_receipt
from scripts.audit_daily_operations import (
    AuditInputError,
    _read_receipt,
    _strict_json,
    audit,
)


NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)


def _row(**changes: object) -> dict[str, object]:
    row: dict[str, object] = {
        "id": "synthetic-daily-job",
        "enabled": True,
        "expected_enabled": True,
        "scheduler_result": 0,
        "scheduler_last_run_at": "2026-10-21T11:59:00+00:00",
        "producer_status": "passed",
        "producer_run_id": "run-1",
        "receipt_ref": {"path": "run.json", "sha256": "a" * 64},
        "receipt_identity_verified": True,
        "blockers": [],
        "stale": False,
        "writes_formal_data": False,
        "downstream_ids": ["synthetic-child"],
    }
    row.update(changes)
    return row


def _receipt(**changes: object) -> dict[str, object]:
    receipt: dict[str, object] = {
        "supported": True,
        "kind": "producer",
        "schema": "legacy:generic.v1",
        "run_id": "run-1",
        "started_at": "2026-10-21T11:59:00+00:00",
        "completed_at": "2026-10-21T11:59:30+00:00",
        "producer_status": "completed",
        "blockers": [],
        "errors": [],
        "warnings": [],
        "blocker": [],
        "source_freshness": {"raw_status": None, "semantic": "unknown"},
        "financial_qualification": {"raw_status": None, "semantic": "unknown"},
        "dependency_readiness": {"raw_status": None, "semantic": "unknown"},
        "observability": {"raw_status": None, "semantic": "unknown"},
    }
    receipt.update(changes)
    return receipt


def _write_receipt(tmp_path: Path, payload: dict[str, object]) -> dict[str, str]:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    (tmp_path / "run.json").write_bytes(raw)
    return {"path": "run.json", "sha256": hashlib.sha256(raw).hexdigest()}


def _manifest(row: dict[str, object]) -> dict[str, object]:
    return {"schema": SCHEMA, "observed_at": "2026-10-21T12:00:00+00:00", "components": [row]}


def test_same_run_verified_receipt_is_healthy_but_manifest_claim_is_ignored() -> None:
    result = classify_component(_row(), receipt=_receipt(), observed_at=NOW)
    assert result["status"] == "HEALTHY"
    assert result["tracks"]["application_receipt"]["status"] == "HEALTHY"
    assert result["tracks"]["windows_execution"]["status"] == "HEALTHY"
    assert result["tracks"]["financial_qualification"]["status"] == "UNKNOWN"
    assert set(result["tracks"]) == set(TRACK_KEYS)
    assert result["downstream_hold"] is False


def test_wrong_run_failed_receipt_is_not_attributed_but_windows_failure_remains() -> None:
    result = classify_component(
        _row(scheduler_result=1),
        receipt=_receipt(run_id="another-run", producer_status="failed"),
        observed_at=NOW,
    )
    assert result["status"] == "EXECUTION_FAILED"
    assert result["tracks"]["windows_execution"]["status"] == "EXECUTION_FAILED"
    assert result["tracks"]["application_receipt"]["status"] == "UNKNOWN"
    assert "unverified_failure_not_attributed_to_this_run" in result["tracks"]["application_receipt"]["reason"]


def test_explicit_different_producer_task_fails_identity_even_with_same_run_clocks() -> None:
    receipt = adapt_receipt(
        {
            "schema_version": "scheduled-official-market-status-bundle.v1",
            "task": "another-scheduled-producer",
            "overall_status": "succeeded",
            "wrapper_run_id": "run-1",
            "started_at": "2026-10-21T11:59:00+00:00",
            "finished_at": "2026-10-21T11:59:30+00:00",
        }
    )
    result = classify_component(_row(), receipt=receipt, observed_at=NOW)
    assert result["tracks"]["application_receipt"]["status"] == "UNKNOWN"
    assert "receipt_task_mismatch" in result["tracks"]["application_receipt"]["reason"]
    assert "receipt_task_mismatch" in result["tracks"]["observability"]["reason"]


def test_scheduler_zero_and_positive_financial_claim_do_not_grant_qualification() -> None:
    result = classify_component(
        _row(),
        receipt=_receipt(financial_qualification={"raw_status": "qualified", "semantic": "qualified"}),
        observed_at=NOW,
    )
    assert result["tracks"]["windows_execution"]["status"] == "HEALTHY"
    assert result["tracks"]["application_receipt"]["status"] == "HEALTHY"
    assert result["tracks"]["financial_qualification"]["status"] == "UNKNOWN"
    assert "positive_claim_lacks_external_accepted_evidence" in result["tracks"]["financial_qualification"]["reason"]


def test_explicit_financial_disqualification_is_blocked_source() -> None:
    result = classify_component(
        _row(),
        receipt=_receipt(financial_qualification={"raw_status": "not_qualified", "semantic": "not_qualified"}),
        observed_at=NOW,
    )
    assert result["tracks"]["financial_qualification"]["status"] == "BLOCKED_SOURCE"


def test_same_run_blocked_pending_and_failed_keep_distinct_application_states() -> None:
    blocked = classify_component(
        _row(), receipt=_receipt(producer_status="blocked", blockers=["source_revision_missing"]), observed_at=NOW
    )
    pending = classify_component(_row(), receipt=_receipt(producer_status="pending"), observed_at=NOW)
    failed = classify_component(_row(), receipt=_receipt(producer_status="failed"), observed_at=NOW)
    assert blocked["tracks"]["application_receipt"]["status"] == "BLOCKED_SOURCE"
    assert pending["tracks"]["application_receipt"]["status"] == "DEGRADED"
    assert failed["tracks"]["application_receipt"]["status"] == "EXECUTION_FAILED"


def test_official_market_bundle_uses_wrapper_identity_and_finished_time(tmp_path: Path) -> None:
    payload: dict[str, object] = {
        "schema_version": "scheduled-official-market-status-bundle.v1",
        "wrapper_run_id": "run-1",
        "started_at": "2026-10-21T11:59:00+00:00",
        "finished_at": "2026-10-21T11:59:45+00:00",
        "overall_status": "succeeded",
        "blockers": [],
        "source_status": "current",
        "financial_qualification_status": "not_assessed",
        "dependency_status": "ready",
    }
    ref = _write_receipt(tmp_path, payload)
    receipt = _read_receipt(tmp_path, ref)
    result = classify_component(_row(receipt_ref=ref), receipt=receipt, observed_at=NOW)
    assert receipt["kind"] == "producer"
    assert receipt["run_id"] == "run-1"
    assert receipt["completed_at"] == "2026-10-21T11:59:45+00:00"
    assert result["status"] == "HEALTHY"
    assert result["tracks"]["source_freshness"]["status"] == "HEALTHY"
    assert result["tracks"]["dependency_readiness"]["status"] == "HEALTHY"
    assert result["tracks"]["observability"]["status"] == "HEALTHY"
    assert result["tracks"]["financial_qualification"]["status"] == "UNKNOWN"


@pytest.mark.parametrize(
    "schema",
    ["scheduled-official-market-events-wrapper-pointer.v1", "scheduled-hidden-launch.v1"],
)
def test_pointer_and_launcher_receipts_never_become_application_success(tmp_path: Path, schema: str) -> None:
    payload = {
        "schema_version": schema,
        "run_id": "run-1",
        "started_at": "2026-10-21T11:59:00+00:00",
        "completed_at": "2026-10-21T11:59:30+00:00",
        "status": "completed",
        "overall_status": "completed",
    }
    ref = _write_receipt(tmp_path, payload)
    receipt = _read_receipt(tmp_path, ref)
    result = classify_component(_row(receipt_ref=ref), receipt=receipt, observed_at=NOW)
    assert receipt["kind"] in {"pointer", "launcher"}
    assert result["tracks"]["application_receipt"]["status"] == "UNKNOWN"
    assert result["status"] == "UNKNOWN"


def test_legacy_freshness_without_run_clock_stays_unknown(tmp_path: Path) -> None:
    payload: dict[str, object] = {
        "task": "baldr-data-freshness-check-daily",
        "checked_at": "2026-10-21T11:59:30+00:00",
        "source_statuses": [{"freshness_status": "current"}],
        "status_vocabulary": ["current", "expected_wait", "stale", "failed", "partial", "not_applicable", "unknown"],
        "status": "passed",
    }
    ref = _write_receipt(tmp_path, payload)
    receipt = _read_receipt(tmp_path, ref)
    result = classify_component(_row(receipt_ref=ref), receipt=receipt, observed_at=NOW)
    assert receipt["schema"] == "legacy:baldr-data-freshness-check-daily"
    assert result["tracks"]["application_receipt"]["status"] == "UNKNOWN"
    assert "receipt_run_id_missing" in result["tracks"]["application_receipt"]["reason"]


def test_unknown_explicit_schema_does_not_fallback_to_generic_legacy(tmp_path: Path) -> None:
    payload = {
        "schema_version": "future-unsupported.v9",
        "run_id": "run-1",
        "started_at": "2026-10-21T11:59:00+00:00",
        "completed_at": "2026-10-21T11:59:30+00:00",
        "status": "completed",
    }
    ref = _write_receipt(tmp_path, payload)
    receipt = _read_receipt(tmp_path, ref)
    result = classify_component(_row(receipt_ref=ref), receipt=receipt, observed_at=NOW)
    assert receipt["supported"] is False
    assert result["tracks"]["application_receipt"]["status"] == "UNKNOWN"


def test_generic_legacy_requires_run_started_and_status_types(tmp_path: Path) -> None:
    payload = {"run_id": "run-1", "started_at": "2026-10-21T11:59:00+00:00", "status": "completed"}
    ref = _write_receipt(tmp_path, payload)
    receipt = _read_receipt(tmp_path, ref)
    assert receipt["schema"] == "legacy:generic.v1"
    assert classify_component(_row(receipt_ref=ref), receipt=receipt, observed_at=NOW)["status"] == "UNKNOWN"


def test_bad_receipt_sha_stays_unverified_and_does_not_hide_scheduler_failure(tmp_path: Path) -> None:
    ref = _write_receipt(tmp_path, {"run_id": "run-1", "started_at": "2026-10-21T11:59:00+00:00", "status": "failed"})
    ref["sha256"] = "0" * 64
    with pytest.raises(AuditInputError, match="receipt_sha256_mismatch"):
        _read_receipt(tmp_path, ref)
    result = classify_component(
        _row(scheduler_result=1), receipt=None, receipt_error="receipt_sha256_mismatch", observed_at=NOW
    )
    assert result["status"] == "EXECUTION_FAILED"
    assert result["tracks"]["application_receipt"]["status"] == "UNKNOWN"


def test_receipt_error_invalidates_otherwise_valid_same_run_receipt() -> None:
    result = classify_component(
        _row(), receipt=_receipt(), receipt_error="receipt_sha256_mismatch", observed_at=NOW
    )
    for name in (
        "application_receipt",
        "source_freshness",
        "financial_qualification",
        "dependency_readiness",
        "observability",
    ):
        assert result["tracks"][name]["status"] != "HEALTHY"
    assert "receipt_unverified:receipt_sha256_mismatch" in result["tracks"]["application_receipt"]["reason"]
    assert "receipt_unverified:receipt_sha256_mismatch" in result["tracks"]["observability"]["reason"]
    assert "manifest_identity_claim_not_trusted" in result["tracks"]["observability"]["reason"]


def test_receipt_error_and_warning_fields_are_bounded(tmp_path: Path) -> None:
    payload = {
        "run_id": "run-1",
        "started_at": "2026-10-21T11:59:00+00:00",
        "completed_at": "2026-10-21T11:59:30+00:00",
        "status": "completed",
        "errors": ["safe diagnostic"] * 129,
    }
    ref = _write_receipt(tmp_path, payload)
    with pytest.raises(AuditInputError, match="receipt_errors_invalid"):
        _read_receipt(tmp_path, ref)


def test_known_root_causes_are_narrow_and_expected_disabled_is_not_alerted() -> None:
    path_mismatch = classify_component(
        _row(), receipt=_receipt(producer_status="failed", errors=["daily-price revision receipt database path mismatch: D to F"]),
        observed_at=NOW,
    )
    config_expired = classify_component(
        _row(), receipt=_receipt(producer_status="runtime_config_expired:2026-09-09:2026-10-22"), observed_at=NOW
    )
    embedded_config_text = classify_component(
        _row(), receipt=_receipt(producer_status="prefix-runtime_config_expired:2026-09-09"), observed_at=NOW
    )
    disabled = classify_component(
        _row(enabled=False, expected_enabled=False, receipt_ref=None), observed_at=NOW
    )
    unknown = classify_component(_row(), receipt=_receipt(errors=["an unfamiliar condition"]), observed_at=NOW)
    assert path_mismatch["root_cause"] == "PATH_OR_CUSTODY_MISMATCH"
    assert config_expired["root_cause"] == "CONFIG_DEFECT"
    assert embedded_config_text["root_cause"] == "UNKNOWN"
    assert disabled["root_cause"] == "EXPECTED_FAIL_CLOSED"
    assert disabled["alert_recommended"] is False
    assert unknown["root_cause"] == "UNKNOWN"


def test_same_run_tracks_and_output_guidance_are_read_only_and_hold_downstream() -> None:
    result = classify_component(
        _row(writes_formal_data=True),
        receipt=_receipt(
            producer_status="blocked",
            blockers=["source_not_available"],
            source_freshness={"raw_status": "stale", "semantic": "degraded"},
            dependency_readiness={"raw_status": "blocked", "semantic": "blocked"},
            observability={"raw_status": "same_day_status_only", "semantic": "degraded"},
        ),
        observed_at=NOW,
    )
    assert result["status"] == "BLOCKED_SOURCE"
    assert result["tracks"]["source_freshness"]["status"] == "STALE"
    assert result["tracks"]["dependency_readiness"]["status"] == "BLOCKED_SOURCE"
    assert result["tracks"]["observability"]["status"] == "HEALTHY"
    assert result["tracks"]["observability"]["reason"] == ["exact_identity_hash_clock_verified"]
    assert result["safe_retry"] is False
    assert result["auto_action"] == "none_read_only_audit"
    assert result["downstream_hold"] is True
    assert result["downstream_ids"] == ["synthetic-child"]


def test_identity_requires_completion_order_and_scheduler_within_five_minutes() -> None:
    for changes, expected_reason in (
        ({"completed_at": None}, "receipt_completed_at_missing_or_invalid"),
        ({"started_at": "2026-10-21T11:59:40+00:00", "completed_at": "2026-10-21T11:59:30+00:00"}, "receipt_completed_before_started"),
        ({"completed_at": "2026-10-21T12:00:01+00:00"}, "receipt_completed_at_future"),
        ({"started_at": "2026-10-21T11:50:00+00:00"}, "receipt_scheduler_time_mismatch"),
    ):
        result = classify_component(_row(), receipt=_receipt(**changes), observed_at=NOW)
        assert result["tracks"]["application_receipt"]["status"] == "UNKNOWN"
        assert expected_reason in result["tracks"]["application_receipt"]["reason"]


def test_expected_disabled_is_only_component_degradation_and_all_rows_hold_when_not_healthy() -> None:
    result = classify_component(
        _row(
            id="baldr-ml-direct-chain-maintainer",
            enabled=False,
            expected_enabled=False,
            receipt_ref=None,
        ),
        observed_at=NOW,
    )
    assert result["status"] == "DEGRADED"
    assert result["tracks"]["windows_execution"]["reason"] == ["expected_disabled"]
    assert result["alert_recommended"] is False
    assert result["downstream_hold"] is True
    assert result["safe_retry"] is False


def test_strict_json_rejects_duplicate_keys_and_non_finite_values() -> None:
    with pytest.raises(AuditInputError, match="json_duplicate_key"):
        _strict_json(b'{"status":"passed","status":"failed"}')
    with pytest.raises(AuditInputError, match="json_non_finite"):
        _strict_json(b'{"ratio":NaN}')


def test_manifest_caps_duplicates_and_requires_aware_times() -> None:
    base = _manifest(_row())
    validated = validate_manifest(base)
    assert validated["_observed_at_utc"] == NOW
    with pytest.raises(ObservationError, match="duplicate"):
        validate_manifest(_manifest(_row()) | {"components": [_row(), _row()]})
    with pytest.raises(ObservationError, match="timezone_required"):
        parse_aware_timestamp("2026-10-21T12:00:00", "observed_at")
    with pytest.raises(ObservationError, match="invalid_count"):
        validate_manifest(_manifest(_row()) | {"components": [_row(id=f"job-{i}") for i in range(129)]})


def test_manifest_external_sha_is_required_before_any_receipt_read(tmp_path: Path) -> None:
    manifest = _manifest(_row(receipt_ref=None))
    manifest_path = tmp_path / "manifest.json"
    raw = json.dumps(manifest, separators=(",", ":")).encode("utf-8")
    manifest_path.write_bytes(raw)
    with pytest.raises(AuditInputError, match="snapshot_sha256_mismatch"):
        audit(manifest_path, "0" * 64, tmp_path)
