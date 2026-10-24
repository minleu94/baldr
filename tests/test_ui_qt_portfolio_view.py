import os
import sqlite3
import sys
import threading
import time
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QModelIndex, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QBoxLayout,
    QFileDialog,
    QGridLayout,
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
    assert "本機名冊沒有唯一名稱" in dialog.code_error_label.text()


def test_add_trade_dialog_resolves_exact_unique_company_name_in_both_directions(monkeypatch):
    app()

    class CompanyFrame:
        def to_dict(self, orient):
            assert orient == "records"
            return [
                {"stock_id": "2330", "stock_name": "台積電"},
                {"stock_id": "2317", "stock_name": "鴻海"},
                {"stock_id": "1111", "stock_name": "重名"},
                {"stock_id": "2222", "stock_name": "重名"},
            ]

    service = SimpleNamespace(industry_mapper=SimpleNamespace(companies_df=CompanyFrame()))
    dialog = AddTradeDialog(recommendation_service=service)
    dialog.name_input.setText("台積電")
    assert dialog.code_input.text() == "2330"
    dialog.name_input.setText("鴻海")
    assert dialog.code_input.text() == "2317"
    dialog.name_input.setText("重名")
    assert dialog.code_input.text() == ""
    dialog.name_input.clear()
    dialog.code_input.setText("2330")
    assert dialog.name_input.text() == "台積電"
    dialog.code_input.setText("2317")
    assert dialog.name_input.text() == "鴻海"
    dialog.name_input.setText("台積電")
    assert dialog.code_input.text() == "2317"
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: warnings.append(_args[-1]))
    dialog._validate_and_accept()
    assert any("代號與名稱不符" in message for message in warnings)
    dialog.close()


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
    assert view.card_net_val.value_label.text() == "未知（估值日期缺件或不一致）"
    assert "已標記市值 2/2 檔" in view.active_positions_summary_label.text()


def test_portfolio_two_positions_fit_table_without_trapping_actions_below_blank_space(tmp_path):
    service = FakePortfolioService(FakeConfig(tmp_path))
    view = make_portfolio_view(tmp_path, portfolio_service=service)
    view.refresh_all()
    view.resize(1280, 760)
    view.show()
    app().processEvents()

    table = view.positions_table
    assert table.model() is not None and table.model().rowCount() == 2
    assert table.height() >= (
        table.horizontalHeader().height()
        + table.verticalHeader().defaultSectionSize() * 2
    )
    assert table.height() <= table.maximumHeight() < 180
    assert table.horizontalScrollBarPolicy() == Qt.ScrollBarAsNeeded

    service.positions.append(replace(service.positions[0], position_id="default:2330-more"))
    view._load_positions_table(service.get_portfolio())
    assert table.model() is not None and table.model().rowCount() == 3
    assert table.maximumHeight() > 1000
    assert table.minimumHeight() >= (
        table.horizontalHeader().height()
        + table.verticalHeader().defaultSectionSize() * 2
    )
    view.close()


def test_portfolio_empty_dto_keeps_summary_and_restores_table_when_populated(
    tmp_path,
):
    class EmptyPortfolioService(FakePortfolioService):
        def get_portfolio(self):
            portfolio = super().get_portfolio()
            return replace(
                portfolio,
                total_positions=len(self.positions),
                active_positions=len(self.positions),
                positions=tuple(self.positions),
            )

    service = EmptyPortfolioService(FakeConfig(tmp_path))
    service.positions = []
    view = make_portfolio_view(tmp_path, portfolio_service=service)
    view.refresh_all()

    empty_dto = view._last_portfolio_dto
    assert isinstance(empty_dto, PortfolioDTO)
    assert empty_dto.positions == ()
    assert view.positions_model is not None
    assert view.positions_model.rowCount() == 0
    assert view.positions_table.isHidden()
    assert "活躍持倉：0 檔" in view.active_positions_summary_label.text()
    assert "目前沒有可摘要的持倉列" in view.position_focus_label.text()

    service.positions.append(
        replace(
            FakePortfolioService(FakeConfig(tmp_path)).positions[0],
            position_id="default:2330-restored",
        )
    )
    view._load_positions_table(service.get_portfolio())

    assert view.positions_model is not None
    assert view.positions_model.rowCount() == 1
    assert not view.positions_table.isHidden()
    assert view.positions_table.maximumHeight() < 180
    view.close()


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("current", "資料日符合預期交易日（current）"),
        ("stale", "資料日早於預期交易日（stale）"),
        ("future_rejected", "資料日超前（拒用）（future_rejected）"),
        ("unverified", "資料日未核實（unverified）"),
        ("new_source_state", "new_source_state"),
    ],
)
def test_portfolio_quote_date_status_only_localizes_known_source_codes(status, expected):
    assert portfolio_view_module._quote_freshness_status_text(status) == expected


def test_portfolio_quote_date_status_keeps_row_and_monitor_source_code(tmp_path):
    service, _calls = _manual_2382_service(tmp_path, date(2026, 10, 2))
    view = make_portfolio_view(tmp_path, portfolio_service=service)
    assert view.select_stock("2382")
    assert view.positions_model is not None
    frame = view.positions_model.getDataFrame()
    assert "行情日期狀態" in frame.columns
    assert frame.loc[0, "行情日期狀態"] == "資料日符合預期交易日（current）"
    assert "日期狀態：資料日符合預期交易日（current）" in view.lbl_mon_current_price.text()
    assert "僅供損益觀察" in view.lbl_mon_current_price.text()
    view.close()


def test_portfolio_selected_position_shows_shared_decision_presentation(tmp_path):
    view = make_portfolio_view(tmp_path)

    view.refresh_all()
    assert "尚未選取持倉列" in view.position_focus_label.text()
    assert view.select_stock("2317") is True
    daily_layout = view.manual_account_panel.layout()
    assert daily_layout is not None
    assert daily_layout.indexOf(view.position_focus_label) < daily_layout.indexOf(view.positions_table)
    assert view.position_focus_label.textFormat() == Qt.PlainText

    focus_text = view.position_focus_label.text()
    assert "2317 鴻海" in focus_text
    assert "持有 1,000 股" in focus_text
    assert "平均成本 TWD 150" in focus_text
    assert "目前價格 TWD 151" in focus_text
    assert "未實現損益（毛額）TWD 1,000" in focus_text
    assert "報價資料日：未知" in focus_text
    assert "Paper Health：觀察／未知" in focus_text
    assert "不構成交易動作" in focus_text

    detail_text = view.position_presentation_label.text()
    assert "研究路徑：市場總覽 → 產業／市場探索 → 關鍵股研究 → 觀察清單 → 持倉覆盤" in detail_text
    assert "動作適合度：持有" in detail_text
    assert "排名分數：未知（僅作排序，不等於機率）" in detail_text
    assert "校準機率：不可用（研究中）" in detail_text
    assert "成本基準：TWD 150.00" in detail_text
    assert "來源追溯：recommendation_result；rec-1" in detail_text


def test_portfolio_position_health_known_states_are_human_readable_with_raw_tooltips(
    tmp_path,
):
    view = make_portfolio_view(tmp_path)
    position = next(
        item for item in view.portfolio_service.positions if item.stock_code == "2317"
    )
    health = replace(_make_health_row("2317"), position_id=position.position_id)
    original_payload = health.to_dict()
    view._position_health_by_id = {position.position_id: health}
    view.selected_stock_code = "2317"

    view._render_position_health_lifecycle(health)

    assert "來源受阻" in view.lbl_lifecycle_source.text()
    assert "條件：未知" in view.lbl_lifecycle_signal.text()
    assert "Thesis：資料缺件" in view.lbl_lifecycle_signal.text()
    assert "Metrics：受阻" in view.lbl_lifecycle_signal.text()
    assert "資料品質：受阻" in view.lbl_lifecycle_data_quality.text()
    assert "進場來源：尚未核實" in view.lbl_lifecycle_data_quality.text()
    assert "blocked" in view.lbl_lifecycle_source.toolTip()
    assert "condition=unknown" in view.lbl_lifecycle_signal.toolTip()
    assert "thesis=missing" in view.lbl_lifecycle_signal.toolTip()
    assert "quality=blocked" in view.lbl_lifecycle_data_quality.toolTip()
    assert "entry_lineage=unverified" in view.lbl_lifecycle_data_quality.toolTip()
    assert view.selected_stock_code == "2317"
    assert view._health_for_position(position) is health
    assert health.to_dict() == original_payload


def test_portfolio_position_health_unknown_state_codes_remain_raw(tmp_path):
    view = make_portfolio_view(tmp_path)
    health = replace(
        _make_health_row("2317"),
        source_status="future_source_state",
        quality="future_quality_state",
        condition_status="future_condition_state",
        thesis_status="future_thesis_state",
        metrics_status="future_metrics_state",
        entry_lineage_status="future_lineage_state",
    )

    view._render_position_health_lifecycle(health)

    assert "future_source_state" in view.lbl_lifecycle_source.text()
    assert "future_condition_state" in view.lbl_lifecycle_signal.text()
    assert "future_thesis_state" in view.lbl_lifecycle_signal.text()
    assert "future_metrics_state" in view.lbl_lifecycle_signal.text()
    assert "future_quality_state" in view.lbl_lifecycle_data_quality.text()
    assert "future_lineage_state" in view.lbl_lifecycle_data_quality.text()
    assert "future_source_state" in view.lbl_lifecycle_source.toolTip()
    assert "future_condition_state" in view.lbl_lifecycle_signal.toolTip()
    assert "future_quality_state" in view.lbl_lifecycle_data_quality.toolTip()


def test_portfolio_position_pnl_cells_use_taiwan_direction_colors_without_changing_values(
    tmp_path,
):
    service = FakePortfolioService(FakeConfig(tmp_path))
    base = service.positions[0]
    source_values = (
        (12.5, 12.5),
        (-12.5, -12.5),
        (0.0, 0.0),
        (12.5, None),
    )
    service.positions = [
        replace(
            base,
            position_id=f"default:test-{index}",
            stock_code=f"T{index:03d}",
            realized_pnl=realized,
            unrealized_pnl=unrealized,
        )
        for index, (realized, unrealized) in enumerate(source_values)
    ]
    view = make_portfolio_view(tmp_path, portfolio_service=service)
    view._load_positions_table(service.get_portfolio())

    model = view.positions_model
    assert model is not None
    columns = model.getVisibleColumns()
    realized_column = columns.index("已實現損益（毛額，未扣費稅）")
    unrealized_column = columns.index("未實現損益（毛額，未扣費稅）")
    expected_direction_colors = (
        QColor(portfolio_view_module.MIDNIGHT_ANALYST.market_up),
        QColor(portfolio_view_module.MIDNIGHT_ANALYST.market_down),
        QColor(portfolio_view_module.MIDNIGHT_ANALYST.market_flat),
        QColor(portfolio_view_module.MIDNIGHT_ANALYST.market_up),
    )
    for row, expected_color in enumerate(expected_direction_colors):
        assert model.data(model.index(row, realized_column), Qt.ForegroundRole) == (
            expected_color
        )
        expected_unrealized_color = (
            None if source_values[row][1] is None else expected_color
        )
        assert model.data(
            model.index(row, unrealized_column), Qt.ForegroundRole
        ) == expected_unrealized_color

    frame = model.getDataFrame()
    assert frame["已實現損益（毛額，未扣費稅）"].tolist() == [12.5, -12.5, 0.0, 12.5]
    assert frame["未實現損益（毛額，未扣費稅）"].tolist() == [
        12.5,
        -12.5,
        0.0,
        "-",
    ]
    assert tuple(position.unrealized_pnl for position in service.positions) == (
        12.5,
        -12.5,
        0.0,
        None,
    )
    view.close()


def test_portfolio_unrealized_return_direction_uses_hidden_source_after_sort(tmp_path):
    service = FakePortfolioService(FakeConfig(tmp_path))
    base = service.positions[0]
    source_rows = (
        ("T030", "default:return-positive", 0.125),
        ("T020", "default:return-negative", -0.125),
        ("T010", "default:return-zero", 0.0),
        ("T000", "default:return-unknown", None),
    )
    service.positions = [
        replace(
            base,
            position_id=position_id,
            stock_code=stock_code,
            stock_name=position_id,
            unrealized_pnl_pct=source_value,
        )
        for stock_code, position_id, source_value in source_rows
    ]
    view = make_portfolio_view(tmp_path, portfolio_service=service)
    view._load_positions_table(service.get_portfolio())

    model = view.positions_model
    assert model is not None
    visible_columns = model.getVisibleColumns()
    return_column = visible_columns.index("未實現損益%（毛額）")
    stock_column = visible_columns.index("證券代號")
    assert "_unrealized_pnl_pct_direction" not in visible_columns

    model.sort(stock_column, Qt.AscendingOrder)

    frame = model.getDataFrame()
    expected_by_identity = {
        "default:return-positive": (
            "+12.50%",
            QColor(portfolio_view_module.MIDNIGHT_ANALYST.market_up),
        ),
        "default:return-negative": (
            "-12.50%",
            QColor(portfolio_view_module.MIDNIGHT_ANALYST.market_down),
        ),
        "default:return-zero": (
            "+0.00%",
            QColor(portfolio_view_module.MIDNIGHT_ANALYST.market_flat),
        ),
        "default:return-unknown": ("-", None),
    }
    observed_identities = []
    for row in range(model.rowCount()):
        identity = frame.iloc[row]["_position_id"]
        observed_identities.append(identity)
        expected_text, expected_color = expected_by_identity[identity]
        assert model.data(model.index(row, return_column), Qt.DisplayRole) == expected_text
        assert model.data(model.index(row, return_column), Qt.ForegroundRole) == expected_color
    assert observed_identities == [
        "default:return-unknown",
        "default:return-zero",
        "default:return-negative",
        "default:return-positive",
    ]
    assert tuple(position.unrealized_pnl_pct for position in service.positions) == (
        0.125,
        -0.125,
        0.0,
        None,
    )
    view.close()


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


def test_stress_tab_uses_wide_detail_default_and_preserves_manual_splitter_choice(tmp_path):
    view = make_portfolio_view(tmp_path)
    host = QStackedWidget()
    host.setMinimumSize(0, 0)
    host.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
    host.addWidget(view)
    host.resize(1280, 760)
    host.show()
    view._toggle_advanced_portfolio(True)
    app().processEvents()

    assert view._activate_v2_section("paper", account="paper", preferred_tab="stress")
    app().processEvents()
    stress_sizes = view.main_splitter.sizes()
    stress_ratio = stress_sizes[0] / sum(stress_sizes)
    assert 0.25 <= stress_ratio <= 0.40
    assert view.paper_health_group.isVisible()
    assert view.portfolio_detail_tabs.currentWidget() is (
        view._portfolio_detail_tab_widgets["stress"]
    )

    assert view._activate_v2_section("paper", account="paper", preferred_tab="paper")
    app().processEvents()
    assert view.portfolio_detail_tabs.currentWidget() is (
        view._portfolio_detail_tab_widgets["paper"]
    )
    normal_sizes = view.main_splitter.sizes()
    normal_ratio = normal_sizes[0] / sum(normal_sizes)
    assert 0.52 <= normal_ratio <= 0.68

    view.main_splitter.setSizes([420, 580])
    view._on_portfolio_splitter_moved(420, 1)
    user_sizes = view.main_splitter.sizes()
    user_ratio = user_sizes[0] / sum(user_sizes)
    assert view._activate_v2_section("paper", account="paper", preferred_tab="stress")
    app().processEvents()
    assert view.main_splitter.sizes()[0] / sum(view.main_splitter.sizes()) == pytest.approx(
        user_ratio, abs=0.02
    )
    assert view._activate_v2_section("paper", account="paper", preferred_tab="paper")
    app().processEvents()
    assert view.main_splitter.sizes()[0] / sum(view.main_splitter.sizes()) == pytest.approx(
        user_ratio, abs=0.02
    )
    view.close()


def test_stress_splitter_default_keeps_vertical_ratio_and_position_selection(tmp_path):
    view = make_portfolio_view(tmp_path)
    host = QStackedWidget()
    host.setMinimumSize(0, 0)
    host.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
    host.addWidget(view)
    host.resize(390, 844)
    host.show()
    view._toggle_advanced_portfolio(True)
    app().processEvents()
    assert view.main_splitter.orientation() == Qt.Vertical

    positions_model = view.positions_table.model()
    selected_index = positions_model.index(0, 0)
    selected_value = selected_index.data(Qt.DisplayRole)
    view.positions_table.setCurrentIndex(selected_index)
    assert view._activate_v2_section("paper", account="paper", preferred_tab="stress")
    app().processEvents()
    vertical_sizes = view.main_splitter.sizes()
    vertical_ratio = vertical_sizes[0] / sum(vertical_sizes)
    assert 0.35 <= vertical_ratio <= 0.50
    assert view.positions_table.currentIndex().data(Qt.DisplayRole) == selected_value

    assert view._activate_v2_section("paper", account="paper", preferred_tab="paper")
    app().processEvents()
    returned_sizes = view.main_splitter.sizes()
    assert returned_sizes[0] / sum(returned_sizes) == pytest.approx(vertical_ratio, abs=0.02)
    assert view.positions_table.currentIndex().data(Qt.DisplayRole) == selected_value
    view.close()


def test_daily_positions_panel_is_full_width_immediately_after_status_summary(tmp_path):
    view = make_portfolio_view(tmp_path)
    content = view.portfolio_advanced_scroll.widget()
    assert content is not None
    layout = content.layout()
    assert layout is not None

    positions_index = layout.indexOf(view.manual_account_panel)
    active_summary_index = layout.indexOf(view.active_positions_summary_label)
    assert positions_index == active_summary_index + 1
    assert positions_index < layout.indexOf(view.portfolio_refresh_status_label)
    assert positions_index < layout.indexOf(view.toggle_advanced_portfolio_btn)
    assert view.main_splitter.indexOf(view.manual_account_panel) == -1
    assert view.main_splitter.indexOf(view.paper_health_group) >= 0
    assert view.main_splitter.indexOf(view.portfolio_detail_tabs) >= 0
    assert view.position_action_layout.indexOf(view.btn_record_trade) >= 0


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


def test_position_health_table_prioritizes_review_and_exposes_exact_row_identity(
    tmp_path,
):
    first = replace(
        _make_health_row("2330"),
        position_id="paper:2330-lot-a",
        source_snapshot_id="snapshot-2330-a",
        cohort_key="paper-cohort-a",
    )
    second = replace(
        first,
        position_id="paper:2330-lot-b",
        source_snapshot_id="snapshot-2330-b",
        cohort_key="paper-cohort-b",
        review_required=False,
        why="第二筆來源已核對。",
    )
    missing_identity = replace(
        first,
        position_id=None,
        source_snapshot_id="",
        cohort_key="",
        review_required=False,
    )
    health_model = replace(
        _make_blocked_health_model(),
        positions=(first, second, missing_identity),
    )
    view = make_portfolio_view(
        tmp_path,
        position_health_read_service=FakePositionHealthReadService(health_model),
    )

    view.refresh_all()

    model = view.position_health_model
    headers = [
        model.headerData(column, Qt.Horizontal, Qt.DisplayRole)
        for column in range(model.columnCount())
    ]
    assert headers == [
        "標的",
        "需要確認",
        "決策日",
        "來源狀態",
        "研究建議",
        "評估原因",
    ]
    review_column = model.column_index("review_required")
    assert model.index(0, review_column).data(Qt.DisplayRole) == "需要"
    assert model.index(1, review_column).data(Qt.DisplayRole) == "不需要"

    stock_column = model.column_index("stock_code")
    first_tooltip = model.index(0, stock_column).data(Qt.ToolTipRole)
    second_tooltip = model.index(1, stock_column).data(Qt.ToolTipRole)
    missing_tooltip = model.index(2, stock_column).data(Qt.ToolTipRole)
    assert "position_id）：paper:2330-lot-a" in first_tooltip
    assert "snapshot ID：snapshot-2330-a" in first_tooltip
    assert "cohort key：paper-cohort-a" in first_tooltip
    assert first_tooltip != second_tooltip
    assert "position_id）：未提供" in missing_tooltip
    assert "snapshot ID：未提供" in missing_tooltip
    assert "cohort key：未提供" in missing_tooltip
    assert "不以股票代號代替" in missing_tooltip

    view.position_health_table.selectRow(0)
    view._show_position_health_row(model.index(0, stock_column))
    assert "部位識別（技術）：paper:2330-lot-a" in (
        view.position_health_detail_label.text()
    )
    assert "需要確認：需要" in view.position_health_detail_label.text()

    view.position_health_table.selectRow(1)
    view._show_position_health_row(model.index(1, stock_column))
    assert "部位識別（技術）：paper:2330-lot-b" in (
        view.position_health_detail_label.text()
    )
    assert "需要確認：不需要" in view.position_health_detail_label.text()
    assert "第二筆來源已核對。" in view.position_health_detail_label.text()
    view.close()


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

    assert view.btn_save_stress_history.isEnabled() is True
    view.stress_scenario_combo.setCurrentIndex(
        view.stress_scenario_combo.findData("concentration_event")
    )
    assert view.btn_save_stress_history.isEnabled() is False
    view.btn_run_stress.click()

    assert "最大持倉事件" in view.stress_summary_label.text()
    assert "可計算" in view.stress_summary_label.text()
    assert "研究用途" in view.stress_detail_label.text()
    assert "本次 Stress 結果未附逐列報價資料日／來源" in (
        view.stress_detail_label.text()
    )
    assert view.stress_positions_table.model().rowCount() == 2
    stress_rows = view.stress_positions_table.model()._dataframe
    assert "計算輸入" in stress_rows.columns
    assert stress_rows["計算輸入"].tolist() == [
        "1000 股 × TWD 110/股",
        "1000 股 × TWD 151/股",
    ]
    assert view._stress_result.research_only is True
    assert view._stress_result.investment_effectiveness_claim is False
    assert view.btn_save_stress_history.isEnabled() is True


def test_portfolio_stress_input_column_keeps_only_priced_rows(tmp_path):
    portfolio_service = FakePortfolioService(FakeConfig(tmp_path))
    portfolio_service.positions[1].current_price = None
    view = make_portfolio_view(tmp_path, portfolio_service=portfolio_service)

    view.btn_run_stress.click()

    assert view._stress_result.status == "partial"
    assert view._stress_result.missing_price_codes == ("2317",)
    assert view.stress_positions_table.model().rowCount() == 1
    stress_rows = view.stress_positions_table.model()._dataframe
    assert stress_rows["證券代號"].tolist() == ["2330"]
    assert stress_rows["計算輸入"].tolist() == ["1000 股 × TWD 110/股"]
    assert "缺最新價：2317" in view.stress_detail_label.text()


def test_portfolio_stress_scenario_preview_uses_definition_before_execution(tmp_path):
    view = make_portfolio_view(tmp_path)

    supported_index = view.stress_scenario_combo.findData("concentration_event")
    view.stress_scenario_combo.setCurrentIndex(supported_index)
    supported_preview = view.stress_scenario_preview_label.text()
    assert "只對目前標記市值最大的單一持倉套用 -20% 情境。" in supported_preview
    assert "服務支援狀態：支援" in supported_preview
    assert "必要輸入：無。" in supported_preview
    assert "不是計算結果" in supported_preview
    assert view._stress_result is None
    assert view.stress_summary_label.text() == "情境已變更；請重新執行情境。"
    assert view.btn_save_stress_history.isEnabled() is False

    rotation_index = view.stress_scenario_combo.findData("rotation_failure")
    view.stress_scenario_combo.setCurrentIndex(rotation_index)
    rotation_preview = view.stress_scenario_preview_label.text()
    assert "需要持倉的產業／概念曝險標籤" in rotation_preview
    assert "依情境定義：目前不支援、不可計算" in rotation_preview
    assert "必要輸入：持倉產業／概念曝險標籤。" in rotation_preview
    assert "實際執行診斷仍依結果顯示" in rotation_preview
    assert "scenario_requires:" not in rotation_preview
    assert view._stress_result is None
    assert view.btn_save_stress_history.isEnabled() is False

    outage_index = view.stress_scenario_combo.findData("source_outage")
    view.stress_scenario_combo.setCurrentIndex(outage_index)
    outage_preview = view.stress_scenario_preview_label.text()
    assert "價格來源可用性" in outage_preview
    assert "依情境定義：目前不支援、不可計算" in outage_preview
    assert "實際執行診斷仍依結果顯示" in outage_preview
    assert "scenario_requires:" not in outage_preview
    assert view._stress_result is None
    assert view.btn_save_stress_history.isEnabled() is False
    view.close()


def test_portfolio_stress_scenario_preview_unknown_missing_and_scrollable(tmp_path):
    view = make_portfolio_view(tmp_path)

    definition = view._stress_scenarios_by_id["fast_drop"]
    view._stress_scenarios_by_id["fast_drop"] = replace(definition, description=" ")
    view._refresh_stress_scenario_preview()
    assert "情境定義未提供說明" in view.stress_scenario_preview_label.text()

    missing_inputs = view._stress_scenarios_by_id["rotation_failure"]
    view._stress_scenarios_by_id["rotation_failure"] = replace(
        missing_inputs,
        required_inputs=None,
    )
    view.stress_scenario_combo.setCurrentIndex(
        view.stress_scenario_combo.findData("rotation_failure")
    )
    assert "必要輸入：未知（定義未提供）。" in (
        view.stress_scenario_preview_label.text()
    )
    assert "依情境定義：目前不支援、不可計算" in (
        view.stress_scenario_preview_label.text()
    )
    assert "實際執行診斷仍依結果顯示" in (
        view.stress_scenario_preview_label.text()
    )

    view.stress_scenario_combo.addItem("未來情境", "future_scenario")
    view.stress_scenario_combo.setCurrentIndex(
        view.stress_scenario_combo.findData("future_scenario")
    )
    assert "沒有對應的 StressScenarioDefinition" in (
        view.stress_scenario_preview_label.text()
    )
    assert "目前不支援" not in view.stress_scenario_preview_label.text()

    view.stress_scenario_combo.setCurrentIndex(-1)
    assert "目前沒有選定情境" in view.stress_scenario_preview_label.text()
    assert "未知" in view.stress_scenario_preview_label.text()
    assert view.stress_scenario_preview_scroll.maximumHeight() <= 72
    view.close()


def test_portfolio_stress_scenario_change_clears_result_and_save_identity(
    tmp_path, monkeypatch
):
    view = make_portfolio_view(tmp_path)
    view.stress_scenario_combo.setCurrentIndex(
        view.stress_scenario_combo.findData("concentration_event")
    )
    view.btn_run_stress.click()
    result_a = view._stress_result
    assert result_a is not None
    assert result_a.scenario.scenario_id == "concentration_event"
    assert view.btn_save_stress_history.isEnabled() is True

    view.stress_scenario_combo.setCurrentIndex(
        view.stress_scenario_combo.findData("correlated_selloff")
    )
    assert view._stress_result is None
    assert view.stress_summary_label.text() == "情境已變更；請重新執行情境。"
    assert "舊結果已清除" in view.stress_detail_label.text()
    assert view.stress_positions_table.model().rowCount() == 0
    assert "計算輸入" not in view.stress_positions_table.model()._dataframe.columns
    assert view.btn_save_stress_history.isEnabled() is False
    view.btn_save_stress_history.click()
    assert not view.stress_history_db_path.exists()

    # 即使其他呼叫路徑錯誤地保留舊 DTO，保存入口仍須獨立阻擋身份不符。
    info_messages = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *_args: info_messages.append(_args[1]),
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args: pytest.fail("scenario mismatch must not reach confirmation"),
    )
    view._stress_result = result_a
    view._save_stress_history()
    assert not view.stress_history_db_path.exists()
    assert "Stress 結果已過期" in info_messages
    assert view._stress_result is None
    assert view.btn_save_stress_history.isEnabled() is False

    view.btn_run_stress.click()
    assert view._stress_result.scenario.scenario_id == "correlated_selloff"
    assert view.btn_save_stress_history.isEnabled() is True
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: None)
    view.btn_save_stress_history.click()
    assert view.stress_history_db_path.exists()
    assert view._stress_history_display_records[-1].scenario_label == "相關股同跌 -15%"


def test_portfolio_stress_load_failure_clears_result_and_disables_save(
    tmp_path, monkeypatch
):
    view = make_portfolio_view(tmp_path)
    monkeypatch.setattr(
        view.stress_lab_service,
        "evaluate_positions",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("stress fixture error")),
    )

    view.btn_run_stress.click()

    assert view._stress_result is None
    assert view.stress_summary_label.text() == "情境壓力測試載入失敗；未修改持倉。"
    assert view.stress_detail_label.text() == "診斷：stress fixture error"
    assert view.stress_positions_table.model().rowCount() == 0
    assert "計算輸入" not in view.stress_positions_table.model()._dataframe.columns
    assert view.btn_save_stress_history.isEnabled() is False


def test_portfolio_stress_source_disclosure_survives_section_switch_and_save(
    tmp_path, monkeypatch
):
    view = make_portfolio_view(tmp_path)
    host = QStackedWidget()
    host.resize(1280, 760)
    host.addWidget(view)
    host.show()
    view._toggle_advanced_portfolio(True)
    assert view.select_v2_section("paper") is True
    assert view._set_portfolio_detail_tab("stress") is True
    app().processEvents()

    source_text = view.stress_source_label.text()
    result_before_switch = view._stress_result
    assert view.stress_source_label.isVisible() is True
    assert view.stress_scenario_preview_scroll.isVisible() is True
    assert (
        view.stress_scenario_preview_scroll.height()
        <= view.stress_scenario_preview_scroll.maximumHeight()
    )
    assert view.stress_positions_table.isVisible() is True
    assert "PortfolioService 的交易／手動持倉 DTO" in source_text
    assert "portfolio_id=default" in source_text
    assert "不讀 Paper snapshot、ledger 或 Health" in source_text
    assert "Stress 放在 Paper 分區只是導覽位置" in source_text
    assert result_before_switch is not None

    assert view.select_v2_section("positions") is True
    assert view._stress_result is result_before_switch
    assert view.stress_source_label.text() == source_text
    assert view.select_v2_section("paper") is True
    app().processEvents()
    stress_tab = view._portfolio_detail_tab_widgets["stress"]
    assert view.portfolio_detail_tabs.currentWidget() is stress_tab
    assert view._stress_result is result_before_switch
    assert view.stress_source_label.isVisible() is True
    assert view.stress_source_label.text() == source_text

    confirmation_text = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args: confirmation_text.append(_args[2]) or QMessageBox.Yes,
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: None)
    view.btn_save_stress_history.click()

    assert view.stress_history_db_path.exists()
    assert "不讀 Paper snapshot、ledger 或 Health" in confirmation_text[0]
    assert view._stress_history_display_records[-1].scenario_label == (
        result_before_switch.scenario.label
    )
    host.close()


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


def _stress_history_record(
    *,
    record_id: str,
    scenario_label: str,
    status: str,
    base: str | None,
    stressed: str | None,
    delta: str | None,
    run_at: str,
    as_of_date: str | None = "2026-10-22",
):
    return portfolio_view_module.PortfolioStressHistoryRecord.from_payload(
        {
            "schema_version": "portfolio-stress-lab.v1",
            "scenario": {
                "scenario_id": record_id,
                "label": scenario_label,
            },
            "status": status,
            "priced_position_count": 3 if status == "ready" else (2 if status == "partial" else 0),
            "total_position_count": 3,
            "base_market_value": base,
            "stressed_market_value": stressed,
            "value_delta": delta,
            "as_of_date": as_of_date,
            "research_only": True,
            "investment_effectiveness_claim": False,
        },
        record_id=record_id,
        run_at=run_at,
    )


def test_portfolio_stress_history_card_tracks_exact_selected_record(tmp_path):
    view = make_portfolio_view(tmp_path)
    records = (
        _stress_history_record(
            record_id="stress-ready-zero",
            scenario_label="快速下跌情境",
            status="ready",
            base="0",
            stressed="0",
            delta="0",
            run_at="2026-10-22T09:00:00Z",
        ),
        _stress_history_record(
            record_id="stress-partial",
            scenario_label="部分價格缺件情境",
            status="partial",
            base="12345.60",
            stressed="11111.10",
            delta="-1234.50",
            run_at="2026-10-22T10:00:00Z",
            as_of_date=None,
        ),
        _stress_history_record(
            record_id="stress-not-computable",
            scenario_label="尚不可計算情境",
            status="not_computable",
            base=None,
            stressed=None,
            delta=None,
            run_at="2026-10-22T11:00:00Z",
        ),
    )
    result = SimpleNamespace(
        status="ready",
        db_path="synthetic://stress-history",
        records=records,
        blockers=(),
        warnings=(),
    )

    view._render_stress_history(result)
    model = view.stress_history_table.model()
    assert model.rowCount() == 3
    assert model.data(model.index(0, 2)) == "快速下跌情境"
    assert model.data(model.index(0, 5)) == "0"
    assert model.data(model.index(0, 6)) == "0"
    assert model.data(model.index(0, 7)) == "0"
    assert model.data(model.index(0, 8)) == records[0].payload_hash[:12]
    assert view.stress_history_card_title.text() == "選取一筆已保存紀錄"

    view.stress_history_table.setCurrentIndex(model.index(0, 0))
    assert view.stress_history_card_title.text() == "快速下跌情境"
    assert "ready（可用）" in view.stress_history_card_meta.text()
    assert "2026-10-22T09:00:00Z" in view.stress_history_card_meta.text()
    assert "3/3" in view.stress_history_card_meta.text()
    assert view.stress_history_metric_values["base_market_value"].text() == "0"
    assert view.stress_history_metric_values["stressed_market_value"].text() == "0"
    assert view.stress_history_metric_values["value_delta"].text() == "0"

    view.stress_history_table.setCurrentIndex(model.index(1, 0))
    assert view.stress_history_card_title.text() == "部分價格缺件情境"
    assert "partial（部分完成）" in view.stress_history_card_meta.text()
    assert "基準日：未提供" in view.stress_history_card_meta.text()
    assert view.stress_history_metric_values["base_market_value"].text() == "12345.60"
    assert view.stress_history_metric_values["stressed_market_value"].text() == "11111.10"
    assert view.stress_history_metric_values["value_delta"].text() == "-1234.50"

    view.stress_history_table.setCurrentIndex(model.index(2, 0))
    assert view.stress_history_card_title.text() == "尚不可計算情境"
    assert "not_computable（不可計算）" in view.stress_history_card_meta.text()
    assert all(value.text() == "未提供" for value in view.stress_history_metric_values.values())
    assert "不是預測" in view.stress_history_card_meta.text()

    view.stress_history_table.clearSelection()
    view.stress_history_table.setCurrentIndex(QModelIndex())
    assert view.stress_history_card_title.text() == "選取一筆已保存紀錄"
    assert all(value.text() == "未提供" for value in view.stress_history_metric_values.values())


def test_portfolio_stress_history_table_is_bounded_and_keeps_long_list_selection(tmp_path):
    view = make_portfolio_view(tmp_path)
    records = tuple(
        _stress_history_record(
            record_id=f"stress-{index:02d}",
            scenario_label=f"合成情境 {index:02d}",
            status="ready",
            base=str(index * 100),
            stressed=str(index * 90),
            delta=str(index * -10),
            run_at=f"2026-10-{(index % 28) + 1:02d}T09:00:00Z",
        )
        for index in range(40)
    )
    view._render_stress_history(
        SimpleNamespace(
            status="ready",
            db_path="synthetic://stress-history-40",
            records=records,
            blockers=(),
            warnings=(),
        )
    )

    table = view.stress_history_table
    model = table.model()
    assert model.rowCount() == 40
    expected_max_height = (
        table.horizontalHeader().sizeHint().height()
        + table.verticalHeader().defaultSectionSize() * 7
        + table.horizontalScrollBar().sizeHint().height()
        + table.frameWidth() * 2
    )
    assert table.maximumHeight() == expected_max_height
    assert table.minimumHeight() == 0
    assert table.verticalScrollBarPolicy() == Qt.ScrollBarAsNeeded

    view.resize(1280, 760)
    view._toggle_advanced_portfolio(True)
    assert view._activate_v2_section("paper", account="paper", preferred_tab="stress")
    view.stress_workspace_tabs.setCurrentIndex(1)
    view.show()
    app().processEvents()
    assert table.isVisible()
    assert view.stress_history_card.height() <= view.stress_history_card.sizeHint().height() + 20
    table.setCurrentIndex(model.index(39, 0))
    app().processEvents()
    assert table.verticalScrollBar().maximum() > 0
    assert view.stress_history_card_title.text() == "合成情境 39"
    assert view.stress_history_metric_values["base_market_value"].text() == "3900"

    view.stress_history_read_service = SimpleNamespace(
        inspect=lambda: (_ for _ in ()).throw(OSError("synthetic read failure"))
    )
    view._load_stress_history()
    assert table.model().rowCount() == 0
    expected_empty_max_height = (
        table.horizontalHeader().sizeHint().height()
        + table.verticalHeader().defaultSectionSize()
        + table.horizontalScrollBar().sizeHint().height()
        + table.frameWidth() * 2
    )
    assert table.maximumHeight() == expected_empty_max_height
    assert view.stress_history_card_title.text() == "選取一筆已保存紀錄"
    view.close()


def test_portfolio_stress_history_refresh_and_read_error_clear_selected_card(tmp_path):
    view = make_portfolio_view(tmp_path)
    record = _stress_history_record(
        record_id="stress-refresh",
        scenario_label="刷新前情境",
        status="ready",
        base="100",
        stressed="90",
        delta="-10",
        run_at="2026-10-22T09:00:00Z",
    )
    view._render_stress_history(
        SimpleNamespace(
            status="ready",
            db_path="synthetic://stress-history",
            records=(record,),
            blockers=(),
            warnings=(),
        )
    )
    model = view.stress_history_table.model()
    view.stress_history_table.setCurrentIndex(model.index(0, 0))
    assert view.stress_history_metric_values["base_market_value"].text() == "100"
    stale_index = model.index(0, 0)

    view._render_stress_history(
        SimpleNamespace(
            status="partial",
            db_path="synthetic://stress-history",
            records=(),
            blockers=(),
            warnings=("stress_history_empty",),
        )
    )
    assert view._stress_history_display_records == []
    assert view.stress_history_card_title.text() == "選取一筆已保存紀錄"
    assert view.stress_history_table.model().rowCount() == 1
    assert view.stress_history_table.model().data(
        view.stress_history_table.model().index(0, 0)
    ) == "N/A"
    view._show_stress_history_record(stale_index, QModelIndex())
    assert view.stress_history_card_title.text() == "選取一筆已保存紀錄"

    view.stress_history_read_service = SimpleNamespace(
        inspect=lambda: (_ for _ in ()).throw(OSError("synthetic read failure"))
    )
    view._load_stress_history()
    assert "讀取失敗" in view.stress_history_summary_label.text()
    assert view.stress_history_card_title.text() == "選取一筆已保存紀錄"
    assert all(value.text() == "未提供" for value in view.stress_history_metric_values.values())


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


def test_paper_portfolio_compact_empty_state_preserves_unknown_zero_and_rows(tmp_path):
    state_db = tmp_path / "paper_portfolio" / "paper_portfolio.sqlite"
    view = make_portfolio_view(tmp_path)
    assert view.paper_diagnostics_toggle.isCheckable()
    assert not view.paper_diagnostics_toggle.isChecked()
    assert view.paper_diagnostics_panel.isHidden()
    view.refresh_all()

    assert "尚無 Paper snapshot" in view.paper_snapshot_empty_label.text()
    assert "帳戶命名空間：paper-main" in view.paper_snapshot_empty_label.text()
    assert "raw 累積 0 筆｜持倉 0 檔" in view.paper_snapshot_empty_label.text()
    assert view.paper_snapshot_table.isHidden()

    empty_snapshot = PaperPortfolioSnapshot(
        snapshot_id="paper-main-20260822",
        portfolio_id="paper-main",
        decision_date="2026-08-22",
        source_result_id="rec-empty",
        cash=Decimal("0"),
        total_value=Decimal("0"),
        positions=(),
    )
    PaperPortfolioSnapshotRepository(state_db).append(empty_snapshot)
    view.refresh_all()

    assert "已有 Paper snapshot，但最新 snapshot 沒有持倉" in view.paper_snapshot_empty_label.text()
    assert "paper-main-20260822" in view.paper_snapshot_empty_label.text()
    assert "帳戶命名空間：paper-main" in view.paper_snapshot_empty_label.text()
    assert "raw 累積 1 筆｜持倉 0 檔" in view.paper_snapshot_empty_label.text()
    assert "總值 TWD 0.00｜現金 TWD 0.00" in view.paper_readiness_summary_label.text()
    assert "帳戶命名空間：paper-main｜最新 snapshot ID：paper-main-20260822" in view.paper_identity_label.text()
    assert view.paper_snapshot_table.isHidden()

    view._render_paper_readiness(
        replace(view._paper_readiness, latest_total_value=None, latest_cash=None)
    )
    assert "總值 未知｜現金 未知" in view.paper_readiness_summary_label.text()

    row_snapshot = PaperPortfolioSnapshot(
        snapshot_id="paper-main-20260823",
        portfolio_id="paper-main",
        decision_date="2026-08-23",
        source_result_id="rec-position",
        cash=Decimal("0"),
        total_value=Decimal("10"),
        positions=(
            PaperPortfolioPositionSnapshot(
                stock_code="2330",
                quantity=1,
                mark_price=Decimal("10"),
                market_value=Decimal("10"),
                weight_bp=10000,
            ),
        ),
    )
    PaperPortfolioSnapshotRepository(state_db).append(row_snapshot)
    view.refresh_all()

    assert not view.paper_snapshot_table.isHidden()
    assert view.paper_snapshot_table.model().rowCount() == 1
    assert view.paper_snapshot_empty_label.isHidden()
    assert "paper-main-20260823" in view.paper_identity_label.text()


def test_paper_actions_keep_full_labels_in_two_columns(tmp_path):
    view = make_portfolio_view(tmp_path)
    controls = view.paper_controls_layout
    assert isinstance(controls, QGridLayout)
    expected = (
        (view.btn_refresh_paper, 0, 0),
        (view.btn_build_paper_benchmark, 0, 1),
        (view.btn_import_paper_fills, 1, 0),
        (view.btn_export_paper_template, 1, 1),
        (view.paper_weekly_expected_days, 2, 0),
        (view.btn_refresh_paper_weekly, 2, 1),
    )
    for widget, row, column in expected:
        item = controls.itemAtPosition(row, column)
        assert item is not None and item.widget() is widget
    assert view.btn_refresh_paper.text() == "重新讀取 Paper 狀態"
    assert view.btn_build_paper_benchmark.text() == "預覽／建立 Equal Weight"
    assert view.btn_import_paper_fills.text() == "匯入 Paper 成交 CSV"
    assert view.btn_export_paper_template.text() == "匯出成交範本"
    assert view.btn_refresh_paper_weekly.text() == "計算最近週報"


def test_paper_diagnostics_toggle_and_refresh_keep_full_missing_and_error_details(tmp_path, monkeypatch):
    view = make_portfolio_view(tmp_path)
    readiness_inspect = view.paper_readiness_service.inspect
    weekly_build = view.paper_weekly_evidence_service.build_latest

    view.refresh_all()
    assert "最近週報" in view.paper_weekly_summary_label.text()
    assert "paper_snapshot_db_missing" in view.paper_weekly_report_label.text()
    assert view.paper_diagnostics_panel.isHidden()

    view.paper_diagnostics_toggle.click()
    assert not view.paper_diagnostics_panel.isHidden()
    assert view.paper_diagnostics_toggle.text() == "收合來源與完整診斷"
    assert "snapshot DB：" in view.paper_readiness_detail_label.text()
    assert "paper_snapshot_db_missing" in view.paper_weekly_report_label.text()
    view.paper_diagnostics_toggle.click()
    assert view.paper_diagnostics_panel.isHidden()

    monkeypatch.setattr(
        view.paper_readiness_service,
        "inspect",
        lambda: (_ for _ in ()).throw(RuntimeError("readiness fixture error")),
    )
    monkeypatch.setattr(
        view.paper_weekly_evidence_service,
        "build_latest",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("weekly fixture error")),
    )
    view.refresh_all()
    assert "狀態讀取失敗" in view.paper_readiness_summary_label.text()
    assert "讀取失敗" in view.paper_identity_label.text()
    assert "readiness fixture error" in view.paper_readiness_detail_label.text()
    assert "讀取失敗" in view.paper_weekly_summary_label.text()
    assert "weekly fixture error" not in view.paper_weekly_summary_label.text()
    assert "weekly fixture error" in view.paper_weekly_report_label.text()
    assert view.paper_diagnostics_panel.isHidden()

    monkeypatch.setattr(view.paper_readiness_service, "inspect", readiness_inspect)
    monkeypatch.setattr(view.paper_weekly_evidence_service, "build_latest", weekly_build)
    view.refresh_all()
    assert "最近週報" in view.paper_weekly_summary_label.text()
    assert "paper_snapshot_db_missing" in view.paper_weekly_report_label.text()
    assert view.paper_diagnostics_panel.isHidden()


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


@pytest.mark.parametrize(
    ("realized_pnl", "expected_color"),
    [
        (Decimal("12.5"), portfolio_view_module.MIDNIGHT_ANALYST.market_up),
        (Decimal("-12.5"), portfolio_view_module.MIDNIGHT_ANALYST.market_down),
        (Decimal("0"), portfolio_view_module.MIDNIGHT_ANALYST.text_primary),
    ],
    ids=["positive", "negative", "zero"],
)
def test_portfolio_realized_pnl_uses_taiwan_market_direction_colors(
    tmp_path, realized_pnl, expected_color
):
    view = make_portfolio_view(tmp_path)
    portfolio = replace(
        view.portfolio_service.get_portfolio(), total_realized_pnl=realized_pnl
    )

    view._load_portfolio_summary(portfolio)

    assert view.card_pnl.value_label.text() == f"TWD {realized_pnl:+,.2f}"
    assert f"color: {expected_color};" in view.card_pnl.value_label.styleSheet()


@pytest.mark.parametrize(
    ("pnl_pct", "expected_text", "expected_color"),
    [
        (0.01, "+1.00%", portfolio_view_module.MIDNIGHT_ANALYST.market_up),
        (-0.01, "-1.00%", portfolio_view_module.MIDNIGHT_ANALYST.market_down),
        (0.0, "+0.00%", portfolio_view_module.MIDNIGHT_ANALYST.text_primary),
        (None, "-", portfolio_view_module.MIDNIGHT_ANALYST.text_primary),
    ],
    ids=["positive", "negative", "zero", "unknown"],
)
def test_portfolio_monitor_pnl_preserves_value_and_unknown_quote_wording(
    tmp_path, pnl_pct, expected_text, expected_color
):
    view = make_portfolio_view(tmp_path)
    view.portfolio_service.positions[0].unrealized_pnl_pct = pnl_pct
    view.selected_stock_code = "2330"

    view._update_monitoring_tab()

    assert view.lbl_mon_pnl_pct.text() == expected_text
    assert f"color: {expected_color};" in view.lbl_mon_pnl_pct.styleSheet()
    assert "TWD 110.00" in view.lbl_mon_current_price.text()
    assert "行情資料日未知" in view.lbl_mon_current_price.text()
    assert "手動建立，無推薦 / 回測來源" in view.lbl_strat_id.text()


@pytest.mark.parametrize(
    ("consecutive", "net_qty", "expected_color"),
    [
        (2, 3000, portfolio_view_module.MIDNIGHT_ANALYST.market_up),
        (-2, -3000, portfolio_view_module.MIDNIGHT_ANALYST.market_down),
        (0, 0, portfolio_view_module.MIDNIGHT_ANALYST.text_primary),
    ],
    ids=["positive", "negative", "zero"],
)
def test_portfolio_chip_direction_values_use_market_colors(
    tmp_path, consecutive, net_qty, expected_color
):
    view = make_portfolio_view(tmp_path)
    view.chip_service.get_stock_chip_summary = lambda *_args, **_kwargs: {
        "risk_level": "neutral",
        "consecutive_days": consecutive,
        "accumulated_net": net_qty,
        "concentration": 0.0,
        "risk_reasons": [],
        "quality_counts": {},
        "branch_details": [],
    }
    view.selected_stock_code = "2330"

    view._update_monitoring_tab()

    assert f"color: {expected_color};" in view.lbl_chip_consecutive.styleSheet()
    assert f"color: {expected_color};" in view.lbl_chip_net_5d.styleSheet()


def test_portfolio_chip_summary_without_usable_events_renders_unknown_not_zero(tmp_path):
    view = make_portfolio_view(tmp_path)
    from app_module.portfolio_chip_service import PortfolioChipService

    service = PortfolioChipService(FakeConfig(tmp_path), broker_flow_service=object())
    empty_summary = service._empty_summary("2330", 5)
    view.chip_service.get_stock_chip_summary = lambda *_args, **_kwargs: empty_summary
    view.selected_stock_code = "2330"

    view._update_monitoring_tab()

    assert view.lbl_chip_risk_level.text() == "資料不足"
    assert view.lbl_chip_consecutive.text() == "資料不足"
    assert view.lbl_chip_net_5d.text() == "資料不足"
    assert view.lbl_chip_concentration.text() == "資料不足"
    assert view.lbl_chip_reasons.text() == "無主力分點交易數據"
    expected_color = portfolio_view_module.MIDNIGHT_ANALYST.text_primary
    assert f"color: {expected_color};" in view.lbl_chip_consecutive.styleSheet()
    assert f"color: {expected_color};" in view.lbl_chip_net_5d.styleSheet()


def test_portfolio_chip_available_true_zero_retains_neutral_zero_display(tmp_path):
    view = make_portfolio_view(tmp_path)
    view.chip_service.get_stock_chip_summary = lambda *_args, **_kwargs: {
        "risk_level": "neutral",
        "lots_available": True,
        "usable_event_count": 2,
        "consecutive_days": 0,
        "accumulated_buy": 500,
        "accumulated_sell": 500,
        "accumulated_net": 0,
        "concentration": 0.0,
        "risk_reasons": [],
        "quality_counts": {},
        "branch_details": [],
    }
    view.selected_stock_code = "2330"

    view._update_monitoring_tab()

    assert view.lbl_chip_risk_level.text() == "中性"
    assert view.lbl_chip_consecutive.text() == "0 天"
    assert view.lbl_chip_net_5d.text() == "+0.0 張"
    assert view.lbl_chip_concentration.text() == "0.00%"
    expected_color = portfolio_view_module.MIDNIGHT_ANALYST.text_primary
    assert f"color: {expected_color};" in view.lbl_chip_consecutive.styleSheet()
    assert f"color: {expected_color};" in view.lbl_chip_net_5d.styleSheet()


def test_portfolio_chip_concentration_zero_denominator_is_unavailable(tmp_path):
    view = make_portfolio_view(tmp_path)
    view.chip_service.get_stock_chip_summary = lambda *_args, **_kwargs: {
        "risk_level": "neutral",
        "lots_available": True,
        "usable_event_count": 1,
        "consecutive_days": 0,
        "accumulated_buy": 0,
        "accumulated_sell": 0,
        "accumulated_net": 0,
        "concentration": 0.0,
        "risk_reasons": [],
        "quality_counts": {},
        "branch_details": [],
    }
    view.selected_stock_code = "2330"

    view._update_monitoring_tab()

    assert view.lbl_chip_consecutive.text() == "0 天"
    assert view.lbl_chip_net_5d.text() == "+0.0 張"
    assert view.lbl_chip_concentration.text() == "資料不足"


def test_portfolio_chip_detail_empty_populated_reset_keeps_controls_reachable(tmp_path):
    view = make_portfolio_view(tmp_path)
    summary = {
        "risk_level": "neutral",
        "lots_available": True,
        "usable_event_count": 1,
        "consecutive_days": 0,
        "accumulated_buy": 1000,
        "accumulated_sell": 1000,
        "accumulated_net": 0,
        "concentration": 0.0,
        "risk_reasons": [],
        "quality_counts": {},
        "branch_details": [],
    }
    view.chip_service.get_stock_chip_summary = lambda *_args, **_kwargs: summary
    view.selected_stock_code = "2330"
    view._update_monitoring_tab()

    chip_tab = view.btn_drill_down_chip.parentWidget()
    chip_layout = chip_tab.layout()
    assert chip_layout is not None
    assert view.lbl_chip_risk_level.text() == "中性"
    assert not view.lbl_chip_detail_empty.isHidden()
    assert view.chip_detail_table.isHidden()
    assert view.chip_detail_table.model() is not None
    assert view.chip_detail_table.model().rowCount() == 0
    assert not view.btn_drill_down_chip.isHidden()
    assert chip_layout.indexOf(view.btn_drill_down_chip) == 2
    assert chip_layout.itemAt(0).widget().sizePolicy().verticalPolicy() == QSizePolicy.Maximum
    assert chip_layout.itemAt(1).widget().sizePolicy().verticalPolicy() == QSizePolicy.Maximum
    assert chip_layout.itemAt(3).spacerItem() is not None

    summary["branch_details"] = [
        {
            "display_name": f"測試分點 {index}",
            "buy_qty": 1000 + index * 1000,
            "sell_qty": 250,
            "net_qty": 750 + index * 1000,
        }
        for index in range(7)
    ]
    view._update_monitoring_tab()

    detail_model = view.chip_detail_table.model()
    assert detail_model is not None
    assert detail_model.rowCount() == 7
    assert not view.chip_detail_table.isHidden()
    assert view.lbl_chip_detail_empty.isHidden()
    assert detail_model.getDataFrame().iloc[0]["分點名稱"] == "測試分點 0"
    assert detail_model.getDataFrame().iloc[0]["買進張數"] == 1.0
    five_row_cap = (
        view.chip_detail_table.horizontalHeader().sizeHint().height()
        + view.chip_detail_table.verticalHeader().defaultSectionSize() * 5
        + view.chip_detail_table.horizontalScrollBar().sizeHint().height()
        + view.chip_detail_table.frameWidth() * 2
        + 8
    )
    assert view.chip_detail_table.maximumHeight() <= five_row_cap
    assert not view.btn_drill_down_chip.isHidden()
    assert chip_layout.indexOf(view.btn_drill_down_chip) == 2

    view.selected_stock_code = ""
    view._update_monitoring_tab()

    assert view.chip_detail_table.model() is None
    assert view.chip_detail_table.isHidden()
    assert not view.lbl_chip_detail_empty.isHidden()
    assert not view.btn_drill_down_chip.isHidden()
    assert chip_layout.indexOf(view.btn_drill_down_chip) == 2


def test_portfolio_monitor_unknown_direction_values_use_neutral_text_color(tmp_path):
    view = make_portfolio_view(tmp_path)
    view.selected_stock_code = ""

    view._update_monitoring_tab()

    expected_color = portfolio_view_module.MIDNIGHT_ANALYST.text_primary
    assert view.lbl_mon_pnl_pct.text() == "-"
    assert view.lbl_chip_consecutive.text() == "-"
    assert view.lbl_chip_net_5d.text() == "-"
    assert f"color: {expected_color};" in view.lbl_mon_pnl_pct.styleSheet()
    assert f"color: {expected_color};" in view.lbl_chip_consecutive.styleSheet()
    assert f"color: {expected_color};" in view.lbl_chip_net_5d.styleSheet()


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
    assert context.ml_scope_mode == "current_stock_research"
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
    assert contexts[0].ml_scope_mode == ""
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
