"""Research Lab 回測頁的預設桌面幾何與可讀列數回歸。"""

from __future__ import annotations

import os
import sys
import logging
from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
import pandas as pd
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt
from PySide6.QtGui import QFont, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHeaderView,
    QHBoxLayout,
    QListView,
    QListWidget,
    QMainWindow,
    QScrollArea,
    QTableView,
    QTableWidget,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)
import shiboken6

from ui_qt.views.backtest_view import BacktestView
from ui_qt.theme.fonts import preferred_qt_chinese_font_family, register_qt_chinese_fonts
from ui_qt.theme.qss import build_global_stylesheet


@pytest.fixture
def qt_app() -> Iterator[QApplication]:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)

    existing_top_level_pointers = {
        pointer
        for widget in instance.topLevelWidgets()
        if (pointer := _qobject_pointer(widget)) is not None
    }

    font_families = register_qt_chinese_fonts()
    preferred_font = preferred_qt_chinese_font_family(font_families)
    target_font = None
    if preferred_font:
        target_font = QFont(preferred_font, instance.font().pointSize())

    target_stylesheet = build_global_stylesheet()
    if instance.styleSheet() != target_stylesheet:
        # 相同全域 QSS 的重設會對現存 widgets 重新套用 style，造成昂貴的
        # layout/helper 重量測；只有主題不同時才切換 Fusion 並套用 QSS。
        instance.setStyle("Fusion")
        instance.setStyleSheet(target_stylesheet)
    if target_font is not None and instance.font() != target_font:
        instance.setFont(target_font)

    try:
        yield instance
    finally:
        _delete_new_top_level_widgets(instance, existing_top_level_pointers)


def _qobject_pointer(widget: QWidget) -> int | None:
    try:
        if not shiboken6.isValid(widget):
            return None
        pointers = shiboken6.getCppPointer(widget)
        return int(pointers[0]) if pointers and int(pointers[0]) > 0 else None
    except (RuntimeError, TypeError, IndexError):
        return None


def _delete_new_top_level_widgets(
    app: QApplication,
    original_pointers: set[int],
) -> None:
    new_widgets = [
        widget
        for widget in tuple(app.topLevelWidgets())
        if (pointer := _qobject_pointer(widget)) is not None
        and pointer not in original_pointers
    ]
    for widget in new_widgets:
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _populate_item_view(item_view: QAbstractItemView) -> None:
    """用合成資料驗證空表預留列高、實際資料與捲動行為。"""
    row_count = 40
    column_count = 8
    headers = [f"欄位 {column + 1}" for column in range(column_count)]

    if isinstance(item_view, QTableWidget):
        item_view.setColumnCount(column_count)
        item_view.setRowCount(row_count)
        item_view.setHorizontalHeaderLabels(headers)
        for row in range(row_count):
            for column in range(column_count):
                from PySide6.QtWidgets import QTableWidgetItem

                item_view.setItem(
                    row,
                    column,
                    QTableWidgetItem(f"合成資料 {row + 1:02d} / 欄 {column + 1}"),
                )
        for column in range(column_count):
            item_view.setColumnWidth(column, 220)
        return

    if isinstance(item_view, QListWidget):
        item_view.clear()
        for row in range(row_count):
            item_view.addItem(f"合成清單項目 {row + 1:02d} — 長名稱水平檢視")
        item_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        return

    if isinstance(item_view, QTreeWidget):
        item_view.setColumnCount(column_count)
        item_view.setHeaderLabels(headers)
        item_view.clear()
        for row in range(row_count):
            item_view.addTopLevelItem(
                QTreeWidgetItem(
                    [f"合成資料 {row + 1:02d}"]
                    + [f"欄位 {column + 1}" for column in range(1, column_count)]
                )
            )
        for column in range(column_count):
            item_view.setColumnWidth(column, 220)
        return

    if isinstance(item_view, QListView):
        from PySide6.QtCore import QStringListModel

        item_view.setModel(
            QStringListModel(
                [f"合成清單項目 {row + 1:02d} — 長名稱水平檢視" for row in range(row_count)],
                item_view,
            )
        )
        item_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        return

    if isinstance(item_view, QTableView):
        model = QStandardItemModel(row_count, column_count, item_view)
        model.setHorizontalHeaderLabels(headers)
        for row in range(row_count):
            for column in range(column_count):
                model.setItem(
                    row,
                    column,
                    QStandardItem(f"合成資料 {row + 1:02d} / 欄 {column + 1}"),
                )
        item_view.setModel(model)
        for column in range(column_count):
            item_view.setColumnWidth(column, 220)


def _assert_first_five_rows_and_scroll_to_sixth(
    qt_app: QApplication,
    item_view: QAbstractItemView,
) -> None:
    model = item_view.model()
    assert model is not None
    if isinstance(item_view, QListWidget):
        row_count = item_view.count()
    else:
        row_count = model.rowCount(item_view.rootIndex())
        if row_count == 0:
            row_count = model.rowCount()
    assert row_count >= 6

    original_minimum = item_view.minimumHeight()
    original_maximum = item_view.maximumHeight()
    # 將實際 viewport 收到 helper 計算的最低高度，驗證五列確實在 view 內，
    # 並驗證第六列可透過該 view 自己的 scrollbar 進入 viewport。
    item_view.setFixedHeight(original_minimum)
    try:
        qt_app.processEvents()
        vertical_scrollbar = item_view.verticalScrollBar()
        vertical_scrollbar.setValue(vertical_scrollbar.minimum())
        qt_app.processEvents()
        fifth_index = model.index(4, 0, item_view.rootIndex())
        fifth_rect = item_view.visualRect(fifth_index)
        assert fifth_rect.isValid()
        assert fifth_rect.top() >= 0
        assert fifth_rect.bottom() < item_view.viewport().height()

        sixth_index = model.index(5, 0, item_view.rootIndex())
        vertical_scrollbar.setValue(vertical_scrollbar.maximum())
        qt_app.processEvents()
        assert vertical_scrollbar.maximum() > vertical_scrollbar.minimum()
        assert vertical_scrollbar.value() > vertical_scrollbar.minimum()
        item_view.scrollTo(sixth_index, QAbstractItemView.ScrollHint.PositionAtBottom)
        qt_app.processEvents()
        sixth_rect = item_view.visualRect(sixth_index)
        assert sixth_rect.isValid()
        assert item_view.viewport().rect().intersects(sixth_rect)

        horizontal_scrollbar = item_view.horizontalScrollBar()
        horizontal_header_getter = getattr(item_view, "horizontalHeader", None)
        if callable(horizontal_header_getter):
            column_count = model.columnCount(item_view.rootIndex())
            if column_count > 1 and horizontal_scrollbar.maximum() > horizontal_scrollbar.minimum():
                vertical_scrollbar.setValue(vertical_scrollbar.minimum())
                horizontal_scrollbar.setValue(horizontal_scrollbar.maximum())
                qt_app.processEvents()
                last_column_index = model.index(4, column_count - 1, item_view.rootIndex())
                last_column_rect = item_view.visualRect(last_column_index)
                assert last_column_rect.isValid()
                assert last_column_rect.right() > item_view.viewport().rect().left()
                assert last_column_rect.left() < item_view.viewport().rect().right()
    finally:
        item_view.setMaximumHeight(original_maximum)
        item_view.setMinimumHeight(original_minimum)
        qt_app.processEvents()


@pytest.mark.parametrize(
    ("window_size", "expected_orientation", "navigation_width"),
    [
        ((390, 844), Qt.Orientation.Vertical, 58),
        ((600, 900), Qt.Orientation.Vertical, 58),
        ((1366, 768), Qt.Orientation.Vertical, 184),
        ((1400, 800), Qt.Orientation.Horizontal, 184),
        ((1920, 1080), Qt.Orientation.Horizontal, 184),
        ((2293, 912), Qt.Orientation.Horizontal, 184),
    ],
    ids=(
        "390-narrow-shell",
        "600-narrow-shell",
        "1366-shell",
        "main-window-default",
        "1920-shell",
        "2293-logical-1_5x",
    ),
)
def test_backtest_shell_keeps_controls_and_results_usable(
    qt_app: QApplication,
    test_config,
    window_size: tuple[int, int],
    expected_orientation: Qt.Orientation,
    navigation_width: int,
) -> None:
    """包含 184px 左導覽的 shell 尺寸不能造成回測頁被窄化。"""
    host = QMainWindow()
    shell = QWidget()
    shell_layout = QHBoxLayout(shell)
    shell_layout.setContentsMargins(0, 0, 0, 0)
    shell_layout.setSpacing(0)

    # MainWindow 窄版導覽 58px，標準版展開導覽 184px；保留 shell 寬度。
    navigation = QWidget()
    navigation.setFixedWidth(navigation_width)
    navigation.setObjectName("leftNavigationGeometryProbe")
    shell_layout.addWidget(navigation)

    view = BacktestView(
        backtest_service=MagicMock(),
        config=test_config,
        batch_backtest_service=MagicMock(),
    )
    shell_layout.addWidget(view, stretch=1)
    host.setCentralWidget(shell)
    host.setFixedSize(*window_size)
    host.show()
    qt_app.processEvents()

    assert host.size().width() == window_size[0]
    assert host.size().height() == window_size[1]
    assert view.width() == window_size[0] - navigation_width
    assert view.backtest_splitter.orientation() == expected_orientation
    assert view.config_scroll.width() > 0
    assert view.result_panel.width() > 0
    assert view.config_scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded

    if expected_orientation == Qt.Orientation.Vertical:
        if window_size[0] < 700:
            assert view.config_scroll.width() >= 250
            assert view.result_panel.width() >= 250
            config_scrollbar = view.config_scroll.horizontalScrollBar()
            assert config_scrollbar.maximum() > 0
            config_scrollbar.setValue(config_scrollbar.maximum())
            qt_app.processEvents()
            assert config_scrollbar.value() == config_scrollbar.maximum()
            diagnostics_scroll = view.result_panel._result_tab_widgets["diagnostics"]
            assert diagnostics_scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if window_size[0] < 500:
                view.result_panel.focus_result_tab("diagnostics")
                qt_app.processEvents()
                diagnostics_scrollbar = diagnostics_scroll.horizontalScrollBar()
                assert diagnostics_scrollbar.maximum() > 0
                diagnostics_scrollbar.setValue(diagnostics_scrollbar.maximum())
                qt_app.processEvents()
                rightmost_kpi = view.result_panel.analyst_diagnostics_widget._kpi_labels[
                    "slippage_bp"
                ]
                rightmost_kpi_origin = rightmost_kpi.mapTo(
                    diagnostics_scroll.viewport(), QPoint(0, 0)
                )
                rightmost_kpi_rect = diagnostics_scroll.viewport().rect().intersected(
                    rightmost_kpi.rect().translated(rightmost_kpi_origin)
                )
                assert not rightmost_kpi_rect.isEmpty()
        else:
            assert view.config_scroll.width() >= 900
            assert view.result_panel.width() >= 900
            assert view.config_scroll.height() >= 220
            assert view.result_panel.height() >= 350
    else:
        assert view.config_scroll.width() >= 520
        assert view.result_panel.width() >= 600

    result_panel = view.result_panel
    mode_ids = (
        "single_stock",
        "batch_stock",
        "fixed_basket",
        "recommendation_replay",
        "strategy_research",
    )
    for index in range(view.result_tabs.count()):
        key = result_panel.result_tab_key(index)
        assert key is not None
        content = result_panel.result_tab_content_widget(key)
        assert content is not None
        for item_view in content.findChildren(QAbstractItemView):
            if isinstance(item_view, QHeaderView) or not isinstance(item_view, (QTableView, QListView)):
                continue
            _populate_item_view(item_view)
    qt_app.processEvents()

    for mode_id in mode_ids:
        mode_index = view.research_lab_mode_combo.findData(mode_id)
        assert mode_index >= 0
        view.research_lab_mode_combo.setCurrentIndex(mode_index)
        qt_app.processEvents()

        for index in range(view.result_tabs.count()):
            key = result_panel.result_tab_key(index)
            assert key is not None
            scroll_area = result_panel._result_tab_widgets[key]
            content = result_panel.result_tab_content_widget(key)
            assert isinstance(scroll_area, QScrollArea)
            assert content is not None
            assert scroll_area.widget() is content
            assert scroll_area.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded

            if not view.result_tabs.isTabVisible(index):
                continue
            assert result_panel.focus_result_tab(key) is True
            qt_app.processEvents()
            for item_view in content.findChildren(QAbstractItemView):
                if isinstance(item_view, QHeaderView) or not isinstance(item_view, (QTableView, QListView)):
                    continue
                _populate_item_view(item_view)
            qt_app.processEvents()
            for item_view in content.findChildren(QAbstractItemView):
                if isinstance(item_view, QHeaderView) or not isinstance(item_view, (QTableView, QListView)):
                    continue
                if item_view.isVisible():
                    assert item_view.height() >= item_view.minimumHeight()
                    _assert_first_five_rows_and_scroll_to_sixth(qt_app, item_view)

            if key == "recommendation" and hasattr(result_panel, "portfolio_detail_tabs"):
                for detail_index in range(result_panel.portfolio_detail_tabs.count()):
                    result_panel.portfolio_detail_tabs.setCurrentIndex(detail_index)
                    qt_app.processEvents()
                    for item_view in content.findChildren(QAbstractItemView):
                        if isinstance(item_view, QHeaderView) or not isinstance(item_view, (QTableView, QListView)):
                            continue
                        if item_view.isVisible():
                            _assert_first_five_rows_and_scroll_to_sixth(qt_app, item_view)

    # Semantic keys still resolve to wrapped pages after tab-content wrapping.
    summary_index = view.result_tabs.indexOf(result_panel._result_tab_widgets["summary"])
    assert summary_index >= 0
    assert result_panel.result_tab_key(summary_index) == "summary"
    assert result_panel.result_tab_content_widget("summary") is not None
    assert result_panel.focus_result_tab("summary") is True
    qt_app.processEvents()
    assert view.result_tabs.currentIndex() == summary_index
    assert view.trades_table.isVisible()
    assert view.trades_table.height() >= view.trades_table.minimumHeight()
    assert view.result_panel._result_tab_widgets["legacy"] is not None
    assert view.result_panel._result_tab_widgets["diagnostics"] is not None
    assert view.result_panel._result_tab_widgets["recommendation"] is not None

    host.close()
    host.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qt_app.processEvents()

def test_backtest_charts_load_on_first_result_use_and_replay_pending_reports(
    qt_app: QApplication,
    test_config,
) -> None:
    view = BacktestView(
        backtest_service=MagicMock(),
        config=test_config,
        batch_backtest_service=MagicMock(),
    )
    panel = view.result_panel
    assert panel.charts_available
    assert not panel.chart_widgets_initialized
    assert not panel.portfolio_chart_widgets_initialized

    trade_list = pd.DataFrame(
        {"報酬率%": [5.0, -1.5], "持有天數": [2, 4]}
    )
    equity_curve = pd.DataFrame(
        {"equity": [100.0, 110.0, 105.0]},
        index=pd.to_datetime(["2026-10-01", "2026-10-02", "2026-10-03"]),
    )
    report = SimpleNamespace(
        details={
            "equity_curve": equity_curve,
            "trade_list": trade_list,
        },
        annual_return=0.12,
    )
    view._plot_charts_from_report(report)

    assert not panel.chart_widgets_initialized
    assert set(panel._pending_chart_plots) == {
        "equity_chart",
        "drawdown_chart",
        "return_hist",
        "holding_hist",
    }
    first_queued_equity, _, _, queued_trades = panel._pending_chart_plots[
        "equity_chart"
    ][0]
    equity_curve.loc[pd.Timestamp("2026-10-02"), "equity"] = 999.0
    trade_list.loc[0, "報酬率%"] = 99.0
    assert first_queued_equity.tolist() == [100.0, 110.0, 105.0]
    assert queued_trades.loc[0, "報酬率%"] == 5.0

    next_trades = pd.DataFrame({"報酬率%": [7.5], "持有天數": [8]})
    next_equity_curve = pd.DataFrame(
        {"equity": [200.0, 230.0, 210.0]},
        index=pd.to_datetime(["2026-10-01", "2026-10-02", "2026-10-03"]),
    )
    view._plot_charts_from_report(
        SimpleNamespace(
            details={"equity_curve": next_equity_curve, "trade_list": next_trades},
            annual_return=0.18,
        )
    )
    queued_equity = panel._pending_chart_plots["equity_chart"][0][0]
    assert queued_equity.tolist() == [200.0, 230.0, 210.0]

    assert panel.focus_result_tab("charts")
    qt_app.processEvents()
    assert panel.chart_widgets_initialized
    assert not panel._pending_chart_plots
    chart_widgets = dict(panel._chart_widgets)
    assert set(chart_widgets) == {
        "equity_chart",
        "drawdown_chart",
        "return_hist",
        "holding_hist",
    }
    assert "230" in chart_widgets["equity_chart"].numeric_text.text()
    assert "7.5%" in chart_widgets["return_hist"].numeric_text.text()
    assert "6-20d" in chart_widgets["holding_hist"].numeric_text.text()

    assert panel.focus_result_tab("summary")
    qt_app.processEvents()
    assert panel.focus_result_tab("charts")
    qt_app.processEvents()
    assert all(panel._chart_widgets[name] is widget for name, widget in chart_widgets.items())

    portfolio_result = SimpleNamespace(
        equity_curve=pd.DataFrame(
            {
                "date": ["2026-10-01", "2026-10-02", "2026-10-03"],
                "equity": [100.0, 120.0, 110.0],
            }
        ),
        trades=pd.DataFrame(),
    )
    view._plot_recommendation_portfolio_charts(
        portfolio_result,
        allow_current_benchmark=False,
    )
    assert not panel.portfolio_chart_widgets_initialized
    assert set(panel._pending_portfolio_chart_plots) == {
        "portfolio_equity_chart",
        "portfolio_drawdown_chart",
    }
    pending_portfolio_series = panel._pending_portfolio_chart_plots[
        "portfolio_equity_chart"
    ][0][0]
    portfolio_result.equity_curve.loc[1, "equity"] = 999.0
    assert pending_portfolio_series.iloc[1] == 120.0

    panel.set_research_mode("recommendation_replay")
    assert panel.focus_result_tab("recommendation")
    qt_app.processEvents()
    assert panel.result_tab_key(panel.result_tabs.currentIndex()) == "recommendation"
    assert panel.portfolio_chart_widgets_initialized
    assert not panel._pending_portfolio_chart_plots
    portfolio_widgets = dict(panel._portfolio_chart_widgets)
    assert "120" in portfolio_widgets["portfolio_equity_chart"].numeric_text.text()

    panel.set_research_mode("single_stock")
    qt_app.processEvents()
    panel.set_research_mode("recommendation_replay")
    qt_app.processEvents()
    assert all(
        panel._portfolio_chart_widgets[name] is widget
        for name, widget in portfolio_widgets.items()
    )

    view.close()
    view.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qt_app.processEvents()


def test_backtest_chart_plot_failure_is_visible_isolated_and_retryable(
    qt_app: QApplication,
    test_config,
    monkeypatch,
    caplog,
) -> None:
    import ui_qt.widgets.fast_chart_widget as chart_module

    class FailingChart(QWidget):
        def plot(self, *args, **kwargs):
            raise RuntimeError("chart payload failure")

    view = BacktestView(
        backtest_service=MagicMock(),
        config=test_config,
        batch_backtest_service=MagicMock(),
    )
    panel = view.result_panel
    failed_chart = FailingChart()
    monkeypatch.setattr(chart_module, "create_equity_curve_widget", lambda: failed_chart)

    trade_list = pd.DataFrame({"報酬率%": [3.0], "持有天數": [2]})
    view._plot_charts_from_report(
        SimpleNamespace(
            details={
                "equity_curve": pd.DataFrame(
                    {"equity": [100.0, 120.0]},
                    index=pd.to_datetime(["2026-10-01", "2026-10-02"]),
                ),
                "trade_list": trade_list,
            },
            annual_return=0.1,
        )
    )

    caplog.set_level(logging.ERROR, logger="ui_qt.views.backtest.result_panel")
    assert panel.focus_result_tab("charts")
    qt_app.processEvents()

    assert "equity_chart" in panel._pending_chart_plots
    assert set(panel._pending_chart_plots) == {"equity_chart"}
    assert not panel._chart_error_labels["equity_chart"].isHidden()
    assert "未能繪製" in panel._chart_error_labels["equity_chart"].text()
    assert "3%" in panel._chart_widgets["return_hist"].numeric_text.text()
    assert "chart payload failure" in caplog.text

    monkeypatch.setattr(failed_chart, "plot", lambda *args, **kwargs: None)
    assert panel.ensure_chart_widgets()
    assert not panel._pending_chart_plots
    assert panel._chart_error_labels["equity_chart"].isHidden()

    view.close()
    view.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qt_app.processEvents()
