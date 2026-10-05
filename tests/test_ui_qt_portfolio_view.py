import os
import sqlite3
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QBoxLayout,
    QFileDialog,
    QMessageBox,
    QMainWindow,
    QSizePolicy,
    QStackedWidget,
    QWidget,
)
from PySide6.QtTest import QTest

from app_module.dtos.portfolio_dtos import (
    PortfolioDTO,
    PositionDTO,
    RecordedTradeCostSummaryDTO,
    TradeDTO,
)
from app_module.recommendation.legacy_dtos import (
    RecommendationDTO,
    RecommendationResultDTO,
)
from app_module.portfolio_source_adapter import build_recommendation_trade_source
from app_module.decision_presentation import (
    PositionHealthPresentationDTO,
    PositionHealthReadModel,
)
from app_module.paper_portfolio_snapshot_repository import (
    PaperPortfolioPositionSnapshot,
    PaperPortfolioSnapshot,
    PaperPortfolioSnapshotRepository,
)
from app_module.paper_trade_ledger import PaperTradeLedgerRepository
from ui_qt.views.portfolio_view import (
    AddTradeDialog,
    PortfolioView,
    _format_recorded_trade_costs,
)
import ui_qt.views.portfolio_view as portfolio_view_module
from ui_qt.workers.task_worker import TaskWorker, running_task_workers


def app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


class FakeIndustryMapper:
    def get_stock_name(self, code: str) -> str | None:
        return {"2330": "台積電", "2317": "鴻海"}.get(code)


class FakeRecommendationService:
    def __init__(self):
        self.industry_mapper = FakeIndustryMapper()


def test_add_trade_dialog_autofills_stock_name_and_rejects_unknown_code():
    app()
    dialog = AddTradeDialog(recommendation_service=FakeRecommendationService())

    dialog.code_input.setText("2330")
    assert dialog.name_input.text() == "台積電"
    assert dialog.code_error_label.text() == ""

    dialog.name_input.clear()
    dialog.code_input.setText("999999")
    assert "找不到正式股票代號" in dialog.code_error_label.text()


def test_add_trade_dialog_prefills_taiwan_fee_and_sell_tax():
    app()
    dialog = AddTradeDialog(recommendation_service=FakeRecommendationService())

    dialog.qty_input.setValue(1000)
    dialog.price_input.setValue(100)
    dialog.side_combo.setCurrentIndex(dialog.side_combo.findData("buy"))
    assert dialog.fees_input.value() == 143
    assert dialog.taxes_input.value() == 0

    dialog.side_combo.setCurrentIndex(dialog.side_combo.findData("sell"))
    assert dialog.fees_input.value() == 143
    assert dialog.taxes_input.value() == 300


@dataclass
class FakeConfig:
    output_root: Path

    @property
    def broker_branch_registry_file(self) -> Path:
        return self.output_root / "missing_broker_branch_registry.csv"

    @property
    def data_dir(self) -> Path:
        return self.output_root

    def resolve_output_path(self, relative_path: str) -> Path:
        return self.output_root / relative_path


class FakePortfolioService:
    def __init__(self, config: FakeConfig):
        self.config = config
        self.positions = [
            PositionDTO(
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
                source_type="",
                source_id="",
                source_summary={"current_price_date": "2026-06-22"},
            ),
            PositionDTO(
                position_id="default:2317",
                portfolio_id="default",
                stock_code="2317",
                stock_name="鴻海",
                quantity=1000,
                average_cost=150,
                invested_amount=150000,
                current_price=151,
                unrealized_pnl=1000,
                unrealized_pnl_pct=0.0067,
                source_type="recommendation_result",
                source_id="rec-1",
                source_summary={"profile_id": "balanced"},
            ),
        ]
        self.trades = [
            TradeDTO(
                trade_id="t1",
                portfolio_id="default",
                stock_code="2330",
                stock_name="台積電",
                side="buy",
                quantity=1000,
                price=100,
                trade_date="2026-06-20",
            ),
            TradeDTO(
                trade_id="t2",
                portfolio_id="default",
                stock_code="2317",
                stock_name="鴻海",
                side="buy",
                quantity=1000,
                price=150,
                trade_date="2026-06-20",
            ),
        ]
        self.deleted_trade_ids: list[str] = []

    def get_portfolio(self):
        return PortfolioDTO(
            portfolio_id="default",
            portfolio_name="Default",
            total_positions=2,
            active_positions=2,
            positions=self.positions,
            total_invested_amount=250000,
            total_realized_pnl=0,
        )

    def list_positions(self):
        return self.positions

    def list_trades(self):
        return self.trades

    def get_current_price(self, stock_code: str):
        for position in self.positions:
            if position.stock_code == stock_code:
                return position.current_price
        return None

    def delete_trade(self, trade_id: str) -> bool:
        self.deleted_trade_ids.append(trade_id)
        remaining = [trade for trade in self.trades if trade.trade_id != trade_id]
        if len(remaining) == len(self.trades):
            return False
        self.trades = remaining
        return True


class _SequencedAsyncPortfolioService(FakePortfolioService):
    """Hold the first read so refresh generation/cancellation is observable."""

    def __init__(self, config: FakeConfig):
        super().__init__(config)
        self.read_started = threading.Event()
        self.release_first_read = threading.Event()
        self.calls = 0

    def get_portfolio(self):
        self.calls += 1
        if self.calls == 1:
            self.read_started.set()
            self.release_first_read.wait(timeout=5)
        return super().get_portfolio()

    def list_positions(self):
        raise AssertionError("background refresh must reuse the returned PortfolioDTO")


class FakeJournalService:
    def list_journal_entries(self, stock_code: str = ""):
        return []


class FakeConditionResult:
    status = "valid"
    label = "假設仍成立"
    reasons: list[str] = []
    source_label = "手動建立"
    entry_total_score = "-"
    current_total_score = "-"
    details: dict[str, Any] = {}


class FakeConditionMonitor:
    def evaluate(self, _position, _snapshot):
        return FakeConditionResult()


class FakePositionHealthReadService:
    def __init__(self, model: PositionHealthReadModel):
        self.model = model

    def read_latest(self, *, max_age_days: int):
        assert max_age_days == 1
        return self.model


class FakeChipService:
    def get_stock_chip_summary(self, _stock_code: str, period_days: int = 5):
        return {
            "risk_level": "bearish",
            "consecutive_days": -2,
            "accumulated_net": -3000,
            "concentration": 0.25,
            "risk_reasons": ["連續賣超"],
            "quality_counts": {"observed": 3, "estimated": 1, "unavailable": 2},
            "branch_details": [],
        }


def make_portfolio_view(
    tmp_path,
    parent=None,
    position_health_read_service=None,
    portfolio_service=None,
):
    app()
    view = PortfolioView(
        portfolio_service=portfolio_service or FakePortfolioService(FakeConfig(tmp_path)),
        journal_service=FakeJournalService(),
        condition_monitor=FakeConditionMonitor(),
        position_health_read_service=position_health_read_service,
        parent=parent,
    )
    view._update_lifecycle_review = lambda *_args, **_kwargs: None
    view.chip_service = FakeChipService()
    return view


def _make_health_row(stock_code: str = "1418") -> PositionHealthPresentationDTO:
    return PositionHealthPresentationDTO(
        position_id=f"paper:{stock_code}",
        stock_code=stock_code,
        decision_date="2026-09-21",
        available_at="2026-09-21T20:55:48.508928",
        availability_by_source=(("market", "2026-09-21T20:55:48.508928"),),
        source_status="blocked",
        quality="blocked",
        source_snapshot_id="snapshot-1418",
        cohort_key="paper-main",
        previous_state="UNKNOWN",
        proposed_state="WATCH",
        raw_proposed_state="WATCH",
        action_suitability="WATCH",
        condition_status="unknown",
        thesis_status="missing",
        metrics_status="blocked",
        entry_lineage_status="unverified",
        required_human_fields=("entry_lineage",),
        reasons=("source receipt 已封鎖",),
        why="來源 receipt 已封鎖；暫不可判讀。",
        why_not=("source receipt 已封鎖",),
        proposal_event_id=None,
        input_hash=None,
        policy_hash="policy-1418",
        source_trace=("receipt:paper-health-1418", "reason:source-blocked"),
        source_hashes=(("receipt", "sha256:1418"),),
        review_required=True,
        research_only=True,
        auto_action_allowed=False,
        warnings=("人工確認來源",),
        blockers=("position_health_evaluator_blocked",),
    )


def _make_blocked_health_model() -> PositionHealthReadModel:
    return PositionHealthReadModel(
        schema_version="position-health-presentation.v1",
        status="blocked",
        decision_date="2026-09-21",
        observed_at="2026-09-21T20:55:48.508928",
        available_at="2026-09-21T20:55:48.508928",
        source_status="blocked",
        quality="blocked",
        portfolio_id="paper-main",
        source_snapshot_id="snapshot-1418",
        source_snapshot_rows_sha256="sha256:rows",
        cohort_key="paper-main",
        receipt_path="receipt.json",
        result_path="result.json",
        result_sha256="sha256:result",
        receipt_sha256="sha256:receipt",
        warnings=("source receipt 已封鎖",),
        blockers=("position_health_evaluator_blocked",),
        research_only=True,
        apply_transition=False,
        auto_action_allowed=False,
        broker_execution=False,
        formal_credit=False,
        positions=(_make_health_row(),),
    )


def _wait_until(predicate, timeout_seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        app().processEvents()
        if predicate():
            return True
        QTest.qWait(10)
    app().processEvents()
    return bool(predicate())


def test_portfolio_active_summary_lists_position_count_and_top_symbols(tmp_path):
    view = make_portfolio_view(tmp_path)

    view.refresh_all()

    assert "活躍持倉：2 檔" in view.active_positions_summary_label.text()
    assert "2330 台積電" in view.active_positions_summary_label.text()
    assert view.card_net_val.title_label.text() == "持倉市值（未含現金）"
    assert view.card_net_val.value_label.text() == "TWD 261,000.00"
    assert "已標記市值 2/2 檔" in view.active_positions_summary_label.text()


def test_portfolio_selected_position_shows_shared_decision_presentation(tmp_path):
    view = make_portfolio_view(tmp_path)

    view.refresh_all()
    assert view.select_stock("2317") is True

    detail_text = view.position_presentation_label.text()
    assert "研究路徑：市場總覽 → 產業／市場探索 → 關鍵股研究 → 觀察清單 → 持倉覆盤" in detail_text
    assert "動作適合度：持有" in detail_text
    assert "排名分數：未知（僅作排序，不等於機率）" in detail_text
    assert "校準機率：不可用（研究中）" in detail_text
    assert "成本基準：TWD 150.00" in detail_text
    assert "來源追溯：recommendation_result；rec-1" in detail_text


def test_portfolio_return_uses_position_id_after_table_sort_and_keeps_trade_filter(tmp_path):
    recommendation = RecommendationDTO(
        stock_code="2317",
        stock_name="鴻海",
        close_price=Decimal("151.0"),
        price_change=0.01,
        total_score=75.0,
        indicator_score=70.0,
        pattern_score=72.0,
        volume_score=68.0,
        recommendation_reasons="合成測試推薦",
        industry="電子零組件",
        regime_match=True,
    )
    saved_result = RecommendationResultDTO(
        result_id="rec-1",
        result_name="合成保存結果",
        config={"profile_id": "balanced"},
        recommendations=[recommendation],
        created_at="2026-06-20T09:00:00+08:00",
    )
    trade_source = build_recommendation_trade_source(saved_result, recommendation)
    result_path = tmp_path / "recommendation" / "runs" / "rec-1.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text(
        json.dumps(saved_result.to_dict(), default=str), encoding="utf-8"
    )
    service = FakePortfolioService(FakeConfig(tmp_path))
    linked_position = service.positions[1]
    linked_position.source_summary = trade_source.source_summary
    linked_position.source_snapshot_hash = trade_source.source_snapshot_hash
    view = make_portfolio_view(tmp_path, portfolio_service=service)

    assert view.positions_model is not None
    stock_column = view.positions_model.getVisibleColumns().index("證券代號")
    view.positions_model.sort(stock_column, Qt.AscendingOrder)
    assert tuple(view.positions_model.getDataFrame()["證券代號"]) == ("2317", "2330")

    # The sorted first row is still resolved to the 2317 PositionDTO through
    # hidden position_id, so the saved recommendation identity remains exact.
    assert view.select_stock("2317", "rec-1") is True
    assert view.selected_stock_code == "2317"
    assert "目前只顯示：2317" in view.trade_filter_status_label.text()

    # 完整 legacy writer identity 通過；任一來源 hash 不一致仍 fail closed。
    linked_position.source_snapshot_hash = "sha256:mismatched-fixture"
    assert view.select_stock("2317", "rec-1") is False


def test_portfolio_page_hydrates_summary_and_table_from_one_portfolio_dto(tmp_path):
    class DtoOnlyPortfolioService(FakePortfolioService):
        def list_positions(self):
            raise AssertionError("refresh must use the returned PortfolioDTO")

    app()
    view = PortfolioView(
        portfolio_service=DtoOnlyPortfolioService(FakeConfig(tmp_path)),
        journal_service=FakeJournalService(),
        condition_monitor=FakeConditionMonitor(),
    )

    dto = view._last_portfolio_dto
    assert dto is not None
    assert view.positions_model is not None
    assert view.positions_model.rowCount() == len(dto.positions)
    frame = view.positions_model.getDataFrame()
    assert tuple(frame["證券代號"]) == tuple(
        position.stock_code for position in dto.positions
    )
    assert f"活躍持倉：{dto.active_positions} 檔" in (
        view.active_positions_summary_label.text()
    )
    assert view.card_invested.value_label.text() == (
        f"TWD {dto.total_invested_amount:,.2f}"
    )
    assert "毛額，未扣費稅" in view.card_invested.title_label.text()
    assert "毛額，未扣費稅" in view.card_pnl.title_label.text()


def test_portfolio_ui_exposes_recorded_fees_and_taxes_without_netting() -> None:
    summary = RecordedTradeCostSummaryDTO(
        trade_count=3,
        fees_recorded_count=2,
        fees_missing_count=1,
        taxes_recorded_count=3,
        taxes_missing_count=0,
        fees_by_currency={"TWD": Decimal("12.35")},
        taxes_by_currency={"TWD": Decimal("5.67")},
    )

    text = _format_recorded_trade_costs(summary)

    assert "手續費 TWD 12.35" in text
    assert "交易稅 TWD 5.67" in text
    assert "已記錄 2/3 筆" in text
    assert "1 筆缺值或格式無效" in text
    assert "已記錄 3/3 筆" in text


def test_portfolio_view_reflows_positions_and_existing_evidence_tabs_on_narrow_width(tmp_path):
    view = make_portfolio_view(tmp_path)
    host = QStackedWidget()
    host.setMinimumSize(0, 0)
    host.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
    host.addWidget(view)
    host.show()
    app().processEvents()

    host.resize(1366, 768)
    app().processEvents()
    assert view.main_splitter.orientation() == Qt.Horizontal
    assert view.position_action_layout.direction() == QBoxLayout.LeftToRight
    assert view.positions_table.horizontalScrollBarPolicy() == Qt.ScrollBarAsNeeded

    host.resize(390, 844)
    app().processEvents()
    assert view.main_splitter.orientation() == Qt.Vertical
    assert view.position_action_layout.direction() == QBoxLayout.TopToBottom
    assert view.history_filter_layout.direction() == QBoxLayout.TopToBottom
    assert view.portfolio_detail_tabs.minimumWidth() == 240
    assert "研究建議／待成交佇列／已記錄成交分開判讀" in (
        view.portfolio_refresh_status_label.toolTip()
    )


def test_portfolio_blocked_health_summary_keeps_rows_and_raw_timestamp(tmp_path):
    view = make_portfolio_view(
        tmp_path,
        position_health_read_service=FakePositionHealthReadService(
            _make_blocked_health_model()
        ),
    )

    view.refresh_all()

    summary = view.position_health_summary_label.text()
    assert "有 1 筆評估紀錄，其中 1 筆因來源問題暫不可判讀" in summary
    assert "2026-09-21 20:55" in summary
    assert "2026-09-21T20:55:48.508928" not in summary
    assert "尚無持倉健康評估資料" not in summary
    compact = view.portfolio_compact_context_label.text()
    assert "目前持倉（手動登錄）" in compact
    assert "模擬持倉評估資料" in compact
    assert "2026-09-21T20:55:48.508928" not in compact
    assert "2026-09-21T20:55:48.508928" in view.position_health_summary_label.toolTip()
    assert "position_health_evaluator_blocked" in (
        view.position_health_detail_label.text()
    )
    assert "原始 timestamp：2026-09-21T20:55:48.508928" in (
        view.position_health_detail_label.text()
    )


def test_portfolio_expanded_workspace_scrolls_and_keeps_each_tab_reachable(tmp_path):
    view = make_portfolio_view(
        tmp_path,
        position_health_read_service=FakePositionHealthReadService(
            _make_blocked_health_model()
        ),
    )
    shell = QWidget()
    shell_layout = QBoxLayout(QBoxLayout.LeftToRight, shell)
    navigation = QWidget()
    navigation.setFixedWidth(184)
    shell_layout.addWidget(navigation)
    shell_layout.addWidget(view, 1)
    window = QMainWindow()
    window.setCentralWidget(shell)
    window.statusBar().showMessage("就緒")
    window.resize(1280, 800)
    window.show()
    app().processEvents()

    requested = window.size()
    view.toggle_advanced_portfolio_btn.click()
    app().processEvents()

    actual = window.size()
    assert actual.width() <= requested.width()
    assert actual.height() <= requested.height()
    assert view.paper_health_group.isVisible()
    assert view.position_health_table.isVisible()
    assert view.portfolio_detail_tabs.isVisible()
    assert view.position_action_layout.direction() == QBoxLayout.TopToBottom
    for button in (
        view.btn_record_trade,
        view.btn_stock_research,
        view.btn_import_trades,
        view.btn_add_journal,
        view.btn_refresh,
        view.btn_clear_all,
    ):
        assert button.width() >= button.sizeHint().width()
    assert view.portfolio_advanced_scroll.verticalScrollBar().maximum() > 0
    assert view.positions_table.height() >= (
        view.positions_table.horizontalHeader().height()
        + view.positions_table.verticalHeader().defaultSectionSize() * 2
    )
    assert view.position_health_table.height() >= (
        view.position_health_table.horizontalHeader().height()
        + view.position_health_table.verticalHeader().defaultSectionSize()
    )

    for index in range(view.portfolio_detail_tabs.count()):
        view.portfolio_detail_tabs.setCurrentIndex(index)
        app().processEvents()
        current = view.portfolio_detail_tabs.currentWidget()
        assert current is not None
        assert current.isVisible()
        assert current.height() >= 120

    view.portfolio_detail_tabs.setCurrentIndex(0)
    view.position_health_table.selectRow(0)
    view._show_position_health_row(view.position_health_model.index(0, 0))
    app().processEvents()
    assert view.position_health_detail_label.isVisible()
    assert view.position_health_detail_label.height() >= 3 * view.fontMetrics().height()

    positions_model = view.positions_table.model()
    assert positions_model is not None
    last_column = positions_model.columnCount() - 1
    assert last_column >= 0
    view.positions_table.resizeColumnsToContents()
    view.positions_table.scrollTo(
        positions_model.index(0, last_column),
        QAbstractItemView.PositionAtCenter,
    )
    app().processEvents()
    last_cell = view.positions_table.visualRect(positions_model.index(0, last_column))
    assert last_cell.isValid()
    assert view.positions_table.viewport().rect().contains(last_cell.center())

    window.close()
    view.deleteLater()
    shell.deleteLater()


def test_portfolio_async_refresh_cancels_older_generation_and_uses_one_dto(tmp_path):
    app()
    service = _SequencedAsyncPortfolioService(FakeConfig(tmp_path))
    view = PortfolioView(
        portfolio_service=service,
        journal_service=FakeJournalService(),
        condition_monitor=FakeConditionMonitor(),
        async_refresh=True,
    )

    assert _wait_until(service.read_started.is_set)
    first_generation = view._refresh_generation
    view.refresh_all()
    assert view._refresh_generation == first_generation + 1
    service.release_first_read.set()

    assert _wait_until(lambda: service.calls >= 2 and view._refresh_worker is None)
    assert view._last_portfolio_dto is not None
    assert view.positions_model is not None
    assert view.positions_model.rowCount() == len(view._last_portfolio_dto.positions)
    assert "同一份資料" in view.portfolio_refresh_status_label.text()
    assert view.btn_refresh.isEnabled()


def test_portfolio_stale_worker_callback_cannot_replace_new_generation(tmp_path):
    view = make_portfolio_view(tmp_path)
    previous = view._last_portfolio_dto
    assert previous is not None
    worker = TaskWorker(lambda: previous)
    view._refresh_worker = worker
    view._refresh_generation = 2
    view._worker_generation = 1

    view._on_refresh_worker_finished(previous, 1, worker)

    assert view._last_portfolio_dto is previous
    assert view._refresh_worker is None


def test_main_window_close_cancels_portfolio_worker_without_restarting_pending_generation(
    tmp_path,
):
    """主視窗關閉協調器必須撤銷子頁排隊輪次並等待原生 QThread 結束。"""

    app()
    from ui_qt.main import MainWindow

    service = _SequencedAsyncPortfolioService(FakeConfig(tmp_path))
    window = QMainWindow()
    view = PortfolioView(
        portfolio_service=service,
        journal_service=FakeJournalService(),
        condition_monitor=FakeConditionMonitor(),
        parent=window,
        async_refresh=True,
    )
    window.portfolio_view = view

    assert _wait_until(service.read_started.is_set)
    view.refresh_all()
    assert view._refresh_pending is True

    class CloseEvent:
        accepted = False
        ignored = False

        def accept(self):
            self.accepted = True

        def ignore(self):
            self.ignored = True

    first_event = CloseEvent()
    MainWindow.closeEvent(window, first_event)

    assert first_event.ignored is True
    assert first_event.accepted is False
    assert view._refresh_pending is False
    assert view._refresh_generation > view._worker_generation

    service.release_first_read.set()
    assert _wait_until(
        lambda: view._refresh_worker is None and not running_task_workers()
    )
    assert service.calls == 1

    second_event = CloseEvent()
    MainWindow.closeEvent(window, second_event)
    assert second_event.accepted is True
    assert second_event.ignored is False
    assert view._refresh_worker is None

    window.deleteLater()
    app().processEvents()


def test_portfolio_stress_lab_is_visible_and_research_only(tmp_path):
    view = make_portfolio_view(tmp_path)

    view.stress_scenario_combo.setCurrentIndex(
        view.stress_scenario_combo.findData("concentration_event")
    )
    view.btn_run_stress.click()

    assert "最大持倉事件" in view.stress_summary_label.text()
    assert "可計算" in view.stress_summary_label.text()
    assert "研究用途" in view.stress_detail_label.text()
    assert view.stress_positions_table.model().rowCount() == 2
    assert view._stress_result.research_only is True
    assert view._stress_result.investment_effectiveness_claim is False


def test_portfolio_stress_history_is_read_only_when_not_configured(tmp_path):
    view = make_portfolio_view(tmp_path)

    view.refresh_all()

    assert "Stress 歷史" in view.stress_history_summary_label.text()
    assert "stress_history_not_configured" in view.stress_history_summary_label.text()
    assert view.stress_history_table.model().rowCount() == 1
    assert not (tmp_path / "portfolio").exists()


def test_portfolio_stress_history_requires_confirmation_and_renders_saved_row(tmp_path, monkeypatch):
    view = make_portfolio_view(tmp_path)
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: None)

    view.btn_save_stress_history.click()

    assert view.stress_history_db_path.exists()
    assert view.stress_history_table.model().rowCount() == 1
    assert "狀態：可用" in view.stress_history_summary_label.text()
    assert "writes_allowed=false" in view.stress_history_summary_label.text()


def test_paper_portfolio_readiness_tab_discloses_snapshot_and_missing_benchmark(tmp_path):
    state_db = tmp_path / "paper_portfolio" / "paper_portfolio.sqlite"
    status_path = tmp_path / "scheduled" / "paper_portfolio_daily" / "latest_status.json"
    snapshot = PaperPortfolioSnapshot(
        snapshot_id="paper-main-20260821",
        portfolio_id="paper-main",
        decision_date="2026-08-21",
        source_result_id="rec-1",
        cash=Decimal("100.00"),
        total_value=Decimal("1000.00"),
        positions=(
            PaperPortfolioPositionSnapshot(
                stock_code="2330",
                quantity=1,
                mark_price=Decimal("900.00"),
                market_value=Decimal("900.00"),
                weight_bp=9000,
            ),
        ),
    )
    PaperPortfolioSnapshotRepository(state_db).append(snapshot)
    status_path.parent.mkdir(parents=True)
    status_path.write_text(
        json.dumps(
            {
                "schema_version": "paper-portfolio-daily-status.v1",
                "status": "passed",
                "snapshot_id": snapshot.snapshot_id,
                "decision_date": snapshot.decision_date,
                "cash": "100.00",
                "total_value": "1000.00",
                "state_db": str(state_db.resolve()),
                "writes_market_db": False,
                "auto_rebalance_allowed": False,
                "changes_advice": False,
                "broker_execution": False,
            }
        ),
        encoding="utf-8",
    )

    view = make_portfolio_view(tmp_path)
    view.refresh_all()

    assert "最新可採用 snapshot：2026-08-21" in view.paper_readiness_summary_label.text()
    assert "raw 累積 1 筆" in view.paper_readiness_summary_label.text()
    assert "TWD 1,000.00" in view.paper_readiness_summary_label.text()
    assert "Equal Weight：尚無" in view.paper_readiness_summary_label.text()
    assert "成本帳：資料缺件（missing）（0 筆）" in view.paper_readiness_summary_label.text()
    assert "equal_weight_benchmark_db_missing" in view.paper_readiness_detail_label.text()
    assert view.paper_snapshot_table.model().rowCount() == 1


def test_paper_portfolio_tab_discloses_weekly_evidence_gap_without_writing(tmp_path):
    view = make_portfolio_view(tmp_path)

    view.refresh_all()

    assert "最近週報" in view.paper_weekly_report_label.text()
    assert "paper_snapshot_db_missing" in view.paper_weekly_report_label.text()
    assert not (tmp_path / "paper_portfolio").exists()


def test_paper_equal_weight_button_previews_then_builds_new_ledger(tmp_path, monkeypatch):
    baseline_path = tmp_path / "paper_portfolio" / "baseline_20260712.json"
    baseline_path.parent.mkdir(parents=True)
    baseline_path.write_text(
        json.dumps(
            {
                "decision_date": "2026-08-20",
                "residual_cash": "800.00",
                "research_only": True,
                "writes_positions_db": False,
                "broker_order_allowed": False,
                "auto_rebalance_allowed": False,
                "allocations": [
                    {
                        "stock_code": "2330",
                        "reference_price": "100.00",
                        "executable_shares": 1,
                        "executable_amount": "100.00",
                    },
                    {
                        "stock_code": "2317",
                        "reference_price": "50.00",
                        "executable_shares": 2,
                        "executable_amount": "100.00",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    state_db = tmp_path / "paper_portfolio" / "paper_portfolio.sqlite"
    for snapshot_id, decision_date, total_value in (
        ("paper-main-20260820", "2026-08-20", "1000.00"),
        ("paper-main-20260821", "2026-08-21", "1010.00"),
    ):
        PaperPortfolioSnapshotRepository(state_db).append(
            PaperPortfolioSnapshot(
                snapshot_id=snapshot_id,
                portfolio_id="paper-main",
                decision_date=decision_date,
                source_result_id="recommendation-1",
                cash=Decimal("800.00"),
                total_value=Decimal(total_value),
                positions=(
                    PaperPortfolioPositionSnapshot(
                        stock_code="2330",
                        quantity=1,
                        mark_price=Decimal("100.00"),
                        market_value=Decimal("100.00"),
                        weight_bp=1000,
                    ),
                ),
            )
        )
    market_db = tmp_path / "sqlite" / "twstock.db"
    market_db.parent.mkdir(parents=True)
    with sqlite3.connect(market_db) as connection:
        connection.execute("CREATE TABLE daily_prices (證券代號 TEXT, 日期 TEXT, 收盤價 TEXT)")
        connection.executemany(
            "INSERT INTO daily_prices VALUES (?, ?, ?)",
            (("2330", "20260820", "101.00"), ("2317", "20260820", "49.00")),
        )

    view = make_portfolio_view(tmp_path)
    messages: list[str] = []
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: messages.append(str(_args[2])))

    view.btn_build_paper_benchmark.click()

    benchmark_path = tmp_path / "paper_portfolio" / "paper_equal_weight_benchmark.sqlite"
    assert benchmark_path.exists()
    assert "已保存" in messages[-1]
    assert "Equal Weight：2 筆" in view.paper_readiness_summary_label.text()


def test_paper_fill_csv_import_requires_confirmation_and_only_writes_paper_ledger(
    tmp_path,
    monkeypatch,
):
    view = make_portfolio_view(tmp_path)
    csv_path = tmp_path / "paper_fills.csv"
    csv_path.write_text(
        "fill_id,order_id,portfolio_id,event_date,stock_code,side,requested_quantity,"
        "filled_quantity,reference_price,fill_price,commission,tax,slippage_cost,"
        "turnover_bp,execution_gap_bp,status,source_event_id,override_reason\n"
        "fill-1,order-1,paper-main,2026-08-27,2330,buy,1000,1000,100.00,100.08,"
        "15.00,0.00,8.00,120,8,filled,broker-1,\n",
        encoding="utf-8-sig",
    )
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_args: (str(csv_path), "CSV"))
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: None)

    view.btn_import_paper_fills.click()

    ledger_path = tmp_path / "paper_portfolio" / "paper_trade_ledger.sqlite"
    assert [fill.fill_id for fill in PaperTradeLedgerRepository(ledger_path).list()] == ["fill-1"]
    assert [trade.trade_id for trade in view.portfolio_service.trades] == ["t1", "t2"]
    assert "成本帳：可用（ready）（1 筆）" in view.paper_readiness_summary_label.text()


def test_paper_fill_template_export_writes_headers_only_and_not_ledger(tmp_path, monkeypatch):
    view = make_portfolio_view(tmp_path)
    template = tmp_path / "paper_fills_template.csv"
    messages: list[str] = []
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_args: (str(template), "CSV"))
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: messages.append(str(_args[2])))

    view.btn_export_paper_template.click()

    assert template.read_text(encoding="utf-8-sig").startswith(
        "fill_id,order_id,portfolio_id,event_date"
    )
    assert not (tmp_path / "paper_portfolio" / "paper_trade_ledger.sqlite").exists()
    assert any("空白欄位範本" in message for message in messages)


def test_portfolio_trade_csv_import_requires_confirmation_and_passes_source_trace(tmp_path, monkeypatch):
    view = make_portfolio_view(tmp_path)
    csv_path = tmp_path / "broker.csv"
    csv_path.write_text(
        "stock_code,side,quantity,price,trade_date\n"
        "2330,buy,1000,100,2026-08-20\n",
        encoding="utf-8-sig",
    )
    imported = []
    view.portfolio_service.record_trades = lambda trades: imported.extend(trades) or trades
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_args: (str(csv_path), "CSV"))
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: None)

    view.btn_import_trades.click()

    assert len(imported) == 1
    assert imported[0].source_type == "broker_csv"
    assert imported[0].source_snapshot_hash.startswith("sha256:")


def test_trade_history_filter_label_and_clear_button(tmp_path):
    view = make_portfolio_view(tmp_path)

    view.selected_stock_code = "2330"
    view._load_trades_history()
    assert "目前只顯示：2330" in view.trade_filter_status_label.text()

    view.clear_trade_filter_button.click()
    assert view.selected_stock_code == ""
    assert "顯示全部交易歷史" in view.trade_filter_status_label.text()


def test_portfolio_trade_delete_button_requires_a_selected_transaction(tmp_path):
    view = make_portfolio_view(tmp_path)

    assert view.delete_selected_trade_button.text() == "刪除選取交易"
    assert not view.delete_selected_trade_button.isEnabled()

    view.trades_table.selectRow(0)
    app().processEvents()

    assert view.delete_selected_trade_button.isEnabled()
    assert view.selected_trade_id == "t1"
    assert "已選取：2330 台積電" in view.trade_selection_hint_label.text()


def test_portfolio_trade_delete_button_confirms_then_deletes_one_transaction(tmp_path, monkeypatch):
    view = make_portfolio_view(tmp_path)
    service = view.portfolio_service
    portfolio_updates: list[bool] = []
    view.portfolioUpdated.connect(lambda: portfolio_updates.append(True))
    view.trades_table.selectRow(0)
    app().processEvents()

    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: None)

    view.delete_selected_trade_button.click()

    assert service.deleted_trade_ids == ["t1"]
    assert [trade.trade_id for trade in service.trades] == ["t2"]
    assert portfolio_updates == [True]
    assert not view.delete_selected_trade_button.isEnabled()


def test_portfolio_trade_delete_button_keeps_data_when_confirmation_is_cancelled(tmp_path, monkeypatch):
    view = make_portfolio_view(tmp_path)
    service = view.portfolio_service
    view.trades_table.selectRow(0)
    app().processEvents()

    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.No)

    view.delete_selected_trade_button.click()

    assert service.deleted_trade_ids == []
    assert [trade.trade_id for trade in service.trades] == ["t1", "t2"]


def test_portfolio_monitoring_does_not_treat_source_summary_date_as_quote_proof(tmp_path):
    view = make_portfolio_view(tmp_path)
    view.selected_stock_code = "2330"

    view._update_monitoring_tab()

    assert "行情資料日未知" in view.lbl_mon_current_price.text()
    assert "2026-06-22" not in view.lbl_mon_current_price.text()
    assert "手動建立，無推薦 / 回測來源" in view.lbl_strat_id.text()
    assert "偏空" in view.lbl_chip_risk_level.text()
    assert "bearish" in view.lbl_chip_risk_level.toolTip()
    assert "observed: 3" in view.lbl_chip_concentration.toolTip()


def _manual_2382_service(tmp_path, quote_date):
    service = FakePortfolioService(FakeConfig(tmp_path))
    position = service.positions[0]
    position.position_id = "manual:2382"
    position.stock_code = "2382"
    position.stock_name = "Tai Wei"
    position.last_trade_date = "2026-07-31"
    position.source_summary = {}
    service.positions = [position]
    service.trades = []
    calls: list[str] = []

    def get_current_price_observation(stock_code: str):
        calls.append(stock_code)
        return SimpleNamespace(
            stock_code=stock_code,
            price=Decimal("332.0"),
            data_date=quote_date,
            source_id="sqlite.daily_prices",
            source_snapshot_hash="a" * 64,
            freshness_status="current",
            expected_date=quote_date if isinstance(quote_date, date) else None,
        )

    service.get_current_price_observation = get_current_price_observation
    return service, calls


def _fixed_taipei_market_today() -> date:
    fixed_now = datetime(2026, 10, 5, 12, tzinfo=ZoneInfo("Asia/Taipei"))
    return fixed_now.date()


def test_manual_position_research_uses_same_row_quote_date_without_requery(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        portfolio_view_module, "taiwan_market_today", _fixed_taipei_market_today
    )
    service, quote_calls = _manual_2382_service(tmp_path, date(2026, 10, 2))
    view = make_portfolio_view(tmp_path, portfolio_service=service)
    contexts = []
    view.stockResearchRequested.connect(contexts.append)

    assert view.select_stock("2382")
    calls_before_open = len(quote_calls)
    view._open_selected_stock_research()

    assert len(quote_calls) == calls_before_open
    assert len(contexts) == 1
    context = contexts[0]
    assert context.stock_code == "2382"
    assert context.data_date == "2026-10-02"
    assert context.decision_date == ""
    assert context.result_id == ""
    assert context.identity_status == "unlinked"
    assert context.data_date != "2026-07-31"
    view.close()


@pytest.mark.parametrize(
    "quote_date",
    [None, datetime(2026, 10, 2, 16), date(2026, 10, 6)],
    ids=["missing", "datetime-is-not-a-date", "future"],
)
def test_manual_position_research_keeps_missing_invalid_or_future_quote_date_unknown(
    tmp_path, monkeypatch, quote_date
):
    monkeypatch.setattr(
        portfolio_view_module, "taiwan_market_today", _fixed_taipei_market_today
    )
    service, _quote_calls = _manual_2382_service(tmp_path, quote_date)
    view = make_portfolio_view(tmp_path, portfolio_service=service)
    contexts = []
    view.stockResearchRequested.connect(contexts.append)

    assert view.select_stock("2382")
    view._open_selected_stock_research()

    assert len(contexts) == 1
    assert contexts[0].data_date == ""
    assert contexts[0].result_id == ""
    assert contexts[0].identity_status == "unlinked"
    view.close()


def test_manual_position_research_does_not_use_another_symbols_cached_quote(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        portfolio_view_module, "taiwan_market_today", _fixed_taipei_market_today
    )
    service, _quote_calls = _manual_2382_service(tmp_path, date(2026, 10, 2))
    view = make_portfolio_view(tmp_path, portfolio_service=service)
    cached = view._position_current_snapshots["manual:2382"][1]
    view._position_current_snapshots["manual:2382"] = ("2317", cached)
    contexts = []
    view.stockResearchRequested.connect(contexts.append)

    assert view.select_stock("2382")
    view._open_selected_stock_research()

    assert len(contexts) == 1
    assert contexts[0].data_date == ""
    view.close()


def test_linked_position_research_keeps_canonical_saved_dates(tmp_path, monkeypatch):
    monkeypatch.setattr(
        portfolio_view_module, "taiwan_market_today", _fixed_taipei_market_today
    )
    service, _quote_calls = _manual_2382_service(tmp_path, date(2026, 10, 2))
    position = service.positions[0]
    position.source_type = "recommendation_result"
    position.source_id = "saved-2382"
    position.source_summary = {
        "decision_date": "2026-10-02",
        "current_price_date": "2026-10-01",
    }
    view = make_portfolio_view(tmp_path, portfolio_service=service)
    monkeypatch.setattr(
        view,
        "_validated_recommendation_result_id",
        lambda _position, _code: "saved-2382",
    )
    contexts = []
    view.stockResearchRequested.connect(contexts.append)

    assert view.select_stock("2382")
    view._open_selected_stock_research()

    assert len(contexts) == 1
    assert contexts[0].decision_date == "2026-10-02"
    assert contexts[0].data_date == "2026-10-01"
    assert contexts[0].result_id == "saved-2382"
    assert contexts[0].identity_status == "linked"
    view.close()


def test_portfolio_drill_down_passes_selected_stock_to_parent(tmp_path):
    app()

    class Parent(QWidget):
        def __init__(self):
            super().__init__()
            self.received = None

        def show_smart_money_flow_for_stock(self, stock_code: str):
            self.received = stock_code

    parent = Parent()
    view = make_portfolio_view(tmp_path, parent=parent)
    view.selected_stock_code = "2330"

    view._on_drill_down_chip_clicked()

    assert parent.received == "2330"


def test_deferred_splitter_restore_runs_while_portfolio_view_is_alive(
    tmp_path, monkeypatch
):
    app()
    calls = []
    monkeypatch.setattr(
        PortfolioView,
        "_restore_portfolio_splitter_default_sizes",
        lambda self: calls.append(self),
    )
    parent = QWidget()
    parent.resize(1000, 800)
    view = make_portfolio_view(tmp_path, parent=parent)
    view.resize(1000, 700)
    app().processEvents()

    calls.clear()
    view._portfolio_splitter_user_resized = False
    view._apply_portfolio_advanced_visibility()
    app().processEvents()
    assert calls == [view]


def test_deferred_splitter_restore_is_canceled_when_portfolio_view_is_destroyed(
    tmp_path, monkeypatch
):
    app()
    calls = []
    monkeypatch.setattr(
        PortfolioView,
        "_restore_portfolio_splitter_default_sizes",
        lambda self: calls.append(self),
    )
    parent = QWidget()
    parent.resize(1000, 800)
    view = make_portfolio_view(tmp_path, parent=parent)
    view.resize(1000, 700)
    view._portfolio_splitter_user_resized = False
    view._apply_portfolio_advanced_visibility()
    parent.deleteLater()
    QCoreApplication.sendPostedEvents(parent, QEvent.DeferredDelete)
    app().processEvents()

    assert calls == []
