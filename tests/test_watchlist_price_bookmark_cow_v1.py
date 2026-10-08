"""驗證 F07 價格收藏經 JSON COW 啟用後仍可精確重開。"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
from types import SimpleNamespace
from typing import Any

import pytest

from app_module.daily_market_technical_universe_price_bookmark_v1 import (
    DailyMarketTechnicalUniversePriceBookmarkV1,
    create_daily_market_technical_universe_price_bookmark_v1,
)
from app_module.watchlist_cow_activation import cow_activation_marker_path
from app_module.watchlist_service import (
    TECHNICAL_UNIVERSE_PRICE_BOOKMARK_SOURCE,
    WatchlistService,
)
from app_module.personal_data_paths import to_internal_io_path
from tests.test_ui_qt_technical_official_main_new_process import (
    _close_process_job,
    _process_is_active,
    _spawn_child_process,
    _terminate_process_tree,
)
from tests.test_daily_market_technical_universe_price_query_v1 import (
    _open_session,
    exact_price_store,
)


def _make_bookmark(
    exact_price_store: dict[str, Any],
) -> DailyMarketTechnicalUniversePriceBookmarkV1:
    session = _open_session(exact_price_store)
    query = session.create_query(unknown_price_policy="include")
    result = session.execute(query)
    page = result.read_page(result.create_page_request(0, page_size=4))
    return create_daily_market_technical_universe_price_bookmark_v1(
        query,
        page,
        "S0001",
        scroll_position=37,
    )


def _config(root: Path) -> SimpleNamespace:
    output_root = root / "private-output"
    return SimpleNamespace(
        output_root=output_root,
        resolve_output_path=lambda name: output_root / name,
    )


def _store_snapshot(root: Path) -> dict[str, tuple[int, int, str]]:
    """保存合成研究來源的檔案身份，確保觀察清單操作未改動它。"""

    internal_root = to_internal_io_path(root)
    assert os.path.isdir(internal_root)
    result: dict[str, tuple[int, int, str]] = {}
    pending = [(internal_root, Path())]
    while pending:
        directory, relative_directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                relative = relative_directory / entry.name
                if entry.is_symlink():
                    raise AssertionError(f"研究來源出現 symlink：{relative.as_posix()}")
                if entry.is_dir(follow_symlinks=False):
                    pending.append((entry.path, relative))
                    continue
                if not entry.is_file(follow_symlinks=False):
                    raise AssertionError(f"研究來源出現非一般檔案：{relative.as_posix()}")
                metadata = entry.stat(follow_symlinks=False)
                assert stat.S_ISREG(metadata.st_mode)
                digest = hashlib.sha256()
                with open(entry.path, "rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                result[relative.as_posix()] = (
                    metadata.st_size,
                    metadata.st_mtime_ns,
                    digest.hexdigest(),
                )
    assert result
    return result


def _legacy_payload(
    bookmark: DailyMarketTechnicalUniversePriceBookmarkV1,
) -> dict[str, object]:
    return {
        "version": 1,
        "name": "預設觀察清單",
        "description": "F07 COW 隔離測試",
        "created_at": "2026-10-08T09:00:00",
        "updated_at": "2026-10-08T09:05:00",
        "items": [
            {
                "stock_code": bookmark.stock_code,
                "stock_name": bookmark.stock_code,
                "added_at": "2026-10-08T09:00:00",
                "source": TECHNICAL_UNIVERSE_PRICE_BOOKMARK_SOURCE,
                "source_id": bookmark.bookmark_id,
                "research_bookmark": bookmark.to_dict(),
            }
        ],
    }


def _fresh_process_script() -> str:
    return r'''
import json
import sys
import os
import time
from pathlib import Path
from types import SimpleNamespace

from app_module.daily_market_technical_universe_price_bookmark_v1 import (
    DailyMarketTechnicalUniversePriceBookmarkV1,
    read_daily_market_technical_universe_price_bookmark_v1,
)
from app_module.watchlist_service import WatchlistService

output_root = Path(sys.argv[1])
bookmark_id = sys.argv[2]
expected = json.loads(sys.argv[3])
pid = os.getpid()
parent_pid = os.getppid()
monotonic_boot_ns = time.monotonic_ns()
config = SimpleNamespace(
    output_root=output_root,
    resolve_output_path=lambda name: output_root / name,
)
service = WatchlistService(config)
assert service.get_storage_status().mode == "repository"
assert service.repository is not None
bookmark = service.get_research_bookmark(bookmark_id)
assert type(bookmark) is DailyMarketTechnicalUniversePriceBookmarkV1
assert bookmark.to_dict() == expected["payload"]
state = read_daily_market_technical_universe_price_bookmark_v1(bookmark)
selected = state.selected
page_codes = [row.technical_row.stock_code for row in selected.page.rows]
source_pins = selected.query.source.to_dict()
assert expected["selected_stock_code"] in page_codes
assert selected.query.query_identity_sha256 == expected["query_identity_sha256"]
assert selected.page.page_identity_sha256 == expected["page_identity_sha256"]
assert selected.query.source.source_identity_sha256 == expected["source_identity_sha256"]
assert source_pins == expected["source_pins"]
assert selected.row.technical_row.stock_code == expected["selected_stock_code"]
print(json.dumps({
    "pid": pid,
    "parent_pid": parent_pid,
    "monotonic_boot_ns": monotonic_boot_ns,
    "executable": sys.executable,
    "prefix": sys.prefix,
    "mode": service.get_storage_status().mode,
    "repository_path": str(service.repository.db_path),
    "bookmark": bookmark.to_dict(),
    "selected_stock_code": selected.row.technical_row.stock_code,
    "query_identity_sha256": selected.query.query_identity_sha256,
    "page_identity_sha256": selected.page.page_identity_sha256,
    "source_identity_sha256": selected.query.source.source_identity_sha256,
    "source_pins": source_pins,
    "page_codes": page_codes,
}, ensure_ascii=False, sort_keys=True))
'''


def test_price_bookmark_survives_json_cow_sqlite_restore_and_new_process(
    exact_price_store: dict[str, Any], tmp_path: Path,
) -> None:
    bookmark = _make_bookmark(exact_price_store)
    store_root = Path(exact_price_store["store_root"])
    store_before = _store_snapshot(store_root)
    plan = exact_price_store["plan"]
    receipt = exact_price_store["receipt"]
    expected_source_pins = {
        "generation_identity_sha256": plan.generation_identity_sha256,
        "plan_identity_sha256": plan.identity_sha256,
        "plan_sha256": exact_price_store["plan_sha256"],
        "receipt_identity_sha256": receipt.identity_sha256,
        "receipt_sha256": receipt.content_sha256,
    }

    config = _config(tmp_path)
    legacy = WatchlistService(config)
    source = legacy.default_watchlist_file
    assert legacy.get_storage_status().mode != "repository"
    assert legacy.add_research_bookmark(bookmark).status == "added"
    original_json = source.read_bytes()
    decoded_json = json.loads(original_json.decode("utf-8"))
    row = decoded_json["items"][0]
    assert row["source"] == TECHNICAL_UNIVERSE_PRICE_BOOKMARK_SOURCE
    assert row["source_id"] == bookmark.bookmark_id
    assert row["research_bookmark"] == bookmark.to_dict()

    upgraded_status = legacy.upgrade_to_repository()
    assert upgraded_status.mode == "repository"
    assert legacy.repository is not None
    assert legacy.repository.db_path.is_file()
    marker = cow_activation_marker_path(source)
    assert marker.is_file()
    assert source.read_bytes() == original_json

    reopened = WatchlistService(config)
    assert reopened.get_storage_status().mode == "repository"
    assert reopened.repository is not None
    assert reopened.repository.db_path == legacy.repository.db_path
    loaded = reopened.get_research_bookmark(bookmark.bookmark_id)
    assert type(loaded) is DailyMarketTechnicalUniversePriceBookmarkV1
    assert loaded.to_dict() == bookmark.to_dict()

    removed = reopened.remove_research_bookmark(bookmark.bookmark_id)
    assert removed.status == "removed"
    assert removed.restore_token is not None
    assert reopened.get_research_bookmark(bookmark.bookmark_id) is None
    restored = reopened.restore_research_bookmark(removed.restore_token)
    assert restored.status == "restored"
    restored_bookmark = reopened.get_research_bookmark(bookmark.bookmark_id)
    assert type(restored_bookmark) is DailyMarketTechnicalUniversePriceBookmarkV1
    assert restored_bookmark.to_dict() == bookmark.to_dict()
    assert source.read_bytes() == original_json

    expected = {
        "payload": bookmark.to_dict(),
        "selected_stock_code": bookmark.stock_code,
        "query_identity_sha256": bookmark.selected.query.query_identity_sha256,
        "page_identity_sha256": bookmark.selected.page_identity_sha256,
        "source_identity_sha256": bookmark.selected.source_identity_sha256,
        "source_pins": bookmark.selected.query.source.to_dict(),
    }
    command = [
        sys.executable,
        "-B",
        "-X",
        "utf8",
        "-c",
        _fresh_process_script(),
        str(config.output_root),
        bookmark.bookmark_id,
        json.dumps(expected, ensure_ascii=False, sort_keys=True),
    ]
    process, job_handle = _spawn_child_process(
        command,
        cwd=str(Path(__file__).resolve().parents[1]),
        env=os.environ.copy(),
    )
    try:
        child_stdout, child_stderr = process.communicate(timeout=60)
    except subprocess.TimeoutExpired as exc:
        _terminate_process_tree(process, job_handle=job_handle)
        try:
            process.communicate(timeout=10)
        except subprocess.TimeoutExpired as cleanup_error:
            raise AssertionError("F07 fresh Python 子程序超時後未能收束") from cleanup_error
        raise AssertionError("F07 fresh Python 子程序超過 60 秒") from exc
    finally:
        _close_process_job(job_handle)

    assert process.returncode == 0, child_stderr
    child_report = json.loads(child_stdout.strip().splitlines()[-1])
    assert type(child_report["pid"]) is int
    assert type(child_report["parent_pid"]) is int
    assert type(child_report["monotonic_boot_ns"]) is int
    assert child_report["monotonic_boot_ns"] > 0
    assert isinstance(child_report["executable"], str) and child_report["executable"]
    assert isinstance(child_report["prefix"], str) and child_report["prefix"]
    assert child_report["pid"] != os.getpid()
    assert child_report["parent_pid"] in {os.getpid(), process.pid}
    if child_report["parent_pid"] == process.pid:
        assert child_report["pid"] != process.pid
    else:
        assert child_report["pid"] == process.pid
    assert child_report["executable"] == sys.executable
    assert child_report["prefix"] == sys.prefix
    assert not _process_is_active(child_report["pid"])
    assert child_report["mode"] == "repository"
    assert child_report["bookmark"] == bookmark.to_dict()
    assert child_report["selected_stock_code"] == bookmark.stock_code
    assert bookmark.stock_code in child_report["page_codes"]
    assert child_report["source_pins"]["generation_identity_sha256"] == plan.generation_identity_sha256
    assert child_report["source_pins"]["plan_identity_sha256"] == plan.identity_sha256
    assert child_report["source_pins"]["plan_sha256"] == exact_price_store["plan_sha256"]
    assert child_report["source_pins"]["receipt_identity_sha256"] == receipt.identity_sha256
    assert child_report["source_pins"]["receipt_sha256"] == receipt.content_sha256
    assert source.read_bytes() == original_json
    assert _store_snapshot(store_root) == store_before


@pytest.mark.parametrize(
    "mutation",
    ["unknown_schema", "outer_stock_code", "source_id", "source_mismatch", "duplicate"],
)
def test_price_bookmark_invalid_json_refuses_cow_without_activation(
    exact_price_store: dict[str, Any], tmp_path: Path, mutation: str,
) -> None:
    bookmark = _make_bookmark(exact_price_store)
    store_root = Path(exact_price_store["store_root"])
    store_before = _store_snapshot(store_root)
    config = _config(tmp_path / mutation)
    service = WatchlistService(config)
    source = service.default_watchlist_file
    payload = _legacy_payload(bookmark)
    items = payload["items"]
    assert isinstance(items, list)
    item_value = items[0]
    assert isinstance(item_value, dict)
    item: dict[str, object] = item_value
    raw_bookmark = item["research_bookmark"]
    assert isinstance(raw_bookmark, dict)

    if mutation == "unknown_schema":
        raw_bookmark["schema_version"] = (
            "daily-market-technical-universe-price-bookmark.v99"
        )
    elif mutation == "outer_stock_code":
        item["stock_code"] = "S0002"
    elif mutation == "source_id":
        item["source_id"] = "0" * 64
    elif mutation == "source_mismatch":
        item["source"] = "manual"
    elif mutation == "duplicate":
        items.append(dict(item))
    else:  # pragma: no cover - pytest parameter contract
        raise AssertionError(f"未知 mutation：{mutation}")

    source.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    original_json = source.read_bytes()
    status = service.upgrade_to_repository()

    assert status.mode == "upgrade_available"
    assert service.repository is None
    assert service.canonical_repository_path.exists() is False
    assert not cow_activation_marker_path(source).exists()
    assert not list(source.parent.glob("watchlists.v3-cow-*.sqlite"))
    assert source.read_bytes() == original_json
    assert _store_snapshot(store_root) == store_before
