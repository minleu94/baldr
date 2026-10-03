"""研究採集查核不得將未綁定或遭竄改的證據判為成功。"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import pytest

from scripts import audit_scheduled_research_acquisition as audit


def monthly_fixture(monkeypatch, tmp_path):
    files = {}
    for relative in ['candidate.csv', 'availability.csv', 'source/capture_run.json', 'full_source_scope_manifest.json', 'source/twse.json', 'source/tpex.json']:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = b'original artifact'
        path.write_bytes(raw)
        files[relative] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    manifest = {'schema_version': 'monthly-revenue-research-candidate.v1', 'status': 'research_only_candidate_created', 'run_id': 'child', 'candidate_period': '2026-08', 'source_row_count': 1978, 'candidate_file': 'candidate.csv', 'availability_file': 'availability.csv', 'readback': {'files': files}}
    manifest.update({flag: False for flag in ['auto_apply', 'formal_apply_authorized', 'historical_pit_credit', 'writes_formal_data', 'writes_formal_database']})
    raw = json.dumps(manifest).encode()
    (tmp_path / 'manifest.json').write_bytes(raw)
    sources = {venue: {'requested_url': url, 'http_status': 200, 'status': 'captured', 'content_sha256': files['source/'+venue+'.json']['sha256']} for venue, url in audit.MONTHLY_URLS.items()}
    result = {'schema_version': 'monthly-revenue-research-candidate-status.v1', 'status': 'captured', 'run_root': str(tmp_path), 'candidate_manifest_file': 'manifest.json', 'candidate_manifest_sha256': hashlib.sha256(raw).hexdigest(), 'run_id': 'child', 'candidate_period': '2026-08', 'source_results': sources}
    quick = tmp_path / 'status.json'
    child = tmp_path / 'child.json'
    child.write_text(json.dumps({'schema_version': 'scheduled-monthly-revenue-research-capture.v1', 'run_id': 'parent', 'core_status': 'passed', 'core_status_path': str(quick), 'research_capture': {'status': 'captured', 'result': result}}))
    parent = {'run_id': 'parent', 'status': 'passed', 'monthly_revenue_research_capture': {'result_receipt_path': str(child)}}
    monkeypatch.setattr(audit, '_quick_status_snapshot', lambda **_: (parent, {'binding_status': 'verified', 'status_sha256': 'parent-pin'}))
    return quick


def test_monthly_readback_preserves_qualification_limit(monkeypatch, tmp_path):
    quick = monthly_fixture(monkeypatch, tmp_path)
    result = audit.audit_monthly(quick, now=datetime.now(timezone.utc))
    assert result['status'] == 'captured_verified'
    assert result['verified_artifact_count'] == 6
    assert result['child_records_parent_sha256'] is False
    assert result['formal_database_updated'] is False


def test_changed_monthly_entity_rejected(monkeypatch, tmp_path):
    quick = monthly_fixture(monkeypatch, tmp_path)
    (tmp_path / 'source/tpex.json').write_bytes(b'tampered artifact')
    with pytest.raises(ValueError, match='artifact_hash_mismatch'):
        audit.audit_monthly(quick, now=datetime.now(timezone.utc))


def test_parent_terminal_requires_verified_binding(monkeypatch, tmp_path):
    monkeypatch.setattr(audit, "_quick_status_snapshot", lambda **_: ({}, {"binding_status": "unverified"}))
    with pytest.raises(ValueError, match="parent_terminal_identity"):
        audit.audit_monthly(tmp_path / "status.json", now=datetime.now(timezone.utc))


def test_monthly_parent_identity_mismatch(monkeypatch, tmp_path):
    child = tmp_path / "child.json"
    child.write_text(json.dumps({"schema_version": "scheduled-monthly-revenue-research-capture.v1", "run_id": "other", "core_status": "passed"}))
    parent = {"run_id": "expected", "status": "passed", "monthly_revenue_research_capture": {"result_receipt_path": str(child)}}
    monkeypatch.setattr(audit, "_quick_status_snapshot", lambda **_: (parent, {"binding_status": "verified"}))
    with pytest.raises(ValueError, match="parent_child_identity"):
        audit.audit_monthly(tmp_path / "status.json", now=datetime.now(timezone.utc))


@pytest.mark.parametrize("relative", ["../secret", "C:/secret", "/secret", "source\\secret"])
def test_artifact_path_escape_rejected(tmp_path, relative):
    with pytest.raises(ValueError):
        audit._member(tmp_path, relative)


def test_quarterly_changed_readback_rejected(monkeypatch, tmp_path):
    terminal = tmp_path / "terminal.json"
    terminal.write_text(json.dumps({"schema_version": "mops-quarterly-openapi-research-terminal.v1", "status": "completed_with_review_items", "formal_pit_eligible": False, "candidate_available_at": None, "run_id": "run", "readback": {"run_id": "run", "numeric_rows_rechecked": 1}}))
    monkeypatch.setattr(audit, "verify_capture_run", lambda _: {"run_id": "run", "numeric_rows_rechecked": 2})
    with pytest.raises(ValueError, match="terminal_readback_mismatch"):
        audit.audit_quarterly(terminal)


def test_quarterly_pit_promotion_rejected(tmp_path):
    terminal = tmp_path / "terminal.json"
    terminal.write_text(json.dumps({"schema_version": "mops-quarterly-openapi-research-terminal.v1", "status": "completed_with_review_items", "formal_pit_eligible": True, "candidate_available_at": None}))
    with pytest.raises(ValueError, match="qualification_boundary"):
        audit.audit_quarterly(terminal)


def test_main_missing_receipt_returns_blocked(tmp_path):
    output = tmp_path / "audit.json"
    assert audit.main(["--quick-status", str(tmp_path / "missing.json"), "--output", str(output)]) == 2
    report = json.loads(output.read_text())
    assert report["sources"]["monthly"]["status"] == "blocked"
    assert report["database_write_performed"] is False


def _quick_pending_fixture(tmp_path, *, completed_at="2026-10-03T08:00:00+00:00", child_status="pending_after_core_publication"):
    quick_root = tmp_path / "scheduled" / "data_update_quick"
    receipts_root = quick_root / "research_capture_receipts"
    receipts_root.mkdir(parents=True, exist_ok=True)
    status_path = quick_root / "latest_status.json"
    run_id = "quick_20261003_080000"
    child_path = receipts_root / f"{run_id}-child.json"
    payload = {
        "task": "baldr-data-update-quick-daily",
        "status": "passed",
        "run_id": run_id,
        "completed_at": completed_at,
        "monthly_revenue_research_capture": {
            "status": child_status,
            "result_receipt_path": str(child_path),
        },
    }
    status_path.write_text(json.dumps(payload), encoding="utf-8")
    return status_path, payload, child_path


def test_quick_monthly_receipt_grace_is_exactly_120_seconds(tmp_path):
    from data_module.scheduled_research_acquisition_binding import quick_monthly_capture_status

    status_path, payload, _ = _quick_pending_fixture(tmp_path)
    binding = {"binding_status": "verified", "status_sha256": "sha256:" + "a" * 64}
    completed = datetime(2026, 10, 3, 8, 0, tzinfo=timezone.utc)
    at_boundary = quick_monthly_capture_status(
        quick_payload=payload,
        quick_binding=binding,
        quick_status_path=status_path,
        now=completed + timedelta(seconds=120),
    )
    after_boundary = quick_monthly_capture_status(
        quick_payload=payload,
        quick_binding=binding,
        quick_status_path=status_path,
        now=completed + timedelta(seconds=120, microseconds=1),
    )
    assert at_boundary["status"] == "pending"
    assert at_boundary["pending_limit_seconds"] == 120
    assert after_boundary["status"] == "blocked"
    assert after_boundary["reason"] == "quick_monthly_child_receipt_missing_after_grace"


@pytest.mark.parametrize(
    ("completed_at", "now", "expected_reason"),
    [
        ("2026-10-03T08:00:00", datetime(2026, 10, 3, 8, 1, tzinfo=timezone.utc), "quick_completed_at_must_be_aware"),
        ("2026-10-03T09:00:00+00:00", datetime(2026, 10, 3, 8, 1, tzinfo=timezone.utc), "quick_completed_at_in_future"),
    ],
)
def test_quick_monthly_invalid_or_future_clock_fails_closed(tmp_path, completed_at, now, expected_reason):
    from data_module.scheduled_research_acquisition_binding import quick_monthly_capture_status

    status_path, payload, _ = _quick_pending_fixture(tmp_path, completed_at=completed_at)
    result = quick_monthly_capture_status(
        quick_payload=payload,
        quick_binding={"binding_status": "verified"},
        quick_status_path=status_path,
        now=now,
    )
    assert result["status"] == "blocked"
    assert result["reason"] == expected_reason


def test_quick_monthly_explicit_failure_is_not_masked_by_pending_parent(tmp_path):
    from data_module.scheduled_research_acquisition_binding import quick_monthly_capture_status

    status_path, payload, _ = _quick_pending_fixture(tmp_path, child_status="failed")
    result = quick_monthly_capture_status(
        quick_payload=payload,
        quick_binding={"binding_status": "verified"},
        quick_status_path=status_path,
        now=datetime(2026, 10, 3, 8, 1, tzinfo=timezone.utc),
    )
    assert result["status"] == "failed"
    assert result["reason"] == "quick_monthly_child_declared_failed"


def test_weekly_audit_defaults_to_locator_and_requires_external_pin_pair(tmp_path):
    now = datetime.now(timezone.utc)
    output = tmp_path / "audit.json"
    assert audit.main(["--quick-status", str(tmp_path / "missing.json"), "--output-root", str(tmp_path), "--output", str(output)]) == 2
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["sources"]["weekly_collection"]["status"] == "not_recorded"
    assert audit.main([
        "--quick-status", str(tmp_path / "missing.json"),
        "--output-root", str(tmp_path),
        "--weekly-parent-receipt-path", str(tmp_path / "receipt.json"),
        "--output", str(output),
    ]) == 2
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["sources"]["weekly_collection"]["reason"] == "external_receipt_path_sha_pair_incomplete"


def _patch_audit_without_monthly_capture(monkeypatch):
    monkeypatch.setattr(
        audit,
        "_quick_status_snapshot",
        lambda **_: ({"run_id": "quick-run", "status": "passed"}, {"binding_status": "verified"}),
    )
    monkeypatch.setattr(
        audit,
        "audit_quick_monthly_capture",
        lambda *args, **kwargs: {"status": "not_recorded", "formal_credit": False},
    )


def test_weekly_audit_infers_only_standard_quick_output_root(monkeypatch, tmp_path):
    output_root = tmp_path / "OUTPUT_ROOT"
    quick = output_root / "scheduled" / "data_update_quick" / "latest_status.json"
    receipt = output_root / "scheduled" / "v2_2_weekly_collection" / "controller_runs" / "run" / "terminal.json"
    _patch_audit_without_monthly_capture(monkeypatch)
    calls = []

    def verify(root, **kwargs):
        calls.append((root, kwargs))
        return {"status": "not_recorded", "formal_credit": False}

    monkeypatch.setattr(audit, "verify_weekly_acquisition", verify)
    output = tmp_path / "audit.json"
    assert audit.main([
        "--quick-status", str(quick),
        "--weekly-parent-receipt-path", str(receipt),
        "--weekly-parent-receipt-sha256", "a" * 64,
        "--output", str(output),
    ]) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert len(calls) == 1
    assert calls[0][0] == output_root
    assert calls[0][1]["now"].tzinfo is not None
    assert calls[0][1]["receipt_path"] == receipt
    assert calls[0][1]["expected_sha256"] == "a" * 64
    assert report["sources"]["weekly_collection"]["status"] == "not_recorded"


def test_weekly_audit_explicit_output_root_wins_for_noncanonical_quick_path(monkeypatch, tmp_path):
    _patch_audit_without_monthly_capture(monkeypatch)
    explicit_root = tmp_path / "chosen-output"
    noncanonical_quick = tmp_path / "custom" / "quick.json"
    calls = []
    monkeypatch.setattr(
        audit,
        "verify_weekly_acquisition",
        lambda root, **kwargs: calls.append((root, kwargs)) or {"status": "not_recorded"},
    )
    output = tmp_path / "explicit-root-audit.json"
    assert audit.main([
        "--quick-status", str(noncanonical_quick),
        "--output-root", str(explicit_root),
        "--weekly-parent-receipt-path", str(explicit_root / "parent.json"),
        "--weekly-parent-receipt-sha256", "b" * 64,
        "--output", str(output),
    ]) == 0
    assert calls[0][0] == explicit_root
    assert calls[0][1]["receipt_path"] == explicit_root / "parent.json"


def test_weekly_audit_blocks_noncanonical_quick_path_without_explicit_root(monkeypatch, tmp_path):
    _patch_audit_without_monthly_capture(monkeypatch)
    monkeypatch.setattr(
        audit,
        "verify_weekly_acquisition",
        lambda *args, **kwargs: pytest.fail("must not infer arbitrary output roots"),
    )
    output = tmp_path / "blocked-audit.json"
    assert audit.main([
        "--quick-status", str(tmp_path / "custom" / "quick.json"),
        "--weekly-parent-receipt-path", str(tmp_path / "parent.json"),
        "--weekly-parent-receipt-sha256", "c" * 64,
        "--output", str(output),
    ]) == 2
    report = json.loads(output.read_text(encoding="utf-8"))
    weekly = report["sources"]["weekly_collection"]
    assert weekly["status"] == "blocked"
    assert weekly["reason"] == "weekly_output_root_requires_explicit_root_or_canonical_quick_path"


def test_weekly_audit_preserves_partial_as_top_level_partial_and_exit_two(monkeypatch, tmp_path):
    _patch_audit_without_monthly_capture(monkeypatch)
    weekly_partial = {
        "status": "partial",
        "reason": "weekly_research_child_failed",
        "child_failures": ["quarterly_openapi"],
        "children": {"quarterly_openapi": {"status": "failed", "producer_status": "blocked_catalog_contract_or_transport"}},
        "formal_credit": False,
    }
    monkeypatch.setattr(audit, "verify_weekly_acquisition", lambda *args, **kwargs: weekly_partial)
    output = tmp_path / "partial-audit.json"
    exit_code = audit.main([
        "--quick-status", str(tmp_path / "scheduled" / "data_update_quick" / "latest_status.json"),
        "--output-root", str(tmp_path),
        "--weekly-parent-receipt-path", str(tmp_path / "parent.json"),
        "--weekly-parent-receipt-sha256", "d" * 64,
        "--output", str(output),
    ])

    report = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert report["status"] == "partial"
    assert report["sources"]["weekly_collection"] == weekly_partial
    assert report["sources"]["monthly"]["status"] == "not_recorded"


def _freeze_audit_clock(monkeypatch, instant):
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant if tz is not None else instant.replace(tzinfo=None)

    monkeypatch.setattr(audit, "datetime", FrozenDateTime)


@pytest.mark.parametrize(
    ("age", "expected_status", "expected_exit"),
    [
        (timedelta(seconds=120), "pending", 0),
        (timedelta(seconds=120, microseconds=1), "blocked", 2),
    ],
)
def test_cli_monthly_uses_quick_publication_grace_boundary(
    monkeypatch, tmp_path, age, expected_status, expected_exit
):
    from data_module.scheduled_research_acquisition_binding import QUICK_CHILD_TOTAL_GRACE_SECONDS

    completed = datetime(2026, 10, 3, 8, 0, tzinfo=timezone.utc)
    _freeze_audit_clock(monkeypatch, completed + age)
    status_path, payload, _ = _quick_pending_fixture(tmp_path)
    parent_binding = {"binding_status": "verified", "status_sha256": "sha256:" + "a" * 64}
    monkeypatch.setattr(audit, "_quick_status_snapshot", lambda **_: (payload, parent_binding))
    output = tmp_path / f"audit-{expected_status}.json"

    assert age.total_seconds() <= QUICK_CHILD_TOTAL_GRACE_SECONDS + 0.000001
    exit_code = audit.main(["--quick-status", str(status_path), "--output", str(output)])
    report = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == expected_exit
    assert report["sources"]["monthly"]["status"] == expected_status
    assert report["database_write_performed"] is False


def test_cli_monthly_explicit_child_failure_is_not_pending(monkeypatch, tmp_path):
    completed = datetime(2026, 10, 3, 8, 0, tzinfo=timezone.utc)
    _freeze_audit_clock(monkeypatch, completed + timedelta(seconds=10))
    status_path, payload, _ = _quick_pending_fixture(tmp_path, child_status="failed")
    monkeypatch.setattr(
        audit,
        "_quick_status_snapshot",
        lambda **_: (payload, {"binding_status": "verified", "status_sha256": "sha256:" + "a" * 64}),
    )
    output = tmp_path / "audit-failed.json"

    assert audit.main(["--quick-status", str(status_path), "--output", str(output)]) == 2
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["sources"]["monthly"]["status"] == "failed"
    assert report["sources"]["monthly"]["reason"] == "quick_monthly_child_declared_failed"


def test_cli_monthly_completed_receipt_runs_full_quick_parent_readback(monkeypatch, tmp_path):
    completed = datetime(2026, 10, 3, 8, 0, tzinfo=timezone.utc)
    _freeze_audit_clock(monkeypatch, completed + timedelta(seconds=5))
    monthly_fixture(monkeypatch, tmp_path)
    source_child = json.loads((tmp_path / "child.json").read_text(encoding="utf-8"))

    quick_path, quick_payload, child_path = _quick_pending_fixture(tmp_path, child_status="captured")
    source_child["run_id"] = quick_payload["run_id"]
    source_child["core_status_path"] = str(quick_path)
    child_path.write_text(json.dumps(source_child), encoding="utf-8")
    parent_binding = {"binding_status": "verified", "status_sha256": "sha256:" + "a" * 64}
    monkeypatch.setattr(audit, "_quick_status_snapshot", lambda **_: (quick_payload, parent_binding))
    output = tmp_path / "audit-captured.json"

    assert audit.main(["--quick-status", str(quick_path), "--output", str(output)]) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["sources"]["monthly"]["status"] == "captured_verified"
    assert report["sources"]["monthly"]["parent_run_id"] == quick_payload["run_id"]
    assert report["sources"]["monthly"]["child_records_parent_sha256"] is False
