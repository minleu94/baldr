"""隔離驗證保存研究 Paper producer；所有檔案僅位於 pytest tmp_path。"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

import pytest

from app_module.dtos.portfolio_dtos import JournalEntryDTO
from app_module.dtos.decision_continuity_dtos import DecisionIdentity
from app_module.paper_portfolio_policy import PaperPortfolioPolicyConfig
from app_module.paper_trade_ledger import (
    PaperTradeFill,
    PaperTradeLedgerRepository,
    PaperTradeTransition,
)
from app_module.personal_data_paths import PersonalDataPaths
from app_module.personal_paper_store_paths import PersonalPaperStorePaths
from app_module.personal_store_routes import (
    PersonalStoreDomain,
    PersonalStoreMode,
    StoreIdentity,
    select_personal_store_route,
)
from app_module.research_paper_producer import (
    CASH_USE_ID,
    MARK_USE_ID,
    HumanConfirmedPaperIntent,
    PaperCashEvidence,
    PaperMarketEvidence,
    ResearchPaperProducer,
    ResearchPaperProducerError,
    VerifiedPaperContext,
    VerifiedResearchCandidate,
    research_candidate_identity_sha256,
    verified_context_fingerprint_sha256,
)
from app_module.research_timeline_dtos import ResearchTimelineEntry
from app_module.strategy_paper_account_service import StrategyPaperAccountBinding


EVENT_DATE = "2026-10-21"
CONFIRMED_AT = "2026-10-21T04:59:00+00:00"
TEST_NOW = datetime(2026, 10, 21, 5, 0, tzinfo=timezone.utc)
SHA_A = "sha256:" + "a" * 64
SHA_B = "sha256:" + "b" * 64
SHA_C = "sha256:" + "c" * 64
_BINDING_MANIFEST = StrategyPaperAccountBinding.create_manifest_payload(
    strategy_version_id="strategy-v1",
    strategy_id="strategy",
    strategy_version="1",
    strategy_artifact_sha256=SHA_A,
    params_sha256=SHA_A,
    config_sha256=SHA_A,
    source_run_id="run-1",
    policy_id="paper_policy_default",
    policy_version="v1",
    policy_sha256=SHA_B,
    cost_model_id="taiwan_paper_cost",
    cost_model_version="v1",
    cost_model_sha256=SHA_C,
    benchmark_id="benchmark-v1",
    benchmark_version="1",
    benchmark_sha256=SHA_A,
    start_date=EVENT_DATE,
    initial_capital="500000",
    max_positions=8,
)
BINDING = StrategyPaperAccountBinding.from_manifest(_BINDING_MANIFEST)
NAMESPACE = BINDING.account_namespace


class Provider:
    def __init__(self, context: VerifiedPaperContext) -> None:
        self.context = context
        self.seen_entry: ResearchTimelineEntry | None = None

    def verify(self, entry: ResearchTimelineEntry, intent: HumanConfirmedPaperIntent) -> VerifiedPaperContext:
        self.seen_entry = entry
        return self.context


def producer_for(provider: Provider | None, ledger: PaperTradeLedgerRepository) -> ResearchPaperProducer:
    return ResearchPaperProducer(evidence_provider=provider, ledger=ledger, clock=lambda: TEST_NOW)


def setup(tmp_path: Path, *, cash: Decimal = Decimal("500000")):
    paths = PersonalDataPaths(tmp_path / "market", tmp_path / "legacy", tmp_path / "personal")
    route = select_personal_store_route(
        domain=PersonalStoreDomain.PAPER,
        mode=PersonalStoreMode.PERSONAL,
        identity=StoreIdentity(NAMESPACE),
        personal_paths=paths,
        paper_account_namespace=NAMESPACE,
    )
    paper_paths = PersonalPaperStorePaths.from_route(route, portfolio_id=NAMESPACE)
    ledger = PaperTradeLedgerRepository(
        paper_paths.cost_ledger_db,
        route=route,
        personal_paths=paths,
        portfolio_id=NAMESPACE,
    )
    entry = ResearchTimelineEntry(
        kind="manual",
        record_id="journal-revision-1",
        recorded_at="2026-10-21T04:30:00+00:00",
        text="人工研究判斷",
        reference=JournalEntryDTO(
            journal_id="journal-1",
            portfolio_id="research",
            body="人工研究判斷",
            stock_code="2330",
            source_type="saved-research",
            source_id="result-1",
            source_snapshot_hash="source-hash-1",
            created_at="2026-10-21T04:30:00+00:00",
            revision_id="journal-revision-1",
            decision_identity=DecisionIdentity(
                result_id="result-1",
                stock_code="2330",
                source_snapshot_hash="source-identity-1",
                decision_date=EVENT_DATE,
            ),
        ),
        stock_code="2330",
        source_identity="saved-source-identity-1",
        result_id="result-1",
    )
    candidate = VerifiedResearchCandidate(
        identity_sha256=research_candidate_identity_sha256(entry),
        result_id=entry.result_id,
        record_id=entry.record_id,
        revision_id=entry.reference.revision_id,
        stock_code=entry.stock_code,
        decision_date=EVENT_DATE,
        source_identity=entry.source_identity,
        source_sha256=SHA_B,
        provider_id="fixture-research-reader-v1",
    )
    binding = BINDING
    cash_evidence = PaperCashEvidence(
        amount=cash,
        currency="TWD",
        source_id="owner-cash-source-v1",
        source_sha256=SHA_B,
        use_id=CASH_USE_ID,
        use_acceptance_sha256=SHA_C,
        account_namespace=NAMESPACE,
        binding_sha256=BINDING.binding_sha256,
        available_at="2026-10-21T04:00:00+00:00",
        observed_at="2026-10-21T04:58:00+00:00",
    )
    market = PaperMarketEvidence(
        stock_code="2330",
        currency="TWD",
        mark_price=Decimal("10"),
        execution_reference_price=Decimal("10"),
        source_id="owner-market-source-v1",
        source_sha256=SHA_C,
        use_id=MARK_USE_ID,
        use_acceptance_sha256=SHA_B,
        account_namespace=NAMESPACE,
        binding_sha256=BINDING.binding_sha256,
        event_date=EVENT_DATE,
        available_at="2026-10-21T04:58:00+00:00",
        observed_at="2026-10-21T04:58:30+00:00",
    )
    context = VerifiedPaperContext(
        candidate=candidate,
        binding=binding,
        account_manifest_sha256=SHA_C,
        policy_use_id="paper_policy_default@v1",
        policy_artifact_sha256=SHA_B,
        cost_use_id="taiwan_paper_cost@v1",
        cost_artifact_sha256=SHA_C,
        cost_commission_bp_per_side=15,
        cost_slippage_bp_per_side=10,
        cost_sell_tax_bp=30,
        cost_minimum_fee=Decimal("20.00"),
        slippage_model_id="fixed_bps",
        slippage_model_version="v1",
        currency="TWD",
        policy=PaperPortfolioPolicyConfig(initial_capital=Decimal("500000")),
        cash=cash_evidence,
        marks=(market,),
        positions={},
        sector_by_symbol={"2330": "semiconductor"},
        weekly_turnover_used_bp=0,
        trading_days_since_last_trade=5,
        ledger_rowset_hash=ledger.rowset_hash(),
        provider_id="fixture-provider-v1",
    )
    intent = intent_for(entry, context)
    return paths, route, paper_paths, ledger, entry, context, intent


def intent_for(
    entry: ResearchTimelineEntry,
    context: VerifiedPaperContext,
    *,
    operation_id: str = "paper-op-1",
    quantity: int = 2000,
    side: str = "buy",
) -> HumanConfirmedPaperIntent:
    return HumanConfirmedPaperIntent(
        operation_id=operation_id,
        confirmation_id="manual-confirmation-1",
        candidate_identity_sha256=research_candidate_identity_sha256(entry),
        account_namespace=context.binding.account_namespace,
        binding_sha256=context.binding.binding_sha256,
        evidence_fingerprint_sha256=verified_context_fingerprint_sha256(context),
        side=side,
        quantity=quantity,
        event_date=EVENT_DATE,
        confirmed_at=CONFIRMED_AT,
    )


def test_positive_append_reopen_and_return_exact_research_entry(tmp_path: Path) -> None:
    _, _, _, ledger, entry, context, intent = setup(tmp_path)
    provider = Provider(context)
    result = producer_for(provider, ledger).produce(entry, intent)

    assert result.status == "appended"
    assert result.return_entry is entry
    assert provider.seen_entry is entry
    assert result.fill.source_type == "paper_research_confirmed_v1"
    assert result.fill.research_only is True
    assert result.fill.broker_order_allowed is False
    assert result.fill.auto_rebalance_allowed is False
    assert result.fill.reference_price == Decimal("10")
    assert result.fill.fill_price == Decimal("10.01")
    assert result.fill.commission == Decimal("30.03")
    assert result.fill.tax == Decimal("0.00")
    assert result.fill.slippage_cost == Decimal("20.00")
    assert result.fill.turnover_bp == 400
    assert result.transition.post_cash == Decimal("479949.97")
    assert result.transition.post_total_value == Decimal("499949.97")
    lineage = json.loads(result.fill.override_reason or "{}")
    assert lineage["schema_version"] == "research-paper-confirmed-lineage.v1"
    assert lineage["candidate"]["identity_sha256"] == intent.candidate_identity_sha256
    assert lineage["cash"]["source_sha256"] == context.cash.source_sha256
    assert lineage["currency"] == "TWD"
    assert lineage["cost"]["commission_bp_per_side"] == 15
    assert lineage["cost"]["slippage_bp_per_side"] == 10
    assert lineage["cost"]["sell_tax_bp"] == 30
    assert lineage["cost"]["minimum_fee"] == "20.00"
    assert lineage["cost"]["slippage_model"] == "fixed_bps.v1"
    assert ledger.read_exact_daily_operation(
        intent.operation_id,
        portfolio_id=NAMESPACE,
        event_date=EVENT_DATE,
    ).ordered_fills == (result.fill,)


def test_same_intent_is_idempotent_and_different_same_day_intent_is_rejected(tmp_path: Path) -> None:
    _, _, _, ledger, entry, context, intent = setup(tmp_path)
    producer = producer_for(Provider(context), ledger)
    first = producer.produce(entry, intent)
    retry = producer.produce(entry, intent)
    assert retry.status == "already_committed"
    assert retry.fill == first.fill
    assert ledger.list_transitions(portfolio_id=NAMESPACE) == (first.transition,)

    updated_context = replace(
        context,
        ledger_rowset_hash=ledger.rowset_hash(),
        cash=replace(context.cash, amount=first.transition.post_cash),
        positions={"2330": intent.quantity},
    )
    next_intent = intent_for(entry, updated_context, operation_id="paper-op-2")
    with pytest.raises(ValueError, match="ledger window is not empty"):
        producer_for(Provider(updated_context), ledger).produce(entry, next_intent)
    assert ledger.list(portfolio_id=NAMESPACE) == (first.fill,)


def test_sector_cap_is_computed_from_confirmed_post_trade_positions(tmp_path: Path) -> None:
    _, _, _, ledger, entry, context, _ = setup(tmp_path)
    candidate_market = context.marks[0]
    held_market = replace(candidate_market, stock_code="1234")
    context = replace(
        context,
        cash=replace(context.cash, amount=Decimal("350000")),
        marks=(candidate_market, held_market),
        positions={"1234": 15000},
        sector_by_symbol={"1234": "semiconductor", "2330": "semiconductor"},
    )
    intent = intent_for(entry, context, quantity=1000)

    with pytest.raises(ValueError, match="sector_cap_exceeded"):
        producer_for(Provider(context), ledger).produce(entry, intent)
    assert ledger.list(portfolio_id=NAMESPACE) == ()


def test_revision_comes_from_typed_reference_not_timeline_record_key(tmp_path: Path) -> None:
    _, _, _, ledger, original_entry, context, _ = setup(tmp_path)
    entry = replace(original_entry, record_id="timeline-key-not-revision")
    candidate = replace(
        context.candidate,
        identity_sha256=research_candidate_identity_sha256(entry),
        record_id=entry.record_id,
        revision_id=entry.reference.revision_id,
    )
    context = replace(context, candidate=candidate)
    intent = intent_for(entry, context)
    result = producer_for(Provider(context), ledger).produce(entry, intent)
    assert result.status == "appended"
    assert json.loads(result.fill.override_reason or "{}")["candidate"]["revision_id"] == "journal-revision-1"


def test_cash_must_be_same_day_and_context_mappings_are_copied(tmp_path: Path) -> None:
    _, _, _, ledger, entry, context, _ = setup(tmp_path)
    mutable_positions = {"2330": 0}
    context = replace(context, positions=mutable_positions)
    mutable_positions["2330"] = 2000
    assert context.positions["2330"] == 0

    old_cash = replace(
        context.cash,
        available_at="2026-10-20T04:00:00+00:00",
        observed_at="2026-10-20T04:58:00+00:00",
    )
    old_context = replace(context, cash=old_cash)
    intent = intent_for(entry, old_context)
    with pytest.raises(ResearchPaperProducerError, match="event date"):
        producer_for(Provider(old_context), ledger).produce(entry, intent)
    assert ledger.list(portfolio_id=NAMESPACE) == ()

    old_mark = replace(
        context.marks[0],
        available_at="2026-10-20T04:00:00+00:00",
        observed_at="2026-10-20T04:58:00+00:00",
    )
    old_mark_context = replace(context, marks=(old_mark,))
    old_mark_intent = intent_for(entry, old_mark_context)
    with pytest.raises(ResearchPaperProducerError, match="same-day mark timestamps"):
        producer_for(Provider(old_mark_context), ledger).produce(entry, old_mark_intent)


def test_missing_provider_identity_mismatch_and_missing_mark_fail_closed(tmp_path: Path) -> None:
    _, _, _, ledger, entry, context, intent = setup(tmp_path)
    with pytest.raises(ResearchPaperProducerError, match="provider is not configured"):
        producer_for(None, ledger).produce(entry, intent)

    mismatched = replace(intent, candidate_identity_sha256=SHA_B)
    with pytest.raises(ResearchPaperProducerError, match="candidate identity mismatch"):
        producer_for(Provider(context), ledger).produce(entry, mismatched)

    no_mark = replace(context, marks=())
    no_mark_intent = intent_for(entry, no_mark)
    with pytest.raises(ResearchPaperProducerError, match="mark evidence is missing"):
        producer_for(Provider(no_mark), ledger).produce(entry, no_mark_intent)
    assert ledger.list(portfolio_id=NAMESPACE) == ()


def test_confirmation_cannot_be_in_the_future_of_utc_clock(tmp_path: Path) -> None:
    _, _, _, ledger, entry, context, intent = setup(tmp_path)
    future_intent = replace(intent, confirmed_at="2026-10-21T05:01:00+00:00")
    with pytest.raises(ResearchPaperProducerError, match="cannot be in the future"):
        producer_for(Provider(context), ledger).produce(entry, future_intent)
    assert ledger.list(portfolio_id=NAMESPACE) == ()


def test_account_policy_version_and_currency_mismatch_fail_closed(tmp_path: Path) -> None:
    _, _, _, ledger, entry, context, intent = setup(tmp_path)
    wrong_cost = replace(context, cost_artifact_sha256=SHA_B)
    wrong_cost_intent = intent_for(entry, wrong_cost)
    with pytest.raises(ResearchPaperProducerError, match="version mismatch"):
        producer_for(Provider(wrong_cost), ledger).produce(entry, wrong_cost_intent)

    with pytest.raises(ValueError, match="currency"):
        replace(context, currency="USD")
    assert ledger.list(portfolio_id=NAMESPACE) == ()


def test_insufficient_cash_and_non_decimal_evidence_do_not_write(tmp_path: Path) -> None:
    _, _, _, ledger, entry, context, _ = setup(tmp_path, cash=Decimal("15000"))
    intent = intent_for(entry, context)
    with pytest.raises(ResearchPaperProducerError, match="cash is insufficient"):
        producer_for(Provider(context), ledger).produce(entry, intent)
    assert ledger.list(portfolio_id=NAMESPACE) == ()

    with pytest.raises(ValueError, match="finite Decimal"):
        replace(context.cash, amount=15000.0)  # type: ignore[arg-type]


def test_ledger_failure_rolls_back_fill_when_transition_identity_collides(tmp_path: Path) -> None:
    _, _, _, ledger, entry, context, intent = setup(tmp_path)
    prior_fill = PaperTradeFill(
        fill_id="prior-fill",
        order_id="prior-order",
        portfolio_id=NAMESPACE,
        event_date="2026-10-20",
        stock_code="2330",
        side="buy",
        requested_quantity=1000,
        filled_quantity=0,
        reference_price=Decimal("10"),
        fill_price=None,
        commission=Decimal("0"),
        tax=Decimal("0"),
        slippage_cost=Decimal("0"),
        turnover_bp=0,
        execution_gap_bp=None,
        status="cancelled",
        source_event_id="prior-source-event",
    )
    collision_transition = PaperTradeTransition(
        transition_id="research-paper-transition-v1:" + intent.operation_id,
        batch_id="prior-batch",
        portfolio_id=NAMESPACE,
        event_date="2026-10-20",
        fill_ids=(prior_fill.fill_id,),
        pre_cash=Decimal("500000"),
        pre_total_value=Decimal("500000"),
        post_cash=Decimal("500000"),
        post_total_value=Decimal("500000"),
        common_nav=Decimal("500000"),
        common_prices={"2330": Decimal("10")},
        pre_positions={},
        post_positions={},
    )
    ledger.append_batch((prior_fill,), collision_transition)
    updated_context = replace(context, ledger_rowset_hash=ledger.rowset_hash())
    updated_intent = intent_for(entry, updated_context)
    with pytest.raises(ValueError, match="already exists"):
        producer_for(Provider(updated_context), ledger).produce(entry, updated_intent)
    assert ledger.list(portfolio_id=NAMESPACE) == (prior_fill,)
    assert ledger.list_transitions(portfolio_id=NAMESPACE) == (collision_transition,)
