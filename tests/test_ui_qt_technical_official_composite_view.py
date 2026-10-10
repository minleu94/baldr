"""以真實 synthetic bundle 驗證窄窗、完整文字與跨頁回返狀態。"""

from __future__ import annotations

from pathlib import Path
import sys
import time
from typing import cast

import pytest

_REPO = next(
    path for path in Path(__file__).resolve().parents
    if (path / "tests").is_dir() and (path / "app_module").is_dir()
)
for _import_path in (str(_REPO), str(_REPO / "tests")):
    if _import_path not in sys.path:
        sys.path.insert(0, _import_path)

from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSizePolicy,
    QWidget,
)
from ui_qt.views.daily_market_technical_official_disposition_composite_view import (
    DailyMarketTechnicalOfficialDispositionCompositeView,
)
from ui_qt.main import _drain_qt_deferred_deletes
from test_daily_market_technical_official_disposition_bundle_v1 import _BundleFixture


pytest_plugins = ("test_daily_market_technical_official_disposition_composite_reader_v1",)


@pytest.fixture(scope="module")
def app() -> QApplication:
    """重用單一 Qt application，讓 worker signal 在同一事件迴圈完成。"""

    instance = cast(QApplication | None, QApplication.instance())
    if instance is None:
        instance = QApplication([])
    return instance


def _wait_for_settled(
    app: QApplication,
    events: list[tuple[str, bool]],
    previous_count: int,
    *,
    timeout_seconds: float = 600.0,
) -> tuple[str, bool]:
    deadline = time.monotonic() + timeout_seconds
    while len(events) <= previous_count:
        app.processEvents()
        if time.monotonic() >= deadline:
            raise AssertionError("複合研究 View 背景工作逾時")
        time.sleep(0.005)
    app.processEvents()
    return events[previous_count]


def _close_view_and_wait_for_native_workers(
    app: QApplication,
    view: DailyMarketTechnicalOfficialDispositionCompositeView,
) -> None:
    """送出合作式關閉並等待 View 自有 worker 的原生執行緒終止。"""

    view.begin_shutdown()
    deadline = time.monotonic() + 600.0
    while view.active_worker is not None or view._has_running_worker():
        app.processEvents()
        if time.monotonic() >= deadline:
            raise AssertionError("複合研究 View worker 未在期限內到達原生終態")
        time.sleep(0.005)
    app.processEvents()
    assert view.active_worker is None
    assert not view._has_running_worker()
    assert not view._live_workers
    view.close()
    app.processEvents()
    assert not view.isVisible()
    _drain_qt_deferred_deletes(app, (view,))


def _filter_state(view: object) -> tuple[object, ...]:
    """讀取畫面條件控件，供跨頁與返回前後做精確比對。"""

    return (
        tuple(sorted(scope for scope, check in view.scope_checks.items() if check.isChecked())),
        tuple(
            (key, tuple(sorted(state for state, check in checks.items() if check.isChecked())))
            for key, checks in sorted(view.rule_state_checks.items())
        ),
        tuple(sorted(state for state, check in view.ma_state_checks.items() if check.isChecked())),
        tuple(sorted(state for state, check in view.kdj_state_checks.items() if check.isChecked())),
        view.technical_combine_box.currentData(),
        view.combine_box.currentData(),
        view.unknown_box.currentData(),
        tuple(sorted(state for state, check in view.market_checks.items() if check.isChecked())),
        tuple(sorted(state for state, check in view.disposal_checks.items() if check.isChecked())),
        view.bandwidth_min_input.text(),
        view.bandwidth_max_input.text(),
        view.atr14_min_input.text(),
        view.atr14_max_input.text(),
        view.stock_filter_enabled.isChecked(),
        view.stock_code_input.text(),
        view.sort_field_box.currentData(),
        view.sort_direction_box.currentData(),
        view.page_size_box.value(),
    )


def _assert_narrow_controls(view: QWidget) -> None:
    """驗證頂部控制與目前可見結果頁的最小寬度及位置。"""

    body = view.page_scroll.widget()  # type: ignore[attr-defined]
    assert body is not None
    assert view.width() == 460
    assert body.width() <= view.page_scroll.viewport().width()  # type: ignore[attr-defined]
    assert view.page_scroll.horizontalScrollBar().maximum() == 0  # type: ignore[attr-defined]
    stack = view.results_stack  # type: ignore[attr-defined]
    current_page = stack.currentWidget()
    controls: list[QWidget] = []
    for widget_type in (
        QAbstractButton,
        QComboBox,
        QLabel,
        QLineEdit,
        QPlainTextEdit,
        QSpinBox,
    ):
        controls.extend(
            control
            for control in body.findChildren(widget_type)
            if not stack.isAncestorOf(control) and control.isVisible()
        )
        if current_page is not None:
            controls.extend(
                control
                for control in current_page.findChildren(widget_type)
                if control.isVisible()
            )
    if current_page is not None:
        assert current_page.isVisible()
        page_position = current_page.mapTo(body, QPoint(0, 0))
        assert current_page.width() <= body.width()
        assert page_position.x() >= 0
        assert page_position.x() + current_page.width() <= body.width()
    assert controls
    for control in controls:
        position = control.mapTo(body, QPoint(0, 0))
        diagnostic = (
            f"{control.objectName() or type(control).__name__}: "
            f"{control.width()} < {control.minimumSizeHint().width()}"
        )
        if isinstance(control, QLabel):
            parent = control.parentWidget()
            diagnostic += (
                f"; text={control.text()!r}; wordWrap={control.wordWrap()}; "
                f"parent={type(parent).__name__ if parent is not None else None}"
                f"/{parent.objectName() if parent is not None else ''}"
            )
        assert control.width() >= control.minimumSizeHint().width(), (
            diagnostic
        )
        assert position.x() >= 0
        assert position.x() + control.width() <= body.width()


def test_long_source_path_keeps_exact_identity_without_widening_view(
    app: QApplication,
    tmp_path: Path,
) -> None:
    """長路徑仍精確保留，畫面以短狀態文字及完整提示呈現。"""

    root = tmp_path / ("saved_source_" + "x" * 80)
    root.mkdir()
    view_type = DailyMarketTechnicalOfficialDispositionCompositeView
    view = view_type(root)
    view.resize(460, 700)
    view.show()
    app.processEvents()
    try:
        assert view.bundle_output_root == root
        assert view.root_label.text() == "已選擇保存來源資料夾（完整路徑可停留查看）"
        assert view.root_label.toolTip() == f"完整保存來源路徑：\n{root}"
        assert view.root_label.accessibleDescription() == f"完整保存來源路徑：{root}"
        _assert_narrow_controls(view)
    finally:
        _close_view_and_wait_for_native_workers(app, view)


def test_loaded_page_label_wraps_at_narrow_width_without_losing_counts(
    app: QApplication,
) -> None:
    """載入頁碼全文在 460px 畫面換行，保留本頁與全域筆數。"""

    view_type = DailyMarketTechnicalOfficialDispositionCompositeView
    view = view_type(None)
    loaded_page_text = (
        "第 1 / 2 頁；本頁 256 列／每頁 256 列；全域可見 257 列"
    )
    view.resize(460, 700)
    view.show()
    app.processEvents()
    try:
        view.page_label.setText(loaded_page_text)
        app.processEvents()
        assert view.width() == 460
        assert view.page_label.objectName() == "technicalOfficialCompositePageLabel"
        assert view.page_label.wordWrap()
        assert view.page_label.text() == loaded_page_text
        assert view.page_label.height() > view.page_label.fontMetrics().height()
        assert "本頁 256 列" in view.page_label.text()
        assert "全域可見 257 列" in view.page_label.text()
        _assert_narrow_controls(view)
    finally:
        _close_view_and_wait_for_native_workers(app, view)


def _assert_every_stack_page_fits(view: QWidget, app: QApplication) -> None:
    """逐頁顯示結果 stack，再核對實際配置後的頁面幾何。"""

    stack = view.results_stack  # type: ignore[attr-defined]
    original_index = stack.currentIndex()
    assert stack.count() > 0
    try:
        for index in range(stack.count()):
            stack.setCurrentIndex(index)
            app.processEvents()
            current_page = stack.currentWidget()
            assert current_page is not None and current_page.isVisible()
            _assert_narrow_controls(view)
    finally:
        stack.setCurrentIndex(original_index)
        app.processEvents()


def _scroll_editor_to_last_line(
    app: QApplication,
    outer_scroll: QScrollArea,
    editor: QPlainTextEdit,
) -> None:
    """以可見鍵盤操作逐頁捲動唯讀文字，核對末行在內外 viewport 可見。"""

    assert editor.isReadOnly()
    assert editor.maximumHeight() > editor.minimumHeight()
    assert editor.sizePolicy().verticalPolicy() != QSizePolicy.Policy.Fixed
    assert editor.toPlainText().strip()
    assert editor.verticalScrollBar().maximum() > 0
    assert editor.horizontalScrollBar().maximum() == 0
    assert editor.isVisible() and editor.viewport().isVisible()

    top_level = editor.window()
    assert top_level.isVisible()
    top_level.raise_()
    top_level.activateWindow()
    outer_scroll.ensureWidgetVisible(editor, 0, 0)
    app.processEvents()
    active_window = QApplication.activeWindow()
    active_window_object_name = (
        repr(active_window.objectName()) if active_window is not None else None
    )
    active_window_title = (
        repr(active_window.windowTitle()) if active_window is not None else None
    )
    assert top_level.isActiveWindow() and active_window is top_level, (
        "編輯器所在視窗未重新啟用："
        f"top={type(top_level).__name__}/{top_level.objectName()!r}/"
        f"{top_level.windowTitle()!r}/visible={top_level.isVisible()}/"
        f"active={top_level.isActiveWindow()}；"
        f"active_window={type(active_window).__name__ if active_window else None}/"
        f"{active_window_object_name}/{active_window_title}"
    )

    editor_viewport = editor.viewport()
    outer_viewport = outer_scroll.viewport()
    editor_global_rect = QRect(
        editor_viewport.mapToGlobal(QPoint(0, 0)), editor_viewport.size()
    )
    outer_global_rect = QRect(
        outer_viewport.mapToGlobal(QPoint(0, 0)), outer_viewport.size()
    )
    visible_global_rect = editor_global_rect.intersected(outer_global_rect)
    assert not visible_global_rect.isEmpty(), (
        "編輯器 viewport 與外層 viewport 沒有可點擊交集："
        f"editor_global={editor_global_rect}, outer_global={outer_global_rect}, "
        f"editor_visible={editor_viewport.isVisible()}, "
        f"outer_visible={outer_viewport.isVisible()}"
    )
    click_global = visible_global_rect.center()
    click_position = editor_viewport.mapFromGlobal(click_global)
    assert editor_viewport.rect().contains(click_position)
    assert outer_global_rect.contains(click_global)
    QTest.mouseClick(
        editor_viewport,
        Qt.MouseButton.LeftButton,
        pos=click_position,
    )
    app.processEvents()
    focus_widget = QApplication.focusWidget()
    focus_widget_object_name = (
        repr(focus_widget.objectName()) if focus_widget is not None else None
    )
    active_window = QApplication.activeWindow()
    active_window_type = type(active_window).__name__ if active_window is not None else None
    assert top_level.isActiveWindow() and editor.hasFocus(), (
        "可見 viewport 點擊後唯讀編輯器未取得焦點："
        f"top_active={top_level.isActiveWindow()}, "
        f"active_window={active_window_type}, "
        f"focus_widget={type(focus_widget).__name__ if focus_widget else None}/"
        f"{focus_widget_object_name}, "
        f"editor_visible={editor.isVisible()}, viewport_visible={editor_viewport.isVisible()}, "
        f"focus_policy={editor.focusPolicy()}, click_local={click_position}, "
        f"click_global={click_global}, visible_intersection={visible_global_rect}"
    )

    bar = editor.verticalScrollBar()
    QTest.keyClick(editor, Qt.Key.Key_Home, Qt.KeyboardModifier.ControlModifier)
    app.processEvents()
    assert bar.value() == bar.minimum()
    previous = bar.value()
    assert previous <= bar.maximum()
    inner_scroll_steps = 0
    inner_scroll_state = f"value={bar.value()}/{bar.maximum()}, steps=0"
    for _ in range(512):
        if previous >= bar.maximum():
            break
        QTest.keyClick(editor, Qt.Key.Key_PageDown)
        app.processEvents()
        current = bar.value()
        current_target = bar.maximum()
        inner_scroll_steps += 1
        inner_scroll_state = (
            f"value={current}/{current_target}, steps={inner_scroll_steps}"
        )
        assert current <= current_target, inner_scroll_state
        assert current >= previous, inner_scroll_state
        assert current > previous or current == current_target, inner_scroll_state
        previous = current
    assert inner_scroll_steps > 0, inner_scroll_state
    assert bar.value() == bar.maximum(), inner_scroll_state
    last_block = editor.document().lastBlock()
    assert last_block.isValid()
    block_rect = editor.blockBoundingGeometry(last_block).translated(editor.contentOffset())
    assert block_rect.isValid()
    last_block_cursor = QTextCursor(last_block)
    last_block_cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
    last_visual_line = editor.cursorRect(last_block_cursor)
    assert block_rect.top() <= last_visual_line.center().y() <= block_rect.bottom()
    assert editor.viewport().rect().contains(last_visual_line.center())

    outer_viewport = outer_scroll.viewport()
    outer_bar = outer_scroll.verticalScrollBar()
    assert outer_viewport.isVisible()

    def mapped_line() -> QRectF:
        mapped_top_left = outer_viewport.mapFromGlobal(
            editor.viewport().mapToGlobal(last_visual_line.topLeft())
        )
        return QRectF(mapped_top_left, last_visual_line.size())

    outer_rect = QRectF(outer_viewport.rect())
    outer_scroll_steps = 0
    geometry_state = (
        f"editor_height={editor.height()}, outer_viewport_height={outer_viewport.height()}, "
        f"outer_scroll={outer_bar.value()}/{outer_bar.maximum()}"
    )
    for _ in range(128):
        mapped_last_line = mapped_line()
        if (
            mapped_last_line.top() >= outer_rect.top()
            and mapped_last_line.bottom() <= outer_rect.bottom()
        ):
            break
        if outer_bar.maximum() <= 0:
            raise AssertionError(
                f"末行超出外層可視範圍且外層沒有可捲動範圍：{geometry_state}"
            )
        key = (
            Qt.Key.Key_PageUp
            if mapped_last_line.top() < outer_rect.top()
            else Qt.Key.Key_PageDown
        )
        previous_outer_value = outer_bar.value()
        outer_bar.setFocus(Qt.FocusReason.OtherFocusReason)
        QTest.keyClick(outer_bar, key)
        app.processEvents()
        current_outer_value = outer_bar.value()
        outer_scroll_steps += 1
        geometry_state = (
            f"editor_height={editor.height()}, outer_viewport_height={outer_viewport.height()}, "
            f"outer_scroll={current_outer_value}/{outer_bar.maximum()}, steps={outer_scroll_steps}"
        )
        if key == Qt.Key.Key_PageDown:
            assert current_outer_value > previous_outer_value, geometry_state
        else:
            assert current_outer_value < previous_outer_value, geometry_state

    mapped_last_line = mapped_line()
    assert (
        mapped_last_line.top() >= outer_rect.top()
        and mapped_last_line.bottom() <= outer_rect.bottom()
    ), geometry_state


def _assert_comparison_dialog_narrow_and_scrollable(
    app: QApplication,
    view: QWidget,
) -> None:
    """檢查比較對話框可維持窄寬，並能逐檔捲動看到末行。"""

    dialog = view._comparison_dialog  # type: ignore[attr-defined]
    assert isinstance(dialog, QDialog) and dialog.isVisible()
    dialog.resize(460, 700)
    app.processEvents()
    assert dialog.width() == 460
    scroll = dialog.findChild(QScrollArea)
    assert scroll is not None and scroll.isVisible()
    assert scroll.width() <= dialog.width()
    assert scroll.viewport().width() > 0
    columns = scroll.widget()
    assert columns is not None
    groups = columns.findChildren(QGroupBox)
    assert len(groups) == 2
    close_button = next(
        (button for button in dialog.findChildren(QPushButton)
         if button.text() == "關閉比較，返回原結果"),
        None,
    )
    assert close_button is not None and close_button.isVisible()
    close_position = close_button.mapTo(dialog, QPoint(0, 0))
    assert dialog.rect().contains(close_position)
    assert dialog.rect().contains(
        close_position + QPoint(close_button.width() - 1, close_button.height() - 1)
    )
    for group in groups:
        scroll.ensureWidgetVisible(group, 0, 0)
        app.processEvents()
        position = group.mapTo(scroll.viewport(), QPoint(0, 0))
        group_rect = group.rect().translated(position)
        assert group_rect.intersects(scroll.viewport().rect())
        editor = group.findChild(QPlainTextEdit)
        assert editor is not None and editor.isReadOnly()
        _scroll_editor_to_last_line(app, scroll, editor)
    QTest.mouseClick(
        close_button,
        Qt.MouseButton.LeftButton,
        pos=close_button.rect().center(),
    )
    app.processEvents()
    assert not dialog.isVisible()


def _click_stock_code(app: QApplication, view: object, stock_code: str) -> None:
    """以 Qt 真實滑鼠事件選取目前頁面上的指定列。"""

    index = view.results_model.index_for_stock(stock_code)
    assert index.isValid()
    view.page_scroll.ensureWidgetVisible(view.results_table)
    view.results_table.scrollTo(
        index,
        QAbstractItemView.ScrollHint.PositionAtCenter,
    )
    app.processEvents()
    rect = view.results_table.visualRect(index)
    assert rect.isValid() and view.results_table.viewport().rect().contains(rect.center())
    QTest.mouseClick(
        view.results_table.viewport(),
        Qt.MouseButton.LeftButton,
        pos=rect.center(),
    )
    app.processEvents()
    assert view._selected_row is not None
    assert view._selected_row.stock_code == stock_code


def test_view_constructor_and_busy_restore_need_no_source_producer(app: QApplication) -> None:
    """無來源建構成功，且背景工作結束後恢復股票代碼固定升冪。"""

    view_type = DailyMarketTechnicalOfficialDispositionCompositeView
    view = view_type()
    view.resize(460, 700)
    view.show()
    app.processEvents()
    try:
        _assert_every_stack_page_fits(view, app)
        outer_filters = view.filter_panel.findChild(QGroupBox, "compositeOuterFilters")
        assert outer_filters is not None
        assert outer_filters.minimumSizeHint().width() <= view.page_scroll.viewport().width()
        assert view.current_result is None
        assert view.active_worker is None
        assert view.stock_code_input is not None
        assert not view.stock_code_input.isEnabled()
        view.stock_filter_enabled.setChecked(True)
        assert view.stock_code_input.isEnabled()

        view.sort_field_box.setCurrentIndex(view.sort_field_box.findData("stock_code"))
        view.sort_direction_box.setCurrentIndex(view.sort_direction_box.findData("desc"))
        assert not view.sort_direction_box.isEnabled()
        view._set_controls_busy(True)
        assert not view.sort_direction_box.isEnabled()
        view._set_controls_busy(False)
        assert not view.sort_direction_box.isEnabled()
        assert view.sort_direction_box.currentData() == "asc"
    finally:
        _close_view_and_wait_for_native_workers(app, view)


def test_filled_readonly_reason_panels_scroll_without_a_source_producer(
    app: QApplication,
    tmp_path: Path,
) -> None:
    """在載入任何來源前，以長唯讀原因與稽核文字驗證窄窗捲動。"""

    view_type = DailyMarketTechnicalOfficialDispositionCompositeView
    view = view_type(tmp_path)
    view.resize(460, 700)
    view.show()
    app.processEvents()
    try:
        reasons = "\n".join(
            f"保存理由第 {index:03d} 行：這段文字用來驗證窄視窗下完整呈現與鍵盤捲動。"
            + ("風險說明及來源可得時間仍須逐行保留。" * 5)
            for index in range(1, 81)
        )
        audit = "\n".join(
            f'  "audit_field_{index:03d}": "保存事實與未知狀態 {index:03d}",'
            for index in range(1, 161)
        )
        view.detail_text.setPlainText(reasons)
        view.audit_text.setPlainText("{\n" + audit + "\n}")
        view.results_stack.setCurrentIndex(1)
        app.processEvents()
        _assert_narrow_controls(view)
        _assert_every_stack_page_fits(view, app)
        assert view.results_stack.currentIndex() == 1
        _scroll_editor_to_last_line(app, view.page_scroll, view.detail_text)
        _scroll_editor_to_last_line(app, view.page_scroll, view.audit_text)
        assert view.detail_text.toPlainText().splitlines()[-1].endswith("。")
        assert view.audit_text.toPlainText().rstrip().endswith("}")
    finally:
        _close_view_and_wait_for_native_workers(app, view)
        app.processEvents()


def test_compare_dialog_close_restores_visible_readonly_editor_focus(
    app: QApplication,
    tmp_path: Path,
) -> None:
    """關閉同類比較視窗後，可點擊並捲動唯讀詳情至最後一行。"""

    view_type = DailyMarketTechnicalOfficialDispositionCompositeView
    view = view_type(tmp_path)
    view.resize(460, 700)
    view.show()
    app.processEvents()
    dialog = QDialog(view)
    dialog.setWindowTitle("同來源複合研究保存事實比較")
    dialog.resize(460, 300)
    close_button = QPushButton("關閉比較，返回原結果", dialog)
    close_button.clicked.connect(dialog.accept)
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    app.processEvents()
    try:
        assert view.isVisible() and dialog.isVisible()
        assert QApplication.activeWindow() is dialog
        view.detail_text.setPlainText(
            "\n".join(
                f"比較關閉後仍可閱讀的完整保存理由第 {line:03d} 行。"
                for line in range(1, 81)
            )
        )
        view.results_stack.setCurrentIndex(1)
        app.processEvents()
        QTest.mouseClick(
            close_button,
            Qt.MouseButton.LeftButton,
            pos=close_button.rect().center(),
        )
        app.processEvents()
        assert not dialog.isVisible()
        assert view.isVisible()
        _assert_narrow_controls(view)
        _scroll_editor_to_last_line(app, view.page_scroll, view.detail_text)
        assert view.detail_text.toPlainText().splitlines()[-1].endswith("080 行。")
    finally:
        dialog.close()
        _close_view_and_wait_for_native_workers(app, view)
        app.processEvents()


def test_real_bundle_narrow_window_scroll_and_cross_page_return_keep_exact_state(
    app: QApplication,
    bundle_fixture: _BundleFixture,
) -> None:
    """重用 full257 fixture；驗真 Qt opener、窄窗詳情與跨頁回返。"""

    view_type = DailyMarketTechnicalOfficialDispositionCompositeView
    view = view_type(bundle_fixture.bundle_root)
    view.resize(460, 700)
    view.show()
    app.processEvents()
    events: list[tuple[str, bool]] = []
    view.operationSettled.connect(lambda kind, success: events.append((kind, success)))
    try:
        labels = [label.text() for label in view.findChildren(QLabel)]
        assert "官方市場狀態與技術條件研究" in labels
        assert any(
            "研究用途" in text and "官方資料可得時間未知" in text and "PIT 資格" in text
            for text in labels
        )
        exact_root = bundle_fixture.bundle_root
        assert view.bundle_output_root == exact_root
        assert view.root_label.text() == "已選擇保存來源資料夾（完整路徑可停留查看）"
        assert view.root_label.toolTip() == f"完整保存來源路徑：\n{exact_root}"
        assert view.root_label.accessibleDescription() == f"完整保存來源路徑：{exact_root}"
        body = view.page_scroll.widget()
        assert body is not None
        _assert_narrow_controls(view)
        for control in (
            view.next_catalog_button,
            view.sort_direction_box,
            view.page_size_box,
            view.bookmark_button,
        ):
            position = control.mapTo(body, QPoint(0, 0))
            assert position.x() >= 0
            assert position.x() + control.width() <= body.width()

        previous = len(events)
        view.refresh_catalog()
        kind, succeeded = _wait_for_settled(app, events, previous)
        assert kind == "盤點已保存來源清單" and succeeded
        assert view.catalog_list.count() == 1
        catalog_item = view.catalog_list.item(0)
        assert catalog_item is not None
        catalog_rect = view.catalog_list.visualItemRect(catalog_item)
        assert catalog_rect.isValid() and view.catalog_list.viewport().rect().contains(
            catalog_rect.center()
        )
        QTest.mouseClick(
            view.catalog_list.viewport(),
            Qt.MouseButton.LeftButton,
            pos=catalog_rect.center(),
        )
        app.processEvents()
        assert view.catalog_list.currentRow() == 0
        view.page_size_box.setValue(256)
        for scope, check in view.scope_checks.items():
            check.setChecked(scope == "included_processed")

        previous = len(events)
        view.open_selected_candidate()
        kind, succeeded = _wait_for_settled(app, events, previous)
        assert kind == "精確核驗並執行全母體複合查詢" and succeeded
        _assert_narrow_controls(view)
        _assert_every_stack_page_fits(view, app)
        result = view.current_result
        first_page = view.current_page
        assert result is not None and first_page is not None
        population = result.counts.base_f17_counts.population
        assert (
            population.declared_count,
            population.included_count,
            population.processed_count,
            population.excluded_count,
            population.pending_count,
        ) == (258, 257, 257, 1, 0)
        assert result.visible_count == 257
        assert first_page.page_size == 256 and first_page.page_count == 2
        assert len(first_page.rows) == 256
        assert tuple(row.stock_code for row in first_page.rows) == bundle_fixture.included_codes[:256]
        assert "本頁 256 列" in view.page_label.text()
        assert "全域可見 257 列" in view.page_label.text()

        first_code = first_page.rows[0].stock_code
        _click_stock_code(app, view, first_code)
        view.add_comparison_button.click()
        assert tuple(item.selection.stock_code for item in view._basket) == (first_code,)

        # 先以真 reader 的第一頁列驗證推薦理由、保存事實和風險說明可以捲到末行。
        view.detail_button.click()
        app.processEvents()
        assert view.results_stack.currentIndex() == 1
        _assert_narrow_controls(view)
        _assert_every_stack_page_fits(view, app)
        assert "historical PIT 不適用" in view.detail_text.toPlainText()
        _scroll_editor_to_last_line(app, view.page_scroll, view.detail_text)
        _scroll_editor_to_last_line(app, view.page_scroll, view.audit_text)
        assert view.audit_text.toPlainText().rstrip().endswith("}")
        view.back_button.click()
        app.processEvents()
        assert view.results_stack.currentIndex() == 0
        assert view.current_page is first_page
        assert view._selected_row is not None and view._selected_row.stock_code == first_code
        _assert_narrow_controls(view)

        # 翻到下一頁後選列下鑽，再返回時保留原 query、排序、頁請求、捲動和 basket。
        previous = len(events)
        view.next_page_button.click()
        kind, succeeded = _wait_for_settled(app, events, previous)
        assert kind == "讀取全域排序結果的指定頁" and succeeded
        _assert_narrow_controls(view)
        _assert_every_stack_page_fits(view, app)
        second_page = view.current_page
        assert second_page is not None and second_page.page_index == 1
        assert len(second_page.rows) == 1
        assert second_page.rows[0].stock_code == bundle_fixture.included_codes[-1]
        assert "本頁 1 列" in view.page_label.text()
        assert "全域可見 257 列" in view.page_label.text()
        result = view.current_result
        assert result is not None
        selected_code = second_page.rows[0].stock_code
        _click_stock_code(app, view, selected_code)
        view.add_comparison_button.click()
        assert tuple(item.selection.stock_code for item in view._basket) == (
            first_code,
            selected_code,
        )
        assert view.compare_button.isVisible() and view.compare_button.isEnabled()
        QTest.mouseClick(
            view.compare_button,
            Qt.MouseButton.LeftButton,
            pos=view.compare_button.rect().center(),
        )
        app.processEvents()
        _assert_comparison_dialog_narrow_and_scrollable(app, view)
        _assert_narrow_controls(view)
        bar = view.page_scroll.verticalScrollBar()
        assert bar.maximum() > 0
        bar.setValue(min(83, bar.maximum()))
        app.processEvents()
        original_scroll = bar.value()
        original_result = view.current_result
        original_page = view.current_page
        original_request_identity = view._page_request.request_identity_sha256
        original_query_json = result.query.to_json()
        original_query_identity = result.query.query_identity_sha256
        original_source = view._source
        original_filters = _filter_state(view)
        original_basket = tuple(item.selection.stock_code for item in view._basket)
        original_row = view._selected_row
        original_row_identity = original_row.row_identity_sha256
        assert original_source is not None

        view.detail_button.click()
        app.processEvents()
        assert view.results_stack.currentIndex() == 1
        _assert_narrow_controls(view)
        _assert_every_stack_page_fits(view, app)
        _scroll_editor_to_last_line(app, view.page_scroll, view.detail_text)
        _scroll_editor_to_last_line(app, view.page_scroll, view.audit_text)
        view.back_button.click()
        app.processEvents()

        assert view.results_stack.currentIndex() == 0
        assert view.current_result is original_result
        assert view.current_page is original_page
        assert view.current_page.page_index == 1
        assert view._page_request.request_identity_sha256 == original_request_identity
        assert view.current_result.query.query_identity_sha256 == original_query_identity
        assert view.current_result.query.to_json() == original_query_json
        assert view._source == original_source
        assert _filter_state(view) == original_filters
        assert tuple(item.selection.stock_code for item in view._basket) == original_basket
        assert view._selected_row is original_row
        assert view._selected_row.row_identity_sha256 == original_row_identity
        assert view.page_scroll.verticalScrollBar().value() == original_scroll
    finally:
        _close_view_and_wait_for_native_workers(app, view)
        app.processEvents()
