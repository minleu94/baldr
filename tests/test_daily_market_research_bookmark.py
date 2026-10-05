from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app_module.daily_market_method_contract import method_contracts_sha256
from app_module.daily_market_research_bookmark import (
    DailyMarketResearchBookmarkError,
    create_daily_market_research_bookmark,
    decode_daily_market_research_bookmark,
)
from app_module.watchlist_service import WatchlistService
from data_module.watchlist_repository import WatchlistRepository
from test_daily_market_cohort_projection import _fixture


def _config(root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        output_root=root / "output",
        resolve_output_path=lambda name: root / "output" / name,
    )


def _payload_hash(payload: dict[str, object]) -> str:
    body = {key: value for key, value in payload.items() if key != "payload_sha256"}
    encoded = json.dumps(
        body,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _capture(tmp_path: Path):
    root, snapshot, rows, _screener = _fixture(tmp_path)
    row = rows[0]
    bookmark = create_daily_market_research_bookmark(
        snapshot,
        row,
        sort_key="close",
        descending=True,
        stock_name="Fixture stock",
        filter_state="no_match",
    )
    return root, snapshot, row, bookmark


def test_bookmark_factory_binds_row_to_verified_manifest_artifacts_and_captured_methods(
    tmp_path: Path,
) -> None:
    root, snapshot, row, bookmark = _capture(tmp_path)

    decoded = decode_daily_market_research_bookmark(bookmark.to_dict())
    assert decoded.bookmark_id == bookmark.bookmark_id
    assert decoded.source_snapshot_id == snapshot.manifest_identity_sha256
    assert decoded.source_snapshot_hash == snapshot.manifest_sha256
    assert decoded.snapshot_root == str(root.resolve())
    assert decoded.declared_stock_codes == tuple(
        snapshot.manifest["declared_stock_codes"]
    )
    assert decoded.method_contracts == snapshot.manifest["method_contracts"]
    assert decoded.method_contracts_sha256 == snapshot.manifest["method_contracts_sha256"]
    assert decoded.filter_state == "no_match"
    assert decoded.context.source_workspace == "watchlist"
    assert decoded.context.source_id == bookmark.bookmark_id
    assert decoded.context.result_id == ""

    with pytest.raises(DailyMarketResearchBookmarkError):
        create_daily_market_research_bookmark(
            snapshot,
            replace(row, snapshot_root=str(tmp_path / "unrelated")),
            filter_state="no_match",
        )
    with pytest.raises(DailyMarketResearchBookmarkError):
        create_daily_market_research_bookmark(
            snapshot,
            replace(row, decision_date="2026-10-04"),
            filter_state="no_match",
        )


def test_bookmark_decoder_rejects_wrong_schema_hash_date_and_method_contract() -> None:
    # 此隔離 fixture 僅使用合成 DTO 與不可變輸出檔案。
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        _root, _snapshot, _row, bookmark = _capture(Path(directory))
        original = bookmark.to_dict()

    wrong_schema = deepcopy(original)
    wrong_schema["schema_version"] = "daily-market-research-bookmark.v999"
    wrong_schema["payload_sha256"] = _payload_hash(wrong_schema)
    with pytest.raises(DailyMarketResearchBookmarkError):
        decode_daily_market_research_bookmark(wrong_schema)

    wrong_hash = deepcopy(original)
    wrong_hash["source_snapshot_hash"] = "0" * 64
    with pytest.raises(DailyMarketResearchBookmarkError):
        decode_daily_market_research_bookmark(wrong_hash)

    wrong_date = deepcopy(original)
    wrong_date["decision_date"] = "2026-10-04"
    wrong_date["context"]["decision_date"] = "2026-10-04"
    wrong_date["payload_sha256"] = _payload_hash(wrong_date)
    with pytest.raises(DailyMarketResearchBookmarkError):
        decode_daily_market_research_bookmark(wrong_date)

    wrong_method = deepcopy(original)
    wrong_method["method_contracts"]["close_above_ma20"]["version"] = "9.9.9"
    wrong_method["method_contracts_sha256"] = method_contracts_sha256(
        wrong_method["method_contracts"]
    )
    wrong_method["payload_sha256"] = _payload_hash(wrong_method)
    with pytest.raises(DailyMarketResearchBookmarkError):
        decode_daily_market_research_bookmark(wrong_method)


def test_json_idempotency_query_identity_remove_restore_and_explicit_sqlite_upgrade(
    tmp_path: Path,
) -> None:
    _root, snapshot, row, first = _capture(tmp_path / "source")
    second = create_daily_market_research_bookmark(
        snapshot,
        row,
        sort_key="ma20",
        descending=False,
        stock_name="Fixture stock",
        filter_state="all",
    )
    assert first.stock_code == second.stock_code
    assert first.bookmark_id != second.bookmark_id
    assert first.query_sha256 != second.query_sha256

    settings = _config(tmp_path / "watchlist")
    service = WatchlistService(settings)
    assert service.add_stocks(
        [{"stock_code": first.stock_code, "stock_name": "Manual fixture"}],
        source="manual",
    ) == 1
    added = service.add_research_bookmark(first)
    assert added.status == "added"
    assert service.add_research_bookmark(second).status == "added"
    json_path = service.default_watchlist_file
    before_retry = json_path.read_bytes()
    assert service.add_research_bookmark(first).status == "already_present"
    assert json_path.read_bytes() == before_retry

    conflicting = deepcopy(first.to_dict())
    conflicting["stock_name"] = "Different captured display name"
    conflicting["context"]["stock_name"] = "Different captured display name"
    conflicting["payload_sha256"] = _payload_hash(conflicting)
    assert service.add_research_bookmark(conflicting).status == "conflict"
    assert json_path.read_bytes() == before_retry

    # 新 service instance 可從 JSON 讀回完整的來源 context。
    reopened_json = WatchlistService(settings)
    context = reopened_json.get_research_bookmark_context(first.bookmark_id)
    assert context is not None
    assert context.source_workspace == "watchlist"
    assert context.source_id == first.bookmark_id
    assert context.result_id == ""
    assert context.daily_snapshot_condition_keys == ",".join(first.condition_keys)
    assert context.daily_snapshot_combine_mode == first.combine_mode

    # 顯式 JSON→SQLite 升級保留同股普通項目與兩筆不同查詢收藏。
    upgraded = reopened_json.upgrade_to_repository()
    assert upgraded.is_repository
    repository, status = WatchlistService.discover_repository(settings)
    assert repository is not None
    reopened_sqlite = WatchlistService(
        settings,
        repository=repository,
        storage_status=status,
    )
    assert len(reopened_sqlite.get_stocks()) == 3
    assert reopened_sqlite.get_research_bookmark(first.bookmark_id).to_dict() == first.to_dict()
    assert reopened_sqlite.get_research_bookmark(second.bookmark_id).to_dict() == second.to_dict()

    # 精確移除普通列時，兩筆同股研究收藏仍保留。
    ordinary = reopened_sqlite.remove_watchlist_item(
        first.stock_code, "", "manual"
    )
    assert ordinary.status == "removed"
    assert {item["source_id"] for item in reopened_sqlite.get_stocks()} == {
        first.bookmark_id,
        second.bookmark_id,
    }

    removed = reopened_sqlite.remove_research_bookmark(first.bookmark_id)
    assert removed.status == "removed"
    assert removed.restore_token is not None
    assert reopened_sqlite.get_research_bookmark(first.bookmark_id) is None
    assert reopened_sqlite.get_research_bookmark(second.bookmark_id) is not None
    before_restore_retry = reopened_sqlite.get_watchlist().revision
    restored = reopened_sqlite.restore_research_bookmark(removed.restore_token)
    assert restored.status == "restored"
    assert reopened_sqlite.get_research_bookmark(first.bookmark_id).to_dict() == first.to_dict()
    revision_after_restore = reopened_sqlite.get_watchlist().revision
    assert reopened_sqlite.restore_research_bookmark(removed.restore_token).status == "already_present"
    assert reopened_sqlite.get_watchlist().revision == revision_after_restore
    assert revision_after_restore > before_restore_retry

    # 第二個 service instance 可讀回 SQLite 狀態與追加式 revisions。
    final_repository, final_status = WatchlistService.discover_repository(settings)
    final_service = WatchlistService(
        settings,
        repository=final_repository,
        storage_status=final_status,
    )
    assert final_service.get_research_bookmark(first.bookmark_id).to_dict() == first.to_dict()
    operations = [
        revision["operation"]
        for revision in final_service.list_watchlist_revisions()
    ]
    assert "legacy_import" in operations
    assert "research_bookmark_removed" in operations
    assert "research_bookmark_restored" in operations


def test_sqlite_allows_independent_same_code_bookmarks_across_process_instances(
    tmp_path: Path,
) -> None:
    _root, snapshot, row, first = _capture(tmp_path / "source")
    second = create_daily_market_research_bookmark(
        snapshot,
        row,
        sort_key="ma20",
        descending=False,
        stock_name="Fixture stock",
        filter_state="all",
    )
    settings = _config(tmp_path / "watchlist")
    repository_path = WatchlistService.repository_path(settings)
    repository = WatchlistRepository(repository_path, initialize=True)
    status = WatchlistService._repository_storage_status(
        repository_path,
        repository_path.with_name("default.json"),
    )
    first_process = WatchlistService(
        settings,
        repository=repository,
        storage_status=status,
    )
    assert first_process.add_research_bookmark(first).status == "added"
    assert first_process.add_research_bookmark(second).status == "added"
    revision = first_process.get_watchlist().revision
    assert first_process.add_research_bookmark(first).status == "already_present"
    assert first_process.get_watchlist().revision == revision

    second_process = WatchlistService(
        settings,
        repository=WatchlistRepository(repository_path),
        storage_status=status,
    )
    assert second_process.get_research_bookmark(first.bookmark_id).to_dict() == first.to_dict()
    assert second_process.get_research_bookmark(second.bookmark_id).to_dict() == second.to_dict()
    assert len(second_process.get_stocks()) == 2

    removed = second_process.remove_research_bookmark(first.bookmark_id)
    assert removed.status == "removed"
    assert second_process.get_research_bookmark(first.bookmark_id) is None
    assert second_process.get_research_bookmark(second.bookmark_id) is not None
    assert second_process.restore_research_bookmark(removed.restore_token).status == "restored"
    assert second_process.get_research_bookmark(first.bookmark_id).to_dict() == first.to_dict()


def test_add_rejects_invalid_payload_without_manual_fallback(tmp_path: Path) -> None:
    _root, _snapshot, _row, bookmark = _capture(tmp_path / "source")
    settings = _config(tmp_path / "watchlist")
    service = WatchlistService(settings)
    invalid = bookmark.to_dict()
    invalid["schema_version"] = "daily-market-research-bookmark.v0"
    with pytest.raises(DailyMarketResearchBookmarkError):
        service.add_research_bookmark(invalid)
    assert service.get_stocks() == []

    # 損毀 payload 仍保留研究收藏型別，不會回退成 manual。
    payload = json.loads(service.default_watchlist_file.read_text(encoding="utf-8"))
    payload["items"].append(
        {
            "stock_code": bookmark.stock_code,
            "stock_name": bookmark.stock_name,
            "added_at": "2026-10-05T12:00:00",
            "source": "manual",
            "source_id": bookmark.bookmark_id,
            "research_bookmark": invalid,
        }
    )
    service.default_watchlist_file.write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    reloaded = WatchlistService(settings)
    item = reloaded.get_stocks()[0]
    assert item["source"] == "daily_market_research_bookmark"
    assert item["research_bookmark"]["schema_version"] == "daily-market-research-bookmark.v0"
    with pytest.raises(DailyMarketResearchBookmarkError):
        reloaded.get_research_bookmark_context(bookmark.bookmark_id)
