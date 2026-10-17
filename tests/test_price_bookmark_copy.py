"""價格收藏沿已核技術副本另存；原根不可讀時仍保持查詢、精度及比較。"""
from dataclasses import replace
from decimal import Decimal
from hashlib import sha256
import builtins
import io
import json
import os
from pathlib import Path

import pytest

from app_module.technical_source_copy import TechnicalSourcePin, TechnicalSourceCopyError, copy_technical_source, restore_technical_source, copy_price_bookmarks
from app_module.research_output_copy import ResearchOutputCopyBudget
from app_module.daily_market_technical_universe_price_query_v1 import DailyMarketTechnicalUniversePriceQueryV1
from app_module.daily_market_technical_universe_price_comparison_v1 import DailyMarketTechnicalUniversePriceSelectionV1
from app_module.daily_market_technical_universe_price_bookmark_v1 import DailyMarketTechnicalUniversePriceBookmarkV1, read_daily_market_technical_universe_price_bookmark_v1
from app_module.watchlist_service import TECHNICAL_UNIVERSE_PRICE_BOOKMARK_SOURCE, WatchlistService, _bookmark_item_name
from tests.test_daily_market_technical_universe_price_query_v1 import exact_price_store, _open_session

BUDGET = ResearchOutputCopyBudget(16 * 1024**2, 256 * 1024**2, 10000, 32)


def _prepare(fixture, root, *, restore=False):
    session = _open_session(fixture)
    query = session.create_query(unknown_price_policy="include", descending=True, min_close_price=Decimal("0.00000000000001"),
                                 max_close_price=Decimal("999999999999999.999999999999"), technical_stock_filter=("S0001", "S0002", "S0003"))
    result = session.execute(query)
    def selected(code):
        # 兩頁的比較錨點必須各自保留頁碼，不合併成目前頁。
        for page_index in range(2):
            page = result.read_page(result.create_page_request(page_index, page_size=2))
            if any(row.technical_row.stock_code == code for row in page.rows):
                return DailyMarketTechnicalUniversePriceSelectionV1.from_page(query, page, code)
        raise AssertionError(code)
    bookmark = DailyMarketTechnicalUniversePriceBookmarkV1.create(selected=selected("S0001"), scroll_position=137,
        comparison_selections=(selected("S0003"), selected("S0002")))
    second = DailyMarketTechnicalUniversePriceBookmarkV1.create(selected=selected("S0002"), scroll_position=31)
    watchlist = root / "original-watchlist/default.json"
    watchlist.parent.mkdir(parents=True)
    payload = {"version": 1, "name": "原清單", "description": "原描述", "created_at": "2026-10-06T00:00:00+08:00", "updated_at": "2026-10-06T00:00:00+08:00",
        "items": [{"stock_code": value.stock_code, "stock_name": _bookmark_item_name(value), "added_at": "2026-10-06T00:00:00+08:00", "source": TECHNICAL_UNIVERSE_PRICE_BOOKMARK_SOURCE,
                   "source_id": value.bookmark_id, "research_bookmark": value.to_dict(), "notes": "保留筆記", "extension": {"original_uri": "keep://original"}} for value in (bookmark, second)]}
    watchlist.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    pin = TechnicalSourcePin(**{key: getattr(query.source, key) for key in TechnicalSourcePin.__dataclass_fields__})
    bundle = root / "technical"
    copy_technical_source(pin, bundle, budget=BUDGET)
    if restore:
        master_sha = sha256((bundle / "TECHNICAL_COPY_RECEIPT.json").read_bytes()).hexdigest()
        detached = root / "moved-archive"
        bundle.rename(detached)
        bundle = root / "restored"
        restore_technical_source(detached, master_sha, bundle, budget=BUDGET)
    return watchlist, bundle, bookmark, second


def _copy(watchlist, bundle, target, ids, **kwargs):
    return copy_price_bookmarks(watchlist, sha256(watchlist.read_bytes()).hexdigest(), bundle,
        sha256((bundle / "TECHNICAL_COPY_RECEIPT.json").read_bytes()).hexdigest(), target,
        bookmark_ids=ids, budget=kwargs.pop("budget", BUDGET), **kwargs)


@pytest.mark.parametrize("restore", [False, True])
def test_price_bookmark_new_copy_reopens_exact_pages_and_comparisons_without_old_root(exact_price_store, tmp_path, monkeypatch, restore):
    watchlist, bundle, bookmark, second = _prepare(exact_price_store, tmp_path, restore=restore)
    original = watchlist.read_bytes()
    original_bookmark = bookmark.to_json()
    old_root = exact_price_store["store_root"].parent
    attempts = []
    def guarded(fn):
        def open_file(path, *args, **kwargs):
            if isinstance(path, (str, bytes, os.PathLike)) and Path(os.fsdecode(path)).absolute().is_relative_to(old_root):
                attempts.append(str(path))
                pytest.fail("搬移收藏不得讀原來源根")
            return fn(path, *args, **kwargs)
        return open_file
    monkeypatch.setattr(builtins, "open", guarded(builtins.open))
    monkeypatch.setattr(io, "open", guarded(io.open))
    monkeypatch.setattr(os, "open", guarded(os.open))
    target = tmp_path / "new-output"
    receipt = _copy(watchlist, bundle, target, (bookmark.bookmark_id, second.bookmark_id))
    proof = json.loads(receipt.read_bytes())
    assert proof["selected_item_count"] == 2 and proof["original_item_count"] == 2
    assert watchlist.read_bytes() == (target / "original/source_watchlist.json").read_bytes() == original
    assert bookmark.to_json() == original_bookmark
    copied = json.loads((target / "watchlist/default.json").read_bytes())
    assert [row["notes"] for row in copied["items"]] == ["保留筆記", "保留筆記"]
    class Config:
        output_root = target
        def resolve_output_path(self, part):
            return target / part
    service = WatchlistService(Config())
    for row, old in zip(copied["items"], (bookmark, second)):
        new = service.get_research_bookmark(row["source_id"])
        assert type(new) is DailyMarketTechnicalUniversePriceBookmarkV1 and new.bookmark_id != old.bookmark_id
        state = read_daily_market_technical_universe_price_bookmark_v1(new)
        assert state.selected.selection.row_identity_sha256 == old.selected.row_identity_sha256
        assert new.scroll_position == old.scroll_position and new.selected.page_request.page_index == old.selected.page_request.page_index
        assert new.selected.close_price == old.selected.close_price and new.selected.raw_row_fingerprint_sha256 == old.selected.raw_row_fingerprint_sha256
        assert new.selected.query.min_close_price == old.selected.query.min_close_price
        assert row["extension"] == {"original_uri": "keep://original"}
        assert tuple(value.stock_code for value in new.comparison_selections) == tuple(value.stock_code for value in old.comparison_selections)
        if state.comparison:
            assert state.comparison.columns[0].row.price_state == "unknown"
            assert state.comparison.columns[0].row.price_fact.close_price is None
    assert not attempts and not (target / ".bookmark_copy_pending.json").exists()


@pytest.mark.parametrize("kind", ["wrong_master_sha", "wrong_watchlist_sha", "foreign_source", "pending", "bookmark_tamper", "duplicate_id", "protected", "cancelled"])
def test_price_bookmark_copy_refuses_unsafe_scope_before_target(exact_price_store, tmp_path, monkeypatch, kind):
    watchlist, bundle, bookmark, second = _prepare(exact_price_store, tmp_path)
    ids = (bookmark.bookmark_id,)
    target = tmp_path / "new-output"
    if kind == "pending":
        (bundle / ".technical_copy_pending.json").write_bytes(b"{}")
    elif kind == "bookmark_tamper":
        payload = json.loads(watchlist.read_bytes())
        payload["items"][0]["research_bookmark"]["scroll_position"] = 138
        watchlist.write_text(json.dumps(payload), encoding="utf-8")
    elif kind == "duplicate_id":
        ids = (bookmark.bookmark_id, bookmark.bookmark_id)
    elif kind == "protected":
        monkeypatch.setenv("PERSONAL_STORE_ROOT", str(target))
    elif kind == "foreign_source":
        master = bundle / "TECHNICAL_COPY_RECEIPT.json"
        body = json.loads(master.read_bytes())
        body["source_pin"]["receipt_sha256"] = "a" * 64
        master.write_text(json.dumps(body), encoding="utf-8")
    before = watchlist.read_bytes()
    expected = {"wrong_master_sha": "archive_sha_mismatch", "wrong_watchlist_sha": "source_sha_mismatch",
        "foreign_source": "original_source_not_in_lineage", "pending": "members_changed_or_pending",
        "bookmark_tamper": "bookmark_identity_mismatch", "duplicate_id": "explicit_ids_required",
        "protected": "protected_root", "cancelled": "cancelled"}[kind]
    with pytest.raises(ValueError, match=expected):
        copy_price_bookmarks(watchlist, "0" * 64 if kind == "wrong_watchlist_sha" else sha256(before).hexdigest(), bundle,
            "0" * 64 if kind == "wrong_master_sha" else sha256((bundle / "TECHNICAL_COPY_RECEIPT.json").read_bytes()).hexdigest(), target,
            bookmark_ids=ids, budget=BUDGET, cancel_callback=(lambda: True) if kind == "cancelled" else None)
    assert not target.exists() and watchlist.read_bytes() == before


def test_price_bookmark_copy_validates_original_item_name(exact_price_store, tmp_path):
    watchlist, bundle, bookmark, _ = _prepare(exact_price_store, tmp_path)
    data = json.loads(watchlist.read_bytes())
    data["items"][0]["stock_name"] = "不是原收藏的名稱"
    watchlist.write_text(json.dumps(data), encoding="utf-8")
    target = tmp_path / "new-output"
    with pytest.raises(TechnicalSourceCopyError, match="identity_conflict"):
        _copy(watchlist, bundle, target, (bookmark.bookmark_id,))
    assert not target.exists()


def test_price_bookmark_copy_quarantines_source_change_after_target_created(exact_price_store, tmp_path, monkeypatch):
    import app_module.technical_source_copy as module
    watchlist, bundle, bookmark, _ = _prepare(exact_price_store, tmp_path)
    target = tmp_path / "new-output"
    original = module._Archive.__init__
    raw = watchlist.read_bytes()
    def changed(self, *args, **kwargs):
        original(self, *args, **kwargs)
        if target.exists():
            watchlist.write_bytes(raw + b" ")
    monkeypatch.setattr(module._Archive, "__init__", changed)
    with pytest.raises(TechnicalSourceCopyError, match="source_changed"):
        _copy(watchlist, bundle, target, (bookmark.bookmark_id,))
    assert (target / ".bookmark_copy_pending.json").exists()
    assert (target / "BOOKMARK_COPY_FAILURE.json").exists()
    assert not (target / "BOOKMARK_COPY_RECEIPT.json").exists()
    assert (target / "original/source_watchlist.json").read_bytes() == raw


def test_price_bookmark_copy_cancel_after_creation_keeps_pending_and_source(exact_price_store, tmp_path):
    watchlist, bundle, bookmark, _ = _prepare(exact_price_store, tmp_path)
    raw = watchlist.read_bytes()
    target = tmp_path / "new-output"
    with pytest.raises(TechnicalSourceCopyError, match="cancelled"):
        _copy(watchlist, bundle, target, (bookmark.bookmark_id,), cancel_callback=lambda: target.exists())
    assert watchlist.read_bytes() == raw
    assert (target / ".bookmark_copy_pending.json").exists()
    assert (target / "BOOKMARK_COPY_FAILURE.json").exists()
    assert not (target / "BOOKMARK_COPY_RECEIPT.json").exists()
