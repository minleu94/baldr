import os
import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from app_module.advice_dtos import (
    AdviceAction,
    AdviceClassification,
    AdviceDashboardDTO,
    AdviceMode,
    AdvicePolicyConfig,
    RecommendationAdviceDTO,
)
from app_module.research_session import ResearchStockContextDTO
from app_module.workbench_dtos import WorkbenchDailyEvidence
from ui_qt.views.workbench_view import UnifiedDecisionWorkbenchView

from test_ui_qt_workbench_view import _dashboard_with_replay


def _app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def _daily(
    symbols: tuple[str, ...],
    *,
    result_id: str = "result-1",
    source_id: str = "source-1",
    decision_date: str = "2026-10-16",
    data_date: str = "2026-10-15",
    status: str = "candidate",
) -> WorkbenchDailyEvidence:
    return WorkbenchDailyEvidence(
        status="observed",
        decision_date=decision_date,
        data_as_of_date=data_date,
        headline="候選僅供研究。",
        next_action="逐檔查看既有來源。",
        market_summary="來源已提供。",
        industry_summary="來源已提供。",
        stock_summary="候選由每日來源提供。",
        watchlist_summary="只讀。",
        portfolio_summary="只讀。",
        candidate_symbols=symbols,
        candidate_count=len(symbols),
        candidate_status=status,
        candidate_result_id=result_id,
        candidate_source_id=source_id,
        candidate_source_snapshot_id="snapshot-1",
        candidate_data_date=data_date,
        candidate_identity=tuple(f"row-{symbol}" for symbol in symbols),
    )


def _view(
    daily: WorkbenchDailyEvidence,
    advice: AdviceDashboardDTO | None = None,
    *,
    decision_callback=None,
):
    contexts: list[ResearchStockContextDTO] = []
    dashboard = replace(
        _dashboard_with_replay(), daily_evidence=daily, advice_dashboard=advice
    )
    view = UnifiedDecisionWorkbenchView(
        dashboard=dashboard,
        auto_refresh=False,
        navigate_to_stock_research_callback=contexts.append,
        save_advice_research_decision_callback=decision_callback,
    )
    return view, contexts


def _advice_row(
    stock_code: str,
    *,
    result_id: str = "result-1",
    decision_date: str = "2026-10-16",
    data_date: str = "2026-10-15",
    classification: AdviceClassification = AdviceClassification.PROFESSIONAL_CANDIDATE,
) -> RecommendationAdviceDTO:
    return RecommendationAdviceDTO(
        stock_code=stock_code,
        advice_action=AdviceAction.RESEARCH,
        classification=classification,
        why_reasons=(f"{stock_code} 僅供研究。",),
        confidence_tier="low",
        evidence_tier="insufficient",
        strategy_version="research-v1",
        decision_date=decision_date,
        data_as_of_date=data_date,
        source_result_id=result_id,
        source_trace=(result_id,),
    )


def _advice_dashboard(*rows: RecommendationAdviceDTO) -> AdviceDashboardDTO:
    return AdviceDashboardDTO(
        decision_date="2026-10-16",
        data_as_of_date="2026-10-15",
        mode=AdviceMode.PROFESSIONAL,
        policy=AdvicePolicyConfig(),
        recommendations=tuple(rows),
    )


@pytest.mark.parametrize(
    "classification",
    [
        AdviceClassification.FORMAL_ADVICE,
        AdviceClassification.PROFESSIONAL_CANDIDATE,
    ],
)
def test_selected_daily_candidate_opens_only_its_exact_matching_advice_card(
    classification: AdviceClassification,
) -> None:
    application = _app()
    daily = _daily(("2330", "2603"))
    advice = _advice_dashboard(
        _advice_row("2330"), _advice_row("2603", classification=classification)
    )
    view, _contexts = _view(daily, advice)
    view.show()
    application.processEvents()

    assert not view.daily_candidate_advice_button.isEnabled()
    view.daily_candidate_selector.setCurrentIndex(
        view.daily_candidate_selector.findData("2603")
    )
    assert view.daily_candidate_advice_button.isEnabled()
    assert view.daily_candidate_advice_button.text() == "查看 2603 的策略判讀"
    assert view.advice_recommendation_table.isHidden()
    assert len(view._advice_candidate_card_buttons) == 2

    view.daily_candidate_advice_button.click()

    assert view.advice_candidate_table.selectionModel().currentIndex().row() == 1
    assert view._selected_advice_presentation is not None
    assert view._expanded_advice_candidate_row == 1
    assert not view._advice_candidate_detail_hosts[1].isHidden()
    assert "2603 僅供研究" in view.advice_selection_card.text()
    assert view.overview_scroll_area.widget() is not None
    view.close()


@pytest.mark.parametrize(
    "rows, advice_data_date",
    [
        ((_advice_row("2603", result_id="other-result"),), "2026-10-15"),
        ((_advice_row("2603", decision_date="2026-10-15"),), "2026-10-15"),
        ((_advice_row("2603", data_date="2026-10-14"),), "2026-10-15"),
        ((_advice_row("2603"), _advice_row("2603")), "2026-10-15"),
        ((_advice_row("2603"),), ""),
    ],
)
def test_daily_candidate_advice_link_fails_closed_on_identity_date_or_ambiguity(
    rows: tuple[RecommendationAdviceDTO, ...], advice_data_date: str
) -> None:
    _app()
    daily = _daily(("2603",))
    advice = AdviceDashboardDTO(
        decision_date="2026-10-16",
        data_as_of_date=advice_data_date,
        mode=AdviceMode.PROFESSIONAL,
        policy=AdvicePolicyConfig(),
        recommendations=rows,
    )
    view, _contexts = _view(daily, advice)
    try:
        assert not view.daily_candidate_advice_button.isEnabled()
        assert view._open_daily_candidate_advice() is False
        assert view.advice_candidate_table.selectionModel().currentIndex().row() == -1
    finally:
        view.close()


def test_selecting_exact_advice_candidate_reads_research_state_without_writing() -> None:
    application = _app()
    calls: list[tuple[str, dict[str, str], str]] = []

    def read_decision(action: str, identity: dict[str, str], note: str = ""):
        calls.append((action, identity, note))
        return SimpleNamespace(
            identity=SimpleNamespace(
                result_id="result-1",
                stock_code="2603",
                decision_date="2026-10-16",
                source_snapshot_id="snapshot-1",
                source_snapshot_hash="",
                identity_status="linked",
            ),
            read_error="",
            identity_conflict_reason="",
            decision_status="accepted",
            active_note_count=2,
            next_review_at="2026-10-27T09:00:00+08:00",
        )

    view, _contexts = _view(
        _daily(("2603",)),
        _advice_dashboard(_advice_row("2603")),
        decision_callback=read_decision,
    )
    try:
        view.show()
        application.processEvents()
        view.advice_candidate_table.selectRow(0)
        application.processEvents()
        view.advice_candidate_table.clicked.emit(view.advice_candidate_model.index(0, 0))
        application.processEvents()

        assert [action for action, _identity, _note in calls] == ["readback"]
        assert calls[0][1] == {
            "result_id": "result-1",
            "stock_code": "2603",
            "decision_date": "2026-10-16",
            "source_snapshot_id": "snapshot-1",
            "source_snapshot_hash": "",
            "identity_status": "linked",
        }
        status = view.advice_research_decision_status.text()
        assert "目前人工決定=已納入研究" in status
        assert "研究註記=2 筆" in status
        assert "下次檢視=2026-10-27T09:00:00+08:00" in status
        assert view.advice_accept_decision_button.isEnabled()
        assert view.advice_research_decision_status.isVisible()
    finally:
        view.close()


def test_second_candidate_opens_exact_selected_context_through_candidate_shortcut() -> None:
    application = _app()
    view, contexts = _view(_daily(("2330", "2603")))
    view.show()
    application.processEvents()

    assert view.daily_candidate_selector.currentData() is None
    assert not view.daily_candidate_button.isEnabled()
    assert not view.today_action_buttons["advice"].isEnabled()

    view.daily_candidate_selector.setCurrentIndex(
        view.daily_candidate_selector.findData("2603")
    )
    assert view.daily_candidate_button.text() == "開啟 2603 個股研究報告"
    assert view.daily_candidate_button.isEnabled()
    assert view.today_action_buttons["advice"].isEnabled()

    view.today_action_buttons["advice"].click()

    assert len(contexts) == 1
    context = contexts[0]
    assert context.stock_code == "2603"
    assert context.decision_date == "2026-10-16"
    assert context.data_date == "2026-10-15"
    assert context.result_id == "result-1"
    assert context.source_id == "source-1"
    assert context.source_snapshot_id == "snapshot-1"
    assert context.source_kind == "scheduled_recommendation"
    assert context.source_workspace == "workbench"
    view.close()


@pytest.mark.parametrize("reasons", [("2330：原來源的研究理由。",), ()])
def test_candidate_card_keeps_original_reason_while_market_gap_stays_inspectable(reasons) -> None:
    _app()
    raw_summary = "個股：缺少市場快照或每日候選；請先檢查來源。"
    daily = replace(
        _daily(("2330",)),
        candidate_reasons=reasons,
        stock_summary=raw_summary,
        market_summary="市場快照缺失，不能判定市場狀態。",
    )
    view, _contexts = _view(daily)
    try:
        view.render_dashboard(replace(
            _dashboard_with_replay(), daily_evidence=daily,
            action_items=(), review_items=(), market_context={"source_status": "missing"},
        ))
        reason = view.guided_priority_reason_labels["candidates"].text()
        assert ("原來源的研究理由" if reasons else "原來源未提供可確認對應個股的研究理由") in reason
        assert "候選僅供研究，不代表可交易" in reason
        assert "候選資料日：2026-10-15" in reason
        assert raw_summary not in reason
        assert raw_summary in view.daily_trace_label.text()
        assert "市場快照缺失" in view.guided_priority_reason_labels["market"].text()
        assert view._daily_investment_evidence is daily
        assert view.daily_candidate_button.isEnabled()
    finally:
        view.close()


def test_home_candidate_rows_match_only_explicit_symbol_reasons_and_open_original_context() -> None:
    _app()
    daily = replace(
        _daily(("2330", "2603", "1101")),
        candidate_reasons=("2603：這是2603的原始說明。",),
    )
    view, contexts = _view(daily)
    try:
        first_text = view.home_candidate_preview.findChildren(QLabel)
        joined_text = "\n".join(label.text() for label in first_text)
        assert "2330｜名稱未提供" in joined_text
        assert "2603｜名稱未提供" in joined_text
        assert "2330的原始說明" not in joined_text
        assert "2603：這是2603的原始說明。" in joined_text
        assert "個別說明" in joined_text
        assert "資料日：2026-10-15" in joined_text
        assert "這是2603的原始說明" not in view.daily_candidate_detail_label.text()
        assert "逐股原始理由請看上方候選列" in view.daily_candidate_detail_label.text()

        button = view.home_candidate_preview.findChild(QPushButton, "homeCandidateOpen_2603")
        assert button is not None and button.isEnabled()
        button.click()
        assert len(contexts) == 1
        assert contexts[0].stock_code == "2603"
        assert contexts[0].source_snapshot_id == "snapshot-1"
        assert contexts[0].data_date == "2026-10-15"
        assert view.daily_candidate_selector.count() == 4
    finally:
        view.close()


def test_home_market_card_projects_only_existing_numeric_market_fields() -> None:
    _app()
    dashboard = replace(
        _dashboard_with_replay(),
        market_context={
            "source_status": "partial",
            "market_breadth": {
                "quality": "degraded", "advancing": 812, "declining": 506,
                "unchanged": 42, "breadth_ratio_bp": 6150, "as_of_date": "2026-10-15",
            },
            "market_regime": {
                "quality": "observed", "regime_label": "區間整理",
                "regime_score": 2, "regime_confidence": 71, "as_of_date": "2026-10-14",
            },
        },
    )
    view = UnifiedDecisionWorkbenchView(dashboard=dashboard, auto_refresh=False)
    try:
        assert view.daily_market_card.value_label.text() == "區間整理"
        assert view.daily_market_kpi_labels["advancing"].text() == "812"
        assert view.daily_market_kpi_labels["declining"].text() == "506"
        assert view.daily_market_kpi_labels["unchanged"].text() == "42"
        assert view.daily_market_breadth_ratio_label.text() == "61.50%"
        assert view.daily_market_breadth_ratio_label.accessibleName() == "上漲占漲跌股比"
        assert "不含平盤" in view.daily_market_breadth_ratio_label.toolTip()
        footer = view.daily_market_footer_label.text()
        assert footer == "資料日 2026-10-15｜品質 品質降級｜來源 部分可用（資料缺件）"
        visible_text = " ".join((
            view.daily_market_card.value_label.text(),
            *(label.text() for label in view.daily_market_kpi_labels.values()),
            view.daily_market_breadth_ratio_label.text(),
            footer,
        ))
        assert "61.50%" in visible_text and "信心值" not in visible_text
        assert "成交額" not in visible_text and "指數收盤" not in visible_text

        view.render_dashboard(replace(
            dashboard,
            market_context={
                "source_status": "ready",
                "market_breadth": {"quality": "observed", "breadth_ratio_bp": 0},
            },
        ))
        assert view.daily_market_breadth_ratio_label.text() == "0.00%"
    finally:
        view.close()


def test_home_market_kpis_clear_missing_values_and_old_status_after_refresh() -> None:
    _app()
    dashboard = replace(
        _dashboard_with_replay(),
        market_context={
            "source_status": "partial",
            "market_breadth": {
                "quality": "degraded", "advancing": 812,
                "declining": 506, "unchanged": 42, "breadth_ratio_bp": 6150,
                "as_of_date": "2026-10-15",
            },
        },
    )
    view = UnifiedDecisionWorkbenchView(dashboard=dashboard, auto_refresh=False)
    try:
        view.render_dashboard(replace(
            dashboard,
            market_context={
                "source_status": "blocked",
                "market_breadth": {"quality": "missing"},
            },
        ))
        assert view.daily_market_card.value_label.text() == "市場資料來源受阻"
        assert all(label.text() == "—" for label in view.daily_market_kpi_labels.values())
        assert view.daily_market_breadth_ratio_label.text() == "未提供"
        assert view.daily_market_footer_label.text() == "資料日 未提供｜品質 資料缺件｜來源 受阻"
        assert "812" not in view.daily_market_card.value_label.text()
        assert "partial" not in view.daily_market_footer_label.text()

        view.render_dashboard(replace(dashboard, market_context={}))
        assert view.daily_market_card.value_label.text() == "市場狀態待確認"
        assert all(label.text() == "—" for label in view.daily_market_kpi_labels.values())
        assert view.daily_market_breadth_ratio_label.text() == "未提供"
        assert view.daily_market_footer_label.text() == "資料日 未提供｜品質 未知｜來源 未知"
        assert "unknown" not in view.daily_market_footer_label.text()

        view.render_dashboard(replace(
            dashboard,
            market_context={
                "source_status": "partial",
                "market_breadth": {"quality": "degraded", "breadth_ratio_bp": True},
            },
        ))
        assert view.daily_market_breadth_ratio_label.text() == "無效值"

        view.render_dashboard(replace(dashboard, market_context={}))
        assert view.daily_market_breadth_ratio_label.text() == "未提供"
    finally:
        view.close()


def test_unselected_candidate_and_shared_route_do_not_open_first_symbol() -> None:
    application = _app()
    view, contexts = _view(_daily(("2330", "2603")))
    view.show()
    application.processEvents()

    view.daily_candidate_button.click()
    assert not view.navigate_to_drilldown_target("stock_research")
    assert contexts == []
    view.close()


def test_refresh_keeps_same_identity_selection_but_changed_source_clears_it() -> None:
    application = _app()
    daily = _daily(("2330", "2603"))
    view, contexts = _view(daily)
    view.show()
    application.processEvents()
    view.daily_candidate_selector.setCurrentIndex(
        view.daily_candidate_selector.findData("2603")
    )

    same_source = replace(daily, candidate_reasons=("更新的說明文字。",))
    view._render_daily_investment_journey(same_source)
    assert view.daily_candidate_selector.currentData() == "2603"

    changed_source = replace(same_source, candidate_source_id="source-2")
    view._render_daily_investment_journey(changed_source)
    assert view.daily_candidate_selector.currentData() is None
    assert not view.daily_candidate_button.isEnabled()
    assert not view.navigate_to_drilldown_target("stock_research")
    assert contexts == []

    single_candidate = replace(
        changed_source,
        candidate_symbols=("2330",),
        candidate_count=1,
        candidate_identity=("row-2330",),
        candidate_source_id="source-3",
    )
    view._render_daily_investment_journey(single_candidate)
    assert view.daily_candidate_selector.currentData() == "2330"
    assert view.daily_candidate_button.isEnabled()
    view.close()


@pytest.mark.parametrize(
    ("changed_field", "changed_value"),
    (
        ("decision_date", "2026-10-17"),
        ("candidate_data_date", "2026-10-14"),
        ("candidate_source_snapshot_id", "snapshot-2"),
        ("candidate_identity", ("row-2330", "row-2603-revised")),
    ),
)
def test_refresh_clears_selection_when_source_or_date_identity_changes(
    changed_field: str,
    changed_value: object,
) -> None:
    application = _app()
    daily = _daily(("2330", "2603"))
    view, contexts = _view(daily)
    view.show()
    application.processEvents()
    view.daily_candidate_selector.setCurrentIndex(
        view.daily_candidate_selector.findData("2603")
    )

    refreshed = replace(daily, **{changed_field: changed_value})
    view._render_daily_investment_journey(refreshed)

    assert view.daily_candidate_selector.currentData() is None
    assert not view.daily_candidate_button.isEnabled()
    view.daily_candidate_button.click()
    assert not view.navigate_to_drilldown_target("stock_research")
    assert contexts == []
    view.close()


def test_snapshot_refresh_clears_old_selection_and_rebinds_only_after_reselection() -> None:
    application = _app()
    daily = _daily(("2330", "2603"))
    view, contexts = _view(daily)
    view.show()
    application.processEvents()
    view.daily_candidate_selector.setCurrentIndex(
        view.daily_candidate_selector.findData("2603")
    )

    refreshed = replace(daily, candidate_source_snapshot_id="snapshot-2")
    view._render_daily_investment_journey(refreshed)

    assert view.daily_candidate_selector.currentData() is None
    assert not view.daily_candidate_button.isEnabled()
    view.daily_candidate_button.click()
    assert not view.navigate_to_drilldown_target("stock_research")
    assert contexts == []

    view.daily_candidate_selector.setCurrentIndex(
        view.daily_candidate_selector.findData("2603")
    )
    view.daily_candidate_button.click()
    assert len(contexts) == 1
    assert contexts[0].stock_code == "2603"
    assert contexts[0].result_id == "result-1"
    assert contexts[0].source_snapshot_id == "snapshot-2"
    view.close()


def test_empty_and_failed_candidates_clear_options_and_disable_opening() -> None:
    application = _app()
    daily = _daily(("2330", "2603"))
    view, _contexts = _view(daily)
    view.show()
    application.processEvents()
    view.daily_candidate_selector.setCurrentIndex(
        view.daily_candidate_selector.findData("2603")
    )

    view._render_daily_investment_journey(
        replace(daily, candidate_symbols=(), candidate_count=0, candidate_identity=())
    )
    assert view.daily_candidate_selector.count() == 1
    assert view.daily_candidate_selector.currentData() is None
    assert not view.daily_candidate_button.isEnabled()

    view._render_daily_investment_journey(replace(daily, candidate_status="read_failure"))
    assert view.daily_candidate_selector.count() == 1
    assert view.daily_candidate_selector.currentData() is None
    assert view.daily_candidate_button.text() == "候選來源讀取失敗"
    assert not view.daily_candidate_button.isEnabled()
    view.close()


def test_single_candidate_remains_preselected_and_opens_from_candidate_button() -> None:
    application = _app()
    view, contexts = _view(_daily(("2330",)))
    view.show()
    application.processEvents()

    assert view.daily_candidate_selector.currentData() == "2330"
    assert view.daily_candidate_button.isEnabled()
    view.daily_candidate_button.click()
    assert len(contexts) == 1
    assert contexts[0].stock_code == "2330"
    assert contexts[0].decision_date == "2026-10-16"
    assert contexts[0].data_date == "2026-10-15"
    view.close()


def test_candidate_controls_are_visible_without_expanding_technical_workbench() -> None:
    application = _app()
    view, _contexts = _view(_daily(("2330", "2603")))
    view.resize(1084, 730)
    view.show()
    application.processEvents()
    assert view.daily_candidate_selector.isVisible()
    assert view.daily_candidate_button.isVisible()
    assert not view.position_health_table.isVisible()
    view.close()


def test_stale_source_can_open_only_its_explicit_saved_result() -> None:
    _app()
    daily = _daily(("2330", "2603"), status="stale")
    view, contexts = _view(daily)
    opened = []
    view.navigate_to_saved_recommendation_callback = opened.append
    view._sync_daily_candidate_open_controls()
    assert not view.daily_candidate_button.isEnabled()
    assert view.home_candidate_selector_row.isHidden()
    assert not view.daily_saved_result_button.isHidden()
    assert view.daily_candidate_selector.count() == 1
    assert view.daily_saved_result_button.isEnabled()
    assert "上次保存" in view.daily_saved_result_button.text()
    view.daily_saved_result_button.click()
    assert opened == ["result-1"] and contexts == []
    view.begin_shutdown()
    assert not view._open_daily_saved_result()
    assert opened == ["result-1"]
    view.close()


@pytest.mark.parametrize("status", ["future_blocked", "read_failure", "missing", "degraded"])
def test_unknown_or_future_candidate_does_not_offer_saved_source_fallback(status) -> None:
    _app()
    view, _contexts = _view(_daily(("2330",), status=status))
    opened = []
    view.navigate_to_saved_recommendation_callback = opened.append
    view._sync_daily_candidate_open_controls()
    assert not view.daily_saved_result_button.isEnabled()
    # missing／degraded 的 DTO 仍可能提供研究股票，保持原入口資格。
    if status in {"future_blocked", "read_failure"}:
        assert view.home_candidate_selector_row.isHidden()
    else:
        assert not view.home_candidate_selector_row.isHidden()
    assert view.daily_saved_result_button.isHidden()
    assert not view._open_daily_saved_result()
    assert opened == []
    view.close()


def test_missing_candidate_controls_return_after_verified_refresh_without_implicit_selection() -> None:
    application = _app()
    view, contexts = _view(_daily((), status="missing"))
    view.show()
    application.processEvents()
    try:
        assert view.home_candidate_selector_row.isHidden()
        assert view.daily_saved_result_button.isHidden()
        view._render_daily_investment_journey(_daily(("2330", "2603")))
        application.processEvents()
        assert view.daily_candidate_selector.isVisible()
        assert view.daily_candidate_selector.currentData() is None
        assert not view.daily_candidate_button.isEnabled()
        assert contexts == []
        view.daily_candidate_selector.setCurrentIndex(
            view.daily_candidate_selector.findData("2603")
        )
        view.daily_candidate_button.click()
        assert len(contexts) == 1 and contexts[0].stock_code == "2603"
    finally:
        view.close()
