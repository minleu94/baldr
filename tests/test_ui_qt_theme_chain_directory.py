"""產業鏈卡片目錄的導航、覆蓋與生命週期回歸。"""

import os
import sys
import threading
import time
from datetime import date, datetime, timezone
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QGroupBox, QLabel, QPushButton

from app_module.theme_daily_service import (
    ThemeDailyReport,
    ThemeDailyRow,
    ThemeMetricCoverage,
)
from app_module.theme_research_snapshot import ThemeResearchSnapshot

from ui_qt.views import industry_theme_map_view as view_module

IndustryThemeMapView = view_module.IndustryThemeMapView


def app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


@pytest.fixture(scope="session", autouse=True)
def _keep_application_alive():
    application = app()
    yield application
    application.processEvents()


def _close_directory_view(view, application):
    view.shutdown()
    _wait_until(application, lambda: not view.is_busy())
    view.close()
    view.deleteLater()
    QCoreApplication.sendPostedEvents(view, QEvent.Type.DeferredDelete)
    application.processEvents()


def _wait_until(application, predicate, *, timeout_ms: int = 3000) -> None:
    deadline = time.monotonic() + timeout_ms / 1000
    while True:
        application.processEvents()
        if predicate():
            application.processEvents()
            return
        if time.monotonic() >= deadline:
            raise AssertionError("Qt 狀態未在固定期限內完成")
        QTest.qWait(10)


def _snapshot(
    specifications: tuple[
        tuple[str, str, tuple[str, ...], Decimal | None, ThemeMetricCoverage], ...
    ],
    *,
    identity: str = "a" * 64,
) -> ThemeResearchSnapshot:
    rows = []
    mapping = []
    for chain, theme, stock_ids, returns, coverage in specifications:
        rows.append(
            ThemeDailyRow(
                chain_name=chain,
                theme_name=theme,
                stock_ids=stock_ids,
                mean_return_pct=returns,
                turnover_twd=None,
                volume_multiple_5d=None,
                institutional_net_shares=None,
                institutional_net_turnover_twd=None,
                up_count=0,
                down_count=0,
                flat_count=0,
                institutional_buy_count=0,
                institutional_sell_count=0,
                institutional_flat_count=0,
                advancing_ratio=None,
                institutional_buy_ratio=None,
                coverage=coverage,
                source_ids=("task-local-fixture",),
            )
        )
        for stock_id in stock_ids:
            mapping.append(
                SimpleNamespace(
                    stock_id=stock_id,
                    stock_name=f"測試公司{stock_id}",
                    chain_name=chain,
                    theme_name=theme,
                    chain_tier="測試鏈",
                    assignment_method="測試分類",
                    source_name="task-local fixture",
                    source_tier="fixture",
                    evidence_note="僅測試目錄呈現",
                )
            )
    report = ThemeDailyReport(
        data_date=date(2026, 10, 19),
        known_at=datetime(2026, 10, 20, 0, 0, tzinfo=timezone.utc),
        mapping_snapshot_date="2026-10-16",
        mapping_available_date="2026-10-16",
        status="current_research",
        rows=tuple(rows),
        warnings=(),
    )
    return ThemeResearchSnapshot(identity, report, tuple(mapping))


def _many_chains(count: int) -> ThemeResearchSnapshot:
    complete = ThemeMetricCoverage(1, 1, 0, 0, 0, 0)
    specifications = []
    for chain_index in range(count):
        chain = f"產業鏈{chain_index:02d}"
        stock_id = f"{chain_index:04d}"
        for theme_index in range(4):
            specifications.append(
                (
                    chain,
                    f"題材{theme_index:02d}",
                    (stock_id,),
                    Decimal(theme_index),
                    complete,
                )
            )
    return _snapshot(tuple(specifications))


def _card(view: IndustryThemeMapView, chain: str) -> QGroupBox:
    return next(
        card
        for card in view.chain_directory_group.findChildren(
            QGroupBox, "industryThemeChainDirectoryCard"
        )
        if card.title() == chain
    )


def _shortcut(card: QGroupBox, theme: str) -> QPushButton:
    return next(
        button
        for button in card.findChildren(
            QPushButton, "industryThemeChainDirectoryShortcut"
        )
        if button.text() == theme
    )


def _value_label(card: QGroupBox, chain: str, theme: str) -> QLabel:
    accessible_name = f"{chain}／{theme}漲跌觀察與覆蓋"
    return next(
        label
        for label in card.findChildren(QLabel)
        if label.accessibleName() == accessible_name
    )


@pytest.mark.parametrize("chain_count", (2, 27))
def test_directory_renders_exact_chain_count_and_only_three_name_order_shortcuts(chain_count):
    application = app()
    view = IndustryThemeMapView()
    try:
        view.set_snapshot(_many_chains(chain_count))

        cards = view.chain_directory_group.findChildren(
            QGroupBox, "industryThemeChainDirectoryCard"
        )
        assert len(cards) == chain_count
        assert view.chain_directory_group.isHidden()
        assert not view.chain_directory_button.isChecked()
        for card in cards:
            assert "4 個題材" in card.findChildren(QLabel)[0].text()
            assert "1 檔不重複成員" in card.findChildren(QLabel)[0].text()
            buttons = card.findChildren(
                QPushButton, "industryThemeChainDirectoryShortcut"
            )
            assert [button.text() for button in buttons] == [
                "題材00", "題材01", "題材02",
            ]

        assert view.theme_filter.count() == 1 + chain_count * 4
        view.chain_filter.setCurrentIndex(view.chain_filter.findData("產業鏈00"))
        assert view.theme_filter.count() == 5
    finally:
        _close_directory_view(view, application)


def test_name_shortcut_selects_original_theme_without_reading_or_changing_rankings(monkeypatch):
    application = app()
    snapshot = _many_chains(2)
    source_calls = []
    selection_events = []
    view = IndustryThemeMapView()
    view.snapshotChanged.connect(selection_events.append)
    view.stockSelected.connect(lambda stock_id: selection_events.append(stock_id))

    def forbidden_read(*args, **kwargs):
        source_calls.append((args, kwargs))
        raise AssertionError("目錄捷徑不得重讀版本來源")

    monkeypatch.setattr(view_module, "read_theme_research_snapshot", forbidden_read)
    try:
        view.set_snapshot(snapshot)
        before = tuple(
            tuple(
                view.ranking_table.item(row, column).text()
                for column in range(view.ranking_table.columnCount())
            )
            for row in range(view.ranking_table.rowCount())
        )
        card = _card(view, "產業鏈00")
        shortcut = _shortcut(card, "題材00")

        view.chain_directory_button.click()
        assert not view.chain_directory_group.isHidden()
        assert "名稱序不是表現排行" in view.chain_directory_note.text()
        shortcut.click()

        assert view.chain_filter.currentData() == "產業鏈00"
        assert view.theme_filter.currentText() == "題材00"
        assert view.chain_directory_group.isHidden()
        assert not view.chain_directory_button.isChecked()
        after = tuple(
            tuple(
                view.ranking_table.item(row, column).text()
                for column in range(view.ranking_table.columnCount())
            )
            for row in range(view.ranking_table.rowCount())
        )
        assert after == before
        assert view.snapshot is snapshot
        assert source_calls == []
        assert selection_events == [snapshot]
    finally:
        _close_directory_view(view, application)


def test_shortcut_displays_only_fully_covered_finite_decimals_and_keeps_denominators():
    application = app()
    one_return = ThemeMetricCoverage(1, 1, 0, 0, 0, 0)
    partial_return = ThemeMetricCoverage(2, 1, 0, 0, 0, 0)
    missing_return = ThemeMetricCoverage(2, 0, 0, 0, 0, 0)
    snapshot = _snapshot((
        ("鏈甲", "甲零", ("1001",), Decimal("0.0000"), one_return),
        ("鏈甲", "乙負", ("1002",), Decimal("-1.2500"), one_return),
        ("鏈甲", "丙部分", ("1003", "1004"), Decimal("-999.00"), partial_return),
        ("鏈乙", "丁缺", ("1005", "1006"), None, missing_return),
    ))
    view = IndustryThemeMapView()
    try:
        view.set_snapshot(snapshot)
        card = _card(view, "鏈甲")
        assert [
            button.text()
            for button in card.findChildren(
                QPushButton, "industryThemeChainDirectoryShortcut"
            )
        ] == sorted(["甲零", "乙負", "丙部分"])

        zero_label = _value_label(card, "鏈甲", "甲零")
        negative_label = _value_label(card, "鏈甲", "乙負")
        partial_label = _value_label(card, "鏈甲", "丙部分")
        missing_label = _value_label(_card(view, "鏈乙"), "鏈乙", "丁缺")
        assert zero_label.text() == "平均日漲跌幅：0.00 %｜1 / 1 位成員"
        assert zero_label.toolTip() == "0.0000 %"
        assert negative_label.text() == "平均日漲跌幅：-1.25 %｜1 / 1 位成員"
        assert negative_label.toolTip() == "-1.2500 %"
        assert partial_label.text() == "平均日漲跌幅：漲跌未提供｜1 / 2 位成員"
        assert "-999" not in partial_label.text()
        assert "1 / 2 位成員" in partial_label.toolTip()
        assert missing_label.text() == "平均日漲跌幅：漲跌未提供｜0 / 2 位成員"
        assert "0 / 2 位成員" in missing_label.toolTip()
    finally:
        _close_directory_view(view, application)


@pytest.mark.parametrize("raw", ("NaN", "sNaN", "Infinity", "-Infinity"))
def test_nonfinite_return_is_unavailable_even_with_full_coverage(raw):
    application = app()
    original = _many_chains(1).report.rows[0]
    row = replace(original, mean_return_pct=Decimal(raw))
    view = IndustryThemeMapView()
    try:
        assert view._chain_directory_shortcut_text(row) == (
            "平均日漲跌幅：漲跌未提供｜1 / 1 位成員"
        )
        assert raw not in view._chain_directory_shortcut_tooltip(row)
        assert "1 / 1 位成員" in view._chain_directory_shortcut_tooltip(row)
    finally:
        _close_directory_view(view, application)


def test_old_snapshot_shortcut_signal_cannot_select_same_named_theme_in_new_version():
    application = app()
    original = _many_chains(2)
    replacement_base = _many_chains(2)
    replacement = ThemeResearchSnapshot(
        "b" * 64, replacement_base.report, replacement_base.mapping
    )
    view = IndustryThemeMapView()
    try:
        view.set_snapshot(original)
        old_button = _shortcut(_card(view, "產業鏈00"), "題材00")

        view.set_snapshot(replacement)
        assert view.snapshot is replacement
        assert view.chain_filter.currentData() is None
        # 模擬已排入事件佇列的舊signal，驗證identity守衛仍在click入口生效。
        old_button.clicked.emit()
        assert view.chain_filter.currentData() is None
        assert view.theme_filter.currentIndex() == 0
    finally:
        _close_directory_view(view, application)


def test_old_directory_shortcuts_are_inert_while_busy_and_after_shutdown(monkeypatch):
    application = app()
    first_snapshot = _many_chains(2)
    replacement = _many_chains(2)
    replacement = ThemeResearchSnapshot(
        "b" * 64, replacement.report, replacement.mapping
    )
    started = threading.Event()
    release = threading.Event()
    view = IndustryThemeMapView()
    try:
        view.set_snapshot(first_snapshot)
        old_button = _shortcut(_card(view, "產業鏈00"), "題材00")

        def delayed_read(_path: Path):
            started.set()
            release.wait(timeout=2)
            return replacement

        monkeypatch.setattr(
            view_module, "read_theme_research_snapshot", delayed_read
        )
        view.load_snapshot(Path("delayed-manifest.json"))
        assert started.wait(timeout=1)
        assert view.is_busy()
        assert not view.chain_directory_button.isEnabled()
        old_button.click()
        assert view.chain_filter.currentData() is None
        assert view.theme_filter.currentIndex() == 0

        release.set()
        _wait_until(application, lambda: not view.is_busy())
        assert view.snapshot is replacement
        current_button = _shortcut(_card(view, "產業鏈00"), "題材00")
        view.shutdown()
        current_button.clicked.emit()
        assert view.snapshot is None
        assert view.chain_filter.currentData() is None
        assert view.theme_filter.currentIndex() == 0
    finally:
        release.set()
        _close_directory_view(view, application)


def test_failed_reload_clears_chain_cards_and_disables_directory(monkeypatch):
    application = app()
    view = IndustryThemeMapView()
    try:
        view.set_snapshot(_many_chains(2))
        assert view.chain_directory_group.findChildren(
            QGroupBox, "industryThemeChainDirectoryCard"
        )

        def fail_read(_path: Path):
            raise ValueError("來源讀取失敗")

        monkeypatch.setattr(view_module, "read_theme_research_snapshot", fail_read)
        view.load_snapshot(Path("missing-manifest.json"))
        assert view.snapshot is None
        assert not view.chain_directory_button.isEnabled()
        _wait_until(application, lambda: not view.is_busy())
        assert not view.chain_directory_group.findChildren(
            QGroupBox, "industryThemeChainDirectoryCard"
        )
    finally:
        _close_directory_view(view, application)
