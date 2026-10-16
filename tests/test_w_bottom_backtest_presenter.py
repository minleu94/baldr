from app_module.dtos import BacktestReportDTO, ValidationStatus
from ui_qt.views.backtest.presenter import format_backtest_summary


_W_BOTTOM_SCHEMA = "baldr-w-bottom-basic-diagnostics.v1"


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


def _w_bottom_diagnostics() -> dict:
    return {
        "schema": _W_BOTTOM_SCHEMA,
        "strategy_id": "baldr_w_bottom_basic_v1",
        "strategy_version": "1.0.0",
        "total_sessions": 80,
        "ready_sessions": 42,
        "unavailable_sessions": 38,
        "entry_signal_sessions": 3,
        "exit_condition_sessions": 2,
        "max_wait_sessions": 10,
        "state_basis": "order_intent_episode_not_assumed_fills",
    }


def test_w_bottom_diagnostics_render_intents_without_score_or_fill_claims() -> None:
    summary = format_backtest_summary(
        _report(
            {
                "score_diagnostics": {
                    "max_score": 50,
                    "min_score": 50,
                    "avg_score": 50,
                    "threshold_mode": "fixed",
                    "buy_score": 50,
                    "sell_score": 50,
                },
                "rule_diagnostics": _w_bottom_diagnostics(),
            }
        )
    )

    assert "--- W 底規則診斷 ---" in summary
    assert "總觀測列數: 80 列" in summary
    assert "規則可判讀列數: 42 列" in summary
    assert "不可判讀列數（含暖機、缺件與重啟）: 38 列" in summary
    assert "進場意圖列數: 3 列" in summary
    assert "出場意圖列數: 2 列" in summary
    assert "頸線突破等待上限: 10 列" in summary
    assert "狀態基礎: 訊號意圖；不假設成交。" in summary
    assert "進出場意圖不代表成交，也不代表已完成配對。" in summary
    assert "策略分數診斷" not in summary
    assert "最高得分" not in summary and "買進門檻" not in summary
    assert "布林規則診斷" not in summary
    assert "上軌" not in summary and "進場確認" not in summary
    assert summary.index("W 底規則診斷") < summary.index("Phase 3.5 SOP 驗證")
    assert "總報酬率: 10.00%" in summary


def test_w_bottom_invalid_counts_and_wait_are_not_coerced_to_zero() -> None:
    diagnostics = _w_bottom_diagnostics()
    diagnostics.update(
        {
            "total_sessions": True,
            "ready_sessions": -1,
            "unavailable_sessions": 2.0,
            "entry_signal_sessions": None,
            "max_wait_sessions": 15,
        }
    )

    summary = format_backtest_summary(_report({"rule_diagnostics": diagnostics}))

    assert "總觀測列數: 未提供 列" in summary
    assert "規則可判讀列數: 未提供 列" in summary
    assert "不可判讀列數（含暖機、缺件與重啟）: 未提供 列" in summary
    assert "進場意圖列數: 未提供 列" in summary
    assert "出場意圖列數: 2 列" in summary
    assert "頸線突破等待上限: 未提供 列" in summary
    assert ": 0 列" not in summary


def test_w_bottom_known_schema_with_missing_or_unknown_fields_is_unavailable() -> None:
    diagnostics = _w_bottom_diagnostics()
    diagnostics.pop("ready_sessions")
    diagnostics["unexpected_private_value"] = "不要顯示"

    summary = format_backtest_summary(
        _report(
            {
                "score_diagnostics": {
                    "threshold_mode": "fixed",
                    "buy_score": 50,
                    "sell_score": 50,
                },
                "rule_diagnostics": diagnostics,
            }
        )
    )

    assert "規則診斷不可用（欄位、身份或狀態基礎不符）。" in summary
    assert "總觀測列數: 未提供 列" in summary
    assert "規則可判讀列數: 未提供 列" in summary
    assert "不要顯示" not in summary
    assert "策略分數診斷" not in summary
    assert "買進門檻" not in summary


def test_w_bottom_wrong_identity_and_unknown_schema_are_not_misrepresented() -> None:
    wrong_identity = _w_bottom_diagnostics()
    wrong_identity["strategy_version"] = "1.0.1"
    known_summary = format_backtest_summary(
        _report(
            {
                "score_diagnostics": {"threshold_mode": "fixed", "buy_score": 50},
                "rule_diagnostics": wrong_identity,
            }
        )
    )
    assert "W 底規則診斷" in known_summary
    assert "規則診斷不可用" in known_summary
    assert "策略分數診斷" not in known_summary

    unknown = _w_bottom_diagnostics()
    unknown["schema"] = "baldr-w-bottom-basic-diagnostics.v2"
    unknown_summary = format_backtest_summary(
        _report({"rule_diagnostics": unknown, "score_diagnostics": {}})
    )
    assert "W 底規則診斷" not in unknown_summary


def test_w_bottom_wrong_state_basis_is_unavailable_and_suppresses_scores() -> None:
    diagnostics = _w_bottom_diagnostics()
    diagnostics["state_basis"] = "assumed_fills"

    summary = format_backtest_summary(
        _report(
            {
                "score_diagnostics": {"threshold_mode": "fixed", "buy_score": 50},
                "rule_diagnostics": diagnostics,
            }
        )
    )

    assert "規則診斷不可用" in summary
    assert "規則可判讀列數: 未提供 列" in summary
    assert "策略分數診斷" not in summary


def test_existing_bollinger_diagnostics_remain_compatible() -> None:
    summary = format_backtest_summary(
        _report(
            {
                "score_diagnostics": {
                    "threshold_mode": "fixed",
                    "buy_score": 50,
                    "sell_score": 50,
                },
                "rule_diagnostics": {
                    "schema": "baldr-bollinger-basic-diagnostics.v1",
                    "total_sessions": 10,
                    "ready_sessions": 6,
                    "unavailable_sessions": 4,
                    "entry_signal_sessions": 2,
                    "exit_condition_sessions": 3,
                    "confirmation_sessions": 1,
                    "entry_description": "收盤越過上軌",
                    "exit_description": "收盤低於中軌",
                },
            }
        )
    )

    assert "--- 布林規則診斷 ---" in summary
    assert "總觀測日數: 10 天" in summary
    assert "進場確認日數: 1 天" in summary
    assert "策略分數診斷" not in summary
    assert "W 底規則診斷" not in summary
