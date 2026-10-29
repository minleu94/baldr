import os
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication, QLabel
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from app_module.research_run_dtos import ResearchRunMetadataDTO
from ui_qt.views.backtest_view import BacktestView
from ui_qt.views.research_lab.run_registry_compare_widget import (
    RunRegistryCompareWidget,
)


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_basic_pair_original_details_and_source_disclosure_clear_with_selection(qt_app, tmp_path, monkeypatch):
    from tests.test_single_backtest_rule_execution_v2 import executed_v2_case
    from app_module.basic_strategy_saved_pair import BasicStrategySavedPairReader
    from app_module.research_history_lookup import ResearchHistoryLookup, ResearchHistoryReadBudget
    _, registry, stable, _, _, _ = executed_v2_case(tmp_path, monkeypatch, "stable_conservative_v1")
    _, _, momentum, _, _, _ = executed_v2_case(tmp_path, monkeypatch, "momentum_aggressive_v1")
    lookup = ResearchHistoryLookup(registry=registry, read_budget=ResearchHistoryReadBudget(64 * 1024 * 1024, 256 * 1024 * 1024))
    opened = []
    widget = RunRegistryCompareWidget(registry)
    widget.configure_basic_pair(BasicStrategySavedPairReader(registry, lookup), lookup, opened.append, lambda: None)
    widget.refresh_runs()
    for i in range(widget.run_list.count()):
        item = widget.run_list.item(i)
        item.setSelected(item.data(Qt.ItemDataRole.UserRole) in {stable.run_id, momentum.run_id})
    widget.compare_basic_pair_button.click()
    def wait_worker():
        deadline = time.monotonic() + 10
        while widget._basic_pair_worker is not None and time.monotonic() < deadline:
            qt_app.processEvents()
            QTest.qWait(10)
        assert widget._basic_pair_worker is None
    wait_worker()
    result = widget._basic_pair_result
    assert result is not None
    assert widget.basic_pair_metrics.rowCount() == 7
    assert "14.25 bps" in widget.basic_pair_status.text()
    assert "metadata SHA" not in widget.basic_pair_status.text()
    assert widget.basic_pair_sources.is_collapsed()
    for entry in result.entries:
        assert entry.metadata_sha256 in widget.basic_pair_source_text.toPlainText()
    for row in range(7):
        assert widget.basic_pair_metrics.item(row, 1).toolTip().startswith("原保存值：")
    widget.open_basic_stable_button.click()
    wait_worker()
    assert opened[0].entry.run_id == stable.run_id
    widget.run_list.clearSelection()
    assert widget.basic_pair_metrics.rowCount() == 0
    assert widget.basic_pair_sources.isHidden()
    assert not widget.basic_pair_source_text.toPlainText()
    widget.begin_basic_pair_shutdown()
    widget.close()
    qt_app.processEvents()


@pytest.fixture
def qt_app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def _metadata(run_id: str, **overrides) -> ResearchRunMetadataDTO:
    values = {
        "run_id": run_id,
        "run_name": run_id,
        "run_type": "single_backtest",
        "strategy_id": "baseline_score",
        "universe": ["2330", "2317"],
        "start_date": "2026-01-02",
        "end_date": "2026-01-08",
        "data_fingerprint": "sha256:data",
        "capital_cents": 1_000_000_00,
        "fee_bp_x100": 1425,
        "slippage_bp_x100": 500,
        "execution_price": "next_open",
        "sizing_mode": "fixed_amount",
        "normalized_params": {"buy_score": 70, "sell_score": 40},
        "metrics": {"sharpe_ratio": 1.2},
        "regime_breakdown": {"trend": {"trades": 3}},
        "benchmark_results": {"taiex": {"excess_return_bp": 250}},
        "payload_hash": f"sha256:{run_id}",
        "created_at": "2026-06-14T12:00:00",
    }
    values.update(overrides)
    return ResearchRunMetadataDTO(**values)


class FakeResearchRunService:
    def __init__(self):
        self.runs = [
            _metadata("run-a"),
            _metadata("run-b", normalized_params={"buy_score": 80, "sell_score": 40}),
            _metadata("run-c", run_type="recommendation_portfolio", strategy_id="profile-a"),
        ]
        self.data = {
            "run-a": pd.DataFrame(
                {"日期": ["2026-01-02", "2026-01-05"], "portfolio_value": [1000, 1100]}
            ),
            "run-b": pd.DataFrame(
                {"日期": ["2026-01-02", "2026-01-05"], "portfolio_value": [2000, 2100]}
            ),
            "run-c": pd.DataFrame(
                {"日期": ["2026-01-02", "2026-01-05"], "portfolio_value": [1500, 1510]}
            ),
        }
        self.list_runs_calls = 0
        self.list_runs_thread_id = None
        self.list_runs_error = None
        self._list_runs_lock = threading.Lock()

    def list_runs(self, include_archived: bool = False):
        with self._list_runs_lock:
            self.list_runs_calls += 1
        self.list_runs_thread_id = threading.get_ident()
        if self.list_runs_error is not None:
            raise self.list_runs_error
        return self.runs

    def load_run_data(self, run_id: str):
        return SimpleNamespace(
            metadata=next(run for run in self.runs if run.run_id == run_id),
            equity=self.data[run_id],
            trades=pd.DataFrame(),
        )


def test_backtest_view_mounts_registry_compare_subtab(qt_app):
    view = BacktestView(backtest_service=None, config=None)
    view.research_run_service = FakeResearchRunService()
    widget = view.result_panel.add_registry_compare_tab()

    labels = [view.result_tabs.tabText(index) for index in range(view.result_tabs.count())]

    assert "研究 Registry" in labels
    assert widget is view.run_registry_compare_widget
    promotion_note = next(
        label
        for label in view.result_panel.findChildren(QLabel)
        if label.accessibleName() == "研究 Registry 升級限制"
    )
    assert "不會自動升級策略" in promotion_note.text()
    assert "只讀原保存數值" in widget.purpose_banner.text()


def test_basic_pair_return_disappears_when_registry_selection_changes(qt_app):
    from dataclasses import replace

    view = BacktestView(backtest_service=None, config=None)
    service = FakeResearchRunService()
    service.runs[0] = replace(service.runs[0], strategy_id="stable_conservative_v1")
    service.runs[1] = replace(service.runs[1], strategy_id="momentum_aggressive_v1")
    view.research_run_service = service
    widget = view.result_panel.add_registry_compare_tab()
    widget.refresh_runs()
    widget.run_list.item(0).setSelected(True)
    widget.run_list.item(1).setSelected(True)
    widget._basic_pair_selection = widget._basic_pair_fingerprint()
    assert widget._basic_pair_selection is not None

    view.result_panel.return_basic_pair_button.show()
    assert not view.result_panel.return_basic_pair_button.isHidden()
    widget.run_list.item(1).setSelected(False)
    assert widget._basic_pair_selection is None
    assert view.result_panel.return_basic_pair_button.isHidden()


def test_batch_stock_generic_comparison_clears_saved_performance(qt_app):
    from dataclasses import replace

    service = FakeResearchRunService()
    service.runs[0] = replace(
        service.runs[0], run_type="batch_backtest_stock", universe=["2330"]
    )
    service.runs[1] = replace(
        service.runs[1], run_type="fixed_basket_stock", universe=["2330"]
    )
    widget = RunRegistryCompareWidget(service, page_size=10)
    widget.refresh_runs()
    widget.run_list.item(0).setSelected(True)
    widget.run_list.item(1).setSelected(True)

    widget.compare_selected_runs()

    assert "不可直接比較" in widget.comparability_badge.text()
    assert "歷史 PIT" in widget.comparability_badge.text()
    assert widget.metrics_table.model().rowCount() == 0
    assert widget.normalized_equity_table.isHidden()


def test_backtest_view_can_collapse_config_panel_for_registry_compare_space(qt_app):
    view = BacktestView(backtest_service=None, config=None)

    view._set_config_panel_collapsed(True)

    assert view.config_scroll.isHidden() is True
    assert view.config_panel_expand_btn.text() == "展開左側設定"
    assert view.config_panel_expand_btn.isHidden() is False

    view._set_config_panel_collapsed(False)

    assert view.config_scroll.isHidden() is False
    assert view.config_panel_expand_btn.isHidden() is True
    assert view.config_panel_collapse_btn.text() == "收合左側設定"


def test_registry_compare_widget_filters_paginates_and_limits_selection(qt_app):
    widget = RunRegistryCompareWidget(FakeResearchRunService(), page_size=2)

    widget.refresh_runs()
    assert widget.run_list.count() == 2
    assert "第 1 / 2 頁" in widget.page_label.text()

    widget.next_page()
    assert widget.run_list.count() == 1
    assert "第 2 / 2 頁" in widget.page_label.text()

    assert widget.run_type_filter.itemText(1) == "單股回測"
    assert widget.run_type_filter.itemData(1) == "single_backtest"

    widget.run_type_filter.setCurrentText("單股回測")
    widget.refresh_runs()
    assert widget.run_list.count() == 2
    assert all("單股回測" in widget.run_list.item(i).text() for i in range(2))
    assert widget.run_list.minimumHeight() >= 240
    assert widget.run_list.item(0).sizeHint().height() >= 60
    assert "類型：單股回測" in widget.run_list.item(0).text()

    widget.run_list.selectAll()
    assert widget.selected_run_ids() == ["run-a", "run-b"]


def test_registry_compare_selection_persists_across_pages_and_can_be_cleared(qt_app):
    widget = RunRegistryCompareWidget(FakeResearchRunService(), page_size=2)
    widget.refresh_runs()

    widget.run_list.item(0).setSelected(True)
    widget.next_page()
    widget.run_list.item(0).setSelected(True)

    assert widget.selected_run_ids() == ["run-a", "run-c"]
    widget.previous_page()
    assert widget.run_list.item(0).isSelected()
    assert widget.selection_hint_label.text().startswith("已選 2 / 5")

    widget.clear_selection()
    assert widget.selected_run_ids() == []
    assert widget.compare_button.isEnabled() is False
    assert widget.selection_preview_label.isHidden()
    assert widget.selection_preview_label.text() == ""


def test_registry_selection_preview_matches_comparison_aliases_across_pages(qt_app):
    from dataclasses import replace

    service = FakeResearchRunService()
    long_run_name = "run-a-" + "long-name-" * 6
    service.runs[0] = replace(service.runs[0], run_name=long_run_name)
    widget = RunRegistryCompareWidget(service, page_size=1)
    widget.refresh_runs()

    widget.run_list.item(0).setSelected(True)
    widget.next_page()
    widget.run_list.item(0).setSelected(True)

    assert widget.selected_run_ids() == ["run-a", "run-b"]
    preview = widget.selection_preview_label.text()
    assert "A=run-a-long-name-long-name" in preview
    assert long_run_name not in preview
    assert "B=run-b｜單股回測｜baseline_score" in preview
    assert preview.index("A=run-a") < preview.index("B=run-b")
    assert f"A：{long_run_name}｜單股回測｜baseline_score｜run_id：run-a" in widget.selection_preview_label.toolTip()
    assert "B：run-b｜單股回測｜baseline_score｜run_id：run-b" in widget.selection_preview_label.toolTip()

    widget.compare_selected_runs()

    result_summary = widget.selected_runs_label.text()
    assert f"A：{long_run_name}｜單股回測｜baseline_score" in result_summary
    assert "B：run-b｜單股回測｜baseline_score" in result_summary

    widget.next_page()
    widget.run_list.item(0).setSelected(True)
    assert widget.selected_run_ids() == ["run-a", "run-b", "run-c"]
    assert "目前選取 A–E：" in widget.selection_preview_label.text()
    assert "下方仍保留上次比較：A=run-a-long-name-lon…" in widget.selection_preview_label.text()
    assert "C=run-c" in widget.selection_preview_label.text()
    assert "run_id：run-a" in widget.selection_preview_label.accessibleDescription()

    widget.clear_selection()
    assert widget.selected_run_ids() == []
    assert "目前沒有選取的 run。" in widget.selection_preview_label.text()
    assert "下方仍保留上次比較：A=run-a-long-name-lon…" in widget.selection_preview_label.text()


def test_registry_selection_preview_marks_previous_comparison_after_filter_and_refresh(qt_app):
    service = FakeResearchRunService()
    widget = RunRegistryCompareWidget(service, page_size=10)
    widget.refresh_runs()
    for index in range(widget.run_list.count()):
        item = widget.run_list.item(index)
        item.setSelected(item.data(Qt.ItemDataRole.UserRole) in {"run-a", "run-b"})

    widget.compare_selected_runs()
    widget.strategy_filter.setText("profile-a")

    assert widget.selected_run_ids() == []
    assert "目前沒有選取的 run。" in widget.selection_preview_label.text()
    assert "下方仍保留上次比較：A=run-a" in widget.selection_preview_label.text()

    widget.strategy_filter.clear()
    for index in range(widget.run_list.count()):
        item = widget.run_list.item(index)
        item.setSelected(item.data(Qt.ItemDataRole.UserRole) in {"run-a", "run-b"})
    assert widget.selected_run_ids() == ["run-a", "run-b"]
    assert "下方仍保留上次比較：" not in widget.selection_preview_label.text()

    service.runs = [run for run in service.runs if run.run_id != "run-b"]
    widget.refresh_runs()

    assert widget.selected_run_ids() == ["run-a"]
    assert "目前選取 A–E：A=run-a" in widget.selection_preview_label.text()
    assert "下方仍保留上次比較：A=run-a（run-a）；B=run-b（run-b）" in widget.selection_preview_label.text()


def test_registry_load_failure_clears_previous_result_identity(qt_app):
    service = FakeResearchRunService()
    widget = RunRegistryCompareWidget(service, page_size=10)
    widget.refresh_runs()
    for index in range(widget.run_list.count()):
        item = widget.run_list.item(index)
        item.setSelected(item.data(Qt.ItemDataRole.UserRole) in {"run-a", "run-b"})

    widget.compare_selected_runs()
    assert widget.metrics_table.model().rowCount() > 0
    assert "比較代號：" in widget.selected_runs_label.text()

    widget.clear_selection()
    for index in range(widget.run_list.count()):
        item = widget.run_list.item(index)
        item.setSelected(item.data(Qt.ItemDataRole.UserRole) in {"run-a", "run-c"})
    assert "下方仍保留上次比較：" in widget.selection_preview_label.text()

    original_load_run_data = service.load_run_data

    def fail_loading_c(run_id: str):
        if run_id == "run-c":
            raise OSError("run-c unavailable")
        return original_load_run_data(run_id)

    service.load_run_data = fail_loading_c
    widget.compare_selected_runs()

    assert widget.metrics_table.model().rowCount() == 0
    assert widget.params_diff_table.model().rowCount() == 0
    assert widget.selected_runs_label.text() == "研究載入失敗；未產生新的比較結果。"
    assert widget._last_compared_runs == []
    assert widget._run_aliases == {}
    assert "目前選取 A–E：A=run-a" in widget.selection_preview_label.text()
    assert "B=run-c" in widget.selection_preview_label.text()
    assert "下方仍保留上次比較：" not in widget.selection_preview_label.text()


def test_registry_open_button_only_accepts_one_recommendation_run(qt_app):
    opened: list[str] = []

    def record_open(metadata: ResearchRunMetadataDTO) -> None:
        opened.append(metadata.run_id)

    widget = RunRegistryCompareWidget(
        FakeResearchRunService(),
        on_open_recommendation_run=record_open,
        page_size=10,
    )
    widget.refresh_runs()

    assert widget.open_recommendation_button.isEnabled() is False
    widget.run_list.item(0).setSelected(True)
    assert widget.open_recommendation_button.isEnabled() is False

    widget.clear_selection()
    widget.run_list.item(2).setSelected(True)
    assert widget.open_recommendation_button.isEnabled() is True
    widget.open_recommendation_button.click()
    assert opened == ["run-c"]

    widget.run_list.item(0).setSelected(True)
    assert widget.open_recommendation_button.isEnabled() is False
    widget.clear_selection()
    widget.run_type_filter.setCurrentIndex(
        widget.run_type_filter.findData("single_backtest")
    )
    widget.refresh_runs()
    widget.run_list.item(0).setSelected(True)
    assert widget.open_recommendation_button.isEnabled() is False


def test_registry_compare_maps_batch_and_fixed_basket_run_types(qt_app):
    service = FakeResearchRunService()
    service.runs.extend(
        [
            _metadata("run-batch", run_type="batch_backtest_stock"),
            _metadata("run-fixed", run_type="fixed_basket_stock"),
        ]
    )
    widget = RunRegistryCompareWidget(service, page_size=10)
    widget.refresh_runs()

    assert widget.run_type_filter.findData("batch_backtest_stock") >= 0
    assert widget.run_type_filter.findData("fixed_basket_stock") >= 0
    assert "批次股票回測" in widget.run_list.item(3).text()
    assert "固定組合（逐檔）" in widget.run_list.item(4).text()


def test_registry_compare_widget_renders_badge_diff_metrics_and_saved_benchmark(qt_app):
    widget = RunRegistryCompareWidget(FakeResearchRunService(), page_size=10)
    widget.refresh_runs()
    assert widget.comparison_results_container.isHidden()
    assert widget.signal_comparison_section.is_collapsed()
    assert widget.basic_pair_group.is_collapsed()
    widget.run_list.item(0).setSelected(True)
    widget.run_list.item(1).setSelected(True)

    widget.compare_selected_runs()

    assert not widget.comparison_results_container.isHidden()
    assert "保存條件相同（績效資格另核）" in widget.comparability_badge.text()
    assert widget.params_diff_table.model().rowCount() >= 1
    assert widget.metrics_table.model().rowCount() == 2
    assert widget.regime_table.model().rowCount() == 2
    assert widget.benchmark_table.model().rowCount() == 2
    assert widget.normalized_equity_table.model().rowCount() == 4

    assert "買進分數" in widget.params_summary_label.text()
    assert "主要指標對照" in widget.metrics_summary_label.text()
    assert widget.metrics_summary_table.isHidden() is False
    assert widget.metrics_summary_table.horizontalHeaderItem(1).text() == "A"
    assert widget.metrics_summary_table.item(0, 0).text() == "Sharpe 比率"
    assert widget.metrics_summary_table.item(0, 1).text() == "1.2"
    assert "趨勢交易數=3" in widget.regime_summary_label.text()
    assert "相對大盤超額報酬 bp=250" in widget.benchmark_summary_label.text()
    assert "比較代號：" in widget.selected_runs_label.text()
    assert "已產生標準化權益" in widget.normalized_equity_empty_label.text()


def test_registry_compare_replay_does_not_show_generic_performance_comparison(qt_app):
    service = FakeResearchRunService()
    service.runs = [
        _metadata("replay-a", run_type="recommendation_portfolio"),
        _metadata("replay-b", run_type="recommendation_portfolio"),
    ]
    service.data = {
        run.run_id: pd.DataFrame({
            "日期": ["2026-01-02", "2026-01-05"],
            "portfolio_value": [1000, 1100],
        }) for run in service.runs
    }
    widget = RunRegistryCompareWidget(service, page_size=10)
    widget.refresh_runs()
    widget.run_list.selectAll()

    assert widget.compare_button.isEnabled() is False
    assert "固定日曆版本" in widget.selection_hint_label.text()

    widget.compare_selected_runs()

    assert "不可直接比較" in widget.comparability_badge.text()
    assert "比較完整期間" in widget.comparability_badge.text()
    assert widget.params_diff_table.model().rowCount() >= 1
    assert widget.metrics_table.model().rowCount() == 0
    assert widget.metrics_summary_table.isHidden()
    assert widget.normalized_equity_table.model().rowCount() == 0
    assert "績效／權益比較已停止" in widget.normalized_equity_empty_label.text()


def test_registry_compare_widget_discards_stale_run_list_response(qt_app):
    widget = RunRegistryCompareWidget(FakeResearchRunService(), page_size=10)

    stale_request = widget.begin_run_list_request()
    fresh_request = widget.begin_run_list_request()
    widget.apply_run_list_response(stale_request, [_metadata("stale")])
    widget.apply_run_list_response(fresh_request, [_metadata("fresh")])

    assert widget.run_list.count() == 1
    assert "fresh" in widget.run_list.item(0).text()


def test_registry_compare_widget_shows_empty_normalized_equity_message(qt_app):
    service = FakeResearchRunService()
    service.data["run-b"] = pd.DataFrame(
        {"日期": ["2026-02-02"], "portfolio_value": [2100]}
    )
    widget = RunRegistryCompareWidget(service, page_size=10)

    widget.refresh_runs()
    widget.run_list.item(0).setSelected(True)
    widget.run_list.item(1).setSelected(True)
    widget.compare_selected_runs()

    assert "沒有共同日期可標準化比較" in widget.normalized_equity_empty_label.text()


def test_registry_single_stock_cost_or_period_difference_hides_saved_metrics(qt_app):
    from dataclasses import replace

    service = FakeResearchRunService()
    widget = RunRegistryCompareWidget(service, page_size=10)
    widget.refresh_runs()
    widget.run_list.item(0).setSelected(True)
    widget.run_list.item(1).setSelected(True)
    widget.compare_selected_runs()
    assert widget.metrics_summary_table.isHidden() is False

    service.runs[1] = replace(service.runs[1], fee_bp_x100=service.runs[1].fee_bp_x100 + 1)
    widget.compare_selected_runs()
    assert "交易成本模型不同" in widget.comparability_badge.text()
    assert widget.metrics_summary_table.isHidden()
    assert widget.normalized_equity_table.model().rowCount() == 0

    service.runs[1] = replace(service.runs[0], run_id="run-b", end_date="2026-01-09")
    widget.compare_selected_runs()
    assert "日期區間不同" in widget.comparability_badge.text()
    assert widget.metrics_summary_table.isHidden()


def test_registry_compare_widget_refreshes_on_first_show(qt_app):
    widget = RunRegistryCompareWidget(FakeResearchRunService(), page_size=10)
    widget.refresh_runs_async = MagicMock()

    widget.showEvent(None)
    widget.showEvent(None)

    assert widget.refresh_runs_async.call_count == 1


def test_registry_compare_widget_fits_narrow_result_panel_without_horizontal_overflow(
    qt_app,
):
    widget = RunRegistryCompareWidget(FakeResearchRunService(), page_size=10)
    widget.resize(575, 520)
    widget.show()
    _wait_for_run_list(widget, qt_app)
    qt_app.processEvents()

    assert widget.minimumSizeHint().width() <= widget.width()
    for control in (
        widget.run_type_filter,
        widget.strategy_filter,
        widget.tag_filter,
        widget.refresh_button,
        widget.run_list_status_label,
        widget.compare_button,
        widget.open_recommendation_button,
        widget.rule_result_button,
    ):
        assert not control.geometry().isEmpty()
        assert control.geometry().right() <= widget.width()

    widget.close()


def _wait_for_run_list(widget, qt_app, timeout=5):
    deadline = time.monotonic() + timeout
    while (widget._run_list_loading or widget._run_list_workers) and time.monotonic() < deadline:
        qt_app.processEvents()
        QTest.qWait(10)
    qt_app.processEvents()
    assert not widget._run_list_loading
    assert not widget._run_list_workers


def test_registry_filter_changes_use_loaded_snapshot_without_service_reads(qt_app):
    service = FakeResearchRunService()
    widget = RunRegistryCompareWidget(service, page_size=10)

    widget.refresh_runs()
    assert service.list_runs_calls == 1
    assert widget.run_list_status_label.text() == "已載入 3 筆；目前符合 3 筆"

    widget.strategy_filter.setText("baseline_score")
    assert service.list_runs_calls == 1
    assert widget.run_list.count() == 2
    assert widget.run_list_status_label.text() == "已載入 3 筆；目前符合 2 筆"

    widget.tag_filter.setText("no matching tag")
    assert service.list_runs_calls == 1
    assert widget.run_list.count() == 0
    assert widget.run_list_status_label.text() == "已載入 3 筆；目前符合 0 筆"


def test_registry_first_show_reads_off_thread_and_reports_loading_status(qt_app):
    service = FakeResearchRunService()
    service_started = threading.Event()
    release_service = threading.Event()

    def blocking_list_runs(include_archived=False):
        service.list_runs_calls += 1
        service.list_runs_thread_id = threading.get_ident()
        service_started.set()
        release_service.wait(timeout=2)
        return service.runs

    service.list_runs = blocking_list_runs
    widget = RunRegistryCompareWidget(service, page_size=10)
    gui_thread_id = threading.get_ident()
    fail_safe_release = threading.Timer(2, release_service.set)
    fail_safe_release.start()
    try:
        widget.showEvent(None)
        assert service_started.wait(timeout=1)
        assert service.list_runs_thread_id != gui_thread_id
        assert "載入中" in widget.run_list_status_label.text()
        qt_app.processEvents()
        assert not release_service.is_set()
    finally:
        release_service.set()
        fail_safe_release.cancel()
        fail_safe_release.join(timeout=1)

    _wait_for_run_list(widget, qt_app)
    assert widget.run_list.count() == 3
    assert widget.run_list_status_label.text() == "已載入 3 筆；目前符合 3 筆"


def test_registry_async_refresh_failure_preserves_previous_runs_and_reports_error(qt_app):
    service = FakeResearchRunService()
    widget = RunRegistryCompareWidget(service, page_size=10)
    widget.refresh_runs()
    service.list_runs_error = RuntimeError("registry read failed")

    widget.refresh_runs_async()
    _wait_for_run_list(widget, qt_app)

    assert len(widget._all_runs) == 3
    assert widget.run_list.count() == 3
    assert "更新失敗；保留 3 筆" in widget.run_list_status_label.text()
    assert "registry read failed" in widget.run_list_status_label.toolTip()


def test_registry_async_refresh_rejects_cancelled_stale_result(qt_app):
    first_started = threading.Event()
    release_first = threading.Event()

    class SequencedService(FakeResearchRunService):
        def list_runs(self, include_archived=False):
            with self._list_runs_lock:
                self.list_runs_calls += 1
                call_number = self.list_runs_calls
            if call_number == 1:
                first_started.set()
                release_first.wait(timeout=2)
                return [_metadata("stale")]
            return [_metadata("fresh")]

    service = SequencedService()
    widget = RunRegistryCompareWidget(service, page_size=10)
    try:
        widget.refresh_runs_async()
        assert first_started.wait(timeout=1)
        widget.refresh_runs_async()

        deadline = time.monotonic() + 3
        while (
            widget._run_list_loading
            or not widget._all_runs
        ) and time.monotonic() < deadline:
            qt_app.processEvents()
            QTest.qWait(10)
        assert [run.run_id for run in widget._all_runs] == ["fresh"]
    finally:
        release_first.set()

    _wait_for_run_list(widget, qt_app)
    assert [run.run_id for run in widget._all_runs] == ["fresh"]


def test_registry_list_response_is_discarded_after_shutdown(qt_app):
    service = FakeResearchRunService()
    service_started = threading.Event()
    release_service = threading.Event()

    def blocking_list_runs(include_archived=False):
        service_started.set()
        release_service.wait(timeout=2)
        return [_metadata("late-after-shutdown")]

    service.list_runs = blocking_list_runs
    widget = RunRegistryCompareWidget(service, page_size=10)
    widget.refresh_runs_async()
    try:
        assert service_started.wait(timeout=1)
        widget.begin_run_list_shutdown()
        assert not widget._run_list_loading
    finally:
        release_service.set()

    _wait_for_run_list(widget, qt_app)
    assert widget._all_runs == []
    assert widget._run_list_snapshot_loaded is False
    assert widget.run_list_status_label.text() == "尚未載入"


def test_registry_compare_blocks_mixed_versions_and_clears_previous_results(qt_app):
    from dataclasses import replace

    service = FakeResearchRunService()
    widget = RunRegistryCompareWidget(service, page_size=10)
    widget.refresh_runs()
    widget.run_list.item(0).setSelected(True)
    widget.run_list.item(1).setSelected(True)
    widget.compare_selected_runs()
    assert widget.metrics_table.model().rowCount() == 2
    service.runs[0] = replace(service.runs[0], execution_price="next-session-open.v2")
    service.runs[1] = replace(service.runs[1], execution_price="legacy-same-day-close.v1")
    widget.compare_selected_runs()
    assert widget.metrics_table.model().rowCount() == 0
    assert widget.normalized_equity_table.model().rowCount() == 0
    assert "績效／權益比較已停止" in widget.normalized_equity_empty_label.text()


def test_registry_compare_reports_corruption_without_implicit_repair(qt_app):
    from app_module.research_run_service import ResearchRunIntegrityError

    service = FakeResearchRunService()
    service.load_run_data = MagicMock(side_effect=ResearchRunIntegrityError("hash 不一致"))
    widget = RunRegistryCompareWidget(service, page_size=10)
    widget.refresh_runs()
    widget.run_list.item(0).setSelected(True)
    widget.run_list.item(1).setSelected(True)
    widget.compare_selected_runs()
    assert "未進行修復或重算" in widget.normalized_equity_empty_label.text()
    assert widget.metrics_table.model().rowCount() == 0


def test_registry_compare_clears_prior_metrics_when_saved_equity_has_duplicate_date(qt_app):
    service = FakeResearchRunService()
    widget = RunRegistryCompareWidget(service, page_size=10)
    widget.refresh_runs()
    widget.run_list.item(0).setSelected(True)
    widget.run_list.item(1).setSelected(True)
    widget.compare_selected_runs()
    assert widget.metrics_table.model().rowCount() == 2

    original = pd.DataFrame({
        "日期": ["2026-01-02", "2026-01-02"],
        "portfolio_value": [2000, 2100],
    })
    service.data["run-b"] = original.copy(deep=True)
    widget.compare_selected_runs()

    assert "不可直接比較" in widget.comparability_badge.text()
    assert "重複日期" in widget.normalized_equity_empty_label.text()
    assert widget.metrics_table.model().rowCount() == 0
    assert widget.metrics_summary_table.isHidden()
    assert widget.normalized_equity_table.model().rowCount() == 0
    pd.testing.assert_frame_equal(service.data["run-b"], original)
