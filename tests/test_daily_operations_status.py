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


def _paper_eod_gate(*, blocker_count: int = 129) -> dict[str, object]:
    return {
        "schema_version": "paper-execution-dependency-gate.v1",
        "status": "blocked",
        "ready": False,
        "attempt": 1,
        "target_date": "2026-10-21",
        "observed_at": "2026-10-21T06:00:02-07:00",
        "source_db_written": False,
        "source_files_written": False,
        "blockers": ["source_not_current"] * blocker_count,
        "freshness_lane": {
            "schema_version": "paper-eod-freshness-lane.v1",
            "status": "blocked",
            "target_date": "2026-10-21",
            "required_sources": {
                "sqlite.daily_prices": {
                    "freshness_status": "stale",
                    "expected_period": "2026-10-21",
                    "actual_period": "2026-10-20",
                }
            },
        },
        "market_observation": {
            "mode": "ro/query_only",
            "ready": False,
            "target_date": "2026-10-21",
            "target_key": "20261021",
        },
    }


def _paper_eod_row(ref: dict[str, str], **changes: object) -> dict[str, object]:
    row = _row(
        id="baldr-paper-execution-eod-replay-daily",
        scheduler_result=2,
        scheduler_last_run_at="2026-10-21T06:00:01-07:00",
        producer_status="blocked",
        producer_run_id=None,
        receipt_ref=ref,
        receipt_identity_verified=False,
        stale=False,
        writes_formal_data=False,
    )
    row.update(changes)
    return row


def _write_paper_eod_gate(
    tmp_path: Path,
    payload: dict[str, object],
    relative: Path = Path("natural_receipts_v2/baldr-paper-execution-eod-replay-daily.json"),
) -> dict[str, str]:
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    target.write_bytes(raw)
    return {"path": relative.as_posix(), "sha256": hashlib.sha256(raw).hexdigest()}


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


def test_large_paper_eod_gate_projects_source_block_only_without_run_id_or_blocker_claim(
    tmp_path: Path,
) -> None:
    ref = _write_paper_eod_gate(tmp_path, _paper_eod_gate(blocker_count=1970))
    receipt = _read_receipt(tmp_path, ref)
    result = classify_component(
        _paper_eod_row(ref),
        receipt=receipt,
        observed_at=datetime(2026, 10, 21, 14, 0, tzinfo=timezone.utc),
    )

    application = result["tracks"]["application_receipt"]
    assert application["status"] == "BLOCKED_SOURCE"
    assert application["raw"]["run_id"] is None
    assert application["raw"]["evidence_kind"] == "scheduler_time_correlated_not_producer_run_id"
    projection = application["raw"]["bounded_gate_projection"]
    assert projection["blocker_count"] == 1970
    assert projection["blockers_validation"] == "not_performed_above_128"
    assert projection["source_schema"] == "paper-execution-dependency-gate.v1"
    assert projection["raw_sha256_verified"] is True
    assert receipt["blockers"] == []
    assert result["tracks"]["financial_qualification"]["status"] == "UNKNOWN"
    assert result["tracks"]["observability"]["status"] == "UNKNOWN"
    assert result["status"] == "EXECUTION_FAILED"


def test_paper_eod_projection_threshold_stays_at_128(tmp_path: Path) -> None:
    ref = _write_paper_eod_gate(tmp_path, _paper_eod_gate(blocker_count=128))
    receipt = _read_receipt(tmp_path, ref)
    assert "_bounded_paper_eod_projection" not in receipt
    result = classify_component(
        _paper_eod_row(ref),
        receipt=receipt,
        observed_at=datetime(2026, 10, 21, 14, 0, tzinfo=timezone.utc),
    )
    assert result["tracks"]["application_receipt"]["status"] == "UNKNOWN"

    first_over_limit = _read_receipt(
        tmp_path,
        _write_paper_eod_gate(tmp_path, _paper_eod_gate(blocker_count=129)),
    )
    assert first_over_limit["_bounded_paper_eod_projection"]["blocker_count"] == 129


@pytest.mark.parametrize(
    "changes",
    [
        {"target_date": "2026-10-20"},
        {"source_db_written": True},
        {"source_files_written": True},
        {"ready": True},
        {"status": "passed"},
        {
            "freshness_lane": {
                "schema_version": "paper-eod-freshness-lane.v1",
                "status": "blocked",
                "target_date": "2026-10-21",
                "required_sources": {
                    "sqlite.daily_prices": {
                        "freshness_status": "current",
                        "expected_period": "2026-10-21",
                        "actual_period": "2026-10-21",
                    }
                },
            }
        },
        {
            "freshness_lane": {
                "schema_version": "paper-eod-freshness-lane.v1",
                "status": "blocked",
                "target_date": "2026-10-21",
                "required_sources": {
                    "sqlite.daily_prices": {
                        "freshness_status": "stale",
                        "expected_period": "2026-10-21",
                        "actual_period": "2026-10-22",
                    }
                },
            }
        },
    ],
)
def test_paper_eod_reader_projection_rejects_unproven_source_or_scope(
    tmp_path: Path, changes: dict[str, object]
) -> None:
    payload = _paper_eod_gate()
    payload.update(changes)
    ref = _write_paper_eod_gate(tmp_path, payload)
    with pytest.raises(AuditInputError, match="receipt_blockers_invalid"):
        _read_receipt(tmp_path, ref)


def test_paper_eod_projection_rejects_wrong_raw_hash(tmp_path: Path) -> None:
    ref = _write_paper_eod_gate(tmp_path, _paper_eod_gate())
    ref["sha256"] = "0" * 64
    with pytest.raises(AuditInputError, match="receipt_sha256_mismatch"):
        _read_receipt(tmp_path, ref)


def test_paper_eod_projection_rejects_stale_scheduler_time_and_wrong_date(
    tmp_path: Path,
) -> None:
    ref = _write_paper_eod_gate(tmp_path, _paper_eod_gate())
    receipt = _read_receipt(tmp_path, ref)
    observed = datetime(2026, 10, 21, 14, 0, tzinfo=timezone.utc)

    stale = classify_component(
        _paper_eod_row(ref, scheduler_last_run_at="2026-10-21T06:05:00-07:00"),
        receipt=receipt,
        observed_at=observed,
    )
    assert stale["tracks"]["application_receipt"]["status"] == "UNKNOWN"

    wrong_date = classify_component(
        _paper_eod_row(ref, scheduler_last_run_at="2026-10-20T06:00:01-07:00"),
        receipt=receipt,
        observed_at=observed,
    )
    assert wrong_date["tracks"]["application_receipt"]["status"] == "UNKNOWN"

    late_payload = _paper_eod_gate()
    late_payload["observed_at"] = "2026-10-21T06:05:02-07:00"
    late_ref = _write_paper_eod_gate(tmp_path, late_payload)
    late_receipt = _read_receipt(tmp_path, late_ref)
    outside_window = classify_component(
        _paper_eod_row(late_ref), receipt=late_receipt, observed_at=observed
    )
    assert outside_window["tracks"]["application_receipt"]["status"] == "UNKNOWN"


def test_paper_eod_projection_never_supplies_or_replaces_producer_run_identity(
    tmp_path: Path,
) -> None:
    ref = _write_paper_eod_gate(tmp_path, _paper_eod_gate())
    receipt = _read_receipt(tmp_path, ref)
    result = classify_component(
        _paper_eod_row(ref, producer_run_id="claimed-run"),
        receipt=receipt,
        observed_at=datetime(2026, 10, 21, 14, 0, tzinfo=timezone.utc),
    )
    assert result["tracks"]["application_receipt"]["status"] == "UNKNOWN"
    assert result["tracks"]["observability"]["status"] == "UNKNOWN"


def test_paper_eod_projection_uses_verified_manifest_relative_path(tmp_path: Path) -> None:
    relative = Path("verified/archive/2026-10-21/paper-gate.json")
    ref = _write_paper_eod_gate(tmp_path, _paper_eod_gate(), relative)
    receipt = _read_receipt(tmp_path, ref)
    observed = datetime(2026, 10, 21, 14, 0, tzinfo=timezone.utc)
    result = classify_component(
        _paper_eod_row(ref), receipt=receipt, observed_at=observed
    )
    assert result["tracks"]["application_receipt"]["status"] == "BLOCKED_SOURCE"

    mismatched = dict(ref)
    mismatched["path"] = "verified/archive/2026-10-21/other.json"
    result = classify_component(
        _paper_eod_row(mismatched), receipt=receipt, observed_at=observed
    )
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


def _paper_retry_terminal_success() -> dict[str, object]:
    started = "2026-10-21T11:59:00Z"
    completed = "2026-10-21T11:59:30Z"
    run_id = "1" * 32
    nested: dict[str, object] = {
        "schema_version": "paper-execution-retry-terminal-status.v1",
        "task": "baldr-paper-execution-eod-replay-daily",
        "run_id": run_id,
        "started_at": started,
        "completed_at": completed,
        "status": "machine_verified_candidate",
        "exit_code": 0,
        "financial_qualification_status": "unknown",
        "dependency_readiness_status": "passed",
        "terminal_blocker_code": None,
        "gate_attempts": [
            {
                "attempt": 1,
                "target_date": "2026-10-21",
                "status": "ready",
                "ready": True,
                "blocker_count": 0,
                "receipt_ref": {"path": "claimed-gate.json", "sha256": "0" * 64},
            }
        ],
        "gate_blocker_count": 0,
        "gate_blockers_validation": "not_copied_or_validated",
    }
    return {
        "schema_version": "paper-execution-retry-terminal-receipt.v1",
        "task": "baldr-paper-execution-eod-replay-daily",
        "run_id": run_id,
        "started_at": started,
        "completed_at": completed,
        "code_version": "sha256:" + "b" * 64,
        "exit_code": 0,
        "failure_code": None,
        "status": "machine_verified_candidate",
        "blockers": [],
        "financial_qualification_status": "unknown",
        "dependency_readiness_status": "passed",
        "status_payload": nested,
    }


def test_paper_terminal_same_run_receipt_sha_yields_observability_not_finance(
    tmp_path: Path,
) -> None:
    receipt_payload = _paper_retry_terminal_success()
    receipt_raw = json.dumps(receipt_payload, separators=(",", ":")).encode("utf-8")
    (tmp_path / "paper-terminal.json").write_bytes(receipt_raw)
    run_id = str(receipt_payload["run_id"])
    row = _row(
        id="baldr-paper-execution-eod-replay-daily",
        scheduler_result=0,
        scheduler_last_run_at="2026-10-21T11:59:01Z",
        producer_status="machine_verified_candidate",
        producer_run_id=run_id,
        receipt_ref={
            "path": "paper-terminal.json",
            "sha256": hashlib.sha256(receipt_raw).hexdigest(),
        },
        receipt_identity_verified=False,
    )
    manifest_raw = json.dumps(_manifest(row), separators=(",", ":")).encode("utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_bytes(manifest_raw)
    report = audit(manifest_path, hashlib.sha256(manifest_raw).hexdigest(), tmp_path)
    component = report["components"][0]
    assert component["status"] == "HEALTHY"
    assert component["tracks"]["observability"]["status"] == "HEALTHY"
    assert component["tracks"]["financial_qualification"]["status"] == "UNKNOWN"
    assert (
        component["tracks"]["application_receipt"]["raw"]["gate_reference_verification"]
        == "shape_only_producer_asserted"
    )

    tampered_row = dict(row)
    tampered_row["receipt_ref"] = {"path": "paper-terminal.json", "sha256": "0" * 64}
    tampered_manifest_raw = json.dumps(
        _manifest(tampered_row), separators=(",", ":")
    ).encode("utf-8")
    manifest_path.write_bytes(tampered_manifest_raw)
    tampered_report = audit(
        manifest_path,
        hashlib.sha256(tampered_manifest_raw).hexdigest(),
        tmp_path,
    )
    tampered = tampered_report["components"][0]
    assert tampered["tracks"]["observability"]["status"] == "UNKNOWN"
    assert "receipt_unverified:receipt_sha256_mismatch" in tampered["tracks"]["observability"]["reason"]
