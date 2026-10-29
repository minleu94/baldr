from __future__ import annotations

import sys
import time
from threading import Event, get_ident

import pytest
from PySide6.QtCore import Qt, QTimer
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


class _SyntheticRegistry:
    _strategies = {
        "strategy_alpha": {
            "strategy_id": "strategy_alpha",
            "name": "Alpha",
            "strategy_version": "1.0.0",
        },
        "strategy_beta": {
            "strategy_id": "strategy_beta",
            "name": "Beta",
            "strategy_version": "2.0.0",
        },
    }

    @classmethod
    def list_strategies(cls):
        return {key: dict(value) for key, value in cls._strategies.items()}

    @classmethod
    def get_strategy_meta(cls, strategy_id, version=None):
        base = cls._strategies.get(strategy_id)
        if base is None:
            return None
        result = dict(base)
        if version is not None:
            result["strategy_version"] = version
            result["version"] = version
        return result


class _BlockingVersionReader(_VersionReader):
    def __init__(self, rows=None):
        super().__init__(rows)
        self.entered = Event()
        self.release = Event()
        self.thread_ident = None

    def list_versions(self, strategy_id):
        self.read_calls.append(strategy_id)
        self.thread_ident = get_ident()
        self.entered.set()
        if not self.release.wait(timeout=5):
            raise RuntimeError("synthetic reader was not released")
        return [row for row in self.rows if row.get("strategy_id") == strategy_id]


class _FirstCallBlockingVersionReader(_VersionReader):
    def __init__(self, rows_by_strategy):
        super().__init__()
        self.rows_by_strategy = rows_by_strategy
        self.first_entered = Event()
        self.release_first = Event()
        self.second_entered = Event()

    def list_versions(self, strategy_id):
        call_number = len(self.read_calls)
        self.read_calls.append(strategy_id)
        if call_number == 0:
            self.first_entered.set()
            if not self.release_first.wait(timeout=5):
                raise RuntimeError("first synthetic reader call was not released")
        elif call_number == 1:
            self.second_entered.set()
        return list(self.rows_by_strategy.get(strategy_id, []))


class _ErrorVersionReader(_VersionReader):
    def list_versions(self, strategy_id):
        self.read_calls.append(strategy_id)
        raise RuntimeError("synthetic saved-version read failure")


class _FailThenSucceedVersionReader(_VersionReader):
    def list_versions(self, strategy_id):
        self.read_calls.append(strategy_id)
        if len(self.read_calls) == 1:
            raise RuntimeError("temporary saved-version read failure")
        return [{
            "version_id": "saved-after-retry",
            "strategy_id": strategy_id,
            "strategy_version": "1.5.0",
            "source_run_id": "run-after-retry",
        }]


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


def _wait_until(app, predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    app.processEvents()
    return bool(predicate())


def _wait_for_version_load(view, app):
    return _wait_until(
        app,
        lambda: view._version_load_worker is None
        and not view.version_status_label.text().startswith("讀取保存版本中"),
    )


def test_real_registry_metadata_is_rendered_without_engine_or_writer_calls(qt_driver):
    app = _app()
    service = _VersionReader()
    view = StrategyLibraryView(StrategyRegistry, service)
    qt_driver.addWidget(view)

    assert view.reload()
    assert _wait_for_version_load(view, app)
    _select_strategy(view, "baldr_bollinger_basic_v1")
    assert _wait_for_version_load(view, app)

    assert view.detail_labels["strategy_id"].text() == "baldr_bollinger_basic_v1"
    assert view.detail_labels["description"].text() != "未提供"
    assert view.detail_labels["qualification"].text() == "未提供"
    assert view.detail_labels["cost"].text() == "未提供"
    assert view.select_button.isEnabled()
    assert service.write_calls == 0
    assert view.advanced_details.is_collapsed()
    original_parameters = view.detail_labels["parameter_schema"].text()
    view.advanced_details.toggle_button.click()
    assert not view.advanced_details.is_collapsed()
    assert view.detail_labels["parameter_schema"].text() == original_parameters


def test_strategy_details_group_qualifications_and_keep_apply_action_visible(qt_driver):
    app = _app()
    view = StrategyLibraryView(_SyntheticRegistry, _VersionReader())
    qt_driver.addWidget(view)
    view.resize(900, 620)
    view.show()
    app.processEvents()

    assert view.strategy_content_group.title() == "策略內容與風險"
    assert view.qualification_group.title() == "資料與資格判讀"
    assert view.strategy_detail_scroll.isAncestorOf(
        view.detail_labels["qualification"]
    )
    assert not view.strategy_detail_scroll.isAncestorOf(view.select_button)
    assert view.select_button.isVisible()


def test_select_emits_exact_registered_identity_and_never_runs_query(qt_driver):
    app = _app()
    service = _VersionReader()
    view = StrategyLibraryView(StrategyRegistry, service)
    qt_driver.addWidget(view)
    assert _wait_for_version_load(view, app)
    emitted = []
    view.strategySelected.connect(lambda strategy_id, version: emitted.append((strategy_id, version)))
    _select_strategy(view, "baldr_bollinger_basic_v1")
    assert _wait_for_version_load(view, app)

    choice = view.version_combo.itemData(view.version_combo.currentIndex())
    view.select_button.click()

    assert emitted == [("baldr_bollinger_basic_v1", "1.0.0")]
    assert choice.version == "1.0.0"
    assert service.read_calls
    assert service.write_calls == 0


def test_missing_registry_version_is_visible_but_cannot_be_applied(qt_driver):
    app = _app()
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
    assert _wait_for_version_load(view, app)
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
    app = _app()
    view = StrategyLibraryView(StrategyRegistry, _VersionReader())
    qt_driver.addWidget(view)
    assert _wait_for_version_load(view, app)
    item = _select_strategy(view, "baldr_bollinger_basic_v1")
    assert _wait_for_version_load(view, app)

    view.search_edit.setText("no matching strategy")

    assert item.isHidden()
    assert view._selected_strategy_id == "baldr_bollinger_basic_v1"
    assert view.detail_labels["strategy_id"].text() == "baldr_bollinger_basic_v1"


def test_blocking_saved_version_read_keeps_gui_event_loop_responsive(qt_driver):
    app = _app()
    service = _BlockingVersionReader()
    view = StrategyLibraryView(_SyntheticRegistry, service)
    qt_driver.addWidget(view)
    try:
        assert service.entered.wait(timeout=2)
        assert view.version_status_label.text() == "讀取保存版本中…"
        assert view.version_combo.isEnabled() is False
        assert view.select_button.isEnabled() is False

        callback_ran = []
        QTimer.singleShot(0, lambda: callback_ran.append(True))
        app.processEvents()
        assert callback_ran == [True]
        assert service.thread_ident != get_ident()
    finally:
        service.release.set()
        assert _wait_for_version_load(view, app)


def test_rapid_strategy_switch_ignores_old_reply_and_serializes_reads(qt_driver):
    app = _app()
    rows = {
        "strategy_alpha": [{
            "version_id": "saved-alpha",
            "strategy_id": "strategy_alpha",
            "strategy_version": "1.1.0",
            "source_run_id": "run-alpha",
        }],
        "strategy_beta": [{
            "version_id": "saved-beta",
            "strategy_id": "strategy_beta",
            "strategy_version": "2.1.0",
            "source_run_id": "run-beta",
        }],
    }
    service = _FirstCallBlockingVersionReader(rows)
    view = StrategyLibraryView(_SyntheticRegistry, service)
    qt_driver.addWidget(view)
    try:
        assert service.first_entered.wait(timeout=2)
        _select_strategy(view, "strategy_beta")
        app.processEvents()

        assert service.read_calls == ["strategy_alpha"]
        assert view._selected_strategy_id == "strategy_beta"
        assert view.version_status_label.text() == "讀取保存版本中…"
        assert view.version_combo.isEnabled() is False

        service.release_first.set()
        assert _wait_until(app, service.second_entered.is_set, timeout=2.0)
        assert _wait_for_version_load(view, app)

        assert service.read_calls == ["strategy_alpha", "strategy_beta"]
        assert view._selected_strategy_id == "strategy_beta"
        assert view.detail_labels["strategy_id"].text() == "strategy_beta"
        saved_index = next(
            index
            for index in range(view.version_combo.count())
            if view.version_combo.itemData(index).version == "2.1.0"
        )
        view.version_combo.setCurrentIndex(saved_index)
        assert "saved-beta" in view.detail_labels["source_identity"].text()
        assert "run-beta" in view.detail_labels["source_identity"].text()
        assert "saved-alpha" not in view.detail_labels["source_identity"].text()
    finally:
        service.release_first.set()
        _wait_for_version_load(view, app)


def test_saved_version_error_falls_back_to_registered_metadata(qt_driver):
    app = _app()
    service = _ErrorVersionReader()
    view = StrategyLibraryView(_SyntheticRegistry, service)
    qt_driver.addWidget(view)

    assert _wait_for_version_load(view, app)
    assert service.read_calls == ["strategy_alpha"]
    assert view.version_combo.count() == 1
    assert view.version_combo.currentText() == "版本 1.0.0"
    assert view.detail_labels["strategy_id"].text() == "strategy_alpha"
    assert view.select_button.isEnabled()
    assert "保存版本來源不可用" in view.version_status_label.text()
    assert "synthetic saved-version read failure" in view.version_status_label.toolTip()
    assert not view.retry_versions_button.isHidden()
    assert view.retry_versions_button.isEnabled()


@pytest.mark.parametrize(
    ("version_service", "reason"),
    ((None, "保存版本來源未提供"), (object(), "未提供讀取方法")),
)
def test_retry_is_hidden_when_saved_version_reader_is_not_available(
    qt_driver, version_service, reason
):
    app = _app()
    view = StrategyLibraryView(_SyntheticRegistry, version_service)
    qt_driver.addWidget(view)

    assert _wait_for_version_load(view, app)
    assert view.version_combo.currentText() == "版本 1.0.0"
    assert view.select_button.isEnabled()
    assert reason in view.version_status_label.toolTip()
    assert view.retry_versions_button.isHidden()
    assert view.retry_versions_button.isEnabled() is False


def test_saved_version_retry_recovers_exact_saved_identity(qt_driver):
    app = _app()
    service = _FailThenSucceedVersionReader()
    view = StrategyLibraryView(_SyntheticRegistry, service)
    qt_driver.addWidget(view)

    assert _wait_for_version_load(view, app)
    assert service.read_calls == ["strategy_alpha"]
    assert view.version_combo.currentText() == "版本 1.0.0"
    assert view.select_button.isEnabled()
    assert not view.retry_versions_button.isHidden()

    view.retry_versions_button.click()
    assert view.version_status_label.text() == "讀取保存版本中…"
    assert view.version_combo.isEnabled() is False
    assert view.select_button.isEnabled() is False
    assert view.retry_versions_button.isHidden()
    assert view.retry_versions_button.isEnabled() is False

    assert _wait_for_version_load(view, app)
    assert service.read_calls == ["strategy_alpha", "strategy_alpha"]
    assert "符合此策略 1 筆" in view.version_status_label.text()
    assert view.retry_versions_button.isHidden()
    assert view.version_combo.isEnabled()

    saved_index = next(
        index
        for index in range(view.version_combo.count())
        if view.version_combo.itemData(index).version == "1.5.0"
    )
    saved_choice = view.version_combo.itemData(saved_index)
    assert saved_choice.saved["version_id"] == "saved-after-retry"
    assert saved_choice.saved["source_run_id"] == "run-after-retry"
    view.version_combo.setCurrentIndex(saved_index)
    assert "saved-after-retry" in view.detail_labels["source_identity"].text()
    assert "run-after-retry" in view.detail_labels["source_identity"].text()
    assert service.write_calls == 0


def test_async_saved_versions_preserve_order_identity_and_read_only_behavior(qt_driver):
    app = _app()
    service = _VersionReader([
        {
            "version_id": "saved-new",
            "strategy_id": "strategy_alpha",
            "strategy_version": "1.3.0",
            "source_run_id": "run-new",
        },
        {
            "version_id": "saved-old",
            "strategy_id": "strategy_alpha",
            "strategy_version": "1.2.0",
            "source_run_id": "run-old",
        },
    ])
    view = StrategyLibraryView(_SyntheticRegistry, service)
    qt_driver.addWidget(view)

    assert _wait_for_version_load(view, app)
    assert [
        view.version_combo.itemData(index).version
        for index in range(view.version_combo.count())
    ] == ["1.0.0", "1.3.0", "1.2.0"]
    saved_new = view.version_combo.itemData(1)
    assert saved_new.saved["version_id"] == "saved-new"
    assert saved_new.saved["source_run_id"] == "run-new"
    assert service.write_calls == 0
