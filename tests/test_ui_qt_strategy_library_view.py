from __future__ import annotations

import sys

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from decision_module.strategies import StrategyRegistry
from ui_qt.views.strategy_library_view import StrategyLibraryView


class _VersionReader:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.read_calls = []
        self.write_calls = 0

    def list_versions(self, strategy_id):
        self.read_calls.append(strategy_id)
        return [row for row in self.rows if row.get("strategy_id") == strategy_id]

    def create_version(self, *_args, **_kwargs):
        self.write_calls += 1


def _app():
    app = QApplication.instance()
    return app if app is not None else QApplication(sys.argv)


@pytest.fixture
def qt_driver():
    app = _app()

    class Driver:
        def __init__(self):
            self.widgets = []

        def addWidget(self, widget):
            self.widgets.append(widget)

    driver = Driver()
    yield driver
    for widget in reversed(driver.widgets):
        widget.close()
        widget.deleteLater()
    app.processEvents()


def _select_strategy(view, strategy_id):
    for index in range(view.strategy_list.count()):
        item = view.strategy_list.item(index)
        if item.data(Qt.ItemDataRole.UserRole) == strategy_id:
            view.strategy_list.setCurrentItem(item)
            return item
    raise AssertionError(f"策略未列出：{strategy_id}")


def test_real_registry_metadata_is_rendered_without_engine_or_writer_calls(qt_driver):
    service = _VersionReader()
    view = StrategyLibraryView(StrategyRegistry, service)
    qt_driver.addWidget(view)

    assert view.reload()
    _select_strategy(view, "baldr_bollinger_basic_v1")

    assert view.detail_labels["strategy_id"].text() == "baldr_bollinger_basic_v1"
    assert view.detail_labels["description"].text() != "未提供"
    assert view.detail_labels["qualification"].text() == "未提供"
    assert view.detail_labels["cost"].text() == "未提供"
    assert view.select_button.isEnabled()
    assert service.write_calls == 0


def test_select_emits_exact_registered_identity_and_never_runs_query(qt_driver):
    service = _VersionReader()
    view = StrategyLibraryView(StrategyRegistry, service)
    qt_driver.addWidget(view)
    emitted = []
    view.strategySelected.connect(lambda strategy_id, version: emitted.append((strategy_id, version)))
    _select_strategy(view, "baldr_bollinger_basic_v1")

    choice = view.version_combo.itemData(view.version_combo.currentIndex())
    view.select_button.click()

    assert emitted == [("baldr_bollinger_basic_v1", "1.0.0")]
    assert choice.version == "1.0.0"
    assert service.read_calls
    assert service.write_calls == 0


def test_missing_registry_version_is_visible_but_cannot_be_applied(qt_driver):
    service = _VersionReader([{
        "version_id": "saved_missing_registry",
        "strategy_id": "baldr_bollinger_basic_v1",
        "strategy_version": "9.9.9",
        "validation_status": "validated",
        "source_run_id": "run-1",
    }])
    view = StrategyLibraryView(StrategyRegistry, service)
    qt_driver.addWidget(view)
    _select_strategy(view, "baldr_bollinger_basic_v1")
    index = next(
        i for i in range(view.version_combo.count())
        if "9.9.9" in view.version_combo.itemText(i)
    )
    view.version_combo.setCurrentIndex(index)

    assert not view.select_button.isEnabled()
    assert "未提供" == view.detail_labels["qualification"].text()
    assert view.detail_labels["validation_status"].text() == "validated"
    assert "無法套用" in view.select_button.toolTip()
    assert service.write_calls == 0


def test_search_keeps_selected_strategy_source_identity(qt_driver):
    view = StrategyLibraryView(StrategyRegistry, _VersionReader())
    qt_driver.addWidget(view)
    item = _select_strategy(view, "baldr_bollinger_basic_v1")

    view.search_edit.setText("no matching strategy")

    assert item.isHidden()
    assert view._selected_strategy_id == "baldr_bollinger_basic_v1"
    assert view.detail_labels["strategy_id"].text() == "baldr_bollinger_basic_v1"
