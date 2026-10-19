from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QBoxLayout

from tests.test_ui_qt_recommendation_exact_saved_entry import _read_model, _view


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    application = QApplication.instance() or QApplication([])
    yield application


def _wait_until(application: QApplication, predicate, *, timeout_ms: int = 5000) -> None:
    deadline = time.monotonic() + timeout_ms / 1000
    while True:
        application.processEvents()
        if predicate():
            application.processEvents()
            return
        if time.monotonic() >= deadline:
            raise AssertionError("推薦畫面狀態未在固定期限內完成")
        QTest.qWait(10)


def _rect_in_result_view(view, widget) -> QRect:
    top_left = widget.mapTo(view.result_scroll.viewport(), QPoint(0, 0))
    return QRect(top_left, widget.size())


def _make_view_with_saved_result(tmp_path: Path, result_id: str):
    backing_queries, read_model = _read_model(result_id)
    queries = SimpleNamespace(
        get=backing_queries.get,
        list=lambda: (read_model,),
    )
    view = _view(tmp_path, queries)
    view.refresh_saved_sources_button.setEnabled(True)
    view.load_daily_recommendation_button.setEnabled(True)
    return view, backing_queries, read_model


def _open_from_existing_source_controls(
    view,
    application: QApplication,
    result_id: str,
) -> None:
    view.refresh_saved_sources_button.click()
    _wait_until(
        application,
        lambda: view._saved_source_list_worker is None,
    )

    matching_index = next(
        index
        for index in range(1, view.saved_source_combo.count())
        if (
            isinstance(
                view.saved_source_combo.itemData(index, Qt.ItemDataRole.UserRole),
                (tuple, list),
            )
            and len(view.saved_source_combo.itemData(index, Qt.ItemDataRole.UserRole)) == 8
            and view.saved_source_combo.itemData(index, Qt.ItemDataRole.UserRole)[3]
            == result_id
        )
    )
    view.saved_source_combo.setCurrentIndex(matching_index)
    view.load_saved_result_button.click()
    _wait_until(
        application,
        lambda: view._saved_result_load_worker is None,
    )


def _show_at_desktop_result_width(view, application: QApplication) -> None:
    view.resize(1280, 760)
    view.show()
    application.processEvents()
    view.main_splitter.setSizes([450, 800])
    application.processEvents()
    view._apply_responsive_layout(force=True)
    application.processEvents()
    assert 720 <= view.result_scroll.viewport().width() < 900


def test_saved_readback_compacts_only_saved_controls_and_exposes_five_row_viewport(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    result_id = "compact-saved-recommendation-desktop-001"
    view, _backing_queries, read_model = _make_view_with_saved_result(
        tmp_path, result_id
    )
    original_controls = (
        view.saved_source_combo,
        view.refresh_saved_sources_button,
        view.load_daily_recommendation_button,
        view.cancel_saved_source_button,
        view.load_saved_result_button,
    )
    try:
        _show_at_desktop_result_width(view, qt_app)
        assert view.saved_result_row.direction() == QBoxLayout.Direction.TopToBottom
        assert view.result_title_layout.direction() == QBoxLayout.Direction.TopToBottom

        _open_from_existing_source_controls(view, qt_app, result_id)
        for _ in range(3):
            qt_app.processEvents()

        assert view.current_read_model == read_model
        assert view._verified_saved_result_id() == result_id
        assert "已讀取並驗證單筆 canonical 保存結果" in view.result_status_label.text()
        assert view.saved_result_row.direction() == QBoxLayout.Direction.LeftToRight
        assert view.result_title_layout.direction() == QBoxLayout.Direction.LeftToRight
        assert all(
            before is after
            for before, after in zip(
                original_controls,
                (
                    view.saved_source_combo,
                    view.refresh_saved_sources_button,
                    view.load_daily_recommendation_button,
                    view.cancel_saved_source_button,
                    view.load_saved_result_button,
                ),
            )
        )
        assert view.refresh_saved_sources_button.isEnabled()
        assert view.load_daily_recommendation_button.isEnabled()
        assert not view.cancel_saved_source_button.isEnabled()
        assert view.load_saved_result_button.isEnabled()

        view.result_scroll.verticalScrollBar().setValue(0)
        qt_app.processEvents()
        table = view.results_table
        row_height = table.verticalHeader().defaultSectionSize()
        assert table.minimumHeight() >= view.results_table_minimum_height
        assert table.viewport().height() >= row_height * 5
        table_rect = _rect_in_result_view(view, table)
        viewport_rect = view.result_scroll.viewport().rect()
        required_five_rows_bottom = (
            table_rect.top()
            + table.frameWidth()
            + table.horizontalHeader().height()
            + row_height * 5
        )
        assert table_rect.top() >= 0
        assert required_five_rows_bottom <= viewport_rect.bottom() + 1

        assert view.stock_research_btn.isVisible()
        assert not view.stock_research_btn.isEnabled()
        table.selectRow(0)
        qt_app.processEvents()
        assert view.stock_research_btn.isEnabled()
        assert viewport_rect.contains(_rect_in_result_view(view, view.stock_research_btn))

        # 返回窄頁時仍維持可捲動的原控制列。
        view.resize(390, 844)
        qt_app.processEvents()
        view._apply_responsive_layout(force=True)
        qt_app.processEvents()
        assert view.main_splitter.orientation() == Qt.Orientation.Vertical
        assert view.saved_result_row.direction() == QBoxLayout.Direction.TopToBottom
        assert view.result_title_layout.direction() == QBoxLayout.Direction.TopToBottom
        assert view.result_scroll.verticalScrollBar().maximum() > 0
        view.result_scroll.ensureWidgetVisible(view.load_daily_recommendation_button)
        qt_app.processEvents()
        assert view.result_scroll.viewport().rect().intersects(
            _rect_in_result_view(view, view.load_daily_recommendation_button)
        )

        # 將同一份封存執行結果作一般新分析結果呈現時，恢復原窄版方向。
        view.resize(1280, 760)
        qt_app.processEvents()
        view.main_splitter.setSizes([450, 800])
        qt_app.processEvents()
        view._apply_responsive_layout(force=True)
        execution = read_model.execution
        assert execution is not None
        view._on_recommendation_finished(execution)
        qt_app.processEvents()
        assert view.current_read_model is None
        assert view.saved_result_row.direction() == QBoxLayout.Direction.TopToBottom
        assert view.result_title_layout.direction() == QBoxLayout.Direction.TopToBottom
    finally:
        view.close()
        qt_app.processEvents()


def test_failed_or_cancelled_readback_preserves_previous_saved_result_and_layout(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    result_id = "compact-saved-recommendation-preserve-001"
    view, backing_queries, read_model = _make_view_with_saved_result(
        tmp_path, result_id
    )
    release = threading.Event()
    try:
        _show_at_desktop_result_width(view, qt_app)
        _open_from_existing_source_controls(view, qt_app, result_id)
        loaded_model = view.current_read_model
        assert loaded_model == read_model
        original_model = view.results_table.model()
        assert view.saved_result_row.direction() == QBoxLayout.Direction.LeftToRight
        assert view.result_title_layout.direction() == QBoxLayout.Direction.LeftToRight

        def fail_get(_requested_id: str):
            raise ValueError("保存來源測試失敗")

        view.recommendation_composition = SimpleNamespace(
            queries=SimpleNamespace(get=fail_get, list=lambda: (read_model,))
        )
        assert view.open_saved_recommendation_result("failed-secondary-result")
        _wait_until(qt_app, lambda: view._saved_result_load_worker is None)
        assert view.current_read_model is loaded_model
        assert view.results_table.model() is original_model
        assert "原畫面保留" in view.result_status_label.text()
        assert view.saved_result_row.direction() == QBoxLayout.Direction.LeftToRight
        assert view.result_title_layout.direction() == QBoxLayout.Direction.LeftToRight

        entered = threading.Event()

        def delayed_get(_requested_id: str):
            entered.set()
            assert release.wait(5)
            return backing_queries.get(result_id)

        view.recommendation_composition = SimpleNamespace(
            queries=SimpleNamespace(get=delayed_get, list=lambda: (read_model,))
        )
        assert view.open_saved_recommendation_result("cancelled-secondary-result")
        worker = view._saved_result_load_worker
        assert worker is not None
        assert entered.wait(2)
        view._cancel_saved_source_read()
        release.set()
        assert worker.wait(10_000)
        _wait_until(qt_app, lambda: view._saved_result_load_worker is None)

        assert view.current_read_model is loaded_model
        assert view.results_table.model() is original_model
        assert view.saved_result_row.direction() == QBoxLayout.Direction.LeftToRight
        assert view.result_title_layout.direction() == QBoxLayout.Direction.LeftToRight
    finally:
        release.set()
        view.close()
        qt_app.processEvents()
