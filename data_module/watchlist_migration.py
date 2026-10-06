"""只在指定 sandbox 內驗證 JSON 候選池副本遷移，不改原檔。"""

import hashlib
import json
from pathlib import Path
from typing import Any

from data_module.watchlist_repository import WatchlistRepository


_RESEARCH_BOOKMARK_SOURCE = "daily_market_research_bookmark"


def migrate_watchlist_copy(
    source: Path,
    destination: Path,
    *,
    sandbox_root: Path,
    watchlist_id: str = "default",
    validated_bookmark_ids: frozenset[str] | None = None,
) -> dict[str, Any]:
    """以 sandbox 限定方式複製 legacy JSON；預設仍要求股票代號唯一。

    只有 app service 已嚴格驗證 bookmark payload 後傳入 identity 清單時，
    同股 bookmark 才會以 bookmark ID 作為獨立項目身份。
    """

    root, source, destination = Path(sandbox_root).resolve(), Path(source).resolve(), Path(destination).resolve()
    if not source.is_relative_to(root) or not destination.is_relative_to(root) or source == destination:
        raise ValueError("來源副本與目標資料庫必須位於指定 sandbox 且互不相同")
    raw = source.read_bytes()
    source_hash = hashlib.sha256(raw).hexdigest()
    payload = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ValueError("候選池 JSON 缺有效 items")
    codes = []
    for item in payload["items"]:
        if not isinstance(item, dict) or not all(isinstance(item.get(key), str) and item[key].strip() for key in ("stock_code", "stock_name", "added_at", "source")):
            raise ValueError("候選池存在不可遷移的項目")
        codes.append(item["stock_code"].strip())
    if validated_bookmark_ids is not None:
        seen_identities: set[str] = set()
        seen_bookmark_ids: set[str] = set()
        for item, code in zip(payload["items"], codes):
            if item.get("source") == _RESEARCH_BOOKMARK_SOURCE or "research_bookmark" in item:
                bookmark = item.get("research_bookmark")
                bookmark_id = str(item.get("source_id") or "")
                if (
                    item.get("source") != _RESEARCH_BOOKMARK_SOURCE
                    or not isinstance(bookmark, dict)
                    or bookmark_id not in validated_bookmark_ids
                    or bookmark.get("bookmark_id") != bookmark_id
                    or bookmark.get("stock_code") != code
                    or bookmark_id in seen_bookmark_ids
                ):
                    raise ValueError("研究收藏身份未通過預檢")
                identity = f"bookmark:{bookmark_id}"
                seen_bookmark_ids.add(bookmark_id)
            else:
                identity = f"legacy:{code}"
            if identity in seen_identities:
                raise ValueError("候選池存在重複身份")
            seen_identities.add(identity)
        if seen_bookmark_ids != set(validated_bookmark_ids):
            raise ValueError("研究收藏 ID 集合與預檢不一致")
    if validated_bookmark_ids is None and len(set(codes)) != len(codes):
        raise ValueError("候選池存在重複股票身份")
    repository = WatchlistRepository(destination, initialize=True)
    existing = repository.load(watchlist_id)
    if existing is None:
        revision = repository.import_legacy_payload(
            watchlist_id,
            payload,
            source_hash=source_hash,
        )
    elif existing[0] == payload:
        revision = existing[1]
    else:
        raise RuntimeError("目標候選池已存在不同內容；禁止覆寫")
    loaded = repository.load(watchlist_id)
    if loaded is None or loaded[0] != payload or hashlib.sha256(source.read_bytes()).hexdigest() != source_hash:
        raise RuntimeError("候選池遷移比對失敗")
    return {"schema_version": "watchlist-copy.v1", "source_hash": source_hash, "item_count": len(codes), "revision": revision, "source_unchanged": True}
