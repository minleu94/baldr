import json
import os
from datetime import datetime, timezone
from pathlib import Path

from app_module.runtime_services.scheduled_operations_service import (
    ScheduledOperationsStatusService,
)
from tests.decision_capture_status_fixture import (
    create_decision_capture_fixture,
    create_no_child_skipped_fixture,
)


NOW = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)


def _write_status(root: Path, job_id: str, payload: dict[str, object]) -> Path:
    path = root / job_id / "latest_status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    timestamp = NOW.timestamp()
    os.utime(path, (timestamp, timestamp))
    return path


def _expected_evidence_payload() -> dict[str, object]:
    return {
        "status": "degraded",
        "checked_at": "2026-08-06T11:55:00+00:00",
        "natural_maturity_only": True,
        "manual_action_required": False,
        "pipeline_summary_available": True,
        "freshness_status": "passed",
        "pipeline_errors_count": 0,
        "pipeline_actionable_warning_count": 0,
        "pipeline_blocking_gaps": [],
        "source_coverage_blocking_gaps": [],
        "pipeline_diagnostic_codes": [],
    }


def _warning_update_payload() -> dict[str, object]:
    return {
        "status": "passed_with_warnings",
        "run_id": "update-run-1",
        "checked_at": NOW.isoformat(),
        "end_date": "2026-08-06",
        "warnings": ["TPEX daily prices were already current"],
        "errors": [],
        "steps": [
            {"name": "download", "status": "passed"},
            {"name": "update_tpex_daily_prices", "status": "warning"},
        ],
    }


def _producer_skip(name: str, **result: object) -> dict[str, object]:
    return {"name": name, "status": "skipped", "result": result}


def _warning_update_with_producer_skips() -> dict[str, object]:
    payload = _warning_update_payload()
    payload["steps"].extend(
        [
            _producer_skip(
                "update_broker_branch", success=True, skipped=True,
                optional_source=True, reason="explicit_skip_broker_branch",
            ),
            _producer_skip(
                "sync_broker_branch_to_sqlite", success=True, skipped=True,
                optional_source=True, reason="broker_branch_refresh_skipped",
            ),
            _producer_skip(
                "update_phase3c_candidate_sources", success=True, skipped=True,
                candidate_only=True, reason="operator_requested_candidate_update_skip",
            ),
            _producer_skip(
                "capture_tdcc_current_ownership", success=True, skipped=True,
                reason="phase3c_tdcc_result_not_verified",
                phase3c_step_status="skipped", network_requested=False,
                writes_performed=False,
            ),
            _producer_skip(
                "calculate_technical_indicators", success=True, skipped=True,
                skip_reason="technical_indicators_current",
                technical_computation={}, technical_computation_reuse={},
                technical_reuse_validation={"status": "reused"},
            ),
        ]
    )
    return payload


def test_snapshot_distinguishes_operational_core_from_guarded_safety_boundaries(tmp_path):
    output_root = tmp_path / "output"
    root = output_root / "scheduled"
    for job_id in (
        "data_update_quick",
        "data_freshness",
        "recommendation_snapshot",
        "paper_portfolio_daily",
    ):
        _write_status(root, job_id, {"status": "passed", "checked_at": NOW.isoformat()})
    create_decision_capture_fixture(output_root, producer_now=NOW)
    _write_status(root, "evidence_pipeline_dry_run", _expected_evidence_payload())
    _write_status(
        root,
        "ml_allocation_copilot",
        {"status": "passed_rule_only", "decision_at": "2026-08-07T08:30:00+08:00"},
    )
    _write_status(root, "ml_promotion_evidence", {"status": "blocked"})
    _write_status(
        root,
        "ml_direct_chain_maintenance",
        {"status": "blocked_insufficient_storage"},
    )

    snapshot = ScheduledOperationsStatusService(root, now_provider=lambda: NOW).get_snapshot()
    operations = {operation.job_id: operation for operation in snapshot.operations}

    assert snapshot.overall_state == "operational"
    assert snapshot.core_ready_count == 6
    assert operations["evidence_pipeline_dry_run"].state == "guarded"
    assert operations["ml_allocation_copilot"].state == "guarded"
    assert operations["ml_allocation_copilot"].observed_at_source == "file_mtime"
    assert operations["ml_allocation_copilot"].updated_at == NOW
    assert operations["ml_promotion_evidence"].state == "guarded"
    assert operations["ml_direct_chain_maintenance"].label == "ML Direct/OOC 維護"
    assert operations["ml_direct_chain_maintenance"].state == "attention"
    assert operations["ml_direct_chain_maintenance"].diagnostic == (
        "direct_chain_storage_preflight_blocked"
    )


def test_warning_success_is_guarded_and_counts_as_ready_core_operation(tmp_path):
    output_root = tmp_path / "output"
    root = output_root / "scheduled"
    for job_id in (
        "data_freshness",
        "recommendation_snapshot",
        "evidence_pipeline_dry_run",
        "paper_portfolio_daily",
    ):
        _write_status(root, job_id, {"status": "passed", "checked_at": NOW.isoformat()})
    create_decision_capture_fixture(output_root, producer_now=NOW)
    _write_status(root, "data_update_quick", _warning_update_payload())

    snapshot = ScheduledOperationsStatusService(root, now_provider=lambda: NOW).get_snapshot()
    operation = next(item for item in snapshot.operations if item.job_id == "data_update_quick")

    assert snapshot.overall_state == "operational"
    assert snapshot.core_ready_count == 6
    assert operation.raw_status == "passed_with_warnings"
    assert operation.state == "guarded"
    assert operation.diagnostic == "scheduled_job_completed_with_warnings"


def test_bare_passed_decision_capture_is_not_an_operational_core_job(tmp_path):
    root = tmp_path / "scheduled"
    _write_status(
        root,
        "decision_evidence_capture",
        {"status": "passed", "checked_at": NOW.isoformat()},
    )

    snapshot = ScheduledOperationsStatusService(root, now_provider=lambda: NOW).get_snapshot()
    operation = next(
        item for item in snapshot.operations if item.job_id == "decision_evidence_capture"
    )

    assert operation.raw_status == "passed"
    assert operation.state == "attention"
    assert operation.capture is not None
    assert operation.capture.read_state != "verified"


def test_verified_no_child_calendar_skip_is_not_operational_core_success(
    tmp_path,
    monkeypatch,
):
    output_root = tmp_path / "output"
    fixture = create_no_child_skipped_fixture(
        output_root,
        producer_now=NOW,
        monkeypatch=monkeypatch,
    )

    snapshot = ScheduledOperationsStatusService(
        output_root / "scheduled",
        now_provider=lambda: NOW,
    ).get_snapshot()
    operation = next(
        item for item in snapshot.operations if item.job_id == "decision_evidence_capture"
    )

    assert fixture.status_path.exists()
    assert operation.capture is not None
    assert operation.capture.read_state == "verified"
    assert operation.capture.raw_status == "skipped_non_trading_day"
    assert operation.capture.snapshot_execution_status == "not_started"
    assert operation.state == "attention"
    assert operation.diagnostic == "unexpected_core_status:skipped_non_trading_day"
    assert snapshot.overall_state == "attention"


def test_warning_success_accepts_only_named_producer_skips(tmp_path):
    root = tmp_path / "scheduled"
    _write_status(root, "data_update_quick", _warning_update_with_producer_skips())

    snapshot = ScheduledOperationsStatusService(root, now_provider=lambda: NOW).get_snapshot()
    operation = next(item for item in snapshot.operations if item.job_id == "data_update_quick")

    assert operation.raw_status == "passed_with_warnings"
    assert operation.state == "guarded"
    assert operation.diagnostic == "scheduled_job_completed_with_warnings"


def test_warning_success_rejects_uncontracted_or_malformed_skips(tmp_path):
    unknown_skip = _warning_update_payload()
    unknown_skip["steps"].append(
        {
            "name": "unknown_optional_step",
            "status": "skipped",
            "result": {"success": True, "skipped": True, "optional_source": True},
        }
    )
    wrong_broker_reason = _warning_update_with_producer_skips()
    wrong_broker_reason["steps"][2]["result"]["reason"] = "other_skip_reason"
    unpaired_broker_skip = _warning_update_with_producer_skips()
    unpaired_broker_skip["steps"].remove(
        next(
            step
            for step in unpaired_broker_skip["steps"]
            if step["name"] == "sync_broker_branch_to_sqlite"
        )
    )
    unmarked_candidate_skip = _warning_update_payload()
    unmarked_candidate_skip["steps"].append(
        {
            "name": "update_phase3c_candidate_sources",
            "status": "skipped",
            "result": {
                "success": True,
                "skipped": True,
                "reason": "operator_requested_candidate_update_skip",
            },
        }
    )
    unsafe_tdcc_skip = _warning_update_with_producer_skips()
    unsafe_tdcc_skip["steps"][5]["result"]["network_requested"] = True
    invalid_technical_reuse = _warning_update_with_producer_skips()
    invalid_technical_reuse["steps"][6]["result"]["technical_reuse_validation"][
        "status"
    ] = "not_found"

    for name, payload in (
        ("unknown", unknown_skip),
        ("wrong-broker-reason", wrong_broker_reason),
        ("unpaired-broker", unpaired_broker_skip),
        ("unmarked-candidate", unmarked_candidate_skip),
        ("unsafe-tdcc", unsafe_tdcc_skip),
        ("invalid-technical-reuse", invalid_technical_reuse),
    ):
        root = tmp_path / name
        _write_status(root, "data_update_quick", payload)
        snapshot = ScheduledOperationsStatusService(root, now_provider=lambda: NOW).get_snapshot()
        operation = next(
            item for item in snapshot.operations if item.job_id == "data_update_quick"
        )
        assert operation.state == "attention"
        assert operation.diagnostic == "invalid_warning_success_artifact"


def test_malformed_warning_success_remains_attention(tmp_path):
    with_errors = _warning_update_payload()
    with_errors["errors"] = ["a scheduled update step failed"]
    without_warning = _warning_update_payload()
    without_warning["warnings"] = []
    without_identity = _warning_update_payload()
    without_identity.pop("run_id")
    without_date = _warning_update_payload()
    without_date.pop("end_date")
    with_unknown_step = _warning_update_payload()
    with_unknown_step["steps"][1]["status"] = "pending"

    for name, payload in (
        ("with-errors", with_errors),
        ("without-warning", without_warning),
        ("without-identity", without_identity),
        ("without-date", without_date),
        ("unknown-step", with_unknown_step),
    ):
        root = tmp_path / name
        _write_status(root, "data_update_quick", payload)

        snapshot = ScheduledOperationsStatusService(root, now_provider=lambda: NOW).get_snapshot()
        operation = next(
            item for item in snapshot.operations if item.job_id == "data_update_quick"
        )

        assert snapshot.overall_state == "attention"
        assert operation.state == "attention"
        assert operation.diagnostic == "invalid_warning_success_artifact"


def test_unknown_core_terminal_status_remains_attention(tmp_path):
    root = tmp_path / "scheduled"
    _write_status(root, "data_update_quick", {"status": "mystery"})

    snapshot = ScheduledOperationsStatusService(root, now_provider=lambda: NOW).get_snapshot()
    operation = next(item for item in snapshot.operations if item.job_id == "data_update_quick")

    assert operation.state == "attention"
    assert operation.diagnostic == "unexpected_core_status:mystery"


def test_evidence_degraded_fails_closed_without_complete_natural_maturity_proof(tmp_path):
    root = tmp_path / "scheduled"
    payload = _expected_evidence_payload()
    payload.pop("freshness_status")
    _write_status(root, "evidence_pipeline_dry_run", payload)

    snapshot = ScheduledOperationsStatusService(root, now_provider=lambda: NOW).get_snapshot()
    operation = next(
        item for item in snapshot.operations if item.job_id == "evidence_pipeline_dry_run"
    )

    assert operation.state == "attention"
    assert operation.diagnostic == "evidence_pipeline_degradation_requires_review"
    assert snapshot.overall_state == "attention"


def test_missing_or_stale_core_status_is_attention_not_success(tmp_path):
    root = tmp_path / "scheduled"
    old_payload = {"status": "passed", "checked_at": "2026-08-01T00:00:00+00:00"}
    _write_status(root, "data_update_quick", old_payload)

    snapshot = ScheduledOperationsStatusService(root, now_provider=lambda: NOW).get_snapshot()
    operations = {operation.job_id: operation for operation in snapshot.operations}

    assert operations["data_update_quick"].state == "attention"
    assert "latest_status_stale" in operations["data_update_quick"].diagnostic
    assert operations["data_freshness"].state == "attention"
    assert operations["data_freshness"].read_state == "missing"
    assert snapshot.overall_state == "attention"


def test_unavailable_snapshot_is_fail_closed_for_all_core_operations(tmp_path):
    snapshot = ScheduledOperationsStatusService(
        tmp_path,
        now_provider=lambda: NOW,
    ).build_unavailable_snapshot(
        "scheduled_operations_read_failed:OSError"
    )

    assert snapshot.overall_state == "attention"
    assert snapshot.observed_at == NOW
    assert snapshot.core_ready_count == 0
    assert snapshot.core_job_count == 6
    assert all(
        operation.state == "attention"
        for operation in snapshot.operations
        if operation.lane == "core"
    )
    assert all(
        operation.read_state == "service_error" for operation in snapshot.operations
    )


def test_future_checked_timestamp_falls_back_to_file_mtime_instead_of_hiding_staleness(tmp_path):
    root = tmp_path / "scheduled"
    _write_status(
        root,
        "data_update_quick",
        {"status": "passed", "checked_at": "2026-08-07T12:00:00+00:00"},
    )

    snapshot = ScheduledOperationsStatusService(root, now_provider=lambda: NOW).get_snapshot()
    operation = next(item for item in snapshot.operations if item.job_id == "data_update_quick")

    assert operation.updated_at == NOW
    assert operation.observed_at_source == "file_mtime"
    assert "future_status_timestamp:checked_at" in operation.diagnostic


def test_known_completed_and_non_trading_day_safety_statuses_are_not_reported_as_failures(
    tmp_path,
):
    root = tmp_path / "scheduled"
    _write_status(
        root,
        "ml_raw_pit_refresh",
        {"status": "completed", "completed_at": NOW.isoformat()},
    )
    _write_status(
        root,
        "ml_allocation_copilot",
        {"status": "skipped_non_trading_day"},
    )

    snapshot = ScheduledOperationsStatusService(root, now_provider=lambda: NOW).get_snapshot()
    operations = {operation.job_id: operation for operation in snapshot.operations}

    assert operations["ml_raw_pit_refresh"].state == "operational"
    assert operations["ml_raw_pit_refresh"].diagnostic == ""
    assert operations["ml_allocation_copilot"].state == "guarded"
    assert operations["ml_allocation_copilot"].diagnostic == "non_trading_day_noop"


def test_failed_safety_job_keeps_specific_failure_diagnostic(tmp_path):
    root = tmp_path / "scheduled"
    _write_status(root, "ml_direct_chain_maintenance", {"status": "failed"})

    snapshot = ScheduledOperationsStatusService(root, now_provider=lambda: NOW).get_snapshot()
    operation = next(
        item for item in snapshot.operations if item.job_id == "ml_direct_chain_maintenance"
    )

    assert operation.state == "attention"
    assert operation.diagnostic == "scheduled_job_failed"


def test_oversized_capture_is_rejected_before_generic_status_read(tmp_path, monkeypatch):
    root = tmp_path / "scheduled"
    path = root / "decision_evidence_capture" / "latest_status.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b" " * (1024 * 1024 + 1))
    original_read_text = Path.read_text

    def forbid_unbounded_capture_read(self, *args, **kwargs):
        if self == path:
            raise AssertionError("決策擷取不得先由通用read_text無界讀入")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", forbid_unbounded_capture_read)
    snapshot = ScheduledOperationsStatusService(root, now_provider=lambda: NOW).get_snapshot()
    operation = next(item for item in snapshot.operations if item.job_id == "decision_evidence_capture")

    assert operation.state == "attention"
    assert operation.read_state == "unverified"
    assert operation.capture is not None
    assert operation.capture.diagnostic == "decision_capture_file_unavailable"
