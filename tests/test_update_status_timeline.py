import json
from datetime import datetime, timezone
from pathlib import Path

from app_module.update_status_timeline import (
    UPDATE_STATUS_TIMELINE_SCHEMA,
    load_data_update_timeline,
)


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _update_payload(*, status: str = "passed", completed_at: str = "2026-08-28T09:00:00+08:00") -> dict:
    return {
        "status": status,
        "run_id": "run-1",
        "started_at": "2026-08-28T08:30:00+08:00",
        "completed_at": completed_at,
        "end_date": "2026-08-28",
        "steps": [
            {"name": "download", "status": "passed", "message": "ok"},
            {"name": "sync", "status": "passed", "message": "ok"},
        ],
    }


def _warning_update_payload() -> dict:
    payload = _update_payload(status="passed_with_warnings")
    payload["warnings"] = ["TPEX daily prices were already current"]
    payload["errors"] = []
    payload["steps"][0]["status"] = "warning"
    payload["steps"][0]["message"] = "TPEX daily prices were already current"
    return payload


def _producer_skip(name: str, **result: object) -> dict[str, object]:
    return {"name": name, "status": "skipped", "result": result}


def _warning_update_with_producer_skips() -> dict:
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


def test_timeline_projects_current_run_and_steps(tmp_path: Path) -> None:
    update = _write(tmp_path / "update.json", _update_payload())
    freshness = _write(
        tmp_path / "freshness.json",
        {"status": "passed", "checked_at": "2026-08-28T09:05:00+08:00"},
    )

    result = load_data_update_timeline(
        update_status_path=update,
        freshness_status_path=freshness,
        now=datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc),
    )

    assert result["schema_version"] == UPDATE_STATUS_TIMELINE_SCHEMA
    assert result["status"] == "current"
    assert result["last_success_at"] == "2026-08-28T09:00:00+08:00"
    assert result["run_id"] == "run-1"
    assert result["step_count"] == 2
    assert result["failed_step_count"] == 0
    assert result["boundary"]["read_only"] is True
    assert result["boundary"]["writes_allowed"] is False


def test_timeline_accepts_warning_success_and_preserves_warning_and_identity(tmp_path: Path) -> None:
    update = _write(tmp_path / "update.json", _warning_update_payload())

    result = load_data_update_timeline(
        update_status_path=update,
        now=datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc),
    )

    assert result["status"] == "partial"
    assert result["last_success_at"] == "2026-08-28T09:00:00+08:00"
    assert result["run_id"] == "run-1"
    assert result["target_date"] == "2026-08-28"
    assert result["artifacts"]["update"]["warning_count"] == 1
    assert result["artifacts"]["update"]["warnings"] == [
        "TPEX daily prices were already current"
    ]
    assert result["steps"][0]["status"] == "warning"
    assert not any("unsupported_status" in item for item in result["diagnostics"])


def test_timeline_accepts_only_named_producer_skips_and_keeps_partial_state(
    tmp_path: Path,
) -> None:
    update = _write(tmp_path / "update.json", _warning_update_with_producer_skips())

    result = load_data_update_timeline(
        update_status_path=update,
        now=datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc),
    )

    assert result["status"] == "partial"
    assert result["last_success_at"] == "2026-08-28T09:00:00+08:00"
    assert result["run_id"] == "run-1"
    assert result["target_date"] == "2026-08-28"
    assert result["artifacts"]["update"]["warning_count"] == 1
    assert {step["status"] for step in result["steps"]} >= {"warning", "skipped"}


def test_timeline_rejects_uncontracted_or_malformed_producer_skips(tmp_path: Path) -> None:
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
        update = _write(tmp_path / f"{name}.json", payload)
        result = load_data_update_timeline(
            update_status_path=update,
            now=datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc),
        )
        assert result["status"] == "invalid"
        assert result["last_success_at"] is None
        assert "update:invalid_warning_success_evidence" in result["diagnostics"]


def test_timeline_preserves_bounded_freshness_observations(tmp_path: Path) -> None:
    update = _write(tmp_path / "update.json", _update_payload())
    freshness = _write(
        tmp_path / "freshness.json",
        {
            "status": "passed",
            "checked_at": "2026-08-28T09:05:00+08:00",
            "checks": {
                "daily_prices_latest_date": "20260828",
                "technical_indicators_latest_date": "20260828",
                "data_update_quick_status": "passed",
                "data_update_quick_checked_date": "2026-08-28",
                "data_update_quick_expected_date": "2026-08-28",
                "daily_prices_age_days": 0,
                "twse_daily_price_file_exists_for_latest_date": True,
            },
        },
    )

    result = load_data_update_timeline(
        update_status_path=update,
        freshness_status_path=freshness,
        now=datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc),
    )

    projection = result["artifacts"]["freshness"]
    assert projection["daily_prices_latest_date"] == "20260828"
    assert projection["technical_indicators_latest_date"] == "20260828"
    assert projection["data_update_quick_status"] == "passed"
    assert projection["daily_prices_age_days"] == 0
    assert projection["twse_daily_price_file_exists_for_latest_date"] is True


def test_timeline_does_not_degrade_when_probe_date_is_after_data_end_date(
    tmp_path: Path,
) -> None:
    """A weekend freshness check date is not the latest trading/data date."""

    update = _write(tmp_path / "update.json", _update_payload())
    freshness = _write(
        tmp_path / "freshness.json",
        {
            "status": "passed",
            "checked_at": "2026-08-30T05:00:00+08:00",
            "checks": {
                "daily_prices_latest_date": "20260828",
                "technical_indicators_latest_date": "20260828",
                "data_update_quick_status": "passed",
                "data_update_quick_checked_date": "2026-08-30",
                "data_update_quick_expected_date": "2026-08-28",
            },
        },
    )

    result = load_data_update_timeline(
        update_status_path=update,
        freshness_status_path=freshness,
        now=datetime(2026, 8, 30, 6, 0, tzinfo=timezone.utc),
    )

    assert result["status"] == "current"
    assert not any("quick_checked_date_mismatch" in item for item in result["diagnostics"])


def test_timeline_flags_probe_date_before_expected_date(tmp_path: Path) -> None:
    update = _write(tmp_path / "update.json", _update_payload())
    freshness = _write(
        tmp_path / "freshness.json",
        {
            "status": "passed",
            "checked_at": "2026-08-28T09:05:00+08:00",
            "checks": {
                "data_update_quick_status": "passed",
                "data_update_quick_checked_date": "2026-08-27",
                "data_update_quick_expected_date": "2026-08-28",
            },
        },
    )

    result = load_data_update_timeline(
        update_status_path=update,
        freshness_status_path=freshness,
        now=datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc),
    )

    assert result["status"] == "degraded"
    assert any("quick_checked_date_before_expected" in item for item in result["diagnostics"])


def test_timeline_degrades_when_freshness_observations_mismatch_target_date(
    tmp_path: Path,
) -> None:
    update = _write(tmp_path / "update.json", _warning_update_payload())
    freshness = _write(
        tmp_path / "freshness.json",
        {
            "status": "passed",
            "checked_at": "2026-08-28T09:05:00+08:00",
            "checks": {
                "daily_prices_latest_date": "20260827",
                "technical_indicators_latest_date": "20260828",
                "data_update_quick_status": "failed",
                "data_update_quick_checked_date": "2026-08-27",
                "data_update_quick_expected_date": "2026-08-28",
                "twse_daily_price_file_exists_for_latest_date": False,
            },
        },
    )

    result = load_data_update_timeline(
        update_status_path=update,
        freshness_status_path=freshness,
        now=datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc),
    )

    assert result["status"] == "degraded"
    assert result["last_success_at"] == "2026-08-28T09:00:00+08:00"
    assert result["run_id"] == "run-1"
    assert result["artifacts"]["update"]["warning_count"] == 1
    assert any("daily_prices_latest_date_mismatch" in item for item in result["diagnostics"])
    assert any("quick_status_not_success" in item for item in result["diagnostics"])
    assert any("twse_daily_price_file_missing" in item for item in result["diagnostics"])


def test_timeline_does_not_claim_success_for_failed_or_future_run(tmp_path: Path) -> None:
    failed = _write(tmp_path / "failed.json", _update_payload(status="failed"))
    failed_result = load_data_update_timeline(
        update_status_path=failed,
        now=datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc),
    )
    assert failed_result["status"] == "failed"
    assert failed_result["last_success_at"] is None

    future = _write(
        tmp_path / "future.json",
        _update_payload(completed_at="2026-08-29T09:00:00+08:00"),
    )
    future_result = load_data_update_timeline(
        update_status_path=future,
        now=datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc),
    )
    assert future_result["status"] == "invalid"
    assert future_result["last_success_at"] is None
    assert any("timestamp_in_future" in item for item in future_result["diagnostics"])


def test_timeline_marks_old_run_stale_without_reusing_other_files(tmp_path: Path) -> None:
    update = _write(tmp_path / "update.json", _update_payload())
    result = load_data_update_timeline(
        update_status_path=update,
        freshness_status_path=tmp_path / "missing-freshness.json",
        tpex_status_path=tmp_path / "missing-tpex.json",
        now=datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc),
    )

    assert result["status"] == "stale"
    assert result["last_success_at"] == "2026-08-28T09:00:00+08:00"
    assert any("freshness_artifact_missing" in item for item in result["diagnostics"])
    assert any("tpex_artifact_missing" in item for item in result["diagnostics"])


def test_timeline_missing_and_invalid_are_fail_closed(tmp_path: Path) -> None:
    missing = load_data_update_timeline(
        update_status_path=tmp_path / "nope.json",
        now=datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc),
    )
    assert missing["status"] == "missing"
    assert missing["last_success_at"] is None

    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("[]", encoding="utf-8")
    invalid = load_data_update_timeline(
        update_status_path=invalid_path,
        now=datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc),
    )
    assert invalid["status"] == "missing"
    assert any("update_artifact_root_not_object" in item for item in invalid["diagnostics"])


def test_timeline_rejects_warning_success_with_error_or_failed_step(tmp_path: Path) -> None:
    with_error = _warning_update_payload()
    with_error["errors"] = ["a scheduled update step failed"]
    failed_step = _warning_update_payload()
    failed_step["steps"][1]["status"] = "failed"
    without_warning = _warning_update_payload()
    without_warning["warnings"] = []
    without_identity = _warning_update_payload()
    without_identity.pop("run_id")
    without_date = _warning_update_payload()
    without_date.pop("end_date")
    with_unknown_step = _warning_update_payload()
    with_unknown_step["steps"][1]["status"] = "pending"

    for name, payload in (
        ("with-error", with_error),
        ("failed-step", failed_step),
        ("without-warning", without_warning),
        ("without-identity", without_identity),
        ("without-date", without_date),
        ("unknown-step", with_unknown_step),
    ):
        update = _write(tmp_path / f"{name}.json", payload)
        result = load_data_update_timeline(
            update_status_path=update,
            now=datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc),
        )

        assert result["status"] == "invalid"
        assert result["last_success_at"] is None
        assert "update:invalid_warning_success_evidence" in result["diagnostics"]


def test_timeline_keeps_unknown_terminal_status_invalid(tmp_path: Path) -> None:
    update = _write(tmp_path / "unknown.json", _update_payload(status="mystery"))

    result = load_data_update_timeline(
        update_status_path=update,
        now=datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc),
    )

    assert result["status"] == "invalid"
    assert result["last_success_at"] is None
    assert "update:unsupported_status:mystery" in result["diagnostics"]
