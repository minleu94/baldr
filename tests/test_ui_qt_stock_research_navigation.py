"""持倉與觀察清單共用同一個個股研究報告 context 入口。"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sys

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QMainWindow

from app_module.dtos.portfolio_dtos import PortfolioDTO, PositionDTO
from app_module.research_session import ResearchSessionStore, ResearchStockContextDTO
from ui_qt.main import MainWindow
from ui_qt.views.portfolio_view import PortfolioView
from ui_qt.views.watchlist_view import WatchlistView


def _app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


class WatchlistStub:
    def query_stock_names(self, codes):
        return {"2330": "台積電", "1101": "台泥"}

    def get_stocks(self):
        return [{"stock_code": "2330", "stock_name": "台積電"}]


@dataclass
class PortfolioConfig:
    output_root: Path

    @property
    def broker_branch_registry_file(self) -> Path:
        return self.output_root / "missing_registry.csv"

    @property
    def data_dir(self) -> Path:
        return self.output_root

    def resolve_output_path(self, relative_path: str) -> Path:
        return self.output_root / relative_path


class PortfolioStub:
    def __init__(self, config: PortfolioConfig):
        self.config = config
        self.position = PositionDTO(
            position_id="default:2330",
            portfolio_id="default",
            stock_code="2330",
            stock_name="台積電",
            quantity=1000,
            average_cost=100,
            invested_amount=100000,
            current_price=110,
            unrealized_pnl=10000,
            unrealized_pnl_pct=0.1,
        )

    def get_portfolio(self):
        return PortfolioDTO(
            portfolio_id="default",
            portfolio_name="Default",
            total_positions=1,
            active_positions=1,
            positions=[self.position],
            total_invested_amount=100000,
            total_realized_pnl=0,
        )

    def list_positions(self):
        return [self.position]

    def get_current_price(self, stock_code):
        return self.position.current_price if stock_code == "2330" else None

    def list_trades(self):
        return []


class JournalStub:
    def list_journal_entries(self, stock_code=""):
        return []


class ConditionStub:
    def evaluate(self, _position, _snapshot):
        return type(
            "Condition",
            (),
            {
                "status": "valid",
                "label": "仍符合",
                "source_label": "手動",
                "entry_total_score": "-",
                "current_total_score": "-",
                "reasons": [],
                "details": {},
            },
        )()


def _write_recommendation_result(output_root: Path, result_id: str, stock_code: str) -> None:
    result_path = output_root / "recommendation" / "runs" / f"{result_id}.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(
            {
                "result_id": result_id,
                "recommendations": [{"stock_code": stock_code}],
            }
        ),
        encoding="utf-8",
    )


def test_watchlist_and_portfolio_emit_same_context_contract(tmp_path: Path) -> None:
    _app()
    watchlist = WatchlistView(WatchlistStub())
    portfolio = PortfolioView(
        portfolio_service=PortfolioStub(PortfolioConfig(tmp_path)),
        journal_service=JournalStub(),
        condition_monitor=ConditionStub(),
    )
    portfolio._update_lifecycle_review = lambda *_args, **_kwargs: None

    watch_contexts: list[object] = []
    portfolio_contexts: list[object] = []
    watchlist.stockResearchRequested.connect(watch_contexts.append)
    portfolio.stockResearchRequested.connect(portfolio_contexts.append)

    watchlist.stocks_table.selectRow(0)
    watchlist.stock_research_btn.click()
    portfolio.select_stock("2330")
    portfolio.btn_stock_research.click()

    assert len(watch_contexts) == 1
    assert len(portfolio_contexts) == 1
    assert isinstance(watch_contexts[0], ResearchStockContextDTO)
    assert isinstance(portfolio_contexts[0], ResearchStockContextDTO)
    assert watch_contexts[0].stock_code == portfolio_contexts[0].stock_code == "2330"
    assert watch_contexts[0].source_workspace == "watchlist"
    assert portfolio_contexts[0].source_workspace == "portfolio"
    assert watch_contexts[0].source_kind == "recommendation"
    assert portfolio_contexts[0].source_kind == "portfolio"

    # Returns use the existing model, so selection/filter state is not rebuilt.
    assert watchlist.select_stock("2330") is True
    assert portfolio.select_stock("2330") is True
    watchlist.close()
    portfolio.close()


def test_mainwindow_portfolio_return_requires_current_exact_result_identity(
    tmp_path: Path,
) -> None:
    """真實 Portfolio signal + MainWindow return route 不得以同股替代。"""

    _app()
    result_r1 = "result-r1"
    result_r2 = "result-r2"
    _write_recommendation_result(tmp_path, result_r1, "2330")
    _write_recommendation_result(tmp_path, result_r2, "2330")

    portfolio_service = PortfolioStub(PortfolioConfig(tmp_path))
    position = portfolio_service.position
    position.source_type = "recommendation_result"
    position.source_id = result_r1
    position.source_summary = {"result_id": result_r1, "stock_code": "2330"}
    portfolio = PortfolioView(
        portfolio_service=portfolio_service,
        journal_service=JournalStub(),
        condition_monitor=ConditionStub(),
    )
    portfolio._update_lifecycle_review = lambda *_args, **_kwargs: None

    class RouteHarness(MainWindow):
        def __init__(self) -> None:
            # Use the real MainWindow methods without constructing the full app.
            QMainWindow.__init__(self)

    window = RouteHarness()
    window.portfolio_view = portfolio
    window.research_session_store = ResearchSessionStore()
    window._select_main_workspace = lambda workspace: setattr(window, "last_workspace", workspace)
    portfolio.stockResearchRequested.connect(
        lambda value: window.research_session_store.set_stock_context(value, source="test")
    )

    # Actual PortfolioView button signal creates the linked context.
    assert portfolio.select_stock("2330") is True
    portfolio.btn_stock_research.click()
    snapshot = window.research_session_store.get_snapshot()
    assert snapshot.stock_context is not None
    assert snapshot.stock_context.result_id == result_r1

    # First prove the exact current source can be restored through MainWindow.
    portfolio.positions_table.clearSelection()
    portfolio.selected_stock_code = ""
    MainWindow._return_to_research_source(window, snapshot)
    assert window.last_workspace == "portfolio"
    assert portfolio.selected_stock_code == "2330"

    # Simulate the real stale-report case: the current position now points to
    # R2 while the already-open report still carries R1.
    position.source_id = result_r2
    position.source_summary = {"result_id": result_r2, "stock_code": "2330"}
    portfolio.positions_table.clearSelection()
    portfolio.selected_stock_code = ""
    MainWindow._return_to_research_source(window, snapshot)

    assert portfolio.selected_stock_code == ""
    assert not portfolio.positions_table.selectionModel().hasSelection()
    assert "未精確定位" in window.statusBar().currentMessage()

    portfolio.close()
    window.deleteLater()
    _app().processEvents()
