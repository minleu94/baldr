"""個股下鑽沿真保存來源重開，原DB移除後仍可核驗。"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import sqlite3
import subprocess
import sys

import pytest

from app_module.daily_market_technical_universe_v4_producer import (
    DailyMarketTechnicalUniverseV4ProductionRequest,
    produce_daily_market_technical_universe_v4,
)
from app_module.daily_market_technical_universe_v4_query import DailyMarketTechnicalUniverseV4Query
from app_module.daily_market_technical_universe_v4_stock import (
    DailyMarketTechnicalUniverseV4StockError,
    read_daily_market_technical_universe_v4_stock,
)
from app_module.daily_market_technical_universe_v4_store import DailyMarketTechnicalUniverseV4Cohort
from app_module.rule_research_sample_capture import ResearchCaptureWriteScope
from app_module.personal_data_paths import to_internal_io_path
from app_module.rule_research_technical_parent_capture_v4 import read_daily_market_technical_parent_capture_v4


def test_saved_stock_reopens_without_database_and_rejects_other_page(tmp_path):
    database = tmp_path / "synthetic.sqlite"
    decision = date(2026, 10, 6)
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE daily_prices (日期 TEXT, 證券代號 TEXT, 開盤價 TEXT, 最高價 TEXT, 最低價 TEXT, 收盤價 TEXT, 成交股數 INTEGER)")
        connection.executemany("INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)", [
            ((decision - timedelta(days=39-i)).isoformat(), code, str(100+i),
             str(101+i), str(99+i), str(100+i), 1000+i)
            for code in ("2382", "9999") for i in range(40)
        ])
    connection.close()
    scope = ResearchCaptureWriteScope(tmp_path / "research", database)
    cohort = DailyMarketTechnicalUniverseV4Cohort.create(
        universe_id="synthetic-stock-drill", population_version="fixture-v1",
        decision_date=decision, raw_stock_codes=("2382", "9999"),
    )
    store = scope.root / "technical_universe"
    result = produce_daily_market_technical_universe_v4(DailyMarketTechnicalUniverseV4ProductionRequest(
        source_database=database, cohort=cohort,
        decision_cutoff=datetime(2026, 10, 6, 16, tzinfo=ZoneInfo("Asia/Taipei")),
        store_output_root=store, research_scope=scope,
    ))
    assert result.status == "complete", result.to_dict()
    assert result.plan is not None and result.receipt is not None
    assert result.plan_sha256 is not None
    query = DailyMarketTechnicalUniverseV4Query.create(
        store_output_root=store, generation_identity_sha256=result.plan.generation_identity_sha256,
        plan_identity_sha256=result.plan.identity_sha256, plan_sha256=result.plan_sha256,
        receipt_identity_sha256=result.receipt.identity_sha256,
        receipt_sha256=result.receipt.content_sha256, page_size=1,
    )
    # 只移除本測試自建DB，證明下鑽不需要行情讀取或重新計算。
    database.unlink()
    from app_module.daily_market_technical_universe_v4_comparison import (
        DailyMarketTechnicalUniverseV4ComparisonError,
        read_daily_market_technical_universe_v4_comparison,
    )
    # 用公開 create 重建完整 pins，避免手改帶有 identity 的保存查詢。
    second_query = DailyMarketTechnicalUniverseV4Query.create(
        store_output_root=store, generation_identity_sha256=result.plan.generation_identity_sha256,
        plan_identity_sha256=result.plan.identity_sha256, plan_sha256=result.plan_sha256,
        receipt_identity_sha256=result.receipt.identity_sha256,
        receipt_sha256=result.receipt.content_sha256, page_size=1, page_index=1,
    )
    comparison = read_daily_market_technical_universe_v4_comparison(
        ((query, "2382"), (second_query, "9999")),
    )
    assert [column.row.stock_code for column in comparison.columns] == ["2382", "9999"]
    assert [column.origin_query for column in comparison.columns] == [query, second_query]
    assert all(len(column.row.rules) == 5 for column in comparison.columns)
    assert not comparison.has_mixed_cutoffs
    assert not comparison.has_mixed_methods
    assert not comparison.has_mixed_source_clocks
    assert comparison.to_dict()["historical_pit_eligible"] is False
    for selections, expected_code in (
        (((query, "2382"), (query, "2382")), "technical_universe_v4_comparison_duplicate_column"),
        (((query, "2382"), (query, "9999")), "technical_universe_v4_comparison_stock_not_in_origin_page"),
    ):
        with pytest.raises(DailyMarketTechnicalUniverseV4ComparisonError) as rejected:
            read_daily_market_technical_universe_v4_comparison(selections)
        assert rejected.value.code == expected_code
    with pytest.raises(DailyMarketTechnicalUniverseV4ComparisonError) as comparison_cancelled:
        read_daily_market_technical_universe_v4_comparison(
            ((query, "2382"), (second_query, "9999")), cancel_callback=lambda: True,
        )
    assert comparison_cancelled.value.code == "technical_universe_v4_comparison_cancelled"
    from types import SimpleNamespace
    from app_module.daily_market_technical_universe_v4_bookmark import create_daily_market_technical_universe_v4_bookmark
    from app_module.watchlist_service import WatchlistService
    from app_module.daily_market_research_bookmark import DailyMarketResearchBookmarkError
    bookmark = create_daily_market_technical_universe_v4_bookmark(
        query, "2382", scroll_position=7,
        comparison_selections=((query, "2382"), (second_query, "9999")),
    )
    watchlist_config = SimpleNamespace(
        output_root=tmp_path / "isolated-watchlist",
        resolve_output_path=lambda relative: tmp_path / "isolated-watchlist" / relative,
    )
    watchlist = WatchlistService(watchlist_config)
    assert watchlist.add_research_bookmark(bookmark).status == "added"
    assert watchlist.add_research_bookmark(bookmark).status == "already_present"
    reopened_watchlist = WatchlistService(watchlist_config)
    assert reopened_watchlist.get_research_bookmark(bookmark.bookmark_id) == bookmark
    restored = reopened_watchlist.get_technical_universe_research_bookmark_state(bookmark.bookmark_id)
    assert restored.bookmark == bookmark
    with pytest.raises(DailyMarketResearchBookmarkError) as old_context:
        reopened_watchlist.get_research_bookmark_context(bookmark.bookmark_id)
    assert old_context.value.code == "technical_universe_bookmark_typed_reopen_required"
    original_watchlist_bytes = reopened_watchlist.default_watchlist_file.read_bytes()
    upgraded = reopened_watchlist.upgrade_to_repository()
    assert upgraded.is_repository
    assert reopened_watchlist.default_watchlist_file.read_bytes() == original_watchlist_bytes
    repository, storage_status = WatchlistService.discover_repository(watchlist_config)
    assert repository is not None
    cow_watchlist = WatchlistService(watchlist_config, repository=repository, storage_status=storage_status)
    assert cow_watchlist.get_research_bookmark(bookmark.bookmark_id) == bookmark
    assert cow_watchlist.add_research_bookmark(bookmark).status == "already_present"
    before_remove_revision = cow_watchlist.get_watchlist().revision
    removed = cow_watchlist.remove_research_bookmark(bookmark.bookmark_id)
    assert removed.status == "removed"
    assert removed.restore_token is not None
    assert cow_watchlist.get_research_bookmark(bookmark.bookmark_id) is None
    assert cow_watchlist.restore_research_bookmark(removed.restore_token).status == "restored"
    restored_revision = cow_watchlist.get_watchlist().revision
    assert restored_revision > before_remove_revision
    assert cow_watchlist.restore_research_bookmark(removed.restore_token).status == "already_present"
    assert cow_watchlist.get_watchlist().revision == restored_revision
    assert cow_watchlist.get_research_bookmark(bookmark.bookmark_id) == bookmark
    bookmark_script = (
        "import sys; from pathlib import Path; from types import SimpleNamespace; "
        "from app_module.watchlist_service import WatchlistService; "
        "root=Path(sys.argv[1]); c=SimpleNamespace(output_root=root,resolve_output_path=lambda name:root/name); "
        "repo,status=WatchlistService.discover_repository(c); assert repo is not None; "
        "w=WatchlistService(c,repository=repo,storage_status=status); "
        "s=w.get_technical_universe_research_bookmark_state(sys.argv[2]); "
        "print(s.bookmark.bookmark_id); print(s.bookmark.origin_query.query_identity_sha256)"
    )
    fresh_bookmark = subprocess.run(
        [sys.executable, "-c", bookmark_script, str(watchlist_config.output_root), bookmark.bookmark_id],
        capture_output=True, text=True, check=True,
    )
    assert fresh_bookmark.stdout.splitlines() == [bookmark.bookmark_id, query.query_identity_sha256]
    stock = read_daily_market_technical_universe_v4_stock(query, "2382")
    assert stock.origin_query == query
    assert stock.snapshot.stock_code == "2382"
    assert stock.snapshot.decision_date == decision
    assert len(stock.snapshot.rows) == 40
    assert len(stock.snapshot.rules) == 5
    assert stock.segment_index == 0
    query_file = tmp_path / "origin-query.json"
    query_file.write_text(query.to_json(), encoding="utf-8")
    script = (
        "import sys; from pathlib import Path; "
        "from app_module.daily_market_technical_universe_v4_query import DailyMarketTechnicalUniverseV4Query as Q; "
        "from app_module.daily_market_technical_universe_v4_stock import read_daily_market_technical_universe_v4_stock as read; "
        "q=Q.from_json(Path(sys.argv[1]).read_text(encoding='utf-8')); "
        "s=read(q,'2382'); print(s.snapshot.snapshot_identity_sha256); print(s.origin_query.query_identity_sha256)"
    )
    reopened = subprocess.run([sys.executable, "-c", script, str(query_file)],
                              capture_output=True, text=True, check=True)
    assert reopened.stdout.splitlines() == [stock.snapshot.snapshot_identity_sha256, query.query_identity_sha256]
    with pytest.raises(DailyMarketTechnicalUniverseV4StockError) as wrong_page:
        read_daily_market_technical_universe_v4_stock(query, "9999")
    assert wrong_page.value.code == "technical_universe_v4_stock_not_in_origin_page"
    with pytest.raises(DailyMarketTechnicalUniverseV4StockError) as cancelled:
        read_daily_market_technical_universe_v4_stock(query, "2382", cancel_callback=lambda: True)
    assert cancelled.value.code == "technical_universe_v4_stock_cancelled"
    reference = stock.parent_reference
    package = read_daily_market_technical_parent_capture_v4(
        reference.parent_root, reference.parent_plan_identity_sha256,
        reference.parent_receipt_identity_sha256,
        expected_plan_sha256=reference.parent_plan_sha256,
        expected_receipt_sha256=reference.parent_receipt_sha256,
    )
    from pathlib import Path
    manifest = Path(to_internal_io_path(package["receipt"]["batch_artifacts"][0]["manifest_path"]))
    original = manifest.read_bytes()
    try:
        manifest.write_bytes(original + b" ")
        with pytest.raises(ValueError):
            read_daily_market_technical_universe_v4_stock(query, "2382")
        with pytest.raises(ValueError):
            read_daily_market_technical_universe_v4_comparison(((query, "2382"), (second_query, "9999")))
        manifest.unlink()
        with pytest.raises(ValueError):
            read_daily_market_technical_universe_v4_stock(query, "2382")
    finally:
        manifest.write_bytes(original)
    assert read_daily_market_technical_universe_v4_stock(query, "2382").snapshot == stock.snapshot
    from PySide6.QtWidgets import QApplication
    from ui_qt.views.daily_market_technical_stock_v4_view import DailyMarketTechnicalStockV4View
    app = QApplication.instance() or QApplication([])
    from ui_qt.views.daily_market_technical_comparison_v4_view import DailyMarketTechnicalComparisonV4View
    comparison_view = DailyMarketTechnicalComparisonV4View()
    origins = []
    comparison_view.originRequested.connect(origins.append)
    comparison_view.show_comparison(comparison)
    assert comparison_view.table.columnCount() == 2
    assert comparison_view.table.horizontalHeaderItem(1).text() == "9999"
    assert "資料可得時間未知" in comparison_view.summary.text()
    assert "16:00:00" in comparison_view.table.item(1, 1).text()
    assert comparison_view.table.item(3, 1).text() == "40"
    comparison_view.table.setCurrentCell(4, 1)
    assert "支持依據" in comparison_view.evidence.toPlainText()
    assert "決策截止" in comparison_view.evidence.toPlainText()
    comparison_view.table.setCurrentCell(0, 1)
    comparison_view.return_button.click()
    assert origins == [(second_query, "9999")]
    comparison_view.close()
    view = DailyMarketTechnicalStockV4View()
    returned = []
    view.returnRequested.connect(returned.append)
    view.show_stock(stock)
    view.resize(800, 600)
    view.show()
    app.processEvents()
    assert "2382" in view.summary.text()
    assert "2026-10-06" in view.summary.text()
    assert "歷史可交易" in view.summary.text()
    assert "20 日均量比（含當日）" in view.evidence.toPlainText()
    assert "5 日均量比（含當日）" in view.evidence.toPlainText()
    assert view.return_button.isEnabled()
    view.return_button.click()
    assert returned == [query]
    view.close()
    from types import SimpleNamespace
    from ui_qt.views.daily_market_research_view import DailyMarketResearchView
    from app_module.daily_market_technical_universe_v4_query import read_daily_market_technical_universe_v4_page
    # 服務設定外殼只提供隔離根；資料仍取自上方真producer／store／query。
    daily = DailyMarketResearchView(
        SimpleNamespace(config=SimpleNamespace(output_root=scope.configured_output_root)),
        watchlist_service=cow_watchlist, bookmark_confirmation_callback=lambda value: True,
    )
    browser = daily.technical_universe_view
    assert browser is not None
    assert browser.store_output_root == store
    page = read_daily_market_technical_universe_v4_page(query)
    browser._show_page(page)
    browser.table.selectRow(0)
    saved_notifications = []
    daily.bookmarkSaved.connect(saved_notifications.append)
    browser.bookmarkPrepared.emit(bookmark)
    assert len(saved_notifications) == 1
    assert saved_notifications[0].status == "already_present"
    daily.bookmark_confirmation_callback = lambda value: False
    browser.bookmarkPrepared.emit(bookmark)
    assert len(saved_notifications) == 1
    daily.bookmark_confirmation_callback = lambda value: True
    import time
    prepared_notifications = []
    browser.bookmarkPrepared.connect(prepared_notifications.append)
    browser.bookmark_button.click()
    deadline = time.monotonic() + 30
    while browser._worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert len(prepared_notifications) == 1
    button_bookmark = prepared_notifications[0]
    assert button_bookmark.origin_query == query
    assert button_bookmark.stock_code == "2382"
    assert len(saved_notifications) == 2
    assert saved_notifications[-1].status == "added"
    button_state = cow_watchlist.get_technical_universe_research_bookmark_state(button_bookmark.bookmark_id)
    assert button_state.bookmark == button_bookmark
    browser.stockSelected.emit((query, page.rows[0], stock))
    dialog = daily._technical_stock_dialog
    assert dialog is not None
    details = dialog.findChild(DailyMarketTechnicalStockV4View)
    assert details is not None
    assert "2382" in details.summary.text()
    details.return_button.click()
    app.processEvents()
    assert browser.current_query == query
    assert browser.table.currentIndex().data() == "2382"
    browser.comparisonReady.emit(comparison)
    comparison_dialog = daily._technical_comparison_dialog
    assert comparison_dialog is not None
    comparison_details = comparison_dialog.findChild(DailyMarketTechnicalComparisonV4View)
    assert comparison_details is not None
    assert comparison_details.table.columnCount() == 2
    comparison_details.table.setCurrentCell(0, 1)
    comparison_details.return_button.click()
    import time
    deadline = time.monotonic() + 30
    while browser.current_query != second_query and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert browser.current_query == second_query
    assert browser.table.currentIndex().data() == "9999"
    while browser._worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    from ui_qt.main import MainWindow
    from PySide6.QtWidgets import QTabWidget
    source_tabs = QTabWidget()
    source_tabs.addTab(daily, "每日研究")
    navigated = []
    route_host = SimpleNamespace(
        recommendation_view=SimpleNamespace(
            daily_market_research_view=daily, result_source_tabs=source_tabs,
        ),
        _select_main_workspace=navigated.append,
    )
    MainWindow._open_technical_bookmark_state(route_host, restored)
    deadline = time.monotonic() + 30
    while browser._worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert navigated == ["recommendation"]
    assert source_tabs.currentWidget() is daily
    assert browser.current_query == query
    assert browser.table.currentIndex().data() == "2382"
    assert len(browser._comparison_basket) == 2
    from ui_qt.views.watchlist_view import WatchlistView
    from PySide6.QtCore import Qt
    watchlist_view = WatchlistView(cow_watchlist)
    controls = watchlist_view.technical_bookmark_controls
    watchlist_view.technicalBookmarkStateReady.connect(
        lambda state: MainWindow._open_technical_bookmark_state(route_host, state)
    )
    deadline = time.monotonic() + 30
    while controls._worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    for index in range(controls.bookmarks.count()):
        item = controls.bookmarks.item(index)
        if item.data(Qt.ItemDataRole.UserRole).bookmark_id == bookmark.bookmark_id:
            controls.bookmarks.setCurrentRow(index)
            break
    else:
        raise AssertionError("保存的原比較收藏未列在觀察清單")
    controls.open_button.click()
    deadline = time.monotonic() + 30
    while (controls._worker is not None or browser._worker is not None) and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert navigated == ["recommendation", "recommendation"]
    assert browser.current_query == query
    assert browser.table.currentIndex().data() == "2382"
    assert len(browser._comparison_basket) == 2
    route_host.watchlist_view = watchlist_view
    route_host._record_shutdown_message = lambda message: None
    MainWindow._freeze_child_refresh_sources(route_host)
    assert watchlist_view._shutdown_started
    assert controls._closing
    assert watchlist_view.begin_shutdown()
    watchlist_view.close()
    daily.begin_shutdown()
    daily.close()
