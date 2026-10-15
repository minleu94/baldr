"""已版本化獲利因子的唯讀呈現契約。"""

from __future__ import annotations

import pytest

from app_module.dtos import BacktestReportDTO, ValidationStatus
from ui_qt.views.backtest.presenter import format_backtest_summary


_SEMANTICS = "closed-pair-net-pnl-ratio.v1"


def _report(details: dict[str, object]) -> BacktestReportDTO:
    completed_pairs = 0 if details.get("profit_factor_status") == "no_closed_pairs" else 1
    return BacktestReportDTO(
        total_return=0.1,
        annual_return=0.2,
        sharpe_ratio=1.5,
        max_drawdown=0.05,
        win_rate=0.6,
        total_trades=completed_pairs,
        expectancy=0.02,
        details={"start_date": "2026-01-02", "end_date": "2026-01-05", **details},
        validation_status=ValidationStatus.PASS,
    )


@pytest.mark.parametrize(
    ("status", "value", "expected"),
    [
        ("observed", 1.236, "獲利因子: 1.24（無量綱）"),
        ("observed", 0.0, "獲利因子: 0.00（無量綱）"),
        ("no_closed_pairs", None, "獲利因子：未提供（無已完成配對）"),
        ("unbounded_no_gross_loss", None, "獲利因子：未提供（無虧損，沒有有限比率）"),
        ("undefined_zero_over_zero", None, "獲利因子：未提供（總獲利與虧損皆為零）"),
        ("unavailable_nonfinite", None, "獲利因子：未提供（非有限指標）"),
    ],
)
def test_versioned_profit_factor_states_are_presented_without_recalculation(status, value, expected):
    summary = format_backtest_summary(
        _report(
            {
                "profit_factor_semantics": _SEMANTICS,
                "profit_factor_status": status,
                "profit_factor": value,
            }
        )
    )

    assert expected in summary


@pytest.mark.parametrize(
    "details",
    [
        {"profit_factor": 2.5},
        {"profit_factor": 2.5, "profit_factor_status": "observed"},
        {
            "profit_factor": 2.5,
            "profit_factor_semantics": "future-or-unknown.v2",
            "profit_factor_status": "observed",
        },
        {
            "profit_factor": 2.5,
            "profit_factor_semantics": _SEMANTICS,
            "profit_factor_status": "future_status",
        },
    ],
)
def test_legacy_or_unknown_profit_factor_is_not_claimed(details):
    summary = format_backtest_summary(_report(details))

    assert "未驗證（舊保存值或" in summary
    assert "獲利因子: 2.50" not in summary


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), -0.1, True])
def test_observed_status_rejects_missing_nonfinite_negative_or_boolean_values(value):
    summary = format_backtest_summary(
        _report(
            {
                "profit_factor_semantics": _SEMANTICS,
                "profit_factor_status": "observed",
                "profit_factor": value,
            }
        )
    )

    assert "獲利因子：未提供（觀測值無效）" in summary
    assert "獲利因子: 0.00" not in summary


def test_other_detail_metrics_keep_their_existing_display():
    summary = format_backtest_summary(
        _report(
            {
                "profit_factor_semantics": _SEMANTICS,
                "profit_factor_status": "observed",
                "profit_factor": 1.5,
                "avg_win": 10.25,
                "avg_loss": -4.5,
                "largest_win": 20.0,
                "largest_loss": -8.0,
                "final_equity": 1234.5,
            }
        )
    )

    assert "獲利因子: 1.50（無量綱）" in summary
    assert "平均獲利: $10.25" in summary
    assert "平均虧損: $-4.50" in summary
    assert "最大獲利: $20.00" in summary
    assert "最大虧損: $-8.00" in summary
    assert "最終權益: $1,234.50" in summary


def test_none_in_other_optional_details_is_shown_as_unavailable():
    summary = format_backtest_summary(
        _report(
            {
                "profit_factor_semantics": _SEMANTICS,
                "profit_factor_status": "no_closed_pairs",
                "profit_factor": None,
                "avg_win": None,
                "avg_loss": None,
                "largest_win": None,
                "largest_loss": None,
                "final_equity": None,
            }
        )
    )

    assert "獲利因子：未提供（無已完成配對）" in summary
    assert "平均獲利: 未提供" in summary
    assert "平均虧損: 未提供" in summary
    assert "最大獲利: 未提供" in summary
    assert "最大虧損: 未提供" in summary
    assert "最終權益: 未提供" in summary
