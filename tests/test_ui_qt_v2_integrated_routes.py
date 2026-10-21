from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication

from app_module.journal_service import JournalService
from app_module.personal_journal_paths import resolve_personal_journal_paths
from app_module.research_timeline_service import ResearchTimelineService
from app_module.stock_research_report_notes import StockResearchReportNoteService
from app_module.stock_research_report_snapshot_codec import create_stock_research_report_projection_snapshot
from decision_module.strategies.registry import StrategyRegistry
from tests.test_stock_research_report_snapshot_codec import _report
from ui_qt.main import MainWindow
from ui_qt.views.backtest_view import BacktestView
from ui_qt.views.stock_research_workspace import StockResearchWorkspace


def _app():
    return QApplication.instance() or QApplication([])


class _Combo:
    def __init__(self, strategy_id: str, label: str):
        self.strategy_id = strategy_id
        self.label = label
        self.index = 0

    def findData(self, value):
        return 0 if value == self.strategy_id else -1

    def setCurrentIndex(self, index):
        self.index = index

    def currentData(self):
        return self.strategy_id

    def currentText(self):
        return self.label


class _BacktestHost:
    can_select_registered_strategy = staticmethod(BacktestView.can_select_registered_strategy)
    select_registered_strategy = BacktestView.select_registered_strategy

    def __init__(self, strategy_id: str, label: str):
        self.strategy_combo = _Combo(strategy_id, label)
        self.strategy_desc = SimpleNamespace(text=lambda: "登記策略")
        self._library_strategy_pin = None
        self.changed = 0
        self.collapsed = True

    def _on_strategy_changed(self):
        self.changed += 1

    def _set_config_panel_collapsed(self, collapsed):
        self.collapsed = collapsed

    def _get_default_strategy_config(self):
        return {}

    def _get_strategy_params(self):
        return {}


class _Status:
    def __init__(self):
        self.messages = []

    def showMessage(self, message):
        self.messages.append(message)


class _Stack:
    def __init__(self, current):
        self.current = current

    def currentWidget(self):
        return self.current

    def setCurrentWidget(self, widget):
        self.current = widget


class _ProductShell:
    def __init__(self):
        self.routes = []
        self.origins = []
        self._detail_origin = ""

    def activate_route(self, route):
        self.routes.append(route)

    def set_detail_origin(self, origin):
        self._detail_origin = origin
        self.origins.append(origin)


def _report_route_context(tmp_path: Path):
    paths = resolve_personal_journal_paths(
        tmp_path / "data",
        personal_root=tmp_path / "personal",
    )
    journal = JournalService(
        SimpleNamespace(output_root=paths.personal_paths.legacy_output_root),
        journal_paths=paths,
    )
    note_service = StockResearchReportNoteService(journal)
    report, context = _report()
    snapshot = create_stock_research_report_projection_snapshot(report, context)
    saved = note_service.save(snapshot, "原始報告判斷\n保留全文", revision_id="route-report-1")
    timeline_service = ResearchTimelineService(
        journal,
        report_note_service=note_service,
    )
    entry = next(item for item in timeline_service.read().entries if item.kind == "report")
    return journal, note_service, timeline_service, saved, entry


def _timeline_host(app, workspace, timeline_service, entry):
    timeline_page = object()
    pending = []
    host = SimpleNamespace(
        _shutdown_close_requested=False,
        _timeline_detail_entry=None,
        _timeline_original_worker=None,
        _timeline_original_workers=set(),
        research_timeline_service=timeline_service,
        research_timeline_view=SimpleNamespace(_selected=entry),
        stock_research_workspace=workspace,
        workspace_widgets={"research_timeline": timeline_page, "stock_research": workspace},
        workspace_stack=_Stack(timeline_page),
        product_shell=_ProductShell(),
        statusBar=lambda: _Status(),
    )
    host.product_shell.activate_route = lambda route: (
        host.product_shell.routes.append(route),
        host.workspace_stack.setCurrentWidget(timeline_page) if route == "journal" else None,
    )
    host._verify_timeline_entry = lambda selected, completed: pending.append((selected, completed))
    host._select_main_workspace = lambda key: host.workspace_stack.setCurrentWidget(
        workspace if key == "stock_research" else timeline_page
    )
    return host, pending, timeline_page


def test_strategy_library_route_selects_only_current_registered_version_without_execution(monkeypatch):
    _app()
    import decision_module.strategies  # 載入正式登記策略，測試只讀 registry metadata。

    strategy_id = "baseline_score_threshold"
    current = StrategyRegistry.get_strategy_meta(strategy_id)
    assert current is not None
    current_version = current.get("version", current.get("strategy_version"))
    historical = StrategyRegistry.get_strategy_meta(strategy_id, version="1.0")
    assert historical is not None
    assert current_version != "1.0"
    assert BacktestView.can_select_registered_strategy(strategy_id, current_version)
    assert not BacktestView.can_select_registered_strategy(strategy_id, "1.0")

    backtest = _BacktestHost(strategy_id, current["name"])
    activated = []
    status = _Status()
    host = SimpleNamespace(
        _shutdown_close_requested=False,
        backtest_view=backtest,
        product_shell=SimpleNamespace(activate_route=activated.append),
        statusBar=lambda: status,
    )
    MainWindow._open_library_strategy(host, strategy_id, current_version)

    assert backtest._library_strategy_pin == (strategy_id, current_version)
    assert backtest.changed == 1 and backtest.collapsed is False
    assert activated == ["backtests"]
    assert not hasattr(backtest, "execute")

    original_reader = StrategyRegistry.get_strategy_meta

    def changed_registry(requested_id, *, version=None):
        metadata = original_reader(requested_id, version=version)
        if requested_id == strategy_id and version is None and metadata is not None:
            metadata = dict(metadata)
            metadata["version"] = "9.9.9"
        return metadata

    monkeypatch.setattr(StrategyRegistry, "get_strategy_meta", changed_registry)
    with pytest.raises(ValueError, match="版本已不再"):
        BacktestView._selected_strategy_spec(backtest)


def test_timeline_report_route_fresh_reads_saved_note_then_returns_to_timeline(tmp_path):
    app = _app()
    journal, note_service, timeline_service, saved, entry = _report_route_context(tmp_path)
    workspace = StockResearchWorkspace(
        SimpleNamespace(read_report=lambda *_args, **_kwargs: pytest.fail("不應載入最新報告")),
        report_note_service=note_service,
    )
    host, pending, timeline_page = _timeline_host(app, workspace, timeline_service, entry)
    try:
        MainWindow._open_timeline_original(host, entry)
        assert len(pending) == 1 and pending[0][0] is entry
        selected, completed = pending.pop()
        completed(timeline_service.read_original(selected))

        assert host.workspace_stack.currentWidget() is workspace
        assert workspace.saved_report_view is not None
        assert workspace.report_tabs.currentWidget() is workspace.saved_report_view
        assert workspace.saved_report_view._saved_projection_snapshot.canonical_json == saved.snapshot.canonical_json
        assert workspace.saved_report_view._saved_projection_snapshot.canonical_json == entry.reference.snapshot.canonical_json
        assert host._timeline_detail_entry is entry
        assert host.product_shell.origins == ["journal"]

        assert MainWindow._return_from_timeline_detail(host) is True
        assert len(pending) == 1
        selected, completed = pending.pop()
        completed(timeline_service.read_original(selected))
        assert host.product_shell.routes == ["journal"]
        assert host._timeline_detail_entry is None
        assert host.workspace_stack.currentWidget() is timeline_page
    finally:
        workspace.close()


def test_late_timeline_original_result_does_not_navigate_after_selection_changes(tmp_path):
    app = _app()
    _journal, note_service, timeline_service, _saved, entry = _report_route_context(tmp_path)
    report, context = _report()
    second_snapshot = create_stock_research_report_projection_snapshot(
        replace(report, shared_daily_features={**report.shared_daily_features, "variant": "second"}),
        context,
    )
    second = note_service.save(
        second_snapshot,
        "另一筆保存判斷",
        revision_id="route-report-2",
    )
    second_entry = next(
        item for item in timeline_service.read().entries
        if item.record_id == second.revision_id
    )
    workspace = StockResearchWorkspace(
        SimpleNamespace(read_report=lambda *_args, **_kwargs: pytest.fail("不應載入最新報告")),
        report_note_service=note_service,
    )
    host, pending, timeline_page = _timeline_host(app, workspace, timeline_service, entry)
    try:
        MainWindow._open_timeline_original(host, entry)
        selected, completed = pending.pop()
        host.research_timeline_view._selected = second_entry
        completed(timeline_service.read_original(selected))

        assert host.workspace_stack.currentWidget() is timeline_page
        assert host._timeline_detail_entry is None
        assert host.product_shell.origins == []
    finally:
        workspace.close()


def test_late_timeline_return_does_not_take_over_after_leaving_report_detail(tmp_path):
    app = _app()
    _journal, note_service, timeline_service, _saved, entry = _report_route_context(tmp_path)
    workspace = StockResearchWorkspace(
        SimpleNamespace(read_report=lambda *_args, **_kwargs: pytest.fail("不應載入最新報告")),
        report_note_service=note_service,
    )
    host, pending, _timeline_page = _timeline_host(app, workspace, timeline_service, entry)
    try:
        MainWindow._open_timeline_original(host, entry)
        selected, completed = pending.pop()
        completed(timeline_service.read_original(selected))
        assert host.workspace_stack.currentWidget() is workspace
        assert host.product_shell._detail_origin == "journal"

        assert MainWindow._return_from_timeline_detail(host) is True
        selected, completed = pending.pop()
        host.workspace_stack.setCurrentWidget(object())
        completed(timeline_service.read_original(selected))

        assert host.product_shell.routes == []
        assert host.workspace_stack.currentWidget() is not workspace
    finally:
        workspace.close()
