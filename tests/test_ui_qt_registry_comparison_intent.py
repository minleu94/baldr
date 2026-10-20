import os
import sys
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication

from app_module.research_run_dtos import ResearchRunMetadataDTO
from app_module.saved_strategy_signal_comparison import SavedSignalComparison
from ui_qt.views.research_lab.run_registry_compare_widget import RunRegistryCompareWidget


@pytest.fixture
def qt_app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def _metadata(run_id: str, strategy_id: str, strategy_version: str, fingerprint: str):
    return ResearchRunMetadataDTO(
        run_id=run_id,
        run_name=run_id,
        run_type="single_backtest",
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        universe=["2330"],
        start_date="2026-01-02",
        end_date="2026-01-08",
        data_fingerprint=fingerprint,
        capital_cents=100_000_000,
        fee_bp_x100=1425,
        slippage_bp_x100=500,
        execution_price="next_open",
        sizing_mode="fixed_amount",
        normalized_params={"params": {}},
        metrics={"status": "completed"},
        data_manifest={"run_status": "completed"},
        payload_hash=f"sha256:{run_id}",
        created_at="2026-10-18T08:00:00",
    )


class _ResearchRunService:
    def __init__(self):
        self.runs = [
            _metadata("ma-run", "baldr_ma_alignment_basic_v1", "1.1.0", "sha256:ma"),
            _metadata("w-bottom-run", "baldr_w_bottom_basic_v1", "1.0.0", "sha256:w-bottom"),
        ]
        self._equity = {
            run.run_id: pd.DataFrame(
                {"日期": ["2026-01-02", "2026-01-05"], "portfolio_value": [1000, 1010]}
            )
            for run in self.runs
        }

    def list_runs(self, include_archived: bool = False):
        return self.runs

    def load_run_data(self, run_id: str):
        metadata = next(run for run in self.runs if run.run_id == run_id)
        return SimpleNamespace(
            metadata=metadata,
            equity=self._equity[run_id],
            trades=pd.DataFrame(),
        )


def _selected_widget(qt_app):
    widget = RunRegistryCompareWidget(_ResearchRunService(), page_size=10)
    widget.refresh_runs()
    widget.run_list.selectAll()
    assert len(widget.selected_run_ids()) == 2
    return widget


def test_registry_exposes_distinct_performance_and_saved_signal_actions(qt_app):
    widget = _selected_widget(qt_app)

    assert widget.compare_button.text() == "比較績效／權益"
    assert "績效摘要" in widget.compare_button.toolTip()
    assert "資料指紋" in widget.compare_button.toolTip()
    assert "成本" in widget.compare_button.toolTip()
    assert widget.signal_comparison.compare_button.text() == "對照原保存逐日訊號"
    assert "不比較成交、權益或績效" in widget.signal_comparison.compare_button.toolTip()
    assert "不按成交筆數推算" in widget.signal_comparison.compare_button.toolTip()
    assert "原規則與逐日訊號" in widget.signal_comparison.compare_button.toolTip()
    assert "股票、日期窗與價量內容完全相同" in widget.signal_comparison.compare_button.toolTip()
    assert widget.compare_button.isEnabled()
    assert widget.signal_comparison.compare_button.isEnabled()


def test_performance_incompatibility_names_reason_without_disabling_signal_action(qt_app):
    widget = _selected_widget(qt_app)

    widget.compare_selected_runs()

    message = widget.normalized_equity_empty_label.text()
    assert "績效／權益比較已停止" in message
    assert "資料指紋不同" in message
    assert "不表示訊號可對照" in message
    assert "原規則／訊號綁定" in message
    assert widget.metrics_table.model().rowCount() == 0
    assert widget.signal_comparison.compare_button.isEnabled()
    assert len(widget.signal_comparison._selection) == 2


def test_signal_rejection_keeps_its_exact_reason_separate_from_performance(qt_app):
    widget = _selected_widget(qt_app)
    signal_widget = widget.signal_comparison
    reason = "研究窗價量、日期、股票或解析版本不同；不得以日期交集代替"
    result = SavedSignalComparison("unavailable", (reason,))

    signal_widget._loaded({"generation": signal_widget._generation, "result": result})

    assert signal_widget.result is result
    assert "不可對照" in signal_widget.status.text()
    assert reason in signal_widget.status.text()
    assert "績效可比" not in signal_widget.status.text()
    assert not signal_widget.view_result_button.isEnabled()
