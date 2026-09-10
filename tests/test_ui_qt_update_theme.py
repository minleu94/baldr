import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QGroupBox, QPushButton

from tests.test_ui_qt_update_view_workbench import FakeUpdateService
from ui_qt.main import apply_app_theme
from ui_qt.views.update_view import UpdateView


def _app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    apply_app_theme(instance)
    return instance


def test_update_view_subpages_use_shared_theme_roles_instead_of_local_light_styles():
    _app()
    view = UpdateView(FakeUpdateService())

    assert view.nav_list.objectName() == "updateNavigation"
    assert view.quick_update_all_btn.property("variant") == "secondary"
    assert view.safe_update_all_btn.property("variant") == "primary"
    assert view.check_status_btn.property("variant") == "ghost"

    groups = view.findChildren(QGroupBox)
    assert groups
    assert all(group.styleSheet() == "" for group in groups)
    assert all(group.property("sectionTone") is not None for group in groups)

    buttons = view.findChildren(QPushButton)
    assert all(
        light_token not in button.styleSheet()
        for button in buttons
        for light_token in ("#f8fafc", "#f1f5f9", "#e2e8f0", "#ffffff")
    )
    view.close()
