"""Watchlist item-event storage compatibility and recovery contracts."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from threading import Barrier
from types import SimpleNamespace

import pytest

from app_module.watchlist_service import WatchlistService
from data_module.watchlist_repository import (
    WatchlistRepository,
    WatchlistStorageCapacityError,
    WatchlistStorageIntegrityError,
)


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
        separators=(",", ":"),
    )


def _legacy_json(value: object) -> str:
    """舊 v2 repository 使用 json.dumps 的預設空白格式。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def _sha256(raw: str | bytes) -> str:
    encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
    return hashlib.sha256(encoded).hexdigest()


def _payload(items: list[dict[str, object]]) -> dict[str, object]:
    return {
        "version": 1,
        "name": "隔離觀察清單",
        "description": "item event fixture",
        "created_at": "2026-10-05T00:00:00+00:00",
        "updated_at": "2026-10-05T00:00:00+00:00",
        "items": deepcopy(items),
    }


def _item(
    stock_code: str,
    source: str,
    source_id: str,
    *,
    notes: str = "",
    research_bookmark: dict[str, object] | None = None,
) -> dict[str, object]:
    item: dict[str, object] = {
        "stock_code": stock_code,
        "stock_name": "隔離測試股",
        "added_at": "2026-10-05T00:00:00+00:00",
        "source": source,
        "source_id": source_id,
        "notes": notes,
        "tags": [],
    }
    if research_bookmark is not None:
        item["research_bookmark"] = deepcopy(research_bookmark)
    return item


def _daily_bookmark(bookmark_id: str) -> dict[str, object]:
    return {
        "schema_version": "daily-market-research-bookmark.v1",
        "bookmark_id": bookmark_id,
        "payload_sha256": "a" * 64,
        "query_sha256": "b" * 64,
        "context": {
            "source_snapshot_id": "snapshot:daily:2026-10-02",
            "source_snapshot_hash": "c" * 64,
            "method_contracts": {
                "close_above_ma20": {"name": "close_above_ma20", "version": "1.0.0"}
            },
            "method_contracts_sha256": "d" * 64,
            "condition_keys": ["close_above_ma20"],
        },
    }


def _rank_bookmark(bookmark_id: str) -> dict[str, object]:
    return {
        "schema_version": "daily-market-research-bookmark.v2",
        "bookmark_id": bookmark_id,
        "payload_sha256": "e" * 64,
        "query_sha256": "f" * 64,
        "context": {
            "source_snapshot_id": "snapshot:daily:2026-10-02",
            "source_snapshot_hash": "1" * 64,
            "rank_context": {
                "rank_snapshot_id": "rank-snapshot:2026-10-02",
                "source_hash": "2" * 64,
                "selected_stock_code": "2330",
                "selected_rank": 1,
                "method_name": "fixture-rank-method",
                "method_version": "1.0.0",
                "method_contract_sha256": "3" * 64,
            },
        },
    }


def _create_legacy_v1(
    database: Path,
    payload: dict[str, object],
    *,
    with_source_hash: bool,
) -> None:
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        source_hash_column = ", source_hash TEXT NOT NULL DEFAULT ''" if with_source_hash else ""
        connection.execute(
            "CREATE TABLE watchlists ("
            "watchlist_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, revision INTEGER NOT NULL"
            f"{source_hash_column})"
        )
        values: tuple[object, ...] = ("default", _legacy_json(payload), 7)
        placeholders = "?,?,?"
        if with_source_hash:
            values += (_sha256("legacy-v1-source"),)
            placeholders += ",?"
        connection.execute(
            f"INSERT INTO watchlists VALUES({placeholders})",
            values,
        )


def _create_legacy_v2(database: Path, payload: dict[str, object]) -> None:
    database.parent.mkdir(parents=True, exist_ok=True)
    payload_json = _legacy_json(payload)
    source_hash = _sha256("legacy-v2-source")
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE watchlists ("
            "watchlist_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, revision INTEGER NOT NULL, "
            "source_hash TEXT NOT NULL DEFAULT '', is_deleted INTEGER NOT NULL DEFAULT 0, "
            "last_revision_id TEXT NOT NULL DEFAULT '')"
        )
        connection.execute(
            "CREATE TABLE watchlist_revisions ("
            "revision_id TEXT PRIMARY KEY, watchlist_id TEXT NOT NULL, revision INTEGER NOT NULL, "
            "operation TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL, "
            "source_hash TEXT NOT NULL DEFAULT '', identity_status TEXT NOT NULL DEFAULT 'unknown', "
            "continuity_event_id TEXT NOT NULL DEFAULT '', revision_of TEXT NOT NULL DEFAULT '', "
            "created_at TEXT NOT NULL, UNIQUE(watchlist_id, revision))"
        )
        connection.execute(
            "CREATE INDEX idx_watchlist_revisions_watchlist "
            "ON watchlist_revisions(watchlist_id, revision)"
        )
        connection.execute(
            "INSERT INTO watchlists VALUES(?,?,?,?,?,?)",
            ("default", payload_json, 7, source_hash, 0, "legacy-v2-r7"),
        )
        connection.execute(
            "INSERT INTO watchlist_revisions VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                "legacy-v2-r7",
                "default",
                7,
                "legacy_import",
                payload_json,
                _sha256(payload_json),
                source_hash,
                "unknown",
                "",
                "",
                "2026-10-05T00:00:00+00:00",
            ),
        )


def _allow_capacity(_request: object) -> bool:
    return True


def _new_repository(database: Path) -> WatchlistRepository:
    return WatchlistRepository(
        database,
        initialize=True,
        capacity_preflight=_allow_capacity,
    )


def _read_revision_payload(
    repository: WatchlistRepository,
    revision_id: str,
) -> dict[str, object]:
    selected: dict[str, object] | None = None
    for record in repository.iter_revisions("default"):
        if record["revision_id"] == revision_id:
            payload = record["payload"]
            assert isinstance(payload, dict)
            selected = payload
    assert selected is not None
    return selected


def _history_metrics(repository: WatchlistRepository) -> tuple[int, int, int]:
    revision_count = 0
    full_payload_bytes = 0
    full_item_references = 0
    for record in repository.iter_revisions("default"):
        revision_count += 1
        payload = record["payload"]
        assert isinstance(payload, dict)
        assert record["payload_hash"] == _sha256(_canonical_json(payload))
        full_payload_bytes += len(_canonical_json(payload).encode("utf-8"))
        items = payload["items"]
        assert isinstance(items, list)
        full_item_references += len(items)
    return revision_count, full_payload_bytes, full_item_references


def _sidecars(database: Path) -> tuple[Path, ...]:
    return tuple(Path(f"{database}{suffix}") for suffix in ("-journal", "-wal", "-shm"))


@pytest.mark.parametrize(
    ("legacy_version", "with_source_hash"),
    [("v1", False), ("v1", True), ("v2", True)],
)
def test_v1_v2_are_read_without_byte_changes_or_implicit_initialize(
    tmp_path: Path,
    legacy_version: str,
    with_source_hash: bool,
) -> None:
    database = tmp_path / f"{legacy_version}-{with_source_hash}" / "watchlists.db"
    payload = _payload([_item("2330", "manual", "legacy-manual-2330")])
    if legacy_version == "v1":
        _create_legacy_v1(database, payload, with_source_hash=with_source_hash)
        expected_format = "watchlist-full-payload.v1"
    else:
        _create_legacy_v2(database, payload)
        expected_format = "watchlist-full-payload.v2"
    original_bytes = database.read_bytes()

    reader = WatchlistRepository(database)
    detected = reader.detect_storage_format()
    assert detected["storage_format"] == expected_format
    assert reader.load("default") == (payload, 7)
    assert database.read_bytes() == original_bytes
    assert not any(path.exists() for path in _sidecars(database))

    with pytest.raises(RuntimeError) as refusal:
        WatchlistRepository(
            database,
            initialize=True,
            capacity_preflight=_allow_capacity,
        )
    assert getattr(refusal.value, "code", "") == "watchlist_schema_requires_copy_on_write" or (
        "watchlist_schema_requires_copy_on_write" in str(refusal.value)
    )
    assert database.read_bytes() == original_bytes
    assert not any(path.exists() for path in _sidecars(database))


def test_publication_revision_delete_and_selected_history_restore_keep_item_identity(
    tmp_path: Path,
) -> None:
    database = tmp_path / "watchlists.db"
    repository = _new_repository(database)
    manual = _item("2330", "manual", "manual-2330")
    daily = _item(
        "2330",
        "daily_market_research_bookmark",
        "daily-bookmark-2330",
        research_bookmark=_daily_bookmark("daily-bookmark-2330"),
    )
    ranked = _item(
        "2330",
        "original_stock_ranking_bookmark",
        "rank-bookmark-2330",
        research_bookmark=_rank_bookmark("rank-bookmark-2330"),
    )
    first_payload = _payload([manual, daily, ranked])
    first_revision = repository.save(
        "default",
        first_payload,
        expected_revision=None,
        revision_id="publish-r1",
        operation="published",
    )

    revised_payload = deepcopy(first_payload)
    revised_manual = revised_payload["items"][0]
    assert isinstance(revised_manual, dict)
    revised_manual["notes"] = "只修訂此項目"
    revised_payload["updated_at"] = "2026-10-05T00:01:00+00:00"
    second_revision = repository.save(
        "default",
        revised_payload,
        expected_revision=first_revision,
        revision_id="publish-r2",
        operation="updated",
    )

    removed_payload = deepcopy(revised_payload)
    removed_payload["items"] = [
        item
        for item in revised_payload["items"]
        if not (item["source_id"] == "daily-bookmark-2330")
    ]
    removed_payload["updated_at"] = "2026-10-05T00:02:00+00:00"
    third_revision = repository.save(
        "default",
        removed_payload,
        expected_revision=second_revision,
        revision_id="remove-daily-bookmark",
        operation="item_removed",
    )

    assert repository.load("default") == (removed_payload, third_revision)
    current_items = repository.load("default")[0]["items"]
    assert [item["source_id"] for item in current_items] == [
        "manual-2330",
        "rank-bookmark-2330",
    ]
    assert current_items[1]["research_bookmark"] == ranked["research_bookmark"]
    assert current_items[1]["research_bookmark"]["context"]["rank_context"][
        "rank_snapshot_id"
    ] == "rank-snapshot:2026-10-02"

    tombstoned = repository.delete(
        "default",
        expected_revision=third_revision,
        revision_id="delete-watchlist",
    )
    assert tombstoned is True
    deleted_payload, deleted_revision = repository.load("default", include_deleted=True)
    assert deleted_payload == removed_payload
    assert deleted_revision == third_revision + 1
    assert repository.load("default") is None
    deleted_current = repository.get_current("default")
    assert deleted_current is not None and deleted_current["is_deleted"] is True

    selected_payload = _read_revision_payload(repository, "publish-r1")
    assert selected_payload == first_payload
    restored_revision = repository.save(
        "default",
        selected_payload,
        expected_revision=deleted_revision,
        revision_id="restore-publish-r1",
        operation="revision_restored",
    )
    reopened = WatchlistRepository(database)
    assert reopened.load("default") == (first_payload, restored_revision)

    restored_items = reopened.load("default")[0]["items"]
    assert len(restored_items) == 3
    assert {item["source_id"] for item in restored_items} == {
        "manual-2330",
        "daily-bookmark-2330",
        "rank-bookmark-2330",
    }
    by_source_id = {item["source_id"]: item for item in restored_items}
    assert by_source_id["daily-bookmark-2330"]["research_bookmark"] == daily[
        "research_bookmark"
    ]
    assert by_source_id["rank-bookmark-2330"]["research_bookmark"] == ranked[
        "research_bookmark"
    ]

    inventory = reopened.get_item_storage_inventory()
    assert inventory["complete"] is True
    assert inventory["object_hashes_valid"] is True
    assert inventory["delta_refs_valid"] is True
    assert inventory["revision_chain_valid"] is True
    assert inventory["current_projection_valid"] is True
    history_count, full_payload_bytes, full_item_references = _history_metrics(reopened)
    assert history_count == 5
    assert len(inventory["objects"]) == 4  # 三個初始項目與一個手動項目新版本。
    assert len(inventory["events"]) < full_item_references
    assert inventory["payload_bytes"] < full_payload_bytes
    assert _read_revision_payload(reopened, "publish-r1") == first_payload


def test_same_revision_id_retry_is_idempotent_and_service_duplicate_does_not_publish(
    tmp_path: Path,
) -> None:
    database = tmp_path / "watchlists.db"
    repository = _new_repository(database)
    payload = _payload([_item("2330", "manual", "manual-2330")])
    revision = repository.save(
        "default",
        payload,
        expected_revision=None,
        revision_id="stable-publication-id",
        operation="published",
    )
    original_bytes = database.read_bytes()
    original_inventory = repository.get_item_storage_inventory()
    retry_revision = repository.save(
        "default",
        payload,
        expected_revision=None,
        revision_id="stable-publication-id",
        operation="published",
    )
    assert retry_revision == revision
    assert repository.get_item_storage_inventory()["row_counts"] == original_inventory[
        "row_counts"
    ]
    assert database.read_bytes() == original_bytes

    from tests.test_rank_research_bookmark import _rank_bookmark

    settings = SimpleNamespace(
        output_root=tmp_path / "service-output",
        resolve_output_path=lambda name: tmp_path / "service-output" / name,
    )
    service_database = WatchlistService.repository_path(settings)
    service_repository = _new_repository(service_database)
    status = WatchlistService._repository_storage_status(
        service_database,
        service_database.with_name("default.json"),
    )
    service = WatchlistService(
        settings,
        repository=service_repository,
        storage_status=status,
    )
    bookmark = _rank_bookmark()
    first = service.add_rank_research_bookmark(bookmark)
    before_duplicate = service_database.read_bytes()
    before_counts = service_repository.get_item_storage_inventory()["row_counts"]
    second = service.add_rank_research_bookmark(bookmark)
    assert first.status == "added"
    assert second.status == "already_present"
    assert second.revision == first.revision
    assert service_database.read_bytes() == before_duplicate
    assert service_repository.get_item_storage_inventory()["row_counts"] == before_counts
    assert service.get_research_bookmark(bookmark.bookmark_id).to_dict() == bookmark.to_dict()


def test_two_controlled_writers_cannot_commit_from_the_same_revision(
    tmp_path: Path,
) -> None:
    database = tmp_path / "watchlists.db"
    seed = _new_repository(database)
    first_payload = _payload([_item("2330", "manual", "manual-2330")])
    base_revision = seed.save(
        "default",
        first_payload,
        expected_revision=None,
        revision_id="seed",
    )
    writers = [
        WatchlistRepository(database, capacity_preflight=_allow_capacity),
        WatchlistRepository(database, capacity_preflight=_allow_capacity),
    ]
    barrier = Barrier(2)

    def write(repository: WatchlistRepository, revision_id: str) -> tuple[str, object]:
        next_payload = _payload(
            [_item("2330", "manual", "manual-2330", notes=revision_id)]
        )
        barrier.wait(timeout=10)
        try:
            return (
                "committed",
                repository.save(
                    "default",
                    next_payload,
                    expected_revision=base_revision,
                    revision_id=revision_id,
                ),
            )
        except RuntimeError as exc:
            return ("conflict", str(exc))

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(
            executor.map(
                lambda args: write(*args),
                [(writers[0], "writer-a"), (writers[1], "writer-b")],
            )
        )

    assert sum(outcome[0] == "committed" for outcome in outcomes) == 1
    conflicts = [value for kind, value in outcomes if kind == "conflict"]
    assert len(conflicts) == 1
    assert "watchlist_revision_conflict" in str(conflicts[0])
    current = WatchlistRepository(database).load("default")
    assert current is not None and current[1] == base_revision + 1
    assert _history_metrics(WatchlistRepository(database))[0] == 2


def test_cancel_at_precommit_boundary_rolls_back_and_child_crash_reopens_last_good(
    tmp_path: Path,
) -> None:
    database = tmp_path / "watchlists.db"
    repository = _new_repository(database)
    original = _payload([_item("2330", "manual", "manual-2330")])
    revision = repository.save(
        "default",
        original,
        expected_revision=None,
        revision_id="last-good",
    )

    class _Cancelled(Exception):
        pass

    def cancel_before_commit(_operation: str, _revision_id: str) -> None:
        raise _Cancelled("cancelled at safe commit boundary")

    repository._before_commit = cancel_before_commit  # type: ignore[method-assign]
    with pytest.raises(_Cancelled):
        repository.save(
            "default",
            _payload([_item("2330", "manual", "manual-2330", notes="cancelled")]),
            expected_revision=revision,
            revision_id="cancelled-write",
        )
    assert WatchlistRepository(database).load("default") == (original, revision)
    assert _history_metrics(WatchlistRepository(database))[0] == 1

    crashed_payload = _payload(
        [_item("2330", "manual", "manual-2330", notes="child died before commit")]
    )
    child_script = "\n".join(
        [
            "import json, os, sys",
            "from pathlib import Path",
            "from data_module.watchlist_repository import WatchlistRepository",
            "database = Path(sys.argv[1])",
            "payload = json.loads(sys.argv[2])",
            "repository = WatchlistRepository(database, capacity_preflight=lambda request: True)",
            "repository._before_commit = lambda operation, revision_id: os._exit(73)",
            "repository.save('default', payload, expected_revision=1, revision_id='crashed-write')",
            "os._exit(74)",
        ]
    )
    project_root = Path(__file__).resolve().parents[1]
    child = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", child_script, str(database), json.dumps(crashed_payload)],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert child.returncode == 73, child.stderr

    # 以 read-write SQLite connection 開啟一次，讓 SQLite 自行復原 hot journal。
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
    recovered = WatchlistRepository(database)
    assert recovered.load("default") == (original, revision)
    assert _history_metrics(recovered)[0] == 1
    assert recovered.get_item_storage_inventory()["complete"] is True
    journal = Path(f"{database}-journal")
    if journal.exists():
        # SQLite may retain a cold rollback journal after crash recovery; a
        # zeroed magic header is acceptable once the last-good state reads back.
        assert journal.read_bytes()[:8] == bytes(8)


@pytest.mark.parametrize(
    ("decision", "expected_code"),
    [(False, "capacity_insufficient"), (None, "capacity_unknown")],
)
def test_capacity_denial_is_fail_closed_before_any_database_write(
    tmp_path: Path,
    decision: bool | None,
    expected_code: str,
) -> None:
    database = tmp_path / "watchlists.db"
    repository = _new_repository(database)
    original = _payload([_item("2330", "manual", "manual-2330")])
    revision = repository.save(
        "default",
        original,
        expected_revision=None,
        revision_id="last-good",
    )
    original_bytes = database.read_bytes()
    blocked = WatchlistRepository(
        database,
        capacity_preflight=lambda _request: decision,
    )

    with pytest.raises(WatchlistStorageCapacityError) as refusal:
        blocked.save(
            "default",
            _payload([_item("2330", "manual", "manual-2330", notes="must not persist")]),
            expected_revision=revision,
            revision_id="capacity-blocked",
        )
    assert refusal.value.code == expected_code
    assert database.read_bytes() == original_bytes
    assert not any(path.exists() for path in _sidecars(database))
    assert WatchlistRepository(database).load("default") == (original, revision)


@pytest.mark.parametrize(
    ("corruption", "expected_code"),
    [
        ("schema_marker", "unknown_schema_marker"),
        ("object_hash", "object_hash_mismatch"),
        ("delta_reference", "delta_object_ref_missing"),
        ("current_reference", "current_object_ref_missing"),
        ("current_source_hash", "current_revision_source_hash_mismatch"),
    ],
)
def test_unknown_schema_object_hash_and_references_are_refused(
    tmp_path: Path,
    corruption: str,
    expected_code: str,
) -> None:
    database = tmp_path / corruption / "watchlists.db"
    repository = _new_repository(database)
    repository.save(
        "default",
        _payload([_item("2330", "manual", "manual-2330")]),
        expected_revision=None,
        revision_id="seed",
    )
    inventory = repository.get_item_storage_inventory()
    object_hash = inventory["objects"][0]["object_hash"]

    with sqlite3.connect(database) as connection:
        if corruption == "schema_marker":
            connection.execute(
                "UPDATE watchlist_storage_meta SET storage_format=?",
                ("watchlist-item-events.v999",),
            )
        elif corruption == "object_hash":
            original_item = inventory["objects"][0]["item"]
            changed_item = deepcopy(original_item)
            changed_item["notes"] = "hash 不再對應"
            changed_json = _canonical_json(changed_item)
            connection.execute(
                "UPDATE watchlist_item_objects SET item_json=?,payload_bytes=? "
                "WHERE object_hash=?",
                (changed_json, len(changed_json.encode("utf-8")), object_hash),
            )
        elif corruption == "delta_reference":
            event_row = inventory["events"][0]
            event = deepcopy(event_row["event"])
            event["object_hash"] = "0" * 64
            event_json = _canonical_json(event)
            connection.execute(
                "UPDATE watchlist_revision_events SET event_json=?,event_hash=? "
                "WHERE event_id=?",
                (event_json, _sha256(event_json), event_row["event_id"]),
            )
        else:
            if corruption == "current_reference":
                connection.execute(
                    "UPDATE watchlist_current_items SET object_hash=? WHERE watchlist_id=?",
                    ("0" * 64, "default"),
                )
            else:
                connection.execute(
                    "UPDATE watchlists SET source_hash=? WHERE watchlist_id=?",
                    ("9" * 64, "default"),
                )

    reader = WatchlistRepository(database)
    with pytest.raises(WatchlistStorageIntegrityError) as refusal:
        reader.get_item_storage_inventory()
    assert refusal.value.code == expected_code

    # Ordinary consumers must enforce the same whole-store integrity boundary;
    # checking only the explicit inventory API would leave corrupted history
    # available through the current-payload read path.
    with pytest.raises(WatchlistStorageIntegrityError) as load_refusal:
        reader.load("default")
    assert load_refusal.value.code == expected_code
    with pytest.raises(WatchlistStorageIntegrityError) as current_refusal:
        reader.get_current("default")
    assert current_refusal.value.code == expected_code
