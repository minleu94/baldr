"""隔離 CLI → 明示啟用 → 新服務讀回 → 回滾；原來源bytes保持不變。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import sqlite3
from contextlib import closing
from types import SimpleNamespace

import pytest

from tests.test_f4_item_revision_storage_recovery import (
    _create_legacy_v1, _create_legacy_v2, _item, _payload,
)

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "watchlist_sqlite_cow.py"


def _call(*args: str) -> tuple[int, dict[str, object]]:
    process = subprocess.run([sys.executable, "-X", "utf8", str(CLI), *args], cwd=ROOT,
                             capture_output=True, text=True, encoding="utf-8", timeout=45)
    assert process.stdout.strip(), process.stderr
    return process.returncode, json.loads(process.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("schema", [1, 2])
def test_cli_copy_activation_readback_and_rollback(tmp_path: Path, schema: int) -> None:
    from app_module.watchlist_service import WatchlistService
    from data_module.watchlist_repository import WatchlistRepository
    source = tmp_path / "watchlist" / "watchlists.db"
    target = source.with_name("watchlists.v3-cow.sqlite")
    payload = _payload([_item("2330", "manual", "origin-2330")])
    payload["unknown_envelope"] = {"legacy_metadata": ["保留", 7]}
    if schema == 1:
        _create_legacy_v1(source, payload, with_source_hash=True)
    else:
        _create_legacy_v2(source, payload)
    original = source.read_bytes()
    original_hash = hashlib.sha256(original).hexdigest()
    source_args = ["--source", str(source)]
    target_args = [*source_args, "--destination", str(target)]
    code, preview = _call("dry-run", *target_args)
    assert code == 0 and preview["status"] == "dry_run", preview
    assert not target.exists()
    code, converted = _call("convert", *target_args)
    assert code == 0 and converted["status"] == "ready", converted
    assert source.read_bytes() == original
    assert converted["source_sha256"] == original_hash
    assert WatchlistRepository(target).load("default") == (payload, 7)
    with closing(sqlite3.connect(target.as_uri() + "?mode=ro&immutable=1", uri=True)) as connection:
        for (raw_header,) in connection.execute("SELECT header_json FROM watchlist_revisions_v3"):
            assert "item_json" not in json.loads(raw_header)["payload_layout"]
    code, ready = _call("activation-preview", *target_args)
    assert code == 0 and ready["status"] == "ready", ready
    code, activated = _call("activate", *target_args)
    assert code == 0 and activated["status"] in {"activated", "already_active"}, activated
    code, state = _call("status", *source_args)
    assert code == 0 and state["status"] != "blocked", state
    config = SimpleNamespace(output_root=tmp_path, resolve_output_path=lambda name: tmp_path / name)
    active, _ = WatchlistService.discover_repository(config)
    assert active is not None and active.db_path == target.resolve()
    assert active.load("default") == (payload, 7)
    code, rolled_back = _call("rollback", *source_args)
    assert code == 0 and rolled_back["status"] in {"rolled_back", "already_rolled_back"}, rolled_back
    restored, _ = WatchlistService.discover_repository(config)
    assert restored is not None and restored.db_path == source.resolve()
    assert restored.load("default") == (payload, 7)
    assert source.read_bytes() == original and target.is_file()


def test_cli_unknown_source_blocks_without_creating_target(tmp_path: Path) -> None:
    source = tmp_path / "missing.db"
    target = tmp_path / "target.db"
    code, receipt = _call("dry-run", "--source", str(source), "--destination", str(target))
    assert code == 2 and receipt["status"] == "blocked"
    assert not source.exists() and not target.exists()


def test_repository_readback_snapshot_excludes_concurrent_commit(tmp_path: Path) -> None:
    from data_module.watchlist_repository import WatchlistRepository
    from data_module import watchlist_item_storage
    database = tmp_path / "snapshot.db"
    repository = WatchlistRepository(database, initialize=True, capacity_preflight=lambda request: True)
    original = _payload([_item("2330", "manual", "snapshot-origin")])
    repository.save("default", original, expected_revision=None, revision_id="seed")
    changed = _payload([_item("2454", "manual", "snapshot-next")])
    with closing(sqlite3.connect(database, timeout=0)) as writer:
        with closing(repository._open_read_only()) as reader:
            assert watchlist_item_storage.inventory(reader)["watchlists"][0]["revision"] == 1
            writer.execute("BEGIN IMMEDIATE")
            watchlist_item_storage.save_v3(
                writer, watchlist_id="default", payload=changed, revision_id="next",
                operation="save", source_hash="", identity_status="unknown",
                continuity_event_id="", revision_of="", created_at="2026-10-05",
                expected_revision=1,
            )
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                writer.commit()
            snapshot = watchlist_item_storage.inventory(reader)
            assert snapshot["watchlists"][0]["revision"] == 1
            assert snapshot["watchlists"][0]["payload"] == original
        writer.commit()
    assert repository.load("default") == (changed, 2)
