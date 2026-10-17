"""計分策略1.1.0的數值分析入口；缺指標不以其他日期或零補造。"""
from typing import Any

import numpy as np
import pandas as pd

INPUT_POLICY = {
    "schema": "causal-score-input.v1",
    "ohlcv": "finite_positive_consistent_ohlc_nonnegative_volume_or_all_four_quotes_missing_with_observed_zero_volume",
    "indicators": "preserve_missing_nonfinite_as_unknown_no_forward_backward_or_zero_fill",
    "unquoted_row": "preserve_raw_unknown_no_order_no_assumed_suspension",
    "analysis_segments": "configure_and_score_contiguous_quoted_segments_reset_internal_atr_cache",
    "dates": "unique_increasing_normalized_naive_daily_index",
    "historical_availability": "not_proven_by_numeric_causality",
}


def prepare_causal_score_input(frame: pd.DataFrame) -> pd.DataFrame:
    from analysis_module.technical_analysis.technical_date_support import safe_convert_technical_dates
    result = frame.copy(deep=True)
    if "日期" in result:
        dates = pd.DatetimeIndex(safe_convert_technical_dates(result["日期"]))
        if isinstance(result.index, pd.DatetimeIndex) and not result.index.equals(dates):
            raise ValueError("因果計分日期欄與原日索引衝突")
        result.index = dates
        result = result.drop(columns=["日期"])
    if (not isinstance(result.index, pd.DatetimeIndex) or result.index.hasnans
            or result.index.tz is not None or result.index.has_duplicates
            or not result.index.is_monotonic_increasing or not result.index.equals(result.index.normalize())):
        raise ValueError("因果計分輸入須為唯一遞增的無時區日索引")
    aliases = {
        "open": ("開盤價", "Open", "open"), "high": ("最高價", "High", "high"),
        "low": ("最低價", "Low", "low"), "close": ("收盤價", "Close", "close"),
        "volume": ("成交股數", "Volume", "volume"),
    }
    chosen = {key: next((column for column in names if column in result), None) for key, names in aliases.items()}
    if any(column is None for column in chosen.values()):
        raise ValueError("因果計分缺原OHLCV欄位")
    # 只有原缺值／來源明示空白才可當無報價；四個壞字串或inf不是缺價日。
    raw_quote_missing = {
        name: result[chosen[name]].isna() | result[chosen[name]].astype(str).str.strip().isin(("", "--"))
        for name in ("open", "high", "low", "close")
    }
    numerical = set(result.select_dtypes(include=[np.number]).columns)
    numerical.update(column for names in aliases.values() for column in names if column in result)
    indicators = {"RSI", "rsi", "RSI_14", "MACD", "macd", "MACD_Signal", "MACD_signal", "macd_signal", "Signal",
                  "MACD_hist", "macd_hist", "MACD_histogram", "slowk", "slowd", "SlowK", "SlowD", "K", "D",
                  "ADX", "adx", "ATR", "atr", "upperband", "middleband", "lowerband", "SAR", "TSF"}
    numerical.update(column for column in result if column in indicators or
                     any(column.startswith(prefix) and column[len(prefix):].isdigit() for prefix in ("MA", "SMA", "MA_")))
    # 套件數值轉換只在本分析邊界；不對缺行情、暖機或無限值補日期／數值。
    for column in numerical:
        values = result[column]
        if values.dtype == object:
            values = values.astype(str).str.replace(",", "", regex=False).str.strip().replace({"--": None, "": None})
        result[column] = pd.to_numeric(values, errors="coerce").astype("float64").replace([np.inf, -np.inf], np.nan)
    def field(name: str) -> Any:
        return result[chosen[name]]
    if any(not result[column].equals(field(name)) for name, names in aliases.items() for column in names if column in result):
        raise ValueError("因果計分OHLCV別名衝突")
    if any((field(name).isna() & ~raw_quote_missing[name]).any() for name in raw_quote_missing):
        raise ValueError("因果計分OHLCV含不可解析或非有限原報價")
    unquoted = pd.concat(list(raw_quote_missing.values()), axis=1).all(axis=1) & (field("volume") == 0)
    if (any((field(name).isna() & ~unquoted).any() or ((field(name) <= 0) & ~unquoted).any() for name in ("open", "high", "low", "close"))
            or field("volume").isna().any() or (field("volume") < 0).any()
            or (field("low") > field("high")).any()
            or (field("open") > field("high")).any() or (field("open") < field("low")).any()
            or (field("close") > field("high")).any() or (field("close") < field("low")).any()):
        raise ValueError("因果計分OHLCV缺件、非有限或矛盾；不可填價／填量後回測")
    result["_causal_quote_available"] = ~unquoted
    return result
