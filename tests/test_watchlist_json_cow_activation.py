"""JSON 來源的 Watchlist COW 啟用、追加與回復驗證。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app_module.watchlist_cow_activation import (
    WatchlistCowActivationError,
    activate_watchlist_sqlite,
    cow_activation_marker_path,
    rollback_watchlist_sqlite,
    resolve_watchlist_sqlite_activation,
)
from app_module.watchlist_service import WatchlistService
from data_module.watchlist_json_cow import convert_watchlist_json
from data_module.watchlist_repository import WatchlistRepository


def _config(root: Path) -> SimpleNamespace:
    output_root = root / "output"
    return SimpleNamespace(
        output_root=output_root,
        resolve_output_path=lambda name: output_root / name,
    )


def _fixture_payload() -> dict[str, object]:
    return {
        "version": 1,
        "name": "主要觀察清單",
        "description": "COW 合成測試",
        "created_at": "2026-10-01T09:00:00",
        "updated_at": "2026-10-01T09:05:00",
        "history": [{"event": "legacy", "details": {"keep": True}}],
        "future_envelope": {"nested": ["keep", 7]},
        "_storage_extensions": {"legacy_user_key": "keep"},
        "items": [
            {
                "stock_code": "2330",
                "stock_name": "台積電",
                "added_at": "2026-10-01T09:00:00",
                "source": "manual",
                "source_id": "legacy-source-2330",
                "notes": "保留原始備註",
                "tags": ["核心"],
                "future_item": {"nested": [1, 2]},
                "_storage_extensions": {"legacy_user_key": "keep"},
                "decision_identity": {
                    "identity_status": "unknown",
                    "future_identity": {"version": 9, "keep": True},
                },
            }
        ],
    }


def _write_source(path: Path, payload: dict[str, object]) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    path.write_bytes(raw)
    return raw


def test_json_upgrade_fresh_service_append_rollback_and_unknown_fields(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    service = WatchlistService(config)
    source = service.default_watchlist_file
    payload = _fixture_payload()
    original_raw = _write_source(source, payload)
    canonical = service.canonical_repository_path
    assert not canonical.exists()

    status = service.upgrade_to_repository()
    assert status.mode == "repository"
    assert service.repository is not None
    target = service.repository.db_path
    assert target != canonical.resolve()
    assert target.is_file()
    marker = cow_activation_marker_path(source)
    assert marker.is_file()
    assert source.read_bytes() == original_raw
    assert not canonical.exists()

    marker_before_repeat = hashlib.sha256(marker.read_bytes()).hexdigest()
    assert service.upgrade_to_repository().repository_path == target
    assert hashlib.sha256(marker.read_bytes()).hexdigest() == marker_before_repeat

    fresh = WatchlistService(config)
    assert fresh.get_storage_status().mode == "repository"
    assert fresh.repository is not None
    assert fresh.repository.db_path == target
    before_append = fresh.repository.load("default")
    assert before_append is not None
    before_payload, _ = before_append
    original_item = payload["items"][0]
    stored_item = before_payload["items"][0]
    for key, value in original_item.items():
        assert stored_item[key] == value

    assert fresh.add_stocks(
        [{"stock_code": "2317", "stock_name": "鴻海"}], source="manual"
    ) == 1
    assert source.read_bytes() == original_raw
    after_append = fresh.repository.load("default")
    assert after_append is not None
    appended_payload, _ = after_append
    assert appended_payload["history"] == payload["history"]
    assert appended_payload["future_envelope"] == payload["future_envelope"]
    assert appended_payload["_storage_extensions"] == payload["_storage_extensions"]
    assert len(appended_payload["items"]) == 2
    stored_original = appended_payload["items"][0]
    for key, value in original_item.items():
        assert stored_original[key] == value
    assert stored_original["decision_identity"]["future_identity"] == {
        "version": 9,
        "keep": True,
    }
    assert fresh.repository.list_revisions("default")

    rolled_back = rollback_watchlist_sqlite(source)
    assert rolled_back["status"] == "rolled_back"
    assert source.read_bytes() == original_raw
    resolved = resolve_watchlist_sqlite_activation(source)
    assert resolved["status"] == "rolled_back"
    assert resolved["source_format"] == "legacy_json_v1"
    assert WatchlistRepository(target).load("default")[0]["items"][-1]["stock_code"] == "2317"

    legacy = WatchlistService(config)
    assert legacy.repository is None
    assert legacy.get_storage_status().activation_source_path == source.resolve()
    assert legacy.add_stocks(
        [{"stock_code": "2603", "stock_name": "長榮"}], source="manual"
    ) == 1
    updated = json.loads(source.read_text(encoding="utf-8"))
    assert updated["history"] == payload["history"]
    assert updated["future_envelope"] == payload["future_envelope"]
    assert updated["_storage_extensions"] == payload["_storage_extensions"]
    assert updated["items"][0]["future_item"] == payload["items"][0]["future_item"]
    assert updated["items"][0]["_storage_extensions"] == payload["items"][0]["_storage_extensions"]
    assert updated["items"][0]["decision_identity"]["future_identity"] == {
        "version": 9,
        "keep": True,
    }
    assert updated["items"][-1]["stock_code"] == "2603"
    assert resolve_watchlist_sqlite_activation(source)["status"] == "rolled_back"
    assert WatchlistRepository(target).load("default")[0]["items"][-1]["stock_code"] == "2317"


def test_json_activation_refuses_changed_source_and_stale_service_writer(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    old_service = WatchlistService(config)
    source = old_service.default_watchlist_file
    original = _write_source(source, _fixture_payload())
    target = source.with_name(f"watchlists.v3-cow-test-{uuid4().hex}.sqlite")
    converted = convert_watchlist_json(source, target)
    assert converted.get("status") == "ready", converted

    payload = _fixture_payload()
    payload["description"] = "來源在驗證後變更"
    _write_source(source, payload)
    with pytest.raises(WatchlistCowActivationError, match="source_changed"):
        activate_watchlist_sqlite(source, target)
    assert not cow_activation_marker_path(source).exists()

    _write_source(source, json.loads(original.decode("utf-8")))
    target = source.with_name(f"watchlists.v3-cow-retry-{uuid4().hex}.sqlite")
    converted = convert_watchlist_json(source, target)
    assert converted.get("status") == "ready", converted
    activated = activate_watchlist_sqlite(source, target)
    assert activated["status"] == "activated"
    with pytest.raises(WatchlistCowActivationError, match="stale_service_pointer"):
        old_service.add_stocks(
            [{"stock_code": "2881", "stock_name": "富邦金"}], source="manual"
        )
    assert source.read_bytes() == original


def test_json_upgrade_refuses_multiple_sources_without_initializing_canonical(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    service = WatchlistService(config)
    source = service.default_watchlist_file
    source_raw = _write_source(source, _fixture_payload())
    secondary = source.with_name("secondary.json")
    secondary_raw = _write_source(secondary, _fixture_payload())

    status = service.upgrade_to_repository()

    assert status.mode == "upgrade_available"
    assert "source_scope_ambiguous" in status.message
    assert "仍使用原 JSON" in status.message
    assert not service.canonical_repository_path.exists()
    assert source.read_bytes() == source_raw
    assert secondary.read_bytes() == secondary_raw
