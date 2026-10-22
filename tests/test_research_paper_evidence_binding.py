from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import app_module.journal_service as journal_service_module
from app_module.research_paper_evidence_binding import (
    CALENDAR_SOURCE_SCHEMA,
    CALENDAR_USE_ID,
    PROVIDER_ID,
    ResearchPaperEvidenceBindingError,
    ResearchPaperEvidenceBindingReader,
    _candidate,
    _decode_canonical_json,
    _decode_strict_json,
    _expected_acceptance_use,
)
from app_module.research_timeline_dtos import ResearchTimelineEntry
from app_module.dtos.decision_continuity_dtos import DecisionIdentity
from app_module.journal_service import JournalService
from app_module.paper_portfolio_snapshot_repository import (
    PaperPortfolioSnapshot,
    PaperPortfolioSnapshotReceipt,
    PaperPortfolioSnapshotRepository,
    _cash_seed_source_result_id,
)
from app_module.paper_trade_ledger import (
    PaperTradeFill,
    PaperTradeLedgerRepository,
    PaperTradeTransition,
)
from app_module.personal_paper_store_paths import PersonalPaperStorePaths
from app_module.research_paper_producer import (
    HumanConfirmedPaperIntent,
    ResearchPaperProducer,
    ResearchPaperProducerError,
    preview_research_paper_simulation,
    research_candidate_identity_sha256,
    verified_context_fingerprint_sha256,
)
from app_module.research_timeline_service import ResearchTimelineService
from app_module.strategy_paper_account_service import file_sha256
from tests.test_strategy_paper_account_binding import _create_account, _fixture_roots


EVENT_DATE = "2026-10-21"
CONFIRMED_AT = "2026-10-21T01:00:00+00:00"
AVAILABLE_AT = "2026-10-21T00:30:00+00:00"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass
class _PaperFixture:
    tmp_path: Path
    reader: ResearchPaperEvidenceBindingReader
    entry: ResearchTimelineEntry
    account_service: object
    personal_paths: object
    binding: object
    route: object
    paths: PersonalPaperStorePaths
    ledger: PaperTradeLedgerRepository
    timeline: ResearchTimelineService
    evidence_root: Path
    binding_path: Path
    expected_binding_sha256: str

    def rewrite_binding(self, mutator) -> None:
        document = json.loads(self.binding_path.read_text(encoding="utf-8"))
        mutator(document)
        raw = _canonical_bytes(document)
        self.binding_path.write_bytes(raw)
        self.expected_binding_sha256 = file_sha256(raw)
        self.reader = ResearchPaperEvidenceBindingReader(
            self.binding_path,
            self.expected_binding_sha256,
            self.timeline,
            self.account_service,
            self.personal_paths,
            protected_roots=(self.personal_paths.personal_root,),
        )


def _add_journal_entry_at(journal: JournalService, recorded_at: str) -> None:
    parsed = datetime.fromisoformat(recorded_at.replace("Z", "+00:00"))
    clock = SimpleNamespace(now=lambda _timezone=None: parsed)

    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(journal_service_module, "datetime", clock)
        journal.add_journal_entry(
            "Saved source research",
            stock_code="2330",
            source_type="manual_decision",
            decision_identity=DecisionIdentity(
                stock_code="2330",
                decision_date=EVENT_DATE,
                source_snapshot_id="fixture-research-original",
                source_snapshot_hash="sha256:" + "c" * 64,
            ),
        )


def _build_paper_fixture(
    tmp_path: Path,
    *,
    seed_date: str = EVENT_DATE,
    journal_recorded_at: str = EVENT_DATE + "T00:15:00+00:00",
) -> _PaperFixture:
    personal_paths, strategy_root, contract_root = _fixture_roots(tmp_path)
    account_service, manifest = _create_account(
        tmp_path,
        strategy_id="strategy-paper-evidence",
        strategy_version_id="strategy-paper-evidence-v1",
        roots=(personal_paths, strategy_root, contract_root),
    )
    binding = account_service.select_account(manifest["account_namespace"]).binding
    assert binding is not None
    selected = account_service.select_account(binding.account_namespace)
    assert selected.route is not None
    route = selected.route
    paths = PersonalPaperStorePaths.from_route(route, portfolio_id=binding.portfolio_id)
    ledger = PaperTradeLedgerRepository(
        paths.cost_ledger_db,
        route=route,
        personal_paths=personal_paths,
        portfolio_id=binding.portfolio_id,
    )
    snapshot_repo = PaperPortfolioSnapshotRepository(
        paths.state_db,
        route=route,
        personal_paths=personal_paths,
        portfolio_id=binding.portfolio_id,
    )
    seed_created_at = datetime.fromisoformat(
        seed_date + "T08:30:00+08:00"
    ).astimezone(timezone.utc).isoformat()
    seed = PaperPortfolioSnapshot(
        snapshot_id="fixture-cash-seed",
        portfolio_id=binding.portfolio_id,
        decision_date=seed_date,
        source_result_id=_cash_seed_source_result_id(binding.binding_sha256),
        cash=Decimal("500000"),
        total_value=Decimal("500000"),
        positions=(),
    )
    seed_receipt = PaperPortfolioSnapshotReceipt.account_cash_seed_for(
        seed,
        account_namespace=binding.account_namespace,
        binding_sha256=binding.binding_sha256,
        seed_created_at=seed_created_at,
    )
    snapshot_repo.append_account_cash_seed_once(seed, seed_receipt)

    journal = JournalService(SimpleNamespace(output_root=tmp_path / "journal"))
    _add_journal_entry_at(journal, journal_recorded_at)
    timeline = ResearchTimelineService(journal)
    entry = next(item for item in timeline.read().entries if item.kind == "manual")

    evidence_root = tmp_path / "external-evidence"
    evidence_root.mkdir()
    candidate_sha = research_candidate_identity_sha256(entry)
    cash_record = {
        "record_id": "cash-1",
        "kind": "cash_balance",
        "currency": "TWD",
        "amount": "500000",
        "available_at": AVAILABLE_AT,
        "observed_at": AVAILABLE_AT,
    }
    market_record = {
        "record_id": "mark-2330",
        "kind": "market_observation",
        "stock_code": "2330",
        "currency": "TWD",
        "event_date": EVENT_DATE,
        "mark_price": "50.00",
        "execution_reference_price": "50.00",
        "sector_id": "semiconductor",
        "available_at": AVAILABLE_AT,
        "observed_at": AVAILABLE_AT,
    }
    calendar = {
        "schema_version": CALENDAR_SOURCE_SCHEMA,
        "source_id": "fixture-official-calendar",
        "coverage_start": EVENT_DATE,
        "coverage_end": EVENT_DATE,
        "sessions": [EVENT_DATE],
    }
    raw_sources = {
        "cash": {"schema_version": "research-paper-source-records.v1", "source_id": "fixture-cash", "records": [cash_record]},
        "market": {"schema_version": "research-paper-source-records.v1", "source_id": "fixture-market", "records": [market_record]},
        "calendar": calendar,
    }
    references: dict[str, dict[str, str]] = {}
    for kind, source_doc in raw_sources.items():
        source_raw = _canonical_bytes(source_doc)
        source_path = evidence_root / f"{kind}-source.json"
        source_path.write_bytes(source_raw)
        source_sha = file_sha256(source_raw)
        record_id = "official-sessions" if kind == "calendar" else ("cash-1" if kind == "cash" else "mark-2330")
        use = _expected_acceptance_use(kind, source_sha, record_id)
        acceptance_doc = {
            "schema_version": "research-paper-source-use-acceptance.v1",
            "acceptance_id": f"accept-{kind}-1",
            "accepted_by": "fixture-human-reviewer",
            "accepted_at": "2026-10-21T00:45:00+00:00",
            "account_namespace": binding.account_namespace,
            "binding_sha256": binding.binding_sha256,
            "candidate_identity_sha256": candidate_sha,
            "event_date": EVENT_DATE,
            "currency": "TWD",
            "accepted_uses": [use],
        }
        acceptance_raw = _canonical_bytes(acceptance_doc)
        acceptance_path = evidence_root / f"{kind}-acceptance.json"
        acceptance_path.write_bytes(acceptance_raw)
        references[kind] = {
            "path": source_path.name,
            "sha256": source_sha,
            "record_id": record_id,
            "acceptance_path": acceptance_path.name,
            "acceptance_sha256": file_sha256(acceptance_raw),
            "acceptance_id": acceptance_doc["acceptance_id"],
        }
    binding_doc = {
        "schema_version": "research-paper-evidence-binding.v1",
        "candidate_identity_sha256": candidate_sha,
        "event_date": EVENT_DATE,
        "currency": "TWD",
        "account_namespace": binding.account_namespace,
        "binding_sha256": binding.binding_sha256,
        "account_manifest_sha256": file_sha256(
            (account_service.accounts_root / binding.account_namespace / "account_binding.json").read_bytes()
        ),
        "cash_source": references["cash"],
        "market_sources": [{"stock_code": "2330", **references["market"]}],
        "calendar_source": references["calendar"],
    }
    binding_raw = _canonical_bytes(binding_doc)
    binding_path = evidence_root / "binding.json"
    binding_path.write_bytes(binding_raw)
    expected_binding_sha256 = file_sha256(binding_raw)
    reader = ResearchPaperEvidenceBindingReader(
        binding_path,
        expected_binding_sha256,
        timeline,
        account_service,
        personal_paths,
        protected_roots=(personal_paths.personal_root,),
    )
    return _PaperFixture(
        tmp_path, reader, entry, account_service, personal_paths, binding, route,
        paths, ledger, timeline, evidence_root, binding_path, expected_binding_sha256,
    )


def test_canonical_evidence_json_rejects_duplicate_fields_and_float_values():
    with pytest.raises(ResearchPaperEvidenceBindingError):
        _decode_canonical_json(b'{"a":1,"a":2}', "test")
    with pytest.raises(ResearchPaperEvidenceBindingError):
        _decode_canonical_json(b'{"a":1.5}', "test")


def test_strict_json_accepts_pretty_manifest_bytes_but_rejects_ambiguous_values():
    pretty = b'{\n  "account_namespace": "acct-example",\n  "schema_version": "strategy-paper-account-binding.v1"\n}\n'
    assert _decode_strict_json(pretty, "account binding manifest") == {
        "account_namespace": "acct-example",
        "schema_version": "strategy-paper-account-binding.v1",
    }
    for raw in (b'{"a":1,"a":2}', b'{"a":1.5}', b'{"a":NaN}'):
        with pytest.raises(ResearchPaperEvidenceBindingError):
            _decode_strict_json(raw, "account binding manifest")


def test_reader_pins_original_pretty_manifest_bytes_and_rejects_tampering(tmp_path: Path):
    fixture = _build_paper_fixture(tmp_path)
    manifest_path = (
        fixture.account_service.accounts_root
        / fixture.binding.account_namespace
        / "account_binding.json"
    )
    original = manifest_path.read_bytes()
    assert b"\n" in original
    fixture.reader.preview(fixture.entry)

    manifest_path.write_bytes(original + b" ")
    with pytest.raises(ResearchPaperEvidenceBindingError, match="SHA-256"):
        fixture.reader.preview(fixture.entry)


def test_market_reference_must_name_the_current_symbol_and_reject_unknown_fields(tmp_path: Path):
    fixture = _build_paper_fixture(tmp_path)
    fixture.rewrite_binding(
        lambda document: document["market_sources"][0].update(stock_code="9999")
    )
    with pytest.raises(ResearchPaperEvidenceBindingError, match="exactly cover"):
        fixture.reader.preview(fixture.entry)

    other_fixture = _build_paper_fixture(tmp_path / "unknown-field")
    other_fixture.rewrite_binding(
        lambda document: document["market_sources"][0].update(untrusted_field="ignored")
    )
    with pytest.raises(ResearchPaperEvidenceBindingError, match="fields mismatch"):
        other_fixture.reader.preview(other_fixture.entry)


def test_pinned_reader_requires_exact_sha_and_refuses_path_escape(tmp_path: Path):
    source = tmp_path / "source.json"
    raw = b'{"records":[],"schema_version":"research-paper-source-records.v1","source_id":"cash-1"}'
    source.write_bytes(raw)
    expected = "sha256:" + sha256(raw).hexdigest()

    assert ResearchPaperEvidenceBindingReader._read_pinned_bytes(
        source, root=tmp_path, expected_sha256=expected
    ) == raw
    with pytest.raises(ResearchPaperEvidenceBindingError, match="SHA-256"):
        ResearchPaperEvidenceBindingReader._read_pinned_bytes(
            source, root=tmp_path, expected_sha256="sha256:" + "0" * 64
        )
    with pytest.raises(ResearchPaperEvidenceBindingError, match="escaped"):
        ResearchPaperEvidenceBindingReader._read_pinned_bytes(
            source, root=tmp_path / "nested", expected_sha256=expected
        )


def test_calendar_use_acceptance_names_exact_sessions_use_and_source_hash():
    assert _expected_acceptance_use(
        "calendar", "sha256:" + "a" * 64, "official-sessions"
    ) == {
        "source_sha256": "sha256:" + "a" * 64,
        "record_id": "official-sessions",
        "use_id": CALENDAR_USE_ID,
        "fields": ["sessions"],
    }
    assert CALENDAR_SOURCE_SCHEMA == "research-paper-official-calendar.v1"


@dataclass(frozen=True)
class _Reference:
    revision_id: str
    research_date: str


def test_candidate_uses_typed_revision_and_research_date_not_timeline_record_id():
    entry = ResearchTimelineEntry(
        kind="price",
        record_id="journal-action-id",
        recorded_at="2026-10-21T09:00:00+00:00",
        text="candidate",
        reference=_Reference("price-revision-7", "2026-10-20"),
        stock_code="2330",
        data_date="2026-10-19",
        source_identity="saved-source-identity",
        result_id="result-1",
    )

    candidate = _candidate(entry, "sha256:" + "b" * 64)

    assert candidate.revision_id == "price-revision-7"
    assert candidate.record_id == "journal-action-id"
    assert candidate.decision_date == "2026-10-20"
    assert candidate.provider_id == PROVIDER_ID


def test_candidate_keeps_missing_typed_revision_empty_instead_of_substituting_record_id():
    entry = ResearchTimelineEntry(
        kind="price",
        record_id="journal-action-id",
        recorded_at="2026-10-21T09:00:00+00:00",
        text="candidate",
        reference=object(),
        stock_code="2330",
        source_identity="saved-source-identity",
    )

    entry = ResearchTimelineEntry(
        kind="price",
        record_id=entry.record_id,
        recorded_at=entry.recorded_at,
        text=entry.text,
        reference=_Reference("", "2026-10-20"),
        stock_code=entry.stock_code,
        source_identity=entry.source_identity,
    )
    candidate = _candidate(entry, "sha256:" + "b" * 64)
    assert candidate.revision_id == ""
    assert candidate.record_id != candidate.revision_id


def _confirmed_intent(
    entry: ResearchTimelineEntry,
    context,
    *,
    confirmed_at: str = CONFIRMED_AT,
) -> HumanConfirmedPaperIntent:
    return HumanConfirmedPaperIntent(
        operation_id="fixture-operation-1",
        confirmation_id="fixture-confirmation-1",
        candidate_identity_sha256=research_candidate_identity_sha256(entry),
        account_namespace=context.binding.account_namespace,
        binding_sha256=context.binding.binding_sha256,
        evidence_fingerprint_sha256=verified_context_fingerprint_sha256(context),
        side="buy",
        quantity=1000,
        event_date=EVENT_DATE,
        confirmed_at=confirmed_at,
    )


def _reader_guard_intent(fixture: _PaperFixture) -> HumanConfirmedPaperIntent:
    return HumanConfirmedPaperIntent(
        operation_id="reader-guard-operation",
        confirmation_id="reader-guard-confirmation",
        candidate_identity_sha256=research_candidate_identity_sha256(fixture.entry),
        account_namespace=fixture.binding.account_namespace,
        binding_sha256=fixture.binding.binding_sha256,
        evidence_fingerprint_sha256="sha256:" + "d" * 64,
        side="buy",
        quantity=1000,
        event_date=EVENT_DATE,
        confirmed_at=CONFIRMED_AT,
    )


def test_real_timeline_account_seed_and_sources_preview_produce_reopen_and_retry(tmp_path: Path):
    fixture = _build_paper_fixture(tmp_path)
    context = fixture.reader.preview(fixture.entry)
    assert context.cash.source_id == "fixture-cash"
    assert context.cash.source_sha256 == file_sha256(
        (fixture.evidence_root / "cash-source.json").read_bytes()
    )
    assert context.cash.use_acceptance_sha256 == file_sha256(
        (fixture.evidence_root / "cash-acceptance.json").read_bytes()
    )
    assert [(item.stock_code, item.mark_price, item.execution_reference_price) for item in context.marks] == [
        ("2330", Decimal("50.00"), Decimal("50.00"))
    ]
    assert context.policy_use_id == "paper_policy_default@v1"
    assert context.cost_use_id == "taiwan_paper_cost@v1"
    assert (
        context.cost_commission_bp_per_side,
        context.cost_slippage_bp_per_side,
        context.cost_sell_tax_bp,
        context.cost_minimum_fee,
    ) == (15, 10, 30, Decimal("20.00"))
    assert context.binding.account_namespace == fixture.binding.account_namespace
    intent = _confirmed_intent(fixture.entry, context)
    preview_fill, preview_transition = preview_research_paper_simulation(
        fixture.entry, intent, context
    )
    clock = lambda: datetime(2026, 10, 21, 1, 1, tzinfo=timezone.utc)
    result = ResearchPaperProducer(
        evidence_provider=fixture.reader, ledger=fixture.ledger, clock=clock
    ).produce(fixture.entry, intent)
    assert result.fill == preview_fill
    assert result.transition == preview_transition
    assert preview_fill.reference_price == Decimal("50.00")
    assert preview_fill.fill_price == Decimal("50.05")
    assert preview_fill.gross_amount == Decimal("50050.00")
    assert preview_fill.commission == Decimal("75.08")
    assert preview_fill.slippage_cost == Decimal("50.00")
    assert result.return_entry == fixture.entry
    assert result.append.status == "appended"
    with pytest.raises(ResearchPaperEvidenceBindingError, match="external cash amount"):
        fixture.reader.preview(fixture.entry)

    fresh_reader = ResearchPaperEvidenceBindingReader(
        fixture.binding_path,
        fixture.expected_binding_sha256,
        fixture.timeline,
        fixture.account_service,
        fixture.personal_paths,
        protected_roots=(fixture.personal_paths.personal_root,),
    )
    fresh_ledger = PaperTradeLedgerRepository(
        fixture.paths.cost_ledger_db,
        route=fixture.route,
        personal_paths=fixture.personal_paths,
        portfolio_id=fixture.binding.portfolio_id,
    )
    reopened = fresh_ledger.read_exact_daily_operation(
        intent.operation_id,
        portfolio_id=fixture.binding.portfolio_id,
        event_date=EVENT_DATE,
    )
    assert reopened.ordered_fills == (preview_fill,)
    assert reopened.transition == preview_transition
    assert fresh_reader.verify(fixture.entry, intent).ledger_rowset_hash == context.ledger_rowset_hash

    retry = ResearchPaperProducer(
        evidence_provider=fresh_reader, ledger=fresh_ledger, clock=clock
    ).produce(fixture.entry, intent)
    assert retry.append.status == "already_committed"
    assert retry.fill == preview_fill
    assert retry.return_entry == fixture.entry


def test_cash_seed_created_after_confirmation_is_rejected(tmp_path: Path):
    fixture = _build_paper_fixture(tmp_path)
    context = fixture.reader.preview(fixture.entry)
    intent = _confirmed_intent(
        fixture.entry,
        context,
        confirmed_at="2026-10-21T00:15:00+00:00",
    )

    with pytest.raises(ResearchPaperEvidenceBindingError, match="after human confirmation"):
        fixture.reader.verify(fixture.entry, intent)


def test_saved_research_recorded_after_confirmation_is_rejected(tmp_path: Path):
    fixture = _build_paper_fixture(
        tmp_path,
        journal_recorded_at="2026-10-21T01:15:00+00:00",
    )

    with pytest.raises(ResearchPaperEvidenceBindingError, match="recorded after human confirmation"):
        fixture.reader.verify(fixture.entry, _reader_guard_intent(fixture))


def test_saved_research_naive_recorded_at_is_rejected(tmp_path: Path):
    fixture = _build_paper_fixture(
        tmp_path,
        journal_recorded_at="2026-10-21T00:15:00",
    )

    with pytest.raises(ResearchPaperEvidenceBindingError, match="timezone-aware"):
        fixture.reader.verify(fixture.entry, _reader_guard_intent(fixture))


def test_future_ledger_transition_cannot_establish_current_prestate(tmp_path: Path):
    fixture = _build_paper_fixture(tmp_path)
    future_fill = PaperTradeFill(
        fill_id="future-cancelled-fill",
        order_id="future-cancelled-order",
        portfolio_id=fixture.binding.portfolio_id,
        event_date="2026-10-22",
        stock_code="2330",
        side="buy",
        requested_quantity=1000,
        filled_quantity=0,
        reference_price=Decimal("50.00"),
        fill_price=None,
        commission=Decimal("0.00"),
        tax=Decimal("0.00"),
        slippage_cost=Decimal("0.00"),
        turnover_bp=0,
        execution_gap_bp=None,
        status="cancelled",
        source_event_id="future-cancelled-event",
    )
    future_transition = PaperTradeTransition(
        transition_id="future-cancelled-transition",
        batch_id="future-cancelled-batch",
        portfolio_id=fixture.binding.portfolio_id,
        event_date="2026-10-22",
        fill_ids=(future_fill.fill_id,),
        pre_cash=Decimal("500000.00"),
        pre_total_value=Decimal("500000.00"),
        post_cash=Decimal("500000.00"),
        post_total_value=Decimal("500000.00"),
        common_nav=Decimal("500000.00"),
        common_prices={"2330": Decimal("50.00")},
        pre_positions={},
        post_positions={},
    )
    fixture.ledger.append_daily_operation(
        operation_id="future-cancelled-operation",
        portfolio_id=fixture.binding.portfolio_id,
        event_date="2026-10-22",
        expected_rowset_hash=fixture.ledger.rowset_hash(),
        fills=(future_fill,),
        transition=future_transition,
    )

    with pytest.raises(ResearchPaperEvidenceBindingError, match="rows after the confirmed event date"):
        fixture.reader.preview(fixture.entry)


def test_cash_record_must_equal_reconstructed_seed_balance(tmp_path: Path):
    fixture = _build_paper_fixture(tmp_path)
    cash_source = fixture.evidence_root / "cash-source.json"
    source = json.loads(cash_source.read_text(encoding="utf-8"))
    source["records"][0]["amount"] = "499999"
    source_raw = _canonical_bytes(source)
    cash_source.write_bytes(source_raw)
    source_hash = file_sha256(source_raw)
    acceptance_path = fixture.evidence_root / "cash-acceptance.json"
    acceptance = json.loads(acceptance_path.read_text(encoding="utf-8"))
    acceptance["accepted_uses"][0]["source_sha256"] = source_hash
    acceptance_raw = _canonical_bytes(acceptance)
    acceptance_path.write_bytes(acceptance_raw)

    def update_binding(binding_doc):
        binding_doc["cash_source"]["sha256"] = source_hash
        binding_doc["cash_source"]["acceptance_sha256"] = file_sha256(acceptance_raw)

    fixture.rewrite_binding(update_binding)
    with pytest.raises(ResearchPaperEvidenceBindingError, match="external cash amount"):
        fixture.reader.preview(fixture.entry)


def test_each_use_acceptance_is_required_even_with_pinned_source_bytes(tmp_path: Path):
    fixture = _build_paper_fixture(tmp_path)
    acceptance_path = fixture.evidence_root / "market-acceptance.json"
    acceptance = json.loads(acceptance_path.read_text(encoding="utf-8"))
    acceptance["accepted_uses"] = []
    acceptance_raw = _canonical_bytes(acceptance)
    acceptance_path.write_bytes(acceptance_raw)

    def update_binding(binding_doc):
        binding_doc["market_sources"][0]["acceptance_sha256"] = file_sha256(acceptance_raw)

    fixture.rewrite_binding(update_binding)
    with pytest.raises(ResearchPaperEvidenceBindingError, match="not explicitly accepted"):
        fixture.reader.preview(fixture.entry)


def test_changed_calendar_bytes_fail_against_external_source_sha(tmp_path: Path):
    fixture = _build_paper_fixture(tmp_path)
    source_path = fixture.evidence_root / "calendar-source.json"
    source_path.write_bytes(source_path.read_bytes() + b" ")
    with pytest.raises(ResearchPaperEvidenceBindingError, match="SHA-256 mismatch"):
        fixture.reader.preview(fixture.entry)


def test_market_mark_date_must_match_confirmed_event_date(tmp_path: Path):
    fixture = _build_paper_fixture(tmp_path)
    market_path = fixture.evidence_root / "market-source.json"
    market = json.loads(market_path.read_text(encoding="utf-8"))
    market["records"][0]["event_date"] = "2026-10-20"
    market_raw = _canonical_bytes(market)
    market_path.write_bytes(market_raw)
    market_hash = file_sha256(market_raw)
    acceptance_path = fixture.evidence_root / "market-acceptance.json"
    acceptance = json.loads(acceptance_path.read_text(encoding="utf-8"))
    acceptance["accepted_uses"][0]["source_sha256"] = market_hash
    acceptance_raw = _canonical_bytes(acceptance)
    acceptance_path.write_bytes(acceptance_raw)

    def update_binding(binding_doc):
        reference = binding_doc["market_sources"][0]
        reference["sha256"] = market_hash
        reference["acceptance_sha256"] = file_sha256(acceptance_raw)

    fixture.rewrite_binding(update_binding)
    with pytest.raises(ResearchPaperEvidenceBindingError, match="identity/date/currency"):
        fixture.reader.preview(fixture.entry)


def test_confirmed_prestate_rejects_later_rowset_mutation(tmp_path: Path):
    fixture = _build_paper_fixture(tmp_path, seed_date="2026-10-20")
    context = fixture.reader.preview(fixture.entry)
    intent = _confirmed_intent(fixture.entry, context)
    fill = PaperTradeFill(
        fill_id="unrelated-prior-fill",
        order_id="unrelated-prior-order",
        portfolio_id=fixture.binding.portfolio_id,
        event_date="2026-10-20",
        stock_code="2330",
        side="buy",
        requested_quantity=1000,
        filled_quantity=0,
        reference_price=Decimal("50.00"),
        fill_price=None,
        commission=Decimal("0.00"),
        tax=Decimal("0.00"),
        slippage_cost=Decimal("0.00"),
        turnover_bp=0,
        execution_gap_bp=None,
        status="cancelled",
        source_event_id="unrelated-prior-event",
    )
    transition = PaperTradeTransition(
        transition_id="unrelated-prior-transition",
        batch_id="unrelated-prior-batch",
        portfolio_id=fixture.binding.portfolio_id,
        event_date="2026-10-20",
        fill_ids=(fill.fill_id,),
        pre_cash=Decimal("500000.00"),
        pre_total_value=Decimal("500000.00"),
        post_cash=Decimal("500000.00"),
        post_total_value=Decimal("500000.00"),
        common_nav=Decimal("500000.00"),
        common_prices={"2330": Decimal("50.00")},
        pre_positions={},
        post_positions={},
    )
    fixture.ledger.append_daily_operation(
        operation_id="unrelated-prior-operation",
        portfolio_id=fixture.binding.portfolio_id,
        event_date="2026-10-20",
        expected_rowset_hash=fixture.ledger.rowset_hash(),
        fills=(fill,),
        transition=transition,
    )
    with pytest.raises(ResearchPaperProducerError, match="fingerprint"):
        ResearchPaperProducer(
            evidence_provider=fixture.reader,
            ledger=fixture.ledger,
            clock=lambda: datetime(2026, 10, 21, 1, 1, tzinfo=timezone.utc),
        ).produce(fixture.entry, intent)


def test_retry_refuses_any_rowset_change_after_confirmed_operation(tmp_path: Path):
    fixture = _build_paper_fixture(tmp_path)
    context = fixture.reader.preview(fixture.entry)
    intent = _confirmed_intent(fixture.entry, context)
    result = ResearchPaperProducer(
        evidence_provider=fixture.reader,
        ledger=fixture.ledger,
        clock=lambda: datetime(2026, 10, 21, 1, 1, tzinfo=timezone.utc),
    ).produce(fixture.entry, intent)
    current = fixture.ledger.read_rowset_snapshot(portfolio_id=fixture.binding.portfolio_id)
    later_fill = PaperTradeFill(
        fill_id="later-cancelled-fill",
        order_id="later-cancelled-order",
        portfolio_id=fixture.binding.portfolio_id,
        event_date="2026-10-22",
        stock_code="2330",
        side="buy",
        requested_quantity=1000,
        filled_quantity=0,
        reference_price=Decimal("50.00"),
        fill_price=None,
        commission=Decimal("0.00"),
        tax=Decimal("0.00"),
        slippage_cost=Decimal("0.00"),
        turnover_bp=0,
        execution_gap_bp=None,
        status="cancelled",
        source_event_id="later-cancelled-event",
    )
    later_nav = result.transition.post_total_value
    later_transition = PaperTradeTransition(
        transition_id="later-cancelled-transition",
        batch_id="later-cancelled-batch",
        portfolio_id=fixture.binding.portfolio_id,
        event_date="2026-10-22",
        fill_ids=(later_fill.fill_id,),
        pre_cash=result.transition.post_cash,
        pre_total_value=later_nav,
        post_cash=result.transition.post_cash,
        post_total_value=later_nav,
        common_nav=later_nav,
        common_prices={"2330": Decimal("50.00")},
        pre_positions={"2330": 1000},
        post_positions={"2330": 1000},
    )
    fixture.ledger.append_daily_operation(
        operation_id="later-cancelled-operation",
        portfolio_id=fixture.binding.portfolio_id,
        event_date="2026-10-22",
        expected_rowset_hash=current.rowset_hash,
        fills=(later_fill,),
        transition=later_transition,
    )
    with pytest.raises(ResearchPaperEvidenceBindingError, match="ledger contains rows after the confirmed event date"):
        fixture.reader.verify(fixture.entry, intent)
