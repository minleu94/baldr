"""完整報告固定呈現不得重查 producer 或沿 Main 加入現在資料。"""

from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace
import time

from PySide6.QtWidgets import QApplication

from app_module.research_session import ResearchStockContextDTO
from app_module.stock_research_report_dtos import StockPricePointDTO, StockResearchReportDTO
from app_module.stock_research_report_snapshot_codec import create_stock_research_report_projection_snapshot
from ui_qt.views.stock_research_report_view import StockResearchReportView
from ui_qt.views.stock_research_workspace import StockResearchWorkspace


def _app():
    return QApplication.instance() or QApplication([])


def _wait(app, predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while not predicate():
        app.processEvents()
        assert time.monotonic() < deadline, "報告 worker 未在期限內結束"
        time.sleep(0.005)
    app.processEvents()


def _report(code="2330"):
    return StockResearchReportDTO(
        stock_code=code, stock_name="保存名稱", as_of="2026-10-16",
        generated_at="2026-10-17T01:02:03+08:00",
        price_points=(StockPricePointDTO(data_date="2026-10-16", close_price=Decimal("100.0100")),),
        shared_daily_features={"missing": None, "display": ["原值", Decimal("1.2300")]},
        limitations=("來源仍缺件，不授歷史PIT",),
    )


def test_saved_report_renders_all_tabs_without_reads_or_live_load_signals():
    app = _app()
    calls = []

    def no_read(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("固定報告不得查 producer")

    view = StockResearchReportView(SimpleNamespace(read_report=no_read), saved_snapshot_only=True)
    context = ResearchStockContextDTO(stock_code="2330", source_kind="current_stock_research")
    report = _report()
    snapshot = create_stock_research_report_projection_snapshot(report, context)
    signals = []
    view.reportLoaded.connect(lambda *_: signals.append("reportLoaded"))
    view.activeContextChanged.connect(lambda *_: signals.append("contextChanged"))
    try:
        view.show_saved_report_snapshot(snapshot)
        assert not view.is_busy()
        assert view.status_badge.text() == "載入完成"
        # 接收者可改動的 DTO 不能取代 canonical 原文。
        snapshot.report.shared_daily_features["display"].append("外部改值")
        for index in range(view.tabs.count()):
            view.tabs.setCurrentIndex(index)
            app.processEvents()
        view.set_context(replace(context, stock_code="2317"))
        view._load_stock("2454")
        view.set_chart_marker_reader(SimpleNamespace(read=no_read), None)
        view.set_chart_marker_evidence((), ())
        assert calls == [] and signals == []
        exact = view.get_loaded_report_snapshot()
        assert exact.report == report
        assert exact.identity_sha256 == snapshot.identity_sha256
        assert exact.report.price_points[0].close_price.as_tuple() == Decimal("100.0100").as_tuple()
        assert exact.report.shared_daily_features["display"] == ["原值", Decimal("1.2300")]
        assert view.context == context and view._active_code == "2330"
        assert all(not button.isEnabled() for button in (
            view.load_button, view.reload_button, view.previous_button, view.next_button,
        ))
        assert view.return_button.text() == "返回我的判斷"
        assert "保存時報告" in view.query_as_of_label.text()
    finally:
        assert view.request_close()
        view.close()


def test_capture_requires_current_successful_request_and_rejects_changed_context():
    app = _app()
    report = _report()
    calls = []

    def read_report(code, **kwargs):
        calls.append(code)
        return report

    view = StockResearchReportView(SimpleNamespace(read_report=read_report))
    context = ResearchStockContextDTO(stock_code="2330", ml_scope_mode="current_stock_research")
    try:
        assert view.get_loaded_report_snapshot() is None
        view.set_context(context)
        _wait(app, lambda: view._loaded_report is not None and not view.is_busy())
        snapshot = view.get_loaded_report_snapshot()
        assert snapshot is not None and snapshot.report == report
        assert snapshot.context == view.context
        view.context = replace(view.context, source_id="changed")
        assert view.get_loaded_report_snapshot() is None
        view.context = snapshot.context
        view._on_report_error(view._request_id, "2330", "本次來源失敗")
        assert view.get_loaded_report_snapshot() is None
        assert calls == ["2330"]
    finally:
        assert view.request_close()
        view.close()


def test_saved_workspace_report_keeps_live_report_and_returns_to_notes(tmp_path):
    from app_module.journal_service import JournalService
    from app_module.personal_journal_paths import resolve_personal_journal_paths
    from app_module.stock_research_report_notes import StockResearchReportNoteService

    app = _app()
    paths = resolve_personal_journal_paths(tmp_path / "data", personal_root=tmp_path / "personal")
    journal = JournalService(SimpleNamespace(output_root=paths.personal_paths.legacy_output_root), journal_paths=paths)
    calls = []

    def read_report(code, **kwargs):
        calls.append(code)
        return _report(code)

    workspace = StockResearchWorkspace(
        SimpleNamespace(read_report=read_report), report_note_service=StockResearchReportNoteService(journal),
    )
    context = ResearchStockContextDTO(stock_code="2330", ml_scope_mode="current_stock_research")
    try:
        workspace.set_context(context)
        # 尚未送出新查詢的輸入文字不能改綁剛完成的報告身份。
        workspace.report_view.stock_search.setText("2317")
        _wait(app, lambda: workspace.report_view._loaded_report is not None and not workspace.is_busy())
        original = workspace.report_view._loaded_report
        snapshot = workspace.report_view.get_loaded_report_snapshot()
        workspace.show_saved_report_snapshot(snapshot)
        assert workspace.report_tabs.currentWidget() is workspace.saved_report_view
        assert workspace.saved_report_view._loaded_report == original
        workspace.saved_report_view.return_button.click()
        assert workspace.report_tabs.currentWidget() is workspace.report_notes_page
        assert workspace.report_view._loaded_report is original
        assert calls == ["2330"]
    finally:
        workspace.request_close()
        _wait(app, lambda: not workspace.is_busy())
        workspace.close()


def test_theme_notes_composition_can_defer_private_history_until_opened():
    from ui_qt.widgets.theme_research_notes_widget import ThemeResearchNotesWidget

    app = _app()
    calls = []

    def list_notes():
        calls.append(True)
        return ()

    widget = ThemeResearchNotesWidget(SimpleNamespace(list_notes=list_notes), auto_refresh=False)
    try:
        app.processEvents()
        assert calls == [] and not widget.is_busy()
        widget.refresh_notes()
        _wait(app, lambda: not widget.is_busy())
        assert calls == [True]
    finally:
        widget.shutdown()
        widget.close()
