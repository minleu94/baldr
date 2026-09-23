from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import pytest

from analysis_module.technical_analysis.indicator_kernels import clean_price_values
from analysis_module.technical_analysis.technical_analyzer import TechnicalAnalyzer
from analysis_module.technical_analysis.technical_indicators import (
    CAUSAL_INDICATOR_COLUMNS,
    TechnicalIndicatorCalculator,
    calculate_causal_indicators,
)


def _ohlc(rows: int = 100) -> pd.DataFrame:
    close = 100.0 + np.arange(rows, dtype=np.float64) * 0.25
    return pd.DataFrame(
        {
            "日期": pd.date_range("2024-01-01", periods=rows).strftime("%Y%m%d").astype(int),
            "證券代號": "2330",
            "開盤價": close - 0.2,
            "最高價": close + 1.0,
            "最低價": close - 1.0,
            "收盤價": close,
            "成交股數": np.arange(rows) + 1000,
        }
    )


def test_price_cleaner_detaches_float_array_and_preserves_missing_values() -> None:
    source = pd.Series(np.array([10.0, np.inf, 12.0], dtype=np.float64))
    before = source.copy(deep=True)

    cleaned = clean_price_values(source)

    pd.testing.assert_series_equal(source, before)
    assert np.isnan(cleaned[1])
    assert not np.shares_memory(cleaned, source.to_numpy())


def test_causal_kernel_does_not_mutate_ohlc_or_depend_on_future_suffix() -> None:
    prefix = _ohlc(90)
    prefix.loc[30, "收盤價"] = np.nan
    before = prefix.copy(deep=True)
    extended = pd.concat([prefix, _ohlc(20).assign(日期=lambda df: pd.date_range("2025-01-01", periods=len(df)))], ignore_index=True)

    first = calculate_causal_indicators(prefix)
    with_suffix = calculate_causal_indicators(extended)

    pd.testing.assert_frame_equal(prefix, before)
    assert list(first.columns[-len(CAUSAL_INDICATOR_COLUMNS) :]) == list(CAUSAL_INDICATOR_COLUMNS)
    for column in CAUSAL_INDICATOR_COLUMNS:
        np.testing.assert_allclose(
            first[column].to_numpy(dtype=float),
            with_suffix.loc[: len(prefix) - 1, column].to_numpy(dtype=float),
            equal_nan=True,
        )


def test_kernel_keeps_gap_and_warmup_missing_including_atr_and_adx() -> None:
    source = _ohlc(100)
    source.loc[40, ["開盤價", "最高價", "最低價", "收盤價"]] = np.nan

    result = calculate_causal_indicators(source)

    for column in CAUSAL_INDICATOR_COLUMNS:
        assert pd.isna(result.loc[40, column])
    assert result.loc[41:54, "ATR"].isna().all()
    assert pd.notna(result.loc[55, "ATR"])
    assert result.loc[41:67, "ADX"].isna().all()
    assert pd.notna(result.loc[68, "ADX"])


@pytest.mark.parametrize("bad_row", [{"開盤價": 0.0}, {"最高價": 99.0}])
def test_kernel_rejects_nonpositive_or_inconsistent_ohlc(bad_row: dict[str, float]) -> None:
    source = _ohlc(5)
    for column, value in bad_row.items():
        source.loc[2, column] = value

    with pytest.raises(ValueError, match="OHLC"):
        calculate_causal_indicators(source)


def test_kernel_validates_integer_dates_order_duplicates_and_single_stock() -> None:
    source = _ohlc(5)
    assert calculate_causal_indicators(source)["ATR"].isna().all()

    with pytest.raises(ValueError, match="遞增"):
        calculate_causal_indicators(source.iloc[::-1].reset_index(drop=True))
    duplicate = source.copy()
    duplicate.loc[4, "日期"] = duplicate.loc[3, "日期"]
    with pytest.raises(ValueError, match="重複日期"):
        calculate_causal_indicators(duplicate)
    mixed_stock = source.copy()
    mixed_stock.loc[1, "證券代號"] = "2317"
    with pytest.raises(ValueError, match="單一股票"):
        calculate_causal_indicators(mixed_stock)


def test_calculator_normalizes_integer_dates_and_sorts_descending_input() -> None:
    source = _ohlc(80).iloc[::-1].reset_index(drop=True)
    result = TechnicalIndicatorCalculator(logger=logging.getLogger(__name__)).calculate_all_indicators(
        source,
        "2330",
    )

    assert result is not None
    assert result["日期"].is_monotonic_increasing
    assert result["日期"].iloc[0] == "2024-01-01"
    duplicate = _ohlc(80)
    duplicate.loc[79, "日期"] = duplicate.loc[78, "日期"]
    assert (
        TechnicalIndicatorCalculator(logger=logging.getLogger(__name__)).calculate_all_indicators(
            duplicate,
            "2330",
        )
        is None
    )


def test_public_custom_atr_recovers_after_gap_with_requested_period() -> None:
    source = _ohlc(50)
    source.loc[20, ["開盤價", "最高價", "最低價", "收盤價"]] = np.nan

    result = TechnicalAnalyzer().add_volatility_indicators(
        source,
        config={
            "bollinger": {"enabled": False},
            "sar": {"enabled": False},
            "atr": {"enabled": True, "period": 3},
        },
        full_config={"config_schema_version": 1},
    )

    assert pd.isna(result.loc[20, "ATR"])
    assert result.loc[21:23, "ATR"].isna().all()
    assert pd.notna(result.loc[24, "ATR"])


def test_currentity_slice_uses_same_full_prefix_values_as_normal_publication() -> None:
    source = _ohlc(160)
    calculator = TechnicalIndicatorCalculator(logger=object())
    all_values = calculator.calculate_all_indicators(source, "2330")
    currentity_values = calculate_causal_indicators(source).iloc[-30:]
    full_prefix_slice = all_values.iloc[-30:]

    for column in CAUSAL_INDICATOR_COLUMNS:
        np.testing.assert_allclose(
            full_prefix_slice[column].to_numpy(dtype=float),
            currentity_values[column].to_numpy(dtype=float),
            equal_nan=True,
        )
