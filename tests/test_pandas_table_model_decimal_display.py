"""PandasTableModel opt-in Decimal 顯示格式回歸。"""

from decimal import Decimal

import numpy as np
import pandas as pd
import pytest
from PySide6.QtCore import Qt

from decision_module.recommendation.contracts import RecommendationItem
from ui_qt.models.pandas_table_model import PandasTableModel
from ui_qt.views.recommendation.presenter import recommendation_item_to_view_row
from ui_qt.views.recommendation_view import _recommendation_results_table_model


def _decimal_model(values: list[object]) -> PandasTableModel:
    frame = pd.DataFrame({"指標分": pd.Series(values, dtype=object)})
    return PandasTableModel(frame, decimal_places_by_column={"指標分": 2})


def test_recommendation_consumer_formats_decimal_only_for_display() -> None:
    item = RecommendationItem(
        stock_code="2330",
        close_price=Decimal("1785.00"),
        price_change=Decimal("-3.6474164133738602"),
        rule_score=Decimal("64.63"),
        indicator_score=Decimal("51.71201200250351"),
        pattern_score=Decimal("31.7"),
        volume_score=100,
    )
    frame = pd.DataFrame(
        [recommendation_item_to_view_row(item, ml_status="not_requested")]
    )
    model = _recommendation_results_table_model(frame)
    columns = model.getVisibleColumns()
    price_change_column = columns.index("漲幅%")
    indicator_column = columns.index("指標分")

    assert model.data(model.index(0, price_change_column), Qt.DisplayRole) == "-3.65"
    assert model.data(model.index(0, indicator_column), Qt.DisplayRole) == "51.71"
    assert (
        model.data(model.index(0, price_change_column), Qt.ToolTipRole)
        == "-3.6474164133738602"
    )
    assert (
        model.data(model.index(0, indicator_column), Qt.ToolTipRole)
        == "51.71201200250351"
    )
    raw = model.getDataFrame()
    assert raw.at[0, "漲幅%"] == item.price_change
    assert raw.at[0, "指標分"] == item.indicator_score


def test_decimal_sorting_uses_unrounded_values_and_keeps_raw_values() -> None:
    values = [Decimal("51.712"), Decimal("51.714")]
    frame = pd.DataFrame(
        {"證券代號": ["A", "B"], "指標分": pd.Series(values, dtype=object)}
    )
    model = PandasTableModel(frame, decimal_places_by_column={"指標分": 2})
    model.sort(1, Qt.DescendingOrder)

    sorted_frame = model.getDataFrame()
    assert sorted_frame["證券代號"].tolist() == ["B", "A"]
    assert sorted_frame["指標分"].tolist() == [
        Decimal("51.714"),
        Decimal("51.712"),
    ]
    assert model.data(model.index(0, 1), Qt.DisplayRole) == "51.71"
    assert model.data(model.index(1, 1), Qt.DisplayRole) == "51.71"


def test_large_python_and_numpy_integers_keep_exact_decimal_display() -> None:
    exact_integer = 9007199254740993
    values = [exact_integer, np.int64(exact_integer)]
    frame = pd.DataFrame({"指標分": pd.Series(values, dtype=object)})
    model = PandasTableModel(frame, decimal_places_by_column={"指標分": 2})

    for row, value in enumerate(values):
        assert model.data(model.index(row, 0), Qt.DisplayRole) == "9007199254740993.00"
        assert model.data(model.index(row, 0), Qt.ToolTipRole) == str(value)
    assert model.getDataFrame()["指標分"].tolist() == values


def test_configured_numeric_column_rejects_nonfinite_and_invalid_types() -> None:
    values: list[object] = [
        Decimal("NaN"),
        Decimal("Infinity"),
        True,
        51.71,
        "51.71",
        None,
    ]
    model = _decimal_model(values)

    for row, value in enumerate(values):
        assert model.data(model.index(row, 0), Qt.DisplayRole) == "未知"
        tooltip = model.data(model.index(row, 0), Qt.ToolTipRole)
        assert tooltip == ("" if value is None else str(value))


def test_decimal_display_options_are_strict_and_unconfigured_behavior_is_unchanged() -> None:
    frame = pd.DataFrame({"指標分": pd.Series([Decimal("1.2345")], dtype=object)})

    with pytest.raises(TypeError):
        PandasTableModel(frame, decimal_places_by_column={"指標分": True})
    with pytest.raises(TypeError):
        PandasTableModel(frame, decimal_places_by_column={"指標分": 2.0})
    with pytest.raises(ValueError):
        PandasTableModel(frame, decimal_places_by_column={"指標分": 9})
    with pytest.raises(ValueError):
        PandasTableModel(frame, decimal_places_by_column={"不存在": 2})

    unconfigured = PandasTableModel(frame)
    assert unconfigured.data(unconfigured.index(0, 0), Qt.DisplayRole) == "1.2345"
