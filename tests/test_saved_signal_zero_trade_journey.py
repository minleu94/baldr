"""真實保存的1/0/0成交仍以各自原訊號對照，不放寬績效門檻。"""
from app_module.saved_strategy_signal_comparison import read_saved_strategy_signal_comparison
from tests.test_saved_strategy_signal_comparison import saved_run


def test_one_and_zero_completed_trade_runs_keep_original_daily_signal_comparison(tmp_path, monkeypatch):
    service, ma, ma_report = saved_run(tmp_path, monkeypatch, "baldr_ma_alignment_basic_v1")
    _, pattern, pattern_report = saved_run(tmp_path, monkeypatch, "baldr_w_bottom_basic_v1")
    _, band, band_report = saved_run(tmp_path, monkeypatch, "baldr_bollinger_basic_v1")
    assert ma_report.total_trades == 1
    assert pattern_report.total_trades == band_report.total_trades == 0
    result = read_saved_strategy_signal_comparison(service, (ma, pattern, band))
    assert result.state == "available", result.reasons
    assert result.rows and len(result.strategies) == 3
    assert not result.performance_evaluable and not result.historical_pit_eligible
