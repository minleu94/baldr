from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from app_module.daily_market_research_bookmark import (
    ORIGINAL_STOCK_RANKING_BOOKMARK_SCHEMA,
    ORIGINAL_STOCK_RANKING_BOOKMARK_SOURCE,
    DailyMarketResearchBookmarkError,
    OriginalStockRankingBookmark,
    _rank_context_payload,
    _rank_query_payload,
    _sha256,
    decode_daily_market_research_bookmark,
)
from app_module.research_session.session_dtos import (
    ResearchRankContextDTO,
    ResearchStockContextDTO,
)
from app_module.watchlist_service import WatchlistService
from tests.test_original_stock_ranking import market, _publish, _read, _ranking_pointer


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _rank_bookmark() -> OriginalStockRankingBookmark:
    universe = '{"codes":["2330","2317"]}'
    parameters = '{"lookback":5,"volume_weight":true}'
    rank = ResearchRankContextDTO(
        rank_kind="original_stock_ranking",
        period="week",
        direction="strong",
        rank_snapshot_id=_sha("rank-identity"),
        source_hash=_sha("rank-manifest"),
        ranking_root="C:/isolated/rankings",
        snapshot_root="C:/isolated/snapshots",
        decision_date="2026-10-02",
        parent_snapshot_id=_sha("parent-identity"),
        parent_snapshot_hash=_sha("parent-manifest"),
        parent_cohort_id=_sha("cohort"),
        selected_stock_code="2330",
        selected_rank=1,
        comparison_date="2026-09-28",
        latest_date="2026-10-02",
        comparison_window_dates=("2026-09-28", "2026-09-29", "2026-10-02"),
        comparison_window_rule="native_week_third_row_fallback",
        volume_reference_point_count=2,
        declared_stock_codes=("2330", "2317"),
        eligible_stock_codes=("2330", "2317"),
        missing_rank_stock_codes=(),
        research_universe_json=universe,
        research_universe_sha256=_sha(universe),
        method_name="fixture_method",
        method_version="1",
        method_contract_sha256=_sha("method-contract"),
        engine_file_sha256=_sha("engine-file"),
        engine_parameters_json=parameters,
        engine_parameters_sha256=_sha(parameters),
        source_schema_sha256=_sha("schema"),
        selected_input_fingerprint_sha256=_sha("stock-input"),
        filter_state="all",
        sort_key="rank",
        descending=False,
    )
    context = ResearchStockContextDTO(
        stock_code="2330",
        stock_name="Fixture stock",
        decision_date="2026-10-02",
        data_date="2026-10-02",
        source_snapshot_id=rank.parent_snapshot_id,
        source_snapshot_hash=rank.parent_snapshot_hash,
        source_kind=ORIGINAL_STOCK_RANKING_BOOKMARK_SOURCE,
        source_label="原始強弱排名收藏",
        source_workspace="watchlist",
        daily_snapshot_root=rank.snapshot_root,
        daily_snapshot_cohort_id=rank.parent_cohort_id,
        daily_snapshot_condition_keys="close_above_ma20",
        daily_snapshot_combine_mode="OR",
        rank_context=rank,
    )
    query_sha = _sha256(_rank_query_payload(context))
    identity_payload = {
        'schema_version': ORIGINAL_STOCK_RANKING_BOOKMARK_SCHEMA,
        'stock_code': context.stock_code,
        'source_hash': rank.source_hash,
        'rank_snapshot_id': rank.rank_snapshot_id,
        'period': rank.period,
        'direction': rank.direction,
        'filter_state': rank.filter_state,
        'sort_key': rank.sort_key,
        'descending': rank.descending,
        'daily_snapshot_condition_keys': context.daily_snapshot_condition_keys,
        'daily_snapshot_combine_mode': context.daily_snapshot_combine_mode,
        'query_sha256': query_sha,
    }
    bookmark_id = f"rank-{_sha256(identity_payload)}"
    context = ResearchStockContextDTO(
        **{
            **{key: value for key, value in _rank_context_payload(context).items() if key != "source_id"},
            "source_id": bookmark_id,
        }
    )
    provisional = OriginalStockRankingBookmark(
        bookmark_id=bookmark_id,
        stock_code=context.stock_code,
        stock_name=context.stock_name,
        context_json=json.dumps(
            _rank_context_payload(context), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ),
        _query_sha256=query_sha,
        _payload_sha256="",
    )
    body = provisional.to_dict()
    body.pop("payload_sha256")
    return decode_daily_market_research_bookmark({**body, "payload_sha256": _sha256(body)})


def _config(root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        output_root=root / "output",
        resolve_output_path=lambda name: root / "output" / name,
    )


def test_rank_bookmark_v2_codec_is_strict_and_keeps_full_window_query() -> None:
    bookmark = _rank_bookmark()
    payload = bookmark.to_dict()
    assert set(payload) == {
        "schema_version", "bookmark_id", "payload_sha256", "query_sha256",
        "stock_code", "stock_name", "source", "source_workspace", "source_id",
        "result_id", "context",
    }
    assert bookmark.context.rank_context is not None
    assert bookmark.context.rank_context.comparison_window_dates == (
        "2026-09-28", "2026-09-29", "2026-10-02"
    )
    assert bookmark.context.daily_snapshot_combine_mode == "OR"
    assert "score" not in bookmark.context.rank_context.to_dict()

    wrong_payload_hash = deepcopy(payload)
    wrong_payload_hash["stock_name"] = "tampered"
    with pytest.raises(DailyMarketResearchBookmarkError, match="SHA"):
        decode_daily_market_research_bookmark(wrong_payload_hash)

    bool_as_rank = deepcopy(payload)
    bool_as_rank["context"]["rank_context"]["selected_rank"] = True
    body = {key: value for key, value in bool_as_rank.items() if key != "payload_sha256"}
    bool_as_rank["payload_sha256"] = _sha256(body)
    with pytest.raises(DailyMarketResearchBookmarkError):
        decode_daily_market_research_bookmark(bool_as_rank)


def test_rank_bookmark_watchlist_duplicate_remove_and_restore_use_same_ledger(
    tmp_path: Path,
) -> None:
    service = WatchlistService(_config(tmp_path))
    bookmark = _rank_bookmark()

    first = service.add_rank_research_bookmark(bookmark)
    assert first.status == "added"
    assert first.source_id == bookmark.bookmark_id
    revision = first.revision
    second = service.add_rank_research_bookmark(bookmark)
    assert second.status == "already_present"
    assert second.revision == revision

    item = service.get_stocks()[0]
    assert item["source"] == ORIGINAL_STOCK_RANKING_BOOKMARK_SOURCE
    assert item["research_bookmark"]["schema_version"] == ORIGINAL_STOCK_RANKING_BOOKMARK_SCHEMA
    assert service.get_research_bookmark(bookmark.bookmark_id) == bookmark

    removed = service.remove_research_bookmark(bookmark.bookmark_id)
    assert removed.status == "removed"
    assert removed.restore_token is not None
    assert service.get_research_bookmark(bookmark.bookmark_id) is None
    restored = service.restore_research_bookmark(removed.restore_token)
    assert restored.status == "restored"
    assert service.get_research_bookmark(bookmark.bookmark_id) == bookmark


def test_pinned_rank_keeps_original_when_latest_pointer_changes_and_refuses_wrong_sources(
    market: dict, tmp_path: Path,
) -> None:
    """僅用三股隔離 DB 驗原 artifact；不接正式 producer／資料。"""
    from app_module.daily_market_research_bookmark import (
        create_original_stock_ranking_bookmark,
        create_original_stock_ranking_bookmark_from_context,
    )
    from app_module.original_stock_ranking import (
        OriginalStockRankingError,
        load_original_stock_ranking_from_context,
    )

    assert _publish(market)['status'] == 'published'
    ranking = _read(market)
    code = ranking.rows[0]['stock_code']
    bookmark = create_original_stock_ranking_bookmark(
        market['snapshot'], ranking, ranking_root=market['ranking_root'],
        stock_code=code, stock_name='隔離測試股',
    )
    rank = bookmark.context.rank_context
    assert rank is not None
    watchlist = WatchlistService(_config(tmp_path/'watchlist'))
    assert watchlist.add_rank_research_bookmark(bookmark).status == 'added'
    # 明確改壞隔離 latest；已收藏的原 hash 不應被新 pointer 取代。
    _ranking_pointer(market).write_text('{"unsupported_latest":true}', encoding='utf-8')
    readback = watchlist.get_rank_research_bookmark_context(
        bookmark.bookmark_id, db_path=market['db_path'],
    )
    assert readback.succeeded and readback.context == bookmark.context
    assert readback.row['score_label'] == ranking.rows[0]['score_label']
    assert create_original_stock_ranking_bookmark_from_context(
        bookmark.context, db_path=market['db_path'],
    ).to_dict() == bookmark.to_dict()

    other = next(c for c in rank.eligible_stock_codes if c != code)
    invalid = [
        {'source_hash':'f'*64},
        {'selected_stock_code':other},
        {'decision_date':'2026-10-06'},
        {'method_version':'unsupported-old-method'},
        {'source_schema_sha256':'e'*64},
    ]
    for values in invalid:
        with pytest.raises((OriginalStockRankingError, ValueError)):
            context = replace(rank, **values)
            load_original_stock_ranking_from_context(context, db_path=market['db_path'])

    # 原決策日前的 fixture row 修訂必須拒絕；保留收藏 payload，不換 latest。
    with sqlite3.connect(market['db_path']) as connection:
        connection.execute(
            'UPDATE daily_prices SET "收盤價" = ? WHERE "證券代號" = ? AND "日期" = ?',
            ('999', code, '2026-10-05'),
        )
    refused = watchlist.get_rank_research_bookmark_context(
        bookmark.bookmark_id, db_path=market['db_path'],
    )
    assert not refused.succeeded and refused.status == 'wrong_hash'
    assert refused.code == 'ranking_source_input_hash_mismatch' and refused.message
    assert watchlist.get_research_bookmark(bookmark.bookmark_id).to_dict() == bookmark.to_dict()
