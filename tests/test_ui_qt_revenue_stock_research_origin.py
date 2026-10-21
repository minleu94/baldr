from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace
from typing import Any

import pytest
from PySide6.QtWidgets import QApplication, QTabWidget, QWidget

from ui_qt.main import MainWindow
from ui_qt.views.daily_market_technical_official_disposition_revenue_view import (
    DailyMarketTechnicalOfficialDispositionRevenueView,
    _SourceChoice,
)
from ui_qt.views.revenue_stock_research_origin import RevenueStockResearchOrigin

_APP: QApplication | None = None


def _origin(**overrides: Any) -> RevenueStockResearchOrigin:
    values: dict[str, Any] = {
        "stock_code": "2330",
        "source_identity_sha256": "1" * 64,
        "recipe_identity_sha256": "9" * 64,
        "query_identity_sha256": "2" * 64,
        "page_identity_sha256": "3" * 64,
        "request_identity_sha256": "4" * 64,
        "row_identity_sha256": "5" * 64,
        "page_index": 0,
    }
    values.update(overrides)
    return RevenueStockResearchOrigin.create(**values)


def _install_verified_page(view: DailyMarketTechnicalOfficialDispositionRevenueView) -> Any:
    row = SimpleNamespace(stock_code="2330", row_identity_sha256="5" * 64)
    query = SimpleNamespace(query_identity_sha256="2" * 64)
    request = SimpleNamespace(
        query=query, request_identity_sha256="4" * 64, page_index=0
    )
    page = SimpleNamespace(
        query=query,
        request_identity_sha256=request.request_identity_sha256,
        page_identity_sha256="3" * 64,
        page_index=0,
        rows=(row,),
        source_pins=(("f17", "6" * 64),),
    )
    result = SimpleNamespace(query=query)
    view._source = _SourceChoice("bundle", "7" * 64, "8" * 64, "{}")
    view._recipe = SimpleNamespace(to_json=lambda: "frozen-recipe-v1")
    view._query = query
    view._result = result
    view._page_request = request
    view._page = page
    view._selected_row = row
    return SimpleNamespace(row=row, query=query, request=request, page=page)


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def test_origin_is_immutable_and_rejects_modified_identity() -> None:
    origin = _origin()
    with pytest.raises(FrozenInstanceError):
        origin.stock_code = "2317"  # type: ignore[misc]
    with pytest.raises(ValueError, match="identity_mismatch"):
        replace(origin, stock_code="2317")


def test_revenue_view_creates_and_restores_current_verified_row_without_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app()
    import ui_qt.views.daily_market_technical_official_disposition_revenue_view as revenue_view_module

    monkeypatch.setattr(revenue_view_module, "_query_matches_recipe", lambda *_args: True)
    view = DailyMarketTechnicalOfficialDispositionRevenueView()
    state = _install_verified_page(view)
    requested: list[object] = []
    view.stockResearchRequested.connect(requested.append)

    origin = view.create_stock_research_origin()
    assert origin is not None
    assert origin.stock_code == "2330"
    assert origin.page_index == 0
    view.request_stock_research()
    assert requested == [origin]

    selected: list[str] = []

    def select_stock(code: str) -> bool:
        selected.append(code)
        view._selected_row = state.row
        return code == state.row.stock_code

    monkeypatch.setattr(view, "select_stock_code", select_stock)
    view.results_stack.setCurrentIndex(1)
    assert view.restore_stock_research_origin(origin)
    assert selected == ["2330"]
    assert view.results_stack.currentIndex() == 0


@pytest.mark.parametrize("changed", ["source", "recipe", "query", "page", "row", "selection"])
def test_revenue_view_rejects_origin_when_current_snapshot_identity_changes(
    monkeypatch: pytest.MonkeyPatch, changed: str,
) -> None:
    _app()
    import ui_qt.views.daily_market_technical_official_disposition_revenue_view as revenue_view_module

    monkeypatch.setattr(revenue_view_module, "_query_matches_recipe", lambda *_args: True)
    view = DailyMarketTechnicalOfficialDispositionRevenueView()
    state = _install_verified_page(view)
    origin = view.create_stock_research_origin()
    assert origin is not None
    if changed == "source":
        view._source = _SourceChoice("bundle", "9" * 64, "8" * 64, "{}")
    elif changed == "recipe":
        view._recipe = SimpleNamespace(to_json=lambda: "frozen-recipe-v2")
    elif changed == "query":
        state.query.query_identity_sha256 = "a" * 64
    elif changed == "page":
        state.page.page_identity_sha256 = "b" * 64
    else:
        if changed == "selection":
            view._selected_row = SimpleNamespace(stock_code="2317", row_identity_sha256="c" * 64)
        else:
            state.page.rows = (SimpleNamespace(stock_code="2330", row_identity_sha256="c" * 64),)
    assert not view.restore_stock_research_origin(origin)


@pytest.mark.parametrize("state_name", ["busy", "closing"])
def test_revenue_view_rejects_origin_when_busy_or_closing(
    monkeypatch: pytest.MonkeyPatch, state_name: str,
) -> None:
    _app()
    import ui_qt.views.daily_market_technical_official_disposition_revenue_view as revenue_view_module

    monkeypatch.setattr(revenue_view_module, "_query_matches_recipe", lambda *_args: True)
    view = DailyMarketTechnicalOfficialDispositionRevenueView()
    _install_verified_page(view)
    origin = view.create_stock_research_origin()
    assert origin is not None
    if state_name == "busy":
        view._v2_busy = True
    else:
        view._closing = True
    assert view.create_stock_research_origin() is None
    assert not view.restore_stock_research_origin(origin)


def _main_host(view: object) -> SimpleNamespace:
    opened: list[object] = []
    tabs = QTabWidget()
    first = QWidget()
    revenue = view if isinstance(view, QWidget) else QWidget()
    tabs.addTab(first, "other")
    tabs.addTab(revenue, "revenue")
    tabs.setCurrentWidget(first)
    status_messages: list[str] = []
    return SimpleNamespace(
        technical_official_revenue_research_view=view,
        _shutdown_close_requested=False,
        _open_stock_research_context=opened.append,
        opened=opened,
        recommendation_view=SimpleNamespace(result_source_tabs=tabs),
        statusBar=lambda: SimpleNamespace(showMessage=status_messages.append),
        status_messages=status_messages,
        _select_main_workspace=lambda _key: None,
    )


def test_main_adapter_maps_origin_identity_only_and_rejects_stale_or_closing() -> None:
    _app()
    origin = _origin()
    view = SimpleNamespace(create_stock_research_origin=lambda: origin)
    host = _main_host(view)
    MainWindow._open_revenue_stock_research(host, origin)
    assert len(host.opened) == 1
    context = host.opened[0]
    assert context.stock_code == "2330"
    assert context.source_kind == "official_revenue_saved_selection"
    assert context.source_workspace == "recommendation"
    assert context.source_snapshot_id == origin.query_identity_sha256
    assert context.source_snapshot_hash == origin.origin_sha256
    assert context.result_id == origin.origin_sha256
    assert context.decision_date == "" and context.data_date == ""
    assert not hasattr(context, "revenue_fact")
    assert not hasattr(context, "price")

    stale_host = _main_host(SimpleNamespace(create_stock_research_origin=lambda: _origin(stock_code="2317")))
    MainWindow._open_revenue_stock_research(stale_host, origin)
    assert stale_host.opened == []

    host._shutdown_close_requested = True
    MainWindow._open_revenue_stock_research(host, origin)
    assert len(host.opened) == 1


def test_main_return_uses_real_tabs_and_refuses_mismatched_origin() -> None:
    _app()
    origin = _origin()
    class ReturnView(QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.restore_calls: list[object] = []

        def restore_stock_research_origin(self, value: object) -> bool:
            self.restore_calls.append(value)
            return value == origin

    view = ReturnView()
    host = _main_host(view)
    from app_module.research_session import ResearchStockContextDTO

    context = ResearchStockContextDTO(
        stock_code=origin.stock_code,
        result_id=origin.origin_sha256,
        source_snapshot_id=origin.query_identity_sha256,
        source_snapshot_hash=origin.origin_sha256,
        source_kind="official_revenue_saved_selection",
        source_workspace="recommendation",
    )
    host._official_revenue_research_origin = (context, origin)
    tabs = host.recommendation_view.result_source_tabs
    assert tabs.currentIndex() == 0
    assert MainWindow._return_to_revenue_stock_research(host, context)
    assert tabs.currentIndex() == 1
    assert view.restore_calls == [origin]

    tabs.setCurrentIndex(0)
    mismatched = replace(context, result_id="f" * 64)
    assert not MainWindow._return_to_revenue_stock_research(host, mismatched)
    assert tabs.currentIndex() == 0
