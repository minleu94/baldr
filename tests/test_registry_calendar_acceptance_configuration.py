from __future__ import annotations

from dataclasses import replace

import pytest
from PySide6.QtWidgets import QWidget

pytest_plugins = ("test_registry_period_pair_controller",)

from ui_qt.views.backtest.result_panel import BacktestResultPanel
from ui_qt.views.backtest_view import BacktestView
from test_registry_period_pair_controller import _wait_until
import test_registry_period_pair_daily_controller as daily_controller_helpers


class _PanelHarness:
    """只供呼叫既有tab composition方法，不重建完整Main或BacktestView。"""

    def __init__(self, parent_view: QWidget) -> None:
        self.parent_view = parent_view
        self._research_mode_id = "single_stock"
        self.registered_tab: tuple[str, QWidget, str] | None = None

    def _register_result_tab(self, key: str, widget: QWidget, title: str) -> None:
        self.registered_tab = (key, widget, title)

    def set_research_mode(self, mode: str) -> None:
        self._research_mode_id = mode


def _result_panel_controller(case, *, anchors, error: str, legacy_parent: bool = False):
    owner = QWidget()
    owner.research_run_service = case.service
    owner.config = case.config
    owner._execution_generation = case.generation[0]
    owner._open_recommendation_registry_run = lambda *_args: None
    if not legacy_parent:
        owner.calendar_daily_acceptances = anchors
        owner.calendar_daily_acceptance_error = error
    panel = _PanelHarness(owner)
    BacktestResultPanel.add_registry_compare_tab(panel)
    return owner, panel


def _close_result_panel_controller(case, owner: QWidget, panel: _PanelHarness) -> None:
    controller = panel.period_pair_controller
    controller.begin_shutdown()
    if panel.registered_tab is not None:
        container = panel.registered_tab[1]
        container.close()
        container.deleteLater()
    panel.run_registry_compare_widget.close()
    panel.run_registry_compare_widget.deleteLater()
    controller.deleteLater()
    owner.close()
    owner.deleteLater()
    case.app.processEvents()


@pytest.mark.parametrize("configuration", ["valid", "missing", "error", "legacy"])
def test_registry_tab_passes_main_acceptance_configuration_to_real_controller(
    pair_controller, configuration: str,
):
    case = pair_controller
    anchors = daily_controller_helpers._acceptance_tuple() if configuration == "valid" else None
    error = "binding_read_failed" if configuration == "error" else ""
    owner, panel = _result_panel_controller(
        case, anchors=anchors, error=error, legacy_parent=configuration == "legacy",
    )
    try:
        controller = panel.period_pair_controller
        assert controller._daily_acceptances == anchors
        assert controller._daily_acceptance_configuration_error == error

        controller.source_mode.setCurrentIndex(controller.source_mode.findData("daily"))
        if configuration == "valid":
            assert all(item.acceptance_id in controller.acceptance_status.text() for item in anchors)
        elif configuration in {"missing", "legacy"}:
            assert "缺少" in controller.acceptance_status.text()
            controller.apply_button.click()
            assert controller._pin is None
            assert "缺少" in controller.status.text()
        else:
            assert controller.acceptance_status.text() == "來源用途接受設定無法讀取：binding_read_failed"
            controller.source_mode.setCurrentIndex(controller.source_mode.findData("artifact"))
            controller.source_mode.setCurrentIndex(controller.source_mode.findData("daily"))
            assert controller.acceptance_status.text() == "來源用途接受設定無法讀取：binding_read_failed"
    finally:
        _close_result_panel_controller(case, owner, panel)


def test_backtest_view_keeps_caller_snapshot_and_rejects_conflicting_state(qt_app, monkeypatch):
    import app_module.report_export_service as report_export_service

    monkeypatch.setattr(BacktestView, "_setup_ui", lambda self: None)
    monkeypatch.setattr(BacktestView, "_init_parameter_descriptions", lambda self: None)
    monkeypatch.setattr(report_export_service, "ReportExportService", lambda: object())
    anchors = daily_controller_helpers._acceptance_tuple()
    view = BacktestView(
        backtest_service=None, config=None,
        calendar_daily_acceptances=anchors, calendar_daily_acceptance_error="",
    )
    try:
        assert view.calendar_daily_acceptances == anchors
        assert view.calendar_daily_acceptance_error == ""
    finally:
        view.close()
        view.deleteLater()
        qt_app.processEvents()

    with pytest.raises(ValueError, match="不可同時提供"):
        BacktestView(
            backtest_service=None, config=None,
            calendar_daily_acceptances=anchors, calendar_daily_acceptance_error="read_failed",
        )
    with pytest.raises(TypeError, match="必須是字串"):
        BacktestView(
            backtest_service=None, config=None,
            calendar_daily_acceptance_error=None,
        )
    with pytest.raises(ValueError, match="512"):
        BacktestView(
            backtest_service=None, config=None,
            calendar_daily_acceptance_error="x" * 513,
        )


def test_configuration_error_is_visible_sticky_and_cannot_create_daily_pin(pair_controller):
    case = pair_controller
    controller = case.controller
    reason = "binding_sha_mismatch"

    controller.set_daily_acceptances(None, configuration_error=reason)
    controller.source_mode.setCurrentIndex(controller.source_mode.findData("daily"))
    assert controller.acceptance_status.text() == "來源用途接受設定無法讀取：" + reason
    assert case.widget.compare_period_pair_button.isEnabled() is False

    controller.source_mode.setCurrentIndex(controller.source_mode.findData("artifact"))
    controller.source_mode.setCurrentIndex(controller.source_mode.findData("daily"))
    assert controller.acceptance_status.text() == "來源用途接受設定無法讀取：" + reason
    controller.apply_button.click()
    assert controller._pin is None
    assert "來源用途接受設定無法讀取：" + reason in controller.status.text()


def test_acceptance_configuration_change_invalidates_pin_and_discards_queued_worker(pair_controller):
    case = pair_controller
    controller = case.controller
    pin = daily_controller_helpers._configure_daily(case)
    assert pin is not None
    result = replace(
        case.result,
        market=pin.market,
        calendar_external_sha256=pin.expected_manifest_sha256,
        daily_calendar_source=daily_controller_helpers._daily_identity(pin),
    )
    worker = daily_controller_helpers._start_daily_read(case, pin, result)

    controller.set_daily_acceptances(None, configuration_error="binding_changed")
    assert controller._pin is None
    assert worker.is_cancel_requested() is True
    case.reader.release.set()
    assert worker.wait(5000)
    assert _wait_until(case.app, lambda: controller.worker is None)
    assert case.widget._period_pair_result is None
    assert case.widget._period_pair_busy is False
    assert controller.acceptance_status.text() == "來源用途接受設定無法讀取：binding_changed"


def test_acceptance_configuration_setter_keeps_old_call_and_rejects_bad_error_values(pair_controller):
    case = pair_controller
    controller = case.controller
    anchors = daily_controller_helpers._acceptance_tuple()

    # 舊呼叫形狀仍可用，錯誤原因則是新的獨立配置狀態。
    controller.set_daily_acceptances(anchors)
    assert controller._daily_acceptances == anchors
    assert controller._daily_acceptance_configuration_error == ""
    with pytest.raises(TypeError):
        controller.set_daily_acceptances(None, configuration_error=None)
    with pytest.raises(ValueError, match="512"):
        controller.set_daily_acceptances(None, configuration_error="x" * 513)
    with pytest.raises(ValueError, match="不可同時提供"):
        controller.set_daily_acceptances(anchors, configuration_error="read_failed")
