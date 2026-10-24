from __future__ import annotations

from types import SimpleNamespace

import pytest

from ui_qt.views.backtest_view import BacktestView


class _TextCapture:
    def __init__(self) -> None:
        self.text = ""

    def setPlainText(self, text: str) -> None:
        self.text = text


@pytest.mark.parametrize(
    ("sample_count", "expected"),
    [(0, "未知"), (1, "0.00%")],
)
def test_batch_stats_show_unknown_without_samples_and_keep_observed_zero(
    sample_count: int,
    expected: str,
) -> None:
    stats = {
        "total_stocks": 1,
        "successful_stocks": 1,
        "failed_stocks": 0,
        "no_trade_stocks": 0,
        "profitable_stocks": 0,
        "coverage_bp": 10_000,
        "profitable_rate_bp": 0,
        "cagr_median": 0.0,
        "mdd_median": 0.0,
        "cagr_sample_count": sample_count,
        "mdd_sample_count": sample_count,
    }
    batch_result = SimpleNamespace(overall_stats=stats, stock_results=[])
    view = SimpleNamespace(batch_stats_text=_TextCapture())

    BacktestView._update_batch_stats(view, batch_result)

    cagr_line = next(
        line for line in view.batch_stats_text.text.splitlines() if line.startswith("CAGR 中位數")
    )
    assert cagr_line.endswith(expected)


def test_batch_stats_show_unknown_mdd_when_no_mdd_samples() -> None:
    stats = {
        "total_stocks": 1,
        "successful_stocks": 1,
        "failed_stocks": 0,
        "no_trade_stocks": 0,
        "profitable_stocks": 0,
        "coverage_bp": 10_000,
        "profitable_rate_bp": 0,
        "cagr_median": 0.0,
        "mdd_median": 0.0,
        "cagr_sample_count": 1,
        "mdd_sample_count": 0,
    }
    batch_result = SimpleNamespace(overall_stats=stats, stock_results=[])
    view = SimpleNamespace(batch_stats_text=_TextCapture())

    BacktestView._update_batch_stats(view, batch_result)

    mdd_line = next(
        line for line in view.batch_stats_text.text.splitlines() if line.startswith("MDD 中位數")
    )
    assert mdd_line.endswith("未知")
