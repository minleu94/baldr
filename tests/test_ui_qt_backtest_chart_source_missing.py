"""保存回測圖表切換時，缺少的來源資料不得沿用前一筆曲線。"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication

from ui_qt.views.backtest_view import BacktestView


class ChartSpy:
    def __init__(self):
        self.plots = []
        self.visible = True

    def plot(self, *args):
        self.plots.append(args)

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False


class FakeChartDataService:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def _get(self, method, run_id):
        self.calls.append((method, run_id))
        return self.responses[run_id].get(method)

    def get_equity_series(self, run_id):
        return self._get("equity", run_id)

    def get_benchmark_series(self, start_date, end_date):
        return None

    def get_trade_list(self, run_id):
        return self._get("trade_list", run_id)

    def get_drawdown_series(self, run_id):
        return self._get("drawdown", run_id)

    def get_max_drawdown_info(self, run_id):
        return self._get("max_drawdown", run_id)

    def get_trade_returns(self, run_id):
        return self._get("returns", run_id)

    def get_trade_statistics(self, run_id):
        return self._get("trade_statistics", run_id)

    def get_holding_days(self, run_id):
        return self._get("holding_days", run_id)


@pytest.fixture
def chart_view(test_config, monkeypatch):
    app = QApplication.instance() or QApplication([])
    view = BacktestView(MagicMock(), config=test_config, batch_backtest_service=MagicMock())
    names = ("equity_chart", "drawdown_chart", "return_hist", "holding_hist")
    spies = {name: ChartSpy() for name in names}
    panel = view.result_panel
    panel._charts_available = True
    panel._chart_widgets_initialized = True
    panel._chart_widgets = spies
    monkeypatch.setattr(view, "chart_data_service", None)
    yield view, spies, app
    view.close()
    view.deleteLater()
    app.processEvents()


def _connect_repository(view):
    repository = MagicMock()
    repository.load_run.return_value = SimpleNamespace(
        annual_return=0.12,
        start_date="2026-01-01",
        end_date="2026-01-03",
    )
    view.run_repository = repository


def _set_chart_selection(view, run_ids):
    combo = view.chart_run_combo
    combo.blockSignals(True)
    combo.clear()
    for run_id in run_ids:
        combo.addItem(run_id, run_id)
    combo.blockSignals(False)


def _select_chart_run(view, index):
    combo = view.chart_run_combo
    combo.blockSignals(True)
    combo.setCurrentIndex(index)
    combo.blockSignals(False)
    view._on_chart_run_changed()


def _status_text(view, chart_name):
    return view.result_panel._chart_error_labels[chart_name].text()


def _status_is_visible(view, chart_name):
    return not view.result_panel._chart_error_labels[chart_name].isHidden()


def test_switch_from_a_to_missing_b_clears_all_charts_and_keeps_raw_run_id(chart_view):
    view, spies, _app = chart_view
    _connect_repository(view)
    equity_a = pd.Series([100, 105], index=pd.date_range("2026-01-01", periods=2))
    drawdown_a = pd.Series([0, -0.02], index=equity_a.index)
    service = FakeChartDataService({
        "raw/A:run": {
            "equity": equity_a,
            "trade_list": pd.DataFrame(),
            "drawdown": drawdown_a,
            "max_drawdown": {"max_drawdown": -0.02},
            "returns": [1.5],
            "trade_statistics": {"mean": 1.5},
            "holding_days": [3],
        },
        "raw/B:run": {},
    })
    view.chart_data_service = service
    _set_chart_selection(view, ["raw/A:run", "raw/B:run"])

    _select_chart_run(view, 0)
    assert all(spies[name].plots for name in spies)
    _select_chart_run(view, 1)

    assert service.calls[-4:] == [
        ("equity", "raw/B:run"),
        ("drawdown", "raw/B:run"),
        ("returns", "raw/B:run"),
        ("holding_days", "raw/B:run"),
    ]
    assert view.chart_current_source_label.text() == "目前圖表來源 run ID：raw/B:run"
    assert len(spies["equity_chart"].plots[-1][0]) == 0
    assert len(spies["drawdown_chart"].plots[-1][0]) == 0
    assert spies["return_hist"].plots[-1][0] == []
    assert spies["holding_hist"].plots[-1][0] == []
    assert all(not spies[name].visible for name in spies)
    assert "沒有可用的權益曲線" in _status_text(view, "equity_chart")
    assert "沒有可用的回撤曲線" in _status_text(view, "drawdown_chart")
    assert "沒有可用的交易報酬" in _status_text(view, "return_hist")
    assert "沒有可用的持有天數" in _status_text(view, "holding_hist")
    assert all(_status_is_visible(view, name) for name in spies)


def test_equity_present_but_missing_trades_preserves_valid_curves(chart_view):
    view, spies, _app = chart_view
    _connect_repository(view)
    equity_b = pd.Series([100, 110], index=pd.date_range("2026-02-01", periods=2))
    drawdown_b = pd.Series([0, -0.01], index=equity_b.index)
    service = FakeChartDataService({
        "raw/B:equity-only": {
            "equity": equity_b,
            "trade_list": None,
            "drawdown": drawdown_b,
            "max_drawdown": {"max_drawdown": -0.01},
            "returns": None,
            "trade_statistics": None,
            "holding_days": None,
        },
    })
    view.chart_data_service = service

    view._update_all_charts("raw/B:equity-only")

    assert spies["equity_chart"].plots[-1][0] is equity_b
    assert spies["drawdown_chart"].plots[-1][0] is drawdown_b
    assert spies["equity_chart"].visible
    assert spies["drawdown_chart"].visible
    assert _status_text(view, "equity_chart") == ""
    assert _status_text(view, "drawdown_chart") == ""
    assert not _status_is_visible(view, "equity_chart")
    assert not _status_is_visible(view, "drawdown_chart")
    assert spies["return_hist"].plots[-1][0] == []
    assert spies["holding_hist"].plots[-1][0] == []
    assert not spies["return_hist"].visible
    assert not spies["holding_hist"].visible
    assert "沒有可用的交易報酬" in _status_text(view, "return_hist")
    assert "沒有可用的持有天數" in _status_text(view, "holding_hist")
    assert _status_is_visible(view, "return_hist")
    assert _status_is_visible(view, "holding_hist")
