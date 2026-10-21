"""題材往返沿既有Main研究context，不建立另一套導航。"""
from dataclasses import replace
from datetime import date, datetime, timezone
from types import SimpleNamespace

from app_module.research_session import ResearchStockContextDTO
from app_module.theme_daily_service import ThemeDailyReport
from app_module.theme_research_snapshot import ThemeResearchSnapshot
from decision_module.industry_theme_map import ThemeMappingRow
from ui_qt.main import MainWindow
from ui_qt.views.theme_member_navigation import ThemeMemberNavigation


def host():
    row = ThemeMappingRow("2026-10-16", "2026-10-16", "2330", "台積電", "twse", "半導體",
        "半導體", "中游", "晶圓代工", True, "curated", "local", "T2", "quarterly_snapshot", "fixture")
    report = ThemeDailyReport(date(2026, 10, 16), datetime(2026, 10, 18, tzinfo=timezone.utc),
        "2026-10-16", "2026-10-16", "current_research", (), ())
    snapshot = ThemeResearchSnapshot("a" * 64, report, (row,))
    events = []
    view = SimpleNamespace(snapshot=snapshot, is_busy=lambda: False, selection_revision=1)
    view.capture_selected_member_navigation = lambda expected_stock_code=None: (
        ThemeMemberNavigation(view.snapshot, view.snapshot.identity_sha256, ("半導體", "晶圓代工"),
            ("2330", "2317"), (("2330", "台積電"), ("2317", "鴻海")), "2330", 0,
            "2026-10-16", "2026-10-16", view.selection_revision)
        if expected_stock_code in (None, "2330") else None
    )
    result = SimpleNamespace(industry_theme_map_view=view, _shutdown_close_requested=False,
        _open_stock_research_context=lambda context: events.append(("open", context)),
        _select_main_workspace=lambda name: events.append(("workspace", name)),
        market_tabs=SimpleNamespace(setCurrentWidget=lambda widget: events.append(("tab", widget))),
        statusBar=lambda: SimpleNamespace(showMessage=lambda message: events.append(("message", message))),
        _coerce_stock_research_context=lambda value: value if isinstance(value, ResearchStockContextDTO) else None)
    result._current_theme_member_navigation = lambda context: MainWindow._current_theme_member_navigation(result, context)
    page = object()
    result.stock_research_workspace = SimpleNamespace(report_view=SimpleNamespace(context=None),
        general_report_page=page, content_stack=SimpleNamespace(currentWidget=lambda: page))
    result.workspace_widgets = {"stock_research": object()}
    result.workspace_stack = SimpleNamespace(currentWidget=lambda: result.workspace_widgets["stock_research"])
    return result, events


def test_open_carries_original_snapshot_name_and_dates_then_returns_same_view():
    target, events = host()
    MainWindow._open_theme_research_stock(target, "2330")
    context = next(value for kind, value in events if kind == "open")
    assert context.stock_name == "台積電" and context.data_date == "2026-10-16"
    assert context.source_snapshot_hash == "a" * 64
    assert context.source_kind == "industry_theme_snapshot"
    assert context.source_workspace == "market_explore"
    assert context.ml_scope_mode == "current_stock_research"
    assert context.decision_date == ""
    MainWindow._return_to_research_source(target, context)
    assert ("workspace", "market_explore") in events
    assert ("tab", target.industry_theme_map_view) in events


def test_changed_source_identity_refuses_return_without_fallback():
    target, events = host()
    MainWindow._open_theme_research_stock(target, "2330")
    context = target._industry_theme_origin
    target.industry_theme_map_view.snapshot = ThemeResearchSnapshot("b" * 64,
        target.industry_theme_map_view.snapshot.report, target.industry_theme_map_view.snapshot.mapping)
    events.clear()
    MainWindow._return_to_research_source(target, context)
    assert not any(kind in {"workspace", "tab"} for kind, value in events)
    assert "未以新版本替代" in events[-1][1]


def test_unknown_stock_or_busy_page_cannot_open_general_stock_as_fallback():
    target, events = host()
    MainWindow._open_theme_research_stock(target, "9999")
    assert events == []
    target.industry_theme_map_view.is_busy = lambda: True
    MainWindow._open_theme_research_stock(target, "2330")
    assert events == []


def test_home_theme_entry_returns_same_view_without_loading_a_new_version():
    target, events = host()
    snapshot = target.industry_theme_map_view.snapshot
    MainWindow._open_workbench_industry_themes(target)
    assert target.industry_theme_map_view.snapshot is snapshot
    assert events == [("workspace", "market_explore"), ("tab", target.industry_theme_map_view)]


def test_member_navigation_preserves_source_and_original_selection_on_return():
    target, events = host()
    MainWindow._open_theme_research_stock(target, "2330")
    origin = target._industry_theme_origin
    target.stock_research_workspace.report_view.context = origin
    assert MainWindow._stock_codes_for_research_context(target, origin) == ("2330", "2317")
    next_context = MainWindow._resolve_theme_member_stock(target, origin, "2317")
    assert next_context == replace(origin, stock_code="2317", stock_name="鴻海")
    assert target._industry_theme_navigation.origin_stock_code == "2330"
    assert target._industry_theme_navigation.origin_row_index == 0
    target.stock_research_workspace.report_view.context = next_context
    back = MainWindow._resolve_theme_member_stock(target, next_context, "2330")
    assert back == origin
    events.clear()
    MainWindow._return_to_research_source(target, back)
    assert events == [("workspace", "market_explore"), ("tab", target.industry_theme_map_view)]


def test_changed_selection_revision_rejects_switch_and_return_without_mutating_context():
    target, events = host()
    MainWindow._open_theme_research_stock(target, "2330")
    origin = target._industry_theme_origin
    target.stock_research_workspace.report_view.context = origin
    target.industry_theme_map_view.selection_revision += 1
    assert MainWindow._resolve_theme_member_stock(target, origin, "2317") is None
    assert target._industry_theme_origin == origin
    assert MainWindow._stock_codes_for_research_context(target, origin) == ()
    events.clear()
    MainWindow._return_to_research_source(target, origin)
    assert not any(kind in {"workspace", "tab"} for kind, _ in events)


def test_hidden_or_stale_report_and_outside_member_reject_navigation():
    target, _events = host()
    MainWindow._open_theme_research_stock(target, "2330")
    origin = target._industry_theme_origin
    assert MainWindow._resolve_theme_member_stock(target, origin, "2317") is None
    target.stock_research_workspace.report_view.context = origin
    assert MainWindow._resolve_theme_member_stock(target, origin, "9999") is None
    target.workspace_stack.currentWidget = lambda: object()
    assert MainWindow._resolve_theme_member_stock(target, origin, "2317") is None
    target.workspace_stack.currentWidget = lambda: target.workspace_widgets["stock_research"]
    target.stock_research_workspace.content_stack.currentWidget = lambda: object()
    assert MainWindow._resolve_theme_member_stock(target, origin, "2317") is None
    assert target._industry_theme_origin == origin
