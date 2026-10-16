import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication

from app_module.research_run_dtos import ResearchRunMetadataDTO
from ui_qt.views.backtest_view import BacktestView
from ui_qt.views.research_lab.run_registry_compare_widget import (
    RunRegistryCompareWidget,
)


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


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

    def list_runs(self, include_archived: bool = False):
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
    widget.run_list.item(0).setSelected(True)
    widget.run_list.item(1).setSelected(True)

    widget.compare_selected_runs()

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
    assert "停止績效混排" in widget.normalized_equity_empty_label.text()


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
    widget.refresh_runs = MagicMock()

    widget.showEvent(None)
    widget.showEvent(None)

    assert widget.refresh_runs.call_count == 1


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
    assert "停止績效混排" in widget.normalized_equity_empty_label.text()


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
