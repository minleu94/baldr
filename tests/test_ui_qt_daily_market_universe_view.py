"""真 parent 保存來源經完整母體頁查詢及原 child 下鑽。"""
from __future__ import annotations

from dataclasses import replace
import time
import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app_module.daily_market_universe_run import DailyMarketUniverseRunReader
from app_module.daily_market_universe_selection import (UniverseResearchQuery,
    read_universe_research_page, resolve_universe_stock_snapshot)
from ui_qt.views.daily_market_universe_view import DailyMarketUniverseView
from ui_qt.views.daily_market_research_view import DailyMarketResearchView
from tests.test_daily_market_universe_run_query import completed_run  # noqa: F401


def _wait_for_idle(app, daily):
    deadline = time.monotonic() + 30
    while daily._worker is not None and time.monotonic() < deadline:
        app.processEvents()
        QTest.qWait(10)
    assert daily._worker is None, daily.status_label.text()


def test_saved_full_population_page_and_exact_child(completed_run):
    root, identity, codes = completed_run
    app = QApplication.instance() or QApplication([])
    with DailyMarketUniverseRunReader.open(root, identity) as reader:
        query = UniverseResearchQuery(str(root), identity, reader.manifest_sha256,
            ("close_above_ma20", "close_above_ma60"), "OR", page=5, page_size=50)
    page = read_universe_research_page(query)
    assert page.page.total_count == 258  # 257 納入與一筆具名排除。
    assert page.page.rows[-1]["stock_code"] == "X9999"
    view = DailyMarketUniverseView(root)
    view._show_page(page)
    assert "納入 257" in view.summary.text()
    assert "排除 1" in view.summary.text()
    assert view.table.rowCount() == 8
    assert view.mode.currentText() == "OR"
    assert view.conditions["close_above_ma20"].isChecked()
    assert view.conditions["close_above_ma60"].isChecked()
    assert not view.conditions["close_above_bbands30_upper"].isChecked()
    service, snapshot = resolve_universe_stock_snapshot(query, codes[-1])
    assert tuple(snapshot.stock_snapshots) == (codes[-1],)
    row = service.filter_rows(snapshot, query.condition_keys, query.combine_mode)[0]
    assert row.stock_code == codes[-1]
    context = service.context_for_stock(row)
    assert context.source_snapshot_hash == snapshot.manifest_sha256
    assert context.daily_snapshot_root == str(service.snapshot_root)

    selected_index = next(index for index in range(view.table.rowCount())
        if view.table.item(index, 0).text() == codes[-1])
    view.table.setCurrentCell(selected_index, 0)
    view.table.selectRow(selected_index)
    daily = DailyMarketResearchView(service)
    daily.universe_view = view
    view.cancelRequested.connect(daily.cancel_active_operation)
    opened = []
    daily.stockResearchRequested.connect(opened.append)
    daily._accept_universe_stock((query, codes[-1], (service, snapshot)))
    deadline = time.monotonic() + 30
    while not opened and time.monotonic() < deadline:
        app.processEvents()
        QTest.qWait(10)
    assert len(opened) == 1, daily.status_label.text()
    assert opened[0].stock_code == codes[-1]
    assert opened[0].source_snapshot_hash == snapshot.manifest_sha256
    assert opened[0].daily_snapshot_condition_keys == "close_above_ma20,close_above_ma60"
    assert opened[0].daily_snapshot_combine_mode == "OR"
    assert daily.restore_research_snapshot_stock(codes[-1], snapshot.manifest_sha256)
    assert view.current_query == query
    assert view.table.currentItem().text() == codes[-1]
    assert "納入 257" in view.summary.text()
    view._show_page(read_universe_research_page(query))
    assert view.table.currentItem().text() == codes[-1]
    assert view.mode.currentText() == "OR"
    assert daily.begin_shutdown()
    daily.close()
    assert view.begin_shutdown()
    view.close()
    app.processEvents()


@pytest.mark.parametrize("interrupt", ["cancel", "query_changed"])
def test_pending_population_drilldown_never_opens_after_cancel_or_query_change(
    completed_run, interrupt,
):
    root, identity, codes = completed_run
    app = QApplication.instance() or QApplication([])
    with DailyMarketUniverseRunReader.open(root, identity) as reader:
        query = UniverseResearchQuery(str(root), identity, reader.manifest_sha256)
    view = DailyMarketUniverseView(root)
    view._show_page(read_universe_research_page(query))
    service, snapshot = resolve_universe_stock_snapshot(query, codes[0])
    daily = DailyMarketResearchView(service)
    daily.universe_view = view
    view.cancelRequested.connect(daily.cancel_active_operation)
    opened = []
    daily.stockResearchRequested.connect(opened.append)
    try:
        daily._accept_universe_stock((query, codes[0], (service, snapshot)))
        assert daily._pending_universe_stock is not None
        if interrupt == "cancel":
            view.cancel_button.click()
        else:
            view._show_page(read_universe_research_page(replace(query, descending=True)))
        _wait_for_idle(app, daily)
        assert not opened
        assert daily._pending_universe_stock is None
        assert daily._snapshot.manifest_sha256 == snapshot.manifest_sha256
    finally:
        daily.begin_shutdown()
        _wait_for_idle(app, daily)
        daily.close()
        view.close()
        app.processEvents()
