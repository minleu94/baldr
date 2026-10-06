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


def test_mainwindow_builds_all_workspaces_with_company_metadata_and_no_industry_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """公司產業分類仍存在，缺少指數資料時不應阻斷九個 workspace。"""

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
    window = MainWindow()
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
    )
    try:
        assert window.config.data_root == effective_data_root
        assert window.config.output_root == output_root / "_test"
        assert set(window.workspace_widgets) == set(expected_workspaces)
        assert window.workspace_stack.count() == len(expected_workspaces)

        for key in expected_workspaces:
            button = window.left_navigation.button_for_key(key)
            assert button is not None
            button.click()
            app.processEvents()
            assert window.workspace_stack.currentWidget() is window.workspace_widgets[key]
    finally:
        try:
            window._select_main_workspace("workbench")
        except RuntimeError:
            pass
        if window.isVisible():
            window.close()
            _wait_until_closed(window, app)
        _drain_qt_deferred_deletes(app, (window,))
