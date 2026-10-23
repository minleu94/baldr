"""主窗口缺少產業指數資料時仍可在隔離環境啟動。"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import time
from typing import cast

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app_module.build_identity import BuildIdentity
from ui_qt.main_window_coordinator import PRIMARY_NAVIGATION, PRODUCT_ROUTES
from ui_qt.main import MainWindow, _drain_qt_deferred_deletes


def _app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return cast(QApplication, instance)


def _wait_until_closed(window: MainWindow, app: QApplication) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        app.processEvents()
        try:
            if not window.isVisible():
                return
        except RuntimeError:
            return
        QTest.qWait(10)


@pytest.mark.parametrize("channel", ("development", "release"))
def test_mainwindow_builds_all_workspaces_with_company_metadata_and_no_industry_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    channel: str,
) -> None:
    """公司產業分類仍存在，缺少指數資料時仍建立完整 13 個 workspace。"""

    data_root = tmp_path / "data"
    output_root = tmp_path / "output"
    effective_data_root = data_root / "_test"
    meta_data_dir = effective_data_root / "meta_data"
    meta_data_dir.mkdir(parents=True)
    (meta_data_dir / "companies.csv").write_text(
        "stock_id,stock_name,industry_category\n2330,合成公司,半導體業\n",
        encoding="utf-8-sig",
    )
    assert not (meta_data_dir / "industry_index.csv").exists()

    monkeypatch.setenv("PROFILE", "test")
    monkeypatch.setenv("DATA_ROOT", str(data_root))
    monkeypatch.setenv("OUTPUT_ROOT", str(output_root))
    for name in (
        "RESEARCH_CONSOLE_PROJECTION",
        "P0_SOURCE_CONTROL_CENTER_AUDIT",
        "P0_SOURCE_CONTROL_CENTER_DECISIONS",
        "P0_SOURCE_CONTROL_CENTER_LICENSE_EVIDENCE",
        "PROGRAM_READINESS_ARTIFACT",
        "MONTHLY_REVENUE_AVAILABILITY_CANDIDATE",
        "DATA_UPDATE_STATUS_ARTIFACT",
        "DATA_FRESHNESS_STATUS_ARTIFACT",
        "DATA_UPDATE_HISTORY_ARTIFACT",
        "TPEX_REFRESH_STATUS_ARTIFACT",
        "EVIDENCE_REHEARSAL_REPORT",
        "WEEKLY_EVIDENCE_HISTORY_PROJECTION_PATH",
    ):
        monkeypatch.delenv(name, raising=False)

    app = _app()
    source_commit = "abcdef0123456789abcdef0123456789abcdef01"
    lock_hash = "1" * 64
    identity = BuildIdentity(
        version=f"2026.10.22+{source_commit[:12]}",
        source_commit=source_commit,
        channel=channel,
        dirty=False,
        dependency_lock_sha256=lock_hash,
    )
    window = MainWindow(build_identity=identity)
    window.resize(1280, 760)
    window.show()
    app.processEvents()
    expected_workspaces = (
        "workbench",
        "market_explore",
        "recommendation",
        "backtest",
        "watchlist",
        "stock_research",
        "portfolio",
        "update",
        "runtime",
        "stock_lookup",
        "strategy_library",
        "storage",
        "research_timeline",
    )
    try:
        assert window.config.data_root == effective_data_root
        assert window.config.output_root == output_root / "_test"
        visible_identity = window.build_identity_label.text()
        if channel == "release":
            assert visible_identity == "2026.10.22｜發布版"
            assert source_commit not in visible_identity
            assert source_commit[:12] not in window.windowTitle()
            assert source_commit in window.build_identity_label.toolTip()
            assert lock_hash in window.build_identity_label.toolTip()
        else:
            assert "開發版" in visible_identity
            assert source_commit[:12] in visible_identity
            assert source_commit[:12] in window.windowTitle()
        assert set(window.workspace_widgets) == set(expected_workspaces)
        assert window.workspace_stack.count() == len(expected_workspaces)

        primary_keys = tuple(item.key for item in PRIMARY_NAVIGATION)
        assert len(primary_keys) == 5
        assert tuple(window.left_navigation.item_keys()) == primary_keys
        for key in primary_keys:
            button = window.left_navigation.button_for_key(key)
            assert button is not None
            button.click()
            app.processEvents()
            assert window.left_navigation.current_key() == key

        for route in PRODUCT_ROUTES:
            shell = window.product_shell
            shell.activate_group(route.group)
            app.processEvents()
            route_button = shell.subnav._buttons.get(route.route_id)
            assert route_button is not None
            route_button.click()
            app.processEvents()
            assert shell.route_id == route.route_id
            assert shell.subnav.current_route == route.route_id
            assert window.workspace_stack.currentWidget() is window.workspace_widgets[route.workspace]
            assert window.left_navigation.current_key() == route.group
    finally:
        try:
            window._select_main_workspace("workbench")
        except RuntimeError:
            pass
        if window.isVisible():
            window.close()
            _wait_until_closed(window, app)
        _drain_qt_deferred_deletes(app, (window,))
