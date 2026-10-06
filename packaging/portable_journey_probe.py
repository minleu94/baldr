"""Exercise saved-workflow and cancellation paths inside the frozen Baldr runtime."""

from pathlib import Path
import json
import os
import subprocess
import sys
import threading
import time
from datetime import date, datetime, timezone
from decimal import Decimal


def _deny_network(event: str, _args: tuple[object, ...]) -> None:
    if event in {"socket.connect", "socket.getaddrinfo"}:
        raise PermissionError("portable journey probe has no provider network access")


sys.addaudithook(_deny_network)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app_module.dtos import RegimeResultDTO
from app_module.dtos.portfolio_dtos import PortfolioDTO, PositionDTO
from app_module.exceptions import BacktestCancelledError
from app_module.recommendation.contracts import (
    Context,
    DecisionBatch,
    ExecutionStatus,
    RecommendationExecution,
    ReferenceKind,
    Request,
    VersionReference,
)
from app_module.research_session import ResearchStockContextDTO
from app_module.stock_research_report_dtos import (
    StockPricePointDTO,
    StockResearchReportDTO,
)
from data_module.watchlist_repository import WatchlistRepository
from decision_module.recommendation.contracts import RecommendationItem
from ui_qt.views.market_regime_view import MarketRegimeView
from ui_qt.views.portfolio_view import PortfolioView
from ui_qt.views.recommendation.execution_coordinator import RecommendationExecutionRequest
from ui_qt.views.recommendation_view import RecommendationView
from ui_qt.views.stock_research_report_view import StockResearchReportView
from ui_qt.views.workbench_view import UnifiedDecisionWorkbenchView
from ui_qt.workers.task_worker import TaskWorker


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _under(root: Path, candidate: Path) -> bool:
    return candidate == root or candidate.is_relative_to(root)


class _IsolatedConfig:
    def __init__(self, output_root: Path) -> None:
        self.output_root = output_root
        self.data_dir = output_root

    @property
    def broker_branch_registry_file(self) -> Path:
        return self.output_root / "missing_broker_branch_registry.csv"

    def resolve_output_path(self, relative_path: str) -> Path:
        path = self.output_root / relative_path
        path.mkdir(parents=True, exist_ok=True)
        return path


class _MarketFixture:
    def detect_regime(self) -> RegimeResultDTO:
        return RegimeResultDTO(
            regime="Trend",
            confidence=0.82,
            details={
                "date": "2026-10-05",
                "close_above_ma60": True,
                "ma20_slope_positive": False,
            },
            regime_name_cn="portable fixture",
        )

    def get_strategy_config(self, _regime: str) -> dict[str, object]:
        return {}


class _MissingMarketFixture(_MarketFixture):
    def detect_regime(self) -> RegimeResultDTO:
        return RegimeResultDTO(
            regime="Trend",
            confidence=0.82,
            details={},
            regime_name_cn="portable fixture",
        )


class _StockReadFixture:
    def read_report(self, stock_code: str, **_kwargs: object) -> StockResearchReportDTO:
        return StockResearchReportDTO(
            stock_code=stock_code,
            stock_name="portable fixture",
            as_of="2026-10-02",
            price_points=(
                StockPricePointDTO(
                    data_date="2026-10-02",
                    close_price=Decimal("100"),
                    source_id="portable-journey-fixture",
                ),
            ),
            limitations=("synthetic isolated fixture; no provider or database",),
        )


class _PortfolioReadFixture:
    def __init__(self, config: _IsolatedConfig) -> None:
        self.config = config
        self.position = PositionDTO(
            position_id="portable:2330",
            portfolio_id="portable",
            stock_code="2330",
            stock_name="portable fixture",
            quantity=1000,
            average_cost=100,
            invested_amount=100000,
            current_price=None,
            unrealized_pnl=None,
            unrealized_pnl_pct=None,
        )

    def get_portfolio(self) -> PortfolioDTO:
        return PortfolioDTO(
            portfolio_id="portable",
            portfolio_name="portable fixture",
            total_positions=1,
            active_positions=1,
            positions=[self.position],
            total_invested_amount=100000,
            total_realized_pnl=0,
        )

    def list_positions(self) -> list[PositionDTO]:
        return [self.position]

    def list_trades(self) -> list[object]:
        return []

    def get_current_price(self, _stock_code: str) -> None:
        return None


class _JournalReadFixture:
    def list_journal_entries(self, stock_code: str = "") -> list[object]:
        return []


class _ConditionFixture:
    def evaluate(self, _position: object, _snapshot: object) -> object:
        return type(
            "Condition",
            (),
            {
                "status": "unknown",
                "label": "unknown fixture",
                "source_label": "isolated fixture",
                "entry_total_score": "-",
                "current_total_score": "-",
                "reasons": [],
                "details": {},
            },
        )()


def _recommendation_execution(result_id: str) -> RecommendationExecution:
    config = {
        "patterns": {"selected": ["portable_fixture"]},
        "signals": {"technical_indicators": []},
        "filters": {},
        "profile_id": "portable_fixture",
        "profile_version": "1",
        "regime": "fixture_only",
    }
    request = Request(
        config_snapshot=RecommendationExecutionRequest(config).config_snapshot,
        profile_ref=VersionReference(ReferenceKind.PROFILE, "portable_fixture", "1"),
        max_stocks=1,
        top_n=1,
    )
    item = RecommendationItem(
        stock_code="2330",
        stock_name="portable fixture",
        close_price=100,
        price_change=0,
        rule_score=0,
        indicator_score=0,
        pattern_score=0,
        volume_score=0,
        reason_text="synthetic isolated display fixture",
        industry="fixture",
        regime_match=None,
        rank=1,
    )
    moment = datetime(2026, 10, 5, tzinfo=timezone.utc)
    return RecommendationExecution(
        result_id=result_id,
        request=request,
        context=Context(
            as_of_date=date(2026, 10, 5),
            created_at=moment,
            available_at=moment,
            decision_at=moment,
        ),
        status=ExecutionStatus.COMPLETED,
        decision=DecisionBatch(items=(item,), regime="fixture_only"),
    )


def _wait_for(app: QApplication, predicate, timeout_seconds: float = 15) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.005)
    app.processEvents()
    _require(bool(predicate()), "isolated workspace fixture timed out")


def _run() -> dict[str, object]:
    if not getattr(sys, "frozen", False) or not hasattr(sys, "_MEIPASS"):
        raise RuntimeError("run this probe through the frozen baldr.exe")
    if len(sys.argv) != 2:
        raise RuntimeError("usage: baldr.exe -c <runner> packaging/portable_journey_probe.py <case-root>")

    bundle_root = Path(sys._MEIPASS).resolve()
    case_argument = Path(sys.argv[1]).expanduser()
    if not case_argument.is_absolute():
        raise RuntimeError("probe case root must be absolute")
    case_root = case_argument.resolve()
    case_root.mkdir(parents=True, exist_ok=True)

    data_root = Path(os.environ["DATA_ROOT"]).expanduser().resolve()
    output_root = Path(os.environ["OUTPUT_ROOT"]).expanduser().resolve()
    if not _under(case_root, data_root) or not _under(case_root, output_root):
        raise RuntimeError("DATA_ROOT and OUTPUT_ROOT must stay inside the isolated probe case")

    import app_module
    import data_module
    import ui_qt

    for package in (app_module, data_module, ui_qt):
        package_path = Path(package.__file__).resolve()
        if not _under(bundle_root, package_path):
            raise RuntimeError(f"import escaped frozen bundle: {package_path}")
    for module_name in (
        "ui_qt.views.market_regime_view",
        "ui_qt.views.portfolio_view",
        "ui_qt.views.recommendation_view",
        "ui_qt.views.stock_research_report_view",
    ):
        module_path = Path(sys.modules[module_name].__file__).resolve()
        if not _under(bundle_root, module_path):
            raise RuntimeError(f"workspace module escaped frozen bundle: {module_path}")

    app = QApplication.instance() or QApplication([])

    # Market regime UI renders a bounded, synthetic receipt and keeps absent
    # technical conditions unknown rather than filling them with success.
    market_view = MarketRegimeView(_MarketFixture())
    market_view.resize(900, 600)
    market_view._detect_regime()
    market_view.show()
    app.processEvents()
    _require("2026-10-05" in market_view.layer1_confidence.text(),
             "market fixture date was not displayed")
    market_missing_view = MarketRegimeView(_MissingMarketFixture())
    market_missing_view._detect_regime()
    _require(market_missing_view.layer2_label.text().count("\u672a\u77e5") >= 2,
             "missing market conditions were not rendered as unknown")
    _require("\u672a\u77e5" in market_missing_view.market_risk_label.text(),
             "missing market date did not remain unknown")
    market_display = {
        "regime_date_displayed": "2026-10-05" in market_view.layer1_confidence.text(),
        "missing_conditions": "unknown",
        "missing_market_date_display": market_missing_view.layer1_confidence.text(),
    }
    market_missing_view.close()
    market_view.close()
    app.processEvents()

    route_calls: list[str] = []
    home_stock_contexts: list[object] = []
    view = UnifiedDecisionWorkbenchView(
        auto_refresh=False,
        navigate_to_market_explore_callback=lambda: route_calls.append("market"),
        navigate_to_portfolio_callback=lambda: route_calls.append("portfolio"),
        navigate_to_recommendation_callback=lambda: route_calls.append("selection"),
        navigate_to_stock_research_callback=home_stock_contexts.append,
    )
    for purpose in ("market", "portfolio", "selection"):
        button = view.home_purpose_buttons[purpose]
        _require(button.isEnabled(), f"home purpose is disabled: {purpose}")
        button.click()
    view.home_stock_input.setText("2330")
    view.home_purpose_buttons["stock"].click()
    app.processEvents()
    _require(route_calls == ["market", "portfolio", "selection"]
             and len(home_stock_contexts) == 1
             and getattr(home_stock_contexts[0], "stock_code", "") == "2330",
             f"home purpose callbacks changed: {route_calls!r}")
    _require(view.advanced_workbench_panel.is_collapsed(),
             "guided navigation expanded advanced details")
    stock_context = home_stock_contexts[0]
    view.close()
    view.deleteLater()
    app.processEvents()

    # Stock report loads a synthetic read DTO through its real worker path;
    # missing advice/ML remains unavailable and is never inferred.
    stock_view = StockResearchReportView(_StockReadFixture(), stock_context)
    stock_view.resize(900, 650)
    stock_view.show()
    _wait_for(app, lambda: stock_view._loaded_report is not None)
    for worker in tuple(stock_view._workers):
        _require(worker.wait(10_000), "stock report fixture worker did not stop")
    app.processEvents()
    stock_report = stock_view._loaded_report
    _require(stock_report is not None and stock_report.stock_code == "2330",
             "stock report fixture was not loaded")
    _require("100" in stock_view._summary_values["latest_price"].text(),
             "synthetic stock price was not displayed")
    _require(stock_report.ml.status == "unavailable"
             and stock_report.advice.recommendation is None,
             "stock fixture implied unavailable ML/advice was available")
    stock_display = {
        "stock_code": stock_report.stock_code,
        "as_of": stock_report.as_of,
        "displayed_latest_price": stock_view._summary_values["latest_price"].text(),
        "ml_status": stock_report.ml.status,
        "advice_status": stock_report.advice.status,
    }
    stock_view.close()
    app.processEvents()

    # Render a synthetic completed recommendation execution through the real
    # result presentation path. This intentionally avoids canonical repository
    # reads: the fixture has no filesystem identity, and no strategy, model fit,
    # database, or provider is involved in this display check.
    selection_root = output_root / "portable_journey" / "selection"
    selection_root.mkdir(parents=True, exist_ok=True)
    selection_execution = _recommendation_execution("portable-journey-selection")
    selection_view = RecommendationView(
        recommendation_service=object(),
        regime_service=_MarketFixture(),
        personal_policy_path=selection_root / "missing-policy.json",
    )
    selection_view.resize(1000, 700)
    selection_view.show()
    selection_view._on_recommendation_finished(selection_execution)
    app.processEvents()
    _require(selection_view.current_execution is selection_execution,
             "synthetic selection execution was not rendered")
    _require(selection_view.recommendations_model is not None
             and selection_view.recommendations_model.rowCount() == 1,
             "selection fixture was not displayed")
    _require(len(selection_view.current_execution.items) == 1
             and selection_view.current_execution.items[0].stock_code == "2330",
             "selection fixture stock was not displayed")
    selection_display = {
        "status": "synthetic_execution_display_only",
        "result_id": selection_execution.result_id,
        "rows": selection_view.recommendations_model.rowCount(),
        "stock_code": selection_view.current_execution.items[0].stock_code,
        "persisted": False,
        "canonical_repository_readback": "blocked_by_existing_nofollow_guard",
    }
    selection_view.close()
    app.processEvents()

    # Portfolio view uses one synthetic position with no quote. The value stays
    # explicitly unavailable instead of falling back to cost or an old price.
    portfolio_config = _IsolatedConfig(output_root / "portable_journey" / "portfolio")
    portfolio_config.output_root.mkdir(parents=True, exist_ok=True)
    portfolio_view = PortfolioView(
        portfolio_service=_PortfolioReadFixture(portfolio_config),
        journal_service=_JournalReadFixture(),
        condition_monitor=_ConditionFixture(),
    )
    portfolio_view.resize(1000, 700)
    portfolio_view.show()
    app.processEvents()
    _require(portfolio_view.positions_model is not None
             and portfolio_view.positions_model.rowCount() == 1,
             "isolated portfolio position was not displayed")
    _require("N/A" in portfolio_view.card_net_val.value_label.text(),
             "portfolio total was shown despite a missing current quote")
    portfolio_display = {
        "positions": portfolio_view.positions_model.rowCount(),
        "net_value": portfolio_view.card_net_val.value_label.text(),
        "current_quote": "missing_fixture",
        "trade_rows": portfolio_view.trades_model.rowCount()
        if portfolio_view.trades_model is not None else 0,
    }
    portfolio_view.close()
    app.processEvents()

    # Persist only a synthetic user-space fixture under the isolated output root.
    watchlist_path = output_root / "portable_journey" / "watchlists.db"
    repository = WatchlistRepository(watchlist_path, initialize=True)
    payload = {
        "version": 1,
        "name": "portable journey fixture",
        "description": "isolated save and reopen probe",
        "created_at": "2026-10-06T00:00:00+00:00",
        "updated_at": "2026-10-06T00:00:00+00:00",
        "items": [
            {
                "stock_code": "2330",
                "stock_name": "fixture",
                "added_at": "2026-10-06T00:00:00+00:00",
                "source": "manual",
                "source_id": "portable-journey",
                "notes": "",
                "tags": [],
                "decision_identity": {
                    "result_id": "",
                    "stock_code": "2330",
                    "source_snapshot_id": "",
                    "source_snapshot_hash": "",
                    "decision_date": "",
                },
            }
        ],
    }
    revision = repository.save(
        "default", payload, expected_revision=None,
        revision_id="portable-journey-initial", operation="created",
    )
    reopened = WatchlistRepository(watchlist_path).load("default")
    _require(reopened is not None, "saved watchlist could not be reopened")
    _require(reopened[0] == payload and reopened[1] == revision,
             "watchlist readback did not match the saved fixture")

    # Reopen the same isolated saved fixture through a fresh frozen process.
    readback_code = (
        "import json,sys; from pathlib import Path; "
        "from data_module.watchlist_repository import WatchlistRepository; "
        "value=WatchlistRepository(Path(sys.argv[1])).load('default'); "
        "assert value is not None; "
        "print(json.dumps({'revision':value[1],"
        "'stock_code':value[0]['items'][0]['stock_code']}))"
    )
    child = subprocess.run(
        [sys.executable, "-c", readback_code, str(watchlist_path)],
        cwd=case_root,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    _require(child.returncode == 0,
             f"frozen readback process failed: {child.stderr[-2000:]}")
    child_report = json.loads(child.stdout.strip().splitlines()[-1])
    _require(child_report == {"revision": revision, "stock_code": "2330"},
             f"frozen process readback mismatch: {child_report!r}")

    # Cancel a cooperative worker, then prove a fresh worker still completes.
    task_started = threading.Event()
    cancel_observed = threading.Event()

    def wait_for_cancel(cancel_callback):
        task_started.set()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if cancel_callback():
                raise BacktestCancelledError("portable journey cancellation fixture")
            time.sleep(0.005)
        raise TimeoutError("cancellation callback was not delivered")

    cancelled_worker = TaskWorker(wait_for_cancel)
    cancelled_worker.cancelled.connect(cancel_observed.set)
    cancelled_worker.start()
    _require(task_started.wait(5), "cancellable worker did not start")
    cancelled_worker.cancel(cooperative=True, wait=False)
    _require(cancelled_worker.wait(10_000), "cancelled worker did not stop")
    cancel_deadline = time.monotonic() + 5
    while not cancel_observed.is_set() and time.monotonic() < cancel_deadline:
        app.processEvents()
        time.sleep(0.005)
    _require(cancel_observed.is_set(), "cancelled worker did not publish cancellation")

    restart_result: list[object] = []
    restart_observed = threading.Event()

    def finish_restart(value: object) -> None:
        restart_result.append(value)
        restart_observed.set()

    restarted_worker = TaskWorker(lambda: {"status": "passed", "value": "restarted"})
    restarted_worker.finished.connect(finish_restart)
    restarted_worker.start()
    _require(restarted_worker.wait(10_000), "replacement worker did not stop")
    restart_deadline = time.monotonic() + 5
    while not restart_observed.is_set() and time.monotonic() < restart_deadline:
        app.processEvents()
        time.sleep(0.005)
    _require(restart_observed.is_set(), "replacement worker did not return a result")
    _require(restart_result == [{"status": "passed", "value": "restarted"}],
             f"replacement worker returned an unexpected result: {restart_result!r}")

    report: dict[str, object] = {
        "status": "passed",
        "frozen": True,
        "bundle_root": str(bundle_root),
        "case_root": str(case_root),
        "home_purposes": route_calls,
        "home_stock_context": {
            "stock_code": stock_context.stock_code,
            "source_kind": stock_context.source_kind,
            "source_workspace": stock_context.source_workspace,
        },
        "workspace_displays": {
            "market": market_display,
            "stock": stock_display,
            "selection": selection_display,
            "portfolio": portfolio_display,
        },
        "watchlist_path": str(watchlist_path),
        "watchlist_revision": revision,
        "fresh_process_readback": child_report,
        "worker_cancelled": cancel_observed.is_set(),
        "worker_restarted": restart_result[0],
        "provider_network_allowed": False,
        "true_market_database_used": False,
    }
    report_path = case_root / "portable_journey_probe.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _require(json.loads(report_path.read_text(encoding="utf-8")) == report,
             "probe report save/reopen check failed")
    return report


if __name__ == "__main__":
    result = _run()
    print(json.dumps(result, ensure_ascii=False))
