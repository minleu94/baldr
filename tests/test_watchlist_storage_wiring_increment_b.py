"""Increment B：觀察清單 JSON → canonical repository 的啟用與重啟契約。"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app_module import watchlist_service as watchlist_service_module
from app_module.watchlist_service import WatchlistService
from data_module.watchlist_repository import WatchlistRepository


def _config(root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        output_root=root / "output",
        resolve_output_path=lambda name: root / "output" / name,
    )


def _payload(code: str, name: str) -> dict[str, object]:
    return {
        "version": 1,
        "name": f"{name}候選池",
        "description": "Increment B migration fixture",
        "created_at": "2026-09-14T09:00:00",
        "updated_at": "2026-09-14T09:00:00",
        "items": [
            {
                "stock_code": code,
                "stock_name": name,
                "added_at": "2026-09-14T09:00:00",
                "source": "manual",
                "source_id": "legacy-source-id",
                "notes": "",
                "tags": [],
            }
        ],
    }


def _write_json(path: Path, payload: dict[str, object]) -> bytes:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path.read_bytes()


def test_second_source_failure_keeps_json_active_and_retry_activates_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _config(tmp_path)
    service = WatchlistService(settings)
    watchlist_dir = service.watchlist_dir
    default_path = watchlist_dir / "default.json"
    default_before = default_path.read_bytes()
    second_path = watchlist_dir / "secondary.json"
    second_before = _write_json(second_path, _payload("2317", "鴻海"))
    canonical = WatchlistService.repository_path(settings)

    original_migrate = watchlist_service_module.migrate_watchlist_copy

    def fail_second(source, destination, *, sandbox_root, watchlist_id="default"):
        if watchlist_id == "secondary":
            raise RuntimeError("injected second source failure")
        return original_migrate(
            source,
            destination,
            sandbox_root=sandbox_root,
            watchlist_id=watchlist_id,
        )

    monkeypatch.setattr(watchlist_service_module, "migrate_watchlist_copy", fail_second)
    failed = service.upgrade_to_repository()

    assert not failed.is_repository
    assert failed.upgrade_available
    assert service.repository is None
    assert "仍使用原 JSON" in failed.message
    assert default_path.read_bytes() == default_before
    assert second_path.read_bytes() == second_before
    assert not canonical.exists()
    assert not list(watchlist_dir.glob("watchlists.db.migration-*.tmp"))

    restarted_repository, restarted_status = WatchlistService.discover_repository(settings)
    assert restarted_repository is None
    assert not restarted_status.is_repository
    assert restarted_status.upgrade_available
    assert default_path.read_bytes() == default_before
    assert second_path.read_bytes() == second_before

    monkeypatch.setattr(
        watchlist_service_module, "migrate_watchlist_copy", original_migrate
    )
    activated = service.upgrade_to_repository()
    assert activated.is_repository
    assert "啟用並核對成功" in activated.message
    assert service.repository is not None
    assert canonical.is_file()
    marker = WatchlistService.activation_marker_path(canonical)
    assert marker.is_file()
    assert service.repository.list_ids() == ["default", "secondary"]
    assert default_path.read_bytes() == default_before
    assert second_path.read_bytes() == second_before

    reopened_repository, reopened_status = WatchlistService.discover_repository(settings)
    assert reopened_repository is not None
    assert reopened_status.is_repository
    assert reopened_repository.list_ids() == ["default", "secondary"]


def test_source_verification_failure_does_not_publish_canonical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _config(tmp_path)
    service = WatchlistService(settings)
    watchlist_dir = service.watchlist_dir
    default_path = watchlist_dir / "default.json"
    default_before = default_path.read_bytes()
    _write_json(watchlist_dir / "secondary.json", _payload("2317", "鴻海"))
    canonical = WatchlistService.repository_path(settings)

    def fail_verification(*args, **kwargs):
        raise RuntimeError("injected source mismatch")

    monkeypatch.setattr(WatchlistService, "_verify_repository_payloads", fail_verification)
    failed = service.upgrade_to_repository()

    assert not failed.is_repository
    assert "比對" in failed.message or "mismatch" in failed.message
    assert service.repository is None
    assert not canonical.exists()
    assert default_path.read_bytes() == default_before

    restarted_repository, restarted_status = WatchlistService.discover_repository(settings)
    assert restarted_repository is None
    assert not restarted_status.is_repository
    assert restarted_status.upgrade_available


def test_ready_unmarked_database_with_legacy_json_stays_inactive(
    tmp_path: Path,
) -> None:
    settings = _config(tmp_path)
    service = WatchlistService(settings)
    canonical = WatchlistService.repository_path(settings)
    WatchlistRepository(canonical, initialize=True)

    repository, status = WatchlistService.discover_repository(settings)

    assert repository is None
    assert not status.is_repository
    assert status.upgrade_available
    assert "尚未完成 activation" in status.message


def test_marker_failure_recovers_only_after_exact_source_hash_readback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _config(tmp_path)
    service = WatchlistService(settings)
    watchlist_dir = service.watchlist_dir
    default_path = watchlist_dir / "default.json"
    default_before = default_path.read_bytes()
    secondary_path = watchlist_dir / "secondary.json"
    secondary_before = _write_json(secondary_path, _payload("2317", "鴻海"))
    canonical = WatchlistService.repository_path(settings)

    with monkeypatch.context() as marker_failure:
        def fail_marker(cls, repository_path, payload):
            raise RuntimeError("injected activation marker failure")

        marker_failure.setattr(
            WatchlistService,
            "_write_activation_marker",
            classmethod(fail_marker),
        )
        failed = service.upgrade_to_repository()

    assert not failed.is_repository
    assert service.repository is None
    assert "仍使用原 JSON" in failed.message
    assert canonical.is_file()
    assert not WatchlistService.activation_marker_path(canonical).exists()
    assert default_path.read_bytes() == default_before
    assert secondary_path.read_bytes() == secondary_before

    restarted_repository, restarted_status = WatchlistService.discover_repository(settings)
    assert restarted_repository is None
    assert not restarted_status.is_repository
    assert restarted_status.upgrade_available

    # 中斷後若來源改變，不得用新內容啟用依舊 snapshot 產生的 canonical DB。
    changed_secondary = _payload("2317", "鴻海（修訂來源）")
    changed_bytes = _write_json(secondary_path, changed_secondary)
    restarted = WatchlistService(
        settings,
        repository=restarted_repository,
        storage_status=restarted_status,
    )
    changed_retry = restarted.upgrade_to_repository()
    assert not changed_retry.is_repository
    assert "hash" in changed_retry.message
    assert restarted.repository is None
    assert not WatchlistService.activation_marker_path(canonical).exists()
    assert secondary_path.read_bytes() == changed_bytes
    assert default_path.read_bytes() == default_before

    # 恢復完全相同的原始 bytes 後，才能不重複匯入 history 地啟用 DB。
    secondary_path.write_bytes(secondary_before)
    recovered = restarted.upgrade_to_repository()
    assert recovered.is_repository
    assert restarted.repository is not None
    assert WatchlistService.activation_marker_path(canonical).is_file()
    assert default_path.read_bytes() == default_before
    assert secondary_path.read_bytes() == secondary_before
    assert restarted.repository.list_ids() == ["default", "secondary"]

    recovered_repository, recovered_status = WatchlistService.discover_repository(settings)
    assert recovered_repository is not None
    assert recovered_status.is_repository

    # 啟用後日常寫入只走 SQLite；重開後保留的 JSON 仍逐 byte 不變。
    assert restarted.add_stocks(
        [{"stock_code": "2881", "stock_name": "富邦金"}], source="manual"
    ) == 1
    reopened = WatchlistService(
        settings,
        repository=recovered_repository,
        storage_status=recovered_status,
    )
    assert reopened.get_stock_codes() == ["2881"]
    assert len(reopened.list_watchlist_revisions()) == 2
    assert default_path.read_bytes() == default_before
    assert secondary_path.read_bytes() == secondary_before
