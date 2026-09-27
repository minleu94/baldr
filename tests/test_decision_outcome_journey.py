"""DecisionOutcomeJourney 的合成 fixture 契約測試。

這些 fixture 都是測試專用 payload，不能被解讀成正式市場資料或實際成交。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

import pytest

from app_module.decision_outcome_journey import (
    DecisionOutcomeJourneyService,
    JsonRecommendationReadAdapter,
    JourneyLinkStatus,
    JourneyStatus,
    JourneyTimelineItem,
    OUTCOME_WINDOWS,
    PortfolioLedgerRepositoryReadAdapter,
    project_outcome_maturity,
    _sort_time,
)
from app_module.recommendation.codec import decode_execution_envelope
from app_module.recommendation.persistence import RecommendationExecutionPersistence
from app_module.recommendation.contracts import (
    RecommendationConfigSnapshot,
    ExecutionStatus,
    RecommendationExecution,
    ReferenceKind,
    VersionReference,
)
from app_module.portfolio_source_adapter import (
    build_recommendation_execution_trade_source,
    stable_snapshot_hash,
)
from data_module.contracts.market import SourceRef
from data_module.result_artifact_store import ResultArtifactStore
from data_module.portfolio_ledger_repository import PortfolioLedgerEvent, PortfolioLedgerRepository
from data_module.config import TWStockConfig


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


def _register_legacy_recommendation(
    output_root: Path,
    result_id: str,
    payload: Mapping[str, Any],
) -> tuple[Path, bytes]:
    runs_dir = output_root / "recommendation" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    result_path = runs_dir / f"{result_id}.json"
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    result_path.write_bytes(raw)
    with sqlite3.connect(runs_dir / "recommendation_runs.db") as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                result_id TEXT PRIMARY KEY,
                result_name TEXT,
                notes TEXT,
                created_at TEXT,
                data_path TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO runs (result_id, result_name, notes, created_at, data_path)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                result_id,
                str(payload.get("result_name", "legacy fixture")),
                str(payload.get("notes", "")),
                payload.get("created_at"),
                str(result_path),
            ),
        )
    return result_path, raw


def _save_canonical_recommendation(
    output_root: Path,
) -> tuple[RecommendationExecution, str]:
    fixture = (
        Path(__file__).parent
        / "fixtures"
        / "c1_consumer_readiness"
        / "r016_execution_rev2.json"
    )
    execution = decode_execution_envelope(fixture.read_bytes()).execution
    runs_dir = output_root / "recommendation" / "runs"
    store = ResultArtifactStore(
        artifact_root=runs_dir / "execution_artifacts",
        database_path=runs_dir / "recommendation_runs.db",
    )
    receipt = RecommendationExecutionPersistence(store).save(
        execution,
        label="synthetic canonical journey fixture",
        now=lambda: datetime(2026, 9, 23, tzinfo=timezone.utc),
    )
    return execution, receipt.artifact_location


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
    assert journey.recommendation_result.result_path == str(result_path.resolve())
    assert journey.recommendation_result.to_dict()["original_payload"] == json.loads(
        result_before[1]
    )
    assert journey.recommendation_result.source_identity.source_provider_id == (
        "synthetic-provider-v1"
    )
    assert journey.recommendation_result.source_identity.source_snapshot_hash == (
        SOURCE_SNAPSHOT_HASH
    )
    assert journey.recommendation_result.candidates[0].recommendation_rank == 1
    assert journey.recommendation_result.candidates[0].to_dict()[
        "original_payload"
    ] == json.loads(result_before[1])["recommendations"][0]
    assert journey.journal_entries[0].journal_id == "journal-001"
    assert journey.portfolio_ledger_events[0].record_id == "ledger-trade-001"
    assert PortfolioLedgerRepositoryReadAdapter(ledger_path).repository.read_only is True
    assert (result_path.stat().st_mtime_ns, result_path.read_bytes()) == result_before
    assert (journal_path.stat().st_mtime_ns, journal_path.read_bytes()) == journal_before
    assert (ledger_path.stat().st_mtime_ns, ledger_path.read_bytes()) == ledger_before


def test_journey_reads_registered_legacy_exact_payload_and_verified_path(
    tmp_path: Path,
) -> None:
    result_id = "journey-registered-legacy"
    output_root = tmp_path / "output"
    payload = _result()
    payload["result_id"] = result_id
    payload["source_id"] = "provider-legacy"
    payload["source_snapshot_id"] = "snapshot-legacy"
    payload["source_snapshot_hash"] = "sha256:" + "a" * 64
    payload["config"] = {
        **payload["config"],
        "source_id": "provider-legacy",
        "source_snapshot_id": "snapshot-legacy",
        "source_snapshot_hash": "sha256:" + "a" * 64,
    }
    payload["run_context"] = {
        **payload["run_context"],
        "source_id": "provider-legacy",
        "source_snapshot_id": "snapshot-legacy",
        "source_snapshot_hash": "sha256:" + "a" * 64,
    }
    candidate = dict(payload["recommendations"][0])
    candidate["recommendation_rank"] = 9
    candidate["opaque_provider_row"] = {"nested": ["keep", {"tag": "exact"}]}
    payload["recommendations"] = [candidate]
    payload["opaque_root"] = {"payload": [1, {"unknown": True}]}
    legacy_path, raw = _register_legacy_recommendation(
        output_root,
        result_id,
        payload,
    )

    adapter = JsonRecommendationReadAdapter(output_root)
    service = DecisionOutcomeJourneyService(
        recommendation_reader=adapter,
        evidence_reader=MemoryEvidence(()),
    )
    journey = service.build(result_id)

    assert journey.recommendation_result.source_identity.source_provider_id == (
        "provider-legacy"
    )
    assert journey.recommendation_result.source_identity.source_snapshot_id == (
        "snapshot-legacy"
    )
    assert journey.recommendation_result.source_identity.source_snapshot_hash == (
        "sha256:" + "a" * 64
    )
    assert journey.recommendation_result.candidates[0].recommendation_rank == 9
    assert journey.recommendation_result.original_payload["opaque_root"]["payload"][1][
        "unknown"
    ] is True
    assert journey.recommendation_result.to_dict()["original_payload"] == json.loads(raw)
    assert journey.recommendation_result.candidates[0].to_dict()[
        "original_payload"
    ] == json.loads(raw)["recommendations"][0]
    assert journey.recommendation_result.result_path == str(legacy_path.resolve())
    assert legacy_path.read_bytes() == raw


def test_journey_reads_canonical_query_projection_and_uses_verified_artifact_location(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "canonical-output"
    execution, artifact_location = _save_canonical_recommendation(output_root)
    adapter = JsonRecommendationReadAdapter(output_root)
    query = adapter._queries
    original_get = query.get
    queried_ids: list[str] = []

    def counted_get(result_id: str) -> Any:
        queried_ids.append(result_id)
        return original_get(result_id)

    monkeypatch.setattr(query, "get", counted_get)
    service = DecisionOutcomeJourneyService(
        recommendation_reader=adapter,
        evidence_reader=MemoryEvidence(()),
    )

    journey = service.build(execution.result_id)

    assert queried_ids == [execution.result_id]
    assert journey.recommendation_result.result_id == execution.result_id
    assert journey.recommendation_result.result_path == artifact_location
    assert journey.recommendation_result.result_path != str(
        output_root / "recommendation" / "runs" / f"{execution.result_id}.json"
    )
    assert (
        journey.recommendation_result.decision_date
        == execution.context.as_of_date.isoformat()
    )
    assert journey.recommendation_result.source_identity.source_provider_id == (
        "daily-prices"
    )
    assert journey.recommendation_result.source_identity.source_snapshot_id == (
        "snapshot-A"
    )
    assert journey.recommendation_result.source_identity.source_snapshot_hash is None
    assert journey.recommendation_result.candidates[0].recommendation_rank == (
        execution.decision.items[0].rank  # type: ignore[union-attr]
    )
    candidate = journey.recommendation_result.original_payload["recommendations"][0]
    source_candidate = execution.decision.items[0]  # type: ignore[union-attr]
    assert candidate["stock_code"] == source_candidate.stock_code
    assert candidate["recommendation_rank"] == source_candidate.rank
    assert candidate["rule_score"] == str(source_candidate.rule_score)
    assert candidate["close_price"] == source_candidate.close_price
    assert source_candidate.universe_ref is not None
    assert candidate["universe_ref"]["as_of_date"] == (
        source_candidate.universe_ref.as_of_date.isoformat()
    )
    assert journey.to_dict()["recommendation_result"]["original_payload"][
        "recommendations"
    ][0]["factor_contributions"] == [
        {
            "factor_id": contribution.factor_id,
            "value": contribution.value,
            "unit": contribution.unit,
            "version": contribution.version,
            "source_refs": [
                {
                    "source_id": source.source_id,
                    "revision": source.revision,
                    "snapshot_id": source.snapshot_id,
                }
                for source in contribution.source_refs
            ],
        }
        for contribution in source_candidate.factor_contributions
    ]
    json.dumps(journey.to_dict(), allow_nan=False)


def test_canonical_portfolio_summary_links_only_to_verified_query_facts(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "canonical-trade-output"
    fixture = (
        Path(__file__).parent
        / "fixtures"
        / "c1_consumer_readiness"
        / "r016_execution_rev2.json"
    )
    execution = decode_execution_envelope(fixture.read_bytes()).execution
    execution = replace(
        execution,
        context=replace(
            execution.context,
            source_refs=(
                SourceRef(
                    source_id="verified-source-for-int-revision",
                    revision=7,
                    snapshot_id="source-snapshot-int-revision",
                ),
                SourceRef(
                    source_id="verified-source-for-bool-int-wire-check",
                    revision=1,
                    snapshot_id="source-snapshot-bool-int-wire-check",
                ),
            ),
            data_snapshot_refs=(
                VersionReference(
                    kind=ReferenceKind.DATA_SNAPSHOT,
                    reference_id="data-snapshot-int-revision",
                    version="market-frame-v3",
                ),
            ),
        ),
    )
    runs_dir = output_root / "recommendation" / "runs"
    store = ResultArtifactStore(
        artifact_root=runs_dir / "execution_artifacts",
        database_path=runs_dir / "recommendation_runs.db",
    )
    receipt = RecommendationExecutionPersistence(store).save(
        execution,
        label="合成 canonical trade journey",
        now=lambda: datetime(2026, 9, 24, tzinfo=timezone.utc),
    )
    adapter = JsonRecommendationReadAdapter(output_root)
    verified_read_model = adapter._queries.get(execution.result_id)
    assert verified_read_model is not None
    assert verified_read_model.execution == execution
    assert verified_read_model.ml_read_status != "verified"
    selected = execution.items[0]
    source = build_recommendation_execution_trade_source(
        execution,
        verified_read_model,
        receipt,
        selected,
    )
    base_trade = {
        "trade_id": "canonical-trade-verified-root",
        "portfolio_id": "default",
        "trade_date": execution.context.as_of_date.isoformat(),
        "stock_code": selected.stock_code,
        "side": "buy",
        "quantity": 10,
        "price": "100.00",
        "fees": "0",
        "taxes": "0",
        "source_type": source.source_type,
        "source_id": source.source_id,
        "source_snapshot_hash": source.source_snapshot_hash,
        "source_summary": source.source_summary,
    }
    service = DecisionOutcomeJourneyService(
        recommendation_reader=adapter,
        evidence_reader=MemoryEvidence(()),
        portfolio_trade_reader=MemoryTrades((base_trade,)),
    )

    journey = service.build(execution.result_id)

    assert len(journey.portfolio_trades) == 1
    assert journey.portfolio_trades[0].link_status is JourneyLinkStatus.LINKED, journey.diagnostics
    assert journey.portfolio_trades[0].source_snapshot_hash == source.source_snapshot_hash
    assert base_trade["source_snapshot_hash"] == stable_snapshot_hash(
        base_trade["source_summary"]
    )
    assert source.source_summary["candidate_identity"] == {
        "stock_code": selected.stock_code,
        "rank": selected.rank,
    }
    assert source.source_summary["source_refs"][0]["revision"] == 7
    assert source.source_summary["source_refs"][1]["revision"] == 1
    assert source.source_summary["data_snapshot_ids"] == ["data-snapshot-int-revision"]
    assert source.source_summary["calibrated_probability_bp"] is None
    assert source.source_summary["calibrated_probability_status"] == "unavailable"
    assert source.source_summary["after_cost_profit_probability_bp"] is None
    assert source.source_summary["after_cost_profit_probability_status"] == "unavailable"
    assert source.source_summary["calibration_status"] == "unavailable"
    assert source.source_summary["calibration_provenance"] == {
        "training_provenance": {},
        "inference_provenance": {},
        "provenance_compatibility": {},
        "provenance_status": "unavailable",
    }

    from ui_qt.views.portfolio_view import _canonical_trade_summary_matches_execution

    exact_wire_position = SimpleNamespace(
        source_snapshot_hash=source.source_snapshot_hash,
    )
    assert selected.regime_match is True
    assert _canonical_trade_summary_matches_execution(
        exact_wire_position,
        source.source_summary,
        execution,
        verified_read_model,
        selected.stock_code,
    ) is True
    for mutate_wire_type in (
        lambda summary: summary.__setitem__("regime_match", 1),
        lambda summary: summary["source_refs"][1].__setitem__("revision", True),
    ):
        changed_summary = json.loads(json.dumps(source.source_summary))
        mutate_wire_type(changed_summary)
        changed_position = SimpleNamespace(
            source_snapshot_hash=stable_snapshot_hash(changed_summary),
        )
        assert _canonical_trade_summary_matches_execution(
            changed_position,
            changed_summary,
            execution,
            verified_read_model,
            selected.stock_code,
        ) is False

    for mutate_unavailable_projection in (
        lambda summary: summary.__setitem__("calibrated_probability_bp", 9_900),
        lambda summary: summary.__setitem__("after_cost_profit_probability_bp", 9_800),
        lambda summary: summary.__setitem__("calibrated_probability_status", "verified"),
        lambda summary: summary.__setitem__("calibration_status", "active_candidate"),
        lambda summary: summary["calibration_provenance"].__setitem__(
            "provenance_status", "verified"
        ),
    ):
        changed_summary = json.loads(json.dumps(source.source_summary))
        mutate_unavailable_projection(changed_summary)
        changed_position = SimpleNamespace(
            source_snapshot_hash=stable_snapshot_hash(changed_summary),
        )
        assert _canonical_trade_summary_matches_execution(
            changed_position,
            changed_summary,
            execution,
            verified_read_model,
            selected.stock_code,
        ) is False

    # Journey 的 LINKED 表示 lineage 身分可對接，不宣稱 opaque candidate
    # display 欄位有獨立內容簽章；PortfolioView 另以 typed candidate 核對顯示值。
    display_edit = json.loads(json.dumps(source.source_summary))
    display_edit["total_score"] = "999999"
    display_edit_trade = {
        **base_trade,
        "source_snapshot_hash": stable_snapshot_hash(display_edit),
        "source_summary": display_edit,
    }
    display_edit_journey = DecisionOutcomeJourneyService(
        recommendation_reader=JsonRecommendationReadAdapter(output_root),
        evidence_reader=MemoryEvidence(()),
        portfolio_trade_reader=MemoryTrades((display_edit_trade,)),
    ).build(execution.result_id)
    assert display_edit_journey.portfolio_trades[0].link_status is JourneyLinkStatus.LINKED
    assert (
        display_edit_journey.portfolio_trades[0].original_payload["source_summary"][
            "total_score"
        ]
        == "999999"
    )

    mutations = {
        "payload_hash": lambda summary: summary.__setitem__(
            "payload_hash", "sha256:" + "0" * 64
        ),
        "artifact_location": lambda summary: summary.__setitem__(
            "artifact_location", "forged-artifact.json"
        ),
        "summary_stock": lambda summary: summary.__setitem__(
            "stock_code", "9999"
        ),
        "universe_snapshot": lambda summary: summary.__setitem__(
            "source_snapshot_hash", "sha256:" + "1" * 64
        ),
        "candidate_rank": lambda summary: summary["candidate_identity"].__setitem__(
            "rank", selected.rank + 1
        ),
        "data_snapshot": lambda summary: summary["data_snapshot_ids"].__setitem__(
            0, "different-data-snapshot"
        ),
        "source_ref_revision": lambda summary: summary["source_refs"][0].__setitem__(
            "revision", 8
        ),
    }
    for mutation in mutations.values():
        changed_summary = json.loads(json.dumps(source.source_summary))
        mutation(changed_summary)
        changed_trade = {
            **base_trade,
            "source_snapshot_hash": stable_snapshot_hash(changed_summary),
            "source_summary": changed_summary,
        }
        rejected = DecisionOutcomeJourneyService(
            recommendation_reader=JsonRecommendationReadAdapter(output_root),
            evidence_reader=MemoryEvidence(()),
            portfolio_trade_reader=MemoryTrades((changed_trade,)),
        ).build(execution.result_id)
        assert len(rejected.portfolio_trades) == 1
        assert rejected.portfolio_trades[0].link_status is JourneyLinkStatus.CONFLICT

    bad_checksum = {
        **base_trade,
        "source_snapshot_hash": "0" * 64,
    }
    rejected_checksum = DecisionOutcomeJourneyService(
        recommendation_reader=JsonRecommendationReadAdapter(output_root),
        evidence_reader=MemoryEvidence(()),
        portfolio_trade_reader=MemoryTrades((bad_checksum,)),
    ).build(execution.result_id)
    assert rejected_checksum.portfolio_trades[0].link_status is JourneyLinkStatus.CONFLICT

    mismatched_stock = {**base_trade, "stock_code": "9999"}
    rejected_stock = DecisionOutcomeJourneyService(
        recommendation_reader=JsonRecommendationReadAdapter(output_root),
        evidence_reader=MemoryEvidence(()),
        portfolio_trade_reader=MemoryTrades((mismatched_stock,)),
    ).build(execution.result_id)
    assert rejected_stock.portfolio_trades[0].link_status is JourneyLinkStatus.CONFLICT


def test_portfolio_projection_matches_verified_saved_ml_receipt(
    tmp_path: Path,
) -> None:
    helper_path = Path(__file__).with_name("test_c1_legacy_query_readiness.py")
    spec = importlib.util.spec_from_file_location(
        "r029_portfolio_verified_ml_query_helpers",
        helper_path,
    )
    assert spec is not None and spec.loader is not None
    helper_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper_module)

    execution, _ = helper_module._ml_ready_execution(tmp_path)
    _, persistence, queries = helper_module._stack(tmp_path / "verified-ml-output")
    receipt = persistence.save(execution, label="synthetic verified ML Portfolio source")
    read_model = queries.get(execution.result_id)

    assert read_model is not None
    assert read_model.execution == execution
    assert read_model.ml_read_status == "verified"
    selected = next(item for item in execution.items if item.stock_code == "2330")
    source = build_recommendation_execution_trade_source(
        execution,
        read_model,
        receipt,
        selected,
    )
    assert source.source_summary["ranking_score_bp"] == 7_200
    assert source.source_summary["calibration_model_version"] == "candidate-provenance-1"
    assert source.source_summary["calibration_status"] == "active_candidate"
    assert source.source_summary["calibration_provenance"]["provenance_status"] == "unavailable"

    from ui_qt.views.portfolio_view import _canonical_trade_summary_matches_execution

    position = SimpleNamespace(source_snapshot_hash=source.source_snapshot_hash)
    assert _canonical_trade_summary_matches_execution(
        position,
        source.source_summary,
        execution,
        read_model,
        selected.stock_code,
    ) is True

    projection_mutations = (
        lambda summary: summary.__setitem__("calibrated_probability_bp", 9_900),
        lambda summary: summary.__setitem__("after_cost_profit_probability_bp", 9_800),
        lambda summary: summary.__setitem__("calibrated_probability_status", "forged"),
        lambda summary: summary.__setitem__("calibration_status", "forged"),
        lambda summary: summary["calibration_provenance"]["training_provenance"].__setitem__(
            "candidate_id", "forged-candidate"
        ),
    )
    for mutate_projection in projection_mutations:
        changed_summary = json.loads(json.dumps(source.source_summary))
        mutate_projection(changed_summary)
        changed_position = SimpleNamespace(
            source_snapshot_hash=stable_snapshot_hash(changed_summary),
        )
        assert _canonical_trade_summary_matches_execution(
            changed_position,
            changed_summary,
            execution,
            read_model,
            selected.stock_code,
        ) is False


def test_portfolio_adapter_snapshot_ref_precedes_distinct_request_source_facts(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "portfolio-fallback-output"
    config = TWStockConfig(data_root=tmp_path / "data", output_root=output_root)
    resolved_output_root = Path(config.output_root)
    fixture = (
        Path(__file__).parent
        / "fixtures"
        / "c1_consumer_readiness"
        / "r016_execution_rev2.json"
    )
    execution = decode_execution_envelope(fixture.read_bytes()).execution
    caller_config = {
        "source_snapshot_id": "caller-source-snapshot",
        "source_snapshot_hash": "caller-source-hash",
    }
    raw_caller_config = json.dumps(
        caller_config,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    request_snapshot = RecommendationConfigSnapshot(
        raw_config_json=raw_caller_config,
        raw_json_sha256="sha256:" + hashlib.sha256(
            raw_caller_config.encode("utf-8")
        ).hexdigest(),
    )
    execution = replace(
        execution,
        request=replace(execution.request, config_snapshot=request_snapshot),
        context=replace(
            execution.context,
            universe_snapshot_ref=VersionReference(
                kind=ReferenceKind.UNIVERSE_SNAPSHOT,
                reference_id="context-universe-snapshot",
            ),
        ),
    )
    runs_dir = resolved_output_root / "recommendation" / "runs"
    store = ResultArtifactStore(
        artifact_root=runs_dir / "execution_artifacts",
        database_path=runs_dir / "recommendation_runs.db",
    )
    receipt = RecommendationExecutionPersistence(store).save(
        execution,
        label="canonical adapter snapshot-ref fallback",
        now=lambda: datetime(2026, 9, 24, tzinfo=timezone.utc),
    )
    read_model = JsonRecommendationReadAdapter(resolved_output_root)._queries.get(
        execution.result_id
    )
    assert read_model is not None
    assert read_model.execution == execution
    selected = execution.items[0]
    source = build_recommendation_execution_trade_source(
        execution,
        read_model,
        receipt,
        selected,
    )
    assert source.source_summary["source_snapshot_id"] == "context-universe-snapshot"
    assert source.source_summary["source_snapshot_hash"] == ""

    from ui_qt.views.portfolio_view import PortfolioView

    view = PortfolioView.__new__(PortfolioView)
    view.portfolio_service = SimpleNamespace(config=config)
    position = SimpleNamespace(
        source_type="recommendation_result",
        source_id=execution.result_id,
        source_snapshot_hash=source.source_snapshot_hash,
        source_summary=source.source_summary,
    )
    assert view._validated_recommendation_result_id(
        position,
        selected.stock_code,
    ) == execution.result_id


def test_canonical_shaped_trade_without_same_build_verified_root_is_conflict() -> None:
    summary = {
        "result_id": RESULT_ID,
        "stock_code": STOCK_CODE,
        "integrity_basis": "canonical_payload_and_index_verified",
        "payload_hash": "sha256:" + "1" * 64,
        "artifact_location": "opaque-artifact.json",
        "candidate_identity": {"stock_code": STOCK_CODE, "rank": 1},
        "data_snapshot_ids": [],
        "source_refs": [],
    }
    journey = _service(
        events=[_event()],
        trades=[
            {
                "trade_id": "canonical-shaped-without-root",
                "stock_code": STOCK_CODE,
                "source_id": RESULT_ID,
                "source_type": "recommendation_result",
                "source_snapshot_hash": stable_snapshot_hash(summary),
                "source_summary": summary,
                "trade_date": "2026-01-03",
                "quantity": 1,
                "price": "1.00",
            }
        ],
    ).build(RESULT_ID)

    assert len(journey.portfolio_trades) == 1
    assert journey.portfolio_trades[0].link_status is JourneyLinkStatus.CONFLICT
    assert any(
        item.code == "portfolio_trade_canonical_root_unverified"
        for item in journey.diagnostics
    )


def test_canonical_query_root_rejects_duplicate_candidate_ranks(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "duplicate-rank-output"
    fixture = (
        Path(__file__).parent
        / "fixtures"
        / "c1_consumer_readiness"
        / "r016_execution_rev2.json"
    )
    execution = decode_execution_envelope(fixture.read_bytes()).execution
    selected = execution.items[0]
    assert execution.decision is not None
    duplicate = replace(selected, stock_code="9999")
    execution = replace(
        execution,
        decision=replace(
            execution.decision,
            items=(*execution.items, duplicate),
        ),
    )
    runs_dir = output_root / "recommendation" / "runs"
    store = ResultArtifactStore(
        artifact_root=runs_dir / "execution_artifacts",
        database_path=runs_dir / "recommendation_runs.db",
    )
    receipt = RecommendationExecutionPersistence(store).save(
        execution,
        label="合成 duplicate-rank negative control",
        now=lambda: datetime(2026, 9, 24, tzinfo=timezone.utc),
    )
    adapter = JsonRecommendationReadAdapter(output_root)
    read_model = adapter._queries.get(execution.result_id)
    assert read_model is not None
    assert read_model.execution == execution
    source = build_recommendation_execution_trade_source(
        execution,
        read_model,
        receipt,
        selected,
    )
    trade = {
        "trade_id": "duplicate-rank-canonical-trade",
        "stock_code": selected.stock_code,
        "trade_date": execution.context.as_of_date.isoformat(),
        "source_type": source.source_type,
        "source_id": source.source_id,
        "source_snapshot_hash": source.source_snapshot_hash,
        "source_summary": source.source_summary,
        "quantity": 1,
        "price": "1.00",
    }

    journey = DecisionOutcomeJourneyService(
        recommendation_reader=adapter,
        evidence_reader=MemoryEvidence(()),
        portfolio_trade_reader=MemoryTrades((trade,)),
    ).build(execution.result_id)

    assert journey.recommendation_result.link_status is JourneyLinkStatus.LINKED
    assert len(journey.portfolio_trades) == 1
    assert journey.portfolio_trades[0].link_status is JourneyLinkStatus.CONFLICT
    assert any(
        item.code == "portfolio_trade_canonical_root_unverified"
        for item in journey.diagnostics
    )


def test_query_get_missing_database_is_read_only_and_does_not_custody(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "absent-output-root"
    runs_dir = output_root / "recommendation" / "runs"
    database_path = runs_dir / "recommendation_runs.db"
    adapter = JsonRecommendationReadAdapter(output_root)

    assert not output_root.exists()
    assert adapter._queries.get("missing-result") is None
    assert adapter.read_result("missing-result") is None
    with pytest.raises(FileNotFoundError):
        adapter.path_for("missing-result")
    assert not output_root.exists()
    assert not runs_dir.exists()
    assert not database_path.exists()


def test_journey_rejects_canonical_read_model_without_canonical_integrity_basis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "unsupported-integrity-output"
    execution, _artifact_location = _save_canonical_recommendation(output_root)
    adapter = JsonRecommendationReadAdapter(output_root)
    query = adapter._queries
    original_get = query.get

    def unsupported_get(result_id: str) -> Any:
        read_model = original_get(result_id)
        if read_model is None:
            return None
        return replace(read_model, integrity_basis="legacy_read_time_hash_only")

    monkeypatch.setattr(query, "get", unsupported_get)
    journey = DecisionOutcomeJourneyService(
        recommendation_reader=adapter,
        evidence_reader=MemoryEvidence(()),
    ).build(execution.result_id)

    assert journey.recommendation_result.link_status is JourneyLinkStatus.UNKNOWN
    assert journey.recommendation_result.result_path is None
    assert any(
        item.code == "recommendation_read_failure"
        for item in journey.diagnostics
    )


def test_journey_rejects_non_completed_canonical_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "non-completed-output"
    execution, _artifact_location = _save_canonical_recommendation(output_root)
    adapter = JsonRecommendationReadAdapter(output_root)
    query = adapter._queries
    original_get = query.get

    def unsupported_get(result_id: str) -> Any:
        read_model = original_get(result_id)
        if read_model is None or read_model.execution is None:
            return read_model
        failed_execution = replace(
            read_model.execution,
            status=ExecutionStatus.FAILED,
            decision=None,
            failure_reason="synthetic failure",
        )
        return replace(read_model, execution=failed_execution)

    monkeypatch.setattr(query, "get", unsupported_get)
    journey = DecisionOutcomeJourneyService(
        recommendation_reader=adapter,
        evidence_reader=MemoryEvidence(()),
    ).build(execution.result_id)

    assert journey.recommendation_result.link_status is JourneyLinkStatus.UNKNOWN
    assert journey.recommendation_result.result_path is None
    assert any(
        item.code == "recommendation_read_failure"
        for item in journey.diagnostics
    )


def test_journey_list_result_ids_uses_verified_query_inventory_not_glob(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "inventory-output"
    execution, _artifact_location = _save_canonical_recommendation(output_root)
    legacy_id = "journey-indexed-legacy"
    legacy_payload = _result()
    legacy_payload["result_id"] = legacy_id
    _register_legacy_recommendation(output_root, legacy_id, legacy_payload)
    runs_dir = output_root / "recommendation" / "runs"
    unindexed_id = "journey-unindexed-stray"
    (runs_dir / f"{unindexed_id}.json").write_bytes(
        json.dumps({**_result(), "result_id": unindexed_id}).encode("utf-8")
    )

    adapter = JsonRecommendationReadAdapter(output_root)

    assert adapter.list_result_ids() == tuple(sorted((execution.result_id, legacy_id)))


def test_journey_fails_closed_when_legacy_query_readback_changes_identity_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result_id = "journey-legacy-readback-mismatch"
    output_root = tmp_path / "output"
    payload = {**_result(), "result_id": result_id}
    _register_legacy_recommendation(output_root, result_id, payload)
    adapter = JsonRecommendationReadAdapter(output_root)
    query = adapter._queries
    original_projection = query.get_legacy_original_payload

    def mismatched_projection(candidate_id: str, **kwargs: bool) -> Any:
        projection = original_projection(candidate_id, **kwargs)
        if projection is None:
            return None
        return replace(projection, raw_artifact_sha256="sha256:" + "0" * 64)

    monkeypatch.setattr(query, "get_legacy_original_payload", mismatched_projection)
    service = DecisionOutcomeJourneyService(
        recommendation_reader=adapter,
        evidence_reader=MemoryEvidence(()),
    )

    journey = service.build(result_id)

    assert journey.recommendation_result.link_status is JourneyLinkStatus.UNKNOWN
    assert journey.recommendation_result.result_path is None
    assert any(
        item.code == "recommendation_read_failure"
        for item in journey.diagnostics
    )


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
