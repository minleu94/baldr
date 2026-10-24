"""參數最佳化的已驗證零值與缺值呈現。"""

from decimal import Decimal
from types import SimpleNamespace

import pandas as pd

from ui_qt.views.backtest_view import BacktestView, _optimization_metric_text


def _result(status: str, value: object) -> SimpleNamespace:
    return SimpleNamespace(
        params={},
        metrics={"sharpe_ratio": value, "annual_return": value},
        metric_status={"sharpe_ratio": status, "annual_return": status},
        rank=1,
    )


def test_optimizer_metric_text_keeps_observed_zero_and_hides_unknown() -> None:
    assert _optimization_metric_text(_result("observed", Decimal("0")), "sharpe_ratio") == "0.00"
    assert _optimization_metric_text(_result("observed", Decimal("0")), "annual_return", percent=True) == "0.00%"
    assert _optimization_metric_text(_result("unavailable", Decimal("0")), "annual_return", percent=True).startswith("未提供")
    assert _optimization_metric_text(_result("legacy_unverified", Decimal("0")), "sharpe_ratio").startswith("未知")
    assert _optimization_metric_text(_result("invalid_contract", Decimal("0")), "sharpe_ratio").startswith("未知")
    assert _optimization_metric_text(_result("observed", None), "sharpe_ratio").startswith("未知")


def test_apply_optimizer_params_message_does_not_upgrade_unknown_to_zero(monkeypatch) -> None:
    messages: list[str] = []
    monkeypatch.setattr(
        "ui_qt.views.backtest_view.QMessageBox.information",
        lambda _view, _title, message: messages.append(message),
    )

    class _Table:
        def selectionModel(self):
            return self

        def selectedRows(self):
            return [SimpleNamespace(row=lambda: 0)]

    view = SimpleNamespace(
        current_optimization_results=[_result("unavailable", Decimal("0"))],
        optimization_table=_Table(),
        params_widgets={},
        optimization_param_widgets={},
    )
    BacktestView._apply_optimization_params(view)

    assert len(messages) == 1
    assert "夏普比率: 未提供" in messages[0]
    assert "年化報酬率: 未提供" in messages[0]
    assert "0.00" not in messages[0]


def test_apply_optimizer_params_uses_displayed_rank_after_table_sort(monkeypatch) -> None:
    messages: list[str] = []
    monkeypatch.setattr(
        "ui_qt.views.backtest_view.QMessageBox.information",
        lambda _view, _title, message: messages.append(message),
    )

    class _Table:
        def selectionModel(self):
            return self

        def selectedRows(self):
            return [SimpleNamespace(row=lambda: 0)]

    first = _result("observed", Decimal("1"))
    second = _result("observed", Decimal("2"))
    second.rank = 2
    view = SimpleNamespace(
        current_optimization_results=[first, second],
        optimization_table=_Table(),
        optimization_model=SimpleNamespace(getDataFrame=lambda: pd.DataFrame({"排名": [2, 1]})),
        optimization_param_widgets={},
    )
    BacktestView._apply_optimization_params(view)

    assert len(messages) == 1
    assert "排名 #2" in messages[0]
    assert "夏普比率: 2.00" in messages[0]
