from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFont
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QListWidget, QListWidgetItem

from ui_qt.theme.fonts import preferred_qt_chinese_font_family, register_qt_chinese_fonts
from ui_qt.theme.qss import build_global_stylesheet
from ui_qt.widgets.layout_helpers import _CONTROLLER_ATTRIBUTE, ensure_visible_rows


def _app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def test_wrapped_list_rows_use_actual_visual_height_for_five_row_viewport() -> None:
    app = _app()
    items = QListWidget()
    try:
        families = register_qt_chinese_fonts()
        font_family = preferred_qt_chinese_font_family(families) or app.font().family()
        items.setFont(QFont(font_family, 9))
        items.setStyleSheet(build_global_stylesheet())
        items.setWordWrap(True)
        items.setUniformItemSizes(False)
        items.setSpacing(2)
        items.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        items.resize(260, 180)
        items.show()
        app.processEvents()
        initial_height = ensure_visible_rows(items, 5)
        controller = getattr(items, _CONTROLLER_ATTRIBUTE)
        original_measure = controller.measure_and_apply
        measure_count = 0

        def counted_measure() -> int:
            nonlocal measure_count
            measure_count += 1
            return original_measure()

        controller.measure_and_apply = counted_measure

        for row in range(6):
            label = (
                f"第 {row + 1} 筆長標籤，包含研究內容、來源識別與詳細說明，"
                "在窄視窗需要換成多行才能完整閱讀。"
            ) * 3
            items.addItem(QListWidgetItem(label))

        # 由 model rowsInserted／layout 事件自動重算；此處不再手動呼叫 helper。
        app.processEvents()
        QTest.qWait(200)
        settled_count = measure_count
        QTest.qWait(200)
        assert measure_count == settled_count
        items.verticalScrollBar().setValue(0)
        app.processEvents()

        first_five = [items.visualItemRect(items.item(row)) for row in range(5)]
        hints = [items.sizeHintForRow(row) for row in range(5)]

        assert items.minimumHeight() > initial_height
        assert first_five[0].height() > max(hints)
        assert all(rect.isValid() for rect in first_five)
        assert all(rect.top() >= 0 for rect in first_five)
        assert first_five[-1].bottom() < items.viewport().height()

        previous_count = measure_count
        previous_minimum = items.minimumHeight()
        items.resize(220, 180)
        app.processEvents()
        QTest.qWait(100)
        assert measure_count > previous_count
        assert items.minimumHeight() >= previous_minimum
        assert items.visualItemRect(items.item(4)).bottom() < items.viewport().height()

        previous_count = measure_count
        larger_font = QFont(items.font())
        larger_font.setPointSize(11)
        items.setFont(larger_font)
        app.processEvents()
        QTest.qWait(100)
        assert measure_count > previous_count
        assert items.visualItemRect(items.item(4)).bottom() < items.viewport().height()

        settled_count = measure_count
        QTest.qWait(200)
        assert measure_count == settled_count
    finally:
        items.close()
        items.deleteLater()
        app.processEvents()
