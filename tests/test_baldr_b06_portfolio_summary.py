"""B06 合成分帳／缺件呈現，不執行正式資料或金融公式。"""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from PySide6.QtCore import Qt

from tests.test_ui_qt_portfolio_view import (
    make_portfolio_view, FakeConfig, FakePortfolioService, FakeJournalService, FakeConditionMonitor,
)
from tests.test_ui_qt_user_declared_holding_research import (
    EARLY_NOW, EARLY_DATE, _app, _service, _market, _condition,
)
from app_module.user_declared_holding_research import UserDeclaredHoldingDraft
from app_module.portfolio_condition_monitor import PortfolioCurrentSnapshot
from app_module.user_declared_holding_research import UserDeclaredHoldingResearchStore
from app_module.paper_portfolio_readiness_service import PaperPortfolioReadinessService
from app_module.paper_portfolio_weekly_evidence_service import PaperPortfolioWeeklyEvidenceService
from ui_qt.views.portfolio_view import PortfolioView
from ui_qt.widgets.user_declared_holding_research_widget import (
    UserDeclaredHoldingResearchTableModel,
)


def test_account_selection_keeps_manual_values_out_of_declared_and_paper(tmp_path):
    view = make_portfolio_view(tmp_path)
    try:
        original = view.card_invested.value_label.text()
        for account, tab in (("user_declared", "聲明持倉研究"), ("paper", "Paper Portfolio")):
            view.portfolio_account_selector.setCurrentIndex(
                view.portfolio_account_selector.findData(account)
            )
            assert view.manual_account_panel.isHidden()
            assert view.card_invested.isHidden()
            assert view.card_net_val.isHidden()
            assert view.portfolio_focus_summary.isHidden()
            assert view.portfolio_detail_tabs.tabText(view.portfolio_detail_tabs.currentIndex()) == tab
            assert "不合併" in view.portfolio_account_context_label.text()
            assert view.card_invested.value_label.text() == original
        view.portfolio_account_selector.setCurrentIndex(0)
        assert not view.manual_account_panel.isHidden()
        assert not view.card_invested.isHidden()
        assert not view.portfolio_focus_summary.isHidden()
    finally:
        view.close()


@pytest.mark.parametrize("missing", ["price", "date", "mixed_date", "wrong_price", "foreign_stock", "future"])
def test_partial_or_different_valuation_dates_do_not_show_portfolio_total(tmp_path, missing):
    view = make_portfolio_view(tmp_path)
    try:
        portfolio = view.portfolio_service.get_portfolio()
        for position in portfolio.positions:
            position.source_summary = {"current_price_date": "2026-10-02"}
            view._position_current_snapshots[position.position_id] = (
                position.stock_code, PortfolioCurrentSnapshot(
                    current_price=position.current_price, quote_data_date=date(2026, 10, 2),
                ),
            )
        if missing == "price":
            portfolio.positions[1].current_price = None
        elif missing == "date":
            position = portfolio.positions[1]
            view._position_current_snapshots[position.position_id] = (
                position.stock_code, PortfolioCurrentSnapshot(current_price=position.current_price),
            )
        elif missing == "mixed_date":
            position = portfolio.positions[1]
            view._position_current_snapshots[position.position_id] = (
                position.stock_code, PortfolioCurrentSnapshot(
                    current_price=position.current_price, quote_data_date=date(2026, 10, 1),
                ),
            )
        elif missing == "wrong_price":
            position = portfolio.positions[1]
            view._position_current_snapshots[position.position_id] = (
                position.stock_code, PortfolioCurrentSnapshot(
                    current_price=Decimal("999"), quote_data_date=date(2026, 10, 2),
                ),
            )
        elif missing == "foreign_stock":
            position = portfolio.positions[1]
            view._position_current_snapshots[position.position_id] = (
                "2330", PortfolioCurrentSnapshot(
                    current_price=position.current_price, quote_data_date=date(2026, 10, 2),
                ),
            )
        else:
            position = portfolio.positions[1]
            view._position_current_snapshots[position.position_id] = (
                position.stock_code, PortfolioCurrentSnapshot(
                    current_price=position.current_price, quote_data_date=date(2999, 1, 1),
                ),
            )
        view._load_portfolio_summary(portfolio)
        assert "未知" in view.card_net_val.value_label.text()
        assert "261,000" not in view.card_net_val.value_label.text()
        view._render_portfolio_focus_summary(portfolio)
        assert "估值日期" in view.portfolio_focus_summary.change_label.text()
        assert "未提供，未知" in view.portfolio_focus_summary.risk_label.text()
        assert "不判安全" in view.portfolio_focus_summary.risk_label.text()
        assert "不是估值日" in view.portfolio_focus_summary.evidence_label.text()
    finally:
        view.close()


def test_same_date_existing_values_and_last_good_refresh_stay_separate(tmp_path):
    view = make_portfolio_view(tmp_path)
    try:
        portfolio = view.portfolio_service.get_portfolio()
        for position in portfolio.positions:
            position.source_summary = {"current_price_date": "2026-10-02"}
            view._position_current_snapshots[position.position_id] = (
                position.stock_code, PortfolioCurrentSnapshot(
                    current_price=position.current_price, quote_data_date=date(2026, 10, 2),
                ),
            )
        view._load_portfolio_summary(portfolio)
        assert view.card_net_val.value_label.text() == "TWD 261,000.00"
        view._render_portfolio_focus_summary(portfolio)
        assert "同股原來源" in view.portfolio_focus_summary.next_step_label.text()
        view._set_portfolio_focus_state("cancelled")
        assert "上次可用資料" in view.portfolio_focus_summary.conclusion_label.text()
        assert "最新資料尚未確認" in view.portfolio_focus_summary.sufficiency_label.text()
    finally:
        view.close()


def test_declared_table_keeps_decimal_precision_date_and_unknown(tmp_path):
    _app()
    service = _service(tmp_path, lambda: EARLY_NOW)
    service.create_holding(UserDeclaredHoldingDraft(
        stock_code="2330", quantity=3, declared_cost=Decimal("100.123456789"),
        declared_date=EARLY_DATE, thesis="合成研究假設",
    ))
    model = service.read_research(
        evaluation_date=EARLY_DATE, market_source=_market, condition_source=_condition,
    )
    row = model.rows[0]
    table = UserDeclaredHoldingResearchTableModel((row,))
    assert table.data(table.index(0, 2), Qt.DisplayRole) == "100.123456789"
    assert table.data(table.index(0, 6), Qt.DisplayRole) == row.market_as_of_date.isoformat()
    table.set_rows((replace(row, market_price=None, market_as_of_date=None,
                            mark_to_declared_cost_delta=None),))
    assert table.data(table.index(0, 5), Qt.DisplayRole) == "未知"
    assert table.data(table.index(0, 6), Qt.DisplayRole) == "未知"
    assert table.data(table.index(0, 7), Qt.DisplayRole) == "未知"


def _paper_services(root, *, weekly_id="paper-test"):
    readiness = PaperPortfolioReadinessService(output_root=root, portfolio_id="paper-test")
    weekly = PaperPortfolioWeeklyEvidenceService(
        output_root=root, portfolio_id=weekly_id,
        benchmark_db_path=readiness.benchmark_db_path,
        cost_ledger_db_path=readiness.cost_ledger_db_path,
    )
    return readiness, weekly


def test_injected_private_services_are_exact_and_never_use_legacy_defaults(tmp_path):
    _app()
    config = FakeConfig(tmp_path / "legacy")
    config.personal_store_mode = "personal"
    store = UserDeclaredHoldingResearchStore(tmp_path / "private" / "holdings.jsonl")
    readiness, weekly = _paper_services(tmp_path / "private" / "paper")
    view = PortfolioView(
        FakePortfolioService(config), FakeJournalService(), condition_monitor=FakeConditionMonitor(),
        user_declared_store=store, user_declared_portfolio_id="declared-test",
        paper_readiness_service=readiness, paper_weekly_evidence_service=weekly,
    )
    try:
        assert view.user_declared_research_service.store is store
        assert view.user_declared_research_widget.portfolio_id == "declared-test"
        assert view.paper_readiness_service is readiness
        assert view.paper_weekly_evidence_service is weekly
        assert not (config.output_root / "portfolio").exists()
        assert not (config.output_root / "paper_portfolio").exists()
    finally:
        view.close()


@pytest.mark.parametrize("mode", ["personal", "legacy_read_only", "root_only"])
def test_configured_private_mode_without_injection_refuses_legacy(tmp_path, mode):
    _app()
    config = FakeConfig(tmp_path / "legacy")
    if mode == "root_only":
        config.personal_store_root = tmp_path / "private"
    else:
        config.personal_store_mode = mode
    with pytest.raises(ValueError, match="不回退 legacy"):
        PortfolioView(FakePortfolioService(config), FakeJournalService())
    assert not config.output_root.exists()


def test_partial_paper_injection_and_mismatched_identity_are_rejected(tmp_path):
    _app()
    config = FakeConfig(tmp_path / "legacy")
    readiness, weekly = _paper_services(tmp_path / "private")
    with pytest.raises(ValueError, match="成對注入"):
        PortfolioView(FakePortfolioService(config), FakeJournalService(), paper_readiness_service=readiness)
    for field_name in (
        "portfolio_id", "benchmark_id", "state_db_path", "benchmark_db_path", "cost_ledger_db_path",
    ):
        original = getattr(weekly, field_name)
        setattr(weekly, field_name, str(original) + "-other")
        with pytest.raises(ValueError, match=f"不一致：{field_name}"):
            PortfolioView(
                FakePortfolioService(config), FakeJournalService(),
                paper_readiness_service=readiness, paper_weekly_evidence_service=weekly,
            )
        setattr(weekly, field_name, original)
    assert not config.output_root.exists()
