"""隔離驗證 Watchlist SQLite COW activation、restart readback 與 rollback。"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from app_module.watchlist_cow_activation import (
    WatchlistCowActivationError,
    activate_watchlist_sqlite,
    cow_activation_marker_path,
    preview_watchlist_sqlite_activation,
    resolve_watchlist_sqlite_activation,
    rollback_watchlist_sqlite,
)
from app_module.watchlist_service import WatchlistService
from data_module.watchlist_repository import WatchlistRepository


def _config(root: Path) -> SimpleNamespace:
    output_root = root / "output"
    return SimpleNamespace(
        output_root=output_root,
        resolve_output_path=lambda name: output_root / name,
    )


def _payload(revision: int) -> dict[str, object]:
    item = {
        "stock_code": "2330",
        "stock_name": "台積電",
        "added_at": "2026-10-01T09:00:00",
        "source": "manual",
        "source_id": "source-2330",
        "notes": f"revision-{revision}",
        "tags": [],
    }
    return {
        "version": 1,
        "name": "隔離觀察清單",
        "description": "COW fixture",
        "created_at": "2026-10-01T09:00:00",
        "updated_at": f"2026-10-{revision:02d}T09:00:00",
        "items": [item],
    }


def _payload_json(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False)


def _build_source(path: Path, schema_version: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        if schema_version == 1:
            connection.execute(
                "CREATE TABLE watchlists ("
                "watchlist_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, "
                "revision INTEGER NOT NULL, source_hash TEXT NOT NULL)"
            )
            current_raw = _payload_json(_payload(1))
            connection.execute(
                "INSERT INTO watchlists VALUES (?, ?, ?, ?)",
                ("default", current_raw, 1, ""),
            )
            return

        connection.execute(
            "CREATE TABLE watchlists ("
            "watchlist_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, "
            "revision INTEGER NOT NULL, source_hash TEXT NOT NULL, "
            "is_deleted INTEGER NOT NULL, last_revision_id TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE watchlist_revisions ("
            "revision_id TEXT PRIMARY KEY, watchlist_id TEXT NOT NULL, "
            "revision INTEGER NOT NULL, operation TEXT NOT NULL, "
            "payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL, "
            "source_hash TEXT NOT NULL, identity_status TEXT NOT NULL, "
            "continuity_event_id TEXT NOT NULL, revision_of TEXT NOT NULL, "
            "created_at TEXT NOT NULL)"
        )
        for revision in (1, 2):
            payload_raw = _payload_json(_payload(revision))
            connection.execute(
                "INSERT INTO watchlist_revisions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"revision-{revision}",
                    "default",
                    revision,
                    "legacy_import" if revision == 1 else "updated",
                    payload_raw,
                    hashlib.sha256(payload_raw.encode("utf-8")).hexdigest(),
                    "",
                    "unknown",
                    "",
                    "",
                    f"2026-10-0{revision}T09:00:00+00:00",
                ),
            )
        latest = _payload_json(_payload(2))
        connection.execute(
            "INSERT INTO watchlists VALUES (?, ?, ?, ?, ?, ?)",
            ("default", latest, 2, "", 0, "revision-2"),
        )


def _convert(source: Path, target: Path) -> Path:
    from data_module.watchlist_sqlite_cow import convert_watchlist_sqlite

    result = convert_watchlist_sqlite(source, target)
    assert result.get("status") == "ready", result
    return target.with_name(f"{target.name}.cow-conversion.v1.json")


@pytest.mark.parametrize("schema_version", [1, 2])
def test_cow_activation_fresh_service_readback_append_and_rollback(
    tmp_path: Path, schema_version: int
) -> None:
    config = _config(tmp_path)
    canonical = WatchlistService.repository_path(config)
    canonical.parent.mkdir(parents=True)
    _build_source(canonical, schema_version)
    original_legacy_marker: bytes | None = None
    if schema_version == 2:
        legacy_marker = canonical.with_name(f"{canonical.name}.active")
        original_legacy_marker = json.dumps(
            {
                "schema_version": "watchlist-activation.v1",
                "status": "complete",
                "repository_schema_version": 2,
                "source_hashes": {"default": "fixture-pin"},
                "watchlist_ids": ["default"],
            },
            sort_keys=True,
        ).encode("utf-8")
        legacy_marker.write_bytes(original_legacy_marker)
    source_before = canonical.read_bytes()
    target = canonical.with_name("watchlists.v3-cow.sqlite")
    receipt_path = _convert(canonical, target)

    preview = preview_watchlist_sqlite_activation(canonical, target)
    assert preview["status"] == "ready"
    activated = activate_watchlist_sqlite(canonical, target)
    assert activated["status"] == "activated"
    assert canonical.read_bytes() == source_before
    if original_legacy_marker is not None:
        assert canonical.with_name(f"{canonical.name}.active").read_bytes() == original_legacy_marker
    assert target.is_file()
    assert cow_activation_marker_path(canonical).is_file()
    if original_legacy_marker is None:
        assert not canonical.with_name(f"{canonical.name}.active").exists()

    # 新建 service 物件代表程序重啟後重新 discovery。
    service = WatchlistService(config)
    assert service.get_storage_status().mode == "repository"
    assert service.repository is not None
    assert service.repository.db_path == target.resolve()
    assert [row["stock_code"] for row in service.get_stocks()] == ["2330"]

    prepared_hash = str(activated["prepared_target_sha256"])
    target_before_append = hashlib.sha256(target.read_bytes()).hexdigest()
    assert service.add_stocks(
        [{"stock_code": "2317", "stock_name": "鴻海"}], source="manual"
    ) == 1
    assert WatchlistRepository(target).load("default")[1] >= 2
    assert hashlib.sha256(target.read_bytes()).hexdigest() != target_before_append
    current = resolve_watchlist_sqlite_activation(canonical)
    assert current["status"] == "active"
    assert current["prepared_target_sha256"] == prepared_hash
    assert activate_watchlist_sqlite(canonical, target)["status"] == "already_active"

    rolled_back = rollback_watchlist_sqlite(canonical)
    assert rolled_back["status"] == "rolled_back"
    assert canonical.read_bytes() == source_before
    assert target.is_file()
    assert WatchlistRepository(target).load("default")[0]["items"][-1]["stock_code"] == "2317"
    assert Path(rolled_back["backup_marker_path"]).is_file()
    assert receipt_path.is_file()

    reopened = WatchlistService(config)
    if schema_version == 1:
        assert reopened.get_storage_status().mode == "repository_readonly"
        assert reopened.repository is not None
        assert [row["stock_code"] for row in reopened.get_stocks()] == ["2330"]
        assert not (canonical.parent / "default.json").exists()
        with pytest.raises(RuntimeError, match="watchlist_storage_readonly"):
            reopened.add_stocks([{"stock_code": "2603", "stock_name": "長榮"}])
        assert not (canonical.parent / "default.json").exists()
    else:
        assert reopened.get_storage_status().mode == "repository"
        assert reopened.repository is not None
        assert reopened.repository.db_path == canonical.resolve()
        assert [row["stock_code"] for row in reopened.get_stocks()] == ["2330"]
        assert reopened.add_stocks(
            [{"stock_code": "2603", "stock_name": "長榮"}], source="manual"
        ) == 1
        # rollback 完成後舊 v2 成為正常 writer；後續合法 append 不會令 pointer 損毀。
        assert resolve_watchlist_sqlite_activation(canonical)["status"] == "rolled_back"
        after_old_writer = WatchlistService(config)
        assert after_old_writer.get_storage_status().mode == "repository"
        assert [row["stock_code"] for row in after_old_writer.get_stocks()] == ["2330", "2603"]


@pytest.mark.parametrize(
    "marker_content",
    [
        "{invalid",
        '{"schema_version":"wrong","schema_version":"watchlist-cow-activation.v1"}',
        '{"value":NaN}',
    ],
)
def test_invalid_explicit_marker_blocks_json_writer_and_default_creation(
    tmp_path: Path, marker_content: str
) -> None:
    config = _config(tmp_path)
    canonical = WatchlistService.repository_path(config)
    canonical.parent.mkdir(parents=True)
    marker = cow_activation_marker_path(canonical)
    marker.write_text(marker_content, encoding="utf-8")

    service = WatchlistService(config)
    assert service.repository is None
    assert service.get_storage_status().mode == "blocked"
    assert not (canonical.parent / "default.json").exists()
    with pytest.raises(RuntimeError, match="watchlist_activation_blocked"):
        service.upgrade_to_repository()
    with pytest.raises(RuntimeError, match="watchlist_activation_blocked"):
        service.add_stocks([{"stock_code": "2330", "stock_name": "台積電"}])
    with pytest.raises(RuntimeError, match="watchlist_activation_blocked"):
        service.delete_watchlist("secondary")
    assert not (canonical.parent / "default.json").exists()
    assert not canonical.exists()


def test_activation_cancellation_leaves_no_pointer(tmp_path: Path) -> None:
    config = _config(tmp_path)
    canonical = WatchlistService.repository_path(config)
    canonical.parent.mkdir(parents=True)
    _build_source(canonical, 1)
    target = canonical.with_name("watchlists.v3-cow.sqlite")
    _convert(canonical, target)

    with pytest.raises(WatchlistCowActivationError, match="cancelled"):
        activate_watchlist_sqlite(canonical, target, cancel_check=lambda: True)
    assert not cow_activation_marker_path(canonical).exists()
    assert canonical.is_file() and target.is_file()


def test_activation_refuses_held_source_writer(tmp_path: Path) -> None:
    config = _config(tmp_path)
    canonical = WatchlistService.repository_path(config)
    canonical.parent.mkdir(parents=True)
    _build_source(canonical, 2)
    target = canonical.with_name("watchlists.v3-cow.sqlite")
    _convert(canonical, target)

    with sqlite3.connect(canonical, timeout=0, isolation_level=None) as writer:
        writer.execute("BEGIN IMMEDIATE")
        with pytest.raises(WatchlistCowActivationError) as failure:
            activate_watchlist_sqlite(canonical, target)
        assert failure.value.code == "active_writer"
        writer.execute("ROLLBACK")
    assert not cow_activation_marker_path(canonical).exists()


def test_stale_service_instance_cannot_write_after_activation(tmp_path: Path) -> None:
    config = _config(tmp_path)
    canonical = WatchlistService.repository_path(config)
    canonical.parent.mkdir(parents=True)
    _build_source(canonical, 2)
    stale_repository, stale_status = WatchlistService.discover_repository(config)
    stale_service = WatchlistService(
        config,
        repository=stale_repository,
        storage_status=stale_status,
    )
    assert stale_service.repository is not None
    target = canonical.with_name("watchlists.v3-cow.sqlite")
    _convert(canonical, target)
    activate_watchlist_sqlite(canonical, target)

    with pytest.raises(WatchlistCowActivationError) as failure:
        stale_service.add_stocks([{"stock_code": "2317", "stock_name": "test"}])
    assert failure.value.code == "stale_service_pointer"
    assert WatchlistRepository(canonical).load("default")[0]["items"][0]["stock_code"] == "2330"


def test_receipt_target_hash_mismatch_blocks_activation_without_marker(tmp_path: Path) -> None:
    config = _config(tmp_path)
    canonical = WatchlistService.repository_path(config)
    canonical.parent.mkdir(parents=True)
    _build_source(canonical, 1)
    target = canonical.with_name("watchlists.v3-cow.sqlite")
    receipt_path = _convert(canonical, target)

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["target_sha256"] = "0" * 64
    receipt_path.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")

    result = preview_watchlist_sqlite_activation(canonical, target)
    assert result["status"] == "blocked"
    assert result["code"] == "stale_hash"
    with pytest.raises(Exception):
        activate_watchlist_sqlite(canonical, target)
    assert not cow_activation_marker_path(canonical).exists()
    assert canonical.is_file() and target.is_file()


@pytest.mark.parametrize("fault", ["capacity_unknown", "capacity_insufficient"])
def test_metadata_capacity_refusal_preserves_activation_and_rollback_pointer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    import data_module.ml_storage_capacity as capacity

    canonical = WatchlistService.repository_path(_config(tmp_path))
    _build_source(canonical, 2)
    target = canonical.with_name("watchlists.v3-cow.sqlite")
    _convert(canonical, target)
    before = (canonical.read_bytes(), target.read_bytes())
    original = capacity.evaluate_capacity

    def refused(**kwargs: object) -> SimpleNamespace:
        if fault == "capacity_unknown":
            raise OSError("isolated capacity probe unavailable")
        return SimpleNamespace(within_budget=False)

    monkeypatch.setattr(capacity, "evaluate_capacity", refused)
    with pytest.raises(WatchlistCowActivationError) as activation:
        activate_watchlist_sqlite(canonical, target)
    assert activation.value.code == fault
    assert not cow_activation_marker_path(canonical).exists()
    assert (canonical.read_bytes(), target.read_bytes()) == before
    monkeypatch.setattr(capacity, "evaluate_capacity", original)
    activate_watchlist_sqlite(canonical, target)
    marker_before = cow_activation_marker_path(canonical).read_bytes()
    monkeypatch.setattr(capacity, "evaluate_capacity", refused)
    with pytest.raises(WatchlistCowActivationError) as rollback:
        rollback_watchlist_sqlite(canonical)
    assert rollback.value.code == fault
    assert cow_activation_marker_path(canonical).read_bytes() == marker_before
    assert (canonical.read_bytes(), target.read_bytes()) == before
    assert not (canonical.parent / "default.json").exists()
