"""事件時鐘、角色與讀回信任根的實際隔離回歸。"""
from datetime import datetime, timedelta, timezone
import hashlib
from zoneinfo import ZoneInfo

import pytest

from app_module.evidence_event_dtos import EvidenceEvent, EvidenceEventType
from app_module.evidence_event_importer_dtos import EvidenceCaptureRequest
from app_module.evidence_event_repository import EvidenceEventRepository
from app_module.evidence_event_service import EvidenceEventService
from app_module.forward_daily_price_source_binding import ForwardDailyPriceSourceBinder
from app_module.forward_performance_service import ForwardPerformanceService, extract_event_decision_cutoff
from app_module.forward_source_observation import ForwardSourceObservationRecorder, verify_forward_source_observation_readback
from data_module.daily_price_qualification_binding import DailyPriceRevisionLedger, PinnedDailyPriceQualificationResolver, _canonical_bytes
from data_module.daily_price_source_bundle import publish_daily_price_source_bundle, load_daily_price_source_bundle
from tests.test_daily_price_publication_fetched_row_binding import _twse_fixture


def _context(cutoff):
    return EvidenceCaptureRequest(
        source="recommendation", decision_date=cutoff.astimezone(ZoneInfo('Asia/Taipei')).date(),
        decision_at=cutoff, as_of="2026-07-02", captured_at=cutoff + timedelta(minutes=1),
        capture_mode="research_only",
    ).capture_context


@pytest.mark.parametrize("change", ["missing", "conflict", "tamper", "wrong_day"])
def test_declared_metadata_does_not_grant_event_clock(change):
    cutoff = datetime(2026, 10, 22, 7, tzinfo=timezone.utc)
    meta = {"capture_context": _context(cutoff)}
    if change == "missing":
        meta = {"decision_cutoff": cutoff.isoformat()}
    elif change == "conflict":
        meta["decision_cutoff"] = (cutoff + timedelta(hours=1)).isoformat()
    elif change == "tamper":
        meta["capture_context"]["decision_at"] = (cutoff + timedelta(hours=1)).isoformat()
    event = EvidenceEvent(
        event_id="e", event_hash="sha256:" + "a" * 64, event_date="2026-07-02",
        decision_date="2026-10-21" if change == "wrong_day" else "2026-10-22",
        symbol="2330", event_type=EvidenceEventType.RECOMMENDATION_INCLUDED,
        event_family="recommendation", source_type="fixture", metadata=meta,
    )
    assert extract_event_decision_cutoff(event) is None


def test_real_publications_two_events_outcome_and_readback_are_isolated(tmp_path, monkeypatch):
    config, descriptor, _fetched = _twse_fixture(tmp_path, monkeypatch)
    (config.output_root / "scheduled/tpex_daily_price_sqlite_publication").mkdir(parents=True, exist_ok=True)
    repo = EvidenceEventRepository(config)
    repo.ensure_schema()
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=4)
    source_ref = publish_daily_price_source_bundle(
        output_root=config.output_root, data_root=config.data_root, database_path=config.db_file,
        quick_run_id="event-context-r8", completed_at=now.isoformat(), quick_status="passed",
        descriptors={"twse.mi_index.daily_price": descriptor},
    )
    bundle = load_daily_price_source_bundle(
        output_root=config.output_root, data_root=config.data_root, database_path=config.db_file,
        descriptor=source_ref,
    )
    payload = {"schema_version": "daily-price-qualification-binding.v1", "binding_id": "r8-fixture",
        "created_at": now.isoformat(), "decision": {
            "source_id": "twse.mi_index.daily_price", "decision_revision_id": "r8-source-acceptance",
            "parent_revision_id": None, "status": "accepted",
            "allowed_use_cases": ["forward_decision_baseline", "forward_outcome_evaluation"],
            "blockers": [], "license_evidence_ids": ["sha256:" + "a" * 64],
            "quality_evidence_ids": ["sha256:" + "b" * 64], "pit_evidence_ids": ["sha256:" + "c" * 64],
            "owner_role": "quant_data_architect", "reviewer_role": "operations_owner",
            "decided_at": (now - timedelta(hours=1)).isoformat(), "rollback_reference": "initial_decision",
        }}
    raw = _canonical_bytes(payload) + b"\n"
    path = tmp_path / "source-binding.json"
    path.write_bytes(raw)
    resolver = PinnedDailyPriceQualificationResolver(path, "sha256:" + hashlib.sha256(raw).hexdigest())
    ledger = DailyPriceRevisionLedger(output_root=config.output_root, data_root=config.data_root)
    assert ledger.scan_scheduled_publications() == 2
    binder = ForwardDailyPriceSourceBinder(
        output_root=config.output_root, data_root=config.data_root, database_path=config.db_file,
        bundle=bundle, revision_ledger=ledger, qualification_resolver=resolver,
        qualification_policy=resolver.build_policy(temporal_role="decision_baseline", cutoff_at=cutoff),
    )
    def writer(path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="") as stream:
            stream.write(text)

    observer = ForwardSourceObservationRecorder(
        output_root=config.output_root, db_path=config.db_file, run_id="20261023T010203123456Z",
        writer=writer,
        qualification_verifier=binder.verify_qualified_binding,
    )
    service = ForwardPerformanceService(config, repo, source_observer=observer, price_source_binder=binder)
    observer.begin_calculation()
    for number, hours in enumerate((2, 3)):
        decision = now + timedelta(hours=hours)
        event = EvidenceEventService(repo).record_event(
            event_date="2026-07-02", decision_date=decision.astimezone(ZoneInfo('Asia/Taipei')).date().isoformat(),
            symbol="2330", event_type=EvidenceEventType.RECOMMENDATION_INCLUDED,
            as_of_date="2026-07-02", available_date=decision.astimezone(ZoneInfo('Asia/Taipei')).date().isoformat(),
            event_family="recommendation", source_type="fixture",
            metadata={"capture_context": _context(decision), "fixture_event": number},
        )
        observer.begin_outcome(event_id=event.event_id, window_days=5)
        assert service._find_event_price("2330", event.event_date, data_as_of_date="2026-12-01", event=event) is not None
        ids = observer.end_outcome()
        observer.record_outcome(event_id=event.event_id, window_days=5, return_basis="fixture",
            outcome_status="pending", outcome_payload={"status": "pending"}, query_ids=ids)
    observer.begin_outcome(event_id="outcome", window_days=5)
    assert service._find_exact_official_outcome_price("2330", planned_date="2026-07-02", data_as_of_date="2026-12-01")[0] is not None
    ids = observer.end_outcome()
    observer.record_outcome(event_id="outcome", window_days=5, return_basis="fixture",
        outcome_status="pending", outcome_payload={"status": "pending"}, query_ids=ids)
    reference = observer.persist()
    readback = verify_forward_source_observation_readback(
        output_root=config.output_root, reference=reference, qualification_verifier=binder.verify_qualified_binding,
    )
    baseline = [query for query in readback["queries"] if query["purpose"] == "decision_baseline"]
    assert len(baseline) == 2
    bindings = [query["source_bindings"][0] for query in baseline]
    assert all(item["status"] == "source_qualified" and item["training_eligible"] is False for item in bindings)
    assert len({item["cutoff_at"] for item in bindings}) == 2
    assert len({item["qualification_context_id"] for item in bindings}) == 2
    outcome = next(query for query in readback["queries"] if query["purpose"] == "exact_official_target_price")
    assert outcome["source_bindings"][0]["temporal_role"] == "outcome_realization"
    forged = dict(bindings[0], cutoff_at=cutoff.isoformat())
    forged["qualification_proof_sha256"] = "sha256:" + hashlib.sha256(_canonical_bytes({k: v for k, v in forged.items() if k != "qualification_proof_sha256"})).hexdigest()
    assert not binder.verify_qualified_binding(forged)
    assert not binder.verify_qualified_binding({**bindings[0], "qualification_event_id": "another-event"})
    assert binder.bind_rows([{}], qualification_policy=binder.qualification_policy)[0]["reason_code"] == "event_decision_context_not_registered"
