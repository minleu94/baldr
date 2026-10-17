"""零完成交易對不得被呈現為零成交，缺少觀測也不得補零。"""
from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import pandas as pd
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtWidgets import QApplication, QDialog, QListWidgetItem, QMessageBox

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


def test_failed_report_cannot_save_export_promote_or_reuse_previous_chart(view):
    view.current_run_params = {"stock_code": "2317", "strategy_id": "baseline_score_threshold"}
    view.research_run_service = MagicMock()
    old_chart = MagicMock()
    view.result_panel._chart_widgets["equity_chart"] = old_chart
    view.result_panel._pending_chart_plots["equity_chart"] = (("stale-result",), {})
    view._on_backtest_finished(_report({"error": "生成信號失敗：原OHLCV矛盾"}))
    assert "回測未完成" in view.summary_text.toPlainText()
    assert "總交易次數: 0" not in view.summary_text.toPlainText()
    assert not view.result_panel.save_current_result_button.isEnabled()
    assert not view.promote_btn.isEnabled()
    assert view.result_panel._pending_chart_plots == {}
    old_chart.hide.assert_called_once()
    with pytest.raises(ValueError, match="回測未完成"):
        view._ensure_current_single_backtest_is_saveable()
    view.research_run_service.save_run.assert_not_called()


def test_passed_sop_does_not_override_explicit_research_promotion_blocker(view):
    report = _report({"can_promote": False, "promotion_blocker": "研究PIT與來源尚未接受"})
    report.validation_status = ValidationStatus.PASS
    view.current_run_id = "saved-research"
    view.promotion_service = MagicMock()
    view._on_backtest_finished(report)
    assert not view.promote_btn.isEnabled()
    assert "研究PIT與來源尚未接受" in view.promote_btn.toolTip()


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
    assert all(view.current_run_params[key] is None for key in ('capital', 'fee_bps', 'slippage_bps'))


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


def test_windowed_result_can_save_from_visible_summary_and_history_stays_read_only(
    view, monkeypatch
):
    view.resize(900, 768)
    view.show()
    QApplication.processEvents()
    view.current_run_params = {"stock_code": "2330", "strategy_id": "stable_conservative_v1"}
    view._on_backtest_finished(_report({"execution_summary": {"trade_count": 0}}))
    QApplication.processEvents()

    button = view.result_panel.save_current_result_button
    assert not view.config_scroll.isVisible()
    assert button.isVisible() and button.isEnabled()
    assert "尚未保存" in view.result_panel.save_current_result_status.text()

    saved = []
    monkeypatch.setattr(QDialog, "exec", lambda _dialog: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: None)
    monkeypatch.setattr(view, "_save_single_backtest_to_research_registry",
                        lambda name, notes: saved.append((name, notes)) or "exact-run-2330")
    monkeypatch.setattr(view, "_on_research_run_saved", lambda _run_id: None)
    button.click()

    assert len(saved) == 1 and saved[0][0].startswith("2330_stable_conservative_v1_")
    assert not button.isEnabled() and not view.save_result_btn.isEnabled()
    assert "exact-run-2330" in view.result_panel.save_current_result_status.text()

    item = QListWidgetItem("歷史結果")
    item.setData(Qt.ItemDataRole.UserRole, "old-run")
    view._load_history_run(item, run_data={"run_name": "歷史結果", "stock_code": "2330"})
    assert not button.isEnabled()
    assert "old-run" in view.result_panel.save_current_result_status.text()


def test_saved_run_is_not_reported_as_failed_when_history_refresh_breaks(view, monkeypatch):
    view.current_run_params = {"stock_code": "2330", "strategy_id": "stable_conservative_v1"}
    view._on_backtest_finished(_report({}))
    warnings = []
    critical = []
    monkeypatch.setattr(QDialog, "exec", lambda _dialog: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: critical.append(args))
    monkeypatch.setattr(view, "_save_single_backtest_to_research_registry",
                        lambda _name, _notes: "committed-run")
    monkeypatch.setattr(view, "_on_research_run_saved",
                        lambda _run_id: (_ for _ in ()).throw(RuntimeError("refresh failed")))

    view.result_panel.save_current_result_button.click()

    assert not critical and len(warnings) == 1
    assert "committed-run" in view.result_panel.save_current_result_status.text()
    assert not view.result_panel.save_current_result_button.isEnabled()


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


def test_legacy_saved_detail_keeps_missing_metrics_and_six_pairs_visible(view):
    payload = {
        'run_name': '舊回測', 'stock_code': '2330', 'strategy_id': 'stable_conservative_v1',
        'start_date': '2025-10-15', 'end_date': '2026-09-22',
        'total_return': None, 'annual_return': None, 'sharpe_ratio': None,
        'max_drawdown': None, 'win_rate': None, 'total_trades': 6,
        'trade_list_path': '已遺失的原明細.csv',
    }
    before = deepcopy(payload)
    view.run_repository = SimpleNamespace(load_run_data=lambda run_id: payload if run_id == 'old-six' else None)
    view.chart_data_service = None

    view._load_run_and_switch_tab('old-six')

    text = view.summary_text.toPlainText()
    assert '總交易次數: 6（已完成進出場配對）' in text
    assert '交易明細列數: 未提供' in text
    assert '勿把空表視為零交易' in text
    assert '總報酬率: 未提供' in text and '勝率: 未提供' in text
    assert view.trades_table.model() is None
    assert payload == before
    assert all(view.current_run_params[key] is None for key in ('capital', 'fee_bps', 'slippage_bps'))


def test_legacy_saved_detail_preserves_real_zero_and_matching_detail(view):
    payload = {
        'run_name': '真零配對', 'stock_code': '2317', 'strategy_id': 'stable_conservative_v1',
        'total_return': 0.0, 'annual_return': 0.0, 'sharpe_ratio': 0.0,
        'max_drawdown': 0.0, 'win_rate': 0.0, 'total_trades': 0,
        'capital': 2000000, 'fee_bps': 14.25, 'slippage_bps': 5.0,
        'trade_list': pd.DataFrame(),
    }
    view.run_repository = SimpleNamespace(load_run_data=lambda _run_id: payload)
    view.chart_data_service = None

    view._load_run_and_switch_tab('real-zero')

    text = view.summary_text.toPlainText()
    assert '總交易次數: 0（已完成進出場配對）' in text
    assert '交易明細列數: 0' in text
    assert '總報酬率: 0.00%' in text
    assert '勿把空表視為零交易' not in text
    assert view.current_run_params['capital'] == 2000000
    assert view.current_run_params['fee_bps'] == 14.25
    assert view.current_run_params['slippage_bps'] == 5.0


def test_legacy_saved_compare_does_not_crash_or_invent_missing_metrics(view):
    view.history_list.clear()
    for run_id in ('old-left', 'old-right'):
        item = QListWidgetItem(run_id)
        item.setData(Qt.ItemDataRole.UserRole, run_id)
        view.history_list.addItem(item)
        item.setSelected(True)

    def load_run(run_id):
        return SimpleNamespace(
            run_name=run_id, stock_code='2330', strategy_id=run_id,
            total_return=None, annual_return=None, sharpe_ratio=None,
            max_drawdown=None, win_rate=None, total_trades=None, expectancy=None,
        )

    view.run_repository = SimpleNamespace(load_run=load_run)
    view._compare_runs()

    assert view.compare_table.model() is not None
    assert view.compare_table.model().rowCount() == 2
    assert view.compare_runs_data[0]['run_id'] == 'old-left'
    assert view.compare_table.model().data(view.compare_table.model().index(0, 3)) == '未知'
    assert view.compare_table.model().data(view.compare_table.model().index(0, 8)) == '未知'
