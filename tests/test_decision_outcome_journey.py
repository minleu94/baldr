"""DecisionOutcomeJourney 的合成 fixture 契約測試。

這些 fixture 都是測試專用 payload，不能被解讀成正式市場資料或實際成交。
"""

from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import pytest

from app_module.decision_outcome_journey import (
    DecisionOutcomeJourneyService,
    JourneyLinkStatus,
    JourneyStatus,
    JourneyTimelineItem,
    OUTCOME_WINDOWS,
    PortfolioLedgerRepositoryReadAdapter,
    project_outcome_maturity,
    _sort_time,
)
from data_module.portfolio_ledger_repository import PortfolioLedgerEvent, PortfolioLedgerRepository


RESULT_ID = "synthetic-result-001"
STOCK_CODE = "2330"
SOURCE_SNAPSHOT_HASH = "sha256:synthetic-source"


class MemoryRecommendation:
    def __init__(self, payload: Mapping[str, Any] | None) -> None:
        self.payload = payload

    def read_result(self, result_id: str) -> Mapping[str, Any] | None:
        if self.payload is None:
            return None
        if result_id != self.payload.get("result_id"):
            return None
        return self.payload


class MemoryEvidence:
    def __init__(
        self,
        events: Sequence[Mapping[str, Any]],
        outcomes: Sequence[Mapping[str, Any]] = (),
        *,
        has_more: bool = False,
    ) -> None:
        self.events = tuple(events)
        self.outcomes = tuple(outcomes)
        self.last_has_more = has_more
        self.requested_dates: list[str | None] = []

    def list_events(
        self, *, decision_date: str | None = None
    ) -> Sequence[Mapping[str, Any]]:
        self.requested_dates.append(decision_date)
        return self.events

    def list_outcomes(self, *, event_id: str) -> Sequence[Mapping[str, Any]]:
        return tuple(item for item in self.outcomes if item.get("event_id") == event_id)


class BatchMemoryEvidence(MemoryEvidence):
    def __init__(
        self,
        events: Sequence[Mapping[str, Any]],
        outcomes: Sequence[Mapping[str, Any]] = (),
        *,
        has_more: bool = False,
    ) -> None:
        super().__init__(events, outcomes, has_more=has_more)
        self.requested_event_ids: list[tuple[str, ...]] = []

    def list_outcomes_for_event_ids(
        self,
        event_ids: Sequence[str],
    ) -> Sequence[Mapping[str, Any]]:
        requested = tuple(event_ids)
        self.requested_event_ids.append(requested)
        # Return the complete memory set deliberately; the service must still
        # filter returned rows by the exact event ids it requested.
        return self.outcomes


class MemoryJournal:
    def __init__(self, entries: Sequence[Mapping[str, Any]]) -> None:
        self.entries = tuple(entries)

    def list_entries(self) -> Sequence[Mapping[str, Any]]:
        return self.entries


class MemoryLedger:
    def __init__(self, events: Sequence[PortfolioLedgerEvent | Mapping[str, Any]]) -> None:
        self.events = tuple(events)

    def list_events(self) -> Sequence[PortfolioLedgerEvent | Mapping[str, Any]]:
        return self.events


class MemoryTrades:
    def __init__(self, trades: Sequence[Mapping[str, Any]]) -> None:
        self.trades = tuple(trades)

    def list_trades(self) -> Sequence[Mapping[str, Any]]:
        return self.trades


def _result(*, stock_code: str = STOCK_CODE) -> dict[str, Any]:
    return {
        "result_id": RESULT_ID,
        "result_name": "合成推薦結果（測試）",
        "created_at": "2026-01-02T09:00:00+00:00",
        "config": {
            "decision_date": "2026-01-02",
            "source_snapshot_hash": SOURCE_SNAPSHOT_HASH,
            "strategy_version_id": "synthetic-strategy-v1",
            "strategy_config_id": "synthetic-config-001",
            "strategy_config_hash": "sha256:synthetic-config",
            "universe_policy_id": "synthetic-policy-001",
            "universe_policy_hash": "sha256:synthetic-policy",
            "universe_snapshot_id": "synthetic-universe-001",
            "universe_snapshot_hash": "sha256:synthetic-universe",
            "research_only": True,
        },
        "run_context": {
            "as_of_date": "2026-01-02",
            "source_id": "synthetic-provider-v1",
            "strategy_version_id": "synthetic-strategy-v1",
            "strategy_config_id": "synthetic-config-001",
            "strategy_config_hash": "sha256:synthetic-config",
            "universe_policy_id": "synthetic-policy-001",
            "universe_policy_hash": "sha256:synthetic-policy",
            "universe_snapshot_id": "synthetic-universe-001",
            "universe_snapshot_hash": "sha256:synthetic-universe",
        },
        "recommendations": [
            {
                "證券代號": stock_code,
                "證券名稱": "合成標的",
                "recommendation_rank": 1,
                "opaque_nested": {"preserve": ["source", 1]},
            }
        ],
    }


def _event(
    *,
    event_id: str = "event-001",
    result_id: str = RESULT_ID,
    stock_code: str = STOCK_CODE,
    available_date: str = "2026-01-02",
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "event_hash": f"sha256:{event_id}",
        "event_date": "2026-01-02",
        "decision_date": "2026-01-02",
        "symbol": stock_code,
        "event_type": "recommendation_included",
        "event_family": "recommendation",
        "source_type": "recommendation_result",
        "source_id": result_id,
        "source_snapshot_id": result_id,
        "source_version": "synthetic-importer-v1",
        "as_of_date": "2026-01-02",
        "available_date": available_date,
        "created_at": "2026-01-02T09:01:00+00:00",
        "metadata": {"source_result_id": result_id},
    }


def _outcome(
    *,
    event_id: str = "event-001",
    outcome_id: str = "outcome-001",
    window_days: int = 5,
    forward_return_bp: int | None = 120,
    calculated_at: str = "2026-01-10T09:00:00+00:00",
    return_basis: str = "close_to_close_event_date",
    outcome_status: str = "ready",
) -> dict[str, Any]:
    return {
        "outcome_id": outcome_id,
        "event_id": event_id,
        "window_days": window_days,
        "window_type": "trading_days",
        "return_basis": return_basis,
        "outcome_status": outcome_status,
        "data_quality": "observed",
        "forward_return_bp": forward_return_bp,
        "event_price_date": "2026-01-02",
        "outcome_price_date": "2026-01-09",
        "calculated_at": calculated_at,
        "data_as_of_date": "2026-01-09",
        "metadata": {
            "is_execution_pnl": False,
            "fixture": True,
        },
    }


def _ledger_trade(
    *,
    event_id: str = "ledger-trade-001",
    source_id: str = RESULT_ID,
    source_snapshot_hash: str = SOURCE_SNAPSHOT_HASH,
) -> PortfolioLedgerEvent:
    return PortfolioLedgerEvent(
        event_id=event_id,
        portfolio_id="synthetic-personal",
        source_namespace="manual",
        occurred_at="2026-01-03T09:30:00+00:00",
        stock_code=STOCK_CODE,
        stock_name="合成標的",
        side="buy",
        quantity=100,
        price=Decimal("600.00"),
        fees=Decimal("1.20"),
        taxes=Decimal("0.00"),
        currency="TWD",
        source_id=source_id,
        source_snapshot_hash=source_snapshot_hash,
        thesis_id="thesis-synthetic-001",
        event_type="trade",
        created_at="2026-01-03T09:31:00+00:00",
    )


def _ledger_compensation() -> PortfolioLedgerEvent:
    return PortfolioLedgerEvent(
        event_id="ledger-compensation-001",
        portfolio_id="synthetic-personal",
        source_namespace="manual",
        occurred_at="2026-01-04T09:30:00+00:00",
        stock_code=STOCK_CODE,
        stock_name="合成標的",
        currency="TWD",
        source_id="",
        source_snapshot_hash="",
        thesis_id="thesis-synthetic-001",
        event_type="compensation",
        reverses_event_id="ledger-trade-001",
        reason="合成修訂／補償事件",
        created_at="2026-01-04T09:31:00+00:00",
    )


def _service(
    *,
    result: Mapping[str, Any] | None = None,
    events: Sequence[Mapping[str, Any]] = (),
    outcomes: Sequence[Mapping[str, Any]] = (),
    journals: Sequence[Mapping[str, Any]] = (),
    ledger: Sequence[PortfolioLedgerEvent | Mapping[str, Any]] = (),
    trades: Sequence[Mapping[str, Any]] | None = None,
    evidence_has_more: bool = False,
) -> DecisionOutcomeJourneyService:
    return DecisionOutcomeJourneyService(
        recommendation_reader=MemoryRecommendation(result if result is not None else _result()),
        evidence_reader=MemoryEvidence(events, outcomes, has_more=evidence_has_more),
        journal_reader=MemoryJournal(journals),
        portfolio_ledger_reader=MemoryLedger(ledger),
        portfolio_trade_reader=(None if trades is None else MemoryTrades(trades)),
    )


def test_synthetic_exact_chain_freezes_root_and_separates_personal_records() -> None:
    raw_result = _result()
    outcomes = [
        _outcome(window_days=window, outcome_id=f"outcome-{window}")
        for window in OUTCOME_WINDOWS
    ]
    journals = [
        {
            "journal_id": "journal-result-001",
            "linked_type": "recommendation_result",
            "linked_id": RESULT_ID,
            "source_type": "recommendation_result",
            "source_id": RESULT_ID,
            "source_snapshot_hash": SOURCE_SNAPSHOT_HASH,
            "created_at": "2026-01-03T10:00:00+00:00",
        },
        {
            "journal_id": "journal-revision-001",
            "linked_type": "trade",
            "linked_id": "ledger-trade-001",
            "thesis_id": "thesis-synthetic-001",
            "revision_of": "ledger-trade-001",
            "created_at": "2026-01-04T10:00:00+00:00",
        },
    ]
    service = _service(
        result=raw_result,
        events=[_event()],
        outcomes=outcomes,
        journals=journals,
        ledger=[_ledger_trade(), _ledger_compensation()],
    )

    journey = service.build(RESULT_ID, query_boundary="2026-01-20T00:00:00+00:00")

    assert journey.status is JourneyStatus.LINKED
    assert journey.recommendation_result.source_identity.result_id == RESULT_ID
    assert journey.recommendation_result.source_identity.source_provider_id == "synthetic-provider-v1"
    assert journey.recommendation_result.source_identity.source_snapshot_id is None
    assert journey.recommendation_result.candidates[0].candidate_key == (RESULT_ID, STOCK_CODE)
    assert journey.evidence_events[0].candidate_key == (RESULT_ID, STOCK_CODE)
    assert {item.window_days for item in journey.outcomes} == set(OUTCOME_WINDOWS)
    assert all(item.performance_semantics == "research_forward_return" for item in journey.outcomes)
    assert {item.window_days for item in journey.outcome_maturity} == set(OUTCOME_WINDOWS)
    assert len(journey.journal_entries) == 2
    assert {item.record_id for item in journey.portfolio_ledger_events} == {
        "ledger-trade-001",
        "ledger-compensation-001",
    }
    compensation = next(
        item for item in journey.portfolio_ledger_events if item.event_type == "compensation"
    )
    assert compensation.link_status is JourneyLinkStatus.LINKED
    assert compensation.reverses_event_id == "ledger-trade-001"
    assert journey.has_personal_trade_link is True
    assert journey.investment_effectiveness_claim is False
    assert journey.read_only is True
    assert journey.writes_allowed is False
    assert [item.item_type for item in journey.timeline[:2]] == [
        "recommendation_result",
        "evidence_event",
    ]
    assert journey.timeline.index(
        next(item for item in journey.timeline if item.item_type == "portfolio_ledger_event")
    ) < journey.timeline.index(
        next(item for item in journey.timeline if item.item_type == "evidence_outcome")
    )

    frozen = journey.recommendation_result.original_payload
    with pytest.raises(TypeError):
        frozen["result_id"] = "mutated"  # type: ignore[index]
    raw_result["result_id"] = "mutated-after-build"
    assert journey.recommendation_result.original_payload["result_id"] == RESULT_ID
    assert journey.to_dict()["recommendation_result"]["original_payload"]["result_id"] == RESULT_ID


def test_maturity_projection_keeps_link_and_outcome_status_separate() -> None:
    journey = _service(
        events=[_event()],
        outcomes=[
            _outcome(
                window_days=window,
                outcome_id=f"outcome-{window}",
                forward_return_bp=None,
                outcome_status="insufficient_future_data",
            )
            for window in OUTCOME_WINDOWS
        ],
    ).build(RESULT_ID)
    projected = project_outcome_maturity(journey.outcome_maturity)

    assert len(projected) == len(OUTCOME_WINDOWS)
    assert all(item.status is JourneyLinkStatus.LINKED for item in projected)
    assert all(item.outcome_status == "insufficient_future_data" for item in projected)
    assert all(
        item.status.value != item.outcome_status
        for item in projected
    )


def test_same_stock_and_date_different_source_does_not_join() -> None:
    journey = _service(
        events=[
            _event(event_id="event-target", result_id=RESULT_ID),
            _event(event_id="event-foreign", result_id="different-result"),
        ]
    ).build(RESULT_ID)

    assert [item.event_id for item in journey.evidence_events] == ["event-target"]
    assert journey.coverage.evidence_read == 2
    assert journey.coverage.evidence_linked == 1
    assert journey.coverage.evidence_unlinked == 1
    assert "event-foreign" not in {item.event_id for item in journey.evidence_events}


def test_missing_old_key_is_unknown_and_does_not_block_recommendation_tracking() -> None:
    journey = _service(events=()).build(RESULT_ID)

    assert journey.recommendation_result.result_id == RESULT_ID
    assert journey.recommendation_result.candidates[0].candidate_key == (RESULT_ID, STOCK_CODE)
    assert journey.status is JourneyStatus.PARTIAL
    assert len(journey.outcome_maturity) == len(OUTCOME_WINDOWS)
    assert all(item.status is JourneyLinkStatus.UNKNOWN for item in journey.outcome_maturity)
    assert any(item.code == "evidence_link_missing" for item in journey.diagnostics)
    assert journey.recommendation_result.result_id == RESULT_ID


def test_missing_result_key_is_unknown_without_fabricating_payload() -> None:
    # Use a reader that has no row for the requested identity.
    journey = DecisionOutcomeJourneyService(
        recommendation_reader=MemoryRecommendation(None),
        evidence_reader=MemoryEvidence(()),
    ).build("old-result-key")

    assert journey.status is JourneyStatus.UNKNOWN
    assert journey.recommendation_result.result_id == "old-result-key"
    assert journey.recommendation_result.original_payload == {}
    assert any(item.code == "recommendation_result_key_missing" for item in journey.diagnostics)


def test_conflicting_duplicate_outcome_fails_closed() -> None:
    outcomes = [
        _outcome(outcome_id="outcome-a", window_days=5, forward_return_bp=100),
        _outcome(outcome_id="outcome-b", window_days=5, forward_return_bp=200),
    ]
    journey = _service(events=[_event()], outcomes=outcomes).build(RESULT_ID)

    assert journey.status is JourneyStatus.CONFLICT
    maturity = next(item for item in journey.outcome_maturity if item.window_days == 5)
    assert maturity.status is JourneyLinkStatus.CONFLICT
    assert any(item.code == "conflicting_duplicate_outcome" for item in journey.diagnostics)
    assert {item.forward_return_bp for item in journey.outcomes} == {100, 200}


def test_batch_outcomes_preserve_duplicate_conflict_and_exact_result_scope() -> None:
    reader = BatchMemoryEvidence(
        events=[
            _event(event_id="event-target", result_id=RESULT_ID),
            _event(event_id="event-foreign", result_id="different-result"),
        ],
        outcomes=[
            _outcome(
                event_id="event-target",
                outcome_id="outcome-target-a",
                window_days=5,
                forward_return_bp=100,
            ),
            _outcome(
                event_id="event-target",
                outcome_id="outcome-target-b",
                window_days=5,
                forward_return_bp=200,
            ),
            _outcome(
                event_id="event-foreign",
                outcome_id="outcome-foreign",
                window_days=5,
            ),
        ],
    )
    service = DecisionOutcomeJourneyService(
        recommendation_reader=MemoryRecommendation(_result()),
        evidence_reader=reader,
    )

    journey = service.build(RESULT_ID)

    assert reader.requested_event_ids == [("event-target",)]
    assert [item.event_id for item in journey.evidence_events] == ["event-target"]
    assert {item.event_id for item in journey.outcomes} == {"event-target"}
    maturity = next(item for item in journey.outcome_maturity if item.window_days == 5)
    assert maturity.status is JourneyLinkStatus.CONFLICT
    assert any(item.code == "conflicting_duplicate_outcome" for item in journey.diagnostics)


def test_outcome_return_basis_is_part_of_natural_key() -> None:
    journey = _service(
        events=[_event()],
        outcomes=[
            _outcome(
                window_days=5,
                return_basis="different_research_basis",
            )
        ],
    ).build(RESULT_ID)

    maturity = next(item for item in journey.outcome_maturity if item.window_days == 5)
    assert maturity.status is JourneyLinkStatus.UNKNOWN
    assert maturity.reason == "outcome_return_basis_mismatch"
    assert any(item.code == "outcome_return_basis_mismatch" for item in journey.diagnostics)


def test_conflicting_result_identity_fails_closed() -> None:
    raw = _result()
    raw["config"] = dict(raw["config"], source_id="config-provider")
    raw["run_context"] = dict(raw["run_context"], source_id="different-provider")

    journey = _service(result=raw, events=[_event()]).build(RESULT_ID)

    assert journey.status is JourneyStatus.CONFLICT
    assert journey.recommendation_result.source_identity.source_provider_id is None
    assert any(item.code == "recommendation_source_id_conflict" for item in journey.diagnostics)


def test_revision_and_compensation_are_visible_only_through_explicit_keys() -> None:
    journey = _service(
        events=[_event()],
        outcomes=[_outcome(window_days=window, outcome_id=f"outcome-{window}") for window in OUTCOME_WINDOWS],
        journals=[
            {
                "journal_id": "journal-ledger-link",
                "linked_type": "trade",
                "linked_id": "ledger-trade-001",
                "revision_of": "ledger-trade-001",
                "created_at": "2026-01-04T10:00:00+00:00",
            }
        ],
        ledger=[_ledger_trade(), _ledger_compensation()],
    ).build(RESULT_ID)

    journal = journey.journal_entries[0]
    assert journal.link_status is JourneyLinkStatus.LINKED
    assert journal.relationship_type == "revision_or_reversal"
    assert journal.relationship_target_id == "ledger-trade-001"
    assert {item.record_id for item in journey.portfolio_ledger_events} == {
        "ledger-trade-001",
        "ledger-compensation-001",
    }


def test_bounded_evidence_read_reports_truncation_and_unknown_target() -> None:
    # 這個 reader 明示只回傳 bounded page；目標 result 位於未讀 page。
    journey = _service(
        events=[_event(result_id="different-result")],
        evidence_has_more=True,
    ).build(RESULT_ID)

    assert journey.status is JourneyStatus.PARTIAL
    assert journey.coverage.evidence_read == 1
    assert journey.coverage.evidence_unlinked == 1
    assert any(item.code == "evidence_read_truncated" for item in journey.diagnostics)
    assert any(
        item.code == "evidence_link_unknown_due_to_truncated_read"
        for item in journey.diagnostics
    )
    assert not any(item.code == "evidence_link_missing" for item in journey.diagnostics)

    target_in_page = _service(
        events=[_event()],
        outcomes=[
            _outcome(window_days=window, outcome_id=f"outcome-{window}")
            for window in OUTCOME_WINDOWS
        ],
        evidence_has_more=True,
    ).build(RESULT_ID)
    assert target_in_page.evidence_events[0].event_id == "event-001"
    assert target_in_page.status is JourneyStatus.PARTIAL
    assert any(item.code == "evidence_read_truncated" for item in target_in_page.diagnostics)


def test_query_boundary_compares_cross_offset_instants_and_rejects_future() -> None:
    same_instant = _service(
        events=[
            _event(
                available_date="2026-01-03T17:00:00+08:00",
            )
        ]
    ).build(RESULT_ID, query_boundary="2026-01-03T09:00:00Z")
    assert same_instant.evidence_events[0].link_status is JourneyLinkStatus.LINKED
    assert not any(
        item.code == "evidence_not_available_at_query_boundary"
        for item in same_instant.diagnostics
    )

    future = _service(
        events=[
            _event(
                available_date="2026-01-03T09:00:01Z",
            )
        ],
        outcomes=[
            _outcome(
                outcome_id=f"outcome-future-{window}",
                window_days=window,
                calculated_at="2026-01-03T09:00:01Z",
            )
            for window in OUTCOME_WINDOWS
        ],
    ).build(RESULT_ID, query_boundary="2026-01-03T09:00:00Z")
    assert future.evidence_events[0].link_status is JourneyLinkStatus.DEFERRED
    assert future.outcomes == ()
    assert all(
        item.status is JourneyLinkStatus.DEFERRED for item in future.outcome_maturity
    )
    assert any(
        item.code == "outcome_not_available_at_query_boundary"
        for item in future.diagnostics
    )


def test_date_only_boundary_is_explicit_calendar_day_and_naive_is_unknown() -> None:
    date_boundary = _service(
        events=[_event(available_date="2026-01-03")]
    ).build(RESULT_ID, query_boundary="2026-01-03T00:00:00Z")
    assert date_boundary.evidence_events[0].link_status is JourneyLinkStatus.LINKED

    naive_source = _service(
        events=[_event(available_date="2026-01-03T09:00:00")]
    ).build(RESULT_ID, query_boundary="2026-01-03T09:00:00Z")
    assert naive_source.evidence_events[0].link_status is JourneyLinkStatus.DEFERRED
    assert any(
        item.code == "evidence_not_available_at_query_boundary"
        for item in naive_source.diagnostics
    )

    invalid_boundary = _service(
        events=[_event(available_date="2026-01-03")]
    ).build(RESULT_ID, query_boundary="2026-01-03T09:00:00")
    assert any(
        item.code == "query_boundary_invalid_or_timezone_unknown"
        for item in invalid_boundary.diagnostics
    )
    assert invalid_boundary.evidence_events[0].link_status is JourneyLinkStatus.DEFERRED


def test_timeline_sort_normalizes_aware_offsets_and_puts_unknown_last() -> None:
    first = JourneyTimelineItem(
        item_type="evidence_event",
        item_id="b",
        source_at="2026-01-03T17:00:00+08:00",
        occurred_at="2026-01-03T17:00:00+08:00",
        available_at="2026-01-03",
        query_boundary=None,
        link_status=JourneyLinkStatus.LINKED,
        source_key=("result",),
    )
    second = JourneyTimelineItem(
        item_type="evidence_event",
        item_id="a",
        source_at="2026-01-03T09:00:00Z",
        occurred_at="2026-01-03T09:00:00Z",
        available_at="2026-01-03",
        query_boundary=None,
        link_status=JourneyLinkStatus.LINKED,
        source_key=("result",),
    )
    unknown = JourneyTimelineItem(
        item_type="evidence_event",
        item_id="unknown",
        source_at="2026-01-03T09:00:00",
        occurred_at="2026-01-03T09:00:00",
        available_at=None,
        query_boundary=None,
        link_status=JourneyLinkStatus.UNKNOWN,
        source_key=(),
    )

    assert _sort_time(first.occurred_at) == _sort_time(second.occurred_at)
    assert _sort_time(second.occurred_at) < _sort_time(unknown.occurred_at)
    assert [item.item_id for item in sorted((first, unknown, second), key=lambda item: item.sort_key)] == [
        "a",
        "b",
        "unknown",
    ]


def test_read_only_adapters_do_not_change_source_files(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    result_path = output_root / "recommendation" / "runs" / f"{RESULT_ID}.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text(json.dumps(_result(), ensure_ascii=False), encoding="utf-8")
    journal_path = output_root / "portfolio" / "journal_entries.jsonl"
    journal_path.parent.mkdir(parents=True)
    journal_path.write_text(
        json.dumps(
            {
                "journal_id": "journal-001",
                "linked_id": RESULT_ID,
                "linked_type": "recommendation_result",
                "created_at": "2026-01-03T10:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    ledger_path = tmp_path / "portfolio_ledger.sqlite"
    PortfolioLedgerRepository.create_synthetic_fixture(
        ledger_path,
        events=[_ledger_trade()],
    )
    result_before = (result_path.stat().st_mtime_ns, result_path.read_bytes())
    journal_before = (journal_path.stat().st_mtime_ns, journal_path.read_bytes())
    ledger_before = (ledger_path.stat().st_mtime_ns, ledger_path.read_bytes())

    service = DecisionOutcomeJourneyService.from_paths(
        output_root=output_root,
        journal_path=journal_path,
        portfolio_ledger_path=ledger_path,
    )
    journey = service.build(RESULT_ID)

    assert journey.recommendation_result.result_id == RESULT_ID
    assert journey.journal_entries[0].journal_id == "journal-001"
    assert journey.portfolio_ledger_events[0].record_id == "ledger-trade-001"
    assert PortfolioLedgerRepositoryReadAdapter(ledger_path).repository.read_only is True
    assert (result_path.stat().st_mtime_ns, result_path.read_bytes()) == result_before
    assert (journal_path.stat().st_mtime_ns, journal_path.read_bytes()) == journal_before
    assert (ledger_path.stat().st_mtime_ns, ledger_path.read_bytes()) == ledger_before


def test_no_actual_fill_does_not_block_recommendation_tracking() -> None:
    outcomes = [
        _outcome(window_days=window, outcome_id=f"outcome-{window}")
        for window in OUTCOME_WINDOWS
    ]
    journey = _service(events=[_event()], outcomes=outcomes).build(RESULT_ID)

    assert journey.status is JourneyStatus.LINKED
    assert journey.recommendation_result.result_id == RESULT_ID
    assert journey.evidence_events[0].event_id == "event-001"
    assert journey.portfolio_ledger_events == ()
    assert journey.portfolio_trades == ()
    assert journey.has_personal_trade_link is False


def test_legacy_float_trade_is_preserved_but_not_used_for_financial_calculation() -> None:
    trade = {
        "trade_id": "legacy-trade-001",
        "portfolio_id": "default",
        "trade_date": "2026-01-03",
        "stock_code": STOCK_CODE,
        "side": "buy",
        "quantity": 1000.0,
        "price": 600.5,
        "fees": 1.0,
        "taxes": 0.0,
        "source_id": RESULT_ID,
        "source_snapshot_hash": SOURCE_SNAPSHOT_HASH,
        "created_at": "2026-01-03T10:00:00+00:00",
    }
    journey = _service(
        events=[_event()],
        trades=[trade],
    ).build(RESULT_ID)

    assert journey.portfolio_trades[0].link_status is JourneyLinkStatus.LINKED
    assert journey.portfolio_trades[0].quantity is None
    assert journey.portfolio_trades[0].price is None
    assert journey.portfolio_trades[0].original_payload["price"] == 600.5
    assert any(item.code == "non_decimal_financial_value" for item in journey.diagnostics)
