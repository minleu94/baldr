"""原 F17 頁面以同 owner actor 保存原件，來源漂移後精確重開收藏。"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import sqlite3
from threading import get_ident
from typing import Any, cast

import pytest
from PySide6.QtWidgets import QApplication

from app_module.daily_market_monthly_revenue_archive_reference_artifact_v4 import (
    read_daily_market_monthly_revenue_archive_reference_artifact_v4,
)
from app_module.daily_market_technical_official_disposition_revenue_archived_bookmark_v3 import (
    DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3,
)
from app_module.daily_market_technical_official_disposition_revenue_archived_recipe_v3 import (
    DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3,
)
from app_module.watchlist_service import WatchlistService
from data_module.daily_market_monthly_revenue_cohort_v2 import (
    decode_daily_market_monthly_revenue_source_reference_v3,
)
from data_module.recommendation_current_fundamental_provider import RecommendationCurrentFundamentalProvider
from tests.test_daily_market_technical_official_disposition_revenue_query_v2 import _daily_f17_environment
from tests.test_ui_qt_daily_market_technical_official_disposition_revenue_view_v2 import _wait
from tests.test_watchlist_revenue_archived_bookmark_v3 import _config
from ui_qt.views.daily_market_technical_official_disposition_revenue_view import (
    DailyMarketTechnicalOfficialDispositionRevenueView, DailyRevenueSourceConfigV2,
)

pytest_plugins = ("test_daily_market_technical_official_disposition_bundle_v1",)


def _pins(paths: tuple[Path, ...]) -> dict[str, tuple[str, int, int]]:
    return {str(path): (sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns, path.stat().st_ino) for path in paths}


def test_original_view_archived_bookmark_reopens_after_mutable_sources_and_original_artifacts_drift(
    bundle_fixture: Any, tmp_path: Path,
) -> None:
    app = cast(QApplication, QApplication.instance() or QApplication([]))
    provider, reader, pin, _market_readers, market_roots = _daily_f17_environment(tmp_path / "daily")
    base_provider = RecommendationCurrentFundamentalProvider(
        db_file=provider.db_file, output_root=provider.output_root,
        monthly_source_root=provider.monthly_source_root,
        calendar_cache_path=provider.calendar_cache_path,
        temporary_closure_path=provider.temporary_closure_path,
    )
    selection_calls: list[int] = []
    exact_calls: list[int] = []
    def select(_cutoff: Any) -> Any:
        selection_calls.append(get_ident())
        return reader
    def exact_reader(saved_pin: Any, _cutoff: Any) -> Any:
        assert saved_pin == pin
        exact_calls.append(get_ident())
        return reader
    research, operations = tmp_path / "research", tmp_path / "operations"
    research.mkdir(); operations.mkdir()
    config = DailyRevenueSourceConfigV2(
        base_provider, (Path("F:/Min/Python/Project/FA_Data"),),
        reader_factory=select, exact_reader_factory=exact_reader,
        use_archived_sources=True, source_roots=tuple(market_roots.values()),
    )
    view = DailyMarketTechnicalOfficialDispositionRevenueView(
        bundle_fixture.bundle_root, operation_root_parent=operations,
        monthly_artifact_root=research, daily_source_config_v2=config,
    )
    outcomes: list[tuple[str, bool]] = []
    view.operationSettled.connect(lambda kind, ok: outcomes.append((kind, ok)))
    bookmarks: list[object] = []
    view.bookmarkPrepared.connect(bookmarks.append)
    try:
        view.page_size_box.setValue(8)
        view.refresh_catalog(); _wait(app, lambda: len(outcomes) == 1)
        assert outcomes[-1][1], view.status_label.text()
        _wait(app, view._can_start)
        view.catalog_list.setCurrentRow(0); view.open_selected_candidate()
        _wait(app, lambda: len(outcomes) == 2)
        assert outcomes[-1][1], view.status_label.text()
        result = view.current_result
        recipe = view.current_recipe
        assert result is not None and result.counts.declared_count == result.counts.visible_count == 258
        assert type(recipe) is DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3
        assert result.scope == "current_only" and result.availability_status == "unknown"
        assert result.historical_pit_eligible is False and selection_calls == [selection_calls[0]]
        assert selection_calls[0] != get_ident()
        assert view.select_stock_code("1000")
        view.show_selected_detail(); assert "22.006875" in view.detail_text.toPlainText()
        view.add_selected_to_comparison()
        view.navigate_page(1); _wait(app, lambda: len(outcomes) == 3)
        assert outcomes[-1][1] and view.current_result is result
        page = view.current_page
        assert page is not None and page.page_index == 1
        selected = page.rows[0].stock_code
        assert view.select_stock_code(selected)
        view.prepare_bookmark(); _wait(app, lambda: len(outcomes) == 4)
        assert outcomes[-1][1] and len(bookmarks) == 1
        bookmark = bookmarks[0]
        assert type(bookmark) is DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3
        assert bookmark.saved_recipe.base_recipe.page_index == 1
        assert bookmark.stock_code == selected and len(view.comparison_basket) == 1
        service = WatchlistService(_config(tmp_path / "watchlist-output"))
        service.add_research_bookmark(bookmark)
        loaded = service.get_research_bookmark(bookmark.bookmark_id)
        assert type(loaded) is DailyMarketTechnicalOfficialDispositionRevenueArchivedBookmarkV3
        assert loaded.to_dict() == bookmark.to_dict()
        recipe = loaded.saved_recipe
        original = decode_daily_market_monthly_revenue_source_reference_v3(
            recipe.base_recipe.monthly_source_reference_json,
            expected_reference_sha256=loaded.original_monthly_source_reference_external_sha256,
        ).reference
        archive = read_daily_market_monthly_revenue_archive_reference_artifact_v4(
            research / "archive-references.v4", descriptor=recipe.archive_artifact_descriptor,
            expected_descriptor_sha256=loaded.archive_artifact_descriptor_external_sha256,
            protected_roots=config.protected_roots,
        ).raw_archive_reference.reference
        paths = tuple(sorted(path for root in (Path(archive.archive_root), research / "archive-references.v4", *market_roots.values()) for path in root.rglob("*") if path.is_file()))
        saved_pins = _pins(paths)
        original_snapshot = Path(original.upstream_reference.snapshot_root)
        assert original_snapshot.resolve().is_relative_to(operations.resolve())
    finally:
        view.begin_shutdown(); _wait(app, lambda: view.begin_shutdown())
        view.close(); app.processEvents()
    assert view._source_actor_v2 is not None and not view._source_actor_v2.isRunning()
    with sqlite3.connect(provider.db_file) as connection:
        changed = connection.execute("UPDATE fundamental_current_observations SET value=? WHERE stock_code=? AND kind='monthly_revenue' AND item_code='revenue'", ("999999999999", "1000"))
        assert changed.rowcount >= 1
    for item in archive.files:
        path = Path(item.historical_pin.path)
        assert path.resolve().is_relative_to(tmp_path.resolve())
        path.write_bytes(path.read_bytes() + b"\nprivate-revision\n")
    original_snapshot.rename(tmp_path / "preserved-original-snapshot")
    (research / "monthly-references.v3").rename(tmp_path / "preserved-original-references")
    reopened_view = DailyMarketTechnicalOfficialDispositionRevenueView(
        bundle_fixture.bundle_root, operation_root_parent=operations,
        monthly_artifact_root=research, daily_source_config_v2=config,
    )
    reopened: list[tuple[str, bool]] = []
    reopened_view.operationSettled.connect(lambda kind, ok: reopened.append((kind, ok)))
    try:
        assert reopened_view.restore_bookmark(loaded)
        _wait(app, lambda: len(reopened) == 1)
        assert reopened[-1][1], reopened_view.status_label.text()
        new_result, new_recipe, new_page = reopened_view.current_result, reopened_view.current_recipe, reopened_view.current_page
        assert new_result is not None and new_result.counts.declared_count == 258
        assert type(new_recipe) is DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3
        assert new_recipe.to_json() == recipe.to_json()
        assert new_page is not None and new_page.page_index == 1
        assert [row.stock_code for row in new_page.rows] == [row.stock_code for row in page.rows]
        assert reopened_view._selected_row is not None and reopened_view._selected_row.stock_code == selected
        assert len(selection_calls) == len(exact_calls) == 1
        assert exact_calls[0] != get_ident()
        assert _pins(paths) == saved_pins
        assert not original_snapshot.exists()
        assert service.get_research_bookmark(loaded.bookmark_id).to_dict() == loaded.to_dict()
    finally:
        reopened_view.begin_shutdown(); _wait(app, lambda: reopened_view.begin_shutdown())
        reopened_view.close(); app.processEvents()
    assert reopened_view._source_actor_v2 is not None and not reopened_view._source_actor_v2.isRunning()
