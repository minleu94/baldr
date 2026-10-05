"""項目 revision 格式接入既有唯讀研究儲存治理的有限回歸。"""

from pathlib import Path
import json
import sqlite3

from app_module.research_snapshot_storage_governance import diagnose_research_snapshot_storage
from data_module.watchlist_repository import WatchlistRepository


def test_legacy_v1_governance_reader_does_not_initialize_or_migrate(tmp_path: Path) -> None:
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    database = tmp_path / "watchlists" / "watchlists.db"
    database.parent.mkdir()
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE watchlists(watchlist_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, revision INTEGER NOT NULL)")
        connection.execute("INSERT INTO watchlists VALUES(?,?,?)", ("default", json.dumps({"items": []}), 7))
    before = database.read_bytes()
    receipt = diagnose_research_snapshot_storage(snapshots, watchlist_dir=database.parent, watchlist_inventory_complete=True)
    assert receipt["storage"]["references_complete"] is True
    assert database.read_bytes() == before


def test_item_storage_inventory_scans_unique_payloads_without_expanded_history(tmp_path: Path) -> None:
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    database = tmp_path / "watchlists" / "watchlists.db"
    repository = WatchlistRepository(database, initialize=True)
    payload = {"name": "fixture", "items": []}
    for revision in range(1, 41):
        payload["items"].append({"stock_code": "2330", "stock_name": "fixture", "added_at": "2026-10-05",
                                "source": "manual", "source_id": f"fixture-{revision}", "notes": "x" * 5000})
        repository.save("default", payload, expected_revision=revision - 1 if revision > 1 else None)
    before = database.read_bytes()
    receipt = diagnose_research_snapshot_storage(snapshots, watchlist_dir=database.parent, watchlist_inventory_complete=True)
    assert receipt["storage"]["scan_complete"] is True
    assert receipt["storage"]["references_complete"] is True
    assert database.read_bytes() == before
    assert not Path(f"{database}-wal").exists()
    assert not Path(f"{database}-shm").exists()


def test_item_storage_unknown_schema_is_preserved_and_reference_scan_fails_closed(tmp_path: Path) -> None:
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    database = tmp_path / "watchlists" / "watchlists.db"
    WatchlistRepository(database, initialize=True)
    with sqlite3.connect(database) as connection:
        connection.execute("ALTER TABLE watchlists ADD COLUMN unknown_field TEXT")
    before = database.read_bytes()
    receipt = diagnose_research_snapshot_storage(snapshots, watchlist_dir=database.parent, watchlist_inventory_complete=True)
    assert receipt["storage"]["references_complete"] is False
    assert receipt["issues"]
    assert database.read_bytes() == before
