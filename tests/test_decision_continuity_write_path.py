"""Increment A：決策 identity／候選池／研究日記儲存契約。"""

from __future__ import annotations

import json
import multiprocessing
from pathlib import Path
from queue import Empty
import sqlite3
from types import SimpleNamespace
from typing import Any

import pytest

from app_module.decision_outcome_journey import (
    DecisionOutcomeJourneyService,
    JsonlJournalReadAdapter,
)
from app_module.dtos.decision_continuity_dtos import (
    ACTION_ACCEPTED,
    ACTION_NOTE,
    ACTION_REMOVED,
    DecisionContinuityRevision,
    DecisionIdentity,
)
from app_module.journal_service import JournalService
from app_module.portfolio_store import PortfolioJsonlStore
from app_module.watchlist_service import WatchlistService
from data_module.watchlist_migration import migrate_watchlist_copy
from data_module.watchlist_repository import WatchlistRepository
from data_module.watchlist_sqlite_cow import convert_watchlist_sqlite


def _config(root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        output_root=root / "output",
        resolve_output_path=lambda name: root / "output" / name,
    )


def _identity(result_id: str = "result-001", stock_code: str = "2330") -> DecisionIdentity:
    return DecisionIdentity(
        result_id=result_id,
        stock_code=stock_code,
        source_snapshot_id="snapshot-001",
        source_snapshot_hash="sha256:snapshot-001",
        decision_date="2026-09-14",
    )


def _watchlist_payload() -> dict[str, object]:
    identity = _identity().to_dict()
    return {
        "version": 1,
        "name": "候選池",
        "description": "測試",
        "created_at": "2026-09-14T09:00:00+00:00",
        "updated_at": "2026-09-14T09:00:00+00:00",
        "items": [
            {
                "stock_code": "2330",
                "stock_name": "台積電",
                "added_at": "2026-09-14T09:00:00+00:00",
                "source": "recommendation",
                "source_id": "legacy-provider-id",
                "notes": "",
                "tags": [],
                "decision_identity": identity,
            }
        ],
    }


def _watchlist_competitor(
    db_path: str,
    barrier: Any,
    result_queue: Any,
    revision_id: str,
) -> None:
    """spawn target: two writers race on one optimistic SQLite revision."""

    repository = WatchlistRepository(Path(db_path))
    barrier.wait()
    try:
        revision = repository.save(
            "default",
            {**_watchlist_payload(), "description": revision_id},
            expected_revision=1,
            revision_id=revision_id,
            operation="updated",
        )
    except Exception as exc:
        result_queue.put(("error", type(exc).__name__, str(exc)))
    else:
        result_queue.put(("ok", revision_id, revision))


def _journal_competitor(
    output_root: str,
    barrier: Any,
    result_queue: Any,
    record: dict[str, object],
) -> None:
    """spawn target: race clear/update against the same exact journal head."""

    store = PortfolioJsonlStore(Path(output_root))
    barrier.wait()
    try:
        store.append_journal_revision(record)
    except Exception as exc:
        result_queue.put(("error", type(exc).__name__, str(exc)))
    else:
        result_queue.put(("ok", str(record["revision_id"])))


def _join_processes(processes: list[Any]) -> None:
    for process in processes:
        process.join(timeout=20)
        assert process.exitcode == 0


def test_identity_merge_conflict_and_deep_immutable_revision_payload() -> None:
    identity = _identity()
    assert DecisionIdentity.from_mapping(
        {"decision_identity": identity.to_dict(), **identity.to_dict()},
        default_stock_code="2330",
    ) == identity
    with pytest.raises(ValueError, match="conflicting decision identity field"):
        DecisionIdentity.from_mapping(
            {
                "decision_identity": {"result_id": "r-nested", "stock_code": "2330"},
                "result_id": "r-top",
                "stock_code": "2330",
            }
        )
    with pytest.raises(ValueError, match="stock_code conflicts"):
        DecisionIdentity.from_mapping(
            {"result_id": "r", "stock_code": "2330"},
            default_stock_code="2317",
        )
    with pytest.raises(ValueError, match="stock_code conflicts"):
        DecisionIdentity.from_mapping(identity, default_stock_code="2317")
    with pytest.raises(ValueError, match="stock_code conflicts"):
        DecisionIdentity.from_mapping(
            {"decision_identity": {"result_id": "r", "stock_code": "2330"}},
            default_stock_code="2317",
        )

    unknown = DecisionIdentity(result_id="r", stock_code="2330", identity_status="unknown")
    assert unknown.candidate_key == ("r", "2330")
    assert unknown.is_linked is False

    source = {"nested": {"values": [1], "label": "before"}}
    revision = DecisionContinuityRevision(
        revision_id="rev-001",
        continuity_event_id="event-001",
        action=ACTION_ACCEPTED,
        entity_type="decision",
        entity_id="candidate:r:2330",
        decision_identity=identity,
        created_at="2026-09-14T09:00:00+00:00",
        payload=source,
    )
    source["nested"]["values"].append(2)
    assert revision.payload["nested"]["values"] == (1,)
    with pytest.raises(TypeError):
        revision.payload["nested"]["values"][0] = 9  # type: ignore[index]
    with pytest.raises(TypeError):
        revision.payload["nested"]["new"] = "blocked"  # type: ignore[index]
    exported = revision.to_dict()
    exported["payload"]["nested"]["values"].append(3)
    assert revision.payload["nested"]["values"] == (1,)
    with pytest.raises(TypeError):
        DecisionContinuityRevision(
            revision_id="rev-bad",
            continuity_event_id="event-bad",
            action=ACTION_ACCEPTED,
            entity_type="decision",
            entity_id="candidate:r:2330",
            payload={"bad": {"set"}},
        )


def test_watchlist_repository_history_conflict_tombstone_and_legacy_baseline(tmp_path: Path) -> None:
    db_path = tmp_path / "watchlists.db"
    repository = WatchlistRepository(db_path, initialize=True)
    payload = _watchlist_payload()
    assert repository.save(
        "default",
        payload,
        expected_revision=None,
        revision_id="watch-rev-1",
        continuity_event_id="watch-event-1",
        operation="added",
    ) == 1
    assert repository.save(
        "default",
        payload,
        expected_revision=None,
        revision_id="watch-rev-1",
        continuity_event_id="watch-event-1",
        operation="added",
    ) == 1
    with pytest.raises(RuntimeError, match="event_conflict"):
        repository.save(
            "default",
            {**payload, "description": "changed"},
            expected_revision=1,
            revision_id="watch-rev-1",
            continuity_event_id="watch-event-1",
            operation="added",
        )

    changed = {**payload, "description": "changed"}
    assert repository.save(
        "default",
        changed,
        expected_revision=1,
        revision_id="watch-rev-2",
        continuity_event_id="watch-event-2",
        operation="updated",
        revision_of="watch-rev-1",
    ) == 2
    with pytest.raises(RuntimeError, match="revision_conflict"):
        repository.save(
            "default",
            {**changed, "description": "stale"},
            expected_revision=1,
            revision_id="watch-rev-stale",
            operation="updated",
        )

    assert repository.delete(
        "default",
        expected_revision=2,
        revision_id="watch-rev-3",
        continuity_event_id="watch-event-3",
    )
    assert repository.load("default") is None
    deleted = repository.load("default", include_deleted=True)
    assert deleted is not None and deleted[0] == changed and deleted[1] == 3
    assert repository.list_ids() == []
    history = repository.list_revisions("default")
    assert [item["operation"] for item in history] == ["added", "updated", "removed"]
    assert history[0]["payload"] == payload
    assert history[-1]["payload"] == changed

    old_db = tmp_path / "old.db"
    old_payload = {"version": 1, "items": [{"stock_code": "2317"}]}
    with sqlite3.connect(old_db) as conn:
        conn.execute(
            "CREATE TABLE watchlists("
            "watchlist_id TEXT PRIMARY KEY,payload_json TEXT NOT NULL,"
            "revision INTEGER NOT NULL,source_hash TEXT NOT NULL DEFAULT '')"
        )
        conn.execute(
            "INSERT INTO watchlists VALUES(?,?,?,?)",
            ("default", json.dumps(old_payload), 4, "old-hash"),
        )
    source_bytes = old_db.read_bytes()
    legacy_repository = WatchlistRepository(old_db)
    storage = legacy_repository.detect_storage_format()
    assert storage["schema_version"] == 1
    assert storage["requires_copy_on_write"] is True
    with pytest.raises(RuntimeError, match="watchlist_schema_requires_copy_on_write"):
        WatchlistRepository(old_db, initialize=True)
    assert old_db.read_bytes() == source_bytes

    cow_db = tmp_path / "old-cow.db"
    converted = convert_watchlist_sqlite(
        old_db,
        cow_db,
        capacity_preflight=lambda _request: True,
    )
    assert converted["status"] == "ready", converted
    upgraded = WatchlistRepository(cow_db, initialize=True)
    baseline = upgraded.list_revisions("default")
    assert baseline[0]["operation"] == "migration_baseline"
    assert baseline[0]["is_synthetic_baseline"] is True
    assert baseline[0]["source_revision_id"] == ""
    assert baseline[0]["payload"] == old_payload
    upgraded.save(
        "default",
        {**old_payload, "description": "new"},
        expected_revision=4,
        revision_id="upgrade-rev-5",
        operation="updated",
    )
    assert upgraded.list_revisions("default")[0]["payload"] == old_payload
    upgraded.delete("default", expected_revision=5, revision_id="upgrade-rev-6")
    assert upgraded.load("default", include_deleted=True)[0] == {
        **old_payload,
        "description": "new",
    }
    assert old_db.read_bytes() == source_bytes


def test_watchlist_sqlite_cross_process_competition_is_single_winner(tmp_path: Path) -> None:
    db_path = tmp_path / "race.db"
    repository = WatchlistRepository(db_path, initialize=True)
    repository.save(
        "default",
        _watchlist_payload(),
        expected_revision=None,
        revision_id="race-base",
        operation="added",
    )
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    result_queue = context.Queue()
    processes = [
        context.Process(
            target=_watchlist_competitor,
            args=(str(db_path), barrier, result_queue, f"race-{index}"),
        )
        for index in (1, 2)
    ]
    for process in processes:
        process.start()
    _join_processes(processes)
    results = [result_queue.get(timeout=5) for _ in processes]
    assert sum(item[0] == "ok" for item in results) == 1
    assert sum(item[0] == "error" and "conflict" in item[2] for item in results) == 1
    assert len(WatchlistRepository(db_path).list_revisions("default")) == 2


def test_watchlist_legacy_import_is_bounded_and_does_not_promote_source_id(tmp_path: Path) -> None:
    source = tmp_path / "default.json"
    payload = {
        "version": 1,
        "name": "legacy",
        "description": "",
        "created_at": "2026-09-14T09:00:00",
        "updated_at": "2026-09-14T09:00:00",
        "items": [
            {
                "stock_code": "2330",
                "stock_name": "台積電",
                "added_at": "2026-09-14T09:00:00",
                "source": "recommendation",
                "source_id": "provider-or-result-ambiguous",
                "notes": "",
                "tags": [],
            }
        ],
    }
    source.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    before = source.read_bytes()
    target = tmp_path / "copy.db"
    proof = migrate_watchlist_copy(source, target, sandbox_root=tmp_path)
    assert migrate_watchlist_copy(source, target, sandbox_root=tmp_path) == proof
    service = WatchlistService(
        _config(tmp_path), repository=WatchlistRepository(target)
    )
    item = service.get_stocks()[0]
    assert item["source_id"] == "provider-or-result-ambiguous"
    assert item["decision_identity"]["result_id"] == ""
    assert item["decision_identity"]["identity_status"] == "unknown"
    assert source.read_bytes() == before
    assert len(service.list_watchlist_revisions()) == 1


def test_journal_delete_clear_preserve_legacy_bytes_and_idempotent_retry(tmp_path: Path) -> None:
    service = JournalService(_config(tmp_path))
    service.add_journal_entry(body="Body 1", title="One", stock_code="2330", journal_id="j-1")
    service.add_journal_entry(body="Body 2", title="Two", stock_code="2317", journal_id="j-2")
    path = service.store.journal_file
    before_delete = path.read_bytes()

    assert service.delete_journal_entry("j-1", revision_id="remove-1", reason="修訂")
    after_delete = path.read_bytes()
    assert after_delete.startswith(before_delete)
    assert [entry.journal_id for entry in service.list_journal_entries()] == ["j-2"]
    history = service.list_journal_history()
    assert len(history) == 3
    assert history[-1]["action"] == ACTION_REMOVED
    assert service.delete_journal_entry("j-1", revision_id="remove-1", reason="修訂")
    assert len(service.list_journal_history()) == 3
    with pytest.raises(RuntimeError, match="event_conflict"):
        service.delete_journal_entry("j-1", revision_id="remove-1", reason="不同原因")

    assert service.clear_all_journals() == 1
    assert service.list_journal_entries() == []
    assert service.clear_all_journals() == 0
    assert len(service.list_journal_history()) == 4
    assert path.read_bytes().startswith(after_delete)


def test_journal_corrupt_stream_is_not_overwritten_and_research_actions_make_no_trade(
    tmp_path: Path,
) -> None:
    service = JournalService(_config(tmp_path))
    service.add_journal_entry(body="valid", journal_id="j-1")
    path = service.store.journal_file
    path.write_bytes(path.read_bytes() + b"{partial")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="Invalid JSONL"):
        service.delete_journal_entry("j-1")
    with pytest.raises(ValueError, match="Invalid JSONL"):
        service.clear_all_journals()
    assert path.read_bytes() == before

    clean = JournalService(_config(tmp_path / "clean"))
    identity = _identity()
    accepted = clean.record_decision_action(
        ACTION_ACCEPTED,
        identity,
        revision_id="action-1",
        entity_id="candidate:result-001:2330",
    )
    assert accepted.created_at.endswith("+00:00")
    assert clean.record_decision_action(
        ACTION_ACCEPTED,
        identity,
        revision_id="action-1",
        entity_id="candidate:result-001:2330",
    ) == accepted
    with pytest.raises(RuntimeError, match="event_conflict"):
        clean.record_decision_action(
            ACTION_ACCEPTED,
            identity,
            note="different",
            revision_id="action-1",
            entity_id="candidate:result-001:2330",
        )
    note = clean.record_decision_action(
        ACTION_NOTE,
        identity,
        body="follow-up note",
        revision_id="note-1",
        journal_id="journal-note-1",
    )
    assert note.entity_type == "journal"
    assert clean.list_journal_entries()[0].journal_id == "journal-note-1"
    assert not clean.store.trades_file.exists()
    assert {item.action for item in clean.list_decision_revisions()} == {
        ACTION_ACCEPTED,
        ACTION_NOTE,
    }

    other = clean.record_decision_action(
        ACTION_NOTE,
        _identity(stock_code="2317"),
        body="other stock",
        revision_id="note-2",
        journal_id="journal-note-2",
        linked_id="result-001",
    )
    assert other.candidate_key == ("result-001", "2317")
    assert {entry.journal_id for entry in clean.list_journal_entries()} == {
        "journal-note-1",
        "journal-note-2",
    }


def test_journal_cross_process_same_head_allows_one_clear_or_update(tmp_path: Path) -> None:
    service = JournalService(_config(tmp_path))
    initial = service.record_decision_action(
        ACTION_NOTE,
        _identity(),
        body="initial",
        revision_id="journal-base",
        journal_id="journal-race",
    )
    update = DecisionContinuityRevision(
        revision_id="journal-update",
        continuity_event_id="journal-update",
        action=ACTION_NOTE,
        entity_type="journal",
        entity_id="journal-race",
        decision_identity=_identity(),
        revision_of=initial.revision_id,
        created_at="2026-09-14T10:00:00+00:00",
        payload={"journal_id": "journal-race", "body": "updated", "stock_code": "2330"},
    ).to_dict()
    clear = DecisionContinuityRevision(
        revision_id="journal-clear",
        continuity_event_id="journal-clear",
        action=ACTION_REMOVED,
        entity_type="journal",
        entity_id="journal-race",
        decision_identity=_identity(),
        revision_of=initial.revision_id,
        created_at="2026-09-14T10:00:00+00:00",
        payload={"journal_id": "journal-race", "body": "initial", "stock_code": "2330"},
    ).to_dict()
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    result_queue = context.Queue()
    processes = [
        context.Process(
            target=_journal_competitor,
            args=(str(tmp_path / "output"), barrier, result_queue, record),
        )
        for record in (update, clear)
    ]
    for process in processes:
        process.start()
    _join_processes(processes)
    results = [result_queue.get(timeout=5) for _ in processes]
    assert sum(item[0] == "ok" for item in results) == 1
    assert sum(item[0] == "error" and "chain_conflict" in item[2] for item in results) == 1
    history = service.list_journal_history()
    assert len(history) == 2
    assert len(service.list_journal_entries()) in {0, 1}


def test_missing_or_conflict_identity_cannot_be_forced_linked_and_same_stock_results_survive(
    tmp_path: Path,
) -> None:
    repository = WatchlistRepository(tmp_path / "identity.db", initialize=True)
    incomplete = {
        "version": 1,
        "items": [
            {
                "stock_code": "2330",
                "stock_name": "台積電",
                "added_at": "2026-09-14T09:00:00+00:00",
                "source": "recommendation",
                "decision_identity": {
                    "result_id": "",
                    "stock_code": "2330",
                    "identity_status": "unknown",
                },
            }
        ],
    }
    with pytest.raises(ValueError, match="complete payload identity"):
        repository.save(
            "default",
            incomplete,
            expected_revision=None,
            revision_id="forced-linked",
            identity_status="linked",
        )
    service = WatchlistService(
        _config(tmp_path),
        repository=WatchlistRepository(tmp_path / "same-stock.db", initialize=True),
    )
    assert service.add_stocks(
        [
            {"stock_code": "2330", "stock_name": "台積電", "result_id": "result-a"},
            {"stock_code": "2330", "stock_name": "台積電", "result_id": "result-b"},
        ],
        source="recommendation",
    ) == 2
    assert [item["decision_identity"]["result_id"] for item in service.get_stocks()] == [
        "result-a",
        "result-b",
    ]
    unknown_service = JournalService(_config(tmp_path / "unknown"))
    unknown = unknown_service.record_decision_action(
        ACTION_ACCEPTED,
        DecisionIdentity(result_id="result-unknown", stock_code="2330", identity_status="unknown"),
        revision_id="unknown-action",
        entity_id="candidate:result-unknown:2330",
    )
    assert unknown.candidate_key == ("result-unknown", "2330")
    assert unknown.decision_identity.is_linked is False
    assert unknown_service.list_decision_revisions()[0].decision_identity.is_linked is False


def test_revision_retry_without_entity_reuses_original_entity_and_timestamp(tmp_path: Path) -> None:
    service = JournalService(_config(tmp_path))
    identity = _identity()
    first = service.record_decision_action(
        ACTION_NOTE,
        identity,
        body="retry-safe",
        revision_id="request-1",
    )
    second = service.record_decision_action(
        ACTION_NOTE,
        identity,
        body="retry-safe",
        revision_id="request-1",
    )
    assert second == first
    assert second.entity_id == first.entity_id
    assert second.created_at == first.created_at
    assert len(service.list_journal_history()) == 1


def test_journal_revision_batch_separates_valid_no_newline_stream(tmp_path: Path) -> None:
    store = PortfolioJsonlStore(tmp_path / "output")
    legacy = {"journal_id": "legacy", "body": "valid", "stock_code": "2330"}
    store.journal_file.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
    revision = DecisionContinuityRevision(
        revision_id="batch-note",
        continuity_event_id="batch-note",
        action=ACTION_NOTE,
        entity_type="journal",
        entity_id="batch-journal",
        decision_identity=_identity(),
        created_at="2026-09-14T11:00:00+00:00",
        payload={"journal_id": "batch-journal", "body": "new", "stock_code": "2330"},
    )
    store.append_journal_revisions([revision.to_dict()])
    history = store.load_journal_history()
    assert history[0]["journal_id"] == "legacy"
    assert history[1]["entity_id"] == "batch-journal"
    assert [row["journal_id"] for row in store.load_journal_entries()] == [
        "legacy",
        "batch-journal",
    ]


def test_journal_as_of_projection_does_not_leak_future_revision(tmp_path: Path) -> None:
    store = PortfolioJsonlStore(tmp_path / "output")
    store.append_journal_entry(
        {
            "journal_id": "j-as-of",
            "body": "old note",
            "stock_code": "2330",
            "created_at": "2026-09-14T01:00:00+00:00",
        }
    )
    future = DecisionContinuityRevision(
        revision_id="future-remove",
        continuity_event_id="future-remove",
        action=ACTION_REMOVED,
        entity_type="journal",
        entity_id="j-as-of",
        decision_identity=_identity(),
        created_at="2026-09-14T03:00:00+00:00",
        payload={"journal_id": "j-as-of", "body": "old note", "stock_code": "2330"},
    )
    store.append_journal_revision(future.to_dict())
    adapter = JsonlJournalReadAdapter(store.journal_file)
    assert [
        row["journal_id"]
        for row in adapter.list_entries_as_of("2026-09-14T02:00:00+00:00")
    ] == ["j-as-of"]
    assert adapter.list_entries_as_of("2026-09-14T04:00:00+00:00") == []
    assert adapter.list_entries() == []


class _RecommendationReader:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def read_result(self, result_id: str) -> dict[str, object] | None:
        return self.payload if result_id == self.payload["result_id"] else None


def test_journey_build_as_of_uses_revision_observation_time(tmp_path: Path) -> None:
    output_root = tmp_path / "journey-output"
    output_root.mkdir(parents=True)
    result = {
        "result_id": "result-001",
        "result_name": "test",
        "created_at": "2026-09-14T00:00:00+00:00",
        "config": {
            "decision_date": "2026-09-14",
            "source_snapshot_hash": "sha256:snapshot-001",
        },
        "run_context": {
            "as_of_date": "2026-09-14",
            "source_id": "provider-001",
        },
        "recommendations": [
            {"證券代號": "2330", "證券名稱": "台積電", "recommendation_rank": 1}
        ],
    }
    store = PortfolioJsonlStore(output_root)
    store.append_journal_entry(
        {
            "journal_id": "journey-journal",
            "linked_type": "recommendation_result",
            "linked_id": "result-001",
            "source_id": "result-001",
            "source_snapshot_hash": "sha256:snapshot-001",
            "stock_code": "2330",
            "created_at": "2026-09-14T01:00:00+00:00",
        }
    )
    tombstone = DecisionContinuityRevision(
        revision_id="journey-tombstone",
        continuity_event_id="journey-tombstone",
        action=ACTION_REMOVED,
        entity_type="journal",
        entity_id="journey-journal",
        decision_identity=_identity(),
        created_at="2026-09-14T03:00:00+00:00",
        payload={"journal_id": "journey-journal", "stock_code": "2330"},
    )
    store.append_journal_revision(tombstone.to_dict())
    journey_service = DecisionOutcomeJourneyService(
        recommendation_reader=_RecommendationReader(result),
        journal_reader=JsonlJournalReadAdapter(store.journal_file),
    )
    at_t2 = journey_service.build(
        "result-001",
        query_boundary="2026-09-14T02:00:00+00:00",
    )
    at_t4 = journey_service.build(
        "result-001",
        query_boundary="2026-09-14T04:00:00+00:00",
    )
    assert len(at_t2.journal_entries) == 1
    assert len(at_t4.journal_entries) == 0


def test_valid_jsonl_without_final_newline_gets_separator_without_losing_prefix(tmp_path: Path) -> None:
    store = PortfolioJsonlStore(tmp_path / "output")
    store.journal_file.write_text(
        json.dumps({"journal_id": "legacy", "body": "ok"}, ensure_ascii=False),
        encoding="utf-8",
    )
    prefix = store.journal_file.read_bytes()
    store.append_journal_entry({"journal_id": "new", "body": "ok"})
    raw = store.journal_file.read_bytes()
    assert raw.startswith(prefix + b"\n")
    assert [row["journal_id"] for row in store.load_journal_history()] == ["legacy", "new"]
