"""原研究頁的每日來源、單一 owner-thread 與固定版本收藏旅程。"""
from __future__ import annotations

from pathlib import Path
from threading import get_ident
import time
from types import SimpleNamespace
from typing import Any, Callable, cast

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QScrollArea, QSplitter, QTabWidget, QWidget

from app_module.daily_market_technical_official_disposition_revenue_bookmark_v2 import DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2
from app_module.daily_market_research_bookmark import DailyMarketResearchBookmarkError
from app_module.watchlist_service import WatchlistService
from ui_qt.views.daily_market_technical_official_disposition_revenue_view import DailyMarketTechnicalOfficialDispositionRevenueView, DailyRevenueSourceConfigV2
from ui_qt.views.watchlist_view import WatchlistView
from ui_qt.views.unified_screener_workspace import UnifiedScreenerWorkspace
from tests.test_daily_market_technical_official_disposition_revenue_query_v2 import _daily_f17_environment

pytest_plugins = ("test_daily_market_technical_official_disposition_bundle_v1",)


def _wait(app: QApplication, predicate: Callable[[], bool], seconds: int = 90) -> None:
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()
    assert predicate()


def test_original_view_daily_actor_pages_bookmark_exact_reopen_and_shutdown(
    bundle_fixture: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = cast(QApplication, QApplication.instance() or QApplication([]))
    provider, reader, pin, _readers, _roots = _daily_f17_environment(tmp_path / "daily")
    # 刻意使用 readerless lazy base，重查與收藏須重新配對 exact reader port。
    from data_module.recommendation_current_fundamental_provider import RecommendationCurrentFundamentalProvider
    base_provider = RecommendationCurrentFundamentalProvider(
        db_file=provider.db_file, output_root=provider.output_root,
        monthly_source_root=provider.monthly_source_root,
        calendar_cache_path=provider.calendar_cache_path,
        temporary_closure_path=provider.temporary_closure_path,
    )
    factory_threads: list[int] = []
    selection_count = 0
    def select(_cutoff: Any) -> Any:
        nonlocal selection_count
        selection_count += 1
        factory_threads.append(get_ident())
        return reader
    def exact_reader(saved_pin: Any, _cutoff: Any) -> Any:
        assert saved_pin == pin
        factory_threads.append(get_ident())
        return reader
    artifact_root, operations = tmp_path / "artifacts", tmp_path / "operations"
    artifact_root.mkdir()
    operations.mkdir()
    view = DailyMarketTechnicalOfficialDispositionRevenueView(
        bundle_fixture.bundle_root, operation_root_parent=operations, monthly_artifact_root=artifact_root,
        daily_source_config_v2=DailyRevenueSourceConfigV2(base_provider, (Path("F:/Min/Python/Project/FA_Data"),), reader_factory=select, exact_reader_factory=exact_reader),
    )
    route_tabs = QTabWidget()
    route_tabs.addTab(view, "營收條件來源")
    route_scroll = QScrollArea()
    route_scroll.setWidgetResizable(True)
    route_scroll.setWidget(route_tabs)
    route_splitter = QSplitter()
    route_splitter.addWidget(QWidget())
    route_splitter.addWidget(route_scroll)
    route_host = SimpleNamespace(
        result_source_tabs=route_tabs,
        result_scroll=route_scroll,
        main_splitter=route_splitter,
        result_panel=QWidget(),
    )
    route_workspace = UnifiedScreenerWorkspace(route_host)
    assert route_workspace.quick_route_buttons["official_technical_revenue"].isEnabled()
    assert route_workspace.select_recipe("official_technical_revenue")
    assert route_workspace._source_by_key[route_workspace.combo.currentData()].widget is view
    view.page_size_box.setValue(50)
    outcomes: list[tuple[str, bool]] = []
    view.operationSettled.connect(lambda kind, ok: outcomes.append((kind, ok)))
    bookmarks: list[object] = []
    view.bookmarkPrepared.connect(bookmarks.append)
    try:
        view.refresh_catalog()
        _wait(app, lambda: len(outcomes) == 1)
        assert outcomes[-1][1], view.status_label.text()
        _wait(app, view._can_start)
        view.catalog_list.setCurrentRow(0)
        view.open_selected_candidate()
        _wait(app, lambda: len(outcomes) == 2)
        assert outcomes[-1][1], view.status_label.text()
        result = view.current_result
        assert result is not None and result.counts.declared_count == 258
        assert result.counts.visible_count == 258
        assert result.scope == "current_only" and result.availability_status == "unknown"
        assert result.historical_pit_eligible is False
        assert selection_count == 1
        assert view.current_recipe is not None
        assert view.current_recipe.monthly_cohort_sha256 == pin.cohort_sha256
        assert view.select_stock_code("1000")
        view.show_selected_detail()
        assert "22.006875" in view.detail_text.toPlainText()
        assert "PIT" in view.detail_text.toPlainText()
        view.add_selected_to_comparison()
        view.navigate_page(5)
        _wait(app, lambda: len(outcomes) == 3)
        assert outcomes[-1][1], view.status_label.text()
        assert view.current_result is result and view.current_page is not None
        assert view.current_page.page_index == 5 and len(view.comparison_basket) == 1
        second = view.current_page.rows[0].stock_code
        assert view.select_stock_code(second)
        view.add_selected_to_comparison()
        compared: list[object] = []
        view.comparisonReady.connect(compared.append)
        def accept_dialog() -> None:
            for widget in QApplication.topLevelWidgets():
                if isinstance(widget, QDialog):
                    widget.accept()
        closer = QTimer()
        closer.timeout.connect(accept_dialog)
        closer.start(10)
        view.compare_basket()
        _wait(app, lambda: len(outcomes) == 4)
        closer.stop()
        assert outcomes[-1][1] and len(compared[0]) == 2
        # 分頁完成後、actor 提交前取消，不可改掉 UI 與收藏的原頁。
        from app_module.daily_market_technical_official_disposition_revenue_query_v2 import DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV2
        original_page_reader = DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV2.read_page_request
        def cancelled_page(current: Any, request: Any, **kwargs: Any) -> Any:
            issued = original_page_reader(current, request, **kwargs)
            assert view._source_actor_v2 is not None
            view._source_actor_v2.cancel_current()
            return issued
        before = len(outcomes)
        with monkeypatch.context() as cancellation_patch:
            cancellation_patch.setattr(DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV2, "read_page_request", cancelled_page)
            view.navigate_page(4)
            _wait(app, lambda: len(outcomes) == before + 1)
        assert outcomes[-1][1] is False
        assert view.current_page.page_index == 5 and view.current_result is result
        view.prepare_bookmark()
        _wait(app, lambda: len(bookmarks) == 1)
        _wait(app, view._can_start)
        bookmark = bookmarks[0]
        assert type(bookmark) is DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2
        output = tmp_path / "personal-output"
        output.mkdir()
        config = SimpleNamespace(output_root=output, resolve_output_path=lambda *parts: output.joinpath(*parts))
        service = WatchlistService(config)
        assert service.add_research_bookmark(bookmark).status == "added"
        loaded = WatchlistService(config).get_research_bookmark(bookmark.bookmark_id)
        assert type(loaded) is DailyMarketTechnicalOfficialDispositionRevenueBookmarkV2
        assert loaded.to_dict() == bookmark.to_dict()
        with pytest.raises(DailyMarketResearchBookmarkError, match="月營收收藏"):
            service.get_research_bookmark_context(bookmark.bookmark_id)
        row = {"source": loaded.source, "source_id": loaded.bookmark_id, "證券代號": loaded.stock_code, "research_bookmark": loaded.to_dict()}
        assert WatchlistView._decode_revenue_bookmark_row(row).to_dict() == loaded.to_dict()
        before = len(outcomes)
        assert view.restore_bookmark(loaded)
        _wait(app, lambda: len(outcomes) == before + 1)
        assert outcomes[-1][1], view.status_label.text()
        assert selection_count == 1
        assert view.current_result is not result
        assert view.current_page is not None and view.current_page.page_index == 5
        assert view._selected_row is not None and view._selected_row.stock_code == second
        assert view.current_recipe.monthly_cohort_sha256 == pin.cohort_sha256
        before = len(outcomes)
        # 從統一入口進入原條件面板，明示兩個來源條件群組及 UNKNOWN 政策。
        technical_check = view.rule_state_checks[next(iter(view.rule_state_checks))]["match"]
        technical_check.setChecked(True)
        view.ma_state_checks["match"].setChecked(True)
        view.condition_combine_box.setCurrentIndex(view.condition_combine_box.findData("AND"))
        view.unknown_policy_box.setCurrentIndex(view.unknown_policy_box.findData("only"))
        view.apply_filters()
        _wait(app, lambda: len(outcomes) == before + 1)
        assert outcomes[-1][1], view.status_label.text()
        assert view.current_result.query.condition_combine_mode == "AND"
        assert view.current_result.query.unknown_policy == "only"
        assert selection_count == 1 and not view.comparison_basket
        assert len(set(factory_threads)) == 1 and factory_threads[0] != get_ident()
    finally:
        route_workspace._timer.stop()
        view.begin_shutdown()
        _wait(app, lambda: view.begin_shutdown())
        view.close()
        route_splitter.close()
        app.processEvents()
    assert view._source_actor_v2 is not None and not view._source_actor_v2.isRunning()
