"""驗證 H20 收藏在 Watchlist JSON/COW 中保留來源與精確重開語義。"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from app_module.daily_market_research_bookmark import DailyMarketResearchBookmarkError
from app_module.recommendation.personal_h20_research_bookmark import (
    PERSONAL_H20_RESEARCH_BOOKMARK_SOURCE,
    PersonalH20ResearchBookmark,
)
from app_module.watchlist_service import (
    WatchlistItem,
    WatchlistService,
    decode_daily_market_research_bookmark,
)
from tests.test_personal_h20_research_bookmark import _fixture
from tests.test_personal_h20_research_cohort import public_reader


def _config(root: Path) -> SimpleNamespace:
    output_root = root / "output"
    return SimpleNamespace(
        output_root=output_root,
        resolve_output_path=lambda name: output_root / name,
    )


def _file_snapshot(root: Path) -> dict[Path, tuple[bytes, int]]:
    return {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in root.rglob("*")
        if path.is_file()
    }


def _restart_read_script(
    output_root: Path,
    bookmark_id: str,
    config_path: Path,
    market_root: Path,
) -> str:
    return f"""
import json
from pathlib import Path
from types import SimpleNamespace
from app_module.watchlist_service import WatchlistService
from tests.test_personal_h20_research_cohort import public_reader
output_root = Path({str(output_root)!r})
config = SimpleNamespace(
    output_root=output_root,
    resolve_output_path=lambda name: output_root / name,
)
service = WatchlistService(config)
bookmark = service.get_research_bookmark({bookmark_id!r})
state = service.get_personal_h20_research_bookmark_state(
    {bookmark_id!r},
    config_path=Path({str(config_path)!r}),
    market_root=Path({str(market_root)!r}),
    prediction_reader=public_reader,
)
print(json.dumps({{
    "bookmark_type": type(bookmark).__name__,
    "bookmark_id": bookmark.bookmark_id,
    "sort_descending": bookmark.sort_descending,
    "scroll_position": bookmark.scroll_position,
    "selected_symbol": state.selected_row.symbol,
    "decision_date": state.cohort.decision_date,
    "row_symbols": [row.symbol for row in state.cohort.rows],
    "model_binding_status": state.current_model_binding_status,
}}, sort_keys=True))
"""


def test_h20_bookmark_json_to_cow_keeps_same_stock_source_and_exact_reopen(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    fixture = _fixture(source_root)
    source_before = _file_snapshot(fixture["private_root"])
    settings = _config(tmp_path / "watchlist")
    service = WatchlistService(settings)

    assert service.add_stocks(
        [{"stock_code": fixture["bookmark"].stock_code, "stock_name": "合成手動列"}],
        source="manual",
    ) == 1
    added = service.add_research_bookmark(fixture["bookmark"])
    assert added.status == "added"
    assert service.add_research_bookmark(fixture["bookmark"]).status == "already_present"

    json_path = service.default_watchlist_file
    json_before_retry = json_path.read_bytes()
    entries = service.get_stocks()
    assert len(entries) == 2
    assert {entry["stock_code"] for entry in entries} == {fixture["bookmark"].stock_code}
    h20_entry = next(entry for entry in entries if entry["source"] == PERSONAL_H20_RESEARCH_BOOKMARK_SOURCE)
    assert h20_entry["source_id"] == fixture["bookmark"].bookmark_id
    assert json_path.read_bytes() == json_before_retry

    typed = service.get_research_bookmark(fixture["bookmark"].bookmark_id)
    assert isinstance(typed, PersonalH20ResearchBookmark)
    with pytest.raises(DailyMarketResearchBookmarkError) as generic_context:
        service.get_research_bookmark_context(fixture["bookmark"].bookmark_id)
    assert generic_context.value.code == "personal_h20_bookmark_typed_reopen_required"

    status = service.upgrade_to_repository()
    assert status.is_repository, status.message
    reopened = WatchlistService(settings)
    assert reopened.get_storage_status().is_repository
    decoded = reopened.get_research_bookmark(fixture["bookmark"].bookmark_id)
    assert isinstance(decoded, PersonalH20ResearchBookmark)
    assert decoded.to_dict() == fixture["bookmark"].to_dict()
    assert reopened.repository is not None

    state = reopened.get_personal_h20_research_bookmark_state(
        fixture["bookmark"].bookmark_id,
        config_path=fixture["activation"].config_path,
        market_root=fixture["market_root"],
        prediction_reader=public_reader,
    )
    assert state.selected_row.symbol == fixture["selection"].symbol
    assert state.bookmark.sort_descending is False
    assert state.bookmark.scroll_position == 17
    assert state.current_model_binding_status == "enabled_same_contract"

    before_cancel = reopened.repository.db_path.read_bytes()
    with pytest.raises(InterruptedError, match="personal_h20_bookmark_cancelled"):
        reopened.get_personal_h20_research_bookmark_state(
            fixture["bookmark"].bookmark_id,
            config_path=fixture["activation"].config_path,
            market_root=fixture["market_root"],
            prediction_reader=public_reader,
            cancel_callback=lambda: True,
        )
    assert reopened.repository.db_path.read_bytes() == before_cancel

    removed = reopened.remove_research_bookmark(fixture["bookmark"].bookmark_id)
    assert removed.status == "removed"
    assert removed.restore_token is not None
    assert reopened.get_research_bookmark(fixture["bookmark"].bookmark_id) is None
    assert reopened.restore_research_bookmark(removed.restore_token).status == "restored"
    restored = reopened.get_research_bookmark(fixture["bookmark"].bookmark_id)
    assert isinstance(restored, PersonalH20ResearchBookmark)
    assert restored.to_dict() == fixture["bookmark"].to_dict()

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            _restart_read_script(
                settings.output_root,
                fixture["bookmark"].bookmark_id,
                fixture["activation"].config_path,
                fixture["market_root"],
            ),
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    fresh_process = json.loads(completed.stdout)
    assert fresh_process == {
        "bookmark_id": fixture["bookmark"].bookmark_id,
        "bookmark_type": "PersonalH20ResearchBookmark",
        "decision_date": fixture["cohort"].decision_date,
        "model_binding_status": "enabled_same_contract",
        "row_symbols": [row.symbol for row in fixture["cohort"].rows],
        "scroll_position": 17,
        "selected_symbol": fixture["selection"].symbol,
        "sort_descending": False,
    }
    assert _file_snapshot(fixture["private_root"]) == source_before


def test_h20_identity_collision_and_corrupt_schema_refuse_without_overwrite(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    fixture = _fixture(source_root)
    settings = _config(tmp_path / "collision-watchlist")
    collision_service = WatchlistService(settings)
    bookmark = fixture["bookmark"]
    assert collision_service.add_stocks(
        [
            {
                "stock_code": bookmark.stock_code,
                "stock_name": "同股手動來源",
                "source_id": bookmark.bookmark_id,
            }
        ],
        source="manual",
    ) == 1
    collision_bytes = collision_service.default_watchlist_file.read_bytes()
    conflict = collision_service.add_research_bookmark(bookmark)
    assert conflict.status == "conflict"
    assert conflict.code == "bookmark_source_id_conflict"
    assert collision_service.default_watchlist_file.read_bytes() == collision_bytes

    corrupt_settings = _config(tmp_path / "corrupt-watchlist")
    corrupt_service = WatchlistService(corrupt_settings)
    assert corrupt_service.add_research_bookmark(bookmark).status == "added"
    corrupt_path = corrupt_service.default_watchlist_file
    payload = json.loads(corrupt_path.read_text(encoding="utf-8"))
    raw_bookmark = payload["items"][0]["research_bookmark"]
    raw_bookmark["schema_version"] = "personal-h20-research-bookmark.v999"
    inferred_item = WatchlistItem.from_mapping(
        {
            "stock_code": bookmark.stock_code,
            "stock_name": bookmark.stock_code,
            "added_at": "2026-10-07T00:00:00",
            "source": "manual",
            "source_id": bookmark.bookmark_id,
            "research_bookmark": raw_bookmark,
        }
    )
    assert inferred_item.source == PERSONAL_H20_RESEARCH_BOOKMARK_SOURCE
    raw_bytes = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    corrupt_path.write_bytes(raw_bytes)

    with pytest.raises(DailyMarketResearchBookmarkError) as schema_error:
        decode_daily_market_research_bookmark(raw_bookmark)
    assert schema_error.value.code == "bookmark_schema_mismatch"

    corrupt_reopened = WatchlistService(corrupt_settings)
    with pytest.raises(DailyMarketResearchBookmarkError):
        corrupt_reopened.get_research_bookmark(bookmark.bookmark_id)
    retry = corrupt_reopened.add_research_bookmark(bookmark)
    assert retry.status == "conflict"
    assert corrupt_path.read_bytes() == raw_bytes

    upgrade = corrupt_reopened.upgrade_to_repository()
    assert not upgrade.is_repository
    assert corrupt_path.read_bytes() == raw_bytes
    assert not corrupt_reopened.canonical_repository_path.exists()
