from __future__ import annotations

from app_module.batch_backtest_service import BatchBacktestResultDTO, StockBacktestResult
from ui_qt.views.backtest.presenter import format_batch_backtest_completion


def _result(*rows: StockBacktestResult) -> BatchBacktestResultDTO:
    return BatchBacktestResultDTO(
        batch_id="batch-test", batch_name="test", stock_results=list(rows),
        overall_stats={}, created_at="2026-10-16T00:00:00",
    )


def test_completion_message_counts_saved_runs_and_exposes_save_failure():
    message = format_batch_backtest_completion(_result(
        StockBacktestResult(stock_code="2317", run_id="legacy-2317", success=True),
        StockBacktestResult(
            stock_code="2330", run_id=None, success=True,
            error_reason="保存未完成：ValueError: 保存指標契約拒收",
        ),
    ))

    assert "共回測 2 檔" in message
    assert "已保存 1 檔" in message
    assert "1 檔保存未完成" in message
    assert "沒有 RunID 的列不能重開" in message


def test_completion_message_does_not_claim_unrequested_saves():
    message = format_batch_backtest_completion(_result(
        StockBacktestResult(stock_code="2330", run_id=None, success=True),
    ))

    assert "已保存 0 檔" in message
    assert "已保存的結果可在" not in message
