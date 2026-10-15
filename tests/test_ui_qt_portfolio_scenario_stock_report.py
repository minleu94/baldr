"""原配置情境單股畫面：精確原值、未持有與失敗切換防混帳。"""
from dataclasses import replace
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QGroupBox, QLabel, QTableView

from app_module.portfolio_research_scenario_artifact import encode_scenario_artifact, scenario_artifact_id
from app_module.stock_research_report_dtos import StockResearchReportDTO
from ui_qt.views.portfolio_view import PortfolioView
from ui_qt.views.stock_research_report_view import StockResearchReportView
from test_portfolio_scenario_stock_report_integration import scenario_report
from test_ui_qt_stock_research_report import _app


def _position_text(view):
    page = view._page_layouts['position'].parentWidget()
    values = [label.text() for label in page.findChildren(QLabel) if not label.isHidden()]
    values += [group.title() for group in page.findChildren(QGroupBox) if not group.isHidden()]
    for table in page.findChildren(QTableView):
        if table.isHidden():
            continue
        model = table.model()
        values += [str(model.data(model.index(row, col)))
                   for row in range(model.rowCount()) for col in range(model.columnCount())]
    return '\n'.join(values)


def _loaded(scenario_report, code='2330'):
    service, saved, context, _ = scenario_report
    context = replace(context, stock_code=code)
    report = service.read_report(code, context=context)
    _app()
    view = StockResearchReportView(SimpleNamespace())
    view.context = context
    view._loaded_request_context = context
    view._active_code = code
    view._request_id = 1
    view._render_report(report)
    view._render_report_tab(4)
    return view, saved, report


def test_saved_scenario_stock_view_shows_original_account_and_decimal_values(scenario_report):
    view, saved, report = _loaded(scenario_report)
    try:
        text = _position_text(view)
        projection = report.portfolio_scenario
        assert projection is not None
        for value in ('paper', 'account-a', saved.artifact_id, '1000',
                      str(projection.cash_amount), str(projection.total_value), str(projection.mark_price),
                      projection.account_source_hash, projection.health_state):
            assert value in text
        assert '不是交易指令' in text and '不代表今日帳本' in text
        for target in projection.targets:
            assert target.scenario_kind in text
            if target.target_weight_bp is not None:
                assert str(target.target_weight_bp) in text
    finally:
        view.close()


def test_saved_complete_unheld_stock_displays_known_zero_and_missing_mark(scenario_report):
    view, _, report = _loaded(scenario_report, '2382')
    try:
        text = _position_text(view)
        assert report.portfolio_scenario.quantity == 0
        assert '數量為 0' in text and '未提供' in text
        assert '原 mark_price' in text and '原 snapshot 持有股數' in text
    finally:
        view.close()


@pytest.mark.parametrize('failure', ['error', 'cancel', 'switch'])
def test_scenario_projection_is_removed_on_failure_cancel_or_stock_switch(scenario_report, failure):
    view, saved, _ = _loaded(scenario_report)
    try:
        assert saved.artifact_id in _position_text(view)
        if failure == 'error':
            view._on_report_error(1, '2330', 'source unavailable')
        elif failure == 'cancel':
            view._on_report_cancelled(1, '2330')
        else:
            view._active_code = '2382'
            view._set_loading_state('2382')
        assert view._loaded_report is None or view._loaded_report.portfolio_scenario is None
        assert saved.artifact_id not in _position_text(view)
        view._render_report(StockResearchReportDTO(stock_code='2382'))
        view._render_report_tab(4)
        assert saved.artifact_id not in _position_text(view)
    finally:
        view.close()


def test_unsaved_scenario_preview_cannot_open_a_different_saved_target(scenario_report):
    _, saved, _, _ = scenario_report
    emitted = []
    status = SimpleNamespace(setText=lambda text: emitted.append(text))
    panel = SimpleNamespace(current_comparison=saved.comparison, current_artifact_id='sha256:'+'0'*64,
                            status_label=status)
    owner = SimpleNamespace(portfolio_research_scenario_widget=panel,
                            stockResearchRequested=SimpleNamespace(emit=emitted.append))
    PortfolioView._open_scenario_stock_research(owner, '2330')
    assert len(emitted) == 1 and '請先另存' in emitted[0]
    emitted.clear()
    panel.current_artifact_id = scenario_artifact_id(encode_scenario_artifact(saved.comparison))
    PortfolioView._open_scenario_stock_research(owner, '2330')
    assert len(emitted) == 1 and emitted[0].portfolio_scenario_ref.artifact_id == saved.artifact_id
