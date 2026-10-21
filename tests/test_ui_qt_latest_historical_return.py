"""最新個股明選與歷史研究回訪的來源隔離契約。"""

from __future__ import annotations

from types import MethodType, SimpleNamespace

import pytest

pytest.importorskip("PySide6")

from app_module.research_session import ResearchStockContextDTO
from ui_qt.main import MainWindow, _HistoricalResearchReturn
from app_module.stock_research_report_dtos import StockResearchReportDTO
from ui_qt.views.stock_research_report_view import StockResearchReportView


def _context(**changes: object) -> ResearchStockContextDTO:
    values = {
        "stock_code": "2330",
        "stock_name": "台積電",
        "decision_date": "2026-10-16",
        "data_date": "2026-10-16",
        "result_id": "old-result",
        "source_snapshot_id": "old-snapshot",
        "source_snapshot_hash": "a" * 64,
        "source_id": "old-source",
        "source_version": "old-version",
        "source_kind": "saved_stock_research_report",
        "source_workspace": "journal",
    }
    values.update(changes)
    return ResearchStockContextDTO(**values)


def _historical_host() -> tuple[SimpleNamespace, object, object, object]:
    entry = object()
    token = SimpleNamespace(saved_snapshot=SimpleNamespace(stock_code="2330"), price_selection=None)
    latest = _context(
        decision_date="", data_date="", result_id="", source_snapshot_id="",
        source_snapshot_hash="", source_id="", source_version="",
        source_kind="explicit_latest_stock_research", source_workspace="stock_research",
    )
    report_view = SimpleNamespace(context=latest)
    general_page = object()
    content_stack = SimpleNamespace(currentWidget=lambda: general_page)
    report_tabs = SimpleNamespace(currentWidget=lambda: report_view)
    restored: list[object] = []
    workspace = SimpleNamespace(
        report_view=report_view,
        content_stack=content_stack,
        report_tabs=report_tabs,
        general_report_page=general_page,
        capture_historical_view=lambda: token,
        restore_historical_view=lambda value: restored.append(value) or True,
    )
    shell = SimpleNamespace(
        route_id="overview",
        _detail_origin="overview",
        return_button=SimpleNamespace(setText=lambda _text: None),
        set_detail_origin=lambda route: setattr(shell, "_detail_origin", route),
    )
    host = SimpleNamespace(
        stock_research_workspace=workspace,
        product_shell=shell,
        _timeline_detail_entry=entry,
        _historical_research_return=None,
        _shutdown_close_requested=False,
        workspace_widgets={"stock_research": object(), "research_timeline": object()},
        workspace_stack=None,
        _timeline_detail_entry_before_open=entry,
        restored=restored,
    )
    host.workspace_stack = SimpleNamespace(currentWidget=lambda: host.workspace_widgets["stock_research"])
    host._coerce_stock_research_context = MethodType(MainWindow._coerce_stock_research_context, host)

    def open_stock(context: ResearchStockContextDTO) -> None:
        host._historical_research_return = None
        host._timeline_detail_entry = None
        workspace.report_view.context = context

    host._open_stock_research_context = open_stock
    return host, token, entry, latest


def test_latest_bookmark_opens_fresh_context_and_keeps_exact_history_frame() -> None:
    host, token, entry, _ = _historical_host()
    old = _context()
    host.stock_research_workspace.capture_historical_view = lambda: token
    MainWindow._open_latest_bookmark_research(host, old)

    latest = host.stock_research_workspace.report_view.context
    assert latest.stock_code == old.stock_code
    assert latest.stock_name == old.stock_name
    assert latest.source_kind == "explicit_latest_stock_research"
    assert latest.source_workspace == "stock_research"
    for field in (
        "decision_date", "data_date", "result_id", "source_snapshot_id",
        "source_snapshot_hash", "profile_id", "source_id", "source_version",
        "mapping_source_id", "mapping_version", "rank_context",
    ):
        assert not getattr(latest, field), field
    frame = host._historical_research_return
    assert frame.token is token
    assert frame.timeline_entry is entry
    assert frame.origin_route == "overview"
    assert frame.latest_context == latest


def _return_host() -> tuple[SimpleNamespace, object, object, list[object], list[tuple[object, object]]]:
    host, token, entry, latest = _historical_host()
    host._historical_research_return = _HistoricalResearchReturn(
        token=token, origin_route="overview", timeline_entry=entry, latest_context=latest
    )
    verified: list[tuple[object, object]] = []
    host._verify_timeline_entry = lambda source, callback: verified.append((source, callback))
    host.product_shell.return_button = SimpleNamespace(setText=lambda _text: None)
    return host, token, entry, host.restored, verified


def test_latest_request_cannot_capture_another_stock_history() -> None:
    host, _token, _entry, previous = _historical_host()
    MainWindow._open_latest_bookmark_research(host, _context(stock_code="2317"))
    assert host.stock_research_workspace.report_view.context is previous
    assert host._historical_research_return is None


def test_legacy_missing_chart_report_still_opens_an_independent_latest_context() -> None:
    emitted = []
    old = _context()
    view = SimpleNamespace(
        context=old,
        _loaded_report=StockResearchReportDTO(
            stock_code="2330", research_context={"source_kind": "daily_market_research_snapshot"}
        ),
        _has_historical_latest_action=lambda: False,
        latestResearchRequested=SimpleNamespace(emit=emitted.append),
    )
    assert StockResearchReportView.request_latest_research(view)
    assert len(emitted) == 1 and view.context is old
    latest = emitted[0]
    assert latest.stock_code == old.stock_code
    assert latest.source_kind == "explicit_latest_stock_research"
    assert not latest.decision_date and not latest.result_id and not latest.source_snapshot_hash


def test_historical_return_restores_only_after_current_source_verification() -> None:
    host, token, entry, restored, verified = _return_host()
    assert MainWindow._return_from_latest_historical_research(host) is True
    assert restored == []
    assert verified[0][0] is entry

    verified[0][1](object())

    assert restored == [token]
    assert host._timeline_detail_entry is entry
    assert host._historical_research_return is None
    assert host.product_shell._detail_origin == "overview"


def test_price_history_return_rechecks_exact_selection_before_restoring(monkeypatch) -> None:
    host, _token, _entry, restored, _verified = _return_host()
    frame = host._historical_research_return
    selection = object()
    token = SimpleNamespace(saved_snapshot=None, price_selection=selection)
    host._historical_research_return = _HistoricalResearchReturn(
        token, frame.origin_route, None, frame.latest_context
    )
    pending = []
    host._start_original_verification = lambda reader, args, callback: pending.append((reader, args, callback))
    reads = []
    monkeypatch.setattr(
        "app_module.daily_market_technical_universe_price_comparison_v1.read_daily_market_technical_universe_price_selections_v1",
        lambda selected, **_kwargs: reads.append(selected) or (object(),),
    )
    assert MainWindow._return_from_latest_historical_research(host)
    assert not reads and not restored
    reader, arguments, completed = pending[0]
    result = reader(*arguments)
    assert reads == [(selection,)] and not restored
    completed(result)
    assert restored == [token]


@pytest.mark.parametrize("stale_state", ("report", "route", "leave", "shutdown", "frame"))
def test_late_historical_verification_is_rejected_when_origin_changes(stale_state: str) -> None:
    host, _token, _entry, restored, verified = _return_host()
    assert MainWindow._return_from_latest_historical_research(host) is True

    if stale_state == "report":
        host.stock_research_workspace.report_view.context = _context(stock_code="2317")
    elif stale_state == "route":
        host.product_shell._detail_origin = "paper"
    elif stale_state == "leave":
        host.workspace_stack.currentWidget = lambda: host.workspace_widgets["research_timeline"]
    elif stale_state == "shutdown":
        host._shutdown_close_requested = True
    else:
        host._historical_research_return = object()

    verified[0][1](object())
    assert restored == []


def test_historical_source_verification_error_does_not_restore_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    host, _token, _entry, restored, _verified = _return_host()
    from ui_qt.workers import task_worker

    class _Signal:
        def __init__(self) -> None:
            self.callback = None

        def connect(self, callback) -> None:
            self.callback = callback

        def emit(self, *args) -> None:
            if self.callback is not None:
                self.callback(*args)

    class _Worker:
        def __init__(self, _reader, *_args) -> None:
            self.finished = _Signal()
            self.error = _Signal()
            self.native_thread_finished = _Signal()

        def start(self) -> None:
            self.error.emit("原件來源讀取失敗")
            self.native_thread_finished.emit()

        def deleteLater(self) -> None:
            pass

    monkeypatch.setattr(task_worker, "TaskWorker", _Worker)
    host.research_timeline_service = SimpleNamespace(read_original=lambda _entry: None)
    host._timeline_original_workers = set()
    host._timeline_original_worker = None
    host.statusBar = lambda: SimpleNamespace(showMessage=lambda *_args: None)
    host._start_original_verification = MethodType(MainWindow._start_original_verification, host)
    host._verify_timeline_entry = MethodType(MainWindow._verify_timeline_entry, host)
    assert MainWindow._return_from_latest_historical_research(host) is True
    # 背景 reader 的 error signal 不觸發 completed；保留原現況頁。
    assert restored == []
