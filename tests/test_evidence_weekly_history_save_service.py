from __future__ import annotations

from hashlib import sha256
from types import SimpleNamespace

import pytest

import app_module.evidence_weekly_history_save_service as save_module
from app_module.research_run_dtos import canonical_json


def _report():
    return SimpleNamespace(
        start_date="2026-10-19",
        end_date="2026-10-25",
        status="coverage_only",
        manual_approval=SimpleNamespace(readiness="not_ready"),
        decision_quality=SimpleNamespace(reviews_count=0),
        signal_decay=SimpleNamespace(observations_count=0),
        manual_lifecycle_candidates=(),
        warnings=(),
        to_dict=lambda: {
            "start_date": "2026-10-19",
            "end_date": "2026-10-25",
            "write_performed": False,
        },
    )


def test_candidate_history_save_revalidates_and_reads_back_exact_record(monkeypatch):
    report = _report()
    calls = []
    decision = {
        "decision": "follow_up",
        "candidate_only": True,
        "artifact_sha256": "sha256:" + "a" * 64,
    }

    monkeypatch.setattr(
        save_module,
        "resolve_weekly_review_working_copy_path",
        lambda _config, path: calls.append(("resolve", path)) or "C:/scratch/weekly.db",
    )
    monkeypatch.setattr(
        save_module,
        "fingerprint_sqlite_file_set",
        lambda _path: {"files": [], "sha256": "stable"},
    )

    class _ReportService:
        source_lineage = {"market_source_db": "C:/scratch/weekly.db"}

        def __init__(self, _config, *, db_path, read_only):
            calls.append(("report_service", db_path, read_only))

        def build_weekly_review(self, *, start_date, end_date):
            calls.append(("build", start_date, end_date))
            return report

    monkeypatch.setattr(save_module, "EvidenceOperationsService", _ReportService)
    monkeypatch.setattr(
        save_module,
        "_validated_decision",
        lambda *args, **kwargs: calls.append(("validate", kwargs["start"], kwargs["end"])) or decision,
    )

    # The save result is returned by the same object the repository reads back.
    saved = SimpleNamespace(
        review_id="eor_test",
        review_hash="",
        period_start="2026-10-19",
        period_end="2026-10-25",
        payload_json={"candidate_review_decision": decision},
    )

    class _Repository:
        def __init__(self, _config, *, db_path, read_only):
            calls.append(("repository", db_path, read_only))

        def save_weekly_review(self, saved_report, *, generated_by, payload_json):
            calls.append(("save", generated_by, payload_json.copy()))
            assert saved_report is report
            saved.review_hash = "sha256:" + sha256(
                canonical_json(payload_json).encode("utf-8")
            ).hexdigest()
            saved.payload_json = payload_json
            return saved

        def get_weekly_review(self, review_id):
            calls.append(("readback", review_id))
            return saved

    monkeypatch.setattr(
        save_module,
        "EvidenceOperationsHistoryRepository",
        _Repository,
    )

    result = save_module.save_candidate_weekly_review_history(
        object(),
        db_path="C:/scratch/weekly.db",
        start_date="2026-10-19",
        end_date="2026-10-25",
        decision_artifact_path="C:/scratch/decision.json",
        sidecar_path="C:/scratch/sidecar.db",
        authorized_receipt_root="C:/scratch/output",
    )

    assert result.review_id == "eor_test"
    assert [call[0] for call in calls].count("validate") == 2
    assert ("report_service", "C:/scratch/weekly.db", True) in calls
    assert ("repository", "C:/scratch/weekly.db", False) in calls
    save_call = next(call for call in calls if call[0] == "save")
    assert save_call[2]["candidate_review_decision"] == decision
    assert save_call[2]["source_lineage"] == {"market_source_db": "C:/scratch/weekly.db"}
    assert save_call[2]["write_performed"] is True
    assert ("readback", "eor_test") in calls


def test_candidate_history_save_rejects_changed_decision_before_write(monkeypatch):
    report = _report()
    validations = iter(({"candidate_only": True}, {"candidate_only": False}))
    writes = []
    monkeypatch.setattr(save_module, "resolve_weekly_review_working_copy_path", lambda *_: "C:/scratch/weekly.db")
    monkeypatch.setattr(
        save_module,
        "fingerprint_sqlite_file_set",
        lambda _path: {"files": [], "sha256": "stable"},
    )

    class _ReportService:
        source_lineage = {}

        def __init__(self, *_args, **_kwargs):
            pass

        def build_weekly_review(self, **_kwargs):
            return report

    monkeypatch.setattr(save_module, "EvidenceOperationsService", _ReportService)
    monkeypatch.setattr(save_module, "_validated_decision", lambda *_args, **_kwargs: next(validations))
    monkeypatch.setattr(
        save_module,
        "EvidenceOperationsHistoryRepository",
        lambda *_args, **_kwargs: writes.append("constructed"),
    )

    with pytest.raises(ValueError, match="changed before weekly history save"):
        save_module.save_candidate_weekly_review_history(
            object(),
            db_path="C:/scratch/weekly.db",
            start_date="2026-10-19",
            end_date="2026-10-25",
            decision_artifact_path="C:/scratch/decision.json",
            sidecar_path="C:/scratch/sidecar.db",
        )
    assert writes == []


def test_candidate_history_save_requires_canonical_ordered_period():
    with pytest.raises(ValueError, match="must be an ISO date"):
        save_module.save_candidate_weekly_review_history(
            object(),
            db_path="C:/scratch/weekly.db",
            start_date="2026/10/19",
            end_date="2026-10-25",
            decision_artifact_path="C:/scratch/decision.json",
            sidecar_path="C:/scratch/sidecar.db",
        )
    with pytest.raises(ValueError, match="must not be after"):
        save_module.save_candidate_weekly_review_history(
            object(),
            db_path="C:/scratch/weekly.db",
            start_date="2026-10-26",
            end_date="2026-10-25",
            decision_artifact_path="C:/scratch/decision.json",
            sidecar_path="C:/scratch/sidecar.db",
        )
