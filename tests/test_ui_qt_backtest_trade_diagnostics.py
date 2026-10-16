"""零完成交易對不得被呈現為零成交，缺少觀測也不得補零。"""
from copy import deepcopy
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
import pandas as pd
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtWidgets import QApplication, QListWidgetItem

from app_module.dtos import BacktestReportDTO, ValidationStatus
from ui_qt.views.backtest_view import BacktestView


@pytest.fixture
def view(test_config, monkeypatch):
    app = QApplication.instance() or QApplication([])
    widget = BacktestView(MagicMock(), config=test_config, batch_backtest_service=MagicMock())
    monkeypatch.setattr(widget, '_plot_charts_from_report', lambda report: None)
    yield widget
    widget.close()
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def _report(extra):
    details = {
        'start_date': '2026-09-01', 'end_date': '2026-09-23',
        'score_diagnostics': {
            'max_score': Decimal('70'), 'min_score': Decimal('30'), 'avg_score': Decimal('50'),
            'total_days': 17, 'buy_score': Decimal('60'), 'sell_score': Decimal('40'),
            'buy_hit_days': 1, 'sell_hit_days': 0, 'threshold_mode': 'fixed',
        },
        **extra,
    }
    return BacktestReportDTO(
        total_return=Decimal('0.01'), annual_return=Decimal('0.02'), sharpe_ratio=Decimal('0'),
        max_drawdown=Decimal('0'), win_rate=Decimal('0'), total_trades=0, expectancy=Decimal('0'),
        details=details, validation_status=ValidationStatus.FAIL,
    )


@pytest.mark.parametrize('extra,fill,holding', [
    ({'execution_summary': {'trade_count': 1}, 'terminal_position': 5000}, '1', '5000 股'),
    ({'execution_summary': {'trade_count': 1}}, '1', '未提供'),
    ({'terminal_position': 5000}, '未提供', '5000 股'),
])
def test_open_or_observed_fill_does_not_claim_no_trade_or_suggest_lowering_threshold(view, extra, fill, holding):
    report = _report(extra)
    before = deepcopy(report.to_dict())

    view._on_backtest_finished(report)

    text = view.summary_text.toPlainText()
    assert '尚無已完成交易' in text
    assert f'實際成交筆數：{fill}' in text and f'期末持股：{holding}' in text
    assert '無任何交易' not in text and '降低「buy_score」' not in text
    assert '未平倉估值' in text
    assert report.to_dict() == before and report.total_trades == 0
    assert not view.promote_btn.isEnabled()


@pytest.mark.parametrize('extra', [{}, {'execution_summary': None}, {'execution_summary': {'trade_count': True}}])
def test_missing_fill_metadata_is_unknown_and_not_zero(view, extra):
    view._on_backtest_finished(_report(extra))

    text = view.summary_text.toPlainText()
    assert '尚無已完成交易' in text and '實際成交筆數：未提供' in text
    assert '期末持股：未提供' in text
    assert '實際成交筆數：0' not in text and '無任何交易' not in text
    assert '降低「buy_score」' not in text


def test_explicit_zero_fills_keep_existing_research_diagnostic(view):
    view._on_backtest_finished(_report({'execution_summary': {'trade_count': 0}, 'terminal_position': 0}))

    text = view.summary_text.toPlainText()
    assert '尚無已完成交易' in text and '實際成交筆數：0' in text
    assert '期末持股：0 股' in text
    assert '降低「buy_score」' in text and 'OOS / Walk-forward' in text
    assert '無任何交易' not in text


def test_unknown_scores_do_not_become_a_threshold_failure_reason(view):
    report = _report({'execution_summary': {'trade_count': 0}, 'terminal_position': 0})
    report.details['score_diagnostics']['max_score'] = Decimal('NaN')
    view._on_backtest_finished(report)

    text = view.summary_text.toPlainText()
    assert '尚無已完成交易' in text and '實際成交筆數：0' in text
    assert '降低「buy_score」' not in text and '有達到門檻' not in text


@pytest.mark.parametrize('field,value', [
    ('buy_score', None), ('buy_score', Decimal('NaN')),
    ('threshold_mode', None), ('threshold_mode', 'unknown'),
])
def test_missing_or_invalid_threshold_does_not_infer_a_cause(view, field, value):
    report = _report({'execution_summary': {'trade_count': 0}, 'terminal_position': 0})
    report.details['score_diagnostics'][field] = value
    view._on_backtest_finished(report)

    text = view.summary_text.toPlainText()
    assert '尚無已完成交易' in text
    assert '降低「buy_score」' not in text and '未達買進門檻' not in text


def test_missing_holding_or_quantile_observations_do_not_infer_a_cause(view):
    report = _report({'execution_summary': {'trade_count': 0}})
    view._on_backtest_finished(report)
    assert '期末持股：未提供' in view.summary_text.toPlainText()
    assert '降低「buy_score」' not in view.summary_text.toPlainText()

    report.details['terminal_position'] = 0
    report.details['score_diagnostics']['threshold_mode'] = 'quantile'
    view._on_backtest_finished(report)
    assert '降低「buy_quantile_bp」' not in view.summary_text.toPlainText()


def test_history_zero_pairs_are_labelled_without_inferring_fills(view):
    item = QListWidgetItem('保存來源')
    item.setData(Qt.ItemDataRole.UserRole, 'saved-open-run')
    payload = {'run_name': '保存來源', 'stock_code': '2317', 'total_trades': 0}
    before = deepcopy(payload)

    view._load_history_run(item, run_data=payload)

    text = view.summary_text.toPlainText()
    assert '總交易次數: 0（已完成進出場配對）' in text
    assert '尚無已完成交易' in text and '不代表沒有成交' in text
    assert payload == before and view.current_report is None


def test_six_completed_pairs_show_same_run_fills_and_detail_rows(view):
    details = pd.DataFrame({'買進日': [f'2026-09-{day:02d}' for day in range(1, 7)]})
    report = _report({
        'execution_summary': {'trade_count': 12},
        'terminal_position': 0,
        'trade_list': details,
    })
    report.total_trades = 6

    view._on_backtest_finished(report)

    text = view.summary_text.toPlainText()
    assert '完成進出場配對數：6' in text
    assert '實際成交筆數：12' in text
    assert '交易明細列數：6' in text
    assert '期末持股：0 股' in text
    assert '樣本數不足' in text and 'Walk-forward 驗證未執行' in text
    assert '當次完成配對數與交易明細列數不一致' not in text
    assert view.trades_table.model() is not None
    assert view.trades_table.model().rowCount() == 6
    assert not view.promote_btn.isEnabled()


def test_saved_six_pairs_keep_missing_fill_metadata_explicit(view):
    item = QListWidgetItem('六組配對')
    item.setData(Qt.ItemDataRole.UserRole, 'saved-six-pairs')
    payload = {
        'run_name': '六組配對', 'stock_code': '2317', 'total_trades': 6,
        'trade_list': pd.DataFrame({'買進日': [f'2026-09-{day:02d}' for day in range(1, 7)]}),
    }

    view._load_history_run(item, run_data=payload)

    text = view.summary_text.toPlainText()
    assert 'Registry run：saved-six-pairs' in text
    assert '完成進出場配對數：6' in text
    assert '交易明細列數：6' in text
    assert '實際成交筆數：此歷史紀錄未提供' in text
    assert view.trades_table.model() is not None
    assert view.trades_table.model().rowCount() == 6
