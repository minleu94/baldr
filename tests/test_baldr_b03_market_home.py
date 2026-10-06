"""B03 隔離首頁與市場判讀契約；不讀正式來源或個人資料。"""
import os
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from app_module.dtos import RegimeResultDTO
from app_module.workbench_dtos import WorkbenchDailyEvidence
from ui_qt.views.market_regime_view import MarketRegimeView
from ui_qt.views.workbench_view import UnifiedDecisionWorkbenchView
from test_ui_qt_workbench_view import _dashboard_with_replay


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def daily_fixture(**changes):
    return replace(WorkbenchDailyEvidence(
        status="observed", decision_date="2026-10-05", data_as_of_date="2026-10-02",
        headline="合成來源，尚待研究", next_action="核對原來源",
        market_summary="市場來源未知", industry_summary="產業來源未知",
        stock_summary="股票來源未知", watchlist_summary="清單來源未知",
        portfolio_summary="持倉來源未知",
    ), **changes)


class RegimeFixture:
    def __init__(self, details=None, fail=False):
        self.details = details if details is not None else {
            "date": "2026-10-05", "close_above_ma60": True,
            "ma20_slope_positive": False,
        }
        self.fail = fail

    def detect_regime(self):
        if self.fail:
            raise RuntimeError("synthetic source unavailable")
        return RegimeResultDTO(
            regime="Trend", confidence=0.82, details=self.details,
            regime_name_cn="趨勢盤",
        )

    def get_strategy_config(self, regime):
        return {}


@pytest.mark.parametrize("expanded", [False, True])
def test_detect_refresh_preserves_disclosure_choice(qapp, expanded):
    view = MarketRegimeView(RegimeFixture())
    view.layer3_group.setChecked(expanded)
    for _ in range(2):
        view._detect_regime()
        assert view.layer3_group.isChecked() is expanded
        assert view.layer3_scroll_area.isHidden() is not expanded
        assert view.layer3_layout.count() > 1
    assert "2026-10-05" in view.layer1_confidence.text()
    assert "不是勝率" in view.market_risk_label.text()
    assert "核對" in view.market_next_step_label.text()
    view.close()


def test_missing_conditions_and_date_remain_unknown(qapp):
    view = MarketRegimeView(RegimeFixture(details={}))
    view._detect_regime()
    assert view.layer2_label.text().count("未知（來源未提供）") == 2
    assert "價格未在中長期均線之上" not in view.layer2_label.text()
    assert "資料日未知" in view.market_risk_label.text()
    assert "適合順勢操作" not in view.layer1_description.text()
    view.close()


@pytest.mark.parametrize("details,fail", [({"error": "synthetic missing"}, False), ({}, True)])
def test_failure_does_not_publish_default_trend(qapp, details, fail):
    service = RegimeFixture()
    view = MarketRegimeView(service)
    view.layer3_group.setChecked(True)
    view._detect_regime()
    service.details = details
    service.fail = fail
    view._detect_regime()
    assert view.layer1_status.text() == "檢測失敗"
    assert view.layer1_confidence.text() == ""
    assert view.layer3_layout.count() == 0
    assert view.layer3_group.isChecked()
    assert "不能使用市場分類" in view.market_risk_label.text()
    view.close()


def test_four_purposes_use_existing_callbacks_without_expanding_details(qapp):
    calls = []
    view = UnifiedDecisionWorkbenchView(
        dashboard=_dashboard_with_replay(), auto_refresh=False,
        navigate_to_market_explore_callback=lambda: calls.append("market"),
        navigate_to_daily_decision_callback=lambda: calls.append("old_overview"),
        navigate_to_portfolio_callback=lambda: calls.append("portfolio"),
        navigate_to_recommendation_callback=lambda: calls.append("selection"),
        navigate_to_stock_research_callback=calls.append,
    )
    for key in ("market", "portfolio", "selection"):
        view.home_purpose_buttons[key].click()
    view.home_purpose_buttons["stock"].click()
    assert calls == ["market", "portfolio", "selection"]
    assert view.advanced_workbench_panel.is_collapsed()
    view.guided_priority_action_buttons["market"].click()
    view.guided_priority_action_buttons["portfolio"].click()
    assert calls[-2:] == ["market", "portfolio"]
    assert view.advanced_workbench_panel.is_collapsed()
    view.close()


def test_explicit_search_does_not_borrow_saved_candidate_identity(qapp):
    calls = []
    daily = daily_fixture(
        status="observed", decision_date="2026-10-05", data_as_of_date="2026-10-02",
        candidate_symbols=("2330",), candidate_result_id="saved-result",
        candidate_source_id="saved-source", candidate_data_date="2026-10-01",
    )
    view = UnifiedDecisionWorkbenchView(
        dashboard=replace(_dashboard_with_replay(), daily_evidence=daily),
        auto_refresh=False, navigate_to_stock_research_callback=calls.append,
    )
    view.home_stock_input.setText(" 2382 ")
    view.home_stock_search_button.click()
    current = calls[-1]
    assert current.stock_code == "2382"
    assert current.source_kind == "explicit_latest_stock_research"
    assert current.source_workspace == "workbench"
    assert (current.decision_date, current.data_date, current.result_id, current.source_id) == ("", "", "", "")
    assert view._open_daily_candidate_research()
    saved = calls[-1]
    assert (saved.stock_code, saved.decision_date, saved.data_date, saved.result_id, saved.source_id) == (
        "2330", "2026-10-05", "2026-10-01", "saved-result", "saved-source",
    )
    assert saved.source_kind == "scheduled_recommendation"
    view.close()


@pytest.mark.parametrize("code", ["", "2330;1", "台積電", "１２３４"])
def test_invalid_search_keeps_context_unchanged(qapp, code):
    calls = []
    view = UnifiedDecisionWorkbenchView(auto_refresh=False, navigate_to_stock_research_callback=calls.append)
    view.home_stock_input.setText(code)
    assert not view._open_home_stock_search()
    assert not calls
    assert "請輸入" in view.home_stock_search_hint.text()
    view.close()


def test_unwired_purpose_is_disabled(qapp):
    view = UnifiedDecisionWorkbenchView(auto_refresh=False)
    assert all(not button.isEnabled() for button in view.home_purpose_buttons.values())
    assert not view.home_stock_search_button.isEnabled()
    assert not view.navigate_to_drilldown_target("market_explore")
    view.close()


def test_technical_tokens_are_translated_with_original_trace_retained(qapp):
    daily = daily_fixture(
        headline="source_missing:DecisionDeskSnapshot PIT=false",
        next_action="確認 scope receipt 與 EvidenceEvent table",
    )
    view = UnifiedDecisionWorkbenchView(
        dashboard=replace(_dashboard_with_replay(), daily_evidence=daily), auto_refresh=False,
    )
    assert "DecisionDeskSnapshot" not in view.guided_conclusion_label.text()
    assert "歷史時點資格未具備" in view.guided_conclusion_label.text()
    assert "source_missing" in view.guided_conclusion_label.toolTip()
    assert "scope receipt" not in view.guided_next_action_label.text()
    assert "scope receipt" in view.guided_next_action_label.toolTip()
    assert view.advanced_workbench_panel.is_collapsed()
    view.close()
