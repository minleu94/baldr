from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from datetime import datetime

import pytest

from app_module.evidence_capture_service import EvidenceCaptureService
from app_module.evidence_event_dtos import EvidenceDataQuality, EvidenceEventType
from app_module.evidence_event_repository import EvidenceEventRepository
from app_module.evidence_event_service import EvidenceEventService
from app_module.evidence_event_importer_dtos import (
    EvidenceCaptureRequest,
    EvidenceImportDiagnostic,
    EvidenceImportResult,
    capture_context_is_valid,
)
from data_module.config import TWStockConfig


def _config(tmp_path: Path) -> TWStockConfig:
    return TWStockConfig(data_root=tmp_path / "data", output_root=tmp_path / "output")


class StaticImporter:
    source_name = "static"
    event_type = EvidenceEventType.RECOMMENDATION_INCLUDED

    def collect(self, request: EvidenceCaptureRequest) -> EvidenceImportResult:
        return EvidenceImportResult(
            source_name=self.source_name,
            decision_date=request.decision_date,
            event_payloads=(
                {
                    "event_date": "2026-07-02",
                    "decision_date": "2026-07-02",
                    "symbol": "2330",
                    "event_type": self.event_type,
                    "event_family": "recommendation",
                    "source_type": "recommendation_result",
                    "source_id": "rec-001",
                    "reason_codes": ("rank_top",),
                    "risk_codes": (),
                    "data_quality": EvidenceDataQuality.OBSERVED,
                    "warnings": ("source_warning",),
                    "as_of_date": "2026-07-02",
                    "available_date": "2026-07-02",
                    "metadata": {"stable": True},
                },
            ),
        )


class ExistingSourceAvailabilityImporter(StaticImporter):
    def collect(self, request: EvidenceCaptureRequest) -> EvidenceImportResult:
        base = super().collect(request)
        payload = dict(base.event_payloads[0])
        payload["metadata"] = {
            "stable": True,
            "source_availability": {
                "available_date": "2026-07-02",
                "source_timestamp": "2026-07-02T09:00:00+08:00",
                "owner": "source-custody",
                "capture_at_overrides_source_timestamp": True,
            },
        }
        return EvidenceImportResult(
            source_name=base.source_name,
            decision_date=base.decision_date,
            event_payloads=(payload,),
        )


class StringEventTypeImporter(StaticImporter):
    event_type = EvidenceEventType.RECOMMENDATION_INCLUDED.value


class DiagnosticWarningImporter(StaticImporter):
    def collect(self, request: EvidenceCaptureRequest) -> EvidenceImportResult:
        base = super().collect(request)
        return EvidenceImportResult(
            source_name=base.source_name,
            decision_date=base.decision_date,
            event_payloads=base.event_payloads,
            diagnostics=(
                EvidenceImportDiagnostic(
                    code="source_delayed",
                    message="source is delayed",
                    source_name=self.source_name,
                    severity="warning",
                ),
            ),
        )


class AdvisoryImporter(StaticImporter):
    def collect(self, request: EvidenceCaptureRequest) -> EvidenceImportResult:
        base = super().collect(request)
        return EvidenceImportResult(
            source_name=base.source_name,
            decision_date=base.decision_date,
            event_payloads=base.event_payloads,
            advisory_tokens=("portfolio_alerts_chip_estimated:2330",),
        )


def test_capture_service_dry_run_returns_hash_sample_without_writing(tmp_path):
    repository = EvidenceEventRepository(_config(tmp_path))
    service = EvidenceCaptureService(EvidenceEventService(repository), {"static": StaticImporter()})

    summary = service.capture(EvidenceCaptureRequest(source="static", decision_date="2026-07-02"))

    assert summary.dry_run is True
    assert summary.events_seen == 1
    assert summary.events_valid == 1
    assert summary.events_inserted == 0
    assert summary.sample_events[0]["event_hash"].startswith("sha256:")
    assert repository.list_events() == []


def test_capture_service_hash_is_stable_for_enum_or_string_event_type(tmp_path):
    request = EvidenceCaptureRequest(source="static", decision_date="2026-07-02")
    enum_service = EvidenceCaptureService(
        EvidenceEventService(EvidenceEventRepository(_config(tmp_path / "enum"))),
        {"static": StaticImporter()},
    )
    string_service = EvidenceCaptureService(
        EvidenceEventService(EvidenceEventRepository(_config(tmp_path / "string"))),
        {"static": StringEventTypeImporter()},
    )

    enum_summary = enum_service.capture(request)
    string_summary = string_service.capture(request)

    assert enum_summary.sample_events[0]["event_hash"] == string_summary.sample_events[0]["event_hash"]


def test_capture_service_confirm_writes_and_counts_duplicates(tmp_path):
    repository = EvidenceEventRepository(_config(tmp_path))
    service = EvidenceCaptureService(EvidenceEventService(repository), {"static": StaticImporter()})
    request = EvidenceCaptureRequest(
        source="static",
        decision_date="2026-07-02",
        dry_run=False,
        confirm=True,
    )

    first = service.capture(request)
    second = service.capture(request)

    assert first.events_inserted == 1
    assert first.events_skipped_duplicate == 0
    assert second.events_inserted == 0
    assert second.events_skipped_duplicate == 1
    assert len(repository.list_events()) == 1


def test_capture_service_source_all_keeps_unsupported_diagnostic_and_runs_supported(tmp_path):
    repository = EvidenceEventRepository(_config(tmp_path))
    service = EvidenceCaptureService(EvidenceEventService(repository), {"static": StaticImporter()})

    summary = service.capture(
        EvidenceCaptureRequest(source="all", decision_date="2026-07-02", dry_run=False, confirm=True)
    )

    assert summary.source_name == "all"
    assert summary.events_inserted == 1
    assert summary.diagnostics_by_code["source_unsupported"] >= 1


def test_capture_service_summarizes_warning_tokens_and_warning_diagnostics(tmp_path):
    repository = EvidenceEventRepository(_config(tmp_path))
    service = EvidenceCaptureService(EvidenceEventService(repository), {"static": DiagnosticWarningImporter()})

    summary = service.capture(EvidenceCaptureRequest(source="static", decision_date="2026-07-02"))

    assert summary.warnings_count == 2
    assert summary.to_dict().get("warning_counts") == {
        "diagnostic:source_delayed": 1,
        "source_warning": 1,
    }


def test_capture_service_counts_source_advisory_once_not_per_event(tmp_path):
    repository = EvidenceEventRepository(_config(tmp_path))
    service = EvidenceCaptureService(EvidenceEventService(repository), {"static": AdvisoryImporter()})

    summary = service.capture(EvidenceCaptureRequest(source="static", decision_date="2026-07-02"))

    assert summary.warnings_count == 1
    assert summary.advisories_count == 1
    assert summary.advisory_counts == {"portfolio_alerts_chip_estimated:2330": 1}


def _explicit_request(
    *,
    captured_at: str = "2026-07-02T20:20:00+08:00",
    decision_at: str = "2026-07-02T20:10:00+08:00",
    as_of: str = "2026-07-02",
) -> EvidenceCaptureRequest:
    return EvidenceCaptureRequest(
        source="static",
        decision_date="2026-07-02",
        as_of=as_of,
        decision_at=decision_at,
        captured_at=captured_at,
        capture_mode="eod_research",
        dry_run=False,
        confirm=True,
    )


def test_explicit_capture_preserves_context_and_retry_capture_clock_is_idempotent(tmp_path):
    repository = EvidenceEventRepository(_config(tmp_path))
    service = EvidenceCaptureService(EvidenceEventService(repository), {"static": StaticImporter()})

    first = service.capture(_explicit_request())
    second = service.capture(
        _explicit_request(captured_at="2026-07-02T20:25:00+08:00")
    )

    assert first.temporal_status == "verified"
    assert first.capture_context_hash is not None
    assert first.capture_context_identity_hash is not None
    assert second.events_inserted == 0
    assert second.events_skipped_duplicate == 1
    event = repository.list_events()[0]
    context = event.metadata["capture_context"]
    assert context["decision_at"] == "2026-07-02T20:10:00+08:00"
    assert context["captured_at"] == "2026-07-02T20:20:00+08:00"
    assert capture_context_is_valid(context)
    assert event.metadata["source_availability"]["available_date"] == "2026-07-02"
    assert event.metadata["source_availability"]["capture_at_overrides_source_timestamp"] is False


def test_explicit_capture_merges_existing_source_availability_without_overwrite(tmp_path):
    repository = EvidenceEventRepository(_config(tmp_path))
    service = EvidenceCaptureService(
        EvidenceEventService(repository),
        {"source-custody": ExistingSourceAvailabilityImporter()},
    )
    request = _explicit_request()
    request = EvidenceCaptureRequest(
        source="source-custody",
        decision_date=request.decision_date,
        as_of=request.as_of,
        decision_at=request.decision_at,
        captured_at=request.captured_at,
        capture_mode=request.capture_mode,
        dry_run=False,
        confirm=True,
    )

    service.capture(request)

    event = repository.list_events()[0]
    source_availability = event.metadata["source_availability"]
    assert source_availability["available_date"] == "2026-07-02"
    assert source_availability["source_timestamp"] == "2026-07-02T09:00:00+08:00"
    assert source_availability["owner"] == "source-custody"
    assert source_availability["capture_at_overrides_source_timestamp"] is False


def test_changed_decision_or_as_of_cannot_merge_with_existing_event(tmp_path):
    repository = EvidenceEventRepository(_config(tmp_path))
    service = EvidenceCaptureService(EvidenceEventService(repository), {"static": StaticImporter()})

    service.capture(_explicit_request())
    changed_decision = service.capture(
        _explicit_request(decision_at="2026-07-02T20:11:00+08:00")
    )
    changed_as_of = service.capture(
        _explicit_request(as_of="2026-07-01")
    )

    assert changed_decision.events_inserted == 1
    assert changed_as_of.events_inserted == 1
    assert len(repository.list_events()) == 3


def test_tampered_persisted_capture_context_fails_closed(tmp_path):
    config = _config(tmp_path)
    repository = EvidenceEventRepository(config)
    service = EvidenceCaptureService(EvidenceEventService(repository), {"static": StaticImporter()})
    request = _explicit_request()
    service.capture(request)
    event = repository.list_events()[0]
    tampered = dict(event.metadata)
    tampered_context = dict(tampered["capture_context"])
    tampered_context["captured_at"] = "2026-07-02T20:25:00+08:00"
    tampered["capture_context"] = tampered_context
    with sqlite3.connect(config.db_file) as connection:
        connection.execute(
            "UPDATE evidence_events SET metadata_json = ? WHERE event_id = ?",
            (json.dumps(tampered, ensure_ascii=False, sort_keys=True), event.event_id),
        )
        connection.commit()

    summary = service.capture(request)

    assert summary.events_inserted == 0
    assert summary.events_skipped_duplicate == 0
    assert summary.events_failed == 1
    assert summary.diagnostics_by_code["event_record_failed"] == 1


def test_rehashed_but_mismatched_persisted_context_fails_closed(tmp_path):
    config = _config(tmp_path)
    repository = EvidenceEventRepository(config)
    service = EvidenceCaptureService(EvidenceEventService(repository), {"static": StaticImporter()})
    request = _explicit_request()
    service.capture(request)
    event = repository.list_events()[0]
    tampered = dict(event.metadata)
    tampered["capture_context"] = _explicit_request(
        decision_at="2026-07-02T20:11:00+08:00",
        captured_at="2026-07-02T20:25:00+08:00",
    ).capture_context
    with sqlite3.connect(config.db_file) as connection:
        connection.execute(
            "UPDATE evidence_events SET metadata_json = ? WHERE event_id = ?",
            (json.dumps(tampered, ensure_ascii=False, sort_keys=True), event.event_id),
        )
        connection.commit()

    summary = service.capture(request)

    assert summary.events_failed == 1
    assert summary.diagnostics_by_code["event_record_failed"] == 1


def test_date_only_capture_is_explicitly_unproven_without_context():
    request = EvidenceCaptureRequest(source="static", decision_date="2026-07-02")

    assert request.temporal_status == "temporal_precision_unproven"
    assert request.capture_context is None
    assert request.temporal_summary["preopen_authority"] is False


@pytest.mark.parametrize(
    ("kwargs", "message"),
    (
        (
            {
                "decision_date": "2026-07-02",
                "as_of": "2026-07-02",
                "decision_at": datetime.fromisoformat("2026-07-02T20:10:00+08:00"),
                "captured_at": datetime.fromisoformat("2026-07-02T20:05:00+08:00"),
            },
            "captured_at",
        ),
        (
            {
                "decision_date": "2026-07-02",
                "as_of": "2026-07-03",
                "decision_at": datetime.fromisoformat("2026-07-02T20:10:00+08:00"),
                "captured_at": datetime.fromisoformat("2026-07-02T20:20:00+08:00"),
            },
            "as_of",
        ),
        (
            {
                "decision_date": "2026-07-02",
                "capture_mode": "preopen_verified",
            },
            "capture_mode",
        ),
        (
            {
                "decision_date": "2026-07-02",
                "decision_at": datetime.fromisoformat("2026-07-02T08:10:00+08:00"),
                "captured_at": datetime.fromisoformat("2026-07-02T08:20:00+08:00"),
                "capture_mode": "eod_research",
            },
            "captured_at",
        ),
    ),
)
def test_capture_request_rejects_unproven_temporal_claims(kwargs, message):
    with pytest.raises(ValueError, match=message):
        EvidenceCaptureRequest(source="static", **kwargs)
