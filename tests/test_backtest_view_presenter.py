from ui_qt.views.backtest.presenter import (
    build_portfolio_promotion_success_message,
    choice_display_text,
    format_backtest_summary,
)
from app_module.dtos import BacktestReportDTO, ValidationStatus


def test_portfolio_promotion_success_message_golden_contract() -> None:
    assert build_portfolio_promotion_success_message("version-001", "run-001") == (
        "推薦回放已升級為策略版本。\n\n"
        "版本 ID: version-001\n"
        "來源 run: run-001\n\n"
        "後續可到推薦分析的 Profile / 策略版本來源查看；"
        "若清單尚未更新，請重新整理或重新開啟推薦分析頁。"
    )


def test_choice_display_text_preserves_known_and_unknown_values() -> None:
    assert choice_display_text("threshold_mode", "fixed") == "固定門檻"
    assert choice_display_text("threshold_mode", "quantile") == "百分位排名"
    assert choice_display_text("quantile_method", "nearest_rank") == "最近名次法"
    assert choice_display_text("unknown", 123) == "123"


def test_format_backtest_summary_preserves_sop_and_metric_order() -> None:
    report = BacktestReportDTO(
        total_return=0.1,
        annual_return=0.2,
        sharpe_ratio=1.5,
        max_drawdown=0.05,
        win_rate=0.6,
        total_trades=3,
        expectancy=0.02,
        details={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        validation_status=ValidationStatus.PASS,
    )

    summary = format_backtest_summary(report)

    assert summary.index("Phase 3.5 SOP 驗證") < summary.index("Secondary 指標")
    assert "回測日期範圍: 2026-01-01 至 2026-01-31" in summary
    assert "總交易次數: 3" in summary
    assert "總報酬率: 10.00%" in summary


def test_summary_zero_pairs_are_explicit_without_changing_trade_count() -> None:
    report = BacktestReportDTO(
        total_return=0, annual_return=0, sharpe_ratio=0, max_drawdown=0,
        win_rate=0, total_trades=0, expectancy=0, details={},
        validation_status=ValidationStatus.FAIL,
    )

    summary = format_backtest_summary(report)

    assert '總交易次數: 0（已完成進出場配對）' in summary
    assert '尚無已完成交易' in summary
    assert report.total_trades == 0 and report.details == {}


def test_failed_report_is_not_presented_as_zero_trade_performance() -> None:
    report = BacktestReportDTO(total_return=0, annual_return=0, sharpe_ratio=0, max_drawdown=0,
        win_rate=0, total_trades=0, expectancy=0, validation_status=ValidationStatus.FAIL,
        details={"error": "原OHLCV矛盾，不可回測"})
    summary = format_backtest_summary(report)
    assert "回測未完成" in summary and "原OHLCV矛盾" in summary
    assert "空明細不代表零交易" in summary
    assert "總報酬率" not in summary and "總交易次數: 0" not in summary
