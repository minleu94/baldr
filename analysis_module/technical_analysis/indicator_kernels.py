"""不依賴 UI/Application 的技術指標純資料 kernel。"""

import numpy as np
import pandas as pd

from utils.numeric_text import normalize_grouped_numeric_text


def clean_price_values(series: pd.Series) -> np.ndarray:
    """將價格轉成 float64 array，保留缺值供呼叫端分段計算。"""
    cleaned = series
    if not pd.api.types.is_numeric_dtype(cleaned.dtype):
        cleaned = cleaned.map(normalize_grouped_numeric_text)
    cleaned = pd.to_numeric(cleaned, errors="coerce")
    prices = cleaned.to_numpy(dtype=np.float64, copy=True, na_value=np.nan)
    prices[~np.isfinite(prices)] = np.nan
    return np.ascontiguousarray(prices, dtype=np.float64)
