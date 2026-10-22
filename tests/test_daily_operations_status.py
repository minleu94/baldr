"""每日排程唯讀分類器的合成資料契約測試。"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from app_module.daily_operations_status import (
    ObservationError,
    SCHEMA,
    classify_component,
    parse_aware_timestamp,
    validate_manifest,
)
from scripts.audit_daily_operations import _read_receipt


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
        "run_id": "run-1",
        "started_at": "2026-10-21T11:59:00+00:00",
        "completed_at": "2026-10-21T11:59:30+00:00",
        "status": "completed",
        "producer_status": "passed",
        "blockers": [],
    }
    receipt.update(changes)
    return receipt


def test_healthy_requires_re_read_same_run_success_receipt() -> None:
    assert classify_component(_row(), receipt=_receipt(), observed_at=NOW)["status"] == "HEALTHY"
    # Manifest 的自我宣告不能取代收據身份證據。
    mismatched = classify_component(
        _row(receipt_identity_verified=True),
        receipt=_receipt(run_id="other-run"),
        observed_at=NOW,
    )
    assert mismatched["status"] == "UNKNOWN"
    assert "receipt_run_id_mismatch" in mismatched["reason"]


def test_scheduler_zero_is_not_pipeline_success_and_missing_run_binding_is_unknown() -> None:
    row = _row(producer_status=None, producer_run_id=None, scheduler_last_run_at=None)
    result = classify_component(row, receipt=None, observed_at=NOW)
    assert result["status"] == "UNKNOWN"
    assert result["downstream_hold"] is True


def test_unknown_scheduler_result_or_reader_error_cannot_be_healthy() -> None:
    assert classify_component(_row(scheduler_result=None), receipt=_receipt(), observed_at=NOW)["status"] == "UNKNOWN"
    assert classify_component(_row(), receipt=_receipt(), receipt_error="identity_changed", observed_at=NOW)["status"] == "UNKNOWN"


def test_future_observation_cannot_authorize_future_receipt() -> None:
    with pytest.raises(ObservationError, match="future_timestamp"):
        validate_manifest({"schema": SCHEMA, "observed_at": "9999-01-01T00:00:00+00:00", "components": []})


def test_expected_disabled_is_individual_degraded_reason_without_system_inference() -> None:
    result = classify_component(
        _row(enabled=False, expected_enabled=False, receipt_ref=None), observed_at=NOW
    )
    assert result["status"] == "DEGRADED"
    assert result["downstream_hold"] is True
    assert result["reason"] == ["expected_disabled"]


def test_source_block_and_maturity_remain_distinct_from_execution_failure() -> None:
    blocked = classify_component(
        _row(), receipt=_receipt(producer_status="blocked", blockers=["source_not_available"]),
        observed_at=NOW,
    )
    pending = classify_component(
        _row(), receipt=_receipt(producer_status="pending"), observed_at=NOW
    )
    failed = classify_component(
        _row(), receipt=_receipt(producer_status="failed"), observed_at=NOW
    )
    assert blocked["status"] == "BLOCKED_SOURCE"
    assert pending["status"] == "DEGRADED"
    assert failed["status"] == "EXECUTION_FAILED"


def test_formal_writer_never_gets_safe_retry_and_receipt_future_is_unknown() -> None:
    result = classify_component(
        _row(writes_formal_data=True),
        receipt=_receipt(started_at="2026-10-21T12:10:00+00:00"),
        observed_at=NOW,
    )
    assert result["status"] == "UNKNOWN"
    assert result["safe_retry"] is False
    assert "receipt_timestamp_future" in result["reason"]


@pytest.mark.parametrize(
    ("changes", "expected_reason"),
    [
        ({"completed_at": None}, "receipt_completed_at_missing"),
        ({"started_at": "2026-10-21T11:59:40+00:00", "completed_at": "2026-10-21T11:59:30+00:00"}, "receipt_completed_before_started"),
        ({"completed_at": "2026-10-21T12:00:01+00:00"}, "receipt_completed_at_future"),
    ],
)
def test_receipt_completion_must_be_present_ordered_and_not_future(
    changes: dict[str, object], expected_reason: str
) -> None:
    result = classify_component(_row(), receipt=_receipt(**changes), observed_at=NOW)
    assert result["status"] == "UNKNOWN"
    assert expected_reason in result["reason"]


def test_reader_accepts_status_only_receipt_and_classifier_can_verify_it(tmp_path: Path) -> None:
    payload = {
        "run_id": "run-1",
        "started_at": "2026-10-21T11:59:00+00:00",
        "completed_at": "2026-10-21T11:59:30+00:00",
        "status": "completed",
        "blockers": [],
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    (tmp_path / "run.json").write_bytes(raw)
    receipt = _read_receipt(
        tmp_path,
        {"path": "run.json", "sha256": hashlib.sha256(raw).hexdigest()},
    )
    assert classify_component(_row(), receipt=receipt, observed_at=NOW)["status"] == "HEALTHY"


def test_manifest_caps_duplicate_ids_and_requires_aware_timestamps() -> None:
    base = {
        "schema": SCHEMA,
        "observed_at": "2026-10-21T12:00:00+00:00",
        "components": [_row()],
    }
    validated = validate_manifest(base)
    assert validated["_observed_at_utc"] == NOW
    with pytest.raises(ObservationError, match="duplicate"):
        validate_manifest({**base, "components": [_row(), _row()]})
    with pytest.raises(ObservationError, match="timezone_required"):
        parse_aware_timestamp("2026-10-21T12:00:00", "observed_at")
    with pytest.raises(ObservationError, match="invalid_count"):
        validate_manifest({**base, "components": [_row(id=f"job-{i}") for i in range(129)]})
