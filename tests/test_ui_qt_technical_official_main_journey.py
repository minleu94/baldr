"""真MainWindow串官方對照來源、跨頁比較、收藏與觀察清單原版本重開。"""
import os
import json
import socket
import tempfile
import time
from pathlib import Path
from typing import Any, cast

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication, QTextEdit

from ui_qt.main import MainWindow, _drain_qt_deferred_deletes
from ui_qt.views.watchlist_view import WatchlistView
from test_daily_market_technical_official_disposition_bundle_v1 import bundle_fixture  # type: ignore[import-not-found]


# 與既有 Main 隔離旅程一致；本測試明確固定所有本機輸出與來源。
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

def _configure_isolated_environment(
    tmp_path: Path,
    market_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:

    output_root = tmp_path / "output"
    state_root = tmp_path / "research-state"
    h20_sqlite_read_root = tmp_path / "personal-h20-sqlite-read"
    temp_root = tmp_path / "temporary"
    local_root = tmp_path / "localapp"
    roaming_root = tmp_path / "appdata"
    active_ml_root = tmp_path / "ml-research-output"
    temp_root.mkdir(parents=True, exist_ok=True)
    h20_sqlite_read_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(tempfile, "tempdir", str(temp_root))

    environment_keys = set(_ISOLATED_ENVIRONMENT_KEYS)
    environment_keys.update(("PHASE3C_CANDIDATE_DB_PATH", "TECHNICAL_OFFICIAL_DISPOSITION_READ_ROOT"))
    for key in environment_keys:
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("DATA_ROOT", str(market_root))
    monkeypatch.setenv("OUTPUT_ROOT", str(output_root))
    monkeypatch.setenv("RESEARCH_STATE_ROOT", str(state_root))
    monkeypatch.setenv("TEMP", str(temp_root))
    monkeypatch.setenv("TMP", str(temp_root))
    monkeypatch.setenv("LOCALAPPDATA", str(local_root))
    monkeypatch.setenv("APPDATA", str(roaming_root))
    monkeypatch.setenv("BALDR_CONFIG", str(tmp_path / "baldr-config.json"))
    monkeypatch.setenv("PROFILE", "prod")
    monkeypatch.setenv("PERSONAL_MODEL_POLICY_PATH", str(state_root / "personal-use-policy.json"))
    monkeypatch.setenv("PHASE3C_CANDIDATE_DB_PATH", str(tmp_path / "candidate" / "candidate.sqlite"))
    monkeypatch.setenv("OFFICIAL_CALENDAR_CACHE_PATH", str(market_root / "calendar-cache.json"))
    monkeypatch.setenv("MPLCONFIGDIR", str(output_root / "application_state" / "matplotlib"))
    monkeypatch.setenv("RECOMMENDATION_LEARNING_OUTPUT_ROOT", str(state_root / "recommendation-learning"))
    monkeypatch.setenv("PERSONAL_H20_SQLITE_READ_ROOT", str(h20_sqlite_read_root))

    storage_config = tmp_path / "ml-research-storage.json"
    storage_config.write_text(
        json.dumps(
            {
                "schema_version": "ml-research-storage.v1",
                "active_root": str(active_ml_root),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BALDR_ML_RESEARCH_STORAGE_CONFIG", str(storage_config))
    return output_root, temp_root

def _install_network_deny(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    attempts: list[str] = []

    def deny(*_args: object, **_kwargs: object) -> None:
        attempts.append("socket connection attempted")
        raise AssertionError("synthetic MainWindow H20 journey must not use provider network")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    return attempts

def _wait_for(app: QApplication, predicate: Any, *, timeout_seconds: float = 90.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    app.processEvents()
    assert predicate(), "真 MainWindow H20 保存來源旅程逾時"

def _close_mainwindow(app: QApplication, window: MainWindow) -> None:
    try:
        if window.isVisible():
            window.close()
            _wait_for(app, lambda: not window.isVisible(), timeout_seconds=45.0)
        _drain_qt_deferred_deletes(app, (window,))
    except RuntimeError:
        pass


def test_actual_main_official_source_compare_save_and_watchlist_restore(bundle_fixture: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    market = tmp_path / "market"
    market.mkdir()
    _configure_isolated_environment(tmp_path, market, monkeypatch)
    monkeypatch.setenv("TECHNICAL_OFFICIAL_DISPOSITION_READ_ROOT", str(bundle_fixture.bundle_root))
    network_attempts = _install_network_deny(monkeypatch)
    app = cast(QApplication, QApplication.instance() or QApplication([]))
    window = MainWindow()
    try:
        window.show()
        app.processEvents()
        view = window.technical_official_research_view
        tabs = window.recommendation_view.result_source_tabs
        window.left_navigation.button_for_key("recommendation").click()
        tabs.setCurrentWidget(view)
        assert tabs.currentWidget() is view
        view.refresh_catalog_button.click()
        _wait_for(app, lambda: view.active_worker is None)
        assert len(view._catalog_entries) == 1
        view.catalog_list.setCurrentRow(0)
        _wait_for(app, lambda: view.active_worker is None)
        assert view.current_result.counts.population.declared_count == 258
        view.results_table.setCurrentCell(0, 0)
        first_code = view.current_page.rows[0].stock_code
        assert view._selected_row is not None and view._selected_row.stock_code == first_code
        view.add_comparison_button.click()
        assert tuple(item.stock_code for item in view.comparison_basket) == (first_code,), view.status_label.text()
        view.next_page_button.click()
        _wait_for(app, lambda: view.active_worker is None)
        view.results_table.setCurrentCell(0, 0)
        selected_code = view.current_page.rows[0].stock_code
        assert view._selected_row is not None and view._selected_row.stock_code == selected_code
        view.add_comparison_button.click()
        assert first_code != selected_code
        assert tuple(item.stock_code for item in view.comparison_basket) == (first_code, selected_code), view.status_label.text()
        assert view.compare_button.isEnabled()
        view.compare_button.click()
        _wait_for(app, lambda: view.active_worker is None)
        comparison = window._technical_official_comparison_dialog
        assert comparison.isVisible()
        assert len(comparison.findChildren(QTextEdit)) == 2
        assert all(text.toPlainText() for text in comparison.findChildren(QTextEdit))
        comparison.close()
        query_id = view.current_result.query.query_identity_sha256
        page_index = view.current_page.page_index
        view.detail_button.click()
        assert selected_code in view.detail_text.text()
        view.back_button.click()
        assert view.current_page.page_index == page_index
        view.bookmark_button.click()
        _wait_for(app, lambda: not getattr(window, "_technical_official_bookmark_workers", set()))
        watchlist = window.watchlist_view
        assert isinstance(watchlist, WatchlistView)
        watchlist._load_watchlist()
        assert watchlist.stocks_model is not None
        frame = watchlist.stocks_model.getDataFrame()
        positions = [index for index in range(len(frame)) if frame.iloc[index].get("source") == "technical_official_disposition_research_bookmark"]
        assert len(positions) == 1
        watchlist.stocks_table.selectRow(positions[0])
        watchlist.stock_analysis_btn.click()
        _wait_for(app, lambda: view.active_worker is None)
        assert tabs.currentWidget() is view
        assert view.current_result.query.query_identity_sha256 == query_id
        assert view.current_page.page_index == page_index
        assert view._selected_row.stock_code == selected_code
        assert len(view.comparison_basket) == 2
        assert not network_attempts
    finally:
        _close_mainwindow(app, window)
