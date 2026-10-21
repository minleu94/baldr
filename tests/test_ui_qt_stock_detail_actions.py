"""個股詳情頂部動作只傳遞目前可核驗的來源身份。"""

from __future__ import annotations

import os
import time
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QVBoxLayout, QWidget

from app_module.research_session import ResearchStockContextDTO
from app_module.stock_research_report_dtos import StockPricePointDTO, StockResearchReportDTO
from app_module.stock_research_report_snapshot_codec import (
    create_stock_research_report_projection_snapshot,
)
from ui_qt.views.stock_research_workspace import StockResearchWorkspace
from ui_qt.main import MainWindow
from ui_qt.views.backtest_view import BacktestView

pytest_plugins = ("tests.test_daily_market_technical_universe_price_query_v1",)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _wait(app: QApplication, predicate, timeout: float = 4.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.005)
    app.processEvents()
    assert predicate(), "個股報告讀取未在期限內完成"


def _report(code: str) -> StockResearchReportDTO:
    return StockResearchReportDTO(
        stock_code=code,
        stock_name="測試名稱",
        as_of="2026-10-16",
        price_points=(StockPricePointDTO(data_date="2026-10-16", close_price=Decimal("100")),),
    )


class _ReadService:
    def read_report(self, stock_code: str, **_kwargs: Any) -> StockResearchReportDTO:
        return _report(stock_code)


def _price_selection(fixture: dict[str, Any]):
    from app_module.daily_market_technical_universe_price_comparison_v1 import (
        DailyMarketTechnicalUniversePriceSelectionV1,
    )
    from app_module.daily_market_technical_universe_price_query_v1 import (
        open_daily_market_technical_universe_price_read_session_v1,
    )

    plan = fixture["plan"]
    receipt = fixture["receipt"]
    session = open_daily_market_technical_universe_price_read_session_v1(
        store_output_root=fixture["store_root"],
        generation_identity_sha256=plan.generation_identity_sha256,
        plan_identity_sha256=plan.identity_sha256,
        plan_sha256=fixture["plan_sha256"],
        receipt_identity_sha256=receipt.identity_sha256,
        receipt_sha256=receipt.content_sha256,
    )
    query = session.create_query(unknown_price_policy="include")
    result = session.execute(query)
    request = result.create_page_request(0, page_size=4)
    stock = result.read_stock_snapshot(request, "S0001")
    selection = DailyMarketTechnicalUniversePriceSelectionV1.from_page(
        query, result.read_page(request), "S0001"
    )
    return stock, selection


def test_live_general_report_actions_emit_context_without_writing_or_running():
    app = _app()
    workspace = StockResearchWorkspace(_ReadService())
    context = ResearchStockContextDTO(
        stock_code="2330",
        source_kind="explicit_latest_stock_research",
        source_label="使用者明選的一般個股查詢",
        source_workspace="stock_research",
    )
    favorites = []
    backtest_requests = []
    loaded = []
    failed = []
    workspace.report_view.reportLoaded.connect(loaded.append)
    workspace.report_view.reportFailed.connect(failed.append)
    workspace.favoriteRequested.connect(favorites.append)
    workspace.prepareBacktestRequested.connect(backtest_requests.append)
    try:
        workspace.set_context(context)
        _wait(app, lambda: bool(loaded or failed) and not workspace.report_view.is_busy())
        assert failed == []

        assert workspace.favorite_action.isEnabled(), (
            workspace.report_view._loaded_report,
            workspace.report_view._request_id,
            workspace.report_view._completed_report_request_id,
            workspace.report_view.context,
            workspace.report_view.get_loaded_report_snapshot(),
        )
        assert workspace.prepare_backtest_action.isEnabled()
        assert not workspace.price_comparison_action.isEnabled()
        workspace.favorite_action.click()
        workspace.prepare_backtest_action.click()
        assert favorites == [context]
        assert backtest_requests == [context]

        historical = ResearchStockContextDTO(
            stock_code="2330",
            result_id="saved-result-2330",
            identity_status="exact_saved_selection",
            source_kind="daily_market_research_snapshot",
            source_workspace="stock_research",
        )
        snapshot = create_stock_research_report_projection_snapshot(
            _report("2330"), historical
        )
        workspace.show_saved_report_snapshot(snapshot)
        assert workspace.favorite_action.isEnabled()
        assert not workspace.prepare_backtest_action.isEnabled()
        workspace.prepare_backtest_action.click()
        assert backtest_requests == [context]
    finally:
        workspace.request_close()
        _wait(app, lambda: not workspace.is_busy())
        workspace.close()
        app.processEvents()


def test_price_actions_emit_only_exact_original_selection(
    exact_price_store: dict[str, Any],
):
    app = _app()
    stock, selection = _price_selection(exact_price_store)
    workspace = StockResearchWorkspace(_ReadService())
    favorites = []
    comparisons = []
    backtest_requests = []
    workspace.favoriteRequested.connect(favorites.append)
    workspace.priceComparisonRequested.connect(comparisons.append)
    workspace.prepareBacktestRequested.connect(backtest_requests.append)
    try:
        workspace.show_price_research(stock, selection)
        assert workspace.favorite_action.isEnabled()
        assert workspace.price_comparison_action.isEnabled()
        assert not workspace.prepare_backtest_action.isEnabled()
        workspace.favorite_action.click()
        workspace.price_comparison_action.click()
        workspace.prepare_backtest_action.click()
        assert len(favorites) == 1
        assert favorites[0].source_kind == "technical_price_saved_source"
        assert comparisons == [selection]
        assert backtest_requests == []

        workspace.price_research_view._origin_selection = object()
        workspace._sync_product_action_state()
        assert not workspace.favorite_action.isEnabled()
        assert not workspace.price_comparison_action.isEnabled()
        workspace.price_comparison_action.click()
        assert comparisons == [selection]
    finally:
        workspace.request_close()
        _wait(app, lambda: not workspace.is_busy())
        workspace.close()
        app.processEvents()


class _BacktestPrefillHost(QWidget):
    """只提供正式單股預填方法所需的 Qt 控制項。"""

    prepare_stock_research = BacktestView.prepare_stock_research

    def __init__(self):
        super().__init__()
        self._shutting_down = False
        self.worker = None
        self.research_lab_mode_combo = QComboBox(self)
        self.research_lab_mode_combo.addItem("單股", "single_stock")
        self.stock_mode_combo = QComboBox(self)
        self.stock_mode_combo.addItem("單一股票")
        self.stock_code_input = QLineEdit(self)
        self.config_panel = QWidget(self)
        self.config_panel.setLayout(QVBoxLayout())
        self.collapsed = True

    def _set_config_panel_collapsed(self, value: bool) -> None:
        self.collapsed = value

    def save_watchlist(self, *_args, **_kwargs):
        raise AssertionError("單股研究預填不得保存觀察清單")

    def execute_backtest(self, *_args, **_kwargs):
        raise AssertionError("單股研究預填不得執行回測")


class _Status:
    def __init__(self):
        self.messages = []

    def showMessage(self, message):
        self.messages.append(message)


def _backtest_route_host(context: ResearchStockContextDTO | None):
    prefill = _BacktestPrefillHost()
    status = _Status()
    routes = []
    host = SimpleNamespace(
        _shutdown_close_requested=False,
        stock_research_workspace=SimpleNamespace(
            _live_general_backtest_context=lambda: context
        ),
        backtest_view=prefill,
        product_shell=SimpleNamespace(activate_route=routes.append),
        statusBar=lambda: status,
    )
    return host, prefill, routes, status


def test_main_single_stock_backtest_route_rejects_saved_price_and_stale_contexts():
    app = _app()
    live = ResearchStockContextDTO(
        stock_code="2330", source_kind="explicit_latest_stock_research",
        source_label="目前明選的一般個股查詢",
    )
    host, prefill, routes, status = _backtest_route_host(live)
    MainWindow._prepare_stock_detail_backtest(host, live)
    assert routes == ["backtests"]
    assert prefill.stock_code_input.text() == "2330"
    assert prefill.collapsed is False
    assert "只預填單股代號" in status.messages[-1]
    assert not hasattr(prefill, "execute")

    saved = ResearchStockContextDTO(
        stock_code="2330", source_kind="daily_market_research_snapshot",
        result_id="saved-2330", identity_status="exact_saved_selection",
    )
    price = ResearchStockContextDTO(
        stock_code="2330", source_kind="technical_price_saved_source",
        result_id="price-selection-2330", identity_status="exact_saved_selection",
    )
    original_code = prefill.stock_code_input.text()
    assert BacktestView.prepare_stock_research(prefill, saved) is False
    assert BacktestView.prepare_stock_research(prefill, price) is False
    assert prefill.stock_code_input.text() == original_code

    stale = ResearchStockContextDTO(
        stock_code="2330", source_kind="explicit_latest_stock_research",
        source_label="已被另一個研究選取取代的脈絡",
    )
    stale_host, stale_prefill, stale_routes, _stale_status = _backtest_route_host(live)
    MainWindow._prepare_stock_detail_backtest(stale_host, stale)
    assert stale_routes == []
    assert stale_prefill.stock_code_input.text() == ""

    for rejected in (saved, price):
        rejected_host, rejected_prefill, rejected_routes, _ = _backtest_route_host(None)
        MainWindow._prepare_stock_detail_backtest(rejected_host, rejected)
        assert rejected_routes == []
        assert rejected_prefill.stock_code_input.text() == ""
        rejected_prefill.deleteLater()
    prefill.deleteLater()
    stale_prefill.deleteLater()
    app.processEvents()
