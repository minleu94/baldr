"""v4 bookmark 僅重開固定 query/stock/comparison 保存身份。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from app_module.daily_market_technical_universe_v4_bookmark import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_SOURCE,
    DailyMarketTechnicalUniverseV4Bookmark,
    DailyMarketTechnicalUniverseV4BookmarkError,
    create_daily_market_technical_universe_v4_bookmark,
    read_daily_market_technical_universe_v4_bookmark,
)
from app_module.daily_market_technical_universe_v4_producer import (
    DailyMarketTechnicalUniverseV4ProductionRequest,
    produce_daily_market_technical_universe_v4,
)
from app_module.daily_market_technical_universe_v4_query import (
    DailyMarketTechnicalUniverseV4Query,
)
from app_module.daily_market_technical_universe_v4_stock import (
    read_daily_market_technical_universe_v4_stock,
)
from app_module.daily_market_technical_universe_v4_store import (
    DailyMarketTechnicalUniverseV4Cohort,
)
from app_module.personal_data_paths import to_internal_io_path
from app_module.rule_research_sample_capture import ResearchCaptureWriteScope
from app_module.rule_research_technical_parent_capture_v4 import (
    read_daily_market_technical_parent_capture_v4,
)


_TAIPEI = ZoneInfo("Asia/Taipei")
_DECISION_DATE = date(2026, 10, 6)
_STOCK_CODES = ("2382", "3008", "9999")


def _write_synthetic_source(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE daily_prices ("
            "日期 TEXT, 證券代號 TEXT, 開盤價 TEXT, 最高價 TEXT, "
            "最低價 TEXT, 收盤價 TEXT, 成交股數 INTEGER)"
        )
        connection.executemany(
            "INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)",
            [
                (
                    (_DECISION_DATE - timedelta(days=39 - index)).isoformat(),
                    code,
                    str(100 + index),
                    str(101 + index),
                    str(99 + index),
                    str(100 + index),
                    1000 + index,
                )
                for code in _STOCK_CODES
                for index in range(40)
            ],
        )


@pytest.fixture(scope="module")
def pinned_bookmark() -> Any:
    temporary_root = Path(tempfile.gettempdir()).resolve(strict=True)
    root = Path(tempfile.mkdtemp(prefix="uv4bookmark-", dir=temporary_root)).resolve(strict=True)
    try:
        database = root / "synthetic-prices.sqlite"
        _write_synthetic_source(database)
        scope = ResearchCaptureWriteScope(root / "research", database)
        store_root = scope.root / "technical-universe"
        cohort = DailyMarketTechnicalUniverseV4Cohort.create(
            universe_id="synthetic-universe-bookmark",
            population_version="fixture-v1",
            decision_date=_DECISION_DATE,
            raw_stock_codes=_STOCK_CODES,
        )
        first_result = produce_daily_market_technical_universe_v4(
            DailyMarketTechnicalUniverseV4ProductionRequest(
                source_database=database,
                cohort=cohort,
                decision_cutoff=datetime(2026, 10, 6, 16, 0, tzinfo=_TAIPEI),
                store_output_root=store_root,
                research_scope=scope,
            )
        )
        assert first_result.status == "complete", first_result.to_dict()
        assert first_result.plan is not None
        assert first_result.receipt is not None
        assert first_result.plan_sha256 is not None
        query = DailyMarketTechnicalUniverseV4Query.create(
            store_output_root=store_root,
            generation_identity_sha256=first_result.plan.generation_identity_sha256,
            plan_identity_sha256=first_result.plan.identity_sha256,
            plan_sha256=first_result.plan_sha256,
            receipt_identity_sha256=first_result.receipt.identity_sha256,
            receipt_sha256=first_result.receipt.content_sha256,
            page_size=len(_STOCK_CODES),
        )
        bookmark = create_daily_market_technical_universe_v4_bookmark(
            query,
            "2382",
            scroll_position=37,
            comparison_selections=((query, "2382"), (query, "9999")),
        )

        newer_result = produce_daily_market_technical_universe_v4(
            DailyMarketTechnicalUniverseV4ProductionRequest(
                source_database=database,
                cohort=cohort,
                decision_cutoff=datetime(2026, 10, 6, 16, 1, tzinfo=_TAIPEI),
                store_output_root=store_root,
                research_scope=scope,
            )
        )
        assert newer_result.status == "complete", newer_result.to_dict()
        assert newer_result.plan is not None
        assert newer_result.receipt is not None
        assert (
            newer_result.plan.generation_identity_sha256
            != first_result.plan.generation_identity_sha256
        )
        assert newer_result.receipt.identity_sha256 != first_result.receipt.identity_sha256

        # 後續重開只能依保存的 pins，不能因新 generation 出現就改用它。
        database.unlink()
        selected = read_daily_market_technical_universe_v4_stock(query, "2382")
        parent = selected.parent_reference
        package = read_daily_market_technical_parent_capture_v4(
            parent.parent_root,
            parent.parent_plan_identity_sha256,
            parent.parent_receipt_identity_sha256,
            expected_plan_sha256=parent.parent_plan_sha256,
            expected_receipt_sha256=parent.parent_receipt_sha256,
        )
        child = package["receipt"]["batch_artifacts"][0]
        manifest_path = Path(to_internal_io_path(child["manifest_path"]))
        yield {
            "root": root,
            "database": database,
            "query": query,
            "bookmark": bookmark,
            "newer_result": newer_result,
            "original_result": first_result,
            "manifest_path": manifest_path,
            "manifest_bytes": manifest_path.read_bytes(),
        }
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _canonical_hash(payload: dict[str, Any]) -> str:
    body = {key: value for key, value in payload.items() if key != "bookmark_identity_sha256"}
    encoded = json.dumps(
        body,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def test_bookmark_roundtrip_preserves_exact_old_generation_after_database_removal(
    pinned_bookmark: dict[str, Any],
    tmp_path: Path,
) -> None:
    fixture = pinned_bookmark
    bookmark: DailyMarketTechnicalUniverseV4Bookmark = fixture["bookmark"]
    query: DailyMarketTechnicalUniverseV4Query = fixture["query"]
    reopened = DailyMarketTechnicalUniverseV4Bookmark.from_json(bookmark.to_json())
    assert reopened == bookmark
    assert bookmark.bookmark_id == bookmark.identity_sha256
    assert bookmark.source_id == bookmark.bookmark_id
    assert bookmark.source == DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_SOURCE
    assert bookmark.stock_code == "2382"
    assert bookmark.stock_name == ""
    assert bookmark.scroll_position == 37
    assert fixture["database"].exists() is False

    state = read_daily_market_technical_universe_v4_bookmark(bookmark.to_json())
    assert state.bookmark == bookmark
    assert state.origin_page.query == query
    assert state.origin_page.query.generation_identity_sha256 == (
        fixture["original_result"].plan.generation_identity_sha256
    )
    assert state.origin_page.query.generation_identity_sha256 != (
        fixture["newer_result"].plan.generation_identity_sha256
    )
    assert state.selected_stock.snapshot.stock_code == "2382"
    assert state.selected_stock.snapshot.snapshot_identity_sha256 == (
        bookmark.selected_snapshot_identity_sha256
    )
    assert state.selected_stock.snapshot.source_identity == bookmark.selected_source_identity
    assert state.comparison is not None
    assert tuple(column.row.stock_code for column in state.comparison.columns) == (
        "2382",
        "9999",
    )

    saved_file = tmp_path / "technical-universe-bookmark.json"
    saved_file.write_text(bookmark.to_json(), encoding="utf-8")
    script = (
        "import json,sys; from pathlib import Path; "
        "from app_module.daily_market_technical_universe_v4_bookmark import "
        "read_daily_market_technical_universe_v4_bookmark as read; "
        "s=read(Path(sys.argv[1]).read_text(encoding='utf-8')); "
        "print(json.dumps({'bookmark_id':s.bookmark.bookmark_id,'query_id':"
        "s.origin_page.query.query_identity_sha256,'generation_id':"
        "s.origin_page.query.generation_identity_sha256,'stock':"
        "s.selected_stock.snapshot.stock_code,'snapshot_id':"
        "s.selected_stock.snapshot.snapshot_identity_sha256,'scroll':"
        "s.bookmark.scroll_position,'comparison_codes':[c.row.stock_code for c in "
        "s.comparison.columns]},sort_keys=True))"
    )
    fresh = subprocess.run(
        [sys.executable, "-c", script, str(saved_file)],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(fresh.stdout)
    assert payload == {
        "bookmark_id": bookmark.bookmark_id,
        "query_id": query.query_identity_sha256,
        "generation_id": query.generation_identity_sha256,
        "stock": "2382",
        "snapshot_id": bookmark.selected_snapshot_identity_sha256,
        "scroll": 37,
        "comparison_codes": ["2382", "9999"],
    }


def test_bookmark_rejects_noncanonical_inner_query_wrong_identity_and_cancel(
    pinned_bookmark: dict[str, Any],
) -> None:
    fixture = pinned_bookmark
    bookmark: DailyMarketTechnicalUniverseV4Bookmark = fixture["bookmark"]
    with pytest.raises(DailyMarketTechnicalUniverseV4BookmarkError) as cancelled:
        read_daily_market_technical_universe_v4_bookmark(
            bookmark,
            cancel_callback=lambda: True,
        )
    assert cancelled.value.code == "technical_universe_v4_bookmark_cancelled"

    wrong_identity = bookmark.to_dict()
    wrong_identity["selected_source_identity"] = "f" * 64
    wrong_identity["bookmark_identity_sha256"] = _canonical_hash(wrong_identity)
    with pytest.raises(DailyMarketTechnicalUniverseV4BookmarkError) as changed:
        read_daily_market_technical_universe_v4_bookmark(wrong_identity)
    assert changed.value.code == "technical_universe_v4_bookmark_selected_stock_pin_mismatch"

    noncanonical = bookmark.to_dict()
    noncanonical["origin_query_json"] = f" {noncanonical['origin_query_json']} "
    noncanonical["bookmark_identity_sha256"] = _canonical_hash(noncanonical)
    with pytest.raises(DailyMarketTechnicalUniverseV4BookmarkError) as query_rejected:
        DailyMarketTechnicalUniverseV4Bookmark.from_dict(noncanonical)
    assert query_rejected.value.code == "technical_universe_v4_bookmark_query_invalid"

    wrong_scroll = bookmark.to_dict()
    wrong_scroll["scroll_position"] = True
    wrong_scroll["bookmark_identity_sha256"] = _canonical_hash(wrong_scroll)
    with pytest.raises(DailyMarketTechnicalUniverseV4BookmarkError) as scroll_rejected:
        DailyMarketTechnicalUniverseV4Bookmark.from_dict(wrong_scroll)
    assert scroll_rejected.value.code == "technical_universe_v4_bookmark_scroll_invalid"


def test_bookmark_rejects_missing_or_tampered_child_bytes_and_bad_comparison_sets(
    pinned_bookmark: dict[str, Any],
) -> None:
    fixture = pinned_bookmark
    bookmark: DailyMarketTechnicalUniverseV4Bookmark = fixture["bookmark"]
    manifest: Path = fixture["manifest_path"]
    original: bytes = fixture["manifest_bytes"]
    try:
        manifest.write_bytes(original + b" ")
        with pytest.raises(DailyMarketTechnicalUniverseV4BookmarkError):
            read_daily_market_technical_universe_v4_bookmark(bookmark)
        manifest.write_bytes(original)

        manifest.unlink()
        with pytest.raises(DailyMarketTechnicalUniverseV4BookmarkError):
            read_daily_market_technical_universe_v4_bookmark(bookmark)
    finally:
        manifest.write_bytes(original)

    query: DailyMarketTechnicalUniverseV4Query = fixture["query"]
    for selections in (
        ((query, "2382"),),
        ((query, "9999"), (query, "9999")),
    ):
        with pytest.raises(DailyMarketTechnicalUniverseV4BookmarkError):
            create_daily_market_technical_universe_v4_bookmark(
                query,
                "2382",
                scroll_position=0,
                comparison_selections=selections,
            )
