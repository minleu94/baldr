from __future__ import annotations

import sys

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QToolButton, QVBoxLayout, QWidget

from ui_qt.views.stock_lookup_landing import StockLookupLanding
from ui_qt.widgets.global_search_bar import GlobalSearchBar
from ui_qt.widgets.workspace_subnav import WorkspaceSubnav


@pytest.fixture
def app() -> QApplication:
    instance = QApplication.instance()
    return instance if instance is not None else QApplication(sys.argv)


def test_workspace_subnav_emits_only_when_route_changes(app: QApplication) -> None:
    subnav = WorkspaceSubnav()
    emitted: list[str] = []
    subnav.routeSelected.connect(emitted.append)
    subnav.set_routes((("overview", "總覽"), ("detail", "明細")))

    assert subnav.current_route == "overview"
    detail_button = subnav.findChild(QToolButton, "WorkspaceSubnavRoute_detail")
    assert detail_button is not None
    detail_button.click()
    detail_button.click()

    assert subnav.current_route == "detail"
    assert emitted == ["detail"]
    subnav.set_current_route("overview")
    assert emitted == ["detail"]


def test_workspace_subnav_rejects_more_than_four_routes(app: QApplication) -> None:
    subnav = WorkspaceSubnav()

    with pytest.raises(ValueError):
        subnav.set_routes(tuple((f"route-{index}", f"頁面 {index}") for index in range(5)))


def test_workspace_subnav_tab_entry_and_reverse_return(app: QApplication) -> None:
    host = QWidget()
    layout = QVBoxLayout(host)
    predecessor = QPushButton("搜尋", host)
    subnav = WorkspaceSubnav(host)
    layout.addWidget(predecessor)
    layout.addWidget(subnav)
    subnav.set_routes((("overview", "總覽"), ("detail", "明細")))
    subnav.set_tab_predecessor(predecessor)
    host.show()
    app.processEvents()

    current = subnav._buttons["overview"]
    other = subnav._buttons["detail"]
    assert current.focusPolicy() == Qt.FocusPolicy.TabFocus
    assert other.focusPolicy() == Qt.FocusPolicy.NoFocus

    predecessor.setFocus()
    QTest.keyClick(predecessor, Qt.Key.Key_Tab)
    app.processEvents()
    assert QApplication.focusWidget() is current

    QTest.keyClick(current, Qt.Key.Key_Tab, Qt.KeyboardModifier.ShiftModifier)
    app.processEvents()
    assert QApplication.focusWidget() is predecessor
    host.close()


def test_workspace_subnav_rebuild_and_programmatic_route_rewire_tab_order(app: QApplication) -> None:
    host = QWidget()
    layout = QVBoxLayout(host)
    predecessor = QPushButton("搜尋", host)
    subnav = WorkspaceSubnav(host)
    layout.addWidget(predecessor)
    layout.addWidget(subnav)
    emitted: list[str] = []
    subnav.routeSelected.connect(emitted.append)
    subnav.set_tab_predecessor(predecessor)
    subnav.set_routes((("overview", "總覽"), ("detail", "明細")))
    subnav.set_current_route("detail")
    assert subnav._buttons["detail"].focusPolicy() == Qt.FocusPolicy.TabFocus
    assert subnav._buttons["overview"].focusPolicy() == Qt.FocusPolicy.NoFocus
    assert emitted == []

    subnav.set_routes((("detail", "明細"), ("history", "歷史")))
    host.show()
    app.processEvents()
    current = subnav._buttons["detail"]
    assert current.focusPolicy() == Qt.FocusPolicy.TabFocus
    predecessor.setFocus()
    QTest.keyClick(predecessor, Qt.Key.Key_Tab)
    app.processEvents()
    assert QApplication.focusWidget() is current
    assert emitted == []
    host.close()


def test_workspace_subnav_does_not_promote_disabled_current_route(app: QApplication) -> None:
    subnav = WorkspaceSubnav()
    subnav.set_routes((("overview", "總覽"), ("detail", "明細")))
    disabled = subnav._buttons["overview"]
    disabled.setEnabled(False)
    subnav.set_current_route("overview")

    assert not disabled.isEnabled()
    assert disabled.focusPolicy() == Qt.FocusPolicy.NoFocus
    assert subnav._buttons["detail"].focusPolicy() == Qt.FocusPolicy.NoFocus
    assert disabled.isChecked()


def test_global_search_bar_ignores_blank_query_and_emits_original_text(app: QApplication) -> None:
    search_bar = GlobalSearchBar()
    emitted: list[str] = []
    search_bar.searchRequested.connect(emitted.append)

    search_bar.search_edit.setText("   \t")
    search_bar.search_button.click()
    assert emitted == []

    original_query = "  2330 台積電  "
    search_bar.search_edit.setText(original_query)
    search_bar.search_edit.returnPressed.emit()

    assert emitted == [original_query]


def test_global_search_bar_exposes_context_and_focus_entrypoint(app: QApplication) -> None:
    search_bar = GlobalSearchBar()
    assert search_bar.context_label.text() == "各資料域日期依頁面標示"
    search_bar.set_context_label("行情資料截至 2026-10-20")
    assert search_bar.context_label.text() == "行情資料截至 2026-10-20"

    search_bar.show()
    search_bar.focus_search()
    app.processEvents()
    assert search_bar.search_edit.hasFocus()


def test_stock_lookup_landing_submits_only_nonempty_trimmed_query(app: QApplication) -> None:
    landing = StockLookupLanding()
    emitted: list[str] = []
    landing.searchRequested.connect(emitted.append)

    landing.query_edit.setText("  \t  ")
    landing.submit_button.click()
    assert emitted == []

    landing.query_edit.setText("  台積電  ")
    landing.query_edit.returnPressed.emit()
    assert emitted == ["台積電"]
