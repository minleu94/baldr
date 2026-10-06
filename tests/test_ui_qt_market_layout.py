"""市場相關 Qt 頁面的預設尺寸、捲動與五列可讀性回歸。"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt
from PySide6.QtGui import QFont, QFontMetrics, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableView,
    QWidget,
)
import shiboken6

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app_module.dtos import RegimeResultDTO
from decision_module.flow_contracts import (
    BranchFlowAggregation,
    FlowSignalDTO,
    StockFlowAggregation,
)
from ui_qt.models.pandas_table_model import PandasTableModel
from ui_qt.theme.fonts import preferred_qt_chinese_font_family, register_qt_chinese_fonts
from ui_qt.theme.qss import build_global_stylesheet
from ui_qt.views.dashboard_view import DashboardView
from ui_qt.views.market_regime_view import MarketRegimeView
from ui_qt.views.smart_money.smart_money_flow_view import SmartMoneyFlowView
from ui_qt.views.smart_money.terminal_table_model import BranchTrackerTableModel
from ui_qt.views.strong_industries_view import StrongIndustriesView
from ui_qt.views.strong_stocks_view import StrongStocksView
from ui_qt.views.weak_industries_view import WeakIndustriesView
from ui_qt.views.weak_stocks_view import WeakStocksView


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
        # QApplication 的 QSS setter 會讓現存 QWidget 全面 StyleChange；測試
        # 主題已相同時跳過兩個全域 setter，避免累積的 Qt widgets 重複 polish。
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
    app.processEvents()


def _stocks_frame(rows: int = 12) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "排名": row + 1,
                "證券代號": f"{2300 + row:04d}",
                "證券名稱": f"測試公司 {row + 1}",
                "收盤價": 100 + row,
                "漲幅%": row / 10,
                "評分": 80 - row,
                "推薦理由": f"合成測試理由 {row + 1}，用於檢查長文字是否可以換行及捲動。",
            }
            for row in range(rows)
        ]
    )


def _industries_frame(rows: int = 12) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "排名": row + 1,
                "指數名稱": f"合成產業 {row + 1}",
                "收盤指數": 1200 + row,
                "漲幅%": row / 20,
            }
            for row in range(rows)
        ]
    )


def _make_view(name: str) -> QWidget:
    if name == "strong_stocks":
        view = StrongStocksView(SimpleNamespace(), watchlist_service=MagicMock())
        view.add_to_watchlist_btn.setVisible(True)
        view.load_btn.hide()
        view.refresh_btn.show()
        return view
    if name == "weak_stocks":
        view = WeakStocksView(SimpleNamespace(), watchlist_service=MagicMock())
        view.add_to_watchlist_btn.setVisible(True)
        view.load_btn.hide()
        view.refresh_btn.show()
        return view
    if name == "strong_industries":
        view = StrongIndustriesView(SimpleNamespace())
        view.load_btn.hide()
        view.refresh_btn.show()
        return view
    if name == "weak_industries":
        view = WeakIndustriesView(SimpleNamespace())
        view.load_btn.hide()
        view.refresh_btn.show()
        return view
    if name == "dashboard":
        screening = MagicMock()
        screening.get_strong_stocks.return_value = (_stocks_frame(), 6000)
        screening.get_strong_industries.return_value = _industries_frame()
        return DashboardView(screening, MagicMock())
    raise ValueError(name)


def _mount_in_shell(
    view: QWidget,
    size: tuple[int, int],
    navigation_width: int,
) -> QMainWindow:
    host = QMainWindow()
    shell = QWidget()
    shell_layout = QHBoxLayout(shell)
    shell_layout.setContentsMargins(0, 0, 0, 0)
    shell_layout.setSpacing(0)
    navigation = QWidget()
    navigation.setFixedWidth(navigation_width)
    navigation.setObjectName("leftNavigationGeometryProbe")
    shell_layout.addWidget(navigation)
    shell_layout.addWidget(view, stretch=1)
    host.setCentralWidget(shell)
    host.setFixedSize(*size)
    host.show()
    return host


def _populate_table(table: QTableView, rows: int = 40, columns: int = 8) -> None:
    model = QStandardItemModel(rows, columns, table)
    model.setHorizontalHeaderLabels([f"資料欄位 {column + 1}" for column in range(columns)])
    for row in range(rows):
        for column in range(columns):
            model.setItem(
                row,
                column,
                QStandardItem(f"合成資料 {row + 1:02d} / 欄位 {column + 1}"),
            )
    table.setModel(model)
    for column in range(columns):
        table.setColumnWidth(column, 180)


def _assert_table_five_rows_and_both_scroll_axes(
    qt_app: QApplication,
    table: QTableView,
) -> None:
    model = table.model()
    assert model is not None and model.rowCount() >= 6 and model.columnCount() >= 2
    original_minimum = table.minimumHeight()
    original_maximum = table.maximumHeight()
    table.setFixedHeight(original_minimum)
    try:
        qt_app.processEvents()
        vertical = table.verticalScrollBar()
        vertical.setValue(vertical.minimum())
        qt_app.processEvents()
        fifth = table.visualRect(model.index(4, 0))
        assert fifth.isValid() and fifth.top() >= 0
        assert fifth.bottom() < table.viewport().height()

        vertical.setValue(vertical.maximum())
        qt_app.processEvents()
        assert vertical.maximum() > vertical.minimum()
        assert vertical.value() > vertical.minimum()
        table.scrollTo(model.index(5, 0), QAbstractItemView.ScrollHint.PositionAtBottom)
        qt_app.processEvents()
        sixth = table.visualRect(model.index(5, 0))
        assert sixth.isValid() and table.viewport().rect().intersects(sixth)

        horizontal = table.horizontalScrollBar()
        if horizontal.maximum() > horizontal.minimum():
            horizontal.setValue(horizontal.maximum())
            qt_app.processEvents()
        last_column = table.visualRect(model.index(4, model.columnCount() - 1))
        assert last_column.isValid()
        assert table.viewport().rect().intersects(last_column)
    finally:
        table.setMaximumHeight(original_maximum)
        table.setMinimumHeight(original_minimum)
        qt_app.processEvents()


@pytest.mark.parametrize("page_name", [
    "strong_stocks",
    "weak_stocks",
    "strong_industries",
    "weak_industries",
    "dashboard",
])
@pytest.mark.parametrize(
    ("size", "navigation_width"),
    [((600, 900), 58), ((1400, 800), 184), ((2293, 912), 184)],
    ids=("narrow-shell", "default-window", "maximized-1_5x"),
)
def test_screening_and_dashboard_tables_show_five_rows_and_scroll(
    qt_app: QApplication,
    page_name: str,
    size: tuple[int, int],
    navigation_width: int,
) -> None:
    view = _make_view(page_name)
    host = _mount_in_shell(view, size, navigation_width)
    qt_app.processEvents()

    if page_name == "dashboard":
        assert isinstance(view, DashboardView)
        assert view._dashboard_narrow is (size[0] - navigation_width < view.RESPONSIVE_BREAKPOINT)
        tables = [view.stocks_table, view.industries_table]
    elif page_name in {"strong_stocks", "weak_stocks"}:
        tables = [view.stocks_table]
        assert isinstance(view.page_scroll_area, QScrollArea)
        assert isinstance(view.controls_scroll_area, QScrollArea)
        assert view.controls_scroll_area.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Minimum
        if page_name == "strong_stocks":
            view._update_table_with_data(_stocks_frame())
        else:
            view._update_table_with_data(_stocks_frame())
    else:
        tables = [view.industries_table]
        assert isinstance(view.page_scroll_area, QScrollArea)
        assert isinstance(view.controls_scroll_area, QScrollArea)
        assert view.controls_scroll_area.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Minimum
        view._update_table_with_data(_industries_frame())

    for table in tables:
        _populate_table(table)
    qt_app.processEvents()
    for table in tables:
        assert table.minimumHeight() > 5
        _assert_table_five_rows_and_both_scroll_axes(qt_app, table)

    if size[0] <= 600 and page_name != "dashboard":
        assert view.controls_scroll_area.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
        bar = view.controls_scroll_area.horizontalScrollBar()
        if size[0] < 500:
            assert bar.maximum() > 0
            bar.setValue(bar.maximum())
            qt_app.processEvents()
            assert bar.value() == bar.maximum()

    host.close()
    host.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qt_app.processEvents()


@pytest.mark.parametrize(
    ("size", "navigation_width"),
    [((600, 480), 58), ((1400, 800), 184), ((2293, 912), 184)],
    ids=("short-narrow-shell", "default-window", "maximized-1_5x"),
)
def test_market_regime_keeps_layer_three_and_long_warning_reachable(
    qt_app: QApplication,
    size: tuple[int, int],
    navigation_width: int,
) -> None:
    view = MarketRegimeView(MagicMock())
    host = _mount_in_shell(view, size, navigation_width)
    details = {
        "close": 22000,
        "ma20": 21800,
        "ma60": 21400,
        "ma20_slope": 0.02,
        "adx": 28,
        "adx_value": 28,
        "adx_contribution": 0.8,
        "plus_di": 29,
        "minus_di": 17,
        "atr": 320,
        "trend_distance": 0.9,
        "distance_contribution": 0.6,
        "structure_score": 0.8,
        "strength_score": 0.82,
        "trend_confidence": 0.91,
        "bb_bandwidth": 0.12,
        "rsi": 61,
        "reversion_score": 0.2,
        "breakout_score": 0.65,
        "close_above_ma60": True,
        "ma20_slope_positive": True,
        "plus_di_above_minus_di": True,
        "bandwidth_compressed": False,
        "price_in_range": False,
        "adx_low": False,
        "volume_expanding": True,
        "custom_warning": "合成警示：資料品質需人工確認；" * 12,
    }
    dto = RegimeResultDTO("Trend", 0.91, details, "趨勢市場")
    view._update_layer1(dto)
    view._update_layer2(dto)
    view._update_layer3(dto)
    view.strategy_text.setPlainText(
        "長文字風險與策略限制\n\n" + "使用者必須能閱讀完整的策略條件與資料限制。" * 80
    )
    view.layer3_group.setChecked(True)
    qt_app.processEvents()

    assert isinstance(view.page_scroll_area, QScrollArea)
    assert isinstance(view.layer3_scroll_area, QScrollArea)
    assert view.layer3_scroll_area.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    assert view.strategy_text.minimumHeight() >= 160
    assert view.layer3_scroll_area.minimumHeight() >= 200
    assert len(view.layer3_content.findChildren(QWidget)) >= 10
    if size[0] < 700:
        assert view.page_scroll_area.verticalScrollBar().maximum() > 0
        assert view.layer3_scroll_area.horizontalScrollBar().maximum() > 0
        horizontal = view.layer3_scroll_area.horizontalScrollBar()
        horizontal.setValue(horizontal.maximum())
        qt_app.processEvents()
        raw_group = next(
            group
            for group in view.layer3_content.findChildren(QWidget)
            if getattr(group, "title", lambda: "")() == "原始資料"
        )
        raw_origin = raw_group.mapTo(view.layer3_scroll_area.viewport(), QPoint(0, 0))
        assert view.layer3_scroll_area.viewport().rect().intersects(
            raw_group.rect().translated(raw_origin)
        )

    host.close()
    host.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qt_app.processEvents()


def _smart_money_signals(count: int = 40) -> list[FlowSignalDTO]:
    return [
        FlowSignalDTO(
            stock_code=f"{2300 + row:04d}",
            stock_name=f"合成公司 {row + 1}",
            aggregation=StockFlowAggregation(
                stock_code=f"{2300 + row:04d}",
                stock_name=f"合成公司 {row + 1}",
                total_buy_qty=2000 + row,
                total_sell_qty=200 + row,
                total_net_qty=1800 + row,
            ),
            smart_money_score=90 - row,
            branch_concentration=0.5,
            signal_tags=["合成訊號", "買超"],
            sparkline_data=[-2.0, 1.0, 3.0, 2.0, 5.0],
            intensity_level=2,
        )
        for row in range(count)
    ]


def _smart_money_branches(count: int = 40) -> list[BranchFlowAggregation]:
    return [
        BranchFlowAggregation(
            branch_system_key=f"branch-{row}",
            branch_display_name=f"合成分點 {row + 1}",
            stock_code=f"{2300 + row:04d}",
            stock_name=f"合成公司 {row + 1}",
            total_buy_qty=2000 + row,
            total_sell_qty=200 + row,
            total_net_qty=1800 + row,
            sparkline_data=[-2.0, 1.0, 3.0, 2.0, 5.0],
        )
        for row in range(count)
    ]


def test_smart_money_summary_titles_have_font_glyphs_and_natural_height(
    qt_app: QApplication,
) -> None:
    view = SmartMoneyFlowView(MagicMock())
    try:
        expected_titles = {
            "lbl_regime": "市場趨勢",
            "lbl_heat": "熱度",
            "lbl_bull_bear": "多空個股數",
            "lbl_abnormal": "異常警示",
        }
        for key, expected_title in expected_titles.items():
            card = getattr(view.summary_strip, key)
            title_label = card["title_lbl"]
            assert title_label.text() == expected_title
            metrics = QFontMetrics(title_label.font())
            unsupported = [
                character
                for character in expected_title
                if not character.isspace() and not metrics.inFontUcs4(ord(character))
            ]
            assert not unsupported, (
                f"font={title_label.font().family()!r}, "
                f"application_font={qt_app.font().family()!r}, "
                f"unsupported={unsupported!r}"
            )
            assert card["card"].maximumHeight() > card["card"].minimumHeight()

        assert view.summary_strip.maximumHeight() > view.summary_strip.minimumHeight()
    finally:
        view.close()
        view.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        qt_app.processEvents()


@pytest.mark.parametrize(
    ("size", "navigation_width"),
    [
        ((390, 480), 58),
        ((390, 844), 58),
        ((600, 900), 58),
        ((1400, 800), 184),
        ((2293, 912), 184),
    ],
    ids=("short-phone", "phone-width", "compact-window", "default-window", "maximized-1_5x"),
)
def test_smart_money_reflows_and_keeps_each_table_readable(
    qt_app: QApplication,
    size: tuple[int, int],
    navigation_width: int,
) -> None:
    view = SmartMoneyFlowView(MagicMock())
    host = _mount_in_shell(view, size, navigation_width)
    view._apply_scanner_signals(_smart_money_signals())
    view.detail_table.setModel(
        PandasTableModel(
            pd.DataFrame(
                [
                    {
                        "分點名稱": f"合成分點 {row + 1}",
                        "買進張數": 2000 + row,
                        "賣出張數": 200 + row,
                        "淨買賣超": 1800 + row,
                    }
                    for row in range(40)
                ]
            )
        )
    )
    view.branch_table.setModel(BranchTrackerTableModel(_smart_money_branches()))
    qt_app.processEvents()

    narrow = view.width() < view.RESPONSIVE_BREAKPOINT
    expected_orientation = (
        Qt.Orientation.Vertical if narrow else Qt.Orientation.Horizontal
    )
    assert view.splitter.orientation() == expected_orientation
    assert view.scanner_table.minimumWidth() == 0
    assert view.page_scroll_area.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    assert view.summary_scroll_area.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    assert view.controls_scroll_area.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    assert view.summary_scroll_area.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Minimum
    assert view.controls_scroll_area.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Minimum
    if size[0] < 700:
        if view.summary_strip.minimumWidth() > view.summary_scroll_area.viewport().width():
            assert view.summary_scroll_area.horizontalScrollBar().maximum() > 0
        if view.controls_scroll_area.widget().minimumWidth() > view.controls_scroll_area.viewport().width():
            assert view.controls_scroll_area.horizontalScrollBar().maximum() > 0
    if size[1] < 600:
        assert view.page_scroll_area.verticalScrollBar().maximum() > 0

    view.tab_widget.setCurrentIndex(0)
    qt_app.processEvents()
    _assert_table_five_rows_and_both_scroll_axes(qt_app, view.scanner_table)
    _assert_table_five_rows_and_both_scroll_axes(qt_app, view.detail_table)

    view.tab_widget.setCurrentIndex(1)
    qt_app.processEvents()
    _assert_table_five_rows_and_both_scroll_axes(qt_app, view.branch_table)

    host.close()
    host.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qt_app.processEvents()
