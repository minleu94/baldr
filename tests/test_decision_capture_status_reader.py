from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json

import pytest

from app_module.decision_capture_status_reader import read_decision_capture_status
from app_module.sqlite_read_only import ReadOperationCancelled
from tests.decision_capture_status_fixture import (
    create_decision_capture_fixture,
    create_pending_artifact_fixture,
    create_prelaunch_failure_fixture,
)


BASE_TIME = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)


def _read(fixture, *, observed_at: datetime | None = None):
    return read_decision_capture_status(
        fixture.status_path,
        observed_at=observed_at or fixture.completed_at + timedelta(minutes=1),
    )


def _payload(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_payload(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _reseal_temporal_fixture(fixture, *, child_mode="eod_research", natural_authority=False):
    payload = _payload(fixture.status_path)
    temporal = {
        "capture_mode": "eod_research",
        "temporal_status": "verified",
        "research_only": True,
        "preopen_authority": False,
        "natural_authority": natural_authority,
    }
    payload.update(temporal)
    payload["snapshot"].update(temporal)
    payload["evidence"].update(temporal)
    payload["evidence"]["capture_mode"] = child_mode
    payload["reservation_wait"] = {"elapsed_seconds": 4203.062}
    payload.pop("receipt_sha256")
    _write_payload(fixture.receipt_path, payload)
    payload["receipt_sha256"] = sha256(fixture.receipt_path.read_bytes()).hexdigest()
    _write_payload(fixture.status_path, payload)


def test_reader_projects_only_verified_research_use_and_reservation_wait(tmp_path):
    fixture = create_decision_capture_fixture(tmp_path / "temporal", producer_now=BASE_TIME)
    _reseal_temporal_fixture(fixture)

    result = _read(fixture)

    assert result.read_state == "verified"
    assert result.capture_mode == "eod_research"
    assert result.temporal_status == "verified"
    assert result.research_only is True
    assert result.preopen_authority is False
    assert result.natural_authority is False
    assert result.reservation_wait_seconds == Decimal("4203.062")


@pytest.mark.parametrize("change", ("child_mismatch", "unsupported_authority"))
def test_reader_rejects_inconsistent_temporal_use_even_with_resealed_receipt(tmp_path, change):
    fixture = create_decision_capture_fixture(tmp_path / change, producer_now=BASE_TIME)
    _reseal_temporal_fixture(
        fixture,
        child_mode="research_only" if change == "child_mismatch" else "eod_research",
        natural_authority=change == "unsupported_authority",
    )

    result = _read(fixture)

    assert result.read_state == "unverified"
    assert result.diagnostic == (
        "decision_capture_temporal_child_mismatch"
        if change == "child_mismatch"
        else "decision_capture_temporal_authority_unproven"
    )


def test_reader_verifies_original_receipt_artifacts_and_safe_stage_summary(tmp_path):
    fixture = create_decision_capture_fixture(
        tmp_path / "output",
        producer_now=BASE_TIME,
        private_text="PRIVATE_CAPTURE_PAYLOAD must stay in the saved stderr artifact",
    )

    result = _read(fixture)

    assert result.read_state == "verified"
    assert result.raw_status == "passed"
    assert result.run_id == fixture.run_id
    assert result.decision_date == fixture.decision_date
    assert result.completed_at == fixture.completed_at.isoformat()
    assert result.receipt_path == str(fixture.receipt_path)
    assert result.receipt_sha256 == _payload(fixture.status_path)["receipt_sha256"]
    assert result.snapshot_status == "passed"
    assert result.snapshot_saved is True
    assert result.snapshot_duplicate is False
    assert result.snapshot_execution_status == "returned"
    assert result.last_stage == "snapshot"
    assert result.unfinished_stages == ()
    assert [stage.stage for stage in result.stages] == ["config", "config", "snapshot", "snapshot"]
    assert all(type(stage.elapsed_ms) is int and stage.elapsed_ms >= 0 for stage in result.stages)
    assert "PRIVATE_CAPTURE_PAYLOAD" not in repr(result)


def test_retry_pointer_selects_new_immutable_run_without_changing_old_receipt(tmp_path):
    output_root = tmp_path / "output"
    first = create_decision_capture_fixture(output_root, producer_now=BASE_TIME)
    first_receipt = first.receipt_path.read_bytes()
    second = create_decision_capture_fixture(output_root, producer_now=BASE_TIME)

    result = _read(second)

    assert first.run_id != second.run_id
    assert result.run_id == second.run_id
    assert first.receipt_path.read_bytes() == first_receipt


def test_missing_bare_passed_and_pending_statuses_fail_closed(tmp_path):
    missing_path = (
        tmp_path / "missing" / "scheduled" / "decision_evidence_capture" / "latest_status.json"
    )
    missing = read_decision_capture_status(missing_path, observed_at=BASE_TIME)
    assert missing.read_state == "missing"

    bare_path = (
        tmp_path / "bare" / "scheduled" / "decision_evidence_capture" / "latest_status.json"
    )
    bare_path.parent.mkdir(parents=True)
    _write_payload(bare_path, {"status": "passed", "checked_at": BASE_TIME.isoformat()})
    bare = read_decision_capture_status(bare_path, observed_at=BASE_TIME + timedelta(minutes=1))
    assert bare.read_state == "not_finalized"
    assert bare.raw_status == "passed"

    pending = create_decision_capture_fixture(tmp_path / "pending", producer_now=BASE_TIME)
    pending_payload = _payload(pending.status_path)
    pending_payload["finalized"] = False
    _write_payload(pending.status_path, pending_payload)
    not_finalized = _read(pending)
    assert not_finalized.read_state == "not_finalized"
    assert not_finalized.snapshot_saved is None


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("run_id", "20261015T120000000001Z-0123456789ab"),
        ("receipt_path", "C:/outside/receipt.json"),
        ("receipt_sha256", "0" * 64),
    ),
)
def test_reader_rejects_changed_run_path_and_receipt_hash(tmp_path, field, value):
    fixture = create_decision_capture_fixture(tmp_path / field, producer_now=BASE_TIME)
    payload = _payload(fixture.status_path)
    payload[field] = value
    _write_payload(fixture.status_path, payload)

    result = _read(fixture)

    assert result.read_state == "unverified"


def test_reader_rejects_future_decision_date_and_future_completion_clock(tmp_path):
    future_date = create_decision_capture_fixture(
        tmp_path / "future-date",
        producer_now=BASE_TIME,
        decision_date="2026-10-16",
    )
    assert _read(future_date).read_state == "unverified"

    future_completion = create_decision_capture_fixture(
        tmp_path / "future-completion",
        producer_now=BASE_TIME + timedelta(minutes=2),
    )
    result = _read(
        future_completion,
        observed_at=BASE_TIME + timedelta(minutes=1),
    )
    assert result.read_state == "unverified"
    assert result.diagnostic == "decision_capture_clock_out_of_order_or_future"


def test_reader_rejects_missing_receipt_and_incomplete_child_artifact(tmp_path):
    missing_receipt = create_decision_capture_fixture(
        tmp_path / "missing-receipt",
        producer_now=BASE_TIME,
    )
    missing_receipt.receipt_path.unlink()
    assert _read(missing_receipt).read_state == "unverified"

    missing_artifact = create_decision_capture_fixture(
        tmp_path / "missing-artifact",
        producer_now=BASE_TIME,
    )
    (missing_artifact.run_dir / "evidence.stderr.txt").unlink()
    assert _read(missing_artifact).read_state == "unverified"


def test_reader_rejects_tampered_child_artifact_and_changed_during_read(tmp_path):
    tampered = create_decision_capture_fixture(tmp_path / "tampered", producer_now=BASE_TIME)
    artifact_path = tampered.run_dir / "snapshot.stdout.txt"
    artifact_path.write_bytes(artifact_path.read_bytes() + b"tampered")
    result = _read(tampered)
    assert result.read_state == "unverified"
    assert result.diagnostic == "decision_capture_artifact_size_mismatch" or (
        result.diagnostic == "decision_capture_artifact_hash_mismatch"
    )

    changed = create_decision_capture_fixture(tmp_path / "changed", producer_now=BASE_TIME)
    calls = 0

    def change_after_status_read():
        nonlocal calls
        calls += 1
        if calls == 3:
            changed.status_path.write_bytes(changed.status_path.read_bytes() + b" ")
        return False

    changed_result = read_decision_capture_status(
        changed.status_path,
        observed_at=changed.completed_at + timedelta(minutes=1),
        check_cancel=change_after_status_read,
    )
    assert changed_result.read_state == "unverified"
    assert changed_result.diagnostic == "decision_capture_changed_during_read"


def test_reader_propagates_cooperative_cancel_and_preserves_unknown_timeout_writes(tmp_path):
    fixture = create_decision_capture_fixture(
        tmp_path / "timeout",
        producer_now=BASE_TIME,
        timeout=True,
        private_text="PRIVATE_TIMEOUT_STDERR",
    )
    result = _read(fixture)
    assert result.read_state == "verified"
    assert result.raw_status == "degraded"
    assert result.snapshot_status == "timeout"
    assert result.snapshot_saved is None
    assert result.snapshot_duplicate is None
    assert result.failure_reasons == ("snapshot_cli_timeout", "snapshot_json_invalid")
    assert "PRIVATE_TIMEOUT_STDERR" not in repr(result)

    with pytest.raises(ReadOperationCancelled):
        read_decision_capture_status(
            fixture.status_path,
            observed_at=fixture.completed_at + timedelta(minutes=1),
            check_cancel=lambda: True,
        )


@pytest.mark.parametrize(
    "error_type",
    (
        "FileNotFoundError",
        "PermissionError",
        "NotADirectoryError",
        "ValueError",
        "TypeError",
    ),
)
def test_reader_accepts_only_named_definite_prelaunch_failures(
    tmp_path,
    monkeypatch,
    error_type,
):
    fixture = create_prelaunch_failure_fixture(
        tmp_path / "capture",
        producer_now=BASE_TIME,
        monkeypatch=monkeypatch,
        error_type=error_type,
    )

    result = _read(fixture)

    assert result.read_state == "verified"
    assert result.raw_status == "failed"
    assert result.snapshot_execution_status == "failed"
    assert result.snapshot_saved is None
    assert result.snapshot_duplicate is None
    assert result.failure_reasons == (f"snapshot_step_exception:{error_type}",)
    assert "synthetic child launch failure" not in repr(result)


def test_reader_rejects_post_start_pending_child_artifacts(tmp_path, monkeypatch):
    fixture = create_pending_artifact_fixture(
        tmp_path / "pending-artifact",
        producer_now=BASE_TIME,
        monkeypatch=monkeypatch,
    )

    result = _read(fixture)

    assert result.read_state == "unverified"
    assert result.diagnostic == "decision_capture_artifacts_incomplete"


@pytest.mark.parametrize("raw_status", ("published", "completed", "running"))
def test_unrelated_or_running_status_cannot_become_a_verified_capture(tmp_path, raw_status):
    fixture = create_decision_capture_fixture(tmp_path / "output", producer_now=BASE_TIME)
    payload = _payload(fixture.status_path)
    payload["status"] = raw_status
    receipt = {key: value for key, value in payload.items() if key != "receipt_sha256"}
    raw_receipt = json.dumps(receipt, ensure_ascii=False, sort_keys=True).encode("utf-8")
    # 即使同時損壞兩檔並重算hash，也不能借其他job的成功字串通過本lane。
    fixture.receipt_path.write_bytes(raw_receipt)
    payload["receipt_sha256"] = sha256(raw_receipt).hexdigest()
    _write_payload(fixture.status_path, payload)

    result = _read(fixture)

    assert result.read_state == "unverified"
    assert result.diagnostic == "decision_capture_terminal_status_invalid"
