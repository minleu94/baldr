from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QProgressBar

from app_module.backtest_optimization_stability import (
    OptimizationParameterStability,
    OptimizationStabilitySummary,
)
from ui_qt.views.backtest.result_panel import OptimizationStabilityDistribution
from ui_qt.views.backtest_view import BacktestView


def app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return instance


def _parameter(
    name: str,
    value_bp: int | None,
    present: int,
    total: int,
) -> OptimizationParameterStability:
    return OptimizationParameterStability(
        name=name,
        unique_count=3,
        minimum="1",
        maximum="9",
        value_kind="numeric",
        range_text="numeric range=1~9",
        top5_concentration_bp=value_bp,
        top5_present_count=present,
        top5_total_count=total,
    )


def _summary(
    parameters: tuple[OptimizationParameterStability, ...],
    *,
    status: str = "available",
) -> OptimizationStabilitySummary:
    return OptimizationStabilitySummary(
        status=status,
        sample_count=10,
        objective_sample_count=8,
        objective_name="Sharpe ratio",
        objective_top="1.2",
        objective_median="0.8",
        objective_worst="0.2",
        objective_dispersion="1.0",
        parameters=parameters,
        note="只根據保留的 Top-N；需另跑 OOS。",
    )


def test_optimization_stability_distribution_shows_exact_bp_and_present_denominator() -> None:
    app()
    view = OptimizationStabilityDistribution()
    view.set_summary(
        _summary(
            (
                _parameter("lookback", 6000, 3, 5),
                _parameter("entry_mode", None, 0, 5),
            )
        )
    )

    bar = view.findChild(QProgressBar, "optimizationConcentrationBar_0")
    valid_value = view.findChild(QLabel, "optimizationConcentrationValue_0")
    unknown_name = view.findChild(QLabel, "optimizationParameterName_1")
    unknown_value = view.findChild(QLabel, "optimizationConcentrationValue_1")
    assert not view.isHidden()
    assert bar is not None and bar.value() == 6000 and bar.maximum() == 10_000
    assert valid_value is not None and valid_value.text() == "6000 bp (3/5)"
    assert unknown_name is not None and unknown_name.text() == "entry_mode"
    assert unknown_value is not None and unknown_value.text() == "未知 (0/5)"
    assert not view.findChildren(QProgressBar, "optimizationConcentrationBar_1")
    assert "依有效 objective 排序的目前保留最多前五名" in view.scope_label.text()
    assert "不代表完整參數面、穩健性、OOS、績效或資格" in view.scope_label.text()


def test_optimization_stability_distribution_limits_rows_and_preserves_summary_access() -> None:
    app()
    parameters = tuple(_parameter(f"p{index}", 5000, 5, 5) for index in range(10))
    view = OptimizationStabilityDistribution()
    view.set_summary(_summary(parameters))

    assert len(view._rows) == 9
    assert view.findChild(QLabel, "optimizationParameterName_7").text() == "p7"
    assert not view.findChild(QLabel, "optimizationParameterName_8")
    omitted = view.findChild(QLabel, "optimizationConcentrationOmitted")
    assert omitted is not None and "另有 2 個參數" in omitted.text()


def test_insufficient_summary_hides_and_immediately_detaches_previous_bars() -> None:
    app()
    view = OptimizationStabilityDistribution()
    view.set_summary(_summary((_parameter("lookback", 8000, 4, 5),)))
    old_row = view._rows[0]
    old_bar = old_row.findChild(QProgressBar, "optimizationConcentrationBar_0")
    assert old_bar is not None and old_bar.isVisible()

    view.set_summary(_summary((), status="insufficient"))

    assert view.isHidden()
    assert not view._rows
    assert old_row.parentWidget() is None
    assert old_row.isHidden()
    assert not old_bar.isVisible()
    assert not view.findChildren(QProgressBar)


def test_empty_optimization_result_clears_old_summary_table_and_result_state(monkeypatch) -> None:
    app()
    warnings: list[str] = []
    monkeypatch.setattr(
        "ui_qt.views.backtest_view.QMessageBox.warning",
        lambda _view, _title, message: warnings.append(message),
    )

    class _Control:
        def setEnabled(self, _enabled: bool) -> None:
            pass

        def setVisible(self, _visible: bool) -> None:
            pass

    class _Label(_Control):
        text = "舊一輪的 Top-N 文字"

        def setText(self, value: str) -> None:
            self.text = value

    class _Table:
        model = "舊表格模型"

        def setModel(self, model) -> None:
            self.model = model

    class _Distribution:
        summary = "舊一輪的 DTO"

        def set_summary(self, summary) -> None:
            self.summary = summary

    label = _Label()
    table = _Table()
    distribution = _Distribution()
    view = SimpleNamespace(
        execute_btn=_Control(),
        progress_bar=_Control(),
        progress_label=_Control(),
        config_panel=SimpleNamespace(cancel_btn=None),
        current_optimization_results=["舊結果"],
        optimization_stability_summary="舊摘要 DTO",
        optimization_model="舊模型",
        optimization_stability_label=label,
        optimization_stability_distribution=distribution,
        optimization_table=table,
    )

    BacktestView._on_optimization_finished(view, [])

    assert view.current_optimization_results == []
    assert view.optimization_stability_summary is None
    assert view.optimization_model is None
    assert table.model is None
    assert "本輪沒有可排名結果" in label.text
    assert distribution.summary is None
    assert len(warnings) == 1
