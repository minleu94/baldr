"""真 MainWindow 端到端保存、重開完整母體技術研究收藏。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path
import socket
import sqlite3
import tempfile
import threading
import time
from typing import Any, Callable, cast
from zoneinfo import ZoneInfo

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app_module.daily_market_technical_universe_v4_bookmark import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_SOURCE,
    DailyMarketTechnicalUniverseV4Bookmark,
    DailyMarketTechnicalUniverseV4BookmarkState,
)
from app_module.daily_market_technical_universe_v4_producer import (
    DailyMarketTechnicalUniverseV4ProductionRequest,
    DailyMarketTechnicalUniverseV4ProductionResult,
    produce_daily_market_technical_universe_v4,
)
from app_module.daily_market_technical_universe_v4_store import (
    DailyMarketTechnicalUniverseV4Cohort,
)
from app_module.rule_research_sample_capture import ResearchCaptureWriteScope
from ui_qt.main import MainWindow, _drain_qt_deferred_deletes
from ui_qt.views.daily_market_research_view import DailyMarketResearchView
from ui_qt.views.daily_market_technical_universe_v4_view import (
    DailyMarketTechnicalUniverseV4View,
)
from ui_qt.views.watchlist_view import WatchlistView
from ui_qt.widgets.technical_universe_bookmark_controls import (
    DailyMarketTechnicalUniverseV4BookmarkControls,
)


TAIPEI = ZoneInfo("Asia/Taipei")
DECISION_DATE = date(2026, 10, 6)
_ISOLATED_ENVIRONMENT_KEYS = (
    "APPDATA",
    "BALDR_CONFIG",
    "BALDR_ML_RESEARCH_STORAGE_CONFIG",
    "BANKTAIWAN_RECOMMENDATION_LEARNING_OUTPUT_ROOT",
    "DATA_FRESHNESS_STATUS_ARTIFACT",
    "DATA_UPDATE_HISTORY_ARTIFACT",
    "DATA_UPDATE_STATUS_ARTIFACT",
    "EVIDENCE_REHEARSAL_REPORT",
    "FINMIND_TOKEN",
    "FORMAL_DAILY_PORTFOLIO_CLOCK_MANIFEST",
    "FORMAL_DAILY_ROLLING_CALENDAR_BUNDLE",
    "FORMAL_DAILY_RUNTIME_CONFIG",
    "FORMAL_DAILY_RUNTIME_CONFIG_ROOT",
    "FORMAL_DAILY_RUNTIME_ENVIRONMENT_FILE",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "LOCALAPPDATA",
    "MONTHLY_REVENUE_AVAILABILITY_CANDIDATE",
    "MONTHLY_REVENUE_SNAPSHOT_CANDIDATE",
    "OFFICIAL_CALENDAR_CACHE_PATH",
    "PERSONAL_DATA_ROOT",
    "PERSONAL_H20_ACTIVATION_CONFIG",
    "PERSONAL_JOURNAL_MODE",
    "PERSONAL_JOURNAL_ROOT",
    "PERSONAL_MODEL_POLICY_PATH",
    "PERSONAL_STORE_MODE",
    "PERSONAL_STORE_ROOT",
    "PERSONAL_WATCHLIST_SOURCE",
    "PIT_MEMBERSHIP_EXPECTED_CLASSIFICATION_VERSION",
    "PIT_MARKET_SCOPE",
    "PIT_SECTOR_MEMBERSHIP_CLOCK_MANIFEST_PATH",
    "PIT_SECTOR_MEMBERSHIP_PATH",
    "PIT_SECTOR_MEMBERSHIP_RAW_ROOT",
    "PIT_SECTOR_MEMBERSHIP_TAXONOMY_IDENTITY_PATH",
    "PIT_SECTOR_MEMBERSHIP_UNIVERSE_IDENTITY_PATH",
    "PIT_SECTOR_MEMBERSHIP_UNIVERSE_SYMBOLS_PATH",
    "P0_SOURCE_CONTROL_CENTER_AUDIT",
    "P0_SOURCE_CONTROL_CENTER_DECISIONS",
    "P0_SOURCE_CONTROL_CENTER_LICENSE_EVIDENCE",
    "PAPER_EQUAL_WEIGHT_BENCHMARK_PATH",
    "PAPER_TRADE_LEDGER_PATH",
    "PROFILE",
    "PROGRAM_READINESS_ARTIFACT",
    "RULE_CHAMPION_CONTROLLED_STORE_ID",
    "RECOMMENDATION_LEARNING_OUTPUT_ROOT",
    "RESEARCH_CONSOLE_PROJECTION",
    "TPEX_REFRESH_STATUS_ARTIFACT",
    "TEMP",
    "TMP",
    "WEEKLY_EVIDENCE_HISTORY_PROJECTION_PATH",
)


def _wait_for(
    app: QApplication,
    predicate: Any,
    *,
    timeout_seconds: float = 45.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while not predicate():
        app.processEvents()
        if time.monotonic() >= deadline:
            raise AssertionError("完整母體 MainWindow 收藏旅程逾時")
        time.sleep(0.005)
    app.processEvents()


def _window_is_closed(window: MainWindow) -> bool:
    try:
        return not window.isVisible()
    except RuntimeError:
        return True


def _seed_synthetic_daily_prices(database: Path) -> None:
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "CREATE TABLE daily_prices "
            "(日期 TEXT, 證券代號 TEXT, 開盤價 TEXT, 最高價 TEXT, "
            "最低價 TEXT, 收盤價 TEXT, 成交股數 INTEGER)"
        )
        connection.executemany(
            "INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)",
            [
                (
                    (DECISION_DATE - timedelta(days=39 - index)).isoformat(),
                    stock_code,
                    str(100 + index),
                    str(101 + index),
                    str(99 + index),
                    str(100 + index),
                    1000 + index,
                )
                for stock_code in ("2382", "9999")
                for index in range(40)
            ],
        )
    finally:
        connection.close()


def _create_real_full_n_store(
    output_root: Path,
    database: Path,
) -> DailyMarketTechnicalUniverseV4ProductionResult:
    """以真 SQLite 來源產製兩檔保存來源，輸出落在 MainWindow 瀏覽根。"""

    capture_scope = ResearchCaptureWriteScope(output_root, database)
    cohort = DailyMarketTechnicalUniverseV4Cohort.create(
        universe_id="synthetic-mainwindow-fulln-journey",
        population_version="fixture-v1",
        decision_date=DECISION_DATE,
        raw_stock_codes=("2382", "9999"),
    )
    store_root = output_root / "research_snapshots" / "technical_universe"
    result = produce_daily_market_technical_universe_v4(
        DailyMarketTechnicalUniverseV4ProductionRequest(
            source_database=database,
            cohort=cohort,
            decision_cutoff=datetime(
                2026, 10, 6, 16, 0, tzinfo=TAIPEI
            ),
            store_output_root=store_root,
            research_scope=capture_scope,
        )
    )
    assert result.status == "complete", result.to_dict()
    assert result.plan is not None
    assert result.receipt is not None
    assert result.plan_sha256 is not None
    return result


def _bookmark_row_number(
    controls: DailyMarketTechnicalUniverseV4BookmarkControls,
    bookmark_id: str,
) -> int:
    for row_number in range(controls.bookmarks.count()):
        item = controls.bookmarks.item(row_number)
        entry = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if getattr(entry, "bookmark_id", None) == bookmark_id:
            return row_number
    raise AssertionError("剛保存的完整母體收藏未出現在 Watchlist 控制項")


def test_actual_mainwindow_fulln_bookmark_save_reopen_and_global_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """全真 MainWindow 路由固定保存 query、選股、比較籃並合作取消。"""

    qa_root = Path.cwd() / "output" / "qa" / "main_fulln_bookmark_journey"
    qa_root.mkdir(parents=True, exist_ok=True)
    fixture_root = Path(
        tempfile.mkdtemp(prefix="run-", dir=str(qa_root))
    ).resolve()
    data_root = fixture_root / "data"
    output_root = fixture_root / "output"
    research_state_root = fixture_root / "research-state"
    temporary_root = fixture_root / "temporary"
    active_ml_research_root = (
        Path(tempfile.gettempdir())
        / "baldr-main-fulln-ml-research"
        / fixture_root.name
    ).resolve()
    application_local_root = fixture_root / "localapp"
    application_roaming_root = fixture_root / "appdata"
    source_database = data_root / "synthetic-market.sqlite"
    store_root = output_root / "research_snapshots" / "technical_universe"
    manifest_path = fixture_root / "journey.json"
    ml_storage_config_path = fixture_root / "ml-research-storage.json"
    temporary_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(tempfile, "tempdir", str(temporary_root))

    for name in _ISOLATED_ENVIRONMENT_KEYS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATA_ROOT", str(data_root))
    monkeypatch.setenv("OUTPUT_ROOT", str(output_root))
    monkeypatch.setenv("RESEARCH_STATE_ROOT", str(research_state_root))
    monkeypatch.setenv("TEMP", str(temporary_root))
    monkeypatch.setenv("TMP", str(temporary_root))
    monkeypatch.setenv(
        "MPLCONFIGDIR",
        str(output_root / "application_state" / "matplotlib"),
    )
    monkeypatch.setenv("LOCALAPPDATA", str(application_local_root))
    monkeypatch.setenv("APPDATA", str(application_roaming_root))
    monkeypatch.setenv("BALDR_CONFIG", str(fixture_root / "baldr-config.json"))
    ml_storage_config_path.write_text(
        json.dumps(
            {
                "schema_version": "ml-research-storage.v1",
                "active_root": str(active_ml_research_root),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(
        "BALDR_ML_RESEARCH_STORAGE_CONFIG", str(ml_storage_config_path)
    )
    monkeypatch.setenv("PROFILE", "prod")
    monkeypatch.setenv(
        "PERSONAL_MODEL_POLICY_PATH",
        str(research_state_root / "personal-use-policy.json"),
    )
    monkeypatch.setenv(
        "PERSONAL_H20_ACTIVATION_CONFIG",
        str(data_root / "personal" / "recommendation_h20" / "activation.json"),
    )
    monkeypatch.setenv(
        "OFFICIAL_CALENDAR_CACHE_PATH",
        str(data_root / "official-calendar-cache.json"),
    )
    monkeypatch.setenv(
        "RECOMMENDATION_LEARNING_OUTPUT_ROOT",
        str(research_state_root / "recommendation-learning"),
    )
    monkeypatch.setenv(
        "BANKTAIWAN_RECOMMENDATION_LEARNING_OUTPUT_ROOT",
        str(research_state_root / "bank-taiwan-recommendation-learning"),
    )

    phase = "isolated_configuration"
    journey_passed = False

    def write_fixture_checkpoint(status: str) -> None:
        payload = {
            "fixture_scope": "synthetic_only_no_formal_private_or_provider_network",
            "status": status,
            "phase": phase,
            "fixture_root": str(fixture_root),
            "data_root": str(data_root),
            "output_root": str(output_root),
            "research_state_root": str(research_state_root),
            "active_ml_research_root": str(active_ml_research_root),
            "ml_storage_config_path": str(ml_storage_config_path),
            "temporary_root": str(temporary_root),
            "source_database": str(source_database),
            "store_root": str(store_root),
        }
        manifest_path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )

    write_fixture_checkpoint("in_progress")

    network_attempts: list[str] = []

    def forbid_network(*_args: object, **_kwargs: object) -> None:
        network_attempts.append("socket connection attempted")
        raise AssertionError("此 synthetic MainWindow journey 不得連接 provider 網路")

    monkeypatch.setattr(socket.socket, "connect", forbid_network)
    monkeypatch.setattr(socket.socket, "connect_ex", forbid_network)
    monkeypatch.setattr(socket, "create_connection", forbid_network)

    _seed_synthetic_daily_prices(source_database)
    output_root.mkdir(parents=True, exist_ok=True)
    phase = "synthetic_source_seeded"
    write_fixture_checkpoint("in_progress")
    result = _create_real_full_n_store(output_root, source_database)
    plan = result.plan
    receipt = result.receipt
    assert plan is not None
    assert receipt is not None
    phase = "full_n_store_produced"
    write_fixture_checkpoint("in_progress")

    app = cast(QApplication, QApplication.instance() or QApplication([]))
    window: MainWindow | None = None
    shutdown_release = threading.Event()
    shutdown_reader_entered = threading.Event()
    shutdown_cancel_observed = threading.Event()
    routed_states: list[object] = []
    bookmark_notifications: list[object] = []
    confirmed_bookmarks: list[DailyMarketTechnicalUniverseV4Bookmark] = []
    manifest: dict[str, object] = {}

    try:
        active_window = MainWindow()
        window = active_window
        assert active_window.config.data_root.resolve() == data_root.resolve()
        assert active_window.config.output_root.resolve() == output_root.resolve()
        assert active_window.application_settings.ml_registry_repository_root.resolve() == (
            research_state_root.resolve()
        )
        assert active_window.stock_research_ml_registry.research_root.resolve() == (
            active_ml_research_root.resolve()
        )
        assert active_window.config.personal_data_root is None
        assert active_window.config.personal_watchlist_source is None
        assert active_window.config.personal_journal_root is None
        assert active_window.config.personal_journal_mode is None
        assert active_window.config.personal_store_root is None
        assert active_window.config.personal_store_mode is None
        assert active_window.watchlist_service is not None
        window_watchlist_service = active_window.watchlist_service
        assert window_watchlist_service.default_watchlist_file.resolve().is_relative_to(
            output_root.resolve()
        )
        assert window_watchlist_service.canonical_repository_path.resolve().is_relative_to(
            output_root.resolve()
        )
        assert isinstance(active_window.watchlist_view, WatchlistView)
        active_window.show()
        app.processEvents()
        phase = "full_mainwindow_initialized"
        write_fixture_checkpoint("in_progress")

        active_window.left_navigation.button_for_key("recommendation").click()
        assert active_window.left_navigation.current_key() == "recommendation"
        recommendation = active_window.recommendation_view
        daily = recommendation.daily_market_research_view
        assert isinstance(daily, DailyMarketResearchView)
        recommendation.result_source_tabs.setCurrentWidget(daily)
        assert recommendation.result_source_tabs.currentWidget() is daily

        browser = daily.technical_universe_view
        assert isinstance(browser, DailyMarketTechnicalUniverseV4View)
        assert browser.store_output_root.resolve() == store_root.resolve()
        assert browser.production_request_factory is not None

        browser.refresh_button.click()
        _wait_for(
            app,
            lambda: browser._worker is None and browser.sources.count() == 1,
        )
        selected_source = browser.selected_source
        assert selected_source is not None and selected_source.is_selectable
        browser.load_button.click()
        _wait_for(app, lambda: browser._worker is None and browser.current_page is not None)
        page = browser.current_page
        query = browser.current_query
        assert page is not None and query is not None
        assert page.is_complete
        assert query.decision_date == DECISION_DATE
        assert [row.stock_code for row in page.rows] == ["2382", "9999"]
        phase = "mainwindow_query_loaded"
        write_fixture_checkpoint("in_progress")

        for stock_code in ("2382", "9999"):
            assert browser._select_stock_code(stock_code)
            browser.add_selected_to_comparison()
        assert [item.row.stock_code for item in browser._comparison_basket] == [
            "2382",
            "9999",
        ]
        assert browser._select_stock_code("2382")

        def confirm_bookmark(value: object) -> bool:
            assert isinstance(value, DailyMarketTechnicalUniverseV4Bookmark)
            assert value.origin_query == query
            assert value.selected_stock_code == "2382"
            assert tuple(selection.stock_code for selection in value.comparison_selections) == (
                "2382",
                "9999",
            )
            confirmed_bookmarks.append(value)
            return True

        daily.bookmark_confirmation_callback = confirm_bookmark
        daily.bookmarkSaved.connect(bookmark_notifications.append)
        browser.bookmark_button.click()
        _wait_for(
            app,
            lambda: browser._worker is None and len(confirmed_bookmarks) == 1,
        )
        bookmark = confirmed_bookmarks[0]
        assert browser.current_query == query
        assert len(bookmark_notifications) == 1
        assert getattr(bookmark_notifications[0], "status", None) == "added"
        persisted = window_watchlist_service.get_research_bookmark(bookmark.bookmark_id)
        assert persisted == bookmark
        assert bookmark.source == DAILY_MARKET_TECHNICAL_UNIVERSE_V4_BOOKMARK_SOURCE
        assert len(bookmark.comparison_selections) == 2
        phase = "bookmark_saved_to_isolated_watchlist"
        write_fixture_checkpoint("in_progress")

        watchlist = active_window.watchlist_view
        controls = watchlist.technical_bookmark_controls
        _wait_for(
            app,
            lambda: controls._worker is None
            and controls.bookmarks.count() == 1,
        )
        row_number = _bookmark_row_number(controls, bookmark.bookmark_id)
        controls.bookmarks.setCurrentRow(row_number)
        assert controls.open_button.isEnabled()
        watchlist.technicalBookmarkStateReady.connect(routed_states.append)
        controls.open_button.click()
        _wait_for(
            app,
            lambda: controls._worker is None
            and browser._worker is None
            and browser.current_query == bookmark.origin_query,
        )

        assert len(routed_states) == 1
        restored_state = routed_states[0]
        assert isinstance(restored_state, DailyMarketTechnicalUniverseV4BookmarkState)
        assert restored_state.bookmark == bookmark
        assert active_window.left_navigation.current_key() == "recommendation"
        assert recommendation.result_source_tabs.currentWidget() is daily
        assert browser.current_query == bookmark.origin_query
        selected_restored_row = browser._selected_row()
        assert selected_restored_row is not None
        assert selected_restored_row.stock_code == bookmark.selected_stock_code
        assert [item.row.stock_code for item in browser._comparison_basket] == [
            "2382",
            "9999",
        ]
        assert all(
            item.query == bookmark.origin_query
            for item in browser._comparison_basket
        )
        phase = "typed_bookmark_reopened_and_routed"
        write_fixture_checkpoint("in_progress")

        original_reader = window_watchlist_service.get_technical_universe_research_bookmark_state

        def delayed_real_reader(
            bookmark_id: str,
            watchlist_id: str = "default",
            *,
            cancel_callback: Callable[[], bool] | None = None,
        ) -> DailyMarketTechnicalUniverseV4BookmarkState:
            shutdown_reader_entered.set()
            if not shutdown_release.wait(timeout=20):
                raise AssertionError("全域關閉測試的 reader barrier 未釋放")
            if cancel_callback is not None and cancel_callback():
                shutdown_cancel_observed.set()
            return original_reader(
                bookmark_id,
                watchlist_id,
                cancel_callback=cancel_callback,
            )

        monkeypatch.setattr(
            window_watchlist_service,
            "get_technical_universe_research_bookmark_state",
            delayed_real_reader,
        )
        controls.open_selected()
        assert shutdown_reader_entered.wait(timeout=10)
        assert active_window.close() is False
        app.processEvents()
        assert active_window._shutdown_close_requested
        assert active_window.isVisible()
        assert controls._closing
        shutdown_release.set()
        _wait_for(app, lambda: _window_is_closed(active_window), timeout_seconds=45)
        assert shutdown_cancel_observed.is_set()
        assert controls._worker is None
        assert routed_states == [restored_state]
        phase = "global_shutdown_cancel_completed"

        manifest = {
            "fixture_scope": "synthetic_only_no_formal_private_or_provider_network",
            "fixture_root": str(fixture_root),
            "data_root": str(data_root),
            "output_root": str(output_root),
            "research_state_root": str(research_state_root),
            "active_ml_research_root": str(active_ml_research_root),
            "ml_storage_config_path": str(ml_storage_config_path),
            "source_database": str(source_database),
            "store_root": str(store_root),
            "generation_identity_sha256": plan.generation_identity_sha256,
            "plan_identity_sha256": plan.identity_sha256,
            "plan_sha256": result.plan_sha256,
            "receipt_identity_sha256": receipt.identity_sha256,
            "receipt_sha256": receipt.content_sha256,
            "query_identity_sha256": query.query_identity_sha256,
            "bookmark_identity_sha256": bookmark.bookmark_identity_sha256,
            "selected_stock_code": bookmark.selected_stock_code,
            "comparison_stock_codes": [
                selection.stock_code for selection in bookmark.comparison_selections
            ],
            "shutdown_cancel_observed": shutdown_cancel_observed.is_set(),
            "network_attempts": network_attempts,
        }
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        assert manifest_path.is_file()
        assert network_attempts == []
        journey_passed = True
    finally:
        shutdown_release.set()
        if window is not None:
            if not _window_is_closed(window):
                window.close()
                _wait_for(app, lambda: _window_is_closed(window), timeout_seconds=45)
            _drain_qt_deferred_deletes(app, (window,))
        if not journey_passed:
            write_fixture_checkpoint("incomplete_or_failed")
