from __future__ import annotations

import gc
import os
import warnings
from weakref import ref

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QRect, QSize, Qt
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QLayout,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QTableView,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtTest import QTest

from ui_qt.widgets.layout_helpers import (
    bounded_initial_window_geometry,
    create_scroll_area,
    ensure_visible_rows,
)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_initial_window_geometry_is_bounded_to_available_logical_screen_area():
    for available in (
        QRect(0, 0, 1366, 728),
        QRect(0, 0, 1920, 1040),
        QRect(0, 0, 2293, 912),
        QRect(0, 0, 300, 200),
    ):
        geometry = bounded_initial_window_geometry(available)

        assert geometry.width() <= max(1, available.width() - 32)
        assert geometry.height() <= max(1, available.height() - 48)
        assert geometry.x() >= available.x()
        assert geometry.y() >= available.y()
        assert geometry.x() + geometry.width() <= available.x() + available.width()
        assert geometry.y() + geometry.height() <= available.y() + available.height()

    desktop = bounded_initial_window_geometry(QRect(0, 0, 1920, 1040))
    assert (desktop.width(), desktop.height()) == (1400, 800)


def test_table_keeps_five_rows_and_accounts_for_wrapped_row_and_horizontal_scrollbar():
    app = _app()
    table = QTableWidget(6, 8)
    try:
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        table.resize(280, 200)
        for row in range(6):
            table.setRowHeight(row, 30)
        table.setRowHeight(0, 78)
        table.show()
        app.processEvents()

        minimum_height = ensure_visible_rows(table, 5)
        expected_rows_height = sum(table.rowHeight(row) for row in range(5))
        expected_chrome = (
            table.horizontalHeader().sizeHint().height()
            + table.horizontalScrollBar().sizeHint().height()
            + 2 * table.frameWidth()
        )
        table.resize(table.width(), minimum_height)
        table.verticalScrollBar().setValue(0)
        app.processEvents()

        assert minimum_height >= expected_rows_height + expected_chrome
        assert table.minimumHeight() >= minimum_height
        assert table.maximumHeight() == QWidget().maximumHeight()
        assert table.visualRect(table.model().index(0, 0)).top() >= 0
        assert table.visualRect(table.model().index(4, 0)).bottom() < table.viewport().height()
    finally:
        table.close()
        table.deleteLater()
        app.processEvents()


def test_list_remeasures_when_long_items_are_added_after_initial_empty_measurement():
    app = _app()
    items = QListWidget()
    try:
        items.resize(260, 160)
        items.show()
        initial_height = ensure_visible_rows(items, 5)

        for row in range(6):
            QListWidgetItem(f"項目 {row}", items)
        long_item = items.item(0)
        long_item.setSizeHint(QSize(220, 72))
        app.processEvents()

        expected_items_height = sum(
            max(items.sizeHintForRow(row), items.fontMetrics().height() + 8)
            for row in range(5)
        )
        # model／SizeHint 事件應自行重算；不再手動呼叫 helper 觸發更新。
        assert items.minimumHeight() >= expected_items_height + 2 * items.frameWidth()
        items.resize(items.width(), items.minimumHeight())
        items.verticalScrollBar().setValue(0)
        app.processEvents()

        assert items.minimumHeight() >= initial_height
        assert items.visualItemRect(items.item(0)).top() >= 0
        assert items.visualItemRect(items.item(4)).bottom() < items.viewport().height()
    finally:
        items.close()
        items.deleteLater()
        app.processEvents()


def test_view_state_is_ready_when_geometry_event_arrives_and_keeps_five_rows_visible():
    app = _app()

    class GeometryProbeTable(QTableWidget):
        def __init__(self) -> None:
            self.state_snapshots: list[tuple[object, bool, object]] = []
            super().__init__(6, 2)

        def resizeEvent(self, event) -> None:  # noqa: N802
            state = getattr(self, "_layout_helpers_visible_rows_controller", None)
            if state is not None:
                self.state_snapshots.append(
                    (state, state._view() is self, state._rows)
                )
            super().resizeEvent(event)

    table = GeometryProbeTable()
    try:
        for row in range(6):
            table.setRowHeight(row, 32)
        table.resize(300, 180)
        table.show()
        ensure_visible_rows(table, 5)
        app.processEvents()

        state = getattr(table, "_layout_helpers_visible_rows_controller")
        assert table.state_snapshots
        assert all(snapshot == (state, True, 5) for snapshot in table.state_snapshots)
        table.resize(table.width(), table.minimumHeight())
        table.verticalScrollBar().setValue(0)
        app.processEvents()

        first_five = [
            table.visualRect(table.model().index(row, 0)) for row in range(5)
        ]
        assert all(rect.isValid() and rect.top() >= 0 for rect in first_five)
        assert first_five[-1].bottom() < table.viewport().height()
    finally:
        table.close()
        table.deleteLater()
        app.processEvents()


def test_app_dispatcher_metaobject_stays_stable_across_views_and_model_swaps():
    app = _app()
    views: list[QTableView] = []
    initial_method_count: int | None = None
    try:
        seed_view = QTableView()
        views.append(seed_view)
        ensure_visible_rows(seed_view, 5)
        dispatcher = getattr(app, "_layout_helpers_visible_rows_dispatcher")
        initial_method_count = dispatcher.metaObject().methodCount()

        for _view_index in range(8):
            view = QTableView()
            views.append(view)
            ensure_visible_rows(view, 5)
            state = getattr(view, "_layout_helpers_visible_rows_controller")
            assert not isinstance(state, QObject)
            assert dispatcher.metaObject().methodCount() == initial_method_count

            for _model_index in range(3):
                model = QStandardItemModel(6, 3, app)
                view.setModel(model)
                app.processEvents()

                assert state._connected_model is model
                assert dispatcher.metaObject().methodCount() == initial_method_count
    finally:
        for view in views:
            view.close()
            view.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()


def test_pending_measure_is_discarded_when_view_is_deferred_deleted():
    app = _app()
    view = QTableView()
    state = None
    try:
        ensure_visible_rows(view, 5)
        state = getattr(view, "_layout_helpers_visible_rows_controller")
        dispatcher = getattr(app, "_layout_helpers_visible_rows_dispatcher")
        measurements: list[int] = []
        original_measure = state.measure_and_apply

        def counted_measure() -> int:
            measurements.append(1)
            return original_measure()

        state.measure_and_apply = counted_measure
        state.schedule_measure()
        assert state._scheduled
        assert dispatcher._timer.isActive()

        view.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()

        assert state.disposed
        assert not state._scheduled
        assert not measurements
        assert not dispatcher._pending
    finally:
        if state is not None and not state.disposed:
            view.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()


def test_destroyed_callback_does_not_warn_or_retain_visible_rows_state():
    app = _app()
    view = QTableView()
    ensure_visible_rows(view, 5)
    state = getattr(view, "_layout_helpers_visible_rows_controller")
    dispatcher = getattr(app, "_layout_helpers_visible_rows_dispatcher")
    state_ref = ref(state)

    state.schedule_measure()
    assert state._scheduled
    # 模擬 QObject 已先移除正在銷毀的 sender connection，再進入清理回呼。
    view.destroyed.disconnect(state._destroyed_callback)

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always", RuntimeWarning)
        state._on_view_destroyed()
        app.processEvents()

    assert state.disposed
    assert not state._scheduled
    assert not dispatcher._pending
    assert not [warning for warning in captured if issubclass(warning.category, RuntimeWarning)]

    state = None
    view = None
    gc.collect()
    app.processEvents()
    assert state_ref() is None


def test_model_replacement_disconnects_old_model_and_keeps_new_model_resize_reactive():
    app = _app()
    view = QTableView()
    old_model = QStandardItemModel(6, 2, app)
    new_model = QStandardItemModel(6, 2, app)
    try:
        view.setModel(old_model)
        view.resize(300, 180)
        view.show()
        ensure_visible_rows(view, 5)
        state = getattr(view, "_layout_helpers_visible_rows_controller")
        measurement_count = 0
        original_measure = state.measure_and_apply

        def counted_measure() -> int:
            nonlocal measurement_count
            measurement_count += 1
            return original_measure()

        state.measure_and_apply = counted_measure
        view.setModel(new_model)
        app.processEvents()
        QTest.qWait(30)
        count_after_replace = measurement_count

        old_model.setData(old_model.index(0, 0), "stale update")
        app.processEvents()
        QTest.qWait(30)
        assert measurement_count == count_after_replace

        new_model.setData(new_model.index(0, 0), "current update")
        app.processEvents()
        QTest.qWait(30)
        assert measurement_count > count_after_replace

        previous_minimum = view.minimumHeight()
        view.resize(view.width() - 40, view.height())
        app.processEvents()
        QTest.qWait(30)
        view.verticalHeader().resizeSection(0, 80)
        app.processEvents()
        assert view.minimumHeight() >= previous_minimum
        view.resize(view.width(), view.minimumHeight())
        view.verticalScrollBar().setValue(0)
        app.processEvents()
        assert view.visualRect(new_model.index(4, 0)).bottom() < view.viewport().height()
    finally:
        view.close()
        view.deleteLater()
        app.processEvents()


def test_scroll_area_preserves_content_minimum_without_freezing_large_viewport_growth():
    app = _app()
    content = QWidget()
    content_layout = QVBoxLayout(content)
    for row in range(12):
        item = QWidget()
        item.setMinimumHeight(40)
        content_layout.addWidget(item)
    area = create_scroll_area(content, object_name="layoutAuditScroll")
    try:
        area.resize(320, 180)
        area.show()
        app.processEvents()

        assert area.objectName() == "layoutAuditScroll"
        assert area.widgetResizable()
        assert area.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        assert area.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
        assert (
            content.layout().verticalSizeConstraint()
            == QLayout.SizeConstraint.SetMinimumSize
        )
        assert (
            content.layout().horizontalSizeConstraint()
            == QLayout.SizeConstraint.SetNoConstraint
        )
        assert area.verticalScrollBar().maximum() > 0

        area.resize(520, 700)
        app.processEvents()
        assert area.viewport().height() > 180
    finally:
        area.close()
        area.deleteLater()
        app.processEvents()


def test_scroll_area_can_expose_horizontal_overflow_when_requested():
    app = _app()
    content = QWidget()
    content.setMinimumWidth(900)
    area = create_scroll_area(content, horizontal_scroll=True)
    try:
        area.resize(320, 180)
        area.show()
        app.processEvents()

        assert area.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
        assert area.horizontalScrollBar().maximum() > 0
    finally:
        area.close()
        area.deleteLater()
        app.processEvents()
