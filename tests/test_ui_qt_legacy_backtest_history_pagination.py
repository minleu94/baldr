"""Legacy 回測歷史與圖表選單的唯讀游標瀏覽。"""

from unittest.mock import MagicMock
from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ui_qt.views.backtest_view import BacktestView


class FakeRunRepository:
    def __init__(self, runs):
        self.runs = sorted(
            runs,
            key=lambda run: (str(run.get("created_at") or ""), str(run.get("run_id") or "")),
            reverse=True,
        )
        self.calls = []
        self.error = None

    def list_runs(self, *, limit=100, cursor=None):
        self.calls.append((limit, cursor))
        if self.error:
            raise self.error
        remaining = self.runs
        if cursor is not None:
            remaining = [
                run for run in remaining
                if (str(run.get("created_at") or ""), str(run.get("run_id") or "")) < cursor
            ]
        return remaining[:limit]

    def load_run(self, run_id):
        run = next((item for item in self.runs if item["run_id"] == run_id), None)
        if run is None:
            return None
        return SimpleNamespace(run_name=run["run_name"], stock_code=run["stock_code"])


def _runs(count):
    return [
        {
            "run_id": f"run-{index:03d}",
            "run_name": f"回測 {index}",
            "stock_code": "2330",
            "strategy_id": "baseline",
            # 每兩筆同時間戳核對 run_id tie-break；最後一筆缺時間核對 NULL 游標。
            "created_at": None if index == count - 1 else f"stamp-{count - index // 2:03d}",
        }
        for index in range(count)
    ]


@pytest.fixture
def view(test_config, monkeypatch):
    app = QApplication.instance() or QApplication([])
    widget = BacktestView(MagicMock(), config=test_config, batch_backtest_service=MagicMock())
    monkeypatch.setattr(widget, "_update_all_charts", MagicMock())
    monkeypatch.setattr(widget, "_clear_saved_charts", MagicMock())
    yield widget
    widget.close()
    widget.deleteLater()
    app.processEvents()


def _item_ids(widget):
    return [
        widget.history_list.item(index).data(Qt.ItemDataRole.UserRole)
        for index in range(widget.history_list.count())
    ]


def test_legacy_history_pages_cover_all_runs_and_clear_selection(view):
    repository = FakeRunRepository(_runs(111))
    view.run_repository = repository

    view._refresh_history()
    first_ids = _item_ids(view)
    expected_ids = [run["run_id"] for run in repository.runs]
    assert len(first_ids) == 100
    assert first_ids == expected_ids[:100]
    assert view.history_scope_label.text() == "第 1 頁｜本頁 100 筆｜尚有較舊結果"
    assert repository.calls[-1] == (101, None)

    view.history_list.item(0).setSelected(True)
    view._history_next_page()
    assert _item_ids(view) == expected_ids[100:]
    assert view.history_list.selectedItems() == []
    assert "第 2 頁｜本頁 11 筆｜已到最舊結果" == view.history_scope_label.text()
    assert repository.calls[-1][1] == (str(repository.runs[99].get("created_at") or ""), repository.runs[99]["run_id"])

    view._history_previous_page()
    assert _item_ids(view) == first_ids
    assert view.history_previous_btn.isEnabled() is False


def test_history_null_created_at_is_explicit_and_empty_or_error_are_visible(view):
    repository = FakeRunRepository([{
        "run_id": "null-time", "run_name": "舊保存", "stock_code": "2330", "strategy_id": "legacy",
        "created_at": None,
    }])
    view.run_repository = repository
    view._refresh_history()
    assert "保存時間未提供" in view.history_list.item(0).text()
    assert view.history_scope_label.text() == "第 1 頁｜本頁 1 筆｜已到最舊結果"

    repository.runs = []
    view._refresh_history()
    assert view.history_list.count() == 0
    assert view.history_scope_label.text() == "目前沒有保存的 legacy 回測結果"

    repository.error = OSError("history unavailable")
    view._refresh_history()
    assert "歷史頁讀取失敗：OSError" in view.history_scope_label.text()
    assert not view.history_next_btn.isEnabled()


def test_chart_history_appends_bounded_chunks_and_preserves_selected_run(view):
    repository = FakeRunRepository(_runs(111))
    view.run_repository = repository

    view._update_chart_run_combo()
    combo = view.chart_run_combo
    assert combo.count() == 51
    assert combo.itemData(1) == repository.runs[0]["run_id"]
    assert combo.itemData(1, Qt.ItemDataRole.ToolTipRole) == f"run_id: {repository.runs[0]['run_id']}"
    assert view.chart_history_scope_label.text() == "已載入 50 筆｜尚有較舊結果"
    combo.setCurrentIndex(7)
    selected_run_id = combo.currentData()
    chart_loads_before_append = view._update_all_charts.call_count
    view._load_older_chart_runs()

    assert combo.count() == 101
    assert combo.currentData() == selected_run_id
    assert view.chart_history_scope_label.text() == "已載入 100 筆｜尚有較舊結果"
    assert view.load_older_chart_runs_btn.isEnabled()
    assert view._update_all_charts.call_count == chart_loads_before_append
    assert repository.calls == [(51, None), (51, (str(repository.runs[49].get("created_at") or ""), repository.runs[49]["run_id"]))]

    view._load_older_chart_runs()
    assert combo.count() == 112
    assert combo.currentData() == selected_run_id
    assert view.chart_history_scope_label.text() == "已載入 111 筆｜已載入全部可用結果"
    assert not view.load_older_chart_runs_btn.isEnabled()


def test_chart_empty_and_error_states_are_visible(view):
    repository = FakeRunRepository([])
    view.run_repository = repository
    view._clear_saved_charts = MagicMock()
    view._update_chart_run_combo()
    assert view.chart_run_combo.count() == 1
    assert view.chart_history_scope_label.text() == "目前沒有保存的 legacy 回測結果"
    assert not view.load_older_chart_runs_btn.isEnabled()
    view._clear_saved_charts.assert_not_called()

    repository.error = OSError("chart history unavailable")
    view._update_chart_run_combo()
    assert "圖表歷史讀取失敗：OSError" in view.chart_history_scope_label.text()
    assert view.load_older_chart_runs_btn.isEnabled()
    assert view.load_older_chart_runs_btn.text() == "重試載入"
    view.load_older_chart_runs_btn.click()
    assert "圖表歷史讀取失敗：OSError" in view.chart_history_scope_label.text()


def test_chart_refresh_pins_verified_selected_run_and_avoids_duplicate_when_page_reaches_it(view):
    repository = FakeRunRepository(_runs(111))
    view.run_repository = repository
    view._update_chart_run_combo()
    view._load_older_chart_runs()
    view._load_older_chart_runs()
    combo = view.chart_run_combo
    combo.setCurrentIndex(combo.count() - 1)
    selected_run_id = combo.currentData()
    assert selected_run_id
    assert view.chart_current_source_label.text() == f"目前圖表來源 run ID：{selected_run_id}"
    chart_loads_before_refresh = view._update_all_charts.call_count

    view._update_chart_run_combo()

    assert combo.currentData() == selected_run_id
    assert combo.findData(selected_run_id) == combo.count() - 1
    assert view.chart_current_source_label.text() == f"目前圖表來源 run ID：{selected_run_id}"
    assert view._update_all_charts.call_count == chart_loads_before_refresh

    view._load_older_chart_runs()
    view._load_older_chart_runs()
    assert combo.currentData() == selected_run_id
    assert sum(combo.itemData(index) == selected_run_id for index in range(combo.count())) == 1
    assert view.chart_history_scope_label.text() == "已載入 111 筆｜已載入全部可用結果"


def test_chart_refresh_clears_selection_and_plots_when_selected_run_was_deleted(view):
    repository = FakeRunRepository(_runs(111))
    view.run_repository = repository
    view._update_chart_run_combo()
    view._load_older_chart_runs()
    view._load_older_chart_runs()
    combo = view.chart_run_combo
    combo.setCurrentIndex(combo.count() - 1)
    deleted_run_id = combo.currentData()
    assert deleted_run_id
    chart_loads_before_refresh = view._update_all_charts.call_count

    repository.runs = [run for run in repository.runs if run["run_id"] != deleted_run_id]
    view._update_chart_run_combo()

    assert combo.currentData() is None
    assert view.chart_current_source_label.text() == "目前圖表來源：未選擇"
    view._clear_saved_charts.assert_called_once_with(
        "目前圖表來源已不存在或無法核對；請重新選擇保存結果。"
    )
    assert view._update_all_charts.call_count == chart_loads_before_refresh
