from app_module.dtos import BacktestReportDTO, ValidationStatus
from ui_qt.views.backtest.presenter import format_backtest_summary


_SCHEMA = "baldr-bollinger-basic-diagnostics.v1"


def _report(details: dict) -> BacktestReportDTO:
    return BacktestReportDTO(
        total_return=0.1,
        annual_return=0.2,
        sharpe_ratio=1.5,
        max_drawdown=0.05,
        win_rate=0.6,
        total_trades=3,
        expectancy=0.02,
        details=details,
        validation_status=ValidationStatus.PASS,
    )


def test_bollinger_diagnostics_render_without_score_or_trade_claims() -> None:
    report = _report(
        {
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "score_diagnostics": {
                "max_score": 111.0,
                "min_score": 222.0,
                "avg_score": 333.0,
                "threshold_mode": "fixed",
                "buy_score": 444.0,
                "sell_score": 555.0,
                "total_days": 8,
                "buy_hit_days": 2,
                "sell_hit_days": 1,
            },
            "rule_diagnostics": {
                "schema": _SCHEMA,
                "total_sessions": 10,
                "ready_sessions": 6,
                "unavailable_sessions": 4,
                "entry_signal_sessions": 2,
                "exit_condition_sessions": 3,
                "confirmation_sessions": 1,
                "entry_description": "收盤由布林上軌內側穿越至上軌外側",
                "exit_description": "收盤低於布林中軌時發出出場意圖",
            },
        }
    )

    summary = format_backtest_summary(report)

    assert "--- 布林規則診斷 ---" in summary
    assert "總觀測日數: 10 天" in summary
    assert "指標可用日數: 6 天" in summary
    assert "指標不可用日數: 4 天" in summary
    assert "進場訊號日數: 2 天" in summary
    assert "出場條件日數: 3 天" in summary
    assert "進場確認日數: 1 天" in summary
    assert "進場條件: 收盤由布林上軌內側穿越至上軌外側" in summary
    assert "出場條件: 收盤低於布林中軌時發出出場意圖" in summary
    assert "以上日數表示條件或意圖，不代表成交或已完成進出場配對。" in summary
    assert "策略分數診斷" not in summary
    assert "最高得分" not in summary and "最低得分" not in summary
    assert "買進門檻" not in summary and "賣出門檻" not in summary
    assert "111.0" not in summary and "555.0" not in summary
    assert summary.index("布林規則診斷") < summary.index("Phase 3.5 SOP 驗證")
    assert summary.index("Phase 3.5 SOP 驗證") < summary.index("Secondary 指標")
    assert "總報酬率: 10.00%" in summary


def test_missing_or_invalid_bollinger_values_render_as_unprovided() -> None:
    report = _report(
        {
            "rule_diagnostics": {
                "schema": _SCHEMA,
                "ready_sessions": True,
                "unavailable_sessions": -1,
                "entry_signal_sessions": 2.0,
                "exit_condition_sessions": None,
                "entry_description": "  ",
                "exit_description": 123,
            }
        }
    )

    summary = format_backtest_summary(report)

    assert "總觀測日數: 未提供 天" in summary
    assert "指標可用日數: 未提供 天" in summary
    assert "指標不可用日數: 未提供 天" in summary
    assert "進場訊號日數: 未提供 天" in summary
    assert "出場條件日數: 未提供 天" in summary
    assert "進場確認日數: 未提供 天" in summary
    assert "進場條件: 未提供" in summary
    assert "出場條件: 未提供" in summary
    assert ": 0 天" not in summary


def test_unknown_bollinger_schema_is_not_presented_as_a_valid_rule() -> None:
    report = _report(
        {
            "score_diagnostics": {},
            "rule_diagnostics": {
                "schema": "baldr-bollinger-basic-diagnostics.v2",
                "total_sessions": 10,
                "entry_description": "不應被當作已知規則",
            },
        }
    )

    summary = format_backtest_summary(report)

    assert "布林規則診斷" not in summary
    assert "不應被當作已知規則" not in summary
    assert "Phase 3.5 SOP 驗證" in summary
    assert "Secondary 指標" in summary
