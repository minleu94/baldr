"""舊 watchlist SQLite COW converter 的 bounded round-trip contract。"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
from copy import deepcopy
from contextlib import closing

import pytest

from data_module.watchlist_repository import WatchlistRepository
from data_module.watchlist_sqlite_cow import convert_watchlist_sqlite, dry_run_watchlist_sqlite
from tests.test_f4_item_revision_storage_recovery import (
    _create_legacy_v1, _create_legacy_v2, _item, _payload,
)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _allow_capacity(request: object) -> bool:
    return True


@pytest.mark.parametrize("schema", [1, 2])
def test_cow_preserves_source_raw_payload_revision_seven_and_receipt(
    tmp_path: Path, schema: int,
) -> None:
    source = tmp_path / f"source-v{schema}.db"
    target = tmp_path / f"target-v{schema}.db"
    payload = _payload([_item("2330", "manual", "fixture-origin", notes="COW sentinel")])
    payload["unknown_envelope"] = {"nested_extension": ["keep", 7]}
    if schema == 1:
        _create_legacy_v1(source, payload, with_source_hash=True)
    else:
        _create_legacy_v2(source, payload)
    with closing(sqlite3.connect(source)) as source_conn:
        source_payload_raw = str(source_conn.execute(
            "SELECT payload_json FROM watchlists WHERE watchlist_id='default'"
        ).fetchone()[0])
    source_bytes = source.read_bytes()
    source_stat = source.stat()

    preview = dry_run_watchlist_sqlite(source, target, capacity_preflight=_allow_capacity)
    assert preview["status"] == "dry_run"
    assert preview["comparison"]["complete"] is True
    assert not target.exists()
    assert not Path(str(target) + ".cow-conversion.v1.json").exists()

    converted = convert_watchlist_sqlite(source, target, capacity_preflight=_allow_capacity)
    assert converted["status"] == "ready", converted
    assert converted["source_sha256"] == _sha256(source_bytes)
    assert converted["source_size_bytes"] == len(source_bytes)
    assert converted["source_stat"] == {
        "size": source_stat.st_size, "mtime_ns": source_stat.st_mtime_ns,
        "inode": source_stat.st_ino, "device": source_stat.st_dev,
    }
    assert source.read_bytes() == source_bytes
    assert source.stat().st_mtime_ns == source_stat.st_mtime_ns

    repository = WatchlistRepository(target)
    assert repository.load("default") == (payload, 7)
    current = repository.get_current("default")
    assert current is not None
    assert current["payload_json"] == source_payload_raw
    history = repository.list_revisions("default")
    assert len(history) == 1
    assert history[0]["revision"] == 7
    assert history[0]["payload_hash"] == _sha256(current["payload_json"].encode("utf-8"))
    prepared_target_hash = _sha256(target.read_bytes())
    if schema == 1:
        assert history[0]["is_synthetic_baseline"] is True
        assert history[0]["source_revision_id"] == ""
        assert history[0]["created_at"] == ""
    else:
        assert history[0]["revision_id"] == "legacy-v2-r7"
        assert history[0]["revision_of"] == ""

    updated = deepcopy(payload)
    updated["unknown_envelope"]["post_migration"] = "native-v3"
    assert repository.save(
        "default", updated, expected_revision=7, revision_id="native-v3-r8",
        operation="updated", source_hash="post-migration-source",
    ) == 8
    appended = repository.list_revisions("default")
    assert [row["revision"] for row in appended] == [7, 8]
    assert appended[0]["payload_hash"] == _sha256(source_payload_raw.encode("utf-8"))
    assert appended[1]["payload"] == updated

    receipt_path = Path(converted["receipt_path"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["schema_version"] == "watchlist-cow-conversion.v1"
    assert receipt["target_sha256"] == prepared_target_hash
    assert receipt["comparison"]["payload_hashes_matched"] == 1
    assert "COW sentinel" not in receipt_path.read_text(encoding="utf-8")

    again = convert_watchlist_sqlite(source, target, capacity_preflight=_allow_capacity)
    assert again["status"] == "blocked"
    assert again["error_code"] == "target_already_exists"


def _create_v2_lexical(database: Path, *, payload_raw: str, deleted: int = 1) -> None:
    revision_id = "legacy-gap-r7"
    source_hash = hashlib.sha256(b"source-seed").hexdigest()
    payload_hash = _sha256(payload_raw.encode("utf-8"))
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as conn:
        conn.execute(
            "CREATE TABLE watchlists (watchlist_id TEXT PRIMARY KEY,payload_json TEXT NOT NULL,"
            "revision INTEGER NOT NULL,source_hash TEXT NOT NULL DEFAULT '',is_deleted INTEGER NOT NULL DEFAULT 0,"
            "last_revision_id TEXT NOT NULL DEFAULT '')"
        )
        conn.execute(
            "CREATE TABLE watchlist_revisions (revision_id TEXT PRIMARY KEY,watchlist_id TEXT NOT NULL,"
            "revision INTEGER NOT NULL,operation TEXT NOT NULL,payload_json TEXT NOT NULL,payload_hash TEXT NOT NULL,"
            "source_hash TEXT NOT NULL DEFAULT '',identity_status TEXT NOT NULL DEFAULT 'unknown',"
            "continuity_event_id TEXT NOT NULL DEFAULT '',revision_of TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,"
            "UNIQUE(watchlist_id,revision))"
        )
        conn.execute(
            "INSERT INTO watchlists VALUES(?,?,?,?,?,?)",
            ("default", payload_raw, 7, source_hash, deleted, revision_id),
        )
        conn.execute(
            "INSERT INTO watchlist_revisions VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (revision_id, "default", 7, "legacy_edit", payload_raw, payload_hash,
             source_hash, "unlinked", "event:opaque", "pre-migration-parent", "old-time-token"),
        )


def test_v2_lexical_codec_preserves_noncanonical_json_and_opaque_parent(tmp_path: Path) -> None:
    payload_raw = (
        '{ "unknown" : { "a" : 1.0 }, "items" : [ { "stock_code" : "2330", '
        '"stock_name" : "Taiwan Semi", "source" : "manual", "source_id" : "legacy", '
        '"added_at" : "2026-01-01", "extension" : {"x":  true} } ] }'
    )
    source = tmp_path / "legacy.db"
    target = tmp_path / "v3.db"
    _create_v2_lexical(source, payload_raw=payload_raw, deleted=1)
    result = convert_watchlist_sqlite(source, target, capacity_preflight=_allow_capacity)
    assert result["status"] == "ready", result

    repository = WatchlistRepository(target)
    current = repository.get_current("default")
    assert current is not None and current["payload_json"] == payload_raw
    assert current["is_deleted"] is True
    history = repository.list_revisions("default")
    assert len(history) == 1
    assert history[0]["revision"] == 7
    assert history[0]["revision_of"] == "pre-migration-parent"
    assert history[0]["continuity_event_id"] == "event:opaque"
    assert history[0]["identity_status"] == "unlinked"
    assert history[0]["payload_hash"] == _sha256(payload_raw.encode("utf-8"))
    assert history[0]["is_deleted"] is True


@pytest.mark.parametrize("bad_raw", [
    '{"items":[{"key":1,"key":2}]}',
    '{"items":[],"bad":NaN}',
    '{"items":[{"value":Infinity}]}',
])
def test_duplicate_or_nonfinite_source_json_fails_closed(tmp_path: Path, bad_raw: str) -> None:
    source = tmp_path / "legacy.db"
    target = tmp_path / "target.db"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE watchlists(watchlist_id TEXT PRIMARY KEY,payload_json TEXT NOT NULL,revision INTEGER NOT NULL)")
        conn.execute("INSERT INTO watchlists VALUES(?,?,?)", ("default", bad_raw, 7))
    result = dry_run_watchlist_sqlite(source, target, capacity_preflight=_allow_capacity)
    assert result["status"] == "blocked"
    assert result["error_code"] in {"duplicate_json_key", "nonfinite_json_number"}
    assert not target.exists()


@pytest.mark.parametrize(("decision", "expected"), [(False, "capacity_insufficient"), (None, "capacity_unknown")])
def test_capacity_denial_and_cancel_never_publish(tmp_path: Path, decision: bool | None, expected: str) -> None:
    source = tmp_path / "legacy.db"
    target = tmp_path / "target.db"
    _create_legacy_v1(source, _payload([_item("2317", "manual", "source")]), with_source_hash=False)
    denied = convert_watchlist_sqlite(source, target, capacity_preflight=lambda _request: decision)
    assert denied["status"] == "blocked" and denied["error_code"] == expected
    assert not target.exists()
    cancelled = convert_watchlist_sqlite(source, target, capacity_preflight=_allow_capacity,
                                         cancel_check=lambda: True)
    assert cancelled["status"] == "blocked" and cancelled["error_code"] == "cancelled"
    assert not target.exists()


def test_conversion_holds_reserved_lock_and_preserves_failed_stage_on_source_change(tmp_path: Path) -> None:
    source = tmp_path / "legacy.db"
    target = tmp_path / "target.db"
    _create_legacy_v1(source, _payload([_item("2454", "manual", "source")]), with_source_hash=False)
    before = source.read_bytes()

    def prove_reserved_lock(_request: object) -> bool:
        probe = sqlite3.connect(source, timeout=0.1)
        try:
            with pytest.raises(sqlite3.OperationalError):
                probe.execute("BEGIN IMMEDIATE")
        finally:
            probe.close()
        return True

    prepared = convert_watchlist_sqlite(source, target, capacity_preflight=prove_reserved_lock)
    assert prepared["status"] == "ready", prepared
    assert source.read_bytes() == before
    released_probe = sqlite3.connect(source, timeout=0.1)
    try:
        released_probe.execute("BEGIN IMMEDIATE")
        released_probe.rollback()
    finally:
        released_probe.close()

    changed_target = tmp_path / "changed-source-target.db"

    def touch_source(_request: object) -> bool:
        os.utime(source, None)
        return True

    blocked = convert_watchlist_sqlite(source, changed_target, capacity_preflight=touch_source)
    assert blocked["status"] == "blocked"
    assert blocked["error_code"] == "source_changed_before_publish"
    assert not changed_target.exists()
    stage = Path(str(blocked["failed_stage_path"]))
    assert stage.is_file()


@pytest.mark.parametrize("schema", [1, 2])
def test_cow_sqlite_uri_preserves_unicode_and_reserved_characters(tmp_path, schema):
    source = tmp_path / "合法來源 # 100%.sqlite"
    target = tmp_path / "合法目標 # 100%.sqlite"
    payload = _payload([_item("2330", "manual", "synthetic-uri")])
    if schema == 1:
        _create_legacy_v1(source, payload, with_source_hash=True)
    else:
        _create_legacy_v2(source, payload)
    before = source.read_bytes(), source.stat().st_mtime_ns
    result = convert_watchlist_sqlite(source, target, capacity_preflight=_allow_capacity)
    assert result["status"] == "ready", result
    assert result["source_path"] == str(source)
    assert result["target_path"] == str(target)
    assert WatchlistRepository(target).load("default") == (payload, 7)
    assert (source.read_bytes(), source.stat().st_mtime_ns) == before
