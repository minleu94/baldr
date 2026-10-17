"""新副本必須遵守完整輸出預算，且不得發布有重複收藏身分的清單。"""
from dataclasses import replace
from hashlib import sha256
import json

import pytest

from app_module.technical_source_copy import TechnicalSourceCopyError, restore_technical_source
from tests.test_price_bookmark_copy import _prepare, _copy, BUDGET
from tests.test_daily_market_technical_universe_price_query_v1 import exact_price_store


def test_price_bookmark_total_budget_counts_receipt_before_publication(exact_price_store, tmp_path):
    watchlist, bundle, bookmark, _ = _prepare(exact_price_store, tmp_path)
    raw_master = (bundle / "TECHNICAL_COPY_RECEIPT.json").read_bytes()
    source_bytes = len(raw_master) + sum(item["bytes"] for item in json.loads(raw_master)["destination_files"])
    payload = json.loads(watchlist.read_bytes())
    payload["description"] = "原註記" + "L" * (source_bytes * 2 + 65536)
    watchlist.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    probe = tmp_path / "probe-output"
    receipt = _copy(watchlist, bundle, probe, (bookmark.bookmark_id,))
    # 範圍可容納原件＋新清單，卻不足以保存必要的完整收據；不能以此宣稱成功。
    limit = watchlist.stat().st_size + (probe / "watchlist/default.json").stat().st_size + receipt.stat().st_size // 2
    assert limit > source_bytes
    target = tmp_path / "limited-output"
    with pytest.raises(TechnicalSourceCopyError, match="byte_budget_exceeded"):
        _copy(watchlist, bundle, target, (bookmark.bookmark_id,), budget=replace(BUDGET, max_total_bytes=limit))
    assert not target.exists()


def test_price_bookmark_collapsed_transport_id_is_not_published_as_ambiguous(exact_price_store, tmp_path):
    watchlist, bundle, bookmark, _ = _prepare(exact_price_store, tmp_path)
    first = tmp_path / "first-bookmark-output"
    _copy(watchlist, bundle, first, (bookmark.bookmark_id,))
    copied_item = json.loads((first / "watchlist/default.json").read_bytes())["items"][0]
    original = json.loads(watchlist.read_bytes())
    original["items"] = [original["items"][0], copied_item]
    watchlist.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
    restored = tmp_path / "restored-technical"
    restore_technical_source(bundle, sha256((bundle / "TECHNICAL_COPY_RECEIPT.json").read_bytes()).hexdigest(), restored, budget=BUDGET)
    target = tmp_path / "new-output"
    with pytest.raises(TechnicalSourceCopyError, match="derived_identity_collision"):
        _copy(watchlist, restored, target, (bookmark.bookmark_id, copied_item["source_id"]))
    assert not target.exists()
