"""V2 複合 bookmark 只經明確 typed 路由持久化與讀回。"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app_module.daily_market_research_bookmark import DailyMarketResearchBookmarkError
from app_module.daily_market_technical_official_disposition_composite_bookmark_storage_v2 import (
    COMPOSITE_VIEW_BOOKMARK_ENVELOPE_SCHEMA_V2,
    COMPOSITE_VIEW_BOOKMARK_SOURCE_V2,
    DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2,
)
from app_module.watchlist_service import (
    COMPOSITE_VIEW_BOOKMARK_ENVELOPE_SCHEMA_V2 as WATCHLIST_V2_SCHEMA,
    COMPOSITE_VIEW_BOOKMARK_SOURCE_V2 as WATCHLIST_V2_SOURCE,
    WatchlistItem,
    WatchlistService,
    decode_daily_market_research_bookmark,
)

pytest_plugins = (
    "test_daily_market_technical_official_disposition_composite_bookmark_v2",
)


def _config(output_root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        output_root=output_root,
        resolve_output_path=lambda name: output_root / name,
    )


def test_v2_envelope_routes_through_json_and_sqlite_with_exact_identity(
    saved_v2_bookmark,
    tmp_path: Path,
) -> None:
    assert WATCHLIST_V2_SCHEMA == COMPOSITE_VIEW_BOOKMARK_ENVELOPE_SCHEMA_V2
    assert WATCHLIST_V2_SOURCE == COMPOSITE_VIEW_BOOKMARK_SOURCE_V2
    envelope = DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2.create(
        saved_v2_bookmark
    )
    identity = envelope.view_bookmark_identity_sha256
    config = _config(tmp_path / "watchlist-output")

    service = WatchlistService(config)
    added = service.add_composite_research_bookmark_v2(envelope)
    assert added.status == "added"
    assert added.bookmark_id == identity

    json_path = service.default_watchlist_file
    saved_json_bytes = json_path.read_bytes()
    saved_payload = json.loads(saved_json_bytes.decode("utf-8"))
    item = next(
        row for row in saved_payload["items"]
        if row.get("source_id") == identity
    )
    assert item["stock_code"] == envelope.stock_code
    assert item["source"] == COMPOSITE_VIEW_BOOKMARK_SOURCE_V2
    assert item["research_bookmark"] == envelope.to_dict()

    json_reopened_service = WatchlistService(config)
    json_reopened = json_reopened_service.read_composite_research_bookmark_v2(identity)
    assert type(json_reopened) is DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2
    assert json_reopened is not None
    assert json_reopened.to_dict() == envelope.to_dict()
    assert json_reopened.bookmark_json == saved_v2_bookmark.to_json()
    with pytest.raises(DailyMarketResearchBookmarkError) as generic_context:
        json_reopened_service.get_research_bookmark_context(identity)
    assert generic_context.value.code == "composite_bookmark_v2_typed_reopen_required"

    activated = json_reopened_service.upgrade_to_repository()
    assert activated.is_repository, activated.message
    assert json_path.read_bytes() == saved_json_bytes

    sqlite_reopened_service = WatchlistService(config)
    sqlite_reopened = sqlite_reopened_service.read_composite_research_bookmark_v2(identity)
    assert type(sqlite_reopened) is DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2
    assert sqlite_reopened is not None
    assert sqlite_reopened.to_dict() == envelope.to_dict()

    removed = sqlite_reopened_service.remove_research_bookmark(identity)
    assert removed.status == "removed"
    assert removed.restore_token is not None
    assert sqlite_reopened_service.read_composite_research_bookmark_v2(identity) is None
    restored = sqlite_reopened_service.restore_research_bookmark(removed.restore_token)
    assert restored.status == "restored"
    restored_envelope = WatchlistService(config).read_composite_research_bookmark_v2(identity)
    assert restored_envelope is not None
    assert restored_envelope.to_dict() == envelope.to_dict()


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("stock_code", "ZZZZ"),
        ("source", "generic_research_bookmark"),
        ("bookmark_sha256", "0" * 64),
        ("view_bookmark_identity_sha256", "0" * 64),
    ),
)
def test_v2_envelope_rejects_wrong_stock_source_or_identity_hash(
    saved_v2_bookmark,
    field: str,
    replacement: str,
) -> None:
    envelope = DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2.create(
        saved_v2_bookmark
    )
    payload = envelope.to_dict()
    if field == "stock_code" and replacement == envelope.stock_code:
        replacement = "YYYY"
    payload[field] = replacement

    with pytest.raises(ValueError):
        DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2.from_dict(
            payload
        )


def test_unknown_v2_schema_stays_in_v2_namespace_and_never_decodes_as_generic(
    saved_v2_bookmark,
) -> None:
    envelope = DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2.create(
        saved_v2_bookmark
    )
    payload = envelope.to_dict()
    payload["schema_version"] = "daily-market-technical-official-disposition-composite-view-state.v999"

    item = WatchlistItem.from_mapping({
        "stock_code": envelope.stock_code,
        "source": "manual",
        "research_bookmark": payload,
    })
    assert item.source == COMPOSITE_VIEW_BOOKMARK_SOURCE_V2
    assert item.research_bookmark == payload
    with pytest.raises(DailyMarketResearchBookmarkError):
        decode_daily_market_research_bookmark(payload)

