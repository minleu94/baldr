import os
import sys
from dataclasses import replace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

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


def _view(daily: WorkbenchDailyEvidence):
    contexts: list[ResearchStockContextDTO] = []
    dashboard = replace(_dashboard_with_replay(), daily_evidence=daily)
    view = UnifiedDecisionWorkbenchView(
        dashboard=dashboard,
        auto_refresh=False,
        navigate_to_stock_research_callback=contexts.append,
    )
    return view, contexts


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
    assert context.source_kind == "scheduled_recommendation"
    assert context.source_workspace == "recommendation"
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
