from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QToolButton

from ui_qt.widgets.theme_widgets import CollapsibleSectionPanel


def _app() -> QApplication:
    instance = QApplication.instance()
    return instance if isinstance(instance, QApplication) else QApplication(sys.argv)


def test_collapsible_panel_uses_inline_heading_and_directional_compact_toggle() -> None:
    application = _app()
    panel = CollapsibleSectionPanel("證據與來源追蹤", collapsed=True)
    try:
        toggle = panel.toggle_button
        assert isinstance(toggle, QToolButton)
        assert panel.is_collapsed()
        assert panel.content_widget.isHidden()
        assert toggle.text() == "展開"
        assert toggle.arrowType() == Qt.ArrowType.RightArrow
        assert not toggle.isChecked()
        assert toggle.autoRaise()
        assert toggle.accessibleName() == "展開證據與來源追蹤"
        assert "證據與來源追蹤" in toggle.toolTip()
        assert toggle.sizeHint().width() < 100
        assert toggle.sizeHint().height() < 40
        assert ":hover" in toggle.styleSheet()
        assert ":pressed" in toggle.styleSheet()
        assert ":focus" in toggle.styleSheet()
        assert "background:" not in panel.title_label.styleSheet()

        toggle.click()

        assert not panel.is_collapsed()
        assert not panel.content_widget.isHidden()
        assert toggle.text() == "收合"
        assert toggle.arrowType() == Qt.ArrowType.DownArrow
        assert toggle.isChecked()
        assert toggle.accessibleName() == "收合證據與來源追蹤"
    finally:
        panel.close()
        application.processEvents()


def test_collapsible_panel_updates_call_site_accessible_action_name() -> None:
    application = _app()
    panel = CollapsibleSectionPanel("完整工作台", collapsed=True)
    try:
        panel.toggle_button.setAccessibleName("展開完整工作台與原始來源")
        panel.toggle_button.click()
        assert panel.toggle_button.accessibleName() == "收合完整工作台與原始來源"
    finally:
        panel.close()
        application.processEvents()
